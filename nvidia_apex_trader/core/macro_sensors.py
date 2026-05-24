import logging
import MetaTrader5 as mt5
import numpy as np
from numba import njit

logger = logging.getLogger("Macro_Sensors")
logger.setLevel(logging.INFO)

# =============================================================================
# INSTITUTIONAL SMART MONEY CONCEPTS (SMC) DETECTION
# =============================================================================

def detect_fair_value_gaps(candles: list, current_price: float = 0.0, max_lookback: int = 100) -> dict:
    """
    Detects Fair Value Gaps (FVGs) â€” 3-candle imbalance patterns used by institutional traders.

    Bullish FVG: Candle 1 High < Candle 3 Low  (price left a vacuum below, expecting return)
    Bearish FVG: Candle 1 Low > Candle 3 High  (price left a vacuum above, expecting return)

    A gap is considered UNFILLED if price has NOT retraced into the gap zone since formation.
    Only the most recent unfilled gaps are returned (nearest to current price).

    Args:
        candles: List of candle dicts [{open, high, low, close}, ...] oldest first.
        current_price: Current market price for proximity sorting.
        max_lookback: Max candles to scan (default 100 for speed).

    Returns:
        {"bullish": [...], "bearish": [...], "nearest_bullish": {}, "nearest_bearish": {}}
    """
    if not candles or len(candles) < 4:
        return {"bullish": [], "bearish": [], "nearest_bullish": None, "nearest_bearish": None}

    lookback = min(max_lookback, len(candles))
    recent = candles[-lookback:]
    bullish_fvgs = []
    bearish_fvgs = []

    for i in range(len(recent) - 3):
        c1 = recent[i]
        c2 = recent[i + 1]
        c3 = recent[i + 2]

        # Bullish FVG: c1.high < c3.low
        c1_high = float(c1.get("high", c1.get("high", 0)))
        c3_low = float(c3.get("low", c3.get("low", 0)))
        c1_low = float(c1.get("low", c1.get("low", 0)))
        c3_high = float(c3.get("high", c3.get("high", 0)))

        # Bullish FVG detection
        if c1_high < c3_low:
            gap_top = c3_low
            gap_bottom = c1_high
            # Check if unfilled: no candle after i+2 has retraced into [gap_bottom, gap_top]
            filled = False
            for j in range(i + 3, len(recent)):
                cj_low = float(recent[j].get("low", recent[j].get("low", 0)))
                cj_high = float(recent[j].get("high", recent[j].get("high", 0)))
                if cj_low <= gap_top and cj_high >= gap_bottom:
                    filled = True
                    break
            if not filled:
                bullish_fvgs.append({
                    "type": "bullish",
                    "gap_top": round(gap_top, 5),
                    "gap_bottom": round(gap_bottom, 5),
                    "index": i,
                    "mid": round((gap_top + gap_bottom) / 2, 5)
                })

        # Bearish FVG detection
        if c1_low > c3_high:
            gap_top = c1_low
            gap_bottom = c3_high
            filled = False
            for j in range(i + 3, len(recent)):
                cj_low = float(recent[j].get("low", recent[j].get("low", 0)))
                cj_high = float(recent[j].get("high", recent[j].get("high", 0)))
                if cj_low <= gap_top and cj_high >= gap_bottom:
                    filled = True
                    break
            if not filled:
                bearish_fvgs.append({
                    "type": "bearish",
                    "gap_top": round(gap_top, 5),
                    "gap_bottom": round(gap_bottom, 5),
                    "index": i,
                    "mid": round((gap_top + gap_bottom) / 2, 5)
                })

    # Keep only the 5 most recent unfilled gaps per type
    bullish_fvgs = bullish_fvgs[-5:]
    bearish_fvgs = bearish_fvgs[-5:]

    # Sort by proximity to current price if provided
    nearest_bullish = None
    nearest_bearish = None
    if current_price > 0:
        if bullish_fvgs:
            nearest_bullish = min(bullish_fvgs, key=lambda g: abs(g["mid"] - current_price))
        if bearish_fvgs:
            nearest_bearish = min(bearish_fvgs, key=lambda g: abs(g["mid"] - current_price))
    else:
        if bullish_fvgs:
            nearest_bullish = bullish_fvgs[-1]
        if bearish_fvgs:
            nearest_bearish = bearish_fvgs[-1]

    return {
        "bullish": bullish_fvgs,
        "bearish": bearish_fvgs,
        "nearest_bullish": nearest_bullish,
        "nearest_bearish": nearest_bearish
    }


