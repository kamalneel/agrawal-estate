# Investments Page — Spec

Status: **approved design** (Neel, 2026-07-09). Method per
[PAGE-DESIGN-PLAYBOOK.md](PAGE-DESIGN-PLAYBOOK.md). Serves Objective 3 in
[OBJECTIVES.md](OBJECTIVES.md), reframed by Neel — see below.

## Test question

> **"How is my portfolio — the stocks I actually hold — doing, independent
> of any income I've collected? Which bets are working, which aren't, and
> what should I do more/less of?"**

Explicitly NOT: total wealth (cash-inclusive, income mixes in — that's
fine elsewhere), what was earned (Income). This page is **pure price
performance of the holdings themselves** — plus, since 2026-08-08, where
that portfolio is *supposed* to be and what closes the gap (see
"Allocation targets & execution" below).

**Scope boundary moved 2026-08-08 (Neel).** This page previously disowned
"what to trade" entirely. It now owns the *allocation-driven* half of that
question — which names to buy or sell and how many contracts — because
that follows directly from the targets, which live here. Options Execution
keeps the *weekly* half: which strike this Friday, RSI gating, per-account
selection, rolls. One rule of thumb: **Investments answers "what should my
portfolio become"; Options Execution answers "what do I place today."**

## Why "pure" is exact, not approximated

Current market value − cost basis is *structurally* independent of
income: options premium and dividends never touch a stock's cost basis.
No need to back cash flows out of a value series — the gap between
"value" and "invested capital" IS the answer, by construction. This
reuses the same lot engine (`stock_lot` / `stock_lot_sale`,
`app/shared/services/cost_basis_service.py`) validated during income
unification (tied to the filed 8949 to the dollar) — Income and
Investments will agree by construction, not by coincidence.

## Three decisions (confirmed)

1. **Assignment lots**: basis = strike price, as-is, no adjustment
   (consistent with the definition-of-income rule). Marginal distortion
   from wheel mechanics is accepted, not engineered around.
2. **Closed positions**: shown, tagged separately from open positions —
   a fully-exited symbol still shows how the bet did (realized gain from
   `stock_lot_sale`), not just currently-held ones.
3. **Trillion-club policy check**: **deferred**, not built here. The
   audit (2026-07-09) found no market-cap data source anywhere in the
   app (`get_single_stock_info` fetches it via yfinance but is never
   called; no field is persisted). Revisit as its own piece once a
   Robinhood/Schwab-first source is confirmed (per the
   market-data-source-order KB rule) — do not add a Yahoo dependency for
   this without discussing it first.

## Hierarchy

- **L1 — Pure investment headline + chart.** Aggregate current value −
  cost basis, $ and %, across all *open* lots. Chart: portfolio value
  over time (`investment_holdings_history`, ~daily since 2026-02-16)
  plotted against **capital invested over time** (reconstructed from
  lot purchase/sale dates — not a snapshot, a real trajectory). The gap
  between the two lines is the pure investment return, visually, over
  time.
- **L1.5 — Allocation targets (added 2026-08-08).** Two tables, Physical
  AI and Infrastructure AI, showing current vs. target holding (%, $, and
  shares) per symbol with the gap and the option order that closes it.
  Sits above Winners & Losers because the target is now the primary read:
  W&L says how the bets did, this says what the book should be. See
  "Allocation targets & execution" below.
- **L2 — Winners & Losers.** Every symbol aggregated across accounts
  (a bet is "AAPL," not "AAPL in three different accounts"), ranked by
  return %, weight-in-portfolio shown alongside. Closed positions listed
  separately below, tagged, using realized $ and % vs. total cost basis.
- **L3 — Holdings table.** Existing per-symbol table; basis/return
  sourced from the lot engine (same as W&L — one definition), withheld
  with a footnote when lots cover <98% of live shares. Trillion-club
  badge column deliberately omitted per decision 3.
- **L4 — Context, not history.** One-line True Portfolio strip
  (cash-inclusive total, day change) + accounts grid. **Deleted from the
  page (2026-07-08, Neel):** the Capital Flow table and the True
  Portfolio chart — a transaction log answers "what happened," not
  "which bets work," and a cash-inclusive wealth trajectory is exactly
  the income-mixed-in view this page is defined against. Per-symbol
  trade provenance instead lives behind a click on any Winners & Losers
  row (open or closed), fed by `/investments/capital-events` (endpoints
  retained). Forced-buy premium context (the option-chains view) is
  Options Execution material.

## Known data gaps (2026-07-08 audit — pending fresh source files)

