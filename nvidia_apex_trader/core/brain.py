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

# =============================================================================
# GLOBAL NVIDIA NIM RATE LIMITER (Token Bucket per API key)
# =============================================================================
# NVIDIA limit: 40 RPM. We enforce 30 RPM to leave 25% headroom and avoid bans.
NVIDIA_RPM_LIMIT = 30          # Hard cap: 30 calls per minute per key
NVIDIA_MIN_GAP = 2.5           # Minimum 2.5 seconds between calls on same key
NVIDIA_CALL_LOG = {}           # {api_key: [timestamps]}  rolling 60s window
NVIDIA_LAST_CALL_PER_KEY = {}  # {api_key: last_timestamp}

_nvidia_lock = asyncio.Lock()

async def _wait_for_nvidia_rate_limit(api_key: str):
    """Async global pre-flight rate limiter. Sleeps proactively if key is near limit.
    FIX: Converted from threading.Lock + time.sleep to asyncio.Lock + asyncio.sleep
    to prevent event-loop blocking that caused 429 cascades across all 3 agents."""
    global NVIDIA_CALL_LOG, NVIDIA_LAST_CALL_PER_KEY
    now = time.time()
    async with _nvidia_lock:
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
    Native NVIDIA NIM integration. OPTIMIZED: ~150 tokens total."""
    
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
        context_text = compress_candle_data(market_data_text, max_candles=3)
        liquidity_data_str = "Backtest Mode - Synthetic Context Provided"

    system_prompt = (
        "You are an elite quantitative trading AI based on the Qwen architecture. "
        "Analyze the provided market data concisely. "
        "You may output a brief logical analysis, but you MUST conclude your response "
        "with a single, strictly formatted JSON block containing your final decision. "
        "Do not output any text after the JSON block. "
        f"Forex/Metals macro sentiment analyzer for {symbol}. "
        'Output format: {"sentiment":"BULLISH"|"BEARISH"|"NEUTRAL","confidence":0-100,'
        '"squeeze_risk":"HIGH"|"MEDIUM"|"LOW","dominant_side":"LONG"|"SHORT"|"BALANCED","summary":"1 sentence"}'
    )

    user_prompt = f"{context_text}"

    payload = {
        "model": "meta/llama-3.1-70b-instruct",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 80,
        "response_format": {"type": "json_object"}
    }

    _neutral_fallback = {
        "sentiment": "NEUTRAL", "confidence": 50,
        "squeeze_risk": "LOW", "dominant_side": "BALANCED",
        "bullish_pct": 33, "bearish_pct": 33, "neutral_pct": 34,
        "report": "Fundamental analysis offline.", "liquidity_data": liquidity_data_str
    }

    claw_key = os.getenv("NVIDIA_API_KEY_FUNDAMENTAL") or os.getenv("NVIDIA_API_KEY")
    
    print(f"[CLAW] Routing Fundamental Analysis directly to NVIDIA NIM...")
    response = await call_nvidia_nim_api(payload, claw_key)

    if not response or response.status_code != 200:
        print(f"[CLAW] NVIDIA API exhausted. Triggering agent-specific local fallback...")
        response = await asyncio.to_thread(execute_local_fallback, payload)

    if response and response.status_code == 200:
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        parsed = robust_json_parse(content, _neutral_fallback)
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

    print(f"[CLAW] Fundamental analysis offline or failed.")
    return _neutral_fallback

def _get_max_leverage_setting() -> int:
    """Read the user's max_leverage from persisted system parameters.
    Returns 10 if the file is missing or unreadable."""
    import os, json as _json
    params_file = os.path.join(os.path.expanduser("~"), ".apex_trader", "apex_parameters.json")
    try:
        if os.path.exists(params_file):
            with open(params_file, "r", encoding="utf-8") as f:
                data = _json.load(f)
            return int(data.get("max_leverage", 10))
    except Exception:
        pass
    return 10

def execute_local_fallback(payload: dict) -> requests.Response:
    """Route to local LM Studio with COMPRESSED prompt. Max 1200 tokens output.
    FIX #2: Increased max_tokens 80 → 150 → 400 → 1200 for distilled reasoning + JSON.
    FIX #3: Clamps leverage in the response to the user's max_leverage setting.
    FIX #4: Tuned for qwen3.5-9b-claude-4.6-opus-reasoning-distilled-v2.
    FIX #5: 400→1200 — reasoning tokens regularly exceed 300, truncating JSON."""
    print(f"[LOCAL-FALLBACK] NVIDIA API unavailable. Routing to LM Studio (RTX 4060 / Qwen-Reasoning)...")
    try:
        messages = payload.get("messages", [])
        # Keep original system prompt (already optimized), compress user content
        sys_content = messages[0].get("content", "") if messages else ""
        user_content = messages[-1].get("content", "") if len(messages) > 1 else ""
        # Compress if user content is bloated
        if len(user_content) > 500:
            user_content = compress_candle_data(user_content, max_candles=3)
        fallback_payload = {
            "model": "local-model",
            "messages": [
                {"role": "system", "content": sys_content[:800]},
                {"role": "user", "content": user_content[:700]}
            ],
            "temperature": 0.1,
            "max_tokens": 1200,  # FIX #5: 400→1200 — reasoning burns ~300+ tokens before JSON
            "stream": False
        }
        response = requests.post(LOCAL_LLM_URL, json=fallback_payload, timeout=120)

        # ── FIX #3: LEVERAGE CLAMP for LM Studio responses ──
        # Local models ignore the user's leverage cap. Hard-clamp here.
        if response.status_code == 200:
            try:
                max_lev = _get_max_leverage_setting()
                resp_json = response.json()
                content_str = resp_json.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content_str:
                    parsed = robust_json_parse(content_str, {})
                    raw_lev = int(parsed.get("leverage", parsed.get("recommended_leverage", 0)))
                    if raw_lev > max_lev and raw_lev > 0:
                        print(f"[LOCAL-CLAMP] LM Studio leverage clamped: {raw_lev}x → {max_lev}x")
                        parsed["leverage"] = max_lev
                        parsed["recommended_leverage"] = max_lev
                        # Re-pack the clamped JSON back into the response
                        resp_json["choices"][0]["message"]["content"] = json.dumps(parsed)
                        # Monkey-patch the response so callers see clamped values
                        original_json = response.json
                        response.json = lambda _rj=resp_json: _rj
            except Exception as clamp_err:
                print(f"[LOCAL-CLAMP] Clamp parse error (non-fatal): {clamp_err}")

        return response
    except Exception as e:
        print(f"[LOCAL-FALLBACK] LM Studio fallback failed: {e}. Defaulting to HOLD.")
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

