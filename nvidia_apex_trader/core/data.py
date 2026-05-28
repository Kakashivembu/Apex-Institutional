import MetaTrader5 as mt5
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import asyncio
import os
import socket
import requests
import json
import traceback
from datetime import datetime

_last_global_dom_result_signature = None
_last_global_dom_transport_mode = None

# ccxt is imported lazily inside fetch_global_liquidity() to avoid
# module-level hangs on systems where ccxt.async_support blocks during init.
ccxt_async = None  # Sentinel; replaced at runtime if ccxt is available

def fetch_candles_sync(symbol, resolution, limit=1000, network="mainnet"):
    """Fetch candles from MT5 IPC. Legacy Delta Exchange routing removed."""
    import MetaTrader5 as mt5
    from core.mt5_engine import _resolve_tradeable_symbol

    # Resolve broker-specific symbol name (e.g., GOLD.i# -> XAUUSD.x on GoatFunded)
    symbol = _resolve_tradeable_symbol(symbol)

    res_map = {
        "1m": mt5.TIMEFRAME_M1,
        "5m": mt5.TIMEFRAME_M5,
        "15m": mt5.TIMEFRAME_M15,
        "1h": mt5.TIMEFRAME_H1,
        "4h": mt5.TIMEFRAME_H4,
    }
    timeframe = res_map.get(resolution.lower(), mt5.TIMEFRAME_M1)

    if not mt5.symbol_select(symbol, True):
        print(f"[MT5 CANDLES] Cannot select {symbol} in Market Watch")

    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, limit)
    if rates is None:
        error = mt5.last_error()
        print(f"[MT5 CANDLES] Failed to copy rates for {symbol} {resolution}: {error}")
        return []

    candles = []
    for rate in rates:
        candles.append({
            "time": int(rate[0]),
            "open": float(rate[1]),
            "high": float(rate[2]),
            "low": float(rate[3]),
            "close": float(rate[4]),
            "volume": int(rate[5])
        })
    return candles

async def fetch_multi_timeframe(symbols=["GOLD"], network="mainnet"):
    # MARKET DATA: Always fetch from mainnet regardless of trading network.
    # The fetch_candles_sync function hardcodes mainnet base_url internally.
    resolutions = ["1m", "5m", "15m", "1h", "4h"]
    market_data = {}

    for sym in symbols:
        market_data[sym] = {}
        for res in resolutions:
            # Run the synchronous requests in threadpool
            # network param kept for API parity but fetch_candles_sync uses mainnet internally
            candles = await asyncio.to_thread(fetch_candles_sync, sym, res, 1000, network)
            market_data[sym][res] = candles

    return format_for_llm(market_data)