One cost-basis source: the lot engine feeds BOTH Winners & Losers and the
Total Portfolio Holdings table. Where lots cover <98% of live shares the
UI withholds basis/return with a footnote instead of fabricating a
number (the old table summed `investment_holdings.cost_basis`, which is
NULL for some accounts — TSLA showed +810% because Jaya's basis silently
dropped out of the denominator while her shares stayed in the value).

Verified as **data holes, not engine bugs** (lots replay the transaction
table exactly):

1. **Alisha's Brokerage** — feed dead since 2026-01-07 (6 rows ever);
   holds 5 positions incl. 17 IBIT with only a 5-share buy recorded.
   Fix: ingest fresh Robinhood activity CSV.
2. **Neel's Brokerage IBIT** — holdings 1,500 vs lots 1,400; ~100 shares
   acquired Mar 2025–Feb 2026 with no purchase row (likely an
   un-ingested put assignment; see assignment-CSV-freshness KB rule).
   Fix: fresh activity CSV covering that window.
3. **Agrawal Family HSA (Fidelity)** — zero transaction history ingested
   (161 NVDA + FDRXX). Neel has the data; will take time to pull. Until
   then HSA-held shares are flagged, not silently dropped.

## Endpoint

`GET /api/v1/investments/pure-performance` →
`{as_of, current_value, cost_basis, gain, gain_pct, chart[], open_positions[], closed_positions[]}`.
Backed by `get_pure_performance()` in
`app/shared/services/cost_basis_service.py` (symmetric placement to
`get_realized_pnl_by_period`, same module that already serves both Income
and this page).

## Allocation targets & execution (added 2026-08-08, Neel)

### The policy

Two buckets, 50/50, per the AI value-chain thesis
(`project-kb/wiki/concepts/ai-value-chain-thesis.md`):

- **Physical AI** — AAPL, TSLA, SPCX.
- **Infrastructure AI** — the nine-name AI value chain: hyperscalers
  (AMZN, MSFT, GOOGL), GPUs (NVDA, AMD), fab (TSM), custom ASIC (AVGO),
  inference memory + networking (MU, MRVL).

Everything else is off-thesis and sells to zero.

### Targets are declared, not computed

Target **share counts** (not percentages) live in
`data/allocation_targets.json` — user-declared, hand-editable, exactly the
`data/investment_policy.json` pattern. Share counts because of the
round-lot rule (`playbook/universal/finance/buy-in-round-lots-of-100.md`):
every position is a multiple of 100 so calls can be written against all of
it, and a dollar target that implies 247 shares is not actionable.

The weights behind those counts came from a one-time volatility analysis
(premium yield per name, 2026-08-08). That analysis is **frozen into the
config, not re-run at request time** — deliberately. Recomputing volatility
per page load would add a Yahoo daily-history dependency, which the
`market-data-source-order` KB rule forbids on must-succeed paths. When the
thesis changes, edit the JSON.

### Execution model

Neel does not buy and sell stock directly. He expresses both sides as short
options and lets them be exercised, earning premium on the way:

| Intent | Action |
|---|---|
| Buy (below target) | Sell **ATM puts** — assigned, shares arrive at strike |
| Sell / trim (above target) | Sell **ATM calls** — called away at strike |
| Exit (off-thesis) | Sell **ATM calls** until the position is gone |

**"Aggressive" = ATM**, fixed 2026-08-08. Strike at spot: max premium,
~50% assignment odds per expiry. It is *not* "delta 80" — that label was
already retired in `v6_engine.py` for being misleading (a true delta-80
call is deep ITM and matched neither documented policy).

Contract counts are `abs(gap_shares) // 100`, **net of options already
open** on that symbol — a name with 5 puts already sold needs 5 more, not
10. Recommendations are aggregate (per symbol, all accounts), matching the
W&L convention that a bet is "AAPL," not "AAPL in three accounts";
per-account placement is Options Execution's job.

Strike and premium estimates call the **same helper V6 uses**, so a symbol
shows identical numbers on both pages. Premium figures are heuristics, not
quotes — labelled "est." until a live chain feed exists. As of 2026-08-08
there is none: Schwab tokens are revoked and yfinance's chain endpoint is
broken.

### Feasibility

Selling ATM puts to acquire stock ties up collateral equal to the notional.
The page states the total collateral the buy program needs against
available cash (`/ingestion/robinhood-cash/balances`). If the plan cannot
be placed, it says so rather than listing unplaceable orders.

### Endpoint

