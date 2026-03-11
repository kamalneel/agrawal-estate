# Stuck Position Escape Framework

**Version:** 5.0
**Created:** February 3, 2026
**Last Updated:** February 3, 2026
**Status:** Validated with real Robinhood data (includes LIFE SUPPORT discovery)

---

## Executive Summary

This framework addresses two distinct problems that occur when selling options:

1. **TIME TRAPPED**: Long-dated positions that can't easily compress to weekly
2. **DEEP UNDERWATER**: Weekly positions that are ITM and earning reduced income

These are different problems requiring different solutions.

---

## Part 1: Position Categories

### Category Definitions

| Category | Definition | Roll Cadence | ITM Status | Income |
|----------|------------|--------------|------------|--------|
| **SWIMMING** | Healthy position | Weekly | OTM or ATM | Full ($150-350/week) |
| **SHALLOW UNDERWATER** | Minor issue | Weekly | 1-10% ITM | Good ($50-150/week) |
| **DEEP UNDERWATER** | Reduced income | Weekly | 10-25% ITM | Low ($15-50/week) |
| **LIFE SUPPORT** | Minimal income | Bi-weekly+ | 25-35% ITM | Minimal ($0.30+/roll) |
| **DROWNING** | Can't roll for credit | Any | >35% ITM | **Debit required** |
| **TIME TRAPPED** | Stuck in time | N/A | Any ITM | Zero (long-dated) |

### The Critical Distinction: LIFE SUPPORT vs DROWNING

**LIFE SUPPORT** (NOT drowning):
- Weekly rolls hit breakeven ($0)
- But bi-weekly or monthly rolls still generate a credit
- You can maintain the position without paying money
- Example: HOOD at 30% ITM, bi-weekly roll = $0.30 credit

**DROWNING** (true crisis):
- ALL rolls (weekly, bi-weekly, monthly) require a debit
- You MUST pay money to maintain the position
- This is the actual point requiring action

### Validated Roll Data by ITM Depth (HOOD, High IV)

| ITM % | Weekly Roll | Bi-Weekly Roll | Status |
|-------|-------------|----------------|--------|
| 26.8% | $15 credit | ~$30+ credit | Deep Underwater |
| 30.0% | $0 (breakeven) | **$0.30 credit** | **LIFE SUPPORT** |
| ~35%+ | Debit | ~$0 or debit | DROWNING (estimated) |

### Visual Guide

```
                          TIME TO EXPIRATION
                      Weekly/Bi-Weekly       Long-Dated (>4 weeks)
                 ┌───────────────────────┬─────────────────────────┐
         OTM    │      SWIMMING         │      TIME TRAPPED       │
                │   (Full weekly income)│   (Waiting, no income)  │
    I   ────────┼───────────────────────┼─────────────────────────┤
    T   1-10%   │  SHALLOW UNDERWATER   │      TIME TRAPPED       │
    M    ITM    │  (Good weekly income) │   (Waiting, no income)  │
        ────────┼───────────────────────┼─────────────────────────┤
    %   10-25%  │   DEEP UNDERWATER     │      TIME TRAPPED       │
         ITM    │  (Low weekly income)  │   (Waiting, no income)  │
        ────────┼───────────────────────┼─────────────────────────┤
       25-35%   │    LIFE SUPPORT       │      TIME TRAPPED       │
         ITM    │ (Bi-weekly for credit)│   (Waiting, no income)  │
        ────────┼───────────────────────┼─────────────────────────┤
        >35%    │      DROWNING         │      TIME TRAPPED       │
         ITM    │ (ALL rolls = debit)   │   (Waiting, no income)  │
                └───────────────────────┴─────────────────────────┘

KEY INSIGHT: You're only DROWNING when you can't roll for ANY credit.
If bi-weekly or monthly rolls still generate credit, you're on LIFE SUPPORT - not drowning.
```

### Your Current Positions (Feb 3, 2026 - UPDATED)

