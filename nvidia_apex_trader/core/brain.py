import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import os
import json
import re
import asyncio
import subprocess
import requests
import time
import socket
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
from core.memory import load_memory

_original_getaddrinfo = socket.getaddrinfo
def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _ipv4_only_getaddrinfo
import urllib3.util.connection as _urllib3_conn
_urllib3_conn.allowed_gai_family = lambda: socket.AF_INET

env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_API_KEY_2 = os.getenv("NVIDIA_API_KEY_2", "")
NVIDIA_API_KEY_3 = os.getenv("NVIDIA_API_KEY_3", "")

# Build rotation pool of NVIDIA keys
NVIDIA_KEYS = [k for k in [NVIDIA_API_KEY, NVIDIA_API_KEY_2, NVIDIA_API_KEY_3] if k]
print(f"[BRAIN] Loaded {len(NVIDIA_KEYS)} NVIDIA API key(s) for rotation")

# Auto-update Hermes Agent config.yaml with WSL gateway IP so fallback model works
try:
    print("[BRAIN] Synchronizing Hermes Agent fallback IP...")
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    subprocess.run([
        "wsl", "--", "/home/hyper/.hermes/hermes-agent/venv/bin/python", "-c",
        "import yaml, socket, subprocess\n"
        "out = subprocess.check_output(['ip', 'route']).decode()\n"
        "gateway_ip = [l.split()[2] for l in out.split('\\n') if l.startswith('default')][0]\n"
        "config_path = '/home/hyper/.hermes/config.yaml'\n"
        "try:\n"
        "    with open(config_path, 'r') as f:\n"
        "        config = yaml.safe_load(f)\n"
        "    if 'fallback_model' in config and config['fallback_model']['provider'] == 'lm_studio':\n"
        "        config['fallback_model']['base_url'] = f'http://{gateway_ip}:1234/v1'\n"
        "        with open(config_path, 'w') as f:\n"
        "            yaml.dump(config, f, default_flow_style=False)\n"
        "except Exception as e: pass"
    ], creationflags=creationflags, check=False)
except Exception as e:
    print(f"[BRAIN] Failed to sync Hermes fallback IP: {e}")

# API Key rate limiting state dictionary
api_key_states = {}

def get_key_state(api_key):
    if api_key not in api_key_states:
        api_key_states[api_key] = {
            "last_call": 0.0,
            "error_count": 0,
            "last_rate_limit_time": 0.0
        }
    return api_key_states[api_key]

RATE_LIMIT_DELAY = 1.5 # 1.5 seconds between calls (40 RPM = 1.5s per call)

# Memory limits
MAX_MEMORY_MESSAGES = 10
FLIGHT_RECORDER_FILE = "apex_flight_state.json"
GLOBAL_COOLDOWNS = {}

# CHALLENGE MODE — GoatFunded $1,000 challenge (max -$20 drawdown)
# When True, the A+ Gatekeeper mandates an Institutional Liquidity Sweep
# (Turtle Soup / Judas Swing) before any trade can pass. This enforces
# extreme 1:10 R/R asymmetry by requiring the tightest possible SL anchor.
CHALLENGE_MODE = os.getenv("CHALLENGE_MODE", "True").lower() in ("true", "1", "yes")
print(f"[BRAIN] CHALLENGE_MODE: {CHALLENGE_MODE} (Liquidity Sweep Gate {'ACTIVE' if CHALLENGE_MODE else 'DISABLED'})")

# GoatFunded absolute max drawdown: -$20 on $1,000 = 2.0% of account
# No trade's SL percentage may exceed this limit.
GOATFUNDED_MAX_DRAWDOWN_PCT = 2.0

# =============================================================================
# GLOBAL NVIDIA NIM RATE LIMITER (Token Bucket per API key)
# =============================================================================
# NVIDIA limit: 40 RPM. We enforce 30 RPM to leave 25% headroom and avoid bans.
NVIDIA_RPM_LIMIT = 30          # Hard cap: 30 calls per minute per key
NVIDIA_MIN_GAP = 2.5           # Minimum 2.5 seconds between calls on same key
NVIDIA_CALL_LOG = {}           # {api_key: [timestamps]}  rolling 60s window
NVIDIA_LAST_CALL_PER_KEY = {}  # {api_key: last_timestamp}

_nvidia_locks = {}

async def _get_nvidia_lock(api_key: str):
    if api_key not in _nvidia_locks:
        _nvidia_locks[api_key] = asyncio.Lock()
    return _nvidia_locks[api_key]

async def _wait_for_nvidia_rate_limit(api_key: str):
    """Async global pre-flight rate limiter. Sleeps proactively if key is near limit.
    FIX: Converted from threading.Lock + time.sleep to asyncio.Lock + asyncio.sleep
    to prevent event-loop blocking that caused 429 cascades across all 3 agents."""
    global NVIDIA_CALL_LOG, NVIDIA_LAST_CALL_PER_KEY
    now = time.time()
    lock = await _get_nvidia_lock(api_key)
    async with lock:
        # 1. Enforce minimum gap between calls on the same key
        last = NVIDIA_LAST_CALL_PER_KEY.get(api_key, 0)
        gap = now - last
        if gap < NVIDIA_MIN_GAP:
            sleep_needed = NVIDIA_MIN_GAP - gap
            print(f"[NVIDIA-RATE-LIMITER] Key gap too short ({gap:.2f}s < {NVIDIA_MIN_GAP}s). Sleeping {sleep_needed:.2f}s...")
            await asyncio.sleep(sleep_needed)
            now = time.time()

        # 2. Rolling 60-second window: prune old timestamps
        log = NVIDIA_CALL_LOG.get(api_key, [])
        cutoff = now - 60
        log = [t for t in log if t > cutoff]

        # 3. If we're at or near the limit, sleep until oldest call expires
        if len(log) >= NVIDIA_RPM_LIMIT:
            oldest = min(log)
            sleep_until = oldest + 60 + 0.5  # 0.5s safety margin
            sleep_needed = max(0, sleep_until - now)
            if sleep_needed > 0:
                print(f"[NVIDIA-RATE-LIMITER] Key at {len(log)}/30 RPM. Sleeping {sleep_needed:.1f}s until window clears...")
                await asyncio.sleep(sleep_needed)
                now = time.time()
                # Re-prune after sleep
                log = [t for t in log if t > (now - 60)]

        # 4. Record this call
        log.append(now)
        NVIDIA_CALL_LOG[api_key] = log
        NVIDIA_LAST_CALL_PER_KEY[api_key] = now
        rpm = len(log)
        if rpm >= 20:
            print(f"[NVIDIA-RATE-LIMITER] Key RPM: {rpm}/30 — approaching limit, calls throttled")

# Circuit breaker for NVIDIA API
nvidia_circuit_broken = False
nvidia_circuit_failure_count = 0
nvidia_circuit_last_failure = 0
NVIDIA_CIRCUIT_THRESHOLD = 5  # Open circuit after 5 consecutive failures
NVIDIA_CIRCUIT_COOLDOWN = 120  # 2 minutes before testing again

nvidia_client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY
)

BLOCKRUN_PROXY = "http://127.0.0.1:8402"
BLOCKRUN_AUTH = "x402-proxy-handles-auth"
BLOCKRUN_FREE_MODEL = "meta/llama-4-maverick"

LOCAL_LLM_URL = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1/chat/completions")

WAKE_CYCLES_REMAINING = 0

# AI Consensus response cache — prevents redundant NVIDIA calls when price hasn't moved
_ai_consensus_cache = {}  # {cache_key: {"result": dict, "expires": float, "created": float}}
AI_CACHE_TTL = 45       # Cache valid for 45 seconds

def _make_ai_cache_key(symbol: str, market_data_text: str, live_price: float, force_run: bool) -> str:
    """Create a cache key based on symbol, price bucket, and market data fingerprint."""
    import hashlib
    # Round price to nearest $2 for GOLD to avoid cache misses on tiny wiggles
    price_bucket = round(live_price / 2) * 2 if live_price > 0 else 0
    # Force-run bypasses cache
    force_flag = "FORCE" if force_run else "NORMAL"
    data = f"{symbol}:{price_bucket}:{force_flag}:{market_data_text[:500]}"
    return hashlib.md5(data.encode()).hexdigest()

