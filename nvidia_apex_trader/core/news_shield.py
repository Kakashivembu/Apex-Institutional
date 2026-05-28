"""
Economic Calendar Killswitch - ForexFactory News Shield
Protects capital from extreme slippage during high-impact macroeconomic events.
"""

import aiohttp
import asyncio
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET
from typing import List, Dict, Optional
import pytz

# ForexFactory XML Feed URL
FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

# Currency mapping for symbol extraction
CURRENCY_MAP = {
    # Forex pairs
    "EUR": ["EUR"],
    "GBP": ["GBP"],
    "USD": ["USD"],
    "JPY": ["JPY"],
    "AUD": ["AUD"],
    "CAD": ["CAD"],
    "CHF": ["CHF"],
    "NZD": ["NZD"],
    # Commodities (typically USD-denominated)
    "XAU": ["USD"],  # Gold (XAUUSD format)
    "GOLD": ["USD"],  # Gold (broker literal)
    "GOLD.I#": ["USD"],  # Gold (XM Global broker literal)
    "XAG": ["USD"],  # Silver
    "USO": ["USD"],  # Oil
    "WTI": ["USD"],  # Oil
    "BTC": ["USD"],  # Bitcoin
    "ETH": ["USD"],  # Ethereum
}


def parse_impact(impact_str: str) -> str:
    """Normalize impact string to standard values."""
    if not impact_str:
        return "Low"
    impact = impact_str.strip().upper()
    if impact in ("HIGH", "H", "3", "RED"):
        return "High"
    elif impact in ("MEDIUM", "M", "MODERATE", "2", "ORANGE"):
        return "Medium"
    else:
        return "Low"


def parse_ff_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    """
    Parse ForexFactory datetime (EST/EDT) and convert to local time.
    ForexFactory uses US Eastern Time (EST/EDT depending on DST).
    """
    try:
        # Clean up the strings
        date_str = date_str.strip() if date_str else ""
        time_str = time_str.strip() if time_str else ""
        
        if not date_str:
            return None
        
        # Parse date (format: MM/DD/YYYY)
        try:
            month, day, year = map(int, date_str.split("/"))
        except ValueError:
            return None
        
        # Parse time (format: HH:MM or variants)
        hour, minute = 0, 0
        if time_str and time_str not in ("", "All Day", "Tentative"):
            # Handle various time formats
            time_str = time_str.replace("am", " AM").replace("pm", " PM")
            try:
                if ":" in time_str:
                    parts = time_str.replace(" ", ":").split(":")
                    hour = int(parts[0])
                    minute = int(parts[1])
                    # Handle AM/PM
                    if len(parts) > 2 and parts[2].upper() in ("PM", "P") and hour != 12:
                        hour += 12
                    elif len(parts) > 2 and parts[2].upper() in ("AM", "A") and hour == 12:
                        hour = 0
                else:
                    hour = int(time_str)
            except (ValueError, IndexError):
                hour, minute = 0, 0
        
        # Create datetime in US Eastern Time
        eastern = pytz.timezone("US/Eastern")
        dt_eastern = eastern.localize(datetime(year, month, day, hour, minute))
        
        # Convert to local time
        dt_local = dt_eastern.astimezone()
        
        return dt_local
        
    except Exception as e:
        print(f"[NEWS-SHIELD] Error parsing datetime '{date_str} {time_str}': {e}")
        return None


# Global Cache to prevent HTTP 429 rate limits
_cached_news: List[Dict] = []
_last_fetch_time: Optional[datetime] = None

