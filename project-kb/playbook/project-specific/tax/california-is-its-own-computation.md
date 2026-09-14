---
scope: project-specific
project: tax
category: technical
applies-to: CA Form 540 forecast, state estimated payments
created: 2026-09-12
source-context: "TY2025 reconciliation: federal formulas reproduced the return to the dollar; California was off by 1,922 on identical AGI"
---

# California Is Its Own Computation, Not Federal With Different Brackets

Start from federal AGI, then apply California conformity differences, California's own standard deduction, the FTB rate schedule for the year, and exemption credits. Never feed federal AGI straight into a CA bracket table.

## Why
On the filed TY2025 return the app's CA estimate missed by 1,922 for four independent reasons: no HSA add-back (CA does not recognize HSAs: W-2 box 12W 6,802 is added to CA wages → +633), an estimated standard deduction (11,026 vs 11,412), a bracket table that was wrong for both 2024 and 2025 (20,139 vs 18,400 on the same taxable income), and missing exemption credits (2 × 153 + 475 per dependent = 781). CA also charged a 92 underpayment penalty where federal charged none.

## How to apply
- CA AGI = federal AGI + HSA contributions (employer and employee) + any other Schedule CA column C additions.
- Use the FTB "540 Tax Rate Schedules" for the tax year. 2025 Schedule Y (MFJ): 1% to 22,158; 2% to 52,528; 4% to 82,904; 6% to 115,084; 8% to 145,448; 9.3% to 742,958; 10.3% to 891,542; 11.3% to 1,000,000; 12.3% above; +1% MHST over 1,000,000. Standard deduction 11,412 MFJ. Verified: these reproduce the filed 18,400.
- Subtract exemption credits (personal 153 each, dependent 475 each in 2025); they phase out above the federal AGI threshold printed on Form 540 line 32.
- Estimate the FTB 5805 penalty separately from federal Form 2210; CA has its own safe-harbor math.
- Record the year's CA constants next to the federal ones and re-verify them against the first filed return that uses them.
