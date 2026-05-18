import asyncio
from core.brain import evaluate_market
import json
from unittest.mock import patch, AsyncMock

# Mock responses to force a unified "SELL" decision from all agents
async def mock_evaluate_market():
    market_data_unified = """=== REAL-TIME BTC/USUT MARKET DATA ===
Current Price: $62390.60
24h Change: +1.24%
24h High: $62480.23
24h Low: $62100.00
24h Volume: 123456 BTC
Recent Price Action:
- Last price showing +1.24% movement
- Trading range: $62100.00 - $62480.23
- Current volatility: HIGH"""

    dom_data_unified = """Global DOM X-Ray: 150.32 BTC resting Support vs 140.21 BTC resting Resistance. Imbalance: 52% Bids / 48% Asks. Aggregated Volume: 290.53 BTC. Largest wall: 25.65 BTC BID @ $62380.25 (Binance)."""
    
    # Mock the NVIDIA API responses to return SELL for all agents
    with patch('core.brain.get_market_sentiment', new=AsyncMock(return_value={
        "sentiment": "BEARISH", 
        "confidence": 80, 
        "report": "Mocked bearish sentiment"
    })):
        with patch('core.brain.analyze_macro_trend', new=AsyncMock(return_value={
            "decision": "SELL", 
            "confidence": 80, 
            "volatility": "high", 
            "recommended_leverage": 25
        })):
            with patch('core.brain.find_sniper_entry', new=AsyncMock(return_value={
                "decision": "SELL", 
                "confidence": 80, 
                "entry_price": 62385.0, 
                "leverage": 10
            })):
                result = await evaluate_market("", market_data_unified, 100000, dom_data_unified, force_run=True)
                return result

async def main():
    result = await mock_evaluate_market()
    print("Mocked unified bearish scenario result:", json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())