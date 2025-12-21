# Options Notification & Recommendation Algorithm (V3)

**Version:** V3.0 - Simplified Strategy-Aligned Algorithm  
**Status:** Specification (Implementation Pending)  
**Created:** December 21, 2024  
**Migration From:** V2.3

---

## Executive Summary

### Why V3?

V2.3 was over-engineered with features misaligned to the actual investment strategy:
- Multiple ITM thresholds (5%, 10%, 20%) that forced premature position closes
- Complex cost sensitivity rules that rejected economically sound rolls
- Timing predictions (Monday IV bumps, FOMC spikes) that added speculation
- 10 overlapping strategies creating conflicting recommendations

### User's Actual Strategy

**Core principle:** Weekly covered calls (Delta 10) for income generation, with patient position management when stocks move against you.

**When OTM and profitable:** Roll weekly at 60% profit capture  
**When ITM:** Find zero-cost roll to ANY duration (1 week to 12 months)  
**When far-dated:** Pull back to weekly when cost-neutral  
**Never:** Panic close positions (exception: cannot escape within 12 months)

### V3 Goals

1. **Simplicity:** 3 position states, clear decision tree
2. **Alignment:** Algorithm matches actual trading behavior
3. **Reliability:** Eliminate race conditions and conflicting recommendations
4. **Maintainability:** 60% less code, single source of truth

### Key Metrics

| Metric | V2.3 | V3.0 | Change |
|--------|------|------|--------|
| Lines of Code | ~2,500 | ~1,000 | -60% |
| Strategy Files | 10 | 4 | -60% |
| Daily Scans | 5 (uncoordinated) | 5 (coordinated) | Same, but safer |
| Decision States | ~15 | 3 | -80% |
| Configuration Params | 50+ | 12 | -76% |

---

## Table of Contents

