"""
Option Data Providers Module

A modular, extensible system for fetching option data from multiple sources.

Architecture:
- OptionDataProvider: Abstract base class defining the interface
- Concrete providers: SchwabProvider, YahooProvider, etc.
- OptionDataService: Manages providers with priority-based fallback

Adding a new provider:
1. Create a new file in this directory (e.g., my_broker_provider.py)
2. Implement the OptionDataProvider interface
3. Register it in OptionDataService.PROVIDERS

Removing a provider:
1. Remove from OptionDataService.PROVIDERS
2. Optionally delete the provider file
"""

from .base import OptionDataProvider, OptionChainData, OptionQuote, ProviderStatus
from .service import OptionDataService, get_option_service

__all__ = [
    'OptionDataProvider',
    'OptionChainData', 
    'OptionQuote',
    'ProviderStatus',
    'OptionDataService',
    'get_option_service',
]

