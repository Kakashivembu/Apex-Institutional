"""
APEX Performance Tracker — Kelly Criterion + Daily Scoreboard
Implements mathematically optimal position sizing and live session metrics.
"""
import os
import json
import numpy as np
from datetime import datetime, date

# ============================================================
# KELLY CRITERION POSITION SIZING
# ============================================================

def kelly_position_size(confidence_pct: float, rr_ratio: float, max_risk_pct: float = 0.045, kelly_fraction: float = 0.50, scalper_mode: bool = False) -> float:
    """
    Fractional Kelly Criterion for optimal position sizing.
    
    Args:
        confidence_pct: AI consensus confidence (0-100)
        rr_ratio: Risk/Reward ratio (e.g., 2.0 means TP is 2x SL)
        max_risk_pct: Hard ceiling on risk per trade (default 4.5%)
        kelly_fraction: Kelly multiplier (0.25 = quarter-Kelly for safety)
        scalper_mode: If True, hard cap at 1.5% (~$15 on $1000 account)
    
    Returns:
        Optimal risk percentage of equity (e.g., 0.005 = 0.5%)
    """
    # SCALPER MODE: Hard cap risk at 1.5% ($15 on $1000 GoatFunded account)
    if scalper_mode:
        max_risk_pct = 0.015
    # Map confidence to win probability
    p = max(0.01, min(0.95, confidence_pct / 100))
    b = max(0.1, rr_ratio)  # Net odds from R:R ratio
    q = 1 - p
    
    # Full Kelly: f* = (p * b - q) / b
    full_kelly = (p * b - q) / b
    
    if full_kelly <= 0:
        # Negative edge — minimum micro-size only
        return 0.001
    
    # Fractional Kelly to reduce variance (quarter-Kelly default)
    fractional = full_kelly * kelly_fraction
    
    # Hard cap at max_risk_pct
    risk_pct = min(fractional, max_risk_pct)
    
    # Floor at 0.1% minimum
    return max(0.001, round(risk_pct, 5))


# ============================================================
# MONTE CARLO RISK ENGINE (PROBABILITY OF RUIN)
# ============================================================

def compute_probability_of_ruin(win_rate: float, avg_winner: float, avg_loser: float, starting_pnl: float = 0.0, max_drawdown: float = -20.0, trades: int = 20, iterations: int = 1000) -> float:
    """
    Runs a Monte Carlo simulation projecting the next N trades to calculate 
    the probability of the equity curve hitting the GoatFunded max drawdown limit.
    """
    if win_rate <= 0 or avg_winner <= 0 or avg_loser >= 0:
        return 0.0
        
    ruin_count = 0
    p_win = max(0.01, min(0.99, win_rate / 100.0))
    p_loss = 1.0 - p_win
    
    for _ in range(iterations):
        # Simulate trade results
        results = np.random.choice([avg_winner, avg_loser], size=trades, p=[p_win, p_loss])
        cumulative = starting_pnl + np.cumsum(results)
        
        if np.any(cumulative <= max_drawdown):
            ruin_count += 1
            
    probability = (ruin_count / iterations) * 100.0
    return round(probability, 2)


# ============================================================
# DAILY PERFORMANCE SCOREBOARD
# ============================================================

# In-memory session trade results
_session_trades = []


def record_closed_trade(symbol: str, direction: str, entry: float, exit_price: float,
                         pnl: float, confidence: float, exit_reason: str,
                         sl_pct: float = 0, tp_pct: float = 0):
    """Record a completed trade for session performance tracking."""
    _session_trades.append({
        "timestamp": datetime.now().isoformat(),
        "symbol": symbol,
        "direction": direction,
        "entry": entry,
        "exit": exit_price,
        "pnl": round(pnl, 2),
        "confidence": confidence,
        "exit_reason": exit_reason,
        "sl_pct": sl_pct,
        "tp_pct": tp_pct,
    })


