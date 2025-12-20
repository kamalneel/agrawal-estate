"""
Insights Engine - Automatically discovers interesting patterns and anomalies
in the Agrawal family financial data.

Uses statistical methods (z-scores, percentiles) and pattern detection
to surface noteworthy insights about portfolio performance.

Insight Categories:
1. Record-Breaking - All-time highs/lows
2. Outliers - Statistically unusual values (> 2 std dev)
3. Trend Changes - Leadership changes, reversals
4. Milestones - Crossing significant thresholds
5. Comparisons - Period-over-period performance
6. Streaks - Consecutive positive/negative periods
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Set
from collections import defaultdict
import statistics
import hashlib
import json
from pathlib import Path
from sqlalchemy.orm import Session

from app.modules.income.services import get_income_service
from app.modules.investments.services import get_holdings_summary


# Path for storing archived insight IDs
ARCHIVE_FILE = Path(__file__).parent.parent.parent.parent / "data" / "insights_archive.json"


def _load_archived_ids() -> Set[str]:
    """Load the set of archived insight IDs from file."""
    try:
        if ARCHIVE_FILE.exists():
            with open(ARCHIVE_FILE, 'r') as f:
                data = json.load(f)
                return set(data.get('archived_ids', []))
    except Exception as e:
        print(f"Error loading archived insights: {e}")
    return set()


def _save_archived_ids(archived_ids: Set[str]) -> None:
    """Save the set of archived insight IDs to file."""
    try:
        ARCHIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ARCHIVE_FILE, 'w') as f:
            json.dump({
                'archived_ids': list(archived_ids),
                'updated_at': datetime.now().isoformat()
            }, f, indent=2)
    except Exception as e:
        print(f"Error saving archived insights: {e}")


def archive_insight(insight_id: str) -> bool:
    """Archive an insight by its ID."""
    archived_ids = _load_archived_ids()
    archived_ids.add(insight_id)
    _save_archived_ids(archived_ids)
    return True


def unarchive_insight(insight_id: str) -> bool:
    """Remove an insight from the archive."""
    archived_ids = _load_archived_ids()
    archived_ids.discard(insight_id)
    _save_archived_ids(archived_ids)
    return True


def clear_archive() -> int:
    """Clear all archived insights. Returns count of cleared items."""
    archived_ids = _load_archived_ids()
    count = len(archived_ids)
    _save_archived_ids(set())
    return count


def get_archived_count() -> int:
    """Get the count of archived insights."""
    return len(_load_archived_ids())


class InsightCategory(str, Enum):
    RECORD = "record"           # All-time highs/lows
    OUTLIER = "outlier"         # Statistically unusual values
    TREND = "trend"             # Leadership changes, reversals
    MILESTONE = "milestone"     # Crossing thresholds
    COMPARISON = "comparison"   # Period-over-period
    STREAK = "streak"           # Consecutive patterns


class InsightSentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    CELEBRATION = "celebration"  # Extra special positive events


@dataclass
class Insight:
    """A single insight discovered about the family's finances."""
    category: InsightCategory
    sentiment: InsightSentiment
    title: str
    description: str
    metric_name: str
    metric_value: Optional[float] = None
    comparison_value: Optional[float] = None
    change_percent: Optional[float] = None
    icon: str = "sparkles"  # Lucide icon name
    priority: int = 50  # 1-100, higher = more important
    tags: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def id(self) -> str:
        """Generate a unique ID for this insight based on its key properties."""
        # Use category, metric_name, and a simplified title for stable ID
        key = f"{self.category.value}:{self.metric_name}:{self.title[:50]}"
        return hashlib.md5(key.encode()).hexdigest()[:12]


