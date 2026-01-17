"""
Expense Notification Service

Sends mobile notifications one day before forecasted expenses are due.
Helps user prepare by transferring money to spending account in advance.
"""

import logging
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.modules.strategies.expense_forecasting_service import ExpenseForecastingService

logger = logging.getLogger(__name__)


class ExpenseNotificationService:
    """Service for sending expense reminder notifications."""

    def __init__(self):
        self.forecasting_service = ExpenseForecastingService()

    def get_expenses_due_tomorrow(self, db: Session) -> List[Dict[str, Any]]:
        """
        Get all expenses forecasted to be due tomorrow.

        Args:
            db: Database session

        Returns:
            List of expenses due tomorrow with details
        """
        try:
            # Get forecast for the next 2 days
            current_year = date.today().year
            forecast = self.forecasting_service.forecast_expenses(
                year=current_year,
                months_ahead=1,  # Just need next month
                historical_years=2
            )

            # Calculate tomorrow's date
            tomorrow = date.today() + timedelta(days=1)

            # Find all expenses due tomorrow
            expenses_tomorrow = []

            for month_data in forecast.get('forecasted_months', []):
                for expense in month_data.get('predicted_expenses', []):
                    expense_date_str = expense.get('predicted_date')
                    if not expense_date_str:
                        continue

                    try:
                        # Parse the date
                        expense_date = date.fromisoformat(expense_date_str)

                        # Check if it's tomorrow
                        if expense_date == tomorrow:
                            expenses_tomorrow.append({
                                'description': expense.get('description', 'Unknown expense'),
                                'amount': expense.get('predicted_amount', 0),
                                'confidence': expense.get('confidence', 0),
                                'frequency': expense.get('frequency', 'unknown'),
                                'date': expense_date_str
                            })
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Failed to parse expense date {expense_date_str}: {e}")
                        continue

            if expenses_tomorrow:
                logger.info(f"Found {len(expenses_tomorrow)} expense(s) due tomorrow ({tomorrow})")
            else:
                logger.debug(f"No expenses due tomorrow ({tomorrow})")

            return expenses_tomorrow

        except Exception as e:
            logger.error(f"Error getting expenses due tomorrow: {e}", exc_info=True)
            return []

    def format_expense_notification_message(self, expenses: List[Dict[str, Any]]) -> Optional[str]:
        """
        Format expense reminder message for Telegram.

        Args:
            expenses: List of expenses due tomorrow

        Returns:
            Formatted message string or None if no expenses
        """
        if not expenses:
            return None

        # Calculate tomorrow's date for display
        tomorrow = date.today() + timedelta(days=1)
        tomorrow_str = tomorrow.strftime('%A, %b %d')  # e.g., "Monday, Jan 20"

        # Build message
        lines = [
            "💰 *EXPENSE REMINDER*",
            f"Due {tomorrow_str}:",
            ""
        ]

        # Sort by amount (highest first)
        sorted_expenses = sorted(expenses, key=lambda x: x['amount'], reverse=True)

        total_amount = 0
        for expense in sorted_expenses:
            description = expense['description']
            amount = expense['amount']
            confidence = expense['confidence']

            total_amount += amount

            # Format amount
            amount_str = f"${amount:,.0f}"

            # Add confidence indicator
            if confidence >= 70:
                confidence_emoji = "🟢"
            elif confidence >= 50:
                confidence_emoji = "🟡"
            else:
                confidence_emoji = "🔴"

            # Build line: emoji + description + amount + confidence
            lines.append(f"• {description}: {amount_str} {confidence_emoji}")

        # Add total if multiple expenses
        if len(expenses) > 1:
            lines.append("")
            lines.append(f"*Total: ${total_amount:,.0f}*")

        lines.extend([
            "",
            "💡 _Please transfer money to your spending account_",
            "_to ensure sufficient balance for these charges._"
        ])

        return "\n".join(lines)

    def send_expense_notifications(self, db: Session) -> Dict[str, Any]:
        """
        Check for expenses due tomorrow and send notifications.

        This method is called by the scheduler daily.

        Args:
            db: Database session

        Returns:
            Dict with notification results
        """
        try:
            # Get expenses due tomorrow
            expenses = self.get_expenses_due_tomorrow(db)

            if not expenses:
                logger.info("No expenses due tomorrow - no notifications to send")
                return {
                    'success': True,
                    'expenses_found': 0,
                    'notification_sent': False
                }

            # Format message
            message = self.format_expense_notification_message(expenses)

            if not message:
                logger.warning("Failed to format expense notification message")
                return {
                    'success': False,
                    'expenses_found': len(expenses),
                    'notification_sent': False,
                    'error': 'Failed to format message'
                }

            # Send notification via Telegram
            from app.shared.services.notifications import get_notification_service
            notification_service = get_notification_service()

            if not notification_service.telegram_enabled:
                logger.warning("Telegram notifications not enabled - cannot send expense reminder")
                return {
                    'success': False,
                    'expenses_found': len(expenses),
                    'notification_sent': False,
                    'error': 'Telegram not enabled'
                }

            # Send Telegram message
            success, message_id = notification_service._send_telegram(message)

            if success:
                logger.info(f"Expense notification sent successfully for {len(expenses)} expense(s)")
                return {
                    'success': True,
                    'expenses_found': len(expenses),
                    'notification_sent': True,
                    'telegram_message_id': message_id,
                    'total_amount': sum(e['amount'] for e in expenses)
                }
            else:
                logger.error("Failed to send expense notification via Telegram")
                return {
                    'success': False,
                    'expenses_found': len(expenses),
                    'notification_sent': False,
                    'error': 'Telegram send failed'
                }

        except Exception as e:
            logger.error(f"Error in send_expense_notifications: {e}", exc_info=True)
            return {
                'success': False,
                'expenses_found': 0,
                'notification_sent': False,
                'error': str(e)
            }


# Global service instance
_expense_notification_service: Optional[ExpenseNotificationService] = None


def get_expense_notification_service() -> ExpenseNotificationService:
    """Get or create the global expense notification service instance."""
    global _expense_notification_service
    if _expense_notification_service is None:
        _expense_notification_service = ExpenseNotificationService()
    return _expense_notification_service
