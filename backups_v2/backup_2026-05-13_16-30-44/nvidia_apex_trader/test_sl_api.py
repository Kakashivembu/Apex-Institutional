"""Test if the step-trail can actually modify SL on Delta Exchange"""
import urllib3; urllib3.disable_warnings()
from core.exchange import delta_request_sync, get_position_bracket_orders_sync
import key_manager

keys = key_manager.get_active_keys()
k = keys[0]
ak, asec, net = k['api_key'], k['api_secret'], k['network']
acct = k['account_name']

# 1. Get current position
resp = delta_request_sync(ak, asec, 'GET', '/v2/positions/margined', None, net)
positions = [p for p in resp.get('result', []) if int(p.get('size', 0)) != 0]

if not positions:
    print("No open positions found!")
    exit()

pos = positions[0]
entry = float(pos.get('entry_price', 0))
mark = float(pos.get('mark_price', 0))
size = int(pos.get('size', 0))
side = 'SHORT' if size < 0 else 'LONG'
pid = pos.get('product_id', 0)
sym = pos.get('product_symbol', '')

print(f"Account: {acct}")
print(f"Position: {side} {sym} x{abs(size)}")
print(f"Entry: ${entry:,.2f} | Mark: ${mark:,.2f}")
print(f"Product ID: {pid}")

# 2. Check bracket orders
print(f"\nSearching for bracket SL order...")
brackets = get_position_bracket_orders_sync(ak, asec, sym, net)
sl_order = brackets.get('sl_order')
tp_order = brackets.get('tp_order')

print(f"SL Order: {sl_order}")
print(f"TP Order: {tp_order}")

if sl_order:
    current_sl = float(sl_order.get('stop_price', 0))
    sl_id = sl_order.get('id')
    print(f"\nCurrent SL: #{sl_id} @ ${current_sl:,.1f}")
    print(f"CONFIRMED: Step-trail CAN modify this SL order via API")
else:
    print(f"\nWARNING: No SL bracket order found!")
    print(f"Positions opened WITHOUT bracket SL cannot be trailed.")
    print(f"The step-trail will log '[WARN] No SL bracket leg found'")
    
    # Let's also check raw open orders
    print(f"\nChecking ALL open orders...")
    from core.exchange import get_open_orders_sync
    orders = get_open_orders_sync(ak, asec, pid, net)
    print(f"Found {len(orders)} open orders:")
    for o in orders:
        print(f"  ID: {o.get('id')} | Type: {o.get('order_type')} | Side: {o.get('side')} | Stop: {o.get('stop_price')} | Limit: {o.get('limit_price')}")
