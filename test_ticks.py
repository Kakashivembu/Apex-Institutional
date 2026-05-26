import MetaTrader5 as mt5
from datetime import datetime, timedelta
import collections

if mt5.initialize():
    symbol = 'XAUUSD.x'
    if not mt5.symbol_info(symbol): 
        symbol = 'GOLD.i#'
    ticks = mt5.copy_ticks_from(symbol, datetime.now() - timedelta(minutes=60), 1000, mt5.COPY_TICKS_ALL)
    if ticks is not None:
        buys = sum(1 for t in ticks if t['flags'] & mt5.TICK_FLAG_BUY)
        sells = sum(1 for t in ticks if t['flags'] & mt5.TICK_FLAG_SELL)
        print(f'Total ticks: {len(ticks)}, Buys: {buys}, Sells: {sells}')
        
        flag_counts = collections.Counter(t['flags'] for t in ticks)
        print("Flag distribution:")
        for flag, count in flag_counts.items():
            print(f"Flag {flag}: {count}")