async def call_nvidia_nim_api(payload: dict, api_key: str = None, max_retries: int = 3) -> requests.Response:
    """Async NVIDIA API call with non-blocking rate limiting.
    Implements retry with exponential backoff on 429 Rate Limit errors.
    Circuit breaker prevents repeated calls when API is down.

    FIX (ASYNC CONVERSION): Converted from synchronous def + time.sleep to
    async def + asyncio.sleep. HTTP requests run via asyncio.to_thread to
    keep the event loop unblocked. This eliminates the deadlock where 3
    agents blocked each other through threading.Lock + time.sleep, causing
    20+ second cascading delays and 429 storms.
    """
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    target_key = api_key or os.getenv("NVIDIA_API_KEY")
    headers = {
        "Authorization": f"Bearer {target_key}",
        "Content-Type": "application/json"
    }
    
    state = get_key_state(target_key)

    for attempt in range(max_retries):
        current_time = time.time()

        # ── GLOBAL PRE-FLIGHT RATE LIMITER (async) ──
        if target_key:
            await _wait_for_nvidia_rate_limit(target_key)
        else:
            # Fallback: enforce minimum delay if no key found
            elapsed = current_time - state["last_call"]
            if elapsed < NVIDIA_MIN_GAP:
                await asyncio.sleep(NVIDIA_MIN_GAP - elapsed)
            state["last_call"] = time.time()

        try:
            # Run blocking requests.post in thread pool to avoid blocking the event loop
            response = await asyncio.to_thread(
                requests.post, url, headers=headers, json=payload, timeout=25, verify=False
            )
        except requests.exceptions.Timeout:
            print(f"[NVIDIA] Timeout. Bypassing retries...")
            class TimeoutResponse:
                status_code = 408
                text = "Request Timeout"
                def json(self): return {}
            return TimeoutResponse()

        # Handle 429 errors with exponential backoff + jitter (non-blocking)
        if response.status_code == 429:
            state["error_count"] += 1
            import random
            jitter = random.uniform(0.5, 2.0)
            sleep_time = min(15, (2 ** attempt) + jitter)
            print(f"[NVIDIA] Rate limited (429)! Error count: {state['error_count']}. Retrying in {sleep_time:.1f}s (jitter: {jitter:.1f}s)...")
            await asyncio.sleep(sleep_time)
            continue

        # SUCCESS: Reset backoff state
        if response.status_code == 200:
            if state["error_count"] > 0:
                print(f"[NVIDIA] Success after {state['error_count']} previous 429 errors — backoff cleared")
                state["error_count"] = 0
            return response

        return response

    class ExhaustedResponse:
        status_code = 500
        text = "All retries exhausted"
        def json(self): return {}
    return ExhaustedResponse()

