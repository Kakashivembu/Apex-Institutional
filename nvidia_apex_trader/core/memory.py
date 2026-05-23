"""
APEX Trading Memory — Persistent failure classification and lesson learning.
Every losing trade is classified and the lesson is injected into agent prompts
so the system learns from mistakes and avoids repeating them.
"""
import os
import json
from datetime import datetime

MEMORY_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'APEX_MEMORY.md')
TRADE_JOURNAL = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'APEX_TRADE_JOURNAL.json')

# Keep last N lessons in memory to avoid infinite growth
MAX_MEMORY_LESSONS = 25


def load_memory() -> str:
    """Load trading memory for injection into AI agent prompts."""
    if not os.path.exists(MEMORY_FILE):
        return "No memory found."
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return "No memory found."


def append_to_memory(new_rule: str):
    """Append a new lesson to memory and keep it within MAX_MEMORY_LESSONS."""
    try:
        lines = []
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()

        # Add new lesson
        timestamp = datetime.now().strftime("%m/%d %H:%M")
        lines.append(f"\n- [{timestamp}] {new_rule}")

        # Keep only the header + last N lessons
        header_lines = [l for l in lines if not l.strip().startswith("- [")]
        lesson_lines = [l for l in lines if l.strip().startswith("- [")]
        trimmed = header_lines + lesson_lines[-MAX_MEMORY_LESSONS:]

        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            f.writelines(trimmed)
    except Exception as e:
        print(f"[MEMORY] Error writing memory: {e}")


def classify_trade_failure(trade_data: dict) -> str:
    """
    Classify why a losing trade failed.
    
    Categories:
        WEAK_SIGNAL   — Low confidence entry that shouldn't have triggered
        SL_TOO_TIGHT  — SL distance was too small for the asset's ATR
        BAD_TIMING    — Entered too late in the trend (near exhaustion)
        TREND_REVERSAL— Macro trend reversed after entry
        SPREAD_KILL   — Loss approximately equals the spread (noise kill)
        UNKNOWN       — Unclassified
    """
    pnl = float(trade_data.get("realized_pnl", 0))
    confidence = float(trade_data.get("confidence", 0))
    sl_pct = float(trade_data.get("sl_pct", 0))
    tp_pct = float(trade_data.get("tp_pct", 0))
    entry = float(trade_data.get("entry_price", 0))
    exit_price = float(trade_data.get("exit_price", 0))
    tier_reached = int(trade_data.get("tier_reached", 0))
    exit_reason = str(trade_data.get("exit_reason", ""))
    symbol = str(trade_data.get("symbol", "")).upper()
    
    if pnl >= 0:
        return "PROFITABLE"
    
    # Check if loss was tiny (spread-width)
    if entry > 0 and abs(pnl) > 0:
        loss_pct = abs(exit_price - entry) / entry * 100 if entry > 0 else 0
        # Gold: spread is ~0.03-0.05%, Forex: ~0.01-0.02%
        is_gold = any(m in symbol for m in ("GOLD", "XAU"))
        spread_threshold = 0.05 if is_gold else 0.02
        if loss_pct <= spread_threshold:
            return "SPREAD_KILL"
    
    # Low confidence entry
    if confidence < 65:
        return "WEAK_SIGNAL"
    
    # SL was too tight for the asset class
    is_wide_asset = any(m in symbol for m in ("GOLD", "XAU", "SILVER", "XAG", "US30", "US100", "BTC"))
    if is_wide_asset and sl_pct < 0.06:
        return "SL_TOO_TIGHT"
    elif not is_wide_asset and sl_pct < 0.025:
        return "SL_TOO_TIGHT"
    
    # Reached tier 1+ but still lost — trend reversed on you
    if tier_reached >= 1:
        return "TREND_REVERSAL"
    
    # Exit was at SL (never moved favorably)
    if exit_reason == "sl":
        return "BAD_TIMING"
    
    return "UNKNOWN"


def record_trade_outcome(trade_data: dict):
    """
    Record a completed trade's outcome. For losses, classify the failure
    and append the lesson to APEX_MEMORY.md for future agent reference.
    """
    pnl = float(trade_data.get("realized_pnl", 0))
    symbol = trade_data.get("symbol", "UNKNOWN")
    direction = trade_data.get("side", "long").upper()
    exit_reason = trade_data.get("exit_reason", "unknown")
    
    # Classify
    failure_class = classify_trade_failure(trade_data)
    
    # Log to journal file
    journal_entry = {
        "timestamp": datetime.now().isoformat(),
        "symbol": symbol,
        "direction": direction,
        "entry": trade_data.get("entry_price"),
        "exit": trade_data.get("exit_price"),
        "pnl": round(pnl, 2),
        "exit_reason": exit_reason,
        "tier_reached": trade_data.get("tier_reached", 0),
        "confidence": trade_data.get("confidence", 0),
        "failure_class": failure_class,
    }
    _append_journal(journal_entry)
    
    # For losses, write the lesson to memory
    if pnl < 0:
        lesson = f"**{failure_class}** {symbol} {direction} lost ${abs(pnl):.2f} (exit: {exit_reason})"
        
        # Add actionable guidance based on classification
        if failure_class == "SPREAD_KILL":
            lesson += " → Avoid entries during low-liquidity periods"
        elif failure_class == "WEAK_SIGNAL":
            lesson += " → Only enter when AI confidence ≥ 70%"
        elif failure_class == "SL_TOO_TIGHT":
            lesson += " → Widen SL for this asset class"
        elif failure_class == "BAD_TIMING":
            lesson += " → Wait for deeper pullback before entry"
        elif failure_class == "TREND_REVERSAL":
            lesson += " → Reached TP tier but trend reversed; consider faster partial close"
        
        append_to_memory(lesson)
        print(f"[MEMORY] Loss classified: {failure_class} | {lesson}")
    else:
        print(f"[MEMORY] Win recorded: {symbol} {direction} +${pnl:.2f} via {exit_reason}")
    
    return failure_class


def _append_journal(entry: dict):
    """Append to the JSON trade journal (persistent file)."""
    try:
        journal = []
        if os.path.exists(TRADE_JOURNAL):
            with open(TRADE_JOURNAL, 'r', encoding='utf-8') as f:
                journal = json.load(f)
        
        journal.append(entry)
        
        # Keep last 200 trades
        journal = journal[-200:]
        
        with open(TRADE_JOURNAL, 'w', encoding='utf-8') as f:
            json.dump(journal, f, indent=2)
    except Exception as e:
        print(f"[MEMORY] Journal write error: {e}")


def get_recent_failure_summary(n: int = 5) -> str:
    """Get a summary of recent failures for injection into agent prompts."""
    try:
        if not os.path.exists(TRADE_JOURNAL):
            return ""
        with open(TRADE_JOURNAL, 'r', encoding='utf-8') as f:
            journal = json.load(f)
        
        losses = [t for t in journal if t.get("pnl", 0) < 0][-n:]
        if not losses:
            return ""
        
        # Count failure types
        from collections import Counter
        classes = Counter(t.get("failure_class", "UNKNOWN") for t in losses)
        most_common = classes.most_common(1)[0] if classes else ("NONE", 0)
        
        return f"Recent {len(losses)} losses: {dict(classes)}. Most common: {most_common[0]} ({most_common[1]}x). Avoid repeating."
    except Exception:
        return ""
