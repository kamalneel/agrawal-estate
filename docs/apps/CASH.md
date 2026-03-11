# Cash & Banking App

## Goal

Track all cash holdings across checking accounts, savings accounts, money market funds, and CDs. Provide visibility into liquid assets and cash flow management.

---

## Features

### Current Features

1. **Account Aggregation**
   - Checking accounts
   - Savings accounts
   - Money market accounts
   - CDs (Certificates of Deposit)

2. **Balance Tracking**
   - Current balances
   - Historical balance trends
   - Interest earned

3. **Cash Flow**
   - Inflows and outflows
   - Transaction categorization
   - Monthly summaries

4. **Plaid Integration**
   - Automatic account linking
   - Real-time balance updates
   - Transaction sync

---

## Roadmap

- [ ] Cash flow forecasting
- [ ] Emergency fund tracking
- [ ] High-yield savings recommendations
- [ ] CD ladder management
- [ ] Bill payment tracking

---

## Architecture

### Frontend
- **Page:** `/pages/Cash.tsx`
- **Route:** `/cash`

### Backend
- **Module:** `/backend/app/modules/cash/`

### Data Model

Key tables:
- `cash_accounts` - Account records
- `cash_transactions` - Transaction history
- `plaid_connections` - Linked accounts
