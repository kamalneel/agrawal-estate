"""Unified income service — Phase 3 of income unification.

One view over ALL income, fixed + dynamic, per the definition-of-income
playbook rule and docs/INCOME-UNIFICATION-SPEC.md:

- fixed:   salary (payslip receipt dates; W-2 annual totals at year
           granularity), rental (monthly table, dated the 1st)
- dynamic: options premium, dividends, interest, stock lending (SLIP),
           realized equity-sale P/L (shared lot engine; call assignments
           are ordinary equity sales)

Aggregation is query-time (no new tables), actual-receipt basis, weeks end
on Friday (Sat-Fri). All accounts included, tax treatment irrelevant.
"""
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.shared.services.cost_basis_service import get_realized_pnl_by_period

FIXED_SOURCES = {"salary", "rental"}
DYNAMIC_SOURCES = {"options", "dividends", "interest", "lending", "equity_sales"}

# Must match backend/app/modules/income/db_queries.py predicates.
_TXN_SOURCE_CASE = """
    CASE
      WHEN t.transaction_type IN ('STO','BTC','STC','BTO') THEN 'options'
      WHEN t.transaction_type IN ('DIVIDEND','CDIV','QUAL DIV REINVEST',
           'REINVEST DIVIDEND','CASH DIVIDEND','QUALIFIED DIVIDEND') THEN 'dividends'
      WHEN t.transaction_type IN ('INTEREST','INT','BANK INTEREST','BOND INTEREST') THEN 'interest'
      WHEN t.transaction_type = 'SLIP' THEN 'lending'
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
                           or (granularity == "year" and y in w2_years.get(key, set())))
                if not covered:
                    p = date(y, m, 1)
                    if in_range(p) and r.monthly_net:
                        by_source[_bucket(p, granularity)]["salary"] += float(r.monthly_net)
                m += 1
                if m > 12:
                    y, m = y + 1, 1

    # --- rental (fixed): monthly table, dated the 1st of the month.
    # The table holds the LEASE SCHEDULE (pre-populated through the lease
    # term); income counts only elapsed months — receipt basis, the same
    # clamp recurring salary uses.
    _today = date.today()
    for r in db.execute(text("""
        SELECT tax_year, month, SUM(gross_amount) AS amount
        FROM rental_monthly_income
        WHERE (tax_year, month) <= (:cy, :cm)
        GROUP BY 1, 2
    """), {"cy": _today.year, "cm": _today.month}).fetchall():
        d = date(r.tax_year, r.month, 1)
        if in_range(d) and r.amount:
            by_source[_bucket(d, granularity)]["rental"] += float(r.amount)

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
