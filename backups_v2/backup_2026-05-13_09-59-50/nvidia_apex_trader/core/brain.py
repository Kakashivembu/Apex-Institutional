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
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Build rotation pool of NVIDIA keys
NVIDIA_KEYS = [k for k in [NVIDIA_API_KEY, NVIDIA_API_KEY_2] if k]
print(f"[BRAIN] Loaded {len(NVIDIA_KEYS)} NVIDIA API key(s) for rotation")

# NVIDIA API rate limiting (40 RPM)
last_nvidia_call = 0
RATE_LIMIT_DELAY = 1.5 # 1.5 seconds between calls (40 RPM = 1.5s per call)

# Track 429 errors for exponential backoff
# Memory limits
MAX_MEMORY_MESSAGES = 10
FLIGHT_RECORDER_FILE = "apex_flight_state.json"
GLOBAL_COOLDOWNS = {}
rate_limit_error_count = 0
last_rate_limit_time = 0

# =============================================================================
# GLOBAL NVIDIA NIM RATE LIMITER (Token Bucket per API key)
# =============================================================================
# NVIDIA limit: 40 RPM. We enforce 30 RPM to leave 25% headroom and avoid bans.
NVIDIA_RPM_LIMIT = 30          # Hard cap: 30 calls per minute per key
NVIDIA_MIN_GAP = 2.5           # Minimum 2.5 seconds between calls on same key
NVIDIA_CALL_LOG = {}           # {api_key: [timestamps]}  rolling 60s window
NVIDIA_LAST_CALL_PER_KEY = {}  # {api_key: last_timestamp}

import threading
_nvidia_lock = threading.Lock()

def _wait_for_nvidia_rate_limit(api_key: str):
    """Global pre-flight rate limiter. Sleeps proactively if key is near limit."""
    global NVIDIA_CALL_LOG, NVIDIA_LAST_CALL_PER_KEY
    now = time.time()
    with _nvidia_lock:
        # 1. Enforce minimum gap between calls on the same key
        last = NVIDIA_LAST_CALL_PER_KEY.get(api_key, 0)
        gap = now - last
        if gap < NVIDIA_MIN_GAP:
            sleep_needed = NVIDIA_MIN_GAP - gap
            print(f"[NVIDIA-RATE-LIMITER] Key gap too short ({gap:.2f}s < {NVIDIA_MIN_GAP}s). Sleeping {sleep_needed:.2f}s...")
            time.sleep(sleep_needed)
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
                time.sleep(sleep_needed)
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

LOCAL_LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"

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


