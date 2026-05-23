import MetaTrader5 as mt5
import json
import os

# Read the user's explicit UI settings from apex_parameters.json
PARAMS_FILE = os.path.join(os.path.expanduser("~"), ".apex_trader", "apex_parameters.json")
try:
    with open(PARAMS_FILE, "r") as f:
        params = json.load(f)
        ui_sl = float(params.get("base_stop_loss_pct", 0.12))
        ui_tp = float(params.get("base_take_profit_pct", 0.25))
except Exception as e:
    print(f"Failed to read parameters: {e}")
    ui_sl = 0.12
    ui_tp = 0.25

# Asset-class multiplier (Gold/Index need wider breathing room)
MULTIPLIERS = {
    "XAU": 2.5, "GOLD": 2.5,
    "XAG": 3.0, "SILVER": 3.0,
    "US30": 2.5, "US100": 2.5, "US500": 2.5, "DJ30": 2.5,
    "BTC": 5.0, "ETH": 5.0,
}

def get_multiplier(symbol):
    sym = symbol.upper()
    for key, mult in MULTIPLIERS.items():
        if key in sym:
            return mult
    return 1.0

def update_open_positions():
    print(f"Connecting to MT5...")
    print(f"UI Settings: SL={ui_sl}%, TP={ui_tp}%")
    
    if not mt5.initialize():
        print(f"Failed to initialize MT5, error: {mt5.last_error()}")
        return

    positions = mt5.positions_get()
    if positions is None or len(positions) == 0:
        print("No open positions found.")
        mt5.shutdown()
        return

    print(f"Found {len(positions)} open positions.\n")

    for pos in positions:
        ticket = pos.ticket
        symbol = pos.symbol
        pos_type = pos.type
        entry_price = pos.price_open
        current_sl = pos.sl
        current_tp = pos.tp
        
        mult = get_multiplier(symbol)
        sl_pct = ui_sl * mult
        tp_pct = ui_tp * mult
        
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            print(f"  [SKIP] Could not get symbol info for {symbol}")
            continue
            
        tick = symbol_info.point
        
        if pos_type == mt5.POSITION_TYPE_BUY:
            new_sl = round(entry_price * (1 - sl_pct / 100) / tick) * tick
            new_tp = round(entry_price * (1 + tp_pct / 100) / tick) * tick
            side = "LONG"
        elif pos_type == mt5.POSITION_TYPE_SELL:
            new_sl = round(entry_price * (1 + sl_pct / 100) / tick) * tick
            new_tp = round(entry_price * (1 - tp_pct / 100) / tick) * tick
            side = "SHORT"
        else:
            continue

        new_sl = round(new_sl, symbol_info.digits)
        new_tp = round(new_tp, symbol_info.digits)

        print(f"  Ticket #{ticket} | {side} {symbol} | Entry: {entry_price}")
        print(f"    Old SL: {current_sl} -> New SL: {new_sl}")
        print(f"    Old TP: {current_tp} -> New TP: {new_tp}")
        print(f"    Asset multiplier: {mult}x (effective SL={sl_pct}%, TP={tp_pct}%)")

        if abs(new_sl - current_sl) < tick and abs(new_tp - current_tp) < tick:
            print(f"    [OK] Already correct, skipping.\n")
            continue

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": symbol,
            "sl": new_sl,
            "tp": new_tp,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"    [FAIL] Error {result.retcode}: {result.comment}\n")
        else:
            print(f"    [OK] Modified successfully.\n")

    mt5.shutdown()
    print("Done.")

if __name__ == "__main__":
    update_open_positions()
