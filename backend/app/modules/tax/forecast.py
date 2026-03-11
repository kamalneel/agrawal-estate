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

from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from decimal import Decimal
from sqlalchemy import extract, and_, func
from datetime import date
import json

from app.modules.tax.models import IncomeTaxReturn, EstimatedTaxPayment
from app.modules.income.models import W2Record, RetirementContribution, TaxDependent
from app.modules.income import db_queries
from app.modules.income.salary_service import get_salary_service
from app.modules.income.rental_service import get_rental_service
from app.modules.investments.models import InvestmentTransaction, InvestmentAccount


# IRS Quarterly Estimated Tax Payment Schedule
# These are the due dates for estimated tax payments
QUARTERLY_PAYMENT_SCHEDULE = {
    # Tax Year 2025: Payments due during 2025 and early 2026
    2025: [
        {"quarter": 1, "period": "Jan 1 - Mar 31, 2025", "due_date": date(2025, 4, 15), "months": [1, 2, 3]},
        {"quarter": 2, "period": "Apr 1 - May 31, 2025", "due_date": date(2025, 6, 16), "months": [4, 5]},  # June 15 is Sunday
        {"quarter": 3, "period": "Jun 1 - Aug 31, 2025", "due_date": date(2025, 9, 15), "months": [6, 7, 8]},
        {"quarter": 4, "period": "Sep 1 - Dec 31, 2025", "due_date": date(2026, 1, 15), "months": [9, 10, 11, 12]},
    ],
    # Tax Year 2026: Payments due during 2026 and early 2027
    2026: [
        {"quarter": 1, "period": "Jan 1 - Mar 31, 2026", "due_date": date(2026, 4, 15), "months": [1, 2, 3]},
        {"quarter": 2, "period": "Apr 1 - May 31, 2026", "due_date": date(2026, 6, 15), "months": [4, 5]},
        {"quarter": 3, "period": "Jun 1 - Aug 31, 2026", "due_date": date(2026, 9, 15), "months": [6, 7, 8]},
        {"quarter": 4, "period": "Sep 1 - Dec 31, 2026", "due_date": date(2027, 1, 15), "months": [9, 10, 11, 12]},
    ],
    # Tax Year 2027: For future years
    2027: [
        {"quarter": 1, "period": "Jan 1 - Mar 31, 2027", "due_date": date(2027, 4, 15), "months": [1, 2, 3]},
        {"quarter": 2, "period": "Apr 1 - May 31, 2027", "due_date": date(2027, 6, 15), "months": [4, 5]},
        {"quarter": 3, "period": "Jun 1 - Aug 31, 2027", "due_date": date(2027, 9, 15), "months": [6, 7, 8]},
        {"quarter": 4, "period": "Sep 1 - Dec 31, 2027", "due_date": date(2028, 1, 15), "months": [9, 10, 11, 12]},
    ],
}


def _calculate_underpayment_penalty(
    payment_schedule: List[Dict[str, Any]],
    federal_safe_harbor: float,
    state_safe_harbor: float,
    prior_federal_tax: float,
    prior_state_tax: float,
    current_federal_tax: float,
    current_state_tax: float,
    year: int
) -> Dict[str, Any]:
    """
    Calculate underpayment penalty for federal and state taxes.

    IRS Form 2210 / CA Form 5805 methodology:
    - Required payment each quarter is 25% of safe harbor amount (cumulative)
    - Penalty is calculated on underpayment from due date to payment date
    - Interest rate: 7% annually for federal (2025), similar for CA
    """
    # Interest rates for 2025 (annual)
    FEDERAL_RATE = 0.07  # 7% for 2025
    CA_RATE = 0.07  # California uses similar rates

    # Required cumulative payments by quarter (25%, 50%, 75%, 100%)
    quarterly_percentages = [0.25, 0.50, 0.75, 1.00]

    federal_quarters = []
    state_quarters = []
    total_federal_penalty = 0
    total_state_penalty = 0

    cumulative_fed_paid = 0
    cumulative_state_paid = 0

    for i, payment in enumerate(payment_schedule):
        quarter = payment["quarter"]
        due_date = date.fromisoformat(payment["due_date"])

        # Required cumulative payment by this quarter
        fed_required = federal_safe_harbor * quarterly_percentages[i]
        state_required = state_safe_harbor * quarterly_percentages[i]

        # Actual cumulative payment by this quarter
        fed_paid_this_q = (payment.get("quarter_w2_federal", 0) or 0) + (payment.get("est_federal_paid", 0) or 0)
        state_paid_this_q = (payment.get("quarter_w2_state", 0) or 0) + (payment.get("est_state_paid", 0) or 0)
        cumulative_fed_paid += fed_paid_this_q
        cumulative_state_paid += state_paid_this_q

        # Underpayment for this quarter
        fed_underpayment = max(0, fed_required - cumulative_fed_paid)
        state_underpayment = max(0, state_required - cumulative_state_paid)

        # Calculate penalty days (from due date to next due date or April 15)
        # Simplified: assume penalty accrues until April 15 of following year
        april_15_next = date(year + 1, 4, 15)
        if i < 3:
            next_due = date.fromisoformat(payment_schedule[i + 1]["due_date"])
            penalty_days = (next_due - due_date).days
        else:
            penalty_days = (april_15_next - due_date).days

        # Calculate penalty (simple interest for this period)
        fed_penalty = fed_underpayment * (FEDERAL_RATE * penalty_days / 365)
        state_penalty = state_underpayment * (CA_RATE * penalty_days / 365)

        total_federal_penalty += fed_penalty
        total_state_penalty += state_penalty

        federal_quarters.append({
            "quarter": quarter,
            "required": round(fed_required, 2),
            "paid": round(cumulative_fed_paid, 2),
            "underpayment": round(fed_underpayment, 2),
            "penalty": round(fed_penalty, 2),
            "days": penalty_days
        })

        state_quarters.append({
            "quarter": quarter,
            "required": round(state_required, 2),
            "paid": round(cumulative_state_paid, 2),
            "underpayment": round(state_underpayment, 2),
            "penalty": round(state_penalty, 2),
            "days": penalty_days
        })

    # Check if safe harbor was met (no penalty if paid enough)
    total_fed_paid = cumulative_fed_paid
    total_state_paid = cumulative_state_paid

    # Safe harbor check: if paid >= safe harbor, no penalty
    federal_safe_harbor_met = total_fed_paid >= federal_safe_harbor
    state_safe_harbor_met = total_state_paid >= state_safe_harbor

    # Also check: if balance due < $1000, no penalty
    federal_balance_due = max(0, current_federal_tax - total_fed_paid)
    state_balance_due = max(0, current_state_tax - total_state_paid)

    federal_penalty_waived = federal_safe_harbor_met or federal_balance_due < 1000
    state_penalty_waived = state_safe_harbor_met or state_balance_due < 500  # CA threshold is $500

    return {
        "federal": {
            "safe_harbor": round(federal_safe_harbor, 2),
            "safe_harbor_110_prior": round(prior_federal_tax * 1.10, 2),
            "safe_harbor_90_current": round(current_federal_tax * 0.90, 2),
            "total_paid": round(total_fed_paid, 2),
            "safe_harbor_met": federal_safe_harbor_met,
            "balance_due": round(federal_balance_due, 2),
            "penalty_waived": federal_penalty_waived,
            "estimated_penalty": round(total_federal_penalty, 2) if not federal_penalty_waived else 0,
            "quarters": federal_quarters,
            "interest_rate": f"{FEDERAL_RATE * 100:.0f}%"
        },
        "state": {
            "safe_harbor": round(state_safe_harbor, 2),
            "safe_harbor_110_prior": round(prior_state_tax * 1.10, 2),
            "safe_harbor_90_current": round(current_state_tax * 0.90, 2),
            "total_paid": round(total_state_paid, 2),
            "safe_harbor_met": state_safe_harbor_met,
            "balance_due": round(state_balance_due, 2),
            "penalty_waived": state_penalty_waived,
            "estimated_penalty": round(total_state_penalty, 2) if not state_penalty_waived else 0,
            "quarters": state_quarters,
            "interest_rate": f"{CA_RATE * 100:.0f}%"
        },
        "total_estimated_penalty": round(
            (total_federal_penalty if not federal_penalty_waived else 0) +
            (total_state_penalty if not state_penalty_waived else 0), 2
        )
    }


