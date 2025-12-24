"""
Unified Position Evaluator for V3 Algorithm

V3.0: Single source of truth for position evaluation.
Consolidates all strategy logic into one clear flow with 3 states.

This replaces the 10 separate strategy files from V2 with a unified approach:
1. One evaluation per position
2. Priority-based routing
3. Clear decision tree
4. No conflicting recommendations

States:
1. PULL_BACK: Far-dated position can return to shorter expiration
2. ROLL_ITM: In the money, need to escape
3. ROLL_WEEKLY: Profitable, roll to next week
4. NO_ACTION: Hold current position
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime, date, timedelta
import logging

from app.modules.strategies.pull_back_detector import check_pull_back_opportunity, PullBackResult
from app.modules.strategies.zero_cost_finder import find_zero_cost_roll, ZeroCostRollResult
from app.modules.strategies.utils.option_calculations import calculate_itm_status, is_acceptable_cost
from app.modules.strategies.recommendations import StrategyRecommendation

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Result of position evaluation."""
    action: str  # 'PULL_BACK', 'ROLL_ITM', 'ROLL_WEEKLY', 'CLOSE_CATASTROPHIC', 'NO_ACTION'
    position_id: str
    symbol: str
    priority: str  # 'urgent', 'high', 'medium', 'low'
    reason: str
    details: Dict[str, Any]
    
    # For roll actions
    new_strike: Optional[float] = None
    new_expiration: Optional[date] = None
    net_cost: Optional[float] = None
    
    # For pull-back
    pull_back_data: Optional[Dict[str, Any]] = None
    
    # For ITM rolls
    zero_cost_data: Optional[Dict[str, Any]] = None


