"""
Schwab API Option Data Provider

Provides option data from Charles Schwab API.

Features:
- Real-time quotes during market hours
- Full Greeks (delta, gamma, theta, vega)
- Reliable rate limits (120 req/min)

Requirements:
- SCHWAB_APP_KEY and SCHWAB_APP_SECRET in .env
- Initial OAuth authentication via schwab_service.authenticate_schwab()
"""

import logging
import pandas as pd
from datetime import date, datetime
from typing import Dict, List, Optional, Any

from .base import OptionDataProvider, OptionChainData, OptionQuote

logger = logging.getLogger(__name__)


class SchwabProvider(OptionDataProvider):
    """
    Schwab API provider for option data.
    
    Priority: 10 (highest - preferred source)
    """
    
    name = "schwab"
    priority = 10  # Highest priority
    supports_greeks = True
    supports_real_time = True
    
    def __init__(self):
        self._last_error: Optional[str] = None
        self._error_count: int = 0
    
    def is_available(self) -> bool:
        """Check if Schwab is configured and authenticated."""
        try:
            from app.modules.strategies.schwab_service import is_schwab_configured
            return is_schwab_configured()
        except ImportError:
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get detailed Schwab status."""
        try:
            from app.modules.strategies.schwab_service import get_schwab_status
            status = get_schwab_status()
            status['provider'] = self.name
            status['priority'] = self.priority
            status['last_error'] = self._last_error
            status['error_count'] = self._error_count
            return status
        except ImportError:
            return {
                'provider': self.name,
                'configured': False,
                'error': 'schwab_service module not found'
            }
    
    def get_option_chain(
        self, 
        symbol: str, 
        expiration_date: date
    ) -> Optional[OptionChainData]:
        """Fetch option chain from Schwab."""
        if not self.is_available():
            return None
        
        try:
            from app.modules.strategies.schwab_service import get_options_chain_schwab
            
            exp_str = expiration_date.strftime("%Y-%m-%d")
            logger.info(f"[SCHWAB] Fetching chain for {symbol} exp={exp_str}")
            
            chain_data = get_options_chain_schwab(symbol, exp_str)
            
            if not chain_data:
                self._last_error = f"No data returned for {symbol}"
                return None
            
            calls_list = chain_data.get('calls', [])
            puts_list = chain_data.get('puts', [])
            
            if not calls_list and not puts_list:
                self._last_error = f"Empty chain for {symbol}"
                return None
            
            # Convert to DataFrames
            calls_df = self._to_dataframe(calls_list, symbol, 'call', expiration_date)
            puts_df = self._to_dataframe(puts_list, symbol, 'put', expiration_date)
            
            logger.debug(f"[SCHWAB] {symbol}: {len(calls_df)} calls, {len(puts_df)} puts")
            
            # Clear error state on success
            self._last_error = None
            self._error_count = 0
            
            return OptionChainData(
                symbol=symbol,
                expiration=exp_str,
                calls=calls_df,
                puts=puts_df,
                underlying_price=chain_data.get('underlying_price'),
                source=self.name,
                fetched_at=datetime.now()
            )
            
        except Exception as e:
            self._last_error = str(e)
            self._error_count += 1
            logger.error(f"[SCHWAB] Error fetching chain for {symbol}: {e}")
            return None
    
    def _to_dataframe(
        self, 
        options_list: List[Dict], 
        symbol: str,
        option_type: str, 
        expiration_date: date
    ) -> pd.DataFrame:
        """Convert Schwab options list to DataFrame."""
        if not options_list:
            return pd.DataFrame()
        
        rows = []
        exp_str = expiration_date.strftime("%y%m%d")
        
        for opt in options_list:
            strike = opt.get('strike', 0)
            strike_str = f"{int(strike * 1000):08d}"
            type_char = 'C' if option_type == 'call' else 'P'
            contract_symbol = f"{symbol}{exp_str}{type_char}{strike_str}"
            
            rows.append({
                'contractSymbol': contract_symbol,
                'strike': strike,
                'bid': opt.get('bid', 0) or 0,
                'ask': opt.get('ask', 0) or 0,
                'lastPrice': opt.get('last', 0) or 0,
                'volume': opt.get('volume', 0) or 0,
                'openInterest': opt.get('openInterest', 0) or 0,
                'impliedVolatility': 0,
                'delta': opt.get('delta'),
                'gamma': opt.get('gamma'),
                'theta': opt.get('theta'),
                'vega': opt.get('vega'),
                'inTheMoney': opt.get('inTheMoney', False),
            })
        
        return pd.DataFrame(rows)
    
    def get_expirations(self, symbol: str) -> List[str]:
        """Get available expirations from Schwab."""
        if not self.is_available():
            return []
        
        try:
            from app.modules.strategies.schwab_service import get_option_expirations_schwab
            
            expirations = get_option_expirations_schwab(symbol)
            logger.debug(f"[SCHWAB] {symbol}: {len(expirations)} expirations")
            return expirations
            
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"[SCHWAB] Error fetching expirations for {symbol}: {e}")
            return []
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price from Schwab (via option chain underlying)."""
        if not self.is_available():
            return None
        
        try:
            from app.modules.strategies.schwab_service import get_options_chain_schwab
            
            # Get chain without specific expiration to get underlying price
            chain = get_options_chain_schwab(symbol)
            if chain and chain.get('underlying_price'):
                return float(chain['underlying_price'])
            return None
            
        except Exception as e:
            logger.warning(f"[SCHWAB] Error getting price for {symbol}: {e}")
            return None

