"""
V5 Orchestrator - Thin coordination layer that calls all 4 engines.

Responsibilities:
- Instantiates and calls engines
- Converts V5EvaluationResult → notification dicts
- Formats titles and action displays
- Formats Telegram messages
- Saves to DB history
- Manages follow-up conditions
- Routes pending order evaluation
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
from decimal import Decimal

from app.modules.strategies.v5.base import (
    V5EvaluationResult,
    get_v5_config,
    calculate_intrinsic_time_value,
    estimate_current_premium,
)
from app.modules.strategies.v5.engine_uncovered import UncoveredEngine
from app.modules.strategies.v5.engine_puts import PutEngine
from app.modules.strategies.v5.engine_profit import ProfitEngine
from app.modules.strategies.v5.engine_underwater import UnderwaterEngine
from app.modules.strategies.v5_pending_order_evaluator import V5PendingOrderEvaluator, PendingOrderAdvice
from app.modules.strategies.v5_sanitizer import sanitize_for_json
from app.modules.strategies.recommendation_models import (
    PositionRecommendation,
    RecommendationSnapshot,
    FollowUpCondition,
    generate_recommendation_id,
)
from app.modules.strategies.technical_analysis import get_technical_analysis_service
from app.modules.strategies.option_monitor import OptionChainFetcher

logger = logging.getLogger(__name__)

# V5 Version Tag - added to every notification for runtime verification
V5_VERSION_TAG = "v5_standalone"


# Global option chain fetcher for real-time premiums
_option_chain_fetcher = None

def _get_option_chain_fetcher():
    """Get or create the global option chain fetcher."""
    global _option_chain_fetcher
    if _option_chain_fetcher is None:
        _option_chain_fetcher = OptionChainFetcher()
    return _option_chain_fetcher


class V5Orchestrator:
    """
    V5 Orchestrator - coordinates all 4 engines and handles formatting/persistence.
    """

    def __init__(self, db: Session):
        self.db = db
        self.ta_service = get_technical_analysis_service()
        self.option_fetcher = _get_option_chain_fetcher()
        self.pending_order_evaluator = V5PendingOrderEvaluator(db=db)

        # Initialize engines
        self.uncovered_engine = UncoveredEngine(db=db, ta_service=self.ta_service)
        self.put_engine = PutEngine(db=db, ta_service=self.ta_service)
        self.profit_engine = ProfitEngine(ta_service=self.ta_service, option_fetcher=self.option_fetcher)
        self.underwater_engine = UnderwaterEngine(
            ta_service=self.ta_service,
            option_fetcher=self.option_fetcher,
            db=db
        )

        # Create a combined evaluator interface for strategy_service compatibility
        self.evaluator = _CombinedEvaluator(
            ta_service=self.ta_service,
            option_fetcher=self.option_fetcher,
            profit_engine=self.profit_engine,
            underwater_engine=self.underwater_engine,
            db=db
        )

    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================

    def get_all_v5_notifications(
        self,
        positions: List[Any],
        cost_basis_map: Optional[Dict[str, float]] = None,
        weekly_income_map: Optional[Dict[str, float]] = None,
        include_uncovered: bool = True,
        include_follow_ups: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get ALL V5 notifications in one call.

        Combines: position evaluation, uncovered detection, follow-ups, puts, pending orders.
        """
        all_notifications = []

        # 0. Cleanup stale recommendations
        self._cleanup_stale_recommendations(positions)

        # 1. Evaluate existing positions
        logger.info(f"[V5] Evaluating {len(positions)} existing positions...")
        position_notifications = self._evaluate_and_notify(
            positions=positions,
            cost_basis_map=cost_basis_map,
            weekly_income_map=weekly_income_map
        )
        all_notifications.extend(position_notifications)
        logger.info(f"[V5] Generated {len(position_notifications)} position notifications")

        # 2. Uncovered positions
        if include_uncovered:
            logger.info("[V5] Checking for uncovered positions...")
            uncovered_notifications = self.uncovered_engine.run()
            all_notifications.extend(uncovered_notifications)
            logger.info(f"[V5] Generated {len(uncovered_notifications)} uncovered position notifications")

        # 3. Follow-up conditions
        if include_follow_ups:
            logger.info("[V5] Checking follow-up conditions...")
            triggered_follow_ups = self._check_follow_up_conditions()
            if triggered_follow_ups:
                follow_up_notifications = self._generate_follow_up_notifications(triggered_follow_ups)
                all_notifications.extend(follow_up_notifications)
                logger.info(f"[V5] Generated {len(follow_up_notifications)} follow-up notifications")

        # 4. Cash-secured puts
        logger.info("[V5] Checking cash-secured put opportunities...")
        put_notifications = self.put_engine.run(positions, cost_basis_map)
        all_notifications.extend(put_notifications)
        logger.info(f"[V5] Generated {len(put_notifications)} cash-secured put notifications")

        # 5. Pending order advice
        logger.info("[V5] Checking pending orders...")
        pending_order_notifications = self._evaluate_pending_orders(
            positions=positions,
            notifications=all_notifications
        )
        replaced_position_ids = set()
        for po_notif in pending_order_notifications:
            if po_notif.get('replaces_position_id'):
                replaced_position_ids.add(po_notif.get('replaces_position_id'))

        if replaced_position_ids:
            all_notifications = [n for n in all_notifications if n.get('id') not in replaced_position_ids]
            all_notifications.extend(pending_order_notifications)
            logger.info(f"[V5] Replaced {len(replaced_position_ids)} notifications with pending order advice")

        # Tag all notifications
        for notif in all_notifications:
            notif['generated_by'] = V5_VERSION_TAG

        logger.info(f"[V5] Total notifications: {len(all_notifications)} (tagged with {V5_VERSION_TAG})")
        return all_notifications

    # =========================================================================
    # POSITION EVALUATION
    # =========================================================================

    def _evaluate_and_notify(
        self,
        positions: List[Any],
        cost_basis_map: Optional[Dict[str, float]] = None,
        weekly_income_map: Optional[Dict[str, float]] = None
    ) -> List[Dict[str, Any]]:
        """Evaluate positions and generate notifications."""
        notifications = []
        cost_basis_map = cost_basis_map or {}
        weekly_income_map = weekly_income_map or {}

        for position in positions:
            try:
                symbol = position.symbol
                cost_basis = cost_basis_map.get(symbol)
                weekly_income = weekly_income_map.get(symbol)

                result = self.evaluator.evaluate(
                    position,
                    cost_basis=cost_basis,
                    weekly_income=weekly_income
                )

                if result:
                    notif = self._result_to_notification(result, position)
                    notif = sanitize_for_json(notif)
                    notifications.append(notif)
                    self._record_snapshot(result, position)

            except Exception as e:
                logger.error(f"Error evaluating {position.symbol}: {e}", exc_info=True)

        logger.info(f"[V5] Evaluated {len(positions)} positions, {len(notifications)} with notifications")
        return notifications

    # =========================================================================
    # RESULT → NOTIFICATION CONVERSION
    # =========================================================================

    def _result_to_notification(
        self,
        result: V5EvaluationResult,
        position: Any
    ) -> Dict[str, Any]:
        """Convert V5EvaluationResult to notification format."""
        contracts = getattr(position, 'contracts_sold', 1)
        option_type = getattr(position, 'option_type', 'call')
        source_strike = getattr(position, 'strike_price', None)
        source_expiration = getattr(position, 'expiration_date', None)

        account_name = getattr(position, 'account_name', None)
        if not account_name:
            snapshot = getattr(position, 'snapshot', None)
            if snapshot:
                account_name = getattr(snapshot, 'account_name', None)

        total_premium = None
        if result.action in ('ROLL', 'COMPRESS', 'ROLL_BIWEEKLY', 'ROLL_MONTHLY') and result.net_cost is not None:
            if result.net_cost < 0:
                total_premium = abs(result.net_cost)

        title = self._format_title(
            action=result.action,
            symbol=result.symbol,
            contracts=contracts,
            option_type=option_type,
            source_strike=float(source_strike) if source_strike else None,
            source_expiration=source_expiration,
            target_strike=result.new_strike,
            target_expiration=result.new_expiration,
            total_premium=total_premium,
            stuck_category=result.stuck_category,
            biweekly_credit=result.biweekly_credit,
            monthly_credit=result.monthly_credit
        )

        if result.action in ('ROLL', 'COMPRESS') and result.net_cost is not None and result.net_cost > 0:
            total_cost = result.net_cost
            title += f" · Cost ~${total_cost:.0f}"

        return {
            'id': result.position_id,
            'symbol': result.symbol,
            'account_name': account_name,
            'action': result.action,
            'action_display': self._format_action_display(result.action),
            'title': title,
            'reason': result.reason,
            'reason_short': result.reason_short,
            'rationale': result.reason,
            'philosophy': result.philosophy_applied,
            'stuck_category': result.stuck_category,
            'iv_category': result.iv_category,
            'weekly_credit': result.weekly_credit,
            'biweekly_credit': result.biweekly_credit,
            'monthly_credit': result.monthly_credit,
            'has_follow_up': result.has_follow_up,
            'follow_up_condition': result.follow_up_condition,
            'follow_up_threshold': result.follow_up_threshold,
            'follow_up_action': result.follow_up_action,
            'contracts': contracts,
            'option_type': option_type,
            'source_strike': source_strike,
            'source_expiration': source_expiration,
            'target_strike': result.new_strike,
            'target_expiration': result.new_expiration,
            'net_cost': result.net_cost,
            'intrinsic_pct': result.intrinsic_pct,
            'time_value': result.time_value,
            'escape_weeks': result.escape_weeks,
            'compression_value': result.compression_value,
            'compression_cost': result.compression_cost,
            'cost_basis': result.cost_basis,
            'assignment_acceptable': result.assignment_acceptable,
            'context': result.details,
            'snapshot_id': None,
        }

    def _format_action_display(self, action: str) -> str:
        """Format action for display."""
        action_map = {
            'HOLD': 'HOLD',
            'CLOSE': 'CLOSE',
            'ROLL': 'ROLL',
            'COMPRESS': 'COMPRESS',
            'LET_EXPIRE': 'LET EXPIRE',
            'WAIT_FOR_PULLBACK': 'WAIT',
            'WAIT_FOR_RECOVERY': 'WAIT',
            'ROLL_BIWEEKLY': 'ROLL (2wk)',
            'ROLL_MONTHLY': 'ROLL (4wk)',
        }
        return action_map.get(action, action)

    def _format_title(
        self,
        action: str,
        symbol: str,
        contracts: int,
        option_type: str,
        source_strike: float = None,
        source_expiration: date = None,
        target_strike: float = None,
        target_expiration: date = None,
        total_premium: float = None,
        stuck_category: str = None,
        biweekly_credit: float = None,
        monthly_credit: float = None
    ) -> str:
        """Format notification title."""
        opt_type = option_type.upper() if option_type else 'CALL'

        def fmt_date(d):
            if d is None:
                return ''
            if isinstance(d, str):
                try:
                    d = datetime.strptime(d, '%Y-%m-%d').date()
                except:
                    return d
            return f"{d.month:02d}/{d.day:02d}"

        def fmt_strike(s):
            if s is None:
                return ''
            s = float(s)
            if s >= 100:
                return f"${s:.0f}"
            else:
                return f"${s:.2f}"

        # V5 NEW: ROLL_BIWEEKLY and ROLL_MONTHLY formats
        if action == 'ROLL_BIWEEKLY':
            credit = biweekly_credit if biweekly_credit else 0
            title = f"ROLL (2wk): {symbol} {fmt_strike(source_strike)} {opt_type} → {fmt_strike(target_strike)} {fmt_date(target_expiration)}"
            if credit > 0:
                title += f" · Credit ${credit:.2f}"
            return title

        elif action == 'ROLL_MONTHLY':
            credit = monthly_credit if monthly_credit else 0
            title = f"ROLL (4wk): {symbol} {fmt_strike(source_strike)} {opt_type} → {fmt_strike(target_strike)} {fmt_date(target_expiration)}"
            if credit > 0:
                title += f" · Credit ${credit:.2f}"
            return title

        # Standard formats
        action_verb = {
            'ROLL': 'Roll',
            'CLOSE': 'Close',
            'COMPRESS': 'Compress',
            'HOLD': 'Hold',
            'LET_EXPIRE': 'Let Expire',
            'SELL': 'Sell',
            'WAIT': 'Wait',
            'WAIT_FOR_PULLBACK': 'Wait',
            'WAIT_FOR_RECOVERY': 'Wait',
        }.get(action, action.title())

        opt_type_lower = opt_type.lower()

        if action == 'ROLL':
            title = f"{action_verb} {contracts} {symbol} {fmt_strike(source_strike)} {opt_type_lower} {fmt_date(source_expiration)} to {fmt_strike(target_strike)} {opt_type_lower} {fmt_date(target_expiration)}"
        elif action == 'COMPRESS':
            if target_strike and target_expiration:
                title = f"{action_verb} {contracts} {symbol} {fmt_strike(source_strike)} {opt_type_lower} {fmt_date(source_expiration)} to {fmt_strike(target_strike)} {opt_type_lower} {fmt_date(target_expiration)} (weekly)"
            else:
                title = f"{action_verb} {contracts} {symbol} {fmt_strike(source_strike)} {opt_type_lower} {fmt_date(source_expiration)} to weekly"
        elif action == 'CLOSE':
            title = f"{action_verb} {contracts} {symbol} {fmt_strike(source_strike)} {opt_type_lower} {fmt_date(source_expiration)}"
        elif action == 'HOLD':
            title = f"{action_verb} {contracts} {symbol} {fmt_strike(source_strike)} {opt_type_lower} {fmt_date(source_expiration)}"
        elif action == 'LET_EXPIRE':
            title = f"{action_verb} {contracts} {symbol} {fmt_strike(source_strike)} {opt_type_lower} {fmt_date(source_expiration)}"
        elif action == 'SELL':
            title = f"{action_verb} {contracts} {symbol} {fmt_strike(target_strike)} {opt_type_lower} {fmt_date(target_expiration)}"
        elif action in ('WAIT', 'WAIT_FOR_PULLBACK', 'WAIT_FOR_RECOVERY'):
            title = f"{action_verb} on {symbol} ({contracts} uncovered)"
        else:
            title = f"{action_verb} {contracts} {symbol}"

        if total_premium and total_premium > 0:
            title += f" · Earn ${total_premium:.0f}"

        return title

    # =========================================================================
    # SNAPSHOT RECORDING (RLHF tracking)
    # =========================================================================

    def _record_snapshot(
        self,
        result: V5EvaluationResult,
        position: Any
    ) -> Optional[RecommendationSnapshot]:
        """Record V5 evaluation as a snapshot for RLHF tracking."""
        try:
            rec = self._get_or_create_recommendation(position)
            if not rec:
                return None

            last_snapshot = self.db.query(RecommendationSnapshot).filter(
                RecommendationSnapshot.recommendation_id == rec.id
            ).order_by(RecommendationSnapshot.snapshot_number.desc()).first()

            snapshot_number = (last_snapshot.snapshot_number + 1) if last_snapshot else 1

            snapshot = RecommendationSnapshot(
                recommendation_id=rec.id,
                snapshot_number=snapshot_number,
                evaluated_at=datetime.utcnow(),
                recommended_action=result.action,
                reason=result.reason,
                priority='normal',
                target_strike=result.new_strike,
                target_expiration=result.new_expiration,
                net_cost=result.net_cost,
                full_context={
                    'v5_philosophy': result.philosophy_applied,
                    'reason_short': result.reason_short,
                    'has_follow_up': result.has_follow_up,
                    'follow_up_condition': result.follow_up_condition,
                    'follow_up_threshold': result.follow_up_threshold,
                    'intrinsic_pct': result.intrinsic_pct,
                    'escape_weeks': result.escape_weeks,
                    'stuck_category': result.stuck_category,
                    'iv_category': result.iv_category,
                    'weekly_credit': result.weekly_credit,
                    'biweekly_credit': result.biweekly_credit,
                    'monthly_credit': result.monthly_credit,
                    **result.details
                },
                created_at=datetime.utcnow(),
            )

            snapshot.notification_decision = 'sent_v5'
            rec.total_snapshots = snapshot_number
            rec.last_snapshot_at = datetime.utcnow()

            self.db.add(snapshot)
            self.db.commit()

            return snapshot

        except Exception as e:
            logger.error(f"Error recording V5 snapshot: {e}", exc_info=True)
            self.db.rollback()
            return None

    def _get_or_create_recommendation(
        self,
        position: Any
    ) -> Optional[PositionRecommendation]:
        """Get or create a PositionRecommendation for this position."""
        try:
            symbol = position.symbol
            strike = getattr(position, 'strike_price', 0)
            expiration = getattr(position, 'expiration_date', date.today())
            option_type = (getattr(position, 'option_type', 'call') or 'call').lower()

            account = None
            if hasattr(position, 'snapshot') and position.snapshot:
                account = getattr(position.snapshot, 'account_name', None)
            if not account:
                account = getattr(position, 'account_name', 'Unknown')

            rec_id = generate_recommendation_id(
                symbol=symbol,
                account_name=str(account) if account else 'Unknown',
                strike=float(strike) if strike else None,
                expiration=expiration,
                option_type=option_type
            )

            rec = self.db.query(PositionRecommendation).filter(
                PositionRecommendation.recommendation_id == rec_id
            ).first()

            if rec and rec.status != 'active':
                rec.status = 'active'
                rec.last_snapshot_at = datetime.utcnow()
                self.db.commit()

            if not rec:
                rec = PositionRecommendation(
                    recommendation_id=rec_id,
                    symbol=symbol,
                    account_name=str(account) if account else 'Unknown',
                    source_strike=float(strike) if strike else None,
                    source_expiration=expiration,
                    option_type=option_type,
                    source_contracts=getattr(position, 'contracts_sold', 1),
                    status='active',
                    first_detected_at=datetime.utcnow(),
                )
                self.db.add(rec)
                self.db.commit()

            return rec

        except Exception as e:
            logger.error(f"Error getting/creating recommendation: {e}", exc_info=True)
            return None

    def _cleanup_stale_recommendations(self, current_positions: List[Any]) -> int:
        """Mark recommendations as superseded if the underlying position no longer exists."""
        try:
            current_keys = set()
            for pos in current_positions:
                symbol = pos.symbol
                strike = float(pos.strike_price) if pos.strike_price else None
                exp = pos.expiration_date
                opt_type = (getattr(pos, 'option_type', 'call') or 'call').lower()

                if strike and exp:
                    key = (symbol, strike, exp, opt_type)
                    current_keys.add(key)

            active_recs = self.db.query(PositionRecommendation).filter(
                PositionRecommendation.status == 'active',
                PositionRecommendation.position_type == 'sold_option'
            ).all()

            superseded_count = 0
            now = datetime.utcnow()

            for rec in active_recs:
                rec_key = (
                    rec.symbol,
                    float(rec.source_strike) if rec.source_strike else None,
                    rec.source_expiration,
                    (rec.option_type or 'call').lower()
                )

                if rec_key not in current_keys:
                    rec.status = 'superseded'
                    rec.resolution_type = 'position_closed'
                    rec.resolution_notes = 'Position no longer in active holdings'
                    rec.resolved_at = now
                    superseded_count += 1

            if superseded_count > 0:
                self.db.commit()
                logger.info(f"[V5] Marked {superseded_count} stale recommendations as superseded")

            return superseded_count

        except Exception as e:
            logger.error(f"[V5] Error cleaning up stale recommendations: {e}", exc_info=True)
            self.db.rollback()
            return 0

    # =========================================================================
    # FOLLOW-UP CONDITIONS
    # =========================================================================

    def get_active_follow_up_conditions(self) -> List[FollowUpCondition]:
        """Get all active (non-triggered, non-expired) follow-up conditions."""
        return self.db.query(FollowUpCondition).filter(
            FollowUpCondition.is_active == True,
            FollowUpCondition.expired == False,
            FollowUpCondition.triggered_at.is_(None)
        ).all()

    def _check_follow_up_conditions(self) -> List[Dict[str, Any]]:
        """Check if any follow-up conditions have been met."""
        conditions = self.get_active_follow_up_conditions()
        triggered = []
        now = datetime.utcnow()

        for condition in conditions:
            try:
                if condition.expires_at and condition.expires_at < now:
                    condition.expired = True
                    condition.is_active = False
                    continue

                indicators = self.ta_service.get_technical_indicators(condition.symbol)
                if not indicators:
                    continue

                current_price = indicators.current_price
                reference_price = float(condition.reference_price)
                threshold = float(condition.threshold_pct) if condition.threshold_pct else 0.03

                condition_met = False
                price_change_pct = (current_price - reference_price) / reference_price

                if condition.condition_type in ['stock_drops_3_pct', 'stock_drops']:
                    condition_met = price_change_pct <= -threshold

                elif condition.condition_type in ['stock_bounces', 'stock_recovers']:
                    condition_met = price_change_pct >= threshold

                elif condition.condition_type in ['stock_pulls_back', 'stock_pulls_back_2_pct']:
                    condition_met = price_change_pct <= -threshold

                if condition_met:
                    condition.triggered_at = now
                    condition.trigger_price = Decimal(str(current_price))
                    condition.is_active = False

                    triggered.append({
                        'condition': condition,
                        'symbol': condition.symbol,
                        'condition_type': condition.condition_type,
                        'follow_up_action': condition.follow_up_action,
                        'reference_price': reference_price,
                        'trigger_price': current_price,
                        'price_change_pct': price_change_pct,
                        'account_name': condition.account_name,
                    })

                    logger.info(
                        f"[V5] Follow-up triggered for {condition.symbol}: "
                        f"{condition.condition_type} ({price_change_pct*100:.1f}% change)"
                    )

            except Exception as e:
                logger.warning(f"Error checking condition for {condition.symbol}: {e}")

        self.db.commit()
        return triggered

    def _generate_follow_up_notifications(self, triggered: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate notifications for triggered follow-up conditions."""
        notifications = []

        for trigger in triggered:
            condition = trigger['condition']
            symbol = trigger['symbol']
            action = trigger['follow_up_action']
            ref_price = trigger['reference_price']
            trigger_price = trigger['trigger_price']
            change_pct = trigger['price_change_pct']

            if action == 'RE_ENTER':
                reason = (
                    f"**Re-Entry Opportunity**: {symbol} has dropped {abs(change_pct)*100:.1f}% "
                    f"from ${ref_price:.2f} to ${trigger_price:.2f}.\n\n"
                    f"V5 Philosophy: Tactical timing - the stock has pulled back as expected. "
                    f"Consider selling a new covered call at this lower price."
                )
                reason_short = f"{symbol} dropped {abs(change_pct)*100:.0f}% - re-entry time"

            elif action == 'SELL_NEW':
                reason = (
                    f"**Sell New Option**: {symbol} has pulled back {abs(change_pct)*100:.1f}% "
                    f"to ${trigger_price:.2f}.\n\n"
                    f"V5 Philosophy: After closing early, wait for pullback before selling new. "
                    f"Pullback achieved - good time to sell new option."
                )
                reason_short = f"{symbol} pulled back {abs(change_pct)*100:.0f}% - sell new option"

            else:
                reason = f"Follow-up condition met for {symbol}: {action}"
                reason_short = f"{symbol} follow-up: {action}"

            notif = {
                'id': f"followup_{condition.id}",
                'symbol': symbol,
                'account_name': trigger.get('account_name'),
                'action': action,
                'action_display': f"FOLLOW-UP: {action}",
                'reason': reason,
                'reason_short': reason_short,
                'rationale': reason,
                'philosophy': 'tactical_timing',
                'is_follow_up': True,
                'original_condition': condition.condition_type,
                'reference_price': ref_price,
                'trigger_price': trigger_price,
                'price_change_pct': change_pct,
                'source_strike': 0.0,
                'source_expiration': date.today(),
                'option_type': 'call',
                'contracts': 1,
                'context': {
                    'account_name': trigger.get('account_name'),
                    'condition_id': condition.id,
                },
            }

            notifications.append(notif)

            condition.follow_up_notification_sent = True
            condition.follow_up_notification_at = datetime.utcnow()

        self.db.commit()
        return notifications

    # =========================================================================
    # PENDING ORDER EVALUATION
    # =========================================================================

    def _evaluate_pending_orders(
        self,
        positions: List[Any],
        notifications: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Evaluate pending orders and generate advice notifications."""
        pending_order_notifications = []

        notif_map = {}
        for notif in notifications:
            symbol = notif.get('symbol')
            source_strike = notif.get('source_strike')
            source_exp = notif.get('source_expiration')
            opt_type = notif.get('option_type', 'call')
            if symbol and source_strike and source_exp:
                key = (symbol, float(source_strike), str(source_exp), opt_type.lower())
                notif_map[key] = notif

        for position in positions:
            try:
                snapshot = getattr(position, 'snapshot', None)
                if not snapshot:
                    continue

                snapshot_id = snapshot.id
                symbol = position.symbol
                strike = float(position.strike_price) if position.strike_price else None
                expiration = position.expiration_date
                option_type = (getattr(position, 'option_type', 'call') or 'call').lower()

                if not strike or not expiration:
                    continue

                should_skip, pending_order = self.pending_order_evaluator.should_skip_v5_notification(
                    symbol=symbol,
                    option_type=option_type,
                    strike=strike,
                    expiration=expiration,
                    snapshot_id=snapshot_id,
                    v5_action=''
                )

                if not pending_order:
                    continue

                key = (symbol, strike, str(expiration), option_type)
                v5_notif = notif_map.get(key, {})
                v5_action = v5_notif.get('action', 'HOLD')

                v5_recommendation = {
                    'action': v5_action,
                    'days_to_exp': v5_notif.get('context', {}).get('days_to_exp', 99),
                    'new_expiration': v5_notif.get('target_expiration'),
                    'new_strike': v5_notif.get('target_strike'),
                }

                market_data = {
                    'current_bid': float(pending_order.limit_price) if pending_order.limit_price else None,
                    'current_ask': None,
                }

                advice = self.pending_order_evaluator.evaluate_pending_order(
                    pending_order=pending_order,
                    v5_recommendation=v5_recommendation,
                    market_data=market_data
                )

                po_notif = self._pending_order_advice_to_notification(
                    advice=advice,
                    position=position,
                    pending_order=pending_order,
                    original_notif=v5_notif
                )
                pending_order_notifications.append(po_notif)

                logger.info(
                    f"[V5] Pending order advice for {symbol}: {advice.action} - {advice.reason_short}"
                )

            except Exception as e:
                logger.error(f"[V5] Error evaluating pending order for {position.symbol}: {e}", exc_info=True)

        return pending_order_notifications

    def _pending_order_advice_to_notification(
        self,
        advice: PendingOrderAdvice,
        position: Any,
        pending_order: Any,
        original_notif: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Convert PendingOrderAdvice to notification format."""
        symbol = advice.symbol
        contracts = getattr(position, 'contracts_sold', 1) or 1
        option_type = getattr(position, 'option_type', 'call') or 'call'

        source_strike = getattr(position, 'strike_price', None)
        if source_strike is None and pending_order.strike_price:
            source_strike = pending_order.strike_price
        source_strike = float(source_strike) if source_strike else 0.0

        source_expiration = getattr(position, 'expiration_date', None)
        if source_expiration is None and pending_order.from_expiration:
            source_expiration = pending_order.from_expiration
        elif source_expiration is None and pending_order.to_expiration:
            source_expiration = pending_order.to_expiration

        account_name = getattr(position, 'account_name', None)
        if not account_name:
            snapshot = getattr(position, 'snapshot', None)
            if snapshot:
                account_name = getattr(snapshot, 'account_name', None)
        if not account_name:
            account_name = pending_order.account_name or 'unknown'

        action_emoji = {
            'KEEP': '✓',
            'MODIFY_UP': '↑',
            'MODIFY_DOWN': '↓',
            'CANCEL': '✗',
            'REPLACE': '↻',
        }.get(advice.action, '?')

        limit_price = float(pending_order.limit_price) if pending_order.limit_price else 0.0
        order_type = pending_order.order_type or 'ROLL'

        limit_str = f"${limit_price:.2f}" if limit_price > 0 else "N/A"
        suggested_str = f"${advice.suggested_limit:.2f}" if advice.suggested_limit else "N/A"

        if advice.action == 'KEEP':
            title = f"{action_emoji} KEEP: Pending {order_type} {symbol} @ {limit_str}"
        elif advice.action == 'MODIFY_UP':
            title = f"{action_emoji} MODIFY UP: {symbol} {limit_str} → {suggested_str}"
        elif advice.action == 'MODIFY_DOWN':
            title = f"{action_emoji} MODIFY DOWN: {symbol} {limit_str} → {suggested_str}"
        elif advice.action == 'CANCEL':
            title = f"{action_emoji} CANCEL: Pending {order_type} {symbol}"
        elif advice.action == 'REPLACE':
            title = f"{action_emoji} REPLACE: {symbol} pending order"
        else:
            title = f"Pending order: {symbol}"

        return {
            'id': f"po_{advice.order_id}",
            'replaces_position_id': original_notif.get('id'),
            'symbol': symbol,
            'account_name': account_name,
            'action': f'PENDING_ORDER_{advice.action}',
            'action_display': f'{action_emoji} {advice.action}',
            'title': title,
            'reason': advice.reason,
            'reason_short': advice.reason_short,
            'rationale': advice.reason,
            'philosophy': 'Pending Order Advisor',
            'is_pending_order': True,
            'pending_order_id': advice.order_id,
            'pending_order_type': order_type,
            'pending_limit_price': limit_price,
            'suggested_limit': advice.suggested_limit,
            'suggested_expiration': advice.suggested_expiration,
            'suggested_strike': advice.suggested_strike,
            'urgency_level': advice.urgency_level,
            'contracts': contracts,
            'option_type': option_type,
            'source_strike': source_strike,
            'source_expiration': source_expiration,
            'context': {
                'account_name': account_name,
                'original_v5_action': original_notif.get('action'),
                'current_market_bid': advice.current_market_bid,
                'pending_order_raw': pending_order.raw_text,
            },
            'snapshot_id': None,
        }

    # =========================================================================
    # TELEGRAM FORMATTING
    # =========================================================================

    def format_telegram_message(
        self,
        notifications: List[Dict[str, Any]],
        include_reasoning: bool = False
    ) -> str:
        """Format notifications for Telegram."""
        if not notifications:
            return ""

        lines = ["📢 *V5 Options Update*", ""]

        ACCOUNT_ORDER = {
            "Neel's Brokerage": 1, "Neel's Retirement": 2, "Neel's Roth IRA": 3,
            "Jaya's Brokerage": 4, "Jaya's IRA": 5, "Jaya's Roth IRA": 6,
            "Alisha's Brokerage": 7, "Agrawal Family HSA": 8,
        }

        by_account: Dict[str, List] = {}
        for notif in notifications:
            account = notif.get('context', {}).get('account_name') or notif.get('account_name') or 'Portfolio'
            if account not in by_account:
                by_account[account] = []
            by_account[account].append(notif)

        sorted_accounts = sorted(by_account.keys(), key=lambda x: ACCOUNT_ORDER.get(x, 50))

        for account in sorted_accounts:
            items = by_account[account]
            lines.append(f"*{account}* ({len(items)}):")

            for item in items:
                action = item.get('action_display', item.get('action', '?'))
                symbol = item.get('symbol', '?')
                source_strike = item.get('source_strike')
                target_strike = item.get('target_strike')
                option_type = item.get('option_type', 'call')
                reason_short = item.get('reason_short', '')
                is_uncovered = item.get('is_uncovered', False)
                contracts = item.get('contracts', 1)
                total_premium = item.get('total_premium')
                stock_price = item.get('stock_price')
                stuck_category = item.get('stuck_category')

                life_support_emoji = ""
                if stuck_category == "LIFE_SUPPORT":
                    life_support_emoji = "🏥 "
                elif stuck_category == "DROWNING":
                    life_support_emoji = "🆘 "

                if item.get('is_pending_order'):
                    action_emoji = {
                        'PENDING_ORDER_KEEP': '✓',
                        'PENDING_ORDER_MODIFY_UP': '↑',
                        'PENDING_ORDER_MODIFY_DOWN': '↓',
                        'PENDING_ORDER_CANCEL': '✗',
                        'PENDING_ORDER_REPLACE': '↻',
                    }.get(item.get('action'), '📋')

                    limit_price = item.get('pending_limit_price')
                    suggested_limit = item.get('suggested_limit')
                    urgency = item.get('urgency_level', 'normal')
                    urgency_indicator = '🔴 ' if urgency == 'critical' else ('🟡 ' if urgency == 'high' else '')

                    if item.get('action') == 'PENDING_ORDER_KEEP':
                        line = f"• {urgency_indicator}{action_emoji} KEEP: {symbol} pending @ ${limit_price:.2f}"
                    elif item.get('action') == 'PENDING_ORDER_MODIFY_UP':
                        line = f"• {urgency_indicator}{action_emoji} MODIFY UP: {symbol} ${limit_price:.2f}→${suggested_limit:.2f}"
                    elif item.get('action') == 'PENDING_ORDER_MODIFY_DOWN':
                        line = f"• {urgency_indicator}{action_emoji} MODIFY DOWN: {symbol} ${limit_price:.2f}→${suggested_limit:.2f}"
                    elif item.get('action') == 'PENDING_ORDER_CANCEL':
                        line = f"• {urgency_indicator}{action_emoji} CANCEL: {symbol} pending order"
                    elif item.get('action') == 'PENDING_ORDER_REPLACE':
                        line = f"• {urgency_indicator}{action_emoji} REPLACE: {symbol} pending order"
                    else:
                        line = f"• {action_emoji} PENDING: {symbol}"

                    lines.append(line)
                    if reason_short and len(reason_short) < 80:
                        lines.append(f"  _{reason_short}_")
                    continue

                elif item.get('action') in ('ROLL_BIWEEKLY', 'ROLL_MONTHLY'):
                    roll_period = "2wk" if item.get('action') == 'ROLL_BIWEEKLY' else "4wk"
                    credit = item.get('biweekly_credit') if item.get('action') == 'ROLL_BIWEEKLY' else item.get('monthly_credit')
                    credit_str = f"${credit:.2f}" if credit else ""
                    line = f"• {life_support_emoji}ROLL ({roll_period}): {symbol} ${source_strike:.0f} → ${target_strike:.0f} {credit_str}"
                elif is_uncovered and action in ('SELL', 'WAIT'):
                    if action == 'SELL' and target_strike:
                        if total_premium:
                            line = f"• SELL: {contracts} {symbol} ${target_strike:.0f} calls · Earn ${total_premium:.0f}"
                        else:
                            line = f"• SELL: {contracts} {symbol} ${target_strike:.0f} calls"
                    elif action == 'WAIT':
                        line = f"• ⏸️ WAIT: {symbol} ({contracts} uncovered)"
                    else:
                        line = f"• {action}: {symbol} ({contracts} uncovered)"
                elif source_strike:
                    if target_strike and action == 'ROLL':
                        line = f"• {life_support_emoji}{action}: {symbol} ${source_strike:.0f}→${target_strike:.0f} {option_type}"
                    else:
                        line = f"• {life_support_emoji}{action}: {symbol} ${source_strike:.0f} {option_type}"
                else:
                    line = f"• {life_support_emoji}{action}: {symbol}"

                if stock_price and not is_uncovered:
                    line += f" · ${stock_price:.0f}"

                if item.get('has_follow_up'):
                    line += " 🔄"

                if item.get('is_follow_up'):
                    line = f"• 🔔 FOLLOW-UP: {symbol}"

                lines.append(line)

                if reason_short and len(reason_short) < 80:
                    lines.append(f"  _{reason_short}_")

            lines.append("")

        now = datetime.now()
        lines.append(f"_{now.strftime('%I:%M %p')}_")

        return "\n".join(lines)

    # =========================================================================
    # SAVE TO HISTORY
    # =========================================================================

    def save_v5_to_history(self, notifications: List[Dict[str, Any]], scan_type: str = None) -> int:
        """Save V5 notifications to V2 snapshot tables."""
        saved = 0
        now = datetime.utcnow()

        snapshot_number_cache: Dict[int, int] = {}
        rec_cache: Dict[str, Any] = {}

        for notif in notifications:
            try:
                symbol = notif.get('symbol')
                account_name = notif.get('account_name')
                option_type = notif.get('option_type', 'call')
                source_strike = notif.get('source_strike')
                source_expiration = notif.get('source_expiration')
                action = notif.get('action', 'HOLD')

                if not symbol:
                    continue

                exp_date = source_expiration
                if isinstance(exp_date, str):
                    exp_date = date.fromisoformat(exp_date)
                elif isinstance(exp_date, datetime):
                    exp_date = exp_date.date()

                strike_val = float(source_strike) if source_strike else 0.0
                rec_id = generate_recommendation_id(
                    symbol=symbol,
                    account_name=account_name or 'unknown',
                    strike=strike_val,
                    expiration=exp_date,
                    option_type=option_type
                )

                action_type_map = {
                    'HOLD': 'HOLD',
                    'CLOSE': 'CLOSE_POSITION',
                    'ROLL': 'ROLL_POSITION',
                    'COMPRESS': 'ROLL_POSITION',
                    'LET_EXPIRE': 'NO_ACTION',
                    'WAIT_FOR_PULLBACK': 'WAIT',
                    'WAIT_FOR_RECOVERY': 'WAIT',
                    'SELL': 'SELL_CALL',
                    'WAIT': 'WAIT',
                    'ROLL_BIWEEKLY': 'ROLL_POSITION',
                    'ROLL_MONTHLY': 'ROLL_POSITION',
                }
                action_type = action_type_map.get(action, action)

                priority_map = {
                    'CLOSE': 'high',
                    'ROLL': 'high',
                    'COMPRESS': 'high',
                    'LET_EXPIRE': 'low',
                    'HOLD': 'low',
                    'SELL': 'medium',
                    'WAIT': 'low',
                    'WAIT_FOR_PULLBACK': 'low',
                    'WAIT_FOR_RECOVERY': 'low',
                    'ROLL_BIWEEKLY': 'high',
                    'ROLL_MONTHLY': 'high',
                }
                priority = priority_map.get(action, 'low')

                if rec_id in rec_cache:
                    existing_rec = rec_cache[rec_id]
                else:
                    existing_rec = self.db.query(PositionRecommendation).filter(
                        PositionRecommendation.recommendation_id == rec_id
                    ).first()

                    if not existing_rec:
                        existing_rec = PositionRecommendation(
                            recommendation_id=rec_id,
                            symbol=symbol,
                            account_name=account_name or 'unknown',
                            option_type=option_type,
                            source_strike=strike_val,
                            source_expiration=exp_date,
                            status='active',
                            first_detected_at=now,
                            created_at=now,
                            updated_at=now,
                        )
                        self.db.add(existing_rec)
                        self.db.flush()
                    elif existing_rec.status != 'active':
                        existing_rec.status = 'active'
                        existing_rec.updated_at = now

                    rec_cache[rec_id] = existing_rec

                rec_db_id = existing_rec.id
                last_snap = None
                if rec_db_id in snapshot_number_cache:
                    next_snap_num = snapshot_number_cache[rec_db_id] + 1
                else:
                    last_snap = self.db.query(RecommendationSnapshot).filter(
                        RecommendationSnapshot.recommendation_id == rec_db_id
                    ).order_by(RecommendationSnapshot.snapshot_number.desc()).first()
                    next_snap_num = (last_snap.snapshot_number + 1) if last_snap else 1

                snapshot_number_cache[rec_db_id] = next_snap_num

                action_changed = True
                if last_snap:
                    action_changed = (last_snap.recommended_action != action)

                context = notif.get('context', {})
                context['v5_philosophy'] = notif.get('philosophy', '')
                context['scan_type'] = scan_type
                context['stuck_category'] = notif.get('stuck_category')
                context['iv_category'] = notif.get('iv_category')

                target_strike = notif.get('target_strike')
                target_expiration = notif.get('target_expiration')
                if isinstance(target_expiration, str):
                    target_expiration = date.fromisoformat(target_expiration)

                full_ctx = sanitize_for_json({
                    **context,
                    'v5_title': notif.get('title', ''),
                    'v5_reason_short': notif.get('reason_short', ''),
                    'v5_action_display': notif.get('action_display', ''),
                    'v5_philosophy': notif.get('philosophy', ''),
                    'v5_action_type': action_type,
                    'contracts': notif.get('contracts', 1),
                    'option_type': option_type,
                    'account_name': account_name,
                    'has_follow_up': notif.get('has_follow_up', False),
                    'follow_up_condition': notif.get('follow_up_condition'),
                    'follow_up_action': notif.get('follow_up_action'),
                    'stuck_category': notif.get('stuck_category'),
                    'iv_category': notif.get('iv_category'),
                    'weekly_credit': notif.get('weekly_credit'),
                    'biweekly_credit': notif.get('biweekly_credit'),
                    'monthly_credit': notif.get('monthly_credit'),
                })

                snapshot = RecommendationSnapshot(
                    recommendation_id=existing_rec.id,
                    snapshot_number=next_snap_num,
                    recommended_action=action,
                    priority=priority,
                    reason=notif.get('reason', ''),
                    decision_state=notif.get('philosophy', ''),
                    stock_price=context.get('current_price'),
                    profit_pct=context.get('profit_pct', 0) * 100 if context.get('profit_pct') else None,
                    days_to_expiration=context.get('days_to_exp'),
                    is_itm=context.get('is_itm'),
                    itm_pct=context.get('itm_pct'),
                    target_strike=float(target_strike) if target_strike else None,
                    target_expiration=target_expiration,
                    net_cost=float(notif.get('net_cost')) if notif.get('net_cost') else None,
                    rsi=context.get('rsi'),
                    full_context=full_ctx,
                    action_changed=action_changed,
                    target_changed=False,
                    priority_changed=False,
                    evaluated_at=now,
                    scan_type=scan_type,
                    verbose_notification_sent=True,
                    verbose_notification_at=now,
                    notification_sent=True,
                    notification_sent_at=now,
                    notification_mode='verbose',
                )
                self.db.add(snapshot)

                existing_rec.total_snapshots = next_snap_num
                existing_rec.last_snapshot_at = now
                existing_rec.updated_at = now

                saved += 1

            except Exception as e:
                logger.error(f"[V5] Error saving notification to history for {notif.get('symbol')}: {e}")
                continue

        try:
            self.db.commit()
            logger.info(f"[V5] Saved {saved} notifications to V2 history")
        except Exception as e:
            logger.error(f"[V5] Error committing V5 notifications to history: {e}")
            self.db.rollback()
            saved = 0

        return saved


class _CombinedEvaluator:
    """
    Internal evaluator that delegates to ProfitEngine and UnderwaterEngine.

    Preserves the V5PositionEvaluator.evaluate() interface used by strategy_service.
    """

    def __init__(self, ta_service, option_fetcher, profit_engine, underwater_engine, db=None):
        self.ta_service = ta_service
        self.option_fetcher = option_fetcher
        self.profit_engine = profit_engine
        self.underwater_engine = underwater_engine
        self.db = db
        self.config = get_v5_config()

    def evaluate(
        self,
        position,
        cost_basis: Optional[float] = None,
        weekly_income: Optional[float] = None
    ) -> Optional[V5EvaluationResult]:
        """
        Main V5 evaluation logic - delegates to appropriate engine.

        Same interface as the old V5PositionEvaluator.evaluate().
        """
        try:
            indicators = self.ta_service.get_technical_indicators(position.symbol)
            if not indicators:
                logger.warning(f"Cannot get indicators for {position.symbol}, using fallback evaluation")
                return self.profit_engine.evaluate_fallback(position)

            current_price = indicators.current_price

            today = date.today()
            days_to_exp = (position.expiration_date - today).days

            from app.modules.strategies.utils.option_calculations import calculate_itm_status
            strike_price = float(position.strike_price) if position.strike_price else 0.0
            itm_calc = calculate_itm_status(
                current_price, strike_price, position.option_type
            )
            is_itm = itm_calc['is_itm']
            itm_pct = itm_calc['itm_pct']

            original_premium_raw = getattr(position, 'original_premium', 1.0)
            original_premium = float(original_premium_raw) if original_premium_raw else 1.0

            current_premium_raw = getattr(position, 'current_premium', None) or \
                                  getattr(position, 'premium_per_contract', None)
            if current_premium_raw is not None:
                current_premium = float(current_premium_raw)
            else:
                current_premium = estimate_current_premium(position, indicators)

            profit_pct = (original_premium - current_premium) / original_premium if original_premium > 0 else 0

            intrinsic_value, time_value = calculate_intrinsic_time_value(
                position, current_price, current_premium
            )
            intrinsic_pct = intrinsic_value / current_premium if current_premium > 0 else 0

            # STEP 1: Time Cushion Check
            if days_to_exp <= self.config['time_cushion']['min_days_to_expiry']:
                if is_itm:
                    return self.underwater_engine.evaluate_time_cushion_itm(
                        position, is_itm, itm_pct, intrinsic_pct,
                        current_price, current_premium
                    )
                else:
                    return self.profit_engine.evaluate_time_cushion_otm(
                        position, profit_pct, current_price, current_premium, intrinsic_pct
                    )

            # STEP 2: Early Profit Capture
            early_close_threshold = self.config.get('early_close_threshold', 0.70)
            if profit_pct >= early_close_threshold:
                return self.profit_engine.evaluate_early_profit(
                    position, profit_pct, original_premium, current_premium,
                    current_price, days_to_exp
                )

            # STEP 3: Cost Basis Check (for puts)
            if position.option_type == 'put' and cost_basis is not None:
                assignment_result = self._check_assignment_acceptability(
                    position, cost_basis, current_price, is_itm, itm_pct, days_to_exp
                )
                if assignment_result:
                    return assignment_result

            # STEP 4-5: ITM → Underwater Engine
            if is_itm:
                return self.underwater_engine.evaluate(
                    position, is_itm, itm_pct, intrinsic_pct, intrinsic_value, time_value,
                    current_price, current_premium, profit_pct, days_to_exp,
                    weekly_income, cost_basis
                )

            # STEP 6: OTM → Profit Engine
            return self.profit_engine.evaluate_otm(
                position, itm_pct, current_price, current_premium,
                profit_pct, days_to_exp, indicators
            )

        except Exception as e:
            logger.error(f"V5 evaluation error for {position.symbol}: {e}", exc_info=True)
            return None

    def _check_assignment_acceptability(
        self,
        position,
        cost_basis: float,
        current_price: float,
        is_itm: bool,
        itm_pct: float,
        days_to_exp: int
    ) -> Optional[V5EvaluationResult]:
        """For puts: Check if assignment would be acceptable based on cost basis."""
        strike = float(position.strike_price) if position.strike_price else 0.0
        assignment_improves_basis = strike < cost_basis

        if is_itm and assignment_improves_basis:
            reason = (
                f"**HOLD - Assignment Acceptable**: Put is ITM ({itm_pct:.1f}%), "
                f"but assignment at ${strike:.2f} would improve your cost basis (${cost_basis:.2f}).\n\n"
                f"V5 Philosophy: We believe in our holdings. Assignment at a lower price "
                f"improves our position."
            )
            reason_short = f"ITM put, but strike ${strike:.0f} < cost basis ${cost_basis:.0f} - assignment OK"

            return V5EvaluationResult(
                action='HOLD',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='believe_in_holdings',
                details={
                    'is_itm': is_itm,
                    'itm_pct': itm_pct,
                    'cost_basis': cost_basis,
                    'strike': strike,
                    'assignment_improves_basis': True
                },
                cost_basis=cost_basis,
                assignment_acceptable=True
            )

        return None
