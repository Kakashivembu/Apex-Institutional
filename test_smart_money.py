#!/usr/bin/env python
"""
APEX INSTITUTIONAL - SMART MONEY LIQUIDITY X-RAY
=================================================
Standalone diagnostic script for Fair Value Gap (FVG) and Liquidity Zone detection.
Read-only - NO account interactions, NO API key usage for trading.
Uses public Delta Mainnet candle data only.

Run: python test_smart_money.py
"""

import sys
import os
import json

# Add nvidia_apex_trader to path
_script_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(_script_dir) != "nvidia_apex_trader":
    _trader_dir = os.path.join(_script_dir, "nvidia_apex_trader")
else:
    _trader_dir = _script_dir
sys.path.insert(0, _trader_dir)

from core.data import fetch_candles_sync


def detect_fvgs(candles):
    """
    Detect Fair Value Gaps (FVGs) from an array of candles.

    Bullish FVG: Low of Candle 3 > High of Candle 1
        - The gap is between C1 High and C3 Low
        - Implies institutional buying pressure filling the gap

    Bearish FVG: High of Candle 3 < Low of Candle 1
        - The gap is between C1 Low and C3 High
        - Implies institutional selling pressure filling the gap

    Args:
        candles: List of dicts with 'open', 'high', 'low', 'close' keys

    Returns:
        List of dicts representing unmitigated FVGs:
        {
            'type': 'BULLISH' or 'BEARISH',
            'top': float,   # Upper boundary of the gap
            'bottom': float, # Lower boundary of the gap
            'index': int,   # Candle index where FVG was detected (C3 position)
            'freshness': int, # How many candles ago (higher = older)
            'mitigated_pct': float # 0.0 = unmitigated, 100.0 = fully mitigated
        }
    """
    if len(candles) < 3:
        return []

    fvgs = []
    n = len(candles)

    for i in range(2, n):
        c1 = candles[i - 2]
        c2 = candles[i - 1]
        c3 = candles[i]

        c1_high = float(c1.get("high", 0))
        c1_low = float(c1.get("low", 0))
        c3_high = float(c3.get("high", 0))
        c3_low = float(c3.get("low", 0))

        # ── Bullish FVG ─────────────────────────────────────────────
        # C3 Low is ABOVE C1 High — price gapped up, creating a deficit zone
        if c3_low > c1_high:
            gap_top = c3_low      # Top of the unfilled zone
            gap_bottom = c1_high  # Bottom of the unfilled zone
            gap_size = gap_top - gap_bottom

            # Calculate mitigation: have subsequent candles traded through this gap?
            mitigated_range = 0.0
            for j in range(i + 1, n):
                candle_high = float(candles[j].get("high", 0))
                candle_low = float(candles[j].get("low", 0))

                # Check how much of the gap has been filled
                if gap_size > 0:
                    # If candle low reaches into the gap, calculate fill %
                    if candle_low <= gap_top:
                        filled_from_top = max(0, gap_top - max(candle_low, gap_bottom))
                        mitigated_range = max(mitigated_range, (filled_from_top / gap_size) * 100)

            fvgs.append({
                "type": "BULLISH",
                "top": round(gap_top, 2),
                "bottom": round(gap_bottom, 2),
                "index": i,
                "candle_time": candles[i].get("time", 0),
                "freshness": n - i - 1,
                "mitigated_pct": round(mitigated_range, 1),
                "gap_size": round(gap_size, 2)
            })

        # ── Bearish FVG ─────────────────────────────────────────────
        # C3 High is BELOW C1 Low — price gapped down, creating a surplus zone
        elif c3_high < c1_low:
            gap_top = c1_low      # Top of the unfilled zone
            gap_bottom = c3_high  # Bottom of the unfilled zone
            gap_size = gap_top - gap_bottom

            # Calculate mitigation
            mitigated_range = 0.0
            for j in range(i + 1, n):
                candle_high = float(candles[j].get("high", 0))
                candle_low = float(candles[j].get("low", 0))

                if gap_size > 0:
                    # If candle high reaches into the gap from below
                    if candle_high >= gap_bottom:
                        filled_from_bottom = min(candle_high, gap_top) - gap_bottom
                        mitigated_range = max(mitigated_range, (filled_from_bottom / gap_size) * 100)

            fvgs.append({
                "type": "BEARISH",
                "top": round(gap_top, 2),
                "bottom": round(gap_bottom, 2),
                "index": i,
                "candle_time": candles[i].get("time", 0),
                "freshness": n - i - 1,
                "mitigated_pct": round(mitigated_range, 1),
                "gap_size": round(gap_size, 2)
            })

    return fvgs


