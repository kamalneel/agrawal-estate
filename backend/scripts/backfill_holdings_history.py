"""Backfill investment_holdings_history for dates before the daily snapshot
job existed: replayed share counts x official daily closes.

WHY
---
The Performance view yields income on AVERAGE CAPITAL, and capital comes from
investment_holdings_history — which begins 2026-02-16, the day the snapshot
job was switched on. Income before that had no denominator, so the view was
clamped there and six weeks of 2026 premium ($59,879) silently fell outside
it. This synthesises the missing days so the window can start where the
income does. The Investments page draws the same series, and its calendar-
year buttons (2024, 2025 ...) only exist for years that have rows.

HOW
---
Positions: replay investment_transactions day by day per (account, symbol),
in the SHARE UNITS OF THAT DAY. BUY/ACATI/CONV add, SELL/ACATO/LIQ remove
(null quantity = the whole position), SPL/SPLIT adds the credited shares —
so the count steps 16 -> 160 on NVDA's 2024-06-10 split, exactly as the
account did. MCP-inferred assignments are expanded the way the lot rebuild
expands them (shared code), so the two never disagree about a share move.

Why transactions and not stock_lot: the lot rebuild scales every lot that
is OPEN at a split into post-split units, retroactively, while lots closed
before the split keep pre-split units. A lot-level replay therefore hands
back a mix of units for any day before a split, and the first version of
this script did exactly that — its NFLX rows for Jan–Nov 2025 carried the
10:1-scaled quantity against the raw pre-split price, overstating
neel_retirement by $217K–$458K every month until the 2025-11-17 split
(found 2026-09-13 against the monthly statements; gate 3 below exists so
it cannot recur). Transactions have no such ambiguity.

Prices: RAW (unadjusted) daily closes from the Robinhood historicals tool
(adjustment_type='none'), saved as JSON in --prices-dir. Raw because the
replayed counts are as-of-that-day; split-adjusting would double-adjust.

THREE GATES, then all-or-nothing per (account, symbol)
----------------------------------------------------
1. Every position-day must have a close. A symbol with any unpriced day is
   dropped entirely.
2. The synthetic value on the last backfilled day must be within --tol of the
   first REAL snapshot (--seam) for that pair. A miss means the replayed
   share count is wrong for that pair (a missing opening position, a
   phantom, an unrecorded corporate action) — drop it rather than write a
   wrong denominator.
3. The source's own control total (validate-parser-against-source-totals):
   on every month-end that has a statement in portfolio_snapshots, the
   synthetic account total must be within --tol of the statement's
   securities_value. This is the one check that sees INSIDE the period —
   gate 2 only sees the seam and passed the NFLX rows above. A breach
   ABORTS the run; it is not attributable to one pair.

Dropping is safe because performance_service counts a pair's share-based
income only from its first day of capital: excluded pairs contribute neither
capital nor income, so nothing is inflated. What is lost is a little income
on those pairs, reported here.

Rows are written with source='backfill_lot_engine' and are idempotent: each
run deletes and rewrites that source for the period. Delete the source to
revert entirely.

Where to start: the Robinhood book is complete from 2024-03-28, the day the
Schwab ACATS transfer landed (Schwab's 2024-03-31 statement shows $654 left
behind). Before that the ledger sees only the handful of positions opened
at Robinhood in early March against ~$800K still at Schwab, which would
draw as a near-empty portfolio, not a small one.

Usage:
    python scripts/backfill_holdings_history.py --start 2024-03-28 --end 2026-02-13 \
        --seam 2026-02-16 --prices-dir data/price-history [--save]
"""
import argparse
import glob
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.database import SessionLocal  # noqa: E402
from sqlalchemy import text  # noqa: E402
from rebuild_stock_lots import expand_inferred_assignments, SHARES_IN  # noqa: E402

SOURCE = "backfill_lot_engine"
US_HOLIDAYS = {  # NYSE closures in scope; extend as needed
    date(2024, 1, 1), date(2024, 1, 15), date(2024, 2, 19), date(2024, 3, 29),
    date(2024, 5, 27), date(2024, 6, 19), date(2024, 7, 4), date(2024, 9, 2),
    date(2024, 11, 28), date(2024, 12, 25),
    date(2025, 1, 1), date(2025, 1, 9), date(2025, 1, 20), date(2025, 2, 17),
    date(2025, 4, 18), date(2025, 5, 26), date(2025, 6, 19), date(2025, 7, 4),
    date(2025, 9, 1), date(2025, 11, 27), date(2025, 12, 25),
    date(2026, 1, 1), date(2026, 1, 19),
}

#: Below this the replay treats a position as closed; guards float dust.
EPS = 1e-6


def trading_days(start, end):
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in US_HOLIDAYS:
            yield d
        d += timedelta(days=1)


def load_prices(prices_dir):
    closes = {}
    for path in glob.glob(str(Path(prices_dir) / "*.json")):
        try:
            data = json.load(open(path))
        except Exception:
            continue
        for r in data.get("data", {}).get("results", []):
            for b in r.get("bars", []):
                if b.get("interpolated"):
                    continue
                closes[(r["symbol"], b["begins_at"][:10])] = float(b["close_price"])
    return closes