| Position | Stock Price | ITM % | Expiry | Category | Status |
|----------|-------------|-------|--------|----------|--------|
| HOOD $111 put | **$85.54** | **29.8%** | Weekly | **LIFE SUPPORT** | Bi-weekly roll = $0.30 credit |
| AVGO $360 put | **$309.12** | **16.5%** | Weekly | **DEEP UNDERWATER** | Weekly roll = $0.25 credit |
| TSLA $370 call | $424.38 | 12.8% | Sept 18 | TIME TRAPPED | Waiting, no income |
| MU $350 call | $419.80 | 16.6% | Apr 17 | TIME TRAPPED | Waiting, no income |

**STATUS ASSESSMENT:**
- **HOOD**: On LIFE SUPPORT but NOT drowning. Weekly rolls = $0, but bi-weekly rolls = $0.30/contract ($90 total).
  - Strategy: Roll bi-weekly, wait for recovery. Annual income: ~$2,340 (3 contracts)
  - You're a HOOD believer - this strategy aligns with your conviction
- **AVGO**: Deep underwater but stable. Weekly rolls still generating $0.25/contract.
  - Strategy: Continue weekly rolls, monitor for further decline

---

## Part 2: DEEP UNDERWATER Positions

### Definition
- Already on weekly rolls
- Rolling each week for a small credit
- ITM >10%, earning less than optimal

### The Key Insight

**You're NOT stuck - you're earning income, just less than ideal.**

The question isn't "how do I escape?" but rather "how do I optimize?"

### Weekly Income by ITM Depth (Validated)

| ITM % | Weekly Credit/Contract | Annual Income | Status |
|-------|----------------------|---------------|--------|
| 25-30% | ~$15-25 | ~$750-1,250 | Survival mode |
| 15-25% | ~$20-35 | ~$1,000-1,750 | Reduced income |
| 10-15% | ~$30-50 | ~$1,500-2,500 | Moderate income |
| 5-10% | ~$50-100 | ~$2,500-5,000 | Good income |
| 0-5% (ATM) | ~$100-350 | ~$5,000-17,500 | Full income |

### Validated Data Points (Robinhood, Feb 3, 2026)

| Position | ITM % | Weekly Roll Credit |
|----------|-------|-------------------|
| HOOD $111 put | 26.8% | **$15/contract** |
| AVGO $360 put | 15.8% | **$23/contract** |

### Decision Framework for DEEP UNDERWATER

```
STEP 1: Calculate current weekly income
  → Use Robinhood roll screen for actual number

STEP 2: Calculate ATM weekly income (what you COULD earn)
  → Check ATM strike premium

STEP 3: Calculate opportunity cost
  → Opportunity Cost = (ATM Income - Current Income) × 52 weeks

STEP 4: Evaluate options
```

### Option A: HOLD STRIKE (Wait for Recovery)

**How it works:**
- Keep rolling weekly at current strike
- Earn small credit each week
- Wait for stock to move favorably

**When to use:**
- You believe stock will recover (calls: drop, puts: rise)
- Opportunity cost is acceptable
- You don't want to lock in losses

**Math:**
```
Cost: $0 upfront
Income: Current weekly credit × 52 = Annual income
Opportunity cost: (ATM - Current) × 52 = Lost potential income

Example (HOOD $111 put):
  Current: $15/week × 52 = $780/year
  ATM ($87): ~$150/week × 52 = $7,800/year
  Opportunity cost: $7,020/year

  BUT if HOOD recovers to $111:
    Your put becomes ATM
    You start earning full income
    No loss locked in
```

### Option B: MIGRATE STRIKE

**How it works:**
- Roll to a better strike (closer to ATM)
- Pay a debit to improve position
- Earn higher weekly income going forward

**When to use:**
- Stock unlikely to recover
- Debit is reasonable relative to improved income
- You want to accelerate recovery

**Math:**
```
For PUTS (migrate to LOWER strike = closer to ATM):
  Debit = Current Strike Premium - New Strike Premium
  Income improvement = New Weekly - Current Weekly
  Breakeven = Debit ÷ Weekly Improvement

Example (HOOD $111 → $100 put):
  Current $111: $24.08 to buy back
  New $100: ~$14.00 to sell (estimate)
  Debit: ~$10.08/share = $1,008/contract

  Weekly improvement: ~$30 - $15 = $15/week
  Breakeven: $1,008 ÷ $15 = 67 weeks ❌ Too long
```

### Option C: TAKE LOSS (Restart at ATM)