async def fetch_economic_calendar() -> List[Dict]:
    """
    Fetch economic calendar data from ForexFactory XML feed.
    
    Returns:
        List of event dictionaries containing:
        - title: Event name
        - country: Affected currency/country code
        - impact: High/Medium/Low
        - date: Local datetime object
        - actual: Actual value (if available)
        - forecast: Forecasted value
        - previous: Previous value
    """
    global _cached_news, _last_fetch_time
    
    now = datetime.now()
    # Check if cache is valid (less than 1 hour old)
    if _last_fetch_time is not None:
        if (now - _last_fetch_time).total_seconds() < 3600:
            return _cached_news

    events = []
    
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(FF_CALENDAR_URL) as response:
                if response.status != 200:
                    print(f"[NEWS-SHIELD] Calendar fetch failed: HTTP {response.status}")
                    _last_fetch_time = now # Update fetch time to enforce backoff
                    return events # Return empty array gracefully
                
                xml_content = await response.text()
                
        # Parse XML
        root = ET.fromstring(xml_content)
        
        for event in root.findall(".//event"):
            try:
                title_elem = event.find("title")
                country_elem = event.find("country")
                date_elem = event.find("date")
                time_elem = event.find("time")
                impact_elem = event.find("impact")
                
                title = title_elem.text.strip() if title_elem is not None and title_elem.text else "Unknown"
                country = country_elem.text.strip() if country_elem is not None and country_elem.text else ""
                date_str = date_elem.text if date_elem is not None and date_elem.text else ""
                time_str = time_elem.text if time_elem is not None and time_elem.text else ""
                impact = parse_impact(impact_elem.text if impact_elem is not None and impact_elem.text else "Low")
                
                # Parse datetime
                event_datetime = parse_ff_datetime(date_str, time_str)
                if event_datetime is None:
                    continue
                
                events.append({
                    "title": title,
                    "country": country,
                    "impact": impact,
                    "date": event_datetime,
                    "raw_date": date_str,
                    "raw_time": time_str,
                })
                
            except Exception as e:
                # Skip malformed events
                continue
                
        print(f"[NEWS-SHIELD] Loaded {len(events)} economic events from ForexFactory")
        
        # Update cache
        _cached_news = events
        _last_fetch_time = now
        print("[NEWS-SHIELD] Global economic calendar updated and cached.")
        
    except aiohttp.ClientError as e:
        print(f"[NEWS-SHIELD] Network error fetching calendar: {e}")
    except ET.ParseError as e:
        print(f"[NEWS-SHIELD] XML parse error: {e}")
    except Exception as e:
        print(f"[NEWS-SHIELD] Unexpected error fetching calendar: {e}")
    
    return events


def extract_currencies_from_symbol(symbol: str) -> List[str]:
    """
    Extract base and quote currencies from a trading symbol.
    
    Examples:
        "GBPUSD" -> ["GBP", "USD"]
        "EURJPY" -> ["EUR", "JPY"]
        "GOLD" -> ["USD"] (Gold is USD-denominated)
        "BTCUSD" -> ["USD"] (BTC is USD-denominated)
    """
    if not symbol:
        return ["USD"]  # Default to USD for safety
    
    symbol = symbol.upper().replace("/", "").replace("-", "")
    
    # Handle commodities and crypto (typically USD-denominated)
    for prefix, currencies in CURRENCY_MAP.items():
        if symbol.startswith(prefix):
            return currencies.copy()
    
    # Handle forex pairs (6 character format)
    if len(symbol) >= 6:
        base = symbol[:3]
        quote = symbol[3:6]
        currencies = []
        if base in CURRENCY_MAP:
            currencies.append(base)
        if quote in CURRENCY_MAP:
            currencies.append(quote)
        if currencies:
            return currencies
    
    # Fallback: return USD
    return ["USD"]


def country_to_currency(country: str) -> str:
    """Map country name to currency code."""
    mapping = {
        "United States": "USD",
        "US": "USD",
        "USA": "USD",
        "Euro Zone": "EUR",
        "Eurozone": "EUR",
        "European Union": "EUR",
        "EU": "EUR",
        "United Kingdom": "GBP",
        "UK": "GBP",
        "Britain": "GBP",
        "England": "GBP",
        "Japan": "JPY",
        "Australia": "AUD",
        "Canada": "CAD",
        "Switzerland": "CHF",
        "Swiss": "CHF",
        "New Zealand": "NZD",
    }
    return mapping.get(country.strip(), country)


