import logging
import pandas as pd
import MetaTrader5 as mt5
import asyncio
from datetime import datetime, timedelta

# Setup basic logging for the MT5 Engine
logger = logging.getLogger("MT5_Engine")
logger.setLevel(logging.INFO)
_symbol_resolution_cache = {}

# Cross-broker base-name aliases: maps XMGlobal-style names to standard names
# so fuzzy matching works regardless of which broker is connected.
_BASE_NAME_ALIASES = {
    "GOLD": "XAUUSD",
    "SILVER": "XAGUSD",
    "XAUEUR": "XAUUSD",   # Fallback if XAUEUR not available
    "XAUJPY": "XAUUSD",   # Fallback if XAUJPY not available
    "GAUUSD": "XAUUSD",   # Galliano gold alias
    "US30CASH": "US30",
    "US100CASH": "NAS100",
    "US500CASH": "SPX500",
    "JP225CASH": "JAP225",
    "GER40CASH": "GER40",
    "OILCASH": "WTI",
    "BRENTCASH": "BRENT",
    "DJ30": "US30",
}

def _resolve_tradeable_symbol(requested_symbol: str) -> str:
    """
    Robust symbol resolver - Maps requested symbols to the correct broker suffix.
    Supports multiple brokers (XMGlobal, GoatFunded, etc.) via suffix probing
    and base-name aliasing.
    Returns the exact symbol if it exists in MT5.
    """
    requested = (requested_symbol or "").strip()
    if not requested:
        requested = "XAUUSD.x"

    cached = _symbol_resolution_cache.get(requested)
    if cached:
        return cached

    # 1. Try exact match first
    info = mt5.symbol_info(requested)
    if info is not None:
        if not info.visible:
            mt5.symbol_select(requested, True)
        _symbol_resolution_cache[requested] = requested
        return requested

    all_symbols_raw = mt5.symbols_get() or []
    symbol_by_upper = {s.name.upper(): s.name for s in all_symbols_raw}

    case_match = symbol_by_upper.get(requested.upper())
    if case_match:
        logger.info(f"Case-insensitive matched '{requested}' to '{case_match}'")
        if not mt5.symbol_info(case_match).visible:
            mt5.symbol_select(case_match, True)
        _symbol_resolution_cache[requested] = case_match
        return case_match

    # 2. Strip all known suffixes to get the base symbol
    base_symbol = requested.upper().replace(".I#", "").replace("#", "").replace(".I", "").replace(".X", "")

    # 3. Check cross-broker aliases (e.g., GOLD -> XAUUSD, US30CASH -> US30)
    base_candidates = [base_symbol]
    alias = _BASE_NAME_ALIASES.get(base_symbol)
    if alias:
        base_candidates.append(alias)

    # 4. Preferred suffixes — ordered by most common broker conventions
    preferred_suffixes = [".x", "#", ".i#", "i", ".c", ".pro", ""]

    for base in base_candidates:
        for suffix in preferred_suffixes:
            test_sym = base + suffix
            matched_sym = symbol_by_upper.get(test_sym.upper())
            if matched_sym:
                logger.info(f"Fuzzy matched '{requested}' to '{matched_sym}' (base: {base}, suffix: {suffix})")
                if not mt5.symbol_info(matched_sym).visible:
                    mt5.symbol_select(matched_sym, True)
                _symbol_resolution_cache[requested] = matched_sym
                return matched_sym

    # Fallback: return as-is (callers handle missing tick safely)
    logger.warning(f"Symbol '{requested}' not found in MT5 Market Watch. Using as-is.")
    return requested

async def init_mt5(account_id: int, password: str, server: str) -> bool:
    """
    Initializes the MetaTrader 5 terminal and attempts to login.
    Returns True if successful, False otherwise.
    """
    logger.info(f"Attempting to initialize MT5 for account: {account_id} on server: {server}")
    
    for attempt in range(3):
        # Initialize the MT5 terminal with 60000ms timeout
        if not mt5.initialize(login=account_id, password=password, server=server, timeout=60000):
            error = mt5.last_error()
            logger.error(f"MT5 initialization failed on attempt {attempt+1}. Error code: {error}")
            if error and error[0] == -10005:
                print("[WARNING] IPC Timeout. Ensure MT5 is physically open and run PM2 as Administrator.")
            if attempt < 2:
                await asyncio.sleep(2)
                continue
            return False
            
        # Attempt to login
        authorized = mt5.login(login=account_id, password=password, server=server)
        
        if authorized:
            logger.info("Successfully connected to MT5 account.")
            return True
        else:
            error = mt5.last_error()
            logger.error(f"Failed to connect to MT5 account #{account_id}. Error code: {error}")
            return False
            
    return False

