"""
Expense Forecasting Service

Analyzes historical spending patterns to predict future expenses.
Identifies recurring bills and forecasts amounts and dates.
"""

from typing import List, Dict, Any, Tuple
from datetime import datetime, date, timedelta
from collections import defaultdict
import csv
import re
from pathlib import Path
from decimal import Decimal
import statistics


class RecurringExpense:
    """Represents a recurring expense pattern."""

    def __init__(self, description: str):
        self.description = description
        self.occurrences: List[Tuple[date, float]] = []
        self.avg_amount = 0.0
        self.std_dev = 0.0
        self.avg_day_of_month = 0
        self.frequency = "monthly"  # monthly, quarterly, annual
        self.confidence = 0.0

    def add_occurrence(self, transaction_date: date, amount: float):
        """Add an occurrence of this expense."""
        self.occurrences.append((transaction_date, amount))

    def analyze(self):
        """Analyze the pattern to determine avg amount, timing, confidence."""
        if not self.occurrences:
            return

        # Calculate average amount
        amounts = [amt for _, amt in self.occurrences]
        self.avg_amount = statistics.mean(amounts)

        # Calculate standard deviation for confidence
        if len(amounts) > 1:
            self.std_dev = statistics.stdev(amounts)
            # Confidence: higher when std dev is low relative to mean
            cv = (self.std_dev / self.avg_amount) if self.avg_amount > 0 else 1.0
            self.confidence = max(0, min(100, (1 - cv) * 100))
        else:
            self.confidence = 50  # Medium confidence for single occurrence

        # Calculate average day of month
        days = [d.day for d, _ in self.occurrences]
        self.avg_day_of_month = int(statistics.mean(days))

        # Determine frequency
        if len(self.occurrences) >= 2:
            dates_sorted = sorted([d for d, _ in self.occurrences])
            gaps = [(dates_sorted[i+1] - dates_sorted[i]).days
                   for i in range(len(dates_sorted)-1)]
            avg_gap = statistics.mean(gaps)

            if avg_gap < 40:
                self.frequency = "monthly"
            elif avg_gap < 120:
                self.frequency = "quarterly"
            else:
                self.frequency = "annual"