def _get_estimated_payments(db: Session, year: int) -> Dict[str, Any]:
    """
    Get estimated tax payments made for a tax year.

    Returns:
        Dict with federal_payments, state_payments (lists), and totals
    """
    payments = db.query(EstimatedTaxPayment).filter(
        EstimatedTaxPayment.tax_year == year
    ).order_by(EstimatedTaxPayment.payment_date).all()

    federal_payments = []
    state_payments = []
    total_federal_paid = 0
    total_state_paid = 0

    for payment in payments:
        payment_data = {
            "date": payment.payment_date.isoformat() if payment.payment_date else None,
            "amount": float(payment.amount or 0),
            "quarter": payment.quarter,
            "method": payment.payment_method,
            "confirmation": payment.confirmation_number,
            "notes": payment.notes,
        }

        if payment.payment_type == 'federal':
            federal_payments.append(payment_data)
            total_federal_paid += float(payment.amount or 0)
        elif payment.payment_type == 'state':
            payment_data["state_code"] = payment.state_code
            state_payments.append(payment_data)
            total_state_paid += float(payment.amount or 0)

    return {
        "federal_payments": federal_payments,
        "state_payments": state_payments,
        "total_federal_paid": total_federal_paid,
        "total_state_paid": total_state_paid,
        "total_paid": total_federal_paid + total_state_paid,
    }


