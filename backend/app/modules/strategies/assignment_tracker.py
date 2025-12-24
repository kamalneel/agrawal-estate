"""
Assignment Tracker for Monday Buy-Back Follow-Up

V3.0: Track assignments from Friday for Monday morning buy-back reminders.

Flow:
1. Friday 12:45 PM: Smart assignment decision made
2. Friday EOD: User accepts assignment (or system records it)
3. Monday 6:00 AM: Generate buy-back recommendations
4. Monday: User buys back shares and sells new weekly

This enables the "accept assignment → buy back Monday" strategy
for IRA accounts where assignment is cheaper than rolling.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta
import logging
import json

from app.modules.strategies.algorithm_config import get_config

logger = logging.getLogger(__name__)


@dataclass
class AssignmentRecord:
    """Record of an assignment for follow-up."""
    symbol: str
    strike_price: float
    option_type: str
    contracts: int
    assignment_date: date
    assignment_price: float  # Same as strike for covered calls
    account_type: str
    account_name: Optional[str]
    buyback_completed: bool = False
    buyback_date: Optional[date] = None
    buyback_price: Optional[float] = None
    new_call_sold: bool = False
    new_call_strike: Optional[float] = None
    new_call_premium: Optional[float] = None


# In-memory tracking (for stateless environments, consider using database)
_assignment_tracking: List[AssignmentRecord] = []


def record_assignment(
    symbol: str,
    strike_price: float,
    option_type: str,
    contracts: int,
    account_type: str,
    account_name: Optional[str] = None
) -> AssignmentRecord:
    """
    Record an assignment for Monday follow-up.
    
    Args:
        symbol: Stock symbol
        strike_price: Strike price (assignment price for covered calls)
        option_type: 'call' or 'put'
        contracts: Number of contracts assigned
        account_type: Account type (IRA, ROTH_IRA, etc.)
        account_name: Account name for display
        
    Returns:
        AssignmentRecord
    """
    record = AssignmentRecord(
        symbol=symbol,
        strike_price=strike_price,
        option_type=option_type,
        contracts=contracts,
        assignment_date=date.today(),
        assignment_price=strike_price,  # For covered calls, assignment = strike
        account_type=account_type,
        account_name=account_name
    )
    
    _assignment_tracking.append(record)
    
    logger.info(
        f"Assignment recorded: {symbol} ${strike_price} {option_type} "
        f"x{contracts} in {account_type}"
    )
    
    return record


def record_assignment_from_position(position) -> AssignmentRecord:
    """
    Record assignment from a position object.
    
    Args:
        position: Position object with required attributes
        
    Returns:
        AssignmentRecord
    """
    return record_assignment(
        symbol=position.symbol,
        strike_price=position.strike_price,
        option_type=position.option_type,
        contracts=position.contracts,
        account_type=getattr(position, 'account_type', 'IRA'),
        account_name=getattr(position, 'account_name', None)
    )


def get_assignments_from_last_friday() -> List[AssignmentRecord]:
    """
    Get assignments from last Friday (for Monday follow-up).
    
    Returns:
        List of AssignmentRecord objects
    """
    today = date.today()
    
    # Calculate last Friday
    # Monday = 0, Friday = 4
    if today.weekday() == 0:  # Monday
        last_friday = today - timedelta(days=3)
    else:
        # Calculate days since Friday
        days_since_friday = (today.weekday() - 4) % 7
        if days_since_friday == 0:
            days_since_friday = 7
        last_friday = today - timedelta(days=days_since_friday)
    
    # Get assignments from that Friday that haven't been bought back
    friday_assignments = [
        a for a in _assignment_tracking
        if a.assignment_date == last_friday and not a.buyback_completed
    ]
    
    logger.debug(
        f"Found {len(friday_assignments)} assignments from {last_friday} "
        f"(total tracked: {len(_assignment_tracking)})"
    )
    
    return friday_assignments


def get_pending_assignments() -> List[AssignmentRecord]:
    """
    Get all pending assignments (not bought back).
    
    Returns:
        List of AssignmentRecord objects
    """
    return [a for a in _assignment_tracking if not a.buyback_completed]


def mark_buyback_completed(
    symbol: str,
    assignment_date: date,
    buyback_price: float
) -> Optional[AssignmentRecord]:
    """
    Mark assignment as bought back.
    
    Args:
        symbol: Stock symbol
        assignment_date: Date of original assignment
        buyback_price: Price at which shares were bought back
        
    Returns:
        Updated AssignmentRecord, or None if not found
    """
    for assignment in _assignment_tracking:
        if (assignment.symbol == symbol and 
            assignment.assignment_date == assignment_date and
            not assignment.buyback_completed):
            assignment.buyback_completed = True
            assignment.buyback_date = date.today()
            assignment.buyback_price = buyback_price
            
            logger.info(
                f"Buyback completed: {symbol} at ${buyback_price:.2f} "
                f"(assigned at ${assignment.assignment_price:.2f})"
            )
            
            return assignment
    
    logger.warning(f"Assignment not found: {symbol} from {assignment_date}")
    return None


def mark_new_call_sold(
    symbol: str,
    assignment_date: date,
    new_strike: float,
    new_premium: float
) -> Optional[AssignmentRecord]:
    """
    Mark that new covered call has been sold after buyback.
    
    Args:
        symbol: Stock symbol
        assignment_date: Date of original assignment
        new_strike: Strike of new covered call
        new_premium: Premium received for new call
        
    Returns:
        Updated AssignmentRecord, or None if not found
    """
    for assignment in _assignment_tracking:
        if (assignment.symbol == symbol and 
            assignment.assignment_date == assignment_date):
            assignment.new_call_sold = True
            assignment.new_call_strike = new_strike
            assignment.new_call_premium = new_premium
            
            logger.info(
                f"New call sold: {symbol} ${new_strike} @ ${new_premium:.2f}"
            )
            
            return assignment
    
    return None


def generate_monday_buyback_recommendations(
    ta_service=None,
    option_fetcher=None
) -> List[Dict[str, Any]]:
    """
    Monday morning: Generate buy-back recommendations for Friday assignments.
    
    Args:
        ta_service: TechnicalAnalysisService instance
        option_fetcher: OptionChainFetcher instance
        
    Returns:
        List of buyback recommendation dicts
    """
    # Get services if not provided
    if ta_service is None:
        from app.modules.strategies.technical_analysis import get_technical_analysis_service
        ta_service = get_technical_analysis_service()
    
    if option_fetcher is None:
        from app.modules.strategies.option_monitor import OptionChainFetcher
        option_fetcher = OptionChainFetcher()
    
    # Get config thresholds
    config = get_config('v3')
    smart_config = config.get('smart_assignment', {})
    skip_threshold = smart_config.get('monday_skip_threshold', 3.0)
    wait_threshold = smart_config.get('monday_wait_threshold', 1.0)
    
    assignments = get_assignments_from_last_friday()
    recommendations = []
    
    for assignment in assignments:
        try:
            rec = _generate_single_buyback_rec(
                assignment, ta_service, option_fetcher,
                skip_threshold, wait_threshold
            )
            if rec:
                recommendations.append(rec)
        except Exception as e:
            logger.error(f"Error generating buyback rec for {assignment.symbol}: {e}")
    
    logger.info(f"Generated {len(recommendations)} Monday buyback recommendations")
    return recommendations


def _generate_single_buyback_rec(
    assignment: AssignmentRecord,
    ta_service,
    option_fetcher,
    skip_threshold: float,
    wait_threshold: float
) -> Optional[Dict[str, Any]]:
    """
    Generate buyback recommendation for a single assignment.
    """
    symbol = assignment.symbol
    assignment_price = assignment.assignment_price
    contracts = assignment.contracts
    
    # Get current price
    indicators = ta_service.get_technical_indicators(symbol)
    if not indicators:
        logger.warning(f"Cannot get indicators for {symbol}")
        return None
    
    current_price = indicators.current_price
    price_change_pct = (current_price - assignment_price) / assignment_price * 100
    
    # Calculate buy-back cost
    buyback_cost_total = current_price * 100 * contracts
    assignment_value = assignment_price * 100 * contracts
    extra_cost = buyback_cost_total - assignment_value
    
    # Get recommended new strike (Delta 10 for weekly)
    strike_rec = ta_service.recommend_strike_price(
        symbol=symbol,
        option_type='call',
        expiration_weeks=1,
        probability_target=0.90  # Delta 10
    )
    
    new_strike = strike_rec.recommended_strike if strike_rec else current_price * 1.02
    
    # Get next Friday
    today = date.today()
    days_to_friday = (4 - today.weekday()) % 7
    if days_to_friday == 0:
        days_to_friday = 7
    next_friday = today + timedelta(days=days_to_friday)
    
    # Try to get new premium
    new_premium = _get_option_premium(option_fetcher, symbol, new_strike, 'call', next_friday)
    weekly_income = new_premium * 100 * contracts if new_premium else 0
    
    # Decide recommendation based on price change
    if price_change_pct > skip_threshold:  # >3% above assignment
        action = "SKIP_BUYBACK"
        reason = f"Stock up {price_change_pct:.1f}% - too expensive to buy back"
        priority = "low"
    elif price_change_pct > wait_threshold:  # 1-3% above
        action = "WAIT_OR_BUY"
        reason = f"Stock up {price_change_pct:.1f}% - consider waiting for dip"
        priority = "medium"
    elif price_change_pct < -2.0:  # Down >2%
        action = "BUY_NOW"
        reason = f"Stock down {abs(price_change_pct):.1f}% - great buy-back price!"
        priority = "high"
    else:  # -2% to +1%
        action = "BUY_NOW"
        reason = f"Good price - only {price_change_pct:+.1f}% from assignment"
        priority = "high"
    
    return {
        'type': 'BUYBACK_AFTER_ASSIGNMENT',
        'action': action,
        'symbol': symbol,
        'priority': priority,
        'reason': reason,
        # Assignment details
        'assignment_date': assignment.assignment_date.isoformat(),
        'assignment_price': assignment_price,
        'contracts': contracts,
        'account_type': assignment.account_type,
        'account_name': assignment.account_name,
        # Current market
        'current_price': current_price,
        'price_change_pct': round(price_change_pct, 2),
        'extra_cost': round(extra_cost, 2),
        # New covered call
        'new_strike': new_strike,
        'new_premium': round(new_premium, 2) if new_premium else None,
        'weekly_income': round(weekly_income, 2),
        'next_friday': next_friday.isoformat(),
        # Summary
        'summary': (
            f"Buy back {contracts}x {symbol} at ${current_price:.2f} "
            f"({price_change_pct:+.1f}% from ${assignment_price:.2f}), "
            f"then sell ${new_strike:.0f} call for ${new_premium:.2f}" if new_premium
            else f"Buy back {contracts}x {symbol} at ${current_price:.2f}"
        )
    }


def _get_option_premium(fetcher, symbol: str, strike: float, option_type: str, expiration: date) -> float:
    """Get option premium from chain."""
    try:
        chain = fetcher.get_option_chain(symbol, expiration)
        if not chain:
            return 0
        
        key = 'calls' if option_type.lower() == 'call' else 'puts'
        options_df = chain.get(key)
        
        if options_df is None or options_df.empty:
            return 0
        
        matching = options_df[
            (options_df['strike'] >= strike - 0.5) &
            (options_df['strike'] <= strike + 0.5)
        ]
        
        if matching.empty:
            return 0
        
        row = matching.iloc[0]
        bid = row.get('bid', 0) or 0
        ask = row.get('ask', 0) or 0
        
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        return bid or ask or 0
        
    except Exception:
        return 0


def clear_old_assignments(days_old: int = 30):
    """
    Clear assignments older than specified days.
    
    Args:
        days_old: Remove assignments older than this many days
    """
    global _assignment_tracking
    cutoff = date.today() - timedelta(days=days_old)
    
    before_count = len(_assignment_tracking)
    _assignment_tracking = [
        a for a in _assignment_tracking
        if a.assignment_date >= cutoff
    ]
    after_count = len(_assignment_tracking)
    
    if before_count > after_count:
        logger.info(f"Cleared {before_count - after_count} old assignments")


def get_assignment_stats() -> Dict[str, Any]:
    """Get statistics about tracked assignments."""
    total = len(_assignment_tracking)
    pending = len([a for a in _assignment_tracking if not a.buyback_completed])
    completed = total - pending
    
    return {
        'total_tracked': total,
        'pending_buyback': pending,
        'completed': completed,
    }


def export_assignments() -> List[Dict[str, Any]]:
    """Export all assignments as dicts (for persistence)."""
    result = []
    for a in _assignment_tracking:
        d = asdict(a)
        d['assignment_date'] = a.assignment_date.isoformat()
        if a.buyback_date:
            d['buyback_date'] = a.buyback_date.isoformat()
        result.append(d)
    return result


def import_assignments(data: List[Dict[str, Any]]):
    """Import assignments from dicts (for persistence)."""
    global _assignment_tracking
    _assignment_tracking = []
    
    for d in data:
        record = AssignmentRecord(
            symbol=d['symbol'],
            strike_price=d['strike_price'],
            option_type=d['option_type'],
            contracts=d['contracts'],
            assignment_date=date.fromisoformat(d['assignment_date']),
            assignment_price=d['assignment_price'],
            account_type=d['account_type'],
            account_name=d.get('account_name'),
            buyback_completed=d.get('buyback_completed', False),
            buyback_date=date.fromisoformat(d['buyback_date']) if d.get('buyback_date') else None,
            buyback_price=d.get('buyback_price'),
            new_call_sold=d.get('new_call_sold', False),
            new_call_strike=d.get('new_call_strike'),
            new_call_premium=d.get('new_call_premium')
        )
        _assignment_tracking.append(record)
    
    logger.info(f"Imported {len(_assignment_tracking)} assignments")

