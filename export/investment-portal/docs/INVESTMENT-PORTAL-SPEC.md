# Investment Portal for Parents - Project Specification

**Domain:** `investment.nagendraandretha.com`
**Purpose:** Read-only investment dashboard for parents (Nagendra Prasad Agrawal & Rita Devi) to view their mutual fund portfolios, metrics, and recommendations.
**Created:** March 2026
**Author:** Neel Kamal Agrawal

---

## Background & Motivation

The main Agrawal Estate Planner application runs locally and is not hosted online. However, my parents (age 70+, based in India) need access to their portfolio analysis, fund metrics, and recommendations. This portal extracts the relevant India mutual fund data from the estate planner and presents it in a simple, accessible web application.

The parents are not tech-savvy. The UI must be extremely simple, use large fonts, and explain financial concepts using real-world analogies (like real estate/rental properties).

---

## Architecture

### Tech Stack (Recommended)
- **Frontend:** Next.js or Vite + React (static site preferred for cost)
- **Hosting:** Vercel or Netlify (free tier sufficient)
- **Data:** Static JSON/CSV files (no backend database needed - data is updated manually by Neel)
- **Domain:** `investment.nagendraandretha.com` (subdomain of existing `nagendraandretha.com`)

### Why Static?
- Data changes infrequently (monthly updates at most)
- No user authentication needed (only family views this)
- Zero hosting cost
- No server to maintain
- Neel pushes data updates via git, site auto-deploys

---

## Data Files

All data lives in the `/data` directory. These CSV files are the source of truth:

### 1. Father's Portfolio: `np_agrawal_portfolio_metrics.csv`
**Owner:** Nagendra Prasad Agrawal
**Holdings:** 20 mutual funds + PPF
**Total Invested:** ~INR 1,14,61,687
**Total Value (Mar 2025):** ~INR 2,24,80,987

**Columns:**
| Column | Description |
|--------|-------------|
| # | Serial number |
| Fund Name | Full fund name |
| Category | Fund category (Large Cap, Mid Cap, Sectoral, etc.) |
| Folio | Folio number with fund house |
| Investment Date | Date of first investment |
| Years Held | Duration of holding |
| Invested (INR) | Total amount invested |
| Mar 2025 Value | Valuation as of March 2025 |
| Current Value | Latest known valuation |
| Gain/Loss | Absolute gain or loss |
| Gain % | Percentage gain |
| 1Y Return % | Fund's 1-year return (fund-level, not personal) |
| 3Y Return % | Fund's 3-year CAGR |
| 5Y Return % | Fund's 5-year CAGR |
| AUM (Cr) | Assets Under Management in Crores |
| Expense Ratio % | Annual fee charged by fund |
| Star Rating | Value Research / Tickertape rating |
| Volatility % | Standard deviation of returns |
| Sharpe Ratio | Risk-adjusted return metric |
| Alpha % | Excess return vs benchmark |
| Beta | Market sensitivity (mostly N/A) |
| CRISIL Risk | Risk classification |
| N-Rank Score | Proprietary scoring (0-100) |
| N-Rank Tier | Excellent/Good/Caution/Poor |

### 2. Mother's Portfolio: `rita_agrawal_portfolio_metrics.csv`
**Owner:** Rita Devi (Rita Grover)
**Holdings:** 36 funds (including PPF, SCSS, 2 Sahara funds with no valuation)
**Total Invested:** ~INR 1,49,93,400
**Total Value (Mar 2025):** ~INR 2,22,37,474

**Columns:** Same as Father's portfolio (except no N-Rank Score/Tier columns yet).

**Special Notes:**
- PPF (row 1) and SCSS (row 35) are government schemes with guaranteed returns
- Sahara Fund 1 & 2 (rows 3, 12) have no valuation (fund house issues)
- UTI ULIP (row 6) is an insurance product, not a mutual fund
- Franklin IDCW funds (rows 9, 17) show low NAV returns because dividends are paid out, reducing NAV
- All funds are Regular Plan (through advisor Abhay Kumar)

### 3. Mother's Raw Holdings: `rita_holdings.csv`
Original holdings data with investment tranches and notes. Use for reference on multi-tranche investments.

### 4. Recommended Funds: `recommended_funds_metrics.csv`
**Purpose:** Research-backed fund recommendations for future investments
**Count:** 24 funds ranked by N-Rank recommendation score

