"""
Apex Institutional — Hyperparameter Grid Search Engine
======================================================
Runs an automated optimization grid over historical data by injecting
different SL and TP multipliers. Relies on the _eval_cache in the
backtester to avoid redundant NVIDIA API calls.
"""

import asyncio
import itertools
from typing import Callable, Optional

from core.backtester import run_historical_backtest

async def run_grid_search(
    symbol: str,
    start_date: str,
    end_date: str,
    timeframe: str,
    sl_range: dict,  # {"min": 0.5, "max": 2.0, "step": 0.5}
    tp_range: dict,  # {"min": 1.0, "max": 4.0, "step": 1.0}
    capital: float,
    progress_callback: Optional[Callable] = None,
    is_cancelled: Optional[Callable] = None,
) -> dict:
    """
    Executes a grid search across the defined SL and TP parameter ranges.
    Returns the top 10 results sorted by profit factor.
    """
    
    # 1. Generate grid
    def float_range(start, stop, step):
        current = start
        while current <= stop:
            yield round(current, 2)
            current += step
            
    sl_values = list(float_range(sl_range["min"], sl_range["max"], sl_range["step"]))
    tp_values = list(float_range(tp_range["min"], tp_range["max"], tp_range["step"]))
    
    combinations = list(itertools.product(sl_values, tp_values))
    total_iterations = len(combinations)
    
    if total_iterations == 0:
        return {"success": False, "error": "Invalid grid parameters. Zero combinations generated."}

    # 2. Pre-flight Cache Run
    # Run the backtester once with standard parameters to fetch and cache all AI signals.
    # We pass a wrapper callback to show progress during the caching phase
    async def caching_progress(prog: dict):
        if progress_callback:
            await progress_callback({
                "status": "caching",
                "message": f"Pre-fetching AI directional signals ({prog.get('pct_complete', 0)}%)...",
                "pct_complete": prog.get('pct_complete', 0)
            })
            
    cache_result = await run_historical_backtest(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        timeframe=timeframe,
        capital=capital,
        step_interval=0,
        progress_callback=caching_progress,
        cache_only=True
    )
    
    if not cache_result.get("success"):
        return cache_result  # Abort if MT5 data fetch fails or API breaks

    # 3. Grid Iteration Loop
    results = []
    
    for idx, (sl, tp) in enumerate(combinations):
        if is_cancelled and is_cancelled():
            if progress_callback:
                await progress_callback({
                    "status": "cancelled",
                    "message": "Optimization cancelled by user.",
                    "pct_complete": 100
                })
            break

        if progress_callback:
            await progress_callback({
                "status": "optimizing",
                "message": f"Running grid iteration {idx+1}/{total_iterations}: SL={sl}% TP={tp}%",
                "pct_complete": round((idx / total_iterations) * 100, 1),
                "current_iteration": idx + 1,
                "total_iterations": total_iterations
            })

        # Run headless backtest with overrides (uses cache)
        bt_result = await run_historical_backtest(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            capital=capital,
            step_interval=0,
            progress_callback=None,
            sl_override=sl,
            tp_override=tp
        )
        
        if bt_result.get("success"):
            summary = bt_result["summary"]
            results.append({
                "sl_pct": sl,
                "tp_pct": tp,
                "total_trades": summary["total_trades"],
                "win_rate": summary["win_rate"],
                "profit_factor": summary["profit_factor"],
                "total_pnl": summary["total_pnl"],
                "max_drawdown": summary["max_drawdown"],
                "sharpe_ratio": summary["sharpe_ratio"]
            })
            
        # Yield to event loop to prevent server lockup
        await asyncio.sleep(0)
        
    # 4. Sort and return Top 10
    # Sort by profit_factor first (avoiding 999.0 which means no losses), then by total_pnl
    valid_results = [r for r in results if r["total_trades"] > 0]
    
    sorted_results = sorted(
        valid_results, 
        key=lambda x: (x["profit_factor"] if x["profit_factor"] < 999.0 else 0, x["total_pnl"]), 
        reverse=True
    )
    
    top_10 = sorted_results[:10]
    
    if progress_callback:
        await progress_callback({
            "status": "complete",
            "message": "Optimization complete.",
            "pct_complete": 100,
            "top_results": top_10
        })

    return {
        "success": True,
        "total_combinations_tested": total_iterations,
        "top_results": top_10
    }
