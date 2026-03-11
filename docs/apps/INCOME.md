# Income App

## Goal

Track all sources of income for the family, including salary, stock compensation, rental income, dividends, and interest. Provide historical views and projections for tax planning and budgeting.

---

## Features

### Current Features

1. **Salary Income**
   - W-2 wages tracking
   - Pay stub history
   - Withholding tracking

2. **Stock Compensation**
   - RSU vesting schedules
   - Stock option exercises
   - ESPP purchases
   - Fair market value at vest

3. **Rental Income**
   - Property-by-property income
   - Tenant payment tracking
   - Vacancy tracking

4. **Investment Income**
   - Dividend income
   - Interest income
   - Capital gains distributions

5. **Other Income**
   - Miscellaneous income sources
   - Side business income

---

## Roadmap

- [ ] Income forecasting for future months
- [ ] Tax impact calculator per income source
- [ ] Income goal tracking
- [ ] Year-over-year comparison

---

## Architecture

### Frontend
- **Page:** `/pages/Income.tsx`
- **Route:** `/income`

### Backend
- **Module:** `/backend/app/modules/income/`
- **Models:** Salary records, stock compensation events, rental payments

### Data Model

Key tables:
- `salary_records` - W-2 and paycheck data
- `stock_compensation` - RSU/option events
- `rental_income` - Rental property income
- `dividend_income` - Dividend distributions
