"""
Spending module services.

ONE definition of "spending", consumed by every endpoint on the page, by the
outflow reconciliation, and by the BBD model: `spending_rows()`. It loads the
Monarch rows for a period and runs each through `models.classify`, which
decides — in this order — counterparty rule, refund, kind, display label.

Aggregation happens in Python, not SQL. The table is ~4,000 rows and the
rulebook (counterparty, merchant overrides, rent split, refund pairing) is
per-row logic that SQL cannot express; grouping on the stored category was
exactly how the page came to disagree with itself. See
docs/SPENDING-PAGE-AUDIT-2026-09.md for the incidents behind each rule.
"""

from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import extract, func, text
from sqlalchemy.orm import Session

from app.modules.spending.models import (
    ACCOUNT_NAMES,
    ACCOUNT_ORDER,
    EXPECTED_MONTHLY_LABELS,
    NON_MONTHLY_CATEGORIES,
    RETIRED_ACCOUNTS,
    TRIPS,
    CategoryKind,
    SpendingTransaction,
    classify,
)

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

#: Brokerage accounts whose cash movements are the "how much" side.
OUTFLOW_ACCOUNTS = ("neel_brokerage", "jaya_brokerage")

#: How many days an account may trail the newest Monarch row before its
#: stamp turns amber (project-kb: check-freshness-and-ask-first).
FRESHNESS_LAG_DAYS = 7
#: Beyond this an unretired account is reported as dead, not lagging.
FRESHNESS_DEAD_DAYS = 30


# ── The one definition ──────────────────────────────────────────────────

def _trip_for(d: date) -> Optional[str]:
    for t in TRIPS:
        if t["start"] <= d <= t["end"]:
            return t["name"]
    return None


def _norm_merchant(m: Optional[str]) -> str:
    m = (m or "").strip().lower()
    # "Refund Emirates Airlines" is Monarch's merchant for the refund of an
    # "Emirates Airlines" charge; strip every spelling so the two pair.
    for prefix in ("refund: ", "refund from ", "refund "):
        if m.startswith(prefix):
            m = m[len(prefix):]
    return m


def _pair_misfiled_refunds(rows: list[dict]) -> None:
    """A refund Monarch filed as INCOME has no category of its own. Give it
    the label of the charge it reverses (same merchant, same amount) so the
    two net to zero on one line, as they would have if Monarch had filed the
    refund correctly. No partner -> 'Refunds', visibly."""
    charges: dict[tuple, str] = {}
    for r in rows:
        if r["amount"] < 0:
            charges.setdefault((_norm_merchant(r["merchant"]),
                                round(-r["amount"], 2)), r["label"])
    for r in rows:
        if r["is_refund"] and r["kind"] == CategoryKind.INCOME.value:
            r["label"] = charges.get(
                (_norm_merchant(r["merchant"]), round(r["amount"], 2)),
                "Refunds")
            r["misfiled_refund"] = True


#: A fixed monthly bill paid on or after this day is for the FOLLOWING month.
#: Rent for August was wired on 2026-07-31; by transaction date July carried
#: two rents and August none, which both misstates each month and trips the
#: missing-recurring flag. Project-kb: attribute-income-to-its-stated-period
#: — the same rule, applied to the fixed bills in EXPECTED_MONTHLY_LABELS
#: only. Everything else stays on its transaction date.
EARLY_PAYMENT_DAY = 25


def _period_of(label: str, d: date) -> tuple[int, int]:
    if label in EXPECTED_MONTHLY_LABELS and d.day >= EARLY_PAYMENT_DAY:
        nxt = (d.replace(day=1) + timedelta(days=32))
        return nxt.year, nxt.month
    return d.year, d.month


