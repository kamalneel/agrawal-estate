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
        """
        Set up scheduled jobs per V3 Algorithm Specification.
        
        V3 Schedule (Pacific Time, Weekdays Only):
        ============================================
        Scan 1: 6:00 AM  - Main Daily Scan (comprehensive + technical analysis)
        Scan 2: 8:00 AM  - Post-Opening Urgent (state changes from market open)
        Scan 3: 12:00 PM - Midday Opportunities (intraday changes)
        Scan 4: 12:45 PM - Pre-Close Urgent (expiring today, smart assignment)
        Scan 5: 8:00 PM  - Evening Planning (next day preparation)
        
        NO after-hours notifications between 1 PM and 8 PM.
        NO weekend notifications (market closed).
        """
        
        # =================================================================
        # SCAN 1: 6:00 AM - Main Daily Scan (with technical analysis)
        # =================================================================
        # Purpose: Comprehensive evaluation before user wakes up
        # Evaluates: All positions, pull-backs, ITM escapes, weekly rolls,
        #           earnings/dividend alerts, new sell opportunities
        #           Monday only: Buy-back reminders
        self.scheduler.add_job(
            self.run_full_technical_analysis,
            trigger=CronTrigger(
                hour=6,
                minute=0,
                day_of_week='mon-fri',
                timezone=PT
            ),
            id='scan_1_main_daily',
            name='V3 Scan 1: Main Daily Scan (6:00 AM PT)',
            replace_existing=True
        )
        
        # =================================================================
        # SCAN 2: 8:00 AM - Post-Opening Urgent (V2)
        # =================================================================
        # Purpose: Catch urgent state changes from market open volatility
        # Evaluates: Newly ITM positions, new pull-back opportunities,
        #           earnings TODAY, positions >10% deeper ITM, expiring TODAY
        # NOTE: Using V2 system - notifications reference snapshot numbers
        self.scheduler.add_job(
            lambda: self.check_and_notify_v2(scan_type='8am_post_open'),
            trigger=CronTrigger(
                hour=8,
                minute=0,
                day_of_week='mon-fri',
                timezone=PT
            ),
            id='scan_2_post_open',
            name='V3 Scan 2: Post-Opening Urgent (8:00 AM PT) [V2]',
            replace_existing=True
        )
        
        # =================================================================
        # SCAN 3: 12:00 PM - Midday Opportunities (V2)
        # =================================================================
        # Purpose: Check for intraday opportunities
        # Evaluates: Pull-back opportunities, significant moves (>10% since morning)
        self.scheduler.add_job(
            lambda: self.check_and_notify_v2(scan_type='12pm_midday'),
            trigger=CronTrigger(
                hour=12,
                minute=0,
                day_of_week='mon-fri',
                timezone=PT
            ),
            id='scan_3_midday',
            name='V3 Scan 3: Midday Opportunities (12:00 PM PT) [V2]',
            replace_existing=True
        )
        
        # =================================================================
        # SCAN 4: 12:45 PM - Pre-Close Urgent (V2)
        # =================================================================
        # Purpose: Last 15 minutes before market close (1:00 PM PT)
        # Evaluates: Expiring TODAY, Smart Assignment (IRA), Triple Witching
        self.scheduler.add_job(
            lambda: self.check_and_notify_v2(scan_type='1245pm_pre_close'),
            trigger=CronTrigger(
                hour=12,
                minute=45,
                day_of_week='mon-fri',
                timezone=PT
            ),
            id='scan_4_pre_close',
            name='V3 Scan 4: Pre-Close Urgent (12:45 PM PT) [V2]',
            replace_existing=True
        )
        
        # =================================================================
        # SCAN 5: 8:00 PM - Evening Planning (V2)
        # =================================================================
        # Purpose: Next day preparation (informational only)
        # Evaluates: Earnings TOMORROW, Ex-dividend TOMORROW, 
        #           Positions expiring TOMORROW
        self.scheduler.add_job(
            lambda: self.check_and_notify_v2(scan_type='8pm_evening'),
            trigger=CronTrigger(
                hour=20,
                minute=0,
                day_of_week='mon-fri',
                timezone=PT
            ),
            id='scan_5_evening',
            name='V3 Scan 5: Evening Planning (8:00 PM PT)',
            replace_existing=True
        )
        
        # =================================================================
        # NO AFTER-HOURS OR WEEKEND SCANS
        # =================================================================
        # Per V3 spec: Only 5 scans per weekday, no weekend notifications
        # Market is closed, no action can be taken
        
        logger.info("V3 Schedule configured: 5 daily scans (6AM, 8AM, 12PM, 12:45PM, 8PM) weekdays only")

        # =================================================================
        # EXPENSE NOTIFICATIONS
        # =================================================================
        # Purpose: Remind user to transfer money for upcoming expenses
        # Runs daily at 6:00 AM PT (7 days/week, before main scan)
        # Checks for expenses due tomorrow and sends Telegram notification
        self.scheduler.add_job(
            self.send_expense_notifications,
            trigger=CronTrigger(
                hour=6,
                minute=0,
                timezone=PT
            ),
            id='expense_notifications_daily',
            name='Expense Notifications (6:00 AM PT Daily)',
            replace_existing=True
        )

        logger.info("Expense notifications configured: daily check at 6:00 AM PT (7 days/week)")

        # =================================================================
        # RLHF LEARNING JOBS
        # =================================================================
        
        # Daily Reconciliation: 9:00 PM PT (after market close)
        # Matches today's recommendations to executions
        self.scheduler.add_job(
            self.run_daily_reconciliation,
            trigger=CronTrigger(
                hour=21,
                minute=0,
                day_of_week='mon-fri',
                timezone=PT
            ),
            id='rlhf_daily_reconciliation',
            name='RLHF: Daily Reconciliation (9:00 PM PT)',
            replace_existing=True
        )
        
        # Weekly Learning Summary: Saturday 9:00 AM PT
        # Generates weekly analysis and patterns
        self.scheduler.add_job(
            self.run_weekly_learning_summary,
            trigger=CronTrigger(
                hour=9,
                minute=0,
                day_of_week='sat',
                timezone=PT
            ),
            id='rlhf_weekly_summary',
            name='RLHF: Weekly Learning Summary (Saturday 9:00 AM PT)',
            replace_existing=True
        )
        
        # Outcome Tracking: 10:00 PM PT daily
        # Updates position outcomes for completed positions
        self.scheduler.add_job(
            self.run_outcome_tracking,
            trigger=CronTrigger(
                hour=22,
                minute=0,
                day_of_week='mon-fri',
                timezone=PT
            ),
            id='rlhf_outcome_tracking',
            name='RLHF: Outcome Tracking (10:00 PM PT)',
            replace_existing=True
        )
        
        logger.info("RLHF Learning jobs configured: daily reconciliation (9PM), weekly summary (Sat 9AM), outcome tracking (10PM)")
    
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
            
            # Now run the V2-native recommendation check with notifications
            self.check_and_notify_v2(send_notifications=True, scan_type='6am_main')
            
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
        
        # ================================================================
        # CONSOLIDATE ALL RECOMMENDATIONS INTO A SINGLE MESSAGE
        # This ensures grouping by account works correctly
        # ================================================================
        all_to_send = []  # Collect all recommendations to send in one message
        
        # 1. Bull put spread recommendations (if any passed weekly filter)
        # Limit to top 5 to avoid overwhelming notifications
        if bull_put_to_send:
            # Sort by profit (descending) and take the top 5
            bull_put_to_send.sort(key=lambda x: x.get("context", {}).get("max_profit", 0), reverse=True)
            top_bull_puts = bull_put_to_send[:5]  # Limit to top 5
            for rec in top_bull_puts:
                record_recommendation_sent(db, rec.get("type", "bull_put_spread"), rec)
            all_to_send.extend(top_bull_puts)
            logger.info(f"Queued {len(top_bull_puts)} bull put spread notification(s) (top {len(top_bull_puts)} of {len(bull_put_to_send)} found)")
        
        # 2. Always include urgent
        if urgent_recs:
            to_send = self._filter_new_or_escalated(db, urgent_recs)
            if to_send:
                all_to_send.extend(to_send)
                logger.info(f"Queued {len(to_send)} urgent notification(s)")
        
        # 3. High priority: always send
        if high_recs:
            to_send = self._filter_new_or_escalated(db, high_recs)
            if to_send:
                all_to_send.extend(to_send)
                if is_active_hours:
                    logger.info(f"Queued {len(to_send)} high priority notification(s) (active hours)")
                else:
                    logger.info(f"Queued {len(to_send)} high priority notification(s) (quiet hours)")
        
        # 4. Medium/Low: Only send before 8 AM or after 2 PM PT (not during 8 AM - 2 PM)
        if not is_active_hours:
            medium_low_recs = medium_recs + low_recs
            if medium_low_recs:
                to_send = self._filter_new_or_escalated(db, medium_low_recs)
                if to_send:
                    all_to_send.extend(to_send)
                    logger.info(f"Queued {len(to_send)} medium/low priority notification(s) (quiet hours)")
        else:
            # During active hours, skip medium/low
            if medium_recs or low_recs:
                logger.info(f"Skipping {len(medium_recs) + len(low_recs)} medium/low priority recommendation(s) during active hours (8 AM - 2 PM PT)")
        
        # ================================================================
        # DUAL NOTIFICATION MODE: VERBOSE + SMART
        # ================================================================
        # 1. VERBOSE MODE: Send ALL recommendations (no filtering)
        #    Every snapshot triggers a notification
        # 2. SMART MODE: Send filtered recommendations (current behavior)
        #    Only new or changed recommendations
        # ================================================================
        
        # Get all recommendations (excluding bull put which already has limits)
        all_for_verbose = other_recs.copy()  # All other_recs without smart filtering
        # Filter out NO_ACTION and HOLD for verbose mode
        all_for_verbose = [r for r in all_for_verbose if r.get("action_type") not in ("NO_ACTION", "HOLD")]
        
        # 1. VERBOSE MODE: Send ALL recommendations
        if all_for_verbose:
            logger.info(f"[VERBOSE MODE] Sending {len(all_for_verbose)} recommendation(s)")
            verbose_results = notification_service.send_recommendation_notification(
                all_for_verbose,
                priority_filter=None,
                notification_mode='verbose'
            )
            self._record_notifications(db, all_for_verbose, verbose_results, notification_mode='verbose')
            sent_recommendations.extend(all_for_verbose)
            logger.info(f"[VERBOSE MODE] Sent {len(all_for_verbose)} notification(s)")
        else:
            logger.info("[VERBOSE MODE] No recommendations to send")
        
        # 2. SMART MODE: Send filtered recommendations
        if all_to_send:
            logger.info(f"[SMART MODE] Sending {len(all_to_send)} filtered recommendation(s)")
            smart_results = notification_service.send_recommendation_notification(
                all_to_send,
                priority_filter=None,
                notification_mode='smart'
            )
            self._record_notifications(db, all_to_send, smart_results, notification_mode='smart')
            sent_count = len(all_to_send)
            # Don't add to sent_recommendations again (already added in verbose)
            logger.info(f"[SMART MODE] Sent {sent_count} notification(s)")
        else:
            logger.info("[SMART MODE] No new/changed notifications to send")
        
        total_verbose = len(all_for_verbose) if all_for_verbose else 0
        total_smart = len(all_to_send) if all_to_send else 0
        
        if total_verbose > 0 or total_smart > 0:
            logger.info(f"Total notifications sent: {total_verbose} verbose + {total_smart} smart")
        else:
            logger.info("No notifications to send")
        
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
        channel_results: Dict[str, bool],
        notification_mode: str = 'smart'
    ):
        """
        Record that notifications were sent.
        
        Args:
            db: Database session
            recommendations: List of recommendation dicts
            channel_results: Results from notification service
            notification_mode: 'verbose' or 'smart'
        """
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        telegram_message_id = channel_results.get("telegram_message_id")
        
        for rec in recommendations:
            rec_id = rec.get("id")
            priority = rec.get("priority", "low")
            
            # Check if this is a priority escalation (only for smart mode)
            last_notif = db.query(RecommendationNotification).filter(
                RecommendationNotification.recommendation_id == rec_id,
                RecommendationNotification.notification_mode == notification_mode
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
            # For verbose mode, use shorter cooldowns (or no cooldown)
            if notification_mode == 'verbose':
                cooldown_minutes = {
                    "urgent": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0
                }
            else:
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
                notification_mode=notification_mode,
                channels_sent=channel_results,
                next_notification_allowed_at=next_allowed
            )
            db.add(notification)
            
            # === V2: Mark corresponding snapshot as notified ===
            self._mark_v2_snapshot_notified(
                db, rec, 
                telegram_message_id=telegram_message_id,
                notification_type=notification_type,
                notification_mode=notification_mode
            )
        
        db.commit()
    
    def _mark_v2_snapshot_notified(
        self,
        db: Session,
        rec: Dict[str, Any],
        telegram_message_id: int = None,
        notification_type: str = "new",
        notification_mode: str = "smart"
    ):
        """
        Mark the latest V2 snapshot as notified.
        
        This keeps the V2 model in sync with notifications.
        
        Args:
            db: Database session
            rec: Recommendation dict
            telegram_message_id: Message ID from Telegram
            notification_type: 'new', 'update', 'priority_escalated'
            notification_mode: 'verbose' or 'smart'
        """
        try:
            from app.modules.strategies.recommendation_models import (
                PositionRecommendation,
                RecommendationSnapshot,
                generate_recommendation_id
            )
            from datetime import date
            
            context = rec.get("context", {})
            symbol = context.get("symbol")
            account_name = context.get("account_name") or context.get("account")
            source_strike = context.get("current_strike") or context.get("strike_price")
            source_expiration_str = context.get("current_expiration") or context.get("expiration_date")
            option_type = context.get("option_type", "call")
            
            if not symbol or not source_strike or not source_expiration_str:
                return
            
            # Parse expiration
            if isinstance(source_expiration_str, str):
                source_expiration = date.fromisoformat(source_expiration_str)
            else:
                source_expiration = source_expiration_str
            
            # Generate recommendation ID
            rec_id = generate_recommendation_id(
                symbol, float(source_strike), source_expiration, option_type, account_name
            )
            
            # Find the V2 recommendation
            v2_rec = db.query(PositionRecommendation).filter(
                PositionRecommendation.recommendation_id == rec_id,
                PositionRecommendation.status == 'active'
            ).first()
            
            if not v2_rec:
                return
            
            # Get the latest snapshot
            latest_snapshot = db.query(RecommendationSnapshot).filter(
                RecommendationSnapshot.recommendation_id == v2_rec.id
            ).order_by(RecommendationSnapshot.snapshot_number.desc()).first()
            
            if latest_snapshot:
                now = datetime.utcnow()
                
                # Update mode-specific fields
                if notification_mode == 'verbose':
                    latest_snapshot.verbose_notification_sent = True
                    latest_snapshot.verbose_notification_at = now
                elif notification_mode == 'smart':
                    latest_snapshot.smart_notification_sent = True
                    latest_snapshot.smart_notification_at = now
                
                # Update general fields if this is the first notification
                if not latest_snapshot.notification_sent:
                    latest_snapshot.notification_sent = True
                    latest_snapshot.notification_sent_at = now
                    latest_snapshot.notification_channel = "telegram"
                    latest_snapshot.telegram_message_id = telegram_message_id
                    latest_snapshot.notification_decision = f"sent_{notification_type}"
                    latest_snapshot.notification_mode = notification_mode
                    
                    # Update recommendation stats (only count once per snapshot)
                    v2_rec.total_notifications_sent = (v2_rec.total_notifications_sent or 0) + 1
                    v2_rec.updated_at = now
                elif latest_snapshot.notification_mode and notification_mode not in latest_snapshot.notification_mode:
                    # Update mode to 'both' if we're adding a second mode
                    latest_snapshot.notification_mode = 'both'
                
                logger.debug(f"[V2_NOTIFY] Marked snapshot #{latest_snapshot.snapshot_number} for {rec_id} as notified ({notification_mode} mode)")
                
        except Exception as e:
            logger.error(f"[V2_NOTIFY] Error marking snapshot as notified: {e}")
    
    # =========================================================================
    # V2-NATIVE NOTIFICATION METHOD
    # =========================================================================
    
    def check_and_notify_v2(self, send_notifications: bool = True, scan_type: str = None):
        """
        V2-native recommendation check and notification.
        
        This method:
        1. Runs the V1 recommendation engine (which dual-writes to V2)
        2. Sends notifications directly from V2 snapshots
        3. Includes snapshot numbers in notifications for traceability
        
        Args:
            send_notifications: Whether to actually send Telegram notifications
            scan_type: Optional scan identifier (e.g., '6am', '12pm')
        """
        db: Session = SessionLocal()
        try:
            logger.info(f"[V2] Running V2-native recommendation check...")
            
            # Step 0: Clean up stale recommendations (positions that no longer exist)
            from app.modules.strategies.recommendation_service import RecommendationService
            rec_cleanup_service = RecommendationService(db)
            cleaned_count = rec_cleanup_service.cleanup_stale_recommendations()
            if cleaned_count > 0:
                logger.info(f"[V2] Cleaned {cleaned_count} stale recommendations before scan")
            
            # Step 1: Generate recommendations via V1 (which dual-writes to V2)
            service = StrategyService(db)
            recommendations = service.generate_recommendations({
                "default_premium": 60,
                "profit_threshold": 0.80
            })
            
            if recommendations:
                logger.info(f"[V2] Generated {len(recommendations)} V1 recommendations (dual-written to V2)")
                
                # Save to V1 history for backwards compatibility
                from app.modules.strategies.recommendations import OptionsStrategyRecommendationService
                rec_service = OptionsStrategyRecommendationService(db)
                rec_service.save_recommendations_to_history(recommendations, scan_type=scan_type)
            
            # Step 2: Get notifications from V2 model (including sell opportunities)
            from app.modules.strategies.v2_notification_service import get_v2_notification_service
            v2_service = get_v2_notification_service(db)
            
            # Use comprehensive method that includes V2 snapshots + V1 sell opportunities
            notifications = v2_service.get_all_notifications_to_send(
                mode='both', 
                scan_type=scan_type,
                include_sell_opportunities=True
            )
            
            verbose_count = len(notifications['verbose'])
            smart_count = len(notifications['smart'])
            
            logger.info(f"[V2] Notifications to send: {verbose_count} verbose, {smart_count} smart")
            
            if not send_notifications:
                logger.info("[V2] Notifications disabled, skipping send")
                return
            
            # Step 3: Send notifications
            notification_service = get_notification_service()
            
            # Send VERBOSE mode notification
            if notifications['verbose']:
                verbose_message = v2_service.format_telegram_message(
                    notifications['verbose'], 
                    mode='verbose'
                )
                if verbose_message and notification_service.telegram_enabled:
                    success, message_id = notification_service._send_telegram(verbose_message)
                    if success:
                        logger.info(f"[V2] Sent VERBOSE notification ({verbose_count} items)")
                        # Mark snapshots as notified
                        for notif in notifications['verbose']:
                            v2_service.mark_snapshot_notified(
                                notif['snapshot_id'], 
                                mode='verbose',
                                message_id=message_id
                            )
            
            # Send SMART mode notification
            if notifications['smart']:
                smart_message = v2_service.format_telegram_message(
                    notifications['smart'], 
                    mode='smart'
                )
                if smart_message and notification_service.telegram_enabled:
                    success, message_id = notification_service._send_telegram(smart_message)
                    if success:
                        logger.info(f"[V2] Sent SMART notification ({smart_count} items)")
                        # Mark snapshots as notified
                        for notif in notifications['smart']:
                            v2_service.mark_snapshot_notified(
                                notif['snapshot_id'], 
                                mode='smart',
                                message_id=message_id
                            )
            
            logger.info("[V2] V2-native notification check complete")
            
        except Exception as e:
            logger.error(f"[V2] Error in V2 recommendation check: {e}", exc_info=True)
        finally:
            db.close()
    
    # =========================================================================
    # RLHF LEARNING METHODS
    # =========================================================================
    
    def run_daily_reconciliation(self):
        """
        Run daily reconciliation of recommendations to executions.
        
        Called at 9 PM PT after market close.
        """
        from datetime import date, timedelta
        db: Session = SessionLocal()
        try:
            logger.info("Running daily RLHF reconciliation...")
            
            from app.modules.strategies.reconciliation_service import get_reconciliation_service
            
            service = get_reconciliation_service(db)
            
            # Reconcile today's activity
            today = date.today()
            result = service.reconcile_day(today)
            
            logger.info(f"Daily reconciliation complete: {result}")
            
            # Also check yesterday in case any were missed
            yesterday = today - timedelta(days=1)
            result_yesterday = service.reconcile_day(yesterday)
            logger.info(f"Yesterday reconciliation complete: {result_yesterday}")
            
        except Exception as e:
            logger.error(f"Error in daily reconciliation: {e}", exc_info=True)
        finally:
            db.close()
    
    def run_weekly_learning_summary(self):
        """
        Generate weekly learning summary.
        
        Called Saturday 9 AM PT.
        Analyzes the past week's patterns and generates V4 candidates.
        """
        from datetime import date
        db: Session = SessionLocal()
        try:
            logger.info("Generating weekly learning summary...")
            
            from app.modules.strategies.reconciliation_service import get_reconciliation_service
            
            service = get_reconciliation_service(db)
            
            # Get last week's ISO week number
            today = date.today()
            # Go back to get last week (since we're running on Saturday)
            last_week = today - timedelta(days=7)
            iso_cal = last_week.isocalendar()
            
            summary = service.generate_weekly_summary(iso_cal.year, iso_cal.week)
            
            logger.info(f"Weekly summary generated for {iso_cal.year}-W{iso_cal.week}")
            
            # Send notification if there are insights
            if summary.patterns_observed or summary.v4_candidates:
                self._send_weekly_learning_notification(summary)
            
        except Exception as e:
            logger.error(f"Error in weekly learning summary: {e}", exc_info=True)
        finally:
            db.close()
    
    def run_outcome_tracking(self):
        """
        Track outcomes for completed positions.

        Called at 10 PM PT daily.
        """
        from datetime import date
        db: Session = SessionLocal()
        try:
            logger.info("Running outcome tracking...")

            from app.modules.strategies.reconciliation_service import get_reconciliation_service

            service = get_reconciliation_service(db)
            result = service.track_position_outcomes(date.today())

            logger.info(f"Outcome tracking complete: {result}")

        except Exception as e:
            logger.error(f"Error in outcome tracking: {e}", exc_info=True)
        finally:
            db.close()

    def send_expense_notifications(self):
        """
        Check for expenses due tomorrow and send notifications.

        Called at 6:00 AM PT daily (7 days/week).
        Sends mobile notifications one day before forecasted expenses are due.
        """
        db: Session = SessionLocal()
        try:
            logger.info("Checking for expenses due tomorrow...")

            from app.modules.strategies.expense_notification_service import get_expense_notification_service

            service = get_expense_notification_service()
            result = service.send_expense_notifications(db)

            if result.get('notification_sent'):
                total = result.get('total_amount', 0)
                count = result.get('expenses_found', 0)
                logger.info(f"Expense notification sent: {count} expense(s), total ${total:,.0f}")
            elif result.get('expenses_found', 0) > 0:
                logger.warning(f"Found {result['expenses_found']} expense(s) but notification failed: {result.get('error')}")
            else:
                logger.debug("No expenses due tomorrow")

        except Exception as e:
            logger.error(f"Error in expense notifications: {e}", exc_info=True)
        finally:
            db.close()

    def _send_weekly_learning_notification(self, summary):
        """Send notification with weekly learning summary."""
        try:
            notification_service = get_notification_service()
            
            # Build notification message
            msg_lines = [
                f"📊 WEEKLY LEARNING SUMMARY ({summary.year}-W{summary.week_number})",
                "",
                f"RECOMMENDATIONS: {summary.total_recommendations}",
                f"├─ ✅ Consent: {summary.consent_count}",
                f"├─ ✏️ Modified: {summary.modify_count}",
                f"├─ ❌ Rejected: {summary.reject_count}",
                f"└─ 🆕 Independent: {summary.independent_count}",
            ]
            
            if summary.actual_pnl is not None:
                msg_lines.extend([
                    "",
                    f"P&L: ${float(summary.actual_pnl):,.2f}",
                ])
            
            if summary.patterns_observed:
                msg_lines.extend([
                    "",
                    f"PATTERNS DETECTED: {len(summary.patterns_observed)}",
                ])
                for p in summary.patterns_observed[:3]:
                    msg_lines.append(f"• {p.get('description', 'Unknown pattern')}")
            
            if summary.v4_candidates:
                msg_lines.extend([
                    "",
                    f"V4 CANDIDATES: {len(summary.v4_candidates)}",
                ])
                for c in summary.v4_candidates[:2]:
                    msg_lines.append(f"• {c.get('description', 'Unknown change')}")
            
            msg_lines.extend([
                "",
                "Review in Learning tab for full details."
            ])
            
            message = "\n".join(msg_lines)
            
            # Send via Telegram
            notification_service.send_telegram_message(message)
            
            # Update summary to mark notification sent
            summary.notification_sent = True
            summary.notification_sent_at = datetime.utcnow()
            
            logger.info("Weekly learning notification sent")
            
        except Exception as e:
            logger.error(f"Error sending weekly learning notification: {e}")
    
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

