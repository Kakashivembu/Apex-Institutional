import React, { useState, useEffect, useCallback } from 'react';
import {
  TrendingUp, Award, AlertTriangle, DollarSign, BarChart3,
  RefreshCw, Filter, ArrowUpRight, ArrowDownRight, Target,
  Clock, Zap, Shield, XCircle, Trash2
} from 'lucide-react';
import { API_BASE } from '../lib/api';

const USDT_TO_INR = 85;

const formatUsd = (value, digits = 2) => `$${Number(value || 0).toFixed(digits)}`;
const formatInr = (value, digits = 0) => `₹${(Number(value || 0) * USDT_TO_INR).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
const formatPrice = (value, symbol = '') => {
  const n = Number(value || 0);
  const s = String(symbol || '').toUpperCase();
  const digits = s.includes('JPY') ? 3 : s.includes('GOLD') || s.includes('XAU') ? 2 : 5;
  return `$${n.toFixed(digits)}`;
};

// ─── Mini SVG Charts ───────────────────────────────────────
const PnLChart = ({ data }) => {
  if (!data || data.length < 2) return (
    <div className="flex items-center justify-center h-full text-slate-600 text-sm font-medium">
      <p>Waiting for trade data...</p>
    </div>
  );

  const W = 700, H = 220, PAD = 40;
  const values = data.map(d => d.cumulative_pnl);
  const minV = Math.min(0, ...values);
  const maxV = Math.max(0.01, ...values);
  const range = maxV - minV || 1;

  const points = data.map((d, i) => {
    const x = PAD + (i / (data.length - 1)) * (W - PAD * 2);
    const y = H - PAD - ((d.cumulative_pnl - minV) / range) * (H - PAD * 2);
    return `${x},${y}`;
  }).join(' ');

  const zeroY = H - PAD - ((0 - minV) / range) * (H - PAD * 2);
  const lastVal = values[values.length - 1];
  const isPositive = lastVal >= 0;

  // Area fill
  const firstX = PAD;
  const lastX = PAD + ((data.length - 1) / (data.length - 1)) * (W - PAD * 2);
  const areaPath = `M ${firstX},${zeroY} L ${points.split(' ').map(p => p).join(' L ')} L ${lastX},${zeroY} Z`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-full">
      <defs>
        <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={isPositive ? '#2ecda7' : '#f70670'} stopOpacity="0.3" />
          <stop offset="100%" stopColor={isPositive ? '#2ecda7' : '#f70670'} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {/* Zero line */}
      <line x1={PAD} y1={zeroY} x2={W - PAD} y2={zeroY} stroke="rgba(255,255,255,0.1)" strokeDasharray="4,4" />
      <text x={PAD - 5} y={zeroY + 4} textAnchor="end" fill="#555" fontSize="10">$0</text>
      {/* Area */}
      <path d={areaPath} fill="url(#pnlGrad)" />
      {/* Line */}
      <polyline points={points} fill="none" stroke={isPositive ? '#2ecda7' : '#f70670'} strokeWidth="2.5" strokeLinejoin="round" />
      {/* Dots for each trade */}
      {data.map((d, i) => {
        const x = PAD + (i / (data.length - 1)) * (W - PAD * 2);
        const y = H - PAD - ((d.cumulative_pnl - minV) / range) * (H - PAD * 2);
        const color = d.pnl >= 0 ? '#2ecda7' : '#f70670';
        return <circle key={i} cx={x} cy={y} r="3" fill={color} opacity="0.8" />;
      })}
      {/* Labels */}
      <text x={PAD - 5} y={PAD + 4} textAnchor="end" fill="#555" fontSize="10">${maxV.toFixed(2)}</text>
      <text x={PAD - 5} y={H - PAD + 14} textAnchor="end" fill="#555" fontSize="10">${minV.toFixed(2)}</text>
      {/* End value */}
      {data.length > 0 && (() => {
        const lx = PAD + ((data.length - 1) / (data.length - 1)) * (W - PAD * 2);
        const ly = H - PAD - ((lastVal - minV) / range) * (H - PAD * 2);
        return (
          <text x={lx + 8} y={ly + 4} fill={isPositive ? '#2ecda7' : '#f70670'} fontSize="11" fontWeight="bold">
            ${lastVal.toFixed(2)}
          </text>
        );
      })()}
    </svg>
  );
};

const DonutChart = ({ data }) => {
  const entries = Object.entries(data || {});
  if (entries.length === 0) return (
    <div className="flex items-center justify-center h-full text-slate-600 text-sm">No data</div>
  );

  const total = entries.reduce((s, [, v]) => s + v, 0);
  const colors = { tp: '#2ecda7', sl: '#f70670', step_trail: '#fbbf24', manual: '#888888', unknown: '#555555' };
  const labels = { tp: 'Take Profit', sl: 'Stop Loss', step_trail: 'Step Trail', manual: 'Manual', unknown: 'Unknown' };
  const CX = 80, CY = 80, R = 60, r = 40;

  let startAngle = -90;
  const arcs = entries.map(([reason, count]) => {
    const pct = count / total;
    const angle = pct * 360;
    const endAngle = startAngle + angle;
    const large = angle > 180 ? 1 : 0;
    const toRad = a => (a * Math.PI) / 180;
    const x1o = CX + R * Math.cos(toRad(startAngle));
    const y1o = CY + R * Math.sin(toRad(startAngle));
    const x2o = CX + R * Math.cos(toRad(endAngle));
    const y2o = CY + R * Math.sin(toRad(endAngle));
    const x1i = CX + r * Math.cos(toRad(endAngle));
    const y1i = CY + r * Math.sin(toRad(endAngle));
    const x2i = CX + r * Math.cos(toRad(startAngle));
    const y2i = CY + r * Math.sin(toRad(startAngle));
    const path = `M ${x1o} ${y1o} A ${R} ${R} 0 ${large} 1 ${x2o} ${y2o} L ${x1i} ${y1i} A ${r} ${r} 0 ${large} 0 ${x2i} ${y2i} Z`;
    startAngle = endAngle;
    return { reason, count, pct, path, color: colors[reason] || '#555' };
  });

  return (
    <div className="flex items-center gap-6">
      <svg viewBox="0 0 160 160" className="w-36 h-36 flex-shrink-0">
        {arcs.map((a, i) => (
          <path key={i} d={a.path} fill={a.color} opacity="0.85" className="hover:opacity-100 transition-opacity" />
        ))}
        <text x={CX} y={CY - 4} textAnchor="middle" fill="white" fontSize="18" fontWeight="900">{total}</text>
        <text x={CX} y={CY + 12} textAnchor="middle" fill="#888" fontSize="9">TRADES</text>
      </svg>
      <div className="space-y-2">
        {arcs.map((a, i) => (
          <div key={i} className="flex items-center gap-2 text-xs">
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: a.color }} />
            <span className="text-slate-400 w-20">{labels[a.reason] || a.reason}</span>
            <span className="text-white font-bold">{a.count}</span>
            <span className="text-slate-600">({(a.pct * 100).toFixed(0)}%)</span>
          </div>
        ))}
      </div>
    </div>
  );
};

// ─── Close Reason Badge ───────────────────────────────────
const ReasonBadge = ({ reason }) => {
  const cfg = {
    tp: { label: 'TP', color: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30', icon: Target },
    sl: { label: 'SL', color: 'bg-pink-500/20 text-pink-400 border-pink-500/30', icon: XCircle },
    step_trail: { label: 'TRAIL', color: 'bg-amber-500/20 text-amber-400 border-amber-500/30', icon: TrendingUp },
    manual: { label: 'MANUAL', color: 'bg-slate-500/20 text-slate-400 border-slate-500/30', icon: Shield },
  };
  const c = cfg[reason] || cfg.manual;
  const Icon = c.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-black tracking-widest border ${c.color}`}>
      <Icon className="w-3 h-3" />
      {c.label}
    </span>
  );
};

