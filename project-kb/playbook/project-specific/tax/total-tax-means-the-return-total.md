---
scope: project-specific
project: tax
category: other
applies-to: tax forecast totals, forecast-vs-actual comparisons, Tax Center hero numbers
created: 2026-09-12
source-context: "TY2025 reconciliation: the app's 104,646 'total tax' included 13,740 of payroll withholding that is on no return line"
---

# "Total Tax" Means Form 1040 Line 24 Plus Form 540 Line 64

Social Security and Medicare are withheld from wages and never appear as tax on the return. Show them as their own line, never inside the number that is compared to the return or used for estimated payments.

## Why
The TY2025 forecast reported 104,646; the return's federal plus California total was 58,998. Of the apparent 45,648 miss, 13,740 was payroll tax the app had folded in. Every comparison made with that total was overstated, and the safe-harbor math (110% of prior-year tax) was computed on a base the IRS does not use.

## How to apply
- `total_tax` = federal total tax after credits (incl. NIIT, AMT, other taxes) + state total tax after credits.
- Payroll taxes: separate field, labeled "withheld payroll taxes", informational.
- Safe harbor, refund/owe, and forecast-error percentages all use the return-defined total.
