"""Import income rows from Robinhood monthly PDF statements.

WHY THIS EXISTS
---------------
Three income streams reach this system through no automated path at all:

  - dividends (CDIV/DIV/DIVNRA)
  - interest (INT, and GDBP "Gold Deposit Boost")
  - stock lending (SLIP)

The Robinhood MCP feed exposes none of them — scripts/robinhood_mcp_bridge.py
says so in its own header — so options stay current to the day while these
three silently flatline at whatever the last activity-CSV import reached. On
2026-09-06 options ran through 09/04 while dividends stopped 07/21, interest
06/30 and lending 07/08, and August read $0 for all three. That is a
freshness artifact, not a real zero.

The monthly statement carries them, and unlike the activity CSV it is always
available. app/ingestion/parsers/robinhood_pdf.py deliberately extracts
nothing ("statements provide NO VALUE"); that judgement was made when the
CSV was the assumed refresh path. It holds for holdings and portfolio value.
It does not hold for these three streams.

CASH MOVEMENTS (added 2026-09-06)
---------------------------------
Brokerage cash in/out (XENT, XENT_CC, XENT_CM, ACH, RTP -> CASH_MOVEMENT) is
the Spending page's "how much" side, and it too had no automated path: the
MCP feed never carries it and the activity CSV had last landed in early
July, so outflows silently stopped at 07/20. The statement rows have no
printed sign; it is read from the Debit/Credit column position and
cross-checked against the description (see CASH_*_HINTS). Disagreement
aborts. The printed "Total Funds Paid and Received" cannot validate these
rows (it sums the whole activity table, including rows this regex does not
parse), so the dry run also prints whether each brokerage->Checking/Savings
transfer appears on the receiving side in Monarch.

WHAT THIS DELIBERATELY DOES *NOT* IMPORT
----------------------------------------
Options and equity rows, though the statement is full of them. They already
arrive via the MCP sync, and the bridge warns that its synthesized amounts
are GROSS while the statement's are NET of reg fees — so the two will not
dedup against each other and every STO/BTC would double-count. Options are
the largest income line in the app; corrupting it to backfill $578 of
dividends would be a bad trade. Same reasoning for BUY/SELL/OEXP/OASGN.

MARGIN INTEREST
---------------
MINT ("Aggregated Margin Rate") is interest CHARGED, and it lands in the
interest income bucket as a NEGATIVE number — Neel, 2026-09-06: "margin
interest is negative income, fold it into the interest tab".

It is stored under its own transaction_type, MARGIN_INTEREST, rather than as
a negative INTEREST row, for two reasons. The deduper takes its crossover
per (account, transaction_type): reusing INTEREST would put the 07/14 and
07/20 margin charges behind the 07/31 interest payments already in the
ledger, and they would be silently skipped as "already imported". And the
ledger stays honest — interest earned and interest charged remain separable
for tax work. The folding happens where it is displayed: MARGIN_INTEREST is
listed alongside INTEREST in unified_service._TXN_SOURCE_CASE and in the
income/db_queries.py predicates, which must agree.

VALIDATION
----------
Every statement prints its own "Income and Expense Summary" per account. The
extracted rows are summed and checked against it before anything is written,
so a regex that silently misses a row fails loudly instead of quietly
understating income.

Usage:
    python scripts/import_robinhood_statement_pdf.py <dir-or-pdf>... [--save]

Dry-run by default; --save commits.
"""
import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pdfplumber  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.ingestion.parsers.base import ParsedRecord, RecordType  # noqa: E402
from app.ingestion.services import save_investment_transactions_hybrid  # noqa: E402

#: Robinhood statement account number -> this system's account_id.
#: Robinhood splits one logical brokerage across several internal account
#: numbers (Neel's "Individual" appears four times, Jaya's three), all of
#: which are the same account to us. Verified 2026-09-06 against rows already
#: in the DB: the 07/08 SLIP pair landed in neel_roth_ira / jaya_ira and the
#: 07/21 MU dividends in jaya_roth_ira / jaya_ira, matching the account
#: numbers below. An unmapped number aborts the run rather than guessing.
ACCOUNT_MAP = {
    # Neel — Individual
    "648299006": "neel_brokerage",
    "170317739": "neel_brokerage",
    "593591191": "neel_brokerage",
    "925668238": "neel_brokerage",
    # Neel — retirement
    "439569591": "neel_retirement",   # Traditional IRA
    "514429901": "neel_roth_ira",     # Roth IRA
    # Jaya — Individual
    "701552176": "jaya_brokerage",
    "407859297": "jaya_brokerage",
    "560126427": "jaya_brokerage",
    # Jaya — retirement
    "534052659": "jaya_ira",          # Traditional IRA
    "704155779": "jaya_roth_ira",     # Roth IRA
}