async def check_news_killswitch(active_symbol: str) -> Dict:
    """
    Check if trading should be halted due to upcoming or recent high-impact news.
    
    Args:
        active_symbol: The trading symbol being analyzed (e.g., "BTCUSD", "GBPUSD")
    
    Returns:
        Dict with:
        - is_safe: True if trading is safe, False if killswitch should engage
        - reason: Explanation string if not safe
        - events: List of matching high-impact events (for logging)
    """
    # Default to safe if anything fails
    default_safe = {"is_safe": True, "reason": "", "events": []}
    
    try:
        # Fetch calendar
        calendar = await fetch_economic_calendar()
        
        if not calendar:
            # No calendar data - default to safe to prevent lockouts
            return default_safe
        
        # Extract currencies from symbol
        currencies = extract_currencies_from_symbol(active_symbol)
        
        now = datetime.now().astimezone()
        
        # Time windows (conservative for capital protection)
        PRE_EVENT_WINDOW = timedelta(minutes=30)   # Halt 30 mins before
        POST_EVENT_WINDOW = timedelta(minutes=15)  # Halt 15 mins after
        
        dangerous_events = []
        
        for event in calendar:
            # Only check High impact events (Red Folder)
            if event["impact"] != "High":
                continue
            
            # Check if event affects our symbol's currencies
            event_currency = country_to_currency(event["country"])
            if event_currency not in currencies:
                continue
            
            event_time = event["date"]
            
            # Ensure both datetimes are timezone-aware
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=now.tzinfo)
            
            # Calculate time delta
            time_to_event = event_time - now
            minutes_to_event = time_to_event.total_seconds() / 60
            
            # Check if we're in the danger window
            # (within 30 mins before OR 15 mins after)
            in_pre_window = 0 < minutes_to_event <= 30
            in_post_window = -15 <= minutes_to_event <= 0
            
            if in_pre_window or in_post_window:
                dangerous_events.append({
                    "title": event["title"],
                    "currency": event_currency,
                    "time": event_time,
                    "minutes_away": round(minutes_to_event, 1)
                })
        
        if dangerous_events:
            # Sort by proximity
            dangerous_events.sort(key=lambda x: abs(x["minutes_away"]))
            closest = dangerous_events[0]
            
            if closest["minutes_away"] > 0:
                reason = f"High Impact: {closest['title']} ({closest['currency']}) in {closest['minutes_away']:.0f} mins"
            else:
                reason = f"High Impact: {closest['title']} ({closest['currency']}) was {-closest['minutes_away']:.0f} mins ago"
            
            return {
                "is_safe": False,
                "reason": reason,
                "events": dangerous_events
            }
        
        return default_safe
        
    except Exception as e:
        print(f"[NEWS-SHIELD] Killswitch check error: {e}")
        # CRITICAL: Default to safe on any error to prevent infinite lockouts
        return default_safe


async def get_daily_news_summary(active_symbol: str) -> str:
    """
    Format today's news events for the given symbol into a readable string for the LLM.
    """
    try:
        calendar = await fetch_economic_calendar()
        if not calendar:
            return "No economic calendar data available."
            
        currencies = extract_currencies_from_symbol(active_symbol)
        now = datetime.now().astimezone()
        
        # We only care about events happening TODAY
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        
        relevant_events = []
        for event in calendar:
            event_time = event["date"]
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=now.tzinfo)
                
            if today_start <= event_time <= today_end:
                event_currency = country_to_currency(event["country"])
                if event_currency in currencies and event["impact"] in ("High", "Medium"):
                    time_to_event = event_time - now
                    minutes_to_event = time_to_event.total_seconds() / 60
                    
                    if minutes_to_event > 0:
                        time_str = f"in {minutes_to_event / 60:.1f} hours"
                    else:
                        time_str = f"{-minutes_to_event / 60:.1f} hours ago"
                        
                    relevant_events.append(f"- [{event['impact']} Impact] {event['title']} ({event_currency}) @ {event_time.strftime('%H:%M')} ({time_str})")
        
        if relevant_events:
            return "Today's Economic News for " + active_symbol + ":\n" + "\n".join(relevant_events)
        else:
            return "No high/medium impact economic news for " + active_symbol + " today."
            
    except Exception as e:
        print(f"[NEWS-SHIELD] Error generating news summary: {e}")
        return "News data unavailable due to error."

# Standalone test
if __name__ == "__main__":
    async def test():
        print("=" * 60)
        print("NEWS SHIELD TEST")
        print("=" * 60)
        
        # Test currency extraction
        test_symbols = ["BTCUSD", "GBPUSD", "EURJPY", "GOLD", "EURUSD"]
        print("\n[Currency Extraction Test]")
        for sym in test_symbols:
            currencies = extract_currencies_from_symbol(sym)
            print(f"  {sym} -> {currencies}")
        
        # Test calendar fetch
        print("\n[Calendar Fetch Test]")
        calendar = await fetch_economic_calendar()
        high_impact = [e for e in calendar if e["impact"] == "High"]
        print(f"  Total events: {len(calendar)}")
        print(f"  High impact events: {len(high_impact)}")
        
        # Show upcoming high impact events
        now = datetime.now().astimezone()
        upcoming = [e for e in high_impact if e["date"] > now]
        upcoming.sort(key=lambda x: x["date"])
        print(f"\n  Upcoming High Impact Events (next 5):")
        for e in upcoming[:5]:
            time_to = (e["date"] - now).total_seconds() / 60
            print(f"    - {e['title']} ({e['country']}): {time_to:.0f} mins away")
        
        # Test killswitch for various symbols
        print("\n[Killswitch Test]")
        for sym in ["BTCUSD", "GBPUSD", "EURUSD"]:
            result = await check_news_killswitch(sym)
            status = "SAFE" if result["is_safe"] else f"BLOCKED: {result['reason']}"
            print(f"  {sym}: {status}")
        
        print("\n" + "=" * 60)
    
    asyncio.run(test())