def parse_timeframe_metrics(market_data_text: str) -> dict:
    metrics = {}
    pattern = re.compile(
        r'\[(?P<tf>\d+[mh])\].*?EMA9/21:\s*(?P<ema>[A-Z_]+)\s*\([^)]*\)\s*'
        r'\| Momentum\([^)]*\):\s*(?P<momentum>[+-]?[\d.]+)%\s*'
        r'\| Strength:\s*(?P<higher>\d+)\s*higher\s*/\s*(?P<lower>\d+)\s*lower closes\s*'
        r'\| Last 5 candles:\s*(?P<green>\d+)\s*green\s*/\s*(?P<red>\d+)\s*red\s*'
        r'\| Trend Score:\s*(?P<score>[+-]?\d+)/100',
        re.IGNORECASE,
    )
    for match in pattern.finditer(market_data_text or ""):
        tf = match.group("tf")
        metrics[tf] = {
            "ema_cross": match.group("ema").upper(),
            "momentum_pct": float(match.group("momentum")),
            "consecutive_higher": int(match.group("higher")),
            "consecutive_lower": int(match.group("lower")),
            "green_count": int(match.group("green")),
            "red_count": int(match.group("red")),
            "trend_score": int(match.group("score")),
        }
    return metrics

def detect_trend_exhaustion(market_data_text: str, action: str) -> dict:
    metrics = parse_timeframe_metrics(market_data_text)
    if action not in ("LONG", "SHORT") or not metrics:
        return {"veto": False, "reason": "", "metrics": metrics}

    is_long = action == "LONG"
    fresh_cross = "GOLDEN_CROSS" if is_long else "DEATH_CROSS"
    fresh_cross_present = any(tf_data.get("ema_cross") == fresh_cross for tf_data in metrics.values())

    triggers = []
    for tf, momentum_floor, streak_floor, candle_floor, score_floor in (
        ("1m", 1.0, 5, 5, 75),
        ("5m", 1.5, 5, 5, 65),
        ("15m", 2.5, 0, 5, 60),
    ):
        tf_data = metrics.get(tf)
        if not tf_data:
            continue
        if is_long:
            is_extended = (
                tf_data["momentum_pct"] >= momentum_floor and
                tf_data["trend_score"] >= score_floor and
                (tf_data["consecutive_higher"] >= streak_floor or tf_data["green_count"] >= candle_floor)
            )
            streak = tf_data["consecutive_higher"]
        else:
            is_extended = (
                tf_data["momentum_pct"] <= -momentum_floor and
                tf_data["trend_score"] <= -score_floor and
                (tf_data["consecutive_lower"] >= streak_floor or tf_data["red_count"] >= candle_floor)
            )
            streak = tf_data["consecutive_lower"]
        if is_extended:
            triggers.append(f"{tf}: momentum {tf_data['momentum_pct']:+.2f}%, score {tf_data['trend_score']:+d}, streak {streak}")

    severe_extension = len(triggers) >= 2 or any(t.startswith("15m") for t in triggers)
    if severe_extension and not fresh_cross_present:
        return {"veto": True, "reason": "; ".join(triggers), "metrics": metrics}

    return {"veto": False, "reason": "", "metrics": metrics}


def validate_trend_start_entry(market_data_text: str, action: str, macro_result: dict, scalper_result: dict, trend_bias: dict, live_price: float = 0.0, symbol: str = "") -> dict:
    """Final deterministic entry gate before any live trade can be emitted.

    The LLMs can describe a trade, but execution must still prove that this is an
    early trend-continuation entry: trend sign, MTF candles, macro, and scalper all
    agree. This blocks late chase entries and weak reversals that usually hit SL.
    """
    if action not in ("LONG", "SHORT"):
        return {"pass": True, "reason": "No directional trade requested"}

    expected = "BUY" if action == "LONG" else "SELL"
    is_long = action == "LONG"
    metrics = parse_timeframe_metrics(market_data_text)
    if not metrics:
        return {"pass": False, "reason": "No candle metrics available for entry timing"}

    macro_decision = str(macro_result.get("decision", "HOLD")).upper()
    scalper_decision = str(scalper_result.get("decision", "HOLD")).upper()
    macro_conf = safe_int(macro_result.get("confidence", 0), 0, 0, 100)
    scalper_conf = safe_int(scalper_result.get("confidence", 0), 0, 0, 100)
    trend_score = safe_int(trend_bias.get("score", 0), 0, -100, 100)

    # Majority voting: HOLD = abstention (not opposition). Only active counter-signals block.
    opposite = "SELL" if expected == "BUY" else "BUY"
    agree_count = 0
    oppose_count = 0
    if macro_decision == expected: agree_count += 1
    elif macro_decision == opposite: oppose_count += 1  # Active opposition
    if scalper_decision == expected: agree_count += 1
    elif scalper_decision == opposite: oppose_count += 1  # Active opposition

    if oppose_count > 0:
        return {"pass": False, "reason": f"Agent actively opposing {expected}: Macro={macro_decision}, Scalper={scalper_decision}"}
    if agree_count == 0:
        return {"pass": False, "reason": f"No AI agent agrees with {expected} (Macro={macro_decision}, Scalper={scalper_decision})"}

    # Confidence gate: best AGREEING agent must be >= 60%
    best_conf = max(
        macro_conf if macro_decision == expected else 0,
        scalper_conf if scalper_decision == expected else 0
    )
    if best_conf < 60:
        return {"pass": False, "reason": f"Best agreeing agent confidence {best_conf}% < 60%"}
    if is_long and trend_score < 15:
        return {"pass": False, "reason": f"Trend score {trend_score:+d} too weak for LONG start"}
    if not is_long and trend_score > -15:
        return {"pass": False, "reason": f"Trend score {trend_score:+d} too weak for SHORT start"}

    aligned = []
    counter = []
    present = []
    for tf in ("5m", "15m", "1h"):
        data = metrics.get(tf)
        if not data:
            continue
        present.append(tf)
        score = safe_int(data.get("trend_score", 0), 0, -100, 100)
        momentum = safe_float(data.get("momentum_pct", 0.0), 0.0)
        ema = str(data.get("ema_cross", "")).upper()
        if is_long:
            if score >= 10 and momentum >= -0.05:
                aligned.append(f"{tf}:{score:+d}")
            if score <= -20 or ema == "DEATH_CROSS" or momentum < -0.20:
                counter.append(f"{tf}:{score:+d}/{momentum:+.2f}%")
        else:
            if score <= -10 and momentum <= 0.05:
                aligned.append(f"{tf}:{score:+d}")
            if score >= 20 or ema == "GOLDEN_CROSS" or momentum > 0.20:
                counter.append(f"{tf}:{score:+d}/{momentum:+.2f}%")

    if len(present) >= 2 and len(aligned) < 2:
        return {"pass": False, "reason": f"Only {len(aligned)}/{len(present)} timing frames align ({', '.join(aligned) or 'none'})"}
    if counter:
        return {"pass": False, "reason": f"Counter-trend timing frame present: {', '.join(counter)}"}

    raw_entry = scalper_result.get("entry_price", 0)
    entry_price = safe_float(raw_entry, live_price or 0.0, 0.0)
    if live_price and live_price > 0 and entry_price > 0:
        gap_pct = abs(entry_price - live_price) / live_price * 100
        # Asset-class-aware distance: Gold/Index/Crypto tick faster than Forex
        _sym_upper = (symbol or "").upper()
        if any(m in _sym_upper for m in ("GOLD", "XAU", "SILVER", "XAG")):
            max_entry_gap = 0.50
        elif any(m in _sym_upper for m in ("US30", "US100", "US500", "JP225", "GER40", "DJ30", "BTC", "ETH")):
            max_entry_gap = 0.40
        else:
            max_entry_gap = 0.30  # Forex
        if gap_pct > max_entry_gap:
            return {"pass": False, "reason": f"Scalper entry is {gap_pct:.3f}% away from live price (max {max_entry_gap}%)"}

    return {"pass": True, "reason": f"Trend-start confirmed: {', '.join(aligned) or 'bias-only'} | Best conf {best_conf}%"}
