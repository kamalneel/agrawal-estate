# Notifications & Scheduler

This document covers the notification system setup, configuration, scheduling strategy, and testing.

**Related Documentation:**
- [Options Strategies](./OPTIONS_STRATEGIES.md) - Educational guide on options selling, delta, and strategy roadmap
- [Notification Algorithm V2](./OPTIONS-NOTIFICATION-ALGORITHM-V2.md) - Active algorithm specification for the recommendation engine
- [Notification Algorithm V1](./OPTIONS-NOTIFICATION-ALGORITHM-V1.md) - Original algorithm (deprecated)

## Table of Contents

1. [Quick Start - Telegram](#quick-start---telegram)
2. [Notification Options](#notification-options)
3. [Scheduling Strategy](#scheduling-strategy)
4. [Configuration](#configuration)
5. [Testing](#testing)

---

## Quick Start - Telegram

**Telegram is the recommended notification channel:**
- ✅ 100% FREE
- ✅ 5 minute setup
- ✅ Works from localhost
- ✅ Very reliable

### Step 1: Create a Telegram Bot

1. Open Telegram app
2. Search for `@BotFather`
3. Send: `/newbot`
4. Follow prompts:
   - Choose a name (e.g., "Estate Planner Bot")
   - Choose a username (e.g., "agrawal_estate_bot")
5. **Save the token** - looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

### Step 2: Get Your Chat ID

1. Start a chat with your new bot (search for the username)
2. Send any message (e.g., "Hello")
3. Open this URL in browser:
   ```
   https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates
   ```
4. Find `"chat":{"id":123456789}` - that's your chat ID

**Alternative:** Message `@userinfobot` on Telegram

### Step 3: Configure Environment

Add to your `.env` file:
```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
```

### Step 4: Test It

```python
import os, requests

bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
chat_id = os.getenv('TELEGRAM_CHAT_ID')

url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
data = {"chat_id": chat_id, "text": "🎉 Test notification!"}
response = requests.post(url, json=data)
print(response.json())  # Should show "ok": true
```

---

## Notification Options

### Recommended: Telegram Bot ⭐

**Why it's best for home server:**
- 100% FREE
- 5 minute setup
- Works from localhost
- Reliable official API
- Rich features (formatting, buttons)
- Direct to your phone

### Alternative: Email

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
NOTIFY_EMAIL=your_email@gmail.com
```

**Pros:** Free, simple
**Cons:** Less immediate, may go to spam

### Alternative: WhatsApp via Twilio

```bash
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
WHATSAPP_TO=whatsapp:+1234567890
```

**Pros:** Official, reliable
**Cons:** ~$0.005-0.01 per message (still very cheap)

### Alternative: Pushover

One-time $5 purchase (lifetime)

### Alternative: Discord Webhook

Free, good for rich formatting

---

## Scheduling Strategy

### Automated Polling Schedule

The scheduler automatically checks for recommendations based on time:

| Time Period | Frequency | Rationale |
|------------|-----------|-----------|
| **Market Hours** (9:30 AM - 4:00 PM ET, Mon-Fri) | Every 15 min | Options prices change frequently |
| **Pre-Market** (4:00 AM - 9:30 AM ET, Mon-Fri) | Every 30 min | Some movement, less critical |
| **After Hours** (4:00 PM - 8:00 PM ET, Mon-Fri) | Every 60 min | Minimal price changes |
| **Overnight** (8:00 PM - 4:00 AM ET, Mon-Fri) | Every 2 hours | Very minimal changes |
| **Weekends** | Every 6 hours | Markets closed |

### Notification Frequency Rules

**Priority-Based Sending:**

| Event | Timing | Cooldown |
|-------|--------|----------|
| New Urgent Recommendation | Immediate | None |
| New High Priority | Immediate | None |
| Priority Escalation | Immediate | None |
| Medium/Low Priority | Batched every 30 min | 30 min |
| Existing Recommendation Update | Only if priority changes | 1 hour |

**Time-Based Rules:**
- **8 AM - 2 PM PT (active hours)**: Send Urgent + High only
- **Before 8 AM / After 2 PM PT**: Send all priorities (Urgent, High, Medium, Low)
- **Weekends**: Send all priorities, batched every 6 hours

### Deduplication

The system tracks sent notifications to avoid spam:
- Tracks last notification time per recommendation ID
- Only sends if:
  - New recommendation (never notified)
  - Priority increased
  - Recommendation expired
  - Cooldown period expired

> **📋 For technical details**, see [Deduplication Logic](./OPTIONS-NOTIFICATION-ALGORITHM-V2.md#4-deduplication-logic-unchanged) in the algorithm doc.

---

## Configuration

### Environment Variables

```bash
# Polling Configuration
RECOMMENDATION_CHECK_INTERVAL_MARKET_HOURS=15  # minutes
RECOMMENDATION_CHECK_INTERVAL_AFTER_HOURS=60   # minutes
RECOMMENDATION_CHECK_INTERVAL_WEEKEND=360      # minutes (6 hours)

# Notification Configuration
NOTIFICATION_COOLDOWN_URGENT=0      # minutes (immediate)
NOTIFICATION_COOLDOWN_HIGH=0        # minutes (immediate)
NOTIFICATION_COOLDOWN_MEDIUM=30     # minutes
NOTIFICATION_COOLDOWN_LOW=60        # minutes
NOTIFICATION_BATCH_INTERVAL=30      # minutes

# Market Hours (ET timezone)
MARKET_OPEN_HOUR=9
MARKET_OPEN_MINUTE=30
MARKET_CLOSE_HOUR=16
MARKET_CLOSE_MINUTE=0
```

### Scheduler Jobs

The scheduler creates 4 jobs:
- `check_active_hours` - 8 AM - 2 PM PT (every 15 min)
- `check_pre_market` - Before 8 AM PT (every 30 min)
- `check_after_hours` - After 2 PM PT (every 60 min)
- `check_weekends` - Weekends (every 6 hours)

---

## Testing

### Manual Trigger (Recommended)

**Using Test Script:**
```bash
cd backend
./scripts/test_scheduler.sh <your_password> [send_notifications]

# With notifications
./scripts/test_scheduler.sh mypassword

# Dry run (no notifications)
./scripts/test_scheduler.sh mypassword false
```

**Using curl:**
```bash
# Get auth token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password": "your_password"}' | \
  python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# Trigger check
curl -X POST "http://localhost:8000/api/v1/strategies/recommendations/check-now?send_notifications=true" \
  -H "Authorization: Bearer $TOKEN"
```

**Using the UI:**
1. Navigate to Options Selling page
2. Go to Notification tab
3. Recommendations are fetched automatically

### Check Scheduler Status

**View PM2 Logs:**
```bash
pm2 logs agrawal-backend --lines 50
pm2 logs agrawal-backend --lines 100 | grep -i "scheduler\|recommendation"
```

**Look for:**
```
INFO:apscheduler.scheduler:Added job "Check recommendations during active hours..."
INFO:app.core.scheduler:Running scheduled recommendation check...
INFO:app.core.scheduler:Found X recommendation(s)
INFO:app.core.scheduler:Total notifications sent: N
```

### Test Deduplication

```bash
# Trigger twice in quick succession
./scripts/test_scheduler.sh <password>
sleep 5
./scripts/test_scheduler.sh <password>
```

Second run should show "No new notifications to send" or fewer notifications.

### Test Time-Based Rules

```bash
# Check current Pacific Time
TZ='America/Los_Angeles' date
```

- During active hours (8 AM - 2 PM PT): Only urgent/high sent
- During quiet hours: All priorities sent

### Query Notification History

```sql
SELECT 
    recommendation_id,
    notification_type,
    priority,
    channels_sent,
    sent_at
FROM recommendation_notifications
ORDER BY sent_at DESC
LIMIT 10;
```

---

## Troubleshooting

### Notifications Not Sending

1. **Check channel configuration:**
   - Verify `.env` has `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`

2. **Check if recommendations exist:**
   ```bash
   curl "http://localhost:8000/api/v1/strategies/options-selling/recommendations" \
     -H "Authorization: Bearer $TOKEN"
   ```

3. **Check time-based filtering:**
   - Verify current Pacific Time
   - Check if recommendations are being filtered

4. **Check server logs:**
   ```bash
   pm2 logs agrawal-backend --lines 100 | grep -i "error\|notification"
   ```

### Scheduler Not Running

1. **Restart backend:**
   ```bash
   pm2 restart agrawal-backend --update-env
   ```

2. **Check dependencies:**
   ```bash
   pip list | grep apscheduler
   ```

3. **Verify startup:**
   ```bash
   pm2 logs agrawal-backend --lines 50 | grep -i "scheduler\|startup"
   ```

### Telegram Bot Not Responding

- Make sure you started a chat with your bot first
- Verify the chat ID is correct
- Check that the bot token is correct

---

## Rate Limits & Costs

### Yahoo Finance API
- No official rate limits (be respectful)
- Recommended: Max 1 request per symbol per 5 minutes
- With 20 positions: ~48 requests/hour (reasonable)

### Telegram API
- Rate limit: 30 messages/second per bot
- Your usage: ~10-20 messages/day (well within limits)

### Twilio WhatsApp
- ~$0.005-0.01 per message (very cheap)

---

## Security Notes

- Keep bot tokens secret (don't commit to git)
- Telegram bot can only send to your configured chat ID
- No one else can use your bot without the token

---

*Last Updated: December 2025*

