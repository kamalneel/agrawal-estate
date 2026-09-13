"""Backfill investment_holdings_history for dates before the daily snapshot
job existed: lot-engine positions x official daily closes.

WHY
---
The Performance view yields income on AVERAGE CAPITAL, and capital comes from
investment_holdings_history — which begins 2026-02-16, the day the snapshot
job was switched on. Income before that had no denominator, so the view was
clamped there and six weeks of 2026 premium ($59,879) silently fell outside
it. This synthesises the missing days so the window can start where the
income does.

HOW
---
Positions: replay stock_lot / stock_lot_sale day by day. A lot contributes on
day d if bought on/before d, less whatever of it was sold on/before d, LESS
any ACATO transfer-out on/before d. The last term matters: the rebuild
consumes lots on ACATO without writing a sale row, so a replay that only
subtracts sales resurrects positions that left by transfer — the first run
did exactly that, reviving six 2020-era holdings (WYNN, UBER, UAL ...) with
$94K of phantom January capital.

Prices: raw (unadjusted) daily closes from the Robinhood historicals tool,
saved as JSON in --prices-dir. Raw because the lot engine's share counts are
as-of-that-day; split-adjusting would double-adjust.

TWO GATES, then all-or-nothing per (account, symbol)
----------------------------------------------------
1. Every position-day must have a close. A symbol with any unpriced day is
   dropped entirely.
2. The synthetic value on the last backfilled day must be within --tol of the
   first REAL snapshot (--seam) for that pair. A miss means the lot engine's
   share count is wrong for that pair (no lots for a real holding, a phantom,
   a split) — drop it rather than write a wrong denominator.

Dropping is safe because performance_service counts a pair's share-based
income only from its first day of capital: excluded pairs contribute neither
capital nor January calls, so nothing is inflated. What is lost is a little
income on those pairs ($1,108 for Jan-Feb 2026), reported here.

Rows are written with source='backfill_lot_engine' and are idempotent: each
run deletes and rewrites that source for the period. Delete the source to
revert entirely.

Usage:
    python scripts/backfill_holdings_history.py --start 2025-01-02 --end 2026-02-13 \
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

from app.core.database import SessionLocal  # noqa: E402
from sqlalchemy import text  # noqa: E402

SOURCE = "backfill_lot_engine"
US_HOLIDAYS = {  # NYSE closures in scope; extend as needed
    date(2025, 1, 1), date(2025, 1, 9), date(2025, 1, 20), date(2025, 2, 17),
    date(2025, 4, 18), date(2025, 5, 26), date(2025, 6, 19), date(2025, 7, 4),
    date(2025, 9, 1), date(2025, 11, 27), date(2025, 12, 25),
    date(2026, 1, 1), date(2026, 1, 19),
}


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
    """(day, account, symbol) -> shares, from lots less sales less ACATO."""
    end = days[-1]
    lots = db.execute(text("""
        SELECT lot_id, account_id, symbol, purchase_date, quantity
        FROM stock_lot WHERE purchase_date <= :end
    """), {"end": end}).mappings().all()
    sales = defaultdict(list)
    for s in db.execute(text("""
        SELECT lot_id, sale_date, quantity_sold FROM stock_lot_sale WHERE sale_date <= :end
    """), {"end": end}).mappings().all():
        sales[s["lot_id"]].append((s["sale_date"], float(s["quantity_sold"])))
    # ACATO: shares out on a date, no sale row. Apply FIFO against the
    # account+symbol book on that date.
    # ACATO quantity is NULL when the ENTIRE position was transferred (the
    # rebuild treats it the same way). None here means "all shares held".
    acato = defaultdict(list)
    for a in db.execute(text("""
        SELECT account_id, symbol, transaction_date, quantity FROM investment_transactions
        WHERE transaction_type = 'ACATO' AND transaction_date <= :end
    """), {"end": end}).mappings().all():
        q = float(a["quantity"]) if a["quantity"] is not None else None
        acato[(a["account_id"], a["symbol"])].append((a["transaction_date"], q))

    by_pair = defaultdict(list)
    for l in lots:
        by_pair[(l["account_id"], l["symbol"])].append(l)

    pos = defaultdict(float)
    for pair, plots in by_pair.items():
        plots.sort(key=lambda l: (l["purchase_date"], l["lot_id"]))
        # A NULL-quantity ACATO transfers out the ENTIRE position as of that
        # date — i.e. every lot bought on/before it. Lots bought afterwards
        # are new capital and must survive; the first version of this zeroed
        # the pair permanently and dropped a real $38K NVDA position.
        full_outs = sorted(ad for ad, q in acato.get(pair, ()) if q is None)
        for d in days:
            rem = []
            for l in plots:
                if l["purchase_date"] > d:
                    continue
                # wiped by a whole-position transfer between purchase and d?
                if any(l["purchase_date"] <= ad <= d for ad in full_outs):
                    continue
                q = float(l["quantity"]) - sum(qs for sd, qs in sales[l["lot_id"]] if sd <= d)
                if q > 1e-6:
                    rem.append(q)
            partial_out = sum(q for ad, q in acato.get(pair, ()) if q is not None and ad <= d)
            held = sum(rem) - partial_out
            if held > 1e-6:
                pos[(d,) + pair] = held
    return pos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=date.fromisoformat, required=True)
    ap.add_argument("--end", type=date.fromisoformat, required=True)
    ap.add_argument("--seam", type=date.fromisoformat, required=True,
                    help="first REAL snapshot date to reconcile the last synthetic day against")
    ap.add_argument("--prices-dir", required=True)
    ap.add_argument("--tol", type=float, default=8.0, help="gate-2 tolerance, percent")
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
    print(f"rows to write: {len(kept)}")

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
