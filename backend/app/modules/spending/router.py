"""
Spending module API routes.

Every figure comes from services.spending_rows() — one definition. The old
/cash-flow/* endpoints (brokerage CASH_MOVEMENT only, no dedup, month
attribution shifted by a stale hardcoded expense list) and the unused
/categories and /trends were removed on 2026-09-06; they gave the page a
second and third total that disagreed with the first.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

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
    """Filtered, paginated spending rows. `category` is a display label.
    spending_type: 'recurring', 'non_monthly', or omit for all."""
    return services.get_spending_transactions(
        db, year=year, month=month, category=category, merchant=merchant,
        account=account, search=search, spending_type=spending_type,
        page=page, page_size=page_size,
    )


@router.get("/summary/{year}")
def spending_summary(year: int, month: Optional[int] = None,
                     db: Session = Depends(get_db)):
    """Period totals, monthly series, categories, merchants, accounts, flags."""
    return services.get_spending_summary(db, year, month)


@router.get("/years")
def available_years(db: Session = Depends(get_db)):
    return {"years": services.get_available_years(db)}


@router.get("/filters")
def filter_options(year: Optional[int] = None, db: Session = Depends(get_db)):
    return services.get_available_filters(db, year)


@router.get("/freshness")
def freshness(db: Session = Depends(get_db)):
    """Per-account tails over all history, outflow tail, last complete month."""
    return services.get_freshness(db)


@router.get("/outflows")
def get_outflows(db: Session = Depends(get_db)):
    """Brokerage outflows by month with the categorized total alongside —
    the reconciliation line, not the headline."""
    return services.get_outflows(db)
