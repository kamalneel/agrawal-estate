"""Unified income service — Phase 3 of income unification.

One view over ALL income, fixed + dynamic, per the definition-of-income
playbook rule and docs/INCOME-UNIFICATION-SPEC.md:

- fixed:   salary (payslip receipt dates; W-2 annual totals at year
           granularity), rental (monthly table, dated the 1st), airbnb
           (build-out costs today, revenue from 2027)
- dynamic: options premium, dividends, interest, stock lending (SLIP),
           realized equity-sale P/L (shared lot engine; call assignments
           are ordinary equity sales)

Aggregation is query-time (no new tables), actual-receipt basis, weeks end
on Friday (Sat-Fri). All accounts included, tax treatment irrelevant.
"""
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.modules.spending.models import AIRBNB_CATEGORY, HARTSTENE_CATEGORY
from app.shared.services.cost_basis_service import get_realized_pnl_by_period

FIXED_SOURCES = {"salary", "rental", "airbnb"}

#: No "lending" stream. Robinhood's Fully Paid Securities Lending (SLIP) paid
#: $9.42 across 77 payments in two and a half years — 70 of them exactly
#: $0.01 — while occupying a card the same size as options at $40K. Neel,
#: 2026-09-06: "drop it". SLIP rows are still ingested and still carry their
#: own transaction_type (they are taxable substitute payments, 1099-MISC, and
#: not qualified-dividend eligible, so tax work must keep them separable);
#: they simply land in `interest` here — the line for what cash and
#: securities earn or cost while sitting there. If a hard-to-borrow name ever
#: makes lending material, it shows up on its own without rebuilding this.
DYNAMIC_SOURCES = {"options", "dividends", "interest", "equity_sales"}

#: Monarch category -> income stream. Both sides of each category net into
#: the stream (see the BUSINESS block in get_unified_income).
#: 303 Hartstene feeds "rental" so the user sees ONE continuous rent line:
#: the hand-maintained lease schedule before Monarch coverage begins, actual
#: bank receipts from then on.
_BUSINESS_STREAMS = {
    HARTSTENE_CATEGORY: "rental",
    AIRBNB_CATEGORY: "airbnb",
}

#: Tenants who have rented 303 Hartstene, matched inside the Zelle memo.
#: Namit/Anubhuti Jain held the lease through Feb 2025; Eric Morales from
#: Apr 2025. Extend this when the tenant changes, or their rent silently
#: stops counting.
_HARTSTENE_TENANTS = (
    "eric morales", "eric a morales",     # Apr 2025 -
    "anubhuti jain", "namit jain",        # - Feb 2025
)

#: A tenant receipt that is NOT rent. Security deposits are a liability, not
#: income (Eric's Mar 2025 "partial deposit #1" $2,000 and "deposit payment
#: #2" $20), and the Namit deposit was refunded in full on 2025-05-19.
_NON_RENT_TENANT_MEMOS = ("deposit",)


def _is_hartstene_rent(amount, original_statement: str | None) -> bool:
    """True only for rent actually received from the tenant.

    The `303 Hartstene Dr` Monarch category is a PROPERTY ledger, not a rent
    ledger: alongside the rent it carries HOA/ClickPay, county tax, Home
    Depot, plumbing, security deposits in and out, and a long tail of rows
    that simply landed in the wrong category (an Uber, a Great Wolf Lodge
    Zelle, a $6,000 "Return of Posted Check", an $11 Zelle from a stranger).

    Netting all of that produced a rent card that never once showed the rent
    — August 2026 read $7,864 against a $6,400 lease. Neel, 2026-09-06:
    "Show only rent on the card and use that in your sum."

    So rent is defined narrowly and positively: money IN, from a known
    tenant, not a deposit. Anything unrecognised is excluded rather than
    guessed at — the same conservative direction the Spending page takes
    with unexplained inflows (see spending/models.REFUND_STATEMENT_PREFIX).
    """
    if amount is None or float(amount) <= 0:
        return False
    memo = (original_statement or "").lower()
    if not any(t in memo for t in _HARTSTENE_TENANTS):
        return False
    return not any(x in memo for x in _NON_RENT_TENANT_MEMOS)


#: "July rent pt1", "Sept rent pt 2", "December rent #1" — Eric writes the
#: month he is paying for into every Zelle memo. That memo, not the date the
#: transfer cleared, is what the rent belongs to.
_RENT_MONTH_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b")

