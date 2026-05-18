# Apex Institutional - Comprehensive Project Analysis

## Executive Summary

**Project Name:** Apex Institutional  
**Type:** AI-Powered Cryptocurrency Trading Terminal  
**Core Technology Stack:** React + FastAPI + WebSockets + NVIDIA/OpenRouter AI APIs  
**Exchange Integration:** Delta Exchange (Testnet with Mainnet-ready architecture)  

---

## 1. Architecture Overview

### 1.1 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (React + Vite)                       │
│                         Port: 5173 | Theme: Dark/Tailwind                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  App.jsx (Main)  │  TradingCommandCenter  │  BacktestEngine  │  ApiFleetMgr │
│  Sidebar.jsx     │  ClawFundamentalDesk  │  SystemParameters             │
└────────────────────────────┬──────────────────────────────────────────────┘
                             │ WebSocket (ws://localhost:8000)
                             │ HTTP REST (http://localhost:8000)
┌────────────────────────────┴──────────────────────────────────────────────┐
│                           BACKEND (FastAPI + Python)                       │
│                              Port: 8000                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  server.py          │  websocket_server.py  │  key_manager.py             │
│  API Endpoints:     │  WebSocket Handler   │  SQLite Database            │
│  - /api/keys        │  Broadcast every 10s  │  API key CRUD               │
│  - /api/backtest    │  Real-time market     │                             │
│  - / (websocket)    │                        │                             │
└────────────────────────────┬──────────────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   NVIDIA API    │  │  OpenRouter API │  │  Binance API    │
│  (LLM Models)   │  │  (Sentiment)    │  │  (BTC Price)    │
│                 │  │                 │  │                 │
│  • Llama 3.1    │  │  • DeepSeek     │  │  • 24hr ticker  │
│  • Rate Limit   │  │  • Auto model   │  │                 │
│    40 RPM       │  │                 │  │                 │
└────────┬────────┘  └────────┬────────┘  └─────────────────┘
         │                   │
         └────────┬──────────┘
                  ▼
         ┌─────────────────┐
         │  Delta Exchange │
         │  (Crypto DEX)   │
         ├─────────────────┤
         │  • Positions    │
         │  • Wallet       │
         │  • Orders       │
         │  • HMAC-SHA256  │
         └─────────────────┘

```

### 1.2 Technology Stack

| Layer | Technology | Version/Notes |
|-------|------------|---------------|
| **Frontend Framework** | React | 19.2.4 |
| **Build Tool** | Vite | 8.0.4 |
| **UI Framework** | Tailwind CSS | 4.2.2 |
| **Icons** | Lucide React | 1.8.0 |
| **Charts** | react-ts-tradingview-widgets | 1.2.8 |
| **Charts (Alt)** | Recharts | 3.8.1 |
| **Backend Framework** | FastAPI | Latest |
| **Web Server** | Uvicorn | Latest |
| **Database** | SQLite | apex_keys.db |
| **HTTP Client** | aiohttp + requests | Async + Sync |
| **AI - Primary** | NVIDIA NIM (Llama 3.1 70B) | 40 RPM limit |
| **AI - Fallback** | OpenRouter (Auto) | Multiple models |
| **Exchange** | Delta Exchange | Testnet |

---

## 2. Frontend Components Analysis

### 2.1 Main Entry Point: App.jsx

**File:** `frontend/src/App.jsx` (338 lines)

**Key Features:**
- WebSocket connection with auto-reconnect (max 5 attempts)
- Real-time market data state management
- Tab-based navigation with 5 views
- Error boundary with graceful error handling
- Last update timestamp tracking

**State Structure:**
```javascript
{
  activeTab: 'dashboard' | 'backtest' | 'fundamentals' | 'api-keys' | 'settings',
  wsConnected: boolean,
  marketData: {
    swarm_decisions: [],
    positions: [],
    equity: { total: 0, daily_pnl: 0, daily_change_pct: 0 },
    consensus: { direction: 'HOLD', strength: 0 }
  }
}
```

**Navigation Items:**
1. Trading Command Center
2. Backtest Engine
3. Claw Fundamental Desk
4. API Fleet Manager
5. System Parameters

---

### 2.2 TradingCommandCenter.jsx

**File:** `frontend/src/components/TradingCommandCenter.jsx` (322 lines)

**Features:**
- Real-time BTC/USD price display from Binance
- TradingView chart integration (AdvancedRealTimeChart)
- Triple-Agent Consensus display
- Live Fleet Positions table
- Bot Performance chart (equity curve)
- AI Recommendation panel

**Key Data Points:**
- BTC Price (last_price, 24h change, volume)
- Agent decisions (CLAW, Macro, Scalper)
- Position tracking (symbol, qty, entry, current, P&L)
- Consensus strength percentage

---

### 2.3 BacktestEngine.jsx

**File:** `frontend/src/components/BacktestEngine.jsx` (226 lines)

**Configuration Options:**
- Start Date (date picker)
- End Date (date picker)
- Capital (default: $100,000)
- Leverage (default: 10x, max: 100x)

**Results Display:**
- Win Rate (%)
- Total P&L ($)
- Max Drawdown ($)
- Profit Factor (x)
- Additional metrics table (total trades, winners, losers, avg win, avg loss, Sharpe ratio)

**API Endpoint:** `POST /api/backtest`

---

### 2.4 ApiFleetManager.jsx

**Purpose:** Manages multiple API keys for different exchange accounts

**Features:**
- Add new API key pair (account name, API key, API secret, network)
- Delete existing keys
- Display masked keys for security
- View all keys with status indicators

---

### 2.5 ClawFundamentalDesk.jsx

**Purpose:** Display fundamental analysis from CLAW agent

**Features:**
- Sentiment analysis results
- Market news aggregation
- Confidence scores

---

### 2.6 SystemParameters.jsx

**Purpose:** System configuration and parameters

**Features:**
- Trading parameters
- Risk management settings
- System diagnostics

---

## 3. Backend Components Analysis

### 3.1 server.py - Main FastAPI Server

**File:** `nvidia_apex_trader/server.py` (448 lines)

**API Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check - returns "Apex Institutional API" |
| `/api/keys` | GET | Retrieve all stored API keys (masked) |
| `/api/keys` | POST | Add new API key (account_name, api_key, api_secret, network) |
| `/api/keys` | DELETE | Delete API key by account_name |
| `/api/backtest` | POST | Run AI-powered backtest |
| `/` (WebSocket) | WS | Real-time market data stream |

**WebSocket Handler:**
- `ping` - Returns pong with timestamp
- `get_state` - Returns current market data snapshot

**Market Data Loop (every 10 seconds):**
1. Fetch live BTC data from Binance
2. Get active API keys from database
3. For each active key:
   - Fetch real balance from Delta Exchange
   - Fetch open positions
4. Run AI evaluation (3-agent consensus)
5. Broadcast to all connected clients

---

### 3.2 core/brain.py - AI Agent Pipeline

**File:** `nvidia_apex_trader/core/brain.py` (359 lines)

**Three-Agent Architecture:**

#### Agent 1: CLAW (Fundamental Desk)
- **API:** OpenRouter (Direct)
- **Model:** openrouter/auto (DeepSeek preferred)
- **Purpose:** Market sentiment analysis
- **Output:** `{sentiment, confidence, report}`
- **Rate Limit:** None (uses OpenRouter)

#### Agent 2: Macro Trend Follower
- **API:** NVIDIA NIM
- **Model:** meta/llama-3.1-70b-instruct
- **Purpose:** Determine macro trend direction
- **Input:** Sentiment report + 1H/4H candle data
- **Output:** `{decision: BUY|SELL|HOLD, confidence, reasoning}`
- **Rate Limit:** 40 RPM (1.5s delay between calls)

#### Agent 3: NVIDIA Scalper
- **API:** NVIDIA NIM
- **Model:** meta/llama-3.1-70b-instruct
- **Purpose:** Find sniper entry points
- **Input:** 5M candle data
- **Output:** `{decision, confidence, entry_price, reasoning}`
- **Rate Limit:** 40 RPM

**Consensus Logic:**
```
BUY + BUY = LONG
SELL + SELL = SHORT
Any other = HOLD
```

---

### 3.3 core/exchange.py - Delta Exchange Integration

**File:** `nvidia_apex_trader/core/exchange.py` (232 lines)

**Authentication:**
- HMAC SHA256 signature
- Timestamp-based (seconds)
- API Key + Signature in headers

**Endpoints Called:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v2/wallet/balances` | Get USDT wallet balance |
| GET | `/v2/positions/margined` | Get open positions |
| POST | `/v2/orders` | Execute market order |

**Safety Features:**
- `DRY_RUN = True` by default (Shadow Mode)
- Simulated order output with SHADOW prefix
- SSL verification disabled for testnet

**Functions:**
- `get_real_delta_balance()` - Async fetch USDT balance
- `get_real_active_positions()` - Async fetch open positions
- `execute_delta_order()` - Execute order with SL/TP
- `generate_signature()` - HMAC-SHA256 signature generation

---

### 3.4 core/data.py - Market Data Fetching

**File:** `nvidia_apex_trader/core/data.py` (71 lines)

**Capabilities:**
- Fetch OHLCV candles (1m, 5m, 15m, 1h)
- Multi-timeframe analysis
- Format data for LLM consumption
- Testnet endpoint: `cdn-ind.testnet.deltaex.org`

---

### 3.5 key_manager.py - API Key Storage

**File:** `nvidia_apex_trader/key_manager.py` (141 lines)

**Database:** SQLite (`apex_keys.db`)

**Schema:**
```sql
CREATE TABLE api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_name TEXT NOT NULL UNIQUE,
    api_key TEXT NOT NULL,
    api_secret TEXT NOT NULL,
    network TEXT DEFAULT 'testnet',
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL
);
```

**Functions:**
- `init_db()` - Initialize database
- `add_key()` - Add new key pair
- `get_all_keys()` - Get all keys
- `get_active_keys()` - Get active keys only
- `delete_key()` - Delete by account name
- `get_key_by_account()` - Get single key

---

## 4. Data Flow Analysis

### 4.1 Real-Time Market Data Flow

```
Binance API (BTCUSDT)
         │
         ▼
   server.py
   fetch_live_btc_data()
         │
         ├─────────────────────┐
         │                     │
         ▼                     ▼
  Delta Exchange        3-Agent AI
  (positions/balance)  (brain.py)
         │                     │
         └──────────┬──────────┘
                    │
                    ▼
            Broadcast via WebSocket
                    │
                    ▼
         All Connected Clients
```

### 4.2 Backtest Flow

```
User Input (start_date, end_date, capital, leverage)
         │
         ▼
POST /api/backtest
         │
         ▼
OpenRouter API (Quantitative Analysis)
         │
         ▼
Parse JSON Response
         │
         ▼
Return Results to Frontend
```

---

## 5. Configuration & Environment

### 5.1 Environment Variables

**File:** `nvidia_apex_trader/.env`

| Variable | Required | Description |
|----------|----------|-------------|
| `NVIDIA_API_KEY` | Yes | NVIDIA NIM API key (nvapi-...) |
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key (sk-or-v1-...) |
| `DELTA_TESTNET_API_KEY` | Optional | Delta Exchange testnet key |
| `DELTA_TESTNET_API_SECRET` | Optional | Delta Exchange testnet secret |
| `DRY_RUN` | Optional | Set to True for shadow mode (default: True) |

### 5.2 Port Configuration

| Service | Port | URL |
|---------|------|-----|
| Frontend (Vite) | 5173 | http://localhost:5173 |
| Backend (FastAPI) | 8000 | http://localhost:8000 |
| WebSocket | 8000 | ws://localhost:8000 |

---

## 6. Known Issues & Development Gotchas

### 6.1 Critical Issues from AGENTS.md

1. **Variable Naming Conflict**
   - Issue: Frontend uses `btcMarketData` not `marketData`
   - Solution: Always use `market_data` from WebSocket

2. **CORS Configuration**
   - Configured for: `localhost:5173`, `127.0.0.1:5173`, `*`
   - Default allows all origins

3. **PM2 Ecosystem**
   - Config file: `ecosystem.config.js`
   - Fixed for Windows Node.js 24

4. **Error Handling**
   - Backtest has fallback simulation if OpenRouter fails

5. **DNS Issues**
   - Windows may have API connectivity problems
   - Uses IPv4 connectors (socket.AF_INET)

### 6.2 Performance Considerations

- **NVIDIA API:** 40 RPM rate limit → 1.5s delay between calls
- **NVIDIA 429 Handling:** Exponential backoff implemented (up to 30s)
- **OpenRouter:** May return malformed JSON → robust parsing implemented
- **WebSocket:** Broadcasts every 10 seconds
- **Delta Exchange:** Mainnet ready (testnet keys currently configured)
- **Binance Fallback:** CoinGecko API as secondary source + random fallback

---

## 7. File Structure Summary

```
NEW NVdia Apex Ultimate/
├── AGENTS.md                          # Project instructions
├── apex_keys.db                       # SQLite database
├── package.json                       # Root (Tailwind only)
├── ecosystem.config.js                # PM2 process management
│
├── frontend/
│   ├── package.json                   # React + dependencies
│   ├── vite.config.js                 # Vite configuration
│   ├── tailwind.config.js            # Tailwind CSS config
│   ├── postcss.config.js              # PostCSS config
│   ├── index.html                    # Entry HTML
│   └── src/
│       ├── main.jsx                   # React entry
│       ├── App.jsx                    # Main application
│       ├── App.css                    # Global styles
│       ├── index.css                  # Tailwind imports
│       └── components/
│           ├── TradingCommandCenter.jsx   # Main dashboard
│           ├── BacktestEngine.jsx         # Historical backtesting
│           ├── ApiFleetManager.jsx        # API key management
│           ├── ClawFundamentalDesk.jsx    # Fundamental analysis
│           ├── SystemParameters.jsx       # System config
│           └── Sidebar.jsx                # Navigation
│
└── nvidia_apex_trader/
    ├── .env                           # Environment variables
    ├── server.py                      # FastAPI server (448 lines)
    ├── websocket_server.py           # WebSocket handler
    ├── main.py                        # Entry point
    ├── key_manager.py                 # SQLite key management
    ├── requirements.txt               # Python dependencies
    ├── apex.config.js                 # Config file
    ├── APEX_MEMORY.md                 # AI memory/context
    ├── APEX_STRATEGY.md               # Trading strategy
    └── core/
        ├── brain.py                   # 3-Agent AI pipeline (359 lines)
        ├── exchange.py                # Delta Exchange API (232 lines)
        ├── data.py                    # Candle data fetching (71 lines)
        └── memory.py                  # Memory/context storage

```

---

## 8. Security Considerations

1. **API Key Masking**
   - Keys displayed as: `XXXX...XXXX` (first 8 + last 4 chars)
   - Full secrets never exposed in API responses

2. **Dry Run Mode**
   - Default: `DRY_RUN = True`
   - Orders logged but not executed

3. **CORS Configuration**
   - Allows localhost:5173 (frontend dev)
   - Allows all origins for WebSocket

4. **SSL Verification**
   - Disabled for testnet Delta Exchange
   - Should be enabled for mainnet

---

## 9. Testing & Validation

### Backend Health Check
```bash
curl http://localhost:8000
# Expected: {"message":"Apex Institutional API","status":"online"}
```

### WebSocket Test
```bash
python -c "import websocket; ws = websocket.create_connection('ws://localhost:8000/'); ws.send('{\"type\":\"get_state\"}'); print(ws.recv()[:200])"
```

### Backtest API Test
```bash
curl -X POST http://localhost:8000/api/backtest -H "Content-Type: application/json" -d '{"start_date":"2024-01-01","end_date":"2024-12-31","capital":100000,"leverage":10}'
```

---

## 10. Summary

**Apex Institutional** is a sophisticated AI-powered cryptocurrency trading terminal featuring:

- **Multi-Agent AI System:** Three specialized agents (CLAW, Macro, Scalper) working in consensus
- **Real-Time Data:** Live BTC prices from Binance, positions from Delta Exchange
- **Modern UI:** Dark-themed React dashboard with TradingView charts
- **Safe Testing:** Shadow mode with dry-run orders
- **Extensible:** Multiple API key support, SQLite storage

The architecture follows best practices with clear separation between frontend (React), backend (FastAPI), and AI processing (NVIDIA/OpenRouter). The system is designed for both testing (testnet) and production (mainnet ready).

---

*Analysis generated on: 2026-04-11*
*Total files analyzed: 17*
*Total lines of code: ~2,500+*