**How it works:**
- Buy back current position (realize loss)
- Immediately sell new ATM option
- Start earning full premium

**When to use:**
- Stock very unlikely to recover
- Breakeven on migration too long
- You want to maximize income NOW

**Math:**
```
Loss = Buyback Cost - Original Premium Received
Full ATM Income = ~$150-350/week
Breakeven = Loss ÷ (ATM Income - Current Income)

Example (HOOD $111 put):
  Buyback: $24.08 × 100 × 3 = $7,224
  Original premium (assume): ~$5.00 × 100 × 3 = $1,500
  Loss: $7,224 - $1,500 = $5,724

  Income improvement: $150 - $15 = $135/week × 3 = $405/week
  Breakeven: $5,724 ÷ $405 = 14 weeks ✓ Reasonable
```

### DEEP UNDERWATER Decision Matrix

| Situation | Recommendation |
|-----------|----------------|
| Stock likely to recover within 3 months | **HOLD STRIKE** |
| Stock flat, migration breakeven < 26 weeks | **MIGRATE STRIKE** |
| Stock flat, migration breakeven > 26 weeks | **HOLD STRIKE** or **TAKE LOSS** |
| Stock moving further against you | **TAKE LOSS** |
| High IV stock (>60%) | **HOLD STRIKE** (credits are decent) |
| Low IV stock (<35%) | **TAKE LOSS** (credits too small) |

---

## Part 3: LIFE SUPPORT and DROWNING Positions

### The Critical Distinction

**LIFE SUPPORT** ≠ **DROWNING**

| Category | Weekly Roll | Bi-Weekly Roll | Monthly Roll | Action |
|----------|-------------|----------------|--------------|--------|
| **LIFE SUPPORT** | $0 (breakeven) | Credit ($0.30+) | Credit | Roll longer, wait |
| **DROWNING** | Debit | Debit | Debit | MUST take action |

### LIFE SUPPORT Definition

- Weekly rolls have hit breakeven ($0 credit)
- BUT bi-weekly or monthly rolls still generate a credit
- You can maintain the position without paying money
- Time is still on your side (just slower)

**Key Insight:** As long as you can roll for ANY credit, you're NOT drowning.

### LIFE SUPPORT Strategy

**The goal:** Keep the position alive while waiting for recovery.

**How it works:**
1. Stop rolling weekly (no credit available)
2. Roll bi-weekly (or longer) for a small credit
3. Wait for stock to recover
4. Resume weekly rolls when ITM% improves

**Example (HOOD at 30% ITM):**
```
Weekly roll: $0 (breakeven) → Don't do this
Bi-weekly roll: $0.30/contract → DO THIS

Income on bi-weekly cadence:
  $0.30 × 3 contracts × 26 bi-weekly periods = $2,340/year

  That's still ~9% annualized return on capital at risk!
```

**When to use LIFE SUPPORT strategy:**
- You believe in the stock (HOOD believer)
- Bi-weekly (or longer) rolls still generate credit
- You're willing to wait for recovery
- Taking loss would hurt more than reduced income

### DROWNING Definition (True Crisis)

- **ALL rolls require a debit** - weekly, bi-weekly, AND monthly
- You MUST pay money to maintain the position
- Every roll costs you cash
- This is the actual crisis point

### How to Detect LIFE SUPPORT vs DROWNING

```python
def get_position_status(position, stock_price):
    """
    Determine if position is LIFE SUPPORT or DROWNING.
    """
    # Check weekly roll
    weekly_credit = get_roll_credit(position, days=7)

    # Check bi-weekly roll
    biweekly_credit = get_roll_credit(position, days=14)

    # Check monthly roll
    monthly_credit = get_roll_credit(position, days=28)

    if weekly_credit > 0:
        return "DEEP_UNDERWATER"  # Still getting weekly credits
    elif biweekly_credit > 0 or monthly_credit > 0:
        return "LIFE_SUPPORT"  # Can still roll for credit
    else:
        return "DROWNING"  # All rolls are debits
```

### Validated Data: LIFE SUPPORT Thresholds

