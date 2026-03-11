# Notifications App

## Goal

Provide timely alerts and recommendations across all modules. Deliver actionable notifications via web UI and Telegram integration for time-sensitive financial decisions.

---

## Features

### Current Features

1. **Notification Types**
   - Options recommendations
   - Tax payment reminders
   - Price alerts
   - Expense forecasts
   - Document expiration warnings

2. **Delivery Channels**
   - Web UI notifications
   - Telegram bot integration
   - In-app notification center

3. **Smart Filtering**
   - Notification aggregation
   - Priority-based delivery
   - User preference settings

4. **Notification Management**
   - Read/unread tracking
   - Dismissal handling
   - Action tracking

---

## Roadmap

- [ ] Email notifications
- [ ] Push notifications (mobile)
- [ ] Notification scheduling
- [ ] Digest mode (daily summary)

---

## Architecture

### Frontend
- **Page:** `/pages/Notifications.tsx`
- **Route:** `/notifications`

### Backend
- **Module:** `/backend/app/modules/strategies/` (notification services)

### Data Model

Key tables:
- `notifications` - Notification records
- `notification_preferences` - User settings
