"""Import Robinhood activity CSVs (the six per-account exports).

These are the ONLY source of cash movements (XENT / XENT_CC / ACH / RTP).
The trading MCP returns orders, positions and quotes — a transfer between
your own accounts is not a trade, so nothing in the MCP surface reports it.
That is why option rows stay current to yesterday via sync while
CASH_MOVEMENT silently goes stale until one of these files is imported.
See docs/SPENDING-PAGE-SPEC.md → Known data notes.

Uses the standard pipeline (RobinhoodParser -> save_records), so the hybrid
per-transaction-type crossover dedup applies unchanged — re-importing an
overlapping file is safe.

Usage: python scripts/import_rh_activity_csvs.py <dir-or-csv...> [--save]

Dry-run by default: parses, saves inside a transaction, reports, rolls back.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.ingestion.parsers.robinhood import RobinhoodParser  # noqa: E402
from app.ingestion.services import save_records  # noqa: E402

CASH_TYPES = ("XENT_CC", "XENT", "CASH_MOVEMENT", "RTP", "ACH")


def cash_freshness(db) -> dict:
    return {
        r[0]: r[1]
        for r in db.execute(text("""
            SELECT account_id, MAX(transaction_date)
            FROM investment_transactions
            WHERE transaction_type IN :types
            GROUP BY 1
        """), {"types": CASH_TYPES}).fetchall()
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    files: list[Path] = []
    for p in args.paths:
        files.extend(sorted(p.glob("*.csv")) if p.is_dir() else [p])
    if not files:
        print("No CSV files found.")
        return 1

    parser = RobinhoodParser()
    db = SessionLocal()
    try:
        before = cash_freshness(db)
        totals = {"created": 0, "skipped": 0, "updated": 0}

        for f in files:
            if not parser.can_parse(f):
                print(f"  SKIP  {f.name}: not a Robinhood export")
                continue
            account_id = parser._infer_account_from_filename(f)
            if account_id == "robinhood_default":
                # Refuse rather than dump rows into a catch-all account.
                print(f"  ERROR {f.name}: account not inferable from filename — "
                      f"rename it (e.g. 'Neel Investment.csv') and re-run")
                continue

            result = parser.parse(f)
            if not result.success:
                print(f"  ERROR {f.name}: {result.errors}")
                continue

            saved = save_records(db, result.records)
            for k in totals:
                totals[k] += saved.get(k, 0)
            print(f"  {f.name:24s} -> {account_id:16s} "
                  f"parsed={len(result.records):5d} created={saved['created']:5d} "
                  f"skipped={saved['skipped']:5d}")

        after = cash_freshness(db)
        print(f"\nTotals: created={totals['created']} skipped={totals['skipped']}")
        print("\nCash-movement freshness:")
        for acct in sorted(set(before) | set(after)):
            b, a = before.get(acct), after.get(acct)
            arrow = f"{b} -> {a}" if b != a else f"{a} (unchanged)"
            print(f"  {acct:22s} {arrow}")

        if args.save:
            db.commit()
            print("\nCOMMITTED")
        else:
            db.rollback()
            print("\nDRY RUN — rolled back (pass --save to commit)")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
