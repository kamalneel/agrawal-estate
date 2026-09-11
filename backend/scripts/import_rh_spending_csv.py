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
  - Per-account cutoff: rows dated after the newest existing
    spending_transactions row for that account are imported — Monarch
    already covers the earlier span.
  - HOLE FILL (2026-09-10): rows that fall inside a hole in the existing
    coverage are imported too. A hole is a silence longer than HOLE_MIN_DAYS
    between two existing transaction days for that account — the shape a
    dropped-and-reconnected feed leaves (Monarch's 2026-08-26 reconnect left
    the card empty Jul 9-25). Inside a hole a row is skipped if the DB
    already has a row for that account with the same amount within
    +/- FUZZY_DAYS (Monarch may date a purchase on its posting day), so a
    partially covered hole does not double-count. Outside holes and before
    the cutoff nothing is imported: Monarch is the categorization authority
    there, and rh_csv rows would only duplicate it under a second hash.
  - Card rows with Status 'Pending' are skipped; they arrive posted in the
    next Monarch export.
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

# MUST match the name Monarch currently exports for this account, or the
# per-account cutoff below finds no coverage and the account splits in two
# under the old and new names. Monarch renamed this 2026-07-25
# ("Robinhood Credit Card (...8154)" -> the value below); keep this in sync
# with ACCOUNT_ALIASES in import_monarch_spending_csv.py.
CARD_ACCOUNT = "Robinhood Credit Card **8154 (...8154)"
# Since the 2026-08-26 reconnect Monarch tracks these two under the names
# below (the old rh_csv-only names "Robinhood Savings" / "Robinhood Checking
# (Joint)" were renamed in the DB via ACCOUNT_ALIASES). Using any other name
# here splits the account in two and the cutoff finds no coverage.
SAVINGS_ACCOUNT = "Savings (...7358)"
CHECKING_ACCOUNT = "Checking (...8935)"

#: Silence between two existing transaction days that counts as a hole.
HOLE_MIN_DAYS = 12
#: Inside a hole, a same-amount row this many days either side is the same
#: transaction seen through Monarch on a different (posting) date.
FUZZY_DAYS = 3

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
    # Neel, 2026-07-09: wires to Eric Chang = monthly rent ($9K/mo from
    # Jun 1 + one month deposit); Gifthealth = Neel's medication; cash
    # deliveries (incl. fee/tip rows) pay the home cleaners (~$250/mo).
    "outgoing wire transfer to eric chang": "Rent",
    "gifthealth": "Medical",
    # Unambiguous chains first seen in the July 2026 hole fill.
    "whole foods market": "Groceries",
    "in n out san carlos": "Restaurants & Bars",
    "mendocinofarms": "Restaurants & Bars",
    "marufuku ramen palo alto": "Restaurants & Bars",
    "palmetto superfood": "Restaurants & Bars",
    "roost roast": "Coffee Shops",
    "woof gang bakery grooming palo alto": "Pets",
    "cloud 9 spa burlingame": "Personal",
    "cash delivery": "Home Improvement",
    "cash delivery fee": "Home Improvement",
    "cash delivery tip": "Home Improvement",
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


def account_holes(db, account: str):
    """[(first missing day, last missing day)] — every silence longer than
    HOLE_MIN_DAYS between existing transaction days for this account."""
    from datetime import timedelta
    days = [r[0] for r in db.execute(text("""
        SELECT DISTINCT transaction_date FROM spending_transactions
        WHERE account = :a ORDER BY 1"""), {"a": account}).fetchall()]
    holes = []
    for a, b in zip(days, days[1:]):
        if (b - a).days > HOLE_MIN_DAYS:
            holes.append((a + timedelta(days=1), b - timedelta(days=1)))
    return holes


def fuzzy_exists(db, account: str, day, amount: float) -> bool:
    return db.execute(text("""
        SELECT 1 FROM spending_transactions
        WHERE account = :a AND amount = :amt
          AND transaction_date BETWEEN :d - :f AND :d + :f
        LIMIT 1"""), {"a": account, "amt": round(amount, 2), "d": day,
                      "f": FUZZY_DAYS}).first() is not None


def parse_card(path: Path, cat_map):
    out = []
    for row in csv.DictReader(open(path, encoding="utf-8-sig")):
        if row["Status"] in ("Declined", "Pending"):
            continue
        amt = -float(row["Amount"])  # charge → negative spend
        rtype = row["Type"]
        merchant = (row.get("Merchant") or rtype).strip()
        if rtype == "Payment":
            category = "Credit Card Payment"
        else:
            # A refund carries "Refund: <merchant>"; look the merchant up so
            # it lands in the category it nets against.
            lookup = merchant[len("refund: "):] if merchant.lower().startswith("refund: ") else merchant
            category = cat_map.get(_norm(lookup))
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
        name = path.name.lower()
        if "saving" in name:
            return "savings"
        if "checking" in name:
            return "checking"
        # Robinhood downloads are named by UUID; tell the two cash accounts
        # apart by content. Each account names the OTHER in its internal
        # transfers: Checking says "Joint Savings with Jaya", Savings says
        # "Joint Checking with Jaya". (Both pay wires and cards, so those
        # are no use as a tell — the Savings file has Eric Chang wires too.)
        text_ = open(path, encoding="utf-8-sig").read().lower()
        if "joint savings" in text_ and "joint checking" not in text_:
            return "checking"
        if "joint checking" in text_ and "joint savings" not in text_:
            return "savings"
        raise SystemExit(f"cannot tell checking from savings: {path} — "
                         f"rename the file to include 'checking' or 'savings'")
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
        if not rows:
            print(f"{p.name}: {kind}, no rows")
            continue
        account = rows[0]["account"]
        cutoff = account_cutoff(db, account)
        holes = account_holes(db, account)
        kept, after, in_hole, fuzzy_dups = [], 0, 0, 0
        for r in rows:
            day = datetime.strptime(r["date"], "%Y-%m-%d").date()
            if cutoff is None or day > cutoff:
                kept.append(r)
                after += 1
            elif any(lo <= day <= hi for lo, hi in holes):
                if fuzzy_exists(db, account, day, r["amount"]):
                    fuzzy_dups += 1
                    continue
                kept.append(r)
                in_hole += 1
        print(f"{p.name}: {kind} -> {account}")
        print(f"   {len(rows)} rows in file; existing coverage through {cutoff}")
        for lo, hi in holes:
            n = sum(1 for r in kept if lo <= datetime.strptime(r['date'], '%Y-%m-%d').date() <= hi)
            print(f"   hole {lo}..{hi}: {n} rows fill it")
        print(f"   -> {after} after cutoff, {in_hole} inside holes, "
              f"{fuzzy_dups} skipped as already present (same amount within "
              f"±{FUZZY_DAYS} days), {len(rows) - len(kept) - fuzzy_dups} "
              f"already covered by Monarch")
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
