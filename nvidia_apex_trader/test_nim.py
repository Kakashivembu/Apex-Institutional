import os
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# All keys are natively routed to NVIDIA NIM
keys = {
    "Scalper AI": os.getenv("NVIDIA_API_KEY", ""),
    "Trend Follower AI": os.getenv("NVIDIA_API_KEY_2", ""),
    "Chat AI": os.getenv("NVIDIA_CHAT_KEY", ""),
    "Fundamental Desk AI": os.getenv("OPENROUTER_API_KEY", "") # Holds your nvapi- key
}

url = "https://integrate.api.nvidia.com/v1/chat/completions"
model = "meta/llama-3.1-8b-instruct"

for name, k in keys.items():
    if not k:
        print(f"[{name}] FAIL - Key not configured in .env")
        continue
    
    headers = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Say 'hello' in one word."}],
        "max_tokens": 10
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            print(f"[{name}] SUCCESS - Connection active.")
        else:
            print(f"[{name}] ERROR - HTTP {response.status_code}: {response.text[:100]}")
    except Exception as e:
        print(f"[{name}] FATAL ERROR - {e}")