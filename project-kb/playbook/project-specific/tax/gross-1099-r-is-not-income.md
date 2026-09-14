---
scope: project-specific
project: tax
category: technical
applies-to: 1099-R ingestion, actual-tax items, forecast income sources
created: 2026-09-12
source-context: "TY2025 return: 116,224 of 401(k) rollovers and 14,000 of backdoor Roth conversions appear as gross distributions with 0 taxable"
---

# A 1099-R Gross Distribution Is Not Income Until the Code Says So

Ingest box 1 (gross), box 2a (taxable), box 7 (code), and the Form 8606 basis together. Only the taxable amount after the code and 8606 reaches the forecast.

## Why
The TY2025 return carries 130,224 of 1099-R gross distributions and 0 of taxable income: two 401(k)-to-IRA rollovers (code G) and two 7,000 nondeductible-IRA-to-Roth conversions (code 2, basis 7,000 on Form 8606 → taxable 0). A parser that sums box 1 would add 130K of phantom AGI, crossing every cliff in `magi-cliffs-drive-decisions`.

## How to apply
- Code G / H → rollover, taxable 0.
- Code 2 / 7 with a same-year nondeductible contribution → conversion; taxable = amount − 8606 basis (pro-rata across all traditional IRAs, so keep `ira_fmv` at 12/31 populated).
- Record backdoor Roths in `retirement_contributions` as a nondeductible traditional contribution plus a conversion, not as both an IRA and a Roth contribution.