def _calculate_quarterly_payments(
    total_tax: float,
    federal_tax: float,
    state_tax: float,
    w2_withheld: float,
    federal_withheld: float,
    state_withheld: float,
    income_by_month: Dict[int, float],
    year: int,
    w2_months: int = 10,  # Number of months W2 income was earned (for withholding distribution)
    estimated_payments: Optional[Dict[str, Any]] = None  # Estimated payments already made
) -> List[Dict[str, Any]]:
    """
    Calculate quarterly estimated tax payments based on income timing.
    
    The IRS requires estimated payments for income not subject to withholding.
    California FTB also requires quarterly payments on the same schedule.
    This calculates how much should be paid each quarter based on when income
    was actually received, broken out by federal and state.
    
    Also tracks W2 withholding accumulated through each quarter to show
    how much has already been paid via payroll vs additional estimated payments needed.
    
    Args:
        total_tax: Total estimated tax liability for the year
        federal_tax: Federal tax liability
        state_tax: State (CA) tax liability
        w2_withheld: Total amount withheld from W-2 wages
        federal_withheld: Federal withholding from W-2
        state_withheld: State withholding from W-2
        income_by_month: Dict mapping month number (1-12) to taxable income amount
        year: Tax year
        w2_months: Number of months W2 income was earned (default 10 for Jan-Oct)
    
    Returns:
        List of quarterly payment details with due dates and amounts (federal + state)
    """
    # Get payment schedule for this year (or use 2026 as template for future years)
    schedule_year = year if year in QUARTERLY_PAYMENT_SCHEDULE else 2026
    schedule = QUARTERLY_PAYMENT_SCHEDULE[schedule_year]
    
    # Adjust due dates for the actual tax year if using template
    if year not in QUARTERLY_PAYMENT_SCHEDULE:
        schedule = []
        template = QUARTERLY_PAYMENT_SCHEDULE[2026]
        for q in template:
            new_q = q.copy()
            # Adjust year offsets
            year_offset = year - 2026
            due_year = q["due_date"].year + year_offset
            new_q["due_date"] = date(due_year, q["due_date"].month, q["due_date"].day)
            new_q["period"] = q["period"].replace("2026", str(year)).replace("2027", str(year + 1))
            schedule.append(new_q)
    
    # Calculate total annual income
    total_annual_income = sum(income_by_month.values()) if income_by_month else 0
    
    # Estimate monthly W2 withholding (distributed over w2_months)
    # This allows us to show how much has been withheld through each quarter
    monthly_federal_withheld = federal_withheld / w2_months if w2_months > 0 else 0
    monthly_state_withheld = state_withheld / w2_months if w2_months > 0 else 0
    
    # Amount we need to pay via estimated payments (after W-2 withholding)
    # Break out federal and state separately
    estimated_tax_needed = max(0, total_tax - w2_withheld)
    federal_estimated_needed = max(0, federal_tax - federal_withheld)
    state_estimated_needed = max(0, state_tax - state_withheld)
    
    # If no estimated tax needed, return empty payments
    if estimated_tax_needed <= 0:
        return [{
            "quarter": q["quarter"],
            "period": q["period"],
            "due_date": q["due_date"].isoformat(),
            "income_for_period": 0,
            "cumulative_income": 0,
            "estimated_payment": 0,
            "federal_payment": 0,
            "state_payment": 0,
            "w2_federal_paid": round(federal_withheld),
            "w2_state_paid": round(state_withheld),
            "cumulative_paid": 0,
            "status": "not_required",
            "note": "W-2 withholding covers tax liability"
        } for q in schedule]
    
    # Parse estimated payments by quarter
    estimated_by_quarter = {1: {"federal": 0, "state": 0}, 2: {"federal": 0, "state": 0},
                           3: {"federal": 0, "state": 0}, 4: {"federal": 0, "state": 0}}
    if estimated_payments:
        for fp in estimated_payments.get("federal_payments", []):
            q = fp.get("quarter")
            if q and 1 <= q <= 4:
                estimated_by_quarter[q]["federal"] += fp.get("amount", 0)
        for sp in estimated_payments.get("state_payments", []):
            q = sp.get("quarter")
            if q and 1 <= q <= 4:
                estimated_by_quarter[q]["state"] += sp.get("amount", 0)

    # Calculate quarterly income and payments
    payments = []
    cumulative_income = 0
    cumulative_paid = 0
    cumulative_federal_paid = 0
    cumulative_state_paid = 0
    cumulative_w2_federal = 0
    cumulative_w2_state = 0
    cumulative_est_federal_paid = 0
    cumulative_est_state_paid = 0

    for q in schedule:
        # Calculate income for this quarter's months
        quarter_income = sum(income_by_month.get(m, 0) for m in q["months"])
        cumulative_income += quarter_income
        
        # Calculate W2 withholding for this quarter (assume evenly distributed over w2_months)
        # Count how many months in this quarter had W2 income
        w2_months_in_quarter = sum(1 for m in q["months"] if m <= w2_months)
        quarter_w2_federal = monthly_federal_withheld * w2_months_in_quarter
        quarter_w2_state = monthly_state_withheld * w2_months_in_quarter
        cumulative_w2_federal += quarter_w2_federal
        cumulative_w2_state += quarter_w2_state
        
        # Calculate proportional tax for this quarter based on income received
        if total_annual_income > 0:
            income_ratio = cumulative_income / total_annual_income
            
            # Federal payment (additional estimated payment beyond W2)
            cumulative_federal_due = federal_estimated_needed * income_ratio
            federal_payment = cumulative_federal_due - cumulative_federal_paid
            federal_payment = round(max(0, federal_payment))
            cumulative_federal_paid += federal_payment
            
            # State payment (California FTB - additional beyond W2)
            cumulative_state_due = state_estimated_needed * income_ratio
            state_payment = cumulative_state_due - cumulative_state_paid
            state_payment = round(max(0, state_payment))
            cumulative_state_paid += state_payment
            
            # Total payment
            payment_due = federal_payment + state_payment
        else:
            # If no monthly breakdown, use equal quarterly payments
            federal_payment = round(federal_estimated_needed / 4)
            state_payment = round(state_estimated_needed / 4)
            payment_due = federal_payment + state_payment
            cumulative_federal_paid += federal_payment
            cumulative_state_paid += state_payment
        
        cumulative_paid += payment_due
        
        # Determine payment status based on current date
        today = date.today()
        if q["due_date"] < today:
            status = "past_due"
        elif (q["due_date"] - today).days <= 30:
            status = "due_soon"
        else:
            status = "upcoming"
        
        # Get estimated payments actually made for this quarter
        quarter_num = q["quarter"]
        est_federal_paid = estimated_by_quarter[quarter_num]["federal"]
        est_state_paid = estimated_by_quarter[quarter_num]["state"]
        cumulative_est_federal_paid += est_federal_paid
        cumulative_est_state_paid += est_state_paid

        # Calculate remaining amount due for this quarter (due - paid)
        federal_remaining = max(0, federal_payment - est_federal_paid)
        state_remaining = max(0, state_payment - est_state_paid)

        # Update status based on whether payment has been made
        if est_federal_paid >= federal_payment and est_state_paid >= state_payment:
            status = "paid"
        elif est_federal_paid > 0 or est_state_paid > 0:
            status = "partial" if status == "past_due" else status

        payments.append({
            "quarter": q["quarter"],
            "period": q["period"],
            "due_date": q["due_date"].isoformat(),
            "income_for_period": round(quarter_income, 2),
            "cumulative_income": round(cumulative_income, 2),
            "estimated_payment": payment_due,
            "federal_payment": federal_payment,
            "state_payment": state_payment,
            # Per-quarter W2 withholding (for display)
            "quarter_w2_federal": round(quarter_w2_federal, 2),
            "quarter_w2_state": round(quarter_w2_state, 2),
            # Cumulative W2 withholding (kept for backward compatibility)
            "w2_federal_paid": round(cumulative_w2_federal, 2),
            "w2_state_paid": round(cumulative_w2_state, 2),
            "cumulative_paid": round(cumulative_paid, 2),
            "cumulative_federal_paid": round(cumulative_federal_paid, 2),
            "cumulative_state_paid": round(cumulative_state_paid, 2),
            # Estimated payments actually made for this quarter
            "est_federal_paid": round(est_federal_paid, 2),
            "est_state_paid": round(est_state_paid, 2),
            "cumulative_est_federal_paid": round(cumulative_est_federal_paid, 2),
            "cumulative_est_state_paid": round(cumulative_est_state_paid, 2),
            # Remaining amounts due
            "federal_remaining": round(federal_remaining, 2),
            "state_remaining": round(state_remaining, 2),
            "status": status,
        })
    
    return payments


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

    # Calculate rental net income for QBI deduction
    rental_income = forecast_income.get("rental_income", 0)
    rental_depreciation = forecast_income.get("rental_depreciation", 0)
    rental_net_income = max(0, rental_income - rental_depreciation)

    # Calculate taxable income (with QBI deduction)
    taxable_income, qbi_deduction = _calculate_taxable_income(
        agi, deductions, forecast_year, rental_net_income=rental_net_income
    )

    # Calculate federal tax with preferential rates for qualified dividends + LTCG
    filing_status = base_return.filing_status or "MFJ"
    cap_gains = forecast_income.get("capital_gains", {})
    # Qualified dividends: assume all dividends are qualified (typical for equity holdings)
    qualified_dividends = forecast_income.get("dividend_income", 0)
    long_term_gains = cap_gains.get("net_long_term", 0)
    preferential_income = max(0, qualified_dividends + long_term_gains)
    # Preferential income can't exceed taxable income
    preferential_income = min(preferential_income, taxable_income)
    federal_tax = _calculate_federal_tax(
        taxable_income, filing_status, forecast_year,
        preferential_income=preferential_income
    )
    
    # Calculate tax credits (Child Tax Credit, etc.)
    credits = _calculate_credits(db, forecast_year, federal_tax)

    # Subtract credits from federal tax (non-refundable, capped at tax liability)
    federal_tax_after_credits = max(0, federal_tax - credits["total_credits"])

    # Calculate state tax (assuming California)
    # CA uses its own standard deduction (much lower than federal)
    ca_taxable_income = _calculate_ca_taxable_income(agi, deductions, forecast_year)
    state_tax = _calculate_ca_state_tax(ca_taxable_income, filing_status, forecast_year)

    # Calculate other taxes (payroll, NIIT, etc.)
    other_taxes = _calculate_other_taxes(forecast_income, agi, base_details)

    # Calculate effective rate (use federal tax after credits)
    total_tax = federal_tax_after_credits + state_tax + other_taxes
    effective_rate = (total_tax / agi * 100) if agi > 0 else 0

    # Build details JSON similar to base year
    forecast_details = _build_forecast_details(
        forecast_income, deductions, base_details, forecast_year,
        qbi_deduction=qbi_deduction, credits=credits
    )
    
    # Calculate quarterly payment schedule for estimated taxes
    # Get W-2 withholding broken out by federal and state
    federal_withheld = forecast_income.get("w2_income", {}).get("federal_withheld", 0)
    state_withheld = forecast_income.get("w2_income", {}).get("state_withheld", 0)
    w2_withheld = federal_withheld + state_withheld
    
    # Get estimated payments already made
    estimated_payments = _get_estimated_payments(db, forecast_year)

    monthly_income = forecast_income.get("monthly_income", {})
    payment_schedule = _calculate_quarterly_payments(
        total_tax=total_tax,
        federal_tax=federal_tax_after_credits,
        state_tax=state_tax,
        w2_withheld=w2_withheld,
        federal_withheld=federal_withheld,
        state_withheld=state_withheld,
        income_by_month=monthly_income,
        year=forecast_year,
        estimated_payments=estimated_payments
    )

    # Calculate safe harbor amounts (to avoid underpayment penalties)
    # Safe harbor: Pay 110% of prior year tax or 90% of current year tax (for AGI > $150k)
    prior_federal_tax = float(base_return.federal_tax or 0) if base_return else 0
    prior_state_tax = float(base_return.state_tax or 0) if base_return else 0
    prior_year_tax = prior_federal_tax + prior_state_tax

    # Federal safe harbor (use tax after credits)
    federal_safe_harbor_prior = prior_federal_tax * 1.10
    federal_safe_harbor_current = federal_tax_after_credits * 0.90
    federal_safe_harbor = min(federal_safe_harbor_prior, federal_safe_harbor_current) if prior_federal_tax > 0 else federal_safe_harbor_current

    # State safe harbor (CA uses same rules for AGI $150k-$1M)
    state_safe_harbor_prior = prior_state_tax * 1.10
    state_safe_harbor_current = state_tax * 0.90
    state_safe_harbor = min(state_safe_harbor_prior, state_safe_harbor_current) if prior_state_tax > 0 else state_safe_harbor_current

    safe_harbor_prior = prior_year_tax * 1.10
    safe_harbor_current = total_tax * 0.90
    safe_harbor_amount = min(safe_harbor_prior, safe_harbor_current) if prior_year_tax > 0 else safe_harbor_current

    # Calculate underpayment penalty
    penalty_info = _calculate_underpayment_penalty(
        payment_schedule=payment_schedule,
        federal_safe_harbor=federal_safe_harbor,
        state_safe_harbor=state_safe_harbor,
        prior_federal_tax=prior_federal_tax,
        prior_state_tax=prior_state_tax,
        current_federal_tax=federal_tax_after_credits,
        current_state_tax=state_tax,
        year=forecast_year
    )

    # Calculate remaining estimated tax needed after payments
    total_estimated_paid = estimated_payments.get("total_paid", 0)
    remaining_estimated_needed = max(0, total_tax - w2_withheld - total_estimated_paid)

    return {
        "tax_year": forecast_year,
        "agi": agi,
        "federal_tax": federal_tax_after_credits,
        "federal_tax_before_credits": federal_tax,
        "state_tax": state_tax,
        "other_tax": other_taxes,
        "total_tax": total_tax,
        "effective_rate": round(effective_rate, 2),
        "filing_status": filing_status,
        "qbi_deduction": round(qbi_deduction, 2),
        "credits": credits,
        "details": forecast_details,
        "is_forecast": True,
        "payment_schedule": payment_schedule,
        "w2_withholding": {
            "federal": forecast_income.get("w2_income", {}).get("federal_withheld", 0),
            "state": forecast_income.get("w2_income", {}).get("state_withheld", 0),
            "total": w2_withheld
        },
        "estimated_payments": {
            "federal_paid": estimated_payments.get("total_federal_paid", 0),
            "state_paid": estimated_payments.get("total_state_paid", 0),
            "total_paid": total_estimated_paid,
            "payments": estimated_payments.get("federal_payments", []) + estimated_payments.get("state_payments", [])
        },
        "estimated_tax_needed": max(0, total_tax - w2_withheld),
        "remaining_estimated_needed": remaining_estimated_needed,
        "safe_harbor": {
            "prior_year_110": round(safe_harbor_prior, 2),
            "current_year_90": round(safe_harbor_current, 2),
            "recommended": round(safe_harbor_amount, 2)
        },
        "underpayment_penalty": penalty_info
    }