def _compute_ema(closes: list, period: int) -> list:
    """Compute Exponential Moving Average from a list of close prices."""
    if len(closes) < period:
        return closes[:]
    multiplier = 2 / (period + 1)
    ema = [sum(closes[:period]) / period]  # Seed with SMA
    for price in closes[period:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    return ema


def compute_trend_indicators(closes: list) -> dict:
    """Compute technical trend indicators from close prices.
    Returns EMA cross, momentum, trend strength, and candle direction.
    All computed locally in Python — zero API cost."""
    if len(closes) < 5:
        return {"ema_cross": "NEUTRAL", "momentum_pct": 0, "trend_strength": 0,
                "consecutive_higher": 0, "consecutive_lower": 0,
                "green_count": 0, "red_count": 0, "trend_score": 0,
                "ema9": 0, "ema21": 0}

    # --- EMA 9/21 Cross ---
    ema9 = _compute_ema(closes, 9)
    ema21 = _compute_ema(closes, 21)
    if len(ema9) >= 2 and len(ema21) >= 2:
        ema9_now, ema21_now = ema9[-1], ema21[-1]
        ema9_prev, ema21_prev = ema9[-2], ema21[-2]
        if ema9_now > ema21_now and ema9_prev <= ema21_prev:
            ema_cross = "GOLDEN_CROSS"  # Bullish
        elif ema9_now < ema21_now and ema9_prev >= ema21_prev:
            ema_cross = "DEATH_CROSS"  # Bearish
        elif ema9_now > ema21_now:
            ema_cross = "BULLISH"  # EMA9 above EMA21
        elif ema9_now < ema21_now:
            ema_cross = "BEARISH"  # EMA9 below EMA21
        else:
            ema_cross = "NEUTRAL"
    else:
        ema_cross = "NEUTRAL"
        ema9_now = ema21_now = closes[-1]

    # --- Momentum: % change over last 10 candles ---
    lookback = min(10, len(closes) - 1)
    if lookback > 0 and closes[-lookback - 1] > 0:
        momentum_pct = ((closes[-1] - closes[-lookback - 1]) / closes[-lookback - 1]) * 100
    else:
        momentum_pct = 0

    # --- Trend Strength: consecutive higher/lower closes ---
    higher_count = 0
    lower_count = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] > closes[i - 1]:
            higher_count += 1
        else:
            break
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] < closes[i - 1]:
            lower_count += 1
        else:
            break

    # --- Candle Body Direction (last 5) ---
    last5 = closes[-6:] if len(closes) >= 6 else closes
    green_count = sum(1 for i in range(1, len(last5)) if last5[i] > last5[i - 1])
    red_count = sum(1 for i in range(1, len(last5)) if last5[i] < last5[i - 1])

    # --- Composite Trend Score: -100 to +100 ---
    score = 0
    # EMA component (±30)
    if ema_cross in ("GOLDEN_CROSS", "BULLISH"):
        score += 30 if ema_cross == "GOLDEN_CROSS" else 20
    elif ema_cross in ("DEATH_CROSS", "BEARISH"):
        score -= 30 if ema_cross == "DEATH_CROSS" else 20
    # Momentum component (±40)
    score += max(-40, min(40, momentum_pct * 20))
    # Consecutive candles component (±20)
    score += min(20, higher_count * 5) - min(20, lower_count * 5)
    # Green/Red ratio component (±10)
    score += (green_count - red_count) * 2

    score = max(-100, min(100, int(score)))

    return {
        "ema_cross": ema_cross,
        "ema9": round(ema9_now, 2) if ema9 else 0,
        "ema21": round(ema21_now, 2) if ema21 else 0,
        "momentum_pct": round(momentum_pct, 2),
        "trend_strength": higher_count if higher_count > 0 else -lower_count,
        "consecutive_higher": higher_count,
        "consecutive_lower": lower_count,
        "green_count": green_count,
        "red_count": red_count,
        "trend_score": score
    }


def compute_rsi(closes: list, period: int = 3) -> float:
    """Compute RSI (Relative Strength Index) for scalping micro-reversals.
    
    RSI(3) is ultra-fast and catches the exact moment a micro-pullback
    exhausts. Values > 75 = overbought (ideal SHORT entry at local peak).
    Values < 25 = oversold (ideal LONG entry at local trough).
    
    Args:
        closes: List of close prices (needs at least period+1 values)
        period: RSI lookback period (default 3 for scalping)
    
    Returns:
        RSI value 0-100, or 50.0 if insufficient data.
    """
    if len(closes) < period + 1:
        return 50.0  # Neutral if insufficient data
    
    # Calculate price changes
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    
    # Separate gains and losses
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]
    
    # Initial average using SMA
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    # Smooth with exponential moving average (Wilder's method)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100.0  # Pure uptrend
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)


def compute_stoch_rsi(closes: list, rsi_period: int = 3, stoch_period: int = 3) -> float:
    """Compute Stochastic RSI for extreme overbought/oversold detection.
    
    Stoch RSI normalizes RSI into a 0-100 range based on its own
    recent high/low, making it even more sensitive to micro-reversals.
    Values > 80 = extreme overbought. Values < 20 = extreme oversold.
    
    Returns:
        Stochastic RSI value 0-100, or 50.0 if insufficient data.
    """
    if len(closes) < rsi_period + stoch_period + 1:
        return 50.0
    
    # Compute RSI series
    rsi_values = []
    for i in range(rsi_period + 1, len(closes) + 1):
        rsi_val = compute_rsi(closes[:i], rsi_period)
        rsi_values.append(rsi_val)
    
    if len(rsi_values) < stoch_period:
        return 50.0
    
    # Stochastic of last stoch_period RSI values
    recent_rsi = rsi_values[-stoch_period:]
    rsi_high = max(recent_rsi)
    rsi_low = min(recent_rsi)
    
    if rsi_high == rsi_low:
        return 50.0
    
    current_rsi = rsi_values[-1]
    stoch = ((current_rsi - rsi_low) / (rsi_high - rsi_low)) * 100
    return round(stoch, 2)

