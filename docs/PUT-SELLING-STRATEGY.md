# Cash-Secured Put Selling Strategy (V3.4)

**Version:** 3.4  
**Status:** 🚧 IMPLEMENTING  
**Created:** January 9, 2026  
**Philosophy:** Utilize idle cash to generate income through put selling on stocks you're willing to own

---

## Overview

This strategy recommends selling cash-secured puts on stocks in your portfolio when:
1. Technical conditions are favorable (stock is oversold/at support)
2. Premium is attractive relative to capital requirement
3. You have available cash and are willing to own more of the stock

---

## Core Philosophy

### Why Sell Puts?

1. **Generate Income**: Collect premium from time decay
2. **Buy Lower**: If assigned, you acquire stock at a discount (strike - premium)
3. **Mean Reversion Bet**: Sell when stock is beaten down, likely to recover
4. **Capital Efficiency**: Put idle cash to work

### When to Sell Puts (V3.4 Logic)

| Condition | Favorable | Neutral | Unfavorable |
|-----------|-----------|---------|-------------|
| RSI | < 40 (oversold) | 40-60 | > 70 (overbought) |
| Bollinger Band | < 35% (lower half) | 35-65% | > 80% (upper half) |
| Recent Movement | Down 5%+ | Flat | Up 10%+ |

**Key Insight**: Sell puts when stocks are BEATEN DOWN, not when they're flying high.

---

## Scoring Methodology

### TA Score (Base: 50 points)

```
RSI Factor:
  RSI < 30  (oversold):       +30 points
  RSI 30-40 (near oversold):  +20 points
  RSI 40-50 (neutral-bull):   +10 points
  RSI 50-60 (neutral):         +0 points
  RSI 60-70 (getting hot):    -10 points
  RSI > 70  (overbought):     -20 points

Bollinger Band Factor:
  BB < 20%  (at support):     +30 points
  BB 20-35% (lower half):     +20 points
  BB 35-50% (below middle):   +10 points
  BB 50-65% (at middle):       +0 points
  BB 65-80% (upper half):     -10 points
  BB > 80%  (at resistance):  -20 points
```

### Premium Score (Bonus up to 30 points)

```
Premium Score = min(ROI% × 100, 30)

Where: ROI% = (Premium per Contract) / (Strike × 100)
```

### Combined Score

```
Combined Score = TA Score + Premium Score

Grades:
  A+ = Score ≥ 90  → STRONG RECOMMEND
  A  = Score ≥ 80  → RECOMMEND  
  B+ = Score ≥ 70  → CONSIDER
  B  = Score ≥ 60  → NEUTRAL
  C  = Score ≥ 50  → CAUTION
  D  = Score < 50  → AVOID
```

---

## Target Selection

### Delta Target: ~0.10 (10 Delta)

- **90% probability** of expiring out-of-the-money
- Typically **8-12% below current price**
- Balance between premium and safety

### Expiration: Weekly Preferred

- **Maximum time decay** (theta)
- Quick capital recycling
- Can adjust weekly based on conditions

### Strike Selection Logic

```python
# Find the put option closest to 10 delta
for option in put_chain:
    if 0.08 <= abs(option.delta) <= 0.15:
        # Prefer the one closest to 0.10
        select_if_closest_to_target(option)

# Fallback: Find strike ~8-10% below current price
if no_10_delta_found:
    target_strike = current_price * 0.92
    select_highest_strike_below(target_strike)
```

---

## Recommendation Triggers

### Minimum Thresholds

| Criteria | Minimum for Recommendation |
|----------|---------------------------|
| Combined Score | ≥ 80 (Grade A) |
| Premium per Contract | ≥ $30 |
| Probability of Profit | ≥ 85% |
| Capital Utilization | ≤ 50% of available cash per position |

### Position Sizing

```
Max contracts per symbol = floor(available_cash * 0.20 / (strike × 100))
```

- Never commit more than 20% of available cash to a single put
- Diversify across 3-5 positions

---

## Integration with Holdings

### Include ALL Portfolio Stocks

The strategy considers puts on **any stock you currently hold**, even if just 1 share:

```sql
SELECT DISTINCT symbol 
FROM investment_holdings 
WHERE quantity > 0
  AND symbol NOT IN ('FDRXX', 'SPAXX', 'VMFXX')  -- Exclude money markets
  AND symbol NOT LIKE '%X'  -- Exclude most funds
```

**Rationale**: If you own it, you believe in it. Selling puts is just buying more at a discount.

---

## Notification Format

### Telegram Message

