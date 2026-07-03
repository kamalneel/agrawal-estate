# N-Rank Algorithm Specification

## Overview

N-Rank (Neel Rank) is a proprietary scoring system (0-100) for evaluating Indian mutual funds. It measures funds across 5 key dimensions to identify strong performers while penalizing poor risk-adjusted returns and deteriorating funds.

**Current Version:** v3 (Aggressive Wealth Transfer Strategy)

**Implementation:** `frontend/src/pages/IndiaInvestments.tsx`

---

## Scoring Dimensions Summary

| Dimension | Max Points | Min Points | Weight |
|-----------|------------|------------|--------|
| Quality | 20 | 0 | 20% |
| Returns | 50 | -20 | 50% |
| Risk-Adjusted | 15 | -10 | 15% |
| Cost | 5 | -3 | 5% |
| Strategic Fit | 10 | 0 | 10% |
| **TOTAL** | 100 | -33 | 100% |

---

## Dimension 1: Quality (20 points max)

Measures fund house credibility, size, and track record.

### A. Value Research Rating (10 points)

| Rating | Points |
|--------|--------|
| ★★★★★ (5 stars) | 10 |
| ★★★★ (4 stars) | 7 |
| ★★★ (3 stars) | 4 |
| ★★ (2 stars) | 2 |
| ★ (1 star) | 0 |

### B. AUM Size (7 points)

Avoid extremes, reward sweet spot:

| AUM Range | Points | Rationale |
|-----------|--------|-----------|
| < ₹500 Cr | 0 | Too small, closure risk |
| ₹500 - 2,000 Cr | 2 | Small but acceptable |
| ₹2,000 - 10,000 Cr | 5 | Good size |
| ₹10,000 - 50,000 Cr | 7 | **OPTIMAL** - proven & agile |
| > ₹50,000 Cr | 5 | Very large, less agile |

### C. Fund Age / Track Record (3 points)

| Fund Age | Points | Rationale |
|----------|--------|-----------|
| < 3 years | 0 | Unproven |
| 3-5 years | 1 | Moderate track record |
| 5-10 years | 2 | Good track record |
| > 10 years | 3 | Proven through cycles |

---

## Dimension 2: Returns (50 points max, -20 min)

**PRIMARY dimension for aggressive strategy** - emphasizes recent performance and long-term consistency.

### A. 1-Year Return (15 to -10 points)

| 1Y Return | Points |
|-----------|--------|
| > 30% | 15 |
| 20% - 30% | 12 |
| 15% - 20% | 9 |
| 10% - 15% | 6 |
| 5% - 10% | 3 |
| 0% - 5% | 0 |
| -5% - 0% | **-5** |
| < -5% | **-10** |

### B. 3-Year Return (20 to -5 points)

| 3Y Return | Points |
|-----------|--------|
| > 30% | 20 |
| 25% - 30% | 16 |
| 20% - 25% | 12 |
| 15% - 20% | 8 |
| 10% - 15% | 4 |
| 5% - 10% | 0 |
| < 5% | **-5** |

### C. 5-Year Return (15 to -5 points)

| 5Y Return | Points |
|-----------|--------|
| > 25% | 15 |
| 20% - 25% | 12 |
| 15% - 20% | 8 |
| 10% - 15% | 4 |
| 5% - 10% | 0 |
| < 5% | **-5** |

### D. Momentum Check (0 to -5 points)

Penalizes funds that are deteriorating (recent returns much worse than historical).

| Condition | Penalty |
|-----------|---------|
| 1Y < 3Y by > 20 percentage points | **-5** |
| 1Y < 3Y by 15-20 percentage points | **-3** |
| 1Y < 3Y by 10-15 percentage points | **-2** |
| Otherwise | 0 |

**Example:** Fund with 3Y=22% but 1Y=-6% → Gap is 28pp → **-5 penalty**

---

## Dimension 3: Risk-Adjusted Performance (15 points max, -10 min)

**Reduced weight from earlier versions** - aggressive strategy tolerates volatility.

### A. Sharpe Ratio (10 to -5 points)

| Sharpe Value | Points |
|--------------|--------|
| > 1.5 | 10 |
| 1.0 - 1.5 | 8 |
| 0.7 - 1.0 | 6 |
| 0.5 - 0.7 | 4 |
| 0.3 - 0.5 | 2 |
| 0 - 0.3 | 0 |
| -0.5 - 0 | **-2** |
| < -0.5 | **-5** |

