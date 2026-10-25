"""
Scheduler Service for Automated Recommendation Checks

Uses APScheduler to periodically check for recommendations and send notifications
based on time-based rules.
"""

import logging
from typing import Dict, Any, Optional
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
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
        
        Decision-point scan emails (Neel, 2026-07-14: 6:50 / 8:00 / 12:00 /
        8:00 PM PT) are NOT scheduled here since 2026-09-17 — they are
        sent by notify_after_sync() when the launchd sync that precedes
        each one completes (see the note in the body). What remains here
        are the housekeeping jobs.

        NO after-hours notifications between 1 PM and 8 PM.
        NO weekend notifications (market closed).
        """

        # =================================================================
        # SCAN EMAILS ARE NO LONGER CRON JOBS HERE (2026-09-17)
        # =================================================================
        # Neel: "the flow is Sync → wait for completion → email." Until
        # today the four decision-point scans (6:50 / 8:00 / 12:00 / 8:00
        # PM PT) fired on their own clock, ~15 min after a launchd sync
        # that might or might not have finished. Now the sync wrapper
        # (scripts/scheduled_refresh.sh, launchd com.agrawal.estate.refresh)
        # runs at 6:40 / 7:50 / 11:50 / 19:50 and, when its run completes,
        # POSTs /strategies/notify/after-sync?scan_type=… — which calls
        # notify_after_sync() below. The email therefore always sits on
        # the sync that just finished, and says so in its header. The
        # in-between syncs (9:05, 10:05, 13:05) send a short "sync
        # complete" email through the same endpoint, without scan_type.
        # Nothing here fires a scan on its own any more.

        # =================================================================
        # NO AFTER-HOURS OR WEEKEND SCANS
        # =================================================================
        # Per V3 spec: Only 5 scans per weekday, no weekend notifications
        # Market is closed, no action can be taken
        
        # =================================================================
        # DAILY PORTFOLIO SNAPSHOT: 8:15 PM PT (Weekdays)
        # =================================================================
        # Purpose: Record daily portfolio values for growth charts
        # Runs 15 minutes after evening scan so prices are fresh
        # Populates portfolio_snapshots + investment_holdings_history
        self.scheduler.add_job(
            self.take_daily_portfolio_snapshot,
            trigger=CronTrigger(
                hour=20,
                minute=15,
                day_of_week='mon-fri',
                timezone=PT
            ),
            id='daily_portfolio_snapshot',
            name='Daily Portfolio Snapshot (8:15 PM PT)',
            replace_existing=True
        )

        logger.info("Schedule configured: 4 daily scans (6:50AM, 8AM, 12PM, 8PM) weekdays only")
        logger.info("Daily portfolio snapshot configured: 8:15 PM PT weekdays")

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
        # CALL-ASSIGNMENT TAX-LOT NOTICES (Neel, 2026-09-13)
        # =================================================================
        # Robinhood disposes assigned shares by the account's default lot
        # method (FIFO unless changed) and corrects them only until 9 PM ET
        # on the settlement date. Daily at 6:30 AM PT: warn about ITM short
        # calls in taxable accounts expiring within 2 days (set Highest Cost
        # before 8 PM ET), and about assignments that already landed (support
        # message + deadline). Each notice goes out exactly once. Also runs
        # after MCP assignment detection; this is the safety net.
        self.scheduler.add_job(
            self.send_assignment_tax_notices,
            trigger=CronTrigger(hour=6, minute=30, timezone=PT),
            id='assignment_tax_notices_daily',
            name='Call-assignment tax-lot notices (6:30 AM PT Daily)',
            replace_existing=True
        )

        # =================================================================
        # PRICE ALERT CHECKER: Every 5 minutes during market hours
        # =================================================================
        # Purpose: Check user-created price alerts and send email when triggered
        # Runs Mon-Fri 6:30 AM to 1:15 PM PT (market hours + buffer)
        self.scheduler.add_job(
            self.check_price_alerts,
            trigger=IntervalTrigger(
                minutes=5,
                timezone=PT,
            ),
            id='price_alert_checker',
            name='Price Alert Checker (every 5 min)',
            replace_existing=True
        )

        logger.info("Price alert checker configured: every 5 minutes")

        # =================================================================
        # RLHF LEARNING JOBS — REMOVED 2026-10-25 (options UX audit, step 5)
        # =================================================================
        # Daily reconciliation (9 PM), outcome tracking (10 PM) and the
        # Saturday learning summary matched V2–V5 recommendations to what
        # was traded. Nothing has read their tables since the Learning page
        # lost its menu link; V7/V8 learn from Neel directly, as knobs
        # (docs/OPTIONS-UX-AUDIT.md). The tables are kept.

    # =========================================================================
    # V6 NOTIFICATION METHOD
    # =========================================================================

    def check_and_notify_v6(self, send_notifications: bool = True, scan_type: str = None,
                            sync: Optional[Dict[str, Any]] = None):
        """
        V6-native recommendation check and notification — same engine that
        powers the Options Execution page (build_action_queue). Added
        2026-07-22 so the email and the page finally agree; see
        app/modules/strategies/v6_email.py for why.
        """
        db: Session = SessionLocal()
        try:
            logger.info(f"[V6] Running V6 action-queue check (scan_type={scan_type})...")

            from app.modules.strategies.v7_engine import build_live_action_queue
            queue = build_live_action_queue(db)   # V8 since 2026-10-22; settings.LIVE_STRATEGY_ENGINE
            items = queue.get("items", [])
            logger.info(f"[{queue.get('engine_version', 'v6')}] Total items: {len(items)}")

            if not send_notifications:
                logger.info("[V6] Notifications disabled, skipping send")
                return

            if not items:
                logger.info("[V6] No items to send")
                return

            notification_service = get_notification_service()
            if not notification_service.email_enabled:
                logger.info("[V6] Email not enabled, skipping send")
                return

            from app.modules.strategies.v6_email import format_html_email, format_plain_text

            scan_label = SCAN_LABELS.get(scan_type or "", scan_type or "")

            html_body = format_html_email(queue, scan_label=scan_label, sync=sync)
            plain_text = format_plain_text(queue, scan_label=scan_label, sync=sync)

            summary = queue.get("summary", {})
            urgent = summary.get("urgent", 0)
            ev = (queue.get("engine_version") or "v6").upper().split("-")[0].split(".")[0]
            subject = (
                f"🚨 {urgent} Urgent — {ev} Action Queue"
                if urgent else
                f"📊 {len(items)} {ev} Recommendations — {scan_label.split('—')[0].strip()}"
            )
            if sync and not sync.get("ok"):
                subject = "⚠️ SYNC FAILED · " + subject

            success, _ = notification_service._send_email(
                subject=subject, html_body=html_body, plain_text=plain_text
            )
            if success:
                logger.info(f"[V6] Sent email notification ({len(items)} items)")
            else:
                logger.error("[V6] Failed to send email notification")

            logger.info("[V6] V6 notification check complete")

        except Exception as e:
            logger.error(f"[V6] Error in V6 recommendation check: {e}", exc_info=True)
        finally:
            db.close()

    # =========================================================================
    # PORTFOLIO SNAPSHOT METHOD
    # =========================================================================

    def take_daily_portfolio_snapshot(self):
        """
        Take a daily snapshot of all portfolio holdings and values.

        Called at 8:15 PM PT weekdays, 15 minutes after the evening scan.
        Populates portfolio_snapshots and investment_holdings_history tables.
        """
        db: Session = SessionLocal()
        try:
            logger.info("Taking daily portfolio snapshot...")

            from app.modules.investments.snapshot_service import take_daily_snapshot

            stats = take_daily_snapshot(db)

            logger.info(
                f"Daily portfolio snapshot complete: "
                f"{stats['accounts_snapshot']} accounts, "
                f"{stats['holdings_snapshot']} holdings, "
                f"total ${stats['total_portfolio_value']:,.0f}"
            )

        except Exception as e:
            logger.error(f"Error in daily portfolio snapshot: {e}", exc_info=True)
        finally:
            db.close()

    def check_price_alerts(self):
        """
        Check all active price alerts and send email notifications for any that trigger.
        Runs every 5 minutes via interval trigger.
        """
        try:
            from app.shared.services.price_alerts import get_price_alert_manager, build_price_alert_email_html
            import os

            mgr = get_price_alert_manager()
            active = mgr.list_alerts()
            if not active:
                return

            triggered = mgr.check_all()
            if not triggered:
                return

            import resend as _resend
            api_key = os.getenv("RESEND_API_KEY", "").strip()
            if not api_key:
                logger.warning("RESEND_API_KEY not set — cannot send price alert emails")
                return

            _resend.api_key = api_key
            from_addr = os.getenv("AGENT_FROM", "Neel's Estate Planner <assistant@neellab.info>").strip()
            to_addr = os.getenv("AGENT_USER_EMAIL", "neelkamal@gmail.com").strip()
            reply_to = os.getenv("AGENT_INBOX_ADDRESS", "assistant@neellab.info").strip()

            for item in triggered:
                alert = item["alert"]
                price = item["current_price"]
                cond = "dropped below" if alert.condition == "below" else "risen above"
                subject = f"Price Alert: {alert.symbol} has {cond} ${alert.target_price:,.2f}"
                html = build_price_alert_email_html(alert, price)
                plain = (
                    f"{alert.symbol} is now ${price:,.2f} — "
                    f"{cond} your target of ${alert.target_price:,.2f}.\n\n"
                    "— Your Estate Planner Assistant"
                )
                try:
                    _resend.Emails.send({
                        "from": from_addr,
                        "to": [to_addr],
                        "reply_to": reply_to,
                        "subject": subject,
                        "html": html,
                        "text": plain,
                    })
                    logger.info(f"Price alert email sent: {alert.symbol} @ ${price:.2f}")
                except Exception as e:
                    logger.error(f"Failed to send price alert email: {e}")

        except Exception as e:
            logger.error(f"Error in check_price_alerts: {e}", exc_info=True)

    def send_assignment_tax_notices(self):
        """Call-assignment tax-lot notices for taxable accounts — see
        app/modules/tax/assignment_tax_notice_service.py."""
        db: Session = SessionLocal()
        try:
            from app.modules.tax.assignment_tax_notice_service import run_assignment_tax_notices
            result = run_assignment_tax_notices(db, lookahead_days=2)
            logger.info(f"[tax-lots] {len(result['sent'])} notice(s) sent, {result['skipped']} already sent, "
                        f"{len(result['errors'])} error(s)")
            for e in result["errors"]:
                logger.warning(f"[tax-lots] {e}")
        except Exception as e:
            logger.error(f"[tax-lots] notice run failed: {e}")
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
    
    def shutdown(self):
        """Shutdown the scheduler."""
        self.scheduler.shutdown()
        logger.info("Recommendation scheduler stopped")


# Global scheduler instance
# Decision points (Neel, 2026-07-14), now timed by the sync that precedes
# each one (2026-09-17): the wrapper syncs at 6:40 / 7:50 / 11:50 / 19:50
# and the email follows the moment the run completes (~6 min later).
SCAN_LABELS = {
    "manual":        "Manual scan (after a sync you started)",
    "6am_main":      "Scan 1 — Wake-up Triage (after the 6:40 AM sync)",
    "8am_post_open": "Scan 2 — Coffee Break (after the 7:50 AM sync)",
    "12pm_midday":   "Scan 3 — Pre-Close Decisions (after the 11:50 AM sync)",
    "8pm_evening":   "Scan 5 — Evening Planning (after the 7:50 PM sync)",
}


def read_refresh_status() -> Dict[str, Any]:
    """The last scheduled sync's outcome, written by scripts/scheduled_refresh.sh."""
    import json
    from app.core.config import settings
    try:
        return json.loads((settings.DATA_DIR / "refresh_status.json").read_text())
    except Exception:
        return {}


