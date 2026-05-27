"""
Apex Institutional — MT5 Historical Backtest Engine
====================================================
Fetches historical candle data from MetaTrader 5 via IPC, replays it through
the AI Swarm's 3-agent consensus pipeline, and produces a simulated trade
ledger + equity curve WITHOUT executing any live orders.

Key design constraints:
  - NVIDIA NIM 40 RPM rate limit → evaluate every `step_interval`-th candle
  - asyncio.sleep(0) yields after each evaluation to keep Uvicorn responsive
  - All synchronous MT5 calls wrapped in asyncio.to_thread()
  - One position at a time (matches live trading behaviour)
"""

import asyncio
import logging
import math
import time
import os
from datetime import datetime, timezone
from typing import Optional, Callable

try:
    import plotly.graph_objects as go
except ImportError:
    go = None

import MetaTrader5 as mt5

from core.data import compute_trend_indicators, format_for_llm
from core.mt5_engine import _resolve_tradeable_symbol
from core.brain import (
    evaluate_market,
    compute_trend_bias,
    format_trend_bias,
    detect_trend_exhaustion,
    is_aplus_setup,
    NVIDIA_KEYS,
    NVIDIA_API_KEY,
)

logger = logging.getLogger("Backtester")
logger.setLevel(logging.INFO)

# ── Maximum date range caps ────────────────────────────────────────────────
MAX_M5_DAYS = 30
MAX_H1_DAYS = 90

# Evaluation Cache for Optimizer Grid Search
_eval_cache = {}

# ── MT5 timeframe map ─────────────────────────────────────────────────────
_TF_MAP = {
    "M5":  mt5.TIMEFRAME_M5,
    "H1":  mt5.TIMEFRAME_H1,
    "M15": mt5.TIMEFRAME_M15,
}

# ══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════

