# Algorithm Upgrade Best Practices

**Document Purpose:** Capture learnings from algorithm upgrades to ensure future versions are implemented correctly, completely, and without regressions.

**Based On:** V4 implementation (January 20, 2026)

---

## Table of Contents

1. [Pre-Implementation Phase](#pre-implementation-phase)
2. [Philosophy Documentation](#philosophy-documentation)
3. [Testing Strategy](#testing-strategy)
4. [Implementation Checklist](#implementation-checklist)
5. [Common Pitfalls](#common-pitfalls)
6. [V4 Implementation Case Study](#v4-implementation-case-study)
7. [Rollback Strategy](#rollback-strategy)

---

## Pre-Implementation Phase

### Step 1: Document the Philosophy First

Before writing any code, create a comprehensive specification document that covers:

1. **Foundational beliefs** - The "why" behind every decision
2. **Core philosophy** - One-sentence summary of the algorithm's purpose
3. **Key principles** - 5-8 rules that guide all decisions
4. **Decision priority order** - What takes precedence when rules conflict
5. **Anti-patterns** - What NOT to do (with explanations)
6. **Examples** - Real scenarios with step-by-step reasoning

**V4 Example:**
```
V4 Foundational Philosophy:
1. Believe in holdings
2. Hold forever
3. Mean reversion is inevitable
4. Primary goal: weekly options income
5. Avoid unnecessary risk
6. Avoid forced assignment
```

### Step 2: Identify ALL Dependent Systems

Before implementation, search the codebase to find every system that will be affected:

```bash
# Find all references to the notification service
grep -r "v2_notification_service\|check_and_notify" --include="*.py"

# Find all scheduler jobs
grep -r "scheduler\|add_job\|cron" --include="*.py"

# Find all API endpoints related to recommendations
grep -r "recommendations\|recommend" --include="*.py" backend/app/modules/
```

**Critical Systems to Check:**
- [ ] Scheduler (all scheduled scans)
- [ ] Manual trigger endpoints
- [ ] RLHF/Learning system
- [ ] Notification service
- [ ] Reconciliation service
- [ ] API router endpoints
- [ ] Database models

### Step 3: Create a Dependency Map

Document which files need changes:

| Component | File | Change Type | Notes |
|-----------|------|-------------|-------|
| Core evaluator | `v4_position_evaluator.py` | NEW | Core decision engine |
| Notification integration | `v4_notification_service.py` | NEW | Bridges evaluator to notifications |
| Scheduler | `scheduler.py` | MODIFY | All scans must use new version |
| Models | `recommendation_models.py` | MODIFY | New models for follow-up tracking |
| Config | `algorithm_config.py` | MODIFY | V4 config section |
| Router | `router.py` | MODIFY | Add new endpoint |
| RLHF | `reconciliation_service.py` | MODIFY | Handle new action types |

---

## Philosophy Documentation

### Capture the Decision Logic

For every recommendation type, document:

1. **Trigger conditions** - When does this recommendation fire?
2. **Reasoning** - Why is this the right action?
3. **Philosophy applied** - Which core principle justifies this?
4. **Alternative considered** - What else could we have recommended?
5. **User action** - What should the user do?

**Example from V4:**
```python
# LET_EXPIRE recommendation
{
    "action": "LET_EXPIRE",
    "reason": "Position is safe OTM with 3% cushion. Time decay is working in your favor.",
    "reason_short": "Safe OTM, let expire",
    "philosophy_applied": "V4 Philosophy: Primary goal is weekly income. Position is working as intended.",
    "alternative_considered": "Could roll for credit, but position is healthy - no action needed"
}
```

### Notification Formats

Define both mobile (brief) and web (detailed) formats:

**Mobile (Telegram):**
```
LET_EXPIRE: NVDA $145.00 Jan 24
Safe OTM, let expire
```

**Web (Full RLHF):**
```
LET_EXPIRE: NVDA $145.00 Call Jan 24

Reasoning:
- Position is 3.2% OTM
- 4 days to expiration
- Time decay working in favor
- No action needed

Philosophy Applied:
V4: Primary goal is weekly income. Position is working as intended.

Alternative: Could roll for $0.15 credit, but unnecessary.
```

---

## Testing Strategy

### Phase 1: Unit Testing the Evaluator

Create a dry-run test that:
1. Fetches real positions from the database
2. Runs them through the new evaluator
3. Prints detailed output WITHOUT taking action

```python
# test_v4_dry_run.py
async def test_v4_dry_run():
    """Test V4 evaluator with real positions - NO side effects"""
    positions = await fetch_active_positions()

    for position in positions:
        result = evaluator.evaluate(position)
        print(f"\n{position.symbol} {position.strike} {position.expiration_date}")
        print(f"  Action: {result.action}")
        print(f"  Reason: {result.reason}")
        print(f"  Philosophy: {result.philosophy_applied}")
```

### Phase 2: Integration Testing

Test the full notification flow:
1. Evaluator produces recommendation
2. Notification service formats it
3. Database records are created
4. Telegram message is generated (but not sent)

### Phase 3: Manual Trigger Testing

Use the API endpoint to test on-demand:
```bash
curl -X POST http://localhost:8000/api/strategies/recommendations/check-now-v4
```

### Phase 4: Verify Scheduler Integration

After updating the scheduler:
1. Restart the backend
2. Check logs for the new version being used
3. Wait for the next scheduled scan
4. Verify the notification shows new-version formatting

---

## Implementation Checklist

### Before Starting

- [ ] Philosophy document complete and reviewed
- [ ] All dependent systems identified
- [ ] Test data prepared (real positions to test against)
- [ ] Rollback plan documented

### Core Implementation

- [ ] New config section added to `algorithm_config.py`
- [ ] New evaluator created (or existing modified)
- [ ] New models added (with migration)
- [ ] Notification service updated
- [ ] Router endpoint added

### Integration (CRITICAL)

**This is where V4 initially failed - don't skip these:**

- [ ] **Scheduler: ALL scans updated to use new version**
  - [ ] 6am main scan
  - [ ] 8am post-open scan
  - [ ] 12pm midday scan
  - [ ] 12:45pm pre-close scan
  - [ ] 8pm evening scan
  - [ ] Manual trigger function

- [ ] **RLHF/Reconciliation service handles new action types**
  - [ ] New action types mapped to recommendation_type
  - [ ] Feedback can be recorded for new actions

- [ ] **API endpoints use new version**
  - [ ] `strategy_service.generate_recommendations()` has V4 branch
  - [ ] `ALGORITHM_VERSION` default updated to new version
  - [ ] RLHF epoch updated for new version

### Verification

- [ ] Dry-run test passes with real positions
- [ ] Manual trigger produces correct notifications
- [ ] Scheduler runs use new version (check logs after restart)
- [ ] RLHF UI shows new action types correctly
- [ ] Notification format matches spec (mobile AND web)

---

## Common Pitfalls

### Pitfall 1: Adding New Version as "Option" Instead of "Default"

**What happened in V4:**
- Created `check_and_notify_v4()` method
- Added `/check-now-v4` endpoint
- But scheduler still called `check_and_notify_v2()`
- User received V3-style notifications despite "V4 being implemented"

**Solution:**
When implementing a new version, immediately grep for all calls to the old version and update them:
```bash
grep -rn "check_and_notify_v2\|v2_notification" --include="*.py"
```

### Pitfall 2: Type Mismatches (Decimal vs Float)

**What happened in V4:**
```python
# Error: unsupported operand type(s) for -: 'decimal.Decimal' and 'float'
intrinsic_value = stock_price - strike_price  # stock_price was Decimal
```

**Solution:**
Always convert database Decimal fields to float for calculations:
```python
strike_price = float(position.strike_price) if position.strike_price else 0.0
stock_price = float(stock_price) if stock_price else 0.0
```

### Pitfall 3: Wrong Field Names

**What happened in V4:**
```python
# Error: 'SoldOption' object has no attribute 'contracts'
# Actual field name was 'contracts_sold'
```

**Solution:**
Before implementation, read the model definitions:
```python
# Check the actual model
class SoldOption(Base):
    contracts_sold = Column(Integer)  # Not 'contracts'
```

### Pitfall 4: Wrong Status Values

**What happened in V4:**
```python
# Found 0 positions with:
filter(SoldOption.status == 'active')
# Actual status value was 'open'
```

**Solution:**
Query the database to see actual values:
```sql
SELECT DISTINCT status FROM sold_options;
```

### Pitfall 5: Orphaned Code from Copy-Paste

**What happened in V4:**
```python
# IndentationError from orphaned code block that was partially deleted
```

**Solution:**
After any edit, run Python syntax check:
```bash
python -m py_compile backend/app/modules/strategies/v4_notification_service.py
```

### Pitfall 6: Multiple Alembic Heads

**What happened in V4:**
```
Multiple head revisions are present; run revision with --head
```

**Solution:**
Use specific revision name:
```bash
alembic upgrade add_v4_follow_up_conditions
```

### Pitfall 7: Multiple Code Paths for Same Feature

**What happened in V4 (discovered later):**
- Updated scheduler to use V4 ✓
- Verified scheduler sends V4 Telegram notifications ✓
- But UI still showed V3-style recommendations ✗

**Root cause:** Two separate code paths:
1. **Scheduler path** (for Telegram notifications) → `scheduler.check_and_notify_v4()` → `v4_notification_service`
2. **API path** (for UI display) → `/options-selling/recommendations` → `strategy_service.generate_recommendations()` → **still using V3!**

**Solution:**
1. Add V4 branch to `strategy_service.generate_recommendations()`:
```python
if ALGORITHM_VERSION.lower() == 'v4':
    return self.generate_v4_recommendations(params)
```
2. Create `generate_v4_recommendations()` method using V4 evaluator
3. Update `ALGORITHM_VERSION` default to "v4"

**Lesson:** When implementing a new algorithm version, audit ALL code paths that generate/display recommendations:
- Scheduler notification path
- API endpoint path
- Any background job paths
- Any direct database queries that might bypass the evaluator

### Pitfall 8: .env File Overrides Code Defaults

**What happened in V4:**
- Changed default `ALGORITHM_VERSION` in code to "v4"
- Restarted server, but V3 was still running
- Root cause: `.env` file had `ALGORITHM_VERSION=v3` which overrides code default

**Solution:**
Always check `.env` file after changing defaults:
```bash
grep ALGORITHM_VERSION backend/.env
```

Update or remove the line to use the new version.

### Pitfall 9: Config Key Mismatch Between Code and Config

**What happened in V4:**
- V4 evaluator code used `self.config['escape_duration']['max_weeks']`
- But V4_CONFIG defined `max_escape_weeks` at top level
- Result: KeyError for all ITM positions, only OTM positions worked

**Solution:**
When adding new config parameters:
1. Define the config structure FIRST
2. Write code that matches the config exactly
3. Test with both ITM and OTM positions

---

## V4 Implementation Case Study

### Timeline

1. **Philosophy Development** (Session 1)
   - Defined the 6 beliefs
   - Created intrinsic/time value model
   - Documented decision framework
   - Added V4_CONFIG to algorithm_config.py

2. **Initial Implementation** (Session 2)
   - Created v4_position_evaluator.py
   - Created v4_notification_service.py
   - Added database migration for follow_up_conditions
   - Added /check-now-v4 endpoint
   - Added check_and_notify_v4 to scheduler

3. **Bug Fixes** (Session 2)
   - Fixed Decimal/float type mismatches (3 instances)
   - Fixed field name: contracts → contracts_sold
   - Fixed status filter: 'active' → 'open'
   - Fixed orphaned code causing IndentationError

4. **Critical Gap Discovered** (Session 2)
   - User received V3-style notification after "V4 implementation"
   - Root cause: Scheduler still used V2/V3
   - V4 was added as option, not made the default

5. **Gap Resolution - Scheduler** (Session 2)
   - Updated ALL scheduler scans to use V4
   - Updated manual trigger to use V4

6. **Second Gap Discovered** (Session 2)
   - User received V3-style recommendation in UI after scheduler fix
   - Root cause: API endpoint still using V3 via `strategy_service`
   - Two separate code paths: scheduler (V4) vs API (still V3)

7. **Gap Resolution - API** (Session 2)
   - Added `generate_v4_recommendations()` to strategy_service
   - Added V4 branch in `generate_recommendations()`
   - Updated `ALGORITHM_VERSION` default to "v4"
   - Updated RLHF epoch to V4

### Lessons Learned

1. **"Adding a new version" ≠ "Making it the default"**
   - Must update ALL entry points
   - Scheduler is the primary entry point for notifications

2. **Test with actual notifications, not just code**
   - The dry-run test showed correct V4 output
   - But real notifications still came from V3
   - Always verify end-to-end

3. **Document ALL integration points upfront**
   - Create dependency map before implementation
   - Check off each integration point

4. **Type safety matters**
   - Database uses Decimal for precision
   - Python calculations need float
   - Always convert at the boundary

### Files Created/Modified

| File | Action | Lines Changed |
|------|--------|---------------|
| `algorithm_config.py` | Modified | +50 (V4_CONFIG), default changed to v4 |
| `v4_position_evaluator.py` | Created | ~400 |
| `v4_notification_service.py` | Created | ~350 |
| `recommendation_models.py` | Modified | +30 (FollowUpCondition) |
| `scheduler.py` | Modified | +150 (V4 methods, scan updates) |
| `router.py` | Modified | +20 (new endpoint) |
| `reconciliation_service.py` | Modified | +15 (new action types) |
| `strategy_service.py` | Modified | +200 (V4 branch, generate_v4_recommendations) |
| Migration file | Created | ~40 |

---

## Rollback Strategy

### Quick Rollback (No Code Changes)

If V4 has issues, revert scheduler to V3:

```python
# In scheduler.py, change back:
lambda: self.check_and_notify_v2(scan_type='8am_post_open')
# Instead of:
lambda: self.check_and_notify_v4(scan_type='8am_post_open')
```

### Full Rollback

1. Revert scheduler changes
2. Keep V4 code but don't call it
3. V4 code can be tested independently
4. Resume V4 when ready by updating scheduler again

### Version Coexistence

Both V3 and V4 code can exist simultaneously:
- `check_and_notify_v2()` - V3 logic
- `check_and_notify_v4()` - V4 logic
- Switch by updating scheduler config

---

## Checklist Template for Future Versions

Copy this for V5, V6, etc.:

### Pre-Implementation
- [ ] Philosophy document complete
- [ ] Dependency map created
- [ ] Test data identified

### Implementation
- [ ] Config added
- [ ] Core evaluator created/modified
- [ ] Notification service updated
- [ ] Database migration (if needed)
- [ ] Router endpoint added

### Integration
- [ ] Scheduler: 6am scan
- [ ] Scheduler: 8am scan
- [ ] Scheduler: 12pm scan
- [ ] Scheduler: 12:45pm scan
- [ ] Scheduler: 8pm scan
- [ ] Scheduler: manual trigger
- [ ] RLHF handles new action types
- [ ] API endpoints updated

### Verification
- [ ] Dry-run test passes
- [ ] Manual trigger works
- [ ] Real notification received in new format
- [ ] RLHF UI works with new actions
- [ ] No Python syntax errors

---

---

## V5 Implementation Case Study

### The Bug

V5 implementation was completed, but the preview endpoint returned `Internal Server Error`. All imports passed, all unit tests passed, but the endpoint failed at runtime.

### Root Cause

The V5 preview endpoint code was **copied from V4**, which contained a latent bug:

```python
# BUG: This class doesn't exist
from app.modules.investments.models import PortfolioHolding

# CORRECT: The actual class name
from app.modules.investments.models import InvestmentHolding
```

This bug existed in:
- `router.py` (V4 and V5 preview endpoints)
- `scheduler.py`
- `strategy_service.py`

The bug was hidden because:
1. These code paths were wrapped in `try/except` blocks that silently failed
2. The preview endpoints weren't tested end-to-end after implementation
3. Import syntax was valid (no `SyntaxError`), just wrong class name

### Why Testing Didn't Catch It

The testing approach was:
1. ✅ Read the code
2. ✅ Check imports compile
3. ✅ Reason about logic
4. ❌ **Actually run the endpoint** ← This was skipped

### The Fix

A diagnostic endpoint was added that caught the bug immediately:

```python
@router.get("/recommendations/v5-test")
async def test_v5_imports(db: Session = Depends(get_db)):
    """Test V5 imports and actual functionality."""
    errors = []

    # Test imports
    try:
        from app.modules.investments.models import PortfolioHolding
        errors.append({"test": "import", "status": "OK"})
    except Exception as e:
        errors.append({"test": "import", "status": "FAILED", "error": str(e)})

    # Test actual query
    try:
        holdings = db.query(PortfolioHolding).all()
        errors.append({"test": "query", "status": "OK"})
    except Exception as e:
        errors.append({"test": "query", "status": "FAILED", "error": str(e)})

    return {"tests": errors}
```

### V5-Specific Pitfalls

#### Pitfall 10: Trusting Copied Code Without Verification

**What happened:**
- V5 preview endpoint was copied from V4 preview endpoint
- V4 had a bug (`PortfolioHolding` instead of `InvestmentHolding`)
- Bug was inherited into V5

**Solution:**
Before copying any import or pattern from existing code:
```bash
# Verify the class actually exists in that module
grep "class PortfolioHolding" backend/app/modules/investments/models.py
# Returns nothing → the class doesn't exist!

grep "class.*Holding" backend/app/modules/investments/models.py
# Returns: class InvestmentHolding(BaseModel):
```

#### Pitfall 11: Not Running Endpoints After Creating Them

**What happened:**
- Created V5 preview endpoint
- Checked that Python syntax was valid
- Did NOT actually call the endpoint
- Moved on to next task

**Solution:**
After creating ANY new endpoint, immediately test it:
```bash
# RIGHT AFTER writing the endpoint:
curl http://localhost:8000/api/v1/strategies/recommendations/preview-v5-debug

# If it returns 500, debug NOW, not later
```

#### Pitfall 12: Silent Failures in try/except Blocks

**What happened:**
- The buggy import was inside a `try/except` that returned `{}`
- Code "worked" but returned empty data
- No error was visible

**Solution:**
During development, temporarily remove try/except or add explicit logging:
```python
# BAD: Silent failure
try:
    from app.modules.investments.models import PortfolioHolding
    holdings = db.query(PortfolioHolding).all()
except:
    return {}  # Silently returns empty

# GOOD: Explicit failure during development
from app.modules.investments.models import PortfolioHolding  # Will crash if wrong
holdings = db.query(PortfolioHolding).all()
```

---

## Updated Checklist Template for V6+

Copy this for V6, V7, etc.:

### Pre-Implementation
- [ ] Philosophy document complete
- [ ] Dependency map created
- [ ] Test data identified
- [ ] **NEW: Verify ALL imports from copied code actually exist**

### Implementation
- [ ] Config added
- [ ] Core evaluator created/modified
- [ ] Notification service updated
- [ ] Database migration (if needed)
- [ ] Router endpoint added
- [ ] **NEW: Smoke test endpoint created FIRST**

### Runtime Verification (MANDATORY - Do Not Skip)
- [ ] **NEW: Hit every new endpoint with curl, verify 200 response**
- [ ] **NEW: Check endpoint returns actual data, not empty `{}`**
- [ ] **NEW: Test with `include_uncovered=True` and `include_follow_ups=True`**

### Integration
- [ ] Scheduler: 6am scan
- [ ] Scheduler: 8am scan
- [ ] Scheduler: 12pm scan
- [ ] Scheduler: 12:45pm scan
- [ ] Scheduler: 8pm scan
- [ ] Scheduler: manual trigger
- [ ] RLHF handles new action types
- [ ] API endpoints updated

### Final Verification
- [ ] Dry-run test passes
- [ ] Manual trigger works
- [ ] Real notification received in new format
- [ ] RLHF UI works with new actions
- [ ] No Python syntax errors
- [ ] **NEW: All endpoints return 200 with real data**

---

## Quick Verification Commands

Run these after ANY algorithm upgrade:

```bash
# 1. Check algorithm version is active
curl -s http://localhost:8000/api/v1/strategies/algorithm-status | jq

# 2. Test preview endpoint returns data (not error)
curl -s http://localhost:8000/api/v1/strategies/recommendations/preview-vX-debug | head -c 200

# 3. Verify no Internal Server Error
curl -s http://localhost:8000/api/v1/strategies/recommendations/preview-vX-debug | grep -q "Internal Server Error" && echo "FAILED" || echo "OK"

# 4. Check notification count > 0
curl -s http://localhost:8000/api/v1/strategies/recommendations/preview-vX-debug | jq '.total_notifications'
```

---

---

## V5 Migration Gaps (February 2026)

During debugging of why put recommendations weren't appearing, several integration gaps were discovered. These are critical lessons for V6 migration.

### Pitfall 13: Version Never Called Delegated Logic

**What happened:**
- V5's `get_all_v5_notifications()` was supposed to delegate cash-secured put evaluation to V4
- But the call to `_evaluate_cash_secured_puts()` was missing entirely
- The method existed, it just was never called

**Root cause:** When creating V5 (which delegates some logic to V4), the feature list wasn't audited.

**Solution:**
When creating a new version that delegates to previous version:
```python
# AUDIT ALL features the previous version provides:
# V4 features:
# 1. Position evaluation ✓ (implemented in V5)
# 2. Cash-secured puts ← MISSING IN V5!
# 3. Follow-up conditions ← Was this called?
# 4. Uncovered positions ← Was this called?

# Then ensure V5 exposes them ALL:
def get_all_v5_notifications(...):
    # 1. Position evaluation
    position_notifications = self.evaluate_and_notify(...)

    # 2. Uncovered positions - MUST NOT FORGET
    uncovered = self._evaluate_uncovered_positions()

    # 3. Follow-ups - MUST NOT FORGET
    follow_ups = self._check_follow_up_conditions()

    # 4. Cash-secured puts - MUST NOT FORGET
    puts = self._evaluate_cash_secured_puts(...)
```

### Pitfall 14: Feature Missing Data Source Query

**What happened:**
- Put candidate symbols only came from positions (sold options)
- But stocks held without active options weren't queried from `investment_holdings`
- Result: Held stocks without current options never got put recommendations

**Solution:**
When a feature depends on portfolio data, list ALL relevant data sources:
```sql
-- Put candidates should come from:
-- 1. sold_options (current positions) ✓
-- 2. investment_holdings (held stocks) ← WAS MISSING
-- 3. watchlist (if exists)

-- Query ALL sources:
SELECT DISTINCT symbol FROM sold_options WHERE ...
UNION
SELECT DISTINCT symbol FROM investment_holdings WHERE quantity >= 100
```

### Pitfall 15: Wrong Attribute Name on Shared Data Class

**What happened:**
```python
# Code used:
strike_rec.strike_price

# But StrikeRecommendation dataclass defined:
@dataclass
class StrikeRecommendation:
    recommended_strike: float  # NOT strike_price!
```

**Solution:**
When using data classes from other modules:
1. Open the module and verify field names
2. Use IDE autocomplete to catch mismatches
3. Add type hints that would fail at lint time:
```python
def _find_best_put_opportunity(...) -> Optional[StrikeRecommendation]:
    strike_rec = get_recommendation(...)
    if strike_rec:
        # Type checker will catch: StrikeRecommendation has no attribute 'strike_price'
        return strike_rec.recommended_strike  # CORRECT
```

### Pitfall 16: Missing Top-Level Fields in Notification Dict

**What happened:**
- Put notification dict had `account_name` only inside `context`
- Save function expected it at TOP LEVEL
- Also `source_strike` and `source_expiration` were None
- Result: Recommendation ID was generated incorrectly, causing duplicates

**Solution:**
Define explicit schema for notification dicts (see `notification_schema.py`):
```python
# REQUIRED top-level fields for save function:
'account_name': account_name,      # NOT just in context!
'source_strike': strike,           # For recommendation ID
'source_expiration': expiration,   # For recommendation ID

# Context is for EXTRA info, not required fields
'context': {
    'days_to_exp': days,
    'is_itm': is_itm,
    # ...
}
```

### Pitfall 17: Batch Save Duplicate Handling

**What happened:**
- Multiple notifications in same batch shared same `recommendation_id`
- DB query for "last snapshot number" didn't see uncommitted records
- Result: Duplicate snapshot numbers → constraint violation

**Also:**
- Recommendation lookup filtered by `status == 'active'`
- But unique constraint is on `recommendation_id` regardless of status
- Result: Insert failure when reactivating old recommendation

**Solution:**
Use in-memory caches for batch processing:
```python
def save_to_history(notifications: List[Dict]):
    # Caches for batch processing
    snapshot_number_cache: Dict[int, int] = {}
    rec_cache: Dict[str, Any] = {}

    for notif in notifications:
        rec_id = generate_recommendation_id(...)

        # Check CACHE first, then DB
        if rec_id in rec_cache:
            rec = rec_cache[rec_id]
        else:
            rec = db.query(Recommendation).filter(
                recommendation_id == rec_id
                # NO status filter - unique on ID alone
            ).first()
            rec_cache[rec_id] = rec

        # Get snapshot number from cache or DB
        if rec.id in snapshot_number_cache:
            next_num = snapshot_number_cache[rec.id] + 1
        else:
            last = db.query(Snapshot).filter(...).order_by(desc).first()
            next_num = (last.snapshot_number + 1) if last else 1

        snapshot_number_cache[rec.id] = next_num
```

### Pitfall 18: Missing Manual Trigger Endpoint

**What happened:**
- `/recommendations/check-now-v4` existed
- No `/recommendations/check-now-v5` was created
- Testing V5 required modifying scheduler, which was cumbersome

**Solution:**
When creating new algorithm version, ALWAYS add:
```python
@router.post("/recommendations/check-now-v{N}")
async def check_now_vN(...):
    """Manual trigger for V{N} notifications."""

@router.get("/recommendations/check-now-v{N}-debug")
async def check_now_vN_debug(...):
    """Debug endpoint that returns full notification data without sending."""
```

---

## V6 Migration Checklist

When migrating from V5 to V6, complete ALL items:

### Feature Audit
- [ ] List ALL features V5 provides (position eval, puts, uncovered, follow-ups, pending orders)
- [ ] Ensure V6 exposes or delegates EVERY feature
- [ ] Test each feature type produces notifications

### Data Source Audit
- [ ] For each feature, list all DB tables it should query
- [ ] Verify queries cover ALL relevant tables
- [ ] Test with data in each table (not just the obvious one)

### Schema Compliance
- [ ] All notification dicts use `NotificationDict` TypedDict
- [ ] Required fields are at TOP LEVEL, not buried in context
- [ ] IDE/linter catches any field mismatches

### Batch Processing
- [ ] Save function uses in-memory caching
- [ ] No `status == 'active'` filter on unique ID lookups
- [ ] Test with batch of 10+ notifications for same symbol

### Endpoints
- [ ] `/check-now-v6` endpoint created
- [ ] `/check-now-v6-debug` endpoint created
- [ ] Both tested with curl and return 200

### Runtime Verification
- [ ] Each notification type (calls, puts, uncovered, pending orders) appears
- [ ] Save function commits without constraint violations
- [ ] Telegram formatting includes all notification types

---

**Document History:**
- January 20, 2026: Initial version based on V4 implementation
- February 3, 2026: Added V5 lessons (import verification, runtime testing)
- February 4, 2026: Added V5 migration gaps (Pitfalls 13-18, V6 checklist)

**Key Takeaways:**
> 1. The biggest risk in algorithm upgrades is not the new logic - it's failing to update all the integration points.
> 2. **Never trust copied code.** Verify every import against the actual source module.
> 3. **Always run endpoints immediately after creating them.** Syntax checking is not enough.
> 4. **Audit ALL features** when creating a version that delegates to previous version.
> 5. **Use in-memory caching** for batch save operations to avoid duplicate key issues.