#: Memo-less rent transfers inherit the month of the nearest rent payment
#: that does name one. Every such row in the ledger has a partner within 5
#: days (the two halves of one month's rent), so the window is generous
#: enough to pair them and tight enough not to reach the next month's rent.
_RENT_PAIR_WINDOW_DAYS = 10


def _rent_month(pay_date: date, original_statement: str | None) -> Optional[date]:
    """The month a rent payment is FOR, from its memo. None if unstated.

    The memo names a month but never a year, so the year is the one that puts
    the named month closest to the payment date: "Jan rent pt2" paid
    2025-12-29 is January 2026, three days out, not January 2025.
    """
    memo = (original_statement or "").lower().split("conf#")[0]
    m = _RENT_MONTH_RE.search(memo)
    if not m:
        return None
    month = ("jan", "feb", "mar", "apr", "may", "jun",
             "jul", "aug", "sep", "oct", "nov", "dec").index(m.group(1)) + 1
    return min((date(y, month, 1) for y in
                (pay_date.year - 1, pay_date.year, pay_date.year + 1)),
               key=lambda d: abs((d - pay_date).days))


def _attribute_rent_months(rows: List) -> Dict[int, date]:
    """Row id -> the month that row's rent is for.

    Two passes: read the month straight off every memo that states one, then
    give each memo-less row the month of its nearest dated neighbour. Rows
    with neither keep their own month (the caller falls back to the receipt
    date), which is the pre-attribution behaviour.
    """
    stated = {r.id: _rent_month(r.transaction_date, r.original_statement)
              for r in rows}
    resolved: Dict[int, date] = {}
    dated = [(r.transaction_date, stated[r.id]) for r in rows if stated[r.id]]
    for r in rows:
        if stated[r.id]:
            resolved[r.id] = stated[r.id]
            continue
        near = [(abs((d - r.transaction_date).days), m) for d, m in dated
                if abs((d - r.transaction_date).days) <= _RENT_PAIR_WINDOW_DAYS]
        if near:
            resolved[r.id] = min(near)[1]
    return resolved


#: Monarch merchant -> person, for salary that actually landed in the bank.
#: Matched on employer name rather than the "Paychecks"/"Jaya's Salary"
#: categories because those categories also carry non-salary rows (Costco
#: Visa "Credit Card Payment", "Autopay Rautopay", a "Transfer Jaya Agrawal"
#: — ~$15K of them), which would silently inflate the salary line.
#: Verified against the ledger 2026-08-14: Cisco Jan-Oct 2025, DeWinter from
#: 2026-06-05, Central PAYROLL (AdamX) from 2026-06-12.
_SALARY_EMPLOYERS = {
    "Cisco Systems": "jaya",
    "Cisco Systems Inc": "jaya",
    "DeWinter": "jaya",
    "Dewinter Co": "jaya",
    "Central PAYROLL": "neel",
}

#: Receipts that arrive from a payroll source but are NOT salary. Keyed by
#: (date, merchant, amount) so an unrelated row from the same employer is
#: unaffected and a re-import cannot silently reintroduce the payment.
#: 2025-10-28 Cisco $39,308.18 is Jaya's severance (Neel, 2026-08-14:
#: "that Oct payout was severance, don't count it as salary") — it is over a
#: third of her 2025 receipts and would dominate any monthly view.
_NON_SALARY_PAYROLL_RECEIPTS = {
    (date(2025, 10, 28), "Cisco Systems Inc", 39308.18),
}

# Must match backend/app/modules/income/db_queries.py predicates.
_TXN_SOURCE_CASE = """
    CASE
      WHEN t.transaction_type IN ('STO','BTC','STC','BTO') THEN 'options'
      WHEN t.transaction_type IN ('DIVIDEND','CDIV','QUAL DIV REINVEST',
           'REINVEST DIVIDEND','CASH DIVIDEND','QUALIFIED DIVIDEND') THEN 'dividends'
      WHEN t.transaction_type IN ('INTEREST','INT','BANK INTEREST','BOND INTEREST',
           'MARGIN_INTEREST','SLIP') THEN 'interest'
    END
"""

