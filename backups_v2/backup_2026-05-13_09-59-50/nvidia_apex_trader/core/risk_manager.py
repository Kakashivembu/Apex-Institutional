"""
Risk Management Module - Daily Drawdown Circuit Breaker
Institutional-grade capital protection against localized catastrophic days.
"""

from datetime import datetime, timedelta
from typing import Dict, Optional
import asyncio

# =============================================================================
# CIRCUIT BREAKER CONFIGURATION
# =============================================================================
DAILY_DRAWDOWN_LIMIT = 0.03  # 3% max daily loss (institutional standard)
# NOTE: Adaptive limit is applied in check_circuit_breaker based on account size

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


def get_current_date() -> str:
    """Get current date in YYYY-MM-DD format."""
    return datetime.now().strftime("%Y-%m-%d")


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
    
    print(f"[RISK-MANAGER] Circuit breaker reset for {current_date}. Start balance: ${balance:,.2f}")


def check_circuit_breaker(current_balance: float) -> Dict:
    """
    Check if the circuit breaker should trip based on current balance.
    Adaptive: small accounts (<$500) use 1.5% daily limit for zero-drawdown protection.

    Args:
        current_balance: Current account equity/balance

    Returns:
        Dict with:
        - active: True if circuit breaker is tripped
        - drawdown_pct: Current drawdown percentage
        - limit: Maximum allowed drawdown
        - reason: Explanation if tripped
        - can_trade: False if new entries should be blocked
    """
    global _circuit_state

    # Adaptive drawdown limit: micro accounts get tighter protection
    if current_balance <= 100:
        adaptive_limit = 0.015  # 1.5% daily max loss for $100 accounts
    elif current_balance <= 500:
        adaptive_limit = 0.02   # 2% daily max loss for $500 accounts
    else:
        adaptive_limit = DAILY_DRAWDOWN_LIMIT  # 3% for larger accounts

    # Auto-reset for new day
    if should_reset_for_new_day():
        reset_circuit_breaker(current_balance)

    # Initialize if first run
    if _circuit_state["daily_start_balance"] <= 0:
        reset_circuit_breaker(current_balance)

    # Update high water mark
    if current_balance > _circuit_state["high_water_mark"]:
        _circuit_state["high_water_mark"] = current_balance

    # Calculate drawdown from daily start (not peak-to-trough)
    start_balance = _circuit_state["daily_start_balance"]
    if start_balance > 0:
        drawdown_pct = (current_balance - start_balance) / start_balance
    else:
        drawdown_pct = 0.0

    _circuit_state["current_drawdown_pct"] = drawdown_pct

    # Check if we should trip the breaker
    if not _circuit_state["active"] and drawdown_pct <= -adaptive_limit:
        _circuit_state["active"] = True
        _circuit_state["trip_time"] = datetime.now()
        _circuit_state["trip_reason"] = f"Daily drawdown limit hit: {drawdown_pct*100:.2f}% (adaptive limit: {adaptive_limit*100}%)"

        print(f"\n{'='*70}")
        print(f"[CIRCUIT BREAKER] TRIPPED!")
        print(f"[CIRCUIT BREAKER] Daily loss: {drawdown_pct*100:.2f}% exceeds {adaptive_limit*100}% limit")
        print(f"[CIRCUIT BREAKER] ALL NEW ENTRIES BLOCKED UNTIL MIDNIGHT")
        print(f"{'='*70}\n")

    return {
        "active": _circuit_state["active"],
        "drawdown_pct": round(drawdown_pct * 100, 2),
        "limit_pct": round(adaptive_limit * 100, 2),
        "start_balance": round(_circuit_state["daily_start_balance"], 2),
        "high_water_mark": round(_circuit_state["high_water_mark"], 2),
        "reason": _circuit_state["trip_reason"],
        "can_trade": not _circuit_state["active"],  # False when active
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
        "limit_pct": round(DAILY_DRAWDOWN_LIMIT * 100, 2),
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
    print("RISK MANAGER - CIRCUIT BREAKER TEST")
    print("=" * 60)
    
    # Simulate a day
    print("\n[Test 1] Starting balance: $100,000")
    reset_circuit_breaker(100000)
    
    print("\n[Test 2] Small loss -2% (should NOT trip)")
    result = check_circuit_breaker(98000)
    print(f"  Active: {result['active']}, Drawdown: {result['drawdown_pct']}%")
    
    print("\n[Test 3] Recovery +5% (should NOT trip)")
    result = check_circuit_breaker(105000)
    print(f"  Active: {result['active']}, Drawdown: {result['drawdown_pct']}%")
    
    print("\n[Test 4] Catastrophic loss -4% (should TRIP)")
    result = check_circuit_breaker(96000)
    print(f"  Active: {result['active']}, Drawdown: {result['drawdown_pct']}%")
    print(f"  Reason: {result['reason']}")
    print(f"  Can trade: {result['can_trade']}")
    
    print("\n[Test 5] After trip - recovery attempt (should STAY tripped)")
    result = check_circuit_breaker(100000)
    print(f"  Active: {result['active']}, Drawdown: {result['drawdown_pct']}%")
    print(f"  Can trade: {result['can_trade']}")
    
    print("\n" + "=" * 60)
