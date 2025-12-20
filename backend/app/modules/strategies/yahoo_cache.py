"""
Yahoo Finance Data Cache with NASDAQ Fallback

Provides intelligent caching for options and stock data with automatic fallback:
- Primary: yfinance (Yahoo Finance library)
- Fallback: Direct Yahoo API (for stock prices)
- Fallback: NASDAQ API (for options data when yfinance rate-limited)

Cache TTL varies based on market hours:
- During market hours: 5 minutes (data changes frequently)
- Outside market hours: 30 minutes (prices static)
- Weekends: 60 minutes (markets closed)

This module caches:
- Stock info (ticker.info)
- Option chains (ticker.option_chain or NASDAQ API)
- Available expirations (ticker.options)
"""

import yfinance as yf
import requests
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass
import logging
import pytz

logger = logging.getLogger(__name__)

# Global cache storage
_ticker_info_cache: Dict[str, Tuple[datetime, Dict]] = {}
_option_chain_cache: Dict[str, Tuple[datetime, Any]] = {}
_options_expirations_cache: Dict[str, Tuple[datetime, List[str]]] = {}
_earnings_date_cache: Dict[str, Tuple[datetime, Optional[date]]] = {}  # Earnings dates (24hr cache)
_price_history_cache: Dict[str, Tuple[datetime, Any]] = {}  # Price history

# Track last fetch time for freshness indicator
_last_fetch_times: Dict[str, datetime] = {}

# Track errors for UI display
_last_errors: Dict[str, Tuple[datetime, str]] = {}
_data_sources: Dict[str, str] = {}  # Track which source was used


@dataclass
class OptionChainResult:
    """Wrapper to match yfinance option_chain return format."""
    calls: pd.DataFrame
    puts: pd.DataFrame
    source: str = "yfinance"  # or "nasdaq"


def get_cache_ttl() -> int:
    """
    Get cache TTL based on market hours.
    
    Returns TTL in seconds:
    - During market hours (6:30 AM - 1:00 PM PT, Mon-Fri): 5 minutes
    - Pre/post market (4:00 AM - 6:30 AM, 1:00 PM - 5:00 PM PT): 10 minutes  
    - Outside market hours: 30 minutes
    - Weekends: 60 minutes
    """
    try:
        PT = pytz.timezone('America/Los_Angeles')
        now = datetime.now(PT)
        hour = now.hour
        minute = now.minute
        weekday = now.weekday()
        
        # Weekend - long cache
        if weekday >= 5:
            return 3600  # 60 minutes
        
        # Convert to minutes since midnight
        current_time = hour * 60 + minute
        
        # Market hours (9:30 AM - 4:00 PM ET = 6:30 AM - 1:00 PM PT)
        market_open = 6 * 60 + 30   # 6:30 AM PT
        market_close = 13 * 60      # 1:00 PM PT
        
        # Extended hours (4:00 AM - 8:00 PM ET = 1:00 AM - 5:00 PM PT)
        extended_open = 4 * 60      # 4:00 AM PT
        extended_close = 17 * 60    # 5:00 PM PT
        
        if market_open <= current_time <= market_close:
            # Regular market hours - 5 minute cache
            return 300
        elif extended_open <= current_time <= extended_close:
            # Extended hours - 10 minute cache
            return 600
        else:
            # Outside market hours - 30 minute cache
            return 1800
            
    except Exception as e:
        logger.warning(f"Error calculating cache TTL: {e}")
        return 300  # Default to 5 minutes


def get_last_fetch_time(cache_type: str = "options") -> Optional[datetime]:
    """Get the last time we fetched fresh data from Yahoo."""
    return _last_fetch_times.get(cache_type)


def record_error(error_type: str, message: str):
    """Record an error for UI display."""
    _last_errors[error_type] = (datetime.now(), message)


def clear_error(error_type: str):
    """Clear an error after successful fetch."""
    _last_errors.pop(error_type, None)


