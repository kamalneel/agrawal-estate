"""
V5 Pending Order Evaluator

Evaluates pending orders (limit orders waiting to be filled) against current market
conditions and V5 recommendations to advise:

1. KEEP - Pending order is still a good idea, wait for fill
2. MODIFY_UP - Increase limit price to get filled faster (give up some credit)
3. MODIFY_DOWN - Decrease limit price for more credit (may take longer to fill)
4. CANCEL - Market conditions changed significantly, cancel the order
5. REPLACE - Replace with a different roll (different expiration/strike)

Use Cases:
- User has pending roll order → V5 would have recommended same action → KEEP
- User has pending roll order → V5 recommends different action → REPLACE/CANCEL
- User has pending roll order at $3.00 → market moved, $2.80 more realistic → MODIFY_DOWN
- User has urgent position → pending order at $3.00 but market at $2.50 → MODIFY_UP
"""

from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
import logging

from sqlalchemy.orm import Session
from app.modules.strategies.models import PendingOrder, SoldOption

logger = logging.getLogger(__name__)


@dataclass
class PendingOrderAdvice:
    """Advice for a pending order."""
    order_id: int
    symbol: str
    current_order: Dict[str, Any]  # Details of the pending order

    # Recommendation
    action: str  # KEEP, MODIFY_UP, MODIFY_DOWN, CANCEL, REPLACE
    reason: str
    reason_short: str

    # For MODIFY actions
    suggested_limit: Optional[float] = None

    # For REPLACE actions
    suggested_expiration: Optional[date] = None
    suggested_strike: Optional[float] = None

    # Market context
    current_market_bid: Optional[float] = None
    urgency_level: str = "normal"  # normal, high, critical


