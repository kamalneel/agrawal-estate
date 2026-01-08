# V3 Implementation Notes

**Implementation Date:** December 21, 2024  
**Spec Version:** V3.0 + V3.3 Addendum  
**Status:** ✅ Complete (V3.3 Addendum Implemented January 7, 2026)

> **V3.3 Addendum:** See [V3.3-ADDENDUM.md](./V3.3-ADDENDUM.md) for mean reversion awareness, weekly income priority, and flexible ITM debit limits.

---

## What Was Built

### Implementation Summary

V3 was implemented in 5 chunks, each validated before proceeding:

| Chunk | Description | Files | Status |
|-------|-------------|-------|--------|
| 1 | Remove timing optimization | `new_covered_call.py`, `algorithm_config.py` | ✅ Complete |
| 2 | Remove ITM thresholds, 20% cost rule | `option_calculations.py`, `roll_options.py` | ✅ Complete |
| 3 | Zero-cost finder (52 weeks, Delta 30) | `zero_cost_finder.py` (new) | ✅ Complete |
| 4 | Pull-back detector, unified evaluator | `pull_back_detector.py`, `position_evaluator.py` (new) | ✅ Complete |
| 5 | Smart assignment (IRA only) | `smart_assignment_evaluator.py`, `assignment_tracker.py` (new) | ✅ Complete |

---

## New Files Created

### Core V3 Modules

| File | Purpose | Lines |
|------|---------|-------|
| `zero_cost_finder.py` | Find SHORTEST zero-cost roll (up to 52 weeks) | ~320 |
| `pull_back_detector.py` | Detect pull-back opportunities for far-dated positions | ~260 |
| `position_evaluator.py` | Unified 3-state position evaluation + SmartScanFilter | ~400 |
| `v3_scanner.py` | 5-scan schedule with state tracking | ~450 |
| `smart_assignment_evaluator.py` | IRA-only smart assignment vs roll decision | ~310 |
| `assignment_tracker.py` | Track assignments for Monday buy-back follow-up | ~380 |

### Test Files Created

| File | Purpose |
|------|---------|
| `test_chunk2_validation.py` | 20% cost rule, threshold removal tests |
| `test_chunk3_validation.py` | Zero-cost finder tests (52 weeks, Delta 30) |
| `test_chunk4_validation.py` | Pull-back detector, unified evaluator tests |
| `test_chunk5_validation.py` | Smart assignment tests |

---

## Files Modified

| File | Changes |
|------|---------|
| `algorithm_config.py` | Added V3_CONFIG with 15 simplified parameters |
| `new_covered_call.py` | Removed timing optimization, kept TA-based wait |
| `roll_options.py` | Simplified ITM handling, removed thresholds |
| `itm_roll_optimizer.py` | Added delta_target parameter, 52-week scanning |
| `option_calculations.py` | Removed threshold checks, added 20% cost rule |

---

## Key Deviations from Original Spec

### 1. Timing Optimizer
- **Spec:** Delete `timing_optimizer.py`
- **Implementation:** File didn't exist; removed timing logic from `new_covered_call.py` instead
- **Impact:** None - same result achieved

### 2. Multi-Week Optimizer  
- **Spec:** Rename `multi_week_optimizer.py` → `zero_cost_finder.py`
- **Implementation:** `multi_week_optimizer.py` didn't exist; created `zero_cost_finder.py` as new file
- **Impact:** None - cleaner implementation

### 3. Threshold Functions
- **Spec:** Delete threshold functions entirely
- **Implementation:** Made functions return "always can roll" for backwards compatibility
- **Impact:** Same behavior, safer for any remaining callers

### 4. Smart Assignment (Chunk 5)
- **Spec:** Not in original V3 spec
- **Implementation:** Added as Chunk 5 based on user's IRA strategy
- **Impact:** Additional feature beyond original scope

---

## V3 Decision Tree