def _get_forecast_income(db: Session, year: int) -> Dict[str, Any]:
    """
    Get all income sources for the forecast year.
    
    IMPORTANT: For tax purposes, we only include income from TAXABLE accounts.
    Income from retirement accounts (IRA, Roth IRA, 401k, HSA) is either
    tax-deferred or tax-free and should NOT be included in current year taxes.
    """
    income = {
        "w2_income": {},
        "rental_income": 0,
        "rental_depreciation": 0,
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
    total_dependent_care = 0

    for w2 in w2_records:
        wages = float(w2.wages or 0)
        federal_withheld = float(w2.federal_tax_withheld or 0)
        state_withheld = float(w2.state_tax_withheld or 0)
        ss_tax = float(w2.social_security_tax or 0)
        medicare_tax = float(w2.medicare_tax or 0)
        dep_care = float(w2.dependent_care_benefits or 0)

        total_w2_wages += wages
        total_federal_withheld += federal_withheld
        total_state_withheld += state_withheld
        total_social_security += ss_tax
        total_medicare += medicare_tax
        total_dependent_care += dep_care

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
        "dependent_care_benefits": total_dependent_care,
        "breakdown": w2_breakdown
    }
    
    # Get TAXABLE investment income only (excludes IRA, Roth IRA, 401k, HSA)
    # Income in retirement accounts is tax-deferred or tax-free
    taxable_income_summary = db_queries.get_taxable_income_summary(db, year=year)
    income["options_income"] = taxable_income_summary.get("options_income", 0)
    income["dividend_income"] = taxable_income_summary.get("dividend_income", 0)
    income["interest_income"] = taxable_income_summary.get("interest_income", 0)
    
    # Get account-level breakdowns for taxable income
    income["options_by_account"] = _get_taxable_income_by_account(db, year, "options")
    income["dividends_by_account"] = _get_taxable_income_by_account(db, year, "dividends")
    income["interest_by_account"] = _get_taxable_income_by_account(db, year, "interest")
    
    # Get monthly income breakdown for quarterly payment calculations
    income["monthly_income"] = _get_monthly_income_breakdown(db, year, income)
    
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
    
    # Apply depreciation deduction for rental properties
    # Depreciation is a major tax deduction for rental income
    # Estimate based on prior year or property cost basis
    rental_depreciation = _estimate_rental_depreciation(db, year)
    income["rental_income"] = year_rental_income
    income["rental_depreciation"] = rental_depreciation

    # Get capital gains/losses for the forecast year (TAXABLE accounts only)
    capital_gains = _calculate_capital_gains(db, year)
    income["capital_gains"] = capital_gains

    # Get retirement contributions for the forecast year (these reduce AGI)
    retirement = _get_retirement_contributions(db, year)
    income["retirement_contributions"] = retirement

    return income


def _calculate_ira_deduction_after_phaseout(
    retirement: Dict[str, Any],
    magi: float,
    filing_status: str = "MFJ",
    year: int = 2025
) -> float:
    """
    Calculate the IRA deduction after applying income-based phase-out rules.

    IRA deduction phase-out for 2025 (Married Filing Jointly):
    - Active participant (has workplace plan like 401k):
      Phase-out range: $126,000 - $146,000 MAGI
    - Spouse of active participant (no own workplace plan):
      Phase-out range: $236,000 - $246,000 MAGI
    - Neither spouse is active participant: No phase-out

    Phase-out formula:
      reduced = contribution * (phase_out_end - MAGI) / (phase_out_end - phase_out_start)
      rounded UP to the nearest $10

    Source: IRS Publication 590-A
    """
    # 2025 MFJ phase-out ranges
    # Source: IRS Revenue Procedure 2024-40
    ACTIVE_PARTICIPANT_START = 126000
    ACTIVE_PARTICIPANT_END = 146000
    SPOUSE_OF_PARTICIPANT_START = 236000
    SPOUSE_OF_PARTICIPANT_END = 246000

    ira_per_person = retirement.get("ira_per_person", [])
    anyone_has_plan = retirement.get("anyone_has_workplace_plan", False)

    if not ira_per_person:
        return 0

    # If nobody has a workplace plan, full deduction (no phase-out)
    if not anyone_has_plan:
        return retirement.get("ira_deduction_before_phaseout", 0)

    total_deduction = 0
    for person in ira_per_person:
        contribution = person.get("ira_contribution", 0)
        if contribution <= 0:
            continue

        has_plan = person.get("has_workplace_plan", False)

        if has_plan:
            # Active participant phase-out
            start, end = ACTIVE_PARTICIPANT_START, ACTIVE_PARTICIPANT_END
        else:
            # Spouse of active participant phase-out
            start, end = SPOUSE_OF_PARTICIPANT_START, SPOUSE_OF_PARTICIPANT_END

        if magi <= start:
            # Below phase-out range: full deduction
            total_deduction += contribution
        elif magi >= end:
            # Above phase-out range: no deduction
            pass  # $0 for this person
        else:
            # Within phase-out range: partial deduction
            # Formula: contribution * (end - MAGI) / (end - start), rounded up to $10
            reduction_factor = (end - magi) / (end - start)
            reduced = contribution * reduction_factor
            # Round UP to nearest $10
            import math
            reduced = math.ceil(reduced / 10) * 10
            # Minimum $200 if any contribution was made (IRS rule)
            reduced = max(reduced, min(200, contribution))
            total_deduction += reduced

    return total_deduction


