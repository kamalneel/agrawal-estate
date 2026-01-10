"""
Tax Form Generator

Generates official IRS Form 1040 and California Form 540 from tax forecast data.
"""

from typing import Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from app.modules.tax.forms import (
    Form1040, Schedule1, ScheduleE, ScheduleD,
    CaliforniaForm540, TaxFormPackage
)
from app.modules.tax.forecast import calculate_tax_forecast
from app.modules.tax.models import IncomeTaxReturn


def generate_tax_forms(
    db: Session,
    tax_year: int = 2025,
    base_year: int = 2024
) -> TaxFormPackage:
    """
    Generate complete tax form package from forecast data.

    Args:
        db: Database session
        tax_year: Year to generate forms for
        base_year: Base year for comparison

    Returns:
        TaxFormPackage with Form 1040, CA 540, and supporting schedules
    """
    # Get tax forecast
    forecast = calculate_tax_forecast(db, forecast_year=tax_year, base_year=base_year)

    # Get base year return for reference
    base_return = db.query(IncomeTaxReturn).filter(
        IncomeTaxReturn.tax_year == base_year
    ).first()

    # Generate Form 1040
    form_1040 = _generate_form_1040(forecast, base_return)

    # Generate Schedule 1 (Additional Income and Adjustments)
    schedule_1 = _generate_schedule_1(forecast)

    # Generate Schedule E (Rental Income) if applicable
    schedule_e = None
    if forecast.get("details", {}).get("rental_properties"):
        schedule_e = _generate_schedule_e(forecast)

    # Generate Schedule D (Capital Gains) if applicable
    schedule_d = None
    cap_gains = forecast.get("details", {}).get("capital_gains")
    if cap_gains and (cap_gains.get("short_term") or cap_gains.get("long_term")):
        schedule_d = _generate_schedule_d(forecast)

    # Generate California Form 540
    california_540 = _generate_california_540(forecast, base_return)

    # Build notes
    notes = [
        f"Tax forecast for {tax_year} based on {base_year} patterns",
        f"Generated on {datetime.now().strftime('%Y-%m-%d')}",
        "This is a FORECAST for comparison purposes only",
        "Not an official tax return - consult with tax professional"
    ]

    if forecast.get("details", {}).get("capital_gains", {}).get("note"):
        notes.append(forecast["details"]["capital_gains"]["note"])

    return TaxFormPackage(
        form_1040=form_1040,
        schedule_1=schedule_1,
        schedule_e=schedule_e,
        schedule_d=schedule_d,
        california_540=california_540,
        is_forecast=True,
        generation_date=datetime.now().isoformat(),
        notes=notes
    )


