import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Terminal, Search, Pause, Play, Copy, Trash2, ArrowDown } from 'lucide-react';

const LOG_COLORS = {
  '[CLAW]': 'text-cyan-400',
  '[MACRO': 'text-purple-400',
  '[SCALPER]': 'text-amber-400',
  '[STEP-TRAIL': 'text-emerald-400',
  '[DELTA': 'text-blue-400',
  '[ERROR': 'text-rose-400',
  '[SYSTEM]': 'text-white',
  '[BACKTEST': 'text-purple-400',
  '[AUTOPSY]': 'text-amber-400',
  '[TRADE': 'text-emerald-400',
  '[STARTUP]': 'text-pink-400',
  '[RISK]': 'text-amber-400',
  '[MEMORY]': 'text-slate-400',
  '[FLEET]': 'text-cyan-400',
  '[SERVER]': 'text-slate-400',
  '[GLOBAL DOM]': 'text-blue-300',
  '[CANDLES]': 'text-purple-300',
  '[CONSENSUS]': 'text-white font-bold',
  '[HUNT MODE]': 'text-emerald-300 font-medium',
  '[MONITOR MODE]': 'text-amber-300 font-medium',
  '[PARALLEL]': 'text-cyan-300',
  'FINAL DECISION': 'text-white font-bold',
  'CONSENSUS': 'text-white font-bold',
  '===': 'text-slate-600',
};

const getLogColor = (msg) => {
  for (const [key, color] of Object.entries(LOG_COLORS)) {
    if (msg.includes(key)) return color;
  }
  return 'text-slate-500';
};

const LiveTerminal = ({ serverLogs = [], onClear }) => {
  const [filter, setFilter] = useState('');
  const [paused, setPaused] = useState(false);
  const [userScrolledUp, setUserScrolledUp] = useState(false);
  const containerRef = useRef(null);
  const bottomRef = useRef(null);
  const prevLenRef = useRef(0);
  const isAutoScrolling = useRef(false);

  const filtered = useMemo(() => {
    if (!filter) return serverLogs;
    const lc = filter.toLowerCase();
    return serverLogs.filter(l => l.msg.toLowerCase().includes(lc));
  }, [serverLogs, filter]);

  // Auto-scroll to bottom when new logs arrive (if user hasn't scrolled up)
  useEffect(() => {
    if (paused || userScrolledUp) return;
    
    // Pause auto-scrolling if user is selecting text
    const selection = window.getSelection();
    if (selection && selection.toString().length > 0) return;

    // Always scroll to bottom if we are supposed to be at the bottom.
    // We don't check length because when the array hits 2000, length stops increasing,
    // which would otherwise break auto-scroll and cause DOM shifting (flickering).
    isAutoScrolling.current = true;
    bottomRef.current?.scrollIntoView({ behavior: 'instant' });
    
    // Reset the flag after scroll event fires
    requestAnimationFrame(() => {
      isAutoScrolling.current = false;
    });
  }, [filtered, paused, userScrolledUp]);

  const handleScroll = useCallback(() => {
    if (!containerRef.current || isAutoScrolling.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    // User is "scrolled up" if they're more than 20px from the bottom
    const atBottom = scrollHeight - scrollTop - clientHeight < 20;
    setUserScrolledUp(!atBottom);
  }, []);

  const scrollToBottom = useCallback(() => {
    setUserScrolledUp(false);
    setPaused(false);
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  const copyLogs = useCallback(() => {
    const text = filtered.map(l => `[${l.ts}] ${l.msg}`).join('\n');
    navigator.clipboard.writeText(text);
  }, [filtered]);

  return (
    <div className="max-w-6xl mx-auto w-full animate-fade-in">
      <div className="glass-card p-0 overflow-hidden relative" style={{ height: 'calc(100vh - 180px)' }}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 sm:px-5 py-3 border-b border-white/5 bg-black/60">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-pink-500 to-pink-600 flex items-center justify-center shadow-lg shadow-pink-500/20">
              <Terminal className="w-4.5 h-4.5 text-white" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Live Terminal</h2>
              <p className="text-[10px] text-slate-500">
                {filtered.length} log entries
                {paused && <span className="text-amber-400 ml-2">● PAUSED</span>}
                {userScrolledUp && !paused && <span className="text-blue-400 ml-2">● SCROLLED</span>}
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            {/* Search */}
            <div className="relative hidden sm:block">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
              <input
                type="text"
                placeholder="Filter logs..."
                value={filter}
                onChange={e => setFilter(e.target.value)}
                className="w-48 pl-8 pr-3 py-1.5 bg-white/5 border border-white/10 rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-pink-500/40 transition-colors"
              />
            </div>

            {/* Pause */}
            <button
              onClick={() => setPaused(!paused)}
              className={`p-2 rounded-lg border transition-colors ${paused ? 'bg-amber-500/10 border-amber-500/20 text-amber-400' : 'bg-white/5 border-white/10 text-slate-400 hover:text-white'}`}
              title={paused ? 'Resume auto-scroll' : 'Pause auto-scroll'}
            >
              {paused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
            </button>

            {/* Copy */}
            <button
              onClick={copyLogs}
              className="p-2 rounded-lg bg-white/5 border border-white/10 text-slate-400 hover:text-white transition-colors"
              title="Copy logs"
            >
              <Copy className="w-3.5 h-3.5" />
            </button>

            {/* Clear */}
            {onClear && (
              <button
                onClick={onClear}
                className="p-2 rounded-lg bg-white/5 border border-white/10 text-slate-400 hover:text-rose-400 transition-colors"
                title="Clear logs"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Log Area */}
        <div
          ref={containerRef}
          onScroll={handleScroll}
          className="overflow-y-auto px-3 sm:px-4 py-2 bg-black/40"
          style={{ height: 'calc(100% - 52px)' }}
        >
          {filtered.length === 0 ? (
            <div className="flex items-center justify-center h-full text-slate-600 text-sm">
              <div className="text-center">
                <Terminal className="w-8 h-8 mx-auto mb-3 opacity-30" />
                <p>Waiting for server logs...</p>
              </div>
            </div>
          ) : (
            <>
              {filtered.map((log, i) => (
                <div key={log.id || i} className={`terminal-line ${getLogColor(log.msg)}`}>
                  <span className="text-slate-600 mr-2 select-none">{log.ts}</span>
                  {log.msg}
                </div>
              ))}
              <div ref={bottomRef} />
            </>
          )}
        </div>

        {/* Scroll to bottom FAB */}
        {(userScrolledUp || paused) && (
          <button
            onClick={scrollToBottom}
            className="absolute bottom-4 right-6 flex items-center space-x-2 px-3 py-2 rounded-full bg-pink-500/20 border border-pink-500/30 text-pink-400 hover:bg-pink-500/30 transition-all shadow-lg shadow-pink-500/10 z-10"
          >
            <ArrowDown className="w-4 h-4" />
            <span className="text-[10px] font-medium">Latest</span>
          </button>
        )}
      </div>
    </div>
  );
};

export default LiveTerminal;
