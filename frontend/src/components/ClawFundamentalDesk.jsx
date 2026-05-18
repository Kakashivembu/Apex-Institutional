import React, { useState, useEffect } from 'react';
import { Activity, TrendingUp, TrendingDown, Minus, AlertTriangle, RefreshCw, Loader2, Shield, BarChart3, Droplets } from 'lucide-react';
import { API_BASE } from '../lib/api';

const ClawFundamentalDesk = ({ wsConnected, marketData }) => {
  const [clawData, setClawData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefresh, setLastRefresh] = useState(null);

  useEffect(() => {
    fetchClawIntelligence();
    const interval = setInterval(fetchClawIntelligence, 60_000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!marketData?.swarm_decisions?.length) return;
    const clawDecision = marketData.swarm_decisions.find(d => d.agent === 'CLAW');
    if (!clawDecision) return;
    setClawData(prev => ({
      ...prev,
      sentiment: clawDecision.decision,
      confidence: clawDecision.confidence,
      report: clawDecision.signal?.replace(/^Sentiment:\s*/, '') || prev?.report || '',
      squeeze_risk: prev?.squeeze_risk || 'MEDIUM',
      dominant_side: prev?.dominant_side || 'BALANCED',
      liquidity_data: prev?.liquidity_data || '',
    }));
  }, [marketData]);

  const fetchClawIntelligence = async () => {
    try {
      setError(null);
      const res = await fetch(`${API_BASE}/api/claw/intelligence`, { signal: AbortSignal.timeout(15_000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.success) {
        setClawData(data);
        setLastRefresh(new Date());
      }
    } catch (err) {
      console.error('[CLAW] Fetch error:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchClawIntelligence();
    setRefreshing(false);
  };

  const sentiment = (clawData?.sentiment || 'NEUTRAL').toUpperCase();
  const confidence = clawData?.confidence ?? 0;
  const squeezeRisk = (clawData?.squeeze_risk || 'MEDIUM').toUpperCase();
  const dominantSide = (clawData?.dominant_side || 'BALANCED').toUpperCase();
  const report = clawData?.report || 'Awaiting AI analysis...';
  const liquidityData = clawData?.liquidity_data || '';
  const bullishPct = clawData?.bullish_pct ?? 33;
  const bearishPct = clawData?.bearish_pct ?? 33;
  const neutralPct = clawData?.neutral_pct ?? 34;

  const sentimentConfig = {
    BULLISH: { color: 'emerald', icon: TrendingUp, border: 'border-emerald-500/30', bg: 'bg-emerald-500/10', text: 'text-emerald-400', glow: 'shadow-emerald-500/20' },
    BEARISH: { color: 'rose', icon: TrendingDown, border: 'border-rose-500/30', bg: 'bg-rose-500/10', text: 'text-rose-400', glow: 'shadow-rose-500/20' },
    NEUTRAL: { color: 'slate', icon: Minus, border: 'border-cyan-500/30', bg: 'bg-cyan-500/10', text: 'text-cyan-400', glow: 'shadow-cyan-500/10' },
  };
  const sCfg = sentimentConfig[sentiment] || sentimentConfig.NEUTRAL;
  const SentimentIcon = sCfg.icon;

  const squeezeConfig = {
    HIGH: { color: 'red', border: 'border-red-500/50', bg: 'bg-red-500/10', text: 'text-red-400', pulse: true },
    MEDIUM: { color: 'amber', border: 'border-amber-500/40', bg: 'bg-amber-500/10', text: 'text-amber-400', pulse: false },
    LOW: { color: 'emerald', border: 'border-emerald-500/30', bg: 'bg-emerald-500/10', text: 'text-emerald-400', pulse: false },
  };
  const sqCfg = squeezeConfig[squeezeRisk] || squeezeConfig.MEDIUM;

  const sideConfig = {
    LONG: { color: 'emerald', bg: 'bg-emerald-500/10', text: 'text-emerald-400' },
    SHORT: { color: 'rose', bg: 'bg-rose-500/10', text: 'text-rose-400' },
    BALANCED: { color: 'cyan', bg: 'bg-cyan-500/10', text: 'text-cyan-400' },
  };
  const sdCfg = sideConfig[dominantSide] || sideConfig.BALANCED;

  const confidenceColor = confidence >= 70 ? 'emerald' : confidence >= 40 ? 'amber' : 'rose';
  const confidenceText = { emerald: 'text-emerald-400', amber: 'text-amber-400', rose: 'text-rose-400' }[confidenceColor];

  const GaugeBar = ({ value, colorClass }) => (
    <div className="w-full h-1.5 bg-black/40 rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-700 ${colorClass}`}
        style={{ width: `${Math.min(100, value)}%` }}
      />
    </div>
  );

  return (
    <div className="max-w-6xl mx-auto w-full">
      <div className="glass-card p-8">

        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center space-x-4">
            <div className={`w-12 h-12 rounded-2xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/20`}>
              <Activity className="w-6 h-6 text-white" />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-white tracking-tight">Global Macro & Sentiment Radar</h2>
              <p className="text-sm text-slate-500 mt-1">Real-time MT5 Forex & Commodities macro intelligence</p>
            </div>
          </div>
          <div className="flex items-center space-x-4">
            {/* FIX #3: Refresh button disabled when disconnected */}
            <button
              onClick={handleRefresh}
              disabled={refreshing || loading || !wsConnected}
              className={`px-4 py-2 rounded-xl border transition-all flex items-center space-x-2 ${
                !wsConnected
                  ? 'bg-slate-800/40 border-slate-700/30 text-slate-600 cursor-not-allowed opacity-50'
                  : 'bg-white/5 hover:bg-white/10 border-white/5 hover:border-cyan-500/30 disabled:opacity-40'
              }`}
              title={!wsConnected ? 'WebSocket disconnected — cannot refresh' : ''}
            >
              <RefreshCw className={`w-4 h-4 text-slate-400 ${refreshing || !wsConnected ? 'animate-spin' : ''}`} />
              <span className="text-sm text-slate-400">{!wsConnected ? 'Offline' : refreshing ? 'Fetching...' : 'Refresh'}</span>
            </button>
            <div className="flex items-center space-x-2">
              {wsConnected ? (
                <>
                  <div className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse shadow-lg shadow-emerald-400/50" />
                  <span className="text-xs text-emerald-400 font-medium">Live</span>
                </>
              ) : (
                <>
                  <div className="w-2 h-2 bg-rose-400 rounded-full" />
                  <span className="text-xs text-rose-400 font-medium">Disconnected</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* FIX #3: Disconnected state fallback banner */}
        {!wsConnected && (
          <div className="mb-6 p-4 bg-amber-500/10 border border-amber-500/30 rounded-2xl flex items-center space-x-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
            <div>
              <p className="text-amber-300 text-sm font-bold">⚠️ Live Macro feed offline — radar using cached data</p>
              <p className="text-amber-400/60 text-xs mt-0.5">Live sentiment data unavailable. Reconnecting automatically...</p>
            </div>
          </div>
        )}

        {loading && !clawData ? (
          <div className="flex flex-col items-center justify-center py-16 space-y-3">
            <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
            <span className="text-slate-400 text-sm">Fetching macro sentiment data from MT5...</span>
          </div>
        ) : error && !clawData ? (
          <div className="bg-red-500/10 border border-red-500/20 rounded-2xl p-6 text-center">
            <AlertTriangle className="w-8 h-8 text-red-400 mx-auto mb-2" />
            <p className="text-red-400 font-medium">Failed to load CLAW data</p>
            <p className="text-slate-400 text-sm mt-1">{error}</p>
            <button onClick={handleRefresh} className="mt-3 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 border border-red-500/30 rounded-xl text-sm text-red-400 transition-colors">
              Retry
            </button>
          </div>
        ) : (
          <>
            {/* Main sentiment banner */}
            <div className={`rounded-2xl p-5 mb-6 border ${sCfg.border} ${sCfg.bg} ${sqCfg.pulse ? 'animate-pulse' : ''}`}
              style={sqCfg.pulse ? { boxShadow: `0 0 30px rgba(239,68,68,0.1)` } : {}}>
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center space-x-3">
                  <div className={`w-10 h-10 rounded-xl ${sCfg.bg} border ${sCfg.border} flex items-center justify-center`}>
                    <SentimentIcon className={`w-5 h-5 ${sCfg.text}`} />
                  </div>
                  <div>
                    <div className={`font-bold text-lg ${sCfg.text}`}>AI Verdict: {sentiment}</div>
                    <div className="text-xs text-slate-400 mt-0.5">
                      Confidence: <span className={confidenceText}>{confidence}%</span>
                      {lastRefresh && <> · Updated {lastRefresh.toLocaleTimeString()}</>}
                    </div>
                  </div>
                </div>
                {liquidityData && (
                  <div className="text-xs text-slate-400 font-mono bg-black/20 px-3 py-1.5 rounded-lg border border-white/5">
                    {liquidityData.length > 60 ? liquidityData.slice(0, 60) + '…' : liquidityData}
                  </div>
                )}
              </div>
            </div>

            {/* 2x2 Metric Grid */}
            <div className="grid grid-cols-2 gap-4 mb-6">

              {/* Sentiment Breakdown */}
              <div className="bg-black/30 border border-white/5 rounded-2xl p-5">
                <div className="flex items-center space-x-2 mb-4">
                  <BarChart3 className="w-4 h-4 text-cyan-400" />
                  <span className="text-sm font-semibold text-white">Sentiment Breakdown</span>
                </div>
                <div className="space-y-3">
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-emerald-400">Bullish</span>
                      <span className="text-white font-mono">{bullishPct}%</span>
                    </div>
                    <GaugeBar value={bullishPct} colorClass="bg-emerald-500" />
                  </div>
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-slate-400">Neutral</span>
                      <span className="text-white font-mono">{neutralPct}%</span>
                    </div>
                    <GaugeBar value={neutralPct} colorClass="bg-slate-500" />
                  </div>
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-rose-400">Bearish</span>
                      <span className="text-white font-mono">{bearishPct}%</span>
                    </div>
                    <GaugeBar value={bearishPct} colorClass="bg-rose-500" />
                  </div>
                </div>
              </div>

              {/* Volatility & Whipsaw Risk */}
              <div className={`bg-black/30 border rounded-2xl p-5 ${sqCfg.border} ${sqCfg.pulse ? 'animate-pulse' : ''}`}
                style={sqCfg.pulse ? { boxShadow: `0 0 20px rgba(239,68,68,0.08)` } : {}}>
                <div className="flex items-center space-x-2 mb-4">
                  <AlertTriangle className={`w-4 h-4 ${sqCfg.text}`} />
                  <span className="text-sm font-semibold text-white">Volatility & Whipsaw Risk</span>
                </div>
                <div className="flex items-center justify-center flex-col">
                  <span className={`text-4xl font-black ${sqCfg.text} tracking-wider`}>{squeezeRisk}</span>
                  <span className="text-xs text-slate-500 mt-2">
                    {squeezeRisk === 'HIGH' ? 'Elevated volatility — potential whipsaw incoming' :
                     squeezeRisk === 'MEDIUM' ? 'Moderate positioning — watch for momentum shift' :
                     'Stable order flow — low whipsaw risk'}
                  </span>
                </div>
              </div>

              {/* Dominant Side */}
              <div className={`bg-black/30 border rounded-2xl p-5 ${sdCfg.color === 'emerald' ? 'border-emerald-500/20' : sdCfg.color === 'rose' ? 'border-rose-500/20' : 'border-cyan-500/20'}`}>
                <div className="flex items-center space-x-2 mb-4">
                  <Droplets className={`w-4 h-4 ${sdCfg.text}`} />
                  <span className="text-sm font-semibold text-white">Dominant Side</span>
                </div>
                <div className="flex items-center justify-center flex-col">
                  <span className={`text-4xl font-black ${sdCfg.text} tracking-wider`}>{dominantSide}</span>
                  <span className="text-xs text-slate-500 mt-2">
                    {dominantSide === 'LONG' ? 'Majority of flow is bullish — watch for reversal traps' :
                     dominantSide === 'SHORT' ? 'Majority of flow is bearish — watch for snap-back rallies' :
                     'Longs and shorts are balanced — no directional pressure'}
                  </span>
                </div>
              </div>

              {/* Confidence Score */}
              <div className="bg-black/30 border border-white/5 rounded-2xl p-5">
                <div className="flex items-center space-x-2 mb-4">
                  <Shield className={`w-4 h-4 ${confidenceText}`} />
                  <span className="text-sm font-semibold text-white">Confidence Score</span>
                </div>
                <div className="flex items-center justify-center flex-col">
                  <div className="relative w-24 h-24">
                    <svg className="w-24 h-24 -rotate-90" viewBox="0 0 100 100">
                      <circle cx="50" cy="50" r="42" fill="none" stroke="#0b1114" strokeWidth="10" />
                      <circle
                        cx="50" cy="50" r="42" fill="none"
                        stroke={confidenceColor === 'emerald' ? '#10b981' : confidenceColor === 'amber' ? '#f59e0b' : '#f43f5e'}
                        strokeWidth="10"
                        strokeDasharray={`${(confidence / 100) * 264} 264`}
                        strokeLinecap="round"
                        className="transition-all duration-1000"
                      />
                    </svg>
                    <div className="absolute inset-0 flex items-center justify-center">
                      <span className={`text-2xl font-black ${confidenceText}`}>{confidence}</span>
                    </div>
                  </div>
                  <span className="text-xs text-slate-500 mt-2 text-center">
                    {confidence >= 70 ? 'High confidence — strong signal' :
                     confidence >= 40 ? 'Moderate confidence — act with caution' :
                     'Low confidence — market unclear'}
                  </span>
                </div>
              </div>

            </div>

            {/* AI Tactical Summary - Frosted Glass Terminal */}
            <div className="relative group">
              <div className="absolute -inset-0.5 bg-gradient-to-r from-cyan-500/10 via-blue-500/10 to-cyan-500/10 rounded-2xl blur opacity-40 group-hover:opacity-60 transition-opacity" />
              <div className="relative bg-[#0a0f14]/90 backdrop-blur-xl border border-cyan-500/20 rounded-2xl p-6">
                <div className="flex items-center space-x-2 mb-4">
                  <div className="w-2 h-2 bg-cyan-400 rounded-full animate-pulse shadow-lg shadow-cyan-400/50" />
                  <span className="text-xs font-bold text-cyan-400 uppercase tracking-widest">AI Tactical Summary</span>
                  <span className="text-xs text-slate-600 ml-auto">CLAW Agent · Macro Sentiment v3.0</span>
                </div>
                <p className="text-slate-200 text-sm leading-relaxed font-mono">
                  {report}
                </p>
                <div className="mt-4 pt-4 border-t border-white/5 flex items-center justify-between">
                  <div className="flex items-center space-x-3 text-xs text-slate-500">
                    <span className={`flex items-center space-x-1.5 ${sqCfg.text}`}>
                      <AlertTriangle className="w-3 h-3" />
                      <span>Risk: {squeezeRisk}</span>
                    </span>
                    <span className={`flex items-center space-x-1.5 ${sdCfg.text}`}>
                      <Droplets className="w-3 h-3" />
                      <span>Side: {dominantSide}</span>
                    </span>
                  </div>
                  <span className="text-xs text-slate-600">
                    {clawData?.last_updated ? `Fetched ${new Date(clawData.last_updated).toLocaleTimeString()}` : ''}
                  </span>
                </div>
              </div>
            </div>

          </>
        )}
      </div>
    </div>
  );
};

export default ClawFundamentalDesk;