def _calculate_agi(income: Dict[str, Any]) -> float:
    """
    Calculate Adjusted Gross Income from income sources.

    AGI = Total Income - Above-the-line Deductions

    Includes:
    - W-2 wages
    - Dividend income from TAXABLE accounts only
    - Interest income from TAXABLE accounts only
    - Capital gains/losses (includes realized options gains + stock lot gains)
    - Rental income (net after expenses AND depreciation)

    NOTE: Options income (STO/BTC premiums) is NOT added separately.
    It is incorporated into capital_gains via _calculate_capital_gains()
    with a realization rate adjustment. This prevents double-counting
    (options gains + stock lot gains overlapping) and accounts for
    unrealized open positions.

    Note: Income from retirement accounts (IRA, Roth IRA, 401k, HSA) is
    NOT included as it is either tax-deferred or tax-free.

    Subtracts (above-the-line deductions):
    - IRA contributions (traditional only, subject to phase-out)
    - HSA contributions
    - Rental depreciation
    - Other pre-tax retirement contributions (already excluded from W-2 wages)
    """
    agi = 0

    # W-2 wages (already reduced by 401k contributions in Box 1)
    agi += income["w2_income"].get("total_wages", 0)

    # Dependent care benefits (W-2 Box 10) - taxable income on 1040 line 1e
    agi += income["w2_income"].get("dependent_care_benefits", 0)

    # Investment income from TAXABLE accounts only
    # NOTE: Options income (STO/BTC premiums) is NOT added here separately.
    # It is incorporated into capital_gains via _calculate_capital_gains()
    # to avoid double-counting and to apply realization adjustments.
    agi += income.get("dividend_income", 0)
    agi += income.get("interest_income", 0)

    # Rental income (net after expenses)
    rental_income = income.get("rental_income", 0)
    agi += rental_income
    
    # Subtract rental depreciation (major tax deduction)
    # IMPORTANT: Depreciation can only be applied if there's rental income
    # Under passive activity rules, rental losses are generally limited
    # For simplicity, we cap depreciation at the rental income amount
    # (preventing artificial losses when there's no rental activity)
    rental_depreciation = income.get("rental_depreciation", 0)
    if rental_income > 0:
        # Apply depreciation up to the rental income (can reduce to $0, but not negative)
        # Note: Full passive loss rules are more complex - this is simplified
        applicable_depreciation = min(rental_depreciation, rental_income)
        agi -= applicable_depreciation

    # Capital gains/losses (net, from TAXABLE accounts only)
    # IRS rules: Net capital losses are limited to $3,000/year deduction
    # ($1,500 if married filing separately). Excess carries forward.
    cap_gains = income.get("capital_gains", {})
    net_short_term = cap_gains.get("net_short_term", 0)
    net_long_term = cap_gains.get("net_long_term", 0)
    net_capital_gain = net_short_term + net_long_term
    
    # Apply the $3,000 capital loss limitation (for MFJ)
    # If net is negative (loss), limit deduction to $3,000
    CAPITAL_LOSS_LIMIT = 3000  # $3,000 for MFJ, $1,500 for MFS
    if net_capital_gain < 0:
        # Can only deduct up to the limit
        applicable_loss = max(net_capital_gain, -CAPITAL_LOSS_LIMIT)
        agi += applicable_loss
    else:
        # Gains are fully taxable
        agi += net_capital_gain

    # Above-the-line deductions (reduce AGI)
    retirement = income.get("retirement_contributions", {})

    # IRA deduction with phase-out based on MAGI
    # MAGI for IRA phase-out = AGI before IRA deduction (which is current 'agi')
    magi = agi
    ira_deduction = _calculate_ira_deduction_after_phaseout(retirement, magi)
    agi -= ira_deduction

    # HSA contributions
    agi -= retirement.get("hsa_contribution", 0)
    # Note: 401k contributions already excluded from W-2 Box 1 wages

    return agi


def _calculate_taxable_income(
    agi: float,
    deductions: Dict[str, Any],
    year: int,
    rental_net_income: float = 0
) -> tuple:
    """
    Calculate taxable income after deductions and QBI deduction.

    Returns (taxable_income, qbi_deduction) tuple.
    """
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

    taxable_income_before_qbi = max(0, agi - deduction)

    # QBI Deduction (Section 199A) - 20% of qualified business income
    # Rental income from Schedule E qualifies as QBI for non-passive landlords
    # Simplified calculation applies when taxable income < $383,900 (MFJ 2025)
    qbi_deduction = 0
    if rental_net_income > 0:
        qbi_amount = rental_net_income * 0.20
        # QBI deduction is limited to 20% of taxable income before QBI deduction
        taxable_income_limit = taxable_income_before_qbi * 0.20
        qbi_deduction = min(qbi_amount, taxable_income_limit)

    taxable_income = max(0, taxable_income_before_qbi - qbi_deduction)
    return taxable_income, qbi_deduction


def _calculate_ca_taxable_income(
    agi: float,
    deductions: Dict[str, Any],
    year: int
) -> float:
    """
    Calculate California taxable income after CA-specific deductions.

    California has its own standard deduction that is much lower than federal.
    CA does NOT conform to the federal standard deduction amount.

    2025 CA Standard Deduction (estimated with ~2.8% inflation from 2024):
    - MFJ: $11,026 (2024: $10,726)
    - Single: $5,513 (2024: $5,363)

    Source: California Franchise Tax Board (FTB)
    """
    ca_standard_deductions = {
        2025: 11026,  # MFJ, estimated from 2024 + inflation
        2024: 10726,  # MFJ, official
        2023: 10404,  # MFJ, official
    }

    ca_standard = ca_standard_deductions.get(year, 11026)
    # CA itemized deductions differ from federal (e.g., no SALT cap)
    # For simplicity, use the larger of CA standard or itemized
    itemized_total = deductions.get("itemized_total", 0)
    deduction = max(ca_standard, itemized_total) if itemized_total > 0 else ca_standard

    return max(0, agi - deduction)


def _calculate_federal_tax(
    taxable_income: float,
    filing_status: str,
    year: int,
    preferential_income: float = 0
) -> float:
    """
    Calculate federal income tax using official IRS tax brackets.

    Applies preferential rates (0%/15%/20%) to qualified dividends and
    long-term capital gains, and ordinary rates to remaining income.

    The preferential income is "stacked on top" of ordinary income:
    1. Tax ordinary income at ordinary rates (10%-37%)
    2. Stack preferential income above it and apply LTCG rates based on
       where it falls in the income scale

    2025 LTCG/Qualified Dividend brackets (MFJ):
      0% up to $96,700
      15% from $96,700 to $600,050
      20% above $600,050

    Source: IRS Revenue Procedure 2024-40, Tax Foundation
    """
    # --- Ordinary income brackets ---
    if year >= 2025:
        if filing_status in ["MFJ", "married_filing_jointly"]:
            brackets = [
                (0, 0.10), (23850, 0.12), (96950, 0.22),
                (206700, 0.24), (394600, 0.32), (501050, 0.35), (751600, 0.37),
            ]
            ltcg_brackets = [(0, 0.0), (96700, 0.15), (600050, 0.20)]
        elif filing_status in ["Single", "single"]:
            brackets = [
                (0, 0.10), (11925, 0.12), (48475, 0.22),
                (103350, 0.24), (197300, 0.32), (250525, 0.35), (626350, 0.37),
            ]
            ltcg_brackets = [(0, 0.0), (48350, 0.15), (533400, 0.20)]
        else:
            brackets = [
                (0, 0.10), (23850, 0.12), (96950, 0.22),
                (206700, 0.24), (394600, 0.32), (501050, 0.35), (751600, 0.37),
            ]
            ltcg_brackets = [(0, 0.0), (96700, 0.15), (600050, 0.20)]
    else:
        brackets = [
            (0, 0.10), (23200, 0.12), (94300, 0.22),
            (201050, 0.24), (383900, 0.32), (487050, 0.35), (731200, 0.37),
        ]
        ltcg_brackets = [(0, 0.0), (94050, 0.15), (583750, 0.20)]
        if filing_status in ["Single", "single"]:
            brackets = [
                (0, 0.10), (11600, 0.12), (47150, 0.22),
                (100525, 0.24), (191950, 0.32), (243725, 0.35), (609350, 0.37),
            ]
            ltcg_brackets = [(0, 0.0), (47025, 0.15), (518900, 0.20)]

    # If no preferential income, use simple ordinary calculation
    if preferential_income <= 0:
        return _apply_brackets(taxable_income, brackets)

    # --- Split calculation: ordinary + preferential ---
    ordinary_income = taxable_income - preferential_income

    # Step 1: Tax on ordinary income at ordinary rates
    ordinary_tax = _apply_brackets(ordinary_income, brackets)

    # Step 2: Tax on preferential income at LTCG rates
    # Preferential income is "stacked" on top of ordinary income
    # The LTCG rate depends on where the preferential income falls
    pref_tax = 0.0
    remaining_pref = preferential_income

    for i in range(len(ltcg_brackets)):
        bracket_start, rate = ltcg_brackets[i]
        bracket_end = ltcg_brackets[i + 1][0] if i + 1 < len(ltcg_brackets) else float('inf')

        if remaining_pref <= 0:
            break

        # How much of this LTCG bracket is available after ordinary income?
        if ordinary_income >= bracket_end:
            # Ordinary income fills this bracket entirely - preferential skips it
            continue
        elif ordinary_income > bracket_start:
            # Ordinary income partially fills this bracket
            available_in_bracket = bracket_end - ordinary_income
        else:
            # Ordinary income doesn't reach this bracket
            available_in_bracket = bracket_end - bracket_start

        taxable_in_bracket = min(remaining_pref, available_in_bracket)
        pref_tax += taxable_in_bracket * rate
        remaining_pref -= taxable_in_bracket

    return ordinary_tax + pref_tax


