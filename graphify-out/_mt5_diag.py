"""Verify GOLD.i# is the correct gold trading symbol."""
import MetaTrader5 as mt5

if not mt5.initialize():
    print(f"MT5 init failed: {mt5.last_error()}")
    exit(1)

# Select and check GOLD.i#
mt5.symbol_select("GOLD.i#", True)
info = mt5.symbol_info("GOLD.i#")
if info:
    print(f"Symbol: {info.name}")
    print(f"  Path: {info.path}")
    print(f"  Description: {info.description}")
    print(f"  Currency base: {info.currency_base}")
    print(f"  Currency profit: {info.currency_profit}")
    print(f"  Trade mode: {info.trade_mode}")
    print(f"  Visible: {info.visible}")
    print(f"  Spread: {info.spread}")
    print(f"  Volume min: {info.volume_min}")
    
    tick = mt5.symbol_info_tick("GOLD.i#")
    if tick:
        print(f"\n  LIVE TICK: Bid={tick.bid}, Ask={tick.ask}, Last={tick.last}")
    else:
        print(f"\n  No tick (market closed/weekend). Error: {mt5.last_error()}")
    
    # Try fetching recent candles
    import datetime
    rates = mt5.copy_rates_from_pos("GOLD.i#", mt5.TIMEFRAME_H1, 0, 5)
    if rates is not None and len(rates) > 0:
        print(f"\n  Last {len(rates)} H1 candles available:")
        for r in rates:
            dt = datetime.datetime.utcfromtimestamp(r[0])
            print(f"    {dt} | O:{r[1]:.2f} H:{r[2]:.2f} L:{r[3]:.2f} C:{r[4]:.2f}")
    else:
        print(f"\n  No historical candles. Error: {mt5.last_error()}")
else:
    print("GOLD.i# not found either!")

mt5.shutdown()