| Stock | ITM % | Weekly | Bi-Weekly | Status |
|-------|-------|--------|-----------|--------|
| HOOD | 26.8% | $15 credit | ~$30 credit | Deep Underwater |
| HOOD | 30.0% | $0 (breakeven) | **$0.30 credit** | **LIFE SUPPORT** |
| HOOD | ~35%+ | Debit | ~$0 or debit | DROWNING (estimated) |

### What To Do on LIFE SUPPORT

**Option A: EXTEND ROLL CADENCE (Recommended for believers)**
- Switch from weekly to bi-weekly rolls
- Accept reduced but still positive income
- Wait for recovery

**Math:**
```
HOOD at 30% ITM, bi-weekly roll = $0.30/contract

Income comparison:
  Weekly at 25% ITM: $15 × 52 = $780/year per contract
  Bi-weekly at 30% ITM: $0.30 × 26 = $7.80/year per contract ← Much less!

BUT you're still:
  ✓ Not paying money
  ✓ Maintaining the position
  ✓ Waiting for recovery
  ✓ Aligned with your conviction
```

**Option B: TAKE LOSS (For non-believers)**
- If you don't believe in the stock
- Or opportunity cost is too high
- Close position, restart at ATM

### What To Do When DROWNING (All Rolls = Debit)

**There is only ONE option: TAKE LOSS**

When even monthly rolls require a debit, you're paying to maintain a losing position.

**Math:**
```
If monthly roll = -$50 debit:
  Annual cost: $50 × 12 = $600/year to maintain

Better to:
  Take loss once
  Restart at ATM
  Earn $150+/week = $7,800/year
```

### Warning Signs Approaching DROWNING

Set alerts at these levels:

**High IV stocks (HOOD-like):**
```
25% ITM: Weekly credit drops to ~$15 (Deep Underwater)
30% ITM: Weekly credit = $0 (LIFE SUPPORT begins)
35% ITM: Bi-weekly credit approaching $0 (DROWNING warning!)
```

**Price alerts for HOOD $111 put:**
```
HOOD $85: Currently here, 30% ITM, LIFE SUPPORT
HOOD $80: 38.8% ITM → Check bi-weekly credit, may be DROWNING
HOOD $75: 48% ITM → Likely DROWNING, consider taking loss

HOOD $95: 16.8% ITM → Back to DEEP UNDERWATER, resume weekly
HOOD $100: 11% ITM → SHALLOW UNDERWATER
HOOD $111: ATM → Full income restored!
```

---

## Part 4: TIME TRAPPED Positions

### Definition
- Long-dated position (>4 weeks to expiry)
- ITM and can't easily compress to weekly
- Earning ZERO weekly income while waiting

### The Key Insight

**You're stuck in time, missing income opportunities every week.**

The question is: "Is the compression cost worth the weekly income I'd gain?"

### The Compression Decision

```
Compression Cost = Long-dated Premium - Weekly Premium (same strike)

Weekly Income After = Credit from rolling weekly

Breakeven = Compression Cost ÷ Weekly Income

Rule of Thumb:
  Breakeven < 26 weeks: COMPRESS makes sense
  Breakeven 26-52 weeks: MARGINAL, depends on outlook
  Breakeven > 52 weeks: DON'T COMPRESS, wait or take loss
```

### Decision Framework for TIME TRAPPED

```
STEP 1: Calculate compression cost (same strike)
  → Use Robinhood: Long-dated buyback - Weekly sell

STEP 2: Calculate weekly income if compressed
  → What would weekly roll generate?

STEP 3: Calculate breakeven weeks
  → Compression Cost ÷ Weekly Income

STEP 4: Consider lower strike compression
  → Might get credit, but sacrifice strike value

STEP 5: Evaluate options based on breakeven
```

### Option A: WAIT (Hold Long-Dated)

**How it works:**
- Do nothing, hold the position
- Set price alerts for favorable moves
- Act when stock moves or time runs short

**When to use:**
- Stock expected to move favorably
- Compression breakeven > 52 weeks
- You have > 60 days to expiration

**Cost:** ~$0 (minimal theta on long-dated options)

