"""
Zero-Cost Roll Finder

V3.0: Find SHORTEST duration achieving zero-cost roll.

This module replaces V2's scoring-based multi-week optimizer with a simpler
sequential search that returns the FIRST acceptable roll option.

V3 Logic:
1. Scan expirations from 1 week to 52 weeks
2. For each expiration, check if net_cost <= max_debit (20% of original premium)
3. Return FIRST (shortest) duration that achieves zero-cost
4. Skip earnings weeks (not weeks before/after)

Per V3 Addendum:
- ITM rolls use Delta 30 (probability_target=0.70)
- Weekly rolls use Delta 10 (probability_target=0.90)
- Pull-backs use Delta 30 (probability_target=0.70)
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime, date, timedelta
import logging

from app.modules.strategies.utils.option_calculations import is_acceptable_cost

logger = logging.getLogger(__name__)

# V3: Scan schedule for efficient searching up to 52 weeks
# Check every week for 1-4, then skip weeks for longer durations
SCAN_DURATIONS_WEEKS = [1, 2, 3, 4, 6, 8, 12, 16, 24, 36, 52]


@dataclass
class ZeroCostRollResult:
    """Result of zero-cost roll search."""
    expiration_date: date
    weeks_out: int
    strike: float
    new_premium: float
    buy_back_cost: float
    net_cost: float
    net_cost_total: float  # net_cost * 100 * contracts
    probability_otm: float  # 0-100%
    delta: float
    is_credit: bool
    acceptable: bool
    
    # Additional context
    strike_distance_pct: float
    days_to_expiry: int
    current_price: float
    original_premium: float
    max_debit_allowed: float


def find_zero_cost_roll(
    symbol: str,
    current_strike: float,
    option_type: str,
    current_expiration: date,
    current_price: float,
    buy_back_cost: float,
    original_premium: float,
    contracts: int = 1,
    max_months: int = 12,
    delta_target: float = 0.70,
    ta_service=None,
    option_fetcher=None,
    skip_earnings: bool = True,
    skip_dividends: bool = True
) -> Optional[ZeroCostRollResult]:
    """
    V3: Find SHORTEST duration achieving zero-cost roll.
    
    Scans expirations sequentially from 1 week to max_months.
    Returns the FIRST acceptable roll (not the "best" scored).
    
    Args:
        symbol: Stock ticker
        current_strike: Current option strike price
        option_type: 'call' or 'put'
        current_expiration: Current option expiration date
        current_price: Current stock price
        buy_back_cost: Cost to close current position (per share)
        original_premium: Original premium received (for 20% rule)
        contracts: Number of contracts
        max_months: Maximum months to search (default 12 = 52 weeks)
        delta_target: Target probability OTM
            - 0.70 (Delta 30) for ITM escapes and pull-backs
            - 0.90 (Delta 10) for weekly rolls
        ta_service: TechnicalAnalysisService instance
        option_fetcher: OptionChainFetcher instance
        skip_earnings: Skip expirations in earnings week
        skip_dividends: Skip expirations near ex-dividend
        
    Returns:
        ZeroCostRollResult if found, None if no acceptable roll within max_months
    """
    # Get services if not provided
    if ta_service is None:
        from app.modules.strategies.technical_analysis import get_technical_analysis_service
        ta_service = get_technical_analysis_service()
    
    if option_fetcher is None:
        from app.modules.strategies.option_monitor import OptionChainFetcher
        option_fetcher = OptionChainFetcher()
    
    # Calculate max acceptable debit (20% of original premium)
    max_debit = original_premium * 0.20
    max_weeks = max_months * 4  # Convert months to weeks
    
    today = date.today()
    
    # Filter scan durations to max_weeks
    scan_weeks = [w for w in SCAN_DURATIONS_WEEKS if w <= max_weeks]
    
    logger.info(
        f"Zero-cost finder: {symbol} ${current_strike} {option_type}, "
        f"buy_back=${buy_back_cost:.2f}, max_debit=${max_debit:.2f}, "
        f"delta_target={delta_target}, max_weeks={max_weeks}"
    )
    
    for weeks in scan_weeks:
        # Calculate target expiration (next Friday after weeks)
        target_date = today + timedelta(weeks=weeks)
        days_to_friday = (4 - target_date.weekday()) % 7
        expiration = target_date + timedelta(days=days_to_friday)
        
        # Skip if before or same as current expiration
        if expiration <= current_expiration:
            logger.debug(f"Skipping {expiration} - before/same as current {current_expiration}")
            continue
        
        # Skip earnings week if enabled
        if skip_earnings and should_skip_expiration_for_earnings(symbol, expiration):
            logger.debug(f"Skipping {expiration} - earnings week")
            continue
        
        # Skip dividend week if enabled
        if skip_dividends and should_skip_expiration_for_dividend(symbol, expiration):
            logger.debug(f"Skipping {expiration} - ex-dividend week")
            continue
        
        # Get recommended strike using delta_target
        strike_rec = ta_service.recommend_strike_price(
            symbol=symbol,
            option_type=option_type,
            expiration_weeks=weeks,
            probability_target=delta_target
        )
        
        if not strike_rec:
            logger.debug(f"No strike recommendation for {weeks}w")
            continue
        
        new_strike = strike_rec.recommended_strike
        
        # Get option premium for this strike and expiration
        premium_result = _get_option_premium(
            option_fetcher, symbol, new_strike, option_type, expiration
        )
        
        if premium_result is None:
            logger.debug(f"No premium data for {weeks}w ${new_strike}")
            continue
        
        new_premium = premium_result['mid_price']
        delta = premium_result.get('delta', 1 - delta_target)
        probability_otm = (1 - abs(delta)) * 100
        
        # Calculate net cost
        net_cost = buy_back_cost - new_premium  # Positive = debit, Negative = credit
        
        # Check if acceptable using V3 20% rule
        cost_check = is_acceptable_cost(net_cost, original_premium)
        
        if cost_check['acceptable']:
            # FOUND IT! Return immediately (shortest acceptable)
            logger.info(
                f"Zero-cost found: {weeks}w {expiration} ${new_strike} "
                f"net_cost=${net_cost:.2f} (max=${max_debit:.2f})"
            )
            
            # Calculate strike distance
            if option_type.lower() == 'call':
                strike_distance_pct = ((new_strike - current_price) / current_price) * 100
            else:
                strike_distance_pct = ((current_price - new_strike) / current_price) * 100
            
            return ZeroCostRollResult(
                expiration_date=expiration,
                weeks_out=weeks,
                strike=new_strike,
                new_premium=new_premium,
                buy_back_cost=buy_back_cost,
                net_cost=net_cost,
                net_cost_total=net_cost * 100 * contracts,
                probability_otm=probability_otm,
                delta=delta,
                is_credit=net_cost < 0,
                acceptable=True,
                strike_distance_pct=strike_distance_pct,
                days_to_expiry=(expiration - today).days,
                current_price=current_price,
                original_premium=original_premium,
                max_debit_allowed=max_debit
            )
        else:
            logger.debug(
                f"Week {weeks}: net_cost=${net_cost:.2f} > max_debit=${max_debit:.2f}, continuing..."
            )
    
    # Could not find acceptable roll within max_months
    logger.warning(
        f"No zero-cost roll found for {symbol} ${current_strike} {option_type} "
        f"within {max_months} months"
    )
    return None


def should_skip_expiration_for_earnings(symbol: str, exp_date: date) -> bool:
    """
    V3 Addendum: Skip ONLY the earnings week itself.
    Do NOT skip weeks before or after.
    
    Args:
        symbol: Stock ticker
        exp_date: Expiration date to check
        
    Returns:
        True if exp_date falls in the earnings week
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