**Columns:**
| Column | Description |
|--------|-------------|
| Rank | Position in recommendation ranking |
| Fund Name | Full fund name |
| Fund House | AMC name |
| Category | Fund category |
| Scheme Code | AMFI scheme code (for API lookups) |
| Recommendation Score | N-Rank score (0-100) |
| NAV | Latest NAV |
| NAV Date | Date of NAV |
| 1Y/3Y/5Y/10Y Return % | Historical returns |
| AUM (Cr) | Fund size |
| Expense Ratio % | Annual fee |
| VR Rating (Stars) | Value Research star rating |
| Volatility % | Standard deviation |
| Sharpe Ratio | Risk-adjusted return |
| Alpha % | Excess return vs benchmark |
| Beta | Market sensitivity |
| Notes | Human-readable commentary |

---

## Educational Content

### 5. Mutual Fund Guide: `MUTUAL-FUND-GUIDE-FOR-PARENTS.md`
A comprehensive guide explaining mutual fund concepts to 70+ year old parents using real estate analogies:
- What is a mutual fund (compared to buying a flat in a colony)
- NAV explained as "price per square foot"
- Expense ratio as "society maintenance charges"
- Returns as "rental yield"
- Risk categories as "location risk"
- When to sell vs hold

### 6. Father's Practice Guide: `FATHER-PORTFOLIO-PRACTICE-GUIDE.md`
Detailed walkthrough of each of Father's 20 funds:
- For each fund: metrics table, plain-language explanation, step-by-step N-Rank calculation, verdict
- Portfolio summary with strengths, concerns
- Top 5 and bottom 5 funds by N-Rank
- Practice exercises

### 7. N-Rank Algorithm: `N-RANK-ALGORITHM.md`
The proprietary scoring algorithm specification:
- 5 dimensions: Quality (20%), Returns (50%), Risk-Adjusted (15%), Cost (5%), Strategic Fit (10%)
- Scoring tables for each metric
- Tier classification: Excellent (60+), Good (45-59), Caution (30-44), Poor (<30)
- Pre-filtering rules

---

## Pages & Features

### Page 1: Home / Dashboard
- Welcome message
- Summary cards:
  - Father's Portfolio: Total invested, Total value, Overall gain %
  - Mother's Portfolio: Total invested, Total value, Overall gain %
  - Combined family wealth in mutual funds
- Navigation to individual portfolios

### Page 2: Father's Portfolio (NP Agrawal)
- Portfolio summary header (total invested, current value, gain)
- Table of all 20 holdings with key columns:
  - Fund Name, Category, Invested, Current Value, Gain %, 1Y Return, Sharpe, N-Rank Score, N-Rank Tier
- Color coding: Green for Excellent, Yellow for Good, Orange for Caution, Red for Poor
- Click on fund to expand and see all metrics
- Portfolio health indicators:
  - Sector concentration chart (pie chart)
  - Average N-Rank score
  - Top 5 / Bottom 5 funds

### Page 3: Mother's Portfolio (Rita Devi)
- Same layout as Father's portfolio
- Note about Regular Plan vs Direct Plan
- Flag IDCW funds with explanation about dividend payout affecting NAV returns
- Flag Sahara funds as "unavailable"

### Page 4: Recommendations
- Table of 24 recommended funds ranked by score
- Columns: Rank, Fund Name, Category, Score, 1Y/3Y/5Y Returns, Sharpe, Alpha, Beta, AUM, Expense Ratio
- Color coding by tier (same as portfolio pages)
- Notes column visible
- Filter by category

### Page 5: Learn (Educational)
- Render the Mutual Fund Guide content
- Simple, large-font layout
- Real estate analogies prominently displayed
- Glossary of terms

### Page 6: N-Rank Calculator (Optional/Advanced)
- Interactive tool to understand how N-Rank works
- Input fund metrics, see score breakdown
- Educational purpose

---

## Design Requirements

### Accessibility (Critical - users are 70+ years old)
- **Font size:** Minimum 18px body, 24px+ headers
- **Contrast:** High contrast (dark text on light background)
- **Language:** Simple English with Hindi terms where appropriate (e.g., "Crore", "Lakh")
- **Colors:** Use traffic light metaphor (green = good, red = bad)
- **Mobile-first:** Parents primarily use phones
- **No login required:** Public but obscure URL

### Currency Formatting
- Always INR with Indian number formatting: 1,00,000 (not 100,000)
- Use "Cr" for Crores, "L" for Lakhs
- Show values in Lakhs when > 1L (e.g., "17.34L" instead of "17,34,443")