async def get_mt5_balance() -> float:
    """
    Retrieves the free margin (balance) of the connected MT5 account.
    """
    account_info = mt5.account_info()
    if account_info is None:
        error = mt5.last_error()
        logger.error(f"Failed to retrieve account info. Error code: {error}")
        return 0.0
        
    return float(account_info.margin_free)

_ipc_error_logged = False

async def get_mt5_positions() -> list[dict]:
    """
    Fetches all open positions and maps them to a standardized dictionary format.
    """
    global _ipc_error_logged
    if mt5.terminal_info() is None:
        if not _ipc_error_logged:
            logger.error("(-10004) MT5 IPC connection dead. Fallback empty state.")
            _ipc_error_logged = True
        return []
    _ipc_error_logged = False
    
    positions = mt5.positions_get()
    
    if positions is None:
        error = mt5.last_error()
        logger.error(f"Failed to get positions. Error code: {error}")
        return []
        
    mapped_positions = []
    for pos in positions:
        # Map MT5 position type to 'long' or 'short' string
        side = "long" if pos.type == mt5.ORDER_TYPE_BUY else "short"
        
        mapped_positions.append({
            "symbol": pos.symbol,
            "qty": pos.volume,
            "entry": pos.price_open,
            "current": pos.price_current,
            "pnl": pos.profit,
            "side": side,
            "ticket": pos.ticket,
            "sl": float(pos.sl or 0.0),
            "tp": float(pos.tp or 0.0),
            "swap": float(getattr(pos, "swap", 0.0) or 0.0),
            "status": "active",
        })
        
    return mapped_positions

async def execute_mt5_order(symbol: str, side: str, lot_size: float, sl: float = None, tp: float = None) -> dict:
    """
    Executes a market order on MT5.
    """
    # Resolve broker-specific symbol name (e.g., GOLD.i# -> XAUUSD.x on GoatFunded)
    symbol = _resolve_tradeable_symbol(symbol)
    account_info = mt5.account_info()
    if account_info is None:
        error = mt5.last_error()
        print(f"[MT5 REJECTION] account_info() failed before order_send(). MT5 Error Code: {error}")
        logger.error(f"Failed to retrieve account info before order_send(). Error code: {error}")
        return {"success": False, "error": f"Failed to get account info, error: {error}"}

    if account_info.margin_free < 10.0:
        print(f"[MARGIN LOCK] Insufficient free margin (${account_info.margin_free:.2f}). Halting new entry for {symbol}.")
        logger.warning(
            f"Margin lock blocked {symbol} entry. Free margin: {account_info.margin_free}, "
            f"balance: {account_info.balance}"
        )
        return {"success": False, "error": "Insufficient free margin"}

    # 1. Fetch current tick to get Bid/Ask
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        error = mt5.last_error()
        logger.error(f"Failed to retrieve tick data for {symbol}. Error code: {error}")
        return {"success": False, "error": f"Failed to get tick data, error: {error}"}
        
    # Determine order type and execution price
    side_normalized = side.lower()
    is_buy = side_normalized in ("long", "buy")
    order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
    price = tick.ask if is_buy else tick.bid
    
    # 2. Construct the request dictionary
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lot_size),
        "type": order_type,
        "price": price,
        "sl": 0.0,
        "tp": 0.0,
        "deviation": 20, # Slippage deviation in points
        "magic": 100100, # Magic number to identify orders
        "comment": "Apex Exec",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC, # Using IOC as requested (can fallback to ORDER_FILLING_FOK depending on broker)
    }
         
    logger.info(f"Sending MT5 order request: {request}")
    
    # 3. Send the order
    result = mt5.order_send(request)
    
    # 4. Strict Error Handling
    if result is None:
        error = mt5.last_error()
        print(f"[MT5 REJECTION] order_send() failed. MT5 Error Code: {error}")
        logger.error(f"order_send() completely failed for {symbol}. Error code: {error}")
        return {"success": False, "error": f"order_send failed, error: {error}"}
        
    # Check if the trade execution returned an error retcode (10009 is TRADE_RETCODE_DONE)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[MT5 REJECTION] Trade rejected by broker. Retcode: {result.retcode} | Comment: {result.comment}")
        logger.error(f"Order failed! Retcode: {result.retcode}, Comment: {result.comment}")
        return {"success": False, "error": result.comment}
        
    ticket = result.order
    print(f"[EXECUTION] Step 1: Market Order filled (Ticket: {ticket})")
    logger.info(f"Market order successfully placed! Ticket: {ticket}")

    if sl is None and tp is None:
        print(f"[EXECUTION] Step 2: No SL/TP supplied for ticket {ticket}; protection attach skipped.")
        return {"success": True, "order_id": ticket, "result": {"order_id": ticket}, "protection_attached": False}

    modify_request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "symbol": symbol,
        "sl": float(sl) if sl is not None else 0.0,
        "tp": float(tp) if tp is not None else 0.0,
    }
    logger.info(f"Attaching SL/TP for ticket {ticket}: {modify_request}")

    modify_result = mt5.order_send(modify_request)
    if modify_result is None:
        error = mt5.last_error()
        print(f"[MT5 REJECTION] SL/TP attach order_send() failed. MT5 Error Code: {error}")
        logger.error(f"SL/TP attach failed for ticket {ticket}. Error code: {error}")
        return {"success": True, "order_id": ticket, "result": {"order_id": ticket}, "protection_attached": False, "protection_error": f"order_send failed, error: {error}"}

    if modify_result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[MT5 REJECTION] SL/TP attach rejected by broker. Retcode: {modify_result.retcode} | Comment: {modify_result.comment}")
        logger.error(f"SL/TP attach failed for ticket {ticket}. Retcode: {modify_result.retcode}, Comment: {modify_result.comment}")
        return {"success": True, "order_id": ticket, "result": {"order_id": ticket}, "protection_attached": False, "protection_error": modify_result.comment}

    print("[EXECUTION] Step 2: SL/TP attached successfully.")
    print(f"[TRADE:SUCCESS] Ticket: {ticket}")
    logger.info(f"SL/TP attached successfully for ticket {ticket}")
    return {"success": True, "order_id": ticket, "result": {"order_id": ticket}, "protection_attached": True}


