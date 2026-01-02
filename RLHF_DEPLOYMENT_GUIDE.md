# RLHF Learning System - Deployment Guide

**Created:** January 2, 2025 (while traveling)  
**Context:** This was developed on the laptop while traveling. Deploy on home server.

---

## TL;DR - Quick Deploy

```bash
cd ~/Personal/agrawal-estate  # or wherever your repo is
git pull origin main
cd backend
source venv/bin/activate
alembic upgrade head
# Restart your server (however you do that)
```

---

## What Was Implemented

### The Problem We're Solving

You have a notification system (V3) that sends recommendations. You execute trades that may or may not follow those recommendations. We need to:

1. **Track** what the algorithm recommended vs what you actually did
2. **Classify** whether you consented, modified, or rejected recommendations
3. **Track outcomes** to see who was right (you or the algorithm)
4. **Detect patterns** in your divergences
5. **Propose V4 changes** based on evidence, not gut feelings

### Design Philosophy

- Algorithm stays pure (data-driven)
- Human feedback is observed, not encoded
- Changes are proposed, not automatic
- You decide what to implement

---

## Files Created

### 1. Database Models
**File:** `backend/app/modules/strategies/learning_models.py`

4 new SQLAlchemy models:
- `RecommendationExecutionMatch` - Links recommendations to executions
- `PositionOutcome` - Tracks what happened after execution
- `WeeklyLearningSummary` - Weekly aggregation of insights
- `AlgorithmChange` - Audit trail of algorithm modifications

### 2. Database Migration
**File:** `backend/migrations/versions/20250102_add_rlhf_learning_tables.py`

Creates 4 new tables with proper indexes and foreign keys.

### 3. Reconciliation Service
**File:** `backend/app/modules/strategies/reconciliation_service.py`

Core business logic:
- `reconcile_day(date)` - Match recommendations to executions
- `track_position_outcomes(date)` - Track completed position outcomes
- `generate_weekly_summary(year, week)` - Generate weekly analysis

### 4. API Router
**File:** `backend/app/modules/strategies/learning_router.py`

Endpoints under `/api/v1/strategies/learning/`:
- GET/POST `/reconcile` - Trigger reconciliation
- GET `/matches` - View matches
- GET `/weekly-summaries` - View summaries
- GET `/analytics/*` - Analytics endpoints
- POST `/v4-candidates/{id}/decide` - Decide on changes

### 5. Documentation
**File:** `docs/RLHF-LEARNING-SYSTEM.md`

Full documentation of the system.

---

## Files Modified

### 1. Scheduler
**File:** `backend/app/core/scheduler.py`

Added 3 new scheduled jobs:
- **9:00 PM PT (Mon-Fri):** Daily reconciliation
- **10:00 PM PT (Mon-Fri):** Outcome tracking
- **Saturday 9:00 AM PT:** Weekly learning summary

New methods added:
- `run_daily_reconciliation()`
- `run_weekly_learning_summary()`
- `run_outcome_tracking()`
- `_send_weekly_learning_notification()`

### 2. Main App
**File:** `backend/app/main.py`

Added import and router registration for `learning_router`.

---

## Deployment Steps

### Step 1: Pull Code

```bash
cd ~/Personal/agrawal-estate
git pull origin main
```

### Step 2: Run Migration

```bash
cd backend
source venv/bin/activate
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade 20251222_feedback_and_telegram -> 20250102_rlhf_learning, Add RLHF learning tables
```

### Step 3: Verify Tables Created

```bash
# Connect to your PostgreSQL
psql -d agrawal_estate  # or your DB name

# Check tables exist
\dt *learning*
\dt *matches*
\dt *outcomes*
\dt *algorithm*
```

Expected tables:
- `recommendation_execution_matches`
- `position_outcomes`
- `weekly_learning_summaries`
- `algorithm_changes`

### Step 4: Restart Server

