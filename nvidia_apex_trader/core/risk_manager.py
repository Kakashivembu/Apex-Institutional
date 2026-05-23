"""
Risk Management Module - Daily Drawdown Circuit Breaker
Institutional-grade capital protection against localized catastrophic days.
"""

from datetime import datetime, timedelta
from typing import Dict, Optional
import asyncio
import json
import os

# =============================================================================
# CIRCUIT BREAKER CONFIGURATION
# =============================================================================
REALIZED_DRAWDOWN_LIMIT = 0.05   # 5% max REALIZED daily loss (closed trades)
FLOATING_EMERGENCY_LIMIT = 0.20  # 20% max FLOATING drawdown (open trade emergency / margin-call shield)

# Global state (module-level singleton)
_circuit_state = {
    "active": False,           # Circuit breaker currently tripped
    "daily_start_balance": 0.0,  # Balance at 00:00 or first trade of day
    "high_water_mark": 0.0,    # Peak balance during the day
    "current_drawdown_pct": 0.0,
    "last_reset_date": None,   # Track day for auto-reset at midnight
    "trip_time": None,         # When the breaker was tripped
    "trip_reason": "",         # Reason for trip
}

CIRCUIT_STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "circuit_state.json")

def load_circuit_state():
    global _circuit_state
    if os.path.exists(CIRCUIT_STATE_FILE):
        try:
            with open(CIRCUIT_STATE_FILE, "r") as f:
                data = json.load(f)
                
            if data.get("last_reset_date") == get_current_date():
                trip_time_str = data.get("trip_time")
                trip_time = None
                if trip_time_str:
                    try:
                        trip_time = datetime.fromisoformat(trip_time_str)
                    except:
                        pass
                
                _circuit_state["active"] = data.get("active", False)
                _circuit_state["daily_start_balance"] = data.get("daily_start_balance", 0.0)
                _circuit_state["high_water_mark"] = data.get("high_water_mark", 0.0)
                _circuit_state["current_drawdown_pct"] = data.get("current_drawdown_pct", 0.0)
                _circuit_state["last_reset_date"] = data.get("last_reset_date")
                _circuit_state["trip_time"] = trip_time
                _circuit_state["trip_reason"] = data.get("trip_reason", "")
                print(f"[RISK-MANAGER] Loaded persistent circuit state for {get_current_date()}")
        except Exception as e:
            print(f"[RISK-MANAGER] Error loading circuit state: {e}")

