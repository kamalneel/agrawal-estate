# India Investments App

## Goal

Track investments held in India, including mutual funds, fixed deposits, and other assets. Handle currency conversion and cross-border tax implications.

---

## Features

### Current Features

1. **Investment Tracking**
   - Mutual funds (India)
   - Fixed deposits
   - PPF/EPF
   - NRE/NRO accounts
   - Real estate in India

2. **Currency Handling**
   - INR to USD conversion
   - Historical exchange rates
   - USD-equivalent values

3. **Tax Considerations**
   - FBAR reporting requirements
   - FATCA compliance tracking
   - India tax paid tracking

4. **Family Investments**
   - Father's portfolio tracking
   - Family member investments

---

## Roadmap

- [ ] Real-time INR/USD conversion
- [ ] India tax filing integration
- [ ] Mutual fund NAV tracking
- [ ] Capital gains in INR
- [ ] DTAA benefit tracking

---

## Architecture

### Frontend
- **Page:** `/pages/IndiaInvestments.tsx`
- **Route:** `/india-investments`

### Backend
- **Module:** `/backend/app/modules/india_investments/`

### Data Model

Key tables:
- `india_mutual_funds` - MF holdings
- `india_fixed_deposits` - FD records
- `india_accounts` - NRE/NRO accounts