async def run_fleet_backtest(
    watchlist: list,
    start_date: str,
    end_date: str,
    timeframe: str,
    capital: float,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Iterates through all assets in the watchlist, aggregates the trades, and computes global stats."""
    master_ledger = []
    
    for idx, symbol in enumerate(watchlist):
        if progress_callback:
            try:
                await progress_callback({
                    "status": "running",
                    "message": f"Processing Fleet Asset {idx+1}/{len(watchlist)}: {symbol}",
                    "pct_complete": round((idx / len(watchlist)) * 100, 1),
                    "current_time": f"Starting {symbol}...",
                    "evaluations_run": 0,
                    "trades_so_far": len(master_ledger)
                })
            except Exception:
                pass
                
        async def fleet_progress_wrapper(inner_prog: dict):
            if progress_callback:
                asset_pct = inner_prog.get("pct_complete", 0)
                global_pct = ((idx / len(watchlist)) * 100) + (asset_pct / len(watchlist))
                try:
                    await progress_callback({
                        "status": "running",
                        "message": f"Processing Fleet Asset {idx+1}/{len(watchlist)}: {symbol}",
                        "pct_complete": round(global_pct, 1),
                        "current_time": inner_prog.get("current_time", f"Processing {symbol}..."),
                        "evaluations_run": inner_prog.get("evaluations_run", 0),
                        "trades_so_far": inner_prog.get("trades_so_far", 0) + len(master_ledger)
                    })
                except Exception:
                    pass

        try:
            res = await run_historical_backtest(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                timeframe=timeframe,
                capital=capital,
                progress_callback=fleet_progress_wrapper
            )
            if res.get("success") and res.get("ledger"):
                # Tag symbol so UI knows which asset took the trade
                for trade in res["ledger"]:
                    trade["symbol"] = symbol
                    master_ledger.append(trade)
        except Exception as e:
            print(f"[FLEET BACKTEST ERROR] Failed to process {symbol}: {e}")
            
    if not master_ledger:
        summary = _compute_summary([], capital, capital, 0.0)
        
        if progress_callback:
            try:
                await progress_callback({
                    "status": "completed",
                    "message": "Fleet Backtest Complete (0 trades passed God-Tier Gatekeeper)",
                    "pct_complete": 100
                })
            except Exception:
                pass
                
        return {
            "success": True,
            "summary": summary,
            "ledger": [],
            "equity_curve": [{"time": start_date, "equity": capital}, {"time": end_date, "equity": capital}],
        }
            
    # Sort chronologically by entry_time
    master_ledger.sort(key=lambda x: x["entry_time"])
    
    # Re-calculate global equity and drawdown
    final_equity = capital
    max_equity = capital
    max_dd = 0.0
    global_equity_curve = [{"time": start_date, "equity": capital}]
    
    for trade in master_ledger:
        final_equity += trade["pnl"]
        max_equity = max(max_equity, final_equity)
        dd = (final_equity - max_equity) / max_equity * 100 if max_equity > 0 else 0
        max_dd = min(max_dd, dd)
        global_equity_curve.append({"time": trade["exit_time"], "equity": round(final_equity, 2)})
        
    summary = _compute_summary(master_ledger, capital, final_equity, max_dd)
    
    if progress_callback:
        try:
            await progress_callback({
                "status": "completed",
                "message": f"Fleet Backtest Complete ({len(master_ledger)} trades)",
                "pct_complete": 100
            })
        except Exception:
            pass
            
    return {
        "success": True,
        "summary": summary,
        "ledger": master_ledger,
        "equity_curve": global_equity_curve,
    }


async def run_historical_backtest(
    symbol: str = "GOLD.i#",
    start_date: str = "2025-05-01",
    end_date: str = "2025-05-07",
    timeframe: str = "H1",
    capital: float = 10_000.0,
    step_interval: int = 0,
    progress_callback=None,
    sl_override: float = None,
    tp_override: float = None,
    leverage_override: int = None,
    cache_only: bool = False,
) -> dict:
    """
    Main entry point.  Returns the full backtest result dict.

    Parameters
    ----------
    symbol        : MT5 symbol (resolved via broker alias map)
    start_date    : ISO date string  YYYY-MM-DD
    end_date      : ISO date string  YYYY-MM-DD
    timeframe     : "M5" | "H1" | "M15"
    capital       : starting equity for simulation
    step_interval : evaluate every N-th candle (0 = auto: 12 for M5, 1 for H1)
    progress_callback : async callable(dict) to push progress updates
    """

    # ── 1. Validate inputs ─────────────────────────────────────────────
    tf_key = timeframe.upper()
    mt5_tf = _TF_MAP.get(tf_key)
    if mt5_tf is None:
        return _error(f"Unsupported timeframe '{timeframe}'. Use M5, M15, or H1.")

    try:
        dt_start = datetime.strptime(start_date, "%Y-%m-%d")
        dt_end   = datetime.strptime(end_date,   "%Y-%m-%d").replace(hour=23, minute=59)
    except ValueError:
        return _error("Invalid date format. Use YYYY-MM-DD.")

    if dt_end <= dt_start:
        return _error("end_date must be after start_date.")

    day_span = (dt_end - dt_start).days
    max_days = MAX_M5_DAYS if tf_key == "M5" else MAX_H1_DAYS
    if day_span > max_days:
        return _error(f"Date range too large ({day_span}d). Maximum is {max_days} days for {tf_key}.")

    # step_interval is calculated dynamically after fetching candles if <= 0

    # -- 2. Check MT5 IPC (auto-recover if bridge dropped) ----------------
    term_info = await asyncio.to_thread(mt5.terminal_info)
    if term_info is None:
        print("[BACKTEST] MT5 IPC dead - attempting re-initialization...")
        init_ok = await asyncio.to_thread(mt5.initialize)
        if not init_ok:
            err = mt5.last_error()
            return _error(
                f"MT5 IPC connection is dead and re-init failed ({err}). "
                f"Ensure MetaTrader 5 is physically open, Algo Trading is enabled (green), "
                f"and the terminal is logged in."
            )
        print("[BACKTEST] MT5 re-initialized successfully.")

    resolved = _resolve_tradeable_symbol(symbol)
    print(f"[BACKTEST] Symbol resolved: {symbol} -> {resolved}")

    # Ensure symbol is visible in Market Watch before requesting history
    mt5.symbol_select(resolved, True)

    # -- 3. Fetch historical candles ----------------------------------------
    print(f"[BACKTEST] Fetching {tf_key} candles for {resolved} from {start_date} to {end_date} ...")

    rates = mt5.copy_rates_range(resolved, mt5_tf, dt_start, dt_end)

    if rates is None or len(rates) == 0:
        err = mt5.last_error()
        return _error(
            f"MT5 returned no historical data for {resolved} ({tf_key}) in "
            f"{start_date} -> {end_date}. Ensure the symbol is in Market Watch "
            f"and history is downloaded. MT5 error: {err}"
        )

    # Convert structured numpy array -> list of dicts
    candles = _rates_to_dicts(rates)
    total_candles = len(candles)
    print(f"[BACKTEST] Received {total_candles} candles.")

    if step_interval <= 0:
        step_interval = 1
        print(f"[BACKTEST] Dynamic Step Interval disabled (step=1) for exhaustive A+ Gatekeeper testing.")

    # ── 4. Also fetch multi-timeframe context candles (for richer AI prompts) ──
    # We'll fetch 1H and 4H candles for the same range for Macro agent context
    h1_rates = mt5.copy_rates_range(resolved, mt5.TIMEFRAME_H1, dt_start, dt_end) if tf_key != "H1" else rates
    h4_rates = mt5.copy_rates_range(resolved, mt5.TIMEFRAME_H4, dt_start, dt_end)

    h1_candles = _rates_to_dicts(h1_rates) if h1_rates is not None else []
    h4_candles = _rates_to_dicts(h4_rates) if h4_rates is not None else []

    # ── 5. Simulation loop ─────────────────────────────────────────────
    ledger = []
    equity = capital
    cooldowns = {}
    equity_curve = [{"time": start_date, "equity": round(equity, 2)}]
    position = None  # None or {side, entry_price, sl_price, tp_price, entry_time, reasoning}
    peak_equity = capital
    max_drawdown = 0.0
    evaluations_run = 0
    lookback = 50  # candles of lookback for indicator computation

    total_steps = len(range(lookback, total_candles, step_interval))
    step_count = 0

    for idx in range(lookback, total_candles, step_interval):
        step_count += 1

        # Yield to event loop — prevent Uvicorn blocking
        await asyncio.sleep(0)

        current_candle = candles[idx]
        current_price = current_candle["close"]
        candle_time = current_candle["time_str"]

        # ── 5a. If we have an open position, check SL/TP on intervening candles ──
        if position is not None:
            # Check all candles between last eval and this one
            check_start = max(lookback, idx - step_interval)
            for ci in range(check_start, idx + 1):
                c = candles[ci]
                exit_result = _check_exit(position, c)
                if exit_result is not None:
                    pnl = exit_result["pnl"]
                    equity += pnl
                    peak_equity = max(peak_equity, equity)
                    dd = (equity - peak_equity) / peak_equity * 100 if peak_equity > 0 else 0
                    max_drawdown = min(max_drawdown, dd)

                    if pnl < 0:
                        cooldowns[resolved] = c["time"]

                    ledger.append({
                        "entry_time": position["entry_time"],
                        "exit_time": c["time_str"],
                        "side": position["side"],
                        "entry_price": round(position["entry_price"], 5),
                        "exit_price": round(exit_result["exit_price"], 5),
                        "pnl": round(pnl, 2),
                        "pnl_pct": round((pnl / position["equity_at_entry"]) * 100, 3),
                        "exit_reason": exit_result["reason"],
                        "reasoning": position["reasoning"],
                    })
                    equity_curve.append({"time": c["time_str"], "equity": round(equity, 2)})
                    
                    if go is not None:
                        _generate_trade_chart(position, exit_result, pnl, resolved, candles, position.get("entry_idx", ci), ci, len(ledger))
                        
                    position = None
                    break

        # ── 5b. Build synthetic market data text for the AI ──────────
        window = candles[max(0, idx - lookback): idx + 1]
        market_data_text = _build_market_data_text(
            symbol=resolved,
            primary_candles=window,
            primary_tf=tf_key,
            h1_candles=_get_context_window(h1_candles, current_candle["time"], 50),
            h4_candles=_get_context_window(h4_candles, current_candle["time"], 20),
            current_price=current_price,
        )

        # ── 5c. Run AI consensus (only if no open position) ─────────
        if position is None:
            if resolved in cooldowns and (current_candle["time"] - cooldowns[resolved]) < 1800:
                print(f"[GATEKEEPER] Asset {resolved} in Cooldown. Skipping setup to prevent overtrading.")
                continue

            evaluations_run += 1

            if progress_callback:
                try:
                    await progress_callback({
                        "status": "running",
                        "candles_processed": idx,
                        "candles_total": total_candles,
                        "evaluations_run": evaluations_run,
                        "evaluations_total": total_steps,
                        "trades_so_far": len(ledger),
                        "current_equity": round(equity, 2),
                        "current_time": candle_time,
                        "pct_complete": round((step_count / total_steps) * 100, 1),
                    })
                except Exception:
                    pass

            cache_key = f"{resolved}_{candle_time}_{tf_key}"
            if cache_key in _eval_cache:
                result = _eval_cache[cache_key]
            else:
                try:
                    result = await _evaluate_backtest(
                        market_data_text=market_data_text,
                        current_price=current_price,
                        symbol=resolved,
                        candle_time=candle_time,
                        window=window,
                    )
                    _eval_cache[cache_key] = result
                except Exception as e:
                    print(f"[BACKTEST] AI eval error at {candle_time}: {e}")
                    continue
            
            if cache_only:
                continue

            action = result.get("action", "HOLD")

            if action in ("LONG", "SHORT"):
                sl_pct = sl_override if sl_override is not None else result.get("stop_loss_pct", 1.5)
                tp_pct = tp_override if tp_override is not None else result.get("take_profit_pct", 4.0)

                if action == "LONG":
                    sl_price = current_price * (1 - sl_pct / 100)
                    tp_price = current_price * (1 + tp_pct / 100)
                else:
                    sl_price = current_price * (1 + sl_pct / 100)
                    tp_price = current_price * (1 - tp_pct / 100)

                # Dynamic risk sizing
                abs_score = abs(result.get("_debug", {}).get("trend_bias", {}).get("score", 0))
                if abs_score >= 35:
                    base_risk = 0.03
                elif abs_score >= 30:
                    base_risk = 0.02
                else:
                    base_risk = 0.01

                position = {
                    "side": action,
                    "entry_price": current_price,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "sl_pct": sl_pct,
                    "tp_pct": tp_pct,
                    "equity_at_entry": equity,
                    "entry_time": candle_time,
                    "entry_idx": idx,
                    "reasoning": result.get("reasoning", ""),
                    "risk_pct": base_risk,
                }
                print(f"[BACKTEST] {action} @ {current_price:.2f} | SL: {sl_price:.2f} | TP: {tp_price:.2f} | {candle_time}")

    # ── 6. Force-close any open position at final candle ────────────
    if position is not None and total_candles > 0:
        final = candles[-1]
        final_price = final["close"]
        risk_pct = position.get("risk_pct", 0.02)
        max_risk_dollars = position["equity_at_entry"] * risk_pct
        if position["side"] == "LONG":
            raw_pnl = final_price - position["entry_price"]
            sl_dist = position["entry_price"] - position["sl_price"]
        else:
            raw_pnl = position["entry_price"] - final_price
            sl_dist = position["sl_price"] - position["entry_price"]
            
        if sl_dist > 0:
            pnl = (raw_pnl / sl_dist) * max_risk_dollars
        else:
            pnl = 0
            
        equity += pnl
        ledger.append({
            "entry_time": position["entry_time"],
            "exit_time": final["time_str"],
            "side": position["side"],
            "entry_price": round(position["entry_price"], 5),
            "exit_price": round(final_price, 5),
            "pnl": round(pnl, 2),
            "pnl_pct": round((pnl / position["equity_at_entry"]) * 100, 3),
            "exit_reason": "END_OF_DATA",
            "reasoning": position["reasoning"],
        })
        equity_curve.append({"time": final["time_str"], "equity": round(equity, 2)})
        
        if go is not None:
            _generate_trade_chart(position, {"exit_price": final_price, "reason": "END_OF_DATA"}, pnl, resolved, candles, position.get("entry_idx", len(candles)-1), len(candles)-1, len(ledger))

    # ── 7. Compute summary stats ───────────────────────────────────
    summary = _compute_summary(ledger, capital, equity, max_drawdown)

    print(f"[BACKTEST] Complete: {summary['total_trades']} trades | "
          f"WR: {summary['win_rate']}% | PnL: ${summary['total_pnl']:+,.2f} | "
          f"PF: {summary['profit_factor']} | Sharpe: {summary['sharpe_ratio']}")

    return {
        "success": True,
        "ledger": ledger,
        "summary": summary,
        "equity_curve": equity_curve,
        "candles_processed": total_candles,
        "evaluations_run": evaluations_run,
        "symbol": resolved,
        "timeframe": tf_key,
        "start_date": start_date,
        "end_date": end_date,
    }


# ══════════════════════════════════════════════════════════════════════════
# AI CONSENSUS (Backtest-specific — no live MT5 calls)
# ══════════════════════════════════════════════════════════════════════════

async def _evaluate_backtest(market_data_text: str, current_price: float, symbol: str, candle_time: str = "", window: list = None) -> dict:
    """
    Lightweight consensus pipeline for backtesting.
    Now directly feeds into the Single Continuous Hermes Pipeline via evaluate_market.
    """
    # Build trend bias from candle data (zero API cost)
    trend_bias = compute_trend_bias(market_data_text)
    trend_score = trend_bias["score"]
    trend_label = trend_bias["label"]
    
    # ── LIQUIDITY SWEEP CHECK ──
    from core.macro_sensors import detect_liquidity_sweep
    sweep_result = detect_liquidity_sweep(window) if window else None

    # ── A+ SETUP GATEKEEPER ──
    aplus_pass, reject_reason = is_aplus_setup(market_data_text, trend_bias, float(current_price or 0.0), symbol, timestamp_str=candle_time, sweep_result=sweep_result)
    if not aplus_pass:
        return {
            "action": "HOLD",
            "confidence": 0,
            "reasoning": f"Rejected by A+ Filter: {reject_reason}"
        }

    print("[BACKTEST-THROTTLE] Pacing AI requests to protect IP limits. Sleeping 15s...")
    await asyncio.sleep(15)

    # Call the new unified evaluate_market
    result = await evaluate_market(
        memory_text="[BACKTEST ENVIRONMENT]",
        market_data_text=market_data_text,
        margin=10000.0,
        dom_data="",
        active_positions=[],
        force_run=True,
        active_symbol=symbol,
        live_asset_price=current_price,
        broadcast_callback=None
    )
    
    final_action = result.get("action", "HOLD")
    
    # Exhaustion veto
    exhaustion = detect_trend_exhaustion(market_data_text, final_action)
    if final_action in ("LONG", "SHORT") and exhaustion.get("veto"):
        final_action = "HOLD"

    ai_sl = result.get("stop_loss", 1.5)
    ai_tp = result.get("take_profit", 4.0)
    
    rr = round(ai_tp / ai_sl, 2) if ai_sl > 0 else 0
    if final_action in ("LONG", "SHORT") and (rr < 1.5 or ai_tp < 0.2):
        final_action = "HOLD"

    return {
        "action": final_action,
        "stop_loss_pct": ai_sl,
        "take_profit_pct": ai_tp,
        "leverage": result.get("leverage", 10),
        "reasoning": result.get("_debug", {}).get("hermes_reasoning", ""),
    }


# ══════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _rates_to_dicts(rates) -> list:
    """Convert MT5 numpy structured array to list of dicts."""
    out = []
    for r in rates:
        ts = int(r[0])  # time field is Unix timestamp
        out.append({
            "time": ts,
            "time_str": datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M"),
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
            "volume": int(r[5]),
        })
    return out


def _get_context_window(candles: list, ref_time: int, window: int) -> list:
    """Get the last `window` candles up to and including `ref_time`."""
    filtered = [c for c in candles if c["time"] <= ref_time]
    return filtered[-window:] if len(filtered) > window else filtered


def _build_market_data_text(
    symbol: str,
    primary_candles: list,
    primary_tf: str,
    h1_candles: list,
    h4_candles: list,
    current_price: float,
) -> str:
    """
    Construct a market_data_text string identical in format to what
    evaluate_market receives in live mode.  Uses format_for_llm() from
    core/data.py for consistency.
    """
    # Build the multi-resolution dict that format_for_llm expects
    market_data = {symbol: {}}

    # Primary timeframe
    tf_label = primary_tf.lower()
    market_data[symbol][tf_label] = primary_candles[-50:]

    # Context timeframes
    if h1_candles and primary_tf != "H1":
        market_data[symbol]["1h"] = h1_candles[-50:]
    if h4_candles:
        market_data[symbol]["4h"] = h4_candles[-20:]

    candle_text = format_for_llm(market_data)
    
    from core.macro_sensors import detect_asian_range
    amd_data = detect_asian_range(h1_candles if h1_candles else primary_candles, current_price)
    asian_range_str = amd_data.get("description", "Range Unknown")

    header = (
        f"=== HISTORICAL {symbol} MARKET DATA (MT5 Backtest Replay) ===\n"
        f"Current Price: ${current_price:,.2f}\n"
        f"Timeframe: {primary_tf}\n"
        f"Source: MT5 Historical Candles\n\n"
        f"=== ICT LIQUIDITY & AMD PATTERN ===\n"
        f"{asian_range_str}\n\n"
    )

    return header + candle_text


def _check_exit(position: dict, candle: dict) -> Optional[dict]:
    """
    Check if a candle triggers SL or TP for the open position.
    Returns None if no exit, or {exit_price, pnl, reason}.
    SL is checked first (conservative assumption).
    """
    side = position["side"]
    entry = position["entry_price"]
    sl = position["sl_price"]
    tp = position["tp_price"]
    high = candle["high"]
    low = candle["low"]
    
    # Dynamic Risk Parity Math
    risk_pct = position.get("risk_pct", 0.02)
    max_risk_dollars = position["equity_at_entry"] * risk_pct
    rr = position["tp_pct"] / position["sl_pct"] if position["sl_pct"] > 0 else 1

    if side == "LONG":
        # SL hit?
        if low <= sl:
            return {"exit_price": sl, "pnl": -max_risk_dollars, "reason": "SL"}
        # TP hit?
        if high >= tp:
            return {"exit_price": tp, "pnl": max_risk_dollars * rr, "reason": "TP"}
    else:  # SHORT
        # SL hit?
        if high >= sl:
            return {"exit_price": sl, "pnl": -max_risk_dollars, "reason": "SL"}
        # TP hit?
        if low <= tp:
            return {"exit_price": tp, "pnl": max_risk_dollars * rr, "reason": "TP"}

    return None


def _compute_summary(ledger: list, initial_capital: float, final_equity: float, max_dd: float) -> dict:
    """Compute aggregate stats from the trade ledger."""
    if not ledger:
        return {
            "total_trades": 0, "winners": 0, "losers": 0,
            "win_rate": 0.0, "total_pnl": 0.0, "max_drawdown": 0.0,
            "profit_factor": 0.0, "sharpe_ratio": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0,
            "final_equity": round(final_equity, 2),
        }

    wins = [t for t in ledger if t["pnl"] > 0]
    losses = [t for t in ledger if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in ledger)
    gross_profit = sum(t["pnl"] for t in wins) if wins else 0
    gross_loss = abs(sum(t["pnl"] for t in losses)) if losses else 0

    pnl_values = [t["pnl"] for t in ledger]
    avg_pnl = sum(pnl_values) / len(pnl_values) if pnl_values else 0
    std_pnl = (sum((p - avg_pnl) ** 2 for p in pnl_values) / len(pnl_values)) ** 0.5 if len(pnl_values) > 1 else 0
    sharpe = round(avg_pnl / std_pnl, 2) if std_pnl > 0 else 0.0

    return {
        "total_trades": len(ledger),
        "winners": len(wins),
        "losers": len(losses),
        "win_rate": round((len(wins) / len(ledger)) * 100, 1),
        "total_pnl": round(total_pnl, 2),
        "max_drawdown": round(max_dd, 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else 999.0,
        "sharpe_ratio": sharpe,
        "avg_win": round(gross_profit / len(wins), 2) if wins else 0.0,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0.0,
        "final_equity": round(final_equity, 2),
    }


def _error(msg: str) -> dict:
    """Standard error envelope."""
    print(f"[BACKTEST ERROR] {msg}")
    return {"success": False, "error": msg}


def _generate_trade_chart(position: dict, exit_result: dict, pnl: float, symbol: str, candles: list, entry_idx: int, exit_idx: int, trade_id: int):
    """Generate a Plotly Candlestick chart for a completed trade and save it as HTML."""
    try:
        import os; os.makedirs('backtest_charts', exist_ok=True)
        
        start_idx = max(0, entry_idx - 5)
        end_idx = min(len(candles) - 1, exit_idx + 10)
        chart_candles = candles[start_idx:end_idx+1]
        
        times = [c["time_str"] for c in chart_candles]
        opens = [c["open"] for c in chart_candles]
        highs = [c["high"] for c in chart_candles]
        lows = [c["low"] for c in chart_candles]
        closes = [c["close"] for c in chart_candles]
        
        fig = go.Figure(data=[go.Candlestick(x=times, open=opens, high=highs, low=lows, close=closes)])
        
        entry_price = position["entry_price"]
        sl_price = position["sl_price"]
        tp_price = position["tp_price"]
        
        fig.add_hline(y=entry_price, line_dash="solid", line_color="blue", annotation_text="Entry")
        fig.add_hline(y=sl_price, line_dash="dash", line_color="red", annotation_text="SL")
        fig.add_hline(y=tp_price, line_dash="dash", line_color="green", annotation_text="TP")
        
        color = "green" if pnl > 0 else "red"
        fig.add_annotation(
            x=candles[exit_idx]["time_str"],
            y=exit_result["exit_price"],
            text=f"Exit ({exit_result['reason']})",
            showarrow=True,
            arrowhead=1,
            arrowcolor=color,
            font=dict(color=color)
        )
        
        title = f"Trade #{trade_id} - {symbol} - {position['side']} - PnL: ${pnl:.2f}"
        fig.update_layout(title=title, xaxis_title="Time", yaxis_title="Price", template="plotly_dark", xaxis_rangeslider_visible=False)
        
        filename = f"backtest_charts/trade_{trade_id}_{symbol.replace('.','_')}_{pnl:.2f}.html"
        fig.write_html(filename)
    except Exception as e:
        import traceback
        print(f"[CHART ERROR] Failed to generate visual for trade: {e}")
        print(traceback.format_exc())
