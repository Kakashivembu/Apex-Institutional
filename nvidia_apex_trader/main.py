import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import asyncio
import os
import json
import time
import requests
from dotenv import load_dotenv

from core.data import fetch_multi_timeframe
from core.memory import load_memory, append_to_memory
from core.brain import evaluate_market, reflect_on_trade
from core.exchange import get_available_balance, execute_order, get_open_positions, get_delta_url
import key_manager

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

# Get active keys from database instead of .env
def get_active_credentials():
    """Get the first active API key from the key manager"""
    keys = key_manager.get_active_keys()
    if keys:
        k = keys[0]
        return k.get('api_key', ''), k.get('api_secret', ''), k.get('network', 'india_testnet')
    # Fallback to .env
    return os.getenv('DELTA_TESTNET_API_KEY', ''), os.getenv('DELTA_TESTNET_API_SECRET', ''), 'india_testnet'

API_KEY, API_SECRET, NETWORK = get_active_credentials()

def get_current_mark_price(symbol):
    """Fetch mark price from Delta Exchange with strict perpetual contract matching.
    Only matches the exact 'BTCUSD' perpetual — rejects spot pairs like BTC_USDT.
    Includes $60k sanity floor to reject dead/hallucinated pairs.
    Returns 0.0 silently if no match found (Binance fallback handled upstream).
    """
    try:
        base_url = get_delta_url(NETWORK)
        r = requests.get(f"{base_url}/v2/tickers", timeout=10)
        res = r.json()
        tickers = res.get("result", [])

        # STRICT: normalize and match only the perpetual contract
        for ticker in tickers:
            sym = ticker.get("symbol", "").upper().replace("-", "").replace("_", "")
            if sym == "BTCUSD":
                price = float(ticker.get("mark_price", 0) or 0)
                # SANITY: Reject dead/hallucinated pairs with unrealistic prices
                if price < 60000:
                    print(f"[DELTA] REJECTED '{ticker.get('symbol')}' — price ${price:,.2f} below $60k sanity floor")
                    continue
                if price > 0:
                    print(f"[DELTA] Matched perpetual '{ticker.get('symbol')}' for '{symbol}' | mark_price=${price:,.2f}")
                    return price
        # No valid BTCUSD perpetual found — quietly return 0.0 (no terminal spam)
    except Exception as e:
        print(f"[DELTA] Mark price fetch error: {e}")
    return 0.0

async def execute_trade(decision_json):
    action = decision_json.get("action")
    if action == "HOLD":
        print(f"Holding. Reason: {decision_json.get('reasoning')}")
        return False

    asset = decision_json.get("asset")
    stop_loss_pct = float(decision_json.get("stop_loss_pct", 5))
    take_profit_pct = float(decision_json.get("take_profit_pct", 10))

    print(f"Executing {action} on {asset}...")
    
    margin = get_available_balance(API_KEY, API_SECRET)
    if margin <= 0:
        print(f"Error: Available Margin is {margin} or failed to fetch. Cannot trade.")
        return False

    risk_amount = margin * 0.10
    
    calc_leverage = risk_amount / stop_loss_pct if stop_loss_pct > 0 else 1
    leverage = min(100, max(1, calc_leverage))

    position_size_usd = (risk_amount / stop_loss_pct) * 100

    mark_price = get_current_mark_price(asset)
    if mark_price <= 0:
        print("Failed to fetch mark price. Aborting.")
        return False

    if action == "LONG":
        sl_price = mark_price * (1 - (stop_loss_pct/100))
        tp_price = mark_price * (1 + (take_profit_pct/100))
    else: # SHORT
        sl_price = mark_price * (1 + (stop_loss_pct/100))
        tp_price = mark_price * (1 - (take_profit_pct/100))

    if "BTC" in asset:
        contract_m, tick = 0.001, 0.1
    else:
        contract_m, tick = 0.01, 0.05

    contract_size = max(1, int(position_size_usd / (mark_price * contract_m)))
    
    sl_price = round(round(sl_price / tick) * tick, 1 if tick == 0.1 else 2)
    tp_price = round(round(tp_price / tick) * tick, 1 if tick == 0.1 else 2)

    print(f"Risk Params: Margin: ${margin:.2f} | Lev: {leverage:.1f}x | Size: {contract_size} | Entry: {mark_price}")
    print(f"Brackets: SL {sl_price} | TP {tp_price}")

    api_side = "buy" if action == "LONG" else "sell"
    res = execute_order(API_KEY, API_SECRET, asset, api_side, contract_size, sl_price, tp_price)
    print(f"Delta API Execution Result: {res}")
    
    return True

async def apex_loop():
    print("NVIDIA APEX Engine Starting...")
    while True:
        print('\n--- APEX CYCLE TICK ---')
        margin = get_available_balance(API_KEY, API_SECRET)
        print(f"\n[WALLET VERIFIED] Live Delta Testnet Margin: ${margin:.2f}")
        try:
            market_data_text = await fetch_multi_timeframe(["BTCUSD", "ETHUSD"])
            memory_text = load_memory()
            
            print("Evaluating Market Data via NVIDIA Brain...")
            decision = await evaluate_market(memory_text, market_data_text, margin)
            
            executed = await execute_trade(decision)
            
            if executed:
                print("Logging execution block for future reflection...")
                new_rule = reflect_on_trade("unknown", "unknown", "+", market_data_text[:500])
                append_to_memory(new_rule)
            
            reasoning = str(decision.get('reasoning', '')).lower()
            if 'scalp' in reasoning or 'snipe' in reasoning:
                sleep_time = 60
                print(f"Scalper Phase detected. Sleeping {sleep_time} seconds.")
            else:
                sleep_time = 600
                print(f"Swing Phase detected. Sleeping {sleep_time} seconds (10m).")
            
            await asyncio.sleep(sleep_time)

        except Exception as e:
            print(f"Critical Apex Loop Error: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(apex_loop())
