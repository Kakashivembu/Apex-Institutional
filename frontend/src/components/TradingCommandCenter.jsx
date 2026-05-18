import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { 
  Cpu, Wifi, Zap, TrendingUp, Layers, Globe, 
  Gauge, Search, RefreshCw, Activity, Shield,
  ArrowUpRight, ArrowDownRight, Target, Copy, Loader2, LineChart, ActivitySquare,
  CheckCircle2, XCircle, Clock
} from 'lucide-react';
import { AdvancedRealTimeChart } from 'react-ts-tradingview-widgets';
import { API_BASE } from '../lib/api';

const USDT_TO_INR = 85;

// ═══════════════════════════════════════════════════════════════════════════
// FOREX SESSION ENGINE — Live Asia / London / New York detection (UTC-based)
// ═══════════════════════════════════════════════════════════════════════════
const FOREX_SESSIONS = [
  { id: 'asia',    label: 'Asia',     emoji: '🌏', open: 0,  close: 9,  color: 'purple', gradient: 'from-purple-500 to-indigo-600',  glow: 'rgba(168,85,247,0.6)',  bg: 'purple-500' },
  { id: 'london',  label: 'London',   emoji: '🇬🇧', open: 7,  close: 16, color: 'cyan',   gradient: 'from-cyan-500 to-blue-600',     glow: 'rgba(6,182,212,0.6)',   bg: 'cyan-500'   },
  { id: 'newyork', label: 'New York', emoji: '🇺🇸', open: 13, close: 22, color: 'amber',  gradient: 'from-amber-500 to-orange-600',  glow: 'rgba(245,158,11,0.6)', bg: 'amber-500'  },
];

const getActiveSessions = () => {
  const now = new Date();
  const utcH = now.getUTCHours();
  const utcM = now.getUTCMinutes();
  const utcDecimal = utcH + utcM / 60;

  const active = FOREX_SESSIONS.filter(s => {
    if (s.open < s.close) return utcDecimal >= s.open && utcDecimal < s.close;
    return utcDecimal >= s.open || utcDecimal < s.close; // wraps midnight
  });

  // Find next session opening
  let nextSession = null;
  let minMinutes = Infinity;
  for (const s of FOREX_SESSIONS) {
    if (active.find(a => a.id === s.id)) continue;
    let diff = (s.open * 60) - (utcH * 60 + utcM);
    if (diff <= 0) diff += 24 * 60;
    if (diff < minMinutes) {
      minMinutes = diff;
      nextSession = s;
    }
  }

  // Compute progress & time remaining for each active session
  const enriched = active.map(s => {
    const duration = (s.close > s.open ? s.close - s.open : 24 - s.open + s.close) * 60;
    let elapsed = (utcH * 60 + utcM) - s.open * 60;
    if (elapsed < 0) elapsed += 24 * 60;
    const remaining = duration - elapsed;
    const progress = Math.min(100, (elapsed / duration) * 100);
    const remH = Math.floor(remaining / 60);
    const remM = remaining % 60;
    return { ...s, progress, remainingStr: `${remH}h ${remM}m`, remainingMin: remaining };
  });

  const nextH = nextSession ? Math.floor(minMinutes / 60) : 0;
  const nextM = nextSession ? minMinutes % 60 : 0;

  return {
    active: enriched,
    nextSession,
    nextIn: nextSession ? `${nextH}h ${nextM}m` : null,
    utcTime: `${String(utcH).padStart(2,'0')}:${String(utcM).padStart(2,'0')}`,
    isOffMarket: enriched.length === 0,
  };
};


const AnimatedPrice = ({ value, prefix = "$", className = "" }) => {
  const [displayValue, setDisplayValue] = useState(value);
  const [trend, setTrend] = useState(null);
  
  useEffect(() => {
    if (!value || value === displayValue) return;
    setTrend(value > displayValue ? 'up' : 'down');
    
    let startValue = displayValue;
    let endValue = value;
    let startTime = null;
    const duration = 500;
    
    const animate = (currentTime) => {
      if (!startTime) startTime = currentTime;
      const progress = Math.min((currentTime - startTime) / duration, 1);
      const easeProgress = progress * (2 - progress);
      setDisplayValue(startValue + (endValue - startValue) * easeProgress);
      
      if (progress < 1) requestAnimationFrame(animate);
      else setTimeout(() => setTrend(null), 500);
    };
    requestAnimationFrame(animate);
  }, [value]);
  
  return (
    <span className={`${className} transition-colors duration-300 ${trend === 'up' ? 'text-emerald-400 drop-shadow-[0_0_10px_rgba(52,211,153,0.8)]' : trend === 'down' ? 'text-pink-500 drop-shadow-[0_0_10px_rgba(247,6,112,0.8)]' : ''}`}>
      {prefix}{displayValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 5 })}
    </span>
  );
};

const MACRO_ASSETS = [
  { id: 'GOLD.i#', symbol: 'OANDA:XAUUSD', label: 'Gold (XAUUSD)' },
  { id: 'SILVER.i#', symbol: 'OANDA:XAGUSD', label: 'Silver (XAGUSD)' },
  { id: 'US30Cash#', symbol: 'FOREXCOM:DJI', label: 'US30 (Dow)' },
  { id: 'EURUSD#', symbol: 'OANDA:EURUSD', label: 'EUR/USD' },
  { id: 'GBPUSD#', symbol: 'OANDA:GBPUSD', label: 'GBP/USD' },
  { id: 'USDJPY#', symbol: 'OANDA:USDJPY', label: 'USD/JPY' },
  { id: 'AUDUSD#', symbol: 'OANDA:AUDUSD', label: 'AUD/USD' },
  { id: 'USDCAD#', symbol: 'OANDA:USDCAD', label: 'USD/CAD' },
  { id: 'USDCHF#', symbol: 'OANDA:USDCHF', label: 'USD/CHF' },
  { id: 'NZDUSD#', symbol: 'OANDA:NZDUSD', label: 'NZD/USD' },
  { id: 'EURGBP#', symbol: 'OANDA:EURGBP', label: 'EUR/GBP' },
  { id: 'GBPJPY#', symbol: 'OANDA:GBPJPY', label: 'GBP/JPY' },
];

