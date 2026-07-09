"""Import Robinhood-native spending CSVs into spending_transactions.

Three formats, auto-detected by header (docs/SPENDING-PAGE-SPEC.md):
  - Credit Card:  Date,Time,Cardholder,Amount,Points,Balance,Status,Type,Merchant,Description
  - Savings/Checking: Date,Description,Amount

Rules:
  - Card rows: CSV sign is positive=charge, negative=credit → stored
    Monarch-style (spend negative). Declined rows skipped. Payments →
    'Credit Card Payment' (an EXCLUDED category, so they never count as
    spend). Purchases/refunds are categorized by a merchant→category map
    LEARNED from the existing Monarch-categorized history (case-insensitive
    exact merchant match, majority vote); unknown merchants → NULL
    (renders as Uncategorized).
  - Per-account cutoff: only rows dated after the newest existing
    spending_transactions row for that account are imported — Monarch
    already covers the earlier span; no fuzzy cross-source dedup needed.
  - Savings/Checking rows keep their sign (already negative=out) and get
    description-keyword categories (transfers/interest/payroll → excluded
    categories; wires & cash delivery left uncategorized = real spend).
  - record_hash includes an instance counter so genuinely identical rows
    (two same-price coffees same day) survive while re-imports dedupe.

Usage: python scripts/import_rh_spending_csv.py <csv...> [--save]
"""
import csv
import hashlib
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal  # noqa: E402
from sqlalchemy import text  # noqa: E402

CARD_ACCOUNT = "Robinhood Credit Card (...8154)"  # matches Monarch's name
SAVINGS_ACCOUNT = "Robinhood Savings"
CHECKING_ACCOUNT = "Robinhood Checking (Joint)"

DESC_CATEGORIES = [
    ("interest payment", "Interest"),
    ("internal transfer", "Transfer"),
    ("inter-entity transfer", "Transfer"),
    ("acctverify", "Transfer"),
    ("robinhood credits", "Transfer"),
    ("payroll", "Paychecks"),
    ("citi card", "Credit Card Payment"),
    ("chase credit", "Credit Card Payment"),
]

# Trip tags and one-offs must never transfer to new purchases via the
# merchant map (a cafe visited on the Europe trip isn't "Europe Trip 2025"
# forever).
NON_TRANSFERABLE_CATEGORIES = (
    "Europe Trip 2025", "India Trip 2024", "Bali trip",
    "AdamX Work Trip - Vegas", "ANNUAL EXPENSES", "ONE TIME",
    "Travel & Vacation",
)

# Unambiguous merchants Monarch history doesn't know under these names.
SEED_CATEGORIES = {
    "anthem blue individual": "Insurance",
    "city of palo alto": "Gas & Electric",
    "emirates airlines": "Travel & Vacation",
    "china airlines": "Travel & Vacation",
    "air india": "Travel & Vacation",
    "expedia": "Travel & Vacation",
    "worldmark the club": "Travel & Vacation",
}


def _norm(m: str) -> str:
    """Normalize merchant for matching: lowercase, drop punctuation and
    corporate suffixes/articles ('Blue Bottle Coffee, Inc' == 'Blue Bottle
    Coffee', 'the YMCA' == 'YMCA')."""
    s = "".join(c if c.isalnum() or c == " " else " " for c in m.lower())
    words = [w for w in s.split() if w not in ("the", "inc", "llc", "co", "corp")]
    return " ".join(words)


def merchant_category_map(db):
    rows = db.execute(text("""
        SELECT merchant, category, COUNT(*) AS n
        FROM spending_transactions
        WHERE merchant IS NOT NULL AND category IS NOT NULL
          AND tags IS DISTINCT FROM 'rh_csv'
          AND category NOT IN :nt
        GROUP BY 1, 2
    """), {"nt": NON_TRANSFERABLE_CATEGORIES}).fetchall()
    best: dict[str, tuple[str, int]] = {}
    for r in rows:
        m = _norm(r.merchant)
        if m and (m not in best or r.n > best[m][1]):
            best[m] = (r.category, r.n)
    out = {m: c for m, (c, _) in best.items()}
    out.update(SEED_CATEGORIES)
    return out


