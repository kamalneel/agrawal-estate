"""
Options & Stock Data Cache

SIMPLIFIED ARCHITECTURE:
- Options Data: Schwab API ONLY (reliable delta data)
- Stock Prices: Direct Yahoo API (free, simple)

No more fallback chains that give bad data. If Schwab fails, we fail clearly.

Cache TTL varies based on market hours:
- During market hours: 5-15 minutes
- Outside market hours: 30-90 minutes
- Weekends: 60-180 minutes
"""

import requests
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass
import logging
import pytz

logger = logging.getLogger(__name__)

# =============================================================================
# CACHE STORAGE
# =============================================================================

_ticker_info_cache: Dict[str, Tuple[datetime, Dict]] = {}
_option_chain_cache: Dict[str, Tuple[datetime, Any]] = {}
_options_expirations_cache: Dict[str, Tuple[datetime, List[str]]] = {}
_earnings_date_cache: Dict[str, Tuple[datetime, Optional[date]]] = {}
_price_history_cache: Dict[str, Tuple[datetime, Any]] = {}

# Track last fetch time for freshness indicator
_last_fetch_times: Dict[str, datetime] = {}

# Track errors for UI display
_last_errors: Dict[str, Tuple[datetime, str]] = {}
_data_sources: Dict[str, str] = {}


@dataclass
class OptionChainResult:
    """Wrapper for option chain data."""
    calls: pd.DataFrame
    puts: pd.DataFrame
    source: str = "schwab"


# =============================================================================
# CACHE TTL
# =============================================================================

def get_cache_ttl(data_type: str = "prices") -> int:
    """
    Get cache TTL based on market hours and data type.
    
    Returns TTL in seconds.
    """
    try:
        PT = pytz.timezone('America/Los_Angeles')
        now = datetime.now(PT)
        hour = now.hour
        minute = now.minute
        weekday = now.weekday()
        
        # Multiplier for options data (delta doesn't change as fast)
        options_multiplier = 3 if data_type == "options" else 1
        
        # Weekend - long cache
        if weekday >= 5:
            return 3600 * options_multiplier
        
        current_time = hour * 60 + minute
        market_open = 6 * 60 + 30   # 6:30 AM PT
        market_close = 13 * 60      # 1:00 PM PT
        extended_open = 4 * 60      # 4:00 AM PT
        extended_close = 17 * 60    # 5:00 PM PT
        
        if market_open <= current_time <= market_close:
            return 300 * options_multiplier  # 5 min (prices) or 15 min (options)
        elif extended_open <= current_time <= extended_close:
            return 600 * options_multiplier  # 10 min (prices) or 30 min (options)
        else:
            return 1800 * options_multiplier  # 30 min (prices) or 90 min (options)
            
    except Exception as e:
        logger.warning(f"Error calculating cache TTL: {e}")
        return 300


def get_last_fetch_time(cache_type: str = "options") -> Optional[datetime]:
    """Get the last time we fetched fresh data."""
    return _last_fetch_times.get(cache_type)


def record_error(error_type: str, message: str):
    """Record an error for UI display."""
    _last_errors[error_type] = (datetime.now(), message)


def clear_error(error_type: str):
    """Clear an error after successful fetch."""
    _last_errors.pop(error_type, None)


def get_data_freshness_info() -> Dict[str, Any]:
    """Get information about data freshness for UI display."""
    now = datetime.now()
    ttl = get_cache_ttl()
    
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
    
    options_fetch = _last_fetch_times.get("options")
    prices_fetch = _last_fetch_times.get("prices")
    
    next_refresh = None
    if options_fetch:
        next_refresh = options_fetch + timedelta(seconds=ttl)
    
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
# STOCK PRICES - Direct Yahoo API (simple, free)
# =============================================================================

