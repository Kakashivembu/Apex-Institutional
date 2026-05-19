import re
import codecs

with open('nvidia_apex_trader/core/brain.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Rename fetch_nvidia_sync to call_nvidia_nim_api
code = code.replace('fetch_nvidia_sync', 'call_nvidia_nim_api')

# 2. Add response = None at start of agent loops
def insert_response_none(code, func_name):
    pattern = rf"(def {func_name}\(.*?\):\n.*?)(    max_retries = 2)"
    def repl(m):
        return m.group(1) + "    response = None\n" + m.group(2)
    return re.sub(pattern, repl, code, flags=re.DOTALL)

code = insert_response_none(code, "get_market_sentiment")
code = insert_response_none(code, "analyze_macro_trend")
code = insert_response_none(code, "find_sniper_entry")

# 3. Replace the parsing block inside the try with a break
def strip_parsing(code, func_name, parse_start, parse_end):
    # Find the try block inside the agent
    pattern = rf"(def {func_name}.*?if response\.status_code == 200:\n)(.*?)(            elif response\.status_code in \(502, 503, 429\))"
    def repl(m):
        return m.group(1) + "                break\n" + m.group(3)
    return re.sub(pattern, repl, code, flags=re.DOTALL)

code = strip_parsing(code, "get_market_sentiment", "", "")
code = strip_parsing(code, "analyze_macro_trend", "", "")
code = strip_parsing(code, "find_sniper_entry", "", "")

# 4. Clean up exceptions and add fallback and parsing at the end
# get_market_sentiment
claw_old_end = '''        except requests.exceptions.Timeout:
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
    return _neutral_fallback'''

claw_new_end = '''        except Exception as e:
            if attempt < max_retries:
                print(f"[CLAW] Error: {e} - Retry {attempt+1}/{max_retries}...")
                await asyncio.sleep(3)
                continue
            print(f"[CLAW] API error: {e}")

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
    return _neutral_fallback'''
code = code.replace(claw_old_end, claw_new_end)

# analyze_macro_trend
macro_old_end = '''        except requests.exceptions.Timeout:
            if attempt < max_retries:
                print(f"[MACRO] Timeout - Retry {attempt+1}/{max_retries}...")
                await asyncio.sleep(3)
                continue
            print("[MACRO] Timeout error (all retries exhausted)")
            return {**_hold, "reasoning": "Request timeout"}
        except requests.exceptions.RequestException as e:
            print(f"[MACRO] Request error: {e}")
            return {**_hold, "reasoning": f"Connection error: {str(e)}"}
        except Exception as e:
            print(f"[MACRO] Error: {e}")
            return {**_hold, "reasoning": str(e)}
    return {**_hold, "reasoning": "All retries exhausted"}'''
macro_new_end = '''        except Exception as e:
            if attempt < max_retries:
                print(f"[MACRO] Error: {e} - Retry {attempt+1}/{max_retries}...")
                await asyncio.sleep(3)
                continue
            print(f"[MACRO] API error: {e}")

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

    return {**_hold, "reasoning": "All retries exhausted"}'''
code = code.replace(macro_old_end, macro_new_end)

# find_sniper_entry
scalper_old_end = '''        except requests.exceptions.Timeout:
            if attempt < max_retries:
                print(f"[SCALPER] Timeout - Retry {attempt+1}/{max_retries}...")
                await asyncio.sleep(3)
                continue
            print("[SCALPER] Timeout error (all retries exhausted)")
            return {**_hold, "reasoning": "Request timeout"}
        except requests.exceptions.RequestException as e:
            print(f"[SCALPER] Request error: {e}")
            return {**_hold, "reasoning": f"Connection error: {str(e)}"}
        except Exception as e:
            print(f"[SCALPER] Error: {e}")
            return {**_hold, "reasoning": str(e)}
    return {**_hold, "reasoning": "All retries exhausted"}'''
scalper_new_end = '''        except Exception as e:
            if attempt < max_retries:
                print(f"[SCALPER] Error: {e} - Retry {attempt+1}/{max_retries}...")
                await asyncio.sleep(3)
                continue
            print(f"[SCALPER] API error: {e}")

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

    return {**_hold, "reasoning": "All retries exhausted"}'''
code = code.replace(scalper_old_end, scalper_new_end)

# Phase 2: Parallel execution block in evaluate_market
old_eval = '''    # PARALLEL EXECUTION: 3-Way Stagger to prevent 429 bursts
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
    scalper_result = await scalper_task'''

new_eval = '''    # PARALLEL EXECUTION: Micro-stagger to prevent 429 bursts
    print(f"[PARALLEL] Running CLAW, Macro, and Scalper with micro-stagger...")

    async def run_claw():
        claw_key = OPENROUTER_API_KEY if OPENROUTER_API_KEY else NVIDIA_API_KEY
        print("[STEP 1/3] Running CLAW Fundamental Analysis (NVIDIA NIM)...")
        return await get_market_sentiment([claw_key], sanity_alert, symbol=symbol)

    async def run_macro():
        await asyncio.sleep(0.7)
        macro_key = NVIDIA_API_KEY_2 if NVIDIA_API_KEY_2 else NVIDIA_API_KEY
        print("[STEP 2/3] Running Macro Trend Analysis (NVIDIA NIM)...")
        return await analyze_macro_trend(macro_key, "Sentiment: Processing parallel...", market_data_text, market_data_text, trading_memory, sanity_alert, symbol=symbol, trend_bias_text=trend_bias_text)

    async def run_scalper():
        await asyncio.sleep(1.4)
        scalper_key = NVIDIA_API_KEY
        print("[STEP 3/3] Running Scalper Analysis (NVIDIA NIM)...")
        h1_bias = ""
        try:
            from core.macro_sensors import get_h1_trend_bias
            h1_data = get_h1_trend_bias(symbol)
            h1_bias = h1_data.get("bias", "")
        except Exception as h1_err:
            print(f"[HTF-GATE] H1 bias fetch failed (non-blocking): {h1_err}")
        return await find_sniper_entry(scalper_key, market_data_text, symbol_live_price, trading_memory, sanity_alert, symbol=symbol, trend_bias_text=trend_bias_text, h1_bias=h1_bias)

    # Await all results using gather
    results = await asyncio.gather(run_claw(), run_macro(), run_scalper())
    sentiment_result = results[0]
    sentiment_report = f"Sentiment: {sentiment_result.get('sentiment', 'NEUTRAL')} ({sentiment_result.get('confidence', 0)}%) - {sentiment_result.get('report', '')}"
    macro_result = results[1]
    scalper_result = results[2]'''
code = code.replace(old_eval, new_eval)

with open('nvidia_apex_trader/core/brain.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Patch applied.")
