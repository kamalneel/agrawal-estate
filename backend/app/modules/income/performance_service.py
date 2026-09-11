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

CALLS EARN ON SHARES; PUTS EARN ON CASH
---------------------------------------
The two are not interchangeable and must not share a denominator. A covered
call is written against shares you own, so its premium is a return on SHARE
capital. A cash-secured put is written against cash, so its premium is a
return on COLLATERAL — at the time it is sold you may own none of the stock
at all.

Neel, 2026-09-11: "puts income should go into the cash-secured put section,
and only the call income should show up on the call table."

Dividing both by share capital made put sellers look like the best equity
performers. SOXL was the clearest case: $33,407 of PUT premium across
June-August against zero shares held — the holdings history had no SOXL rows
for July, which looked like a data gap and was in fact correct, because the
shares did not exist until the puts were assigned in late August. Measured
against share capital it read 24.52%/mo; its actual call income over those
shares is $343, or 0.25%/mo.

Portfolio-wide the split is $150,120 of put premium against $60,098 of call
premium, so roughly 71% of option income was being yielded on capital it
never touched. `yield_monthly` therefore counts calls + dividends only.
Put premium gets its own denominator rather than none: `put_collateral_service`
parses the per-symbol collateral (strike x 100 x contracts) out of the position
snapshots, validated at 98% against the account totals Robinhood already
records. So every symbol carries BOTH yields — `yield_monthly` on share
capital from calls and dividends, `put_yield_monthly` on the cash those puts
actually tied up.

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

