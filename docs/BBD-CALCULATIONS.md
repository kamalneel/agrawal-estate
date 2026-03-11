# Buy, Borrow, Die - Calculation Reference

## Overview

The BBD page has 4 sections:
1. **Growth** - Portfolio growth (Assumptions vs Reality)
2. **Earnings** - Options income yield (Assumptions vs Reality)
3. **Borrow** - Simulated margin borrowing from spending data
4. **Projection** - 55-year forward simulation

---

## Key Constants

| Constant | Value | Location |
|---|---|---|
| Annual portfolio growth target | 8% | `ASSUMED_ANNUAL_GROWTH = 0.08` |
| Monthly options yield target | 1% (12%/yr) | `ASSUMED_MONTHLY_YIELD = 0.01` |
| Annual margin interest rate | 5% | `ASSUMED_ANNUAL_MARGIN_RATE = 0.05` |
| Margin LTV (loan-to-value) | 70% | `MARGIN_LTV = 0.70` |
| Data start date | 2025-01-01 | `DATA_CUTOFF_DATE` |
| Brokerage accounts | neel_brokerage, jaya_brokerage | `BROKERAGE_ACCOUNTS` |

All constants in `backend/app/modules/strategies/bbd_performance_service.py`.

---

## Section 1: Growth (Assumptions vs Reality)

### Data Source
- `portfolio_snapshots` table, filtered to dates >= 2025-01-01
- For each (account, month), takes the latest `statement_date` snapshot
- **Same-store pairing**: Only sums accounts present in BOTH the start and end months being compared, to avoid false growth from accounts being opened/closed

### Monthly Growth Calculation (Modified Dietz Return)

```
actual_percent = (ending - beginning - net_flows) / (beginning + time_weighted_flows) * 100
```

Where:
- `ending` = same-store paired portfolio sum at end of month
- `beginning` = same-store paired portfolio sum at start of month
- `net_flows` = sum of external cash flows during the month (from `investment_transactions` types: CASH_MOVEMENT, ACATI, ACATO, INTERNAL_TRANSFER, TRANSFER)
- `time_weighted_flows` = each flow weighted by `(total_days - days_since_flow) / total_days`

### Weekly Growth Calculation (Simple Return)
```
actual_percent = (ending / beginning - 1) * 100
```
Weekly does NOT use Modified Dietz (no flow adjustment).

### Expected Values
- Monthly: `(1.08^(1/12) - 1) * 100` ≈ 0.6434%
- Weekly: `(1.08^(7/365) - 1) * 100` ≈ 0.1480%
- Yearly: 8.0%
- `expected_value = baseline * (1 + expected_rate)`

### Summary Cards
| Card | Formula |
|---|---|
| Avg Monthly Growth % | Compound yearly returns, derive monthly: `((1+compound)^(1/total_months) - 1) * 100` |
| Avg Monthly Growth $ | `total_dollar_change / total_months` |
| Cumulative Growth % | `product(1 + each_year_pct/100) - 1`, compounded across all years |
| Cumulative Growth $ | Sum of `(actual_value - baseline_value)` across all yearly metrics |
| {Year} Growth | From yearly `portfolio_growth` metric in DB |
| Target Monthly | `(1.08^(1/12) - 1) * 100` ≈ 0.6434% |
| Target Annual | 8.0% |

### Color Logic
- Green: actual >= expected
- Red: actual < expected

---

## Section 2: Earnings (Options Yield)

### Data Source
- `investment_transactions` table, types: STO, BTC, STC, BTO
- Summed by month to get total options income
- Baseline = same-store brokerage portfolio value at prior month

### Monthly Yield Calculation
```
actual_percent = (monthly_options_income / baseline_portfolio_value) * 100
expected_percent = 1.0  (1% per month)
expected_value = baseline * 0.01
```

### Yearly Yield Calculation
```
actual_percent = (sum_of_all_monthly_income_for_year / jan_portfolio_value) * 100
```

### Weekly Yield Calculation
- Interpolates daily portfolio values from monthly snapshots
- Gets weekly income via `_get_options_income_for_range(start, end)`

### Summary Cards
| Card | Formula |
|---|---|
| Avg Monthly Earnings % | Average of `actual_percent` across all monthly metrics |
| Avg Monthly Earnings $ | Average of `actual_value` across all monthly metrics |
| Cumulative Earnings $ | Sum of all monthly `actual_value` |
| Cumulative Earnings % | `(total_income / avg_baseline) * 100` |
| {Year} Earnings | From yearly `options_yield` metric |
| Target Monthly | 1.0% |
| Target Annual | 12.0% |

---

## Section 3: Borrow (Margin Simulation)

### Concept
Simulates what would happen if ALL spending were financed by borrowing against the portfolio (margin loan), rather than selling assets. This is the core BBD strategy.