class ExpenseForecastingService:
    """Service for forecasting future expenses based on historical patterns."""

    def __init__(self, robinhood_data_path: str = None):
        """
        Initialize the forecasting service.

        Args:
            robinhood_data_path: Path to Robinhood CSV data directory
        """
        if robinhood_data_path:
            self.robinhood_dir = Path(robinhood_data_path)
        else:
            # Default path
            self.robinhood_dir = Path(__file__).parent.parent.parent.parent.parent / "data" / "processed" / "investments" / "robinhood"

    def load_spending_transactions(self, year: int = None) -> List[Dict[str, Any]]:
        """
        Load spending transactions from CSV files.

        Args:
            year: Specific year to load, or None for all years

        Returns:
            List of transaction dictionaries
        """
        transactions = []

        # Try year-specific file first
        if year:
            csv_path = self.robinhood_dir / f"Neel Individual {year} complete.csv"
            if not csv_path.exists():
                csv_path = self.robinhood_dir / "Neel Individual 2021-2025 all data.csv"
        else:
            csv_path = self.robinhood_dir / "Neel Individual 2021-2025 all data.csv"

        if not csv_path.exists():
            return transactions

        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                activity_date = row.get('Activity Date', '')
                description = row.get('Description', '')
                trans_code = row.get('Trans Code', '')
                amount_str = row.get('Amount', '')

                if not activity_date or not amount_str:
                    continue

                date_match = re.match(r'(\d+)/(\d+)/(\d+)', activity_date)
                if not date_match:
                    continue

                month_num = int(date_match.group(1))
                day_num = int(date_match.group(2))
                year_num = int(date_match.group(3))

                # Filter by year if specified
                if year and year_num != year:
                    continue

                amount_clean = amount_str.replace('$', '').replace(',', '').replace('(', '').replace(')', '')
                try:
                    amount = abs(float(amount_clean))
                except ValueError:
                    continue

                # Check if this is a spending transaction
                is_spending = False
                if trans_code == 'ACH' and 'Withdrawal' in description:
                    is_spending = True
                elif trans_code == 'XENT_CC' and 'Credit Card balance payment' in description:
                    is_spending = True
                elif trans_code == 'XENT' and 'Brokerage to Spending' in description:
                    is_spending = True

                if is_spending:
                    transactions.append({
                        'date': date(year_num, month_num, day_num),
                        'amount': amount,
                        'description': description,
                        'trans_code': trans_code
                    })

        return transactions

    def identify_recurring_expenses(self, transactions: List[Dict[str, Any]]) -> List[RecurringExpense]:
        """
        Identify recurring expense patterns from transactions.

        Looks for:
        - Similar descriptions
        - Similar amounts (within 10%)
        - Regular timing

        Args:
            transactions: List of spending transactions

        Returns:
            List of RecurringExpense objects
        """
        # Group transactions by similar descriptions
        expense_groups: Dict[str, RecurringExpense] = {}

        for txn in transactions:
            description = txn['description']
            amount = txn['amount']
            txn_date = txn['date']

            # Normalize description for grouping
            # Extract key terms from description
            desc_key = self._normalize_description(description)

            # Find matching expense group or create new one
            matched = False
            for key, expense in expense_groups.items():
                # Check if amounts are similar (within 15% tolerance)
                if expense.occurrences:
                    avg_amt = statistics.mean([amt for _, amt in expense.occurrences])
                    amt_diff_pct = abs(amount - avg_amt) / avg_amt if avg_amt > 0 else 1.0

                    # Match if similar description and similar amount
                    if self._descriptions_similar(key, desc_key) and amt_diff_pct < 0.15:
                        expense.add_occurrence(txn_date, amount)
                        matched = True
                        break

            if not matched:
                expense = RecurringExpense(description)
                expense.add_occurrence(txn_date, amount)
                expense_groups[desc_key] = expense

        # Analyze patterns and filter for truly recurring expenses
        recurring_expenses = []
        for expense in expense_groups.values():
            # Only consider as "recurring" if seen at least 2 times
            if len(expense.occurrences) >= 2:
                expense.analyze()
                recurring_expenses.append(expense)

        # Sort by average amount (largest first)
        recurring_expenses.sort(key=lambda e: e.avg_amount, reverse=True)

        return recurring_expenses

    def _normalize_description(self, description: str) -> str:
        """Normalize description for pattern matching."""
        # Remove common noise words
        desc = description.lower()
        desc = re.sub(r'withdrawal|payment|transfer|balance', '', desc)
        desc = re.sub(r'\s+', ' ', desc).strip()
        return desc[:50]  # First 50 chars

    def _descriptions_similar(self, desc1: str, desc2: str) -> bool:
        """Check if two descriptions are similar enough to be the same expense."""
        # Simple similarity: check if one contains the other
        return desc1 in desc2 or desc2 in desc1

    def forecast_expenses(
        self,
        year: int,
        months_ahead: int = 3,
        historical_years: int = 2
    ) -> Dict[str, Any]:
        """
        Forecast expenses for upcoming months based on historical patterns.

        Args:
            year: Current year
            months_ahead: How many months to forecast
            historical_years: How many years of history to analyze

        Returns:
            Dictionary with forecast data
        """
        # Load historical data
        all_transactions = []
        for y in range(year - historical_years, year + 1):
            all_transactions.extend(self.load_spending_transactions(y))

        # Identify recurring patterns
        recurring_expenses = self.identify_recurring_expenses(all_transactions)

        # Generate forecast
        current_date = datetime.now().date()
        forecasted_months = []

        for month_offset in range(1, months_ahead + 1):
            forecast_month = current_date + timedelta(days=30 * month_offset)
            forecast_year = forecast_month.year
            forecast_month_num = forecast_month.month

            # Predict expenses for this month
            predicted_expenses = []
            total_predicted = 0.0

            for expense in recurring_expenses:
                # Skip if not likely to occur this month based on frequency
                if expense.frequency == "quarterly":
                    # Check if this month aligns with quarterly pattern
                    last_occurrence = max([d for d, _ in expense.occurrences])
                    months_since = (forecast_month.year - last_occurrence.year) * 12 + \
                                  (forecast_month.month - last_occurrence.month)
                    if months_since % 3 != 0:
                        continue
                elif expense.frequency == "annual":
                    # Only predict if same month as last occurrence
                    last_occurrence = max([d for d, _ in expense.occurrences])
                    if forecast_month.month != last_occurrence.month:
                        continue

                # Predict date
                predicted_day = min(expense.avg_day_of_month, 28)  # Cap at 28 to avoid month-end issues
                predicted_date = date(forecast_year, forecast_month_num, predicted_day)

                predicted_expenses.append({
                    'description': expense.description,
                    'predicted_date': predicted_date.isoformat(),
                    'predicted_amount': round(expense.avg_amount, 2),
                    'confidence': round(expense.confidence, 1),
                    'frequency': expense.frequency,
                    'historical_occurrences': len(expense.occurrences),
                    'amount_range': {
                        'min': round(expense.avg_amount - expense.std_dev, 2),
                        'max': round(expense.avg_amount + expense.std_dev, 2)
                    }
                })

                total_predicted += expense.avg_amount

            forecasted_months.append({
                'year': forecast_year,
                'month': forecast_month_num,
                'month_name': forecast_month.strftime('%B'),
                'predicted_expenses': predicted_expenses,
                'total_predicted': round(total_predicted, 2),
                'num_predicted_expenses': len(predicted_expenses)
            })

        # Calculate summary statistics
        total_recurring = len(recurring_expenses)
        avg_monthly_recurring = statistics.mean([m['total_predicted'] for m in forecasted_months]) if forecasted_months else 0

        return {
            'forecast_period': {
                'start_month': forecasted_months[0] if forecasted_months else None,
                'end_month': forecasted_months[-1] if forecasted_months else None,
                'months_ahead': months_ahead
            },
            'forecasted_months': forecasted_months,
            'summary': {
                'total_recurring_expenses_identified': total_recurring,
                'avg_monthly_recurring_spending': round(avg_monthly_recurring, 2),
                'historical_years_analyzed': historical_years,
                'total_transactions_analyzed': len(all_transactions)
            },
            'recurring_patterns': [
                {
                    'description': e.description,
                    'avg_amount': round(e.avg_amount, 2),
                    'frequency': e.frequency,
                    'avg_day_of_month': e.avg_day_of_month,
                    'confidence': round(e.confidence, 1),
                    'occurrences': len(e.occurrences)
                }
                for e in recurring_expenses
            ]
        }
