import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  LayoutDashboard,
  BarChart3,
  Database,
  Key,
  Settings,
  TrendingUp,
  Activity,
  Zap,
  Wifi,
  WifiOff,
  RefreshCw,
  ArrowUpRight,
  ArrowDownRight,
  Wallet,
  Layers,
  Shield,
  ShieldOff,
  AlertTriangle,
  Terminal,
  Cpu,
  Search,
  MessageSquare
} from 'lucide-react';
import TradingCommandCenter from './components/TradingCommandCenter';
import ApiFleetManager from './components/ApiFleetManager';
import BacktestEngine from './components/BacktestEngine';
import HyperOptimizer from './components/HyperOptimizer';
import ClawFundamentalDesk from './components/ClawFundamentalDesk';
import SystemParameters from './components/SystemParameters';
import LiveTerminal from './components/LiveTerminal';
import FluidBackground from './components/FluidBackground';
import BotPerformance from './components/BotPerformance';
import ChatBox from './components/ChatBox';
import { API_BASE, WS_URL } from './lib/api';

// =============================================================================
// RISK STATUS BANNER COMPONENT
// =============================================================================
const RiskStatusBanner = ({ 
  killswitchActive, 
  killswitchReason, 
  circuitBreaker, 
  circuitReason,
  drawdownPct,
  timeUntilReset 
}) => {
  // Circuit breaker override state (hooks must be at top level)
  const [resetting, setResetting] = React.useState(false);
  const [resetSuccess, setResetSuccess] = React.useState(false);

  const handleForceReset = async () => {
    if (resetting) return;
    setResetting(true);
    try {
      const res = await fetch(`${API_BASE}/api/circuit-breaker/reset`, { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        setResetSuccess(true);
        setTimeout(() => setResetSuccess(false), 3000);
      }
    } catch (err) {
      console.error('[CIRCUIT BREAKER] Reset failed:', err);
    } finally {
      setResetting(false);
    }
  };

  // Determine status
  const isCircuitBreaker = circuitBreaker;
  const isKillswitch = killswitchActive && !circuitBreaker;
  const isSafe = !killswitchActive && !circuitBreaker;
  
  if (isSafe) {
    // Green - System Armed
    return (
      <div className="bg-emerald-500/10 border-y border-emerald-500/30 px-4 py-2">
        <div className="flex items-center justify-center space-x-3">
          <div className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" />
          <span className="text-sm font-bold text-emerald-400">SYSTEM ARMED</span>
          <span className="text-slate-400">|</span>
          <span className="text-sm text-emerald-300">NO HIGH-IMPACT NEWS</span>
          <Shield className="w-4 h-4 text-emerald-400" />
        </div>
      </div>
    );
  }
  
  if (isCircuitBreaker) {
    // Red - Circuit Breaker Tripped — with manual override button
    if (resetSuccess) {
      return (
        <div className="bg-emerald-500/15 border-y border-emerald-500/40 px-4 py-3">
          <div className="flex items-center justify-center space-x-3">
            <div className="w-3 h-3 bg-emerald-400 rounded-full animate-ping" />
            <span className="text-base font-bold text-emerald-400">✅ CIRCUIT BREAKER RESET — SWARM RE-ARMED</span>
          </div>
        </div>
      );
    }

    return (
      <div className="bg-rose-500/15 border-y border-rose-500/40 px-4 py-3 animate-pulse">
        <div className="flex flex-col sm:flex-row items-center justify-center space-y-2 sm:space-y-0 sm:space-x-4">
          <div className="flex items-center space-x-3">
            <div className="w-3 h-3 bg-rose-500 rounded-full animate-ping" />
            <span className="text-base font-bold text-rose-400">🛑 CIRCUIT BREAKER TRIPPED</span>
          </div>
          <span className="text-slate-500 hidden sm:inline">|</span>
          <span className="text-sm text-rose-300 text-center">
            MAX DAILY DRAWDOWN ({drawdownPct}%) REACHED
          </span>
          <span className="text-slate-500 hidden sm:inline">|</span>
          <span className="text-sm text-rose-200">
            HALTED ({timeUntilReset})
          </span>
          <span className="text-slate-500 hidden sm:inline">|</span>
          <button
            onClick={handleForceReset}
            disabled={resetting}
            className={`relative group shrink-0 px-4 py-1.5 rounded-lg text-xs font-black uppercase tracking-wider transition-all duration-300 border-2 ${
              resetting
                ? 'border-slate-600 bg-slate-800/50 text-slate-500 cursor-wait'
                : 'border-orange-500/70 bg-gradient-to-r from-orange-600/20 to-rose-600/20 text-orange-300 hover:from-orange-600/40 hover:to-rose-600/40 hover:text-orange-200 hover:border-orange-400 hover:shadow-lg hover:shadow-orange-500/20 cursor-pointer'
            }`}
          >
            {/* Pulsing ring */}
            {!resetting && (
              <span className="absolute inset-0 rounded-lg border-2 border-orange-400/40 animate-ping pointer-events-none" />
            )}
            <span className="relative flex items-center space-x-1.5">
              <span>{resetting ? '⏳' : '⚡'}</span>
              <span>{resetting ? 'RESETTING...' : 'FORCE RESET'}</span>
            </span>
          </button>
        </div>
      </div>
    );
  }
  
  if (isKillswitch) {
    // Yellow/Orange - Killswitch Active
    return (
      <div className="bg-amber-500/15 border-y border-amber-500/40 px-4 py-3">
        <div className="flex flex-col sm:flex-row items-center justify-center space-y-2 sm:space-y-0 sm:space-x-4">
          <div className="flex items-center space-x-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 animate-pulse" />
            <span className="text-base font-bold text-amber-400">⚠️ NEWS SHIELD ACTIVE</span>
          </div>
          <span className="text-slate-500 hidden sm:inline">|</span>
          <span className="text-sm text-amber-300 text-center max-w-md truncate">
            {killswitchReason || 'High-impact macroeconomic event detected'}
          </span>
          <span className="text-slate-500 hidden sm:inline">|</span>
          <span className="text-sm text-amber-200">TRADING HALTED</span>
        </div>
      </div>
    );
  }
  
  return null;
};

const ACTIVE_TAB_STORAGE_KEY = 'apex.activeTab';
const USDT_TO_INR = 85;
const MT5_SPREAD_FEE_ESTIMATE = 0.0; // MT5 PnL typically includes spread
const MT5_CONTRACT_MULTIPLIER = 1.0;

const App = () => {
  const [activeTab, setActiveTab] = useState(() => localStorage.getItem(ACTIVE_TAB_STORAGE_KEY) || 'dashboard');
  const [wsConnected, setWsConnected] = useState(false);
  const [wsMessage, setWsMessage] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [error, setError] = useState(null);
  const [systemInfo, setSystemInfo] = useState(null);
  const [tradingEnabled, setTradingEnabled] = useState(false);
  const [mountedTabs, setMountedTabs] = useState(['dashboard']);
  const [selectedAccount, setSelectedAccount] = useState('fleet');

  // Accumulated terminal logs (survives across WebSocket broadcasts)
  const [accumulatedLogs, setAccumulatedLogs] = useState([]);
  const logCursorRef = useRef(0);

  // Real-time data from WebSocket
  const [marketData, setMarketData] = useState({
    swarm_decisions: [],
    positions: [],
    macro_matrix: {},
    tick_velocity: {},
    equity: { total: 0, daily_pnl: 0, daily_change_pct: 0 },
    consensus: { direction: 'HOLD', strength: 0 },
    margin: { available_margin: 0, total_balance: 0, used_margin: 0, unrealized_pnl: 0, currency: 'USD' },
    nvidia_api_stats: { rpm: 0, rpm_limit: 40, calls_total: 0, last_call: 0 },
    server_logs: [],
    // Risk management state
    killswitch_active: false,
    killswitch_reason: '',
    circuit_breaker: false,
    circuit_reason: '',
    drawdown_pct: 0.0,
    time_until_reset: ''
  });

  // Fetch system info on component mount
  useEffect(() => {
    const fetchSystemInfo = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/system-info`);
        const data = await response.json();
        setSystemInfo(data);
      } catch (err) {
        console.error('Failed to fetch system info:', err);
      }
    };

    fetchSystemInfo();
  }, []);

  useEffect(() => {
    localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, activeTab);
    setMountedTabs((prev) => (prev.includes(activeTab) ? prev : [...prev, activeTab]));
  }, [activeTab]);
  
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const shouldReconnectRef = useRef(true);

  const refreshData = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'get_state' }));
    }
  };

  const toggleTrading = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/trading/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !tradingEnabled })
      });
      const data = await res.json();
      if (data.success !== false) setTradingEnabled(data.trading_enabled);
    } catch (e) {
      console.error('[TRADING] Toggle failed:', e);
    }
  };

  useEffect(() => {
    fetch(`${API_BASE}/api/trading/status`)
      .then(r => r.json())
      .then(d => setTradingEnabled(d.trading_enabled === true))
      .catch(() => {});
  }, []);

  const connectWebSocketRef = useRef(null);
  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN || wsRef.current?.readyState === WebSocket.CONNECTING) return;
    try {
      wsRef.current = new WebSocket(WS_URL);
      wsRef.current.onopen = () => {
        setWsConnected(true);
        setLastUpdate(new Date());
        wsRef.current.send(JSON.stringify({ type: 'get_state' }));
      };
      wsRef.current.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          setWsMessage(message);
          if (message.type === 'market_update') {
            const newLogs = message.data.server_logs || [];
            if (newLogs.length > 0) {
              setAccumulatedLogs(prev => {
                const existingIds = new Set(prev.map(l => l.id).filter(id => id));
                const uniqueNew = newLogs.filter(l => !l.id || !existingIds.has(l.id));
                if (uniqueNew.length === 0) return prev;
                const combined = [...prev, ...uniqueNew];
                // Cap at 2000 lines to prevent memory bloat
                return combined.length > 2000 ? combined.slice(-2000) : combined;
              });
            }
            // Remove server_logs from marketData to avoid stale snapshot
            const { server_logs, ...restData } = message.data;
            setMarketData(prev => ({ ...prev, ...restData }));
            setLastUpdate(new Date(message.timestamp));
            
            // Log risk status changes for debugging
            if (restData.killswitch_active && !marketData.killswitch_active) {
              console.warn('[RISK] Killswitch activated:', restData.killswitch_reason);
            }
            if (restData.circuit_breaker && !marketData.circuit_breaker) {
              console.error('[RISK] Circuit breaker tripped:', restData.circuit_reason);
            }
          } else if (message.type === 'live_price') {
            setMarketData(prev => ({
              ...prev,
              active_symbol: message.symbol || prev.active_symbol,
              dom: message.dom || prev.dom,
              market_data: {
                ...(prev.market_data || {}),
                last_price: message.price
              },
              // ── SENSOR INJECTION: merge Matrix & Velocity from fast price stream ──
              macro_matrix: {
                ...(prev.macro_matrix || {}),
                strongest: message.strongest || prev.macro_matrix?.strongest || '—',
                weakest: message.weakest || prev.macro_matrix?.weakest || '—',
                scores: message.matrix_scores || prev.macro_matrix?.scores || {},
                tick_velocity: `${message.velocity_high ? 'HIGH' : 'LOW'} (${(message.velocity_ratio || 0).toFixed(1)}x)`,
                velocity_ratio: message.velocity_ratio ?? prev.macro_matrix?.velocity_ratio ?? 0,
                velocity_high: message.velocity_high ?? prev.macro_matrix?.velocity_high ?? false,
              }
            }));
          } else if (message.type === 'trading_status_update') {
            // Update the trading status when we receive an update from the server
            setTradingEnabled(message.trading_enabled);
          }
        } catch (err) { console.error('WS parse error:', err); }
      };
      wsRef.current.onerror = () => {
        setWsConnected(false);
        try { wsRef.current?.close(); } catch {}
      };
      wsRef.current.onclose = () => {
        setWsConnected(false);
        wsRef.current = null;
        if (shouldReconnectRef.current) {
          reconnectTimeoutRef.current = setTimeout(() => {
            connectWebSocketRef.current?.();
          }, 3000);
        }
      };
    } catch {
      setWsConnected(false);
      if (shouldReconnectRef.current) {
        reconnectTimeoutRef.current = setTimeout(() => {
          connectWebSocketRef.current?.();
        }, 3000);
      }
    }
  }, []);

  useEffect(() => { connectWebSocketRef.current = connectWebSocket; }, [connectWebSocket]);
  useEffect(() => {
    shouldReconnectRef.current = true;
    connectWebSocket();
    return () => {
      shouldReconnectRef.current = false;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connectWebSocket]);

  // NIM Stats
  const rawNimStats = marketData.nvidia_api_stats || {};
  const nimAgents = [
    { id: 'fundamental', label: 'Fundamental AI' },
    { id: 'scalper', label: 'Scalper AI' },
    { id: 'trend', label: 'Trend AI' },
    { id: 'chat', label: 'Chat AI' }
  ];

  const navItems = [
    { id: 'dashboard', label: 'Command Center', icon: LayoutDashboard },
    { id: 'performance', label: 'Bot Performance', icon: TrendingUp },
    { id: 'backtest', label: 'Backtest Engine', icon: BarChart3 },
    { id: 'optimize', label: 'Hyper-Optimizer', icon: Zap },
    { id: 'fundamentals', label: 'Radar Desk', icon: Database },
    { id: 'fleet', label: 'Fleet Manager', icon: Key },
    { id: 'terminal', label: 'Terminal', icon: Terminal },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  const renderTabContent = (tabId) => {
    switch (tabId) {
      case 'dashboard':
        return <TradingCommandCenter marketData={marketData} tradingEnabled={tradingEnabled} />;
      case 'performance':
        return <BotPerformance onNavigate={setActiveTab} />;
      case 'backtest':
        return <BacktestEngine wsConnected={wsConnected} wsMessage={wsMessage} />;
      case 'optimize':
        return <HyperOptimizer wsConnected={wsConnected} wsMessage={wsMessage} />;
      case 'fundamentals':
        return <ClawFundamentalDesk marketData={marketData} />;
      case 'fleet':
        return <ApiFleetManager wsConnected={wsConnected} />;
      case 'terminal':
        return <LiveTerminal serverLogs={accumulatedLogs} />;
      case 'settings':
        return <SystemParameters wsConnected={wsConnected} />;
      default:
        return null;
    }
  };

  // Calculate financial values
  const equity = marketData.equity?.total || 0;
  const pnl = (marketData.equity?.daily_pnl || 0);
  const upnl = marketData.margin?.unrealized_pnl || 0;
  const inrRate = USDT_TO_INR;
  const estimatedOpenFees = (marketData.positions?.length || 0) * MT5_SPREAD_FEE_ESTIMATE;

  return (
    <div className="h-screen bg-slate-950 text-white flex overflow-hidden">
      <FluidBackground />
      {/* ====== SIDEBAR (desktop: left panel, mobile: bottom nav) ====== */}
      <div className="hidden lg:flex w-64 bg-black/40 backdrop-blur-xl border-r border-white/5 flex-col shrink-0">
        {/* Logo */}
        <div className="p-5 border-b border-white/5">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-pink-400 to-pink-600 flex items-center justify-center shadow-lg shadow-pink-500/25 animate-float">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight">APEX</h1>
              <p className="text-[10px] text-slate-500 uppercase tracking-[0.2em]">Institutional</p>
            </div>
          </div>
        </div>
        
        {/* Nav - scrollable area */}
        <nav className="flex-1 py-4 px-2 overflow-y-auto min-h-0">
          <p className="text-[10px] text-slate-600 uppercase tracking-widest px-3 mb-2 font-medium">Navigation</p>
          <ul className="space-y-0.5">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <li key={item.id}>
                  <button
                    onClick={() => setActiveTab(item.id)}
                    className={`nav-item w-full flex items-center gap-3 px-3 py-2.5 text-[13px] rounded-xl transition-all duration-200 group ${
                      isActive
                        ? 'active bg-pink-500/10 text-pink-400'
                        : 'text-slate-500 hover:bg-white/[0.03] hover:text-slate-300'
                    }`}
                  >
                    <Icon className={`w-[18px] h-[18px] shrink-0 transition-all duration-200 ${isActive ? 'text-pink-400' : 'group-hover:text-slate-300'}`} />
                    <span className="font-medium truncate text-left">{item.label}</span>
                    {item.id === 'terminal' && accumulatedLogs.length > 0 && (
                      <span className="ml-auto text-[10px] bg-pink-500/15 text-pink-400 px-1.5 py-0.5 rounded-full">
                        {accumulatedLogs.length}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>



        {/* ── PINNED BOTTOM: NIM Gauges + Connection ── */}
        <div className="shrink-0 border-t border-white/5">
          {/* NIM API Gauges (Per Key) */}
          <div className="px-3 pt-2 pb-1 space-y-1.5">
            {nimAgents.map(agent => {
              const stats = rawNimStats[agent.id];
              if (!stats) return null;
              const pct = Math.min(100, (stats.rpm / stats.rpm_limit) * 100);
              return (
                <div key={agent.id} className="flex items-center gap-2">
                  <Cpu className="w-2.5 h-2.5 text-pink-400 shrink-0" />
                  <span className="text-[8px] text-slate-500 uppercase tracking-wider font-bold w-20 truncate">{agent.label}</span>
                  <div className="flex-1 h-1 bg-white/5 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-700 ${
                        stats.rpm > 30 ? 'bg-rose-400' : stats.rpm > 15 ? 'bg-amber-400' : 'bg-gradient-to-r from-pink-500 to-pink-400'
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className={`text-[9px] font-bold font-mono w-8 text-right ${stats.rpm > 30 ? 'text-rose-400' : stats.rpm > 15 ? 'text-amber-400' : 'text-pink-400'}`}>
                    {stats.rpm}/{stats.rpm_limit}
                  </span>
                </div>
              );
            })}
          </div>
        
          {/* Connection Status */}
          <div className="px-3 pb-3 pt-1">
            <div className="flex items-center space-x-2 px-3 py-2 rounded-xl bg-black/40">
              {wsConnected ? (
                <>
                  <div className="w-1.5 h-1.5 bg-pink-400 rounded-full animate-pulse shadow-lg shadow-pink-400/50" />
                  <span className="text-[11px] text-pink-400 font-medium">Live</span>
                </>
              ) : (
                <>
                  <div className="w-1.5 h-1.5 bg-rose-400 rounded-full" />
                  <span className="text-[11px] text-rose-400 font-medium">Offline</span>
                </>
              )}
              <span className="text-[9px] text-slate-600 ml-auto">
                {lastUpdate ? lastUpdate.toLocaleTimeString() : '—'}
              </span>
            </div>
          </div>
        </div>  {/* end pinned bottom */}
      </div>

      {/* ====== MAIN AREA ====== */}
      {/* ====== MOBILE BOTTOM NAV ====== */}
      <div className="lg:hidden fixed bottom-0 left-0 right-0 z-50 bg-black/90 backdrop-blur-xl border-t border-white/5 px-2 py-2">
        <div className="mobile-tabbar flex items-stretch gap-1 overflow-x-auto scroll-smooth pb-1">
          {navItems.map(item => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`min-w-[74px] flex flex-col items-center justify-center gap-1 px-2 py-1.5 rounded-xl transition-colors border ${
                  isActive
                    ? 'text-pink-400 bg-pink-500/10 border-pink-500/25'
                    : 'text-slate-500 border-transparent hover:text-slate-300 hover:bg-white/[0.03]'
                }`}
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span className="w-full truncate text-center text-[8px] font-bold leading-tight">{item.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 min-w-0 overflow-y-auto bg-transparent pb-20 lg:pb-0">
        {/* Top Bar */}
        <div className="sticky top-0 z-20 bg-transparent/85 backdrop-blur-xl border-b border-white/5">
          <div className="flex flex-col xl:flex-row justify-between items-stretch xl:items-center px-3 sm:px-6 py-2 sm:py-3 gap-3">
            <div className="flex items-center justify-between gap-3 sm:gap-4 w-full xl:w-auto min-w-0">
              {/* Breadcrumb */}
              <div className="min-w-0">
                <h2 className="text-lg font-bold text-white truncate">
                  {navItems.find(n => n.id === activeTab)?.label || 'Dashboard'}
                </h2>
                {systemInfo && (
                  <div className="text-[9px] text-slate-600 mt-1">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="truncate">Public IP: {systemInfo.all_ips?.find(ip => ip.type === 'Public IP')?.address || 'N/A'}</span>
                      <button 
                        onClick={() => {
                          const ip = systemInfo.all_ips?.find(ip => ip.type === 'Public IP')?.address || 'N/A';
                          navigator.clipboard.writeText(ip);
                        }}
                        className="shrink-0 px-2 py-1 bg-pink-500/20 text-pink-400 rounded"
                      >
                        Copy IP
                      </button>
                    </div>
                  </div>
                )}
                <p className="text-[11px] text-slate-600 mt-0.5 truncate">
                  {wsConnected ? 'Real-time monitoring active' : 'Connecting...'}
                  {marketData.dry_run ? ' • Shadow Mode' : ' • Live Trading'}
                </p>
              </div>

              {/* Arm/Disarm */}
              <button
                onClick={toggleTrading}
                className={`shrink-0 flex items-center space-x-2 px-3 py-1.5 rounded-xl text-xs font-bold transition-all duration-300 ${
                  tradingEnabled
                    ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400'
                    : 'bg-amber-500/10 border border-amber-500/30 text-amber-400'
                }`}
              >
                {tradingEnabled ? <Shield className="w-3.5 h-3.5" /> : <ShieldOff className="w-3.5 h-3.5" />}
                <span>{tradingEnabled ? 'ARMED' : 'SHADOW'}</span>
                {tradingEnabled && <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />}
              </button>
            </div>

            {/* Right: Stats + Account */}
            <div className="flex items-center justify-start xl:justify-end gap-2 sm:gap-4 w-full xl:w-auto overflow-x-auto min-w-0">
              {/* Quick Stats */}
              <div className="flex items-center space-x-2 sm:space-x-3 shrink-0">
                <div className="stat-card glass-card-static rounded-xl px-2 sm:px-3 py-1.5 sm:py-2">
                  <p className="text-[8px] sm:text-[9px] text-slate-600 uppercase">Equity</p>
                  <p className="text-xs sm:text-sm font-bold text-white">${equity.toLocaleString()}</p>
                  <p className="text-[8px] sm:text-[9px] text-slate-600 hidden sm:block">₹{(equity * inrRate).toLocaleString(undefined, {maximumFractionDigits: 0})}</p>
                </div>
                <div className="stat-card glass-card-static rounded-xl px-2 sm:px-3 py-1.5 sm:py-2">
                  <p className="text-[8px] sm:text-[9px] text-slate-600 uppercase">P&L</p>
                  <p className={`text-xs sm:text-sm font-bold ${pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {pnl >= 0 ? '+' : ''}${pnl.toLocaleString()}
                  </p>
                  <p className={`text-[8px] sm:text-[9px] ${pnl >= 0 ? 'text-emerald-600' : 'text-rose-600'} hidden sm:block`}>₹{(pnl * inrRate).toLocaleString(undefined, {maximumFractionDigits: 0})}</p>
                  <p className="text-[8px] sm:text-[9px] text-slate-600 hidden lg:block">UPNL ${upnl.toLocaleString(undefined, {maximumFractionDigits: 2})} - Fees ${estimatedOpenFees.toLocaleString(undefined, {maximumFractionDigits: 2})}</p>
                </div>
                <div className="stat-card glass-card-static rounded-xl px-2 sm:px-3 py-1.5 sm:py-2 hidden sm:block">
                  <p className="text-[8px] sm:text-[9px] text-slate-600 uppercase">UPNL</p>
                  <p className={`text-xs sm:text-sm font-bold ${upnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {upnl >= 0 ? '+' : ''}${upnl.toLocaleString(undefined, {maximumFractionDigits: 2})}
                  </p>
                  <p className={`text-[8px] sm:text-[9px] ${upnl >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>₹{(upnl * inrRate).toLocaleString(undefined, {maximumFractionDigits: 0})}</p>
                  <p className="text-[8px] sm:text-[9px] text-slate-600">Gross before fees</p>
                </div>
              </div>

              {/* Account Selector */}
              <select
                value={selectedAccount}
                onChange={(e) => setSelectedAccount(e.target.value)}
                className="bg-black/60 border border-white/10 text-white text-xs rounded-xl px-3 py-2 focus:outline-none focus:border-pink-500/40 cursor-pointer"
              >
                <option value="fleet">Fleet ({Object.keys(marketData.account_balances || {}).length})</option>
                {Object.values(marketData.account_balances || {}).map(acct => (
                  <option key={acct.account_name} value={acct.account_name}>
                    {acct.account_name} — ${(acct.balance || 0).toLocaleString()}
                  </option>
                ))}
              </select>

              {/* Refresh */}
              <button
                onClick={refreshData}
                className="p-2 rounded-xl bg-white/5 hover:bg-white/10 transition-colors"
              >
                <RefreshCw className={`w-4 h-4 text-slate-500 ${wsConnected ? 'animate-spin-slow' : ''}`} />
              </button>
            </div>
          </div>
        </div>

        {/* System Status Risk Banner */}
        <RiskStatusBanner 
          killswitchActive={marketData.killswitch_active}
          killswitchReason={marketData.killswitch_reason}
          circuitBreaker={marketData.circuit_breaker}
          circuitReason={marketData.circuit_reason}
          drawdownPct={marketData.drawdown_pct}
          timeUntilReset={marketData.time_until_reset}
        />

        {/* Page Content */}
        <main className="p-3 sm:p-6">
          <div className="max-w-[1800px] mx-auto w-full">
            {mountedTabs.map((tabId) => {
              const isActive = activeTab === tabId;
              return (
                <section
                  key={tabId}
                  className={isActive ? 'page-enter' : 'hidden'}
                  aria-hidden={!isActive}
                >
                  {renderTabContent(tabId)}
                </section>
              );
            })}
          </div>
        </main>
      </div>
    </div>
  );
};

export default App;
