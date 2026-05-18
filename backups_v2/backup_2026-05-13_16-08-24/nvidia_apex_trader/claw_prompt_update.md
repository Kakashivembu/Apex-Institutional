# Apex CLAW Agent Prompt Update

## Summary

I've successfully updated the CLAW Agent's psychological prompt to include a tolerance band for DOM imbalances. This should reduce the agent's sensitivity to normal market noise and prevent it from vetoing profitable trades based on minor liquidity fluctuations.

## Changes Made

1. **Located the CLAW prompt**: Found in `nvidia_apex_trader/core/brain.py` in the `get_market_sentiment` function
2. **Added DOM TOLERANCE RULE**: 
   ```text
   DOM TOLERANCE RULE: A Global DOM Imbalance between 40% and 60% is normal market noise. Do NOT use the DOM to veto a trade or turn BEARISH/BULLISH if the imbalance is within this 40-60 band. Only consider the DOM a directional threat if one side exceeds 60%.
   ```
3. **Updated system_prompt**: The rule was added to the system_prompt string in the get_market_sentiment function

## Testing

I've tested the updated prompt and confirmed that the CLAW agent is still functioning correctly. The agent now includes the new tolerance rule in its analysis, which should reduce false positives from minor DOM imbalances.

## Next Steps

1. Monitor the agent's behavior to ensure it's no longer being overly sensitive to normal market noise
2. Observe if the consensus mechanism is now allowing more valid trades to pass through
3. Adjust the tolerance parameters if needed based on real-world performance