"""Fix: Restore real account name + purge all demo trades for clean start."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "apex_keys.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# 1. Restore api_keys back to VEMBARASAN (real account)
c.execute("UPDATE api_keys SET account_name = 'VEMBARASAN' WHERE account_name = 'VEMBUDEMO'")
print(f"api_keys restored: {c.rowcount} row(s) -> VEMBARASAN")

# 2. Delete ALL demo trades (both old and renamed)
c.execute("DELETE FROM trade_history")
print(f"trade_history purged: {c.rowcount} demo trades deleted")

conn.commit()

# Verify
c.execute("SELECT id, account_name, network, status FROM api_keys")
print("\n=== API KEYS ===")
for r in c.fetchall():
    print(r)

c.execute("SELECT COUNT(*) FROM trade_history")
print(f"\nTrade history count: {c.fetchone()[0]}")

conn.close()
print("\nDone! Clean slate — ready for real trading.")
