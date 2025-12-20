"""
Scheduler Service for Automated Recommendation Checks

Uses APScheduler to periodically check for recommendations and send notifications
based on time-based rules.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.strategies.strategy_service import StrategyService
from app.modules.strategies.models import RecommendationNotification
from app.shared.services.notifications import get_notification_service

logger = logging.getLogger(__name__)

# Pacific Time timezone
PT = pytz.timezone('America/Los_Angeles')


class RecommendationScheduler:
    """Manages scheduled recommendation checks and notifications."""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        logger.info("Recommendation scheduler started")
    
    def setup_schedules(self):
        """Set up all scheduled jobs."""
        # New schedule:
        # 1. First run: 6:30 AM (with technical analysis)
        # 2. Second run: 8:00 AM
        # 3. Third run: 11:30 AM
        # 4. Fourth run: 12:30 PM
        # 5. After hours: Every 2 hours (2 PM, 4 PM, 6 PM, 8 PM, 10 PM, 12 AM)
        # 6. Weekends: Every 4 hours (12 AM, 4 AM, 8 AM, 12 PM, 4 PM, 8 PM)
        
        # Daily full technical analysis at 6:30 AM PT (first run of the day)
        self.scheduler.add_job(
            self.run_full_technical_analysis,
            trigger=CronTrigger(
                hour=6,
                minute=30,
                day_of_week='mon-fri',
                timezone=PT
            ),
            id='daily_technical_analysis',
            name='Daily full technical analysis (6:30 AM PT)',
            replace_existing=True
        )
        
        # Second run: 8:00 AM PT (weekdays)
        self.scheduler.add_job(
            self.check_and_notify,
            trigger=CronTrigger(
                hour=8,
                minute=0,
                day_of_week='mon-fri',
                timezone=PT
            ),
            id='check_8am',
            name='Check recommendations at 8:00 AM PT',
            replace_existing=True
        )
        
        # Third run: 11:30 AM PT (weekdays)
        self.scheduler.add_job(
            self.check_and_notify,
            trigger=CronTrigger(
                hour=11,
                minute=30,
                day_of_week='mon-fri',
                timezone=PT
            ),
            id='check_1130am',
            name='Check recommendations at 11:30 AM PT',
            replace_existing=True
        )
        
        # Fourth run: 12:30 PM PT (weekdays)
        self.scheduler.add_job(
            self.check_and_notify,
            trigger=CronTrigger(
                hour=12,
                minute=30,
                day_of_week='mon-fri',
                timezone=PT
            ),
            id='check_1230pm',
            name='Check recommendations at 12:30 PM PT',
            replace_existing=True
        )
        
        # After hours (after 2 PM PT): Check every 2 hours (2 PM, 4 PM, 6 PM, 8 PM, 10 PM, 12 AM)
        self.scheduler.add_job(
            self.check_and_notify,
            trigger=CronTrigger(
                hour='14,16,18,20,22,0',  # 2 PM, 4 PM, 6 PM, 8 PM, 10 PM, 12 AM
                minute='0',
                day_of_week='mon-fri',
                timezone=PT
            ),
            id='check_after_hours',
            name='Check recommendations after hours (every 2 hours)',
            replace_existing=True
        )
        
        # Weekends: Check every 4 hours (12 AM, 4 AM, 8 AM, 12 PM, 4 PM, 8 PM)
        self.scheduler.add_job(
            self.check_and_notify,
            trigger=CronTrigger(
                hour='0,4,8,12,16,20',  # Every 4 hours
                minute='0',
                day_of_week='sat,sun',
                timezone=PT
            ),
            id='check_weekends',
            name='Check recommendations on weekends (every 4 hours)',
            replace_existing=True
        )
        
        logger.info("Scheduled jobs configured")
    
    def run_full_technical_analysis(self):
        """
        Run full technical analysis at 6:30 AM PT (first run of the day).
        
        This pre-computes technical indicators for all holdings and caches them
        for faster recommendation generation during the day.
        """
        db: Session = SessionLocal()
        try:
            logger.info("Running daily full technical analysis (6:30 AM PT)...")
            
            from app.modules.strategies.technical_analysis import get_technical_analysis_service
            from sqlalchemy import text
            
            ta_service = get_technical_analysis_service()
            
            # Get all unique symbols from holdings
            result = db.execute(text("""
                SELECT DISTINCT ih.symbol 
                FROM investment_holdings ih
                JOIN investment_accounts ia ON ih.account_id = ia.account_id AND ih.source = ia.source
                WHERE ih.quantity >= 100
                AND ih.symbol NOT LIKE '%CASH%'
                AND ih.symbol NOT LIKE '%MONEY%'
                AND ia.account_type IN ('brokerage', 'retirement', 'ira', 'roth_ira')
            """))
            
            symbols = [row[0] for row in result]
            logger.info(f"Analyzing {len(symbols)} symbols: {symbols}")
            
            # Pre-fetch technical indicators (this warms up the cache)
            for symbol in symbols:
                try:
                    indicators = ta_service.get_technical_indicators(symbol)
                    if indicators:
                        logger.debug(f"Cached TA for {symbol}: RSI={indicators.rsi_14:.1f}, Trend={indicators.trend}")
                except Exception as e:
                    logger.warning(f"Failed to fetch TA for {symbol}: {e}")
            
            logger.info(f"Completed technical analysis for {len(symbols)} symbols")
            
            # Now run the normal recommendation check
            self.check_and_notify(send_notifications=True)
            
        except Exception as e:
            logger.error(f"Error in daily technical analysis: {e}", exc_info=True)
        finally:
            db.close()
    
    def check_and_notify(self, send_notifications: bool = True):
        """Check for recommendations and send notifications based on time rules."""
        db: Session = SessionLocal()
        try:
            logger.info(f"Running scheduled recommendation check (notifications: {send_notifications})...")
            
            # Generate recommendations
            service = StrategyService(db)
            recommendations = service.generate_recommendations({
                "default_premium": 60,
                "profit_threshold": 0.80
            })
            
            if not recommendations:
                logger.info("No recommendations found")
                return
            
            # Convert to dict
            recommendations_data = []
            for rec in recommendations:
                rec_dict = rec.dict()
                if rec_dict.get("created_at"):
                    rec_dict["created_at"] = rec_dict["created_at"].isoformat()
                if rec_dict.get("expires_at"):
                    rec_dict["expires_at"] = rec_dict["expires_at"].isoformat()
                recommendations_data.append(rec_dict)
            
            # Filter and send notifications based on time rules
            # IMPORTANT: Save the SAME recommendations that are sent to notifications
            if send_notifications:
                sent_recommendations = self._send_time_based_notifications(db, recommendations_data)
                
                # Save the recommendations that were actually sent to history for web UI
                if sent_recommendations:
                    try:
                        from app.modules.strategies.recommendations import OptionsStrategyRecommendationService
                        rec_service = OptionsStrategyRecommendationService(db)
                        # Convert dicts back to StrategyRecommendation objects for saving
                        from app.modules.strategies.recommendations import StrategyRecommendation
                        rec_objects = []
                        for rec_dict in sent_recommendations:
                            # Extract account_name from context if not already set
                            context = rec_dict.get("context", {})
                            account_name = rec_dict.get("account_name") or context.get("account_name") or context.get("account")
                            symbol = rec_dict.get("symbol") or context.get("symbol")
                            
                            # Reconstruct StrategyRecommendation from dict
                            rec_obj = StrategyRecommendation(
                                id=rec_dict.get("id"),
                                type=rec_dict.get("type"),
                                category=rec_dict.get("category"),
                                priority=rec_dict.get("priority"),
                                title=rec_dict.get("title"),
                                description=rec_dict.get("description"),
                                rationale=rec_dict.get("rationale"),
                                action=rec_dict.get("action"),
                                action_type=rec_dict.get("action_type"),
                                potential_income=rec_dict.get("potential_income"),
                                potential_risk=rec_dict.get("potential_risk"),
                                time_horizon=rec_dict.get("time_horizon"),
                                symbol=symbol,
                                account_name=account_name,
                                context=context,
                                created_at=datetime.fromisoformat(rec_dict["created_at"]) if rec_dict.get("created_at") else datetime.utcnow(),
                                expires_at=datetime.fromisoformat(rec_dict["expires_at"]) if rec_dict.get("expires_at") else None
                            )
                            rec_objects.append(rec_obj)
                        
                        saved_count = rec_service.save_recommendations_to_history(rec_objects)
                        logger.info(f"Saved {saved_count} sent recommendations to history for web UI")
                    except Exception as save_error:
                        logger.error(f"Failed to save sent recommendations to history: {save_error}", exc_info=True)
                        # Continue even if saving fails
            else:
                # If notifications are disabled, still save all recommendations for web UI
                if recommendations:
                    try:
                        from app.modules.strategies.recommendations import OptionsStrategyRecommendationService
                        rec_service = OptionsStrategyRecommendationService(db)
                        saved_count = rec_service.save_recommendations_to_history(recommendations)
                        logger.info(f"Saved {saved_count} recommendations to history for web UI (notifications disabled)")
                    except Exception as save_error:
                        logger.warning(f"Failed to save recommendations to history: {save_error}")
                        # Continue even if saving fails
                logger.info(f"Found {len(recommendations_data)} recommendation(s) (notifications disabled)")
            
        except Exception as e:
            logger.error(f"Error in scheduled recommendation check: {e}", exc_info=True)
        finally:
            db.close()
    
    def _send_time_based_notifications(
        self,
        db: Session,
        recommendations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Send notifications based on time-based rules.
        
        Returns:
            List of recommendations that were actually sent (for saving to history)
        """
        from app.modules.strategies.weekly_recommendation_filter import (
            should_send_recommendation,
            record_recommendation_sent
        )
        
        now_pt = datetime.now(PT)
        current_hour = now_pt.hour
        is_weekend = now_pt.weekday() >= 5
        
        # Determine notification window (Pacific Time)
        # 8 AM - 2 PM PT: Active hours (send urgent + high immediately, skip medium/low)
        # Before 8 AM or after 2 PM PT: Quiet hours (send all, but batch medium/low)
        is_active_hours = 8 <= current_hour < 14 and not is_weekend
        
        notification_service = get_notification_service()
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        
        # Separate recommendations by type and priority
        # Handle ALL bull put strategies (both bull_put_spread and mega_cap_bull_put) with limits
        bull_put_recs = [r for r in recommendations if r.get("type") in ["bull_put_spread", "mega_cap_bull_put"]]
        other_recs = [r for r in recommendations if r.get("type") not in ["bull_put_spread", "mega_cap_bull_put"]]
        
        # Handle bull put spread recommendations with weekly limits
        bull_put_to_send = []
        for rec in bull_put_recs:
            strategy_type = rec.get("type", "bull_put_spread")
            should_send, reason = should_send_recommendation(db, strategy_type, rec, min_profit_delta=10.0)
            if should_send:
                bull_put_to_send.append(rec)
            else:
                logger.info(f"Skipping {strategy_type} recommendation: {reason}")
        
        # Filter other recommendations normally
        urgent_recs = [r for r in other_recs if r.get("priority") == "urgent"]
        high_recs = [r for r in other_recs if r.get("priority") == "high"]
        medium_recs = [r for r in other_recs if r.get("priority") == "medium"]
        low_recs = [r for r in other_recs if r.get("priority") == "low"]
        
        sent_count = 0
        sent_recommendations = []  # Track all recommendations that were actually sent
        
        # Send bull put spread recommendations (if any passed weekly filter)
        # Limit to top 5 to avoid overwhelming notifications
        if bull_put_to_send:
            # Sort by profit (descending) and take the top 5
            bull_put_to_send.sort(key=lambda x: x.get("context", {}).get("max_profit", 0), reverse=True)
            top_bull_puts = bull_put_to_send[:5]  # Limit to top 5
            
            results = notification_service.send_recommendation_notification(
                top_bull_puts,
                priority_filter="high"
            )
            self._record_notifications(db, top_bull_puts, results)
            for rec in top_bull_puts:
                record_recommendation_sent(db, rec.get("type", "bull_put_spread"), rec)
            sent_count += len(top_bull_puts)
            sent_recommendations.extend(top_bull_puts)
            logger.info(f"Sent {len(top_bull_puts)} bull put spread notification(s) (top {len(top_bull_puts)} of {len(bull_put_to_send)} found)")
        
        # Always send urgent immediately
        if urgent_recs:
            to_send = self._filter_new_or_escalated(db, urgent_recs)
            if to_send:
                results = notification_service.send_recommendation_notification(
                    to_send,
                    priority_filter="urgent"
                )
                self._record_notifications(db, to_send, results)
                sent_count += len(to_send)
                sent_recommendations.extend(to_send)
                logger.info(f"Sent {len(to_send)} urgent notification(s)")
        
        # High priority: immediate during active hours (8 AM - 2 PM PT), send in quiet hours too
        if high_recs:
            to_send = self._filter_new_or_escalated(db, high_recs)
            if to_send:
                results = notification_service.send_recommendation_notification(
                    to_send,
                    priority_filter="high"
                )
                self._record_notifications(db, to_send, results)
                sent_count += len(to_send)
                sent_recommendations.extend(to_send)
                if is_active_hours:
                    logger.info(f"Sent {len(to_send)} high priority notification(s) (active hours)")
                else:
                    logger.info(f"Sent {len(to_send)} high priority notification(s) (quiet hours)")
        
        # Medium/Low: Only send before 8 AM or after 2 PM PT (not during 8 AM - 2 PM)
        if not is_active_hours:
            medium_low_recs = medium_recs + low_recs
            if medium_low_recs:
                to_send = self._filter_new_or_escalated(db, medium_low_recs)
                if to_send:
                    results = notification_service.send_recommendation_notification(
                        to_send,
                        priority_filter="low"  # Include all medium/low
                    )
                    self._record_notifications(db, to_send, results)
                    sent_count += len(to_send)
                    sent_recommendations.extend(to_send)
                    logger.info(f"Sent {len(to_send)} medium/low priority notification(s) (quiet hours)")
        else:
            # During active hours, skip medium/low
            if medium_recs or low_recs:
                logger.info(f"Skipping {len(medium_recs) + len(low_recs)} medium/low priority recommendation(s) during active hours (8 AM - 2 PM PT)")
        
        if sent_count > 0:
            logger.info(f"Total notifications sent: {sent_count}")
        else:
            logger.info("No new notifications to send (all filtered by deduplication)")
        
        return sent_recommendations
    
    def _filter_new_or_escalated(
        self,
        db: Session,
        recommendations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter recommendations to only include new ones or those with priority escalation."""
        filtered = []
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        
        for rec in recommendations:
            rec_id = rec.get("id")
            current_priority = rec.get("priority", "low")
            
            # Check last notification for this recommendation
            last_notif = db.query(RecommendationNotification).filter(
                RecommendationNotification.recommendation_id == rec_id
            ).order_by(RecommendationNotification.sent_at.desc()).first()
            
            if not last_notif:
                # New recommendation - always send
                filtered.append(rec)
            else:
                # Check if priority escalated
                last_priority = last_notif.priority
                if priority_order.get(current_priority, 99) < priority_order.get(last_priority, 99):
                    # Priority increased - send
                    filtered.append(rec)
                elif last_notif.next_notification_allowed_at:
                    # Check if cooldown expired
                    if datetime.utcnow() >= last_notif.next_notification_allowed_at:
                        filtered.append(rec)
                # Otherwise, skip (already notified and no escalation)
        
        return filtered
    
    def _record_notifications(
        self,
        db: Session,
        recommendations: List[Dict[str, Any]],
        channel_results: Dict[str, bool]
    ):
        """Record that notifications were sent."""
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        
        for rec in recommendations:
            rec_id = rec.get("id")
            priority = rec.get("priority", "low")
            
            # Check if this is a priority escalation
            last_notif = db.query(RecommendationNotification).filter(
                RecommendationNotification.recommendation_id == rec_id
            ).order_by(RecommendationNotification.sent_at.desc()).first()
            
            notification_type = "new"
            previous_priority = None
            
            if last_notif:
                if priority_order.get(priority, 99) < priority_order.get(last_notif.priority, 99):
                    notification_type = "priority_escalated"
                    previous_priority = last_notif.priority
                else:
                    notification_type = "update"
            
            # Calculate next notification allowed time based on priority
            cooldown_minutes = {
                "urgent": 0,
                "high": 0,
                "medium": 30,
                "low": 60
            }
            cooldown = cooldown_minutes.get(priority, 60)
            next_allowed = datetime.utcnow() + timedelta(minutes=cooldown) if cooldown > 0 else None
            
            notification = RecommendationNotification(
                recommendation_id=rec_id,
                notification_type=notification_type,
                priority=priority,
                previous_priority=previous_priority,
                channels_sent=channel_results,
                next_notification_allowed_at=next_allowed
            )
            db.add(notification)
        
        db.commit()
    
    def shutdown(self):
        """Shutdown the scheduler."""
        self.scheduler.shutdown()
        logger.info("Recommendation scheduler stopped")


# Global scheduler instance
_scheduler: Optional[RecommendationScheduler] = None


def get_scheduler() -> Optional[RecommendationScheduler]:
    """Get the global scheduler instance."""
    return _scheduler


def start_scheduler():
    """Start the recommendation scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = RecommendationScheduler()
        _scheduler.setup_schedules()
        logger.info("Recommendation scheduler started and configured")
        print("✓ Recommendation scheduler started and configured")  # Also print for visibility
    else:
        logger.info("Recommendation scheduler already running")
        print("✓ Recommendation scheduler already running")  # Also print for visibility


def stop_scheduler():
    """Stop the recommendation scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None
        logger.info("Recommendation scheduler stopped")


def trigger_manual_check(send_notifications: bool = True):
    """Manually trigger a recommendation check (for testing)."""
    if _scheduler:
        _scheduler.check_and_notify(send_notifications=send_notifications)
    else:
        # Create temporary scheduler for one-time check
        temp_scheduler = RecommendationScheduler()
        temp_scheduler.check_and_notify(send_notifications=send_notifications)
        temp_scheduler.shutdown()

