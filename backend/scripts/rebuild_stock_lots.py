"""Rebuild stock_lot / stock_lot_sale from transaction history (all accounts).

Replays every equity transaction in investment_transactions chronologically,
per (account, symbol), FIFO. Replaces all existing lot data — the tables are
derived data; sources are never touched. Re-runnable. Back up first:

    pg_dump -d agrawal_estate -t stock_lot -t stock_lot_sale --data-only -f backup.sql
    cd backend && venv/bin/python scripts/rebuild_stock_lots.py [--dry-run]

Event handling (see docs/INCOME-UNIFICATION-SPEC.md):
- BUY/BOUGHT           -> lot at transaction cost (assignments arrive as BUY
                          at strike, which is the income-ledger basis rule)
- SELL/SOLD            -> FIFO consumption -> stock_lot_sale rows
                          (call assignments arrive as SELL at strike)
- ACATI/CONV w/ shares -> lot with unknown basis, notes=BASIS_UNKNOWN:ACAT
- ACATO                -> shares out, no sale row (null qty = entire position)
- SPL/SPLIT            -> scale open lot quantities by (held+credited)/held
- SELL exceeding held  -> synthetic zero-basis lot for the shortfall,
                          notes=BASIS_UNKNOWN:SYNTHETIC_OPENING (positions
                          that arrived without share-level transfer records)

Unknown-basis lots carry cost_basis=0 and a BASIS_UNKNOWN:* note; sale rows
that consumed them are flagged BASIS_UNKNOWN in notes. Income code must
exclude/flag those P/L figures until basis is resolved (resolution hierarchy:
1099-B, Robinhood avg cost via MCP, market price at transfer date).

After each rebuild, resolutions recorded in data/basis_overrides.json are
reapplied (lots matched on account+symbol+purchase_date; sale rows on
account+symbol+sale_date+quantity+proceeds), so a rebuild never regresses
previously-resolved basis. New resolutions must be added to that file.
"""
import argparse
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.modules.tax.models import StockLot, StockLotSale
from sqlalchemy import text

SHARES_IN = ("BUY", "BOUGHT", "ACATI", "CONV", "SPL", "SPLIT")
EPS = Decimal("0.00000001")


class Lot:
    """In-memory lot. qty/cost mutate as sales consume; orig_* preserved."""

    def __init__(self, account_id, source, symbol, lot_date, qty, cost,
                 known, txid, note=None):
        self.account_id, self.source, self.symbol = account_id, source, symbol
        self.lot_date, self.txid, self.note, self.known = lot_date, txid, note, known
        self.qty, self.cost = qty, cost
        self.orig_qty, self.orig_cost = qty, cost

    def scale(self, ratio):
        self.qty *= ratio
        self.orig_qty *= ratio


