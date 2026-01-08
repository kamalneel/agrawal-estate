# Notification System

**Version:** 3.3  
**Created:** January 7, 2026  
**Status:** ✅ IMPLEMENTED

---

## Executive Summary

This document defines the **COMMUNICATION** layer - how recommendations are delivered to the user via Telegram and the Web UI.

**Related Documents:**
- [V3-TRADING-PHILOSOPHY.md](./V3-TRADING-PHILOSOPHY.md) - Why we make decisions
- [RECOMMENDATION-ENGINE.md](./RECOMMENDATION-ENGINE.md) - How we generate recommendations

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    NOTIFICATION SYSTEM                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│    ┌─────────────────────────────────────────────────────┐      │
│    │            Recommendation Service (V2)               │      │
│    │                                                      │      │
│    │  PositionRecommendation ──► RecommendationSnapshot   │      │
│    └─────────────────────┬───────────────────────────────┘      │
│                          │                                       │
│                          ▼                                       │
│    ┌─────────────────────────────────────────────────────┐      │
│    │           V2 Notification Service                    │      │
│    │                                                      │      │
│    │  - Formats messages                                  │      │
│    │  - Applies account ordering                          │      │
│    │  - Handles Verbose/Smart modes                       │      │
│    │  - Deduplicates notifications                        │      │
│    └────────────┬───────────────────────┬────────────────┘      │
│                 │                       │                        │
│        ┌────────▼────────┐    ┌────────▼────────┐               │
│        │    Telegram     │    │     Web UI      │               │
│        │    Bot          │    │     API         │               │
│        └─────────────────┘    └─────────────────┘               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## V2 Data Model

### Single Source of Truth

Both Telegram and Web UI use the same underlying data:

```
PositionRecommendation
├── id: "rec_AVGO_abc123_350.0_20260123_call"
├── symbol: "AVGO"
├── account_name: "Neel's Brokerage"
├── position_type: "sold_option" | "uncovered"
├── status: "active" | "resolved" | "position_closed"
│
└── snapshots: [
    RecommendationSnapshot #1 (6:00 AM scan)
    RecommendationSnapshot #2 (8:00 AM scan)  ← Latest
    ...
]
```

### Snapshot Contents

Each snapshot captures the recommendation state at a point in time:

```python
snapshot = {
    'snapshot_number': 2,
    'stock_price': 346.50,
    'current_action': 'ROLL_ITM',
    'current_priority': 'high',
    'target_strike': 340.0,
    'target_expiration': date(2026, 1, 16),
    'target_premium': 5.20,
    'net_cost': -0.80,  # Credit
    'rationale': '1.1% ITM - compress to Jan 16 for credit',
    'detailed_analysis': '...',
    'context': {...},
    
    # Change tracking
    'action_changed': True,   # ⚡
    'target_changed': False,  # 🎯
    'priority_changed': True, # ⬆️
    
    'notification_mode': 'verbose',
    'created_at': datetime(2026, 1, 7, 16, 0, 0)
}
```

---

## Notification Modes

### Verbose Mode

**Purpose:** Show EVERY snapshot from each scan  
**Use Case:** Full transparency, debugging, seeing all evaluations

**Behavior:**
- Returns ALL snapshots within the time window
- No filtering based on changes
- Shows snapshot number and all change indicators

### Smart Mode

**Purpose:** Show only NEW or CHANGED recommendations  
**Use Case:** Noise reduction, actionable alerts only

**Behavior:**
- Only returns snapshots where something changed:
  - `action_changed = True` (⚡ action changed)
  - `target_changed = True` (🎯 target changed)
  - `priority_changed = True` (⬆️ priority changed)
- First snapshot for new recommendations always shown

**API Filter:**
```python
if mode == 'smart':
    query = query.filter(
        or_(
            RecommendationSnapshot.action_changed == True,
            RecommendationSnapshot.target_changed == True,
            RecommendationSnapshot.priority_changed == True
        )
    )
```

---

## Notification Formatting

### Title Format

