"""
Strategies API routes.
Handles Buy/Borrow/Die and other wealth strategies.
"""

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text, func, extract
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from decimal import Decimal
from datetime import date, datetime, timezone
import os
import logging

logger = logging.getLogger(__name__)

# Centralized timezone handling - import from core
from app.core.timezone import format_datetime_for_api as _format_dt_as_utc

import threading

from app.core.database import get_db
from app.core.auth import get_current_user
from app.modules.strategies.models import SoldOptionsSnapshot, SoldOption
from app.modules.strategies.services import (
    save_parsed_options,
    get_current_sold_options,
    get_sold_options_by_account,
    calculate_unsold_options
)

router = APIRouter()


# ============================================================================
# ALGORITHM STATUS ENDPOINT
# ============================================================================

@router.get("/algorithm-status")
async def get_algorithm_status():
    """Return current algorithm version and configuration with isolation verification."""
    from app.modules.strategies.algorithm_config import ALGORITHM_VERSION, get_config
    import sys

    config = get_config()

    # Check which notification service modules are loaded
    v4_loaded = 'app.modules.strategies.v4_notification_service' in sys.modules
    v5_loaded = 'app.modules.strategies.v5_notification_service' in sys.modules

    # Get V5 version tag if V5 is loaded
    v5_version_tag = None
    v5_has_v4_imports = None
    if ALGORITHM_VERSION == 'v5':
        try:
            from app.modules.strategies.v5_notification_service import V5_VERSION_TAG
            v5_version_tag = V5_VERSION_TAG

            # Check if V5 module has any V4 imports (runtime verification)
            import app.modules.strategies.v5_notification_service as v5_module
            v5_source_file = v5_module.__file__
            with open(v5_source_file, 'r') as f:
                source = f.read()
                v5_has_v4_imports = 'from app.modules.strategies.v4' in source or 'import app.modules.strategies.v4' in source
        except Exception as e:
            v5_version_tag = f"error: {e}"

    return {
        "algorithm_version": ALGORITHM_VERSION,
        "config_version": config.get("version", "unknown"),
        "description": config.get("description", ""),
        "life_support_enabled": config.get("life_support", {}).get("enabled", False),
        # Version isolation verification
        "isolation_status": {
            "v4_module_loaded": v4_loaded,
            "v5_module_loaded": v5_loaded,
            "v5_version_tag": v5_version_tag,
            "v5_has_v4_imports": v5_has_v4_imports,
            "is_truly_standalone": v5_has_v4_imports == False if v5_has_v4_imports is not None else None,
        }
    }


class BuyBorrowDieParams(BaseModel):
    """Parameters for Buy/Borrow/Die projection."""
    starting_capital: Optional[float] = None  # If None, fetched from DB
    annual_growth_rate: float = 0.08  # 8% default
    monthly_borrowing: float = 20000  # $20K/month
    borrowing_interest_rate: float = 0.0525  # 5.25%
    current_age: int = 45
    end_age: int = 100
    first_year_months: int = 11  # 2025 partial year (11 months = ~$220K)
    margin_buffer_percent: float = 0.76  # 76% margin available


class StrategyUpdateRequest(BaseModel):
    """Request model for updating strategy configuration."""
    enabled: Optional[bool] = None
    notification_enabled: Optional[bool] = None
    notification_priority_threshold: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class YearlyProjection(BaseModel):
    """Projection data for a single year."""
    year: int
    age: int
    starting_capital: float
    capital_growth: float
    ending_capital: float
    annual_borrowing: float
    cumulative_borrowing: float
    annual_interest: float
    cumulative_interest: float
    total_debt: float  # cumulative borrowing + cumulative interest
    net_worth: float  # ending capital - total debt
    margin_available: float  # 76% of ending capital
    margin_utilization: float  # total debt / margin available (%)
    is_safe: bool  # margin utilization < 100%


class BuyBorrowDieProjection(BaseModel):
    """Complete Buy/Borrow/Die projection."""
    starting_capital: float
    params: BuyBorrowDieParams
    projections: List[YearlyProjection]
    summary: dict


