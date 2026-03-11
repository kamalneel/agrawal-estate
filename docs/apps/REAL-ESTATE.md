# Real Estate App

## Goal

Track all real estate holdings including primary residence, rental properties, and investment properties. Monitor property values, mortgages, rental income, and property-related expenses.

---

## Features

### Current Features

1. **Property Tracking**
   - Property details and addresses
   - Purchase price and date
   - Current estimated value
   - Property type classification

2. **Mortgage Management**
   - Loan details and terms
   - Payment schedules
   - Interest rate tracking
   - Amortization schedules

3. **Rental Property Management**
   - Tenant information
   - Rental income tracking
   - Vacancy tracking
   - Lease terms

4. **Property Expenses**
   - Property taxes
   - Insurance
   - HOA fees
   - Maintenance costs

5. **Equity Tracking**
   - Home equity calculation
   - LTV (Loan-to-Value) ratios
   - Equity growth over time

---

## Roadmap

- [ ] Property value estimates via Zillow/Redfin API
- [ ] Rental yield analysis
- [ ] Cap rate calculations
- [ ] Refinance analysis tool
- [ ] Property comparison tools

---

## Architecture

### Frontend
- **Page:** `/pages/RealEstate.tsx`
- **Route:** `/real-estate`

### Backend
- **Module:** `/backend/app/modules/real_estate/`

### Data Model

Key tables:
- `properties` - Property records
- `mortgages` - Loan details
- `rental_leases` - Lease agreements
- `property_expenses` - Expense records
