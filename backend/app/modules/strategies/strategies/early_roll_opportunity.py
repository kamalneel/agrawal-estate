"""
Early Roll Opportunity Strategy

Alerts when positions reach profit threshold with days remaining, suggesting early roll.
Uses technical analysis (Delta 10) to recommend optimal new strike price.

ALGORITHM VERSION AWARE:
- V1: 80% profit threshold (60% during earnings week)
- V2: 60% profit threshold (45% during earnings week, 35% for short DTE)

Set ALGORITHM_VERSION=v1 or ALGORITHM_VERSION=v2 in environment.
"""

from typing import List, Dict, Any, Optional
from datetime import date, datetime, timedelta, timezone
import logging

from app.modules.strategies.strategy_base import BaseStrategy, StrategyConfig
from app.modules.strategies.recommendations import StrategyRecommendation
from app.modules.strategies.option_monitor import OptionRollMonitor, get_positions_from_db
from app.modules.strategies.technical_analysis import TechnicalAnalysisService
from app.modules.strategies.algorithm_config import (
    get_config,
    get_profit_threshold,
    ALGORITHM_VERSION,
)

logger = logging.getLogger(__name__)

# Get thresholds from algorithm config (supports V1/V2 switching)
_config = get_config()
NORMAL_PROFIT_THRESHOLD = _config["early_roll"]["profit_threshold"]
EARNINGS_WEEK_PROFIT_THRESHOLD = _config["early_roll"]["earnings_week_profit_threshold"]
SHORT_DTE_THRESHOLD = _config["early_roll"].get("short_dte_threshold")


def _get_next_friday_after(ref_date: date) -> date:
    """Get the date of the Friday AFTER the reference date (for rolling to next week)."""
    # Find the next Friday after the reference date
    days_ahead = 4 - ref_date.weekday()  # Friday = 4
    if days_ahead <= 0:
        days_ahead += 7
    return ref_date + timedelta(days=days_ahead)