_PERIOD_EXPR = {
    "week": "(t.transaction_date + ((5 - EXTRACT(DOW FROM t.transaction_date)::int + 7) % 7)"
            " * INTERVAL '1 day')::date",
    "month": "date_trunc('month', t.transaction_date)::date",
    "year": "date_trunc('year', t.transaction_date)::date",
}


def _bucket(d: date, granularity: str) -> date:
    if granularity == "week":  # Friday-ending
        return d + timedelta(days=(4 - d.weekday()) % 7)
    if granularity == "month":
        return date(d.year, d.month, 1)
    return date(d.year, 1, 1)


NON_TAXABLE_ACCOUNT_TYPES = ('ira', 'roth_ira', 'traditional_ira', '401k',
                             'hsa', 'retirement')


def get_unified_income(
    db: Session,
    granularity: str = "month",
    start: Optional[date] = None,
    end: Optional[date] = None,
    taxable_only: bool = False,
) -> Dict:
    """taxable_only limits brokerage-sourced income to taxable accounts;
    salary and rental are always taxable and stay included."""
    if granularity not in _PERIOD_EXPR:
        raise ValueError(f"granularity must be one of {list(_PERIOD_EXPR)}")

    # period -> source -> amount ; period -> account -> amount
    by_source = defaultdict(lambda: defaultdict(float))
    by_account = defaultdict(lambda: defaultdict(float))
    unresolved = defaultdict(int)

    def in_range(d: date) -> bool:
        return (start is None or d >= start) and (end is None or d <= end)

    # --- investment-transaction sources (options/dividends/interest/lending)
    where, params = [], {}
    if start:
        where.append("t.transaction_date >= :start")
        params["start"] = start
    if end:
        where.append("t.transaction_date <= :end")
        params["end"] = end
    if taxable_only:
        ntt = ", ".join(f"'{t}'" for t in NON_TAXABLE_ACCOUNT_TYPES)
        where.append(f"a.account_type NOT IN ({ntt})")
    where_sql = ("AND " + " AND ".join(where)) if where else ""
    rows = db.execute(text(f"""
        SELECT {_PERIOD_EXPR[granularity]} AS period,
               {_TXN_SOURCE_CASE} AS src,
               a.account_name,
               SUM(t.amount) AS amount
        FROM investment_transactions t
        JOIN investment_accounts a
          ON a.account_id = t.account_id AND a.source = t.source
        WHERE a.is_active = 'Y' AND {_TXN_SOURCE_CASE} IS NOT NULL {where_sql}
        GROUP BY 1, 2, 3
    """), params).fetchall()
    for r in rows:
        by_source[r.period][r.src] += float(r.amount)
        by_account[r.period][r.account_name] += float(r.amount)

    # --- realized equity-sale P/L (shared lot engine)
    for r in get_realized_pnl_by_period(db, granularity=granularity,
                                        start=start, end=end,
                                        taxable_only=taxable_only):
        p = date.fromisoformat(r["period"])
        by_source[p]["equity_sales"] += r["realized_pnl"]
        acct = db.execute(text(
            "SELECT account_name FROM investment_accounts WHERE account_id=:a LIMIT 1"
        ), {"a": r["account_id"]}).scalar() or r["account_id"]
        by_account[p][acct] += r["realized_pnl"]
        unresolved[p] += r["unresolved_count"]

    # --- salary (fixed): payslip receipts; W-2 yearly totals at year level
    from app.modules.income.salary_service import get_salary_service
    try:
        salaries = get_salary_service(db).load_all_payslips()
    except Exception:
        salaries = {}
    # months (YYYY-MM) covered by payslips / years covered by W-2s, per person
    payslip_months: dict = {}
    w2_years: dict = {}
    for name, inc in salaries.items():
        key = name.split()[0].lower()
        w2_years.setdefault(key, set()).update(
            int(y) for y, g in (inc.yearly_gross or {}).items() if g)
        for slip in inc.payslips or []:
            d = slip.pay_date.date() if hasattr(slip.pay_date, "date") else slip.pay_date
            if slip.gross_pay_period:
                payslip_months.setdefault(key, set()).add(f"{d.year}-{d.month:02d}")
        if granularity == "year":
            for yr, gross in (inc.yearly_gross or {}).items():
                p = date(int(yr), 1, 1)
                if in_range(p) and gross:
                    by_source[p]["salary"] += float(gross)
        else:
            for slip in inc.payslips or []:
                d = slip.pay_date.date() if hasattr(slip.pay_date, "date") else slip.pay_date
                if in_range(d) and slip.gross_pay_period:
                    by_source[_bucket(d, granularity)]["salary"] += float(slip.gross_pay_period)

    # --- salary ACTUALS from the Monarch bank feed (net deposits).
    #
    # These are the paychecks that actually landed, so they own every month
    # they cover; salary_projections below fills only the gaps. Same
    # ownership split as rental further down — modelled figures supply the
    # months the feed doesn't reach, actuals take over from there.
    #
    # Added 2026-08-14: the salary line was previously driven entirely by
    # salary_projections and never consulted this feed, so it drew a flat
    # monthly line through a year that actually ranged from $740.95 to
    # $43,068.63 and billed months (Nov-Dec 2025) with no paycheck at all.
    # salary_actual records WHICH (person, month) pairs the feed covers, so
    # the projection loop below can skip them. The amounts themselves are
    # bucketed from each deposit's own date — bucketing from the month key
    # would collapse a month of paychecks onto the 1st and put them all in
    # one week at week granularity.
    salary_actual: Dict[tuple, float] = {}   # (person, 'YYYY-MM') -> net
    for r in db.execute(text("""
        SELECT transaction_date, merchant, SUM(amount) AS amount
        FROM spending_transactions
        WHERE amount > 0 AND merchant IN :merchants
        GROUP BY 1, 2
    """).bindparams(bindparam("merchants", expanding=True)),
        {"merchants": list(_SALARY_EMPLOYERS)}).fetchall():
        if (r.transaction_date, r.merchant, float(r.amount)) in _NON_SALARY_PAYROLL_RECEIPTS:
            continue
        person = _SALARY_EMPLOYERS[r.merchant]
        d = r.transaction_date
        mk = f"{d.year}-{d.month:02d}"
        salary_actual[(person, mk)] = salary_actual.get((person, mk), 0.0) + float(r.amount)
        # At year granularity a W-2 already contributed this person's GROSS
        # for the year; adding net deposits on top would double-count them.
        if granularity == "year" and d.year in w2_years.get(person, set()):
            continue
        if in_range(d):
            by_source[_bucket(d, granularity)]["salary"] += float(r.amount)

    # --- recurring salary (salary_projections): counted as ACTUAL take-home
    # for ELAPSED months a person has no payslip/W-2 coverage (user-confirmed;
    # amounts are net until payslips are ingested). Not applied to weekly
    # granularity — recurring rows carry no pay dates.
    if granularity in ("month", "year"):
        today = date.today()
        for r in db.execute(text(
            "SELECT person, monthly_net, effective_from, effective_to FROM salary_projections"
        )).fetchall():
            key = (r.person or "").split()[0].lower()
            fy, fm = map(int, r.effective_from.split("-"))
            if r.effective_to:
                ty, tm = map(int, r.effective_to.split("-"))
            else:
                ty, tm = today.year, today.month
            ty, tm = min((ty, tm), (today.year, today.month))
            y, m = fy, fm
            while (y, m) <= (ty, tm):
                month_key = f"{y}-{m:02d}"
                covered = (month_key in payslip_months.get(key, set())
                           or (key, month_key) in salary_actual
                           or (granularity == "year" and y in w2_years.get(key, set())))
                if not covered:
                    p = date(y, m, 1)
                    if in_range(p) and r.monthly_net:
                        by_source[_bucket(p, granularity)]["salary"] += float(r.monthly_net)
                m += 1
                if m > 12:
                    y, m = y + 1, 1

    # --- rental (fixed), pre-Monarch history only.
    #
    # `rental_monthly_income` is a hand-maintained LEASE SCHEDULE for 303
    # Hartstene (property_id 1), pre-populated through the lease term. The
    # same rent also arrives as actual bank receipts in the Monarch feed
    # under HARTSTENE_CATEGORY — verified identical: Jan-Mar 2026 is $6,220
    # in the schedule and $5,000 + $1,220 Zelle in Monarch, to the cent.
    #
    # Counting both double-counts the rent, so ownership is split by date:
    # the schedule supplies history from before Monarch coverage begins, and
    # Monarch actuals take over from that month on. The boundary is derived
    # from the data rather than hardcoded, so it moves by itself if an older
    # Monarch export is ever loaded.
    #
    # Future-dated schedule rows are NOT actuals and are excluded here; they
    # remain available as a projection (see docs/INCOME-UNIFICATION-SPEC.md).
    _today = date.today()
    _monarch_from = db.execute(text("""
        SELECT MIN(transaction_date) FROM spending_transactions WHERE category = :cat
    """), {"cat": HARTSTENE_CATEGORY}).scalar()
    _cutoff = ((_monarch_from.year, _monarch_from.month) if _monarch_from
               else (_today.year + 1, 1))

    for r in db.execute(text("""
        SELECT tax_year, month, SUM(gross_amount) AS amount
        FROM rental_monthly_income
        WHERE (tax_year, month) <= (:cy, :cm)
        GROUP BY 1, 2
    """), {"cy": _today.year, "cm": _today.month}).fetchall():
        if (r.tax_year, r.month) >= _cutoff:
            continue  # Monarch owns this month — see above
        d = date(r.tax_year, r.month, 1)
        if in_range(d) and r.amount:
            by_source[_bucket(d, granularity)]["rental"] += float(r.amount)

    # --- businesses (fixed): income-producing assets whose two sides share
    # one Monarch category, so the category NETS to a single stream here.
    #
    #   303 Hartstene — owned outright and let out. RENT RECEIPTS ONLY; see
    #     _is_hartstene_rent for why the rest of the category is dropped.
    #   Airbnb — partial ownership, still being built out. Negative until
    #     2027 revenue, and still nets both sides.
    #
    # These categories are CategoryKind.BUSINESS, hence excluded from the
    # Spending page — the exclusion there IS the inclusion here, so a row can
    # never be counted twice. Spending stores outflows negative, so amounts
    # carry through unchanged and the sign means what it says.
    for cat, src in _BUSINESS_STREAMS.items():
        rent_only = cat == HARTSTENE_CATEGORY
        rows = db.execute(text("""
            SELECT id, transaction_date, amount, original_statement
            FROM spending_transactions
            WHERE category = :cat
        """), {"cat": cat}).fetchall()
        if rent_only:
            rows = [r for r in rows
                    if _is_hartstene_rent(r.amount, r.original_statement)]
            # Rent is owed monthly but paid in two Zelle transfers that
            # straddle month ends, and always a month ahead — so the receipt
            # date puts a fragment in one month and one-and-a-half months in
            # the next (Jul 2026 read $12,800, Feb 2026 read $1,220). Neel,
            # 2026-09-06: "count each payment in the month its memo names".
            # Every month then reads its lease rate exactly: $6,220 through
            # Mar 2026, $6,400 from Apr 2026 (both signed leases, $5,800 and
            # $5,980 plus $420 HOA).
            #
            # Only for month/year. A week is shorter than the thing being
            # attributed, so weekly stays on the receipt date — that view
            # answers "what landed this week", which is the cash question.
            attributed = ({} if granularity == "week"
                          else _attribute_rent_months(rows))
        for r in rows:
            d = attributed.get(r.id, r.transaction_date) if rent_only \
                else r.transaction_date
            if in_range(d) and r.amount:
                by_source[_bucket(d, granularity)][src] += float(r.amount)

    # --- assemble
    periods: List[Dict] = []
    for p in sorted(set(by_source) | set(by_account)):
        srcs = {k: round(v, 2) for k, v in by_source[p].items()}
        fixed = sum(v for k, v in srcs.items() if k in FIXED_SOURCES)
        dynamic = sum(v for k, v in srcs.items() if k in DYNAMIC_SOURCES)
        periods.append({
            "period": str(p),
            "total": round(fixed + dynamic, 2),
            "fixed": round(fixed, 2),
            "dynamic": round(dynamic, 2),
            "by_source": srcs,
            "by_account": {k: round(v, 2) for k, v in by_account[p].items()},
            "unresolved_basis_rows": unresolved.get(p, 0),
        })

    return {
        "granularity": granularity,
        "start": str(start) if start else None,
        "end": str(end) if end else None,
        "periods": periods,
        "totals": {
            "total": round(sum(x["total"] for x in periods), 2),
            "fixed": round(sum(x["fixed"] for x in periods), 2),
            "dynamic": round(sum(x["dynamic"] for x in periods), 2),
        },
    }