def calculate_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return 0
    true_ranges = []
    for i in range(1, len(closes)):
        h = highs[i]
        l = lows[i]
        pc = closes[i-1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        true_ranges.append(tr)
    return sum(true_ranges[-period:]) / period


def format_for_llm(market_data):
    """Format market data for LLM consumption with full technical analysis.
    Includes EMA 9/21 cross, momentum %, trend strength, candle direction,
    and Institutional Smart Money Concepts (FVGs and Order Blocks)."""
    from core.macro_sensors import detect_fair_value_gaps, detect_order_blocks

    lines = ["--- MT5 MARKET DATA SNAPSHOT ---"]
    for sym, res_dict in market_data.items():
        lines.append(f"\nAsset: {sym}")
        for res, candles in res_dict.items():
            if not candles:
                lines.append(f" [{res}] No data available (Network Error?).")
                continue

            closes = [float(c.get('close', 0)) for c in candles]
            highs = [float(c.get('high', 0)) for c in candles]
            lows = [float(c.get('low', 0)) for c in candles]

            if len(closes) > 0:
                current = closes[-1]
                overall_trend = "UP" if closes[-1] > closes[0] else "DOWN"
                indicators = compute_trend_indicators(closes)

                lines.append(
                    f" [{res}] Price: {current} | Trend: {overall_trend} "
                    f"| High: {max(highs)} | Low: {min(lows)} "
                    f"| EMA9/21: {indicators['ema_cross']} ({indicators['ema9']}/{indicators['ema21']}) "
                    f"| Momentum({min(10, len(closes)-1)}): {indicators['momentum_pct']:+.2f}% "
                    f"| Strength: {indicators['consecutive_higher']} higher / {indicators['consecutive_lower']} lower closes "
                    f"| Last 5 candles: {indicators['green_count']} green / {indicators['red_count']} red "
                    f"| Trend Score: {indicators['trend_score']:+d}/100"
                )

                # ── SMC DETECTION (lightweight, 50-candle lookback) ──
                try:
                    fvg = detect_fair_value_gaps(candles, current_price=current, max_lookback=50)
                    ob = detect_order_blocks(candles, current_price=current, max_lookback=50)

                    # FVG section
                    fvg_lines = []
                    if fvg.get("nearest_bullish"):
                        nb = fvg["nearest_bullish"]
                        fvg_lines.append(f"Bullish FVG (Support): {nb['gap_bottom']}-{nb['gap_top']} (mid {nb['mid']})")
                    if fvg.get("nearest_bearish"):
                        nb = fvg["nearest_bearish"]
                        fvg_lines.append(f"Bearish FVG (Resistance): {nb['gap_bottom']}-{nb['gap_top']} (mid {nb['mid']})")
                    if fvg_lines:
                        lines.append(f" [{res}] FVGs: {' | '.join(fvg_lines)}")

                    # Order Block section
                    ob_lines = []
                    if ob.get("nearest_bullish"):
                        nb = ob["nearest_bullish"]
                        ob_lines.append(f"Bullish OB (Demand): {nb['low']}-{nb['high']}")
                    if ob.get("nearest_bearish"):
                        nb = ob["nearest_bearish"]
                        ob_lines.append(f"Bearish OB (Supply): {nb['low']}-{nb['high']}")
                    if ob_lines:
                        lines.append(f" [{res}] OBs: {' | '.join(ob_lines)}")
                        
                    # Calculate ATR and Dynamic Risk Limits
                    atr = calculate_atr(highs, lows, closes, period=14)
                    dynamic_sl_pct = 0.5
                    dynamic_tp_pct = 1.0
                    
                    if atr > 0:
                        closest_ob_dist = float('inf')
                        if ob.get("nearest_bullish") and current > ob["nearest_bullish"]["high"]:
                            closest_ob_dist = min(closest_ob_dist, current - ob["nearest_bullish"]["high"])
                        if ob.get("nearest_bearish") and ob["nearest_bearish"]["low"] > current:
                            closest_ob_dist = min(closest_ob_dist, ob["nearest_bearish"]["low"] - current)
                            
                        if closest_ob_dist != float('inf'):
                            # Add 1.5x ATR buffer to prevent volatility stop-hunts
                            sl_dist = closest_ob_dist + (1.5 * atr)
                            dynamic_sl_pct = (sl_dist / current) * 100
                            dynamic_sl_pct = min(max(dynamic_sl_pct, 0.2), 1.5)  # Hard cap tighter
                            dynamic_tp_pct = min(dynamic_sl_pct * 2.5, 10.0)     # Target 1:2.5 R:R
                            
                    lines.append(f" [{res}] LIVE VOLATILITY ALIGNMENT: Current ATR is {atr:.2f}. Recommended Dynamic SL distance is {dynamic_sl_pct:.2f}%. Recommended Dynamic TP distance is {dynamic_tp_pct:.2f}%.")
                except Exception as smc_err:
                    lines.append(f" [{res}] SMC: unavailable ({smc_err})")

    return "\n".join(lines)


def fetch_liquidity_data_sync() -> str:
    """Legacy Binance Futures liquidity fetcher — disabled in MT5 mode.
    Returns graceful notice. All market data now comes from MT5 IPC."""
    return "Liquidity Hunter: MT5-native mode. Legacy futures OI/volume endpoints disabled."


async def fetch_liquidity_data():
    """Async wrapper - runs synchronous requests in thread pool to bypass Windows DNS blocking."""
    return await asyncio.to_thread(fetch_liquidity_data_sync)


# ============================================================
# DOM (DEPTH OF MARKET) L2 ORDER BOOK IMBALANCE
# ============================================================

def fetch_dom_imbalance_sync(symbol: str = "GOLD") -> str:
    """Fetch DOM from MT5 market book (Depth of Market) via IPC.

    Uses mt5.market_book_get() for L2 data. Falls back to symbol_info
    if DOM is unavailable. Returns graceful default if MT5 IPC fails.
    """
    from core.mt5_engine import _resolve_tradeable_symbol
    symbol = _resolve_tradeable_symbol(symbol)
    try:
        if not mt5.symbol_select(symbol, True):
            pass

        book = mt5.market_book_get(symbol)
        if book:
            bids = [entry for entry in book if entry.type == 2]  # 2 = bid
            asks = [entry for entry in book if entry.type == 1]  # 1 = ask

            total_bid_vol = sum(b.volume for b in bids)
            total_ask_vol = sum(a.volume for a in asks)
            total_vol = total_bid_vol + total_ask_vol

            if total_vol > 0:
                bid_pct = (total_bid_vol / total_vol) * 100
                ask_pct = (total_ask_vol / total_vol) * 100
                best_bid = bids[0].price if bids else 0
                best_ask = asks[0].price if asks else 0

                all_levels = [(b.price, b.volume, "BID") for b in bids] + [(a.price, a.volume, "ASK") for a in asks]
                biggest_wall = max(all_levels, key=lambda x: x[1]) if all_levels else (0, 0, "NONE")

                if bid_pct >= 65:
                    direction = "BUYERS (strong bid wall)"
                elif bid_pct >= 55:
                    direction = "BUYERS (moderate bid-side lean)"
                elif ask_pct >= 65:
                    direction = "SELLERS (strong ask wall)"
                elif ask_pct >= 55:
                    direction = "SELLERS (moderate ask-side lean)"
                else:
                    direction = "BALANCED"

                return (
                    f"DOM X-Ray (MT5 Market Depth): "
                    f"{total_bid_vol:.0f} lots Support vs {total_ask_vol:.0f} lots Resistance. "
                    f"Imbalance: {bid_pct:.0f}% Bids / {ask_pct:.0f}% Asks — {direction}. "
                    f"Spread: {best_bid:,.2f} / {best_ask:,.2f}. "
                    f"Largest wall: {biggest_wall[1]:.0f} lots {biggest_wall[2]} @ {biggest_wall[0]:,.2f}."
                )

        # Fallback to symbol_info if market book unavailable
        info = mt5.symbol_info(symbol)
        if info is not None:
            spread = info.point * info.spread if info.point and info.spread else 0
            return f"DOM X-Ray (MT5 L1): {symbol} | Bid: {info.bid:,.2f} | Ask: {info.ask:,.2f} | Spread: {spread:,.2f}. Market Depth not subscribed."

        return f"DOM X-Ray: MT5 IPC returned no data for {symbol}"

    except Exception as e:
        return f"DOM X-Ray: Error ({type(e).__name__}) — MT5 IPC failure"


async def fetch_dom_imbalance(symbol: str = "GOLD") -> str:
    """Async wrapper — runs synchronous DOM fetch in thread pool (non-blocking)."""
    return await asyncio.to_thread(fetch_dom_imbalance_sync, symbol)


async def fetch_global_liquidity(symbol="GOLD"):
    """MT5-native liquidity check. Legacy crypto exchange aggregation removed."""
    dom_text = await fetch_dom_imbalance(symbol)
    return {
        "text": f"Global DOM (MT5-only): {dom_text}",
        "bids": 0.0,
        "asks": 0.0,
        "bid_pct": 50.0,
        "ask_pct": 50.0,
        "total_vol": 0.0,
        "wall_price": 0.0,
        "wall_size": 0.0,
        "wall_side": "NONE",
        "wall_source": "MT5",
    }


# ============================================================
# SMART MONEY — FAIR VALUE GAP (FVG) DETECTION ENGINE
# ============================================================

def detect_fvgs(candles):
    """Detect Fair Value Gaps from candle arrays.
    Bullish FVG: Low of Candle 3 > High of Candle 1
    Bearish FVG: High of Candle 3 < Low of Candle 1
    Returns list of unmitigated gaps with metadata."""
    if len(candles) < 3:
        return []

    fvgs = []
    n = len(candles)

    for i in range(2, n):
        c1 = candles[i - 2]
        c2 = candles[i - 1]
        c3 = candles[i]

        c1_high = float(c1.get("high", 0))
        c1_low = float(c1.get("low", 0))
        c3_high = float(c3.get("high", 0))
        c3_low = float(c3.get("low", 0))

        # Bullish FVG: C3 Low above C1 High
        if c3_low > c1_high:
            gap_top = c3_low
            gap_bottom = c1_high
            gap_size = gap_top - gap_bottom

            mitigated_range = 0.0
            for j in range(i + 1, n):
                candle_low = float(candles[j].get("low", 0))
                if gap_size > 0 and candle_low <= gap_top:
                    filled_from_top = max(0, gap_top - max(candle_low, gap_bottom))
                    mitigated_range = max(mitigated_range, (filled_from_top / gap_size) * 100)

            fvgs.append({
                "type": "BULLISH",
                "top": round(gap_top, 2),
                "bottom": round(gap_bottom, 2),
                "index": i,
                "candle_time": candles[i].get("time", 0),
                "freshness": n - i - 1,
                "mitigated_pct": round(mitigated_range, 1),
                "gap_size": round(gap_size, 2)
            })

        # Bearish FVG: C3 High below C1 Low
        elif c3_high < c1_low:
            gap_top = c1_low
            gap_bottom = c3_high
            gap_size = gap_top - gap_bottom

            mitigated_range = 0.0
            for j in range(i + 1, n):
                candle_high = float(candles[j].get("high", 0))
                if gap_size > 0 and candle_high >= gap_bottom:
                    filled_from_bottom = min(candle_high, gap_top) - gap_bottom
                    mitigated_range = max(mitigated_range, (filled_from_bottom / gap_size) * 100)

            fvgs.append({
                "type": "BEARISH",
                "top": round(gap_top, 2),
                "bottom": round(gap_bottom, 2),
                "index": i,
                "candle_time": candles[i].get("time", 0),
                "freshness": n - i - 1,
                "mitigated_pct": round(mitigated_range, 1),
                "gap_size": round(gap_size, 2)
            })

    return fvgs


def score_liquidity(fvgs, current_price):
    """Score FVGs by Liquidity Quality.
    Base 100, -1pt per candle age, -2pt per 1% distance from price,
    mitigation bonus/penalty. Returns sorted list with scores attached."""
    scored = []

    for fvg in fvgs:
        base_score = 100.0
        gap_top = fvg["top"]
        gap_bottom = fvg["bottom"]
        gap_mid = (gap_top + gap_bottom) / 2

        freshness_penalty = fvg["freshness"] * 1.0
        distance = abs(current_price - gap_mid)
        distance_pct = (distance / current_price) * 100
        proximity_penalty = distance_pct * 2.0

        mitigated = fvg["mitigated_pct"]
        if mitigated == 0:
            mitigation_factor = 0
        elif 30 < mitigated < 80:
            mitigation_factor = 5
        elif mitigated >= 80:
            mitigation_factor = -20
        else:
            mitigation_factor = 0

        final_score = max(base_score - freshness_penalty - proximity_penalty + mitigation_factor, 0)

        scored.append({
            **fvg,
            "mid_price": round(gap_mid, 2),
            "distance_from_now": round(distance_pct, 2),
            "liquidity_score": round(final_score, 1)
        })

    scored.sort(key=lambda x: x["liquidity_score"], reverse=True)
    return scored


async def fetch_smart_money_zones(current_price: float = 0, symbol: str = "GOLD") -> str:
    """Fetch 15m + 1h candles, detect FVGs, score them, return top 3 as formatted text.
    Called by server.py after fetch_multi_timeframe to inject into AI prompt payload."""
    try:
        candles_15m = await asyncio.to_thread(fetch_candles_sync, symbol, "15m", 1000, "mainnet")
        candles_1h = await asyncio.to_thread(fetch_candles_sync, symbol, "1h", 1000, "mainnet")

        if not candles_15m and not candles_1h:
            return "Smart Money: No candle data available this cycle."

        # Extract current_price from latest candle if not provided
        if current_price <= 0:
            if candles_15m:
                current_price = float(candles_15m[-1].get("close", 0))
            elif candles_1h:
                current_price = float(candles_1h[-1].get("close", 0))

        # Detect + score FVGs on both timeframes
        fvgs_15m_raw = detect_fvgs(candles_15m) if len(candles_15m) >= 3 else []
        fvgs_1h_raw = detect_fvgs(candles_1h) if len(candles_1h) >= 3 else []

        scored_15m = score_liquidity(fvgs_15m_raw, current_price) if fvgs_15m_raw else []
        scored_1h = score_liquidity(fvgs_1h_raw, current_price) if fvgs_1h_raw else []

        # Combine and take top 3 (prefer near-price, unmitigated)
        all_fvgs = scored_15m + scored_1h
        # Filter: within 3% of price and not fully mitigated
        filtered = [f for f in all_fvgs if f["distance_from_now"] < 3.0 and f["mitigated_pct"] < 95]
        top3 = filtered[:3]

        if not top3:
            # Fallback: just use top 3 by score regardless of proximity
            top3 = all_fvgs[:3]

        if not top3:
            return "Smart Money: No significant liquidity zones detected."

        lines = []
        for fvg in top3:
            gap_pct = (fvg["gap_size"] / current_price) * 100 if current_price else 0
            lines.append(
                f"[{fvg['type']}] FVG | Score: {fvg['liquidity_score']} | "
                f"Zone: ${fvg['bottom']:,.2f} -> ${fvg['top']:,.2f} | "
                f"Gap: {gap_pct:.2f}% | Mitigated: {fvg['mitigated_pct']}%"
            )

        return "\n".join(lines)

    except Exception as e:
        print(f"[SmartMoney] Error detecting FVG zones: {e}")
        return "Smart Money: Error detecting zones this cycle."
