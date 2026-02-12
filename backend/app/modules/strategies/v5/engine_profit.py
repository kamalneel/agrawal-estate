"""
V5 Engine 3: Profit-Taking / OTM Position Management

Handles OTM positions: early profit capture, time decay, roll-to-continue.

V5 Philosophy:
- Don't let a winner become a loser (70%+ profit → close)
- Primary goal is weekly income (roll to continue earning)
- Close early for flexibility (80%+ profit with follow-up)
- Let time decay work (hold when profitable)
"""

import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, date, timedelta

from app.modules.strategies.v5.base import (
    V5EvaluationResult,
    get_v5_config,
    calculate_escape_strike,
)

logger = logging.getLogger(__name__)


class ProfitEngine:
    """
    Engine 3: Profit-taking and OTM position evaluation.

    Handles early profit capture, time cushion OTM, and standard OTM holding logic.
    """

    def __init__(self, ta_service, option_fetcher):
        self.ta_service = ta_service
        self.option_fetcher = option_fetcher
        self.config = get_v5_config()

    def evaluate_early_profit(
        self,
        position,
        profit_pct: float,
        original_premium: float,
        current_premium: float,
        current_price: float,
        days_to_exp: int
    ) -> V5EvaluationResult:
        """Handle positions where 70%+ of premium has been captured."""
        strike = float(position.strike_price) if position.strike_price else 0.0
        contracts = getattr(position, 'contracts_sold', 1) or 1
        profit_captured = (original_premium - current_premium) * contracts * 100
        cost_to_close = current_premium * contracts * 100

        reason = (
            f"**CLOSE - Lock In Profits**: You've captured {profit_pct*100:.0f}% of the premium "
            f"(${profit_captured:.0f} profit).\n\n"
            f"V5 Philosophy: Don't let a winner become a loser. With {days_to_exp} days left, "
            f"the remaining ${cost_to_close:.0f} isn't worth the risk of reversal.\n\n"
            f"**Action**: Buy to close at ~${current_premium:.2f} per contract."
        )
        reason_short = f"{profit_pct*100:.0f}% profit captured - close to lock in ${profit_captured:.0f}"

        return V5EvaluationResult(
            action='CLOSE',
            position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
            symbol=position.symbol,
            reason=reason,
            reason_short=reason_short,
            philosophy_applied='lock_in_profits',
            details={
                'profit_pct': profit_pct,
                'profit_captured': profit_captured,
                'cost_to_close': cost_to_close,
                'original_premium': original_premium,
                'current_premium': current_premium,
                'days_to_exp': days_to_exp,
                'trigger': 'early_profit_capture'
            }
        )

    def evaluate_time_cushion_otm(
        self,
        position,
        profit_pct: float,
        current_price: float,
        current_premium: float,
        intrinsic_pct: float
    ) -> V5EvaluationResult:
        """Handle OTM positions with <=2 days to expiry."""
        min_days = self.config['time_cushion']['min_days_to_expiry']
        early_close_threshold = self.config.get('early_close_threshold', 0.70)

        if profit_pct >= 0.80:
            new_strike, new_exp, net_credit = self._calculate_roll_targets(
                position, current_premium, current_price
            )
            strike = float(position.strike_price) if position.strike_price else 0.0

            reason = (
                f"**Time Cushion + Profitable**: Position expires in ≤{min_days} days, "
                f"OTM with {profit_pct*100:.0f}% profit.\n\n"
                f"V5 Philosophy: Primary goal is weekly income. Roll to next week to continue earning.\n\n"
                f"Roll ${strike:.0f} {position.option_type} to ${new_strike:.0f} {new_exp.strftime('%m/%d')} · "
                f"Earn ~${net_credit:.0f}"
            )
            reason_short = f"Time cushion, {profit_pct*100:.0f}% profit - roll to ${new_strike:.0f} {new_exp.strftime('%m/%d')}"

            return V5EvaluationResult(
                action='ROLL',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='weekly_options_income',
                new_strike=new_strike,
                new_expiration=new_exp,
                net_cost=-net_credit if net_credit > 0 else abs(net_credit),
                details={
                    'days_to_exp': min_days,
                    'profit_pct': profit_pct,
                    'trigger': 'time_cushion_profitable',
                    'estimated_credit': net_credit
                }
            )
        elif profit_pct >= early_close_threshold:
            strike = float(position.strike_price) if position.strike_price else 0.0
            contracts = getattr(position, 'contracts_sold', 1) or 1
            original_premium_raw = getattr(position, 'original_premium', 1.0)
            original_premium = float(original_premium_raw) if original_premium_raw else 1.0
            profit_captured = (original_premium - current_premium) * contracts * 100
            cost_to_close = current_premium * contracts * 100

            reason = (
                f"**CLOSE - Lock In Profits**: Position expires in ≤{min_days} days, "
                f"OTM with {profit_pct*100:.0f}% profit (${profit_captured:.0f} captured).\n\n"
                f"V5 Philosophy: Don't let a winner become a loser. "
                f"With {profit_pct*100:.0f}% captured, buy to close.\n\n"
                f"**Action**: Buy to close {contracts} {position.symbol} ${strike:.0f} {position.option_type}."
            )
            reason_short = f"{profit_pct*100:.0f}% profit captured - buy to close for ${cost_to_close:.0f}"

            return V5EvaluationResult(
                action='CLOSE',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='lock_in_profits',
                details={
                    'days_to_exp': min_days,
                    'profit_pct': profit_pct,
                    'profit_captured': profit_captured,
                    'cost_to_close': cost_to_close,
                    'trigger': 'time_cushion_early_close',
                    'current_price': current_price,
                }
            )
        else:
            reason = (
                f"**Let Expire**: Position expires in ≤{min_days} days, "
                f"OTM with {profit_pct*100:.0f}% profit.\n\n"
                f"V5 Philosophy: Position is OTM and will likely expire worthless. "
                f"No action needed - full premium captured."
            )
            reason_short = f"OTM, {profit_pct*100:.0f}% profit - let expire"

            return V5EvaluationResult(
                action='LET_EXPIRE',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='weekly_options_income',
                details={
                    'days_to_exp': min_days,
                    'profit_pct': profit_pct,
                    'trigger': 'expire_worthless'
                }
            )

    def evaluate_otm(
        self,
        position,
        itm_pct: float,
        current_price: float,
        current_premium: float,
        profit_pct: float,
        days_to_exp: int,
        indicators
    ) -> V5EvaluationResult:
        """Handle OTM positions (standard path)."""
        otm_pct = abs(itm_pct)

        if profit_pct >= 0.80:
            reason = (
                f"**Early Close for Flexibility**: {profit_pct*100:.0f}% profit captured, "
                f"position is {otm_pct:.1f}% OTM.\n\n"
                f"V5 Philosophy: Close early to gain re-entry flexibility."
            )
            reason_short = f"{profit_pct*100:.0f}% profit, close for flexibility"

            return V5EvaluationResult(
                action='CLOSE',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='tactical_timing',
                has_follow_up=True,
                follow_up_condition='stock_pulls_back',
                follow_up_threshold=0.02,
                follow_up_action='SELL_NEW',
                details={
                    'profit_pct': profit_pct,
                    'otm_pct': otm_pct,
                    'early_close': True
                }
            )

        elif profit_pct >= 0.60:
            if days_to_exp <= 7:
                new_strike, new_exp, net_credit = self._calculate_roll_targets(
                    position, current_premium, current_price
                )
                strike = float(position.strike_price) if position.strike_price else 0.0

                reason = (
                    f"**Roll to Next Week**: {profit_pct*100:.0f}% profit, "
                    f"expiring in {days_to_exp} days.\n\n"
                    f"V5 Philosophy: Primary goal is weekly income. Roll to continue earning."
                )
                reason_short = f"{profit_pct*100:.0f}% profit, roll to {new_exp.strftime('%m/%d')}"

                return V5EvaluationResult(
                    action='ROLL',
                    position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                    symbol=position.symbol,
                    reason=reason,
                    reason_short=reason_short,
                    philosophy_applied='weekly_options_income',
                    new_strike=new_strike,
                    new_expiration=new_exp,
                    net_cost=-net_credit if net_credit > 0 else abs(net_credit),
                    details={
                        'profit_pct': profit_pct,
                        'days_to_exp': days_to_exp,
                        'estimated_credit': net_credit
                    }
                )
            else:
                reason = (
                    f"**HOLD**: {profit_pct*100:.0f}% profit with {days_to_exp} days remaining.\n\n"
                    f"V5 Philosophy: Let time decay continue working. No action needed yet."
                )
                reason_short = f"{profit_pct*100:.0f}% profit, {days_to_exp}d left - hold"

                return V5EvaluationResult(
                    action='HOLD',
                    position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                    symbol=position.symbol,
                    reason=reason,
                    reason_short=reason_short,
                    philosophy_applied='weekly_options_income',
                    details={
                        'profit_pct': profit_pct,
                        'days_to_exp': days_to_exp
                    }
                )

        else:
            reason = (
                f"**HOLD**: {profit_pct*100:.0f}% profit, position is {otm_pct:.1f}% OTM.\n\n"
                f"V5 Philosophy: Position is working as expected. Time decay will continue."
            )
            reason_short = f"{profit_pct*100:.0f}% profit, {otm_pct:.1f}% OTM - hold"

            return V5EvaluationResult(
                action='HOLD',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='weekly_options_income',
                details={
                    'profit_pct': profit_pct,
                    'otm_pct': otm_pct,
                    'days_to_exp': days_to_exp
                }
            )

    def evaluate_fallback(self, position) -> Optional[V5EvaluationResult]:
        """Fallback evaluation when technical indicators are unavailable."""
        try:
            symbol = position.symbol
            strike = float(position.strike_price) if position.strike_price else 0.0
            contracts = getattr(position, 'contracts_sold', 1) or 1

            gain_loss_pct = getattr(position, 'gain_loss_percent', None)
            if gain_loss_pct is not None:
                profit_pct = float(gain_loss_pct) / 100
            else:
                profit_pct = 0.0

            today = date.today()
            exp_date = position.expiration_date
            if exp_date:
                if isinstance(exp_date, datetime):
                    exp_date = exp_date.date()
                days_to_exp = (exp_date - today).days
            else:
                days_to_exp = 7

            if profit_pct >= 0.70:
                reason = (
                    f"**CLOSE - Lock In Profits**: You've captured {profit_pct*100:.0f}% of the premium.\n\n"
                    f"V5 Philosophy: Don't let a winner become a loser.\n\n"
                    f"Note: Price data unavailable - using stored position data."
                )
                reason_short = f"{profit_pct*100:.0f}% profit - close to lock in gains"

                return V5EvaluationResult(
                    action='CLOSE',
                    position_id=str(position.id) if hasattr(position, 'id') else symbol,
                    symbol=symbol,
                    reason=reason,
                    reason_short=reason_short,
                    philosophy_applied='lock_in_profits',
                    details={
                        'profit_pct': profit_pct,
                        'days_to_exp': days_to_exp,
                        'trigger': 'fallback_high_profit',
                        'ta_unavailable': True
                    }
                )

            elif days_to_exp <= 3:
                reason = (
                    f"**TIME CUSHION**: Position expires in {days_to_exp} days with {profit_pct*100:.0f}% profit.\n\n"
                    f"V5 Philosophy: Avoid forced assignment. Consider rolling to next week.\n\n"
                    f"Note: Price data unavailable - check current stock price before acting."
                )
                reason_short = f"{days_to_exp}d to expiry, {profit_pct*100:.0f}% profit - review for roll"

                return V5EvaluationResult(
                    action='ROLL',
                    position_id=str(position.id) if hasattr(position, 'id') else symbol,
                    symbol=symbol,
                    reason=reason,
                    reason_short=reason_short,
                    philosophy_applied='avoid_forced_assignment',
                    details={
                        'profit_pct': profit_pct,
                        'days_to_exp': days_to_exp,
                        'trigger': 'fallback_time_cushion',
                        'ta_unavailable': True
                    }
                )

            else:
                reason = (
                    f"**HOLD**: Position has {profit_pct*100:.0f}% profit with {days_to_exp} days remaining.\n\n"
                    f"V5 Philosophy: Let time decay continue working.\n\n"
                    f"Note: Price data unavailable - using stored position data."
                )
                reason_short = f"{profit_pct*100:.0f}% profit, {days_to_exp}d left - hold"

                return V5EvaluationResult(
                    action='HOLD',
                    position_id=str(position.id) if hasattr(position, 'id') else symbol,
                    symbol=symbol,
                    reason=reason,
                    reason_short=reason_short,
                    philosophy_applied='weekly_options_income',
                    details={
                        'profit_pct': profit_pct,
                        'days_to_exp': days_to_exp,
                        'trigger': 'fallback_hold',
                        'ta_unavailable': True
                    }
                )

        except Exception as e:
            logger.error(f"Fallback evaluation failed for {position.symbol}: {e}")
            return None

    def _calculate_roll_targets(
        self,
        position,
        current_premium: float,
        current_price: float,
        force_escape: bool = False
    ) -> Tuple[float, date, float]:
        """
        Calculate roll targets: new strike, new expiration, and estimated net credit.

        Uses LIVE option chain data when available, with naive fallback.
        """
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
                    try:
                        current_expiration = datetime.strptime(current_expiration, '%Y-%m-%d').date()
                    except:
                        pass
                elif isinstance(current_expiration, datetime):
                    current_expiration = current_expiration.date()
                elif hasattr(current_expiration, 'date'):
                    current_expiration = current_expiration.date()

                if isinstance(current_expiration, date) and new_expiration <= current_expiration:
                    new_expiration = current_expiration + timedelta(days=7)
        except Exception as e:
            logger.warning(f"Error calculating new expiration for {position.symbol}: {e}")

        if option_type == 'call':
            is_itm = current_price > strike
        else:
            is_itm = current_price < strike

        if is_itm or force_escape:
            new_strike = calculate_escape_strike(strike, current_price, option_type, True)
        else:
            new_strike = strike

        # Use live option chain data
        current_exp_date = getattr(position, 'expiration_date', None)
        if current_exp_date:
            if isinstance(current_exp_date, datetime):
                current_exp_date = current_exp_date.date()
            elif isinstance(current_exp_date, str):
                try:
                    current_exp_date = datetime.strptime(current_exp_date, '%Y-%m-%d').date()
                except:
                    current_exp_date = None

        close_cost_per_share = current_premium
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
                    logger.debug(f"[V5 Roll] {position.symbol}: Live close cost = ${close_cost_per_share:.2f}/share (ask)")
            except Exception as e:
                logger.warning(f"[V5 Roll] Failed to get current option quote for {position.symbol}: {e}")

        estimated_new_premium = current_premium * 2.0
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
                    logger.debug(f"[V5 Roll] {position.symbol}: Live new premium = ${estimated_new_premium:.2f}/share (bid)")
            except Exception as e:
                logger.warning(f"[V5 Roll] Failed to get new option quote for {position.symbol}: {e}")

        net_credit_per_share = estimated_new_premium - close_cost_per_share
        net_credit = net_credit_per_share * contracts * 100

        logger.info(f"[V5 Roll] {position.symbol}: Close ${close_cost_per_share:.2f} → New ${estimated_new_premium:.2f} = Net {'Credit' if net_credit > 0 else 'Debit'} ${abs(net_credit):.0f}")

        return new_strike, new_expiration, net_credit