def _fetch_price_direct_api(symbol: str) -> Optional[Dict]:
    """
    Fetch stock price from direct Yahoo API.
    
    This is simple and reliable for stock prices.
    """
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
        params = {"interval": "1d", "range": "1d"}
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'chart' in data and 'result' in data['chart'] and data['chart']['result']:
                result = data['chart']['result'][0]
                meta = result.get('meta', {})
                
                info = {
                    'symbol': symbol,
                    'regularMarketPrice': meta.get('regularMarketPrice'),
                    'currentPrice': meta.get('regularMarketPrice'),
                    'previousClose': meta.get('previousClose'),
                    'regularMarketVolume': meta.get('regularMarketVolume'),
                    'currency': meta.get('currency'),
                    'exchangeName': meta.get('exchangeName'),
                    '_source': 'yahoo_direct'
                }
                
                if info['currentPrice']:
                    logger.debug(f"Got {symbol} price ${info['currentPrice']} from Yahoo API")
                    return info
                    
    except Exception as e:
        logger.warning(f"Yahoo API failed for {symbol}: {e}")
    
    return None


def get_ticker_info(symbol: str, force_refresh: bool = False) -> Optional[Dict]:
    """
    Get stock price info with caching.
    
    Uses direct Yahoo API (simple and reliable for prices).
    """
    cache_key = symbol.upper()
    now = datetime.now()
    ttl = get_cache_ttl()
    
    # Check cache
    if not force_refresh and cache_key in _ticker_info_cache:
        cached_time, cached_data = _ticker_info_cache[cache_key]
        if (now - cached_time).total_seconds() < ttl:
            logger.debug(f"Cache hit for {symbol} ticker info")
            return cached_data
    
    # Fetch from Yahoo API
    result = _fetch_price_direct_api(symbol)
    if result:
        _ticker_info_cache[cache_key] = (now, result)
        _last_fetch_times["prices"] = now
        _data_sources["prices"] = "yahoo_direct"
        return result
    
    # Return stale cache if available
    if cache_key in _ticker_info_cache:
        logger.info(f"Returning stale cache for {symbol}")
        return _ticker_info_cache[cache_key][1]
    
    record_error("prices", f"Failed to get price for {symbol}")
    return None


# =============================================================================
# OPTIONS DATA - Schwab API ONLY (has delta!)
# =============================================================================

def _get_schwab_chain(symbol: str, expiration_date: str) -> Optional[OptionChainResult]:
    """
    Get options chain from Schwab API.
    
    This is the ONLY source for options data because it has delta.
    """
    try:
        from app.modules.strategies.schwab_service import get_options_chain_schwab
        
        logger.info(f"[SCHWAB] Fetching options chain for {symbol} exp={expiration_date}")
        chain_data = get_options_chain_schwab(symbol, expiration_date)
        
        if chain_data and (chain_data.get('calls') or chain_data.get('puts')):
            calls_list = chain_data.get('calls', [])
            puts_list = chain_data.get('puts', [])
            
            def convert_to_dataframe(options_list, option_type):
                if not options_list:
                    return pd.DataFrame()
                
                converted = []
                for opt in options_list:
                    exp = opt.get('expirationDate', expiration_date).replace('-', '')
                    strike_str = str(int(opt.get('strike', 0) * 1000)).zfill(8)
                    opt_char = 'C' if option_type == 'call' else 'P'
                    contract_symbol = f"{symbol}{exp}{opt_char}{strike_str}"
                    
                    converted.append({
                        'contractSymbol': contract_symbol,
                        'strike': opt.get('strike', 0),
                        'bid': opt.get('bid', 0) or 0,
                        'ask': opt.get('ask', 0) or 0,
                        'lastPrice': opt.get('last', 0) or 0,
                        'volume': opt.get('volume', 0) or 0,
                        'openInterest': opt.get('openInterest', 0) or 0,
                        'impliedVolatility': opt.get('impliedVolatility', 0) or 0,
                        'delta': opt.get('delta'),
                        'gamma': opt.get('gamma'),
                        'theta': opt.get('theta'),
                        'vega': opt.get('vega'),
                        'inTheMoney': opt.get('inTheMoney', False),
                        '_source': 'schwab'
                    })
                
                return pd.DataFrame(converted)
            
            calls_df = convert_to_dataframe(calls_list, 'call')
            puts_df = convert_to_dataframe(puts_list, 'put')
            
            if not calls_df.empty and 'delta' in calls_df.columns:
                delta_count = calls_df['delta'].notna().sum()
                logger.info(f"[SCHWAB] {symbol}: {len(calls_df)} calls, {len(puts_df)} puts, {delta_count} with delta")
            
            return OptionChainResult(
                calls=calls_df,
                puts=puts_df,
                source="schwab"
            )
        else:
            logger.warning(f"[SCHWAB] {symbol}: No data returned")
            return None
            
    except ImportError:
        logger.error("[SCHWAB] Schwab service not available - check schwab_service.py")
        return None
    except Exception as e:
        logger.error(f"[SCHWAB] {symbol}: Error - {e}")
        return None


