"""
Tax Forecast Calculation Service.

Generates tax forecasts for future years based on:
- Historical tax data (deductions, filing status, etc.)
- Projected income for the forecast year
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from decimal import Decimal
import json

from app.modules.tax.models import IncomeTaxReturn
from app.modules.income.models import W2Record
from app.modules.income import db_queries
from app.modules.income.salary_service import get_salary_service
from app.modules.income.rental_service import get_rental_service


def calculate_tax_forecast(
    db: Session,
    forecast_year: int = 2025,
    base_year: int = 2024
) -> Dict[str, Any]:
    """
    Calculate tax forecast for a given year based on historical data and projected income.
    
    Args:
        db: Database session
        forecast_year: Year to forecast (default: 2025)
        base_year: Year to use as base for deductions and patterns (default: 2024)
    
    Returns:
        Dictionary with forecasted tax data in the same format as IncomeTaxReturn
    """
    # Get base year tax return for deductions and filing status
    base_return = db.query(IncomeTaxReturn).filter(
        IncomeTaxReturn.tax_year == base_year
    ).first()
    
    if not base_return:
        raise ValueError(f"No tax return found for base year {base_year}")
    
    # Parse base year details
    base_details = {}
    if base_return.details_json:
        try:
            base_details = json.loads(base_return.details_json)
        except:
            pass
    
    # Get 2025 income data
    forecast_income = _get_forecast_income(db, forecast_year)
    
    # Calculate AGI
    agi = _calculate_agi(forecast_income)
    
    # Get deductions from base year
    deductions = base_details.get("deductions", {})
    
    # Calculate taxable income
    taxable_income = _calculate_taxable_income(agi, deductions, forecast_year)
    
    # Calculate federal tax
    filing_status = base_return.filing_status or "MFJ"
    federal_tax = _calculate_federal_tax(taxable_income, filing_status, forecast_year)
    
    # Calculate state tax (assuming California)
    state_tax = _calculate_ca_state_tax(taxable_income, filing_status, forecast_year)
    
    # Calculate other taxes (payroll, NIIT, etc.)
    other_taxes = _calculate_other_taxes(forecast_income, agi, base_details)
    
    # Calculate effective rate
    total_tax = federal_tax + state_tax + other_taxes
    effective_rate = (total_tax / agi * 100) if agi > 0 else 0
    
    # Build details JSON similar to base year
    forecast_details = _build_forecast_details(
        forecast_income, deductions, base_details, forecast_year
    )
    
    return {
        "tax_year": forecast_year,
        "agi": agi,
        "federal_tax": federal_tax,
        "state_tax": state_tax,
        "other_tax": other_taxes,
        "total_tax": total_tax,
        "effective_rate": round(effective_rate, 2),
        "filing_status": filing_status,
        "details": forecast_details,
        "is_forecast": True
    }


def _get_forecast_income(db: Session, year: int) -> Dict[str, Any]:
    """Get all income sources for the forecast year."""
    income = {
        "w2_income": {},
        "rental_income": 0,
        "options_income": 0,
        "dividend_income": 0,
        "interest_income": 0,
    }
    
    # Get W-2 income for the year
    w2_records = db.query(W2Record).filter(
        W2Record.tax_year == year
    ).all()
    
    w2_breakdown = []
    total_w2_wages = 0
    total_federal_withheld = 0
    total_state_withheld = 0
    total_social_security = 0
    total_medicare = 0
    
    for w2 in w2_records:
        wages = float(w2.wages or 0)
        federal_withheld = float(w2.federal_tax_withheld or 0)
        state_withheld = float(w2.state_tax_withheld or 0)
        ss_tax = float(w2.social_security_tax or 0)
        medicare_tax = float(w2.medicare_tax or 0)
        
        total_w2_wages += wages
        total_federal_withheld += federal_withheld
        total_state_withheld += state_withheld
        total_social_security += ss_tax
        total_medicare += medicare_tax
        
        w2_breakdown.append({
            "employee_name": w2.employee_name,
            "employer": w2.employer,
            "wages": wages,
            "federal_withheld": federal_withheld,
            "state_withheld": state_withheld,
        })
    
    income["w2_income"] = {
        "total_wages": total_w2_wages,
        "federal_withheld": total_federal_withheld,
        "state_withheld": total_state_withheld,
        "social_security": total_social_security,
        "medicare": total_medicare,
        "breakdown": w2_breakdown
    }
    
    # Get investment income
    investment_summary = db_queries.get_income_summary(db, year=year)
    income["options_income"] = investment_summary.get("options_income", 0)
    income["dividend_income"] = investment_summary.get("dividend_income", 0)
    income["interest_income"] = investment_summary.get("interest_income", 0)
    
    # Get rental income for the forecast year
    rental_service = get_rental_service()
    rental_summary = rental_service.get_rental_summary()
    
    # Filter rental data for the forecast year
    year_rental_income = 0
    if rental_summary.get("properties"):
        for prop in rental_summary["properties"]:
            # Check if property has data for the forecast year
            if prop.get("year") == year:
                year_rental_income += prop.get("net_income", 0)
            # Also check monthly income for the year
            elif prop.get("monthly_income"):
                for month_data in prop["monthly_income"]:
                    if month_data.get("year") == year:
                        year_rental_income += month_data.get("amount", 0)
    
    income["rental_income"] = year_rental_income
    
    return income


def _calculate_agi(income: Dict[str, Any]) -> float:
    """Calculate Adjusted Gross Income from income sources."""
    agi = 0
    
    # W-2 wages
    agi += income["w2_income"].get("total_wages", 0)
    
    # Investment income (options, dividends, interest)
    agi += income.get("options_income", 0)
    agi += income.get("dividend_income", 0)
    agi += income.get("interest_income", 0)
    
    # Rental income (net after expenses and depreciation)
    agi += income.get("rental_income", 0)
    
    return agi


def _calculate_taxable_income(
    agi: float,
    deductions: Dict[str, Any],
    year: int
) -> float:
    """Calculate taxable income after deductions."""
    # Standard deduction amounts (Married Filing Jointly)
    standard_deductions = {
        2025: 30800,  # Estimated - adjust when official
        2024: 29200,
        2023: 27700,
    }
    
    standard_deduction = standard_deductions.get(year, 29200)
    itemized_total = deductions.get("itemized_total", 0)
    
    # Use the larger of standard or itemized
    deduction = max(standard_deduction, itemized_total) if itemized_total > 0 else standard_deduction
    
    taxable_income = max(0, agi - deduction)
    return taxable_income


def _calculate_federal_tax(
    taxable_income: float,
    filing_status: str,
    year: int
) -> float:
    """
    Calculate federal income tax using tax brackets.
    Simplified calculation - uses 2024 brackets for 2025 (adjust when 2025 brackets are official).
    """
    # 2024 Tax Brackets (Married Filing Jointly)
    # Using 2024 brackets as estimate for 2025
    brackets = [
        (0, 0.10),
        (23200, 0.12),
        (94300, 0.22),
        (201050, 0.24),
        (383900, 0.32),
        (487050, 0.35),
        (731200, 0.37),
    ]
    
    # Single brackets (if needed)
    if filing_status == "Single":
        brackets = [
            (0, 0.10),
            (11600, 0.12),
            (47150, 0.22),
            (100525, 0.24),
            (191950, 0.32),
            (243725, 0.35),
            (609350, 0.37),
        ]
    
    tax = 0.0
    remaining_income = taxable_income
    
    for i in range(len(brackets)):
        bracket_start, rate = brackets[i]
        bracket_end = brackets[i + 1][0] if i + 1 < len(brackets) else float('inf')
        
        if remaining_income <= 0:
            break
        
        if taxable_income > bracket_start:
            bracket_income = min(remaining_income, bracket_end - bracket_start)
            tax += bracket_income * rate
            remaining_income -= bracket_income
    
    return tax


def _calculate_ca_state_tax(
    taxable_income: float,
    filing_status: str,
    year: int
) -> float:
    """
    Calculate California state income tax.
    Using 2024 brackets as estimate for 2025.
    """
    # 2024 California Tax Brackets (Married Filing Jointly)
    brackets = [
        (0, 0.01),
        (20298, 0.02),
        (48042, 0.04),
        (61214, 0.06),
        (76364, 0.08),
        (101710, 0.093),
        (610404, 0.103),
        (732546, 0.113),
        (1227424, 0.123),
    ]
    
    # Single brackets
    if filing_status == "Single":
        brackets = [
            (0, 0.01),
            (10149, 0.02),
            (24021, 0.04),
            (30607, 0.06),
            (38182, 0.08),
            (50855, 0.093),
            (305202, 0.103),
            (366273, 0.113),
            (613712, 0.123),
        ]
    
    tax = 0.0
    remaining_income = taxable_income
    
    for i in range(len(brackets)):
        bracket_start, rate = brackets[i]
        bracket_end = brackets[i + 1][0] if i + 1 < len(brackets) else float('inf')
        
        if remaining_income <= 0:
            break
        
        if taxable_income > bracket_start:
            bracket_income = min(remaining_income, bracket_end - bracket_start)
            tax += bracket_income * rate
            remaining_income -= bracket_income
    
    return tax


def _calculate_other_taxes(
    income: Dict[str, Any],
    agi: float,
    base_details: Dict[str, Any]
) -> float:
    """Calculate other taxes: payroll taxes, NIIT, etc."""
    other_tax = 0
    
    # Payroll taxes (already withheld, but included in "other" category)
    w2_data = income.get("w2_income", {})
    other_tax += w2_data.get("social_security", 0)
    other_tax += w2_data.get("medicare", 0)
    
    # NIIT (Net Investment Income Tax) - 3.8% on investment income above threshold
    # Threshold: $250,000 for MFJ, $200,000 for Single
    niit_threshold = 250000  # MFJ default
    investment_income = (
        income.get("options_income", 0) +
        income.get("dividend_income", 0) +
        income.get("interest_income", 0)
    )
    
    if agi > niit_threshold and investment_income > 0:
        niit_base = min(investment_income, agi - niit_threshold)
        niit = niit_base * 0.038
        other_tax += niit
    else:
        niit = 0
    
    return other_tax


def _build_forecast_details(
    income: Dict[str, Any],
    deductions: Dict[str, Any],
    base_details: Dict[str, Any],
    year: int
) -> Dict[str, Any]:
    """Build the details JSON structure for the forecast."""
    details = {
        "income_sources": [],
        "w2_breakdown": [],
        "deductions": deductions.copy(),
        "payroll_taxes": [],
        "additional_taxes": {},
    }
    
    # Income sources
    if income["w2_income"].get("total_wages", 0) > 0:
        details["income_sources"].append({
            "source": "W-2 Wages",
            "amount": income["w2_income"]["total_wages"]
        })
    
    if income.get("rental_income", 0) > 0:
        details["income_sources"].append({
            "source": "Rental Income",
            "amount": income["rental_income"]
        })
    
    if income.get("options_income", 0) > 0:
        details["income_sources"].append({
            "source": "Options Income",
            "amount": income["options_income"]
        })
    
    if income.get("dividend_income", 0) > 0:
        details["income_sources"].append({
            "source": "Dividend Income",
            "amount": income["dividend_income"]
        })
    
    if income.get("interest_income", 0) > 0:
        details["income_sources"].append({
            "source": "Interest Income",
            "amount": income["interest_income"]
        })
    
    # W-2 breakdown
    details["w2_breakdown"] = income["w2_income"].get("breakdown", [])
    
    # Payroll taxes
    w2_data = income.get("w2_income", {})
    if w2_data.get("social_security", 0) > 0 or w2_data.get("medicare", 0) > 0:
        details["payroll_taxes"].append({
            "employer": "Combined",
            "social_security": w2_data.get("social_security", 0),
            "medicare": w2_data.get("medicare", 0),
        })
    
    # Additional taxes (NIIT)
    investment_income = (
        income.get("options_income", 0) +
        income.get("dividend_income", 0) +
        income.get("interest_income", 0)
    )
    
    agi = _calculate_agi(income)
    niit_threshold = 250000
    if agi > niit_threshold and investment_income > 0:
        niit_base = min(investment_income, agi - niit_threshold)
        niit = niit_base * 0.038
        details["additional_taxes"]["niit"] = niit
    
    # Copy rental properties from base if available
    if base_details.get("rental_properties"):
        details["rental_properties"] = base_details["rental_properties"]
    
    return details

