#!/usr/bin/env python3
"""
Option Roll Monitoring Script

This script monitors sold option positions and sends notifications when
early roll opportunities arise (when 80%+ profit is captured before expiration).

Usage:
    # Run once manually:
    python scripts/monitor_option_rolls.py
    
    # Run with custom threshold:
    python scripts/monitor_option_rolls.py --threshold 0.70
    
    # Dry run (no notifications, just check):
    python scripts/monitor_option_rolls.py --dry-run

For continuous monitoring, set up a cron job:
    # Run every hour during market hours (9:30 AM - 4:00 PM ET, Mon-Fri)
    30 9-16 * * 1-5 cd /path/to/backend && venv/bin/python scripts/monitor_option_rolls.py

Or add to ecosystem.config.js for PM2:
    {
        name: 'option-monitor',
        script: 'scripts/monitor_option_rolls.py',
        interpreter: 'venv/bin/python',
        cron_restart: '30 9-16 * * 1-5',
        autorestart: false
    }
"""

import sys
import os
import argparse
import logging
from datetime import datetime, date, time
from pathlib import Path

# Add the app directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('option_monitor')


def is_market_hours() -> bool:
    """Check if US stock market is currently open (roughly)."""
    now = datetime.now()
    
    # Skip weekends
    if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    
    # Market hours: 9:30 AM - 4:00 PM ET
    # This is a rough check - doesn't account for holidays or timezone
    current_time = now.time()
    market_open = time(9, 30)
    market_close = time(16, 0)
    
    return market_open <= current_time <= market_close


def send_notification(message: str, alerts_count: int, method: str = 'console'):
    """
    Send notification about roll opportunities.
    
    Supported methods:
    - console: Print to stdout (default)
    - email: Send email (requires SMTP config)
    - slack: Post to Slack (requires webhook URL)
    - pushover: Send push notification (requires API key)
    """
    if method == 'console':
        print("\n" + "=" * 60)
        print(message)
        print("=" * 60 + "\n")
        return
    
    if method == 'email':
        # TODO: Implement email notification
        # Requires: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, NOTIFY_EMAIL
        logger.info("Email notification not yet implemented")
        return
    
    if method == 'slack':
        # TODO: Implement Slack webhook
        # Requires: SLACK_WEBHOOK_URL env variable
        slack_url = os.getenv('SLACK_WEBHOOK_URL')
        if slack_url:
            import requests
            try:
                response = requests.post(slack_url, json={
                    "text": f"🔔 *Option Roll Alert* - {alerts_count} position(s) ready for rolling",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": message}
                        }
                    ]
                })
                if response.status_code == 200:
                    logger.info("Slack notification sent")
                else:
                    logger.error(f"Slack notification failed: {response.text}")
            except Exception as e:
                logger.error(f"Error sending Slack notification: {e}")
        return
    
    if method == 'pushover':
        # TODO: Implement Pushover notification
        # Requires: PUSHOVER_USER_KEY, PUSHOVER_API_TOKEN
        logger.info("Pushover notification not yet implemented")
        return


def run_monitor(
    profit_threshold: float = 0.80,
    dry_run: bool = False,
    notify_method: str = 'console',
    force: bool = False
):
    """
    Main monitoring function.
    
    Args:
        profit_threshold: Minimum profit % to trigger alert (0.80 = 80%)
        dry_run: If True, don't save alerts to DB or send notifications
        notify_method: How to send notifications ('console', 'email', 'slack')
        force: Run even outside market hours
    """
    logger.info(f"Starting option roll monitor (threshold: {profit_threshold*100:.0f}%)")
    
    # Check market hours (unless forced)
    if not force and not is_market_hours():
        logger.info("Market is closed. Skipping check. Use --force to override.")
        return
    
    # Set up database connection
    from app.core.config import settings
    from app.core.database import get_db, engine
    
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        from app.modules.strategies.option_monitor import (
            OptionRollMonitor,
            get_positions_from_db,
            save_alerts_to_db
        )
        
        # Get positions from database
        positions = get_positions_from_db(db)
        
        if not positions:
            logger.info("No open positions with original premium found")
            return
        
        logger.info(f"Found {len(positions)} position(s) to monitor")
        
        # Run the monitor
        monitor = OptionRollMonitor(profit_threshold=profit_threshold)
        alerts = monitor.check_all_positions(positions)
        
        if alerts:
            logger.info(f"Found {len(alerts)} roll opportunity/opportunities!")
            
            # Format message
            message = monitor.format_alert_message(alerts)
            
            if dry_run:
                print("\n[DRY RUN - No notifications sent]")
                print(message)
            else:
                # Save alerts to database
                new_count = save_alerts_to_db(db, alerts)
                logger.info(f"Saved {new_count} new alert(s) to database")
                
                # Send notification
                send_notification(message, len(alerts), notify_method)
        else:
            logger.info("No roll opportunities at this time")
            
            # Log position status for debugging
            for pos in positions:
                logger.debug(f"  {pos.symbol} ${pos.strike_price} {pos.option_type} - "
                           f"original: ${pos.original_premium:.2f}")
    
    except Exception as e:
        logger.error(f"Error during monitoring: {e}", exc_info=True)
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description='Monitor sold options for early roll opportunities'
    )
    parser.add_argument(
        '--threshold', '-t',
        type=float,
        default=0.80,
        help='Profit threshold to trigger alert (default: 0.80 = 80%%)'
    )
    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='Check without saving alerts or sending notifications'
    )
    parser.add_argument(
        '--notify', '-n',
        choices=['console', 'email', 'slack', 'pushover'],
        default='console',
        help='Notification method (default: console)'
    )
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Run even outside market hours'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    run_monitor(
        profit_threshold=args.threshold,
        dry_run=args.dry_run,
        notify_method=args.notify,
        force=args.force
    )


if __name__ == '__main__':
    main()








