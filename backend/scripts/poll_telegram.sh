#!/bin/bash
# Poll Telegram for new reply feedback
# 
# Add to crontab to run every 5 minutes:
#   */5 * * * * /Users/neelpersonal/agrawal-estate-planner/backend/scripts/poll_telegram.sh >> /tmp/telegram_poller.log 2>&1

cd /Users/neelpersonal/agrawal-estate-planner/backend
source venv/bin/activate

echo "$(date): Polling Telegram for replies..."
python -m app.shared.services.telegram_poller

echo "$(date): Done"