`GET /api/v1/investments/allocation-plan` →
`{as_of, base_value, buckets[{key, label, target_pct, current_pct, rows[]}], exit_rows[], feasibility}`.
Backed by `get_allocation_plan()` in
`app/modules/investments/allocation_service.py`.

## Strategy model & policy deviations (added 2026-07-12, Neel)

**Demoted to an archive fold 2026-08-08 (Neel: "this is not helping me in
any way").** The section still renders — the core-exit ledger and idle
inventory are real facts and the endpoint is unchanged — but it now sits
collapsed at the bottom of the page instead of above Winners & Losers. It
answers a question Neel is no longer asking weekly; the allocation targets
above answer the one he is. Do not delete it; the two-book model still
informs the delta rules on Options Execution.

Two books, two rule sets. Classification lives in
`data/investment_policy.json` (user-declared, seeded from known market
caps — revisits spec decision 3 *without* adding a market-cap API
dependency: the $1T rule is Neel's membership heuristic, the file is his
declaration).

**Book 1 — Core (durable compounders).** $1T+ names. Buy, never sell,
no market timing. Income engine: covered calls at **delta ~10**.
Covered calls on core are the strategy, NOT a deviation. The deviation
is post-assignment: stock called away and no recovery mechanism started.
Recovery has two legal paths (Neel's rule): immediate re-buy, or selling
puts on the name until re-assigned. Deviation states per exit event:

- `recovered` — shares replaced (re-bought or put-assigned back)
- `recovering` — open short puts on that symbol in that account
- `idle` — neither, N days elapsed, gap $ = (price now − sale px) × unrecovered shares

**Book 2 — Inventory (volatility harvest).** Volatile names one would
not regret owning (INTC, SOXL, RKLB, …). Sell puts while they're
volatile; on assignment, wheel out with **delta ~20** calls
(aggressive by design — the goal is exit, not ownership). Exits are
the harvest, never a deviation. The deviation is **idle inventory**:
assigned shares sitting without an exit call written.

**Boundary with Options Execution (no-duplication rule):** the options
page *prevents* deviations (ITM roll alerts, what to do with a specific
option now); this page surfaces deviations *after* they happen and
tracks recovery. The exit-recovery ledger uses put premiums collected
during the gap as an input to the "cost of waiting" decision metric —
that is decision support, not income reporting, which stays on Income.

**Endpoint:** `GET /api/v1/investments/policy-deviations` →
`{policy, core_exits[], idle_inventory[]}` from
`app/modules/investments/policy_service.py`. Exit events come from
`stock_lot_sale` (12-month window, per account+symbol+date, FIFO
allocation of post-event acquisitions so multi-event symbols don't
double-count recovery); open puts/calls from the latest
`sold_options_snapshots` per account; prices from
`investment_holdings.current_price` (MCP-synced).

**Why deviations happen (Neel, 2026-07-12):** after the big April/May
call assignments freed a pile of cash, put-selling on volatile names
(4–6x the percentage premium of delta-10 core calls) absorbed all
attention; core re-entry and call-writing lapsed. The trap is comparing
premium yield to premium yield — Core's return is premium + durable
drift. So besides the per-symbol ledger, the endpoint reports an
aggregate: total idle-exit gap vs. inventory put income earned over the
same window ("the distraction P&L").

## vs. Buy & Hold — ghost freeze-curve (added 2026-07-18, Neel)

Question: "Am I playing the options game right, versus just holding what
I own and touching nothing?" One curve, every anchor date at once:
delta(T) = ghost_value_today(T) − actual_today, where freezing at T means
buying back all open short options at that day's marks, then holding the
T-date shares and cash untouched (external deposits/withdrawals flow into
the ghost as inert cash). Above zero: freezing would have won. Assignment
days marked; clicking any anchor opens the drill (actual-vs-ghost series
+ share-divergence table + premium collected since).

Implementation: `app/modules/investments/ghost_service.py`,
`GET /investments/ghost-curve` + `/ghost-curve/detail?anchor=`.
Share counts reconstruct BACKWARD from current MCP-synced holdings minus
lot events (forward replay drags in phantom pre-2024 residue). Anchors
restricted to dates with full 6-account cash snapshots (2026-06-09+);
extending into April/May requires an official activity-CSV backfill —
the transaction ledger alone validated $214K short over six weeks
(2026-07-18), so cash reconstruction without it is untrustworthy.
Documented approximations: no dividend adjustment; buyback from nearest
options snapshot (≤10 days); fully-exited symbols valued at last known
price (flagged).

Reading rule (on the page, not just in heads): in a bull run the curve
drifts positive because every covered-call strategy sells upside — judge
the gap against premium collected in the window, not by sign alone.