@router.post("/buy-borrow-die/projection", response_model=BuyBorrowDieProjection)
async def calculate_buy_borrow_die_projection(
    params: BuyBorrowDieParams,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Calculate Buy/Borrow/Die projection over time."""
    
    # Get starting capital from database if not provided
    starting_capital = params.starting_capital
    if starting_capital is None:
        result = db.execute(text("""
            SELECT COALESCE(SUM(ih.market_value), 0) as total_value
            FROM investment_accounts ia
            LEFT JOIN investment_holdings ih ON ia.account_id = ih.account_id
            WHERE ia.account_type IN ('brokerage')
            AND ia.account_name IN ('Neel''s Brokerage', 'Jaya''s Brokerage')
        """))
        row = result.fetchone()
        starting_capital = float(row[0]) if row and row[0] else 2900000  # Default fallback
    
    projections = []
    current_year = 2025
    num_years = params.end_age - params.current_age
    
    capital = starting_capital
    cumulative_borrowing = 0.0
    cumulative_interest = 0.0
    
    years_until_trouble = None
    max_net_worth = 0
    
    for i in range(num_years):
        year = current_year + i
        age = params.current_age + i
        
        # Calculate capital growth
        starting_cap = capital
        growth = capital * params.annual_growth_rate
        ending_cap = capital + growth
        
        # Calculate borrowing for this year
        if i == 0:
            # First year - partial year
            annual_borrowing = params.monthly_borrowing * params.first_year_months
        else:
            annual_borrowing = params.monthly_borrowing * 12
        
        cumulative_borrowing += annual_borrowing
        
        # Calculate interest on total debt (compound interest on existing debt)
        annual_interest = cumulative_borrowing * params.borrowing_interest_rate
        cumulative_interest += annual_interest
        
        total_debt = cumulative_borrowing + cumulative_interest
        net_worth = ending_cap - total_debt
        
        # Margin calculations
        margin_available = ending_cap * params.margin_buffer_percent
        margin_utilization = (total_debt / margin_available * 100) if margin_available > 0 else 0
        is_safe = margin_utilization < 100
        
        if not is_safe and years_until_trouble is None:
            years_until_trouble = i
        
        max_net_worth = max(max_net_worth, net_worth)
        
        projections.append(YearlyProjection(
            year=year,
            age=age,
            starting_capital=round(starting_cap, 0),
            capital_growth=round(growth, 0),
            ending_capital=round(ending_cap, 0),
            annual_borrowing=round(annual_borrowing, 0),
            cumulative_borrowing=round(cumulative_borrowing, 0),
            annual_interest=round(annual_interest, 0),
            cumulative_interest=round(cumulative_interest, 0),
            total_debt=round(total_debt, 0),
            net_worth=round(net_worth, 0),
            margin_available=round(margin_available, 0),
            margin_utilization=round(margin_utilization, 1),
            is_safe=is_safe
        ))
        
        # Update capital for next year
        capital = ending_cap
    
    # Calculate summary statistics
    final_projection = projections[-1] if projections else None
    
    summary = {
        "starting_capital": round(starting_capital, 0),
        "final_capital": final_projection.ending_capital if final_projection else 0,
        "capital_growth_multiple": round(final_projection.ending_capital / starting_capital, 1) if final_projection else 0,
        "total_borrowed": final_projection.cumulative_borrowing if final_projection else 0,
        "total_interest_paid": final_projection.cumulative_interest if final_projection else 0,
        "total_debt": final_projection.total_debt if final_projection else 0,
        "final_net_worth": final_projection.net_worth if final_projection else 0,
        "max_net_worth": round(max_net_worth, 0),
        "years_until_margin_call": years_until_trouble,
        "strategy_sustainable": years_until_trouble is None or years_until_trouble >= num_years,
        "final_margin_utilization": final_projection.margin_utilization if final_projection else 0,
    }
    
    return BuyBorrowDieProjection(
        starting_capital=starting_capital,
        params=params,
        projections=projections,
        summary=summary
    )


class MonthlyActual(BaseModel):
    """Actual spending and income data for a single month."""
    year: int
    month: int
    month_name: str
    spending: float
    income: float
    options_income: float
    dividend_income: float  # Separate dividend income
    interest_income: float  # Separate interest income (not including dividends)
    rental_income: float  # Separate rental income
    salary_income: float  # Salary only (not including rental)
    net_cash_flow: float  # income - spending
    cumulative_net: float  # running total of net cash flow
    cumulative_spending: float
    cumulative_income: float
    # Taxable income (excludes IRA, Roth IRA, retirement accounts)
    taxable_options_income: float = 0.0
    taxable_dividend_income: float = 0.0
    taxable_interest_income: float = 0.0
    taxable_income: float = 0.0  # Sum of taxable options + dividend + interest + rental


class BuyBorrowDieActuals(BaseModel):
    """Actual spending and income data for Buy/Borrow/Die strategy."""
    monthly_data: List[MonthlyActual]
    total_spending: float
    total_income: float
    total_options_income: float
    total_interest_income: float
    total_salary_income: float
    net_position: float  # total_income - total_spending
    monthly_salary: float
    year: int
    is_sustainable: bool
    months_of_data: int
    annualized_spending: float
    annualized_income: float
    projected_annual_deficit: float
    # Taxable income (excludes IRA, Roth IRA, retirement accounts)
    total_taxable_income: float = 0.0


class YearSummary(BaseModel):
    """Summary for a single year."""
    year: int
    total_income: float
    total_spending: float
    net_position: float
    cumulative_gap: float
    months_of_data: int


class AllYearsResponse(BaseModel):
    """Response for all years summary."""
    yearly_summaries: List[YearSummary]
    total_cumulative_gap: float


class AvailableYearsResponse(BaseModel):
    """Response for available years."""
    years: List[int]


@router.get("/buy-borrow-die/actuals/years")
async def get_available_years(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Get list of years that have actuals data."""
    import csv
    import re
    from pathlib import Path
    from datetime import datetime
    
    years_with_data = set()
    current_year = datetime.now().year
    min_valid_year = 2020  # Reasonable minimum year
    max_valid_year = current_year + 1  # Allow up to next year
    
    def is_valid_year(year: int) -> bool:
        """Check if year is in valid range."""
        return min_valid_year <= year <= max_valid_year
    
    # Check CSV files for available years
    csv_dir = Path(__file__).parent.parent.parent.parent.parent / "data" / "processed" / "investments" / "robinhood"
    
    if csv_dir.exists():
        for csv_file in csv_dir.glob("*.csv"):
            # Extract year from filename - look for 4-digit patterns that are valid years
            match = re.search(r'(\d{4})', csv_file.name)
            if match:
                year = int(match.group(1))
                if is_valid_year(year):
                    years_with_data.add(year)
    
    # Also check database for transaction years
    try:
        from app.modules.income import db_queries as income_db
        options_monthly = income_db.get_options_income_monthly(db)
        for month_key in options_monthly.keys():
            year = int(month_key.split('-')[0])
            if is_valid_year(year):
                years_with_data.add(year)
    except:
        pass
    
    # Default to current year if no data found
    if not years_with_data:
        years_with_data.add(current_year)
    
    return AvailableYearsResponse(years=sorted(years_with_data, reverse=True))


@router.get("/buy-borrow-die/actuals/all-years")
async def get_all_years_actuals(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Get summary data for all years."""
    from datetime import datetime
    
    # Get available years first
    years_response = await get_available_years(db, user)
    years = years_response.years
    
    yearly_summaries = []
    cumulative_gap = 0.0
    
    for year in sorted(years):
        try:
            # Fetch actuals for each year
            actuals = await get_buy_borrow_die_actuals(year=year, db=db, user=user)
            
            # Only include years that have some data (income or spending > 0)
            if actuals.total_income > 0 or actuals.total_spending > 0:
                cumulative_gap += actuals.net_position
                
                yearly_summaries.append(YearSummary(
                    year=year,
                    total_income=actuals.total_income,
                    total_spending=actuals.total_spending,
                    net_position=actuals.net_position,
                    cumulative_gap=round(cumulative_gap, 2),
                    months_of_data=actuals.months_of_data
                ))
        except Exception as e:
            print(f"Error fetching data for year {year}: {e}")
            continue
    
    return AllYearsResponse(
        yearly_summaries=yearly_summaries,
        total_cumulative_gap=round(cumulative_gap, 2)
    )


@router.get("/buy-borrow-die/actuals/{year}")
async def get_buy_borrow_die_actuals(
    year: int = 2025,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get actual spending and income data for Buy/Borrow/Die tracking.
    
    Uses the SAME database as the Income page for consistency.
    Income includes: Options, Dividends, Interest from investment_transactions
    Plus: Salary and Rental from their respective services
    Spending: Tracked from CASH_MOVEMENT transactions in the database (withdrawals, transfers to spending)
    """
    from app.modules.income import db_queries as income_db
    from app.modules.income.salary_service import get_salary_service
    from app.modules.income.rental_service import get_rental_service
    
    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    
    # =========================================================================
    # INCOME: Get from database (same source as Income page)
    # =========================================================================

    # Get options income by month from database (all accounts)
    options_monthly = income_db.get_options_income_monthly(db, year=year)

    # Get dividend income by month from database (all accounts)
    dividends_monthly = income_db.get_dividend_income_monthly(db, year=year)

    # Get interest income by month from database (all accounts)
    interest_monthly = income_db.get_interest_income_monthly(db, year=year)

    # =========================================================================
    # TAXABLE INCOME: Exclude IRA, Roth IRA, and retirement accounts
    # =========================================================================

    # Get taxable options income (excludes IRA, Roth IRA, retirement)
    taxable_options_monthly = income_db.get_options_income_monthly(db, year=year, taxable_only=True)

    # Get taxable dividend income
    taxable_dividends_monthly = income_db.get_dividend_income_monthly(db, year=year, taxable_only=True)

    # Get taxable interest income
    taxable_interest_monthly = income_db.get_interest_income_monthly(db, year=year, taxable_only=True)
    
    # Get salary income from SalaryService (same as Income page)
    # Use get_salary_by_year() for simpler data access
    salary_monthly: Dict[int, float] = {}
    annual_salary = 0.0
    try:
        salary_service = get_salary_service(db=db)
        salary_by_year = salary_service.get_salary_by_year(year)
        # Sum up gross for all employees for this year
        annual_salary = salary_by_year.get('total_gross_income', 0.0)
        
        # Divide annual salary by 12 for even monthly distribution
        if annual_salary > 0:
            monthly_salary_amount = annual_salary / 12
            for m in range(1, 13):
                salary_monthly[m] = monthly_salary_amount
    except Exception as e:
        print(f"Error loading salary: {e}")
    
    # Get rental income from RentalService (same as Income page)
    # Use actual monthly data instead of dividing annual by 12
    rental_monthly: Dict[int, float] = {}
    try:
        rental_service = get_rental_service()
        rental_summary = rental_service.get_rental_summary()

        for prop in rental_summary.get('properties', []):
            if prop.get('year') == year:
                # Get expense ratio to convert gross monthly to net
                gross_income = prop.get('gross_income', 0)
                expense_ratio = prop.get('total_expenses', 0) / gross_income if gross_income > 0 else 0

                # Use actual monthly_income data
                for monthly in prop.get('monthly_income', []):
                    month_str = monthly.get('month', '')  # e.g., "2026-01"
                    if month_str:
                        try:
                            month_num = int(month_str.split('-')[1])
                            gross_amount = monthly.get('amount', 0)
                            # Convert gross to net using expense ratio
                            net_amount = gross_amount * (1 - expense_ratio)
                            rental_monthly[month_num] = rental_monthly.get(month_num, 0) + net_amount
                        except (IndexError, ValueError):
                            pass
    except Exception as e:
        print(f"Error loading rental: {e}")
    
    # =========================================================================
    # SPENDING: Get from database (CASH_MOVEMENT transactions)
    # =========================================================================
    # 
    # Spending is tracked from CASH_MOVEMENT transactions with negative amounts:
    # - ACH Withdrawal (negative amount + "Withdrawal" in description)
    # - XENT: Brokerage to Spending (negative amount + "Brokerage to Spending")
    # - XENT_CC: Credit Card balance payment (negative amount + "Credit Card")
    # - RTP: Instant bank transfer (negative amount)
    #
    # NOT counted as spending:
    # - ACH Deposit (positive = capital infusion)
    # - XENT: Spending to Brokerage (positive = refund, but we ignore per user preference)
    # - XENT_CC: Cash back (positive = small income, handled separately)
    # - INTERNAL_TRANSFER: Between own accounts (e.g., IRA transfers)
    # =========================================================================
    
    from app.modules.investments.models import InvestmentTransaction
    from sqlalchemy import extract, func, and_, or_
    
    monthly_spending: Dict[int, float] = {}
    
    # Query spending transactions from database
    # CASH_MOVEMENT with negative amount and spending-related descriptions
    spending_query = db.query(
        extract('month', InvestmentTransaction.transaction_date).label('month'),
        func.sum(func.abs(InvestmentTransaction.amount)).label('total')
    ).filter(
        extract('year', InvestmentTransaction.transaction_date) == year,
        InvestmentTransaction.transaction_type == 'CASH_MOVEMENT',
        InvestmentTransaction.amount < 0,  # Money leaving the account
        # Only count brokerage accounts (where spending happens), not retirement accounts
        InvestmentTransaction.account_id.in_(['neel_brokerage', 'jaya_brokerage']),
        # Filter for spending-related descriptions
        or_(
            InvestmentTransaction.description.ilike('%Withdrawal%'),
            InvestmentTransaction.description.ilike('%Brokerage to Spending%'),
            InvestmentTransaction.description.ilike('%Credit Card balance payment%'),
            InvestmentTransaction.description.ilike('%bank transfer%'),
        )
    ).group_by(
        extract('month', InvestmentTransaction.transaction_date)
    )
    
    for row in spending_query.all():
        month_num = int(row.month)
        monthly_spending[month_num] = float(row.total or 0)
    
    # =========================================================================
    # BUILD MONTHLY DATA
    # =========================================================================
    
    monthly_data = []
    cumulative_spending = 0.0
    cumulative_income = 0.0
    cumulative_net = 0.0
    months_with_data = 0

    total_options = 0.0
    total_dividends = 0.0
    total_interest = 0.0
    total_salary = 0.0
    total_rental = 0.0
    total_taxable = 0.0

    for month in range(1, 13):
        month_key = f"{year}-{month:02d}"

        spending = monthly_spending.get(month, 0.0)
        options_income = options_monthly.get(month_key, 0.0)
        dividend_income = dividends_monthly.get(month_key, 0.0)
        interest_income = interest_monthly.get(month_key, 0.0)
        salary_income = salary_monthly.get(month, 0.0)
        rental_income = rental_monthly.get(month, 0.0)

        # Taxable income (excludes IRA, Roth IRA, retirement accounts)
        taxable_options = taxable_options_monthly.get(month_key, 0.0)
        taxable_dividends = taxable_dividends_monthly.get(month_key, 0.0)
        taxable_interest = taxable_interest_monthly.get(month_key, 0.0)
        # Rental income is always taxable
        taxable_month = taxable_options + taxable_dividends + taxable_interest + rental_income

        # Track totals
        total_options += options_income
        total_dividends += dividend_income
        total_interest += interest_income
        total_salary += salary_income
        total_rental += rental_income
        total_taxable += taxable_month

        total_month_income = options_income + dividend_income + interest_income + salary_income + rental_income

        has_activity = spending > 0 or total_month_income > 0
        if has_activity:
            months_with_data += 1

        net_cash_flow = total_month_income - spending

        cumulative_spending += spending
        cumulative_income += total_month_income
        cumulative_net += net_cash_flow

        monthly_data.append(MonthlyActual(
            year=year,
            month=month,
            month_name=month_names[month],
            spending=round(spending, 2),
            income=round(total_month_income, 2),
            options_income=round(options_income, 2),
            dividend_income=round(dividend_income, 2),
            interest_income=round(interest_income, 2),
            rental_income=round(rental_income, 2),
            salary_income=round(salary_income, 2),
            net_cash_flow=round(net_cash_flow, 2),
            cumulative_net=round(cumulative_net, 2),
            cumulative_spending=round(cumulative_spending, 2),
            cumulative_income=round(cumulative_income, 2),
            # Taxable income fields
            taxable_options_income=round(taxable_options, 2),
            taxable_dividend_income=round(taxable_dividends, 2),
            taxable_interest_income=round(taxable_interest, 2),
            taxable_income=round(taxable_month, 2)
        ))
    
    # Calculate totals
    total_spending = cumulative_spending
    total_income = total_options + total_dividends + total_interest + total_salary + total_rental
    net_position = total_income - total_spending
    
    # Annualize based on months with data
    annualized_spending = (total_spending / months_with_data * 12) if months_with_data > 0 else 0
    annualized_income = (total_income / months_with_data * 12) if months_with_data > 0 else 0
    projected_annual_deficit = annualized_spending - annualized_income
    
    is_sustainable = net_position >= 0
    
    return BuyBorrowDieActuals(
        monthly_data=monthly_data,
        total_spending=round(total_spending, 2),
        total_income=round(total_income, 2),
        total_options_income=round(total_options, 2),
        total_interest_income=round(total_interest + total_dividends, 2),
        total_salary_income=round(total_salary + total_rental, 2),
        net_position=round(net_position, 2),
        monthly_salary=total_salary / months_with_data if months_with_data > 0 else 0,
        year=year,
        is_sustainable=is_sustainable,
        months_of_data=months_with_data,
        annualized_spending=round(annualized_spending, 2),
        annualized_income=round(annualized_income, 2),
        projected_annual_deficit=round(projected_annual_deficit, 2),
        total_taxable_income=round(total_taxable, 2)
    )


@router.get("/buy-borrow-die/spending-details/{year}")
async def get_spending_details(
    year: int = 2025,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get detailed spending transactions for Buy/Borrow/Die tracking.
    Returns individual transactions with date, account, amount, and description.
    """
    from app.modules.investments.models import InvestmentTransaction
    from sqlalchemy import extract, or_
    
    # Query spending transactions from database
    spending_transactions = db.query(InvestmentTransaction).filter(
        extract('year', InvestmentTransaction.transaction_date) == year,
        InvestmentTransaction.transaction_type == 'CASH_MOVEMENT',
        InvestmentTransaction.amount < 0,  # Money leaving the account
        # Only count brokerage accounts (where spending happens)
        InvestmentTransaction.account_id.in_(['neel_brokerage', 'jaya_brokerage']),
        # Filter for spending-related descriptions
        or_(
            InvestmentTransaction.description.ilike('%Withdrawal%'),
            InvestmentTransaction.description.ilike('%Brokerage to Spending%'),
            InvestmentTransaction.description.ilike('%Credit Card balance payment%'),
            InvestmentTransaction.description.ilike('%bank transfer%'),
        )
    ).order_by(InvestmentTransaction.transaction_date.desc()).all()
    
    # Format response
    transactions = []
    for txn in spending_transactions:
        # Map account_id to friendly name
        account_name = "Neel's Brokerage" if txn.account_id == 'neel_brokerage' else "Jaya's Brokerage"
        
        transactions.append({
            "date": txn.transaction_date.isoformat(),
            "account": account_name,
            "amount": abs(float(txn.amount)),  # Return positive for display
            "description": txn.description,
            "type": _categorize_spending(txn.description),
        })
    
    total = sum(t["amount"] for t in transactions)
    
    return {
        "year": year,
        "transactions": transactions,
        "total_spending": round(total, 2),
        "transaction_count": len(transactions),
    }


def _categorize_spending(description: str) -> str:
    """Categorize spending transaction by description."""
    desc_lower = description.lower()
    if 'credit card' in desc_lower:
        return 'Credit Card Payment'
    elif 'brokerage to spending' in desc_lower:
        return 'Transfer to Spending'
    elif 'withdrawal' in desc_lower:
        return 'ACH Withdrawal'
    elif 'bank transfer' in desc_lower:
        return 'Bank Transfer'
    else:
        return 'Other'


@router.post("/options-selling/income-projection")
async def calculate_options_income(
    params: dict,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Calculate potential income from selling covered calls."""
    
    # Default parameters
    default_premium = params.get("default_premium", 60)  # Default $60 per contract per week
    symbol_premiums = params.get("symbol_premiums", {})  # Per-symbol overrides: {"AAPL": 50, "TSLA": 150}
    delta = params.get("delta", 10)  # Delta 10 strategy
    weeks_per_year = params.get("weeks_per_year", 50)  # Assuming 2 weeks off

    # Load premium settings from database (auto-updated values)
    from app.modules.strategies.models import OptionPremiumSetting
    db_premiums = {}
    db_settings = db.query(OptionPremiumSetting).all()
    for setting in db_settings:
        if setting.premium_per_contract is not None:
            db_premiums[setting.symbol] = float(setting.premium_per_contract)

    # Default premiums by symbol (fallback if not in database)
    default_symbol_premiums = {
        "AAPL": 50,
        "TSLA": 150,
        "NVDA": 100,
        "IBIT": 40,
        "AVGO": 80,
        "COIN": 120,
        "PLTR": 60,
        "META": 90,
        "MSFT": 60,
        "MU": 70,
        "TSM": 50,
        "MSTR": 200,
    }
    
    # Merge: database settings (auto-updated) -> defaults -> user overrides
    # User overrides take highest priority
    effective_premiums = {**default_symbol_premiums, **db_premiums, **symbol_premiums}
    
    def get_premium(symbol):
        return effective_premiums.get(symbol, default_premium)
    
    # Get all stock holdings by account
    # Join on BOTH account_id AND source to avoid duplicates from accounts with same ID but different sources
    result = db.execute(text("""
        SELECT 
            ia.account_id,
            ia.account_name,
            ia.account_type,
            ih.symbol,
            ih.quantity,
            ih.current_price,
            ih.market_value,
            ih.description
        FROM investment_holdings ih
        JOIN investment_accounts ia ON ih.account_id = ia.account_id AND ih.source = ia.source
        WHERE ih.quantity > 0 
        AND ih.symbol NOT LIKE '%CASH%' 
        AND ih.symbol NOT LIKE '%MONEY%'
        AND ih.symbol NOT LIKE '%FDRXX%'
        AND ia.account_type IN ('brokerage', 'retirement', 'ira', 'roth_ira')
        ORDER BY ia.account_name, ih.market_value DESC
    """))
    
    accounts = {}
    account_order = []
    
    # Also aggregate by symbol across all accounts
    symbols = {}
    
    for row in result:
        account_id, account_name, account_type, symbol, qty, price, value, description = row
        qty = float(qty) if qty else 0
        price = float(price) if price else 0
        value = float(value) if value else 0
        
        # Skip if less than 100 shares
        if qty < 100:
            continue
            
        options_count = int(qty // 100)
        
        # Aggregate by symbol (for overview)
        if symbol not in symbols:
            symbols[symbol] = {
                "symbol": symbol,
                "description": description or symbol,
                "shares": 0,
                "price": price,
                "value": 0,
                "options": 0,
                "premium_per_contract": get_premium(symbol),
                "weekly_income": 0,
                "monthly_income": 0,
                "yearly_income": 0,
                "accounts": []  # Track which accounts have this symbol
            }
        
        symbols[symbol]["shares"] += qty
        symbols[symbol]["value"] += value
        symbols[symbol]["price"] = price  # Use latest price
        if account_name not in symbols[symbol]["accounts"]:
            symbols[symbol]["accounts"].append(account_name)
        
        # Account-level aggregation
        if account_name not in accounts:
            account_order.append(account_name)
            accounts[account_name] = {
                "account_id": account_id,
                "account_name": account_name,
                "account_type": account_type,
                "holdings": [],
                "total_value": 0,
                "total_shares": 0,
                "total_options": 0,
                "weekly_income": 0,
                "monthly_income": 0,
                "yearly_income": 0
            }
        
        # Check if symbol already exists in this account (merge duplicates)
        symbol_premium = get_premium(symbol)
        existing = next((h for h in accounts[account_name]["holdings"] if h["symbol"] == symbol), None)
        if existing:
            existing["shares"] += qty
            existing["value"] += value
            existing["options"] = int(existing["shares"] // 100)
            existing["weekly_income"] = existing["options"] * symbol_premium
            existing["monthly_income"] = existing["weekly_income"] * 4
            existing["yearly_income"] = existing["weekly_income"] * weeks_per_year
        else:
            weekly = options_count * symbol_premium
            accounts[account_name]["holdings"].append({
                "symbol": symbol,
                "description": description or symbol,
                "shares": qty,
                "price": round(price, 2),
                "value": round(value, 0),
                "options": options_count,
                "premium_per_contract": symbol_premium,
                "weekly_income": weekly,
                "monthly_income": weekly * 4,
                "yearly_income": weekly * weeks_per_year
            })
        
        accounts[account_name]["total_value"] += value
        accounts[account_name]["total_shares"] += qty
    
    # Calculate totals for symbols using per-symbol premiums
    for sym in symbols:
        symbols[sym]["options"] = int(symbols[sym]["shares"] // 100)
        symbol_premium = symbols[sym]["premium_per_contract"]
        symbols[sym]["weekly_income"] = symbols[sym]["options"] * symbol_premium
        symbols[sym]["monthly_income"] = symbols[sym]["weekly_income"] * 4
        symbols[sym]["yearly_income"] = symbols[sym]["weekly_income"] * weeks_per_year
        symbols[sym]["value"] = round(symbols[sym]["value"], 0)
        symbols[sym]["shares"] = int(symbols[sym]["shares"])
        symbols[sym]["account_count"] = len(symbols[sym]["accounts"])
    
    # Sort symbols by options count (descending)
    symbols_list = sorted(symbols.values(), key=lambda x: x["options"], reverse=True)
    
    # Calculate totals for each account
    for account_name in accounts:
        account = accounts[account_name]
        account["total_options"] = sum(h["options"] for h in account["holdings"])
        account["weekly_income"] = sum(h["weekly_income"] for h in account["holdings"])
        account["monthly_income"] = account["weekly_income"] * 4
        account["yearly_income"] = account["weekly_income"] * weeks_per_year
        account["total_value"] = round(account["total_value"], 0)
    
    # Calculate portfolio totals
    total_options = sum(a["total_options"] for a in accounts.values())
    total_weekly = sum(a["weekly_income"] for a in accounts.values())
    total_monthly = total_weekly * 4
    total_yearly = total_weekly * weeks_per_year
    total_value = sum(a["total_value"] for a in accounts.values())
    
    # Yield calculation
    weekly_yield = (total_weekly / total_value * 100) if total_value > 0 else 0
    yearly_yield = (total_yearly / total_value * 100) if total_value > 0 else 0
    
    return {
        "params": {
            "default_premium": default_premium,
            "symbol_premiums": {s["symbol"]: s["premium_per_contract"] for s in symbols.values()},
            "delta": delta,
            "weeks_per_year": weeks_per_year
        },
        "portfolio_summary": {
            "total_value": round(total_value, 0),
            "total_options": total_options,
            "weekly_income": round(total_weekly, 0),
            "monthly_income": round(total_monthly, 0),
            "yearly_income": round(total_yearly, 0),
            "weekly_yield_percent": round(weekly_yield, 3),
            "yearly_yield_percent": round(yearly_yield, 2)
        },
        "symbols": symbols_list,
        "accounts": [accounts[name] for name in account_order if accounts[name]["total_options"] > 0]
    }


@router.get("/buy-borrow-die/current-capital")
async def get_current_capital(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Get current capital account values."""
    result = db.execute(text("""
        SELECT 
            ia.account_name,
            ia.account_type,
            COALESCE(SUM(ih.market_value), 0) as total_value,
            COALESCE(SUM(ih.cost_basis), 0) as cost_basis
        FROM investment_accounts ia
        LEFT JOIN investment_holdings ih ON ia.account_id = ih.account_id
        WHERE ia.account_type = 'brokerage'
        GROUP BY ia.account_name, ia.account_type
        ORDER BY total_value DESC
    """))
    
    accounts = []
    total_value = 0
    total_cost_basis = 0
    
    for row in result:
        name, acct_type, value, cost_basis = row
        value = float(value) if value else 0
        cost_basis = float(cost_basis) if cost_basis else 0
        total_value += value
        total_cost_basis += cost_basis
        accounts.append({
            "account_name": name,
            "account_type": acct_type,
            "market_value": round(value, 0),
            "cost_basis": round(cost_basis, 0),
            "unrealized_gain": round(value - cost_basis, 0)
        })
    
    return {
        "accounts": accounts,
        "total_market_value": round(total_value, 0),
        "total_cost_basis": round(total_cost_basis, 0),
        "total_unrealized_gain": round(total_value - total_cost_basis, 0),
        "margin_available_76pct": round(total_value * 0.76, 0)
    }


@router.get("/buy-borrow-die/expense-forecast")
async def get_expense_forecast(
    months_ahead: int = Query(default=3, ge=1, le=12, description="Months to forecast"),
    historical_years: int = Query(default=2, ge=1, le=5, description="Years of history to analyze"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Forecast future expenses based on historical spending patterns.

    Analyzes recurring expense patterns (similar amounts, regular timing)
    and predicts future expenses with dates and confidence levels.

    Query parameters:
    - months_ahead: How many months to forecast (1-12, default 3)
    - historical_years: Years of history to analyze (1-5, default 2)

    Returns:
    - Forecasted expenses by month with predicted amounts and dates
    - Recurring expense patterns identified
    - Confidence levels based on consistency
    """
    from app.modules.strategies.expense_forecasting_service import ExpenseForecastingService

    try:
        current_year = datetime.now().year
        service = ExpenseForecastingService()

        forecast = service.forecast_expenses(
            year=current_year,
            months_ahead=months_ahead,
            historical_years=historical_years
        )

        return forecast
    except Exception as e:
        # If CSV files don't exist or other error, return empty forecast
        return {
            "forecast_period": {
                "start_month": None,
                "end_month": None,
                "months_ahead": months_ahead
            },
            "forecasted_months": [],
            "summary": {
                "total_recurring_expenses_identified": 0,
                "avg_monthly_recurring_spending": 0,
                "historical_years_analyzed": historical_years,
                "total_transactions_analyzed": 0
            },
            "recurring_patterns": [],
            "error": str(e),
            "note": "No expense data available for forecasting. Import transactions to enable forecasting."
        }


# ── BBD Assumptions vs Reality ────────────────────────────────

@router.get("/buy-borrow-die/assumptions/metrics")
async def get_bbd_assumption_metrics(
    metric_type: str,
    period_type: str = 'year',
    year: int = None,
    month: int = None,
    db: Session = Depends(get_db),
):
    """
    Get cached BBD performance metrics for Assumptions vs Reality.

    metric_type: 'portfolio_growth' or 'options_yield'
    period_type: 'year', 'month', or 'week'
    year: optional filter for drill-down
    month: optional filter for drill-down (requires year)
    """
    from app.modules.strategies.bbd_performance_service import BbdPerformanceService

    service = BbdPerformanceService(db)

    # Auto-compute incremental metrics so new months are always available
    service.compute_all(force=False)
    db.commit()

    metrics = service.get_metrics(metric_type, period_type, year, month)

    # For growth metrics, exclude the current in-progress month to avoid misleading partial returns.
    # For options_yield, keep partial months so the income page can show expected income and
    # capital baseline for the current month even before the month completes.
    if period_type == 'month' and metric_type in ('portfolio_growth', 'pure_growth'):
        metrics = [m for m in metrics if m.get('data_completeness') != 'partial']

    if metric_type == 'portfolio_growth':
        assumed_rate = '20%/year (8% growth + 12% options income)'
    elif metric_type == 'pure_growth':
        assumed_rate = '8%/year (market appreciation only)'
    elif metric_type == 'options_yield':
        assumed_rate = '1%/month (12%/year), all investment income'
    elif metric_type.startswith('income_'):
        assumed_rate = 'no target for a single stream'
    elif metric_type.startswith('expense_'):
        assumed_rate = 'sustainable draw: portfolio × (combined − margin) / 12 per month'
    elif metric_type.startswith('net'):
        assumed_rate = 'break-even (0)'
    else:
        assumed_rate = '5% margin interest'

    return {
        'metric_type': metric_type,
        'period_type': period_type,
        'assumed_rate': assumed_rate,
        'metrics': metrics,
    }



@router.get("/buy-borrow-die/settings")
async def get_bbd_settings(db: Session = Depends(get_db)):
    """Return the current BBD configurable assumptions."""
    from app.modules.strategies.bbd_performance_service import BbdPerformanceService
    svc = BbdPerformanceService(db)
    return {
        'assumed_annual_growth': float(svc.ASSUMED_ANNUAL_GROWTH),
        'assumed_combined_return': float(svc.ASSUMED_COMBINED_RETURN),
        'assumed_monthly_yield': float(svc.ASSUMED_MONTHLY_YIELD),
        'assumed_annual_margin_rate': float(svc.ASSUMED_ANNUAL_MARGIN_RATE),
        'margin_ltv': svc.MARGIN_LTV,
    }


class BbdSettingsUpdate(BaseModel):
    assumed_annual_growth: float
    assumed_combined_return: float
    assumed_monthly_yield: float
    assumed_annual_margin_rate: float
    margin_ltv: float


@router.put("/buy-borrow-die/settings")
async def update_bbd_settings(payload: BbdSettingsUpdate, db: Session = Depends(get_db)):
    """Update BBD assumptions and trigger a full recompute."""
    try:
        db.execute(text(
            "UPDATE bbd_settings SET "
            "assumed_annual_growth=:g, assumed_combined_return=:cr, "
            "assumed_monthly_yield=:y, assumed_annual_margin_rate=:r, "
            "margin_ltv=:ltv, updated_at=NOW() WHERE id=1"
        ), {
            'g': payload.assumed_annual_growth,
            'cr': payload.assumed_combined_return,
            'y': payload.assumed_monthly_yield,
            'r': payload.assumed_annual_margin_rate,
            'ltv': payload.margin_ltv,
        })
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"PUT /buy-borrow-die/settings failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    from app.modules.strategies.bbd_performance_service import BbdPerformanceService
    svc = BbdPerformanceService(db)
    count = svc.compute_all(force=True)
    return {'status': 'saved', 'periods_recomputed': count}


@router.post("/buy-borrow-die/assumptions/compute")
async def compute_bbd_assumptions(
    force: bool = False,
    db: Session = Depends(get_db),
):
    """
    Trigger computation of BBD performance metrics.
    Incremental by default — only computes missing or partial periods.
    Set force=True to recompute everything.
    """
    from app.modules.strategies.bbd_performance_service import BbdPerformanceService, BbdIdentityError

    service = BbdPerformanceService(db)
    try:
        count = service.compute_all(force=force)
    except BbdIdentityError as e:
        # Inconsistent cards are never cached: roll back so the page keeps
        # the previous numbers, and say exactly which periods broke.
        db.rollback()
        raise HTTPException(status_code=409, detail={
            'status': 'identity_violation',
            'message': str(e),
            'violations': e.violations,
        })
    db.commit()

    return {
        'status': 'ok',
        'periods_computed': count,
        'force': force,
        'identity_check': 'combined growth = pure growth + options income, every year and month, within $1',
    }


@router.get("/buy-borrow-die/assumptions/summary")
async def get_bbd_assumptions_summary(
    db: Session = Depends(get_db),
):
    """
    Get high-level summary for BBD Assumptions vs Reality cards.
    Returns overall CAGR vs 8%, avg monthly yield vs 1%, latest values.
    """
    from app.modules.strategies.bbd_performance_service import BbdPerformanceService

    service = BbdPerformanceService(db)
    return service.get_summary()


@router.get("/buy-borrow-die/assumptions/taxable-capital")
async def get_taxable_capital_by_month(
    db: Session = Depends(get_db),
):
    """
    Get monthly brokerage-only (taxable) portfolio values.
    Returns {months: {YYYY-MM: value}}.
    """
    from app.modules.strategies.bbd_performance_service import BbdPerformanceService

    service = BbdPerformanceService(db)
    account_months = service._get_account_month_values()
    brokerage_months = service._get_brokerage_month_values(account_months)
    return {'months': {k: round(v, 2) for k, v in sorted(brokerage_months.items())}}


@router.get("/buy-borrow-die/benchmark")
async def get_bbd_benchmark(symbol: str = 'QQQ', db: Session = Depends(get_db)):
    """The two brokerages vs a buy-and-hold twin of `symbol` with identical
    cash flows — docs/BBD-BENCHMARK-SPEC.md."""
    from app.modules.strategies.bbd_benchmark_service import get_benchmark
    symbol = symbol.upper()
    if symbol not in ('QQQ', 'SPY'):
        raise HTTPException(status_code=400, detail="symbol must be QQQ or SPY")
    return get_benchmark(db, symbol)


@router.get("/buy-borrow-die/timeline")
async def get_bbd_timeline(
    time_range: str = Query('data', regex='^(data|5y|10y|20y|30y|all)$'),
    income_offset: bool = Query(False),
    growth_rate: Optional[float] = Query(None, description="Annual growth rate as decimal, e.g. 0.08 for 8%"),
    margin_rate: Optional[float] = Query(None, description="Annual margin interest rate as decimal, e.g. 0.05 for 5%"),
    margin_ltv: Optional[float] = Query(None, description="Margin LTV ratio as decimal, e.g. 0.70 for 70%"),
    options_yield: Optional[float] = Query(None, description="Monthly options yield as decimal, e.g. 0.01 for 1%"),
    db: Session = Depends(get_db),
):
    """
    Get timeline data for the BBD chart.
    Combines actual monthly data with optional forward projections.
    All assumption parameters are optional; defaults used when not provided.
    """
    from app.modules.strategies.bbd_performance_service import BbdPerformanceService

    service = BbdPerformanceService(db)
    return service.get_timeline_data(
        time_range,
        income_offset=income_offset,
        growth_rate=growth_rate,
        margin_rate=margin_rate,
        margin_ltv=margin_ltv,
        options_yield=options_yield,
    )


# Retirement contribution limits (2015-2026)
# Historical data for accurate tracking
RETIREMENT_LIMITS = {
    2015: {
        "ira": 5500, "ira_catchup": 6500, "roth_ira": 5500, "roth_ira_catchup": 6500,
        "401k": 18000, "401k_catchup": 24000, "401k_employer_match": 53000,
        "hsa": 3350, "hsa_family": 6650, "hsa_catchup": 1000,
        "529": 14000, "custodial_ira": 5500,
    },
    2016: {
        "ira": 5500, "ira_catchup": 6500, "roth_ira": 5500, "roth_ira_catchup": 6500,
        "401k": 18000, "401k_catchup": 24000, "401k_employer_match": 53000,
        "hsa": 3350, "hsa_family": 6750, "hsa_catchup": 1000,
        "529": 14000, "custodial_ira": 5500,
    },
    2017: {
        "ira": 5500, "ira_catchup": 6500, "roth_ira": 5500, "roth_ira_catchup": 6500,
        "401k": 18000, "401k_catchup": 24000, "401k_employer_match": 54000,
        "hsa": 3400, "hsa_family": 6750, "hsa_catchup": 1000,
        "529": 14000, "custodial_ira": 5500,
    },
    2018: {
        "ira": 5500, "ira_catchup": 6500, "roth_ira": 5500, "roth_ira_catchup": 6500,
        "401k": 18500, "401k_catchup": 24500, "401k_employer_match": 55000,
        "hsa": 3450, "hsa_family": 6900, "hsa_catchup": 1000,
        "529": 15000, "custodial_ira": 5500,
    },
    2019: {
        "ira": 6000, "ira_catchup": 7000, "roth_ira": 6000, "roth_ira_catchup": 7000,
        "401k": 19000, "401k_catchup": 25000, "401k_employer_match": 56000,
        "hsa": 3500, "hsa_family": 7000, "hsa_catchup": 1000,
        "529": 15000, "custodial_ira": 6000,
    },
    2020: {
        "ira": 6000, "ira_catchup": 7000, "roth_ira": 6000, "roth_ira_catchup": 7000,
        "401k": 19500, "401k_catchup": 26000, "401k_employer_match": 57000,
        "hsa": 3550, "hsa_family": 7100, "hsa_catchup": 1000,
        "529": 15000, "custodial_ira": 6000,
    },
    2021: {
        "ira": 6000, "ira_catchup": 7000, "roth_ira": 6000, "roth_ira_catchup": 7000,
        "401k": 19500, "401k_catchup": 26000, "401k_employer_match": 58000,
        "hsa": 3600, "hsa_family": 7200, "hsa_catchup": 1000,
        "529": 15000, "custodial_ira": 6000,
    },
    2022: {
        "ira": 6000, "ira_catchup": 7000, "roth_ira": 6000, "roth_ira_catchup": 7000,
        "401k": 20500, "401k_catchup": 27000, "401k_employer_match": 61000,
        "hsa": 3650, "hsa_family": 7300, "hsa_catchup": 1000,
        "529": 16000, "custodial_ira": 6000,
    },
    2023: {
        "ira": 6500, "ira_catchup": 7500, "roth_ira": 6500, "roth_ira_catchup": 7500,
        "401k": 22500, "401k_catchup": 30000, "401k_employer_match": 66000,
        "hsa": 3850, "hsa_family": 7750, "hsa_catchup": 1000,
        "529": 17000, "custodial_ira": 6500,
    },
    2024: {
        "ira": 7000, "ira_catchup": 8000, "roth_ira": 7000, "roth_ira_catchup": 8000,
        "401k": 23000, "401k_catchup": 30500, "401k_employer_match": 69000,
        "hsa": 4150, "hsa_family": 8300, "hsa_catchup": 1000,
        "529": 18000, "custodial_ira": 7000,
    },
    2025: {
        "ira": 7000, "ira_catchup": 8000, "roth_ira": 7000, "roth_ira_catchup": 8000,
        "401k": 23500, "401k_catchup": 31000, "401k_employer_match": 70000,
        "hsa": 4300, "hsa_family": 8550, "hsa_catchup": 1000,
        "529": 18000, "custodial_ira": 7000,
    },
    2026: {
        "ira": 7000, "ira_catchup": 8000, "roth_ira": 7000, "roth_ira_catchup": 8000,
        "401k": 23500, "401k_catchup": 31000, "401k_employer_match": 70000,
        "hsa": 4300, "hsa_family": 8550, "hsa_catchup": 1000,
        "529": 18000, "custodial_ira": 7000,
    }
}


@router.get("/retirement-contributions/analysis")
async def get_retirement_contributions_analysis(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Analyze retirement contributions (IRA, Roth IRA, 401k) over time.
    Returns historical contributions from IRS Wage & Income Transcripts (authoritative source)
    and optimization recommendations.
    """
    try:
        # Query the retirement_contributions table (populated from IRS transcripts)
        # This is the AUTHORITATIVE source for contribution data
        from app.modules.income.models import RetirementContribution
        
        records = db.query(RetirementContribution).order_by(
            RetirementContribution.tax_year.desc()
        ).all()
        
        # Build yearly summary from IRS transcript data
        years_data = []
        contributions_by_year = {}
        
        for record in records:
            year = record.tax_year
            owner = record.owner
            
            if year not in contributions_by_year:
                contributions_by_year[year] = {}
            
            contributions_by_year[year][owner] = {
                "ira": float(record.ira_contributions or 0),
                "roth_ira": float(record.roth_ira_contributions or 0),
                "401k": float(record.contributions_401k or 0),
                "hsa": float(record.hsa_contributions or 0),
                "rollover": float(record.rollover_contributions or 0),
                "sep": float(record.sep_contributions or 0),
                "simple": float(record.simple_contributions or 0),
                "ira_fmv": record.ira_fmv or [],
                "wages": float(record.total_wages or 0),
            }
        
        all_years = sorted(contributions_by_year.keys(), reverse=True)
        
        for year in all_years:
            neel_data = contributions_by_year[year].get("Neel", {})
            jaya_data = contributions_by_year[year].get("Jaya", {})
            
            year_data = {
                "year": year,
                "neel": {
                    "ira": neel_data.get("ira", 0),
                    "roth_ira": neel_data.get("roth_ira", 0),
                    "401k": neel_data.get("401k", 0),
                    "hsa": neel_data.get("hsa", 0),
                },
                "jaya": {
                    "ira": jaya_data.get("ira", 0),
                    "roth_ira": jaya_data.get("roth_ira", 0),
                    "401k": jaya_data.get("401k", 0),
                    "hsa": jaya_data.get("hsa", 0),
                }
            }
            
            # Calculate totals
            year_data["neel"]["total"] = sum([
                year_data["neel"]["ira"],
                year_data["neel"]["roth_ira"],
                year_data["neel"]["401k"],
                year_data["neel"]["hsa"],
            ])
            year_data["jaya"]["total"] = sum([
                year_data["jaya"]["ira"],
                year_data["jaya"]["roth_ira"],
                year_data["jaya"]["401k"],
                year_data["jaya"]["hsa"],
            ])
            year_data["family_total"] = year_data["neel"]["total"] + year_data["jaya"]["total"]
            
            # Get limits for this year
            limits = RETIREMENT_LIMITS.get(year, RETIREMENT_LIMITS[2025])
            
            # Calculate what's remaining (assuming both under 50 for now)
            year_data["neel"]["ira_limit"] = limits["ira"]
            year_data["neel"]["roth_ira_limit"] = limits["roth_ira"]
            year_data["neel"]["401k_limit"] = limits["401k"]
            year_data["neel"]["ira_remaining"] = max(0, limits["ira"] - year_data["neel"]["ira"])
            year_data["neel"]["roth_ira_remaining"] = max(0, limits["roth_ira"] - year_data["neel"]["roth_ira"])
            year_data["neel"]["401k_remaining"] = max(0, limits["401k"] - year_data["neel"]["401k"])
            
            year_data["jaya"]["ira_limit"] = limits["ira"]
            year_data["jaya"]["roth_ira_limit"] = limits["roth_ira"]
            year_data["jaya"]["401k_limit"] = limits["401k"]
            year_data["jaya"]["ira_remaining"] = max(0, limits["ira"] - year_data["jaya"]["ira"])
            year_data["jaya"]["roth_ira_remaining"] = max(0, limits["roth_ira"] - year_data["jaya"]["roth_ira"])
            year_data["jaya"]["401k_remaining"] = max(0, limits["401k"] - year_data["jaya"]["401k"])
            
            years_data.append(year_data)
        
        # Calculate maximum annual contributions for family
        current_year = 2026
        limits_2026 = RETIREMENT_LIMITS[2026]
        
        max_annual_contributions = {
            "neel": {
                "ira": limits_2026["ira"],
                "roth_ira": limits_2026["roth_ira"],
                "401k": limits_2026["401k"],
                "hsa": limits_2026["hsa"],
                "total": limits_2026["ira"] + limits_2026["roth_ira"] + limits_2026["401k"] + limits_2026["hsa"]
            },
            "jaya": {
                "ira": limits_2026["ira"],
                "roth_ira": limits_2026["roth_ira"],
                "401k": limits_2026["401k"],
                "hsa": limits_2026["hsa"],
                "total": limits_2026["ira"] + limits_2026["roth_ira"] + limits_2026["401k"] + limits_2026["hsa"]
            },
            "kids": {
                "529_per_child": limits_2026["529"],
                "custodial_ira": limits_2026["custodial_ira"],
                "note": "529 contributions can be front-loaded up to 5 years ($90K per child)"
            },
            "family_total": (limits_2026["ira"] + limits_2026["roth_ira"] + limits_2026["401k"] + limits_2026["hsa"]) * 2
        }
        
        # Build 2026 recommendations
        recommendations_2026 = {
            "neel": {
                "ira": {
                    "recommended": limits_2026["ira"],
                    "current": 0,  # Will be updated if 2026 data exists
                    "remaining": limits_2026["ira"],
                    "priority": "high"
                },
                "roth_ira": {
                    "recommended": limits_2026["roth_ira"],
                    "current": 0,
                    "remaining": limits_2026["roth_ira"],
                    "priority": "high"
                },
                "401k": {
                    "recommended": limits_2026["401k"],
                    "current": 0,
                    "remaining": limits_2026["401k"],
                    "priority": "high"
                },
                "hsa": {
                    "recommended": limits_2026["hsa"],
                    "current": 0,
                    "remaining": limits_2026["hsa"],
                    "priority": "medium"
                }
            },
            "jaya": {
                "ira": {
                    "recommended": limits_2026["ira"],
                    "current": 0,
                    "remaining": limits_2026["ira"],
                    "priority": "high"
                },
                "roth_ira": {
                    "recommended": limits_2026["roth_ira"],
                    "current": 0,
                    "remaining": limits_2026["roth_ira"],
                    "priority": "high"
                },
                "401k": {
                    "recommended": limits_2026["401k"],
                    "current": 0,
                    "remaining": limits_2026["401k"],
                    "priority": "high"
                },
                "hsa": {
                    "recommended": limits_2026["hsa"],
                    "current": 0,
                    "remaining": limits_2026["hsa"],
                    "priority": "medium"
                }
            },
            "kids": {
                "529_plans": {
                    "recommended": limits_2026["529"],
                    "note": "Consider front-loading 5 years ($90K per child) if you have the cash flow",
                    "priority": "medium"
                },
                "custodial_ira": {
                    "recommended": limits_2026["custodial_ira"],
                    "note": "Only if child has earned income",
                    "priority": "low"
                }
            }
        }
        
        # Update 2026 recommendations if data exists
        if years_data and years_data[0]["year"] == 2026:
            current_2026 = years_data[0]
            for person in ["neel", "jaya"]:
                person_data = current_2026[person]
                recommendations_2026[person]["ira"]["current"] = person_data["ira"]
                recommendations_2026[person]["ira"]["remaining"] = person_data["ira_remaining"]
                recommendations_2026[person]["roth_ira"]["current"] = person_data["roth_ira"]
                recommendations_2026[person]["roth_ira"]["remaining"] = person_data["roth_ira_remaining"]
                recommendations_2026[person]["401k"]["current"] = person_data["401k"]
                recommendations_2026[person]["401k"]["remaining"] = person_data["401k_remaining"]
        
        # Get current portfolio values from portfolio_snapshots
        current_values = {
            "neel": {"retirement": 0, "ira": 0, "roth_ira": 0, "hsa": 0, "total": 0},
            "jaya": {"retirement": 0, "ira": 0, "roth_ira": 0, "hsa": 0, "total": 0},
            "family": {"hsa": 0, "total": 0},
            "as_of_date": None
        }
        
        try:
            # Get latest portfolio values for retirement accounts
            snapshot_query = db.execute(text("""
                SELECT DISTINCT ON (owner, account_type)
                    owner, account_type, portfolio_value, statement_date
                FROM portfolio_snapshots
                WHERE account_type IN ('retirement', 'ira', 'roth_ira', 'hsa')
                ORDER BY owner, account_type, statement_date DESC
            """))
            
            latest_date = None
            for row in snapshot_query:
                owner = row[0].lower() if row[0] else ""
                account_type = row[1]
                value = float(row[2]) if row[2] else 0
                stmt_date = row[3]
                
                if stmt_date and (latest_date is None or stmt_date > latest_date):
                    latest_date = stmt_date
                
                if "neel" in owner:
                    if account_type == "retirement":
                        current_values["neel"]["retirement"] = value
                    elif account_type == "ira":
                        current_values["neel"]["ira"] = value
                    elif account_type == "roth_ira":
                        current_values["neel"]["roth_ira"] = value
                    elif account_type == "hsa":
                        current_values["neel"]["hsa"] = value
                elif "jaya" in owner:
                    if account_type == "retirement":
                        current_values["jaya"]["retirement"] = value
                    elif account_type == "ira":
                        current_values["jaya"]["ira"] = value
                    elif account_type == "roth_ira":
                        current_values["jaya"]["roth_ira"] = value
                    elif account_type == "hsa":
                        current_values["jaya"]["hsa"] = value
                elif "family" in owner or "agrawal" in owner:
                    if account_type == "hsa":
                        current_values["family"]["hsa"] = value
            
            # Calculate totals
            current_values["neel"]["total"] = sum([
                current_values["neel"]["retirement"],
                current_values["neel"]["ira"],
                current_values["neel"]["roth_ira"],
                current_values["neel"]["hsa"],
            ])
            current_values["jaya"]["total"] = sum([
                current_values["jaya"]["retirement"],
                current_values["jaya"]["ira"],
                current_values["jaya"]["roth_ira"],
                current_values["jaya"]["hsa"],
            ])
            current_values["family"]["total"] = (
                current_values["neel"]["total"] + 
                current_values["jaya"]["total"] + 
                current_values["family"]["hsa"]
            )
            current_values["as_of_date"] = latest_date.isoformat() if latest_date else None
            
        except Exception as e:
            print(f"Error fetching current values: {e}")
        
        # Calculate all-time totals and growth
        all_time_totals = {
            "neel": {
                "contributions": sum(y["neel"]["total"] for y in years_data),
                "current_value": current_values["neel"]["total"],
            },
            "jaya": {
                "contributions": sum(y["jaya"]["total"] for y in years_data),
                "current_value": current_values["jaya"]["total"],
            },
        }
        
        # Calculate growth
        for person in ["neel", "jaya"]:
            contributions = all_time_totals[person]["contributions"]
            current = all_time_totals[person]["current_value"]
            growth = current - contributions
            growth_pct = (growth / contributions * 100) if contributions > 0 else 0
            all_time_totals[person]["growth"] = growth
            all_time_totals[person]["growth_percent"] = round(growth_pct, 1)
        
        all_time_totals["family"] = {
            "contributions": all_time_totals["neel"]["contributions"] + all_time_totals["jaya"]["contributions"],
            "current_value": current_values["family"]["total"],
            "growth": current_values["family"]["total"] - (all_time_totals["neel"]["contributions"] + all_time_totals["jaya"]["contributions"]),
        }
        if all_time_totals["family"]["contributions"] > 0:
            all_time_totals["family"]["growth_percent"] = round(
                all_time_totals["family"]["growth"] / all_time_totals["family"]["contributions"] * 100, 1
            )
        else:
            all_time_totals["family"]["growth_percent"] = 0
        
        return {
            "years_data": years_data,
            "max_annual_contributions": max_annual_contributions,
            "recommendations_2026": recommendations_2026,
            "current_values": current_values,
            "all_time_totals": all_time_totals,
            "summary": {
                "years_analyzed": len(years_data),
                "earliest_year": min(all_years) if all_years else None,
                "latest_year": max(all_years) if all_years else None,
            }
        }
    except Exception as e:
        import traceback
        error_detail = str(e)
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error analyzing retirement contributions: {error_detail}"
        )


# ============================================================================
# SOLD OPTIONS TRACKING ENDPOINTS
# ============================================================================
# Note: The /sold-options/parse-text endpoint has been removed.
# Use the unified parser at /api/v1/ingestion/robinhood-paste/save instead.
# ============================================================================

@router.get("/sold-options/current")
async def get_current_sold_options_data(
    source: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get the most recent sold options data.
    
    Returns:
    - Snapshot info (when the data was uploaded)
    - List of sold options
    - Options grouped by symbol
    - Summary statistics
    """
    return get_current_sold_options(db, source)


@router.get("/sold-options/snapshots")
async def list_options_snapshots(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    List recent options screenshot uploads.
    """
    snapshots = db.query(SoldOptionsSnapshot).order_by(
        SoldOptionsSnapshot.snapshot_date.desc()
    ).limit(limit).all()
    
    return {
        "snapshots": [
            {
                "id": s.id,
                "source": s.source,
                "account_name": s.account_name,
                "snapshot_date": s.snapshot_date.isoformat(),
                "parsing_status": s.parsing_status,
                "options_count": len(s.options) if s.options else 0,
                "created_at": _format_dt_as_utc(s.created_at)
            }
            for s in snapshots
        ]
    }


@router.delete("/sold-options/snapshot/{snapshot_id}")
async def delete_options_snapshot(
    snapshot_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Delete a snapshot and all its associated options.
    """
    snapshot = db.query(SoldOptionsSnapshot).filter(
        SoldOptionsSnapshot.id == snapshot_id
    ).first()
    
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    db.delete(snapshot)
    db.commit()
    
    return {"success": True, "deleted_id": snapshot_id}


# ============================================================================
# ACTUAL INCOME CALCULATION HELPERS
# ============================================================================
# These functions calculate actual historical income from the InvestmentTransaction
# table rather than projecting based on options * premium.

def get_actual_options_income(db: Session, start_date: date, end_date: date, option_type: str = 'call') -> Dict[str, Dict[str, float]]:
    """
    Get actual options income (STO/BTC transactions) for a date range.

    Args:
        db: Database session
        start_date: Start of date range
        end_date: End of date range
        option_type: 'call' or 'put' - filters by description containing 'Call' or 'Put'

    Returns:
        Dict mapping account_name -> {symbol -> total_income}
    """
    from app.modules.investments.models import InvestmentTransaction, InvestmentAccount
    from sqlalchemy import and_

    # Filter pattern based on option type
    type_filter = 'Call' if option_type == 'call' else 'Put'

    # Query STO (Sell To Open) and BTC (Buy To Close) transactions
    # STO generates income (positive), BTC is buyback (usually negative)
    # Filter by description to separate calls from puts
    results = db.query(
        InvestmentAccount.account_name,
        InvestmentTransaction.symbol,
        func.sum(InvestmentTransaction.amount).label('total')
    ).join(
        InvestmentAccount,
        and_(
            InvestmentTransaction.account_id == InvestmentAccount.account_id,
            InvestmentTransaction.source == InvestmentAccount.source
        )
    ).filter(
        InvestmentTransaction.transaction_type.in_(['STO', 'BTC']),
        InvestmentTransaction.transaction_date >= start_date,
        InvestmentTransaction.transaction_date <= end_date,
        InvestmentTransaction.description.ilike(f'%{type_filter}%')
    ).group_by(
        InvestmentAccount.account_name,
        InvestmentTransaction.symbol
    ).all()

    income_by_account: Dict[str, Dict[str, float]] = {}
    for row in results:
        account_name = row.account_name or 'Unknown'
        symbol = row.symbol or 'OTHER'
        amount = float(row.total or 0)

        # Extract underlying symbol from option symbol (e.g., "TSLA 01/17/2026 450.00 C" -> "TSLA")
        underlying = symbol.split()[0] if symbol else 'OTHER'

        if account_name not in income_by_account:
            income_by_account[account_name] = {}

        if underlying not in income_by_account[account_name]:
            income_by_account[account_name][underlying] = 0
        income_by_account[account_name][underlying] += amount

    return income_by_account


def get_actual_put_income(db: Session, start_date: date, end_date: date) -> Dict[str, float]:
    """
    Get actual put income (STO/BTC transactions for puts) for a date range.

    Returns income by account only (not by symbol) since puts go to CASH row.

    Returns:
        Dict mapping account_name -> total_put_income
    """
    from app.modules.investments.models import InvestmentTransaction, InvestmentAccount
    from sqlalchemy import and_

    results = db.query(
        InvestmentAccount.account_name,
        func.sum(InvestmentTransaction.amount).label('total')
    ).join(
        InvestmentAccount,
        and_(
            InvestmentTransaction.account_id == InvestmentAccount.account_id,
            InvestmentTransaction.source == InvestmentAccount.source
        )
    ).filter(
        InvestmentTransaction.transaction_type.in_(['STO', 'BTC']),
        InvestmentTransaction.transaction_date >= start_date,
        InvestmentTransaction.transaction_date <= end_date,
        InvestmentTransaction.description.ilike('%Put%')
    ).group_by(
        InvestmentAccount.account_name
    ).all()

    return {row.account_name: float(row.total or 0) for row in results}


def get_date_ranges_for_actuals() -> Dict[str, tuple]:
    """
    Calculate date ranges for actual income queries.

    Returns date ranges for:
    - last_week: The most recent complete trading week (Mon-Fri)
    - last_month: The most recent complete month
    - last_year: The most recent complete year

    Example: If today is Sat Feb 14, 2026:
    - last_week: Feb 9-13, 2026 (Mon-Fri)
    - last_month: Jan 1-31, 2026
    - last_year: Jan 1 - Dec 31, 2025
    """
    from datetime import timedelta
    import calendar

    today = date.today()

    # Last full trading week (Monday to Friday)
    # Find the most recent Friday (end of last trading week)
    weekday = today.weekday()  # 0=Mon ... 4=Fri, 5=Sat, 6=Sun
    if weekday >= 5:
        # Weekend: most recent completed trading week ended this Friday
        last_friday = today - timedelta(days=weekday - 4)
    else:
        # Weekday: last completed trading week ended previous Friday
        last_friday = today - timedelta(days=weekday + 3)
    last_monday = last_friday - timedelta(days=4)

    # Last full month
    first_of_this_month = today.replace(day=1)
    last_day_of_last_month = first_of_this_month - timedelta(days=1)
    first_of_last_month = last_day_of_last_month.replace(day=1)

    # Last full year
    last_year = today.year - 1
    first_of_last_year = date(last_year, 1, 1)
    last_of_last_year = date(last_year, 12, 31)

    return {
        'last_week': (last_monday, last_friday),
        'last_month': (first_of_last_month, last_day_of_last_month),
        'last_year': (first_of_last_year, last_of_last_year)
    }


def calculate_actual_income_for_holdings(
    db: Session,
    holdings_by_account: Dict[str, List[Dict]],
    symbols_aggregate: Dict[str, Dict]
) -> tuple:
    """
    Calculate actual weekly, monthly, and yearly income for all holdings.

    Separates CALL income (goes to equity rows) from PUT income (goes to CASH row).

    Returns:
        Tuple of (account_income, symbol_income, portfolio_totals, date_ranges, put_income_by_account)
        - account_income: Dict[account_name -> {weekly, monthly, yearly}] for CALLS only
        - symbol_income: Dict[symbol -> {weekly, monthly, yearly}] for CALLS only
        - portfolio_totals: Dict with total weekly, monthly, yearly (CALLS + PUTS)
        - date_ranges: The date ranges used for calculations
        - put_income_by_account: Dict[account_name -> {weekly, monthly, yearly}] for PUTS only
    """
    date_ranges = get_date_ranges_for_actuals()

    # Get actual CALL income for each period (for equity rows)
    weekly_call_income = get_actual_options_income(db, *date_ranges['last_week'], option_type='call')
    monthly_call_income = get_actual_options_income(db, *date_ranges['last_month'], option_type='call')
    yearly_call_income = get_actual_options_income(db, *date_ranges['last_year'], option_type='call')

    # Get actual PUT income for each period (for CASH row)
    weekly_put_income = get_actual_put_income(db, *date_ranges['last_week'])
    monthly_put_income = get_actual_put_income(db, *date_ranges['last_month'])
    yearly_put_income = get_actual_put_income(db, *date_ranges['last_year'])

    # Build account-level CALL income
    account_income = {}
    for account_name in holdings_by_account:
        account_income[account_name] = {
            'weekly': sum(weekly_call_income.get(account_name, {}).values()),
            'monthly': sum(monthly_call_income.get(account_name, {}).values()),
            'yearly': sum(yearly_call_income.get(account_name, {}).values())
        }

    # Build account-level PUT income (for CASH rows)
    put_income_by_account = {}
    all_put_accounts = set(weekly_put_income.keys()) | set(monthly_put_income.keys()) | set(yearly_put_income.keys())
    for account_name in all_put_accounts:
        put_income_by_account[account_name] = {
            'weekly': weekly_put_income.get(account_name, 0),
            'monthly': monthly_put_income.get(account_name, 0),
            'yearly': yearly_put_income.get(account_name, 0)
        }

    # Build symbol-level CALL income (aggregate across all accounts)
    all_symbols = set()
    for symbols in weekly_call_income.values():
        all_symbols.update(symbols.keys())
    for symbols in monthly_call_income.values():
        all_symbols.update(symbols.keys())
    for symbols in yearly_call_income.values():
        all_symbols.update(symbols.keys())

    symbol_income = {}
    for symbol in all_symbols:
        weekly_total = sum(acct.get(symbol, 0) for acct in weekly_call_income.values())
        monthly_total = sum(acct.get(symbol, 0) for acct in monthly_call_income.values())
        yearly_total = sum(acct.get(symbol, 0) for acct in yearly_call_income.values())
        symbol_income[symbol] = {
            'weekly': weekly_total,
            'monthly': monthly_total,
            'yearly': yearly_total
        }

    # Calculate portfolio totals (CALLS + PUTS combined)
    total_call_weekly = sum(a['weekly'] for a in account_income.values())
    total_call_monthly = sum(a['monthly'] for a in account_income.values())
    total_call_yearly = sum(a['yearly'] for a in account_income.values())

    total_put_weekly = sum(weekly_put_income.values())
    total_put_monthly = sum(monthly_put_income.values())
    total_put_yearly = sum(yearly_put_income.values())

    portfolio_totals = {
        'weekly': total_call_weekly + total_put_weekly,
        'monthly': total_call_monthly + total_put_monthly,
        'yearly': total_call_yearly + total_put_yearly
    }

    # Build account+symbol level CALL income (per account, per symbol)
    account_symbol_income = {}
    for account_name in set(list(weekly_call_income.keys()) + list(monthly_call_income.keys()) + list(yearly_call_income.keys())):
        account_symbol_income[account_name] = {}
        all_acct_syms = set()
        all_acct_syms.update(weekly_call_income.get(account_name, {}).keys())
        all_acct_syms.update(monthly_call_income.get(account_name, {}).keys())
        all_acct_syms.update(yearly_call_income.get(account_name, {}).keys())
        for sym in all_acct_syms:
            account_symbol_income[account_name][sym] = {
                'weekly': weekly_call_income.get(account_name, {}).get(sym, 0),
                'monthly': monthly_call_income.get(account_name, {}).get(sym, 0),
                'yearly': yearly_call_income.get(account_name, {}).get(sym, 0),
            }

    # Per-symbol PUT income (for puts breakdown table)
    weekly_put_by_sym = get_actual_options_income(db, *date_ranges['last_week'], option_type='put')
    monthly_put_by_sym = get_actual_options_income(db, *date_ranges['last_month'], option_type='put')
    yearly_put_by_sym = get_actual_options_income(db, *date_ranges['last_year'], option_type='put')

    all_put_syms: set = set()
    for acct_data in [weekly_put_by_sym, monthly_put_by_sym, yearly_put_by_sym]:
        for syms in acct_data.values():
            all_put_syms.update(syms.keys())

    put_symbol_income: Dict[str, Dict] = {}
    for sym in all_put_syms:
        acct_set: set = set()
        for src in [weekly_put_by_sym, monthly_put_by_sym, yearly_put_by_sym]:
            for acct_name, syms in src.items():
                if sym in syms:
                    acct_set.add(acct_name)
        put_symbol_income[sym] = {
            'weekly': sum(acct.get(sym, 0) for acct in weekly_put_by_sym.values()),
            'monthly': sum(acct.get(sym, 0) for acct in monthly_put_by_sym.values()),
            'yearly': sum(acct.get(sym, 0) for acct in yearly_put_by_sym.values()),
            'accounts': list(acct_set),
        }

    return account_income, symbol_income, portfolio_totals, date_ranges, put_income_by_account, account_symbol_income, put_symbol_income


@router.post("/options-selling/income-projection-with-status")
async def calculate_options_income_with_sold_status(
    params: dict,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Calculate potential income from selling covered calls WITH sold/unsold status.

    This is an enhanced version of the income-projection endpoint that also
    includes information about which options are currently sold (from uploaded
    screenshots) vs unsold.

    Income is calculated from ACTUAL historical transactions:
    - Weekly: Actual income from the last complete week
    - Monthly: Actual income from the last complete month
    - Yearly: Actual income from the last complete year
    """
    # Default parameters
    default_premium = params.get("default_premium", 60)
    symbol_premiums = params.get("symbol_premiums", {})
    delta = params.get("delta", 10)
    weeks_per_year = params.get("weeks_per_year", 50)

    # Load premium settings from database (auto-updated values)
    from app.modules.strategies.models import OptionPremiumSetting
    db_premiums = {}
    db_settings = db.query(OptionPremiumSetting).all()
    for setting in db_settings:
        if setting.premium_per_contract is not None:
            db_premiums[setting.symbol] = float(setting.premium_per_contract)
    
    # Default premiums by symbol (fallback if not in database)
    default_symbol_premiums = {
        "AAPL": 50,
        "TSLA": 150,
        "NVDA": 100,
        "IBIT": 40,
        "AVGO": 80,
        "COIN": 120,
        "PLTR": 60,
        "META": 90,
        "MSFT": 60,
        "MU": 70,
        "TSM": 50,
        "MSTR": 200,
    }

    # Merge: database settings (auto-updated) -> defaults -> user overrides
    # User overrides take highest priority
    effective_premiums = {**default_symbol_premiums, **db_premiums, **symbol_premiums}

    def get_premium_with_source(symbol):
        """Return (premium, source) where source is 'database', 'hardcoded', or 'global_default'."""
        if symbol in symbol_premiums:
            return symbol_premiums[symbol], "user_override"
        elif symbol in db_premiums:
            return db_premiums[symbol], "database"
        elif symbol in default_symbol_premiums:
            return default_symbol_premiums[symbol], "hardcoded"
        else:
            return default_premium, "global_default"

    def get_premium(symbol):
        return get_premium_with_source(symbol)[0]

    # Load cash balances for put income calculation
    from app.modules.strategies.models import AccountCashBalance
    from app.core.account_aliases import normalize_account_name
    cash_balances = {}
    try:
        cash_balance_records = db.query(AccountCashBalance).all()
        for cb in cash_balance_records:
            # Normalize account name to handle aliases (e.g., "Neel's IRA" -> "Neel's Retirement")
            normalized_name = normalize_account_name(cb.account_name)
            cash_balances[normalized_name] = float(cb.cash_balance)
    except Exception:
        pass  # Table might not exist yet

    # Put income is now calculated from actual transactions (not 4-week rolling average)
    # It will be populated later by calculate_actual_income_for_holdings()
    put_income_by_account = {}

    # Get all stock holdings by account
    result = db.execute(text("""
        SELECT
            ia.account_id,
            ia.account_name,
            ia.account_type,
            ih.symbol,
            ih.quantity,
            ih.current_price,
            ih.market_value,
            ih.description,
            ih.cost_basis
        FROM investment_holdings ih
        JOIN investment_accounts ia ON ih.account_id = ia.account_id AND ih.source = ia.source
        WHERE ih.quantity > 0
        AND ih.symbol NOT LIKE '%CASH%'
        AND ih.symbol NOT LIKE '%MONEY%'
        AND ih.symbol NOT LIKE '%FDRXX%'
        AND ia.account_type IN ('brokerage', 'retirement', 'ira', 'roth_ira')
        ORDER BY ia.account_name, ih.market_value DESC
    """))

    accounts = {}
    account_order = []
    symbols = {}
    
    # Build holdings data (same as original endpoint)
    for row in result:
        account_id, account_name, account_type, symbol, qty, price, value, description, cost_basis = row
        qty = float(qty) if qty else 0
        price = float(price) if price else 0
        value = float(value) if value else 0
        cost_basis = float(cost_basis) if cost_basis else 0

        if qty < 100:
            continue

        options_count = int(qty // 100)

        premium, premium_source = get_premium_with_source(symbol)

        if symbol not in symbols:
            symbols[symbol] = {
                "symbol": symbol,
                "description": description or symbol,
                "shares": 0,
                "price": price,
                "value": 0,
                "cost_basis": 0,
                "options": 0,
                "premium_per_contract": premium,
                "premium_source": premium_source,
                "weekly_income": 0,
                "monthly_income": 0,
                "yearly_income": 0,
                "accounts": []
            }

        symbols[symbol]["shares"] += qty
        symbols[symbol]["value"] += value
        symbols[symbol]["cost_basis"] += cost_basis
        symbols[symbol]["price"] = price
        if account_name not in symbols[symbol]["accounts"]:
            symbols[symbol]["accounts"].append(account_name)

        if account_name not in accounts:
            account_order.append(account_name)
            accounts[account_name] = {
                "account_id": account_id,
                "account_name": account_name,
                "account_type": account_type,
                "holdings": [],
                "total_value": 0,
                "total_shares": 0,
                "total_options": 0,
                "weekly_income": 0,
                "monthly_income": 0,
                "yearly_income": 0
            }

        existing = next((h for h in accounts[account_name]["holdings"] if h["symbol"] == symbol), None)
        if existing:
            existing["shares"] += qty
            existing["value"] += value
            existing["options"] = int(existing["shares"] // 100)
            existing["weekly_income"] = existing["options"] * premium
            existing["monthly_income"] = existing["weekly_income"] * 4
            existing["yearly_income"] = existing["weekly_income"] * weeks_per_year
        else:
            weekly = options_count * premium
            accounts[account_name]["holdings"].append({
                "symbol": symbol,
                "description": description or symbol,
                "shares": qty,
                "price": round(price, 2),
                "value": round(value, 0),
                "options": options_count,
                "premium_per_contract": premium,
                "premium_source": premium_source,
                "weekly_income": weekly,
                "monthly_income": weekly * 4,
                "yearly_income": weekly * weeks_per_year
            })
        
        accounts[account_name]["total_value"] += value
        accounts[account_name]["total_shares"] += qty
    
    # Calculate totals for symbols
    for sym in symbols:
        symbols[sym]["options"] = int(symbols[sym]["shares"] // 100)
        symbol_premium = symbols[sym]["premium_per_contract"]
        symbols[sym]["weekly_income"] = symbols[sym]["options"] * symbol_premium
        symbols[sym]["monthly_income"] = symbols[sym]["weekly_income"] * 4
        symbols[sym]["yearly_income"] = symbols[sym]["weekly_income"] * weeks_per_year
        symbols[sym]["value"] = round(symbols[sym]["value"], 0)
        symbols[sym]["cost_basis"] = round(symbols[sym]["cost_basis"], 0)
        # Calculate average cost per share
        shares = symbols[sym]["shares"]
        if shares > 0:
            symbols[sym]["avg_cost_per_share"] = round(symbols[sym]["cost_basis"] / shares, 2)
        else:
            symbols[sym]["avg_cost_per_share"] = 0
        symbols[sym]["shares"] = int(shares)
        symbols[sym]["account_count"] = len(symbols[sym]["accounts"])

    symbols_list = sorted(symbols.values(), key=lambda x: x["options"], reverse=True)

    # ============================================================================
    # ACTUAL INCOME CALCULATION - Replace projections with historical actuals
    # ============================================================================
    # Get actual income from InvestmentTransaction table for:
    # - Weekly: Last complete week (Mon-Sun)
    # - Monthly: Last complete month
    # - Yearly: Last complete year

    date_ranges = None
    actual_portfolio_totals = None
    put_symbol_income: Dict[str, Dict] = {}
    try:
        actual_account_income, actual_symbol_income, actual_portfolio_totals, date_ranges, put_income_by_account, actual_account_symbol_income, put_symbol_income = \
            calculate_actual_income_for_holdings(db, accounts, symbols)

        # Update symbol-level income with actuals
        for sym in symbols_list:
            symbol = sym["symbol"]
            if symbol in actual_symbol_income:
                sym["weekly_income"] = actual_symbol_income[symbol]["weekly"]
                sym["monthly_income"] = actual_symbol_income[symbol]["monthly"]
                sym["yearly_income"] = actual_symbol_income[symbol]["yearly"]

        # Update each holding's income with actuals (direct per-account per-symbol attribution)
        for account_name in accounts:
            for holding in accounts[account_name]["holdings"]:
                symbol = holding["symbol"]
                if symbol == "CASH":
                    continue  # CASH row uses put income, handled separately
                acct_sym = actual_account_symbol_income.get(account_name, {}).get(symbol)
                if acct_sym:
                    holding["weekly_income"] = round(acct_sym["weekly"], 2)
                    holding["monthly_income"] = round(acct_sym["monthly"], 2)
                    holding["yearly_income"] = round(acct_sym["yearly"], 2)

    except Exception as e:
        # If actual income calculation fails, fall back to projections
        logger.warning(f"Could not calculate actual income, using projections: {e}")
        date_ranges = get_date_ranges_for_actuals()

    # Calculate totals for each account
    for account_name in accounts:
        account = accounts[account_name]
        account["total_options"] = sum(h["options"] for h in account["holdings"])
        account["weekly_income"] = sum(h["weekly_income"] for h in account["holdings"])
        account["monthly_income"] = sum(h["monthly_income"] for h in account["holdings"])
        account["yearly_income"] = sum(h["yearly_income"] for h in account["holdings"])
        account["total_value"] = round(account["total_value"], 0)

    # Add CASH row for accounts with cash balances (for put income)
    total_cash = 0
    cash_symbol_data = None

    # Calculate TOTAL put income from ALL accounts for portfolio-level CASH row
    # put_income_by_account is now {account_name: {weekly, monthly, yearly}}
    total_put_weekly_all_accounts = sum(v.get('weekly', 0) for v in put_income_by_account.values())
    total_put_monthly_all_accounts = sum(v.get('monthly', 0) for v in put_income_by_account.values())
    total_put_yearly_all_accounts = sum(v.get('yearly', 0) for v in put_income_by_account.values())

    for account_name, cash_balance in cash_balances.items():
        if cash_balance <= 0:
            continue

        total_cash += cash_balance
        # Get put income for this specific account (now has weekly/monthly/yearly)
        account_put_income = put_income_by_account.get(account_name, {})
        put_weekly = account_put_income.get('weekly', 0)
        put_monthly = account_put_income.get('monthly', 0)
        put_yearly = account_put_income.get('yearly', 0)

        # Create or get account if it doesn't exist
        if account_name not in accounts:
            account_order.append(account_name)
            accounts[account_name] = {
                "account_id": f"cash_{account_name}",
                "account_name": account_name,
                "account_type": "brokerage",
                "holdings": [],
                "total_value": 0,
                "total_shares": 0,
                "total_options": 0,
                "weekly_income": 0,
                "monthly_income": 0,
                "yearly_income": 0
            }

        # Add CASH row to this account's holdings
        accounts[account_name]["holdings"].append({
            "symbol": "CASH",
            "description": "Cash-Secured Puts",
            "shares": 0,
            "price": 1.0,
            "value": round(cash_balance, 0),
            "options": 0,  # Puts don't have a fixed "options" count like calls
            "premium_per_contract": put_weekly,  # Weekly put income for this account
            "premium_source": "actual_puts",  # Indicates this is from actual transactions
            "weekly_income": put_weekly,
            "monthly_income": put_monthly,
            "yearly_income": put_yearly,
            "is_cash_row": True
        })

        # Update account totals to include put income
        accounts[account_name]["total_value"] += cash_balance
        accounts[account_name]["weekly_income"] += put_weekly
        accounts[account_name]["monthly_income"] += put_monthly
        accounts[account_name]["yearly_income"] += put_yearly

    # Add CASH to portfolio-level symbols if we have any cash OR any put income
    if total_cash > 0 or total_put_weekly_all_accounts > 0:
        cash_symbol_data = {
            "symbol": "CASH",
            "description": "Cash-Secured Puts",
            "shares": 0,
            "price": 1.0,
            "value": round(total_cash, 0),
            "options": 0,
            "premium_per_contract": total_put_weekly_all_accounts,  # ALL put income
            "premium_source": "actual_puts",
            "weekly_income": total_put_weekly_all_accounts,  # ALL put income from all accounts
            "monthly_income": total_put_monthly_all_accounts,
            "yearly_income": total_put_yearly_all_accounts,
            "accounts": list(put_income_by_account.keys()),  # All accounts with put income
            "account_count": len(put_income_by_account),
            "sold_contracts": 0,
            "unsold_contracts": 0,
            "utilization_status": "full" if total_put_weekly_all_accounts > 0 else "none",
            "is_cash_row": True
        }
        symbols_list.append(cash_symbol_data)

    # Portfolio totals - now using actual values (not multipliers)
    total_options = sum(a["total_options"] for a in accounts.values())
    total_weekly = sum(a["weekly_income"] for a in accounts.values())
    total_monthly = sum(a["monthly_income"] for a in accounts.values())
    total_yearly = sum(a["yearly_income"] for a in accounts.values())
    total_value = sum(a["total_value"] for a in accounts.values())

    weekly_yield = (total_weekly / total_value * 100) if total_value > 0 else 0
    yearly_yield = (total_yearly / total_value * 100) if total_value > 0 else 0

    # ============ NEW: Get sold options data BY ACCOUNT ============
    sold_by_account = get_sold_options_by_account(db)
    sold_data = get_current_sold_options(db)  # For backward compatibility (snapshot info)
    
    # Aggregate sold options across all accounts for portfolio-level totals
    all_sold_by_symbol = {}
    for account_name, account_sold_data in sold_by_account.items():
        for symbol, opts in account_sold_data.get("by_symbol", {}).items():
            if symbol not in all_sold_by_symbol:
                all_sold_by_symbol[symbol] = []
            all_sold_by_symbol[symbol].extend(opts)
    
    # FIRST: Calculate sold/unsold status for each account's holdings
    # This is the source of truth that individual tabs display
    for account_name in accounts:
        account = accounts[account_name]
        account_unsold_count = 0
        
        # Get sold options data specific to this account
        # Use exact account_name match from holdings query
        account_sold_data = sold_by_account.get(account_name, {})
        account_sold_by_symbol = account_sold_data.get("by_symbol", {})
        
        # Debug logging for account matching
        import logging
        logger = logging.getLogger(__name__)
        if account_name == "Jaya's IRA" or "MU" in [h.get("symbol") for h in account.get("holdings", [])]:
            logger.debug(f"Account: {account_name}, sold_data keys: {list(sold_by_account.keys())}, found: {account_name in sold_by_account}")
            if account_name in sold_by_account:
                logger.debug(f"  by_symbol keys: {list(account_sold_by_symbol.keys())}, MU present: {'MU' in account_sold_by_symbol}")
        
        for holding in account["holdings"]:
            symbol = holding["symbol"]
            account_symbol_options = holding["options"]
            
            # Get sold contracts for THIS account and THIS symbol
            # ONLY count CALLS - puts don't require share backing (they're cash-secured)
            symbol_sold_opts = account_sold_by_symbol.get(symbol, [])
            account_sold = sum(
                opt["contracts_sold"] for opt in symbol_sold_opts 
                if opt.get("option_type", "").lower() == "call"
            )
            
            # Calculate unsold for this account's holding
            account_unsold = max(0, account_symbol_options - account_sold)
            
            holding["sold_contracts"] = account_sold
            holding["unsold_contracts"] = account_unsold
            
            # Determine utilization status for this account's holding
            if account_sold == 0:
                holding["utilization_status"] = "none"
            elif account_unsold == 0:
                holding["utilization_status"] = "full"
            else:
                holding["utilization_status"] = "partial"
            
            account_unsold_count += account_unsold
        
        account["unsold_options"] = account_unsold_count
        
        # Store snapshot info for this account if available
        if account_name in sold_by_account:
            account["sold_options_snapshot"] = sold_by_account[account_name].get("snapshot")
    
    # SECOND: Calculate symbol-level unsold by SUMMING from accounts
    # This ensures Overview matches the sum of individual account tabs
    symbol_sold_unsold = {}  # symbol -> {sold: X, unsold: Y}
    for account_name in accounts:
        for holding in accounts[account_name]["holdings"]:
            symbol = holding["symbol"]
            if symbol not in symbol_sold_unsold:
                symbol_sold_unsold[symbol] = {"sold": 0, "unsold": 0}
            symbol_sold_unsold[symbol]["sold"] += holding.get("sold_contracts", 0)
            symbol_sold_unsold[symbol]["unsold"] += holding.get("unsold_contracts", 0)
    
    # Add sold/unsold status to symbols (portfolio level)
    for sym in symbols_list:
        symbol = sym["symbol"]
        sym_data = symbol_sold_unsold.get(symbol, {"sold": 0, "unsold": sym["options"]})
        sym["sold_contracts"] = sym_data["sold"]
        sym["unsold_contracts"] = sym_data["unsold"]
        
        # Determine utilization status
        if sym_data["sold"] == 0:
            sym["utilization_status"] = "none"
        elif sym_data["unsold"] == 0:
            sym["utilization_status"] = "full"
        else:
            sym["utilization_status"] = "partial"
    
    # Calculate total unsold by summing account-level unsold counts
    # This ensures consistency with what individual tabs display
    total_unsold = sum(accounts[name].get("unsold_options", 0) for name in accounts)
    total_sold = total_options - total_unsold
    
    # Format date ranges for API response
    income_periods = {}
    if date_ranges:
        income_periods = {
            "weekly": {
                "start": date_ranges['last_week'][0].isoformat(),
                "end": date_ranges['last_week'][1].isoformat(),
                "label": f"{date_ranges['last_week'][0].strftime('%b %d')} - {date_ranges['last_week'][1].strftime('%b %d, %Y')}"
            },
            "monthly": {
                "start": date_ranges['last_month'][0].isoformat(),
                "end": date_ranges['last_month'][1].isoformat(),
                "label": date_ranges['last_month'][0].strftime('%B %Y')
            },
            "yearly": {
                "start": date_ranges['last_year'][0].isoformat(),
                "end": date_ranges['last_year'][1].isoformat(),
                "label": str(date_ranges['last_year'][0].year)
            }
        }

    # Build per-symbol put position data from sold_by_account (already computed above)
    # Collect put option IDs and raw position info
    put_option_ids: list = []
    put_positions_raw: Dict[str, list] = {}  # symbol -> [{account, id, strike_price, contracts}]
    for acct_name, acct_data in sold_by_account.items():
        for sym, opts in acct_data.get("by_symbol", {}).items():
            for opt in opts:
                if opt.get("option_type", "").lower() == "put":
                    put_option_ids.append(opt["id"])
                    put_positions_raw.setdefault(sym, []).append({
                        "account": acct_name,
                        "id": opt["id"],
                        "strike_price": opt["strike_price"],
                        "contracts": opt["contracts_sold"],
                    })

    # Fetch expiration dates and premiums for put positions
    put_detail_by_id: Dict[int, Dict] = {}
    if put_option_ids:
        put_opts_full = db.query(SoldOption).filter(SoldOption.id.in_(put_option_ids)).all()
        for po in put_opts_full:
            put_detail_by_id[po.id] = {
                "expiration_date": po.expiration_date.isoformat() if po.expiration_date else None,
                "original_premium": float(po.original_premium) if po.original_premium else None,
                "current_premium": float(po.premium_per_contract) if po.premium_per_contract else None,
            }

    # Get current stock prices for put symbols (from holdings dict if available)
    # Seed from open-position symbols + all symbols with historical put income
    all_price_syms = set(put_positions_raw.keys()) | set(put_symbol_income.keys())
    put_sym_prices: Dict[str, Optional[float]] = {
        sym: symbols[sym]["price"] if sym in symbols else None for sym in all_price_syms
    }

    # For symbols not in holdings, look up from investment_holdings history
    missing_price_syms = [s for s, p in put_sym_prices.items() if p is None]
    if missing_price_syms:
        placeholders = ', '.join(f':sym{i}' for i in range(len(missing_price_syms)))
        params = {f'sym{i}': s for i, s in enumerate(missing_price_syms)}
        price_rows = db.execute(text(f"""
            SELECT DISTINCT ON (ih.symbol) ih.symbol, ih.current_price
            FROM investment_holdings ih
            WHERE ih.symbol IN ({placeholders})
            AND ih.current_price IS NOT NULL
            ORDER BY ih.symbol, ih.current_price DESC
        """), params)
        for row in price_rows:
            sym, price = row
            if price and put_sym_prices.get(sym) is None:
                put_sym_prices[sym] = float(price)

    # Assemble put_position_data per symbol
    put_position_data: Dict[str, Dict] = {}
    for sym, raw_positions in put_positions_raw.items():
        total_contracts = 0
        value_locked = 0.0
        full_positions = []
        for rp in raw_positions:
            detail = put_detail_by_id.get(rp["id"], {})
            contracts = rp["contracts"]
            strike = rp["strike_price"]
            locked = strike * 100 * contracts
            total_contracts += contracts
            value_locked += locked
            full_positions.append({
                "account": rp["account"],
                "strike_price": strike,
                "contracts": contracts,
                "value_locked": round(locked, 0),
                "expiration_date": detail.get("expiration_date"),
                "original_premium": detail.get("original_premium"),
                "current_premium": detail.get("current_premium"),
            })
        put_position_data[sym] = {
            "total_contracts": total_contracts,
            "shares_equivalent": total_contracts * 100,
            "value_locked": round(value_locked, 0),
            "current_price": put_sym_prices.get(sym),
            "positions": full_positions,
            "strikes": sorted(set(p["strike_price"] for p in full_positions)),
        }

    # Build put_symbols_list merging income + position data
    # Retired symbols (active=False) are excluded unless they have an open position
    retired_syms = {
        s.symbol for s in db.query(OptionPremiumSetting).filter(OptionPremiumSetting.active == False).all()
    }
    all_put_syms_set = (
        (set(put_symbol_income.keys()) - retired_syms) | set(put_position_data.keys())
    )
    put_symbols_list = []
    for sym in all_put_syms_set:
        income = put_symbol_income.get(sym, {"weekly": 0, "monthly": 0, "yearly": 0, "accounts": []})
        pos = put_position_data.get(sym, {})
        income_accounts = set(income.get("accounts", []))
        pos_accounts = set(p["account"] for p in pos.get("positions", []))
        all_accounts = sorted(income_accounts | pos_accounts)
        put_symbols_list.append({
            "symbol": sym,
            "total_contracts": pos.get("total_contracts", 0),
            "shares_equivalent": pos.get("shares_equivalent", 0),
            "value_locked": pos.get("value_locked", 0),
            "current_price": pos.get("current_price"),
            "avg_cost_per_share": symbols.get(sym, {}).get("avg_cost_per_share"),
            "strikes": pos.get("strikes", []),
            "positions": pos.get("positions", []),
            "weekly_income": round(income["weekly"], 2),
            "monthly_income": round(income["monthly"], 2),
            "yearly_income": round(income["yearly"], 2),
            "account_count": len(all_accounts),
            "accounts": all_accounts,
        })
    # Sort by value locked (open positions first), then by yearly income
    put_symbols_list.sort(key=lambda x: (x["value_locked"], abs(x["yearly_income"])), reverse=True)

    result = {
        "params": {
            "default_premium": default_premium,
            "symbol_premiums": {s["symbol"]: s["premium_per_contract"] for s in symbols_list},
            "delta": delta,
            "weeks_per_year": weeks_per_year
        },
        "portfolio_summary": {
            "total_value": round(total_value, 0),
            "total_options": total_options,
            "total_sold": total_sold,
            "total_unsold": total_unsold,
            "weekly_income": round(total_weekly, 0),
            "monthly_income": round(total_monthly, 0),
            "yearly_income": round(total_yearly, 0),
            "weekly_yield_percent": round(weekly_yield, 3),
            "yearly_yield_percent": round(yearly_yield, 2),
            "total_cash_for_puts": round(total_cash, 0)
        },
        "income_periods": income_periods,
        "sold_options_snapshot": sold_data.get("snapshot"),
        "symbols": symbols_list,
        "put_symbols": put_symbols_list,
        "accounts": [accounts[name] for name in account_order if accounts[name]["total_options"] > 0]
    }

    return result


# ============================================================================
# OPTION ROLL MONITORING ENDPOINTS
# ============================================================================

class OptionPositionCreate(BaseModel):
    """Create a new option position for monitoring."""
    symbol: str
    strike_price: float
    option_type: str  # 'call' or 'put'
    expiration_date: str  # YYYY-MM-DD
    contracts: int = 1
    original_premium: float  # Premium received when sold
    account_name: Optional[str] = None


class OptionPositionUpdate(BaseModel):
    """Update an existing option position."""
    original_premium: Optional[float] = None
    status: Optional[str] = None  # 'open', 'closed', 'rolled'


@router.post("/option-monitor/positions")
async def add_monitored_position(
    position: OptionPositionCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Add a new option position for early roll monitoring.

    This creates a standalone position entry for monitoring, separate from
    the screenshot-based tracking. Use this when you want precise control
    over the original premium for profit calculations.
    """
    from app.modules.strategies.models import SoldOptionsSnapshot, SoldOption
    from app.core.account_aliases import normalize_account_name

    # Normalize account name to handle aliases (e.g., "Neel's IRA" -> "Neel's Retirement")
    account_name = normalize_account_name(position.account_name) if position.account_name else None

    # Parse expiration date
    try:
        exp_date = datetime.strptime(position.expiration_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Create or get a snapshot for manual entries
    snapshot = db.query(SoldOptionsSnapshot).filter(
        SoldOptionsSnapshot.source == 'manual',
        SoldOptionsSnapshot.account_name == account_name,
        SoldOptionsSnapshot.parsing_status == 'success'
    ).order_by(SoldOptionsSnapshot.snapshot_date.desc()).first()

    if not snapshot:
        snapshot = SoldOptionsSnapshot(
            source='manual',
            account_name=account_name,
            snapshot_date=datetime.utcnow(),
            parsing_status='success',
            notes='Manually entered positions for roll monitoring'
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
    
    # Create the option
    sold_option = SoldOption(
        snapshot_id=snapshot.id,
        symbol=position.symbol.upper(),
        strike_price=Decimal(str(position.strike_price)),
        option_type=position.option_type.lower(),
        expiration_date=exp_date,
        contracts_sold=position.contracts,
        premium_per_contract=Decimal(str(position.original_premium)),
        original_premium=Decimal(str(position.original_premium)),
        status='open'
    )
    db.add(sold_option)
    db.commit()
    db.refresh(sold_option)
    
    # Clear recommendations cache after adding position
    from app.core.cache import clear_cache
    clear_cache("recommendations:")
    
    return {
        "success": True,
        "position_id": sold_option.id,
        "message": f"Added {position.symbol} ${position.strike_price} {position.option_type} for monitoring"
    }


@router.put("/option-monitor/positions/{position_id}")
async def update_monitored_position(
    position_id: int,
    updates: OptionPositionUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Update a monitored position (e.g., set original premium or close it)."""
    from app.modules.strategies.models import SoldOption
    
    option = db.query(SoldOption).filter(SoldOption.id == position_id).first()
    if not option:
        raise HTTPException(status_code=404, detail="Position not found")
    
    if updates.original_premium is not None:
        option.original_premium = Decimal(str(updates.original_premium))
    
    if updates.status is not None:
        option.status = updates.status
    
    db.commit()
    
    # Clear recommendations cache after updating position
    from app.core.cache import clear_cache
    clear_cache("recommendations:")
    
    return {"success": True, "message": f"Position {position_id} updated"}


@router.get("/option-monitor/check")
async def check_roll_opportunities(
    profit_threshold: float = Query(default=0.80, ge=0.1, le=1.0),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Check all open positions for early roll opportunities.
    
    This fetches current option prices from Yahoo Finance and calculates
    profit percentages. Returns alerts for positions that have exceeded
    the profit threshold.
    
    Args:
        profit_threshold: Minimum profit % to trigger alert (default 0.80 = 80%)
    """
    from app.modules.strategies.option_monitor import (
        OptionRollMonitor, 
        get_positions_from_db,
        save_alerts_to_db
    )
    
    # Get positions from database
    positions = get_positions_from_db(db)
    
    if not positions:
        return {
            "success": True,
            "positions_checked": 0,
            "alerts": [],
            "message": "No open positions with original premium set found. Add positions or update existing ones with original_premium."
        }
    
    # Run the monitor
    monitor = OptionRollMonitor(profit_threshold=profit_threshold)
    alerts = monitor.check_all_positions(positions)
    
    # Save alerts to database
    new_alert_count = save_alerts_to_db(db, alerts) if alerts else 0
    
    # Format response
    alerts_data = []
    for alert in alerts:
        pos = alert.position
        alerts_data.append({
            "symbol": pos.symbol,
            "strike_price": pos.strike_price,
            "option_type": pos.option_type,
            "expiration_date": pos.expiration_date.isoformat(),
            "contracts": pos.contracts,
            "original_premium": pos.original_premium,
            "current_premium": round(alert.current_premium, 2),
            "profit_amount": round(alert.profit_amount, 2),
            "profit_percent": round(alert.profit_percent * 100, 1),
            "days_to_expiry": alert.days_to_expiry,
            "urgency": alert.urgency,
            "recommendation": alert.recommendation,
            "position_id": pos.sold_option_id
        })
    
    return {
        "success": True,
        "positions_checked": len(positions),
        "alerts_count": len(alerts),
        "new_alerts_saved": new_alert_count,
        "profit_threshold": f"{profit_threshold * 100:.0f}%",
        "alerts": alerts_data,
        "message": monitor.format_alert_message(alerts) if alerts else "No roll opportunities at this time."
    }


@router.get("/option-monitor/alerts")
async def get_roll_alerts(
    include_acknowledged: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get historical roll alerts.
    
    Args:
        include_acknowledged: Include alerts that have been acknowledged
        limit: Maximum number of alerts to return
    """
    from app.modules.strategies.models import OptionRollAlert
    
    query = db.query(OptionRollAlert)
    
    if not include_acknowledged:
        query = query.filter(OptionRollAlert.alert_acknowledged == 'N')
    
    alerts = query.order_by(
        OptionRollAlert.alert_triggered_at.desc()
    ).limit(limit).all()
    
    return {
        "alerts": [
            {
                "id": a.id,
                "symbol": a.symbol,
                "strike_price": float(a.strike_price),
                "option_type": a.option_type,
                "expiration_date": a.expiration_date.isoformat() if a.expiration_date else None,
                "contracts": a.contracts,
                "original_premium": float(a.original_premium),
                "current_premium": float(a.current_premium),
                "profit_percent": float(a.profit_percent),
                "alert_type": a.alert_type,
                "alert_triggered_at": a.alert_triggered_at.isoformat(),
                "acknowledged": a.alert_acknowledged == 'Y',
                "action_taken": a.action_taken
            }
            for a in alerts
        ],
        "count": len(alerts)
    }


@router.post("/option-monitor/alerts/{alert_id}/acknowledge")
async def acknowledge_roll_alert(
    alert_id: int,
    action_taken: Optional[str] = Query(default=None, description="Action taken: 'rolled', 'closed', 'ignored'"),
    notes: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Acknowledge a roll alert and optionally record the action taken."""
    from app.modules.strategies.models import OptionRollAlert
    
    alert = db.query(OptionRollAlert).filter(OptionRollAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.alert_acknowledged = 'Y'
    alert.acknowledged_at = datetime.utcnow()
    if action_taken:
        alert.action_taken = action_taken
    if notes:
        alert.notes = notes
    
    db.commit()
    
    return {"success": True, "message": f"Alert {alert_id} acknowledged"}


@router.get("/option-monitor/positions/debug/{symbol}")
async def debug_symbol_positions(
    symbol: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Debug endpoint to check what positions exist in database for a specific symbol.
    Shows all snapshots and their expiration dates.
    """
    from app.modules.strategies.models import SoldOption, SoldOptionsSnapshot
    from sqlalchemy import desc, func
    
    symbol_upper = symbol.upper()
    
    # Get all positions for this symbol across all snapshots
    all_positions = db.query(SoldOption).join(SoldOptionsSnapshot).filter(
        SoldOption.symbol == symbol_upper
    ).order_by(desc(SoldOptionsSnapshot.snapshot_date), desc(SoldOption.expiration_date)).all()
    
    # Get unique account names for this symbol
    account_names = db.query(SoldOptionsSnapshot.account_name).join(SoldOption).filter(
        SoldOption.symbol == symbol_upper,
        SoldOptionsSnapshot.account_name.isnot(None)
    ).distinct().all()
    unique_accounts = [name[0] for name in account_names if name[0]]
    
    # Group by snapshot
    by_snapshot = {}
    for pos in all_positions:
        snapshot_id = pos.snapshot_id
        if snapshot_id not in by_snapshot:
            snapshot = pos.snapshot
            by_snapshot[snapshot_id] = {
                "snapshot_id": snapshot_id,
                "account_name": snapshot.account_name,
                "snapshot_date": snapshot.snapshot_date.isoformat() if snapshot.snapshot_date else None,
                "parsing_status": snapshot.parsing_status,
                "positions": []
            }
        
        by_snapshot[snapshot_id]["positions"].append({
            "id": pos.id,
            "strike_price": float(pos.strike_price),
            "option_type": pos.option_type,
            "expiration_date": pos.expiration_date.isoformat() if pos.expiration_date else None,
            "contracts": pos.contracts_sold,
            "status": pos.status,
            "premium": float(pos.premium_per_contract) if pos.premium_per_contract else None,
            "gain_loss": float(pos.gain_loss_percent) if pos.gain_loss_percent else None
        })
    
    # Get latest snapshot per account
    latest_snapshots = db.query(
        SoldOptionsSnapshot.account_name,
        func.max(SoldOptionsSnapshot.id).label('latest_id')
    ).filter(
        SoldOptionsSnapshot.parsing_status == 'success'
    ).group_by(SoldOptionsSnapshot.account_name).all()
    
    latest_ids = {name: id for name, id in latest_snapshots}
    
    # Mark which snapshots are latest
    for snapshot_id, data in by_snapshot.items():
        data["is_latest"] = data["snapshot_id"] in latest_ids.values()
        if data["account_name"] in latest_ids:
            data["is_latest_for_account"] = latest_ids[data["account_name"]] == snapshot_id
        else:
            data["is_latest_for_account"] = False
    
    # Get what positions would be used by get_positions_from_db (latest snapshots only)
    from app.modules.strategies.option_monitor import get_positions_from_db
    active_positions = get_positions_from_db(db)
    figma_active = [p for p in active_positions if p.symbol == symbol_upper]
    
    return {
        "symbol": symbol_upper,
        "total_positions_in_db": len(all_positions),
        "unique_account_names": unique_accounts,
        "active_positions_used_by_strategies": [
            {
                "symbol": p.symbol,
                "strike": p.strike_price,
                "option_type": p.option_type,
                "expiration_date": p.expiration_date.isoformat() if p.expiration_date else None,
                "account_name": p.account_name,
                "contracts": p.contracts
            }
            for p in figma_active
        ],
        "snapshots": list(by_snapshot.values()),
        "latest_snapshot_ids": latest_ids
    }


@router.get("/option-monitor/positions")
async def list_monitored_positions(
    status: Optional[str] = Query(default="open", description="Filter by status: 'open', 'closed', 'all'"),
    use_live_prices: bool = Query(default=False, description="Fetch live prices from Yahoo Finance for current G/L %"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    List all option positions being monitored.
    
    Shows positions that have premium data for monitoring.
    
    IMPORTANT: Only shows positions from the LATEST snapshot per account.
    If an option was in an old snapshot but NOT in the latest snapshot,
    it's considered rolled/closed and won't appear in "open" positions.
    """
    from app.modules.strategies.models import SoldOption, SoldOptionsSnapshot
    from sqlalchemy import func, and_, or_
    
    today = date.today()
    
    # STEP 1: Find the latest snapshot ID for each account
    # This is crucial - we only want positions from the most recent data paste per account
    latest_snapshots_subquery = db.query(
        SoldOptionsSnapshot.account_name,
        func.max(SoldOptionsSnapshot.id).label('max_id')
    ).filter(
        SoldOptionsSnapshot.parsing_status == 'success'
    ).group_by(SoldOptionsSnapshot.account_name).subquery()
    
    # Get the actual snapshot IDs
    latest_snapshot_ids = db.query(SoldOptionsSnapshot.id).join(
        latest_snapshots_subquery,
        and_(
            SoldOptionsSnapshot.account_name == latest_snapshots_subquery.c.account_name,
            SoldOptionsSnapshot.id == latest_snapshots_subquery.c.max_id
        )
    ).all()
    latest_ids = [s.id for s in latest_snapshot_ids]
    
    # STEP 2: Query positions ONLY from latest snapshots
    query = db.query(SoldOption).filter(
        SoldOption.snapshot_id.in_(latest_ids)
    )
    
    if status == "open":
        query = query.filter(
            SoldOption.status == 'open',
            SoldOption.expiration_date >= today
        )
    elif status == "closed":
        query = query.filter(SoldOption.status.in_(['closed', 'rolled', 'expired']))
    
    all_positions = query.order_by(SoldOption.expiration_date.asc()).all()
    
    # STEP 3: For positions that need premium data, check older snapshots
    # But ONLY for positions that exist in the latest snapshot
    # Key: (symbol, strike, expiration, account, option_type)
    positions_needing_premium = {}
    
    for p in all_positions:
        key = (p.symbol, float(p.strike_price), p.expiration_date, 
               p.snapshot.account_name if p.snapshot else None, p.option_type)
        
        # Check if this position has good premium data
        has_good_data = (p.original_premium or 
                        (p.premium_per_contract and p.gain_loss_percent is not None))
        
        if not has_good_data:
            # Mark this position as needing premium data from older snapshots
            positions_needing_premium[key] = p
    
    # STEP 4: If any positions need premium data, look in older snapshots
    if positions_needing_premium:
        # Get all positions from older snapshots that match our keys
        older_positions = db.query(SoldOption).join(SoldOptionsSnapshot).filter(
            SoldOptionsSnapshot.parsing_status == 'success',
            ~SoldOption.snapshot_id.in_(latest_ids)  # NOT in latest snapshots
        ).all()
        
        for op in older_positions:
            key = (op.symbol, float(op.strike_price), op.expiration_date,
                   op.snapshot.account_name if op.snapshot else None, op.option_type)
            
            if key in positions_needing_premium:
                current_pos = positions_needing_premium[key]
                # Check if older position has better premium data
                older_has_better = False
                
                if op.original_premium and not current_pos.original_premium:
                    older_has_better = True
                elif (op.premium_per_contract and op.gain_loss_percent is not None and 
                      not (current_pos.premium_per_contract and current_pos.gain_loss_percent is not None)):
                    older_has_better = True
                
                if older_has_better:
                    # Copy premium data from older position to current
                    # (We don't actually modify DB, just use the older data for display)
                    positions_needing_premium[key] = op
    
    # STEP 5: Build result, merging premium data where needed
    result_positions = []
    
    # If using live prices, fetch them
    live_prices = {}
    price_update_time = None
    if use_live_prices:
        from app.modules.strategies.option_monitor import OptionChainFetcher
        fetcher = OptionChainFetcher()
        price_update_time = datetime.utcnow()
        
        # Fetch live prices for all positions that can be monitored
        for p in all_positions:
            key = (p.symbol, float(p.strike_price), p.expiration_date,
                   p.snapshot.account_name if p.snapshot else None, p.option_type)
            premium_source_pos = positions_needing_premium.get(key, p)
            
            # Calculate original premium to determine if we can monitor
            original_premium = None
            if premium_source_pos.original_premium:
                original_premium = float(premium_source_pos.original_premium)
            elif premium_source_pos.premium_per_contract and premium_source_pos.gain_loss_percent is not None:
                curr = float(premium_source_pos.premium_per_contract)
                gl = float(premium_source_pos.gain_loss_percent)
                if gl != 100:
                    original_premium = curr / (1 - gl / 100)
            elif premium_source_pos.premium_per_contract:
                original_premium = float(premium_source_pos.premium_per_contract)
            
            if original_premium and p.expiration_date:
                try:
                    quote = fetcher.get_option_quote(
                        symbol=p.symbol,
                        strike_price=float(p.strike_price),
                        option_type=p.option_type,
                        expiration_date=p.expiration_date
                    )
                    if quote:
                        current_premium = quote.bid if quote.bid > 0 else quote.last_price
                        if current_premium > 0:
                            live_prices[p.id] = {
                                "current_premium": current_premium,
                                "gain_loss_percent": ((original_premium - current_premium) / original_premium * 100) if original_premium > 0 else None
                            }
                except Exception as e:
                    logger.warning(f"Failed to fetch live price for {p.symbol} ${p.strike_price}: {e}")
    
    for p in all_positions:
        key = (p.symbol, float(p.strike_price), p.expiration_date,
               p.snapshot.account_name if p.snapshot else None, p.option_type)
        
        # Use the position with best premium data
        premium_source_pos = positions_needing_premium.get(key, p)
        
        # Calculate original premium
        original_premium = None
        premium_source = None
        
        if premium_source_pos.original_premium:
            original_premium = float(premium_source_pos.original_premium)
            premium_source = "set"
        elif premium_source_pos.premium_per_contract and premium_source_pos.gain_loss_percent is not None:
            curr = float(premium_source_pos.premium_per_contract)
            gl = float(premium_source_pos.gain_loss_percent)
            if gl != 100:
                original_premium = curr / (1 - gl / 100)
                premium_source = "calculated"
        elif premium_source_pos.premium_per_contract:
            original_premium = float(premium_source_pos.premium_per_contract)
            premium_source = "current"
        
        # Use live prices if available, otherwise use stored data
        if p.id in live_prices:
            current_premium = live_prices[p.id]["current_premium"]
            gain_loss_percent = live_prices[p.id]["gain_loss_percent"]
            data_source = "live"
        else:
            current_premium = float(p.premium_per_contract) if p.premium_per_contract else None
            gain_loss_percent = float(p.gain_loss_percent) if p.gain_loss_percent else None
            data_source = "stored"
        
        # Get snapshot date for historical data indicator
        snapshot_date = p.snapshot.snapshot_date if p.snapshot else None
        
        result_positions.append({
            "id": p.id,
            "symbol": p.symbol,
            "strike_price": float(p.strike_price),
            "option_type": p.option_type,
            "expiration_date": p.expiration_date.isoformat() if p.expiration_date else None,
            "contracts": p.contracts_sold,
            "original_premium": round(original_premium, 2) if original_premium else None,
            "premium_source": premium_source,
            "current_premium": round(current_premium, 2) if current_premium else None,
            "gain_loss_percent": round(gain_loss_percent, 1) if gain_loss_percent is not None else None,
            "status": p.status,
            "account": p.snapshot.account_name if p.snapshot else None,
            "days_to_expiry": (p.expiration_date - today).days if p.expiration_date else None,
            "can_monitor": original_premium is not None,
            "data_source": data_source,  # "live" or "stored"
            "snapshot_date": snapshot_date.isoformat() if snapshot_date else None
        })
    
    # Sort by expiration date
    result_positions.sort(key=lambda x: (x["expiration_date"] or "", x["symbol"]))
    
    return {
        "positions": result_positions,
        "count": len(result_positions),
        "monitorable_count": sum(1 for p in result_positions if p["can_monitor"]),
        "status_filter": status,
        "price_update_time": price_update_time.isoformat() if price_update_time else None,
        "using_live_prices": use_live_prices
    }


@router.get("/option-monitor/yield-scan")
async def get_yield_scan(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Fetch live option yield data for both tiers:
    - Tier 1 (mega-cap): AAPL, MSFT, NVDA, AVGO, GOOGL, AMZN, META, TSLA, LLY — calls at delta 10 and 20
    - Tier 2 (sub-$1T): current DB holdings excluding Tier 1 and crypto — puts at delta 20 and 10
    """
    from app.modules.strategies.option_data_service import get_option_chain
    from app.modules.investments.models import InvestmentHolding
    from datetime import date, timedelta, datetime as dt

    today = date.today()
    days_to_friday = (4 - today.weekday()) % 7 or 7
    next_friday = today + timedelta(days=days_to_friday)

    TIER1 = {"AAPL", "MSFT", "NVDA", "AVGO", "GOOGL", "AMZN", "META", "TSLA", "LLY"}
    EXCLUDED = {"FDRXX", "SPAXX", "VMFXX"}  # money markets only
    # Supplemental Tier 2 universe — historically used for puts, always show even if not currently held
    TIER2_SUPPLEMENTAL = {"PLTR", "HOOD", "COIN", "AMD", "SHOP", "INTC", "RKLB", "NFLX",
                          "CRCL", "FIG", "MSTR", "MU", "IBIT"}

    TIER1_NOTES = {"TSLA": "carve-out", "LLY": "named inclusion"}
    TIER1_ORDER = ["AVGO", "META", "TSLA", "NVDA", "AMZN", "MSFT", "GOOGL", "LLY", "AAPL"]

    def _find_closest(options_df, target_delta: float):
        df = options_df.copy()
        df = df.dropna(subset=["delta", "bid", "ask"])
        df["delta_abs"] = df["delta"].abs()
        df = df[df["delta_abs"] > 0]
        if df.empty:
            return None
        df["mid"] = (df["bid"] + df["ask"]) / 2
        row = df.iloc[(df["delta_abs"] - target_delta).abs().argsort()[:1]]
        strike = float(row["strike"].values[0])
        delta_act = float(row["delta_abs"].values[0])
        mid = float(row["mid"].values[0])
        premium = round(mid * 100, 2)
        yld = round(premium / (strike * 100) * 100, 2) if strike > 0 else 0
        return {"strike": strike, "delta": round(delta_act, 3), "premium": premium, "yield_pct": yld}

    def _stock_price(chain):
        calls = chain.get("calls")
        if calls is None or calls.empty:
            return None
        df = calls.dropna(subset=["delta"])
        df = df[df["delta"].abs() > 0]
        if df.empty:
            return None
        atm = df.iloc[(df["delta"].abs() - 0.50).abs().argsort()[:1]]
        return float(atm["strike"].values[0])

    # ── Tier 1 calls ────────────────────────────────────────────────────────
    tier1_results = []
    for symbol in TIER1_ORDER:
        try:
            chain = get_option_chain(symbol, next_friday)
            if not chain or "calls" not in chain:
                tier1_results.append({"symbol": symbol, "error": "no data"})
                continue
            price = _stock_price(chain)
            d10 = _find_closest(chain["calls"], 0.10)
            d20 = _find_closest(chain["calls"], 0.20)
            tier1_results.append({
                "symbol": symbol,
                "stock_price": price,
                "note": TIER1_NOTES.get(symbol, ""),
                "d10": d10,
                "d20": d20,
            })
        except Exception as e:
            tier1_results.append({"symbol": symbol, "error": str(e)[:80]})

    # ── Tier 2 puts — DB holdings merged with supplemental universe ─────────
    try:
        holdings = db.query(InvestmentHolding).filter(InvestmentHolding.quantity > 0).all()
    except Exception:
        holdings = []

    # Group DB holdings by symbol
    tier2_map: dict = {}
    for h in holdings:
        sym = h.symbol
        if not sym or len(sym) > 6:
            continue
        if sym in TIER1 or sym in EXCLUDED:
            continue
        if sym not in tier2_map:
            tier2_map[sym] = {"qty": 0, "accounts": []}
        tier2_map[sym]["qty"] += float(h.quantity or 0)
        acct = str(h.account_id)
        if acct not in tier2_map[sym]["accounts"]:
            tier2_map[sym]["accounts"].append(acct)

    # Add supplemental tickers not already in DB holdings
    for sym in TIER2_SUPPLEMENTAL:
        if sym not in tier2_map:
            tier2_map[sym] = {"qty": 0, "accounts": []}

    tier2_results = []
    for symbol, info in sorted(tier2_map.items()):
        qty = int(info["qty"])
        accts = info["accounts"]
        if qty > 0:
            holdings_note = f"{qty} shares"
        else:
            holdings_note = "watchlist"
        try:
            chain = get_option_chain(symbol, next_friday)
            if not chain or "puts" not in chain:
                tier2_results.append({"symbol": symbol, "holdings": holdings_note, "error": "no data"})
                continue
            puts_df = chain["puts"].copy()
            puts_df["delta"] = -puts_df["delta"].abs()  # normalise to negative
            price = None
            if "calls" in chain:
                price = _stock_price(chain)

            d20 = _find_closest(puts_df, 0.20)   # user "delta 80" = 80% OTM
            d10 = _find_closest(puts_df, 0.10)   # user "delta 90" = 90% OTM
            tier2_results.append({
                "symbol": symbol,
                "stock_price": price,
                "holdings": holdings_note,
                "d80": d20,  # user label
                "d90": d10,  # user label
            })
        except Exception as e:
            tier2_results.append({"symbol": symbol, "holdings": holdings_note, "error": str(e)[:80]})

    # Sort Tier 2 by d80 yield descending
    def _sort_key(r):
        d = r.get("d80") or {}
        return d.get("yield_pct", -1)
    tier2_results.sort(key=_sort_key, reverse=True)

    return {
        "expiry": next_friday.isoformat(),
        "fetched_at": dt.utcnow().isoformat(),
        "tier1_calls": tier1_results,
        "tier2_puts": tier2_results,
    }


@router.get("/premium-settings")
async def get_premium_settings(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Get current premium settings for all symbols, including both CALL and PUT premiums."""
    from app.modules.strategies.models import OptionPremiumSetting

    settings = db.query(OptionPremiumSetting).all()

    result = {}
    for setting in settings:
        result[setting.symbol] = {
            # CALL premium (backward compatible field name)
            "premium_per_contract": float(setting.premium_per_contract) if setting.premium_per_contract else None,
            "call_premium_per_contract": float(setting.premium_per_contract) if setting.premium_per_contract else None,
            "call_contracts_sold": setting.call_contracts_sold,
            "call_net_total": float(setting.call_net_total) if setting.call_net_total else None,
            # PUT premium
            "put_premium_per_contract": float(setting.put_premium_per_contract) if setting.put_premium_per_contract else None,
            "put_contracts_sold": setting.put_contracts_sold,
            "put_net_total": float(setting.put_net_total) if setting.put_net_total else None,
            # Metadata
            "is_auto_updated": setting.is_auto_updated,
            "manual_override": setting.manual_override,
            "last_auto_update": setting.last_auto_update.isoformat() if setting.last_auto_update else None,
            "updated_at": setting.updated_at.isoformat()
        }

    return result


@router.post("/premium-settings/update")
async def update_premium_settings(
    symbol: str,
    premium_per_contract: float,
    manual_override: bool = False,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Manually update premium setting for a symbol."""
    from app.modules.strategies.models import OptionPremiumSetting
    from decimal import Decimal
    
    setting = db.query(OptionPremiumSetting).filter(
        OptionPremiumSetting.symbol == symbol.upper()
    ).first()
    
    if setting:
        setting.premium_per_contract = Decimal(str(premium_per_contract))
        setting.manual_override = manual_override
        if manual_override:
            setting.is_auto_updated = False
    else:
        setting = OptionPremiumSetting(
            symbol=symbol.upper(),
            premium_per_contract=Decimal(str(premium_per_contract)),
            is_auto_updated=not manual_override,
            manual_override=manual_override
        )
        db.add(setting)
    
    db.commit()
    
    return {
        "success": True,
        "symbol": symbol.upper(),
        "premium_per_contract": premium_per_contract,
        "manual_override": manual_override
    }


@router.post("/premium-settings/auto-update")
async def trigger_auto_update_premiums(
    weeks: int = 4,
    min_transactions: int = 1,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Manually trigger auto-update of premium settings based on 4-week averages."""
    from app.modules.strategies.services import update_premium_settings_from_averages
    
    result = update_premium_settings_from_averages(db, weeks, min_transactions)
    db.commit()
    
    return result


@router.get("/premium-settings/averages")
async def get_premium_averages(
    weeks: int = 4,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Get calculated 4-week averages without updating settings."""
    from app.modules.strategies.services import calculate_4_week_average_premiums
    
    averages = calculate_4_week_average_premiums(db, weeks)
    
    return {
        "weeks": weeks,
        "averages": averages,
        "symbol_count": len(averages)
    }


# ============================================================================
# STRATEGY RECOMMENDATIONS ENDPOINTS
# ============================================================================

from app.core.cache import cached_response

@router.get("/options-selling/recommendations")
@cached_response(base_ttl=60, extended_ttl=300, key_prefix="recommendations:")
async def get_options_recommendations(
    default_premium: float = Query(default=60),
    profit_threshold: float = Query(default=0.80),
    send_notification: bool = Query(default=False, description="Send notification if recommendations found"),
    notification_priority: Optional[str] = Query(default="high", description="Minimum priority to notify (urgent, high, medium, low)"),
    strategy_filter: Optional[str] = Query(default=None, description="Filter by strategy type"),
    force_refresh: bool = Query(default=False, description="Bypass cache and fetch fresh data from Schwab"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get actionable recommendations for options selling strategy.
    
    This endpoint analyzes your current portfolio state and generates
    prioritized recommendations for actions you should take using enabled strategies.
    
    Set send_notification=true to automatically send notifications for new recommendations.
    Set force_refresh=true to bypass the cache and fetch fresh live data from Schwab.
    """
    from app.modules.strategies.strategy_service import StrategyService
    import logging
    
    logger = logging.getLogger(__name__)
    
    params = {
        "default_premium": default_premium,
        "profit_threshold": profit_threshold
    }
    
    try:
        service = StrategyService(db)
        recommendations = service.generate_recommendations(params)
        
        # Save recommendations to history for tracking
        if recommendations:
            try:
                from app.modules.strategies.recommendations import OptionsStrategyRecommendationService
                rec_service = OptionsStrategyRecommendationService(db)
                saved_count = rec_service.save_recommendations_to_history(recommendations)
                logger.info(f"Saved {saved_count} recommendations to history")
            except Exception as save_error:
                logger.warning(f"Failed to save recommendations to history: {save_error}")
                # Don't fail the request if saving to history fails
    except Exception as e:
        logger.error(f"Error generating recommendations: {e}", exc_info=True)
        # Return empty recommendations rather than failing completely
        recommendations = []
    
    # Filter by strategy if requested
    if strategy_filter:
        recommendations = [r for r in recommendations if r.type == strategy_filter]
    
    # Log summary by strategy type
    by_type = {}
    for rec in recommendations:
        rec_type = rec.type
        by_type[rec_type] = by_type.get(rec_type, 0) + 1
    logger.info(f"API returning recommendations by type: {by_type} (total: {len(recommendations)})")
    
    # Convert to dict for JSON serialization
    recommendations_data = []
    for rec in recommendations:
        rec_dict = rec.dict()
        
        # Ensure account_name and symbol are extracted from context if not set
        if not rec_dict.get("account_name") and rec_dict.get("context"):
            context = rec_dict.get("context", {})
            account_name = context.get("account_name") or context.get("account")
            if account_name:
                rec_dict["account_name"] = account_name
        
        if not rec_dict.get("symbol") and rec_dict.get("context"):
            context = rec_dict.get("context", {})
            symbol = context.get("symbol")
            if symbol:
                rec_dict["symbol"] = symbol
        
        # Convert datetime to ISO string with explicit UTC indicator
        def to_utc_iso(dt):
            if dt is None:
                return None
            iso = dt.isoformat()
            # If timezone-aware, isoformat() already includes +00:00
            # If naive (shouldn't happen, but safety), append Z
            if dt.tzinfo is None and 'Z' not in iso and '+' not in iso:
                return iso + 'Z'
            return iso
        
        if rec_dict.get("created_at"):
            rec_dict["created_at"] = to_utc_iso(rec_dict["created_at"])
        if rec_dict.get("expires_at"):
            rec_dict["expires_at"] = to_utc_iso(rec_dict["expires_at"])
        recommendations_data.append(rec_dict)
    
    # Send notifications if requested
    # Only send for strategies that have notification_enabled=True
    notification_results = {}
    if send_notification and recommendations_data:
        from app.shared.services.notifications import get_notification_service
        notification_service = get_notification_service()
        
        # Filter recommendations by strategy notification settings
        strategy_service = StrategyService(db)
        notifiable_recommendations = []
        
        for rec in recommendations_data:
            strategy_config = strategy_service.get_strategy_config(rec["type"])
            if strategy_config and strategy_config.notification_enabled:
                # Check if priority meets threshold
                priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
                rec_priority = priority_order.get(rec["priority"], 99)
                threshold_priority = priority_order.get(
                    strategy_config.notification_priority_threshold or notification_priority,
                    99
                )
                if rec_priority <= threshold_priority:
                    notifiable_recommendations.append(rec)
        
        if notifiable_recommendations:
            notification_results = notification_service.send_recommendation_notification(
                notifiable_recommendations,
                priority_filter=notification_priority
            )
    
    # Group by strategy
    by_strategy = {}
    for rec in recommendations_data:
        strategy_type = rec["type"]
        if strategy_type not in by_strategy:
            by_strategy[strategy_type] = []
        by_strategy[strategy_type].append(rec)
    
    from datetime import datetime
    return {
        "recommendations": recommendations_data,
        "count": len(recommendations_data),
        "generated_at": datetime.now(timezone.utc).isoformat(),  # Timestamp when recommendations were generated (UTC)
        "by_priority": {
            "urgent": len([r for r in recommendations_data if r["priority"] == "urgent"]),
            "high": len([r for r in recommendations_data if r["priority"] == "high"]),
            "medium": len([r for r in recommendations_data if r["priority"] == "medium"]),
            "low": len([r for r in recommendations_data if r["priority"] == "low"]),
        },
        "by_category": {
            cat: len([r for r in recommendations_data if r["category"] == cat])
            for cat in ["income_generation", "risk_management", "optimization"]
        },
        "by_strategy": {k: len(v) for k, v in by_strategy.items()},
        "notifications_sent": notification_results if send_notification else None
    }


# ============================================================================
# STRATEGY MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/strategies")
async def get_all_strategies(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Get all available strategies with their configurations."""
    from app.modules.strategies.strategy_service import StrategyService
    from app.modules.strategies.strategies import STRATEGY_REGISTRY
    
    service = StrategyService(db)
    configs = service.get_all_strategy_configs()
    
    # Get info for all registered strategies (even if not in DB yet)
    all_strategies = []
    config_dict = {c.strategy_type: c for c in configs}
    
    for strategy_type, strategy_class in STRATEGY_REGISTRY.items():
        strategy_info = service.get_strategy_info(strategy_type)
        if strategy_info:
            config = config_dict.get(strategy_type)
            if config:
                strategy_info["enabled"] = config.enabled
                strategy_info["notification_enabled"] = config.notification_enabled
                strategy_info["notification_priority_threshold"] = config.notification_priority_threshold
                strategy_info["parameters"] = config.parameters
            else:
                # Strategy exists but no config in DB - use defaults
                strategy_info["enabled"] = True
                strategy_info["notification_enabled"] = True
                strategy_info["notification_priority_threshold"] = "high"
                strategy_info["parameters"] = strategy_class.default_parameters
            
            all_strategies.append(strategy_info)
    
    return {
        "strategies": all_strategies,
        "count": len(all_strategies)
    }


@router.get("/strategies/{strategy_type}")
async def get_strategy(
    strategy_type: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Get configuration for a specific strategy."""
    from app.modules.strategies.strategy_service import StrategyService
    
    service = StrategyService(db)
    config = service.get_strategy_config(strategy_type)
    
    if not config:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_type} not found")
    
    strategy_info = service.get_strategy_info(strategy_type)
    
    return {
        **strategy_info,
        "enabled": config.enabled,
        "notification_enabled": config.notification_enabled,
        "notification_priority_threshold": config.notification_priority_threshold,
        "parameters": config.parameters
    }


@router.put("/strategies/{strategy_type}")
async def update_strategy(
    strategy_type: str,
    request: StrategyUpdateRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Update strategy configuration."""
    from app.modules.strategies.strategy_service import StrategyService
    
    service = StrategyService(db)
    
    try:
        config = service.update_strategy_config(
            strategy_type=strategy_type,
            enabled=request.enabled,
            notification_enabled=request.notification_enabled,
            notification_priority_threshold=request.notification_priority_threshold,
            parameters=request.parameters
        )
        
        return {
            "success": True,
            "strategy": {
                "strategy_type": config.strategy_type,
                "name": config.name,
                "enabled": config.enabled,
                "notification_enabled": config.notification_enabled,
                "notification_priority_threshold": config.notification_priority_threshold,
                "parameters": config.parameters
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/strategies/debug")
async def debug_strategies(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Debug endpoint to see which strategies are enabled and what they're generating."""
    from app.modules.strategies.strategy_service import StrategyService
    import logging
    
    logger = logging.getLogger(__name__)
    
    service = StrategyService(db)
    enabled_strategies = service.get_enabled_strategies()
    
    debug_info = {
        "enabled_strategies": [],
        "recommendations_by_strategy": {},
        "total_recommendations": 0
    }
    
    for strategy in enabled_strategies:
        strategy_info = {
            "strategy_type": strategy.strategy_type,
            "name": strategy.name,
            "enabled": strategy.config.enabled,
            "notification_enabled": strategy.config.notification_enabled,
            "notification_priority_threshold": strategy.config.notification_priority_threshold,
            "parameters": strategy.config.parameters
        }
        debug_info["enabled_strategies"].append(strategy_info)
        
        # Try to generate recommendations for this strategy
        try:
            params = {
                "default_premium": 60,
                "profit_threshold": 0.80
            }
            recommendations = strategy.generate_recommendations(params)
            debug_info["recommendations_by_strategy"][strategy.strategy_type] = {
                "count": len(recommendations),
                "recommendations": [
                    {
                        "id": rec.id,
                        "type": rec.type,
                        "priority": rec.priority,
                        "title": rec.title,
                        "symbol": rec.context.get("symbol") if rec.context else None
                    }
                    for rec in recommendations[:5]  # Limit to first 5
                ]
            }
            debug_info["total_recommendations"] += len(recommendations)
        except Exception as e:
            debug_info["recommendations_by_strategy"][strategy.strategy_type] = {
                "count": 0,
                "error": str(e)
            }
            logger.error(f"Error testing strategy {strategy.strategy_type}: {e}", exc_info=True)

    return debug_info


@router.post("/debug/clear-cache")
async def clear_all_caches():
    """
    Clear all price and options data caches.

    Useful for forcing fresh API calls after testing.
    No authentication required for debugging.
    """
    from app.modules.strategies.yahoo_cache import clear_cache, get_cache_stats

    # Get stats before clearing
    stats_before = get_cache_stats()

    # Clear all caches
    clear_cache()

    # Get stats after clearing
    stats_after = get_cache_stats()

    return {
        "message": "All caches cleared",
        "stats_before": stats_before,
        "stats_after": stats_after
    }


@router.post("/strategies/{strategy_type}/test")
async def test_strategy(
    strategy_type: str,
    params: Optional[Dict[str, Any]] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Test a strategy to see what recommendations it would generate."""
    from app.modules.strategies.strategy_service import StrategyService
    from app.modules.strategies.strategies import STRATEGY_REGISTRY
    
    if params is None:
        params = {}
    
    strategy_class = STRATEGY_REGISTRY.get(strategy_type)
    if not strategy_class:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_type} not found")
    
    service = StrategyService(db)
    config = service.get_strategy_config(strategy_type)
    
    if not config:
        # Create temporary config with defaults
        from app.modules.strategies.strategy_base import StrategyConfig
        config = StrategyConfig(
            strategy_type=strategy_type,
            name=strategy_class.name,
            description=strategy_class.description,
            category=strategy_class.category,
            parameters=strategy_class.default_parameters
        )
    
    # Create strategy instance and generate recommendations
    strategy = strategy_class(db, config)
    recommendations = strategy.generate_recommendations(params)
    
    # Convert to dict
    def to_utc_iso_single(dt):
        if dt is None:
            return None
        iso = dt.isoformat()
        if dt.tzinfo is None and 'Z' not in iso and '+' not in iso:
            return iso + 'Z'
        return iso
    
    recommendations_data = []
    for rec in recommendations:
        rec_dict = rec.dict()
        if rec_dict.get("created_at"):
            rec_dict["created_at"] = to_utc_iso_single(rec_dict["created_at"])
        if rec_dict.get("expires_at"):
            rec_dict["expires_at"] = to_utc_iso_single(rec_dict["expires_at"])
        recommendations_data.append(rec_dict)
    
    return {
        "strategy_type": strategy_type,
        "recommendations": recommendations_data,
        "count": len(recommendations_data)
    }


# ============================================================================
# SCHEDULER DIAGNOSTICS
# ============================================================================

@router.get("/scheduler/status")
async def get_scheduler_status(
    user=Depends(get_current_user)
):
    """
    Get scheduler status and list of scheduled jobs.

    Use this to diagnose why scheduled notifications might not be running.
    """
    from app.core.scheduler import get_scheduler
    import pytz

    PT = pytz.timezone('America/Los_Angeles')

    scheduler = get_scheduler()

    if scheduler is None:
        return {
            "status": "not_running",
            "message": "Scheduler has not been started. Backend may need restart.",
            "jobs": []
        }

    if not scheduler.scheduler.running:
        return {
            "status": "stopped",
            "message": "Scheduler exists but is not running.",
            "jobs": []
        }

    # Get all scheduled jobs
    jobs = []
    for job in scheduler.scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": next_run.astimezone(PT).strftime('%Y-%m-%d %H:%M:%S %Z') if next_run else "Not scheduled",
            "trigger": str(job.trigger),
        })

    # Sort by next run time
    jobs.sort(key=lambda x: x["next_run_time"] if x["next_run_time"] != "Not scheduled" else "9999")

    now_pt = datetime.now(PT)

    return {
        "status": "running",
        "current_time_pt": now_pt.strftime('%Y-%m-%d %H:%M:%S %Z'),
        "day_of_week": now_pt.strftime('%A'),
        "is_weekday": now_pt.weekday() < 5,
        "jobs_count": len(jobs),
        "jobs": jobs,
        "note": "Jobs only run Monday-Friday. Today is " + now_pt.strftime('%A') + "."
    }


# ============================================================================
# TECHNICAL ANALYSIS ENDPOINTS
# ============================================================================

@router.get("/technical-analysis/{symbol}")
async def get_technical_analysis(
    symbol: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get comprehensive technical analysis for a symbol.
    
    Returns:
    - Current price and 52-week range
    - Moving averages (50-day, 200-day)
    - Volatility metrics (daily, weekly, annualized)
    - RSI (14-day) with overbought/oversold status
    - Bollinger Bands (20-day, 2σ)
    - Support and resistance levels
    - Probability ranges for options selling
    - Trend analysis
    - Earnings date if available
    """
    from app.modules.strategies.technical_analysis import get_technical_analysis_service
    
    ta_service = get_technical_analysis_service()
    indicators = ta_service.get_technical_indicators(symbol.upper())
    
    if not indicators:
        raise HTTPException(
            status_code=404,
            detail=f"Could not fetch technical data for {symbol}. Check if the symbol is valid."
        )
    
    return {
        "symbol": symbol.upper(),
        "indicators": indicators.to_dict(),
        "summary": {
            "trend": indicators.trend,
            "rsi_status": indicators.rsi_status,
            "bollinger_position": indicators.bb_position,
            "recommendation": _get_summary_recommendation(indicators)
        }
    }


def _get_summary_recommendation(indicators) -> str:
    """Generate a summary recommendation based on technical indicators."""
    signals = []
    
    if indicators.rsi_status == "overbought":
        signals.append("overbought (RSI > 70)")
    elif indicators.rsi_status == "oversold":
        signals.append("oversold (RSI < 30)")
    
    if indicators.bb_position == "above_upper":
        signals.append("above upper Bollinger Band")
    elif indicators.bb_position == "below_lower":
        signals.append("below lower Bollinger Band")
    
    if indicators.trend == "bullish":
        signals.append("bullish trend")
    elif indicators.trend == "bearish":
        signals.append("bearish trend")
    
    if not signals:
        return "Neutral - no strong signals"
    
    return ", ".join(signals).capitalize()


def _compute_option_signal(indicators, utilization: str) -> dict:
    """
    Compute a directional signal for a symbol's options.

    Returns a dict with:
      action: "sell" | "hold" | "buy_back"
      confidence: "strong" | "moderate" | "weak"
      reason: short human-readable explanation
    """
    score = 0  # positive = sell, negative = buy back, near 0 = hold
    reasons = []

    # RSI signals
    if indicators.rsi_14 >= 70:
        score += 2
        reasons.append("overbought RSI")
    elif indicators.rsi_14 >= 60:
        score += 1
        reasons.append("elevated RSI")
    elif indicators.rsi_14 <= 30:
        score -= 2
        reasons.append("oversold RSI")
    elif indicators.rsi_14 <= 40:
        score -= 1
        reasons.append("low RSI")

    # Trend signals — bearish trend is good for selling calls (stock stays flat/drops)
    if indicators.trend == "bearish":
        score += 1
        reasons.append("bearish trend")
    elif indicators.trend == "bullish":
        score -= 1
        reasons.append("bullish trend")

    # Bollinger Band position
    if indicators.bb_position in ("above_upper",):
        score += 1
        reasons.append("above upper BB")
    elif indicators.bb_position in ("below_lower",):
        score -= 1
        reasons.append("below lower BB")

    # Price vs moving averages — below 50-day MA = safer to sell calls
    if indicators.ma_50 and indicators.current_price < indicators.ma_50 * 0.97:
        score += 1
        reasons.append("below 50-day MA")
    elif indicators.ma_50 and indicators.current_price > indicators.ma_50 * 1.03:
        score -= 1
        reasons.append("above 50-day MA")

    # Earnings proximity — risky to sell near earnings
    if indicators.earnings_within_week:
        score -= 2
        reasons.append("earnings within week")

    # Determine action based on score and current utilization
    if utilization == "none":
        # All options are unsold — decide sell vs hold
        if score >= 2:
            action, confidence = "sell", "strong"
        elif score >= 1:
            action, confidence = "sell", "moderate"
        elif score <= -2:
            action, confidence = "hold", "strong"
        elif score <= -1:
            action, confidence = "hold", "moderate"
        else:
            action, confidence = "sell", "weak"
    elif utilization == "full":
        # All sold — decide buy back vs hold
        if score <= -2:
            action, confidence = "buy_back", "strong"
        elif score <= -1:
            action, confidence = "buy_back", "moderate"
        elif score >= 2:
            action, confidence = "hold", "strong"
        elif score >= 1:
            action, confidence = "hold", "moderate"
        else:
            action, confidence = "hold", "weak"
    else:
        # Partial — could go either way
        if score >= 2:
            action, confidence = "sell", "strong"
        elif score >= 1:
            action, confidence = "sell", "moderate"
        elif score <= -2:
            action, confidence = "buy_back", "strong"
        elif score <= -1:
            action, confidence = "buy_back", "moderate"
        else:
            action, confidence = "hold", "weak"

    return {
        "action": action,
        "confidence": confidence,
        "score": score,
        "reason": "; ".join(reasons) if reasons else "no strong signals",
    }


@router.post("/technical-analysis/batch-signals")
async def get_batch_signals(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get directional option signals for multiple symbols at once.

    Request body: { "symbols": [{ "symbol": "AAPL", "utilization": "partial" }, ...] }
    Returns: { "signals": { "AAPL": { "action": "sell", "confidence": "strong", "reason": "..." }, ... } }
    """
    from app.modules.strategies.technical_analysis import get_technical_analysis_service
    import logging

    logger = logging.getLogger(__name__)
    body = await request.json()
    symbol_requests = body.get("symbols", [])

    ta_service = get_technical_analysis_service()
    signals = {}

    for item in symbol_requests:
        sym = item.get("symbol", "").upper()
        utilization = item.get("utilization", "none")

        if not sym or sym == "CASH":
            continue

        try:
            indicators = ta_service.get_technical_indicators(sym)
            if indicators:
                signals[sym] = _compute_option_signal(indicators, utilization)
            else:
                signals[sym] = {
                    "action": "hold",
                    "confidence": "weak",
                    "score": 0,
                    "reason": "no data available",
                }
        except Exception as e:
            logger.warning(f"Failed to get TA for {sym}: {e}")
            signals[sym] = {
                "action": "hold",
                "confidence": "weak",
                "score": 0,
                "reason": "analysis unavailable",
            }

    return {"signals": signals}


@router.get("/technical-analysis/{symbol}/strike-recommendation")
async def get_strike_recommendation(
    symbol: str,
    option_type: str = Query(..., description="call or put"),
    weeks: int = Query(default=1, description="Weeks until expiration"),
    probability: float = Query(default=90, description="Target probability OTM (e.g., 90 for 90%)"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get recommended strike price for selling options.
    
    Uses technical analysis to recommend a strike price that:
    - Has the specified probability of staying OTM
    - Considers support/resistance levels
    - Accounts for current volatility
    """
    from app.modules.strategies.technical_analysis import get_technical_analysis_service
    
    if option_type.lower() not in ["call", "put"]:
        raise HTTPException(status_code=400, detail="option_type must be 'call' or 'put'")
    
    ta_service = get_technical_analysis_service()
    
    strike_rec = ta_service.recommend_strike_price(
        symbol=symbol.upper(),
        option_type=option_type.lower(),
        expiration_weeks=weeks,
        probability_target=probability / 100.0
    )
    
    if not strike_rec:
        raise HTTPException(
            status_code=404,
            detail=f"Could not generate strike recommendation for {symbol}"
        )
    
    # Also get full indicators for context
    indicators = ta_service.get_technical_indicators(symbol.upper())
    
    return {
        "symbol": symbol.upper(),
        "option_type": option_type.lower(),
        "expiration_weeks": weeks,
        "target_probability": probability,
        "recommendation": strike_rec.to_dict(),
        "context": {
            "current_price": indicators.current_price if indicators else None,
            "weekly_volatility_pct": round(indicators.weekly_volatility * 100, 2) if indicators else None,
            "rsi": round(indicators.rsi_14, 1) if indicators else None,
            "trend": indicators.trend if indicators else None,
        }
    }


@router.get("/put-scouting")
async def get_put_scouting(
    symbols: str = Query(..., description="Comma-separated list of symbols"),
    weeks: int = Query(default=1, description="Weeks until expiration"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Return delta-80 and delta-90 strike/premium projections for a list of symbols.
    Used by the Put Scouting panel on the Options Income page.
    Fetches all symbols in parallel via a thread pool.
    """
    from app.modules.strategies.technical_analysis import get_technical_analysis_service
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    symbol_list = [s.strip().upper() for s in symbols.split(',') if s.strip()]
    if not symbol_list:
        return []

    ta_service = get_technical_analysis_service()

    def scout(sym: str):
        try:
            return ta_service.scout_put_strikes(sym, probability_targets=[0.80, 0.90], weeks=weeks)
        except Exception as e:
            return {"symbol": sym, "error": str(e), "targets": []}

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=min(len(symbol_list), 8)) as pool:
        tasks = [loop.run_in_executor(pool, scout, sym) for sym in symbol_list]
        results = await asyncio.gather(*tasks)

    return [r for r in results if r is not None]


@router.get("/technical-analysis/{symbol}/volatility-risk")
async def assess_volatility_risk(
    symbol: str,
    expiration_date: str = Query(..., description="Expiration date (YYYY-MM-DD)"),
    profit_captured: float = Query(..., description="Profit captured percentage (0-100)"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Assess volatility risk for a position.
    
    Used to determine if an option should be closed early due to
    upcoming volatility (earnings, technical breakouts, etc.)
    """
    from app.modules.strategies.technical_analysis import get_technical_analysis_service
    from datetime import datetime
    
    try:
        exp_date = datetime.strptime(expiration_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    ta_service = get_technical_analysis_service()
    
    risk = ta_service.assess_volatility_risk(
        symbol=symbol.upper(),
        expiration_date=exp_date,
        profit_captured_pct=profit_captured
    )
    
    return {
        "symbol": symbol.upper(),
        "expiration_date": expiration_date,
        "profit_captured": profit_captured,
        "risk_assessment": risk.to_dict()
    }


@router.get("/data-freshness")
async def get_data_freshness(user=Depends(get_current_user)):
    """
    Get information about Yahoo Finance data freshness.
    
    Returns:
    - last_options_fetch: When options data was last fetched
    - cache_ttl_seconds: Current cache TTL (varies by market hours)
    - is_market_hours: Whether market is currently open
    - next_refresh_available: When cache will expire
    
    This helps the UI show users how fresh the data is.
    """
    from app.modules.strategies.yahoo_cache import (
        get_data_freshness_info,
        get_cache_stats
    )
    
    freshness = get_data_freshness_info()
    stats = get_cache_stats()
    
    return {
        **freshness,
        "cache_stats": stats
    }


@router.post("/clear-cache")
async def clear_yahoo_cache(
    symbol: Optional[str] = Query(default=None, description="Symbol to clear, or None for all"),
    user=Depends(get_current_user)
):
    """
    Clear Yahoo Finance cache to force fresh data fetch.
    
    Use this if you need real-time data immediately.
    Note: May hit rate limits if called frequently.
    """
    from app.modules.strategies.yahoo_cache import clear_cache, get_cache_stats
    
    clear_cache(symbol)
    
    return {
        "success": True,
        "message": f"Cleared cache for {symbol if symbol else 'all symbols'}",
        "cache_stats": get_cache_stats()
    }


# ============================================================================
# DEBUG: HOLDINGS DATA VERIFICATION
# ============================================================================

@router.get("/debug/holdings/{symbol}")
async def debug_holdings_for_symbol(
    symbol: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Debug endpoint to show raw database data for a specific symbol.
    
    Shows:
    - All holdings rows for the symbol across all accounts
    - All accounts that have this symbol
    - Whether there are duplicates that could cause aggregation issues
    
    Use this to debug when Options Selling shows incorrect share counts.
    """
    from app.modules.investments.models import InvestmentHolding, InvestmentAccount
    
    symbol_upper = symbol.upper()
    
    # Get ALL holdings for this symbol (including from all sources)
    holdings = db.query(InvestmentHolding).filter(
        InvestmentHolding.symbol == symbol_upper
    ).all()
    
    holdings_data = []
    for h in holdings:
        # Look up the account
        account = db.query(InvestmentAccount).filter(
            InvestmentAccount.account_id == h.account_id,
            InvestmentAccount.source == h.source
        ).first()
        
        holdings_data.append({
            "holding_id": h.id if hasattr(h, 'id') else None,
            "account_id": h.account_id,
            "source": h.source,
            "account_name": account.account_name if account else "NO ACCOUNT FOUND",
            "account_type": account.account_type if account else None,
            "symbol": h.symbol,
            "quantity": float(h.quantity) if h.quantity else 0,
            "current_price": float(h.current_price) if h.current_price else 0,
            "market_value": float(h.market_value) if h.market_value else 0,
            "last_updated": h.last_updated.isoformat() if h.last_updated else None,
        })
    
    # Get all accounts that COULD have this symbol
    all_accounts = db.query(InvestmentAccount).filter(
        InvestmentAccount.account_type.in_(['brokerage', 'retirement', 'ira', 'roth_ira'])
    ).all()
    
    accounts_data = []
    for a in all_accounts:
        accounts_data.append({
            "account_id": a.account_id,
            "account_name": a.account_name,
            "source": a.source,
            "account_type": a.account_type,
        })
    
    # Check for potential duplicates (same account_name but different account_id)
    account_names = {}
    for h in holdings_data:
        name = h["account_name"]
        if name not in account_names:
            account_names[name] = []
        account_names[name].append(h)
    
    duplicates = {
        name: rows for name, rows in account_names.items() 
        if len(rows) > 1
    }
    
    # Calculate total that would show in Options Selling (by account_name)
    totals_by_account_name = {}
    for h in holdings_data:
        name = h["account_name"]
        if name not in totals_by_account_name:
            totals_by_account_name[name] = 0
        totals_by_account_name[name] += h["quantity"]
    
    return {
        "symbol": symbol_upper,
        "total_holdings_rows": len(holdings),
        "holdings": holdings_data,
        "totals_by_account_name": totals_by_account_name,
        "has_potential_duplicates": len(duplicates) > 0,
        "potential_duplicates": duplicates,
        "all_brokerage_accounts": accounts_data,
        "diagnosis": (
            f"ISSUE FOUND: Multiple holdings rows for same account_name are being aggregated. "
            f"See 'potential_duplicates' for details."
            if duplicates else
            "No duplicate account_names found. Check if total matches expected."
        )
    }


@router.get("/debug/accounts")
async def debug_all_accounts(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Debug endpoint to show all investment accounts and their holdings summary.
    
    Use this to identify:
    - Duplicate accounts with same name but different IDs
    - Accounts that might need to be merged
    """
    from app.modules.investments.models import InvestmentHolding, InvestmentAccount
    
    accounts = db.query(InvestmentAccount).order_by(
        InvestmentAccount.account_name,
        InvestmentAccount.source
    ).all()
    
    result = []
    for a in accounts:
        # Get holdings count and total for this account
        holdings = db.query(InvestmentHolding).filter(
            InvestmentHolding.account_id == a.account_id,
            InvestmentHolding.source == a.source
        ).all()
        
        total_value = sum(float(h.market_value or 0) for h in holdings)
        symbols = [h.symbol for h in holdings if h.quantity and float(h.quantity) >= 100]
        
        result.append({
            "account_id": a.account_id,
            "account_name": a.account_name,
            "source": a.source,
            "account_type": a.account_type,
            "holdings_count": len(holdings),
            "total_value": round(total_value, 2),
            "symbols_with_100_plus_shares": symbols,
        })
    
    # Check for duplicate account_names
    name_counts = {}
    for a in result:
        name = a["account_name"]
        if name not in name_counts:
            name_counts[name] = []
        name_counts[name].append(a)
    
    duplicates = {
        name: accounts for name, accounts in name_counts.items()
        if len(accounts) > 1
    }
    
    return {
        "total_accounts": len(accounts),
        "accounts": result,
        "duplicate_account_names": duplicates,
        "has_duplicates": len(duplicates) > 0,
        "recommendation": (
            "DUPLICATE ACCOUNTS FOUND! Accounts with the same name but different IDs "
            "will have their holdings aggregated in the Options Selling page. "
            "Use the /api/v1/ingestion/merge-accounts endpoint to consolidate them."
            if duplicates else
            "No duplicate account names found."
        )
    }


# =============================================================================
# PUT SELLING OPPORTUNITIES
# =============================================================================

@router.get("/put-opportunities")
async def get_put_opportunities(
    refresh: bool = Query(default=False, description="Set to true to recalculate from live data"),
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user)
):
    """
    Get put selling opportunities for portfolio stocks.

    By default, returns cached data from the database (fast).
    Set refresh=true to recalculate from live TA data and options chains (slow but fresh).
    """
    from app.modules.strategies.strategies.cash_secured_put import CashSecuredPutStrategy
    from app.modules.strategies.strategy_base import StrategyConfig

    try:
        # If not refreshing, load from database first
        if not refresh:
            # Query today's put opportunities from database
            today = date.today()
            results = db.execute(text("""
                SELECT
                    symbol, stock_price, strike, expiration,
                    bid_price, ask_price, delta, premium_per_contract,
                    otm_pct, score, grade, rsi, bb_position_pct,
                    rsi_score, bb_score, premium_score, ta_score,
                    trend, full_context, created_at
                FROM put_opportunities
                WHERE recommendation_date = :today
                ORDER BY score DESC
            """), {"today": today}).fetchall()

            if results:
                opportunities = []
                for row in results:
                    full_context = row.full_context or {}
                    opportunities.append({
                        "symbol": row.symbol,
                        "current_price": float(row.stock_price) if row.stock_price else 0,
                        "strike": float(row.strike) if row.strike else 0,
                        "otm_pct": float(row.otm_pct) if row.otm_pct else 0,
                        "bid": float(row.bid_price) if row.bid_price else 0,
                        "ask": float(row.ask_price) if row.ask_price else 0,
                        "premium": float(row.premium_per_contract) if row.premium_per_contract else 0,
                        "grade": row.grade or "",
                        "score": float(row.score) if row.score else 0,
                        "roi_pct": full_context.get("roi_pct", 0),
                        "capital_required": float(row.strike) * 100 if row.strike else 0,
                        "expiration": row.expiration.isoformat() if row.expiration else "",
                        "delta": float(row.delta) if row.delta else 0,
                        "prob_otm": (1 - abs(float(row.delta))) * 100 if row.delta else 90,
                        "rsi": float(row.rsi) if row.rsi else 0,
                        "rsi_status": full_context.get("rsi_status", ""),
                        "bb_position_pct": float(row.bb_position_pct) if row.bb_position_pct else 0,
                        "bb_status": full_context.get("bb_status", ""),
                        "ta_score": int(row.ta_score) if row.ta_score else 0,
                        "premium_score": int(row.premium_score) if row.premium_score else 0,
                        "trend": row.trend or "",
                        "rationale": full_context.get("rationale", ""),
                    })

                # Get the most recent update time
                latest_update = max(row.created_at for row in results) if results else None

                return {
                    "opportunities": opportunities,
                    "count": len(opportunities),
                    "updated_at": latest_update.isoformat() if latest_update else None,
                    "from_cache": True,
                }

        # Refresh = true OR no cached data: Calculate fresh
        logger.info("Calculating fresh put opportunities...")

        config = StrategyConfig(
            strategy_type="cash_secured_put",
            name="Cash-Secured Put Strategy",
            description="Put selling opportunities",
            category="income_generation",
            enabled=True,
            notification_enabled=True,
            parameters={}
        )
        strategy = CashSecuredPutStrategy(db, config)

        # Generate recommendations (this does all the TA analysis and saves to DB)
        recommendations = strategy.generate_recommendations({})

        # Convert to response format
        opportunities = []
        for rec in recommendations:
            context = rec.context if hasattr(rec, 'context') else {}
            opportunities.append({
                "symbol": context.get("symbol", ""),
                "current_price": context.get("stock_price", 0),
                "strike": context.get("strike", 0),
                "otm_pct": context.get("otm_pct", 0),
                "bid": context.get("bid", 0),
                "ask": context.get("ask", 0),
                "premium": context.get("premium_per_contract", 0),
                "grade": context.get("grade", ""),
                "score": context.get("combined_score", 0),
                "roi_pct": context.get("roi_pct", 0),
                "capital_required": context.get("capital_required", 0),
                "expiration": context.get("expiration", ""),
                "delta": context.get("delta", 0),
                "prob_otm": context.get("prob_otm", 0),
                "rsi": context.get("rsi", 0),
                "rsi_status": context.get("rsi_status", ""),
                "bb_position_pct": context.get("bb_position_pct", 0),
                "bb_status": context.get("bb_status", ""),
                "ta_score": context.get("ta_score", 0),
                "premium_score": context.get("premium_score", 0),
                "trend": context.get("trend", ""),
                "rationale": rec.rationale if hasattr(rec, 'rationale') else "",
            })

        opportunities.sort(key=lambda x: x.get("score", 0), reverse=True)

        return {
            "opportunities": opportunities,
            "count": len(opportunities),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "from_cache": False,
        }

    except Exception as e:
        logger.error(f"Error fetching put opportunities: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ACQUISITION WATCHLIST (Stocks to buy via puts)
# =============================================================================

class AcquisitionWatchlistItem(BaseModel):
    """Request model for adding a stock to acquisition watchlist."""
    symbol: str
    target_price: Optional[float] = None
    notes: Optional[str] = None


@router.get("/acquisition-watchlist")
async def get_acquisition_watchlist(
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user)
):
    """Get all stocks in the acquisition watchlist with current put options."""
    from app.modules.strategies.schwab_service import get_options_chain_schwab
    from app.modules.strategies.technical_analysis import get_technical_analysis_service
    from datetime import timedelta

    try:
        # Get watchlist items
        results = db.execute(text("""
            SELECT id, symbol, target_price, notes, active, created_at
            FROM acquisition_watchlist
            WHERE active = true
            ORDER BY created_at DESC
        """)).fetchall()

        if not results:
            return {"watchlist": [], "count": 0}

        # Get next Friday for expiration
        today = date.today()
        days_ahead = 4 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        next_friday = today + timedelta(days=days_ahead)

        ta_service = get_technical_analysis_service()
        watchlist = []

        for row in results:
            symbol = row.symbol
            item = {
                "id": row.id,
                "symbol": symbol,
                "target_price": float(row.target_price) if row.target_price else None,
                "notes": row.notes,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "current_price": None,
                "put_options": [],
                "ta_summary": None,
            }

            # Get current price and TA
            try:
                indicators = ta_service.get_technical_indicators(symbol)
                if indicators:
                    item["current_price"] = indicators.current_price
                    item["ta_summary"] = {
                        "rsi": indicators.rsi_14,
                        "rsi_status": indicators.rsi_status,
                        "bb_position_pct": ((indicators.current_price - indicators.bb_lower) /
                                           (indicators.bb_upper - indicators.bb_lower)) * 100
                                           if indicators.bb_upper != indicators.bb_lower else 50,
                        "trend": indicators.trend,
                    }

                    # Get put options near target price or 5-10% OTM
                    target = row.target_price or (indicators.current_price * 0.95)
                    chain = get_options_chain_schwab(symbol, next_friday.isoformat(), 'PUT')

                    if chain and 'puts' in chain:
                        for opt in chain['puts']:
                            strike = opt.get('strike', 0)
                            bid = opt.get('bid', 0) or 0
                            delta = abs(opt.get('delta', 0) or 0)

                            if strike <= 0 or bid <= 0:
                                continue

                            # Show strikes within 15% of current price
                            otm_pct = ((indicators.current_price - strike) / indicators.current_price) * 100
                            if 0 < otm_pct <= 15:
                                premium = bid * 100
                                effective_buy = strike - bid
                                discount = ((indicators.current_price - effective_buy) / indicators.current_price) * 100

                                item["put_options"].append({
                                    "strike": strike,
                                    "bid": bid,
                                    "ask": opt.get('ask', 0) or 0,
                                    "delta": delta,
                                    "otm_pct": round(otm_pct, 1),
                                    "premium": round(premium, 0),
                                    "effective_buy_price": round(effective_buy, 2),
                                    "discount_pct": round(discount, 1),
                                    "capital_required": strike * 100,
                                    "expiration": next_friday.isoformat(),
                                    "prob_otm": round((1 - delta) * 100, 0),
                                })

                        # Sort by strike descending (closest to current price first)
                        item["put_options"].sort(key=lambda x: x["strike"], reverse=True)
                        # Limit to top 5 options
                        item["put_options"] = item["put_options"][:5]

            except Exception as e:
                logger.warning(f"Error getting data for {symbol}: {e}")

            watchlist.append(item)

        return {
            "watchlist": watchlist,
            "count": len(watchlist),
            "next_expiration": next_friday.isoformat(),
        }

    except Exception as e:
        logger.error(f"Error fetching acquisition watchlist: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/acquisition-watchlist")
async def add_to_acquisition_watchlist(
    item: AcquisitionWatchlistItem,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user)
):
    """Add a stock to the acquisition watchlist."""
    try:
        # Check if already exists
        existing = db.execute(text(
            "SELECT id FROM acquisition_watchlist WHERE symbol = :symbol"
        ), {"symbol": item.symbol.upper()}).fetchone()

        if existing:
            # Update existing entry
            db.execute(text("""
                UPDATE acquisition_watchlist
                SET target_price = :target_price, notes = :notes, active = true, updated_at = NOW()
                WHERE symbol = :symbol
            """), {
                "symbol": item.symbol.upper(),
                "target_price": item.target_price,
                "notes": item.notes,
            })
            db.commit()
            return {"message": f"{item.symbol.upper()} updated in watchlist", "action": "updated"}
        else:
            # Insert new entry
            db.execute(text("""
                INSERT INTO acquisition_watchlist (symbol, target_price, notes, active, created_at)
                VALUES (:symbol, :target_price, :notes, true, NOW())
            """), {
                "symbol": item.symbol.upper(),
                "target_price": item.target_price,
                "notes": item.notes,
            })
            db.commit()
            return {"message": f"{item.symbol.upper()} added to watchlist", "action": "added"}

    except Exception as e:
        logger.error(f"Error adding to acquisition watchlist: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/acquisition-watchlist/{symbol}")
async def remove_from_acquisition_watchlist(
    symbol: str,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user)
):
    """Remove a stock from the acquisition watchlist."""
    try:
        result = db.execute(text(
            "DELETE FROM acquisition_watchlist WHERE symbol = :symbol"
        ), {"symbol": symbol.upper()})
        db.commit()

        if result.rowcount > 0:
            return {"message": f"{symbol.upper()} removed from watchlist"}
        else:
            raise HTTPException(status_code=404, detail=f"{symbol.upper()} not found in watchlist")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing from acquisition watchlist: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Schwab Token Status & Re-Authentication
# =============================================================================

@router.get("/schwab/token-status")
async def get_schwab_token_status(user=Depends(get_current_user)):
    """
    Get Schwab token health status.
    Reads schwab_token.json and computes refresh token expiry (7 days from creation).
    No Schwab API call needed.
    """
    from app.modules.strategies.schwab_service import get_schwab_token_status as _get_status
    return _get_status()


@router.post("/schwab/authenticate")
async def trigger_schwab_auth(user=Depends(get_current_user)):
    """
    Trigger Schwab OAuth re-authentication.
    Runs authenticate_schwab() in a background thread (it blocks while waiting
    for browser OAuth). Returns immediately so the frontend can poll token-status.
    """
    from app.modules.strategies.schwab_service import authenticate_schwab, _auth_in_progress

    if _auth_in_progress:
        return {"message": "Authentication already in progress..."}

    def _run_auth():
        import app.modules.strategies.schwab_service as svc
        svc._auth_in_progress = True
        try:
            # Reset cached client so fresh token is picked up
            svc._schwab_client = None
            # Delete old token file to force browser-based re-auth
            # (otherwise easy_client may load the stale token and return
            # without opening a browser)
            svc.TOKEN_FILE.unlink(missing_ok=True)
            authenticate_schwab()
        finally:
            svc._auth_in_progress = False

    thread = threading.Thread(target=_run_auth, daemon=True)
    thread.start()

    return {"message": "Browser opened for Schwab login. Complete the OAuth flow to re-authenticate."}


# ============================================================================
# IMPROVEMENT IDEAS — AI-POWERED SELF-IMPROVEMENT LOOP
# ============================================================================

_IMPROVEMENT_SYSTEM_PROMPT = """You are an expert options income advisor analyzing a single brokerage account.

V6 Strategy Rules:
- Puts are the PRIMARY income engine; calls are secondary
- IRA/retirement accounts: Delta 75, trade aggressively, any stock is fine
- Taxable accounts: Delta 90 (deep OTM), trillion-dollar-market-cap stocks only (AAPL, NVDA, META, MSFT, TSLA, AMZN, GOOG)
- Preferred expirations: 1-2 weeks out; never beyond 4 weeks
- Runaway stocks (structural catalyst): roll at zero cost; do NOT close
- Oscillating stocks (sentiment/macro): use RSI < 45 as entry signal
- Unsold contracts = idle income — should always be sold unless there's a strong hold reason
- Available cash = put-selling capacity; cash sitting idle loses 1-2% weekly yield

Your task: Given the account snapshot below, generate 3-5 specific, actionable improvement ideas.

IMPORTANT RULES for ideas:
- Reference exact symbols, contracts, and dollar amounts from the data
- If a symbol has unsold contracts, flag it with estimated income opportunity
- If cash is available and no puts are open, suggest puts to sell
- Do NOT suggest selling calls on symbols with <100 shares
- Do NOT suggest IRA-type strategies on taxable accounts and vice versa
- Ideas must be immediately executable this week

Return ONLY a JSON array (no markdown, no explanation outside JSON):
[
  {
    "symbol": "AAPL",
    "title": "3 unsold contracts — $X idle",
    "action": "Sell 3x $185 puts expiring Jun 6 at Delta 90",
    "expected_income": "$630 (~$210/contract)",
    "rationale": "RSI at 42 (oscillating), near lower BB support, cash-secured, lowers avg cost if assigned"
  }
]

If there are no specific improvements (everything is fully utilized), return a single idea about optimizing expirations or rolling for more premium."""


@router.post("/options-selling/improvement-ideas")
async def generate_improvement_ideas(
    request: Request,
    user=Depends(get_current_user)
):
    """Generate AI-powered improvement ideas for an account's options income."""
    import asyncio
    import anthropic
    import json as _json

    raw = "[]"
    account_name = "Unknown Account"
    try:
        payload = await request.json()
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")

        account_name = payload.get("account_name", "Unknown Account")
        account_type = payload.get("account_type", "brokerage")
        account_value = float(payload.get("account_value") or 0)
        holdings = payload.get("holdings", [])
        cash_available = float(payload.get("cash_available") or 0)
        put_positions = payload.get("put_positions", [])
        technical_signals = payload.get("technical_signals", {})
        weekly_income = float(payload.get("weekly_income") or 0)
        monthly_income = float(payload.get("monthly_income") or 0)
        ira_delta = payload.get("ira_delta", 75)
        taxable_delta = payload.get("taxable_delta", 90)

        is_ira = account_type in ("retirement", "ira", "roth_ira")
        delta_target = ira_delta if is_ira else taxable_delta

        lines = [
            f"Account: {account_name}",
            f"Type: {'IRA/Retirement' if is_ira else 'Taxable Brokerage'} (Delta target: {delta_target})",
            f"Total Value: ${account_value:,.0f}",
            f"Cash Available for Puts: ${cash_available:,.0f}",
            f"Last Week Income: ${weekly_income:,.0f} | Last Month: ${monthly_income:,.0f}",
            "",
            "HOLDINGS (covered call candidates):",
        ]

        for h in holdings:
            symbol = h.get("symbol", "")
            options = h.get("options", 0)
            sold = h.get("sold_contracts", 0)
            unsold = h.get("unsold_contracts", 0)
            value = float(h.get("value") or 0)
            weekly = float(h.get("weekly_income") or 0)
            utilization = h.get("utilization_status", "none")

            ta = technical_signals.get(symbol, {})
            rsi_str = f"RSI:{ta.get('rsi'):.0f}" if isinstance(ta.get("rsi"), (int, float)) else ""
            bb_str = f"BB:{ta.get('bb_position_pct'):.0f}%" if isinstance(ta.get("bb_position_pct"), (int, float)) else ""
            trend_str = str(ta.get("trend", "") or "")
            ta_str = " | ".join(filter(None, [rsi_str, bb_str, trend_str]))

            status = "FULLY SOLD" if utilization == "full" else f"PARTIAL ({sold} sold, {unsold} unsold)" if utilization == "partial" else f"NONE SOLD ({options} available)"
            lines.append(f"  {symbol}: {options} contracts | ${value:,.0f} value | ${weekly:,.0f}/wk | Status: {status}" + (f" | TA: {ta_str}" if ta_str else ""))

        if put_positions:
            lines.append("")
            lines.append("OPEN PUT POSITIONS:")
            for p in put_positions:
                exp = p.get("expiration_date") or "?"
                value_locked = float(p.get("value_locked") or 0)
                lines.append(f"  {p.get('symbol')}: {p.get('contracts')}x ${p.get('strike_price')} put | Locked: ${value_locked:,.0f} | Exp: {exp}")
        else:
            lines.append("")
            lines.append("OPEN PUT POSITIONS: None")

        context = "\n".join(lines)

        def _call_claude() -> str:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=os.getenv("AGENT_MODEL", "claude-sonnet-4-6"),
                max_tokens=2048,
                system=_IMPROVEMENT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"Generate improvement ideas for this account:\n\n{context}"}],
            )
            return response.content[0].text if response.content else "[]"

        raw = await asyncio.to_thread(_call_claude)

        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0].strip()

        # Sanitize: escape literal newlines/tabs inside JSON string values
        # (Claude sometimes includes unescaped newlines in multi-sentence strings)
        def _sanitize_json_strings(s: str) -> str:
            result = []
            in_string = False
            i = 0
            while i < len(s):
                c = s[i]
                if in_string:
                    if c == '\\':
                        result.append(c)
                        i += 1
                        if i < len(s):
                            result.append(s[i])
                        i += 1
                        continue
                    elif c == '"':
                        in_string = False
                        result.append(c)
                    elif c == '\n':
                        result.append('\\n')
                    elif c == '\r':
                        result.append('\\r')
                    elif c == '\t':
                        result.append('\\t')
                    else:
                        result.append(c)
                else:
                    if c == '"':
                        in_string = True
                        result.append(c)
                    else:
                        result.append(c)
                i += 1
            return ''.join(result)

        ideas = _json.loads(_sanitize_json_strings(raw))
        return {"ideas": ideas, "account_name": account_name}

    except _json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude ideas response: {e}\nRaw: {raw}")
        return {"ideas": [], "error": "Failed to parse AI response", "account_name": account_name}
    except HTTPException:
        raise
    except Exception as e:
        import traceback as _tb
        logger.error(f"improvement-ideas EXCEPTION:\n{_tb.format_exc()}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ============================================================================
# POSITION COVERAGE ANALYSIS
# Combines equity cost basis, realized G/L, and covered-call income per symbol.
# ============================================================================

@router.get("/position-coverage")
async def get_position_coverage(
    years: str = Query(default="2025,2026", description="Comma-separated list of years"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    For each equity symbol with covered-call activity, compute:
      - Total capital deployed (all accounts)
      - Realized equity gain/loss (taxable accounts exact; retirement estimated)
      - Net call-option income (STO credits minus BTC debits, calls only)
      - Total return and return-on-capital %
      - Entry date, exit date, holding period, position status (open/closed/partial)

    Returns both an aggregate (all-accounts) summary and a per-account breakdown.
    """
    from app.modules.tax.models import StockLot, StockLotSale
    from app.modules.investments.models import InvestmentTransaction
    from sqlalchemy import extract, or_, func
    from collections import defaultdict
    import math

    year_list = [int(y.strip()) for y in years.split(",") if y.strip().isdigit()]
    if not year_list:
        year_list = [2025, 2026]

    TAXABLE = {"neel_brokerage", "jaya_brokerage"}
    RETIREMENT = {"neel_retirement", "jaya_ira", "jaya_roth_ira", "neel_roth_ira", "alisha_brokerage"}

    # ── Step 1: Discover symbols that have CALL activity in any account ────
    year_filters = or_(*[
        extract("year", InvestmentTransaction.transaction_date) == y
        for y in year_list
    ])

    call_txns = db.query(InvestmentTransaction).filter(
        InvestmentTransaction.transaction_type.in_(["STO", "BTC"]),
        year_filters,
    ).all()
    call_txns = [t for t in call_txns if "call" in (t.description or "").lower()]

    symbols_with_calls = sorted(set(t.symbol for t in call_txns if t.symbol))

    if not symbols_with_calls:
        return {"symbols": [], "by_account": [], "years": year_list}

    # ── Step 2: Build call income per (symbol, account) ───────────────────
    call_data: dict = defaultdict(lambda: defaultdict(lambda: {"sto": 0.0, "btc": 0.0, "count": 0}))
    for t in call_txns:
        amt = float(t.amount or 0)
        if t.transaction_type == "STO":
            call_data[t.symbol][t.account_id]["sto"] += amt
            call_data[t.symbol][t.account_id]["count"] += 1
        else:
            call_data[t.symbol][t.account_id]["btc"] += amt

    # ── Step 3: Capital + equity G/L from StockLot / StockLotSale ─────────
    # Taxable: exact data from lot tracker
    lots = db.query(StockLot).filter(StockLot.symbol.in_(symbols_with_calls)).all()
    sales = (
        db.query(StockLotSale)
        .join(StockLot, StockLotSale.lot_id == StockLot.lot_id)
        .filter(StockLot.symbol.in_(symbols_with_calls))
        .all()
    )

    # Build lot maps
    lots_by_sym_acct: dict = defaultdict(list)
    for lot in lots:
        lots_by_sym_acct[(lot.symbol, lot.account_id)].append(lot)

    sales_by_sym_acct: dict = defaultdict(list)
    for sale in sales:
        lot = next((l for l in lots if l.lot_id == sale.lot_id), None)
        if lot:
            sales_by_sym_acct[(lot.symbol, lot.account_id)].append(sale)

    # Retirement: BUY / SELL transactions
    ret_buys = db.query(InvestmentTransaction).filter(
        InvestmentTransaction.symbol.in_(symbols_with_calls),
        InvestmentTransaction.transaction_type == "BUY",
        InvestmentTransaction.account_id.in_(RETIREMENT),
        InvestmentTransaction.amount < 0,
    ).all()

    ret_sells = db.query(InvestmentTransaction).filter(
        InvestmentTransaction.symbol.in_(symbols_with_calls),
        InvestmentTransaction.transaction_type == "SELL",
        InvestmentTransaction.account_id.in_(RETIREMENT),
        InvestmentTransaction.amount > 0,
    ).all()

    ret_buy_by: dict = defaultdict(lambda: {"qty": 0.0, "amt": 0.0, "dates": []})
    for t in ret_buys:
        k = (t.symbol, t.account_id)
        ret_buy_by[k]["qty"] += float(t.quantity or 0)
        ret_buy_by[k]["amt"] += abs(float(t.amount or 0))
        if t.transaction_date:
            d = t.transaction_date if isinstance(t.transaction_date, date) else t.transaction_date.date()
            ret_buy_by[k]["dates"].append(d)

    ret_sell_by: dict = defaultdict(lambda: {"qty": 0.0, "proceeds": 0.0, "dates": []})
    for t in ret_sells:
        k = (t.symbol, t.account_id)
        ret_sell_by[k]["qty"] += float(t.quantity or 0)
        ret_sell_by[k]["proceeds"] += float(t.amount or 0)
        if t.transaction_date:
            d = t.transaction_date if isinstance(t.transaction_date, date) else t.transaction_date.date()
            ret_sell_by[k]["dates"].append(d)

    # ── Step 4: Aggregate per (symbol, account) row ───────────────────────
    all_accounts: set = set()
    for t in call_txns:
        all_accounts.add(t.account_id)
    for lot in lots:
        all_accounts.add(lot.account_id)

    rows: list = []

    for sym in symbols_with_calls:
        for acct in sorted(all_accounts):
            lot_list = lots_by_sym_acct.get((sym, acct), [])
            sale_list = sales_by_sym_acct.get((sym, acct), [])
            c = call_data.get(sym, {}).get(acct, {"sto": 0.0, "btc": 0.0, "count": 0})
            rb = ret_buy_by.get((sym, acct), {"qty": 0.0, "amt": 0.0, "dates": []})
            rs = ret_sell_by.get((sym, acct), {"qty": 0.0, "proceeds": 0.0, "dates": []})

            # Capital
            if lot_list:
                capital = sum(float(l.cost_basis) for l in lot_list)
            elif rb["amt"] > 0:
                capital = rb["amt"]
            else:
                capital = 0.0

            if capital == 0 and c["sto"] == 0:
                continue  # no activity in this symbol/account

            # Equity G/L
            if sale_list:
                equity_gl = sum(float(s.gain_loss) for s in sale_list)
            elif rb["qty"] > 0 and rs["qty"] > 0:
                avg_cost = rb["amt"] / rb["qty"]
                equity_gl = rs["proceeds"] - avg_cost * rs["qty"]
            else:
                equity_gl = 0.0

            # Call income
            call_income = c["sto"] + c["btc"]

            # Entry / exit dates
            entry_dates = []
            if lot_list:
                entry_dates += [l.purchase_date for l in lot_list if l.purchase_date]
            if rb["dates"]:
                entry_dates += rb["dates"]

            exit_dates = []
            if sale_list:
                exit_dates += [s.sale_date for s in sale_list]
            if rs["dates"]:
                exit_dates += rs["dates"]

            entry_date = min(entry_dates).isoformat() if entry_dates else None

            # Status
            open_qty = sum(float(l.quantity_remaining) for l in lot_list) if lot_list else 0.0
            ret_unsold = max(0, rb["qty"] - rs["qty"]) if rb["qty"] > 0 else 0.0
            if lot_list or rb["qty"] > 0:
                if open_qty > 0 or ret_unsold > 0:
                    status = "open" if (open_qty + ret_unsold) >= sum(float(l.quantity) for l in lot_list) + rb["qty"] - 0.01 else "partial"
                    exit_date = None
                else:
                    status = "closed"
                    exit_date = max(exit_dates).isoformat() if exit_dates else None
            else:
                status = "calls_only"
                exit_date = None

            # Holding period
            if entry_date and exit_date:
                days = (date.fromisoformat(exit_date) - date.fromisoformat(entry_date)).days
            elif entry_date:
                days = (date.today() - date.fromisoformat(entry_date)).days
            else:
                days = None

            total_return = equity_gl + call_income
            return_pct = round(total_return / capital * 100, 1) if capital > 0 else None
            annualized_pct = None
            if return_pct is not None and days and days > 0 and capital > 0:
                base = 1 + total_return / capital
                if base > 0:  # guard against complex result from fractional power of negative
                    annualized_pct = round((base ** (365 / days) - 1) * 100, 1)

            shares_total = sum(float(l.quantity) for l in lot_list) + rb["qty"]
            rows.append({
                "symbol": sym,
                "account_id": acct,
                "is_taxable": acct in TAXABLE,
                "capital": round(capital, 2),
                "equity_gl": round(equity_gl, 2),
                "call_income": round(call_income, 2),
                "total_return": round(total_return, 2),
                "return_pct": round(return_pct, 1) if return_pct is not None else None,
                "annualized_pct": annualized_pct,
                "entry_date": entry_date,
                "exit_date": exit_date,
                "status": status,
                "holding_days": days,
                "shares_held": round(open_qty + ret_unsold, 2),
                "shares_total": round(shares_total, 2),
            })

    # ── Step 5: Roll up to symbol-level aggregate ─────────────────────────
    sym_agg: dict = defaultdict(lambda: {
        "capital": 0.0, "equity_gl": 0.0, "call_income": 0.0,
        "entry_dates": [], "exit_dates": [], "statuses": set(),
        "shares_held": 0.0, "shares_total": 0.0,
    })
    for r in rows:
        a = sym_agg[r["symbol"]]
        a["capital"]      += r["capital"]
        a["equity_gl"]    += r["equity_gl"]
        a["call_income"]  += r["call_income"]
        a["shares_held"]  += r.get("shares_held", 0.0)
        a["shares_total"] += r.get("shares_total", 0.0)
        if r["entry_date"]:
            a["entry_dates"].append(r["entry_date"])
        if r["exit_date"]:
            a["exit_dates"].append(r["exit_date"])
        a["statuses"].add(r["status"])

    aggregates = []
    for sym in symbols_with_calls:
        a = sym_agg[sym]
        cap = a["capital"]
        eq  = a["equity_gl"]
        cal = a["call_income"]
        tot = eq + cal
        pct = round(tot / cap * 100, 1) if cap > 0 else None
        entry = min(a["entry_dates"]) if a["entry_dates"] else None
        exit_ = max(a["exit_dates"]) if a["exit_dates"] else None
        statuses = a["statuses"]
        if "open" in statuses and "closed" not in statuses and "partial" not in statuses:
            status = "open"        # all shares still held
        elif "partial" in statuses or ("open" in statuses and "closed" in statuses):
            status = "partial"     # some shares sold, some still held
        else:
            status = "closed"      # all shares fully exited

        days = None
        annualized = None
        if entry:
            ref = date.fromisoformat(exit_) if exit_ and status == "closed" else date.today()
            days = (ref - date.fromisoformat(entry)).days
            if pct is not None and days > 0 and cap > 0:
                base = 1 + tot / cap
                if base > 0:
                    annualized = round((base ** (365 / days) - 1) * 100, 1)

        aggregates.append({
            "symbol": sym,
            "capital": round(cap, 2),
            "equity_gl": round(eq, 2),
            "call_income": round(cal, 2),
            "total_return": round(tot, 2),
            "return_pct": pct,
            "annualized_pct": annualized,
            "entry_date": entry,
            "exit_date": exit_,
            "status": status,
            "holding_days": days,
            "shares_held": round(a["shares_held"], 2),
            "shares_total": round(a["shares_total"], 2),
        })

    aggregates.sort(key=lambda x: -(x["total_return"] or 0))

    return {
        "years": year_list,
        "symbols": aggregates,
        "by_account": rows,
    }



@router.get("/v6/action-queue")
async def get_v6_action_queue(engine: Optional[str] = None, db: Session = Depends(get_db)):
    """The action queue behind the Options Execution page — the LIVE engine
    (settings.LIVE_STRATEGY_ENGINE, V8 since 2026-10-22) in the queue
    contract the page has always consumed. `?engine=v6` returns the V6
    queue for comparison. See docs/OPTIONS-EXECUTION-PAGE-SPEC.md."""
    if (engine or "").lower() == "v6":
        from app.modules.strategies.v6_engine import build_action_queue
        return build_action_queue(db)
    from app.modules.strategies.v7_engine import build_live_action_queue
    return build_live_action_queue(db)


@router.post("/notify/after-sync")
async def post_notify_after_sync(scan_type: Optional[str] = None):
    """Called by scripts/scheduled_refresh.sh the moment a sync finishes
    (success or failure — it reads data/refresh_status.json). With
    scan_type (6am_main / 8am_post_open / 12pm_midday / 8pm_evening) it
    sends that decision-point scan email on the data just synced; without
    it, a short "sync complete" confirmation. Neel, 2026-09-17: "the flow
    is Sync → wait for completion → email." See scheduler.notify_after_sync."""
    from app.core.scheduler import notify_after_sync, SCAN_LABELS
    if scan_type and scan_type not in SCAN_LABELS:
        raise HTTPException(status_code=400, detail=f"unknown scan_type; one of {sorted(SCAN_LABELS)}")
    try:
        return notify_after_sync(scan_type)
    except Exception as e:
        logger.error(f"notify_after_sync failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-as-of")
async def get_data_as_of(db: Session = Depends(get_db)):
    """Cheap freshness probe for the pages to poll: the latest position
    snapshot and cash snapshot. When either advances, the page re-fetches.
    (Neel, 2026-09-17: a stale tab kept showing a card for a call he had
    already sold; the hourly sync lands but the page did not know.)"""
    from sqlalchemy import text as _text
    pos = db.execute(_text("SELECT MAX(snapshot_date) FROM sold_options_snapshots")).scalar()
    cash = db.execute(_text("SELECT MAX(snapshot_date) FROM account_cash_balance_history")).scalar()
    # prices: the newest live quote the bridge wrote (a prices-only sync
    # advances this without touching positions or cash).
    prices = db.execute(_text(
        "SELECT MAX(created_at) FROM symbol_price_history WHERE source = 'robinhood_mcp_live_quote'"
    )).scalar()
    return {"positions": str(pos) if pos else None, "cash": str(cash) if cash else None,
            "prices": str(prices) if prices else None}


@router.get("/sync/status")
async def get_sync_status():
    """What the last Robinhood sync did and whether one is running now —
    data/refresh_status.json as written by scripts/scheduled_refresh.sh,
    plus the lock directory the script holds while it runs."""
    from app.core.config import settings
    from app.core.scheduler import read_refresh_status
    st = read_refresh_status() or {}
    lock = settings.DATA_DIR / "refresh.lock"
    st["running"] = bool(st.get("running")) and lock.exists()
    return st


@router.get("/sync/tracked-symbols")
async def get_tracked_symbols(for_: Optional[str] = Query(None, alias="for"),
                              db: Session = Depends(get_db)):
    """The symbols EVERY sync must quote — the one list, so a name cannot
    be tracked by the engine and invisible to the pull.

    Rebuilt 2026-09-23 after Neel asked why AMZN, CRWD, TSM and MSFT were
    still on 9/18 closes after a 6:40 full sync. Two causes:

    1. The /refresh skill quoted only symbols the synced accounts HOLD or
       have options on, so bucket C names he does not own yet, and names
       just assigned away (MSFT), were never priced. Only `prices` mode
       read this endpoint. Step 3 of the skill now reads it too.
    2. This list itself carried names nothing can ever refresh: FIG and
       HOOD are held only in Alisha's Brokerage, which the skill
       deliberately never syncs, and MGTNW / TQQQ are leftovers of V6's
       `investment_policy.json` inventory (MGTNW has never had a single
       price row). They sat here looking tracked and permanently stale.

    So the list is now: what the SYNCED accounts hold, plus every open
    option's underlying, plus V7's three groups (long-term, short-term,
    put-only) — which is exactly what the engine reasons about. Anything
    dropped is returned in `excluded` rather than silently disappearing.
    """
    import json as _json
    from app.core.config import settings
    from sqlalchemy import text as _text

    # Accounts the /refresh skill actually pulls. Alisha's is excluded by
    # the skill (known share-count discrepancy, unresolved), so symbols
    # only she holds can never be made fresh — see docs/ROBINHOOD_MCP_SYNC.md.
    NEVER_SYNCED = {"Alisha's Brokerage"}
    rows = db.execute(_text("""
        SELECT DISTINCT h.symbol, a.account_name
        FROM investment_holdings h
        JOIN investment_accounts a ON a.account_id = h.account_id AND a.source = h.source
        WHERE a.is_active = 'Y' AND h.quantity > 0 AND h.symbol IS NOT NULL
    """)).fetchall()
    held = {r.symbol for r in rows if r.account_name not in NEVER_SYNCED}
    unsyncable = {r.symbol for r in rows if r.account_name in NEVER_SYNCED} - held

    # underlyings of open short options — always needed for marks
    held |= {r[0] for r in db.execute(_text("""
        SELECT DISTINCT so.symbol FROM sold_options so
        WHERE so.snapshot_id IN (SELECT MAX(id) FROM sold_options_snapshots GROUP BY account_name)
    """)).fetchall() if r[0]}

    wanted, ignore = set(), set()
    try:
        p2 = _json.loads((settings.DATA_DIR / "policy_v2.json").read_text())
        wanted = (set(p2["long_term"]["symbols"]) | set(p2["short_term"]["symbols"])
                  | set(p2.get("put_only", {}).get("symbols", [])))
    except Exception:
        pass
    try:
        ignore = set(_json.loads((settings.DATA_DIR / "investment_policy.json").read_text()).get("ignore") or [])
    except Exception:
        pass

    syms = sorted((held | wanted) - ignore - {"CASH", ""})

    if for_ == "chains":
        # Option chains are expensive to pull (2026-09-24: an all-symbols
        # run spent $63.70 and wrote nothing). Quote only what is actually
        # being decided this week: symbols with an open option position,
        # plus the short-term / put-only names the put ranking chooses
        # between. Everything else keeps using the ATM-IV estimate, which
        # is what it had before chains existed.
        open_opts = {r[0] for r in db.execute(_text("""
            SELECT DISTINCT symbol FROM sold_options
            WHERE snapshot_id IN (SELECT MAX(id) FROM sold_options_snapshots GROUP BY account_name)
        """)).fetchall() if r[0]}
        # Open positions only. Adding the whole put-ranking universe put it
        # back at 20 symbols (~160 MCP calls); a new put's estimate is
        # decent now that implied vol is real, while a roll's strike,
        # premium and SPREAD are where a wrong number costs money.
        pick = sorted(open_opts & set(syms))
        spots = {r[0]: float(r[1]) for r in db.execute(_text("""
            SELECT DISTINCT ON (symbol) symbol, close_price FROM symbol_price_history
            WHERE symbol = ANY(:s) ORDER BY symbol, price_date DESC
        """), {"s": pick}).fetchall()}
        return {"symbols": pick, "spots": spots, "count": len(pick),
                "why": "symbols with an open option position — where a wrong strike, premium or spread costs money"}

    return {"symbols": syms,
            "held": sorted(held - ignore),
            "wanted": sorted(wanted - held - ignore),
            "excluded": {"only_in_unsynced_accounts": sorted(unsyncable - wanted),
                         "ignored": sorted(ignore)}}


@router.get("/chains")
async def get_option_chains_stored(symbol: Optional[str] = None, expiration: Optional[str] = None,
                                   db: Session = Depends(get_db)):
    """The stored option chain (level 3 of the sync). No symbol: a coverage
    summary — what is on file, how many contracts and how old. With a
    symbol: the contracts themselves, optionally one expiry."""
    if not symbol:
        rows = db.execute(text("""
            SELECT symbol, COUNT(*) n, COUNT(DISTINCT expiration_date) exps,
                   MIN(expiration_date) first_exp, MAX(expiration_date) last_exp, MAX(as_of) as_of
            FROM option_chain_quotes GROUP BY symbol ORDER BY symbol
        """)).fetchall()
        return {"symbols": [{"symbol": r.symbol, "contracts": r.n, "expiries": r.exps,
                             "first_expiry": str(r.first_exp), "last_expiry": str(r.last_exp),
                             "as_of": str(r.as_of)} for r in rows],
                "total_contracts": sum(r.n for r in rows)}
    q = """SELECT * FROM option_chain_quotes WHERE symbol = :s"""
    params: Dict[str, Any] = {"s": symbol.upper()}
    if expiration:
        q += " AND expiration_date = :e"
        params["e"] = expiration
    q += " ORDER BY expiration_date, option_type, strike_price"
    rows = db.execute(text(q), params).fetchall()
    def f(v):
        return float(v) if v is not None else None
    return {"symbol": symbol.upper(), "count": len(rows),
            "contracts": [{"expiration": str(r.expiration_date), "strike": f(r.strike_price),
                           "type": r.option_type, "bid": f(r.bid), "ask": f(r.ask), "mark": f(r.mark),
                           "delta": f(r.delta), "implied_vol": f(r.implied_vol),
                           "open_interest": r.open_interest, "volume": r.volume,
                           "underlying_price": f(r.underlying_price), "as_of": str(r.as_of)}
                          for r in rows]}


@router.post("/sync", status_code=202)
async def start_sync(mode: str = Query("full", pattern="^(full|state|prices|chains)$")):
    """Pull from Robinhood now — the page's Sync button (Neel, 2026-09-18:
    "enhance the role of the refresh button to pull from Robinhood").

    The pull can only run inside a Claude Code session (the Robinhood MCP
    servers are OAuth'd to Claude Code, not to this backend), so this
    spawns scripts/scheduled_refresh.sh detached, exactly as launchd does
    every hour. The script takes a lock, records progress in
    data/refresh_status.json, syncs, and then POSTs /notify/after-sync —
    which emails only the four decision-point scans and any FAILED run;
    a successful manual run is silent (Neel, 2026-09-18). Poll
    /sync/status; when `running` clears, re-fetch the queue. Returns 409
    if a sync is already in flight.
    """
    import subprocess
    from app.core.config import settings
    script = settings.DATA_DIR.parent / "scripts" / "scheduled_refresh.sh"
    if (settings.DATA_DIR / "refresh.lock").exists():
        raise HTTPException(status_code=409, detail="A sync is already running")
    if not script.exists():
        raise HTTPException(status_code=500, detail=f"{script} not found")
    env = dict(os.environ, REFRESH_TRIGGER="manual", REFRESH_MODE=mode)
    subprocess.Popen(["/bin/zsh", str(script)], cwd=str(settings.DATA_DIR.parent),
                     env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    return {"started": True, "mode": mode,
            "detail": {"state": "Account sync started; about 5 minutes.",
                       "prices": "Price sync started; about a minute.",
                       "chains": "Option-chain sync started; about 10 minutes.",
                       "full": "Full sync started; about 5 minutes."}[mode]
            + " The page updates when it lands."}


@router.get("/v8/preview")
async def get_v8_preview(db: Session = Depends(get_db)):
    """V8 action queue — PREVIEW, beside live V7 (Neel, 2026-10-04: "put
    these new ones in V8 and run it in parallel so I can give you feedback
    before moving to V8"). Same engine; V8 reads policy_v8.json layered
    over policy_v2.json, so the two differ only in knobs and lists."""
    from app.modules.strategies.v7_engine import build_v7_queue
    return build_v7_queue(db, "v8")


@router.get("/v8/diff")
async def get_v8_diff(db: Session = Depends(get_db)):
    """What V8 would do differently from live V7, card by card — the whole
    point of running them side by side."""
    from app.modules.strategies.v7_engine import build_action_queue, load_policy_v2
    v7 = build_action_queue(db, "v7")
    v8 = build_action_queue(db, "v8")
    def key(i):
        return (i["account"], i["symbol"], i["action"], i["detail"][:40])
    a = {key(i): i for i in v7["items"]}
    b = {key(i): i for i in v8["items"]}
    only7 = [a[k] for k in a if k not in b]
    only8 = [b[k] for k in b if k not in a]
    pol8 = load_policy_v2("v8")
    return {
        "differences": pol8.get("differences_from_v7", []),
        "v7_summary": v7["summary"], "v8_summary": v8["summary"],
        "only_in_v7": [{"account": i["account"], "symbol": i["symbol"], "action": i["action"],
                        "priority": i["priority"], "detail": i["detail"]} for i in only7],
        "only_in_v8": [{"account": i["account"], "symbol": i["symbol"], "action": i["action"],
                        "priority": i["priority"], "detail": i["detail"]} for i in only8],
    }


@router.get("/v7/preview")
async def get_v7_preview(db: Session = Depends(get_db)):
    """V7 action queue — PREVIEW ONLY. Two books, four layers, built from
    data/policy_v2.json. Runs beside V6, which stays the live notification
    engine until the switch is flipped. See v7_engine.py and
    docs/INVESTMENT-THESIS-V2-DRAFT.md."""
    from app.modules.strategies.v7_engine import build_v7_queue
    return build_v7_queue(db)


@router.get("/v7/knobs")
async def get_v7_knobs():
    """Every tunable the V7 engine uses — data/policy_v2.json "knobs"."""
    from app.modules.strategies.v7_engine import load_policy_v2
    pol = load_policy_v2()
    return {"knobs": {k: v for k, v in pol["knobs"].items() if not k.startswith("_")},
            "note": pol["knobs"].get("_note", "")}


@router.put("/v7/knobs")
async def put_v7_knobs(payload: dict):
    """Update knob values. Body: {"values": {key: number, ...}}. Validated
    against each knob's min/max; written back to data/policy_v2.json so the
    next engine run (and git) sees it."""
    from pathlib import Path as _Path
    import json as _json
    from app.modules.strategies.v7_engine import _POLICY_V2
    pol = _json.loads(_POLICY_V2.read_text())
    knobs = pol["knobs"]
    values = (payload or {}).get("values", {})
    changed = {}
    for key, raw in values.items():
        if key not in knobs or key.startswith("_"):
            raise HTTPException(400, f"unknown knob {key}")
        try:
            v = float(raw)
        except (TypeError, ValueError):
            raise HTTPException(400, f"{key}: not a number")
        k = knobs[key]
        if "min" in k and v < k["min"] or "max" in k and v > k["max"]:
            raise HTTPException(400, f"{key}: {v} outside [{k.get('min')}, {k.get('max')}]")
        if isinstance(k["value"], int) and float(v).is_integer():
            v = int(v)
        if v != k["value"]:
            changed[key] = {"from": k["value"], "to": v}
            k["value"] = v
    if changed:
        _POLICY_V2.write_text(_json.dumps(pol, indent=2, ensure_ascii=False) + "\n")
    return {"changed": changed, "knobs": {k: v for k, v in knobs.items() if not k.startswith("_")}}


@router.get("/v6/assignment-loss")
async def get_v6_assignment_loss(db: Session = Depends(get_db)):
    """Forced-assignment loss: strike vs. market price AT THE MOMENT OF
    ASSIGNMENT (not vs. today's price). Neel, 2026-07-22 — see
    assignment_loss_service.py for the reasoning."""
    from app.modules.strategies.assignment_loss_service import get_assignment_loss
    return get_assignment_loss(db)


@router.get("/v6/put-campaigns")
async def get_v6_put_campaigns(db: Session = Depends(get_db)):
    """Put campaigns per stock: every assigned put's shares valued today
    (or at their sale price) plus the premium collected on the way —
    Neel, 2026-10-22. See get_put_campaigns in assignment_loss_service.py."""
    from app.modules.strategies.assignment_loss_service import get_put_campaigns
    return get_put_campaigns(db)


@router.get("/v6/call-campaigns")
async def get_v6_call_campaigns(db: Session = Depends(get_db)):
    """Call Campaigns per stock: net call premium minus the upside given up
    on the day of each call assignment, on bought shares only (put-assigned
    shares are the Put Campaign's). Was /v6/covered-call-income (Neel,
    2026-10-23); renamed 2026-10-24. See covered_call_service.py."""
    from app.modules.strategies.covered_call_service import get_call_campaigns
    return get_call_campaigns(db)


@router.post("/v6/assignments/confirm")
async def post_confirm_assignments(ids: Optional[List[int]] = None, db: Session = Depends(get_db)):
    """Record Neel's reply to the "Confirm N assignments?" email. Promotes
    the listed pending_confirmation OASGN rows (all pending rows when no
    ids are given) to confirmed. GET /v6/assignments/pending lists them."""
    from app.modules.strategies.assignment_detection_service import confirm_pending_assignments
    return confirm_pending_assignments(db, ids)


@router.get("/v6/assignments/pending")
async def get_pending_assignments(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT t.id, a.account_name, t.symbol, t.description, t.quantity, t.transaction_date
        FROM investment_transactions t JOIN investment_accounts a ON a.account_id = t.account_id
        WHERE t.transaction_type = 'OASGN' AND t.source = 'robinhood_mcp_inferred_pending_confirmation'
        ORDER BY t.transaction_date, a.account_name, t.symbol
    """)).fetchall()
    return [{"id": r.id, "account": r.account_name, "symbol": r.symbol, "description": r.description,
             "contracts": float(r.quantity), "date": str(r.transaction_date)} for r in rows]


@router.post("/v6/detect-assignments")
async def post_v6_detect_assignments(db: Session = Depends(get_db)):
    """MCP-only assignment detection (no CSV) — run as part of every
    refresh. See assignment_detection_service.py for the two-signal
    design and the email-on-unconfirmed flow. Idempotent."""
    from app.modules.strategies.assignment_detection_service import detect_and_record_assignments
    return detect_and_record_assignments(db)
