# Spending Categorization Principles

Living document for classifying Monarch Money categories into spending tiers.

## Three-Tier Classification

| Tier | Treatment | Examples |
|------|-----------|---------|
| **EXCLUDED** | Not spending at all; filtered out of all views | Transfers, paychecks, credit card payments |
| **NON_MONTHLY** | Included in total spending, charts, and tables but excluded from "Avg Monthly" calculation | Taxes, insurance, annual travel |
| **MONTHLY** | Recurring monthly expenses; included in everything including Avg Monthly | Groceries, rent, utilities |

## Rules for Classifying New Categories

1. **Is it income, a transfer, or a non-expense?** &rarr; EXCLUDED
2. **Does it occur once a year or less, or is it a large one-time expense?** &rarr; NON_MONTHLY
3. **Everything else** &rarr; MONTHLY (default)

When in doubt, classify as MONTHLY. Reclassify only if it demonstrably distorts the monthly average.

## Full Category Table

### EXCLUDED (not spending)
Defined in `models.py :: EXCLUDED_CATEGORIES`

| Category | Reason |
|----------|--------|
| Transfer | Internal money movement |
| Credit Card Payment | Debt repayment, not spending |
| Paychecks | Income |
| Interest | Income |
| Loan from Neel's Investment | Internal transfer |
| Other Income | Income |
| Balance Adjustments | Not real spending |
| Investment | Not spending |
| Jaya's Salary | Income |
| Loan Repayment | Debt, not spending |
| Tesla's loan payment | Debt payment |

### NON_MONTHLY (annual / one-time)
Defined in `models.py :: NON_MONTHLY_CATEGORIES`

| Category | Reason |
|----------|--------|
| Taxes | Annual estimated/quarterly tax payments |
| Insurance | Annual or semi-annual premiums |
| Travel & Vacation | Lumpy, trip-based spending |
| ANNUAL EXPENSES | Explicitly tagged annual |
| ONE TIME | Explicitly tagged one-time |
| AdamX Work Trip - Vegas | Trip tag, one-time |
| Bali trip | Trip tag, one-time |
| Europe Trip 2025 | Trip tag, one-time |
| India Trip 2024 | Trip tag, one-time |

### MONTHLY (recurring)
All other categories default to MONTHLY.

| Category | Notes |
|----------|-------|
| Auto Maintenance | |
| Auto Payment | |
| Cash & ATM | |
| Charity | |
| Child Activities | |
| Child Incentive | |
| Clothing | |
| Coffee Shops | |
| Dentist | |
| Education | |
| Electronics | |
| Entertainment & Recreation | |
| Financial & Legal Services | |
| Financial Fees | |
| Fitness | |
| Furniture & Housewares | |
| Gas | |
| Gas & Electric | Utility |
| Gifts | |
| Groceries | |
| Home Improvement | |
| Internet & Cable | Utility |
| Medical | |
| Miscellaneous | |
| News | Subscription |
| Parking & Tolls | |
| Personal | |
| Pets | |
| Phone | Utility |
| Public Transit | |
| Rent | |
| Restaurants & Bars | |
| Shopping | |
| Software | Subscription |
| Taxi & Ride Shares | |
| Uncategorized | |

### Additional MONTHLY categories (from 2025 CSV custom tags)

| Category | Notes |
|----------|-------|
| AI Tools | Subscription software |
| Adamx | Business expense |
| Jaya Personal Expense | |
| Jaya's Education | |
| Joann Riggio | Payee-as-category |
| 303 Hartstene Dr | Property expense |

## Trip-Based Classification

In addition to category-based classification, spending can be classified by **date range** using the `TRIPS` list in `models.py`. ALL spending within a trip's date range is treated as non-monthly, regardless of Monarch category (e.g., dog sitter, restaurants, gas during a trip).

To add a new trip, tell Claude the dates and destination:
> "March 14-28, Bali"

This gets added to `models.py :: TRIPS` as:
```python
{"name": "Bali Trip", "start": date(2025, 3, 14), "end": date(2025, 3, 28)}
```

### Current Trips

| Trip | Start | End |
|------|-------|-----|
| Vegas NYE 2025 | 2025-12-28 | 2026-01-01 |

### Priority Rules
- Trip date range takes priority over category classification
- A "Groceries" transaction during a trip counts toward the trip, not monthly groceries
- NON_MONTHLY categories still apply for transactions outside any trip date range

## Changelog

| Date | Change |
|------|--------|
| 2026-02-06 | Initial categorization. Created three-tier system. EXCLUDED: 11 categories. NON_MONTHLY: 9 categories. All others default to MONTHLY. Added 2025 CSV custom categories to appropriate tiers. |
| 2026-02-06 | Added trip-based date-range classification. Vegas NYE 2025 (Dec 28 - Jan 1). Annual expenses breakdown in summary API and frontend. |