def get_option_expirations(symbol: str, force_refresh: bool = False) -> List[str]:
    """
    Get available option expiration dates.
    
    Uses Schwab API only.
    """
    cache_key = symbol.upper()
    now = datetime.now()
    ttl = get_cache_ttl(data_type="options")
    
    # Check cache
    if not force_refresh and cache_key in _options_expirations_cache:
        cached_time, cached_data = _options_expirations_cache[cache_key]
        if (now - cached_time).total_seconds() < ttl:
            logger.debug(f"Cache hit for {symbol} expirations")
            return cached_data
    
    # Fetch from Schwab
    try:
        from app.modules.strategies.schwab_service import get_option_expirations_schwab
        
        logger.info(f"[EXPIRATIONS] {symbol}: Fetching from Schwab")
        expirations = get_option_expirations_schwab(symbol)
        
        if expirations:
            _options_expirations_cache[cache_key] = (now, expirations)
            _last_fetch_times["options"] = now
            _data_sources["expirations"] = "schwab"
            clear_error("expirations")
            logger.info(f"[EXPIRATIONS] {symbol}: Got {len(expirations)} expirations")
            return expirations
        else:
            logger.warning(f"[EXPIRATIONS] {symbol}: No expirations returned from Schwab")
            
    except ImportError:
        logger.error("[EXPIRATIONS] Schwab service not available")
    except Exception as e:
        logger.error(f"[EXPIRATIONS] {symbol}: Schwab failed - {e}")
    
    # Return stale cache if available
    if cache_key in _options_expirations_cache:
        logger.info(f"Returning stale cache for {symbol} expirations")
        return _options_expirations_cache[cache_key][1]
    
    record_error("expirations", f"Schwab failed for {symbol}")
    return []


def get_option_chain(
    symbol: str, 
    expiration_date: str = None,
    force_refresh: bool = False
) -> Optional[OptionChainResult]:
    """
    Get option chain with caching.
    
    Uses Schwab API only (has delta data).
    """
    if not expiration_date:
        logger.warning(f"[CHAIN] {symbol}: No expiration date provided")
        return None
    
    cache_key = f"{symbol.upper()}_{expiration_date}"
    now = datetime.now()
    ttl = get_cache_ttl(data_type="options")
    
    # Check cache
    if not force_refresh and cache_key in _option_chain_cache:
        cached_time, cached_data = _option_chain_cache[cache_key]
        if (now - cached_time).total_seconds() < ttl:
            logger.debug(f"Cache hit for {symbol} {expiration_date} option chain")
            return cached_data
    
    # Fetch from Schwab
    result = _get_schwab_chain(symbol, expiration_date)
    
    if result:
        _option_chain_cache[cache_key] = (now, result)
        _last_fetch_times["options"] = now
        _data_sources["options"] = "schwab"
        clear_error("options")
        return result
    
    # Return stale cache if available
    if cache_key in _option_chain_cache:
        logger.info(f"Returning stale cache for {symbol} {expiration_date}")
        return _option_chain_cache[cache_key][1]
    
    record_error("options", f"Schwab failed for {symbol} {expiration_date}")
    return None


