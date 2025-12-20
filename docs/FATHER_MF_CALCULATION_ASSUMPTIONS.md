# Father's Mutual Fund - Calculation Assumptions

## Document Purpose
This document records all assumptions made when estimating values for Father's (Nagendra Prasad Agrawal) mutual fund holdings. These assumptions were provided by Neel or derived from available data.

**Last Updated:** December 16, 2025  
**Documented as:** Neel's Instructions for Calculation

---

## Data Sources

### Primary Source: Portfolio Summary PDF
- **File:** `portfolio_summary_report_1764922988213.pdf`
- **Generated On:** December 5, 2025
- **MFD Name:** Abhay Kumar
- **Contains:** 12 mutual fund schemes with official names, folio numbers, investment amounts, current values, and XIRR

### Secondary Source: Handwritten Notes (Original)
- Father's handwritten notes with fund names (informal/abbreviated)
- Some discrepancies found between handwritten notes and PDF

---

## Calculation Assumptions

### 1. Franklin Focused Equity Fund - Current Value Estimation

**Data Available:**
- Initial Investment: ₹52,000
- Investment Date: March 6, 2019
- March 2025 Value: ₹1,30,327 (from database)

**Calculation Method:**
- Calculated CAGR from actual data points
- CAGR = ((130,327 / 52,000) ^ (1/6.07)) - 1 = **16.34% per year**
- Applied CAGR to estimate current value (Dec 2025)

**Result:**
- Estimated Current Value: **₹1,44,433**

**Neel's Instruction:** Use the growth rate derived from actual data (investment to March 2025) and assume constant growth rate to estimate current value.

---

### 2. DSP Aggressive Hybrid Fund - Value Estimation

**Data Available:**
- Initial Investment: ₹5,00,000
- Investment Date: March 6, 2019
- No current value or March 2025 value available

**Calculation Method:**
- Used category average CAGR for Aggressive Hybrid Funds
- Assumed CAGR: **12% per year** (conservative estimate for hybrid funds, typical range 10-14%)
- Time to March 2025: ~6 years
- Time to Dec 2025: ~6.75 years

**Results:**
- March 2025 Value: ₹5,00,000 × (1.12)^6 = **₹9,86,918**
- Current Value (Dec 2025): ₹5,00,000 × (1.12)^6.75 = **₹10,84,472**

**Neel's Instruction:** Since specific fund performance data was not available online, use category average CAGR of 12% for hybrid funds.

---

### 3. Reliance - Value Estimation

**Data Available:**
- Initial Investment: ₹9,48,758
- Investment Date: August 13, 2020
- No current value or March 2025 value available
- Assumed to be Reliance Industries stock (not a mutual fund)

**Calculation Method:**
- Reliance Industries stock has grown approximately 50-60% since August 2020
- Used **55% total growth** from Aug 2020 to Dec 2025
- For March 2025 (earlier date), used **45% growth**

**Results:**
- March 2025 Value: ₹9,48,758 × 1.45 = **₹13,75,699**
- Current Value (Dec 2025): ₹9,48,758 × 1.55 = **₹14,70,575**

**Neel's Instruction:** Estimate based on approximate stock price growth of Reliance Industries from Aug 2020 to present.

---

### 4. Funds Invested AFTER March 2025 - March 2025 Value

**Applicable Funds:**
- DSP Flexi Cap Quality 30 Index Fund (Invested: Aug 12, 2025)
- Edelweiss Balanced Advantage Fund (G) (Invested: Aug 13, 2025)
- Invesco Indian Business Cycle Fund (Invested: Aug 18, 2025)
- HSBC Aggressive Hybrid Fund (G) (Invested: Nov 30, 2025)
- Elelwise Multi Asset Omni Fund (Invested: Dec 2, 2025)

**Logic:**
These funds did not exist in March 2025 (invested after that date). However, for reporting parity and total consistency:

**Neel's Instruction:** Set March 2025 value equal to the Initial Investment amount for funds invested after March 2025. This ensures the totals are consistent across time periods, even though technically these funds didn't exist in March 2025.

**Results:**
- All 5 funds: March 2025 Value = Initial Investment = ₹5,00,000 each

---

### 5. Linear Interpolation for March 2025 Values (PDF Funds)

**Method Used:**
For the 12 funds from the PDF that were invested before March 2025, we calculated March 2025 values using linear interpolation:

1. Calculate total growth from investment date to PDF date (Dec 4, 2025)
2. Calculate daily growth rate
3. Apply daily growth rate to estimate value at March 31, 2025

**Formula:**
```
Daily Growth = (Current Value - Initial Investment) / Days from Investment to PDF Date
March 2025 Value = Initial Investment + (Daily Growth × Days from Investment to March 31, 2025)
```

**Neel's Instruction:** Use linear interpolation from known data points to estimate March 2025 values.

---

## Summary of Estimated Values

| Fund | Method | March 2025 (Est) | Current (Est) |
|------|--------|------------------|---------------|
| Franklin Focused Equity Fund | CAGR from actual data | ₹1,30,327 (actual) | ₹1,44,433 |
| DSP Aggressive Hybrid Fund | 12% CAGR assumption | ₹9,86,918 | ₹10,84,472 |
| Reliance | 55% stock growth assumption | ₹13,75,699 | ₹14,70,575 |
| Post-March 2025 funds (5 total) | Initial = March 2025 | ₹5,00,000 each | From PDF or TBD |

---

## Notes

1. All estimates are approximations based on category averages or assumed growth rates
2. Actual values may differ - these should be updated when actual statements are available
3. For tax or legal purposes, always use official statements from fund houses
4. The "Reliance" entry needs clarification - is it Reliance Industries stock or a Reliance MF scheme?

---

### 6. Invesco Indian Business Cycle Fund - Current Value

**Data Available:**
- Initial Investment: ₹5,00,000
- Investment Date: August 17, 2025
- March 2025: ₹5,00,000 (set to initial per Rule #4)

**Result:**
- Current Value: **₹5,16,397** (as displayed on India Investments page)

**Note:** This value appears to be calculated/fetched from the frontend. Represents ~3.3% growth since Aug 2025.

---

### 7. DSP Flexi Cap Quality 30 Index Fund - Current Value

**Data Available:**
- Initial Investment: ₹5,00,000
- Investment Date: August 12, 2025

**Neel's Instruction:** Set Current = Initial Investment for this recent investment (only ~4 months old).

**Result:**
- Current Value: **₹5,00,000**

---

### 8. Elelwise Multi Asset Omni Fund - Current Value

**Data Available:**
- Initial Investment: ₹5,00,000
- Investment Date: December 2, 2025

**Neel's Instruction:** "It's only been a month since the investment. So I would like the current to be the same as the initial investment amount."

**Result:**
- Current Value: **₹5,00,000**

---

## Final Portfolio Summary

| Metric | Value |
|--------|-------|
| Total Holdings | 21 |
| Total Invested | ₹1,36,10,445 |
| March 2025 Value | ₹2,32,47,363 |
| Current Value | ₹2,44,84,036 |
| Growth (Invested → March 2025) | 70.8% |
| Growth (Invested → Current) | 79.9% |

---

## Revision History

| Date | Changes | By |
|------|---------|-----|
| Dec 16, 2025 | Initial documentation of calculation assumptions | Neel |
| Dec 16, 2025 | Added assumptions for Invesco, DSP Flexi Cap, Elelwise funds | Neel |

