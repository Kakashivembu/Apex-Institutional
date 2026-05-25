import React, { useState, useEffect } from 'react';
import {
  Key, Plus, Trash2, AlertCircle,
  CheckCircle2, Loader2, Cpu, MessageSquare, Database, Target, TrendingUp
} from 'lucide-react';
import { API_BASE } from '../lib/api';

const API_BASE_URL = API_BASE;

const AI_ROLES = [
  { id: 'chat', label: 'Chat AI', icon: MessageSquare, description: 'Powers the UI Command Center Chat', color: 'indigo' },
  { id: 'fundamental', label: 'Fundamental Desk AI', icon: Database, description: 'Macro/Claw contextual analysis', color: 'purple' },
  { id: 'scalper', label: 'Scalper AI', icon: Target, description: 'Short-term execution logic', color: 'amber' },
  { id: 'trend', label: 'Trend Follower AI', icon: TrendingUp, description: 'Long-term position sizing', color: 'emerald' },
];

const MT5_SERVERS = [
  // XMGlobal (all known servers)
  'XMGlobal-MT5 2',
  'XMGlobal-MT5 3',
  'XMGlobal-MT5 4',
  'XMGlobal-MT5 5',
  'XMGlobal-MT5 6',
  'XMGlobal-MT5 7',
  'XMGlobal-MT5 8',
  'XMGlobal-MT5 9',
  'XMGlobal-MT5 10',
  'XMGlobal-MT5 11',
  'XMGlobal-MT5 12',
  'XMGlobal-MT5 13',
  'XMGlobal-MT5 14',
  'XMGlobal-MT5 15',
  'XMGlobal-MT5 16',
  'XMGlobal-MT5 17',
  'XMGlobal-MT5 18',
  // GoatFunded
  'GoatFunded-Server',
  'GoatFunded-Server2',
  'GoatFunded-Server3',
  // ICMarkets
  'ICMarketsSC-MT5-2',
  'ICMarketsSC-MT5-4',
  // Exness
  'Exness-MT5Real',
  'Exness-MT5Real2',
  'Exness-MT5Trial',
  // Pepperstone
  'Pepperstone-Edge05',
  'Pepperstone-Edge08',
  // FTMO
  'FTMO-Server3',
  'FTMO-Server4',
  // Eightcap
  'Eightcap-Live',
  'Eightcap-Demo',
  // RoboForex
  'RoboForex-ECN',
  'RoboForex-Pro',
  // Vantage
  'VantageInternational-Live 1',
  'VantageInternational-Demo',
  // BlackBull
  'BlackBullMarkets-Live',
  'BlackBullMarkets-Demo',
  // FPMarkets
  'FPMarkets-Live',
  'FPMarkets-Demo',
  // Custom entry
  '__CUSTOM__',
];

