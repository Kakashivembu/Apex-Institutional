import asyncio
import os
from dotenv import load_dotenv
from nvidia_apex_trader.core.exchange import get_real_delta_balance, get_real_active_positions

load_dotenv('nvidia_apex_trader/.env')

DELTA_API_KEY = os.getenv("DELTA_TESTNET_API_KEY")
DELTA_SECRET = os.getenv("DELTA_TESTNET_API_SECRET")

print(f"Using Delta API key: {DELTA_API_KEY[:8]}...{DELTA_API_KEY[-4:]}")
print(f"Using Delta secret: {DELTA_SECRET[:8]}...{DELTA_SECRET[-4:]}")

async def test_exchange_functions():
    print("\n=== Testing Exchange Functions ===")
    
    # Test 1: Get real balance
    print("1. Testing get_real_delta_balance...")
    try:
        balance = await get_real_delta_balance(DELTA_API_KEY, DELTA_SECRET)
        print(f"Balance: ${balance:.2f}")
    except Exception as e:
        print(f"Balance error: {e}")
    
    # Test 2: Get active positions
    print("\n2. Testing get_real_active_positions...")
    try:
        positions = await get_real_active_positions(DELTA_API_KEY, DELTA_SECRET)
        print(f"Positions: {positions}")
    except Exception as e:
        print(f"Positions error: {e}")

if __name__ == "__main__":
    asyncio.run(test_exchange_functions())