**Example (TSLA $370 Sept call):**
```
Current: TSLA at $424, you're 12.8% ITM
Expected: TSLA might pull back

WAIT with alerts:
  Alert 1: TSLA $410 (9.8% ITM) - Reassess
  Alert 2: TSLA $400 (7.5% ITM) - Compress to weekly
  Alert 3: TSLA $385 (3.9% ITM) - Compress, good income
  Alert 4: TSLA $370 (ATM) - Exit or roll for credit
```

### Option B: COMPRESS TO WEEKLY (Same Strike)

**How it works:**
- Buy back long-dated option
- Sell weekly option at SAME strike
- Start earning weekly income

**When to use:**
- Compression breakeven < 26 weeks
- Stock NOT expected to recover soon
- You want income NOW

**Math:**
```
Example (TSLA $370 call):
  Sept $370 buyback: ~$100.80
  Weekly $370 sell: ~$57.05
  Compression cost: $43.75/share = $4,375/contract

  Weekly income at $370 (12.8% ITM): ~$30-45/week
  Breakeven: $4,375 ÷ $37.50 = 117 weeks ❌ Too long
```

### Option C: COMPRESS TO LOWER STRIKE

**How it works:**
- Buy back long-dated option
- Sell weekly at LOWER strike (calls) or HIGHER strike (puts)
- Get credit or smaller debit, but sacrifice strike

**When to use:**
- Same-strike compression too expensive
- You're willing to sacrifice some strike value
- Credit or small debit is available

**Math:**
```
Example (TSLA $370 Sept → $335 Weekly):
  Sept $370 buyback: ~$97.80
  Weekly $335 sell: ~$88.80
  Net: $9.00 debit = $900/contract

  Strike sacrifice: $370 - $335 = $35 = $3,500/contract
  Weekly income at $335 (21% ITM): ~$15-20/week

  Total cost: $900 + $3,500 = $4,400
  Weekly income: ~$17.50/week
  Breakeven: 251 weeks ❌ Terrible
```

### Option D: TAKE LOSS (Exit and Restart)

**How it works:**
- Buy back the long-dated option (full cost)
- Sell new ATM weekly immediately
- Start earning maximum income

**When to use:**
- All compression options have bad breakeven
- Stock unlikely to recover
- You want to stop the bleeding

**Math:**
```
Example (TSLA $370 Sept call):
  Buyback: $100.80/share = $10,080/contract
  Original premium received: ~$15.00 = $1,500
  Loss: $8,580

  New ATM weekly ($425): ~$12.00 = $1,200/week income
  Current income: $0/week
  Improvement: $1,200/week

  Breakeven: $8,580 ÷ $1,200 = 7 weeks ✓ Fast recovery
```

### TIME TRAPPED Decision Matrix

| Compression Breakeven | Stock Outlook | Recommendation |
|----------------------|---------------|----------------|
| < 26 weeks | Any | **COMPRESS** |
| 26-52 weeks | Favorable move expected | **WAIT** |
| 26-52 weeks | No move expected | **COMPRESS** or **TAKE LOSS** |
| > 52 weeks | Favorable move expected | **WAIT** |
| > 52 weeks | No move expected | **TAKE LOSS** |

---

## Part 5: The Complete Algorithm

### Master Decision Tree

