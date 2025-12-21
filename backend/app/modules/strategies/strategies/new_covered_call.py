"""
New Covered Call Opportunity Strategy

V3.0 - Simplified: Technical analysis based wait/sell decision only.

When shares are uncovered (just closed an option for profit), determine
whether to sell a new call immediately or wait.

The stock dropped (that's why the option was profitable), so:
- If CORRECTING (was overbought, moving to middle): Safe to sell now
- If BOUNCING (oversold, at support): Wait for bounce before selling

V3 CHANGES:
- Removed timing optimization (Friday → Monday, VIX, FOMC predictions)
- Only use real price-based technical analysis (RSI, support levels)
- Simple: Check TA → Wait or Sell
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
import logging

from sqlalchemy import text
from app.modules.strategies.strategy_base import BaseStrategy
from app.modules.strategies.recommendations import StrategyRecommendation
from app.modules.strategies.technical_analysis import get_technical_analysis_service
from app.modules.strategies.services import get_sold_options_by_account

logger = logging.getLogger(__name__)


class NewCoveredCallStrategy(BaseStrategy):
    """
    Strategy for selling new covered calls on uncovered shares.
    
    V3.0 - Simplified: Only uses technical analysis, no timing predictions.
    
    Uses technical analysis to determine:
    - SELL NOW: Stock correcting from overbought (safe to sell)
    - WAIT: Stock oversold/at support (will likely bounce)
    """
    
    strategy_type = "new_covered_call"
    name = "New Call"
    description = "Identifies when to sell new covered calls with TA guidance"
    category = "income_generation"
    default_parameters = {
        "min_contracts_uncovered": 1,  # Minimum uncovered contracts to alert
        "expiration_weeks": 1,  # Default weeks until expiration
    }
    
    def generate_recommendations(self, params: Dict[str, Any]) -> List[StrategyRecommendation]:
        """Generate new covered call recommendations."""
        recommendations = []
        
        ta_service = get_technical_analysis_service()
        
        # Get all holdings with enough shares for options (100+ shares)
        result = self.db.execute(text("""
            SELECT 
                ia.account_name,
                ih.symbol,
                ih.quantity,
                ih.current_price,
                ih.market_value,
                ih.description
            FROM investment_holdings ih
            JOIN investment_accounts ia ON ih.account_id = ia.account_id AND ih.source = ia.source
            WHERE ih.quantity >= 100
            AND ih.symbol NOT LIKE '%CASH%'
            AND ih.symbol NOT LIKE '%MONEY%'
            AND ih.symbol NOT LIKE '%FDRXX%'
            AND ia.account_type IN ('brokerage', 'retirement', 'ira', 'roth_ira')
            ORDER BY ih.market_value DESC
        """))
        
        # Get currently sold options
        sold_by_account = get_sold_options_by_account(self.db)
        
        # Find uncovered positions
        uncovered_positions = []
        
        for row in result:
            account_name, symbol, qty, price, value, description = row
            qty = float(qty) if qty else 0
            options_count = int(qty // 100)
            
            # Count sold contracts for this symbol in this account
            sold_count = 0
            if account_name in sold_by_account:
                by_symbol = sold_by_account[account_name].get("by_symbol", {})
                if symbol in by_symbol:
                    sold_count = sum(opt["contracts_sold"] for opt in by_symbol[symbol])
            
            uncovered = options_count - sold_count
            
            if uncovered >= self.get_parameter("min_contracts_uncovered", 1):
                uncovered_positions.append({
                    "account_name": account_name,
                    "symbol": symbol,
                    "quantity": qty,
                    "options_count": options_count,
                    "sold_count": sold_count,
                    "uncovered": uncovered,
                    "current_price": float(price) if price else 0,
                    "market_value": float(value) if value else 0,
                })
        
        # Analyze each uncovered position
        for position in uncovered_positions:
            try:
                rec = self._analyze_uncovered_position(position, ta_service)
                if rec:
                    recommendations.append(rec)
            except Exception as e:
                logger.error(f"Error analyzing {position['symbol']}: {e}")
                continue
        
        return recommendations
    
    def _analyze_uncovered_position(
        self,
        position: Dict[str, Any],
        ta_service
    ) -> Optional[StrategyRecommendation]:
        """
        Analyze whether to sell a call on uncovered shares.
        
        V3: Only uses technical analysis - no timing predictions.
        """
        symbol = position["symbol"]
        
        # V3: Only check technical analysis for wait/sell decision
        should_wait, reason, analysis = ta_service.should_wait_to_sell(symbol)
        
        # Get full indicators for context
        indicators = ta_service.get_technical_indicators(symbol)
        
        if not indicators:
            return None
        
        # Get strike recommendation
        strike_rec = ta_service.recommend_strike_price(
            symbol=symbol,
            option_type="call",
            expiration_weeks=self.get_parameter("expiration_weeks", 1),
            probability_target=0.90
        )
        
        if not strike_rec:
            return None
        
        next_friday = self._get_next_friday()
        
        context = {
            "symbol": symbol,
            "account": position["account_name"],
            "unsold_contracts": position["uncovered"],
            "total_options_possible": position["options_count"],
            "currently_sold": position["sold_count"],
            "current_price": indicators.current_price,
            "recommended_strike": strike_rec.recommended_strike,
            "expiration_date": next_friday.isoformat(),
            "should_wait": should_wait,
            "wait_reason": reason,
            # Technical analysis for UI popup
            "technical_analysis": {
                "rsi": round(indicators.rsi_14, 1),
                "rsi_status": indicators.rsi_status,
                "bb_position": indicators.bb_position,
                "bb_upper": round(indicators.bb_upper, 2),
                "bb_middle": round(indicators.bb_middle, 2),
                "bb_lower": round(indicators.bb_lower, 2),
                "trend": indicators.trend,
                "nearest_support": indicators.nearest_support,
                "nearest_resistance": indicators.nearest_resistance,
                "weekly_volatility": round(indicators.weekly_volatility * 100, 2),
                "prob_90_high": indicators.prob_90_high,
            },
            "strike_rationale": strike_rec.rationale,
        }
        
        if should_wait:
            # WAIT recommendation
            title = f"WAIT {symbol} - {position['uncovered']} unsold, likely bounce · Stock ${indicators.current_price:.0f}"
            
            return StrategyRecommendation(
                id=f"new_call_wait_{symbol}_{position['account_name']}_{date.today().isoformat()}",
                type=self.strategy_type,
                category=self.category,
                priority="low",
                title=title,
                description=(
                    f"{symbol} has {position['uncovered']} unsold contract(s) in {position['account_name']}. "
                    f"Wait before selling - stock likely to bounce."
                ),
                rationale=reason,
                action="Monitor and wait for bounce before selling covered call",
                action_type="monitor",
                potential_income=None,
                potential_risk="low",
                time_horizon="this_week",
                symbol=symbol,
                account_name=position['account_name'],
                context=context,
                expires_at=datetime.now() + timedelta(days=2)  # Re-check in 2 days
            )
        else:
            # SELL NOW recommendation
            # Estimate premium (rough: 0.3-0.5% of stock price for weekly OTM)
            estimated_premium = indicators.current_price * 0.004 * position["uncovered"] * 100
            
            title = f"SELL {position['uncovered']} {symbol} ${strike_rec.recommended_strike:.0f} call for {next_friday.strftime('%b %d')} · Stock ${indicators.current_price:.0f}"
            
            return StrategyRecommendation(
                id=f"new_call_sell_{symbol}_{position['account_name']}_{date.today().isoformat()}",
                type=self.strategy_type,
                category=self.category,
                priority="high",
                title=title,
                description=(
                    f"Sell {position['uncovered']} {symbol} covered call(s) at ${strike_rec.recommended_strike:.0f} "
                    f"expiring {next_friday.strftime('%b %d')} in {position['account_name']}"
                ),
                rationale=reason + " " + strike_rec.rationale,
                action=(
                    f"Sell {position['uncovered']} {symbol} ${strike_rec.recommended_strike:.0f} call "
                    f"expiring {next_friday.strftime('%b %d')}"
                ),
                action_type="sell",
                potential_income=round(estimated_premium, 2),
                potential_risk="low",
                time_horizon="this_week",
                symbol=symbol,
                account_name=position['account_name'],
                context=context,
                expires_at=datetime.combine(next_friday, datetime.max.time())
            )
    
    def _get_next_friday(self) -> date:
        """Get the date of next Friday."""
        today = date.today()
        days_ahead = 4 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return today + timedelta(days=days_ahead)