### B. Alpha (7 to -5 points)

| Alpha | Points |
|-------|--------|
| > 7% | 7 |
| 5% - 7% | 5 |
| 3% - 5% | 4 |
| 1% - 3% | 2 |
| 0% - 1% | 1 |
| -3% - 0% | **-2** |
| < -3% | **-5** |

### C. Volatility (penalty only for extreme, -2 max)

| Volatility (Std Dev) | Points |
|----------------------|--------|
| < 20% | 0 |
| 20% - 25% | **-1** |
| > 25% | **-2** |

---

## Dimension 4: Cost Efficiency (5 points max, -3 min)

**Reduced weight** - performance matters more than fees for aggressive strategy.

| Expense Ratio | Points |
|---------------|--------|
| < 0.5% | 5 |
| 0.5% - 0.75% | 4 |
| 0.75% - 1.0% | 3 |
| 1.0% - 1.5% | 2 |
| 1.5% - 2.0% | 0 |
| > 2.0% | **-3** |

---

## Dimension 5: Strategic Fit (10 points max)

Rewards funds that add diversification to portfolio.

### A. Sector Diversification Bonus (5 points)

| Sector Type | Points | Rationale |
|-------------|--------|-----------|
| US Tech / FAANG / Nasdaq | +5 | High growth, international exposure |
| Healthcare / Pharma | +4 | Defensive + growth |
| International (non-US) | +4 | Geographic diversification |
| Consumption / FMCG | +3 | Steady growth |
| Infrastructure | +2 | India growth story |
| Banking / Financial | 0 | Already over-allocated in typical portfolios |

### B. Direct Plan Bonus (2 points)

| Plan Type | Points |
|-----------|--------|
| Direct Plan | +2 |
| Regular Plan | 0 |

### C. Clean NAV History (3 points)

| History | Points |
|---------|--------|
| 10+ years clean | +3 |
| 5-10 years | +2 |
| 3-5 years | +1 |
| < 3 years | 0 |

---

## Tier Classification

| Tier | Score | Action |
|------|-------|--------|
| 🟢 **Excellent** | 60+ | Strong buy / increase allocation |
| 🟡 **Good** | 45-59 | Hold / consider buying |
| 🟠 **Caution** | 30-44 | Monitor / consider reducing |
| 🔴 **Poor** | < 30 | Sell / avoid |

---

## Fund Filtering (Pre-Scoring)

Eliminate funds before scoring if ANY condition is met:

1. VR Rating < ★★★ (below 3 stars)
2. AUM < ₹500 Cr (closure risk)
3. Expense Ratio > 2.5% for International OR > 1.5% for Indian
4. 3Y CAGR < 0% (negative returns)
5. Alpha < -2 (significantly underperforming)
6. Fund Age < 3 years (unless exceptional performance)

---

## Ranking & Selection Logic

### Step 1: Filter
Apply pre-filtering rules above to eliminate poor funds.

### Step 2: Score
Calculate N-Rank for all remaining funds.

### Step 3: Category Balancing
Ensure diversification:

**If selecting 3 funds:**
- Maximum 2 from same category
- Prefer mix of: Indian Equity + International + Different sub-categories

**If selecting 5+ funds:**
- Maximum 3 from same category
- Ensure at least 2 different geographies

### Step 4: Rank

1. **Rank #1 (Foundation Fund):**
   - Highest N-Rank score
   - Must be 5-star OR have Sharpe > 1.0
   - Preference: Stability + Consistency
   - *"Core holding - must be rock solid"*

2. **Rank #2 (Efficiency Fund):**
   - Next highest score
   - Different category from #1
   - Highest Sharpe Ratio among remaining
   - *"Best risk-adjusted returns to complement core"*

3. **Rank #3 (Growth/Opportunity Fund):**
   - High score (top 5)
   - Meets specific requirement (e.g., US tech exposure)
   - Can be higher volatility if returns justify
   - Must add diversification
   - *"Capture specific growth opportunity"*

---

## Allocation Logic

