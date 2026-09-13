---
scope: universal
project: null
category: technical
applies-to: anything that needs share counts as of a past date — holdings backfills, per-day collateral, historical weights
created: 2026-09-13
source-context: "The lot-based holdings backfill valued 27 pre-split NFLX shares as 271 for ten months."
---

# `stock_lot` Quantities Are in Post-Split Units — Replay Transactions for As-Of-Day Counts

The lot rebuild scales every lot that is *open* at a split into post-split
units, retroactively, and leaves lots closed before the split in pre-split
units. A lot-level replay to a date before a split therefore hands back a
mix of units for the same symbol, and no single price series is right for
it. Anything that needs "how many shares on day d" must replay
`investment_transactions` (BUY/SELL/ACATI/ACATO/SPL…) forward, which keeps
each day in that day's units, and price it with **raw** closes.

## Why

`stock_lot` exists for cost basis, and cost basis is split-invariant, so
scaling the quantity and the per-share cost together is correct for that
purpose. Share counts are not split-invariant. The first holdings backfill
replayed lots and used raw prices; for NFLX before 2025-11-17 that was the
scaled count × the unscaled price — 10× the real position, $217K–$458K of
phantom `neel_retirement` capital every month.

## How to apply

- Cost basis, realised gain, holding period → read `stock_lot` /
  `stock_lot_sale`. Share count on a date → replay transactions.
- Use the same transaction universe and ordering as
  `scripts/rebuild_stock_lots.py` (same-day inflows before outflows,
  MCP-inferred assignments expanded the same way — import its helpers),
  so the two replays never disagree about a share move.
- Raw closes (`adjustment_type='none'`) with as-of-day counts. Never
  split-adjusted prices with them, and never raw prices with lot counts.
- Related: [[synthesised-series-need-in-period-control-totals]] is the
  gate that catches this class of error when it recurs.
