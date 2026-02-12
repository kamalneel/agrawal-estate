"""
V5 Base - Shared types, helpers, and config for all V5 engines.

Contains:
- V5EvaluationResult dataclass (the contract between engines and orchestrator)
- LIFE_SUPPORT_THRESHOLDS (IV-based stuck thresholds)
- Shared helper functions
- Config access
"""

from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
import logging

from app.modules.strategies.algorithm_config import get_config

logger = logging.getLogger(__name__)


# V5 NEW: LIFE_SUPPORT thresholds by IV category
# life_support_starts: ITM% where weekly roll = $0 but bi-weekly/monthly still credit
# drowning_starts: ITM% where even monthly roll = $0, position is unsalvageable
LIFE_SUPPORT_THRESHOLDS = {
    "high_iv": {"life_support_starts": 30, "drowning_starts": 35},
    "medium_iv": {"life_support_starts": 17, "drowning_starts": 22},
    "low_iv": {"life_support_starts": 10, "drowning_starts": 15},
}


@dataclass
class V5EvaluationResult:
    """Result of V5 position evaluation with rich reasoning."""
    # Core decision
    # V5 ACTIONS: HOLD, CLOSE, ROLL, COMPRESS, WAIT_FOR_PULLBACK, WAIT_FOR_RECOVERY, LET_EXPIRE
    #            + ROLL_BIWEEKLY, ROLL_MONTHLY (V5 NEW for LIFE_SUPPORT)
    action: str
    position_id: str
    symbol: str

    # V5: Reasoning (inherited from V4)
    reason: str  # Full reasoning text for notification
    reason_short: str  # One-line summary
    philosophy_applied: str  # Which V5 belief drove this decision

    # V5 NEW: LIFE_SUPPORT category tracking
    stuck_category: Optional[str] = None  # HEALTHY, STUCK, LIFE_SUPPORT, DROWNING
    iv_category: Optional[str] = None  # high_iv, medium_iv, low_iv
    weekly_credit: Optional[float] = None  # Weekly roll credit (may be negative/debit)
    biweekly_credit: Optional[float] = None  # Bi-weekly roll credit
    monthly_credit: Optional[float] = None  # Monthly roll credit

    # Follow-up tracking (for two-part actions)
    has_follow_up: bool = False
    follow_up_condition: Optional[str] = None  # e.g., "stock_drops_3_pct"
    follow_up_threshold: Optional[float] = None  # e.g., 0.03
    follow_up_action: Optional[str] = None  # e.g., "RE_ENTER"

    # Position details
    details: Dict[str, Any] = field(default_factory=dict)

    # For roll/compress actions
    new_strike: Optional[float] = None
    new_expiration: Optional[date] = None
    net_cost: Optional[float] = None

    # V4/V5 metrics
    intrinsic_pct: Optional[float] = None  # % of option value that is intrinsic
    time_value: Optional[float] = None
    escape_weeks: Optional[int] = None  # Weeks needed to escape
    compression_value: Optional[float] = None  # Dual-benefit value
    compression_cost: Optional[float] = None

    # Cost basis info (for puts)
    cost_basis: Optional[float] = None
    assignment_acceptable: Optional[bool] = None


def get_v5_config() -> dict:
    """Get V5 configuration."""
    return get_config('v5')


def calculate_intrinsic_time_value(
    position,
    current_price: float,
    current_premium: float
) -> Tuple[float, float]:
    """Calculate intrinsic and time value of an option."""
    strike = float(position.strike_price) if position.strike_price else 0.0
    if position.option_type == 'call':
        intrinsic = max(0, current_price - strike)
    else:  # put
        intrinsic = max(0, strike - current_price)

    time_value = max(0, current_premium - intrinsic)

    return intrinsic, time_value


def estimate_current_premium(position, indicators) -> float:
    """Estimate current premium if not provided."""
    original_raw = getattr(position, 'original_premium', 1.0)
    original = float(original_raw) if original_raw else 1.0
    days_held = getattr(position, 'days_held', 0)
    total_days = getattr(position, 'total_days', 30)

    if total_days > 0:
        decay_factor = max(0.1, 1 - (days_held / total_days))
        return original * decay_factor
    return original * 0.5


