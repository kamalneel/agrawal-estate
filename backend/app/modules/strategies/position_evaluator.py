"""
Unified Position Evaluator for V3 Algorithm

V3.3: Comprehensive position evaluation with mean reversion awareness.

GOAL: Maintain ~30-60 day positions to capture multiple mean reversion cycles.

FRAMEWORK:
┌─────────────────────────────────────────────────────────────────┐
│  IF ITM:                                                         │
│    ├─ Near expiry (≤60 days) → ESCAPE: Roll to OTM urgently     │
│    │   (Assignment risk - must get out now)                      │
│    │                                                             │
│    └─ Far expiry (>60 days) → COMPRESS: Shorten to ~60-90 days  │
│        + get OTM (Position for next mean reversion cycle)        │
│                                                                  │
│  IF OTM:                                                         │
│    ├─ Far expiry (>8 weeks) → PULL-BACK: Return to shorter      │
│    │   (Position works, but compress to stay nimble)             │
│    │                                                             │
│    ├─ Near expiry + ≥60% profit → ROLL: Capture and repeat      │
│    │                                                             │
│    └─ Near expiry + <60% profit → HOLD: Wait for time decay     │
│                                                                  │
│  NEAR ITM (within 2%):                                           │
│    └─ Preemptive warning before assignment risk                  │
└─────────────────────────────────────────────────────────────────┘

Actions:
1. PULL_BACK: Far-dated OTM → shorter expiration (stay nimble)
2. ROLL_ITM: Near-dated ITM → escape to OTM (avoid assignment)  
3. COMPRESS: Far-dated ITM → shorter + OTM (catch mean reversion)
4. NEAR_ITM_WARNING: Within 2% of strike (preemptive alert)
5. ROLL_WEEKLY: Profitable OTM → next week (capture profits)
6. CLOSE_CATASTROPHIC: Cannot escape ITM (limit loss)
7. MONITOR: Far-dated ITM, no compress found (wait for opportunity)
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime, date, timedelta
import logging

from app.modules.strategies.pull_back_detector import check_pull_back_opportunity, PullBackResult
from app.modules.strategies.zero_cost_finder import find_zero_cost_roll, ZeroCostRollResult
from app.modules.strategies.utils.option_calculations import calculate_itm_status, is_acceptable_cost
from app.modules.strategies.recommendations import StrategyRecommendation
from app.modules.strategies.yahoo_cache import get_option_expirations

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Result of position evaluation."""
    action: str  # 'PULL_BACK', 'ROLL_ITM', 'COMPRESS', 'NEAR_ITM_WARNING', 'ROLL_WEEKLY', 'CLOSE_CATASTROPHIC', 'MONITOR'
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
    
    # V3.4: Enhanced explanation fields
    ta_summary: Optional[Dict[str, Any]] = None  # Technical Analysis snapshot
    decision_rationale: Optional[str] = None  # Plain English explanation


def build_ta_summary(
    symbol: str,
    current_price: float,
    strike_price: float,
    option_type: str,
    days_to_exp: int,
    ta_indicators: Any
) -> Dict[str, Any]:
    """
    Build a simple, readable Technical Analysis summary.
    
    Returns:
        Dict with key TA metrics in a simple format
    """
    if not ta_indicators:
        return {}
    
    # Calculate ITM/OTM status
    if option_type == 'call':
        is_itm = current_price > strike_price
        itm_pct = ((current_price - strike_price) / strike_price * 100) if is_itm else 0
        otm_pct = ((strike_price - current_price) / strike_price * 100) if not is_itm else 0
    else:  # put
        is_itm = current_price < strike_price
        itm_pct = ((strike_price - current_price) / strike_price * 100) if is_itm else 0
        otm_pct = ((current_price - strike_price) / strike_price * 100) if not is_itm else 0
    
    # Calculate Bollinger Band position (0% = lower, 100% = upper)
    bb_range = ta_indicators.bb_upper - ta_indicators.bb_lower
    bb_position_pct = ((current_price - ta_indicators.bb_lower) / bb_range * 100) if bb_range > 0 else 50
    
    # Determine BB position description
    if bb_position_pct < 25:
        bb_position_desc = "near lower support"
    elif bb_position_pct < 40:
        bb_position_desc = "lower half"
    elif bb_position_pct > 75:
        bb_position_desc = "near upper resistance"
    elif bb_position_pct > 60:
        bb_position_desc = "upper half"
    else:
        bb_position_desc = "middle"
    
    # RSI interpretation
    rsi = ta_indicators.rsi_14
    if rsi < 30:
        rsi_desc = "oversold"
    elif rsi < 40:
        rsi_desc = "near oversold"
    elif rsi > 70:
        rsi_desc = "overbought"
    elif rsi > 60:
        rsi_desc = "near overbought"
    else:
        rsi_desc = "neutral"
    
    return {
        'current_price': round(current_price, 2),
        'strike_price': round(strike_price, 2),
        'option_type': option_type.upper(),
        'is_itm': is_itm,
        'itm_pct': round(itm_pct, 1) if is_itm else None,
        'otm_pct': round(otm_pct, 1) if not is_itm else None,
        'days_to_expiry': days_to_exp,
        'bollinger': {
            'upper': round(ta_indicators.bb_upper, 2),
            'middle': round(ta_indicators.bb_middle, 2),
            'lower': round(ta_indicators.bb_lower, 2),
            'position_pct': round(bb_position_pct, 0),
            'position_desc': bb_position_desc,
        },
        'rsi': {
            'value': round(rsi, 1),
            'status': rsi_desc,
        },
        'support': round(ta_indicators.nearest_support, 2) if ta_indicators.nearest_support else None,
        'resistance': round(ta_indicators.nearest_resistance, 2) if ta_indicators.nearest_resistance else None,
        'ma_50': round(ta_indicators.ma_50, 2) if ta_indicators.ma_50 else None,
        'ma_200': round(ta_indicators.ma_200, 2) if ta_indicators.ma_200 else None,
    }


