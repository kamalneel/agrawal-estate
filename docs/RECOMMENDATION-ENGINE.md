# Recommendation Engine

**Version:** 3.3  
**Created:** January 7, 2026  
**Status:** ✅ IMPLEMENTED

---

## Executive Summary

This document defines the **HOW** of our recommendation system - the algorithms, data flows, and code architecture that implement the [V3 Trading Philosophy](./V3-TRADING-PHILOSOPHY.md).

**Related Documents:**
- [V3-TRADING-PHILOSOPHY.md](./V3-TRADING-PHILOSOPHY.md) - Why we make these decisions
- [NOTIFICATION-SYSTEM.md](./NOTIFICATION-SYSTEM.md) - How we communicate decisions

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    RECOMMENDATION ENGINE                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐           │
│  │   Position   │    │   Strategy   │    │  Technical   │           │
│  │   Evaluator  │    │   Service    │    │  Analysis    │           │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘           │
│         │                   │                   │                    │
│         └─────────┬─────────┴─────────┬─────────┘                    │
│                   │                   │                              │
│         ┌─────────▼─────────┐ ┌───────▼────────┐                    │
│         │   Pull-Back       │ │  Zero-Cost     │                    │
│         │   Detector        │ │  Roll Finder   │                    │
│         └─────────┬─────────┘ └───────┬────────┘                    │
│                   │                   │                              │
│                   └─────────┬─────────┘                              │
│                             │                                        │
│                   ┌─────────▼─────────┐                              │
│                   │   Recommendation  │                              │
│                   │   Service (V2)    │                              │
│                   └─────────┬─────────┘                              │
│                             │                                        │
│              ┌──────────────┼──────────────┐                        │
│              │              │              │                         │
│    ┌─────────▼───┐  ┌───────▼───┐  ┌──────▼──────┐                  │
│    │ Position    │  │ Snapshot  │  │ Execution   │                  │
│    │ Recommend.  │  │ Records   │  │ Records     │                  │
│    └─────────────┘  └───────────┘  └─────────────┘                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Position Evaluator (`position_evaluator.py`)

The brain of the recommendation engine. Evaluates each open position and determines the recommended action.

**Entry Point:**
```python
from app.modules.strategies.position_evaluator import get_position_evaluator

evaluator = get_position_evaluator()
result = evaluator.evaluate(position)
```

**Evaluation Flow (State Machine):**

```
┌─────────────────────────────────────────────────────────────────┐
│                 POSITION EVALUATION STATES                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  STATE 1: PULL-BACK (Highest Priority)                          │
│  ├─ Condition: Position is >1 week out                          │
│  ├─ Check: Can we return to shorter duration profitably?        │
│  └─ Action: PULL_BACK to shorter expiration                     │
│                                                                  │
│  STATE 1.5: WEEKLY INCOME COMPRESS (V3.3)                       │
│  ├─ Condition: Slightly ITM (<5%) AND profitable (>60%)         │
│  ├─ Check: Can we compress to shorter while staying ITM?        │
│  └─ Action: COMPRESS to preserve weekly income                  │
│                                                                  │
│  STATE 2: ITM HANDLING                                          │
│  ├─ 2a: Far-dated ITM (>60 days)                               │
│  │   ├─ Try: COMPRESS to 45-90 days                             │
│  │   └─ Fallback: MONITOR for mean reversion                    │
│  │                                                               │
│  └─ 2b: Near-dated ITM (≤60 days)                              │
│      └─ Action: ESCAPE with flexible debit ($2-$5)             │
│                                                                  │
│  STATE 2.5: NEAR-ITM WARNING                                    │
│  ├─ Condition: Within 2% of strike + ≤7 days to expiry         │
│  └─ Action: Alert user to potential assignment                  │
│                                                                  │
│  STATE 3: PROFITABLE ROLL                                       │
│  ├─ Condition: OTM + ≥60% profit captured                       │
│  └─ Action: ROLL to capture profit and restart cycle            │
│                                                                  │
│  STATE 4: NO ACTION                                             │
│  └─ Position is fine, continue monitoring                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Output:**
```python
@dataclass
class EvaluationResult:
    action: str          # PULL_BACK, COMPRESS, ROLL_ITM, CLOSE_CATASTROPHIC, MONITOR, ROLL
    position_id: str     # Unique identifier
    symbol: str          # Stock symbol
    priority: str        # urgent, high, medium, low
    reason: str          # Human-readable explanation
    details: dict        # Additional context
    new_strike: float    # Recommended new strike (if rolling)
    new_expiration: date # Recommended new expiration (if rolling)
    net_cost: float      # Expected cost (negative = credit)
    zero_cost_data: dict # Roll details
