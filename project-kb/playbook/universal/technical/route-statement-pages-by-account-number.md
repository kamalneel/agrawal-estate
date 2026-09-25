---
scope: universal
project: null
category: technical
applies-to: statement and document parsers, and any parser that intentionally returns nothing
created: 2026-09-25
source-context: "Robinhood statement PDFs turned out to be combined statements (brokerage, IRA, Roth, Agentic, Alisha's account in one file); three files were misjudged as the wrong account from page 1. The PDF parser had returned nothing on purpose since it was written, so no 2026 month-end ever landed."
---

# Route Statement Pages by Account Number, and Never Ship a No-Op Parser

A statement file is not an account. Parse every page, match each account
header's number to the app's account map, and skip unknown numbers with a
warning. Never infer the account from the filename or the first page.

A parser that deliberately returns nothing ("this source provides no
value") is a silent gap: files are accepted, logged as success, moved to
processed, and produce no rows. Either extract what the document
uniquely carries, or refuse the file loudly.

## Why

Robinhood's monthly PDF is one file per login, with each account on its own
run of pages: Neel's file opens with Alisha's account, then the Agentic
cash account, then the brokerage on page 15. Judged by page 1, three files
were "the wrong account"; parsed by page, they held exactly the brokerage
months the BBD page needed. Jaya's "Retirement" file carried her
Traditional IRA and her Roth.

`RobinhoodPDFParser.parse()` had returned an empty result with the note
"Robinhood PDFs provide no value" since it was written. Statements are the
only source of authoritative month-end value, cash and margin; that no-op
is why every 2026 month-end on the BBD page came from securities-only
daily rows.

## How to apply

- Keep an explicit `STATEMENT_ACCOUNTS` map (statement number → app
  account, owner, type). Untracked numbers are reported and skipped, never
  written under a guessed account.
- Validate each section against the document's own totals (securities +
  cash = portfolio value within $1) and reject the file on mismatch —
  see [[validate-parser-against-source-totals]].
- Log "N sections, M tracked, K skipped" per file so a combined statement
  with nothing tracked is visible in the ingestion log.
- If a parser exists only to skip a file type, delete it or make it fail
  the file with a clear reason; a success with zero records is the worst
  outcome.
