# OPTIONS NOTIFICATION & RECOMMENDATION ALGORITHM V4.0

**Version:** 4.0
**Status:** ✅ ACTIVE (Implemented January 20, 2026)
**Created:** January 20, 2026
**Migration From:** V3.3/V3.4
**Philosophy:** Data-driven intrinsic/time value model with escape duration limits

**Related Documentation:**
- [ALGORITHM-HISTORY.md](./ALGORITHM-HISTORY.md) - Historical reference for all versions
- [ALGORITHM-UPGRADE-BEST-PRACTICES.md](./ALGORITHM-UPGRADE-BEST-PRACTICES.md) - How to upgrade algorithms

---

## Executive Summary

### The V4 Breakthrough

V4 introduces a **data-driven model** based on real options chain analysis. Key discoveries:

1. **Intrinsic % determines strategy** - not just ITM %
2. **The 50/50 crossover point** shifts based on time remaining
3. **Compression always costs money** - approximately the difference in time value
4. **4-week escape cap** - prevents income opportunity traps
5. **Tactical timing** - sell into strength, buy into weakness
6. **Put selling with cost basis awareness** - assignment can be good

### What Changed from V3

| Aspect | V3 | V4 | Why |
|--------|----|----|-----|
| Max escape duration | 12 months | **4 weeks** | Prevents income traps (MU $295 lesson) |
| Position assessment | ITM % only | **Intrinsic %** | More accurate - accounts for time value |
| Compression decisions | Not modeled | **Cost-aware** | Knows when compression is too expensive |
| Long-dated positions | One-move fix | **Progressive pullback** | Step-by-step recovery |
| Debit tolerance | Avoid if possible | **Prefer over extension** | $5 debit beats 12-week trap |
| Entry/exit timing | Immediate | **Tactical** | Sell high, buy low |
| Put selling | Basic | **Cost basis aware** | Assignment assessment |

### Key Metrics

| Metric | V3 | V4 | Change |
|--------|----|----|--------|
| Max Escape Duration | 52 weeks | 4 weeks | -92% |
| Position Categories | 3 states | 6 categories | +100% granularity |
| New Decision Engines | 0 | 5 | Intrinsic, Compression, Pullback, Timing, Put Assessment |
| Config Parameters | 12 | 25+ | Comprehensive but organized |

---

## Part 0: Foundational Philosophy

**This section is the foundation of ALL V4 decisions. Every rule flows from these beliefs.**

### The Six Beliefs

```
┌─────────────────────────────────────────────────────────────────┐
│           V4 FOUNDATIONAL PHILOSOPHY                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. BELIEVE IN HOLDINGS                                         │
│     Every stock I own, I believe in.                            │
│     Otherwise, why would I own it?                              │
│                                                                  │
│  2. HOLD FOREVER                                                │
│     I am not trading in and out.                                │
│     I own these stocks for life.                                │
│                                                                  │
│  3. MEAN REVERSION IS INEVITABLE                                │
│     If it goes down, it will go up.                             │
│     If it goes up, it will go down.                             │
│     This is the cycle. It is certain.                           │
│                                                                  │
│  4. PRIMARY GOAL: WEEKLY OPTIONS INCOME                         │
│     The ONLY thing I'm trying to do is earn                     │
│     options premium on my holdings every week.                  │
│     That's it. Nothing else.                                    │
│                                                                  │
│  5. AVOID UNNECESSARY RISK                                      │
│     Don't sell calls when stock is DOWN → wait for recovery     │
│     Don't sell puts when stock is UP → wait for pullback        │
│     Don't make stupid decisions. Be patient.                    │
│                                                                  │
│  6. AVOID FORCED ASSIGNMENT                                     │
│     If expiry is 1-2 days away, roll out by a week.            │
│     Give yourself CUSHION for recovery.                         │
│     If stock is up → cushion for it to go down                 │
│     If stock is down → cushion for it to go up                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### How Philosophy Drives Decisions

| Situation | Wrong Thinking | V4 Thinking |
|-----------|----------------|-------------|
| Stock dropped 5% | "Minimize damage, close/roll" | "It will recover. Wait." |
| Put is ITM | "Avoid assignment at all costs" | "I believe in this stock. Assignment is fine." |
| Call is at loss | "Close before it gets worse" | "Stock will come down. Be patient." |
| Expiry in 1-2 days | "Hope it works out" | "Roll for cushion. Give time for mean reversion." |
| Stock is down | "Sell call now to get premium" | "Wait for recovery, then sell call." |
| Stock is up | "Sell put now to get premium" | "Wait for pullback, then sell put." |

### The Time Cushion Rule

When expiry is near (≤2 days), **roll out by 1 week** regardless of profit/loss.

**Why?**
- 1-2 days is not enough time for mean reversion
- You're gambling, not investing
- A week gives cushion for the inevitable cycle

**Example:**
- Friday, your put expires Monday (2 days)
- Stock is slightly ITM
- Wrong: "Hope it recovers over weekend"
- V4: "Roll to next Friday. Give it time."

---

## Part 1: Intrinsic vs Time Value Model

### The Fundamental Concept

```
Option Price = Intrinsic Value + Time Value

