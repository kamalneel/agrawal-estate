"""
Close Early Opportunity Strategy

Identifies options that should be closed early due to:
1. Already captured 70-80%+ profit
2. Volatility risk before expiration (earnings, technical indicators)

Notification is ONLY sent when both conditions are met - this is a 
"CLOSE NOW" action recommendation.
"""

from typing import List, Dict, Any
from datetime import datetime, date, timedelta
import logging

from app.modules.strategies.strategy_base import BaseStrategy, StrategyConfig
from app.modules.strategies.recommendations import StrategyRecommendation
from app.modules.strategies.option_monitor import get_positions_from_db, OptionRollMonitor
from app.modules.strategies.technical_analysis import get_technical_analysis_service

logger = logging.getLogger(__name__)


class CloseEarlyOpportunityStrategy(BaseStrategy):
    """
    Strategy for identifying options that should be closed early.
    
    Trigger: Option at 70-80%+ profit AND volatility risk detected.
    
    Volatility risk factors:
    - Earnings before expiration
    - RSI extremes (>70 or <30)
    - Bollinger Band squeeze
    - High ATR/volatility
    - Near key support/resistance
    """
    
    strategy_type = "close_early_opportunity"
    name = "Take Profit"
    description = "Alert when options should be closed early due to profit + volatility risk"
    category = "risk_management"
    default_parameters = {
        "min_profit_percent": 70,  # Minimum profit captured to consider
        "min_risk_score": 30,  # Minimum volatility risk score to trigger
    }
    
    def generate_recommendations(self, params: Dict[str, Any]) -> List[StrategyRecommendation]:
        """Generate close early recommendations."""
        recommendations = []
        
        min_profit = self.get_parameter("min_profit_percent", 70) / 100.0
        
        # Get open positions from database
        positions = get_positions_from_db(self.db)
        
        if not positions:
            logger.info("No open positions for close early analysis")
            return recommendations
        
        # Check each position
        monitor = OptionRollMonitor(profit_threshold=min_profit)
        ta_service = get_technical_analysis_service()
        
        for position in positions:
            try:
                # First check if profit threshold is met
                alert = monitor.check_position(position)
                
                if not alert:
                    continue
                
                # Position has met profit threshold
                # Now check volatility risk
                risk = ta_service.assess_volatility_risk(
                    symbol=position.symbol,
                    expiration_date=position.expiration_date,
                    profit_captured_pct=alert.profit_percent * 100
                )
                
                if not risk.should_close_early:
                    continue
                
                # Both conditions met - generate recommendation
                indicators = ta_service.get_technical_indicators(position.symbol)
                
                # Build detailed context for UI popup
                context = {
                    "symbol": position.symbol,
                    "strike_price": position.strike_price,
                    "option_type": position.option_type,
                    "expiration_date": position.expiration_date.isoformat(),
                    "days_to_expiry": alert.days_to_expiry,
                    "contracts": position.contracts,
                    "original_premium": position.original_premium,
                    "current_premium": alert.current_premium,
                    "profit_amount": alert.profit_amount,
                    "profit_percent": round(alert.profit_percent * 100, 1),
                    "account": position.account_name,
                    # Risk assessment
                    "risk_level": risk.risk_level,
                    "risk_factors": risk.risk_factors,
                    # Technical analysis for UI popup
                    "technical_analysis": {}
                }
                
                if indicators:
                    context["technical_analysis"] = {
                        "current_price": indicators.current_price,
                        "rsi": round(indicators.rsi_14, 1),
                        "rsi_status": indicators.rsi_status,
                        "bollinger_position": indicators.bb_position,
                        "bb_upper": round(indicators.bb_upper, 2),
                        "bb_lower": round(indicators.bb_lower, 2),
                        "weekly_volatility": round(indicators.weekly_volatility * 100, 2),
                        "earnings_date": indicators.earnings_date.isoformat() if indicators.earnings_date else None,
                        "earnings_within_week": indicators.earnings_within_week,
                        "nearest_resistance": indicators.nearest_resistance,
                        "nearest_support": indicators.nearest_support,
                    }
                
                # Single clear title with ALL key info: contracts, symbol, strike, current price, profit %
                profit_pct = int(alert.profit_percent * 100)
                current_stock_price = indicators.current_price if indicators else None
                
                # Title: Everything you need to take action
                title = (
                    f"Close {position.contracts} {position.symbol} ${position.strike_price} "
                    f"{position.option_type}{'s' if position.contracts > 1 else ''} at ${alert.current_premium:.2f} - "
                    f"{profit_pct}% profit"
                )
                
                # Description: The reasoning (why close now) - stock price + risk factor
                if current_stock_price and risk.risk_factors:
                    description = f"{position.symbol} at ${current_stock_price:.2f}. {risk.risk_factors[0]}"
                elif risk.risk_factors:
                    description = risk.risk_factors[0]
                else:
                    description = f"{profit_pct}% of premium captured"
                
                # Rationale for the Analysis section (more detail)
                rationale = f"You've captured {profit_pct}% of the premium. " + (risk.risk_factors[0] if risk.risk_factors else "")
                
                # Action: The exact trade command
                action = f"Buy to close {position.contracts} {position.symbol} ${position.strike_price} {position.option_type} at ${alert.current_premium:.2f}"
                
                # Include account in ID to make unique per account
                account_slug = (position.account_name or "unknown").replace(" ", "_").replace("'", "")
                recommendation = StrategyRecommendation(
                    id=f"close_early_{position.symbol}_{position.strike_price}_{date.today().isoformat()}_{account_slug}",
                    type=self.strategy_type,
                    category=self.category,
                    priority="urgent" if len(risk.risk_factors) >= 2 else "high",
                    title=title,
                    description=description,
                    rationale=rationale,
                    action=action,
                    action_type="close",
                    potential_income=alert.profit_amount * position.contracts * 100,
                    potential_risk="low",
                    time_horizon="immediate",
                    symbol=position.symbol,
                    account_name=position.account_name,
                    context=context,
                    expires_at=datetime.combine(position.expiration_date, datetime.max.time())
                )
                
                recommendations.append(recommendation)
                logger.info(f"Close early recommendation: {position.symbol} ${position.strike_price} - {len(risk.risk_factors)} risk factors")
                
            except Exception as e:
                logger.error(f"Error analyzing {position.symbol} for close early: {e}")
                continue
        
        return recommendations

