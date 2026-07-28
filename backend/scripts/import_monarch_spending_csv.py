"""Import a Monarch Money CSV export into spending_transactions.

Monarch is the categorization authority (docs/SPENDING-PAGE-SPEC.md). A fresh
export supersedes whatever already covers the same ground — earlier Monarch
exports and the rh_csv gap-filler alike. This script implements that supersede
rule safely.

Three things a naive import gets wrong:

  1. **Account renames.** Monarch renames accounts between exports
     ("Robinhood Credit Card (...8154)" -> "Robinhood Credit Card **8154
     (...8154)", "Robinhood Spending (...2623)" -> "Spending (...dabe)"). The
     record_hash includes the account name, so a rename makes every row look
     new and the whole account double-counts. ACCOUNT_ALIASES maps historical
     names onto the current export's name; DB rows are renamed in place before
     the supersede window is cleared.

  2. **Monarch is not uniformly fresher.** Its per-account feeds stop at
     different dates, and for the Robinhood accounts they lag the rh_csv
     gap-filler (card through 2026-06-26 vs rh_csv through 2026-07-08).
     Clearing whole accounts would destroy fresher data. The supersede window
     is therefore bounded per account at that account's own max date in the
     export — rows after it survive.

  3. **Accounts absent from the export.** Monarch does not track Robinhood
     Checking/Savings at all. Accounts the export never mentions are left
     completely untouched.

Net rule: for each account in the CSV, delete existing rows in
[--since, max(CSV date for that account)], then insert every CSV row.

Usage:
    python scripts/import_monarch_spending_csv.py <csv> [--since YYYY-MM-DD] [--save]

Dry-run by default; --save commits. --since defaults to the CSV's own min date.
"""
import argparse
import csv
import hashlib
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal  # noqa: E402
from sqlalchemy import text  # noqa: E402

# Historical DB account name -> name used by the current export. Extend this
# whenever Monarch renames an account; without an entry the account silently
# double-counts under both names.
ACCOUNT_ALIASES = {
    "Robinhood Credit Card (...8154)": "Robinhood Credit Card **8154 (...8154)",
    "Robinhood Spending (...2623)": "Spending (...dabe)",
}


