"""
V5 Engine 4: Underwater Position Management

Handles ITM positions through LIFE_SUPPORT, DROWNING, compression, and roll logic.

Categories:
- HEALTHY: <5% ITM, standard handling
- STUCK: 5-17% ITM (medium IV), weekly rolls still yield credit
- LIFE_SUPPORT: 17-22% ITM (medium IV), weekly debit but biweekly/monthly credit
- DROWNING: >22% ITM (medium IV), all rolls are debits → CLOSE

V5 Philosophy:
- Mean reversion is inevitable
- When weekly fails, extend duration to maintain credit (LIFE_SUPPORT)
- Zero-cost compression = iterative path out of stuck positions
- DROWNING = take loss immediately, stop the bleeding
"""

import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, date, timedelta
from decimal import Decimal

from app.modules.strategies.v5.base import (
    V5EvaluationResult,
    LIFE_SUPPORT_THRESHOLDS,
    get_v5_config,
    calculate_intrinsic_time_value,
    get_iv_category,
    get_stuck_category,
    calculate_escape_strike,
    estimate_roll_credits,
)

logger = logging.getLogger(__name__)


class UnderwaterEngine:
    """
    Engine 4: Underwater position management.

    Handles all ITM-specific logic: LIFE_SUPPORT rolls, DROWNING detection,
    zero-cost compression, and standard ITM evaluation.
    """

    def __init__(self, ta_service, option_fetcher, db=None):
        self.ta_service = ta_service
        self.option_fetcher = option_fetcher
        self.db = db
        self.config = get_v5_config()

    def evaluate(
        self,
        position,
        is_itm: bool,
        itm_pct: float,
        intrinsic_pct: float,
        intrinsic_value: float,
        time_value: float,
        current_price: float,
        current_premium: float,
        profit_pct: float,
        days_to_exp: int,
        weekly_income: Optional[float] = None,
        cost_basis: Optional[float] = None
    ) -> Optional[V5EvaluationResult]:
        """
        Evaluate an ITM position.

        Called by the orchestrator/evaluator when a position is ITM and has passed
        the time cushion and early profit checks.

        Returns V5EvaluationResult or None if this engine can't handle it.
        """
        if not is_itm:
            return None

        # Step 1: LIFE_SUPPORT check
        life_support_result = self._handle_life_support(
            position, itm_pct, intrinsic_pct, intrinsic_value, time_value,
            current_price, current_premium, days_to_exp, weekly_income
        )
        if life_support_result:
            return life_support_result

        # Step 2: Zero-cost compression for long-dated ITM
        if days_to_exp > 30:
            compression_result = self._check_zero_cost_compression(
                position, current_price, current_premium, days_to_exp,
                itm_pct, intrinsic_pct
            )
            if compression_result:
                return compression_result

        # Step 3: DROWNING check
        iv_category = get_iv_category(position.symbol)
        stuck_category = get_stuck_category(itm_pct, iv_category)
        if stuck_category == "DROWNING":
            drowning_result = self._handle_drowning(
                position, itm_pct, iv_category, current_price, current_premium,
                days_to_exp, intrinsic_pct, time_value
            )
            if drowning_result:
                return drowning_result

        # Step 4: Standard ITM handling
        return self._handle_itm_position(
            position, is_itm, itm_pct, intrinsic_pct, intrinsic_value, time_value,
            current_price, current_premium, profit_pct, days_to_exp,
            weekly_income, cost_basis
        )

    def evaluate_time_cushion_itm(
        self,
        position,
        is_itm: bool,
        itm_pct: float,
        intrinsic_pct: float,
        current_price: float,
        current_premium: float
    ) -> V5EvaluationResult:
        """
        Handle ITM positions with <=2 days to expiry (time cushion).

        V5 Philosophy: Roll at SAME STRIKE, extend time.
        """
        min_days = self.config['time_cushion']['min_days_to_expiry']
        strike = float(position.strike_price) if position.strike_price else 0.0
        option_type = getattr(position, 'option_type', 'call')
        contracts = getattr(position, 'contracts_sold', 1) or 1

        today = date.today()
        days_to_friday = (4 - today.weekday()) % 7
        if days_to_friday == 0:
            days_to_friday = 7
        next_friday = today + timedelta(days=days_to_friday)
        biweekly_exp = next_friday + timedelta(days=7)
        monthly_exp = next_friday + timedelta(days=21)

        weekly_credit, biweekly_credit, monthly_credit = estimate_roll_credits(
            position, current_price, current_premium, self.option_fetcher
        )

        # Pick shortest duration that yields credit
        if weekly_credit >= 0:
            new_exp = next_friday
            roll_credit = weekly_credit
            roll_type = "weekly"
            action = 'ROLL'
        elif biweekly_credit > 0:
            new_exp = biweekly_exp
            roll_credit = biweekly_credit
            roll_type = "bi-weekly"
            action = 'ROLL_BIWEEKLY'
        elif monthly_credit > 0:
            new_exp = monthly_exp
            roll_credit = monthly_credit
            roll_type = "monthly"
            action = 'ROLL_MONTHLY'
        else:
            new_exp = next_friday
            roll_credit = weekly_credit
            roll_type = "weekly"
            action = 'ROLL'

        total_credit = roll_credit * contracts * 100
        credit_or_cost = "Credit" if roll_credit >= 0 else "Cost"

        reason = (
            f"**Time Cushion Alert**: Position expires in ≤{min_days} days and is ITM ({itm_pct:.1f}%).\n\n"
            f"V5 Philosophy: Roll at SAME STRIKE to extend time. Mean reversion will help - just need time.\n"
            f"Stock: ${current_price:.2f} | Strike: ${strike:.0f} (keeping same)\n\n"
            f"Roll ${strike:.0f} {option_type} to {new_exp.strftime('%m/%d')} ({roll_type}) · "
            f"{credit_or_cost} ~${abs(total_credit):.0f}"
        )
        reason_short = f"Time cushion - roll {option_type} ${strike:.0f} to {new_exp.strftime('%m/%d')} ({roll_type})"

        return V5EvaluationResult(
            action=action,
            position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
            symbol=position.symbol,
            reason=reason,
            reason_short=reason_short,
            philosophy_applied='same_strike_time_extension',
            new_strike=strike,
            new_expiration=new_exp,
            net_cost=-total_credit if roll_credit >= 0 else abs(total_credit),
            weekly_credit=weekly_credit,
            biweekly_credit=biweekly_credit,
            monthly_credit=monthly_credit,
            details={
                'days_to_exp': min_days,
                'is_itm': is_itm,
                'itm_pct': itm_pct,
                'trigger': 'time_cushion_v5',
                'roll_type': roll_type,
                'weekly_credit': weekly_credit,
                'biweekly_credit': biweekly_credit,
                'monthly_credit': monthly_credit,
                'current_price': current_price,
                'escape_applied': False
            },
            intrinsic_pct=intrinsic_pct
        )

    def _handle_life_support(
        self,
        position,
        itm_pct: float,
        intrinsic_pct: float,
        intrinsic_value: float,
        time_value: float,
        current_price: float,
        current_premium: float,
        days_to_exp: int,
        weekly_income: Optional[float]
    ) -> Optional[V5EvaluationResult]:
        """
        Handle LIFE_SUPPORT category positions.

        LIFE_SUPPORT = weekly roll yields $0/debit, but bi-weekly/monthly still credit.
        """
        if not self.config.get('life_support', {}).get('enabled', True):
            return None

        iv_category = get_iv_category(position.symbol)
        stuck_category = get_stuck_category(itm_pct, iv_category)

        if stuck_category != "LIFE_SUPPORT":
            return None

        max_days_for_life_support = self.config.get('life_support', {}).get('max_days_to_exp', 14)
        if days_to_exp > max_days_for_life_support:
            return None

        weekly_credit, biweekly_credit, monthly_credit = estimate_roll_credits(
            position, current_price, current_premium, self.option_fetcher
        )

        strike = float(position.strike_price) if position.strike_price else 0.0
        option_type = getattr(position, 'option_type', 'call')
        contracts = getattr(position, 'contracts_sold', 1) or 1

        today = date.today()
        days_to_friday = (4 - today.weekday()) % 7
        if days_to_friday == 0:
            days_to_friday = 7

        next_friday = today + timedelta(days=days_to_friday)
        biweekly_expiration = next_friday + timedelta(days=7)
        monthly_expiration = next_friday + timedelta(days=21)

        if weekly_credit >= 0:
            return None  # Weekly still yields credit - use normal handling

        elif biweekly_credit > 0:
            total_credit = biweekly_credit * contracts * 100

            reason = (
                f"**LIFE_SUPPORT - Roll to Bi-Weekly**: {position.symbol} is {itm_pct:.1f}% ITM.\n\n"
                f"Weekly roll would cost ${abs(weekly_credit):.2f}/share (debit), "
                f"but bi-weekly yields ${biweekly_credit:.2f}/share credit.\n\n"
                f"V5 Philosophy: Extend duration to maintain income while waiting for mean reversion.\n\n"
                f"Roll ${strike:.0f} {option_type} to ${strike:.0f} {biweekly_expiration.strftime('%m/%d')} · "
                f"Credit ${total_credit:.0f}"
            )
            reason_short = f"LIFE_SUPPORT: Roll to 2wk for ${total_credit:.0f} credit"

            return V5EvaluationResult(
                action='ROLL_BIWEEKLY',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='life_support_extension',
                stuck_category='LIFE_SUPPORT',
                iv_category=iv_category,
                weekly_credit=weekly_credit,
                biweekly_credit=biweekly_credit,
                monthly_credit=monthly_credit,
                new_strike=strike,
                new_expiration=biweekly_expiration,
                net_cost=-total_credit,
                details={
                    'itm_pct': itm_pct,
                    'trigger': 'life_support_biweekly',
                    'weekly_credit': weekly_credit,
                    'biweekly_credit': biweekly_credit,
                    'monthly_credit': monthly_credit,
                    'current_price': current_price,
                    'days_to_exp': days_to_exp,
                },
                intrinsic_pct=intrinsic_pct,
                time_value=time_value
            )

        elif monthly_credit > 0:
            total_credit = monthly_credit * contracts * 100

            reason = (
                f"**LIFE_SUPPORT - Roll to Monthly**: {position.symbol} is {itm_pct:.1f}% ITM.\n\n"
                f"Weekly: ${weekly_credit:.2f} (debit) | Bi-weekly: ${biweekly_credit:.2f} (debit)\n"
                f"Monthly yields ${monthly_credit:.2f}/share credit.\n\n"
                f"V5 Philosophy: Extend duration to maintain income while waiting for mean reversion.\n\n"
                f"Roll ${strike:.0f} {option_type} to ${strike:.0f} {monthly_expiration.strftime('%m/%d')} · "
                f"Credit ${total_credit:.0f}"
            )
            reason_short = f"LIFE_SUPPORT: Roll to 4wk for ${total_credit:.0f} credit"

            return V5EvaluationResult(
                action='ROLL_MONTHLY',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='life_support_extension',
                stuck_category='LIFE_SUPPORT',
                iv_category=iv_category,
                weekly_credit=weekly_credit,
                biweekly_credit=biweekly_credit,
                monthly_credit=monthly_credit,
                new_strike=strike,
                new_expiration=monthly_expiration,
                net_cost=-total_credit,
                details={
                    'itm_pct': itm_pct,
                    'trigger': 'life_support_monthly',
                    'weekly_credit': weekly_credit,
                    'biweekly_credit': biweekly_credit,
                    'monthly_credit': monthly_credit,
                    'current_price': current_price,
                    'days_to_exp': days_to_exp,
                },
                intrinsic_pct=intrinsic_pct,
                time_value=time_value
            )

        else:
            logger.warning(
                f"[V5] {position.symbol} is DROWNING: weekly=${weekly_credit:.2f}, "
                f"biweekly=${biweekly_credit:.2f}, monthly=${monthly_credit:.2f} - all debits"
            )
            return None

    def _handle_drowning(
        self,
        position,
        itm_pct: float,
        iv_category: str,
        current_price: float,
        current_premium: float,
        days_to_exp: int,
        intrinsic_pct: float,
        time_value: float
    ) -> Optional[V5EvaluationResult]:
        """
        Handle DROWNING positions - ALL rolls are debits.

        Verifies with live roll credits before recommending CLOSE.
        """
        strike = float(position.strike_price) if position.strike_price else 0.0
        option_type = getattr(position, 'option_type', 'call')
        contracts = getattr(position, 'contracts_sold', 1) or 1

        weekly_credit, biweekly_credit, monthly_credit = estimate_roll_credits(
            position, current_price, current_premium, self.option_fetcher
        )

        if weekly_credit > 0 or biweekly_credit > 0 or monthly_credit > 0:
            logger.info(
                f"[V5] {position.symbol} categorized as DROWNING by ITM% but still has credit rolls: "
                f"weekly=${weekly_credit:.2f}, biweekly=${biweekly_credit:.2f}, monthly=${monthly_credit:.2f} - "
                f"falling through to ITM handling"
            )
            return None

        cost_to_close = current_premium * contracts * 100

        original_premium_raw = getattr(position, 'original_premium', None)
        original_premium = float(original_premium_raw) if original_premium_raw else 0.0
        original_total = original_premium * contracts * 100
        estimated_loss = cost_to_close - original_total

        reason = (
            f"**DROWNING - CLOSE Position**: {position.symbol} is {itm_pct:.1f}% ITM "
            f"({iv_category.replace('_', ' ')}).\n\n"
            f"**All rolls require a debit** - weekly, bi-weekly, AND monthly.\n"
            f"- Weekly: ${weekly_credit:.2f}/share (debit)\n"
            f"- Bi-weekly: ${biweekly_credit:.2f}/share (debit)\n"
            f"- Monthly: ${monthly_credit:.2f}/share (debit)\n\n"
            f"Every roll costs money to maintain this position.\n\n"
            f"V5 Philosophy: When you can't roll for ANY credit, take the loss and restart.\n"
            f"Stock: ${current_price:.2f} | Strike: ${strike:.0f}\n"
            f"Cost to close: ~${cost_to_close:.0f}"
        )

        if estimated_loss > 0:
            reason += f" | Estimated loss: ~${estimated_loss:.0f}"

        reason += (
            f"\n\n**Action**: Buy to close {contracts} {position.symbol} ${strike:.0f} {option_type}. "
            f"Consider selling new ATM option to restart income generation."
        )

        reason_short = f"DROWNING ({itm_pct:.0f}% ITM) - close to stop the bleeding"

        return V5EvaluationResult(
            action='CLOSE',
            position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
            symbol=position.symbol,
            reason=reason,
            reason_short=reason_short,
            philosophy_applied='drowning_take_loss',
            stuck_category='DROWNING',
            iv_category=iv_category,
            weekly_credit=weekly_credit,
            biweekly_credit=biweekly_credit,
            monthly_credit=monthly_credit,
            details={
                'itm_pct': itm_pct,
                'intrinsic_pct': intrinsic_pct,
                'cost_to_close': cost_to_close,
                'estimated_loss': estimated_loss,
                'trigger': 'drowning_close',
                'current_price': current_price,
                'days_to_exp': days_to_exp,
            },
            intrinsic_pct=intrinsic_pct,
            time_value=time_value
        )

    def _check_zero_cost_compression(
        self,
        position,
        current_price: float,
        current_premium: float,
        days_to_exp: int,
        itm_pct: float,
        intrinsic_pct: float
    ) -> Optional[V5EvaluationResult]:
        """
        Check for zero-cost compression opportunity on long-dated ITM positions.
        """
        try:
            from app.modules.strategies.schwab_service import (
                get_option_expirations_schwab,
                get_options_chain_schwab
            )

            symbol = position.symbol
            strike = float(position.strike_price) if position.strike_price else 0.0
            option_type = getattr(position, 'option_type', 'call')
            contracts = getattr(position, 'contracts_sold', 1) or 1
            current_expiration = position.expiration_date

            if isinstance(current_expiration, str):
                current_expiration = date.fromisoformat(current_expiration)

            available_expirations = get_option_expirations_schwab(symbol)
            if not available_expirations:
                logger.debug(f"[V5 Compression] No expirations available for {symbol}")
                return None

            today = date.today()

            shorter_expirations = []
            for exp_str in available_expirations:
                exp = date.fromisoformat(exp_str) if isinstance(exp_str, str) else exp_str
                if exp < current_expiration and (exp - today).days >= 7:
                    shorter_expirations.append(exp)

            if not shorter_expirations:
                logger.debug(f"[V5 Compression] No shorter expirations for {symbol}")
                return None

            shorter_expirations.sort(reverse=True)

            max_cost_immediate = 500
            best_compression = None
            debug_info = []

            logger.info(f"[V5 Compression] Checking {symbol}: strike=${strike}, current_premium=${current_premium:.2f}, current_price=${current_price:.2f}")

            for target_exp in shorter_expirations:
                exp_str = target_exp.isoformat()
                days_saved = (current_expiration - target_exp).days

                chain = get_options_chain_schwab(
                    symbol,
                    expiration_date=exp_str,
                    option_type=option_type.upper()
                )

                if not chain:
                    continue

                options = chain.get('calls' if option_type.lower() == 'call' else 'puts', [])
                if not options:
                    continue

                for opt in options:
                    opt_strike = opt.get('strike', 0)
                    bid = opt.get('bid', 0)

                    if bid <= 0:
                        continue

                    strike_diff = opt_strike - strike
                    is_same_strike = abs(strike_diff) <= 1

                    if not is_same_strike:
                        if option_type.lower() == 'call':
                            if strike_diff > 10 or strike_diff < -20:
                                continue
                            if opt_strike < current_price * 0.90:
                                continue
                        else:
                            if strike_diff < -10 or strike_diff > 20:
                                continue
                            if opt_strike > current_price * 1.10:
                                continue

                    net_cost_per_share = current_premium - bid
                    net_cost_total = net_cost_per_share * 100 * contracts

                    if len(debug_info) < 3:
                        debug_info.append(f"{target_exp}: ${opt_strike} bid=${bid:.2f} cost=${net_cost_total:.0f}")

                    if net_cost_total <= max_cost_immediate:
                        compression_info = {
                            'target_exp': target_exp,
                            'target_strike': opt_strike,
                            'new_premium': bid,
                            'net_cost_per_share': net_cost_per_share,
                            'net_cost_total': net_cost_total,
                            'days_saved': days_saved,
                            'is_credit': net_cost_total < 0,
                        }

                        if best_compression is None or days_saved > best_compression['days_saved']:
                            best_compression = compression_info

            if best_compression:
                target_exp = best_compression['target_exp']
                target_strike = best_compression['target_strike']
                net_cost_total = best_compression['net_cost_total']
                days_saved = best_compression['days_saved']
                is_credit = best_compression['is_credit']

                if is_credit:
                    cost_str = f"Credit ${abs(net_cost_total):.0f}"
                elif net_cost_total == 0:
                    cost_str = "Zero cost"
                else:
                    cost_str = f"Cost ${net_cost_total:.0f}"

                reason = (
                    f"**COMPRESS - Zero/Low Cost Opportunity**: {symbol} is {itm_pct:.1f}% ITM.\n\n"
                    f"Compression available: {current_expiration.strftime('%b')} → {target_exp.strftime('%b %d')} "
                    f"({days_saved} days shorter)\n"
                    f"{cost_str}\n\n"
                    f"V5 Philosophy: Iterative compression at low cost is the path out of stuck positions. "
                    f"Each compression brings you closer to freedom.\n\n"
                    f"Roll ${strike:.0f} {option_type} to ${target_strike:.0f} {target_exp.strftime('%m/%d')}"
                )
                reason_short = f"COMPRESS: {days_saved}d shorter for {cost_str}"

                logger.info(
                    f"[V5 Compression] Found opportunity for {symbol}: "
                    f"{current_expiration} → {target_exp}, {cost_str}"
                )

                return V5EvaluationResult(
                    action='COMPRESS',
                    position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                    symbol=position.symbol,
                    reason=reason,
                    reason_short=reason_short,
                    philosophy_applied='iterative_compression',
                    new_strike=target_strike,
                    new_expiration=target_exp,
                    net_cost=net_cost_total,
                    compression_cost=net_cost_total,
                    details={
                        'itm_pct': itm_pct,
                        'trigger': 'zero_cost_compression',
                        'days_saved': days_saved,
                        'current_expiration': current_expiration.isoformat(),
                        'target_expiration': target_exp.isoformat(),
                        'current_premium': current_premium,
                        'new_premium': best_compression['new_premium'],
                        'is_credit': is_credit,
                    },
                    intrinsic_pct=intrinsic_pct
                )

            if debug_info:
                logger.info(f"[V5 Compression] {symbol} options checked: {debug_info}")
            logger.info(f"[V5 Compression] No compression under ${max_cost_immediate} for {symbol}")
            return None

        except Exception as e:
            logger.error(f"[V5 Compression] Error checking {position.symbol}: {e}", exc_info=True)
            return None

    def _handle_itm_position(
        self,
        position,
        is_itm: bool,
        itm_pct: float,
        intrinsic_pct: float,
        intrinsic_value: float,
        time_value: float,
        current_price: float,
        current_premium: float,
        profit_pct: float,
        days_to_exp: int,
        weekly_income: Optional[float],
        cost_basis: Optional[float]
    ) -> V5EvaluationResult:
        """Handle ITM positions using V5 intrinsic/time value model."""
        max_escape_weeks = self.config.get('max_escape_weeks', 4)
        weeks_to_escape = min(int(itm_pct / 1.0) + 1, max_escape_weeks)

        if intrinsic_pct < 0.50:
            reason = (
                f"**HOLD - Mean Reversion Expected**: Position is shallow ITM ({itm_pct:.1f}%), "
                f"intrinsic is only {intrinsic_pct*100:.0f}% of premium.\n\n"
                f"V5 Philosophy: Mean reversion is inevitable. Stock will likely move back OTM."
            )
            reason_short = f"Shallow ITM ({itm_pct:.1f}%), wait for mean reversion"

            return V5EvaluationResult(
                action='HOLD',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='mean_reversion',
                details={
                    'itm_pct': itm_pct,
                    'intrinsic_pct': intrinsic_pct,
                    'time_value': time_value
                },
                intrinsic_pct=intrinsic_pct,
                time_value=time_value,
                escape_weeks=weeks_to_escape
            )

        elif intrinsic_pct < 0.80:
            reason = (
                f"**Moderate ITM**: Position is {itm_pct:.1f}% ITM, "
                f"intrinsic is {intrinsic_pct*100:.0f}% of premium.\n\n"
                f"V5 Philosophy: Stock could revert, but risk is increasing. "
                f"Monitor closely. Consider closing on any bounce."
            )
            reason_short = f"Moderate ITM ({itm_pct:.1f}%), monitor for bounce"

            return V5EvaluationResult(
                action='HOLD',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='tactical_timing',
                has_follow_up=True,
                follow_up_condition='stock_bounces',
                follow_up_threshold=0.02,
                follow_up_action='CLOSE',
                details={
                    'itm_pct': itm_pct,
                    'intrinsic_pct': intrinsic_pct
                },
                intrinsic_pct=intrinsic_pct,
                escape_weeks=weeks_to_escape
            )

        else:
            return self._evaluate_compression(
                position, itm_pct, intrinsic_pct, intrinsic_value, time_value,
                current_price, current_premium, days_to_exp, weekly_income
            )

    def _evaluate_compression(
        self,
        position,
        itm_pct: float,
        intrinsic_pct: float,
        intrinsic_value: float,
        time_value: float,
        current_price: float,
        current_premium: float,
        days_to_exp: int,
        weekly_income: Optional[float]
    ) -> V5EvaluationResult:
        """Evaluate whether to compress a deep ITM position to weekly."""
        if weekly_income is None:
            weekly_income = self.config['compression']['default_weekly_income']

        weekly_income_per_share = weekly_income / 100.0
        favorable_prob = self.config['compression']['cycle_capture']['favorable_cycle_probability']

        benefit_weekly = weekly_income_per_share
        cycle_capture_value = current_premium * 0.20 * favorable_prob
        total_value = benefit_weekly + cycle_capture_value
        compression_cost = intrinsic_value
        compress_ratio = total_value / compression_cost if compression_cost > 0 else float('inf')

        should_compress = compress_ratio >= self.config['compression']['consider_threshold']

        if should_compress:
            strike = float(position.strike_price) if position.strike_price else 0.0
            option_type = getattr(position, 'option_type', 'call')
            contracts = getattr(position, 'contracts_sold', 1) or 1
            current_expiration = getattr(position, 'expiration_date', None)

            today = date.today()
            days_to_friday = (4 - today.weekday()) % 7
            if days_to_friday == 0:
                days_to_friday = 7
            new_expiration = today + timedelta(days=days_to_friday)

            try:
                if current_expiration:
                    if isinstance(current_expiration, str):
                        current_expiration = datetime.strptime(current_expiration, '%Y-%m-%d').date()
                    elif isinstance(current_expiration, datetime):
                        current_expiration = current_expiration.date()
                    elif hasattr(current_expiration, 'date'):
                        current_expiration = current_expiration.date()

                    if isinstance(current_expiration, date) and new_expiration <= current_expiration:
                        days_after = current_expiration + timedelta(days=1)
                        days_to_next_friday = (4 - days_after.weekday()) % 7
                        if days_to_next_friday == 0:
                            days_to_next_friday = 7
                        new_expiration = days_after + timedelta(days=days_to_next_friday)
            except Exception:
                pass

            new_strike = calculate_escape_strike(strike, current_price, option_type, is_itm=True)
            strike_change = abs(new_strike - strike)

            # Use live option chain data for accurate compression calculations
            close_cost_per_share = current_premium
            current_exp_date = getattr(position, 'expiration_date', None)
            if current_exp_date:
                if isinstance(current_exp_date, datetime):
                    current_exp_date = current_exp_date.date()
                elif isinstance(current_exp_date, str):
                    try:
                        current_exp_date = datetime.strptime(current_exp_date, '%Y-%m-%d').date()
                    except:
                        current_exp_date = None

            if current_exp_date and self.option_fetcher:
                try:
                    current_quote = self.option_fetcher.get_option_quote(
                        symbol=position.symbol,
                        strike_price=strike,
                        option_type=option_type,
                        expiration_date=current_exp_date
                    )
                    if current_quote:
                        close_cost_per_share = current_quote.ask if current_quote.ask else (current_quote.last_price or current_premium)
                        logger.debug(f"[V5 Compress] {position.symbol}: Live close cost = ${close_cost_per_share:.2f}/share (ask)")
                except Exception as e:
                    logger.warning(f"[V5 Compress] Failed to get current option quote for {position.symbol}: {e}")

            estimated_new_premium = weekly_income_per_share
            if self.option_fetcher:
                try:
                    new_quote = self.option_fetcher.get_option_quote(
                        symbol=position.symbol,
                        strike_price=new_strike,
                        option_type=option_type,
                        expiration_date=new_expiration
                    )
                    if new_quote:
                        estimated_new_premium = new_quote.bid if new_quote.bid else (new_quote.last_price or estimated_new_premium)
                        logger.debug(f"[V5 Compress] {position.symbol}: Live new premium = ${estimated_new_premium:.2f}/share (bid)")
                except Exception as e:
                    logger.warning(f"[V5 Compress] Failed to get new option quote for {position.symbol}: {e}")

            estimated_net_credit = estimated_new_premium - close_cost_per_share
            net_per_contract = estimated_net_credit * 100
            total_roll_cost = net_per_contract * contracts

            logger.info(f"[V5 Compress] {position.symbol}: Close ${close_cost_per_share:.2f} → New ${estimated_new_premium:.2f} = Net {'Credit' if total_roll_cost > 0 else 'Debit'} ${abs(total_roll_cost):.0f}")

            if option_type == 'call' and new_strike > strike:
                strike_direction = f"UP from ${strike:.0f} to ${new_strike:.0f}"
            elif option_type == 'put' and new_strike < strike:
                strike_direction = f"DOWN from ${strike:.0f} to ${new_strike:.0f}"
            else:
                strike_direction = f"${new_strike:.0f}"

            reason = (
                f"**COMPRESS + Roll {strike_direction}**: Deep ITM ({itm_pct:.1f}%), "
                f"intrinsic is {intrinsic_pct*100:.0f}% of premium.\n\n"
                f"V5 Philosophy: Compress to weekly AND move strike to escape ITM.\n"
                f"Stock: ${current_price:.2f} | Current strike: ${strike:.0f} | New strike: ${new_strike:.0f}\n\n"
                f"**Roll Economics** (per share):\n"
                f"- Buy back current: ${close_cost_per_share:.2f}\n"
                f"- Sell new weekly: ~${estimated_new_premium:.2f}\n"
                f"- Net: {'Credit' if estimated_net_credit > 0 else 'Debit'} ${abs(estimated_net_credit):.2f}/share\n"
                f"- Total ({contracts} contract{'s' if contracts > 1 else ''}): "
                f"{'Earn' if total_roll_cost > 0 else 'Cost'} ~${abs(total_roll_cost):.0f}\n\n"
                f"Roll ${strike:.0f} {position.option_type} to ${new_strike:.0f} {new_expiration.strftime('%m/%d')} · "
                f"{'Earn' if total_roll_cost > 0 else 'Cost'} ~${abs(total_roll_cost):.0f}"
            )
            if strike_change > 0:
                reason_short = f"Roll {option_type} ${strike:.0f}→${new_strike:.0f} {new_expiration.strftime('%m/%d')} to escape ITM"
            else:
                reason_short = f"Compress to weekly ${new_strike:.0f} {new_expiration.strftime('%m/%d')}"

            return V5EvaluationResult(
                action='COMPRESS',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='dual_benefit_compression',
                new_strike=new_strike,
                new_expiration=new_expiration,
                net_cost=-total_roll_cost,
                details={
                    'itm_pct': itm_pct,
                    'intrinsic_pct': intrinsic_pct,
                    'benefit_weekly': benefit_weekly,
                    'cycle_capture_value': cycle_capture_value,
                    'total_value': total_value,
                    'compression_cost': compression_cost,
                    'compress_ratio': compress_ratio,
                },
                intrinsic_pct=intrinsic_pct,
                compression_value=total_value,
                compression_cost=compression_cost
            )
        else:
            reason = (
                f"**CLOSE + Wait for Recovery**: Deep ITM ({itm_pct:.1f}%), "
                f"but compression not favorable.\n\n"
                f"V5 Philosophy: Tactical timing - close now and wait for stock to recover."
            )
            reason_short = f"Deep ITM, close + wait for {position.symbol} recovery"

            return V5EvaluationResult(
                action='CLOSE',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='tactical_timing',
                has_follow_up=True,
                follow_up_condition='stock_drops_3_pct',
                follow_up_threshold=0.03,
                follow_up_action='RE_ENTER',
                details={
                    'itm_pct': itm_pct,
                    'compress_ratio': compress_ratio,
                    'wait_for_recovery': True
                },
                intrinsic_pct=intrinsic_pct
            )
