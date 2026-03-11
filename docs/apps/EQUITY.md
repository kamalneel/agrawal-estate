# Equity App

## Goal

Provide detailed tracking of stock and equity holdings, with focus on employer stock compensation, vesting schedules, and equity-based wealth management.

---

## Features

### Current Features

1. **Stock Holdings**
   - All equity positions across accounts
   - Current market values
   - Cost basis per lot

2. **Employer Stock**
   - RSU tracking
   - Stock option grants
   - ESPP holdings
   - Vesting schedules

3. **Concentration Analysis**
   - Single-stock exposure
   - Diversification metrics
   - Risk warnings

4. **Equity Transactions**
   - Vest events
   - Sales history
   - Tax lot matching

---

## Roadmap

- [ ] Vesting calendar visualization
- [ ] 10b5-1 plan tracking
- [ ] Blackout period alerts
- [ ] Equity comp value projection
- [ ] Diversification recommendations

---

## Architecture

### Frontend
- **Page:** `/pages/Equity.tsx`
- **Route:** `/equity`

### Backend
- **Module:** `/backend/app/modules/equity/`

### Data Model

Key tables:
- `equity_grants` - Stock grants and options
- `vesting_events` - Scheduled and completed vests
- `equity_sales` - Sale transactions
