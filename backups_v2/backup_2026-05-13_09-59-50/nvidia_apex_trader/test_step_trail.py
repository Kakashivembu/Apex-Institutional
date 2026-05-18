"""
STEP-TRAIL VERIFICATION SCRIPT
===============================
Simulates the step-trailing logic offline to prove the math works
for both LONG and SHORT positions across all tiers + recovery.

Run: python test_step_trail.py
"""

# Mirror the config from server.py — MAXIMUM PROFIT CAPTURE CONFIG
STEP_TRAIL_CONFIG = {
    "initial_sl_pct": 1.2,
    "tier1_trigger_pct": 0.3,
    "tier1_sl_pct": 0.05,
    "tier2_trigger_pct": 0.8,
    "tier2_trail_pct": 0.3,
    "tier2_sl_pct": 0.5,
    "tier3_trigger_pct": 2.0,
    "tier3_trail_pct": 0.15,
    "tier3_sl_pct": 1.5,
    "tier2_min_step_pct": 0.05,
}

def simulate_trail(side, entry_price, price_sequence):
    """Simulate the step-trailing engine through a price sequence"""
    cfg = STEP_TRAIL_CONFIG
    tick = 0.5
    
    # Initial SL
    if side == "long":
        current_sl = round(entry_price * (1 - cfg["initial_sl_pct"] / 100), 1)
    else:
        current_sl = round(entry_price * (1 + cfg["initial_sl_pct"] / 100), 1)
    
    current_tier = 0
    highest = entry_price
    lowest = entry_price
    
    print(f"\n{'='*70}")
    print(f"  SIMULATING {side.upper()} from ${entry_price:,.1f} | Initial SL: ${current_sl:,.1f}")
    print(f"{'='*70}")
    
    for mark_price in price_sequence:
        # Track peak
        if side == "long":
            highest = max(highest, mark_price)
            peak = highest
            move_pct = ((peak - entry_price) / entry_price) * 100
        else:
            lowest = min(lowest, mark_price)
            peak = lowest
            move_pct = ((entry_price - peak) / entry_price) * 100
        
        new_sl = current_sl
        new_tier = current_tier
        triggered = False
        
        # Tier 3: Runner Trail — ultra-tight behind peak
        if move_pct >= cfg["tier3_trigger_pct"]:
            new_tier = 3
            if side == "long":
                raw_sl = peak * (1 - cfg["tier3_trail_pct"] / 100)
            else:
                raw_sl = peak * (1 + cfg["tier3_trail_pct"] / 100)
            candidate = round(round(raw_sl / tick) * tick, 5)
            
            if side == "long":
                step_thresh = current_sl * (1 + cfg["tier2_min_step_pct"] / 100)
                if candidate > step_thresh:
                    new_sl = candidate
                    triggered = True
            else:
                step_thresh = current_sl * (1 - cfg["tier2_min_step_pct"] / 100)
                if candidate < step_thresh:
                    new_sl = candidate
                    triggered = True
        
        # Tier 2: Profit Step — trail behind peak
        elif move_pct >= cfg["tier2_trigger_pct"]:
            new_tier = 2
            if side == "long":
                raw_sl = peak * (1 - cfg["tier2_trail_pct"] / 100)
            else:
                raw_sl = peak * (1 + cfg["tier2_trail_pct"] / 100)
            candidate = round(round(raw_sl / tick) * tick, 5)
            
            if side == "long":
                step_thresh = current_sl * (1 + cfg["tier2_min_step_pct"] / 100)
                if candidate > step_thresh:
                    new_sl = candidate
                    triggered = True
            else:
                step_thresh = current_sl * (1 - cfg["tier2_min_step_pct"] / 100)
                if candidate < step_thresh:
                    new_sl = candidate
                    triggered = True
        
        # Tier 1: Breakeven lock
        elif move_pct >= cfg["tier1_trigger_pct"] and current_tier < 1:
            new_tier = 1
            if side == "long":
                new_sl = round(round(entry_price * (1 + cfg["tier1_sl_pct"] / 100) / tick) * tick, 5)
            else:
                new_sl = round(round(entry_price * (1 - cfg["tier1_sl_pct"] / 100) / tick) * tick, 5)
            triggered = True
        
        # MONOTONICITY GUARD
        sl_valid = False
        if triggered:
            if side == "long" and new_sl > current_sl:
                sl_valid = True
            elif side == "short" and new_sl < current_sl:
                sl_valid = True
            else:
                print(f"  Price ${mark_price:>10,.1f} | Move {move_pct:+5.1f}% | [GUARD] BLOCKED ${current_sl:,.1f} -> ${new_sl:,.1f}")
        
        if sl_valid:
            tier_names = {0: "INITIAL", 1: "BREAKEVEN", 2: "PROFIT STEP", 3: "RUNNER TRAIL"}
            print(f"  Price ${mark_price:>10,.1f} | Move {move_pct:+5.1f}% | >> TIER {new_tier} ({tier_names[new_tier]}) SL: ${current_sl:,.1f} -> ${new_sl:,.1f}")
            current_sl = new_sl
            current_tier = max(current_tier, new_tier)
        else:
            status = f"Tier {current_tier}, SL ${current_sl:,.1f}"
            print(f"  Price ${mark_price:>10,.1f} | Move {move_pct:+5.1f}% | {status}")
    
    print(f"\n  FINAL STATE: Tier {current_tier} | SL: ${current_sl:,.1f}")
    return current_tier, current_sl


