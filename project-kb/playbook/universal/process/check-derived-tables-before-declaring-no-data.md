---
scope: universal
project: null
category: process
applies-to: any report or answer that says a period, account or stream has no data
created: 2026-09-25
source-context: "Jaya's growth report said '2024 salary not on file' while the IRS wage transcripts had been parsed into w2_records nine months earlier; Neel: 'I thought you had the tax document for 2024'"
---

# Check Derived Tables and the Inbox Before Declaring "No Data"

Before writing "not on file" or "no data for 2024", look past the
transaction feeds: the derived tables (`w2_records`, `income_tax_returns`,
`margin_monthly_balances`, `stock_lot_sale`), the tax inbox, and the
processed-files folders. A feed that starts in 2025 does not mean the
system knows nothing about 2024.

## Why

The 2024 salary "gap" was answered by `w2_records` (both 2024 W-2s, with
401(k) and Roth 401(k) boxes) populated from the IRS transcripts in
December 2025. The Chase feed the report was built from simply starts in
January 2025. The user knew the document existed; the report said it did
not.

The same shape recurred in the BBD audit: statement values for Jan–Apr
2026 existed in `margin_monthly_balances` while `portfolio_snapshots` had
none, and the Robinhood PDFs on disk were combined statements whose
useful account sat on page 15, not page 1.

## How to apply

- Enumerate the sources per stream: feed tables, derived tables, document
  folders (`data/inbox`, `data/processed`, `data/tax-documents`), and the
  ingestion log (`ingestion_log.file_name`). Query them before writing the
  sentence.
- When a document is multi-part (combined statements, transcripts), check
  every page or section before calling it the wrong account.
- Say what was checked: "not in the Chase feed, the W-2 table or the tax
  inbox" is a claim; "not on file" is a guess.