def detect_order_blocks(candles: list, current_price: float = 0.0, max_lookback: int = 100) -> dict:
    """
    Detects Order Blocks (OBs) â€” institutional supply/demand zones.

    Bullish OB: The last bearish candle (close < open) immediately before a strong
                impulsive bullish move that breaks structure (creates a new local high).
    Bearish OB: The last bullish candle (close > open) immediately before a strong
                impulsive bearish move that breaks structure (creates a new local low).

    Structure break is defined as: move >= 1.5x ATR20 from the OB candle's close,
    breaking the previous swing high/low.

    Args:
        candles: List of candle dicts [{open, high, low, close}, ...] oldest first.
        current_price: Current market price for proximity sorting.
        max_lookback: Max candles to scan (default 100 for speed).

    Returns:
        {"bullish": [...], "bearish": [...], "nearest_bullish": {}, "nearest_bearish": {}}
    """
    if not candles or len(candles) < 20:
        return {"bullish": [], "bearish": [], "nearest_bullish": None, "nearest_bearish": None}

    lookback = min(max_lookback, len(candles))
    recent = candles[-lookback:]
    n = len(recent)

    # Compute ATR20 for momentum threshold
    atr = 0.0
    trs = []
    for i in range(max(1, n - 20), n):
        prev_close = float(recent[i - 1].get("close", recent[i - 1].get("close", 0)))
        high = float(recent[i].get("high", recent[i].get("high", 0)))
        low = float(recent[i].get("low", recent[i].get("low", 0)))
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    atr = sum(trs) / len(trs) if trs else 0.0001

    # Find swing highs/lows (local extrema with 3-candle window)
    def is_swing_high(i):
        if i < 2 or i >= n - 2:
            return False
        h = float(recent[i].get("high", 0))
        return h > float(recent[i - 1].get("high", 0)) and h > float(recent[i - 2].get("high", 0)) and \
               h > float(recent[i + 1].get("high", 0)) and h > float(recent[i + 2].get("high", 0))

    def is_swing_low(i):
        if i < 2 or i >= n - 2:
            return False
        l = float(recent[i].get("low", 0))
        return l < float(recent[i - 1].get("low", 0)) and l < float(recent[i - 2].get("low", 0)) and \
               l < float(recent[i + 1].get("low", 0)) and l < float(recent[i + 2].get("low", 0))

    swing_highs = [(i, float(recent[i].get("high", 0))) for i in range(2, n - 2) if is_swing_high(i)]
    swing_lows = [(i, float(recent[i].get("low", 0))) for i in range(2, n - 2) if is_swing_low(i)]

    bullish_obs = []
    bearish_obs = []

    # Detect Bullish Order Blocks
    for i in range(2, n - 5):
        c = recent[i]
        o = float(c.get("open", c.get("open", 0)))
        close_p = float(c.get("close", c.get("close", 0)))
        # Must be a bearish candle
        if close_p >= o:
            continue
        # Look for structure break after this candle
        for sh_idx, sh_val in swing_highs:
            if sh_idx <= i:
                continue
            # The move from candle close to swing high must be impulsive (>= 1.5x ATR)
            move = sh_val - close_p
            if move >= 1.5 * atr:
                # Verify this is the last bearish candle before the impulse
                all_bullish = True
                for k in range(i + 1, sh_idx):
                    ck = recent[k]
                    if float(ck.get("close", ck.get("close", 0))) < float(ck.get("open", ck.get("open", 0))):
                        all_bullish = False
                        break
                if all_bullish:
                    bullish_obs.append({
                        "type": "bullish",
                        "high": round(float(c.get("high", c.get("high", 0))), 5),
                        "low": round(float(c.get("low", c.get("low", 0))), 5),
                        "open": round(o, 5),
                        "close": round(close_p, 5),
                        "index": i,
                        "swing_index": sh_idx
                    })
                    break

    # Detect Bearish Order Blocks
    for i in range(2, n - 5):
        c = recent[i]
        o = float(c.get("open", c.get("open", 0)))
        close_p = float(c.get("close", c.get("close", 0)))
        # Must be a bullish candle
        if close_p <= o:
            continue
        for sl_idx, sl_val in swing_lows:
            if sl_idx <= i:
                continue
            move = close_p - sl_val
            if move >= 1.5 * atr:
                all_bearish = True
                for k in range(i + 1, sl_idx):
                    ck = recent[k]
                    if float(ck.get("close", ck.get("close", 0))) > float(ck.get("open", ck.get("open", 0))):
                        all_bearish = False
                        break
                if all_bearish:
                    bearish_obs.append({
                        "type": "bearish",
                        "high": round(float(c.get("high", c.get("high", 0))), 5),
                        "low": round(float(c.get("low", c.get("low", 0))), 5),
                        "open": round(o, 5),
                        "close": round(close_p, 5),
                        "index": i,
                        "swing_index": sl_idx
                    })
                    break

    # Deduplicate by index and keep most recent 3 per type
    seen_bull = set()
    dedup_bull = []
    for ob in reversed(bullish_obs):
        if ob["index"] not in seen_bull:
            seen_bull.add(ob["index"])
            dedup_bull.append(ob)
    bullish_obs = list(reversed(dedup_bull[-3:]))

    seen_bear = set()
    dedup_bear = []
    for ob in reversed(bearish_obs):
        if ob["index"] not in seen_bear:
            seen_bear.add(ob["index"])
            dedup_bear.append(ob)
    bearish_obs = list(reversed(dedup_bear[-3:]))

    # Find nearest to current price
    nearest_bullish = None
    nearest_bearish = None
    if current_price > 0:
        if bullish_obs:
            nearest_bullish = min(bullish_obs, key=lambda g: abs((g["high"] + g["low"]) / 2 - current_price))
        if bearish_obs:
            nearest_bearish = min(bearish_obs, key=lambda g: abs((g["high"] + g["low"]) / 2 - current_price))
    else:
        if bullish_obs:
            nearest_bullish = bullish_obs[-1]
        if bearish_obs:
            nearest_bearish = bearish_obs[-1]

    return {
        "bullish": bullish_obs,
        "bearish": bearish_obs,
        "nearest_bullish": nearest_bullish,
        "nearest_bearish": nearest_bearish
    }