def _generate_form_1040(forecast: Dict[str, Any], base_return: IncomeTaxReturn) -> Form1040:
    """Generate IRS Form 1040 from forecast data."""

    details = forecast.get("details", {})
    income_sources = {item["source"]: item["amount"] for item in details.get("income_sources", [])}
    w2_breakdown = details.get("w2_breakdown", [])
    cap_gains_detail = details.get("capital_gains", {})
    deductions = details.get("deductions", {})

    # Calculate W-2 wages
    total_wages = sum(w2.get("wages", 0) for w2 in w2_breakdown)
    total_federal_withheld = sum(w2.get("federal_withheld", 0) for w2 in w2_breakdown)

    # Get capital gains
    capital_gain_loss = cap_gains_detail.get("total", 0)

    # Schedule 1 income (rental from Schedule E)
    schedule_1_income = income_sources.get("Rental Income", 0)

    # Calculate total income
    wages = total_wages
    interest = income_sources.get("Interest Income", 0)
    dividends = income_sources.get("Dividend Income", 0)
    capital_gains = capital_gain_loss
    schedule1_additional = schedule_1_income

    total_income = wages + interest + dividends + capital_gains + schedule1_additional

    # Adjustments to income (from Schedule 1 Part II)
    # IRA deduction and HSA contributions
    retirement = forecast.get("details", {}).get("retirement_contributions", {})
    ira_deduction = retirement.get("ira_deduction", 0) if isinstance(retirement, dict) else 0
    hsa_contribution = retirement.get("hsa_contribution", 0) if isinstance(retirement, dict) else 0
    total_adjustments = ira_deduction + hsa_contribution

    # AGI
    agi = forecast.get("agi", 0)

    # Deductions
    standard_deduction = 31500  # 2025 MFJ
    itemized_deduction = deductions.get("itemized_total", 0)
    deduction_amount = max(standard_deduction, itemized_deduction)
    deduction_type = "itemized" if itemized_deduction > standard_deduction else "standard"

    # Taxable income
    taxable_income = forecast.get("details", {}).get("taxable_income", 0) or max(0, agi - deduction_amount)

    # Tax
    federal_tax = forecast.get("federal_tax", 0)

    # Other taxes
    additional_taxes_dict = details.get("additional_taxes", {})
    niit = additional_taxes_dict.get("niit", 0) if isinstance(additional_taxes_dict, dict) else 0

    # Payroll taxes
    payroll = details.get("payroll_taxes", [])
    social_security = sum(p.get("social_security", 0) for p in payroll) if payroll else 0
    medicare = sum(p.get("medicare", 0) for p in payroll) if payroll else 0

    # Total tax
    total_tax = forecast.get("total_tax", 0)

    # Calculate refund or amount owed
    total_payments = total_federal_withheld
    overpayment = max(0, total_payments - total_tax)
    amount_owed = max(0, total_tax - total_payments)

    # Determine filing status name
    filing_status_map = {
        "MFJ": "Married filing jointly",
        "Single": "Single",
        "HOH": "Head of household",
        "MFS": "Married filing separately"
    }
    filing_status = filing_status_map.get(forecast.get("filing_status", "MFJ"), "Married filing jointly")

    return Form1040(
        tax_year=forecast.get("tax_year", 2025),
        filing_status=filing_status,
        taxpayer_name="Neel Agrawal",
        spouse_name="Jaya Agrawal",

        # Income (Lines 1-9)
        line_1a=wages,
        line_1z=wages,
        line_2a=0,  # Tax-exempt interest
        line_2b=interest,  # Taxable interest
        line_3a=dividends,  # Assume all dividends are ordinary for now
        line_3b=dividends,
        line_7=capital_gains,  # Capital gain/loss from Schedule D
        line_8=schedule1_additional,  # From Schedule 1
        line_9=total_income,

        # Adjustments (Lines 10-11)
        line_10=total_adjustments,  # From Schedule 1
        line_11=agi,

        # Deductions (Lines 12-15)
        line_12=deduction_amount,
        line_12_type=deduction_type,
        line_13=0,  # Qualified business income deduction
        line_14=deduction_amount,
        line_15=taxable_income,

        # Tax and Credits (Lines 16-24)
        line_16=federal_tax,
        line_17=niit + social_security + medicare,  # Additional taxes
        line_18=federal_tax + niit + social_security + medicare,
        line_19=0,  # Child tax credit
        line_20=0,  # Other credits
        line_21=0,
        line_22=federal_tax + niit + social_security + medicare,
        line_23=0,  # Other taxes
        line_24=total_tax,

        # Payments (Lines 25-33)
        line_25a=total_federal_withheld,
        line_25d=total_federal_withheld,
        line_32=total_payments,
        line_33=overpayment,

        # Refund or Amount Owed
        line_34=overpayment if overpayment > 0 else 0,
        line_36=amount_owed if amount_owed > 0 else 0,
        line_38=amount_owed if amount_owed > 0 else 0,
    )


def _generate_schedule_1(forecast: Dict[str, Any]) -> Schedule1:
    """Generate Schedule 1 - Additional Income and Adjustments."""

    details = forecast.get("details", {})
    income_sources = {item["source"]: item["amount"] for item in details.get("income_sources", [])}

    # Rental income goes on Schedule E, which flows to Schedule 1 line 5
    rental_income = income_sources.get("Rental Income", 0)

    # Options income (treated as other income)
    options_income = income_sources.get("Options Income", 0)

    # Retirement contributions
    retirement = details.get("retirement_contributions", {}) if isinstance(details.get("retirement_contributions"), dict) else {}
    ira_deduction = retirement.get("ira_deduction", 0)
    hsa_contribution = retirement.get("hsa_contribution", 0)

    # Total additional income
    total_additional_income = rental_income

    # Total adjustments
    total_adjustments = ira_deduction + hsa_contribution

    return Schedule1(
        line_5=rental_income,  # Rental income from Schedule E
        line_8=options_income,  # Options income as "other income"
        line_10=total_additional_income + options_income,

        line_13=hsa_contribution,  # HSA deduction
        line_20=ira_deduction,  # IRA deduction
        line_25=total_adjustments,
        line_26=total_adjustments,
    )


