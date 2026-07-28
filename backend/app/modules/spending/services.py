"""
Spending module services.
Query functions for spending transactions imported from Monarch Money,
plus Robinhood cash-flow queries (CASH_MOVEMENT).
"""

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, desc, and_, or_

from app.modules.spending.models import (
    SpendingTransaction, EXCLUDED_CATEGORIES, NON_MONTHLY_CATEGORIES, TRIPS,
    RENT_CATEGORY, REFUND_STATEMENT_PREFIX, display_category, split_rent_label,
)
from app.modules.investments.models import InvestmentTransaction
from app.modules.strategies.expense_forecasting_service import KNOWN_RECURRING_EXPENSES


def _base_query(db: Session):
    """Rows the Spending page counts: money going OUT, plus genuine refunds.

    The Spending page shows spending and nothing else. Two filters, both
    load-bearing:

    1. Category must be CategoryKind.SPENDING — income, transfers and the
       property/Airbnb businesses are somebody else's page.
    2. The row must be an outflow, OR an inflow Monarch explicitly tagged
       "Refund: <merchant>" (models.is_refund).

    Any other inflow — a bank deposit, a returned security deposit, a tax
    refund — is EXCLUDED, never netted. Letting unmarked inflows net is what
    made June 2026 read $3,437 against $17,750 of actual spending.
    """
    return db.query(SpendingTransaction).filter(
        ~SpendingTransaction.category.in_(EXCLUDED_CATEGORIES),
        or_(
            SpendingTransaction.amount < 0,
            func.lower(SpendingTransaction.original_statement).like(
                f"{REFUND_STATEMENT_PREFIX}%"),
        ),
    )


def _apply_period(q, year: int, month: Optional[int] = None):
    """Scope a query to a year, and to one month when the user picked one.

    Every panel must honour the month selector. Previously `/summary` and
    `/housing` took a year only, so clicking June showed June transactions
    beside year-to-date categories and housing on the same screen.
    """
    q = q.filter(extract("year", SpendingTransaction.transaction_date) == year)
    if month:
        q = q.filter(extract("month", SpendingTransaction.transaction_date) == month)
    return q


def _non_monthly_filter():
    """Build SQLAlchemy filter for non-monthly transactions (trip dates OR non-monthly categories)."""
    trip_conditions = [
        and_(
            SpendingTransaction.transaction_date >= t["start"],
            SpendingTransaction.transaction_date <= t["end"],
        )
        for t in TRIPS
    ]
    in_any_trip = or_(*trip_conditions) if trip_conditions else None

    if in_any_trip is not None:
        return or_(
            in_any_trip,
            and_(~in_any_trip, SpendingTransaction.category.in_(NON_MONTHLY_CATEGORIES)),
        ), in_any_trip
    else:
        return SpendingTransaction.category.in_(NON_MONTHLY_CATEGORIES), None


def get_available_years(db: Session) -> list[int]:
    """Get all years that have spending data."""
    rows = (
        db.query(extract("year", SpendingTransaction.transaction_date).label("yr"))
        .filter(~SpendingTransaction.category.in_(EXCLUDED_CATEGORIES))
        .distinct()
        .order_by(desc("yr"))
        .all()
    )
    return [int(r.yr) for r in rows]


def get_available_filters(db: Session, year: Optional[int] = None) -> dict:
    """Get unique values for filter dropdowns."""
    q = _base_query(db)
    if year:
        q = q.filter(extract("year", SpendingTransaction.transaction_date) == year)

    categories = [
        r[0]
        for r in q.with_entities(SpendingTransaction.category).distinct().order_by(SpendingTransaction.category).all()
        if r[0]
    ]
    accounts = [
        r[0]
        for r in q.with_entities(SpendingTransaction.account).distinct().order_by(SpendingTransaction.account).all()
        if r[0]
    ]
    merchants = [
        r[0]
        for r in q.with_entities(SpendingTransaction.merchant).distinct().order_by(SpendingTransaction.merchant).all()
        if r[0]
    ]
    return {"categories": categories, "accounts": accounts, "merchants": merchants}