async def calculate_currency_matrix() -> dict:
    """
    Fetches 4H and 1H price changes for major pairs to calculate a relative strength score (0-100)
    for the base currencies (USD, EUR, GBP, JPY, XAU). Returns Strongest and Weakest.
    
    Broker-agnostic: dynamically resolves symbol suffixes (.x, #, .i#, bare) for
    each pair so it works across XMGlobal, GoatFunded, and other prop firm accounts.
    """
    from core.mt5_engine import _resolve_tradeable_symbol

    # --- Resolve forex pairs via the existing broker-agnostic resolver ---
    base_forex = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
    resolved_symbols = []
    for base in base_forex:
        resolved = _resolve_tradeable_symbol(base)
        info = mt5.symbol_info(resolved)
        if info is not None:
            if not info.visible:
                mt5.symbol_select(resolved, True)
            resolved_symbols.append(resolved)
        else:
            logger.warning(f"[MATRIX] Could not resolve forex pair: {base} (tried {resolved})")

    # --- Resolve Gold via alias probing (broker naming varies wildly) ---
    gold_aliases = ["XAUUSD", "XAUUSD.x", "GOLD", "GOLD.x", "GOLD.i#", "GOLD#", "XAUUSD#", "XAUUSD.i#"]
    gold_symbol = None
    for alias in gold_aliases:
        info = mt5.symbol_info(alias)
        if info is not None:
            if not info.visible:
                mt5.symbol_select(alias, True)
            gold_symbol = alias
            break
    if gold_symbol:
        resolved_symbols.append(gold_symbol)
    else:
        # Last resort: try the generic resolver
        fallback = _resolve_tradeable_symbol("XAUUSD")
        if mt5.symbol_info(fallback) is not None:
            resolved_symbols.append(fallback)
            gold_symbol = fallback
        else:
            logger.warning("[MATRIX] Could not resolve any Gold symbol for currency matrix")

    logger.info(f"[MATRIX] Resolved symbols: {resolved_symbols}")
    matrix = {}
    
    for sym in resolved_symbols:
        # Fetch last 2 candles for 4H and 1H
        rates_h4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 2)
        rates_h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 2)
        
        change_h4 = 0.0
        change_h1 = 0.0
        
        if rates_h4 is not None and len(rates_h4) == 2:
            change_h4 = ((rates_h4[1]['close'] - rates_h4[0]['close']) / rates_h4[0]['close']) * 100
            
        if rates_h1 is not None and len(rates_h1) == 2:
            change_h1 = ((rates_h1[1]['close'] - rates_h1[0]['close']) / rates_h1[0]['close']) * 100
            
        matrix[sym] = {"H4": change_h4, "H1": change_h1}
        
    # Calculate simple Relative Strength Base Scores (0 starting, adjust based on pair changes)
    scores = {"USD": 50, "EUR": 50, "GBP": 50, "JPY": 50, "XAU": 50, "AUD": 50}
    
    # Simple scoring logic: if EURUSD is up, EUR gets stronger, USD gets weaker.
    # We weight H4 more heavily than H1
    for sym, changes in matrix.items():
        total_change = (changes["H4"] * 0.7) + (changes["H1"] * 0.3)
        # Strip broker suffixes to extract clean base/quote currencies
        clean = sym.upper().replace(".X", "").replace(".I#", "").replace("#", "").replace(".I", "").replace(".PRO", "").replace(".C", "")
        # Gold/XAU detection (broker names: GOLD, XAUUSD, GOLD.x, XAUUSD.i#, etc.)
        if clean.startswith("GOLD") or clean.startswith("XAU"):
            base, quote = "XAU", "USD"
        else:
            base = clean[:3]
            quote = clean[3:6]  # Limit to 3 chars to avoid residual suffix chars
        
        if quote == "USD":
            # Direct pair (EURUSD, GBPUSD, AUDUSD, GOLD)
            if total_change > 0:
                scores[base] += abs(total_change) * 10
                scores["USD"] -= abs(total_change) * 10
            else:
                scores[base] -= abs(total_change) * 10
                scores["USD"] += abs(total_change) * 10
        elif base == "USD":
            # Indirect pair (USDJPY)
            if total_change > 0:
                scores["USD"] += abs(total_change) * 10
                scores[quote] -= abs(total_change) * 10
            else:
                scores["USD"] -= abs(total_change) * 10
                scores[quote] += abs(total_change) * 10

    # Normalize scores between 0 and 100
    min_score = min(scores.values())
    max_score = max(scores.values())
    
    if max_score > min_score:
        for k in scores:
            scores[k] = ((scores[k] - min_score) / (max_score - min_score)) * 100
    else:
        for k in scores:
            scores[k] = 50.0

    scores = {k: round(v, 2) for k, v in scores.items()}
    
    strongest = max(scores, key=scores.get)
    weakest = min(scores, key=scores.get)
    
    return {
        "strongest": strongest,
        "weakest": weakest,
        "scores": scores,
        "matrix": matrix
    }

async def detect_tick_velocity(symbol: str) -> dict:
    """
    Fetches MT5 tick volume for the last 6 one-minute candles (5 closed + 1 open).
    Detects if current tick volume is > 200% of the moving average.
    """
    try:
        info = mt5.symbol_info(symbol)
        if info is None:
            return {"is_high_velocity": False, "ratio": 0.0, "current_vol": 0, "ma_vol": 0}
        if not info.visible:
            mt5.symbol_select(symbol, True)

        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 6)
    except Exception:
        return {"is_high_velocity": False, "ratio": 0.0, "current_vol": 0, "ma_vol": 0}
    
    if rates is None or len(rates) < 6:
        return {"is_high_velocity": False, "ratio": 0.0, "current_vol": 0, "ma_vol": 0}
        
    # Last 5 closed candles for moving average
    closed_candles = rates[:5]
    ma_vol = sum(r['tick_volume'] for r in closed_candles) / 5.0
    
    # Current open candle
    curr_vol = rates[5]['tick_volume']
    
    ratio = float(curr_vol / ma_vol) if ma_vol > 0 else 0.0
    is_high_velocity = bool(ratio > 2.0)
    
    return {
        "is_high_velocity": is_high_velocity,
        "ratio": round(ratio, 2),
        "current_vol": int(curr_vol),
        "ma_vol": round(float(ma_vol), 2)
    }

def get_smc_killzone() -> tuple:
    """
    Full London + New York trading-session gate using New York time.

    Active window:
      - 2:00 AM to 5:00 PM NY Time, continuous.

    This keeps the engine awake through full London, London/New York overlap,
    NY lunch, and full New York instead of only narrow killzone slices.
    """
    import pytz
    from datetime import datetime

    ny_tz = pytz.timezone('America/New_York')
    ny_time = datetime.now(pytz.utc).astimezone(ny_tz)
    current_time_float = ny_time.hour + (ny_time.minute / 60.0)

    # 05:27 NY is tradable: London continuation remains active until 08:00 NY.
    if 2.0 <= current_time_float < 8.0:
        return True, "London Session"
    if 8.0 <= current_time_float < 12.0:
        return True, "London/NY Overlap"
    if 12.0 <= current_time_float < 17.0:
        return True, "New York Session"

    return False, "Outside London/New York Session"


def is_killzone_active() -> bool:
    """
    Convenience wrapper for the Gatekeeper.
    Returns True ONLY if a valid SMC Killzone is active.
    Called before every new entry attempt. Trailing/management of open trades is always allowed.
    """
    is_active, _ = get_smc_killzone()
    return is_active