def get_data_freshness_info() -> Dict[str, Any]:
    """
    Get information about data freshness for UI display.
    
    Returns:
        Dict with:
        - last_options_fetch: ISO timestamp of last options data fetch
        - last_prices_fetch: ISO timestamp of last price fetch  
        - cache_ttl_seconds: Current cache TTL
        - is_market_hours: Whether market is currently open
        - next_refresh_available: When cache will expire
        - errors: Any recent errors
        - data_source: Which API provided the data (yfinance/nasdaq/direct_api)
    """
    now = datetime.now()
    ttl = get_cache_ttl()
    
    # Determine market status
    try:
        PT = pytz.timezone('America/Los_Angeles')
        now_pt = datetime.now(PT)
        weekday = now_pt.weekday()
        hour = now_pt.hour
        
        is_market_hours = (
            weekday < 5 and 
            6 * 60 + 30 <= hour * 60 + now_pt.minute <= 13 * 60
        )
    except:
        is_market_hours = False
    
    # Get last fetch times
    options_fetch = _last_fetch_times.get("options")
    prices_fetch = _last_fetch_times.get("prices")
    
    # Calculate next refresh
    next_refresh = None
    if options_fetch:
        next_refresh = options_fetch + timedelta(seconds=ttl)
    
    # Get recent errors (within last 5 minutes)
    recent_errors = {}
    for error_type, (error_time, message) in _last_errors.items():
        if (now - error_time).total_seconds() < 300:
            recent_errors[error_type] = {
                "time": error_time.isoformat(),
                "message": message
            }
    
    return {
        "last_options_fetch": options_fetch.isoformat() if options_fetch else None,
        "last_prices_fetch": prices_fetch.isoformat() if prices_fetch else None,
        "cache_ttl_seconds": ttl,
        "cache_ttl_display": f"{ttl // 60} minutes",
        "is_market_hours": is_market_hours,
        "next_refresh_available": next_refresh.isoformat() if next_refresh else None,
        "errors": recent_errors if recent_errors else None,
        "data_sources": dict(_data_sources) if _data_sources else None,
    }


# =============================================================================
# NASDAQ API Functions (Fallback for Options Data)
# =============================================================================

def _fetch_nasdaq_options(symbol: str, limit: int = 100) -> Optional[Dict]:
    """
    Fetch options data directly from NASDAQ API.
    
    This is the fallback when yfinance is rate-limited.
    """
    url = f"https://api.nasdaq.com/api/quote/{symbol}/option-chain"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
        'Accept': 'application/json',
    }
    params = {
        'assetclass': 'stocks',
        'limit': limit,
        'fromdate': 'all',
        'todate': 'undefined',
        'excode': 'oprac',
        'callput': 'callput',
        'money': 'all',
        'type': 'all'
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"NASDAQ API returned {response.status_code} for {symbol}")
            return None
    except Exception as e:
        logger.warning(f"NASDAQ API error for {symbol}: {e}")
        return None


def _parse_nasdaq_to_dataframe(nasdaq_data: Dict, option_type: str = "call") -> pd.DataFrame:
    """
    Parse NASDAQ API response into a DataFrame matching yfinance format.
    
    Args:
        nasdaq_data: Response from NASDAQ API
        option_type: "call" or "put"
    """
    # Safely navigate nested structure - NASDAQ may return {"data": null}
    data = nasdaq_data.get('data') or {}
    table = data.get('table') or {}
    rows = table.get('rows') or []
    
    if not rows:
        return pd.DataFrame()
    
    parsed_rows = []
    prefix = "c_" if option_type == "call" else "p_"
    
    for row in rows:
        # Skip None or empty rows
        if not row:
            continue
        if not row.get('strike'):
            continue
            
        try:
            # Parse strike price
            strike_str = row.get('strike', '').replace('$', '').replace(',', '')
            strike = float(strike_str) if strike_str else None
            
            if strike is None:
                continue
            
            # Parse bid/ask/last
            def parse_price(val):
                if val is None or val == '--' or val == '':
                    return 0.0
                try:
                    return float(str(val).replace('$', '').replace(',', ''))
                except:
                    return 0.0
            
            def parse_int(val):
                if val is None or val == '--' or val == '':
                    return 0
                try:
                    return int(str(val).replace(',', ''))
                except:
                    return 0
            
            parsed_rows.append({
                'strike': strike,
                'bid': parse_price(row.get(f'{prefix}Bid')),
                'ask': parse_price(row.get(f'{prefix}Ask')),
                'lastPrice': parse_price(row.get(f'{prefix}Last')),
                'volume': parse_int(row.get(f'{prefix}Volume')),
                'openInterest': parse_int(row.get(f'{prefix}Openinterest')),
                'impliedVolatility': 0.0,  # NASDAQ doesn't provide IV
                'inTheMoney': False,  # Would need stock price to calculate
                'contractSymbol': f"{row.get('expiryDate', '')}_{strike}_{option_type[0].upper()}",
                'expiryDate': row.get('expiryDate', ''),
                '_source': 'nasdaq'
            })
        except Exception as e:
            logger.debug(f"Error parsing NASDAQ row: {e}")
            continue
    
    return pd.DataFrame(parsed_rows)


