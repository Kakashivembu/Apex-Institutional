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
REALIZED_DRAWDOWN_LIMIT = 0.049   # 4.9% max REALIZED daily loss (Competition 5% limit)
FLOATING_EMERGENCY_LIMIT = 0.049  # 4.9% max FLOATING drawdown

# Global state (module-level singleton)
# Key: account_id (str) -> dict of circuit state
_circuit_state_accounts = {}

CIRCUIT_STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "circuit_state.json")

def _get_default_state():
    return {
        "active": False,
        "daily_start_balance": 0.0,
        "high_water_mark": 0.0,
        "current_drawdown_pct": 0.0,
        "last_reset_date": None,
        "trip_time": None,
        "trip_reason": "",
    }

def get_state_for_account(account_id: str) -> dict:
    if account_id not in _circuit_state_accounts:
        _circuit_state_accounts[account_id] = _get_default_state()
    return _circuit_state_accounts[account_id]

def load_circuit_state():
    global _circuit_state_accounts
    if os.path.exists(CIRCUIT_STATE_FILE):
        try:
            with open(CIRCUIT_STATE_FILE, "r") as f:
                data = json.load(f)
            
            # Migration check: if old format (flat dict), wipe it and start fresh.
            if "accounts" in data:
                accounts_data = data["accounts"]
                for acc_id, acc_state in accounts_data.items():
                    if acc_state.get("last_reset_date") == get_current_date():
                        trip_time_str = acc_state.get("trip_time")
                        trip_time = None
                        if trip_time_str:
                            try:
                                trip_time = datetime.fromisoformat(trip_time_str)
                            except:
                                pass
                        
                        acc_state["trip_time"] = trip_time
                        _circuit_state_accounts[acc_id] = acc_state
            print(f"[RISK-MANAGER] Loaded persistent circuit state for {get_current_date()}")
        except Exception as e:
            print(f"[RISK-MANAGER] Error loading circuit state: {e}")

def save_circuit_state():
    try:
        data_to_save = {"accounts": {}}
        for acc_id, state in _circuit_state_accounts.items():
            state_copy = state.copy()
            if state_copy["trip_time"]:
                state_copy["trip_time"] = state_copy["trip_time"].isoformat()
            data_to_save["accounts"][acc_id] = state_copy
            
        with open(CIRCUIT_STATE_FILE, "w") as f:
            json.dump(data_to_save, f)
    except Exception as e:
        print(f"[RISK-MANAGER] Error saving circuit state: {e}")


def get_current_date() -> str:
    """Get current date in YYYY-MM-DD format."""
    return datetime.now().strftime("%Y-%m-%d")

# Load state on module import
load_circuit_state()


def should_reset_for_new_day(account_id: str) -> bool:
    """Check if we need to reset for a new trading day."""
    current_date = get_current_date()
    state = get_state_for_account(account_id)
    return state["last_reset_date"] != current_date


def reset_circuit_breaker(balance: float, account_id: str = "default") -> None:
    """
    Reset the circuit breaker for a new trading day.
    Call this at 00:00 or on first balance update of the day.
    """
    current_date = get_current_date()
    state = get_state_for_account(account_id)
    
    state["active"] = False
    state["daily_start_balance"] = balance
    state["high_water_mark"] = balance
    state["current_drawdown_pct"] = 0.0
    state["last_reset_date"] = current_date
    state["trip_time"] = None
    state["trip_reason"] = ""
    
    save_circuit_state()
    
    print(f"[RISK-MANAGER] Circuit breaker reset for {current_date} [{account_id}]. Start balance: ${balance:,.2f}")