INTRINSIC VALUE (ICE):
  - For CALL: max(0, Stock Price - Strike)
  - For PUT: max(0, Strike - Stock Price)
  - FIXED regardless of time remaining
  - Only changes when stock moves
  - You CANNOT decay this away with time

TIME VALUE (WATER):
  - Everything else: Option Price - Intrinsic
  - INCREASES with more time to expiration
  - DECAYS to zero by expiration (theta)
  - This is what you capture when selling options
```

### Real Data Example: TSLA $370 Call at Different Expirations

Stock Price: ~$421 | Strike: $370 | ITM: ~12%

| Expiration | Days | Option Price | Intrinsic | Time Value | Intrinsic % |
|------------|------|--------------|-----------|------------|-------------|
| Jan 30 | 10 | ~$55 | $51.30 | ~$4 | **93%** |
| Feb 27 | 38 | ~$60 | $51.30 | ~$9 | **85%** |
| Mar 20 | 59 | ~$65 | $51.30 | ~$14 | **79%** |
| Apr 17 | 87 | ~$70 | $51.30 | ~$19 | **73%** |
| May 15 | 115 | $78.10 | $51.30 | $26.80 | **66%** |
| Jun 18 | 149 | ~$84 | $51.30 | ~$33 | **61%** |
| Jul 17 | 178 | $89.05 | $51.30 | $37.75 | **58%** |
| Sep 18 | 241 | $99.38 | $51.30 | $48.08 | **52%** |

**Key Insight:** Intrinsic stays at $51.30. Only time value changes!

### The Complete ITM% x Time Matrix

```
+-------------------------------------------------------------------------+
|     INTRINSIC % = f(ITM%, Months to Expiration)                         |
+-------------------------------------------------------------------------+
|                                                                          |
|                         MONTHS TO EXPIRATION                             |
|                                                                          |
|     ITM%     |  1 mo  |  2 mo  |  4 mo  |  6 mo  |  8 mo  | Category    |
|   -----------+--------+--------+--------+--------+--------+-------------|
|     3%       |  ~65%  |  ~55%  |  ~42%  |  ~35%  |  ~28%  | LOW BAD     |
|     5%       |  ~72%  |  ~62%  |  ~50%  |  ~42%  |  ~35%  | MEDIUM      |
|     8%       |  ~80%  |  ~72%  |  ~58%  |  ~50%  |  ~42%  | CROSSOVER   |
|     12%      |  ~85%  |  ~78%  |  ~66%  |  ~57%  |  ~52%  | MED-HIGH    |
|     15%      |  ~88%  |  ~83%  |  ~72%  |  ~64%  |  ~58%  | HIGH BAD    |
|     20%      |  ~92%  |  ~88%  |  ~78%  |  ~70%  |  ~65%  | CATASTROPHIC|
|                                                                          |
|   Reading: Higher % = More intrinsic = More "ice" = Harder to manage    |
|                                                                          |
+-------------------------------------------------------------------------+
```

### The 50/50 Crossover Line

The point where intrinsic = time value (50/50) shifts based on time:

| Time Remaining | Crossover ITM% | Meaning |
|----------------|----------------|---------|
| 1 month | ~3% ITM | Nearly any ITM is mostly intrinsic |
| 2 months | ~5% ITM | Still need to be close to strike |
| 4 months | ~8% ITM | Some breathing room |
| 6 months | ~10% ITM | Moderate ITM still has hope |
| 8 months | ~12% ITM | Deep ITM can have balanced composition |

**Above the crossover:** Intrinsic dominates -> Stock must move to help you
**Below the crossover:** Time value dominates -> Time decay still helps

### Position Assessment Categories

| Intrinsic % | Category | What It Means | Strategy |
|-------------|----------|---------------|----------|
| 0-25% | SAFE | Mostly time value | Normal management |
| 25-40% | LOW BAD | More water than ice | Can wait, time helps |
| 40-55% | MEDIUM | Near crossover | Decision point |
| 55-70% | MED-HIGH | More ice than water | Need stock movement |
| 70-85% | HIGH BAD | Mostly ice | Stock must move significantly |
| 85%+ | CATASTROPHIC | Almost all ice | Cut loss or accept assignment |

---

## Part 2: Maximum Escape Duration (4 Weeks)

### The Problem with Long Escapes

When escaping ITM, V3 would search up to 52 weeks. Real-world result:

**Example:** MU $295 call -> Rolled to $350 April (3 months out)
- Position "safe" but TRAPPED
- When stock pulled back, couldn't capitalize (compression too expensive)
- Lost 12 weeks of potential weekly income

### The 4-Week Cap

```python
MAX_ESCAPE_WEEKS = 4  # Hard limit