def get_option_chain_nasdaq(symbol: str) -> Optional[OptionChainResult]:
    """
    Get option chain from NASDAQ API as fallback.
    
    Returns an OptionChainResult with calls and puts DataFrames.
    """
    logger.info(f"Fetching option chain from NASDAQ API for {symbol}")
    
    nasdaq_data = _fetch_nasdaq_options(symbol, limit=200)
    
    if not nasdaq_data:
        return None
    
    calls_df = _parse_nasdaq_to_dataframe(nasdaq_data, "call")
    puts_df = _parse_nasdaq_to_dataframe(nasdaq_data, "put")
    
    if calls_df.empty and puts_df.empty:
        return None
    
    _data_sources["options"] = "nasdaq"
    _last_fetch_times["options"] = datetime.now()
    clear_error("options")
    
    logger.info(f"Got {len(calls_df)} calls and {len(puts_df)} puts from NASDAQ for {symbol}")
    
    return OptionChainResult(calls=calls_df, puts=puts_df, source="nasdaq")


def get_ticker_info(symbol: str, force_refresh: bool = False) -> Optional[Dict]:
    """
    Get ticker info with caching.
    
    Uses yfinance first, falls back to direct Yahoo API on rate limit.
    
    Args:
        symbol: Stock symbol
        force_refresh: If True, bypass cache
    
    Returns:
        Ticker info dict or None if failed
    """
    import requests
    
    cache_key = symbol.upper()
    now = datetime.now()
    ttl = get_cache_ttl()
    
    # Check cache
    if not force_refresh and cache_key in _ticker_info_cache:
        cached_time, cached_data = _ticker_info_cache[cache_key]
        if (now - cached_time).total_seconds() < ttl:
            logger.debug(f"Cache hit for {symbol} ticker info")
            return cached_data
    
    # Try yfinance first
    try:
        logger.info(f"Fetching ticker info for {symbol} via yfinance")
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        if info and info.get('currentPrice') or info.get('regularMarketPrice'):
            _ticker_info_cache[cache_key] = (now, info)
            _last_fetch_times["prices"] = now
            return info
            
    except Exception as e:
        logger.warning(f"yfinance failed for {symbol}: {e}")
    
    # Fallback to direct Yahoo API (less likely to be rate limited)
    try:
        logger.info(f"Falling back to direct Yahoo API for {symbol}")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
        params = {"interval": "1d", "range": "1d"}
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'chart' in data and 'result' in data['chart'] and data['chart']['result']:
                result = data['chart']['result'][0]
                meta = result.get('meta', {})
                
                # Create a minimal info dict compatible with yfinance format
                info = {
                    'symbol': symbol,
                    'regularMarketPrice': meta.get('regularMarketPrice'),
                    'currentPrice': meta.get('regularMarketPrice'),
                    'previousClose': meta.get('previousClose'),
                    'regularMarketVolume': meta.get('regularMarketVolume'),
                    'currency': meta.get('currency'),
                    'exchangeName': meta.get('exchangeName'),
                    '_source': 'direct_api'  # Mark as from fallback
                }
                
                _ticker_info_cache[cache_key] = (now, info)
                _last_fetch_times["prices"] = now
                logger.info(f"Got {symbol} price ${info['currentPrice']} from direct API")
                return info
                
    except Exception as e:
        logger.warning(f"Direct API also failed for {symbol}: {e}")
    
    # Return cached data if available (even if stale)
    if cache_key in _ticker_info_cache:
        logger.info(f"Returning stale cache for {symbol} due to errors")
        return _ticker_info_cache[cache_key][1]
    
    return None


