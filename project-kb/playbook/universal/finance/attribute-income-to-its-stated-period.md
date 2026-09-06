---
scope: universal
project: null
category: other
applies-to: monthly income attribution, rent, any recurring payment whose source names the period it covers
created: 2026-09-06
source-context: "July 2026 showed $12,800 of rent and August $1,453; the lease was $6,400/mo the whole time."
---

# Attribute Income to the Period It Is For, Not the Day It Landed

When the source document states which period a payment covers, count it in
that period. Bucketing by receipt date is only correct when the source is
silent.

## Why

The tenant pays a month ahead, in two Zelle transfers that straddle month
ends. On receipt-date basis, July 2026 held July's rent *and* August's
($12,800) while August held September's. Every month was wrong; two happened
to look plausible.

Every one of those transfers named its month in the memo — "August rent pt
1", "Sept rent pt2". The data to fix it was already there, unread.

Attribution also revealed a fact recollection had wrong: once each payment
sat in its own month, every month landed exactly on the signed lease rate
($6,220 through Mar 2026, $6,400 from Apr 2026), which corrected both a
hand-maintained schedule table and everyone's memory of "$6,300".

## How to apply

- Parse the stated period from the memo/description; fall back to receipt
  date only when it is absent.
- The memo names a month but rarely a year — pick the year that puts the
  named month **nearest the payment date** ("Jan rent" paid 2025-12-29 is
  January 2026).
- For payments split into parts, let a part with no stated period inherit
  from its nearest dated sibling within a few days.
- Do NOT attribute at a granularity finer than the thing being attributed:
  a month's rent has no meaningful week, so weekly views stay on receipt
  date and answer "what landed this week".
- Reconciling to the contract (lease, offer letter, invoice) is the test
  that attribution worked. See
  [[category-is-a-ledger-not-a-stream]] for the composition half.
