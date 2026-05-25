import MetaTrader5 as mt5
import time

def close_all_positions():
    if not mt5.initialize():
        print("initialize() failed")
        return
    
    positions = mt5.positions_get()
    if positions is None or len(positions) == 0:
        print("No open positions.")
        mt5.shutdown()
        return

    print(f"Closing {len(positions)} positions...")
    
    for p in positions:
        symbol_info = mt5.symbol_info(p.symbol)
        if symbol_info is None:
            continue
            
        tick = mt5.symbol_info_tick(p.symbol)
        if tick is None:
            continue
            
        action_type = mt5.ORDER_TYPE_BUY if p.type == mt5.ORDER_TYPE_SELL else mt5.ORDER_TYPE_SELL
        price = tick.ask if p.type == mt5.ORDER_TYPE_SELL else tick.bid
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": p.ticket,
            "symbol": p.symbol,
            "volume": p.volume,
            "type": action_type,
            "price": price,
            "deviation": 20,
            "magic": p.magic,
            "comment": "AI Emergency Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Failed to close {p.ticket}: retcode={result.retcode}")
        else:
            print(f"Successfully closed {p.ticket}")
            
    mt5.shutdown()

if __name__ == "__main__":
    close_all_positions()
