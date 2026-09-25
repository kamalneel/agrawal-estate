---
scope: universal
project: null
category: process
applies-to: any suspected data gap, and any request to the user for files or exports
created: 2026-09-25
source-context: "BBD audit F6: zero options rows in Mar–Apr 2025 looked like a missing import; Neel recalled 'a lot of option activity' — for Feb–Mar 2026, not 2025. Robinhood's realized-trade record and its own export both showed no trades."
---

# Verify a Suspected Gap Against the Source's Own Record Before Asking

A zero in the ledger is a hypothesis, not a finding. Before asking for an
export, check the source's own account of the period: the broker's
realized-trade record through the connection, the archived export that
covered the window, and the pages in the app that read the same ledger.
If they agree with the zero, the gap is real activity, not missing data,
and the ask is withdrawn.

## Why

Neel's brokerage showed no options in March and April 2025 while other
rows existed, which is exactly what a failed import looks like. Neel
confirmed heavy activity. Three checks said otherwise: Robinhood's
archived activity export for the period had two expirations and no new
sales; Robinhood's realized-trade record showed zero option closes from
Mar 16 to May 10 in all three accounts; the Income and Options pages read
the same ledger. The recollection was of February–March 2026. Asking for
2025 exports would have cost time and produced nothing.

This is the other half of [[check-freshness-and-ask-first]]: ask early for
what is missing and obtainable, but confirm it is missing.

## How to apply

- For a broker gap: query the broker's realized P&L or order history for
  the window through the MCP, and read the export already in
  `data/processed` for that period. Compare counts, not just totals.
- Cross-check with a second page or report in the app that reads the same
  table; if both show the zero, it is not an import defect.
- Bring the evidence to the user with the years and accounts named; a
  memory of "lots of activity" is usually right about a different period.
- Only then request the file, naming account, months and destination
  folder, one thing at a time.
