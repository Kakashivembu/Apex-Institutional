import React, { useState, useEffect } from 'react';
import { API_BASE } from '../lib/api';
import { Clock, Globe, ArrowRight, Shield, Crosshair, Zap, Moon } from 'lucide-react';

const PHASE_CONFIG = {
  build: { icon: Shield, gradient: 'from-purple-600 to-violet-800', border: 'border-purple-500/40', glow: 'shadow-[0_0_30px_rgba(147,51,234,0.2)]', text: 'text-purple-300', badge: 'bg-purple-500/20 text-purple-300', dot: 'bg-purple-400', bar: 'from-purple-500 to-violet-600' },
  sweep: { icon: Crosshair, gradient: 'from-red-600 to-rose-800', border: 'border-red-500/40', glow: 'shadow-[0_0_30px_rgba(239,68,68,0.2)]', text: 'text-red-300', badge: 'bg-red-500/20 text-red-300', dot: 'bg-red-400', bar: 'from-red-500 to-rose-600' },
  entry: { icon: Zap, gradient: 'from-emerald-600 to-green-800', border: 'border-emerald-500/40', glow: 'shadow-[0_0_30px_rgba(16,185,129,0.2)]', text: 'text-emerald-300', badge: 'bg-emerald-500/20 text-emerald-300', dot: 'bg-emerald-400', bar: 'from-emerald-500 to-green-600' },
  cooldown: { icon: Moon, gradient: 'from-slate-600 to-slate-800', border: 'border-slate-500/30', glow: '', text: 'text-slate-400', badge: 'bg-slate-500/20 text-slate-400', dot: 'bg-slate-500', bar: 'from-slate-500 to-slate-600' },
};

