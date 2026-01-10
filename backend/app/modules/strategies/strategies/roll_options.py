"""
Roll Options Strategy

ALGORITHM VERSION AWARE:
- V1: Scenarios A, B, C (includes end-of-week auto-roll)
- V2: Scenarios A, C, D (removes end-of-week, adds preemptive roll)

Set ALGORITHM_VERSION=v1 or ALGORITHM_VERSION=v2 in environment.

Scenario A: Early Roll (Profit Target Hit)
- V1: Option captured 80%+ profit
- V2: Option captured 60%+ profit
- Roll to next Friday with new strike from technical analysis

Scenario B: End-of-Week Roll (Time-Based) - V1 ONLY
- Thursday/Friday, option expires this Friday
- Less than profit threshold captured, but NOT in the money
- Roll to avoid losing the 2-day gap window
- REMOVED in V2: Let options expire, sell fresh Monday for better premium

Scenario C: In The Money (ITM)
- Stock moved against position
- Technical analysis to determine: Wait vs Roll out 3-4 weeks

Scenario D: Preemptive Roll (V2 ONLY)
- Stock approaching strike with momentum
- Alert before position goes ITM

EARNINGS AWARENESS:
- During earnings week, be MORE AGGRESSIVE about ITM rolls (don't wait for reversal)
- Binary earnings events can cause 5-15% gaps, making ITM positions much worse
- Always recommend rolling before earnings even if reversal signals exist
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
import logging

from app.modules.strategies.strategy_base import BaseStrategy
from app.modules.strategies.recommendations import StrategyRecommendation
from app.modules.strategies.option_monitor import get_positions_from_db, OptionRollMonitor, OptionChainFetcher
from app.modules.strategies.technical_analysis import get_technical_analysis_service
from app.modules.strategies.algorithm_config import (
    get_config,
    get_profit_threshold,
    is_feature_enabled,
    ALGORITHM_VERSION,
)
# V3: Simplified utility functions
from app.modules.strategies.utils.option_calculations import (
    calculate_itm_status,
    is_acceptable_cost,
)
# V3: Zero-cost finder (replaces multi-week optimizer scoring)
from app.modules.strategies.zero_cost_finder import (
    find_zero_cost_roll,
    ZeroCostRollResult,
)

logger = logging.getLogger(__name__)

# Load config
_config = get_config()


def generate_close_recommendation(
    position,
    reason: str = "Cannot find zero-cost roll within 52 weeks",
    itm_pct: float = 0,
    intrinsic_value: float = 0
) -> 'StrategyRecommendation':
    """
    V3 SIMPLIFIED: Generate a CLOSE recommendation.
    
    V3 Strategy: Only close when cannot find zero-cost roll within 52 weeks.
    This is the ONLY reason to close in V3 - no ITM thresholds.
    
    Args:
        position: The option position
        reason: Why we're recommending close
        itm_pct: Current ITM percentage
        intrinsic_value: Current intrinsic value
        
    Returns:
        StrategyRecommendation with CLOSE action
    """
    # Estimate close cost
    close_cost_per_share = intrinsic_value * 1.05  # Add 5% for time value/slippage
    close_cost_total = close_cost_per_share * 100 * position.contracts
    
    title = f"🚨 CLOSE {position.symbol} ${position.strike_price} {position.option_type.upper()} - Cannot escape within 52 weeks"
    
    # Build context
    context = {
        "symbol": position.symbol,
        "scenario": "C_itm_catastrophic_close",
        "current_strike": position.strike_price,
        "option_type": position.option_type,
        "contracts": position.contracts,
        "account": position.account_name,
        "itm_percent": round(itm_pct, 1),
        "intrinsic_value": round(intrinsic_value, 2),
        "close_cost_per_share": round(close_cost_per_share, 2),
        "close_cost_total": round(close_cost_total, 2),
        "reason": reason,
        "v3_note": "V3: Only close when cannot find zero-cost roll within 52 weeks",
    }
    
    description = (
        f"{position.contracts}x {position.symbol} ${position.strike_price} {position.option_type}\n"
        f"Currently {itm_pct:.1f}% ITM (${intrinsic_value:.2f} intrinsic)\n\n"
        f"CATASTROPHIC: {reason}\n"
        f"Estimated close cost: ${close_cost_per_share:.2f}/share (${close_cost_total:.0f} total)"
    )
    
    rationale = (
        f"Position is {itm_pct:.1f}% ITM. Searched up to 52 weeks but cannot find "
        f"a roll within 20% of original premium. Close and redeploy capital."
    )
    
    account_slug = (position.account_name or "unknown").replace(" ", "_").replace("'", "")
    
    return StrategyRecommendation(
        id=f"roll_itm_close_{position.symbol}_{position.strike_price}_{date.today().isoformat()}_{account_slug}",
        type="roll_options",
        category="optimization",
        priority="urgent",
        title=title,
        description=description,
        rationale=rationale,
        action=f"Close {position.contracts}x {position.symbol} ${position.strike_price} {position.option_type} at approximately ${close_cost_per_share:.2f}/share",
        action_type="close",
        potential_income=None,
        potential_risk="high",
        time_horizon="immediate",
        symbol=position.symbol,
        account_name=position.account_name,
        context=context,
        expires_at=datetime.combine(position.expiration_date, datetime.max.time())
    )


class RollOptionsStrategy(BaseStrategy):
    """
    Strategy for rolling options with technical analysis-based strike selection.
    
    ALGORITHM VERSION AWARE:
    - V1: Scenarios A, B, C
    - V2: Scenarios A, C, D (end-of-week removed, preemptive added)
    """
    
    strategy_type = "roll_options"
    name = "Roll"
    description = f"[{ALGORITHM_VERSION.upper()}] Smart rolling with technical analysis for strike selection"
    category = "optimization"
    # Parameters loaded from algorithm_config based on ALGORITHM_VERSION
    default_parameters = {
        "profit_threshold_early": int(_config["early_roll"]["profit_threshold"] * 100),
        "profit_threshold_low": 50,  # % below this on Thu/Fri triggers Scenario B (V1 only)
        "itm_threshold_percent": _config["itm_roll"]["itm_threshold_percent"],
        "enable_end_of_week_roll": _config["roll_options"]["enable_end_of_week_roll"],
        "enable_preemptive_roll": _config["preemptive_roll"]["enabled"],
    }
    
    def generate_recommendations(self, params: Dict[str, Any]) -> List[StrategyRecommendation]:
        """Generate roll recommendations for all three scenarios."""
        recommendations = []
        
        profit_threshold_early = self.get_parameter("profit_threshold_early", 80) / 100.0
        profit_threshold_low = self.get_parameter("profit_threshold_low", 50) / 100.0
        
        # Get open positions from database
        positions = get_positions_from_db(self.db)
        
        if not positions:
            return recommendations
        
        today = date.today()
        day_of_week = today.weekday()  # 0=Monday, 4=Friday
        is_thursday_or_friday = day_of_week >= 3
        
        monitor = OptionRollMonitor(profit_threshold=profit_threshold_early)
        ta_service = get_technical_analysis_service()
        fetcher = OptionChainFetcher()
        
        for position in positions:
            try:
                # Get current option quote
                alert = monitor.check_position(position)
                
                # Check ITM status and earnings
                indicators = ta_service.get_technical_indicators(position.symbol)
                if not indicators:
                    continue
                
                current_price = indicators.current_price
                strike = position.strike_price
                
                # Check for upcoming earnings (within 5 trading days)
                is_earnings_week = indicators.earnings_within_week
                earnings_date = indicators.earnings_date
                
                if is_earnings_week:
                    logger.info(f"EARNINGS ALERT: {position.symbol} has earnings on {earnings_date}")
                
                # V2.2: Use centralized ITM calculation
                itm_status = calculate_itm_status(current_price, strike, position.option_type)
                is_itm = itm_status['is_itm']
                itm_pct = itm_status['itm_pct']
                
                days_to_expiry = (position.expiration_date - today).days
                expires_this_week = days_to_expiry <= 2
                
                # Calculate profit if we have alert data
                profit_pct = alert.profit_percent if alert else 0
                
                # === SCENARIO C: ITM Analysis ===
                if is_itm and itm_pct >= self.get_parameter("itm_threshold_percent", 1.0):
                    rec = self._handle_itm_scenario(
                        position, indicators, ta_service, itm_pct, days_to_expiry,
                        is_earnings_week=is_earnings_week, earnings_date=earnings_date
                    )
                    if rec:
                        recommendations.append(rec)
                    continue
                
                # === SCENARIO A: Early Roll (High Profit) ===
                if alert and profit_pct >= profit_threshold_early:
                    rec = self._handle_early_roll(
                        position, alert, indicators, ta_service,
                        is_earnings_week=is_earnings_week, earnings_date=earnings_date
                    )
                    if rec:
                        recommendations.append(rec)
                    continue
                
                # === SCENARIO B: End-of-Week Roll (V1 ONLY) ===
                # In V2, this is disabled - let options expire and sell fresh Monday
                if self.get_parameter("enable_end_of_week_roll", False):
                    if is_thursday_or_friday and expires_this_week and not is_itm:
                        # Only trigger if NOT already captured high profit
                        if profit_pct < profit_threshold_early:
                            rec = self._handle_end_of_week_roll(
                                position, indicators, ta_service, profit_pct, days_to_expiry,
                                is_earnings_week=is_earnings_week, earnings_date=earnings_date
                            )
                            if rec:
                                recommendations.append(rec)
                
                # === SCENARIO D: Preemptive Roll (V2 ONLY) ===
                # Alert when stock is approaching strike with momentum
                if self.get_parameter("enable_preemptive_roll", False):
                    if not is_itm and days_to_expiry > 2:
                        rec = self._handle_preemptive_roll(
                            position, indicators, ta_service, current_price, strike, days_to_expiry,
                            is_earnings_week=is_earnings_week, earnings_date=earnings_date
                        )
                        if rec:
                            recommendations.append(rec)
                
            except Exception as e:
                logger.error(f"Error analyzing {position.symbol} for roll: {e}")
                continue
        
        return recommendations
    
    def _handle_early_roll(
        self,
        position,
        alert,
        indicators,
        ta_service,
        is_earnings_week: bool = False,
        earnings_date: Optional[date] = None
    ) -> Optional[StrategyRecommendation]:
        """
        Scenario A: Early roll when 80-90%+ profit captured.
        Roll to next Friday with strike from technical analysis.
        
        COST AWARENESS:
        - Calculates actual net cost/credit of the roll
        - Skips if debit is too high relative to remaining premium
        
        EARNINGS AWARENESS:
        - During earnings week, add earnings alert emoji and context
        """
        # Get recommended strike for next week
        strike_rec = ta_service.recommend_strike_price(
            symbol=position.symbol,
            option_type=position.option_type,
            expiration_weeks=1,
            probability_target=0.90
        )
        
        if not strike_rec:
            return None
        
        next_friday = self._get_friday_after(position.expiration_date)
        
        # === COST CALCULATION ===
        # Buy-back cost: current option premium (what we pay to close)
        buy_back_cost = alert.current_premium
        
        # New premium: fetch actual market price for the new option
        new_premium = self._get_option_premium(
            position.symbol, 
            strike_rec.recommended_strike, 
            position.option_type, 
            next_friday
        )
        
        # DO NOT use fallback estimates - they can be dangerously inaccurate
        # Instead, show unavailable data and let user verify actual price
        if new_premium is None:
            premium_source = "unavailable"
            net_cost = None
            net_cost_total = None
            net_cost_str = "check new premium on Robinhood"
            is_credit = None
            logger.warning(f"{position.symbol}: New premium data unavailable - will indicate in recommendation")
        else:
            premium_source = "market"
            # Net cost: positive = debit (you pay), negative = credit (you receive)
            net_cost = buy_back_cost - new_premium
            net_cost_total = net_cost * 100 * position.contracts
            
            # Format for display
            if net_cost < 0:
                net_cost_str = f"${abs(net_cost):.2f} credit"
                is_credit = True
            else:
                net_cost_str = f"${net_cost:.2f} debit"
                is_credit = False
        
        # === COST SENSITIVITY CHECK ===
        # Only perform checks if we have actual premium data
        # If premium unavailable, still show recommendation but user must verify
        remaining_premium = position.original_premium - buy_back_cost
        
        if net_cost is not None and net_cost > 0:  # It's a debit
            # If debit > remaining premium, rolling costs more than just letting it expire
            if net_cost > remaining_premium and remaining_premium > 0:
                logger.info(
                    f"Skipping early roll for {position.symbol}: debit ${net_cost:.2f} > "
                    f"remaining premium ${remaining_premium:.2f}"
                )
                return None
            
            # If debit > 50% of new premium, it's a bad deal
            if new_premium and new_premium > 0 and net_cost > (new_premium * 0.5):
                logger.info(
                    f"Skipping early roll for {position.symbol}: debit ${net_cost:.2f} > "
                    f"50% of new premium ${new_premium:.2f}"
                )
                return None
        
        context = {
            "symbol": position.symbol,
            "scenario": "A_early_roll",
            "current_strike": position.strike_price,
            "new_strike": strike_rec.recommended_strike,
            "current_expiration": position.expiration_date.isoformat(),
            "new_expiration": next_friday.isoformat(),
            "contracts": position.contracts,
            "profit_percent": round(alert.profit_percent * 100, 1),
            "profit_amount": alert.profit_amount,
            "original_premium": position.original_premium,
            "current_premium": alert.current_premium,
            "account": position.account_name,
            # Cost analysis (values may be None if premium unavailable)
            "buy_back_cost": round(buy_back_cost, 2),
            "new_premium": round(new_premium, 2) if new_premium is not None else None,
            "new_premium_source": premium_source,  # "market" or "unavailable"
            "net_cost": round(net_cost, 2) if net_cost is not None else None,
            "net_cost_total": round(net_cost_total, 2) if net_cost_total is not None else None,
            "is_credit": is_credit,  # None if premium unavailable
            # Technical analysis
            "technical_analysis": {
                "current_price": indicators.current_price,
                "rsi": round(indicators.rsi_14, 1),
                "weekly_volatility": round(indicators.weekly_volatility * 100, 2),
                "prob_90_high": indicators.prob_90_high,
                "nearest_resistance": indicators.nearest_resistance,
            },
            "strike_rationale": strike_rec.rationale,
        }
        
        # Title includes net cost/credit
        title = (
            f"ROLL {position.symbol} ${position.strike_price}→${strike_rec.recommended_strike:.0f} "
            f"{position.option_type} ({net_cost_str})"
        )
        
        # V2: Priority based on days to expiration
        days_left = alert.days_to_expiry if hasattr(alert, 'days_to_expiry') else (position.expiration_date - date.today()).days
        if days_left <= 0:
            priority = "urgent"  # Expires today
        elif days_left == 1:
            priority = "urgent"  # Expires tomorrow
        elif days_left <= 2:
            priority = "high"    # Expires in 2 days
        elif is_earnings_week:
            priority = "urgent"  # Earnings week
        elif alert.profit_percent >= 0.90:
            priority = "high"    # 90%+ captured
        else:
            priority = "medium"  # Standard early roll
        
        # Format premium strings (handle unavailable data)
        new_premium_str = f"${new_premium:.2f}" if new_premium is not None else "premium not available"
        
        # Description/rationale handling for unavailable premium
        if new_premium is not None:
            description = (
                f"Roll {position.symbol} ${position.strike_price} {position.option_type} "
                f"{position.expiration_date.strftime('%b %d')} → "
                f"{next_friday.strftime('%b %d')} ${strike_rec.recommended_strike:.0f} - "
                f"{net_cost_str}/share ({alert.profit_percent*100:.0f}% profit captured)"
            )
            rationale = (
                f"Captured {alert.profit_percent*100:.0f}% profit. "
                f"Roll cost: buy back at ${buy_back_cost:.2f}, sell new at {new_premium_str} = {net_cost_str}. "
                f"{strike_rec.rationale}"
            )
            action = (
                f"Buy to close ${position.strike_price} {position.option_type} at ${buy_back_cost:.2f}, "
                f"sell ${strike_rec.recommended_strike:.0f} {position.option_type} for {next_friday.strftime('%b %d')} "
                f"at ~{new_premium_str} ({net_cost_str})"
            )
            potential_income = abs(net_cost_total) if is_credit else new_premium * 100 * position.contracts
        else:
            description = (
                f"Roll {position.symbol} ${position.strike_price} {position.option_type} "
                f"{position.expiration_date.strftime('%b %d')} → "
                f"{next_friday.strftime('%b %d')} ${strike_rec.recommended_strike:.0f} - "
                f"Check new premium ({alert.profit_percent*100:.0f}% profit captured)"
            )
            rationale = (
                f"Captured {alert.profit_percent*100:.0f}% profit. "
                f"Roll cost: buy back at ${buy_back_cost:.2f}, sell new at {new_premium_str}. "
                f"{strike_rec.rationale}"
            )
            action = (
                f"Buy to close ${position.strike_price} {position.option_type} at ${buy_back_cost:.2f}, "
                f"sell ${strike_rec.recommended_strike:.0f} {position.option_type} for {next_friday.strftime('%b %d')} "
                f"({net_cost_str})"
            )
            potential_income = None
        
        # Include account in ID to make unique per account
        account_slug = (position.account_name or "unknown").replace(" ", "_").replace("'", "")
        return StrategyRecommendation(
            id=f"roll_early_{position.symbol}_{position.strike_price}_{date.today().isoformat()}_{account_slug}",
            type=self.strategy_type,
            category=self.category,
            priority=priority,
            title=title,
            description=description,
            rationale=rationale,
            action=action,
            action_type="roll",
            potential_income=potential_income,
            potential_risk="low",
            time_horizon="this_week",
            symbol=position.symbol,
            account_name=position.account_name,
            context=context,
            expires_at=datetime.combine(position.expiration_date, datetime.max.time())
        )
    
    def _handle_end_of_week_roll(
        self,
        position,
        indicators,
        ta_service,
        profit_pct: float,
        days_to_expiry: int,
        is_earnings_week: bool = False,
        earnings_date: Optional[date] = None
    ) -> Optional[StrategyRecommendation]:
        """
        Scenario B: Thursday/Friday roll to avoid gap risk.
        Roll to next Friday even if not at target profit.
        
        COST AWARENESS:
        - Calculates actual net cost/credit of the roll
        - Shows cost in notification
        - Skips if debit is unreasonably high
        
        EARNINGS AWARENESS:
        - During earnings week, add extra urgency to the recommendation
        """
        strike_rec = ta_service.recommend_strike_price(
            symbol=position.symbol,
            option_type=position.option_type,
            expiration_weeks=1,
            probability_target=0.90
        )
        
        if not strike_rec:
            return None
        
        # Roll to the Friday AFTER the current expiration (not just next Friday from today)
        # This ensures we're always rolling forward, even if checking on Thursday for Friday expiry
        next_friday = self._get_friday_after(position.expiration_date)
        
        # === COST CALCULATION ===
        # Get current option price (buy-back cost)
        current_option_price = self._get_option_premium(
            position.symbol,
            position.strike_price,
            position.option_type,
            position.expiration_date
        )
        
        # Estimate if we can't get market price
        if current_option_price is None:
            # For end-of-week, option should be cheap (mostly time value)
            # Estimate based on remaining premium
            current_option_price = position.original_premium * (1 - profit_pct)
        
        buy_back_cost = current_option_price
        
        # Get new option premium
        new_premium = self._get_option_premium(
            position.symbol,
            strike_rec.recommended_strike,
            position.option_type,
            next_friday
        )
        
        if new_premium is None:
            # Estimate new premium based on original (assume similar premium)
            new_premium = position.original_premium * 0.9
            premium_source = "estimated"
        else:
            premium_source = "market"
        
        # Net cost calculation
        net_cost = buy_back_cost - new_premium
        net_cost_total = net_cost * 100 * position.contracts
        
        if net_cost < 0:
            net_cost_str = f"${abs(net_cost):.2f} credit"
            is_credit = True
        else:
            net_cost_str = f"${net_cost:.2f} debit"
            is_credit = False
        
        # === COST SENSITIVITY CHECK ===
        # For end-of-week rolls, we're more lenient because avoiding gap risk has value
        # But still skip if debit is > new premium (you're paying more than you'll receive)
        if net_cost > 0 and new_premium > 0:
            if net_cost > new_premium:
                logger.info(
                    f"Skipping end-of-week roll for {position.symbol}: debit ${net_cost:.2f} > "
                    f"new premium ${new_premium:.2f} - not worth it"
                )
                return None
        
        context = {
            "symbol": position.symbol,
            "scenario": "B_end_of_week",
            "current_strike": position.strike_price,
            "new_strike": strike_rec.recommended_strike,
            "current_expiration": position.expiration_date.isoformat(),
            "new_expiration": next_friday.isoformat(),
            "contracts": position.contracts,
            "profit_percent": round(profit_pct * 100, 1),
            "days_to_expiry": days_to_expiry,
            "account": position.account_name,
            # Cost analysis
            "buy_back_cost": round(buy_back_cost, 2),
            "new_premium": round(new_premium, 2),
            "new_premium_source": premium_source,
            "net_cost": round(net_cost, 2),
            "net_cost_total": round(net_cost_total, 2),
            "is_credit": is_credit,
            "technical_analysis": {
                "current_price": indicators.current_price,
                "rsi": round(indicators.rsi_14, 1),
                "weekly_volatility": round(indicators.weekly_volatility * 100, 2),
            },
            "strike_rationale": strike_rec.rationale,
        }
        
        day_name = "Friday" if days_to_expiry == 0 else "Thursday"
        title = f"ROLL {position.symbol} ${position.strike_price}→${strike_rec.recommended_strike:.0f} ({day_name}, {net_cost_str})"
        
        return StrategyRecommendation(
            id=f"roll_eow_{position.symbol}_{position.strike_price}_{date.today().isoformat()}",
            type=self.strategy_type,
            category=self.category,
            priority="high" if days_to_expiry == 0 else "medium",
            title=title,
            description=(
                f"Roll {position.symbol} ${position.strike_price} {position.option_type} "
                f"{position.expiration_date.strftime('%b %d')} → "
                f"{next_friday.strftime('%b %d')} ${strike_rec.recommended_strike:.0f} - "
                f"{net_cost_str}/share, avoid weekend gap"
            ),
            rationale=(
                f"Option expires {day_name} with {profit_pct*100:.0f}% profit. "
                f"Roll now to capture next week's premium and avoid weekend gap risk. "
                f"{strike_rec.rationale}"
            ),
            action=(
                f"Roll {position.symbol} ${position.strike_price} {position.option_type} "
                f"to {next_friday.strftime('%b %d')} ${strike_rec.recommended_strike:.0f}"
            ),
            action_type="roll",
            potential_income=position.original_premium * position.contracts * 100,
            potential_risk="low",
            time_horizon="immediate",
            symbol=position.symbol,
            account_name=position.account_name,
            context=context,
            expires_at=datetime.combine(position.expiration_date, datetime.max.time())
        )
    
    def _handle_preemptive_roll(
        self,
        position,
        indicators,
        ta_service,
        current_price: float,
        strike: float,
        days_to_expiry: int,
        is_earnings_week: bool = False,
        earnings_date: Optional[date] = None
    ) -> Optional[StrategyRecommendation]:
        """
        Scenario D (V2 ONLY): Preemptive roll when stock is approaching strike.
        
        Alert when stock is within 3% of strike with momentum, before position goes ITM.
        """
        # Get preemptive roll config
        preemptive_config = _config.get("preemptive_roll", {})
        approaching_threshold = preemptive_config.get("approaching_threshold_pct", 3.0)
        urgent_threshold = preemptive_config.get("urgent_threshold_pct", 1.5)
        
        # Calculate distance to strike
        if position.option_type.lower() == "call":
            # For calls, we're concerned when stock approaches from below
            if current_price >= strike:
                return None  # Already ITM, handled by Scenario C
            distance_pct = (strike - current_price) / strike * 100
            approaching = distance_pct <= approaching_threshold
        else:
            # For puts, we're concerned when stock approaches from above
            if current_price <= strike:
                return None  # Already ITM, handled by Scenario C
            distance_pct = (current_price - strike) / strike * 100
            approaching = distance_pct <= approaching_threshold
        
        if not approaching:
            return None
        
        # Check momentum (is stock moving toward strike?)
        # Simple check: compare current price to 3-day average
        try:
            from app.modules.strategies.yahoo_cache import get_price_history
            hist = get_price_history(position.symbol, period="5d")
            if hist is not None and len(hist) >= 3:
                three_day_avg = hist['Close'].iloc[-3:].mean()
                if position.option_type.lower() == "call":
                    has_momentum = current_price > three_day_avg  # Moving up toward strike
                else:
                    has_momentum = current_price < three_day_avg  # Moving down toward strike
            else:
                has_momentum = True  # Assume momentum if we can't check
        except Exception:
            has_momentum = True  # Assume momentum on error
        
        if not has_momentum:
            return None  # Stock not moving toward strike
        
        # Determine priority
        if distance_pct <= urgent_threshold:
            priority = "urgent"
            message = "Stock very close to strike - consider preemptive roll"
        else:
            priority = "high"
            message = "Stock trending toward strike - prepare to roll"
        
        # Get recommended new strike
        strike_rec = ta_service.recommend_strike_price(
            symbol=position.symbol,
            option_type=position.option_type,
            expiration_weeks=2,  # Suggest 2 weeks for preemptive rolls
            probability_target=0.90
        )
        
        if not strike_rec:
            return None
        
        new_strike = strike_rec.recommended_strike
        next_exp = self._get_friday_after(position.expiration_date)
        # For preemptive, consider 2 weeks out
        next_exp_2wk = self._get_friday_after(next_exp)
        
        context = {
            "symbol": position.symbol,
            "scenario": "D_preemptive_roll",
            "current_strike": position.strike_price,
            "new_strike": new_strike,
            "current_price": current_price,
            "distance_to_strike_pct": round(distance_pct, 1),
            "days_to_expiry": days_to_expiry,
            "account": position.account_name,
            "has_momentum": has_momentum,
            "is_earnings_week": is_earnings_week,
            "earnings_date": earnings_date.isoformat() if earnings_date else None,
        }
        
        account_slug = (position.account_name or "unknown").replace(" ", "_").replace("'", "")
        
        title = (
            f"⚠️ {position.symbol} approaching ${strike:.0f} strike · "
            f"Stock ${current_price:.0f} ({distance_pct:.1f}% away)"
        )
        
        return StrategyRecommendation(
            id=f"roll_preemptive_{position.symbol}_{position.strike_price}_{date.today().isoformat()}_{account_slug}",
            type=self.strategy_type,
            category=self.category,
            priority=priority,
            title=title,
            description=(
                f"{position.symbol} is {distance_pct:.1f}% from your ${strike:.0f} {position.option_type} strike "
                f"with bullish momentum. {message}"
            ),
            rationale=(
                f"Stock at ${current_price:.2f}, strike at ${strike:.0f} ({distance_pct:.1f}% away). "
                f"Momentum detected. Consider rolling to ${new_strike:.0f} for {next_exp_2wk.strftime('%b %d')} "
                f"before position goes ITM. {strike_rec.rationale}"
            ),
            action=(
                f"Consider rolling {position.symbol} ${strike:.0f} {position.option_type} "
                f"to ${new_strike:.0f} for {next_exp_2wk.strftime('%b %d')} (2 weeks)"
            ),
            action_type="roll",
            potential_income=None,
            potential_risk="medium",
            time_horizon="this_week",
            symbol=position.symbol,
            account_name=position.account_name,
            context=context,
            expires_at=datetime.combine(position.expiration_date, datetime.max.time())
        )

    def _handle_itm_scenario(
        self,
        position,
        indicators,
        ta_service,
        itm_pct: float,
        days_to_expiry: int,
        is_earnings_week: bool = False,
        earnings_date: Optional[date] = None
    ) -> Optional[StrategyRecommendation]:
        """
        V3 SIMPLIFIED: Scenario C - In The Money handling.
        
        V3 Strategy:
        1. Check if TA suggests waiting (can be overridden for earnings)
        2. Find zero-cost roll using ITM optimizer (up to 52 weeks)
        3. If found: recommend roll
        4. If not found within 52 weeks: recommend CLOSE (catastrophic)
        
        NO THRESHOLD CHECKS - any ITM% can be rolled if we can find zero-cost.
        Uses Delta 30 (70% OTM probability) for ITM escapes per V3 Addendum.
        """
        from app.modules.strategies.itm_roll_optimizer import get_itm_roll_optimizer
        
        current_price = indicators.current_price
        
        # ====================================================================
        # STEP 1: Check if TA suggests waiting (but override during earnings)
        # ====================================================================
        action, reason, analysis = ta_service.analyze_itm_position(
            symbol=position.symbol,
            strike_price=position.strike_price,
            option_type=position.option_type
        )
        
        # EARNINGS OVERRIDE: Never wait during earnings week
        if is_earnings_week and action == "wait":
            logger.info(f"EARNINGS OVERRIDE: {position.symbol} - overriding 'wait' to 'roll' due to earnings on {earnings_date}")
            action = "roll"
            reason = (
                f"⚠️ EARNINGS on {earnings_date.strftime('%b %d') if earnings_date else 'this week'}! "
                f"Binary earnings events can gap 5-15%."
            )
        
        if action == "wait":
            # WATCH notification - don't roll yet
            context = {
                "symbol": position.symbol,
                "scenario": "C_itm_wait",
                "current_strike": position.strike_price,
                "current_price": indicators.current_price,
                "itm_percent": round(itm_pct, 1),
                "days_to_expiry": days_to_expiry,
                "account": position.account_name,
                "technical_analysis": analysis,
                "action": "wait",
            }
            
            title = f"WATCH {position.symbol} ${position.strike_price} {position.option_type} - ITM {itm_pct:.1f}% (Stock ${indicators.current_price:.0f})"
            
            return StrategyRecommendation(
                id=f"roll_itm_wait_{position.symbol}_{position.strike_price}_{date.today().isoformat()}",
                type=self.strategy_type,
                category=self.category,
                priority="medium",
                title=title,
                description=(
                    f"{position.symbol} is {itm_pct:.1f}% ITM but showing reversal signals. "
                    f"Wait before rolling."
                ),
                rationale=reason,
                action="Monitor position - do not roll yet",
                action_type="monitor",
                potential_income=None,
                potential_risk="medium",
                time_horizon="this_week",
                context=context,
                expires_at=datetime.combine(position.expiration_date, datetime.max.time())
            )
        
        # ====================================================================
        # STEP 2: V3 - Use ITM Roll Optimizer with 20% cost rule
        # ====================================================================
        # V3: Calculate max acceptable debit (20% of original premium)
        # Note: We need original_premium from position
        original_premium = getattr(position, 'original_premium', 1.0)  # Default $1 if not available
        max_debit = original_premium * 0.20
        
        optimizer = get_itm_roll_optimizer()
        roll_analysis = optimizer.analyze_itm_position(
            symbol=position.symbol,
            current_strike=position.strike_price,
            option_type=position.option_type,
            current_expiration=position.expiration_date,
            contracts=position.contracts,
            account_name=position.account_name,
            max_weeks_out=52,  # V3: Up to 52 weeks (1 year)
            max_net_debit=max_debit,  # V3: Use 20% rule
            delta_target=0.70  # V3 Addendum: Delta 30 for ITM escapes
        )
        
        if not roll_analysis:
            # Cannot find zero-cost roll within 52 weeks - CATASTROPHIC
            logger.warning(f"Cannot find zero-cost roll for {position.symbol} within 52 weeks - recommending CLOSE")
            itm_calc = calculate_itm_status(current_price, position.strike_price, position.option_type)
            return generate_close_recommendation(
                position=position,
                reason="Cannot find zero-cost roll within 52 weeks",
                itm_pct=itm_pct,
                intrinsic_value=itm_calc['intrinsic_value']
            )
        
        # ====================================================================
        # V3.1 FIX: Check if position is CATASTROPHIC (cannot escape to OTM)
        # ====================================================================
        if roll_analysis.is_catastrophic:
            logger.warning(
                f"[CATASTROPHIC] {position.symbol}: {itm_pct:.1f}% ITM, "
                f"cannot escape to OTM within cost constraints - recommending CLOSE"
            )
            itm_calc = calculate_itm_status(current_price, position.strike_price, position.option_type)
            return generate_close_recommendation(
                position=position,
                reason=f"Cannot escape ITM ({itm_pct:.1f}%). All roll options remain deeply ITM.",
                itm_pct=itm_pct,
                intrinsic_value=itm_calc['intrinsic_value']
            )
        
        # ====================================================================
        # STEP 3: V3 - Return roll recommendation (no additional validation)
        # ====================================================================
        # Build context with roll options
        conservative = roll_analysis.conservative
        moderate = roll_analysis.moderate
        aggressive = roll_analysis.aggressive
        
        roll_options_data = []
        for opt, label in [(conservative, "Conservative"), (moderate, "Moderate"), (aggressive, "Aggressive")]:
            if opt:
                net_str = f"${abs(opt.net_cost):.2f} {'credit' if opt.net_cost < 0 else 'debit'}"
                roll_options_data.append({
                    "label": label,
                    "expiration": opt.expiration_date.isoformat(),
                    "expiration_display": opt.expiration_date.strftime('%b %d'),
                    "weeks_out": opt.expiration_weeks,
                    "strike": opt.new_strike,
                    "new_premium": round(opt.new_premium, 2),
                    "net_cost": round(opt.net_cost, 2),
                    "net_cost_total": round(opt.net_cost_total, 2),
                    "net_cost_display": net_str,
                    "probability_otm": round(opt.probability_otm, 0),
                    "delta": round(opt.delta, 2),
                    "strike_distance_pct": round(opt.strike_distance_pct, 1),
                    "days_to_expiry": opt.days_to_expiry,
                })
        
        # Determine recommended option (moderate by default)
        recommended = moderate or conservative or aggressive
        if not recommended:
            itm_calc = calculate_itm_status(current_price, position.strike_price, position.option_type)
            return generate_close_recommendation(
                position=position,
                reason="No valid roll options found",
                itm_pct=itm_pct,
                intrinsic_value=itm_calc['intrinsic_value']
            )
        
        context = {
            "symbol": position.symbol,
            "scenario": "C_itm_v3_zero_cost",
            "current_strike": position.strike_price,
            "current_price": roll_analysis.current_price,
            "itm_percent": round(itm_pct, 1),
            "current_expiration": position.expiration_date.isoformat(),
            "contracts": position.contracts,
            "account": position.account_name,
            "account_name": position.account_name,  # Also include as account_name for notification organizer
            "option_type": position.option_type,
            # V3.1 FIX: Include new strike and expiration for proper notification formatting
            "new_strike": recommended.new_strike,
            "new_expiration": recommended.expiration_date.isoformat(),
            "weeks_out": recommended.expiration_weeks,
            # Cost analysis
            "buy_back_cost": round(roll_analysis.buy_back_cost, 2),
            "buy_back_total": round(roll_analysis.buy_back_total, 2),
            "max_debit_allowed": round(max_debit, 2),
            "net_cost": round(recommended.net_cost, 2),
            "net_cost_total": round(recommended.net_cost_total, 2),
            "is_credit": recommended.net_cost < 0,
            "new_premium": round(recommended.new_premium, 2),
            "probability_otm": round(recommended.probability_otm, 0),
            # Roll options
            "roll_options": roll_options_data,
            "recommended_option": "Moderate" if moderate else ("Conservative" if conservative else "Aggressive"),
            # Technical analysis
            "technical_signals": roll_analysis.technical_signals,
            "recommendation_summary": roll_analysis.recommendation_summary,
            # Earnings awareness
            "is_earnings_week": is_earnings_week,
            "earnings_date": earnings_date.isoformat() if earnings_date else None,
            # V3 info
            "v3_note": "V3: Using 20% cost rule, searching up to 52 weeks",
        }
        
        # Build title
        rec_net_str = f"${abs(recommended.net_cost):.2f} {'credit' if recommended.net_cost < 0 else 'debit'}"
        
        if is_earnings_week:
            title = (
                f"📊 EARNINGS: ROLL ITM {position.symbol} ${position.strike_price}→${recommended.new_strike:.0f} "
                f"({recommended.expiration_weeks}wk, {rec_net_str}) · Stock ${current_price:.0f}"
            )
        else:
            title = (
                f"ROLL ITM {position.symbol} ${position.strike_price}→${recommended.new_strike:.0f} "
                f"({recommended.expiration_weeks}wk, {rec_net_str}) · Stock ${current_price:.0f}"
            )
        
        # Build rationale
        itm_calc = calculate_itm_status(current_price, position.strike_price, position.option_type)
        intrinsic_value = itm_calc['intrinsic_value']
        itm_status = f"{itm_pct:.1f}% ITM (${intrinsic_value:.2f} intrinsic)"
        
        rationale_parts = [
            f"**Position**: {position.symbol} ${position.strike_price} {position.option_type} is {itm_pct:.1f}% ITM",
            f"**V3 Strategy**: Find shortest zero-cost roll (max debit ${max_debit:.2f})",
            "",
            "**Roll Options**:",
        ]
        
        for opt_data in roll_options_data:
            rationale_parts.append(
                f"• **{opt_data['label']}**: {opt_data['expiration_display']} ${opt_data['strike']:.0f} - "
                f"{opt_data['net_cost_display']}/share, {opt_data['probability_otm']:.0f}% prob OTM"
            )
        
        rationale = "\n".join(rationale_parts)
        
        # Priority - earnings week is urgent, otherwise based on ITM%
        if is_earnings_week:
            priority = "urgent"
        elif itm_pct >= 10:
            priority = "urgent"
        elif itm_pct >= 5:
            priority = "high"
        else:
            priority = "medium"
        
        # Description
        if is_earnings_week:
            description = (
                f"📊 EARNINGS on {earnings_date.strftime('%b %d') if earnings_date else 'this week'}! "
                f"{position.contracts}x {position.symbol} ${position.strike_price} {position.option_type} "
                f"{position.expiration_date.strftime('%b %d')} → "
                f"{recommended.expiration_date.strftime('%b %d')} ${recommended.new_strike:.0f} - "
                f"{rec_net_str}/share · Currently {itm_status}"
            )
        else:
            description = (
                f"{position.contracts}x {position.symbol} ${position.strike_price} {position.option_type} "
                f"{position.expiration_date.strftime('%b %d')} → "
                f"{recommended.expiration_date.strftime('%b %d')} ${recommended.new_strike:.0f} - "
                f"{rec_net_str}/share · Currently {itm_status}"
            )
        
        return StrategyRecommendation(
            id=f"roll_itm_{position.symbol}_{position.strike_price}_{date.today().isoformat()}",
            type=self.strategy_type,
            category=self.category,
            priority=priority,
            title=title,
            description=description,
            rationale=rationale,
            action=(
                f"Roll {position.contracts}x {position.symbol} ${position.strike_price} {position.option_type} "
                f"to {recommended.expiration_date.strftime('%b %d')} ${recommended.new_strike:.0f} "
                f"({rec_net_str}/share)"
            ),
            action_type="roll",
            potential_income=None if recommended.net_cost > 0 else abs(recommended.net_cost) * 100 * position.contracts,
            potential_risk="medium" if recommended.probability_otm >= 70 else "high",
            time_horizon="immediate",
            context=context,
            expires_at=datetime.combine(position.expiration_date, datetime.max.time())
        )
    
    def _handle_itm_scenario_fallback(
        self,
        position,
        indicators,
        ta_service,
        itm_pct: float,
        days_to_expiry: int,
        action: str,
        reason: str,
        analysis: Dict
    ) -> Optional[StrategyRecommendation]:
        """
        Fallback ITM handling when optimizer fails.
        
        V2 ENHANCED: Now includes:
        - Cost analysis (debit/credit calculation)
        - Scenario comparison (Roll vs Wait vs Accept Assignment)
        - 3 strike options (Conservative/Moderate/Aggressive)
        """
        weeks_out = 4 if action == "roll_3_4_weeks" else 1
        
        # Get 3 strike recommendations at different probability levels
        strike_moderate = ta_service.recommend_strike_price(
            symbol=position.symbol,
            option_type=position.option_type,
            expiration_weeks=weeks_out,
            probability_target=0.90  # Delta 10 = Moderate
        )
        
        strike_conservative = ta_service.recommend_strike_price(
            symbol=position.symbol,
            option_type=position.option_type,
            expiration_weeks=weeks_out,
            probability_target=0.95  # Delta 5 = Conservative (further OTM)
        )
        
        strike_aggressive = ta_service.recommend_strike_price(
            symbol=position.symbol,
            option_type=position.option_type,
            expiration_weeks=weeks_out,
            probability_target=0.80  # Delta 20 = Aggressive (closer to ATM)
        )
        
        # Use moderate as default, but ensure we have at least one
        strike_rec = strike_moderate or strike_conservative or strike_aggressive
        if not strike_rec:
            return None
        
        target_date = date.today() + timedelta(weeks=weeks_out)
        # Find next Friday
        while target_date.weekday() != 4:
            target_date += timedelta(days=1)
        
        # === V2 COST ANALYSIS ===
        current_price = indicators.current_price
        
        # Estimate buy-back cost (intrinsic value + time value)
        if position.option_type.lower() == "call":
            intrinsic = max(0, current_price - position.strike_price)
        else:
            intrinsic = max(0, position.strike_price - current_price)
        
        # Estimate time value based on days left and volatility
        time_value_estimate = indicators.weekly_volatility * current_price * (days_to_expiry / 7) ** 0.5 * 0.4
        buy_back_cost = intrinsic + time_value_estimate
        
        # Try to get actual market premium for new option, or estimate it
        new_premium = self._get_option_premium(
            position.symbol,
            strike_rec.recommended_strike,
            position.option_type,
            target_date
        )
        
        if new_premium is None:
            # Estimate based on volatility and time
            new_days = (target_date - date.today()).days
            new_premium = indicators.weekly_volatility * current_price * (new_days / 7) ** 0.5 * 0.5
            premium_source = "estimated"
        else:
            premium_source = "market"
        
        # Calculate net cost
        net_cost = buy_back_cost - new_premium  # Positive = debit
        net_cost_total = net_cost * 100 * position.contracts
        
        if net_cost < 0:
            net_cost_str = f"${abs(net_cost):.2f} credit"
            is_credit = True
        else:
            net_cost_str = f"${net_cost:.2f} debit"
            is_credit = False
        
        # === V2 MULTI-WEEK EXPIRATION ANALYSIS ===
        # Compare 1, 2, 3 week expirations to find optimal duration
        multi_week_analysis = []
        recommended_strike = strike_rec.recommended_strike
        
        for wk in [1, 2, 3]:
            wk_date = date.today() + timedelta(weeks=wk)
            while wk_date.weekday() != 4:  # Find Friday
                wk_date += timedelta(days=1)
            
            wk_days = (wk_date - date.today()).days
            
            # Estimate premium for this duration
            wk_premium = indicators.weekly_volatility * current_price * (wk_days / 7) ** 0.5 * 0.5
            wk_net = buy_back_cost - wk_premium
            
            # Calculate weekly return rate
            weekly_return = (wk_premium - buy_back_cost) / wk if wk > 0 else 0
            
            multi_week_analysis.append({
                "weeks": wk,
                "expiration": wk_date.isoformat(),
                "expiration_display": wk_date.strftime('%b %d'),
                "days": wk_days,
                "premium_estimate": round(wk_premium, 2),
                "net_cost": round(wk_net, 2),
                "net_display": f"${abs(wk_net):.2f} {'credit' if wk_net < 0 else 'debit'}",
                "weekly_return": round(weekly_return, 2),
                "is_recommended": wk == weeks_out,
            })
        
        # Find best weekly return (for recommendations)
        best_weekly = max(multi_week_analysis, key=lambda x: x["weekly_return"])
        
        # === V2 3 ROLL OPTIONS (Conservative/Moderate/Aggressive) ===
        roll_options = []
        new_days = (target_date - date.today()).days
        
        # Helper to estimate premium for a strike
        def estimate_premium(strike_price: float) -> float:
            if position.option_type.lower() == "call":
                otm_pct = (strike_price - current_price) / current_price
            else:
                otm_pct = (current_price - strike_price) / current_price
            # Further OTM = lower premium
            base_premium = indicators.weekly_volatility * current_price * (new_days / 7) ** 0.5 * 0.5
            otm_factor = max(0.2, 1 - otm_pct * 5)  # Reduce premium for further OTM
            return base_premium * otm_factor
        
        # Build roll options for each strike level
        for label, strike_opt, prob_otm in [
            ("Conservative", strike_conservative, 95),
            ("Moderate", strike_moderate, 90),
            ("Aggressive", strike_aggressive, 80),
        ]:
            if strike_opt:
                est_premium = estimate_premium(strike_opt.recommended_strike)
                est_net = buy_back_cost - est_premium
                if position.option_type.lower() == "call":
                    otm_pct = ((strike_opt.recommended_strike - current_price) / current_price) * 100
                else:
                    otm_pct = ((current_price - strike_opt.recommended_strike) / current_price) * 100
                
                roll_options.append({
                    "label": label,
                    "strike": strike_opt.recommended_strike,
                    "expiration": target_date.isoformat(),
                    "expiration_display": target_date.strftime('%b %d'),
                    "weeks_out": weeks_out,
                    "premium_estimate": round(est_premium, 2),
                    "net_cost": round(est_net, 2),
                    "net_cost_display": f"${abs(est_net):.2f} {'credit' if est_net < 0 else 'debit'}",
                    "probability_otm": prob_otm,
                    "otm_percent": round(otm_pct, 1),
                })
        
        # === V2 SCENARIO COMPARISON ===
        scenarios = []
        
        # Scenario 1: Roll Now (using moderate option)
        scenario_roll = {
            "action": "Roll Now",
            "description": f"Roll to ${strike_rec.recommended_strike:.0f} for {target_date.strftime('%b %d')}",
            "net_cost": net_cost,
            "net_cost_display": net_cost_str,
            "pros": "Immediate protection, no assignment risk",
            "cons": "Locks in debit" if net_cost > 0 else "Good deal - credit received",
        }
        scenarios.append(scenario_roll)
        
        # Scenario 2: Wait for Reversal (if TA suggests possible)
        if indicators.rsi_14 > 65 or analysis.get("reversal_signals"):
            scenario_wait = {
                "action": "Wait 1-2 Days",
                "description": f"RSI at {indicators.rsi_14:.0f} - stock may pull back",
                "net_cost": None,
                "net_cost_display": "Potentially better",
                "pros": f"If stock drops {itm_pct:.1f}%, position goes OTM",
                "cons": "Stock could continue rising, increasing loss",
            }
            scenarios.append(scenario_wait)
        
        # Scenario 3: Accept Assignment (for calls)
        if position.option_type.lower() == "call":
            assignment_proceeds = position.strike_price * 100 * position.contracts
            scenario_assign = {
                "action": "Accept Assignment",
                "description": f"Let shares be called away at ${position.strike_price}",
                "net_cost": 0,
                "net_cost_display": f"Receive ${assignment_proceeds:,.0f}",
                "pros": "Clean exit, collect strike price",
                "cons": f"Miss further upside above ${position.strike_price}",
            }
            scenarios.append(scenario_assign)
        
        # Build enhanced context
        context = {
            "symbol": position.symbol,
            "scenario": f"C_itm_{action}",
            "current_strike": position.strike_price,
            "new_strike": strike_rec.recommended_strike,
            "current_price": indicators.current_price,
            "itm_percent": round(itm_pct, 1),
            "current_expiration": position.expiration_date.isoformat(),
            "new_expiration": target_date.isoformat(),
            "weeks_out": weeks_out,
            "contracts": position.contracts,
            "account": position.account_name,
            "account_name": position.account_name,
            # V2 Cost Analysis
            "buy_back_cost": round(buy_back_cost, 2),
            "new_premium": round(new_premium, 2),
            "new_premium_source": premium_source,
            "net_cost": round(net_cost, 2),
            "net_cost_total": round(net_cost_total, 2),
            "is_credit": is_credit,
            # V2 Multi-Week Analysis
            "multi_week_analysis": multi_week_analysis,
            "best_weekly_return_weeks": best_weekly["weeks"],
            # V2 Roll Options (3 choices)
            "roll_options": roll_options,
            "recommended_option": "Moderate",
            # V2 Scenario Comparison
            "scenarios": scenarios,
            "recommended_scenario": "Roll Now" if net_cost < new_premium * 0.5 else "Consider Options",
            # Technical analysis
            "technical_analysis": analysis,
            "rsi": round(indicators.rsi_14, 1),
            "strike_rationale": strike_rec.rationale,
        }
        
        # Enhanced title with cost
        title = (
            f"ROLL ITM {position.symbol} ${position.strike_price}→${strike_rec.recommended_strike:.0f} "
            f"({weeks_out}wk, {net_cost_str}) · Stock ${indicators.current_price:.0f}"
        )
        
        # Enhanced description with cost analysis
        description = (
            f"Roll {position.contracts}x {position.symbol} ${position.strike_price} {position.option_type} "
            f"{position.expiration_date.strftime('%b %d')} → "
            f"{target_date.strftime('%b %d')} ${strike_rec.recommended_strike:.0f}\n\n"
            f"**Cost Analysis**: Buy back ~${buy_back_cost:.2f}, sell new ~${new_premium:.2f} = {net_cost_str}/share"
        )
        
        # Enhanced rationale with roll options and scenarios
        rationale_parts = [
            f"Position is {itm_pct:.1f}% ITM (stock ${current_price:.2f} vs ${position.strike_price} strike).",
            "",
            "**Cost Analysis**:",
            f"• Buy back current option: ~${buy_back_cost:.2f}/share",
            "",
            "**Expiration Comparison** (at ${:.0f} strike):".format(strike_rec.recommended_strike),
        ]
        
        # Add multi-week comparison
        for wk in multi_week_analysis:
            marker = "✓" if wk["is_recommended"] else " "
            rationale_parts.append(
                f"{marker} **{wk['weeks']}-week** ({wk['expiration_display']}): "
                f"~${wk['premium_estimate']:.2f} = {wk['net_display']} "
                f"(${wk['weekly_return']:.2f}/wk)"
            )
        
        rationale_parts.extend([
            "",
            "**Strike Options** (all {0}-week to {1}):".format(weeks_out, target_date.strftime('%b %d')),
        ])
        
        for opt in roll_options:
            rationale_parts.append(
                f"• **{opt['label']}**: ${opt['strike']:.0f} ({opt['otm_percent']:.1f}% OTM) - "
                f"~${opt['premium_estimate']:.2f} = {opt['net_cost_display']}, "
                f"{opt['probability_otm']}% prob OTM"
            )
        
        rationale_parts.extend([
            "",
            "**Alternative Scenarios**:",
        ])
        
        for i, s in enumerate(scenarios, 1):
            rationale_parts.append(f"{i}. **{s['action']}**: {s['description']}")
        
        rationale_parts.extend([
            "",
            f"**Technical**: RSI {indicators.rsi_14:.0f}, {indicators.trend} trend",
        ])
        
        rationale = "\n".join(rationale_parts)
        
        account_slug = (position.account_name or "unknown").replace(" ", "_").replace("'", "")
        
        return StrategyRecommendation(
            id=f"roll_itm_{position.symbol}_{position.strike_price}_{date.today().isoformat()}_{account_slug}",
            type=self.strategy_type,
            category=self.category,
            priority="urgent" if itm_pct >= 5 else "high",
            title=title,
            description=description,
            rationale=rationale,
            action=(
                f"Roll {position.contracts}x {position.symbol} from ${position.strike_price} to "
                f"${strike_rec.recommended_strike:.0f} {position.option_type} "
                f"for {target_date.strftime('%b %d')} ({net_cost_str})"
            ),
            action_type="roll",
            potential_income=abs(net_cost_total) if is_credit else None,
            potential_risk="medium" if itm_pct < 5 else "high",
            time_horizon="immediate",
            symbol=position.symbol,
            account_name=position.account_name,
            context=context,
            expires_at=datetime.combine(position.expiration_date, datetime.max.time())
        )
    
    def _get_next_friday(self) -> date:
        """Get the date of next Friday from today."""
        today = date.today()
        days_ahead = 4 - today.weekday()  # Friday = 4
        if days_ahead <= 0:
            days_ahead += 7
        return today + timedelta(days=days_ahead)
    
    def _get_friday_after(self, reference_date: date) -> date:
        """Get the date of the Friday AFTER the reference date.
        
        This is used for rolling options - we always roll to the week
        after the current expiration, not just the next Friday from today.
        """
        # Find how many days until Friday after the reference date
        days_ahead = 4 - reference_date.weekday()  # Friday = 4
        if days_ahead <= 0:
            # If reference is Friday or later in the week, go to next week's Friday
            days_ahead += 7
        return reference_date + timedelta(days=days_ahead)
    
    def _get_option_premium(
        self,
        symbol: str,
        strike: float,
        option_type: str,
        expiration: date
    ) -> Optional[float]:
        """
        Get the market price (premium) for an option.
        
        Args:
            symbol: Stock symbol
            strike: Option strike price
            option_type: 'call' or 'put'
            expiration: Option expiration date
            
        Returns:
            Mid price of the option, or None if not available
        """
        try:
            # Lazy initialization of fetcher
            if not hasattr(self, '_fetcher'):
                self._fetcher = OptionChainFetcher()
            
            chain = self._fetcher.get_option_chain(symbol, expiration)
            if not chain:
                return None
            
            key = 'calls' if option_type.lower() == 'call' else 'puts'
            options_df = chain.get(key)
            
            if options_df is None or options_df.empty:
                return None
            
            # Find the closest strike
            matching = options_df[
                (options_df['strike'] >= strike - 0.5) & 
                (options_df['strike'] <= strike + 0.5)
            ]
            
            if matching.empty:
                # Try wider range
                matching = options_df[
                    (options_df['strike'] >= strike - 2) & 
                    (options_df['strike'] <= strike + 2)
                ]
                if matching.empty:
                    return None
                # Get closest
                matching = matching.iloc[(matching['strike'] - strike).abs().argsort()[:1]]
            
            row = matching.iloc[0]
            
            # Use mid price
            bid = row.get('bid', 0) or 0
            ask = row.get('ask', 0) or 0
            
            if bid > 0 and ask > 0:
                return (bid + ask) / 2
            elif ask > 0:
                return ask * 0.9  # Discount ask if no bid
            elif bid > 0:
                return bid
            else:
                # Fall back to lastPrice
                return row.get('lastPrice', None)
                
        except Exception as e:
            logger.debug(f"Could not get option premium for {symbol} ${strike} {option_type} {expiration}: {e}")
            return None