# ============================================================
# TREND BIAS PRE-SCORER — Local Python trend analysis (no API cost)
# ============================================================
def compute_trend_bias(market_data_text: str) -> dict:
    """Extract trend scores from candle data in market_data_text.
    Returns a composite bias from -100 (strong bearish) to +100 (strong bullish).
    This runs BEFORE any LLM calls and is injected into all agent prompts."""
    import re
    scores = []
    weights = {"1m": 0.5, "5m": 1.0, "15m": 1.5, "1h": 2.5, "4h": 3.5}  # Higher TF = more weight
    
    # Extract trend scores from the enhanced candle format
    for match in re.finditer(r'\[(\d+[mh])\].*?Trend Score:\s*([+-]?\d+)/100', market_data_text):
        tf = match.group(1)
        score = int(match.group(2))
        weight = weights.get(tf, 1.0)
        scores.append((tf, score, weight))
    
    if not scores:
        return {"score": 0, "label": "NEUTRAL", "detail": "No candle data available"}
    
    # Weighted average
    total_weight = sum(w for _, _, w in scores)
    weighted_score = sum(s * w for _, s, w in scores) / total_weight if total_weight > 0 else 0
    weighted_score = max(-100, min(100, int(weighted_score)))
    
    # Determine label
    if weighted_score >= 60:
        label = "STRONG_BULLISH"
    elif weighted_score >= 30:
        label = "BULLISH"
    elif weighted_score >= 10:
        label = "LEAN_BULLISH"
    elif weighted_score <= -60:
        label = "STRONG_BEARISH"
    elif weighted_score <= -30:
        label = "BEARISH"
    elif weighted_score <= -10:
        label = "LEAN_BEARISH"
    else:
        label = "NEUTRAL"
    
    detail_parts = [f"{tf}={s:+d}" for tf, s, _ in scores]
    detail = f"Scores: {', '.join(detail_parts)} -> Weighted: {weighted_score:+d}"
    
    print(f"[TREND BIAS] {label} ({weighted_score:+d}/100) | {detail}")
    
    return {"score": weighted_score, "label": label, "detail": detail, "per_tf": {tf: s for tf, s, _ in scores}}


def format_trend_bias(trend_bias: dict) -> str:
    label = str(trend_bias.get("label", "NEUTRAL")).replace("_", " ")
    score = int(trend_bias.get("score", 0) or 0)
    return f"{label} ({score:+d})"


def safe_float(value, default: float = 0.0, min_value: float | None = None, max_value: float | None = None) -> float:
    try:
        if isinstance(value, str):
            match = re.search(r"[-+]?\d+(?:\.\d+)?", value.replace(",", ""))
            value = match.group(0) if match else default
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if min_value is not None:
        number = max(min_value, number)
    if max_value is not None:
        number = min(max_value, number)
    return number


def safe_int(value, default: int = 0, min_value: int | None = None, max_value: int | None = None) -> int:
    return int(round(safe_float(value, default, min_value, max_value)))


def get_symbol_risk_profile(symbol: str) -> dict:
    sym = (symbol or "").upper()
    clean = re.sub(r"[^A-Z0-9]", "", sym)
    forex_currencies = ("EUR", "GBP", "USD", "JPY", "AUD", "CAD", "CHF", "NZD")
    is_forex = len(clean) >= 6 and clean[:3] in forex_currencies and clean[3:6] in forex_currencies

    if is_forex:
        if "JPY" in clean[:6]:
            return {"class": "FOREX_JPY", "sl": 0.150, "tp": 0.300, "min_sl": 0.100, "min_tp": 0.200}
        if clean[:6] in ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF"):
            return {"class": "FOREX_MAJOR", "sl": 0.150, "tp": 0.300, "min_sl": 0.100, "min_tp": 0.200}
        return {"class": "FOREX_CROSS", "sl": 0.200, "tp": 0.400, "min_sl": 0.150, "min_tp": 0.300}
    if any(m in sym for m in ("GOLD", "XAU")):
        return {"class": "GOLD", "sl": 0.250, "tp": 0.500, "min_sl": 0.150, "min_tp": 0.300}
    if any(m in sym for m in ("SILVER", "XAG")):
        return {"class": "SILVER", "sl": 0.300, "tp": 0.600, "min_sl": 0.200, "min_tp": 0.400}
    if any(i in sym for i in ("US30", "US100", "NAS100", "US500", "SPX500", "JP225", "JAP225", "GER40", "AUS200", "UK100", "DJ30")):
        return {"class": "INDEX", "sl": 0.250, "tp": 0.500, "min_sl": 0.150, "min_tp": 0.300}
    if any(e in sym for e in ("WTI", "OIL", "BRENT")):
        return {"class": "ENERGY", "sl": 0.300, "tp": 0.600, "min_sl": 0.150, "min_tp": 0.300}
    if any(c in sym for c in ("BTC", "ETH", "SOL", "LTC", "BNB", "BCH", "XRP", "ENJ")):
        return {"class": "CRYPTO", "sl": 1.000, "tp": 2.000, "min_sl": 0.500, "min_tp": 1.000}
    return {"class": "FOREX_DEFAULT", "sl": 0.150, "tp": 0.300, "min_sl": 0.100, "min_tp": 0.200}


def clamp_risk_to_symbol(symbol: str, sl_pct, tp_pct) -> tuple[float, float, dict]:
    profile = get_symbol_risk_profile(symbol)
    min_sl = profile.get("min_sl", 0.01)
    sl = safe_float(sl_pct, profile["sl"], min_sl, profile["sl"])
    tp = safe_float(tp_pct, profile["tp"], profile["min_tp"], profile["tp"])
    if tp < sl * 1.5:
        tp = min(profile["tp"], sl * 1.5)
    return round(sl, 3), round(tp, 3), profile


def get_asset_limits(symbol: str) -> dict:
    """
    Returns the GoatFunded-safe dynamic SL/TP limits per asset class.
    These limits are designed to protect the -$20 max drawdown on a $1,000 account.
    The final_sl_pct must NEVER exceed GOATFUNDED_MAX_DRAWDOWN_PCT (2.0%).
    """
    sym = (symbol or "").upper()
    profile = get_symbol_risk_profile(symbol)
    asset_class = profile["class"]

    # Asset-specific minimum SL/TP (the tightest safe breathing room)
    limits = {
        "GOLD":          {"min_sl": 0.25, "min_tp": 0.40, "max_sl": 1.50},
        "SILVER":        {"min_sl": 0.30, "min_tp": 0.50, "max_sl": 1.50},
        "INDEX":         {"min_sl": 0.25, "min_tp": 0.40, "max_sl": 1.50},
        "ENERGY":        {"min_sl": 0.30, "min_tp": 0.50, "max_sl": 1.50},
        "CRYPTO":        {"min_sl": 0.50, "min_tp": 1.50, "max_sl": 2.00},
        "FOREX_MAJOR":   {"min_sl": 0.10, "min_tp": 0.20, "max_sl": 1.00},
        "FOREX_JPY":     {"min_sl": 0.10, "min_tp": 0.20, "max_sl": 1.00},
        "FOREX_CROSS":   {"min_sl": 0.15, "min_tp": 0.30, "max_sl": 1.00},
        "FOREX_DEFAULT": {"min_sl": 0.10, "min_tp": 0.20, "max_sl": 1.00},
    }

    asset_limits = limits.get(asset_class, {"min_sl": 0.10, "min_tp": 0.20, "max_sl": 1.00})

    # Hard cap: no asset class may exceed the GoatFunded drawdown limit
    asset_limits["max_sl"] = min(asset_limits["max_sl"], GOATFUNDED_MAX_DRAWDOWN_PCT)
    asset_limits["asset_class"] = asset_class
    asset_limits["profile"] = profile

    return asset_limits


# ============================================================
# PROMPT COMPRESSION HELPERS — Minimize token count for 8B models
# ============================================================

def compress_candle_data(raw_text: str, max_candles: int = 5) -> str:
    """Extract last N candles + final indicator values from verbose market data text.
    Reduces ~500+ tokens per timeframe down to ~60 tokens."""
    import re
    lines = []
    # Extract trend scores per timeframe
    for m in re.finditer(r'\[(\d+[mh])\].*?EMA9/21:\s*(\w+).*?Trend Score:\s*([+-]?\d+)/100', raw_text, re.DOTALL):
        lines.append(f"[{m.group(1)}] EMA:{m.group(2)} Score:{m.group(3)}")
    # Extract last N OHLCV candles (format: O:x,H:x,L:x,C:x)
    candle_pattern = re.compile(r'[Oo](?:pen)?[:\s]*([0-9.]+).*?[Hh](?:igh)?[:\s]*([0-9.]+).*?[Ll](?:ow)?[:\s]*([0-9.]+).*?[Cc](?:lose)?[:\s]*([0-9.]+)')
    candles = candle_pattern.findall(raw_text)
    if candles:
        for c in candles[-max_candles:]:
            lines.append(f"O:{c[0]},H:{c[1]},L:{c[2]},C:{c[3]}")
    # Extract SMC levels if present
    for m in re.finditer(r'Nearest (Bullish|Bearish) (FVG|OB).*?(\d+\.?\d*)\s*to\s*(\d+\.?\d*)', raw_text):
        lines.append(f"{m.group(1)[:1]}{m.group(2)}:{m.group(3)}-{m.group(4)}")
    return "\n".join(lines) if lines else raw_text[:300]


