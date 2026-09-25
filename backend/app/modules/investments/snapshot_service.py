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


#: Account types whose "cash" is the whole IRA cash line (no margin).
_IRA_TYPES = ('ira', 'roth_ira', 'retirement', 'hsa', '401k')

#: A cash figure older than this is still used, but flagged in stats and logs
#: so a refresh that stopped running is noticed rather than silently frozen.
_CASH_STALE_AFTER_DAYS = 2


def _signed_cash_by_account(db: Session) -> Dict[str, Dict[str, Any]]:
    """Signed cash per account from the last MCP refresh (`account_cash_balances`).

    Brokerage (margin) accounts: free cash − margin borrowed, so an account on
    margin is negative. IRAs: `margin_total` holds the statement-style "IRA cash"
    total (the refresh stores buying power in `cash_balance`); fall back to
    `cash_balance` when it is missing. Options collateral is a reservation
    against this cash, not extra cash, so it is deliberately not added.
    Returns {account_id: {"cash": Decimal, "as_of": datetime}}.
    """
    rows = db.execute(text("""
        SELECT a.account_id, a.account_type,
               c.cash_balance, c.margin_used, c.margin_total, c.updated_at
        FROM account_cash_balances c
        JOIN investment_accounts a ON a.account_name = c.account_name
    """)).fetchall()
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if r.account_type in _IRA_TYPES:
            cash = r.margin_total if r.margin_total is not None else (r.cash_balance or 0)
        else:
            cash = (r.cash_balance or 0) - (r.margin_used or 0)
        out[r.account_id] = {"cash": Decimal(str(cash)), "as_of": r.updated_at}
    return out


def _short_option_marks_by_account(db: Session) -> Dict[str, Decimal]:
    """Mark-to-market liability of open short options per account, from the
    latest `sold_options_snapshots` paste (which the MCP refresh writes).
    Statements fold this into "Total Securities"; so does the daily snapshot.
    Returns {account_id: positive liability}."""
    rows = db.execute(text("""
        SELECT a.account_id,
               COALESCE(SUM(o.premium_per_contract * 100 * o.contracts_sold), 0) AS liability
        FROM sold_options o
        JOIN sold_options_snapshots s ON s.id = o.snapshot_id
        JOIN investment_accounts a ON a.account_name = s.account_name
        WHERE o.status = 'open'
          AND s.id IN (SELECT MAX(id) FROM sold_options_snapshots GROUP BY account_name)
        GROUP BY a.account_id
    """)).fetchall()
    return {r.account_id: Decimal(str(r.liability)) for r in rows}


def refresh_today_snapshot(db: Session, account_id: str, snapshot_date: date = None) -> Dict[str, Any]:
    """Recompute one account's snapshot row for today from the stored holdings'
    market values, open short-option marks and the last refresh's signed cash —
    the same definition as take_daily_snapshot, without a price fetch.

    Called by the MCP refresh after its holdings paste and after its cash save
    (whichever lands last wins, and both agree). Before 2026-09-25 the paste
    save wrote securities-only with cash 0, overwriting the 8:15 PM value
    several times a day. Returns the values written, or {} if the account is
    unknown. Does not commit."""
    today = snapshot_date or date.today()
    account = db.query(InvestmentAccount).filter(InvestmentAccount.account_id == account_id).first()
    if not account:
        return {}
    holdings = db.query(InvestmentHolding).filter(
        InvestmentHolding.account_id == account_id,
        InvestmentHolding.quantity > 0,
    ).all()
    equities = sum((Decimal(str(h.market_value or 0)) for h in holdings if h.symbol != 'CASH'), Decimal("0"))
    holding_cash = next((h.quantity for h in holdings if h.symbol == 'CASH'), Decimal("0"))
    securities_value = equities - _short_option_marks_by_account(db).get(account_id, Decimal("0"))
    cash_map = _signed_cash_by_account(db)
    cash_balance = cash_map[account_id]["cash"] if account_id in cash_map else holding_cash
    portfolio_value = securities_value + cash_balance

    db.execute(text("""
        INSERT INTO portfolio_snapshots
            (source, account_id, owner, account_type, statement_date,
             portfolio_value, cash_balance, securities_value, created_at, updated_at)
        VALUES (:source, :account_id, :owner, :account_type, :statement_date,
                :portfolio_value, :cash_balance, :securities_value, NOW(), NOW())
        ON CONFLICT ON CONSTRAINT uq_portfolio_snapshot
        DO UPDATE SET
            portfolio_value = EXCLUDED.portfolio_value,
            cash_balance = EXCLUDED.cash_balance,
            securities_value = EXCLUDED.securities_value,
            updated_at = NOW()
    """), {
        "source": account.source, "account_id": account_id,
        "owner": account_id.split('_')[0].title() if '_' in account_id else 'Unknown',
        "account_type": account.account_type, "statement_date": today,
        "portfolio_value": float(portfolio_value), "cash_balance": float(cash_balance),
        "securities_value": float(securities_value),
    })
    return {"portfolio_value": float(portfolio_value), "cash_balance": float(cash_balance),
            "securities_value": float(securities_value)}


def take_daily_snapshot(db: Session) -> Dict[str, Any]:
    """
    Take a daily snapshot of all portfolio holdings and values.

    1. Fetches all active holdings with quantity > 0
    2. Gets current prices via Schwab (batch) with Yahoo fallback
    3. Upserts per-holding rows into investment_holdings_history
    4. Aggregates per-account totals and upserts into portfolio_snapshots

    portfolio_value is net liquidation value, the same quantity a statement
    prints (docs/BBD-CALCULATIONS.md, "Portfolio value"):

        securities_value = shares × price − open short-option marks
        cash_balance     = signed cash from the last MCP refresh
                           (negative when on margin)
        portfolio_value  = securities_value + cash_balance

    Before 2026-09-25 this wrote securities only with cash_balance = 0, which
    made margin borrowing read as growth once daily rows replaced statement
    rows in the series (BBD audit F1). Accounts with no MCP cash row fall back
    to a CASH holding row, as before.

    Returns stats dict with counts and values.
    """
    today = date.today()
    stats = {
        "snapshot_date": today.isoformat(),
        "holdings_snapshot": 0,
        "accounts_snapshot": 0,
        "symbols_priced": 0,
        "total_portfolio_value": 0.0,
        "cash_source": {},
        "stale_cash_accounts": [],
    }

    cash_map = _signed_cash_by_account(db)
    option_marks = _short_option_marks_by_account(db)

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
        holding_cash = Decimal("0")

        for h in acct_holdings:
            qty = h.quantity or Decimal("0")
            symbol = h.symbol

            if symbol == 'CASH':
                holding_cash = qty
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

        # Short options are a liability inside "securities", as on a statement.
        securities_value -= option_marks.get(account_id, Decimal("0"))

        # Signed cash: MCP refresh first, CASH holding row as the fallback.
        if account_id in cash_map:
            cash_balance = cash_map[account_id]["cash"]
            stats["cash_source"][account_id] = "mcp_refresh"
            as_of = cash_map[account_id]["as_of"]
            if as_of and (datetime.utcnow() - as_of).days >= _CASH_STALE_AFTER_DAYS:
                stats["stale_cash_accounts"].append(account_id)
                logger.warning(
                    f"[SNAPSHOT] {account_id}: cash from refresh is "
                    f"{(datetime.utcnow() - as_of).days} days old ({as_of:%Y-%m-%d})"
                )
        else:
            cash_balance = holding_cash
            stats["cash_source"][account_id] = "holding"

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