```python
def calculate_allocation(selected_funds):
    """Determine % allocation for top 3 funds"""
    
    rank_1_score = selected_funds[0].neel_score
    rank_2_score = selected_funds[1].neel_score
    rank_3_score = selected_funds[2].neel_score
    
    total_score = rank_1_score + rank_2_score + rank_3_score
    
    # Proportional allocation with constraints
    # Rank 1: 35-45%, Rank 2: 30-40%, Rank 3: remainder
    allocation_1 = max(35, min(45, (rank_1_score / total_score) * 100))
    allocation_2 = max(30, min(40, (rank_2_score / total_score) * 100))
    allocation_3 = 100 - allocation_1 - allocation_2
    
    # Round to nearest 5%
    allocation_1 = round(allocation_1 / 5) * 5
    allocation_2 = round(allocation_2 / 5) * 5
    allocation_3 = 100 - allocation_1 - allocation_2
    
    return [allocation_1, allocation_2, allocation_3]
```

---

## Portfolio Health Analysis

**Note:** These metrics apply to the PORTFOLIO, not individual funds.

### Sector Concentration Risk

```
DANGER: Any sector > 25% of portfolio
WARNING: Any sector > 20% of portfolio
OPTIMAL: No sector > 15% of portfolio
```

### Target Sector Allocation

| Sector | Target | Notes |
|--------|--------|-------|
| Technology | 15-20% | Missing from most portfolios |
| Healthcare | 5-10% | Defensive + growth |
| International | 20-25% | Geographic diversification |
| Consumption | 5-10% | Steady growth |
| Banking | 15-20% | Often over-allocated |

### Portfolio Diversification Score

```
Score = 100 - (Concentration Penalty + Missing Sector Penalty)

Concentration Penalty:
- Each sector > 25%: -20 points
- Each sector > 20%: -10 points

Missing Sector Penalty:
- Tech missing: -15 points
- International missing: -15 points
- Healthcare missing: -5 points
```

---

## Handling Missing Data

| Data Point | Handling |
|------------|----------|
| Missing VR Rating | 0 points (neutral) |
| Missing AUM | 0 points (neutral) |
| Missing Sharpe | 0 points (neutral, not penalty) |
| Missing Alpha | 0 points (neutral, not penalty) |
| Missing Returns | 0 points for that component |
| Missing Expense | Assume 1% (mid-range penalty) |

**Rationale:** Missing data should be neutral, not penalized. Only known bad data gets penalties.

---

## Key Principles

1. **Performance First:** 50% weight on returns emphasizes growth for aggressive strategy
2. **Penalize Bad Metrics:** Negative Sharpe/Alpha get penalties, not neutral scores
3. **Recent Performance Matters:** 1Y returns and momentum checks catch deteriorating funds
4. **Diversification Rewards:** Sector bonuses encourage portfolio balance
5. **Cost Conscious:** Lower expenses compound to better returns
6. **Quality Baseline:** Filters ensure minimum quality standards
7. **User Intent:** Category fit can override pure scoring when goals are specific

---

## Data Sources Priority

1. **Kuvera API** (primary): Sharpe, Alpha, Volatility, Returns
2. **MF API** (secondary): NAV, Scheme Code, Basic info
3. **Value Research** (rating): VR Rating stars

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | Dec 2024 | Initial algorithm - 5 dimensions, no penalties for negative metrics |
| v2.0 | Dec 2024 | Added penalties for negative Sharpe/Alpha, 1Y returns, momentum check |
| v3.0 | Dec 2024 | Aggressive strategy weights (50% returns), sector bonuses, portfolio-level analysis |

### v1 Issues (Fixed in v2+)

- Negative Sharpe Ratio got 0 points instead of penalty
- Negative Alpha got 0 points instead of penalty  
- 1Y return completely ignored
- No momentum/consistency check
- Expense penalty too weak (max 10 points)

### v2 → v3 Changes

| Aspect | v2 | v3 | Rationale |
|--------|----|----|-----------|
| 1Y Return Weight | 8 pts | 15 pts | Emphasize recent performance |
| 3Y Return Weight | 10 pts | 20 pts | Primary performance metric |
| 5Y Return Weight | 7 pts | 15 pts | Long-term consistency |
| Volatility Penalty | Up to -5 | Reduced to -2 max | Tolerate volatility for aggressive strategy |
| Sharpe Weight | 15 pts | 10 pts | Less important for aggressive strategy |
| Expense Weight | 15 pts | 5 pts | Minor factor |
| Sector Bonus | N/A | +5 pts | Reward diversification |
| Direct Plan Bonus | N/A | +2 pts | Tax efficiency |