def check_circuit_breaker(current_balance: float, current_equity: float = 0.0, account_id: str = "default", trading_mode: str = "challenge") -> Dict:
    """
    Dual-threshold circuit breaker: REALIZED losses (balance) and FLOATING emergency (equity).
    """
    # Fallback: if equity not provided, use balance
    if current_equity <= 0:
        current_equity = current_balance

    state = get_state_for_account(account_id)

    # Auto-reset for new day
    if should_reset_for_new_day(account_id):
        reset_circuit_breaker(current_balance, account_id)

    # Initialize if first run
    if state["daily_start_balance"] <= 0:
        reset_circuit_breaker(current_balance, account_id)

    # Update high water mark
    if current_balance > state["high_water_mark"]:
        state["high_water_mark"] = current_balance

    # ── Dual Drawdown Calculation ──
    start_balance = state["daily_start_balance"]
    if start_balance > 0:
        realized_dd_pct = ((start_balance - current_balance) / start_balance) * 100
        floating_dd_pct = ((start_balance - current_equity) / start_balance) * 100
    else:
        realized_dd_pct = 0.0
        floating_dd_pct = 0.0

    state["current_drawdown_pct"] = max(realized_dd_pct, floating_dd_pct) / 100.0

    # ── Dual-Threshold Trip Logic ──
    if trading_mode == "competition":
        realized_limit = 4.9
        floating_limit = 4.9
    elif trading_mode == "realmoney":
        realized_limit = 1.5
        floating_limit = 1.5
    else: # challenge
        realized_limit = 2.5
        floating_limit = 2.0

    if not state["active"]:
        if realized_dd_pct >= realized_limit:
            state["active"] = True
            state["trip_time"] = datetime.now()
            state["trip_reason"] = (
                f"REALIZED daily loss limit: {realized_dd_pct:.2f}% >= {realized_limit}% "
                f"(Balance ${current_balance:,.2f} vs Start ${start_balance:,.2f})"
            )
            print(f"\n{'='*70}")
            print(f"[CIRCUIT BREAKER] [{account_id}] TRIPPED — REALIZED DRAWDOWN")
            print(f"[CIRCUIT BREAKER] Realized loss: {realized_dd_pct:.2f}% (limit: {realized_limit}%)")
            print(f"[CIRCUIT BREAKER] ALL NEW ENTRIES BLOCKED UNTIL MIDNIGHT")
            print(f"{'='*70}\n")

        elif floating_dd_pct >= floating_limit:
            state["active"] = True
            state["trip_time"] = datetime.now()
            state["trip_reason"] = (
                f"FLOATING emergency limit: {floating_dd_pct:.2f}% >= {floating_limit}% "
                f"(Equity ${current_equity:,.2f} vs Start ${start_balance:,.2f})"
            )
            print(f"\n{'='*70}")
            print(f"[CIRCUIT BREAKER] [{account_id}] TRIPPED — FLOATING EMERGENCY")
            print(f"[CIRCUIT BREAKER] Floating drawdown: {floating_dd_pct:.2f}% (emergency limit: {floating_limit}%)")
            print(f"[CIRCUIT BREAKER] MARGIN CALL PROTECTION — ALL ENTRIES BLOCKED")
            print(f"{'='*70}\n")
    else:
        # If it's already active, check if the limits have been increased (e.g. switched to Competition Mode)
        # and the drawdowns are now safely below the new limits.
        if realized_dd_pct < realized_limit and floating_dd_pct < floating_limit:
            state["active"] = False
            state["trip_time"] = None
            state["trip_reason"] = ""
            print(f"\n{'='*70}")
            print(f"[CIRCUIT BREAKER] [{account_id}] RECOVERED — Limits updated or drawdown recovered.")
            print(f"{'='*70}\n")
            
        if state["active"]:
            save_circuit_state()
    else:
        # Save state periodically
        save_circuit_state()

    return {
        "active": state["active"],
        "realized_dd_pct": round(realized_dd_pct, 2),
        "floating_dd_pct": round(floating_dd_pct, 2),
        "drawdown_pct": round(max(realized_dd_pct, floating_dd_pct), 2),
        "realized_limit_pct": round(realized_limit, 2),
        "floating_limit_pct": round(floating_limit, 2),
        "limit_pct": round(realized_limit, 2),
        "start_balance": round(start_balance, 2),
        "high_water_mark": round(state["high_water_mark"], 2),
        "reason": state["trip_reason"],
        "can_trade": not state["active"],
        "trip_time": state["trip_time"].isoformat() if state["trip_time"] else None,
        "time_until_reset": _get_time_until_midnight(),
    }


def _get_time_until_midnight() -> str:
    now = datetime.now()
    midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    remaining = midnight - now
    hours, remainder = divmod(remaining.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours}h {minutes}m"


def get_circuit_status(account_id: str = "default") -> Dict:
    state = get_state_for_account(account_id)
    return {
        "active": state["active"],
        "drawdown_pct": round(state["current_drawdown_pct"] * 100, 2),
        "realized_limit_pct": round(REALIZED_DRAWDOWN_LIMIT * 100, 2),
        "floating_limit_pct": round(FLOATING_EMERGENCY_LIMIT * 100, 2),
        "limit_pct": round(REALIZED_DRAWDOWN_LIMIT * 100, 2),
        "start_balance": round(state["daily_start_balance"], 2),
        "high_water_mark": round(state["high_water_mark"], 2),
        "reason": state["trip_reason"],
        "can_trade": not state["active"],
        "trip_time": state["trip_time"].isoformat() if state["trip_time"] else None,
        "time_until_reset": _get_time_until_midnight(),
    }


def force_reset(account_id: str = None) -> None:
    if account_id:
        state = get_state_for_account(account_id)
        state["active"] = False
        state["trip_reason"] = "Manual reset by admin"
        print(f"[RISK-MANAGER] [{account_id}] Circuit breaker manually reset")
    else:
        for acc_id, state in _circuit_state_accounts.items():
            if state["active"]:
                state["active"] = False
                state["trip_reason"] = "Manual reset by admin"
                print(f"[RISK-MANAGER] [{acc_id}] Circuit breaker manually reset")
    save_circuit_state()


async def midnight_reset_loop():
    print("[RISK-MANAGER] Midnight reset loop started")
    while True:
        try:
            now = datetime.now()
            midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
            seconds_until_midnight = (midnight - now).total_seconds()
            sleep_seconds = min(seconds_until_midnight + 5, 3600)
            print(f"[RISK-MANAGER] Next reset in {sleep_seconds/3600:.1f} hours ({midnight.strftime('%Y-%m-%d %H:%M')})")
            await asyncio.sleep(sleep_seconds)
            
            for acc_id in _circuit_state_accounts.keys():
                if should_reset_for_new_day(acc_id):
                    _circuit_state_accounts[acc_id]["last_reset_date"] = None
            print(f"[RISK-MANAGER] Midnight reached. Circuit breaker armed for new day.")
        except Exception as e:
            print(f"[RISK-MANAGER] Error in midnight loop: {e}")
            await asyncio.sleep(300)

if __name__ == "__main__":
    pass
