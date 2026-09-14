---
scope: universal
project: null
category: technical
applies-to: any ledger keyed by a free-text category (rental expenses, spending categories, transaction types)
created: 2026-09-12
source-context: "TY2025 rental expenses: two ingestion batches wrote auto_travel and auto_and_travel, hoa and other, etc.; 7,090 was counted twice"
---

# The Same Fact Under Two Spellings Is a Duplicate

Category keys must be normalized to one canonical key before rows are inserted or summed, and an ingester must upsert on (entity, period, canonical key), not append.

## Why
`rental_annual_expenses` for 2025 was written on 2026-02-13 (`auto_travel`, `cleaning_maintenance`, `legal_professional`, `hoa`) and again on 2026-02-20 (`auto_and_travel`, `cleaning_and_maintenance`, `legal_and_professional_fee`, `other`). Every summary added both. Rental net income fell from 23,476 to 14,406 in the forecast, the QBI deduction followed, and nothing flagged it because each row was individually valid.

## How to apply
- Define the canonical key list per ledger (for Schedule E: the IRS line names) and map every incoming spelling to it in one function.
- Ingest with upsert semantics per canonical key; a second file for the same period replaces, not appends.
- Validate against the source document's printed total (`validate-parser-against-source-totals`); a total that exceeds the document's is the tell.