#: Statement trans code -> our transaction_type. Mirrors the activity-CSV
#: parser (app/ingestion/parsers/robinhood.py) exactly, so a row imported
#: from a statement is indistinguishable from the same row imported from the
#: CSV and the hybrid deduper treats them as one.
INCOME_TYPES = {
    "CDIV": "DIVIDEND",
    "DIV": "DIVIDEND",
    "DIVNRA": "DIVIDEND",
    "INT": "INTEREST",
    "GDBP": "INTEREST",
    "SLIP": "SLIP",
}

#: Interest CHARGED. Imported as negative income under its own type, and
#: validated separately — it is not part of the statement's "Interest
#: Earned" line. See module docstring.
MARGIN_TYPES = {"MINT": "MARGIN_INTEREST"}

#: Cash leaving or entering the brokerage: the Spending page's "how much"
#: side (docs/SPENDING-PAGE-SPEC.md). Added 2026-09-06: these rows had no
#: refresh path at all — the MCP feed does not carry them and the activity
#: CSV had last landed in early July, so brokerage outflows silently stopped
#: on 07/20 while the page kept reporting them as current. Same dedup
#: argument as margin: the MCP never emits CASH_MOVEMENT, so nothing
#: collides. Codes mirror app/ingestion/parsers/robinhood.py; XENT_CM
#: (brokerage <-> Checking/Savings) is new in 2026 statements.
CASH_TYPES = {
    "XENT": "CASH_MOVEMENT",
    "XENT_CC": "CASH_MOVEMENT",
    "XENT_CM": "CASH_MOVEMENT",
    "ACH": "CASH_MOVEMENT",
    "RTP": "CASH_MOVEMENT",
}

#: A cash row's sign comes from WHICH COLUMN its amount sits in (Debit or
#: Credit) — the text has no sign, so the column is read from word x-positions
#: against the "Debit"/"Credit" header of the activity table. The description
#: is used as an independent cross-check, and a disagreement ABORTS the run:
#: a mis-signed transfer would count a deposit as spending.
CASH_DEBIT_HINTS = ("withdrawal", "reversal", "from brokerage to")
CASH_CREDIT_HINTS = ("deposit", "cash back", "to brokerage")

#: "<description> <SYM> <Margin|Cash> <TYPE> <MM/DD/YYYY> ... $<amount>"
ROW_RE = re.compile(
    r"^(?P<desc>.*?)\s+(?P<sym>[A-Z][A-Z0-9.]{0,5})?\s*"
    r"(?P<acct_type>Margin|Cash)\s+"
    r"(?P<type>[A-Z][A-Z_]{1,10})\s+"
    r"(?P<date>\d\d/\d\d/\d{4})\s+(?P<rest>.*)$")
MONEY_RE = re.compile(r"\$([\d,]+\.\d\d)")
ACCT_RE = re.compile(r"Account #:(\S+)")

#: The per-account "Income and Expense Summary" block, this-period column.
SUMMARY_RE = {
    "DIVIDEND": re.compile(r"^Dividends\s+\$([\d,]+\.\d\d)", re.M),
    "INTEREST": re.compile(r"^Interest Earned\*{0,3}\s+\$([\d,]+\.\d\d)", re.M),
    "SLIP": re.compile(r"^Stock Lending\s+\$([\d,]+\.\d\d)", re.M),
}


def money(s):
    return Decimal(s.replace(",", ""))


def _page_lines_with_positions(page):
    """Rebuild the page's lines from positioned words, so a row's amount can
    be placed in the Debit or Credit column. extract_text() loses that."""
    lines = defaultdict(list)
    for w in page.extract_words():
        lines[round(w["top"])].append(w)
    for top in sorted(lines):
        words = sorted(lines[top], key=lambda w: w["x0"])
        yield " ".join(w["text"] for w in words), words