def get_spending_transactions(
    db: Session,
    year: Optional[int] = None,
    month: Optional[int] = None,
    category: Optional[str] = None,
    merchant: Optional[str] = None,
    account: Optional[str] = None,
    search: Optional[str] = None,
    spending_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Get filtered, paginated list of spending transactions.

    spending_type: 'recurring' (monthly only), 'non_monthly' (trips/annual only), or None (all).
    """
    q = _base_query(db)

    if year:
        q = q.filter(extract("year", SpendingTransaction.transaction_date) == year)
    if month:
        q = q.filter(extract("month", SpendingTransaction.transaction_date) == month)
    if spending_type:
        nm_filter, _ = _non_monthly_filter()
        if spending_type == "recurring":
            q = q.filter(~nm_filter)
        elif spending_type == "non_monthly":
            q = q.filter(nm_filter)
    if category:
        q = q.filter(SpendingTransaction.category == category)
    if merchant:
        q = q.filter(SpendingTransaction.merchant == merchant)
    if account:
        q = q.filter(SpendingTransaction.account == account)
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            SpendingTransaction.merchant.ilike(pattern)
            | SpendingTransaction.original_statement.ilike(pattern)
            | SpendingTransaction.category.ilike(pattern)
            | SpendingTransaction.notes.ilike(pattern)
        )

    total = q.count()
    rows = (
        q.order_by(desc(SpendingTransaction.transaction_date), desc(SpendingTransaction.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    transactions = []
    for r in rows:
        transactions.append({
            "id": r.id,
            "date": r.transaction_date.isoformat(),
            "merchant": r.merchant,
            "category": r.category,
            "account": r.account,
            "original_statement": r.original_statement,
            "notes": r.notes,
            "amount": float(r.amount),
            "tags": r.tags,
            "owner": r.owner,
        })

    return {
        "transactions": transactions,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


def get_spending_summary(db: Session, year: int, month: Optional[int] = None) -> dict:
    """Totals, category breakdown, top merchants, monthly totals.

    `month` scopes everything to that month — when the user clicks June, every
    figure this returns is June's.
    """
    q = _apply_period(_base_query(db), year, month)

    # Total spending (amounts are negative, so sum is negative)
    total_row = q.with_entities(func.sum(SpendingTransaction.amount)).scalar() or 0
    total_spending = -float(total_row)

    # Monthly totals
    monthly_rows = (
        q.with_entities(
            extract("month", SpendingTransaction.transaction_date).label("month"),
            func.sum(SpendingTransaction.amount).label("total"),
            func.count(SpendingTransaction.id).label("count"),
        )
        .group_by("month")
        .order_by("month")
        .all()
    )

    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    monthly = []
    for r in monthly_rows:
        m = int(r.month)
        monthly.append({
            "month": m,
            "month_name": month_names[m],
            "total": -float(r.total),
            "count": r.count,
        })

    months_with_data = len(monthly)

    # Use shared non-monthly filter
    nm_filter, in_any_trip = _non_monthly_filter()

    # Recurring spending = everything that is NOT non-monthly
    recurring_row = (
        q.filter(~nm_filter)
        .with_entities(func.sum(SpendingTransaction.amount))
        .scalar()
    ) or 0
    recurring_spending = -float(recurring_row)
    non_monthly_spending = total_spending - recurring_spending
    avg_monthly = recurring_spending / months_with_data if months_with_data else 0

    # Annual expenses breakdown: per-trip totals + per-category totals (outside trips)
    annual_expenses = []
    for trip in TRIPS:
        trip_sum = (
            q.filter(
                SpendingTransaction.transaction_date >= trip["start"],
                SpendingTransaction.transaction_date <= trip["end"],
            )
            .with_entities(func.sum(SpendingTransaction.amount))
            .scalar()
        ) or 0
        amt = -float(trip_sum)
        if amt > 0:
            annual_expenses.append({
                "label": trip["name"],
                "type": "trip",
                "total": round(amt, 2),
            })

    # NON_MONTHLY categories (excluding transactions already claimed by trips)
    not_in_trips = ~in_any_trip if in_any_trip is not None else True
    for cat in sorted(NON_MONTHLY_CATEGORIES):
        cat_filter = [SpendingTransaction.category == cat]
        if not_in_trips is not True:
            cat_filter.append(not_in_trips)
        cat_sum = (
            q.filter(*cat_filter)
            .with_entities(func.sum(SpendingTransaction.amount))
            .scalar()
        ) or 0
        amt = -float(cat_sum)
        if amt > 0:
            annual_expenses.append({
                "label": cat,
                "type": "category",
                "total": round(amt, 2),
            })

    # Sort annual expenses by total descending
    annual_expenses.sort(key=lambda x: x["total"], reverse=True)

    # Category breakdown. `Rent` is split by counterparty into the two homes
    # plus one-time search/moving costs (see models.RENT_SPLIT_RULES) — as one
    # line it hid the move between houses entirely.
    cat_rows = (
        q.with_entities(
            SpendingTransaction.category,
            SpendingTransaction.merchant,
            SpendingTransaction.original_statement,
            SpendingTransaction.amount,
        ).all()
    )
    # Group in Python rather than SQL: the displayed category is derived
    # per row (merchant overrides, then the per-home rent split), so a plain
    # GROUP BY on the stored category would report the wrong buckets.
    cat_totals: dict[str, list] = {}
    for r in cat_rows:
        label = display_category(r.category, r.merchant, r.original_statement)
        entry = cat_totals.setdefault(label, [0.0, 0])
        entry[0] += -float(r.amount)
        entry[1] += 1

    categories = []
    for cat_name, (cat_total, count) in sorted(
        cat_totals.items(), key=lambda kv: kv[1][0], reverse=True
    ):
        categories.append({
            "category": cat_name,
            "total": cat_total,
            "count": count,
            "percent": round(cat_total / total_spending * 100, 1) if total_spending else 0,
            "is_monthly": cat_name not in NON_MONTHLY_CATEGORIES,
        })

    top_category = categories[0]["category"] if categories else "N/A"

    # Top merchants
    merch_rows = (
        q.with_entities(
            SpendingTransaction.merchant,
            func.sum(SpendingTransaction.amount).label("total"),
            func.count(SpendingTransaction.id).label("count"),
        )
        .group_by(SpendingTransaction.merchant)
        .order_by(func.sum(SpendingTransaction.amount))
        .limit(20)
        .all()
    )
    top_merchants = []
    for r in merch_rows:
        top_merchants.append({
            "merchant": r.merchant or "Unknown",
            "total": -float(r.total),
            "count": r.count,
        })

    # Month-over-month change
    mom_change = 0.0
    if len(monthly) >= 2:
        prev = monthly[-2]["total"]
        curr = monthly[-1]["total"]
        if prev > 0:
            mom_change = round((curr - prev) / prev * 100, 1)

    return {
        "year": year,
        "total_spending": total_spending,
        "recurring_spending": round(recurring_spending, 2),
        "non_monthly_spending": round(non_monthly_spending, 2),
        "avg_monthly": round(avg_monthly, 2),
        "months_with_data": months_with_data,
        "top_category": top_category,
        "mom_change": mom_change,
        "monthly": monthly,
        "categories": categories,
        "top_merchants": top_merchants,
        "annual_expenses": annual_expenses,
    }


def get_spending_categories(db: Session, year: int) -> dict:
    """Detailed category breakdown with monthly sub-data."""
    q = _base_query(db).filter(
        extract("year", SpendingTransaction.transaction_date) == year
    )

    # Per-category monthly breakdown
    rows = (
        q.with_entities(
            SpendingTransaction.category,
            extract("month", SpendingTransaction.transaction_date).label("month"),
            func.sum(SpendingTransaction.amount).label("total"),
            func.count(SpendingTransaction.id).label("count"),
        )
        .group_by(SpendingTransaction.category, "month")
        .order_by(SpendingTransaction.category, "month")
        .all()
    )

    cat_map: dict[str, dict] = {}
    for r in rows:
        cat = r.category or "Uncategorized"
        if cat not in cat_map:
            cat_map[cat] = {"category": cat, "total": 0, "count": 0, "months": {}}
        amt = -float(r.total)
        cat_map[cat]["total"] += amt
        cat_map[cat]["count"] += r.count
        cat_map[cat]["months"][int(r.month)] = {"total": amt, "count": r.count}

    # Sort by total descending
    categories = sorted(cat_map.values(), key=lambda c: c["total"], reverse=True)

    grand_total = sum(c["total"] for c in categories)
    for c in categories:
        c["percent"] = round(c["total"] / grand_total * 100, 1) if grand_total else 0

    return {"year": year, "categories": categories, "grand_total": grand_total}


def get_spending_trends(db: Session) -> dict:
    """Month-over-month and year-over-year trends."""
    q = _base_query(db)

    rows = (
        q.with_entities(
            extract("year", SpendingTransaction.transaction_date).label("year"),
            extract("month", SpendingTransaction.transaction_date).label("month"),
            func.sum(SpendingTransaction.amount).label("total"),
            func.count(SpendingTransaction.id).label("count"),
        )
        .group_by("year", "month")
        .order_by("year", "month")
        .all()
    )

    month_names = [
        "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]

    monthly_trend = []
    for r in rows:
        monthly_trend.append({
            "year": int(r.year),
            "month": int(r.month),
            "label": f"{month_names[int(r.month)]} {int(r.year)}",
            "total": -float(r.total),
            "count": r.count,
        })

    # Yearly totals
    yearly = {}
    for m in monthly_trend:
        yr = m["year"]
        if yr not in yearly:
            yearly[yr] = {"year": yr, "total": 0, "count": 0}
        yearly[yr]["total"] += m["total"]
        yearly[yr]["count"] += m["count"]

    return {
        "monthly_trend": monthly_trend,
        "yearly_totals": sorted(yearly.values(), key=lambda y: y["year"]),
    }


# ── Robinhood cash-flow helpers ─────────────────────────────

def _cash_flow_base_filter():
    """Return common SQLAlchemy filters for Robinhood CASH_MOVEMENT (both directions)."""
    return [
        InvestmentTransaction.transaction_type == 'CASH_MOVEMENT',
        InvestmentTransaction.account_id.in_(['neel_brokerage', 'jaya_brokerage']),
    ]


def _categorize_cash_flow(description: str) -> str:
    """Categorize a CASH_MOVEMENT transaction by its description."""
    desc_lower = description.lower()
    if 'credit card' in desc_lower:
        return 'Credit Card Payment'
    elif 'brokerage to spending' in desc_lower:
        return 'Transfer to Spending'
    elif 'withdrawal' in desc_lower:
        return 'ACH Withdrawal'
    elif 'bank transfer' in desc_lower:
        return 'Bank Transfer'
    return 'Other'


def get_cash_flow_summary(db: Session, year: int) -> dict:
    """Aggregate Robinhood CASH_MOVEMENT by month — net flow (outflows - inflows)."""
    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]

    # Outflows (negative amounts)
    out_rows = (
        db.query(
            extract('month', InvestmentTransaction.transaction_date).label('month'),
            func.sum(func.abs(InvestmentTransaction.amount)).label('total'),
        )
        .filter(
            extract('year', InvestmentTransaction.transaction_date) == year,
            InvestmentTransaction.amount < 0,
            *_cash_flow_base_filter(),
        )
        .group_by(extract('month', InvestmentTransaction.transaction_date))
        .all()
    )
    out_by_month = {int(r.month): float(r.total or 0) for r in out_rows}

    # Inflows (positive amounts)
    in_rows = (
        db.query(
            extract('month', InvestmentTransaction.transaction_date).label('month'),
            func.sum(InvestmentTransaction.amount).label('total'),
        )
        .filter(
            extract('year', InvestmentTransaction.transaction_date) == year,
            InvestmentTransaction.amount > 0,
            *_cash_flow_base_filter(),
        )
        .group_by(extract('month', InvestmentTransaction.transaction_date))
        .all()
    )
    in_by_month = {int(r.month): float(r.total or 0) for r in in_rows}

    all_months = sorted(set(out_by_month.keys()) | set(in_by_month.keys()))
    monthly = []
    grand_total = 0.0
    for m in all_months:
        outflow = out_by_month.get(m, 0)
        inflow = in_by_month.get(m, 0)
        net = outflow - inflow  # net spending (positive = spent more than received)
        grand_total += net
        monthly.append({
            "month": m,
            "month_name": month_names[m],
            "total": round(net, 2),
            "outflow": round(outflow, 2),
            "inflow": round(inflow, 2),
        })

    # Classify individual outflow transactions for the year (recurring vs one-time)
    one_time_threshold = 15_000
    outflow_txns = (
        db.query(InvestmentTransaction)
        .filter(
            extract('year', InvestmentTransaction.transaction_date) == year,
            InvestmentTransaction.amount < 0,
            *_cash_flow_base_filter(),
        )
        .order_by(InvestmentTransaction.transaction_date)
        .all()
    )

    recurring_total = 0.0
    one_time_total = 0.0
    inflow_total = sum(in_by_month.values())
    outflow_total = sum(out_by_month.values())
    one_time_expenses = []

    for t in outflow_txns:
        amount = abs(float(t.amount))
        tx_type = _categorize_cash_flow(t.description)
        is_one_time = amount >= one_time_threshold and tx_type != 'Credit Card Payment'
        if is_one_time:
            one_time_total += amount
            account_name = "Neel's Brokerage" if t.account_id == 'neel_brokerage' else "Jaya's Brokerage"
            one_time_expenses.append({
                "date": t.transaction_date.isoformat(),
                "account": account_name,
                "amount": amount,
                "description": t.description,
                "type": tx_type,
                "direction": "out",
            })
        else:
            recurring_total += amount

    months_count = len(monthly) or 1
    expected_annual = round(sum(e["amount"] for e in KNOWN_RECURRING_EXPENSES) * months_count, 2)

    return {
        "year": year,
        "monthly": monthly,
        "total": round(grand_total, 2),
        "avg_monthly": round(grand_total / months_count, 2),
        "outflow_total": round(outflow_total, 2),
        "inflow_total": round(inflow_total, 2),
        "recurring_total": round(recurring_total, 2),
        "one_time_total": round(one_time_total, 2),
        "one_time_expenses": one_time_expenses,
        "expected_annual": expected_annual,
        "months_with_data": months_count,
    }


_EARLY_DUE_CUTOFF = 5       # expenses due on or before this day may be paid early
_LATE_MONTH_START = 26      # transactions on or after this day could be early payments
_MATCH_TOLERANCE = 0.30     # 30% tolerance for amount matching


def _early_due_expenses() -> list[dict]:
    """Return known recurring expenses that are due early in the month (day <= 5)."""
    return [e for e in KNOWN_RECURRING_EXPENSES if e["day_of_month"] <= _EARLY_DUE_CUTOFF]


def _matches_early_expense(amount: float) -> bool:
    """Check if a transaction amount approximately matches any early-due expense."""
    for e in _early_due_expenses():
        expected = e["amount"]
        if expected > 0 and abs(amount - expected) / expected <= _MATCH_TOLERANCE:
            return True
    return False


def get_cash_flow_month(db: Session, year: int, month: int) -> dict:
    """Return individual Robinhood CASH_MOVEMENT transactions for a single month,
    classified as recurring vs one-time.

    Smart month attribution: transactions on the 26th+ of the previous month that
    match an early-due recurring expense (day_of_month <= 5) are pulled into the
    current month. Conversely, transactions on the 26th+ of the current month that
    match an early-due expense are excluded (they belong to the next month).
    """
    # Previous month
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    # Query: all transactions in current calendar month + tail of previous month
    current_month_filter = and_(
        extract('year', InvestmentTransaction.transaction_date) == year,
        extract('month', InvestmentTransaction.transaction_date) == month,
    )
    prev_tail_filter = and_(
        extract('year', InvestmentTransaction.transaction_date) == prev_year,
        extract('month', InvestmentTransaction.transaction_date) == prev_month,
        extract('day', InvestmentTransaction.transaction_date) >= _LATE_MONTH_START,
    )

    txns = (
        db.query(InvestmentTransaction)
        .filter(
            or_(current_month_filter, prev_tail_filter),
            *_cash_flow_base_filter(),
        )
        .order_by(InvestmentTransaction.transaction_date.desc())
        .all()
    )

    # One-time = large non-credit-card outflow (ACH withdrawals, brokerage transfers, etc.)
    one_time_threshold = 15_000

    transactions = []
    one_time_expenses = []
    outflow_total = 0.0
    inflow_total = 0.0
    recurring_total = 0.0
    one_time_total = 0.0

    for t in txns:
        raw_amount = float(t.amount)
        amount = abs(raw_amount)
        is_outflow = raw_amount < 0
        tx_day = t.transaction_date.day
        tx_month = t.transaction_date.month
        tx_year = t.transaction_date.year
        is_prev_month = (tx_year == prev_year and tx_month == prev_month)
        is_curr_month = (tx_year == year and tx_month == month)

        # Smart month-shifting only applies to outflows
        if is_outflow:
            matches_early = _matches_early_expense(amount)
            if is_prev_month and not matches_early:
                continue
            if is_curr_month and tx_day >= _LATE_MONTH_START and matches_early:
                continue
        else:
            # Inflows: only include if they fall in the current calendar month
            if not is_curr_month:
                continue

        account_name = "Neel's Brokerage" if t.account_id == 'neel_brokerage' else "Jaya's Brokerage"
        direction = "out" if is_outflow else "in"
        entry = {
            "date": t.transaction_date.isoformat(),
            "account": account_name,
            "amount": amount,
            "description": t.description,
            "type": _categorize_cash_flow(t.description),
            "direction": direction,
        }
        transactions.append(entry)

        if is_outflow:
            outflow_total += amount
            is_one_time = (
                amount >= one_time_threshold
                and entry["type"] != 'Credit Card Payment'
            )
            if is_one_time:
                one_time_expenses.append(entry)
                one_time_total += amount
            else:
                recurring_total += amount
        else:
            inflow_total += amount

    net_total = outflow_total - inflow_total
    expected_total = round(sum(e["amount"] for e in KNOWN_RECURRING_EXPENSES), 2)

    # Expected expenses list (static from config)
    expected_expenses = [
        {
            "description": e["description"],
            "amount": e["amount"],
            "day_of_month": e["day_of_month"],
            "category": e["category"],
        }
        for e in KNOWN_RECURRING_EXPENSES
    ]

    return {
        "year": year,
        "month": month,
        "transactions": transactions,
        "outflow_total": round(outflow_total, 2),
        "inflow_total": round(inflow_total, 2),
        "net_total": round(net_total, 2),
        "recurring_total": round(recurring_total, 2),
        "expected_total": expected_total,
        "expected_expenses": expected_expenses,
        "one_time_expenses": one_time_expenses,
        "one_time_total": round(one_time_total, 2),
    }
