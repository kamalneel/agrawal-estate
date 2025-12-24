"""
Notification Service for Strategy Recommendations

Supports multiple notification channels:
- Telegram Bot (recommended - free, simple, reliable)
- Email (backup option)
- Twilio WhatsApp (if you want WhatsApp)
- Console (for testing)

Configure via environment variables.

Telegram Feedback Integration:
- Tracks sent message IDs for reply correlation
- See telegram_webhook.py for incoming reply handling
"""

import os
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from pathlib import Path
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

logger = logging.getLogger(__name__)


def _load_env_file():
    """Load environment variables from .env file if it exists."""
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Remove quotes if present
                    value = value.strip('"\'')
                    # Only set if not already in environment
                    if key not in os.environ:
                        os.environ[key] = value


class NotificationService:
    """Unified notification service supporting multiple channels."""
    
    def __init__(self):
        # Load .env file if it exists
        _load_env_file()
        
        self.telegram_enabled = bool(os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID'))
        self.email_enabled = bool(
            os.getenv('SMTP_HOST') and 
            os.getenv('SMTP_USER') and 
            os.getenv('NOTIFY_EMAIL')
        )
        self.whatsapp_enabled = bool(
            os.getenv('TWILIO_ACCOUNT_SID') and 
            os.getenv('TWILIO_AUTH_TOKEN') and 
            os.getenv('TWILIO_WHATSAPP_FROM') and 
            os.getenv('WHATSAPP_TO')
        )
        
        # Log enabled channels
        enabled = []
        if self.telegram_enabled:
            enabled.append("Telegram")
        if self.email_enabled:
            enabled.append("Email")
        if self.whatsapp_enabled:
            enabled.append("WhatsApp (Twilio)")
        
        if enabled:
            logger.info(f"Notification channels enabled: {', '.join(enabled)}")
        else:
            logger.warning("No notification channels configured. Set environment variables to enable.")
    
    def send_recommendation_notification(
        self,
        recommendations: List[Dict[str, Any]],
        priority_filter: Optional[str] = None,
        db_session=None
    ) -> Dict[str, Any]:
        """
        Send notification about new recommendations.
        
        Args:
            recommendations: List of recommendation dicts
            priority_filter: Only notify for this priority or higher (e.g., "high")
            db_session: Optional database session for tracking Telegram messages
        
        Returns:
            Dict of channel -> success status (with telegram_message_id if applicable)
        """
        # Filter by priority if specified
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        if priority_filter:
            min_priority = priority_order.get(priority_filter, 99)
            filtered = [
                r for r in recommendations
                if priority_order.get(r.get("priority", "low"), 99) <= min_priority
            ]
        else:
            filtered = recommendations
        
        if not filtered:
            return {}
        
        # Format message
        message = self._format_recommendations_message(filtered)
        
        # Extract recommendation IDs for tracking
        recommendation_ids = [
            r.get("id") or r.get("recommendation_id") 
            for r in filtered 
            if r.get("id") or r.get("recommendation_id")
        ]
        
        # Send to all enabled channels
        results = {}
        
        if self.telegram_enabled:
            success, message_id = self._send_telegram(message)
            results["telegram"] = success
            results["telegram_message_id"] = message_id
            
            # Track Telegram message for reply correlation
            if success and message_id and db_session and recommendation_ids:
                self._track_telegram_message(
                    db_session=db_session,
                    message_id=message_id,
                    recommendation_ids=recommendation_ids,
                    message_text=message
                )
        
        if self.email_enabled:
            results["email"] = self._send_email(
                subject="Strategy Recommendations",
                body=message
            )
        
        if self.whatsapp_enabled:
            results["whatsapp"] = self._send_whatsapp(message)
        
        return results
    
    def _track_telegram_message(
        self,
        db_session,
        message_id: int,
        recommendation_ids: List[str],
        message_text: str
    ):
        """
        Track a Telegram message for reply correlation.
        
        This stores the message_id and associated recommendation_ids so that
        when a user replies to the message, we can correlate it with the
        original recommendations.
        """
        try:
            from app.modules.strategies.models import TelegramMessageTracking
            
            chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
            
            tracking = TelegramMessageTracking(
                telegram_message_id=message_id,
                telegram_chat_id=chat_id,
                recommendation_ids=recommendation_ids,
                message_text=message_text[:5000] if message_text else None,  # Limit size
                sent_at=datetime.utcnow()
            )
            
            db_session.add(tracking)
            db_session.commit()
            
            logger.info(f"Tracked Telegram message {message_id} with {len(recommendation_ids)} recommendations")
            
        except Exception as e:
            logger.error(f"Failed to track Telegram message: {e}")
            # Don't fail the notification if tracking fails
            try:
                db_session.rollback()
            except:
                pass
    
    def send_alert(
        self,
        title: str,
        message: str,
        priority: str = "medium"
    ) -> Dict[str, Any]:
        """
        Send a simple alert notification.
        
        Args:
            title: Alert title
            message: Alert message
            priority: Priority level
        
        Returns:
            Dict of channel -> success status
        """
        formatted = f"*{title}*\n\n{message}"
        
        results = {}
        
        if self.telegram_enabled:
            success, message_id = self._send_telegram(formatted)
            results["telegram"] = success
            results["telegram_message_id"] = message_id
        
        if self.email_enabled:
            results["email"] = self._send_email(
                subject=title,
                body=message
            )
        
        if self.whatsapp_enabled:
            results["whatsapp"] = self._send_whatsapp(formatted)
        
        return results
    
    def _format_recommendations_message(self, recommendations: List[Dict[str, Any]]) -> str:
        """
        Format recommendations into organized, actionable messages for Telegram.
        
        Features (V3 Enhanced):
        1. Groups recommendations by individual account (Brokerage, IRA, Retirement for each owner)
        2. Adds estimated premium/income for SELL recommendations
        3. Sorts by estimated profit within each account
        4. Clean, readable format
        
        Example output:
        ```
        *Neel's Brokerage - 3 Recommendations:*
        • SELL: 1 IBIT $53 calls Dec 26 · Stock $51 ($338/wk)
        • SELL: 1 NVDA $195 calls Dec 26 · Stock $183 ($220/wk)
        • SELL: 1 MSFT $509 calls Dec 26 · Stock $484 ($180/wk)
        
        *Neel's IRA - 2 Recommendations:*
        • SELL: 1 MU $100 calls Dec 26 · Stock $95 ($150)
        • ROLL: TSM 1x $200 → $205 Dec 26
        
        *Jaya's Brokerage - 2 Recommendations:*
        • SELL: 1 NVDA $195 calls Dec 26 · Stock $183 ($220/wk)
        • ROLL: AVGO 2x $362.5 put → $350 Jan 2 · Stock $340
        
        7:12 AM
        ```
        """
        from app.shared.services.notification_organizer import organize_and_format
        
        return organize_and_format(recommendations, group_threshold=3)
    
    def _send_telegram(self, message: str) -> Tuple[bool, Optional[int]]:
        """
        Send message via Telegram bot.
        
        Returns:
            Tuple of (success, message_id) where message_id is used for reply tracking
        """
        try:
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            chat_id = os.getenv('TELEGRAM_CHAT_ID')
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            response = requests.post(url, json=data, timeout=10)
            response.raise_for_status()
            
            # Extract message_id from response for reply tracking
            result = response.json()
            message_id = result.get("result", {}).get("message_id")
            
            logger.info(f"Telegram notification sent successfully (message_id: {message_id})")
            return True, message_id
            
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return False, None
    
    def _send_email(self, subject: str, body: str) -> bool:
        """Send email notification."""
        try:
            smtp_host = os.getenv('SMTP_HOST')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_user = os.getenv('SMTP_USER')
            smtp_password = os.getenv('SMTP_PASSWORD')
            notify_email = os.getenv('NOTIFY_EMAIL')
            
            msg = MIMEMultipart()
            msg['From'] = smtp_user
            msg['To'] = notify_email
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
            server.quit()
            
            logger.info("Email notification sent successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            return False
    
    def _send_whatsapp(self, message: str) -> bool:
        """Send WhatsApp message via Twilio."""
        try:
            from twilio.rest import Client
            
            account_sid = os.getenv('TWILIO_ACCOUNT_SID')
            auth_token = os.getenv('TWILIO_AUTH_TOKEN')
            from_number = os.getenv('TWILIO_WHATSAPP_FROM')  # e.g., "whatsapp:+14155238886"
            to_number = os.getenv('WHATSAPP_TO')  # e.g., "whatsapp:+1234567890"
            
            client = Client(account_sid, auth_token)
            
            message_obj = client.messages.create(
                body=message,
                from_=from_number,
                to=to_number
            )
            
            logger.info(f"WhatsApp notification sent successfully (SID: {message_obj.sid})")
            return True
            
        except ImportError:
            logger.error("Twilio library not installed. Run: pip install twilio")
            return False
        except Exception as e:
            logger.error(f"Failed to send WhatsApp notification: {e}")
            return False


# Global instance
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Get or create the global notification service instance."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service

