"""
Centralized timezone utilities for consistent timestamp handling.

IMPORTANT: The codebase has TWO conventions for naive datetimes:
1. V1 models: Store Pacific time as naive datetime
2. V2 models (recommendation_models.py): Store UTC as naive datetime via datetime.utcnow()

This module provides utilities to:
1. Convert timestamps to UTC for API responses
2. Ensure all timestamps sent to frontend have 'Z' suffix (UTC)

Frontend JavaScript parses timestamps with 'Z' suffix as UTC and 
automatically converts to user's local timezone for display.
"""

from datetime import datetime
import pytz

# Server timezone (Pacific)
PACIFIC = pytz.timezone('America/Los_Angeles')
UTC = pytz.UTC


def format_datetime_for_api(dt: datetime, assume_utc: bool = True) -> str | None:
    """
    Convert a datetime to UTC ISO string for API responses.
    
    Args:
        dt: A datetime object (naive or timezone-aware)
        assume_utc: If True, naive datetimes are assumed to be UTC (from datetime.utcnow())
                    If False, naive datetimes are assumed to be Pacific time
        
    Returns:
        ISO format string with 'Z' suffix (UTC) or None if dt is None
        
    Notes:
        - Timezone-aware datetimes are always converted to UTC correctly
        - For naive datetimes, behavior depends on assume_utc parameter
        - Default is assume_utc=True since most new code uses datetime.utcnow()
        - Returns format: "2026-01-06T20:43:50.245704Z"
    """
    if dt is None:
        return None
    
    # If already timezone-aware, convert to UTC
    if dt.tzinfo is not None:
        utc_dt = dt.astimezone(UTC)
        return utc_dt.isoformat().replace('+00:00', 'Z')
    
    # Naive datetime handling
    if assume_utc:
        # Naive datetime is already UTC (from datetime.utcnow())
        # Just add Z suffix, no conversion needed
        return dt.isoformat() + 'Z'
    else:
        # Naive datetime is in Pacific time (legacy behavior)
        # Localize to Pacific, then convert to UTC
        try:
            pacific_dt = PACIFIC.localize(dt)
            utc_dt = pacific_dt.astimezone(UTC)
            return utc_dt.isoformat().replace('+00:00', 'Z')
        except Exception:
            # Fallback: return without Z (will be interpreted as local time by JS)
            return dt.isoformat()


def format_pacific_datetime_for_api(dt: datetime) -> str | None:
    """
    Convert a Pacific naive datetime to UTC ISO string for API responses.
    Use this for legacy V1 models that store Pacific time.
    """
    return format_datetime_for_api(dt, assume_utc=False)


def now_utc() -> datetime:
    """Get current time in UTC (timezone-aware)."""
    return datetime.now(UTC)


def now_utc_iso() -> str:
    """Get current time as UTC ISO string with Z suffix."""
    return now_utc().isoformat().replace('+00:00', 'Z')


def now_pacific() -> datetime:
    """Get current time in Pacific (timezone-aware)."""
    return datetime.now(PACIFIC)