```
┌─────────────────────────────────────────────────────────────┐
│                   POSITION EVALUATOR                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. FAR-DATED & CAN PULL BACK? (>1 week out)                │
│     ├─ YES → PULL_BACK (Delta 30 strike, shortest duration) │
│     └─ NO → Continue to state 2                             │
│                                                              │
│  2. IN THE MONEY?                                           │
│     ├─ YES → Find zero-cost roll ≤52 weeks (Delta 30)       │
│     │   ├─ Found → ROLL_ITM                                 │
│     │   └─ Not found → CLOSE_CATASTROPHIC                   │
│     └─ NO → Continue to state 3                             │
│                                                              │
│  3. PROFITABLE (≥60%) AND OTM?                              │
│     ├─ YES → ROLL_WEEKLY (Delta 10)                         │
│     └─ NO → No action                                       │
│                                                              │
│  4. EXPIRATION DAY + IRA + BORDERLINE ITM (0.1-2%)?         │
│     ├─ YES → Evaluate SMART_ASSIGNMENT vs ROLL              │
│     └─ NO → Normal handling                                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Configuration Reference

### V3 Core Parameters (15 total)

```python
V3_CONFIG = {
    # Core thresholds
    "profit_threshold": 0.60,      # Roll at 60%+ profit
    "max_debit_pct": 0.20,         # Max 20% of original premium
    "max_roll_months": 12,         # Up to 52 weeks

    # Strike selection
    "strike_selection": {
        "weekly_delta_target": 0.90,      # Delta 10 for weekly
        "itm_escape_delta_target": 0.70,  # Delta 30 for ITM escapes
        "pullback_delta_target": 0.70,    # Delta 30 for pull-backs
    },

    # Smart assignment (IRA only)
    "smart_assignment": {
        "enabled": True,
        "accounts": ["IRA", "ROTH_IRA", "ROTH IRA"],
        "max_itm_pct": 2.0,
        "min_itm_pct": 0.1,
        "min_roll_weeks": 2,
        "min_roll_debit": 15,
        "monday_skip_threshold": 3.0,
        "monday_wait_threshold": 1.0,
    },
}
```

---

## Scan Schedule (Pacific Time)

| Time | Scan | Purpose |
|------|------|---------|
| 6:00 AM | Main | Comprehensive position evaluation, Monday buy-backs |
| 8:00 AM | Urgent | State changes (OTM→ITM), new pull-backs |
| 12:00 PM | Midday | Pull-back opportunities from intraday drops |
| 12:45 PM | Pre-close | Expiring positions, smart assignment (IRA) |
| 8:00 PM | Evening | Next day prep (earnings, expiring tomorrow) |

---

## Known Issues / Quirks

### 1. Original Premium Not Always Available
- **Issue:** Some positions don't have `original_premium` attribute
- **Workaround:** Default to $1.00 if not available
- **Impact:** May affect 20% cost calculation accuracy

### 2. Earnings/Dividend Tracking
- **Issue:** Depends on `EarningsTracker` and `DividendTracker` classes
- **Workaround:** Gracefully returns False if tracker fails
- **Impact:** May not skip earnings weeks if tracker unavailable

### 3. Assignment Tracking In-Memory
- **Issue:** `assignment_tracker.py` uses in-memory list
- **Workaround:** Added `export_assignments()` / `import_assignments()` for persistence
- **Recommendation:** Consider database table for production

---

## Quick Reference

### Delta Targets
| Scenario | Delta Target | Probability OTM |
|----------|-------------|-----------------|
| Weekly rolls | 0.90 | 90% (Delta 10) |
| ITM escapes | 0.70 | 70% (Delta 30) |
| Pull-backs | 0.70 | 70% (Delta 30) |

### Cost Rules
| Rule | Threshold |
|------|-----------|
| Maximum debit | 20% of original premium |
| Credit | Always accept |
| Max roll duration | 52 weeks (12 months) |

### Smart Assignment (IRA Only)
| Condition | Threshold |
|-----------|-----------|
| ITM range | 0.1% - 2.0% |
| Trigger | Expiration day only |
| Skip buyback | >3% above assignment |
| Wait suggestion | 1-3% above assignment |

---

## Migration Checklist

- [x] V2 docs marked as deprecated
- [x] V3 docs status updated to "Implemented"
- [x] All 5 chunks implemented and validated
- [x] Test files created for each chunk
- [ ] Comprehensive testing complete
- [ ] Production deployment

---

## Next Steps

1. **Comprehensive Testing** - Run full test suite
2. **Real Position Testing** - Test with actual positions
3. **Edge Case Testing** - Test catastrophic scenarios
4. **Production Deployment** - Enable V3 in production
5. **Monitoring** - Watch for unexpected behavior