class InsightsEngine:
    """
    Engine for discovering interesting patterns in financial data.
    
    Uses statistical methods and rule-based detection to surface insights:
    - Z-score analysis for outlier detection
    - Percentile tracking for records
    - Trend analysis for pattern changes
    """
    
    # Thresholds for outlier detection (in standard deviations)
    OUTLIER_THRESHOLD = 2.0
    SIGNIFICANT_THRESHOLD = 1.5
    
    # Milestone thresholds (in dollars)
    MILESTONES = [1000, 5000, 10000, 25000, 50000, 100000, 250000, 500000, 1000000]
    
    def __init__(self, db: Session):
        self.db = db
        self.insights: List[Insight] = []
        
    def discover_all_insights(self, include_archived: bool = False, limit: int = 5) -> List[Dict]:
        """
        Run all insight discovery algorithms and return combined results.
        Returns insights sorted by priority (most important first).
        
        Args:
            include_archived: If True, include archived insights. If False, exclude them.
            limit: Maximum number of insights to return.
        """
        self.insights = []
        
        # Get income data
        income_service = get_income_service()
        
        # Run discovery algorithms
        self._discover_options_insights(income_service)
        self._discover_dividend_insights(income_service)
        self._discover_portfolio_insights()
        self._discover_account_insights(income_service)
        self._discover_symbol_insights(income_service)
        self._discover_streak_insights(income_service)
        self._discover_comparison_insights(income_service)
        self._discover_income_totals(income_service)
        self._discover_top_performers(income_service)
        self._discover_monthly_insights(income_service)
        
        # Sort by priority (highest first)
        self.insights.sort(key=lambda x: x.priority, reverse=True)
        
        # Load archived IDs
        archived_ids = _load_archived_ids() if not include_archived else set()
        
        # Filter out archived insights unless requested
        filtered_insights = [
            i for i in self.insights 
            if include_archived or i.id not in archived_ids
        ]
        
        # Convert to dict for JSON serialization
        return [self._insight_to_dict(i) for i in filtered_insights[:limit]]
    
    def get_all_insights_with_status(self) -> Tuple[List[Dict], List[Dict]]:
        """
        Get all insights split into active and archived.
        Returns (active_insights, archived_insights).
        """
        self.insights = []
        
        # Get income data
        income_service = get_income_service()
        
        # Run discovery algorithms
        self._discover_options_insights(income_service)
        self._discover_dividend_insights(income_service)
        self._discover_portfolio_insights()
        self._discover_account_insights(income_service)
        self._discover_symbol_insights(income_service)
        self._discover_streak_insights(income_service)
        self._discover_comparison_insights(income_service)
        self._discover_income_totals(income_service)
        self._discover_top_performers(income_service)
        self._discover_monthly_insights(income_service)
        
        # Sort by priority (highest first)
        self.insights.sort(key=lambda x: x.priority, reverse=True)
        
        # Load archived IDs
        archived_ids = _load_archived_ids()
        
        # Split into active and archived
        active = []
        archived = []
        
        for insight in self.insights:
            insight_dict = self._insight_to_dict(insight)
            if insight.id in archived_ids:
                archived.append(insight_dict)
            else:
                active.append(insight_dict)
        
        return active, archived
    
    def _insight_to_dict(self, insight: Insight) -> Dict:
        """Convert insight dataclass to dictionary."""
        return {
            "id": insight.id,
            "category": insight.category.value,
            "sentiment": insight.sentiment.value,
            "title": insight.title,
            "description": insight.description,
            "metric_name": insight.metric_name,
            "metric_value": insight.metric_value,
            "comparison_value": insight.comparison_value,
            "change_percent": insight.change_percent,
            "icon": insight.icon,
            "priority": insight.priority,
            "tags": insight.tags,
            "timestamp": insight.timestamp.isoformat(),
        }
    
    def _calculate_z_score(self, value: float, values: List[float]) -> float:
        """Calculate z-score for a value relative to a distribution."""
        if len(values) < 2:
            return 0.0
        mean = statistics.mean(values)
        stdev = statistics.stdev(values)
        if stdev == 0:
            return 0.0
        return (value - mean) / stdev
    
    def _get_percentile(self, value: float, values: List[float]) -> float:
        """Get the percentile rank of a value."""
        if not values:
            return 50.0
        sorted_vals = sorted(values)
        count_below = sum(1 for v in sorted_vals if v < value)
        return (count_below / len(sorted_vals)) * 100
    
    def _format_currency(self, value: float) -> str:
        """Format a number as currency."""
        if value >= 1000000:
            return f"${value/1000000:.1f}M"
        elif value >= 1000:
            return f"${value/1000:.1f}K"
        else:
            return f"${value:,.0f}"
    
    def _get_month_name(self, month_key: str) -> str:
        """Convert YYYY-MM to 'Month YYYY' format."""
        try:
            year, month = month_key.split('-')
            dt = datetime(int(year), int(month), 1)
            return dt.strftime("%B %Y")
        except:
            return month_key
    
    def _discover_options_insights(self, income_service) -> None:
        """Discover insights about options income."""
        options_data = income_service.get_consolidated_options_income()
        monthly = options_data.get('monthly', {})
        
        if len(monthly) < 2:
            return
        
        # Get current and previous month
        sorted_months = sorted(monthly.keys())
        current_month = sorted_months[-1]
        current_value = monthly[current_month]
        
        # Get all values for statistics
        all_values = list(monthly.values())
        positive_values = [v for v in all_values if v > 0]
        
        # Check for all-time high
        if current_value > 0 and current_value == max(positive_values):
            self.insights.append(Insight(
                category=InsightCategory.RECORD,
                sentiment=InsightSentiment.CELEBRATION,
                title="🏆 All-Time High Options Income!",
                description=f"{self._get_month_name(current_month)} achieved the highest options income in Agrawal family history at {self._format_currency(current_value)}.",
                metric_name="options_income",
                metric_value=current_value,
                icon="trophy",
                priority=95,
                tags=["options", "record", "income"],
            ))
        
        # Check for statistical outlier (positive)
        if len(positive_values) >= 6:
            z_score = self._calculate_z_score(current_value, positive_values)
            if z_score > self.OUTLIER_THRESHOLD:
                percentile = self._get_percentile(current_value, positive_values)
                self.insights.append(Insight(
                    category=InsightCategory.OUTLIER,
                    sentiment=InsightSentiment.POSITIVE,
                    title="Exceptional Options Performance",
                    description=f"This month's options income of {self._format_currency(current_value)} is in the {percentile:.0f}th percentile - significantly above your historical average.",
                    metric_name="options_income",
                    metric_value=current_value,
                    icon="trending-up",
                    priority=80,
                    tags=["options", "outlier"],
                ))
        
        # Month-over-month comparison
        if len(sorted_months) >= 2:
            prev_month = sorted_months[-2]
            prev_value = monthly[prev_month]
            if prev_value > 0:
                pct_change = ((current_value - prev_value) / prev_value) * 100
                if pct_change > 50:
                    self.insights.append(Insight(
                        category=InsightCategory.COMPARISON,
                        sentiment=InsightSentiment.POSITIVE,
                        title="Strong Options Month",
                        description=f"Options income surged {pct_change:.0f}% from {self._get_month_name(prev_month)} to {self._get_month_name(current_month)}.",
                        metric_name="options_income_mom",
                        metric_value=current_value,
                        comparison_value=prev_value,
                        change_percent=pct_change,
                        icon="arrow-up-right",
                        priority=65,
                        tags=["options", "growth"],
                    ))
                elif pct_change < -30:
                    self.insights.append(Insight(
                        category=InsightCategory.COMPARISON,
                        sentiment=InsightSentiment.NEUTRAL,
                        title="Options Income Pullback",
                        description=f"Options income decreased {abs(pct_change):.0f}% from {self._get_month_name(prev_month)}. Consider reviewing open positions.",
                        metric_name="options_income_mom",
                        metric_value=current_value,
                        comparison_value=prev_value,
                        change_percent=pct_change,
                        icon="arrow-down-right",
                        priority=55,
                        tags=["options", "decline"],
                    ))
    
    def _discover_dividend_insights(self, income_service) -> None:
        """Discover insights about dividend income."""
        dividend_data = income_service.get_consolidated_dividend_income()
        monthly = dividend_data.get('monthly', {})
        by_symbol = dividend_data.get('by_symbol', {})
        
        if len(monthly) < 2:
            return
        
        sorted_months = sorted(monthly.keys())
        current_month = sorted_months[-1]
        current_value = monthly[current_month]
        all_values = [v for v in monthly.values() if v > 0]
        
        # Check for record dividend month
        if current_value > 0 and len(all_values) >= 3 and current_value == max(all_values):
            self.insights.append(Insight(
                category=InsightCategory.RECORD,
                sentiment=InsightSentiment.POSITIVE,
                title="Peak Dividend Month",
                description=f"Record dividend income of {self._format_currency(current_value)} received in {self._get_month_name(current_month)}.",
                metric_name="dividend_income",
                metric_value=current_value,
                icon="coins",
                priority=75,
                tags=["dividends", "record"],
            ))
        
        # Top dividend payer insight
        if by_symbol:
            top_symbols = sorted(by_symbol.items(), key=lambda x: x[1], reverse=True)[:3]
            if top_symbols:
                top_symbol, top_amount = top_symbols[0]
                total_dividends = dividend_data.get('total_income', 1)
                pct = (top_amount / total_dividends) * 100 if total_dividends > 0 else 0
                
                if pct > 30:
                    self.insights.append(Insight(
                        category=InsightCategory.TREND,
                        sentiment=InsightSentiment.NEUTRAL,
                        title=f"{top_symbol} Leads Dividend Income",
                        description=f"{top_symbol} contributes {pct:.0f}% of your total dividend income ({self._format_currency(top_amount)} total).",
                        metric_name="top_dividend_stock",
                        metric_value=top_amount,
                        icon="bar-chart-2",
                        priority=50,
                        tags=["dividends", top_symbol],
                    ))
    
    def _discover_portfolio_insights(self) -> None:
        """Discover insights about portfolio holdings."""
        try:
            holdings_summary = get_holdings_summary(self.db)
            total_value = holdings_summary.get('totalValue', 0)
            by_owner = holdings_summary.get('byOwner', {})
            
            # Check for milestone crossings in total value
            for milestone in self.MILESTONES:
                if total_value >= milestone and total_value < milestone * 1.1:
                    self.insights.append(Insight(
                        category=InsightCategory.MILESTONE,
                        sentiment=InsightSentiment.CELEBRATION,
                        title=f"Portfolio Crossed {self._format_currency(milestone)}!",
                        description=f"Your public equity portfolio has grown to {self._format_currency(total_value)}, crossing the {self._format_currency(milestone)} milestone.",
                        metric_name="portfolio_value",
                        metric_value=total_value,
                        icon="target",
                        priority=85,
                        tags=["portfolio", "milestone"],
                    ))
                    break
            
            # Check account distribution
            if by_owner:
                owner_values = [(name, data.get('value', 0)) for name, data in by_owner.items()]
                owner_values.sort(key=lambda x: x[1], reverse=True)
                
                if len(owner_values) >= 2:
                    top_owner, top_value = owner_values[0]
                    pct = (top_value / total_value) * 100 if total_value > 0 else 0
                    
                    if pct > 60:
                        self.insights.append(Insight(
                            category=InsightCategory.TREND,
                            sentiment=InsightSentiment.NEUTRAL,
                            title=f"{top_owner}'s Accounts Lead",
                            description=f"{top_owner}'s accounts hold {pct:.0f}% of the family's public equity ({self._format_currency(top_value)}).",
                            metric_name="account_concentration",
                            metric_value=pct,
                            icon="pie-chart",
                            priority=40,
                            tags=["portfolio", "distribution"],
                        ))
        except Exception as e:
            print(f"Error discovering portfolio insights: {e}")
    
    def _discover_account_insights(self, income_service) -> None:
        """Discover insights about individual account performance."""
        options_data = income_service.get_consolidated_options_income()
        by_account = options_data.get('by_account', {})
        
        if not by_account:
            return
        
        # Find best performing account this month
        current_month = None
        account_monthly = {}
        
        for account_name, account_data in by_account.items():
            monthly = account_data.get('monthly', {})
            if monthly:
                sorted_months = sorted(monthly.keys())
                if sorted_months:
                    if current_month is None:
                        current_month = sorted_months[-1]
                    month_val = monthly.get(current_month, 0)
                    if month_val > 0:
                        account_monthly[account_name] = month_val
        
        if account_monthly:
            # Best account this month
            best_account = max(account_monthly, key=account_monthly.get)
            best_value = account_monthly[best_account]
            
            # Check if this account has never been the leader before
            historical_leaders = defaultdict(int)
            for account_name, account_data in by_account.items():
                for month, val in account_data.get('monthly', {}).items():
                    if month < current_month and val > 0:
                        # Find leader for this historical month
                        month_vals = {}
                        for a_name, a_data in by_account.items():
                            month_vals[a_name] = a_data.get('monthly', {}).get(month, 0)
                        if month_vals:
                            leader = max(month_vals, key=month_vals.get)
                            historical_leaders[leader] += 1
            
            if historical_leaders and best_account not in historical_leaders:
                self.insights.append(Insight(
                    category=InsightCategory.TREND,
                    sentiment=InsightSentiment.POSITIVE,
                    title=f"New Leader: {best_account}",
                    description=f"{best_account} leads options income for the first time with {self._format_currency(best_value)} in {self._get_month_name(current_month)}!",
                    metric_name="account_leadership",
                    metric_value=best_value,
                    icon="crown",
                    priority=70,
                    tags=["accounts", "leadership", "first-time"],
                ))
    
    def _discover_symbol_insights(self, income_service) -> None:
        """Discover insights about individual stock symbols."""
        options_data = income_service.get_consolidated_options_income()
        transactions = options_data.get('transactions', [])
        
        if len(transactions) < 10:
            return
        
        # Track monthly income by symbol
        symbol_monthly: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        
        for txn in transactions:
            if txn.get('trans_code') in ('STO', 'BTC', 'OEXP', 'OASGN'):
                date_str = txn.get('date', '')[:7]  # YYYY-MM
                symbol = txn.get('symbol', '')
                amount = txn.get('amount', 0)
                if date_str and symbol:
                    symbol_monthly[symbol][date_str] += amount
        
        if not symbol_monthly:
            return
        
        # Get current month leaders
        all_months = set()
        for sym_data in symbol_monthly.values():
            all_months.update(sym_data.keys())
        
        if not all_months:
            return
        
        sorted_months = sorted(all_months)
        current_month = sorted_months[-1]
        
        # Calculate current month totals by symbol
        current_totals = {}
        for symbol, monthly_data in symbol_monthly.items():
            total = monthly_data.get(current_month, 0)
            if total > 0:
                current_totals[symbol] = total
        
        if not current_totals:
            return
        
        # Find leader
        current_leader = max(current_totals, key=current_totals.get)
        current_leader_value = current_totals[current_leader]
        
        # Find previous month leader
        if len(sorted_months) >= 2:
            prev_month = sorted_months[-2]
            prev_totals = {}
            for symbol, monthly_data in symbol_monthly.items():
                total = monthly_data.get(prev_month, 0)
                if total > 0:
                    prev_totals[symbol] = total
            
            if prev_totals:
                prev_leader = max(prev_totals, key=prev_totals.get)
                
                if current_leader != prev_leader:
                    self.insights.append(Insight(
                        category=InsightCategory.TREND,
                        sentiment=InsightSentiment.POSITIVE,
                        title=f"{current_leader} Takes the Lead",
                        description=f"{current_leader} has overtaken {prev_leader} as the top options income generator this month with {self._format_currency(current_leader_value)}.",
                        metric_name="symbol_leadership",
                        metric_value=current_leader_value,
                        icon="shuffle",
                        priority=75,
                        tags=["symbols", current_leader, "leadership-change"],
                    ))
    
    def _discover_streak_insights(self, income_service) -> None:
        """Discover insights about consecutive patterns (streaks)."""
        options_data = income_service.get_consolidated_options_income()
        monthly = options_data.get('monthly', {})
        
        if len(monthly) < 3:
            return
        
        sorted_months = sorted(monthly.keys())
        
        # Count consecutive positive months (ending with current month)
        positive_streak = 0
        for month in reversed(sorted_months):
            if monthly[month] > 0:
                positive_streak += 1
            else:
                break
        
        if positive_streak >= 6:
            self.insights.append(Insight(
                category=InsightCategory.STREAK,
                sentiment=InsightSentiment.CELEBRATION,
                title=f"🔥 {positive_streak}-Month Winning Streak!",
                description=f"You've achieved positive options income for {positive_streak} consecutive months. Exceptional consistency!",
                metric_name="positive_streak",
                metric_value=positive_streak,
                icon="flame",
                priority=85,
                tags=["streak", "options", "consistency"],
            ))
        elif positive_streak >= 3:
            self.insights.append(Insight(
                category=InsightCategory.STREAK,
                sentiment=InsightSentiment.POSITIVE,
                title=f"{positive_streak} Months of Positive Income",
                description=f"Options income has been positive for {positive_streak} straight months. Keep the momentum going!",
                metric_name="positive_streak",
                metric_value=positive_streak,
                icon="trending-up",
                priority=60,
                tags=["streak", "options"],
            ))
    
    def _discover_comparison_insights(self, income_service) -> None:
        """Discover year-over-year and period comparisons."""
        options_data = income_service.get_consolidated_options_income()
        monthly = options_data.get('monthly', {})
        
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        # Calculate YTD for current year
        current_ytd = sum(
            monthly.get(f"{current_year}-{m:02d}", 0)
            for m in range(1, current_month + 1)
        )
        
        # Always show YTD total if significant
        if current_ytd > 5000:
            self.insights.append(Insight(
                category=InsightCategory.MILESTONE,
                sentiment=InsightSentiment.POSITIVE,
                title=f"{current_year} Options: {self._format_currency(current_ytd)}",
                description=f"Year-to-date options income has reached {self._format_currency(current_ytd)} across all accounts.",
                metric_name="ytd_options_total",
                metric_value=current_ytd,
                icon="calendar-check",
                priority=55,
                tags=["options", "ytd", str(current_year)],
            ))
        
        if len(monthly) < 13:  # Need at least a year of data for YoY
            return
        
        # Calculate YTD for previous year
        prev_ytd = sum(
            monthly.get(f"{current_year-1}-{m:02d}", 0)
            for m in range(1, current_month + 1)
        )
        
        if prev_ytd > 0:
            pct_change = ((current_ytd - prev_ytd) / prev_ytd) * 100
            
            if pct_change > 25:
                self.insights.append(Insight(
                    category=InsightCategory.COMPARISON,
                    sentiment=InsightSentiment.POSITIVE,
                    title=f"YTD Options Up {pct_change:.0f}%",
                    description=f"Year-to-date options income ({self._format_currency(current_ytd)}) is {pct_change:.0f}% higher than the same period last year ({self._format_currency(prev_ytd)}).",
                    metric_name="ytd_options_yoy",
                    metric_value=current_ytd,
                    comparison_value=prev_ytd,
                    change_percent=pct_change,
                    icon="calendar-check",
                    priority=70,
                    tags=["options", "yearly", "growth"],
                ))
            elif pct_change < -25:
                self.insights.append(Insight(
                    category=InsightCategory.COMPARISON,
                    sentiment=InsightSentiment.NEUTRAL,
                    title=f"YTD Options Down {abs(pct_change):.0f}%",
                    description=f"Year-to-date options income ({self._format_currency(current_ytd)}) is {abs(pct_change):.0f}% lower than last year ({self._format_currency(prev_ytd)}). Market conditions may have changed.",
                    metric_name="ytd_options_yoy",
                    metric_value=current_ytd,
                    comparison_value=prev_ytd,
                    change_percent=pct_change,
                    icon="calendar-x",
                    priority=55,
                    tags=["options", "yearly"],
                ))
    
    def _discover_income_totals(self, income_service) -> None:
        """Discover insights about total income across all categories."""
        summary = income_service.get_income_summary()
        
        total_income = summary.get('total_investment_income', 0)
        options = summary.get('options_income', 0)
        dividends = summary.get('dividend_income', 0)
        interest = summary.get('interest_income', 0)
        
        # Total investment income milestone
        if total_income > 10000:
            self.insights.append(Insight(
                category=InsightCategory.MILESTONE,
                sentiment=InsightSentiment.CELEBRATION,
                title=f"Total Investment Income: {self._format_currency(total_income)}",
                description=f"Your portfolio has generated {self._format_currency(total_income)} in total investment income (options: {self._format_currency(options)}, dividends: {self._format_currency(dividends)}, interest: {self._format_currency(interest)}).",
                metric_name="total_investment_income",
                metric_value=total_income,
                icon="coins",
                priority=65,
                tags=["income", "total", "milestone"],
            ))
        
        # Options as percentage of total
        if total_income > 0 and options > 0:
            options_pct = (options / total_income) * 100
            if options_pct > 70:
                self.insights.append(Insight(
                    category=InsightCategory.TREND,
                    sentiment=InsightSentiment.NEUTRAL,
                    title=f"Options Dominate Income ({options_pct:.0f}%)",
                    description=f"Options trading accounts for {options_pct:.0f}% of your investment income. Consider diversifying income sources.",
                    metric_name="options_income_concentration",
                    metric_value=options_pct,
                    icon="pie-chart",
                    priority=45,
                    tags=["options", "concentration"],
                ))
        
        # Dividend growth potential
        if dividends > 1000:
            self.insights.append(Insight(
                category=InsightCategory.TREND,
                sentiment=InsightSentiment.POSITIVE,
                title=f"Dividend Income: {self._format_currency(dividends)}",
                description=f"Your portfolio is generating {self._format_currency(dividends)} in passive dividend income from your stock holdings.",
                metric_name="dividend_total",
                metric_value=dividends,
                icon="coins",
                priority=48,
                tags=["dividends", "passive-income"],
            ))
        
        # Interest income
        if interest > 1000:
            self.insights.append(Insight(
                category=InsightCategory.TREND,
                sentiment=InsightSentiment.POSITIVE,
                title=f"Interest Income: {self._format_currency(interest)}",
                description=f"Cash holdings and sweep accounts have generated {self._format_currency(interest)} in interest income.",
                metric_name="interest_total",
                metric_value=interest,
                icon="landmark",
                priority=42,
                tags=["interest", "cash"],
            ))
    
    def _discover_top_performers(self, income_service) -> None:
        """Discover insights about top performing symbols."""
        options_data = income_service.get_consolidated_options_income()
        transactions = options_data.get('transactions', [])
        
        if len(transactions) < 5:
            return
        
        # Calculate total income by symbol (all time)
        symbol_totals: Dict[str, float] = defaultdict(float)
        
        for txn in transactions:
            if txn.get('trans_code') in ('STO', 'BTC', 'OEXP', 'OASGN'):
                symbol = txn.get('symbol', '')
                amount = txn.get('amount', 0)
                if symbol and amount > 0:
                    symbol_totals[symbol] += amount
        
        if not symbol_totals:
            return
        
        # Sort by total income
        sorted_symbols = sorted(symbol_totals.items(), key=lambda x: x[1], reverse=True)
        
        # Top performer insight
        if sorted_symbols:
            top_symbol, top_amount = sorted_symbols[0]
            if top_amount > 5000:
                self.insights.append(Insight(
                    category=InsightCategory.TREND,
                    sentiment=InsightSentiment.POSITIVE,
                    title=f"{top_symbol}: Top Options Earner",
                    description=f"{top_symbol} has generated {self._format_currency(top_amount)} in total options income, making it your most profitable options ticker.",
                    metric_name="top_options_symbol",
                    metric_value=top_amount,
                    icon="trophy",
                    priority=60,
                    tags=["options", top_symbol, "top-performer"],
                ))
        
        # Second place
        if len(sorted_symbols) >= 2:
            second_symbol, second_amount = sorted_symbols[1]
            if second_amount > 3000:
                self.insights.append(Insight(
                    category=InsightCategory.TREND,
                    sentiment=InsightSentiment.POSITIVE,
                    title=f"{second_symbol}: Strong Options Performer",
                    description=f"{second_symbol} is your second-highest options income generator with {self._format_currency(second_amount)} total.",
                    metric_name="second_options_symbol",
                    metric_value=second_amount,
                    icon="medal",
                    priority=52,
                    tags=["options", second_symbol],
                ))
        
        # Number of active symbols
        active_symbols = len([s for s, v in symbol_totals.items() if v > 100])
        if active_symbols >= 5:
            self.insights.append(Insight(
                category=InsightCategory.TREND,
                sentiment=InsightSentiment.POSITIVE,
                title=f"Diversified: {active_symbols} Active Tickers",
                description=f"You're generating options income from {active_symbols} different stocks, showing good diversification in your options strategy.",
                metric_name="options_ticker_count",
                metric_value=active_symbols,
                icon="grid-3x3",
                priority=44,
                tags=["options", "diversification"],
            ))
    
    def _discover_monthly_insights(self, income_service) -> None:
        """Discover insights about monthly performance."""
        options_data = income_service.get_consolidated_options_income()
        monthly = options_data.get('monthly', {})
        
        if len(monthly) < 2:
            return
        
        sorted_months = sorted(monthly.keys())
        current_month = sorted_months[-1]
        current_value = monthly[current_month]
        
        # Get all positive values for average calculation
        positive_values = [v for v in monthly.values() if v > 0]
        
        if len(positive_values) >= 3:
            avg_monthly = statistics.mean(positive_values)
            
            # Above average month
            if current_value > avg_monthly * 1.2:
                pct_above = ((current_value - avg_monthly) / avg_monthly) * 100
                self.insights.append(Insight(
                    category=InsightCategory.COMPARISON,
                    sentiment=InsightSentiment.POSITIVE,
                    title=f"{pct_above:.0f}% Above Average This Month",
                    description=f"{self._get_month_name(current_month)} options income of {self._format_currency(current_value)} is {pct_above:.0f}% above your historical average of {self._format_currency(avg_monthly)}.",
                    metric_name="monthly_vs_average",
                    metric_value=current_value,
                    comparison_value=avg_monthly,
                    change_percent=pct_above,
                    icon="trending-up",
                    priority=58,
                    tags=["monthly", "above-average"],
                ))
            
            # Show average for context
            self.insights.append(Insight(
                category=InsightCategory.COMPARISON,
                sentiment=InsightSentiment.NEUTRAL,
                title=f"Monthly Average: {self._format_currency(avg_monthly)}",
                description=f"Your average monthly options income is {self._format_currency(avg_monthly)} based on {len(positive_values)} months of data.",
                metric_name="monthly_average",
                metric_value=avg_monthly,
                icon="calculator",
                priority=38,
                tags=["monthly", "average"],
            ))
        
        # Best month ever (if not current month)
        best_month = max(monthly.keys(), key=lambda k: monthly[k])
        if best_month != current_month and monthly[best_month] > 0:
            self.insights.append(Insight(
                category=InsightCategory.RECORD,
                sentiment=InsightSentiment.NEUTRAL,
                title=f"Best Month: {self._get_month_name(best_month)}",
                description=f"Your highest options income month was {self._get_month_name(best_month)} with {self._format_currency(monthly[best_month])}.",
                metric_name="best_month_ever",
                metric_value=monthly[best_month],
                icon="trophy",
                priority=46,
                tags=["monthly", "record"],
            ))


def get_daily_insights(db: Session, limit: int = 5) -> List[Dict]:
    """
    Get the daily insights for the dashboard.
    This is the main entry point for the insights API.
    Excludes archived insights.
    """
    engine = InsightsEngine(db)
    return engine.discover_all_insights(include_archived=False, limit=limit)


def get_insights_with_archive(db: Session) -> Dict:
    """
    Get all insights split by active/archived status.
    Returns a dict with 'active' and 'archived' lists.
    """
    engine = InsightsEngine(db)
    active, archived = engine.get_all_insights_with_status()
    return {
        "active": active,
        "archived": archived,
        "active_count": len(active),
        "archived_count": len(archived),
    }

