# Buy-Borrow-Die Page — Data Audit, 2026-09-24

Status: **F1–F4 and F7–F9 fixed 2026-09-25; F6 checked and closed as not a gap** (each section carries what
changed and the before/after numbers); F5 resolved by F1's Jan 2025 baseline.
Everything else is still open. Audited against the live API
(`/strategies/buy-borrow-die/*`), the tables it reads (`portfolio_snapshots`,
`investment_transactions`, `margin_monthly_balances`, `spending_transactions`,
`bbd_performance_metrics`, `bbd_settings`), Robinhood statements, and live
Robinhood account values on 2026-09-24. Companion to
[SPENDING-PAGE-AUDIT-2026-09.md](SPENDING-PAGE-AUDIT-2026-09.md).

## What the page shows today

| Card | Value | Verdict |
|---|---|---|
| Total capital (taxable) | $1,702,231 | overstated by ~$108K (F1) |
| 2025 growth | +25.5% / $47,809 | % inflated ~5 pts, $ ignores flows (F1, F3) |
| 2026 growth to date | +22.4% / $57,925 | % roughly 3× too high (F1) |
| Avg monthly growth | 2.82% | arithmetic, spec says compound 2.29% (F4) |
| Cumulative pure growth $ | $105,734 | identical to combined growth $ (F3) |
| 2025 earnings | 7.68% / $88,405 | denominator excludes Jaya, numerator includes her (F5) |
| Margin used | $143,221 / 12.0% | April 2026 value carried forward 5 months (F7) |
| 2025 expenses | $270,701 | year is hard-coded; 2026 never shows (F9) |
| Avg monthly spending | $27,990/mo | correct per definition; one-offs dominate 2026 (F10) |

## Findings, most damaging first

### F1 — Two definitions of "portfolio value" are mixed in one series

`portfolio_snapshots.portfolio_value` means two different things:

- **Statement rows** (through Oct 2025 for Neel, Dec 2025 for Jaya):
  securities + cash − margin, i.e. net liquidation value.
- **Daily MCP rows** (everything after): securities only. `cash_balance` is
  0.00 on every one of them. Cash held is dropped; margin borrowed is not
  subtracted.

The service takes "latest row in the month", so the series silently switches
definition: Neel in Nov 2025, Jaya in Jan 2026.

| Month | Statement value | Value the page uses | Gap |
|---|---|---|---|
| Neel Dec 2025 | $1,138,682 | $1,199,512 (Dec 26 daily) | +$60,830 |
| Jaya Jan 2026 | $648,306 | $530,610 | −$117,696 |
| Neel Apr 2026 | $996,835 | $1,145,876 | +$149,041 |
| Jaya Apr 2026 | $555,784 | $641,925 | +$86,141 |
| Both, today | $1,594,674 (live) | $1,702,231 | +$107,557 |

Consequences:

- **2025 growth** ends on Neel's Dec 26 daily row, $61K above the statement.
- **Jan 2026 monthly growth −9.75%** is mostly Jaya's $166K of cash falling
  out of the series when her source switched, not a market move.
- **2026 growth +22.4%** is on a securities-only basis. Withdrawals ($262K)
  are counted as outflows, but the $143K of margin that financed them is not
  counted as an inflow, so borrowed money reads as growth. Re-run on statement
  and live values (Jan $1,725,359 → today $1,594,674, flows −$261,591), the
  2026 Modified Dietz return is roughly **+8%**, not +22%.
- The timeline's "Total capital" and "Net worth" lines have a step at the
  switch and run ~$100–235K high through 2026.

**Fixed 2026-09-25.** One definition now, documented in
[BBD-CALCULATIONS.md](BBD-CALCULATIONS.md) "Portfolio value": net
liquidation value, `securities_value + cash_balance`, cash signed.

- `investments/snapshot_service.take_daily_snapshot` now takes signed cash
  from the MCP refresh (`account_cash_balances`: brokerage cash − margin,
  IRA total cash) and subtracts open short-option marks from securities.
  Falls back to a CASH holding row for accounts without a refresh (Alisha,
  HSA). Flags cash older than two days in its stats.
