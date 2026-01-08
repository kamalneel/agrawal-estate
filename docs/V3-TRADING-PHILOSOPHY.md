# V3 Trading Philosophy

**Version:** 3.3  
**Created:** December 21, 2024  
**Updated:** January 7, 2026  
**Status:** ✅ ACTIVE

---

## Executive Summary

This document defines the **WHY** behind our options trading decisions. It captures the core philosophy, key principles, and decision priorities that guide the recommendation engine.

**Related Documents:**
- [RECOMMENDATION-ENGINE.md](./RECOMMENDATION-ENGINE.md) - How we implement these decisions
- [NOTIFICATION-SYSTEM.md](./NOTIFICATION-SYSTEM.md) - How we communicate decisions to the user

---

## Core Philosophy

> **"Generate weekly income from covered calls/puts while managing risk through patience and mean reversion awareness."**

### The Weekly Income Cycle

The goal is to earn premium **every week**, not occasionally. This means:

1. **Prefer weekly expirations** over monthly when possible
2. **Compress time** rather than extend when rolling
3. **Don't waste weeks** sitting in positions that don't earn

### Mean Reversion Awareness

Stocks oscillate around their mean. Our strategy:

1. **When stock spikes up** → It will likely pull back → Don't panic-roll to far dates
2. **When stock drops** → It will likely bounce → Wait to sell calls at better prices
3. **Use shorter time windows** to capture these cycles (45-90 days optimal)

---

## Key Principles

### Principle 1: Compress Over Extend

When rolling a position, **shorter duration is preferred** over longer duration.

| Scenario | Bad Choice | Good Choice |
|----------|-----------|-------------|
| Slightly ITM, profitable | Extend to next month | Compress to this week |
| Far-dated ITM | Keep 8-month position | Compress to 2-3 months |
| OTM with profit | Wait for expiry | Pull back to this week |

**Why:** Each week you extend = one week of income lost. At $50-100/contract/week, this compounds to significant opportunity cost.

### Principle 2: Don't Panic on ITM

Being in-the-money is not an emergency (unless expiration is imminent).

| ITM Situation | Time to Expiry | Response |
|---------------|----------------|----------|
| Any ITM | > 60 days | **Patience** - Try to compress, else monitor |
| Slight ITM (<5%) | ≤ 60 days | **Evaluate** - Compress if profitable, else escape |
| Deep ITM (>10%) | ≤ 14 days | **Urgent** - Escape now with flexible debit |

**Why:** Most ITM positions resolve naturally through mean reversion. Paying large debits to escape immediately often costs more than waiting.

### Principle 3: Use Technical Analysis for Entry

When selling new options on uncovered shares, use TA to time entry:

| RSI | Bollinger Position | Action | Rationale |
|-----|-------------------|--------|-----------|
| < 30 | Near lower band | **WAIT** | Stock oversold, likely bounce |
| > 70 | Near upper band | **SELL NOW** | Stock overbought, good premium |
| 30-70 | Middle | **SELL NOW** | Neutral, start earning |

**Why:** Selling calls when a stock is at its bottom means lower strikes and lower premiums. Wait for better entry.

### Principle 4: Accept Small Debits for Mean Reversion

When escaping ITM, it's acceptable to pay a small debit if:
- The new position is positioned for mean reversion
- The time saved is significant

| ITM Severity | Max Acceptable Debit |
|--------------|---------------------|
| Slight (1-5%) | $2.00 |
| Moderate (5-10%) | $3.00 |
| Deep (>10%) | $5.00 |

**Why:** A $4 debit to roll from a losing position to a winning position over 2-3 months is often worthwhile.

---

## Decision Priority Order

When evaluating a position, apply these checks in order:

```
1. PULL-BACK (Highest Priority)
   └─ Can we return to shorter duration profitably?
   └─ Goal: Get back to weekly income cycle
   
2. WEEKLY INCOME COMPRESS
   └─ If slightly ITM + profitable
   └─ Compress even if staying ITM
   └─ Preserve weekly cycle over escaping ITM
   
3. ITM HANDLING
   ├─ Far-dated (>60 days): Try COMPRESS, else MONITOR
   └─ Near-dated (≤60 days): ESCAPE with flexible debit
   
4. NEAR-ITM WARNING
   └─ Within 2% of strike + expiring soon
   └─ Alert user to potential assignment
   
5. PROFITABLE ROLL
   └─ OTM with ≥60% profit captured
   └─ Roll to capture and restart cycle
   
6. NO ACTION
   └─ Position is fine, let it ride
```

---

## Risk Tolerance Parameters

### Time Preferences

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Ideal expiration | 1-2 weeks | Weekly income |
| Max comfortable extension | 4-6 weeks | Still manageable |
| Far-dated threshold | 60+ days | Mean reversion territory |
| Max scan horizon | 6 months | Don't look further |

