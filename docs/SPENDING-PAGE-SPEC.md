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

## Robinhood-native CSV import (2026-07-08)

`backend/scripts/import_rh_spending_csv.py` imports RH's own exports
(credit card / savings / checking) into `spending_transactions`
(`tags='rh_csv'`), covering the gap between Monarch exports:

- Per-account cutoff: only rows newer than existing coverage import — no
  cross-source fuzzy dedup needed.
- Card purchases auto-categorized from a merchant→category map **learned
  from Monarch history** (normalized matching: punctuation/Inc/the
  stripped) + a small seed list. Trip tags and one-offs are
  non-transferable (a Europe-trip cafe isn't "Europe Trip 2025" forever).
  Payments → 'Credit Card Payment' (excluded). Declined rows skipped.
- Unknown merchants stay NULL → render as Uncategorized (never guessed).
  As of import: $48K uncategorized, dominated by wires to Eric Chang
  ($28.5K), Cash Delivery, Gifthealth — need Neel's classification.
- **Supersede rule for future Monarch imports**: Monarch is the
  categorization authority. When a fresh Monarch export covering the
  rh_csv period is imported, first delete the rows it supersedes, then
  import — otherwise the same purchases double-count under two hash
  schemes (NFLX-incident class). Implemented in
  `backend/scripts/import_monarch_spending_csv.py` (dry-run by default).

  Exercised for real on 2026-07-25, which surfaced two corrections to the
  rule as originally written:

  1. **Bound the delete per account at that account's own last date in
     the export — do not clear whole accounts.** Monarch is not uniformly
     fresher than rh_csv. Its per-account feeds stop at different dates,
     and the Robinhood ones *lag*: card through 2026-06-26 and Spending
     through 2026-06-06, while rh_csv ran to 2026-07-08. Clearing the
     card account wholesale would have destroyed 64 rows of the freshest
     spending data on the page.
  2. **Reconcile account renames before deleting or hashing.** Monarch
     renamed `Robinhood Credit Card (...8154)` →
     `Robinhood Credit Card **8154 (...8154)` and
     `Robinhood Spending (...2623)` → `Spending (...dabe)` (new
     identifier, same account — Jan totals match to the cent). Since
     `record_hash` includes the account name, a rename makes every row
     look new: of 1251 rows only 67 hash-matched, and a naive import
     would have double-counted ~800 card rows. The script keeps an
     `ACCOUNT_ALIASES` map and renames DB rows in place first; **it must
     be extended whenever Monarch renames an account.**

  Accounts absent from an export (Robinhood Checking/Savings — Monarch
  does not track them) are left untouched, so rh_csv remains their only
  source.

## Known data notes

*(updated 2026-07-25 after the 2026 YTD Monarch import)*

- **Categorization is now the fresh side; outflows are the stale side** —
  the reverse of the situation this page was designed around. Monarch
  covers 2026-01-01 → 2026-07-25 across all 11 accounts (BofA/Chase/Citi/
  PayPal included, so the ~5% gap is closed). Uncategorized 2026 spend is
  $818 across 23 rows, down from ~$48K. Robinhood card/Spending are
  Monarch-covered through 2026-06-26 / 06-06, with rh_csv carrying the
  card to 07-08.
- **Outflows are stale and it distorts every monthly comparison**:
  `neel_brokerage` through 2026-06-08, `jaya_brokerage` through
  2026-04-02. Apr–Jul show categorized > outflows purely because the
  outflow side is missing — not a categorization gap. Needs an
  activity-CSV import to fix; nothing on the Monarch side will.
- **Outflows ≠ monthly spend, by construction.** Outflows measure money
  *leaving the brokerage*, which is lumpy pre-funding, not spend in that
  month. Feb 2026: $51,337 moved brokerage→spending in 4 transfers
  against $25,956 of actual categorized spending. The two only converge
  over longer windows — treat the L1 reconciliation line as a
  quarter-or-longer check, not a monthly one.
- **The old March 2026 note was wrong** and has been corrected: it read
  "outflows $179K vs categorized $14K — tax payments left via ACH."
  With full Monarch coverage, March categorized is **$81,463**, and the
  dominant item is a **$55,722 Subaru** (category `ONE TIME`, bought from
  Home Expense 9486), not taxes. The IRS row that month is a **+$16,897
  credit**, not a payment.
- Outflow freshness tracks the activity-CSV import, not the MCP order
  sync — cash movements don't come through `get_equity_orders`.
- `monarch_through` on `/spending/outflows` is a global
  `MAX(transaction_date)` (now 2026-07-25). That overstates the Robinhood
  card, which Monarch only categorizes through 06-26. A per-account
  freshness stamp would be more honest if the card's tail ever matters.
