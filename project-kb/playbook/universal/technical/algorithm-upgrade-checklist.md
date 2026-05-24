---
scope: universal
project: null
category: technical
applies-to: algorithm upgrades, notification engine changes, recommendation engine changes
created: 2026-04-06
source-context: "Extracted from docs/ALGORITHM-UPGRADE-BEST-PRACTICES.md — V4 case study"
---

# Algorithm Upgrade Checklist

When upgrading an algorithm version, follow this checklist to avoid regressions.

## Why

The V4 upgrade revealed that missing even one dependent system (scheduler, RLHF, reconciliation) causes silent failures. The checklist ensures completeness.

## How to apply

Before implementation, verify changes to ALL of these:
- [ ] Scheduler (all scheduled scans)
- [ ] Manual trigger endpoints
- [ ] RLHF/Learning system
- [ ] Notification service
- [ ] Reconciliation service
- [ ] API router endpoints
- [ ] Database models
- [ ] Algorithm config

After implementation:
- [ ] All old version references removed or redirected
- [ ] Rollback strategy documented
- [ ] Before/after comparison with real data
