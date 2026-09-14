# 2025 Tax Return vs Forecast — Reconciliation to the Filed Return

**Date:** 2026-09-12
**Source of truth:** `data/tax-documents/2025/2025_Tax_Return_Filed_Diwakar_Taxes.pdf` (66 pp, filed 2026-02-19 by Diwakar Taxes, MFJ). Every number below was read from the return itself, not from the 1099s.
**Forecast:** `GET /api/v1/tax/forecast/2025` as computed by `backend/app/modules/tax/forecast.py` against the live database on 2026-09-12.
**Supersedes:** `docs/2025-TAX-FORECAST-VS-ACTUAL.md` (Feb 2026), which compared against the 1099s before the return existed and measured a 5.2% error. That error is now 54% — see §4 for why it regressed.

---

## 1. Bottom line

| | Filed return | App forecast (today) | Miss |
|---|---:|---:|---:|
| Adjusted gross income (1040 line 11) | 279,049 | 371,722 | +92,673 (+33%) |
| Taxable income (line 15) | 242,854 | 337,341 | +94,487 |
| Federal tax before credits (line 16) | 42,383 | 60,320 | +17,937 |
| Child tax credit (line 19) | 2,200 | 2,200 | 0 |
| Net investment income tax (Sch 2 line 12) | 1,104 | 4,625 | +3,521 |
| **Federal total tax (line 24)** | **41,287** | **62,745** | **+21,458** |
| CA tax (540 line 64) | 17,619 | 28,161 | +10,542 |
| CA underpayment penalty (540 line 113) | 92 | 0 | −92 |
| **Federal + CA** | **58,998** | **90,906** | **+31,908 (+54%)** |
| Payroll taxes (W-2 boxes 4+6, not on the return) | — | 13,740 | app adds these to "total tax" |

Payments and outcome on the return: federal paid 63,184 → refund 21,897; CA paid 23,062 → refund 5,351. The app knew the payments correctly (26,184 + 37,000 federal; 13,062 + 10,000 CA).

## 2. Line-by-line

| Return line | Filed | Forecast | Status |
|---|---:|---:|---|
| 1a W-2 wages (Jaya, Cisco) | 177,281 | 177,281 | exact |
| 1e Taxable dependent-care benefits (Form 2441) | 808 | 808 | exact |
| 2b Taxable interest | 7,717 | 7,709 | −8 (Gold boost / lending rows) |
| 3a / 3b Qualified / ordinary dividends | 2,783 / 2,792 | 2,792 / 2,792 | assumes all qualified; fine |
| 4a / 4b IRA distributions (backdoor Roth ×2, Form 8606) | 14,000 / 0 | not modeled | zero impact |
| 5a / 5b Pensions (401k rollovers 72,186 + 44,038) | 116,224 / 0 | not modeled | zero impact |
| 7a Capital gain (Schedule D line 16) | 66,510 | 168,725 | **+102,215** |
| ↳ Short-term (Sch D line 7) | 51,554 | 101,120 | includes 30,000+ from IRAs |
| ↳ Long-term (Sch D line 15) | 14,956 | 67,605 | includes 55,000+ from IRAs |
| ↳ Section 1256 (IBIT options, Form 6781, 60/40) | 3,322 | treated as ST | small |
| ↳ Wash sales disallowed (Neel) | 2,028 | not tracked | small |
| Sch 1 line 5 Rental (Schedule E line 26) | 23,476 | 14,406 | **−9,070** |
| ↳ Rents | 67,300 | 67,300 | exact |
| ↳ Expenses excl. depreciation | 21,185 | 30,475 | +9,290 (duplicates 7,090; fridge 2,200 capitalized) |
| ↳ Depreciation | 22,639 | 22,419 | −220 (new fridge, 5-yr) |
| Sch 1 line 8z Other income (Robinhood ACAT bonus) | 465 | 0 | −465 (exists as `ABIP` row, unmapped) |
| 10 Adjustments (IRA deduction after phase-out) | 0 | 0 | exact |
| 12e Standard deduction | 31,500 | 31,500 | exact |
| 13a QBI deduction (20% of rental) | 4,695 | 2,881 | follows rental miss |
| 16 Tax (QD&CG worksheet) | 42,383 | 60,320 | formula verified exact on return inputs |
| AMT (Form 6251) | 0 (TMT 33,761) | not modeled | 8,622 headroom |
| Form 8936 clean-vehicle credit | 7,500 transferred to dealer, no recapture (2025 MAGI < 300K) | not modeled | see §5 |
| CA AGI (540 line 17) | 285,851 | 371,722 | CA adds back HSA 6,802 |
| CA standard deduction | 11,412 | 11,026 | −386 |
| CA tax (540 line 31, before exemption credit) | 18,400 | 28,161 | brackets also wrong |
| CA exemption credits (2×153 + 475) | 781 | 0 | not modeled |

