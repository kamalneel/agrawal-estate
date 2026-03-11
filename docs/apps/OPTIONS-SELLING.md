# Options Selling App

## Goal

Implement and manage a systematic options selling strategy focused on cash-secured puts. Use machine learning and technical analysis to generate recommendations, track performance, and optimize the strategy over time.

---

## Features

### Current Features

1. **Position Tracking**
   - Open options positions
   - Assigned shares
   - Expired worthless positions
   - Rolled positions

2. **Recommendation Engine (V3/V4)**
   - Technical analysis integration
   - N-Rank scoring algorithm
   - Follow-up action recommendations
   - Smart notification filtering

3. **Strategy Management**
   - Cash allocation tracking
   - Buying power utilization
   - Premium income tracking
   - Win rate calculations

4. **Notifications**
   - Telegram integration
   - Web UI notifications
   - Verbose and smart modes
   - Position-specific alerts

5. **RLHF Learning**
   - User feedback collection
   - Strategy improvement over time
   - Decision tree optimization

---

## Roadmap

See detailed algorithm documentation:
- [V3 Algorithm](../OPTIONS-NOTIFICATION-ALGORITHM-V3.md)
- [V4 Algorithm](../OPTIONS-NOTIFICATION-ALGORITHM-V4.md)
- [Trading Philosophy](../V3-TRADING-PHILOSOPHY.md)

---

## Architecture

### Frontend
- **Page:** `/pages/OptionsSelling.tsx`
- **Route:** `/options`

### Backend
- **Module:** `/backend/app/modules/strategies/`
- **Key Services:**
  - `recommendation_service.py` - Core recommendation logic
  - `strategy_service.py` - Strategy execution
  - `v3_notification_service.py` - Notification dispatch
  - `position_evaluator.py` - Position analysis

### Data Model

Key tables:
- `options_positions` - Open and closed positions
- `options_recommendations` - Generated recommendations
- `rlhf_feedback` - User feedback records