async def get_market_sentiment(nvidia_keys: list, sanity_alert: str = "", symbol: str = "GOLD", market_data_text: str = "") -> dict:
    """AGENT 1: The Liquidation & Whale Hunter - Feeds real MT5 Macro Data to AI.
    Native NVIDIA NIM integration."""
    
    if not market_data_text:
        print("[CLAW] Fetching MT5 Macro Sensors...")
        from core.macro_sensors import calculate_currency_matrix, detect_tick_velocity

        matrix_data, velocity_data = await asyncio.gather(
            calculate_currency_matrix(),
            detect_tick_velocity(symbol)
        )
        matrix_text = f"Currency Matrix (0-100 Relative Strength): Strongest: {matrix_data['strongest']}, Weakest: {matrix_data['weakest']}"
        velocity_text = f"Tick Velocity (1M scale): High Velocity: {velocity_data['is_high_velocity']}, Ratio: {velocity_data['ratio']}x"
        context_text = f"{matrix_text}\n{velocity_text}"
        liquidity_data_str = f"{matrix_text} | {velocity_text}"
    else:
        context_text = market_data_text
        liquidity_data_str = "Backtest Mode - Synthetic Context Provided"

    system_prompt = f"""You are an institutional quantitative global macro tracker for Forex/Metals.
Analyze the following live macro, tick-velocity, and market data for {symbol}.
Determine if directional pressure favors upside, downside, or neutrality.
Return ONLY a valid JSON object with exactly this structure:
{{
    "sentiment": "BULLISH" or "BEARISH" or "NEUTRAL",
    "confidence": 0-100,
    "squeeze_risk": "HIGH" or "MEDIUM" or "LOW",
    "dominant_side": "LONG" or "SHORT" or "BALANCED",
    "summary": "1-2 sentences."
}}"""

    user_prompt = f"""{sanity_alert}Act as an institutional quantitative tracker. Analyze:
{context_text}
Return valid JSON with sentiment (BULLISH/BEARISH/NEUTRAL), confidence (0-100), squeeze_risk (HIGH/MEDIUM/LOW), dominant_side (LONG/SHORT/BALANCED), and a 1-2 sentence summary.

[EXECUTION_CYCLE_ID: {time.time()}]"""

    payload = {
        "model": "meta/llama-3.1-70b-instruct",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 150,
        "response_format": {"type": "json_object"}
    }

    max_retries = 2
    for attempt in range(max_retries + 1):
        active_key = nvidia_keys[attempt % len(nvidia_keys)] if nvidia_keys else NVIDIA_API_KEY
        headers = {
            "Authorization": f"Bearer {active_key}",
            "Content-Type": "application/json"
        }
        
        try:
            print(f"[CLAW] Routing Fundamental Analysis directly to NVIDIA NIM...")
            response = await asyncio.to_thread(
                fetch_nvidia_sync,
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers,
                payload
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                
                clean_content = content.replace("```json", "").replace("```", "").strip()

                try:
                    parsed = json.loads(clean_content)
                    sentiment = parsed.get("sentiment", "NEUTRAL").upper()
                    confidence = int(parsed.get("confidence", 50))
                    squeeze_risk = parsed.get("squeeze_risk", "MEDIUM").upper()
                    dominant_side = parsed.get("dominant_side", "BALANCED").upper()
                    report = parsed.get("summary", "No summary available")

                    if sentiment == "BULLISH":
                        bullish_pct, bearish_pct, neutral_pct = max(60, confidence), max(10, 100 - confidence - 20), 20
                    elif sentiment == "BEARISH":
                        bullish_pct, bearish_pct, neutral_pct = max(10, 100 - confidence - 20), max(60, confidence), 20
                    else:
                        bullish_pct, bearish_pct, neutral_pct = 33, 33, 34

                    print(f"[CLAW] Sentiment: {sentiment} ({confidence}%) | Squeeze: {squeeze_risk} | Side: {dominant_side}")
                    print(f"[CLAW] Report: {report}")

                    return {
                        "sentiment": sentiment,
                        "confidence": confidence,
                        "bullish_pct": bullish_pct,
                        "bearish_pct": bearish_pct,
                        "neutral_pct": neutral_pct,
                        "report": report,
                        "liquidity_data": liquidity_data_str,
                        "squeeze_risk": squeeze_risk,
                        "dominant_side": dominant_side
                    }
                except json.JSONDecodeError:
                    print(f"[CLAW] JSON Decode Error. Content: {clean_content}")
                    pass
            elif response.status_code == 401:
                print("[CLAW] HTTP 401 Unauthorized - check NVIDIA Fundamental Desk key in AI Brain Fleet.")
                return {
                    "sentiment": "NEUTRAL", "confidence": 50,
                    "squeeze_risk": "LOW", "dominant_side": "BALANCED",
                    "bullish_pct": 33, "bearish_pct": 33, "neutral_pct": 34,
                    "report": "Fundamental analysis disabled: NVIDIA authentication failed (401).",
                    "liquidity_data": liquidity_data_str
                }
            elif response.status_code in (502, 503, 429) and attempt < max_retries:
                if getattr(response, "text", "") in ("Circuit breaker open", "All retries exhausted"):
                    print("[CLAW] API Circuit breaker is active. Bypassing retries.")
                    break
                wait_time = 3 * (attempt + 1)
                print(f"[CLAW] HTTP {response.status_code} - Retry {attempt+1}/{max_retries} in {wait_time}s...")
                await asyncio.sleep(wait_time)
                continue
            else:
                print(f"[CLAW] HTTP {response.status_code}")
                pass
        except requests.exceptions.Timeout:
            if attempt < max_retries:
                print(f"[CLAW] Timeout - Retry {attempt+1}/{max_retries}...")
                await asyncio.sleep(3)
                continue
            print("[CLAW] Timeout error (all retries exhausted)")
            pass
        except requests.exceptions.RequestException as e:
            print(f"[CLAW] Request error: {e}")
            pass
        except Exception as e:
            if attempt < max_retries:
                print(f"[CLAW] NVIDIA Error: {e} - Retry {attempt+1}/{max_retries}...")
                await asyncio.sleep(3)
                continue
            print(f"[CLAW] NVIDIA fallback error: {e}")
            pass

    print(f"[CLAW] Fundamental analysis offline or failed.")
    return {
        "sentiment": "NEUTRAL", "confidence": 50,
        "squeeze_risk": "LOW", "dominant_side": "BALANCED",
        "bullish_pct": 33, "bearish_pct": 33, "neutral_pct": 34,
        "report": "Fundamental analysis offline due to API failure.",
        "liquidity_data": liquidity_data_str
    }

def execute_local_fallback(payload: dict) -> requests.Response:
    print(f"[LOCAL-FALLBACK] NVIDIA API unavailable. Routing to LM Studio (RTX 4060)...")
    try:
        messages = payload.get("messages", [])
        prompt = "\n".join([m.get("content", "") for m in messages])
        fallback_payload = {
            "messages": [
                {
                    "role": "system",
                    "content": "You are the Apex Scalper Agent. You are a quantitative machine. You MUST output ONLY raw, valid JSON. Do not include markdown formatting, backticks, or conversational text. Your output must match this exact schema: {\"direction\": \"BUY\", \"confidence\": 85, \"reasoning\": \"string\"}"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,
            "max_tokens": 800
        }
        response = requests.post(LOCAL_LLM_URL, json=fallback_payload, timeout=120)
        return response
    except Exception as e:
        print(f"[LOCAL-FALLBACK] LM Studio fallback failed: {e}. Defaulting to HOLD to prevent zombie retries.")
        class FakeResponse:
            status_code = 200
            text = "Local fallback GPU timeout or crash"
            def json(self):
                return {
                    "choices": [{
                        "message": {
                            "content": '{"direction": "HOLD", "confidence": 0, "reasoning": "Local fallback GPU timeout or crash. Defaulting to HOLD."}'
                        }
                    }]
                }
        return FakeResponse()

def fetch_nvidia_sync(url: str, headers: dict, payload: dict, max_retries: int = 3) -> requests.Response:
    """Synchronous NVIDIA API call using requests (runs in thread pool)
    Implements retry with exponential backoff on 429 Rate Limit errors.
    Circuit breaker prevents repeated calls when API is down.

    FIX: rate_limit_error_count now RESETS on success. Previously it never
    reset, causing a permanent 4s+ backoff sleep on every call after a single 429.
    Timeouts are no longer treated as rate limit errors (they're network issues).
    """
    global last_nvidia_call, rate_limit_error_count, last_rate_limit_time
    global nvidia_circuit_broken, nvidia_circuit_failure_count, nvidia_circuit_last_failure

    current_time = time.time()

    # CIRCUIT BREAKER: Check if circuit is open
    if nvidia_circuit_broken:
        if current_time - nvidia_circuit_last_failure >= NVIDIA_CIRCUIT_COOLDOWN:
            print(f"[NVIDIA] Circuit breaker testing API availability...")
            nvidia_circuit_broken = False  # Allow one test call
        else:
            print(f"[NVIDIA] Circuit breaker OPEN — API calls skipped for {NVIDIA_CIRCUIT_COOLDOWN - int(current_time - nvidia_circuit_last_failure)}s")
            return execute_local_fallback(payload)

    for attempt in range(max_retries):
        current_time = time.time()

        # ── GLOBAL PRE-FLIGHT RATE LIMITER ──
        # Extract API key from headers for per-key tracking
        api_key = headers.get("Authorization", "").replace("Bearer ", "").strip()
        if api_key:
            _wait_for_nvidia_rate_limit(api_key)
        else:
            # Fallback: enforce minimum delay if no key found
            elapsed = current_time - last_nvidia_call
            if elapsed < NVIDIA_MIN_GAP:
                time.sleep(NVIDIA_MIN_GAP - elapsed)
            last_nvidia_call = time.time()

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=25, verify=False)
        except requests.exceptions.Timeout:
            # Timeouts are NOT rate limit errors — track as circuit failure
            print(f"[NVIDIA] Timeout. Bypassing retries and triggering immediate local fallback.")
            nvidia_circuit_failure_count += 1
            nvidia_circuit_last_failure = time.time()
            return execute_local_fallback(payload)

        # Handle 429 errors with exponential backoff + jitter
        if response.status_code == 429:
            rate_limit_error_count += 1
            import random
            jitter = random.uniform(0.5, 2.0)  # Random 0.5-2.0s to prevent thundering herd
            sleep_time = min(15, (2 ** attempt) + jitter)
            print(f"[NVIDIA] Rate limited (429)! Error count: {rate_limit_error_count}. Retrying in {sleep_time:.1f}s (jitter: {jitter:.1f}s)...")
            time.sleep(sleep_time)
            continue

        # SUCCESS: Reset backoff state and circuit breaker so future calls don't sleep needlessly
        if response.status_code == 200:
            if rate_limit_error_count > 0:
                print(f"[NVIDIA] Success after {rate_limit_error_count} previous 429 errors — backoff cleared")
                rate_limit_error_count = 0
            if nvidia_circuit_failure_count > 0:
                print(f"[NVIDIA] Circuit breaker closed after {nvidia_circuit_failure_count} failures")
                nvidia_circuit_failure_count = 0
            return response

        # Other HTTP errors - track as circuit failure
        if response.status_code >= 500:
            nvidia_circuit_failure_count += 1
            nvidia_circuit_last_failure = time.time()
            print(f"[NVIDIA] Server error {response.status_code}, failure count: {nvidia_circuit_failure_count}")

        return response

    # If we exhausted all retries, track as circuit failure
    nvidia_circuit_failure_count += 1
    nvidia_circuit_last_failure = time.time()
    print(f"[NVIDIA] All {max_retries} retries exhausted — circuit failure count: {nvidia_circuit_failure_count}")

    # Open circuit if threshold reached
    if nvidia_circuit_failure_count >= NVIDIA_CIRCUIT_THRESHOLD:
        print(f"[NVIDIA] CIRCUIT BREAKER OPENED — API disabled for {NVIDIA_CIRCUIT_COOLDOWN}s")
        nvidia_circuit_broken = True

    return execute_local_fallback(payload)

def get_optimized_parameters(symbol: str):
    # OBSOLETE: Replaced by Dynamic ATR Volatility Engine
    return None, None

async def analyze_macro_trend(nvidia_key: str, sentiment_report: str, candle_1h: str, candle_4h: str, trading_memory: str = "", sanity_alert: str = "", symbol: str = "GOLD", trend_bias_text: str = "NEUTRAL (+0)") -> dict:
    """AGENT 2: The Macro Trend Follower (NVIDIA NIM) - Using requests + asyncio.to_thread"""
    if not nvidia_key:
        return {"decision": "HOLD", "confidence": 0, "reasoning": "No NVIDIA API key"}

    memory_section = (f"""\n\nCRITICAL DIRECTIVES FROM HISTORICAL MEMORY:
{trading_memory[:1500] if trading_memory else 'No historical lessons recorded.'}
\nYou MUST obey any lessons regarding trend alignment, risk-reward ratios, or timeframe conflicts.""" if trading_memory else "")

    system_prompt = f"""You are a Macro Trend Follower AI analyzing global macro Forex/Metals markets ({symbol}).

TREND HIERARCHY (in order of importance):
1. 4H TREND is the PRIMARY signal — this is the dominant market direction
2. 1H TREND confirms or warns of divergence from 4H
3. EMA 9/21 CROSS on 1H and 4H — golden cross = bullish, death cross = bearish
4. MOMENTUM SCORE — positive = upward pressure, negative = downward pressure

SMART MONEY CONCEPTS (SMC) — INSTITUTIONAL PRICE LEVELS:
- FAIR VALUE GAPS (FVG): Unfilled 3-candle vacuum zones. Bullish FVGs are support magnets. Bearish FVGs are resistance magnets.
- ORDER BLOCKS (OB): Institutional supply/demand zones. Bullish OB = demand zone below price. Bearish OB = supply zone above price.
- If Bullish FVGs or OBs exist below current price, they act as NEAREST SUPPORT. If Bearish FVGs or OBs exist above current price, they act as NEAREST RESISTANCE.
- USE THESE LEVELS to assess risk: if entering LONG, the nearest Bullish OB/FVG below price is your logical stop-loss floor. If entering SHORT, the nearest Bearish OB/FVG above price is your logical stop-loss ceiling.

CRITICAL RULES:
- CRITICAL RULE: The current mathematical trend is {trend_bias_text}. You are a Trend-Following algorithm. You are strictly forbidden from predicting reversals or 'calling the top/bottom' against this trend. If the trend is Bullish, you must look for BUY setups or HOLD. If Bearish, SELL or HOLD.
- ICT SWEEP RULE: If liquidity-sweep evidence conflicts with {trend_bias_text}, choose HOLD rather than calling a reversal against the mathematical trend.
- ANTI-CONTRARIAN RULE: If the 4H Trend Score is above +30, you MUST vote BUY unless you have 90%+ confidence in a specific reversal catalyst.
- ANTI-CONTRARIAN RULE: If the 4H Trend Score is below -30, you MUST vote SELL unless you have 90%+ confidence in a specific reversal catalyst.
- MOMENTUM ALIGNMENT: If EMA9 is above EMA21 on both 1H and 4H, the trend is UP — align with it. If EMA9 is below EMA21 on both, the trend is DOWN — align with it.

Leverage scaling: 85%+ confidence = 30x-50x. 70%-84% = 15x-30x. Below 70% = 5x-15x. Maximum leverage: 50x.

Respond ONLY in valid JSON format:
{{"decision": "BUY"|"SELL"|"HOLD", "confidence": 0-100, "volatility": "low"|"medium"|"high", "recommended_leverage": 1-50, "reasoning": "brief explanation citing which timeframe trends support your decision"}}{memory_section}"""

    user_prompt = f"""{sanity_alert}=== CLAW SENTIMENT REPORT ===
{sentiment_report}

=== 1H CANDLE DATA ===
{candle_1h}

=== 4H CANDLE DATA ===
{candle_4h}

Determine the macro trend direction based on the above data.

MATHEMATICAL TREND_BIAS: {trend_bias_text}

[EXECUTION_CYCLE_ID: {time.time()}]"""

    headers = {
        "Authorization": f"Bearer {nvidia_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "meta/llama-3.1-70b-instruct",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 500,
        "response_format": {"type": "json_object"}
    }

    max_retries = 2
    for attempt in range(max_retries + 1):
        # Rotate API key on each attempt
        active_key = NVIDIA_KEYS[attempt % len(NVIDIA_KEYS)] if NVIDIA_KEYS else nvidia_key
        rotated_headers = {
            "Authorization": f"Bearer {active_key}",
            "Content-Type": "application/json"
        }
        key_label = f"Key{(attempt % len(NVIDIA_KEYS)) + 1}" if NVIDIA_KEYS else "Default"
        try:
            print(f"[MACRO] Routing Macro Trend Analysis directly to NVIDIA NIM...")
            response = await asyncio.to_thread(
                fetch_nvidia_sync,
                "https://integrate.api.nvidia.com/v1/chat/completions",
                rotated_headers,
                payload
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                result = json.loads(content)
                decision = result.get("decision", "HOLD").upper()
                volatility = result.get("volatility", "medium")
                rec_leverage = min(50, max(1, int(result.get("recommended_leverage", 10))))
                print(f"[MACRO TREND] {decision} ({result.get('confidence', 0)}%) | Vol: {volatility} | Lev: {rec_leverage}x")
                return {
                    "decision": decision,
                    "confidence": result.get("confidence", 0),
                    "volatility": volatility,
                    "recommended_leverage": rec_leverage,
                    "reasoning": result.get("reasoning", "")
                }
            elif response.status_code in (502, 503, 429) and attempt < max_retries:
                if getattr(response, "text", "") in ("Circuit breaker open", "All retries exhausted"):
                    return {"decision": "HOLD", "confidence": 0, "reasoning": "Circuit breaker active"}
                wait_time = 3 * (attempt + 1)
                print(f"[MACRO] HTTP {response.status_code} ({key_label}) - Retry {attempt+1}/{max_retries} in {wait_time}s (switching key)...")
                await asyncio.sleep(wait_time)
                continue
            else:
                print(f"[MACRO] HTTP {response.status_code}: {response.text[:200]}")
                return {"decision": "HOLD", "confidence": 0, "reasoning": f"HTTP error: {response.status_code}"}
        except requests.exceptions.Timeout:
            if attempt < max_retries:
                print(f"[MACRO] Timeout - Retry {attempt+1}/{max_retries}...")
                await asyncio.sleep(3)
                continue
            print("[MACRO] Timeout error (all retries exhausted)")
            return {"decision": "HOLD", "confidence": 0, "reasoning": "Request timeout"}
        except requests.exceptions.RequestException as e:
            print(f"[MACRO] Request error: {e}")
            return {"decision": "HOLD", "confidence": 0, "reasoning": f"Connection error: {str(e)}"}
        except Exception as e:
            print(f"[MACRO] Error: {e}")
            return {"decision": "HOLD", "confidence": 0, "reasoning": str(e)}
    return {"decision": "HOLD", "confidence": 0, "reasoning": "All retries exhausted"}

async def find_sniper_entry(nvidia_key: str, candle_5m: str, live_price: float = 0, trading_memory: str = "", sanity_alert: str = "", symbol: str = "GOLD", trend_bias_text: str = "NEUTRAL (+0)") -> dict:
    """AGENT 3: The Scalper (NVIDIA NIM) - Using requests + asyncio.to_thread.
    Args:
        nvidia_key: NVIDIA API key for NIM access.
        candle_5m: Formatted market data string (contains Current Price from server.py).
        live_price: Explicit live symbol price from server.py stream.
        trading_memory: Injected historical lessons from APEX_MEMORY.md.
    """
    if not nvidia_key:
        return {"decision": "HOLD", "confidence": 0, "reasoning": "No NVIDIA API key"}

    if live_price > 0:
        current_price = live_price
        print(f"[SCALPER] {symbol} price provided: ${current_price:,.2f}")
    else:
        current_price = 0

    if current_price <= 0:
        print("[SCALPER] ERROR: current_price is 0! NVIDIA cannot calculate entry with $0 price.")
        return {"decision": "HOLD", "confidence": 0, "entry_price": "", "reasoning": f"Live {symbol} price unavailable", "stop_loss_pct": 1.5, "take_profit_pct": 4.0, "leverage": 10}

    mem = trading_memory[:1500] if trading_memory else ""
    if mem:
        memory_section = "\n\nCRITICAL DIRECTIVES FROM HISTORICAL MEMORY:\n" + mem + "\nYou MUST obey any lessons regarding timeframe alignment, risk-reward ratios, or trade conflicts mentioned above."
    else:
        memory_section = ""

    system_prompt = (
        f"You are an Elite Scalper AI specializing in global macro scalping ({symbol}) for Forex/Metals. "
        f"The current live {symbol} price is ${current_price:,.2f}. "
        "Based on this exact price, calculate precise entry, stop loss, and take profit levels for a scalp trade. "
        "\n\nTREND ALIGNMENT RULES (MANDATORY):"
        f"\n- CRITICAL RULE: The current mathematical trend is {trend_bias_text}. You are a Trend-Following algorithm. You are strictly forbidden from predicting reversals or 'calling the top/bottom' against this trend. If the trend is Bullish, you must look for BUY setups or HOLD. If Bearish, SELL or HOLD."
        "\n- BULLISH MOMENTUM: If 1H data shows 3+ consecutive green closes, EMA9 > EMA21, or Trend Score > +30 → you MUST vote BUY. Do NOT vote SELL into bullish momentum."
        "\n- BEARISH MOMENTUM: If 1H data shows 3+ consecutive red closes, EMA9 < EMA21, or Trend Score < -30 → you MUST vote SELL. Do NOT vote BUY into bearish momentum."
        "\n- ANTI-KNIFE RULE (BOTH DIRECTIONS): Never fight strong momentum in EITHER direction. Do not short rallies. Do not buy crashes."
        "\n\nINSTITUTIONAL SMC PRECISION RULES (MANDATORY):"
        f"\n- ICT SWEEP RULE: If liquidity-sweep evidence conflicts with {trend_bias_text}, choose HOLD rather than calling a reversal against the mathematical trend."
        "\n- The market data below contains exact Fair Value Gap (FVG) and Order Block (OB) price levels detected by institutional algorithms."
        "\n- DYNAMIC VOLATILITY OVERRIDE: The market data now contains 'LIVE VOLATILITY ALIGNMENT'. You MUST strictly use the Recommended Dynamic SL and TP percentages provided in the market data to set your exact stop_loss_pct and take_profit_pct. This ensures you survive current ATR volatility."
        "\n- For LONG setups: Ensure your STOP LOSS is placed using the recommended Dynamic SL percentage. This is mathematically calculated to sit 1.5x ATR below the nearest Bullish OB/FVG."
        "\n- For SHORT setups: Ensure your STOP LOSS is placed using the recommended Dynamic SL percentage. This is mathematically calculated to sit 1.5x ATR above the nearest Bearish OB/FVG."
        "\n- R:R TWEAK: Target 1:2.0 to 1:4.0 R:R on strong-trend setups. On ranging/consolidating charts, accept 1:1.5 minimum. Never take <1:1.5."
        "\n- If no 'LIVE VOLATILITY ALIGNMENT' data is present, fall back to standard 1.5% SL and 4.0% TP."
        "\n\nCRITICAL: You may vote HOLD when there is no trend-following setup. Do not force a counter-trend BUY or SELL."
        "\n\nLeverage: 85%+ confidence = 30x-50x. 70%-84% = 15x-30x. Below 70% = 5x-15x. Maximum: 50x."
        '\nOutput ONLY valid JSON: {"decision": "BUY"|"SELL"|"HOLD", "confidence": 0-100, '
        '"entry_price": calculated_entry_price_as_number, '
        '"stop_loss_pct": 0.5-3.0, "take_profit_pct": 1.5-10.0, "leverage": 1-50, "reasoning": "brief, cite trend data"}'
        + memory_section
    )
    user_prompt = (
        f"{sanity_alert}{symbol} live price: ${current_price:,.2f}. "
        f"MATHEMATICAL TREND_BIAS: {trend_bias_text}. "
        "Market data: " + candle_5m + ". "
        "Calculate exact entry price, SL (% from entry), TP (% from entry), and recommended leverage for a scalp. "
        "Return ONLY valid JSON with ALL fields: decision, confidence, entry_price, stop_loss_pct, take_profit_pct, leverage, reasoning."
        f"\n\n[EXECUTION_CYCLE_ID: {time.time()}]"
    )

    headers = {
        "Authorization": f"Bearer {nvidia_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "meta/llama-3.1-70b-instruct",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 500,
        "response_format": {"type": "json_object"}
    }

    max_retries = 2
    for attempt in range(max_retries + 1):
        # Rotate API key on each attempt
        active_key = NVIDIA_KEYS[attempt % len(NVIDIA_KEYS)] if NVIDIA_KEYS else nvidia_key
        rotated_headers = {
            "Authorization": f"Bearer {active_key}",
            "Content-Type": "application/json"
        }
        key_label = f"Key{(attempt % len(NVIDIA_KEYS)) + 1}" if NVIDIA_KEYS else "Default"
        try:
            print(f"[SCALPER] Executing short-term logic via NVIDIA NIM...")
            response = await asyncio.to_thread(
                fetch_nvidia_sync,
                "https://integrate.api.nvidia.com/v1/chat/completions",
                rotated_headers,
                payload
            )

            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                result = json.loads(content)
                decision = result.get("decision", "HOLD").upper()
                sl_pct = min(3.0, max(0.3, float(result.get("stop_loss_pct", 1.5))))
                tp_pct = min(10.0, max(0.5, float(result.get("take_profit_pct", 4.0))))
                ai_leverage = min(50, max(1, int(result.get("leverage", 10))))
                raw_entry = result.get("entry_price", "")
                try:
                    parsed_entry = float(raw_entry)
                except (TypeError, ValueError):
                    parsed_entry = 0.0
                entry_price = round(parsed_entry, 5) if parsed_entry > 0 else round(current_price, 5)
                confidence = result.get("confidence", 0)
                print(f"[SCALPER] {decision} @ {entry_price} ({confidence}%) | SL: {sl_pct}% | TP: {tp_pct}% | Lev: {ai_leverage}x")
                return {
                    "decision": decision,
                    "confidence": confidence,
                    "entry_price": entry_price,
                    "stop_loss_pct": sl_pct,
                    "take_profit_pct": tp_pct,
                    "leverage": ai_leverage,
                    "reasoning": result.get("reasoning", "")
                }
            elif response.status_code in (502, 503, 429) and attempt < max_retries:
                if getattr(response, "text", "") in ("Circuit breaker open", "All retries exhausted"):
                    return {"decision": "HOLD", "confidence": 0, "entry_price": "", "reasoning": "Circuit breaker active"}
                wait_time = 3 * (attempt + 1)
                print(f"[SCALPER] HTTP {response.status_code} ({key_label}) - Retry {attempt+1}/{max_retries} in {wait_time}s (switching key)...")
                await asyncio.sleep(wait_time)
                continue
            else:
                print(f"[SCALPER] HTTP {response.status_code}: {response.text[:200]}")
                return {"decision": "HOLD", "confidence": 0, "entry_price": "", "reasoning": f"HTTP error: {response.status_code}"}
        except requests.exceptions.Timeout:
            if attempt < max_retries:
                print(f"[SCALPER] Timeout - Retry {attempt+1}/{max_retries}...")
                await asyncio.sleep(3)
                continue
            print("[SCALPER] Timeout error (all retries exhausted)")
            return {"decision": "HOLD", "confidence": 0, "entry_price": "", "reasoning": "Request timeout"}
        except requests.exceptions.RequestException as e:
            print(f"[SCALPER] Request error: {e}")
            return {"decision": "HOLD", "confidence": 0, "entry_price": "", "reasoning": f"Connection error: {str(e)}"}
        except json.JSONDecodeError as e:
            print(f"[SCALPER] JSON parse error: {e} | Content: {content[:200] if 'content' in dir() else 'N/A'}")
            return {"decision": "HOLD", "confidence": 0, "entry_price": "", "reasoning": f"JSON parse error: {str(e)}"}
        except Exception as e:
            print(f"[SCALPER] Error: {e}")
            return {"decision": "HOLD", "confidence": 0, "entry_price": "", "reasoning": str(e)}
def is_aplus_setup(market_data_text: str, trend_bias: dict, live_price: float, symbol: str, timestamp_str: str = "", smc_proximity_pct: float = 0.0015) -> tuple[bool, str]:
    """
    Mathematical Gatekeeper: Only allows A+ Setups to pass to the LLM.
    1. Killzone Filter: Must be within London or NY session.
    2. Trend Alignment: 1H and 4H scores must both be >= 30 (LONG) or <= -30 (SHORT).
    3. R:R Ratio: Dynamic TP must be >= 1.5x Dynamic SL.
    4. SMC Proximity: Live price must be within 0.15% of an Institutional OB/FVG.
    """
    from core.macro_sensors import check_killzones
    
    # 0. Killzone Check
    if not check_killzones(timestamp_str):
        return False, "Price action outside Institutional Killzones."

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

    # Determine structural direction
    weighted = trend_bias.get("score", 0)
    
    if weighted >= 20 and score_1h >= 15 and score_4h >= 15:
        target_dir = "LONG"
    elif weighted <= -20 and score_1h <= -15 and score_4h <= -15:
        target_dir = "SHORT"
    else:
        return False, f"1H Market Structure Mismatch or Weak Macro Trend (Weighted: {weighted:+.0f}, 1H: {score_1h:+d}, 4H: {score_4h:+d})"

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
        return True, "" # Skip if no levels found in text
        
    closest_dist_pct = min(abs(live_price - lvl) / live_price for lvl in target_levels)
    
    # Tightened strike zone: only entries at exact institutional levels
    proximity_buffer = 0.0075 if "GOLD" in symbol.upper() or "XAU" in symbol.upper() else 0.0040
    
    if closest_dist_pct > proximity_buffer:
        side_str = "Demand/Support" if target_dir == "LONG" else "Supply/Resistance"
        return False, f"Price not in Institutional Strike Zone (Nearest {side_str} is {closest_dist_pct*100:.2f}% away, limit {proximity_buffer*100:.2f}%)"

    return True, ""

    return {"decision": "HOLD", "confidence": 0, "entry_price": "", "reasoning": "All retries exhausted"}
async def evaluate_market(memory_text: str, market_data_text: str, margin: float = 0, dom_data: str = "", active_positions: list = None, force_run: bool = False, active_symbol: str = "GOLD", live_asset_price: float = 0.0) -> dict:
    """THE CONSENSUS LOGIC - Main async entry point"""
    global WAKE_CYCLES_REMAINING
    print("=" * 60)
    print("APEX 3-AGENT CONSENSUS PIPELINE")
    print("=" * 60)

    import time
    symbol = active_symbol or "GOLD"
    if symbol in GLOBAL_COOLDOWNS:
        time_left = GLOBAL_COOLDOWNS[symbol] - time.time()
        if time_left > 0:
            print(f"[GATING] {symbol} is in POST-TRADE COOLDOWN for {int(time_left/60)} more minutes. Forcing HOLD.")
            return {"decision": "HOLD", "status": "COOLDOWN", "consensus_strength": 0}
        else:
            del GLOBAL_COOLDOWNS[symbol] # Cooldown expired


    # ── VOLATILITY GATE: Skip LLM calls if market is sideways ──
    if not force_run:
        gate = await check_market_volatility(symbol)
        if not gate["pass"]:
            print("=" * 60)
            print("FINAL DECISION: HOLD (Volatility Gate)")
            print("=" * 60)
            return gate["result"]
    else:
        print("[SYSTEM] MANUAL OVERRIDE ENGAGED: Bypassing Volatility Gate. Forcing all NVIDIA AI Agents to wake up...")

    # ── TREND BIAS PRE-SCORE ──
    trend_bias = compute_trend_bias(market_data_text)
    trend_score = trend_bias["score"]
    trend_label = trend_bias["label"]
    trend_bias_text = format_trend_bias(trend_bias)

    # ── AI CONSENSUS CACHE ──
    # If we evaluated this exact market state recently, return cached result
    # to avoid burning NVIDIA API rate limits on unchanged conditions.
    _cache_key = _make_ai_cache_key(symbol, market_data_text, float(live_asset_price or 0.0), force_run)
    _now = time.time()
    if _cache_key in _ai_consensus_cache:
        _cached = _ai_consensus_cache[_cache_key]
        if _cached["expires"] > _now:
            age = int(_now - _cached["created"])
            print(f"[AI-CACHE] HIT for {symbol} (age: {age}s). Returning cached consensus. Skipping {3} NVIDIA calls.")
            return _cached["result"]

    # ── A+ SETUP GATEKEEPER ──
    # Reject mediocre setups mathematically before firing any AI APIs
    if not force_run:
        aplus_pass, reject_reason = is_aplus_setup(market_data_text, trend_bias, float(live_asset_price or 0.0), symbol)
        if not aplus_pass:
            print("=" * 60)
            print(f"[GATEKEEPER] Rejected: {reject_reason}")
            print(f"FINAL DECISION: HOLD")
            print("=" * 60)
            return {
                "action": "HOLD",
                "asset": symbol,
                "confidence": 0,
                "reasoning": f"Rejected by A+ Filter: {reject_reason}",
                "status": "GATED",
                "_debug": {"trend_bias": trend_bias}
            }

    if active_positions is None:
        active_positions = []
    is_sanity_check = False
    sanity_alert = ""

    # Continuous fleet stacking: active positions do not hibernate the AI swarm.
    if active_positions:
        print(f"[STACK MODE] {len(active_positions)} active position(s) detected. AI Agents remain ACTIVE for continuous stacking.")
        if WAKE_CYCLES_REMAINING > 0:
            WAKE_CYCLES_REMAINING -= 1
            is_sanity_check = True
            print(f"[SANITY CHECK] Manual override context added. Cycles left: {WAKE_CYCLES_REMAINING}")

            pos = active_positions[0]
            size = float(pos.get("size", 0) or pos.get("qty", 0))
            side = "LONG" if size > 0 else "SHORT"
            entry = pos.get("entry_price", 0)
            sanity_alert = f"\n[SYSTEM ALERT: SANITY CHECK MODE. The user currently has an OPEN {side} position from {entry}. The user has manually woken you up to get a fresh read on the market. Evaluate the price action. Does the market still support holding this {side}, or are there signs of a reversal? Output your standard JSON analysis.]\n\n"
    else:
        print("[HUNT MODE] No active positions. Agents ACTIVE with fresh data.")

    trading_memory = load_memory()
    print(f"[MEMORY] Loaded {len(trading_memory)} chars from APEX_MEMORY.md")

    symbol_live_price = float(live_asset_price or 0.0)
    if symbol_live_price > 0:
        print(f"[SCALPER] {symbol} price provided: ${symbol_live_price:,.2f}")
    else:
        print(f"[SCALPER] Live {symbol} price unavailable from server state.")

    # PARALLEL EXECUTION: 3-Way Stagger to prevent 429 bursts
    # Increased to 3s gaps + global rate limiter in fetch_nvidia_sync keeps us under 30 RPM
    print(f"[PARALLEL] Running CLAW, Macro, and Scalper with 3s 3-way stagger...")

    # 1. Fire CLAW immediately (using OPENROUTER_API_KEY / Fundamental Key)
    claw_key = OPENROUTER_API_KEY if OPENROUTER_API_KEY else NVIDIA_API_KEY
    print("[STEP 1/3] Running CLAW Fundamental Analysis (NVIDIA NIM)...")
    claw_task = asyncio.create_task(get_market_sentiment([claw_key], sanity_alert, symbol=symbol))

    await asyncio.sleep(3.0)

    # 2. Fire Macro (using NVIDIA_API_KEY_2 / Trend Key)
    macro_key = NVIDIA_API_KEY_2 if NVIDIA_API_KEY_2 else NVIDIA_API_KEY
    print("[STEP 2/3] Running Macro Trend Analysis (NVIDIA NIM)...")
    macro_task = asyncio.create_task(analyze_macro_trend(macro_key, "Sentiment: Processing parallel...", market_data_text, market_data_text, trading_memory, sanity_alert, symbol=symbol, trend_bias_text=trend_bias_text))

    await asyncio.sleep(3.0)

    # 3. Fire Scalper (using NVIDIA_API_KEY / Scalper Key)
    scalper_key = NVIDIA_API_KEY
    print("[STEP 3/3] Running Scalper Analysis (NVIDIA NIM)...")
    scalper_task = asyncio.create_task(find_sniper_entry(scalper_key, market_data_text, symbol_live_price, trading_memory, sanity_alert, symbol=symbol, trend_bias_text=trend_bias_text))
    
    # Await all results
    sentiment_result = await claw_task
    sentiment_report = f"Sentiment: {sentiment_result.get('sentiment', 'NEUTRAL')} ({sentiment_result.get('confidence', 0)}%) - {sentiment_result.get('report', '')}"
    macro_result = await macro_task
    scalper_result = await scalper_task

    # (Trend bias was already calculated above)

    print("[CONSENSUS] Computing final 3-Agent decision...")
    macro_decision = str(macro_result.get("decision", "HOLD")).upper()
    scalper_decision = str(scalper_result.get("decision", "HOLD")).upper()
    claw_vote = sentiment_result.get("sentiment", "NEUTRAL").upper()

    direction_map = {
        "BUY": 1,
        "LONG": 1,
        "BULLISH": 1,
        "SELL": -1,
        "SHORT": -1,
        "BEARISH": -1,
        "HOLD": 0,
        "NEUTRAL": 0,
    }

    def normalize_confidence(value):
        confidence_value = float(value or 0)
        if confidence_value > 1:
            return confidence_value / 100
        return confidence_value

    weighted_votes = {
        "Macro": direction_map.get(macro_decision, 0) * normalize_confidence(macro_result.get("confidence", 0)) * 0.40,
        "CLAW": direction_map.get(claw_vote, 0) * normalize_confidence(sentiment_result.get("confidence", 0)) * 0.35,
        "Scalper": direction_map.get(scalper_decision, 0) * normalize_confidence(scalper_result.get("confidence", 0)) * 0.25,
    }
    hold_penalty = sum([
        0.40 * normalize_confidence(macro_result.get("confidence", 0)) if direction_map.get(macro_decision, 0) == 0 else 0,
        0.35 * normalize_confidence(sentiment_result.get("confidence", 0)) if direction_map.get(claw_vote, 0) == 0 else 0,
        0.25 * normalize_confidence(scalper_result.get("confidence", 0)) if direction_map.get(scalper_decision, 0) == 0 else 0,
    ])
    directional_score = sum(weighted_votes.values())
    if directional_score > 0:
        final_score = max(0, directional_score - hold_penalty)
    else:
        final_score = min(0, directional_score + hold_penalty)
    confidence = min(100, int(abs(final_score) * 100))

    if final_score >= 0.40:
        final_action = "LONG"
    elif final_score <= -0.40:
        final_action = "SHORT"
    else:
        final_action = "HOLD"
        if macro_decision != "HOLD" or scalper_decision != "HOLD" or claw_vote in ("BULLISH", "BEARISH"):
            reasoning = f"Weighted consensus score {final_score:+.4f} below execution threshold. Trade BLOCKED."

    print(
        f"[CONSENSUS] Weighted score={final_score:+.4f} "
        f"(Directional={directional_score:+.4f}, HoldGravity={hold_penalty:.4f}; "
        f"Macro={weighted_votes['Macro']:+.4f}, CLAW={weighted_votes['CLAW']:+.4f}, Scalper={weighted_votes['Scalper']:+.4f}) "
        f"=> {final_action}"
    )

    # Trend veto: direction must agree with the mathematical trend sign.
    if final_action == "SHORT" and trend_score > 0:
        print(f"[TREND VETO] BLOCKED SHORT — Trend is BULLISH ({trend_label}, score: {trend_score:+d}). Agents voted SHORT but 4H/1H trends disagree. Forcing HOLD.")
        final_action = "HOLD"
    elif final_action == "LONG" and trend_score < 0:
        print(f"[TREND VETO] BLOCKED LONG — Trend is BEARISH ({trend_label}, score: {trend_score:+d}). Agents voted LONG but 4H/1H trends disagree. Forcing HOLD.")
        final_action = "HOLD"
    elif final_action in ("LONG", "SHORT"):
        print(f"[TREND CHECK] Trade direction {final_action} ALIGNS with trend ({trend_label}, {trend_score:+d}). Approved.")

    exhaustion_check = detect_trend_exhaustion(market_data_text, final_action)
    if final_action in ("LONG", "SHORT") and exhaustion_check.get("veto"):
        print(f"[VETO] Trend Exhaustion detected. Ignoring late entry. {exhaustion_check['reason']}")
        final_action = "HOLD"

    # AI-determined risk parameters from the Scalper agent
    ai_sl = scalper_result.get("stop_loss_pct", 1.5)
    ai_tp = scalper_result.get("take_profit_pct", 4.0)
    ai_leverage = scalper_result.get("leverage", 10)
    macro_leverage = macro_result.get("recommended_leverage", 10)
    volatility = macro_result.get("volatility", "medium")

    # Blend leverage: weight toward the more confident agent, cap at 50x
    macro_conf = macro_result.get("confidence", 50)
    scalper_conf = scalper_result.get("confidence", 50)
    total_conf = macro_conf + scalper_conf
    if total_conf > 0:
        # Confidence-weighted average
        final_leverage = int((ai_leverage * scalper_conf + macro_leverage * macro_conf) / total_conf)
    else:
        final_leverage = 10
    final_leverage = min(50, max(1, final_leverage))

    avg_confidence = (macro_conf + scalper_conf) / 2
    print(f"[RISK CONTROL] AI Confidence: {avg_confidence:.0f}% (Macro: {macro_conf}% / Scalper: {scalper_conf}%). AI dynamically selected {final_leverage}x Leverage.")

    # Volatility adjustment: widen SL/TP in high vol, tighten in low vol
    if volatility == "high":
        ai_sl = min(3.0, ai_sl * 1.3)
        ai_tp = min(10.0, ai_tp * 1.3)
    elif volatility == "low":
        ai_sl = max(0.5, ai_sl * 0.8)
        ai_tp = max(1.0, ai_tp * 0.8)

    # ============================================================
    # RISK/REWARD GATE — Hard VETO (optimized for M15 scalping)
    # ============================================================
    # Lowered thresholds to allow more frequent high-probability scalps
    # while still blocking structurally bad setups.
    MIN_RR_RATIO = 1.5  # Standard M15 scalping minimum: 1.5x reward per 1x risk
    MIN_TP_PCT = 0.2    # Minimum 0.2% TP allows Forex swings while blocking fee/spread micro-scalps

    if final_action in ("LONG", "SHORT"):
        rr_ratio = round(ai_tp / ai_sl, 2) if ai_sl > 0 else 0.0

        # GATE 1: Anti-Fee Scalp Protection
        if ai_tp < MIN_TP_PCT:
            print(f"[VETO] Anti-Fee Scalp Protection: TP={ai_tp:.2f}% is below {MIN_TP_PCT}% minimum. Trade cannot clear exchange fees. Blocking.")
            final_action = "HOLD"

        # GATE 2: Minimum Risk/Reward Ratio
        elif rr_ratio < MIN_RR_RATIO:
            print(f"[VETO] Insufficient Risk/Reward Ratio ({rr_ratio:.2f}). Minimum required is {MIN_RR_RATIO}. TP={ai_tp:.1f}% vs SL={ai_sl:.1f}%. Trade rejected.")
            final_action = "HOLD"

        else:
            print(f"[RISK GATE] R:R Ratio {rr_ratio:.2f} (>= {MIN_RR_RATIO}) | TP={ai_tp:.1f}% | SL={ai_sl:.1f}% | APPROVED")

    print(f"[RISK] AI Params: SL={ai_sl:.1f}% | TP={ai_tp:.1f}% | Leverage={final_leverage}x | Volatility={volatility}")

    # Ensure all result variables are defined with safe defaults
    if 'reasoning' not in locals():
        reasoning = f"Consensus: {final_action} | Trend: {trend_label} ({trend_score:+d})"
    if 'confidence' not in locals():
        confidence = avg_confidence
    if 'rr_ratio' not in locals():
        rr_ratio = 0.0
    debug_info = {
        "sentiment": sentiment_result,
        "macro": macro_result,
        "scalper": scalper_result,
        "trend_bias": trend_bias
    }

    result = {
        "action": final_action,
        "is_sanity_check": is_sanity_check,
        "asset": symbol,
        "stop_loss_pct": ai_sl,
        "take_profit_pct": ai_tp,
        "leverage": final_leverage,
        "volatility": volatility,
        "reasoning": reasoning,
        "confidence": confidence,
        "rr_ratio": rr_ratio,
        "_debug": debug_info
    }

    # ── AI CONSENSUS CACHE STORE ──
    # Cache this result so we don't burn NVIDIA API calls on unchanged market data
    _ai_consensus_cache[_cache_key] = {
        "result": result,
        "expires": time.time() + AI_CACHE_TTL,
        "created": time.time()
    }
    print(f"[AI-CACHE] Stored consensus for {symbol} (TTL: {AI_CACHE_TTL}s)")

    return result


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

            response = await asyncio.to_thread(
                fetch_nvidia_sync,
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers, payload
            )

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