def save_circuit_state():
    try:
        data = _circuit_state.copy()
        if data["trip_time"]:
            data["trip_time"] = data["trip_time"].isoformat()
        with open(CIRCUIT_STATE_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[RISK-MANAGER] Error saving circuit state: {e}")


def get_current_date() -> str:
    """Get current date in YYYY-MM-DD format."""
    return datetime.now().strftime("%Y-%m-%d")

# Load state on module import
load_circuit_state()


def should_reset_for_new_day() -> bool:
    """Check if we need to reset for a new trading day."""
    current_date = get_current_date()
    return _circuit_state["last_reset_date"] != current_date


def reset_circuit_breaker(balance: float) -> None:
    """
    Reset the circuit breaker for a new trading day.
    Call this at 00:00 or on first balance update of the day.
    """
    current_date = get_current_date()
    
    _circuit_state["active"] = False
    _circuit_state["daily_start_balance"] = balance
    _circuit_state["high_water_mark"] = balance
    _circuit_state["current_drawdown_pct"] = 0.0
    _circuit_state["last_reset_date"] = current_date
    _circuit_state["trip_time"] = None
    _circuit_state["trip_reason"] = ""
    
    save_circuit_state()
    
    print(f"[RISK-MANAGER] Circuit breaker reset for {current_date}. Start balance: ${balance:,.2f}")


def check_circuit_breaker(current_balance: float, current_equity: float = 0.0) -> Dict:
    """
    Dual-threshold circuit breaker: REALIZED losses (balance) and FLOATING emergency (equity).

    - REALIZED LIMIT (5%): Trips when closed-trade losses erode 5% of the daily start balance.
      This is the primary protection against a losing streak of completed trades.
    - FLOATING EMERGENCY (20%): Trips when open-trade unrealized losses reach 20% of start balance.
      This is a margin-call shield — normal floating dips (2-5%) during stacking are tolerated.

    Args:
        current_balance: Account balance (reflects realized P&L only)
        current_equity:  Account equity (balance + unrealized P&L of open positions)

    Returns:
        Dict with active, drawdown metrics, reason, and can_trade flag.
    """
    global _circuit_state

    # Fallback: if equity not provided, use balance (backward-compatible)
    if current_equity <= 0:
        current_equity = current_balance

    # Auto-reset for new day
    if should_reset_for_new_day():
        reset_circuit_breaker(current_balance)

    # Initialize if first run
    if _circuit_state["daily_start_balance"] <= 0:
        reset_circuit_breaker(current_balance)

    # Update high water mark (track peak balance, not equity)
    if current_balance > _circuit_state["high_water_mark"]:
        _circuit_state["high_water_mark"] = current_balance

    # ── Dual Drawdown Calculation ──
    start_balance = _circuit_state["daily_start_balance"]
    if start_balance > 0:
        realized_dd_pct = ((start_balance - current_balance) / start_balance) * 100  # Positive = loss
        floating_dd_pct = ((start_balance - current_equity) / start_balance) * 100   # Positive = loss
    else:
        realized_dd_pct = 0.0
        floating_dd_pct = 0.0

    # Store the worse of the two for general telemetry
    _circuit_state["current_drawdown_pct"] = max(realized_dd_pct, floating_dd_pct) / 100.0  # Keep as fraction for compat

    # ── Dual-Threshold Trip Logic ──
    realized_limit = REALIZED_DRAWDOWN_LIMIT * 100   # 5.0%
    floating_limit = FLOATING_EMERGENCY_LIMIT * 100  # 20.0%

    if not _circuit_state["active"]:
        if realized_dd_pct >= realized_limit:
            _circuit_state["active"] = True
            _circuit_state["trip_time"] = datetime.now()
            _circuit_state["trip_reason"] = (
                f"REALIZED daily loss limit: {realized_dd_pct:.2f}% >= {realized_limit}% "
                f"(Balance ${current_balance:,.2f} vs Start ${start_balance:,.2f})"
            )
            print(f"\n{'='*70}")
            print(f"[CIRCUIT BREAKER] TRIPPED — REALIZED DRAWDOWN")
            print(f"[CIRCUIT BREAKER] Realized loss: {realized_dd_pct:.2f}% (limit: {realized_limit}%)")
            print(f"[CIRCUIT BREAKER] ALL NEW ENTRIES BLOCKED UNTIL MIDNIGHT")
            print(f"{'='*70}\n")

        elif floating_dd_pct >= floating_limit:
            _circuit_state["active"] = True
            _circuit_state["trip_time"] = datetime.now()
            _circuit_state["trip_reason"] = (
                f"FLOATING emergency limit: {floating_dd_pct:.2f}% >= {floating_limit}% "
                f"(Equity ${current_equity:,.2f} vs Start ${start_balance:,.2f})"
            )
            print(f"\n{'='*70}")
            print(f"[CIRCUIT BREAKER] TRIPPED — FLOATING EMERGENCY")
            print(f"[CIRCUIT BREAKER] Floating drawdown: {floating_dd_pct:.2f}% (emergency limit: {floating_limit}%)")
            print(f"[CIRCUIT BREAKER] MARGIN CALL PROTECTION — ALL ENTRIES BLOCKED")
            print(f"{'='*70}\n")
            
        if _circuit_state["active"]:
            save_circuit_state()
    else:
        # Save state periodically to update high water mark
        save_circuit_state()

    return {
        "active": _circuit_state["active"],
        "realized_dd_pct": round(realized_dd_pct, 2),
        "floating_dd_pct": round(floating_dd_pct, 2),
        "drawdown_pct": round(max(realized_dd_pct, floating_dd_pct), 2),  # Backward-compat: worst of both
        "realized_limit_pct": round(realized_limit, 2),
        "floating_limit_pct": round(floating_limit, 2),
        "limit_pct": round(realized_limit, 2),  # Backward-compat
        "start_balance": round(start_balance, 2),
        "high_water_mark": round(_circuit_state["high_water_mark"], 2),
        "reason": _circuit_state["trip_reason"],
        "can_trade": not _circuit_state["active"],
        "trip_time": _circuit_state["trip_time"].isoformat() if _circuit_state["trip_time"] else None,
        "time_until_reset": _get_time_until_midnight(),
    }


def _get_time_until_midnight() -> str:
    """Calculate time remaining until midnight for UI display."""
    now = datetime.now()
    midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    remaining = midnight - now
    hours, remainder = divmod(remaining.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours}h {minutes}m"


def get_circuit_status() -> Dict:
    """Get current circuit breaker status without checking balance."""
    return {
        "active": _circuit_state["active"],
        "drawdown_pct": round(_circuit_state["current_drawdown_pct"] * 100, 2),
        "realized_limit_pct": round(REALIZED_DRAWDOWN_LIMIT * 100, 2),
        "floating_limit_pct": round(FLOATING_EMERGENCY_LIMIT * 100, 2),
        "limit_pct": round(REALIZED_DRAWDOWN_LIMIT * 100, 2),
        "start_balance": round(_circuit_state["daily_start_balance"], 2),
        "high_water_mark": round(_circuit_state["high_water_mark"], 2),
        "reason": _circuit_state["trip_reason"],
        "can_trade": not _circuit_state["active"],
        "trip_time": _circuit_state["trip_time"].isoformat() if _circuit_state["trip_time"] else None,
        "time_until_reset": _get_time_until_midnight(),
    }


def force_reset() -> None:
    """Manual reset of circuit breaker (for admin use only)."""
    _circuit_state["active"] = False
    _circuit_state["trip_reason"] = "Manual reset by admin"
    save_circuit_state()
    print(f"[RISK-MANAGER] Circuit breaker manually reset")


# =============================================================================
# ASYNC MIDNIGHT RESET LOOP
# =============================================================================

async def midnight_reset_loop():
    """
    Background loop that automatically resets the circuit breaker at midnight.
    This ensures the breaker is always ready for the new trading day.
    """
    print("[RISK-MANAGER] Midnight reset loop started")
    
    while True:
        try:
            now = datetime.now()
            
            # Calculate seconds until next midnight
            midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
            seconds_until_midnight = (midnight - now).total_seconds()
            
            # Sleep until midnight + small buffer
            sleep_seconds = min(seconds_until_midnight + 5, 3600)  # Max 1 hour checks
            
            print(f"[RISK-MANAGER] Next reset in {sleep_seconds/3600:.1f} hours ({midnight.strftime('%Y-%m-%d %H:%M')})")
            
            await asyncio.sleep(sleep_seconds)
            
            # Perform reset
            if should_reset_for_new_day():
                # Reset will happen on next balance check with new balance
                _circuit_state["last_reset_date"] = None  # Force reset
                print(f"[RISK-MANAGER] Midnight reached. Circuit breaker armed for new day.")
                
        except Exception as e:
            print(f"[RISK-MANAGER] Error in midnight loop: {e}")
            await asyncio.sleep(300)  # 5 min retry on error


# Standalone test
if __name__ == "__main__":
    print("=" * 60)
    print("RISK MANAGER - DUAL-THRESHOLD CIRCUIT BREAKER TEST")
    print("=" * 60)
    
    # Simulate a day
    print("\n[Test 1] Starting balance: $100,000")
    reset_circuit_breaker(100000)
    
    print("\n[Test 2] Balance $98k, Equity $97k — small floating dip (should NOT trip)")
    result = check_circuit_breaker(98000, 97000)
    print(f"  Active: {result['active']}, Realized DD: {result['realized_dd_pct']}%, Floating DD: {result['floating_dd_pct']}%")
    
    print("\n[Test 3] Balance $100k, Equity $82k — 18% floating dip from stacking (should NOT trip)")
    result = check_circuit_breaker(100000, 82000)
    print(f"  Active: {result['active']}, Realized DD: {result['realized_dd_pct']}%, Floating DD: {result['floating_dd_pct']}%")
    
    print("\n[Test 4] Balance $94k — 6% REALIZED loss (should TRIP)")
    force_reset()
    reset_circuit_breaker(100000)
    result = check_circuit_breaker(94000, 94000)
    print(f"  Active: {result['active']}, Realized DD: {result['realized_dd_pct']}%")
    print(f"  Reason: {result['reason']}")
    
    print("\n[Test 5] Balance $100k, Equity $79k — 21% FLOATING emergency (should TRIP)")
    force_reset()
    reset_circuit_breaker(100000)
    result = check_circuit_breaker(100000, 79000)
    print(f"  Active: {result['active']}, Floating DD: {result['floating_dd_pct']}%")
    print(f"  Reason: {result['reason']}")
    
    print("\n[Test 6] After trip - recovery attempt (should STAY tripped)")
    result = check_circuit_breaker(100000, 100000)
    print(f"  Active: {result['active']}, Can trade: {result['can_trade']}")
    
    print("\n" + "=" * 60)