def get_optimized_parameters(symbol: str):
    # OBSOLETE: Replaced by Dynamic ATR Volatility Engine
    return None, None

async def analyze_macro_trend(nvidia_key: str, sentiment_report: str, candle_1h: str, candle_4h: str, trading_memory: str = "", sanity_alert: str = "", symbol: str = "GOLD", trend_bias_text: str = "NEUTRAL (+0)") -> dict:
    """AGENT 2: The Macro Trend Follower (NVIDIA NIM). OPTIMIZED: ~200 tokens total."""
    if not nvidia_key:
        return {"decision": "HOLD", "confidence": 0, "reasoning": "No NVIDIA API key"}

    # Compress candle data from ~500+ tokens per TF to ~60
    compact_1h = compress_candle_data(candle_1h, max_candles=3)
    compact_4h = compress_candle_data(candle_4h, max_candles=3)

    system_prompt = (
        "You are an elite quantitative trading AI based on the Qwen architecture. "
        "Analyze the provided market data concisely. "
        "You may output a brief logical analysis, but you MUST conclude your response "
        "with a single, strictly formatted JSON block containing your final decision. "
        "Do not output any text after the JSON block. "
        f"Forex/Metals macro trend follower for {symbol}. Trend bias: {trend_bias_text}. "
        "Follow the trend. BUY if bullish, SELL if bearish, HOLD if unclear. Never counter-trend. "
        'Output format: {"decision":"BUY"|"SELL"|"HOLD","confidence":0-100,'
        '"volatility":"low"|"medium"|"high","recommended_leverage":1-50,"reasoning":"brief"}'
    )

    user_prompt = f"1H:{compact_1h}\n4H:{compact_4h}"

    payload = {
        "model": "meta/llama-3.1-70b-instruct",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 80,
        "response_format": {"type": "json_object"}
    }

    _hold = {"decision": "HOLD", "confidence": 0, "reasoning": ""}

    macro_key = os.getenv("NVIDIA_API_KEY_MACRO") or os.getenv("NVIDIA_API_KEY")
    
    print(f"[MACRO] Routing Macro Trend Analysis directly to NVIDIA NIM...")
    response = await call_nvidia_nim_api(payload, macro_key)

    if not response or response.status_code != 200:
        print(f"[MACRO] NVIDIA API exhausted. Triggering agent-specific local fallback...")
        response = await asyncio.to_thread(execute_local_fallback, payload)

    if response and response.status_code == 200:
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        result = robust_json_parse(content, _hold)
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

    return {**_hold, "reasoning": "All retries exhausted"}

