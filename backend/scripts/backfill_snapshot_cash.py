#!/usr/bin/env python3
"""
Backfill signed cash into portfolio_snapshots so every row carries the same
definition of portfolio value (docs/BBD-CALCULATIONS.md, "Portfolio value"):

    portfolio_value = securities_value + cash_balance   (cash signed, negative on margin)

Daily rows written before 2026-09-25 stored securities only with cash = 0.
Two authoritative sources already in the database fill the gap:

  A. margin_monthly_balances (statement month-ends, source='statement'):
     portfolio_value and closing_balance (signed cash) per account per month.
     Written to the month-end date. A row that already came from a statement
     import (ingestion_id set) is never overwritten: if its portfolio value
     agrees within $1 the cash is filled in, otherwise the conflict is
     reported and the row left alone.

  B. account_cash_balance_history (daily MCP refresh, since 2026-06-09):
     brokerage cash = cash_balance − margin_used, IRA cash = true_cash.
     Applied to daily rows without ingestion_id on the same date;
     portfolio_value is recomputed as securities_value + cash. Open-option
     marks are not available historically, so securities_value is unchanged.

Dry-run by default. --apply writes, and records one ingestion_log row for
provenance (module 'investments', file_name 'backfill_snapshot_cash').

Usage:
    cd backend && venv/bin/python scripts/backfill_snapshot_cash.py [--apply]
"""

import argparse
import calendar
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402

IRA_TYPES = ('ira', 'roth_ira', 'retirement', 'hsa', '401k')
TOLERANCE = Decimal("1.00")