def _generate_schedule_e(forecast: Dict[str, Any]) -> ScheduleE:
    """Generate Schedule E - Rental Real Estate Income."""

    details = forecast.get("details", {})
    rental_properties = details.get("rental_properties", [])
    income_sources = {item["source"]: item["amount"] for item in details.get("income_sources", [])}

    rental_net_income = income_sources.get("Rental Income", 0)

    # Use first rental property if available
    if rental_properties and len(rental_properties) > 0:
        prop = rental_properties[0]
        address = prop.get("address", "Rental Property")
        gross_income = prop.get("income", 0)
        total_expenses = prop.get("expenses", 0)
        depreciation = prop.get("depreciation", 0)
    else:
        address = "Rental Property"
        gross_income = 0
        total_expenses = 0
        depreciation = 0

    return ScheduleE(
        property_address=address,
        line_3=gross_income,
        line_18=depreciation,
        line_20=total_expenses,
        line_21=rental_net_income,
        line_26=rental_net_income,
    )


def _generate_schedule_d(forecast: Dict[str, Any]) -> ScheduleD:
    """Generate Schedule D - Capital Gains and Losses."""

    details = forecast.get("details", {})
    cap_gains = details.get("capital_gains", {})

    short_term = cap_gains.get("short_term", 0)
    long_term = cap_gains.get("long_term", 0)
    total = cap_gains.get("total", 0)

    return ScheduleD(
        # Short-term
        line_1a=short_term,
        line_7=short_term,

        # Long-term
        line_8a=long_term,
        line_15=long_term,

        # Summary
        line_16=total,
        line_17=total > 0,
        line_20=total if total > 0 else 0,
        line_21=abs(total) if total < 0 else 0,
    )


def _generate_california_540(
    forecast: Dict[str, Any],
    base_return: IncomeTaxReturn
) -> CaliforniaForm540:
    """Generate California Form 540 from forecast data."""

    details = forecast.get("details", {})
    income_sources = {item["source"]: item["amount"] for item in details.get("income_sources", [])}
    w2_breakdown = details.get("w2_breakdown", [])
    cap_gains_detail = details.get("capital_gains", {})
    deductions = details.get("deductions", {})

    # Income
    wages = sum(w2.get("wages", 0) for w2 in w2_breakdown)
    interest = income_sources.get("Interest Income", 0)
    dividends = income_sources.get("Dividend Income", 0)
    capital_gains = cap_gains_detail.get("total", 0)
    rental_income = income_sources.get("Rental Income", 0)

    total_income = wages + interest + dividends + capital_gains + rental_income

    # AGI (California generally follows federal AGI)
    agi = forecast.get("agi", 0)

    # Standard deduction for California (MFJ 2025)
    ca_standard_deduction = 11080
    itemized_deduction = deductions.get("itemized_total", 0)
    deduction_amount = max(ca_standard_deduction, itemized_deduction)
    deduction_type = "itemized" if itemized_deduction > ca_standard_deduction else "standard"

    # Exemptions (California doesn't have personal exemptions as of 2025)
    exemptions = 0

    # Taxable income
    taxable_income = max(0, agi - deduction_amount - exemptions)

    # Tax
    state_tax = forecast.get("state_tax", 0)

    # Mental Health Services Tax (1% on income > $1M)
    mental_health_tax = 0
    if taxable_income > 1000000:
        mental_health_tax = (taxable_income - 1000000) * 0.01

    total_ca_tax = state_tax

    # Withholding
    total_state_withheld = sum(w2.get("state_withheld", 0) for w2 in w2_breakdown)

    # Calculate refund or amount owed
    overpayment = max(0, total_state_withheld - total_ca_tax)
    amount_owed = max(0, total_ca_tax - total_state_withheld)

    # Filing status
    filing_status_map = {
        "MFJ": "Married/RDP filing jointly",
        "Single": "Single",
        "HOH": "Head of household",
        "MFS": "Married/RDP filing separately"
    }
    filing_status = filing_status_map.get(forecast.get("filing_status", "MFJ"), "Married/RDP filing jointly")

    return CaliforniaForm540(
        tax_year=forecast.get("tax_year", 2025),
        filing_status=filing_status,
        taxpayer_name="Neel Agrawal",
        spouse_name="Jaya Agrawal",

        # Income
        line_11=wages,
        line_12=interest,
        line_13=dividends,
        line_16=capital_gains,
        line_17=rental_income,
        line_20=total_income,

        # AGI
        line_22=agi,

        # Deductions
        line_23=deduction_amount,
        line_23_type=deduction_type,
        line_24=exemptions,
        line_25=taxable_income,

        # Tax
        line_31=state_tax - mental_health_tax if mental_health_tax > 0 else state_tax,
        line_33=mental_health_tax,
        line_34=state_tax,
        line_36=state_tax,
        line_38=total_ca_tax,

        # Payments
        line_41=total_state_withheld,
        line_44=total_state_withheld,

        # Refund or Owed
        line_45=overpayment,
        line_46=overpayment,
        line_47=amount_owed,
        line_49=amount_owed,
    )