def _apply_brackets(income: float, brackets: list) -> float:
    """Apply progressive tax brackets to an income amount."""
    tax = 0.0
    remaining = income
    for i in range(len(brackets)):
        bracket_start, rate = brackets[i]
        bracket_end = brackets[i + 1][0] if i + 1 < len(brackets) else float('inf')
        if remaining <= 0:
            break
        if income > bracket_start:
            bracket_income = min(remaining, bracket_end - bracket_start)
            tax += bracket_income * rate
            remaining -= bracket_income
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
    """
    Calculate other taxes: payroll taxes, NIIT, etc.
    
    NIIT (Net Investment Income Tax) applies to:
    - Options income
    - Dividends
    - Interest
    - Capital gains (both short-term and long-term)
    - Rental income (net)
    
    Only income from TAXABLE accounts is subject to NIIT.
    """
    other_tax = 0
    
    # Payroll taxes (already withheld, but included in "other" category)
    w2_data = income.get("w2_income", {})
    other_tax += w2_data.get("social_security", 0)
    other_tax += w2_data.get("medicare", 0)
    
    # NIIT (Net Investment Income Tax) - 3.8% on investment income above threshold
    # Threshold: $250,000 for MFJ, $200,000 for Single
    # Source: IRS Topic 559
    niit_threshold = 250000  # MFJ default
    
    # NIIT applies to ALL net investment income including capital gains
    # NOTE: Options income is now included within capital_gains (not separate)
    cap_gains = income.get("capital_gains", {})
    net_capital_gains = cap_gains.get("net_short_term", 0) + cap_gains.get("net_long_term", 0)

    # Net rental income is also subject to NIIT (minus depreciation)
    net_rental = income.get("rental_income", 0) - income.get("rental_depreciation", 0)

    investment_income = (
        income.get("dividend_income", 0) +
        income.get("interest_income", 0) +
        net_capital_gains +  # Includes options gains (realized) + stock lot gains
        max(0, net_rental)   # Include rental income (if positive)
    )
    
    if agi > niit_threshold and investment_income > 0:
        niit_base = min(investment_income, agi - niit_threshold)
        niit = niit_base * 0.038
        other_tax += niit
    
    return other_tax


def _calculate_credits(
    db: Session,
    year: int,
    federal_tax: float
) -> Dict[str, Any]:
    """
    Calculate tax credits for the forecast year.

    Currently supports:
    - Child Tax Credit (CTC): $2,200/child for 2025 (OBBBA), $2,000/child for 2024
    - Non-refundable: capped at federal tax liability
    """
    dependents = db.query(TaxDependent).filter(
        TaxDependent.tax_year == year,
        TaxDependent.qualifies_for_ctc == True
    ).all()

    # CTC amount per child by year
    ctc_per_child = {
        2025: 2200,  # One Big Beautiful Bill Act (OBBBA)
        2024: 2000,
    }
    ctc_amount = ctc_per_child.get(year, 2000)

    child_tax_credit = len(dependents) * ctc_amount

    # Non-refundable: capped at federal tax liability
    child_tax_credit = min(child_tax_credit, federal_tax)

    total_credits = child_tax_credit

    return {
        "child_tax_credit": round(child_tax_credit, 2),
        "num_qualifying_children": len(dependents),
        "ctc_per_child": ctc_amount,
        "total_credits": round(total_credits, 2),
    }


