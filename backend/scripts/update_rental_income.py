#!/usr/bin/env python3
"""
Update rental income data in the database with correct values:
- Monthly rental income: $6,300 × 12 = $75,600/year
- HOA: $420/month × 12 = $5,040/year
- Property tax: $1,000/month × 12 = $12,000/year
- Maintenance: $200/month × 12 = $2,400/year
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.modules.income.models import (
    RentalProperty,
    RentalAnnualSummary,
    RentalMonthlyIncome,
    RentalExpense
)
from decimal import Decimal
import json


# Constants
MONTHLY_RENT = Decimal('6300.00')
ANNUAL_RENT = MONTHLY_RENT * 12  # $75,600

MONTHLY_HOA = Decimal('420.00')
ANNUAL_HOA = MONTHLY_HOA * 12  # $5,040

MONTHLY_PROPERTY_TAX = Decimal('1000.00')
ANNUAL_PROPERTY_TAX = MONTHLY_PROPERTY_TAX * 12  # $12,000

MONTHLY_MAINTENANCE = Decimal('200.00')
ANNUAL_MAINTENANCE = MONTHLY_MAINTENANCE * 12  # $2,400

TOTAL_EXPENSES = ANNUAL_HOA + ANNUAL_PROPERTY_TAX + ANNUAL_MAINTENANCE  # $19,440
NET_INCOME = ANNUAL_RENT - TOTAL_EXPENSES  # $56,160


def main():
    db = SessionLocal()
    
    try:
        # Find the property
        property_address = "303 Hartstene Dr, Redwood City CA 94065"
        property = db.query(RentalProperty).filter(
            RentalProperty.property_address == property_address
        ).first()
        
        if not property:
            print(f"Property not found: {property_address}")
            return
        
        print(f"Updating rental income for: {property.property_address}")
        print(f"Property ID: {property.id}\n")
        
        # Update annual summaries for both 2024 and 2025
        years = [2024, 2025]
        
        for year in years:
            print(f"Updating year {year}...")
            
            # Get or create annual summary
            summary = db.query(RentalAnnualSummary).filter(
                RentalAnnualSummary.property_id == property.id,
                RentalAnnualSummary.tax_year == year
            ).first()
            
            if not summary:
                summary = RentalAnnualSummary(
                    property_id=property.id,
                    tax_year=year
                )
                db.add(summary)
            
            # Update annual summary
            summary.annual_income = ANNUAL_RENT
            summary.total_expenses = TOTAL_EXPENSES
            summary.net_income = NET_INCOME
            
            # Update expense breakdown JSON (only the three categories)
            summary.expense_breakdown = {
                'hoa': float(ANNUAL_HOA),
                'property_tax': float(ANNUAL_PROPERTY_TAX),
                'maintenance': float(ANNUAL_MAINTENANCE)
            }
            
            print(f"  Annual Income: ${ANNUAL_RENT:,.2f}")
            print(f"  Total Expenses: ${TOTAL_EXPENSES:,.2f}")
            print(f"  Net Income: ${NET_INCOME:,.2f}")
            
            # Update monthly income records for all 12 months
            for month in range(1, 13):
                monthly = db.query(RentalMonthlyIncome).filter(
                    RentalMonthlyIncome.property_id == property.id,
                    RentalMonthlyIncome.tax_year == year,
                    RentalMonthlyIncome.month == month
                ).first()
                
                if not monthly:
                    monthly = RentalMonthlyIncome(
                        property_id=property.id,
                        tax_year=year,
                        month=month,
                        gross_amount=MONTHLY_RENT
                    )
                    db.add(monthly)
                else:
                    monthly.gross_amount = MONTHLY_RENT
            
            print(f"  Updated 12 monthly income records to ${MONTHLY_RENT:,.2f}/month")
            
            # Delete old expense records and create new ones (only 3 categories)
            db.query(RentalExpense).filter(
                RentalExpense.property_id == property.id,
                RentalExpense.tax_year == year
            ).delete()
            
            # Create new expense records
            expenses = [
                ('hoa', ANNUAL_HOA, 'HOA dues'),
                ('property_tax', ANNUAL_PROPERTY_TAX, 'Property tax'),
                ('maintenance', ANNUAL_MAINTENANCE, 'Maintenance')
            ]
            
            for category, amount, description in expenses:
                expense = RentalExpense(
                    property_id=property.id,
                    tax_year=year,
                    category=category,
                    amount=amount,
                    description=description
                )
                db.add(expense)
            
            print(f"  Updated expense records: HOA ${ANNUAL_HOA:,.2f}, Property Tax ${ANNUAL_PROPERTY_TAX:,.2f}, Maintenance ${ANNUAL_MAINTENANCE:,.2f}")
            print()
        
        # Commit all changes
        db.commit()
        print("✓ All updates committed successfully!")
        
        # Print summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Monthly Rental Income: ${MONTHLY_RENT:,.2f}")
        print(f"Annual Rental Income: ${ANNUAL_RENT:,.2f}")
        print(f"\nMonthly Expenses:")
        print(f"  HOA: ${MONTHLY_HOA:,.2f}")
        print(f"  Property Tax: ${MONTHLY_PROPERTY_TAX:,.2f}")
        print(f"  Maintenance: ${MONTHLY_MAINTENANCE:,.2f}")
        print(f"  Total Monthly: ${MONTHLY_HOA + MONTHLY_PROPERTY_TAX + MONTHLY_MAINTENANCE:,.2f}")
        print(f"\nAnnual Expenses:")
        print(f"  HOA: ${ANNUAL_HOA:,.2f}")
        print(f"  Property Tax: ${ANNUAL_PROPERTY_TAX:,.2f}")
        print(f"  Maintenance: ${ANNUAL_MAINTENANCE:,.2f}")
        print(f"  Total Annual: ${TOTAL_EXPENSES:,.2f}")
        print(f"\nNet Annual Income: ${NET_INCOME:,.2f}")
        
    except Exception as e:
        db.rollback()
        print(f"Error updating rental income: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()



