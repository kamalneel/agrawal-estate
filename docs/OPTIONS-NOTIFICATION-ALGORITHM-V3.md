# OPTIONS NOTIFICATION & RECOMMENDATION ALGORITHM V3.0

**Version:** 3.0 → **3.3**  
**Status:** ✅ IMPLEMENTED  
**Created:** December 21, 2024  
**Last Updated:** January 7, 2026  
**Migration From:** V2.3  
**Philosophy:** Patient position management aligned with actual trading strategy

---

## 📚 Documentation Index

The V3 system is documented across **four files** for clarity:

| Document | Purpose | When to Read |
|----------|---------|--------------|
| **[V3-TRADING-PHILOSOPHY.md](./V3-TRADING-PHILOSOPHY.md)** | WHY we make decisions | Understanding the strategy |
| **[RECOMMENDATION-ENGINE.md](./RECOMMENDATION-ENGINE.md)** | HOW recommendations are generated | Debugging logic issues |
| **[NOTIFICATION-SYSTEM.md](./NOTIFICATION-SYSTEM.md)** | HOW we communicate to users | Fixing display issues |
| **This file** | Original V3 spec + history | Reference and migration notes |

### Quick Links

- **V3.3 Changes:** [V3.3-ADDENDUM.md](./V3.3-ADDENDUM.md)
- **Implementation Notes:** [V3-IMPLEMENTATION-NOTES.md](./V3-IMPLEMENTATION-NOTES.md)

### V3.3 Key Updates (Jan 2026)

