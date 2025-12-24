"""
Option Data Service

Manages multiple option data providers with priority-based fallback.

Usage:
    from app.modules.strategies.option_providers import get_option_service
    
    service = get_option_service()
    chain = service.get_option_chain('AAPL', expiration_date)
    quote = service.get_quote('AAPL', 200.0, 'call', expiration_date)

Adding/Removing Providers:
    Edit the PROVIDER_CLASSES list in this file to add or remove providers.
    Providers are tried in order of their `priority` attribute (lower = higher priority).
"""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional, Any, Type
import threading

from .base import OptionDataProvider, OptionChainData, OptionQuote, ProviderStatus

logger = logging.getLogger(__name__)

# =============================================================================
# PROVIDER REGISTRATION
# =============================================================================
# Add or remove providers here. Order doesn't matter - providers are sorted by priority.

PROVIDER_CLASSES: List[Type[OptionDataProvider]] = []


def _load_providers():
    """Load provider classes. Called once at module init."""
    global PROVIDER_CLASSES
    
    providers = []
    
    # Schwab Provider (priority 10 - highest)
    try:
        from .schwab_provider import SchwabProvider
        providers.append(SchwabProvider)
        logger.debug("Registered SchwabProvider")
    except ImportError as e:
        logger.warning(f"Could not load SchwabProvider: {e}")
    
    # Yahoo Provider (priority 50 - fallback)
    try:
        from .yahoo_provider import YahooProvider
        providers.append(YahooProvider)
        logger.debug("Registered YahooProvider")
    except ImportError as e:
        logger.warning(f"Could not load YahooProvider: {e}")
    
    # =========================================================================
    # ADD NEW PROVIDERS HERE
    # =========================================================================
    # Example:
    # try:
    #     from .ibkr_provider import IBKRProvider
    #     providers.append(IBKRProvider)
    # except ImportError as e:
    #     logger.warning(f"Could not load IBKRProvider: {e}")
    
    PROVIDER_CLASSES = providers


# Load providers on module import
_load_providers()


# =============================================================================
# SERVICE SINGLETON
# =============================================================================

_service_instance: Optional['OptionDataService'] = None
_service_lock = threading.Lock()


def get_option_service() -> 'OptionDataService':
    """Get the singleton OptionDataService instance."""
    global _service_instance
    
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = OptionDataService()
    
    return _service_instance


def reset_service():
    """Reset the service (useful for testing)."""
    global _service_instance
    with _service_lock:
        _service_instance = None


# =============================================================================
# OPTION DATA SERVICE
# =============================================================================