## 3. Waterfall — from the forecast to the return

Each row applies one fix and re-runs the app's own formulas.

| Step | AGI | Federal after credits | NIIT | CA (app formula) | Fed + CA |
|---|---:|---:|---:|---:|---:|
| App forecast today | 371,722 | 58,120 | 4,625 | 28,161 | 90,906 |
| 1. Drop retirement-account lot sales | 284,498 | 42,234 | 1,311 | 20,049 | 63,594 |
| 2. Dedupe rental expenses; fridge as 5-yr asset | 293,568 | 43,975 | 1,656 | 20,892 | 66,523 |
| 3. Add 465 ACAT bonus, +8 interest | 294,041 | 44,089 | 1,674 | 20,936 | 66,699 |
| 4. Options timing, 1256, wash (residual) | 279,049 | 40,182 | 1,104 | 19,542 | 60,828 |
| 5. CA-specific rules (HSA add-back, std ded, brackets, exemption) | 279,049 | 40,183 | 1,104 | 17,619 | 58,906 |
| Filed return | 279,049 | 40,183 | 1,104 | 17,619 | 58,906 |

Tax impact by cause: lot-engine leak −27,312; rental data +2,929; unmapped income +176; options timing −5,871; CA rules −1,922.

## 4. Root causes, classified

### A. Code regression (bug) — $87,224 of AGI, ~$27,300 of tax
`_calculate_capital_gains()` calls the shared `CostBasisService.get_capital_gains_summary(year)`, which has **no account filter**. 2025 lot sales in the table: `neel_retirement` 28,976 ST + 54,991 LT, `jaya_ira` 2,162 ST + 1,095 LT. Taxable accounts alone give 2,991 ST + 11,519 LT, and Neel's brokerage long-term proceeds (32,486) match the 1099-B to the dollar. The function's docstring says "Only includes transactions from TAXABLE brokerage accounts"; it did not.

Why it regressed: on 2026-07-04 the lot engine was promoted to shared for income unification, where the rule is "retirement accounts count" (`definition-of-income`). The tax module kept consuming it without adding the filter the income definition says tax views must apply. The Feb analysis was right at the time; the July change silently broke it.

### B. Data defect — rental expenses double-counted, −$9,070 of AGI
`rental_annual_expenses` for 2025 has two ingestion batches (2026-02-13 and 2026-02-20) with different category keys for the same facts: `auto_travel`/`auto_and_travel`, `cleaning_maintenance`/`cleaning_and_maintenance`, `legal_professional`/`legal_and_professional_fee`, `hoa`/`other`. That is 7,090 counted twice. Separately, the CPA capitalized the 2,200 refrigerator as 5-year property (220/yr) instead of expensing it as a repair (−1,980 vs our notes). Net: the app understated rental income by 9,070 and therefore QBI by 1,814.

### C. Data gap — income types present but unmapped, −$465
The 464.95 ACAT bonus is in `investment_transactions` as type `ABIP` (Jaya brokerage) but nothing routes it to Schedule 1 line 8z. `GDBP` (Gold deposit boost) and `SLIP` (stock lending) rows do reach interest.

### D. Assumption problem — option premium is taxed when the position closes, ~$15,000 of AGI
After fixing A–C the app still shows 81,501 of taxable capital gains against 66,510 on Schedule D. The app's income definition counts premium when collected (correct for *income*), then scales by a count-based closure rate (BTC count ÷ STO count = 75.8%). The 1099 realizes premium only on buy-to-close, expiry, or assignment, and for an **assigned put the premium is folded into the share basis** and is not realized until the shares are sold — possibly next year. Dollar realization implied by the 1099s: Neel ≈ 64%, Jaya ≈ 38%. A count ratio cannot see that Jaya's open December positions carried far more premium than Neel's. Smaller pieces of the same residual: Section 1256 60/40 split on IBIT (3,322), wash sales (2,028), and the 841 non-covered lot.

### E. Formula gaps — California only, −$1,922
Federal formulas are exact: on the return's inputs the app produces 42,382 tax (return 42,383), 4,695 QBI, 1,104 NIIT. California is not:
- CA does not recognize HSAs: employer HSA contributions (W-2 box 12 code W, 6,802) are added back → CA AGI 285,851. App uses federal AGI. (+633 tax)
- 2025 CA standard deduction is 11,412, app estimated 11,026. (−36)
- App's CA brackets are wrong for both 2024 and 2025 — on the return's CA taxable income they give 20,139 vs 18,400. The FTB 2025 Schedule Y (MFJ) that reproduces 18,400 exactly: 1% to 22,158; 2% to 52,528; 4% to 82,904; 6% to 115,084; 8% to 145,448; 9.3% to 742,958; 10.3% to 891,542; 11.3% to 1,000,000; 12.3% above (plus 1% MHST over 1M). (−1,739)
- Exemption credits 2×153 + 475 per dependent = 781 not applied. (−781)
- CA underpayment penalty 92 (FTB 5805) not estimated; federal 2210 penalty was 0 because the annualized-income method (Schedule AI) was used.

