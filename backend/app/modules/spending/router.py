"""
Spending module API routes.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.modules.spending import services

router = APIRouter()


@router.get("/transactions")
def list_transactions(
    year: Optional[int] = None,
    month: Optional[int] = None,
    category: Optional[str] = None,
    merchant: Optional[str] = None,
    account: Optional[str] = None,
    search: Optional[str] = None,
    spending_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Get filtered, paginated spending transactions.

    spending_type: 'recurring', 'non_monthly', or omit for all.
    """
    return services.get_spending_transactions(
        db,
        year=year,
        month=month,
        category=category,
        merchant=merchant,
        account=account,
        search=search,
        spending_type=spending_type,
        page=page,
        page_size=page_size,
    )


@router.get("/summary/{year}")
def spending_summary(year: int, month: Optional[int] = None,
                     db: Session = Depends(get_db)):
    """Get annual spending summary with category breakdown."""
    return services.get_spending_summary(db, year, month)


@router.get("/categories/{year}")
def spending_categories(year: int, db: Session = Depends(get_db)):
    """Get detailed category breakdown with monthly sub-data."""
    return services.get_spending_categories(db, year)


@router.get("/trends")
def spending_trends(db: Session = Depends(get_db)):
    """Get month-over-month and year-over-year spending trends."""
    return services.get_spending_trends(db)


@router.get("/years")
def available_years(db: Session = Depends(get_db)):
    """Get years that have spending data."""
    years = services.get_available_years(db)
    return {"years": years}


@router.get("/cash-flow/{year}")
def cash_flow_summary(year: int, db: Session = Depends(get_db)):
    """Robinhood CASH_MOVEMENT outflows aggregated by month."""
    return services.get_cash_flow_summary(db, year)


@router.get("/cash-flow/{year}/{month}")
def cash_flow_month(year: int, month: int, db: Session = Depends(get_db)):
    """Robinhood CASH_MOVEMENT transactions for a single month."""
    return services.get_cash_flow_month(db, year, month)


@router.get("/filters")
def filter_options(year: Optional[int] = None, db: Session = Depends(get_db)):
    """Get unique filter values (categories, accounts, merchants)."""
    return services.get_available_filters(db, year)


@router.get("/outflows")
def get_outflows(db: Session = Depends(get_db)):
    """Total spend from investment-account outflows (fresh via MCP sync),
    with Monarch categorized totals alongside for reconciliation.

    Spending definition (Neel, 2026-07-08): money leaving Neel's/Jaya's
    brokerage toward spending channels. Two buckets by description —
    card & spending (XENT_CC balance payments through Oct 2025, then
    'Transfer from Brokerage to Spending'; cash back netted) vs. bank
    transfers out (ACH/RTP to BofA/Chase). Pre-Dec-2025 rows are deduped
    at query time: the backfill double-ingested identical rows under two
    hash schemes (same bug class as the NFLX split incident).
    """
    from sqlalchemy import text
    from app.modules.spending.models import EXCLUDED_CATEGORIES

    rows = db.execute(text("""
        WITH dedup AS (
            SELECT DISTINCT ON (account_id, transaction_date, transaction_type,
                                amount, COALESCE(description,''))
                   account_id, transaction_date, amount, description
            FROM investment_transactions
            WHERE account_id IN ('neel_brokerage','jaya_brokerage')
              AND transaction_type IN ('XENT_CC','XENT','CASH_MOVEMENT','RTP')
              AND transaction_date <= '2025-11-30'
            UNION ALL
            SELECT account_id, transaction_date, amount, description
            FROM investment_transactions
            WHERE account_id IN ('neel_brokerage','jaya_brokerage')
              AND transaction_type IN ('XENT_CC','XENT','CASH_MOVEMENT','RTP')
              AND transaction_date > '2025-11-30'
        )
        SELECT date_trunc('month', transaction_date)::date AS mo,
               account_id,
               SUM(CASE WHEN amount < 0 AND (description ILIKE '%credit card%'
                         OR description ILIKE '%spending%')
                        THEN -amount ELSE 0 END) AS card_spending,
               SUM(CASE WHEN amount > 0 AND description ILIKE '%cash back%'
                        THEN amount ELSE 0 END) AS cashback,
               SUM(CASE WHEN amount < 0 AND NOT (description ILIKE '%credit card%'
                         OR description ILIKE '%spending%')
                        THEN -amount ELSE 0 END) AS bank_out,
               MAX(transaction_date) AS latest
        FROM dedup
        GROUP BY 1, 2 ORDER BY 1
    """)).fetchall()

    # Outflows, plus only the inflows Monarch tagged "Refund:" — same rule as
    # services._base_query. Income/transfers/businesses drop out by category;
    # every other inflow is excluded rather than netted.
    monarch = db.execute(text("""
        SELECT date_trunc('month', transaction_date)::date AS mo,
               SUM(-amount) AS spent
        FROM spending_transactions
        WHERE (category IS NULL OR category NOT IN :excluded)
          AND (amount < 0 OR lower(COALESCE(original_statement,'')) LIKE 'refund:%')
        GROUP BY 1
    """), {"excluded": tuple(EXCLUDED_CATEGORIES)}).fetchall()
    monarch_by_month = {str(r.mo): float(r.spent) for r in monarch}

    monarch_through = db.execute(text(
        "SELECT MAX(transaction_date) FROM spending_transactions")).scalar()

    months: dict = {}
    as_of = None
    for r in rows:
        m = months.setdefault(str(r.mo), {
            "month": str(r.mo), "card_spending": 0.0, "cashback": 0.0,
            "bank_out": 0.0, "by_account": {}})
        card, cb, bank = float(r.card_spending), float(r.cashback), float(r.bank_out)
        m["card_spending"] += card
        m["cashback"] += cb
        m["bank_out"] += bank
        m["by_account"][r.account_id] = round(card - cb + bank, 2)
        if as_of is None or r.latest > as_of:
            as_of = r.latest

    out = []
    for key in sorted(months):
        m = months[key]
        m["total"] = round(m["card_spending"] - m["cashback"] + m["bank_out"], 2)
        m["card_net"] = round(m["card_spending"] - m["cashback"], 2)
        m["monarch_total"] = round(monarch_by_month.get(key, 0.0), 2) or None
        for k in ("card_spending", "cashback", "bank_out"):
            m[k] = round(m[k], 2)
        out.append(m)

    return {
        "as_of": str(as_of) if as_of else None,
        "monarch_through": str(monarch_through) if monarch_through else None,
        "months": out,
    }