class SmartScanFilter:
    """
    Prevent duplicate notifications within same day.
    
    Tracks what recommendations have been sent and only alerts on NEW or CHANGED.
    Resets automatically at midnight.
    """
    
    def __init__(self):
        self.sent_today: Dict[str, int] = {}
        self.last_reset = datetime.now().date()
    
    def should_send(self, position_id: str, recommendation: Dict[str, Any]) -> bool:
        """
        Return True if this is new/changed recommendation.
        
        Args:
            position_id: Unique position identifier
            recommendation: Recommendation dict or EvaluationResult
        
        Returns:
            True if should send notification, False if duplicate
        """
        # Auto-reset at midnight
        self._check_daily_reset()
        
        # Hash key fields to detect changes
        rec_hash = self._hash_recommendation(recommendation)
        
        if position_id not in self.sent_today:
            # First time seeing this position today
            self.sent_today[position_id] = rec_hash
            return True
        
        if self.sent_today[position_id] != rec_hash:
            # Recommendation changed
            self.sent_today[position_id] = rec_hash
            return True
        
        # Already sent this exact recommendation today
        return False
    
    def _hash_recommendation(self, rec) -> int:
        """
        Hash key fields to detect changes.
        """
        if isinstance(rec, EvaluationResult):
            return hash((
                rec.action,
                rec.new_strike,
                str(rec.new_expiration) if rec.new_expiration else None,
                rec.priority
            ))
        elif isinstance(rec, dict):
            return hash((
                rec.get('action'),
                rec.get('new_strike'),
                str(rec.get('new_expiration')) if rec.get('new_expiration') else None,
                rec.get('priority'),
            ))
        else:
            return hash(str(rec))
    
    def _check_daily_reset(self):
        """Reset filter at midnight."""
        today = datetime.now().date()
        if today > self.last_reset:
            self.sent_today = {}
            self.last_reset = today
    
    def reset_daily(self):
        """Manual reset (called at midnight by scheduler)."""
        self.sent_today = {}
        self.last_reset = datetime.now().date()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get filter statistics."""
        return {
            'positions_tracked': len(self.sent_today),
            'last_reset': self.last_reset.isoformat(),
        }


class PositionEvaluator:
    """
    Single evaluator with priority-based routing.
    
    V3 Core Philosophy:
    - ONE recommendation per position per scan
    - Priority-based: Pull-back > ITM > Profitable > No Action
    - Simple 3-state decision tree
    - Clear, predictable behavior
    """
    
    def __init__(self, ta_service=None, option_fetcher=None):
        """
        Initialize evaluator.
        
        Args:
            ta_service: TechnicalAnalysisService instance
            option_fetcher: OptionChainFetcher instance
        """
        if ta_service is None:
            from app.modules.strategies.technical_analysis import get_technical_analysis_service
            ta_service = get_technical_analysis_service()
        
        if option_fetcher is None:
            from app.modules.strategies.option_monitor import OptionChainFetcher
            option_fetcher = OptionChainFetcher()
        
        self.ta_service = ta_service
        self.option_fetcher = option_fetcher
    
    def evaluate(self, position) -> Optional[EvaluationResult]:
        """
        Main evaluation logic - returns ONE recommendation per position.
        
        Priority order (first match wins):
        1. Pull-back opportunity (far-dated → shorter)
        2. ITM escape (find zero-cost roll)
        3. Profitable weekly roll (60%+ profit)
        4. No action
        
        Args:
            position: Position object with required attributes
        
        Returns:
            EvaluationResult, or None if no action needed
        """
        try:
            # Get current price and calculate ITM status
            indicators = self.ta_service.get_technical_indicators(position.symbol)
            if not indicators:
                logger.warning(f"Cannot get indicators for {position.symbol}")
                return None
            
            current_price = indicators.current_price
            itm_calc = calculate_itm_status(
                current_price, position.strike_price, position.option_type
            )
            is_itm = itm_calc['is_itm']
            itm_pct = itm_calc['itm_pct']
            
            # Calculate weeks to expiration
            today = date.today()
            days_to_exp = (position.expiration_date - today).days
            weeks_to_exp = max(1, days_to_exp // 7)
            
            # Calculate profit percentage
            original_premium = getattr(position, 'original_premium', 1.0)
            current_premium = getattr(position, 'current_premium', None)
            if current_premium is None:
                # Estimate current premium
                current_premium = self._estimate_current_premium(position, indicators)
            
            profit_pct = (original_premium - current_premium) / original_premium if original_premium > 0 else 0
            
            # ================================================================
            # STATE 1: Pull-back opportunity (highest priority)
            # If far-dated and can return to shorter duration, do it
            # ================================================================
            if weeks_to_exp > 1:
                pull_back = check_pull_back_opportunity(
                    symbol=position.symbol,
                    current_expiration=position.expiration_date,
                    current_strike=position.strike_price,
                    option_type=position.option_type,
                    current_premium=current_premium,
                    original_premium=original_premium,
                    contracts=position.contracts,
                    ta_service=self.ta_service,
                    option_fetcher=self.option_fetcher
                )
                
                if pull_back:
                    return self._generate_pullback_result(position, pull_back)
            
            # ================================================================
            # STATE 2: In the money (escape strategy)
            # Find zero-cost roll to any duration ≤12 months
            # ================================================================
            if is_itm:
                return self._handle_itm_position(
                    position, current_price, current_premium, 
                    original_premium, itm_pct
                )
            
            # ================================================================
            # STATE 3: OTM and profitable (standard weekly roll)
            # Roll at 60% profit capture
            # ================================================================
            if profit_pct >= 0.60 and not is_itm:
                return self._handle_profitable_position(
                    position, current_price, profit_pct
                )
            
            # ================================================================
            # STATE 4: No action needed
            # ================================================================
            return None
            
        except Exception as e:
            logger.error(f"Error evaluating {position.symbol}: {e}", exc_info=True)
            return None
    
    def _handle_itm_position(
        self, 
        position, 
        current_price: float,
        current_premium: float,
        original_premium: float,
        itm_pct: float
    ) -> EvaluationResult:
        """
        Find shortest zero-cost roll using Delta 30.
        Only close if cannot escape within 12 months.
        """
        max_debit = original_premium * 0.20
        
        # Use Delta 30 for ITM rolls (per V3 Addendum)
        zero_cost_roll = find_zero_cost_roll(
            symbol=position.symbol,
            current_strike=position.strike_price,
            option_type=position.option_type,
            current_expiration=position.expiration_date,
            current_price=current_price,
            buy_back_cost=current_premium,
            original_premium=original_premium,
            contracts=position.contracts,
            max_months=12,
            delta_target=0.70,  # Delta 30 per V3 Addendum
            ta_service=self.ta_service,
            option_fetcher=self.option_fetcher
        )
        
        if zero_cost_roll:
            # Found escape route
            priority = 'urgent' if itm_pct >= 10 else ('high' if itm_pct >= 5 else 'medium')
            
            return EvaluationResult(
                action='ROLL_ITM',
                position_id=self._get_position_id(position),
                symbol=position.symbol,
                priority=priority,
                reason=(
                    f'{itm_pct:.1f}% ITM - rolling to {zero_cost_roll.weeks_out} weeks '
                    f'at ${zero_cost_roll.strike:.2f} strike'
                ),
                details={
                    'itm_pct': itm_pct,
                    'current_price': current_price,
                    'current_premium': current_premium,
                    'original_premium': original_premium,
                },
                new_strike=zero_cost_roll.strike,
                new_expiration=zero_cost_roll.expiration_date,
                net_cost=zero_cost_roll.net_cost,
                zero_cost_data={
                    'weeks_out': zero_cost_roll.weeks_out,
                    'new_premium': zero_cost_roll.new_premium,
                    'probability_otm': zero_cost_roll.probability_otm,
                    'is_credit': zero_cost_roll.is_credit,
                }
            )
        else:
            # CATASTROPHIC: Cannot escape within 12 months
            return EvaluationResult(
                action='CLOSE_CATASTROPHIC',
                position_id=self._get_position_id(position),
                symbol=position.symbol,
                priority='urgent',
                reason=(
                    f'Cannot find zero-cost roll within 12 months. '
                    f'Position {itm_pct:.1f}% ITM. Close position and accept loss.'
                ),
                details={
                    'itm_pct': itm_pct,
                    'current_price': current_price,
                    'max_debit_tried': max_debit,
                    'max_months_searched': 12,
                }
            )
    
    def _handle_profitable_position(
        self, 
        position, 
        current_price: float,
        profit_pct: float
    ) -> EvaluationResult:
        """
        Roll weekly at 60% profit using Delta 10.
        Standard income generation strategy.
        """
        # Use Delta 10 for weekly rolls (NOT Delta 30)
        strike_rec = self.ta_service.recommend_strike_price(
            symbol=position.symbol,
            option_type=position.option_type,
            expiration_weeks=1,
            probability_target=0.90  # Delta 10
        )
        
        if not strike_rec:
            logger.warning(f"Cannot get strike for weekly roll: {position.symbol}")
            return None
        
        new_strike = strike_rec.recommended_strike
        
        # Get next Friday
        today = date.today()
        days_to_friday = (4 - today.weekday()) % 7
        if days_to_friday == 0:
            days_to_friday = 7  # Next Friday if today is Friday
        new_expiration = today + timedelta(days=days_to_friday)
        
        return EvaluationResult(
            action='ROLL_WEEKLY',
            position_id=self._get_position_id(position),
            symbol=position.symbol,
            priority='medium',
            reason=f'{profit_pct*100:.0f}% profit captured - roll to next week',
            details={
                'profit_pct': profit_pct,
                'current_price': current_price,
            },
            new_strike=new_strike,
            new_expiration=new_expiration
        )
    
    def _generate_pullback_result(
        self, 
        position, 
        pull_back: PullBackResult
    ) -> EvaluationResult:
        """Generate pull-back recommendation."""
        return EvaluationResult(
            action='PULL_BACK',
            position_id=self._get_position_id(position),
            symbol=position.symbol,
            priority='high',
            reason=(
                f'Can pull back from {pull_back.from_weeks} weeks '
                f'to {pull_back.to_weeks} weeks. {pull_back.benefit}'
            ),
            details={
                'weeks_saved': pull_back.weeks_saved,
                'current_value': pull_back.current_value,
            },
            new_strike=pull_back.new_strike,
            new_expiration=pull_back.to_expiration,
            net_cost=pull_back.net_cost,
            pull_back_data={
                'from_weeks': pull_back.from_weeks,
                'to_weeks': pull_back.to_weeks,
                'from_expiration': pull_back.from_expiration.isoformat(),
                'to_expiration': pull_back.to_expiration.isoformat(),
                'new_premium': pull_back.new_premium,
            }
        )
    
    def _estimate_current_premium(self, position, indicators) -> float:
        """Estimate current option premium if not available."""
        try:
            # Try to get from option chain
            chain = self.option_fetcher.get_option_chain(
                position.symbol, position.expiration_date
            )
            if chain:
                key = 'calls' if position.option_type.lower() == 'call' else 'puts'
                options_df = chain.get(key)
                if options_df is not None and not options_df.empty:
                    matching = options_df[
                        (options_df['strike'] >= position.strike_price - 0.5) &
                        (options_df['strike'] <= position.strike_price + 0.5)
                    ]
                    if not matching.empty:
                        row = matching.iloc[0]
                        bid = row.get('bid', 0) or 0
                        ask = row.get('ask', 0) or 0
                        if bid > 0 and ask > 0:
                            return (bid + ask) / 2
                        elif ask > 0:
                            return ask
        except Exception as e:
            logger.debug(f"Could not get option price: {e}")
        
        # Fallback: estimate based on intrinsic + time value
        itm_calc = calculate_itm_status(
            indicators.current_price, position.strike_price, position.option_type
        )
        intrinsic = itm_calc['intrinsic_value']
        
        days_left = (position.expiration_date - date.today()).days
        time_value = indicators.weekly_volatility * indicators.current_price * (max(days_left, 1) / 7) ** 0.5 * 0.4
        
        return intrinsic + time_value
    
    def _get_position_id(self, position) -> str:
        """Generate unique position identifier."""
        return f"{position.symbol}_{position.strike_price}_{position.expiration_date.isoformat()}"


def get_position_evaluator(ta_service=None, option_fetcher=None) -> PositionEvaluator:
    """Factory function to get a PositionEvaluator instance."""
    return PositionEvaluator(ta_service, option_fetcher)


def get_scan_filter() -> SmartScanFilter:
    """Factory function to get a SmartScanFilter instance."""
    return SmartScanFilter()

