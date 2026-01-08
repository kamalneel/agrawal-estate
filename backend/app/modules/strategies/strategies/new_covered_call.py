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
from decimal import Decimal
import logging

from sqlalchemy import text
from app.modules.strategies.strategy_base import BaseStrategy
from app.modules.strategies.recommendations import StrategyRecommendation
from app.modules.strategies.technical_analysis import get_technical_analysis_service
from app.modules.strategies.services import get_sold_options_by_account
from app.modules.strategies.option_monitor import OptionChainFetcher
from app.modules.strategies.recommendation_models import (
    PositionRecommendation,
    RecommendationSnapshot,
    generate_recommendation_id
)

logger = logging.getLogger(__name__)

# Global option chain fetcher for real-time premiums
_option_chain_fetcher = None

def _get_option_chain_fetcher():
    """Get or create the global option chain fetcher."""
    global _option_chain_fetcher
    if _option_chain_fetcher is None:
        _option_chain_fetcher = OptionChainFetcher()
    return _option_chain_fetcher


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
            # Only count CALLS - puts don't require share backing (they're cash-secured)
            sold_count = 0
            if account_name in sold_by_account:
                by_symbol = sold_by_account[account_name].get("by_symbol", {})
                if symbol in by_symbol:
                    sold_count = sum(
                        opt["contracts_sold"] for opt in by_symbol[symbol]
                        if opt.get("option_type", "").lower() == "call"
                    )
            
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
            
            # Save to V2 model
            self._save_to_v2(
                position=position,
                action='WAIT',
                priority='low',
                reason=reason,
                context=context,
                target_strike=strike_rec.recommended_strike,
                target_expiration=next_friday,
                target_premium=None
            )
            
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
            # Try to get real premium from options chain
            option_fetcher = _get_option_chain_fetcher()
            real_premium_per_contract = None
            
            try:
                option_quote = option_fetcher.get_option_quote(
                    symbol=symbol,
                    expiration_date=next_friday,
                    strike=strike_rec.recommended_strike,
                    option_type='call'
                )
                if option_quote:
                    # Use bid price for selling (more conservative/realistic)
                    if option_quote.bid and option_quote.bid > 0:
                        real_premium_per_contract = option_quote.bid * 100
                    elif option_quote.last_price and option_quote.last_price > 0:
                        real_premium_per_contract = option_quote.last_price * 100
                    logger.debug(f"Real premium for {symbol} ${strike_rec.recommended_strike:.0f}: ${real_premium_per_contract:.2f}/contract")
            except Exception as e:
                logger.warning(f"Could not fetch real premium for {symbol}: {e}")
            
            # Fallback to estimate if real premium not available
            if real_premium_per_contract is None:
                real_premium_per_contract = indicators.current_price * 0.004 * 100  # 0.4% estimate per contract
            
            total_premium = real_premium_per_contract * position["uncovered"]
            
            # Add premium to context for frontend
            context["premium_per_contract"] = round(real_premium_per_contract, 2)
            context["total_premium"] = round(total_premium, 2)
            
            # Include premium in title and description
            title = f"SELL {position['uncovered']} {symbol} ${strike_rec.recommended_strike:.0f} call for {next_friday.strftime('%b %d')} · Stock ${indicators.current_price:.0f} and earn ${total_premium:.2f}"
            
            # Save to V2 model
            self._save_to_v2(
                position=position,
                action='SELL',
                priority='high',
                reason=reason + " " + strike_rec.rationale,
                context=context,
                target_strike=strike_rec.recommended_strike,
                target_expiration=next_friday,
                target_premium=real_premium_per_contract
            )
            
            return StrategyRecommendation(
                id=f"new_call_sell_{symbol}_{position['account_name']}_{date.today().isoformat()}",
                type=self.strategy_type,
                category=self.category,
                priority="high",
                title=title,
                description=(
                    f"Sell {position['uncovered']} {symbol} covered call(s) at ${strike_rec.recommended_strike:.0f} "
                    f"expiring {next_friday.strftime('%b %d')} in {position['account_name']} and earn ${total_premium:.2f}"
                ),
                rationale=reason + " " + strike_rec.rationale,
                action=(
                    f"Sell {position['uncovered']} {symbol} ${strike_rec.recommended_strike:.0f} call "
                    f"expiring {next_friday.strftime('%b %d')}"
                ),
                action_type="sell",
                potential_income=round(total_premium, 2),
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
    
    def _save_to_v2(
        self,
        position: Dict[str, Any],
        action: str,  # 'SELL' or 'WAIT'
        priority: str,
        reason: str,
        context: Dict[str, Any],
        target_strike: float = None,
        target_expiration: date = None,
        target_premium: float = None
    ) -> Optional[RecommendationSnapshot]:
        """
        Save recommendation to V2 model (PositionRecommendation + Snapshot).
        
        This ensures all strategies contribute to a single recommendation
        object per position, with multiple snapshots tracking evaluations.
        """
        try:
            symbol = position["symbol"]
            account_name = position["account_name"]
            
            # Generate deterministic ID for uncovered position
            rec_id = generate_recommendation_id(
                symbol=symbol,
                account_name=account_name,
                strike=None,  # Uncovered position
                expiration=None,
                option_type="call"
            )
            
            # Find or create PositionRecommendation
            existing = self.db.query(PositionRecommendation).filter(
                PositionRecommendation.recommendation_id == rec_id,
                PositionRecommendation.status == 'active'
            ).first()
            
            now = datetime.utcnow()
            
            if existing:
                recommendation = existing
                recommendation.last_snapshot_at = now
                recommendation.updated_at = now
            else:
                recommendation = PositionRecommendation(
                    recommendation_id=rec_id,
                    symbol=symbol,
                    account_name=account_name,
                    source_strike=None,  # Uncovered
                    source_expiration=None,  # Uncovered
                    option_type='call',
                    source_contracts=position.get('uncovered', 1),
                    position_type='uncovered',
                    status='active',
                    first_detected_at=now,
                    last_snapshot_at=now,
                    total_snapshots=0,
                    total_notifications_sent=0,
                    created_at=now,
                    updated_at=now
                )
                self.db.add(recommendation)
                self.db.flush()  # Get the ID
            
            # Get previous snapshot to track changes
            prev_snapshot = self.db.query(RecommendationSnapshot).filter(
                RecommendationSnapshot.recommendation_id == recommendation.id
            ).order_by(RecommendationSnapshot.snapshot_number.desc()).first()
            
            snapshot_number = (prev_snapshot.snapshot_number + 1) if prev_snapshot else 1
            
            # Detect changes from previous snapshot
            action_changed = False
            target_changed = False
            priority_changed = False
            
            if prev_snapshot:
                action_changed = prev_snapshot.recommended_action != action
                target_changed = (
                    target_strike is not None and 
                    prev_snapshot.target_strike is not None and
                    float(prev_snapshot.target_strike) != target_strike
                )
                priority_changed = prev_snapshot.priority != priority
            
            # Create snapshot
            snapshot = RecommendationSnapshot(
                recommendation_id=recommendation.id,
                snapshot_number=snapshot_number,
                evaluated_at=now,
                scan_type='scheduled',
                recommended_action=action,
                priority=priority,
                decision_state='uncovered_position',
                reason=reason,
                target_strike=Decimal(str(target_strike)) if target_strike else None,
                target_expiration=target_expiration,
                target_premium=Decimal(str(target_premium)) if target_premium else None,
                stock_price=Decimal(str(context.get('current_price', 0))),
                # Technical analysis
                rsi=Decimal(str(context.get('technical_analysis', {}).get('rsi', 0))),
                trend=context.get('technical_analysis', {}).get('trend'),
                bollinger_position=context.get('technical_analysis', {}).get('bb_position'),
                # Change tracking
                action_changed=action_changed,
                target_changed=target_changed,
                priority_changed=priority_changed,
                previous_action=prev_snapshot.recommended_action if prev_snapshot else None,
                previous_target_strike=prev_snapshot.target_strike if prev_snapshot else None,
                previous_priority=prev_snapshot.priority if prev_snapshot else None,
                # Full context
                full_context=context,
                created_at=now
            )
            
            self.db.add(snapshot)
            
            # Update recommendation stats
            recommendation.total_snapshots = snapshot_number
            recommendation.last_snapshot_at = now
            
            self.db.commit()
            
            logger.info(
                f"[V2] {symbol}@{account_name}: Snapshot #{snapshot_number} "
                f"({action}) {'⚡' if action_changed else ''}"
            )
            
            return snapshot
            
        except Exception as e:
            logger.error(f"[V2] Error saving {position.get('symbol', '?')}: {e}", exc_info=True)
            self.db.rollback()
            return None

