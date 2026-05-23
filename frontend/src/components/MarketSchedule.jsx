import React, { useState, useEffect } from 'react';
import { API_BASE } from '../lib/api';
import { Clock, Globe, ArrowRight } from 'lucide-react';

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
    const id = setInterval(fetchSchedule, 60000); // refresh every minute
    return () => clearInterval(id);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-4 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin" />
          <p className="text-slate-400 text-sm font-medium animate-pulse">Loading Schedule Matrix...</p>
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

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="glass-card rounded-3xl p-6 flex flex-col md:flex-row items-center justify-between gap-6 border border-white/5">
        <div>
          <h2 className="text-2xl font-black font-heading tracking-tight text-white mb-2 flex items-center gap-3">
            <Clock className="w-6 h-6 text-cyan-400" />
            Global Session Matrix
          </h2>
          <p className="text-sm text-slate-400 max-w-xl">
            Real-time synchronization with major forex market sessions. AI Fleet scanning is restricted to active session pairs to maximize momentum capture.
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

      {/* Gap Warning */}
      {scheduleData.is_gap && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-4 flex items-center gap-4">
          <div className="w-2 h-2 bg-amber-400 rounded-full animate-ping shrink-0" />
          <p className="text-sm text-amber-300">
            <strong className="text-amber-400">MARKET GAP:</strong> All major sessions are currently closed. The AI Fleet is sleeping to avoid low-liquidity slippage.
          </p>
        </div>
      )}

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {scheduleData.sessions.map(session => {
          const isActive = session.is_active;
          return (
            <div 
              key={session.id}
              className={`relative rounded-3xl overflow-hidden transition-all duration-500 ${
                isActive 
                  ? 'bg-gradient-to-br from-cyan-900/40 to-blue-900/20 border border-cyan-500/30 shadow-[0_0_30px_rgba(6,182,212,0.15)] transform scale-[1.02]' 
                  : 'bg-black/40 border border-white/5 opacity-60 hover:opacity-100'
              }`}
            >
              {isActive && (
                <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-cyan-400 to-blue-500" />
              )}
              
              <div className="p-6">
                <div className="flex justify-between items-start mb-6">
                  <h3 className={`text-lg font-bold tracking-tight ${isActive ? 'text-white' : 'text-slate-300'}`}>
                    {session.label}
                  </h3>
                  {isActive && (
                    <span className="px-2.5 py-1 bg-cyan-500/20 text-cyan-400 text-[10px] font-black uppercase tracking-widest rounded-full animate-pulse">
                      Live
                    </span>
                  )}
                </div>

                <div className="space-y-4">
                  <div className="bg-black/30 rounded-xl p-3 border border-white/5">
                    <p className="text-[10px] text-slate-500 uppercase tracking-widest font-bold mb-1">Time (IST)</p>
                    <p className={`font-mono text-sm ${isActive ? 'text-cyan-300' : 'text-slate-400'}`}>
                      {session.open_ist} - {session.close_ist}
                    </p>
                  </div>

                  <div>
                    <p className="text-[10px] text-slate-500 uppercase tracking-widest font-bold mb-2">Assigned Pairs</p>
                    <div className="flex flex-wrap gap-2">
                      {session.pairs.map(pair => (
                        <span 
                          key={pair} 
                          className={`px-2 py-1 text-xs rounded border ${
                            isActive 
                              ? 'bg-cyan-500/10 border-cyan-500/20 text-cyan-100' 
                              : 'bg-white/5 border-white/5 text-slate-400'
                          }`}
                        >
                          {pair}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      
      {/* Gold Overlap Alert */}
      <div className="bg-amber-500/10 border border-amber-500/20 rounded-3xl p-6 mt-6">
        <h3 className="text-amber-400 font-bold mb-2 flex items-center gap-2">
          <span className="text-xl">🏆</span> XAUUSD (Gold) Master Rule
        </h3>
        <p className="text-sm text-amber-200/70">
          Gold trading is strictly restricted to the high-liquidity window between <strong>08:00 - 16:00 UTC</strong> (London and New York overlap). Outside of these hours, Gold is automatically excluded from the scanning fleet to protect against choppy Asian range traps.
        </p>
      </div>

    </div>
  );
};

export default MarketSchedule;
