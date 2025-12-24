"""
Smart Assignment Strategy for IRA/Roth IRA Accounts

V3.0: On expiration Friday, evaluate borderline ITM positions.
Decide: Accept assignment vs Roll.

When to Use:
- Position is 0.1% - 2.0% ITM (borderline)
- Account is IRA or Roth IRA (no wash sale concerns)
- Expiring TODAY (Friday)

Strategy:
- If assignment loss < roll cost (debit + opportunity cost)
- Accept assignment → Buy back Monday → Sell new weekly
- This can save $50-200 per contract in borderline situations

Why IRA Only:
- No wash sale concerns
- No tax implications for buy-back
- Clean round-trip in one account
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, date, timedelta
import logging

from app.modules.strategies.zero_cost_finder import find_zero_cost_roll
from app.modules.strategies.utils.option_calculations import calculate_itm_status
from app.modules.strategies.algorithm_config import get_config

logger = logging.getLogger(__name__)


@dataclass
class SmartAssignmentResult:
    """Result of smart assignment evaluation."""
    action: str  # 'ACCEPT_ASSIGNMENT' or 'ROLL'
    position_id: str
    symbol: str
    priority: str
    reason: str
    
    # Assignment details
    assignment_price: float
    current_price: float
    itm_pct: float
    itm_amount: float
    assignment_loss_per_share: float
    assignment_loss_total: float
    
    # Roll details (if available)
    roll_option: Optional[Dict[str, Any]]
    roll_debit: float
    roll_weeks: int
    opportunity_cost: float
    total_roll_cost: float
    
    # Comparison
    savings_by_assignment: float
    recommended: str  # 'assignment' or 'roll'


def evaluate_smart_assignment_ira(
    position,
    ta_service=None,
    option_fetcher=None
) -> Optional[SmartAssignmentResult]:
    """
    On expiration Friday, decide: Accept assignment vs Roll.
    Only for IRA/Roth IRA accounts with borderline ITM positions.
    
    Args:
        position: Position expiring today
        ta_service: TechnicalAnalysisService instance
        option_fetcher: OptionChainFetcher instance
    
    Returns:
        SmartAssignmentResult if applicable, None otherwise
    """
    # Get services if not provided
    if ta_service is None:
        from app.modules.strategies.technical_analysis import get_technical_analysis_service
        ta_service = get_technical_analysis_service()
    
    if option_fetcher is None:
        from app.modules.strategies.option_monitor import OptionChainFetcher
        option_fetcher = OptionChainFetcher()
    
    # Get config
    config = get_config('v3')
    smart_config = config.get('smart_assignment', {})
    
    if not smart_config.get('enabled', True):
        return None
    
    # ================================================================
    # CHECK PREREQUISITES
    # ================================================================
    
    # 1. Only for IRA/Roth IRA accounts
    account_type = getattr(position, 'account_type', '').upper()
    allowed_accounts = smart_config.get('accounts', ['IRA', 'ROTH_IRA'])
    
    # Normalize account types
    normalized_account = account_type.replace('_', ' ').replace('-', ' ')
    is_ira = any(
        acc.upper() in normalized_account or normalized_account in acc.upper()
        for acc in allowed_accounts
    )
    
    if not is_ira:
        logger.debug(f"Smart assignment: {position.symbol} skipped - not IRA ({account_type})")
        return None
    
    # 2. Only on expiration day
    today = date.today()
    days_to_exp = (position.expiration_date - today).days
    
    if days_to_exp != 0:
        logger.debug(f"Smart assignment: {position.symbol} skipped - {days_to_exp} days to expiration")
        return None
    
    # 3. Get current price and ITM status
    indicators = ta_service.get_technical_indicators(position.symbol)
    if not indicators:
        logger.warning(f"Smart assignment: Cannot get indicators for {position.symbol}")
        return None
    
    current_price = indicators.current_price
    itm_calc = calculate_itm_status(current_price, position.strike_price, position.option_type)
    
    if not itm_calc['is_itm']:
        logger.debug(f"Smart assignment: {position.symbol} skipped - not ITM")
        return None
    
    itm_pct = itm_calc['itm_pct']
    itm_amount = itm_calc['intrinsic_value']
    
    # 4. Check ITM range: 0.1% - 2.0% (borderline)
    min_itm = smart_config.get('min_itm_pct', 0.1)
    max_itm = smart_config.get('max_itm_pct', 2.0)
    
    if itm_pct < min_itm or itm_pct > max_itm:
        logger.debug(
            f"Smart assignment: {position.symbol} skipped - {itm_pct:.2f}% ITM "
            f"outside range [{min_itm}%, {max_itm}%]"
        )
        return None
    
    # ================================================================
    # CALCULATE ASSIGNMENT COST
    # ================================================================
    contracts = position.contracts
    assignment_loss_per_share = itm_amount
    assignment_loss_total = assignment_loss_per_share * 100 * contracts
    
    # ================================================================
    # CALCULATE ROLL COST
    # ================================================================
    original_premium = getattr(position, 'original_premium', 1.0)
    current_premium = getattr(position, 'current_premium', itm_amount + 0.10)
    max_debit = original_premium * 0.20
    
    roll_analysis = find_zero_cost_roll(
        symbol=position.symbol,
        current_strike=position.strike_price,
        option_type=position.option_type,
        current_expiration=position.expiration_date,
        current_price=current_price,
        buy_back_cost=current_premium,
        original_premium=original_premium,
        contracts=contracts,
        max_months=12,
        delta_target=0.70,  # Delta 30
        ta_service=ta_service,
        option_fetcher=option_fetcher
    )
    
    if not roll_analysis:
        # Cannot roll within 52 weeks - assignment is only option
        logger.info(
            f"Smart assignment: {position.symbol} - cannot find roll, "
            f"recommend assignment (loss ${assignment_loss_total:.2f})"
        )
        
        return SmartAssignmentResult(
            action='ACCEPT_ASSIGNMENT',
            position_id=_get_position_id(position),
            symbol=position.symbol,
            priority='high',
            reason="Cannot find zero-cost roll within 52 weeks - accept assignment",
            assignment_price=position.strike_price,
            current_price=current_price,
            itm_pct=itm_pct,
            itm_amount=itm_amount,
            assignment_loss_per_share=assignment_loss_per_share,
            assignment_loss_total=assignment_loss_total,
            roll_option=None,
            roll_debit=0,
            roll_weeks=0,
            opportunity_cost=0,
            total_roll_cost=float('inf'),
            savings_by_assignment=float('inf'),
            recommended='assignment'
        )
    
    # ================================================================
    # COMPARE COSTS
    # ================================================================
    roll_net_cost = roll_analysis.net_cost
    roll_debit = max(roll_net_cost, 0) * 100 * contracts  # Total debit
    roll_weeks = roll_analysis.weeks_out
    
    # Check if roll is "too cheap" to consider assignment
    min_roll_weeks = smart_config.get('min_roll_weeks', 2)
    min_roll_debit = smart_config.get('min_roll_debit', 15)
    
    if roll_weeks < min_roll_weeks and roll_debit <= min_roll_debit:
        logger.debug(
            f"Smart assignment: {position.symbol} - roll is cheap "
            f"({roll_weeks}w, ${roll_debit:.2f}), using normal roll"
        )
        return None  # Roll is cheap enough, use normal roll logic
    
    # Estimate opportunity cost (weekly income lost while locked up)
    weekly_premium_estimate = _estimate_weekly_premium(position.symbol, ta_service, option_fetcher)
    weekly_income = weekly_premium_estimate * 100 * contracts
    opportunity_cost = weekly_income * roll_weeks
    
    # Total roll cost = debit + opportunity cost
    total_roll_cost = roll_debit + opportunity_cost
    
    logger.info(
        f"Smart assignment: {position.symbol} comparison - "
        f"Assignment loss: ${assignment_loss_total:.2f}, "
        f"Roll cost: ${total_roll_cost:.2f} (debit ${roll_debit:.2f} + opp ${opportunity_cost:.2f})"
    )
    
    # ================================================================
    # MAKE RECOMMENDATION
    # ================================================================
    if assignment_loss_total < total_roll_cost:
        savings = total_roll_cost - assignment_loss_total
        
        logger.info(
            f"Smart assignment: {position.symbol} - ACCEPT ASSIGNMENT "
            f"(saves ${savings:.2f})"
        )
        
        return SmartAssignmentResult(
            action='ACCEPT_ASSIGNMENT',
            position_id=_get_position_id(position),
            symbol=position.symbol,
            priority='high',
            reason=f"Assignment saves ${savings:.0f} vs rolling {roll_weeks} weeks",
            assignment_price=position.strike_price,
            current_price=current_price,
            itm_pct=itm_pct,
            itm_amount=itm_amount,
            assignment_loss_per_share=assignment_loss_per_share,
            assignment_loss_total=assignment_loss_total,
            roll_option={
                'expiration': roll_analysis.expiration_date.isoformat(),
                'weeks': roll_weeks,
                'strike': roll_analysis.strike,
                'new_premium': roll_analysis.new_premium,
                'net_cost': roll_net_cost,
            },
            roll_debit=roll_debit,
            roll_weeks=roll_weeks,
            opportunity_cost=opportunity_cost,
            total_roll_cost=total_roll_cost,
            savings_by_assignment=savings,
            recommended='assignment'
        )
    else:
        # Roll is cheaper - don't trigger smart assignment
        logger.debug(
            f"Smart assignment: {position.symbol} - roll is cheaper, using normal logic"
        )
        return None


def _estimate_weekly_premium(symbol: str, ta_service, option_fetcher) -> float:
    """
    Estimate weekly premium for this symbol (Delta 10 strike).
    
    Based on current volatility and typical covered call premiums.
    """
    try:
        # Get current price and volatility
        indicators = ta_service.get_technical_indicators(symbol)
        if not indicators:
            return 0.50  # Default estimate
        
        current_price = indicators.current_price
        weekly_vol = indicators.weekly_volatility
        
        # Get recommended Delta 10 strike
        strike_rec = ta_service.recommend_strike_price(
            symbol=symbol,
            option_type='call',
            expiration_weeks=1,
            probability_target=0.90  # Delta 10
        )
        
        if strike_rec:
            # Try to get actual premium from option chain
            today = date.today()
            days_to_friday = (4 - today.weekday()) % 7
            if days_to_friday == 0:
                days_to_friday = 7
            next_friday = today + timedelta(days=days_to_friday)
            
            chain = option_fetcher.get_option_chain(symbol, next_friday)
            if chain:
                calls = chain.get('calls')
                if calls is not None and not calls.empty:
                    matching = calls[
                        (calls['strike'] >= strike_rec.recommended_strike - 0.5) &
                        (calls['strike'] <= strike_rec.recommended_strike + 0.5)
                    ]
                    if not matching.empty:
                        row = matching.iloc[0]
                        bid = row.get('bid', 0) or 0
                        ask = row.get('ask', 0) or 0
                        if bid > 0 and ask > 0:
                            return (bid + ask) / 2
        
        # Fallback: Estimate based on volatility
        # Typical weekly Delta 10 premium is about 0.3-0.5% of stock price
        return current_price * weekly_vol * 0.3
        
    except Exception as e:
        logger.warning(f"Error estimating weekly premium for {symbol}: {e}")
        return 0.50  # Conservative default


def _get_position_id(position) -> str:
    """Generate unique position identifier."""
    return f"{position.symbol}_{position.strike_price}_{position.expiration_date.isoformat()}"


def get_smart_assignment_evaluator():
    """Factory function for dependency injection."""
    return {
        'evaluate_smart_assignment_ira': evaluate_smart_assignment_ira,
    }

