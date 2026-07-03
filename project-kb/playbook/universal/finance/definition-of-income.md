---
scope: universal
project: null
category: other
applies-to: all income calculations, summaries, dashboards, and reports
created: 2026-07-03
source-context: "Income unification design discussion — Neel defined income for the app's north-star objectives; see docs/INCOME-UNIFICATION-SPEC.md"
---

# Definition of Income

Income is **realized money events only**, fixed + dynamic, across **all
accounts**, with an identical definition regardless of tax treatment.

- **Fixed**: salary, rent.
- **Dynamic**: options premium, dividends, interest, stock lending, and
  realized stock-sale P/L (positive or negative).
- **Holding a stock is never income.** Unrealized gains/losses don't count.
- **Call assignment** is income at the moment shares are called away — it is
  a forced sale, realized through the lot engine and categorized as
  **equity-sale income exactly like a normal stock sale**, never as options
  income. The call's premium remains options income (counted at collection).
- **Put assignment** is NOT income — it creates a lot at **strike-price
  basis** (not tax basis of strike − premium, because premium was already
  counted as income when collected; using tax basis would double-count).
- **Retirement accounts count.** A sale in an IRA is income even with no tax
  consequence. Taxable-only filtering belongs to the tax module exclusively.

## Why

Neel's stated objective (2026-07-03): one place answering "what did I earn
this week / month / year across all sources." Prior code conflated income
with gross sale proceeds and silently excluded salary, stock sales, lending,
and all retirement-account P/L.

## How to apply

Any time code sums, displays, or forecasts "income": include all sources and
all accounts, use realized P/L (never proceeds) for stock sales, respect the
strike-basis rule for assigned lots, and never fork the definition based on
tax status. Tax views filter *from* this definition; they don't redefine it.