### Data Source
- `spending_transactions` table (from Monarch Money CSV imports)
- Only negative amounts (actual expenses), excluding transfer-like categories
- Excluded categories: Transfer, Credit Card Payment, Paychecks, Interest, Investments, Savings, Fees & Charges, etc.

### Monthly Borrowing Calculation
```
monthly_rate = (1.05)^(1/12) - 1  ≈ 0.4074%

For each month chronologically:
  cumulative_margin = cumulative_margin * (1 + monthly_rate) + this_month_spending
  margin_available = brokerage_portfolio_value * 0.70
  utilization_pct = cumulative_margin / margin_available * 100

Expected line:
  avg_monthly_spend = total_spending / num_months
  expected_cumulative = expected_cumulative * (1 + monthly_rate) + avg_monthly_spend
```

### Summary Cards
| Card | Formula |
|---|---|
| Margin Available | 70% of brokerage portfolio value (latest month) |
| Margin Used | Latest cumulative margin balance |
| Margin Utilization % | `cumulative_margin / margin_available * 100` |
| Avg Monthly Spending | `sum(all_monthly_spending) / count(months)` |
| {Year} Expenses | Sum of monthly spending for that year |
| Interest Accrued | `current_margin_balance - sum(all_spending)` (the difference is simulated interest) |

### Color Logic (Inverted)
- Green: actual utilization <= expected (lower is better)
- Red: actual utilization > expected

---

## Section 4: Future Projection

### Adjustable Input Parameters
| Parameter | Default | Description |
|---|---|---|
| Growth Rate | 8% | Annual portfolio appreciation |
| Monthly Borrowing | $20,000 | Monthly living expenses borrowed |
| Interest Rate | 5.25% | Annual margin loan interest rate |

### Fixed Parameters
| Parameter | Value |
|---|---|
| Current Age | 45 |
| End Age | 100 |
| First Year Months | 11 |
| Margin Buffer % | 76% |

### Starting Capital
- SQL: `SUM(market_value) FROM investment_holdings` for brokerage accounts (Neel's + Jaya's)
- Fallback: $2,900,000

### Projection Loop (for each year i=0 to 55)
```python
growth = capital * annual_growth_rate
ending_cap = capital + growth

annual_borrowing = monthly_borrowing * 12  # (* first_year_months for year 0)
cumulative_borrowing += annual_borrowing

annual_interest = cumulative_borrowing * borrowing_interest_rate  # simple interest
cumulative_interest += annual_interest

total_debt = cumulative_borrowing + cumulative_interest
net_worth = ending_cap - total_debt

margin_available = ending_cap * 0.76  # margin_buffer_percent
margin_utilization = total_debt / margin_available * 100
is_safe = margin_utilization < 100

capital = ending_cap  # carry forward
```

**Note**: Interest is **simple interest** on cumulative borrowing (not compound). Each year's interest = `cumulative_borrowing * rate`. Interest does NOT compound on itself.

### Summary Cards
| Card | Formula |
|---|---|
| Starting Capital | Sum of brokerage holdings market values |
| Final Portfolio (Age 100) | Last year's `ending_capital` |
| Capital Growth Multiple | `final_capital / starting_capital` |
| Total Borrowed | Last year's `cumulative_borrowing` |
| Total Interest Paid | Last year's `cumulative_interest` |
| Final Net Worth | `final_capital - total_debt` |
| Strategy Sustainable | True if utilization never reaches 100% |
| Final Margin Utilization | Last year's `margin_utilization` % |
| Tax Savings (client-side) | `total_borrowed * 0.25` (assumed 25% tax rate) |

### Charts
1. **Portfolio Growth vs Debt** - Lines for Portfolio, Debt, Net Worth, Interest over age
2. **Margin Utilization** - Area chart with 80% warning and 100% danger reference lines

---

## API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/strategies/buy-borrow-die/projection` | POST | Future projection (Section 4) |
| `/strategies/buy-borrow-die/assumptions/metrics?metric_type=portfolio_growth&period_type=month` | GET | Growth chart (Section 1) |
| `/strategies/buy-borrow-die/assumptions/metrics?metric_type=options_yield&period_type=month` | GET | Earnings chart (Section 2) |
| `/strategies/buy-borrow-die/assumptions/metrics?metric_type=margin_borrowing&period_type=month` | GET | Borrow chart (Section 3) |
| `/strategies/buy-borrow-die/assumptions/summary` | GET | Summary cards for all 3 sections |
| `/strategies/buy-borrow-die/assumptions/compute?force=true` | POST | Recompute all metrics |

---

## Source Files

| File | Role |
|---|---|
| `frontend/src/pages/BuyBorrowDie.tsx` | Page UI, client-side formatting, drill-down navigation |
| `backend/app/modules/strategies/router.py` | All BBD API endpoints |
| `backend/app/modules/strategies/bbd_performance_service.py` | Core computation engine |
| `backend/app/modules/strategies/models.py` | `BbdPerformanceMetric` DB model |
| `backend/app/modules/spending/models.py` | Excluded spending categories |