| Action | Format | Example |
|--------|--------|---------|
| ROLL | `🔄 ROLL: {symbol} ${old}→${new} {date} · ${cost}` | `🔄 ROLL: AVGO $350→$340 01/16 · $0.80 credit` |
| SELL | `📈 SELL: {symbol} ({contracts} uncovered) · Earn ${premium}` | `📈 SELL: AAPL (17 uncovered) · Earn $340` |
| WAIT | `⏸️ WAIT: {symbol} ({contracts} uncovered) · Stock ${price}` | `⏸️ WAIT: NFLX (5 uncovered) · Stock $91` |
| MONITOR | `👁️ MONITOR: {symbol} ${strike} · Stock ${price}` | `👁️ MONITOR: TSLA $370 · Stock $435` |
| COMPRESS | `📥 COMPRESS: {symbol} ${old}→${new} {date} · ${cost}` | `📥 COMPRESS: TSLA $370→$370 03/20 · $0.50 debit` |
| CLOSE | `🚨 CLOSE: {symbol} ${strike} - Cannot escape` | `🚨 CLOSE: FIG $60.0 - Cannot escape` |

### Cost Display

```python
if net_cost < 0:
    cost_str = f"${abs(net_cost):.2f} credit"
elif net_cost > 0:
    cost_str = f"${net_cost:.2f} debit"
else:
    cost_str = "cost-neutral"
```

### Snapshot Badges

```
(snap #2) ⚡🎯⬆️
```

- `#N` - Snapshot number (how many times evaluated)
- `⚡` - Action changed from previous
- `🎯` - Target (strike/expiration) changed
- `⬆️` - Priority increased

---

## Telegram Formatting

### Message Structure

```
📢 VERBOSE MODE - All Snapshots
───────────────────────

Neel's Brokerage - 10 Recommendations:
• 🔄 ROLL: AVGO $350→$340 01/16 ($0.80 credit)
• 📈 SELL: AAPL (17 uncovered) (earn $340)
• ⏸️ WAIT: NFLX (5 uncovered) - oversold, likely bounce

Jaya's Brokerage - 3 Recommendations:
• 🔄 ROLL: TSLA $370→$380 01/23 ($1.20 debit)
...

12:00 PM
```

### Account Grouping

Notifications are grouped by account in NEO order (see Account Ordering below).

### Line Format by Action

```python
# ROLL
line = f"• 🔄 ROLL: {symbol} ${source}→${target} {exp}"
if net_cost:
    cost_type = "debit" if net_cost > 0 else "credit"
    line += f" (${abs(net_cost):.2f} {cost_type})"

# SELL
line = f"• 📈 SELL: {symbol} ${strike} calls"
if premium:
    line += f" (earn ${premium * contracts:.0f})"

# WAIT
line = f"• ⏸️ WAIT: {symbol} ({contracts} uncovered) - {reason_short}"
```

---

## Web UI Formatting

### API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/notifications/v2/current` | Current active recommendations |
| `/notifications/v2/history` | Historical recommendations (last 7 days) |

### Response Format

```json
{
  "notifications": [
    {
      "id": "rec_AVGO_abc123_350.0_20260123_call",
      "symbol": "AVGO",
      "account_name": "Neel's Brokerage",
      "action_type": "ROLL_ITM",
      "priority": "high",
      "title": "🔄 ROLL: AVGO $350.00→$340.00 01/16 · $0.80 credit",
      "description": "1.1% ITM - compress to Jan 16 for credit...",
      "source_strike": 350.0,
      "source_expiration": "2026-01-23",
      "target_strike": 340.0,
      "target_expiration": "2026-01-16",
      "net_cost": -0.80,
      "contracts": 2,
      "snapshot_number": 2,
      "action_changed": true,
      "target_changed": false,
      "priority_changed": true,
      "created_at": "2026-01-07T20:00:00Z",
      "context": {...}
    }
  ],
  "mode": "verbose",
  "count": 15,
  "generated_at": "2026-01-07T20:05:00Z"
}
```

### UI Components

```tsx
// Notification Card
<NotificationCard>
  <Header>
    <AccountBadge>{rec.account_name}</AccountBadge>
    <SnapshotBadge>#{rec.snapshot_number}</SnapshotBadge>
    {rec.action_changed && <ChangeBadge>⚡</ChangeBadge>}
  </Header>
  <Title>{rec.title}</Title>
  <Description>{rec.description}</Description>
  <ActionBadge type={rec.action_type}>
    {getStrategyLabel(rec.action_type)}
  </ActionBadge>
</NotificationCard>
```

### CSS Classes by Action