def detect_asian_range(candles: list, current_price: float) -> str:
    """
    Detects the Asian Range (00:00 to 06:00 broker time) for the most recent day in the provided candles.
    Checks if the current price is sweeping the high or low of this range.
    Returns a string describing the AMD pattern context.
    """
    from datetime import datetime
    
    if not candles or len(candles) < 6:
        return "Range Unknown - Insufficient Data"
        
    # Get the latest day from the last candle
    last_time = candles[-1].get("time_str", "")
    if not last_time:
        ts = candles[-1].get("time", 0)
        if ts > 0:
            last_time = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        else:
            return "Range Unknown - Invalid Time Data"
            
    try:
        last_dt = datetime.strptime(last_time, "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            last_dt = datetime.fromisoformat(last_time)
        except ValueError:
            return "Range Unknown - Invalid Time Format"
            
    target_date = last_dt.date()
    
    asian_high = -float('inf')
    asian_low = float('inf')
    found_candles = 0
    
    for c in candles:
        t_str = c.get("time_str", "")
        if not t_str:
            ts = c.get("time", 0)
            if ts > 0:
                t_str = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            else:
                continue
                
        try:
            dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M")
        except ValueError:
            try:
                dt = datetime.fromisoformat(t_str)
            except ValueError:
                continue
                
        if dt.date() == target_date and 0 <= dt.hour < 6:
            high = float(c.get("high", 0))
            low = float(c.get("low", 0))
            if high > asian_high: asian_high = high
            if low < asian_low: asian_low = low
            found_candles += 1
            
    if found_candles == 0:
        return "Range Unknown - No 00:00-06:00 candles found for current day"
        
    if current_price > asian_high:
        return f"PRICE IS SWEEPING ASIAN HIGHS ({asian_high}) - ANTICIPATE BEARISH REVERSAL (Distribution Phase)"
    elif current_price < asian_low:
        return f"PRICE IS SWEEPING ASIAN LOWS ({asian_low}) - ANTICIPATE BULLISH REVERSAL (Distribution Phase)"
    else:
        return f"Inside Asian Range / Standard PA (High: {asian_high}, Low: {asian_low})"


# =============================================================================
# HTF TREND BIAS GATE â€” H1 EMA20 vs EMA50 (mandatory pre-entry filter)
# =============================================================================

def get_h1_trend_bias(symbol: str) -> dict:
    """
    Fetches H1 EMA20 and EMA50 from MT5 to determine mandatory trade direction.
    This is a HARD GATE â€” not a weighted suggestion.
    
    Returns:
        {"bias": "BUY"|"SELL"|"SKIP", "ema20": float, "ema50": float, "gap_pct": float}
    """
    try:
        info = mt5.symbol_info(symbol)
        if info is None:
            return {"bias": "SKIP", "ema20": 0, "ema50": 0, "gap_pct": 0, "reason": "Symbol not found"}
        if not info.visible:
            mt5.symbol_select(symbol, True)
        
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 55)
        if rates is None or len(rates) < 50:
            return {"bias": "SKIP", "ema20": 0, "ema50": 0, "gap_pct": 0, "reason": "Insufficient H1 data"}
        
        closes = [float(r['close']) for r in rates]
        
        def calc_ema(data, period):
            if len(data) < period:
                return sum(data) / len(data)
            multiplier = 2 / (period + 1)
            ema = sum(data[:period]) / period
            for price in data[period:]:
                ema = (price - ema) * multiplier + ema
            return ema
        
        ema20 = calc_ema(closes, 20)
        ema50 = calc_ema(closes, 50)
        
        mid_price = (ema20 + ema50) / 2 if (ema20 + ema50) > 0 else 1
        gap_pct = abs(ema20 - ema50) / mid_price * 100
        
        if gap_pct < 0.005:
            bias = "SKIP"
            reason = f"H1 EMAs ranging (gap: {gap_pct:.4f}%)"
        elif ema20 > ema50:
            bias = "BUY"
            reason = f"H1 EMA20 ({ema20:.5f}) > EMA50 ({ema50:.5f})"
        else:
            bias = "SELL"
            reason = f"H1 EMA20 ({ema20:.5f}) < EMA50 ({ema50:.5f})"
        
        print(f"[HTF-GATE] {symbol}: {bias} | EMA20={ema20:.5f} EMA50={ema50:.5f} Gap={gap_pct:.4f}% | {reason}")
        return {"bias": bias, "ema20": round(ema20, 5), "ema50": round(ema50, 5), "gap_pct": round(gap_pct, 4), "reason": reason}
    
    except Exception as e:
        print(f"[HTF-GATE] Error fetching H1 bias for {symbol}: {e}")
        return {"bias": "SKIP", "ema20": 0, "ema50": 0, "gap_pct": 0, "reason": f"Error: {e}"}



def get_early_trend_continuation(symbol: str, direction: str) -> dict:
    """Detect the green-circle entry: pullback/retest then first continuation candle.

    This intentionally rejects late momentum after several same-direction M15
    candles. It is used before live execution so the bot enters near the start of
    the leg instead of buying/selling the exhausted candle.
    """
    try:
        info = mt5.symbol_info(symbol)
        if info is None:
            return {"pass": False, "reason": "Symbol not found"}
        if not info.visible:
            mt5.symbol_select(symbol, True)

        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 9)
        if rates is None or len(rates) < 7:
            return {"pass": False, "reason": "Insufficient M15 data"}

        current_price = float(info.ask if direction.upper() in ("BUY", "LONG") else info.bid)
        is_buy = direction.upper() in ("BUY", "LONG")
        closed = list(rates[:-1])  # keep existing convention: final bar is forming
        last = closed[-1]
        prior = closed[-6:-1]
        recent_pullback = closed[-4:-1]

        def o(c): return float(c['open'])
        def h(c): return float(c['high'])
        def l(c): return float(c['low'])
        def c(candle): return float(candle['close'])
        def body(candle): return abs(c(candle) - o(candle))
        def rng(candle): return max(h(candle) - l(candle), 0.0)

        atr = sum(rng(x) for x in closed[-7:]) / max(1, len(closed[-7:]))
        if atr <= 0:
            return {"pass": False, "reason": "M15 ATR unavailable"}

        if is_buy:
            continuation = c(last) > o(last) and c(last) >= c(closed[-2])
            pullback_seen = any(c(x) < o(x) for x in recent_pullback)
            retest_low = min(l(x) for x in recent_pullback)
            leg_extension = current_price - retest_low
            consecutive = 0
            for bar in reversed(closed[-5:]):
                if c(bar) > o(bar):
                    consecutive += 1
                else:
                    break
            broke_retest = c(last) > max(o(closed[-2]), c(closed[-2])) or h(last) > h(closed[-2])
        else:
            continuation = c(last) < o(last) and c(last) <= c(closed[-2])
            pullback_seen = any(c(x) > o(x) for x in recent_pullback)
            retest_high = max(h(x) for x in recent_pullback)
            leg_extension = retest_high - current_price
            consecutive = 0
            for bar in reversed(closed[-5:]):
                if c(bar) < o(bar):
                    consecutive += 1
                else:
                    break
            broke_retest = c(last) < min(o(closed[-2]), c(closed[-2])) or l(last) < l(closed[-2])

        if not continuation:
            return {"pass": False, "reason": "No first continuation M15 candle yet"}
        if not pullback_seen:
            return {"pass": False, "reason": "No pullback/retest before continuation"}
        if not broke_retest:
            return {"pass": False, "reason": "Continuation has not broken the pullback candle yet"}
        if consecutive > 2:
            return {"pass": False, "reason": f"Late chase: {consecutive} M15 candles already in same direction"}
        if leg_extension > atr * 2.2:
            return {"pass": False, "reason": f"Late chase: current leg is {leg_extension/atr:.1f} ATR from pullback"}
        if body(last) > atr * 1.6:
            return {"pass": False, "reason": "Last M15 candle is an expansion candle; wait for next pullback"}

        side = "BUY" if is_buy else "SELL"
        return {"pass": True, "reason": f"{side} pullback continuation: first/second M15 resume candle after retest, extension {leg_extension/atr:.1f} ATR"}

    except Exception as e:
        return {"pass": False, "reason": f"Early continuation check error: {e}"}
