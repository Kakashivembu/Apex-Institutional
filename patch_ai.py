import re
import os

filepath = r"f:\NEW NVdia Apex Ultimate\nvidia_apex_trader\core\brain.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Instead of re.sub which interprets escape sequences, use string replacement.
# Find the start of `async def call_hermes_wsl_direct` and end of `async def call_hermes_gateway`

start_idx = content.find("async def call_hermes_wsl_direct")
end_idx = content.find("async def evaluate_market")

if start_idx != -1 and end_idx != -1:
    before = content[:start_idx]
    after = content[end_idx:]
    
    replacement = """async def _clean_json_response(content: str) -> dict:
    import json
    import re
    match = re.search(r'\\{.*\\}', content, re.DOTALL)
    if match:
        content = match.group(0)
    else:
        content = content.replace('```json', '').replace('```', '').strip()
    try:
        clean_json = content.replace('\\n', ' ')
        return json.loads(clean_json)
    except json.JSONDecodeError:
        decision_match = re.search(r'"decision"\\s*:\\s*"([A-Z]+)"', content, re.IGNORECASE)
        conf_match = re.search(r'"confidence"\\s*:\\s*(\\d+)', content)
        if decision_match:
            return {
                "decision": decision_match.group(1).upper(),
                "confidence": int(conf_match.group(1)) if conf_match else 50,
                "reasoning": "Rescued via Regex from broken JSON output."
            }
        return None

async def call_hermes_gateway(payload: dict, broadcast_callback=None, session_name="apex_trader") -> dict:
    \"\"\"
    Loops through the multi-tier fallback architecture.
    \"\"\"
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
            "reasoning": "Loading DOM and macro sensors into working memory...\\nChecking endpoints..."
        }))

    endpoints = [
        {
            "name": "HERMES_WSL",
            "url": os.getenv("HERMES_WSL_URL", "http://127.0.0.1:8080/v1/chat/completions"),
            "key": os.getenv("HERMES_WSL_API_KEY", "lm-studio"),
            "model": "hermes-3-llama-3.1-8b",
            "timeout": 60
        },
        {
            "name": "NVIDIA_NIM_PROXY",
            "url": os.getenv("FORGE_PROXY_URL", "http://localhost:8081/v1/chat/completions"),
            "key": os.getenv("NVIDIA_API_KEY", ""),
            "model": "meta/llama-3.1-70b-instruct",
            "timeout": 120
        },
        {
            "name": "OPENCODEX",
            "url": os.getenv("OPENCODEX_URL", "https://api.opencodex.dev/v1/chat/completions"),
            "key": os.getenv("OPENCODEX_API_KEY", "opencodex"),
            "model": "hermes-3-llama-3.1-8b",
            "timeout": 60
        },
        {
            "name": "MIMO",
            "url": os.getenv("MIMO_URL", "https://api.mimo.ai/v1/chat/completions"),
            "key": os.getenv("MIMO_API_KEY", "mimo"),
            "model": "hermes-3-llama-3.1-8b",
            "timeout": 60
        },
        {
            "name": "OPENROUTER",
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "key": os.getenv("OPENROUTER_API_KEY", ""),
            "model": "nousresearch/hermes-3-llama-3.1-405b",
            "timeout": 60
        },
        {
            "name": "OLLAMA",
            "url": os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/v1/chat/completions"),
            "key": "ollama",
            "model": "hermes3",
            "timeout": 60
        },
        {
            "name": "LM_STUDIO",
            "url": os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1/chat/completions"),
            "key": os.getenv("LM_STUDIO_API_KEY", "lm-studio"),
            "model": "hermes-3-llama-3.1-8b",
            "timeout": 60
        }
    ]

    async with aiohttp.ClientSession() as session:
        for ep in endpoints:
            print(f"[{session_name.upper()}] Attempting endpoint: {ep['name']} ({ep['url']})")
            headers = {"Content-Type": "application/json"}
            if ep['key']:
                headers["Authorization"] = f"Bearer {ep['key']}"
            
            req_payload = {
                "model": ep["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "stream": False
            }
            
            try:
                async with session.post(ep["url"], json=req_payload, headers=headers, timeout=ep["timeout"]) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data["choices"][0]["message"].get("content", "")
                        if not content and "reasoning_content" in data["choices"][0]["message"]:
                            content = data["choices"][0]["message"]["reasoning_content"]
                        
                        result = await _clean_json_response(content)
                        if result:
                            if broadcast_callback:
                                await broadcast_callback({
                                    "type": "hermes_activity",
                                    "agent_status": "complete",
                                    "message": f"Evaluation complete via {ep['name']}.",
                                    "reasoning": f"Final Decision: {result.get('decision', 'UNKNOWN')} | Confidence: {result.get('confidence', 0)}%"
                                })
                            return result
                        else:
                            print(f"[{session_name.upper()}] {ep['name']} returned invalid JSON.")
                    else:
                        error_text = await resp.text()
                        print(f"[{session_name.upper()}] {ep['name']} HTTP {resp.status}: {error_text[:100]}")
                        
            except Exception as e:
                print(f"[{session_name.upper()}] {ep['name']} Exception: {str(e)}")
            
            if broadcast_callback:
                await broadcast_callback({
                    "type": "hermes_activity",
                    "agent_status": "generating_strategy",
                    "message": f"{ep['name']} failed. Cycling to next endpoint...",
                    "reasoning": "Endpoint timeout or error. Engaging cascade fallback."
                })
                
    # If all fail, return a HOLD
    print(f"[{session_name.upper()}] ALL ENDPOINTS FAILED. Returning HOLD.")
    return {"decision": "HOLD", "confidence": 0, "reasoning": "All AI endpoints failed in the fallback cycle."}

"""
    content = before + replacement + "\n" + after

content = content.replace(
    'return await call_lm_studio_direct(macro_prompt)',
    'return await call_hermes_gateway({"messages": [{"role": "user", "content": macro_prompt}]}, broadcast_callback, session_name="apex_macro")'
)

content = content.replace(
    'return await call_lm_studio_direct(scalper_prompt)',
    'return await call_hermes_gateway({"messages": [{"role": "user", "content": scalper_prompt}]}, broadcast_callback, session_name="apex_scalper")'
)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Patch successful!")
