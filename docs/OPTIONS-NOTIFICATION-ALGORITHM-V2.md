# Options Notification & Recommendation Algorithm (V2)

**Version:** V2.2 - Enhanced Algorithm  
**Status:** Active  
**Last Updated:** December 19, 2024

**Changes from V1:**
- Lowered profit thresholds (80% → 60%)
- Removed end-of-week auto-roll logic
- Added preemptive roll strategy for approaching strikes
- Added multi-week expiration analysis
- Added strategic timing optimization (IV-based)
- Enhanced cost sensitivity evaluation
- Added liquidity and execution quality checks
- Added execution guidance system
- Added dividend/ex-dividend tracking
- Added performance tracking and analytics
- **NEW:** Added Triple Witching Day special handling with comprehensive execution guidance
- **V2.1:** Fixed ITM/OTM status display (shows actual ITM% with intrinsic value)
- **V2.1:** Fixed ITM PUT roll strike selection (now rolls DOWN properly)
- **V2.1:** Fixed roll cost validation (ensures buy_back_cost >= intrinsic value)
- **V2.1:** Improved UX (hides roll options when CLOSE_DONT_ROLL recommended)
- **V2.2:** Added ITM threshold enforcement (20%/10%/5%/3% thresholds for CLOSE vs ROLL)
- **V2.2:** Added economic sanity checks (savings must be $50+ or 10%+)
- **V2.2:** Added roll options validation (catches identical strikes)
- **V2.2:** Prevents rolling INTO another ITM position

**Related Documentation:**
- [V1 Algorithm](./OPTIONS-NOTIFICATION-ALGORITHM-V1.md) - Original algorithm (deprecated)
- [Notifications & Scheduler](./NOTIFICATIONS.md) - Setup guide for Telegram, scheduling, and testing
- [Options Strategies](./OPTIONS_STRATEGIES.md) - Educational guide on options selling, delta, and strategy roadmap

---

## 1. System Overview

This system monitors sold options positions and generates actionable notifications for:
1. **Rolling options** (extend to next expiration)
2. **Closing positions** (lock in profits)
3. **Selling new covered calls** (generate income)
4. **Earnings alerts** (risk management)
5. **Dividend alerts** (assignment risk management)
6. **Execution guidance** (optimize fills)
7. **Triple Witching alerts** (quarterly expiration chaos management)

### Data Sources
- **Positions**: Sold options from database (`sold_options` table)
- **Holdings**: Stock holdings from database (`investment_holdings` table)
- **Market Data**: Yahoo Finance API (stock prices, option chains, liquidity metrics)
- **Technical Analysis**: Calculated from price history
- **Corporate Actions**: Dividend dates and amounts
- **Performance Metrics**: Historical recommendation outcomes

---

## 2. Strategy Types

### 2.1 Roll Options Strategy (`roll_options.py`)

Handles four distinct scenarios:

#### Scenario A: Early Roll (Profit Target Hit)
**Trigger Conditions**:
- Option has captured ≥60% of original premium (UPDATED from 80%)
- NOT in the money

**Logic**:
```python
profit_percent = (original_premium - current_premium) / original_premium
if profit_percent >= 0.60:  # UPDATED from 0.80
    → Generate "Early Roll" recommendation
```

**Cost Sensitivity** (ENHANCED):
```python
net_cost = buy_back_cost - new_premium

# Evaluate three scenarios
scenarios = {
    'roll_now': evaluate_roll_now(),
    'wait_expire': evaluate_wait_to_expire(),
    'wait_partial': evaluate_wait_partial()
}

best_scenario = max(scenarios, key=scenarios.get)

# Only recommend roll if within 10% of best scenario
if best_scenario == 'roll_now' or scenarios['roll_now'] >= scenarios[best_scenario] * 0.90:
    → Generate recommendation
else:
    → Suggest waiting with explanation
```

**Enhanced Cost Rules**:
```python
# Standard threshold
if net_cost > 0:  # It's a debit
    if net_cost > remaining_premium:
        SKIP  # Costs more than letting it expire
    if net_cost > (new_premium * 0.50):
        SKIP  # Debit > 50% of new premium = bad deal

# Earnings exception (more lenient)
if earnings_within(5_days):
    if net_cost < (new_premium * 0.75):
        ACCEPT  # Derisking has value

# High profit exception
if profit_percent >= 0.80:  # Already captured 80%+
    if net_cost < (original_premium * 0.15):
        ACCEPT  # Don't be greedy

# Expiring soon exception
if days_to_expiration <= 1:
    if net_cost < new_premium:
        ACCEPT  # Just move to next week
```

**Roll Target** (ENHANCED - Multi-Week Analysis):
```python
def find_optimal_roll_expiration(symbol, current_expiration, strike, option_type):
    """
    Scan 1-3 week expirations and choose optimal based on:
    - Total credit/debit
    - Weekly return rate
    - Time efficiency
    """
    
    max_weeks = 3  # Configurable
    
    # Get premiums for each duration
    expirations = []
    for weeks in range(1, max_weeks + 1):
        exp_date = get_friday_after(current_expiration, weeks)
        premium = get_premium_estimate(symbol, strike, exp_date, option_type)
        expirations.append({
            'weeks': weeks,
            'date': exp_date,
            'premium': premium,
            'net_credit': premium - buy_back_cost
        })
    
    # Calculate scores
    for exp in expirations:
        weekly_return = exp['net_credit'] / exp['weeks']
        
        # Scoring weights
        credit_score = exp['net_credit'] / exp['premium']
        weekly_score = weekly_return / exp['premium']
        time_score = 1 / exp['weeks']
        
        exp['score'] = (
            credit_score * 0.40 +
            weekly_score * 0.30 +
            time_score * 0.30
        )
    
    # Check marginal benefit
    best_weeks = 1
    for exp in expirations[1:]:  # Skip 1-week (baseline)
        prev_exp = expirations[exp['weeks'] - 2]
        marginal_premium = exp['premium'] - prev_exp['premium']
        
        if marginal_premium >= 0.15:  # Still adding $0.15+ value
            if exp['score'] > expirations[best_weeks - 1]['score']:
                best_weeks = exp['weeks']
    
    return expirations[best_weeks - 1]
```

