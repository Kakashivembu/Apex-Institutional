import React, { useState, useRef, useEffect } from 'react';
import { Play, Loader2, TrendingUp, TrendingDown, AlertTriangle, Clock } from 'lucide-react';
import { API_BASE } from '../lib/api';
import BacktestLedger from './BacktestLedger';

const SYMBOLS = [
  'ALL_FLEET',
  // Metals
  'GOLD.i#', 'SILVER.i#', 'XAUEUR.i#', 'XAUJPY.i#', 'GAUUSD.i#',
  // Indices
  'US30Cash#', 'US100Cash#', 'US500Cash#', 'JP225Cash#', 'GER40Cash#',
  // Energy
  'OILCash#', 'BRENTCash#',
  // Crypto
  'BTCUSD#', 'ETHUSD#', 'BTCJPY#', 'XRPUSD#', 'ENJUSD#',
  // Forex Majors
  'EURUSD#', 'GBPUSD#', 'USDJPY#', 'AUDUSD#', 'USDCAD#', 'USDCHF#', 'NZDUSD#',
  // Forex Crosses
  'EURGBP#', 'GBPJPY#', 'EURJPY#', 'AUDCAD#', 'AUDJPY#', 'EURAUD#',
  'GBPCAD#', 'EURNZD#', 'EURCHF#', 'AUDNZD#', 'GBPAUD#', 'CHFJPY#',
  'EURCAD#', 'CADJPY#', 'NZDCAD#', 'NZDJPY#',
];
const TIMEFRAMES = [
  { value: 'H1', label: 'H1 (1 Hour)', maxDays: 90 },
  { value: 'M5', label: 'M5 (5 Minute)', maxDays: 30 },
  { value: 'M15', label: 'M15 (15 Minute)', maxDays: 60 },
];