async def place_mt5_limit_order(symbol: str, side: str, lot_size: float, limit_price: float, sl: float = None, tp: float = None) -> dict:
    """
    Executes a limit order (pending order) on MT5 at a specific price.
    """
    symbol = _resolve_tradeable_symbol(symbol)
    
    # Tick info
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {"success": False, "error": f"Failed to get tick data, error: {mt5.last_error()}"}
        
    side_normalized = side.lower()
    is_buy = side_normalized in ("long", "buy")
    order_type = mt5.ORDER_TYPE_BUY_LIMIT if is_buy else mt5.ORDER_TYPE_SELL_LIMIT
    
    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": float(lot_size),
        "type": order_type,
        "price": float(limit_price),
        "sl": float(sl) if sl is not None else 0.0,
        "tp": float(tp) if tp is not None else 0.0,
        "deviation": 20,
        "magic": 100100,
        "comment": "Apex Limit",
        "type_time": mt5.ORDER_TIME_GTC,
    }
    
    logger.info(f"Sending MT5 limit order request: {request}")
    result = mt5.order_send(request)
    
    if result is None:
        return {"success": False, "error": f"order_send failed, error: {mt5.last_error()}"}
        
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {"success": False, "error": result.comment}
        
    return {"success": True, "order_id": result.order, "result": {"order_id": result.order}}


async def cancel_mt5_pending_order(ticket: int) -> dict:
    """Cancels a pending order."""
    request = {
        "action": mt5.TRADE_ACTION_REMOVE,
        "order": ticket,
    }
    result = mt5.order_send(request)
    if result is None:
        return {"success": False, "error": f"order_send failed: {mt5.last_error()}"}
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {"success": False, "error": result.comment}
    return {"success": True}


async def get_mt5_pending_orders() -> list:
    """Retrieves all pending limit/stop orders matching magic 100100."""
    orders = mt5.orders_get()
    if orders is None:
        return []
        
    pending = []
    for o in orders:
        if getattr(o, "magic", 0) != 100100:
            continue
        # Check if it's a limit or stop order
        t = getattr(o, "type", -1)
        if t in (mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT, mt5.ORDER_TYPE_BUY_STOP, mt5.ORDER_TYPE_SELL_STOP):
            pending.append({
                "ticket": o.ticket,
                "symbol": o.symbol,
                "type": t,
                "volume": o.volume_initial,
                "price": o.price_open,
                "sl": o.sl,
                "tp": o.tp,
                "time_setup": o.time_setup
            })
    return pending