```python
def evaluate_stuck_position(position, stock_price, iv):
    """
    Master algorithm for stuck position evaluation.
    Returns category and recommended action.
    """

    # Calculate basics
    itm_pct = calculate_itm_pct(position, stock_price)
    days_to_exp = (position.expiration - today).days
    drowning_threshold = get_drowning_threshold(iv)

    # STEP 1: Categorize the position
    if days_to_exp <= 7:  # Weekly positions
        if itm_pct <= 0:
            category = "SWIMMING"
        elif itm_pct <= 10:
            category = "SHALLOW_UNDERWATER"
        elif itm_pct < drowning_threshold:
            category = "DEEP_UNDERWATER"
        else:
            category = "DROWNING"  # Weekly rolls no longer profitable
    else:  # > 7 days (long-dated)
        if itm_pct > 0:
            category = "TIME_TRAPPED"
        else:
            category = "SWIMMING"  # OTM long-dated is fine

    # STEP 2: Get recommendation based on category
    if category == "SWIMMING":
        return swimming_strategy(position)

    elif category == "SHALLOW_UNDERWATER":
        return shallow_underwater_strategy(position, stock_price)

    elif category == "DEEP_UNDERWATER":
        return deep_underwater_strategy(position, stock_price)

    elif category == "DROWNING":
        return drowning_strategy(position, stock_price)  # TAKE LOSS immediately

    elif category == "TIME_TRAPPED":
        return time_trapped_strategy(position, stock_price)


def get_drowning_threshold(iv):
    """
    Return the ITM% at which weekly rolls flip to breakeven/debit.
    Based on validated Robinhood data.
    """
    if iv >= 60:      # High IV (HOOD-like)
        return 30
    elif iv >= 35:    # Medium IV (AVGO-like)
        return 17
    else:             # Low IV
        return 10  # Estimated


def drowning_strategy(position, stock_price):
    """Strategy for DROWNING positions - rolls no longer profitable."""

    # Calculate take-loss breakeven
    loss = get_buyback_cost(position) - position.original_premium
    atm_income = get_atm_weekly_premium(position.symbol)
    take_loss_breakeven = loss / atm_income if atm_income > 0 else float('inf')

    # DROWNING positions should almost always take loss
    # Only exception: imminent recovery expected
    if stock_expected_to_recover_soon(position.symbol):  # Within 2 weeks
        targets = calculate_recovery_targets(position, stock_price)
        return Action("WAIT_SHORT_TERM",
            reason="DROWNING but recovery expected - wait max 2 weeks",
            alerts=targets,
            deadline=today + timedelta(weeks=2),
            fallback="TAKE_LOSS")
    else:
        return Action("TAKE_LOSS",
            reason=f"DROWNING - rolls no longer profitable. Take loss, recover in {take_loss_breakeven:.0f} weeks at ATM",
            loss=loss,
            new_income=atm_income,
            urgency="HIGH")


def deep_underwater_strategy(position, stock_price):
    """Strategy for DEEP UNDERWATER positions (weekly, >10% ITM)."""

    weekly_income = get_weekly_roll_credit(position)
    atm_income = get_atm_weekly_premium(position.symbol)

    # Option A: Hold
    hold_opportunity_cost = (atm_income - weekly_income) * 52

    # Option B: Take Loss
    loss = get_buyback_cost(position) - position.original_premium
    income_improvement = atm_income - weekly_income
    take_loss_breakeven = loss / income_improvement if income_improvement > 0 else float('inf')

    # Decision
    if stock_expected_to_recover(position.symbol):
        return Action("HOLD_STRIKE",
            reason="Stock expected to recover, keep rolling weekly",
            weekly_income=weekly_income)

    elif take_loss_breakeven < 20:  # Less than 20 weeks
        return Action("TAKE_LOSS",
            reason=f"Breakeven in {take_loss_breakeven:.0f} weeks - restart at ATM",
            loss=loss,
            new_income=atm_income)

    else:
        return Action("HOLD_STRIKE",
            reason="Keep rolling, taking loss not worth it",
            weekly_income=weekly_income)


def time_trapped_strategy(position, stock_price):
    """Strategy for TIME TRAPPED positions (long-dated, ITM)."""

    compression_cost = get_compression_cost(position)
    weekly_income = estimate_weekly_income_at_strike(position.strike, stock_price)
    breakeven_weeks = compression_cost / weekly_income if weekly_income > 0 else float('inf')

    # Option: Take loss
    loss = get_buyback_cost(position) - position.original_premium
    atm_income = get_atm_weekly_premium(position.symbol)
    take_loss_breakeven = loss / atm_income if atm_income > 0 else float('inf')

    # Decision tree
    if breakeven_weeks < 26:
        return Action("COMPRESS_TO_WEEKLY",
            reason=f"Compress - breakeven in {breakeven_weeks:.0f} weeks",
            cost=compression_cost,
            weekly_income=weekly_income)

    elif stock_expected_to_recover(position.symbol) and position.days_to_exp > 45:
        # Calculate price targets
        targets = calculate_price_targets(position)
        return Action("WAIT",
            reason="Wait for stock to move favorably",
            alerts=targets)

    elif take_loss_breakeven < 12:  # 3 months
        return Action("TAKE_LOSS",
            reason=f"Take loss - recover in {take_loss_breakeven:.0f} weeks at ATM",
            loss=loss,
            new_income=atm_income)

    else:
        return Action("WAIT",
            reason="No good options - wait and reassess",
            reassess_date=today + timedelta(weeks=2))
```