### F. Definition mismatch — "total tax"
The app adds Social Security + Medicare (13,740) to total tax. Those are withheld payroll taxes and appear nowhere on the return's tax lines. Comparing 104,646 to 58,998 overstates the miss; the like-for-like miss is 31,908.

### G. Not modeled, zero tax impact this year, still worth knowing
- Two 401(k) rollovers (116,224) and two backdoor Roth conversions (14,000) show as gross distributions with 0 taxable (codes G / 2 + Form 8606). A parser that reads 1099-R box 1 as income would add 130K of phantom income.
- The 7,500 clean-vehicle credit was transferred to the dealer. It survives only because 2025 MAGI (279,049) is under the 300,000 MFJ cap (2024 was 489,982, so the "either year" test hinged on 2025). Had the forecast's 371,722 been right, the credit would have been recaptured on Schedule 2 line 1b.
- AMT was 8,622 away from binding.

## 5. Data problem or assumption problem?

| Cause | Kind | Share of the 92,673 AGI miss |
|---|---|---:|
| A. Lot engine includes IRA/401k sales | code bug (regression) | 94% |
| B. Rental expense duplicates + fridge | data defect (+ CPA judgment) | −10% |
| D. Option premium timing, 1256, wash | assumption / model | 16% |
| C. Unmapped income rows, interest | data mapping | −1% |
| E. CA rules | formula (state only) | 0% of AGI, 1,922 of tax |

The forecast machinery itself is sound at the federal level. Almost the entire miss is *inputs*: one query leaking non-taxable accounts, one duplicated ledger, and one income definition (cash premium) used where the tax definition (closed premium) belongs.

## 6. Fixes, in priority order

*Status 2026-09-12 (later the same day):* 1, 3, 4, 6 applied (commits e085258 / 44d6231 plus the California, other-income and 2026-constant changes); the forecast re-run for 2025 now gives 61,210 vs the filed 58,998 (+3.7%). Still open: 2 (rental expense dedupe), 5 (position-level premium realization), 7 (1256 / wash sales), 8 (1099-R ingestion). Paystub withholding now feeds open years via `salary_payslips` (`scripts/ingest_paystubs.py`).

1. **Filter the lot engine to taxable accounts in the tax path.** `backend/app/modules/tax/forecast.py` `_calculate_capital_gains()` → pass an account allow-list (or `is_taxable`) into `CostBasisService.get_realized_gains()` (`backend/app/shared/services/cost_basis_service.py:231`). Add a test that a sale in `neel_retirement` never reaches the forecast.
2. **Normalize rental expense category keys and upsert.** Re-ingest 2025 rental expenses so one canonical key per Schedule E line survives (no direct DB edits — fix the ingester per `no-direct-db-modifications`). Validate against the return's Two-Year Comparison worksheet totals (2024: 22,863; 2025: 21,185).
3. **Map Robinhood income types to return lines.** `ABIP` → Sch 1 8z; keep `GDBP`, `SLIP`, `INT` → 2b; `CDIV` → 3b.
4. **California module.** HSA add-back from W-2 box 12W, 2025 standard deduction 11,412, FTB Schedule Y brackets above, exemption credits, and an estimate of the FTB 5805 penalty.
5. **Position-level premium realization for the tax view.** Realize on BTC / OEXP / call OASGN in the year they occur; on put OASGN, defer the premium into the lot's tax basis (strike − premium) while the income view keeps strike basis. Exclude positions open at 12/31. Needs `sold_options` to carry account and open date (today it has neither).
6. **Report payroll taxes as a separate line**, never inside the return total.
7. **Section 1256 and wash sales.** Tag IBIT (and any ETF-on-index) options as 1256 with 60/40; `StockLotSale.wash_sale` already exists, populate it from the 1099-B "W" rows.
8. **Ingest the 1099-R correctly.** Box 1 gross with code G or a Form 8606 conversion → taxable 0.

## 7. What the return also tells us for 2026 planning

- Distance to cliffs at 2025 AGI 279,049: NIIT threshold 250,000 (already over by 29,049); EV-credit MAGI 300,000 (20,951 headroom); child tax credit phase-out 400,000; CA itemized-deduction limitation 504,411.
- Estimated payments: the annualized method (Form 2210 Schedule AI) eliminated the federal penalty because income was back-loaded; CA still charged 92. The app's quarterly schedule should offer the annualized method.
- Both spouses did backdoor Roths; the deductible-IRA question is moot at this income (both phased out) and the app's `retirement_contributions` rows should record them as non-deductible + conversion, not as a 7,000 IRA and a 7,000 Roth each.
