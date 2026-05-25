"""
Key Manager - Manages API keys stored in SQLite database
"""
import sqlite3
import os
from typing import List, Dict, Optional
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "apex_keys.db")

def get_connection():
    """Get SQLite connection with row factory"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database with CREATE TABLE IF NOT EXISTS"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name TEXT NOT NULL UNIQUE,
            api_key TEXT NOT NULL,
            api_secret TEXT NOT NULL,
            network TEXT DEFAULT 'testnet',
            status TEXT DEFAULT 'active',
            trading_mode TEXT DEFAULT 'challenge',
            created_at TEXT NOT NULL
        )
    """)

    columns = {row[1] for row in cursor.execute("PRAGMA table_info(api_keys)").fetchall()}
    if "trading_mode" not in columns:
        cursor.execute("ALTER TABLE api_keys ADD COLUMN trading_mode TEXT DEFAULT 'challenge'")
        print("[KEY_MANAGER] Migrated api_keys: added trading_mode column")

    if "exchange" in columns:
        try:
            cursor.execute("ALTER TABLE api_keys DROP COLUMN exchange")
        except sqlite3.OperationalError:
            cursor.execute("""
                CREATE TABLE api_keys_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_name TEXT NOT NULL UNIQUE,
                    api_key TEXT NOT NULL,
                    api_secret TEXT NOT NULL,
                    network TEXT DEFAULT 'testnet',
                    status TEXT DEFAULT 'active',
                    trading_mode TEXT DEFAULT 'challenge',
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                INSERT INTO api_keys_new (id, account_name, api_key, api_secret, network, status, trading_mode, created_at)
                SELECT id, account_name, api_key, api_secret, network, status, 'challenge', created_at
                FROM api_keys
            """)
            cursor.execute("DROP TABLE api_keys")
            cursor.execute("ALTER TABLE api_keys_new RENAME TO api_keys")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL DEFAULT 0,
            entry_time TEXT NOT NULL,
            exit_time TEXT DEFAULT NULL,
            contracts INTEGER NOT NULL,
            leverage REAL DEFAULT 10,
            sl_price REAL DEFAULT 0,
            tp_price REAL DEFAULT 0,
            pnl REAL DEFAULT 0,
            fees REAL DEFAULT 0,
            close_reason TEXT DEFAULT NULL,
            status TEXT DEFAULT 'open',
            order_id TEXT DEFAULT NULL,
            dry_run INTEGER DEFAULT 0,
            notes TEXT DEFAULT NULL,
            ai_reasoning TEXT DEFAULT NULL
        )
    """)

    # Migrate existing databases: add ai_reasoning if missing
    trade_columns = {row[1] for row in cursor.execute("PRAGMA table_info(trade_history)").fetchall()}
    if "ai_reasoning" not in trade_columns:
        cursor.execute("ALTER TABLE trade_history ADD COLUMN ai_reasoning TEXT DEFAULT NULL")
        print("[KEY_MANAGER] Migrated trade_history: added ai_reasoning column")

    # ── OPTIONS TRADES TABLE (Isolated from futures trade_history) ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS options_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name TEXT NOT NULL,
            underlying TEXT NOT NULL DEFAULT 'BTC',
            strategy TEXT NOT NULL,
            short_symbol TEXT DEFAULT '',
            long_symbol TEXT DEFAULT '',
            strike_short REAL NOT NULL,
            strike_long REAL NOT NULL,
            spread_width REAL DEFAULT 0,
            expiry TEXT NOT NULL,
            contracts INTEGER NOT NULL DEFAULT 1,
            net_premium REAL NOT NULL DEFAULT 0,
            max_loss REAL NOT NULL DEFAULT 0,
            risk_pct REAL DEFAULT 0,
            credit_risk_ratio REAL DEFAULT 0,
            spot_at_entry REAL DEFAULT 0,
            confidence INTEGER DEFAULT 0,
            source TEXT DEFAULT 'ai',
            reasoning TEXT DEFAULT '',
            status TEXT DEFAULT 'PAPER',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print(f"[KEY_MANAGER] Database initialized at: {DB_PATH}")

def add_key(account_name: str, api_key: str, api_secret: str, network: str = "testnet", trading_mode: str = "challenge") -> Dict:
    """Add a new API key to database"""
    conn = get_connection()
    cursor = conn.cursor()
    
    created_at = datetime.now().isoformat()
    
    try:
        cursor.execute("""
            INSERT INTO api_keys (account_name, api_key, api_secret, network, status, trading_mode, created_at)
            VALUES (?, ?, ?, ?, 'active', ?, ?)
        """, (account_name, api_key, api_secret, network, trading_mode, created_at))
        conn.commit()
        
        new_key = {
            "id": cursor.lastrowid,
            "account_name": account_name,
            "api_key": api_key,
            "api_secret": api_secret,
            "network": network,
            "status": "active",
            "trading_mode": trading_mode,
            "created_at": created_at
        }
    except sqlite3.IntegrityError:
        conn.close()
        return {"error": "Account name already exists"}
    finally:
        conn.close()
    
    return new_key

def get_all_keys() -> List[Dict]:
    """Get all stored API keys"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM api_keys ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    
    keys = []
    for row in rows:
        keys.append({
            "id": row["id"],
            "account_name": row["account_name"],
            "api_key": row["api_key"],
            "api_secret": row["api_secret"],
            "network": row["network"],
            "status": row["status"],
            "trading_mode": row["trading_mode"],
            "created_at": row["created_at"]
        })
    
    return keys