def find_itm_escape(position):
    for weeks in [1, 2, 3, 4]:  # Only search up to 4 weeks
        roll = find_roll(weeks, delta_target=0.70)  # Delta 30
        if roll.net_cost <= max_debit:
            return roll

    # If no free escape within 4 weeks, accept small debit
    return find_roll(weeks=4, accept_debit=True, max_debit=5.00)
```

### Why 4 Weeks?

| Duration | Time Value | Compression Cost | Trapped Risk |
|----------|------------|------------------|--------------|
| 1-2 weeks | Low | Cheap | Low |
| 3-4 weeks | Moderate | Moderate | Low |
| 8 weeks | High | Expensive | **High** |
| 12+ weeks | Very High | Very Expensive | **Very High** |

**Key insight:** Better to pay $3-5 debit for a 4-week escape than get a "free" 12-week escape that traps you.

---

## Part 3: Compression Cost Model

### The Reality of Time Compression

**Compression Cost = Time Value (Current) - Time Value (Target)**

This is UNAVOIDABLE. You are paying to give up time value.

### Real Data: TSLA $370 Compression Costs

| Roll | Time Compressed | Cost |
|------|-----------------|------|
| Sep -> Jul | 2 months | **$10.33** |
| Jul -> May | 2 months | **$10.95** |
| May -> Apr | 1 month | **$8.00** |
| Sep -> May | 4 months | **$21.28** |

### Compression Cost Formula (Approximation)

For a position at ~12% ITM on a $400+ stock:
```
Compression Cost ~ $5-6 per month compressed
```

For lower-priced stocks, scale proportionally:
```
Compression Cost ~ (Stock Price / 100) x $1.25 per month
```

### When Compression Becomes Cheaper

Compression cost DECREASES when:

1. **Stock drops (intrinsic shrinks):**
   - At 12% ITM: ~$5-6/month
   - At 5% ITM: ~$3-4/month
   - At OTM: ~$1-2/month (just time value difference)

2. **You're closer to expiration:**
   - Less time value remaining = less to give up

3. **IV drops:**
   - Lower IV = lower time value = cheaper compression

### The Compression Paradox

```
+------------------------------------------------------------------+
|                  THE COMPRESSION PARADOX                          |
+------------------------------------------------------------------+
|                                                                   |
|  MORE TIME REMAINING:                                             |
|    + Lower intrinsic % (position "looks" better)                  |
|    + More room for mean reversion                                 |
|    - MORE expensive to compress (more time value to give up)      |
|    - Longer wait if stock doesn't cooperate                       |
|                                                                   |
|  LESS TIME REMAINING:                                             |
|    - Higher intrinsic % (position "looks" worse)                  |
|    - Less room for mean reversion                                 |
|    + CHEAPER to compress (less time value)                        |
|    + Faster resolution one way or another                         |
|                                                                   |
|  CONCLUSION:                                                      |
|    Don't compress just because you can.                           |
|    Compression is expensive when you need it most.                |
|                                                                   |
+------------------------------------------------------------------+
```

### Compression Decision Formula (Dual-Benefit)

Compression has **TWO benefits**, not just one:

```
┌─────────────────────────────────────────────────────────────────┐
│  DUAL-BENEFIT COMPRESSION MODEL                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  BENEFIT 1: Weekly Income                                       │
│    • Every week in far-dated = week NOT earning premium         │
│    • Value = Weeks to Expiry × Weekly Premium                   │
│    • Example: 16 weeks × $80 = $1,280                           │
│                                                                  │
│  BENEFIT 2: Cycle Capture                                       │
│    • Far-dated options can't exit cleanly on drops              │
│    • Stock drops to $320, but May option still has $26 value    │
│    • By May, stock may recover → ITM again!                     │
│    • Value = Prob(Favorable Cycle) × Exit Cost Savings          │
│    • Example: 60% × $2,400 = $1,440                             │
│                                                                  │
│  TOTAL VALUE = Benefit 1 + Benefit 2                            │
│  Example: $1,280 + $1,440 = $2,720                              │
│                                                                  │
│  DECISION: Compress when Total Value > Compression Cost         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