def parse_rows(path: Path) -> list[dict]:
    """Read the CSV and attach the record_hash used by MonarchParser."""
    with open(path, encoding="utf-8-sig") as f:
        raw = list(csv.DictReader(f))

    instance: dict[str, int] = defaultdict(int)
    rows = []
    for line_no, r in enumerate(raw, start=2):
        date_str = (r.get("Date") or "").strip()
        amount_str = (r.get("Amount") or "").strip()
        if not date_str or not amount_str:
            print(f"  ! row {line_no}: missing date/amount, skipped")
            continue

        merchant = (r.get("Merchant") or "").strip()
        account = (r.get("Account") or "").strip()
        original = (r.get("Original Statement") or "").strip()
        amount = Decimal(amount_str.replace("$", "").replace(",", ""))

        # Same key + hash scheme as app/ingestion/parsers/monarch.py so that
        # re-running this script is idempotent.
        key = (f"{r.get('Date','')}|{r.get('Merchant','')}|{r.get('Account','')}"
               f"|{r.get('Amount','')}|{r.get('Original Statement','')}")
        inst = instance[key]
        instance[key] += 1

        digest = hashlib.sha256(
            f"{date_str}|{merchant}|{account}|{amount:.2f}|{original}"
            f"|instance_{inst}".encode()
        ).hexdigest()

        rows.append({
            "transaction_date": datetime.strptime(date_str, "%Y-%m-%d").date(),
            "merchant": merchant or None,
            "category": (r.get("Category") or "").strip() or None,
            "account": account or None,
            "original_statement": original or None,
            "notes": (r.get("Notes") or "").strip() or None,
            "amount": amount,
            "tags": (r.get("Tags") or "").strip() or None,
            "owner": (r.get("Owner") or "").strip() or None,
            "record_hash": digest,
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", type=Path)
    ap.add_argument("--since", help="Supersede window start (default: CSV min date)")
    ap.add_argument("--save", action="store_true", help="Commit (default: dry run)")
    args = ap.parse_args()

    rows = parse_rows(args.csv_path)
    if not rows:
        print("No rows parsed.")
        return 1

    dates = [r["transaction_date"] for r in rows]
    since = (datetime.strptime(args.since, "%Y-%m-%d").date()
             if args.since else min(dates))

    # Per-account coverage end — the supersede window's upper bound.
    coverage: dict[str, object] = {}
    for r in rows:
        acct = r["account"]
        if acct not in coverage or r["transaction_date"] > coverage[acct]:
            coverage[acct] = r["transaction_date"]

    print(f"\nCSV: {args.csv_path.name}")
    print(f"  {len(rows)} rows, {min(dates)} -> {max(dates)}")
    print(f"  supersede window starts {since}\n")

    db = SessionLocal()
    try:
        # --- 1. Reconcile account renames ------------------------------------
        for old, new in ACCOUNT_ALIASES.items():
            if new not in coverage:
                continue  # this export doesn't include that account
            n = db.execute(
                text("SELECT COUNT(*) FROM spending_transactions WHERE account = :o"),
                {"o": old},
            ).scalar()
            if n:
                print(f"RENAME  {n:5d}  {old}\n              -> {new}")
                db.execute(
                    text("UPDATE spending_transactions SET account = :n WHERE account = :o"),
                    {"o": old, "n": new},
                )

        # --- 2. Supersede: clear each covered account's window ----------------
        print("\nSUPERSEDE (delete existing rows inside each account's coverage):")
        total_deleted = 0
        for acct in sorted(coverage):
            through = coverage[acct]
            stats = db.execute(text("""
                SELECT COUNT(*), COALESCE(SUM(amount), 0)
                FROM spending_transactions
                WHERE account = :a AND transaction_date BETWEEN :s AND :e
            """), {"a": acct, "s": since, "e": through}).one()

            kept = db.execute(text("""
                SELECT COUNT(*), MIN(transaction_date), MAX(transaction_date)
                FROM spending_transactions
                WHERE account = :a AND transaction_date > :e
            """), {"a": acct, "e": through}).one()

            note = ""
            if kept[0]:
                note = f"   [keeps {kept[0]} fresher rows {kept[1]}..{kept[2]}]"
            print(f"  {acct[:40]:40s} <= {through}  del={stats[0]:5d} "
                  f"({float(stats[1]):>12,.2f}){note}")
            total_deleted += stats[0]

            db.execute(text("""
                DELETE FROM spending_transactions
                WHERE account = :a AND transaction_date BETWEEN :s AND :e
            """), {"a": acct, "s": since, "e": through})

        # --- 3. Insert ---------------------------------------------------------
        inserted = skipped = 0
        for r in rows:
            exists = db.execute(
                text("SELECT 1 FROM spending_transactions WHERE record_hash = :h"),
                {"h": r["record_hash"]},
            ).scalar()
            if exists:
                skipped += 1
                continue
            db.execute(text("""
                INSERT INTO spending_transactions
                    (transaction_date, merchant, category, account,
                     original_statement, notes, amount, tags, owner, record_hash,
                     created_at, updated_at)
                VALUES
                    (:transaction_date, :merchant, :category, :account,
                     :original_statement, :notes, :amount, :tags, :owner,
                     :record_hash, NOW(), NOW())
            """), r)
            inserted += 1

        print(f"\nDeleted {total_deleted}, inserted {inserted}, "
              f"skipped {skipped} (hash already present)")

        if args.save:
            db.commit()
            print("COMMITTED")
        else:
            db.rollback()
            print("DRY RUN — nothing written (pass --save to commit)")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
