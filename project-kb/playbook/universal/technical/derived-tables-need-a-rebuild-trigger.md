---
scope: universal
project: null
category: technical
applies-to: materialized/derived tables — cost-basis lots, aggregates, caches, anything replayed from a source ledger
created: 2026-09-06
source-context: "Equity-sale income read $0 for July and August; stock_lot_sale had not been written since 2026-06-18."
---

# A Derived Table Needs an Explicit Rebuild Trigger, Hung Off Its Real Writer

If a table is derived from another, something must rebuild it when the source
changes. Name that trigger and wire it. A rebuild script that only a human
runs is not a trigger.

## Why

`stock_lot` / `stock_lot_sale` are replayed from `investment_transactions` by
`scripts/rebuild_stock_lots.py`. Nothing called it — not the scheduler, not
the ingestion pipeline. The tables were last written 2026-06-18 and every
assignment after that was invisible to equity-sale income for nearly three
months. The August INTC call assignment (100 shares at $100, a $1,010 gain)
simply did not exist as income.

The obvious hook was wrong. Ingestion looked like the right place, but
MCP-inferred assignments are INSERTed directly by
`assignment_detection_service` and never touch the ingestion pipeline — so
hooking ingestion would have left the exact case that broke still broken.

## How to apply

- Trace who actually writes the source rows, all of them. Hook the rebuild
  to that writer, not to the path you assume data arrives on.
- Run the rebuild in its own session, after the writer's commit. A rebuild
  that clears before rewriting must be able to roll back without taking the
  newly written source rows with it.
- Wrap it so a rebuild failure cannot break the thing that triggered it, and
  log what stays stale until someone reruns it by hand.
- Suspect staleness whenever a derived figure reads zero while its source
  keeps moving. Compare `MAX(date)` of the derived table against `MAX(date)`
  of its source — a gap is the whole diagnosis. Related:
  [[assignment-rows-require-csv-freshness]].