```python
def compression_value(position, weekly_income):
    weeks_remaining = (position.expiry - today).days / 7

    # Benefit 1: Weekly income opportunity
    benefit_1 = weeks_remaining * weekly_income

    # Benefit 2: Cycle capture value
    # Far-dated exit cost vs Weekly exit cost difference
    cycle_probability = 0.60  # 60% chance of favorable cycle
    exit_cost_savings = estimate_far_dated_price(position) - estimate_weekly_price(position)
    benefit_2 = cycle_probability * exit_cost_savings * 100  # per contract

    total_value = benefit_1 + benefit_2
    return total_value

def should_compress(position, buyback_cost, weekly_income):
    total_value = compression_value(position, weekly_income)

    if total_value > buyback_cost:
        return COMPRESS, f"Value ${total_value:.0f} > Cost ${buyback_cost:.0f}"
    elif total_value > buyback_cost * 0.90:  # within 10%
        return CONSIDER, f"Value ${total_value:.0f} ≈ Cost ${buyback_cost:.0f}"
    else:
        return WAIT, f"Value ${total_value:.0f} < Cost ${buyback_cost:.0f}"
```

### Example: AVGO $330 Call, May Expiry

| AVGO Price | Compression Cost | Total Value | Decision |
|------------|------------------|-------------|----------|
| $334 (now) | $4,100 | $2,720 | ❌ HOLD |
| $320 | $2,600 | $2,560 | ⚠️ CONSIDER |
| $315 | $2,200 | $2,520 | ✓ COMPRESS |
| $310 | $1,900 | $2,480 | ✓ COMPRESS |

---

## Part 4: Progressive Pull-Back Strategy

### For Over-Extended Positions (>4 weeks out)

When you're trapped in a long-dated position, don't try to fix it in one move. Use each mean reversion as a stepping stone.