---

## Part 6: Price Alert System

### DROWNING Warning Alerts (Set These Now!)

**HOOD $111 put (currently DROWNING at 30% ITM, $85.39):**
```
DOWNSIDE (further decline):
  Alert: HOOD $80 → 38.8% ITM, deep in DROWNING territory
  Action: TAKE LOSS IMMEDIATELY if this triggers

UPSIDE (recovery):
  Alert: HOOD $95 → 16.8% ITM, back to DEEP UNDERWATER (resume rolls!)
  Alert: HOOD $100 → 11% ITM, SHALLOW UNDERWATER
  Alert: HOOD $111 → ATM, full income
```

**AVGO $360 put (currently near-DROWNING at 16.5% ITM, $309.12):**
```
DOWNSIDE (further decline):
  Alert: AVGO $300 → 20% ITM, deep DROWNING
  Action: TAKE LOSS IMMEDIATELY if this triggers

UPSIDE (recovery):
  Alert: AVGO $320 → 12.5% ITM, DEEP UNDERWATER (decent rolls)
  Alert: AVGO $340 → 5.9% ITM, SHALLOW UNDERWATER
  Alert: AVGO $360 → ATM, full income
```

### For DEEP UNDERWATER Positions

Set alerts for when position approaches DROWNING or improves:

```
Generic High IV Stock ($X put at 20% ITM):
  DROWNING WARNING: Stock drops to 25% ITM
  DROWNING ALERT: Stock drops to 30% ITM → TAKE LOSS
  RECOVERY: Stock rises to 15% ITM → Better rolls
  RECOVERY: Stock rises to 10% ITM → Good rolls
```

### For TIME TRAPPED Positions

Set alerts for compression opportunities:

```
TSLA $370 call (currently 12.8% ITM at $424):
  Alert: TSLA $410 → 9.8% ITM, reassess compression
  Alert: TSLA $400 → 7.5% ITM, compression attractive
  Alert: TSLA $385 → 3.9% ITM, compress now
  Alert: TSLA $370 → ATM, exit or roll for credit

MU $350 call (currently 16.6% ITM at $419.80):
  Alert: MU $390 → 10.3% ITM, reassess compression
  Alert: MU $375 → 6.7% ITM, compression attractive
  Alert: MU $360 → 2.8% ITM, compress now
  Alert: MU $350 → ATM, exit or roll for credit
```

---

## Part 7: Summary Cheat Sheet

### Quick Reference

| Category | You Are | Earning | Goal | Primary Strategy |
|----------|---------|---------|------|------------------|
| SWIMMING | Weekly + OTM | Full income | Maintain | Keep rolling weekly |
| SHALLOW UNDERWATER | Weekly + <10% ITM | Good income | Recover | Roll weekly, wait |
| DEEP UNDERWATER | Weekly + 10-25% ITM | Low income | Optimize | Roll weekly or take loss |
| **LIFE SUPPORT** | Weekly=$0, Bi-weekly=credit | Minimal income | Survive | **Roll bi-weekly, wait** |
| **DROWNING** | ALL rolls = debit | **Negative** | **Escape** | **TAKE LOSS** |
| TIME TRAPPED | Long-dated + ITM | Nothing | Escape | Wait, compress, or take loss |

### Key Thresholds (High IV Stocks like HOOD)

| ITM % | Weekly Roll | Bi-Weekly Roll | Category |
|-------|-------------|----------------|----------|
| 25% | ~$15 credit | ~$30 credit | Deep Underwater |
| 30% | $0 | **$0.30 credit** | **LIFE SUPPORT** |
| 35%+ | Debit | ~$0 or debit | DROWNING |

### One-Minute Decision

**LIFE SUPPORT (weekly=$0, but bi-weekly=credit):**
1. Do you believe in the stock?
2. YES → Switch to bi-weekly rolls, wait for recovery
3. NO → Take loss, restart at ATM

**DROWNING (ALL rolls = debit):**
1. You're paying money to hold a losing position
2. **TAKE LOSS IMMEDIATELY** - no other option

