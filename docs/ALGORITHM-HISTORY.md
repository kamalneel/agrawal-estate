# Algorithm Version History

**Purpose:** Consolidated historical reference for all algorithm versions. This document preserves key decisions, philosophies, and learnings from each version for future reference.

**Current Version:** V4 (January 20, 2026)

---

## Version Timeline

| Version | Date | Status | Key Innovation |
|---------|------|--------|----------------|
| V1 | 2024 | Deprecated | Basic notification rules |
| V2 | 2024 | Deprecated | Complex multi-strategy approach |
| V3 | Dec 2024 | Deprecated | Unified evaluator, 52-week escapes |
| V3.3 | Jan 2026 | Deprecated | Mean reversion, weekly income priority |
| V3.4 | Jan 2026 | Deprecated | TA-based MONITOR for ITM |
| **V4** | Jan 2026 | **ACTIVE** | Intrinsic/time value model, 4-week cap |

---

## V1: Basic Notification Rules (2024)

### Overview
First attempt at options notification system. Simple rule-based approach.

### Key Characteristics
- Basic ITM/OTM detection
- Fixed thresholds for action triggers
- No sophisticated roll optimization
- Limited notification formatting

### Why Replaced
Too simplistic for real-world options management. Didn't account for time value, mean reversion, or income optimization.

---

## V2: Multi-Strategy Approach (2024)

### Overview
Attempted to handle every edge case with specialized strategies.

### Key Characteristics
- 10 separate strategy files
- Multiple ITM thresholds (5%, 10%, 20%)
- Complex cost sensitivity rules
- Strategic timing predictions (Monday IV bumps, FOMC)
- ~2,500 lines of code

### Files
```
timing_optimizer.py
performance_tracker.py
approaching_strike_alert.py
early_roll_opportunity.py
multi_week_optimizer.py
(+ 5 more)
```

### Problems Identified
1. Over-engineered - 10 files for one decision
2. ITM thresholds forced premature closes
3. Complex cost rules rejected valid rolls
4. Timing predictions added speculation
5. Race conditions from overlapping strategies

### Key Metrics
| Metric | V2 Value |
|--------|----------|
| Lines of Code | ~2,500 |
| Strategy Files | 10 |
| Config Parameters | 50+ |
| ITM Thresholds | 4 |
| Cost Rules | 7 scenarios |

---

## V3: Unified Evaluator (December 2024)

### Philosophy
> "Patient position management aligned with actual trading strategy"

### Core Principle
Find zero-cost roll to ANY expiration needed (1 week to 12 months). Only close if cannot escape within 12 months.

### Key Innovations
1. **Single unified evaluator** - One file, 3 states
2. **No ITM thresholds** - Only time-based catastrophic
3. **One cost rule** - ≤20% of original premium
4. **No timing predictions** - Only real TA signals
5. **Pull-back detector** - Return to shorter when possible
6. **Smart assignment (IRA)** - Accept assignment vs expensive roll

### Decision States
```
STATE 1: Can Pull Back? (Highest Priority)
  └─ Return far-dated to shorter duration

STATE 2: In The Money?
  └─ Find zero-cost roll ≤52 weeks

STATE 3: Profitable & OTM?
  └─ Roll to next week (weekly income)

STATE 4: No Action
```

### Strike Selection
| Scenario | Delta Target | Why |
|----------|-------------|-----|
| Weekly rolls | Delta 10 (90% OTM) | Income generation |
| ITM escapes | Delta 30 (70% OTM) | Minimize time stuck |
| Pull-backs | Delta 30 (70% OTM) | Return to income |

### Key Metrics (vs V2)
| Metric | V2 | V3 | Improvement |
|--------|----|----|-------------|
| Lines of Code | ~2,500 | ~1,000 | -60% |
| Strategy Files | 10 | 1 | -90% |
| Config Parameters | 50+ | 12 | -76% |
| ITM Thresholds | 4 | 0 | -100% |