def notify_after_sync(scan_type: Optional[str] = None) -> Dict[str, Any]:
    """Sync → wait → email (Neel, 2026-09-17). Called by the sync wrapper
    the moment a run finishes, success or failure.

    - scan_type given: the decision-point scan email, with the sync's
      outcome in its header and the sync report at the bottom. On a
      failed sync the email still goes out (on the data already in the
      app) with a red banner and a SYNC FAILED subject — a missed
      decision point is worse than a stale one.
    - no scan_type: nothing on success. Neel, 2026-09-18: "you are also
      sending me a separate sync email. This is not needed." A FAILED
      off-slot sync still emails — a dead sync must never be silent
      (playbook: check-freshness-and-ask-first).
    """
    sync = read_refresh_status()
    if not scan_type and sync.get("ok"):
        return {"sent": None, "sync_ok": True, "reason": "off-slot success, no email by request"}
    if scan_type:
        sched = _scheduler or RecommendationScheduler()
        try:
            sched.check_and_notify_v6(send_notifications=True, scan_type=scan_type, sync=sync)
        finally:
            if sched is not _scheduler:
                sched.shutdown()
        return {"sent": "scan", "scan_type": scan_type, "sync_ok": sync.get("ok")}

    from app.modules.strategies.v6_email import sync_box_html, sync_report_html, sync_report_plain, _sync_time, _as_of_pt
    from app.modules.strategies.v7_engine import build_live_action_queue
    db: Session = SessionLocal()
    try:
        queue = build_live_action_queue(db)
    finally:
        db.close()
    summary = queue.get("summary", {})
    prem = (queue.get("premium") or {}).get("today", {})
    net = prem.get("net", 0)
    counts = f"queue {summary.get('urgent', 0)} urgent / {summary.get('high', 0)} high"
    prem_txt = f"today's premium {'+' if net >= 0 else '-'}${abs(net):,.0f} ({prem.get('fills', 0)} fills)"
    when = _sync_time(sync)
    subject = (f"✅ Sync complete {when} — {counts}, {prem_txt}" if sync.get("ok")
               else f"⚠️ Sync FAILED {when} — {counts} (stale)")
    html = (sync_box_html(sync, queue.get("data_as_of", ""))
            + f'<div style="font-size:14px; color:#374151;">{counts} · {prem_txt} · data as of {_as_of_pt(queue.get("data_as_of", ""))}</div>'
            + sync_report_html(sync))
    plain = f"{sync_report_plain(sync)}\n\n{counts} · {prem_txt} · data as of {_as_of_pt(queue.get('data_as_of', ''))}"
    ok, _ = get_notification_service()._send_email(subject=subject, html_body=html, plain_text=plain)
    return {"sent": "sync_summary" if ok else None, "sync_ok": sync.get("ok")}


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