def compress_dom_data(raw_dom: str, top_n: int = 3) -> str:
    """Extract top N bid/ask levels from verbose DOM text. ~30 tokens instead of ~200+."""
    import re
    if not raw_dom or len(raw_dom) < 10:
        return "DOM:N/A"
    bids = re.findall(r'[Bb]id.*?(\d+\.?\d+).*?(?:size|vol|qty)[:\s]*(\d+)', raw_dom)
    asks = re.findall(r'[Aa]sk.*?(\d+\.?\d+).*?(?:size|vol|qty)[:\s]*(\d+)', raw_dom)
    parts = []
    if bids:
        parts.append("B:" + ",".join(f"{b[0]}@{b[1]}" for b in bids[:top_n]))
    if asks:
        parts.append("A:" + ",".join(f"{a[0]}@{a[1]}" for a in asks[:top_n]))
    return "|".join(parts) if parts else raw_dom[:150]


def robust_json_parse(text: str, fallback: dict = None) -> dict:
    """Parse JSON with regex fallback for garbled LLM output. Never crashes.
    Enhanced for distilled reasoning models (e.g. Qwen-reasoning) that emit
    chain-of-thought text *before* the final JSON block."""
    import re
    if fallback is None:
        fallback = {}
    if not text:
        return fallback
    clean = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass
    # Strategy 1: Find the LAST {...} block (reasoning models put JSON at the end)
    all_matches = list(re.finditer(r'\{[^{}]*\}', clean, re.DOTALL))
    if all_matches:
        # Try last match first (most likely the final JSON verdict)
        for m in reversed(all_matches):
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
    # Strategy 2: Greedy match — captures nested braces from reasoning models
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', clean, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    # Strategy 3: Last resort — grab everything between first { and last }
    match = re.search(r'\{.*\}', clean, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    print(f"[JSON-PARSE] Failed all attempts: {clean[:150]}")
    return fallback


# ============================================================
# DOM VOLATILITY GATE — Local Python filter to conserve API limits
# ============================================================
async def check_market_volatility(symbol: str = "GOLD") -> dict:
    """Pre-LLM gating function. Parses MT5 Macro Data locally.
    If the market is sideways (low velocity + low currency gap), returns
    a HOLD verdict instantly without burning any LLM API calls.
    """
    from core.macro_sensors import calculate_currency_matrix, detect_tick_velocity
    import asyncio
    
    # Run macro sensors
    matrix_data, velocity_data = await asyncio.gather(
        calculate_currency_matrix(),
        detect_tick_velocity(symbol)
    )
    
    is_high_velocity = velocity_data.get('is_high_velocity', False)
    ratio = velocity_data.get('ratio', 1.0)
    
    strongest = matrix_data.get('strongest', 'USD')
    weakest = matrix_data.get('weakest', 'USD')
    scores = matrix_data.get('scores', {})
    
    gap = scores.get(strongest, 50) - scores.get(weakest, 50)
    
    # Gating Logic
    # FIX: If matrix gap is 0.0 (all symbols failed to resolve or weekend),
    # don't auto-block — fall through to velocity-only check.
    if gap == 0.0 and not matrix_data.get('matrix'):
        # Matrix is completely empty — data failure, not a real sideways market
        if ratio > 0.5:
            print(f"[GATING] ⚠ Matrix data unavailable (gap=0.0). Tick Velocity {ratio}x > 0.5x — PASSING on velocity alone.")
            return {"pass": True}
        else:
            print(f"[GATING] ⚠ Matrix data unavailable (gap=0.0) AND low velocity ({ratio}x). Blocking to be safe.")
            return {
                "pass": False,
                "reason": f"Matrix data failure + low velocity ({ratio}x)",
                "result": {
                    "action": "HOLD",
                    "asset": "GOLD",
                    "leverage": 1,
                    "stop_loss_pct": 1.5,
                    "take_profit_pct": 4.0,
                    "volatility": "low",
                    "reasoning": f"GATED: Matrix data failure (0 symbols resolved) + low velocity ({ratio}x).",
                    "_debug": {}
                }
            }
    
    if is_high_velocity or gap >= 20.0:
        print(f"[GATING] Macro volatility confirmed. Tick Velocity: {ratio}x. Matrix Gap: {gap:.1f}. Proceeding to AI consensus.")
        return {"pass": True}
    
    print(f"[GATING] Market is SIDEWAYS. Tick Velocity: {ratio}x | Matrix Gap: {gap:.1f}. Conserving API limits.")
    return {
        "pass": False,
        "reason": f"Sideways market (Velocity {ratio}x, Gap {gap:.1f})",
        "result": {
            "action": "HOLD",
            "asset": "GOLD",
            "leverage": 1,
            "stop_loss_pct": 1.5,
            "take_profit_pct": 4.0,
            "volatility": "low",
            "reasoning": f"GATED: Low volatility (Velocity {ratio}x, Matrix gap {gap:.1f}). Skipping LLM consensus.",
            "_debug": {}
        }
    }




async def fetch_liquidity_data_async() -> str:
    """Fetch liquidity data using asyncio.to_thread - bypasses Windows DNS blocking.
    This calls the synchronous fetch_liquidity_data_sync() in a thread pool."""
    from core.data import fetch_liquidity_data_sync
    return await asyncio.to_thread(fetch_liquidity_data_sync)


async def evaluate_options_spread(options_chain: dict, market_trend: str, acct_balance: float, spot_price: float = 0.0) -> dict:
    """THETA HARVESTER — CREDIT SPREAD EVALUATION (standalone function)."""
    print("=" * 60)
    print("THETA HARVESTER — CREDIT SPREAD EVALUATION")
    print("=" * 60)

    OPTIONS_MAX_LOSS_PCT = 0.02  # 2% max risk per spread

    # Use spot from chain if not provided
    if spot_price <= 0:
        spot_price = options_chain.get("spot_price", 0)
    if spot_price <= 0:
        print("[THETA] ERROR: No spot price available. Cannot construct spreads.")
        return {"action": "HOLD", "reasoning": "No spot price available", "_source": "no_candidates"}

    print(f"[THETA] BTC Spot: ${spot_price:,.2f} | Trend: {market_trend} | Balance: ${acct_balance:,.2f}")
    print(f"[THETA] Chain: {len(options_chain.get('calls', []))}C / {len(options_chain.get('puts', []))}P | Expiries: {options_chain.get('expiry_dates', [])}")

    # ── Step 1: Construct all candidate spreads ──
    candidates = _construct_credit_spreads(options_chain, spot_price, acct_balance, market_trend)

    if not candidates:
        print("[THETA] No viable credit spreads found in the current chain.")
        return {"action": "HOLD", "reasoning": "No viable credit spreads in 0-7d chain", "_source": "no_candidates"}

    # ── Step 2: Apply hard risk cap filter ──
    safe_candidates = [
        c for c in candidates
        if c["total_max_loss"] <= acct_balance * OPTIONS_MAX_LOSS_PCT
    ]
    if not safe_candidates:
        print(f"[THETA] All {len(candidates)} candidates exceed {OPTIONS_MAX_LOSS_PCT*100:.0f}% risk cap.")
        return {"action": "HOLD", "reasoning": f"All spreads exceed {OPTIONS_MAX_LOSS_PCT*100:.0f}% max loss cap", "_source": "no_candidates"}

    print(f"[THETA] {len(safe_candidates)}/{len(candidates)} candidates pass the {OPTIONS_MAX_LOSS_PCT*100:.0f}% risk cap")

    # ── Step 3: Top 5 candidates for AI evaluation ──
    top5 = safe_candidates[:5]

    for i, s in enumerate(top5):
        print(
            f"[THETA] #{i+1}: {s['spread_type']} | "
            f"Sell {s['short_leg']['symbol']} ${s['short_leg']['strike']:,.0f} @ ${s['short_leg']['premium']:.2f} | "
            f"Buy {s['long_leg']['symbol']} ${s['long_leg']['strike']:,.0f} @ ${s['long_leg']['premium']:.2f} | "
            f"Credit: ${s['net_credit_per_contract']:.2f} | MaxLoss: ${s['max_loss_per_contract']:.2f} | "
            f"C/R: {s['credit_risk_ratio']:.3f} | x{s['max_contracts']} | Exp: {s['expiry']}"
        )

    # ── Step 4: NVIDIA NIM AI Selection ──
    ai_selected = None
    try:
        active_key = NVIDIA_KEYS[0] if NVIDIA_KEYS else NVIDIA_API_KEY
        if active_key:
            spreads_text = ""
            for i, s in enumerate(top5):
                spreads_text += (
                    f"\n  Spread #{i+1}: {s['spread_type']}"
                    f"\n    Short: {s['short_leg']['symbol']} (Strike ${s['short_leg']['strike']:,.0f}, "
                    f"Bid ${s['short_leg']['premium']:.2f}, Delta {s['short_leg']['delta']:.3f}, OI {s['short_leg']['oi']:.0f})"
                    f"\n    Long:  {s['long_leg']['symbol']} (Strike ${s['long_leg']['strike']:,.0f}, "
                    f"Ask ${s['long_leg']['premium']:.2f}, Delta {s['long_leg']['delta']:.3f}, OI {s['long_leg']['oi']:.0f})"
                    f"\n    Width: ${s['spread_width']:,.0f} | Net Credit: ${s['net_credit_per_contract']:.2f}/contract | "
                    f"Max Loss: ${s['max_loss_per_contract']:.2f}/contract"
                    f"\n    Credit/Risk Ratio: {s['credit_risk_ratio']:.3f} | Max Contracts: {s['max_contracts']} | "
                    f"OTM%: {s['otm_pct']:.1f}% | Expiry: {s['expiry']}\n"
                )

            system_prompt = """You are an institutional options strategist specializing in BTC Credit Spreads for theta decay harvesting.
You are selecting the OPTIMAL credit spread from a pre-screened list. All spreads already pass risk limits.

SELECTION CRITERIA (in order of priority):
1. CREDIT/RISK RATIO: Higher is better. Prefer ratios above 0.15.
2. OTM DISTANCE: Short leg should be 3-6% OTM for safety. 2-3% is aggressive. >6% may have thin premiums.
3. OPEN INTEREST: Both legs should have OI > 10 for liquidity. Avoid illiquid strikes.
4. EXPIRY: 24-48 hours to expiry is the theta sweet spot. Less than 24h has gamma risk.
5. TREND ALIGNMENT: Bull Put Spreads work best in bullish/neutral. Bear Call Spreads in bearish.

Return ONLY valid JSON:
{
    "selected_spread": 1-5 (the spread number you recommend),
    "contracts": recommended_number_of_contracts,
    "confidence": 0-100,
    "reasoning": "brief explanation citing specific metrics"
}
If NONE of the spreads are acceptable, return: {"selected_spread": 0, "contracts": 0, "confidence": 0, "reasoning": "why"}"""

            user_prompt = f"""BTC Spot: ${spot_price:,.2f}
Market Trend: {market_trend}
Account Balance: ${acct_balance:,.2f}
Max Risk Allowed: ${acct_balance * OPTIONS_MAX_LOSS_PCT:,.2f} ({OPTIONS_MAX_LOSS_PCT*100:.0f}% of balance)

CANDIDATE SPREADS:
{spreads_text}

Select the best spread (1-{len(top5)}) or 0 for HOLD."""

            headers = {"Authorization": f"Bearer {active_key}", "Content-Type": "application/json"}
            payload = {
                "model": "meta/llama-3.1-70b-instruct",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.15,
                "max_tokens": 300,
                "response_format": {"type": "json_object"}
            }

            response = await call_nvidia_nim_api(payload, active_key)

            if response.status_code == 200:
                content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "{}")
                clean = content.replace("```json", "").replace("```", "").strip()
                parsed = json.loads(clean)
                selected_idx = int(parsed.get("selected_spread", 0))
                ai_contracts = int(parsed.get("contracts", 1))
                ai_confidence = int(parsed.get("confidence", 0))
                ai_reasoning = parsed.get("reasoning", "")

                if 1 <= selected_idx <= len(top5):
                    ai_selected = top5[selected_idx - 1]
                    # Override contracts with AI recommendation (capped at max safe)
                    ai_contracts = min(ai_contracts, ai_selected["max_contracts"])
                    ai_contracts = max(1, ai_contracts)
                    ai_selected["_ai_contracts"] = ai_contracts
                    ai_selected["_ai_confidence"] = ai_confidence
                    ai_selected["_ai_reasoning"] = ai_reasoning
                    print(f"[THETA] AI selected Spread #{selected_idx} with {ai_contracts} contracts ({ai_confidence}% confidence)")
                    print(f"[THETA] AI Reasoning: {ai_reasoning}")
                else:
                    print(f"[THETA] AI rejected all spreads: {ai_reasoning}")
            else:
                print(f"[THETA] NVIDIA NIM returned HTTP {response.status_code}. Falling back to local best.")
    except Exception as ai_err:
        print(f"[THETA] AI evaluation error: {ai_err}. Falling back to local best.")

    # ── Step 5: Build final result ──
    if ai_selected:
        chosen = ai_selected
        contracts = chosen.get("_ai_contracts", chosen["max_contracts"])
        confidence = chosen.get("_ai_confidence", 70)
        reasoning = chosen.get("_ai_reasoning", "AI selected best credit/risk ratio")
        source = "ai"
    else:
        # Fallback: pick the best credit/risk ratio candidate locally
        chosen = top5[0]
        contracts = min(chosen["max_contracts"], max(1, int(acct_balance * 0.10 / chosen["max_loss_per_contract"])))
        confidence = 50
        reasoning = f"Local fallback: best credit/risk ratio {chosen['credit_risk_ratio']:.3f}"
        source = "local_best"

    total_credit = round(chosen["net_credit_per_contract"] * contracts, 2)
    total_max_loss = round(chosen["max_loss_per_contract"] * contracts, 2)
    risk_pct = round(total_max_loss / acct_balance * 100, 2) if acct_balance > 0 else 0

    result = {
        "action": "OPEN_SPREAD",
        "spread_type": chosen["spread_type"],
        "short_leg": chosen["short_leg"],
        "long_leg": chosen["long_leg"],
        "spread_width": chosen["spread_width"],
        "contracts": contracts,
        "net_credit": total_credit,
        "max_loss": total_max_loss,
        "risk_pct": risk_pct,
        "credit_risk_ratio": chosen["credit_risk_ratio"],
        "expiry": chosen["expiry"],
        "reasoning": reasoning,
        "confidence": confidence,
        "_source": source,
    }

    print("=" * 60)
    print(f"THETA DECISION: {result['action']} — {result['spread_type']}")
    print(f"  Short: {result['short_leg']['symbol']} @ ${result['short_leg']['premium']:.2f}")
    print(f"  Long:  {result['long_leg']['symbol']} @ ${result['long_leg']['premium']:.2f}")
    print(f"  Contracts: {contracts} | Net Credit: ${total_credit:.2f} | Max Loss: ${total_max_loss:.2f} ({risk_pct:.1f}% of balance)")
    print("=" * 60)

    return result


