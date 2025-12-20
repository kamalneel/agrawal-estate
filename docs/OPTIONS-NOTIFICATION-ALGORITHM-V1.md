# Options Notification & Recommendation Algorithm (V1)

**Version:** V1 - Initial Algorithm  
**Status:** ⚠️ DEPRECATED - See [V2](./OPTIONS-NOTIFICATION-ALGORITHM-V2.md)  
**Last Updated:** December 18, 2024

> **Note:** This document is preserved for historical reference. The active algorithm is [V2](./OPTIONS-NOTIFICATION-ALGORITHM-V2.md) which includes lower profit thresholds, preemptive rolls, multi-week analysis, liquidity checks, execution guidance, dividend tracking, and performance analytics.

**Related Documentation:**
- [Notifications & Scheduler](./NOTIFICATIONS.md) - Setup guide for Telegram, scheduling, and testing
- [Options Strategies](./OPTIONS_STRATEGIES.md) - Educational guide on options selling, delta, and strategy roadmap

---

## 1. System Overview

This system monitors sold options positions and generates actionable notifications for:
1. **Rolling options** (extend to next expiration)
2. **Closing positions** (lock in profits)
3. **Selling new covered calls** (generate income)
4. **Earnings alerts** (risk management)

### Data Sources
- **Positions**: Sold options from database (`sold_options` table)
- **Holdings**: Stock holdings from database (`investment_holdings` table)
- **Market Data**: Yahoo Finance API (stock prices, option chains)
- **Technical Analysis**: Calculated from price history

---

## 2. Strategy Types

### 2.1 Roll Options Strategy (`roll_options.py`)

Handles three distinct scenarios:

#### Scenario A: Early Roll (Profit Target Hit)
**Trigger Conditions**:
- Option has captured ≥80% of original premium
- NOT in the money

**Logic**:
```
profit_percent = (original_premium - current_premium) / original_premium
if profit_percent >= 0.80:
    → Generate "Early Roll" recommendation
```

**Cost Sensitivity**:
```python
net_cost = buy_back_cost - new_premium

# Skip if debit is bad deal:
if net_cost > 0:  # It's a debit
    if net_cost > remaining_premium:
        SKIP  # Costs more than letting it expire
    if net_cost > (new_premium * 0.5):
        SKIP  # Debit > 50% of new premium = bad deal
```

**Roll Target**: Next Friday after current expiration (NOT next Friday from today)
```python
def _get_friday_after(reference_date):
    days_ahead = 4 - reference_date.weekday()  # Friday = 4
    if days_ahead <= 0:
        days_ahead += 7
    return reference_date + timedelta(days=days_ahead)
```

---

#### Scenario B: End-of-Week Roll (Time-Based)
**Trigger Conditions**:
- Today is Thursday or Friday
- Option expires THIS Friday
- NOT in the money
- Less than 80% profit captured

**Rationale**: Avoid weekend gap risk. Even with partial profit, rolling collects new premium and avoids 2-day price gap.

**Cost Sensitivity**:
```python
# More lenient than early roll (avoiding gap has value)
if net_cost > new_premium:
    SKIP  # Only skip if debit exceeds new premium entirely
```

---

#### Scenario C: In The Money (ITM) Roll
**Trigger Conditions**:
- Current stock price is beyond strike price
- ITM percentage ≥ 1%

**ITM Calculation**:
```python
# For CALLS:
is_itm = current_price > strike_price
itm_pct = (current_price - strike_price) / strike_price * 100

# For PUTS:
is_itm = current_price < strike_price
itm_pct = (strike_price - current_price) / strike_price * 100
```

**Decision Flow**:
```
1. Check Technical Analysis:
   - Is stock showing reversal signals?
   - RSI overbought/oversold?
   - At support/resistance?

2. If reversal likely AND NOT earnings week:
   → Generate "WATCH" recommendation (wait before rolling)

3. If NOT reversal OR earnings week:
   → Use ITM Roll Optimizer
   → Present 3 options: Conservative, Moderate, Aggressive
```

**ITM Roll Optimizer Logic**:
- Scans multiple expirations (1-6 weeks out)
- Scans multiple strikes (at-the-money to 10% OTM)
- For each combination, calculates:
  - Net cost/credit
  - Probability of staying OTM
  - Delta
  - Annualized return if successful

**Scoring Formula**:
```python
score = (
    cost_score * 0.35 +      # Lower cost = better
    prob_score * 0.35 +      # Higher prob OTM = better
    time_score * 0.20 +      # Shorter duration = better
    return_score * 0.10      # Higher potential return = better
)
```

**Category Selection**:
- **Conservative**: Highest probability OTM (>80%), may have higher cost
- **Moderate**: Balanced cost and probability (recommended default)
- **Aggressive**: Lowest cost (credit preferred), accepts lower probability