1. [What's Removed](#1-whats-removed)
2. [What's Changed](#2-whats-changed)
3. [What's Added](#3-whats-added)
4. [Core Architecture](#4-core-architecture)
5. [Position States & Logic](#5-position-states--logic)
6. [Scan Schedule](#6-scan-schedule)
7. [Configuration](#7-configuration)
8. [Implementation Chunks](#8-implementation-chunks)
9. [Migration Guide](#9-migration-guide)

---

## 1. What's Removed

### 1.1 Performance Tracking System ✅ ALREADY DONE
**Status:** Never implemented, only in docs  
**Action:** Remove from V3 documentation

### 1.2 Strategic Timing Optimization
**Files deleted:**
- `timing_optimizer.py` (~300 lines)

**Rationale:**
- Predicts "Monday IV bumps" and "FOMC spikes" - pure speculation
- Users ignore timing suggestions and sell anyway
- Adds complexity without measurable benefit
- Real technical analysis (RSI, support levels) is kept

**Impact:** -300 lines

### 1.3 ITM Threshold Enforcement
**Code removed from:**
- `roll_options.py`: All threshold check functions
- `itm_roll_optimizer.py`: Threshold validations
- `triple_witching_handler.py`: Threshold overrides

**Deleted logic:**
```python
# REMOVED - No longer check thresholds
if itm_pct > 20:
    return "CATASTROPHIC_CLOSE"
elif itm_pct > 10:
    return "CLOSE_DONT_ROLL"
elif itm_pct > 5:
    return "CLOSE"
```

**Rationale:**
- User's strategy: Never close based on ITM%, always find zero-cost roll
- Only close if cannot escape within 12 months (time-based, not ITM%-based)
- These thresholds forced premature exits

**Impact:** -200 lines

### 1.4 Economic Sanity Checks
**Code removed:**
```python
# REMOVED - No longer validate "minimum savings"
if savings < 50 or savings_pct < 10:
    return "CLOSE - Not worth rolling"

# REMOVED - No longer prevent rolling into ITM
if new_strike_would_be_itm:
    return "CLOSE - Can't roll into ITM"
```

**Rationale:**
- User accepts small savings or even small debits (20% rule)
- Rolling into slightly ITM is acceptable if it's the best available zero-cost option
- Overly restrictive rules rejected valid rolls

**Impact:** -100 lines

### 1.5 Complex Cost Sensitivity Rules
**Deleted scenarios:**
- Earnings exception (75% debit allowed)
- High profit exception (15% debit allowed)
- Expiring soon exception (100% debit allowed)
- Scenario comparison (roll now vs wait vs partial)

**Replaced with:** Single 20% rule (see section 2.2)

**Impact:** -150 lines

### 1.6 Overlapping Strategy Files
**Merged/Deleted:**
- `early_roll_opportunity.py` → Merged into `roll_options.py`
- `approaching_strike_alert.py` → Merged into `roll_options.py`
- Multiple strategies generating recommendations for same position → Single evaluator

**Rationale:**
- Strategy overlap created conflicting recommendations
- Deduplication prevented duplicates but not conflicts
- Single evaluation path is clearer

**Impact:** -200 lines

**Total Removed:** ~1,150 lines

---

## 2. What's Changed

### 2.1 Roll Options Strategy - Simplified

**V2.3 Flow (Complex):**
```
1. Check ITM threshold → Maybe CLOSE
2. Check TA reversal → Maybe WATCH
3. Run optimizer → 3 options
4. Validate roll options → Maybe CLOSE
5. Economic sanity → Maybe CLOSE
6. Liquidity check → Maybe SKIP
7. Generate recommendation
```

**V3.0 Flow (Simple):**
```
1. Is ITM? → Find zero-cost roll (any duration ≤12 months)
2. Is profitable (≥60%) and OTM? → Roll weekly
3. Else → No action
```

**Before:**
```python
# V2.3 - Complex decision tree
def generate_itm_recommendation(position):
    # Check threshold
    threshold = check_itm_thresholds(itm_pct)
    if threshold['should_close']:
        return generate_close()
    
    # Check TA
    action, reason = ta_service.analyze_itm_position()
    if action == "wait":
        return generate_watch()
    
    # Run optimizer
    options = optimizer.analyze_itm_position()
    
    # Validate
    validation = validate_roll_options(options)
    if not validation['valid']:
        return generate_close()
    
    # Economic check
    economics = evaluate_roll_economics()
    if not economics['sound']:
        return generate_close()
    
    return generate_roll(options)
```

**After:**
```python
# V3.0 - Simple zero-cost finder
def generate_itm_recommendation(position):
    # Find shortest duration achieving zero cost
    zero_cost_roll = find_zero_cost_roll(
        position=position,
        max_debit=position.original_premium * 0.20,
        max_months=12
    )
    
    if zero_cost_roll:
        return generate_roll_recommendation(zero_cost_roll)
    else:
        # CATASTROPHIC: Can't escape in 12 months
        return generate_close_recommendation(
            reason="Cannot find zero-cost roll within 12 months"
        )
```

### 2.2 Cost Sensitivity - One Rule

**V2.3 (7 different rules):**
```python
# Standard
if net_debit > new_premium * 0.50: REJECT

# Earnings
if earnings_within(5) and net_debit < new_premium * 0.75: ACCEPT

# High profit
if profit >= 0.80 and net_debit < original_premium * 0.15: ACCEPT

# Expiring soon
if dte <= 1 and net_debit < new_premium: ACCEPT

# ... 3 more edge cases
```

**V3.0 (1 simple rule):**
```python
# ONLY RULE: Debit must be ≤ 20% of original premium
max_acceptable_debit = position.original_premium * 0.20

if net_debit <= max_acceptable_debit:
    ACCEPT  # This is "zero cost" in our strategy
else:
    REJECT  # Keep searching for better expiration
```

**Special case:**
```python
# Any credit is automatically acceptable
if net_debit < 0:  # It's a credit
    ACCEPT  # Always good
```

**Rationale:**
- User typically closes at 80% profit (leaves 20% on table)
- Willing to spend that 20% to escape ITM
- Simple, consistent rule across all scenarios

### 2.3 Multi-Week Optimizer - Repurposed

**V2.3 Purpose:** Find "optimal" expiration based on scoring (credit 40%, weekly return 30%, time 30%)

**V3.0 Purpose:** Find SHORTEST duration achieving zero cost

**Before:**
```python
# V2.3 - Score and rank
def find_optimal_roll_expiration():
    max_weeks = 3
    
    for weeks in range(1, max_weeks + 1):
        exp = get_expiration(weeks)
        premium = get_premium(exp)
        
        # Calculate scores
        credit_score = net_credit / premium * 0.40
        weekly_score = (net_credit / weeks) / premium * 0.30
        time_score = (1 / weeks) * 0.30
        
        total_score = credit_score + weekly_score + time_score
    
    return highest_scored_expiration
```

**After:**
```python
# V3.0 - Find first acceptable
def find_zero_cost_roll(position, max_debit, max_months=12):
    """
    Scan expirations from 1 week to 12 months.
    Return FIRST (shortest) expiration achieving zero cost.
    """
    
    durations = [1, 2, 3, 4, 6, 8, 12, 16, 24, 36, 48]  # weeks
    
    for weeks in durations:
        if weeks > (max_months * 4):  # Convert months to weeks
            break
        
        exp_date = get_expiration_date(weeks)
        
        # Skip if earnings/dividend between now and expiration
        if has_catalyst_before(exp_date):
            continue
        
        # Get premium for roll
        strike = get_best_strike_for_expiration(exp_date)
        new_premium = get_option_premium(strike, exp_date)
        buy_back_cost = position.current_premium
        
        net_cost = buy_back_cost - new_premium
        
        # Check if acceptable
        if net_cost <= max_debit:
            return {
                'expiration': exp_date,
                'weeks': weeks,
                'strike': strike,
                'new_premium': new_premium,
                'net_cost': net_cost,
                'acceptable': True
            }
    
    # Could not find acceptable roll within max_months
    return None
```

**Key changes:**
- Scan up to 12 months (not just 3 weeks)
- Return FIRST acceptable (not highest scored)
- Simple pass/fail on cost threshold
- No complex scoring formulas

### 2.4 New Covered Call Strategy - Simplified

**Before:**
```python
# V2.3 - Check timing optimization + TA
def generate_recommendation(position):
    # Strategic timing
    timing = evaluate_timing_opportunity(symbol)
    if timing['should_wait']:
        return wait_recommendation(timing)
    
    # Technical analysis
    ta_wait, reason = ta_service.should_wait_to_sell()
    if ta_wait:
        return wait_recommendation(reason)
    
    # Recommend sell
    return sell_recommendation()
```

**After:**
```python
# V3.0 - Only check TA
def generate_recommendation(position):
    # Technical analysis only
    ta_wait, reason, analysis = ta_service.should_wait_to_sell(symbol)
    
    if ta_wait:
        # Clear TA signals: oversold, at support, etc.
        return wait_recommendation(reason, analysis)
    
    # Recommend selling weekly Delta 10
    strike = ta_service.recommend_strike_price(
        symbol=symbol,
        option_type='call',
        expiration_weeks=1,
        probability_target=0.90  # Delta 10
    )
    
    return sell_recommendation(strike)
```

**Removed:**
- All timing predictions (Monday IV bump, FOMC, VIX expansion, Friday cutoff)
- Timing optimizer module entirely

**Kept:**
- Technical analysis wait signals (RSI < 30, at support, oversold)
- These are real price-based signals, not timing speculation

---

## 3. What's Added

### 3.1 Pull-Back Detector (New Feature)

**Purpose:** When far-dated positions can return to weekly income, alert user

**Trigger logic:**
```python
def check_pull_back_opportunity(position):
    """
    Check daily: Can we pull back to weekly at zero cost?
    """
    
    # Only check far-dated positions
    if position.weeks_to_expiration <= 2:
        return None  # Already weekly-ish
    
    # Get current far-dated call value
    current_value = position.current_premium
    
    # Get weekly strike (Delta 10)
    weekly_strike = ta_service.recommend_strike_price(
        symbol=position.symbol,
        option_type=position.option_type,
        expiration_weeks=1,
        probability_target=0.90
    )
    
    # Get weekly premium
    weekly_exp = get_next_friday()
    weekly_premium = get_option_premium(weekly_strike, weekly_exp)
    
    # Calculate net cost
    net_cost = current_value - weekly_premium
    max_acceptable = position.original_premium * 0.20
    
    # Check if acceptable
    if net_cost <= max_acceptable:
        return {
            'action': 'PULL_BACK',
            'from_expiration': position.expiration,
            'to_expiration': weekly_exp,
            'from_strike': position.strike,
            'to_strike': weekly_strike,
            'net_cost': net_cost,
            'benefit': f'Return to weekly income ({position.weeks_to_expiration} weeks early)'
        }
    
    return None
```

**When to check:**
- Every day during 6 AM main scan
- For all positions >2 weeks out

**Why important:**
- User rolled to Feb to escape ITM
- Stock drops in January
- Can now return to weekly income generation
- Don't want to wait until Feb if opportunity exists now

### 3.2 Smart Scan Filtering

**Problem in V2.3:** Multiple scans could generate duplicate notifications for same position

**V3.0 Solution:** Track what's been sent, only notify on NEW or CHANGED recommendations

```python
class SmartScanFilter:
    """
    Prevent duplicate notifications within same day.
    """
    
    def __init__(self):
        self.sent_today = {}  # {position_id: recommendation_hash}
    
    def should_send(self, position_id, recommendation):
        """
        Return True if this is new/changed recommendation.
        """
        rec_hash = self._hash_recommendation(recommendation)
        
        if position_id not in self.sent_today:
            # First time seeing this position today
            self.sent_today[position_id] = rec_hash
            return True
        
        if self.sent_today[position_id] != rec_hash:
            # Recommendation changed
            self.sent_today[position_id] = rec_hash
            return True
        
        # Already sent this exact recommendation today
        return False
    
    def _hash_recommendation(self, rec):
        """
        Hash key fields to detect changes.
        """
        return hash((
            rec['action'],  # ROLL, CLOSE, WAIT, etc.
            rec.get('new_strike'),
            rec.get('new_expiration'),
            rec.get('priority')
        ))
    
    def reset_daily(self):
        """Call this at midnight to reset for new day."""
        self.sent_today = {}
```

**Usage:**
```python
# 6 AM scan
filter = SmartScanFilter()
for position in positions:
    rec = evaluate_position(position)
    if rec and filter.should_send(position.id, rec):
        send_notification(rec)

# 8 AM scan
for position in urgent_positions:
    rec = evaluate_urgent(position)
    if rec and filter.should_send(position.id, rec):
        send_notification(rec)  # Only if changed since 6 AM
```

### 3.3 State-Based 8 AM Urgency

**Purpose:** Only alert at 8 AM for meaningful state changes

```python
def check_8am_urgent(position, morning_scan_state):
    """
    Check what changed since 6 AM that requires immediate action.
    """
    urgent_reasons = []
    
    # 1. Newly ITM (state change from OTM → ITM)
    if not morning_scan_state.was_itm and position.is_itm():
        urgent_reasons.append({
            'type': 'NEW_ITM',
            'message': f'Went ITM at market open ({position.symbol} now ${position.current_price})',
            'action': 'Find zero-cost roll'
        })
    
    # 2. Can now pull back (new opportunity)
    if position.weeks_to_expiration > 2:
        can_pull_back = check_pull_back_opportunity(position)
        if can_pull_back and not morning_scan_state.could_pull_back:
            urgent_reasons.append({
                'type': 'PULLBACK_AVAILABLE',
                'message': f'Can now pull back to weekly (stock dropped to ${position.current_price})',
                'action': 'Execute pull-back'
            })
    
    # 3. Earnings TODAY
    if position.has_earnings_today():
        urgent_reasons.append({
            'type': 'EARNINGS_TODAY',
            'message': f'Earnings announcement today - last chance to act',
            'action': 'Close or roll before announcement'
        })
    
    # 4. Deep ITM getting significantly worse
    if morning_scan_state.was_itm:
        additional_itm = position.itm_pct - morning_scan_state.itm_pct
        if additional_itm > 10:  # More than 10% deeper ITM
            urgent_reasons.append({
                'type': 'DEEPER_ITM',
                'message': f'Position {additional_itm:.1f}% deeper ITM since morning',
                'action': 'May need longer roll duration'
            })
    
    # 5. Expiring TODAY
    if position.days_to_expiration == 0:
        urgent_reasons.append({
            'type': 'EXPIRES_TODAY',
            'message': 'Position expires today',
            'action': 'Roll or accept assignment'
        })
    
    return urgent_reasons
```

**Key principle:** Alert on STATE CHANGES, not just magnitude of moves

---

## 4. Core Architecture

### 4.1 Single Position Evaluator

**All strategy logic consolidated into one clear flow:**

```python
class PositionEvaluator:
    """
    Single source of truth for position evaluation.
    Replaces 10 separate strategy files.
    """
    
    def __init__(self, ta_service, optimizer):
        self.ta_service = ta_service
        self.optimizer = optimizer
    
    def evaluate(self, position):
        """
        Main evaluation logic - returns ONE recommendation per position.
        
        Priority order:
        1. Can pull back? (return to weekly income)
        2. Is ITM? (find zero-cost escape)
        3. Is profitable? (roll weekly)
        4. Else: no action
        """
        
        # STATE 1: Pull-back opportunity (highest priority)
        # If far-dated and can return to weekly, do it
        if position.weeks_to_expiration > 2:
            pull_back = self._check_pull_back(position)
            if pull_back:
                return self._generate_pullback_rec(position, pull_back)
        
        # STATE 2: In the money (escape strategy)
        # Find zero-cost roll to any duration ≤12 months
        if position.is_itm():
            return self._handle_itm_position(position)
        
        # STATE 3: OTM and profitable (standard weekly roll)
        # Roll at 60% profit capture
        if position.profit_pct >= 0.60:
            return self._handle_profitable_position(position)
        
        # STATE 4: No action needed
        return None
    
    def _check_pull_back(self, position):
        """Check if can pull back to weekly at zero cost."""
        return check_pull_back_opportunity(position)
    
    def _handle_itm_position(self, position):
        """Find shortest zero-cost roll."""
        max_debit = position.original_premium * 0.20
        
        zero_cost_roll = find_zero_cost_roll(
            position=position,
            max_debit=max_debit,
            max_months=12
        )
        
        if zero_cost_roll:
            return {
                'action': 'ROLL_ITM',
                'position': position,
                'roll_to': zero_cost_roll,
                'priority': 'high' if position.itm_pct > 5 else 'medium',
                'reason': f'{position.itm_pct:.1f}% ITM - rolling to {zero_cost_roll["weeks"]} weeks'
            }
        else:
            # CATASTROPHIC: Cannot escape within 12 months
            return {
                'action': 'CLOSE_CATASTROPHIC',
                'position': position,
                'priority': 'urgent',
                'reason': 'Cannot find zero-cost roll within 12 months - close position'
            }
    
    def _handle_profitable_position(self, position):
        """Roll weekly at 60% profit."""
        # Get weekly Delta 10 strike
        new_strike = self.ta_service.recommend_strike_price(
            symbol=position.symbol,
            option_type=position.option_type,
            expiration_weeks=1,
            probability_target=0.90
        )
        
        new_expiration = get_next_friday()
        
        return {
            'action': 'ROLL_WEEKLY',
            'position': position,
            'new_strike': new_strike,
            'new_expiration': new_expiration,
            'priority': 'medium',
            'reason': f'{position.profit_pct*100:.0f}% profit captured'
        }
    
    def _generate_pullback_rec(self, position, pull_back_data):
        """Generate pull-back recommendation."""
        return {
            'action': 'PULL_BACK',
            'position': position,
            'pull_back': pull_back_data,
            'priority': 'high',
            'reason': f'Can return to weekly income ({position.weeks_to_expiration} weeks early)'
        }
```

### 4.2 File Structure Changes

**V2.3 Structure:**
```
strategies/
├── strategies/
│   ├── roll_options.py (400 lines)
│   ├── early_roll_opportunity.py (200 lines)
│   ├── approaching_strike_alert.py (150 lines)
│   ├── new_covered_call.py (200 lines)
│   ├── earnings_alert.py (150 lines)
│   ├── dividend_alert.py (200 lines)
│   ├── sell_unsold_contracts.py (150 lines)
│   └── triple_witching_handler.py (300 lines)
├── itm_roll_optimizer.py (400 lines)
├── multi_week_optimizer.py (200 lines)
├── timing_optimizer.py (300 lines) ← DELETE
├── liquidity_checker.py (200 lines)
├── execution_advisor.py (200 lines)
├── technical_analysis.py (300 lines)
└── utils/
    └── option_calculations.py (200 lines)
```

**V3.0 Structure:**
```
strategies/
├── position_evaluator.py (300 lines) ← NEW: Single evaluator
├── strategies/
│   ├── earnings_alert.py (150 lines) ← Keep (risk management)
│   ├── dividend_alert.py (200 lines) ← Keep (risk management)
│   └── sell_unsold_contracts.py (150 lines) ← Keep (income opportunity)
├── zero_cost_finder.py (250 lines) ← RENAMED/REFACTORED from multi_week_optimizer
├── pull_back_detector.py (150 lines) ← NEW
├── liquidity_checker.py (200 lines) ← Keep
├── execution_advisor.py (200 lines) ← Keep
├── technical_analysis.py (300 lines) ← Keep
└── utils/
    └── option_calculations.py (200 lines) ← Keep
```

**Net change:** ~1,750 lines → ~1,000 lines (43% reduction)

---

## 5. Position States & Logic

### 5.1 Three Core States

Every position is in exactly ONE state:

```
┌─────────────────────────────────────────────────────────────┐
│                   POSITION EVALUATOR                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. FAR-DATED & CAN PULL BACK?                              │
│     ├─ YES → Recommend pull-back to weekly                  │
│     └─ NO  → Continue to state 2                            │
│                                                              │
│  2. IN THE MONEY?                                           │
│     ├─ YES → Find zero-cost roll (≤12 months)               │
│     │         ├─ Found  → Recommend roll                    │
│     │         └─ Not found → CATASTROPHIC CLOSE             │
│     └─ NO  → Continue to state 3                            │
│                                                              │
│  3. PROFITABLE (≥60%) AND OTM?                              │
│     ├─ YES → Recommend weekly roll                          │
│     └─ NO  → No action                                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Decision Trees

#### State 1: Pull-Back Check

```python
if position.weeks_to_expiration > 2:
    current_value = position.current_premium
    weekly_strike = get_delta_10_strike(symbol)
    weekly_premium = get_premium(weekly_strike, next_friday)
    net_cost = current_value - weekly_premium
    max_debit = position.original_premium * 0.20
    
    if net_cost <= max_debit:
        → RECOMMEND PULL-BACK
    else:
        → Continue to State 2
```

#### State 2: ITM Escape

```python
if position.is_itm():
    max_debit = position.original_premium * 0.20
    
    # Scan expirations: 1w, 2w, 3w, 4w, 6w, 8w, 12w, 16w, 24w, 36w, 48w
    for weeks in [1, 2, 3, 4, 6, 8, 12, 16, 24, 36, 48]:
        if weeks > 48:  # Max 12 months
            break
        
        exp_date = calculate_expiration(weeks)
        strike = get_best_strike(exp_date)
        new_premium = get_premium(strike, exp_date)
        net_cost = position.current_premium - new_premium
        
        if net_cost <= max_debit:
            → RECOMMEND ROLL to this expiration
            return  # Found it, stop searching
    
    # Loop completed without finding acceptable roll
    → CATASTROPHIC CLOSE (cannot escape within 12 months)
```

#### State 3: Weekly Roll

```python
if not position.is_itm() and position.profit_pct >= 0.60:
    new_strike = get_delta_10_strike(symbol)
    new_expiration = next_friday()
    
    → RECOMMEND WEEKLY ROLL
```

### 5.3 Special Cases

#### Earnings Conflict
```python
# When finding zero-cost roll, skip expirations that span earnings
for weeks in durations:
    exp_date = calculate_expiration(weeks)
    
    if has_earnings_between(today, exp_date):
        continue  # Skip this expiration, try next one
    
    # ... normal zero-cost check
```

#### Dividend Conflict
```python
# When finding zero-cost roll, skip expirations near ex-div date
for weeks in durations:
    exp_date = calculate_expiration(weeks)
    
    if has_ex_div_between(today, exp_date):
        continue  # Skip this expiration, try next one
    
    # ... normal zero-cost check
```

#### Liquidity Filter
```python
# After finding candidate roll, check liquidity
zero_cost_roll = find_zero_cost_roll(...)

if zero_cost_roll:
    liquidity = check_liquidity(
        symbol=symbol,
        strike=zero_cost_roll['strike'],
        expiration=zero_cost_roll['expiration']
    )
    
    if liquidity['overall'] == 'poor':
        # Try next expiration in sequence
        continue
    
    return zero_cost_roll  # Acceptable
```

---

## 6. Scan Schedule

### 6.1 Five Daily Scans (Pacific Time)

All times in Pacific (user's timezone)

#### Scan 1: 6:00 AM - Main Daily Scan 📊

**Purpose:** Comprehensive evaluation before user wakes up

**What it evaluates:**
- All positions (comprehensive)
- Roll recommendations (ITM, profitable, pull-backs)
- New sell opportunities (closed positions)
- Earnings alerts (next 5 days)
- Dividend alerts (next 7 days)

**Notification sent:** 6:00 AM  
**User sees:** 6:30 AM (when waking up)  
**Action window:** 6:30-8:00 AM (before school drop-off)

```python
def scan_6am():
    """Main comprehensive scan."""
    recommendations = []
    
    for position in get_all_positions():
        # Evaluate position
        rec = evaluator.evaluate(position)
        if rec:
            recommendations.append(rec)
    
    # Check for earnings/dividends
    recommendations.extend(check_earnings_alerts())
    recommendations.extend(check_dividend_alerts())
    
    # Check for new sell opportunities
    recommendations.extend(check_sell_opportunities())
    
    # Send all recommendations
    send_notification(recommendations, priority='daily_comprehensive')
```

---

#### Scan 2: 8:00 AM - Post-Opening Scan 🚨

**Purpose:** Catch urgent changes from market open volatility

**What it evaluates:**
- State changes only (OTM → ITM, new pull-back opportunities)
- Significant gaps (>10% deeper ITM)
- Earnings TODAY
- Expiring TODAY

**Notification sent:** 8:00 AM (if urgent items found)  
**User sees:** 8:15 AM (arriving at office)  
**Action window:** 8:15 AM - noon

```python
def scan_8am():
    """Urgent state changes from market open."""
    morning_state = load_6am_scan_state()  # What positions looked like at 6 AM
    urgent_items = []
    
    for position in get_all_positions():
        current_state = get_current_state(position)
        
        # Check for urgent state changes
        urgent = check_8am_urgent(position, morning_state[position.id])
        
        if urgent:
            urgent_items.extend(urgent)
    
    # Only send if there are urgent items
    if urgent_items:
        send_notification(urgent_items, priority='urgent')
```

---

#### Scan 3: 12:00 PM - Midday Scan 🔄

**Purpose:** Check for intraday opportunities and significant moves

**What it evaluates:**
- Pull-back opportunities (stock dropped, can pull back)
- Significant intraday moves (>10% since morning)
- Position updates

**Notification sent:** 12:00 PM (if significant changes)  
**User sees:** Noon (lunch time)  
**Action window:** 12:00-1:00 PM

```python
def scan_12pm():
    """Midday opportunities and significant changes."""
    morning_state = load_6am_scan_state()
    am_state = load_8am_scan_state()
    significant_changes = []
    
    for position in get_all_positions():
        # Check for pull-back opportunities
        if position.weeks_to_expiration > 2:
            pull_back = check_pull_back_opportunity(position)
            if pull_back and not was_pullback_available_this_morning(position):
                significant_changes.append(pull_back)
        
        # Check for significant moves
        move_since_morning = calculate_move_since(position, morning_state)
        if abs(move_since_morning) > 10:
            significant_changes.append({
                'type': 'SIGNIFICANT_MOVE',
                'position': position,
                'move_pct': move_since_morning
            })
    
    # Only send if significant
    if significant_changes:
        send_notification(significant_changes, priority='medium')
```

---

#### Scan 4: 12:45 PM - Pre-Close Urgent Scan ⏰

**Purpose:** Last chance actions before market close (1:00 PM Pacific)

**What it evaluates:**
- Positions expiring TODAY
- Triple Witching alerts (if quarterly expiration)
- Last-minute urgent actions only

**Notification sent:** 12:45 PM (only if expiring positions or critical)  
**User sees:** 15 minutes before market close  
**Action window:** 12:45-1:00 PM

```python
def scan_1245pm():
    """Last chance before market close."""
    urgent_close_items = []
    
    # Check for expiring positions
    expiring_today = [p for p in get_all_positions() if p.days_to_expiration == 0]
    
    for position in expiring_today:
        if position.is_itm():
            urgent_close_items.append({
                'type': 'EXPIRES_TODAY_ITM',
                'position': position,
                'action': 'Roll or accept assignment - LAST 15 MINUTES',
                'priority': 'urgent'
            })
    
    # Check for Triple Witching
    if is_triple_witching_today():
        urgent_close_items.extend(generate_triple_witching_alerts())
    
    # Only send if urgent
    if urgent_close_items:
        send_notification(urgent_close_items, priority='critical')
```

---

#### Scan 5: 8:00 PM - Evening Planning Scan 📅

**Purpose:** Prepare for next day, no immediate action needed

**What it evaluates:**
- Earnings TOMORROW
- Ex-dividend TOMORROW
- Positions expiring TOMORROW
- Planning information only

**Notification sent:** 8:00 PM  
**User sees:** Evening  
**Action window:** Mental preparation, action tomorrow

```python
def scan_8pm():
    """Next day planning - informational only."""
    tomorrow_events = []
    
    # Earnings tomorrow
    for position in get_all_positions():
        if position.has_earnings_tomorrow():
            tomorrow_events.append({
                'type': 'EARNINGS_TOMORROW',
                'position': position,
                'info': 'Be aware - earnings before market open'
            })
        
        if position.has_ex_div_tomorrow():
            tomorrow_events.append({
                'type': 'EX_DIV_TOMORROW',
                'position': position,
                'info': 'Ex-dividend date tomorrow'
            })
        
        if position.days_to_expiration == 1:
            tomorrow_events.append({
                'type': 'EXPIRES_TOMORROW',
                'position': position,
                'info': 'Position expires tomorrow'
            })
    
    # Send as informational (low priority)
    if tomorrow_events:
        send_notification(tomorrow_events, priority='info')
```

---

### 6.2 Smart Filtering Implementation

```python
# Global scan filter (resets at midnight)
scan_filter = SmartScanFilter()

def daily_midnight_reset():
    """Called at 12:01 AM to reset filter for new day."""
    scan_filter.reset_daily()

def run_scan(scan_func, scan_name):
    """
    Wrapper for all scans - handles filtering.
    """
    recommendations = scan_func()
    
    filtered_recs = []
    for rec in recommendations:
        position_id = rec['position'].id
        
        if scan_filter.should_send(position_id, rec):
            filtered_recs.append(rec)
        else:
            logger.debug(f"{scan_name}: Skipping duplicate for {position_id}")
    
    if filtered_recs:
        send_notification(filtered_recs, scan_name=scan_name)
    
    return filtered_recs

# Usage
def scheduler():
    run_scan(scan_6am, "6AM_MAIN")
    # ... wait until 8 AM
    run_scan(scan_8am, "8AM_URGENT")
    # ... etc
```

---

## 7. Configuration

### 7.1 Simplified Config (12 parameters)

**V2.3 had 50+ parameters. V3.0 has 12.**

```python
# config/algorithm_config.py

ALGORITHM_CONFIG = {
    # Core thresholds
    "profit_threshold": 0.60,              # Roll when 60%+ profit captured
    "max_debit_pct": 0.20,                 # Max debit = 20% of original premium
    "max_roll_months": 12,                 # Never roll beyond 12 months
    
    # Strike selection
    "delta_target": 0.10,                  # Delta 10 (90% OTM probability)
    
    # Pull-back
    "min_weeks_for_pullback": 2,           # Only pull back if >2 weeks out
    
    # Earnings/Dividend awareness
    "earnings_lookback_days": 5,           # Alert if earnings within 5 days
    "dividend_lookback_days": 7,           # Alert if ex-div within 7 days
    
    # Liquidity thresholds
    "min_open_interest": 50,               # Warn if OI < 50
    "max_spread_pct": 10,                  # Warn if spread > 10%
    
    # Scan schedule (Pacific time)
    "scan_times": {
        "main": "06:00",
        "post_open": "08:00",
        "midday": "12:00",
        "pre_close": "12:45",
        "evening": "20:00"
    },
    
    # 8 AM urgency threshold
    "urgent_deepening_threshold": 10,      # Alert if >10% deeper ITM
    
    # Special dates
    "triple_witching_months": [3, 6, 9, 12]  # Mar, Jun, Sep, Dec
}
```

### 7.2 Removed Configurations

All of these are DELETED:

```python
# REMOVED - No longer used
"normal_profit_threshold": 0.60           # Redundant with profit_threshold
"earnings_week_profit_threshold": 0.45    # No special earnings threshold
"short_dte_threshold": 0.35               # No DTE-based thresholds
"catastrophic_itm_pct": 20.0              # No ITM% thresholds
"deep_itm_pct": 10.0                      # No ITM% thresholds
"normal_close_threshold_pct": 5.0         # No ITM% thresholds
"triple_witching_close_threshold_pct": 3.0 # No special TW threshold
"max_debit_pct_earnings": 0.75            # No special earnings debit
"max_debit_pct_high_profit": 0.15         # No special profit debit
"max_debit_pct_expiring_soon": 1.0        # No special expiring debit
"scenario_comparison_tolerance": 0.90     # No scenario comparison
"min_savings_to_wait": 0.10               # No savings threshold
"min_roll_savings_dollars": 50            # No savings threshold
"min_roll_savings_percent": 10            # No savings threshold
"min_strike_variation_pct": 2.0           # No strike variation check
"max_roll_weeks_standard": 2              # No max weeks limits
"max_roll_weeks_preemptive": 3            # No max weeks limits
"max_roll_weeks_deep_itm": 6              # No max weeks limits
"min_marginal_premium": 0.15              # No marginal premium check
"mean_reversion_expected_days": 5         # No mean reversion prediction
"approaching_threshold_pct": 3.0          # No approaching strike logic
"urgent_threshold_pct": 1.5               # No approaching strike logic
"min_days_to_expiration": 2               # No min DTE check
"momentum_lookback_days": 3               # No momentum check
"min_volume_multiple": 1.2                # No volume check
"enable_timing_optimization": False       # Deleted entirely
"friday_cutoff_time": "14:00"             # No timing optimization
"min_premium_pct_of_stock": 0.003         # No timing optimization
"low_vix_threshold": 15                   # No timing optimization
"avoid_morning_chaos": False              # No timing optimization
# ... 15 more timing-related params deleted
```

---

## 8. Implementation Chunks

### Chunk 1: Cleanup & Simplify New Covered Call

**Goal:** Remove timing optimization, simplify new call recommendations

**Files to modify:**
- `strategies/new_covered_call.py`

**Files to delete:**
- `timing_optimizer.py` (if it exists)

**Changes:**
1. Remove all imports of `timing_optimizer`
2. Remove `evaluate_timing_opportunity()` call block
3. Keep only TA-based wait logic (`should_wait_to_sell()`)
4. Simplify to: Check TA → Wait or Sell

**Validation:**
- Run test: Closed position → Should recommend selling new call
- Verify no timing predictions in output
- Check that TA waits still work (RSI < 30, at support)

**Estimated effort:** 1 hour  
**Risk:** Low (pure deletion)

---

### Chunk 2: Remove ITM Thresholds & Simplify Cost Logic

**Goal:** Remove all threshold enforcement, simplify to 20% rule

**Files to modify:**
- `strategies/roll_options.py`
- `itm_roll_optimizer.py`
- `triple_witching_handler.py`
- `utils/option_calculations.py`

**Changes:**

1. **Delete threshold functions:**
   ```python
   # DELETE these entirely
   def should_close_itm_position_by_threshold()
   def check_itm_thresholds()
   def evaluate_roll_economics()
   def validate_roll_options()
   ```

2. **Simplify ITM handling in roll_options.py:**
   ```python
   # BEFORE: Complex decision tree
   threshold = check_itm_thresholds()
   if threshold['should_close']: ...
   
   # AFTER: Simple zero-cost finder
   zero_cost = find_zero_cost_roll(position, max_debit)
   if zero_cost:
       return recommend_roll(zero_cost)
   else:
       return recommend_close("Cannot escape within 12 months")
   ```

3. **Update cost validation:**
   ```python
   # BEFORE: 7 different cost rules
   if net_debit > new_premium * 0.50: REJECT
   # ... plus 6 more exceptions
   
   # AFTER: One rule
   max_debit = position.original_premium * 0.20
   if net_debit <= max_debit:
       ACCEPT
   ```

4. **Remove from config:**
   - All ITM threshold percentages
   - All cost sensitivity exceptions
   - Economic sanity check parameters

**Validation:**
- Test ITM position: Should find zero-cost roll (not close at 5% ITM)
- Test 15% ITM position: Should find longer-dated roll
- Test 50% ITM position: Should try up to 12 months, then close if can't escape
- Verify no "CLOSE_DONT_ROLL" recommendations for <12 month escapable positions

**Estimated effort:** 3 hours  
**Risk:** Medium (logic changes, but well-defined)

---

### Chunk 3: Repurpose Multi-Week Optimizer to Zero-Cost Finder

**Goal:** Change from scoring best to finding shortest zero-cost

**Files to modify:**
- `multi_week_optimizer.py` → Rename to `zero_cost_finder.py`
- `itm_roll_optimizer.py` (calls to multi-week)
- `roll_options.py` (calls to multi-week)

**Changes:**

1. **Rename file:**
   ```
   multi_week_optimizer.py → zero_cost_finder.py
   ```

2. **Replace scoring logic with sequential search:**
   ```python
   # BEFORE: Score all, pick best
   def find_optimal_roll_expiration():
       for weeks in range(1, max_weeks + 1):
           score = calculate_score(weeks)
       return highest_scored
   
   # AFTER: Find first acceptable
   def find_zero_cost_roll(position, max_debit, max_months=12):
       durations = [1, 2, 3, 4, 6, 8, 12, 16, 24, 36, 48]  # weeks
       
       for weeks in durations:
           if weeks > (max_months * 4):
               break
           
           net_cost = calculate_roll_cost(weeks)
           
           if net_cost <= max_debit:
               return build_roll_recommendation(weeks)
       
       return None  # Cannot escape within max_months
   ```

3. **Update callers:**
   ```python
   # Change all calls from:
   optimal = multi_week_optimizer.find_optimal_roll_expiration(...)
   
   # To:
   zero_cost = zero_cost_finder.find_zero_cost_roll(position, max_debit, 12)
   ```

4. **Extend duration scan:**
   - V2.3: Scanned 1-3 weeks
   - V3.0: Scan 1-48 weeks (12 months)

**Validation:**
- Test 5% ITM: Should find 1-2 week roll
- Test 20% ITM: Should find 6-8 week roll
- Test 40% ITM: Should find 24+ week roll or fail gracefully
- Verify returns SHORTEST acceptable duration, not highest scored

**Estimated effort:** 2 hours  
**Risk:** Medium (refactor existing optimizer)

---

### Chunk 4: Add Pull-Back Detector & Consolidate Evaluator

**Goal:** New pull-back feature + single position evaluator

**Files to create:**
- `pull_back_detector.py` (new)
- `position_evaluator.py` (new)

**Files to modify:**
- Main scan scheduler
- `roll_options.py` (integrate with evaluator)

**Changes:**

1. **Create pull_back_detector.py:**
   ```python
   def check_pull_back_opportunity(position):
       """
       Check if far-dated position can return to weekly.
       Returns pull-back recommendation or None.
       """
       # Only check positions >2 weeks out
       if position.weeks_to_expiration <= 2:
           return None
       
       # Get weekly option details
       weekly_strike = get_delta_10_strike(position.symbol)
       weekly_premium = get_premium(weekly_strike, next_friday())
       
       # Calculate cost
       current_value = position.current_premium
       net_cost = current_value - weekly_premium
       max_debit = position.original_premium * 0.20
       
       # Check if acceptable
       if net_cost <= max_debit:
           return build_pullback_recommendation(...)
       
       return None
   ```

2. **Create position_evaluator.py:**
   ```python
   class PositionEvaluator:
       def evaluate(self, position):
           # State 1: Pull-back?
           pull_back = check_pull_back_opportunity(position)
           if pull_back:
               return pull_back
           
           # State 2: ITM?
           if position.is_itm():
               return handle_itm_position(position)
           
           # State 3: Profitable?
           if position.profit_pct >= 0.60:
               return handle_profitable_position(position)
           
           return None
   ```

3. **Update scan scheduler:**
   ```python
   # Replace individual strategy calls with:
   evaluator = PositionEvaluator()
   
   for position in positions:
       rec = evaluator.evaluate(position)
       if rec and scan_filter.should_send(position.id, rec):
           recommendations.append(rec)
   ```

4. **Implement 5-scan schedule:**
   - 6 AM: Main scan (comprehensive)
   - 8 AM: Urgent state changes
   - 12 PM: Midday opportunities
   - 12:45 PM: Pre-close urgent
   - 8 PM: Next day planning

**Validation:**
- Test far-dated position (8 weeks out): Should check pull-back daily
- Test pull-back trigger: Stock drops, position can return to weekly
- Test scan filtering: Same recommendation not sent twice in same day
- Verify all 5 scans run at correct times

**Estimated effort:** 4 hours  
**Risk:** Medium (new code + integration)

---

### Implementation Order

```
Day 1: Chunk 1 (Cleanup)
├─ Remove timing_optimizer
├─ Simplify new_covered_call
└─ Validate: Recommendations still work

Day 2: Chunk 2 (ITM Simplification)  
├─ Remove thresholds
├─ Simplify cost logic to 20% rule
└─ Validate: ITM handling works

Day 3: Chunk 3 (Zero-Cost Finder)
├─ Refactor multi_week → zero_cost_finder
├─ Update callers
└─ Validate: Finds shortest duration

Day 4: Chunk 4 (Pull-Back & Evaluator)
├─ Create pull_back_detector
├─ Create position_evaluator
├─ Implement scan schedule
└─ Validate: Full system test
```

---

## 9. Migration Guide

### 9.1 Testing Strategy

**Before implementing each chunk:**
1. Create test cases for current behavior
2. Implement chunk
3. Run tests, verify behavior matches V3 spec
4. Manual test with real positions
5. Commit

**Test cases needed:**

**Chunk 1 tests:**
- Closed position → Recommend sell (no timing suggestions)
- Oversold stock (RSI < 30) → Wait recommendation
- Normal stock → Sell recommendation

**Chunk 2 tests:**
- 3% ITM position → Find zero-cost roll (don't close)
- 15% ITM position → Find longer roll
- 50% ITM position → Try up to 12 months
- Verify max debit = 20% of original premium

**Chunk 3 tests:**
- 5% ITM → Find 1-2 week roll
- 20% ITM → Find 4-8 week roll
- 40% ITM → Find 12+ week roll
- Verify returns SHORTEST acceptable

**Chunk 4 tests:**
- Far-dated (8 weeks) → Check pull-back daily
- Stock drops → Pull-back triggers
- Multiple scans same day → No duplicate notifications
- 5 scans run at correct times

### 9.2 Rollback Plan

Each chunk is independent and can be rolled back:

```
Chunk 1 fails → Restore timing_optimizer.py, revert new_covered_call.py
Chunk 2 fails → Restore threshold functions, revert to V2.3 cost logic
Chunk 3 fails → Restore multi_week_optimizer.py, revert callers
Chunk 4 fails → Remove new files, restore old scan schedule
```

**Recommendation:** Commit after each chunk with clear message:
```
git commit -m "V3 Chunk 1: Remove timing optimization"
git commit -m "V3 Chunk 2: Simplify ITM to 20% rule"
git commit -m "V3 Chunk 3: Zero-cost roll finder"
git commit -m "V3 Chunk 4: Pull-back detector and unified evaluator"
```

### 9.3 Configuration Migration

**Old config (V2.3):**
```python
"profit_threshold": 0.60,
"catastrophic_itm_pct": 20.0,
"deep_itm_pct": 10.0,
"normal_close_threshold_pct": 5.0,
# ... 46 more parameters
```

**New config (V3.0):**
```python
"profit_threshold": 0.60,
"max_debit_pct": 0.20,
"max_roll_months": 12,
# ... 9 more parameters (12 total)
```

**Migration script:**
```python
def migrate_config_v2_to_v3(old_config):
    """Convert V2.3 config to V3.0 format."""
    return {
        # Core thresholds
        "profit_threshold": old_config.get("profit_threshold", 0.60),
        "max_debit_pct": 0.20,  # New parameter
        "max_roll_months": 12,  # New parameter
        
        # Strike selection (unchanged)
        "delta_target": old_config.get("delta_target", 0.10),
        
        # Pull-back (new)
        "min_weeks_for_pullback": 2,
        
        # Earnings/Dividend (unchanged)
        "earnings_lookback_days": old_config.get("earnings_lookback_days", 5),
        "dividend_lookback_days": old_config.get("dividend_lookback_days", 7),
        
        # Liquidity (simplified)
        "min_open_interest": old_config.get("min_open_interest", 50),
        "max_spread_pct": old_config.get("max_spread_pct", 10),
        
        # Scan times (new structure)
        "scan_times": {
            "main": "06:00",
            "post_open": "08:00",
            "midday": "12:00",
            "pre_close": "12:45",
            "evening": "20:00"
        },
        
        # 8 AM urgency (new)
        "urgent_deepening_threshold": 10,
        
        # Special dates (unchanged)
        "triple_witching_months": [3, 6, 9, 12]
    }
```

---

## 10. Success Criteria

### 10.1 Functional Requirements

✅ **Core Functionality:**
- Weekly covered calls at Delta 10 when OTM and profitable
- Zero-cost rolls for ITM positions (up to 12 months)
- Pull-back from far-dated to weekly when possible
- Earnings/dividend alerts for risk management
- 5 daily scans at specified times

✅ **Behavior Changes:**
- No premature closes based on ITM% (except catastrophic)
- Accepts small debits (≤20% of original premium)
- No timing predictions (Monday bumps, FOMC, etc.)
- Single recommendation per position per day
- No conflicting recommendations

### 10.2 Performance Requirements

✅ **Efficiency:**
- Daily scans complete in <30 seconds
- No duplicate notifications within same day
- Zero-cost finder checks up to 12 months in <5 seconds

✅ **Reliability:**
- No race conditions between scans
- Consistent behavior across all positions
- Graceful handling of missing data

### 10.3 Code Quality

✅ **Maintainability:**
- 60% reduction in code lines
- Clear single-responsibility modules
- Comprehensive unit tests (40+ tests)
- Well-documented decision logic

✅ **Testability:**
- Each chunk independently testable
- Clear success/failure criteria
- Easy to add new test cases

---

## 11. Future Enhancements (Post-V3)

**Not included in V3.0, but potential future additions:**

### 11.1 Machine Learning Strike Selection
- Train model on historical success rates
- Optimize Delta target based on stock volatility
- Adaptive strike selection

### 11.2 Tax Optimization
- Wash sale detection and warnings
- Holding period tracking (short-term vs long-term)
- Tax-loss harvesting suggestions

### 11.3 Position Sizing Alerts
- Alert when position becomes >X% of portfolio
- Suggest reducing position size
- Portfolio-level risk management

### 11.4 Advanced Technical Analysis
- Custom indicator combinations
- Backtesting capabilities
- Strategy performance metrics per stock

---

## Appendix A: V2.3 vs V3.0 Comparison

| Feature | V2.3 | V3.0 | Change |
|---------|------|------|--------|
| **Lines of Code** | ~2,500 | ~1,000 | -60% |
| **Strategy Files** | 10 | 4 | -60% |
| **Config Parameters** | 50+ | 12 | -76% |
| **Position States** | ~15 | 3 | -80% |
| **ITM Thresholds** | 4 (20%, 10%, 5%, 3%) | 0 | -100% |
| **Cost Rules** | 7 different scenarios | 1 simple rule | -86% |
| **Max Roll Duration** | 3 weeks (standard) | 12 months | +400% |
| **Timing Predictions** | Yes (Monday, FOMC, VIX) | No | Removed |
| **Pull-Back Feature** | No | Yes | New |
| **Daily Scans** | 5 (uncoordinated) | 5 (coordinated) | Improved |
| **Scan Filtering** | Basic dedup | Smart state tracking | Enhanced |
| **Race Conditions** | Possible | Eliminated | Fixed |
| **Conflicting Recs** | Possible | Eliminated | Fixed |

---

## Appendix B: File Deletion Checklist

**Files to DELETE in V3.0:**

- [ ] `timing_optimizer.py`
- [ ] `performance_tracker.py` (if exists)
- [ ] `approaching_strike_alert.py` (merged into evaluator)
- [ ] `early_roll_opportunity.py` (merged into evaluator)

**Files to RENAME:**

- [ ] `multi_week_optimizer.py` → `zero_cost_finder.py`

**Files to CREATE:**

- [ ] `position_evaluator.py`
- [ ] `pull_back_detector.py`

**Files to KEEP (modified):**

- [ ] `roll_options.py` (simplified)
- [ ] `itm_roll_optimizer.py` (simplified)
- [ ] `new_covered_call.py` (simplified)
- [ ] `earnings_alert.py` (unchanged)
- [ ] `dividend_alert.py` (unchanged)
- [ ] `sell_unsold_contracts.py` (unchanged)
- [ ] `triple_witching_handler.py` (simplified)
- [ ] `technical_analysis.py` (unchanged)
- [ ] `liquidity_checker.py` (unchanged)
- [ ] `execution_advisor.py` (unchanged)
- [ ] `utils/option_calculations.py` (simplified)

---

## Appendix C: Configuration Reference

**Complete V3.0 configuration:**

```python
# config/algorithm_config.py

ALGORITHM_CONFIG_V3 = {
    # ===== CORE THRESHOLDS =====
    "profit_threshold": 0.60,
    # Roll weekly when 60%+ profit captured
    
    "max_debit_pct": 0.20,
    # Maximum acceptable debit = 20% of original premium
    # This is the ONLY cost rule
    
    "max_roll_months": 12,
    # Never roll beyond 12 months
    # If can't escape in 12 months → Close position
    
    # ===== STRIKE SELECTION =====
    "delta_target": 0.10,
    # Delta 10 = 90% probability OTM
    # Used for all new sells and weekly rolls
    
    # ===== PULL-BACK =====
    "min_weeks_for_pullback": 2,
    # Only check pull-back for positions >2 weeks out
    # Don't pull back 3-week to 1-week (not worth it)
    
    # ===== RISK MANAGEMENT =====
    "earnings_lookback_days": 5,
    # Alert if earnings within 5 trading days
    
    "dividend_lookback_days": 7,
    # Alert if ex-dividend within 7 days
    
    # ===== LIQUIDITY =====
    "min_open_interest": 50,
    # Warn if open interest < 50 contracts
    
    "max_spread_pct": 10,
    # Warn if bid-ask spread > 10%
    
    # ===== SCAN SCHEDULE (Pacific Time) =====
    "scan_times": {
        "main": "06:00",          # Comprehensive daily scan
        "post_open": "08:00",     # Urgent state changes
        "midday": "12:00",        # Pull-backs and opportunities
        "pre_close": "12:45",     # Last chance actions
        "evening": "20:00"        # Next day planning
    },
    
    # ===== URGENCY THRESHOLDS =====
    "urgent_deepening_threshold": 10,
    # Alert at 8 AM if position >10% deeper ITM than 6 AM
    
    # ===== SPECIAL DATES =====
    "triple_witching_months": [3, 6, 9, 12]
    # March, June, September, December
    # 3rd Friday = Triple Witching Day
}
```

---

---

## Appendix D: ADDENDUM & CORRECTIONS (December 21, 2024)

**Priority:** HIGH - Critical corrections to original specification

### D.1 Strike Selection Strategy - CORRECTED

**Original V3 Spec (INCORRECT):**
> All strikes use Delta 10 (90% OTM probability)

**CORRECTED Strategy:**

| Situation | Strike Target | Probability OTM | Rationale |
|-----------|---------------|-----------------|-----------|
| **Weekly rolls** (OTM, profitable) | **Delta 10** | **90%** | Maximum safety for income generation |
| **ITM rolls** (in trouble, escaping) | **Delta 30** | **70%** | Minimize time needed, still safe |
| **Pull-backs** (returning to income) | **Delta 30** | **70%** | Balance speed and safety |

**Code Update Required:**

```python
# In zero_cost_finder.py and pull_back_detector.py

def get_best_strike_for_expiration(symbol, expiration, option_type, position_state):
    """
    Get appropriate strike based on position state.
    
    Args:
        position_state: 'weekly', 'itm_escape', or 'pullback'
    """
    
    if position_state == 'weekly':
        # Standard weekly income generation
        return ta_service.recommend_strike_price(
            symbol=symbol,
            option_type=option_type,
            expiration=expiration,
            probability_target=0.90  # Delta 10
        )
    
    elif position_state in ['itm_escape', 'pullback']:
        # ITM rolls or pull-backs - minimize time
        return ta_service.recommend_strike_price(
            symbol=symbol,
            option_type=option_type,
            expiration=expiration,
            probability_target=0.70  # Delta 30
        )
```

**Rationale:**
- When OTM and profitable: Use Delta 10 (conservative, maximum safety)
- When ITM (in trouble): Use Delta 30 to minimize weeks needed for zero-cost escape
- Delta 30 = ~70% OTM probability = "just slightly outside the money"
- Still safe, but closer to current price = higher premiums = shorter escape time

---

### D.2 Maximum Roll Duration - CORRECTED

**Original:** 48 weeks (~11 months)  
**Corrected:** 52 weeks (exactly 1 year)

```python
for weeks in [1, 2, 3, 4, 6, 8, 12, 16, 24, 36, 52]:
    # 52 weeks = exactly 1 year
```

---

### D.3 Pull-Back Logic - ENHANCED

**Original (INCOMPLETE):**
> Check if can pull back to weekly (1 week out)

**CORRECTED Logic:**
> Check ALL intermediate expirations between 1 week and current expiration  
> Find SHORTEST duration achieving cost-neutral  
> Pull back to that expiration (doesn't have to be weekly)

**Example:**
```
Position in 8 weeks → Check: 1w, 2w, 3w, 4w, 5w, 6w, 7w

1 week:  $0.30 debit (too expensive) ✗
2 weeks: $0.18 debit (≤20% threshold) ✓ ACCEPT

Recommendation: Pull back from 8 weeks → 2 weeks (not all the way to 1 week)
```

**Pull-Back Threshold:** Check ANY position >1 week out (not just >2 weeks)

**Updated Code:**
```python
def check_pull_back_opportunity(position):
    """
    Scan ALL expirations between 1 week and current expiration.
    Find SHORTEST that achieves cost-neutral.
    """
    
    current_weeks = position.weeks_to_expiration
    
    # Only check if >1 week out (not >2 weeks)
    if current_weeks <= 1:
        return None
    
    # Check all intermediate expirations
    durations = [1, 2, 3, 4, 6, 8, 12, 16, 24, 36, 52]
    
    for weeks in durations:
        if weeks >= current_weeks:
            break  # Don't check expirations at or beyond current
        
        exp_date = calculate_expiration(weeks)
        
        # Use Delta 30 for pull-backs
        new_strike = ta_service.recommend_strike_price(
            symbol=position.symbol,
            option_type=position.option_type,
            expiration=exp_date,
            probability_target=0.70  # Delta 30
        )
        
        new_premium = get_option_premium(new_strike, exp_date)
        current_value = position.current_premium
        net_cost = current_value - new_premium
        max_debit = position.original_premium * 0.20
        
        if net_cost <= max_debit:
            # Found shortest acceptable pull-back
            return {
                'action': 'PULL_BACK',
                'from_expiration': position.expiration,
                'from_weeks': current_weeks,
                'to_expiration': exp_date,
                'to_weeks': weeks,
                'new_strike': new_strike,
                'net_cost': net_cost,
                'benefit': f'Return to income {current_weeks - weeks} weeks early'
            }
    
    return None
```

---

### D.4 Earnings Handling - CLARIFIED

**Skip Logic:** Skip ONLY the earnings week itself, not weeks before/after.

```python
def should_skip_expiration_for_earnings(symbol, exp_date):
    """
    Skip ONLY the earnings week itself.
    Do NOT skip weeks before or after.
    """
    
    earnings_date = get_next_earnings_date(symbol)
    
    if not earnings_date:
        return False  # No earnings scheduled
    
    # Get the week of earnings
    earnings_week_start = get_week_start(earnings_date)
    earnings_week_end = get_week_end(earnings_date)
    
    # Check if expiration falls IN the earnings week
    if earnings_week_start <= exp_date <= earnings_week_end:
        return True  # Skip this expiration
    
    return False  # OK to use this expiration
```

**Edge Case - Excessive Earnings:**

```python
def detect_excessive_earnings(symbol):
    """
    If stock has earnings scheduled every week (edge case),
    recommend selling the entire holding.
    """
    
    earnings_dates = get_earnings_schedule_next_quarter(symbol)
    
    if len(earnings_dates) >= 10:  # 10+ earnings in next 13 weeks
        return {
            'action': 'SELL_HOLDING',
            'reason': 'EXCESSIVE_VOLATILITY',
            'message': (
                f'{symbol} has earnings scheduled {len(earnings_dates)} times '
                f'in the next quarter. This is too volatile for our strategy. '
                f'Recommend closing entire position.'
            ),
            'priority': 'urgent'
        }
    
    return None
```

---

### D.5 Summary of Corrections

| Item | Original | Corrected |
|------|----------|-----------|
| **ITM roll delta** | Delta 10 (90%) | **Delta 30 (70%)** |
| **Pull-back delta** | Delta 10 (90%) | **Delta 30 (70%)** |
| **Weekly roll delta** | Delta 10 (90%) | Delta 10 (90%) ✓ unchanged |
| **Max duration** | 48 weeks | **52 weeks** |
| **Pull-back threshold** | >2 weeks | **>1 week** |
| **Pull-back target** | Weekly only | **Shortest acceptable** |
| **Earnings skip** | Unclear | **Earnings week only** |

---

### D.6 Expected Behavior Examples

**Example 1: ITM Roll**
- NVDA $500 call, stock at $550 (10% ITM)
- Original (Delta 10): $605 strike → Need 8+ weeks
- Corrected (Delta 30): $570 strike → Need 3-4 weeks ✓ Better!

**Example 2: Pull-Back**
- AAPL call in 8 weeks, stock dropped
- Original: Can pull back to 1 week? No → No recommendation
- Corrected: 1w (✗), 2w (✓) → Pull back to 2 weeks ✓ Better!

**Example 3: Weekly Roll (No Change)**
- AAPL $180 call, 65% profit, OTM
- Both versions: Delta 10 → $185 strike, weekly expiration ✓

---

**END OF V3.0 SPECIFICATION**
