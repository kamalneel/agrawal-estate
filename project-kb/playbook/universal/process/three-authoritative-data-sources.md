---
scope: universal
project: null
category: process
applies-to: data imports, new data integrations, debugging data issues
created: 2026-04-06
source-context: "Extracted from docs/DATA_ARCHITECTURE.md — data flow architecture"
---

# Three Authoritative Data Sources

All financial data enters the system through exactly three sources:

1. **PDF/CSV Account Statements** — historical portfolio values, cost basis, cash balance (monthly)
2. **Activity Report CSV** — transactions: STO, BTC, dividends, buy/sell (as needed)
3. **Robinhood Paste (copy from app)** — current holdings & options status (real-time)

## Why

Constraining data entry to three well-defined sources makes deduplication tractable, ensures audit trails, and prevents data integrity issues from ad-hoc modifications.

## How to apply

- When adding a new data type, determine which of the three sources it maps to
- If none fit, propose a new authoritative source with clear ownership and dedup strategy
- Never create a "quick import" path that bypasses the ingestion pipeline
- When debugging data issues, trace back to the source document first