### Implementation Notes
V3 was implemented in 5 chunks:
1. Remove timing optimization
2. Remove ITM thresholds, add 20% cost rule
3. Zero-cost finder (52 weeks, Delta 30)
4. Pull-back detector, unified evaluator
5. Smart assignment (IRA only)

---

## V3.3: Mean Reversion & Weekly Income (January 2026)

### Key Addition to Philosophy
> "Weekly income generation takes priority over escaping ITM."

### Changes from V3.0

#### 1. Weekly Income Priority
For slightly ITM + profitable positions: **COMPRESS time first, extend only if necessary.**

```
✅ RIGHT: Roll to Jan 16 $340 with $5.65 CREDIT (compress)
❌ WRONG: Roll to Jan 30 $345 (extend, lose weekly cycle)
```

#### 2. Mean Reversion Awareness
Different handling based on time to expiration:

| Days to Expiry | ITM Handling |
|----------------|--------------|
| ≤ 60 days | ESCAPE NOW |
| > 60 days | COMPRESS or MONITOR |

#### 3. Flexible ITM Debit Limits
Absolute limits based on ITM severity:

| ITM Severity | Max Debit |
|--------------|-----------|
| Slight (1-5%) | $2.00 |
| Moderate (5-10%) | $3.00 |
| Deep (>10%) | $5.00 |

#### 4. WAIT Recommendations
TA-driven hold signals for uncovered positions:

| RSI | Action |
|-----|--------|
| < 30 | WAIT (oversold) |
| > 70 | SELL NOW |
| 30-70 | SELL NOW |

### V3.3 Decision Flow
```
IF ITM + Near expiry (≤60 days):
  → ESCAPE with flexible debit

IF ITM + Far expiry (>60 days):
  → Try COMPRESS, else MONITOR

IF Slightly ITM (<5%) + Profitable (>60%):
  → COMPRESS (preserve weekly income)

IF Uncovered:
  → Use TA for SELL vs WAIT
```

---

## V3.4: TA-Based MONITOR (January 2026)

### Key Addition
Before escaping ITM, check Technical Analysis for support/resistance.

### Logic
| Option Type | MONITOR When |
|-------------|--------------|
| PUT ITM | Stock at SUPPORT (BB < 35% or RSI < 40) |
| CALL ITM | Stock at RESISTANCE (BB > 65% or RSI > 60) |

### Thresholds
```python
TA_MONITOR_MAX_ITM_PCT = 8.0  # Apply to ≤8% ITM
TA_MONITOR_MIN_DAYS = 5       # Need at least 5 days
```

### Example
AVGO $355 PUT (6.5% ITM, 8 days left), BB Position 29%:
- V3.3: Roll to March (lose 10 weeks income)
- V3.4: MONITOR - wait for bounce from support

---

## V4: Intrinsic/Time Value Model (January 2026)

### Philosophy Evolution

V4 adds **6 foundational beliefs**:
1. Believe in holdings
2. Hold forever
3. Mean reversion is inevitable
4. Primary goal: weekly options income
5. Avoid unnecessary risk
6. Avoid forced assignment

### Key Innovations

#### 1. Intrinsic Value Model
```
Option Price = Intrinsic Value + Time Value

Intrinsic (ICE): Fixed, only changes when stock moves
Time Value (WATER): Decays to zero, this is what you capture
```

#### 2. Position Categories by Intrinsic %
| Intrinsic % | Category | Strategy |
|-------------|----------|----------|
| 0-25% | SAFE | Normal management |
| 25-40% | LOW BAD | Time helps, can wait |
| 40-55% | MEDIUM | Decision point |
| 55-70% | MED-HIGH | Need stock movement |
| 70-85% | HIGH BAD | Stock must move significantly |
| 85%+ | CATASTROPHIC | Cut loss or accept assignment |

#### 3. Maximum Escape Duration: 4 Weeks
```
V3: Search up to 52 weeks for free escape
V4: Cap at 4 weeks, prefer $5 debit over 12-week trap
```

**Why:** MU $295 lesson - rolled to 3 months out, got "trapped" when couldn't capitalize on pullbacks.

