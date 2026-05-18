"""Quick smoke test for Flight Recorder save/load round-trip."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from core.flight_recorder import save_flight_state, load_flight_state, STATE_FILE

# Clean up any leftover test state
if os.path.exists(STATE_FILE):
    os.remove(STATE_FILE)

# Test 1: Load from missing file
s, t = load_flight_state()
assert s == {} and t == {}, "FAIL: Expected empty dicts from missing file"
print("[PASS] Load from missing file -> empty dicts")

# Test 2: Save and reload
test_trail = {
    "Acct1:BTCUSD": {
        "entry_price": 85000.0,
        "current_tier": 2,
        "current_active_sl": 85595.0,
        "peak_price": 86100.0,
        "side": "long",
        "symbol": "BTCUSD"
    }
}
test_traps = {
    "BTCUSD": {
        "predicted_trigger_price": 86500.0,
        "protective_sl_price": 86200.0,
        "reasoning": "Front-running TP resistance",
        "executed": False
    }
}

save_flight_state(test_trail, test_traps, force=True)
assert os.path.exists(STATE_FILE), "FAIL: State file not created"
print("[PASS] State file created on disk")

s, t = load_flight_state()
assert "Acct1:BTCUSD" in s, f"FAIL: Trail key missing. Got: {list(s.keys())}"
assert s["Acct1:BTCUSD"]["entry_price"] == 85000.0, "FAIL: Entry price mismatch"
assert s["Acct1:BTCUSD"]["current_tier"] == 2, "FAIL: Tier mismatch"
assert t["BTCUSD"]["predicted_trigger_price"] == 86500.0, "FAIL: Trap trigger mismatch"
print("[PASS] Round-trip data integrity verified")

# Test 3: Debounce (second save should be skipped)
import time
save_flight_state({"new": "data"}, {})  # Should be debounced (< 2s since last save)
s2, t2 = load_flight_state()
assert "Acct1:BTCUSD" in s2, "FAIL: Debounce should have prevented overwrite"
print("[PASS] Debounce prevented rapid overwrite")

# Test 4: Corrupt file recovery
with open(STATE_FILE, "w") as f:
    f.write("{invalid json!!!")
s3, t3 = load_flight_state()
assert s3 == {} and t3 == {}, "FAIL: Corrupt file should return empty dicts"
print("[PASS] Corrupt file handled gracefully")

# Cleanup
for f in os.listdir(os.path.dirname(STATE_FILE) or "."):
    if f.startswith("apex_flight_state"):
        try:
            os.remove(os.path.join(os.path.dirname(STATE_FILE) or ".", f))
        except:
            pass

print("\n=== ALL TESTS PASSED ===")
