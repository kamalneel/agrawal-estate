"""
Unified Option Data Service

DEPRECATED: This module is kept for backwards compatibility.
New code should use: app.modules.strategies.option_providers

Provides a single interface for all option-related data:
- Option chain (calls/puts with Greeks)
- Option expirations
- Stock prices

Data source priority (managed by provider system):
1. Schwab API (priority 10) - Real-time, has Greeks
2. Yahoo Finance (priority 50) - Fallback

To add/remove providers, edit:
app/modules/strategies/option_providers/service.py
"""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


def _get_service():
    """Get the option data service."""
    from app.modules.strategies.option_providers import get_option_service
    return get_option_service()


def get_option_chain_fetcher():
    """Get singleton OptionChainFetcher instance (backwards compatibility)."""
    from app.modules.strategies.option_monitor import OptionChainFetcher
    return OptionChainFetcher()


def get_option_expirations(symbol: str) -> List[str]:
    """
    Get available option expiration dates.
    
    Uses provider system with automatic fallback.
    """
    return _get_service().get_expirations(symbol)


def get_option_chain(symbol: str, expiration_date: date) -> Optional[Dict]:
    """
    Get option chain for a symbol and expiration date.
    
    Returns dict with 'expiration', 'calls', 'puts' (DataFrames).
    """
    return _get_service().get_option_chain_legacy(symbol, expiration_date)


def get_option_quote(
    symbol: str,
    strike_price: float,
    option_type: str,
    expiration_date: date
) -> Optional[Any]:
    """Get quote for a specific option contract."""
    return _get_service().get_option_quote_legacy(
        symbol, strike_price, option_type, expiration_date
    )


def get_current_price(symbol: str) -> Optional[float]:
    """Get current stock price."""
    return _get_service().get_current_price(symbol)


def get_stock_info(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get stock info (price, name, etc.).
    
    Uses provider system for price, Yahoo for metadata.
    """
    result = {}
    
    # Get price from provider system
    price = _get_service().get_current_price(symbol)
    if price:
        result['currentPrice'] = price
        result['regularMarketPrice'] = price
    
    # Get additional info from Yahoo (name, etc.)
    try:
        from app.modules.strategies.yahoo_cache import get_ticker_info
        yahoo_info = get_ticker_info(symbol)
        if yahoo_info:
            for key in ['shortName', 'longName', 'sector', 'industry']:
                if key in yahoo_info:
                    result[key] = yahoo_info[key]
            
            if 'currentPrice' not in result:
                result['currentPrice'] = yahoo_info.get('currentPrice') or yahoo_info.get('regularMarketPrice')
                result['regularMarketPrice'] = result.get('currentPrice')
    except Exception as e:
        logger.warning(f"[OPTIONS] Yahoo info failed for {symbol}: {e}")
    
    return result if result else None


def find_strike_by_delta(
    symbol: str,
    option_type: str,
    expiration_date: str,
    target_delta: float = 0.10,
    current_price: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """Find the strike closest to target delta."""
    exp_date = datetime.strptime(expiration_date, "%Y-%m-%d").date()
    
    quote = _get_service().find_strike_by_delta(
        symbol=symbol,
        expiration_date=exp_date,
        target_delta=target_delta,
        option_type=option_type,
        current_price=current_price
    )
    
    if quote:
        return {
            'strike': quote.strike,
            'delta': quote.delta,
            'bid': quote.bid,
            'ask': quote.ask
        }
    
    return None

