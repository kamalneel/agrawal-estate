---
scope: universal
project: null
category: technical
applies-to: cached or materialized metric tables filled by upsert (bbd_performance_metrics and anything like it)
created: 2026-09-25
source-context: "BBD audit F2: a Jan 2025 monthly growth row computed 2026-02-06 with the wrong account set and the old 8% target survived seven months of recomputes"
---

# A Forced Recompute Clears the Cache First

An upsert-only cache keeps every row it ever produced. When the computation
changes so that a row is no longer produced (a filter, a cutoff, a
different baseline), the old row stays and reads as current. `force=True`
must delete the whole cache before recomputing, or the cache must be keyed
on a hash of its inputs and assumptions so a change invalidates it.

## Why

`bbd_performance_metrics` had a Jan 2025 monthly growth row with a
baseline that included non-brokerage accounts and the 8% target from before
the 16% combined-return setting. Every recompute since February skipped it:
the upsert only touched rows it regenerated, and the cutoff-delete only
removed rows *before* 2025-01-01. It sat at the top of the monthly chart
for seven months.

## How to apply

- `force` means "the cache is wrong": delete all rows for the metric
  family, then rebuild. Never trust the upsert to reach stale rows.
- Better: store a settings/version hash on each row and treat a mismatch
  as stale on read.
- After any change to account filters, cutoffs or assumptions, run the
  forced recompute and diff the row count and date range before and after.