# =============================================================================
# MOMENTUM CONFIRMATION â€” M15 candle direction check (pre-entry filter)
# =============================================================================

def is_momentum_confirmed(symbol: str, direction: str) -> bool:
    """
    Checks last 2 closed M15 candles to confirm directional momentum.
    For BUY: last closed M15 must be green. For SELL: must be red.
    Also checks price is not >50% inside previous candle body (mid-candle).
    """
    try:
        info = mt5.symbol_info(symbol)
        if info is None:
            return False
        if not info.visible:
            mt5.symbol_select(symbol, True)
        
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 3)
        if rates is None or len(rates) < 3:
            print(f"[MOMENTUM] {symbol}: Insufficient M15 data, blocking entry")
            return False
        
        last_closed = rates[-2]
        prev_closed = rates[-3]
        
        last_open = float(last_closed['open'])
        last_close = float(last_closed['close'])
        
        prev_open = float(prev_closed['open'])
        prev_close = float(prev_closed['close'])
        prev_body_top = max(prev_open, prev_close)
        prev_body_bot = min(prev_open, prev_close)
        prev_body_size = prev_body_top - prev_body_bot
        
        current_price = float(info.ask if direction.upper() in ("BUY", "LONG") else info.bid)
        is_buy = direction.upper() in ("BUY", "LONG")
        
        if is_buy:
            candle_confirms = last_close > last_open
        else:
            candle_confirms = last_close < last_open
        
        if not candle_confirms:
            print(f"[MOMENTUM] {symbol}: Last M15 candle does NOT confirm {direction.upper()} â€” BLOCKED")
            return False
        
        if prev_body_size > 0 and prev_body_bot < current_price < prev_body_top:
            depth = min(current_price - prev_body_bot, prev_body_top - current_price)
            penetration = depth / prev_body_size
            if penetration > 0.5:
                print(f"[MOMENTUM] {symbol}: Price mid-candle ({penetration:.0%} into prev body) â€” BLOCKED")
                return False
        
        print(f"[MOMENTUM] {symbol}: {direction.upper()} confirmed by M15 structure âœ“")
        return True
    
    except Exception as e:
        print(f"[MOMENTUM] Error checking {symbol}: {e}")
        return False


# =============================================================================
# ORDER FLOW IMBALANCE (OFI) SENSOR — Institutional HFT Footprint Detector
# =============================================================================
# Hybrid approach:
#   1. Primary: MT5 Depth of Market (DOM) — works on exchange-traded instruments
#   2. Fallback: Tick-Volume-Weighted Price Delta — works on ALL brokers (Forex/CFD)
#
# The fallback computes OFI from M1 candle tick-volume and price direction:
#   - Aggressive buying = price rising on high volume → positive OFI
#   - Institutional distribution = price falling on high volume → negative OFI
# =============================================================================

_prev_dom_state = {}  # Global memory cache for DOM-based OFI delta tracking
_prev_tvd_state = {}  # Global memory cache for tick-volume-delta OFI


def _try_dom_ofi(symbol: str) -> tuple[bool, float]:
    """Attempt DOM-based OFI. Returns (success, ofi_value).
    Returns (False, 0.0) if DOM is not available for this broker/symbol."""
    global _prev_dom_state

    if not mt5.market_book_add(symbol):
        return False, 0.0

    book = mt5.market_book_get(symbol)
    if not book:
        mt5.market_book_release(symbol)
        return False, 0.0

    # Isolate bids and asks from current snapshot
    bids = [level for level in book if level.type == mt5.BOOK_TYPE_BUY]
    asks = [level for level in book if level.type == mt5.BOOK_TYPE_SELL]

    if not bids or not asks:
        mt5.market_book_release(symbol)
        return False, 0.0

    # Extract true best bid/ask
    best_bid = max(bids, key=lambda x: x.price)
    best_ask = min(asks, key=lambda x: x.price)

    curr_bid_p, curr_bid_v = best_bid.price, best_bid.volume
    curr_ask_p, curr_ask_v = best_ask.price, best_ask.volume

    if symbol not in _prev_dom_state:
        _prev_dom_state[symbol] = {
            "bid_p": curr_bid_p, "bid_v": curr_bid_v,
            "ask_p": curr_ask_p, "ask_v": curr_ask_v
        }
        return True, 0.0  # First scan — initialized, real data next cycle

    prev = _prev_dom_state[symbol]

    # Calculate Institutional Delta Bid Accumulation
    if curr_bid_p > prev["bid_p"]:
        delta_bid_vol = curr_bid_v
    elif curr_bid_p == prev["bid_p"]:
        delta_bid_vol = curr_bid_v - prev["bid_v"]
    else:
        delta_bid_vol = 0

    # Calculate Institutional Delta Ask Accumulation
    if curr_ask_p < prev["ask_p"]:
        delta_ask_vol = curr_ask_v
    elif curr_ask_p == prev["ask_p"]:
        delta_ask_vol = curr_ask_v - prev["ask_v"]
    else:
        delta_ask_vol = 0

    _prev_dom_state[symbol] = {
        "bid_p": curr_bid_p, "bid_v": curr_bid_v,
        "ask_p": curr_ask_p, "ask_v": curr_ask_v
    }

    return True, float(delta_bid_vol - delta_ask_vol)


@njit(fastmath=True)
def _compute_tvd_ofi_njit(closes, opens, tick_vols):
    # Calculate signed flow
    signed_flows = (closes - opens) * tick_vols
    
    # Split: recent 3 candles vs baseline 7 candles
    baseline = signed_flows[:7]
    recent = signed_flows[7:]
    
    # Mathematical logic
    baseline_mean = np.mean(baseline) if len(baseline) > 0 else 0.0
    recent_sum = np.sum(recent)
    
    ofi = recent_sum - (baseline_mean * len(recent))
    
    baseline_magnitude = np.mean(np.abs(baseline)) if len(baseline) > 0 else 1.0
    if baseline_magnitude > 0:
        normalized_ofi = ofi / baseline_magnitude * 100.0
    else:
        normalized_ofi = 0.0
        
    return normalized_ofi

