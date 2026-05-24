---
scope: universal
project: null
category: technical
applies-to: CSV imports, investment transaction processing, save_investment_transactions_hybrid()
created: 2026-04-06
source-context: "Critical bug fix from Feb 2026 — global crossover caused STO/BTC records to be skipped"
---

# Deduplication Uses Hybrid Crossover + Count-Based Per Transaction Type

The deduplication algorithm calculates crossover dates per `(account, transaction_type)` pair, NOT globally. Records before the crossover for their type are skipped. Records at/after use count-based matching.

## Why

A Feb 2026 bug showed that global crossover across all types caused STO/BTC records to be skipped when CASH_MOVEMENT had a later max date. The fix was per-type crossover (lines 118-128 in services.py at time of fix).

## How to apply

- When modifying deduplication logic, always maintain per-type crossover isolation
- Identical transactions are valid (e.g., 5 identical STO contracts) — use instance counters in hashes
- Count-based logic: `to_import = csv_count - db_count`
- `_normalize_amount()` handles parentheses format: `($8,940.08)` -> `-8940.08`
- Test with overlapping date ranges across different transaction types