### Data Freshness
- Show "Data as of: March 2025" prominently
- Last updated timestamp on each page
- Note: "Portfolio data is updated periodically by Neel"

---

## N-Rank Algorithm Implementation

The N-Rank scoring should be implemented in the frontend (JavaScript/TypeScript). Here is the complete algorithm:

### Dimension 1: Quality (20 points max)

```javascript
function scoreQuality(fund) {
  let score = 0;

  // A. Star Rating (10 points)
  const starPoints = { 5: 10, 4: 7, 3: 4, 2: 2, 1: 0 };
  score += starPoints[fund.starRating] || 0;

  // B. AUM Size (7 points)
  const aum = fund.aumCr;
  if (aum >= 10000 && aum <= 50000) score += 7;      // Optimal
  else if (aum >= 2000 && aum < 10000) score += 5;    // Good
  else if (aum > 50000) score += 5;                    // Very large
  else if (aum >= 500 && aum < 2000) score += 2;      // Small
  // else 0 (< 500 Cr)

  // C. Fund Age (3 points)
  const years = fund.yearsHeld;
  if (years > 10) score += 3;
  else if (years >= 5) score += 2;
  else if (years >= 3) score += 1;

  return score;
}
```

### Dimension 2: Returns (50 points max, -20 min)

```javascript
function scoreReturns(fund) {
  let score = 0;

  // A. 1Y Return (15 to -10)
  const r1y = fund.return1Y;
  if (r1y > 30) score += 15;
  else if (r1y >= 20) score += 12;
  else if (r1y >= 15) score += 9;
  else if (r1y >= 10) score += 6;
  else if (r1y >= 5) score += 3;
  else if (r1y >= 0) score += 0;
  else if (r1y >= -5) score -= 5;
  else score -= 10;

  // B. 3Y Return (20 to -5)
  const r3y = fund.return3Y;
  if (r3y > 30) score += 20;
  else if (r3y >= 25) score += 16;
  else if (r3y >= 20) score += 12;
  else if (r3y >= 15) score += 8;
  else if (r3y >= 10) score += 4;
  else if (r3y >= 5) score += 0;
  else score -= 5;

  // C. 5Y Return (15 to -5)
  const r5y = fund.return5Y;
  if (r5y > 25) score += 15;
  else if (r5y >= 20) score += 12;
  else if (r5y >= 15) score += 8;
  else if (r5y >= 10) score += 4;
  else if (r5y >= 5) score += 0;
  else score -= 5;

  // D. Momentum Check (0 to -5)
  if (r1y !== null && r3y !== null) {
    const gap = r3y - r1y;
    if (gap > 20) score -= 5;
    else if (gap > 15) score -= 3;
    else if (gap > 10) score -= 2;
  }

  return score;
}
```

### Dimension 3: Risk-Adjusted (15 points max, -10 min)

```javascript
function scoreRiskAdjusted(fund) {
  let score = 0;

  // A. Sharpe Ratio (10 to -5)
  const sharpe = fund.sharpeRatio;
  if (sharpe !== null) {
    if (sharpe > 1.5) score += 10;
    else if (sharpe >= 1.0) score += 8;
    else if (sharpe >= 0.7) score += 6;
    else if (sharpe >= 0.5) score += 4;
    else if (sharpe >= 0.3) score += 2;
    else if (sharpe >= 0) score += 0;
    else if (sharpe >= -0.5) score -= 2;
    else score -= 5;
  }

  // B. Alpha (7 to -5) - NOTE: Tickertape alpha uses trailing methodology
  // Values like -55% are anomalous for sector funds. Use with caution.
  const alpha = fund.alpha;
  if (alpha !== null) {
    if (alpha > 7) score += 7;
    else if (alpha >= 5) score += 5;
    else if (alpha >= 3) score += 4;
    else if (alpha >= 1) score += 2;
    else if (alpha >= 0) score += 1;
    else if (alpha >= -3) score -= 2;
    else score -= 5;
  }

  // C. Volatility penalty (-2 max)
  const vol = fund.volatility;
  if (vol !== null) {
    if (vol > 25) score -= 2;
    else if (vol > 20) score -= 1;
  }

  return score;
}
```

### Dimension 4: Cost (5 points max, -3 min)

```javascript
function scoreCost(fund) {
  const er = fund.expenseRatio;
  if (er === null) return 2; // Assume mid-range
  if (er < 0.5) return 5;
  if (er < 0.75) return 4;
  if (er < 1.0) return 3;
  if (er < 1.5) return 2;
  if (er < 2.0) return 0;
  return -3;
}
```