```
+------------------------------------------------------------------+
|           PROGRESSIVE PULL-BACK FRAMEWORK                         |
+------------------------------------------------------------------+
|                                                                   |
|  SITUATION:                                                       |
|    Position is >4 weeks out from an escape roll                   |
|    Compression is expensive ($10+/2 months)                       |
|    PRIMARY strategy: Wait for stock to move                       |
|                                                                   |
|  STEP 1: WAIT FOR PULLBACK                                        |
|    Set price alerts at key levels                                 |
|    Do nothing while stock is elevated                             |
|    Patience is required                                           |
|                                                                   |
|  STEP 2: FIRST OPPORTUNITY (Stock drops 5%+)                      |
|    Option: Compress TIME (same strike, shorter duration)          |
|    Or: Raise STRIKE (closer to current price)                     |
|    Only if cost is reasonable (<$8-10)                            |
|    May choose to wait for bigger drop                             |
|                                                                   |
|  STEP 3: SECOND OPPORTUNITY (Stock drops 10%+)                    |
|    Intrinsic value has shrunk significantly                       |
|    Compression now cheaper                                        |
|    More aggressive pull-back possible                             |
|                                                                   |
|  STEP 4: FULL ESCAPE (Stock drops below strike)                   |
|    Position now OTM!                                              |
|    Pull back to weekly with credit                                |
|    Resume normal income generation                                |
|                                                                   |
+------------------------------------------------------------------+
```

### Example: TSLA $370 Sep Progressive Plan

Current: Stock at $421, Position is $370 Sep call

| Stock Price | Action | Est. Cost | Result |
|-------------|--------|-----------|--------|
| $421 (now) | WAIT | $0 | Too expensive to compress |
| $400 (5% drop) | Evaluate: Sep -> Jun | ~$13 | Maybe wait for more |
| $385 (9% drop) | Sep -> Jun, raise to $390 | ~$5-7 | 4 months out, 1% ITM |
| $370 (12% drop) | Pull to weekly $380 | Credit | Back to income! |

### The Math at Each Level

**At $421 (current):**
- Sep $370 = $99.38
- Jun $370 = ~$84
- Compress cost = ~$15

**At $400 (5% drop):**
- Sep $370 = ~$75
- Jun $370 = ~$62
- Compress cost = ~$13 (slightly better)

**At $380 (10% drop):**
- Sep $370 = ~$52
- Jun $370 = ~$40
- Compress cost = ~$12 (better)
- Jun $390 (OTM) = ~$30
- Raise + compress = ~$22 (but now OTM!)

**At $360 (15% drop):**
- Sep $370 = ~$35
- Weekly $370 (OTM) = ~$3
- Full exit cost = ~$32 BUT you're now making weekly income again

---

## Part 5: Tactical Timing

### Core Principle

**Sell options when stock is UP. Buy back options when stock is DOWN.**

This applies differently to calls and puts:

| Stock Direction | Call Action | Put Action |
|-----------------|-------------|------------|
| Stock UP | SELL calls (better premium) | BUY BACK puts (close at profit) |
| Stock DOWN | BUY BACK calls (cheaper) | SELL puts (opportunity) |

### Why Separate Buy and Sell (Don't Roll)

**Rolling = Buy Back + Sell at the same time**

The problem: You can't optimize both legs simultaneously.

| Action | When Stock DOWN | When Stock UP |
|--------|-----------------|---------------|
| Buy back | ✓ GOOD (cheaper) | ✗ Expensive |
| Sell | ✗ BAD (poor premium) | ✓ GOOD (rich premium) |
| Roll | ⚠️ Mixed | ⚠️ Mixed |

**V4 Rule: Separate the legs to optimize each one.**

- Stock is DOWN → Buy back NOW (good), sell LATER (when up)
- Stock is UP → Sell NOW (good), buy back LATER (when down)

### Call Re-Entry Rules

When you've closed a profitable call position:

```
┌─────────────────────────────────────────────────────────────────┐
│           CALL RE-ENTRY TIMING                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  IF stock is DOWN 3%+ today:                                    │
│     → Do NOT sell new call immediately                          │
│     → WAIT for recovery                                         │
│                                                                  │
│  RE-ENTRY TRIGGER:                                              │
│     → Stock UP 2% from close                                    │
│     → OR stabilization with bullish TA signal                   │
│                                                                  │
│  MAX WAIT (day-of-week aware):                                  │
│     → Wednesday = last day for same-week expiry                 │
│     → If no recovery by Wednesday → sell for next Friday        │
│                                                                  │
│  IF stock drops FURTHER:                                        │
│     → Continue waiting                                          │
│     → Do NOT sell into weakness                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Weekly Options Timeline

```
Friday    : Sell option for NEXT Friday (7 days out)
Monday    : 4 working days remain
Tuesday   : 3 working days remain
Wednesday : 2 working days remain ← Last day for same-week re-entry
Thursday  : 1 working day remains ← Too late for same-week
Friday    : Expiration day        ← Cannot sell same-week
```

---

## Part 6: Put Selling Strategy

### When to Sell Puts

Trigger conditions (OR logic - either one triggers consideration):

**Condition A: Volatility-Based Drop**
```
Trigger = Stock drops > 2x ATR (14-day)

