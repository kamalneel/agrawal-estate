"""
Simple in-memory cache for API responses.

This provides a lightweight caching solution for expensive API endpoints
without requiring external dependencies like Redis.
"""

import time
import hashlib
import json
from typing import Any, Dict, Optional, Callable
from functools import wraps
from datetime import datetime
import pytz
import logging

logger = logging.getLogger(__name__)

# In-memory cache storage
_cache: Dict[str, Dict[str, Any]] = {}


def _get_cache_ttl_for_market_hours(base_ttl: int = 60, extended_ttl: int = 300) -> int:
    """
    Get cache TTL based on market hours.
    
    During market hours: use base_ttl
    Outside market hours: use extended_ttl
    """
    try:
        PT = pytz.timezone('America/Los_Angeles')
        now = datetime.now(PT)
        hour = now.hour
        minute = now.minute
        weekday = now.weekday()
        
        # Weekend
        if weekday >= 5:
            return extended_ttl
        
        # Market hours: 6:30 AM - 1:00 PM PT
        current_time = hour * 60 + minute
        market_open = 6 * 60 + 30
        market_close = 13 * 60
        
        if market_open <= current_time <= market_close:
            return base_ttl
        
        return extended_ttl
    except Exception:
        return base_ttl


def cache_key(*args, **kwargs) -> str:
    """Generate a cache key from function arguments."""
    key_data = json.dumps({"args": str(args), "kwargs": str(kwargs)}, sort_keys=True)
    return hashlib.md5(key_data.encode()).hexdigest()


def get_cached(key: str) -> Optional[Any]:
    """Get a value from cache if it exists and hasn't expired."""
    if key in _cache:
        entry = _cache[key]
        if time.time() < entry["expires_at"]:
            logger.debug(f"Cache HIT for key: {key[:8]}...")
            return entry["value"]
        else:
            # Expired, remove it
            del _cache[key]
            logger.debug(f"Cache EXPIRED for key: {key[:8]}...")
    return None


def set_cached(key: str, value: Any, ttl: int) -> None:
    """Store a value in cache with TTL in seconds."""
    _cache[key] = {
        "value": value,
        "expires_at": time.time() + ttl,
        "created_at": time.time()
    }
    logger.debug(f"Cache SET for key: {key[:8]}... (TTL: {ttl}s)")


def clear_cache(prefix: Optional[str] = None) -> int:
    """Clear cache entries, optionally only those matching a prefix."""
    global _cache
    if prefix is None:
        count = len(_cache)
        _cache = {}
        return count
    else:
        keys_to_delete = [k for k in _cache if k.startswith(prefix)]
        for key in keys_to_delete:
            del _cache[key]
        return len(keys_to_delete)


def cached_response(
    base_ttl: int = 60,
    extended_ttl: int = 300,
    key_prefix: str = "",
    force_refresh_threshold: int = 900  # 15 minutes in seconds
):
    """
    Decorator for caching API responses.
    
    Args:
        base_ttl: Cache TTL during market hours (seconds)
        extended_ttl: Cache TTL outside market hours (seconds)
        key_prefix: Optional prefix for cache keys
        force_refresh_threshold: When send_notification=True, bypass cache if older than this (seconds)
    
    Usage:
        @router.get("/expensive-endpoint")
        @cached_response(base_ttl=60, extended_ttl=300)
        async def my_endpoint(...):
            ...
    
    Note: When send_notification=True, cache is only bypassed if data is older than 
    force_refresh_threshold (default 15 minutes). This prevents API rate limiting while
    ensuring reasonably fresh data for notifications.
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            # Exclude 'db' and 'user' from cache key as they're request-specific
            cache_kwargs = {
                k: v for k, v in kwargs.items() 
                if k not in ('db', 'user')
            }
            key = f"{key_prefix}{func.__name__}:{cache_key(*args, **cache_kwargs)}"
            
            # Special handling when send_notification is True
            if kwargs.get('send_notification', False):
                # Check if we have cached data
                if key in _cache:
                    entry = _cache[key]
                    cache_age = time.time() - entry.get("created_at", 0)
                    
                    # If cache is fresh (< 15 minutes), use it to avoid API rate limiting
                    if cache_age < force_refresh_threshold:
                        logger.debug(
                            f"Using cached data for {func.__name__} "
                            f"(age: {int(cache_age)}s < {force_refresh_threshold}s threshold)"
                        )
                        # Return cached result but still send notifications
                        # (notifications will be sent for any new recommendations in the cached data)
                        return entry["value"]
                    else:
                        # Cache is stale (> 15 minutes), bypass it
                        logger.debug(
                            f"Cache BYPASSED for {func.__name__} "
                            f"(age: {int(cache_age)}s >= {force_refresh_threshold}s threshold)"
                        )
                else:
                    # No cache exists, proceed with fresh fetch
                    logger.debug(f"No cache found for {func.__name__}, fetching fresh data")
            
            # Check cache for normal requests (or if we're not bypassing)
            cached = get_cached(key)
            if cached is not None:
                return cached
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache the result
            ttl = _get_cache_ttl_for_market_hours(base_ttl, extended_ttl)
            set_cached(key, result, ttl)
            
            return result
        return wrapper
    return decorator


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics."""
    now = time.time()
    active_entries = sum(1 for v in _cache.values() if now < v["expires_at"])
    expired_entries = len(_cache) - active_entries
    
    return {
        "total_entries": len(_cache),
        "active_entries": active_entries,
        "expired_entries": expired_entries,
        "cache_keys": list(_cache.keys())[:10]  # First 10 keys for debugging
    }