### Cost Preferences

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Pull-back max debit | 20% of original premium | Must be worthwhile |
| ITM escape max debit | $2-$5 (severity-based) | Flexible for urgency |
| Compress max debit | $1 (same strike) / $5 (OTM) | Cost-neutral preferred |

### Strike Preferences

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Target delta | 0.30 (30% ITM probability) | Balance risk/reward |
| Near-ITM warning | Within 2% of strike | Early warning |
| Urgent near-ITM | Within 1% of strike | Immediate action |

---

## Examples with Rationale

### Example 1: Weekly Income Priority

**Position:** AVGO $350 Put Jan 23, Stock $346 (1.1% ITM), 79% profit

**Philosophy Applied:**
- Principle 1 (Compress over Extend): Don't extend to Jan 30
- Principle 2 (Don't Panic): 1.1% ITM is slight, not urgent
- Decision: **Compress to Jan 16 at $340** (+$5.65 credit)

**Result:** Preserved weekly income, earned credit, shorter duration.

### Example 2: Mean Reversion Patience

**Position:** TSLA $370 Call Sep 18, Stock $435 (17% ITM), 254 days out

**Philosophy Applied:**
- Principle 2 (Don't Panic): 254 days is far, no urgency
- Mean Reversion: TSLA spiked, likely to pull back
- Decision: **MONITOR** - wait for pullback opportunity

**Result:** No unnecessary debit paid, position monitored for compress opportunity.

### Example 3: Flexible Debit Escape

**Position:** MU $295 Call Jan 16, Stock $340 (15% ITM), 9 days out

**Philosophy Applied:**
- Principle 2: Near expiry + deep ITM = urgent
- Principle 4: Deep ITM (15%) allows up to $5 debit
- Decision: **Roll to $340 March at $4.20 debit**

**Result:** Escaped assignment, positioned for mean reversion over 10 weeks.

### Example 4: TA-Guided Entry

**Position:** NFLX, 5 uncovered contracts, RSI = 26.7

**Philosophy Applied:**
- Principle 3: RSI < 30 = oversold
- Mean Reversion: Stock will likely bounce
- Decision: **WAIT** - don't sell at bottom

**Result:** Avoided selling at low premium, will get better entry after bounce.

---

## Anti-Patterns (What NOT to Do)

### ❌ Panic Rolling

**Bad:** "Stock went ITM, roll out 6 months immediately!"
**Why Bad:** Pays large debit, loses 5 months of income opportunity
**Better:** Wait for mean reversion, compress if possible

### ❌ Chasing Delta

**Bad:** "Always roll to 30-delta, even if it means extending"
**Why Bad:** Prioritizes delta over time, loses weekly income
**Better:** Accept higher delta for shorter duration

### ❌ Ignoring Technical Signals

**Bad:** "Stock is oversold but sell calls anyway to start earning"
**Why Bad:** Locks in low strike, misses bounce
**Better:** Wait for RSI recovery, sell at better premium

### ❌ Extending Instead of Compressing

**Bad:** "Roll Jan 23 to Jan 30 for credit"
**Why Bad:** Gives away one week of income
**Better:** "Roll Jan 23 to Jan 16 for credit" (compress)

---

## Configuration Reference

```python
TRADING_PHILOSOPHY_CONFIG = {
    # === TIME PREFERENCES ===
    "ideal_expiration_weeks": 1,
    "max_extension_weeks": 6,
    "far_dated_threshold_days": 60,
    "max_scan_months": 6,
    
    # === COST PREFERENCES ===
    "pull_back_max_debit_pct": 0.20,
    "itm_escape_debit_limits": {
        "slight": 2.0,    # 1-5% ITM
        "moderate": 3.0,  # 5-10% ITM
        "deep": 5.0,      # >10% ITM
    },
    "compress_same_strike_max_debit": 1.0,
    "compress_otm_escape_max_debit": 5.0,
    
    # === STRIKE PREFERENCES ===
    "target_delta": 0.30,
    "near_itm_warning_pct": 2.0,
    "urgent_near_itm_pct": 1.0,
    
    # === TA THRESHOLDS ===
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "bollinger_buffer_pct": 2.0,
    
    # === WEEKLY INCOME PRIORITY ===
    "prefer_compress_when": {
        "max_itm_pct": 5.0,
        "min_profit_pct": 0.60,
    },
}
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 3.0 | Dec 21, 2024 | Initial V3 philosophy |
| 3.1 | Dec 28, 2024 | Added WAIT recommendations |
| 3.2 | Jan 5, 2026 | Schwab as primary data source |
| 3.3 | Jan 7, 2026 | Weekly income priority, mean reversion awareness |

---

**END OF V3 TRADING PHILOSOPHY**

