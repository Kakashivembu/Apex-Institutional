import requests
import time
import json

# Using 127.0.0.1 is safer than "localhost" for LM Studio
LOCAL_LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"

prompt = "=== MARKET DATA (GOLD.i#) ===\nCurrent Price: $4,736.20\n1H Trend Score: BULLISH (+40)\n4H Trend Score: LEAN_BULLISH (+22)\n\n=== ICT LIQUIDITY & AMD PATTERN ===\nAsian High: $4,720.00\nAsian Low: $4,680.00\nSTATUS: PRICE IS SWEEPING ASIAN HIGHS - ANTICIPATE BEARISH REVERSAL (Distribution).\n\n=== VOLATILITY ALIGNMENT ===\nDynamic SL Distance: 1.50%\nDynamic TP Target: 3.80%\n\n=== RULES ===\nICT SWEEP RULE: If the market data indicates a Liquidity Sweep, DO NOT trust basic trend indicators. Anticipate a reversal."

payload = {
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

print("[SYSTEM] Firing prompt to LM Studio (RTX 4060)...")
start_time = time.time()

try:
    response = requests.post(LOCAL_LLM_URL, json=payload, timeout=120)
    response.raise_for_status()
    
    end_time = time.time()
    latency = end_time - start_time
    
    data = response.json()
    ai_text = data['choices'][0]['message']['content']
    completion_tokens = data['usage']['completion_tokens']
    
    # Calculate Tokens Per Second (TPS)
    tps = completion_tokens / latency if latency > 0 else 0
    
    print("\n=== LM STUDIO RESPONSE ===")
    print(ai_text)
    print("==========================")
    print(f"Latency:      {latency:.2f} seconds")
    print(f"Generation:   {completion_tokens} tokens")
    print(f"Speed:        {tps:.2f} Tokens/Second")

except Exception as e:
    print(f"\n[ERROR] Local model failed: {e}")
    print("Make sure LM Studio Server is running and the URL is exact.")

# END OF FILE
# THIS IS THE MAGIC LINE THAT KEEPS THE WINDOW OPEN
print("\n")
input("Press Enter to close this window...")