Examples:
- IBIT (3% daily ATR) → Trigger at 6% drop
- NVDA (2.5% daily ATR) → Trigger at 5% drop
- AAPL (1.2% daily ATR) → Trigger at 2.4% drop
```

**Condition B: Technical Signals**
- RSI below 30 (oversold)
- Price hits key support level

### Which Stocks Qualify

**Only stocks in current holdings.**

Rationale: If you hold it, you believe in it. If assigned, you're happy to own more.

### Strike Selection

**Delta 20** (approximately 20% probability of assignment)

### The Cost Basis Rule

**Critical insight: Assignment is GOOD if it improves your cost basis.**

```
┌─────────────────────────────────────────────────────────────────┐
│           PUT ASSIGNMENT ASSESSMENT                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Compare: Put Strike vs Your Cost Basis                         │
│                                                                  │
│  IF strike < cost_basis:                                        │
│     → Assignment IMPROVES your average cost                     │
│     → Recommendation: HOLD (assignment acceptable)              │
│                                                                  │
│  IF strike ≈ cost_basis (within 2%):                            │
│     → Assignment is NEUTRAL                                     │
│     → Recommendation: HOLD (assignment acceptable)              │
│                                                                  │
│  IF strike > cost_basis + 2%:                                   │
│     → Assignment WORSENS your average cost                      │
│     → Recommendation: Consider CLOSE before expiry              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Example: NFLX Put Assessment

| Data Point | Value |
|------------|-------|
| Your cost basis | $85 |
| Put strike | $82 |
| Comparison | Strike < Cost Basis |
| If assigned | Buy at $82 → Lowers your average |
| Recommendation | HOLD (assignment is good) |

### Post-Assignment

When a put is assigned:
1. You now own more shares at the strike price
2. System detects increased holdings
3. Start selling covered calls on those shares
4. Wheel continues

### Notification Format (for RLHF)

```
📉 PUT SELLING OPPORTUNITY: IBIT

Trigger: Single-day drop of 6.2%
├─ 14-day ATR: 3.0%
├─ Multiplier: 2.0x
└─ Threshold: 6.0% (EXCEEDED)

Current Price: $50.69
Recommended Strike: $48 (Delta 20)
Expiration: Jan 31 (weekly)
Premium: ~$0.85/contract

Your Cost Basis: $52.00
If Assigned: Buy at $48 → IMPROVES average ✓

[Accept] [Modify] [Reject]
```

---

## Part 7: V4 Decision Framework (Calls)

### Primary Decision Tree

```
+------------------------------------------------------------------+
|           V4 POSITION EVALUATION                                  |
+------------------------------------------------------------------+
|                                                                   |
|  1. CALCULATE INTRINSIC %                                         |
|     intrinsic = max(0, stock - strike)  # for calls               |
|     intrinsic_pct = intrinsic / option_price                      |
|                                                                   |
|  2. DETERMINE CATEGORY                                            |
|     < 40% intrinsic -> TIME HELPS (can use normal strategies)     |
|     40-60% intrinsic -> CROSSOVER (decision point)                |
|     > 60% intrinsic -> STOCK MUST MOVE (wait for mean reversion)  |
|                                                                   |
|  3. IF TIME HELPS (< 40% intrinsic):                              |
|     Use normal V3 strategies:                                     |
|        - Pull-back if profitable and far-dated                    |
|        - Weekly roll if >=60% profit                              |
|        - ITM escape if needed (max 4 weeks)                       |
|                                                                   |
|  4. IF CROSSOVER (40-60% intrinsic):                              |
|     Evaluate both options:                                        |
|        - Calculate compression cost                               |
|        - Compare to expected weekly income                        |
|        - If compression > 4 weeks income -> WAIT                  |
|        - If compression <= 4 weeks income -> CONSIDER             |
|                                                                   |
|  5. IF STOCK MUST MOVE (> 60% intrinsic):                         |
|     Do NOT compress (too expensive)                               |
|        - Set price alerts for pullback                            |
|        - Wait for mean reversion                                  |
|        - Only act when stock drops 5%+                            |
|        - Consider cutting loss if thesis wrong                    |
|                                                                   |
+------------------------------------------------------------------+
```

