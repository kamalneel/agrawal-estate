"""
Daily portfolio snapshot service.

Takes automated snapshots of portfolio holdings and values,
populating portfolio_snapshots and investment_holdings_history tables.
Runs daily at 8:15 PM PT via cron, after market close.
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.modules.investments.models import (
    InvestmentAccount,
    InvestmentHolding,
    InvestmentHoldingHistory,
    PortfolioSnapshot,
)
from app.modules.investments.price_service import get_prices_schwab_first

logger = logging.getLogger(__name__)


def take_daily_snapshot(db: Session) -> Dict[str, Any]:
    """
    Take a daily snapshot of all portfolio holdings and values.

    1. Fetches all active holdings with quantity > 0
    2. Gets current prices via Schwab (batch) with Yahoo fallback
    3. Upserts per-holding rows into investment_holdings_history
    4. Aggregates per-account totals and upserts into portfolio_snapshots
    5. Populates cash_balance from CASH holding rows

    Returns stats dict with counts and values.
    """
    today = date.today()
    stats = {
        "snapshot_date": today.isoformat(),
        "holdings_snapshot": 0,
        "accounts_snapshot": 0,
        "symbols_priced": 0,
        "total_portfolio_value": 0.0,
    }

    # Get all active accounts
    accounts = db.query(InvestmentAccount).filter(
        InvestmentAccount.is_active == 'Y'
    ).all()
    account_map = {a.account_id: a for a in accounts}

    if not accounts:
        logger.warning("[SNAPSHOT] No active accounts found")
        return stats

    # Get all holdings with quantity > 0
    holdings = db.query(InvestmentHolding).filter(
        InvestmentHolding.quantity > 0
    ).all()

    if not holdings:
        logger.warning("[SNAPSHOT] No holdings found")
        return stats

    # Collect unique stock symbols (exclude CASH)
    symbols = list(set(
        h.symbol for h in holdings
        if h.symbol and h.symbol != 'CASH'
    ))

    # Fetch prices in one batch call
    price_map = {}
    if symbols:
        raw_prices = get_prices_schwab_first(symbols)
        for sym, data in raw_prices.items():
            if data and data.get("current_price"):
                price_map[sym] = float(data["current_price"])
        stats["symbols_priced"] = len(price_map)
        logger.info(f"[SNAPSHOT] Got prices for {len(price_map)}/{len(symbols)} symbols")

    # Group holdings by account
    account_holdings: Dict[str, list] = {}
    for h in holdings:
        account_holdings.setdefault(h.account_id, []).append(h)

    # Process each account
    for account_id, acct_holdings in account_holdings.items():
        if account_id not in account_map:
            continue

        account = account_map[account_id]
        securities_value = Decimal("0")
        cash_balance = Decimal("0")

        for h in acct_holdings:
            qty = h.quantity or Decimal("0")
            symbol = h.symbol

            if symbol == 'CASH':
                cash_balance = qty
                continue

            # Get price: live price > stored price
            price = price_map.get(symbol)
            if price is None and h.current_price:
                price = float(h.current_price)
            if price is None:
                continue

            market_value = float(qty) * price
            securities_value += Decimal(str(round(market_value, 2)))

            # Upsert into investment_holdings_history
            db.execute(text("""
                INSERT INTO investment_holdings_history
                    (source, account_id, symbol, snapshot_date, quantity, market_value, created_at, updated_at)
                VALUES
                    (:source, :account_id, :symbol, :snapshot_date, :quantity, :market_value, NOW(), NOW())
                ON CONFLICT ON CONSTRAINT uq_holding_history
                DO UPDATE SET
                    quantity = EXCLUDED.quantity,
                    market_value = EXCLUDED.market_value,
                    updated_at = NOW()
            """), {
                "source": h.source,
                "account_id": account_id,
                "symbol": symbol,
                "snapshot_date": today,
                "quantity": float(qty),
                "market_value": round(market_value, 2),
            })
            stats["holdings_snapshot"] += 1

        portfolio_value = securities_value + cash_balance

        # Upsert into portfolio_snapshots
        db.execute(text("""
            INSERT INTO portfolio_snapshots
                (source, account_id, owner, account_type, statement_date,
                 portfolio_value, cash_balance, securities_value,
                 created_at, updated_at)
            VALUES
                (:source, :account_id, :owner, :account_type, :statement_date,
                 :portfolio_value, :cash_balance, :securities_value,
                 NOW(), NOW())
            ON CONFLICT ON CONSTRAINT uq_portfolio_snapshot
            DO UPDATE SET
                portfolio_value = EXCLUDED.portfolio_value,
                cash_balance = EXCLUDED.cash_balance,
                securities_value = EXCLUDED.securities_value,
                owner = EXCLUDED.owner,
                account_type = EXCLUDED.account_type,
                updated_at = NOW()
        """), {
            "source": account.source,
            "account_id": account_id,
            "owner": account_id.split('_')[0].title() if '_' in account_id else 'Unknown',
            "account_type": account.account_type,
            "statement_date": today,
            "portfolio_value": float(portfolio_value),
            "cash_balance": float(cash_balance),
            "securities_value": float(securities_value),
        })
        stats["accounts_snapshot"] += 1
        stats["total_portfolio_value"] += float(portfolio_value)

    db.commit()
    logger.info(
        f"[SNAPSHOT] Daily snapshot complete: {stats['accounts_snapshot']} accounts, "
        f"{stats['holdings_snapshot']} holdings, total ${stats['total_portfolio_value']:,.0f}"
    )
    return stats
