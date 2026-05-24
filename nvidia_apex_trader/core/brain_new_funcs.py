import aiohttp
import json
import asyncio

async def call_hermes_gateway(payload: dict, broadcast_callback=None) -> dict:
    """
    Communicates with the local Hermes API Gateway (http://127.0.0.1:8080/v1/chat/completions).
    Uses aiohttp to stream responses if requested, forwarding reasoning to the frontend via WebSocket.
    """
    url = "http://127.0.0.1:8080/v1/chat/completions"
    
    # Force streaming for real-time frontend thoughts
    payload["stream"] = True
    
    final_json_string = ""
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as response:
                if response.status != 200:
                    err = await response.text()
                    print(f"[HERMES GATEWAY] Error {response.status}: {err}")
                    return {}
                
                # Process Server-Sent Events (SSE)
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            
                            if content:
                                final_json_string += content
                                
                                # Broadcast live thoughts to the frontend
                                if broadcast_callback:
                                    # We don't await because broadcast_callback is usually a coroutine or sync
                                    # It might be an async function, so let's handle both
                                    coro = broadcast_callback({
                                        "type": "hermes_activity",
                                        "agent_status": "analyzing",
                                        "reasoning_chunk": content
                                    })
                                    if asyncio.iscoroutine(coro):
                                        asyncio.create_task(coro)
                                        
                        except json.JSONDecodeError:
                            pass
                            
        # Now parse the final collected JSON string
        return robust_json_parse(final_json_string, {"decision": "HOLD", "confidence": 0})
        
    except Exception as e:
        print(f"[HERMES GATEWAY] Connection failed: {e}. Is Hermes running on port 8080?")
        return {"decision": "HOLD", "confidence": 0}

async def evaluate_market(memory_text: str, market_data_text: str, margin: float = 0, dom_data: str = "", active_positions: list = None, force_run: bool = False, active_symbol: str = "GOLD", live_asset_price: float = 0.0, broadcast_callback=None) -> dict:
    """
    Master evaluator using the Single Continuous Hermes Pipeline.
    Combines all context (Fundamental, Macro, Scalping DOM) into one prompt.
    """
    symbol = active_symbol
    risk_profile = get_symbol_risk_profile(symbol)
    
    if broadcast_callback:
        coro = broadcast_callback({
            "type": "hermes_activity",
            "agent_status": "assembling_context",
            "message": f"Fetching full DOM and Macro context for {symbol}..."
        })
        if asyncio.iscoroutine(coro):
            asyncio.create_task(coro)

    print(f"[EVAL] Assembling continuous context for {symbol}...")

    # Build the massive unified system prompt
    system_prompt = f"""You are Antigravity Hermes, an elite institutional HFT and Macro AI agent.
You process massive amounts of quantitative data, orderbook (DOM) imbalances, and multi-timeframe trends to make unified trading decisions.

# ASSET PROFILE
Asset: {symbol}
Type: {risk_profile['class']}
Volatility: {risk_profile['vol']}
Minimum Stop Loss: {risk_profile['sl']}%

# YOUR MISSION
1. Analyze the Level 2 Orderbook (DOM) to find sniper entry points.
2. Cross-reference with H1/H4 Macro Trends to ensure you trade WITH the institutional flow.
3. Consider Open Interest, Order Flow Imbalance (OFI), and VPIN toxicity.
4. If conditions are contradictory, output HOLD. If aligned, output BUY or SELL.

# OUTPUT FORMAT (STRICT JSON ONLY)
You MUST output ONLY a valid JSON object matching this schema. NO markdown backticks, NO extra text.
{{
  "decision": "BUY" | "SELL" | "HOLD",
  "confidence": <0-100>,
  "leverage": <integer 1-20>,
  "stop_loss_pct": <float>,
  "take_profit_pct": <float>,
  "entry_price": <float, exact optimal entry based on DOM>,
  "reasoning": "Detailed institutional reasoning here"
}}
"""

    user_prompt = f"""# LIVE MARKET CONTEXT
Asset: {symbol}
Live Price: {live_asset_price}
Available Margin: ${margin}

# OPEN POSITIONS
{json.dumps(active_positions) if active_positions else "None"}

# MEMORY & PREVIOUS TRADES
{memory_text}

# MARKET DATA SENSORS (MULTI-TIMEFRAME & SENTIMENT)
{market_data_text}

# LEVEL 2 ORDERBOOK (DOM)
{dom_data}

Execute your analysis and return the final JSON trade signal.
"""

    payload = {
        "model": "hermes-gateway",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 500
    }

    if broadcast_callback:
        coro = broadcast_callback({
            "type": "hermes_activity",
            "agent_status": "generating_strategy",
            "message": f"Sent {len(system_prompt) + len(user_prompt)} bytes of context. Awaiting signal..."
        })
        if asyncio.iscoroutine(coro):
            asyncio.create_task(coro)

    # Call the local continuous Hermes Gateway
    result = await call_hermes_gateway(payload, broadcast_callback)
    
    decision = result.get("decision", "HOLD").upper()
    confidence = safe_int(result.get("confidence", 0), 0, 0, 100)
    sl_pct, tp_pct, _ = clamp_risk_to_symbol(symbol, result.get("stop_loss_pct", risk_profile["sl"]), result.get("take_profit_pct", risk_profile["tp"]))
    ai_leverage = safe_int(result.get("leverage", 10), 10, 1, 20)
    
    print(f"[HERMES] Final Signal: {decision} ({confidence}%) | SL {sl_pct}% | TP {tp_pct}%")
    
    if broadcast_callback:
        coro = broadcast_callback({
            "type": "hermes_activity",
            "agent_status": "idle",
            "message": f"Signal received: {decision} ({confidence}%)"
        })
        if asyncio.iscoroutine(coro):
            asyncio.create_task(coro)

    return {
        "action": decision,
        "confidence": confidence,
        "leverage": ai_leverage,
        "stop_loss": sl_pct,
        "take_profit": tp_pct,
        "volatility": "high" if confidence < 50 else "medium",
        "entry_price": result.get("entry_price", live_asset_price),
        "_debug": {
            "hermes_reasoning": result.get("reasoning", "")
        }
    }
