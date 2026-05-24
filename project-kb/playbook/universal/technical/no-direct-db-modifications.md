---
scope: universal
project: null
category: technical
applies-to: all database operations, data imports, AI-assisted changes
created: 2026-04-06
source-context: "Extracted from docs/DATA_ARCHITECTURE.md — core data integrity rule"
---

# No Direct Database Modifications

NEVER modify data directly in the database. All data changes must come from one of the three authoritative sources: PDF/CSV statements, activity report CSVs, or Robinhood copy-paste.

## Why

Data integrity depends on traceability. Every record should trace back to an authoritative source document. Direct DB modifications bypass deduplication logic, audit trails, and validation.

## How to apply

When asked to insert, update, or delete records directly, STOP and alert the user:

> "Per data integrity rules, all data should come from an authoritative source. Would you like to: (1) Upload a PDF statement, (2) Process a CSV file, or (3) Use the copy-paste parser?"

Only proceed with direct modification if explicitly confirmed AND it's for: fixing a bug in previously ingested data, deleting duplicates/errors, or emergency data recovery.
