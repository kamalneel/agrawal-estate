# Income Unification — Spec

Status: **agreed philosophy, pre-implementation** (discussed with Neel 2026-07-03)
Serves: Objective 1 in [OBJECTIVES.md](OBJECTIVES.md)

## Definition of income (agreed)

Income is **realized money events**, fixed + dynamic, across **all accounts**
— identical definition regardless of tax treatment.

- **Fixed**: salary, rent, **airbnb**.
- **Dynamic**: options premium, dividends, interest, stock lending, and
  **realized stock-sale P/L** (positive or negative).
- **Holding a stock is never income.** Unrealized moves don't count.
- **Assignments** (decision A, 2026-07-03):
  - **Call assignment** = a forced sale → realized P/L counts as income at
    the moment shares are called away, categorized as **equity-sale income,
    exactly like a normal stock sale** — NOT options income (clarified
    2026-07-03). The call's premium stays in options income, collected when
    the call was sold. Mechanically the assignment is just a SELL through
    the lot engine; no separate "assignment" income category exists.
  - **Put assignment** = a forced purchase → **not** income. It creates a
    lot at the strike price. Income arrives later when those shares are sold.
- **Retirement accounts included** (decision B): a sale in an IRA is income
  even though it has no tax consequence. Tax-only views remain the tax
  module's job.

### Double-counting rule (critical)

Options premium is counted as income **when collected** (already true today).
Therefore, in the income ledger, a lot created by put assignment has basis =
**strike price**, NOT the tax basis (strike − premium). Using tax basis would
count the premium twice. The tax module keeps tax-basis semantics; the income
view keeps strike-basis semantics.

## What exists today (verified 2026-07-03)

| Source | Where | State |
|---|---|---|
| Options / dividends / interest / lending | `income/db_queries.py` over `investment_transactions` | Good; lending excluded from summary total (bug) |
| Stock sales | `get_taxable_stock_sales` | **Gross proceeds only** — not P/L; taxable accounts only |
| Realized P/L engine | `tax/cost_basis_service.py` (`stock_lot`, `stock_lot_sale`, FIFO) | Works, but **lots exist only for taxable brokerages** (neel 594, jaya 12, alisha 2). Zero lots for Neel's Retirement (71 sells!), Jaya's IRA (25), both Roths |
| Salary | `salary_service.py` (payslips + W2Record) | Good, excluded from summary total |
| Rental | `rental_service.py` (monthly tables) | In total but missing from per-account rows |
| Assignments | `strategies/assignment_tracker.py` | Disconnected from income |

Backfill feasibility: `investment_transactions` covers each account's full
life (Neel's Brokerage from 2018-11, others from 2024–2025 inception), so
lots for retirement accounts can be built from history.

## Design

### 1. Unified income service (no new tables)

`income/unified_service.py`: unions the existing per-source queries into
normalized events — `(date, source_type, fixed|dynamic, account, symbol?,
amount)` — and aggregates by **week / month / year** on an
**actual-receipt basis** (no proration; salary lands the week it was paid).

Query-time aggregation. No schema change, no data duplication, consistent
with the no-direct-DB-modifications rule. Materialize later only if slow.

### 2. Promote the lot engine to shared infrastructure

`CostBasisService` becomes the single realized-P/L source for both tax and
income. Income calls it per-period across **all** accounts; tax keeps its
taxable-only filters.

### 3. Backfill lots for non-taxable accounts

One-time import via the existing `import_robinhood_transactions` path
(FIFO), fed from `investment_transactions` history, for: Neel's Retirement,
Jaya's IRA, both Roth IRAs, HSA. Taxable-brokerage lots already exist —
**reconcile, don't rebuild** (verify existing 594 Neel lots against
transaction history before touching anything).

### 4. API

`GET /api/v1/income/unified?granularity=week|month|year&start=&end=`
→ per-period rows: total, fixed subtotal, dynamic subtotal, per-source
breakdown, per-account breakdown. `/income/summary` becomes a thin wrapper
(same totals — fixing the salary/stock-sale/lending exclusions).

### 5. Frontend

