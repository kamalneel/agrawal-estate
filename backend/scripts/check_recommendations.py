#!/usr/bin/env python3
"""
Check for strategy recommendations and send notifications.

This script can be run periodically (e.g., via cron) to check for new
recommendations and send notifications.

Usage:
    python -m scripts.check_recommendations [--priority high] [--dry-run]
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.modules.strategies.recommendations import OptionsStrategyRecommendationService
from app.shared.services.notifications import get_notification_service

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description='Check for strategy recommendations and send notifications'
    )
    parser.add_argument(
        '--priority',
        choices=['urgent', 'high', 'medium', 'low'],
        default='high',
        help='Minimum priority to notify (default: high)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Check without sending notifications'
    )
    parser.add_argument(
        '--default-premium',
        type=float,
        default=60,
        help='Default premium per contract (default: 60)'
    )
    parser.add_argument(
        '--profit-threshold',
        type=float,
        default=0.80,
        help='Profit threshold for early rolls (default: 0.80)'
    )
    
    args = parser.parse_args()
    
    # Set up database connection
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        logger.info("Checking for strategy recommendations...")
        
        # Generate recommendations
        service = OptionsStrategyRecommendationService(db)
        recommendations = service.generate_recommendations({
            "default_premium": args.default_premium,
            "profit_threshold": args.profit_threshold
        })
        
        if not recommendations:
            logger.info("No recommendations found")
            return
        
        logger.info(f"Found {len(recommendations)} recommendation(s)")
        
        # Convert to dict for notification service
        recommendations_data = []
        for rec in recommendations:
            rec_dict = rec.dict()
            if rec_dict.get("created_at"):
                rec_dict["created_at"] = rec_dict["created_at"].isoformat()
            if rec_dict.get("expires_at"):
                rec_dict["expires_at"] = rec_dict["expires_at"].isoformat()
            recommendations_data.append(rec_dict)
        
        # Filter by priority
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        min_priority = priority_order.get(args.priority, 99)
        filtered = [
            r for r in recommendations_data
            if priority_order.get(r.get("priority", "low"), 99) <= min_priority
        ]
        
        if not filtered:
            logger.info(f"No recommendations meet priority threshold: {args.priority}")
            return
        
        logger.info(f"{len(filtered)} recommendation(s) meet priority threshold")
        
        # Print recommendations
        for rec in filtered:
            logger.info(f"  [{rec['priority'].upper()}] {rec['title']}")
        
        # Send notifications
        if args.dry_run:
            logger.info("[DRY RUN] Would send notifications for recommendations")
        else:
            notification_service = get_notification_service()
            results = notification_service.send_recommendation_notification(
                filtered,
                priority_filter=args.priority
            )
            
            if results:
                for channel, success in results.items():
                    if success:
                        logger.info(f"✓ Notification sent via {channel}")
                    else:
                        logger.warning(f"✗ Failed to send notification via {channel}")
            else:
                logger.warning("No notification channels configured")
    
    except Exception as e:
        logger.error(f"Error checking recommendations: {e}", exc_info=True)
        sys.exit(1)
    
    finally:
        db.close()


if __name__ == '__main__':
    main()



