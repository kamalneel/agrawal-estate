---
scope: universal
project: null
category: design
applies-to: any UI surface, report, or notification that lists the family's accounts
created: 2026-07-05
source-context: "Income page redesign — Neel: 'it looks like you are organizing accounts in different ways. The hierarchy goes like this: …'"
---

# Canonical Account Hierarchy

Whenever accounts are listed, always use this fixed order — never sort
accounts by amount, alphabet, or anything else:

1. Neel's Brokerage (Investment)
2. Neel's Retirement (IRA)
3. Neel's Roth IRA
4. Jaya's Brokerage (Investment)
5. Jaya's IRA
6. Jaya's Roth IRA
7. Alisha's Brokerage
8. Agrawal Family HSA

## Why

Neel scans account lists positionally; different orderings on different
screens (by income, worst-first, alphabetical) force re-reading. Stated
explicitly 2026-07-05.

## How to apply

- Backend: `ACCOUNT_ORDER` in `app/modules/investments/services.py`
  (by account_id) — already canonical.
- Frontend: `accountRank` / `sortByAccountRank` in
  `frontend/src/lib/accountOrder.ts` (by account name) — use it for every
  new account listing; do not write ad-hoc sorts.
- Within grouped views (e.g., taxable vs sheltered), keep this order
  inside each group.
