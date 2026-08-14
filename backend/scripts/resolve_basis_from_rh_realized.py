"""Resolve BASIS_UNKNOWN lots from Robinhood's realized P&L.

!! NOT WIRED IN — writes to the WRONG section of basis_overrides.json. !!

Kept for the RH_REALIZED data below (16 account/symbol pulls) and the method,
both of which are sound. What is wrong is the target.

Discovered 2026-08-14 after running it: reported income comes from the STORED
`cost_basis`/`gain_loss` columns on stock_lot_sale, not from the lot's
cost_per_share (see get_realized_pnl_by_period). basis_overrides.json has two
sections for exactly that reason -- "lots" and "sales" -- and this script only
writes "lots", so its output is inert for income and leaves lot-level basis
contradicting sale-level basis. It was applied and then reverted.

The wider mistake: `BASIS_UNKNOWN` on a stock_lot is a leftover label, not a
live defect. Zero sale rows are flagged BASIS_UNKNOWN, so nothing is excluded
from or inflated in reported P/L; the 49 labelled lots all had their SALES
resolved in July 2026 (TRANSFER_DATE_PRICE, F8949_2024_PRORATA, 1099B_2025,
RH_AVG_COST, SALE_DATE_PROXY). Counting lot labels overstated the problem.

The genuine residual is narrower: 24 sale rows resolved as
SALE_DATE_PROXY -- "no acquisition record; P/L=0" -- covering $102,045.61 of
proceeds that contribute exactly zero P/L. Robinhood's realized gain can
replace that guess with a real figure. To do it, rework this to emit "sales"
entries (account_id, symbol, sale_date, quantity_sold, proceeds, cost_basis,
is_long_term, note) matching apply_basis_overrides' UPDATE, and target only
the SALE_DATE_PROXY rows.


The rebuild creates zero-basis lots in two cases (see rebuild_stock_lots.py):
ACAT transfers that arrive without cost basis, and sales that exceed recorded
holdings. Both book their entire proceeds as gain. As of 2026-08-14 that was
49 lots and $317,912 of proceeds counted as pure profit -- e.g. Jaya's IRA
SNAP showed a $12,819 GAIN where the reality was a $33,893 LOSS.

Why realized P&L rather than the RH_AVG_COST route used in July 2026: these
lots are all fully sold, so get_equity_tax_lots (open lots only) can't see
them and there is no current average cost to read. get_pnl_trade_history
reaches back to 2024 and reports the gain Robinhood actually booked.

Deriving basis from it is safe even though Robinhood folds option premium
into assignment proceeds: premium inflates proceeds and gain by the SAME
amount, so `basis = price*qty - realized_gain` is premium-independent.

Method, per (account, symbol, sale_date):
  true_total_basis = sum over RH trades of (price*qty - realized_gain)
  known_basis      = basis already carried by resolved lots in that sale
  remainder        = true_total_basis - known_basis  -> split pro-rata across
                     the unknown lots by share count
This makes the SALE's realized P/L match Robinhood, which is the figure the
Income page actually reports. It does NOT claim the per-share number is the
original purchase price -- lot selection differs (Robinhood picks specified
lots; the rebuild is FIFO), so the remainder is an allocation, not a receipt.
Notes record that honestly as BASIS_RESOLVED:RH_REALIZED.

A negative or implausible remainder is reported and NOT written -- that means
the known lots already exceed Robinhood's total and something else is wrong.

Usage:
    venv/bin/python scripts/resolve_basis_from_rh_realized.py [--write]
Then rerun rebuild_stock_lots.py to apply.
"""
import argparse
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from sqlalchemy import text

OVERRIDES = Path(__file__).resolve().parent.parent.parent / "data" / "basis_overrides.json"