def get_option_expirations(symbol: str, force_refresh: bool = False) -> List[str]:
    """
    Get available option expiration dates with caching.
    
    Uses yfinance first, falls back to NASDAQ API if rate-limited.
    
    Args:
        symbol: Stock symbol
        force_refresh: If True, bypass cache
    
    Returns:
        List of expiration date strings (YYYY-MM-DD format)
    """
    cache_key = symbol.upper()
    now = datetime.now()
    ttl = get_cache_ttl()
    
    # Check cache
    if not force_refresh and cache_key in _options_expirations_cache:
        cached_time, cached_data = _options_expirations_cache[cache_key]
        if (now - cached_time).total_seconds() < ttl:
            logger.debug(f"Cache hit for {symbol} expirations")
            return cached_data
    
    # Try yfinance first
    try:
        logger.info(f"Fetching expirations for {symbol} via yfinance")
        ticker = yf.Ticker(symbol)
        expirations = list(ticker.options) if ticker.options else []
        
        if expirations:
            _options_expirations_cache[cache_key] = (now, expirations)
            _last_fetch_times["options"] = now
            _data_sources["expirations"] = "yfinance"
            clear_error("expirations")
            return expirations
            
    except Exception as e:
        logger.warning(f"yfinance failed for {symbol} expirations: {e}")
        record_error("yfinance", f"Rate limited: {str(e)[:50]}")
    
    # Fallback to NASDAQ API
    try:
        logger.info(f"Falling back to NASDAQ API for {symbol} expirations")
        nasdaq_data = _fetch_nasdaq_options(symbol, limit=50)
        
        if nasdaq_data:
            # Extract unique expiry dates from NASDAQ response
            # Safely navigate - NASDAQ may return {"data": null}
            data = nasdaq_data.get('data') or {}
            table = data.get('table') or {}
            rows = table.get('rows') or []
            expiry_dates = set()
            
            for row in rows:
                if not row:  # Skip None or empty rows
                    continue
                expiry = row.get('expiryDate')
                if expiry:
                    # Convert "Dec 12" format to "2024-12-12" format
                    try:
                        # NASDAQ uses short format like "Dec 12"
                        # We need to add the year and convert
                        from dateutil import parser
                        parsed = parser.parse(expiry)
                        # If the parsed date is in the past, it's next year
                        if parsed.date() < date.today():
                            parsed = parsed.replace(year=parsed.year + 1)
                        expiry_dates.add(parsed.strftime("%Y-%m-%d"))
                    except:
                        pass
            
            expirations = sorted(list(expiry_dates))
            if expirations:
                _options_expirations_cache[cache_key] = (now, expirations)
                _last_fetch_times["options"] = now
                _data_sources["expirations"] = "nasdaq"
                clear_error("expirations")
                logger.info(f"Got {len(expirations)} expirations from NASDAQ for {symbol}")
                return expirations
                
    except Exception as e:
        logger.warning(f"NASDAQ API also failed for {symbol} expirations: {e}")
        record_error("nasdaq", f"Failed: {str(e)[:50]}")
    
    # Return cached data if available
    if cache_key in _options_expirations_cache:
        logger.info(f"Returning stale cache for {symbol} expirations")
        return _options_expirations_cache[cache_key][1]
    
    record_error("expirations", f"All sources failed for {symbol}")
    return []


