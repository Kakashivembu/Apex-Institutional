import asyncio
import os
import logging
import time
from typing import List, Dict
import MetaTrader5 as mt5

from core.mt5_engine import (
    init_mt5,
    get_mt5_balance,
    get_mt5_positions,
    execute_mt5_order,
    modify_mt5_position_sl_tp,
    get_live_price
)

DRY_RUN = os.getenv("DRY_RUN", "False").lower() in ("true", "1", "yes")

async def _ensure_mt5(api_key: str, api_secret: str, network: str) -> bool:
    if not api_key or not api_secret:
        return False
    try:
        account_id = int(api_key)
        return await init_mt5(account_id, api_secret, network)
    except Exception as e:
        print(f"[MT5-BRIDGE] Init error: {e}")
        return False

def get_delta_url(network: str = "testnet") -> str:
    return "MT5_NATIVE"

# =====================================================================
# MT5 BRIDGE
# =====================================================================

async def get_real_delta_balance(api_key: str, api_secret: str, network: str = "testnet") -> float:
    if await _ensure_mt5(api_key, api_secret, network):
        return await get_mt5_balance()
    return 0.0

async def get_real_active_positions(api_key: str, api_secret: str, network: str = "testnet") -> List[Dict]:
    if not await _ensure_mt5(api_key, api_secret, network):
        return []
    
    positions = await get_mt5_positions()
    mapped_positions = []
    
    for pos in positions:
        mapped_positions.append({
            "symbol": pos["symbol"],
            "qty": pos["qty"],
            "entry": pos["entry"],
            "current": pos["current"],
            "pnl": pos["pnl"],
            "status": "active",
            "side": pos["side"],
            "leverage": 10,
            "reported_leverage": 10,
            "margin": pos["qty"] * 100, 
            "ticket": pos.get("ticket"),
            "sl": pos.get("sl", 0.0),
            "tp": pos.get("tp", 0.0),
        })
    return mapped_positions

async def execute_delta_order(api_key: str, api_secret: str, symbol: str, side: str, size: float, stop_loss: float = None, take_profit: float = None, network: str = "testnet") -> dict:
    if DRY_RUN:
        print(f"[MT5 SHADOW] {side} {size} {symbol} (SL:{stop_loss} TP:{take_profit})")
        return {"success": True, "result": {"order_id": f"SHADOW_{int(time.time())}"}}
        
    if not await _ensure_mt5(api_key, api_secret, network):
        return {"success": False, "error": "MT5 Not Connected"}
        
    res = await execute_mt5_order(symbol, side, size, stop_loss, take_profit)
    if res.get("success"):
        return {"success": True, "result": {"id": res.get("order_id"), "order_id": res.get("order_id")}}
    return res

async def set_delta_leverage(api_key: str, api_secret: str, symbol: str, leverage: int, network: str = "testnet") -> dict:
    return {"success": True, "result": {}, "applied_leverage": leverage}

async def close_delta_position(api_key: str, api_secret: str, symbol: str, network: str = "testnet") -> dict:
    pos = await get_real_active_positions(api_key, api_secret, network)
    for p in pos:
        if p["symbol"] == symbol:
            close_side = "sell" if p["side"] == "long" else "buy"
            return await execute_delta_order(api_key, api_secret, symbol, close_side, p["qty"], None, None, network)
    return {"success": False, "error": "No position"}

async def get_available_margin(api_key: str, api_secret: str, network: str = "testnet") -> dict:
    if not await _ensure_mt5(api_key, api_secret, network):
        return {
            "available_margin": 0.0, "total_balance": 0.0,
            "used_margin": 0.0, "unrealized_pnl": 0.0, "currency": "USD"
        }
    
    account_info = await asyncio.to_thread(mt5.account_info)
    if account_info is None:
        return {
            "available_margin": 0.0, "total_balance": 0.0,
            "used_margin": 0.0, "unrealized_pnl": 0.0, "currency": "USD"
        }

    pos = await get_mt5_positions()
    unrealized_pnl = sum([p["pnl"] for p in pos])

    return {
        "available_margin": float(account_info.margin_free or 0.0),
        "total_balance": float(account_info.equity or account_info.balance or 0.0),
        "used_margin": float(account_info.margin or 0.0),
        "unrealized_pnl": unrealized_pnl,
        "currency": "USD"
    }

def delta_request_sync(*args, **kwargs):
    return {"success": False, "error": "Deprecated. Use MT5 bridged async functions."}

def delta_public_get_sync(*args, **kwargs):
    import requests
    response = requests.Response()
    response.status_code = 400
    response._content = b'{"error":"Deprecated"}'
    return response

def modify_bracket_sl_sync(api_key: str, api_secret: str, order_id: int, product_id: int, new_sl_price: float, network: str = "testnet") -> dict:
    if not api_key: return {"success": False}
    # order_id in MT5 maps to the ticket
    res = asyncio.run(modify_mt5_position_sl_tp(order_id, new_sl_price, 0.0))
    return res

def get_position_bracket_orders_sync(api_key: str, api_secret: str, product_symbol: str = "BTCUSD", network: str = "testnet", side: str = None) -> dict:
    return {"sl_order": None, "tp_order": None}

def verify_position_closed_sync(api_key: str, api_secret: str, symbol: str, network: str = "testnet", product_id: int = None) -> dict:
    try:
        pos = asyncio.run(get_real_active_positions(api_key, api_secret, network))
        for p in pos:
            if p["symbol"] == symbol:
                return {"status": "open", "reason": "Position still reported by MT5"}
        return {"status": "closed", "reason": "Position absent from MT5 open positions"}
    except Exception as e:
        return {"status": "unknown", "reason": str(e)}

def get_available_balance(api_key: str, api_secret: str) -> float:
    return asyncio.run(get_real_delta_balance(api_key, api_secret, "testnet"))

def execute_order(api_key: str, api_secret: str, symbol: str, side: str, size: int, sl: float, tp: float) -> dict:
    return asyncio.run(execute_delta_order(api_key, api_secret, symbol, side, float(size), sl, tp, "testnet"))

async def get_delta_options_chain(underlying_asset: str = "BTC", network: str = "mainnet") -> dict:
    return {
        "success": False, "calls": [], "puts": [], "expiry_dates": [],
        "underlying": underlying_asset, "spot_price": 0.0, "fetched_at": int(time.time()),
        "error": "Options not supported on MT5"
    }

async def execute_options_order(*args, **kwargs) -> dict:
    return {"success": False, "error": "Options not supported on MT5"}