class OptionDataService:
    """
    Unified option data service with provider fallback.
    
    Tries providers in priority order until one succeeds.
    Caches provider instances and tracks their status.
    """
    
    def __init__(self, provider_classes: Optional[List[Type[OptionDataProvider]]] = None):
        """
        Initialize the service.
        
        Args:
            provider_classes: Optional list of provider classes to use.
                            If None, uses PROVIDER_CLASSES from this module.
        """
        classes = provider_classes or PROVIDER_CLASSES
        
        # Instantiate providers and sort by priority
        self._providers: List[OptionDataProvider] = []
        for cls in classes:
            try:
                provider = cls()
                self._providers.append(provider)
            except Exception as e:
                logger.error(f"Failed to instantiate {cls.__name__}: {e}")
        
        # Sort by priority (lower = higher priority)
        self._providers.sort(key=lambda p: p.priority)
        
        # Log active providers
        provider_names = [f"{p.name}(pri={p.priority})" for p in self._providers]
        logger.info(f"OptionDataService initialized with providers: {', '.join(provider_names)}")
        
        # Cache settings
        self._cache: Dict[str, tuple] = {}  # key -> (timestamp, data)
        self._cache_ttl = 300  # 5 minutes default
    
    @property
    def providers(self) -> List[OptionDataProvider]:
        """Get list of registered providers."""
        return self._providers.copy()
    
    def get_available_providers(self) -> List[OptionDataProvider]:
        """Get list of currently available providers."""
        return [p for p in self._providers if p.is_available()]
    
    def get_provider_status(self) -> List[Dict[str, Any]]:
        """Get status of all providers."""
        return [p.get_status() for p in self._providers]
    
    def get_primary_provider(self) -> Optional[OptionDataProvider]:
        """Get the highest-priority available provider."""
        for provider in self._providers:
            if provider.is_available():
                return provider
        return None
    
    # =========================================================================
    # CORE API
    # =========================================================================
    
    def get_option_chain(
        self, 
        symbol: str, 
        expiration_date: date,
        require_greeks: bool = False
    ) -> Optional[OptionChainData]:
        """
        Get option chain, trying providers in priority order.
        
        Args:
            symbol: Stock symbol
            expiration_date: Expiration date
            require_greeks: If True, skip providers that don't support Greeks
        
        Returns:
            OptionChainData or None if all providers fail
        """
        for provider in self._providers:
            if not provider.is_available():
                logger.debug(f"Skipping unavailable provider: {provider.name}")
                continue
            
            if require_greeks and not provider.supports_greeks:
                logger.debug(f"Skipping {provider.name} - doesn't support Greeks")
                continue
            
            try:
                chain = provider.get_option_chain(symbol, expiration_date)
                if chain:
                    logger.debug(f"Got chain for {symbol} from {provider.name}")
                    return chain
            except Exception as e:
                logger.warning(f"Provider {provider.name} failed for {symbol}: {e}")
                continue
        
        logger.warning(f"All providers failed for {symbol} {expiration_date}")
        return None
    
    def get_quote(
        self, 
        symbol: str, 
        strike: float, 
        option_type: str,
        expiration_date: date
    ) -> Optional[OptionQuote]:
        """
        Get quote for a specific option contract.
        
        Args:
            symbol: Stock symbol
            strike: Strike price
            option_type: 'call' or 'put'
            expiration_date: Expiration date
        
        Returns:
            OptionQuote or None
        """
        for provider in self._providers:
            if not provider.is_available():
                continue
            
            try:
                quote = provider.get_quote(symbol, strike, option_type, expiration_date)
                if quote:
                    logger.debug(f"Got quote for {symbol} ${strike} from {provider.name}")
                    return quote
            except Exception as e:
                logger.warning(f"Provider {provider.name} failed for quote: {e}")
                continue
        
        return None
    
    def get_expirations(self, symbol: str) -> List[str]:
        """
        Get available expiration dates.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            List of expiration dates in YYYY-MM-DD format
        """
        for provider in self._providers:
            if not provider.is_available():
                continue
            
            try:
                expirations = provider.get_expirations(symbol)
                if expirations:
                    logger.debug(f"Got {len(expirations)} expirations for {symbol} from {provider.name}")
                    return expirations
            except Exception as e:
                logger.warning(f"Provider {provider.name} failed for expirations: {e}")
                continue
        
        return []
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current stock price.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Current price or None
        """
        for provider in self._providers:
            if not provider.is_available():
                continue
            
            try:
                price = provider.get_current_price(symbol)
                if price:
                    logger.debug(f"Got price ${price} for {symbol} from {provider.name}")
                    return price
            except Exception as e:
                logger.warning(f"Provider {provider.name} failed for price: {e}")
                continue
        
        return None
    
    def find_strike_by_delta(
        self,
        symbol: str,
        expiration_date: date,
        target_delta: float = 0.10,
        option_type: str = 'call',
        current_price: Optional[float] = None
    ) -> Optional[OptionQuote]:
        """
        Find strike closest to target delta.
        
        Prefers providers with Greek support.
        
        Args:
            symbol: Stock symbol
            expiration_date: Expiration date
            target_delta: Target absolute delta (e.g., 0.10)
            option_type: 'call' or 'put'
            current_price: Current stock price for OTM filtering
        
        Returns:
            OptionQuote for matching strike, or None
        """
        # Get current price if not provided
        if current_price is None:
            current_price = self.get_current_price(symbol)
        
        # Try providers with Greeks first
        for provider in self._providers:
            if not provider.is_available():
                continue
            
            if not provider.supports_greeks:
                continue
            
            try:
                chain = provider.get_option_chain(symbol, expiration_date)
                if chain:
                    quote = chain.find_strike_by_delta(target_delta, option_type, current_price)
                    if quote:
                        logger.debug(f"Found delta {target_delta} strike from {provider.name}")
                        return quote
            except Exception as e:
                logger.warning(f"Provider {provider.name} failed for delta search: {e}")
                continue
        
        # Fall back to any provider
        chain = self.get_option_chain(symbol, expiration_date)
        if chain:
            return chain.find_strike_by_delta(target_delta, option_type, current_price)
        
        return None
    
    # =========================================================================
    # COMPATIBILITY LAYER
    # =========================================================================
    # These methods provide backwards compatibility with the old OptionChainFetcher
    
    def get_option_chain_legacy(
        self, 
        symbol: str, 
        expiration_date: date
    ) -> Optional[Dict[str, Any]]:
        """
        Get option chain in legacy format (dict with 'calls' and 'puts' DataFrames).
        
        For backwards compatibility with existing code.
        """
        chain = self.get_option_chain(symbol, expiration_date)
        if not chain:
            return None
        
        return {
            'expiration': chain.expiration,
            'calls': chain.calls,
            'puts': chain.puts,
        }
    
    def get_option_quote_legacy(
        self,
        symbol: str,
        strike_price: float,
        option_type: str,
        expiration_date: date
    ) -> Optional[Any]:
        """
        Get option quote in legacy OptionQuote format.
        
        For backwards compatibility with existing code.
        """
        from app.modules.strategies.option_monitor import OptionQuote as LegacyQuote
        
        quote = self.get_quote(symbol, strike_price, option_type, expiration_date)
        if not quote:
            return None
        
        return LegacyQuote(
            contract_symbol=quote.contract_symbol,
            strike=quote.strike,
            bid=quote.bid,
            ask=quote.ask,
            last_price=quote.last_price,
            volume=quote.volume,
            open_interest=quote.open_interest,
            implied_volatility=quote.implied_volatility,
            in_the_money=quote.in_the_money
        )