def _tick_volume_delta_ofi(symbol: str) -> float:
    """Tick-Volume-Weighted Price Delta OFI — works on ALL MT5 brokers.

    Algorithm:
    - Fetch the last 10 closed M1 candles + 1 forming candle
    - For each closed candle, compute signed_flow = (close - open) * tick_volume
      Positive = buyers dominated that minute, Negative = sellers dominated
    - Recent candles (last 3) are the "live" window; older 7 are the "baseline"
    - OFI = sum(recent_signed_flow) - mean(baseline_signed_flow) * 3
      This isolates sudden institutional surges from normal background noise.
    """
    global _prev_tvd_state

    try:
        info = mt5.symbol_info(symbol)
        if info is None:
            return 0.0
        if not info.visible:
            mt5.symbol_select(symbol, True)

        # 11 bars = 10 closed + 1 forming
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 11)
        if rates is None or len(rates) < 11:
            return 0.0

        # Use only the 10 closed candles (index 0-9), skip the forming bar (index 10)
        closed = rates[:10]

        # Extract to NumPy arrays for Numba compilation
        closes = np.array([r['close'] for r in closed], dtype=np.float64)
        opens = np.array([r['open'] for r in closed], dtype=np.float64)
        tick_vols = np.array([r['tick_volume'] for r in closed], dtype=np.float64)

        # Execute C-compiled logic
        normalized_ofi = _compute_tvd_ofi_njit(closes, opens, tick_vols)

        return round(normalized_ofi, 1)

    except Exception as e:
        print(f"[OFI-TVD] Error computing tick-volume OFI for {symbol}: {e}")
        return 0.0


def calculate_order_flow_imbalance(symbol: str) -> float:
    """
    Computes instantaneous Order Flow Imbalance (OFI).

    Primary: MT5 Depth of Market (DOM) for exchange-traded instruments.
    Fallback: Tick-Volume-Weighted Price Delta for Forex/CFD brokers.

    Positive value = Aggressive institutional buying pressure.
    Negative value = Toxic order flow / Institutional distribution.
    """
    # Try DOM-based OFI first (only works on exchange instruments)
    dom_available, dom_ofi = _try_dom_ofi(symbol)

    if dom_available:
        print(f"[OFI] {symbol}: DOM-based OFI={dom_ofi:+.0f} (L2 Order Book)")
        return dom_ofi

    # Fallback: Tick-volume-weighted price delta (works on ALL brokers)
    tvd_ofi = _tick_volume_delta_ofi(symbol)
    return tvd_ofi


# =============================================================================
# VPIN SENSOR — Volume-Synchronized Probability of Informed Trading
# =============================================================================
# Detects when informed institutional traders are aggressively absorbing
# liquidity using Bulk Volume Classification (BVC) over volume-synchronized
# buckets. High VPIN = toxic informed flow = potential adverse selection.
#
# Algorithm:
#   1. Fetch N M1 candles with tick volume
#   2. BVC: classify each candle's volume as buy/sell based on price position
#      buy_vol = tick_volume × (close - low) / (high - low)
#      sell_vol = tick_volume - buy_vol
#   3. Accumulate into fixed-size volume buckets (not time-based)
#   4. VPIN = mean(|buy_vol - sell_vol| / bucket_size) across last K buckets
#   5. Range: 0.0 (balanced) to 1.0 (fully one-sided / toxic)
# =============================================================================

@njit(fastmath=True)
def _compute_vpin_njit(highs, lows, closes, tick_vols, num_buckets):
    n = len(highs)
    buy_vols = np.zeros(n)
    sell_vols = np.zeros(n)
    total_volume = 0.0
    
    # Step 1: Bulk Volume Classification
    for i in range(n):
        tv = tick_vols[i]
        if tv <= 0:
            continue
        rng = highs[i] - lows[i]
        if rng > 0:
            bf = (closes[i] - lows[i]) / rng
        else:
            bf = 0.5
        buy_vols[i] = tv * bf
        sell_vols[i] = tv * (1.0 - bf)
        total_volume += tv
        
    if total_volume <= 0:
        return 0.0, 0, 0.0, 0.0
        
    target_bucket_size = total_volume / max(num_buckets, 1)
    if target_bucket_size <= 0:
        return 0.0, 0, 0.0, 0.0
        
    # Step 2: Volume-Synchronized Buckets
    bucket_buy = 0.0
    bucket_sell = 0.0
    bucket_vol = 0.0
    
    # Arrays to store bucket results (oversized for safety)
    max_b = num_buckets + 10
    buckets_buy = np.zeros(max_b)
    buckets_sell = np.zeros(max_b)
    buckets_imbalance = np.zeros(max_b)
    b_idx = 0
    
    for i in range(n):
        rem_buy = buy_vols[i]
        rem_sell = sell_vols[i]
        rem_tot = buy_vols[i] + sell_vols[i]
        
        while rem_tot > 0:
            space = target_bucket_size - bucket_vol
            if rem_tot <= space:
                bucket_buy += rem_buy
                bucket_sell += rem_sell
                bucket_vol += rem_tot
                rem_tot = 0.0
            else:
                frac = space / rem_tot if rem_tot > 0 else 0.0
                bucket_buy += rem_buy * frac
                bucket_sell += rem_sell * frac
                bucket_vol += space
                rem_buy *= (1.0 - frac)
                rem_sell *= (1.0 - frac)
                rem_tot -= space
                
            if bucket_vol >= target_bucket_size * 0.999:
                if b_idx < max_b:
                    buckets_buy[b_idx] = bucket_buy
                    buckets_sell[b_idx] = bucket_sell
                    buckets_imbalance[b_idx] = abs(bucket_buy - bucket_sell) / bucket_vol if bucket_vol > 0 else 0.0
                    b_idx += 1
                bucket_buy = 0.0
                bucket_sell = 0.0
                bucket_vol = 0.0
                
    if b_idx == 0:
        return 0.0, 0, 0.0, 0.0
        
    # Step 3: VPIN Calculation (mean absolute imbalance across buckets)
    start_idx = max(0, b_idx - num_buckets)
    valid_buckets = b_idx - start_idx
    
    imbalance_sum = 0.0
    recent_buy_sum = 0.0
    recent_sell_sum = 0.0
    
    for i in range(start_idx, b_idx):
        imbalance_sum += buckets_imbalance[i]
        recent_buy_sum += buckets_buy[i]
        recent_sell_sum += buckets_sell[i]
        
    vpin = imbalance_sum / valid_buckets
    return min(1.0, max(0.0, vpin)), valid_buckets, recent_buy_sum, recent_sell_sum

