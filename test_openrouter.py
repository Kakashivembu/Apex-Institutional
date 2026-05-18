import requests
import json
import os
from dotenv import load_dotenv

load_dotenv('nvidia_apex_trader/.env')

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
print(f"Using API key: {OPENROUTER_API_KEY[:20]}...{OPENROUTER_API_KEY[-4:]}")

headers = {
    'Authorization': f'Bearer {OPENROUTER_API_KEY}',
    'Content-Type': 'application/json',
    'HTTP-Referer': 'https://apex-institutional.com',
    'X-Title': 'Apex Institutional Trading Terminal'
}

system_prompt = """You are a Macro-Economic Crypto Analyst. Scrape current crypto news and analyze market sentiment.
Return ONLY a valid JSON object with this exact structure:
{"overall_sentiment": "Bullish", "confidence_score": 80, "summary": "Brief analysis of current market conditions"}"""

payload = {
    'model': 'openrouter/auto',
    'messages': [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': 'Analyze current crypto market sentiment and provide a JSON report with bullish/bearish/neutral sentiment, confidence score (0-100), and brief summary.'}
    ],
    'temperature': 0.2,
    'max_tokens': 500,
    'response_format': {'type': 'json_object'}
}

try:
    response = requests.post('https://openrouter.ai/api/v1/chat/completions', headers=headers, json=payload, timeout=30)
    print(f'Status: {response.status_code}')
    print(f'Headers: {dict(response.headers)}')
    
    if response.status_code == 200:
        data = response.json()
        content = data.get('choices', [{}])[0].get('message', {}).get('content', '{}')
        print(f'Content: {content}')
        
        # Test parsing
        try:
            parsed = json.loads(content)
            print(f'Parsed: {parsed}')
        except json.JSONDecodeError:
            print('JSON parsing failed')
            print('Raw content:', repr(content))
    else:
        print(f'Error response: {response.text[:200]}')
        
except Exception as e:
    print(f'Request error: {e}')
    import traceback
    traceback.print_exc()