const BOT_STATUS_LABELS = {
  DORMANT: { label: 'DORMANT', color: 'text-purple-400', bg: 'bg-purple-500/10 border-purple-500/30' },
  ARMED: { label: 'ARMED', color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/30' },
  FIRES: { label: 'ACTIVE', color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/30' },
  SLEEPING: { label: 'SLEEPING', color: 'text-slate-500', bg: 'bg-slate-500/10 border-slate-500/30' },
};

const MarketSchedule = () => {
  const [scheduleData, setScheduleData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchSchedule = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/market-schedule`);
        const data = await res.json();
        if (data.success) {
          setScheduleData(data);
        }
      } catch (err) {
        console.error('Failed to fetch market schedule:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchSchedule();
    const id = setInterval(fetchSchedule, 30000);
    return () => clearInterval(id);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-4 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin" />
          <p className="text-slate-400 text-sm font-medium animate-pulse">Loading Strategy Schedule...</p>
        </div>
      </div>
    );
  }

  if (!scheduleData) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-500 min-h-[400px]">
        <Globe className="w-12 h-12 mb-4 opacity-50" />
        <p>Schedule data unavailable.</p>
      </div>
    );
  }

  const currentPhaseData = (scheduleData.geek_phases || []).find(p => p.is_active);
  const phaseStyle = currentPhaseData ? PHASE_CONFIG[currentPhaseData.id] : PHASE_CONFIG.cooldown;
  const statusInfo = currentPhaseData ? BOT_STATUS_LABELS[currentPhaseData.bot_status] : BOT_STATUS_LABELS.SLEEPING;

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Header with Current Phase */}
      <div className={`glass-card rounded-3xl p-6 border ${phaseStyle.border} ${phaseStyle.glow} transition-all duration-700`}>
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div className="flex-1">
            <h2 className="text-2xl font-black font-heading tracking-tight text-white mb-2 flex items-center gap-3">
              <Clock className="w-6 h-6 text-cyan-400" />
              The Trading Geek Strategy
              <span className="text-sm font-normal text-slate-500">(IST)</span>
            </h2>
            <p className="text-sm text-slate-400 max-w-xl">
              Strictly follows structural sweeps. The bot waits for a liquidity sweep of the Asian Range during London/NY, waits for a LTF CHoCH + FVG, and enters at the Order Block with trend alignment.
            </p>
          </div>
          
          <div className="flex items-center gap-6 bg-black/40 px-6 py-4 rounded-2xl border border-white/5 shrink-0">
            <div className="text-center">
              <p className="text-[10px] text-slate-500 uppercase tracking-widest font-bold mb-1">Server (UTC)</p>
              <p className="text-xl font-mono font-bold text-white">{scheduleData.utc_time.replace(' UTC', '')}</p>
            </div>
            <ArrowRight className="w-4 h-4 text-slate-600" />
            <div className="text-center">
              <p className="text-[10px] text-cyan-500 uppercase tracking-widest font-bold mb-1">Local (IST)</p>
              <p className="text-xl font-mono font-bold text-cyan-400">{scheduleData.ist_time.replace(' IST', '')}</p>
            </div>
          </div>
        </div>

        {/* Current Phase Banner */}
        {currentPhaseData && (
          <div className={`mt-6 rounded-2xl p-5 bg-gradient-to-r ${phaseStyle.gradient} bg-opacity-20 border ${phaseStyle.border}`}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <span className="text-2xl">{currentPhaseData.emoji}</span>
                <div>
                  <p className="text-white font-black text-lg">{currentPhaseData.label}</p>
                  <p className="text-white/60 text-xs font-mono">{currentPhaseData.ist_open} — {currentPhaseData.ist_close} IST</p>
                </div>
              </div>
              <span className={`px-4 py-2 rounded-xl text-xs font-black uppercase tracking-widest border ${statusInfo.bg} ${statusInfo.color} animate-pulse`}>
                Bot: {statusInfo.label}
              </span>
            </div>
            <p className="text-white/80 text-sm leading-relaxed">{currentPhaseData.description}</p>
          </div>
        )}
      </div>

      {/* Geek Phase Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {(scheduleData.geek_phases || []).map(phase => {
          const style = PHASE_CONFIG[phase.id] || PHASE_CONFIG.cooldown;
          const PhaseIcon = style.icon;
          const isActive = phase.is_active;
          const status = BOT_STATUS_LABELS[phase.bot_status] || BOT_STATUS_LABELS.SLEEPING;
          
          return (
            <div 
              key={phase.id}
              className={`relative rounded-3xl overflow-hidden transition-all duration-500 ${
                isActive 
                  ? `bg-gradient-to-br ${style.gradient} bg-opacity-30 ${style.border} border ${style.glow} transform scale-[1.02]` 
                  : 'bg-black/40 border border-white/5 opacity-60 hover:opacity-100'
              }`}
            >
              {isActive && (
                <div className={`absolute top-0 inset-x-0 h-1 bg-gradient-to-r ${style.bar}`} />
              )}
              
              <div className="p-6">
                <div className="flex justify-between items-start mb-4">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">{phase.emoji}</span>
                    <h3 className={`text-sm font-bold tracking-tight ${isActive ? 'text-white' : 'text-slate-300'}`}>
                      {phase.label}
                    </h3>
                  </div>
                  {isActive && (
                    <span className={`px-2 py-1 text-[9px] font-black uppercase tracking-widest rounded-full animate-pulse ${style.badge}`}>
                      Live
                    </span>
                  )}
                </div>

                <div className="space-y-4">
                  {/* Time Block */}
                  <div className="bg-black/30 rounded-xl p-3 border border-white/5">
                    <p className="text-[10px] text-slate-500 uppercase tracking-widest font-bold mb-1">Time (IST)</p>
                    <p className={`font-mono text-sm font-bold ${isActive ? style.text : 'text-slate-400'}`}>
                      {phase.ist_open} — {phase.ist_close}
                    </p>
                    <p className="text-[10px] text-slate-600 font-mono mt-1">
                      {phase.utc_open} — {phase.utc_close} UTC
                    </p>
                  </div>

                  {/* Bot Status */}
                  <div className="bg-black/30 rounded-xl p-3 border border-white/5">
                    <p className="text-[10px] text-slate-500 uppercase tracking-widest font-bold mb-1">Bot Status</p>
                    <p className={`text-xs font-black uppercase tracking-wider ${isActive ? status.color : 'text-slate-500'}`}>
                      {phase.bot_status}
                    </p>
                  </div>

                  {/* Description */}
                  <p className={`text-[11px] leading-relaxed ${isActive ? 'text-white/70' : 'text-slate-500'}`}>
                    {phase.detail}
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Gold Master Rule */}
      <div className="bg-amber-500/10 border border-amber-500/20 rounded-3xl p-6">
        <h3 className="text-amber-400 font-bold mb-2 flex items-center gap-2">
          <span className="text-xl">🏆</span> XAUUSD (Gold) Master Rule
        </h3>
        <p className="text-sm text-amber-200/70">
          The Trading Geek strategy for Gold relies on volatility. It only fires during the <strong>London Open to NY Close</strong> window. During the slow Asian session, the bot only collects the highest and lowest price to set up the trap.
        </p>
      </div>

      {/* Trading Geek Strategy Summary */}
      <div className="bg-gradient-to-br from-cyan-900/20 to-blue-900/10 border border-cyan-500/15 rounded-3xl p-6">
        <h3 className="text-cyan-400 font-bold mb-4 flex items-center gap-2">
          <Crosshair className="w-5 h-5" /> Trading Geek Execution Engine
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-black/30 rounded-xl p-4 border border-blue-500/20">
            <p className="text-blue-400 font-bold text-sm mb-2">1. 1H Trend Align</p>
            <p className="text-[11px] text-slate-400 leading-relaxed">The bot checks the 1-Hour chart to verify if price is above or below the 200 EMA. It will never trade counter-trend.</p>
          </div>
          <div className="bg-black/30 rounded-xl p-4 border border-purple-500/20">
            <p className="text-purple-400 font-bold text-sm mb-2">2. Liquidity Sweep</p>
            <p className="text-[11px] text-slate-400 leading-relaxed">Price must pierce beyond the Asian High or Asian Low to take out retail stop losses.</p>
          </div>
          <div className="bg-black/30 rounded-xl p-4 border border-amber-500/20">
            <p className="text-amber-400 font-bold text-sm mb-2">3. LTF CHoCH</p>
            <p className="text-[11px] text-slate-400 leading-relaxed">After the sweep, the bot drops to the 1m/5m chart and waits for a strong, energetic reversal that breaks structure (CHoCH).</p>
          </div>
          <div className="bg-black/30 rounded-xl p-4 border border-emerald-500/20">
            <p className="text-emerald-400 font-bold text-sm mb-2">4. Limit Entry</p>
            <p className="text-[11px] text-slate-400 leading-relaxed">The bot places a Limit Order precisely at the Order Block (the last opposite candle before the CHoCH) with SL at the wick.</p>
          </div>
        </div>
      </div>

    </div>
  );
};

export default MarketSchedule;