# =============================================================================
# OTHER DATA (using yfinance for non-critical data)
# =============================================================================

def get_earnings_date(symbol: str, force_refresh: bool = False) -> Optional[date]:
    """Get earnings date with caching (24hr TTL)."""
    import yfinance as yf
    
    cache_key = symbol.upper()
    now = datetime.now()
    EARNINGS_TTL = 86400  # 24 hours
    
    if not force_refresh and cache_key in _earnings_date_cache:
        cached_time, cached_data = _earnings_date_cache[cache_key]
        if (now - cached_time).total_seconds() < EARNINGS_TTL:
            return cached_data
    
    try:
        ticker = yf.Ticker(symbol)
        calendar = ticker.calendar
        
        if calendar is None or isinstance(calendar, dict):
            _earnings_date_cache[cache_key] = (now, None)
            return None
        
        if not isinstance(calendar, pd.DataFrame) or calendar.empty:
            _earnings_date_cache[cache_key] = (now, None)
            return None
        
        earnings_date_series = calendar.get('Earnings Date')
        if earnings_date_series is not None and len(earnings_date_series) > 0:
            result = earnings_date_series[0].date() if hasattr(earnings_date_series[0], 'date') else None
            _earnings_date_cache[cache_key] = (now, result)
            return result
            
    except Exception as e:
        logger.debug(f"[EARNINGS] {symbol}: Error - {e}")
    
    _earnings_date_cache[cache_key] = (now, None)
    return None


def get_price_history(symbol: str, period: str = "5d", force_refresh: bool = False) -> Optional[pd.DataFrame]:
    """Get price history with caching."""
    import yfinance as yf
    
    cache_key = f"{symbol.upper()}_{period}"
    now = datetime.now()
    ttl = get_cache_ttl()
    
    if not force_refresh and cache_key in _price_history_cache:
        cached_time, cached_data = _price_history_cache[cache_key]
        if (now - cached_time).total_seconds() < ttl:
            return cached_data
    
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        
        if hist is not None and not hist.empty:
            _price_history_cache[cache_key] = (now, hist)
            _last_fetch_times["history"] = now
            return hist
            
    except Exception as e:
        logger.debug(f"[HISTORY] {symbol}: Error - {e}")
    
    if cache_key in _price_history_cache:
        return _price_history_cache[cache_key][1]
    
    return None


# =============================================================================
# CACHE MANAGEMENT
# =============================================================================

def clear_cache(symbol: Optional[str] = None):
    """Clear cached data."""
    global _ticker_info_cache, _option_chain_cache, _options_expirations_cache, _earnings_date_cache, _price_history_cache
    
    if symbol:
        symbol = symbol.upper()
        _ticker_info_cache.pop(symbol, None)
        _options_expirations_cache.pop(symbol, None)
        _earnings_date_cache.pop(symbol, None)
        for cache in [_option_chain_cache, _price_history_cache]:
            keys_to_remove = [k for k in cache.keys() if k.startswith(symbol)]
            for k in keys_to_remove:
                cache.pop(k, None)
        logger.info(f"Cleared cache for {symbol}")
    else:
        _ticker_info_cache.clear()
        _option_chain_cache.clear()
        _options_expirations_cache.clear()
        _earnings_date_cache.clear()
        _price_history_cache.clear()
        logger.info("Cleared all cache")


def get_cache_stats() -> Dict[str, Any]:
    """Get statistics about the cache."""
    return {
        "ticker_info_entries": len(_ticker_info_cache),
        "option_chain_entries": len(_option_chain_cache),
        "expirations_entries": len(_options_expirations_cache),
        "earnings_date_entries": len(_earnings_date_cache),
        "price_history_entries": len(_price_history_cache),
        "current_ttl_seconds": get_cache_ttl(),
        "data_sources": dict(_data_sources),
        "last_fetch_times": {
            k: v.isoformat() if v else None 
            for k, v in _last_fetch_times.items()
        }
    }
