---
scope: universal
project: null
category: technical
applies-to: every parser that extracts rows from statements, PDFs, or reports
created: 2026-09-06
source-context: "Writing the Robinhood PDF statement importer; the check caught a real bug before any write."
---

# Validate a Parser Against the Source Document's Own Totals

Financial documents print their own summary. Extract the rows, sum them,
compare to the printed total, and **abort the import on a mismatch**. Never
write rows that disagree with the page they came from.

## Why

A row regex fails silently. It does not raise — it just returns fewer rows,
and the import "succeeds" while understating income by exactly the rows it
missed. Nothing downstream can detect this, because the missing money leaves
no trace.

Robinhood statements print an "Income and Expense Summary" per account. On
the first run of `import_robinhood_statement_pdf.py` the check reported six
mismatches. The extraction was right; the *validator* was wrong — it merged
July's and August's summaries per account and compared one month's stated
total against two months of rows. Either way the gate did its job: a bug
surfaced before a single row was written.

## How to apply

- Find the document's own control total (summary block, subtotal, "Total
  Funds Paid and Received"). Nearly every financial statement has one.
- Validate **per document and per account**, never merged across files — the
  same account appears in every month's statement.
- Abort, do not warn. A warning in a log is a silently wrong number.
- Where a known category sits outside the printed line (Robinhood reports
  GDBP outside "Interest Earned"), allow the specific asymmetry and say why
  in a comment — do not loosen the check globally.
- Print the comparison even when it passes; it is the cheapest evidence that
  an import was complete.
