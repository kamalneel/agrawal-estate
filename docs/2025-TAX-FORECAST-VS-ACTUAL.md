# 2025 Tax Forecast vs Actual — Analysis Report

**Date:** February 13, 2026
**Tax Year:** 2025
**Filing Status:** Married Filing Jointly
**Documents:** Jaya W-2 (Cisco), Neel 1099 (Robinhood), Jaya 1099 (Robinhood)

---

## 1. How the Forecast Works

The forecast pulls data from our database (transaction imports, W-2 records, rental records, retirement contributions) and calculates estimated tax using IRS brackets and rules. It runs year-round as transactions are imported.

**Income sources used by the forecast:**
- **W-2 wages** — From uploaded W-2 record
- **Options income** — Net STO/BTC premiums from Robinhood CSV imports
- **Dividends** — DIVIDEND transactions from Robinhood CSV imports
- **Interest** — INTEREST transactions from Robinhood CSV imports
- **Rental income** — From rental property records (manual entry)
- **Capital gains** — From cost basis tracker (stock lot sales)

**What are the "Actuals"?**
The actual numbers come from Robinhood's 1099 tax forms, which are the official IRS-reported figures. The 1099 is only available after year-end (typically mid-February).

---

## 2. Before & After Comparison

```
                               OLD Forecast NEW Forecast       Actual
                               (before fix)  (after fix)  (from 1099)
────────────────────────────── ──────────── ──────────── ────────────
  W-2 Wages                          $177,281     $177,281     $177,281
  Investment Gains                   $117,449      $77,220      $66,511
  Dividends                            $2,792       $2,792       $2,792
  Interest                             $7,709       $7,709       $7,717
  Other Income (1099-MISC)                 $0           $0         $465
  Rental (net of expenses)            $56,160      $56,160      $56,160
────────────────────────────── ──────────── ──────────── ────────────
  Less: Depreciation                 -$22,419     -$22,419     -$22,419
  Less: IRA Deduction                -$14,000           $0           $0
────────────────────────────── ──────────── ──────────── ────────────
  ADJUSTED GROSS INCOME              $324,973     $298,743     $288,507

  Federal Income Tax                  $56,127      $48,660      $45,779
  CA State Tax                        $21,909      $21,373      $20,422
  Social Security + Medicare          $13,740      $13,740      $13,740
  NIIT (3.8%)                          $2,849       $1,852       $1,463
────────────────────────────── ──────────── ──────────── ────────────
  TOTAL TAX                           $94,625      $85,626      $81,404

  Forecast Error:                   $13,221       $4,222
  Error Rate:                         16.2%         5.2%
```

**Payments already made:** Federal $63,184 | CA $23,062
**Result:** Federal REFUND $15,942 | CA REFUND $2,640 | **Total refund: $18,582**

---

## 3. Error Categorization

Total forecast error: **$13,221** overestimate → After bug fixes: **$4,222** (reduced by $8,999)

### Category A: BUGS (code errors — now fixed)

These are errors in the forecast code that have been **eliminated** by code fixes.

| Bug | Description | Tax Impact | Status |
|-----|-------------|-----------|--------|
| A1 | **Investment gains double-counting** | $14,925 | Fixed |
| A2 | **IRA deduction not phased out** | $5,194 | Fixed |
| A3 | **No preferential rates for LTCG/dividends** | $1,172 | Fixed |
| A4 | **CA used federal standard deduction** | $1,904 | Fixed |
| | **Total Category A** | **$8,999** | |

**A1. Investment gains double-counting** ($14,925)
The code added options income ($88K from STO/BTC premiums) AND stock lot capital gains ($29K) as separate AGI items, totaling $117K. But these partly overlap — when options are assigned, the gain appears in both trackers. Fix: combined into a single capital gains figure using a realization rate.

**A2. IRA deduction not phased out** ($5,194)
Deducted $14K (Neel $7K + Jaya $7K traditional IRA) without checking income limits. At this AGI, both are fully phased out (Jaya >$146K active participant limit, Neel >$246K spouse limit). This bug went the **other direction** — it made the forecast AGI too low by $14K, partially masking the $50K overcount from A1. Fix: added IRS phase-out rules per Publication 590-A.

**A3. No preferential tax rates** ($1,172)
Taxed qualified dividends ($2,783) and long-term gains ($10,229) at ordinary rates (24% marginal) instead of the preferential 15% rate. Fix: implemented 0%/15%/20% capital gains brackets.