### Dimension 5: Strategic Fit (10 points max)

```javascript
function scoreStrategicFit(fund) {
  let score = 0;

  // A. Sector bonus (5 points)
  const category = fund.category.toLowerCase();
  if (category.includes('nasdaq') || category.includes('us tech') || category.includes('fang')) score += 5;
  else if (category.includes('healthcare') || category.includes('pharma')) score += 4;
  else if (category.includes('europe') || category.includes('global') || category.includes('international')) score += 4;
  else if (category.includes('consumption') || category.includes('fmcg')) score += 3;
  else if (category.includes('infrastructure') || category.includes('manufacturing')) score += 2;
  // Banking/Financial: 0

  // B. Direct Plan bonus (2 points)
  if (fund.name.toLowerCase().includes('direct')) score += 2;

  // C. Clean history (3 points)
  const years = fund.yearsHeld;
  if (years > 10) score += 3;
  else if (years >= 5) score += 2;
  else if (years >= 3) score += 1;

  return score;
}
```

### Total N-Rank & Tier

```javascript
function calculateNRank(fund) {
  const quality = scoreQuality(fund);
  const returns = scoreReturns(fund);
  const riskAdj = scoreRiskAdjusted(fund);
  const cost = scoreCost(fund);
  const strategic = scoreStrategicFit(fund);

  const total = quality + returns + riskAdj + cost + strategic;
  const clamped = Math.max(0, Math.min(100, total));

  let tier;
  if (clamped >= 60) tier = 'Excellent';
  else if (clamped >= 45) tier = 'Good';
  else if (clamped >= 30) tier = 'Caution';
  else tier = 'Poor';

  return { score: clamped, tier, breakdown: { quality, returns, riskAdj, cost, strategic } };
}
```

---

## Data Update Process

When Neel updates portfolio data:
1. Update the relevant CSV file(s) in `/data`
2. Commit and push to git repository
3. Site auto-deploys via Vercel/Netlify

No backend, no database migrations, no API changes needed.

---

## Alpha Methodology Caveat

The Alpha values from Tickertape.in use **trailing alpha** methodology (not standard CAPM alpha). This means:
- Sector funds (Banking, Technology, Energy) show extremely negative alpha (-40% to -55%) because they're measured against a broad market benchmark, not their sector benchmark
- These values are useful for **relative comparison** within the portfolio but should NOT be interpreted as "the fund lost 55% vs benchmark"
- The portal should include a tooltip or note explaining this when alpha is displayed

---

## File Inventory for New Project

Copy these files from `agrawal-estate-planner` to the new project:

### Data Files (required)
```
data/np_agrawal_portfolio_metrics.csv     # Father's portfolio
data/rita_agrawal_portfolio_metrics.csv    # Mother's portfolio
data/rita_holdings.csv                     # Mother's raw holdings with tranches
data/recommended_funds_metrics.csv        # Recommended funds
```

### Documentation (required)
```
docs/MUTUAL-FUND-GUIDE-FOR-PARENTS.md     # Educational guide
docs/FATHER-PORTFOLIO-PRACTICE-GUIDE.md   # Father's fund-by-fund analysis
docs/N-RANK-ALGORITHM.md                  # Scoring algorithm spec
docs/apps/INVESTMENT-PORTAL-SPEC.md       # This file (project spec)
```

### Not Needed
- Backend code (Python/FastAPI) - not applicable
- US equity/options data - not relevant
- Tax/income/real estate modules - not relevant
- Migration files - no database needed
- Schwab/Yahoo integration - no live data needed

---

## Future Enhancements

1. **Auto-refresh NAV data** - Use MFapi.in (`https://api.mfapi.in/mf/{scheme_code}`) to fetch latest NAV for each fund and show real-time valuations
2. **Mother's N-Rank calculation** - Apply N-Rank scoring to Mother's portfolio (same algorithm)
3. **Practice Guide for Mother** - Generate similar to Father's guide
4. **Comparison view** - Compare Father vs Mother portfolio allocation
5. **SIP tracker** - Track ongoing SIPs (Mother's HSBC SIP)
6. **Hindi language toggle** - For parent accessibility

---

## Summary

This is a simple, static web application that:
1. Reads CSV data files
2. Displays portfolio tables with color-coded metrics
3. Calculates N-Rank scores in the browser
4. Shows educational content about mutual funds
5. Auto-deploys when data is updated

No backend, no auth, no database. Just data + UI.