def calculate_vpin(symbol: str, num_candles: int = 50, num_buckets: int = 10) -> dict:
    """
    Computes VPIN (Volume-Synchronized Probability of Informed Trading).

    Uses Bulk Volume Classification (BVC) on M1 candles to detect when
    institutional informed traders are aggressively absorbing liquidity.
    Now C-Compiled with Numba for microsecond execution.
    """
    _default = {"vpin": 0.0, "is_toxic": False, "dominant_side": "BALANCED", "bucket_count": 0}

    try:
        info = mt5.symbol_info(symbol)
        if info is None:
            return _default
        if not info.visible:
            mt5.symbol_select(symbol, True)

        # Fetch M1 candles
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, num_candles + 1)
        if rates is None or len(rates) < num_candles + 1:
            return _default

        # Use only closed candles
        closed = rates[:num_candles]

        # Extract to NumPy arrays for Numba compilation
        highs = np.array([r['high'] for r in closed], dtype=np.float64)
        lows = np.array([r['low'] for r in closed], dtype=np.float64)
        closes = np.array([r['close'] for r in closed], dtype=np.float64)
        tick_vols = np.array([r['tick_volume'] for r in closed], dtype=np.float64)

        # Execute C-compiled VPIN logic
        vpin_val, valid_buckets, total_recent_buy, total_recent_sell = _compute_vpin_njit(
            highs, lows, closes, tick_vols, num_buckets
        )

        if valid_buckets == 0:
            return _default

        vpin = round(float(vpin_val), 3)

        if total_recent_buy > total_recent_sell * 1.15:
            dominant = "BUY"
        elif total_recent_sell > total_recent_buy * 1.15:
            dominant = "SELL"
        else:
            dominant = "BALANCED"

        is_toxic = vpin >= 0.70

        return {
            "vpin": vpin,
            "is_toxic": is_toxic,
            "dominant_side": dominant,
            "bucket_count": int(valid_buckets)
        }

    except Exception as e:
        print(f"[VPIN] Error computing VPIN for {symbol}: {e}")
        return _default


# =============================================================================
# INSTITUTIONAL LIQUIDITY SWEEP DETECTOR — Turtle Soup / Judas Swing
# =============================================================================
# Detects when price sweeps above a structural high (or below a structural low)
# to grab resting liquidity, then REJECTS back inside the range — the hallmark
# of an institutional Liquidity Sweep (ICT Turtle Soup / Judas Swing).
#
# This is a zero-API-cost, pure-Python pre-filter. Callers pass in raw OHLC
# candle dicts (same format as detect_fair_value_gaps / detect_order_blocks).
#
# Window Layout:
#   rates[-1]  = current forming candle (EXCLUDED — not yet closed)
#   rates[-2]  = trigger candle (most recently CLOSED candle)
#   rates[:-2] = historical baseline for structural high/low calculation
# =============================================================================

def detect_liquidity_sweep(rates: list, lookback_period: int = 50) -> dict:
    """
    Detects Institutional Liquidity Sweeps (Turtle Soup / Judas Swings).

    A sweep occurs when price briefly pierces a structural level to trigger
    resting stop-loss orders, then reverses — indicating smart money has
    grabbed liquidity and is likely to drive price in the opposite direction.

    Args:
        rates: List of candle dicts [{open, high, low, close}, ...] oldest first.
               Must include at least lookback_period + 2 candles.
        lookback_period: Number of historical candles to scan for structural
                         high/low (default 50). Excludes forming and trigger candles.

    Returns:
        {
            "sweep_detected": bool,
            "direction": "LONG" | "SHORT" | "NONE",
            "stop_loss_anchor": float,    # Tightest SL = trigger candle extreme
            "structural_high": float,
            "structural_low": float,
            "trigger_candle_idx": int,     # Index of trigger candle in rates
            "details": str                 # Human-readable explanation
        }
    """
    _default = {
        "sweep_detected": False,
        "direction": "NONE",
        "stop_loss_anchor": 0.0,
        "structural_high": 0.0,
        "structural_low": 0.0,
        "trigger_candle_idx": -1,
        "details": ""
    }

    # ── Guard: need at least lookback + forming candle + trigger candle ──
    min_candles = lookback_period + 2
    if not rates or len(rates) < min_candles:
        _default["details"] = f"Insufficient candle data ({len(rates) if rates else 0} < {min_candles})"
        return _default

    # ── Window Extraction ──
    # Exclude: rates[-1] (forming candle) and rates[-2] (trigger candle)
    trigger_candle = rates[-2]
    historical_baseline = rates[:-2][-lookback_period:]

    if len(historical_baseline) < lookback_period:
        _default["details"] = f"Baseline window too small ({len(historical_baseline)} < {lookback_period})"
        return _default

    # ── Structural Liquidity Pools ──
    structural_high = max(float(c.get("high", 0)) for c in historical_baseline)
    structural_low = min(float(c.get("low", float("inf"))) for c in historical_baseline)

    # ── Trigger Candle Anatomy ──
    t_open = float(trigger_candle.get("open", 0))
    t_high = float(trigger_candle.get("high", 0))
    t_low = float(trigger_candle.get("low", 0))
    t_close = float(trigger_candle.get("close", 0))

    body_size = abs(t_close - t_open)
    # Prevent division-by-zero on doji candles: use a tiny epsilon
    body_size_safe = max(body_size, 1e-10)

    upper_wick = t_high - max(t_open, t_close)
    lower_wick = min(t_open, t_close) - t_low

    trigger_idx = len(rates) - 2

    # ── Bearish Sweep Detection (SHORT Signal) ──
    # Trap:      trigger high pierced above structural high (grabbed buy-stop liquidity)
    # Rejection: trigger closed BELOW structural high (smart money rejected the breakout)
    # Footprint: upper wick > body * 1.2 (institutional rejection wick)
    bearish_trap = t_high > structural_high
    bearish_rejection = t_close < structural_high
    bearish_footprint = upper_wick > (body_size_safe * 1.2)

    if bearish_trap and bearish_rejection and bearish_footprint:
        result = {
            "sweep_detected": True,
            "direction": "SHORT",
            "stop_loss_anchor": t_high,
            "structural_high": round(structural_high, 5),
            "structural_low": round(structural_low, 5),
            "trigger_candle_idx": trigger_idx,
            "details": (
                f"BEARISH SWEEP: Trigger high {t_high:.5f} pierced structural high "
                f"{structural_high:.5f}, closed at {t_close:.5f} (below). "
                f"Upper wick {upper_wick:.5f} > body {body_size:.5f} × 1.2 = "
                f"{body_size_safe * 1.2:.5f}. SL anchor: {t_high:.5f}"
            )
        }
        logger.info(f"[SWEEP] 🔴 {result['details']}")
        return result

    # ── Bullish Sweep Detection (LONG Signal) ──
    # Trap:      trigger low pierced below structural low (grabbed sell-stop liquidity)
    # Rejection: trigger closed ABOVE structural low (smart money rejected the breakdown)
    # Footprint: lower wick > body * 1.2 (institutional rejection wick)
    bullish_trap = t_low < structural_low
    bullish_rejection = t_close > structural_low
    bullish_footprint = lower_wick > (body_size_safe * 1.2)

    if bullish_trap and bullish_rejection and bullish_footprint:
        result = {
            "sweep_detected": True,
            "direction": "LONG",
            "stop_loss_anchor": t_low,
            "structural_high": round(structural_high, 5),
            "structural_low": round(structural_low, 5),
            "trigger_candle_idx": trigger_idx,
            "details": (
                f"BULLISH SWEEP: Trigger low {t_low:.5f} pierced structural low "
                f"{structural_low:.5f}, closed at {t_close:.5f} (above). "
                f"Lower wick {lower_wick:.5f} > body {body_size:.5f} × 1.2 = "
                f"{body_size_safe * 1.2:.5f}. SL anchor: {t_low:.5f}"
            )
        }
        logger.info(f"[SWEEP] 🟢 {result['details']}")
        return result

    # ── No Sweep Detected ──
    _default["structural_high"] = round(structural_high, 5)
    _default["structural_low"] = round(structural_low, 5)
    _default["trigger_candle_idx"] = trigger_idx
    _default["details"] = (
        f"No sweep. Trigger H/L: {t_high:.5f}/{t_low:.5f} vs "
        f"Structural H/L: {structural_high:.5f}/{structural_low:.5f}. "
        f"Upper wick: {upper_wick:.5f}, Lower wick: {lower_wick:.5f}, Body: {body_size:.5f}"
    )
    return _default

