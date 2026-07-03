"""
Rental Income Service - Load rental income from database.

For the current year, if no data exists, projects income based on previous year's
monthly average. Income is only counted for months that have passed (up to and
including the current month).
"""

from datetime import datetime, date
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from sqlalchemy import func
from app.core.database import SessionLocal
from app.modules.income.models import (
    RentalProperty as RentalPropertyModel,
    RentalAnnualSummary,
    RentalMonthlyIncome,
    RentalExpense as RentalExpenseModel,
)
from app.modules.real_estate.models import PropertyRentalExpense


@dataclass
class RentalExpense:
    """Represents a rental expense category."""
    category: str
    amount: float
    notes: str = ''


@dataclass  
class MonthlyRent:
    """Represents monthly rental income."""
    month: str  # e.g., "2025-01"
    month_name: str  # e.g., "Jan"
    amount: float
    year: int


@dataclass
class RentalProperty:
    """Represents a rental property with income and expenses."""
    address: str
    year: int
    gross_income: float = 0.0
    total_expenses: float = 0.0
    net_income: float = 0.0
    property_tax: float = 0.0
    hoa: float = 0.0
    maintenance: float = 0.0
    other_expenses: float = 0.0
    cost_basis: float = 0.0
    monthly_income: List[MonthlyRent] = field(default_factory=list)
    expenses: List[RentalExpense] = field(default_factory=list)


# Month number to name mapping
MONTH_NAMES = {
    1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr',
    5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug',
    9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
}


