import React, { useState, useEffect } from 'react';
import { Play, Settings, RefreshCw, BarChart2, Activity, ChevronRight, Zap } from 'lucide-react';
import { API_BASE } from '../lib/api';

const MACRO_ASSETS = [
  { id: 'GOLD.i#', label: 'Gold (XAUUSD)' },
  { id: 'SILVER.i#', label: 'Silver (XAGUSD)' },
  { id: 'US30Cash#', label: 'US30 (Dow)' },
  { id: 'EURUSD#', label: 'EUR/USD' },
  { id: 'GBPUSD#', label: 'GBP/USD' },
  { id: 'USDJPY#', label: 'USD/JPY' },
  { id: 'AUDUSD#', label: 'AUD/USD' },
  { id: 'USDCAD#', label: 'USD/CAD' },
  { id: 'USDCHF#', label: 'USD/CHF' },
  { id: 'NZDUSD#', label: 'NZD/USD' },
  { id: 'EURGBP#', label: 'EUR/GBP' },
  { id: 'GBPJPY#', label: 'GBP/JPY' },
];

const HyperOptimizer = ({ wsConnected, wsMessage }) => {
  const [config, setConfig] = useState({
    symbol: 'GOLD.i#',
    start_date: '2025-05-01',
    end_date: '2025-05-07',
    timeframe: 'M15',
    capital: 10000,
    sl_min: 0.5, sl_max: 2.0, sl_step: 0.5,
    tp_min: 1.0, tp_max: 4.0, tp_step: 1.0
  });

  const [isRunning, setIsRunning] = useState(false);
  const [taskId, setTaskId] = useState(null);
  const [progress, setProgress] = useState(null);
  const [results, setResults] = useState(null);

  useEffect(() => {
    if (!wsMessage) return;
    const data = wsMessage;
    
    // Auto-reconnect to running task if we lost the ID due to a page refresh
    if (data.type === 'optimize_progress') {
      if (!taskId || data.task_id === taskId) {
        if (!taskId) setTaskId(data.task_id); // Adopt task
        setProgress(data.progress);
        setIsRunning(true);
      }
    } else if (data.type === 'optimize_complete' && (!taskId || data.task_id === taskId)) {
      setIsRunning(false);
      setResults(data.result);
      setProgress({ pct_complete: 100, message: 'Optimization Complete' });
    }
  }, [wsMessage, taskId]);

  // Load last flight record on mount
  useEffect(() => {
    const loadLastResult = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/last-flight-records`);
        const data = await res.json();
        if (data && data.optimizer && !results && !isRunning) {
          setResults(data.optimizer);
          setProgress({ pct_complete: 100, message: 'Loaded from Flight Records' });
        }
      } catch (e) {
        console.error("Failed to load last flight records:", e);
      }
    };
    loadLastResult();
  }, []);

  const handleStart = async () => {
    setIsRunning(true);
    setResults(null);
    setProgress({ pct_complete: 0, message: 'Initiating...' });
    
    try {
      const res = await fetch(`${API_BASE}/api/mt5-optimize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: config.symbol,
          start_date: config.start_date,
          end_date: config.end_date,
          timeframe: config.timeframe,
          capital: config.capital,
          sl_range: { min: config.sl_min, max: config.sl_max, step: config.sl_step },
          tp_range: { min: config.tp_min, max: config.tp_max, step: config.tp_step }
        })
      });
      const data = await res.json();
      if (data.success) {
        setTaskId(data.task_id);
      } else {
        setIsRunning(false);
        setProgress({ message: `Error: ${data.error}`, pct_complete: 0 });
      }
    } catch (err) {
      setIsRunning(false);
      setProgress({ message: 'Network error.', pct_complete: 0 });
    }
  };

  const handleStop = async () => {
    if (!taskId) return;
    try {
      await fetch(`${API_BASE}/api/mt5-optimize/stop/${taskId}`, { method: 'POST' });
      setProgress(prev => ({ ...prev, message: 'Stopping...' }));
    } catch (e) {
      console.error(e);
    }
  };

  const updateConfig = (key, val) => setConfig(prev => ({ ...prev, [key]: val }));
  const updateNum = (key, val) => setConfig(prev => ({ ...prev, [key]: parseFloat(val) || 0 }));

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      <div className="flex items-center space-x-4 mb-8">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-[0_0_20px_rgba(99,102,241,0.4)]">
          <Settings className="w-6 h-6 text-white" />
        </div>
        <div>
          <h2 className="text-3xl font-black font-heading text-white tracking-tight">Hyper-Optimizer</h2>
          <p className="text-slate-400 font-medium">Grid Search SMC Parameters</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Configuration Panel */}
        <div className="lg:col-span-4 space-y-6">
          <div className="glass-card rounded-[2rem] p-6 shadow-2xl relative overflow-hidden border border-white/5">
            <h3 className="text-xl font-bold text-white mb-6 flex items-center gap-2">
              <Activity className="w-5 h-5 text-cyan-400" /> Backtest Target
            </h3>
            <div className="space-y-4">
              <div>
                <label className="text-xs text-slate-400 uppercase tracking-widest font-bold mb-1 block">Symbol</label>
                <select 
                  value={config.symbol} 
                  onChange={e => updateConfig('symbol', e.target.value)}
                  className="w-full bg-[#0a0a0a] border border-white/10 rounded-xl px-4 py-2.5 text-white font-mono focus:outline-none focus:border-cyan-500" 
                >
                  {MACRO_ASSETS.map(asset => (
                    <option key={asset.id} value={asset.id}>{asset.label}</option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-slate-400 uppercase tracking-widest font-bold mb-1 block">Start Date</label>
                  <input type="date" value={config.start_date} onChange={e => updateConfig('start_date', e.target.value)} className="w-full bg-[#0a0a0a] border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm" />
                </div>
                <div>
                  <label className="text-xs text-slate-400 uppercase tracking-widest font-bold mb-1 block">End Date</label>
                  <input type="date" value={config.end_date} onChange={e => updateConfig('end_date', e.target.value)} className="w-full bg-[#0a0a0a] border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-slate-400 uppercase tracking-widest font-bold mb-1 block">Timeframe</label>
                  <select value={config.timeframe} onChange={e => updateConfig('timeframe', e.target.value)} className="w-full bg-[#0a0a0a] border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm">
                    <option value="M5">M5</option>
                    <option value="M15">M15</option>
                    <option value="H1">H1</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-slate-400 uppercase tracking-widest font-bold mb-1 block">Capital</label>
                  <input type="number" value={config.capital} onChange={e => updateNum('capital', e.target.value)} className="w-full bg-[#0a0a0a] border border-white/10 rounded-xl px-4 py-2.5 text-white font-mono" />
                </div>
              </div>
            </div>
          </div>

          <div className="glass-card rounded-[2rem] p-6 shadow-2xl relative overflow-hidden border border-white/5">
            <h3 className="text-xl font-bold text-white mb-6 flex items-center gap-2">
              <Settings className="w-5 h-5 text-indigo-400" /> Grid Parameters
            </h3>
            
            <div className="space-y-6">
              {/* SL Range */}
              <div className="p-4 bg-slate-900/50 rounded-2xl border border-white/5">
                <h4 className="text-sm font-bold text-slate-300 mb-3">Stop Loss (%)</h4>
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">Min</label>
                    <input type="number" step="0.1" value={config.sl_min} onChange={e => updateNum('sl_min', e.target.value)} className="w-full bg-black border border-white/10 rounded-lg px-3 py-1.5 text-white text-sm" />
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">Max</label>
                    <input type="number" step="0.1" value={config.sl_max} onChange={e => updateNum('sl_max', e.target.value)} className="w-full bg-black border border-white/10 rounded-lg px-3 py-1.5 text-white text-sm" />
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">Step</label>
                    <input type="number" step="0.1" value={config.sl_step} onChange={e => updateNum('sl_step', e.target.value)} className="w-full bg-black border border-white/10 rounded-lg px-3 py-1.5 text-white text-sm" />
                  </div>
                </div>
              </div>

              {/* TP Range */}
              <div className="p-4 bg-slate-900/50 rounded-2xl border border-white/5">
                <h4 className="text-sm font-bold text-slate-300 mb-3">Take Profit (%)</h4>
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">Min</label>
                    <input type="number" step="0.1" value={config.tp_min} onChange={e => updateNum('tp_min', e.target.value)} className="w-full bg-black border border-white/10 rounded-lg px-3 py-1.5 text-white text-sm" />
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">Max</label>
                    <input type="number" step="0.1" value={config.tp_max} onChange={e => updateNum('tp_max', e.target.value)} className="w-full bg-black border border-white/10 rounded-lg px-3 py-1.5 text-white text-sm" />
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">Step</label>
                    <input type="number" step="0.1" value={config.tp_step} onChange={e => updateNum('tp_step', e.target.value)} className="w-full bg-black border border-white/10 rounded-lg px-3 py-1.5 text-white text-sm" />
                  </div>
                </div>
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={handleStart}
                disabled={isRunning || !wsConnected}
                className={`flex-1 py-4 rounded-xl font-bold flex items-center justify-center gap-2 transition-all shadow-lg
                  ${(isRunning || !wsConnected) 
                    ? 'bg-slate-800 text-slate-500 cursor-not-allowed' 
                    : 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white hover:from-cyan-400 hover:to-blue-500 shadow-cyan-500/25'}`}
              >
                {isRunning ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5" />}
                {isRunning ? 'OPTIMIZING...' : 'START GRID SEARCH'}
              </button>
              
              {isRunning && (
                <button
                  onClick={handleStop}
                  className="w-24 py-4 rounded-xl font-bold flex items-center justify-center bg-rose-500/10 text-rose-500 hover:bg-rose-500 hover:text-white transition-all border border-rose-500/50 shadow-lg shadow-rose-500/20"
                >
                  STOP
                </button>
              )}
            </div>
            {!wsConnected && <p className="text-xs text-pink-400 text-center mt-2">WebSocket disconnected.</p>}
          </div>
        </div>

        {/* Results & Progress Area */}
        <div className="lg:col-span-8 flex flex-col gap-6">
          
          {/* Progress Bar */}
          {progress && (
            <div className="glass-card rounded-[2rem] p-6 border border-white/5">
               <div className="flex justify-between items-end mb-2">
                 <span className="text-sm font-bold text-cyan-400">{progress.message}</span>
                 <span className="text-xs font-mono text-slate-400">{progress.pct_complete}%</span>
               </div>
               <div className="h-2 w-full bg-black rounded-full overflow-hidden">
                 <div 
                   className="h-full bg-gradient-to-r from-cyan-400 to-indigo-500 transition-all duration-300"
                   style={{ width: `${progress.pct_complete || 0}%` }}
                 />
               </div>
            </div>
          )}

          {/* Results Table */}
          <div className="glass-card rounded-[2.5rem] p-8 flex-1 border border-white/5">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xl font-bold text-white flex items-center gap-2">
                <BarChart2 className="w-6 h-6 text-purple-400" />
                Top Parameter Combinations
              </h3>
              {results && results.total_combinations_tested && (
                <span className="text-sm text-slate-400 bg-slate-800/50 px-3 py-1 rounded-full border border-white/10">
                  {results.total_combinations_tested} permutations tested
                </span>
              )}
            </div>

            {results && results.top_results ? (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="text-left text-xs font-bold text-slate-400 uppercase tracking-widest border-b border-white/10">
                      <th className="pb-3 pl-4">Rank</th>
                      <th className="pb-3 text-cyan-400">SL %</th>
                      <th className="pb-3 text-cyan-400">TP %</th>
                      <th className="pb-3">Trades</th>
                      <th className="pb-3">Win Rate</th>
                      <th className="pb-3">Profit Factor</th>
                      <th className="pb-3 text-right pr-4">Total PnL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.top_results.map((r, i) => (
                      <tr key={i} className="border-b border-white/5 hover:bg-white/5 transition-colors group">
                        <td className="py-4 pl-4 text-sm font-bold text-slate-500">#{i + 1}</td>
                        <td className="py-4 font-mono text-cyan-300">{r.sl_pct.toFixed(2)}%</td>
                        <td className="py-4 font-mono text-cyan-300">{r.tp_pct.toFixed(2)}%</td>
                        <td className="py-4 text-slate-300 font-mono">{r.total_trades}</td>
                        <td className="py-4 text-slate-300 font-mono">{r.win_rate.toFixed(1)}%</td>
                        <td className="py-4 text-emerald-400 font-bold font-mono">
                          {r.profit_factor >= 999.0 ? "∞" : r.profit_factor.toFixed(2)}
                        </td>
                        <td className={`py-4 text-right pr-4 font-bold font-mono ${r.total_pnl >= 0 ? 'text-emerald-400' : 'text-pink-400'}`}>
                          ${r.total_pnl.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}
                        </td>
                      </tr>
                    ))}
                    {results.top_results.length === 0 && (
                      <tr>
                        <td colSpan="7" className="py-8 text-center text-slate-500 text-sm">No valid trades executed in any configuration.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="h-48 flex flex-col items-center justify-center text-slate-600">
                <Zap className="w-12 h-12 mb-3 opacity-20" />
                <p>Run grid search to generate heatmap rankings.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default HyperOptimizer;