```css
.rollBadge { background: blue; }
.sellBadge { background: green; }
.waitBadge { background: amber; }
.monitorBadge { background: gray; }
.closeBadge { background: red; }
```

---

## Account Ordering (NEO)

**NEO Order:** Neel's accounts first, then Jaya's, then others.

```python
ACCOUNT_ORDER = [
    "Neel's Brokerage",
    "Neel's Retirement", 
    "Neel's Roth IRA",
    "Jaya's Brokerage",
    "Jaya's IRA",
    "Jaya's Roth IRA",
]

def sort_accounts(accounts: List[str]) -> List[str]:
    def sort_key(account: str) -> int:
        try:
            return ACCOUNT_ORDER.index(account)
        except ValueError:
            return len(ACCOUNT_ORDER)  # Unknown accounts at end
    
    return sorted(accounts, key=sort_key)
```

---

## Timezone Handling

### The Problem

- Database stores naive datetimes (assumed UTC for V2)
- Server runs in Pacific Time
- API must return timezone-aware UTC strings
- Frontend converts to user's local time

### The Solution

Centralized utility in `backend/app/core/timezone.py`:

```python
from datetime import datetime, timezone
import pytz

PACIFIC = pytz.timezone('America/Los_Angeles')

def format_datetime_for_api(dt: datetime, assume_utc: bool = True) -> str:
    """
    Converts datetime to UTC ISO string with 'Z' suffix.
    
    Args:
        dt: datetime (naive or aware)
        assume_utc: If True, naive datetimes are UTC (V2 models)
                    If False, naive datetimes are Pacific (V1 models)
    
    Returns:
        "2026-01-07T20:00:00Z"
    """
    if dt is None:
        return None
    
    if dt.tzinfo is None:
        if assume_utc:
            dt_aware = dt.replace(tzinfo=timezone.utc)
        else:
            dt_aware = PACIFIC.localize(dt)
    else:
        dt_aware = dt
    
    return dt_aware.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
```

### Usage

```python
# V2 models (stored as naive UTC)
"created_at": format_datetime_for_api(snapshot.created_at, assume_utc=True)

# V1 models (stored as naive Pacific)
"created_at": format_datetime_for_api(record.created_at, assume_utc=False)
```

---

## Deduplication

### Problem

Multiple strategies could generate recommendations for the same position, causing duplicates.

### Solution

Deduplicate by `(account_name, symbol, action_type)`, keeping the most recent:

```python
def get_all_notifications_to_send(self, mode: str = 'verbose') -> List[dict]:
    # ... fetch all notifications ...
    
    # Deduplicate
    deduplicated = {}
    for notif in all_notifications:
        key = (notif['account_name'], notif['symbol'], notif['action_type'])
        if key not in deduplicated or notif['created_at'] > deduplicated[key]['created_at']:
            deduplicated[key] = notif
    
    return list(deduplicated.values())
```

---

## Stale Recommendation Cleanup

### Problem

Recommendations persist after positions are closed (sold/assigned).

### Solution

Before each scan, cleanup stale recommendations:

```python
def cleanup_stale_recommendations(self) -> int:
    """
    Compares active recommendations against current sold_options.
    Marks missing positions as 'position_closed'.
    
    Note: Skips 'uncovered' positions (they don't have strikes to match).
    """
    # Get latest sold_options snapshot
    latest_snapshot = self.db.query(SoldOptionsSnapshot).order_by(
        SoldOptionsSnapshot.created_at.desc()
    ).first()
    
    # Get all sold options from snapshot
    current_positions = set()
    for opt in latest_snapshot.sold_options:
        key = (opt.symbol, opt.account_name, opt.strike_price, opt.expiration_date)
        current_positions.add(key)
    
    # Find stale recommendations
    active_recs = self.db.query(PositionRecommendation).filter(
        PositionRecommendation.status == 'active'
    ).all()
    
    resolved_count = 0
    for rec in active_recs:
        if rec.position_type == 'uncovered':
            continue  # Skip uncovered - managed differently
        
        key = (rec.symbol, rec.account_name, rec.source_strike, rec.source_expiration)
        if key not in current_positions:
            rec.status = 'position_closed'
            rec.resolved_at = datetime.utcnow()
            resolved_count += 1
    
    self.db.commit()
    return resolved_count
```

---

## Scheduled Jobs