def parse_cash_rows(path):
    """-> (cash rows, problems). Cash rows carry a signed amount.

    Separate pass from parse_statement: income/margin parsing is validated
    against the statement's printed summary and must not change; cash rows
    need word positions, which that pass does not use.
    """
    rows, problems = [], []
    acct = None
    debit_x = credit_x = None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            m = ACCT_RE.search(text)
            if m:
                acct = m.group(1)
            if "Account Activity" not in text and debit_x is None:
                continue
            for line, words in _page_lines_with_positions(page):
                if line.startswith("Description Symbol Acct Type"):
                    for w in words:
                        if w["text"] == "Debit":
                            debit_x = w["x0"]
                        elif w["text"] == "Credit":
                            credit_x = w["x0"]
                    continue
                r = ROW_RE.match(line)
                if not r or r.group("type") not in CASH_TYPES:
                    continue
                if debit_x is None or credit_x is None:
                    problems.append(f"{path.name}: cash row before any "
                                    f"Debit/Credit header: {line[:60]}")
                    continue
                amounts = [w for w in words
                           if re.fullmatch(r"\$[\d,]+\.\d\d", w["text"])
                           and w["x0"] > debit_x - 5]
                if not amounts:
                    continue
                last = amounts[-1]
                is_credit = (abs(last["x0"] - credit_x)
                             < abs(last["x0"] - debit_x))
                desc = r.group("desc").strip()
                d = desc.lower()
                hint_debit = any(h in d for h in CASH_DEBIT_HINTS)
                hint_credit = any(h in d for h in CASH_CREDIT_HINTS)
                if hint_debit == hint_credit:
                    problems.append(f"{path.name}: no sign hint for cash row "
                                    f"'{desc}' — add it to CASH_*_HINTS")
                elif hint_credit != is_credit:
                    problems.append(f"{path.name}: column says "
                                    f"{'credit' if is_credit else 'debit'} but "
                                    f"description '{desc}' says otherwise")
                amount = money(last["text"][1:])
                rows.append({
                    "file": path.name,
                    "statement_account": acct,
                    "code": r.group("type"),
                    "type": CASH_TYPES[r.group("type")],
                    "date": datetime.strptime(r.group("date"), "%m/%d/%Y").date(),
                    "symbol": "",
                    "amount": amount if is_credit else -amount,
                    "description": desc,
                })
    return rows, problems