def replay_positions(db, days):
    """(day, account, symbol) -> shares held, in that day's units.

    Same transaction universe and same inferred-assignment expansion as
    scripts/rebuild_stock_lots.py, so a share the lot engine knows about is
    a share this replay knows about.
    """
    end = days[-1]
    rows = db.execute(text("""
        SELECT a.account_id, t.source, t.symbol, t.transaction_date,
               t.transaction_type, t.quantity, t.amount, t.description, t.id
        FROM investment_transactions t
        JOIN investment_accounts a ON a.account_id = t.account_id
        WHERE a.is_active = 'Y'
          AND t.transaction_date <= :end
          AND t.transaction_type IN ('BUY','BOUGHT','SELL','SOLD','ACATI',
                                     'ACATO','SPL','SPLIT','CONV','LIQ',
                                     'OASGN')
          AND t.symbol IS NOT NULL AND t.symbol NOT IN ('', 'UNKNOWN')
        ORDER BY a.account_id, t.symbol, t.transaction_date, t.id
    """), {"end": end}).fetchall()
    txns = expand_inferred_assignments(rows)

    by_pair = defaultdict(list)
    for t in txns:
        by_pair[(t.account_id, t.symbol)].append(t)

    pos = {}
    short_sales = 0
    for pair, plist in by_pair.items():
        # Same-day inflows before outflows, as the lot rebuild orders them:
        # the ACATS-in and the sale of those very shares share a date (SHOP,
        # U, APPS 2024-03-28) and the sale's row id happens to be lower.
        plist.sort(key=lambda t: (t.transaction_date,
                                  0 if t.transaction_type in SHARES_IN else 1, t.id))
        held = 0.0
        i = 0
        for d in days:
            while i < len(plist) and plist[i].transaction_date <= d:
                t = plist[i]
                i += 1
                q = float(t.quantity) if t.quantity is not None else None
                ttype = t.transaction_type
                if ttype in ("BUY", "BOUGHT", "ACATI", "CONV", "SPL", "SPLIT"):
                    if q and q > 0:
                        held += q
                elif ttype in ("SELL", "SOLD", "ACATO", "LIQ"):
                    # null quantity: the entire position leaves (ACATO whole-
                    # position transfer, LIQ issuer liquidation). A cash-only
                    # ACATO row has no shares to remove either way.
                    out = q if (q and q > 0) else (held if ttype in ("ACATO", "LIQ") else 0.0)
                    if out > held + EPS:
                        # The lot rebuild inserts a synthetic opening lot here
                        # (shares that arrived without a share-level record).
                        # The equivalent for a share count is: the position
                        # was at least this big, and is now empty.
                        short_sales += 1
                    held = max(held - out, 0.0)
            if held > EPS:
                pos[(d,) + pair] = held
    if short_sales:
        print(f"note: {short_sales} sells exceeded the replayed position (synthetic-opening "
              f"cases in the lot engine); the days before each are understated")
    return pos