def account_cutoff(db, account: str):
    return db.execute(text(
        "SELECT MAX(transaction_date) FROM spending_transactions WHERE account = :a"
    ), {"a": account}).scalar()


def parse_card(path: Path, cat_map):
    out = []
    for row in csv.DictReader(open(path, encoding="utf-8-sig")):
        if row["Status"] == "Declined":
            continue
        amt = -float(row["Amount"])  # charge → negative spend
        rtype = row["Type"]
        merchant = (row.get("Merchant") or rtype).strip()
        if rtype == "Payment":
            category = "Credit Card Payment"
        else:
            category = cat_map.get(_norm(merchant))
        owner = (row.get("Cardholder") or "").split()[0] or None
        out.append({
            "date": row["Date"], "merchant": merchant, "category": category,
            "account": CARD_ACCOUNT, "amount": amt, "owner": owner,
            "notes": f"{rtype}/{row['Status']}",
            "statement": row.get("Description") or None,
        })
    return out


def parse_simple(path: Path, account: str):
    out = []
    for row in csv.DictReader(open(path, encoding="utf-8-sig")):
        desc = (row.get("Description") or "").strip()
        low = desc.lower()
        category = next((c for k, c in DESC_CATEGORIES if k in low), None)
        out.append({
            "date": row["Date"], "merchant": desc, "category": category,
            "account": account, "amount": float(row["Amount"]), "owner": None,
            "notes": None, "statement": desc,
        })
    return out


def detect(path: Path):
    headers = set(next(csv.reader(open(path, encoding="utf-8-sig"))))
    if {"Cardholder", "Merchant", "Status"}.issubset(headers):
        return "card"
    if {"Date", "Description", "Amount"}.issubset(headers):
        return "savings" if "saving" in path.name.lower() else "checking"
    raise SystemExit(f"unrecognized CSV format: {path}")


def main():
    save = "--save" in sys.argv
    paths = [Path(a) for a in sys.argv[1:] if not a.startswith("--")]
    if not paths:
        raise SystemExit(__doc__)

    db = SessionLocal()
    cat_map = merchant_category_map(db)
    print(f"merchant→category map: {len(cat_map)} merchants learned from Monarch history")

    records = []
    for p in paths:
        kind = detect(p)
        if kind == "card":
            rows = parse_card(p, cat_map)
        else:
            rows = parse_simple(p, SAVINGS_ACCOUNT if kind == "savings" else CHECKING_ACCOUNT)
        cutoff = account_cutoff(db, rows[0]["account"]) if rows else None
        kept = [r for r in rows
                if cutoff is None or datetime.strptime(r["date"], "%Y-%m-%d").date() > cutoff]
        print(f"{p.name}: {kind}, {len(rows)} rows, cutoff {cutoff} → {len(kept)} to import")
        records.extend(kept)

    # instance numbering for identical rows + dedup hash
    counter: dict[str, int] = defaultdict(int)
    inserted = skipped = uncategorized = 0
    for r in records:
        key = f"rhcsv|{r['account']}|{r['date']}|{r['merchant']}|{r['amount']:.2f}"
        counter[key] += 1
        r["hash"] = hashlib.sha256(f"{key}|{counter[key]}".encode()).hexdigest()
        if r["category"] is None:
            uncategorized += 1

    for r in records:
        exists = db.execute(text(
            "SELECT 1 FROM spending_transactions WHERE record_hash = :h"), {"h": r["hash"]}).first()
        if exists:
            skipped += 1
            continue
        if save:
            db.execute(text("""
                INSERT INTO spending_transactions
                    (transaction_date, merchant, category, account,
                     original_statement, notes, amount, tags, owner,
                     record_hash, created_at, updated_at)
                VALUES (:date, :merchant, :category, :account, :statement,
                        :notes, :amount, 'rh_csv', :owner, :hash, NOW(), NOW())
            """), r)
        inserted += 1

    if save:
        db.commit()
    total_spend = sum(r["amount"] for r in records if r["amount"] < 0)
    print(f"{'SAVED' if save else 'PREVIEW'}: {inserted} inserted, {skipped} already present, "
          f"{uncategorized} uncategorized, spend total {total_spend:,.2f}")


if __name__ == "__main__":
    main()