// ─── Main Component ───────────────────────────────────────
const BotPerformance = () => {
  const [stats, setStats] = useState(null);
  const [trades, setTrades] = useState([]);
  const [chartData, setChartData] = useState([]);
  const [accountFilter, setAccountFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [resetting, setResetting] = useState(false);

  const fetchData = useCallback(async () => {
    setRefreshing(true);
    const q = accountFilter ? `?account=${encodeURIComponent(accountFilter)}` : '';
    try {
      const [statsRes, tradesRes, chartRes] = await Promise.all([
        fetch(`${API_BASE}/api/bot-performance${q}`).then(r => r.json()),
        fetch(`${API_BASE}/api/bot-performance/trades${q}`).then(r => r.json()),
        fetch(`${API_BASE}/api/bot-performance/chart${q}`).then(r => r.json()),
      ]);
      if (statsRes.success) setStats(statsRes);
      if (tradesRes.success) setTrades(tradesRes.trades || []);
      if (chartRes.success) setChartData(chartRes.chart || []);
    } catch (e) {
      console.error('[BOT-PERF] Fetch error:', e);
    }
    setLoading(false);
    setRefreshing(false);
  }, [accountFilter]);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => { const iv = setInterval(fetchData, 5000); return () => clearInterval(iv); }, [fetchData]);

  const accounts = stats?.accounts || [];
  const accountTabs = [
    { account_name: '', label: 'Fleet Total', open_trades_count: stats?.open_trades || 0 },
    ...accounts.map(acct => ({
      account_name: acct.account_name,
      label: acct.account_name,
      open_trades_count: acct.open_trades_count || 0,
    })),
  ];

  if (loading) return (
    <div className="flex items-center justify-center h-96">
      <div className="text-center">
        <RefreshCw className="w-8 h-8 text-pink-500 animate-spin mx-auto mb-3" />
        <p className="text-slate-500 font-bold text-sm">Loading Bot Performance...</p>
      </div>
    </div>
  );

  const s = stats || {};
  const totalTrades = (s.total_trades || 0) + (s.open_trades || 0);

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      {/* Header */}
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-4xl font-black font-heading text-white tracking-tight">Bot Performance</h1>
          <p className="text-sm text-slate-500 mt-1 font-medium">
            Lifetime trade analytics — {s.source === 'xm_mt5_history' ? 'synced from local XMGlobal MT5 history' : 'SQLite fallback'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Reset Stats */}
          <button
            id="reset-trade-history-btn"
            onClick={async () => {
              if (!window.confirm(
                'Are you sure you want to permanently delete all trade history?\n\nThis will purge every recorded trade from the database.\nYour API keys and configuration will NOT be affected.\n\nThis cannot be undone.'
              )) return;
              setResetting(true);
              try {
                const q = accountFilter ? `?account=${encodeURIComponent(accountFilter)}` : '';
                const res = await fetch(`${API_BASE}/api/bot-performance/reset${q}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) {
                  await fetchData();
                } else {
                  alert(`Reset failed: ${data.error}`);
                }
              } catch (e) {
                alert(`Reset error: ${e.message}`);
              }
              setResetting(false);
            }}
            disabled={resetting}
            className="p-2.5 rounded-xl bg-red-500/10 hover:bg-red-500/25 transition-colors border border-red-500/20 hover:border-red-500/40 group"
            title={accountFilter ? `Reset trades for ${accountFilter}` : 'Reset all trade history'}
          >
            <Trash2 className={`w-4 h-4 text-red-400 group-hover:text-red-300 ${resetting ? 'animate-pulse' : ''}`} />
          </button>
          <button
            onClick={fetchData}
            disabled={refreshing}
            className="p-2.5 rounded-xl bg-white/5 hover:bg-white/10 transition-colors border border-white/5"
          >
            <RefreshCw className={`w-4 h-4 text-slate-400 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="glass-card rounded-[1.5rem] p-3">
        <div className="flex flex-wrap gap-2">
          {accountTabs.map((tab) => {
            const isActive = accountFilter === tab.account_name;
            return (
              <button
                key={tab.account_name || 'fleet-total'}
                onClick={() => setAccountFilter(tab.account_name)}
                className={`px-4 py-2 rounded-2xl border text-sm font-bold transition-all ${
                  isActive
                    ? 'bg-pink-500/20 border-pink-500/40 text-pink-300 shadow-lg shadow-pink-500/10'
                    : 'bg-white/[0.02] border-white/10 text-slate-400 hover:text-white hover:bg-white/[0.05]'
                }`}
              >
                <span>{tab.label}</span>
                {tab.open_trades_count > 0 ? (
                  <span className={`ml-2 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] ${isActive ? 'bg-pink-500/20 text-pink-200' : 'bg-emerald-500/15 text-emerald-400'}`}>
                    {tab.open_trades_count} live
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        {[
          { label: 'Total Trades', value: totalTrades, sub: `${s.open_positions || s.open_trades || 0} open`, icon: BarChart3, color: 'from-indigo-500 to-purple-600' },
          { label: 'Win Rate', value: `${Number(s.win_rate || 0).toFixed(1)}%`, sub: `${s.winners || 0}W / ${s.losers || 0}L`, icon: Award,
            color: (s.win_rate || 0) >= 50 ? 'from-emerald-500 to-emerald-700' : 'from-pink-500 to-pink-700' },
          { label: 'Net P&L', value: formatUsd(s.net_pnl, 2), sub: `${formatInr(s.net_pnl)} • All XM realized history`, icon: DollarSign,
            color: (s.net_pnl || 0) >= 0 ? 'from-emerald-500 to-emerald-700' : 'from-pink-500 to-pink-700' },
          { label: "Today's Trades", value: s.today_trades || 0, sub: `${s.today_winners || 0}W / ${(s.today_trades || 0) - (s.today_winners || 0)}L today`, icon: Clock,
            color: 'from-cyan-500 to-blue-600' },
          { label: "Today's P&L", value: formatUsd(s.today_pnl, 2), sub: `${formatInr(s.today_pnl)} • Live MT5`, icon: Zap,
            color: (s.today_pnl || 0) >= 0 ? 'from-emerald-500 to-teal-600' : 'from-pink-500 to-red-600' },
          { label: 'Profit Factor', value: s.profit_factor != null ? (s.profit_factor >= 999 ? '∞' : s.profit_factor.toFixed(2)) : '—', sub: `Fees: ${formatUsd(s.total_fees, 4)}`, icon: Shield,
            color: (s.profit_factor || 0) >= 1.5 ? 'from-emerald-500 to-emerald-700' : (s.profit_factor || 0) >= 1 ? 'from-amber-500 to-orange-600' : 'from-pink-500 to-pink-700' },
        ].map((card, i) => {
          const Icon = card.icon;
          return (
            <div key={i} className="glass-card rounded-[2rem] p-6 relative overflow-hidden group">
              <div className={`absolute top-0 right-0 w-24 h-24 bg-gradient-to-br ${card.color} opacity-10 rounded-full blur-2xl transform translate-x-6 -translate-y-6 group-hover:opacity-20 transition-opacity`} />
              <div className="flex items-center gap-3 mb-4 relative z-10">
                <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${card.color} flex items-center justify-center shadow-lg`}>
                  <Icon className="w-5 h-5 text-white" />
                </div>
                <span className="text-[10px] text-slate-500 uppercase tracking-[0.15em] font-bold">{card.label}</span>
              </div>
              <p className="text-3xl font-black font-heading text-white relative z-10">{card.value}</p>
              <p className="text-xs text-slate-500 mt-1 font-medium relative z-10">{card.sub}</p>
            </div>
          );
        })}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-12 gap-6">
        {/* PnL Chart */}
        <div className="col-span-12 lg:col-span-8 glass-card rounded-[2rem] p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-pink-500 to-pink-700 flex items-center justify-center shadow-lg shadow-pink-500/25">
                <TrendingUp className="w-5 h-5 text-white" />
              </div>
              <div>
                <h3 className="text-lg font-black font-heading text-white">Cumulative P&L</h3>
                <p className="text-[10px] text-slate-600 uppercase tracking-wider font-medium">Trade-by-trade equity curve</p>
              </div>
            </div>
            {chartData.length > 0 && (
              <div className={`text-xl font-black font-heading ${(chartData[chartData.length-1]?.cumulative_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-pink-500'}`}>
                {(chartData[chartData.length-1]?.cumulative_pnl || 0) >= 0 ? '+' : ''}${(chartData[chartData.length-1]?.cumulative_pnl || 0).toFixed(2)}
                <span className="block text-[10px] text-slate-500 font-medium">
                  {formatInr(chartData[chartData.length-1]?.cumulative_pnl || 0)}
                </span>
              </div>
            )}
          </div>
          <div className="h-[220px]">
            <PnLChart data={chartData} />
          </div>
        </div>

        {/* Close Reason Donut */}
        <div className="col-span-12 lg:col-span-4 glass-card rounded-[2rem] p-6">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center shadow-lg shadow-amber-500/25">
              <Target className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="text-lg font-black font-heading text-white">Close Reasons</h3>
              <p className="text-[10px] text-slate-600 uppercase tracking-wider font-medium">How trades were closed</p>
            </div>
          </div>
          <DonutChart data={s.close_reasons} />
        </div>
      </div>

      {/* Extra Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Avg Win', value: formatUsd(s.avg_win, 4), inr: formatInr(s.avg_win), positive: true },
          { label: 'Avg Loss', value: formatUsd(s.avg_loss, 4), inr: formatInr(s.avg_loss), positive: false },
          { label: 'Best Trade', value: formatUsd(s.best_trade, 4), inr: formatInr(s.best_trade), positive: true },
          { label: 'Worst Trade', value: formatUsd(s.worst_trade, 4), inr: formatInr(s.worst_trade), positive: false },
        ].map((item, i) => (
          <div key={i} className="bg-white/[0.02] border border-white/5 rounded-2xl p-4">
            <p className="text-[10px] text-slate-600 uppercase tracking-widest font-bold mb-1">{item.label}</p>
            <p className={`text-lg font-black font-heading ${item.positive ? 'text-emerald-400' : 'text-pink-500'}`}>{item.value}</p>
            <p className="text-[10px] text-slate-500 mt-1">{item.inr}</p>
          </div>
        ))}
      </div>

      {/* Per-Account Breakdown */}
      {accounts.length > 0 && (
        <div className="glass-card rounded-[2rem] p-6">
          <h3 className="text-lg font-black font-heading text-white mb-4">Account Breakdown</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {accounts.map((acct, i) => (
              <div key={i} className="bg-white/[0.02] border border-white/5 rounded-2xl p-5 hover:bg-white/[0.04] transition-colors">
                <div className="flex items-center justify-between mb-3">
                  <span className="font-black font-heading text-white text-base">{acct.account_name}</span>
                  <span className={`text-sm font-bold ${acct.pnl >= 0 ? 'text-emerald-400' : 'text-pink-500'}`}>
                    {acct.pnl >= 0 ? '+' : ''}{formatUsd(acct.pnl, 4)}
                    <span className="block text-[10px] text-slate-500 text-right">{formatInr(acct.pnl)}</span>
                  </span>
                </div>
                <div className="flex justify-between text-xs text-slate-500">
                  <span>{acct.trades} trades</span>
                  <span>WR: {Number(acct.win_rate || 0).toFixed(1)}%</span>
                  <span>Fees: {formatUsd(acct.fees, 4)} / {formatInr(acct.fees)}</span>
                </div>
                {acct.today_trades > 0 && (
                  <div className="flex items-center gap-3 text-xs text-cyan-400 font-bold mt-1">
                    <span>Today: {acct.today_trades} trades</span>
                    <span className={Number(acct.today_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-pink-400'}>{formatUsd(acct.today_pnl, 2)}</span>
                  </div>
                )}
                {/* Win rate bar */}
                <div className="mt-3 w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${acct.win_rate >= 50 ? 'bg-emerald-500' : 'bg-pink-500'}`}
                    style={{ width: `${acct.win_rate}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Trade History Table */}
      <div className="glass-card rounded-[2rem] p-8">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/25">
              <Clock className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="text-lg font-black font-heading text-white">Trade History</h3>
              <p className="text-[10px] text-slate-600 uppercase tracking-wider font-medium">{trades.length} trades recorded</p>
            </div>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-[10px] text-slate-600 uppercase tracking-widest border-b border-white/10">
                <th className="pb-3 font-bold">#</th>
                <th className="pb-3 font-bold">Account</th>
                <th className="pb-3 font-bold">Symbol</th>
                <th className="pb-3 font-bold">Side</th>
                <th className="pb-3 font-bold">Entry</th>
                <th className="pb-3 font-bold">Exit</th>
                <th className="pb-3 font-bold">Contracts</th>
                <th className="pb-3 font-bold">P&L</th>
                <th className="pb-3 font-bold">Fees</th>
                <th className="pb-3 font-bold">Closed By</th>
                <th className="pb-3 font-bold">Status</th>
                <th className="pb-3 font-bold">AI Reasoning</th>
                <th className="pb-3 font-bold">Date</th>
              </tr>
            </thead>
            <tbody>
              {trades.length === 0 ? (
                <tr>
                  <td colSpan={13} className="py-16 text-center">
                    <Zap className="w-10 h-10 text-slate-700 mx-auto mb-3" />
                    <p className="text-slate-600 font-bold text-sm">No trades recorded yet.</p>
                    <p className="text-slate-700 text-xs mt-1">Trades will appear here as the bot executes.</p>
                  </td>
                </tr>
              ) : trades.map((t) => {
                const isWin = t.pnl > 0;
                const isClosed = t.status === 'closed';
                const entryDate = t.entry_time ? new Date(t.entry_time) : null;
                const exitDate = t.exit_time ? new Date(t.exit_time) : null;
                let duration = '—';
                if (entryDate && exitDate) {
                  const diffMs = exitDate - entryDate;
                  const diffMins = Math.floor(diffMs / 60000);
                  if (diffMins < 60) duration = `${diffMins}m`;
                  else if (diffMins < 1440) duration = `${Math.floor(diffMins / 60)}h ${diffMins % 60}m`;
                  else duration = `${Math.floor(diffMins / 1440)}d`;
                }
                return (
                  <tr key={t.id} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                    <td className="py-4 text-xs text-slate-600 font-mono">{t.id}</td>
                    <td className="py-4">
                      <span className="text-xs font-bold text-white bg-white/5 px-2 py-1 rounded-lg">{t.account_name}</span>
                    </td>
                    <td className="py-4 text-sm font-bold text-white font-mono">{t.symbol}</td>
                    <td className="py-4">
                      <span className={`px-2 py-0.5 rounded-lg text-[10px] font-black tracking-widest ${
                        t.side === 'LONG' || t.side === 'BUY' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-pink-500/15 text-pink-400'
                      }`}>
                        {t.side}
                      </span>
                    </td>
                    <td className="py-4 text-sm text-white font-mono">{formatPrice(t.entry_price, t.symbol)}</td>
                    <td className="py-4 text-sm text-slate-400 font-mono">{isClosed ? formatPrice(t.exit_price, t.symbol) : '—'}</td>
                    <td className="py-4 text-sm text-white font-mono">{t.contracts}</td>
                    <td className={`py-4 text-sm font-black font-heading ${isClosed ? (isWin ? 'text-emerald-400' : 'text-pink-500') : 'text-slate-500'}`}>
                      {isClosed ? (
                        <>
                          {isWin ? '+' : ''}{formatUsd(t.pnl, 2)}
                          <span className="block text-[10px] text-slate-500 font-medium">{formatInr(t.pnl)}</span>
                        </>
                      ) : '—'}
                    </td>
                    <td className="py-4 text-xs text-slate-500 font-mono">
                      {formatUsd(t.fees, 4)}
                      <span className="block text-[10px] text-slate-600 font-medium">{formatInr(t.fees)}</span>
                    </td>
                    <td className="py-4">
                      {isClosed ? <ReasonBadge reason={t.close_reason} /> : <span className="text-[10px] text-slate-600">—</span>}
                    </td>
                    <td className="py-4">
                      {isClosed ? (
                        <span className="text-[10px] text-slate-600 font-bold">CLOSED • {duration}</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400 font-bold">
                          <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />
                          OPEN
                        </span>
                      )}
                    </td>
                    <td className="py-4 max-w-[200px]">
                      <p className="text-[10px] text-slate-400 truncate" title={t.ai_reasoning || ''}>
                        {t.ai_reasoning ? (t.ai_reasoning.length > 60 ? t.ai_reasoning.slice(0, 60) + '…' : t.ai_reasoning) : '—'}
                      </p>
                    </td>
                    <td className="py-4 text-[10px] text-slate-600 font-mono">
                      {entryDate ? entryDate.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' }) : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default BotPerformance;
