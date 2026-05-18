# Apex Institutional - Full Project Report
**Date**: May 13, 2026
**Role**: Principal Quantitative Architect & Lead Full-Stack Engineer
**Project Status**: Production-Hardened (Forex Scalping Phase)

---

## 1. Project Identity
**"Apex Institutional"** is a high-frequency Global Macro Trading Terminal built for professional MetaTrader 5 (MT5) execution. It leverages a triple-agent AI swarm (NVIDIA NIM / OpenRouter) to evaluate macro sentiment, order flow (DOM), and technical structure (SMC) to execute precision trades with a focus on institutional-grade risk management.

---

## 2. Core Technology Stack
- **Backend**: FastAPI (Python 3.12+) with WebSockets for real-time telemetry.
- **Frontend**: React + Vite + Tailwind CSS + Framer Motion (Premium UI/UX).
- **AI Intelligence**: NVIDIA NIM (Meta Llama 3.1 70B/405B) + OpenRouter (Fallback).
- **Broker Interface**: Native MetaTrader 5 Bridge (XM Global / Institutional liquidity).
- **Persistence**: SQLite (`apex_keys.db`) + JSON Flight Recorder (`apex_flight_state.json`).

---

## 3. Key Architectural Pillars

### A. The AI Swarm (Consensus Engine)
Located in `core/brain.py`, the system runs a weighted consensus between three distinct AI personas:
1. **CLAW (Fundamental Desk)**: Analyzes macro sentiment and news.
2. **NVIDIA MACRO (Trend Follower)**: Evaluates multi-timeframe structure and EMA alignment.
3. **NVIDIA SCALPER (Precision Entry)**: Scans order book (DOM) and tick velocity for trigger points.
*Consensus Threshold: >= 55% strength required for execution.*

### B. Risk Management (The Circuit Breaker)
Located in `core/risk_manager.py`, now upgraded to **Dual-Threshold Logic**:
- **Realized Drawdown (5%)**: Trips based on closed-trade balance loss (prevents daily blowups).
- **Floating Emergency (20%)**: Trips on open-equity drawdown (margin-call protection).
- *Benefits*: Allows "Unlimited Stacking" strategies to breathe through normal spread/market fluctuations (~2-5%) without paralyzing the bot.

### C. Execution Engine (Step-Trailing SL)
Located in `server.py`, the engine uses a 3-tier micro-pipette strategy:
- **Tier 1 (Breakeven)**: Locks ~1 pip profit at ~4 pips move.
- **Tier 2 (Profit Step)**: Trails ~5 pips behind peak at ~10 pips move.
- **Tier 3 (Runner)**: Ultra-tight ~3 pip trail for extended moves.
*Hard Clamping*: All AI outputs are forced into a max 0.15% SL and 0.30% TP window for Forex scalping.

### D. AI Predictive Traps
A unique feature that uses NVIDIA NIM to predict "Reversal Traps" ahead of institutional supply/demand zones. If price hits a predicted trigger, the SL snaps to a high-probability protective level ahead of the zone.

---

## 4. Critical Hardening (Latest Updates - May 13, 2026)
1. **Forex Geometry Shift**: Replaced all crypto-sized volatility parameters (1-4%) with micro-pipette scalping values (0.01% - 0.30%).
2. **Async Loop Optimization**: Reduced inter-position processing delay from 200ms to **20ms**.
3. **MT5 Reliability**: Implemented a 100ms retry mechanism on `order_send` to prevent dropped tickets during heavy stacking (20+ positions).
4. **AI Directional Guardrails**: Hard-coded mathematical checks to prevent AI from outputting nonsensical SLs (e.g., SL above current price for a LONG).

---

## 5. File Map for LLM Context
- `nvidia_apex_trader/server.py`: Main execution loop, WebSocket management, and Step-Trailer.
- `nvidia_apex_trader/core/brain.py`: AI Swarm logic and sentiment analysis.
- `nvidia_apex_trader/core/risk_manager.py`: Realized vs Floating drawdown logic.
- `nvidia_apex_trader/core/mt5_engine.py`: Native MetaTrader 5 API bridge.
- `nvidia_apex_trader/core/macro_sensors.py`: SMC levels, Asian Range, and Tick Velocity.
- `frontend/src/components/TradingCommandCenter.jsx`: Main UI dashboard.

---

## 6. Current Operational Protocol
The bot is currently optimized for **Forex Majors (EURUSD, GBPUSD) and Gold**. It operates in "Unlimited Stacking" mode where it can open multiple positions on a single trend, protected by the aggressive dual-threshold risk manager and the micro-pipette trailing engine.
