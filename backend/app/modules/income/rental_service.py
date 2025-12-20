"""
Rental Income Service - Load rental income from database.
"""

from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from app.core.database import SessionLocal
from app.modules.income.models import (
    RentalProperty as RentalPropertyModel,
    RentalAnnualSummary,
    RentalMonthlyIncome,
    RentalExpense as RentalExpenseModel,
)


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
            
            self._loaded = True
            
        except Exception as e:
            print(f"Error loading rental data from database: {e}")
        finally:
            db.close()
        
        return self.properties

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

