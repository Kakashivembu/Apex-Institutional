import React from 'react';
import { ScrollText, TrendingUp, TrendingDown, Clock, Target, XCircle, ArrowRight } from 'lucide-react';

const BacktestLedger = ({ trades = [] }) => {
  if (!trades.length) return null;

  const pnlColor = (v) => v >= 0 ? 'text-emerald-400' : 'text-rose-400';
  const sideColor = (s) => s === 'LONG' ? 'text-emerald-400' : 'text-rose-400';
  const sideBg = (s) => s === 'LONG' ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-rose-500/10 border-rose-500/20';
  const reasonIcon = (r) => {
    if (r === 'TP') return <Target className="w-3 h-3 text-emerald-400" />;
    if (r === 'SL') return <XCircle className="w-3 h-3 text-rose-400" />;
    return <Clock className="w-3 h-3 text-slate-400" />;
  };

  return (
    <div className="glass-card p-6">
      <h4 className="text-sm font-semibold text-slate-400 uppercase mb-4 flex items-center space-x-2">
        <ScrollText className="w-4 h-4 text-amber-400" />
        <span>Trade Ledger — {trades.length} Simulated Trades</span>
      </h4>

      <div className="overflow-x-auto max-h-[500px] overflow-y-auto rounded-xl border border-white/5">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10">
            <tr className="bg-black/80 backdrop-blur text-slate-500 text-[10px] uppercase">
              <th className="px-3 py-2.5 text-left">#</th>
              <th className="px-3 py-2.5 text-left">Entry</th>
              <th className="px-3 py-2.5 text-left">Exit</th>
              <th className="px-3 py-2.5 text-center">Side</th>
              <th className="px-3 py-2.5 text-right">Entry $</th>
              <th className="px-3 py-2.5 text-right">Exit $</th>
              <th className="px-3 py-2.5 text-right">PnL</th>
              <th className="px-3 py-2.5 text-center">Reason</th>
              <th className="px-3 py-2.5 text-left">AI Reasoning</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => (
              <tr key={i} className="border-t border-white/5 hover:bg-white/[0.02] transition-colors">
                <td className="px-3 py-2.5 text-slate-600 font-mono text-xs">{i + 1}</td>
                <td className="px-3 py-2.5 text-slate-400 text-xs whitespace-nowrap">{t.entry_time}</td>
                <td className="px-3 py-2.5 text-slate-400 text-xs whitespace-nowrap">{t.exit_time}</td>
                <td className="px-3 py-2.5 text-center">
                  <span className={`inline-flex items-center space-x-1 px-2 py-0.5 rounded-lg border text-[10px] font-bold ${sideBg(t.side)}`}>
                    {t.side === 'LONG' ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                    <span className={sideColor(t.side)}>{t.side}</span>
                  </span>
                </td>
                <td className="px-3 py-2.5 text-right text-white font-mono text-xs">${t.entry_price?.toFixed(2)}</td>
                <td className="px-3 py-2.5 text-right text-white font-mono text-xs">${t.exit_price?.toFixed(2)}</td>
                <td className={`px-3 py-2.5 text-right font-bold font-mono text-xs ${pnlColor(t.pnl)}`}>
                  {t.pnl >= 0 ? '+' : ''}{t.pnl?.toFixed(2)} <span className="text-slate-600">({t.pnl_pct?.toFixed(2)}%)</span>
                </td>
                <td className="px-3 py-2.5 text-center">
                  <span className="inline-flex items-center space-x-1">{reasonIcon(t.exit_reason)}<span className="text-xs text-slate-400">{t.exit_reason}</span></span>
                </td>
                <td className="px-3 py-2.5 text-xs text-slate-500 max-w-[250px] truncate" title={t.reasoning}>{t.reasoning}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default BacktestLedger;