async def close_mt5_position(ticket: int, symbol: str = None, volume: float = None, side: str = None) -> dict:
    """
    Close a single MT5 position by ticket number.
    Automatically determines the opposite order type from the position.
    
    Args:
        ticket: Position ticket to close
        symbol: Override symbol (auto-detected from position if None)
        volume: Override volume (auto-detected from position if None)
        side: Override side 'long'/'short' (auto-detected from position if None)
    """
    # If we don't have full info, look up the position
    if not symbol or not volume or not side:
        positions = mt5.positions_get(ticket=ticket)
        if not positions or len(positions) == 0:
            return {"success": False, "error": f"Position ticket {ticket} not found"}
        pos = positions[0]
        symbol = symbol or pos.symbol
        volume = volume or pos.volume
        side = side or ("long" if pos.type == mt5.ORDER_TYPE_BUY else "short")
    
    # Resolve broker-specific symbol name
    symbol = _resolve_tradeable_symbol(symbol)
    
    # Close = opposite direction
    close_is_buy = (side == "short")
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        error = mt5.last_error()
        logger.error(f"No tick data for {symbol} when closing ticket {ticket}. Error: {error}")
        return {"success": False, "error": f"No tick for {symbol}: {error}"}
    
    close_request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": int(ticket),
        "symbol": symbol,
        "volume": float(volume),
        "type": mt5.ORDER_TYPE_BUY if close_is_buy else mt5.ORDER_TYPE_SELL,
        "price": tick.ask if close_is_buy else tick.bid,
        "deviation": 20,
        "magic": 100100,
        "comment": "Apex Close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    logger.info(f"Closing position ticket {ticket}: {close_request}")
    result = mt5.order_send(close_request)
    
    if result is None:
        error = mt5.last_error()
        logger.error(f"Close order_send() failed for ticket {ticket}. Error: {error}")
        return {"success": False, "error": f"Close failed: {error}"}
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"Close rejected for ticket {ticket}. Retcode: {result.retcode}, Comment: {result.comment}")
        return {"success": False, "error": result.comment}
    
    logger.info(f"Position ticket {ticket} closed successfully. Order: {result.order}")
    return {"success": True, "order_id": result.order, "ticket": ticket}

def calculate_basket_vwap(symbol_positions: list) -> float:
    """
    Calculates the Volume-Weighted Average Price (VWAP) across all individual MT5 position tickets 
    for a specific symbol basket.
    
    Expected format for symbol_positions: list of dicts with 'qty' and 'entry' keys.
    """
    total_qty = 0.0
    total_notional = 0.0
    
    for pos in symbol_positions:
        qty = pos.get('qty', 0.0)
        entry = pos.get('entry', 0.0)
        
        if qty > 0 and entry > 0:
            total_qty += qty
            total_notional += (qty * entry)
            
    if total_qty == 0.0:
        return 0.0
        
    return total_notional / total_qty

async def modify_mt5_position_sl_tp(ticket: int, sl: float, tp: float) -> dict:
    """
    Sends an MT5 TRADE_ACTION_SLTP modification request to update an individual ticket.
    """
    # Create the request
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "sl": float(sl) if sl else 0.0,
        "tp": float(tp) if tp else 0.0
    }
    
    logger.info(f"Sending SL/TP modification for ticket {ticket}: SL={sl}, TP={tp}")
    
    # Send order to MT5
    result = mt5.order_send(request)
    
    if result is None:
        error = mt5.last_error()
        print(f"[MT5 REJECTION] SL/TP order_send() failed. MT5 Error Code: {error}")
        logger.error(f"modify_mt5_position_sl_tp() failed for ticket {ticket}. Error: {error}")
        return {"success": False, "error": f"order_send failed: {error}"}
        
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[MT5 REJECTION] SL/TP rejected by broker. Retcode: {result.retcode} | Comment: {result.comment}")
        logger.error(f"Modification failed! Retcode: {result.retcode}, Comment: {result.comment}")
        return {"success": False, "error": result.comment}
        
    print(f"[TRADE:SUCCESS] SL/TP updated for ticket: {ticket}")
    logger.info(f"Successfully updated SL/TP for ticket {ticket}")
    return {"success": True, "result": result}


