import requests
import json
import os
import time
from dotenv import load_dotenv

load_dotenv('nvidia_apex_trader/.env')

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
print(f"Using NVIDIA API key: {NVIDIA_API_KEY[:20]}...{NVIDIA_API_KEY[-4:]}")

headers = {
    'Authorization': f'Bearer {NVIDIA_API_KEY}',
    'Content-Type': 'application/json'
}

# Test 1: Check available models
print("\n=== Testing NVIDIA API Models ===")
try:
    response = requests.get('https://integrate.api.nvidia.com/v1/models', headers=headers, timeout=30)
    print(f'Status: {response.status_code}')
    print(f'Headers: {dict(response.headers)}')
    if response.status_code == 200:
        models = response.json()
        model_names = [m['id'] for m in models.get('data', [])]
        print(f'Available models: {model_names}')
    else:
        print(f'Error: {response.text[:200]}')
except Exception as e:
    print(f'Error: {e}')

# Test 2: Test chat completion with rate limiting
print("\n=== Testing NVIDIA Chat Completion ===")
payload = {
    "model": "meta/llama-3.1-70b-instruct",
    "messages": [
        {"role": "system", "content": "You are a Macro Trend Follower AI. Analyze the market data and determine trend direction. Respond ONLY in valid JSON format: {\"decision\": \"BUY\"|\"SELL\"|\"HOLD\", \"confidence\": 0-100, \"reasoning\": \"brief explanation\"}"},
        {"role": "user", "content": "Analyze the current market trend and provide your decision."}
    ],
    "temperature": 0.2,
    "max_tokens": 500,
    "response_format": {"type": "json_object"}
}

try:
    # Add rate limiting delay
    time.sleep(1.5)
    
    response = requests.post('https://integrate.api.nvidia.com/v1/chat/completions', headers=headers, json=payload, timeout=30)
    print(f'Status: {response.status_code}')
    rate_limit = response.headers.get('x-ratelimit-remaining', 'unknown')
    print(f'Rate limit remaining: {rate_limit}')
    
    if response.status_code == 200:
        data = response.json()
        content = data.get('choices', [{}])[0].get('message', {}).get('content', '{}')
        print(f'Content: {content}')
        
        try:
            parsed = json.loads(content)
            print(f'Parsed: {parsed}')
        except json.JSONDecodeError:
            print('JSON parsing failed')
    elif response.status_code == 429:
        print('Rate limited! Need to implement proper rate limiting')
        print(f'Response: {response.text[:200]}')
    else:
        print(f'Error: {response.text[:200]}')
        
except Exception as e:
    print(f'Request error: {e}')
    import traceback
    traceback.print_exc()