```
📊 PUT SELLING OPPORTUNITIES

🎯 TSLA - Grade A+ (Score: 120)
   📈 Stock: $447.43
   📝 Sell $418 Put @ $1.25 = $125/contract
   💰 ROI: 0.30% | Capital: $41,750
   🎯 Win Rate: ~90%
   📊 RSI 34 (near oversold) | BB 31% (lower half)

🎯 AAPL - Grade A+ (Score: 125)
   📈 Stock: $259.57
   📝 Sell $248 Put @ $0.36 = $36/contract
   💰 ROI: 0.15% | Capital: $24,750
   🎯 Win Rate: ~92%
   📊 RSI 23 (OVERSOLD) | BB 1% (at support)

⚠️ AVOID: MU (RSI 80 overbought), RKLB (RSI 77)
```

### Web UI Card

```
┌─────────────────────────────────────────────────┐
│ 💵 SELL PUT: TSLA                    Grade: A+  │
├─────────────────────────────────────────────────┤
│ Sell $418 Put expiring Jan 16                   │
│ Premium: $125/contract · ROI: 0.30%             │
│                                                 │
│ 📊 Technical Snapshot:                          │
│   Current: $447.43 | Strike: $418 (6.6% OTM)    │
│   RSI: 34 (near oversold) 🟢                    │
│   Bollinger: 31% (lower half) 🟢                │
│                                                 │
│ 💭 Why This Recommendation:                     │
│   TSLA is trading near the lower Bollinger Band │
│   with RSI showing near-oversold conditions.    │
│   This suggests limited downside and high       │
│   probability of the put expiring worthless.    │
│                                                 │
│ [Sell This Put] [Skip] [Remind Me Tomorrow]     │
└─────────────────────────────────────────────────┘
```

---

## RLHF Data Capture

### Automatic Tracking (Implicit Feedback)

When a put recommendation is generated:
```json
{
  "symbol": "TSLA",
  "recommendation_date": "2026-01-09",
  "score": 120,
  "grade": "A+",
  "strike": 418,
  "expiration": "2026-01-16",
  "bid_price": 1.25,
  "delta": -0.10,
  "rsi": 34,
  "bb_position": 31,
  "status": "recommended"
}
```

When user acts:
```json
{
  "action_taken": "sold",
  "action_date": "2026-01-09",
  "contracts_sold": 1,
  "premium_received": 125.00
}
```

At expiration:
```json
{
  "outcome": "expired_otm",
  "final_pnl": 125.00,
  "was_prediction_correct": true
}
```

### Explicit Feedback (User Input)

After skipping a recommendation:
- [ ] Premium too low
- [ ] Capital requirement too high  
- [ ] Don't like this stock for puts
- [ ] TA didn't convince me
- [ ] Already have enough exposure
- [ ] Other: [free text]

---

## Learning Adjustments

### After 30+ Trades

1. **Success Rate by RSI Band**
   ```
   RSI < 30: 98% success → Increase weight to +35
   RSI 30-40: 94% success → Keep at +20
   RSI > 70: 72% success → Decrease to -25
   ```

2. **Symbol Preferences**
   ```
   User trades TSLA puts frequently → Boost TSLA recommendations
   User ignores MSTR → Reduce MSTR priority
   ```

3. **Premium Threshold**
   ```
   User never acts on < $50 premium → Filter those out
   ```

---

## Risk Management

### Hard Limits

| Risk Control | Limit |
|--------------|-------|
| Max % of cash in puts | 50% |
| Max % per single symbol | 20% |
| Avoid earnings week | Yes |
| Min days to expiration | 5 |
| Max delta | -0.20 |

### Automatic Avoidance

- **Earnings within 5 days**: Skip (IV crush risk)
- **Ex-dividend within 3 days**: Flag for early assignment risk
- **Major Fed announcement**: Reduce exposure

---

## Implementation Checklist

- [ ] Create `CashSecuredPutStrategy` class
- [ ] Add to `strategy_service.py` non-position strategies
- [ ] Create `put_opportunities` database table
- [ ] Add scoring logic with TA integration
- [ ] Create notification templates (Telegram + Web)
- [ ] Add to V2 recommendation flow
- [ ] Implement RLHF data capture
- [ ] Add explicit feedback UI
- [ ] Create learning/adjustment algorithm

---

## Related Documentation

- [V3 Trading Philosophy](./V3-TRADING-PHILOSOPHY.md)
- [Recommendation Engine](./RECOMMENDATION-ENGINE.md)
- [Technical Analysis Integration](./OPTIONS-NOTIFICATION-ALGORITHM-V3.md#technical-analysis)
- [RLHF Framework](./RLHF/LEARNING-FRAMEWORK.md) (future)

