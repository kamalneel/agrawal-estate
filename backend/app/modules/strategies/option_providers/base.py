"""
Base classes and interfaces for Option Data Providers.

This defines the contract that all option data providers must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import pandas as pd


class ProviderStatus(Enum):
    """Status of a data provider."""
    AVAILABLE = "available"      # Ready to use
    UNAVAILABLE = "unavailable"  # Not configured or credentials missing
    ERROR = "error"              # Configured but experiencing errors
    RATE_LIMITED = "rate_limited"  # Temporarily blocked due to rate limits


@dataclass
class OptionQuote:
    """Represents a quote for a specific option contract."""
    contract_symbol: str
    strike: float
    bid: float
    ask: float
    last_price: float
    volume: int = 0
    open_interest: int = 0
    implied_volatility: float = 0.0
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    in_the_money: bool = False
    
    @property
    def mid_price(self) -> float:
        """Calculate mid price between bid and ask."""
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.last_price or self.bid or self.ask
    
    @property
    def premium_per_contract(self) -> float:
        """Premium in dollars per contract (100 shares)."""
        return self.bid * 100 if self.bid > 0 else self.last_price * 100


@dataclass
class OptionChainData:
    """Represents an option chain for a symbol and expiration."""
    symbol: str
    expiration: str  # YYYY-MM-DD format
    calls: pd.DataFrame  # DataFrame with columns: strike, bid, ask, delta, etc.
    puts: pd.DataFrame
    underlying_price: Optional[float] = None
    source: str = "unknown"
    fetched_at: datetime = field(default_factory=datetime.now)
    
    def get_call_quote(self, strike: float, tolerance: float = 0.01) -> Optional[OptionQuote]:
        """Get quote for a specific call strike."""
        return self._get_quote(self.calls, strike, 'call', tolerance)
    
    def get_put_quote(self, strike: float, tolerance: float = 0.01) -> Optional[OptionQuote]:
        """Get quote for a specific put strike."""
        return self._get_quote(self.puts, strike, 'put', tolerance)
    
    def _get_quote(self, df: pd.DataFrame, strike: float, 
                   option_type: str, tolerance: float) -> Optional[OptionQuote]:
        """Get quote from DataFrame."""
        if df.empty:
            return None
        
        # Find matching strike
        matching = df[abs(df['strike'] - strike) < tolerance]
        
        if matching.empty:
            # Find closest
            closest_idx = (abs(df['strike'] - strike)).idxmin()
            matching = df.loc[[closest_idx]]
        
        row = matching.iloc[0]
        
        return OptionQuote(
            contract_symbol=row.get('contractSymbol', f"{self.symbol}_{strike}_{option_type[0].upper()}"),
            strike=row['strike'],
            bid=row.get('bid', 0) or 0,
            ask=row.get('ask', 0) or 0,
            last_price=row.get('lastPrice', 0) or 0,
            volume=int(row.get('volume', 0) or 0),
            open_interest=int(row.get('openInterest', 0) or 0),
            implied_volatility=row.get('impliedVolatility', 0) or 0,
            delta=row.get('delta'),
            gamma=row.get('gamma'),
            theta=row.get('theta'),
            vega=row.get('vega'),
            in_the_money=row.get('inTheMoney', False)
        )
    
    def find_strike_by_delta(self, target_delta: float, option_type: str = 'call',
                              current_price: Optional[float] = None) -> Optional[OptionQuote]:
        """
        Find the strike closest to target delta.
        
        Args:
            target_delta: Target absolute delta (e.g., 0.10 for Delta 10)
            option_type: 'call' or 'put'
            current_price: Current stock price for OTM filtering
        
        Returns:
            OptionQuote for the matching strike, or None
        """
        df = self.calls if option_type.lower() == 'call' else self.puts
        
        if df.empty:
            return None
        
        # Filter to OTM only if price provided
        if current_price:
            if option_type.lower() == 'call':
                df = df[df['strike'] > current_price]
            else:
                df = df[df['strike'] < current_price]
        
        if df.empty:
            return None
        
        # Filter to rows with valid delta
        if 'delta' not in df.columns:
            return None
        
        valid_delta = df[df['delta'].notna()].copy()
        if valid_delta.empty:
            return None
        
        # Find closest to target delta
        valid_delta['delta_diff'] = abs(abs(valid_delta['delta']) - target_delta)
        best_idx = valid_delta['delta_diff'].idxmin()
        best_row = valid_delta.loc[best_idx]
        
        return OptionQuote(
            contract_symbol=best_row.get('contractSymbol', ''),
            strike=best_row['strike'],
            bid=best_row.get('bid', 0) or 0,
            ask=best_row.get('ask', 0) or 0,
            last_price=best_row.get('lastPrice', 0) or 0,
            delta=best_row.get('delta'),
            gamma=best_row.get('gamma'),
            theta=best_row.get('theta'),
            vega=best_row.get('vega'),
            in_the_money=best_row.get('inTheMoney', False)
        )


class OptionDataProvider(ABC):
    """
    Abstract base class for option data providers.
    
    All providers must implement these methods to be used by OptionDataService.
    
    To create a new provider:
    1. Subclass OptionDataProvider
    2. Implement all abstract methods
    3. Set the `name` and `priority` class attributes
    """
    
    # Provider identification
    name: str = "base"  # Unique name for this provider
    priority: int = 100  # Lower = higher priority (used for fallback order)
    
    # Feature flags - override in subclass
    supports_greeks: bool = False  # Does this provider return delta/gamma/theta/vega?
    supports_real_time: bool = False  # Real-time or delayed quotes?
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this provider is available and configured.
        
        Returns:
            True if provider can be used, False otherwise
        """
        pass
    
    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """
        Get detailed status information about this provider.
        
        Returns:
            Dict with status info (configured, authenticated, last_error, etc.)
        """
        pass
    
    @abstractmethod
    def get_option_chain(
        self, 
        symbol: str, 
        expiration_date: date
    ) -> Optional[OptionChainData]:
        """
        Fetch option chain for a symbol and expiration.
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            expiration_date: Expiration date
        
        Returns:
            OptionChainData or None if unavailable
        """
        pass
    
    @abstractmethod
    def get_expirations(self, symbol: str) -> List[str]:
        """
        Get available expiration dates for a symbol.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            List of expiration dates in YYYY-MM-DD format
        """
        pass
    
    def get_quote(
        self, 
        symbol: str, 
        strike: float, 
        option_type: str,
        expiration_date: date
    ) -> Optional[OptionQuote]:
        """
        Get quote for a specific option contract.
        
        Default implementation fetches full chain and extracts quote.
        Override for more efficient single-quote fetching if provider supports it.
        
        Args:
            symbol: Stock symbol
            strike: Strike price
            option_type: 'call' or 'put'
            expiration_date: Expiration date
        
        Returns:
            OptionQuote or None
        """
        chain = self.get_option_chain(symbol, expiration_date)
        if not chain:
            return None
        
        if option_type.lower() == 'call':
            return chain.get_call_quote(strike)
        else:
            return chain.get_put_quote(strike)
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current stock price.
        
        Default implementation uses underlying price from option chain.
        Override for more efficient price fetching if provider supports it.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Current price or None
        """
        # Default: try to get from any expiration's chain
        expirations = self.get_expirations(symbol)
        if expirations:
            from datetime import datetime
            exp_date = datetime.strptime(expirations[0], "%Y-%m-%d").date()
            chain = self.get_option_chain(symbol, exp_date)
            if chain and chain.underlying_price:
                return chain.underlying_price
        return None

