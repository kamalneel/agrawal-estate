---
scope: universal
project: null
category: technical
applies-to: any table that holds a value series fed by more than one writer (statement imports, daily jobs, sync saves)
created: 2026-09-25
source-context: "BBD audit F1: portfolio_snapshots.portfolio_value meant net liquidation value in statement rows and securities-only in daily rows; 2026 growth read +22% when it was ~+9%"
---

# One Definition Per Stored Series

A column that holds a time series must mean exactly one thing, and every
writer must produce that thing. Store the components explicitly (here:
securities, signed cash, margin) so the definition is checkable row by row,
never implied by which job happened to write the row.

## Why

`portfolio_snapshots.portfolio_value` was net liquidation value when a
statement wrote it and securities-only (cash 0, margin ignored) when the
daily job wrote it. Nothing looked wrong: every row had a plausible number.
When daily rows took over from statements (Nov 2025 for Neel, Jan 2026 for
Jaya) the series silently changed meaning. Margin borrowed in 2026 read as
growth, Jaya's $166K of cash "vanished" in January, and the BBD page showed
+22% for the year against roughly +9% on one consistent basis.

There were three writers, not two. The MCP refresh's holdings paste rewrote
today's row with securities only several times a day, undoing the 8:15 PM
value — found only after the first two were fixed.

## How to apply

- Write the definition down where the table is documented, with the
  formula and the source of each component per writer
  (see docs/BBD-CALCULATIONS.md, "Portfolio value").
- Grep for every writer of the table before changing one of them. A
  `INSERT INTO <table>` / `Model(` search across the repo is the minimum.
- Never store a component as 0 because a writer lacks it. Leave it null and
  fall back explicitly, or fetch it from the source that has it.
- Reading side: prefer the authoritative row (statement, `ingestion_id`
  set) over derived rows in the same period, and say so in the reader.
- When a series is corrected, backfill from data already in the database
  with a dry-run script that reports conflicts and never overwrites a
  statement-sourced row (see `backend/scripts/backfill_snapshot_cash.py`).