async def evaluate_options_market(
    market_data: dict,
    options_chain: dict,
    margin: float = 0.0
) -> dict:
    """Legacy wrapper — routes to evaluate_options_spread for backward compatibility."""
    trend = market_data.get("trend", "neutral")
    spot = market_data.get("price", market_data.get("last_price", options_chain.get("spot_price", 0)))
    return await evaluate_options_spread(options_chain, trend, margin, spot)


async def run_trade_autopsy(trade_data: dict, market_context: dict) -> dict:
    """
    Run an AI-powered autopsy on a closed trade to analyze performance.
    
    Args:
        trade_data: Dict containing trade details (symbol, side, entry, exit, pnl, etc.)
        market_context: Dict containing market conditions at time of trade
        
    Returns:
        Dict with autopsy analysis including what went right/wrong
    """
    try:
        symbol = trade_data.get("symbol", "UNKNOWN")
        side = trade_data.get("side", "long")
        entry = trade_data.get("entry_price", 0)
        exit_price = trade_data.get("exit_price", 0)
        pnl = trade_data.get("realized_pnl", 0)
        exit_reason = trade_data.get("exit_reason", "unknown")
        
        # Simple analysis based on PnL
        if pnl > 0:
            analysis = f"Profitable {side} trade on {symbol}. Entry ${entry:.2f}, exit ${exit_price:.2f}. Exit via {exit_reason}."
            grade = "A" if pnl > entry * 0.01 else "B"
        elif pnl < 0:
            analysis = f"Loss on {side} {symbol}. Entry ${entry:.2f}, exit ${exit_price:.2f}. Review {exit_reason} timing."
            grade = "C" if pnl > -entry * 0.01 else "D"
        else:
            analysis = f"Breakeven trade on {symbol}. No profit/loss recorded."
            grade = "B-"
        
        print(f"[AUTOPSY] Trade graded {grade}: {analysis[:80]}...")
        
        return {
            "success": True,
            "grade": grade,
            "analysis": analysis,
            "trade_symbol": symbol,
            "pnl": pnl,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"[AUTOPSY] Error running autopsy: {e}")
        return {
            "success": False,
            "error": str(e),
            "trade_symbol": trade_data.get("symbol", "UNKNOWN")
        }