- `backend/scripts/backfill_snapshot_cash.py` (dry-run by default) rewrote
  history from data already in the database: statement month-ends from
  `margin_monthly_balances` (Jan–Apr 2025, Nov 2025–Apr 2026, both
  brokerages) and daily signed cash from `account_cash_balance_history`
  (Jun 9 2026 onward, all six accounts). 3 rows added, 425 updated,
  provenance in `ingestion_log` id 1009. Statement rows were never
  overwritten; the one conflict (Neel Oct 2025: statement row $1,198,432 vs
  margin table $1,177,169) is left as is.
- `bbd_performance_service._get_account_month_values` prefers the
  statement-sourced row in a month over the latest daily row.
- Metrics recomputed with `force=true`.

Before (Sep 24 rows) → after (Sep 25 rows, market down that day), from the
summary endpoint:

| Card | Before | After |
|---|---|---|
| 2025 growth | +25.5% on $1,151,703 (Neel only) | +15.8% on $1,649,370 (both accounts; Jaya's Jan 2025 statement now in) |
| 2026 growth to date | +22.4% | +9.5% |
| 2025 pure growth | +16.5% | +10.1% |
| 2026 pure growth to date | +9.9% | −1.5% |
| Cumulative growth | +53.7% | +26.9% |
| Cumulative pure growth | +28.1% | +8.4% |
| 2025 earnings yield | 7.68% | 5.36% (F5 also resolved by the Jan 2025 baseline) |
| Total capital | $1,702,231 (Sep 24) | $1,607,291 (Sep 25) |

**Follow-ups the same day.**

- A third writer was found and fixed: the MCP refresh's holdings paste
  rewrote today's row with securities only (cash 0) several times a day,
  undoing the 8:15 PM value. The paste save and the cash save now both call
  `snapshot_service.refresh_today_snapshot`, so today's row always carries
  the definition above.
- `RobinhoodPDFParser` had been returning nothing since it was written
  ("Robinhood PDFs provide no value"), which is why no 2026 statement had a
  snapshot row. It now emits one ACCOUNT_SUMMARY per account section,
  validated against the statement's own totals (securities + cash must
  equal Portfolio Value within $1), maps statement account numbers to app
  accounts, skips untracked accounts (Alisha, joint, Agentic, Airbnb) with a
  warning, and writes the signed Brokerage Cash Balance line into
  `margin_monthly_balances`. Robinhood's PDFs are combined statements: one
  file can carry the brokerage, the IRA and the Roth on different pages.
- Imported 2026-09-25 through the inbox scan: Jul and Aug 2026 for both
  brokerages, Jaya's IRA and Roth; Nov 2025 and Jan–Aug 2026 for Neel's
  Retirement; Jan–Jul 2026 for Neel's Roth. Margin table now runs through
  Aug 2026.

Neel's brokerage May and Jun 2026 landed later the same day (margin
−$6,479 and −$84,909; the table now has every month Jan 2025–Aug 2026 for
him). Jaya's May and Jun 2026 followed (margin +$12,183 and −$48,157), so
both brokerages now have a statement month-end for every month Jan 2025
through Aug 2026. Neel's Oct 2025 statement then settled the conflict: the
PDF prints $1,177,168.67 (the margin table was right; the $1,198,431.83
row from the Nov 2025 import was wrong) and the row now carries the
statement's cash of $12,055.84. Still missing on this axis:
for the retirement accounts Jaya's IRA and Roth Jan–Jun 2026 and Neel's
Roth Aug 2026. September statements arrive around Oct 3–4.

### F2 — Stale cached row: Jan 2025 monthly growth

`portfolio_growth / month / 2025-01-01` has baseline $1,585,290 and expected
0.64%. That baseline includes non-brokerage accounts and the expected rate is
the old 8% assumption. The row was computed 2026-02-06 and never touched again
because `_upsert_metric` skips existing rows unless `force=True`, and
`compute_all` only deletes rows *before* the cutoff. Every other row was
refreshed on 2026-09-25.

**Fixed 2026-09-25.** `compute_all(force=True)` now clears the whole cache
before recomputing, so a row the recompute no longer produces cannot
survive. The Jan 2025 row is gone; monthly growth now starts Feb 2025. A
settings-hash key would still be the cleaner guard.

### F3 — Dollar growth ignores cash flows; "pure" $ equals "combined" $

