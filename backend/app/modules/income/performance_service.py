"""Portfolio income performance — yield on capital, not dollars earned.

Neel, 2026-09-10, asked for three things the per-account Income drill-down
could not answer:

  1. which equity is not performing
  2. which account is performing
  3. how his cash is performing, given he sells puts against it

All three are the same question — income divided by the capital that earned
it — and the existing views answer none of them, because they report dollars
with no denominator. $7,370 of TSLA premium reads as a win until you divide
by the $704,419 backing it.

WHY AVERAGE CAPITAL, NOT CURRENT VALUE
--------------------------------------
Dividing a period's income by TODAY's position value is wrong whenever the
position was trimmed or exited during it. Measured that way HOOD yields
2,255% and RKLB 123% — arithmetic, not insight. `investment_holdings_history`
carries a daily market_value per (account, symbol), so the denominator is the
average capital actually deployed across the period. That turns HOOD into
1.93%/mo and RKLB into 3.19%/mo.

The history begins 2026-02-16. Nothing earlier can be measured this way, so
the period is clamped to that and `coverage` reports it rather than quietly
returning a yield computed from a shorter window than the income.

WHY SYMBOL *AND* ACCOUNT, NOT A FLAT "ALL ACCOUNTS" TOTAL
---------------------------------------------------------
Neel's first instinct was a sixth "All Accounts" bucket. Summing across
accounts would have erased the finding that prompted the question: TSLA
earns 0.66%/mo in Neel's brokerage and 0.04% in Jaya's, on the same strike
assigned eight days apart. So every symbol row carries its per-account split.

CASH (3)
--------
`account_cash_balance_history.options_collateral` is the cash actually tied
up securing puts, which is the honest denominator for put premium. The cash
POOL only means something where cash is real: in the IRAs `true_cash` is free
cash + collateral, but the margin brokerage accounts run a negative
true_cash (it is borrowing, not cash), so cash-pool yield and utilisation are
reported as None there rather than as a nonsense ratio — measured naively
those accounts showed 6,124% utilisation.

Columns are sparsely populated (options_collateral on 200 of 421 rows), so
averages are taken only over dates where the figure exists.
"""
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

#: First date in investment_holdings_history. Income before this cannot be
#: put over a denominator, so periods are clamped here.
HISTORY_START = date(2026, 2, 16)

OPTION_TYPES = ("STO", "BTC", "STC", "BTO")
INCOME_TYPES = OPTION_TYPES + ("DIVIDEND",)

#: investment_accounts.account_id -> account_cash_balance_history.account_name
_CASH_ACCOUNT_NAME = {
    "neel_brokerage": "Neel's Brokerage",
    "jaya_brokerage": "Jaya's Brokerage",
    "neel_retirement": "Neel's Retirement",
    "jaya_ira": "Jaya's IRA",
    "jaya_roth_ira": "Jaya's Roth IRA",
    "neel_roth_ira": "Neel's Roth IRA",
}


def _monthly(value: float, capital: float, days: int) -> Optional[float]:
    """Income/capital as a MONTHLY rate. None when capital is too small to
    divide by — a $49 position that earned $353 is not a 727% yield, it is a
    rounding artifact."""
    if not capital or capital < 1000 or days <= 0:
        return None
    return (value / capital) * 100 * 30 / days