import aiohttp
import json
import asyncio

async def call_lm_studio_direct(prompt: str) -> dict:
    """Direct fast-path to local LM Studio for simpler agents to save NVIDIA quota."""
    try:
        import aiohttp
        import os
        async with aiohttp.ClientSession() as session:
            lm_payload = {
                "model": "meta/llama-3.1-70b-instruct",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "stream": False
            }
            lm_url = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1/chat/completions")
            api_key = os.getenv("LM_STUDIO_API_KEY", "lm-studio")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
                
            async with session.post(lm_url, json=lm_payload, headers=headers, timeout=300) as resp:
                if resp.status == 200:
                    lm_data = await resp.json()
                    message_obj = lm_data["choices"][0]["message"]
                    lm_content = message_obj.get("content", "")
                    
                    if not lm_content and "reasoning_content" in message_obj:
                        lm_content = message_obj["reasoning_content"]
                        
                    # Local models might add conversational text around the JSON.
                    # Use regex to extract everything between the first { and last }
                    import re
                    match = re.search(r'\{.*\}', lm_content, re.DOTALL)
                    if match:
                        lm_content = match.group(0)
                    else:
                        lm_content = lm_content.replace('```json', '').replace('```', '').strip()
                    
                    try:
                        # Clean unescaped literal newlines which break json.loads
                        clean_json = lm_content.replace('\n', ' ')
                        return json.loads(clean_json)
                    except json.JSONDecodeError:
                        # Robust rescue via Regex for cut-off or badly formed JSON
                        import re
                        decision_match = re.search(r'"decision"\s*:\s*"([A-Z]+)"', lm_content, re.IGNORECASE)
                        conf_match = re.search(r'"confidence"\s*:\s*(\d+)', lm_content)
                        
                        if decision_match:
                            return {
                                "decision": decision_match.group(1).upper(),
                                "confidence": int(conf_match.group(1)) if conf_match else 50,
                                "reasoning": "Rescued via Regex from broken JSON output."
                            }
                        return {"decision": "HOLD", "confidence": 0, "reasoning": "LM Studio generated completely invalid output"}
                else:
                    return {"decision": "HOLD", "confidence": 0, "reasoning": f"LM Studio HTTP {resp.status}"}
    except Exception as e:
        err_msg = str(e)
        if "Timeout" in err_msg or not err_msg:
            err_msg = "Request timed out (Model too slow)"
        return {"decision": "HOLD", "confidence": 0, "reasoning": f"LM Studio Connection Error: {err_msg}"}

async def _clean_json_response(content: str) -> dict:
    import json
    import re
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        content = match.group(0)
    else:
        content = content.replace('```json', '').replace('```', '').strip()
    try:
        clean_json = content.replace('\n', ' ')
        return json.loads(clean_json)
    except json.JSONDecodeError:
        decision_match = re.search(r'"decision"\s*:\s*"([A-Z]+)"', content, re.IGNORECASE)
        conf_match = re.search(r'"confidence"\s*:\s*(\d+)', content)
        if decision_match:
            return {
                "decision": decision_match.group(1).upper(),
                "confidence": int(conf_match.group(1)) if conf_match else 50,
                "reasoning": "Rescued via Regex from broken JSON output."
            }
        return None

async def call_hermes_gateway(payload: dict, broadcast_callback=None, session_name="apex_trader") -> dict:
    """
    Loops through the multi-tier fallback architecture.
    """
    import aiohttp
    import json
    import os
    import asyncio
    
    prompt = payload["messages"][-1]["content"]
    
    if broadcast_callback:
        asyncio.create_task(broadcast_callback({
            "type": "hermes_activity",
            "agent_status": "analyzing",
            "message": f"[{session_name.upper()}] Routing through AI Gateway...",
            "reasoning": "Loading DOM and macro sensors into working memory...\nChecking endpoints..."
        }))

    import random
    import shlex
    
    # Load-balance NVIDIA keys natively by passing to the Hermes subprocess environment
    NVIDIA_KEYS = [k.strip() for k in os.getenv("NVIDIA_API_KEY", "").split(",") if k.strip()]
    nim_key = random.choice(NVIDIA_KEYS) if NVIDIA_KEYS else os.getenv("NVIDIA_API_KEY", "")
    
    env = os.environ.copy()
    env["NVIDIA_API_KEY"] = nim_key
    
    skills_path = "/mnt/f/NEW NVdia Apex Ultimate/.agent/skills.md"
    
    try:
        import subprocess
        creationflags = 0
        if os.name == 'nt':
            creationflags = subprocess.CREATE_NO_WINDOW

        process = await asyncio.create_subprocess_exec(
            "wsl", "--", "/home/hyper/.hermes/hermes-agent/venv/bin/python", "-m", "hermes_cli.main", 
            "chat", "-Q", "-q", prompt, "-s", skills_path, "--yolo", "--accept-hooks",
            "--provider", "nvidia", "-m", "meta/llama-3.1-70b-instruct",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=creationflags,
            env=env
        )
        
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=600)
        
        if process.returncode != 0:
            err_msg = stderr.decode('utf-8')
            out_msg = stdout.decode('utf-8')
            full_err = f"OUT: {out_msg[:200]} | ERR: {err_msg[:200]}"
            print(f"[{session_name.upper()}] HERMES CLI Failed: {full_err}")
            if broadcast_callback:
                await broadcast_callback({
                    "type": "hermes_activity",
                    "agent_status": "generating_strategy",
                    "message": f"HERMES CLI failed. Returning HOLD.",
                    "reasoning": f"Error: {full_err[:100]}"
                })
            return {"decision": "HOLD", "confidence": 0, "reasoning": f"Hermes CLI Error: {full_err[:100]}"}
            
        content = stdout.decode('utf-8')
        result = await _clean_json_response(content)
        
        if result:
            if broadcast_callback:
                await broadcast_callback({
                    "type": "hermes_activity",
                    "agent_status": "complete",
                    "message": f"Evaluation complete via HERMES NATIVE CLI.",
                    "reasoning": f"Final Decision: {result.get('decision', 'UNKNOWN')} | Confidence: {result.get('confidence', 0)}%"
                })
            return result
        else:
            print(f"[{session_name.upper()}] HERMES returned invalid JSON: {content[:100]}")
            return {"decision": "HOLD", "confidence": 0, "reasoning": "Hermes CLI returned invalid JSON"}
            
    except asyncio.TimeoutError:
        print(f"[{session_name.upper()}] HERMES CLI timeout.")
        return {"decision": "HOLD", "confidence": 0, "reasoning": "Hermes WSL CLI timed out"}
    except Exception as e:
        print(f"[{session_name.upper()}] HERMES CLI Exception: {str(e)}")
        return {"decision": "HOLD", "confidence": 0, "reasoning": f"Hermes WSL CLI Exception: {str(e)}"}


