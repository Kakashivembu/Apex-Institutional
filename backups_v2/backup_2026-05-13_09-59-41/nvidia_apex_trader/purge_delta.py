import os

# 1. Update mt5_engine.py
with open('core/mt5_engine.py', 'a', encoding='utf-8') as f:
    f.write('''\nasync def get_live_price(symbol: str = "GOLD") -> dict:
    """
    Fetches the live tick price for a given symbol from MT5.
    """
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        error = mt5.last_error()
        logger.error(f"Failed to get live price for {symbol}. Error: {error}")
        return {"symbol": symbol, "ask": 0.0, "bid": 0.0, "last": 0.0}
    return {"symbol": symbol, "ask": tick.ask, "bid": tick.bid, "last": tick.last}
''')

# 2. Update server.py
with open('server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace global variables
content = content.replace('live_btc_price', 'live_asset_price')
content = content.replace('live_asset_price = 0.0', 'live_asset_price = 0.0\nactive_symbol = "GOLD"')

# Remove fetch_live_btc_data (if present, replace with empty)
fetch_btc_block = '''async def fetch_live_btc_data():
    return {"last_price": 60000.0, "price_change_pct": 0.0, "volume": 0.0, "source": "MT5_Mock"}'''
content = content.replace(fetch_btc_block, '')

# Replace live_price_broadcast_loop with mt5_price_stream_loop
old_loop = '''async def live_price_broadcast_loop():
    """Fetches real-time BTC price and DOM every 3 seconds and broadcasts to UI."""
    global live_asset_price, last_dom_data, last_dom_metrics
    await asyncio.sleep(5)
    while True:
        try:
            price_data = await fetch_live_btc_data()
            global_dom = await fetch_global_liquidity("BTC/USDT")
            dom_data = global_dom.get("text", "Global DOM Imbalance: Unavailable this cycle")
            
            if dom_data:
                last_dom_metrics = {
                    "bids": global_dom.get("bids", 0.0),
                    "asks": global_dom.get("asks", 0.0),
                    "bid_pct": global_dom.get("bid_pct", 0.0),
                    "ask_pct": global_dom.get("ask_pct", 0.0),
                    "total_vol": global_dom.get("total_vol", 0.0),
                    "wall_price": global_dom.get("wall_price", 0.0),
                    "wall_size": global_dom.get("wall_size", 0.0),
                    "wall_side": global_dom.get("wall_side", "NONE"),
                    "wall_source": global_dom.get("wall_source", "N/A"),
                }
                last_dom_data = (
                    f"Global DOM X-Ray: {last_dom_metrics['bids']:.3f} BTC resting Support vs {last_dom_metrics['asks']:.3f} BTC resting Resistance. "
                    f"Imbalance: {last_dom_metrics['bid_pct']:.0f}% Bids / {last_dom_metrics['ask_pct']:.0f}% Asks. "
                    f"Aggregated Volume: {last_dom_metrics['total_vol']:.3f} BTC. "
                    f"Largest wall: {last_dom_metrics['wall_size']:.3f} BTC {last_dom_metrics['wall_side']} @ ${last_dom_metrics['wall_price']:,.2f} ({last_dom_metrics['wall_source']})."
                )
                
            if price_data and price_data.get("last_price"):
                current = price_data.get("last_price")
                live_asset_price = current
                await manager.broadcast({
                    "type": "live_price",
                    "price": current,
                    "dom": last_dom_data,
                    "dom_metrics": last_dom_metrics,
                    "timestamp": datetime.now().isoformat()
                })
        except Exception:
            pass
        await asyncio.sleep(3)'''

new_loop = '''async def mt5_price_stream_loop():
    """Fetches real-time price from MT5 every 2 seconds and broadcasts to UI."""
    global live_asset_price, active_symbol
    await asyncio.sleep(5)
    while True:
        try:
            price_data = await mt5_engine.get_live_price(active_symbol)
            if price_data and price_data.get("ask"):
                # Use ask or mid price
                current = price_data.get("ask")
                if current > 0:
                    live_asset_price = current
                    await manager.broadcast({
                        "type": "live_price",
                        "price": current,
                        "timestamp": datetime.now().isoformat()
                    })
        except Exception as e:
            print(f"[MT5 STREAM] Error: {e}")
            pass
        await asyncio.sleep(2)'''

content = content.replace(old_loop, new_loop)
content = content.replace('asyncio.create_task(live_price_broadcast_loop())', 'asyncio.create_task(mt5_price_stream_loop())')

# Update Monitor print statement
content = content.replace(
    'print(f"[MONITOR] Positions: {len(last_positions)} | Equity: ${last_equity.get(\'total\', 0):.2f} | Live BTC: ${live_asset_price:,.2f}")',
    'print(f"[MONITOR] Positions: {len(last_positions)} | Equity: ${last_equity.get(\'total\', 0):.2f} | Live {active_symbol}: ${live_asset_price:,.2f}")'
)

with open('server.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Modifications complete.")
