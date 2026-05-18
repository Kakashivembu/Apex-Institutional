#!/usr/bin/env python
"""
APEX INSTITUTIONAL - AGENT VISION DIAGNOSTIC SCRIPT
====================================================
Safe, standalone diagnostic that audits what data feeds the 3-Agent Consensus Engine.
Does NOT execute trades or send prompts to NVIDIA API.

Run: python test_agent_vision.py
Output: AGENT_VISION_AUDIT.log (detailed raw prompts)
        Console summary
"""

import sys
import os
import json
import re
import asyncio
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Add nvidia_apex_trader to path
_script_dir = os.path.dirname(os.path.abspath(__file__))
# If running from root (test_agent_vision.py in root), add nvidia_apex_trader subdir
if os.path.basename(_script_dir) != "nvidia_apex_trader":
    _trader_dir = os.path.join(_script_dir, "nvidia_apex_trader")
else:
    _trader_dir = _script_dir
sys.path.insert(0, _trader_dir)

os.environ.setdefault('DOTENV_SKIP_LOAD', 'false')
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    from dotenv import load_dotenv
    load_dotenv(env_path)

from core.data import fetch_multi_timeframe, fetch_dom_imbalance, fetch_liquidity_data_sync, format_for_llm
from core.memory import load_memory
from core.brain import NVIDIA_API_KEY, NVIDIA_KEYS, get_market_sentiment


# =============================================================================
# DATA FETCHING FUNCTIONS (mirrors server.py)
# =============================================================================

async def fetch_live_btc_data_sync():
    """Fetch live BTC market data from Delta Exchange (primary) + Binance (fallback)."""
    import requests as req

    # PRIMARY: Delta Exchange
    def _fetch_delta():
        try:
            base_url = "https://api.delta.exchange"
            url = f"{base_url}/v2/tickers"
            r = req.get(url, timeout=10, verify=False)
            if r.status_code != 200:
                return None
            data = r.json()
            tickers = data.get("result", [])
            for ticker in tickers:
                sym = ticker.get("symbol", "").upper().replace("-", "").replace("_", "")
                if sym == "BTCUSD":
                    price = float(ticker.get("mark_price", 0) or 0)
                    if price < 60000:
                        continue
                    if price > 0:
                        return ticker
            return None
        except Exception as e:
            print(f"[DELTA API] Error: {e}")
            return None

    btc_ticker = await asyncio.to_thread(_fetch_delta)

    if btc_ticker:
        last_price = float(btc_ticker.get('mark_price', 0) or 0)
        if last_price <= 0:
            last_price = float(btc_ticker.get('close_price', 0) or 0)
        price_change_pct = float(btc_ticker.get('price_change_percent', 0) or 0)
        high_price = float(btc_ticker.get('high_price', 0) or 0)
        low_price = float(btc_ticker.get('low_price', 0) or 0)
        volume = float(btc_ticker.get('volume', 0) or 0)
        return {
            "last_price": last_price,
            "price_change_pct": price_change_pct,
            "high_price": high_price,
            "low_price": low_price,
            "volume": volume
        }

    # FALLBACK: Binance
    def _fetch_binance():
        try:
            url = "https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=BTCUSDT"
            r = req.get(url, timeout=10)
            if r.status_code != 200:
                return None
            data = r.json()
            return {
                "last_price": float(data.get("lastPrice", 0)),
                "price_change_pct": float(data.get("priceChangePercent", 0)),
                "high_price": float(data.get("highPrice", 0)),
                "low_price": float(data.get("lowPrice", 0)),
                "volume": float(data.get("quoteVolume", 0)) / 100  # Approximate BTC volume
            }
        except Exception as e:
            print(f"[BINANCE API] Error: {e}")
            return None

    return await asyncio.to_thread(_fetch_binance)


