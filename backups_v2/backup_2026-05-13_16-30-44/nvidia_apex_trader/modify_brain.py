import sys

try:
    with open('core/brain.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Replacements
    content = content.replace(
        '    print("[CLAW] Fetching live liquidity data and global DOM heatmap...")',
        '    print("[CLAW] Fetching MT5 Macro Sensors...")'
    )

    old_import = '''    from core.data import fetch_global_liquidity

    liquidity_data, global_dom = await asyncio.gather(
        fetch_liquidity_data_async(),
        fetch_global_liquidity("BTC/USDT")
    )
    global_dom_text = global_dom.get("text", "Global DOM Imbalance: Unavailable")'''

    new_import = '''    from core.macro_sensors import calculate_currency_matrix, detect_tick_velocity

    matrix_data, velocity_data = await asyncio.gather(
        calculate_currency_matrix(),
        detect_tick_velocity("BTCUSD")
    )
    
    matrix_text = f"Currency Matrix (0-100 Relative Strength): Strongest: {matrix_data['strongest']}, Weakest: {matrix_data['weakest']}"
    velocity_text = f"Tick Velocity (1M scale): High Velocity: {velocity_data['is_high_velocity']}, Ratio: {velocity_data['ratio']}x"'''

    content = content.replace(old_import, new_import)
    content = content.replace('{liquidity_data}\n{global_dom_text}', '{matrix_text}\n{velocity_text}')
    content = content.replace('f"{liquidity_data} | {global_dom_text}"', 'f"{matrix_text} | {velocity_text}"')

    with open('core/brain.py', 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Replaced successfully")
except Exception as e:
    print(f"Error: {e}")