---

## Part 8: Configuration Reference

### V4 Configuration (in algorithm_config.py)

```python
V4_CONFIG = {
    "version": "v4",
    "description": "Intrinsic/Time Value Model: 4-week escape cap, compression cost awareness",

    # === CORE THRESHOLDS ===
    "profit_threshold": 0.60,
    "max_debit_pct": 0.20,

    # === V4 KEY CHANGE: ESCAPE DURATION ===
    "max_escape_weeks": 4,                # CHANGED from 12 months
    "prefer_debit_over_extension": True,
    "extension_debit_limit": 5.00,

    # === V4 NEW: INTRINSIC VALUE MODEL ===
    "intrinsic_value": {
        "time_helps_threshold": 0.40,
        "crossover_low": 0.40,
        "crossover_high": 0.60,
        "stock_must_move_threshold": 0.60,
        "categories": {
            "safe": {"max": 0.25},
            "low_bad": {"min": 0.25, "max": 0.40},
            "medium": {"min": 0.40, "max": 0.55},
            "med_high": {"min": 0.55, "max": 0.70},
            "high_bad": {"min": 0.70, "max": 0.85},
            "catastrophic": {"min": 0.85},
        },
    },

    # === V4 NEW: COMPRESSION COST MODEL ===
    "compression": {
        "enabled": True,
        "compress_threshold_weeks": 2,
        "consider_threshold_weeks": 4,
        "too_expensive_threshold_weeks": 4,
        "cost_per_month_multiplier": 1.25,
        "base_stock_price": 100,
    },

    # === V4 NEW: PROGRESSIVE PULLBACK ===
    "progressive_pullback": {
        "enabled": True,
        "min_weeks_to_trigger": 4,
        "trigger_evaluate": 0.05,
        "trigger_act": 0.10,
        "trigger_full_escape": 0.00,
        "max_cost_at_evaluate": 10.00,
        "max_cost_at_act": 8.00,
    },

    # === ITM ESCAPE DEBIT LIMITS ===
    "itm_escape_debit_limits": {
        "slight_itm_max": 2.00,
        "moderate_itm_max": 3.00,
        "deep_itm_max": 5.00,
    },

    # ... (inherits remaining config from V3)
}
```

---

## Part 9: Quick Reference Cards

### Card 1: Intrinsic % Quick Lookup

**For 12% ITM position (like TSLA $370 at $421):**

| Time Out | Intrinsic % | Category |
|----------|-------------|----------|
| 1 month | 85% | HIGH BAD |
| 2 months | 78% | MED-HIGH |
| 4 months | 66% | MED-HIGH |
| 6 months | 57% | CROSSOVER |
| 8 months | 52% | CROSSOVER |

### Card 2: Compression Cost Quick Estimate

**Per month of compression for $400+ stock:**

| ITM % | Cost/Month |
|-------|------------|
| OTM | ~$2 |
| 5% | ~$3-4 |
| 10% | ~$5 |
| 15% | ~$5-6 |
| 20% | ~$6-7 |

### Card 3: Decision Quick Guide

| Intrinsic % | Primary Strategy | Avoid |
|-------------|------------------|-------|
| < 40% | Normal V3 strategies | N/A |
| 40-60% | Evaluate carefully | Expensive compression |
| > 60% | Wait for stock drop | Any compression |
| > 80% | Cut loss or wait | Everything except exit |

