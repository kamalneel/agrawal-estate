---
scope: universal
project: null
category: technical
applies-to: any query or service feeding a tax forecast or tax form
created: 2026-09-12
source-context: "TY2025 reconciliation: the shared lot engine fed 87,224 of IRA/401k stock gains into the tax forecast, 94% of a 92,673 AGI miss"
---

# Filter to Taxable Accounts at Every Source That Feeds a Tax Number

The tax module must apply its taxable-account filter at each query it consumes, including shared engines whose own definition deliberately includes every account. A docstring or a comment claiming "taxable only" is not a filter.

## Why
`definition-of-income` says retirement accounts count and "tax views filter *from* this definition." When the lot engine was promoted to shared (2026-07-04) the tax forecast kept calling `get_capital_gains_summary(year)` with no account argument. It silently absorbed 83,967 of `neel_retirement` and 3,257 of `jaya_ira` gains. The function's docstring said "Only includes transactions from TAXABLE brokerage accounts." The February grading had shown a 5.2% error; by September it was 54% and nobody noticed until the filed return arrived.

## How to apply
- Every tax-path call into a shared service passes an explicit account scope; shared services expose that parameter rather than assuming.
- Add a regression test per source: a sale, dividend, premium, or interest row in a retirement account must not change the forecast.
- When a shared engine's scope changes, grep for every consumer and re-run the last forecast-vs-return reconciliation as the acceptance check (`algorithm-upgrade-checklist`).
