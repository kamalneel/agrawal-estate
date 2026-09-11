"""
BBD Performance Service - Computes Assumptions vs Reality metrics.

Compares actual portfolio growth and options yield against the BBD assumptions:
- Portfolio grows at 8%/year
- Options selling earns 1%/month (12%/year)

Metrics are cached in bbd_performance_metrics table for fast retrieval.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
from sqlalchemy import func, extract, and_
from sqlalchemy.orm import Session

from app.modules.strategies.models import BbdPerformanceMetric, MarginMonthlyBalance, BbdSettings
from app.modules.investments.models import InvestmentTransaction, InvestmentAccount, PortfolioSnapshot
from app.modules.spending.models import SpendingTransaction
from app.modules.income.models import RentalMonthlyIncome, W2Record, SalaryProjection


class BbdPerformanceService:
    # Fallback defaults (used if DB row is missing)
    ASSUMED_ANNUAL_GROWTH = Decimal('0.08')
    ASSUMED_COMBINED_RETURN = Decimal('0.16')
    ASSUMED_MONTHLY_YIELD = Decimal('0.01')
    ASSUMED_ANNUAL_MARGIN_RATE = Decimal('0.05')
    MARGIN_LTV = 0.70
    DATA_CUTOFF_DATE = date(2025, 1, 1)
    EXTERNAL_FLOW_TYPES = ['CASH_MOVEMENT', 'ACATI', 'ACATO', 'INTERNAL_TRANSFER', 'TRANSFER']
    BROKERAGE_ACCOUNTS = ['neel_brokerage', 'jaya_brokerage']

    def __init__(self, db: Session):
        self.db = db
        self._load_settings()

    def _load_settings(self):
        """Load configurable BBD assumptions from DB, falling back to class defaults."""
        try:
            row = self.db.query(BbdSettings).filter(BbdSettings.id == 1).first()
            if row:
                self.ASSUMED_ANNUAL_GROWTH = Decimal(str(row.assumed_annual_growth))
                self.ASSUMED_COMBINED_RETURN = Decimal(str(row.assumed_combined_return))
                self.ASSUMED_MONTHLY_YIELD = Decimal(str(row.assumed_monthly_yield))
                self.ASSUMED_ANNUAL_MARGIN_RATE = Decimal(str(row.assumed_annual_margin_rate))
                self.MARGIN_LTV = float(row.margin_ltv)
        except Exception:
            self.db.rollback()  # Reset session so subsequent queries aren't poisoned

    # ── Public API ────────────────────────────────────────────────

    def compute_all(self, force: bool = False) -> int:
        """Compute missing metrics for all period/metric combos. Returns count of rows upserted."""
        # Delete metrics before cutoff date
        self.db.query(BbdPerformanceMetric).filter(
            BbdPerformanceMetric.period_start < self.DATA_CUTOFF_DATE,
        ).delete()
        self.db.flush()

        count = 0
        for metric_type in ('portfolio_growth', 'pure_growth', 'options_yield', 'margin_borrowing'):
            period_types = ('year', 'month') if metric_type == 'margin_borrowing' else ('year', 'month', 'week')
            for period_type in period_types:
                count += self._compute_metric(metric_type, period_type, force)
        return count

    def get_metrics(
        self,
        metric_type: str,
        period_type: str = 'year',
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch cached metrics from DB, filtered for drill-down."""
        q = self.db.query(BbdPerformanceMetric).filter(
            BbdPerformanceMetric.metric_type == metric_type,
            BbdPerformanceMetric.period_type == period_type,
        )
        if year:
            q = q.filter(extract('year', BbdPerformanceMetric.period_start) == year)
        if month:
            q = q.filter(extract('month', BbdPerformanceMetric.period_start) == month)
        q = q.order_by(BbdPerformanceMetric.period_start)
        return [self._row_to_dict(r) for r in q.all()]

    def get_summary(self) -> Dict[str, Any]:
        """Summary cards: Growth & Earnings — each with both % and $ amount.

        Growth cumulative/average are derived from yearly metrics (each year
        uses a consistent same-store account set internally), chained together.
        This avoids the problem of compounding monthly rates with different
        account sets, and avoids first-to-last pairing missing transferred accounts.
        """
        yearly_growth = self.get_metrics('portfolio_growth', 'year')
        yearly_pure_growth = self.get_metrics('pure_growth', 'year')
        monthly_pure_growth = self.get_metrics('pure_growth', 'month')
        monthly_earnings = self.get_metrics('options_yield', 'month')
        yearly_earnings = self.get_metrics('options_yield', 'year')

        valid_earn = [m for m in monthly_earnings if m.get('actual_value') is not None]

        # ── Growth: chain yearly returns ──
        # Each yearly metric uses same-store pairing (Jan→Dec or Jan→latest)
        # with a consistent set of accounts. Chaining yearly returns is valid
        # because each year's % is self-consistent.
        cumulative_growth_pct = None
        cumulative_growth_amt = None
        avg_monthly_growth_pct = None
        avg_monthly_growth_amt = None

        valid_yearly = [m for m in yearly_growth if m.get('actual_percent') is not None]
        if valid_yearly:
            compound = 1.0
            total_dollar_change = 0.0
            total_months = 0
            for m in valid_yearly:
                compound *= (1 + m['actual_percent'] / 100)
                if m.get('actual_value') is not None and m.get('baseline_value') is not None:
                    total_dollar_change += (m['actual_value'] - m['baseline_value'])
                # Count months in this year's period
                ps = date.fromisoformat(m['period_start'])
                pe = date.fromisoformat(m['period_end'])
                actual_end = min(pe, date.today())
                months_in_period = max(1, (actual_end.year - ps.year) * 12 + actual_end.month - ps.month)
                total_months += months_in_period

            cumulative_growth_pct = round((compound - 1) * 100, 2)
            cumulative_growth_amt = round(total_dollar_change, 2)
            if total_months > 0:
                avg_monthly_growth_pct = round(cumulative_growth_pct / total_months, 4)
                avg_monthly_growth_amt = round(total_dollar_change / total_months, 2)

        # ── Pure Growth (market appreciation only) ──
        valid_pure_monthly = [m for m in monthly_pure_growth if m.get('actual_percent') is not None]
        valid_pure_yearly = [m for m in yearly_pure_growth if m.get('actual_percent') is not None]

        cumulative_pure_growth_pct = None
        cumulative_pure_growth_amt = None
        avg_monthly_pure_growth_pct = None
        avg_monthly_pure_growth_amt = None

        if valid_pure_yearly:
            compound = 1.0
            total_dollar_change = 0.0
            total_months = 0
            for m in valid_pure_yearly:
                compound *= (1 + m['actual_percent'] / 100)
                if m.get('actual_value') is not None and m.get('baseline_value') is not None:
                    total_dollar_change += (m['actual_value'] - m['baseline_value'])
                ps = date.fromisoformat(m['period_start'])
                pe = date.fromisoformat(m['period_end'])
                actual_end = min(pe, date.today())
                months_in_period = max(1, (actual_end.year - ps.year) * 12 + actual_end.month - ps.month)
                total_months += months_in_period
            cumulative_pure_growth_pct = round((compound - 1) * 100, 2)
            cumulative_pure_growth_amt = round(total_dollar_change, 2)
            if total_months > 0:
                avg_monthly_pure_growth_pct = round(cumulative_pure_growth_pct / total_months, 4)
                avg_monthly_pure_growth_amt = round(total_dollar_change / total_months, 2)

        annual_pure_growth = {}
        for m in yearly_pure_growth:
            dollar_change = round(m['actual_value'] - m['baseline_value'], 2) if m.get('actual_value') is not None and m.get('baseline_value') is not None else None
            annual_pure_growth[m['period_label']] = {
                'percent': m['actual_percent'],
                'amount': dollar_change,
                'baseline': m.get('baseline_value'),
            }

        # ── Average Monthly Earnings (% and $) ──
        avg_monthly_earnings_pct = round(
            sum(m['actual_percent'] for m in valid_earn) / len(valid_earn), 4
        ) if valid_earn else None
        avg_monthly_earnings_amt = round(
            sum(m['actual_value'] for m in valid_earn) / len(valid_earn), 2
        ) if valid_earn else None

        # ── Cumulative Earnings (% and $) ──
        cumulative_earnings_amt = round(
            sum(m['actual_value'] for m in valid_earn), 2
        ) if valid_earn else None
        cumulative_earnings_pct = None
        if valid_earn:
            total_income = sum(m['actual_value'] for m in valid_earn)
            avg_baseline = sum(m['baseline_value'] for m in valid_earn if m.get('baseline_value')) / len(valid_earn)
            if avg_baseline > 0:
                cumulative_earnings_pct = round((total_income / avg_baseline) * 100, 2)

        # ── Annual Growth (% and $) by year ──
        annual_growth = {}
        for m in yearly_growth:
            dollar_change = round(m['actual_value'] - m['baseline_value'], 2) if m.get('actual_value') is not None and m.get('baseline_value') is not None else None
            annual_growth[m['period_label']] = {
                'percent': m['actual_percent'],
                'amount': dollar_change,
                'baseline': m.get('baseline_value'),
            }

        # ── Annual Earnings (% and $) by year ──
        annual_earnings = {}
        for m in yearly_earnings:
            annual_earnings[m['period_label']] = {
                'percent': m['actual_percent'],
                'amount': m['actual_value'],
                'baseline': m.get('baseline_value'),
            }

        # ── Borrowing summary ──
        monthly_spending = self._get_monthly_spending()
        spend_values = list(monthly_spending.values())
        avg_monthly_borrowing_amt = round(sum(spend_values) / len(spend_values), 2) if spend_values else None

        # Annual spending totals
        annual_spending: Dict[str, float] = {}
        for month_key, amount in monthly_spending.items():
            yr = month_key[:4]
            annual_spending[yr] = annual_spending.get(yr, 0) + amount

        # Latest margin balance and utilization from most recent monthly metric
        latest_margin = self.db.query(BbdPerformanceMetric).filter(
            BbdPerformanceMetric.metric_type == 'margin_borrowing',
            BbdPerformanceMetric.period_type == 'month',
        ).order_by(BbdPerformanceMetric.period_start.desc()).first()

        current_margin_balance = float(latest_margin.actual_value) if latest_margin and latest_margin.actual_value else None
        current_margin_utilization_pct = float(latest_margin.actual_percent) if latest_margin and latest_margin.actual_percent else None
        margin_available = float(latest_margin.baseline_value) if latest_margin and latest_margin.baseline_value else None

        # Total interest accrued = cumulative_margin - sum of all spending
        total_interest_accrued = None
        if current_margin_balance is not None and spend_values:
            total_spent = sum(spend_values)
            total_interest_accrued = round(max(0.0, current_margin_balance - total_spent), 2)

        # Annual borrowing from yearly metrics
        yearly_borrowing = self.get_metrics('margin_borrowing', 'year')
        annual_borrowing = {}
        for m in yearly_borrowing:
            annual_borrowing[m['period_label']] = {
                'cumulative_margin': m['actual_value'],
                'utilization_pct': m['actual_percent'],
                'portfolio_value': m.get('baseline_value'),
            }

        return {
            # Combined: growth + income
            'avg_monthly_growth_pct': avg_monthly_growth_pct,
            'avg_monthly_growth_amt': avg_monthly_growth_amt,
            'cumulative_growth_pct': cumulative_growth_pct,
            'cumulative_growth_amt': cumulative_growth_amt,
            'annual_growth': annual_growth,
            'expected_monthly_growth_pct': round(((1 + float(self.ASSUMED_COMBINED_RETURN)) ** (1/12) - 1) * 100, 4),
            'expected_annual_growth_pct': float(self.ASSUMED_COMBINED_RETURN) * 100,
            # Pure market growth (options income stripped out)
            'avg_monthly_pure_growth_pct': avg_monthly_pure_growth_pct,
            'avg_monthly_pure_growth_amt': avg_monthly_pure_growth_amt,
            'cumulative_pure_growth_pct': cumulative_pure_growth_pct,
            'cumulative_pure_growth_amt': cumulative_pure_growth_amt,
            'annual_pure_growth': annual_pure_growth,
            'expected_monthly_pure_growth_pct': round(((1 + float(self.ASSUMED_ANNUAL_GROWTH)) ** (1/12) - 1) * 100, 4),
            'expected_annual_pure_growth_pct': float(self.ASSUMED_ANNUAL_GROWTH) * 100,
            # Options income only
            'avg_monthly_earnings_pct': avg_monthly_earnings_pct,
            'avg_monthly_earnings_amt': avg_monthly_earnings_amt,
            'cumulative_earnings_pct': cumulative_earnings_pct,
            'cumulative_earnings_amt': cumulative_earnings_amt,
            'annual_earnings': annual_earnings,
            'expected_monthly_earnings_pct': 1.0,
            'expected_annual_earnings_pct': 12.0,
            # Borrowing
            'margin_available': margin_available,
            'current_margin_balance': current_margin_balance,
            'current_margin_utilization_pct': current_margin_utilization_pct,
            'total_interest_accrued': total_interest_accrued,
            'avg_monthly_borrowing_amt': avg_monthly_borrowing_amt,
            'annual_spending': {yr: round(amt, 2) for yr, amt in annual_spending.items()},
            'annual_borrowing': annual_borrowing,
            'assumed_margin_rate_pct': 5.0,
        }

    # ── Core computation ──────────────────────────────────────────

    def _compute_metric(self, metric_type: str, period_type: str, force: bool) -> int:
        """Compute metrics for one metric_type + period_type combo."""
        if metric_type == 'portfolio_growth':
            return self._compute_portfolio_growth(period_type, force)
        elif metric_type == 'pure_growth':
            return self._compute_pure_growth(period_type, force)
        elif metric_type == 'options_yield':
            return self._compute_options_yield(period_type, force)
        elif metric_type == 'margin_borrowing':
            return self._compute_borrowing_metrics(period_type, force)
        return 0

    # ── Portfolio Growth ──────────────────────────────────────────

    def _compute_portfolio_growth(self, period_type: str, force: bool) -> int:
        """Compute portfolio growth metrics using same-store account pairing."""
        account_months = {
            k: v for k, v in self._get_account_month_values().items()
            if any(k.startswith(acct) for acct in self.BROKERAGE_ACCOUNTS)
        }
        all_months = set()
        for acct_data in account_months.values():
            all_months.update(acct_data.keys())

        if len(all_months) < 2:
            return 0

        if period_type == 'year':
            return self._compute_portfolio_growth_yearly(account_months, sorted(all_months), force)
        elif period_type == 'month':
            return self._compute_portfolio_growth_monthly(account_months, sorted(all_months), force)
        elif period_type == 'week':
            return self._compute_portfolio_growth_weekly(account_months, sorted(all_months), force)
        return 0

    def _paired_sum(self, account_months: Dict[str, Dict[str, float]], month_a: str, month_b: str) -> tuple:
        """Sum portfolio values for accounts present in BOTH months.
        Returns (sum_a, sum_b, paired_account_ids) where paired_account_ids is
        the set of raw account_ids (without source suffix) in the paired set."""
        val_a = 0.0
        val_b = 0.0
        paired_account_ids: set = set()
        for acct_key, acct_data in account_months.items():
            if month_a in acct_data and month_b in acct_data:
                val_a += acct_data[month_a]
                val_b += acct_data[month_b]
                # Key format: {account_id}_{source} — extract account_id
                account_id = acct_key.rsplit('_', 1)[0]
                paired_account_ids.add(account_id)
        return val_a, val_b, paired_account_ids

    def _compute_portfolio_growth_yearly(self, account_months: Dict[str, Dict[str, float]], sorted_months: List[str], force: bool) -> int:
        """Yearly growth using same-store pairing between start and end of year."""
        today = date.today()
        count = 0

        years_with_data = {}
        for m in sorted_months:
            yr = int(m[:4])
            years_with_data.setdefault(yr, []).append(m)

        for yr, year_months in sorted(years_with_data.items()):
            if len(year_months) < 2:
                continue

            # Baseline month: prefer Jan of this year (avoids cross-year account
            # composition changes), fall back to Dec prior year, then earliest month
            jan_key = f"{yr}-01"
            dec_key = f"{yr - 1}-12"
            if jan_key in set(sorted_months):
                baseline_month = jan_key
            elif dec_key in set(sorted_months):
                baseline_month = dec_key
            else:
                baseline_month = year_months[0]

            actual_month = year_months[-1]

            # Same-store: only accounts present in both baseline and actual months
            baseline_val, actual_val, paired_ids = self._paired_sum(account_months, baseline_month, actual_month)

            if baseline_val < 10000:
                continue

            period_start = date(yr, 1, 1)
            period_end = date(yr, 12, 31)
            completeness = 'partial' if yr == today.year else 'complete'

            # Modified Dietz: adjust for external cash flows from paired accounts only
            flows = self._get_external_cash_flows_for_period(period_start, period_end)
            flows = [f for f in flows if f['account_id'] in paired_ids]
            actual_pct = self._modified_dietz_return(baseline_val, actual_val, flows, period_start, period_end)
            expected_pct = float(self.ASSUMED_COMBINED_RETURN) * 100
            expected_val = baseline_val * (1 + float(self.ASSUMED_COMBINED_RETURN))

            self._upsert_metric(
                period_type='year', period_start=period_start, period_end=period_end,
                metric_type='portfolio_growth',
                actual_value=actual_val, actual_percent=actual_pct,
                expected_value=expected_val, expected_percent=expected_pct,
                baseline_value=baseline_val,
                data_completeness=completeness, force=force,
            )
            count += 1
        return count

    def _compute_portfolio_growth_monthly(self, account_months: Dict[str, Dict[str, float]], sorted_months: List[str], force: bool) -> int:
        """Monthly growth: same-store comparison to prior month with Modified Dietz adjustment."""
        today = date.today()
        monthly_rate = ((1 + float(self.ASSUMED_COMBINED_RETURN)) ** (1/12) - 1) * 100
        count = 0

        for i in range(1, len(sorted_months)):
            prev_key = sorted_months[i - 1]
            cur_key = sorted_months[i]

            # Skip if gap > 2 months
            prev_yr, prev_mo = int(prev_key[:4]), int(prev_key[5:7])
            cur_yr, cur_mo = int(cur_key[:4]), int(cur_key[5:7])
            month_gap = (cur_yr - prev_yr) * 12 + (cur_mo - prev_mo)
            if month_gap > 2:
                continue

            baseline_val, actual_val, paired_ids = self._paired_sum(account_months, prev_key, cur_key)
            if baseline_val < 10000:
                continue

            yr, mo = cur_yr, cur_mo
            period_start = date(yr, mo, 1)
            if mo == 12:
                period_end = date(yr, 12, 31)
            else:
                period_end = date(yr, mo + 1, 1) - timedelta(days=1)

            completeness = 'partial' if (yr == today.year and mo == today.month) else 'complete'

            # Modified Dietz: adjust for external cash flows from paired accounts only
            flows = self._get_external_cash_flows_for_period(period_start, period_end)
            flows = [f for f in flows if f['account_id'] in paired_ids]
            actual_pct = self._modified_dietz_return(baseline_val, actual_val, flows, period_start, period_end)
            expected_val = baseline_val * (1 + monthly_rate / 100)

            self._upsert_metric(
                period_type='month', period_start=period_start, period_end=period_end,
                metric_type='portfolio_growth',
                actual_value=actual_val, actual_percent=actual_pct,
                expected_value=expected_val, expected_percent=monthly_rate,
                baseline_value=baseline_val,
                data_completeness=completeness, force=force,
            )
            count += 1
        return count

    def _compute_portfolio_growth_weekly(self, account_months: Dict[str, Dict[str, float]], sorted_months: List[str], force: bool) -> int:
        """Weekly growth: interpolate paired monthly snapshots to daily values."""
        if len(sorted_months) < 2:
            return 0

        # Build paired monthly totals for each consecutive month pair
        paired_snapshots: Dict[str, float] = {}
        for i in range(len(sorted_months)):
            if i == 0:
                total = sum(d.get(sorted_months[0], 0) for d in account_months.values())
            else:
                _, total, _ = self._paired_sum(account_months, sorted_months[i - 1], sorted_months[i])
            if total > 10000:
                paired_snapshots[sorted_months[i]] = total

        today = date.today()
        weekly_rate = ((1 + float(self.ASSUMED_COMBINED_RETURN)) ** (7/365) - 1) * 100
        count = 0

        daily_values = self._interpolate_daily(paired_snapshots)
        if not daily_values:
            return 0

        sorted_days = sorted(daily_values.keys())
        first_day = sorted_days[0]
        last_day = sorted_days[-1]

        current = first_day - timedelta(days=first_day.weekday())
        if current < first_day:
            current += timedelta(days=7)

        while current + timedelta(days=6) <= last_day:
            week_start = current
            week_end = current + timedelta(days=6)

            baseline_val = daily_values.get(week_start) or self._nearest_value(daily_values, week_start)
            actual_val = daily_values.get(week_end) or self._nearest_value(daily_values, week_end)

            if baseline_val and actual_val and baseline_val > 0:
                actual_pct = ((actual_val / baseline_val) - 1) * 100
                expected_val = baseline_val * (1 + weekly_rate / 100)
                completeness = 'interpolated'
                if week_end >= today:
                    completeness = 'partial'

                self._upsert_metric(
                    period_type='week', period_start=week_start, period_end=week_end,
                    metric_type='portfolio_growth',
                    actual_value=actual_val, actual_percent=actual_pct,
                    expected_value=expected_val, expected_percent=weekly_rate,
                    baseline_value=baseline_val,
                    data_completeness=completeness, force=force,
                )
                count += 1

            current += timedelta(days=7)
        return count

    # ── Pure Market Growth (portfolio growth minus options income) ────

    def _compute_pure_growth(self, period_type: str, force: bool) -> int:
        """Pure market growth = portfolio return with options income stripped out.
        Uses Modified Dietz but adds options income as a synthetic external inflow,
        so the return reflects only market appreciation."""
        account_months = {
            k: v for k, v in self._get_account_month_values().items()
            if any(k.startswith(acct) for acct in self.BROKERAGE_ACCOUNTS)
        }
        all_months = set()
        for acct_data in account_months.values():
            all_months.update(acct_data.keys())
        sorted_months = sorted(all_months)

        if len(sorted_months) < 2:
            return 0

        monthly_options = self._get_options_income_monthly()

        if period_type == 'year':
            return self._compute_pure_growth_yearly(account_months, sorted_months, monthly_options, force)
        elif period_type == 'month':
            return self._compute_pure_growth_monthly(account_months, sorted_months, monthly_options, force)
        elif period_type == 'week':
            return self._compute_portfolio_growth_weekly(account_months, sorted_months, force)
        return 0

    def _compute_pure_growth_yearly(
        self,
        account_months: Dict[str, Dict[str, float]],
        sorted_months: List[str],
        monthly_options: Dict[str, float],
        force: bool,
    ) -> int:
        today = date.today()
        count = 0

        years_with_data: Dict[int, List[str]] = {}
        for m in sorted_months:
            years_with_data.setdefault(int(m[:4]), []).append(m)

        for yr, year_months in sorted(years_with_data.items()):
            if len(year_months) < 2:
                continue

            jan_key = f"{yr}-01"
            dec_key = f"{yr - 1}-12"
            if jan_key in set(sorted_months):
                baseline_month = jan_key
            elif dec_key in set(sorted_months):
                baseline_month = dec_key
            else:
                baseline_month = year_months[0]

            actual_month = year_months[-1]
            baseline_val, actual_val, paired_ids = self._paired_sum(account_months, baseline_month, actual_month)
            if baseline_val < 10000:
                continue

            period_start = date(yr, 1, 1)
            period_end = date(yr, 12, 31)
            completeness = 'partial' if yr == today.year else 'complete'

            flows = self._get_external_cash_flows_for_period(period_start, period_end)
            flows = [f for f in flows if f['account_id'] in paired_ids]

            # Treat options income as external inflow so Modified Dietz strips it from market return
            for m in year_months:
                income = monthly_options.get(m, 0)
                if income > 0:
                    m_yr, m_mo = int(m[:4]), int(m[5:7])
                    flows.append({'account_id': '_options', 'date': date(m_yr, m_mo, 15), 'amount': income})

            actual_pct = self._modified_dietz_return(baseline_val, actual_val, flows, period_start, period_end)
            expected_pct = float(self.ASSUMED_ANNUAL_GROWTH) * 100
            expected_val = baseline_val * (1 + float(self.ASSUMED_ANNUAL_GROWTH))

            self._upsert_metric(
                period_type='year', period_start=period_start, period_end=period_end,
                metric_type='pure_growth',
                actual_value=actual_val, actual_percent=actual_pct,
                expected_value=expected_val, expected_percent=expected_pct,
                baseline_value=baseline_val,
                data_completeness=completeness, force=force,
            )
            count += 1
        return count

    def _compute_pure_growth_monthly(
        self,
        account_months: Dict[str, Dict[str, float]],
        sorted_months: List[str],
        monthly_options: Dict[str, float],
        force: bool,
    ) -> int:
        today = date.today()
        monthly_rate = ((1 + float(self.ASSUMED_ANNUAL_GROWTH)) ** (1/12) - 1) * 100
        count = 0

        for i in range(1, len(sorted_months)):
            prev_key = sorted_months[i - 1]
            cur_key = sorted_months[i]

            prev_yr, prev_mo = int(prev_key[:4]), int(prev_key[5:7])
            cur_yr, cur_mo = int(cur_key[:4]), int(cur_key[5:7])
            month_gap = (cur_yr - prev_yr) * 12 + (cur_mo - prev_mo)
            if month_gap > 2:
                continue

            baseline_val, actual_val, paired_ids = self._paired_sum(account_months, prev_key, cur_key)
            if baseline_val < 10000:
                continue

            yr, mo = cur_yr, cur_mo
            period_start = date(yr, mo, 1)
            period_end = date(yr, mo + 1, 1) - timedelta(days=1) if mo < 12 else date(yr, 12, 31)
            completeness = 'partial' if (yr == today.year and mo == today.month) else 'complete'

            flows = self._get_external_cash_flows_for_period(period_start, period_end)
            flows = [f for f in flows if f['account_id'] in paired_ids]

            income = monthly_options.get(cur_key, 0)
            if income > 0:
                flows.append({'account_id': '_options', 'date': date(yr, mo, 15), 'amount': income})

            actual_pct = self._modified_dietz_return(baseline_val, actual_val, flows, period_start, period_end)
            expected_val = baseline_val * (1 + monthly_rate / 100)

            self._upsert_metric(
                period_type='month', period_start=period_start, period_end=period_end,
                metric_type='pure_growth',
                actual_value=actual_val, actual_percent=actual_pct,
                expected_value=expected_val, expected_percent=monthly_rate,
                baseline_value=baseline_val,
                data_completeness=completeness, force=force,
            )
            count += 1
        return count

    # ── Options Yield ─────────────────────────────────────────────

    def _compute_options_yield(self, period_type: str, force: bool) -> int:
        """Compute options yield metrics using same-store portfolio baselines."""
        account_months = {
            k: v for k, v in self._get_account_month_values().items()
            if any(k.startswith(acct) for acct in self.BROKERAGE_ACCOUNTS)
        }
        all_months = set()
        for acct_data in account_months.values():
            all_months.update(acct_data.keys())
        sorted_months = sorted(all_months)

        if period_type == 'year':
            return self._compute_options_yield_yearly(account_months, sorted_months, force)
        elif period_type == 'month':
            return self._compute_options_yield_monthly(account_months, sorted_months, force)
        elif period_type == 'week':
            return self._compute_options_yield_weekly(account_months, sorted_months, force)
        return 0

    def _compute_options_yield_yearly(self, account_months: Dict[str, Dict[str, float]], sorted_months: List[str], force: bool) -> int:
        """Yearly options yield: total options income / same-store portfolio value."""
        monthly_income = self._get_options_income_monthly()
        if not monthly_income:
            return 0

        today = date.today()
        yearly_income: Dict[int, float] = {}
        for month_key, amount in monthly_income.items():
            yr = int(month_key[:4])
            yearly_income[yr] = yearly_income.get(yr, 0) + amount

        years_with_data = {}
        for m in sorted_months:
            yr = int(m[:4])
            years_with_data.setdefault(yr, []).append(m)

        count = 0
        for yr, income in sorted(yearly_income.items()):
            year_months = years_with_data.get(yr, [])
            if not year_months:
                continue

            # Baseline: Jan of this year (paired with Dec prior or earliest)
            jan_key = f"{yr}-01"
            dec_key = f"{yr - 1}-12"
            baseline_month = jan_key if jan_key in set(sorted_months) else (dec_key if dec_key in set(sorted_months) else year_months[0])
            end_month = year_months[-1]

            baseline_val, _, _ = self._paired_sum(account_months, baseline_month, end_month)
            if baseline_val < 10000:
                # Fallback: just use sum of all accounts in baseline month
                baseline_val = sum(d.get(baseline_month, 0) for d in account_months.values())
            if baseline_val < 10000:
                continue

            period_start = date(yr, 1, 1)
            period_end = date(yr, 12, 31)
            completeness = 'partial' if yr == today.year else 'complete'

            actual_pct = (income / baseline_val) * 100
            expected_pct = float(self.ASSUMED_MONTHLY_YIELD) * 12 * 100  # 12%
            expected_val = baseline_val * float(self.ASSUMED_MONTHLY_YIELD) * 12

            self._upsert_metric(
                period_type='year', period_start=period_start, period_end=period_end,
                metric_type='options_yield',
                actual_value=income, actual_percent=actual_pct,
                expected_value=expected_val, expected_percent=expected_pct,
                baseline_value=baseline_val,
                data_completeness=completeness, force=force,
            )
            count += 1
        return count

    def _compute_options_yield_monthly(self, account_months: Dict[str, Dict[str, float]], sorted_months: List[str], force: bool) -> int:
        """Monthly options yield: income / same-store portfolio value at start of month.
        Iterates ALL months in the data range (not just months with income) so that
        expected values and baseline capital are always computed."""
        monthly_income = self._get_options_income_monthly()
        if not sorted_months:
            return 0

        today = date.today()
        count = 0
        sorted_months_set = set(sorted_months)

        # Generate complete month range from first month with portfolio data through current month
        first_yr, first_mo = int(sorted_months[0][:4]), int(sorted_months[0][5:7])
        last_yr, last_mo = int(sorted_months[-1][:4]), int(sorted_months[-1][5:7])
        # Extend range to include current month so carry-forward logic can fill gaps
        if (today.year, today.month) > (last_yr, last_mo):
            last_yr, last_mo = today.year, today.month
        all_months = []
        yr, mo = first_yr, first_mo
        while (yr, mo) <= (last_yr, last_mo):
            all_months.append(f"{yr}-{mo:02d}")
            mo += 1
            if mo > 12:
                mo = 1
                yr += 1

        # Pre-compute total portfolio value per month for gap-filling
        monthly_portfolio = {}
        for m in sorted_months:
            monthly_portfolio[m] = sum(acct.get(m, 0) for acct in account_months.values())

        last_known_portfolio = 0

        for month_key in all_months:
            yr, mo = int(month_key[:4]), int(month_key[5:7])

            # Track last known portfolio value for carry-forward
            if month_key in monthly_portfolio:
                last_known_portfolio = monthly_portfolio[month_key]

            # Find prior month key
            if mo == 1:
                prev_key = f"{yr - 1}-12"
            else:
                prev_key = f"{yr}-{mo - 1:02d}"

            # Determine baseline using best available data
            if prev_key in sorted_months_set and month_key in sorted_months_set:
                # Both months have portfolio data — use same-store pairing
                baseline_val, _, _ = self._paired_sum(account_months, prev_key, month_key)
            elif prev_key in monthly_portfolio:
                # Only previous month has data — use its total
                baseline_val = monthly_portfolio[prev_key]
            elif last_known_portfolio > 0:
                # Gap in data — carry forward last known portfolio value
                baseline_val = last_known_portfolio
            else:
                continue

            if baseline_val < 10000:
                continue

            income = monthly_income.get(month_key, 0)

            period_start = date(yr, mo, 1)
            if mo == 12:
                period_end = date(yr, 12, 31)
            else:
                period_end = date(yr, mo + 1, 1) - timedelta(days=1)

            completeness = 'partial' if (yr == today.year and mo == today.month) else 'complete'
            actual_pct = (income / baseline_val) * 100
            expected_pct = float(self.ASSUMED_MONTHLY_YIELD) * 100
            expected_val = baseline_val * float(self.ASSUMED_MONTHLY_YIELD)

            self._upsert_metric(
                period_type='month', period_start=period_start, period_end=period_end,
                metric_type='options_yield',
                actual_value=income, actual_percent=actual_pct,
                expected_value=expected_val, expected_percent=expected_pct,
                baseline_value=baseline_val,
                data_completeness=completeness, force=force,
            )
            count += 1
        return count

    def _compute_options_yield_weekly(self, account_months: Dict[str, Dict[str, float]], sorted_months: List[str], force: bool) -> int:
        """Weekly options yield using interpolated same-store portfolio values."""
        if len(sorted_months) < 2:
            return 0

        # Build paired monthly totals for interpolation
        paired_snapshots: Dict[str, float] = {}
        for i in range(len(sorted_months)):
            if i == 0:
                total = sum(d.get(sorted_months[0], 0) for d in account_months.values())
            else:
                _, total, _ = self._paired_sum(account_months, sorted_months[i - 1], sorted_months[i])
            if total > 10000:
                paired_snapshots[sorted_months[i]] = total

        daily_values = self._interpolate_daily(paired_snapshots)
        if not daily_values:
            return 0

        today = date.today()
        sorted_days = sorted(daily_values.keys())
        first_day = sorted_days[0]
        last_day = sorted_days[-1]
        weekly_yield_pct = float(self.ASSUMED_MONTHLY_YIELD) * 100 * 12 / 52
        count = 0

        current = first_day - timedelta(days=first_day.weekday())
        if current < first_day:
            current += timedelta(days=7)

        while current + timedelta(days=6) <= last_day:
            week_start = current
            week_end = current + timedelta(days=6)

            income = self._get_options_income_for_range(week_start, week_end)
            baseline_val = daily_values.get(week_start) or self._nearest_value(daily_values, week_start)
            if not baseline_val or baseline_val <= 0:
                current += timedelta(days=7)
                continue

            actual_pct = (income / baseline_val) * 100 if income else 0
            expected_val = baseline_val * weekly_yield_pct / 100

            completeness = 'interpolated'
            if week_end >= today:
                completeness = 'partial'

            self._upsert_metric(
                period_type='week', period_start=week_start, period_end=week_end,
                metric_type='options_yield',
                actual_value=income, actual_percent=actual_pct,
                expected_value=expected_val, expected_percent=weekly_yield_pct,
                baseline_value=baseline_val,
                data_completeness=completeness, force=force,
            )
            count += 1
            current += timedelta(days=7)
        return count

    # ── Margin Borrowing ────────────────────────────────────────

    def _compute_borrowing_metrics(self, period_type: str, force: bool) -> int:
        """Compute margin borrowing metrics."""
        if period_type == 'month':
            return self._compute_borrowing_monthly(force)
        elif period_type == 'year':
            return self._compute_borrowing_yearly(force)
        return 0

    def _compute_borrowing_monthly(self, force: bool) -> int:
        """Monthly margin borrowing.
        actual_value: real margin from statements when available, else simulated cumulative spending.
        expected_value: max sustainable BBD withdrawal — portfolio × (growth_rate − margin_rate) / 12
                        compounded at 5%/yr. Borrowing at this rate keeps debt/portfolio ratio stable forever.
        Margin available = 70% of brokerage portfolio value."""
        monthly_spending = self._get_monthly_spending()
        if not monthly_spending:
            return 0

        account_months = self._get_account_month_values()
        brokerage_months = self._get_brokerage_month_values(account_months)
        if not brokerage_months:
            return 0

        real_margin = self._get_real_margin_data()

        all_months = set(monthly_spending.keys()) | set(brokerage_months.keys()) | set(real_margin.keys())
        sorted_months = sorted(all_months)
        if not sorted_months:
            return 0

        monthly_rate = (1 + float(self.ASSUMED_ANNUAL_MARGIN_RATE)) ** (1/12) - 1
        net_annual_spread = float(self.ASSUMED_COMBINED_RETURN - self.ASSUMED_ANNUAL_MARGIN_RATE)
        simulated_margin = 0.0
        expected_cumulative = 0.0
        today = date.today()
        count = 0

        for month_key in sorted_months:
            spending = monthly_spending.get(month_key, 0.0)

            # Keep simulated running total as fallback for months without real data
            if simulated_margin > 0:
                simulated_margin *= (1 + monthly_rate)
            simulated_margin += spending

            portfolio_value = brokerage_months.get(month_key, 0)

            # Expected = max sustainable BBD borrow this month: portfolio × (growth − rate) / 12
            # Borrowing this amount keeps debt/portfolio ratio permanently stable
            sustainable_monthly = portfolio_value * net_annual_spread / 12 if portfolio_value > 0 else 0.0
            if expected_cumulative > 0:
                expected_cumulative *= (1 + monthly_rate)
            expected_cumulative += sustainable_monthly

            if portfolio_value <= 0:
                continue
            margin_available = portfolio_value * self.MARGIN_LTV

            # Use real statement data when available; fall back to simulation
            actual_margin = real_margin[month_key] if month_key in real_margin else max(0.0, simulated_margin)

            actual_pct = (actual_margin / margin_available * 100) if margin_available > 0 else 0
            expected_pct = (expected_cumulative / margin_available * 100) if margin_available > 0 else 0

            yr, mo = int(month_key[:4]), int(month_key[5:7])
            period_start = date(yr, mo, 1)
            if mo == 12:
                period_end = date(yr, 12, 31)
            else:
                period_end = date(yr, mo + 1, 1) - timedelta(days=1)

            completeness = 'partial' if (yr == today.year and mo == today.month) else 'complete'

            self._upsert_metric(
                period_type='month', period_start=period_start, period_end=period_end,
                metric_type='margin_borrowing',
                actual_value=actual_margin, actual_percent=actual_pct,
                expected_value=expected_cumulative, expected_percent=expected_pct,
                baseline_value=margin_available,
                data_completeness=completeness, force=force,
            )
            count += 1
        return count

    def _compute_borrowing_yearly(self, force: bool) -> int:
        """Yearly margin borrowing: snapshot the December (or latest) month's actual margin per year."""
        monthly_spending = self._get_monthly_spending()
        if not monthly_spending:
            return 0

        account_months = self._get_account_month_values()
        brokerage_months = self._get_brokerage_month_values(account_months)
        if not brokerage_months:
            return 0

        real_margin = self._get_real_margin_data()

        all_months = sorted(set(monthly_spending.keys()) | set(brokerage_months.keys()) | set(real_margin.keys()))
        if not all_months:
            return 0

        monthly_rate = (1 + float(self.ASSUMED_ANNUAL_MARGIN_RATE)) ** (1/12) - 1
        net_annual_spread = float(self.ASSUMED_COMBINED_RETURN - self.ASSUMED_ANNUAL_MARGIN_RATE)
        simulated_margin = 0.0
        expected_cumulative = 0.0
        today = date.today()

        year_snapshots: Dict[int, Dict[str, float]] = {}

        for month_key in all_months:
            spending = monthly_spending.get(month_key, 0.0)

            if simulated_margin > 0:
                simulated_margin *= (1 + monthly_rate)
            simulated_margin += spending

            yr = int(month_key[:4])
            portfolio_value = brokerage_months.get(month_key, 0)

            # Expected = max sustainable BBD borrow this month: portfolio × (growth − rate) / 12
            sustainable_monthly = portfolio_value * net_annual_spread / 12 if portfolio_value > 0 else 0.0
            if expected_cumulative > 0:
                expected_cumulative *= (1 + monthly_rate)
            expected_cumulative += sustainable_monthly

            if portfolio_value > 0:
                actual_margin = real_margin[month_key] if month_key in real_margin else max(0.0, simulated_margin)
                year_snapshots[yr] = {
                    'actual_margin': actual_margin,
                    'expected_cumulative': expected_cumulative,
                    'margin_available': portfolio_value * self.MARGIN_LTV,
                }

        count = 0
        for yr, snap in sorted(year_snapshots.items()):
            margin_available = snap['margin_available']
            actual_pct = (snap['actual_margin'] / margin_available * 100) if margin_available > 0 else 0
            expected_pct = (snap['expected_cumulative'] / margin_available * 100) if margin_available > 0 else 0

            period_start = date(yr, 1, 1)
            period_end = date(yr, 12, 31)
            completeness = 'partial' if yr == today.year else 'complete'

            self._upsert_metric(
                period_type='year', period_start=period_start, period_end=period_end,
                metric_type='margin_borrowing',
                actual_value=snap['actual_margin'], actual_percent=actual_pct,
                expected_value=snap['expected_cumulative'], expected_percent=expected_pct,
                baseline_value=margin_available,
                data_completeness=completeness, force=force,
            )
            count += 1
        return count

    # ── Data sources ──────────────────────────────────────────────

    def _get_real_margin_data(self) -> Dict[str, float]:
        """Return total margin borrowed per month from real Robinhood statements.
        Returns {YYYY-MM: margin_borrowed} where margin_borrowed >= 0.
        Nets across all brokerage accounts: if Neel borrows $130K but Jaya has
        $10K cash, the true combined margin is $120K, not $130K."""
        rows = self.db.query(MarginMonthlyBalance).filter(
            MarginMonthlyBalance.account_name.in_(self.BROKERAGE_ACCOUNTS)
        ).all()

        # Sum ALL balances (positive and negative) per month, then clamp to 0
        net_by_month: Dict[str, float] = {}
        for row in rows:
            month_key = f"{row.year}-{row.month:02d}"
            net_by_month[month_key] = net_by_month.get(month_key, 0.0) + float(row.closing_balance or 0)

        result: Dict[str, float] = {k: max(0.0, -v) for k, v in net_by_month.items()}

        # Forward-fill gaps up to the current month using the last known balance
        if result:
            today = date.today()
            last_key = max(result.keys())
            last_val = result[last_key]
            yr, mo = int(last_key[:4]), int(last_key[5:7])
            while True:
                mo += 1
                if mo > 12:
                    mo = 1
                    yr += 1
                fill_key = f"{yr}-{mo:02d}"
                if fill_key > f"{today.year}-{today.month:02d}":
                    break
                if fill_key not in result:
                    result[fill_key] = last_val

        return result

    def _get_brokerage_month_values(self, account_months: Dict[str, Dict[str, float]]) -> Dict[str, float]:
        """Get total brokerage portfolio value per month (neel + jaya brokerage only).
        Returns {YYYY-MM: total_value}."""
        result: Dict[str, float] = {}
        for key, months_data in account_months.items():
            # key format is "account_id_source", check if starts with a brokerage account
            if any(key.startswith(acct) for acct in self.BROKERAGE_ACCOUNTS):
                for month_key, value in months_data.items():
                    result[month_key] = result.get(month_key, 0) + value
        return result

    def _get_monthly_spending(self) -> Dict[str, float]:
        """Monthly spending {YYYY-MM: positive spend}, from the Spending
        page's own definition (spending.services.spending_rows) so this
        model and the page can never disagree. Previously this was a third
        definition — no refund netting, no rulebook — see
        docs/SPENDING-PAGE-AUDIT-2026-09.md D8."""
        from app.modules.spending.services import monthly_spending_totals
        return monthly_spending_totals(self.db, since=self.DATA_CUTOFF_DATE)

    def _get_account_month_values(self) -> Dict[str, Dict[str, float]]:
        """Get per-account, per-month portfolio values.
        Returns {account_id: {YYYY-MM: value}}.
        Uses the portfolio_value at the latest statement_date within each month
        (not max value, which inflates totals by summing peak days across accounts).
        Filtered to DATA_CUTOFF_DATE onwards."""
        # Subquery: find latest statement_date per (account_id, source, month)
        latest_dates = self.db.query(
            PortfolioSnapshot.account_id,
            PortfolioSnapshot.source,
            func.to_char(PortfolioSnapshot.statement_date, 'YYYY-MM').label('month'),
            func.max(PortfolioSnapshot.statement_date).label('max_date'),
        ).filter(
            PortfolioSnapshot.statement_date >= self.DATA_CUTOFF_DATE,
        ).group_by(
            PortfolioSnapshot.account_id,
            PortfolioSnapshot.source,
            func.to_char(PortfolioSnapshot.statement_date, 'YYYY-MM'),
        ).subquery()

        # Main query: get portfolio_value at that latest date
        rows = self.db.query(
            PortfolioSnapshot.account_id,
            PortfolioSnapshot.source,
            latest_dates.c.month,
            PortfolioSnapshot.portfolio_value.label('value'),
        ).join(
            latest_dates,
            and_(
                PortfolioSnapshot.account_id == latest_dates.c.account_id,
                PortfolioSnapshot.source == latest_dates.c.source,
                PortfolioSnapshot.statement_date == latest_dates.c.max_date,
            )
        ).order_by(latest_dates.c.month).all()

        account_months: Dict[str, Dict[str, float]] = {}
        for r in rows:
            key = f"{r.account_id}_{r.source}"
            account_months.setdefault(key, {})[r.month] = float(r.value)
        return account_months

    def _get_paired_portfolio_values(self, month_a: str, month_b: str) -> tuple:
        """Get portfolio totals for two months using only accounts present in BOTH.
        Returns (value_a, value_b) — same set of accounts in both."""
        account_months = self._get_account_month_values()
        val_a = 0.0
        val_b = 0.0
        for acct_data in account_months.values():
            if month_a in acct_data and month_b in acct_data:
                val_a += acct_data[month_a]
                val_b += acct_data[month_b]
        return val_a, val_b

    def _get_monthly_portfolio_values(self) -> Dict[str, float]:
        """Get total portfolio value per month (YYYY-MM → value).
        Sums across all accounts. Filtered to DATA_CUTOFF_DATE onwards.
        NOTE: For growth calculations, use _paired_sum instead."""
        rows = self.db.query(
            func.to_char(PortfolioSnapshot.statement_date, 'YYYY-MM').label('month'),
            func.sum(PortfolioSnapshot.portfolio_value).label('total')
        ).filter(
            PortfolioSnapshot.statement_date >= self.DATA_CUTOFF_DATE,
        ).group_by('month').order_by('month').all()
        return {row.month: float(row.total) for row in rows}

    def _get_options_income_monthly(self) -> Dict[str, float]:
        """Get monthly options income (YYYY-MM → net income). Brokerage accounts only."""
        rows = self.db.query(
            func.to_char(InvestmentTransaction.transaction_date, 'YYYY-MM').label('month'),
            func.sum(InvestmentTransaction.amount).label('total')
        ).filter(
            InvestmentTransaction.transaction_type.in_(['STO', 'BTC', 'STC', 'BTO']),
            InvestmentTransaction.account_id.in_(self.BROKERAGE_ACCOUNTS),
            InvestmentTransaction.transaction_date >= self.DATA_CUTOFF_DATE,
        ).group_by('month').order_by('month').all()
        return {row.month: float(row.total or 0) for row in rows}

    def _get_options_income_for_range(self, start: date, end: date) -> float:
        """Get total options income for a date range. Brokerage accounts only."""
        effective_start = max(start, self.DATA_CUTOFF_DATE)
        result = self.db.query(
            func.sum(InvestmentTransaction.amount)
        ).filter(
            InvestmentTransaction.transaction_type.in_(['STO', 'BTC', 'STC', 'BTO']),
            InvestmentTransaction.account_id.in_(self.BROKERAGE_ACCOUNTS),
            InvestmentTransaction.transaction_date >= effective_start,
            InvestmentTransaction.transaction_date <= end,
        ).scalar()
        return float(result or 0)

    def _get_monthly_income(self) -> Dict[str, Dict[str, float]]:
        """Aggregate all NON-RETIREMENT income sources into {YYYY-MM: {source: amount, total: sum}}.
        Only includes income from brokerage (taxable) accounts — retirement account
        income (401k, IRA) is excluded since that money can't offset spending.
        Sources: brokerage options/dividends/interest, rental, salary (W-2 take-home)."""
        result: Dict[str, Dict[str, float]] = {}

        def _add(month_key: str, source: str, amount: float):
            if month_key not in result:
                result[month_key] = {'options': 0, 'dividends': 0, 'interest': 0, 'rental': 0, 'salary': 0, 'total': 0}
            result[month_key][source] += amount
            result[month_key]['total'] += amount

        # 1. Options income — brokerage accounts only
        opt_rows = self.db.query(
            func.to_char(InvestmentTransaction.transaction_date, 'YYYY-MM').label('month'),
            func.sum(InvestmentTransaction.amount).label('total'),
        ).filter(
            InvestmentTransaction.transaction_type.in_(['STO', 'BTC', 'STC', 'BTO']),
            InvestmentTransaction.account_id.in_(self.BROKERAGE_ACCOUNTS),
            InvestmentTransaction.transaction_date >= self.DATA_CUTOFF_DATE,
        ).group_by('month').all()
        for row in opt_rows:
            _add(row.month, 'options', float(row.total or 0))

        # 2. Dividends — brokerage accounts only
        div_rows = self.db.query(
            func.to_char(InvestmentTransaction.transaction_date, 'YYYY-MM').label('month'),
            func.sum(InvestmentTransaction.amount).label('total'),
        ).filter(
            InvestmentTransaction.transaction_type.in_(['DIVIDEND', 'DIV']),
            InvestmentTransaction.account_id.in_(self.BROKERAGE_ACCOUNTS),
            InvestmentTransaction.transaction_date >= self.DATA_CUTOFF_DATE,
        ).group_by('month').all()
        for row in div_rows:
            _add(row.month, 'dividends', float(row.total or 0))

        # 3. Interest — brokerage accounts only
        int_rows = self.db.query(
            func.to_char(InvestmentTransaction.transaction_date, 'YYYY-MM').label('month'),
            func.sum(InvestmentTransaction.amount).label('total'),
        ).filter(
            InvestmentTransaction.transaction_type.in_(['INTEREST', 'INT']),
            InvestmentTransaction.account_id.in_(self.BROKERAGE_ACCOUNTS),
            InvestmentTransaction.transaction_date >= self.DATA_CUTOFF_DATE,
        ).group_by('month').all()
        for row in int_rows:
            _add(row.month, 'interest', float(row.total or 0))

        # 4. Rental income
        rental_rows = self.db.query(
            RentalMonthlyIncome.tax_year,
            RentalMonthlyIncome.month,
            func.sum(RentalMonthlyIncome.gross_amount).label('total'),
        ).group_by(
            RentalMonthlyIncome.tax_year,
            RentalMonthlyIncome.month,
        ).all()
        for row in rental_rows:
            if row.tax_year < self.DATA_CUTOFF_DATE.year:
                continue
            month_key = f"{row.tax_year}-{row.month:02d}"
            _add(month_key, 'rental', float(row.total or 0))

        # 5. Salary: use SalaryProjection config table
        # Each row has (person, monthly_net, effective_from, effective_to)
        # For each month in range, find active projections and sum
        sal_rows = self.db.query(SalaryProjection).all()
        if sal_rows:
            # Determine the month range we need salary for
            all_month_keys = set(result.keys())
            # Also include months from rental/investment range
            if all_month_keys:
                min_month = min(all_month_keys)
                max_month = max(all_month_keys)
            else:
                min_month = f"{self.DATA_CUTOFF_DATE.year}-01"
                max_month = date.today().strftime('%Y-%m')

            # Generate month range
            yr, mo = int(min_month[:4]), int(min_month[5:7])
            end_yr, end_mo = int(max_month[:4]), int(max_month[5:7])
            while (yr, mo) <= (end_yr, end_mo):
                month_key = f"{yr}-{mo:02d}"
                total_salary = 0.0
                for sp in sal_rows:
                    if sp.effective_from <= month_key and (sp.effective_to is None or sp.effective_to >= month_key):
                        total_salary += float(sp.monthly_net)
                if total_salary > 0:
                    _add(month_key, 'salary', total_salary)
                mo += 1
                if mo > 12:
                    mo = 1
                    yr += 1

        return result

    def _get_external_cash_flows_for_period(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Get external cash flows (deposits/withdrawals) for Modified Dietz adjustment.
        Returns list of {account_id, date, amount} for flows in the period."""
        effective_start = max(start_date, self.DATA_CUTOFF_DATE)
        rows = self.db.query(
            InvestmentTransaction.account_id,
            InvestmentTransaction.transaction_date,
            InvestmentTransaction.amount,
        ).filter(
            InvestmentTransaction.transaction_type.in_(self.EXTERNAL_FLOW_TYPES),
            InvestmentTransaction.transaction_date >= effective_start,
            InvestmentTransaction.transaction_date <= end_date,
        ).all()
        return [
            {'account_id': r.account_id, 'date': r.transaction_date, 'amount': float(r.amount)}
            for r in rows
        ]

    # ── Helpers ───────────────────────────────────────────────────

    def _modified_dietz_return(
        self, baseline_val: float, actual_val: float,
        flows: List[Dict[str, Any]], period_start: date, period_end: date,
    ) -> float:
        """Compute Modified Dietz return percentage.
        Adjusts raw return for external cash flows weighted by time in period.
        Falls back to simple return if no flows or denominator is near zero."""
        total_days = (period_end - period_start).days + 1
        if total_days <= 0:
            total_days = 1

        net_flows = sum(f['amount'] for f in flows)
        weighted_flows = sum(
            f['amount'] * (total_days - (f['date'] - period_start).days) / total_days
            for f in flows
        )

        denominator = baseline_val + weighted_flows
        if abs(denominator) < 1000:
            # Fallback to simple return if denominator is too small
            return ((actual_val / baseline_val) - 1) * 100 if baseline_val > 0 else 0.0

        return ((actual_val - baseline_val - net_flows) / denominator) * 100

    def _interpolate_daily(self, snapshots: Dict[str, float]) -> Dict[date, float]:
        """Linearly interpolate monthly snapshots to daily values."""
        if not snapshots:
            return {}

        # Convert YYYY-MM to date (use 15th of month as anchor)
        monthly_dates = []
        for key in sorted(snapshots.keys()):
            yr, mo = int(key[:4]), int(key[5:7])
            monthly_dates.append((date(yr, mo, 15), snapshots[key]))

        if len(monthly_dates) < 2:
            return {monthly_dates[0][0]: monthly_dates[0][1]} if monthly_dates else {}

        daily: Dict[date, float] = {}
        for i in range(len(monthly_dates) - 1):
            d1, v1 = monthly_dates[i]
            d2, v2 = monthly_dates[i + 1]
            days_between = (d2 - d1).days
            if days_between <= 0:
                continue
            for d in range(days_between + 1):
                day = d1 + timedelta(days=d)
                ratio = d / days_between
                daily[day] = v1 + (v2 - v1) * ratio

        return daily

    def _nearest_value(self, daily: Dict[date, float], target: date) -> Optional[float]:
        """Find nearest value to target date."""
        if target in daily:
            return daily[target]
        for delta in range(1, 15):
            for d in (target - timedelta(days=delta), target + timedelta(days=delta)):
                if d in daily:
                    return daily[d]
        return None

    def _upsert_metric(
        self, period_type: str, period_start: date, period_end: date,
        metric_type: str, actual_value: float, actual_percent: float,
        expected_value: float, expected_percent: float, baseline_value: float,
        data_completeness: str, force: bool,
    ):
        """Insert or update a metric row."""
        existing = self.db.query(BbdPerformanceMetric).filter(
            BbdPerformanceMetric.period_type == period_type,
            BbdPerformanceMetric.period_start == period_start,
            BbdPerformanceMetric.metric_type == metric_type,
        ).first()

        variance_pct = actual_percent - expected_percent
        variance_val = actual_value - expected_value

        if existing:
            # Only update if force, or if it was partial/current period
            if not force and existing.data_completeness == 'complete':
                return
            existing.actual_value = actual_value
            existing.actual_percent = round(actual_percent, 4)
            existing.expected_value = round(expected_value, 2)
            existing.expected_percent = round(expected_percent, 4)
            existing.baseline_value = round(baseline_value, 2)
            existing.variance_percent = round(variance_pct, 4)
            existing.variance_value = round(variance_val, 2)
            existing.data_completeness = data_completeness
            existing.computed_at = datetime.utcnow()
            existing.updated_at = datetime.utcnow()
        else:
            row = BbdPerformanceMetric(
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                metric_type=metric_type,
                actual_value=round(actual_value, 2),
                actual_percent=round(actual_percent, 4),
                expected_value=round(expected_value, 2),
                expected_percent=round(expected_percent, 4),
                baseline_value=round(baseline_value, 2),
                variance_percent=round(variance_pct, 4),
                variance_value=round(variance_val, 2),
                data_completeness=data_completeness,
            )
            self.db.add(row)
        self.db.flush()

    def get_timeline_data(
        self,
        time_range: str = 'data',
        income_offset: bool = False,
        growth_rate: Optional[float] = None,
        margin_rate: Optional[float] = None,
        margin_ltv: Optional[float] = None,
        options_yield: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Return monthly data points for the BBD timeline chart.

        Combines actual historical data with optional forward projections.
        time_range: 'data' (actuals only), '5y', '10y', 'all' (to age 100)
        income_offset: if True, subtract monthly income from debt accumulation in projections
        growth_rate: annual portfolio growth rate (default 0.08 = 8%)
        margin_rate: annual margin interest rate (default 0.05 = 5%)
        margin_ltv: loan-to-value ratio (default 0.70 = 70%)
        options_yield: monthly options yield (default 0.01 = 1%)
        """
        annual_growth = growth_rate if growth_rate is not None else float(self.ASSUMED_ANNUAL_GROWTH)
        annual_margin = margin_rate if margin_rate is not None else float(self.ASSUMED_ANNUAL_MARGIN_RATE)
        ltv = margin_ltv if margin_ltv is not None else self.MARGIN_LTV
        monthly_yield = options_yield if options_yield is not None else float(self.ASSUMED_MONTHLY_YIELD)
        # ── Gather actuals ──
        account_months = self._get_account_month_values()
        brokerage_months = self._get_brokerage_month_values(account_months)
        monthly_spending = self._get_monthly_spending()

        # Get margin borrowing monthly metrics for cumulative debt
        margin_metrics = self.db.query(BbdPerformanceMetric).filter(
            BbdPerformanceMetric.metric_type == 'margin_borrowing',
            BbdPerformanceMetric.period_type == 'month',
        ).order_by(BbdPerformanceMetric.period_start).all()

        margin_by_month: Dict[str, Dict[str, float]] = {}
        for m in margin_metrics:
            key = m.period_start.strftime('%Y-%m')
            margin_by_month[key] = {
                'cumulative_debt': float(m.actual_value) if m.actual_value else 0,
                'margin_available': float(m.baseline_value) if m.baseline_value else 0,
                'utilization_pct': float(m.actual_percent) if m.actual_percent else 0,
            }

        # Build actual data points from months where we have portfolio data
        all_months = sorted(set(brokerage_months.keys()) | set(margin_by_month.keys()))
        data_points: List[Dict[str, Any]] = []

        # For income_offset: compute cumulative actual income to subtract from debt
        actual_monthly_income: Dict[str, Dict[str, float]] = {}
        if income_offset:
            actual_monthly_income = self._get_monthly_income()

        cumulative_income = 0.0
        for month_key in all_months:
            yr, mo = int(month_key[:4]), int(month_key[5:7])
            total_capital = brokerage_months.get(month_key, 0)
            margin_info = margin_by_month.get(month_key, {})
            cumulative_debt = margin_info.get('cumulative_debt', 0)
            margin_available = margin_info.get('margin_available', total_capital * ltv)

            if total_capital <= 0:
                continue

            # Accumulate actual income and offset debt
            month_income = actual_monthly_income.get(month_key, {}).get('total', 0)
            cumulative_income += month_income
            if income_offset:
                cumulative_debt = max(0, cumulative_debt - cumulative_income)

            net_worth = total_capital - cumulative_debt
            label = date(yr, mo, 1).strftime('%b %Y')

            month_spend = monthly_spending.get(month_key, 0)

            point: Dict[str, Any] = {
                'month': month_key,
                'label': label,
                'total_capital': round(total_capital, 0),
                'margin_available': round(margin_available, 0),
                'cumulative_debt': round(cumulative_debt, 0),
                'net_worth': round(net_worth, 0),
                'actual_monthly_spending': round(month_spend, 0),
                'is_actual': True,
            }
            if income_offset:
                point['actual_monthly_income'] = round(month_income, 0)
                point['cumulative_income'] = round(cumulative_income, 0)
            data_points.append(point)

        if not data_points:
            return {'data_points': [], 'last_actual_month': None, 'assumptions': {}, 'summary': {}}

        last_actual_month = data_points[-1]['month']
        last_actual = data_points[-1]

        # ── Compute average monthly spending for projections ──
        spend_values = list(monthly_spending.values())
        avg_monthly_spending = sum(spend_values) / len(spend_values) if spend_values else 0

        # ── Compute income components for income_offset mode ──
        # Options income scales with portfolio (1%/mo assumed yield).
        # Other income uses current rate (last actual month) per source.
        avg_fixed_income = 0.0
        current_interest = 0.0
        current_dividends = 0.0
        current_rental = 0.0
        current_salary = 0.0
        if income_offset and actual_monthly_income:
            last_sources = actual_monthly_income.get(last_actual_month, {})
            current_interest = last_sources.get('interest', 0)
            current_rental = last_sources.get('rental', 0)
            current_salary = last_sources.get('salary', 0)

            # Dividends: average of last 3 months (quarterly payout pattern)
            recent_months = sorted(actual_monthly_income.keys())[-3:]
            current_dividends = sum(
                actual_monthly_income.get(m, {}).get('dividends', 0) for m in recent_months
            ) / 3 if recent_months else 0

            avg_fixed_income = current_interest + current_dividends + current_rental + current_salary

        # ── Determine projection months ──
        today = date.today()
        current_age = 45  # hardcoded as in projection endpoint
        birth_year = today.year - current_age

        if time_range == 'data':
            projection_months = 0
        elif time_range == '5y':
            projection_months = 5 * 12
        elif time_range == '10y':
            projection_months = 10 * 12
        elif time_range == '20y':
            projection_months = 20 * 12
        elif time_range == '30y':
            projection_months = 30 * 12
        else:  # 'all' — to age 100
            end_year = birth_year + 100
            last_yr, last_mo = int(last_actual_month[:4]), int(last_actual_month[5:7])
            projection_months = (end_year - last_yr) * 12 + (12 - last_mo)

        # ── Generate projections ──
        if projection_months > 0:
            monthly_growth_rate = (1 + annual_growth) ** (1/12) - 1
            monthly_interest_rate = (1 + annual_margin) ** (1/12) - 1

            proj_capital = last_actual['total_capital']
            proj_debt = last_actual['cumulative_debt']
            last_yr, last_mo = int(last_actual_month[:4]), int(last_actual_month[5:7])

            # Add a bridge point: last actual data duplicated as first projected point
            data_points[-1] = {
                **data_points[-1],
                # Add projected fields equal to actual so lines connect
                'proj_total_capital': last_actual['total_capital'],
                'proj_margin_available': last_actual['margin_available'],
                'proj_cumulative_debt': last_actual['cumulative_debt'],
                'proj_net_worth': last_actual['net_worth'],
            }

            for i in range(1, projection_months + 1):
                mo = last_mo + i
                yr = last_yr + (mo - 1) // 12
                mo = ((mo - 1) % 12) + 1
                month_key = f"{yr}-{mo:02d}"
                label = date(yr, mo, 1).strftime('%b %Y')

                # Grow capital
                proj_capital *= (1 + monthly_growth_rate)
                # Interest on existing debt
                if proj_debt > 0:
                    proj_debt *= (1 + monthly_interest_rate)
                # Add monthly spending as new debt
                proj_debt += avg_monthly_spending
                # Subtract income if income_offset mode
                proj_monthly_income = 0.0
                if income_offset:
                    # Options income = 1%/mo of current capital; other income is flat
                    options_income = proj_capital * monthly_yield
                    proj_monthly_income = options_income + avg_fixed_income
                    proj_debt = max(0, proj_debt - proj_monthly_income)

                margin_avail = proj_capital * ltv
                net_worth = proj_capital - proj_debt

                point: Dict[str, Any] = {
                    'month': month_key,
                    'label': label,
                    'total_capital': None,
                    'margin_available': None,
                    'cumulative_debt': None,
                    'net_worth': None,
                    'proj_total_capital': round(proj_capital, 0),
                    'proj_margin_available': round(margin_avail, 0),
                    'proj_cumulative_debt': round(proj_debt, 0),
                    'proj_net_worth': round(net_worth, 0),
                    'is_actual': False,
                }
                if income_offset:
                    point['proj_monthly_income'] = round(proj_monthly_income, 0)
                data_points.append(point)

        # ── Summary ──
        final = data_points[-1]
        # Use 'is not None' checks — 'or' fails when projected values are 0 (falsy)
        final_capital = final.get('proj_total_capital') if final.get('proj_total_capital') is not None else final.get('total_capital', 0)
        final_debt = final.get('proj_cumulative_debt') if final.get('proj_cumulative_debt') is not None else final.get('cumulative_debt', 0)
        final_margin = final.get('proj_margin_available') if final.get('proj_margin_available') is not None else final.get('margin_available', 0)
        final_net = final.get('proj_net_worth') if final.get('proj_net_worth') is not None else final.get('net_worth', 0)

        # ── Per-account breakdown for latest month ──
        account_breakdown = []
        # Look up display names for brokerage accounts
        account_names = {}
        acct_rows = self.db.query(InvestmentAccount).filter(
            InvestmentAccount.account_id.in_(self.BROKERAGE_ACCOUNTS),
        ).all()
        for a in acct_rows:
            account_names[a.account_id] = a.account_name or a.account_id

        for key, months_data in account_months.items():
            if not any(key.startswith(acct) for acct in self.BROKERAGE_ACCOUNTS):
                continue
            val = months_data.get(last_actual_month, 0)
            if val <= 0:
                continue
            # key is "account_id_source" — extract account_id
            account_id = key.rsplit('_', 1)[0]
            display_name = account_names.get(account_id, account_id)
            account_breakdown.append({
                'name': display_name,
                'value': round(val, 0),
            })
        account_breakdown.sort(key=lambda x: x['value'], reverse=True)

        summary = {
            'current_total_capital': last_actual['total_capital'],
            'current_margin_available': last_actual['margin_available'],
            'current_cumulative_debt': last_actual['cumulative_debt'],
            'current_net_worth': last_actual['net_worth'],
            'current_utilization_pct': round(
                (last_actual['cumulative_debt'] / last_actual['margin_available'] * 100)
                if last_actual['margin_available'] > 0 else 0, 1
            ),
            'capital_account_breakdown': account_breakdown,
            'final_total_capital': round(final_capital, 0),
            'final_margin_available': round(final_margin, 0),
            'final_cumulative_debt': round(final_debt, 0),
            'final_net_worth': round(final_net, 0),
        }

        assumptions = {
            'annual_growth_rate_pct': round(annual_growth * 100, 2),
            'annual_interest_rate_pct': round(annual_margin * 100, 2),
            'avg_monthly_spending': round(avg_monthly_spending, 0),
            'margin_ltv_pct': round(ltv * 100, 1),
            'income_offset': income_offset,
            'options_yield_pct': round(monthly_yield * 100, 2) if income_offset else 0,
            'avg_fixed_income': round(avg_fixed_income, 0) if income_offset else 0,
            'fixed_income_breakdown': {
                'interest': round(current_interest, 0),
                'dividends': round(current_dividends, 0),
                'rental': round(current_rental, 0),
                'salary': round(current_salary, 0),
            } if income_offset else {},
        }

        # ── Income breakdown table (only when income_offset is on) ──
        income_breakdown: List[Dict[str, Any]] = []
        if income_offset:
            all_breakdown_months = sorted(set(list(actual_monthly_income.keys()) + list(monthly_spending.keys())))
            for mk in all_breakdown_months:
                yr, mo = int(mk[:4]), int(mk[5:7])
                label = date(yr, mo, 1).strftime('%b %Y')
                sources = actual_monthly_income.get(mk, {})
                spend = monthly_spending.get(mk, 0)
                total_inc = sources.get('total', 0)
                income_breakdown.append({
                    'month': mk,
                    'label': label,
                    'spending': round(spend, 0),
                    'options': round(sources.get('options', 0), 0),
                    'dividends': round(sources.get('dividends', 0), 0),
                    'interest': round(sources.get('interest', 0), 0),
                    'rental': round(sources.get('rental', 0), 0),
                    'salary': round(sources.get('salary', 0), 0),
                    'total_income': round(total_inc, 0),
                    'net': round(total_inc - spend, 0),
                })

        return {
            'data_points': data_points,
            'last_actual_month': last_actual_month,
            'time_range': time_range,
            'assumptions': assumptions,
            'summary': summary,
            'income_breakdown': income_breakdown,
        }

    def _row_to_dict(self, row: BbdPerformanceMetric) -> Dict[str, Any]:
        """Convert a DB row to dict for API response."""
        # Generate a human-readable label
        if row.period_type == 'year':
            label = str(row.period_start.year)
        elif row.period_type == 'month':
            label = row.period_start.strftime('%b %Y')
        else:
            label = f"W/O {row.period_start.strftime('%b %d')}"

        return {
            'period_label': label,
            'period_start': row.period_start.isoformat(),
            'period_end': row.period_end.isoformat(),
            'actual_value': float(row.actual_value) if row.actual_value is not None else None,
            'expected_value': float(row.expected_value) if row.expected_value is not None else None,
            'actual_percent': float(row.actual_percent) if row.actual_percent is not None else None,
            'expected_percent': float(row.expected_percent) if row.expected_percent is not None else None,
            'baseline_value': float(row.baseline_value) if row.baseline_value is not None else None,
            'variance_percent': float(row.variance_percent) if row.variance_percent is not None else None,
            'variance_value': float(row.variance_value) if row.variance_value is not None else None,
            'data_completeness': row.data_completeness,
        }