def _build_forecast_details(
    income: Dict[str, Any],
    deductions: Dict[str, Any],
    base_details: Dict[str, Any],
    year: int,
    qbi_deduction: float = 0,
    credits: Optional[Dict[str, Any]] = None
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
        w2_entry = {
            "source": "W-2 Wages",
            "amount": income["w2_income"]["total_wages"]
        }
        dep_care = income["w2_income"].get("dependent_care_benefits", 0)
        if dep_care > 0:
            w2_entry["dependent_care_benefits"] = dep_care
        details["income_sources"].append(w2_entry)
    
    if income.get("rental_income", 0) > 0:
        depreciation = income.get("rental_depreciation", 0)
        net_taxable_rental = income["rental_income"] - depreciation
        details["income_sources"].append({
            "source": "Rental Income (Net of Depreciation)",
            "amount": net_taxable_rental,
            "gross": income["rental_income"],
            "depreciation": depreciation
        })
    
    # Options premiums and stock lot gains are separate components of capital gains
    cap_gains_data = income.get("capital_gains", {})
    if cap_gains_data.get("options_realized", 0) > 0:
        details["income_sources"].append({
            "source": "Option Premiums (Realized)",
            "amount": cap_gains_data["options_realized"],
            "raw_net": cap_gains_data.get("options_net_income", 0),
            "closure_rate": cap_gains_data.get("options_closure_rate", 1.0),
            "note": "Taxable accounts only; adjusted for open positions"
        })

    # Stock lot gains (from direct sales or assignments)
    stock_st = cap_gains_data.get("stock_lot_st", 0)
    stock_lt = cap_gains_data.get("stock_lot_lt", 0)
    stock_total = stock_st + stock_lt
    if stock_total != 0:
        details["income_sources"].append({
            "source": "Stock Sale Gains/Losses",
            "amount": stock_total,
            "note": f"ST: ${stock_st:,.0f}, LT: ${stock_lt:,.0f} (from cost basis tracker)"
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
    
    # Add account-level breakdowns for investment income
    if income.get("options_by_account"):
        details["options_by_account"] = income["options_by_account"]
    
    if income.get("dividends_by_account"):
        details["dividends_by_account"] = income["dividends_by_account"]
    
    if income.get("interest_by_account"):
        details["interest_by_account"] = income["interest_by_account"]
    
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
    
    # Additional taxes (NIIT) - options income is now within capital_gains
    cap_gains = income.get("capital_gains", {})
    net_capital_gains = cap_gains.get("net_short_term", 0) + cap_gains.get("net_long_term", 0)
    net_rental = income.get("rental_income", 0) - income.get("rental_depreciation", 0)

    investment_income = (
        income.get("dividend_income", 0) +
        income.get("interest_income", 0) +
        net_capital_gains +  # Includes realized options gains
        max(0, net_rental)
    )
    
    agi = _calculate_agi(income)
    niit_threshold = 250000
    if agi > niit_threshold and investment_income > 0:
        niit_base = min(investment_income, agi - niit_threshold)
        niit = niit_base * 0.038
        details["additional_taxes"]["niit"] = niit
        details["additional_taxes"]["niit_base"] = niit_base
        details["additional_taxes"]["investment_income_total"] = investment_income
    
    # Copy rental properties from base if available
    if base_details.get("rental_properties"):
        details["rental_properties"] = base_details["rental_properties"]

    # Add capital gains if present (now includes options + stock lot gains)
    cap_gains = income.get("capital_gains", {})
    if cap_gains.get("net_short_term") or cap_gains.get("net_long_term"):
        details["capital_gains"] = {
            "short_term": cap_gains.get("net_short_term", 0),
            "long_term": cap_gains.get("net_long_term", 0),
            "total": cap_gains.get("net_short_term", 0) + cap_gains.get("net_long_term", 0),
            "options_realized": cap_gains.get("options_realized", 0),
            "options_closure_rate": cap_gains.get("options_closure_rate", 0),
            "stock_lot_st": cap_gains.get("stock_lot_st", 0),
            "stock_lot_lt": cap_gains.get("stock_lot_lt", 0),
        }
        # Add total capital gains to income sources (sum of options + stock lots)
        net_investment_gains = cap_gains.get("net_short_term", 0) + cap_gains.get("net_long_term", 0)
        if net_investment_gains != 0:
            details["income_sources"].append({
                "source": "Total Capital Gains (Schedule D)",
                "amount": net_investment_gains,
                "note": cap_gains.get("note", "")
            })

    # QBI deduction
    if qbi_deduction > 0:
        details["qbi_deduction"] = round(qbi_deduction, 2)

    # Tax credits
    if credits and credits.get("total_credits", 0) > 0:
        details["credits"] = credits

    return details


def _calculate_capital_gains(db: Session, year: int) -> Dict[str, float]:
    """
    Calculate net capital gains/losses from investment transactions.

    Combines TWO sources of investment gains into a single capital gains figure:
    1. Stock lot sales (from cost basis tracker) - tracks stock dispositions
    2. Options income (STO/BTC premiums) - tracks option premium flows

    Both appear on the 1099-B / Schedule D as capital gains. They are combined
    here to avoid double-counting in AGI (options_income is NOT added separately).

    Options gains are adjusted by a "realization rate" because STO premiums are
    recorded when positions are opened, but the 1099 only reports gains when
    positions are CLOSED. Open positions at year-end would inflate the forecast.
    Realization rate = BTC count / STO count (approximates closure fraction).

    To avoid double-counting between options and stock lots:
    - Options gains (realized) are treated as short-term capital gains
    - Only long-term stock lot gains are added on top (options are always ST)
    - Short-term stock lot gains are excluded when options income is present,
      since they likely overlap (assigned options produce ST stock sales)

    IMPORTANT: Only includes transactions from TAXABLE brokerage accounts.

    Returns dict with net_short_term and net_long_term
    """
    # Non-taxable account types to exclude
    non_taxable_types = ['ira', 'roth_ira', 'traditional_ira', '401k', 'hsa', 'retirement']

    # --- Step 1: Get stock lot sale gains from cost basis tracker ---
    stock_gains_st = 0.0
    stock_gains_lt = 0.0
    stock_num_transactions = 0
    stock_note = ""

    try:
        from app.modules.tax.cost_basis_service import CostBasisService

        service = CostBasisService(db)
        summary = service.get_capital_gains_summary(year)

        if summary.get("num_transactions", 0) > 0:
            stock_gains_st = summary.get("total_short_term_gain", 0)
            stock_gains_lt = summary.get("total_long_term_gain", 0)
            stock_num_transactions = summary.get("num_transactions", 0)
            stock_note = "cost_basis"
    except Exception:
        db.rollback()

    if not stock_note:
        # Fallback: estimate from SELL transactions
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
            total_proceeds = sum(float(t.amount or 0) for t in sell_transactions)
            estimated_gains = total_proceeds * 0.50 if total_proceeds > 0 else 0
            stock_gains_lt = estimated_gains
            stock_note = "estimated_50pct"

    # --- Step 2: Get realized options gains ---
    # Query STO and BTC transaction counts and amounts from taxable accounts
    options_net = 0.0
    options_closure_rate = 1.0
    realized_options = 0.0

    sto_result = db.query(
        func.sum(InvestmentTransaction.amount).label('total'),
        func.count(InvestmentTransaction.id).label('count')
    ).join(
        InvestmentAccount,
        and_(
            InvestmentTransaction.account_id == InvestmentAccount.account_id,
            InvestmentTransaction.source == InvestmentAccount.source
        )
    ).filter(
        InvestmentTransaction.transaction_type == 'STO',
        extract('year', InvestmentTransaction.transaction_date) == year,
        InvestmentAccount.is_active == 'Y',
        ~func.lower(InvestmentAccount.account_type).in_(non_taxable_types)
    ).first()

    btc_result = db.query(
        func.sum(InvestmentTransaction.amount).label('total'),
        func.count(InvestmentTransaction.id).label('count')
    ).join(
        InvestmentAccount,
        and_(
            InvestmentTransaction.account_id == InvestmentAccount.account_id,
            InvestmentTransaction.source == InvestmentAccount.source
        )
    ).filter(
        InvestmentTransaction.transaction_type == 'BTC',
        extract('year', InvestmentTransaction.transaction_date) == year,
        InvestmentAccount.is_active == 'Y',
        ~func.lower(InvestmentAccount.account_type).in_(non_taxable_types)
    ).first()

    sto_total = float(sto_result.total or 0) if sto_result else 0
    sto_count = int(sto_result.count or 0) if sto_result else 0
    btc_total = float(btc_result.total or 0) if btc_result else 0
    btc_count = int(btc_result.count or 0) if btc_result else 0

    options_net = sto_total + btc_total  # BTC amounts are negative

    if options_net > 0 and sto_count > 0:
        # Estimate what fraction of positions are closed (realized)
        # BTC count / STO count approximates the closure rate
        # Cap at 1.0 (more BTCs than STOs means closing prior-year positions)
        options_closure_rate = min(1.0, btc_count / sto_count) if sto_count > 0 else 1.0
        realized_options = options_net * options_closure_rate

    # --- Step 3: Combine options premiums + stock lot gains ---
    # These are separate income streams that DO NOT overlap:
    #   - Options premiums (STO/BTC): cash from selling/buying option contracts
    #   - Stock lot gains: capital gain/loss when shares are sold (including assignments)
    # Both appear on Schedule D but are distinct transactions.
    if realized_options > 0:
        net_short_term = realized_options + stock_gains_st
        net_long_term = stock_gains_lt
        parts = [f"Options: ${options_net:,.0f} net × {options_closure_rate:.0%} realized = ${realized_options:,.0f}"]
        if stock_gains_st != 0:
            parts.append(f"Stock sales ST: ${stock_gains_st:,.0f}")
        if stock_gains_lt != 0:
            parts.append(f"Stock sales LT: ${stock_gains_lt:,.0f}")
        note = "; ".join(parts)
    else:
        # No options activity - use stock lot sales directly
        net_short_term = stock_gains_st
        net_long_term = stock_gains_lt
        note = stock_note or "No investment gains data"

    return {
        "net_short_term": net_short_term,
        "net_long_term": net_long_term,
        "taxable_accounts_only": True,
        "note": note,
        # Breakdown for transparency
        "options_net_income": options_net,
        "options_closure_rate": options_closure_rate,
        "options_realized": realized_options,
        "stock_lot_st": stock_gains_st,
        "stock_lot_lt": stock_gains_lt,
        "stock_lot_transactions": stock_num_transactions,
    }


def _estimate_rental_depreciation(db: Session, year: int) -> float:
    """
    Estimate rental property depreciation for tax purposes.
    
    Depreciation is a major tax deduction for rental properties.
    Residential rental properties depreciate over 27.5 years (straight-line).
    
    Formula: (Building Value) / 27.5 years
    
    We estimate based on:
    1. Prior year tax return depreciation (if available)
    2. Property cost basis (purchase price minus land value, typically 80% of price)
    """
    from app.modules.income.models import RentalProperty, RentalAnnualSummary
    
    # Try to get depreciation from prior year tax return
    prior_year = year - 1
    prior_return = db.query(IncomeTaxReturn).filter(
        IncomeTaxReturn.tax_year == prior_year
    ).first()
    
    if prior_return and prior_return.details_json:
        try:
            details = json.loads(prior_return.details_json)
            rental_props = details.get("rental_properties", [])
            if rental_props:
                # Use prior year depreciation as estimate
                total_depreciation = sum(
                    float(prop.get("depreciation", 0)) for prop in rental_props
                )
                if total_depreciation > 0:
                    return total_depreciation
        except:
            pass
    
    # Fallback: Estimate depreciation from property cost basis
    # Residential property depreciates over 27.5 years
    # Typically, land is ~20% and building is ~80% of purchase price
    properties = db.query(RentalProperty).filter(
        RentalProperty.is_active == 'Y'
    ).all()
    
    total_depreciation = 0
    for prop in properties:
        purchase_price = float(prop.purchase_price or 0)
        if purchase_price > 0:
            # Assume 80% is building value (depreciable)
            building_value = purchase_price * 0.80
            # Annual depreciation over 27.5 years
            annual_depreciation = building_value / 27.5
            total_depreciation += annual_depreciation
    
    return total_depreciation


def _get_monthly_income_breakdown(
    db: Session,
    year: int,
    income: Dict[str, Any]
) -> Dict[int, float]:
    """
    Get monthly income breakdown for quarterly payment calculations.
    
    Combines W-2 wages (spread evenly), options, dividends, interest,
    and rental income by month.
    
    Args:
        db: Database session
        year: Tax year
        income: Income dict from _get_forecast_income
    
    Returns:
        Dict mapping month number (1-12) to total taxable income
    """
    monthly = {m: 0.0 for m in range(1, 13)}
    
    # W-2 wages - spread evenly across 12 months
    w2_monthly = income.get("w2_income", {}).get("total_wages", 0) / 12
    for m in range(1, 13):
        monthly[m] += w2_monthly
    
    # Options income by month (from taxable accounts only)
    options_monthly = db_queries.get_options_income_monthly(db, year=year)
    for month_str, amount in options_monthly.items():
        try:
            month_num = int(month_str.split('-')[1])  # "2025-03" -> 3
            # Filter for taxable accounts would require additional logic
            # For now, we'll use the monthly totals and adjust later
            monthly[month_num] += float(amount or 0)
        except (ValueError, IndexError):
            pass
    
    # Dividends by month
    div_monthly = db_queries.get_dividend_income_monthly(db, year=year)
    for month_str, amount in div_monthly.items():
        try:
            month_num = int(month_str.split('-')[1])
            monthly[month_num] += float(amount or 0)
        except (ValueError, IndexError):
            pass
    
    # Interest by month
    int_monthly = db_queries.get_interest_income_monthly(db, year=year)
    for month_str, amount in int_monthly.items():
        try:
            month_num = int(month_str.split('-')[1])
            monthly[month_num] += float(amount or 0)
        except (ValueError, IndexError):
            pass
    
    # Rental income - spread evenly (assuming monthly rent)
    rental_monthly = income.get("rental_income", 0) / 12
    for m in range(1, 13):
        monthly[m] += rental_monthly
    
    # Capital gains - if we have them, spread based on transaction dates
    # For now, assume evenly distributed or concentrated in certain months
    cap_gains = income.get("capital_gains", {})
    total_cap_gains = cap_gains.get("net_short_term", 0) + cap_gains.get("net_long_term", 0)
    if total_cap_gains > 0:
        # Default: spread evenly across quarters
        cap_gain_quarterly = total_cap_gains / 4
        for m in [3, 6, 9, 12]:  # End of each quarter
            monthly[m] += cap_gain_quarterly
    
    return monthly


def _get_taxable_income_by_account(
    db: Session, 
    year: int, 
    income_type: str
) -> list:
    """
    Get income breakdown by taxable account for a specific income type.
    
    Args:
        db: Database session
        year: Tax year
        income_type: 'options', 'dividends', or 'interest'
    
    Returns:
        List of {account_name, account_id, source, amount} for taxable accounts only
    """
    # Non-taxable account types to exclude
    non_taxable_types = ['ira', 'roth_ira', 'traditional_ira', '401k', 'hsa', 'retirement']
    
    # Get all active accounts with their data
    accounts = db.query(InvestmentAccount).filter(
        InvestmentAccount.is_active == 'Y'
    ).all()
    
    result = []
    for account in accounts:
        account_type = (account.account_type or "").lower()
        
        # Skip non-taxable accounts
        if account_type in non_taxable_types:
            continue
        
        # Get income for this specific account
        if income_type == "options":
            summary = db_queries.get_options_income_summary(db, year=year, account_id=account.account_id)
        elif income_type == "dividends":
            summary = db_queries.get_dividend_income_summary(db, year=year, account_id=account.account_id)
        elif income_type == "interest":
            summary = db_queries.get_interest_income_summary(db, year=year, account_id=account.account_id)
        else:
            continue
        
        total = summary.get("total_income", 0)
        if total > 0:
            # Derive owner from account_name
            owner = account.account_name.split("'")[0] if account.account_name and "'" in account.account_name else 'Unknown'
            
            result.append({
                "account_name": account.account_name,
                "account_id": account.account_id,
                "source": account.source,
                "owner": owner,
                "amount": round(total, 2)
            })
    
    # Sort by amount descending
    result.sort(key=lambda x: x["amount"], reverse=True)
    return result


def _get_retirement_contributions(db: Session, year: int) -> Dict[str, Any]:
    """
    Get retirement contributions that reduce AGI.

    401(k) contributions: Already excluded from W-2 Box 1 wages
    Traditional IRA: Deductible (reduces AGI), SUBJECT TO PHASE-OUT
    Roth IRA: Not deductible (doesn't reduce AGI)
    HSA: Deductible (reduces AGI)

    2025 Limits:
    - 401(k): $23,500 ($31,000 with catch-up 50+, $34,750 ages 60-63)
    - IRA: $7,000 ($8,000 with catch-up 50+)
    - HSA: $4,300 individual / $8,550 family ($1,000 catch-up 55+)

    Returns dict with deductible amounts and per-person breakdown
    for IRA phase-out calculation in _calculate_agi().
    """
    contributions = db.query(RetirementContribution).filter(
        RetirementContribution.tax_year == year
    ).all()

    total_ira_deduction = 0
    total_hsa_contribution = 0
    total_401k = 0
    ira_per_person = []

    for contrib in contributions:
        ira_contrib = float(contrib.ira_contributions or 0)
        total_ira_deduction += ira_contrib

        hsa_contrib = float(contrib.hsa_contributions or 0)
        total_hsa_contribution += hsa_contrib

        k401_contrib = float(contrib.contributions_401k or 0)
        roth_401k = float(contrib.roth_401k or 0)
        total_401k += k401_contrib + roth_401k

        # Track per-person IRA + workplace plan status for phase-out
        has_workplace_plan = (k401_contrib > 0 or roth_401k > 0)
        if ira_contrib > 0:
            ira_per_person.append({
                "owner": contrib.owner or "Unknown",
                "ira_contribution": ira_contrib,
                "has_workplace_plan": has_workplace_plan,
            })

    return {
        "ira_deduction_before_phaseout": total_ira_deduction,
        "ira_deduction": total_ira_deduction,  # Will be overridden by _calculate_agi
        "ira_per_person": ira_per_person,
        "anyone_has_workplace_plan": total_401k > 0,
        "hsa_contribution": total_hsa_contribution,
        "k401_total": total_401k,
        "total_above_line_deduction": total_ira_deduction + total_hsa_contribution
    }