# Pulled from get_pnl_trade_history(span="all"), 2026-08-14.
# (account_id, symbol) -> [(sale_date, quantity, price, realized_gain)]
#
# EQUITY rows only. That feed mixes in option closes, recognisable by a tiny
# negative `price` (the per-contract net, e.g. -1 / -21 / -54) against a
# quantity that is a contract count. Including one would corrupt the derived
# basis, so each entry below was checked against the ledger's own share count.
#
# Dates are the LEDGER's sale_date. Robinhood timestamps in UTC and can be a
# day later — the 2025-08-29 NVDA assignment arrives as 2025-08-30T04:11Z.
RH_REALIZED = {
    ("jaya_ira", "NVDA"): [("2026-05-15", "1000", "204.97905", "152977.34")],
    ("jaya_ira", "SNAP"): [
        ("2024-06-25", "300", "16.45", "-12964.17"),
        ("2024-06-17", "300", "15.95", "-15221.2"),
        ("2024-06-17", "203", "15.27098522167487684729064039", "-5708.07"),
    ],
    ("jaya_ira", "AAPL"): [("2024-12-16", "50", "249.5", "6663.81")],
    ("jaya_ira", "IBIT"): [("2026-06-18", "400", "36.2719", "2956.76")],
    ("jaya_brokerage", "SNAP"): [("2024-04-15", "500", "10.6329", "-5226.05")],
    ("neel_retirement", "TQQQ"): [
        ("2024-04-04", "454", "62.145", "-1901.37"),
        ("2024-05-10", "3", "59.5", "-16.35"),
        ("2024-05-22", "200", "64.95", "-220.6"),
    ],
    ("neel_retirement", "VOO"): [
        ("2025-10-24", "11.662239", "622.8143669496054745576728448", "1358.07"),
        ("2025-10-24", "38.528069", "622.8150183182032818722370955", "3795.86"),
    ],
    ("neel_retirement", "SNAP"): [("2024-04-04", "500", "11.22", "-19601.72")],
    ("neel_retirement", "IBIT"): [("2026-05-22", "1300", "43.473", "13198.27")],
    ("neel_retirement", "AVGO"): [("2026-05-22", "400", "422.24755", "101786.06")],
    ("neel_retirement", "NFLX"): [("2026-05-22", "500", "89.64948", "1065.71")],
    ("neel_retirement", "NVDA"): [
        ("2025-08-29", "300", "177.8995666666666666666666667", "23990.28"),
        ("2026-05-15", "200", "199.4291", "6799.71"),
    ],
    ("neel_brokerage", "TQQQ"): [
        ("2024-03-28", "100", "61.9993", "249.93"),
        ("2024-04-15", "100", "58.075", "451.5"),
        ("2024-09-19", "15", "70.26", "325.95"),
        ("2024-11-04", "35", "70.64114285714285714285714286", "-372"),
    ],
    ("neel_brokerage", "SHOP"): [("2024-03-28", "100", "77.8091", "-1754.17")],
    ("neel_brokerage", "AVGO"): [("2026-05-22", "400", "423.997525", "59994.67")],
}


def main(write: bool) -> None:
    db = SessionLocal()
    # basis Robinhood implies, per (account, symbol, sale_date)
    rh_basis = defaultdict(Decimal)
    for (acct, sym), trades in RH_REALIZED.items():
        for d, qty, price, gain in trades:
            rh_basis[(acct, sym, d)] += (
                Decimal(price) * Decimal(qty) - Decimal(gain))

    resolutions, problems = [], []
    for (acct, sym, sale_date), true_basis in sorted(rh_basis.items()):
        rows = db.execute(text("""
            SELECT l.lot_id, l.purchase_date, l.quantity, l.cost_per_share,
                   s.quantity_sold, COALESCE(l.notes,'') AS notes
            FROM stock_lot_sale s JOIN stock_lot l ON l.lot_id = s.lot_id
            WHERE l.account_id = :a AND l.symbol = :s AND s.sale_date = :d
        """), {"a": acct, "s": sym, "d": sale_date}).fetchall()
        if not rows:
            problems.append(f"{acct} {sym} {sale_date}: no sale rows in ledger")
            continue

        unknown = [r for r in rows if r.notes.startswith("BASIS_UNKNOWN")]
        if not unknown:
            continue  # already resolved
        known_basis = sum(
            (Decimal(str(r.quantity_sold)) * Decimal(str(r.cost_per_share))
             for r in rows if not r.notes.startswith("BASIS_UNKNOWN")),
            Decimal(0))
        remainder = true_basis - known_basis
        unknown_shares = sum(Decimal(str(r.quantity_sold)) for r in unknown)

        if remainder <= 0 or unknown_shares <= 0:
            problems.append(
                f"{acct} {sym} {sale_date}: remainder {remainder:.2f} "
                f"(RH total {true_basis:.2f} - known {known_basis:.2f}) — NOT written")
            continue

        per_share = remainder / unknown_shares
        for r in unknown:
            resolutions.append({
                "account_id": acct,
                "symbol": sym,
                "purchase_date": r.purchase_date.isoformat(),
                "quantity": f"{float(r.quantity):.6f}",
                "cost_per_share": f"{per_share:.4f}",
                "note": (f"BASIS_RESOLVED:RH_REALIZED (was {r.notes}); allocated from "
                         f"Robinhood realized P&L on the {sale_date} sale "
                         f"(total basis {true_basis:.2f}, known {known_basis:.2f}) — "
                         f"an allocation across unknown lots, not an observed purchase price"),
            })
        print(f"  {acct:<17} {sym:<5} {sale_date}  RH basis {float(true_basis):>12,.2f} "
              f"- known {float(known_basis):>11,.2f} -> {float(per_share):>9,.4f}/sh "
              f"over {float(unknown_shares):.2f} sh")

    if problems:
        print("\nNOT resolved:")
        for p in problems:
            print("  " + p)

    if not write:
        print(f"\n{len(resolutions)} resolutions computed (dry run — rerun with --write)")
        return

    doc = json.loads(OVERRIDES.read_text())
    existing = {(o["account_id"], o["symbol"], o["purchase_date"]) for o in doc["lots"]}
    added = [r for r in resolutions
             if (r["account_id"], r["symbol"], r["purchase_date"]) not in existing]
    doc["lots"].extend(added)
    OVERRIDES.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"\nwrote {len(added)} new resolutions to {OVERRIDES.name} "
          f"({len(resolutions) - len(added)} already present)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    main(ap.parse_args().write)