`annual_growth[year].amount = actual_value − baseline_value`. For 2025 that is
$47,809 next to a +25.5% return on a $1.15M base; the $238K Neel withdrew that
year is simply missing. The same subtraction is used for `pure_growth`, so the
"market appreciation only" dollar cards ($105,734 cumulative, $5,565/mo) are
byte-identical to the combined ones. Only the percentages are flow-adjusted.

**Fixed 2026-09-25.** Each growth row now stores `net_flows` (external cash
in/out for the paired accounts; pure_growth also counts options premium as
an inflow) and `gain_value = actual − baseline − net_flows` (migration
`20260925_bbd_metric_gain`). The summary's dollar cards and the growth
table's new Flows and Gain columns read `gain_value`. Verified against the
ledger: 2025 flows −$75,671 (Neel −$216,919, Jaya +$141,248).

| Card | Before | After |
|---|---|---|
| 2025 growth $ | $47,809 (later $176,772 after F1) | $252,442 beside +15.8% |
| 2026 growth $ to date | −$123,396 | +$138,195 beside +9.2% |
| Cumulative growth $ | $105,735 | $390,637 |
| 2025 pure growth $ | same as combined | $164,038 (= $252,442 − $88,405 premium) |
| 2026 pure growth $ to date | same as combined | −$32,497 beside −2.0% |

### F4 — Average monthly growth is arithmetic, spec says compound

`avg_monthly_growth_pct = cumulative_growth_pct / total_months` → 53.66 / 19 =
2.82%. [BBD-CALCULATIONS.md](BBD-CALCULATIONS.md) specifies
`((1+cumulative)^(1/months) − 1)` = 2.29%. Same for pure growth: 1.48% shown,
1.31% per spec.

**Fixed 2026-09-25.** Both averages are now the compound monthly rate. On
the corrected series: combined 1.24%/mo (was 1.39% arithmetic) against a
1.24% target; pure 0.40%/mo (was 0.41%) against 0.64%.

### F5 — 2025 options yield: Jaya in the numerator, not the denominator

Jaya's brokerage has no snapshot before April 2025, so the 2025 yearly
baseline pairs Neel only ($1,151,703). The income total ($88,405) includes
Jaya's $28,916. Neel-only yield is 5.2%; the page shows 7.68%. Monthly rows
Jan–Apr 2025 have the same mismatch (Jaya's Jan income $2,495 over Neel's
baseline).

### F6 — Options income gaps in early 2025

Neel's brokerage has **zero** STO/BTC rows in Mar and Apr 2025 while 35 and 32
other rows exist for those months. Jaya has none Feb–Apr and Sep 2025. Either
no options were sold, or those activity exports were never imported. This feeds
the 2025 yearly total, the 0.58% monthly average, and the tax module's 2025
figure. **Neel to confirm**; if trades happened, the Mar–Apr 2025 activity CSVs
close the gap.

**Resolved 2026-09-25: not a gap.** Neel recalled heavy options activity in
that window, so it was checked three ways. Robinhood's own activity export
(the archived "Neel Investment 2025 (till Nov 20)" CSV) has 3 STO rows in
Feb 2025, then only two TSLA call expirations in March and nothing in
April. Robinhood's realized-trade record shows zero option closes from
Mar 16 to May 10, 2025 in Neel's brokerage, Neel's IRA and Jaya's
brokerage, with the two March closes ($132, $218) matching the two
expirations. The Income and Options pages read the same ledger and show
the same zeros. No options were sold Mar–Apr 2025 (the tariff sell-off);
the ledger is complete for that window.

### F7 — Margin balances stop in April 2026 and are forward-filled

`margin_monthly_balances` was last loaded 2026-05-04 (statements through Apr
2026). `_get_real_margin_data` forward-fills the last value, so May–Sep all
show $143,221. Live on 2026-09-25: Neel −$9,714, Jaya −$25,490, net
$35,204 — the page overstates current margin by 4×, and five months of
utilization on the chart are invented. (An earlier draft of this note
quoted Jaya at −$133,470; that was her Sep 8 balance, since paid down.)
The daily signed cash now in `portfolio_snapshots.cash_balance` (from the
refresh, since Jun 9) is a ready replacement for the forward-fill.
Update 2026-09-25: the Jul and Aug 2026 statements are in, so the table now
ends Aug 2026 and the forward-filled figure is $227,027 (Aug) against
$33,644 live.