The denominator is collateral USED, not cash held — Neel, 2026-09-11: "if the
account has $50,000 in cash and only $40,000 of that was used as put
collateral, then the denominator ... should be the $40,000". Yield on the
whole pool is still reported beside it, because the gap between the two IS
the idle cash, and that is worth seeing.
"""
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

#: First date in investment_holdings_history. Income before this cannot be
#: put over a denominator, so periods are clamped here.
HISTORY_START = date(2026, 2, 16)

#: Shortest span worth extrapolating to a monthly rate. CBRS, assigned nine
#: days before the view was first run, annualised to 107.51%/mo — a number
#: about the calendar, not the position. Under this, `yield_monthly` is None
#: and the UI shows the raw dollars plus `held_days` instead.
MIN_SPAN_DAYS = 21

#: Neel's own hurdle rates, 2026-09-11: "my monthly returns on call are 1%
#: per month, and my monthly return on puts is 2%". They differ because the
#: capital differs — a covered call rents out shares already committed to a
#: thesis, while a put rents out cash that has no other job. Shipped in the
#: response so the two tables colour against their OWN bar rather than one
#: shared threshold.
TARGET_CALL_MONTHLY_PCT = 1.0
TARGET_PUT_MONTHLY_PCT = 2.0

#: One options contract. Below this many shares a covered call is impossible.
SHARES_PER_CONTRACT = 100

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
    rounding artifact.

    `days` is the span the position was actually HELD, not the length of the
    reporting period. Using the period understates anything bought or sold
    inside it: SOXL was held 94 of 206 days and read 11.19%/mo against a true
    24.52%. Positions held throughout are unaffected.
    """
    if not capital or capital < 1000 or days < MIN_SPAN_DAYS:
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
               SUM(amount) FILTER (WHERE transaction_type IN {OPTION_TYPES}
                                   AND description ILIKE '%%call%%') AS calls,
               SUM(amount) FILTER (WHERE transaction_type IN {OPTION_TYPES}
                                   AND description ILIKE '%%put%%') AS puts,
               SUM(amount) FILTER (WHERE transaction_type = 'DIVIDEND') AS dividends,
               COUNT(*) AS legs
        FROM investment_transactions
        WHERE transaction_date >= :start AND transaction_date <= :end
          AND transaction_type IN {INCOME_TYPES}
          AND symbol IS NOT NULL AND symbol <> ''
        GROUP BY 1, 2
    """), p).fetchall()

    # --- average capital per (account, symbol), plus the span actually held.
    # first/last bound the days the yield is annualised over; a position sold
    # in May must not be spread across a period running to September.
    cap_rows = db.execute(text("""
        SELECT account_id, symbol, AVG(daily) AS avg_capital,
               COUNT(*) AS observed_days,
               MIN(snapshot_date) AS first_seen, MAX(snapshot_date) AS last_seen
        FROM (
            SELECT account_id, symbol, snapshot_date, SUM(market_value) AS daily
            FROM investment_holdings_history
            WHERE snapshot_date >= :start AND snapshot_date <= :end
            GROUP BY 1, 2, 3
        ) d GROUP BY 1, 2
    """), p).fetchall()
    cap = {(r.account_id, r.symbol): float(r.avg_capital or 0) for r in cap_rows}
    span = {(r.account_id, r.symbol): (r.first_seen, r.last_seen) for r in cap_rows}
    observed = {(r.account_id, r.symbol): int(r.observed_days) for r in cap_rows}

    # Snapshots land on trading days, so the calendar is denser than the
    # snapshot count. This converts "days we saw the position" into calendar
    # days, which is what a monthly rate has to be annualised over.
    snapshot_dates = db.execute(text("""
        SELECT COUNT(DISTINCT snapshot_date) FROM investment_holdings_history
        WHERE snapshot_date >= :start AND snapshot_date <= :end
    """), p).scalar() or 0
    day_scale = (days / snapshot_dates) if snapshot_dates else 1.0

    # Days a SYMBOL was held anywhere: distinct dates across accounts, so two
    # accounts holding it the same day is one day, not two.
    symbol_observed = {r.symbol: int(r.n) for r in db.execute(text("""
        SELECT symbol, COUNT(DISTINCT snapshot_date) AS n
        FROM investment_holdings_history
        WHERE snapshot_date >= :start AND snapshot_date <= :end
        GROUP BY 1
    """), p).fetchall()}

    # --- what is still held, so the view can be narrowed to live positions.
    # Held is per (account, symbol): NVDA is open in three accounts and closed
    # in others, and the symbol row has to reflect that rather than guess.
    held_rows = db.execute(text("""
        SELECT account_id, symbol, SUM(quantity) AS shares,
               SUM(quantity * current_price) AS value
        FROM investment_holdings WHERE quantity > 0 GROUP BY 1, 2
    """)).fetchall()
    held = {(r.account_id, r.symbol): float(r.value or 0) for r in held_rows}
    shares = {(r.account_id, r.symbol): float(r.shares or 0) for r in held_rows}

    # Per-symbol put collateral, parsed from the position snapshots. This is
    # the denominator put premium actually earned against — Neel, 2026-09-11:
    # "per-symbol collateral is the right number".
    from app.modules.income.put_collateral_service import get_put_collateral
    collateral = get_put_collateral(db, start, end)

    names = {r.account_id: r.account_name for r in db.execute(text(
        "SELECT account_id, account_name FROM investment_accounts")).fetchall()}

    # --- assemble: symbol -> per-account splits, then roll up
    by_symbol: Dict[str, Dict] = {}
    by_account: Dict[str, Dict] = {}
    for r in income_rows:
        calls = float(r.calls or 0)
        puts = float(r.puts or 0)
        dividends = float(r.dividends or 0)
        total = calls + puts + dividends
        # Only calls and dividends are earned BY THE SHARES. Puts are secured
        # by cash and are yielded in the cash section instead.
        equity_income = calls + dividends
        capital = cap.get((r.account_id, r.symbol), 0.0)

        # Held days = days actually OBSERVED holding it, scaled to the
        # calendar — NOT first-to-last. SOXL was bought 6 Jun, sold 18 Jun,
        # then re-acquired by assignment on 25 Aug: first-to-last spans 94
        # days, 68 of which it owned no shares at all, which understated its
        # yield ~3.6x. An uninterrupted position is unaffected, since its
        # observed days already fill the span.
        obs = observed.get((r.account_id, r.symbol), 0)
        held_days = max(round(obs * day_scale), 1) if obs else days
        # first/last are still reported so the UI can show WHEN it was held;
        # they no longer drive the yield.
        first, last = span.get((r.account_id, r.symbol), (None, None))
        current_value = held.get((r.account_id, r.symbol), 0.0)

        s = by_symbol.setdefault(r.symbol, {
            "symbol": r.symbol, "income": 0.0, "calls": 0.0, "puts": 0.0,
            "equity_income": 0.0, "put_collateral": 0.0,
            "dividends": 0.0, "avg_capital": 0.0, "capital_days": 0.0,
            "current_value": 0.0, "current_shares": 0.0,
            "first_seen": None, "last_seen": None,
            "held_days": 0, "is_held": False, "accounts": []})
        s["income"] += total
        s["calls"] += calls
        s["puts"] += puts
        s["equity_income"] += equity_income
        s["dividends"] += dividends
        s["put_collateral"] += collateral["by_pair"].get((r.account_id, r.symbol), 0.0)
        # Capital-DAYS, not capital. Summing per-account averages would count
        # accounts that held the symbol at different times as if they held it
        # simultaneously — GOOGL read $124,197 of capital when no more than
        # ~$50k was ever deployed at once, halving its yield. Divided by the
        # symbol's own span below, this is the time-weighted average.
        s["capital_days"] += capital * held_days
        s["current_value"] += current_value
        s["current_shares"] += shares.get((r.account_id, r.symbol), 0.0)
        # Symbol span comes from the real first/last across accounts, never
        # from max(held_days): an account with income but no history row falls
        # back to the full period, and taking the max would let that fallback
        # stretch a 100-day position across 207 days.
        if first:
            s["first_seen"] = min(s["first_seen"] or first, first)
            s["last_seen"] = max(s["last_seen"] or last, last)
        s["is_held"] = s["is_held"] or current_value > 0
        s["accounts"].append({
            "account_id": r.account_id,
            "account_name": names.get(r.account_id, r.account_id),
            "income": round(total, 2),
            "calls": round(calls, 2),
            "puts": round(puts, 2),
            "put_collateral": round(collateral["by_pair"].get((r.account_id, r.symbol), 0.0), 2),
            "put_yield_monthly": _monthly(
                puts, collateral["by_pair"].get((r.account_id, r.symbol), 0.0), days),
            "avg_capital": round(capital, 2),
            "current_value": round(current_value, 2),
            "current_shares": round(shares.get((r.account_id, r.symbol), 0.0), 4),
            "is_held": current_value > 0,
            "held_days": held_days,
            "yield_monthly": _monthly(equity_income, capital, held_days),
        })

        a = by_account.setdefault(r.account_id, {
            "account_id": r.account_id,
            "account_name": names.get(r.account_id, r.account_id),
            "income": 0.0, "calls": 0.0, "puts": 0.0, "equity_income": 0.0,
            "avg_capital": 0.0, "symbols": 0, "legs": 0})
        a["income"] += total
        a["calls"] += calls
        a["puts"] += puts
        a["equity_income"] += equity_income
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
        obs = symbol_observed.get(s["symbol"], 0)
        s["held_days"] = max(round(obs * day_scale), 1) if obs else days
        s["avg_capital"] = s["capital_days"] / s["held_days"] if s["held_days"] else 0.0
        del s["capital_days"]
        s["first_seen"] = str(s["first_seen"]) if s["first_seen"] else None
        s["last_seen"] = str(s["last_seen"]) if s["last_seen"] else None
        s["yield_monthly"] = _monthly(s["equity_income"], s["avg_capital"], s["held_days"])
        # Put yield annualises over the FULL period, not held_days: the
        # collateral average already counts days with no put open as zero, so
        # the two sides cover the same window.
        s["put_yield_monthly"] = _monthly(s["puts"], s["put_collateral"], days)
        # Under one contract's worth of shares you cannot write a covered call
        # at all, so the symbol does not belong in the calls table by default
        # however much it earned. Neel, 2026-09-11: LLY (20 sh) and MU (57 sh)
        # "are not worthy of option income ... I don't want to ... crowd the
        # space". Dividends alone do not make a row callable.
        s["callable"] = s["current_shares"] >= SHARES_PER_CONTRACT
        # Open put collateral right now, as opposed to the period average:
        # this is what says "still selling puts on it".
        s["put_collateral_now"] = round(
            collateral["current_by_symbol"].get(s["symbol"], 0.0), 2)
        for k in ("income", "calls", "puts", "equity_income", "dividends",
                  "avg_capital", "current_value", "current_shares", "put_collateral"):
            s[k] = round(s[k], 2)
        symbols.append(s)
    symbols.sort(key=lambda s: (s["yield_monthly"] is None, s["yield_monthly"] or 0))

    accounts = []
    for a in by_account.values():
        a["put_collateral"] = round(collateral["by_account"].get(a["account_id"], 0.0), 2)
        a["put_yield_monthly"] = _monthly(a["puts"], a["put_collateral"], days)
        a["yield_monthly"] = _monthly(a["equity_income"], a["avg_capital"], days)
        for k in ("calls", "puts", "equity_income"):
            a[k] = round(a[k], 2)
        a["income"] = round(a["income"], 2)
        a["avg_capital"] = round(a["avg_capital"], 2)
        accounts.append(a)
    accounts.sort(key=lambda a: -(a["yield_monthly"] or -999))

    return {
        "period": {"start": str(start), "end": str(end), "days": days},
        "targets": {"call_monthly_pct": TARGET_CALL_MONTHLY_PCT,
                    "put_monthly_pct": TARGET_PUT_MONTHLY_PCT},
        "coverage": {
            "history_start": str(HISTORY_START),
            "note": ("Capital is the daily average from "
                     f"{HISTORY_START}; earlier income cannot be yielded."),
        },
        "by_symbol": symbols,
        "by_account": accounts,
        "cash": _cash_performance(db, start, end, days, collateral),
        "collateral_parse": validate_collateral(db, start, end),
        "totals": {
            "income": round(sum(a["income"] for a in accounts), 2),
            "avg_capital": round(sum(a["avg_capital"] for a in accounts), 2),
        },
    }


def validate_collateral(db: Session, start: date, end: date) -> Dict:
    """Health of the snapshot parse behind every put yield on this page."""
    from app.modules.income.put_collateral_service import validate
    return validate(db, start, end)


def _cash_performance(db: Session, start: date, end: date, days: int,
                      collateral: Dict) -> List[Dict]:
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
        # Prefer the parsed per-symbol total: it is the same measurement
        # broken down, and it exists on days the recorded column is NULL.
        parsed = collateral["by_account"].get(account_id, 0.0)
        recorded = float(row.collateral or 0) if row else 0.0
        collateral_used = parsed or recorded
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
            "avg_collateral": round(collateral_used, 2),
            "collateral_recorded": round(recorded, 2),
            "avg_cash_pool": round(true_cash, 2) if cash_backed else None,
            "avg_margin_used": round(margin_used, 2) if margin_used else None,
            "cash_backed": cash_backed,
            "utilization_pct": (round(collateral_used / true_cash * 100, 1)
                                if cash_backed and true_cash else None),
            "idle_cash": (round(true_cash - collateral_used, 2)
                          if cash_backed else None),
            "yield_on_collateral_monthly": _monthly(put_premium, collateral_used, days),
            "yield_on_cash_monthly": (_monthly(put_premium, true_cash, days)
                                      if cash_backed else None),
        })
    out.sort(key=lambda r: -(r["yield_on_collateral_monthly"] or -999))
    return out