**A4. CA standard deduction wrong** ($1,904)
Used the federal $31,500 standard deduction for California instead of the correct CA standard deduction (~$11,026 MFJ). This actually **understated** CA tax. Fix: created a separate CA taxable income calculation.

---

### Category B: OVERSIGHTS (tax rules we didn't account for)

These are conceptual gaps — tax rules or behaviors we didn't think about when designing the forecast. The biggest one (B1) is now partially addressed.

| Oversight | Description | AGI Impact | Status |
|-----------|-------------|-----------|--------|
| B1 | **Unrealized options positions** | ~$10,709 | Partially fixed |
| B2 | **Section 1256 contracts (IBIT)** | $3,322 | Not yet modeled |
| B3 | **Wash sale adjustments** | $2,028 | Not yet tracked |

**B1. Unrealized options positions** (~$10,709 remaining AGI gap)
When you sell a put (STO), the premium hits your account immediately. But the IRS doesn't tax it until the position **closes** (via BTC, expiration, or assignment). At year-end, ~109 of your 450 STO positions were still open — those premiums were in the forecast but NOT on the 1099.

The key insight: **money in your account ≠ taxable event.** The premium is yours to keep, but the tax obligation only crystallizes when the position resolves.

Fix: We now apply a "closure rate" (BTC count / STO count = 75.8%) to estimate realized gains. This reduced the error from ~$51K to ~$11K, but isn't perfect because some BTCs in 2025 actually close positions from 2024 (cross-year timing).

**B2. Section 1256 contracts** ($3,322)
IBIT options are "Section 1256 contracts" with a special 60% long-term / 40% short-term split regardless of holding period. Our system doesn't model this rule. Tax impact: ~$300 in savings not captured.

**B3. Wash sale adjustments** ($2,028)
Neel had $2,028 in wash sale disallowed losses. These adjust the cost basis of replacement shares rather than being currently deductible. Our cost basis tracker doesn't track wash sales across positions.

---

### Category C: DATA ISSUES (transaction data ≠ 1099 data)

These are **inherent limitations** of forecasting from transaction CSV data. They will **always exist** until the 1099 arrives, even in 2026 and beyond.

| Data Issue | Description | Amount |
|-----------|-------------|--------|
| C1 | **Income types not in CSV imports** | $465 |
| C2 | **Interest amount mismatch** | $8 |
| C3 | **Qualified vs ordinary dividend split** | Unknown |
| C4 | **Cross-year position timing** | ~$10,709 |

**C1. Income types not in transaction imports** ($465)
The 1099 includes income our CSV imports don't capture:
- ACAT Bonus Payment (1099-MISC): $464.95
- Gold Deposit Boost interest: part of Jaya's $5,163
- Security Lending Income Program: in Jaya's interest

These are Robinhood-specific income types that don't appear as standard transaction types in CSV exports.

**C2. Interest amount mismatch** ($8)
Forecast: $7,709 (from INTEREST transactions) vs Actual: $7,717 (from 1099-INT). Tiny gap from rounding or non-standard interest types.

**C3. Qualified vs. ordinary dividend split**
Our system tracks total dividends ($2,792) but not the qualified portion ($2,783). We assume all dividends are qualified (close enough — 99.7% were). The 1099 provides the exact split.

**C4. Cross-year position timing** (~$10,709)
Even with the closure rate fix, there's a ~$10K gap because some BTCs in 2025 close positions opened in 2024, inflating the closure rate estimate. This is the **largest remaining source of error** and the hardest to fix without building full position-level STO→BTC matching.

---

## 4. What This Means for 2026

| Category | 2025 Impact | 2026 Expectation |
|----------|-------------|------------------|
| **A. Bugs** | $8,999 | **$0** — All four bugs are fixed |
| **B. Oversights** | ~$10,709 AGI | **~$3-5K AGI** — Closure rate helps but isn't perfect |
| **C. Data Issues** | ~$473 AGI | **~$500 AGI** — Will always exist until 1099 arrives |

**Expected 2026 forecast accuracy:**
- Before these fixes: ~16% error
- After these fixes: ~5% error
- Irreducible floor: ~3-4% error (data limitations without 1099)

**To get below 3%:** Import the 1099 data as soon as it's available (usually mid-February) and use actual 1099 figures to replace estimates.