```

---

### 2. Pull-Back Detector (`pull_back_detector.py`)

Finds opportunities to return far-dated positions to shorter durations.

**When Called:** STATE 1 of evaluation (highest priority)

**Logic:**
```python
def check_pull_back_opportunity(
    symbol: str,
    current_expiration: date,
    current_strike: float,
    option_type: str,
    current_premium: float,
    original_premium: float,
    contracts: int,
    ta_service: TechnicalAnalysisService,
    option_fetcher: OptionChainFetcher
) -> Optional[PullBackOpportunity]:
    """
    Checks if we can roll to a SHORTER expiration profitably.
    
    Returns:
        PullBackOpportunity with:
        - target_expiration
        - target_strike
        - net_cost (should be credit or small debit)
        - weeks_saved
    """
```

**Conditions for Pull-Back:**
1. Current position is > 1 week out
2. Profit captured is significant (position value dropped)
3. Can roll to shorter expiration at acceptable cost (≤20% of original premium)
4. Shorter expiration has liquidity

---

### 3. Zero-Cost Roll Finder (`zero_cost_finder.py`)

Finds roll opportunities for ITM positions with acceptable cost.

**When Called:** STATE 2 of evaluation (ITM handling)

**V3.3 Updates:**
- Uses **actual available expirations** from Schwab API
- Iterates through **all OTM strikes** to find acceptable roll
- **Flexible debit limits** based on ITM severity

**Logic:**
```python
def find_zero_cost_roll(
    symbol: str,
    current_strike: float,
    current_expiration: date,
    current_premium: float,
    original_premium: float,
    option_type: str = 'call',
    max_weeks_out: int = 26,
    max_debit: float = 5.0  # V3.3: Flexible limit
) -> Optional[ZeroCostRollResult]:
    """
    Finds a roll to OTM at acceptable cost.
    
    V3.3 Algorithm:
    1. Get all available expirations from Schwab
    2. For each expiration (shortest first):
       a. Get all OTM strikes
       b. For each strike (highest premium first for calls):
          - Calculate net cost = buy_back - new_premium
          - If net_cost ≤ max_debit: FOUND IT, return
    3. If no strike works, try next expiration
    4. If no expiration works, return None
    """
```

**Output:**
```python
@dataclass
class ZeroCostRollResult:
    expiration_date: date    # New expiration
    strike: float            # New strike
    weeks_out: int           # Weeks from today
    new_premium: float       # Premium received
    net_cost: float          # Cost (negative = credit)
    probability_otm: float   # Probability of staying OTM
    is_credit: bool          # True if net_cost < 0
```

---

### 4. Technical Analysis Service (`technical_analysis.py`)

Provides TA indicators for decision-making.

**Key Methods:**

```python
class TechnicalAnalysisService:
    
    def get_technical_indicators(self, symbol: str) -> TechnicalIndicators:
        """
        Returns:
            - current_price: float
            - rsi: float (0-100)
            - bollinger_upper: float
            - bollinger_middle: float (SMA 20)
            - bollinger_lower: float
            - sma_20: float
            - sma_50: float
        """
    
    def recommend_strike_price(
        self,
        symbol: str,
        option_type: str,
        expiration_weeks: int = 1,
        probability_target: float = 0.70,
        target_expiration_date: str = None  # V3.3: Use actual date
    ) -> StrikeRecommendation:
        """
        Recommends optimal strike based on target delta.
        Uses live options chain from Schwab.
        """
    
    def get_price_history(self, symbol: str, period_days: int = 90) -> dict:
        """
        Gets price history for TA calculations.
        V3.3: Schwab primary, Yahoo fallback.
        """