const HistoricalBacktest = () => {
  const [symbol, setSymbol] = useState('GOLD.i#');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [timeframe, setTimeframe] = useState('H1');
  const [capital, setCapital] = useState(10000);
  const [taskId, setTaskId] = useState(null);
  const [status, setStatus] = useState('idle');
  const [progress, setProgress] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => {
    const now = new Date();
    const end = new Date(now); end.setDate(end.getDate() - 2);
    const start = new Date(end); start.setDate(start.getDate() - 5);
    setStartDate(start.toISOString().split('T')[0]);
    setEndDate(end.toISOString().split('T')[0]);

    // Load last flight record on mount
    const loadLastResult = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/last-flight-records`);
        const data = await res.json();
        if (data && data.backtest && !result && status === 'idle') {
          setResult(data.backtest);
          setStatus('complete');
        }
      } catch (e) {
        console.error("Failed to load last flight records:", e);
      }
    };
    loadLastResult();

    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const startBacktest = async () => {
    setStatus('starting'); setError(null); setResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/mt5-backtest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, start_date: startDate, end_date: endDate, timeframe, capital, step_interval: 0 }),
      });
      const data = await res.json();
      if (!data.success) { setError(data.error); setStatus('idle'); return; }
      setTaskId(data.task_id);
      setStatus('running');
      pollRef.current = setInterval(() => pollStatus(data.task_id), 2000);
    } catch (e) { setError(e.message); setStatus('idle'); }
  };

  const pollStatus = async (tid) => {
    try {
      const res = await fetch(`${API_BASE}/api/mt5-backtest/status/${tid}`);
      const data = await res.json();
      if (data.progress) setProgress(data.progress);
      if (data.status === 'complete') {
        clearInterval(pollRef.current); pollRef.current = null;
        setResult(data.result); setStatus('complete');
      } else if (data.status === 'error') {
        clearInterval(pollRef.current); pollRef.current = null;
        setError(data.error); setStatus('idle');
      }
    } catch (e) { console.error('Poll error:', e); }
  };

  const pnlColor = (v) => v >= 0 ? 'text-emerald-400' : 'text-rose-400';
  const summary = result?.summary || {};

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="glass-card p-6">
        <div className="flex items-center space-x-3 mb-6">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center shadow-lg shadow-amber-500/20">
            <TrendingUp className="w-5 h-5 text-white" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">MT5 Historical Backtest</h3>
            <p className="text-xs text-slate-500">Real candle data + AI Swarm consensus replay</p>
          </div>
        </div>

        {/* Input Form */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-4">
          <div>
            <label className="text-[10px] text-slate-500 uppercase mb-1 block">Symbol</label>
            <select value={symbol} onChange={e => setSymbol(e.target.value)} disabled={status === 'running'}
              className="w-full bg-black/50 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm focus:border-amber-500/50 outline-none">
              {SYMBOLS.map(s => <option key={s} value={s}>{s === 'ALL_FLEET' ? '🌍 All Assets (Fleet)' : s}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[10px] text-slate-500 uppercase mb-1 block">Start Date</label>
            <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} disabled={status === 'running'}
              className="w-full bg-black/50 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm focus:border-amber-500/50 outline-none" />
          </div>
          <div>
            <label className="text-[10px] text-slate-500 uppercase mb-1 block">End Date</label>
            <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} disabled={status === 'running'}
              className="w-full bg-black/50 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm focus:border-amber-500/50 outline-none" />
          </div>
          <div>
            <label className="text-[10px] text-slate-500 uppercase mb-1 block">Timeframe</label>
            <select value={timeframe} onChange={e => setTimeframe(e.target.value)} disabled={status === 'running'}
              className="w-full bg-black/50 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm focus:border-amber-500/50 outline-none">
              {TIMEFRAMES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[10px] text-slate-500 uppercase mb-1 block">Capital ($)</label>
            <input type="number" value={capital} onChange={e => setCapital(Number(e.target.value))} disabled={status === 'running'}
              className="w-full bg-black/50 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm focus:border-amber-500/50 outline-none" />
          </div>
        </div>

        {/* Run Button */}
        <button onClick={startBacktest} disabled={status === 'running' || status === 'starting'}
          className="w-full bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-400 hover:to-orange-500 text-white font-semibold py-3.5 rounded-xl transition-all flex items-center justify-center space-x-2 shadow-lg shadow-amber-500/20 disabled:opacity-50">
          {status === 'running' || status === 'starting' ? (
            <><Loader2 className="w-5 h-5 animate-spin" /><span>Running Simulation...</span></>
          ) : (
            <><Play className="w-5 h-5" /><span>Run Historical Simulation</span></>
          )}
        </button>

        {/* Error */}
        {error && (
          <div className="mt-4 p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-sm text-rose-400 flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" /><span>{error}</span>
          </div>
        )}

        {/* Progress */}
        {status === 'running' && progress && (
          <div className="mt-4 bg-gradient-to-r from-amber-500/10 to-orange-500/10 border border-amber-500/20 rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center space-x-2">
                <Loader2 className="w-4 h-4 text-amber-400 animate-spin" />
                <span className="text-sm text-white">{progress.current_time || 'Initializing...'}</span>
              </div>
              <span className="text-xs text-slate-400">
                {progress.evaluations_run || 0} evals • {progress.trades_so_far || 0} trades
              </span>
            </div>
            <div className="w-full h-2 bg-black/40 rounded-full">
              <div className="h-full bg-gradient-to-r from-amber-500 to-orange-500 rounded-full transition-all duration-500"
                style={{ width: `${progress.pct_complete || 0}%` }} />
            </div>
            <p className="text-xs text-slate-500 mt-1 text-right">{(progress.pct_complete || 0).toFixed(1)}%</p>
          </div>
        )}
      </div>

      {/* Results */}
      {status === 'complete' && result && (
        <>
          {/* Summary Stats */}
          <div className="glass-card p-6">
            <h4 className="text-sm font-semibold text-slate-400 uppercase mb-4 flex items-center space-x-2">
              <TrendingUp className="w-4 h-4 text-amber-400" />
              <span>Simulation Results — {result.symbol} {result.timeframe} • {result.start_date} → {result.end_date}</span>
            </h4>
            <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
              {[
                { label: 'Total PnL', value: `$${Math.abs(summary.total_pnl || 0).toFixed(2)}`, color: pnlColor(summary.total_pnl), prefix: summary.total_pnl >= 0 ? '+$' : '-$', raw: true },
                { label: 'Win Rate', value: `${summary.win_rate || 0}%`, color: (summary.win_rate || 0) >= 50 ? 'text-emerald-400' : 'text-rose-400' },
                { label: 'Trades', value: summary.total_trades || 0, color: 'text-white' },
                { label: 'Winners', value: summary.winners || 0, color: 'text-emerald-400' },
                { label: 'Losers', value: summary.losers || 0, color: 'text-rose-400' },
                { label: 'Profit Factor', value: `${summary.profit_factor || 0}x`, color: 'text-purple-400' },
                { label: 'Sharpe', value: summary.sharpe_ratio || 0, color: 'text-cyan-400' },
                { label: 'Max Drawdown', value: `${(summary.max_drawdown || 0).toFixed(2)}%`, color: 'text-rose-400' },
                { label: 'Avg Win', value: `$${(summary.avg_win || 0).toFixed(2)}`, color: 'text-emerald-400' },
                { label: 'Avg Loss', value: `$${(summary.avg_loss || 0).toFixed(2)}`, color: 'text-rose-400' },
                { label: 'Final Equity', value: `$${(summary.final_equity || 0).toLocaleString()}`, color: pnlColor((summary.final_equity || 0) - capital) },
                { label: 'Evaluations', value: result.evaluations_run || 0, color: 'text-slate-300' },
              ].map((s, i) => (
                <div key={i} className="bg-black/50 rounded-xl p-3">
                  <p className="text-[10px] text-slate-500 uppercase">{s.label}</p>
                  <p className={`text-lg font-bold ${s.color}`}>
                    {s.raw ? `${summary.total_pnl >= 0 ? '+' : '-'}$${Math.abs(summary.total_pnl || 0).toFixed(2)}` : s.value}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* Trade Ledger */}
          <BacktestLedger trades={result.ledger || []} />
        </>
      )}
    </div>
  );
};

export default HistoricalBacktest;