#### 4. Compression Cost Awareness
```
Compression Cost = Time Value (Current) - Time Value (Target)
Approximately $5-6 per month for $400+ stock at 12% ITM
```

#### 5. Dual-Benefit Compression Model
```
Total Value = Weekly Income Lost + Cycle Capture Value
Compress when Total Value > Compression Cost
```

#### 6. Time Cushion Rule
When expiry is near (≤2 days), roll out by 1 week regardless of profit/loss.

### V4 Decision Framework
```
1. CALCULATE INTRINSIC %

2. IF TIME HELPS (< 40% intrinsic):
   → Normal strategies (pull-back, weekly roll, ITM escape)

3. IF CROSSOVER (40-60% intrinsic):
   → Evaluate compression cost vs weekly income

4. IF STOCK MUST MOVE (> 60% intrinsic):
   → Do NOT compress (too expensive)
   → Set price alerts, wait for mean reversion
```

### Configuration Changes (V3 → V4)
| Parameter | V3 | V4 |
|-----------|----|----|
| Max escape duration | 12 months | 4 weeks |
| Position categories | 3 states | 6 categories |
| Compression model | None | Full cost awareness |
| Debit preference | Avoid | Prefer over extension |

---

## Lessons Learned Across Versions

### From V2 → V3
1. Simplicity wins - 10 files → 1 evaluator
2. Patience beats panic - remove arbitrary ITM thresholds
3. One cost rule is enough - 7 scenarios → 1 rule

### From V3 → V3.3
1. Weekly income is the goal, not escaping ITM
2. Compression is better than extension
3. Mean reversion is real - use it

### From V3.4 → V4
1. Intrinsic % matters more than ITM %
2. Long escapes trap you - cap at 4 weeks
3. Pay small debits to avoid big opportunity costs
4. Time value is what you trade - understand it

### Implementation Lessons (V4)
1. "Adding a new version" ≠ "Making it the default"
2. Must update ALL scheduler scans
3. Type safety: Decimal (DB) → float (calculations)
4. Test end-to-end with real notifications

---

## Archived Documents

The following documents have been consolidated into this file:

| Document | Status | Notes |
|----------|--------|-------|
| `OPTIONS-NOTIFICATION-ALGORITHM-V1.md` | Archived | Historical reference |
| `OPTIONS-NOTIFICATION-ALGORITHM-V2.md` | Archived | Historical reference |
| `OPTIONS-NOTIFICATION-ALGORITHM-V3.md` | Archived | V3 full spec |
| `V3-TRADING-PHILOSOPHY.md` | Archived | V3 philosophy details |
| `V3-IMPLEMENTATION-NOTES.md` | Archived | V3 implementation details |
| `V3.3-ADDENDUM.md` | Archived | V3.3 additions |

**Current active spec:** `OPTIONS-NOTIFICATION-ALGORITHM-V4.md`

---

## Quick Reference: Version Comparison

| Feature | V2 | V3 | V3.3 | V4 |
|---------|----|----|------|-----|
| Max escape | ? | 52 weeks | 52 weeks | **4 weeks** |
| ITM thresholds | 4 levels | None | None | Intrinsic-based |
| Mean reversion | No | No | Yes | Yes + timing |
| Weekly priority | No | Pull-back | COMPRESS | Dual-benefit |
| TA for timing | Speculation | Entry only | Entry + ITM | All decisions |
| Cost model | 7 rules | 20% rule | Flexible debit | Compression cost |

---

**Document History:**
- January 20, 2026: Consolidated from V3 documentation
- Purpose: Historical reference for algorithm evolution

**Related Documents:**
- [OPTIONS-NOTIFICATION-ALGORITHM-V4.md](./OPTIONS-NOTIFICATION-ALGORITHM-V4.md) - Current active specification
- [ALGORITHM-UPGRADE-BEST-PRACTICES.md](./ALGORITHM-UPGRADE-BEST-PRACTICES.md) - How to upgrade algorithms