class V5PendingOrderEvaluator:
    """
    Evaluates pending orders against V5 recommendations and market conditions.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_pending_orders_for_snapshot(self, snapshot_id: int) -> List[PendingOrder]:
        """Get all pending orders for a snapshot."""
        return self.db.query(PendingOrder).filter(
            PendingOrder.snapshot_id == snapshot_id,
            PendingOrder.status == 'pending'
        ).all()

    def find_matching_pending_order(
        self,
        symbol: str,
        option_type: str,
        strike: float,
        expiration: date,
        snapshot_id: int
    ) -> Optional[PendingOrder]:
        """
        Find a pending order that matches a position.

        For ROLL orders, we match by:
        - symbol
        - option_type
        - from_expiration (current position's expiration)

        The to_expiration and strike may differ (that's what we're rolling to).
        """
        pending_orders = self.get_pending_orders_for_snapshot(snapshot_id)

        for order in pending_orders:
            if order.symbol.upper() == symbol.upper():
                if order.option_type and order.option_type.lower() == option_type.lower():
                    # For ROLL orders, from_expiration should match position's expiration
                    if order.order_type == 'ROLL' and order.from_expiration:
                        if order.from_expiration == expiration:
                            return order
                    # For BUY_TO_CLOSE, to_expiration should match
                    elif order.order_type == 'BUY_TO_CLOSE' and order.to_expiration:
                        if order.to_expiration == expiration:
                            # Check strike if specified
                            if order.strike_price is None or float(order.strike_price) == strike:
                                return order

        return None

    def evaluate_pending_order(
        self,
        pending_order: PendingOrder,
        v5_recommendation: Dict[str, Any],
        market_data: Dict[str, Any]
    ) -> PendingOrderAdvice:
        """
        Evaluate a pending order against V5 recommendation and market conditions.

        Args:
            pending_order: The pending order from database
            v5_recommendation: What V5 would recommend for this position
            market_data: Current market data including bid/ask for the option

        Returns:
            PendingOrderAdvice with recommended action
        """
        symbol = pending_order.symbol
        order_type = pending_order.order_type
        limit_price = float(pending_order.limit_price) if pending_order.limit_price else None

        v5_action = v5_recommendation.get('action', 'UNKNOWN')
        days_to_exp = v5_recommendation.get('days_to_exp', 99)

        # Get current market bid for the spread/roll
        current_bid = market_data.get('current_bid')
        current_ask = market_data.get('current_ask')
        urgency = self._calculate_urgency(days_to_exp, v5_recommendation)

        current_order = {
            'order_type': order_type,
            'from_expiration': str(pending_order.from_expiration) if pending_order.from_expiration else None,
            'to_expiration': str(pending_order.to_expiration) if pending_order.to_expiration else None,
            'strike_price': float(pending_order.strike_price) if pending_order.strike_price else None,
            'limit_price': limit_price,
            'contracts': pending_order.contracts,
        }

        # Case 1: V5 says CLOSE but user has ROLL order → might want to CANCEL
        if v5_action == 'CLOSE' and order_type == 'ROLL':
            return PendingOrderAdvice(
                order_id=pending_order.id,
                symbol=symbol,
                current_order=current_order,
                action='REPLACE',
                reason=(
                    f"V5 recommends CLOSE (early profit capture or time decay captured). "
                    f"Your pending ROLL order should be replaced with a BUY_TO_CLOSE."
                ),
                reason_short="V5 says CLOSE, not ROLL",
                current_market_bid=current_bid,
                urgency_level=urgency
            )

        # Case 2: V5 says HOLD but user has ROLL order → CANCEL
        if v5_action == 'HOLD' and order_type == 'ROLL':
            return PendingOrderAdvice(
                order_id=pending_order.id,
                symbol=symbol,
                current_order=current_order,
                action='CANCEL',
                reason=(
                    f"V5 recommends HOLD (position is healthy, no action needed). "
                    f"Consider canceling the pending roll order."
                ),
                reason_short="V5 says HOLD, no roll needed",
                current_market_bid=current_bid,
                urgency_level=urgency
            )

        # Case 3: V5 says ROLL (same as pending) → check limit price
        if v5_action in ('ROLL', 'ROLL_BIWEEKLY', 'ROLL_MONTHLY') and order_type == 'ROLL':
            # Check if the roll target matches
            v5_exp = v5_recommendation.get('new_expiration')
            pending_exp = pending_order.to_expiration

            exp_matches = False
            if v5_exp and pending_exp:
                if isinstance(v5_exp, str):
                    v5_exp = datetime.strptime(v5_exp, '%Y-%m-%d').date()
                exp_matches = v5_exp == pending_exp

            if exp_matches or not v5_exp:
                # Same roll target, check limit price
                return self._evaluate_limit_price(
                    pending_order, limit_price, current_bid, current_ask, urgency
                )
            else:
                # Different roll target
                return PendingOrderAdvice(
                    order_id=pending_order.id,
                    symbol=symbol,
                    current_order=current_order,
                    action='REPLACE',
                    reason=(
                        f"V5 recommends rolling to {v5_exp}, but your pending order "
                        f"targets {pending_exp}. Consider replacing with the new target."
                    ),
                    reason_short=f"Different target: V5 says {v5_exp}",
                    suggested_expiration=v5_exp,
                    suggested_strike=v5_recommendation.get('new_strike'),
                    current_market_bid=current_bid,
                    urgency_level=urgency
                )

        # Case 4: V5 says COMPRESS but user has regular ROLL → check if same direction
        if v5_action == 'COMPRESS' and order_type == 'ROLL':
            # Compression is a specific type of roll (shorter duration)
            # If the pending roll is already compressing, KEEP it
            pending_exp = pending_order.to_expiration
            current_exp = pending_order.from_expiration

            if pending_exp and current_exp and pending_exp < current_exp:
                # User is already compressing! This is good.
                return self._evaluate_limit_price(
                    pending_order, limit_price, current_bid, current_ask, urgency
                )
            else:
                # User is rolling out (longer duration), but V5 says compress
                return PendingOrderAdvice(
                    order_id=pending_order.id,
                    symbol=symbol,
                    current_order=current_order,
                    action='REPLACE',
                    reason=(
                        f"V5 recommends COMPRESS (shorter duration) to escape stuck position. "
                        f"Your pending roll is extending duration. Consider compressing instead."
                    ),
                    reason_short="V5 says COMPRESS, not extend",
                    suggested_expiration=v5_recommendation.get('new_expiration'),
                    suggested_strike=v5_recommendation.get('new_strike'),
                    current_market_bid=current_bid,
                    urgency_level=urgency
                )

        # Default: KEEP the pending order
        return PendingOrderAdvice(
            order_id=pending_order.id,
            symbol=symbol,
            current_order=current_order,
            action='KEEP',
            reason="Pending order aligns with current market conditions.",
            reason_short="Order looks good",
            current_market_bid=current_bid,
            urgency_level=urgency
        )

    def _evaluate_limit_price(
        self,
        pending_order: PendingOrder,
        limit_price: Optional[float],
        current_bid: Optional[float],
        current_ask: Optional[float],
        urgency: str
    ) -> PendingOrderAdvice:
        """Evaluate if the limit price should be modified."""
        symbol = pending_order.symbol

        current_order = {
            'order_type': pending_order.order_type,
            'from_expiration': str(pending_order.from_expiration) if pending_order.from_expiration else None,
            'to_expiration': str(pending_order.to_expiration) if pending_order.to_expiration else None,
            'strike_price': float(pending_order.strike_price) if pending_order.strike_price else None,
            'limit_price': limit_price,
            'contracts': pending_order.contracts,
        }

        if limit_price is None or current_bid is None:
            return PendingOrderAdvice(
                order_id=pending_order.id,
                symbol=symbol,
                current_order=current_order,
                action='KEEP',
                reason="Cannot evaluate limit price without market data. Order looks OK.",
                reason_short="Keep (no market data)",
                urgency_level=urgency
            )

        # For credit spreads/rolls, higher limit = more credit for us
        # Market bid is what we can get filled at immediately
        price_gap = limit_price - current_bid
        price_gap_pct = (price_gap / current_bid * 100) if current_bid > 0 else 0

        if urgency == 'critical' and price_gap > 0.10:
            # Position expires soon, need to get filled!
            suggested = round(current_bid + 0.05, 2)  # Just above bid
            return PendingOrderAdvice(
                order_id=pending_order.id,
                symbol=symbol,
                current_order=current_order,
                action='MODIFY_DOWN',
                reason=(
                    f"URGENT: Position expires soon! Your limit ${limit_price:.2f} is "
                    f"${price_gap:.2f} above market bid ${current_bid:.2f}. "
                    f"Lower to ${suggested:.2f} to get filled."
                ),
                reason_short=f"URGENT: Lower to ${suggested:.2f}",
                suggested_limit=suggested,
                current_market_bid=current_bid,
                urgency_level=urgency
            )

        if urgency == 'high' and price_gap > 0.25:
            # Approaching expiration
            suggested = round(current_bid + 0.10, 2)
            return PendingOrderAdvice(
                order_id=pending_order.id,
                symbol=symbol,
                current_order=current_order,
                action='MODIFY_DOWN',
                reason=(
                    f"Position approaching expiration. Your limit ${limit_price:.2f} is "
                    f"${price_gap:.2f} above market bid ${current_bid:.2f}. "
                    f"Consider lowering to ${suggested:.2f}."
                ),
                reason_short=f"Lower to ${suggested:.2f}",
                suggested_limit=suggested,
                current_market_bid=current_bid,
                urgency_level=urgency
            )

        # Not urgent - check if we're leaving money on table
        if current_bid > limit_price + 0.10:
            # Market moved in our favor! We could get MORE credit
            suggested = round(current_bid - 0.05, 2)
            return PendingOrderAdvice(
                order_id=pending_order.id,
                symbol=symbol,
                current_order=current_order,
                action='MODIFY_UP',
                reason=(
                    f"Market moved in your favor! Current bid ${current_bid:.2f} is "
                    f"above your limit ${limit_price:.2f}. "
                    f"Consider raising to ${suggested:.2f} for more credit."
                ),
                reason_short=f"Raise to ${suggested:.2f} for more credit",
                suggested_limit=suggested,
                current_market_bid=current_bid,
                urgency_level=urgency
            )

        # Price is reasonable, KEEP
        return PendingOrderAdvice(
            order_id=pending_order.id,
            symbol=symbol,
            current_order=current_order,
            action='KEEP',
            reason=(
                f"Your limit ${limit_price:.2f} is close to market bid ${current_bid:.2f}. "
                f"Order should fill soon."
            ),
            reason_short="Good limit, wait for fill",
            current_market_bid=current_bid,
            urgency_level=urgency
        )

    def _calculate_urgency(self, days_to_exp: int, v5_rec: Dict[str, Any]) -> str:
        """Calculate urgency level based on time to expiration."""
        if days_to_exp <= 1:
            return 'critical'
        elif days_to_exp <= 3:
            return 'high'
        else:
            return 'normal'

    def should_skip_v5_notification(
        self,
        symbol: str,
        option_type: str,
        strike: float,
        expiration: date,
        snapshot_id: int,
        v5_action: str
    ) -> Tuple[bool, Optional[PendingOrder]]:
        """
        Check if we should skip the V5 notification because user already has
        a pending order that accomplishes the same goal.

        Returns:
            (should_skip, pending_order) - True if should skip, with the matching order
        """
        pending_order = self.find_matching_pending_order(
            symbol, option_type, strike, expiration, snapshot_id
        )

        if not pending_order:
            return (False, None)

        # Check if pending order aligns with V5 recommendation
        if v5_action in ('ROLL', 'ROLL_BIWEEKLY', 'ROLL_MONTHLY'):
            if pending_order.order_type == 'ROLL':
                # User already has a roll pending - skip V5 "roll" notification
                # Instead, we'll send a pending order advice notification
                return (True, pending_order)

        if v5_action == 'CLOSE':
            if pending_order.order_type == 'BUY_TO_CLOSE':
                # User already closing position
                return (True, pending_order)

        if v5_action == 'COMPRESS':
            # Check if pending roll is a compression (to shorter expiration)
            if pending_order.order_type == 'ROLL':
                if pending_order.to_expiration and pending_order.from_expiration:
                    if pending_order.to_expiration < pending_order.from_expiration:
                        # It's a compression roll
                        return (True, pending_order)

        return (False, pending_order)
