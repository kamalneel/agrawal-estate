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
     different dates, and for the Robinhood accounts they lagged the rh_csv
     gap-filler (card through 2026-06-26 vs rh_csv through 2026-07-08).
     Clearing whole accounts would destroy fresher data.

  3. **An export is not contiguous within its own date range.** After the
     2026-08-26 reconnect, Monarch's July file carried the Robinhood card on
     the 26th-31st and nothing from the 1st-25th. Superseding the whole span
     would have deleted 44 real rh_csv rows for Jul 1-8 in exchange for
     nothing, widening a 17-day hole to 25 days.

  4. **Accounts absent from the export** are left completely untouched.

Net rule: for each account in the CSV, delete existing rows ONLY on the dates
that account actually appears on in the CSV, then insert every CSV row. Days
the export skips keep whatever is already there.

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
from sqlalchemy import bindparam, text  # noqa: E402

# Historical DB account name -> name used by the current export. Extend this
# whenever Monarch renames an account; without an entry the account silently
# double-counts under both names.
ACCOUNT_ALIASES = {
    "Robinhood Credit Card (...8154)": "Robinhood Credit Card **8154 (...8154)",
    "Robinhood Spending (...2623)": "Spending (...dabe)",
    # 2026-08-26: after Neel reconnected the Robinhood accounts, Monarch began
    # reporting the two cash accounts under fresh names. rh_csv had been their
    # only source until now, so these map the gap-filler's names onto
    # Monarch's. Identity confirmed by content, not by the identifier:
    # Checking carries the same brokerage transfers, card payments and
    # outgoing wires; Savings shows the same to/from-brokerage and
    # "To Joint Checking With Jaya" movements.
    "Robinhood Checking (Joint)": "Checking (...8935)",
    "Robinhood Savings": "Savings (...7358)",
    # NOT aliased: "Spending (...dabe)" (Monarch, through 2026-06-06). Three
    # old names map onto two new ones, so which — if either — it became is
    # ambiguous. Left alone rather than guessed; it simply stops there.
}


#: Since the 2026-08-26 reconnect, Monarch lists every brokerage transfer in
#: the Robinhood cash accounts TWICE in the same export: once with the terse
#: statement text Robinhood's own feed uses, and once with Monarch's long
#: form ("Transfer from Robinhood Brokerage account ending in 1773 of
#: $5000.00"). Same account, date and amount; different text, so different
#: hashes, so both would import. Seen on 2026-07-04/06/07/31 and
#: 2026-08-08/12/22. The terse one is dropped when a partner exists.
#: Deliberately narrow — three identical Amazon rows on one day are three
#: real orders and must survive.
DUPLICATE_TERSE_STATEMENTS = {"from brokerage", "to brokerage"}
DUPLICATE_ACCOUNTS_PREFIXES = ("Checking (", "Savings (")


def collapse_monarch_duplicates(raw: list[dict]) -> tuple[list[dict], list[str]]:
    """Drop the terse twin of a double-listed Robinhood cash-account transfer.
    Returns (rows kept, human-readable notes on what was dropped)."""
    by_key: dict[tuple, list[int]] = defaultdict(list)
    for i, r in enumerate(raw):
        acct = (r.get("Account") or "").strip()
        if acct.startswith(DUPLICATE_ACCOUNTS_PREFIXES):
            by_key[(r.get("Date"), acct, r.get("Amount"))].append(i)
    drop: set[int] = set()
    notes = []
    for key, idxs in by_key.items():
        if len(idxs) < 2:
            continue
        terse = [i for i in idxs
                 if (raw[i].get("Original Statement") or "").strip().lower()
                 in DUPLICATE_TERSE_STATEMENTS]
        if terse and len(terse) < len(idxs):
            for i in terse:
                drop.add(i)
                notes.append(f"{key[0]} {key[1][:20]} {key[2]:>10}  dropped "
                             f"'{raw[i].get('Original Statement')}' (twin kept)")
    return [r for i, r in enumerate(raw) if i not in drop], notes


def parse_rows(path: Path) -> list[dict]:
    """Read the CSV and attach the record_hash used by MonarchParser."""
    with open(path, encoding="utf-8-sig") as f:
        raw = list(csv.DictReader(f))

    raw, dup_notes = collapse_monarch_duplicates(raw)
    if dup_notes:
        print("\nDOUBLE-LISTED TRANSFERS collapsed (Monarch lists these twice):")
        for n in dup_notes:
            print(f"  {n}")

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

    # Per-account set of dates the export actually covers. A max date alone
    # is not enough — see the supersede block below.
    covered_dates: dict[str, set] = {}
    for r in rows:
        covered_dates.setdefault(r["account"], set()).add(r["transaction_date"])
    coverage = {a: max(d) for a, d in covered_dates.items()}

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

        # --- 2. Supersede, PER ACCOUNT PER DAY --------------------------------
        # Delete only on dates the export actually carries rows for that
        # account. An export is NOT contiguous within its date range: after
        # Neel reconnected his accounts on 2026-08-26, Monarch's July file
        # covered the Robinhood card on the 26th-31st only, with nothing from
        # the 1st-25th. Clearing the whole [since, max] window would have
        # deleted 44 real rh_csv rows for Jul 1-8 and replaced them with
        # nothing, widening a 17-day hole to 25 days.
        #
        # Trade-off: if Monarch DELETES a transaction and it was the only one
        # that day, the stale row survives here. That is much the lesser evil
        # against silently destroying days the export simply doesn't cover.
        print("\nSUPERSEDE (per account, only on dates the export covers):")
        total_deleted = 0
        for acct in sorted(covered_dates):
            dates = sorted(covered_dates[acct])
            stats = db.execute(text("""
                SELECT COUNT(*), COALESCE(SUM(amount), 0)
                FROM spending_transactions
                WHERE account = :a AND transaction_date IN :dates
            """).bindparams(bindparam("dates", expanding=True)),
                {"a": acct, "dates": dates}).one()

            # Rows inside the export's span that it does NOT cover, and so are
            # deliberately left alone — the holes worth seeing.
            untouched = db.execute(text("""
                SELECT COUNT(*) FROM spending_transactions
                WHERE account = :a AND transaction_date BETWEEN :lo AND :hi
                  AND transaction_date NOT IN :dates
            """).bindparams(bindparam("dates", expanding=True)),
                {"a": acct, "lo": dates[0], "hi": dates[-1], "dates": dates}).scalar()

            note = f"   [{untouched} kept in gaps]" if untouched else ""
            print(f"  {acct[:38]:38s} {dates[0]}..{dates[-1]} "
                  f"({len(dates):3d}d)  del={stats[0]:4d} "
                  f"({float(stats[1]):>11,.2f}){note}")
            total_deleted += stats[0]

            db.execute(text("""
                DELETE FROM spending_transactions
                WHERE account = :a AND transaction_date IN :dates
            """).bindparams(bindparam("dates", expanding=True)),
                {"a": acct, "dates": dates})

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
