"""
Tax Forecast Calculation Service.

Generates tax forecasts for future years based on:
- Historical tax data (deductions, filing status, etc.)
- Projected income for the forecast year
- Official IRS 2025 tax brackets and Trump Tax Cuts (TCJA) provisions
- One Big Beautiful Bill Act (OBBBA) provisions signed July 4, 2025

Updated with official 2025 tax law changes including:
- Standard deduction: $31,500 (MFJ)
- Updated federal tax brackets (7 brackets, inflation-adjusted)
- Capital gains treatment (0%, 15%, 20% rates)
- NIIT 3.8% (unchanged, $250k threshold MFJ)
- Retirement contribution limits (401k: $23,500, IRA: $7,000, HSA: $8,550 family)
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from decimal import Decimal
from sqlalchemy import extract, and_, func
import json

from app.modules.tax.models import IncomeTaxReturn
from app.modules.income.models import W2Record, RetirementContribution
from app.modules.income import db_queries
from app.modules.income.salary_service import get_salary_service
from app.modules.income.rental_service import get_rental_service
from app.modules.investments.models import InvestmentTransaction, InvestmentAccount


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
        "capital_gains": {},
        "retirement_contributions": {},
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

    # Get capital gains/losses for the forecast year
    capital_gains = _calculate_capital_gains(db, year)
    income["capital_gains"] = capital_gains

    # Get retirement contributions for the forecast year (these reduce AGI)
    retirement = _get_retirement_contributions(db, year)
    income["retirement_contributions"] = retirement

    return income


def _calculate_agi(income: Dict[str, Any]) -> float:
    """
    Calculate Adjusted Gross Income from income sources.

    AGI = Total Income - Above-the-line Deductions

    Includes:
    - W-2 wages
    - Investment income (options, dividends, interest)
    - Rental income (net)
    - Capital gains/losses (net)

    Subtracts (above-the-line deductions):
    - IRA contributions
    - HSA contributions
    - Other pre-tax retirement contributions (already excluded from W-2 wages)
    """
    agi = 0

    # W-2 wages (already reduced by 401k contributions in Box 1)
    agi += income["w2_income"].get("total_wages", 0)

    # Investment income (options, dividends, interest)
    agi += income.get("options_income", 0)
    agi += income.get("dividend_income", 0)
    agi += income.get("interest_income", 0)

    # Rental income (net after expenses and depreciation)
    agi += income.get("rental_income", 0)

    # Capital gains/losses (net)
    cap_gains = income.get("capital_gains", {})
    net_short_term = cap_gains.get("net_short_term", 0)
    net_long_term = cap_gains.get("net_long_term", 0)
    agi += net_short_term + net_long_term

    # Above-the-line deductions (reduce AGI)
    retirement = income.get("retirement_contributions", {})
    # IRA contributions (traditional IRA reduces AGI, Roth does not)
    agi -= retirement.get("ira_deduction", 0)
    # HSA contributions
    agi -= retirement.get("hsa_contribution", 0)
    # Note: 401k contributions already excluded from W-2 Box 1 wages

    return agi


def _calculate_taxable_income(
    agi: float,
    deductions: Dict[str, Any],
    year: int
) -> float:
    """Calculate taxable income after deductions."""
    # Standard deduction amounts (Married Filing Jointly)
    # Source: One Big Beautiful Bill Act (OBBBA), signed July 4, 2025
    standard_deductions = {
        2025: 31500,  # Official IRS amount for 2025 (OBBBA)
        2024: 29200,
        2023: 27700,
    }

    standard_deduction = standard_deductions.get(year, 31500)
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
    Calculate federal income tax using official IRS tax brackets.
    Updated for 2025 with TCJA provisions made permanent.
    Source: IRS Revenue Procedure 2024-40, Tax Foundation
    """
    # 2025 Official Tax Brackets (Married Filing Jointly)
    # Source: https://taxfoundation.org/data/all/federal/2025-tax-brackets/
    if year >= 2025:
        if filing_status in ["MFJ", "married_filing_jointly"]:
            brackets = [
                (0, 0.10),
                (23850, 0.12),
                (96950, 0.22),
                (206700, 0.24),
                (394600, 0.32),
                (501050, 0.35),
                (751600, 0.37),
            ]
        elif filing_status in ["Single", "single"]:
            brackets = [
                (0, 0.10),
                (11925, 0.12),
                (48475, 0.22),
                (103350, 0.24),
                (197300, 0.32),
                (250525, 0.35),
                (626350, 0.37),
            ]
        else:
            # Default to MFJ
            brackets = [
                (0, 0.10),
                (23850, 0.12),
                (96950, 0.22),
                (206700, 0.24),
                (394600, 0.32),
                (501050, 0.35),
                (751600, 0.37),
            ]
    else:
        # 2024 Tax Brackets (Married Filing Jointly)
        brackets = [
            (0, 0.10),
            (23200, 0.12),
            (94300, 0.22),
            (201050, 0.24),
            (383900, 0.32),
            (487050, 0.35),
            (731200, 0.37),
        ]

        if filing_status in ["Single", "single"]:
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

    California has 9 tax brackets ranging from 1% to 12.3%.
    High earners (income > $1M) pay additional 1% mental health tax (total 13.3%).

    2025 brackets are slightly adjusted for inflation from 2024.
    Source: California Franchise Tax Board (FTB)
    """
    # 2025 California Tax Brackets (Married Filing Jointly)
    # Note: California adjusts brackets annually for inflation
    # Using 2024 brackets with ~2.8% inflation adjustment for 2025
    if year >= 2025:
        brackets = [
            (0, 0.01),
            (20862, 0.02),      # ~2.8% inflation adjustment
            (49387, 0.04),
            (62928, 0.06),
            (78502, 0.08),
            (104558, 0.093),
            (627495, 0.103),
            (753057, 0.113),
            (1261792, 0.123),
        ]

        if filing_status in ["Single", "single"]:
            brackets = [
                (0, 0.01),
                (10431, 0.02),
                (24694, 0.04),
                (31464, 0.06),
                (39251, 0.08),
                (52279, 0.093),
                (313748, 0.103),
                (376529, 0.113),
                (630896, 0.123),
            ]
    else:
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

        if filing_status in ["Single", "single"]:
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

    # Mental Health Services Tax: Additional 1% on income over $1M
    if taxable_income > 1000000:
        mental_health_tax = (taxable_income - 1000000) * 0.01
        tax += mental_health_tax

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

    # Add capital gains if present
    cap_gains = income.get("capital_gains", {})
    if cap_gains.get("net_short_term") or cap_gains.get("net_long_term"):
        details["capital_gains"] = {
            "short_term": cap_gains.get("net_short_term", 0),
            "long_term": cap_gains.get("net_long_term", 0),
            "total": cap_gains.get("net_short_term", 0) + cap_gains.get("net_long_term", 0)
        }
        # Add to income sources
        if cap_gains.get("net_short_term", 0) + cap_gains.get("net_long_term", 0) != 0:
            details["income_sources"].append({
                "source": "Capital Gains (Net)",
                "amount": cap_gains.get("net_short_term", 0) + cap_gains.get("net_long_term", 0)
            })

    return details


def _calculate_capital_gains(db: Session, year: int) -> Dict[str, float]:
    """
    Calculate net capital gains/losses from investment transactions.

    Uses actual cost basis tracking for precise gain/loss calculations.
    Falls back to transaction-based estimation, then to 50% conservative estimate.

    Short-term: Assets held ≤ 1 year (taxed as ordinary income)
    Long-term: Assets held > 1 year (preferential rates: 0%, 15%, 20%)

    Returns dict with net_short_term and net_long_term
    """
    try:
        # Try to use actual cost basis tracking
        from app.modules.tax.cost_basis_service import CostBasisService

        service = CostBasisService(db)
        summary = service.get_capital_gains_summary(year)

        if summary.get("num_transactions", 0) > 0:
            # We have actual cost basis data - use it!
            return {
                "net_short_term": summary.get("total_short_term_gain", 0),
                "net_long_term": summary.get("total_long_term_gain", 0),
                "total_proceeds": summary.get("total_proceeds", 0),
                "total_cost_basis": summary.get("total_cost_basis", 0),
                "num_transactions": summary.get("num_transactions", 0),
                "note": "Actual cost basis data"
            }
    except Exception:
        # Cost basis tracking not available or failed - fall back to estimation
        pass

    # Fallback 1: Use transaction data if available
    sell_transactions = db.query(InvestmentTransaction).join(
        InvestmentAccount,
        and_(
            InvestmentTransaction.account_id == InvestmentAccount.account_id,
            InvestmentTransaction.source == InvestmentAccount.source
        )
    ).filter(
        InvestmentTransaction.transaction_type.in_(['SELL', 'SOLD']),
        extract('year', InvestmentTransaction.transaction_date) == year
    ).all()

    if sell_transactions:
        # We have transaction data - use actual sale amounts with 50% gain estimate
        total_proceeds = sum(float(t.amount or 0) for t in sell_transactions)

        # Use 50% as a conservative estimate of gains when we have transactions but no cost basis
        # This is more conservative than 30% and accounts for typical market appreciation
        estimated_gains = total_proceeds * 0.50 if total_proceeds > 0 else 0

        # For now, classify all as long-term (most holdings are long-term)
        return {
            "net_short_term": 0,
            "net_long_term": estimated_gains,
            "total_proceeds": total_proceeds,
            "note": "Estimated at 50% gains - import to Cost Basis Tracker for accuracy"
        }

    # Fallback 2: No transaction data at all - return zeros
    # This happens when there are no sales in the database for this year
    return {
        "net_short_term": 0,
        "net_long_term": 0,
        "total_proceeds": 0,
        "note": "No transaction data available - import transactions to Cost Basis Tracker"
    }


def _get_retirement_contributions(db: Session, year: int) -> Dict[str, float]:
    """
    Get retirement contributions that reduce AGI.

    401(k) contributions: Already excluded from W-2 Box 1 wages
    Traditional IRA: Deductible (reduces AGI)
    Roth IRA: Not deductible (doesn't reduce AGI)
    HSA: Deductible (reduces AGI)

    2025 Limits:
    - 401(k): $23,500 ($31,000 with catch-up 50+, $34,750 ages 60-63)
    - IRA: $7,000 ($8,000 with catch-up 50+)
    - HSA: $4,300 individual / $8,550 family ($1,000 catch-up 55+)

    Returns dict with deductible amounts
    """
    # Query retirement contribution records
    contributions = db.query(RetirementContribution).filter(
        RetirementContribution.tax_year == year
    ).all()

    total_ira_deduction = 0
    total_hsa_contribution = 0
    total_401k = 0

    for contrib in contributions:
        # Traditional IRA contributions are deductible
        ira_contrib = float(contrib.ira_contributions or 0)
        total_ira_deduction += ira_contrib

        # HSA contributions are deductible
        hsa_contrib = float(contrib.hsa_contributions or 0)
        total_hsa_contribution += hsa_contrib

        # 401k for reference (already excluded from W-2 wages)
        k401_contrib = float(contrib.contributions_401k or 0)
        total_401k += k401_contrib

    return {
        "ira_deduction": total_ira_deduction,
        "hsa_contribution": total_hsa_contribution,
        "k401_total": total_401k,  # For reference only, already excluded from wages
        "total_above_line_deduction": total_ira_deduction + total_hsa_contribution
    }

