# Investments Page — Spec

Status: **approved design** (Neel, 2026-07-09). Method per
[PAGE-DESIGN-PLAYBOOK.md](PAGE-DESIGN-PLAYBOOK.md). Serves Objective 3 in
[OBJECTIVES.md](OBJECTIVES.md), reframed by Neel — see below.

## Test question

> **"How is my portfolio — the stocks I actually hold — doing, independent
> of any income I've collected? Which bets are working, which aren't, and
> what should I do more/less of?"**

Explicitly NOT: total wealth (cash-inclusive, income mixes in — that's
fine elsewhere), what to trade (Options Execution), what was earned
(Income). This page is **pure price performance of the holdings
themselves.**

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
