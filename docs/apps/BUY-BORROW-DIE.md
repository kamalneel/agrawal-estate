# Buy/Borrow/Die Strategy App

## Goal

Implement the "Buy, Borrow, Die" wealth strategy that minimizes taxes by holding appreciated assets, borrowing against them for liquidity, and passing them to heirs with a stepped-up cost basis.

---

## Features

### Current Features

1. **Asset Tracking**
   - Highly appreciated assets
   - Unrealized gains
   - Cost basis vs market value

2. **Borrowing Capacity**
   - Margin loan availability
   - Securities-backed lending
   - Interest rate tracking

3. **Tax Analysis**
   - Capital gains avoided
   - Interest deductibility
   - Estate tax implications

4. **Strategy Recommendations**
   - When to borrow vs sell
   - Asset selection for collateral
   - Rebalancing suggestions

5. **Expense Forecasting**
   - Large upcoming expenses
   - Cash needs projection
   - Borrowing recommendations

---

## Roadmap

- [ ] Interactive scenario modeling
- [ ] Estate value projections
- [ ] Tax savings calculator
- [ ] Generational wealth tracking

---

## Architecture

### Frontend
- **Page:** `/pages/BuyBorrowDie.tsx`
- **Route:** `/buy-borrow-die`

### Backend
- **Module:** `/backend/app/modules/strategies/`

### Data Model

Leverages data from investments, real estate, and tax modules.
