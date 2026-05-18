# APEX Institutional V2 - Strategy & Risk Framework

## 1. The 3-Agent Unanimous Mandate
- **The Gatekeeper:** Execution is strictly prohibited unless a 100% Unanimous Consensus (3/3) is achieved between the Fundamental Desk (CLAW), Macro Trend Follower, and Scalper AI.
- **Volatility Gate:** If the DOM X-Ray indicates a sideways, low-volatility market (e.g., ~50B/50A), all AI API calls are suppressed to conserve rate limits.

## 2. Dynamic Leverage & Margin Rules
- **Max Risk Per Trade:** 10% of Available Margin.
- **Leverage Ceiling:** Maximum 30x leverage.
- **Dynamic Sizing:** Leverage is calculated inversely to the Stop Loss. If volatility requires expanding the Stop Loss from 1.0% to 2.5%, Leverage MUST be automatically reduced to maintain the strict 10% dollar-risk constraint.

## 3. The Risk Engines
- **DOM Killswitch:** Monitors extreme order book imbalances to abort trades before spoofed walls collapse.
- **Fee-Adjusted Step-Trail:** "Breakeven" is strictly defined as `Entry Price ± 0.12%` to cover Delta Exchange round-trip taker fees and slippage. Stop Losses cannot trail to breakeven until the market clears this fee zone.
- **Momentum Check:** AI trade directions (LONG/SHORT) must align with the current 5-minute micro-momentum candle before execution is permitted.