async def evaluate_market(memory_text: str, market_data_text: str, margin: float = 0, dom_data: str = "", active_positions: list = None, force_run: bool = False, active_symbol: str = "GOLD", live_asset_price: float = 0.0, broadcast_callback=None, smc_data: dict = None) -> dict:
    """
    Master evaluator using the Single Continuous Hermes Pipeline.
    Combines all context (Fundamental, Macro, Scalping DOM) into one prompt.
    """
    symbol = active_symbol
    risk_profile = get_symbol_risk_profile(symbol)
    
    if broadcast_callback:
        coro = broadcast_callback({
            "type": "hermes_activity",
            "agent_status": "assembling_context",
            "message": f"Fetching full DOM and Macro context for {symbol}..."
        })
        if asyncio.iscoroutine(coro):
            asyncio.create_task(coro)

    print(f"[EVAL] Initiating 3-Agent Parallel Swarm for {symbol}...")

    # Fetch FRED Macroeconomic Data
    from core.exchange import fetch_fred_macro_data
    fred_data = await fetch_fred_macro_data()
    macro_context = f"US 10-Year Yield (DGS10) = {fred_data['dgs10']}%, Latest CPI = {fred_data['cpi']}"

    # 1. CLAW Prompt (Institutional SMC - Complex -> Hermes/NVIDIA)
    claw_prompt = f"""You are Antigravity CLAW, the Institutional SMC Agent.
Asset: {symbol} | Type: {risk_profile['class']}
Context: {market_data_text}
Macro Context: {macro_context}
Memory: {memory_text}
Task: Perform deep Fundamental & Smart Money Concepts (SMC) analysis. Look for liquidity sweeps and institutional alignment. Filter liquidity sweeps against these fundamental flows.
Output strictly JSON: {{"decision": "BUY"|"SELL"|"HOLD", "confidence": <0-100>, "leverage": <1-20>, "stop_loss_pct": <float>, "take_profit_pct": <float>, "reasoning": "..."}}"""

    # 2. MACRO Prompt (News & Sentiment - Simple -> LM Studio)
    macro_prompt = f"""You are Antigravity MACRO, the News & Sentiment Agent.
Asset: {symbol}
Context: {market_data_text}
Task: Analyze multi-timeframe trends, moving averages, and forex news sentiment.
Output strictly JSON: {{"decision": "BUY"|"SELL"|"HOLD", "confidence": <0-100>, "reasoning": "..."}}"""

    # 3. SCALPER Prompt (Orderbook/DOM - Fast -> LM Studio)
    scalper_prompt = f"""You are Antigravity SCALPER, the Orderbook DOM Agent.
Asset: {symbol} | Live Price: {live_asset_price}
DOM Data: {dom_data}
Task: Analyze Level 2 Orderbook imbalances (OFI, VPIN) for sniper entry points. Focus on toxic orderflow.
Output strictly JSON: {{"decision": "BUY"|"SELL"|"HOLD", "confidence": <0-100>, "entry_price": <float>, "reasoning": "..."}}"""

    # Launch the parallel swarm
    async def run_claw():
        payload = {"messages": [{"role": "user", "content": claw_prompt}]}
        return await call_hermes_gateway(payload, broadcast_callback, session_name="apex_claw")

    async def run_macro():
        await asyncio.sleep(0.5) # Stagger
        return await call_hermes_gateway({"messages": [{"role": "user", "content": macro_prompt}]}, broadcast_callback, session_name="apex_macro")

    async def run_scalper():
        await asyncio.sleep(1.0) # Stagger
        return await call_hermes_gateway({"messages": [{"role": "user", "content": scalper_prompt}]}, broadcast_callback, session_name="apex_scalper")

    if broadcast_callback:
        coro = broadcast_callback({
            "type": "hermes_activity",
            "agent_status": "generating_strategy",
            "message": "3-Agent Swarm deployed. Awaiting consensus..."
        })
        if asyncio.iscoroutine(coro): asyncio.create_task(coro)

    # Gather results concurrently
    claw_res, macro_res, scalper_res = await asyncio.gather(run_claw(), run_macro(), run_scalper())

    # Weighted Consensus Logic
    claw_dec = claw_res.get("decision", "HOLD").upper()
    macro_dec = macro_res.get("decision", "HOLD").upper()
    scalper_dec = scalper_res.get("decision", "HOLD").upper()

    decisions = [claw_dec, macro_dec, scalper_dec]
    
    def score_decision(d):
        if d == "BUY": return 1.0
        if d == "SELL": return -1.0
        return 0.0

    # Weights: CLAW (50%), MACRO (25%), SCALPER (25%)
    net_score = (score_decision(claw_dec) * 0.50) + \
                (score_decision(macro_dec) * 0.25) + \
                (score_decision(scalper_dec) * 0.25)
    
    # Thresholds: +/- 0.40 required to override HOLD
    if net_score >= 0.40:
        final_decision = "BUY"
    elif net_score <= -0.40:
        final_decision = "SELL"
    else:
        final_decision = "HOLD"

    avg_conf = (
        safe_int(claw_res.get("confidence", 0), 0, 0, 100) +
        safe_int(macro_res.get("confidence", 0), 0, 0, 100) +
        safe_int(scalper_res.get("confidence", 0), 0, 0, 100)
    ) // 3

    sl_pct, tp_pct, _ = clamp_risk_to_symbol(symbol, claw_res.get("stop_loss_pct", risk_profile["sl"]), claw_res.get("take_profit_pct", risk_profile["tp"]))
    
    # --- SWEEP SL OVERRIDE (CHALLENGE MODE 1:10 R:R) ---
    if smc_data and smc_data.get("sweep_detected"):
        anchor = smc_data.get("sweep_sl_anchor", 0.0)
        direction = smc_data.get("sweep_direction", "NONE")
        if anchor > 0 and live_asset_price > 0 and final_decision == direction:
            distance = abs(live_asset_price - anchor)
            dynamic_sl_pct = (distance / live_asset_price) * 100.0
            # Add a microscopic buffer (0.01%) above the wick
            sl_pct = round(dynamic_sl_pct + 0.01, 3)
            # Enforce 1:10 Risk-to-Reward minimum for Turtle Soup setups
            tp_pct = round(sl_pct * 10.0, 3)
            print(f"[JUDAS SWING] SL strictly pegged to wick anchor {anchor}. R:R mapped to 1:10 (TP {tp_pct}%)")

    ai_leverage = safe_int(claw_res.get("leverage", 10), 10, 1, 20)
    
    buys = decisions.count("BUY")
    sells = decisions.count("SELL")
    reasoning_summary = f"Consensus: {buys} BUY, {sells} SELL.\n\n[CLAW - SMC Analysis]: {decisions[0]}\n{claw_res.get('reasoning', '')}\n\n[MACRO - Trend Analysis]: {decisions[1]}\n{macro_res.get('reasoning', '')}\n\n[SCALPER - DOM Analysis]: {decisions[2]}\n{scalper_res.get('reasoning', '')}"
    
    print(f"[SWARM] Final Consensus: {final_decision} ({avg_conf}%) | SL {sl_pct}% | TP {tp_pct}%")
    
    if broadcast_callback:
        coro = broadcast_callback({
            "type": "hermes_activity",
            "agent_status": "idle",
            "message": f"Consensus Reached: {final_decision} ({avg_conf}%)",
            "reasoning_chunk": f"\n\n--- FINAL SWARM REPORT ---\n{reasoning_summary}"
        })
        if asyncio.iscoroutine(coro): asyncio.create_task(coro)

    return {
        "action": final_decision,
        "confidence": avg_conf,
        "leverage": ai_leverage,
        "stop_loss": sl_pct,
        "take_profit": tp_pct,
        "volatility": "high" if avg_conf < 50 else "medium",
        "entry_price": scalper_res.get("entry_price", live_asset_price),
        "_debug": {
            "hermes_reasoning": reasoning_summary
        }
    }
