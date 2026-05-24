---
type: concept
name: Data Ingestion Pipeline
last-compiled: 2026-04-06
sources: [docs/DATA_ARCHITECTURE.md, docs/apps/DATA-INGESTION.md, README.md]
---

# Data Ingestion Pipeline

## Summary
File-based data ingestion system that imports financial data from PDF statements, CSV exports, and copy-paste from brokerage apps. Uses automatic deduplication to handle overlapping imports safely.

## Key Details
- **Inbox structure**: `data/inbox/investments/{robinhood,schwab,other}`, `data/inbox/{income,tax,real_estate,estate_planning}`
- **Processing flow**: inbox -> parsed -> deduplicated -> database; files move to `data/processed/` or `data/failed/`
- **Deduplication**: Hybrid crossover + count-based algorithm per transaction type
- **Supported brokers**: Robinhood, Schwab
- **Three sources**: PDF/CSV statements, activity CSVs, Robinhood paste

## What We Know
- No external API integrations — all data stays local
- Amount parsing handles parentheses format for negatives
- Identical transactions are valid (use instance counters)
- Frontend has a Data Ingestion page for uploads

## Open Questions
- Schwab API integration status (token file exists: `backend/schwab_token.json`)

## Related Playbook Rules
- `no-direct-db-modifications`
- `three-authoritative-data-sources`
- `deduplication-hybrid-crossover`