def get_session_stats() -> dict:
    """Compute live session performance metrics."""
    if not _session_trades:
        return {
            "session_trades": 0, "win_rate": 0.0, "net_pnl": 0.0,
            "profit_factor": 0.0, "avg_winner": 0.0, "avg_loser": 0.0,
            "best_trade": 0.0, "worst_trade": 0.0, "streak": 0,
        }
    
    wins = [t for t in _session_trades if t["pnl"] > 0]
    losses = [t for t in _session_trades if t["pnl"] < 0]
    
    total = len(_session_trades)
    win_rate = len(wins) / total * 100 if total else 0
    
    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 99.99
    
    avg_winner = round(gross_profit / len(wins), 2) if wins else 0
    avg_loser = round(-gross_loss / len(losses), 2) if losses else 0
    
    best = max(t["pnl"] for t in _session_trades)
    worst = min(t["pnl"] for t in _session_trades)
    
    # Current streak
    streak = 0
    for t in reversed(_session_trades):
        if t["pnl"] > 0:
            if streak >= 0:
                streak += 1
            else:
                break
        elif t["pnl"] < 0:
            if streak <= 0:
                streak -= 1
            else:
                break
                
    net_pnl = sum(t["pnl"] for t in _session_trades)
    
    prob_ruin = 0.0
    if total >= 3 and avg_winner > 0 and avg_loser < 0:
        prob_ruin = compute_probability_of_ruin(win_rate, avg_winner, avg_loser, starting_pnl=net_pnl)
    
    return {
        "session_trades": total,
        "win_rate": round(win_rate, 1),
        "net_pnl": round(net_pnl, 2),
        "profit_factor": profit_factor,
        "avg_winner": avg_winner,
        "avg_loser": avg_loser,
        "best_trade": round(best, 2),
        "worst_trade": round(worst, 2),
        "streak": streak,  # Positive = win streak, negative = loss streak
        "probability_of_ruin": prob_ruin,
    }


def get_kelly_recommendation(session_stats: dict, base_confidence: float, rr_ratio: float, scalper_mode: bool = False) -> dict:
    """
    Get Kelly-adjusted position sizing that adapts to session performance.
    If session is going poorly, automatically reduce aggression.
    Scalper mode uses quarter-Kelly with $15 hard cap.
    """
    fraction = 0.50  # Default half-Kelly for Competition Mode
    
    # SCALPER MODE: Use quarter-Kelly for micro-account protection
    if scalper_mode:
        fraction = 0.25
    
    win_rate = session_stats.get("win_rate", 0)
    session_trades = session_stats.get("session_trades", 0)
    streak = session_stats.get("streak", 0)
    
    # Adaptive Kelly fraction based on live session performance
    if session_trades >= 3:
        if scalper_mode:
            # Scalper: Very conservative adaptation
            if win_rate >= 70:
                fraction = 0.35  # Slightly more aggressive on hot streak
            elif win_rate < 40:
                fraction = 0.15  # Micro-risk on cold streak
            elif streak <= -3:
                fraction = 0.10  # Emergency minimum on loss streak
        else:
            if win_rate >= 70:
                fraction = 0.75  # Highly aggressive on hot streak
            elif win_rate < 40:
                fraction = 0.25  # Reduce size on cold streak
            elif streak <= -3:
                fraction = 0.15  # Emergency reduction on loss streak
    
    risk_pct = kelly_position_size(base_confidence, rr_ratio, kelly_fraction=fraction, scalper_mode=scalper_mode)
    
    mode_label = "SCALPER" if scalper_mode else "Kelly"
    return {
        "risk_pct": risk_pct,
        "kelly_fraction": fraction,
        "reason": (
            f"{mode_label} {fraction:.0%} | WR:{win_rate:.0f}% ({session_trades} trades) | Streak:{streak:+d}"
            if session_trades >= 3 else
            f"{mode_label} {fraction:.0%} | New session ({session_trades} trades)"
        )
    }