**DEEP UNDERWATER:**
1. Check: Will stock recover in 3 months?
2. YES → Keep rolling weekly
3. NO → Calculate take-loss breakeven. If < 20 weeks, take loss.

**TIME TRAPPED:**
1. Check: Compression breakeven < 26 weeks?
2. YES → Compress to weekly
3. NO → Will stock recover before expiry?
4. YES → Wait with price alerts
5. NO → Take loss if breakeven < 12 weeks, else wait

---

## Appendix A: Validated Data

### Robinhood Roll Credits (Feb 3, 2026)

| Stock | Strike | Type | Stock Price | ITM % | Weekly | Bi-Weekly | Status |
|-------|--------|------|-------------|-------|--------|-----------|--------|
| HOOD | $111 | Put | $87.53 | 26.8% | $15 | ~$30 | Deep Underwater |
| HOOD | $111 | Put | $85.54 | 29.8% | **$0** | **$0.30** | **LIFE SUPPORT** |
| AVGO | $360 | Put | $310.77 | 15.8% | $23 | ~$46 | Deep Underwater |
| AVGO | $360 | Put | $309.12 | 16.5% | $0.25 | ~$0.50 | Near-LIFE SUPPORT |
| MU | $350 | Call | $419.80 | 16.6% | - | - | Monthly: $808 |

### Key Findings

**1. LIFE SUPPORT Discovery (Critical Insight):**
When weekly rolls hit $0 (breakeven), you're NOT drowning if bi-weekly rolls still generate credit!

| Stock | ITM % | Weekly | Bi-Weekly | Actual Status |
|-------|-------|--------|-----------|---------------|
| HOOD | 30% | $0 | **$0.30 credit** | **LIFE SUPPORT** (not drowning!) |

**2. The Real DROWNING Threshold:**
DROWNING = when ALL rolls (weekly, bi-weekly, monthly) require a debit.
Estimated at ~35%+ ITM for high IV stocks (not yet validated).

**3. Income on LIFE SUPPORT:**
```
HOOD at 30% ITM, bi-weekly roll = $0.30/contract
3 contracts × $0.30 × 26 bi-weekly periods = $23.40/year

Wait... that's very low. BUT you're:
- Not paying money (positive cash flow)
- Maintaining your position
- Waiting for recovery
- Aligned with conviction (HOOD believer)
```

**4. IV Determines Survivability:**
- High IV stocks can reach 30%+ ITM before LIFE SUPPORT
- Medium IV stocks hit LIFE SUPPORT around ~17% ITM
- The key question: Can you roll for ANY credit?

**5. Robinhood vs API Execution:**
- Robinhood executes closer to mid-market
- API bid/ask data significantly overstates costs
- Always use Robinhood roll preview for actual numbers

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **ITM** | In-The-Money (stock beyond strike) |
| **ATM** | At-The-Money (stock at strike) |
| **OTM** | Out-of-The-Money (stock not at strike yet) |
| **Compression** | Moving from long-dated to weekly expiration |
| **Migration** | Changing strike price while staying at same expiration |
| **Weekly Roll** | Closing current week, opening next week |
| **Bi-Weekly Roll** | Closing current position, opening +14 days out |
| **Time Value** | Option premium beyond intrinsic value |
| **IV** | Implied Volatility - market's expected movement |
| **LIFE SUPPORT** | Weekly rolls = $0, but bi-weekly rolls still generate credit |
| **DROWNING** | ALL rolls (weekly, bi-weekly, monthly) require a debit |

---

**Document History:**
- v1.0 (Feb 3, 2026): Initial framework with 10% ITM rule
- v2.0 (Feb 3, 2026): Updated after Robinhood validation
- v3.0 (Feb 3, 2026): Complete rewrite with TIME TRAPPED vs DEEP UNDERWATER categories
- v4.0 (Feb 3, 2026): Added DROWNING category with validated thresholds (HOOD 30%, AVGO 17%)
- v5.0 (Feb 3, 2026): **Critical revision** - Added LIFE SUPPORT category. DROWNING redefined as "ALL rolls = debit" not just "weekly = $0". HOOD at 30% ITM is LIFE SUPPORT (bi-weekly = $0.30 credit), not DROWNING.
