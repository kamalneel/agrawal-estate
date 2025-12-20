# Recommendation System

This document covers the design, implementation, and management of the recommendation system that transforms the app from a reporting system to a strategy application.

## Table of Contents

1. [Overview](#overview)
2. [Design Principles](#design-principles)
3. [Recommendation Types](#recommendation-types)
4. [API Usage](#api-usage)
5. [Strategy Management](#strategy-management)
6. [Adding New Strategies](#adding-new-strategies)

---

## Overview

### Before (Reporting System)
- App shows: "You have 3 unsold AAPL contracts"
- User decides: What to do with this information
- Action: User takes action manually

### After (Strategy Application)
- App shows: "**Recommendation**: Sell 3 unsold AAPL calls - $150/week potential income"
- App explains: Why this makes sense (rationale)
- App suggests: Specific action to take
- User acts: On clear, prioritized recommendations

---

## Design Principles

1. **Actionable**: Recommendations suggest specific actions, not just report facts
2. **Prioritized**: Clear priority levels (urgent, high, medium, low)
3. **Contextual**: Based on current portfolio state
4. **Trackable**: Users can acknowledge and track actions taken
5. **Extensible**: Easy to add new recommendation types

---

## Recommendation Types

### 1. Sell Unsold Contracts (Income Generation)

**When**: You have holdings with unsold contracts that could generate income

**Example**:
```json
{
  "type": "sell_unsold_contracts",
  "priority": "high",
  "title": "Sell 3 unsold AAPL covered call(s)",
  "description": "You have 3 unsold contract(s) that could generate $150/week",
  "action": "Sell 3 AAPL covered call(s) at delta 10 strike",
  "potential_income": 150.0
}
```

### 2. Early Roll Opportunities (Optimization)

**When**: Position has reached 80%+ profit with days remaining

**Example**:
```json
{
  "type": "early_roll_opportunity",
  "priority": "high",
  "title": "Roll AAPL $275 call early - 85% profit captured",
  "description": "Rolling now would capture premium and redeploy capital",
  "action": "Close current position and roll to next week's expiration",
  "context": {
    "profit_percent": 85.0,
    "days_remaining": 3
  }
}
```

### 3. Premium Setting Adjustments (Optimization)

**When**: Actual premiums differ >15% from your settings

**Example**:
```json
{
  "type": "adjust_premium_expectation",
  "priority": "medium",
  "title": "Update TSLA premium setting - actual is 20% higher",
  "action": "Update TSLA premium setting from $150 to $180 per contract"
}
```

### 4. Diversification Recommendations (Risk Management)

**When**: Portfolio is >35% concentrated in one symbol

**Example**:
```json
{
  "type": "diversify_holdings",
  "priority": "medium",
  "title": "Consider diversifying - 40% of income from AAPL",
  "action": "Review and sell options on NVDA, META, or MSFT"
}
```

### 5. Expiring Options Management (Income Generation)

**When**: Options are expiring this week and need action

**Example**:
```json
{
  "type": "manage_expiring_options",
  "priority": "urgent",
  "title": "3 positions expiring Friday - decide on roll or let expire",
  "context": {
    "expiring_count": 3,
    "expiration_date": "2025-12-10"
  }
}
```

### 6. ITM Roll Optimizer (Cost-Optimized Rolls)

**When**: Position goes In-The-Money (ITM)

Analyzes all combinations of time and strike to find optimal balance:

| Option | Expiration | Strike | Net Cost | Prob OTM |
|--------|-----------|--------|----------|----------|
| Conservative | Jan 24 (3w) | $680 | -$4.50 | 85% |
| Moderate | Jan 17 (2w) | $665 | -$2.00 | 72% |
| Aggressive | Jan 10 (1w) | $655 | -$1.00 | 58% |

---

## API Usage

### Get Recommendations

```bash
GET /api/v1/strategies/options-selling/recommendations?default_premium=60&profit_threshold=0.80
```

**Response:**
```json
{
  "recommendations": [
    {
      "id": "sell_unsold_AAPL_2025-12-08",
      "type": "sell_unsold_contracts",
      "category": "income_generation",
      "priority": "high",
      "title": "Sell 3 unsold AAPL covered call(s)",
      "description": "Could generate $150/week ($7,500/year)",
      "rationale": "Based on your premium settings...",
      "action": "Sell 3 AAPL covered call(s) at delta 10 strike",
      "action_type": "sell",
      "potential_income": 150.0,
      "potential_risk": "low",
      "time_horizon": "this_week",
      "context": {
        "symbol": "AAPL",
        "unsold_contracts": 3
      }
    }
  ],
  "count": 5,
  "by_priority": {
    "urgent": 1,
    "high": 2,
    "medium": 1,
    "low": 1
  }
}
```

### Trigger Manual Check with Notifications

```bash
POST /api/v1/strategies/recommendations/check-now?send_notifications=true
```

---

## Strategy Management

### Viewing Strategies in the UI

1. Navigate to **Strategy Management** in the sidebar
2. View all strategies with:
   - Current status (Enabled/Disabled)
   - Notification settings
   - Configuration parameters

### Modifying Existing Strategies

**Enable/Disable a Strategy:**
- Click the toggle switch (Green = Enabled, Gray = Disabled)

**Toggle Notifications:**
- Click "On/Off" button next to "Notifications:"

**Configure Strategy Settings:**
1. Click the **"Configure"** button
2. Modify:
   - **Notification Priority Threshold**: Minimum priority to trigger notifications (urgent, high, medium, low)
   - **Strategy Parameters**: Strategy-specific settings (e.g., profit thresholds)
3. Click **"Save"**

**Test a Strategy:**
- Click **"Test"** to see sample recommendations

### Current Built-in Strategies

1. **Sell Unsold Contracts** (`sell_unsold_contracts`)
   - Category: Income Generation
   - Parameters: `min_weekly_income`

2. **Early Roll Opportunity** (`early_roll_opportunity`)
   - Category: Optimization
   - Parameters: `profit_threshold`

3. **Premium Adjustment** (`adjust_premium_expectation`)
   - Category: Optimization

4. **Diversification** (`diversify_holdings`)
   - Category: Risk Management

### Notification Priority Threshold

Controls which recommendations trigger notifications:
- **urgent**: Only urgent recommendations
- **high**: Urgent and high priority
- **medium**: Urgent, high, and medium
- **low**: All recommendations

---

## Adding New Strategies

### Step 1: Create the Strategy Class

Create a new file in `backend/app/modules/strategies/strategies/`:

```python
# my_new_strategy.py
from app.modules.strategies.strategy_base import BaseStrategy
from app.modules.strategies.recommendations import StrategyRecommendation

class MyNewStrategy(BaseStrategy):
    
    @property
    def strategy_type(self) -> str:
        return "my_new_strategy"
    
    @property
    def name(self) -> str:
        return "My New Strategy"
    
    @property
    def description(self) -> str:
        return "What this strategy does"
    
    @property
    def category(self) -> str:
        # "income_generation", "optimization", or "risk_management"
        return "optimization"
    
    @property
    def default_parameters(self) -> Dict[str, Any]:
        return {
            "param1": 100,
            "param2": 0.80,
        }
    
    def generate_recommendations(
        self,
        params: Dict[str, Any]
    ) -> List[StrategyRecommendation]:
        recommendations = []
        
        # Your logic here
        if condition_met:
            recommendation = StrategyRecommendation(
                id=f"my_strategy_{symbol}_{datetime.now().isoformat()}",
                type=self.strategy_type,
                category=self.category,
                priority="high",  # urgent, high, medium, low
                title="Your recommendation title",
                description="Detailed description",
                rationale="Why this makes sense",
                action="What action to take",
                action_type="sell",  # sell, roll, adjust, monitor, review
                potential_income=100.0,
                context={"symbol": "AAPL"}
            )
            recommendations.append(recommendation)
        
        return recommendations
```

### Step 2: Register the Strategy

Add to `backend/app/modules/strategies/strategies/__init__.py`:

```python
from app.modules.strategies.strategies.my_new_strategy import MyNewStrategy

STRATEGY_REGISTRY = {
    "sell_unsold_contracts": SellUnsoldContractsStrategy,
    "early_roll_opportunity": EarlyRollOpportunityStrategy,
    "my_new_strategy": MyNewStrategy,  # Add here
}
```

### Step 3: Restart the Server

```bash
pm2 restart agrawal-backend --update-env
```

### Step 4: Configure in UI

1. Go to Strategy Management page
2. Your strategy will appear automatically
3. Click "Configure" to set parameters
4. Enable using the toggle switch

---

## Best Practices

1. **Be Specific**: Recommendations should suggest concrete actions
2. **Show Impact**: Include potential income/risk when relevant
3. **Explain Why**: Include clear rationale
4. **Prioritize Correctly**: Use priority levels appropriately
5. **Test Before Enabling**: Use the "Test" button first
6. **Start Conservative**: Begin with higher priority thresholds
7. **Monitor Results**: Check the Notification tab regularly

---

## Files Reference

### Core Files
- `backend/app/modules/strategies/recommendations.py` - Core recommendation service
- `backend/app/modules/strategies/strategy_base.py` - Base strategy class
- `backend/app/modules/strategies/router.py` - API endpoints
- `backend/app/modules/strategies/models.py` - Database models

### Strategy Files
- `backend/app/modules/strategies/strategies/` - Individual strategy implementations
- `backend/app/modules/strategies/strategies/__init__.py` - Strategy registry

---

*Last Updated: December 2025*

