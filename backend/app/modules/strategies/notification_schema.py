"""
Notification Dict Schema

Defines the structure for notification dicts to catch field mismatches at type-check time.
All notification builders should return NotificationDict or compatible subclass.

CRITICAL FIELDS (required for save function):
- symbol: str
- account_name: str (top-level, not just in context!)
- source_strike: float (for recommendation ID generation)
- source_expiration: date (for recommendation ID generation)
- option_type: str

See docs/ALGORITHM-UPGRADE-BEST-PRACTICES.md Pitfall 16 for why these are critical.
"""

from typing import TypedDict, Optional, Any, Dict, List
from datetime import date


class NotificationContext(TypedDict, total=False):
    """Context dict for additional notification details."""
    account_name: str  # Duplicated here for backwards compatibility
    days_to_exp: int
    is_itm: bool
    itm_pct: float
    current_price: float
    profit_pct: float
    rsi: float
    scan_type: str
    v5_philosophy: str
    stuck_category: str
    iv_category: str
    original_v5_action: str
    current_market_bid: float
    pending_order_raw: str


class NotificationDict(TypedDict, total=False):
    """
    Standard notification dict structure.

    Required fields (for save function to work correctly):
    - id: str
    - symbol: str
    - account_name: str  # MUST be at top level!
    - action: str
    - source_strike: float  # MUST be present for recommendation ID
    - source_expiration: date  # MUST be present for recommendation ID
    - option_type: str
    """
    # Core identification (REQUIRED)
    id: str
    symbol: str
    account_name: str  # CRITICAL: Must be at top level, not just in context

    # Action (REQUIRED)
    action: str
    action_display: str

    # Display
    title: str
    reason: str
    reason_short: str
    rationale: str
    philosophy: str

    # Source position details (REQUIRED for recommendation ID)
    source_strike: float  # CRITICAL: Must be present
    source_expiration: date  # CRITICAL: Must be present
    option_type: str  # CRITICAL: Must be present
    contracts: int

    # Target details (for ROLL/COMPRESS actions)
    target_strike: float
    target_expiration: date
    net_cost: float

    # V5 LIFE_SUPPORT tracking
    stuck_category: str
    iv_category: str
    weekly_credit: float
    biweekly_credit: float
    monthly_credit: float

    # Follow-up tracking
    has_follow_up: bool
    follow_up_condition: str
    follow_up_threshold: float
    follow_up_action: str

    # V5 metrics
    intrinsic_pct: float
    time_value: float
    escape_weeks: int
    compression_value: float
    compression_cost: float

    # Cost basis
    cost_basis: float
    assignment_acceptable: bool

    # Uncovered position flag
    is_uncovered: bool
    stock_price: float
    total_premium: float

    # Pending order fields
    is_pending_order: bool
    pending_order_id: int
    pending_order_type: str
    pending_limit_price: float
    suggested_limit: float
    suggested_expiration: date
    suggested_strike: float
    urgency_level: str
    replaces_position_id: str

    # Context (for additional details)
    context: NotificationContext
    snapshot_id: int


class PutNotificationDict(NotificationDict):
    """
    Put recommendation notification dict.

    Extends NotificationDict with put-specific fields.
    """
    is_put_recommendation: bool
    target_premium: float
    annual_yield_pct: float
    account_cash: float


def validate_notification_dict(notif: Dict[str, Any]) -> List[str]:
    """
    Validate a notification dict has required fields.

    Returns list of missing/invalid fields for debugging.
    Use during development to catch schema issues early.
    """
    errors = []

    # Required fields
    required = ['symbol', 'account_name', 'action']
    for field in required:
        if field not in notif or notif[field] is None:
            errors.append(f"Missing required field: {field}")

    # Fields required for recommendation ID generation
    if 'source_strike' not in notif or notif.get('source_strike') is None:
        errors.append("Missing source_strike (required for recommendation ID)")

    if 'source_expiration' not in notif or notif.get('source_expiration') is None:
        errors.append("Missing source_expiration (required for recommendation ID)")

    if 'option_type' not in notif or notif.get('option_type') is None:
        errors.append("Missing option_type (required for recommendation ID)")

    # Warn if account_name is only in context (common mistake)
    if 'account_name' not in notif and notif.get('context', {}).get('account_name'):
        errors.append("account_name is only in context, but MUST be at top level")

    return errors


def create_base_notification(
    symbol: str,
    account_name: str,
    action: str,
    source_strike: float,
    source_expiration: date,
    option_type: str,
    **kwargs
) -> NotificationDict:
    """
    Factory function to create a notification dict with required fields.

    Use this to ensure all required fields are present.
    """
    notif: NotificationDict = {
        'id': kwargs.get('id', f"{symbol}_{account_name}_{action}"),
        'symbol': symbol,
        'account_name': account_name,
        'action': action,
        'source_strike': source_strike,
        'source_expiration': source_expiration,
        'option_type': option_type,
        'contracts': kwargs.get('contracts', 1),
        'context': {
            'account_name': account_name,  # Duplicate for backwards compatibility
        },
    }

    # Add optional fields if provided
    for key, value in kwargs.items():
        if key not in notif and value is not None:
            notif[key] = value

    return notif
