# Options Selling Strategies

This document consolidates all options selling strategy documentation including put options basics, delta guidelines, available strategies, and approaches for limited capital.

**Related Documentation:**
- [Notifications & Scheduler](./NOTIFICATIONS.md) - How to set up Telegram, scheduling, and testing
- [Notification Algorithm V2](./OPTIONS-NOTIFICATION-ALGORITHM-V2.md) - Active algorithm specification for each strategy
- [Notification Algorithm V1](./OPTIONS-NOTIFICATION-ALGORITHM-V1.md) - Original algorithm (deprecated)

## Table of Contents

1. [Put Options Basics](#put-options-basics)
2. [Understanding Delta](#understanding-delta)
3. [Stock Selection Criteria](#stock-selection-criteria)
4. [Strategies with Limited Cash](#strategies-with-limited-cash)
5. [Available Strategies](#available-strategies)

---

## Put Options Basics

### Selling vs Buying Puts

#### When You SELL a Put Option

- You **collect** a premium (money comes TO you)
- You take on an **obligation** (you MUST buy if asked)

**Example: Sell AAPL $150 Put for $3.00**
- You receive: **$300** ($3.00 × 100 shares)
- Your obligation: If AAPL drops below $150, you MUST buy 100 shares at $150

**What you're betting:**
- ✅ AAPL will stay **ABOVE $150** (you keep the $300, no purchase needed)
- ❌ AAPL drops **BELOW $150** (you must buy 100 shares at $150)

**Capital required:**
- Cash-secured: Strike × 100 (e.g., $15,000 for a $150 put)
- Margin: ~20-25% of strike (e.g., $3,000-3,750)

#### When You BUY a Put Option

- You **pay** a premium (money goes FROM you)
- You get a **right** (you CAN sell if you want, but don't have to)

**Example: Buy AAPL $145 Put for $1.50**
- You pay: **$150** ($1.50 × 100 shares)
- Your right: If AAPL drops below $145, you CAN sell 100 shares at $145

### Bull Put Spread (Combining Both)

**The Strategy:**
- **Sell** AAPL $150 put for $3.00 (collect $300)
- **Buy** AAPL $145 put for $1.50 (pay $150)
- **Net credit: $1.50** ($150 comes to you)

**What you're betting:**
- AAPL stays **ABOVE $150** (best case - both puts expire worthless, you keep $150)

**Outcomes at different prices:**

| AAPL Price | $150 Put | $145 Put | Result |
|------------|----------|----------|--------|
| $160 (above $150) ✅ | Expires worthless | Expires worthless | **+$150 profit** |
| $148 (between) | ITM - buy at $150 | Can sell at $145 | **-$350 loss** |
| $140 (below $145) ❌ | ITM - buy at $150 | ITM - sell at $145 | **-$350 max loss** |

**Capital required:** Only $500 (spread width) vs $15,000 for cash-secured!

### Key Differences Summary

| Action | Money Flow | Obligation/Right | What You Want | Capital Needed |
|--------|-----------|------------------|---------------|----------------|
| **SELL Put** | TO you | Must BUY if assigned | Stock ABOVE strike | Strike × 100 |
| **BUY Put** | FROM you | Can SELL if profitable | Stock BELOW strike | Just premium |
| **Bull Put Spread** | Net TO you | Buy high, sell low | Stock ABOVE high strike | Spread width × 100 |

---

## Understanding Delta

### What Delta Means for Puts

**Delta for puts:**
- Negative values (puts have negative delta)
- Absolute value increases as strike goes deeper ITM
- Delta -0.10 = 10% likely to be ITM
- Delta -0.80 = 80% likely to be ITM

### Converting "Chance of Profit" to Delta

Many brokers show "Chance of Profit" instead of delta. Here's how they relate:

| Chance of Profit | Assignment Risk | Approx Delta |
|-----------------|-----------------|--------------|
| 90-95% | 5-10% | Delta ~0.05-0.10 |
| 80-85% | 15-20% | Delta ~0.15-0.20 |
| 70-75% | 25-30% | Delta ~0.25-0.30 |

### Delta Selection for Selling Puts

**Delta 5-10 (Very Safe):**
- ~5-10% chance of assignment
- Strike well below current price
- Low premium, very safe
- Example: AAPL $267.5 put when stock is $277

**Delta 15-20 (Recommended):**
- ~15-20% chance of assignment
- Strike moderately below current price
- Good premium, reasonable risk
- Example: AAPL $272.5 put when stock is $277

**Delta 25-30 (Aggressive):**
- ~25-30% chance of assignment
- Strike close to current price
- High premium, higher risk
- Example: AAPL $275 put when stock is $277

### For Bull Put Spreads

**Sell Strike (High):** Delta 15-20
- Look for "Chance of profit: 80-85%"

**Buy Strike (Low/Protective):** Delta 5-10
- Look for "Chance of profit: 90-95%"

### Time to Expiration Matters

- **21-45 day options (Recommended):** Better premiums, more time for stock to move in your favor
- **2-7 day options:** Very low premiums, not worth the risk
- **45+ day options:** Higher premiums but more time exposure

---

## Stock Selection Criteria

### 1. Volatility (IV Rank/Percentile)

**What you want:**
- **IV Rank > 50%** (premiums are expensive, good for selling)
- **IV Rank 30-70%** is the sweet spot
- Higher IV = More premium collected

### 2. Price Action / Technical Levels

**Best scenarios (in order of preference):**

1. **Range-Bound / Sideways** ⭐ BEST
   - Stock bounces between support and resistance
   - Example: AAPL trading between $140-$160 for months

2. **Slowly Rising / Bullish** ✅ GOOD
   - Stock trending up gradually
   - Stock moves away from your put strike

3. **Volatile with Strong Support** ✅ GOOD
   - Stock swings up and down but has clear support level
   - Set puts below support to collect premium safely

**Avoid:**
- ❌ Strong downward trend
- ❌ Low volatility / stagnant (premiums too low)
- ❌ Earnings or major events coming

### 3. Support Levels

**What you want:**
- Clear support level below current price
- Stock has bounced off support multiple times
- Support is 5-15% below current price

**Example:**
- AAPL at $155, Support at $145 (tested 3 times)
- Set put spread: Sell $150 / Buy $145
- Support acts as safety net

### 4. Liquidity

**What you want:**
- High option volume (easy to enter/exit)
- Tight bid-ask spreads (< $0.10)
- Multiple expiration dates available

### 5. Stock Quality

- Stocks you'd be comfortable owning (if assigned)
- Strong fundamentals (won't crash 50% overnight)
- Not meme stocks or near-bankruptcy companies

### Decision Framework

**Step 1: Is the Stock Suitable?**
- ✅ IV Rank > 50%?
- ✅ Clear support level?
- ✅ Stock you'd own?
- ✅ Liquid options?

**Step 2: Choose Your Delta**
- Conservative: Sell Delta 15, Buy Delta 5
- Moderate (Recommended): Sell Delta 20, Buy Delta 10
- Aggressive: Sell Delta 25-30, Buy Delta 15-20

**Step 3: Set Spread Width**
- Narrow ($3-5): Less capital, less risk, lower premium
- Medium ($5-7): Balanced, recommended starting point
- Wide ($7-10): More capital, more risk, higher premium

**Step 4: Calculate Risk/Reward**
- Max Profit = Net Credit Received
- Max Loss = Spread Width - Net Credit
- Target: At least 1:1 risk/reward

---

## Strategies with Limited Cash

### Problem: Traditional Cash-Secured Put Capital Requirements

- Sell 1 AAPL $150 put = $15,000 cash required
- Sell 1 TSLA $200 put = $20,000 cash required

### Solution 1: Bull Put Spreads ⭐ RECOMMENDED

**How it works:**
- Sell a put at higher strike (collect premium)
- Buy a put at lower strike (limits risk)
- Capital required = Spread width × 100

**Example:**
- Sell AAPL $150 put for $3.00
- Buy AAPL $145 put for $1.50
- Net credit: $1.50 ($150 per contract)
- **Capital required: $500** vs $15,000 for cash-secured (97% less!)
- Max loss: $350 ($500 - $150 credit)

**Benefits:**
- Much less capital required
- Defined risk (know max loss upfront)
- Still generates income

### Solution 2: Lower-Priced Stocks

Focus on stocks with lower strike prices:
- HOOD $10 put = $1,000 cash required
- PLTR $15 put = $1,500 cash required
- SOFI $8 put = $800 cash required

### Solution 3: Hybrid Approach

Combine based on cash availability:
- Use available cash for lower-priced stocks (cash-secured)
- Use spreads for higher-priced stocks (defined risk)

### Capital Requirements Comparison

| Strategy | AAPL $150 Put | Capital | Max Profit | Max Loss |
|----------|---------------|---------|-----------|----------|
| Cash-Secured Put | Sell $150 put | $15,000 | $300 | $14,700 |
| Bull Put Spread | Sell $150/$145 | $500 | $150 | $350 |
| Naked Put (Margin) | Sell $150 put | ~$3,500 | $300 | Unlimited* |

---

## Available Strategies

> **📋 For detailed algorithm logic**, see [Notification Algorithm V2](./OPTIONS-NOTIFICATION-ALGORITHM-V2.md)

### Currently Implemented

1. **Roll Options** ✅ - Handles ITM rolls, early rolls (80%+ profit), end-of-week rolls
2. **Early Roll Opportunities** ✅ - Proactive alerts at profit threshold (80% normal, 60% during earnings)
3. **Sell Unsold Contracts** ✅ - Identifies shares that could generate covered call income
4. **New Covered Call** ✅ - Determines when to sell new calls (now vs wait for bounce)
5. **Earnings Alert** ✅ - Heads-up for positions with earnings within 5 days

### Recommended to Add (By Priority)

#### Phase 1: Immediate Value

**Cash-Secured Put Strategy**
- Category: Income Generation
- Identifies opportunities to sell puts on stocks you want to own
- Parameters: min_premium, strike_offset_percent (5-10% OTM), min_days_to_expiry (21-45)

**The Wheel Strategy**
- Category: Income Generation
- Automated rotation between selling cash-secured puts and covered calls
- If assigned on put → sell covered calls
- If called away → sell puts again

#### Phase 2: Enhanced Income

**IV Rank Strategy**
- Category: Optimization
- Recommend selling when IV rank > 70 (premiums expensive)
- Recommend closing when IV rank < 30 (premiums cheap)

**Credit Spread Strategy**
- Category: Income Generation
- Sells credit spreads with 70-80% probability of profit
- Defined risk income generation

#### Phase 3: Risk Management

**Delta Management Strategy**
- Category: Optimization
- Monitors portfolio delta and recommends adjustments
- Maintain target delta exposure

**Collar Strategy**
- Category: Risk Management
- Protects positions with significant gains
- Adds protective puts, sells calls to finance them

#### Phase 4: Advanced

**Poor Man's Covered Call (PMCC)**
- Uses LEAPS instead of owning stock
- Much more capital efficient

**Iron Condor Strategy**
- Sells both call and put credit spreads
- Works in range-bound markets

**Calendar Spread Strategy**
- Sells short-term options, buys longer-term
- Profits from time decay difference

---

## Strategy Selection Criteria

When implementing new strategies, consider:

1. **Data Requirements**
   - IV rank/percentile (requires historical IV data)
   - Delta calculations (requires option chain data)
   - Dividend dates (requires corporate action data)

2. **Complexity**
   - Cash-secured puts: Simple
   - Credit spreads: Medium
   - Iron condors: Complex

3. **Capital Requirements**
   - Covered calls: Own stock
   - Cash-secured puts: Cash collateral
   - Spreads: Defined risk (lower capital)

4. **Risk Profile**
   - Income strategies: Moderate risk
   - Risk management: Lower risk
   - Advanced strategies: Higher complexity

---

*Last Updated: December 2025*

