import React, { useState, useEffect, useCallback } from 'react';
import { Settings, Save, RotateCcw, Shield, AlertTriangle, CheckCircle2, XCircle, Loader2, Target } from 'lucide-react';
import { API_BASE } from '../lib/api';

const FOREX_DEFAULTS = {
  mode: 'forex',
  max_risk_pct: 2.0,
  max_daily_drawdown_pct: 3.0,
  max_trade_drawdown_pct: 2.0,
  base_take_profit_pct: 0.25,
  base_stop_loss_pct: 0.12,
  max_leverage: 10,
  max_open_positions: 1,
  cooldown_minutes: 45,
  auto_rebalance: true,
  stop_loss_enabled: true,
  take_profit_enabled: true,
  scalper_mode: false,
};

const CRYPTO_DEFAULTS = {
  mode: 'crypto',
  max_risk_pct: 10,
  max_daily_drawdown_pct: 10.0,
  max_trade_drawdown_pct: 3.0,
  base_take_profit_pct: 6,
  base_stop_loss_pct: 3,
  max_leverage: 20,
  max_open_positions: 10,
  cooldown_minutes: 5,
  auto_rebalance: true,
  stop_loss_enabled: true,
  take_profit_enabled: true,
  scalper_mode: false,
};

const SystemParameters = ({ wsConnected }) => {
  const [params, setParams] = useState({ ...FOREX_DEFAULTS });
  const [toast, setToast] = useState(null); // { type: 'success'|'error', msg: string }
  const [saving, setSaving] = useState(false);
  const [loadingParams, setLoadingParams] = useState(true);
  const [serverConnected, setServerConnected] = useState(false);
  const [dirty, setDirty] = useState(false);

  const isForex = params.mode === 'forex';

  // ── FIX #1: Server health check — poll every 15s ──
  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/trading/status`, { signal: AbortSignal.timeout(3000) });
      setServerConnected(res.ok);
    } catch {
      setServerConnected(false);
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const iv = setInterval(checkHealth, 15_000);
    return () => clearInterval(iv);
  }, [checkHealth]);

  // ── FIX #2: Load parameters on mount ──
  const fetchParams = useCallback(async () => {
    setLoadingParams(true);
    try {
      const res = await fetch(`${API_BASE}/api/parameters`, { signal: AbortSignal.timeout(5000) });
      if (res.ok) {
        const data = await res.json();
        if (data.success && data.parameters) {
          setParams(data.parameters);
          setDirty(false);
        }
      }
    } catch (err) {
      console.error('[PARAMS] Fetch error:', err);
    } finally {
      setLoadingParams(false);
    }
  }, []);

  useEffect(() => { fetchParams(); }, [fetchParams]);

  // ── Toast auto-dismiss ──
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  // ── Slider configs per mode ──
  const sliderConfig = {
    max_risk_pct:        isForex ? { min: 0.5, max: 10, step: 0.5 } : { min: 1, max: 50, step: 1 },
    max_daily_drawdown_pct: { min: 1, max: 20, step: 0.5 },
    max_trade_drawdown_pct: { min: 0.5, max: 10, step: 0.5 },
    base_take_profit_pct: isForex ? { min: 0.05, max: 1, step: 0.05 } : { min: 1, max: 50, step: 1 },
    base_stop_loss_pct:   isForex ? { min: 0.05, max: 0.5, step: 0.01 } : { min: 1, max: 20, step: 0.5 },
    max_leverage:        { min: 1, max: 100, step: 1 },
    max_open_positions:  { min: 1, max: 20, step: 1 },
    cooldown_minutes:    { min: 1, max: 60, step: 1 },
  };

  const handleSliderChange = (e) => {
    const { name, value } = e.target;
    setParams(prev => ({ ...prev, [name]: parseFloat(value) }));
    setDirty(true);
  };

  const handleToggle = (key) => {
    setParams(prev => ({ ...prev, [key]: !prev[key] }));
    setDirty(true);
  };

  // ── Mode switch: fetch defaults from backend ──
  const handleModeSwitch = async (newMode) => {
    try {
      const res = await fetch(`${API_BASE}/api/parameters/defaults?mode=${newMode}`, { signal: AbortSignal.timeout(3000) });
      if (res.ok) {
        const data = await res.json();
        if (data.success && data.parameters) {
          setParams(data.parameters);
          setDirty(true);
          return;
        }
      }
    } catch (err) {
      console.error('[PARAMS] Defaults fetch error:', err);
    }
    // Fallback to local defaults
    setParams(newMode === 'forex' ? { ...FOREX_DEFAULTS } : { ...CRYPTO_DEFAULTS });
    setDirty(true);
  };

  // ── FIX #3: Save parameters (POST) ──
  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/api/parameters`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
        signal: AbortSignal.timeout(5000),
      });
      const data = await res.json();
      if (data.success) {
        setToast({ type: 'success', msg: '✅ Parameters saved & hot-reloaded' });
        setDirty(false);
      } else {
        setToast({ type: 'error', msg: `❌ Save failed: ${data.error || 'Unknown error'}` });
      }
    } catch (err) {
      setToast({ type: 'error', msg: `❌ Save failed — server unreachable` });
      console.error('[PARAMS] Save error:', err);
    } finally {
      setSaving(false);
    }
  };

  // ── FIX #5: Reset to factory defaults ──
  const handleReset = async () => {
    const mode = params.mode || 'forex';
    try {
      const res = await fetch(`${API_BASE}/api/parameters/defaults?mode=${mode}`, { signal: AbortSignal.timeout(3000) });
      if (res.ok) {
        const data = await res.json();
        if (data.success && data.parameters) {
          setParams(data.parameters);
          setDirty(true);
          setToast({ type: 'success', msg: '🔄 Reset to factory defaults — press Save to apply' });
          return;
        }
      }
    } catch (err) {
      console.error('[PARAMS] Reset fetch error:', err);
    }
    // Fallback to local defaults
    setParams(mode === 'forex' ? { ...FOREX_DEFAULTS } : { ...CRYPTO_DEFAULTS });
    setDirty(true);
    setToast({ type: 'success', msg: '🔄 Reset to defaults — press Save to apply' });
  };

  const sc = sliderConfig;

  if (loadingParams) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <Loader2 className="w-8 h-8 text-pink-500 animate-spin mx-auto mb-3" />
          <p className="text-slate-500 font-bold text-sm">Loading Parameters...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto w-full animate-fade-in">
      <div className="glass-card p-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center space-x-4">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-rose-500 to-rose-600 flex items-center justify-center shadow-lg shadow-rose-500/20">
              <Settings className="w-6 h-6 text-white" />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-white">System Parameters</h2>
              <p className="text-sm text-slate-500 mt-1">Configure trading behavior — persisted to server</p>
            </div>
          </div>
          {/* FIX #1: Connection indicator */}
          <div className="flex items-center space-x-2">
            {serverConnected ? (
              <>
                <div className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse shadow-lg shadow-emerald-400/50" />
                <span className="text-xs text-emerald-400 font-medium">Server Connected</span>
              </>
            ) : (
              <>
                <div className="w-2 h-2 bg-rose-400 rounded-full" />
                <span className="text-xs text-rose-400 font-medium">Server Disconnected</span>
              </>
            )}
          </div>
        </div>

        {/* Toast notification */}
        {toast && (
          <div className={`mb-6 p-4 rounded-2xl flex items-center space-x-3 border transition-all ${
            toast.type === 'success'
              ? 'bg-emerald-500/10 border-emerald-500/20'
              : 'bg-rose-500/10 border-rose-500/20'
          }`}>
            {toast.type === 'success'
              ? <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
              : <XCircle className="w-5 h-5 text-rose-400 shrink-0" />}
            <span className={`text-sm font-medium ${toast.type === 'success' ? 'text-emerald-400' : 'text-rose-400'}`}>
              {toast.msg}
            </span>
          </div>
        )}

        {/* Forex / Crypto Mode Toggle */}
        <div className="mb-8 flex items-center justify-center gap-2 p-1.5 bg-black/40 rounded-2xl border border-white/5">
          <button
            onClick={() => handleModeSwitch('forex')}
            className={`flex-1 py-3 rounded-xl text-sm font-black uppercase tracking-widest transition-all duration-300 ${
              isForex
                ? 'bg-gradient-to-r from-cyan-500/20 to-cyan-600/20 text-cyan-400 border border-cyan-500/40 shadow-lg shadow-cyan-500/10'
                : 'text-slate-500 hover:text-slate-300 border border-transparent'
            }`}
          >
            {"\uD83D\uDCB1"} Forex & Gold Mode
          </button>
          <button
            onClick={() => handleModeSwitch('crypto')}
            className={`flex-1 py-3 rounded-xl text-sm font-black uppercase tracking-widest transition-all duration-300 ${
              !isForex
                ? 'bg-gradient-to-r from-amber-500/20 to-orange-600/20 text-amber-400 border border-amber-500/40 shadow-lg shadow-amber-500/10'
                : 'text-slate-500 hover:text-slate-300 border border-transparent'
            }`}
          >
            {"\u20BF"} Crypto Mode
          </button>
        </div>

        {/* Mode info banner */}
        <div className={`mb-6 p-3 rounded-xl border flex items-center space-x-3 ${
          isForex ? 'bg-cyan-500/5 border-cyan-500/20' : 'bg-amber-500/5 border-amber-500/20'
        }`}>
          <span className={`text-xs font-bold uppercase tracking-wider ${isForex ? 'text-cyan-400' : 'text-amber-400'}`}>
            {isForex ? '\uD83D\uDCB1 FOREX & GOLD MODE' : '\u20BF CRYPTO MODE'}
          </span>
          <span className="text-[10px] text-slate-500">
            {isForex
              ? 'SL: 0.05–0.5% | TP: 0.05–1% | Risk: 0.5–10% — (Note: Gold automatically scales your SL/TP 2.5x wider under the hood)'
              : 'SL: 1–20% | TP: 1–50% | Risk: 1–50% — Wide ranges for volatile markets'}
          </span>
        </div>

        {/* Unsaved changes indicator */}
        {dirty && (
          <div className="mb-6 p-3 rounded-xl bg-amber-500/5 border border-amber-500/20 flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <span className="text-xs text-amber-400 font-bold">Unsaved changes — press Save Parameters to apply</span>
          </div>
        )}

        <div className="space-y-8">
          {/* ── Risk Management ── */}
          <div>
            <div className="flex items-center space-x-2 mb-4">
              <Shield className="w-5 h-5 text-rose-400" />
              <h3 className="text-lg font-semibold text-white">Risk Management</h3>
            </div>

            <div className="space-y-6">
              {/* Max Risk % */}
              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm text-slate-400">Total Max Risk %</label>
                  <span className={`font-bold ${params.max_risk_pct > (isForex ? 5 : 25) ? 'text-rose-400' : 'text-cyan-400'}`}>
                    {params.max_risk_pct}%
                  </span>
                </div>
                <input type="range" name="max_risk_pct" value={params.max_risk_pct} onChange={handleSliderChange}
                  min={sc.max_risk_pct.min} max={sc.max_risk_pct.max} step={sc.max_risk_pct.step}
                  className="w-full h-2 bg-black/40 rounded-full appearance-none cursor-pointer accent-cyan-500" />
                <p className="text-xs text-slate-500 mt-1">Maximum risk per signal block (default: {isForex ? '2%' : '10%'})</p>
                {params.max_risk_pct > (isForex ? 5 : 25) && (
                  <p className="text-xs text-rose-400 mt-1 flex items-center gap-1.5 font-bold">
                    <AlertTriangle className="w-3.5 h-3.5" /> {"\u26A0\uFE0F"} High total risk — capital exposure elevated
                  </p>
                )}
              </div>

              {/* Max Daily Drawdown % */}
              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm text-slate-400">Max Daily Drawdown % (Circuit Breaker)</label>
                  <span className="text-rose-400 font-bold">{params.max_daily_drawdown_pct}%</span>
                </div>
                <input type="range" name="max_daily_drawdown_pct" value={params.max_daily_drawdown_pct} onChange={handleSliderChange}
                  min={sc.max_daily_drawdown_pct.min} max={sc.max_daily_drawdown_pct.max} step={sc.max_daily_drawdown_pct.step}
                  className="w-full h-2 bg-black/40 rounded-full appearance-none cursor-pointer accent-rose-500" />
                <p className="text-xs text-slate-500 mt-1">Stops all trading if daily loss reaches this limit (default: 3.0%)</p>
              </div>

              {/* Max Drawdown Per Trade % */}
              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm text-slate-400">Max Drawdown Per Trade %</label>
                  <span className="text-rose-400 font-bold">{params.max_trade_drawdown_pct}%</span>
                </div>
                <input type="range" name="max_trade_drawdown_pct" value={params.max_trade_drawdown_pct} onChange={handleSliderChange}
                  min={sc.max_trade_drawdown_pct.min} max={sc.max_trade_drawdown_pct.max} step={sc.max_trade_drawdown_pct.step}
                  className="w-full h-2 bg-black/40 rounded-full appearance-none cursor-pointer accent-rose-500" />
                <p className="text-xs text-slate-500 mt-1">Hard cap on SL distance per individual position (default: 2.0%)</p>
              </div>

              {/* Base Take Profit % */}
              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm text-slate-400">Base Take Profit %</label>
                  <span className="text-emerald-400 font-bold">{params.base_take_profit_pct}%</span>
                </div>
                <input type="range" name="base_take_profit_pct" value={params.base_take_profit_pct} onChange={handleSliderChange}
                  min={sc.base_take_profit_pct.min} max={sc.base_take_profit_pct.max} step={sc.base_take_profit_pct.step}
                  className="w-full h-2 bg-black/40 rounded-full appearance-none cursor-pointer accent-emerald-500" />
                <p className="text-xs text-slate-500 mt-1">Default take profit target (default: {isForex ? '0.30%' : '6%'})</p>
              </div>

              {/* Base Stop Loss % */}
              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm text-slate-400">Base Stop Loss %</label>
                  <span className="text-rose-400 font-bold">{params.base_stop_loss_pct}%</span>
                </div>
                <input type="range" name="base_stop_loss_pct" value={params.base_stop_loss_pct} onChange={handleSliderChange}
                  min={sc.base_stop_loss_pct.min} max={sc.base_stop_loss_pct.max} step={sc.base_stop_loss_pct.step}
                  className="w-full h-2 bg-black/40 rounded-full appearance-none cursor-pointer accent-rose-500" />
                <p className="text-xs text-slate-500 mt-1">Default stop loss (default: {isForex ? '0.15% (~15 pips)' : '3%'})</p>
                {isForex && params.base_stop_loss_pct > 0.3 && (
                  <p className="text-xs text-rose-400 mt-1 flex items-center gap-1.5 font-bold">
                    <AlertTriangle className="w-3.5 h-3.5" /> {"\u26A0\uFE0F"} SL &gt; 0.3% is very wide for Forex — consider tightening
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* ── London Scalper Mode ── */}
          <div className="border-t border-white/5 pt-6">
            <div className="flex items-center space-x-2 mb-4">
              <Target className="w-5 h-5 text-fuchsia-400" />
              <h3 className="text-lg font-semibold text-white">London Scalper Mode</h3>
            </div>
            
            <div className="p-5 bg-fuchsia-900/10 border border-fuchsia-500/20 rounded-2xl space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-white font-bold">Enable Scalper Mode (Phase 2 Override)</p>
                  <p className="text-xs text-fuchsia-300/70 mt-1 max-w-sm">
                    Forces bot to fire on London sweeps using max optimized margin sizing. Take Profit is a hard dollar amount.
                  </p>
                </div>
                <button
                  onClick={() => handleToggle('scalper_mode')}
                  className={`w-14 h-7 rounded-full transition-colors flex items-center ${params.scalper_mode ? 'bg-fuchsia-500' : 'bg-slate-700'}`}
                >
                  <div className={`w-5 h-5 rounded-full bg-white transform transition-transform ${params.scalper_mode ? 'translate-x-8' : 'translate-x-1'}`} />
                </button>
              </div>

              {params.scalper_mode && (
                <div className="space-y-6 pt-4 border-t border-fuchsia-500/20">
                  <div className="bg-rose-500/10 p-3 rounded-xl border border-rose-500/30">
                    <p className="text-[11px] text-rose-300 font-bold flex items-center gap-1.5">
                      <AlertTriangle className="w-3.5 h-3.5" /> DANGER: Uses 90% of free margin! Aggressive secure-bag trailing is active.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* ── Position Settings ── */}
          <div className="border-t border-white/5 pt-6">
            <h3 className="text-lg font-semibold text-white mb-4">Position Settings</h3>

            <div className="space-y-6">
              {/* Max Leverage */}
              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm text-slate-400">Max Leverage</label>
                  <span className="text-purple-400 font-bold">{params.max_leverage}x</span>
                </div>
                <input type="range" name="max_leverage" value={params.max_leverage} onChange={handleSliderChange}
                  min="1" max="100" className="w-full h-2 bg-black/40 rounded-full appearance-none cursor-pointer accent-purple-500" />
              </div>

              {/* Max Positions Per Symbol — capped at 20 */}
              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm text-slate-400">Max Positions Per Symbol</label>
                  <span className={`font-bold ${params.max_open_positions > 10 ? 'text-rose-400' : 'text-white'}`}>
                    {params.max_open_positions}
                  </span>
                </div>
                <input type="range" name="max_open_positions" value={params.max_open_positions} onChange={handleSliderChange}
                  min="1" max="20" className="w-full h-2 bg-black/40 rounded-full appearance-none cursor-pointer accent-white" />
                <p className="text-xs text-slate-500 mt-1">Max stacking depth per individual symbol (e.g. EURUSD#)</p>
                {params.max_open_positions > 10 && (
                  <p className="text-xs text-rose-400 mt-1 flex items-center gap-1.5 font-bold">
                    <AlertTriangle className="w-3.5 h-3.5" /> {"\u26A0\uFE0F"} High per-symbol stacking increases margin risk
                  </p>
                )}
              </div>

              {/* Cooldown */}
              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm text-slate-400">Cooldown Between Trades</label>
                  <span className="text-white font-bold">{params.cooldown_minutes} min</span>
                </div>
                <input type="range" name="cooldown_minutes" value={params.cooldown_minutes} onChange={handleSliderChange}
                  min="1" max="60" className="w-full h-2 bg-black/40 rounded-full appearance-none cursor-pointer accent-white" />
              </div>
            </div>
          </div>

          {/* ── Feature Toggles ── */}
          <div className="border-t border-white/5 pt-6">
            <h3 className="text-lg font-semibold text-white mb-4">Feature Toggles</h3>

            <div className="space-y-4">
              {[
                { key: 'auto_rebalance', label: 'Auto Rebalance', desc: 'Automatically rebalance portfolio' },
                { key: 'stop_loss_enabled', label: 'Stop Loss Enabled', desc: 'Automatically close losing positions' },
                { key: 'take_profit_enabled', label: 'Take Profit Enabled', desc: 'Automatically close winning positions' },
              ].map(toggle => (
                <div key={toggle.key} className="flex items-center justify-between p-4 bg-black/30 rounded-2xl border border-white/5">
                  <div>
                    <p className="text-white font-medium">{toggle.label}</p>
                    <p className="text-xs text-slate-500">{toggle.desc}</p>
                  </div>
                  <button
                    onClick={() => handleToggle(toggle.key)}
                    className={`w-12 h-6 rounded-full transition-colors ${params[toggle.key] ? 'bg-cyan-500' : 'bg-slate-600'}`}
                  >
                    <div className={`w-5 h-5 rounded-full bg-white transform transition-transform ${params[toggle.key] ? 'translate-x-6' : 'translate-x-0.5'}`} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex space-x-4 mt-8">
          <button
            onClick={handleSave}
            disabled={saving || !serverConnected}
            className={`flex-1 font-semibold py-4 rounded-2xl transition-all flex items-center justify-center space-x-2 shadow-lg disabled:opacity-50 disabled:cursor-not-allowed ${
              serverConnected
                ? 'bg-gradient-to-r from-cyan-500 to-cyan-600 hover:from-cyan-400 hover:to-cyan-500 text-white shadow-cyan-500/20'
                : 'bg-slate-700 text-slate-400 shadow-none'
            }`}
            title={!serverConnected ? 'Server disconnected — cannot save' : ''}
          >
            {saving ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Save className="w-5 h-5" />
            )}
            <span>{saving ? 'Saving...' : !serverConnected ? 'Server Offline' : 'Save Parameters'}</span>
          </button>

          <button
            onClick={handleReset}
            className="px-6 bg-white/5 hover:bg-white/10 text-slate-400 font-semibold py-4 rounded-2xl transition-all flex items-center space-x-2"
          >
            <RotateCcw className="w-5 h-5" />
            <span>Reset</span>
          </button>
        </div>

        {/* Server sync info */}
        <div className="mt-4 text-center">
          <p className="text-[10px] text-slate-600">
            Parameters persist to <span className="font-mono text-slate-500">~/.apex_trader/apex_parameters.json</span>
            {' '} — hot-reloaded on save, no restart required
          </p>
        </div>
      </div>
    </div>
  );
};

export default SystemParameters;