def spending_rows(db: Session, year: Optional[int] = None,
                  month: Optional[int] = None,
                  since: Optional[date] = None) -> list[dict]:
    """Every row the Spending page counts, newest first, already classified
    and stamped with the (year, month) period it belongs to."""
    q = db.query(SpendingTransaction)
    # Load a week of the previous month too, so an early-paid bill can be
    # attributed into the requested period; the period filter below is exact.
    if year and month:
        lo = date(year, month, 1) - timedelta(days=7)
        hi = (date(year, month, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        q = q.filter(SpendingTransaction.transaction_date.between(lo, hi))
    elif year:
        q = q.filter(SpendingTransaction.transaction_date.between(
            date(year, 1, 1) - timedelta(days=7), date(year, 12, 31)))
    if since:
        q = q.filter(SpendingTransaction.transaction_date >= since)
    q = q.order_by(SpendingTransaction.transaction_date.desc(),
                   SpendingTransaction.id.desc())

    out = []
    for r in q.all():
        c = classify(r.category, r.merchant, r.original_statement, r.amount)
        if not c.counted:
            continue
        period = _period_of(c.label, r.transaction_date)
        if year and period[0] != year:
            continue
        if month and period[1] != month:
            continue
        trip = _trip_for(r.transaction_date)
        out.append({
            "id": r.id,
            "date": r.transaction_date,
            "period": period,
            "merchant": r.merchant,
            "raw_category": r.category,
            "label": c.label,
            "account": r.account,
            "original_statement": r.original_statement,
            "notes": r.notes,
            "amount": float(r.amount),
            "tags": r.tags,
            "owner": r.owner,
            "kind": c.kind.value,
            "is_refund": c.is_refund,
            "misfiled_refund": False,
            "trip": trip,
            "is_non_monthly": trip is not None or c.label in NON_MONTHLY_CATEGORIES,
        })
    _pair_misfiled_refunds(out)
    return out


def monthly_spending_totals(db: Session, since: Optional[date] = None) -> dict[str, float]:
    """{YYYY-MM: spend} — the BBD model's input, same definition as the page."""
    totals: dict[str, float] = defaultdict(float)
    for r in spending_rows(db, since=since):
        totals["%04d-%02d" % r["period"]] += -r["amount"]
    return dict(sorted(totals.items()))


# ── Freshness ───────────────────────────────────────────────────────────

def _monarch_through(db: Session) -> Optional[date]:
    """Newest row from a MONARCH export. Rows tagged rh_csv (Robinhood's own
    downloads, used to fill holes and the tail) are excluded: they make one
    account fresher than the export, and judging the other accounts against
    that date made them all read 'lagging' on 2026-09-10."""
    return (db.query(func.max(SpendingTransaction.transaction_date))
            .filter(SpendingTransaction.tags.is_distinct_from("rh_csv")).scalar())


def _data_through(db: Session) -> Optional[date]:
    """Newest row from any source — how far the page's data actually runs."""
    return db.query(func.max(SpendingTransaction.transaction_date)).scalar()


def _last_complete_month(through: Optional[date]) -> Optional[tuple[int, int]]:
    """(year, month) of the last month Monarch fully covers. A month is
    complete once the export reaches its last day."""
    if not through:
        return None
    nxt = (through.replace(day=1) + timedelta(days=32)).replace(day=1)
    if nxt - timedelta(days=1) == through:
        return through.year, through.month
    prev_end = through.replace(day=1) - timedelta(days=1)
    return prev_end.year, prev_end.month


def _account_dates(db: Session) -> dict[str, list[date]]:
    """Every distinct transaction day per account, over ALL history."""
    rows = (
        db.query(SpendingTransaction.account, SpendingTransaction.transaction_date)
        .distinct().order_by(SpendingTransaction.account,
                             SpendingTransaction.transaction_date).all()
    )
    out: dict[str, list[date]] = defaultdict(list)
    for name, d in rows:
        if name:
            out[name].append(d)
    return out


def _typical_gap(dates: list[date]) -> int:
    """Median days between transaction days over the account's last 180
    days — its own rhythm. A card used every two weeks is not 'lagging' at
    twelve days; a flat threshold flagged Costco Citi and the business
    account on 2026-09-06 while both were simply quiet."""
    last = dates[-1]
    recent = [d for d in dates if d >= last - timedelta(days=180)]
    gaps = sorted((b - a).days for a, b in zip(recent, recent[1:]))
    return gaps[len(gaps) // 2] if gaps else FRESHNESS_LAG_DAYS


#: A silence this many times longer than an account's typical gap, INSIDE a
#: period, is a hole — the feed dropped and reconnected (project-kb:
#: check-freshness-and-ask-first, "a hole in the middle, not a short tail").
#: July 2026: the Robinhood card had 44 rows Jul 1-8, none Jul 9-25, 25 rows
#: Jul 26-31. The month read $5.7K of card spend against a $13K norm.
HOLE_MULTIPLE = 4
#: Only an account used every day can be judged this way — in practice the
#: family card. Bank and savings accounts with a 2–5 day rhythm go quiet for
#: three weeks quite normally: the first pass produced 18 false holes for
#: 2026, and Robinhood checking's own CSV confirmed its Jul 9-29 silence was
#: real.
HOLE_MAX_TYPICAL_GAP = 1
HOLE_MIN_DAYS = 12


def find_holes(db: Session, year: int, month: Optional[int]) -> list[dict]:
    """Gaps inside the period, for daily-use accounts, longer than
    HOLE_MULTIPLE times the account's own rhythm (and at least
    HOLE_MIN_DAYS). Checked over the period's whole span including its
    edges, so a feed that stopped mid-month is caught too."""
    if month:
        start = date(year, month, 1)
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    else:
        start, end = date(year, 1, 1), date(year, 12, 31)
    through = _data_through(db)
    if through and through < end:
        end = through
    holes = []
    for name, dates in _account_dates(db).items():
        if name in RETIRED_ACCOUNTS or dates[0] > end or dates[-1] < start:
            continue
        typical = _typical_gap(dates)
        if typical > HOLE_MAX_TYPICAL_GAP:
            continue
        limit = max(HOLE_MIN_DAYS, HOLE_MULTIPLE * typical)
        inside = [d for d in dates if start <= d <= end]
        # Bound the span by the last row before and first row after the
        # period, so an account quiet across the edge is judged fairly.
        before = [d for d in dates if d < start]
        after = [d for d in dates if d > end]
        span = ([before[-1]] if before else []) + inside + ([after[0]] if after else [])
        for a, b in zip(span, span[1:]):
            gap = (b - a).days
            if gap > limit:
                lo, hi = max(a + timedelta(days=1), start), min(b - timedelta(days=1), end)
                if lo <= hi:
                    holes.append({
                        "account": name,
                        "display": ACCOUNT_NAMES.get(name, name),
                        "from": lo.isoformat(), "to": hi.isoformat(),
                        "days": (hi - lo).days + 1,
                        "typical_gap_days": typical,
                    })
    return sorted(holes, key=lambda h: -h["days"])


def get_freshness(db: Session) -> dict:
    """Per-account tails over ALL history (a dead account drops out of any
    windowed query), the outflow tail, and the last complete month."""
    through = _monarch_through(db)
    dates_by_acct = _account_dates(db)

    accounts = []
    for name, dates in dates_by_acct.items():
        last = dates[-1]
        median_gap = _typical_gap(dates)
        expected = max(FRESHNESS_LAG_DAYS, 2 * median_gap)
        behind = (through - last).days if through else None
        if name in RETIRED_ACCOUNTS:
            status = "retired"
        elif behind is None or behind <= expected:
            status = "live"
        elif behind <= max(FRESHNESS_DEAD_DAYS, 3 * median_gap):
            status = "lagging"
        else:
            status = "dead"
        accounts.append({
            "account": name,
            "display": ACCOUNT_NAMES.get(name, name),
            "last_date": last.isoformat(),
            "days_behind": behind,
            "typical_gap_days": median_gap,
            "rows": len(dates),
            "status": status,
            "note": RETIRED_ACCOUNTS.get(name),
        })
    accounts.sort(key=lambda a: (ACCOUNT_ORDER.get(a["account"], 99), a["account"]))

    out_rows = db.execute(text("""
        SELECT account_id, MAX(transaction_date)
        FROM investment_transactions
        WHERE account_id IN :accts
          AND transaction_type IN ('CASH_MOVEMENT','XENT_CC','XENT','RTP')
        GROUP BY account_id
    """), {"accts": OUTFLOW_ACCOUNTS}).fetchall()
    outflows = {r[0]: r[1].isoformat() for r in out_rows}
    outflows_through = max(outflows.values()) if outflows else None

    lcm = _last_complete_month(through)
    today = date.today()
    # Cash movements come from the MONTHLY statement (project-kb:
    # check-freshness-and-ask-first: judge a statement-fed stream by "is the
    # last completed month imported?", never by the age of its newest row).
    # Current = there is a cash row in or after the last complete month.
    outflows_current = bool(
        lcm and outflows_through
        and date.fromisoformat(outflows_through) >= date(lcm[0], lcm[1], 1))
    data_through = _data_through(db)
    return {
        "monarch_through": through.isoformat() if through else None,
        "monarch_days_old": (today - through).days if through else None,
        "data_through": data_through.isoformat() if data_through else None,
        "outflows_through": outflows_through,
        "outflows_by_account": outflows,
        "outflows_current": outflows_current,
        "outflows_statement_month": MONTH_NAMES[lcm[1]] if lcm else None,
        "outflows_days_behind_monarch": (
            (through - date.fromisoformat(outflows_through)).days
            if through and outflows_through else None),
        "last_complete_month": (
            {"year": lcm[0], "month": lcm[1]} if lcm else None),
        "accounts": accounts,
        "problems": [a for a in accounts if a["status"] in ("lagging", "dead")],
    }


# ── Page queries ────────────────────────────────────────────────────────

def get_available_years(db: Session) -> list[int]:
    rows = (
        db.query(extract("year", SpendingTransaction.transaction_date).label("yr"))
        .distinct().order_by(text("yr DESC")).all()
    )
    return [int(r.yr) for r in rows]


def get_available_filters(db: Session, year: Optional[int] = None) -> dict:
    """Filter values in DISPLAY terms — the same labels the category table
    shows, so clicking a row and picking from the dropdown agree."""
    rows = spending_rows(db, year)
    labels = sorted({r["label"] for r in rows})
    accounts = sorted({r["account"] for r in rows if r["account"]},
                      key=lambda a: (ACCOUNT_ORDER.get(a, 99), a))
    merchants = sorted({r["merchant"] for r in rows if r["merchant"]})
    return {
        "categories": labels,
        "accounts": [{"account": a, "display": ACCOUNT_NAMES.get(a, a)}
                     for a in accounts],
        "merchants": merchants,
    }


def _txn_out(r: dict) -> dict:
    return {
        "id": r["id"],
        "date": r["date"].isoformat(),
        "period": "%04d-%02d" % r["period"],
        "merchant": r["merchant"],
        "category": r["label"],
        "raw_category": r["raw_category"],
        "account": r["account"],
        "account_display": ACCOUNT_NAMES.get(r["account"], r["account"]),
        "original_statement": r["original_statement"],
        "notes": r["notes"],
        "amount": r["amount"],
        "tags": r["tags"],
        "owner": r["owner"],
        "is_refund": r["is_refund"],
        "misfiled_refund": r["misfiled_refund"],
        "trip": r["trip"],
        "is_non_monthly": r["is_non_monthly"],
    }


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
    """Filtered, paginated rows. `category` is a DISPLAY label.

    spending_type: 'recurring', 'non_monthly', or None for all.
    """
    rows = spending_rows(db, year, month)
    if spending_type == "recurring":
        rows = [r for r in rows if not r["is_non_monthly"]]
    elif spending_type == "non_monthly":
        rows = [r for r in rows if r["is_non_monthly"]]
    if category:
        rows = [r for r in rows if r["label"] == category]
    if merchant:
        rows = [r for r in rows if r["merchant"] == merchant]
    if account:
        rows = [r for r in rows if r["account"] == account]
    if search:
        s = search.lower()
        rows = [r for r in rows if any(
            s in (v or "").lower() for v in (
                r["merchant"], r["original_statement"], r["label"],
                r["raw_category"], r["notes"]))]

    total = len(rows)
    start = (page - 1) * page_size
    return {
        "transactions": [_txn_out(r) for r in rows[start:start + page_size]],
        "total": total,
        "total_amount": round(-sum(r["amount"] for r in rows), 2),
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


def get_spending_summary(db: Session, year: int, month: Optional[int] = None) -> dict:
    """Everything the page's upper levels need for one period, from one row
    set, so every figure ties to the headline to the cent."""
    rows = spending_rows(db, year, month)
    through = _monarch_through(db)
    lcm = _last_complete_month(through)

    total = -sum(r["amount"] for r in rows)
    recurring = -sum(r["amount"] for r in rows if not r["is_non_monthly"])
    non_monthly = total - recurring

    # Monthly series — recurring and non-monthly split so the trend chart
    # can stack them and still sum to the headline.
    by_month: dict[int, dict] = {}
    for r in rows:
        mo = r["period"][1]
        m = by_month.setdefault(mo, {
            "month": mo, "month_name": MONTH_NAMES[mo],
            "total": 0.0, "recurring": 0.0, "non_monthly": 0.0, "count": 0})
        m["total"] += -r["amount"]
        m["count"] += 1
        if r["is_non_monthly"]:
            m["non_monthly"] += -r["amount"]
        else:
            m["recurring"] += -r["amount"]
    monthly = [dict(v, total=round(v["total"], 2), recurring=round(v["recurring"], 2),
                    non_monthly=round(v["non_monthly"], 2))
               for _, v in sorted(by_month.items())]
    months_with_data = len(monthly)

    # Categories by display label. Every label is listed — the month view
    # used to hide non-monthly ones with no indicator, so March's visible
    # categories summed to $16K under an $81K headline.
    cats: dict[str, dict] = {}
    for r in rows:
        c = cats.setdefault(r["label"], {"category": r["label"], "total": 0.0,
                                         "count": 0, "refunds": 0.0})
        c["total"] += -r["amount"]
        c["count"] += 1
        if r["amount"] > 0:
            c["refunds"] += r["amount"]
    categories = []
    for c in sorted(cats.values(), key=lambda c: c["total"], reverse=True):
        categories.append({
            "category": c["category"],
            "total": round(c["total"], 2),
            "count": c["count"],
            "refunds": round(c["refunds"], 2),
            "percent": round(c["total"] / total * 100, 1) if total else 0,
            "is_monthly": c["category"] not in NON_MONTHLY_CATEGORIES,
        })

    # Non-monthly breakdown: trips first (all spend inside the window,
    # whatever its category), then the non-monthly categories outside trips.
    nm: dict[str, dict] = {}
    for r in rows:
        if not r["is_non_monthly"]:
            continue
        key = r["trip"] or r["label"]
        e = nm.setdefault(key, {"label": key, "type": "trip" if r["trip"] else "category",
                                "total": 0.0, "count": 0})
        e["total"] += -r["amount"]
        e["count"] += 1
    non_monthly_breakdown = [dict(e, total=round(e["total"], 2))
                             for e in sorted(nm.values(), key=lambda e: e["total"],
                                             reverse=True)]

    # Merchants. Where the money actually goes; was computed and never shown.
    merch: dict[str, dict] = {}
    for r in rows:
        key = r["merchant"] or "Unknown"
        e = merch.setdefault(key, {"merchant": key, "total": 0.0, "count": 0,
                                   "labels": defaultdict(int)})
        e["total"] += -r["amount"]
        e["count"] += 1
        e["labels"][r["label"]] += 1
    top_merchants = []
    for e in sorted(merch.values(), key=lambda e: e["total"], reverse=True)[:15]:
        top_merchants.append({
            "merchant": e["merchant"], "total": round(e["total"], 2),
            "count": e["count"],
            "category": max(e["labels"].items(), key=lambda kv: kv[1])[0],
        })

    # Accounts, in the fixed display order — never by amount.
    accts: dict[str, dict] = {}
    for r in rows:
        key = r["account"] or "Unknown"
        e = accts.setdefault(key, {"account": key, "display": ACCOUNT_NAMES.get(key, key),
                                   "total": 0.0, "count": 0})
        e["total"] += -r["amount"]
        e["count"] += 1
    by_account = [dict(e, total=round(e["total"], 2)) for e in sorted(
        accts.values(), key=lambda e: (ACCOUNT_ORDER.get(e["account"], 99), e["account"]))]

    # Flags — data that needs a decision, surfaced rather than silently
    # counted (playbook: never silently wrong).
    uncat = [r for r in rows if r["label"] == "Uncategorized"]
    misfiled = [r for r in rows if r["misfiled_refund"]]
    flags = {
        "uncategorized": {"count": len(uncat),
                          "total": round(-sum(r["amount"] for r in uncat), 2)},
        "misfiled_refunds": {"count": len(misfiled),
                             "total": round(sum(r["amount"] for r in misfiled), 2)},
        "missing_recurring": [],
        "holes": find_holes(db, year, month),
    }
    # Missing-recurring detector, complete months only: a month without rent
    # or school is a data defect until proven otherwise (Jul/Aug 2026).
    if lcm:
        present: dict[tuple[int, str], bool] = {}
        for r in rows:
            if r["amount"] < 0:
                present[(r["period"][1], r["label"])] = True
        months_to_check = [month] if month else [m["month"] for m in monthly]
        for mo in months_to_check:
            if (year, mo) > lcm:
                continue
            for label in EXPECTED_MONTHLY_LABELS:
                if not present.get((mo, label)):
                    flags["missing_recurring"].append(
                        {"month": mo, "month_name": MONTH_NAMES[mo], "label": label})

    return {
        "year": year,
        "month": month,
        "period_complete": bool(lcm and (not month or (year, month) <= lcm)),
        "monarch_through": through.isoformat() if through else None,
        "total_spending": round(total, 2),
        "recurring_spending": round(recurring, 2),
        "non_monthly_spending": round(non_monthly, 2),
        "avg_monthly": round(recurring / months_with_data, 2) if months_with_data else 0,
        "months_with_data": months_with_data,
        "transaction_count": len(rows),
        "monthly": monthly,
        "categories": categories,
        "non_monthly_breakdown": non_monthly_breakdown,
        "top_merchants": top_merchants,
        "by_account": by_account,
        "flags": flags,
    }


# ── Brokerage outflows (the "how much" side, reconciliation only) ───────

def get_outflows(db: Session) -> dict:
    """Money leaving Neel's/Jaya's brokerage toward spending channels, by
    month, with the categorized total alongside.

    Definition (Neel, 2026-07-08, docs/SPENDING-PAGE-SPEC.md): card &
    spending channel = XENT_CC balance payments (through Oct 2025), then
    'Transfer from Brokerage to Spending', and from 2026-06 'Transfer from
    Brokerage to Checking/Savings' — the same economic channel, relabelled
    by Robinhood twice. Cash back is netted against it. Everything else
    negative is a bank transfer out (ACH/RTP). Pre-Dec-2025 rows are deduped
    at query time (the backfill double-ingested them under two hash
    schemes). Outflows are lumpy pre-funding, not spend in that month — the
    reconciliation only converges over a quarter or more.
    """
    rows = db.execute(text("""
        WITH dedup AS (
            SELECT DISTINCT ON (account_id, transaction_date, transaction_type,
                                amount, COALESCE(description,''))
                   account_id, transaction_date, amount, description
            FROM investment_transactions
            WHERE account_id IN :accts
              AND transaction_type IN ('XENT_CC','XENT','CASH_MOVEMENT','RTP')
              AND transaction_date <= '2025-11-30'
            UNION ALL
            SELECT account_id, transaction_date, amount, description
            FROM investment_transactions
            WHERE account_id IN :accts
              AND transaction_type IN ('XENT_CC','XENT','CASH_MOVEMENT','RTP')
              AND transaction_date > '2025-11-30'
        ),
        classed AS (
            SELECT *,
                   (description ILIKE '%credit card%'
                    OR description ILIKE '%brokerage to spending%'
                    OR description ILIKE '%brokerage to checking%'
                    OR description ILIKE '%brokerage to savings%') AS card_channel
            FROM dedup
        )
        SELECT date_trunc('month', transaction_date)::date AS mo,
               account_id,
               SUM(CASE WHEN amount < 0 AND card_channel THEN -amount ELSE 0 END) AS card_spending,
               SUM(CASE WHEN amount > 0 AND description ILIKE '%cash back%'
                        THEN amount ELSE 0 END) AS cashback,
               SUM(CASE WHEN amount < 0 AND NOT card_channel THEN -amount ELSE 0 END) AS bank_out,
               MAX(transaction_date) AS latest
        FROM classed
        GROUP BY 1, 2 ORDER BY 1
    """), {"accts": OUTFLOW_ACCOUNTS}).fetchall()

    monarch_by_month: dict[str, float] = defaultdict(float)
    for r in spending_rows(db):
        monarch_by_month["%04d-%02d-01" % r["period"]] += -r["amount"]
    through = _monarch_through(db)

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
        "monarch_through": str(through) if through else None,
        "months": out,
    }