- ✅ Weekly income priority (compress over extend)
- ✅ Mean reversion awareness (far-dated ITM handling)  
- ✅ Flexible ITM debit limits ($2-$5 based on severity)
- ✅ WAIT recommendations with technical analysis
- ✅ Schwab as primary data source

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Core Philosophy](#core-philosophy)
3. [Algorithm Overview](#algorithm-overview)
4. [Position States & Logic](#position-states--logic)
5. [Strike Selection Strategy](#strike-selection-strategy)
6. [Cost Rules](#cost-rules)
7. [Smart Assignment (IRA Only)](#smart-assignment-ira-only)
8. [Daily Scan Schedule](#daily-scan-schedule)
9. [Configuration Reference](#configuration-reference)
10. [Decision Trees](#decision-trees)
11. [Examples](#examples)
12. [Migration from V2](#migration-from-v2)

---

## Executive Summary

### What Changed from V2

**V2.3 Problems:**
- Over-engineered with 10 separate strategy files
- Multiple ITM thresholds (5%, 10%, 20%) forced premature closes
- Complex cost sensitivity rules rejected valid rolls
- Strategic timing predictions (Monday IV bumps, FOMC) added speculation
- Race conditions from overlapping strategies
- ~2,500 lines of code

**V3.0 Solutions:**
- Single unified evaluator with 3 clear states
- No ITM thresholds - only time-based catastrophic (cannot escape in 12 months)
- One simple cost rule: ≤20% of original premium
- No timing predictions - only real TA signals
- No race conditions - one recommendation per position
- ~1,000 lines of code (60% reduction)

### Key Metrics

| Metric | V2.3 | V3.0 | Improvement |
|--------|------|------|-------------|
| Lines of Code | ~2,500 | ~1,000 | -60% |
| Strategy Files | 10 | 1 evaluator | -90% |
| Config Parameters | 50+ | 12 | -76% |
| Decision States | ~15 | 3 | -80% |
| ITM Thresholds | 4 | 0 | -100% |
| Cost Rules | 7 scenarios | 1 rule | -86% |
| Race Conditions | Possible | Eliminated | 100% fixed |

---

## Core Philosophy

### User's Actual Trading Strategy

**Weekly Income Generation:**
- Sell weekly covered calls at Delta 10 (90% OTM probability)
- Target ~40 profitable weeks out of 52
- Portfolio: 15 volatile, long-term growth stocks

**When Stuck (ITM):**
- NEVER panic close based on ITM percentage
- Find zero-cost roll to ANY expiration needed (1 week to 12 months)
- 10% ITM → might need 2 weeks for zero cost
- 20% ITM → might need 2 months for zero cost
- Patience over panic - accept being stuck 3-10 times/year per stock

**Pull-Back Strategy:**
- If rolled to far expiration but stock drops back
- Pull back to shorter duration when cost-neutral
- Resume weekly income generation

**Key Constraint:**
- All rolls must be at ZERO COST (≤20% of original premium)
- Only close if cannot escape within 12 months

---

## Algorithm Overview

### Single Position Evaluator

V3 uses one unified evaluator that routes each position through 3 states in priority order:

```python
def evaluate(position):
    # STATE 1: Can pull back? (highest priority)
    if position.weeks_to_expiration > 1:
        pull_back = check_pull_back_opportunity(position)
        if pull_back:
            return recommend_pull_back()
    
    # STATE 2: In the money? (escape strategy)
    if position.is_itm():
        zero_cost = find_zero_cost_roll(max_months=12)
        if zero_cost:
            return recommend_roll(zero_cost)
        else:
            return recommend_close()  # Catastrophic
    
    # STATE 3: Profitable and OTM? (weekly income)
    if position.profit_pct >= 0.60 and not position.is_itm():
        return recommend_weekly_roll()
    
    # STATE 4: No action
    return None
```

### What's Removed from V2

❌ **Performance Tracking** - Never implemented  
❌ **Strategic Timing Optimization** - Pure speculation (Monday IV, FOMC, VIX)  
❌ **ITM Thresholds** - All threshold enforcement (5%, 10%, 20%)  
❌ **Economic Sanity Checks** - Minimum savings requirements ($50, 10%)  
❌ **Complex Cost Rules** - 7 different scenarios with exceptions  
❌ **Overlapping Strategies** - 10 files merged into 1 evaluator  

### What's Added in V3

✅ **Pull-Back Detector** - Return far-dated to shorter when cost-neutral  
✅ **Smart Assignment (IRA)** - Accept assignment vs expensive roll on Friday  
✅ **Unified Evaluator** - Single evaluation path per position  
✅ **Smart Filtering** - No duplicate notifications within same day  
✅ **State-Based Urgency** - 8 AM alerts only on meaningful state changes  

---

## Position States & Logic

### State 1: Pull-Back Opportunity (Highest Priority)

**Trigger:** Position >1 week out, can return to shorter duration at cost-neutral

**Example:**
- Position: 8 weeks to expiration
- Stock dropped, now can pull back
- Check: 1w ($0.30 debit), 2w ($0.18 debit), 3w ($0.15 debit)
- Recommend: Pull back to 2 weeks (first acceptable)

**Logic:**
```python
if position.weeks_to_expiration > 1:
    # Check all intermediate expirations (1w, 2w, 3w... up to current)
    for weeks in [1, 2, 3, 4, 6, 8, 12, 16, 24, 36, 52]:
        if weeks >= current_weeks:
            break
        
        # Skip earnings/dividend weeks
        if has_catalyst_in_week(weeks):
            continue
        
        # Get Delta 30 strike
        strike = get_strike(probability_target=0.70)
        premium = get_premium(strike, weeks)
        
        net_cost = current_value - premium
        max_debit = original_premium * 0.20
        
        if net_cost <= max_debit:
            return recommend_pull_back(weeks)  # First acceptable
```

**Why Priority 1:**
- Get back to income generation faster
- Opportunity may disappear if stock moves again
- More important than waiting for 60% profit on far-dated

---

### State 2: In The Money (Escape Strategy)

**Trigger:** Position is ITM (any amount)

**Goal:** Find shortest zero-cost roll within 12 months

**Logic:**
```python
if position.is_itm():
    max_debit = position.original_premium * 0.20
    
    # Scan 1w, 2w, 3w, 4w, 6w, 8w, 12w, 16w, 24w, 36w, 52w
    for weeks in durations:
        if weeks > 52:
            break
        
        # Skip earnings/dividend weeks
        if has_catalyst_in_week(weeks):
            continue
        
        # Get Delta 30 strike (closer to current price than Delta 10)
        strike = get_strike(probability_target=0.70)
        premium = get_premium(strike, weeks)
        
        net_cost = buy_back - premium
        
        if net_cost <= max_debit:
            return recommend_roll(weeks)  # Found escape!
    
    # Couldn't find zero-cost within 52 weeks
    return recommend_close("Cannot escape within 12 months")
```

**Examples:**

| ITM Amount | Typical Duration Needed | Strike Used |
|------------|------------------------|-------------|
| 3% ITM | 1-2 weeks | Delta 30 (~$103 if stock $100) |
| 10% ITM | 4-6 weeks | Delta 30 (~$114 if stock $110) |
| 20% ITM | 12-16 weeks | Delta 30 (~$124 if stock $120) |
| 50% ITM | 36-48 weeks | Delta 30 (~$155 if stock $150) |
| 100% ITM | >52 weeks → CLOSE | N/A |

**Key Point:** 
- NO thresholds - 3% ITM gets same treatment as 30% ITM
- Only close if cannot escape in 12 months (time-based, not ITM%-based)
- Use Delta 30 to minimize time needed

---

### State 3: Profitable & OTM (Weekly Income)

**Trigger:** Position ≥60% profit and not ITM

**Goal:** Roll to next week, continue income generation

**Logic:**
```python
if position.profit_pct >= 0.60 and not position.is_itm():
    # Get Delta 10 strike for weekly (conservative)
    strike = get_strike(probability_target=0.90)
    expiration = next_friday()
    
    return recommend_weekly_roll(strike, expiration)
```

**Why 60% threshold:**
- Capture most profit while avoiding expiration risk
- Leaving 20% on table is acceptable (matches cost rule)
- Consistent income generation

---

### State 4: No Action

**Trigger:** None of the above apply

**Examples:**
- OTM position with 30% profit (wait for 60%)
- Far-dated position that cannot pull back yet (too expensive)
- Position with 1 day to expiration and OTM (let expire)

---

## Strike Selection Strategy

**Critical: Different strikes for different situations**

### Delta 10 (90% OTM Probability)

**Use for:**
- Weekly rolls (State 3: Profitable OTM positions)
- New covered calls on closed positions
- Monday buy-backs after assignment

**Why:**
- Maximum safety
- Consistent income generation
- Standard strategy

**Example:**
- Stock: $175
- Delta 10 strike: ~$185 (5.7% OTM)
- Probability of success: ~90%

### Delta 30 (70% OTM Probability)

**Use for:**
- ITM escape rolls (State 2)
- Pull-backs (State 1)

**Why:**
- Closer to current price = higher premiums
- Minimizes weeks needed to achieve zero cost
- Still reasonably safe (70% success rate)
- Trade-off: Less safety for faster escape

**Example:**
- Stock: $110 (10% ITM from $100 strike)
- Delta 30 strike: ~$114 (3.6% OTM)
- Probability of success: ~70%
- Can achieve zero cost in 4-6 weeks
- vs Delta 10 strike: ~$120 (9% OTM) would need 12+ weeks

### Comparison Table

| Situation | Strike Target | Distance OTM | Success Rate | Use Case |
|-----------|---------------|--------------|--------------|----------|
| Weekly roll | Delta 10 | ~5-7% | 90% | Income generation |
| ITM escape | Delta 30 | ~3-5% | 70% | Minimize time stuck |
| Pull-back | Delta 30 | ~3-5% | 70% | Return to income |
| New sell | Delta 10 | ~5-7% | 90% | Start fresh position |

---

## Cost Rules

### Single Rule: 20% of Original Premium

**The ONLY cost validation in V3:**

```python
max_acceptable_debit = position.original_premium * 0.20

if net_cost <= max_acceptable_debit:
    ACCEPT  # This is "zero cost" in our strategy
else:
    REJECT  # Keep searching
```

**Special case: Any credit is auto-accepted**

```python
if net_cost < 0:  # It's a credit
    ACCEPT  # Always good
```

### Examples

| Original Premium | Max Debit | Scenario | Result |
|------------------|-----------|----------|--------|
| $1.00 | $0.20 | Net debit $0.15 | ✓ Accept |
| $1.00 | $0.20 | Net debit $0.25 | ✗ Reject, search longer |
| $1.00 | $0.20 | Net credit $0.10 | ✓ Accept (any credit) |
| $2.50 | $0.50 | Net debit $0.45 | ✓ Accept |
| $0.50 | $0.10 | Net debit $0.12 | ✗ Reject |

### Rationale

**Why 20%?**
- User typically closes at 80% profit (leaves 20% on table)
- Willing to spend that 20% to escape ITM
- If captured 80% profit and pay 20% debit → Net 60% profit (still good)

**Why no exceptions?**
- V2 had 7 different rules (earnings exception, high profit exception, etc.)
- Created complexity and inconsistency
- One simple rule is predictable and reliable

**What's removed:**
- ❌ No "must save $50" requirement
- ❌ No "must save 10%" requirement
- ❌ No "earnings week allows 75% debit"
- ❌ No "high profit allows 15% debit"
- ❌ No "expiring soon allows 100% debit"

---

## Smart Assignment (IRA Only)

### Overview

**Feature:** On expiration Friday, if position is barely ITM in IRA account, compare:
- **Option 1:** Accept assignment (sell stock, small loss)
- **Option 2:** Roll out (expensive, locked up weeks)

If assignment is cheaper → Recommend accepting assignment + buying back Monday

### Trigger Conditions

**ALL must be true:**

1. ✅ Account type: IRA or Roth IRA (NOT taxable - wash sale rules)
2. ✅ Day: Expiration Friday (0 days to expiration)
3. ✅ ITM status: 0.1% - 2.0% ITM (borderline)
4. ✅ Roll cost: Would require 2+ weeks OR >$15 debit
5. ✅ Time: 12:45 PM scan (last 15 minutes before market close)

### Decision Logic

```python
def should_accept_assignment_ira(position):
    # Prerequisites
    if account not in ['IRA', 'ROTH_IRA']:
        return False
    
    if days_to_expiration != 0:
        return False
    
    if not (0.1% <= itm_pct <= 2.0%):
        return False
    
    # Calculate costs
    assignment_loss = itm_amount * 100  # e.g., $1/share = $100/contract
    
    # Find zero-cost roll
    roll = find_zero_cost_roll(max_months=12)
    
    if not roll or roll.weeks < 2:
        return False  # Roll is cheap enough
    
    # Calculate total roll cost
    roll_debit = max(roll.net_cost, 0) * 100
    weekly_income = estimate_weekly_premium(symbol) * 100
    opportunity_cost = weekly_income * roll.weeks
    total_roll_cost = roll_debit + opportunity_cost
    
    # Compare
    if assignment_loss < total_roll_cost:
        return True  # Assignment is cheaper
    
    return False
```

### Example

**Friday 12:45 PM - META $655 Call**

```
Current Status:
  Stock: $656.00
  Strike: $655.00
  ITM: 0.15% ($1.00 per share)
  Account: Neels IRA ✓

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OPTION 1: ACCEPT ASSIGNMENT (Recommended)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Loss if assigned:
  • Assignment price: $655/share
  • Current market: $656/share
  • Loss: $1.00/share = $100/contract

Plan for Monday:
  • Buy back META at market
  • Sell fresh weekly call
  • Resume income generation

Estimated cost: $100

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OPTION 2: ROLL OUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Roll to Dec 27 (3 weeks) at $665 strike

Cost:
  • Net debit: $10/contract
  • Opportunity cost (3 weeks locked): $150
  • Total cost: $160/contract

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RECOMMENDATION: Accept Assignment

Savings: $60/contract
```

### Monday Buy-Back

**Monday 6:00 AM - Follow-Up**

```
META - BUY BACK REMINDER

Assignment Summary:
  • Sold at: $655/share (Friday)
  • Contracts: 1 (100 shares)

Current Market:
  • META: $658.00
  • Change: +0.46% vs assignment

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BUY-BACK DECISION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Cost: $658/share (+$3 vs assignment)

OPTIONS:
1. BUY NOW - Only 0.46% above assignment ✓
2. WAIT - Set limit at $656
3. SKIP - If >3% above, consider exiting

RECOMMENDATION: Buy now at $658

After buying:
  → Sell $665 weekly call for $0.55
  → Back to weekly income ✓
```

### Buy-Back Decision Thresholds

| Price vs Assignment | Action | Priority |
|---------------------|--------|----------|
| <1% above | BUY NOW | High |
| 1-3% above | WAIT or BUY | Medium |
| >3% above | SKIP buy-back | Low |

### Why IRA Only?

**Tax implications in taxable accounts:**
- Wash sale rule: Can't buy back same stock within 30 days
- Loss may not be deductible
- Creates tax reporting complexity

**IRA advantages:**
- No wash sale rules
- No tax on assignment loss
- No reporting complexity
- Clean reset Monday

---

## Daily Scan Schedule

### Overview - 5 Daily Scans (Pacific Time)

All scans use **SmartScanFilter** to prevent duplicate notifications within same day.

---

### Scan 1: 6:00 AM - Main Daily Scan 📊

**Purpose:** Comprehensive evaluation before user wakes up

**Evaluates:**
- All positions (comprehensive)
- Pull-back opportunities
- ITM escape rolls
- Weekly roll opportunities
- Earnings alerts (next 5 days)
- Dividend alerts (next 7 days)
- New sell opportunities (closed positions)
- **Monday only:** Buy-back reminders (assigned positions from Friday)

**User workflow:**
- Notification sent: 6:00 AM
- User wakes: 6:30 AM
- Action window: 6:30-8:00 AM (before school drop-off)

---

### Scan 2: 8:00 AM - Post-Opening Urgent 🚨

**Purpose:** Catch urgent state changes from market open volatility

**Evaluates ONLY:**
- Newly ITM positions (OTM at 6 AM → ITM now)
- New pull-back opportunities (couldn't pull back at 6 AM → can now)
- Earnings TODAY
- Positions that went >10% deeper ITM
- Expiring TODAY

**User workflow:**
- Notification sent: 8:00 AM (if urgent items)
- User sees: 8:15 AM (arriving at office)
- Action window: 8:15 AM - noon

**What NOT to alert:**
- ❌ Same recommendation from 6 AM (already sent)
- ❌ Small moves (2-5% normal volatility)
- ❌ Already-known ITM positions still ITM

---

### Scan 3: 12:00 PM - Midday Opportunities 🔄

**Purpose:** Check for intraday opportunities

**Evaluates:**
- Pull-back opportunities (stock dropped intraday)
- Significant moves (>10% since morning)

**User workflow:**
- Notification sent: 12:00 PM (if significant changes)
- User sees: Lunch time
- Action window: 12:00-1:00 PM

---

### Scan 4: 12:45 PM - Pre-Close Urgent ⏰

**Purpose:** Last 15 minutes before market close (1:00 PM Pacific)

**Evaluates ONLY:**
- Expiring TODAY positions
- **Smart Assignment (IRA):** Borderline ITM positions
- Triple Witching alerts (if quarterly expiration)

**User workflow:**
- Notification sent: 12:45 PM (only if critical)
- User sees: 15 min before market close
- Action window: 12:45-1:00 PM

---

### Scan 5: 8:00 PM - Evening Planning 📅

**Purpose:** Next day preparation (informational only)

**Evaluates:**
- Earnings TOMORROW
- Ex-dividend TOMORROW
- Positions expiring TOMORROW

**User workflow:**
- Notification sent: 8:00 PM
- User sees: Evening
- Action window: Mental preparation, act tomorrow

---

### Smart Filtering Logic

**Prevents duplicate notifications within same day:**

```python
class SmartScanFilter:
    def __init__(self):
        self.sent_today = {}
    
    def should_send(self, position_id, recommendation):
        rec_hash = hash((
            recommendation['action'],
            recommendation.get('new_strike'),
            recommendation.get('new_expiration'),
            recommendation.get('priority')
        ))
        
        if position_id not in self.sent_today:
            self.sent_today[position_id] = rec_hash
            return True  # First time
        
        if self.sent_today[position_id] != rec_hash:
            self.sent_today[position_id] = rec_hash
            return True  # Changed
        
        return False  # Duplicate
    
    def reset_daily(self):
        """Called at midnight."""
        self.sent_today = {}
```

**Example:**
- 6 AM: Recommend "Roll AAPL to $185" → Sent ✓
- 8 AM: Same position, same recommendation → Filtered ✗
- 12 PM: Stock moved, now "Roll AAPL to $190" → Sent ✓ (changed)

---

## Configuration Reference

### Complete V3 Configuration

```python
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
    "delta_target_weekly": 0.90,
    # Delta 10 for weekly rolls (90% OTM)
    
    "delta_target_itm": 0.70,
    # Delta 30 for ITM rolls and pull-backs (70% OTM)
    
    # ===== PULL-BACK =====
    "min_weeks_for_pullback": 1,
    # Check pull-back for positions >1 week out
    
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
        "main": "06:00",          # Comprehensive daily
        "post_open": "08:00",     # Urgent state changes
        "midday": "12:00",        # Opportunities
        "pre_close": "12:45",     # Last chance + smart assignment
        "evening": "20:00"        # Next day planning
    },
    
    # ===== URGENCY THRESHOLDS =====
    "urgent_deepening_threshold": 10,
    # Alert at 8 AM if position >10% deeper ITM than 6 AM
    
    # ===== SPECIAL DATES =====
    "triple_witching_months": [3, 6, 9, 12],
    # March, June, September, December
    
    # ===== SMART ASSIGNMENT (IRA ONLY) =====
    "smart_assignment": {
        "enabled": True,
        "accounts": ["IRA", "ROTH_IRA"],
        "max_itm_pct": 2.0,        # Maximum 2% ITM
        "min_itm_pct": 0.1,        # Minimum 0.1% ITM
        "min_roll_weeks": 2,       # Only if roll ≥2 weeks
        "min_roll_debit": 15,      # OR roll debit >$15
        "monday_skip_threshold": 3.0,   # Skip buyback if >3% above
        "monday_wait_threshold": 1.0,   # Wait if 1-3% above
    }
}
```

### What's Removed from V2

**Deleted parameters (38 total):**

```python
# REMOVED - No longer used in V3
"normal_profit_threshold": 0.60           
"earnings_week_profit_threshold": 0.45   
"short_dte_threshold": 0.35              
"catastrophic_itm_pct": 20.0             
"deep_itm_pct": 10.0                     
"normal_close_threshold_pct": 5.0        
"triple_witching_close_threshold_pct": 3.0
"max_debit_pct_earnings": 0.75           
"max_debit_pct_high_profit": 0.15        
"max_debit_pct_expiring_soon": 1.0       
"scenario_comparison_tolerance": 0.90    
"min_savings_to_wait": 0.10              
"min_roll_savings_dollars": 50           
"min_roll_savings_percent": 10           
"min_strike_variation_pct": 2.0          
"max_roll_weeks_standard": 2             
"max_roll_weeks_preemptive": 3           
"max_roll_weeks_deep_itm": 6             
"min_marginal_premium": 0.15             
"mean_reversion_expected_days": 5        
"approaching_threshold_pct": 3.0         
"urgent_threshold_pct": 1.5              
"min_days_to_expiration": 2              
"momentum_lookback_days": 3              
"min_volume_multiple": 1.2               
"enable_timing_optimization": False      
"friday_cutoff_time": "14:00"            
"min_premium_pct_of_stock": 0.003        
"low_vix_threshold": 15                  
"avoid_morning_chaos": False             
# ... +8 more timing-related params
```

---

## Decision Trees

### Complete Evaluation Flow

```
┌─────────────────────────────────────────────────────────────┐
│               POSITION EVALUATOR (V3)                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Input: position                                             │
│                                                              │
│  ┌──────────────────────────────────────────┐               │
│  │ STATE 1: Can Pull Back?                  │               │
│  │ (Far-dated → shorter duration)           │               │
│  └──────────────────────────────────────────┘               │
│         │                                                    │
│         ├─ weeks_to_expiration > 1? ──No──┐                 │
│         │                                  │                 │
│         Yes                                │                 │
│         │                                  │                 │
│         ├─ Check 1w, 2w, 3w... up to current                │
│         ├─ Skip earnings/dividend weeks                      │
│         ├─ Use Delta 30 strikes                              │
│         ├─ net_cost ≤ 20% original?                          │
│         │                                  │                 │
│         Yes──→ RECOMMEND PULL-BACK         │                 │
│         │                                  │                 │
│         No───────────────────────────────→│                 │
│                                            │                 │
│  ┌──────────────────────────────────────────┐               │
│  │ STATE 2: In The Money?                   │←──────────────┘
│  │ (Find zero-cost escape)                  │               │
│  └──────────────────────────────────────────┘               │
│         │                                                    │
│         ├─ is_itm()? ──No──────────────────┐                │
│         │                                   │                │
│         Yes                                 │                │
│         │                                   │                │
│         ├─ Scan 1w→52w for zero-cost       │                │
│         ├─ Skip earnings/dividend weeks     │                │
│         ├─ Use Delta 30 strikes             │                │
│         ├─ net_cost ≤ 20% original?         │                │
│         │                                   │                │
│         Found──→ RECOMMEND ITM ROLL         │                │
│         │                                   │                │
│         Not Found──→ RECOMMEND CLOSE        │                │
│                     (Catastrophic)          │                │
│                                             │                │
│  ┌──────────────────────────────────────────┐               │
│  │ STATE 3: Profitable & OTM?               │←──────────────┘
│  │ (Weekly income generation)               │               │
│  └──────────────────────────────────────────┘               │
│         │                                                    │
│         ├─ profit ≥ 60% AND not ITM? ──No──┐                │
│         │                                   │                │
│         Yes                                 │                │
│         │                                   │                │
│         ├─ Use Delta 10 strike              │                │
│         ├─ Next Friday expiration           │                │
│         │                                   │                │
│         └──→ RECOMMEND WEEKLY ROLL          │                │
│                                             │                │
│  ┌──────────────────────────────────────────┐               │
│  │ STATE 4: No Action                       │←──────────────┘
│  └──────────────────────────────────────────┘               │
│         │                                                    │
│         └──→ RETURN None                                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Smart Assignment Flow (IRA Only)

```
┌─────────────────────────────────────────────────────────────┐
│         SMART ASSIGNMENT EVALUATOR (Friday Only)             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Input: position (expiring today)                            │
│                                                              │
│  ┌─ Account = IRA/Roth? ──No──→ Return None                │
│  │                                                           │
│  Yes                                                         │
│  │                                                           │
│  ┌─ Days to exp = 0? ──No──→ Return None                    │
│  │                                                           │
│  Yes                                                         │
│  │                                                           │
│  ┌─ 0.1% ≤ ITM ≤ 2.0%? ──No──→ Return None                  │
│  │                                                           │
│  Yes                                                         │
│  │                                                           │
│  ├─ Calculate assignment_loss = ITM × 100                    │
│  │                                                           │
│  ├─ Find zero-cost roll (if possible)                        │
│  │                                                           │
│  ┌─ Roll < 2 weeks AND debit < $15? ──Yes──→ Return None    │
│  │   (Roll is cheap, use normal logic)                      │
│  │                                                           │
│  No                                                          │
│  │                                                           │
│  ├─ Calculate total_roll_cost:                               │
│  │   • Roll debit (if any)                                  │
│  │   • + Opportunity cost (weeks × weekly_income)           │
│  │                                                           │
│  ├─ Compare: assignment_loss vs total_roll_cost              │
│  │                                                           │
│  ┌─ assignment_loss < total_roll_cost? ──No──→ Return None  │
│  │                                                           │
│  Yes                                                         │
│  │                                                           │
│  └──→ RECOMMEND SMART ASSIGNMENT                             │
│        • Show both options                                   │
│        • Show savings                                        │
│        • Record for Monday follow-up                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘

Monday Follow-Up:

┌─────────────────────────────────────────────────────────────┐
│         MONDAY BUY-BACK EVALUATOR (6 AM Scan)                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Input: Assignments from last Friday                         │
│                                                              │
│  For each assignment:                                        │
│                                                              │
│  ├─ Get current_price                                        │
│  ├─ Calculate price_change = (current - assignment) / assignment │
│  │                                                           │
│  ├─ price_change > 3%? ──Yes──→ RECOMMEND SKIP              │
│  │                        (Too expensive)                    │
│  │                                                           │
│  ├─ 1% < price_change ≤ 3%? ──Yes──→ RECOMMEND WAIT_OR_BUY  │
│  │                        (Consider waiting)                 │
│  │                                                           │
│  └─ price_change ≤ 1%? ──Yes──→ RECOMMEND BUY_NOW           │
│                          (Good price)                        │
│                                                              │
│  After buy-back:                                             │
│  └─ Sell new weekly call (Delta 10)                          │
│     Resume income generation                                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Examples

### Example 1: OTM Profitable Position (Weekly Roll)

**Scenario:**
```
Position: AAPL $180 call
Stock: $175
Profit: 65% captured
Days to expiration: 3
```

**V3 Evaluation:**
```
State 1 (Pull-back): weeks = 0.4 weeks → Skip (≤1 week)
State 2 (ITM): is_itm() = False → Skip
State 3 (Profitable): profit = 65% ≥ 60% AND not ITM → TRUE
```

**Recommendation:**
```
Action: ROLL_WEEKLY
Strike: $185 (Delta 10, ~5.7% OTM, 90% probability)
Expiration: Next Friday
Premium: ~$0.50
Reason: "65% profit captured - roll to next week"
```

---

### Example 2: Shallow ITM Position (Quick Escape)

**Scenario:**
```
Position: NVDA $500 call
Stock: $515 (3% ITM)
Original premium: $1.00
```

**V3 Evaluation:**
```
State 1 (Pull-back): weeks = 1 week → Check pull-back
  → Cannot pull back (position is weekly)
State 2 (ITM): is_itm() = True → TRUE
```

**Zero-Cost Roll Search:**
```
Max debit: $1.00 × 0.20 = $0.20

Week 1:
  Strike: $533 (Delta 30, 3.5% OTM)
  Buy back: $15.50
  New premium: $15.35
  Net: $0.15 debit ✓ ACCEPT

Result: Found in 1 week
```

**Recommendation:**
```
Action: ROLL_ITM
Strike: $533 (Delta 30)
Expiration: 1 week
Net cost: $0.15 debit ($15/contract)
Reason: "3.0% ITM - rolling to 1 week at $533 strike"
```

**Note:** V2 would have CLOSED this position (5% threshold). V3 rolls it.

---

### Example 3: Deep ITM Position (Longer Escape)

**Scenario:**
```
Position: META $400 call
Stock: $480 (20% ITM)
Original premium: $2.00
```

**V3 Evaluation:**
```
State 1 (Pull-back): Not applicable (position is ITM)
State 2 (ITM): is_itm() = True → TRUE
```

**Zero-Cost Roll Search:**
```
Max debit: $2.00 × 0.20 = $0.40

Week 1: Net $8.00 debit ✗
Week 2: Net $4.50 debit ✗
Week 3: Net $2.80 debit ✗
Week 4: Net $1.20 debit ✗
Week 6: Net $0.65 debit ✗
Week 8: Net $0.35 debit ✓ ACCEPT

Strike for week 8: $498 (Delta 30, 3.75% OTM)
Result: Found in 8 weeks
```

**Recommendation:**
```
Action: ROLL_ITM
Strike: $498 (Delta 30)
Expiration: 8 weeks
Net cost: $0.35 debit ($35/contract)
Reason: "20.0% ITM - rolling to 8 weeks at $498 strike"
```

**Note:** V2 would have CLOSED this (10% threshold). V3 finds 8-week escape.

---

### Example 4: Catastrophic ITM (Cannot Escape)

**Scenario:**
```
Position: TSLA $200 call
Stock: $400 (100% ITM)
Original premium: $1.00
```

**V3 Evaluation:**
```
State 2 (ITM): is_itm() = True → TRUE
```

**Zero-Cost Roll Search:**
```
Max debit: $1.00 × 0.20 = $0.20

Week 1: Net $195 debit ✗
...
Week 52: Net $45 debit ✗

Result: Cannot find acceptable roll within 52 weeks
```

**Recommendation:**
```
Action: CLOSE_CATASTROPHIC
Priority: URGENT
Reason: "Cannot find zero-cost roll within 12 months. 
         Position 100.0% ITM. Close position and accept loss."
```

**This is the ONLY scenario where V3 closes based on ITM.**

---

### Example 5: Pull-Back Opportunity

**Scenario:**
```
Position: AAPL call, 8 weeks to expiration
Original: Rolled here 2 weeks ago when 15% ITM
Now: Stock dropped back
Original premium: $1.50
```

**V3 Evaluation:**
```
State 1 (Pull-back): weeks = 8 weeks > 1 → Check pull-back

Current value: $3.20
Max debit: $1.50 × 0.20 = $0.30

Check 1 week:
  Strike: $182 (Delta 30)
  Premium: $2.85
  Net: $3.20 - $2.85 = $0.35 debit ✗

Check 2 weeks:
  Strike: $183 (Delta 30)
  Premium: $2.95
  Net: $3.20 - $2.95 = $0.25 debit ✓ ACCEPT

Result: Can pull back to 2 weeks
```

**Recommendation:**
```
Action: PULL_BACK
From: 8 weeks
To: 2 weeks
Strike: $183 (Delta 30)
Net cost: $0.25 debit ($25/contract)
Benefit: "Return to income 6 weeks early"
Reason: "Can pull back from 8 weeks to 2 weeks"
```

**User action:** Execute pull-back, then in 2 weeks roll to weekly (if profitable)

---

### Example 6: Smart Assignment (IRA - Friday)

**Scenario:**
```
Position: MSFT $420 call (expiring TODAY)
Stock: $421.50 (0.36% ITM)
Account: IRA
Original premium: $0.80
Time: Friday 12:45 PM
```

**V3 Evaluation:**
```
12:45 PM Scan checks Smart Assignment:

✓ Account = IRA
✓ Days to expiration = 0
✓ ITM = 0.36% (within 0.1-2.0%)

Assignment loss: $1.50/share = $150/contract

Find zero-cost roll:
  Week 3: Strike $430, net debit $0.10
  Total roll cost: $10 + (3 weeks × $50 weekly income) = $160

Compare: $150 < $160
Result: Assignment saves $10/contract
```

**Recommendation:**
```
🎯 MSFT $420 Call - EXPIRING TODAY - Borderline ITM

OPTION 1: ACCEPT ASSIGNMENT (Recommended)
  • Loss: $150/contract
  • Plan: Let expire → Buy back Monday → Sell weekly
  
OPTION 2: ROLL OUT
  • 3 weeks at $430 strike
  • Cost: $160/contract (debit $10 + opportunity $150)

RECOMMENDATION: Accept assignment (saves $10)

⚠️ Weekend risk: Stock could gap up Monday
```

**Monday 6 AM Follow-Up:**
```
MSFT - BUY BACK REMINDER

Assigned Friday at: $420/share
Current price: $422 (+0.48%)
Extra cost: $200/contract

RECOMMENDATION: Buy now at $422
After buying: Sell $430 weekly for $0.60
```

---

### Example 7: No Action (Wait for 60%)

**Scenario:**
```
Position: GOOGL $150 call
Stock: $145
Profit: 45% captured
Days to expiration: 5
```

**V3 Evaluation:**
```
State 1 (Pull-back): weeks = 0.7 weeks < 1 → Skip
State 2 (ITM): is_itm() = False → Skip
State 3 (Profitable): profit = 45% < 60% → Skip
State 4: No action
```

**Recommendation:**
```
None - wait for 60% profit or expiration
```

**User sees:** No notification for this position

---

## Migration from V2

### Behavioral Changes

| Scenario | V2.3 Behavior | V3.0 Behavior |
|----------|---------------|---------------|
| 3% ITM | CLOSE (5% threshold) | ROLL to 1-2 weeks |
| 12% ITM | CLOSE_DONT_ROLL (10% threshold) | ROLL to 4-8 weeks |
| 25% ITM | CATASTROPHIC CLOSE (20% threshold) | ROLL to 12-24 weeks |
| 100% ITM, can't escape | CLOSE | CLOSE (same) |
| Roll costs $0.30 debit | REJECT (50% limit hit) | ACCEPT if ≤20% original |
| Stock at support, oversold | "Wait for Monday IV bump" | "Wait - RSI oversold" |
| Far-dated, stock dropped | No recommendation | PULL-BACK to shorter |
| Friday, barely ITM (IRA) | Roll out | Compare vs assignment |
| Same position, 6 AM & 8 AM | Both send notification | 8 AM filtered (duplicate) |

### Files Changed

**Deleted:**
- `timing_optimizer.py` (~300 lines)
- `performance_tracker.py` (never existed)
- `approaching_strike_alert.py` (merged)
- `early_roll_opportunity.py` (merged)

**Renamed:**
- `multi_week_optimizer.py` → `zero_cost_finder.py`

**Created:**
- `position_evaluator.py` (new - unified evaluator)
- `pull_back_detector.py` (new feature)
- `smart_assignment_evaluator.py` (new feature)
- `assignment_tracker.py` (new feature)
- `v3_scanner.py` (5-scan schedule)

**Modified:**
- `roll_options.py` (simplified)
- `itm_roll_optimizer.py` (simplified)
- `new_covered_call.py` (simplified)
- `utils/option_calculations.py` (simplified)
- `algorithm_config.py` (V3_CONFIG added)

---

## Appendices

### Appendix A: Glossary

**Delta 10:** Strike with ~10% delta, meaning ~90% probability of expiring OTM  
**Delta 30:** Strike with ~30% delta, meaning ~70% probability of expiring OTM  
**Zero-cost roll:** Roll where net debit ≤ 20% of original premium  
**Pull-back:** Closing far-dated position early to return to shorter duration  
**Smart Assignment:** Accepting assignment vs rolling when cheaper (IRA only)  
**ITM:** In The Money - stock price above call strike (or below put strike)  
**OTM:** Out of The Money - stock price below call strike (or above put strike)  
**Catastrophic:** Cannot find zero-cost roll within 12 months

---

### Appendix B: Quick Reference

**When to use Delta 10:**
- Weekly rolls
- New covered calls
- Post-assignment buy-backs

**When to use Delta 30:**
- ITM escape rolls
- Pull-backs

**When to close:**
- ONLY if cannot escape within 12 months
- Smart assignment in IRA (optional, user decides)

**When to pull back:**
- Far-dated position
- Can return to shorter duration at ≤20% original premium
- Checked daily at 6 AM, 12 PM

**When to accept assignment (IRA):**
- Friday expiration
- 0.1-2% ITM
- Assignment loss < Roll cost
- User decides (recommendation provided)

---

### Appendix C: Support & Feedback

**If a recommendation feels wrong:**
1. Note the position details
2. Note what was recommended
3. Note what you expected
4. Provide feedback for algorithm refinement

**Common "odd" recommendations explained:**
- "Why Delta 30 for ITM?" → Minimizes time stuck
- "Why not close at 10% ITM?" → Can still escape cost-neutral
- "Why pull back with 6 weeks left?" → Resume income faster
- "Why accept assignment?" → Cheaper than locking up weeks

---

**END OF V3.0 SPECIFICATION**

---

This document is the official V3.0 algorithm specification. Implementation details may vary slightly based on real-world testing and refinement.

**Last Updated:** December 21, 2024  
**Version:** 3.0.0  
**Status:** ✅ IMPLEMENTED
