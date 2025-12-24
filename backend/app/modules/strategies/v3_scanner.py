"""
V3 Scanner - Unified Position Scanning with V3 Algorithm

This module provides the V3 scan functions that use the unified PositionEvaluator
and SmartScanFilter to generate recommendations.

Scan Schedule (Pacific Time):
1. 6:00 AM - Main comprehensive daily scan
2. 8:00 AM - Post-opening urgent scan (state changes only)
3. 12:00 PM - Midday scan (pull-backs and opportunities)
4. 12:45 PM - Pre-close urgent scan (expiring today only)
5. 8:00 PM - Evening planning scan (next day prep)

Key Features:
- Single evaluation per position using PositionEvaluator
- SmartScanFilter prevents duplicate notifications
- State-based 8 AM urgency detection
- Priority-based routing
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, date, timedelta
import logging

from app.modules.strategies.position_evaluator import (
    PositionEvaluator,
    SmartScanFilter,
    EvaluationResult,
    get_position_evaluator,
    get_scan_filter
)
from app.modules.strategies.pull_back_detector import check_pull_back_opportunity
from app.modules.strategies.smart_assignment_evaluator import evaluate_smart_assignment_ira
from app.modules.strategies.assignment_tracker import (
    record_assignment_from_position,
    generate_monday_buyback_recommendations
)
from app.modules.strategies.recommendations import StrategyRecommendation

logger = logging.getLogger(__name__)

# Global instances (reset daily)
_scan_filter: Optional[SmartScanFilter] = None
_morning_state: Dict[str, Dict[str, Any]] = {}


def get_global_scan_filter() -> SmartScanFilter:
    """Get global scan filter instance, creating if needed."""
    global _scan_filter
    if _scan_filter is None:
        _scan_filter = get_scan_filter()
    return _scan_filter


def reset_daily():
    """Reset filter and state at midnight."""
    global _scan_filter, _morning_state
    if _scan_filter:
        _scan_filter.reset_daily()
    _morning_state = {}
    logger.info("V3 Scanner: Daily reset complete")


@dataclass
class PositionState:
    """Snapshot of position state at a point in time."""
    was_itm: bool
    itm_pct: float
    could_pull_back: bool
    current_price: float
    profit_pct: float


def scan_6am(positions: List[Any], db=None) -> List[Dict[str, Any]]:
    """
    6:00 AM - Main comprehensive daily scan.
    
    Evaluates ALL positions using the unified PositionEvaluator.
    Saves morning state for later comparison.
    
    V3.5: On Mondays, includes buy-back reminders for Friday assignments.
    
    Args:
        positions: List of position objects
        db: Database session (optional)
        
    Returns:
        List of recommendations
    """
    global _morning_state
    
    logger.info(f"V3 6AM Scan: Evaluating {len(positions)} positions")
    
    evaluator = get_position_evaluator()
    scan_filter = get_global_scan_filter()
    
    recommendations = []
    _morning_state = {}  # Reset morning state
    
    for position in positions:
        try:
            # Evaluate position
            result = evaluator.evaluate(position)
            
            # Save morning state for 8 AM comparison
            _morning_state[_get_position_id(position)] = _capture_state(position, evaluator)
            
            # Filter and add recommendation
            if result:
                if scan_filter.should_send(result.position_id, result):
                    recommendations.append(_result_to_dict(result))
                    logger.debug(f"6AM: {result.symbol} -> {result.action}")
                else:
                    logger.debug(f"6AM: {result.symbol} filtered (duplicate)")
                    
        except Exception as e:
            logger.error(f"6AM: Error evaluating {position.symbol}: {e}")
    
    # V3.5: Monday buy-back reminders for IRA assignments
    today = date.today()
    if today.weekday() == 0:  # Monday
        logger.info("V3 6AM Scan: Monday - checking for buyback recommendations")
        buyback_recs = generate_monday_buyback_recommendations()
        for rec in buyback_recs:
            rec_id = f"buyback_{rec['symbol']}_{rec['assignment_date']}"
            if scan_filter.should_send(rec_id, rec):
                recommendations.append(rec)
                logger.info(f"6AM MONDAY: {rec['symbol']} -> {rec['action']}")
    
    logger.info(f"V3 6AM Scan: Generated {len(recommendations)} recommendations")
    return recommendations


def scan_8am(positions: List[Any]) -> List[Dict[str, Any]]:
    """
    8:00 AM - Post-opening urgent scan.
    
    Only alerts on NEW urgent items since 6 AM:
    - Newly ITM (OTM → ITM)
    - New pull-back opportunity
    - Earnings TODAY
    - Deep ITM getting significantly worse (>10% deeper)
    - Expiring TODAY
    
    Args:
        positions: List of position objects
        
    Returns:
        List of urgent recommendations
    """
    logger.info(f"V3 8AM Scan: Checking {len(positions)} positions for urgent changes")
    
    evaluator = get_position_evaluator()
    scan_filter = get_global_scan_filter()
    
    urgent_items = []
    
    for position in positions:
        try:
            position_id = _get_position_id(position)
            morning_state = _morning_state.get(position_id)
            
            # Check for urgent state changes
            urgent = _check_8am_urgent(position, morning_state, evaluator)
            
            for item in urgent:
                if scan_filter.should_send(position_id, item):
                    urgent_items.append(item)
                    logger.info(f"8AM URGENT: {position.symbol} -> {item.get('type', item.get('action'))}")
                    
        except Exception as e:
            logger.error(f"8AM: Error checking {position.symbol}: {e}")
    
    logger.info(f"V3 8AM Scan: Found {len(urgent_items)} urgent items")
    return urgent_items


def scan_12pm(positions: List[Any]) -> List[Dict[str, Any]]:
    """
    12:00 PM - Midday scan.
    
    Checks for:
    - New pull-back opportunities (stock dropped since morning)
    - Significant intraday moves (>10% since morning)
    
    Args:
        positions: List of position objects
        
    Returns:
        List of recommendations
    """
    logger.info(f"V3 12PM Scan: Checking {len(positions)} positions for midday opportunities")
    
    evaluator = get_position_evaluator()
    scan_filter = get_global_scan_filter()
    
    opportunities = []
    
    for position in positions:
        try:
            position_id = _get_position_id(position)
            morning_state = _morning_state.get(position_id)
            
            # Check for new pull-back opportunities
            current_weeks = (position.expiration_date - date.today()).days // 7
            if current_weeks > 1:
                pull_back = check_pull_back_opportunity(
                    symbol=position.symbol,
                    current_expiration=position.expiration_date,
                    current_strike=position.strike_price,
                    option_type=position.option_type,
                    current_premium=getattr(position, 'current_premium', 1.0),
                    original_premium=getattr(position, 'original_premium', 1.0),
                    contracts=position.contracts
                )
                
                if pull_back:
                    was_available = morning_state.could_pull_back if morning_state else False
                    if not was_available:
                        rec = {
                            'action': 'PULL_BACK',
                            'type': 'PULLBACK_NEW',
                            'symbol': position.symbol,
                            'priority': 'high',
                            'message': f'Can now pull back to {pull_back.to_weeks} weeks',
                            'pull_back_data': {
                                'from_weeks': pull_back.from_weeks,
                                'to_weeks': pull_back.to_weeks,
                                'net_cost': pull_back.net_cost,
                            }
                        }
                        if scan_filter.should_send(position_id, rec):
                            opportunities.append(rec)
                            
        except Exception as e:
            logger.error(f"12PM: Error checking {position.symbol}: {e}")
    
    logger.info(f"V3 12PM Scan: Found {len(opportunities)} opportunities")
    return opportunities


def scan_1245pm(positions: List[Any]) -> List[Dict[str, Any]]:
    """
    12:45 PM - Pre-close urgent scan.
    
    Last chance actions before market close (1:00 PM Pacific):
    - Positions expiring TODAY
    - Smart Assignment evaluation (IRA only, borderline ITM)
    - Triple Witching alerts (if applicable)
    
    V3.5: Adds smart assignment for IRA accounts with borderline ITM positions.
    
    Args:
        positions: List of position objects
        
    Returns:
        List of urgent recommendations
    """
    logger.info(f"V3 12:45PM Scan: Checking for expiring positions")
    
    evaluator = get_position_evaluator()
    scan_filter = get_global_scan_filter()
    urgent_items = []
    today = date.today()
    
    for position in positions:
        try:
            # Check if expiring TODAY
            if position.expiration_date == today:
                position_id = _get_position_id(position)
                
                # V3.5: Check smart assignment first (IRA only, 0.1-2% ITM)
                smart_assignment = evaluate_smart_assignment_ira(position)
                
                if smart_assignment:
                    # Smart assignment recommendation found
                    rec = _smart_assignment_to_dict(smart_assignment)
                    if scan_filter.should_send(position_id, rec):
                        urgent_items.append(rec)
                        logger.info(
                            f"12:45PM SMART ASSIGNMENT: {position.symbol} - "
                            f"{smart_assignment.reason}"
                        )
                        
                        # Record for Monday follow-up
                        record_assignment_from_position(position)
                    continue  # Skip normal expiry handling
                
                # Normal expiring position handling
                rec = {
                    'action': 'EXPIRES_TODAY',
                    'type': 'EXPIRES_TODAY',
                    'symbol': position.symbol,
                    'priority': 'urgent',
                    'message': 'Position expires today - LAST 15 MINUTES',
                    'details': {
                        'strike': position.strike_price,
                        'option_type': position.option_type,
                    }
                }
                
                if scan_filter.should_send(position_id, rec):
                    urgent_items.append(rec)
                    logger.warning(f"12:45PM: {position.symbol} EXPIRES TODAY")
                    
        except Exception as e:
            logger.error(f"12:45PM: Error checking {position.symbol}: {e}")
    
    logger.info(f"V3 12:45PM Scan: Found {len(urgent_items)} urgent items")
    return urgent_items


def _smart_assignment_to_dict(result) -> Dict[str, Any]:
    """Convert SmartAssignmentResult to dict for notifications."""
    return {
        'action': result.action,
        'type': 'SMART_ASSIGNMENT_IRA',
        'symbol': result.symbol,
        'priority': result.priority,
        'reason': result.reason,
        'position_id': result.position_id,
        # Assignment details
        'assignment_price': result.assignment_price,
        'current_price': result.current_price,
        'itm_pct': result.itm_pct,
        'assignment_loss_total': result.assignment_loss_total,
        # Roll comparison
        'roll_option': result.roll_option,
        'roll_weeks': result.roll_weeks,
        'total_roll_cost': result.total_roll_cost,
        'savings_by_assignment': result.savings_by_assignment,
        # Plan
        'plan': 'Let expire → Shares assigned → Buy back Monday → Sell new weekly',
    }


def scan_8pm(positions: List[Any]) -> List[Dict[str, Any]]:
    """
    8:00 PM - Evening planning scan.
    
    Prepare for next day (informational only, lower priority):
    - Earnings TOMORROW
    - Ex-dividend TOMORROW
    - Positions expiring TOMORROW
    
    Args:
        positions: List of position objects
        
    Returns:
        List of informational alerts
    """
    logger.info(f"V3 8PM Scan: Preparing next day planning")
    
    scan_filter = get_global_scan_filter()
    tomorrow_events = []
    tomorrow = date.today() + timedelta(days=1)
    
    for position in positions:
        try:
            position_id = _get_position_id(position)
            
            # Check if expiring TOMORROW
            if position.expiration_date == tomorrow:
                rec = {
                    'action': 'EXPIRES_TOMORROW',
                    'type': 'EXPIRES_TOMORROW',
                    'symbol': position.symbol,
                    'priority': 'info',
                    'message': 'Position expires tomorrow - prepare to act in morning',
                    'details': {
                        'strike': position.strike_price,
                        'option_type': position.option_type,
                    }
                }
                
                if scan_filter.should_send(position_id, rec):
                    tomorrow_events.append(rec)
            
            # Check for earnings tomorrow
            if _has_earnings_tomorrow(position.symbol):
                rec = {
                    'action': 'EARNINGS_TOMORROW',
                    'type': 'EARNINGS_TOMORROW',
                    'symbol': position.symbol,
                    'priority': 'info',
                    'message': 'Earnings announcement tomorrow - be aware',
                }
                
                if scan_filter.should_send(position_id + '_earnings', rec):
                    tomorrow_events.append(rec)
                    
        except Exception as e:
            logger.error(f"8PM: Error checking {position.symbol}: {e}")
    
    logger.info(f"V3 8PM Scan: Found {len(tomorrow_events)} tomorrow events")
    return tomorrow_events


def _check_8am_urgent(
    position, 
    morning_state: Optional[PositionState],
    evaluator: PositionEvaluator
) -> List[Dict[str, Any]]:
    """
    Check what changed since 6 AM that requires immediate action.
    """
    urgent_reasons = []
    
    if not morning_state:
        return urgent_reasons
    
    try:
        # Get current state
        from app.modules.strategies.utils.option_calculations import calculate_itm_status
        indicators = evaluator.ta_service.get_technical_indicators(position.symbol)
        if not indicators:
            return urgent_reasons
        
        current_price = indicators.current_price
        itm_calc = calculate_itm_status(
            current_price, position.strike_price, position.option_type
        )
        is_itm = itm_calc['is_itm']
        itm_pct = itm_calc['itm_pct']
        
        # 1. Newly ITM (state change from OTM → ITM)
        if not morning_state.was_itm and is_itm:
            result = evaluator.evaluate(position)
            if result:
                rec = _result_to_dict(result)
                rec['type'] = 'NEW_ITM'
                rec['message'] = f'Went ITM at market open ({position.symbol} now ${current_price:.2f})'
                urgent_reasons.append(rec)
        
        # 2. Can now pull back (new opportunity)
        current_weeks = (position.expiration_date - date.today()).days // 7
        if current_weeks > 1 and not morning_state.could_pull_back:
            pull_back = check_pull_back_opportunity(
                symbol=position.symbol,
                current_expiration=position.expiration_date,
                current_strike=position.strike_price,
                option_type=position.option_type,
                current_premium=getattr(position, 'current_premium', 1.0),
                original_premium=getattr(position, 'original_premium', 1.0),
                contracts=position.contracts
            )
            if pull_back:
                urgent_reasons.append({
                    'action': 'PULL_BACK',
                    'type': 'PULLBACK_AVAILABLE',
                    'symbol': position.symbol,
                    'priority': 'high',
                    'message': 'Can now pull back to earlier expiration',
                    'pull_back_data': {
                        'from_weeks': pull_back.from_weeks,
                        'to_weeks': pull_back.to_weeks,
                    }
                })
        
        # 3. Earnings TODAY
        if _has_earnings_today(position.symbol):
            urgent_reasons.append({
                'action': 'EARNINGS_TODAY',
                'type': 'EARNINGS_TODAY',
                'symbol': position.symbol,
                'priority': 'urgent',
                'message': 'Earnings announcement today - last chance to act'
            })
        
        # 4. Deep ITM getting significantly worse
        if morning_state.was_itm:
            additional_itm = itm_pct - morning_state.itm_pct
            if additional_itm > 10:
                result = evaluator.evaluate(position)
                if result:
                    rec = _result_to_dict(result)
                    rec['type'] = 'DEEPER_ITM'
                    rec['message'] = f'Position {additional_itm:.1f}% deeper ITM since morning'
                    urgent_reasons.append(rec)
        
        # 5. Expiring TODAY
        if position.expiration_date == date.today():
            urgent_reasons.append({
                'action': 'EXPIRES_TODAY',
                'type': 'EXPIRES_TODAY',
                'symbol': position.symbol,
                'priority': 'urgent',
                'message': 'Position expires today - roll or accept assignment'
            })
            
    except Exception as e:
        logger.error(f"Error in 8AM urgent check for {position.symbol}: {e}")
    
    return urgent_reasons


def _capture_state(position, evaluator: PositionEvaluator) -> PositionState:
    """Capture current position state for later comparison."""
    try:
        from app.modules.strategies.utils.option_calculations import calculate_itm_status
        
        indicators = evaluator.ta_service.get_technical_indicators(position.symbol)
        if not indicators:
            return PositionState(
                was_itm=False,
                itm_pct=0,
                could_pull_back=False,
                current_price=0,
                profit_pct=0
            )
        
        current_price = indicators.current_price
        itm_calc = calculate_itm_status(
            current_price, position.strike_price, position.option_type
        )
        
        # Check if pull-back is available
        current_weeks = (position.expiration_date - date.today()).days // 7
        could_pull_back = False
        if current_weeks > 1:
            pull_back = check_pull_back_opportunity(
                symbol=position.symbol,
                current_expiration=position.expiration_date,
                current_strike=position.strike_price,
                option_type=position.option_type,
                current_premium=getattr(position, 'current_premium', 1.0),
                original_premium=getattr(position, 'original_premium', 1.0),
                contracts=position.contracts
            )
            could_pull_back = pull_back is not None
        
        original_premium = getattr(position, 'original_premium', 1.0)
        current_premium = getattr(position, 'current_premium', original_premium)
        profit_pct = (original_premium - current_premium) / original_premium if original_premium > 0 else 0
        
        return PositionState(
            was_itm=itm_calc['is_itm'],
            itm_pct=itm_calc['itm_pct'],
            could_pull_back=could_pull_back,
            current_price=current_price,
            profit_pct=profit_pct
        )
        
    except Exception as e:
        logger.warning(f"Error capturing state for {position.symbol}: {e}")
        return PositionState(
            was_itm=False,
            itm_pct=0,
            could_pull_back=False,
            current_price=0,
            profit_pct=0
        )


def _result_to_dict(result: EvaluationResult) -> Dict[str, Any]:
    """Convert EvaluationResult to dict for notifications."""
    return {
        'action': result.action,
        'symbol': result.symbol,
        'priority': result.priority,
        'reason': result.reason,
        'position_id': result.position_id,
        'new_strike': result.new_strike,
        'new_expiration': result.new_expiration.isoformat() if result.new_expiration else None,
        'net_cost': result.net_cost,
        'details': result.details,
        'pull_back_data': result.pull_back_data,
        'zero_cost_data': result.zero_cost_data,
    }


def _get_position_id(position) -> str:
    """Generate unique position identifier."""
    return f"{position.symbol}_{position.strike_price}_{position.expiration_date.isoformat()}"


def _has_earnings_today(symbol: str) -> bool:
    """Check if stock has earnings today."""
    try:
        from app.modules.strategies.option_monitor import EarningsTracker
        tracker = EarningsTracker()
        earnings_date = tracker.get_next_earnings_date(symbol)
        return earnings_date == date.today() if earnings_date else False
    except Exception:
        return False


def _has_earnings_tomorrow(symbol: str) -> bool:
    """Check if stock has earnings tomorrow."""
    try:
        from app.modules.strategies.option_monitor import EarningsTracker
        tracker = EarningsTracker()
        earnings_date = tracker.get_next_earnings_date(symbol)
        tomorrow = date.today() + timedelta(days=1)
        return earnings_date == tomorrow if earnings_date else False
    except Exception:
        return False

