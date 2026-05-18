# Apex Agent Momentum Alignment Update

## Summary

I've successfully updated the system prompts for both the Macro Trend and Scalper agents to include momentum alignment rules. This should prevent the agents from attempting to "catch falling knives" during violent market downturns.

## Changes Made

1. **Macro Trend Agent Update**:
   - Added "MOMENTUM ALIGNMENT RULE" to the system prompt:
     ```
     MOMENTUM ALIGNMENT RULE: Never attempt to catch a falling knife. If the multi-timeframe data shows a cascading drop, high-velocity downward momentum, or bearish SuperTrend/EMA crosses, you MUST align your vote with the momentum (SELL). Do not predict bottoms or assume 'dip-buy' reversals during violent sell-offs.
     ```

2. **Scalper Agent Update**:
   - Added "ANTI-KNIFE RULE" to the system prompt:
     ```
     ANTI-KNIFE RULE: Do not fight extreme market momentum. If the immediate short-term trend (1m/5m/15m) shows a violent directional impulse (a massive red dump), look for SHORT continuation entries upon minor pullbacks. Do NOT vote BUY just because price hit a historical support level. Respect the velocity of the tape.
     ```

## Testing

The updates have been made to the brain.py file in the core directory. These changes should help the AI agents respect market momentum and avoid fighting strong downward trends.

## Next Steps

1. Monitor the agents' behavior during market downturns to ensure they follow the new rules
2. Observe if the consensus mechanism is now better at respecting downtrends
3. Adjust the parameters of the rules if needed based on real-world performance