class RentalIncomeService:
    """Service to load and aggregate rental income from database."""

    def __init__(self):
        """Initialize the service."""
        self.properties: List[RentalProperty] = []
        self._loaded = False

    def _load_from_database(self) -> List[RentalProperty]:
        """Load rental data from database tables."""
        self.properties = []
        db = SessionLocal()
        
        try:
            # Get all rental properties
            db_properties = db.query(RentalPropertyModel).filter(
                RentalPropertyModel.is_active == 'Y'
            ).all()
            
            for db_prop in db_properties:
                # Get annual summaries for this property
                summaries = db.query(RentalAnnualSummary).filter(
                    RentalAnnualSummary.property_id == db_prop.id
                ).order_by(RentalAnnualSummary.tax_year.desc()).all()
                
                for summary in summaries:
                    # Create a RentalProperty for each year
                    prop = RentalProperty(
                        address=db_prop.property_address or '',
                        year=summary.tax_year,
                        gross_income=float(summary.annual_income or 0),
                        total_expenses=float(summary.total_expenses or 0),
                        net_income=float(summary.net_income or 0),
                        cost_basis=float(db_prop.purchase_price or 0),
                    )
                    
                    # Parse expense breakdown from JSON
                    if summary.expense_breakdown:
                        breakdown = summary.expense_breakdown
                        prop.property_tax = float(breakdown.get('property_tax', 0))
                        prop.hoa = float(breakdown.get('hoa', 0))
                        prop.maintenance = float(breakdown.get('maintenance', 0) + 
                                                 breakdown.get('cleaning_maintenance', 0) +
                                                 breakdown.get('repairs', 0))
                        
                        # Build expenses list
                        for category, amount in breakdown.items():
                            if amount and amount > 0:
                                prop.expenses.append(RentalExpense(
                                    category=category.replace('_', ' ').title(),
                                    amount=float(amount)
                                ))
                    
                    # Get monthly income for this year
                    monthly_records = db.query(RentalMonthlyIncome).filter(
                        RentalMonthlyIncome.property_id == db_prop.id,
                        RentalMonthlyIncome.tax_year == summary.tax_year
                    ).order_by(RentalMonthlyIncome.month).all()
                    
                    for monthly in monthly_records:
                        month_key = f"{monthly.tax_year}-{monthly.month:02d}"
                        month_name = MONTH_NAMES.get(monthly.month, 'Unk')
                        prop.monthly_income.append(MonthlyRent(
                            month=month_key,
                            month_name=month_name,
                            amount=float(monthly.gross_amount or 0),
                            year=monthly.tax_year
                        ))
                    
                    self.properties.append(prop)

            # Sync expenses from Real Estate tab (rental_annual_expenses)
            self._sync_expenses_from_real_estate(db)

            # Project current year's rental income if no data exists
            self._project_current_year_income(db)

            # Cap current year to only months actually received
            self._cap_to_received_months()

            self._loaded = True

        except Exception as e:
            print(f"Error loading rental data from database: {e}")
        finally:
            db.close()

        return self.properties

    def _sync_expenses_from_real_estate(self, db) -> None:
        """
        Override expense data with values from the Real Estate tab's
        rental_annual_expenses table, which is the user-editable source of truth.
        """
        for prop in self.properties:
            expense_rows = db.query(PropertyRentalExpense).filter(
                PropertyRentalExpense.property_id == 1,  # single property for now
                PropertyRentalExpense.tax_year == prop.year,
            ).all()

            if not expense_rows:
                continue

            # Rebuild expenses from Real Estate tab data
            total_expenses = sum(float(e.amount or 0) for e in expense_rows)
            prop.total_expenses = total_expenses
            prop.net_income = prop.gross_income - total_expenses

            prop.property_tax = 0.0
            prop.hoa = 0.0
            prop.maintenance = 0.0
            prop.other_expenses = 0.0
            prop.expenses = []

            for e in expense_rows:
                amt = float(e.amount or 0)
                if amt <= 0:
                    continue

                cat = e.category.lower()
                if 'property_tax' in cat:
                    prop.property_tax = amt
                elif 'hoa' in cat:
                    prop.hoa = amt
                elif cat in ('maintenance', 'cleaning_and_maintenance', 'cleaning_maintenance', 'repairs'):
                    prop.maintenance += amt
                else:
                    prop.other_expenses += amt

                prop.expenses.append(RentalExpense(
                    category=e.category.replace('_', ' ').title(),
                    amount=amt
                ))

    def _project_current_year_income(self, db) -> None:
        """
        Project current year's rental income based on previous year's data.

        For each property, if the current year has no data:
        - Uses the previous year's monthly average
        - Only includes months that have passed (up to current month)
        """
        current_year = date.today().year
        current_month = date.today().month

        # Check if we have data for the current year
        current_year_props = [p for p in self.properties if p.year == current_year]

        if current_year_props:
            # Already have data for current year, no need to project
            return

        # Get all active properties
        db_properties = db.query(RentalPropertyModel).filter(
            RentalPropertyModel.is_active == 'Y'
        ).all()

        for db_prop in db_properties:
            # Find the most recent year's data for this property
            prev_year_props = [p for p in self.properties
                               if p.address == (db_prop.property_address or '')]

            if not prev_year_props:
                continue

            # Sort by year descending and get the most recent
            prev_year_props.sort(key=lambda x: x.year, reverse=True)
            prev_prop = prev_year_props[0]

            # Calculate monthly average from previous year
            if prev_prop.monthly_income:
                monthly_avg = sum(m.amount for m in prev_prop.monthly_income) / len(prev_prop.monthly_income)
            elif prev_prop.gross_income > 0:
                monthly_avg = prev_prop.gross_income / 12
            else:
                continue  # No data to project from

            # Create projected property for current year
            projected_gross = monthly_avg * current_month
            # Use same expense ratio as previous year
            expense_ratio = prev_prop.total_expenses / prev_prop.gross_income if prev_prop.gross_income > 0 else 0
            projected_expenses = projected_gross * expense_ratio
            projected_net = projected_gross - projected_expenses

            prop = RentalProperty(
                address=db_prop.property_address or '',
                year=current_year,
                gross_income=projected_gross,
                total_expenses=projected_expenses,
                net_income=projected_net,
                property_tax=prev_prop.property_tax * (current_month / 12),
                hoa=prev_prop.hoa * (current_month / 12),
                maintenance=prev_prop.maintenance * (current_month / 12),
                cost_basis=float(db_prop.purchase_price or 0),
            )

            # Add monthly income for each passed month
            for month in range(1, current_month + 1):
                month_key = f"{current_year}-{month:02d}"
                month_name = MONTH_NAMES.get(month, 'Unk')
                prop.monthly_income.append(MonthlyRent(
                    month=month_key,
                    month_name=month_name,
                    amount=monthly_avg,
                    year=current_year
                ))

            self.properties.append(prop)

    def _cap_to_received_months(self) -> None:
        """
        For the current year, trim income and expenses to months actually received.

        The DB may have all 12 months pre-populated from a rental agreement, but
        future months haven't been collected yet. This ensures gross income, expenses,
        and net income only reflect months up to and including today.
        """
        current_year = date.today().year
        current_month = date.today().month

        for prop in self.properties:
            if prop.year != current_year:
                continue

            # Drop future months from the monthly breakdown
            prop.monthly_income = [
                m for m in prop.monthly_income
                if int(m.month.split('-')[1]) <= current_month
            ]

            # Recompute gross from actual received months
            prop.gross_income = sum(m.amount for m in prop.monthly_income)

            # Prorate annual expenses to the fraction of the year elapsed
            ratio = current_month / 12
            prop.total_expenses = round(prop.total_expenses * ratio, 2)
            prop.property_tax = round(prop.property_tax * ratio, 2)
            prop.hoa = round(prop.hoa * ratio, 2)
            prop.maintenance = round(prop.maintenance * ratio, 2)
            prop.other_expenses = round(prop.other_expenses * ratio, 2)
            for expense in prop.expenses:
                expense.amount = round(expense.amount * ratio, 2)

            prop.net_income = round(prop.gross_income - prop.total_expenses, 2)

    def load_all_properties(self) -> List[RentalProperty]:
        """Load all rental properties from database."""
        if not self._loaded:
            self._load_from_database()
        return self.properties

    def get_rental_summary(self) -> Dict:
        """Get summary of all rental income."""
        if not self._loaded:
            self._load_from_database()
        
        total_gross = sum(p.gross_income for p in self.properties)
        total_expenses = sum(p.total_expenses for p in self.properties)
        total_net = sum(p.net_income for p in self.properties)
        total_property_tax = sum(p.property_tax for p in self.properties)
        total_hoa = sum(p.hoa for p in self.properties)
        total_maintenance = sum(p.maintenance for p in self.properties)
        
        properties_data = []
        for prop in self.properties:
            properties_data.append({
                'address': prop.address,
                'year': prop.year,
                'gross_income': prop.gross_income,
                'total_expenses': prop.total_expenses,
                'net_income': prop.net_income,
                'property_tax': prop.property_tax,
                'hoa': prop.hoa,
                'maintenance': prop.maintenance,
                'other_expenses': prop.other_expenses,
                'cost_basis': prop.cost_basis,
                'expenses': [{'category': e.category, 'amount': e.amount} for e in prop.expenses],
                'monthly_income': [
                    {'month': m.month, 'month_name': m.month_name, 'amount': m.amount, 'year': m.year}
                    for m in prop.monthly_income
                ],
            })
        
        return {
            'total_gross_income': total_gross,
            'total_expenses': total_expenses,
            'total_net_income': total_net,
            'total_property_tax': total_property_tax,
            'total_hoa': total_hoa,
            'total_maintenance': total_maintenance,
            'property_count': len(self.properties),
            'properties': properties_data,
        }

    def get_monthly_chart_data(self, year: int = None) -> List[Dict]:
        """Get monthly rental income data for charting."""
        if not self._loaded:
            self._load_from_database()
        
        # Aggregate monthly data across all properties
        monthly_data = {}
        
        for prop in self.properties:
            if year and prop.year != year:
                continue
            for monthly in prop.monthly_income:
                if monthly.month not in monthly_data:
                    monthly_data[monthly.month] = {
                        'gross': 0,
                        'month_name': monthly.month_name,
                        'year': monthly.year,
                    }
                monthly_data[monthly.month]['gross'] += monthly.amount
        
        # Convert to list and sort
        chart_data = []
        for month_key, data in sorted(monthly_data.items()):
            chart_data.append({
                'month': month_key,
                'formatted': f"{data['month_name']} {data['year']}",
                'value': data['gross'],
                'year': data['year'],
            })
        
        return chart_data


# Singleton instance - recreated each call to get fresh DB data
_rental_service: Optional[RentalIncomeService] = None


def get_rental_service() -> RentalIncomeService:
    """Get or create the rental income service."""
    # Always create fresh instance to get latest DB data
    return RentalIncomeService()