async def find_sniper_entry(nvidia_key: str, candle_5m: str, live_price: float = 0, trading_memory: str = "", sanity_alert: str = "", symbol: str = "GOLD", trend_bias_text: str = "NEUTRAL (+0)", h1_bias: str = "") -> dict:
    """AGENT 3: The Scalper (NVIDIA NIM). OPTIMIZED: ~180 tokens total. HTF bias injected."""
    if not nvidia_key:
        return {"decision": "HOLD", "confidence": 0, "reasoning": "No NVIDIA API key"}

    _hold = {"decision": "HOLD", "confidence": 0, "entry_price": "", "reasoning": "", "stop_loss_pct": 1.5, "take_profit_pct": 4.0, "leverage": 10}

    if live_price > 0:
        current_price = live_price
        print(f"[SCALPER] {symbol} price provided: ${current_price:,.2f}")
    else:
        current_price = 0

    if current_price <= 0:
        print("[SCALPER] ERROR: current_price is 0! NVIDIA cannot calculate entry with $0 price.")
        return {**_hold, "reasoning": f"Live {symbol} price unavailable"}

    compact_data = compress_candle_data(candle_5m, max_candles=5)

    # Inject HTF bias so the model knows the H1 direction
    htf_line = f" HTF H1 bias: {h1_bias}. Only output signals matching HTF direction." if h1_bias and h1_bias != "SKIP" else ""
    system_prompt = (
        "You are an elite quantitative trading AI based on the Qwen architecture. "
        "Analyze the provided market data concisely. "
        "You may output a brief logical analysis, but you MUST conclude your response "
        "with a single, strictly formatted JSON block containing your final decision. "
        "Do not output any text after the JSON block. "
        f"Forex/Metals scalper for {symbol} at {current_price:,.2f}. Trend: {trend_bias_text}.{htf_line} "
        "Follow the trend direction only. Never counter-trend. "
        'Output format: {"decision":"BUY"|"SELL"|"HOLD","confidence":0-100,"entry_price":number,'
        '"stop_loss_pct":0.1-3.0,"take_profit_pct":0.3-10.0,"leverage":1-50,"reasoning":"brief"}'
    )

    user_prompt = f"{compact_data}"

    payload = {
        "model": "meta/llama-3.1-70b-instruct",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 80,
        "response_format": {"type": "json_object"}
    }

    scalper_key = os.getenv("NVIDIA_API_KEY_SCALPER") or os.getenv("NVIDIA_API_KEY")
    
    print(f"[SCALPER] Executing short-term logic via NVIDIA NIM...")
    response = await call_nvidia_nim_api(payload, scalper_key)

    if not response or response.status_code != 200:
        print(f"[SCALPER] NVIDIA API exhausted. Triggering agent-specific local fallback...")
        response = await asyncio.to_thread(execute_local_fallback, payload)

    if response and response.status_code == 200:
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        result = robust_json_parse(content, _hold)
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

    return {**_hold, "reasoning": "All retries exhausted"}


def is_aplus_setup(market_data_text: str, trend_bias: dict, live_price: float, symbol: str, timestamp_str: str = "", smc_proximity_pct: float = 0.0015) -> tuple[bool, str]:
    """
    Mathematical Gatekeeper: Only allows A+ Setups to pass to the LLM.
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
    
    # Instrument-aware strike zone: Metals need wider tolerance due to high candle volatility
    _sym_upper = symbol.upper()
    is_metal = any(m in _sym_upper for m in ("GOLD", "XAU", "SILVER", "XAG", "US30", "DJ30"))
    proximity_buffer = 0.0080 if is_metal else 0.0040
    
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
    # Increased to 3s gaps + global rate limiter in call_nvidia_nim_api keeps us under 30 RPM
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

    # 3. Fire Scalper (using NVIDIA_API_KEY / Scalper Key) — with HTF bias injection
    scalper_key = NVIDIA_API_KEY
    print("[STEP 3/3] Running Scalper Analysis (NVIDIA NIM)...")
    # FIX #6: Fetch H1 bias and inject into scalper prompt
    try:
        from core.macro_sensors import get_h1_trend_bias
        h1_data = get_h1_trend_bias(symbol)
        h1_bias = h1_data.get("bias", "")
    except Exception as h1_err:
        print(f"[HTF-GATE] H1 bias fetch failed (non-blocking): {h1_err}")
        h1_bias = ""
    scalper_task = asyncio.create_task(find_sniper_entry(scalper_key, market_data_text, symbol_live_price, trading_memory, sanity_alert, symbol=symbol, trend_bias_text=trend_bias_text, h1_bias=h1_bias))
    
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

    # ── FIX #1: STACK MODE HOLD-GRAVITY REDUCTION ──
    # When a position is already open (STACK MODE), reduce the conservative
    # hold bias from the full agent weights to 0.05 per-agent. This lets the
    # bot lean into a confirmed trend and add to winners instead of holding back.
    active_positions_on_symbol = len([p for p in (active_positions or []) if p.get("symbol", "") == symbol]) if active_positions else 0
    if active_positions_on_symbol > 0:
        hold_gravity = 0.05  # Stack mode — lean into confirmed trend
        hold_mode_label = "STACK"
    else:
        hold_gravity = 0.21  # New entry mode — be conservative
        hold_mode_label = "ENTRY"

    hold_penalty = sum([
        hold_gravity * normalize_confidence(macro_result.get("confidence", 0)) if direction_map.get(macro_decision, 0) == 0 else 0,
        hold_gravity * normalize_confidence(sentiment_result.get("confidence", 0)) if direction_map.get(claw_vote, 0) == 0 else 0,
        hold_gravity * normalize_confidence(scalper_result.get("confidence", 0)) if direction_map.get(scalper_decision, 0) == 0 else 0,
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
        f"(Directional={directional_score:+.4f}, HoldGravity={hold_penalty:.4f} [{hold_mode_label} mode, base={hold_gravity}]; "
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