def should_skip_expiration_for_dividend(symbol: str, exp_date: date) -> bool:
    """
    Skip expirations near ex-dividend date to avoid early assignment risk.
    
    Args:
        symbol: Stock ticker
        exp_date: Expiration date to check
        
    Returns:
        True if exp_date is within 2 days of ex-dividend date
    """
    try:
        from app.modules.strategies.option_monitor import DividendTracker
        tracker = DividendTracker()
        ex_div_date = tracker.get_next_ex_dividend_date(symbol)
        
        if not ex_div_date:
            return False
        
        # Skip if expiration is within 2 days of ex-dividend
        days_diff = abs((exp_date - ex_div_date).days)
        return days_diff <= 2
        
    except Exception as e:
        logger.warning(f"Error checking dividend for {symbol}: {e}")
        return False


def detect_excessive_earnings(symbol: str) -> Optional[Dict[str, Any]]:
    """
    V3 Addendum Edge Case: Detect stocks with excessive earnings frequency.
    
    If stock has earnings scheduled 10+ times in next quarter, this is
    too volatile for our covered call strategy.
    
    Args:
        symbol: Stock ticker
        
    Returns:
        Alert dict if excessive earnings detected, None otherwise
    """
    try:
        from app.modules.strategies.option_monitor import EarningsTracker
        tracker = EarningsTracker()
        
        # Check earnings for next 13 weeks (1 quarter)
        earnings_dates = tracker.get_earnings_schedule(symbol, weeks_ahead=13)
        
        if len(earnings_dates) >= 10:
            return {
                'action': 'SELL_HOLDING',
                'reason': 'EXCESSIVE_VOLATILITY',
                'message': (
                    f'{symbol} has earnings scheduled {len(earnings_dates)} times '
                    f'in the next quarter. This is too volatile for our strategy. '
                    f'Recommend closing entire position.'
                ),
                'priority': 'urgent',
                'earnings_count': len(earnings_dates)
            }
        
        return None
        
    except Exception as e:
        logger.warning(f"Error checking earnings frequency for {symbol}: {e}")
        return None


def _get_option_premium(
    fetcher,
    symbol: str,
    strike: float,
    option_type: str,
    expiration: date
) -> Optional[Dict[str, Any]]:
    """
    Get option premium (mid price) from option chain.
    
    Returns:
        Dict with 'mid_price', 'bid', 'ask', 'delta' or None
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
            mid_price = ask * 0.9  # Discount ask if no bid
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


def get_zero_cost_finder():
    """Factory function for dependency injection."""
    return {
        'find_zero_cost_roll': find_zero_cost_roll,
        'should_skip_expiration_for_earnings': should_skip_expiration_for_earnings,
        'should_skip_expiration_for_dividend': should_skip_expiration_for_dividend,
        'detect_excessive_earnings': detect_excessive_earnings,
    }

