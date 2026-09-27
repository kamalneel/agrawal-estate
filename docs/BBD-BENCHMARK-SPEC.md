# BBD Benchmark — "Did the options game beat buying QQQ?"

Status: **spec written 2026-09-27, v1 built the same day.** Serves the
question Neel put on 2026-09-27:

> "At the end of the day, what I'm trying to know is whether all the
> effort that I'm putting in by doing the option selling is producing
> better returns than just buying QQQ and holding on to it."

Everything happens in the two taxable brokerages: buying, holding,
selling options, spending from the account, and borrowing on margin. A
return percentage alone cannot answer the question, because money keeps
moving in and out. The answer has to be in dollars, with the same money
moving the same way in both worlds.

## The method: a twin portfolio with identical cash flows

Build a **QQQ twin** of the two brokerages and run it through history:

1. **Start** on the first month-end both accounts have a statement value
   (2025-01-31). The twin buys QQQ with exactly the accounts' combined net
   liquidation value that day.
2. **Every external cash flow** the real accounts had — deposits in,
   withdrawals out (`investment_transactions` types CASH_MOVEMENT, ACATI,
   ACATO, INTERNAL_TRANSFER, TRANSFER for the paired accounts) — hits the
   twin on the same date, at that day's QQQ close: a deposit buys shares,
   a withdrawal is funded one of two ways (below). Options premium,
   dividends, interest and margin interest are **not** flows: they are the
   strategy's own results and stay inside the real accounts.
3. **Compare** at every month-end and today: real net liquidation value
   (the shared `portfolio_snapshots` series) against the twin's value.
   The difference is the dollar verdict. The twin's time-weighted return
   is just QQQ's price return; the real accounts' is the combined
   Modified Dietz the page already computes.

Two twins, because the real strategy borrows rather than sells:

| Twin | Withdrawals funded by | What it answers |
|---|---|---|
| **QQQ, sell** | selling shares at that day's close | "Passive investor, same spending": the plain buy-and-hold alternative |
| **QQQ, borrow** | a margin loan at the page's margin rate, compounding monthly; twin value = shares × price − loan | "Same leverage, index instead": isolates stock picking + options from the borrowing decision |

## What is deliberately left out of v1, and why

- **Taxes.** The two worlds are taxed differently: options premium and
  short-term gains at ordinary rates, QQQ sales at long-term rates, and
  margin borrowing at zero. That asymmetry favours the twin-sell world
  less than it looks and is the next layer (v2: after-tax with two
  configurable rates). v1 is pre-tax and says so on the page.
- **QQQ dividends** (~0.5%/yr). Small; noted, not modelled. v2 can use
  total-return.
- **Retirement accounts.** Out of BBD scope; a per-account twin is a
  natural extension once this lands.

## Presentation (BBD page, new section "vs. QQQ buy-and-hold")

1. **Verdict line.** "Since Jan 31, 2025, with the same money in and out:
   your brokerages $X, a QQQ buy-and-hold twin $Y. You are $Z ahead /
   behind (±p% of the starting value)." Both twins shown.
2. **Chart.** Real value vs the two twins, month-ends plus today, same
   flows. One glance shows when the gap opened.
3. **Per-year table.** For 2025 and 2026 to date: real ending value, twin
   ending values, dollar gap, real TWR vs QQQ TWR.
4. **Where the gap comes from.** From the metrics the page already has:
   growth vs QQQ price return, income earned, margin interest paid. So a
   lag can be read as "capped upside" or "cash drag" or "the names",
   not just a red number.
5. **Assumptions strip.** Start date and value, flow count, margin rate,
   price source, "pre-tax", QQQ dividends excluded.

## Data

- QQQ (and SPY, for a second yardstick) daily closes from the Robinhood
  MCP `get_equity_historicals`, stored in `symbol_price_history` through
  `POST /ingestion/price-history` (source `robinhood_mcp`). Backfilled
  from 2024-12-01; the refresh keeps them current with the other tracked
  symbols.
- Real values: `portfolio_snapshots`, statement row preferred, paired
  accounts (`BbdPerformanceService._get_account_month_values`,
  `_paired_sum`). Flows: `_get_external_cash_flows_for_period`.

## Implementation

`app/modules/strategies/bbd_benchmark_service.py` → `get_benchmark(db,
symbol='QQQ')`; `GET /strategies/buy-borrow-die/benchmark?symbol=QQQ`.
Frontend section in `BuyBorrowDie.tsx` after Growth + Income.

## Reading the first result honestly

The twin is generous to the index in one way (no tax on QQQ sales, no
tax drag modelled anywhere) and generous to the strategy in another (QQQ
dividends omitted). Neither is large enough to flip a verdict measured
in tens of thousands of dollars. Treat a gap under ~2% of starting value
as noise; treat a persistent gap in one direction across both years as
the answer.
