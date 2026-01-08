"""
Recommendation Service (V2 Architecture)

Handles the lifecycle of recommendations and snapshots:
1. Creating/finding recommendations based on position identity
2. Creating snapshots at each evaluation
3. Detecting changes between snapshots
4. Deciding whether to send notifications
5. Resolving recommendations when user acts or position expires

This is the main interface for the recommendation system.
"""

from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from decimal import Decimal
import logging

from app.modules.strategies.recommendation_models import (
    PositionRecommendation,
    RecommendationSnapshot,
    RecommendationExecution,
    generate_recommendation_id
)
from app.modules.strategies.position_evaluator import EvaluationResult

logger = logging.getLogger(__name__)


class RecommendationService:
    """
    Service for managing recommendations and snapshots.
    
    This is the primary interface for:
    - Recording algorithm evaluations as snapshots
    - Tracking recommendation lifecycle
    - Deciding when to notify
    - Linking executions to recommendations
    """
    
    # Notification cooldown (hours) for unchanged recommendations
    NOTIFICATION_COOLDOWN_HOURS = 4
    
    # Priority escalation always triggers notification
    PRIORITY_ORDER = {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}
    
    def __init__(self, db: Session):
        self.db = db
    
    def record_evaluation(
        self,
        evaluation: EvaluationResult,
        position: Any,
        scan_type: str = None,
        market_conditions: Dict[str, Any] = None,
        ta_indicators: Dict[str, Any] = None,
        full_context: Dict[str, Any] = None
    ) -> Tuple[PositionRecommendation, RecommendationSnapshot, bool]:
        """
        Record an algorithm evaluation as a snapshot.
        
        This is the main entry point called after the position evaluator runs.
        
        Args:
            evaluation: Result from PositionEvaluator.evaluate()
            position: The position object being evaluated
            scan_type: Which scan this is from ('6am', '8am', etc.)
            market_conditions: Stock price, IV, etc.
            ta_indicators: RSI, trend, etc.
            full_context: Complete context to store as JSON
        
        Returns:
            Tuple of (recommendation, snapshot, should_notify)
        """
        # Extract position identity
        symbol = position.symbol
        source_strike = float(position.strike_price)
        source_expiration = position.expiration_date
        option_type = position.option_type
        account_name = getattr(position, 'account_name', None) or getattr(position, 'account', 'Unknown')
        
        # Generate stable recommendation ID
        rec_id = generate_recommendation_id(
            symbol, source_strike, source_expiration, option_type, account_name
        )
        
        # Find or create recommendation
        recommendation = self._find_or_create_recommendation(
            rec_id=rec_id,
            symbol=symbol,
            source_strike=source_strike,
            source_expiration=source_expiration,
            option_type=option_type,
            account_name=account_name,
            contracts=getattr(position, 'contracts', None),
            original_premium=getattr(position, 'original_premium', None)
        )
        
        # Get previous snapshot for change detection
        prev_snapshot = recommendation.get_latest_snapshot()
        
        # Create new snapshot
        snapshot = self._create_snapshot(
            recommendation=recommendation,
            evaluation=evaluation,
            prev_snapshot=prev_snapshot,
            scan_type=scan_type,
            market_conditions=market_conditions,
            ta_indicators=ta_indicators,
            full_context=full_context
        )
        
        # Decide if we should notify
        should_notify = self._should_notify(recommendation, snapshot, prev_snapshot)
        
        # Update recommendation stats
        recommendation.total_snapshots = (recommendation.total_snapshots or 0) + 1
        recommendation.last_snapshot_at = snapshot.evaluated_at
        recommendation.updated_at = datetime.utcnow()
        
        # Commit changes
        try:
            self.db.commit()
            logger.info(
                f"[REC_SERVICE] Recorded snapshot #{snapshot.snapshot_number} "
                f"for {rec_id} (action={evaluation.action}, should_notify={should_notify})"
            )
        except Exception as e:
            logger.error(f"[REC_SERVICE] Error saving snapshot: {e}")
            self.db.rollback()
            raise
        
        return recommendation, snapshot, should_notify
    
    def _find_or_create_recommendation(
        self,
        rec_id: str,
        symbol: str,
        source_strike: float,
        source_expiration: date,
        option_type: str,
        account_name: str,
        contracts: int = None,
        original_premium: float = None
    ) -> PositionRecommendation:
        """Find existing active recommendation or create new one."""
        
        # Look for existing active recommendation
        existing = self.db.query(PositionRecommendation).filter(
            and_(
                PositionRecommendation.recommendation_id == rec_id,
                PositionRecommendation.status == 'active'
            )
        ).first()
        
        if existing:
            logger.debug(f"[REC_SERVICE] Found existing recommendation: {rec_id}")
            return existing
        
        # Create new recommendation
        recommendation = PositionRecommendation(
            recommendation_id=rec_id,
            symbol=symbol,
            account_name=account_name,
            source_strike=Decimal(str(source_strike)),
            source_expiration=source_expiration,
            option_type=option_type,
            source_contracts=contracts,
            source_original_premium=Decimal(str(original_premium)) if original_premium else None,
            status='active',
            first_detected_at=datetime.utcnow(),
            total_snapshots=0,
            total_notifications_sent=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.db.add(recommendation)
        self.db.flush()  # Get the ID
        
        logger.info(f"[REC_SERVICE] Created new recommendation: {rec_id}")
        return recommendation
    
    def _create_snapshot(
        self,
        recommendation: PositionRecommendation,
        evaluation: EvaluationResult,
        prev_snapshot: Optional[RecommendationSnapshot],
        scan_type: str = None,
        market_conditions: Dict[str, Any] = None,
        ta_indicators: Dict[str, Any] = None,
        full_context: Dict[str, Any] = None
    ) -> RecommendationSnapshot:
        """Create a new snapshot for the recommendation."""
        
        # Determine snapshot number
        snapshot_number = (recommendation.total_snapshots or 0) + 1
        
        # Detect changes from previous snapshot
        action_changed = False
        target_changed = False
        priority_changed = False
        
        if prev_snapshot:
            action_changed = prev_snapshot.recommended_action != evaluation.action
            target_changed = (
                prev_snapshot.target_strike != evaluation.new_strike or
                prev_snapshot.target_expiration != evaluation.new_expiration
            )
            priority_changed = prev_snapshot.priority != evaluation.priority
        
        # Extract market conditions
        stock_price = market_conditions.get('current_price') if market_conditions else None
        stock_bid = market_conditions.get('bid') if market_conditions else None
        stock_ask = market_conditions.get('ask') if market_conditions else None
        iv = market_conditions.get('iv') if market_conditions else None
        
        # Extract TA indicators
        rsi = ta_indicators.get('rsi') if ta_indicators else None
        trend = ta_indicators.get('trend') if ta_indicators else None
        bollinger = ta_indicators.get('bollinger_position') if ta_indicators else None
        weekly_vol = ta_indicators.get('weekly_volatility') if ta_indicators else None
        support = ta_indicators.get('support_level') if ta_indicators else None
        resistance = ta_indicators.get('resistance_level') if ta_indicators else None
        
        # Extract from evaluation details
        details = evaluation.details or {}
        current_premium = details.get('current_premium')
        profit_pct = details.get('profit_pct')
        is_itm = details.get('is_itm', False)
        itm_pct = details.get('itm_pct')
        
        # Calculate days to expiration
        days_to_exp = None
        if recommendation.source_expiration:
            days_to_exp = (recommendation.source_expiration - date.today()).days
        
        snapshot = RecommendationSnapshot(
            recommendation_id=recommendation.id,
            snapshot_number=snapshot_number,
            evaluated_at=datetime.utcnow(),
            scan_type=scan_type,
            
            # Algorithm's advice
            recommended_action=evaluation.action,
            priority=evaluation.priority,
            decision_state=evaluation.action,  # Using action as decision state
            reason=evaluation.reason,
            
            # Target parameters
            target_strike=Decimal(str(evaluation.new_strike)) if evaluation.new_strike else None,
            target_expiration=evaluation.new_expiration,
            target_premium=None,  # Will be filled if available
            estimated_cost_to_close=Decimal(str(current_premium)) if current_premium else None,
            net_cost=Decimal(str(evaluation.net_cost)) if evaluation.net_cost else None,
            
            # Source position state
            current_premium=Decimal(str(current_premium)) if current_premium else None,
            profit_pct=Decimal(str(profit_pct * 100)) if profit_pct else None,
            days_to_expiration=days_to_exp,
            is_itm=is_itm,
            itm_pct=Decimal(str(itm_pct)) if itm_pct else None,
            
            # Market conditions
            stock_price=Decimal(str(stock_price)) if stock_price else None,
            stock_bid=Decimal(str(stock_bid)) if stock_bid else None,
            stock_ask=Decimal(str(stock_ask)) if stock_ask else None,
            implied_volatility=Decimal(str(iv)) if iv else None,
            
            # Technical analysis
            rsi=Decimal(str(rsi)) if rsi else None,
            trend=trend,
            bollinger_position=bollinger,
            weekly_volatility=Decimal(str(weekly_vol)) if weekly_vol else None,
            support_level=Decimal(str(support)) if support else None,
            resistance_level=Decimal(str(resistance)) if resistance else None,
            
            # Change tracking
            action_changed=action_changed,
            target_changed=target_changed,
            priority_changed=priority_changed,
            previous_action=prev_snapshot.recommended_action if prev_snapshot else None,
            previous_target_strike=prev_snapshot.target_strike if prev_snapshot else None,
            previous_target_expiration=prev_snapshot.target_expiration if prev_snapshot else None,
            previous_priority=prev_snapshot.priority if prev_snapshot else None,
            
            # Full context
            full_context=full_context,
            
            # Notification (will be updated later)
            notification_sent=False,
            
            created_at=datetime.utcnow()
        )
        
        self.db.add(snapshot)
        return snapshot
    
    def _should_notify(
        self,
        recommendation: PositionRecommendation,
        snapshot: RecommendationSnapshot,
        prev_snapshot: Optional[RecommendationSnapshot]
    ) -> bool:
        """
        Decide whether this snapshot should trigger a notification.
        
        Notify if:
        1. First snapshot (new recommendation)
        2. Action changed (roll → close, etc.)
        3. Target changed significantly
        4. Priority escalated (medium → urgent)
        5. Cooldown period passed for daily reminder
        
        Don't notify if:
        - Same advice as last notification, within cooldown
        - Low priority and no changes
        - Action is NO_ACTION or HOLD
        """
        # Never notify for NO_ACTION or HOLD
        if snapshot.recommended_action in ('NO_ACTION', 'HOLD'):
            snapshot.notification_decision = 'suppressed_hold'
            return False
        
        # First snapshot: always notify
        if prev_snapshot is None:
            snapshot.notification_decision = 'sent_new'
            return True
        
        # Action changed: always notify
        if snapshot.action_changed:
            snapshot.notification_decision = 'sent_action_changed'
            return True
        
        # Target changed significantly: notify
        if snapshot.target_changed:
            # Only if strike changed by more than $1 or expiration changed
            strike_changed = abs(
                float(snapshot.target_strike or 0) - 
                float(snapshot.previous_target_strike or 0)
            ) > 1.0
            exp_changed = snapshot.target_expiration != snapshot.previous_target_expiration
            
            if strike_changed or exp_changed:
                snapshot.notification_decision = 'sent_target_changed'
                return True
        
        # Priority escalated: notify
        if snapshot.priority_changed:
            current_priority = self.PRIORITY_ORDER.get(snapshot.priority, 99)
            previous_priority = self.PRIORITY_ORDER.get(snapshot.previous_priority, 99)
            
            if current_priority < previous_priority:  # Lower number = higher priority
                snapshot.notification_decision = 'sent_priority_escalated'
                return True
        
        # Check cooldown for daily reminder
        last_notification = self._get_last_notification_time(recommendation)
        if last_notification:
            hours_since = (datetime.utcnow() - last_notification).total_seconds() / 3600
            if hours_since >= self.NOTIFICATION_COOLDOWN_HOURS:
                snapshot.notification_decision = 'sent_daily_reminder'
                return True
            else:
                snapshot.notification_decision = 'suppressed_duplicate'
                return False
        
        # No previous notification: notify
        snapshot.notification_decision = 'sent_new'
        return True
    
    def _get_last_notification_time(
        self, 
        recommendation: PositionRecommendation
    ) -> Optional[datetime]:
        """Get the time of the last notification for this recommendation."""
        last_notified = self.db.query(RecommendationSnapshot).filter(
            and_(
                RecommendationSnapshot.recommendation_id == recommendation.id,
                RecommendationSnapshot.notification_sent == True
            )
        ).order_by(
            RecommendationSnapshot.notification_sent_at.desc()
        ).first()
        
        return last_notified.notification_sent_at if last_notified else None
    
    def should_notify_verbose(
        self,
        snapshot: RecommendationSnapshot
    ) -> bool:
        """
        Verbose mode: Should we send a notification for this snapshot?
        
        In verbose mode, EVERY snapshot triggers a notification.
        Only skip for NO_ACTION or HOLD actions.
        """
        if snapshot.recommended_action in ('NO_ACTION', 'HOLD'):
            return False
        return True
    
    def should_notify_smart(
        self,
        recommendation: PositionRecommendation,
        snapshot: RecommendationSnapshot,
        prev_snapshot: Optional[RecommendationSnapshot]
    ) -> bool:
        """
        Smart mode: Should we send a notification for this snapshot?
        
        This uses intelligent logic to avoid notification spam.
        Delegates to the existing _should_notify method.
        """
        return self._should_notify(recommendation, snapshot, prev_snapshot)
    
    def mark_notification_sent(
        self,
        snapshot: RecommendationSnapshot,
        channel: str = 'telegram',
        telegram_message_id: int = None,
        mode: str = 'smart'
    ):
        """
        Mark a snapshot as having been notified.
        
        Args:
            snapshot: The snapshot that was notified
            channel: Notification channel ('telegram', 'email', etc.)
            telegram_message_id: Message ID from Telegram API
            mode: 'verbose', 'smart', or 'both'
        """
        now = datetime.utcnow()
        
        # Update mode-specific fields
        if mode in ('verbose', 'both'):
            snapshot.verbose_notification_sent = True
            snapshot.verbose_notification_at = now
        
        if mode in ('smart', 'both'):
            snapshot.smart_notification_sent = True
            snapshot.smart_notification_at = now
        
        # Update general fields (for backwards compatibility)
        snapshot.notification_sent = True
        snapshot.notification_sent_at = now
        snapshot.notification_channel = channel
        snapshot.notification_mode = mode
        
        if telegram_message_id:
            snapshot.telegram_message_id = telegram_message_id
        
        # Update recommendation stats
        recommendation = snapshot.recommendation
        recommendation.total_notifications_sent = (
            recommendation.total_notifications_sent or 0
        ) + 1
        
        self.db.commit()
    
    def mark_verbose_notification_sent(
        self,
        snapshot: RecommendationSnapshot,
        channel: str = 'telegram',
        telegram_message_id: int = None
    ):
        """Mark a snapshot as having been notified in verbose mode."""
        now = datetime.utcnow()
        snapshot.verbose_notification_sent = True
        snapshot.verbose_notification_at = now
        
        # If this is the first notification, also update general fields
        if not snapshot.notification_sent:
            snapshot.notification_sent = True
            snapshot.notification_sent_at = now
            snapshot.notification_channel = channel
            snapshot.notification_mode = 'verbose'
            if telegram_message_id:
                snapshot.telegram_message_id = telegram_message_id
            
            # Update recommendation stats
            recommendation = snapshot.recommendation
            recommendation.total_notifications_sent = (
                recommendation.total_notifications_sent or 0
            ) + 1
        
        self.db.commit()
    
    def mark_smart_notification_sent(
        self,
        snapshot: RecommendationSnapshot,
        channel: str = 'telegram',
        telegram_message_id: int = None
    ):
        """Mark a snapshot as having been notified in smart mode."""
        now = datetime.utcnow()
        snapshot.smart_notification_sent = True
        snapshot.smart_notification_at = now
        
        # If this is the first notification, also update general fields
        if not snapshot.notification_sent:
            snapshot.notification_sent = True
            snapshot.notification_sent_at = now
            snapshot.notification_channel = channel
            snapshot.notification_mode = 'smart'
            if telegram_message_id:
                snapshot.telegram_message_id = telegram_message_id
            
            # Update recommendation stats
            recommendation = snapshot.recommendation
            recommendation.total_notifications_sent = (
                recommendation.total_notifications_sent or 0
            ) + 1
        elif snapshot.notification_mode == 'verbose':
            # Both modes now sent
            snapshot.notification_mode = 'both'
        
        self.db.commit()
    
    def resolve_recommendation(
        self,
        recommendation_id: int,
        resolution_type: str,
        notes: str = None
    ):
        """
        Mark a recommendation as resolved.
        
        Called when:
        - User acts on the recommendation
        - Position expires
        - Position is assigned
        - Position is closed externally
        """
        recommendation = self.db.query(PositionRecommendation).get(recommendation_id)
        if not recommendation:
            logger.warning(f"[REC_SERVICE] Recommendation {recommendation_id} not found")
            return
        
        recommendation.status = 'resolved'
        recommendation.resolution_type = resolution_type
        recommendation.resolution_notes = notes
        recommendation.resolved_at = datetime.utcnow()
        
        # Calculate days active
        if recommendation.first_detected_at:
            days = (datetime.utcnow() - recommendation.first_detected_at).days
            recommendation.days_active = days
        
        self.db.commit()
        logger.info(
            f"[REC_SERVICE] Resolved recommendation {recommendation.recommendation_id} "
            f"({resolution_type})"
        )
    
    def get_active_recommendations(
        self,
        symbol: str = None,
        account_name: str = None
    ) -> List[PositionRecommendation]:
        """Get all active recommendations, optionally filtered."""
        query = self.db.query(PositionRecommendation).filter(
            PositionRecommendation.status == 'active'
        )
        
        if symbol:
            query = query.filter(PositionRecommendation.symbol == symbol)
        if account_name:
            query = query.filter(PositionRecommendation.account_name == account_name)
        
        return query.order_by(PositionRecommendation.first_detected_at.desc()).all()
    
    def get_recommendation_with_snapshots(
        self,
        recommendation_id: int
    ) -> Optional[PositionRecommendation]:
        """Get a recommendation with all its snapshots loaded."""
        return self.db.query(PositionRecommendation).filter(
            PositionRecommendation.id == recommendation_id
        ).first()
    
    def check_and_resolve_expired_positions(self):
        """
        Check for recommendations whose source positions have expired.
        
        Should be run daily after market close.
        """
        today = date.today()
        
        # Find active recommendations with expired source positions
        expired = self.db.query(PositionRecommendation).filter(
            and_(
                PositionRecommendation.status == 'active',
                PositionRecommendation.source_expiration < today
            )
        ).all()
        
        for rec in expired:
            self.resolve_recommendation(
                rec.id,
                'position_expired_worthless',
                f'Position expired on {rec.source_expiration}'
            )
        
        logger.info(f"[REC_SERVICE] Resolved {len(expired)} expired recommendations")
        return len(expired)
    
    def cleanup_stale_recommendations(self, current_positions: set = None):
        """
        Mark recommendations as resolved if the underlying position no longer exists.
        
        This handles cases where:
        - User closed the position (sold to close, assignment, etc.)
        - Position was rolled to a new strike/expiration
        - Data was updated and position disappeared
        
        Args:
            current_positions: Set of position keys in format "SYMBOL_STRIKE_EXPIRATION_ACCOUNT"
                              If None, will fetch from latest sold_options snapshots.
        
        Should be called at the start of each recommendation scan.
        """
        from app.modules.strategies.models import SoldOptionsSnapshot, SoldOption
        from sqlalchemy import desc
        
        # Build set of current positions if not provided
        if current_positions is None:
            current_positions = set()
            
            # Get latest snapshot for each account
            accounts = self.db.query(SoldOptionsSnapshot.account_name).distinct().all()
            for (account,) in accounts:
                latest = self.db.query(SoldOptionsSnapshot).filter(
                    SoldOptionsSnapshot.account_name == account
                ).order_by(desc(SoldOptionsSnapshot.created_at)).first()
                
                if latest:
                    options = self.db.query(SoldOption).filter(
                        SoldOption.snapshot_id == latest.id
                    ).all()
                    for opt in options:
                        key = f"{opt.symbol}_{opt.strike_price}_{opt.expiration_date}_{account}"
                        current_positions.add(key)
        
        # Find active recommendations without matching positions
        active_recs = self.db.query(PositionRecommendation).filter(
            PositionRecommendation.status == 'active'
        ).all()
        
        cleaned_count = 0
        for rec in active_recs:
            # Skip uncovered positions - they don't have sold options to match against
            # Uncovered positions are managed by the new_covered_call strategy
            if rec.position_type == 'uncovered' or rec.source_strike is None:
                continue
            
            key = f"{rec.symbol}_{rec.source_strike}_{rec.source_expiration}_{rec.account_name}"
            if key not in current_positions:
                self.resolve_recommendation(
                    rec.id,
                    'position_closed',
                    f'Position no longer exists in current snapshot'
                )
                cleaned_count += 1
                logger.info(f"[REC_SERVICE] Cleaned stale: {rec.symbol} ${rec.source_strike} ({rec.account_name})")
        
        if cleaned_count > 0:
            logger.info(f"[REC_SERVICE] Cleaned {cleaned_count} stale recommendations")
        
        return cleaned_count
    
    def link_execution_to_recommendation(
        self,
        recommendation: PositionRecommendation,
        execution_data: Dict[str, Any],
        match_type: str = 'consent'
    ) -> RecommendationExecution:
        """
        Link a user execution to a recommendation.
        
        This creates the RecommendationExecution record that enables RLHF.
        """
        # Find the most recent snapshot before execution
        snapshot = recommendation.get_latest_snapshot()
        
        # Calculate timing
        executed_at = execution_data.get('executed_at', datetime.utcnow())
        hours_after_snapshot = None
        if snapshot:
            delta = executed_at - snapshot.evaluated_at
            hours_after_snapshot = delta.total_seconds() / 3600
        
        # Calculate modification details if applicable
        modification_details = None
        if match_type.startswith('modify'):
            modification_details = self._calculate_modifications(
                snapshot, execution_data
            )
        
        execution = RecommendationExecution(
            recommendation_id=recommendation.id,
            snapshot_id=snapshot.id if snapshot else None,
            
            execution_action=execution_data.get('action'),
            execution_strike=execution_data.get('strike'),
            execution_expiration=execution_data.get('expiration'),
            execution_premium=execution_data.get('premium'),
            execution_contracts=execution_data.get('contracts'),
            execution_net_cost=execution_data.get('net_cost'),
            
            match_type=match_type,
            modification_details=modification_details,
            
            executed_at=executed_at,
            hours_after_snapshot=hours_after_snapshot,
            notification_count_before_action=recommendation.total_notifications_sent,
            
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.db.add(execution)
        
        # Resolve the recommendation
        self.resolve_recommendation(
            recommendation.id,
            f'user_acted_{match_type}',
            f'User executed {execution_data.get("action")} at ${execution_data.get("strike")}'
        )
        
        return execution
    
    def _calculate_modifications(
        self,
        snapshot: RecommendationSnapshot,
        execution_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate what the user modified from the recommendation."""
        mods = {}
        
        if snapshot.target_strike and execution_data.get('strike'):
            mods['strike_diff'] = float(execution_data['strike']) - float(snapshot.target_strike)
        
        if snapshot.target_expiration and execution_data.get('expiration'):
            exec_exp = execution_data['expiration']
            if isinstance(exec_exp, str):
                exec_exp = date.fromisoformat(exec_exp)
            days_diff = (exec_exp - snapshot.target_expiration).days
            mods['expiration_diff_days'] = days_diff
        
        if snapshot.target_premium and execution_data.get('premium'):
            mods['premium_diff'] = float(execution_data['premium']) - float(snapshot.target_premium)
        
        return mods if mods else None


def get_recommendation_service(db: Session) -> RecommendationService:
    """Factory function to get a RecommendationService instance."""
    return RecommendationService(db)