def get_option_chain(
    symbol: str, 
    expiration_date: str = None,
    force_refresh: bool = False
) -> Optional[Any]:
    """
    Get option chain with caching.
    
    Uses yfinance first, falls back to NASDAQ API if rate-limited.
    
    Args:
        symbol: Stock symbol
        expiration_date: Expiration date string (YYYY-MM-DD), optional for NASDAQ
        force_refresh: If True, bypass cache
    
    Returns:
        Option chain object (with .calls and .puts DataFrames) or None
    """
    cache_key = f"{symbol.upper()}_{expiration_date or 'all'}"
    now = datetime.now()
    ttl = get_cache_ttl()
    
    # Check cache
    if not force_refresh and cache_key in _option_chain_cache:
        cached_time, cached_data = _option_chain_cache[cache_key]
        if (now - cached_time).total_seconds() < ttl:
            logger.debug(f"Cache hit for {symbol} {expiration_date} option chain")
            return cached_data
    
    # Try yfinance first (only if expiration_date provided)
    if expiration_date:
        try:
            logger.info(f"Fetching option chain for {symbol} {expiration_date} via yfinance")
            ticker = yf.Ticker(symbol)
            chain = ticker.option_chain(expiration_date)
            
            if chain is not None and (len(chain.calls) > 0 or len(chain.puts) > 0):
                # Wrap in our result type for consistency
                result = OptionChainResult(
                    calls=chain.calls, 
                    puts=chain.puts, 
                    source="yfinance"
                )
                _option_chain_cache[cache_key] = (now, result)
                _last_fetch_times["options"] = now
                _data_sources["options"] = "yfinance"
                clear_error("options")
                return result
                
        except Exception as e:
            logger.warning(f"yfinance failed for {symbol} option chain: {e}")
            record_error("yfinance", f"Rate limited: {str(e)[:50]}")
    
    # Fallback to NASDAQ API
    try:
        logger.info(f"Falling back to NASDAQ API for {symbol} option chain")
        result = get_option_chain_nasdaq(symbol)
        
        if result:
            _option_chain_cache[cache_key] = (now, result)
            return result
            
    except Exception as e:
        logger.warning(f"NASDAQ API also failed for {symbol}: {e}")
        record_error("nasdaq", f"Failed: {str(e)[:50]}")
    
    # Return cached data if available
    if cache_key in _option_chain_cache:
        logger.info(f"Returning stale cache for {symbol} option chain due to error")
        return _option_chain_cache[cache_key][1]
    
    record_error("options", f"All sources failed for {symbol}")
    return None


def get_earnings_date(symbol: str, force_refresh: bool = False) -> Optional[date]:
    """
    Get earnings date with caching.
    
    Earnings dates change rarely, so we cache for 24 hours.
    
    Args:
        symbol: Stock symbol
        force_refresh: If True, bypass cache
    
    Returns:
        Earnings date or None if not found
    """
    cache_key = symbol.upper()
    now = datetime.now()
    
    # Earnings dates are relatively static - cache for 24 hours
    EARNINGS_TTL = 86400  # 24 hours
    
    # Check cache
    if not force_refresh and cache_key in _earnings_date_cache:
        cached_time, cached_data = _earnings_date_cache[cache_key]
        if (now - cached_time).total_seconds() < EARNINGS_TTL:
            logger.debug(f"[EARNINGS_CACHE] Hit for {symbol}: {cached_data}")
            return cached_data
    
    # Fetch from yfinance
    try:
        logger.debug(f"[EARNINGS_CACHE] Fetching earnings for {symbol}")
        ticker = yf.Ticker(symbol)
        calendar = ticker.calendar
        
        # Check if calendar is a valid DataFrame (not None, not a dict error response)
        if calendar is None:
            _earnings_date_cache[cache_key] = (now, None)
            return None
        
        # If it's a dict (error response from Yahoo), skip it
        if isinstance(calendar, dict):
            logger.debug(f"[EARNINGS_CACHE] {symbol}: Calendar is a dict (likely error)")
            _earnings_date_cache[cache_key] = (now, None)
            return None
        
        # Now we know it's a DataFrame - check if it's empty
        if not isinstance(calendar, pd.DataFrame) or calendar.empty:
            _earnings_date_cache[cache_key] = (now, None)
            return None
        
        # Try to get earnings date
        earnings_date_series = calendar.get('Earnings Date')
        if earnings_date_series is not None and len(earnings_date_series) > 0:
            result = earnings_date_series[0].date() if hasattr(earnings_date_series[0], 'date') else None
            _earnings_date_cache[cache_key] = (now, result)
            if result:
                logger.info(f"[EARNINGS_CACHE] {symbol}: Found earnings date = {result}")
            return result
            
    except Exception as e:
        logger.debug(f"[EARNINGS_CACHE] {symbol}: Error fetching - {e}")
    
    # Cache the miss to avoid repeated failures
    _earnings_date_cache[cache_key] = (now, None)
    return None


