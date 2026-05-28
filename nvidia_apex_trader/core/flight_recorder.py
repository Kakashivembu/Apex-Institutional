# ============================================================
# FLIGHT RECORDER — Lightweight JSON Persistence Layer
# ============================================================
# Saves step_trail_state and ai_predictive_traps to disk so
# PM2 restarts don't wipe the bot's memory of active SL tiers,
# MFE/peak prices, and AI-predicted traps.
#
# Thread-safe: Uses atomic write (tmp + rename) to prevent
# corruption if the process crashes mid-write.
# ============================================================

import json
import os
import time
import threading

# ============================================================
# STATE FILE LOCATION — OUTSIDE PROJECT DIRECTORY
# ============================================================
# The state file is stored in ~/.apex_trader/ (user home) so it
# survives project folder copy-paste between PC and laptop.
# If you copy the project to a new machine, the flight recorder
# on the target machine keeps its own state untouched.
# ============================================================
_APEX_DATA_DIR = os.path.join(os.path.expanduser("~"), ".apex_trader")
os.makedirs(_APEX_DATA_DIR, exist_ok=True)
STATE_FILE = os.path.join(_APEX_DATA_DIR, "apex_flight_state.json")

# Legacy path (inside project) — auto-migrate on first load
_LEGACY_STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "apex_flight_state.json")

# Write lock prevents concurrent writes from step_trailing_loop and predictive_trap_loop
_write_lock = threading.Lock()

# Debounce: skip saves if the last save was < N seconds ago (peak_price updates are frequent)
_last_save_time = 0.0
SAVE_DEBOUNCE_SECONDS = 2.0


def save_flight_state(step_trail_state: dict, ai_predictive_traps: dict, force: bool = False, global_cooldowns: dict = None):
    """Persist step_trail_state and ai_predictive_traps to disk.
    
    Uses atomic write (write to .tmp, then os.replace) to avoid
    corrupted reads if the process dies mid-write.
    
    Args:
        step_trail_state: Per-account/symbol trailing stop state dict.
        ai_predictive_traps: Per-symbol AI trap predictions dict.
        force: If True, bypass debounce timer (used for tier changes & position closes).
        global_cooldowns: Cooldown dictionary from core.brain
    """
    global _last_save_time
    
    now = time.time()
    if not force and (now - _last_save_time) < SAVE_DEBOUNCE_SECONDS:
        return  # Skip — too soon since last save
    
    payload = {
        "_meta": {
            "saved_at": now,
            "saved_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
            "version": 1
        },
        "step_trail_state": step_trail_state,
        "ai_predictive_traps": ai_predictive_traps,
        "global_cooldowns": global_cooldowns if global_cooldowns is not None else {}
    }
    
    tmp_path = STATE_FILE + ".tmp"
    
    with _write_lock:
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)
            # Atomic replace — either fully succeeds or the old file remains
            os.replace(tmp_path, STATE_FILE)
            _last_save_time = now
        except Exception as e:
            print(f"[FLIGHT-RECORDER] SAVE ERROR: {e}")
            # Clean up tmp file if rename failed
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except:
                pass


def load_flight_state() -> tuple:
    """Load step_trail_state and ai_predictive_traps from disk.
    
    Returns:
        (step_trail_state: dict, ai_predictive_traps: dict)
        Returns empty dicts if file is missing, corrupt, or incompatible.
    """
    if not os.path.exists(STATE_FILE):
        # Auto-migrate from legacy project-local path if it exists
        if os.path.exists(_LEGACY_STATE_FILE):
            try:
                import shutil
                shutil.copy2(_LEGACY_STATE_FILE, STATE_FILE)
                print(f"[FLIGHT-RECORDER] MIGRATED state from project dir to {STATE_FILE}")
                print(f"[FLIGHT-RECORDER] Old file kept at: {_LEGACY_STATE_FILE}")
            except Exception as mig_err:
                print(f"[FLIGHT-RECORDER] Migration failed: {mig_err}. Using legacy path directly.")
                # Fall back to reading from legacy path
                try:
                    with open(_LEGACY_STATE_FILE, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                    return payload.get("step_trail_state", {}), payload.get("ai_predictive_traps", {}), payload.get("global_cooldowns", {})
                except:
                    pass
        else:
            print(f"[FLIGHT-RECORDER] No state file found at {STATE_FILE}. Starting fresh.")
            return {}, {}, {}
    
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        
        step_trail = payload.get("step_trail_state", {})
        ai_traps = payload.get("ai_predictive_traps", {})
        
        # Validate types
        if not isinstance(step_trail, dict):
            print(f"[FLIGHT-RECORDER] WARNING: step_trail_state is {type(step_trail).__name__}, expected dict. Resetting.")
            step_trail = {}
        if not isinstance(ai_traps, dict):
            print(f"[FLIGHT-RECORDER] WARNING: ai_predictive_traps is {type(ai_traps).__name__}, expected dict. Resetting.")
            ai_traps = {}
        
        meta = payload.get("_meta", {})
        saved_at = meta.get("saved_at_iso", "unknown")
        age_seconds = time.time() - meta.get("saved_at", time.time())
        age_minutes = age_seconds / 60
        
        # ── MT5 MIGRATION: Purge legacy crypto positions / traps ──
        crypto_symbols = {"BTCUSD", "BTCUSDT", "ETHUSD", "ETHUSDT", "BTC", "ETH"}
        purged_trail = {}
        purged_traps = {}
        purge_count = 0

        for key, val in step_trail.items():
            sym = str(val.get("symbol", "")).upper()
            if sym in crypto_symbols:
                print(f"[FLIGHT-RECORDER] PURGED legacy crypto position: {key} ({sym})")
                purge_count += 1
            else:
                purged_trail[key] = val

        for sym, trap in ai_traps.items():
            if sym.upper() in crypto_symbols:
                print(f"[FLIGHT-RECORDER] PURGED legacy AI trap: {sym}")
                purge_count += 1
            else:
                purged_traps[sym] = trap

        if purge_count:
            print(f"[FLIGHT-RECORDER] Cleaned {purge_count} legacy crypto item(s). System now MT5-native only.")
            # Persist the cleaned state immediately so the ghosts don't return
            save_flight_state(purged_trail, purged_traps, force=True)

        step_trail = purged_trail
        ai_traps = purged_traps

        print(f"[FLIGHT-RECORDER] State loaded from disk (saved {saved_at}, {age_minutes:.1f} min ago)")
        print(f"[FLIGHT-RECORDER]   Positions: {len(step_trail)} | AI Traps: {len(ai_traps)}")
        
        # Warn if state is very stale (> 1 hour)
        if age_seconds > 3600:
            print(f"[FLIGHT-RECORDER] WARNING: State is {age_minutes:.0f} min old. Positions may have closed. Will reconcile on first trail scan.")
            
        global_cooldowns = payload.get("global_cooldowns", {})
        
        return step_trail, ai_traps, global_cooldowns
    
    except json.JSONDecodeError as e:
        print(f"[FLIGHT-RECORDER] CORRUPT state file (JSON error: {e}). Starting fresh.")
        # Rename corrupt file for forensic inspection
        try:
            corrupt_path = STATE_FILE + f".corrupt.{int(time.time())}"
            os.rename(STATE_FILE, corrupt_path)
            print(f"[FLIGHT-RECORDER] Corrupt file preserved as: {corrupt_path}")
        except:
            pass
        return {}, {}, {}
    
    except Exception as e:
        print(f"[FLIGHT-RECORDER] LOAD ERROR: {e}. Starting fresh.")
        return {}, {}, {}
