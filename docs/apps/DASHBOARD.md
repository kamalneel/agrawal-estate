# Dashboard App

## Goal

The Dashboard provides a unified, at-a-glance view of the family's complete financial picture. It aggregates data from all modules to show net worth, asset allocation, and key financial metrics.

---

## Features

### Current Features

1. **Net Worth Summary**
   - Total assets across all accounts
   - Total liabilities (mortgages, loans)
   - Net worth calculation
   - Historical net worth tracking

2. **Asset Allocation**
   - Breakdown by asset class (stocks, bonds, real estate, cash)
   - Visualization with charts
   - Target vs actual allocation

3. **Account Overview**
   - All investment accounts
   - Cash and banking accounts
   - Real estate holdings
   - India investments

4. **Quick Metrics**
   - Monthly income summary
   - Tax liability status
   - Investment performance
   - Market value changes

---

## Roadmap

- [ ] Customizable dashboard widgets
- [ ] Goal tracking visualization
- [ ] Alerts and notifications panel
- [ ] Performance benchmarking
- [ ] Family member views

---

## Architecture

### Frontend
- **Page:** `/pages/Dashboard.tsx`
- **Route:** `/dashboard`

### Backend
- **Module:** `/backend/app/modules/dashboard/`
- Aggregates data from income, investments, real estate, and cash modules

### Data Flow
Dashboard reads from all other modules but does not have its own persistent data model.