def build_decision_rationale(
    symbol: str,
    action: str,
    ta_summary: Dict[str, Any],
    option_type: str,
    strike_price: float,
    expiration_date: date,
    new_strike: Optional[float] = None,
    new_expiration: Optional[date] = None,
    net_cost: Optional[float] = None,
) -> str:
    """
    Build a plain English explanation of the decision.
    
    Returns:
        A paragraph explaining WHY this recommendation was made.
    """
    current_price = ta_summary.get('current_price', 0)
    days_to_exp = ta_summary.get('days_to_expiry', 0)
    bb = ta_summary.get('bollinger', {})
    rsi_data = ta_summary.get('rsi', {})
    is_itm = ta_summary.get('is_itm', False)
    itm_pct = ta_summary.get('itm_pct', 0)
    
    # Build the situation description
    situation = f"Your {symbol} ${strike_price:.0f} {option_type.upper()} is "
    if is_itm:
        situation += f"currently {itm_pct:.1f}% in-the-money "
    else:
        situation += f"currently {ta_summary.get('otm_pct', 0):.1f}% out-of-the-money "
    situation += f"with {days_to_exp} days until expiration on {expiration_date.strftime('%b %d')}."
    
    # Build TA context
    bb_pos = bb.get('position_pct', 50)
    bb_desc = bb.get('position_desc', 'middle')
    rsi_val = rsi_data.get('value', 50)
    rsi_status = rsi_data.get('status', 'neutral')
    
    ta_context = f"\n\n{symbol} is trading at ${current_price:.2f}, which is at the {bb_desc} of its Bollinger Band ({bb_pos:.0f}% position). "
    ta_context += f"RSI is at {rsi_val:.0f} ({rsi_status}). "
    
    if ta_summary.get('support'):
        ta_context += f"Nearest support is ${ta_summary['support']:.2f}. "
    if ta_summary.get('resistance'):
        ta_context += f"Nearest resistance is ${ta_summary['resistance']:.2f}."
    
    # Build action-specific rationale
    if action == 'MONITOR':
        if option_type == 'put' and bb_pos < 40:
            rationale = (
                f"\n\nThe stock is near its lower Bollinger Band, which historically acts as support. "
                f"Mean reversion suggests the stock is likely to bounce back toward the middle band (~${bb.get('middle', 0):.2f}) "
                f"in the coming days. If it bounces, your PUT would become less in-the-money or even go out-of-the-money."
            )
            recommendation = (
                f"\n\nRECOMMENDATION: MONITOR for now. You still have {days_to_exp} days. "
                f"Wait 2-3 days to see if the stock bounces from support. "
                f"If it doesn't recover by {(expiration_date - timedelta(days=3)).strftime('%b %d')}, then consider rolling."
            )
        elif option_type == 'call' and bb_pos > 60:
            rationale = (
                f"\n\nThe stock is near its upper Bollinger Band, which historically acts as resistance. "
                f"Mean reversion suggests the stock is likely to pull back toward the middle band (~${bb.get('middle', 0):.2f}) "
                f"in the coming days. If it pulls back, your CALL would become less in-the-money or even go out-of-the-money."
            )
            recommendation = (
                f"\n\nRECOMMENDATION: MONITOR for now. You still have {days_to_exp} days. "
                f"Wait 2-3 days to see if the stock pulls back from resistance. "
                f"If it doesn't correct by {(expiration_date - timedelta(days=3)).strftime('%b %d')}, then consider rolling."
            )
        else:
            rationale = f"\n\nTechnical indicators suggest waiting before taking action."
            recommendation = f"\n\nRECOMMENDATION: MONITOR and reassess in a few days."
    
    elif action in ['ROLL_ITM', 'COMPRESS']:
        if new_strike and new_expiration:
            weeks_out = (new_expiration - date.today()).days // 7
            cost_str = f"${abs(net_cost):.2f} {'credit' if net_cost < 0 else 'debit'}" if net_cost else "cost-neutral"
            
            rationale = (
                f"\n\nThe position needs to be rolled to avoid potential assignment. "
                f"Rolling to ${new_strike:.0f} on {new_expiration.strftime('%b %d')} ({weeks_out} weeks out) "
                f"would move the position out-of-the-money at a {cost_str}."
            )
            recommendation = (
                f"\n\nRECOMMENDATION: Roll to ${new_strike:.0f} {new_expiration.strftime('%b %d')}. "
                f"This is the shortest expiration where an acceptable roll exists."
            )
        else:
            rationale = "\n\nThe position needs to be rolled to manage risk."
            recommendation = "\n\nRECOMMENDATION: Consider rolling to a further expiration."
    
    elif action == 'PULL_BACK':
        if new_strike and new_expiration:
            weeks_saved = (expiration_date - new_expiration).days // 7
            cost_str = f"${abs(net_cost):.2f} {'credit' if net_cost < 0 else 'debit'}" if net_cost else "cost-neutral"
            
            rationale = (
                f"\n\nYou can compress this position to a shorter duration and capture profits. "
                f"The current position has captured enough profit to roll back by {weeks_saved} week(s)."
            )
            recommendation = (
                f"\n\nRECOMMENDATION: Pull back to ${new_strike:.0f} {new_expiration.strftime('%b %d')} for a {cost_str}. "
                f"This preserves your weekly income cycle."
            )
        else:
            rationale = "\n\nYou can compress this position to capture profits."
            recommendation = "\n\nRECOMMENDATION: Consider pulling back to a shorter expiration."
    
    elif action == 'CLOSE_CATASTROPHIC':
        rationale = (
            f"\n\nThis position is deeply in-the-money and no acceptable roll was found within 6 months. "
            f"The position may result in significant loss if held to expiration."
        )
        recommendation = (
            f"\n\nRECOMMENDATION: Consider closing this position to limit further loss. "
            f"Sometimes taking a small loss now prevents a larger loss later."
        )
    
    else:
        rationale = ""
        recommendation = ""
    
    return situation + ta_context + rationale + recommendation


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
    
    def _enrich_with_ta(
        self, 
        result: Optional[EvaluationResult], 
        position, 
        indicators: Any, 
        days_to_exp: int
    ) -> Optional[EvaluationResult]:
        """
        Enrich an EvaluationResult with TA summary and decision rationale.
        
        This ensures ALL recommendations have TA context for the frontend.
        """
        if result is None or indicators is None:
            return result
        
        # Skip if already has TA data
        if result.ta_summary and result.decision_rationale:
            return result
        
        try:
            # Build TA summary
            ta_summary = build_ta_summary(
                symbol=position.symbol,
                current_price=indicators.current_price,
                strike_price=position.strike_price,
                option_type=position.option_type,
                days_to_exp=days_to_exp,
                ta_indicators=indicators
            )
            
            # Build decision rationale
            decision_rationale = build_decision_rationale(
                symbol=position.symbol,
                action=result.action,
                ta_summary=ta_summary,
                option_type=position.option_type,
                strike_price=position.strike_price,
                expiration_date=position.expiration_date,
            )
            
            # Update the result with TA data
            result.ta_summary = ta_summary
            result.decision_rationale = decision_rationale
            
        except Exception as e:
            logger.warning(f"Could not enrich {position.symbol} with TA: {e}")
        
        return result
    
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
        # Store for TA enrichment at end
        _indicators = None
        _days_to_exp = 0
        
        try:
            # Get current price and calculate ITM status
            indicators = self.ta_service.get_technical_indicators(position.symbol)
            if not indicators:
                logger.warning(f"Cannot get indicators for {position.symbol}")
                return None
            
            _indicators = indicators  # Store for enrichment
            
            current_price = indicators.current_price
            itm_calc = calculate_itm_status(
                current_price, position.strike_price, position.option_type
            )
            is_itm = itm_calc['is_itm']
            itm_pct = itm_calc['itm_pct']
            
            # Calculate weeks to expiration
            today = date.today()
            days_to_exp = (position.expiration_date - today).days
            _days_to_exp = days_to_exp  # Store for enrichment
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
                    result = self._generate_pullback_result(position, pull_back)
                    return self._enrich_with_ta(result, position, _indicators, _days_to_exp)
            
            # ================================================================
            # STATE 1.5: Weekly Income Priority (V3.3)
            # For SLIGHTLY ITM + PROFITABLE positions, prefer COMPRESS over EXTEND
            # This preserves the weekly income cycle
            #
            # Example: AVGO $350 Put Jan 23, Stock $346 (1.1% ITM), 79% profit
            #   → Don't extend to Jan 30 (loses weekly cycle)
            #   → COMPRESS to Jan 16 at $355 (preserves weekly cycle)
            # ================================================================
            WEEKLY_INCOME_MAX_ITM_PCT = 5.0  # Only for slightly ITM
            WEEKLY_INCOME_MIN_PROFIT_PCT = 0.60  # Only if profitable
            
            if is_itm and itm_pct <= WEEKLY_INCOME_MAX_ITM_PCT and profit_pct >= WEEKLY_INCOME_MIN_PROFIT_PCT:
                logger.info(
                    f"{position.symbol}: Slightly ITM ({itm_pct:.1f}%) + profitable ({profit_pct:.0%}) - "
                    f"checking weekly income compress first"
                )
                
                # Try to compress to shorter duration (even staying ITM)
                weekly_compress = self._handle_weekly_income_compress(
                    position, current_price, current_premium,
                    original_premium, itm_pct, days_to_exp, profit_pct
                )
                if weekly_compress:
                    return self._enrich_with_ta(weekly_compress, position, _indicators, _days_to_exp)
                
                # If no compress found, fall through to normal ITM handling
                logger.info(f"{position.symbol}: No weekly income compress found, trying normal ITM escape")
            
            # ================================================================
            # STATE 1.6: TA-based MONITOR for slightly ITM (V3.4)
            # For slightly ITM positions with time remaining, check if mean
            # reversion is likely before escaping.
            #
            # Logic:
            # - PUT ITM: Stock dropped below strike. If at SUPPORT (lower BB,
            #   low RSI), stock will likely bounce UP → PUT becomes less ITM
            # - CALL ITM: Stock rose above strike. If at RESISTANCE (upper BB,
            #   high RSI), stock will likely pull back → CALL becomes less ITM
            #
            # Example: AVGO $355 Put, Stock $333 (6% ITM), 8 days to expiry
            #   Stock is at 29% of Bollinger Band (near lower support)
            #   → Don't panic-roll to March (loses 10 weeks income)
            #   → MONITOR - wait for bounce from support
            # ================================================================
            TA_MONITOR_MAX_ITM_PCT = 8.0  # Apply to slightly ITM positions
            TA_MONITOR_MIN_DAYS = 5  # Need at least 5 days for mean reversion
            
            if is_itm and itm_pct <= TA_MONITOR_MAX_ITM_PCT and days_to_exp >= TA_MONITOR_MIN_DAYS:
                # Get full TA indicators
                ta_indicators = self.ta_service.get_technical_indicators(position.symbol)
                
                if ta_indicators:
                    # Calculate position in Bollinger Band (0% = lower, 100% = upper)
                    bb_range = ta_indicators.bb_upper - ta_indicators.bb_lower
                    if bb_range > 0:
                        bb_position_pct = ((current_price - ta_indicators.bb_lower) / bb_range) * 100
                    else:
                        bb_position_pct = 50  # Default to middle if no range
                    
                    rsi = ta_indicators.rsi_14
                    
                    # Determine if mean reversion is likely
                    should_monitor = False
                    monitor_reason = ""
                    
                    if position.option_type == 'put':
                        # PUT ITM: Stock dropped. Monitor if at support (will bounce UP)
                        at_support = bb_position_pct < 35 or rsi < 40
                        if at_support:
                            should_monitor = True
                            monitor_reason = (
                                f"Stock at support (BB position {bb_position_pct:.0f}%, RSI {rsi:.0f}). "
                                f"Mean reversion likely - wait for bounce before rolling."
                            )
                    else:  # call
                        # CALL ITM: Stock spiked. Monitor if at resistance (will pull back)
                        at_resistance = bb_position_pct > 65 or rsi > 60
                        if at_resistance:
                            should_monitor = True
                            monitor_reason = (
                                f"Stock at resistance (BB position {bb_position_pct:.0f}%, RSI {rsi:.0f}). "
                                f"Mean reversion likely - wait for pullback before rolling."
                            )
                    
                    if should_monitor:
                        logger.info(
                            f"{position.symbol}: TA-based MONITOR - {itm_pct:.1f}% ITM, "
                            f"{days_to_exp} days left, BB={bb_position_pct:.0f}%, RSI={rsi:.0f}"
                        )
                        
                        # Build TA summary and decision rationale
                        ta_summary = build_ta_summary(
                            symbol=position.symbol,
                            current_price=current_price,
                            strike_price=position.strike_price,
                            option_type=position.option_type,
                            days_to_exp=days_to_exp,
                            ta_indicators=ta_indicators
                        )
                        
                        decision_rationale = build_decision_rationale(
                            symbol=position.symbol,
                            action='MONITOR',
                            ta_summary=ta_summary,
                            option_type=position.option_type,
                            strike_price=position.strike_price,
                            expiration_date=position.expiration_date,
                        )
                        
                        return EvaluationResult(
                            action='MONITOR',
                            position_id=self._get_position_id(position),
                            symbol=position.symbol,
                            priority='low',
                            reason=monitor_reason,
                            details={
                                'itm_pct': itm_pct,
                                'days_to_exp': days_to_exp,
                                'current_price': current_price,
                                'strike': position.strike_price,
                                'bb_position_pct': bb_position_pct,
                                'rsi': rsi,
                                'bb_lower': ta_indicators.bb_lower,
                                'bb_upper': ta_indicators.bb_upper,
                                'nearest_support': ta_indicators.nearest_support,
                                'nearest_resistance': ta_indicators.nearest_resistance,
                                'strategy': 'ta_monitor_mean_reversion',
                            },
                            ta_summary=ta_summary,
                            decision_rationale=decision_rationale,
                        )
                    else:
                        logger.info(
                            f"{position.symbol}: TA does NOT support waiting - "
                            f"BB={bb_position_pct:.0f}%, RSI={rsi:.0f}, proceeding with ITM escape"
                        )
            
            # ================================================================
            # STATE 2: In the money (escape/compress strategy)
            # 
            # V3.3 Logic:
            # - Near expiry (≤60 days): ESCAPE - urgent, roll to OTM at any time
            # - Far expiry (>60 days): COMPRESS - shorten to ~60-90 days + OTM
            #   This positions us to capture mean reversion in 1-2 months
            #   
            # Example: TSLA $370 Sept (8 months out, ITM)
            #   → Don't just WAIT - try to COMPRESS to March at OTM
            #   → If can roll Sept $370 → March $440 at acceptable cost, do it
            #   → This lets us catch the next mean reversion cycle
            # ================================================================
            if is_itm:
                ITM_COMPRESS_THRESHOLD_DAYS = 60  # 2 months
                
                if days_to_exp > ITM_COMPRESS_THRESHOLD_DAYS:
                    # Far-dated ITM: Try to COMPRESS time while getting OTM
                    compress_result = self._handle_itm_compress(
                        position, current_price, current_premium,
                        original_premium, itm_pct, days_to_exp
                    )
                    if compress_result:
                        return self._enrich_with_ta(compress_result, position, _indicators, _days_to_exp)
                    
                    # No compress opportunity found - just monitor
                    logger.info(
                        f"{position.symbol}: ITM ({itm_pct:.1f}%), {days_to_exp} days out - "
                        f"no compress opportunity, monitoring for pullback"
                    )
                    monitor_result = EvaluationResult(
                        action='MONITOR',
                        position_id=self._get_position_id(position),
                        symbol=position.symbol,
                        priority='low',
                        reason=(
                            f'{itm_pct:.1f}% ITM, {days_to_exp} days to expiry. '
                            f'No cost-neutral compress found. Monitoring for pullback.'
                        ),
                        details={
                            'itm_pct': itm_pct,
                            'days_to_exp': days_to_exp,
                            'current_price': current_price,
                            'strike': position.strike_price,
                            'strategy': 'monitor_for_compress',
                        },
                    )
                    return self._enrich_with_ta(monitor_result, position, _indicators, _days_to_exp)
                
                # ITM with near expiration (<60 days): ESCAPE NOW
                result = self._handle_itm_position(
                    position, current_price, current_premium, 
                    original_premium, itm_pct
                )
                return self._enrich_with_ta(result, position, _indicators, _days_to_exp)
            
            # ================================================================
            # STATE 2.5: Near ITM - approaching strike (preemptive alert)
            # Alert when position is within 2% of strike to avoid assignment
            # This fills the gap between OTM and ITM
            # ================================================================
            otm_pct = itm_calc.get('otm_pct', 0)
            near_itm_threshold = 2.0  # Alert when within 2% of strike
            urgent_near_itm_threshold = 1.0  # Urgent when within 1% of strike
            
            if not is_itm and otm_pct <= near_itm_threshold and days_to_exp <= 7:
                # Position is dangerously close to strike and expiring soon
                result = self._handle_near_itm_position(
                    position, current_price, current_premium, 
                    original_premium, otm_pct, days_to_exp, urgent_near_itm_threshold
                )
                return self._enrich_with_ta(result, position, _indicators, _days_to_exp)
            
            # ================================================================
            # STATE 3: OTM and profitable (standard weekly roll)
            # Roll at 60% profit capture
            # ================================================================
            if profit_pct >= 0.60 and not is_itm:
                result = self._handle_profitable_position(
                    position, current_price, profit_pct
                )
                return self._enrich_with_ta(result, position, _indicators, _days_to_exp)
            
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
        ITM Escape Strategy: Find shortest time to get back OTM.
        
        V3.2 Logic (Mean Reversion):
        - Goal: Escape to OTM as quickly as possible
        - Bet: Stocks that spike up often pull back in 1-2 months
        - Find nearest expiration where we can roll to an OTM strike
        - Accept reasonable debit to escape (not strict 20% rule)
        
        Cost tolerance scales with urgency:
        - Slightly ITM (1-5%): max $2 debit - not urgent, stock may naturally recover
        - Moderately ITM (5-10%): max $3 debit - need to act soon
        - Deeply ITM (>10%): max $5 debit - urgent, accept higher cost to escape
        """
        # ITM escape: use absolute max debit based on urgency, not 20% rule
        # This reflects the true goal: get OTM quickly, accept reasonable cost
        if itm_pct >= 10:
            max_debit_for_escape = 5.0  # Urgent - accept up to $5 debit
            priority = 'urgent'
        elif itm_pct >= 5:
            max_debit_for_escape = 3.0  # Moderate - accept up to $3 debit  
            priority = 'high'
        else:
            max_debit_for_escape = 2.0  # Slight - accept up to $2 debit
            priority = 'medium'
        
        # Use the higher of: 20% rule OR absolute escape limit
        # This ensures we don't reject a good roll just because original premium was low
        effective_max_debit = max(original_premium * 0.20, max_debit_for_escape)
        
        logger.info(
            f"ITM Escape: {position.symbol} {itm_pct:.1f}% ITM, "
            f"max_debit=${effective_max_debit:.2f} (escape_limit=${max_debit_for_escape}, 20%_rule=${original_premium * 0.20:.2f})"
        )
        
        # Find shortest time to get OTM (searches all OTM strikes, not just Delta 30)
        zero_cost_roll = find_zero_cost_roll(
            symbol=position.symbol,
            current_strike=position.strike_price,
            option_type=position.option_type,
            current_expiration=position.expiration_date,
            current_price=current_price,
            buy_back_cost=current_premium,
            original_premium=effective_max_debit / 0.20,  # Effective premium for 20% rule calculation
            contracts=position.contracts,
            max_months=6,  # Mean reversion bet: 6 months should be enough for pullback
            delta_target=0.70,  # Fallback if chain search fails
            ta_service=self.ta_service,
            option_fetcher=self.option_fetcher
        )
        
        if zero_cost_roll:
            # Found escape route to OTM
            return EvaluationResult(
                action='ROLL_ITM',
                position_id=self._get_position_id(position),
                symbol=position.symbol,
                priority=priority,
                reason=(
                    f'{itm_pct:.1f}% ITM - roll to ${zero_cost_roll.strike:.0f} ({zero_cost_roll.weeks_out}wk) '
                    f'to get OTM. Mean reversion bet: stock may pull back.'
                ),
                details={
                    'itm_pct': itm_pct,
                    'current_price': current_price,
                    'current_premium': current_premium,
                    'original_premium': original_premium,
                    'escape_strategy': 'mean_reversion',
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
            # Cannot escape within 6 months - this is truly catastrophic
            return EvaluationResult(
                action='CLOSE_CATASTROPHIC',
                position_id=self._get_position_id(position),
                symbol=position.symbol,
                priority='urgent',
                reason=(
                    f'Cannot escape to OTM within 6 months even with ${effective_max_debit:.2f} debit. '
                    f'Position {itm_pct:.1f}% ITM. Consider closing to limit loss.'
                ),
                details={
                    'itm_pct': itm_pct,
                    'current_price': current_price,
                    'max_debit_tried': effective_max_debit,
                    'max_months_searched': 6,
                }
            )
    
    def _handle_weekly_income_compress(
        self,
        position,
        current_price: float,
        current_premium: float,
        original_premium: float,
        itm_pct: float,
        days_to_exp: int,
        profit_pct: float
    ) -> Optional[EvaluationResult]:
        """
        Weekly Income Compress for slightly ITM + profitable positions.
        
        V3.3 Logic:
        - Position is slightly ITM (<5%) AND profitable (>60%)
        - Goal: COMPRESS to shorter duration to preserve weekly income cycle
        - Accept staying ITM or moving to higher strike (closer to ATM)
        - Accept credit or small debit (≤$1)
        
        Example: AVGO $350 Put Jan 23, Stock $346 (1.1% ITM), 79% profit
        - Don't extend to Jan 30 (loses weekly cycle)
        - COMPRESS to Jan 16 at $355 (preserves weekly cycle, earns credit)
        
        Returns:
            EvaluationResult with COMPRESS action, or None if no opportunity
        """
        MAX_DEBIT_FOR_WEEKLY_COMPRESS = 1.0  # Very tight - prioritize credits
        
        logger.info(
            f"Weekly Income Compress: {position.symbol} {itm_pct:.1f}% ITM, {profit_pct:.0%} profit, "
            f"{days_to_exp} days to exp - looking for shorter duration"
        )
        
        # Get available expirations
        available_exps = get_option_expirations(position.symbol)
        if not available_exps:
            logger.debug(f"No expirations available for {position.symbol}")
            return None
        
        today = date.today()
        best_compress = None
        
        # Search for compress opportunity - SHORTER than current
        for exp_str in available_exps:
            try:
                exp_date = date.fromisoformat(exp_str)
            except:
                continue
            
            exp_days = (exp_date - today).days
            
            # Only consider SHORTER expirations (this is key!)
            if exp_days >= days_to_exp:
                continue  # Must be shorter than current
            if exp_days < 2:
                continue  # Don't compress to expiring tomorrow
            
            # Get option chain for this expiration
            chain_data = self.option_fetcher.get_option_chain(position.symbol, exp_date)
            if not chain_data:
                continue
            
            # Get the appropriate side (calls or puts)
            side_key = 'calls' if position.option_type == 'call' else 'puts'
            chain_df = chain_data.get(side_key)
            if chain_df is None or (hasattr(chain_df, 'empty') and chain_df.empty):
                continue
            
            # Convert DataFrame to list of dicts if needed
            if hasattr(chain_df, 'to_dict'):
                chain = chain_df.to_dict('records')
            else:
                chain = chain_df if isinstance(chain_df, list) else []
            
            # For weekly income compress, we accept:
            # 1. Same strike (staying ITM)
            # 2. Higher strike for calls / Lower strike for puts (closer to ATM or OTM)
            # The goal is to find a CREDIT or small debit
            
            candidates = []
            for opt in chain:
                strike = opt.get('strike', 0)
                bid = opt.get('bid', 0)
                
                if bid <= 0:
                    continue
                
                # Accept same strike or closer to ATM
                if position.option_type == 'call':
                    # For calls: accept same or higher strike
                    if strike < position.strike_price:
                        continue
                else:
                    # For puts: accept same or lower strike (closer to ATM)
                    if strike > position.strike_price:
                        continue
                
                net_cost = current_premium - bid
                
                # Accept if credit or small debit
                if net_cost <= MAX_DEBIT_FOR_WEEKLY_COMPRESS:
                    candidates.append({
                        'strike': strike,
                        'bid': bid,
                        'net_cost': net_cost,
                        'exp_date': exp_date,
                        'exp_days': exp_days,
                        'is_credit': net_cost < 0
                    })
            
            # Sort candidates: prefer credits, then smaller debits
            candidates.sort(key=lambda x: x['net_cost'])
            
            if candidates:
                best_for_exp = candidates[0]
                # Prefer the SHORTEST expiration with acceptable cost
                if best_compress is None or best_for_exp['exp_days'] < best_compress['exp_days']:
                    best_compress = best_for_exp
        
        if best_compress:
            # Found weekly income compress opportunity
            cost_str = f"${abs(best_compress['net_cost']):.2f} " + \
                      ("credit" if best_compress['is_credit'] else "debit")
            weeks_out = best_compress['exp_days'] // 7
            days_saved = days_to_exp - best_compress['exp_days']
            
            logger.info(
                f"Weekly Income Compress found: {position.symbol} → ${best_compress['strike']:.0f} "
                f"@ {best_compress['exp_date']} ({weeks_out}wk), {cost_str}, saves {days_saved} days"
            )
            
            return EvaluationResult(
                action='COMPRESS',
                position_id=self._get_position_id(position),
                symbol=position.symbol,
                priority='medium',
                reason=(
                    f'{profit_pct:.0%} profit captured, {itm_pct:.1f}% ITM. '
                    f'Compress to ${best_compress["strike"]:.0f} @ {best_compress["exp_date"]} '
                    f'for {cost_str}. Preserves weekly income cycle.'
                ),
                details={
                    'itm_pct': itm_pct,
                    'profit_pct': profit_pct,
                    'current_days_to_exp': days_to_exp,
                    'new_days_to_exp': best_compress['exp_days'],
                    'days_saved': days_saved,
                    'current_price': current_price,
                    'current_premium': current_premium,
                    'strategy': 'weekly_income_compress',
                },
                new_strike=best_compress['strike'],
                new_expiration=best_compress['exp_date'],
                net_cost=best_compress['net_cost'],
                zero_cost_data={
                    'weeks_out': weeks_out,
                    'new_premium': best_compress['bid'],
                    'probability_otm': 50.0,  # Approximate for ITM
                    'is_credit': best_compress['is_credit'],
                }
            )
        
        return None  # No weekly income compress found
    
    def _handle_itm_compress(
        self,
        position,
        current_price: float,
        current_premium: float,
        original_premium: float,
        itm_pct: float,
        days_to_exp: int
    ) -> Optional[EvaluationResult]:
        """
        COMPRESS Strategy for far-dated ITM positions.
        
        V3.3 Logic:
        - Position is ITM but expiration is far out (>60 days)
        - Goal: Shorten time to ~60-90 days to catch mean reversion
        - Two approaches:
          1. Same-strike compress: Roll to shorter expiration at SAME strike (cost-neutral)
          2. OTM escape compress: Roll to shorter AND get OTM (accept small debit)
        
        Example: TSLA $370 Sept (8 months out, 17% ITM)
        - Approach 1: Roll Sept $370 → March $370 if cost-neutral
        - Approach 2: Roll Sept $370 → March $440 if ≤$5 debit
        
        Returns:
            EvaluationResult with COMPRESS action, or None if no opportunity
        """
        # Target expiration: 45-90 days out (optimal for mean reversion cycle)
        TARGET_MIN_DAYS = 45   # At least 6 weeks
        TARGET_MAX_DAYS = 90   # At most 3 months
        
        # Cost tolerance:
        # - Same strike compress: must be cost-neutral (≤$1 debit) 
        # - OTM escape compress: accept higher debit based on ITM severity
        SAME_STRIKE_MAX_DEBIT = 1.0  # Very tight for same strike
        if itm_pct >= 10:
            otm_escape_max_debit = 5.0
        elif itm_pct >= 5:
            otm_escape_max_debit = 3.0
        else:
            otm_escape_max_debit = 2.0
        
        logger.info(
            f"ITM Compress: {position.symbol} {itm_pct:.1f}% ITM, {days_to_exp} days to exp, "
            f"looking for compress to {TARGET_MIN_DAYS}-{TARGET_MAX_DAYS} days"
        )
        
        # Get available expirations
        available_exps = get_option_expirations(position.symbol)
        if not available_exps:
            logger.debug(f"No expirations available for {position.symbol}")
            return None
        
        today = date.today()
        best_same_strike = None  # Priority 1: Same strike compress (cost-neutral)
        best_otm_escape = None   # Priority 2: OTM escape compress (accept debit)
        
        # Search for compress opportunity in target window
        for exp_str in available_exps:
            try:
                exp_date = date.fromisoformat(exp_str)
            except:
                continue
            
            exp_days = (exp_date - today).days
            
            # Only consider expirations in target window AND shorter than current
            if not (TARGET_MIN_DAYS <= exp_days <= TARGET_MAX_DAYS):
                continue
            if exp_days >= days_to_exp:
                continue  # Must be shorter than current
            
            # Get option chain for this expiration
            chain_data = self.option_fetcher.get_option_chain(position.symbol, exp_date)
            if not chain_data:
                continue
            
            # Get the appropriate side (calls or puts)
            side_key = 'calls' if position.option_type == 'call' else 'puts'
            chain_df = chain_data.get(side_key)
            if chain_df is None or (hasattr(chain_df, 'empty') and chain_df.empty):
                continue
            
            # Convert DataFrame to list of dicts if needed
            if hasattr(chain_df, 'to_dict'):
                chain = chain_df.to_dict('records')
            else:
                chain = chain_df if isinstance(chain_df, list) else []
            
            # ============================================================
            # APPROACH 1: Same-strike compress (cost-neutral)
            # Goal: Shorten time while staying at same strike
            # Only accept if cost is nearly zero (≤$1 debit)
            # ============================================================
            same_strike_opt = next(
                (opt for opt in chain if abs(opt.get('strike', 0) - position.strike_price) < 0.01),
                None
            )
            if same_strike_opt:
                new_premium = same_strike_opt.get('bid', 0)
                if new_premium > 0:
                    net_cost = current_premium - new_premium
                    if net_cost <= SAME_STRIKE_MAX_DEBIT:
                        weeks_out = exp_days // 7
                        days_saved = days_to_exp - exp_days
                        
                        if best_same_strike is None or exp_days < best_same_strike['exp_days']:
                            best_same_strike = {
                                'exp_date': exp_date,
                                'exp_days': exp_days,
                                'new_strike': position.strike_price,
                                'new_premium': new_premium,
                                'net_cost': net_cost,
                                'weeks_out': weeks_out,
                                'days_saved': days_saved,
                                'otm_pct': -itm_pct,  # Still ITM
                                'is_credit': net_cost < 0,
                                'compress_type': 'same_strike'
                            }
            
            # ============================================================
            # APPROACH 2: OTM escape compress (accept debit)
            # Goal: Shorten time AND escape to OTM
            # Accept higher debit for this double benefit
            # ============================================================
            otm_options = [
                opt for opt in chain
                if (position.option_type == 'call' and opt.get('strike', 0) > current_price) or
                   (position.option_type == 'put' and opt.get('strike', 0) < current_price)
            ]
            
            if otm_options:
                # Sort by strike - want closest OTM (highest premium but still OTM)
                if position.option_type == 'call':
                    otm_options.sort(key=lambda x: x.get('strike', 0))  # Lowest OTM first
                else:
                    otm_options.sort(key=lambda x: x.get('strike', 0), reverse=True)
                
                # Check each OTM strike for acceptable cost
                for opt in otm_options:
                    new_strike = opt.get('strike', 0)
                    new_premium = opt.get('bid', 0)
                    
                    if new_premium <= 0:
                        continue
                    
                    # Net cost = buy back current - sell new
                    net_cost = current_premium - new_premium
                    
                    if net_cost <= otm_escape_max_debit:
                        weeks_out = exp_days // 7
                        days_saved = days_to_exp - exp_days
                        
                        # Calculate OTM percentage at new strike
                        if position.option_type == 'call':
                            otm_pct = ((new_strike - current_price) / current_price) * 100
                        else:
                            otm_pct = ((current_price - new_strike) / current_price) * 100
                        
                        if best_otm_escape is None or exp_days < best_otm_escape['exp_days']:
                            best_otm_escape = {
                                'exp_date': exp_date,
                                'exp_days': exp_days,
                                'new_strike': new_strike,
                                'new_premium': new_premium,
                                'net_cost': net_cost,
                                'weeks_out': weeks_out,
                                'days_saved': days_saved,
                                'otm_pct': otm_pct,
                                'is_credit': net_cost < 0,
                                'compress_type': 'otm_escape'
                            }
                        break  # Found acceptable for this expiration
        
        # Prefer same-strike compress over OTM escape (cost-neutral is better)
        best_compress = best_same_strike or best_otm_escape
        
        if best_compress:
            # Found compress opportunity
            cost_str = f"${abs(best_compress['net_cost']):.2f} " + \
                      ("credit" if best_compress['is_credit'] else "debit")
            
            compress_type = best_compress.get('compress_type', 'unknown')
            type_desc = "same strike" if compress_type == 'same_strike' else "OTM escape"
            
            logger.info(
                f"ITM Compress found ({type_desc}): {position.symbol} → ${best_compress['new_strike']:.0f} "
                f"@ {best_compress['exp_date']} ({best_compress['weeks_out']}wk), {cost_str}"
            )
            
            # Build reason based on compress type
            if compress_type == 'same_strike':
                reason = (
                    f'{itm_pct:.1f}% ITM with {days_to_exp} days left. '
                    f'Compress to {best_compress["exp_date"]} (same ${best_compress["new_strike"]:.0f} strike) '
                    f'for {cost_str}. Saves {best_compress["days_saved"]} days to catch mean reversion.'
                )
            else:
                reason = (
                    f'{itm_pct:.1f}% ITM with {days_to_exp} days left. '
                    f'Compress + escape to ${best_compress["new_strike"]:.0f} @ {best_compress["exp_date"]} '
                    f'({best_compress["weeks_out"]}wk) for {cost_str}. '
                    f'Saves {best_compress["days_saved"]} days AND gets OTM.'
                )
            
            return EvaluationResult(
                action='COMPRESS',
                position_id=self._get_position_id(position),
                symbol=position.symbol,
                priority='medium',
                reason=reason,
                details={
                    'itm_pct': itm_pct,
                    'current_days_to_exp': days_to_exp,
                    'new_days_to_exp': best_compress['exp_days'],
                    'days_saved': best_compress['days_saved'],
                    'current_price': current_price,
                    'current_premium': current_premium,
                    'strategy': 'compress_for_mean_reversion',
                    'target_otm_pct': best_compress['otm_pct'],
                },
                new_strike=best_compress['new_strike'],
                new_expiration=best_compress['exp_date'],
                net_cost=best_compress['net_cost'],
                zero_cost_data={
                    'weeks_out': best_compress['weeks_out'],
                    'new_premium': best_compress['new_premium'],
                    'probability_otm': 100 - (30 if best_compress['otm_pct'] < 5 else 20),  # Rough estimate
                    'is_credit': best_compress['is_credit'],
                }
            )
        
        return None  # No compress opportunity found
    
    def _handle_near_itm_position(
        self,
        position,
        current_price: float,
        current_premium: float,
        original_premium: float,
        otm_pct: float,
        days_to_exp: int,
        urgent_threshold: float
    ) -> EvaluationResult:
        """
        Handle positions that are dangerously close to ITM.
        
        Alert user to consider rolling before assignment risk increases.
        This fills the gap between fully OTM and ITM - preventing situations
        where a position goes ITM and user wasn't warned.
        """
        is_urgent = otm_pct <= urgent_threshold
        priority = 'high' if is_urgent else 'medium'
        
        # Calculate distance to strike
        strike = position.strike_price
        distance = abs(strike - current_price)
        
        # Get a recommended roll target
        strike_rec = self.ta_service.recommend_strike_price(
            symbol=position.symbol,
            option_type=position.option_type,
            expiration_weeks=2,  # Suggest 2 weeks out for near-ITM
            probability_target=0.85  # Delta 15 - safer than weekly
        )
        
        new_strike = strike_rec.recommended_strike if strike_rec else strike + (strike * 0.03)
        
        # Get next Friday + 1 week (2 weeks out)
        today = date.today()
        days_to_friday = (4 - today.weekday()) % 7
        if days_to_friday == 0:
            days_to_friday = 7
        new_expiration = today + timedelta(days=days_to_friday + 7)  # 2 weeks out
        
        reason_prefix = "⚠️ URGENT: " if is_urgent else "⚠️ WARNING: "
        
        return EvaluationResult(
            action='NEAR_ITM_WARNING',
            position_id=self._get_position_id(position),
            symbol=position.symbol,
            priority=priority,
            reason=(
                f'{reason_prefix}Position only {otm_pct:.1f}% OTM (${distance:.2f} from strike). '
                f'Expires in {days_to_exp} days. Consider rolling to avoid assignment risk.'
            ),
            details={
                'otm_pct': otm_pct,
                'distance_to_strike': distance,
                'current_price': current_price,
                'strike_price': strike,
                'days_to_expiry': days_to_exp,
                'current_premium': current_premium,
                'original_premium': original_premium,
                'risk_level': 'urgent' if is_urgent else 'elevated',
            },
            new_strike=new_strike,
            new_expiration=new_expiration
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

        # Get next Friday that is AFTER the current expiration
        today = date.today()
        days_to_friday = (4 - today.weekday()) % 7
        if days_to_friday == 0:
            days_to_friday = 7  # Next Friday if today is Friday
        new_expiration = today + timedelta(days=days_to_friday)

        # If the new expiration is the same as or before the current expiration,
        # skip to the following Friday (can't roll to same/earlier date)
        current_expiration = position.expiration_date if hasattr(position, 'expiration_date') else position.expiration
        if current_expiration and new_expiration <= current_expiration:
            new_expiration = new_expiration + timedelta(days=7)

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


# Module-level singleton for SmartScanFilter (persists across requests)
_scan_filter_instance: Optional[SmartScanFilter] = None


def get_position_evaluator(ta_service=None, option_fetcher=None) -> PositionEvaluator:
    """Factory function to get a PositionEvaluator instance."""
    return PositionEvaluator(ta_service, option_fetcher)


def get_scan_filter() -> SmartScanFilter:
    """
    Factory function to get the singleton SmartScanFilter instance.
    Persists across requests to prevent duplicate notifications within same day.
    """
    global _scan_filter_instance
    if _scan_filter_instance is None:
        _scan_filter_instance = SmartScanFilter()
    return _scan_filter_instance

