# Spending Page — Spec

Status: **stage 1 built** (L1 outflow band, 2026-07-08). Method per
[PAGE-DESIGN-PLAYBOOK.md](PAGE-DESIGN-PLAYBOOK.md); serves Objective 4 in
[OBJECTIVES.md](OBJECTIVES.md) ("high-level categorization, nothing
deeper").

## Test question

> **"What am I spending, on what — and am I spending in the right
> places?"**

## Two sources, two jobs (Neel, 2026-07-08)

1. **How much** → money leaving Neel's/Jaya's brokerage toward spending
   channels (`investment_transactions`; fresh with every activity-CSV /
   sync import). 95% of family spending runs through the Robinhood
   credit card + savings/checking, and the card is paid from the
   brokerage — so outflows ≈ true total spend, current to the day.
   The Robinhood card/checking are NOT reachable via the trading MCP
   (brokerage-only, `affiliate: rhf`); only their brokerage-side funding
   legs are.
2. **On what** → Monarch CSV (aggregates RH card, RH savings/checking,
   BofA, Chase). Manual export, monthly-ish. When stale, the page says
   "categorized through <date>" — never silently blends the two.

## Outflow definition (encoded in `/spending/outflows`)

- Accounts: `neel_brokerage`, `jaya_brokerage`.
- Types: `XENT_CC`, `XENT`, `CASH_MOVEMENT`, `RTP`.
- **Card & spending** bucket: description matches credit-card/spending
  ("Robinhood Credit Card balance payment" through Oct 2025, then
  "Transfer from Brokerage to Spending" — same economic channel,
  relabeled by RH). Positive "Cash back" rows are netted against it.
- **Bank transfers out** bucket: everything else negative (ACH
  Withdrawal, RTP instant transfers → BofA/Chase).
- Pre-Dec-2025 rows deduped at query time (`DISTINCT ON` account/date/
  type/amount/description): the backfill double-ingested identical rows
  under two hash schemes (NFLX-incident bug class). No destructive
  deletes.
- Validation: Jan 2026 outflows $61,796 vs Monarch categorized $60,260 —
  reconciles within 2.5%.

## Hierarchy

- **L1 — Total spend band** (BUILT): period total from outflows, card
  vs bank split, Monarch reconciliation line when covered, dual
  freshness stamps (outflows through X / Monarch through Y, amber when
  stale). Follows the page's existing year/month selector.
- **L2 — Composition**: existing Monarch category views (already decent:
  excluded-categories model, recurring vs one-time vs trips).
- **L3 — Trend**: existing monthly views.
- **L4 — Transactions**: existing tables.
- Stage 2 (not built): restructure L2–L4 to playbook standards once a
  fresh Monarch CSV lands and freshness handling can be exercised for
  real.

## Known data notes

- Monarch data ends 2026-02-06 — awaiting fresh CSV export from Neel.
- Outflow freshness tracks the activity-CSV import (Jun 8 as of
  writing), not the MCP order sync — cash movements don't come through
  `get_equity_orders`.