**Fixed 2026-09-25.** `_get_real_margin_data` now reads signed month-end
cash from `portfolio_snapshots` (statement row preferred, else the month's
latest daily row with the refresh's cash), with `margin_monthly_balances`
only as a fallback for months that have no cash-bearing row. No forward
fill. Margin Used reads $32,207 (2.9% utilization) for September against
$227,027 (20.6%) before. May 2026 reads $0 because Jaya's +$12,183 cash
outweighed Neel's −$6,479 margin that month — the cross-account netting of
F12, unchanged. May–Aug statements need to be loaded into this table; the importer
that fills it is separate from the income importer that already ran on them.

### F8 — "Interest accrued" formula is meaningless with real margin data

`total_interest_accrued = max(0, margin_balance − total_spending)`. That only
made sense when margin was simulated from spending. With real balances
($143K) and $588K of spending it is always 0, so the "(incl. $X interest)"
note never renders. Real margin interest is in the ledger (Jaya $1,035 YTD;
Neel's `MARGIN_INTEREST` rows likewise).

**Fixed 2026-09-25.** The summary now sums the ledger's "Aggregated Margin
Rate" charges for the two brokerages, de-duplicated on (account, date,
amount) because the same charge appears under both `OTHER` and
`MARGIN_INTEREST` on some dates. Exposed as `margin_interest_ytd` ($3,196:
Neel $2,160, Jaya $1,035) and `margin_interest_since_cutoff` ($3,212);
the Margin Used card's note now reads "· $3,196 interest charged this
year" instead of never rendering.

### F9 — "2025 Expenses" card hard-codes the year

`BuyBorrowDie.tsx:1071` reads `annual_spending['2025']`. In September 2026 the
card still says 2025 ($270,701); 2026 YTD ($317,083) is never shown.

**Fixed 2026-09-25.** The Borrow section renders one card per year in
`annual_spending`, sorted, with the current year noted as "Year to date".
Today: 2025 $270,701, 2026 $317,083 year to date.

### F10 — Spending input is right but one-offs steer the projection

`monthly_spending_totals` matches the Spending page (good). 2026 averages
$35.2K/mo vs $22.6K in 2025 because Jan 2026 carries $30K of tax payments and
Mar 2026 the $55.7K Subaru. The overall $27,990/mo drives the 55-year
projection and the "avg monthly borrowing" line. Not a bug; worth a
"one-time items excluded" toggle or a trailing-12-month average.

### F11 — Spec and code disagree on the expected lines

[BBD-CALCULATIONS.md](BBD-CALCULATIONS.md) says growth target 8% and
sustainable borrowing = portfolio × (8% − 5%) / 12. Code and settings use a
combined 16% (`assumed_combined_return`) for the growth card and
(16% − 5%) / 12 ≈ $15.6K/mo for the sustainable line. 16% is also not
8% + 12%. One of the two is stale; decide which and align the other.

### F12 — Cross-spouse netting hides real debt

Real margin nets Jaya's cash against Neel's borrowing. Dec 2025: Jaya +$72,500
cash, Neel −$10,437 margin → page shows $0 borrowed while Neel was paying
interest on $10K. Design choice, but it understates interest-bearing debt.

### Minor

- Yearly baselines use the Jan 31 snapshot, so January's move is excluded
  from every yearly figure (Dec 31, 2024 exists for Neel but sits before the
  cutoff).
- `annual_borrowing[year].portfolio_value` actually holds margin available
  (70% of portfolio).
- Weekly rows are interpolated from month-ends and labelled so; daily rows
  exist since late 2025 and could replace the interpolation.
- Options yield rows carry forward the last known portfolio for months with
  no snapshot; fine, but the same carry-forward is not applied to growth.

## Suggested order of work

1. F1 — one consistent portfolio value; everything else on the page inherits
   it.
2. F7 — load May–Aug 2026 statements into `margin_monthly_balances`.
3. F2 — force a full recompute after fixing F1.
4. F3, F4, F5, F9 — arithmetic and display fixes, each a few lines.
5. F6 — confirm or import the early-2025 options data.
6. F8, F10, F11, F12 — definitional decisions for Neel.