```

**Data Sources (V3.3):**

| Data Type | Primary | Fallback |
|-----------|---------|----------|
| Stock Prices | Schwab API | - |
| Option Chains | Schwab API | - |
| Price History | Schwab API | Yahoo Finance |
| Greeks (Delta) | Schwab API | - |
| Earnings Dates | Yahoo Finance | - |

---

### 5. Recommendation Service (`recommendation_service.py`)

Manages the V2 recommendation lifecycle.

**V2 Model:**
```
PositionRecommendation (one per position)
    └── RecommendationSnapshot (one per evaluation)
        └── RecommendationExecution (one per action taken)
```

**Key Methods:**

```python
class RecommendationService:
    
    def create_or_update_recommendation(
        self,
        symbol: str,
        account_name: str,
        position_type: str,  # 'sold_option' or 'uncovered'
        source_strike: float,
        source_expiration: date,
        option_type: str,
        current_action: str,
        current_priority: str,
        stock_price: float,
        source_contracts: int = 1,
        target_strike: float = None,
        target_expiration: date = None,
        target_premium: float = None,
        net_cost: float = None,
        rationale: str = "",
        detailed_analysis: str = "",
        context: dict = None
    ) -> Tuple[PositionRecommendation, RecommendationSnapshot, bool]:
        """
        Creates or updates a recommendation.
        
        Returns:
            - PositionRecommendation (created or existing)
            - RecommendationSnapshot (new snapshot)
            - is_new: bool (True if new recommendation)
        """
    
    def cleanup_stale_recommendations(self) -> int:
        """
        Resolves recommendations for positions that no longer exist.
        Called at start of each scheduled scan.
        
        V3.3: Skips 'uncovered' positions (they don't have strikes).
        """
```

---

### 6. Strategy Service (`strategy_service.py`)

Orchestrates all strategies and generates recommendations.

**Strategies:**

| Strategy | Purpose | V3.3 Status |
|----------|---------|-------------|
| `position_evaluator` | Evaluate existing sold options | ✅ Active |
| `new_covered_call` | Find opportunities on uncovered shares | ✅ Active |
| `earnings_alert` | Warn about upcoming earnings | ✅ Active |
| `diversification` | Portfolio balance alerts | ✅ Active |
| `triple_witching_handler` | Special expiration handling | ✅ Active |
| `sell_unsold_contracts` | (Deprecated - merged into new_covered_call) | ❌ Disabled |

**Execution Flow:**

```python
def generate_recommendations(accounts: List[str] = None) -> List[Recommendation]:
    """
    1. For each account:
       a. Get sold options from latest snapshot
       b. Evaluate each position with PositionEvaluator
       c. Create/update V2 recommendations
       
    2. Run non-position strategies:
       a. new_covered_call (uncovered shares)
       b. earnings_alert
       c. diversification
       d. triple_witching_handler
       
    3. Return all recommendations
    """
```

---

## Position Types

### Sold Options (Existing Positions)

Identified by: `(symbol, account, strike, expiration, option_type)`

**Recommendation ID Format:**
```python
def generate_recommendation_id(symbol, account_name, strike, expiration, option_type):
    account_hash = hashlib.sha256(account_name.encode()).hexdigest()[:8]
    exp_str = expiration.strftime('%Y%m%d') if isinstance(expiration, date) else expiration
    return f"rec_{symbol}_{account_hash}_{strike}_{exp_str}_{option_type}"
```

### Uncovered Positions (New Opportunities)

Identified by: `(symbol, account, 'uncovered')`

**Recommendation ID Format:**
```python
def generate_uncovered_recommendation_id(symbol, account_name):
    account_hash = hashlib.sha256(account_name.encode()).hexdigest()[:8]
    return f"rec_{symbol}_{account_hash}_uncovered_call"