def score_liquidity(fvgs, current_price):
    """
    Score FVGs based on Liquidity Quality metrics.

    Scoring Logic:
    - Base score: 100 points per FVG
    - Freshness penalty: -1 point per candle age (older = less relevant)
    - Proximity penalty: -2 points per 1% distance from current price
    - Mitigation bonus: partially mitigated gaps (50-80%) may act as liquidity magnets

    Args:
        fvgs: List of FVG dicts from detect_fvgs()
        current_price: Current BTC price (float)

    Returns:
        FVGs sorted by score descending (highest liquidity quality first)
    """
    scored = []

    for fvg in fvgs:
        base_score = 100.0
        gap_top = fvg["top"]
        gap_bottom = fvg["bottom"]
        gap_mid = (gap_top + gap_bottom) / 2

        # Freshness penalty: -1 per candle of age
        freshness_penalty = fvg["freshness"] * 1.0

        # Proximity penalty: distance from current price
        distance = abs(current_price - gap_mid)
        distance_pct = (distance / current_price) * 100
        proximity_penalty = distance_pct * 2.0

        # Mitigation factor: partially filled gaps are more reactive
        # 0% mitigated = pristine gap, harder to fill (higher score)
        # 50-80% mitigated = "magnet zone" where price often respects
        # 100% mitigated = fully filled, irrelevant
        mitigated = fvg["mitigated_pct"]
        if mitigated == 0:
            mitigation_factor = 0  # Pristine - bonus
        elif 30 < mitigated < 80:
            mitigation_factor = 5  # Magnet zone - slight bonus
        elif mitigated >= 80:
            mitigation_factor = -20  # Almost filled - penalize
        else:
            mitigation_factor = 0

        # Calculate final score
        final_score = base_score - freshness_penalty - proximity_penalty + mitigation_factor
        final_score = max(final_score, 0)  # Floor at 0

        scored.append({
            **fvg,
            "mid_price": round(gap_mid, 2),
            "distance_from_now": round(distance_pct, 2),
            "liquidity_score": round(final_score, 1)
        })

    # Sort by score descending
    scored.sort(key=lambda x: x["liquidity_score"], reverse=True)
    return scored


def format_report(fvgs, fvgs_1h, current_price, tf="15m"):
    """Format a console-friendly Smart Money Liquidity X-Ray report."""
    print()
    print("=" * 70)
    print(f"=== SMART MONEY LIQUIDITY X-RAY [{tf.upper()}] ===")
    print(f"=== Current Price: ${current_price:,.2f} ===")
    print("=" * 70)
    print()

    # ── SUMMARY BAR ──────────────────────────────────────────────────
    bullish = [f for f in fvgs if f["type"] == "BULLISH"]
    bearish = [f for f in fvgs if f["type"] == "BEARISH"]
    pristine = [f for f in fvgs if f["mitigated_pct"] == 0]
    partial = [f for f in fvgs if 0 < f["mitigated_pct"] < 80]
    near = [f for f in fvgs if f["distance_from_now"] < 2.0]  # Within 2%

    print(f"  SUMMARY: {len(fvgs)} FVGs detected ({len(bullish)} Bullish | {len(bearish)} Bearish)")
    print(f"  +-> Pristine (unmitigated): {len(pristine)}")
    print(f"  +-> Magnet zones (30-80%):  {len(partial)}")
    print(f"  +-> Near price (<2% away):  {len(near)}")
    print()

    # ── NEAR PRICE TARGETS ───────────────────────────────────────────
    if near:
        print("-" * 70)
        print(f"  NEAR-PRICE LIQUIDITY ZONES (<2% from ${current_price:,.2f})")
        print("-" * 70)
        for fvg in near[:5]:
            tf_label = "[BULL] BULLISH" if fvg["type"] == "BULLISH" else "[BEAR] BEARISH"
            gap_pct = fvg["gap_size"] / current_price * 100
            print(f"  {tf_label} | Score: {fvg['liquidity_score']:5.1f} | "
                  f"Zone: ${fvg['bottom']:,.2f} -> ${fvg['top']:,.2f} | "
                  f"Gap: {gap_pct:.2f}% | Mitigated: {fvg['mitigated_pct']:.0f}%")
        print()

    # ── ALL FVGs SORTED BY SCORE ─────────────────────────────────────
    if fvgs:
        print("-" * 70)
        print(f"  ALL LIQUIDITY ZONES (sorted by Liquidity Score)")
        print("-" * 70)
        print(f"  {'TYPE':<10} {'SCORE':>6} | {'RANGE':<28} | {'DIST':>6} | {'GAP':>6} | {'FRESH':>5} | {'MIT%':>5}")
        print(f"  {'-'*10} {'-'*6} | {'-'*28} | {'-'*6} | {'-'*6} | {'-'*5} | {'-'*5}")

        for fvg in fvgs[:15]:  # Show top 15
            tf_label = "BULLISH" if fvg["type"] == "BULLISH" else "BEARISH"
            range_str = f"${fvg['bottom']:,.0f} - ${fvg['top']:,.0f}"
            print(f"  {tf_label:<10} {fvg['liquidity_score']:>6.1f} | "
                  f"{range_str:<28} | {fvg['distance_from_now']:>5.2f}% | "
                  f"{fvg['gap_size']:>5.1f} | {fvg['freshness']:>5} | {fvg['mitigated_pct']:>5.1f}")

    else:
        print("  No FVGs detected in this timeframe.")

    print()
    print("-" * 70)
    print("  LEGEND:")
    print("  SCORE  = Liquidity quality (100 = fresh & near price)")
    print("  DIST   = Distance from current price (%)")
    print("  GAP    = Dollar size of the FVG")
    print("  FRESH  = Candles since FVG formed (lower = fresher)")
    print("  MIT%   = % of gap already filled (0% = pristine, 100% = gone)")
    print("-" * 70)
    print()


