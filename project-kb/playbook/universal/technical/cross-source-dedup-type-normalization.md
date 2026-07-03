---
scope: universal
project: null
category: technical
applies-to: ingestion parsers, robinhood_mcp_bridge, record_hash generation
created: 2026-07-03
source-context: "Stock-lot rebuild found NFLX 2025-11-17 split ingested twice: official CSV row (type SPLIT, 64-char hash) + MCP sync row (type SPL, 32-char hash)"
---

# Cross-Source Dedup Requires Type Normalization

Deduplication by `record_hash` only works if every source produces the same
hash for the same real-world event. Different feeds use different type codes
(`SPL` vs `SPLIT`, `BOUGHT` vs `BUY`) and different hash schemes (MCP bridge:
32-char; CSV parsers: 64-char), so identical events slip past the unique
constraint as "different" rows.

## Why

The NFLX 10:1 split (2025-11-17, Neel's Retirement) was ingested from both
the official CSV and the MCP sync. The duplicate doubled the split credit,
producing 440 phantom shares in the lot replay. Verified it was the only
cross-source duplicate (exact and fee-tolerant matching) and deleted the MCP
row — but the ingestion gap remains until parsers normalize.

## How to apply

- Normalize transaction type codes to one canonical vocabulary BEFORE
  computing `record_hash`, in every parser and the MCP bridge.
- Non-trade events (splits, transfers, assignments) need the same
  cross-source care as trades — the original "never mix MCP and CSV trade
  rows for the same period" rule under-scoped the problem.
- After any change to hashing or a new source: run the duplicate check
  (same account/symbol/date/quantity, amount within $1, different hash).
