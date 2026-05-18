import React, { useState, useEffect, useRef } from 'react';
import { BarChart3, RefreshCw, Loader2, Clock, Zap, Shield, CheckCircle2, Timer, Users } from 'lucide-react';
import { API_BASE } from '../lib/api';
import HistoricalBacktest from './HistoricalBacktest';

const BacktestEngine = ({ wsConnected, marketData }) => {
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [progress, setProgress] = useState(null);
  const [countdown, setCountdown] = useState(300);
  const [status, setStatus] = useState('waiting');
  const intervalRef = useRef(null);

  useEffect(() => {
    checkBacktestStatus();
    intervalRef.current = setInterval(checkBacktestStatus, 2000);
    return () => clearInterval(intervalRef.current);
  }, []);

  useEffect(() => {
    if (status !== 'waiting') return;
    const timer = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) { clearInterval(timer); setStatus('running'); return 0; }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [status]);

  const checkBacktestStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/backtest/auto`);
      const data = await response.json();
      if (data.progress) setProgress(data.progress);
      if (data.success && data.ready) {
        setResults(Array.isArray(data.results) ? data.results : [data.results]);
        setStatus('ready'); setCountdown(0);
      } else if (data.remaining_seconds > 0) {
        setCountdown(data.remaining_seconds); setStatus('waiting');
      } else { setStatus('running'); }
    } catch (error) { console.error('Backtest status error:', error); }
  };

  const rerunBacktest = async () => {
    setLoading(true); setResults(null); setStatus('running');
    setProgress({ status: 'running', current_account: null, completed_accounts: [], remaining_accounts: [], cooldown_remaining: 0, results: [] });
    try {
      const response = await fetch(`${API_BASE}/api/backtest/rerun`, { method: 'POST', headers: { 'Content-Type': 'application/json' } });
      const data = await response.json();
      if (data.success) { setStatus('running'); } else { alert('Re-backtest failed: ' + (data.error || 'Unknown error')); }
    } catch (error) { alert('Re-backtest error: ' + error.message); }
    setLoading(false);
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const pnlColor = (val) => val >= 0 ? 'text-emerald-400' : 'text-rose-400';
  const pnlSign = (val) => val >= 0 ? '+' : '';
  const accountCount = Object.keys(marketData?.account_balances || {}).length;

  return (
    <div className="max-w-6xl mx-auto w-full space-y-8 animate-fade-in">
      {/* MT5 Historical Backtest Panel */}
      <HistoricalBacktest />

    </div>
  );
};

export default BacktestEngine;