class EarlyRollOpportunityStrategy(BaseStrategy):
    """Strategy for identifying early roll opportunities.
    
    ALGORITHM VERSION AWARE:
    - V1: 80% profit threshold (60% during earnings week)
    - V2: 60% profit threshold (45% during earnings, 35% for short DTE)
    
    Switch versions via ALGORITHM_VERSION environment variable.
    """
    
    strategy_type = "early_roll_opportunity"
    name = "Early Roll Opportunities"
    description = f"[{ALGORITHM_VERSION.upper()}] Alerts when positions reach profit threshold with days remaining, suggesting early roll"
    category = "optimization"
    # Parameters loaded from algorithm_config based on ALGORITHM_VERSION
    default_parameters = {
        "profit_threshold": NORMAL_PROFIT_THRESHOLD,
        "earnings_week_profit_threshold": EARNINGS_WEEK_PROFIT_THRESHOLD,
        "short_dte_threshold": SHORT_DTE_THRESHOLD,
    }
    
    def generate_recommendations(self, params: Dict[str, Any]) -> List[StrategyRecommendation]:
        """Generate recommendations for early roll opportunities."""
        recommendations = []
        
        try:
            # Get positions from database first
            positions = get_positions_from_db(self.db)
            logger.info(f"Early Roll: Found {len(positions)} positions to analyze")
            
            if not positions:
                logger.info("Early Roll: No positions found in database")
                return recommendations
        except Exception as e:
            logger.error(f"Early Roll: Error getting positions: {e}", exc_info=True)
            return recommendations
        
        # Initialize technical analysis service for strike calculations and earnings data
        ta_service = TechnicalAnalysisService()
        
        # Cache earnings data and indicators for each unique symbol
        earnings_cache: Dict[str, tuple] = {}  # symbol -> (is_earnings_week, earnings_date, indicators)
        
        # Process each position with earnings-aware threshold
        for pos in positions:
            # Check if this symbol has earnings within the week (cache results)
            if pos.symbol not in earnings_cache:
                try:
                    indicators = ta_service.get_technical_indicators(pos.symbol)
                    is_earnings_week = indicators.earnings_within_week if indicators else False
                    earnings_date = indicators.earnings_date if indicators else None
                    earnings_cache[pos.symbol] = (is_earnings_week, earnings_date, indicators)
                    if is_earnings_week and indicators:
                        logger.info(f"Early Roll: {pos.symbol} has EARNINGS on {earnings_date} - using conservative 60% threshold")
                except Exception as e:
                    logger.debug(f"Could not check earnings for {pos.symbol}: {e}")
                    earnings_cache[pos.symbol] = (False, None, None)
            
            is_earnings_week, earnings_date, cached_indicators = earnings_cache.get(pos.symbol, (False, None, None))
            
            # Calculate days to expiration for short DTE threshold (V2 feature)
            days_to_exp = (pos.expiration_date - date.today()).days if pos.expiration_date else None
            
            # Use version-aware threshold (handles V1 vs V2 differences)
            # V1: 80%/60%, V2: 60%/45%/35%
            profit_threshold = get_profit_threshold(
                is_earnings_week=is_earnings_week,
                days_to_expiration=days_to_exp
            )
            
            # Check this position for roll opportunity
            monitor = OptionRollMonitor(profit_threshold=profit_threshold)
            alert = monitor.check_position(pos)
            
            if alert:
                rec = self._generate_roll_recommendation(
                    pos, alert, ta_service, cached_indicators, 
                    is_earnings_week, earnings_date, profit_threshold
                )
                if rec:
                    recommendations.append(rec)
        
        return recommendations
    
    def _generate_roll_recommendation(
        self, 
        pos, 
        alert, 
        ta_service: TechnicalAnalysisService,
        indicators,
        is_earnings_week: bool,
        earnings_date: Optional[date],
        profit_threshold: float
    ) -> Optional[StrategyRecommendation]:
        """Generate a single roll recommendation for a position."""
        
        # Determine priority based on days to expiration, earnings, and profit
        # V2: Days to expiration is the primary driver for urgency
        days_left = alert.days_to_expiry
        
        if days_left <= 0:
            priority = "urgent"  # Expires today
        elif days_left == 1:
            priority = "urgent"  # Expires tomorrow
        elif days_left <= 2:
            priority = "high"    # Expires in 2 days
        elif is_earnings_week:
            priority = "urgent"  # Earnings week always urgent
        elif alert.profit_percent >= 0.90:
            priority = "high"    # 90%+ profit captured
        elif alert.profit_percent >= 0.80:
            priority = "high"    # 80%+ profit captured (V2 still flags these)
        else:
            priority = "medium"  # Standard early roll (60-80% profit)
        
        # Calculate roll details
        profit_pct = int(alert.profit_percent * 100)
        current_expiry = pos.expiration_date
        logger.info(
            f"Early roll check: {pos.symbol} ${pos.strike_price} {pos.option_type} "
            f"in {pos.account_name} - Current expiration: {current_expiry}, "
            f"Profit: {profit_pct}%, Days left: {alert.days_to_expiry}"
            f"{' [EARNINGS WEEK]' if is_earnings_week else ''}"
        )
        
        # Get the Friday AFTER current expiry (roll to next week)
        next_friday = _get_next_friday_after(current_expiry)
        logger.info(f"Roll recommendation: {pos.symbol} - From {current_expiry} to {next_friday}")
        
        # V2: Check if stock is oversold - recommend Close + Wait instead of Roll
        should_wait_for_bounce = False
        wait_reason = None
        if indicators and indicators.rsi_14:
            if indicators.rsi_14 < 30:
                should_wait_for_bounce = True
                wait_reason = f"RSI at {indicators.rsi_14:.0f} (oversold) - stock likely to bounce"
                logger.info(f"{pos.symbol}: RSI={indicators.rsi_14:.0f} - recommending Close + Wait instead of Roll")
            elif indicators.rsi_14 < 35 and hasattr(indicators, 'bb_position') and indicators.bb_position in ["below_lower", "near_lower"]:
                should_wait_for_bounce = True
                wait_reason = f"RSI at {indicators.rsi_14:.0f} and near lower Bollinger Band - likely bounce"
                logger.info(f"{pos.symbol}: RSI={indicators.rsi_14:.0f}, BB={indicators.bb_position} - recommending Close + Wait")
        
        # Calculate new strike using Technical Analysis (Delta 10)
        strike_recommendation = ta_service.recommend_strike_price(
            symbol=pos.symbol,
            option_type=pos.option_type,
            expiration_weeks=1,
            probability_target=0.90  # Delta 10 = 90% probability OTM
        )
        
        # Get current price from cached indicators
        current_price = indicators.current_price if indicators else None
        
        # Use TA-recommended strike, or fall back to current strike if TA unavailable
        if strike_recommendation:
            new_strike = strike_recommendation.recommended_strike
            strike_rationale = strike_recommendation.rationale
            strike_source = getattr(strike_recommendation, 'source', 'unknown')
            logger.info(f"{pos.symbol} roll: TA recommends ${new_strike:.0f} strike (source: {strike_source})")
        else:
            new_strike = pos.strike_price
            strike_rationale = "Technical analysis unavailable - using current strike"
            strike_source = "fallback_current_strike"
            logger.warning(f"{pos.symbol} roll: TA unavailable, using current strike ${new_strike}")
        
        # Estimate new premium based on the strike distance from current price
        if current_price and new_strike > pos.strike_price:
            premium_factor = 0.75  # Rolling UP - expect slightly lower premium
        elif current_price and new_strike < pos.strike_price:
            premium_factor = 0.90  # Rolling DOWN - expect slightly higher premium
        else:
            premium_factor = 0.80  # Same strike or unknown
        
        estimated_new_premium = pos.original_premium * premium_factor
        estimated_total_income = estimated_new_premium * pos.contracts * 100
        
        # Format dates as MM/DD
        current_exp_str = current_expiry.strftime("%-m/%d")
        new_exp_str = next_friday.strftime("%-m/%d")
        
        # Format strikes for display
        old_strike_str = f"${pos.strike_price:.0f}" if pos.strike_price >= 10 else f"${pos.strike_price:.2f}"
        new_strike_str = f"${new_strike:.0f}" if new_strike >= 10 else f"${new_strike:.2f}"
        
        # V2: Adjust title/description based on whether we should wait for bounce
        price_info = f" Current price: ${current_price:.2f}." if current_price else ""
        
        if should_wait_for_bounce:
            # CLOSE + WAIT recommendation (stock is oversold)
            title = (
                f"⏸️ CLOSE {pos.contracts} {pos.symbol} {old_strike_str} ({current_exp_str}) - "
                f"WAIT to sell new call · {profit_pct}% profit"
            )
            description = (
                f"{profit_pct}% profit captured.{price_info} "
                f"⏸️ {wait_reason}. Close now, wait 2-3 days before selling new call at {new_strike_str}."
            )
            rationale_parts = [
                f"You've captured {profit_pct}% of the premium with {alert.days_to_expiry} days remaining.",
                f"⏸️ TIMING RECOMMENDATION: {wait_reason}",
                f"Close the {old_strike_str} call now to lock in profit.",
                f"Wait 2-3 days for the bounce, then sell new {new_strike_str} call for better premium.",
                f"Expected improvement: +10-20% premium after bounce."
            ]
            action = f"Buy to close {old_strike_str} at ${alert.current_premium:.2f}, then WAIT 2-3 days before selling new call"
            action_type = "close_wait"
        elif is_earnings_week:
            # Earnings week - standard roll but with warning
            title = (
                f"📊 EARNINGS: Roll {pos.contracts} {pos.symbol} {old_strike_str} ({current_exp_str}) → "
                f"{new_strike_str} ({new_exp_str}) - Earn ~${estimated_total_income:.0f}"
            )
            description = (
                f"📊 EARNINGS on {earnings_date.strftime('%b %d') if earnings_date else 'this week'}! "
                f"{profit_pct}% profit captured (using {int(profit_threshold*100)}% earnings threshold).{price_info} "
                f"Lock in profits before binary event."
            )
            rationale_parts = [
                f"⚠️ EARNINGS on {earnings_date} - using conservative threshold to lock in profits.",
                f"You've captured {profit_pct}% of the premium with {alert.days_to_expiry} days remaining.",
                f"Roll to {new_strike_str} for {new_exp_str} to collect ~${estimated_new_premium:.2f}/contract.",
                strike_rationale
            ]
            action = f"Buy to close {old_strike_str} at ${alert.current_premium:.2f}, sell {new_strike_str} {pos.option_type} for {new_exp_str}"
            action_type = "roll"
        else:
            # Standard roll recommendation
            title = (
                f"Roll {pos.contracts} {pos.symbol} {old_strike_str} ({current_exp_str}) → "
                f"{new_strike_str} ({new_exp_str}) - Earn ~${estimated_total_income:.0f}"
            )
            description = f"{profit_pct}% profit captured with {alert.days_to_expiry} days left.{price_info} Roll to collect new premium."
            rationale_parts = [
                f"You've captured {profit_pct}% of the premium with {alert.days_to_expiry} days remaining.",
                f"Roll to {new_strike_str} for {new_exp_str} to collect ~${estimated_new_premium:.2f}/contract.",
                strike_rationale
            ]
            action = f"Buy to close {old_strike_str} at ${alert.current_premium:.2f}, sell {new_strike_str} {pos.option_type} for {new_exp_str}"
            action_type = "roll"
        
        # Add RSI info to rationale
        if indicators and indicators.rsi_14:
            rsi_status = "overbought" if indicators.rsi_14 > 70 else "oversold" if indicators.rsi_14 < 30 else "neutral"
            rationale_parts.append(f"RSI: {indicators.rsi_14:.0f} ({rsi_status})")
        
        rationale = " ".join(rationale_parts)
        
        # Include account in ID to make unique per account
        account_slug = (pos.account_name or "unknown").replace(" ", "_").replace("'", "")
        
        return StrategyRecommendation(
            id=f"roll_early_{pos.symbol}_{pos.strike_price}_{pos.expiration_date.isoformat()}_{account_slug}",
            type=self.strategy_type,
            category=self.category,
            priority=priority,
            title=title,
            description=description,
            rationale=rationale,
            action=action,
            action_type=action_type,
            potential_income=estimated_total_income,
            potential_risk="low",
            time_horizon="immediate" if alert.days_to_expiry <= 2 or is_earnings_week else "this_week",
            symbol=pos.symbol,
            account_name=pos.account_name,
            context={
                "symbol": pos.symbol,
                "strike_price": pos.strike_price,
                "option_type": pos.option_type,
                "expiration_date": pos.expiration_date.isoformat(),
                "contracts": pos.contracts,
                "profit_percent": profit_pct,
                "days_remaining": alert.days_to_expiry,
                "original_premium": pos.original_premium,
                "current_premium": alert.current_premium,
                "profit_amount": alert.profit_amount,
                "account": pos.account_name,
                # Roll details with TA-recommended strike
                "new_strike": new_strike,
                "old_strike": pos.strike_price,
                "new_expiration": next_friday.isoformat(),
                "estimated_new_premium": estimated_new_premium,
                "estimated_total_income": estimated_total_income,
                # Technical analysis context
                "current_price": current_price,
                "strike_rationale": strike_rationale,
                "strike_source": strike_source,
                "rsi": indicators.rsi_14 if indicators else None,
                "ta_available": strike_recommendation is not None,
                # Earnings awareness
                "is_earnings_week": is_earnings_week,
                "earnings_date": earnings_date.isoformat() if earnings_date else None,
                "profit_threshold_used": profit_threshold,
                # V2: Strategic timing
                "should_wait_for_bounce": should_wait_for_bounce,
                "wait_reason": wait_reason,
                "bb_position": indicators.bb_position if indicators and hasattr(indicators, 'bb_position') else None,
            },
            expires_at=datetime.utcnow() + timedelta(days=alert.days_to_expiry)
        )
