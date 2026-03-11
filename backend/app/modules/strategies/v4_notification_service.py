"""
V4 Notification Service

Integrates V4 Position Evaluator with the notification system.

Key differences from V3:
- Uses V4 evaluator for all position analysis
- Generates rich reasoning in notifications
- Tracks follow-up conditions for two-part actions
- Sends HOLD notifications (no suppression)
- No priority-based sorting (all equal)
- Detects and notifies on uncovered positions (shares without sold calls)
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.modules.strategies.v4_position_evaluator import V4PositionEvaluator, V4EvaluationResult
from app.modules.strategies.v4_sanitizer import sanitize_for_json
from app.modules.strategies.recommendation_models import (
    PositionRecommendation,
    RecommendationSnapshot,
    FollowUpCondition,
    generate_recommendation_id,
)
from app.modules.strategies.technical_analysis import get_technical_analysis_service
from app.modules.strategies.option_monitor import OptionChainFetcher
from decimal import Decimal

logger = logging.getLogger(__name__)

# Global option chain fetcher for real-time premiums
_option_chain_fetcher = None

def _get_option_chain_fetcher():
    """Get or create the global option chain fetcher."""
    global _option_chain_fetcher
    if _option_chain_fetcher is None:
        _option_chain_fetcher = OptionChainFetcher()
    return _option_chain_fetcher


class V4NotificationService:
    """
    V4-native notification service.

    Uses V4 evaluator and generates notifications with rich reasoning.
    """

    def __init__(self, db: Session):
        self.db = db
        self.evaluator = V4PositionEvaluator(db=db)
        self.ta_service = get_technical_analysis_service()

    # =========================================================================
    # UNCOVERED POSITION DETECTION
    # =========================================================================

    def get_uncovered_positions(self) -> List[Dict[str, Any]]:
        """
        Detect positions with shares but no sold calls (uncovered).

        V4 Philosophy: Every share should be generating income.
        If you have 100+ shares without a sold call, that's missed income.

        Returns:
            List of dicts with account_name, symbol, uncovered contracts, etc.
        """
        try:
            # Get all holdings with enough shares for options (100+ shares)
            # Include all account types that can hold stocks (exclude HSA, 401k which typically can't trade options)
            result = self.db.execute(text("""
                SELECT
                    ia.account_name,
                    ih.symbol,
                    ih.quantity,
                    ih.current_price,
                    ih.market_value
                FROM investment_holdings ih
                JOIN investment_accounts ia ON ih.account_id = ia.account_id AND ih.source = ia.source
                WHERE ih.quantity >= 100
                AND ih.symbol NOT LIKE '%CASH%'
                AND ih.symbol NOT LIKE '%MONEY%'
                AND ih.symbol NOT LIKE '%FDRXX%'
                AND (
                    ia.account_type IN ('brokerage', 'retirement', 'ira', 'roth_ira', 'traditional_ira', 'roth')
                    OR ia.account_type LIKE '%ira%'
                    OR ia.account_type LIKE '%brokerage%'
                )
                ORDER BY ih.market_value DESC
            """))

            # Get currently sold options by account
            from app.modules.strategies.services import get_sold_options_by_account
            from app.core.account_aliases import normalize_account_name, get_all_names_for_account
            sold_by_account = get_sold_options_by_account(self.db)

            uncovered_positions = []
            all_holdings = list(result)
            logger.info(f"[V4] Found {len(all_holdings)} holdings with 100+ shares")

            # Debug: Log account names from both sources
            holdings_accounts = set(row[0] for row in all_holdings)
            sold_accounts = set(sold_by_account.keys())
            logger.info(f"[V4] Holdings accounts: {holdings_accounts}")
            logger.info(f"[V4] Sold options accounts: {sold_accounts}")

            # Build a lookup that handles account aliases
            # Maps canonical name -> sold_by_account key
            # Also maps all aliases to their sold_by_account keys
            canonical_to_sold_key = {}
            for acc_name in sold_by_account.keys():
                canonical = normalize_account_name(acc_name)
                canonical_to_sold_key[canonical] = acc_name
                # Also map all known aliases
                for alias in get_all_names_for_account(canonical):
                    canonical_to_sold_key[alias.lower().strip()] = acc_name
            logger.info(f"[V4] Canonical to sold key mapping: {canonical_to_sold_key}")

            for row in all_holdings:
                account_name, symbol, qty, price, value = row
                qty = float(qty) if qty else 0
                options_count = int(qty // 100)

                # Count sold CALLS for this symbol in this account
                # Puts don't require share backing (they're cash-secured)
                sold_count = 0

                # Match accounts using alias normalization
                # Holdings account_name (e.g., "Neel's Retirement") needs to match
                # sold options account_name (which might be stored as "Neel's IRA")
                canonical_holdings_acc = normalize_account_name(account_name)
                actual_sold_account = None

                # Try multiple lookup strategies
                if account_name in sold_by_account:
                    actual_sold_account = account_name
                elif canonical_holdings_acc in sold_by_account:
                    actual_sold_account = canonical_holdings_acc
                elif canonical_holdings_acc in canonical_to_sold_key:
                    actual_sold_account = canonical_to_sold_key[canonical_holdings_acc]
                elif account_name.lower().strip() in canonical_to_sold_key:
                    actual_sold_account = canonical_to_sold_key[account_name.lower().strip()]

                if actual_sold_account:
                    logger.debug(f"[V4] Account match: '{account_name}' -> '{actual_sold_account}'")
                    by_symbol = sold_by_account[actual_sold_account].get("by_symbol", {})
                    if symbol in by_symbol:
                        sold_count = sum(
                            opt["contracts_sold"] for opt in by_symbol[symbol]
                            if opt.get("option_type", "").lower() == "call"
                        )
                else:
                    logger.debug(f"[V4] No sold options account match for holdings account '{account_name}' (canonical: {canonical_holdings_acc})")

                uncovered = options_count - sold_count

                # Log each holding's status
                logger.debug(f"[V4] Holding: {account_name} | {symbol} | qty={qty} | options={options_count} | sold={sold_count} | uncovered={uncovered}")

                if uncovered > 0:
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

            logger.info(f"[V4] Found {len(uncovered_positions)} uncovered positions")
            if uncovered_positions:
                for pos in uncovered_positions:
                    logger.info(f"[V4] Uncovered: {pos['account_name']} | {pos['symbol']} | {pos['uncovered']} uncovered")
            return uncovered_positions

        except Exception as e:
            logger.error(f"[V4] Error detecting uncovered positions: {e}", exc_info=True)
            return []

    def evaluate_uncovered_positions(self) -> List[Dict[str, Any]]:
        """
        Evaluate uncovered positions and generate SELL or WAIT notifications.

        V4 Philosophy (Tactical Timing):
        - Don't sell calls when stock is DOWN → wait for recovery
        - Sell when stock is UP (good premium capture)

        Uses technical analysis to determine:
        - SELL: Stock correcting from overbought, safe to sell
        - WAIT: Stock oversold/at support, likely to bounce
        """
        uncovered = self.get_uncovered_positions()
        notifications = []

        for position in uncovered:
            try:
                notif = self._evaluate_single_uncovered(position)
                if notif:
                    notif = sanitize_for_json(notif)
                    notifications.append(notif)
            except Exception as e:
                logger.error(f"[V4] Error evaluating uncovered {position['symbol']}: {e}")

        return notifications

    def _evaluate_single_uncovered(
        self,
        position: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Evaluate a single uncovered position for SELL or WAIT."""
        symbol = position["symbol"]
        account_name = position["account_name"]
        uncovered = position["uncovered"]

        # Get technical analysis
        indicators = self.ta_service.get_technical_indicators(symbol)
        if not indicators:
            logger.warning(f"[V4] No indicators for {symbol}, defaulting to SELL")
            # Default to SELL if no TA available
            return self._build_uncovered_sell_notification(position, None, None)

        # Check if we should wait (stock is oversold/bouncing)
        should_wait, reason, analysis = self.ta_service.should_wait_to_sell(symbol)

        # Get strike recommendation
        strike_rec = self.ta_service.recommend_strike_price(
            symbol=symbol,
            option_type="call",
            expiration_weeks=1,
            probability_target=0.90  # Delta 10
        )

        next_friday = self._get_next_friday()

        if should_wait:
            # WAIT - stock oversold, likely to bounce
            return self._build_uncovered_wait_notification(
                position, indicators, strike_rec, next_friday, reason
            )
        else:
            # SELL - technical conditions favorable
            return self._build_uncovered_sell_notification(
                position, indicators, strike_rec, next_friday, reason
            )

    def _build_uncovered_sell_notification(
        self,
        position: Dict[str, Any],
        indicators,
        strike_rec,
        next_friday: date = None,
        reason: str = None
    ) -> Dict[str, Any]:
        """Build a SELL notification for uncovered position."""
        symbol = position["symbol"]
        account_name = position["account_name"]
        uncovered = position["uncovered"]
        current_price = position.get("current_price", 0)

        if next_friday is None:
            next_friday = self._get_next_friday()

        # Get strike price
        if strike_rec:
            strike = strike_rec.recommended_strike
            strike_rationale = strike_rec.rationale
        else:
            # Fallback: ~5% OTM
            strike = round(current_price * 1.05, 0)
            strike_rationale = "Estimated 5% OTM (no live data)"

        # Try to get real premium
        premium_per_contract = None
        premium_source = "unavailable"

        try:
            option_fetcher = _get_option_chain_fetcher()
            option_quote = option_fetcher.get_option_quote(
                symbol=symbol,
                strike_price=strike,
                option_type='call',
                expiration_date=next_friday
            )
            if option_quote:
                if option_quote.bid and option_quote.bid > 0:
                    premium_per_contract = option_quote.bid * 100
                    premium_source = "live_bid"
                elif option_quote.last_price and option_quote.last_price > 0:
                    premium_per_contract = option_quote.last_price * 100
                    premium_source = "last_price"
        except Exception as e:
            logger.debug(f"Could not fetch premium for {symbol}: {e}")

        total_premium = premium_per_contract * uncovered if premium_per_contract else None

        # Build reason
        if reason:
            full_reason = (
                f"**SELL Covered Call**: {symbol} has {uncovered} uncovered contract(s).\n\n"
                f"**Technical Analysis**: {reason}\n\n"
                f"V4 Philosophy: Every share should be generating weekly income. "
                f"Sell ${strike:.0f} call expiring {next_friday.strftime('%b %d')}."
            )
        else:
            full_reason = (
                f"**SELL Covered Call**: {symbol} has {uncovered} uncovered contract(s).\n\n"
                f"V4 Philosophy: Every share should be generating weekly income."
            )

        if total_premium:
            reason_short = f"{uncovered} {symbol} uncovered - sell ${strike:.0f} call, earn ${total_premium:.0f}"
        else:
            reason_short = f"{uncovered} {symbol} uncovered - sell ${strike:.0f} call"

        # Save to V2 model for tracking
        self._save_uncovered_to_v2(
            position=position,
            action='SELL',
            priority='high',
            reason=full_reason,
            target_strike=strike,
            target_expiration=next_friday,
            target_premium=premium_per_contract,
            indicators=indicators
        )

        # Format title in standard format: "Sell 9 NVDA $200 call 1/30 · Earn $315"
        title = self._format_title(
            action='SELL',
            symbol=symbol,
            contracts=uncovered,
            option_type='call',
            source_strike=None,
            source_expiration=None,
            target_strike=strike,
            target_expiration=next_friday,
            total_premium=total_premium
        )

        return {
            'id': f"uncovered_sell_{symbol}_{account_name}_{date.today().isoformat()}",
            'symbol': symbol,
            'action': 'SELL',
            'action_display': 'Sell',
            'title': title,  # Standard formatted title
            'reason': full_reason,
            'reason_short': reason_short,
            'rationale': full_reason,
            'philosophy': 'weekly_options_income',
            # Position details
            'contracts': uncovered,
            'option_type': 'call',
            'source_strike': None,  # Uncovered - no existing strike
            'source_expiration': None,
            # Target
            'target_strike': strike,
            'target_expiration': next_friday,
            'target_premium': premium_per_contract,
            'total_premium': total_premium,
            'premium_source': premium_source,
            # Context
            'is_uncovered': True,
            'stock_price': current_price,
            'context': {
                'account_name': account_name,
                'uncovered_contracts': uncovered,
                'total_options': position.get("options_count", 0),
                'sold_contracts': position.get("sold_count", 0),
                'strike_rationale': strike_rationale,
            },
        }

    def _build_uncovered_wait_notification(
        self,
        position: Dict[str, Any],
        indicators,
        strike_rec,
        next_friday: date,
        reason: str
    ) -> Dict[str, Any]:
        """Build a WAIT notification for uncovered position."""
        symbol = position["symbol"]
        account_name = position["account_name"]
        uncovered = position["uncovered"]
        current_price = position.get("current_price", 0)

        # Get strike price for reference
        if strike_rec:
            strike = strike_rec.recommended_strike
        else:
            strike = round(current_price * 1.05, 0)

        full_reason = (
            f"**WAIT Before Selling**: {symbol} has {uncovered} uncovered contract(s), "
            f"but stock is likely to bounce.\n\n"
            f"**Technical Analysis**: {reason}\n\n"
            f"V4 Philosophy (Tactical Timing): Don't sell calls when stock is DOWN. "
            f"Wait for recovery to capture better premium."
        )

        reason_short = f"{uncovered} {symbol} uncovered - wait for bounce"

        # Save to V2 model for tracking
        self._save_uncovered_to_v2(
            position=position,
            action='WAIT',
            priority='low',
            reason=full_reason,
            target_strike=strike,
            target_expiration=next_friday,
            target_premium=None,
            indicators=indicators
        )

        # Format title: "Wait on NVDA (9 uncovered)"
        title = self._format_title(
            action='WAIT',
            symbol=symbol,
            contracts=uncovered,
            option_type='call',
            source_strike=None,
            source_expiration=None,
            target_strike=strike,
            target_expiration=next_friday,
            total_premium=None
        )

        return {
            'id': f"uncovered_wait_{symbol}_{account_name}_{date.today().isoformat()}",
            'symbol': symbol,
            'action': 'WAIT',
            'action_display': 'Wait',
            'title': title,  # Standard formatted title
            'reason': full_reason,
            'reason_short': reason_short,
            'rationale': full_reason,
            'philosophy': 'tactical_timing',
            # Position details
            'contracts': uncovered,
            'option_type': 'call',
            'source_strike': None,
            'source_expiration': None,
            # Target (for when to sell)
            'target_strike': strike,
            'target_expiration': next_friday,
            # Context
            'is_uncovered': True,
            'stock_price': current_price,
            'context': {
                'account_name': account_name,
                'uncovered_contracts': uncovered,
                'wait_reason': reason,
                'rsi': indicators.rsi_14 if indicators else None,
                'trend': indicators.trend if indicators else None,
            },
        }

    def _save_uncovered_to_v2(
        self,
        position: Dict[str, Any],
        action: str,
        priority: str,
        reason: str,
        target_strike: float,
        target_expiration: date,
        target_premium: Optional[float],
        indicators
    ) -> Optional[RecommendationSnapshot]:
        """Save uncovered position recommendation to V2 model."""
        try:
            symbol = position["symbol"]
            account_name = position["account_name"]

            # Generate deterministic ID for uncovered position
            rec_id = generate_recommendation_id(
                symbol=symbol,
                account_name=account_name,
                strike=None,  # Uncovered
                expiration=None,
                option_type="call"
            )

            # Find or create PositionRecommendation
            # Don't filter by status - we want to find any existing record with this ID
            # to avoid unique constraint violations
            existing = self.db.query(PositionRecommendation).filter(
                PositionRecommendation.recommendation_id == rec_id
            ).first()

            now = datetime.utcnow()

            if existing:
                recommendation = existing
                recommendation.last_snapshot_at = now
                recommendation.updated_at = now
                # Reactivate if it was resolved
                if recommendation.status != 'active':
                    recommendation.status = 'active'
                    recommendation.resolution_type = None
                    recommendation.resolution_notes = None
                    recommendation.resolved_at = None
            else:
                recommendation = PositionRecommendation(
                    recommendation_id=rec_id,
                    symbol=symbol,
                    account_name=account_name,
                    source_strike=None,  # Uncovered
                    source_expiration=None,
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
                self.db.flush()

            # Get previous snapshot for change tracking
            prev_snapshot = self.db.query(RecommendationSnapshot).filter(
                RecommendationSnapshot.recommendation_id == recommendation.id
            ).order_by(RecommendationSnapshot.snapshot_number.desc()).first()

            snapshot_number = (prev_snapshot.snapshot_number + 1) if prev_snapshot else 1

            # Detect changes from previous snapshot
            action_changed = prev_snapshot and prev_snapshot.recommended_action != action
            target_changed = prev_snapshot and prev_snapshot.target_strike != (Decimal(str(target_strike)) if target_strike else None)
            priority_changed = prev_snapshot and prev_snapshot.priority != priority

            # Create snapshot
            snapshot = RecommendationSnapshot(
                recommendation_id=recommendation.id,
                snapshot_number=snapshot_number,
                evaluated_at=now,
                scan_type='v4_scheduled',
                recommended_action=action,
                priority=priority,
                decision_state='uncovered_position',
                reason=reason,
                target_strike=Decimal(str(target_strike)) if target_strike else None,
                target_expiration=target_expiration,
                target_premium=Decimal(str(target_premium)) if target_premium else None,
                stock_price=Decimal(str(position.get('current_price', 0))),
                rsi=Decimal(str(indicators.rsi_14)) if indicators and indicators.rsi_14 else None,
                trend=indicators.trend if indicators else None,
                action_changed=action_changed,
                target_changed=target_changed,
                priority_changed=priority_changed,
                previous_action=prev_snapshot.recommended_action if prev_snapshot else None,
                full_context={
                    'v4_philosophy': 'weekly_options_income' if action == 'SELL' else 'tactical_timing',
                    'uncovered_contracts': position.get('uncovered'),
                    'account_name': account_name,
                },
                created_at=now,
                notification_decision='sent_v4',
            )

            self.db.add(snapshot)
            recommendation.total_snapshots = snapshot_number
            self.db.commit()

            logger.info(f"[V4] Uncovered {symbol}@{account_name}: Snap #{snapshot_number} ({action})")
            return snapshot

        except Exception as e:
            logger.error(f"[V4] Error saving uncovered {position.get('symbol')}: {e}", exc_info=True)
            self.db.rollback()
            return None

    def _get_next_friday(self) -> date:
        """Get the date of next Friday."""
        today = date.today()
        days_ahead = 4 - today.weekday()  # Friday = 4
        if days_ahead <= 0:
            days_ahead += 7
        return today + timedelta(days=days_ahead)

    # =========================================================================
    # CASH-SECURED PUT RECOMMENDATIONS
    # =========================================================================

    def evaluate_cash_secured_puts(
        self,
        positions: List[Any],
        cost_basis_map: Optional[Dict[str, float]] = None
    ) -> List[Dict[str, Any]]:
        """
        Evaluate opportunities to sell cash-secured puts.

        V4 Philosophy:
        - Use idle cash to generate income via put selling
        - Only sell puts on stocks already in portfolio (believe in holdings)
        - Sell puts when stock is DOWN (good entry point if assigned)
        - Strike below cost basis = assignment improves average cost

        Args:
            positions: List of current positions (to get account names)
            cost_basis_map: {symbol: cost_basis} for assignment evaluation

        Returns:
            List of cash-secured put recommendation notifications
        """
        from app.modules.strategies.algorithm_config import (
            get_config, get_available_cash_for_puts, should_recommend_new_put
        )
        from app.modules.strategies.models import SoldOption, SoldOptionsSnapshot
        from sqlalchemy import func

        notifications = []
        config = get_config()
        cost_basis_map = cost_basis_map or {}

        # Get accounts with fixed cash balances configured
        fixed_balances = config.get("fixed_cash_balances", {})
        if not fixed_balances:
            logger.info("[V4] No fixed cash balances configured, skipping put recommendations")
            return notifications

        # Get unique symbols from current holdings that could have puts sold
        # Include symbols from sold options AND from investment holdings
        portfolio_symbols = set()
        for pos in positions:
            if hasattr(pos, 'symbol') and pos.symbol:
                portfolio_symbols.add(pos.symbol)

        # Also get symbols from investment_holdings (for uncovered positions)
        try:
            holdings_result = self.db.execute(text("""
                SELECT DISTINCT ih.symbol
                FROM investment_holdings ih
                JOIN investment_accounts ia ON ih.account_id = ia.account_id AND ih.source = ia.source
                WHERE ih.quantity >= 100
                AND ih.symbol NOT LIKE '%CASH%'
                AND ih.symbol NOT LIKE '%MONEY%'
                AND ih.symbol NOT LIKE '%FDRXX%'
            """))
            for row in holdings_result:
                portfolio_symbols.add(row[0])
            logger.info(f"[V4] Put candidates: {len(portfolio_symbols)} symbols from holdings + sold options")
        except Exception as e:
            logger.warning(f"[V4] Could not fetch holdings for put candidates: {e}")

        # For each account with fixed cash
        logger.info(f"[V4] Checking put opportunities for {len(fixed_balances)} accounts: {list(fixed_balances.keys())}")
        for account_name, fixed_balance in fixed_balances.items():
            try:
                logger.info(f"[V4] PUT CHECK: {account_name} with ${fixed_balance:,} configured")

                # Get existing puts for this account
                snap_id = self.db.query(func.max(SoldOptionsSnapshot.id)).filter(
                    SoldOptionsSnapshot.account_name == account_name
                ).scalar()

                existing_puts = []
                if snap_id:
                    existing_puts = self.db.query(SoldOption).filter(
                        SoldOption.snapshot_id == snap_id,
                        SoldOption.status == 'open',
                        SoldOption.option_type == 'put'
                    ).all()
                    logger.info(f"[V4] PUT CHECK: {account_name} has {len(existing_puts)} existing puts")
                else:
                    logger.info(f"[V4] PUT CHECK: {account_name} has no snapshot (snap_id=None)")

                # Check if we can recommend new puts
                can_recommend, available_cash, reason = should_recommend_new_put(
                    account_name, existing_puts
                )
                logger.info(f"[V4] PUT CHECK: {account_name} can_recommend={can_recommend}, available=${available_cash:,.0f}, reason={reason}")

                if not can_recommend:
                    continue

                # Find best put opportunity for this account
                logger.info(f"[V4] PUT CHECK: {account_name} searching {len(portfolio_symbols)} symbols for best opportunity")
                put_notif = self._find_best_put_opportunity(
                    account_name=account_name,
                    available_cash=available_cash,
                    existing_puts=existing_puts,
                    portfolio_symbols=portfolio_symbols,
                    cost_basis_map=cost_basis_map
                )

                if put_notif:
                    logger.info(f"[V4] PUT CHECK: {account_name} found opportunity: {put_notif.get('symbol')} ${put_notif.get('target_strike')}")
                    notifications.append(put_notif)
                else:
                    logger.info(f"[V4] PUT CHECK: {account_name} no opportunity found")

            except Exception as e:
                logger.error(f"[V4] Error evaluating puts for {account_name}: {e}", exc_info=True)

        return notifications

    def _find_best_put_opportunity(
        self,
        account_name: str,
        available_cash: float,
        existing_puts: List[Any],
        portfolio_symbols: set,
        cost_basis_map: Dict[str, float]
    ) -> Optional[Dict[str, Any]]:
        """
        Find the best cash-secured put opportunity for an account.

        Strategy:
        1. Look at stocks in portfolio that are oversold/at support
        2. Prefer strikes below cost basis (assignment improves avg cost)
        3. Pick strike that fits within available cash

        Returns:
            Put recommendation notification or None
        """
        # Symbols already with puts in this account - avoid doubling up
        existing_put_symbols = {p.symbol for p in existing_puts}
        logger.info(f"[V4] PUT SEARCH: Existing put symbols to skip: {existing_put_symbols}")

        best_opportunity = None
        best_score = -1
        evaluated_count = 0
        skipped_existing = 0
        skipped_no_indicators = 0
        skipped_no_strike = 0
        skipped_too_expensive = 0

        for symbol in portfolio_symbols:
            if symbol in existing_put_symbols:
                skipped_existing += 1
                continue  # Already have a put on this

            try:
                # Get technical analysis
                indicators = self.ta_service.get_technical_indicators(symbol)
                if not indicators:
                    skipped_no_indicators += 1
                    continue

                current_price = indicators.current_price
                if not current_price:
                    skipped_no_indicators += 1
                    continue

                evaluated_count += 1

                # Score this opportunity (higher = better)
                score = self._score_put_opportunity(
                    symbol=symbol,
                    indicators=indicators,
                    cost_basis=cost_basis_map.get(symbol)
                )

                if score > best_score:
                    # Check if we can afford a put at Delta 20 strike
                    strike_rec = self.ta_service.recommend_strike_price(
                        symbol=symbol,
                        option_type="put",
                        expiration_weeks=1,
                        probability_target=0.80  # Delta 20 for puts
                    )

                    if strike_rec and strike_rec.recommended_strike:
                        strike = strike_rec.recommended_strike
                        required_cash = strike * 100  # 1 contract

                        logger.info(f"[V4] PUT EVAL: {symbol} score={score:.1f}, RSI={indicators.rsi_14:.1f}, strike=${strike:.0f}, required=${required_cash:,.0f}, available=${available_cash:,.0f}")

                        if required_cash <= available_cash:
                            best_score = score
                            best_opportunity = {
                                'symbol': symbol,
                                'strike': strike,
                                'indicators': indicators,
                                'score': score,
                                'required_cash': required_cash,
                                'premium_estimate': None,  # Premium fetched separately
                            }
                            logger.info(f"[V4] PUT EVAL: {symbol} is new best opportunity!")
                        else:
                            skipped_too_expensive += 1
                    else:
                        skipped_no_strike += 1
                        logger.debug(f"[V4] PUT EVAL: {symbol} no strike recommendation")

            except Exception as e:
                logger.warning(f"[V4] Error evaluating put opportunity for {symbol}: {e}")

        logger.info(f"[V4] PUT SEARCH SUMMARY: evaluated={evaluated_count}, skipped_existing={skipped_existing}, skipped_no_indicators={skipped_no_indicators}, skipped_no_strike={skipped_no_strike}, skipped_too_expensive={skipped_too_expensive}")

        if not best_opportunity:
            return None

        # Build notification
        return self._build_put_recommendation(
            account_name=account_name,
            available_cash=available_cash,
            opportunity=best_opportunity
        )

    def _score_put_opportunity(
        self,
        symbol: str,
        indicators,
        cost_basis: Optional[float]
    ) -> float:
        """
        Score a put selling opportunity (higher = better).

        Factors:
        - RSI < 30: Oversold, good time to sell puts (+2)
        - RSI 30-40: Approaching oversold (+1)
        - Near support level (+1)
        - Strike would be below cost basis (+2)
        """
        score = 0.0

        if indicators.rsi_14:
            if indicators.rsi_14 < 30:
                score += 2.0  # Oversold - great opportunity
            elif indicators.rsi_14 < 40:
                score += 1.0  # Approaching oversold

        # Trend analysis - prefer selling puts when down
        if indicators.trend == 'oversold_bounce':
            score += 1.5
        elif indicators.trend in ('lower_band', 'bearish'):
            score += 1.0  # Stock is down - good for puts

        # Cost basis comparison
        if cost_basis and indicators.current_price:
            if indicators.current_price < cost_basis:
                score += 2.0  # Stock below cost basis - assignment would help

        return score

    def _build_put_recommendation(
        self,
        account_name: str,
        available_cash: float,
        opportunity: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build a cash-secured put recommendation notification."""
        symbol = opportunity['symbol']
        strike = opportunity['strike']
        indicators = opportunity['indicators']
        premium = opportunity.get('premium_estimate', 0) or 50  # Default estimate
        required = opportunity['required_cash']

        current_price = indicators.current_price if indicators else 0
        rsi = indicators.rsi_14 if indicators else None
        next_friday = self._get_next_friday()

        # Calculate OTM percentage
        otm_pct = ((current_price - strike) / current_price * 100) if current_price else 0

        # Build reason
        reason_parts = [
            f"**Cash-Secured Put Opportunity**: ${available_cash:,.0f} available in {account_name}.",
            "",
            f"V4 Philosophy: Use idle cash to generate income on stocks you believe in.",
            "",
            f"Recommendation: Sell 1 {symbol} ${strike:.0f} put expiring {next_friday.strftime('%m/%d')}",
            f"- Stock price: ${current_price:.2f}",
            f"- Strike {otm_pct:.1f}% below current price",
        ]

        if rsi:
            if rsi < 30:
                reason_parts.append(f"- RSI {rsi:.0f} (oversold - good entry point)")
            elif rsi < 40:
                reason_parts.append(f"- RSI {rsi:.0f} (approaching oversold)")
            else:
                reason_parts.append(f"- RSI {rsi:.0f}")

        reason_parts.append(f"- Cash required: ${required:,.0f}")
        reason_parts.append(f"- Estimated premium: ~${premium:.0f}")

        full_reason = "\n".join(reason_parts)
        reason_short = f"Sell {symbol} ${strike:.0f} put - ${available_cash:,.0f} cash available"

        # Format title: "SELL: 1 NVDA $180 put for 01/31 · Earn ~$50"
        title = f"SELL: 1 {symbol} ${strike:.0f} put for {next_friday.strftime('%m/%d')} · Earn ~${premium:.0f}"

        return {
            'id': f"csp_{symbol}_{account_name}_{date.today().isoformat()}",
            'symbol': symbol,
            'account_name': account_name,  # Top-level for save function
            'action': 'SELL_PUT',
            'action_display': 'Sell Put',
            'title': title,
            'reason': full_reason,
            'reason_short': reason_short,
            'rationale': full_reason,
            'philosophy': 'weekly_options_income',
            'priority': 'medium',
            # Position details
            'contracts': 1,
            'option_type': 'put',
            # Use target values as source for recommendation ID generation
            'source_strike': strike,
            'source_expiration': next_friday,
            # Target
            'target_strike': strike,
            'target_expiration': next_friday,
            'target_premium': premium,
            # Cash context
            'is_cash_secured_put': True,
            'available_cash': available_cash,
            'required_cash': required,
            'stock_price': current_price,
            'context': {
                'account_name': account_name,
                'available_cash': available_cash,
                'required_cash': required,
                'rsi': rsi,
                'otm_pct': otm_pct,
                'trend': indicators.trend if indicators else None,
            },
        }

    # =========================================================================
    # COMPREHENSIVE V4 NOTIFICATION METHOD
    # =========================================================================

    def get_all_v4_notifications(
        self,
        positions: List[Any],
        cost_basis_map: Optional[Dict[str, float]] = None,
        weekly_income_map: Optional[Dict[str, float]] = None,
        include_uncovered: bool = True,
        include_follow_ups: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get ALL V4 notifications in one call.

        This is the single entry point for V4 notifications that combines:
        1. Existing position evaluation (HOLD, ROLL, COMPRESS, CLOSE, etc.)
        2. Uncovered position detection (SELL, WAIT)
        3. Follow-up condition triggers

        Args:
            positions: List of SoldOption positions to evaluate
            cost_basis_map: {symbol: cost_basis} for put evaluation
            weekly_income_map: {symbol: weekly_premium} for compression calc
            include_uncovered: Whether to include uncovered position notifications
            include_follow_ups: Whether to check and include follow-up triggers

        Returns:
            Complete list of all V4 notifications
        """
        all_notifications = []

        # 0. Cleanup: Mark old recommendations as superseded if position no longer exists
        # This prevents stale recommendations from appearing when positions change
        self._cleanup_stale_recommendations(positions)

        # 1. Evaluate existing positions
        logger.info(f"[V4] Evaluating {len(positions)} existing positions...")
        position_notifications = self.evaluate_and_notify(
            positions=positions,
            cost_basis_map=cost_basis_map,
            weekly_income_map=weekly_income_map
        )
        all_notifications.extend(position_notifications)
        logger.info(f"[V4] Generated {len(position_notifications)} position notifications")

        # 2. Detect and evaluate uncovered positions
        if include_uncovered:
            logger.info("[V4] Checking for uncovered positions...")
            uncovered_notifications = self.evaluate_uncovered_positions()
            all_notifications.extend(uncovered_notifications)
            logger.info(f"[V4] Generated {len(uncovered_notifications)} uncovered position notifications")

        # 3. Check follow-up conditions
        if include_follow_ups:
            logger.info("[V4] Checking follow-up conditions...")
            triggered_follow_ups = self.check_follow_up_conditions()
            if triggered_follow_ups:
                follow_up_notifications = self.generate_follow_up_notifications(triggered_follow_ups)
                all_notifications.extend(follow_up_notifications)
                logger.info(f"[V4] Generated {len(follow_up_notifications)} follow-up notifications")

        # 4. Cash-secured put recommendations
        logger.info("[V4] Checking cash-secured put opportunities...")
        put_notifications = self.evaluate_cash_secured_puts(positions, cost_basis_map)
        all_notifications.extend(put_notifications)
        logger.info(f"[V4] Generated {len(put_notifications)} cash-secured put notifications")

        logger.info(f"[V4] Total notifications: {len(all_notifications)}")
        return all_notifications

    def save_v4_to_history(self, notifications: List[Dict[str, Any]], scan_type: str = None) -> int:
        """
        Save V4 notifications to V2 snapshot tables so they appear on the Notifications page.

        Converts V4 notification dicts to PositionRecommendation + RecommendationSnapshot
        records in the database.

        Args:
            notifications: List of V4 notification dicts (from get_all_v4_notifications)
            scan_type: Optional scan identifier (e.g., '6am_main', '8am_post_open')

        Returns:
            Number of notifications saved
        """
        saved = 0
        now = datetime.utcnow()

        # Track snapshot numbers in memory to avoid duplicates within the same batch
        # (since DB queries don't see uncommitted snapshots from earlier iterations)
        snapshot_number_cache: Dict[int, int] = {}
        # Also cache recommendation objects to avoid duplicate inserts
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

                # Parse expiration for ID generation
                exp_date = source_expiration
                if isinstance(exp_date, str):
                    exp_date = date.fromisoformat(exp_date)
                elif isinstance(exp_date, datetime):
                    exp_date = exp_date.date()

                # Generate unique recommendation ID (same logic as V2)
                strike_val = float(source_strike) if source_strike else 0.0
                rec_id = generate_recommendation_id(
                    symbol=symbol,
                    account_name=account_name or 'unknown',
                    strike=strike_val,
                    expiration=exp_date,
                    option_type=option_type
                )

                # Map V4 action to V2-compatible action_type
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
                }
                action_type = action_type_map.get(action, action)

                # Map action to priority
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
                }
                priority = priority_map.get(action, 'low')

                # Find or create PositionRecommendation
                # Check cache first (for recs created in this batch), then DB
                if rec_id in rec_cache:
                    existing_rec = rec_cache[rec_id]
                else:
                    # Query without status filter since recommendation_id is unique
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
                        self.db.flush()  # Get the ID
                    elif existing_rec.status != 'active':
                        # Reactivate if it was resolved
                        existing_rec.status = 'active'
                        existing_rec.updated_at = now

                    # Cache for subsequent iterations
                    rec_cache[rec_id] = existing_rec

                # Get the next snapshot number - check cache first, then DB
                rec_db_id = existing_rec.id
                last_snap = None  # Initialize for action_changed check
                if rec_db_id in snapshot_number_cache:
                    # We already added a snapshot for this rec in this batch
                    next_snap_num = snapshot_number_cache[rec_db_id] + 1
                else:
                    # Query DB for the last committed snapshot
                    last_snap = self.db.query(RecommendationSnapshot).filter(
                        RecommendationSnapshot.recommendation_id == rec_db_id
                    ).order_by(RecommendationSnapshot.snapshot_number.desc()).first()
                    next_snap_num = (last_snap.snapshot_number + 1) if last_snap else 1

                # Update cache for subsequent iterations
                snapshot_number_cache[rec_db_id] = next_snap_num

                # Check if action changed (for smart mode filtering)
                # Note: If rec_db_id was in cache, last_snap is None (we assume action changed within batch)
                action_changed = True
                if last_snap:
                    action_changed = (last_snap.recommended_action != action)

                # Build context for snapshot
                context = notif.get('context', {})
                context['v4_philosophy'] = notif.get('philosophy', '')
                context['scan_type'] = scan_type
                context['ta_unavailable'] = context.get('ta_unavailable', False)

                # Determine target strike/expiration for display
                target_strike = notif.get('target_strike')
                target_expiration = notif.get('target_expiration')
                if isinstance(target_expiration, str):
                    target_expiration = date.fromisoformat(target_expiration)

                # Build full context JSON for the snapshot
                full_ctx = sanitize_for_json({
                    **context,
                    'v4_title': notif.get('title', ''),
                    'v4_reason_short': notif.get('reason_short', ''),
                    'v4_action_display': notif.get('action_display', ''),
                    'v4_philosophy': notif.get('philosophy', ''),
                    'v4_action_type': action_type,
                    'contracts': notif.get('contracts', 1),
                    'option_type': option_type,
                    'account_name': account_name,
                    'has_follow_up': notif.get('has_follow_up', False),
                    'follow_up_condition': notif.get('follow_up_condition'),
                    'follow_up_action': notif.get('follow_up_action'),
                })

                # Create snapshot using actual model columns
                snapshot = RecommendationSnapshot(
                    recommendation_id=existing_rec.id,
                    snapshot_number=next_snap_num,
                    recommended_action=action,
                    priority=priority,
                    reason=notif.get('reason', ''),
                    decision_state=notif.get('philosophy', ''),
                    # Position data
                    stock_price=context.get('current_price'),
                    profit_pct=context.get('profit_pct', 0) * 100 if context.get('profit_pct') else None,
                    days_to_expiration=context.get('days_to_exp'),
                    is_itm=context.get('is_itm'),
                    itm_pct=context.get('itm_pct'),
                    # Target (for ROLL/COMPRESS)
                    target_strike=float(target_strike) if target_strike else None,
                    target_expiration=target_expiration,
                    net_cost=float(notif.get('net_cost')) if notif.get('net_cost') else None,
                    # Technical indicators (if available)
                    rsi=context.get('rsi'),
                    # Full context as JSON
                    full_context=full_ctx,
                    # Change tracking
                    action_changed=action_changed,
                    target_changed=False,
                    priority_changed=False,
                    # Timestamps
                    evaluated_at=now,
                    scan_type=scan_type,
                    # Mark as notified (so it shows on the page)
                    verbose_notification_sent=True,
                    verbose_notification_at=now,
                    notification_sent=True,
                    notification_sent_at=now,
                    notification_mode='verbose',
                )
                self.db.add(snapshot)

                # Update recommendation stats
                existing_rec.total_snapshots = next_snap_num
                existing_rec.last_snapshot_at = now
                existing_rec.updated_at = now

                saved += 1

            except Exception as e:
                logger.error(f"[V4] Error saving notification to history for {notif.get('symbol')}: {e}")
                continue

        # Commit all at once
        try:
            self.db.commit()
            logger.info(f"[V4] Saved {saved} notifications to V2 history")
        except Exception as e:
            logger.error(f"[V4] Error committing V4 notifications to history: {e}")
            self.db.rollback()
            saved = 0

        return saved

    # =========================================================================
    # MAIN EVALUATION METHODS
    # =========================================================================

    def evaluate_and_notify(
        self,
        positions: List[Any],
        cost_basis_map: Optional[Dict[str, float]] = None,
        weekly_income_map: Optional[Dict[str, float]] = None
    ) -> List[Dict[str, Any]]:
        """
        Evaluate positions using V4 logic and generate notifications.

        Args:
            positions: List of position objects to evaluate
            cost_basis_map: {symbol: cost_basis} for put evaluation
            weekly_income_map: {symbol: weekly_premium} for compression calc

        Returns:
            List of notification items ready for formatting/sending
        """
        notifications = []
        cost_basis_map = cost_basis_map or {}
        weekly_income_map = weekly_income_map or {}

        # Track evaluation results for logging
        evaluated = 0
        failed = []
        skipped_no_result = []

        # Log positions by account for debugging
        accounts_summary = {}
        for pos in positions:
            acct = getattr(pos, 'account_name', None)
            if not acct:
                # Try to get from snapshot
                snapshot = getattr(pos, 'snapshot', None)
                if snapshot:
                    acct = getattr(snapshot, 'account_name', 'Unknown')
                else:
                    acct = 'Unknown'
            accounts_summary[acct] = accounts_summary.get(acct, 0) + 1
        logger.info(f"[V4] Positions by account: {accounts_summary}")

        for position in positions:
            try:
                symbol = position.symbol
                strike = getattr(position, 'strike_price', 0)

                # Get cost basis and weekly income for this symbol
                cost_basis = cost_basis_map.get(symbol)
                weekly_income = weekly_income_map.get(symbol)

                # Log if put position is missing cost basis
                if position.option_type == 'put' and cost_basis is None:
                    logger.debug(f"[V4] {symbol} put: No cost basis - assignment check will be skipped")

                # Evaluate with V4
                result = self.evaluator.evaluate(
                    position,
                    cost_basis=cost_basis,
                    weekly_income=weekly_income
                )

                if result:
                    evaluated += 1
                    # Convert V4 result to notification format
                    notif = self._result_to_notification(result, position)
                    # Sanitize to prevent numpy/Decimal serialization errors
                    notif = sanitize_for_json(notif)
                    notifications.append(notif)

                    # Record snapshot for RLHF tracking
                    self._record_snapshot(result, position)
                else:
                    # Result was None - likely TA indicators failed
                    skipped_no_result.append(f"{symbol} ${strike}")

            except Exception as e:
                failed.append(f"{position.symbol}: {str(e)[:50]}")
                logger.error(f"Error evaluating {position.symbol}: {e}", exc_info=True)

        # Log summary
        if skipped_no_result:
            logger.warning(f"[V4] {len(skipped_no_result)} positions skipped (no indicators): {skipped_no_result[:5]}")
        if failed:
            logger.error(f"[V4] {len(failed)} positions failed: {failed[:5]}")

        logger.info(f"[V4] Evaluated {evaluated}/{len(positions)} positions, {len(notifications)} with notifications")

        return notifications

    def _result_to_notification(
        self,
        result: V4EvaluationResult,
        position: Any
    ) -> Dict[str, Any]:
        """Convert V4EvaluationResult to notification format."""
        contracts = getattr(position, 'contracts_sold', 1)
        option_type = getattr(position, 'option_type', 'call')
        source_strike = getattr(position, 'strike_price', None)
        source_expiration = getattr(position, 'expiration_date', None)

        # Get account name from position or snapshot
        account_name = getattr(position, 'account_name', None)
        if not account_name:
            snapshot = getattr(position, 'snapshot', None)
            if snapshot:
                account_name = getattr(snapshot, 'account_name', None)

        # For ROLL/COMPRESS actions, calculate total cost/premium for display
        # net_cost convention: negative = credit, positive = debit
        total_premium = None
        if result.action in ('ROLL', 'COMPRESS') and result.net_cost is not None:
            if result.net_cost < 0:
                total_premium = abs(result.net_cost)  # Credit — show as "Earn"

        # Format title in standard format
        title = self._format_title(
            action=result.action,
            symbol=result.symbol,
            contracts=contracts,
            option_type=option_type,
            source_strike=float(source_strike) if source_strike else None,
            source_expiration=source_expiration,
            target_strike=result.new_strike,
            target_expiration=result.new_expiration,
            total_premium=total_premium
        )

        # For debits, append cost info to title
        if result.action in ('ROLL', 'COMPRESS') and result.net_cost is not None and result.net_cost > 0:
            total_cost = result.net_cost  # already total dollars from evaluator
            title += f" · Cost ~${total_cost:.0f}"

        return {
            'id': result.position_id,
            'symbol': result.symbol,
            'account_name': account_name,  # Include account for grouping
            'action': result.action,
            'action_display': self._format_action_display(result.action),
            'title': title,  # Standard formatted title
            # V4: Rich reasoning
            'reason': result.reason,
            'reason_short': result.reason_short,
            'rationale': result.reason,  # For compatibility with existing UI
            'philosophy': result.philosophy_applied,
            # Follow-up tracking
            'has_follow_up': result.has_follow_up,
            'follow_up_condition': result.follow_up_condition,
            'follow_up_threshold': result.follow_up_threshold,
            'follow_up_action': result.follow_up_action,
            # Position details
            'contracts': contracts,
            'option_type': option_type,
            'source_strike': source_strike,
            'source_expiration': source_expiration,
            # Target (if rolling/compressing)
            'target_strike': result.new_strike,
            'target_expiration': result.new_expiration,
            'net_cost': result.net_cost,
            # V4 metrics
            'intrinsic_pct': result.intrinsic_pct,
            'time_value': result.time_value,
            'escape_weeks': result.escape_weeks,
            'compression_value': result.compression_value,
            'compression_cost': result.compression_cost,
            # Cost basis info
            'cost_basis': result.cost_basis,
            'assignment_acceptable': result.assignment_acceptable,
            # Context
            'context': result.details,
            'snapshot_id': None,  # Will be set after recording
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
        total_premium: float = None
    ) -> str:
        """
        Format notification title in standard format.

        Examples:
        - Roll 17 AAPL $267.5 call 1/30 to $280 call 2/07 · Earn $90
        - Sell 9 NVDA $200 call 1/30 · Earn $315
        - Close 1 MU $350 call 4/17
        - Compress 2 AVGO $360 put 1/30 to weekly
        - Hold 1 TSLA $420 call 2/07
        - Let Expire 1 IBIT $53 call 1/24
        """
        opt_type = option_type.lower() if option_type else 'call'

        # Format dates as M/DD
        def fmt_date(d):
            if d is None:
                return ''
            if isinstance(d, str):
                try:
                    d = datetime.strptime(d, '%Y-%m-%d').date()
                except:
                    return d
            return f"{d.month}/{d.day}"

        # Format strike
        def fmt_strike(s):
            if s is None:
                return ''
            s = float(s)
            if s >= 100:
                return f"${s:.0f}"
            else:
                return f"${s:.2f}"

        # Action verb (capitalize first letter only)
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

        # Build title based on action
        if action == 'ROLL':
            title = f"{action_verb} {contracts} {symbol} {fmt_strike(source_strike)} {opt_type} {fmt_date(source_expiration)} to {fmt_strike(target_strike)} {opt_type} {fmt_date(target_expiration)}"
        elif action == 'COMPRESS':
            # Show actual target for compress (same strike, next week)
            if target_strike and target_expiration:
                title = f"{action_verb} {contracts} {symbol} {fmt_strike(source_strike)} {opt_type} {fmt_date(source_expiration)} to {fmt_strike(target_strike)} {opt_type} {fmt_date(target_expiration)} (weekly)"
            else:
                title = f"{action_verb} {contracts} {symbol} {fmt_strike(source_strike)} {opt_type} {fmt_date(source_expiration)} to weekly"
        elif action == 'CLOSE':
            title = f"{action_verb} {contracts} {symbol} {fmt_strike(source_strike)} {opt_type} {fmt_date(source_expiration)}"
        elif action == 'HOLD':
            title = f"{action_verb} {contracts} {symbol} {fmt_strike(source_strike)} {opt_type} {fmt_date(source_expiration)}"
        elif action == 'LET_EXPIRE':
            title = f"{action_verb} {contracts} {symbol} {fmt_strike(source_strike)} {opt_type} {fmt_date(source_expiration)}"
        elif action == 'SELL':
            # Uncovered position - use target strike/expiration
            title = f"{action_verb} {contracts} {symbol} {fmt_strike(target_strike)} {opt_type} {fmt_date(target_expiration)}"
        elif action in ('WAIT', 'WAIT_FOR_PULLBACK', 'WAIT_FOR_RECOVERY'):
            title = f"{action_verb} on {symbol} ({contracts} uncovered)"
        else:
            title = f"{action_verb} {contracts} {symbol}"

        # Add earnings if available
        if total_premium and total_premium > 0:
            title += f" · Earn ${total_premium:.0f}"

        return title

    def _record_snapshot(
        self,
        result: V4EvaluationResult,
        position: Any
    ) -> Optional[RecommendationSnapshot]:
        """Record V4 evaluation as a snapshot for RLHF tracking."""
        try:
            # Find or create recommendation
            rec = self._get_or_create_recommendation(position)
            if not rec:
                return None

            # Get previous snapshot number
            last_snapshot = self.db.query(RecommendationSnapshot).filter(
                RecommendationSnapshot.recommendation_id == rec.id
            ).order_by(RecommendationSnapshot.snapshot_number.desc()).first()

            snapshot_number = (last_snapshot.snapshot_number + 1) if last_snapshot else 1

            # Create snapshot
            snapshot = RecommendationSnapshot(
                recommendation_id=rec.id,
                snapshot_number=snapshot_number,
                evaluated_at=datetime.utcnow(),  # Required field
                recommended_action=result.action,
                reason=result.reason,
                # V4: No priority (or use 'normal' for all)
                priority='normal',
                # Target info
                target_strike=result.new_strike,
                target_expiration=result.new_expiration,
                net_cost=result.net_cost,
                # V4 context
                full_context={
                    'v4_philosophy': result.philosophy_applied,
                    'reason_short': result.reason_short,
                    'has_follow_up': result.has_follow_up,
                    'follow_up_condition': result.follow_up_condition,
                    'follow_up_threshold': result.follow_up_threshold,
                    'intrinsic_pct': result.intrinsic_pct,
                    'escape_weeks': result.escape_weeks,
                    'compression_value': result.compression_value,
                    'compression_cost': result.compression_cost,
                    **result.details
                },
                created_at=datetime.utcnow(),
            )

            # V4: Always send notification (no suppression)
            snapshot.notification_decision = 'sent_v4'

            # Update recommendation's total_snapshots counter
            rec.total_snapshots = snapshot_number
            rec.last_snapshot_at = datetime.utcnow()

            self.db.add(snapshot)
            self.db.commit()

            # If this result has a follow-up condition, create it
            if result.has_follow_up and result.follow_up_condition:
                # Get current price for reference
                try:
                    indicators = self.evaluator.ta_service.get_technical_indicators(position.symbol)
                    if indicators:
                        self.create_follow_up_condition(
                            result=result,
                            recommendation=rec,
                            snapshot=snapshot,
                            current_price=indicators.current_price
                        )
                except Exception as e:
                    logger.warning(f"Could not create follow-up condition: {e}")

            return snapshot

        except Exception as e:
            logger.error(f"Error recording V4 snapshot: {e}", exc_info=True)
            self.db.rollback()
            return None

    def _get_or_create_recommendation(
        self,
        position: Any
    ) -> Optional[PositionRecommendation]:
        """Get or create a PositionRecommendation for this position."""
        try:
            from app.modules.strategies.recommendation_models import generate_recommendation_id

            symbol = position.symbol
            strike = getattr(position, 'strike_price', 0)
            expiration = getattr(position, 'expiration_date', date.today())
            # Normalize option_type to lowercase to prevent duplicates
            option_type = (getattr(position, 'option_type', 'call') or 'call').lower()
            # Account name is in the snapshot relationship, not directly on the position
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

            # Try to find existing ACTIVE recommendation
            # If we find a superseded/resolved one, reactivate it instead of creating a new one
            rec = self.db.query(PositionRecommendation).filter(
                PositionRecommendation.recommendation_id == rec_id
            ).first()

            if rec and rec.status != 'active':
                # Reactivate the existing recommendation
                logger.info(f"Reactivating {rec.status} recommendation for {symbol} {strike} {expiration}")
                rec.status = 'active'
                rec.last_snapshot_at = datetime.utcnow()
                self.db.commit()

            if not rec:
                # Create new
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
        """
        Mark recommendations as superseded if the underlying position no longer exists.

        This prevents stale recommendations from appearing in notifications when:
        - Options expire and are replaced with new strikes
        - User closes a position
        - Data refresh brings in different positions

        Args:
            current_positions: List of currently open SoldOption positions

        Returns:
            Number of recommendations marked as superseded
        """
        try:
            # Build set of current position keys (symbol, strike, expiration, option_type)
            current_keys = set()
            for pos in current_positions:
                symbol = pos.symbol
                strike = float(pos.strike_price) if pos.strike_price else None
                exp = pos.expiration_date
                opt_type = (getattr(pos, 'option_type', 'call') or 'call').lower()

                # Create a key that matches the recommendation_id format
                if strike and exp:
                    key = (symbol, strike, exp, opt_type)
                    current_keys.add(key)

            # Get all active sold_option recommendations
            active_recs = self.db.query(PositionRecommendation).filter(
                PositionRecommendation.status == 'active',
                PositionRecommendation.position_type == 'sold_option'
            ).all()

            superseded_count = 0
            now = datetime.utcnow()

            for rec in active_recs:
                # Build key for this recommendation
                rec_key = (
                    rec.symbol,
                    float(rec.source_strike) if rec.source_strike else None,
                    rec.source_expiration,
                    (rec.option_type or 'call').lower()
                )

                # If this recommendation's position is not in current positions, mark superseded
                if rec_key not in current_keys:
                    rec.status = 'superseded'
                    rec.resolution_type = 'position_closed'
                    rec.resolution_notes = 'Position no longer in active holdings'
                    rec.resolved_at = now
                    superseded_count += 1
                    logger.debug(f"[V4] Marking {rec.symbol} {rec.source_strike} as superseded")

            if superseded_count > 0:
                self.db.commit()
                logger.info(f"[V4] Marked {superseded_count} stale recommendations as superseded")

            return superseded_count

        except Exception as e:
            logger.error(f"[V4] Error cleaning up stale recommendations: {e}", exc_info=True)
            self.db.rollback()
            return 0

    def format_telegram_message(
        self,
        notifications: List[Dict[str, Any]],
        include_reasoning: bool = False
    ) -> str:
        """
        Format notifications for Telegram.

        V4: Concise format for mobile, reasoning available in web app.

        Args:
            notifications: List of notification items
            include_reasoning: Whether to include full reasoning (default False for mobile)
        """
        if not notifications:
            return ""

        lines = ["📢 *V4 Options Update*", ""]

        # Account ordering - Neel's first, then Jaya's, then others
        ACCOUNT_ORDER = {
            "Neel's Brokerage": 1, "Neel's Retirement": 2, "Neel's Roth IRA": 3,
            "Jaya's Brokerage": 4, "Jaya's IRA": 5, "Jaya's Roth IRA": 6,
            "Alisha's Brokerage": 7, "Agrawal Family HSA": 8,
        }

        # Group by account (if available)
        by_account: Dict[str, List] = {}
        for notif in notifications:
            account = notif.get('context', {}).get('account_name') or 'Portfolio'
            if account not in by_account:
                by_account[account] = []
            by_account[account].append(notif)

        # Sort accounts by defined order
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

                # Format line based on notification type
                if is_uncovered and action in ('SELL', 'WAIT'):
                    # Uncovered position notification
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
                    # Existing position notification
                    if target_strike and action == 'ROLL':
                        line = f"• {action}: {symbol} ${source_strike:.0f}→${target_strike:.0f} {option_type}"
                    else:
                        line = f"• {action}: {symbol} ${source_strike:.0f} {option_type}"
                else:
                    line = f"• {action}: {symbol}"

                # Add stock price if available
                if stock_price and not is_uncovered:
                    line += f" · ${stock_price:.0f}"

                # Add follow-up indicator
                if item.get('has_follow_up'):
                    line += " 🔄"

                # Add follow-up tag
                if item.get('is_follow_up'):
                    line = f"• 🔔 FOLLOW-UP: {symbol}"

                lines.append(line)

                # Add short reason (mobile-friendly)
                if reason_short and len(reason_short) < 80:
                    lines.append(f"  _{reason_short}_")

            lines.append("")

        # Timestamp
        now = datetime.now()
        lines.append(f"_{now.strftime('%I:%M %p')}_")

        return "\n".join(lines)

    def create_follow_up_condition(
        self,
        result: V4EvaluationResult,
        recommendation: PositionRecommendation,
        snapshot: RecommendationSnapshot,
        current_price: float
    ) -> Optional[FollowUpCondition]:
        """
        Create a follow-up condition when V4 sets one.

        Called when result.has_follow_up is True.
        """
        if not result.has_follow_up:
            return None

        try:
            # Check if condition already exists for this recommendation
            existing = self.db.query(FollowUpCondition).filter(
                FollowUpCondition.recommendation_id == recommendation.id,
                FollowUpCondition.is_active == True,
                FollowUpCondition.condition_type == result.follow_up_condition
            ).first()

            if existing:
                # Update reference price if condition already exists
                existing.reference_price = Decimal(str(current_price))
                existing.reference_date = datetime.utcnow()
                self.db.commit()
                return existing

            # Create new follow-up condition
            condition = FollowUpCondition(
                recommendation_id=recommendation.id,
                snapshot_id=snapshot.id,
                symbol=result.symbol,
                account_name=recommendation.account_name,
                condition_type=result.follow_up_condition,
                threshold_pct=Decimal(str(result.follow_up_threshold)) if result.follow_up_threshold else None,
                reference_price=Decimal(str(current_price)),
                reference_date=datetime.utcnow(),
                follow_up_action=result.follow_up_action,
                is_active=True,
                # Conditions expire after 30 days by default
                expires_at=datetime.utcnow() + timedelta(days=30),
            )

            self.db.add(condition)
            self.db.commit()

            logger.info(
                f"[V4] Created follow-up condition for {result.symbol}: "
                f"{result.follow_up_condition} @ ${current_price:.2f}"
            )

            return condition

        except Exception as e:
            logger.error(f"Error creating follow-up condition: {e}", exc_info=True)
            self.db.rollback()
            return None

    def get_active_follow_up_conditions(self) -> List[FollowUpCondition]:
        """Get all active (non-triggered, non-expired) follow-up conditions."""
        return self.db.query(FollowUpCondition).filter(
            FollowUpCondition.is_active == True,
            FollowUpCondition.expired == False,
            FollowUpCondition.triggered_at.is_(None)
        ).all()

    def check_follow_up_conditions(self) -> List[Dict[str, Any]]:
        """
        Check if any follow-up conditions have been met.

        Called on each scan to check if conditions have triggered.
        Returns list of triggered follow-ups ready for notification.
        """
        conditions = self.get_active_follow_up_conditions()
        triggered = []
        now = datetime.utcnow()

        for condition in conditions:
            try:
                # Check if expired
                if condition.expires_at and condition.expires_at < now:
                    condition.expired = True
                    condition.is_active = False
                    continue

                # Get current price
                indicators = self.evaluator.ta_service.get_technical_indicators(condition.symbol)
                if not indicators:
                    continue

                current_price = indicators.current_price
                reference_price = float(condition.reference_price)
                threshold = float(condition.threshold_pct) if condition.threshold_pct else 0.03

                # Check condition based on type
                condition_met = False
                price_change_pct = (current_price - reference_price) / reference_price

                if condition.condition_type in ['stock_drops_3_pct', 'stock_drops']:
                    # Stock dropped by threshold %
                    condition_met = price_change_pct <= -threshold

                elif condition.condition_type in ['stock_bounces', 'stock_recovers']:
                    # Stock bounced/recovered by threshold %
                    condition_met = price_change_pct >= threshold

                elif condition.condition_type in ['stock_pulls_back', 'stock_pulls_back_2_pct']:
                    # Stock pulled back by threshold % (for selling new calls)
                    condition_met = price_change_pct <= -threshold

                if condition_met:
                    # Trigger the condition
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
                        f"[V4] Follow-up triggered for {condition.symbol}: "
                        f"{condition.condition_type} ({price_change_pct*100:.1f}% change)"
                    )

            except Exception as e:
                logger.warning(f"Error checking condition for {condition.symbol}: {e}")

        self.db.commit()
        return triggered

    def generate_follow_up_notifications(
        self,
        triggered: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Generate notifications for triggered follow-up conditions.

        These are the "Part 2" notifications of two-part recommendations.
        """
        notifications = []

        for trigger in triggered:
            condition = trigger['condition']
            symbol = trigger['symbol']
            action = trigger['follow_up_action']
            ref_price = trigger['reference_price']
            trigger_price = trigger['trigger_price']
            change_pct = trigger['price_change_pct']

            # Build notification
            if action == 'RE_ENTER':
                reason = (
                    f"**Re-Entry Opportunity**: {symbol} has dropped {abs(change_pct)*100:.1f}% "
                    f"from ${ref_price:.2f} to ${trigger_price:.2f}.\n\n"
                    f"V4 Philosophy: Tactical timing - the stock has pulled back as expected. "
                    f"Consider selling a new covered call at this lower price."
                )
                reason_short = f"{symbol} dropped {abs(change_pct)*100:.0f}% - re-entry time"

            elif action == 'SELL_NEW':
                reason = (
                    f"**Sell New Option**: {symbol} has pulled back {abs(change_pct)*100:.1f}% "
                    f"to ${trigger_price:.2f}.\n\n"
                    f"V4 Philosophy: After closing early, wait for pullback before selling new. "
                    f"Pullback achieved - good time to sell new option."
                )
                reason_short = f"{symbol} pulled back {abs(change_pct)*100:.0f}% - sell new option"

            else:
                reason = f"Follow-up condition met for {symbol}: {action}"
                reason_short = f"{symbol} follow-up: {action}"

            notif = {
                'id': f"followup_{condition.id}",
                'symbol': symbol,
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
                'context': {
                    'account_name': trigger.get('account_name'),
                    'condition_id': condition.id,
                },
            }

            notifications.append(notif)

            # Mark condition as notified
            condition.follow_up_notification_sent = True
            condition.follow_up_notification_at = datetime.utcnow()

        self.db.commit()
        return notifications


def get_v4_notification_service(db: Session) -> V4NotificationService:
    """Factory function to get V4 notification service."""
    return V4NotificationService(db)