async def run_diagnostics():
    """Main diagnostic routine - fetches all data and assembles prompts."""
    print("=" * 70)
    print("APEX AGENT VISION DIAGNOSTIC")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()

    # Initialize output log
    log_lines = []
    log_lines.append("=" * 70)
    log_lines.append("APEX INSTITUTIONAL - AGENT VISION AUDIT LOG")
    log_lines.append(f"Generated: {datetime.now().isoformat()}")
    log_lines.append("=" * 70)
    log_lines.append("")

    # ==========================================================================
    # SECTION 1: CLAW DESK DATA (Liquidity/Sentiment)
    # ==========================================================================
    print("[1/5] Fetching CLAW liquidity data...")

    claw_output = await get_market_sentiment("")
    liquidity_data = claw_output.get("liquidity_data", "Liquidity data unavailable.")
    sentiment_report = f"Sentiment: {claw_output.get('sentiment', 'NEUTRAL')} ({claw_output.get('confidence', 0)}%) - {claw_output.get('report', '')}"

    log_lines.append("=" * 70)
    log_lines.append("SECTION 1: [CLAW DESK DATA] - Liquidity & Sentiment")
    log_lines.append("=" * 70)
    log_lines.append(f"Raw Liquidity Data String:\n{liquidity_data}")
    log_lines.append("")
    log_lines.append(f"Parsed Sentiment Report:\n{sentiment_report}")
    log_lines.append("")
    log_lines.append(f"Full CLAW Output Dict:")
    log_lines.append(json.dumps(claw_output, indent=2))
    log_lines.append("")

    print(f"   Sentiment: {claw_output.get('sentiment')} ({claw_output.get('confidence')}%)")
    print(f"   Dominant Side: {claw_output.get('dominant_side')}")
    print(f"   Squeeze Risk: {claw_output.get('squeeze_risk')}")

    # ==========================================================================
    # SECTION 2: DOM X-RAY DATA (Order Book Imbalance)
    # ==========================================================================
    print("[2/5] Fetching DOM X-Ray order book imbalance...")

    dom_data = await fetch_dom_imbalance("BTCUSD")

    log_lines.append("=" * 70)
    log_lines.append("SECTION 2: [DOM X-RAY DATA] - Level 2 Order Book")
    log_lines.append("=" * 70)
    log_lines.append(dom_data)
    log_lines.append("")

    print(f"   {dom_data[:120]}...")

    # ==========================================================================
    # SECTION 3: CANDLE DATA (Multi-Timeframe)
    # ==========================================================================
    print("[3/5] Fetching multi-timeframe candle data...")

    candle_data = await fetch_multi_timeframe(["BTCUSD"])

    log_lines.append("=" * 70)
    log_lines.append("SECTION 3: [CANDLE DATA] - Multi-Timeframe Trend")
    log_lines.append("=" * 70)
    log_lines.append(candle_data)
    log_lines.append("")

    print(f"   {candle_data[:120]}...")

    # ==========================================================================
    # SECTION 4: BTC MARKET DATA (Live Price)
    # ==========================================================================
    print("[4/5] Fetching live BTC price...")

    btc_price_data = await fetch_live_btc_data_sync()

    if btc_price_data:
        btc_price = btc_price_data.get("last_price", 0)
        btc_change = btc_price_data.get("price_change_pct", 0)
        btc_high = btc_price_data.get("high_price", 0)
        btc_low = btc_price_data.get("low_price", 0)
        btc_volume = btc_price_data.get("volume", 0)
        btc_market_data = f"""=== REAL-TIME BTC/USDT MARKET DATA ===
Current Price: ${btc_price:,.2f}
24h Change: {btc_change:+.2f}%
24h High: ${btc_high:,.2f}
24h Low: ${btc_low:,.2f}
24h Volume: {btc_volume:,.0f} BTC

Recent Price Action:
- Last price showing {btc_change:+.2f}% movement
- Trading range: ${btc_low:,.2f} - ${btc_high:,.2f}
- Current volatility: {'HIGH' if abs(btc_change) > 3 else 'MEDIUM' if abs(btc_change) > 1 else 'LOW'}
"""
    else:
        btc_price = 0
        btc_market_data = "ERROR: Could not fetch live BTC data"

    log_lines.append("=" * 70)
    log_lines.append("SECTION 4: [BTC MARKET DATA] - Live Price Snapshot")
    log_lines.append("=" * 70)
    log_lines.append(btc_market_data)
    log_lines.append("")

    print(f"   BTC Price: ${btc_price:,.2f}")

    # ==========================================================================
    # ASSEMBLE MARKET_DATA_TEXT (exact replica of server.py line 339)
    # ==========================================================================
    market_data_text = f"Current equity: $0, Positions: 0 | {btc_market_data}\n\n=== CANDLE TREND DATA ===\n{candle_data}\n\n=== LEVEL 2 ORDER BOOK INTELLIGENCE ===\n{dom_data}"

    log_lines.append("=" * 70)
    log_lines.append("ASSEMBLED: [MARKET_DATA_TEXT] - Exact string sent to evaluate_market()")
    log_lines.append("=" * 70)
    log_lines.append(market_data_text)
    log_lines.append("")

    # ==========================================================================
    # SECTION 5: MACRO AGENT PROMPT (Exact replica of brain.py analyze_macro_trend)
    # ==========================================================================
    print("[5/5] Building Macro & Scalper agent prompts...")

    trading_memory = load_memory()
    memory_section = (f"""CRITICAL DIRECTIVES FROM HISTORICAL MEMORY:
{trading_memory[:1500] if trading_memory else 'No historical lessons recorded.'}
You MUST obey any lessons regarding trend alignment, risk-reward ratios, or timeframe conflicts.""" if trading_memory else "")

    macro_system_prompt = f"""You are a Macro Trend Follower AI.
Analyze the 1H/4H candles and the CLAW sentiment report. Determine the macro trend.
Output strictly 'BUY', 'SELL', or 'HOLD'.
Also assess current market volatility and recommend risk parameters.
IMPORTANT: The market data includes a 'DOM X-Ray' section showing the Level 2 Order Book imbalance (physical resting buy/sell walls). Use this to:
- INCREASE leverage if massive walls SUPPORT your trade direction (e.g., huge bid wall below for LONG)
- DECREASE leverage if massive walls OPPOSE your trade direction (e.g., huge ask wall above for LONG)
- Widen SL if trading into a wall, tighten TP if a wall sits near your target
You have full autonomy over position leverage, ranging from 1x to 100x. You MUST scale this leverage mathematically with your confidence score. Example baseline: 90%+ confidence = 50x to 100x leverage. 75% to 89% confidence = 20x to 50x leverage. Below 75% confidence = 5x to 15x leverage. Adjust dynamically based on market volatility and order book imbalance.
Respond ONLY in valid JSON format:
{{"decision": "BUY"|"SELL"|"HOLD", "confidence": 0-100, "volatility": "low"|"medium"|"high", "recommended_leverage": 1-100, "reasoning": "brief explanation"}}{memory_section}"""

    macro_user_prompt = f"""=== CLAW SENTIMENT REPORT ===
{sentiment_report}

=== CANDLE TREND DATA ===
{candle_data}

=== LEVEL 2 ORDER BOOK INTELLIGENCE ===
{dom_data}

Determine the macro trend direction based on the above data."""

    log_lines.append("=" * 70)
    log_lines.append("SECTION 5A: [MACRO AGENT SYSTEM PROMPT]")
    log_lines.append("=" * 70)
    log_lines.append(macro_system_prompt)
    log_lines.append("")

    log_lines.append("=" * 70)
    log_lines.append("SECTION 5B: [MACRO AGENT USER PROMPT] - Full input to Macro agent")
    log_lines.append("=" * 70)
    log_lines.append(macro_user_prompt)
    log_lines.append("")

    # ==========================================================================
    # SECTION 6: SCALPER AGENT PROMPT (Exact replica of brain.py find_sniper_entry)
    # ==========================================================================

    live_btc_price = btc_price
    current_price = live_btc_price

    if current_price <= 0:
        current_price = 75000  # Fallback for calculation purposes

    scalper_system_prompt = (
        "You are an Elite Scalper AI specializing in BTC/USDT futures. "
        f"The current live BTC price is ${current_price:,.2f}. "
        "Based on this exact price, calculate precise entry, stop loss, and take profit levels for a scalp trade. "
        "IMPORTANT: The market data includes a 'DOM X-Ray' section showing Level 2 Order Book resting walls. "
        "Use physical bid walls as support targets for LONG entries (enter just above massive bids). "
        "Use physical ask walls as resistance targets for SHORT entries (enter just below massive asks). "
        "If a massive wall opposes your trade direction, widen your stop loss to account for potential wall absorption. "
        "You have full autonomy over position leverage, ranging from 1x to 100x. You MUST scale this leverage mathematically with your confidence score. "
        "Example baseline: 90%+ confidence = 50x to 100x leverage. 75% to 89% confidence = 20x to 50x leverage. Below 75% confidence = 5x to 15x leverage. Adjust dynamically based on market volatility. "
        '"Output ONLY valid JSON: {"decision": "BUY"|"SELL"|"HOLD", "confidence": 0-100, '
        '"entry_price": calculated_entry_price_as_number, '
        '"stop_loss_pct": 0.3-3.0, "take_profit_pct": 0.5-10.0, "leverage": 1-100, "reasoning": "brief"}'
        + (f"\n\nCRITICAL DIRECTIVES FROM HISTORICAL MEMORY:\n{trading_memory[:1500]}\nYou MUST obey any lessons regarding timeframe alignment, risk-reward ratios, or trade conflicts mentioned above." if trading_memory else "")
    )

    scalper_user_prompt = (
        f"BTC live price: ${current_price:,.2f}. "
        f"Market data: {market_data_text}. "
        "Calculate exact entry price, SL (% from entry), TP (% from entry), and recommended leverage for a scalp. "
        "Return ONLY valid JSON with ALL fields: decision, confidence, entry_price, stop_loss_pct, take_profit_pct, leverage, reasoning."
    )

    log_lines.append("=" * 70)
    log_lines.append("SECTION 6A: [SCALPER AGENT SYSTEM PROMPT]")
    log_lines.append("=" * 70)
    log_lines.append(scalper_system_prompt)
    log_lines.append("")

    log_lines.append("=" * 70)
    log_lines.append("SECTION 6B: [SCALPER AGENT USER PROMPT] - Full input to Scalper agent")
    log_lines.append("=" * 70)
    log_lines.append(scalper_user_prompt)
    log_lines.append("")

    # ==========================================================================
    # WRITE LOG FILE
    # ==========================================================================
    log_file = os.path.join(os.path.dirname(__file__), "AGENT_VISION_AUDIT.log")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    print()
    print("=" * 70)
    print("AGENT VISION AUDIT COMPLETE")
    print("=" * 70)
    print(f"Log written to: {log_file}")
    print()
    print("SUMMARY:")
    print(f"  BTC Price:         ${btc_price:,.2f}")
    print(f"  Volatility:        {'HIGH' if abs(btc_change) > 3 else 'MEDIUM' if abs(btc_change) > 1 else 'LOW'}")
    print(f"  BTC 24h Change:    {btc_change:+.2f}%")
    print(f"  Sentiment:         {claw_output.get('sentiment')} ({claw_output.get('confidence')}%)")
    print(f"  Dominant Side:     {claw_output.get('dominant_side')}")
    print(f"  Squeeze Risk:      {claw_output.get('squeeze_risk')}")
    print(f"  DOM Imbalance:     {dom_data[:80]}...")
    print()
    print(f"PROMPT SIZES:")
    print(f"  Macro System:      {len(macro_system_prompt):,} chars")
    print(f"  Macro User:        {len(macro_user_prompt):,} chars")
    print(f"  Scalper System:    {len(scalper_system_prompt):,} chars")
    print(f"  Scalper User:      {len(scalper_user_prompt):,} chars")
    print(f"  Total Market Data: {len(market_data_text):,} chars")
    print()
    print("Check AGENT_VISION_AUDIT.log for full raw prompt dump.")
    print("=" * 70)

    return {
        "btc_price": btc_price,
        "sentiment": claw_output,
        "dom_data": dom_data,
        "candle_data": candle_data,
        "market_data_text": market_data_text,
        "macro_user_prompt": macro_user_prompt,
        "scalper_user_prompt": scalper_user_prompt,
        "log_file": log_file
    }


if __name__ == "__main__":
    results = asyncio.run(run_diagnostics())