### Schedule (Pacific Time)

| Time | Job |
|------|-----|
| 6:00 AM | `check_and_notify_v2` |
| 8:00 AM | `check_and_notify_v2` |
| 12:00 PM | `check_and_notify_v2` |
| 12:45 PM | `check_and_notify_v2` |
| 8:00 PM | `check_and_notify_v2` |

### Job Flow

```python
async def check_and_notify_v2(self):
    """
    1. Cleanup stale recommendations
    2. Generate all recommendations (via strategy_service)
    3. Format notifications (via v2_notification_service)
    4. Send to Telegram
    5. Notifications available via API for Web UI
    """
    db = SessionLocal()
    try:
        # 1. Cleanup
        rec_service = RecommendationService(db)
        cleaned = rec_service.cleanup_stale_recommendations()
        logger.info(f"Cleaned up {cleaned} stale recommendations")
        
        # 2. Generate
        strategy_service = StrategyService(db)
        recommendations = strategy_service.generate_recommendations()
        
        # 3. Format
        notif_service = V2NotificationService(db)
        
        # 4. Send Telegram (both modes)
        for mode in ['verbose', 'smart']:
            message = notif_service.format_telegram_message(mode)
            if message:
                await telegram_bot.send_message(message, mode=mode)
        
        # 5. API automatically has access to same data
        
    finally:
        db.close()
```

---

## API Reference

### GET `/api/v1/strategies/notifications/v2/current`

Returns current active recommendations.

**Query Parameters:**
- `mode`: `verbose` | `smart` (default: `verbose`)

**Response:**
```json
{
  "notifications": [...],
  "mode": "verbose",
  "count": 15,
  "generated_at": "2026-01-07T20:00:00Z"
}
```

### GET `/api/v1/strategies/notifications/v2/history`

Returns historical recommendations.

**Query Parameters:**
- `mode`: `verbose` | `smart` (default: `verbose`)
- `days_back`: integer (default: 7)

**Response:**
```json
{
  "notifications": [...],
  "mode": "smart",
  "count": 45,
  "days_back": 7
}
```

---

## File Reference

| File | Purpose |
|------|---------|
| `v2_notification_service.py` | Core notification formatting |
| `recommendation_service.py` | V2 model management |
| `recommendation_models.py` | SQLAlchemy models |
| `router.py` | API endpoints |
| `scheduler.py` | Scheduled jobs |
| `timezone.py` | Datetime utilities |
| `Notifications.tsx` | Web UI component |
| `Notifications.module.css` | UI styling |

---

## Configuration

```python
NOTIFICATION_CONFIG = {
    # === MODES ===
    "default_mode": "verbose",
    "available_modes": ["verbose", "smart"],
    
    # === HISTORY ===
    "default_days_back": 7,
    "max_days_back": 30,
    
    # === FORMATTING ===
    "max_description_length": 200,
    "truncate_rationale": True,
    
    # === DEDUPLICATION ===
    "dedupe_key": ["account_name", "symbol", "action_type"],
    
    # === CLEANUP ===
    "cleanup_on_scan": True,
    "skip_uncovered_cleanup": True,
    
    # === TELEGRAM ===
    "telegram_enabled": True,
    "telegram_send_both_modes": True,
    
    # === SCHEDULING ===
    "scan_times_pt": ["06:00", "08:00", "12:00", "12:45", "20:00"],
}
```

---

## Troubleshooting

### Issue: Notifications show wrong time

**Cause:** Timezone conversion issue  
**Fix:** Ensure `format_datetime_for_api` is used with correct `assume_utc` flag

### Issue: Duplicate notifications

**Cause:** Multiple strategies generating for same position  
**Fix:** Deduplication logic in `get_all_notifications_to_send`

### Issue: Stale recommendations showing

**Cause:** Position closed but recommendation not resolved  
**Fix:** `cleanup_stale_recommendations` runs before each scan

### Issue: Missing notifications in Smart mode

**Cause:** No changes detected (action/target/priority all same)  
**Fix:** This is expected behavior - switch to Verbose mode to see all

### Issue: "$None" in titles

**Cause:** Target strike is null (e.g., for WAIT recommendations)  
**Fix:** Use stock price for display when target_strike is None

---

**END OF NOTIFICATION SYSTEM DOCUMENTATION**

