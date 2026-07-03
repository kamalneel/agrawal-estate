"""
Notification Service — Resend Email

Replaces the previous Telegram-based system.
Sends HTML email via Resend to AGENT_USER_EMAIL.
Reply-To is set to AGENT_INBOX_ADDRESS so replies reach the email assistant.
"""

import os
import logging
import re
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_env_file():
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    value = value.strip("\"'").strip()
                    if key not in os.environ and value:
                        os.environ[key] = value


def _md_to_html(text: str) -> str:
    """Convert Telegram-style markdown subset to HTML."""
    text = re.sub(r"\*([^*\n]+)\*", r"<strong>\1</strong>", text)
    text = re.sub(r"_([^_\n]+)_", r"<em>\1</em>", text)
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    text = text.replace("\n", "<br>\n")
    return text


def _wrap_html(body_html: str) -> str:
    now_str = datetime.now().strftime("%A, %B %-d · %-I:%M %p PT")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 15px; line-height: 1.65; color: #111827;
    max-width: 640px; margin: 0 auto; padding: 28px 20px;
    background: #ffffff;
  }}
  .hdr {{ border-bottom: 2px solid #2563eb; padding-bottom: 10px; margin-bottom: 22px; }}
  .hdr h2 {{ margin: 0 0 4px; color: #2563eb; font-size: 17px; font-weight: 700; }}
  .hdr .ts {{ font-size: 12px; color: #6b7280; }}
  .body {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
           padding: 18px 22px; }}
  strong {{ color: #111827; }}
  code {{ background: #e5e7eb; padding: 1px 5px; border-radius: 3px;
          font-size: 13px; font-family: 'SF Mono', monospace; }}
  .ftr {{ margin-top: 20px; padding-top: 14px; border-top: 1px solid #e5e7eb;
          font-size: 12px; color: #9ca3af; }}
</style>
</head>
<body>
  <div class="hdr">
    <h2>🏦 Agrawal Estate Planner</h2>
    <div class="ts">{now_str}</div>
  </div>
  <div class="body">{body_html}</div>
  <div class="ftr">
    Reply to this email to ask a follow-up question — your estate planner assistant will respond.
  </div>
</body>
</html>"""


class NotificationService:
    """Sends notifications via Resend email."""

    def __init__(self):
        _load_env_file()

        import resend as _resend
        self._resend = _resend

        api_key = os.getenv("RESEND_API_KEY", "").strip()
        if api_key:
            self._resend.api_key = api_key
            self.email_enabled = True
        else:
            self.email_enabled = False
            logger.warning("RESEND_API_KEY not set — email notifications disabled")

        self.from_addr = os.getenv("AGENT_FROM", "Agrawal Estate Planner <assistant@neellab.info>").strip()
        self.to_addr = os.getenv("AGENT_USER_EMAIL", "neelkamal@gmail.com").strip()
        self.reply_to = os.getenv("AGENT_INBOX_ADDRESS", "assistant@neellab.info").strip()

        if self.email_enabled:
            logger.info(f"Email notifications enabled → {self.to_addr} (reply-to: {self.reply_to})")

    # -------------------------------------------------------------------------
    # Legacy compat — scheduler checks .telegram_enabled before calling _send_telegram
    # -------------------------------------------------------------------------

    @property
    def telegram_enabled(self) -> bool:
        return self.email_enabled

    def _send_telegram(self, message: str) -> Tuple[bool, Optional[str]]:
        """Legacy shim — callers still use this name; routes to email."""
        return self._send_email(
            subject="Estate Planner Update",
            html_body=_md_to_html(message),
            plain_text=message,
        )

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def send_recommendation_notification(
        self,
        recommendations: List[Dict[str, Any]],
        priority_filter: Optional[str] = None,
        db_session=None,
        notification_mode: str = None,
        scan_label: str = "",
    ) -> Dict[str, Any]:
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        if priority_filter:
            min_p = priority_order.get(priority_filter, 99)
            filtered = [
                r for r in recommendations
                if priority_order.get(r.get("priority", "low"), 99) <= min_p
            ]
        else:
            filtered = recommendations

        if not filtered:
            return {}

        # Subject line
        urgent = sum(1 for r in filtered if r.get("priority") == "urgent")
        if urgent:
            subject = f"🚨 {urgent} Urgent + {len(filtered) - urgent} More — Options Scan"
        elif notification_mode == "smart":
            subject = f"⚡ {len(filtered)} Updated Recommendations"
        else:
            subject = f"📊 {len(filtered)} Options Recommendations"

        # Rich HTML body (accounts × action tables)
        from app.shared.services.notification_organizer import format_html_email
        html_body = format_html_email(
            filtered,
            scan_label=scan_label,
            notification_mode=notification_mode or "",
        )

        # Plain text fallback (legacy format)
        plain_text = self._format_recommendations_message(filtered)

        success, msg_id = self._send_email(subject=subject, html_body=html_body, plain_text=plain_text)
        return {"email": success, "email_message_id": msg_id, "notification_mode": notification_mode}

    def send_alert(self, title: str, message: str, priority: str = "medium") -> Dict[str, Any]:
        html_body = f"<strong>{title}</strong><br><br>{_md_to_html(message)}"
        success, msg_id = self._send_email(subject=title, html_body=html_body, plain_text=f"{title}\n\n{message}")
        return {"email": success, "email_message_id": msg_id}

    def send_message(self, message: str, subject: str = "Estate Planner Update") -> bool:
        """Ad-hoc message sender — used by weekly learning summary etc."""
        success, _ = self._send_email(subject=subject, html_body=_md_to_html(message), plain_text=message)
        return success

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    def _format_recommendations_message(self, recommendations: List[Dict[str, Any]]) -> str:
        from app.shared.services.notification_organizer import organize_and_format
        return organize_and_format(recommendations, group_threshold=3)

    def _send_email(
        self, subject: str, html_body: str, plain_text: str = ""
    ) -> Tuple[bool, Optional[str]]:
        if not self.email_enabled:
            logger.warning("Email not enabled — skipping send")
            return False, None
        try:
            params: Dict[str, Any] = {
                "from": self.from_addr,
                "to": [self.to_addr],
                "reply_to": self.reply_to,
                "subject": subject,
                "html": _wrap_html(html_body),
                "text": plain_text,
            }
            response = self._resend.Emails.send(params)
            msg_id = response.get("id") if isinstance(response, dict) else getattr(response, "id", None)
            logger.info(f"Email sent (id={msg_id}) subject='{subject}'")
            return True, str(msg_id) if msg_id else None
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False, None


# Global instance
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
