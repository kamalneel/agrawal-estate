---
scope: universal
project: null
category: technical
applies-to: any backfilled or reconstructed time series — holdings history, capital-over-time, anything replayed from a ledger and priced
created: 2026-09-13
source-context: "Backfilling 2024 holdings history; the existing 2025 backfill turned out to be $217K–$458K high every month, and its only check had passed."
---

# A Synthesised Series Needs a Control Total Inside the Period, Not Just at the Seam

When a table is reconstructed rather than ingested, validate it against the
source's own totals at points *inside* the reconstructed range — every
month-end that has a statement — and abort on a miss. Reconciling only where
the synthetic series meets the real one proves nothing about the middle.

## Why

`backfill_holdings_history.py` rebuilt Jan 2025 → Feb 2026 from the lot
engine and checked one thing: that its last synthetic day matched the first
real snapshot. It passed. It was also wrong for ten months: NFLX lots had
been scaled to post-split units by the lot rebuild, the script priced them
with raw pre-split closes, and `neel_retirement` read 10× on that position
until the 2025-11-17 split date — after which the units agreed and the
seam check saw nothing. The monthly statements in `portfolio_snapshots`
had the right number the whole time; nobody was comparing to them.

## How to apply

- Find the source's control total for the same quantity (statement
  `securities_value` per account per month-end) and check every one that
  falls inside the period. Print the comparison, pass or fail.
- Abort on breach. A per-pair drop is fine at the seam where the miss is
  attributable; a month-end miss is not, so the run stops.
- Allow only the asymmetries you can name: an assignment dated the last
  trading day lands on the next statement, so accept when the day before
  agrees. One day, documented — not a wider tolerance.
- This is [[validate-parser-against-source-totals]] applied to data you
  generated instead of data you parsed. Same rule, same reason.
