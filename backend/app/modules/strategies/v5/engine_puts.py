"""
V5 Engine 2: Cash-Secured Put Recommendations

Finds best put opportunities for idle cash across accounts.

V5 Philosophy:
- Use idle cash to generate income via put selling
- Only sell puts on stocks already in portfolio (believe in holdings)
- Sell puts when stock is DOWN (good entry point if assigned)
- Strike below cost basis = assignment improves average cost
"""

import logging
from datetime import date
from typing import Dict, List, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text, func

from app.modules.strategies.v5.base import get_next_friday

logger = logging.getLogger(__name__)


class PutEngine:
    """
    Engine 2: Cash-secured put opportunity detection.

    Scans accounts with idle cash and finds best put selling opportunities
    on portfolio stocks.
    """

    def __init__(self, db: Session, ta_service):
        self.db = db
        self.ta_service = ta_service

    def run(
        self,
        positions: List[Any],
        cost_basis_map: Optional[Dict[str, float]] = None
    ) -> List[Dict[str, Any]]:
        """
        Run cash-secured put evaluation.

        Args:
            positions: List of current positions (to find portfolio symbols)
            cost_basis_map: {symbol: cost_basis} for scoring

        Returns:
            List of notification dicts (SELL_PUT actions)
        """
        from app.modules.strategies.algorithm_config import (
            get_config, get_available_cash_for_puts, should_recommend_new_put
        )
        from app.modules.strategies.models import SoldOption, SoldOptionsSnapshot

        notifications = []
        config = get_config()
        cost_basis_map = cost_basis_map or {}

        fixed_balances = config.get("fixed_cash_balances", {})
        if not fixed_balances:
            logger.info("[V5] No fixed cash balances configured, skipping put recommendations")
            return notifications

        # Get unique symbols from current holdings
        portfolio_symbols = set()
        for pos in positions:
            if hasattr(pos, 'symbol') and pos.symbol:
                portfolio_symbols.add(pos.symbol)

        # Also get symbols from investment_holdings
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
            logger.info(f"[V5] Put candidates: {len(portfolio_symbols)} symbols from holdings + sold options")
        except Exception as e:
            logger.warning(f"[V5] Could not fetch holdings for put candidates: {e}")

        # For each account with fixed cash
        for account_name, fixed_balance in fixed_balances.items():
            try:
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

                can_recommend, available_cash, reason = should_recommend_new_put(
                    account_name, existing_puts
                )

                if not can_recommend:
                    continue

                put_notif = self._find_best_put_opportunity(
                    account_name=account_name,
                    available_cash=available_cash,
                    existing_puts=existing_puts,
                    portfolio_symbols=portfolio_symbols,
                    cost_basis_map=cost_basis_map
                )

                if put_notif:
                    notifications.append(put_notif)

            except Exception as e:
                logger.error(f"[V5] Error evaluating puts for {account_name}: {e}", exc_info=True)

        return notifications

    def _find_best_put_opportunity(
        self,
        account_name: str,
        available_cash: float,
        existing_puts: List[Any],
        portfolio_symbols: set,
        cost_basis_map: Dict[str, float]
    ) -> Optional[Dict[str, Any]]:
        """Find the best cash-secured put opportunity for an account."""
        existing_put_symbols = {p.symbol for p in existing_puts}

        best_opportunity = None
        best_score = -1

        for symbol in portfolio_symbols:
            if symbol in existing_put_symbols:
                continue

            try:
                indicators = self.ta_service.get_technical_indicators(symbol)
                if not indicators or not indicators.current_price:
                    continue

                current_price = indicators.current_price

                score = self._score_put_opportunity(
                    symbol=symbol,
                    indicators=indicators,
                    cost_basis=cost_basis_map.get(symbol)
                )

                if score > best_score:
                    strike_rec = self.ta_service.recommend_strike_price(
                        symbol=symbol,
                        option_type="put",
                        expiration_weeks=1,
                        probability_target=0.80
                    )

                    if strike_rec and strike_rec.recommended_strike:
                        strike = strike_rec.recommended_strike
                        required_cash = strike * 100

                        if required_cash <= available_cash:
                            best_score = score
                            best_opportunity = {
                                'symbol': symbol,
                                'strike': strike,
                                'indicators': indicators,
                                'score': score,
                                'required_cash': required_cash,
                                'premium_estimate': None,
                            }

            except Exception as e:
                logger.warning(f"[V5] Error evaluating put opportunity for {symbol}: {e}")

        if not best_opportunity:
            return None

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
        """Score a put selling opportunity (higher = better)."""
        score = 0.0

        if indicators.rsi_14:
            if indicators.rsi_14 < 30:
                score += 2.0
            elif indicators.rsi_14 < 40:
                score += 1.0

        if indicators.trend == 'oversold_bounce':
            score += 1.5
        elif indicators.trend in ('lower_band', 'bearish'):
            score += 1.0

        if cost_basis and indicators.current_price:
            if indicators.current_price < cost_basis:
                score += 2.0

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
        premium = opportunity.get('premium_estimate', 0) or 50
        required = opportunity['required_cash']

        current_price = indicators.current_price if indicators else 0
        rsi = indicators.rsi_14 if indicators else None
        next_friday = get_next_friday()

        otm_pct = ((current_price - strike) / current_price * 100) if current_price else 0

        reason_parts = [
            f"**Cash-Secured Put Opportunity**: ${available_cash:,.0f} available in {account_name}.",
            "",
            f"V5 Philosophy: Use idle cash to generate income on stocks you believe in.",
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

        title = f"SELL: 1 {symbol} ${strike:.0f} put for {next_friday.strftime('%m/%d')} · Earn ~${premium:.0f}"

        return {
            'id': f"csp_{symbol}_{account_name}_{date.today().isoformat()}",
            'symbol': symbol,
            'account_name': account_name,
            'action': 'SELL_PUT',
            'action_display': 'Sell Put',
            'title': title,
            'reason': full_reason,
            'reason_short': reason_short,
            'rationale': full_reason,
            'philosophy': 'weekly_options_income',
            'priority': 'medium',
            'contracts': 1,
            'option_type': 'put',
            'source_strike': strike,
            'source_expiration': next_friday,
            'target_strike': strike,
            'target_expiration': next_friday,
            'target_premium': premium,
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
