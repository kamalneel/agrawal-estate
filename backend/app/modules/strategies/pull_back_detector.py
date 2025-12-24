"""
Pull-Back Detector for V3 Algorithm

V3.0: Check if far-dated positions can return to shorter expirations at cost-neutral.

When a position was rolled far out (e.g., 8 weeks) to escape ITM, and the stock
drops back down, we may be able to "pull back" to a shorter expiration and
return to weekly income generation sooner.

V3 Addendum:
- Check ALL intermediate expirations (not just weekly)
- Return SHORTEST duration achieving cost-neutral
- Use Delta 30 (probability_target=0.70) for pull-backs
- Check any position >1 week out (not just >2 weeks)
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime, date, timedelta
import logging

from app.modules.strategies.utils.option_calculations import is_acceptable_cost

logger = logging.getLogger(__name__)

# Same scan schedule as zero_cost_finder for consistency
SCAN_DURATIONS_WEEKS = [1, 2, 3, 4, 6, 8, 12, 16, 24, 36, 52]


@dataclass
class PullBackResult:
    """Result of pull-back opportunity check."""
    from_expiration: date
    from_weeks: int
    to_expiration: date
    to_weeks: int
    new_strike: float
    new_premium: float
    current_value: float
    net_cost: float
    net_cost_total: float
    weeks_saved: int
    acceptable: bool
    benefit: str


def check_pull_back_opportunity(
    symbol: str,
    current_expiration: date,
    current_strike: float,
    option_type: str,
    current_premium: float,  # Current value of the option
    original_premium: float,  # What we originally received
    contracts: int = 1,
    ta_service=None,
    option_fetcher=None
) -> Optional[PullBackResult]:
    """
    Check if far-dated position can return to shorter expiration at cost-neutral.
    
    Scans ALL intermediate expirations between 1 week and current expiration.
    Returns FIRST (shortest) expiration achieving cost-neutral.
    
    V3 Addendum: Uses Delta 30 for pull-backs (same as ITM escapes).
    
    Args:
        symbol: Stock ticker
        current_expiration: Current option expiration date
        current_strike: Current option strike price
        option_type: 'call' or 'put'
        current_premium: Current option value (buy-back cost)
        original_premium: Original premium received (for 20% rule)
        contracts: Number of contracts
        ta_service: TechnicalAnalysisService instance
        option_fetcher: OptionChainFetcher instance
        
    Returns:
        PullBackResult if opportunity found, None otherwise
    """
    # Get services if not provided
    if ta_service is None:
        from app.modules.strategies.technical_analysis import get_technical_analysis_service
        ta_service = get_technical_analysis_service()
    
    if option_fetcher is None:
        from app.modules.strategies.option_monitor import OptionChainFetcher
        option_fetcher = OptionChainFetcher()
    
    today = date.today()
    current_weeks = max(1, (current_expiration - today).days // 7)
    
    # Only check positions >1 week out (per V3 Addendum)
    if current_weeks <= 1:
        logger.debug(f"Pull-back check skipped: {symbol} only {current_weeks} weeks out")
        return None
    
    # Calculate max acceptable debit (20% of original premium)
    max_debit = original_premium * 0.20
    
    logger.info(
        f"Pull-back check: {symbol} ${current_strike} {option_type}, "
        f"current_weeks={current_weeks}, current_value=${current_premium:.2f}, "
        f"max_debit=${max_debit:.2f}"
    )
    
    # Check all intermediate expirations
    for weeks in SCAN_DURATIONS_WEEKS:
        # Don't check expirations at or beyond current
        if weeks >= current_weeks:
            break
        
        # Calculate target expiration (next Friday after weeks)
        target_date = today + timedelta(weeks=weeks)
        days_to_friday = (4 - target_date.weekday()) % 7
        exp_date = target_date + timedelta(days=days_to_friday)
        
        # Skip earnings week (per V3 Addendum - skip ONLY earnings week)
        if _should_skip_for_earnings(symbol, exp_date):
            logger.debug(f"Pull-back skipping {exp_date} - earnings week")
            continue
        
        # Skip ex-dividend week
        if _should_skip_for_dividend(symbol, exp_date):
            logger.debug(f"Pull-back skipping {exp_date} - ex-dividend week")
            continue
        
        # Get recommended strike using Delta 30 (per V3 Addendum)
        strike_rec = ta_service.recommend_strike_price(
            symbol=symbol,
            option_type=option_type,
            expiration_weeks=weeks,
            probability_target=0.70  # Delta 30 per V3 Addendum
        )
        
        if not strike_rec:
            logger.debug(f"Pull-back: No strike recommendation for {weeks}w")
            continue
        
        new_strike = strike_rec.recommended_strike
        
        # Get option premium for this strike and expiration
        premium_result = _get_option_premium(
            option_fetcher, symbol, new_strike, option_type, exp_date
        )
        
        if premium_result is None:
            logger.debug(f"Pull-back: No premium data for {weeks}w ${new_strike}")
            continue
        
        new_premium = premium_result['mid_price']
        
        # Calculate net cost to pull back
        # We buy back current option (current_premium) and sell new (new_premium)
        net_cost = current_premium - new_premium  # Positive = debit
        
        # Check if acceptable using 20% rule
        cost_check = is_acceptable_cost(net_cost, original_premium)
        
        if cost_check['acceptable']:
            # FOUND IT! Return immediately (shortest acceptable)
            weeks_saved = current_weeks - weeks
            
            logger.info(
                f"Pull-back found: {symbol} from {current_weeks}w to {weeks}w, "
                f"net_cost=${net_cost:.2f}, weeks_saved={weeks_saved}"
            )
            
            return PullBackResult(
                from_expiration=current_expiration,
                from_weeks=current_weeks,
                to_expiration=exp_date,
                to_weeks=weeks,
                new_strike=new_strike,
                new_premium=new_premium,
                current_value=current_premium,
                net_cost=net_cost,
                net_cost_total=net_cost * 100 * contracts,
                weeks_saved=weeks_saved,
                acceptable=True,
                benefit=f'Return to income {weeks_saved} weeks early'
            )
        else:
            logger.debug(
                f"Pull-back {weeks}w: net_cost=${net_cost:.2f} > max_debit=${max_debit:.2f}"
            )
    
    # No cost-neutral pull-back available
    logger.debug(f"No pull-back opportunity for {symbol}")
    return None


def _should_skip_for_earnings(symbol: str, exp_date: date) -> bool:
    """
    V3 Addendum: Skip ONLY the earnings week itself.
    Do NOT skip weeks before or after.
    """
    try:
        from app.modules.strategies.option_monitor import EarningsTracker
        tracker = EarningsTracker()
        earnings_date = tracker.get_next_earnings_date(symbol)
        
        if not earnings_date:
            return False
        
        # Get week boundaries (Monday to Sunday)
        earnings_week_start = earnings_date - timedelta(days=earnings_date.weekday())
        earnings_week_end = earnings_week_start + timedelta(days=6)
        
        # Skip if expiration falls IN the earnings week
        return earnings_week_start <= exp_date <= earnings_week_end
        
    except Exception as e:
        logger.warning(f"Error checking earnings for {symbol}: {e}")
        return False


def _should_skip_for_dividend(symbol: str, exp_date: date) -> bool:
    """
    Skip if expiration is in ex-dividend week.
    """
    try:
        from app.modules.strategies.option_monitor import DividendTracker
        tracker = DividendTracker()
        ex_div_date = tracker.get_next_ex_dividend_date(symbol)
        
        if not ex_div_date:
            return False
        
        # Get week boundaries
        div_week_start = ex_div_date - timedelta(days=ex_div_date.weekday())
        div_week_end = div_week_start + timedelta(days=6)
        
        # Skip if expiration falls in ex-div week
        return div_week_start <= exp_date <= div_week_end
        
    except Exception as e:
        logger.warning(f"Error checking dividend for {symbol}: {e}")
        return False


def _get_option_premium(
    fetcher,
    symbol: str,
    strike: float,
    option_type: str,
    expiration: date
) -> Optional[Dict[str, Any]]:
    """
    Get option premium (mid price) from option chain.
    """
    try:
        chain = fetcher.get_option_chain(symbol, expiration)
        if not chain:
            return None
        
        key = 'calls' if option_type.lower() == 'call' else 'puts'
        options_df = chain.get(key)
        
        if options_df is None or options_df.empty:
            return None
        
        # Find matching strike (with tolerance)
        matching = options_df[
            (options_df['strike'] >= strike - 0.5) &
            (options_df['strike'] <= strike + 0.5)
        ]
        
        if matching.empty:
            return None
        
        row = matching.iloc[0]
        bid = row.get('bid', 0) or 0
        ask = row.get('ask', 0) or 0
        delta = row.get('delta', 0.3) or 0.3
        
        if bid > 0 and ask > 0:
            mid_price = (bid + ask) / 2
        elif bid > 0:
            mid_price = bid
        elif ask > 0:
            mid_price = ask * 0.9
        else:
            mid_price = row.get('lastPrice', 0)
        
        if mid_price <= 0:
            return None
        
        return {
            'mid_price': mid_price,
            'bid': bid,
            'ask': ask,
            'delta': delta
        }
        
    except Exception as e:
        logger.warning(f"Error getting option premium: {e}")
        return None


def get_pull_back_detector():
    """Factory function for dependency injection."""
    return {
        'check_pull_back_opportunity': check_pull_back_opportunity,
    }