def get_active_keys() -> List[Dict]:
    """Get only active API keys"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM api_keys WHERE status = 'active' ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    
    keys = []
    for row in rows:
        keys.append({
            "id": row["id"],
            "account_name": row["account_name"],
            "api_key": row["api_key"],
            "api_secret": row["api_secret"],
            "network": row["network"],
            "status": row["status"],
            "trading_mode": row["trading_mode"],
            "created_at": row["created_at"]
        })
    
    return keys

def delete_key(account_name: str) -> bool:
    """Delete API key by account name"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM api_keys WHERE account_name = ?", (account_name,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def get_key_by_account(account_name: str) -> Optional[Dict]:
    """Get a specific API key by account name"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM api_keys WHERE account_name = ?", (account_name,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row["id"],
            "account_name": row["account_name"],
            "api_key": row["api_key"],
            "api_secret": row["api_secret"],
            "network": row["network"],
            "status": row["status"],
            "trading_mode": row["trading_mode"],
            "created_at": row["created_at"]
        }
    return None

def update_trading_mode(account_name: str, mode: str) -> bool:
    """Update the trading mode for a specific account"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE api_keys SET trading_mode = ? WHERE account_name = ?", (mode, account_name))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated

def get_all_account_names(active_only: bool = False) -> List[str]:
    """Return configured account names, optionally only active ones."""
    conn = get_connection()
    cursor = conn.cursor()
    if active_only:
        cursor.execute("SELECT account_name FROM api_keys WHERE status = 'active' ORDER BY created_at DESC")
    else:
        cursor.execute("SELECT account_name FROM api_keys ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [row["account_name"] for row in rows]

def get_open_trade_counts(account_filter: str = None) -> Dict[str, int]:
    """Return open trade counts keyed by account name."""
    conn = get_connection()
    cursor = conn.cursor()
    params = []
    where = "WHERE status = 'open'"
    if account_filter:
        where += " AND account_name = ?"
        params.append(account_filter)
    cursor.execute(f"SELECT account_name, COUNT(*) as cnt FROM trade_history {where} GROUP BY account_name", params)
    rows = cursor.fetchall()
    conn.close()
    return {row["account_name"]: row["cnt"] for row in rows}

# ============================================================
# TRADE HISTORY PERSISTENCE (Bot Performance)
# ============================================================

def insert_trade(account_name: str, symbol: str, side: str, entry_price: float,
                 contracts: int, leverage: float = 10, sl_price: float = 0,
                 tp_price: float = 0, order_id: str = None, dry_run: bool = False,
                 entry_fee: float = 0, ai_reasoning: str = "") -> Dict:
    """Log a new trade when a position is opened. Returns the trade record."""
    conn = get_connection()
    cursor = conn.cursor()
    entry_time = datetime.now().isoformat()

    # Truncate long reasoning strings to prevent DB bloat
    safe_reasoning = (ai_reasoning or "")[:4000]

    try:
        cursor.execute("""
            INSERT INTO trade_history
                (account_name, symbol, side, entry_price, entry_time, contracts,
                 leverage, sl_price, tp_price, fees, status, order_id, dry_run, ai_reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
        """, (account_name, symbol, side.upper(), entry_price, entry_time,
              contracts, leverage, sl_price, tp_price, entry_fee, order_id,
              1 if dry_run else 0, safe_reasoning))
        conn.commit()
        trade_id = cursor.lastrowid
        print(f"[TRADE_DB] Logged OPEN #{trade_id}: {side.upper()} {symbol} x{contracts} @ ${entry_price} [{account_name}]")
        return {"id": trade_id, "account_name": account_name, "symbol": symbol,
                "side": side.upper(), "entry_price": entry_price, "entry_time": entry_time,
                "ai_reasoning": safe_reasoning}
    except Exception as e:
        print(f"[TRADE_DB] Insert error: {e}")
        return {"error": str(e)}
    finally:
        conn.close()


def close_trade(account_name: str, symbol: str, exit_price: float, pnl: float,
                exit_fee: float = 0, close_reason: str = "manual",
                side: str = "", entry_price: float = 0, contracts: int = 0,
                leverage: float = 10) -> bool:
    """Close the most recent open trade for this account+symbol.
    close_reason: 'manual' | 'tp' | 'sl' | 'step_trail'
    
    If no open trade is found in the DB, backfills a complete closed record
    using the provided entry data (from step_trail_state or autopsy context).
    This handles trades opened before DB tracking was added, or after server restarts.
    """
    conn = get_connection()
    cursor = conn.cursor()
    exit_time = datetime.now().isoformat()

    try:
        # Find the most recent open trade for this account + symbol
        cursor.execute("""
            SELECT id, fees FROM trade_history
            WHERE account_name = ? AND symbol = ? AND status = 'open'
            ORDER BY id DESC LIMIT 1
        """, (account_name, symbol))
        row = cursor.fetchone()

        if not row:
            # BACKFILL: No open record exists — insert a complete closed trade retroactively
            if entry_price > 0 and pnl != 0:
                print(f"[TRADE_DB] No open trade for {account_name}:{symbol}. Backfilling closed record...")
                cursor.execute("""
                    INSERT INTO trade_history
                        (account_name, symbol, side, entry_price, entry_time, exit_price, exit_time,
                         contracts, leverage, sl_price, tp_price, pnl, fees,
                         close_reason, status, order_id, dry_run)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, 'closed', '', 0)
                """, (account_name, symbol, side.upper(), entry_price, exit_time,
                      exit_price, exit_time, contracts, leverage,
                      round(pnl, 4), round(exit_fee, 4), close_reason))
                conn.commit()
                trade_id = cursor.lastrowid
                print(f"[TRADE_DB] BACKFILLED #{trade_id}: {side.upper()} {close_reason.upper()} @ ${exit_price} | PnL: ${pnl:+,.2f} [{account_name}]")
                return True
            else:
                print(f"[TRADE_DB] No open trade found for {account_name}:{symbol} to close (no backfill data)")
                conn.close()
                return False

        trade_id = row["id"]
        existing_fees = float(row["fees"] or 0)
        total_fees = existing_fees + exit_fee

        cursor.execute("""
            UPDATE trade_history
            SET exit_price = ?, exit_time = ?, pnl = ?, fees = ?,
                close_reason = ?, status = 'closed'
            WHERE id = ?
        """, (exit_price, exit_time, round(pnl, 4), round(total_fees, 4),
              close_reason, trade_id))
        conn.commit()
        print(f"[TRADE_DB] Closed #{trade_id}: {close_reason.upper()} @ ${exit_price} | PnL: ${pnl:+,.2f} | Fees: ${total_fees:.4f} [{account_name}]")
        return True
    except Exception as e:
        print(f"[TRADE_DB] Close error: {e}")
        return False
    finally:
        conn.close()


def close_trade_by_order_id(account_name: str, order_id: str, symbol: str, exit_price: float, pnl: float,
                            exit_fee: float = 0, close_reason: str = "manual",
                            side: str = "", entry_price: float = 0, contracts: int = 0,
                            leverage: float = 10) -> bool:
    """Close an exact open trade by MT5 position ticket/order_id; backfill if it was not DB-tracked."""
    if not order_id:
        return close_trade(account_name, symbol, exit_price, pnl, exit_fee, close_reason, side, entry_price, contracts, leverage)

    conn = get_connection()
    cursor = conn.cursor()
    exit_time = datetime.now().isoformat()

    try:
        cursor.execute("""
            SELECT id, fees FROM trade_history
            WHERE account_name = ? AND order_id = ? AND status = 'open'
            ORDER BY id DESC LIMIT 1
        """, (account_name, str(order_id)))
        row = cursor.fetchone()

        if row:
            trade_id = row["id"]
            total_fees = float(row["fees"] or 0) + exit_fee
            cursor.execute("""
                UPDATE trade_history
                SET exit_price = ?, exit_time = ?, pnl = ?, fees = ?,
                    close_reason = ?, status = 'closed'
                WHERE id = ?
            """, (exit_price, exit_time, round(pnl, 4), round(total_fees, 4), close_reason, trade_id))
            conn.commit()
            print(f"[TRADE_DB] Closed #{trade_id} ticket {order_id}: {close_reason.upper()} @ ${exit_price} | PnL: ${pnl:+,.2f} [{account_name}]")
            return True

        if entry_price > 0:
            print(f"[TRADE_DB] No open DB row for ticket {order_id}. Backfilling closed MT5 record...")
            cursor.execute("""
                INSERT INTO trade_history
                    (account_name, symbol, side, entry_price, entry_time, exit_price, exit_time,
                     contracts, leverage, sl_price, tp_price, pnl, fees,
                     close_reason, status, order_id, dry_run)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, 'closed', ?, 0)
            """, (account_name, symbol, side.upper(), entry_price, exit_time,
                  exit_price, exit_time, contracts, leverage,
                  round(pnl, 4), round(exit_fee, 4), close_reason, str(order_id)))
            conn.commit()
            trade_id = cursor.lastrowid
            print(f"[TRADE_DB] BACKFILLED #{trade_id} ticket {order_id}: {side.upper()} {close_reason.upper()} @ ${exit_price} | PnL: ${pnl:+,.2f} [{account_name}]")
            return True

        print(f"[TRADE_DB] No open trade found for ticket {order_id} and no backfill data")
        return False
    except Exception as e:
        print(f"[TRADE_DB] Close-by-ticket error: {e}")
        return False
    finally:
        conn.close()


def get_all_trades(account_filter: str = None, limit: int = 500) -> List[Dict]:
    """Get all trades, optionally filtered by account. Most recent first."""
    conn = get_connection()
    cursor = conn.cursor()

    if account_filter:
        cursor.execute("""
            SELECT * FROM trade_history
            WHERE account_name = ?
            ORDER BY id DESC LIMIT ?
        """, (account_filter, limit))
    else:
        cursor.execute("""
            SELECT * FROM trade_history
            ORDER BY id DESC LIMIT ?
        """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    trades = []
    for row in rows:
        trades.append({
            "id": row["id"],
            "account_name": row["account_name"],
            "symbol": row["symbol"],
            "side": row["side"],
            "entry_price": row["entry_price"],
            "exit_price": row["exit_price"],
            "entry_time": row["entry_time"],
            "exit_time": row["exit_time"],
            "contracts": row["contracts"],
            "leverage": row["leverage"],
            "sl_price": row["sl_price"],
            "tp_price": row["tp_price"],
            "pnl": row["pnl"],
            "fees": row["fees"],
            "close_reason": row["close_reason"],
            "status": row["status"],
            "order_id": row["order_id"],
            "dry_run": bool(row["dry_run"]),
            "ai_reasoning": row["ai_reasoning"] if "ai_reasoning" in row.keys() and row["ai_reasoning"] else "",
        })

    return trades


def get_trade_stats(account_filter: str = None) -> Dict:
    """Calculate aggregate bot performance stats."""
    conn = get_connection()
    cursor = conn.cursor()

    base_where = "WHERE status = 'closed'"
    params = []
    if account_filter:
        base_where += " AND account_name = ?"
        params.append(account_filter)

    # Total closed trades
    cursor.execute(f"SELECT COUNT(*) as cnt FROM trade_history {base_where}", params)
    total_closed = cursor.fetchone()["cnt"]

    # Winners
    cursor.execute(f"SELECT COUNT(*) as cnt FROM trade_history {base_where} AND pnl > 0", params)
    winners = cursor.fetchone()["cnt"]

    # Losers
    cursor.execute(f"SELECT COUNT(*) as cnt FROM trade_history {base_where} AND pnl <= 0", params)
    losers = cursor.fetchone()["cnt"]

    # Open trades
    open_where = "WHERE status = 'open'"
    open_params = []
    if account_filter:
        open_where += " AND account_name = ?"
        open_params.append(account_filter)
    cursor.execute(f"SELECT COUNT(*) as cnt FROM trade_history {open_where}", open_params)
    open_count = cursor.fetchone()["cnt"]

    # Aggregates
    cursor.execute(f"""
        SELECT
            COALESCE(SUM(pnl), 0) as total_pnl,
            COALESCE(SUM(fees), 0) as total_fees,
            COALESCE(AVG(CASE WHEN pnl > 0 THEN pnl END), 0) as avg_win,
            COALESCE(AVG(CASE WHEN pnl <= 0 THEN pnl END), 0) as avg_loss,
            COALESCE(MAX(pnl), 0) as best_trade,
            COALESCE(MIN(pnl), 0) as worst_trade
        FROM trade_history {base_where}
    """, params)
    agg = cursor.fetchone()

    # Close reason breakdown
    cursor.execute(f"""
        SELECT close_reason, COUNT(*) as cnt
        FROM trade_history {base_where}
        GROUP BY close_reason
    """, params)
    reasons = {}
    for row in cursor.fetchall():
        reasons[row["close_reason"] or "unknown"] = row["cnt"]

    # Per-account breakdown
    cursor.execute(f"""
        SELECT account_name, COUNT(*) as trades,
               COALESCE(SUM(pnl), 0) as pnl,
               COALESCE(SUM(fees), 0) as fees,
               COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) as wins
        FROM trade_history {base_where}
        GROUP BY account_name
    """, params)
    accounts = []
    for row in cursor.fetchall():
        acct_trades = row["trades"]
        accounts.append({
            "account_name": row["account_name"],
            "trades": acct_trades,
            "pnl": round(row["pnl"], 4),
            "fees": round(row["fees"], 4),
            "win_rate": round((row["wins"] / acct_trades) * 100, 1) if acct_trades > 0 else 0
        })

    conn.close()

    win_rate = round((winners / total_closed) * 100, 1) if total_closed > 0 else 0
    loss_rate = round((losers / total_closed) * 100, 1) if total_closed > 0 else 0

    return {
        "total_trades": total_closed,
        "open_trades": open_count,
        "winners": winners,
        "losers": losers,
        "win_rate": win_rate,
        "loss_rate": loss_rate,
        "total_pnl": round(agg["total_pnl"], 4),
        "total_fees": round(agg["total_fees"], 4),
        "net_pnl": round(agg["total_pnl"] - agg["total_fees"], 4),
        "avg_win": round(agg["avg_win"], 4),
        "avg_loss": round(agg["avg_loss"], 4),
        "best_trade": round(agg["best_trade"], 4),
        "worst_trade": round(agg["worst_trade"], 4),
        "close_reasons": reasons,
        "accounts": accounts
    }


def get_trade_chart_data(account_filter: str = None) -> List[Dict]:
    """Get time-series PnL data for charting (cumulative)."""
    conn = get_connection()
    cursor = conn.cursor()

    base_where = "WHERE status = 'closed'"
    params = []
    if account_filter:
        base_where += " AND account_name = ?"
        params.append(account_filter)

    cursor.execute(f"""
        SELECT id, account_name, exit_time, pnl, fees, close_reason, symbol, side
        FROM trade_history {base_where}
        ORDER BY id ASC
    """, params)

    rows = cursor.fetchall()
    conn.close()

    cumulative_pnl = 0
    chart_data = []
    for row in rows:
        cumulative_pnl += (row["pnl"] or 0)
        chart_data.append({
            "id": row["id"],
            "account": row["account_name"],
            "time": row["exit_time"],
            "pnl": round(row["pnl"] or 0, 4),
            "cumulative_pnl": round(cumulative_pnl, 4),
            "fees": round(row["fees"] or 0, 4),
            "reason": row["close_reason"],
            "symbol": row["symbol"],
            "side": row["side"]
        })

    return chart_data


def reset_trade_history(account_filter: str = None) -> Dict:
    """Purge trade history from the database. Preserves API keys.
    If account_filter is provided, only deletes trades for that account.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        if account_filter:
            cursor.execute("DELETE FROM trade_history WHERE account_name = ?", (account_filter,))
            deleted = cursor.rowcount
            print(f"[TRADE_DB] Purged {deleted} trades for account: {account_filter}")
        else:
            cursor.execute("DELETE FROM trade_history")
            deleted = cursor.rowcount
            print(f"[TRADE_DB] Purged ALL {deleted} trades from history")

        conn.commit()
        return {"success": True, "deleted": deleted}
    except Exception as e:
        print(f"[TRADE_DB] Reset error: {e}")
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


init_db()


# ============================================================
# OPTIONS TRADE PERSISTENCE (Isolated from futures trade_history)
# ============================================================
# These functions ONLY interact with the `options_trades` table.
# They do NOT touch `trade_history` or any futures data.
# ============================================================

def insert_options_trade(
    account_name: str,
    underlying: str = "BTC",
    strategy: str = "BULL_PUT_SPREAD",
    short_symbol: str = "",
    long_symbol: str = "",
    strike_short: float = 0,
    strike_long: float = 0,
    spread_width: float = 0,
    expiry: str = "",
    contracts: int = 1,
    net_premium: float = 0,
    max_loss: float = 0,
    risk_pct: float = 0,
    credit_risk_ratio: float = 0,
    spot_at_entry: float = 0,
    confidence: int = 0,
    source: str = "ai",
    reasoning: str = "",
    status: str = "PAPER"
) -> Dict:
    """Insert a new options trade record into the isolated options_trades table."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO options_trades
                (account_name, underlying, strategy, short_symbol, long_symbol,
                 strike_short, strike_long, spread_width, expiry, contracts,
                 net_premium, max_loss, risk_pct, credit_risk_ratio,
                 spot_at_entry, confidence, source, reasoning, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            account_name, underlying, strategy, short_symbol, long_symbol,
            strike_short, strike_long, spread_width, expiry, contracts,
            round(net_premium, 4), round(max_loss, 4), round(risk_pct, 2),
            round(credit_risk_ratio, 4), round(spot_at_entry, 2),
            confidence, source, reasoning, status
        ))
        conn.commit()
        trade_id = cursor.lastrowid
        print(
            f"[OPTIONS_DB] Logged #{trade_id}: {strategy} {status} | "
            f"Sell ${strike_short:,.0f} / Buy ${strike_long:,.0f} x{contracts} | "
            f"Credit: ${net_premium:.2f} | MaxLoss: ${max_loss:.2f} | Exp: {expiry}"
        )
        return {"id": trade_id, "strategy": strategy, "status": status}
    except Exception as e:
        print(f"[OPTIONS_DB] Insert error: {e}")
        return {"error": str(e)}
    finally:
        conn.close()


def get_options_trades(account_filter: str = None, limit: int = 200) -> List[Dict]:
    """Fetch options trade history, most recent first. Isolated from futures."""
    conn = get_connection()
    cursor = conn.cursor()

    if account_filter:
        cursor.execute("""
            SELECT * FROM options_trades
            WHERE account_name = ?
            ORDER BY id DESC LIMIT ?
        """, (account_filter, limit))
    else:
        cursor.execute("""
            SELECT * FROM options_trades
            ORDER BY id DESC LIMIT ?
        """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    trades = []
    for row in rows:
        trades.append({
            "id": row["id"],
            "account_name": row["account_name"],
            "underlying": row["underlying"],
            "strategy": row["strategy"],
            "short_symbol": row["short_symbol"],
            "long_symbol": row["long_symbol"],
            "strike_short": row["strike_short"],
            "strike_long": row["strike_long"],
            "spread_width": row["spread_width"],
            "expiry": row["expiry"],
            "contracts": row["contracts"],
            "net_premium": row["net_premium"],
            "max_loss": row["max_loss"],
            "risk_pct": row["risk_pct"],
            "credit_risk_ratio": row["credit_risk_ratio"],
            "spot_at_entry": row["spot_at_entry"],
            "confidence": row["confidence"],
            "source": row["source"],
            "reasoning": row["reasoning"],
            "status": row["status"],
            "timestamp": row["timestamp"],
        })

    return trades


def get_options_stats(account_filter: str = None) -> Dict:
    """Calculate aggregate options performance stats. Isolated from futures.

    Returns structure parallel to get_trade_stats() for frontend compatibility.
    """
    conn = get_connection()
    cursor = conn.cursor()

    params = []
    where = "WHERE 1=1"
    if account_filter:
        where += " AND account_name = ?"
        params.append(account_filter)

    # Total trades by status
    cursor.execute(f"""
        SELECT status, COUNT(*) as cnt FROM options_trades {where}
        GROUP BY status
    """, params)
    status_counts = {}
    total_trades = 0
    for row in cursor.fetchall():
        status_counts[row["status"]] = row["cnt"]
        total_trades += row["cnt"]

    # Aggregate financial metrics
    cursor.execute(f"""
        SELECT
            COALESCE(SUM(net_premium), 0) as total_premium_collected,
            COALESCE(SUM(max_loss), 0) as total_max_risk_exposure,
            COALESCE(AVG(net_premium), 0) as avg_premium,
            COALESCE(AVG(max_loss), 0) as avg_max_loss,
            COALESCE(AVG(risk_pct), 0) as avg_risk_pct,
            COALESCE(AVG(credit_risk_ratio), 0) as avg_credit_risk_ratio,
            COALESCE(AVG(confidence), 0) as avg_confidence,
            COALESCE(MAX(net_premium), 0) as best_premium,
            COALESCE(MIN(net_premium), 0) as worst_premium,
            COALESCE(AVG(contracts), 0) as avg_contracts
        FROM options_trades {where}
    """, params)
    agg = cursor.fetchone()

    # Strategy breakdown
    cursor.execute(f"""
        SELECT strategy, COUNT(*) as cnt,
               COALESCE(SUM(net_premium), 0) as premium,
               COALESCE(SUM(max_loss), 0) as risk
        FROM options_trades {where}
        GROUP BY strategy
    """, params)
    strategies = {}
    for row in cursor.fetchall():
        strategies[row["strategy"]] = {
            "count": row["cnt"],
            "total_premium": round(row["premium"], 4),
            "total_risk": round(row["risk"], 4)
        }

    # Per-account breakdown
    cursor.execute(f"""
        SELECT account_name, COUNT(*) as trades,
               COALESCE(SUM(net_premium), 0) as premium,
               COALESCE(SUM(max_loss), 0) as risk,
               COALESCE(AVG(confidence), 0) as avg_conf
        FROM options_trades {where}
        GROUP BY account_name
    """, params)
    accounts = []
    for row in cursor.fetchall():
        accounts.append({
            "account_name": row["account_name"],
            "trades": row["trades"],
            "total_premium": round(row["premium"], 4),
            "total_risk": round(row["risk"], 4),
            "avg_confidence": round(row["avg_conf"], 1)
        })

    # Recent 10 for quick preview
    cursor.execute(f"""
        SELECT id, strategy, strike_short, strike_long, contracts,
               net_premium, max_loss, expiry, status, confidence, timestamp
        FROM options_trades {where}
        ORDER BY id DESC LIMIT 10
    """, params)
    recent = []
    for row in cursor.fetchall():
        recent.append({
            "id": row["id"],
            "strategy": row["strategy"],
            "strike_short": row["strike_short"],
            "strike_long": row["strike_long"],
            "contracts": row["contracts"],
            "net_premium": row["net_premium"],
            "max_loss": row["max_loss"],
            "expiry": row["expiry"],
            "status": row["status"],
            "confidence": row["confidence"],
            "timestamp": row["timestamp"],
        })

    conn.close()

    return {
        "total_trades": total_trades,
        "status_breakdown": status_counts,
        "total_premium_collected": round(agg["total_premium_collected"], 4),
        "total_max_risk_exposure": round(agg["total_max_risk_exposure"], 4),
        "avg_premium_per_trade": round(agg["avg_premium"], 4),
        "avg_max_loss_per_trade": round(agg["avg_max_loss"], 4),
        "avg_risk_pct": round(agg["avg_risk_pct"], 2),
        "avg_credit_risk_ratio": round(agg["avg_credit_risk_ratio"], 4),
        "avg_confidence": round(agg["avg_confidence"], 1),
        "best_premium": round(agg["best_premium"], 4),
        "worst_premium": round(agg["worst_premium"], 4),
        "avg_contracts": round(agg["avg_contracts"], 1),
        "strategies": strategies,
        "accounts": accounts,
        "recent_trades": recent
    }
