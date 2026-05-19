import re

with open('nvidia_apex_trader/core/brain.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Replace fetch_nvidia_sync to call_nvidia_nim_api
code = code.replace('fetch_nvidia_sync', 'call_nvidia_nim_api')

# 2. Patch get_market_sentiment
old_claw_try = '''        try:
            print(f"[CLAW] Routing Fundamental Analysis directly to NVIDIA NIM...")
            response = await asyncio.to_thread(
                call_nvidia_nim_api,
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers,
                payload
            )
            
            if response.status_code == 200:
                data = response.json()'''
new_claw_try = '''        try:
            print(f"[CLAW] Routing Fundamental Analysis directly to NVIDIA NIM...")
            response = await asyncio.to_thread(
                call_nvidia_nim_api,
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers,
                payload
            )
            
            if response.status_code == 200:
                break'''
code = code.replace(old_claw_try, new_claw_try)

old_claw_parse = '''            else:
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
    return _neutral_fallback'''
new_claw_parse = '''            else:
                print(f"[CLAW] HTTP {response.status_code}")
                pass
        except Exception as e:
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
# First remove the original parsing block that we shifted to the end
# Wait, it's easier to just replace the whole function block.
