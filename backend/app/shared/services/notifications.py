"""
Notification Service for Strategy Recommendations

Supports multiple notification channels:
- Telegram Bot (recommended - free, simple, reliable)
- Email (backup option)
- Twilio WhatsApp (if you want WhatsApp)
- Console (for testing)

Configure via environment variables.
"""

import os
import logging
from typing import Optional, List, Dict, Any
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
        priority_filter: Optional[str] = None
    ) -> Dict[str, bool]:
        """
        Send notification about new recommendations.
        
        Args:
            recommendations: List of recommendation dicts
            priority_filter: Only notify for this priority or higher (e.g., "high")
        
        Returns:
            Dict of channel -> success status
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
        
        # Send to all enabled channels
        results = {}
        
        if self.telegram_enabled:
            results["telegram"] = self._send_telegram(message)
        
        if self.email_enabled:
            results["email"] = self._send_email(
                subject="Strategy Recommendations",
                body=message
            )
        
        if self.whatsapp_enabled:
            results["whatsapp"] = self._send_whatsapp(message)
        
        return results
    
    def send_alert(
        self,
        title: str,
        message: str,
        priority: str = "medium"
    ) -> Dict[str, bool]:
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
            results["telegram"] = self._send_telegram(formatted)
        
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
        Format recommendations into SHORT, actionable messages for Telegram.
        
        Format hierarchy (most important first):
        1. Action type (Close/Roll)
        2. Contract count  
        3. Symbol + Strike
        4. Price to close at
        5. Profit %
        6. Account name
        7. Why (brief reasoning)
        """
        from datetime import datetime
        
        lines = []
        
        # Group by priority
        by_priority = {"urgent": [], "high": [], "medium": [], "low": []}
        for rec in recommendations:
            priority = rec.get("priority", "low")
            by_priority[priority].append(rec)
        
        # Process urgent/high first
        for priority in ["urgent", "high", "medium", "low"]:
            recs = by_priority[priority]
            if not recs:
                continue
            
            # Show ALL recommendations - no truncation
            for rec in recs:
                rec_type = rec.get("type", "")
                context = rec.get("context", {})
                
                # Extract common fields
                symbol = context.get("symbol", "")
                strike = context.get("strike_price", "")
                opt_type = context.get("option_type", "call")
                contracts = context.get("contracts", 1)
                account = rec.get("account_name") or context.get("account_name") or context.get("account", "")
                current_premium = context.get("current_premium", 0)
                profit_pct = context.get("profit_percent", 0)
                
                # Account tag (short)
                account_short = ""
                if account:
                    # Shorten account name: "Neel's Brokerage" -> "Neel"
                    account_short = account.split("'")[0] if "'" in account else account[:10]
                
                if rec_type == "close_early_opportunity":
                    # CLOSE: 3 TSLA $490 calls @ $0.15 (91%) [Neel]
                    # Why: RSI overbought
                    price_str = f"@ ${current_premium:.2f}" if current_premium else ""
                    line = f"*CLOSE:* {contracts} {symbol} ${strike} {opt_type} {price_str} ({profit_pct:.0f}%)"
                    if account_short:
                        line += f" [{account_short}]"
                    lines.append(line)
                    
                    # Add brief reason if available
                    risk_factors = context.get("risk_factors", [])
                    if risk_factors:
                        # Shorten the reason
                        reason = risk_factors[0]
                        if "RSI" in reason:
                            reason = "RSI overbought"
                        elif "Bollinger" in reason:
                            reason = "Near upper Bollinger band"
                        lines.append(f"  ↳ {reason}")
                
                elif rec_type == "early_roll_opportunity":
                    # ROLL: TSLA 3x $490 Dec 19 → $505 Dec 26 · Stock $450 (91% profit) [Neel]
                    days_left = context.get("days_remaining", 0)
                    current_exp = context.get("expiration_date", "")
                    new_exp = context.get("new_expiration", "")
                    new_strike = context.get("new_strike", strike)
                    current_price = context.get("current_price", 0)
                    
                    # Format dates
                    current_exp_str = ""
                    new_exp_str = ""
                    try:
                        from datetime import datetime as dt
                        if current_exp:
                            exp_dt = dt.fromisoformat(current_exp.replace('Z', '+00:00')) if 'T' in current_exp else dt.strptime(current_exp, '%Y-%m-%d')
                            current_exp_str = exp_dt.strftime('%b %d')
                        if new_exp:
                            new_exp_dt = dt.fromisoformat(new_exp.replace('Z', '+00:00')) if 'T' in new_exp else dt.strptime(new_exp, '%Y-%m-%d')
                            new_exp_str = new_exp_dt.strftime('%b %d')
                    except:
                        pass
                    
                    line = f"*ROLL:* {symbol} {contracts}x ${strike}"
                    if current_exp_str:
                        line += f" {current_exp_str}"
                    line += f" → ${new_strike:.0f}"
                    if new_exp_str:
                        line += f" {new_exp_str}"
                    if current_price:
                        line += f" · Stock ${current_price:.0f}"
                    line += f" ({profit_pct:.0f}% profit)"
                    if account_short:
                        line += f" [{account_short}]"
                    lines.append(line)
                
                elif rec_type == "roll_options":
                    # ITM or standard roll
                    old_strike = context.get("old_strike", context.get("current_strike", strike))
                    current_exp = context.get("current_expiration", "")
                    current_price = context.get("current_price", 0)
                    scenario = context.get("scenario", "")
                    
                    # Format current expiration date
                    current_exp_str = ""
                    if current_exp:
                        try:
                            from datetime import datetime as dt
                            exp_date = dt.fromisoformat(current_exp.replace('Z', '+00:00')) if 'T' in current_exp else dt.strptime(current_exp, '%Y-%m-%d')
                            current_exp_str = exp_date.strftime('%b %d')
                        except:
                            current_exp_str = current_exp[5:10] if len(current_exp) >= 10 else current_exp
                    
                    if scenario == "C_itm_optimized" and context.get("roll_options"):
                        # ITM Roll with options
                        roll_options = context.get("roll_options", [])
                        rec_opt = context.get("recommended_option", "Moderate")
                        for opt in roll_options:
                            if opt.get("label") == rec_opt:
                                net_cost = opt.get("net_cost", 0)
                                new_strike = opt.get("strike", 0)
                                exp_display = opt.get("expiration_display", "")
                                
                                cost_str = f"+${abs(net_cost):.2f}" if net_cost < 0 else f"-${net_cost:.2f}"
                                # Format: ROLL: FIG 1x $60 Jan 16 → $60 Dec 26 · Stock $36 [Neel]
                                line = f"*ROLL:* {symbol} {contracts}x ${old_strike} {current_exp_str} → ${new_strike:.0f} {exp_display}"
                                if current_price:
                                    line += f" · Stock ${current_price:.0f}"
                                line += f" ({cost_str})"
                                if account_short:
                                    line += f" [{account_short}]"
                                lines.append(line)
                                break
                    else:
                        # Standard roll
                        new_strike = context.get("new_strike", "")
                        new_exp = context.get("new_expiration", "")
                        if new_strike and new_exp:
                            try:
                                from datetime import datetime as dt
                                new_exp_date = dt.fromisoformat(new_exp.replace('Z', '+00:00')) if 'T' in new_exp else dt.strptime(new_exp, '%Y-%m-%d')
                                new_exp_str = new_exp_date.strftime('%b %d')
                            except:
                                new_exp_str = new_exp[5:10] if len(new_exp) >= 10 else new_exp
                            line = f"*ROLL:* {symbol} {contracts}x ${old_strike} {current_exp_str} → ${new_strike} {new_exp_str}"
                            if current_price:
                                line += f" · Stock ${current_price:.0f}"
                        else:
                            line = f"*ROLL:* {symbol} {contracts}x ${old_strike} {opt_type}"
                            if current_price:
                                line += f" · Stock ${current_price:.0f}"
                        if account_short:
                            line += f" [{account_short}]"
                        lines.append(line)
                
                elif rec_type == "new_covered_call":
                    # SELL: 5 AAPL $290 calls Dec 20 · Stock $248 [Neel]
                    uncovered = context.get("uncovered_contracts", contracts)
                    rec_strike = context.get("recommended_strike", strike)
                    current_price = context.get("current_price", 0)
                    exp_date = context.get("expiration_date", "")
                    
                    # Format expiration
                    exp_str = ""
                    if exp_date:
                        try:
                            from datetime import datetime as dt
                            exp_dt = dt.fromisoformat(exp_date.replace('Z', '+00:00')) if 'T' in exp_date else dt.strptime(exp_date, '%Y-%m-%d')
                            exp_str = exp_dt.strftime('%b %d')
                        except:
                            exp_str = exp_date[5:10] if len(exp_date) >= 10 else exp_date
                    
                    line = f"*SELL:* {uncovered} {symbol} ${rec_strike:.0f} calls"
                    if exp_str:
                        line += f" {exp_str}"
                    if current_price:
                        line += f" · Stock ${current_price:.0f}"
                    if account_short:
                        line += f" [{account_short}]"
                    lines.append(line)
                
                elif rec_type == "bull_put_spread":
                    # BULL PUT PORTFOLIO: AAPL $280/$270 ($1.50 credit)
                    sell_strike = context.get("sell_strike", "")
                    buy_strike = context.get("buy_strike", "")
                    credit = context.get("net_credit", 0)
                    if sell_strike and buy_strike:
                        lines.append(f"*BULL PUT PORTFOLIO:* {symbol} ${sell_strike:.0f}/${buy_strike:.0f} (${credit:.2f} cr)")
                
                elif rec_type == "mega_cap_bull_put":
                    # BULL PUT NOT IN PORTFOLIO: CSCO $79/$74 ($1.60 credit)
                    sell_strike = context.get("sell_strike", "")
                    buy_strike = context.get("buy_strike", "")
                    credit = context.get("net_credit", 0)
                    if sell_strike and buy_strike:
                        lines.append(f"*BULL PUT NOT IN PORTFOLIO:* {symbol} ${sell_strike:.0f}/${buy_strike:.0f} (${credit:.2f} cr)")
                
                elif rec_type == "sell_unsold_contracts":
                    # SELL: 18 AAPL $288 calls Dec 20 · Stock $248 ($844/wk)
                    unsold = context.get("unsold_contracts", 0)
                    weekly = context.get("weekly_income", 0)
                    rec_strike = context.get("strike_price", 0)
                    current_price = context.get("current_price", 0)
                    
                    # Calculate next Friday for expiration
                    from datetime import date as d, timedelta
                    today = d.today()
                    days_ahead = 4 - today.weekday()
                    if days_ahead <= 0:
                        days_ahead += 7
                    next_friday = today + timedelta(days=days_ahead)
                    exp_str = next_friday.strftime('%b %d')
                    
                    if rec_strike:
                        strike_str = f"${rec_strike:.0f}" if rec_strike >= 100 else f"${rec_strike:.2f}"
                        line = f"*SELL:* {unsold} {symbol} {strike_str} calls {exp_str}"
                    else:
                        line = f"*SELL:* {unsold} {symbol} calls {exp_str}"
                    
                    if current_price:
                        line += f" · Stock ${current_price:.0f}"
                    line += f" (${weekly:.0f}/wk)"
                    lines.append(line)
                
                else:
                    # Default - use title (already optimized in strategy)
                    lines.append(f"• {rec.get('title', '')}")
            
            lines.append("")  # Blank line between priorities
        
        # Remove trailing empty lines
        while lines and lines[-1] == "":
            lines.pop()
        
        # Show ALL recommendations - no truncation message needed
        
        # Short timestamp in local time
        now = datetime.now()
        time_str = now.strftime("%I:%M %p").lstrip('0')
        lines.append(f"_{time_str}_")
        
        return "\n".join(lines)
    
    def _send_telegram(self, message: str) -> bool:
        """Send message via Telegram bot."""
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
            
            logger.info("Telegram notification sent successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return False
    
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

