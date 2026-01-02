# RLHF Learning System

**Version:** 1.0  
**Created:** January 2, 2025  
**Status:** 🟡 PENDING DEPLOYMENT

---

## Overview

The RLHF (Reinforcement Learning from Human Feedback) system tracks the relationship between algorithm recommendations and your actual executions, enabling systematic learning and improvement.

### Design Philosophy

1. **Algorithm stays pure** - Data-driven, no gut feelings encoded
2. **Human feedback is observed** - Not directly encoded into rules
3. **Patterns are detected** - Not assumed
4. **Changes are proposed** - Not automatic
5. **You decide** - Weekly review of patterns and candidates

---

## Components

### 1. Database Tables

| Table | Purpose |
|-------|---------|
| `recommendation_execution_matches` | Links recommendations to executions |
| `position_outcomes` | Tracks what happened after execution |
| `weekly_learning_summaries` | Aggregates weekly insights |
| `algorithm_changes` | Audit trail of algorithm modifications |

### 2. Match Types

| Type | Description |
|------|-------------|
| `consent` | User followed recommendation closely |
| `modify` | User executed with modifications (different strike, expiration) |
| `reject` | Recommendation ignored, no action taken |
| `independent` | User acted without any recommendation |
| `no_action` | Recommendation sent, position resolved itself |

### 3. Scheduled Jobs

| Job | Schedule | Purpose |
|-----|----------|---------|
| Daily Reconciliation | 9:00 PM PT (Mon-Fri) | Match recommendations to executions |
| Outcome Tracking | 10:00 PM PT (Mon-Fri) | Track position outcomes |
| Weekly Summary | Saturday 9:00 AM PT | Generate patterns and V4 candidates |

---

## API Endpoints

All endpoints are under `/api/v1/strategies/learning/`

### Reconciliation

```
POST /reconcile?target_date=2025-01-02
  → Manually trigger reconciliation for a date

POST /track-outcomes?as_of_date=2025-01-02
  → Trigger outcome tracking

GET /matches?start_date=&end_date=&match_type=&symbol=
  → Get reconciliation matches with filters

GET /matches/{id}
  → Get detailed match with outcome

PATCH /matches/{id}/reason?reason_code=timing&reason_text=...
  → Add your reason for a divergence
```

### Weekly Summaries

```
GET /weekly-summaries?year=2025&limit=10
  → List weekly summaries

GET /weekly-summaries/2025/1
  → Get detailed summary for 2025-W01

POST /weekly-summaries/generate?year=2025&week=1
  → Manually generate a summary

PATCH /weekly-summaries/2025/1/review?review_notes=...&review_status=reviewed
  → Update review status
```

### V4 Candidates

```
GET /v4-candidates
  → Get all algorithm change candidates

POST /v4-candidates/{id}/decide?decision=implement&reason=...
  → Record decision on a candidate
```

### Analytics

```
GET /analytics/divergence-rate?days=30
  → Your divergence rate over time

GET /analytics/algorithm-accuracy?days=90
  → Algorithm accuracy (when followed vs diverged)

GET /analytics/top-modifications?days=90
  → Most common modifications you make
```

---

## User Reason Codes

When you diverge from recommendations, you can record why:

| Code | Description |
|------|-------------|
| `timing` | Timing-related decision |
| `premium_low` | Premium was too low |
| `iv_low` | IV was too low |
| `earnings_concern` | Worried about earnings |
| `gut_feeling` | Intuition-based decision |
| `better_opportunity` | Found a better trade |
| `risk_too_high` | Risk was unacceptable |
| `already_exposed` | Already had exposure |
| `other` | Other (use reason_text) |

---

## Weekly Learning Notification

Every Saturday at 9 AM PT, you'll receive:

```
📊 WEEKLY LEARNING SUMMARY (2025-W01)

RECOMMENDATIONS: 23
├─ ✅ Consent: 15 (65%)
├─ ✏️ Modified: 5 (22%)
├─ ❌ Rejected: 2 (9%)
└─ 🆕 Independent: 1 (4%)

P&L: $1,180.00

PATTERNS DETECTED: 2
• User adds 7 days on average to DTE
• User rejects low-premium recommendations

V4 CANDIDATES: 2
• Increase default DTE by 7 days
• Add minimum premium filter ($0.25)

Review in Learning tab for full details.
```

---

## V4 Candidate Lifecycle

1. **Detection** - Pattern observed in weekly data
2. **Proposal** - Candidate created with evidence
3. **Decision** - You decide: `implement`, `defer`, `reject`
4. **Implementation** - If implemented, code is updated
5. **Validation** - Results tracked for 4 weeks
6. **Final** - Kept, rolled back, or modified

---

## Deployment Steps

When you get home:

```bash
# 1. Pull latest code
cd ~/Personal/agrawal-estate
git pull

# 2. Activate virtual environment
cd backend
source venv/bin/activate

# 3. Run migration
alembic upgrade head

# 4. Restart server
# (your existing restart command)
```

---

## Files Created

```
backend/
├── app/
│   ├── modules/
│   │   └── strategies/
│   │       ├── learning_models.py      # Database models
│   │       ├── learning_router.py      # API endpoints
│   │       └── reconciliation_service.py  # Core logic
│   ├── core/
│   │   └── scheduler.py                # Updated with RLHF jobs
│   └── main.py                         # Updated router registration
└── migrations/
    └── versions/
        └── 20250102_add_rlhf_learning_tables.py
```

---

## Key Insights

### What This System Does

1. **Observes** your trading vs algorithm recommendations
2. **Measures** outcomes for both paths
3. **Detects** patterns in your divergences
4. **Proposes** algorithm changes with evidence
5. **Tracks** whether changes helped

### What This System Does NOT Do

1. ❌ Automatically change the algorithm
2. ❌ Encode your gut feelings as rules
3. ❌ Assume you're always right
4. ❌ Assume the algorithm is always right
5. ❌ Make decisions for you

### The Core Question

When you diverge from the algorithm:

> "If I could give the algorithm the information I have right now, would it agree with me?"

- **YES** → Algorithm needs better data inputs, not different logic
- **NO, and I'm often right** → There's a pattern the algorithm is missing
- **NO, and I'm often wrong** → Trust the algorithm more

---

## Future Enhancements (Not Implemented)

- [ ] Counterfactual P&L calculation (what algorithm would have made)
- [ ] Symbol-specific preference learning
- [ ] Time-of-day pattern detection
- [ ] Integration with Telegram for quick reason capture
- [ ] Dashboard visualization of learning metrics

---

**END OF DOCUMENTATION**