def get_iv_category(symbol: str) -> str:
    """
    Determine IV category for a symbol.

    High IV stocks (>40%): HOOD, TSLA, MARA, etc.
    Medium IV stocks (20-40%): Most growth stocks
    Low IV stocks (<20%): Blue chips like AAPL, MSFT
    """
    high_iv_symbols = {'HOOD', 'TSLA', 'MARA', 'RIOT', 'COIN', 'GME', 'AMC', 'RIVN', 'LCID'}
    low_iv_symbols = {'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'BRK.B', 'JNJ', 'PG', 'KO'}

    if symbol.upper() in high_iv_symbols:
        return "high_iv"
    elif symbol.upper() in low_iv_symbols:
        return "low_iv"
    else:
        return "medium_iv"


def get_stuck_category(itm_pct: float, iv_category: str) -> str:
    """
    Determine stuck category based on ITM% and IV.

    Returns: HEALTHY, STUCK, LIFE_SUPPORT, or DROWNING
    """
    thresholds = LIFE_SUPPORT_THRESHOLDS.get(iv_category, LIFE_SUPPORT_THRESHOLDS["medium_iv"])
    life_support_starts = thresholds["life_support_starts"]
    drowning_starts = thresholds["drowning_starts"]

    if itm_pct < 5:
        return "HEALTHY"
    elif itm_pct < life_support_starts:
        return "STUCK"
    elif itm_pct < drowning_starts:
        return "LIFE_SUPPORT"
    else:
        return "DROWNING"


def calculate_escape_strike(
    current_strike: float,
    current_price: float,
    option_type: str,
    is_itm: bool
) -> float:
    """Calculate the escape strike - a strike that gets us to ATM or slightly OTM."""
    if not is_itm:
        return current_strike

    if current_price >= 100:
        increment = 5.0
    elif current_price >= 50:
        increment = 2.5
    else:
        increment = 1.0

    if option_type == 'call':
        new_strike = (current_price // increment + 1) * increment
        return max(new_strike, current_strike)
    else:
        new_strike = (current_price // increment) * increment
        return min(new_strike, current_strike)


def get_next_friday() -> date:
    """Get the date of next Friday."""
    today = date.today()
    days_ahead = 4 - today.weekday()  # Friday = 4
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def estimate_roll_credits(
    position,
    current_price: float,
    current_premium: float,
    option_fetcher
) -> Tuple[float, float, float]:
    """
    Estimate credits for weekly, bi-weekly, and monthly rolls using LIVE option chain data.

    Returns: (weekly_credit, biweekly_credit, monthly_credit) per share
    Positive = credit, Negative = debit
    """
    strike = float(position.strike_price) if position.strike_price else 0.0
    option_type = getattr(position, 'option_type', 'call')
    current_expiration = getattr(position, 'expiration_date', None)

    # Calculate target expiration dates
    today = date.today()
    days_to_friday = (4 - today.weekday()) % 7
    if days_to_friday == 0:
        days_to_friday = 7
    next_friday = today + timedelta(days=days_to_friday)
    biweekly_exp = next_friday + timedelta(days=7)
    monthly_exp = next_friday + timedelta(days=21)

    # Try to get REAL option chain data
    close_cost = None
    weekly_bid = None
    biweekly_bid = None
    monthly_bid = None

    try:
        # Get close cost (ask price to buy back current position)
        if current_expiration:
            exp_date = current_expiration
            if isinstance(exp_date, str):
                exp_date = datetime.strptime(exp_date, '%Y-%m-%d').date()
            elif isinstance(exp_date, datetime):
                exp_date = exp_date.date()

            current_quote = option_fetcher.get_option_quote(
                symbol=position.symbol,
                strike_price=strike,
                option_type=option_type,
                expiration_date=exp_date
            )
            if current_quote:
                close_cost = current_quote.ask if current_quote.ask else current_quote.last_price
                logger.debug(f"[V5 ROLL] {position.symbol}: Close cost from chain = ${close_cost:.2f}")

        # Get weekly new premium (bid price to sell)
        weekly_quote = option_fetcher.get_option_quote(
            symbol=position.symbol,
            strike_price=strike,
            option_type=option_type,
            expiration_date=next_friday
        )
        if weekly_quote:
            weekly_bid = weekly_quote.bid if weekly_quote.bid else weekly_quote.last_price
            logger.debug(f"[V5 ROLL] {position.symbol}: Weekly bid = ${weekly_bid:.2f}")

        # Get biweekly new premium
        biweekly_quote = option_fetcher.get_option_quote(
            symbol=position.symbol,
            strike_price=strike,
            option_type=option_type,
            expiration_date=biweekly_exp
        )
        if biweekly_quote:
            biweekly_bid = biweekly_quote.bid if biweekly_quote.bid else biweekly_quote.last_price
            logger.debug(f"[V5 ROLL] {position.symbol}: Biweekly bid = ${biweekly_bid:.2f}")

        # Get monthly new premium
        monthly_quote = option_fetcher.get_option_quote(
            symbol=position.symbol,
            strike_price=strike,
            option_type=option_type,
            expiration_date=monthly_exp
        )
        if monthly_quote:
            monthly_bid = monthly_quote.bid if monthly_quote.bid else monthly_quote.last_price
            logger.debug(f"[V5 ROLL] {position.symbol}: Monthly bid = ${monthly_bid:.2f}")

    except Exception as e:
        logger.warning(f"[V5 ROLL] {position.symbol}: Error fetching option chain: {e}")

    # Calculate credits using real data, or fallback to estimates
    if close_cost is None:
        intrinsic, time_value = calculate_intrinsic_time_value(position, current_price, current_premium)
        close_cost = intrinsic + max(time_value, current_premium * 0.1)
        logger.debug(f"[V5 ROLL] {position.symbol}: Estimated close cost = ${close_cost:.2f}")

    # Calculate net credits (new_bid - close_cost)
    if weekly_bid is not None:
        weekly_credit = weekly_bid - close_cost
    else:
        weekly_credit = -close_cost * 0.3

    if biweekly_bid is not None:
        biweekly_credit = biweekly_bid - close_cost
    else:
        biweekly_credit = close_cost * 0.1 - close_cost

    if monthly_bid is not None:
        monthly_credit = monthly_bid - close_cost
    else:
        monthly_credit = close_cost * 0.3

    logger.info(f"[V5 ROLL] {position.symbol} ${strike:.0f} {option_type}: "
               f"close=${close_cost:.2f}, weekly=${weekly_credit:.2f}, "
               f"biweekly=${biweekly_credit:.2f}, monthly=${monthly_credit:.2f}")

    return weekly_credit, biweekly_credit, monthly_credit
