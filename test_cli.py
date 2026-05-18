import subprocess
import asyncio

async def test_command():
    command = 'openclaw agent --session-id terminal --message "Act as a Macro-Economic Crypto Analyst. Scrape current crypto news and return ONLY a valid JSON sentiment report: {\\\"overall_sentiment\\\": \\\"Bullish\\\", \\\"confidence_score\\\": 80, \\\"summary\\\": \\\"...\\\"}" --local --json'
    
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        print(f"Return code: {result.returncode}")
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_command())