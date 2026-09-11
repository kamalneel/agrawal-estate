---
scope: universal
project: null
category: process
applies-to: any monthly view of income or spending that contains fixed recurring lines (rent, school, insurance, salary, dividends)
created: 2026-09-06
source-context: "Spending page audit: rent had been missing for three months and nothing on the page said so."
---

# A Recurring Line That Vanishes Is a Data Defect Until Proven Otherwise

If a line has appeared every period for a long run (rent for 20 months),
a period without it is a data problem — a miscategorized row, a stale
export, a renamed account — not a real zero. Check for presence
mechanically and flag the gap on the headline, in red, before anyone
reads the total.

## Why

Rent went missing from the Spending page for June, July and August 2026.
The monthly total simply read lower, and lower looks like good news. The
gap was only found by an audit; the page had every fact it needed to raise
it on the first day.

The same shape recurs: dividends reading $0 because a statement was not
imported ([[check-freshness-and-ask-first]]), the rent card netting a
property cost ([[category-is-a-ledger-not-a-stream]]). In every case the
number was plausible and wrong, and the check that would have caught it is
"is the thing that is always there, there?"

## How to apply

- Keep an explicit list of expected lines (`EXPECTED_MONTHLY_LABELS`), each
  with a comment saying why it is on the list. Check complete periods only.
- **Know the cadence before adding a line.** School (Stratford) bills
  September through May; putting it on the list flagged every summer month.
  Insurance is quarterly. Only a line due every calendar period belongs.
- Attribute early payments to the period they are for (a rent wire on the
  31st is next month's), or the check fires falsely on both sides of the
  boundary. See [[attribute-income-to-its-stated-period]].
- Flag, do not fill. The detector says "no Home Rent in June"; it never
  invents a row. Whether the gap is real (a deposit covered the month) is
  the user's call, so the flag stays until they say so.
- Related: [[classify-by-rule-before-category-kind]] is usually the fix once
  the flag fires.
