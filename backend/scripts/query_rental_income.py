#!/usr/bin/env python3
"""
Query rental income data from the database.
Shows all properties, annual summaries, monthly income, and expenses.
"""

import sys
import os
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
from sqlalchemy import func
import json


def format_currency(amount):
    """Format amount as currency."""
    if amount is None:
        return "$0.00"
    return f"${float(amount):,.2f}"


def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def main():
    db = SessionLocal()
    
    try:
        # Get all rental properties
        print_section("RENTAL PROPERTIES")
        properties = db.query(RentalProperty).all()
        
        if not properties:
            print("No rental properties found in database.")
        else:
            print(f"\nTotal Properties: {len(properties)}\n")
            
            for prop in properties:
                print(f"Property ID: {prop.id}")
                print(f"  Address: {prop.property_address}")
                print(f"  Name: {prop.property_name or 'N/A'}")
                print(f"  Purchase Date: {prop.purchase_date or 'N/A'}")
                print(f"  Purchase Price: {format_currency(prop.purchase_price)}")
                print(f"  Current Value: {format_currency(prop.current_value)}")
                print(f"  Active: {prop.is_active}")
                print(f"  Notes: {prop.notes or 'None'}")
                print()
        
        # Get annual summaries
        print_section("ANNUAL SUMMARIES (Income & Expenses by Year)")
        summaries = db.query(RentalAnnualSummary).join(RentalProperty).order_by(
            RentalProperty.property_address,
            RentalAnnualSummary.tax_year.desc()
        ).all()
        
        if not summaries:
            print("No annual summaries found in database.")
        else:
            print(f"\nTotal Annual Summaries: {len(summaries)}\n")
            
            for summary in summaries:
                prop = summary.property
                print(f"Property: {prop.property_address}")
                print(f"  Tax Year: {summary.tax_year}")
                print(f"  Annual Income: {format_currency(summary.annual_income)}")
                print(f"  Total Expenses: {format_currency(summary.total_expenses)}")
                print(f"  Net Income: {format_currency(summary.net_income)}")
                
                if summary.expense_breakdown:
                    print(f"  Expense Breakdown:")
                    for category, amount in summary.expense_breakdown.items():
                        if amount and amount > 0:
                            print(f"    {category}: {format_currency(amount)}")
                
                print(f"  Source File: {summary.source_file or 'N/A'}")
                print()
        
        # Get monthly income
        print_section("MONTHLY RENTAL INCOME")
        monthly_income = db.query(RentalMonthlyIncome).join(RentalProperty).order_by(
            RentalProperty.property_address,
            RentalMonthlyIncome.tax_year.desc(),
            RentalMonthlyIncome.month
        ).all()
        
        if not monthly_income:
            print("No monthly income records found in database.")
        else:
            print(f"\nTotal Monthly Records: {len(monthly_income)}\n")
            
            # Group by property and year
            current_prop = None
            current_year = None
            
            for monthly in monthly_income:
                prop = monthly.property
                if current_prop != prop.property_address or current_year != monthly.tax_year:
                    if current_prop is not None:
                        print()
                    current_prop = prop.property_address
                    current_year = monthly.tax_year
                    print(f"Property: {prop.property_address} - Year {monthly.tax_year}")
                
                month_names = {
                    1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr',
                    5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug',
                    9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
                }
                month_name = month_names.get(monthly.month, f"Month {monthly.month}")
                print(f"  {month_name}: {format_currency(monthly.gross_amount)}")
        
        # Get expenses
        print_section("RENTAL EXPENSES (By Category)")
        expenses = db.query(RentalExpense).join(RentalProperty).order_by(
            RentalProperty.property_address,
            RentalExpense.tax_year.desc(),
            RentalExpense.category
        ).all()
        
        if not expenses:
            print("No expense records found in database.")
        else:
            print(f"\nTotal Expense Records: {len(expenses)}\n")
            
            # Group by property and year
            current_prop = None
            current_year = None
            
            for expense in expenses:
                prop = expense.property
                if current_prop != prop.property_address or current_year != expense.tax_year:
                    if current_prop is not None:
                        print()
                    current_prop = prop.property_address
                    current_year = expense.tax_year
                    print(f"Property: {prop.property_address} - Year {expense.tax_year}")
                
                print(f"  {expense.category}: {format_currency(expense.amount)}")
                if expense.description:
                    print(f"    Description: {expense.description}")
        
        # Summary statistics
        print_section("SUMMARY STATISTICS")
        
        # Total properties
        total_props = db.query(func.count(RentalProperty.id)).scalar()
        active_props = db.query(func.count(RentalProperty.id)).filter(
            RentalProperty.is_active == 'Y'
        ).scalar()
        
        # Total income/expenses across all years
        total_income = db.query(func.sum(RentalAnnualSummary.annual_income)).scalar() or 0
        total_expenses = db.query(func.sum(RentalAnnualSummary.total_expenses)).scalar() or 0
        total_net = db.query(func.sum(RentalAnnualSummary.net_income)).scalar() or 0
        
        # Years covered
        years = db.query(RentalAnnualSummary.tax_year).distinct().order_by(
            RentalAnnualSummary.tax_year.desc()
        ).all()
        years_list = [y[0] for y in years]
        
        # Monthly records count
        monthly_count = db.query(func.count(RentalMonthlyIncome.id)).scalar()
        
        # Expense records count
        expense_count = db.query(func.count(RentalExpense.id)).scalar()
        
        print(f"\nProperties:")
        print(f"  Total: {total_props}")
        print(f"  Active: {active_props}")
        
        print(f"\nFinancial Summary (All Years):")
        print(f"  Total Gross Income: {format_currency(total_income)}")
        print(f"  Total Expenses: {format_currency(total_expenses)}")
        print(f"  Total Net Income: {format_currency(total_net)}")
        
        print(f"\nData Coverage:")
        print(f"  Years: {', '.join(map(str, years_list)) if years_list else 'None'}")
        print(f"  Monthly Income Records: {monthly_count}")
        print(f"  Expense Records: {expense_count}")
        print(f"  Annual Summary Records: {len(summaries)}")
        
    except Exception as e:
        print(f"Error querying database: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()



