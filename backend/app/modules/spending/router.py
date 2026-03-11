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
def spending_summary(year: int, db: Session = Depends(get_db)):
    """Get annual spending summary with category breakdown."""
    return services.get_spending_summary(db, year)


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