const ApiFleetManager = ({ wsConnected }) => {
  // Exchange State
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // AI State
  const [aiKeys, setAiKeys] = useState({});
  const [aiLoading, setAiLoading] = useState(true);
  const [aiSubmitting, setAiSubmitting] = useState(false);
  const [editAiRole, setEditAiRole] = useState(null);
  const [newAiKey, setNewAiKey] = useState('');
  // FIX #4: AI key health status
  const [aiKeyStatus, setAiKeyStatus] = useState({});
  const [customServer, setCustomServer] = useState('');

  const [formData, setFormData] = useState({
    account_name: '',
    api_key: '',
    api_secret: '',
    network: MT5_SERVERS[0]
  });

  useEffect(() => {
    fetchKeys();
    fetchAiKeys();
    fetchAiKeyStatus();
    // FIX #4: Poll AI key status every 60 seconds
    const statusInterval = setInterval(fetchAiKeyStatus, 60_000);
    return () => clearInterval(statusInterval);
  }, []);

  const fetchKeys = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/keys`);
      if (response.ok) {
        const data = await response.json();
        setKeys(data.keys || []);
      } else {
        setKeys([]);
      }
    } catch (err) {
      console.error('Error fetching keys:', err);
      setKeys([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchAiKeys = async () => {
    setAiLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/ai-keys`);
      if (response.ok) {
        const data = await response.json();
        setAiKeys(data.keys || {});
      }
    } catch (err) {
      console.error('Error fetching AI keys:', err);
    } finally {
      setAiLoading(false);
    }
  };

  // FIX #4: Fetch AI key health status
  const fetchAiKeyStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/ai-keys/status`);
      if (response.ok) {
        const data = await response.json();
        setAiKeyStatus(data.status || {});
      }
    } catch (err) {
      console.error('Error fetching AI key status:', err);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    // Resolve the actual server name (custom or dropdown)
    const resolvedNetwork = formData.network === '__CUSTOM__' ? customServer.trim() : formData.network;
    if (!resolvedNetwork) {
      setError('Please enter a custom MT5 server name');
      return;
    }

    setSubmitting(true);
    const payload = { ...formData, network: resolvedNetwork };

    try {
      const response = await fetch(`${API_BASE_URL}/api/keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        setSuccess(`Account "${formData.account_name}" added to fleet successfully!`);
        setFormData({ account_name: '', api_key: '', api_secret: '', network: MT5_SERVERS[0] });
        setCustomServer('');
        fetchKeys();
      } else {
        const data = await response.json();
        setError(data.detail || 'Failed to add API key');
      }
    } catch (err) {
      setError('Failed to connect to server');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (accountName) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/keys?account_name=${encodeURIComponent(accountName)}`, { method: 'DELETE' });
      if (response.ok) {
        setSuccess(`Account "${accountName}" removed from fleet`);
        fetchKeys();
      } else {
        setError('Failed to delete API key');
      }
    } catch (err) {
      setError('Failed to connect to server');
    }
  };

  const handleLogin = async (accountName) => {
    try {
      setSuccess(`Attempting to login to MT5 as ${accountName}...`);
      const response = await fetch(`${API_BASE_URL}/api/mt5/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_name: accountName })
      });
      const data = await response.json();
      if (data.success) {
        setSuccess(data.message);
      } else {
        setError(data.error || 'Failed to login to MT5');
      }
    } catch (err) {
      setError('Failed to connect to server');
    }
  };

  const handleUpdateMode = async (accountName, newMode) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/keys/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_name: accountName, mode: newMode })
      });
      const data = await response.json();
      if (data.success) {
        setSuccess(`Account "${accountName}" mode updated to ${newMode.toUpperCase()}`);
        fetchKeys();
      } else {
        setError(data.error || 'Failed to update trading mode');
      }
    } catch (err) {
      setError('Failed to connect to server');
    }
  };

  const handleAiSubmit = async (role) => {
    if (!newAiKey) return;
    setAiSubmitting(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/ai-keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role, key: newAiKey }),
      });
      if (response.ok) {
        setSuccess(`AI Key for "${role}" instantly injected into memory & .env`);
        setNewAiKey('');
        setEditAiRole(null);
        fetchAiKeys();
      } else {
        setError('Failed to update AI key');
      }
    } catch (err) {
      setError('Failed to connect to server');
    } finally {
      setAiSubmitting(false);
    }
  };

  const handleAiDelete = async (role) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/ai-keys?role=${role}`, { method: 'DELETE' });
      if (response.ok) {
        setSuccess(`AI Key for "${role}" deleted from memory & .env`);
        fetchAiKeys();
      } else {
        setError('Failed to delete AI key');
      }
    } catch (err) {
      setError('Failed to connect to server');
    }
  };

  return (
    <div className="max-w-6xl mx-auto w-full grid grid-cols-1 lg:grid-cols-2 gap-8">

      {/* LEFT PANEL: MT5 Execution Bridge */}
      <div className="glass-card p-8">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center space-x-4">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-cyan-500 to-cyan-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
              <Key className="w-6 h-6 text-white" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">MT5 Execution Bridge</h2>
              <p className="text-xs text-slate-500 mt-1">Stored securely in SQLite DB</p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            {wsConnected ? (
              <><div className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse shadow-lg shadow-emerald-400/50"></div><span className="text-[10px] text-emerald-400 font-medium">Online</span></>
            ) : (
              <><div className="w-2 h-2 bg-rose-400 rounded-full"></div><span className="text-[10px] text-rose-400 font-medium">Offline</span></>
            )}
          </div>
        </div>

        {error && <div className="mb-4 p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl flex items-center space-x-3"><AlertCircle className="w-4 h-4 text-rose-400" /><span className="text-rose-400 text-xs">{error}</span></div>}
        {success && <div className="mb-4 p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl flex items-center space-x-3"><CheckCircle2 className="w-4 h-4 text-emerald-400" /><span className="text-emerald-400 text-xs">{success}</span></div>}

        <form onSubmit={handleSubmit} className="mb-8 border border-white/5 bg-black/20 p-4 rounded-2xl">
          <div className="space-y-4">
            <div className="flex space-x-4">
              <div className="flex-1 space-y-1">
                <label className="text-[10px] text-slate-400 uppercase tracking-wider">Account Name</label>
                <input type="text" name="account_name" value={formData.account_name} onChange={handleInputChange} required className="w-full bg-black/40 border border-white/10 rounded-xl py-2 px-3 text-sm text-white focus:border-cyan-500/50 outline-none" />
              </div>
              <div className="flex-1 space-y-1">
                <label className="text-[10px] text-slate-400 uppercase tracking-wider">MT5 Server Name</label>
                <select
                  name="network"
                  value={formData.network}
                  onChange={handleInputChange}
                  required
                  className="w-full bg-black/40 border border-white/10 rounded-xl py-2 px-3 text-sm text-white focus:border-cyan-500/50 outline-none"
                >
                  {MT5_SERVERS.map((server) => (
                    <option key={server} value={server} className="bg-slate-900 text-white">
                      {server === '__CUSTOM__' ? '✏️ Custom Server...' : server}
                    </option>
                  ))}
                </select>
                {formData.network === '__CUSTOM__' && (
                  <input
                    type="text"
                    placeholder="Type exact MT5 server name (e.g. XMGlobal-MT5 14)"
                    value={customServer}
                    onChange={(e) => setCustomServer(e.target.value)}
                    required
                    className="w-full mt-2 bg-black/40 border border-amber-500/30 rounded-xl py-2 px-3 text-sm text-amber-300 focus:border-amber-400/60 outline-none placeholder-slate-600"
                  />
                )}
              </div>
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-slate-400 uppercase tracking-wider">MT5 Account ID (Numbers Only)</label>
              <input type="text" name="api_key" value={formData.api_key} onChange={handleInputChange} required className="w-full bg-black/40 border border-white/10 rounded-xl py-2 px-3 text-sm text-white focus:border-cyan-500/50 outline-none" />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-slate-400 uppercase tracking-wider">MT5 Password</label>
              <input type="password" name="api_secret" value={formData.api_secret} onChange={handleInputChange} required className="w-full bg-black/40 border border-white/10 rounded-xl py-2 px-3 text-sm text-white focus:border-cyan-500/50 outline-none" />
            </div>
          </div>
          <button type="submit" disabled={submitting} className="mt-4 w-full bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 border border-cyan-500/30 font-medium py-2 rounded-xl transition-all text-sm flex items-center justify-center space-x-2">
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Plus className="w-4 h-4" /><span>Add MT5 Account</span></>}
          </button>
        </form>

        <div className="space-y-3">
          {loading ? (
            <div className="flex items-center justify-center py-8"><Loader2 className="w-6 h-6 text-cyan-400 animate-spin" /></div>
          ) : keys.map((key, index) => (
            <div key={index} className="border border-white/5 bg-white/[0.02] rounded-xl p-4 flex items-center justify-between">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-semibold text-white text-sm">{key.account_name}</span>
                  <span className="text-[9px] bg-white/10 px-2 py-0.5 rounded-full text-slate-400 uppercase">{key.network}</span>
                  
                  <select 
                    value={key.trading_mode || 'challenge'}
                    onChange={(e) => handleUpdateMode(key.account_name, e.target.value)}
                    className="ml-2 bg-black/40 border border-white/10 rounded-lg py-0.5 px-2 text-[10px] text-white focus:border-cyan-500/50 outline-none uppercase tracking-wide"
                  >
                    <option value="challenge" className="bg-slate-900 text-white">Challenge</option>
                    <option value="realmoney" className="bg-slate-900 text-white">Real Money</option>
                    <option value="competition" className="bg-slate-900 text-white">Competition</option>
                  </select>
                </div>
                <div className="text-xs font-mono text-slate-500 mt-1">Key: {key.api_key?.substring(0, 10)}...</div>
              </div>
              <div className="flex items-center space-x-2">
                <button onClick={() => handleLogin(key.account_name)} className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wide bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/20 rounded-lg transition-colors">
                  Login to MT5
                </button>
                <button onClick={() => handleDelete(key.account_name)} className="p-2 text-rose-400 hover:bg-rose-400/10 rounded-lg transition-colors" title="Delete Account">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* RIGHT PANEL: AI Brain Keys */}
      <div className="glass-card p-8 bg-gradient-to-br from-indigo-900/10 to-transparent">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center space-x-4">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <Cpu className="w-6 h-6 text-white" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">AI Brain Fleet</h2>
              <p className="text-xs text-indigo-400 mt-1">Stored safely in .env & instantly hot-reloaded</p>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          {aiLoading ? (
            <div className="flex items-center justify-center py-8"><Loader2 className="w-6 h-6 text-indigo-400 animate-spin" /></div>
          ) : AI_ROLES.map((role) => {
            const Icon = role.icon;
            const currentKey = aiKeys[role.id];
            const isEditing = editAiRole === role.id;

            return (
              <div key={role.id} className={`border border-${role.color}-500/20 bg-${role.color}-500/5 rounded-2xl p-4 transition-all ${isEditing ? `ring-1 ring-${role.color}-500/50` : ''}`}>
                <div className="flex items-start justify-between">
                  <div className="flex space-x-3">
                    <div className={`w-8 h-8 rounded-lg bg-${role.color}-500/20 flex items-center justify-center shrink-0`}>
                      <Icon className={`w-4 h-4 text-${role.color}-400`} />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-white">{role.label}</h3>
                      <p className="text-[10px] text-slate-400 mt-0.5">{role.description}</p>
                    </div>
                  </div>
                  {!isEditing && (
                    <div className="flex items-center space-x-2">
                      <button onClick={() => setEditAiRole(role.id)} className={`text-[10px] px-3 py-1 bg-${role.color}-500/20 hover:bg-${role.color}-500/30 text-${role.color}-300 rounded-lg transition-colors`}>
                        {currentKey ? 'Update Key' : 'Inject Key'}
                      </button>
                      {currentKey && (
                        <button onClick={() => handleAiDelete(role.id)} className="p-1 text-rose-400 hover:bg-rose-400/10 rounded transition-colors" title="Delete Key from .env">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  )}
                </div>

                {!isEditing && currentKey && (
                  <div className="mt-3 bg-black/40 rounded-lg py-2 px-3 border border-white/5 flex items-center justify-between">
                    <span className="font-mono text-xs text-slate-500 tracking-wider flex-1 overflow-hidden truncate">
                      {currentKey}
                    </span>
                    <CheckCircle2 className={`w-3.5 h-3.5 text-${role.color}-400 ml-2`} />
                  </div>
                )}

                {/* FIX #4: AI Key Auth Status Indicator */}
                {!isEditing && currentKey && (() => {
                  const status = aiKeyStatus[role.id];
                  if (!status) return null;
                  const statusCode = status.status_code || 0;
                  const isOk = statusCode === 200 || status.status === 'ok';
                  const isRateLimited = statusCode === 429;
                  const isAuthFailed = statusCode === 401 || statusCode === 403;
                  return (
                    <div className="mt-2 flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${
                        isOk ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)] animate-pulse'
                        : isRateLimited ? 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.8)]'
                        : isAuthFailed ? 'bg-rose-400 shadow-[0_0_6px_rgba(244,63,94,0.8)]'
                        : 'bg-slate-500'
                      }`} />
                      <span className={`text-[10px] font-bold uppercase tracking-wider ${
                        isOk ? 'text-emerald-400'
                        : isRateLimited ? 'text-amber-400'
                        : isAuthFailed ? 'text-rose-400'
                        : 'text-slate-500'
                      }`}>
                        {isOk ? 'Authenticated'
                        : isRateLimited ? 'Rate Limited (429)'
                        : isAuthFailed ? 'Auth Failed'
                        : `Status: ${statusCode}`}
                      </span>
                      {isAuthFailed && (
                        <span className="px-2 py-0.5 bg-rose-500/20 text-rose-400 text-[9px] font-black rounded-lg border border-rose-500/30">
                          AUTH FAILED
                        </span>
                      )}
                      {status.last_checked && (
                        <span className="text-[9px] text-slate-600 ml-auto">
                          {new Date(status.last_checked).toLocaleTimeString()}
                        </span>
                      )}
                    </div>
                  );
                })()}

                {!isEditing && !currentKey && (
                  <div className="mt-3 bg-black/20 rounded-lg py-2 px-3 border border-dashed border-rose-500/30 flex items-center space-x-2">
                    <AlertCircle className="w-3 h-3 text-rose-400" />
                    <span className="text-[10px] text-rose-400">Offline: Key Missing</span>
                  </div>
                )}

                {isEditing && (
                  <div className="mt-4 flex items-center space-x-2">
                    <input
                      type="password"
                      placeholder="Paste strictly valid API Key (e.g. nvapi-...)"
                      value={newAiKey}
                      onChange={(e) => setNewAiKey(e.target.value)}
                      className={`flex-1 bg-black/60 border border-${role.color}-500/30 rounded-lg py-2 px-3 text-xs text-white outline-none focus:border-${role.color}-400`}
                    />
                    <button
                      onClick={() => handleAiSubmit(role.id)}
                      disabled={aiSubmitting || !newAiKey}
                      className={`px-3 py-2 bg-${role.color}-500 hover:bg-${role.color}-400 text-white text-xs font-medium rounded-lg transition-colors flex items-center disabled:opacity-50`}
                    >
                      {aiSubmitting ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Save & Hot-Reload'}
                    </button>
                    <button
                      onClick={() => { setEditAiRole(null); setNewAiKey(''); }}
                      className="px-3 py-2 bg-white/5 hover:bg-white/10 text-slate-400 text-xs font-medium rounded-lg transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

    </div>
  );
};

export default ApiFleetManager;
