"""
Yahoo Finance Option Data Provider

Provides option data from Yahoo Finance API.

Features:
- No authentication required
- Broadly available
- Good for metadata and fallback

Limitations:
- Rate limited (can get 429 errors)
- Delta values often missing
- Delayed quotes during market hours

Note: This is primarily a fallback provider when Schwab is unavailable.
"""

import logging
import pandas as pd
from datetime import date, datetime
from typing import Dict, List, Optional, Any

from .base import OptionDataProvider, OptionChainData, OptionQuote

logger = logging.getLogger(__name__)


class YahooProvider(OptionDataProvider):
    """
    Yahoo Finance provider for option data.
    
    Priority: 50 (fallback - used when primary sources fail)
    """
    
    name = "yahoo"
    priority = 50  # Lower priority than Schwab
    supports_greeks = False  # Yahoo often doesn't have delta
    supports_real_time = False  # Delayed quotes
    
    def __init__(self):
        self._last_error: Optional[str] = None
        self._error_count: int = 0
        self._rate_limited_until: Optional[datetime] = None
    
    def is_available(self) -> bool:
        """Yahoo is always available (no auth required)."""
        # Check if we're rate limited
        if self._rate_limited_until:
            if datetime.now() < self._rate_limited_until:
                return False
            self._rate_limited_until = None
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """Get Yahoo provider status."""
        return {
            'provider': self.name,
            'priority': self.priority,
            'configured': True,  # Always configured
            'available': self.is_available(),
            'last_error': self._last_error,
            'error_count': self._error_count,
            'rate_limited_until': self._rate_limited_until.isoformat() if self._rate_limited_until else None,
            'note': 'Fallback provider - no authentication required'
        }
    
    def get_option_chain(
        self, 
        symbol: str, 
        expiration_date: date
    ) -> Optional[OptionChainData]:
        """Fetch option chain from Yahoo Finance."""
        if not self.is_available():
            return None
        
        try:
            import yfinance as yf
            
            exp_str = expiration_date.strftime("%Y-%m-%d")
            logger.info(f"[YAHOO] Fetching chain for {symbol} exp={exp_str}")
            
            ticker = yf.Ticker(symbol)
            
            # Get available expirations
            try:
                expirations = list(ticker.options)
            except Exception as e:
                self._last_error = f"Failed to get expirations: {e}"
                return None
            
            if not expirations:
                self._last_error = f"No options available for {symbol}"
                return None
            
            # Find matching or closest expiration
            if exp_str not in expirations:
                closest = min(expirations, 
                             key=lambda x: abs((datetime.strptime(x, "%Y-%m-%d").date() - expiration_date).days))
                logger.info(f"[YAHOO] Using closest expiration {closest} instead of {exp_str}")
                exp_str = closest
            
            # Get option chain
            opt_chain = ticker.option_chain(exp_str)
            
            if opt_chain is None:
                self._last_error = f"No chain returned for {symbol}"
                return None
            
            # Get underlying price
            underlying_price = None
            try:
                info = ticker.info
                underlying_price = info.get('currentPrice') or info.get('regularMarketPrice')
            except:
                pass
            
            # Clear error state on success
            self._last_error = None
            self._error_count = 0
            
            return OptionChainData(
                symbol=symbol,
                expiration=exp_str,
                calls=opt_chain.calls,
                puts=opt_chain.puts,
                underlying_price=underlying_price,
                source=self.name,
                fetched_at=datetime.now()
            )
            
        except Exception as e:
            error_str = str(e)
            self._last_error = error_str
            self._error_count += 1
            
            # Check for rate limiting
            if '429' in error_str or 'rate' in error_str.lower():
                from datetime import timedelta
                self._rate_limited_until = datetime.now() + timedelta(minutes=5)
                logger.warning(f"[YAHOO] Rate limited, pausing until {self._rate_limited_until}")
            
            logger.error(f"[YAHOO] Error fetching chain for {symbol}: {e}")
            return None
    
    def get_expirations(self, symbol: str) -> List[str]:
        """Get available expirations from Yahoo Finance."""
        if not self.is_available():
            return []
        
        try:
            import yfinance as yf
            
            ticker = yf.Ticker(symbol)
            expirations = list(ticker.options)
            
            logger.debug(f"[YAHOO] {symbol}: {len(expirations)} expirations")
            return expirations
            
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"[YAHOO] Error fetching expirations for {symbol}: {e}")
            return []
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price from Yahoo Finance."""
        if not self.is_available():
            return None
        
        try:
            import yfinance as yf
            
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            price = info.get('currentPrice') or info.get('regularMarketPrice')
            return float(price) if price else None
            
        except Exception as e:
            logger.warning(f"[YAHOO] Error getting price for {symbol}: {e}")
            return None