async def get_mt5_closed_position_details(position_ticket: int, lookback_days: int = 14) -> dict:
    """Read closed-position details from the local MT5 terminal history by position ticket."""
    if not position_ticket:
        return {}

    date_to = datetime.now()
    date_from = date_to - timedelta(days=lookback_days)

    deals = mt5.history_deals_get(date_from, date_to)
    if deals is None:
        logger.error(f"history_deals_get() failed for ticket {position_ticket}. Error: {mt5.last_error()}")
        return {}

    ticket_str = str(position_ticket)
    matched = [d for d in deals if str(getattr(d, "position_id", "")) == ticket_str]
    if not matched:
        return {}

    matched.sort(key=lambda d: getattr(d, "time", 0))
    entry_in = getattr(mt5, "DEAL_ENTRY_IN", 0)
    entry_out = getattr(mt5, "DEAL_ENTRY_OUT", 1)
    entry_inout = getattr(mt5, "DEAL_ENTRY_INOUT", 2)
    type_buy = getattr(mt5, "DEAL_TYPE_BUY", 0)

    entry_deals = [d for d in matched if getattr(d, "entry", None) in (entry_in, entry_inout)]
    exit_deals = [d for d in matched if getattr(d, "entry", None) in (entry_out, entry_inout)]
    entry_deal = entry_deals[0] if entry_deals else matched[0]
    exit_deal = exit_deals[-1] if exit_deals else matched[-1]

    pnl = sum(
        float(getattr(d, "profit", 0.0) or 0.0)
        + float(getattr(d, "commission", 0.0) or 0.0)
        + float(getattr(d, "swap", 0.0) or 0.0)
        for d in matched
    )

    return {
        "ticket": position_ticket,
        "symbol": getattr(exit_deal, "symbol", "") or getattr(entry_deal, "symbol", ""),
        "side": "long" if getattr(entry_deal, "type", None) == type_buy else "short",
        "entry_price": float(getattr(entry_deal, "price", 0.0) or 0.0),
        "exit_price": float(getattr(exit_deal, "price", 0.0) or 0.0),
        "volume": float(getattr(entry_deal, "volume", 0.0) or 0.0),
        "pnl": round(pnl, 4),
        "exit_time": datetime.fromtimestamp(getattr(exit_deal, "time", 0)).isoformat() if getattr(exit_deal, "time", 0) else datetime.now().isoformat(),
        "exit_reason_code": getattr(exit_deal, "reason", -1),
    }


