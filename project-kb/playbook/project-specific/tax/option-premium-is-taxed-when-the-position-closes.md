---
scope: project-specific
project: tax
category: other
applies-to: tax forecast capital-gains estimate, Schedule D projection, quarterly estimated payments
created: 2026-09-12
source-context: "Reconciling the TY2025 forecast to the filed return: after removing data bugs, options still overstated Schedule D by ~15K"
---

# Option Premium Is Income When Collected, but Taxed When the Position Closes

The income definition counts premium the day it lands. The 1099-B counts it only when the contract is bought to close, expires, or is assigned — and an **assigned put's premium is not realized at all that year**: it lowers the basis of the shares and surfaces only when those shares are sold. The tax view must model that, not scale cash premium by a closure ratio.

## Why
TY2025: cash premium net of buy-backs was 88,405; the 1099s realized roughly 47,000 of option-related short-term gain. Count-based closure (BTC ÷ STO = 76%) predicted 66,991. Dollar realization was ~64% for Neel and ~38% for Jaya, because Jaya's December positions carried far more premium than her count share. A ratio of counts cannot see dollars or dates.

## How to apply
- Realize premium for tax in the year of BTC, OEXP, or call assignment.
- On put assignment, move the premium into the lot's *tax* basis (strike − premium) and realize it when the shares sell; the income view keeps strike basis per `definition-of-income`.
- Exclude positions still open at 12/31.
- Options on IBIT and other index-style ETFs are Section 1256: 60% long / 40% short regardless of holding period (Form 6781).
- Any "closure rate" in the forecast is a placeholder to be replaced, not tuned.
