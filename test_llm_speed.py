import time
import requests
import json

url = "http://127.0.0.1:1234/v1/chat/completions"
model = "bartowski/meta-llama-3.1-8b-instruct"

payload = {
    "model": model,
    "messages": [
        {"role": "system", "content": "You are a financial trading system."},
        {"role": "user", "content": "The Asian High is 159.50 and the Asian Low is 158.80. The current price is 158.75 and the 1H trend is bearish (price is below 200 EMA). A 1-minute CHoCH just occurred bullishly after sweeping the low. Based on 'The Trading Geek' strategy, what is your trading decision? Reply in JSON format with 'decision' (BUY, SELL, HOLD) and 'reasoning'."}
    ],
    "temperature": 0.1,
    "max_tokens": 150
}

headers = {
    "Content-Type": "application/json"
}

print(f"Testing Local LLM Speed on {url}")
print(f"Model: {model}\n")

for i in range(1, 4):
    print(f"--- Test Run {i} ---")
    start_time = time.time()
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        end_time = time.time()
        
        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            # LM Studio returns usage stats
            usage = data.get("usage", {})
            completion_tokens = usage.get("completion_tokens", len(content.split()))
            
            duration = end_time - start_time
            tps = completion_tokens / duration if duration > 0 else 0
            
            print(f"Response Time: {duration:.2f} seconds")
            print(f"Tokens Generated: {completion_tokens}")
            print(f"Speed: {tps:.2f} tokens/sec")
            print(f"Output:\n{content}\n")
        else:
            print(f"Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")
        
    time.sleep(1)

print("Test complete.")