# =============================================================================
# LUXALGO SMC PORT: Equal Highs/Lows, Premium/Discount Zones, BOS/CHoCH
# =============================================================================

def detect_equal_highs_lows(candles: list, atr: float = 0.0, threshold_pct: float = 0.001) -> str:
    """
    Detects Retail Liquidity Pools (Equal Highs or Equal Lows) that act as magnets for Smart Money.
    """
    if len(candles) < 10: return ""
    
    highs = []
    lows = []
    for i in range(2, len(candles) - 2):
        try:
            c = candles[i]
            c_h = float(c.get('high', 0))
            c_l = float(c.get('low', 0))
            
            # Fractal High
            if c_h > float(candles[i-1].get('high', 0)) and c_h > float(candles[i-2].get('high', 0)) and \
               c_h > float(candles[i+1].get('high', 0)) and c_h > float(candles[i+2].get('high', 0)):
                highs.append(c_h)
                
            # Fractal Low
            if c_l < float(candles[i-1].get('low', 0)) and c_l < float(candles[i-2].get('low', 0)) and \
               c_l < float(candles[i+1].get('low', 0)) and c_l < float(candles[i+2].get('low', 0)):
                lows.append(c_l)
        except Exception:
            continue
            
    eqh_found = []
    for i in range(len(highs)):
        for j in range(i+1, len(highs)):
            if abs(highs[i] - highs[j]) / (highs[i] or 1) <= threshold_pct:
                eqh_found.append(max(highs[i], highs[j]))
                
    eql_found = []
    for i in range(len(lows)):
        for j in range(i+1, len(lows)):
            if abs(lows[i] - lows[j]) / (lows[i] or 1) <= threshold_pct:
                eql_found.append(min(lows[i], lows[j]))
                
    res = []
    if eqh_found:
        eqh = sorted(eqh_found)[-1]
        res.append(f"EQUAL HIGHS (Buy-Side Liquidity) ~${eqh:,.2f}")
    if eql_found:
        eql = sorted(eql_found)[0]
        res.append(f"EQUAL LOWS (Sell-Side Liquidity) ~${eql:,.2f}")
        
    return " | ".join(res)

def detect_premium_discount_zones(candles: list, current_price: float) -> str:
    """
    Calculates the macro Equilibrium (50%) of the recent range.
    """
    if not candles: return ""
    
    try:
        highs = [float(c.get('high', 0)) for c in candles if float(c.get('high', 0)) > 0]
        lows = [float(c.get('low', 0)) for c in candles if float(c.get('low', 0)) > 0]
        
        if not highs or not lows: return ""
        
        macro_high = max(highs)
        macro_low = min(lows)
        range_size = macro_high - macro_low
        
        if range_size <= 0: return ""
        
        equilibrium = macro_low + (range_size / 2)
        position_pct = ((current_price - macro_low) / range_size) * 100
        
        if position_pct > 60:
            zone = "PREMIUM (Expensive - Favorable for SHORTS)"
        elif position_pct < 40:
            zone = "DISCOUNT (Cheap - Favorable for LONGS)"
        else:
            zone = "EQUILIBRIUM (Fair Value - Choppy)"
            
        return f"Zone: {zone} | Level: {position_pct:.1f}% of range (${macro_low:,.0f} - ${macro_high:,.0f})"
    except Exception:
        return ""

def detect_market_structure(candles: list, current_price: float) -> str:
    """
    Programmatically flags Break of Structure (BOS) / Change of Character (CHoCH).
    """
    if len(candles) < 20: return ""
    
    try:
        highs = []
        lows = []
        for i in range(2, len(candles) - 2):
            c_h = float(candles[i].get('high', 0))
            c_l = float(candles[i].get('low', 0))
            if c_h > float(candles[i-1].get('high', 0)) and c_h > float(candles[i+1].get('high', 0)):
                highs.append(c_h)
            if c_l < float(candles[i-1].get('low', 0)) and c_l < float(candles[i+1].get('low', 0)):
                lows.append(c_l)
                
        if not highs or not lows: return ""
        
        last_high = highs[-1]
        last_low = lows[-1]
        
        if current_price > last_high:
            return f"BULLISH BOS/CHoCH: Price breached recent swing high (${last_high:,.2f})"
        elif current_price < last_low:
            return f"BEARISH BOS/CHoCH: Price breached recent swing low (${last_low:,.2f})"
        
        return "Structure: Ranging within recent swing points."
    except Exception:
        return ""

