# Project Analysis: APEX Institutional

APEX Institutional is a high-frequency, AI-driven autonomous cryptocurrency trading terminal built on a microservices architecture. It leverages NVIDIA NIM and OpenRouter to orchestrate a 3-Agent Consensus pipeline for trading BTC/USD perpetual futures on Delta Exchange India.

## Key Architectural Components

### 1. Frontend (React + Vite + Tailwind CSS)
- **Octo SMM Aesthetic:** The UI has been heavily modernized using a deep black background (`#000000`), a vibrant pink primary accent (`#F70670`), and massive `Onest` typography.
- **Fluid Interface:** Utilizes `FluidBackground.jsx` with a WebGL canvas that reacts to mouse movements, operating seamlessly beneath heavy glassmorphism panels.
- **Live Terminal:** Real-time log streaming directly into the UI via `LiveTerminal.jsx`.
- **Trading Command Center:** The core hub integrating TradingView Advanced Charts and displaying live AI consensus decisions.
- **Dynamic AI Backtest:** The `BacktestEngine.jsx` simulates the 3-Agent strategy using the actual Delta balance over a 30-day period.

### 2. Backend Engine (FastAPI + Uvicorn)
- **3-Agent Consensus (`core/brain.py`):**
  - **CLAW (OpenRouter):** Fundamental analysis agent that scrapes live news and determines market sentiment.
  - **Macro Trend (NVIDIA NIM Llama 3.1 70B):** Assesses 1H/4H timeframe volatility and trend direction.
  - **Scalper (NVIDIA NIM Llama 3.1 70B):** Generates precise entry points and dynamic SL/TP levels on the 5M timeframe.
  - *Staggered Execution:* Built-in 2-second micro-delays between agents prevent API rate limiting (429 Too Many Requests).
- **Fast-Recovery Step Trailing (`server.py`):**
  - Monitors open positions and aggressively trails stop-losses to lock in profits across 3 tiers (Breakeven, Profit Step, Aggressive).
  - On restart, it instantly recovers the actual SL and TP directly from Delta Exchange's bracket orders, preventing any "unprotected" vulnerability windows.
- **Secure Execution (`core/exchange.py`):**
  - Fully asynchronous interactions with Delta Exchange using synchronous `requests` inside thread pools to bypass Windows networking bugs.
  - HMAC SHA256 authentication with dynamic server-time offsetting to mitigate clock drift.

---

# Implementation Plan for `FinalReport.html`

I will transform `FinalReport.html` into a premium, interactive technical document that perfectly mirrors the new Octo SMM theme, enhanced with dynamic Mermaid.js diagrams and AI-generated abstract visual assets.

## Proposed Changes

### [MODIFY] `FinalReport.html`
1. **Octo SMM Theme Integration:**
   - Dark/Black base `#050505` with Vibrant Pink `#F70670` highlights.
   - Heavy `Onest` font for headers, `Manrope` for body text.
   - Glassmorphism styling (`backdrop-filter: blur(40px)`, `rgba(255,255,255,0.03)`) for all data cards and tables.

2. **Mermaid.js Diagram Integration:**
   - Embed Mermaid.js via CDN.
   - **Diagram 1: System Architecture** - Flowchart detailing the PM2 ecosystem mapping to Frontend (Vite), Backend (FastAPI), and the external Delta Exchange.
   - **Diagram 2: 3-Agent Pipeline** - A sequence diagram illustrating the staggered CLAW -> Macro -> Scalper consensus flow.
   - **Diagram 3: Step-Trailing Logic** - A state diagram showing the progression from Tier 0 to Tier 3 with the new Exchange Recovery loop.

3. **Content Expansion:**
   - Document the newly built **Staggered Consensus Engine**.
   - Document the **Live Binance Fallback Data** mechanism.
   - Detail the **Advanced Step-Trailing SL Recovery** behavior.

4. **Visual Enhancements (Images):**
   - I will use the AI image generation tool to create a sleek, abstract "Cyberpunk Trading Terminal Interface" image with pink/black themes to use as a high-quality banner for the report.

## User Review Required

> [!IMPORTANT]
> Does the addition of Mermaid.js diagrams and a fully rewritten glassmorphic HTML structure sound good to you? I will also generate an abstract banner image to replace the old placeholder images (`report_dashboard.png`, etc.) which currently appear broken.

## Verification Plan
1. Generate the AI image and save it locally.
2. Rewrite `FinalReport.html` completely using a temporary Python script to inject the massive HTML payload safely.
3. Open the file or review the source to ensure Mermaid.js syntax is correct and the CSS reflects the Octo SMM guidelines.