---

### 2.2 Early Roll Opportunity Strategy (`early_roll_opportunity.py`)

**Purpose**: Proactive alerts when positions reach profit threshold.

**Trigger Conditions**:
- Normal: 80% profit captured
- Earnings Week: 60% profit captured (more conservative)

**Earnings Awareness**:
```python
NORMAL_PROFIT_THRESHOLD = 0.80
EARNINGS_WEEK_PROFIT_THRESHOLD = 0.60

if symbol has earnings within 5 trading days:
    profit_threshold = 0.60
else:
    profit_threshold = 0.80
```

**Strike Selection**: Uses Technical Analysis to find Delta 10 strike (90% probability OTM)
```python
strike_recommendation = ta_service.recommend_strike_price(
    symbol=symbol,
    option_type=option_type,
    expiration_weeks=1,
    probability_target=0.90  # Delta 10
)
```

---

### 2.3 Sell Unsold Contracts Strategy (`sell_unsold_contracts.py`)

**Purpose**: Identify shares that could be generating covered call income.

**Logic**:
```python
# For each holding with 100+ shares:
options_possible = shares // 100
options_sold = count from sold_options table
unsold = options_possible - options_sold

if unsold > 0:
    → Generate "Sell Covered Call" recommendation
```

**Strike Selection**: Delta 10 (90% probability OTM)

**Income Estimation**:
```python
weekly_income = unsold_contracts * estimated_premium_per_contract
yearly_income = weekly_income * 50  # 50 weeks
```

---

### 2.4 New Covered Call Strategy (`new_covered_call.py`)

**Purpose**: After closing a profitable option, determine whether to sell new call immediately or wait.

**Decision Logic**:
```python
should_wait, reason, analysis = ta_service.should_wait_to_sell(symbol)

# WAIT if:
# - RSI < 30 (oversold, likely bounce)
# - Price at/below lower Bollinger Band
# - Price at strong support level

# SELL NOW if:
# - RSI > 70 (overbought, correcting)
# - Price was at upper Bollinger Band
# - Downtrend in progress (safe to sell calls)
```

---

### 2.5 Earnings Alert Strategy (`earnings_alert.py`)

**Purpose**: Proactive heads-up about positions with upcoming earnings.

**Trigger Conditions**:
- Earnings within 5 trading days

**Alert Priority Based on Position State**:
```python
if is_itm:
    action = "Roll before earnings"
    priority = "urgent"
elif profit_percent >= 50:
    action = "Consider closing to lock in profit"
    priority = "high"
else:
    action = "Monitor - earnings may cause gap"
    priority = "medium"
```

**Extra Urgency**:
```python
if days_to_earnings == 0:
    urgency = "TODAY"
    priority = "urgent"
elif days_to_earnings == 1:
    urgency = "TOMORROW"
```

---

## 3. Technical Analysis

### 3.1 Indicators Calculated

| Indicator | Description | Usage |
|-----------|-------------|-------|
| RSI (14-period) | Relative Strength Index | Overbought (>70) / Oversold (<30) |
| Bollinger Bands | 20-period, 2 std dev | Position relative to bands |
| Weekly Volatility | 5-day historical volatility | Probability ranges, strike selection |
| Support Levels | Historical price floors | Wait-to-sell decisions |
| Resistance Levels | Historical price ceilings | Strike selection |
| 50-day MA | Moving average | Trend direction |
| 200-day MA | Moving average | Long-term trend |
| Earnings Date | Next earnings announcement | Earnings awareness |

### 3.2 Probability Ranges

Based on weekly volatility, we calculate price ranges:
```python
# 1 standard deviation (~68% probability)
prob_68_low = current_price * (1 - weekly_volatility)
prob_68_high = current_price * (1 + weekly_volatility)

# 1.65 standard deviation (~90% probability) - Used for Delta 10
prob_90_low = current_price * (1 - weekly_volatility * 1.65)
prob_90_high = current_price * (1 + weekly_volatility * 1.65)
```

### 3.3 Strike Recommendation Logic

```python
def recommend_strike_price(symbol, option_type, expiration_weeks, probability_target):
    """
    Recommend strike price based on probability target.
    
    probability_target = 0.90 means Delta 10 (90% chance of staying OTM)
    """
    
    # Method 1: Use actual options chain delta (preferred)
    chain = get_option_chain(symbol, expiration)
    for strike in chain:
        if abs(strike.delta) <= 0.10:  # Delta 10
            return strike.strike_price
    
    # Method 2: Fallback to volatility-based estimate
    z_score = norm.ppf(probability_target)  # 1.65 for 90%
    if option_type == "call":
        strike = current_price * (1 + weekly_volatility * z_score * sqrt(weeks))
    else:  # put
        strike = current_price * (1 - weekly_volatility * z_score * sqrt(weeks))
    
    return round_to_nearest_strike(strike)
```

