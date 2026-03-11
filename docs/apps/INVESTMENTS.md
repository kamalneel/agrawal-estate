# Investments App

## Goal

Aggregate and track all investment accounts across multiple brokerages. Provide portfolio analysis, performance tracking, and transaction history for informed investment decisions.

---

## Features

### Current Features

1. **Multi-Broker Aggregation**
   - Schwab accounts
   - Robinhood accounts
   - E*Trade accounts
   - Manual account tracking

2. **Portfolio Holdings**
   - Current positions with live pricing
   - Cost basis tracking
   - Gain/loss calculation
   - Sector allocation

3. **Transaction History**
   - Buy/sell transactions
   - Dividend reinvestments
   - Transfers between accounts
   - Corporate actions

4. **Performance Tracking**
   - Total return calculation
   - Time-weighted returns
   - Benchmark comparison

5. **Data Ingestion**
   - PDF statement parsing
   - CSV import
   - Manual entry

---

## Roadmap

- [ ] Real-time price streaming
- [ ] Rebalancing recommendations
- [ ] Tax-loss harvesting suggestions
- [ ] Asset correlation analysis
- [ ] Risk metrics (beta, volatility)

---

## Architecture

### Frontend
- **Page:** `/pages/Investments.tsx`
- **Route:** `/investments`

### Backend
- **Module:** `/backend/app/modules/investments/`

### Data Model

Key tables:
- `investment_accounts` - Account metadata
- `holdings` - Current positions
- `transactions` - Buy/sell history
- `price_history` - Historical prices