def is_aplus_setup(market_data_text: str, trend_bias: dict, live_price: float, symbol: str, timestamp_str: str = "", smc_proximity_pct: float = 0.0015, ofi: float = 0.0, vpin: float = 0.0, vpin_side: str = "BALANCED", sweep_result: dict = None) -> tuple[bool, str]:
    """
    Mathematical Gatekeeper: Only allows A+ Setups to pass to the LLM.
    0. CHALLENGE_MODE Gate: Institutional Liquidity Sweep must be confirmed.
    1. Killzone Filter: Must be within London or NY session.
    2. Trend Alignment: 1H and 4H scores must both be >= 30 (LONG) or <= -30 (SHORT).
    3. R:R Ratio: Dynamic TP must be >= 1.5x Dynamic SL.
    4. SMC Proximity: Live price must be within 0.15% of an Institutional OB/FVG.
    """
    from core.macro_sensors import get_smc_killzone
    
    # 0. Killzone Check (strict New York time)
    kz_active, kz_name = get_smc_killzone()
    if not kz_active:
        return False, f"Price action outside Institutional Killzones ({kz_name})."

    # 0b. CHALLENGE_MODE: Institutional Liquidity Sweep Hard Gate
    # When active, NO trades pass unless a confirmed sweep (Turtle Soup / Judas Swing)
    # has been detected. This enforces extreme R/R asymmetry for the GoatFunded challenge.
    if CHALLENGE_MODE:
        if sweep_result is None or not sweep_result.get("sweep_detected", False):
            sweep_details = sweep_result.get("details", "No sweep data provided") if sweep_result else "Sweep result not passed to gatekeeper"
            return False, f"CHALLENGE_MODE: No Institutional Liquidity Sweep detected. {sweep_details}"
        else:
            sweep_dir = sweep_result.get("direction", "NONE")
            sweep_sl = sweep_result.get("stop_loss_anchor", 0.0)
            print(f"[A+ CHALLENGE] ✅ Liquidity Sweep CONFIRMED: {sweep_dir} | SL Anchor: {sweep_sl:.5f} | {sweep_result.get('details', '')}")

            # Drawdown Limit Rejection: Compute the SL % from sweep anchor to live price.
            # If the distance exceeds GoatFunded's max drawdown, reject the trade.
            if live_price > 0 and sweep_sl > 0:
                if sweep_dir == "SHORT":
                    sweep_sl_pct = abs(sweep_sl - live_price) / live_price * 100
                else:  # LONG
                    sweep_sl_pct = abs(live_price - sweep_sl) / live_price * 100
                asset_limits = get_asset_limits(symbol)
                if sweep_sl_pct > GOATFUNDED_MAX_DRAWDOWN_PCT:
                    return False, (f"DRAWDOWN LIMIT BREACH: Sweep SL anchor requires {sweep_sl_pct:.2f}% risk "
                                   f"(exceeds GoatFunded max {GOATFUNDED_MAX_DRAWDOWN_PCT}% drawdown). "
                                   f"Asset: {asset_limits['asset_class']} | SL Anchor: {sweep_sl:.5f} | Price: {live_price:.5f}")
                print(f"[RISK-MANAGER] Dynamic Risk Clamping Active: {asset_limits['asset_class']} | "
                      f"Sweep SL: {sweep_sl_pct:.2f}% (limit: {GOATFUNDED_MAX_DRAWDOWN_PCT}%)")

    if live_price <= 0:
        return True, ""  # Skip if live price is unavailable (fallback)

    # 1. Parse Dynamic Risk/Reward
    import re
    dyn_sl_match = re.search(r"Dynamic SL distance is ([\d\.]+)%", market_data_text)
    dyn_tp_match = re.search(r"Dynamic TP distance is ([\d\.]+)%", market_data_text)
    
    if dyn_sl_match and dyn_tp_match:
        dyn_sl = float(dyn_sl_match.group(1))
        dyn_tp = float(dyn_tp_match.group(1))
        rr = dyn_tp / dyn_sl if dyn_sl > 0 else 0
        if rr < 1.5:
            return False, f"Insufficient Dynamic R:R ({rr:.2f} < 1.5)"

    # 2. Trend Alignment (1H Structure Gatekeeper)
    per_tf = trend_bias.get("per_tf", {})
    score_1h = per_tf.get("1h", 0)
    score_4h = per_tf.get("4h", 0)

    # Determine structural direction. Strict macro alignment is preferred, but the
    # green-circle entry happens before 4H fully catches up, so a proven M15 pullback
    # continuation can wake the agents early when H1 is not fighting the trade.
    weighted = trend_bias.get("score", 0)
    early_entry = {"pass": False, "reason": "Not checked"}
    
    if weighted >= 15 and score_1h >= 10:
        target_dir = "LONG"
    elif weighted <= -15 and score_1h <= -10:
        target_dir = "SHORT"
    else:
        try:
            from core.macro_sensors import get_early_trend_continuation
            if weighted >= 12 and score_1h >= 0:
                early_entry = get_early_trend_continuation(symbol, "BUY")
                if early_entry.get("pass"):
                    print(f"[A+ EARLY WAKE] BUY pullback continuation accepted before full 4H confirmation: {early_entry.get('reason')}")
                    return True, ""
            elif weighted <= -12 and score_1h <= 0:
                early_entry = get_early_trend_continuation(symbol, "SELL")
                if early_entry.get("pass"):
                    print(f"[A+ EARLY WAKE] SELL pullback continuation accepted before full 4H confirmation: {early_entry.get('reason')}")
                    return True, ""
        except Exception as early_err:
            early_entry = {"pass": False, "reason": str(early_err)}
        return False, f"1H Market Structure Mismatch or Weak Macro Trend (Weighted: {weighted:+.0f}, 1H: {score_1h:+d}, 4H: {score_4h:+d}) | Early: {early_entry.get('reason')}"

    # 2b. Order Flow Imbalance (OFI) Hard Gate — reject toxic liquidity traps
    if target_dir == "LONG" and ofi < -500:
        return False, f"Toxic Order Flow Imbalance Detected (OFI: {ofi:+.0f} < -500 while targeting LONG)"
    if target_dir == "SHORT" and ofi > 500:
        return False, f"Toxic Order Flow Imbalance Detected (OFI: {ofi:+.0f} > +500 while targeting SHORT)"

    # 2c. VPIN Hard Gate — reject when informed traders are aggressively absorbing liquidity
    if vpin >= 0.70:
        return False, f"VPIN Toxic Flow Detected (VPIN: {vpin:.3f} >= 0.70 threshold). Informed institutional absorption in progress."
    # Directional mismatch: elevated VPIN with dominant side opposing the trade
    if vpin >= 0.50:
        if target_dir == "LONG" and vpin_side == "SELL":
            return False, f"VPIN Directional Conflict (VPIN: {vpin:.3f}, Dominant: SELL while targeting LONG)"
        if target_dir == "SHORT" and vpin_side == "BUY":
            return False, f"VPIN Directional Conflict (VPIN: {vpin:.3f}, Dominant: BUY while targeting SHORT)"

    # 3. SMC Proximity Check
    bullish_levels = []
    bearish_levels = []
    
    bullish_fvg = re.search(r"Nearest Bullish FVG.*(?:mid|to) ([\d\.]+)", market_data_text)
    if bullish_fvg: bullish_levels.append(float(bullish_fvg.group(1).replace(',', '')))
        
    bearish_fvg = re.search(r"Nearest Bearish FVG.*(?:mid|to) ([\d\.]+)", market_data_text)
    if bearish_fvg: bearish_levels.append(float(bearish_fvg.group(1).replace(',', '')))
        
    bullish_ob = re.search(r"Nearest Bullish OB.*to ([\d\.]+)", market_data_text)
    if bullish_ob: bullish_levels.append(float(bullish_ob.group(1).replace(',', '')))
        
    bearish_ob = re.search(r"Nearest Bearish OB.*to ([\d\.]+)", market_data_text)
    if bearish_ob: bearish_levels.append(float(bearish_ob.group(1).replace(',', '')))

    # Check distance to the appropriate levels
    target_levels = bullish_levels if target_dir == "LONG" else bearish_levels
    if not target_levels:
        try:
            from core.macro_sensors import get_early_trend_continuation
            early_entry = get_early_trend_continuation(symbol, "BUY" if target_dir == "LONG" else "SELL")
            if early_entry.get("pass"):
                print(f"[A+ EARLY WAKE] No SMC level, but pullback continuation is clean: {early_entry.get('reason')}")
                return True, ""
        except Exception:
            pass
        return False, "No Institutional SMC levels (OB/FVG) detected to support entry. Blocking FOMO."
        
    closest_dist_pct = min(abs(live_price - lvl) / live_price for lvl in target_levels)
    
    # Instrument-aware strike zone: Metals need wider tolerance due to high candle volatility
    _sym_upper = symbol.upper()
    is_metal = any(m in _sym_upper for m in ("GOLD", "XAU", "SILVER", "XAG", "US30", "DJ30"))
    proximity_buffer = 0.0080 if is_metal else 0.0040
    
    if closest_dist_pct > proximity_buffer:
        side_str = "Demand/Support" if target_dir == "LONG" else "Supply/Resistance"
        try:
            from core.macro_sensors import get_early_trend_continuation
            early_entry = get_early_trend_continuation(symbol, "BUY" if target_dir == "LONG" else "SELL")
            if early_entry.get("pass"):
                print(f"[A+ EARLY WAKE] SMC level is {closest_dist_pct*100:.2f}% away, but pullback continuation is clean: {early_entry.get('reason')}")
                return True, ""
        except Exception:
            pass
        return False, f"Price not in Institutional Strike Zone (Nearest {side_str} is {closest_dist_pct*100:.2f}% away, limit {proximity_buffer*100:.2f}%)"

    return True, ""