---

## 4. Deduplication Logic

**Problem**: Multiple strategies may generate same recommendation.

**Solution**: Unique constraint on `recommendation_id` + INSERT ON CONFLICT DO NOTHING

```python
# Recommendation ID format:
id = f"{strategy}_{symbol}_{strike}_{date}_{account_slug}"

# Example:
"roll_early_AAPL_180.0_2024-12-18_Neels_Brokerage"

# Database insert:
stmt = insert(StrategyRecommendationRecord).values(**values)
stmt = stmt.on_conflict_do_nothing(index_elements=['recommendation_id'])
```

---

## 5. Priority Levels

| Priority | Criteria |
|----------|----------|
| **urgent** | ITM ≥5%, Earnings TODAY/TOMORROW, Expires today |
| **high** | ITM 1-5%, >80% profit captured, Sell opportunity >$5000/year |
| **medium** | End-of-week roll, Wait recommendations, Moderate income |
| **low** | Small positions, Wait for bounce |

---

## 6. Notification Content

### Title Format Examples:
```
# Early Roll:
"ROLL AAPL $180→$185 call ($0.15 credit)"

# End-of-Week Roll:
"ROLL AAPL $180→$185 (Friday, $0.10 credit)"

# ITM Roll:
"ROLL ITM AAPL $180→$185 (2wk, $0.50 debit) · Stock $190"

# Earnings Alert:
"📊 EARNINGS in 2 days: AAPL $180 call (3% OTM) · Stock $175"

# Sell New:
"Sell 3 AAPL call(s) at $185 for Dec 20 · Stock $175"
```

### Description Format:
```
# Roll:
"Roll AAPL $180 call Dec 13 → Dec 20 $185 - $0.15 credit/share (85% profit captured)"

# Sell:
"You have 3 unsold contracts for AAPL that could generate $150/week in income."
```

---

## 7. Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `profit_threshold_early` | 80% | Profit % to trigger early roll |
| `earnings_week_profit_threshold` | 60% | Profit % during earnings week |
| `itm_threshold_percent` | 1.0% | ITM % to trigger ITM roll analysis |
| `days_before_earnings` | 5 | Days before earnings to alert |
| `min_weekly_income` | $50 | Minimum to recommend selling |

---

## 8. Key Formulas

### Net Cost of Roll:
```python
net_cost = buy_back_cost - new_premium
# Negative = Credit (good)
# Positive = Debit (costs money)
```

### Profit Percentage:
```python
profit_percent = (original_premium - current_premium) / original_premium
```

### ITM Percentage:
```python
# Call:
itm_pct = (current_price - strike) / strike * 100

# Put:
itm_pct = (strike - current_price) / strike * 100
```

### OTM Percentage:
```python
# Call:
otm_pct = (strike - current_price) / current_price * 100

# Put:
otm_pct = (current_price - strike) / current_price * 100
```

---

## 9. Known Limitations

1. **API Rate Limiting**: Yahoo Finance may return 429 errors during high-frequency calls
2. **Options Chain Availability**: Not all expirations may have liquid options
3. **Estimated Premiums**: When market data unavailable, premiums are estimated
4. **Market Hours**: Data is cached differently during market hours vs off-hours

---

## 10. Questions for Review

1. Is the 80%/60% profit threshold appropriate for early rolls?
2. Is Delta 10 (90% probability OTM) the right target for strike selection?
3. Should the cost sensitivity thresholds be adjusted?
4. Is the ITM roll optimizer weighting correct (35% cost, 35% probability, 20% time, 10% return)?
5. Are there other scenarios we should be handling?

---

## Appendix A: File Locations

| File | Purpose |
|------|---------|
| `backend/app/modules/strategies/strategies/roll_options.py` | Main roll logic |
| `backend/app/modules/strategies/strategies/early_roll_opportunity.py` | Early roll alerts |
| `backend/app/modules/strategies/strategies/sell_unsold_contracts.py` | Sell unsold calls |
| `backend/app/modules/strategies/strategies/new_covered_call.py` | New call decisions |
| `backend/app/modules/strategies/strategies/earnings_alert.py` | Earnings alerts |
| `backend/app/modules/strategies/technical_analysis.py` | TA calculations |
| `backend/app/modules/strategies/itm_roll_optimizer.py` | ITM roll optimization |
| `backend/app/modules/strategies/recommendations.py` | Save to database |
| `backend/app/shared/services/notifications.py` | Telegram formatting |

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| V1 | Dec 2024 | Initial algorithm with roll, early roll, sell unsold, new call, earnings strategies |