const tvSymbolMap = { 
  "GOLD.i#": "OANDA:XAUUSD", 
  "GOLD#": "OANDA:XAUUSD",
  "XAUUSD#": "OANDA:XAUUSD",
  "XAUUSD.i#": "OANDA:XAUUSD",
  "XAUUSD": "OANDA:XAUUSD",
  "GOLD": "OANDA:XAUUSD",
  "SILVER.i#": "OANDA:XAGUSD",
  "SILVER#": "OANDA:XAGUSD",
  "XAGUSD#": "OANDA:XAGUSD",
  "XAGUSD.i#": "OANDA:XAGUSD",
  "XAGUSD": "OANDA:XAGUSD",
  "SILVER": "OANDA:XAGUSD",
  "EURUSD#": "OANDA:EURUSD",
  "EURUSD.i#": "OANDA:EURUSD", 
  "EURUSD": "OANDA:EURUSD",
  "GBPUSD#": "OANDA:GBPUSD",
  "GBPUSD.i#": "OANDA:GBPUSD",
  "GBPUSD": "OANDA:GBPUSD",
  "USDJPY#": "OANDA:USDJPY",
  "USDJPY.i#": "OANDA:USDJPY",
  "USDJPY": "OANDA:USDJPY",
  "US30Cash#": "FOREXCOM:DJI",
  "US30.i#": "FOREXCOM:DJI",
  "US30#": "FOREXCOM:DJI",
  "US30": "FOREXCOM:DJI",
  "AUDUSD#": "OANDA:AUDUSD",
  "AUDUSD.i#": "OANDA:AUDUSD",
  "AUDUSD": "OANDA:AUDUSD",
  "NZDUSD#": "OANDA:NZDUSD",
  "NZDUSD.i#": "OANDA:NZDUSD",
  "NZDUSD": "OANDA:NZDUSD",
  "USDCAD#": "OANDA:USDCAD",
  "USDCAD.i#": "OANDA:USDCAD",
  "USDCAD": "OANDA:USDCAD",
  "EURGBP#": "OANDA:EURGBP",
  "EURGBP.i#": "OANDA:EURGBP",
  "EURGBP": "OANDA:EURGBP",
  "USDCHF#": "OANDA:USDCHF",
  "USDCHF.i#": "OANDA:USDCHF",
  "USDCHF": "OANDA:USDCHF",
  "GBPJPY#": "OANDA:GBPJPY",
  "GBPJPY.i#": "OANDA:GBPJPY",
  "GBPJPY": "OANDA:GBPJPY",
};

