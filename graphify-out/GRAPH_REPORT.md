# Graph Report - .  (2026-05-10)

## Corpus Check
- 152 files · ~374,686 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 852 nodes · 1312 edges · 81 communities (67 shown, 14 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 63 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]

## God Nodes (most connected - your core abstractions)
1. `useStore` - 36 edges
2. `get_connection()` - 19 edges
3. `api` - 18 edges
4. `h()` - 16 edges
5. `Button()` - 15 edges
6. `Card()` - 15 edges
7. `fetch_real_market_data()` - 14 edges
8. `ApexWebSocketServer` - 14 edges
9. `evaluate_market()` - 14 edges
10. `run_historical_backtest()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `run_diagnostics()` --calls--> `get_market_sentiment()`  [INFERRED]
  test_agent_vision.py → nvidia_apex_trader/core/brain.py
- `run_diagnostics()` --calls--> `load_memory()`  [INFERRED]
  test_agent_vision.py → nvidia_apex_trader/core/memory.py
- `run_diagnostics()` --calls--> `fetch_dom_imbalance()`  [INFERRED]
  test_agent_vision.py → nvidia_apex_trader/core/data.py
- `run_diagnostics()` --calls--> `fetch_multi_timeframe()`  [INFERRED]
  test_agent_vision.py → nvidia_apex_trader/core/data.py
- `test_exchange_functions()` --calls--> `get_real_delta_balance()`  [INFERRED]
  test_exchange.py → nvidia_apex_trader/core/exchange.py

## Communities (81 total, 14 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.04
Nodes (39): AgentActivity, agentOutputBuffers, agentRegistry, app, busyAgents, CLI_BASE_ARGS, CLI_LOCAL_BIN, CLI_PARTS (+31 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (39): configPath(), DEFAULT_CONFIG, getWebhookEvents(), GitHubWebhookConfig, githubWebhookRoutes(), loadGitHubWebhookConfig(), saveGitHubWebhookConfig(), verifyGitHubSignature() (+31 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (11): AI_ROLES, MT5_SERVERS, BotPerformance(), formatInr(), formatUsd(), SYMBOLS, TIMEFRAMES, MACRO_ASSETS (+3 more)

### Community 3 - "Community 3"
Cohesion: 0.08
Nodes (37): add_key(), close_trade(), delete_key(), get_active_keys(), get_all_account_names(), get_all_keys(), get_all_trades(), get_connection() (+29 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (26): close_delta_position(), _ensure_mt5(), execute_delta_order(), execute_order(), get_available_margin(), get_real_active_positions(), get_real_delta_balance(), modify_bracket_sl_sync() (+18 more)

### Community 5 - "Community 5"
Cohesion: 0.11
Nodes (25): api, TelegramStatus, useStore, HookConfig, PerformanceMetrics, ConfigEntry, ConfigPanel(), inputStyle (+17 more)

### Community 6 - "Community 6"
Cohesion: 0.08
Nodes (30): calculate_atr(), _compute_ema(), compute_trend_indicators(), detect_fvgs(), fetch_candles_sync(), fetch_dom_imbalance(), fetch_dom_imbalance_sync(), fetch_global_liquidity() (+22 more)

### Community 7 - "Community 7"
Cohesion: 0.09
Nodes (8): api_get_flight_records(), get_accounts(), get_flight_records(), get_mt5_backtest_status(), Get per-account balance, margin, and positions data, Poll a running MT5 backtest for progress or final results., Run AI-powered historical backtest using BlockRun x402 proxy (free tier)., run_backtest()

### Community 8 - "Community 8"
Cohesion: 0.12
Nodes (22): _build_market_data_text(), _check_exit(), _compute_summary(), _error(), _generate_trade_chart(), _get_context_window(), _rates_to_dicts(), Apex Institutional — MT5 Historical Backtest Engine ============================ (+14 more)

### Community 9 - "Community 9"
Cohesion: 0.11
Nodes (19): configPath(), DEFAULT_CONFIG, getGitLabWebhookEvents(), gitlabEvents, GitLabWebhookConfig, GitLabWebhookEvent, gitlabWebhookRoutes(), GitLabWebhookStores (+11 more)

### Community 10 - "Community 10"
Cohesion: 0.14
Nodes (20): addSubagent(), extractFileFromInput(), FileState, getAllMonitoredSessions(), getNodeLogs(), getProjectSlug(), getSessionDir(), getSessionTree() (+12 more)

### Community 11 - "Community 11"
Cohesion: 0.11
Nodes (16): Agent, SwarmState, AGENT_TYPES, AgentsPanel(), STATUS_FILTERS, styles, STRATEGIES, Strategy (+8 more)

### Community 12 - "Community 12"
Cohesion: 0.15
Nodes (18): check_circuit_breaker(), force_reset(), get_circuit_status(), get_current_date(), _get_time_until_midnight(), midnight_reset_loop(), Risk Management Module - Daily Drawdown Circuit Breaker Institutional-grade capi, Calculate time remaining until midnight for UI display. (+10 more)

### Community 13 - "Community 13"
Cohesion: 0.11
Nodes (17): createWebSocket(), AgentsPanel, AgentVizPanel, ConfigPanel, Dashboard, HiveMindPanel, HooksPanel, LogsPanel (+9 more)

### Community 14 - "Community 14"
Cohesion: 0.18
Nodes (13): AppState, CoordinationMetrics, HiveMindState, MemoryEntry, MemoryStats, NeuralStatus, Session, WSMessage (+5 more)

### Community 15 - "Community 15"
Cohesion: 0.15
Nodes (17): appendAgentOutput(), appendTaskOutputLine(), broadcast(), buildSwarmPrompt(), ensureOutputsDir(), getActiveSwarmAgents(), launchViaClaude(), launchViaSwarmCli() (+9 more)

### Community 16 - "Community 16"
Cohesion: 0.16
Nodes (13): detect_trend_exhaustion(), evaluate_options_market(), evaluate_options_spread(), execute_local_fallback(), fetch_nvidia_sync(), _make_ai_cache_key(), parse_timeframe_metrics(), Create a cache key based on symbol, price bucket, and market data fingerprint. (+5 more)

### Community 17 - "Community 17"
Cohesion: 0.12
Nodes (16): agentRoutes(), aiDefenceRoutes(), configRoutes(), coordinationRoutes(), h(), hiveMindRoutes(), hooksRoutes(), memoryRoutes() (+8 more)

### Community 18 - "Community 18"
Cohesion: 0.17
Nodes (12): VizNode, VizSession, AgentVizPanel(), countActiveNodes(), countDoneNodes(), countNodes(), findNode(), LOG_TYPE_COLORS (+4 more)

### Community 20 - "Community 20"
Cohesion: 0.21
Nodes (14): check_news_killswitch(), country_to_currency(), extract_currencies_from_symbol(), fetch_economic_calendar(), parse_ff_datetime(), parse_impact(), Economic Calendar Killswitch - ForexFactory News Shield Protects capital from ex, Fetch economic calendar data from ForexFactory XML feed.          Returns: (+6 more)

### Community 21 - "Community 21"
Cohesion: 0.14
Nodes (11): getTelegramStores(), reinitTelegramBot(), AgentActivity, HTML, initTelegramBot(), TaskRecord, TelegramConfig, TelegramHandle (+3 more)

### Community 22 - "Community 22"
Cohesion: 0.14
Nodes (8): SwarmAgent, SwarmMonitorState, AgentActivityEvent, STATUS_BG_COLORS, STATUS_BORDER_COLORS, STATUS_COLORS, SwarmMonitorPanel(), TYPE_COLORS

### Community 23 - "Community 23"
Cohesion: 0.17
Nodes (12): _all_accounts_have_symbol_positions(), calculate_consensus(), fetch_live_mt5_data(), fetch_live_mt5_data_wrapper(), fetch_real_market_data(), market_data_loop(), Record a NVIDIA NIM API call for rate tracking., Fetch live market data from MT5 IPC.     Pure MetaTrader 5 operation - no exter (+4 more)

### Community 24 - "Community 24"
Cohesion: 0.18
Nodes (13): check_market_volatility(), fetch_liquidity_data_async(), get_market_sentiment(), Pre-LLM gating function. Parses MT5 Macro Data locally.     If the market is sid, Fetch liquidity data using asyncio.to_thread - bypasses Windows DNS blocking., Fetch liquidity data using asyncio.to_thread - bypasses Windows DNS blocking., AGENT 1: The Liquidation & Whale Hunter - Feeds real MT5 Macro Data to AI.     N, calculate_currency_matrix() (+5 more)

### Community 25 - "Community 25"
Cohesion: 0.21
Nodes (6): addApiLog(), request(), GitHubWebhookStatus, GitLabWebhookStatus, WebhookEvent, styles

### Community 26 - "Community 26"
Cohesion: 0.21
Nodes (11): Run an AI-powered autopsy on a closed trade to analyze performance.          Arg, run_trade_autopsy(), load_flight_state(), Persist step_trail_state and ai_predictive_traps to disk.          Uses atomic w, Load step_trail_state and ai_predictive_traps from disk.          Returns:, save_flight_state(), predictive_trap_loop(), Every 10 minutes, evaluates each open position via NVIDIA NIM     and sets a 't (+3 more)

### Community 27 - "Community 27"
Cohesion: 0.23
Nodes (10): get_available_balance(), get_delta_url(), append_to_memory(), load_memory(), apex_loop(), execute_trade(), get_active_credentials(), get_current_mark_price() (+2 more)

### Community 28 - "Community 28"
Cohesion: 0.18
Nodes (10): is_aplus_setup(), Mathematical Gatekeeper: Only allows A+ Setups to pass to the LLM.     1. Killzo, check_killzones(), detect_asian_range(), detect_fair_value_gaps(), detect_order_blocks(), Detects Order Blocks (OBs) — institutional supply/demand zones.      Bullish OB:, Detects Fair Value Gaps (FVGs) — 3-candle imbalance patterns used by institution (+2 more)

### Community 29 - "Community 29"
Cohesion: 0.22
Nodes (9): delete_ai_key(), delete_data_keys(), get_data_keys(), Return the Global Market Data API Key/Secret from .env (masked)., Write the Global Market Data API Key/Secret to .env., Remove the Global Market Data API Key/Secret from .env., refresh_in_memory_keys(), update_ai_key() (+1 more)

### Community 30 - "Community 30"
Cohesion: 0.22
Nodes (6): ErrorBoundary, Props, State, App(), escapeHtml(), showErrorToast()

### Community 31 - "Community 31"
Cohesion: 0.24
Nodes (10): _evaluate_backtest(), Lightweight consensus pipeline for backtesting.     Runs CLAW → Macro → Scalper, analyze_macro_trend(), compute_trend_bias(), evaluate_market(), find_sniper_entry(), Extract trend scores from candle data in market_data_text.     Returns a composi, AGENT 2: The Macro Trend Follower (NVIDIA NIM) - Using requests + asyncio.to_thr (+2 more)

### Community 32 - "Community 32"
Cohesion: 0.2
Nodes (6): HealthCheck, SystemHealth, CHECK_COLORS, CHECK_ICONS, Dashboard(), STATUS_COLORS

### Community 33 - "Community 33"
Cohesion: 0.24
Nodes (9): Task, COLUMNS, formatTime(), getPriorityBadge(), PRIORITY_COLORS, s, TaskCard(), TasksPanel() (+1 more)

### Community 34 - "Community 34"
Cohesion: 0.31
Nodes (7): fallback, TourContext, TourContextType, TourProvider(), buildTourSteps(), step(), TourStep

### Community 35 - "Community 35"
Cohesion: 0.36
Nodes (7): _dynamic_fallback(), _dynamic_pnl(), generate_ai_backtest(), Apex Institutional - AI Backtest Agent Generates 30-day projected backtests usin, Calculate a realistic PnL based on actual position math., Generate a 30-day projected backtest using AI.          Returns a dictionary wit, Generate a mathematically realistic fallback when AI is unavailable.     Uses po

### Community 36 - "Community 36"
Cohesion: 0.29
Nodes (6): WorkflowDef, getProgressFill(), s, WorkflowDetail(), WorkflowsPanel(), WorkflowTemplate

### Community 37 - "Community 37"
Cohesion: 0.29
Nodes (7): Layout(), LOG_LEVEL_COLORS, NavGroup, navGroups, NavItem, styles, useTour()

### Community 38 - "Community 38"
Cohesion: 0.25
Nodes (5): PreflightCheck, PreflightResult, Props, statusColor, statusIcon

### Community 39 - "Community 39"
Cohesion: 0.29
Nodes (6): detect_fvgs(), format_report(), Score FVGs based on Liquidity Quality metrics.      Scoring Logic:     - Base sc, Format a console-friendly Smart Money Liquidity X-Ray report., Detect Fair Value Gaps (FVGs) from an array of candles.      Bullish FVG: Low of, score_liquidity()

### Community 40 - "Community 40"
Cohesion: 0.33
Nodes (7): ensureDaemon(), execCli(), execFileAsync, getHiveMindMemory(), launchSwarmPipeline(), purgeAllCliAgents(), storeHiveMindMemory()

### Community 41 - "Community 41"
Cohesion: 0.33
Nodes (7): cloneWebhookRepo(), createGitHubPRAndCloseIssue(), createGitLabMRAndCloseIssue(), createWebhookTask(), execAsync, handleWebhookTaskCompletion(), parseWebhookTitle()

### Community 42 - "Community 42"
Cohesion: 0.29
Nodes (6): baseStyle, ButtonProps, disabledStyle, sizeStyles, spinnerStyle, variantStyles

### Community 43 - "Community 43"
Cohesion: 0.33
Nodes (6): Manually trigger a re-backtest — returns immediately, runs in background, Run backtest for a single account via the AI Backtest Agent., Run backtest for ALL accounts sequentially with 60s cooldown, rerun_backtest(), run_auto_backtest(), run_single_account_backtest()

### Community 44 - "Community 44"
Cohesion: 0.4
Nodes (3): ConnectionManager, get_network_info(), websocket_endpoint()

### Community 45 - "Community 45"
Cohesion: 0.33
Nodes (5): STEP-TRAIL VERIFICATION SCRIPT =============================== Simulates the ste, Simulate recovery after PM2 restart, Simulate the step-trailing engine through a price sequence, simulate_trail(), test_recovery()

### Community 46 - "Community 46"
Cohesion: 0.33
Nodes (6): ensurePersistDir(), gracefulShutdown(), loadTelegramConfig(), saveTelegramConfig(), saveToDisk(), TELEGRAM_CONFIG_FILE()

### Community 47 - "Community 47"
Cohesion: 0.5
Nodes (3): formatRelativeTime(), now, stamp

## Knowledge Gaps
- **318 isolated node(s):** `Fetch live BTC market data from Delta Exchange (primary) + Binance (fallback).`, `Main diagnostic routine - fetches all data and assembles prompts.`, `Detect Fair Value Gaps (FVGs) from an array of candles.      Bullish FVG: Low of`, `Score FVGs based on Liquidity Quality metrics.      Scoring Logic:     - Base sc`, `Format a console-friendly Smart Money Liquidity X-Ray report.` (+313 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **14 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `fetch_real_market_data()` connect `Community 23` to `Community 4`, `Community 6`, `Community 7`, `Community 28`, `Community 31`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **Why does `market_data_loop()` connect `Community 23` to `Community 26`, `Community 12`, `Community 20`, `Community 7`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Why does `evaluate_market()` connect `Community 31` to `Community 16`, `Community 50`, `Community 23`, `Community 24`, `Community 27`, `Community 28`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **What connects `Fetch live BTC market data from Delta Exchange (primary) + Binance (fallback).`, `Main diagnostic routine - fetches all data and assembles prompts.`, `Detect Fair Value Gaps (FVGs) from an array of candles.      Bullish FVG: Low of` to the rest of the system?**
  _318 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.04 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.05 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.06 - nodes in this community are weakly interconnected._