def get_portfolio_performance(
    db: Session,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> Dict:
    start = max(start or HISTORY_START, HISTORY_START)
    end = end or date.today()
    days = max((end - start).days, 1)
    p = {"start": start, "end": end}

    # --- income per (account, symbol)
    income_rows = db.execute(text(f"""
        SELECT account_id, symbol,
               SUM(amount) FILTER (WHERE transaction_type IN {OPTION_TYPES}) AS options,
               SUM(amount) FILTER (WHERE transaction_type = 'DIVIDEND') AS dividends,
               COUNT(*) AS legs
        FROM investment_transactions
        WHERE transaction_date >= :start AND transaction_date <= :end
          AND transaction_type IN {INCOME_TYPES}
          AND symbol IS NOT NULL AND symbol <> ''
        GROUP BY 1, 2
    """), p).fetchall()

    # --- average capital per (account, symbol): mean of the daily totals
    cap_rows = db.execute(text("""
        SELECT account_id, symbol, AVG(daily) AS avg_capital
        FROM (
            SELECT account_id, symbol, snapshot_date, SUM(market_value) AS daily
            FROM investment_holdings_history
            WHERE snapshot_date >= :start AND snapshot_date <= :end
            GROUP BY 1, 2, 3
        ) d GROUP BY 1, 2
    """), p).fetchall()
    cap = {(r.account_id, r.symbol): float(r.avg_capital or 0) for r in cap_rows}

    names = {r.account_id: r.account_name for r in db.execute(text(
        "SELECT account_id, account_name FROM investment_accounts")).fetchall()}

    # --- assemble: symbol -> per-account splits, then roll up
    by_symbol: Dict[str, Dict] = {}
    by_account: Dict[str, Dict] = {}
    for r in income_rows:
        options = float(r.options or 0)
        dividends = float(r.dividends or 0)
        total = options + dividends
        capital = cap.get((r.account_id, r.symbol), 0.0)

        s = by_symbol.setdefault(r.symbol, {
            "symbol": r.symbol, "income": 0.0, "options": 0.0,
            "dividends": 0.0, "avg_capital": 0.0, "accounts": []})
        s["income"] += total
        s["options"] += options
        s["dividends"] += dividends
        s["avg_capital"] += capital
        s["accounts"].append({
            "account_id": r.account_id,
            "account_name": names.get(r.account_id, r.account_id),
            "income": round(total, 2),
            "avg_capital": round(capital, 2),
            "yield_monthly": _monthly(total, capital, days),
        })

        a = by_account.setdefault(r.account_id, {
            "account_id": r.account_id,
            "account_name": names.get(r.account_id, r.account_id),
            "income": 0.0, "avg_capital": 0.0, "symbols": 0, "legs": 0})
        a["income"] += total
        a["symbols"] += 1
        a["legs"] += r.legs

    # Account capital is the account's whole book, not just the symbols that
    # happened to earn — idle holdings are capital too, and hiding them would
    # flatter an account that only traded its winners.
    for r in db.execute(text("""
        SELECT account_id, AVG(daily) AS avg_capital FROM (
            SELECT account_id, snapshot_date, SUM(market_value) AS daily
            FROM investment_holdings_history
            WHERE snapshot_date >= :start AND snapshot_date <= :end
            GROUP BY 1, 2
        ) d GROUP BY 1
    """), p).fetchall():
        if r.account_id in by_account:
            by_account[r.account_id]["avg_capital"] = float(r.avg_capital or 0)

    symbols = []
    for s in by_symbol.values():
        s["accounts"].sort(key=lambda x: -x["income"])
        s["yield_monthly"] = _monthly(s["income"], s["avg_capital"], days)
        for k in ("income", "options", "dividends", "avg_capital"):
            s[k] = round(s[k], 2)
        symbols.append(s)
    symbols.sort(key=lambda s: (s["yield_monthly"] is None, s["yield_monthly"] or 0))

    accounts = []
    for a in by_account.values():
        a["yield_monthly"] = _monthly(a["income"], a["avg_capital"], days)
        a["income"] = round(a["income"], 2)
        a["avg_capital"] = round(a["avg_capital"], 2)
        accounts.append(a)
    accounts.sort(key=lambda a: -(a["yield_monthly"] or -999))

    return {
        "period": {"start": str(start), "end": str(end), "days": days},
        "coverage": {
            "history_start": str(HISTORY_START),
            "note": ("Capital is the daily average from "
                     f"{HISTORY_START}; earlier income cannot be yielded."),
        },
        "by_symbol": symbols,
        "by_account": accounts,
        "cash": _cash_performance(db, start, end, days),
        "totals": {
            "income": round(sum(a["income"] for a in accounts), 2),
            "avg_capital": round(sum(a["avg_capital"] for a in accounts), 2),
        },
    }


def _cash_performance(db: Session, start: date, end: date, days: int) -> List[Dict]:
    """Put premium against the cash securing it (level 3)."""
    p = {"start": start, "end": end}
    prem = {r.account_id: (float(r.s or 0), r.n) for r in db.execute(text(f"""
        SELECT account_id, SUM(amount) AS s, COUNT(*) AS n
        FROM investment_transactions
        WHERE transaction_type IN ('STO', 'BTC')
          AND description ILIKE '%%put%%'
          AND transaction_date >= :start AND transaction_date <= :end
        GROUP BY 1
    """), p).fetchall()}

    # AVG() skips NULLs, which is what we want: these columns are populated on
    # roughly half the snapshots and a zero-filled average would understate
    # the collateral actually committed.
    cash = {r.account_name: r for r in db.execute(text("""
        SELECT account_name,
               AVG(NULLIF(options_collateral, 0)) AS collateral,
               AVG(NULLIF(true_cash, 0))          AS true_cash,
               AVG(NULLIF(margin_used, 0))        AS margin_used
        FROM account_cash_balance_history
        WHERE snapshot_date >= :start AND snapshot_date <= :end
        GROUP BY 1
    """), p).fetchall()}

    out = []
    for account_id, name in _CASH_ACCOUNT_NAME.items():
        put_premium, legs = prem.get(account_id, (0.0, 0))
        row = cash.get(name)
        collateral = float(row.collateral or 0) if row else 0.0
        true_cash = float(row.true_cash or 0) if row else 0.0
        margin_used = float(row.margin_used or 0) if row else 0.0

        # true_cash < 0 means the account is borrowing: the puts are secured
        # by margin, not by cash. A "yield on cash" there would divide by a
        # debt. Report the collateral yield and leave the cash columns null.
        cash_backed = true_cash > 0
        out.append({
            "account_id": account_id,
            "account_name": name,
            "put_premium": round(put_premium, 2),
            "put_legs": legs,
            "avg_collateral": round(collateral, 2),
            "avg_cash_pool": round(true_cash, 2) if cash_backed else None,
            "avg_margin_used": round(margin_used, 2) if margin_used else None,
            "cash_backed": cash_backed,
            "utilization_pct": (round(collateral / true_cash * 100, 1)
                                if cash_backed and true_cash else None),
            "idle_cash": (round(true_cash - collateral, 2)
                          if cash_backed else None),
            "yield_on_collateral_monthly": _monthly(put_premium, collateral, days),
            "yield_on_cash_monthly": (_monthly(put_premium, true_cash, days)
                                      if cash_backed else None),
        })
    out.sort(key=lambda r: -(r["yield_on_collateral_monthly"] or -999))
    return out