```

**Position Type Column:**
```sql
ALTER TABLE position_recommendations 
ADD COLUMN position_type VARCHAR(50) DEFAULT 'sold_option';
-- Values: 'sold_option', 'uncovered'
```

---

## ITM Handling Details

### Calculate ITM Status

```python
def calculate_itm_status(current_price: float, strike_price: float, option_type: str) -> dict:
    """
    Returns:
        is_itm: bool
        itm_pct: float (percentage in the money)
        otm_pct: float (percentage out of the money)
    """
    if option_type == 'call':
        is_itm = current_price > strike_price
        itm_pct = ((current_price - strike_price) / strike_price) * 100 if is_itm else 0
        otm_pct = ((strike_price - current_price) / strike_price) * 100 if not is_itm else 0
    else:  # put
        is_itm = current_price < strike_price
        itm_pct = ((strike_price - current_price) / strike_price) * 100 if is_itm else 0
        otm_pct = ((current_price - strike_price) / strike_price) * 100 if not is_itm else 0
    
    return {'is_itm': is_itm, 'itm_pct': itm_pct, 'otm_pct': otm_pct}
```

### Flexible Debit Limits (V3.3)

```python
def get_max_debit_for_itm_escape(itm_pct: float, original_premium: float) -> float:
    """
    Returns maximum acceptable debit based on ITM severity.
    Uses the HIGHER of: percentage rule OR absolute limit.
    """
    percentage_limit = original_premium * 0.20
    
    if itm_pct >= 10:
        absolute_limit = 5.0  # Deep ITM - pay more to escape
    elif itm_pct >= 5:
        absolute_limit = 3.0  # Moderate ITM
    else:
        absolute_limit = 2.0  # Slight ITM
    
    return max(percentage_limit, absolute_limit)
```

### ITM Compress Logic (V3.3)

For far-dated ITM positions (>60 days), we try to COMPRESS before monitoring:

```python
def _handle_itm_compress(position, current_price, ...):
    """
    Two approaches:
    1. Same-strike compress: Roll to shorter expiration at SAME strike
       - Target: 45-90 days
       - Max debit: $1 (cost-neutral)
       
    2. OTM escape compress: Roll to shorter AND get OTM
       - Target: 45-90 days
       - Max debit: $5
    """
```

---

## Uncovered Position Handling

### New Covered Call Strategy (`new_covered_call.py`)

Identifies opportunities to sell calls on shares without existing options.

**Logic:**

```python
def _analyze_uncovered_position(position: dict) -> dict:
    """
    Uses Technical Analysis to determine SELL vs WAIT.
    
    Decision Matrix:
    - RSI < 30: WAIT (oversold, likely bounce)
    - RSI > 70: SELL NOW (overbought, good premium)
    - RSI 30-70 + middle of Bollinger: SELL NOW (neutral)
    - Price near lower Bollinger: WAIT (support)
    
    Returns recommendation with:
    - action: 'SELL' or 'WAIT'
    - rationale: Explanation with TA values
    - target_strike: Recommended strike (for SELL)
    - target_expiration: Recommended date (for SELL)
    """