```bash
# However you restart your server
# If using systemd:
sudo systemctl restart agrawal-estate

# If running manually:
# Kill existing process and start fresh
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Step 5: Verify Scheduler Jobs

Check logs for:
```
RLHF Learning jobs configured: daily reconciliation (9PM), weekly summary (Sat 9AM), outcome tracking (10PM)
```

### Step 6: Test Endpoints

```bash
# Test reconciliation endpoint
curl -X POST "http://localhost:8000/api/v1/strategies/learning/reconcile" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Test weekly summaries
curl "http://localhost:8000/api/v1/strategies/learning/weekly-summaries" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Test analytics
curl "http://localhost:8000/api/v1/strategies/learning/analytics/divergence-rate?days=30" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Post-Deployment: Backfill Historical Data

The system starts tracking from deployment date. To backfill historical data:

```bash
# Manually trigger reconciliation for past dates
curl -X POST "http://localhost:8000/api/v1/strategies/learning/reconcile?target_date=2024-12-30" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Repeat for each day you want to backfill
```

Or create a quick script:
```python
from datetime import date, timedelta
from app.modules.strategies.reconciliation_service import get_reconciliation_service
from app.core.database import SessionLocal

db = SessionLocal()
service = get_reconciliation_service(db)

# Backfill last 30 days
for i in range(30):
    target = date.today() - timedelta(days=i)
    result = service.reconcile_day(target)
    print(f"{target}: {result}")

db.close()
```

---

## Troubleshooting

### Migration Fails

If you get "relation already exists":
```bash
# Check current migration state
alembic current

# If stuck, mark as complete
alembic stamp 20250102_rlhf_learning
```

### Import Errors

If you get import errors, check that all files are present:
```bash
ls -la backend/app/modules/strategies/learning*.py
ls -la backend/app/modules/strategies/reconciliation*.py
```

### Scheduler Not Running Jobs

Check scheduler is started:
```bash
grep -i "scheduler" /path/to/your/logs
```

### No Matches Found

If reconciliation finds no matches:
1. Check you have recommendations in `strategy_recommendations` table
2. Check you have transactions in `investment_transactions` table
3. Check date filters are correct

---

## Future Work (Not Implemented Yet)

If you want to continue developing:

1. **Counterfactual P&L** - Calculate what algorithm would have made
2. **Dashboard UI** - Visualize learning metrics
3. **Telegram Integration** - Quick reason capture via replies
4. **Symbol Insights** - Per-symbol preference learning

---

## Architecture Reference

```
┌─────────────────────────────────────────────────────────────┐
│                    SCHEDULER (9 PM PT)                       │
│                                                              │
│   run_daily_reconciliation()                                 │
│           │                                                  │
│           ▼                                                  │
│   ┌───────────────────────────────────────┐                 │
│   │     ReconciliationService              │                 │
│   │                                        │                 │
│   │   1. Get recommendations (sent today)  │                 │
│   │   2. Get executions (STO/BTC today)    │                 │
│   │   3. Match by symbol, score by         │                 │
│   │      strike/expiration/premium         │                 │
│   │   4. Classify: consent/modify/reject   │                 │
│   │   5. Save to recommendation_execution_ │                 │
│   │      matches table                     │                 │
│   └───────────────────────────────────────┘                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    SCHEDULER (Saturday 9 AM)                 │
│                                                              │
│   run_weekly_learning_summary()                              │
│           │                                                  │
│           ▼                                                  │
│   ┌───────────────────────────────────────┐                 │
│   │   1. Aggregate week's matches          │                 │
│   │   2. Detect patterns:                  │                 │
│   │      - DTE preferences                 │                 │
│   │      - Strike preferences              │                 │
│   │      - Rejection patterns              │                 │
│   │   3. Generate V4 candidates            │                 │
│   │   4. Send Telegram notification        │                 │
│   └───────────────────────────────────────┘                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Contact Context

This was developed during a conversation about:
- Building an RLHF feedback loop for options trading
- The core insight: algorithm has data advantage, you have context advantage
- Goal: observe divergences, detect patterns, propose changes (not auto-encode)
- The system should help answer: "Was I right to diverge, or should I trust the algorithm more?"

If you need to continue this work in a new Cursor chat, you can say:

> "I'm continuing work on the RLHF learning system. Read the docs at 
> `docs/RLHF-LEARNING-SYSTEM.md` and `RLHF_DEPLOYMENT_GUIDE.md` for context.
> [Then describe what you want to do next]"

---

**Good luck with deployment!** 🚀

