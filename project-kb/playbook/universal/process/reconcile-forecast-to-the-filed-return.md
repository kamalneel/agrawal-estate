---
scope: universal
project: null
category: process
applies-to: any forecast that is eventually graded by an authoritative document (tax return, audited statement, closing statement)
created: 2026-09-12
source-context: "TY2025: the 1099-based grading in February said 5.2%; the filed return in September said 54%, with the causes split across code, data, assumptions and formulas"
---

# Reconcile the Forecast to the Filed Document Line by Line, and Classify Every Gap

When the authoritative document arrives, build a line-by-line table (document line, filed value, forecast value), then a waterfall that applies one fix at a time and re-runs the model's own formulas, and tag each gap as one of: **code bug**, **data defect**, **data gap** (fact exists but unmapped), **assumption**, **formula**, **definition mismatch**, **not modeled / zero impact**. Test the formulas on the document's own inputs first; if they reproduce the document, the miss is entirely inputs.

## Why
Grading against an intermediate source (the 1099s) missed a regression that only the return exposed. Grading only the headline number hides offsetting errors: in TY2025 an 87K overstatement and a 9K understatement partly cancelled, and a 13,740 definition mismatch (payroll tax in "total tax") inflated the apparent miss. The classification is what turns a grade into fixes: bugs get tests, data defects get ingestion fixes, assumptions get model changes, formulas get constants.

## How to apply
1. Extract the document to text and verify a few lines against the page images.
2. Table every line the forecast claims to model, plus every line the document has that the forecast does not.
3. Run the model's formulas on the document's inputs (taxable income, preferential income, thresholds) — federal tax, QBI, NIIT, state — and record exact/inexact.
4. Waterfall from the forecast to the document, one cause per step, reporting the dependent totals at each step.
5. Write the classified root-cause list with the file/function for each fix, then update the playbook and the document inventory.
6. Store the grading under `docs/<YEAR>-TAX-RETURN-RECONCILIATION.md` and link it from the playbook README.