if __name__ == "__main__":
    import time

    print("=" * 70)
    print("APEX INSTITUTIONAL - SMART MONEY DETECTION ENGINE")
    print("=" * 70)
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Fetch candles from Delta Mainnet (15m and 1h)
    print("\n[1/4] Fetching 15m candles from Delta Mainnet...")
    candles_15m = fetch_candles_sync("BTCUSD", "15m", limit=50, network="mainnet")
    print(f"      -> Received {len(candles_15m)} candles")

    print("[2/4] Fetching 1h candles from Delta Mainnet...")
    candles_1h = fetch_candles_sync("BTCUSD", "1h", limit=50, network="mainnet")
    print(f"      -> Received {len(candles_1h)} candles")

    if not candles_15m and not candles_1h:
        print("\n[FATAL] No candle data received from Delta Mainnet. Aborting.")
        sys.exit(1)

    # Extract current price from latest candle
    current_price = 0
    if candles_15m:
        current_price = float(candles_15m[-1].get("close", 0))
    elif candles_1h:
        current_price = float(candles_1h[-1].get("close", 0))

    print(f"[3/4] Current BTC Price: ${current_price:,.2f}")

    # Detect FVGs
    print("[4/4] Running FVG detection and liquidity scoring...")

    fvgs_15m_raw = detect_fvgs(candles_15m) if len(candles_15m) >= 3 else []
    fvgs_1h_raw = detect_fvgs(candles_1h) if len(candles_1h) >= 3 else []

    # Score FVGs
    fvgs_15m = score_liquidity(fvgs_15m_raw, current_price) if fvgs_15m_raw else []
    fvgs_1h = score_liquidity(fvgs_1h_raw, current_price) if fvgs_1h_raw else []

    # ── 15M REPORT ────────────────────────────────────────────────────
    format_report(fvgs_15m, fvgs_1h, current_price, tf="15m")

    # ── 1H REPORT ─────────────────────────────────────────────────────
    format_report(fvgs_1h, fvgs_15m, current_price, tf="1h")

    # ── CROSS-TIMEFRAME LIQUIDITY STACKS ─────────────────────────────
    print("=" * 70)
    print("=== CROSS-TIMEFRAME LIQUIDITY STACKS ===")
    print("=" * 70)

    # Find FVGs that overlap between timeframes (confluence zones)
    if fvgs_15m and fvgs_1h:
        print()
        print("  Looking for overlapping zones between 15m and 1h...")
        print()

        stacks = []
        for f15 in fvgs_15m[:10]:
            for f1h in fvgs_1h[:10]:
                # Check if 15m FVG overlaps with 1h FVG
                overlap_top = min(f15["top"], f1h["top"])
                overlap_bottom = max(f15["bottom"], f1h["bottom"])
                if overlap_bottom < overlap_top:  # They overlap
                    stacks.append({
                        "top": overlap_top,
                        "bottom": overlap_bottom,
                        "mid": (overlap_top + overlap_bottom) / 2,
                        "avg_score": (f15["liquidity_score"] + f1h["liquidity_score"]) / 2,
                        "15m_type": f15["type"],
                        "1h_type": f1h["type"]
                    })

        if stacks:
            stacks.sort(key=lambda x: x["avg_score"], reverse=True)
            print(f"  {'TYPE':<14} {'AVG SCORE':>10} | {'STACKED ZONE':<26} | {'SIZE':>8}")
            print(f"  {'-'*14} {'-'*10} | {'-'*26} | {'-'*8}")
            for s in stacks[:5]:
                types = f"{s['15m_type']}/{s['1h_type']}"
                zone = f"${s['bottom']:,.0f} - ${s['top']:,.0f}"
                size = f"${s['top'] - s['bottom']:.0f}"
                print(f"  {types:<14} {s['avg_score']:>10.1f} | {zone:<26} | {size:>8}")
        else:
            print("  No stacked (confluent) zones found between timeframes.")

    print()
    print("=== END OF SMART MONEY LIQUIDITY REPORT ===")
    print("=" * 70)