def month_ends(days):
    """Last trading day of each calendar month in `days`."""
    last = {}
    for d in days:
        last[(d.year, d.month)] = d
    return set(last.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=date.fromisoformat, required=True)
    ap.add_argument("--end", type=date.fromisoformat, required=True)
    ap.add_argument("--seam", type=date.fromisoformat, required=True,
                    help="first REAL snapshot date to reconcile the last synthetic day against")
    ap.add_argument("--prices-dir", required=True)
    ap.add_argument("--tol", type=float, default=8.0, help="gate tolerance, percent")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()

    days = list(trading_days(a.start, a.end))
    closes = load_prices(a.prices_dir)
    db = SessionLocal()
    pos = replay_positions(db, days)
    print(f"period {a.start} -> {a.end}: {len(days)} trading days; "
          f"{len(pos)} position-days across {len({s for (_, _, s) in pos})} symbols; "
          f"{len(closes)} closes loaded")

    # gate 1
    unpriced = defaultdict(int)
    for (d, acct, sym) in pos:
        if (sym, str(d)) not in closes:
            unpriced[sym] += 1
    if unpriced:
        print(f"GATE 1: {sum(unpriced.values())} unpriced position-days; symbols needing prices:")
        for s, n in sorted(unpriced.items(), key=lambda x: -x[1]):
            print(f"   {s:<7}{n} days")
    else:
        print("GATE 1: every position-day priced")
    bad1 = set(unpriced)

    rows = [{"account_id": acct, "symbol": sym, "snapshot_date": d, "quantity": q,
             "market_value": q * closes[(sym, str(d))]}
            for (d, acct, sym), q in pos.items() if sym not in bad1]

    # gate 2
    real = {(r.account_id, r.symbol): float(r.market_value) for r in db.execute(text("""
        SELECT account_id, symbol, market_value FROM investment_holdings_history
        WHERE snapshot_date = :seam AND source <> :src"""), {"seam": a.seam, "src": SOURCE}).fetchall()}
    last = days[-1]
    syn = {(r["account_id"], r["symbol"]): r["market_value"] for r in rows if r["snapshot_date"] == last}
    excluded = set()
    print(f"GATE 2: synthetic {last} vs real {a.seam}")
    for k in sorted(set(syn) | set(real)):
        sv, rv = syn.get(k, 0.0), real.get(k, 0.0)
        if sv < 500 and rv < 500:
            continue
        diff = (sv - rv) / rv * 100 if rv else float("inf")
        if abs(diff) > a.tol:
            excluded.add(k)
            print(f"   EXCLUDE {k[0]:<17}{k[1]:<6} syn ${sv:>11,.0f}  real ${rv:>11,.0f}  {diff:>7.1f}%")
    kept = [r for r in rows if (r["account_id"], r["symbol"]) not in excluded]
    kv = sum(v for k, v in syn.items() if k not in excluded)
    print(f"   {len(excluded)} pairs excluded; kept synthetic {last} = ${kv:,.0f} vs real {a.seam} = ${sum(real.values()):,.0f}")

    # gate 3: statements. Month-end securities_value per account is the
    # source's own total for the same thing this script synthesises. It
    # carries the options marks too (short calls read negative), which is
    # why the tolerance is a few percent and not zero.
    stmts = db.execute(text("""
        SELECT account_id, statement_date, securities_value FROM portfolio_snapshots
        WHERE securities_value IS NOT NULL
          AND statement_date BETWEEN :s AND :e
          AND statement_date = (date_trunc('month', statement_date) + INTERVAL '1 month - 1 day')::date
        ORDER BY statement_date, account_id
    """), {"s": a.start, "e": a.end}).fetchall()
    me = month_ends(days)
    # statement date is a calendar month-end; the synthetic day is the last
    # trading day of that month — and the one before it, see below
    last_trading = {(d.year, d.month): d for d in me}
    prev_day = {d: days[i - 1] for i, d in enumerate(days) if i and d in me}
    check_days = set(me) | set(prev_day.values())
    syn_by_acct_day = defaultdict(float)
    for r in kept:
        if r["snapshot_date"] in check_days:
            syn_by_acct_day[(r["account_id"], r["snapshot_date"])] += r["market_value"]
    breaches = []
    print(f"GATE 3: month-end synthetic vs statement securities_value ({len(stmts)} statements)")
    for s in stmts:
        d = last_trading.get((s.statement_date.year, s.statement_date.month))
        if d is None:
            continue
        rv = float(s.securities_value)
        sv = syn_by_acct_day.get((s.account_id, d), 0.0)
        if rv < 500 and sv < 500:
            continue
        diff = (sv - rv) / rv * 100 if rv else float("inf")
        note = ""
        if abs(diff) > a.tol and d in prev_day:
            # An assignment dated the last trading day of the month lands on
            # the NEXT statement: Robinhood's 2025-12-31 statement for
            # jaya_brokerage omits the 200 AVGO shares put to the account
            # that day (+13.2% here), and the 2025-08-31 one for
            # neel_retirement still carries the 300 NVDA shares called away
            # on 08-29 (-14.2%). The statement is right about the day BEFORE,
            # so a miss on the day is accepted when the prior day agrees.
            # One day, not a window: a wider tolerance would let a real
            # missing position through.
            pv = syn_by_acct_day.get((s.account_id, prev_day[d]), 0.0)
            pdiff = (pv - rv) / rv * 100 if rv else float("inf")
            if abs(pdiff) <= a.tol:
                note = f"  (day-before ${pv:,.0f} {pdiff:+.1f}% — month-end assignment, accepted)"
                diff = pdiff
        flag = "BREACH " if abs(diff) > a.tol else "ok     "
        print(f"   {flag}{s.statement_date} {s.account_id:<17} syn ${sv:>11,.0f}  stmt ${rv:>11,.0f}  "
              f"{(sv - rv) / rv * 100 if rv else float('inf'):>7.1f}%{note}")
        if abs(diff) > a.tol:
            breaches.append((s.statement_date, s.account_id, diff))
    print(f"rows to write: {len(kept)}")
    if breaches:
        print(f"GATE 3 FAILED: {len(breaches)} account-months outside ±{a.tol}% — nothing written. "
              f"Find the position that disagrees with the statement before rerunning.")
        sys.exit(1)

    if not a.save:
        print("DRY RUN — nothing written")
        return
    db.execute(text("""DELETE FROM investment_holdings_history
        WHERE source = :src AND snapshot_date BETWEEN :s AND :e"""),
        {"src": SOURCE, "s": a.start, "e": a.end})
    db.execute(text("""INSERT INTO investment_holdings_history
        (source, account_id, symbol, snapshot_date, quantity, market_value, created_at, updated_at)
        VALUES (:src, :a, :s, :d, :q, :v, NOW(), NOW())"""),
        [{"src": SOURCE, "a": r["account_id"], "s": r["symbol"], "d": r["snapshot_date"],
          "q": r["quantity"], "v": r["market_value"]} for r in kept])
    db.commit()
    print(f"COMMITTED {len(kept)} rows (source={SOURCE}, {a.start}..{a.end})")


if __name__ == "__main__":
    main()