One summary band at the top of the Income page: this week / this month /
this year, fixed vs dynamic, expandable per-source and per-account. Existing
per-source sections stay beneath. Design tokens only.

## Rental: who owns the number (resolved 2026-07-26)

303 Hartstene's rent was recorded **twice** — in `rental_monthly_income`
(a hand-maintained lease schedule, property_id 1, pre-populated through
2027-03) and in the Monarch feed under `303 Hartstene Dr`. Verified
identical: Jan–Mar 2026 is $6,220/mo in the schedule and $5,000 + $1,220 of
Zelle receipts in Monarch, to the cent.

Ownership is now split **by date**, both feeding the one `rental` stream so
the user sees a single continuous line:

- **Before Monarch coverage begins** → the lease schedule (2021-03 → 2024-12).
- **From Monarch's first row onward** → actual bank receipts, netted against
  property costs (HOA, tax, repairs) per `CategoryKind.BUSINESS`.

The boundary is derived from `MIN(transaction_date)` for the category, not
hardcoded, so it moves by itself if an older export is ever loaded.
Future-dated schedule rows are excluded from actuals.

**Known data-quality caveat.** The Monarch actual is noisier than the
schedule, for two reasons worth separating:

1. *Timing, not economics* — the $5,000 and $1,220 legs sometimes straddle a
   month boundary (Feb 27 + Mar 2), so a month can look light and the next
   heavy. Real cash, real dates; only the monthly shape is affected.
2. *Miscategorized rows* — a $10,000 wire (2025-03), a $7,000 BofA transfer,
   Great Wolf Lodge, Uber. 2025 Zelle rent totals $68,600 against a $67,300
   schedule; the extra $10,429 of "gross" is not rent. **Fix at source in
   Monarch** — recategorizing there flows through on the next import.

A net-negative month is therefore legitimate (Nov 2025 = −$1,915, a $2,699
insurance bill against one rent leg), not a bug.

## Pre-revenue streams: Airbnb (built 2026-07-25)

A stream may be **negative before it earns**. The Airbnb business bills
monthly through 2026 with revenue starting 2027; Neel's instruction was to
put it on the Income page now and let it read negative until it turns.

- **Source**: `spending_transactions` rows carrying
  `spending.models.AIRBNB_CATEGORY`. That category is in
  `EXCLUDED_CATEGORIES`, so the same row can never appear on both the
  Spending and Income pages — the exclusion there *is* the inclusion here.
  Both sides import the one constant so the definition cannot drift.
- **Sign**: spending stores outflows negative, so the amounts carry through
  as negative income unchanged. No sign-flipping anywhere.
- **Classified `fixed`**, alongside rent — it is a property-based business,
  not a market-dependent flow. This means the *Fixed* subtotal absorbs the
  drag (Apr 2026 fixed income falls to $836 against a $5,564 Airbnb month),
  which is the honest reading: the household really did earn that much less
  in fixed income that month.
- **No new table.** Query-time aggregation, consistent with §1.

**When revenue starts in 2027**, revenue rows must land in this same stream
so the chip nets to a real margin. Decide then whether Airbnb stays one net
line or splits into gross-revenue / operating-cost rows the way rental may
eventually need to.

## Out of scope (separate problems)

- Yield targets (1%/mo holdings, 2%/mo cash) — Objective 2, next discussion.
- Any change to tax forecasting semantics.

## Open items to resolve during implementation

1. Provenance of the existing 594 taxable lots — reconcile vs transaction
   history before trusting them.
2. Positions that entered accounts without a BUY (transfers/ACATS, gifts) —
   detect sells that can't match a lot and surface them instead of guessing
   basis (see HISTORICAL_COST_BASIS_GUIDE.md).
3. ~~Week boundary convention~~ Resolved 2026-07-03: **Friday-ending weeks**
   (Sat–Fri), matching the options-expiration rhythm. Use everywhere,
   including the existing per-account options weekly view.
4. ~~Labeling call-assignment sales as "assignment"~~ Resolved 2026-07-03:
   no separate label — assignment sales are ordinary equity sales in the
   income view.