### Card 4: Progressive Pullback Triggers

| Stock Movement | Action | Max Cost |
|----------------|--------|----------|
| Down 5% | Evaluate options | $10 |
| Down 10% | Compress or raise | $8 |
| Below strike | Full exit to weekly | Credit |
| Up 5% | Continue waiting | $0 |
| Up 10% | Evaluate cut loss | N/A |

---

## Part 10: Real Position Examples

### Example 1: TSLA $370 Sep

**Current State:**
- Stock: $421
- Strike: $370 (12% ITM)
- Expiration: Sep 18 (8 months)
- Option: $99.38
- Intrinsic: $51.30 (52%)
- Time Value: $48.08 (48%)

**Assessment:** At crossover. Half ice, half water.

**V4 Strategy:**
1. Do NOT compress now (costs $10+/2 months)
2. Set alerts: $400, $385, $370
3. Wait for pullback
4. If TSLA drops to $385 -> Compress Sep->Jun + raise to $390
5. If TSLA drops to $370 -> Full exit to weekly

### Example 2: AVGO $330 May

**Current State:**
- Stock: $335
- Strike: $330 (1.6% ITM)
- Expiration: May 15 (4 months)
- Option: $41.65
- Intrinsic: $5 (12%)
- Time Value: $36.65 (88%)

**Assessment:** LOW BAD. Mostly water.

**V4 Strategy:**
1. Position is healthy - mostly time value
2. Can afford to wait
3. If AVGO drops below $330 -> Natural OTM exit
4. Compression would cost ~$9 - not worth it yet

---

## Part 11: Migration from V3

### Configuration Changes

| V3 Parameter | V4 Parameter | Change |
|--------------|--------------|--------|
| `max_roll_months: 12` | `max_escape_weeks: 4` | 12 months -> 4 weeks |
| N/A | `intrinsic_value` | NEW section |
| N/A | `compression` | NEW section |
| N/A | `progressive_pullback` | NEW section |
| `roll_options.max_roll_weeks: 52` | `roll_options.max_roll_weeks: 4` | 52 -> 4 |

### New Files Required (Implementation Phase)

| File | Purpose |
|------|---------|
| `compression_calculator.py` | Calculate compression costs |
| Updates to `position_evaluator.py` | Add intrinsic % calculation |
| Updates to `zero_cost_finder.py` | Cap at 4 weeks |

### New Functions Required (Implementation Phase)

```python
def calculate_intrinsic_percentage(position) -> float:
    """Returns intrinsic value as % of option price"""

def estimate_compression_cost(position, target_expiration) -> float:
    """Estimates cost to compress to target expiration"""

def evaluate_compression_worthiness(position, target_expiration) -> tuple:
    """Returns (COMPRESS|CONSIDER|WAIT, rationale)"""

def get_progressive_pullback_plan(position) -> list:
    """Returns price triggers and actions for over-extended position"""
```

### Rollback Procedure

To revert to V3:
1. Set `ALGORITHM_VERSION=v3` in `.env`
2. Restart the application
3. V3 code paths will be used

V3 configuration and code remain untouched.

---

## Part 12: RLHF Considerations

### New Epoch

When V4 is activated:
```python
from datetime import date
from app.modules.strategies.algorithm_config import start_new_rlhf_epoch

start_new_rlhf_epoch("v4", date(2026, 1, 20))
```

This ensures:
- V3.4 feedback is preserved but not used for V4 learning
- V4 starts fresh pattern detection
- Historical data remains tagged with its algorithm version

---

**END OF V4 SPECIFICATION**

---

**Document History:**
- January 20, 2026: Initial V4 specification (config + documentation)
- Status: Awaiting review before implementation

**Data Sources:**
- Real TSLA/AVGO options chains (January 20, 2026)
- V3.3/V3.4 production observations

**Related Documents:**
- [V3 Specification](./OPTIONS-NOTIFICATION-ALGORITHM-V3.md)
- [V3.3 Addendum](./V3.3-ADDENDUM.md)
- [Recommendation Engine](./RECOMMENDATION-ENGINE.md)
