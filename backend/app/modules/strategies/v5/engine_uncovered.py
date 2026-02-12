"""
V5 Engine 1: Uncovered Position Detection

Detects positions with shares but no sold calls and recommends SELL or WAIT.

V5 Philosophy:
- Every share should be generating income
- Don't sell calls when stock is DOWN → wait for recovery
- Sell when stock is UP (good premium capture)
"""

import logging
from datetime import date
from typing import Dict, List, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.modules.strategies.v5.base import get_next_friday
from app.modules.strategies.v5_sanitizer import sanitize_for_json

logger = logging.getLogger(__name__)


class UncoveredEngine:
    """
    Engine 1: Uncovered position detection and evaluation.

    Finds positions with shares but no sold calls, and recommends
    SELL (covered call) or WAIT (stock is down, wait for bounce).
    """

    def __init__(self, db: Session, ta_service):
        self.db = db
        self.ta_service = ta_service

    def run(self) -> List[Dict[str, Any]]:
        """
        Run uncovered position detection and evaluation.

        Returns:
            List of notification dicts (SELL or WAIT actions)
        """
        uncovered = self._get_uncovered_positions()
        notifications = []

        for position in uncovered:
            try:
                notif = self._evaluate_single_uncovered(position)
                if notif:
                    notif = sanitize_for_json(notif)
                    notifications.append(notif)
            except Exception as e:
                logger.error(f"[V5] Error evaluating uncovered {position['symbol']}: {e}")

        return notifications

    def get_uncovered_positions(self) -> List[Dict[str, Any]]:
        """Public accessor for uncovered positions (used by orchestrator)."""
        return self._get_uncovered_positions()

    def _get_uncovered_positions(self) -> List[Dict[str, Any]]:
        """
        Detect positions with shares but no sold calls (uncovered).

        Returns:
            List of dicts with account_name, symbol, uncovered contracts, etc.
        """
        try:
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

            from app.modules.strategies.services import get_sold_options_by_account
            from app.core.account_aliases import normalize_account_name, get_all_names_for_account
            sold_by_account = get_sold_options_by_account(self.db)

            uncovered_positions = []
            all_holdings = list(result)
            logger.info(f"[V5] Found {len(all_holdings)} holdings with 100+ shares")

            # Build a lookup that handles account aliases
            canonical_to_sold_key = {}
            for acc_name in sold_by_account.keys():
                canonical = normalize_account_name(acc_name)
                canonical_to_sold_key[canonical] = acc_name
                for alias in get_all_names_for_account(canonical):
                    canonical_to_sold_key[alias.lower().strip()] = acc_name

            for row in all_holdings:
                account_name, symbol, qty, price, value = row
                qty = float(qty) if qty else 0
                options_count = int(qty // 100)

                sold_count = 0
                canonical_holdings_acc = normalize_account_name(account_name)
                actual_sold_account = None

                if account_name in sold_by_account:
                    actual_sold_account = account_name
                elif canonical_holdings_acc in sold_by_account:
                    actual_sold_account = canonical_holdings_acc
                elif canonical_holdings_acc in canonical_to_sold_key:
                    actual_sold_account = canonical_to_sold_key[canonical_holdings_acc]
                elif account_name.lower().strip() in canonical_to_sold_key:
                    actual_sold_account = canonical_to_sold_key[account_name.lower().strip()]

                if actual_sold_account:
                    by_symbol = sold_by_account[actual_sold_account].get("by_symbol", {})
                    if symbol in by_symbol:
                        sold_count = sum(
                            opt["contracts_sold"] for opt in by_symbol[symbol]
                            if opt.get("option_type", "").lower() == "call"
                        )

                uncovered = options_count - sold_count

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

            logger.info(f"[V5] Found {len(uncovered_positions)} uncovered positions")
            return uncovered_positions

        except Exception as e:
            logger.error(f"[V5] Error detecting uncovered positions: {e}", exc_info=True)
            return []

    def _evaluate_single_uncovered(self, position: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Evaluate a single uncovered position for SELL or WAIT."""
        symbol = position["symbol"]

        indicators = self.ta_service.get_technical_indicators(symbol)
        if not indicators:
            logger.warning(f"[V5] No indicators for {symbol}, defaulting to SELL")
            return self._build_sell_notification(position, None, None)

        should_wait, reason, analysis = self.ta_service.should_wait_to_sell(symbol)

        strike_rec = self.ta_service.recommend_strike_price(
            symbol=symbol,
            option_type="call",
            expiration_weeks=1,
            probability_target=0.90
        )

        next_friday = get_next_friday()

        if should_wait:
            return self._build_wait_notification(
                position, indicators, strike_rec, next_friday, reason
            )
        else:
            return self._build_sell_notification(
                position, indicators, strike_rec, next_friday, reason
            )

    def _build_sell_notification(
        self,
        position: Dict[str, Any],
        indicators,
        strike_rec,
        next_friday: date = None,
        reason: str = None
    ) -> Dict[str, Any]:
        """Build a SELL notification for uncovered position."""
        from app.modules.strategies.option_monitor import OptionChainFetcher

        symbol = position["symbol"]
        account_name = position["account_name"]
        uncovered = position["uncovered"]
        current_price = position.get("current_price", 0)

        if next_friday is None:
            next_friday = get_next_friday()

        if strike_rec:
            strike = strike_rec.recommended_strike
            strike_rationale = strike_rec.rationale
        else:
            strike = round(current_price * 1.05, 0)
            strike_rationale = "Estimated 5% OTM (no live data)"

        premium_per_contract = None
        premium_source = "unavailable"

        try:
            option_fetcher = OptionChainFetcher()
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

        if reason:
            full_reason = (
                f"**SELL Covered Call**: {symbol} has {uncovered} uncovered contract(s).\n\n"
                f"**Technical Analysis**: {reason}\n\n"
                f"V5 Philosophy: Every share should be generating weekly income. "
                f"Sell ${strike:.0f} call expiring {next_friday.strftime('%b %d')}."
            )
        else:
            full_reason = (
                f"**SELL Covered Call**: {symbol} has {uncovered} uncovered contract(s).\n\n"
                f"V5 Philosophy: Every share should be generating weekly income."
            )

        if total_premium:
            reason_short = f"{uncovered} {symbol} uncovered - sell ${strike:.0f} call, earn ${total_premium:.0f}"
        else:
            reason_short = f"{uncovered} {symbol} uncovered - sell ${strike:.0f} call"

        # Inline title formatting for SELL
        title = f"Sell {uncovered} {symbol} ${strike:.0f} call {next_friday.strftime('%m/%d')}"
        if total_premium and total_premium > 0:
            title += f" · Earn ${total_premium:.0f}"

        return {
            'id': f"uncovered_sell_{symbol}_{account_name}_{date.today().isoformat()}",
            'symbol': symbol,
            'account_name': account_name,
            'action': 'SELL',
            'action_display': 'Sell',
            'title': title,
            'reason': full_reason,
            'reason_short': reason_short,
            'rationale': full_reason,
            'philosophy': 'weekly_options_income',
            'contracts': uncovered,
            'option_type': 'call',
            'source_strike': strike,
            'source_expiration': next_friday,
            'target_strike': strike,
            'target_expiration': next_friday,
            'target_premium': premium_per_contract,
            'total_premium': total_premium,
            'premium_source': premium_source,
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

    def _build_wait_notification(
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

        if strike_rec:
            strike = strike_rec.recommended_strike
        else:
            strike = round(current_price * 1.05, 0)

        full_reason = (
            f"**WAIT Before Selling**: {symbol} has {uncovered} uncovered contract(s), "
            f"but stock is likely to bounce.\n\n"
            f"**Technical Analysis**: {reason}\n\n"
            f"V5 Philosophy (Tactical Timing): Don't sell calls when stock is DOWN. "
            f"Wait for recovery to capture better premium."
        )

        reason_short = f"{uncovered} {symbol} uncovered - wait for bounce"

        title = f"Wait on {symbol} ({uncovered} uncovered)"

        return {
            'id': f"uncovered_wait_{symbol}_{account_name}_{date.today().isoformat()}",
            'symbol': symbol,
            'account_name': account_name,
            'action': 'WAIT',
            'action_display': 'Wait',
            'title': title,
            'reason': full_reason,
            'reason_short': reason_short,
            'rationale': full_reason,
            'philosophy': 'tactical_timing',
            'contracts': uncovered,
            'option_type': 'call',
            'source_strike': strike,
            'source_expiration': next_friday,
            'target_strike': strike,
            'target_expiration': next_friday,
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
