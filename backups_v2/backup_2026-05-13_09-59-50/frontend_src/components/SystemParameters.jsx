import React, { useState } from 'react';
import { Settings, Save, RotateCcw, Shield, AlertTriangle, CheckCircle2 } from 'lucide-react';

const SystemParameters = ({ wsConnected }) => {
  const [params, setParams] = useState({
    maxRiskPercent: 10,
    baseTpPercent: 6,
    baseSlPercent: 3,
    maxLeverage: 10,
    maxOpenPositions: 999,
    cooldownMinutes: 15,
    autoRebalance: true,
    stopLossEnabled: true,
    takeProfitEnabled: true
  });

  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSliderChange = (e) => {
    const { name, value } = e.target;
    setParams(prev => ({
      ...prev,
      [name]: parseInt(value)
    }));
    setSaved(false);
  };

  const handleToggle = (key) => {
    setParams(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
    setSaved(false);
  };

  const handleSave = async () => {
    setLoading(true);
    await new Promise(resolve => setTimeout(resolve, 1000));
    setLoading(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  const handleReset = () => {
    setParams({
      maxRiskPercent: 10,
      baseTpPercent: 6,
      baseSlPercent: 3,
      maxLeverage: 10,
      maxOpenPositions: 999,
      cooldownMinutes: 15,
      autoRebalance: true,
      stopLossEnabled: true,
      takeProfitEnabled: true
    });
    setSaved(false);
  };

  return (
    <div className="max-w-4xl mx-auto w-full">
      <div className="glass-card p-8">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center space-x-4">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-rose-500 to-rose-600 flex items-center justify-center shadow-lg shadow-rose-500/20">
              <Settings className="w-6 h-6 text-white" />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-white">System Parameters</h2>
              <p className="text-sm text-slate-500 mt-1">Configure trading behavior</p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            {wsConnected ? (
              <>
                <div className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse shadow-lg shadow-emerald-400/50"></div>
                <span className="text-xs text-emerald-400 font-medium">Server Connected</span>
              </>
            ) : (
              <>
                <div className="w-2 h-2 bg-rose-400 rounded-full"></div>
                <span className="text-xs text-rose-400 font-medium">Server Disconnected</span>
              </>
            )}
          </div>
        </div>

        {saved && (
          <div className="mb-6 p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-2xl flex items-center space-x-3">
            <CheckCircle2 className="w-5 h-5 text-emerald-400" />
            <span className="text-emerald-400 text-sm">Parameters saved successfully!</span>
          </div>
        )}

        <div className="space-y-8">
          <div>
            <div className="flex items-center space-x-2 mb-4">
              <Shield className="w-5 h-5 text-rose-400" />
              <h3 className="text-lg font-semibold text-white">Risk Management</h3>
            </div>
            
            <div className="space-y-6">
              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm text-slate-400">Max Risk %</label>
                  <span className="text-cyan-400 font-bold">{params.maxRiskPercent}%</span>
                </div>
                <input
                  type="range"
                  name="maxRiskPercent"
                  value={params.maxRiskPercent}
                  onChange={handleSliderChange}
                  min="1"
                  max="50"
                  className="w-full h-2 bg-black/40 rounded-full appearance-none cursor-pointer accent-cyan-500"
                />
                <p className="text-xs text-slate-500 mt-1">Maximum risk per trade (default: 10%)</p>
              </div>

              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm text-slate-400">Base Take Profit %</label>
                  <span className="text-emerald-400 font-bold">{params.baseTpPercent}%</span>
                </div>
                <input
                  type="range"
                  name="baseTpPercent"
                  value={params.baseTpPercent}
                  onChange={handleSliderChange}
                  min="1"
                  max="50"
                  className="w-full h-2 bg-black/40 rounded-full appearance-none cursor-pointer accent-emerald-500"
                />
                <p className="text-xs text-slate-500 mt-1">Default take profit target (default: 6%)</p>
              </div>

              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm text-slate-400">Base Stop Loss %</label>
                  <span className="text-rose-400 font-bold">{params.baseSlPercent}%</span>
                </div>
                <input
                  type="range"
                  name="baseSlPercent"
                  value={params.baseSlPercent}
                  onChange={handleSliderChange}
                  min="1"
                  max="999"
                  className="w-full h-2 bg-black/40 rounded-full appearance-none cursor-pointer accent-rose-500"
                />
                <p className="text-xs text-slate-500 mt-1">Default stop loss (default: 3%)</p>
              </div>
            </div>
          </div>

          <div className="border-t border-white/5 pt-6">
            <h3 className="text-lg font-semibold text-white mb-4">Position Settings</h3>
            
            <div className="space-y-6">
              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm text-slate-400">Max Leverage</label>
                  <span className="text-purple-400 font-bold">{params.maxLeverage}x</span>
                </div>
                <input
                  type="range"
                  name="maxLeverage"
                  value={params.maxLeverage}
                  onChange={handleSliderChange}
                  min="1"
                  max="100"
                  className="w-full h-2 bg-black/40 rounded-full appearance-none cursor-pointer accent-purple-500"
                />
              </div>

              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm text-slate-400">Max Open Positions</label>
                  <span className="text-white font-bold">{params.maxOpenPositions}</span>
                </div>
                <input
                  type="range"
                  name="maxOpenPositions"
                  value={params.maxOpenPositions}
                  onChange={handleSliderChange}
                  min="1"
                  max="999"
                  className="w-full h-2 bg-black/40 rounded-full appearance-none cursor-pointer accent-white"
                />
              </div>

              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm text-slate-400">Cooldown Between Trades</label>
                  <span className="text-white font-bold">{params.cooldownMinutes} min</span>
                </div>
                <input
                  type="range"
                  name="cooldownMinutes"
                  value={params.cooldownMinutes}
                  onChange={handleSliderChange}
                  min="1"
                  max="60"
                  className="w-full h-2 bg-black/40 rounded-full appearance-none cursor-pointer accent-white"
                />
              </div>
            </div>
          </div>

          <div className="border-t border-white/5 pt-6">
            <h3 className="text-lg font-semibold text-white mb-4">Feature Toggles</h3>
            
            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-black/40/30 rounded-2xl border border-white/5">
                <div>
                  <p className="text-white font-medium">Auto Rebalance</p>
                  <p className="text-xs text-slate-500">Automatically rebalance portfolio</p>
                </div>
                <button
                  onClick={() => handleToggle('autoRebalance')}
                  className={`w-12 h-6 rounded-full transition-colors ${params.autoRebalance ? 'bg-cyan-500' : 'bg-slate-600'}`}
                >
                  <div className={`w-5 h-5 rounded-full bg-white transform transition-transform ${params.autoRebalance ? 'translate-x-6' : 'translate-x-0.5'}`}></div>
                </button>
              </div>

              <div className="flex items-center justify-between p-4 bg-black/40/30 rounded-2xl border border-white/5">
                <div>
                  <p className="text-white font-medium">Stop Loss Enabled</p>
                  <p className="text-xs text-slate-500">Automatically close losing positions</p>
                </div>
                <button
                  onClick={() => handleToggle('stopLossEnabled')}
                  className={`w-12 h-6 rounded-full transition-colors ${params.stopLossEnabled ? 'bg-cyan-500' : 'bg-slate-600'}`}
                >
                  <div className={`w-5 h-5 rounded-full bg-white transform transition-transform ${params.stopLossEnabled ? 'translate-x-6' : 'translate-x-0.5'}`}></div>
                </button>
              </div>

              <div className="flex items-center justify-between p-4 bg-black/40/30 rounded-2xl border border-white/5">
                <div>
                  <p className="text-white font-medium">Take Profit Enabled</p>
                  <p className="text-xs text-slate-500">Automatically close winning positions</p>
                </div>
                <button
                  onClick={() => handleToggle('takeProfitEnabled')}
                  className={`w-12 h-6 rounded-full transition-colors ${params.takeProfitEnabled ? 'bg-cyan-500' : 'bg-slate-600'}`}
                >
                  <div className={`w-5 h-5 rounded-full bg-white transform transition-transform ${params.takeProfitEnabled ? 'translate-x-6' : 'translate-x-0.5'}`}></div>
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="flex space-x-4 mt-8">
          <button
            onClick={handleSave}
            disabled={loading}
            className="flex-1 bg-gradient-to-r from-cyan-500 to-cyan-600 hover:from-cyan-400 hover:to-cyan-500 text-white font-semibold py-4 rounded-2xl transition-all flex items-center justify-center space-x-2 shadow-lg shadow-cyan-500/20 disabled:opacity-50"
          >
            {loading ? (
              <RotateCcw className="w-5 h-5 animate-spin" />
            ) : (
              <Save className="w-5 h-5" />
            )}
            <span>Save Parameters</span>
          </button>
          
          <button
            onClick={handleReset}
            className="px-6 bg-white/5 hover:bg-white/10 text-slate-400 font-semibold py-4 rounded-2xl transition-all flex items-center space-x-2"
          >
            <RotateCcw className="w-5 h-5" />
            <span>Reset</span>
          </button>
        </div>
      </div>
    </div>
  );
};

export default SystemParameters;