const normalizeBrokerSymbol = (symbol = '') => {
  const clean = String(symbol).trim().toUpperCase();
  if (!clean) return '';
  if (clean.includes('GOLD')) return 'GOLD';
  return clean.replace(/\.I#$/i, '').replace(/#$/g, '').replace(/\.I$/i, '');
};

const getTradingViewSymbol = (symbol, fallback = 'OANDA:XAUUSD') => {
  const raw = String(symbol || '').trim();
  const normalized = normalizeBrokerSymbol(raw);
  if (!raw) return fallback;
  if (tvSymbolMap[raw]) return tvSymbolMap[raw];
  if (tvSymbolMap[normalized]) return tvSymbolMap[normalized];
  if (/^[A-Z]{6}$/.test(normalized)) return `OANDA:${normalized}`;
  return fallback;
};

const TradingCommandCenter = ({ marketData, wsConnected, refreshData, inrRate = 84.5 }) => {
  const [localMarketData, setLocalMarketData] = useState(marketData);
  const [networkInfo, setNetworkInfo] = useState(null);
  const [copyStatus, setCopyStatus] = useState({ local: '', remote: '' });
  const [activeChartAsset, setActiveChartAsset] = useState(MACRO_ASSETS[0]);
  const [closingProfitable, setClosingProfitable] = useState(false);
  const [closeProfitableResult, setCloseProfitableResult] = useState(null);
  const [sessionData, setSessionData] = useState(() => getActiveSessions());
  
  useEffect(() => { setLocalMarketData(marketData); }, [marketData]);

  // Tick the session clock every 15 seconds
  useEffect(() => {
    const tick = () => setSessionData(getActiveSessions());
    const id = setInterval(tick, 15000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const radarSymbol = localMarketData.active_symbol;
    if (!radarSymbol) return;
    const normalizedRadarSymbol = normalizeBrokerSymbol(radarSymbol);
    const mapped = MACRO_ASSETS.find((a) => a.id === radarSymbol || normalizeBrokerSymbol(a.id) === normalizedRadarSymbol);
    if (mapped && mapped.id !== activeChartAsset.id) {
      setActiveChartAsset(mapped);
    }
  }, [localMarketData.active_symbol, activeChartAsset.id]);

  useEffect(() => {
    let cancelled = false;
    const loadNetworkInfo = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/network-info`);
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled) setNetworkInfo(data);
      } catch {}
    };
    loadNetworkInfo();
    const interval = setInterval(loadNetworkInfo, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const setCopyFeedback = (key, value) => {
    setCopyStatus(prev => ({ ...prev, [key]: value }));
    setTimeout(() => {
      setCopyStatus(prev => ({ ...prev, [key]: '' }));
    }, 2000);
  };

  const positions = localMarketData.positions || [];
  const agentDecisions = localMarketData.swarm_decisions || [];
  const equity = localMarketData.equity || { total: 0, daily_pnl: 0, daily_change_pct: 0 };
  const consensus = localMarketData.consensus || { direction: 'HOLD', strength: 0 };
  const assetMarketData = localMarketData.market_data || { last_price: 0, price_change_pct: 0, volume: 0, high_price: 0, low_price: 0 };
  const margin = localMarketData.margin || { available_margin: 0, total_balance: 0, used_margin: 0, unrealized_pnl: 0, currency: 'USD' };
  const stepTrail = localMarketData.step_trail || {};
  
  // Live Macro Matrix data from WebSocket (Currency Matrix + Tick Velocity sensors)
  const macroMatrix = localMarketData.macro_matrix || {};
  const matrixStrongest = macroMatrix.strongest || '—';
  const matrixWeakest = macroMatrix.weakest || '—';
  const matrixVelocity = macroMatrix.tick_velocity || '—';
  const velocityHigh = macroMatrix.velocity_high || false;
  const velocityRatio = macroMatrix.velocity_ratio || 0;
  const matrixScores = macroMatrix.scores || {};

  const uniqueActiveSymbols = useMemo(() => {
    const active = positions.filter(p => p.status === 'active');
    return [...new Set(active.map(p => p.symbol))];
  }, [positions]);

  const getDecisionColor = (d) => {
    if (d === 'BUY' || d === 'BULLISH' || d === 'LONG') return 'text-emerald-400 bg-emerald-400/10';
    if (d === 'SELL' || d === 'BEARISH' || d === 'SHORT') return 'text-pink-400 bg-pink-400/10';
    return 'text-slate-400 bg-slate-400/10';
  };

  const getConsensusColor = () => {
    const dir = consensus.direction;
    if (dir === 'BUY' || dir === 'LONG') return 'from-emerald-400 to-emerald-600';
    if (dir === 'SELL' || dir === 'SHORT') return 'from-pink-500 to-pink-700';
    return 'from-slate-400 to-slate-600';
  };

  const getPositionSL = (pos) => {
    const key = `${pos.account}:${pos.ticket || pos.symbol}`;
    const trail = stepTrail[key];
    if (trail && trail.sl > 0) return trail.sl;
    if (pos.sl > 0) return pos.sl;
    return null;
  };

  const getPositionTP = (pos) => {
    const key = `${pos.account}:${pos.ticket || pos.symbol}`;
    const trail = stepTrail[key];
    if (trail && trail.tp > 0) return trail.tp;
    if (pos.tp > 0) return pos.tp;
    return null;
  };

  const getPositionTrailTier = (pos) => {
    const key = `${pos.account}:${pos.ticket || pos.symbol}`;
    const trail = stepTrail[key];
    if (trail) return trail.tier || 0;
    return pos.trail_tier || 0;
  };

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      
      {/* Massive Header Section */}
      <div className="flex flex-col xl:flex-row xl:items-end justify-between gap-6 mb-2 min-w-0">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3 mb-2">
            <select 
              value={activeChartAsset.id}
              onChange={(e) => setActiveChartAsset(MACRO_ASSETS.find(a => a.id === e.target.value))}
              className="max-w-full text-2xl font-black font-heading text-white tracking-tight bg-transparent border-b-2 border-white/20 focus:outline-none focus:border-cyan-400 cursor-pointer pb-1"
            >
              {MACRO_ASSETS.map(asset => (
                <option key={asset.id} value={asset.id} className="bg-slate-900 text-sm font-sans">{asset.label}</option>
              ))}
            </select>
            <span className="px-3 py-1 bg-cyan-500/20 text-cyan-400 text-xs rounded-full border border-cyan-500/30 uppercase font-bold tracking-widest">
              MT5 Macro
            </span>
            {/* Live Session Badge(s) */}
            {sessionData.active.length > 0 ? sessionData.active.map(s => (
              <span
                key={s.id}
                className={`px-3 py-1 text-xs rounded-full border font-black uppercase tracking-widest animate-pulse`}
                style={{
                  background: `linear-gradient(135deg, ${s.glow.replace('0.6','0.15')}, transparent)`,
                  borderColor: s.glow.replace('0.6','0.35'),
                  color: s.glow.replace('0.6','1'),
                  boxShadow: `0 0 12px ${s.glow}`,
                }}
              >
                {s.emoji} {s.label}
              </span>
            )) : (
              <span className="px-3 py-1 bg-slate-700/30 text-slate-500 text-xs rounded-full border border-slate-600/30 uppercase font-bold tracking-widest">
                💤 Off-Market
              </span>
            )}
            {/* FIX #1: Show when AI radar overrides the manual selection */}
            {localMarketData.active_symbol && normalizeBrokerSymbol(localMarketData.active_symbol) !== normalizeBrokerSymbol(activeChartAsset.id) && (
              <span className="px-2 py-0.5 bg-pink-500/15 text-pink-400 text-[10px] rounded-full border border-pink-500/30 font-bold uppercase tracking-widest animate-pulse">
                AI Override
              </span>
            )}
          </div>
          <div className="mb-3">
            <span className="inline-flex items-center px-4 py-1.5 rounded-full bg-amber-500/15 border border-amber-400/30 text-amber-300 text-xs font-black uppercase tracking-widest">
              AI Radar Target: {localMarketData.active_symbol || activeChartAsset.id}
            </span>
          </div>
          <div className="flex flex-wrap items-end gap-4 sm:gap-6 min-w-0">
            <h1 className="text-5xl sm:text-6xl md:text-7xl font-black font-heading tracking-tighter text-white break-words">
              <AnimatedPrice value={assetMarketData.last_price || 0} />
            </h1>
            <div className={`flex items-center space-x-2 text-xl sm:text-2xl font-bold font-heading ${assetMarketData.price_change_pct >= 0 ? 'text-emerald-400' : 'text-pink-500'}`}>
              {assetMarketData.price_change_pct >= 0 ? <ArrowUpRight className="w-8 h-8" /> : <ArrowDownRight className="w-8 h-8" />}
              <span>{assetMarketData.price_change_pct >= 0 ? '+' : ''}{(assetMarketData.price_change_pct || 0).toFixed(2)}%</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 2xl:grid-cols-5 gap-4 w-full xl:w-auto xl:max-w-[1200px]">
          <div className="glass-card px-6 py-4 rounded-3xl min-w-0">
            <p className="text-xs text-slate-400 uppercase tracking-widest mb-1 font-bold">Network Access</p>
            <div className="space-y-3">
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider font-bold mb-1">🏠 Local Access</p>
                {networkInfo?.mobile_access_url ? (
                  <button
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(networkInfo.mobile_access_url);
                        setCopyFeedback('local', 'Copied');
                      } catch {
                        setCopyFeedback('local', 'Copy failed');
                      }
                    }}
                    className="flex items-center gap-2 min-w-0 text-left text-white hover:text-cyan-300 transition-colors"
                    title="Copy local access URL"
                  >
                    <span className="min-w-0 text-sm font-mono break-all">{networkInfo.mobile_access_url}</span>
                    <Copy className="w-4 h-4 shrink-0" />
                  </button>
                ) : (
                  <p className="text-sm text-slate-500">Unavailable</p>
                )}
                <p className="text-[10px] text-slate-500 mt-1">{copyStatus.local || 'Open this URL on your phone while both devices share a network.'}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider font-bold mb-1">🌍 Remote Access</p>
                {networkInfo?.tunnel_url ? (
                  <button
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(networkInfo.tunnel_url);
                        setCopyFeedback('remote', 'Copied');
                      } catch {
                        setCopyFeedback('remote', 'Copy failed');
                      }
                    }}
                    className="flex items-center gap-2 min-w-0 text-left text-white hover:text-cyan-300 transition-colors"
                    title="Copy remote access URL"
                  >
                    <span className="min-w-0 text-sm font-mono break-all">{networkInfo.tunnel_url}</span>
                    <Copy className="w-4 h-4 shrink-0" />
                  </button>
                ) : (
                  <div className="flex items-center gap-2 text-slate-400">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span className="text-sm">Generating tunnel URL...</span>
                  </div>
                )}
                <p className="text-[10px] text-slate-500 mt-1">{copyStatus.remote || 'Share this URL to access the dashboard remotely.'}</p>
              </div>
            </div>
          </div>
          <div className="glass-card px-6 py-4 rounded-3xl min-w-0">
             <div className="flex items-center justify-between mb-2">
               <p className="text-xs text-slate-400 uppercase tracking-widest font-bold">Macro Matrix</p>
               <div className="flex items-center gap-1.5">
                 <div className={`w-1.5 h-1.5 rounded-full ${matrixStrongest !== '—' ? 'bg-emerald-400 animate-pulse shadow-[0_0_6px_rgba(52,211,153,0.8)]' : 'bg-slate-600'}`} />
                 <span className="text-[9px] text-slate-500 uppercase tracking-widest font-bold">{matrixStrongest !== '—' ? 'LIVE' : 'WAITING'}</span>
               </div>
             </div>
             <div className="space-y-1.5 mt-2">
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-500">Strongest:</span>
                  <span className="font-black text-emerald-400 text-sm tracking-wider">{matrixStrongest}</span>
                </div>
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-500">Weakest:</span>
                  <span className="font-black text-pink-400 text-sm tracking-wider">{matrixWeakest}</span>
                </div>
                <div className="flex justify-between items-center text-xs pt-1.5 border-t border-white/5">
                  <span className="text-slate-500">Velocity:</span>
                  <span className={`font-black text-sm ${velocityHigh ? 'text-pink-400 animate-pulse' : 'text-cyan-400'}`}>{matrixVelocity}</span>
                </div>
                {/* Mini Currency Strength Bars */}
                {Object.keys(matrixScores).length > 0 && (
                  <div className="pt-2 border-t border-white/5 space-y-1">
                    {Object.entries(matrixScores).sort(([,a],[,b]) => b - a).map(([currency, score]) => (
                      <div key={currency} className="flex items-center gap-2 text-[10px]">
                        <span className="text-slate-500 w-7 font-bold">{currency}</span>
                        <div className="flex-1 h-1 bg-white/5 rounded-full overflow-hidden">
                          <div 
                            className={`h-full rounded-full transition-all duration-700 ${
                              currency === matrixStrongest ? 'bg-emerald-400 shadow-[0_0_4px_rgba(52,211,153,0.5)]' 
                              : currency === matrixWeakest ? 'bg-pink-400 shadow-[0_0_4px_rgba(244,114,182,0.5)]' 
                              : 'bg-slate-500/60'
                            }`}
                            style={{ width: `${Math.max(2, score)}%` }}
                          />
                        </div>
                        <span className="text-slate-600 w-8 text-right font-mono">{score.toFixed(0)}</span>
                      </div>
                    ))}
                  </div>
                )}
             </div>
          </div>
          <div className="glass-card px-6 py-4 rounded-3xl min-w-0">
            <p className="text-xs text-slate-400 uppercase tracking-widest mb-1 font-bold">Total P&L</p>
            <p className={`text-2xl font-black font-heading ${equity.daily_pnl >= 0 ? 'text-emerald-400' : 'text-pink-500'}`}>
              {equity.daily_pnl >= 0 ? '+' : ''}${equity.daily_pnl?.toLocaleString() || '0'}
            </p>
            <p className={`text-xs ${equity.daily_pnl >= 0 ? 'text-emerald-600' : 'text-pink-600'}`}>
              ₹{((equity.daily_pnl || 0) * inrRate).toLocaleString(undefined, {maximumFractionDigits: 0})}
            </p>
          </div>
          {/* ── SESSION CLOCK WIDGET ── */}
          <div className="glass-card px-6 py-4 rounded-3xl min-w-0 relative overflow-hidden">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs text-slate-400 uppercase tracking-widest font-bold">Session Clock</p>
              <div className="flex items-center gap-1.5">
                <Clock className="w-3 h-3 text-slate-500" />
                <span className="text-[10px] text-slate-400 font-mono font-bold">{sessionData.utcTime} UTC</span>
              </div>
            </div>
            {sessionData.active.length > 0 ? (
              <div className="space-y-2.5">
                {sessionData.active.map(s => (
                  <div key={s.id}>
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-xs font-black text-white">{s.emoji} {s.label}</span>
                      <span className="text-[10px] text-slate-500 font-mono font-bold">{s.remainingStr} left</span>
                    </div>
                    <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full bg-gradient-to-r ${s.gradient} transition-all duration-1000`}
                        style={{ width: `${s.progress}%`, boxShadow: `0 0 8px ${s.glow}` }}
                      />
                    </div>
                  </div>
                ))}
                {/* Overlap indicator */}
                {sessionData.active.length >= 2 && (
                  <div className="flex items-center gap-1.5 pt-1 border-t border-white/5">
                    <div className="w-1.5 h-1.5 bg-amber-400 rounded-full animate-pulse" />
                    <span className="text-[9px] text-amber-400 font-black uppercase tracking-widest">
                      {sessionData.active.map(s => s.label).join(' + ')} Overlap — High Volatility
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-1">
                <p className="text-lg font-black font-heading text-slate-600">💤 Off-Market</p>
                {sessionData.nextSession && (
                  <p className="text-[10px] text-slate-500 mt-1">
                    Next: <span className="text-white font-bold">{sessionData.nextSession.emoji} {sessionData.nextSession.label}</span> in <span className="text-cyan-400 font-bold">{sessionData.nextIn}</span>
                  </p>
                )}
              </div>
            )}
          </div>
          {/* ── BOT PERFORMANCE WIDGET ── */}
          <div className="glass-card px-6 py-4 rounded-3xl min-w-0">
            <div className="flex items-center justify-between mb-1">
              <p className="text-xs text-slate-400 uppercase tracking-widest font-bold">Bot Performance</p>
              <span className="text-[9px] text-slate-600 uppercase tracking-wider font-bold">{marketData?.bot_performance?.total_trades || 0} trades</span>
            </div>
            <div className="flex items-baseline gap-3">
              <p className={`text-2xl font-black font-heading ${(marketData?.bot_performance?.win_rate || 0) >= 50 ? 'text-emerald-400' : 'text-pink-500'}`}>
                {Number(marketData?.bot_performance?.win_rate || 0).toFixed(1)}%
              </p>
              <span className="text-[10px] text-slate-500 font-bold uppercase">Win Rate</span>
            </div>
            <div className="mt-1">
              <p className={`text-sm font-bold font-heading ${(marketData?.bot_performance?.net_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-pink-500'}`}>
                {(marketData?.bot_performance?.net_pnl || 0) >= 0 ? '+' : ''}${Number(marketData?.bot_performance?.net_pnl || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
              <p className="text-[10px] text-slate-600">Closed Net P&L</p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 lg:gap-8">
        
        {/* Main Chart Area */}
        <div className="col-span-12 lg:col-span-8 glass-card rounded-[2.5rem] p-4 overflow-hidden shadow-2xl relative">
          <div className="h-[600px] w-full rounded-3xl overflow-hidden bg-[#050505]">
            <AdvancedRealTimeChart 
              key={`main-chart-${getTradingViewSymbol(localMarketData.active_symbol, activeChartAsset.symbol || "OANDA:XAUUSD")}`}
              theme="dark" 
              symbol={getTradingViewSymbol(localMarketData.active_symbol, activeChartAsset.symbol || "OANDA:XAUUSD")}
              autosize
              interval="15"
              timezone="Etc/UTC"
              style="1"
              locale="en"
              enable_publishing={false}
              hide_top_toolbar={false}
              hide_legend={false}
              save_image={false}
              enabled_features={[
                'use_localstorage_for_settings',
                'save_chart_properties_to_local_storage',
              ]}
              container_id={`main_chart_${activeChartAsset.id.replace(/[^a-zA-Z0-9]/g, '')}`}
            />
          </div>
        </div>

        {/* AI Consensus - Dramatic Panel */}
        <div className="col-span-12 lg:col-span-4 flex flex-col gap-6">
          <div className="glass-card rounded-[2.5rem] p-8 relative overflow-hidden bg-gradient-to-br from-indigo-600/10 to-black/60 border border-indigo-500/20 shadow-[0_0_50px_rgba(99,102,241,0.1)] flex-1 flex flex-col">
            
            <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500/20 rounded-full blur-[80px] pointer-events-none transform translate-x-1/2 -translate-y-1/2" />
            
            <div className="flex items-center justify-between mb-8 relative z-10">
              <div className="flex items-center space-x-3">
                <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-700 flex items-center justify-center shadow-[0_0_20px_rgba(99,102,241,0.4)]">
                  <Cpu className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h3 className="text-2xl font-black font-heading text-white">AI Consensus</h3>
                  {wsConnected && (
                    <div className="flex items-center space-x-2 mt-1">
                      <div className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse shadow-[0_0_10px_rgba(99,102,241,0.8)]" />
                      <span className="text-xs text-indigo-400 font-bold uppercase tracking-widest">Global Macro Engine</span>
                    </div>
                  )}
                </div>
              </div>
              <button 
                onClick={async (e) => {
                  const btn = e.currentTarget;
                  const originalText = btn.innerText;
                  btn.innerText = "Waking...";
                  btn.disabled = true;
                  try {
                    await fetch(`${API_BASE}/api/wake_agents`, { method: 'POST' });
                  } finally {
                    setTimeout(() => {
                      btn.innerText = originalText;
                      btn.disabled = false;
                    }, 2000);
                  }
                }}
                className="px-4 py-2 bg-cyan-600/20 hover:bg-cyan-600/40 border border-cyan-500/50 text-cyan-400 text-[10px] font-black uppercase tracking-widest rounded-xl transition-all shadow-[0_0_15px_rgba(6,182,212,0.2)] whitespace-nowrap"
              >
                ⚡ WAKE AGENTS
              </button>
            </div>

            <div className="mb-10 relative z-10 flex flex-col items-center justify-center py-6 bg-black/40 rounded-3xl border border-white/5">
              <span className="text-sm text-slate-400 uppercase tracking-[0.2em] mb-2 font-bold">Direction</span>
              <span className={`text-5xl font-black font-heading tracking-tighter ${
                  consensus.status === 'SLEEPING' ? 'text-cyan-500/50 text-3xl drop-shadow-[0_0_15px_rgba(6,182,212,0.3)]'
                  : consensus.direction === 'BUY' || consensus.direction === 'LONG' ? 'text-emerald-400 drop-shadow-[0_0_15px_rgba(52,211,153,0.5)]' 
                  : consensus.direction === 'SELL' || consensus.direction === 'SHORT' ? 'text-pink-500 drop-shadow-[0_0_15px_rgba(247,6,112,0.5)]'
                  : 'text-slate-300'
                }`}>
                {consensus.status === 'SLEEPING' ? '[ MONITOR MODE - SLEEPING ]' : (consensus.direction || 'HOLD')}
              </span>
              
              <div className="w-full px-8 mt-6">
                <div className="flex justify-between mb-2">
                  <span className="text-xs text-slate-400 font-bold uppercase tracking-wider">Strength</span>
                  <span className="text-sm font-black font-heading text-white">{consensus.strength || 0}%</span>
                </div>
                <div className="w-full h-3 bg-black/80 rounded-full overflow-hidden border border-white/10">
                  <div 
                    className={`h-full bg-gradient-to-r ${getConsensusColor()} rounded-full transition-all duration-1000 shadow-[0_0_10px_currentColor]`} 
                    style={{ width: `${consensus.strength || 0}%` }}
                  />
                </div>
              </div>
            </div>

            <div className={`space-y-3 relative z-10 flex-1 overflow-y-auto pr-2 custom-scrollbar ${consensus.status === 'SLEEPING' ? 'opacity-30 pointer-events-none grayscale' : ''}`}>
              {agentDecisions.map((agent, index) => (
                <div key={agent.id || index} className="bg-white/[0.02] border border-white/5 rounded-2xl p-4 hover:bg-white/[0.04] transition-colors">
                  <div className="flex justify-between items-center mb-2">
                    <p className="font-black font-heading text-white text-lg">{agent.name || agent.agent}</p>
                    <span className={`font-bold text-xs px-3 py-1 rounded-xl ${getDecisionColor(agent.decision)}`}>
                      {agent.decision}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">{agent.signal || agent.details || '—'}</p>
                  <div className="mt-3 text-right">
                    <span className="text-xs text-slate-500 font-bold">Confidence: <span className="text-white">{agent.confidence}%</span></span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Active Positions Chart Grid */}
      {uniqueActiveSymbols.length > 0 && (
        <div className="glass-card rounded-[2.5rem] p-8">
           <div className="flex items-center space-x-3 mb-6">
              <ActivitySquare className="w-6 h-6 text-cyan-400" />
              <h3 className="text-xl font-black font-heading text-white">Active Symbol Tracking Grid</h3>
           </div>
           <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {uniqueActiveSymbols.map(sym => {
                 let tvSymbol = getTradingViewSymbol(sym);
                 if(String(sym).includes('BTC')) tvSymbol = 'INDEX:BTCUSD';
                 
                 return (
                   <div key={sym} className="h-[250px] rounded-2xl overflow-hidden border border-white/10 bg-[#050505]">
                      <AdvancedRealTimeChart 
                        theme="dark" 
                        symbol={tvSymbol}
                        autosize
                        interval="15"
                        hide_top_toolbar
                        hide_legend
                        save_image={false}
                        container_id={`mini_chart_${sym.replace(/[^a-zA-Z0-9]/g, '')}`}
                      />
                   </div>
                 );
              })}
           </div>
        </div>
      )}

      {/* Fleet Positions - Full Width */}
      <div className="glass-card rounded-[2.5rem] p-8">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center space-x-4">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-[0_0_20px_rgba(99,102,241,0.4)]">
              <Globe className="w-6 h-6 text-white" />
            </div>
            <div>
              <h3 className="text-2xl font-black font-heading text-white">MT5 Positions Basket</h3>
              <p className="text-sm text-slate-400 font-bold uppercase tracking-wider">{positions.filter(p => p.status === 'active').length} Active Contracts</p>
            </div>
          </div>
          
          <div className="flex items-center gap-4">
            <div className="flex space-x-8 bg-black/40 px-6 py-3 rounded-2xl border border-white/5">
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-widest font-bold mb-1">Available Margin</p>
                <p className="text-xl font-black font-heading text-emerald-400">${margin.available_margin?.toLocaleString() || '0'}</p>
              </div>
              <div className="w-px bg-white/10" />
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-widest font-bold mb-1">Used Margin</p>
                <p className="text-xl font-black font-heading text-white">${margin.used_margin?.toLocaleString() || '0'}</p>
              </div>
            </div>
            
            {/* CLOSE ALL PROFITABLE BUTTON */}
            {(() => {
              const profitableCount = positions.filter(p => p.status === 'active' && Number(p.pnl || 0) >= 0).length;
              return (
                <div className="flex flex-col items-center gap-1">
                  <button
                    id="close-all-profitable-btn"
                    disabled={closingProfitable || profitableCount === 0}
                    onClick={async () => {
                      if (!window.confirm(`Close ALL ${profitableCount} profitable/breakeven positions?\n\nThis will immediately close every position with PnL ≥ $0.`)) return;
                      setClosingProfitable(true);
                      setCloseProfitableResult(null);
                      try {
                        const res = await fetch(`${API_BASE}/api/close-profitable`, {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ min_pnl: 0 })
                        });
                        const data = await res.json();
                        setCloseProfitableResult(data);
                        if (data.success && data.closed > 0) {
                          if (refreshData) refreshData();
                        }
                        setTimeout(() => setCloseProfitableResult(null), 8000);
                      } catch (err) {
                        setCloseProfitableResult({ success: false, error: err.message });
                        setTimeout(() => setCloseProfitableResult(null), 5000);
                      } finally {
                        setClosingProfitable(false);
                      }
                    }}
                    className={`group relative px-5 py-3 rounded-2xl text-xs font-black uppercase tracking-widest transition-all duration-300 border shadow-lg ${
                      closingProfitable
                        ? 'bg-amber-500/20 border-amber-500/40 text-amber-400 cursor-wait'
                        : profitableCount === 0
                        ? 'bg-slate-800/40 border-slate-700/30 text-slate-600 cursor-not-allowed'
                        : 'bg-emerald-500/15 border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/25 hover:shadow-[0_0_30px_rgba(52,211,153,0.3)] hover:-translate-y-0.5'
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      {closingProfitable ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <CheckCircle2 className="w-4 h-4" />
                      )}
                      {closingProfitable ? 'Closing...' : `Close All Profitable (${profitableCount})`}
                    </span>
                  </button>
                  {closeProfitableResult && (
                    <div className={`flex items-center gap-1.5 text-[10px] font-bold animate-fade-in ${
                      closeProfitableResult.success ? 'text-emerald-400' : 'text-pink-400'
                    }`}>
                      {closeProfitableResult.success ? (
                        <><CheckCircle2 className="w-3 h-3" /> {closeProfitableResult.message}</>
                      ) : (
                        <><XCircle className="w-3 h-3" /> {closeProfitableResult.error}</>
                      )}
                    </div>
                  )}
                </div>
              );
            })()}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-xs text-slate-500 uppercase tracking-widest border-b border-white/10">
                <th className="pb-4 font-bold">Symbol</th>
                <th className="pb-4 font-bold">Side</th>
                <th className="pb-4 font-bold">Qty</th>
                <th className="pb-4 font-bold">Entry</th>
                <th className="pb-4 font-bold">Mark</th>
                <th className="pb-4 font-bold">P&L</th>
                <th className="pb-4 font-bold">TP / SL</th>
                <th className="pb-4 font-bold">Trail</th>
                <th className="pb-4 font-bold">Action</th>
              </tr>
            </thead>
            <tbody>
              {positions.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-12 text-center">
                    <p className="text-slate-500 font-bold text-lg">No active MT5 positions across the fleet.</p>
                  </td>
                </tr>
              ) : positions.map((pos, index) => {
                const sl = getPositionSL(pos);
                const tp = getPositionTP(pos);
                const tier = getPositionTrailTier(pos);
                const side = pos.side?.toUpperCase() || (pos.qty < 0 ? 'SHORT' : 'LONG');
                const netPnl = Number(pos.pnl || 0); // No complex Delta fee estimation needed for MT5 Forex natively
                const grossUpnl = netPnl;
                
                const trapKey = `${pos.account}:${pos.ticket || pos.symbol}`;
                const trailKey = (marketData.step_trail || {})[trapKey]
                  ? trapKey
                  : Object.keys(marketData.step_trail || {}).find(k =>
                      k.includes(pos.symbol) && k.includes(pos.account)
                    );
                const trailState = trailKey ? (marketData.step_trail || {})[trailKey] : null;
                const trap = (marketData.ai_traps || {})[trapKey] || (marketData.ai_traps || {})[pos.symbol];
                
                const tierNames = { 0: 'INITIAL', 1: 'BREAKEVEN', 2: 'PROFIT STEP', 3: 'RUNNER TRAIL' };
                const tierColors = { 0: 'text-slate-500', 1: 'text-amber-400', 2: 'text-emerald-400', 3: 'text-cyan-400' };
                
                return (
                  <React.Fragment key={index}>
                    <tr className="border-b border-white/[0.05] hover:bg-white/[0.02] transition-colors group">
                      <td className="py-5">
                        <div className="flex items-center space-x-3">
                          <span className="font-black font-heading text-white text-lg">{pos.symbol}</span>
                          {pos.status === 'active' && <div className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse shadow-[0_0_10px_rgba(52,211,153,0.8)]" />}
                        </div>
                        <span className="text-xs text-slate-500 font-bold uppercase tracking-wider">{pos.account}</span>
                      </td>
                      <td className="py-5">
                        <span className={`px-3 py-1 rounded-xl text-xs font-black tracking-widest ${
                          side === 'SHORT' ? 'bg-pink-500/20 text-pink-500' : 'bg-emerald-500/20 text-emerald-400'
                        }`}>
                          {side}
                        </span>
                      </td>
                      <td className="py-5 text-base text-white font-mono font-bold">{Math.abs(pos.qty)}</td>
                      <td className="py-5 text-base text-white font-mono font-bold">${pos.entry?.toFixed(5) || '—'}</td>
                      <td className="py-5 text-base text-slate-300 font-mono">
                        <AnimatedPrice value={pos.current || assetMarketData.last_price || 0} />
                        <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse inline-block ml-1.5 align-middle" title="Live" />
                      </td>
                      <td className={`py-5 text-lg font-black font-heading ${netPnl >= 0 ? 'text-emerald-400' : 'text-pink-500'}`}>
                        {netPnl >= 0 ? '+' : ''}${netPnl.toFixed(2)}
                        <span className={`block text-[10px] font-medium ${netPnl >= 0 ? 'text-emerald-600' : 'text-pink-600'}`}>
                          ₹{(netPnl * (inrRate || USDT_TO_INR)).toLocaleString(undefined, {maximumFractionDigits: 0})}
                        </span>
                      </td>
                      <td className="py-5">
                        <div className="flex flex-col text-xs font-mono font-bold space-y-1">
                          <span className="text-emerald-400">TP: {tp ? `$${tp.toFixed(5)}` : '—'}</span>
                          <span className="text-pink-500">SL: {sl ? `$${sl.toFixed(5)}` : '—'}</span>
                        </div>
                      </td>
                      <td className="py-5">
                        {tier > 0 ? (
                          <span className={`px-3 py-1 text-xs font-black tracking-widest rounded-xl border ${
                            tier === 3 ? 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30'
                            : tier === 2 ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                            : 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                          }`}>
                            T{tier}
                          </span>
                        ) : (
                          <span className="text-slate-600 font-bold">—</span>
                        )}
                      </td>
                      <td className="py-5">
                        <button 
                          onClick={async () => {
                            if (!window.confirm(`Close ${side} ${pos.symbol} x${Math.abs(pos.qty)} on ${pos.account}?`)) return;
                            try {
                              const res = await fetch(`${API_BASE}/api/close-position`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ account: pos.account, symbol: pos.symbol, ticket: pos.ticket })
                              });
                              const data = await res.json();
                              if (data.success) {
                                alert(`Position closed: ${data.message}`);
                                if (refreshData) refreshData();
                              } else {
                                alert(`Close failed: ${data.error}`);
                              }
                            } catch (err) { alert(`Network error: ${err.message}`); }
                          }}
                          className="px-6 py-2 bg-pink-600 hover:bg-pink-500 text-white text-xs font-black uppercase tracking-widest rounded-xl transition-all opacity-0 group-hover:opacity-100 shadow-[0_0_15px_rgba(247,6,112,0.4)] hover:shadow-[0_0_25px_rgba(247,6,112,0.6)] transform hover:-translate-y-0.5"
                        >
                          Close
                        </button>
                      </td>
                    </tr>
                    
                    {(trailState || trap) && (
                      <tr className="border-b border-white/[0.03]">
                        <td colSpan={9} className="py-0 px-0">
                          <div className="mx-4 mb-3 rounded-2xl bg-black/40 border border-white/[0.06] p-4">
                            <div className="flex flex-wrap gap-6">
                              
                              {/* Step-Trail State */}
                              {trailState && (
                                <div className="flex-1 min-w-[280px]">
                                  <div className="flex items-center gap-2 mb-3">
                                    <div className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-pulse" />
                                    <span className="text-[10px] text-purple-400 uppercase tracking-[0.2em] font-black">Step-Trail Engine</span>
                                  </div>
                                  
                                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                    <div>
                                      <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-0.5">Tier</p>
                                      <p className={`text-sm font-black font-heading ${tierColors[trailState.tier] || 'text-slate-400'}`}>
                                        {tierNames[trailState.tier] || `T${trailState.tier}`}
                                      </p>
                                    </div>
                                    <div>
                                      <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-0.5">Active SL</p>
                                      <p className="text-sm font-black font-heading text-pink-400">${trailState.sl?.toFixed(5)}</p>
                                    </div>
                                    <div>
                                      <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-0.5">AI Target (10m)</p>
                                      <p className={`text-sm font-black font-heading ${trailState.ai_target ? 'text-amber-400' : 'text-slate-600'}`}>
                                        {trailState.ai_target ? `$${trailState.ai_target.toFixed(5)}` : 'Calculating...'}
                                      </p>
                                    </div>
                                    <div>
                                      <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-0.5">Entry</p>
                                      <p className="text-sm font-bold font-mono text-slate-400">${trailState.entry?.toFixed(5)}</p>
                                    </div>
                                  </div>
                                  
                                  <div className="mt-3 flex items-center gap-1.5">
                                    {[0,1,2,3].map(t => (
                                      <div key={t} className={`h-1.5 flex-1 rounded-full transition-all duration-500 ${
                                        trailState.tier >= t 
                                          ? t === 3 ? 'bg-cyan-500 shadow-[0_0_8px_rgba(6,182,212,0.6)]' 
                                            : t === 2 ? 'bg-emerald-500' 
                                            : t === 1 ? 'bg-amber-500' 
                                            : 'bg-slate-500'
                                          : 'bg-white/5'
                                      }`} />
                                    ))}
                                    <span className="text-[9px] text-slate-600 ml-1.5 font-bold">T{trailState.tier}/3</span>
                                  </div>
                                </div>
                              )}
                              
                              {/* AI Predictive Trap */}
                              {trap && (
                                <div className="flex-1 min-w-[280px]">
                                  <div className="flex items-center gap-2 mb-3">
                                    <div className={`w-1.5 h-1.5 rounded-full ${trap.executed ? 'bg-emerald-400' : 'bg-amber-400 animate-pulse'}`} />
                                    <span className={`text-[10px] uppercase tracking-[0.2em] font-black ${trap.executed ? 'text-emerald-400' : 'text-amber-400'}`}>
                                      {trap.executed ? 'Trap Executed ✓' : 'AI Trap Active'}
                                    </span>
                                  </div>
                                  
                                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                    <div>
                                      <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-0.5">Trigger At</p>
                                      <p className={`text-sm font-black font-heading ${trap.executed ? 'text-emerald-400 line-through' : 'text-amber-400'}`}>
                                        ${trap.trigger?.toFixed(5)}
                                      </p>
                                    </div>
                                    <div>
                                      <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-0.5">→ Snap SL To</p>
                                      <p className={`text-sm font-black font-heading ${trap.executed ? 'text-emerald-400' : 'text-cyan-400'}`}>
                                        ${trap.protective_sl?.toFixed(5)}
                                      </p>
                                    </div>
                                    <div>
                                      <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-0.5">Status</p>
                                      <p className={`text-xs font-black ${trap.executed ? 'text-emerald-400' : 'text-amber-400'}`}>
                                        {trap.executed ? 'LOCKED' : 'ARMED'}
                                      </p>
                                    </div>
                                  </div>
                                  
                                  {trap.reasoning && (
                                    <p className="mt-2 text-[10px] text-slate-600 italic leading-relaxed truncate">
                                      AI: {trap.reasoning}
                                    </p>
                                  )}
                                </div>
                              )}
                              
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default TradingCommandCenter;
