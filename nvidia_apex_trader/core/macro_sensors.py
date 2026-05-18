import logging
import MetaTrader5 as mt5

logger = logging.getLogger("Macro_Sensors")
logger.setLevel(logging.INFO)

# =============================================================================
# INSTITUTIONAL SMART MONEY CONCEPTS (SMC) DETECTION
# =============================================================================

def detect_fair_value_gaps(candles: list, current_price: float = 0.0, max_lookback: int = 100) -> dict:
    """
    Detects Fair Value Gaps (FVGs) — 3-candle imbalance patterns used by institutional traders.

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
    Detects Order Blocks (OBs) — institutional supply/demand zones.

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
    """
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "GOLD.i#"]
    matrix = {}
    
    for sym in symbols:
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
        # GOLD.i# is broker-literal for XAU/USD
        if sym.startswith("GOLD"):
            base, quote = "XAU", "USD"
        else:
            base = sym[:3]
            quote = sym[3:]
        
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

def check_killzones(timestamp_str: str = "", broker_offset: int = 0) -> bool:
    """
    Checks if the given timestamp falls within high-probability institutional
    trading windows (NO Asian session — low liquidity causes bad fills):
    - London Killzone: 07:00 - 11:00 UTC
    - New York Killzone: 13:00 - 17:00 UTC
    
    If timestamp_str is empty (live mode), uses datetime.utcnow().
    """
    from datetime import datetime
    
    if not timestamp_str:
        now = datetime.utcnow()
        hour = now.hour
    else:
        try:
            dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M")
            hour = dt.hour
        except ValueError:
            try:
                dt = datetime.fromisoformat(timestamp_str)
                hour = dt.hour
            except ValueError:
                return True

    adjusted_hour = (hour + broker_offset) % 24
    
    # TIGHTENED: London + NY only. Asian session REMOVED to prevent low-liquidity entries.
    LONDON_OPEN = 7
    LONDON_CLOSE = 11
    NY_OPEN = 13
    NY_CLOSE = 17

    in_london = LONDON_OPEN <= adjusted_hour <= LONDON_CLOSE
    in_ny = NY_OPEN <= adjusted_hour <= NY_CLOSE

    return in_london or in_ny


def is_killzone_active() -> bool:
    """Convenience function: returns True if current UTC time is within London or NY killzone.
    Called before every new entry attempt. Trailing/management of open trades is always allowed."""
    return check_killzones("")

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
# HTF TREND BIAS GATE — H1 EMA20 vs EMA50 (mandatory pre-entry filter)
# =============================================================================

def get_h1_trend_bias(symbol: str) -> dict:
    """
    Fetches H1 EMA20 and EMA50 from MT5 to determine mandatory trade direction.
    This is a HARD GATE — not a weighted suggestion.
    
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
        
        if gap_pct < 0.03:
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


# =============================================================================
# MOMENTUM CONFIRMATION — M15 candle direction check (pre-entry filter)
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
            print(f"[MOMENTUM] {symbol}: Last M15 candle does NOT confirm {direction.upper()} — BLOCKED")
            return False
        
        if prev_body_size > 0 and prev_body_bot < current_price < prev_body_top:
            depth = min(current_price - prev_body_bot, prev_body_top - current_price)
            penetration = depth / prev_body_size
            if penetration > 0.5:
                print(f"[MOMENTUM] {symbol}: Price mid-candle ({penetration:.0%} into prev body) — BLOCKED")
                return False
        
        print(f"[MOMENTUM] {symbol}: {direction.upper()} confirmed by M15 structure ✓")
        return True
    
    except Exception as e:
        print(f"[MOMENTUM] Error checking {symbol}: {e}")
        return False