**Force 1-week when:**
- Earnings within 2 weeks (don't span earnings)
- Ex-dividend date within 2 weeks (assignment risk)
- User preference set to weekly-only

---

#### Scenario B: End-of-Week Roll ~~(REMOVED)~~
**Status**: DELETED in V2

**Rationale**: This forced rolls just because it was Thursday/Friday, often resulting in bad economics. Better to let options expire and sell fresh on Monday (see Strategic Timing section).

---

#### Scenario C: In The Money (ITM) Roll
**Trigger Conditions** (UNCHANGED):
- Current stock price is beyond strike price
- ITM percentage ≥ 1%

**ITM Calculation** (UNCHANGED):
```python
# For CALLS:
is_itm = current_price > strike_price
itm_pct = (current_price - strike_price) / strike_price * 100

# For PUTS:
is_itm = current_price < strike_price
itm_pct = (strike_price - current_price) / strike_price * 100
```

**Decision Flow** (UNCHANGED):
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

**ITM Roll Optimizer Logic** (ENHANCED with multi-week + V2.1 Fixes):
- Scans multiple expirations (1-3 weeks out for preemptive, 1-6 weeks for deep ITM)
- Scans multiple strikes (at-the-money to 10% OTM)
- For each combination, calculates:
  - Net cost/credit
  - Probability of staying OTM
  - Delta
  - Annualized return if successful

**V2.1 Strike Selection Fixes for ITM Puts**:
```python
# For ITM PUTS: Roll DOWN to get OTM (lower strikes = more OTM)
if option_type.lower() == 'put':
    min_strike = current_price * 0.85  # Down to 15% below current price
    # IMPORTANT: max_strike should be BELOW current price to get OTM
    max_strike = min(current_strike, current_price * 1.02)  # At most 2% above current
    
    # If stock is DEEP below strike (>10% ITM), force rolling to OTM strikes
    itm_amount = (current_strike - current_price) / current_strike
    if itm_amount > 0.10:  # >10% ITM
        max_strike = current_price * 0.98  # Force below current price (OTM territory)
```

**V2.1 Buy-Back Cost Validation**:
```python
# Ensure buy_back_cost is at least intrinsic value
if option_type.lower() == "call":
    intrinsic_value = max(0, current_price - current_strike)
else:  # put
    intrinsic_value = max(0, current_strike - current_price)

# Validate: buy_back_cost should be >= intrinsic value
if current_option_price < intrinsic_value * 0.95:  # Allow 5% tolerance
    # Bad market data - use corrected value
    current_option_price = intrinsic_value + extrinsic_estimate

# For deep ITM, increase max_net_debit proportionally
if itm_pct > 10:
    effective_max_debit = max(max_net_debit, intrinsic_value * 0.5)
```

**Scoring Formula** (UNCHANGED):
```python
score = (
    cost_score * 0.35 +      # Lower cost = better
    prob_score * 0.35 +      # Higher prob OTM = better
    time_score * 0.20 +      # Shorter duration = better
    return_score * 0.10      # Higher potential return = better
)
```

---

#### Scenario D: Preemptive Roll (NEW - Approaching Strike)
**Purpose**: Alert when stock is approaching strike with momentum, before position goes ITM.

**Trigger Conditions**:
```python
# Distance check
distance_pct = abs(current_price - strike_price) / strike_price * 100

# For CALLS:
if option_type == "call":
    approaching = (current_price < strike_price and 
                   distance_pct <= 3.0)  # Within 3% below strike
    
# For PUTS:
elif option_type == "put":
    approaching = (current_price > strike_price and
                   distance_pct <= 3.0)  # Within 3% above strike

# Must have time to act
has_time = days_to_expiration > 2

# Initial trigger
if approaching and has_time:
    → Analyze momentum and technicals
```

**Technical Analysis Requirements**:
```python
# For CALLS - confirm bullish threat:
1. Price trend: Moving UP toward strike (3-day slope positive)
2. No resistance: Strike price NOT near resistance level
3. RSI: > 50 (confirming momentum)
4. Volume: Above average (real move, not noise)

# For PUTS - confirm bearish threat:
1. Price trend: Moving DOWN toward strike
2. No support: Strike price NOT near support level
3. RSI: < 50 (confirming downward momentum)
4. Volume: Above average

# If ALL conditions met:
should_alert = True
```

**Priority Logic**:
```python
if distance_pct <= 1.5:
    priority = "urgent"  # Very close, act soon
    message = "Stock approaching strike - consider preemptive roll"
    
elif distance_pct <= 3.0:
    priority = "high"  # Within range, monitor closely
    message = "Stock trending toward strike - prepare to roll"
```

**Multi-Week Optimization for Preemptive Rolls**:
When executing preemptive rolls, algorithm evaluates 1-3 week options:
```python
# After big move, mean reversion is likely
# Longer expirations give more time for reversion
if stock_moved_sharply(symbol, days=5, threshold=0.05):  # 5%+ move
    max_weeks = 3  # Consider up to 3 weeks
    recommend_weeks = optimize_for_mean_reversion()
else:
    max_weeks = 2  # Standard preemptive roll
```

**Integration with Other Scenarios**:
- If position already ITM → ITM strategy takes precedence
- If position hit 60% profit → Early roll strategy takes precedence
- Otherwise → Approaching strike alert fires

---

### 2.2 Early Roll Opportunity Strategy (`early_roll_opportunity.py`)

**Purpose**: Proactive alerts when positions reach profit threshold.

**Trigger Conditions** (UPDATED):
- Normal: 60% profit captured (UPDATED from 80%)
- Earnings Week: 45% profit captured (UPDATED from 60%)
- Short DTE (<3 days): 35% profit captured (NEW)

**Earnings Awareness**:
```python
NORMAL_PROFIT_THRESHOLD = 0.60           # UPDATED from 0.80
EARNINGS_WEEK_PROFIT_THRESHOLD = 0.45    # UPDATED from 0.60
SHORT_DTE_THRESHOLD = 0.35               # NEW

if symbol has earnings within 5 trading days:
    profit_threshold = 0.45
elif days_to_expiration <= 3:
    profit_threshold = 0.35
else:
    profit_threshold = 0.60
```

**Strike Selection** (UNCHANGED): Uses Technical Analysis to find Delta 10 strike (90% probability OTM)
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

**Logic** (UNCHANGED):
```python
# For each holding with 100+ shares:
options_possible = shares // 100
options_sold = count from sold_options table
unsold = options_possible - options_sold

if unsold > 0:
    → Generate "Sell Covered Call" recommendation
```

**Strike Selection** (UNCHANGED): Delta 10 (90% probability OTM)

**Income Estimation** (UNCHANGED):
```python
weekly_income = unsold_contracts * estimated_premium_per_contract
yearly_income = weekly_income * 50  # 50 weeks
```

---

### 2.4 New Covered Call Strategy (`new_covered_call.py`)

**Purpose**: After closing a profitable option, determine whether to sell new call immediately or wait.

**Decision Logic** (ENHANCED with Strategic Timing):
```python
# Check if we should wait for better timing
timing_check = evaluate_timing_opportunity(symbol)

if timing_check['should_wait']:
    return {
        'action': 'WAIT',
        'reason': timing_check['reason'],
        'sell_when': timing_check['conditions'],
        'estimated_improvement': timing_check['expected_benefit']
    }

# Check technical analysis
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

**Strategic Timing Considerations** (NEW):
```python
def evaluate_timing_opportunity(symbol):
    """
    Determine if waiting 1-3 days could yield better premium.
    """
    
    current_time = datetime.now()
    day_of_week = current_time.strftime('%A')
    time_of_day = current_time.time()
    
    # Case 1: Friday afternoon - wait for Monday
    if day_of_week == 'Friday' and time_of_day > time(14, 0):
        return {
            'should_wait': True,
            'reason': 'Monday IV bump',
            'conditions': 'Monday 10-11am',
            'expected_benefit': '+5-10% premium'
        }
    
    # Case 2: Low VIX environment
    vix = get_vix()
    if vix < 15:
        current_premium = get_weekly_premium(symbol)
        premium_pct = current_premium / get_stock_price(symbol) * 100
        
        if premium_pct < 0.3:  # <0.3% of stock price
            return {
                'should_wait': True,
                'reason': 'Low IV - wait for expansion',
                'conditions': 'VIX spike or market event',
                'expected_benefit': '+20-50% premium'
            }
    
    # Case 3: Morning chaos (first 90 min)
    if time_of_day < time(11, 0):
        stock_move_today = get_intraday_change(symbol)
        if stock_move_today < -2%:  # Down 2%+ at open
            premium_percentile = get_premium_percentile(symbol)
            if premium_percentile < 30:  # Premiums compressed
                return {
                    'should_wait': True,
                    'reason': 'Market stabilization',
                    'conditions': '11am-12pm after volatility settles',
                    'expected_benefit': '+10-15% premium'
                }
    
    # Case 4: Upcoming catalyst
    days_to_fomc = get_days_to_fomc()
    if 0 < days_to_fomc <= 2:
        return {
            'should_wait': True,
            'reason': 'FOMC announcement - IV will spike',
            'conditions': 'Day before or morning of FOMC',
            'expected_benefit': '+15-30% premium'
        }
    
    return {
        'should_wait': False,
        'reason': 'Timing is good - sell now'
    }
```

---

### 2.5 Earnings Alert Strategy (`earnings_alert.py`)

**Purpose**: Proactive heads-up about positions with upcoming earnings.

**Trigger Conditions** (UNCHANGED):
- Earnings within 5 trading days

**Alert Priority Based on Position State** (UNCHANGED):
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

**Extra Urgency** (UNCHANGED):
```python
if days_to_earnings == 0:
    urgency = "TODAY"
    priority = "urgent"
elif days_to_earnings == 1:
    urgency = "TOMORROW"
```

---

### 2.6 Dividend Alert Strategy (NEW - `dividend_alert.py`)

**Purpose**: Prevent early assignment due to dividend capture.

**Trigger Conditions**:
```python
div_date, div_amount = get_next_dividend(symbol)

if not div_date:
    return None  # No dividend coming

days_to_div = (div_date - today).days
days_to_exp = (expiration - today).days

# Only alert if dividend before or near expiration
if days_to_div <= days_to_exp + 7:
    → Evaluate assignment risk
```

**Risk Assessment**:
```python
def evaluate_dividend_assignment_risk(position, div_date, div_amount):
    """
    Determine likelihood of early assignment for dividend capture.
    """
    
    is_itm = position.is_itm()
    itm_amount = position.itm_amount if is_itm else 0
    time_value = position.current_premium - max(itm_amount, 0)
    div_pct = div_amount / position.current_stock_price * 100
    
    # HIGH RISK: ITM + dividend > time value
    if is_itm and div_amount > time_value:
        return {
            'risk_level': 'HIGH',
            'probability': 'Very likely (>80%)',
            'action': 'CLOSE OR ROLL BEFORE EX-DIV',
            'reason': f'Dividend ${div_amount:.2f} > Time value ${time_value:.2f}',
            'priority': 'urgent'
        }
    
    # MEDIUM RISK: Near ATM + significant dividend
    distance_to_strike = abs(position.current_price - position.strike)
    distance_pct = distance_to_strike / position.strike * 100
    
    if distance_pct < 2.0 and div_pct > 0.3:  # Within 2%, dividend >0.3%
        return {
            'risk_level': 'MEDIUM',
            'probability': 'Possible (30-50%)',
            'action': 'MONITOR - May need to close before ex-div',
            'reason': f'Close to strike, dividend {div_pct:.2f}% of stock price',
            'priority': 'high'
        }
    
    # LOW RISK: OTM but aware
    if not is_itm:
        return {
            'risk_level': 'LOW',
            'probability': 'Unlikely (<10%)',
            'action': 'AWARE - Monitor position',
            'reason': f'Currently {distance_pct:.1f}% OTM',
            'priority': 'medium'
        }
    
    return None
```

**Recommendation Format**:
```
⚠️ DIVIDEND ALERT: AAPL $175 call

Ex-Dividend Date: Dec 15 (3 days)
Dividend: $0.25/share (0.14% yield)
Your Expiration: Dec 20 (8 days)

RISK ASSESSMENT: HIGH
Probability of early assignment: Very likely (>80%)

Current Position:
  • Strike: $175
  • Stock price: $180 (ITM by $5.00)
  • Current premium: $5.15
  • Intrinsic value: $5.00
  • Time value: $0.15
  
Why assignment is likely:
  • Dividend ($0.25) > Time value ($0.15)
  • Call buyer profits by exercising early

YOUR LOSS IF ASSIGNED EARLY:
  • Miss dividend: $0.25/share
  • Lose time value: $0.15/share
  • Total: $0.40/share = $40 per contract

RECOMMENDED ACTION: Close or roll BEFORE Dec 14

Options:
1. Close now: Pay $5.15 to exit
   → Keep shares, collect dividend, sell new call after ex-div
   
2. Roll to Jan $180: $1.20 debit
   → Avoid ex-div date, collect higher premium
   
3. Accept assignment: 
   → Sell shares at $175, miss $0.25 dividend, lose $0.15 time value

RECOMMENDED: Option 2 (Roll to January)
```

---

### 2.7 Liquidity Quality Check (NEW - `liquidity_checker.py`)

**Purpose**: Screen recommendations for execution quality before alerting.

**Metrics Evaluated**:
```python
def evaluate_liquidity(symbol, strike, expiration, option_type):
    """
    Check if option is tradable with acceptable execution quality.
    """
    
    chain_data = get_option_data(symbol, strike, expiration, option_type)
    
    bid = chain_data['bid']
    ask = chain_data['ask']
    mid = (bid + ask) / 2
    spread = ask - bid
    volume = chain_data['volume']
    open_interest = chain_data['openInterest']
    
    # Metric 1: Bid-Ask Spread
    spread_pct = (spread / mid * 100) if mid > 0 else 999
    
    if spread_pct < 3:
        spread_quality = "excellent"
    elif spread_pct < 5:
        spread_quality = "good"
    elif spread_pct < 10:
        spread_quality = "fair"
    else:
        spread_quality = "poor"
    
    # Metric 2: Open Interest
    if open_interest > 1000:
        oi_quality = "excellent"
    elif open_interest > 500:
        oi_quality = "good"
    elif open_interest > 100:
        oi_quality = "fair"
    else:
        oi_quality = "poor"
    
    # Metric 3: Daily Volume
    volume_oi_ratio = volume / open_interest if open_interest > 0 else 0
    
    if volume > 100 and volume_oi_ratio > 0.05:
        volume_quality = "excellent"
    elif volume > 50:
        volume_quality = "good"
    elif volume > 10:
        volume_quality = "fair"
    else:
        volume_quality = "poor"
    
    # Overall score
    quality_scores = {'excellent': 4, 'good': 3, 'fair': 2, 'poor': 1}
    avg_score = (quality_scores[spread_quality] + 
                 quality_scores[oi_quality] + 
                 quality_scores[volume_quality]) / 3
    
    if avg_score >= 3.5:
        overall = "excellent"
    elif avg_score >= 2.5:
        overall = "good"
    elif avg_score >= 1.5:
        overall = "fair"
    else:
        overall = "poor"
    
    return {
        'overall': overall,
        'spread': {
            'quality': spread_quality,
            'width': spread,
            'percentage': spread_pct,
            'bid': bid,
            'ask': ask,
            'mid': mid
        },
        'open_interest': {
            'quality': oi_quality,
            'value': open_interest
        },
        'volume': {
            'quality': volume_quality,
            'value': volume,
            'oi_ratio': volume_oi_ratio
        }
    }
```

**Decision Logic**:
```python
# Before generating recommendation:
liquidity = evaluate_liquidity(symbol, recommended_strike, expiration, option_type)

if liquidity['overall'] == 'poor':
    # Try to find alternative strike
    alternatives = find_nearby_liquid_strikes(symbol, recommended_strike, expiration)
    
    if alternatives:
        recommended_strike = alternatives[0]
        regenerate_recommendation()
    else:
        SKIP_RECOMMENDATION  # All options illiquid
        
elif liquidity['overall'] == 'fair':
    ADD_WARNING("⚠️ Moderate liquidity - use limit orders")
```

**Alternative Strike Search**:
```python
def find_nearby_liquid_strikes(symbol, target_strike, expiration, max_distance_pct=0.02):
    """
    Find strikes within 2% of target with better liquidity.
    """
    
    stock_price = get_stock_price(symbol)
    max_distance = stock_price * max_distance_pct
    
    # Get all strikes within range
    strike_range = [
        target_strike - max_distance,
        target_strike + max_distance
    ]
    
    chain = get_option_chain(symbol, expiration)
    candidates = [s for s in chain if strike_range[0] <= s.strike <= strike_range[1]]
    
    # Evaluate each
    evaluated = []
    for strike in candidates:
        liq = evaluate_liquidity(symbol, strike.strike, expiration, option_type)
        evaluated.append({
            'strike': strike.strike,
            'liquidity': liq,
            'distance_from_target': abs(strike.strike - target_strike)
        })
    
    # Sort by liquidity quality, then by distance
    quality_rank = {'excellent': 4, 'good': 3, 'fair': 2, 'poor': 1}
    evaluated.sort(
        key=lambda x: (quality_rank[x['liquidity']['overall']], -x['distance_from_target']),
        reverse=True
    )
    
    # Return strikes with at least "good" liquidity
    return [e['strike'] for e in evaluated if quality_rank[e['liquidity']['overall']] >= 3]
```

---

### 2.8 Execution Guidance System (NEW - `execution_advisor.py`)

**Purpose**: Provide specific price targets and order strategies for manual execution.

**For Closing Positions (Buying Back)**:
```python
def recommend_close_execution(position, liquidity_data):
    """
    Guidance for buying back a short option.
    """
    
    bid = liquidity_data['spread']['bid']
    ask = liquidity_data['spread']['ask']
    mid = liquidity_data['spread']['mid']
    spread = liquidity_data['spread']['width']
    spread_pct = liquidity_data['spread']['percentage']
    
    days_to_exp = position.days_to_expiration
    current_time = datetime.now().time()
    
    # Urgency assessment
    if days_to_exp == 0:
        urgency = "critical"
    elif days_to_exp <= 1:
        urgency = "high"
    elif days_to_exp <= 3:
        urgency = "medium"
    else:
        urgency = "low"
    
    # Spread assessment
    if spread_pct < 5:
        spread_cat = "tight"
    elif spread_pct < 10:
        spread_cat = "moderate"
    else:
        spread_cat = "wide"
    
    # Decision matrix
    if urgency == "critical":
        return {
            'entry_price': ask,
            'strategy': 'market_order',
            'message': 'Expires today - pay ask to guarantee fill',
            'steps': [
                'Enter market order or limit at ask',
                'Execute immediately'
            ]
        }
    
    elif urgency == "high" and spread_cat == "wide":
        return {
            'entry_price': round(mid + (spread * 0.25), 2),
            'strategy': 'limit_aggressive',
            'message': 'Expires soon + wide spread - start aggressive',
            'steps': [
                f'Enter limit order at ${mid + (spread * 0.25):.2f} (mid + 25%)',
                'Wait 2 minutes',
                f'If no fill, move to ${ask:.2f} (ask)'
            ]
        }
    
    elif spread_cat == "tight":
        return {
            'entry_price': mid,
            'strategy': 'limit_mid',
            'message': 'Tight spread - midpoint should fill quickly',
            'steps': [
                f'Enter limit order at ${mid:.2f} (midpoint)',
                'Should fill within 1-2 minutes'
            ]
        }
    
    elif spread_cat == "moderate":
        return {
            'entry_price': mid,
            'strategy': 'limit_mid_patient',
            'message': 'Moderate spread - be patient',
            'steps': [
                f'Enter limit order at ${mid:.2f} (midpoint)',
                'Wait 2 minutes',
                f'If no fill, move to ${round(mid + (spread * 0.25), 2):.2f}',
                f'Final: move to ${ask:.2f} if needed'
            ]
        }
    
    else:  # wide spread, no urgency
        return {
            'entry_price': round(bid + (spread * 0.35), 2),
            'strategy': 'limit_patient',
            'message': 'Wide spread - walk up slowly',
            'steps': [
                f'Enter limit order at ${round(bid + (spread * 0.35), 2):.2f}',
                'Wait 2-3 minutes',
                f'If no fill, move to ${mid:.2f}',
                'Continue walking up in small increments'
            ]
        }
```

**For Opening Positions (Selling New Call)**:
```python
def recommend_sell_execution(symbol, strike, expiration, liquidity_data):
    """
    Guidance for selling a new covered call.
    """
    
    bid = liquidity_data['spread']['bid']
    ask = liquidity_data['spread']['ask']
    mid = liquidity_data['spread']['mid']
    spread = liquidity_data['spread']['width']
    spread_pct = liquidity_data['spread']['percentage']
    
    current_time = datetime.now().time()
    stock_momentum = get_intraday_momentum(symbol)
    
    # Time of day assessment
    if current_time < time(10, 30):
        time_cat = "morning"
    elif current_time < time(15, 30):
        time_cat = "normal"
    else:
        time_cat = "afternoon"
    
    # Spread assessment
    if spread_pct < 5:
        spread_cat = "tight"
    elif spread_pct < 10:
        spread_cat = "moderate"
    else:
        spread_cat = "wide"
    
    # Decision matrix for SELLING
    if time_cat == "morning":
        return {
            'entry_price': round(ask - (spread * 0.25), 2),
            'strategy': 'limit_aggressive',
            'message': 'Morning volatility - aim high',
            'steps': [
                f'Enter limit order at ${round(ask - (spread * 0.25), 2):.2f} (near ask)',
                'Morning IV spike favors sellers',
                'Wait 2-3 minutes',
                f'If no fill, lower to ${mid:.2f}'
            ]
        }
    
    elif spread_cat == "tight":
        return {
            'entry_price': mid,
            'strategy': 'limit_mid',
            'message': 'Tight spread - midpoint works',
            'steps': [
                f'Enter limit order at ${mid:.2f} (midpoint)',
                'Should fill within 1-2 minutes'
            ]
        }
    
    elif spread_cat == "wide" and stock_momentum > 0:
        return {
            'entry_price': round(ask - (spread * 0.25), 2),
            'strategy': 'limit_aggressive',
            'message': 'Stock rising - premiums increasing',
            'steps': [
                f'Enter limit order at ${round(ask - (spread * 0.25), 2):.2f} (near ask)',
                'Rising stock increases call value',
                'Be patient - may fill at good price',
                f'If no fill in 3 min, lower to ${mid:.2f}'
            ]
        }
    
    elif spread_cat == "wide" and stock_momentum < 0:
        return {
            'entry_price': mid,
            'strategy': 'limit_mid_patient',
            'message': 'Stock falling - premiums compressing',
            'steps': [
                f'Enter limit order at ${mid:.2f}',
                'Falling stock may improve premium soon',
                'Wait 2-3 minutes before lowering price'
            ]
        }
    
    else:  # moderate spread, normal conditions
        return {
            'entry_price': round(mid + (spread * 0.15), 2),
            'strategy': 'limit_standard',
            'message': 'Start slightly above mid',
            'steps': [
                f'Enter limit order at ${round(mid + (spread * 0.15), 2):.2f}',
                'Wait 2 minutes',
                f'If no fill, lower to ${mid:.2f}',
                f'Final: accept ${round(mid - (spread * 0.15), 2):.2f} if needed'
            ]
        }
```

**For Two-Legged Rolls**:
```python
def recommend_roll_execution(old_position, new_position, net_credit_or_debit, old_liq, new_liq):
    """
    Determine best method for executing a roll (two legs).
    """
    
    # If BOTH legs have excellent liquidity - spread order possible
    if old_liq['overall'] == 'excellent' and new_liq['overall'] == 'excellent':
        return {
            'method': 'spread_order',
            'net_price': net_credit_or_debit,
            'message': 'Both legs have excellent liquidity',
            'steps': [
                f'Enter spread order for ${abs(net_credit_or_debit):.2f} net {"credit" if net_credit_or_debit < 0 else "debit"}',
                'This executes both legs simultaneously',
                'Guaranteed net price if filled'
            ]
        }
    
    # If EITHER leg has poor liquidity - sequential only
    elif old_liq['overall'] == 'poor' or new_liq['overall'] == 'poor':
        close_guidance = recommend_close_execution(old_position, old_liq)
        sell_guidance = recommend_sell_execution(
            new_position.symbol, 
            new_position.strike, 
            new_position.expiration, 
            new_liq
        )
        
        return {
            'method': 'sequential',
            'message': 'Poor liquidity on one or both legs - execute separately',
            'steps': [
                '=== STEP 1: Close old position ===',
                *close_guidance['steps'],
                '',
                '=== STEP 2: After Step 1 fills, sell new position ===',
                *sell_guidance['steps']
            ],
            'leg1': close_guidance,
            'leg2': sell_guidance
        }
    
    # Mixed liquidity - offer both options
    else:
        return {
            'method': 'user_choice',
            'options': {
                'spread': {
                    'description': 'Execute both legs as spread order',
                    'pros': 'Faster, guaranteed net price',
                    'cons': 'May not fill if market moves',
                    'net_price': net_credit_or_debit
                },
                'sequential': {
                    'description': 'Execute legs one at a time',
                    'pros': 'Higher fill probability',
                    'cons': 'Stock may move between legs',
                    'expected_slippage': '$0.05-0.10 per leg'
                }
            },
            'recommendation': 'sequential',
            'message': 'Moderate liquidity - sequential is safer for manual execution'
        }
```

**Time-of-Day Adjustments**:
```python
def adjust_for_market_conditions(base_guidance, symbol):
    """
    Adjust execution guidance based on current market conditions.
    """
    
    current_time = datetime.now().time()
    
    # Morning volatility (9:30-10:30)
    if time(9, 30) <= current_time < time(10, 30):
        return {
            **base_guidance,
            'timing_note': '⏰ MORNING SESSION - Higher volatility',
            'seller_advantage': 'If selling, premiums are elevated - aim high',
            'buyer_caution': 'If buying back, spreads may be wider',
            'patience': 'low'
        }
    
    # Normal hours (10:30-15:30)
    elif time(10, 30) <= current_time < time(15, 30):
        return {
            **base_guidance,
            'timing_note': '✓ NORMAL HOURS - Standard execution',
            'patience': 'medium'
        }
    
    # Closing rush (15:30-16:00)
    else:
        return {
            **base_guidance,
            'timing_note': '⚠️ LAST 30 MIN - Spreads may widen',
            'urgency': 'Act decisively, market closes soon',
            'patience': 'low'
        }
```

---

### 2.9 Performance Tracking System (NEW - `performance_tracker.py`)

**Purpose**: Track recommendation accuracy and portfolio performance to validate algorithm effectiveness.

**Data Captured**:
```python
# When recommendation generated:
recommendation_record = {
    'id': f'{strategy}_{symbol}_{strike}_{date}_{account}',
    'timestamp': datetime.now(),
    'strategy_type': 'early_roll',
    'symbol': 'AAPL',
    'strike': 180.0,
    'expiration': '2024-12-20',
    
    # Predictions
    'predicted_buyback_cost': 0.15,
    'predicted_new_premium': 0.50,
    'predicted_net': 0.35,  # Credit
    'predicted_profit_pct': 0.65,
    
    # Recommendation
    'recommendation_action': 'ROLL',
    'recommended_strike': 185.0,
    'recommended_expiration': '2024-12-27',
    'priority': 'high',
    
    # Status
    'status': 'pending',  # pending, executed, ignored, skipped
    'user_action': None,
    'execution_timestamp': None
}

# When user executes (or ignores):
execution_record = {
    'recommendation_id': 'early_roll_AAPL_180_2024-12-18_...',
    'user_action': 'executed',  # executed, ignored, modified
    'execution_timestamp': datetime.now(),
    
    # Actual results
    'actual_buyback_cost': 0.16,  # vs predicted 0.15
    'actual_new_premium': 0.48,   # vs predicted 0.50
    'actual_net': 0.32,           # vs predicted 0.35
    
    # Execution quality
    'buyback_slippage': 0.01,     # Paid $0.01 more than predicted
    'sell_slippage': -0.02,       # Got $0.02 less than predicted
    'total_slippage': -0.01,      # Net $0.01 worse
    'slippage_pct': -2.9,         # 2.9% worse than predicted
    
    # Time metrics
    'time_to_execute': 300,       # 5 minutes (seconds)
    'fills_required': 2,          # Number of order modifications
    
    # Outcome
    'outcome': 'success',         # success, partial_success, failure
    'actual_profit': 0.32,
    'vs_prediction': -0.03,       # $0.03 worse than predicted
    'accuracy_pct': 91.4          # 91.4% of predicted
}
```

**Analytics Generated**:
```python
def generate_performance_report(timeframe='week'):
    """
    Generate comprehensive performance analytics.
    """
    
    recommendations = get_recommendations(timeframe)
    
    # Overall metrics
    total_recs = len(recommendations)
    executed = [r for r in recommendations if r.status == 'executed']
    ignored = [r for r in recommendations if r.status == 'ignored']
    
    execution_rate = len(executed) / total_recs * 100
    
    # Financial metrics
    total_premium_collected = sum(r.actual_new_premium for r in executed)
    total_buyback_cost = sum(r.actual_buyback_cost for r in executed)
    net_profit = total_premium_collected - total_buyback_cost
    
    # Win rate
    profitable = [r for r in executed if r.actual_profit > 0]
    win_rate = len(profitable) / len(executed) * 100 if executed else 0
    
    # Prediction accuracy
    avg_prediction_error = np.mean([
        abs(r.actual_net - r.predicted_net) / r.predicted_net * 100
        for r in executed if r.predicted_net != 0
    ])
    
    # Slippage analysis
    avg_slippage = np.mean([r.total_slippage for r in executed])
    avg_slippage_pct = np.mean([r.slippage_pct for r in executed])
    
    # Strategy breakdown
    strategy_breakdown = {}
    for strategy_type in ['early_roll', 'itm_roll', 'preemptive_roll', 'new_sell']:
        strategy_recs = [r for r in executed if r.strategy_type == strategy_type]
        if strategy_recs:
            strategy_breakdown[strategy_type] = {
                'count': len(strategy_recs),
                'avg_profit': np.mean([r.actual_profit for r in strategy_recs]),
                'win_rate': len([r for r in strategy_recs if r.actual_profit > 0]) / len(strategy_recs) * 100,
                'total_profit': sum(r.actual_profit for r in strategy_recs)
            }
    
    # Top performers (symbols)
    symbol_performance = {}
    for symbol in set(r.symbol for r in executed):
        symbol_recs = [r for r in executed if r.symbol == symbol]
        symbol_performance[symbol] = {
            'trades': len(symbol_recs),
            'total_profit': sum(r.actual_profit for r in symbol_recs),
            'avg_profit': np.mean([r.actual_profit for r in symbol_recs]),
            'win_rate': len([r for r in symbol_recs if r.actual_profit > 0]) / len(symbol_recs) * 100
        }
    
    top_symbols = sorted(
        symbol_performance.items(),
        key=lambda x: x[1]['total_profit'],
        reverse=True
    )[:5]
    
    # Warnings and alerts
    warnings = []
    
    # Check for frequent assignments
    assignments = get_assignments(timeframe)
    for symbol in set(a.symbol for a in assignments):
        symbol_assigns = [a for a in assignments if a.symbol == symbol]
        if len(symbol_assigns) >= 2:
            warnings.append({
                'type': 'frequent_assignment',
                'symbol': symbol,
                'count': len(symbol_assigns),
                'message': f'{symbol}: {len(symbol_assigns)} assignments - consider wider strikes'
            })
    
    # Check for low execution rate on specific strategies
    for strategy_type in strategy_breakdown:
        strategy_all = [r for r in recommendations if r.strategy_type == strategy_type]
        strategy_exec = [r for r in executed if r.strategy_type == strategy_type]
        exec_rate = len(strategy_exec) / len(strategy_all) * 100 if strategy_all else 0
        
        if exec_rate < 50:
            warnings.append({
                'type': 'low_execution_rate',
                'strategy': strategy_type,
                'rate': exec_rate,
                'message': f'{strategy_type}: Only {exec_rate:.0f}% executed - review recommendations'
            })
    
    return {
        'timeframe': timeframe,
        'summary': {
            'total_recommendations': total_recs,
            'executed': len(executed),
            'ignored': len(ignored),
            'execution_rate': execution_rate,
            'win_rate': win_rate
        },
        'financial': {
            'total_premium_collected': total_premium_collected,
            'total_buyback_cost': total_buyback_cost,
            'net_profit': net_profit,
            'avg_profit_per_trade': net_profit / len(executed) if executed else 0
        },
        'accuracy': {
            'avg_prediction_error_pct': avg_prediction_error,
            'avg_slippage': avg_slippage,
            'avg_slippage_pct': avg_slippage_pct
        },
        'by_strategy': strategy_breakdown,
        'top_symbols': top_symbols,
        'warnings': warnings
    }
```

**Report Format** (sent weekly):
```
📊 WEEKLY PERFORMANCE REPORT
Week of Dec 11-18, 2024

━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Recommendations: 12 total
  • Executed: 9 (75%)
  • Ignored: 2 (17%)
  • Skipped (liquidity): 1 (8%)

Financial Results:
  • Premium collected: $1,240
  • Buyback costs: $180
  • Net profit: $1,060
  • Avg per trade: $118
  
Win rate: 100% (9/9 profitable)

━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALGORITHM ACCURACY
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Prediction accuracy: +3%
  (Actual results 3% better than predicted)
  
Execution quality:
  • Avg slippage: -$0.02/contract (-2%)
  • Better than expected!

━━━━━━━━━━━━━━━━━━━━━━━━━━━
BY STRATEGY
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Early Rolls: 6 trades
  • Avg profit: $0.45/share
  • Win rate: 100%
  • Total: $270

Preemptive Rolls: 2 trades
  • Avg profit: $0.30/share
  • Avoided ITM: 2 times
  • Saved est: $340

New Sells: 1 trade
  • Premium: $0.85/share
  • Total: $85

━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOP PERFORMERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. AAPL: $320 profit (4 trades, 100% win rate)
2. MSFT: $180 profit (2 trades, 100% win rate)
3. TSLA: $140 profit (3 trades, 100% win rate)

━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ ALERTS & INSIGHTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━
• TSLA: 2 preemptive rolls in 7 days
  → High volatility detected
  → Consider: Wider Delta 10 strikes or reduce position
  
• Friday timing optimization: 2 recommendations to wait for Monday
  → Both resulted in +$0.05-0.08 better premiums
  → Keep using this feature!

━━━━━━━━━━━━━━━━━━━━━━━━━━━
NEXT WEEK OUTLOOK
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Upcoming events:
  • Dec 20: 3 positions expiring
  • Dec 22 (ex-div): MSFT dividend alert
  • Holiday week: Lower volume expected (consider multi-week)
```

---

### 2.10 Triple Witching Day Strategy (NEW - `triple_witching_handler.py`)

**Purpose**: Special handling for quarterly options expiration days when stock options, index options, and stock index futures all expire simultaneously.

**Occurs**: 3rd Friday of March, June, September, and December

**Market Characteristics**:
- 2-3x normal trading volume
- Intraday volatility spikes 150-300%
- Wide bid-ask spreads (2-5x normal)
- "Pinning" effect at major strikes
- IV inflation followed by crush at 4pm ET
- Final hour (3:00-4:00 PM ET) extreme chaos

**Detection Logic**:
```python
def is_triple_witching(date):
    # Must be Friday
    if date.weekday() != 4:
        return False
    # Must be Mar, Jun, Sep, or Dec
    if date.month not in [3, 6, 9, 12]:
        return False
    # Must be 3rd Friday
    first_day = date.replace(day=1)
    days_until_friday = (4 - first_day.weekday()) % 7
    third_friday = first_day + timedelta(days=days_until_friday + 14)
    return date == third_friday.date()
```

**Position Analysis Matrix**:

| Position State | Action | Timing | Rationale |
|---------------|--------|--------|-----------|
| **>5% OTM** | Let expire | No action | Very safe, chaos works in your favor |
| **2-5% OTM** | Monitor | Watch final hour | Probably safe, but watch for pinning |
| **<2% OTM or ATM** | Close by 2:30 PM ET | 10 AM - 2:30 PM | Pinning risk - stock could drift into strike |
| **<5% ITM** | Close or Roll by 2:30 PM | 10 AM - 2:30 PM | Tactical roll makes sense if reasonable |
| **>5% ITM** | Accept assignment or close | Morning (7-10 AM ET) | Deep ITM - don't try to fix in chaos |

**Trading Windows**:

| Time (ET) | Quality | Action |
|-----------|---------|--------|
| 6:30-7:00 AM | 🔴 POOR | DO NOT TRADE - Opening chaos |
| 7:00-10:30 AM | 🟡 FAIR | Close deep ITM positions only |
| 10:30 AM-2:30 PM | 🟢 BEST | Primary trading window |
| 2:30-3:00 PM | 🟡 FAIR | Last chance to close risky positions |
| 3:00-4:00 PM | 🔴 TERRIBLE | AVOID ALL TRADING - Final hour chaos |

**Strategy Overrides Applied**:
- Never roll deep ITM (>5%) on Triple Witching
- More conservative thresholds (3% ITM max for rolls vs 5% normal)
- Default to closing instead of rolling
- Recommend waiting until Monday for new option sales

**Notification Format**:
```
🔴 TRIPLE WITCHING DAY ALERT

Positions expiring today: 5
  • 2 URGENT - Need immediate action
  • 2 WATCH - Monitor closely
  • 1 SAFE - Can let expire

TRADING WINDOWS:
🟢 10:30 AM-2:30 PM ET - Best execution window

CRITICAL REMINDERS:
• NEVER use market orders today
• Expect 2-3x normal bid-ask spreads
• Fills take 5-10 minutes vs 1-2 normal
• Accept higher slippage today
```

**Enhanced Execution Guidance (V2.1)**:

When a position is deep ITM on Triple Witching Day, the system now provides:

1. **hide_roll_options flag**: When `CLOSE_DONT_ROLL` is recommended, the roll options table is hidden to avoid confusion

2. **Detailed Close Cost Display**:
   - Estimated close cost per share
   - Intrinsic value breakdown
   - Total position cost

3. **Time Window Guidance**:
   ```python
   triple_witching_execution = {
       'best_window': '10:30 AM - 2:30 PM ET',
       'avoid_windows': [
           '6:30-7:00 AM ET (opening chaos)',
           '3:00-4:00 PM ET (final hour - extreme pinning)'
       ],
       'expected_slippage': '$50-150 per contract',
       'execution_strategy': [
           'Use LIMIT orders only - NEVER market orders',
           'Start at mid price, be prepared to adjust',
           'Wait 3-5 minutes between price adjustments',
           'Accept some slippage to get filled'
       ]
   }
   ```

4. **ITM Position Status Display** (V2.1 Fix):
   - Shows actual ITM percentage (e.g., "35% ITM")
   - Displays intrinsic value (e.g., "$21.00 intrinsic")
   - Replaces confusing "prob OTM" label with actual position status

**Example Deep ITM Notification on Triple Witching**:
```
🔴 TRIPLE WITCHING: CLOSE FIG - 35.0% ITM (Don't roll today)

Position: 1x FIG $60 put Jan 16
Status: $21 IN THE MONEY

RECOMMENDED ACTION: CLOSE IMMEDIATELY
Estimated Close Cost: $21.25/share ($2,125 total)

Why not roll:
  • Too deep ITM (35%) to roll efficiently
  • Poor fills expected on Triple Witching
  • Close today, sell fresh Monday

TRIPLE WITCHING EXECUTION:
Best window: 10:30 AM - 2:30 PM ET
Expected slippage: $50-150 per contract
Use limit orders at mid price
```

---

## 3. Technical Analysis

### 3.1 Indicators Calculated (UNCHANGED)

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

### 3.2 NEW Indicators

| Indicator | Description | Usage |
|-----------|-------------|-------|
| Intraday Momentum | Price direction today | Execution timing |
| Volume Percentile | Current volume vs average | Liquidity assessment |
| IV Percentile | Current IV vs 52-week range | Premium timing |
| Ex-Dividend Date | Next dividend date | Assignment risk |
| Dividend Amount | Dividend per share | Assignment probability |

### 3.3 Probability Ranges (UNCHANGED)

Based on weekly volatility, we calculate price ranges:
```python
# 1 standard deviation (~68% probability)
prob_68_low = current_price * (1 - weekly_volatility)
prob_68_high = current_price * (1 + weekly_volatility)

# 1.65 standard deviation (~90% probability) - Used for Delta 10
prob_90_low = current_price * (1 - weekly_volatility * 1.65)
prob_90_high = current_price * (1 + weekly_volatility * 1.65)
```

### 3.4 Strike Recommendation Logic (UNCHANGED)

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

## 4. Deduplication Logic (UNCHANGED)

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

## 5. Priority Levels (UPDATED)

| Priority | Criteria |
|----------|----------|
| **urgent** | ITM ≥5%, Earnings TODAY/TOMORROW, Dividend ex-date within 2 days, Expires today |
| **high** | ITM 1-5%, >60% profit captured, Approaching strike <1.5%, Dividend ex-date within 5 days, Sell opportunity >$5000/year |
| **medium** | Approaching strike 1.5-3%, Wait recommendations, Moderate income, Dividend awareness |
| **low** | Small positions, Wait for timing optimization |

---

## 6. Notification Content

### Title Format Examples:
```
# Early Roll:
"ROLL AAPL $180→$185 call ($0.35 credit)"

# Early Roll (Multi-week):
"ROLL AAPL $180→$185 call (2-week, $0.55 credit)"

# ITM Roll:
"ROLL ITM AAPL $180→$185 (2wk, $0.50 debit) · Stock $190"

# Preemptive Roll:
"⚠️ AAPL approaching $180 strike · Stock $177 (+3% today)"

# Earnings Alert:
"📊 EARNINGS in 2 days: AAPL $180 call (3% OTM) · Stock $175"

# Dividend Alert:
"💰 DIVIDEND in 3 days: AAPL $175 call - Early assignment risk HIGH"

# Sell New:
"Sell 3 AAPL call(s) at $185 for Dec 20 · Stock $175"

# Timing Wait:
"AAPL call expired - WAIT until Monday (better premium)"

# Liquidity Warning:
"ROLL AAPL $180→$185 · ⚠️ Moderate liquidity - use limit orders"
```

### Description Format with Enhanced Details:
```
# Roll with Liquidity & Execution:
"Roll AAPL $180 call Dec 13 → Dec 20 $185 - $0.30 credit

Profit Analysis:
  • Captured: 65% ($0.65 of $1.00)
  • Remaining if wait: $0.35
  • Rolling now is optimal

Liquidity: GOOD
  Close $180: Bid $0.18 | Ask $0.22 (spread: $0.04)
  Open $185: Bid $0.48 | Ask $0.52 (spread: $0.04)

Execution Plan:
  Step 1: Close $180 at $0.20 (mid)
  Step 2: Sell $185 at $0.50 (mid)
  Expected net: $0.30 credit
  Expected slippage: $0.01-0.02"

# Preemptive Roll with Mean Reversion:
"TSLA approaching $490 strike (currently $485)

Position at risk - stock trending up with momentum
No resistance detected at $490

RECOMMENDED: Roll to 2-week $500 call
  • Current $490 buyback: $1.80
  • New 2-week $500 premium: $0.55
  • Net debit: $1.25

Why 2-week:
  • Reduces debit vs 1-week ($1.25 vs $1.50)
  • Time for mean reversion if spike reverses
  • Can close early if stock drops back

vs waiting until ITM:
  • If ITM tomorrow: $2.50+ debit
  • Savings by acting now: $1.25"

# Dividend Alert:
"⚠️ DIVIDEND ALERT: AAPL $175 call

Ex-Dividend: Dec 15 (3 days)
Dividend: $0.25/share
Your expiration: Dec 20 (8 days)

RISK: HIGH - Early assignment very likely (>80%)

Why:
  • Position ITM by $5.00
  • Time value only $0.15
  • Dividend ($0.25) > Time value
  • Call buyer profits by exercising

Loss if assigned:
  • Miss dividend: $0.25/share
  • Lose time value: $0.15/share
  • Total: $40 per contract

RECOMMENDED: Roll to Jan $180 before Dec 14
  • Debit: $1.20
  • Avoids assignment
  • Past ex-div date"

# Strategic Timing:
"AAPL $180 call expired OTM

Current Friday 3pm premium: $0.35

WAIT until Monday 10-11am

Why:
  • Monday IV typically 5-10% higher
  • Better visibility after weekend
  • Estimated Monday: $0.40-0.42
  
Potential gain: $5-7 per contract
Risk: None (already closed)"
```

---

## 7. Configuration Parameters (COMPREHENSIVE UPDATE)

### Profit Thresholds
```python
# Early roll thresholds
NORMAL_PROFIT_THRESHOLD = 0.60          # Standard early roll (was 0.80)
EARNINGS_WEEK_PROFIT_THRESHOLD = 0.45   # Before earnings (was 0.60)
SHORT_DTE_THRESHOLD = 0.35              # <3 days to expiration (NEW)
AGGRESSIVE_THRESHOLD = 0.25             # For very short DTE (NEW)
```

### Strike Selection
```python
# Probability targets
STANDARD_PROBABILITY_TARGET = 0.90      # Delta 10 (unchanged)
CONSERVATIVE_PROBABILITY_TARGET = 0.90   # For core holdings
AGGRESSIVE_PROBABILITY_TARGET = 0.80    # For max income (optional)
```

### Cost Sensitivity
```python
# Standard cost thresholds
MAX_DEBIT_PCT_OF_NEW_PREMIUM = 0.50        # Standard
MAX_DEBIT_PCT_EARNINGS = 0.75              # Before earnings (NEW)
MAX_DEBIT_PCT_HIGH_PROFIT = 0.15           # When 80%+ captured (NEW)
MAX_DEBIT_PCT_EXPIRING_SOON = 1.0          # Last 1-2 days (NEW)

# Scenario comparison
SCENARIO_COMPARISON_TOLERANCE = 0.90       # Roll if within 90% of best (NEW)
MIN_SAVINGS_TO_WAIT = 0.10                 # Must save $0.10+ to wait (NEW)
```

### Multi-Week Roll Parameters
```python
MAX_ROLL_WEEKS_STANDARD = 2             # Standard early rolls (NEW)
MAX_ROLL_WEEKS_PREEMPTIVE = 3           # Preemptive/ITM rolls (NEW)
MAX_ROLL_WEEKS_DEEP_ITM = 6             # Deep ITM situations (NEW)
MIN_MARGINAL_PREMIUM = 0.15             # Must add $0.15+/week (NEW)
MEAN_REVERSION_EXPECTED_DAYS = 5        # Assume reversion in 5 days (NEW)
```

### Preemptive Roll Parameters
```python
APPROACHING_THRESHOLD_PCT = 3.0         # Alert within 3% of strike (NEW)
URGENT_THRESHOLD_PCT = 1.5              # Urgent within 1.5% (NEW)
MIN_DAYS_TO_EXPIRATION = 2              # Don't alert if <2 days (NEW)
MOMENTUM_LOOKBACK_DAYS = 3              # Check 3-day trend (NEW)
MIN_VOLUME_MULTIPLE = 1.2               # Volume 20% above avg (NEW)
```

### Strategic Timing Parameters
```python
ENABLE_TIMING_OPTIMIZATION = True       # Feature flag (NEW)
FRIDAY_CUTOFF_TIME = "14:00"           # After 2pm suggest Monday (NEW)
MIN_PREMIUM_PCT_OF_STOCK = 0.003       # 0.3% threshold (NEW)
LOW_VIX_THRESHOLD = 15                 # Below = watch for expansion (NEW)
AVOID_MORNING_CHAOS = True             # Don't sell first 90 min if down >2% (NEW)
MORNING_VOLATILITY_START = time(9, 30) # (NEW)
MORNING_VOLATILITY_END = time(10, 30)  # (NEW)
```

### Liquidity Thresholds
```python
MIN_OPEN_INTEREST = 100                 # Warn below this (NEW)
MIN_DAILY_VOLUME = 20                   # Warn below this (NEW)
MAX_SPREAD_PCT_EXCELLENT = 0.03         # <3% excellent (NEW)
MAX_SPREAD_PCT_GOOD = 0.05             # <5% good (NEW)
MAX_SPREAD_PCT_FAIR = 0.10             # <10% fair (NEW)
SKIP_IF_POOR_LIQUIDITY = True          # Auto-skip poor (NEW)
SUGGEST_ALTERNATIVES = True             # Find better strikes (NEW)
MAX_STRIKE_ADJUSTMENT_PCT = 0.02       # Within 2% of target (NEW)
```

### Execution Guidance Parameters
```python
TIGHT_SPREAD_THRESHOLD = 0.05          # <5% = tight (NEW)
WIDE_SPREAD_THRESHOLD = 0.10           # >10% = wide (NEW)
QUICK_MOVE_SECONDS = 60                # Move price after 1 min (NEW)
NORMAL_WAIT_SECONDS = 120              # Wait 2 min normally (NEW)
PATIENT_WAIT_SECONDS = 180             # Wait 3 min if patient (NEW)
WALK_INCREMENT_PCT = 0.25              # Move 25% toward market (NEW)
AFTERNOON_RUSH_START = time(15, 30)    # (NEW)
```

### Dividend Tracking Parameters
```python
DAYS_BEFORE_EXDIV_ALERT = 7            # Alert within 7 days (NEW)
HIGH_ASSIGNMENT_RISK_THRESHOLD = 0.80   # 80% probability (NEW)
MIN_DIVIDEND_PCT_FOR_RISK = 0.2        # 0.2% of stock price (NEW)
```

### Performance Tracking Parameters
```python
TRACK_RECOMMENDATIONS = True            # Enable tracking (NEW)
GENERATE_WEEKLY_REPORT = True          # Weekly analytics (NEW)
MIN_EXECUTION_RATE_WARNING = 0.50      # Warn if <50% executed (NEW)
```

### Earnings & Events
```python
DAYS_BEFORE_EARNINGS_ALERT = 5         # (unchanged)
MIN_WEEKLY_INCOME = 50                 # Minimum to recommend (unchanged)
```

---

## 8. Key Formulas (UPDATED)

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

### Approaching Strike Distance:
```python
distance_pct = abs(current_price - strike_price) / strike_price * 100
```

### Liquidity Score:
```python
quality_scores = {'excellent': 4, 'good': 3, 'fair': 2, 'poor': 1}
overall_score = (spread_score + oi_score + volume_score) / 3
```

### Execution Slippage:
```python
# For closing (buying back):
slippage = actual_fill - predicted_mid

# For opening (selling):
slippage = predicted_mid - actual_fill

# Total for roll:
total_slippage = close_slippage + sell_slippage
slippage_pct = total_slippage / predicted_net * 100
```

### Dividend Assignment Probability:
```python
if dividend_amount > time_value and is_itm:
    probability = 0.85  # Very likely
elif dividend_amount > (time_value * 0.5) and distance_to_strike < 2%:
    probability = 0.50  # Possible
else:
    probability = 0.10  # Unlikely
```

---

## 9. Workflow Integration

### Daily Scan Process:
```
1. Morning Scan (9:00 AM before market open)
   → Performance report (if Monday)
   → Dividend alerts (check all positions)
   → Earnings alerts (within 5 days)
   → Strategic timing opportunities (Friday positions)

2. Market Open Scan (9:45 AM - after initial volatility)
   → Preemptive roll checks (approaching strikes)
   → Early roll opportunities (60%+ profit)
   → ITM position analysis

3. Midday Scan (12:00 PM)
   → Liquidity recheck for pending recommendations
   → Execution guidance updates

4. Afternoon Scan (3:00 PM - before close)
   → End-of-day timing recommendations
   → Expiring positions (assign or roll decisions)

5. After Market Close (4:15 PM)
   → Performance tracking updates
   → Next day preparation
```

---

## 10. Known Limitations

1. **API Rate Limiting**: Yahoo Finance may return 429 errors during high-frequency calls
2. **Options Chain Availability**: Not all expirations may have liquid options
3. **Estimated Premiums**: When market data unavailable, premiums are estimated
4. **Market Hours**: Data is cached differently during market hours vs off-hours
5. **Dividend Data Accuracy**: Ex-dates may change; verify on brokerage platform
6. **Execution Timing**: Guidance assumes normal market conditions; adjust for news/events
7. **Multi-Week Analysis**: Limited to 3 weeks for standard rolls (data availability)
8. **Performance Tracking**: Requires manual confirmation of executed trades

---

## 10.1 V2.2 ITM Threshold Enforcement

**Purpose**: Enforce strict thresholds for when to CLOSE positions vs attempting to ROLL them.

### ITM Thresholds (Checked BEFORE Roll Analysis)

| Threshold | ITM % | Action | Rationale |
|-----------|-------|--------|-----------|
| **CATASTROPHIC** | >20% | CLOSE IMMEDIATELY | Position failed, cut losses |
| **DEEP ITM** | >10% | CLOSE_DONT_ROLL | Too deep for effective rolling |
| **NORMAL** | >5% | CLOSE_DONT_ROLL | Roll economics are poor |
| **TRIPLE WITCHING** | >3% | CLOSE_DONT_ROLL | Stricter on volatile days |

### Decision Flow

```python
# STEP 1: Threshold check FIRST (before any roll analysis)
threshold_check = should_close_itm_position_by_threshold(
    symbol, strike, option_type, current_price, is_triple_witching_day
)

if threshold_check['should_close']:
    → Generate CLOSE recommendation, skip roll optimizer entirely

# STEP 2: Only if threshold check passes, proceed with TA analysis
action, reason, analysis = ta_service.analyze_itm_position(...)

# STEP 3: If TA says "wait", generate WATCH recommendation
if action == "wait":
    → Generate WATCH recommendation

# STEP 4: Run roll optimizer
roll_analysis = optimizer.analyze_itm_position(...)

# STEP 5: Validate roll options (must have 3 different strikes)
validation = validate_roll_options(roll_options_data)
if not validation['valid']:
    → Generate CLOSE recommendation with error message

# STEP 6: Economic sanity check
economic_check = evaluate_roll_economics(...)
if not economic_check['economically_sound']:
    → Generate CLOSE recommendation with economic analysis

# STEP 7: All checks passed - generate roll recommendation
```

### Economic Sanity Checks

| Check | Criteria | If Fails |
|-------|----------|----------|
| **Cost Check** | Roll cost < Close cost | CLOSE - rolling costs more |
| **Savings Check** | Savings ≥ $50/contract OR ≥10% | CLOSE - minimal savings |
| **New Position ITM** | New strike is OTM | CLOSE - can't roll into ITM |

### Configuration (`algorithm_config.py`)

```python
"itm_roll": {
    # V2.2: ITM Close Thresholds
    "catastrophic_itm_pct": 20.0,          # Never roll
    "deep_itm_pct": 10.0,                  # Too deep to roll
    "normal_close_threshold_pct": 5.0,     # Close on normal days
    "triple_witching_close_threshold_pct": 3.0,  # Close on Triple Witching
    
    # V2.2: Economic sanity thresholds
    "min_roll_savings_dollars": 50,        # Must save $50+ to justify roll
    "min_roll_savings_percent": 10,        # Must save 10%+ to justify roll
    "min_strike_variation_pct": 2.0,       # Options must differ by 2%+
}
```

### Example Scenarios

**Scenario 1: FIG at 35% ITM (Catastrophic)**
```
Input:  FIG $60 PUT, Stock at $39
ITM:    35% (>20% threshold)
Output: CLOSE IMMEDIATELY
Reason: CATASTROPHIC: 35% ITM - position has failed
```

**Scenario 2: AVGO at 7.3% ITM on Triple Witching**
```
Input:  AVGO $362.5 PUT, Stock at $336, Triple Witching
ITM:    7.3% (>3% Triple Witching threshold)
Output: CLOSE_DONT_ROLL
Reason: TRIPLE WITCHING: 7.3% ITM - poor execution expected
```

**Scenario 3: Roll into ITM Position**
```
Input:  Stock at $39, Optimizer suggests roll to $36 strike
New ITM: 8.3% ($36 strike with $39 stock)
Output: CLOSE_DONT_ROLL
Reason: New position would be 8.3% ITM - problem not solved
```

---

## 10.2 V2.1 Bug Fixes Reference

**Scenario: Deep ITM PUT on Triple Witching**

Before V2.1 (Buggy):
```
Title: ROLL ITM AVGO $362.5→$362 (2wk, $0.00 debit) · Stock $336
Description: 2x AVGO $362.5 put Jan 02 → Jan 02 $362 - $0.00/share, 70% OTM

Problems:
1. "70% OTM" when actually 7.3% ITM
2. Rolling to same expiration (Jan 02 → Jan 02)
3. $0.00 debit for deep ITM roll (impossible)
4. Shows CLOSE_DONT_ROLL but still displays roll options table
```

After V2.1 (Fixed):
```
Title: 🔴 TRIPLE WITCHING: CLOSE AVGO - 7.3% ITM (Don't roll today)
Description: 2x AVGO $362.5 put Jan 02 · Currently 7.3% ITM ($26.50 intrinsic)

Fixes:
1. Shows actual "7.3% ITM" with intrinsic value
2. Skips same-week expirations
3. Validates buy_back_cost >= intrinsic value
4. Hides roll options table, shows close guidance instead
5. Displays Triple Witching execution windows and slippage expectations
```

**Validation Checks Added:**

```python
# Check 1: Buy-back cost sanity
if buy_back_cost < intrinsic_value * 0.95:
    raise Warning("Buy-back cost less than intrinsic - using corrected value")

# Check 2: PUT roll direction
if option_type == "put" and new_strike >= current_strike:
    # Force roll DOWN for puts
    max_strike = current_price * 0.98  # Below current price

# Check 3: Same-week roll prevention
if new_expiration <= current_expiration:
    skip("Cannot roll to same or earlier expiration")

# Check 4: Deep ITM roll attempt
if itm_pct > 10 and net_cost <= 0:
    raise Warning("Deep ITM roll showing credit - calculation error likely")
```

---

## 11. Questions for Review (UPDATED)

1. ~~Is the 80%/60% profit threshold appropriate for early rolls?~~ → **RESOLVED: 60% implemented**
2. Is Delta 10 (90% probability OTM) the right target for strike selection? → **KEPT as is**
3. ~~Should the cost sensitivity thresholds be adjusted?~~ → **RESOLVED: Dynamic evaluation implemented**
4. Is the ITM roll optimizer weighting correct (35% cost, 35% probability, 20% time, 10% return)?
5. ~~Are there other scenarios we should be handling?~~ → **RESOLVED: Added preemptive rolls**
6. Should we add machine learning for strike selection? → **Future V3**
7. Should we add tax optimization (wash sales, holding periods)? → **Future V3**
8. Should we add position sizing alerts? → **Future V3**

---

## Appendix A: File Locations (UPDATED)

### Backend Files

| File | Purpose |
|------|---------|
| `backend/app/modules/strategies/strategies/roll_options.py` | Main roll logic (Scenarios A, C, D) - **V2.2: ITM threshold enforcement, economic checks** |
| `backend/app/modules/strategies/strategies/early_roll_opportunity.py` | Early roll alerts |
| `backend/app/modules/strategies/strategies/sell_unsold_contracts.py` | Sell unsold calls |
| `backend/app/modules/strategies/strategies/new_covered_call.py` | New call decisions + timing |
| `backend/app/modules/strategies/strategies/earnings_alert.py` | Earnings alerts |
| `backend/app/modules/strategies/strategies/dividend_alert.py` | **NEW** - Dividend/ex-div tracking |
| `backend/app/modules/strategies/strategies/approaching_strike_alert.py` | **NEW** - Preemptive roll alerts |
| `backend/app/modules/strategies/strategies/triple_witching_handler.py` | **NEW** - Triple Witching Day handling - **V2.1: Enhanced execution guidance** |
| `backend/app/modules/strategies/technical_analysis.py` | TA calculations + momentum |
| `backend/app/modules/strategies/itm_roll_optimizer.py` | ITM roll optimization - **V2.1: PUT strike selection fix, cost validation** |
| `backend/app/modules/strategies/multi_week_optimizer.py` | **NEW** - Multi-week expiration analysis |
| `backend/app/modules/strategies/liquidity_checker.py` | **NEW** - Liquidity evaluation |
| `backend/app/modules/strategies/execution_advisor.py` | **NEW** - Execution guidance |
| `backend/app/modules/strategies/timing_optimizer.py` | **NEW** - Strategic timing (IV, Monday bump) |
| `backend/app/modules/strategies/performance_tracker.py` | **NEW** - Performance analytics |
| `backend/app/modules/strategies/recommendations.py` | Save to database |
| `backend/app/shared/services/notifications.py` | Telegram formatting |

### Frontend Files

| File | Purpose |
|------|---------|
| `frontend/src/pages/Notifications.tsx` | Notifications UI - **V2.1: Triple Witching guidance rendering, hide_roll_options support** |
| `frontend/src/pages/Notifications.module.css` | Notification styles - **V2.1: Triple Witching section styles** |

---

## Appendix B: Version History

| Version | Date | Changes |
|---------|------|---------|
| V1 | Dec 2024 | Initial algorithm with 5 core strategies |
| V2 | Dec 18, 2024 | Lowered thresholds, preemptive rolls, multi-week, liquidity, execution guidance, dividends, performance tracking |
| V2.1 | Dec 19, 2024 | Bug fixes for ITM display, PUT roll strikes, cost validation, Triple Witching UX |
| V2.2 | Dec 19, 2024 | ITM threshold enforcement, economic sanity checks, roll validation, prevent rolling into ITM |

### V2.2 Changes Summary (December 19, 2024)

**ITM Threshold Enforcement:**

1. **Added ITM Threshold Check FIRST** (`roll_options.py`)
   - New function: `should_close_itm_position_by_threshold()`
   - Runs BEFORE roll optimizer (not after)
   - Four thresholds: 20% (catastrophic), 10% (deep), 5% (normal), 3% (Triple Witching)
   - Positions exceeding thresholds get CLOSE recommendation immediately

2. **Added Economic Sanity Checks** (`roll_options.py`)
   - New function: `evaluate_roll_economics()`
   - Check 1: Roll cost must be less than close cost
   - Check 2: Savings must be $50+ per contract OR 10%+
   - Check 3: New position must be OTM (prevent rolling into ITM)

3. **Added Roll Options Validation** (`roll_options.py`)
   - New function: `validate_roll_options()`
   - Validates optimizer returns 3 distinct options
   - Checks strikes differ by at least 2%
   - Falls back to CLOSE if validation fails

4. **Added Close Recommendation Generator** (`roll_options.py`)
   - New function: `generate_close_recommendation()`
   - Creates structured CLOSE recommendations
   - Includes Triple Witching guidance when applicable
   - Shows clear explanation for why closing is recommended

**Configuration Changes (`algorithm_config.py`):**
- Added `catastrophic_itm_pct`: 20.0
- Added `deep_itm_pct`: 10.0
- Added `normal_close_threshold_pct`: 5.0
- Added `triple_witching_close_threshold_pct`: 3.0
- Added `min_roll_savings_dollars`: 50
- Added `min_roll_savings_percent`: 10
- Added `min_strike_variation_pct`: 2.0

---

### V2.1 Changes Summary (December 19, 2024)

**Bug Fixes:**

1. **ITM/OTM Status Display** (`roll_options.py`)
   - Changed from confusing "70% prob OTM" to actual ITM status
   - Now displays: `Currently {itm_pct}% ITM (${intrinsic_value} intrinsic)`
   - Clearly shows position is IN THE MONEY, not probability of staying OTM

2. **Roll Strike Selection for ITM Puts** (`itm_roll_optimizer.py`)
   - Fixed bug where ITM puts recommended rolling to SAME strike
   - Now rolls DOWN to get OTM (lower strikes = more OTM for puts)
   - For >10% ITM puts, forces new strike below current stock price
   - Example: FIG $60 PUT with stock at $39 now recommends $35-40 range, not $60

3. **Roll Cost Calculation Validation** (`itm_roll_optimizer.py`)
   - Added validation: buy_back_cost must be ≥ intrinsic value
   - Flags bad market data and uses corrected value
   - Increased max_net_debit for deep ITM positions (up to 50% of intrinsic)
   - Prevents showing $0 or credit for deep ITM rolls

4. **UX - Hide Roll Options When CLOSE_DONT_ROLL** (`triple_witching_handler.py`)
   - Added `hide_roll_options` flag when Triple Witching override recommends close
   - Frontend now hides the roll options table to avoid confusion
   - Shows close cost guidance instead

5. **Triple Witching Execution Details** (`triple_witching_handler.py`, `Notifications.tsx`)
   - Added comprehensive `triple_witching_execution` object with:
     - Best trading window (10:30 AM - 2:30 PM ET)
     - Windows to avoid (opening chaos, final hour)
     - Expected slippage ($50-150 per contract)
     - Step-by-step execution strategy
     - Close cost estimates with intrinsic value
   - Added styled UI section with color-coded window quality indicators

**Frontend Changes:**
- Added `Recommendation` interface fields for Triple Witching data
- Added `renderTripleWitchingGuidance()` function
- Added CSS styles for Triple Witching section (`.tripleWitchingSection`, window badges, etc.)

### V2.0 Changes Summary (December 18, 2024)
- Lowered profit thresholds: 80% → 60%, with earnings/DTE adjustments
- Removed end-of-week auto-roll logic (Scenario B deleted)
- Added Scenario D: Preemptive roll for approaching strikes
- Added multi-week expiration analysis (1-3 weeks)
- Added strategic timing optimization (IV-based, Monday bump, market conditions)
- Enhanced cost sensitivity with scenario comparison
- Added liquidity screening and quality checks
- Added comprehensive execution guidance system
- Added dividend/ex-dividend tracking and alerts
- Added performance tracking and analytics
- Updated priority levels and notification formats
- Added 8 new configuration parameters sections
- Added 7 new Python modules

### V1.0 (Original - December 2024)
- Initial implementation with 5 core strategies
- 80% profit threshold
- Delta 10 strike selection
- Basic ITM roll optimizer
- Earnings awareness
- Simple cost sensitivity checks

