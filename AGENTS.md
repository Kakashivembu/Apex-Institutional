# Apex Institutional - Agent Instructions

## Quick Start Commands
```bash
# Start all services (PM2 ecosystem)
npm run start:all

# Frontend only (Vite dev server)
cd frontend && npm run dev

# Backend only (FastAPI)
cd nvidia_apex_trader && python -m server

# Test backend health
curl http://localhost:8000
```

## Key Architecture
- **Frontend**: React + Vite + Tailwind CSS (port 5173)
- **Backend**: FastAPI + WebSockets (port 8000)  
- **AI Agents**: OpenRouter + NVIDIA API integration
- **Database**: SQLite (`apex_keys.db`)

## Critical Files & Paths
- `nvidia_apex_trader/server.py` - Main FastAPI server with WebSocket
- `nvidia_apex_trader/core/brain.py` - 3-Agent AI pipeline (CLAW, Macro, Scalper)
- `nvidia_apex_trader/core/exchange.py` - Delta Exchange API with HMAC SHA256
- `frontend/src/components/TradingCommandCenter.jsx` - Main trading dashboard
- `frontend/src/components/BacktestEngine.jsx` - AI-powered backtesting

## API Keys & Configuration
- **OpenRouter**: `sk-or-v1-...` in `.env` (NVIDIA_APE_X_TRADER/.env)
- **NVIDIA API**: `nvapi-...` in `.env`
- **Delta Exchange**: Testnet keys in `.env` (mainnet ready)
- **Shadow Mode**: `DRY_RUN = True` in `exchange.py` for safe testing

## Real Data Integration
- **Live Market Data**: Binance API BTC/USDT prices in WebSocket broadcasts
- **AI Backtesting**: OpenRouter quantitative analysis (no random numbers)
- **WebSocket Data**: Real-time positions, equity, consensus, market data

## Development Gotchas
1. **Variable Naming**: Frontend uses `btcMarketData` (not `marketData`) for Binance data
2. **CORS**: Backend configured for `localhost:5173` and `*` origins
3. **PM2 Ecosystem**: Use `ecosystem.config.js` for process management
4. **Error Handling**: Backtest has fallback simulation if OpenRouter fails
5. **DNS Issues**: Windows may have API connectivity problems - uses IPv4 connectors

## Testing & Validation
```bash
# Test backend API
curl -X POST http://localhost:8000/api/backtest -H "Content-Type: application/json" -d '{"start_date":"2024-01-01","end_date":"2024-12-31","capital":100000,"leverage":10}'

# Test WebSocket
python -c "import websocket; ws = websocket.create_connection('ws://localhost:8000/'); ws.send('{\"type\":\"get_state\"}'); print(ws.recv()[:200])"
```

## Key Environment Variables
```bash
NVIDIA_API_KEY=nvapi-...
OPENROUTER_API_KEY=sk-or-v1-...
DELTA_TESTNET_API_KEY=...
DELTA_TESTNET_API_SECRET=...
DRY_RUN=True
```

## Recent Critical Fixes
- Removed all hardcoded fake data from frontend components
- Fixed WebSocket variable naming conflicts (`marketData` → `btcMarketData`)
- Added real Binance API integration with fallback values
- Replaced random backtesting with AI-powered quantitative analysis
- Fixed PM2 ecosystem configuration for Windows Node.js 24

## Performance Notes
- NVIDIA API has 40 RPM rate limit (1.5s delay between calls)
- OpenRouter responses may contain malformed JSON (robust parsing implemented)
- Delta Exchange mainnet ready (testnet keys currently configured)
- WebSocket broadcasts every 10 seconds with real market data

## Workflow Protocol: GitHub Checkpoints
**CRITICAL RULE**: BEFORE making ANY code changes or starting a new implementation phase, you MUST ALWAYS create a checkpoint on GitHub to preserve the working state.
1. Commit the current state: `git add .` and `git commit -m "Checkpoint: <Brief description>"`
2. Create a tag matching the repository's tagging format (e.g., `Apex-v[Version]-[Feature-Name]` or `v[Version]`). Example: `git tag Apex-v2.7-Risk-Engine`
3. Push the commit and the tag: `git push && git push origin --tags`