def get_price_history(symbol: str, period: str = "5d", force_refresh: bool = False) -> Optional[pd.DataFrame]:
    """
    Get price history with caching.
    
    Args:
        symbol: Stock symbol
        period: Time period (e.g., "5d", "1mo")
        force_refresh: If True, bypass cache
    
    Returns:
        DataFrame with price history or None
    """
    cache_key = f"{symbol.upper()}_{period}"
    now = datetime.now()
    ttl = get_cache_ttl()
    
    # Check cache
    if not force_refresh and cache_key in _price_history_cache:
        cached_time, cached_data = _price_history_cache[cache_key]
        if (now - cached_time).total_seconds() < ttl:
            logger.debug(f"[HISTORY_CACHE] Hit for {symbol} {period}")
            return cached_data
    
    # Fetch from yfinance
    try:
        logger.debug(f"[HISTORY_CACHE] Fetching history for {symbol} {period}")
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        
        if hist is not None and not hist.empty:
            _price_history_cache[cache_key] = (now, hist)
            _last_fetch_times["history"] = now
            return hist
            
    except Exception as e:
        logger.debug(f"[HISTORY_CACHE] {symbol}: Error fetching - {e}")
    
    # Return stale cache if available
    if cache_key in _price_history_cache:
        logger.info(f"[HISTORY_CACHE] Returning stale cache for {symbol}")
        return _price_history_cache[cache_key][1]
    
    return None


def clear_cache(symbol: Optional[str] = None):
    """
    Clear cached data.
    
    Args:
        symbol: If provided, clear only this symbol's cache.
                If None, clear all cache.
    """
    global _ticker_info_cache, _option_chain_cache, _options_expirations_cache, _earnings_date_cache, _price_history_cache
    
    if symbol:
        symbol = symbol.upper()
        # Clear specific symbol
        _ticker_info_cache.pop(symbol, None)
        _options_expirations_cache.pop(symbol, None)
        _earnings_date_cache.pop(symbol, None)
        # Clear all option chains and history for this symbol
        for cache in [_option_chain_cache, _price_history_cache]:
            keys_to_remove = [k for k in cache.keys() if k.startswith(symbol)]
            for k in keys_to_remove:
                cache.pop(k, None)
        logger.info(f"Cleared cache for {symbol}")
    else:
        # Clear all
        _ticker_info_cache.clear()
        _option_chain_cache.clear()
        _options_expirations_cache.clear()
        _earnings_date_cache.clear()
        _price_history_cache.clear()
        logger.info("Cleared all Yahoo cache")


def get_cache_stats() -> Dict[str, Any]:
    """Get statistics about the cache."""
    return {
        "ticker_info_entries": len(_ticker_info_cache),
        "option_chain_entries": len(_option_chain_cache),
        "expirations_entries": len(_options_expirations_cache),
        "earnings_date_entries": len(_earnings_date_cache),
        "price_history_entries": len(_price_history_cache),
        "current_ttl_seconds": get_cache_ttl(),
        "last_fetch_times": {
            k: v.isoformat() if v else None 
            for k, v in _last_fetch_times.items()
        }
    }

