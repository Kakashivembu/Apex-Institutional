import asyncio, websockets, json

async def test():
    uri = "ws://10.112.239.41:8000"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"type": "get_state"}))
        r = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        d = r.get("data", {})
        md = d.get("market_data") or {}
        print(f"Keys in data: {sorted(d.keys())}")
        print(f"market_data present: {bool(md)}")
        if md:
            print(f"  price: {md.get('last_price', 'MISSING')}")
            print(f"  change: {md.get('price_change_pct', 'MISSING')}%")
            print(f"  volume: {md.get('volume', 'MISSING')}")
        print(f"dom present: {bool(d.get('dom'))}")
        print(f"dom_metrics present: {bool(d.get('dom_metrics'))}")
        print(f"nvidia_api_stats present: {bool(d.get('nvidia_api_stats'))}")
        print(f"trading_enabled: {d.get('trading_enabled')}")
        print(f"dry_run: {d.get('dry_run')}")

asyncio.run(test())