def parse_statement(path):
    """-> (income rows, expense rows, {account: {stream: stated total}})."""
    income, expense = [], []
    stated = defaultdict(dict)
    acct = None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            m = ACCT_RE.search(text)
            if m:
                acct = m.group(1)
            if acct and "Income and Expense Summary" in text:
                for stream, rx in SUMMARY_RE.items():
                    hit = rx.search(text)
                    if hit:
                        stated[acct][stream] = money(hit.group(1))
            if "Account Activity" not in text:
                continue
            for line in text.split("\n"):
                r = ROW_RE.match(line.strip())
                if not r:
                    continue
                code = r.group("type")
                if code not in INCOME_TYPES and code not in MARGIN_TYPES:
                    continue
                amounts = MONEY_RE.findall(r.group("rest"))
                if not amounts:
                    continue
                row = {
                    "file": path.name,
                    "statement_account": acct,
                    "code": code,
                    "type": (INCOME_TYPES.get(code) or MARGIN_TYPES[code]),
                    "date": datetime.strptime(r.group("date"), "%m/%d/%Y").date(),
                    "symbol": r.group("sym") or "",
                    "amount": money(amounts[-1]),
                    "description": r.group("desc").strip(),
                }
                if code in MARGIN_TYPES:
                    # Charged, not earned: negate so it reads as the
                    # negative income it is.
                    row["amount"] = -row["amount"]
                    expense.append(row)
                else:
                    income.append(row)
    return income, expense, stated


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", type=Path,
                    help="statement PDFs, or directories of them")
    ap.add_argument("--save", action="store_true", help="Commit (default: dry run)")
    args = ap.parse_args()

    files = []
    for p in args.paths:
        files += sorted(p.glob("*.pdf")) if p.is_dir() else [p]
    if not files:
        print("No PDFs found.")
        return 1

    # Each statement is validated against ITS OWN summary. Merging summaries
    # across files would compare one month's stated total against two months
    # of extracted rows — the same account appears in both the July and the
    # August statement.
    income, expense, cash, bad = [], [], [], 0
    print("\nVALIDATION (extracted vs each statement's own summary):")
    for f in files:
        rows, exp, stated = parse_statement(f)
        income += rows
        expense += exp
        crows, problems = parse_cash_rows(f)
        cash += crows
        for p in problems:
            bad += 1
            print(f"      CASH SIGN PROBLEM: {p}")
        found = defaultdict(Decimal)
        for r in rows:
            found[(r["statement_account"], r["type"])] += r["amount"]
        print(f"  {f.name}  ({len(rows)} income, {len(exp)} margin-interest)")
        for acct in sorted(stated):
            for stream, want in sorted(stated[acct].items()):
                got = found.get((acct, stream), Decimal("0.00"))
                # GDBP is reported by Robinhood outside "Interest Earned"; it
                # is interest to us, so an excess on that line is expected.
                ok = got == want or (stream == "INTEREST" and got >= want)
                if not ok:
                    bad += 1
                if want or got:
                    print(f"      {acct:<11} {stream:<9} statement {want:>9,.2f}"
                          f"  extracted {got:>9,.2f}  "
                          f"{'ok' if ok else 'MISMATCH'}")
    if bad:
        print(f"\nABORT — {bad} stream(s) disagree with the statement. "
              f"The row regex is missing something; fix it before importing.")
        return 1

    unmapped = ({r["statement_account"] for r in income + expense + cash}
                - set(ACCOUNT_MAP))
    if unmapped:
        print(f"\nABORT — unmapped statement accounts: {sorted(unmapped)}")
        print("Add them to ACCOUNT_MAP; guessing would file income to the "
              "wrong person.")
        return 1

    print("\nINCOME ROWS TO IMPORT:")
    for r in sorted(income, key=lambda r: (r["date"], r["statement_account"])):
        print(f"  {r['date']}  {ACCOUNT_MAP[r['statement_account']]:<16} "
              f"{r['type']:<9} {r['symbol']:<6} {r['amount']:>9,.2f}  "
              f"{r['description'][:46]}")
    print(f"  {'':12}{'TOTAL':<16} {'':9} {'':6} "
          f"{sum(r['amount'] for r in income):>9,.2f}")

    if expense:
        print("\nMARGIN INTEREST — imported as negative interest income:")
        for r in sorted(expense, key=lambda r: r["date"]):
            print(f"  {r['date']}  {ACCOUNT_MAP[r['statement_account']]:<16} "
                  f"{r['type']:<15} {r['amount']:>9,.2f}  "
                  f"{r['description'][:40]}")
        print(f"  {'':12}{'TOTAL':<16} {'':15} "
              f"{sum(r['amount'] for r in expense):>9,.2f}")

    db = SessionLocal()
    if cash:
        print("\nCASH MOVEMENTS (sign from Debit/Credit column, checked "
              "against the description):")
        for r in sorted(cash, key=lambda r: (r["date"], r["statement_account"])):
            print(f"  {r['date']}  {ACCOUNT_MAP[r['statement_account']]:<16} "
                  f"{r['code']:<8} {r['amount']:>11,.2f}  {r['description'][:44]}")
        # Cross-source check, informational: every brokerage -> Checking /
        # Savings / Spending transfer should also appear on the receiving
        # side in Monarch. A miss is not an abort (Monarch may simply not
        # have been exported yet) but it is printed so a bad parse shows.
        from sqlalchemy import text as _t
        print("\n  Receiving side in Monarch (spending_transactions):")
        for r in cash:
            if not r["description"].lower().startswith("transfer from brokerage to"):
                continue
            hit = db.execute(_t("""
                SELECT account FROM spending_transactions
                WHERE amount = :amt
                  AND transaction_date BETWEEN :d - 2 AND :d + 2
                  AND (original_statement ILIKE '%brokerage%'
                       OR merchant ILIKE '%brokerage%')
                LIMIT 1
            """), {"amt": -r["amount"], "d": r["date"]}).scalar()
            print(f"    {r['date']}  {r['amount']:>11,.2f}  "
                  f"{'matched: ' + hit if hit else 'NOT FOUND in Monarch'}")

    records = [
        ParsedRecord(
            record_type=(RecordType.DIVIDEND if r["type"] == "DIVIDEND"
                         else RecordType.TRANSACTION),
            data={
                "source": "robinhood",
                "account_id": ACCOUNT_MAP[r["statement_account"]],
                "transaction_date": r["date"],
                "symbol": r["symbol"],
                "description": r["description"],
                "transaction_type": r["type"],
                "quantity": None,
                "price_per_share": None,
                "amount": r["amount"],
                "fees": 0,
            },
            source_row=i,
        )
        for i, r in enumerate(sorted(income + expense + cash,
                                     key=lambda r: r["date"]))
    ]

    try:
        result = save_investment_transactions_hybrid(db, records)
        print(f"\ncreated={result['created']} updated={result['updated']} "
              f"skipped={result['skipped']}")
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
    sys.exit(main())