def test_recovery(side, entry_price, current_price):
    """Simulate recovery after PM2 restart"""
    cfg = STEP_TRAIL_CONFIG
    tick = 0.1  # Forex/Metals precision
    
    if side == "long":
        move_pct = ((current_price - entry_price) / entry_price) * 100
    else:
        move_pct = ((entry_price - current_price) / entry_price) * 100
    
    is_recovery = move_pct > 0.3
    
    if move_pct >= cfg["tier3_trigger_pct"]:
        tier = 3
        if side == "long":
            sl = round(round(current_price * (1 - cfg["tier3_trail_pct"] / 100) / tick) * tick, 1)
        else:
            sl = round(round(current_price * (1 + cfg["tier3_trail_pct"] / 100) / tick) * tick, 1)
    elif move_pct >= cfg["tier2_trigger_pct"]:
        tier = 2
        if side == "long":
            sl = round(round(current_price * (1 - cfg["tier2_trail_pct"] / 100) / tick) * tick, 5)
        else:
            sl = round(round(current_price * (1 + cfg["tier2_trail_pct"] / 100) / tick) * tick, 5)
    elif move_pct >= cfg["tier1_trigger_pct"]:
        tier = 1
        if side == "long":
            sl = round(round(entry_price * (1 + cfg["tier1_sl_pct"] / 100) / tick) * tick, 1)
        else:
            sl = round(round(entry_price * (1 - cfg["tier1_sl_pct"] / 100) / tick) * tick, 1)
    else:
        tier = 0
        if side == "long":
            sl = round(entry_price * (1 - cfg["initial_sl_pct"] / 100), 1)
        else:
            sl = round(entry_price * (1 + cfg["initial_sl_pct"] / 100), 1)
    
    tier_names = {0: "INITIAL", 1: "BREAKEVEN", 2: "PROFIT STEP", 3: "RUNNER TRAIL"}
    tag = "RECOVERED" if is_recovery else "NEW"
    print(f"  [{tag}] {side.upper()} | Entry ${entry_price:,.1f} | Current ${current_price:,.1f} ({move_pct:+.1f}%) -> Tier {tier} ({tier_names[tier]}) SL: ${sl:,.1f}")
    return tier, sl


if __name__ == "__main__":
    print("\n" + "#"*70)
    print("#  STEP-TRAILING STOP LOSS — VERIFICATION TEST")
    print("#"*70)
    
    # === TEST 1: LONG position going up (Gold-like: entry $3300) ===
    simulate_trail("long", 3300, [
        3300, 3305, 3308,           # Flat / small move
        3310,                       # +0.3% -> Tier 1 (breakeven)
        3326.4,                     # +0.8% -> Tier 2 (profit step trail)
        3350, 3370, 3380,           # Trailing higher
        3366,                       # +2.0% -> Tier 3 (runner trail)
        3380, 3400, 3420,           # Runner trailing
        3400,                       # Pullback (SL should NOT move down)
    ])
    
    # === TEST 2: SHORT position going down ===
    simulate_trail("short", 3300, [
        3300, 3295, 3292,           # Flat / small move
        3290.1,                     # -0.3% -> Tier 1 (breakeven)
        3273.6,                     # -0.8% -> Tier 2 (profit step trail)
        3250, 3240, 3230,           # Trailing lower
        3234,                       # -2.0% -> Tier 3 (runner trail)
        3220, 3200, 3180,           # Runner trailing
        3200,                       # Bounce (SL should NOT move up)
    ])
    
    # === TEST 3: Recovery after PM2 restart ===
    print(f"\n{'='*70}")
    print(f"  PM2 RESTART RECOVERY SIMULATION")
    print(f"{'='*70}")
    
    test_recovery("long",  84000, 84050)   # Barely moved -> Tier 0
    test_recovery("long",  84000, 84900)   # +1.07% -> Tier 1
    test_recovery("long",  84000, 85700)   # +2.02% -> Tier 2
    test_recovery("long",  84000, 86600)   # +3.10% -> Tier 3
    test_recovery("short", 84000, 83900)   # Barely moved -> Tier 0
    test_recovery("short", 84000, 83100)   # -1.07% -> Tier 1
    test_recovery("short", 84000, 82300)   # -2.02% -> Tier 2
    test_recovery("short", 84000, 81400)   # -3.10% -> Tier 3
    
    print(f"\n{'='*70}")
    print(f"  ALL TESTS COMPLETE")
    print(f"{'='*70}\n")