async def get_mt5_closed_trades(lookback_days: int = 365, account_name: str = "XMGlobal") -> list[dict]:
    """Return closed trade rows from the local XM MT5 terminal history, grouped by position ticket.
    
    IMPORTANT: MT5 terminal must have History tab set to 'All History' for full data.
    Uses lookback_days=365 (ALL history) and date_to = now + 1 day to guarantee
    today's latest deals are always captured regardless of timezone offset.
    """
    date_to = datetime.now() + timedelta(days=1)  # +1 day to capture ALL of today's deals
    date_from = date_to - timedelta(days=lookback_days + 1)
    deals = mt5.history_deals_get(date_from, date_to)
    if deals is None:
        logger.error(f"history_deals_get() failed. Error: {mt5.last_error()}")
        return []

    entry_in = getattr(mt5, "DEAL_ENTRY_IN", 0)
    entry_out = getattr(mt5, "DEAL_ENTRY_OUT", 1)
    entry_inout = getattr(mt5, "DEAL_ENTRY_INOUT", 2)
    type_buy = getattr(mt5, "DEAL_TYPE_BUY", 0)
    reason_sl = getattr(mt5, "DEAL_REASON_SL", 4)
    reason_tp = getattr(mt5, "DEAL_REASON_TP", 5)

    grouped = {}
    for deal in deals:
        symbol = getattr(deal, "symbol", "") or ""
        position_id = getattr(deal, "position_id", 0) or 0
        if not symbol or not position_id:
            continue
        grouped.setdefault(position_id, []).append(deal)

    rows = []
    for position_id, position_deals in grouped.items():
        position_deals.sort(key=lambda d: getattr(d, "time", 0))
        entry_deals = [d for d in position_deals if getattr(d, "entry", None) in (entry_in, entry_inout)]
        exit_deals = [d for d in position_deals if getattr(d, "entry", None) in (entry_out, entry_inout)]
        if not exit_deals:
            continue

        entry_deal = entry_deals[0] if entry_deals else position_deals[0]
        exit_deal = exit_deals[-1]
        pnl = sum(
            float(getattr(d, "profit", 0.0) or 0.0)
            + float(getattr(d, "commission", 0.0) or 0.0)
            + float(getattr(d, "swap", 0.0) or 0.0)
            for d in position_deals
        )
        fees = abs(sum(float(getattr(d, "commission", 0.0) or 0.0) for d in position_deals))
        close_reason = "manual"
        exit_reason = getattr(exit_deal, "reason", None)
        if exit_reason == reason_tp:
            close_reason = "tp"
        elif exit_reason == reason_sl:
            close_reason = "sl"

        rows.append({
            "id": int(position_id),
            "account_name": account_name,
            "symbol": getattr(exit_deal, "symbol", "") or getattr(entry_deal, "symbol", ""),
            "side": "LONG" if getattr(entry_deal, "type", None) == type_buy else "SHORT",
            "entry_price": float(getattr(entry_deal, "price", 0.0) or 0.0),
            "exit_price": float(getattr(exit_deal, "price", 0.0) or 0.0),
            "entry_time": datetime.fromtimestamp(getattr(entry_deal, "time", 0)).isoformat() if getattr(entry_deal, "time", 0) else None,
            "exit_time": datetime.fromtimestamp(getattr(exit_deal, "time", 0)).isoformat() if getattr(exit_deal, "time", 0) else None,
            "contracts": float(getattr(entry_deal, "volume", 0.0) or 0.0),
            "leverage": 10,
            "sl_price": 0.0,
            "tp_price": 0.0,
            "pnl": round(pnl, 4),
            "fees": round(fees, 4),
            "close_reason": close_reason,
            "status": "closed",
            "order_id": str(position_id),
            "dry_run": False,
            "ai_reasoning": "XM MT5 local account history",
        })

    rows.sort(key=lambda r: r.get("exit_time") or "", reverse=True)
    logger.info(f"[MT5-HISTORY] Loaded {len(rows)} closed trades from MT5 (lookback: {lookback_days} days, deals: {len(deals)})")
    return rows


def build_performance_stats_from_trades(trades: list[dict]) -> dict:
    """Build comprehensive performance stats from MT5 trade history.
    Includes today's trades, profit factor, and per-account breakdown.
    """
    closed = [t for t in trades if t.get("status") == "closed"]
    winners = [t for t in closed if float(t.get("pnl", 0) or 0) > 0]
    losers = [t for t in closed if float(t.get("pnl", 0) or 0) <= 0]
    total_pnl = sum(float(t.get("pnl", 0) or 0) for t in closed)
    total_fees = sum(float(t.get("fees", 0) or 0) for t in closed)
    
    # Today's trades — filter by exit_time matching today's date
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_closed = [t for t in closed if (t.get("exit_time") or "").startswith(today_str)]
    today_pnl = sum(float(t.get("pnl", 0) or 0) for t in today_closed)
    today_winners = [t for t in today_closed if float(t.get("pnl", 0) or 0) > 0]
    
    # Profit Factor = Gross Wins / |Gross Losses|
    gross_wins = sum(float(t.get("pnl", 0) or 0) for t in winners)
    gross_losses = abs(sum(float(t.get("pnl", 0) or 0) for t in losers))
    profit_factor = round(gross_wins / gross_losses, 2) if gross_losses > 0 else (999.0 if gross_wins > 0 else 0.0)
    
    close_reasons = {}
    accounts = {}
    for t in closed:
        reason = t.get("close_reason") or "unknown"
        close_reasons[reason] = close_reasons.get(reason, 0) + 1
        acct = t.get("account_name") or "XMGlobal"
        row = accounts.setdefault(acct, {"account_name": acct, "trades": 0, "pnl": 0.0, "fees": 0.0, "wins": 0,
                                          "today_trades": 0, "today_pnl": 0.0})
        row["trades"] += 1
        row["pnl"] += float(t.get("pnl", 0) or 0)
        row["fees"] += float(t.get("fees", 0) or 0)
        if float(t.get("pnl", 0) or 0) > 0:
            row["wins"] += 1
        # Today per-account
        if (t.get("exit_time") or "").startswith(today_str):
            row["today_trades"] += 1
            row["today_pnl"] += float(t.get("pnl", 0) or 0)

    pnl_values = [float(t.get("pnl", 0) or 0) for t in closed]
    return {
        "total_trades": len(closed),
        "open_trades": 0,
        "winners": len(winners),
        "losers": len(losers),
        "win_rate": round((len(winners) / len(closed)) * 100, 1) if closed else 0,
        "loss_rate": round((len(losers) / len(closed)) * 100, 1) if closed else 0,
        "total_pnl": round(total_pnl, 4),
        "total_fees": round(total_fees, 4),
        "net_pnl": round(total_pnl, 4),
        "profit_factor": profit_factor,
        "avg_win": round(sum(float(t.get("pnl", 0) or 0) for t in winners) / len(winners), 4) if winners else 0,
        "avg_loss": round(sum(float(t.get("pnl", 0) or 0) for t in losers) / len(losers), 4) if losers else 0,
        "best_trade": round(max(pnl_values), 4) if pnl_values else 0,
        "worst_trade": round(min(pnl_values), 4) if pnl_values else 0,
        # Today's stats
        "today_trades": len(today_closed),
        "today_pnl": round(today_pnl, 4),
        "today_winners": len(today_winners),
        "today_win_rate": round((len(today_winners) / len(today_closed)) * 100, 1) if today_closed else 0,
        "close_reasons": close_reasons,
        "accounts": [
            {
                "account_name": v["account_name"],
                "trades": v["trades"],
                "pnl": round(v["pnl"], 4),
                "fees": round(v["fees"], 4),
                "win_rate": round((v["wins"] / v["trades"]) * 100, 1) if v["trades"] else 0,
                "today_trades": v["today_trades"],
                "today_pnl": round(v["today_pnl"], 4),
            }
            for v in accounts.values()
        ],
        "source": "xm_mt5_history",
    }