```

---

## Scheduled Jobs

| Time (PT) | Job | Description |
|-----------|-----|-------------|
| 6:00 AM | check_and_notify_v2 | Morning scan before market |
| 8:00 AM | check_and_notify_v2 | Post-open scan |
| 12:00 PM | check_and_notify_v2 | Midday scan |
| 12:45 PM | check_and_notify_v2 | Pre-close scan |
| 8:00 PM | check_and_notify_v2 | Evening scan after market |

**Each scan:**
1. Calls `cleanup_stale_recommendations()`
2. Runs all strategies
3. Sends notifications via V2 service

---

## Database Models

### PositionRecommendation

```sql
CREATE TABLE position_recommendations (
    id VARCHAR(100) PRIMARY KEY,  -- generated ID
    symbol VARCHAR(10) NOT NULL,
    account_name VARCHAR(100) NOT NULL,
    position_type VARCHAR(50) DEFAULT 'sold_option',  -- V3.3: 'sold_option' or 'uncovered'
    option_type VARCHAR(10) NOT NULL,
    source_strike DECIMAL(10,2),  -- nullable for uncovered
    source_expiration DATE,       -- nullable for uncovered
    source_contracts INTEGER DEFAULT 1,
    status VARCHAR(20) DEFAULT 'active',  -- active, resolved, position_closed
    resolution_reason TEXT,
    created_at TIMESTAMP,
    resolved_at TIMESTAMP,
    
    INDEX idx_symbol (symbol),
    INDEX idx_account (account_name),
    INDEX idx_status (status),
    INDEX idx_position_type (position_type)
);
```

### RecommendationSnapshot

```sql
CREATE TABLE recommendation_snapshots (
    id SERIAL PRIMARY KEY,
    recommendation_id VARCHAR(100) REFERENCES position_recommendations(id),
    snapshot_number INTEGER NOT NULL,
    stock_price DECIMAL(10,2),
    current_action VARCHAR(50),       -- ROLL_ITM, COMPRESS, MONITOR, SELL, WAIT, etc.
    current_priority VARCHAR(20),
    target_strike DECIMAL(10,2),
    target_expiration DATE,
    target_premium DECIMAL(10,2),
    net_cost DECIMAL(10,2),
    rationale TEXT,
    detailed_analysis TEXT,
    context JSONB,
    
    -- Change tracking
    action_changed BOOLEAN DEFAULT FALSE,
    target_changed BOOLEAN DEFAULT FALSE,
    priority_changed BOOLEAN DEFAULT FALSE,
    
    notification_mode VARCHAR(20),  -- 'verbose' or 'smart'
    created_at TIMESTAMP DEFAULT NOW(),
    
    INDEX idx_rec_id (recommendation_id),
    INDEX idx_created (created_at)
);
```

---

## Configuration Reference

```python
RECOMMENDATION_ENGINE_CONFIG = {
    # === PULL-BACK ===
    "pull_back_max_debit_pct": 0.20,
    "pull_back_min_weeks_saved": 1,
    
    # === ITM HANDLING ===
    "itm_compress_threshold_days": 60,
    "compress_target_min_days": 45,
    "compress_target_max_days": 90,
    "same_strike_compress_max_debit": 1.0,
    "otm_escape_compress_max_debit": 5.0,
    "itm_escape_debit_limits": {
        "slight": 2.0,
        "moderate": 3.0,
        "deep": 5.0,
    },
    
    # === WEEKLY INCOME PRIORITY ===
    "weekly_income_max_itm_pct": 5.0,
    "weekly_income_min_profit_pct": 0.60,
    "weekly_income_max_debit": 1.0,
    
    # === NEAR-ITM WARNING ===
    "near_itm_threshold_pct": 2.0,
    "urgent_near_itm_pct": 1.0,
    "near_itm_max_days": 7,
    
    # === TECHNICAL ANALYSIS ===
    "target_delta": 0.30,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    
    # === SCANNING ===
    "max_scan_weeks": 26,
    "stale_cleanup_enabled": True,
}
```

---

## File Reference

| File | Purpose |
|------|---------|
| `position_evaluator.py` | Core evaluation logic |
| `pull_back_detector.py` | Pull-back opportunity finder |
| `zero_cost_finder.py` | ITM roll finder |
| `technical_analysis.py` | TA indicators and strike recommendations |
| `recommendation_service.py` | V2 recommendation lifecycle |
| `recommendation_models.py` | SQLAlchemy models |
| `strategy_service.py` | Strategy orchestration |
| `new_covered_call.py` | Uncovered position strategy |
| `schwab_service.py` | Schwab API integration |
| `yahoo_cache.py` | Yahoo fallback for earnings |

---

**END OF RECOMMENDATION ENGINE DOCUMENTATION**

