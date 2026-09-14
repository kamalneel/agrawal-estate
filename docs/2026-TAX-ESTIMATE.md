# 2026 Tax Estimate — as of 2026-09-12

**Filers:** Neel Kamal & Jaya Agrawal, MFJ, California.
**Method:** the app's forecast (`GET /api/v1/tax/forecast/2026`) after the fixes from `2025-TAX-RETURN-RECONCILIATION.md`, plus full-year scenarios computed with the same rules. Validation: the same code re-run for 2025 now gives 61,210 federal + CA against the filed 58,998 (+3.7%; was +54%).
**Sources:** Neel's five AdamX paystubs (Jul 15 – Sep 15, ingested to `salary_payslips`), Robinhood transactions through 2026-09-11, rental records, `estimated_tax_payments`.

## 1. Tax already paid in 2026

| | Federal | California |
|---|---:|---:|
| Withheld from Neel's AdamX pay (YTD per 09/15 stub) | 9,015.18 | 4,198.28 |
| Estimated payments (Q1, paid 2026-05-01) | 1,700.00 | 550.00 |
| **Paid to date** | **10,715.18** | **4,748.28** |
| Also withheld, not income tax: Social Security 4,030.00, Medicare 942.50, CA SDI 845.00 | | |

Neel's stub at the $360K rate withholds 2,569.50 federal and 1,172.44 CA per semi-monthly period, with no 401(k), benefit, or post-tax deductions. Seven more pay dates remain (Sep 30 – Dec 31), so year-end withholding at the current W-4 will be about **27,002 federal / 12,405 CA**.

Jaya's DeWinter withholding is unknown: no stubs are ingested. Her wages are in the estimate at the stated rate (12,500/month from June), her withholding at zero, so "paid to date" and "still to pay" are both understated by whatever her employer has withheld.

## 2. Liability on income received so far (Jan 1 – Sep 12)

| | Amount |
|---|---:|
| Wages: Neel 65,000 (stubs) + Jaya 50,000 (rate, Jun–Sep) | 115,000 |
| Rental net of prorated depreciation | 26,776 |
| Options premium realized (100,231 net × 92% closure) | 92,530 |
| Stock lot gains, taxable accounts (ST −71,025, LT +31,394) | −39,631 |
| Dividends / interest | 2,428 / 0 (see §5) |
| **AGI** | **196,635** |
| Standard deduction 32,200 + QBI 5,355 | −37,555 |
| Federal tax (2026 brackets, LTCG stack), less child tax credit 2,200 | 22,054 |
| NIIT | 0 (AGI under 250,000 so far) |
| California (CA taxable 185,223, tax 10,103, less exemption credits 306) | 9,797 |
| **Federal + CA on income to date** | **31,851** |
| Paid to date | 15,463 |
| Uncovered so far | 16,387 |

## 3. Full-year scenarios

Assumptions: Neel 15,000 per period through Dec 31 (170,000 for the year); rental 75,600 rent, 21,185 expenses, 22,639 depreciation; options premium continues at the year-to-date pace; no further stock sales; dividends and interest at year-to-date pace. Same brackets, deductions, and CA rules as §2.

| | B. Jaya's wages excluded | C. Jaya 87,500 (Jun–Dec) |
|---|---:|---:|
| AGI | 299,605 | 387,105 |
| Federal tax after credits | 42,509 | 63,509 |
| NIIT | 1,885 | 4,925 |
| California | 20,637 | 28,774 |
| **Federal + CA** | **65,030** | **97,208** |
| Less Neel's year-end withholding + estimates paid (28,702 fed / 12,955 CA) | | |
| **Still to pay (fed / CA)** | 15,692 / 7,681 | 39,732 / 15,819 |

Scenario C is the realistic one; its "still to pay" drops by whatever DeWinter has withheld for Jaya.

Cliffs (playbook `magi-cliffs-drive-decisions`): scenario C crosses the NIIT threshold (250,000) by 137,000 and stays under the child-tax-credit phase-out (400,000) by 12,900 and the CA itemized-deduction limit (504,411). No clean-vehicle credit is at stake in 2026.

## 4. What to pay, and when

The penalty-proof floor is the prior-year safe harbor: **110% of 2025 tax = 45,416 federal, 19,381 California** (2025 AGI exceeded 150,000). Since both scenarios' liabilities exceed those floors, paying the floor avoids penalties and the balance is due 2027-04-15 without penalty.

Withholding is treated as paid evenly through the year (6,750 federal / 3,101 CA per quarter from Neel's projected 27,002 / 12,405).

| Federal (25% per quarter) | Required cumulative | Deemed paid (withholding + estimates) | Shortfall |
|---|---:|---:|---:|
| Q1 due 2026-04-15 | 11,354 | 8,450 | 2,904 |
| Q2 due 2026-06-15 | 22,708 | 15,200 | 7,508 |
| **Q3 due 2026-09-15** | 34,062 | 21,951 | **12,111** |
| Q4 due 2027-01-15 | 45,416 | 28,702 | 16,714 |

| California (30% / 40% / 0% / 30%) | Required cumulative | Deemed paid | Shortfall |
|---|---:|---:|---:|
| Q1 due 2026-04-15 | 5,814 | 3,651 | 2,163 |
| Q2 due 2026-06-15 | 13,567 | 6,753 | 6,814 |
| Q3 due 2026-09-15 | 13,567 | 9,854 | 3,713 |
| Q4 due 2027-01-15 | 19,381 | 12,955 | 6,426 |

Two ways to close the gap:

1. **Estimated payments:** federal 12,111 by 2026-09-15 and 4,603 by 2027-01-15; California 6,814 now and the remaining 6,426 by 2027-01-15 (or 13,240 now). Earlier-quarter shortfalls still accrue penalty up to the payment date (roughly 7% annualized, so a few hundred dollars).
2. **Raise W-4 withholding instead:** because withholding is deemed paid evenly across all four quarters, extra withholding of about **2,388 federal and 918 CA on each of the seven remaining paychecks** reaches the safe harbor and retroactively cures the Q1–Q3 shortfalls with no penalty at all. This is the cheaper route if AdamX can apply it from the Sep 30 pay date.

The 2025 return used the annualized-income method (Form 2210 Schedule AI) to eliminate the federal penalty; it will not help in 2026 because the first quarter already carried 102,717 of income.

## 5. Data still needed

- **Neel's June 2026 AdamX stubs** (06/15, 06/30): the rows exist gross-only from a screen paste, so the quarterly schedule attributes 653 of federal withholding to no month.
- **Jaya's DeWinter stubs** (June onward): her wages are estimated at the stated rate with zero withholding.
- **Robinhood 2026 activity CSVs** for both brokerage accounts: no dividend (CDIV) or interest (INT) rows exist for 2026; 2025 carried 7,717 of interest, so interest is almost certainly understated.
- Any 2026 HSA, 401(k), or IRA contributions for either spouse (Neel's stubs show none).
- Confirmation that no 2026 stock sales remain planned; the lot engine shows a 39,631 net taxable loss so far, which shelters part of the premium income.

## 6. Caveats carried from the 2025 reconciliation

- Options premium is realized on a count-based closure rate (92% today); the 1099 will realize only closed positions and defer assigned-put premium into share basis. Expect the final Schedule D to come in below the estimate, as it did in 2025.
- Federal constants are the IRS 2026 figures (Rev. Proc. 2025-32). California uses the 2025 FTB schedule, standard deduction, and exemption credits until the 2026 ones are published; that overstates CA slightly.
- Wash sales and Section 1256 (IBIT) treatment are not modeled.