def build_chart_from_trades(trades: list[dict]) -> list[dict]:
    ordered = sorted([t for t in trades if t.get("status") == "closed"], key=lambda t: t.get("exit_time") or "")
    cumulative = 0.0
    chart = []
    for t in ordered:
        pnl = float(t.get("pnl", 0) or 0)
        cumulative += pnl
        chart.append({
            "id": t.get("id"),
            "account": t.get("account_name"),
            "time": t.get("exit_time"),
            "pnl": round(pnl, 4),
            "cumulative_pnl": round(cumulative, 4),
            "fees": float(t.get("fees", 0) or 0),
            "reason": t.get("close_reason"),
            "symbol": t.get("symbol"),
            "side": t.get("side"),
        })
    return chart


async def get_live_price(symbol: str = "GOLD.i#") -> dict:
    """
    Fetches the live tick price for a given symbol from MT5.
    """
    global _ipc_error_logged
    if mt5.terminal_info() is None:
        if not _ipc_error_logged:
            logger.error("(-10004) MT5 IPC connection dead. Fallback empty state.")
            _ipc_error_logged = True
        return {"symbol": symbol, "ask": 0.0, "bid": 0.0, "last": 0.0}
    _ipc_error_logged = False
    
    resolved_symbol = _resolve_tradeable_symbol(symbol)
    tick = mt5.symbol_info_tick(resolved_symbol)
    if tick is None:
        error = mt5.last_error()
        logger.error(f"Failed to get live price for {resolved_symbol}. Error: {error}")
        return {"symbol": resolved_symbol, "ask": 0.0, "bid": 0.0, "last": 0.0}
        
    last_val = tick.last
    if last_val <= 0.0 and tick.bid > 0.0:
        last_val = (tick.bid + tick.ask) / 2.0
        
    info = mt5.symbol_info(resolved_symbol)
    price_change_pct = info.price_change if info and hasattr(info, 'price_change') else 0.0
    volume = info.volume if info and hasattr(info, 'volume') else 0.0
    high_price = info.session_high if info and hasattr(info, 'session_high') else (info.bidhigh if info and hasattr(info, 'bidhigh') else 0.0)
    low_price = info.session_low if info and hasattr(info, 'session_low') else (info.bidlow if info and hasattr(info, 'bidlow') else 0.0)
    
    return {
        "symbol": resolved_symbol, 
        "ask": tick.ask, 
        "bid": tick.bid, 
        "last": last_val,
        "price_change_pct": price_change_pct,
        "volume": volume,
        "high_price": high_price,
        "low_price": low_price
    }