def money(v) -> str:
    v = Decimal(str(v or 0))
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args()
    db = SessionLocal()

    accounts = {r.account_id: r for r in db.execute(text(
        "SELECT account_id, account_name, account_type, source FROM investment_accounts"
    )).fetchall()}
    by_name = {r.account_name: r for r in accounts.values()}

    plan = []       # (kind, account_id, date, old_pv, new_pv, old_cash, new_cash, new_sec)
    conflicts = []  # human-readable

    # ── A. statement month-ends from margin_monthly_balances ──────────────
    stmt_rows = db.execute(text("""
        SELECT account_name, year, month, portfolio_value, closing_balance
        FROM margin_monthly_balances
        WHERE source = 'statement' AND portfolio_value IS NOT NULL
        ORDER BY account_name, year, month
    """)).fetchall()
    for r in stmt_rows:
        acct = accounts.get(r.account_name)
        if not acct:
            conflicts.append(f"A: no investment_accounts row for {r.account_name}")
            continue
        month_start = date(r.year, r.month, 1)
        month_end = date(r.year, r.month, calendar.monthrange(r.year, r.month)[1])
        pv = Decimal(str(r.portfolio_value))
        # closing_balance is the statement's "Brokerage Cash Balance" line:
        # negative when on margin, but EXCLUDING the deposit-sweep balance.
        # It is the best cash figure available for daily rows that have none;
        # a cash figure that came from a statement import already includes
        # the sweep and is kept.
        cash = Decimal(str(r.closing_balance or 0))
        sec = pv - cash
        # Latest existing row in the month, so the date set stays aligned with
        # the other accounts' daily rows instead of adding a lone month-end date.
        existing = db.execute(text("""
            SELECT id, statement_date, portfolio_value, cash_balance, securities_value, ingestion_id
            FROM portfolio_snapshots
            WHERE account_id = :a AND source = :s
              AND statement_date BETWEEN :m0 AND :m1
            ORDER BY statement_date DESC LIMIT 1
        """), {"a": acct.account_id, "s": acct.source, "m0": month_start, "m1": month_end}).fetchone()
        if existing and existing.ingestion_id is not None:
            if abs(Decimal(str(existing.portfolio_value)) - pv) <= TOLERANCE:
                if existing.cash_balance is None:
                    plan.append(("A-fill-cash", acct.account_id, existing.statement_date,
                                 existing.portfolio_value, existing.portfolio_value,
                                 existing.cash_balance, cash, sec))
                continue
            conflicts.append(
                f"A: {acct.account_id} {existing.statement_date}: statement row says "
                f"{money(existing.portfolio_value)}, margin table says {money(pv)} "
                f"(cash {money(cash)}) — left untouched")
            continue
        if existing:
            pv_same = abs(Decimal(str(existing.portfolio_value)) - pv) <= TOLERANCE
            has_stmt_cash = existing.cash_balance is not None and Decimal(str(existing.cash_balance)) != 0
            if pv_same and has_stmt_cash:
                continue  # already a statement-quality row (e.g. Jaya Nov 2025, cash incl. sweep)
            if pv_same and abs(Decimal(str(existing.cash_balance or 0)) - cash) <= TOLERANCE:
                continue
            plan.append(("A-update", acct.account_id, existing.statement_date,
                         existing.portfolio_value, pv, existing.cash_balance, cash, sec))
        else:
            plan.append(("A-insert", acct.account_id, month_end, None, pv, None, cash, sec))

    # ── B. daily signed cash from account_cash_balance_history ────────────
    hist = db.execute(text("""
        SELECT account_name, snapshot_date, account_format, cash_balance, margin_used, true_cash
        FROM account_cash_balance_history
        WHERE account_name <> 'Portfolio (Synthetic)'
        ORDER BY account_name, snapshot_date
    """)).fetchall()
    for h in hist:
        acct = by_name.get(h.account_name)
        if not acct:
            continue
        if acct.account_type in IRA_TYPES or h.account_format == 'ira':
            cash = Decimal(str(h.true_cash))
        else:
            cash = Decimal(str(h.cash_balance or 0)) - Decimal(str(h.margin_used or 0))
        existing = db.execute(text("""
            SELECT id, portfolio_value, cash_balance, securities_value, ingestion_id
            FROM portfolio_snapshots
            WHERE account_id = :a AND source = :s AND statement_date = :d
        """), {"a": acct.account_id, "s": acct.source, "d": h.snapshot_date}).fetchone()
        if not existing or existing.ingestion_id is not None:
            continue  # no daily row that day, or a statement row (authoritative)
        if existing.cash_balance is not None and abs(Decimal(str(existing.cash_balance)) - cash) <= Decimal("0.01"):
            continue
        sec = Decimal(str(existing.securities_value if existing.securities_value is not None else existing.portfolio_value))
        plan.append(("B-daily", acct.account_id, h.snapshot_date,
                     existing.portfolio_value, sec + cash, existing.cash_balance, cash, sec))

    # ── report ─────────────────────────────────────────────────────────────
    plan.sort(key=lambda p: (p[1], p[2]))
    print(f"{'DRY RUN' if not args.apply else 'APPLY'}: {len(plan)} snapshot rows to write, "
          f"{len(conflicts)} conflicts\n")
    for kind, a, d, opv, npv, oc, nc, ns in plan:
        if kind.startswith("A") or d.day >= 28:
            print(f"  {kind:11} {a:16} {d}  value {money(opv):>15} -> {money(npv):>15}   "
                  f"cash {money(oc):>13} -> {money(nc):>13}")
    daily_n = sum(1 for p in plan if p[0] == "B-daily")
    print(f"\n  ({daily_n} daily rows in B, month-ends shown above)")
    if conflicts:
        print("\nConflicts (not written):")
        for c in conflicts:
            print("  " + c)

    if not args.apply:
        print("\nDry run only. Re-run with --apply to write.")
        return 0

    # ── apply ──────────────────────────────────────────────────────────────
    log_id = db.execute(text("""
        INSERT INTO ingestion_log (file_name, file_path, file_hash, source, module, status,
                                   records_in_file, records_created, records_updated, records_skipped,
                                   warnings, started_at, completed_at, created_at, updated_at)
        VALUES ('backfill_snapshot_cash', 'backend/scripts/backfill_snapshot_cash.py', NULL,
                'derived', 'investments', 'success', :n, 0, 0, 0, :warn, NOW(), NOW(), NOW(), NOW())
        RETURNING id
    """), {"n": len(plan), "warn": "\n".join(conflicts) or None}).scalar()

    created = updated = 0
    for kind, a, d, opv, npv, oc, nc, ns in plan:
        acct = accounts[a]
        if kind == "A-insert":
            db.execute(text("""
                INSERT INTO portfolio_snapshots
                    (source, account_id, owner, account_type, statement_date,
                     portfolio_value, cash_balance, securities_value, ingestion_id, created_at, updated_at)
                VALUES (:s, :a, :o, :t, :d, :pv, :c, :sec, :ing, NOW(), NOW())
            """), {"s": acct.source, "a": a, "o": a.split('_')[0].title(), "t": acct.account_type,
                   "d": d, "pv": npv, "c": nc, "sec": ns, "ing": log_id})
            created += 1
        else:
            # A-fill-cash keeps its original ingestion_id; A-update / B-daily get the backfill's.
            db.execute(text("""
                UPDATE portfolio_snapshots
                SET portfolio_value = :pv, cash_balance = :c, securities_value = :sec,
                    ingestion_id = CASE WHEN :keep THEN ingestion_id ELSE :ing END,
                    updated_at = NOW()
                WHERE account_id = :a AND source = :s AND statement_date = :d
            """), {"pv": npv, "c": nc, "sec": ns, "keep": kind == "A-fill-cash",
                   "ing": log_id if kind.startswith("A") else None,
                   "a": a, "s": acct.source, "d": d})
            updated += 1

    db.execute(text("UPDATE ingestion_log SET records_created=:c, records_updated=:u WHERE id=:i"),
               {"c": created, "u": updated, "i": log_id})
    db.commit()
    print(f"\nWrote {created} new rows and updated {updated} rows. ingestion_log id {log_id}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