def rebuild(db, dry_run: bool):
    rows = db.execute(text("""
        SELECT a.account_id, t.source, t.symbol, t.transaction_date,
               t.transaction_type, t.quantity, t.amount, t.id
        FROM investment_transactions t
        JOIN investment_accounts a
          ON a.account_id = t.account_id AND a.source = t.source
        WHERE a.is_active = 'Y'
          AND t.transaction_type IN ('BUY','BOUGHT','SELL','SOLD','ACATI',
                                     'ACATO','SPL','SPLIT','CONV','LIQ')
          AND t.symbol IS NOT NULL AND t.symbol NOT IN ('', 'UNKNOWN')
        ORDER BY a.account_id, t.symbol, t.transaction_date, t.id
    """)).fetchall()

    groups = defaultdict(list)
    for r in rows:
        groups[(r.account_id, r.source, r.symbol)].append(r)

    all_lots, sales = [], []
    stats = defaultdict(int)

    for (account_id, source, symbol), txns in groups.items():
        # Same-day ordering: share credits before debits (transfer, then sell)
        txns.sort(key=lambda r: (r.transaction_date,
                                 0 if r.transaction_type in SHARES_IN else 1,
                                 r.id))
        book: list[Lot] = []

        def add_lot(t, qty, cost, known, note=None):
            lot = Lot(account_id, source, symbol, t.transaction_date,
                      qty, cost, known, t.id, note)
            book.append(lot)
            all_lots.append(lot)
            return lot

        for t in txns:
            qty, ttype = t.quantity, t.transaction_type

            if ttype in ("BUY", "BOUGHT"):
                if qty and qty > 0:
                    add_lot(t, qty, abs(t.amount or 0), True)
                    stats["buy_lots"] += 1

            elif ttype in ("ACATI", "CONV"):
                if qty and qty > 0:  # skip cash-only ACAT rows
                    add_lot(t, qty, Decimal(0), False, "BASIS_UNKNOWN:ACAT")
                    stats["acat_lots"] += 1

            elif ttype in ("SPL", "SPLIT"):
                held = sum(l.qty for l in book)
                if held > 0 and qty and qty > 0:
                    ratio = (held + qty) / held
                    for l in book:
                        l.scale(ratio)
                    stats["splits"] += 1
                elif qty and qty > 0:
                    add_lot(t, qty, Decimal(0), False,
                            "BASIS_UNKNOWN:SPLIT_NO_POSITION")
                    stats["split_orphans"] += 1

            elif ttype in ("SELL", "SOLD", "ACATO", "LIQ"):
                is_sale = ttype != "ACATO"
                # ACATO with null quantity = entire position transferred out.
                # LIQ (issuer liquidation, e.g. the OIL ETN in Apr 2020) is a
                # forced sale of the whole position; qty is usually null and
                # proceeds are in amount.
                remaining = qty if (qty and qty > 0) else (
                    sum(l.qty for l in book)
                    if (not is_sale or ttype == "LIQ") else Decimal(0))
                if remaining <= 0:
                    continue

                if is_sale:
                    held = sum(l.qty for l in book)
                    if held + EPS < remaining:
                        shortfall = remaining - held
                        lot = Lot(account_id, source, symbol,
                                  t.transaction_date, shortfall, Decimal(0),
                                  False, None, "BASIS_UNKNOWN:SYNTHETIC_OPENING")
                        book.insert(0, lot)
                        all_lots.append(lot)
                        stats["synthetic_lots"] += 1
                    proceeds_ps = abs(t.amount or 0) / remaining

                while remaining > EPS and book:
                    lot = book[0]
                    take = min(lot.qty, remaining)
                    cost_portion = (lot.cost * take / lot.qty
                                    if lot.qty else Decimal(0))
                    if is_sale:
                        sales.append({"lot": lot, "date": t.transaction_date,
                                      "txid": t.id, "qty": take,
                                      "proceeds_ps": proceeds_ps,
                                      "cost": cost_portion,
                                      "known": lot.known})
                        stats["sale_rows"] += 1
                        if not lot.known:
                            stats["sale_rows_unknown_basis"] += 1
                    lot.qty -= take
                    lot.cost -= cost_portion
                    remaining -= take
                    if lot.qty <= EPS:
                        book.pop(0)

    print(dict(stats))
    print(f"lots: {len(all_lots)}, sale rows: {len(sales)}")
    if dry_run:
        print("DRY RUN — no writes")
        return

    db.execute(text("DELETE FROM stock_lot_sale"))
    db.execute(text("DELETE FROM stock_lot"))

    lot_rows = {}
    for l in all_lots:
        remaining = l.qty if l.qty > EPS else Decimal(0)
        row = StockLot(
            symbol=l.symbol, purchase_date=l.lot_date,
            quantity=l.orig_qty, cost_basis=l.orig_cost,
            cost_per_share=(l.orig_cost / l.orig_qty if l.orig_qty
                            else Decimal(0)),
            account_id=l.account_id, source=l.source,
            purchase_transaction_id=l.txid,
            quantity_remaining=remaining,
            status=("closed" if remaining == 0
                    else "partial" if remaining < l.orig_qty else "open"),
            lot_method="FIFO", notes=l.note,
        )
        db.add(row)
        lot_rows[id(l)] = row
    db.flush()

    for s in sales:
        lot_row = lot_rows[id(s["lot"])]
        proceeds = s["proceeds_ps"] * s["qty"]
        days = (s["date"] - lot_row.purchase_date).days
        db.add(StockLotSale(
            lot_id=lot_row.lot_id, sale_date=s["date"],
            sale_transaction_id=s["txid"], quantity_sold=s["qty"],
            proceeds=proceeds, proceeds_per_share=s["proceeds_ps"],
            cost_basis=s["cost"], gain_loss=proceeds - s["cost"],
            holding_period_days=days, is_long_term=days > 365,
            tax_year=s["date"].year, wash_sale=False,
            notes=None if s["known"] else "BASIS_UNKNOWN",
        ))
    db.commit()
    print("written")
    apply_basis_overrides(db)


def apply_basis_overrides(db):
    """Reapply persisted basis resolutions (data/basis_overrides.json)."""
    path = Path(__file__).resolve().parent.parent.parent / "data" / "basis_overrides.json"
    if not path.exists():
        print("no basis_overrides.json — skipping override pass")
        return
    ov = json.loads(path.read_text())
    n_lots = 0
    for o in ov.get("lots", []):
        res = db.execute(text("""
            UPDATE stock_lot
            SET cost_per_share=:cps, cost_basis=ROUND(:cps*quantity, 2),
                notes=:note, updated_at=NOW()
            WHERE account_id=:acct AND symbol=:sym AND purchase_date=:pd
              AND notes LIKE 'BASIS_UNKNOWN%'
        """), {"cps": Decimal(o["cost_per_share"]), "note": o["note"],
               "acct": o["account_id"], "sym": o["symbol"],
               "pd": o["purchase_date"]})
        n_lots += res.rowcount
    n_sales = 0
    for o in ov.get("sales", []):
        res = db.execute(text("""
            UPDATE stock_lot_sale s
            SET cost_basis=:cb, gain_loss=s.proceeds-:cb,
                is_long_term=:lt, notes=:note, updated_at=NOW()
            FROM stock_lot l
            WHERE l.lot_id=s.lot_id AND s.notes='BASIS_UNKNOWN'
              AND l.account_id=:acct AND l.symbol=:sym AND s.sale_date=:sd
              AND ABS(s.quantity_sold-:qty) < 0.001
              AND ABS(s.proceeds-:pr) < 0.02
        """), {"cb": Decimal(o["cost_basis"]), "lt": o["is_long_term"],
               "note": o["note"], "acct": o["account_id"], "sym": o["symbol"],
               "sd": o["sale_date"], "qty": Decimal(o["quantity_sold"]),
               "pr": Decimal(o["proceeds"])})
        n_sales += res.rowcount
    db.commit()
    unresolved = db.execute(text(
        "SELECT COUNT(*) FROM stock_lot_sale WHERE notes='BASIS_UNKNOWN'"
    )).scalar()
    print(f"overrides applied: {n_lots} lots, {n_sales} sale rows; "
          f"still unresolved: {unresolved}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    db = SessionLocal()
    try:
        rebuild(db, args.dry_run)
    finally:
        db.close()
