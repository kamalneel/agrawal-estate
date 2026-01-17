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
    Spending: Tracked from brokerage withdrawals (ACH, Credit Card, Transfers)
    """
    import csv
    import re
    from pathlib import Path
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
    
    # Get options income by month from database
    options_monthly = income_db.get_options_income_monthly(db, year=year)
    
    # Get dividend income by month from database
    dividends_monthly = income_db.get_dividend_income_monthly(db, year=year)
    
    # Get interest income by month from database
    interest_monthly = income_db.get_interest_income_monthly(db, year=year)
    
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
    # Filter by year to get only rental income for the requested year
    rental_monthly: Dict[int, float] = {}
    try:
        rental_service = get_rental_service()
        rental_summary = rental_service.get_rental_summary()
        # Sum net_income only for properties in the requested year
        annual_rental = 0.0
        for prop in rental_summary.get('properties', []):
            if prop.get('year') == year:
                annual_rental += prop.get('net_income', 0)
        
        if annual_rental > 0:
            monthly_rental = annual_rental / 12
            for m in range(1, 13):
                rental_monthly[m] = monthly_rental
    except Exception as e:
        print(f"Error loading rental: {e}")
    
    # =========================================================================
    # SPENDING: Get from brokerage transactions CSV
    # =========================================================================
    
    monthly_spending: Dict[int, float] = {}
    
    # Try to find the best CSV file for spending data
    robinhood_dir = Path(__file__).parent.parent.parent.parent.parent / "data" / "processed" / "investments" / "robinhood"
    
    # First try year-specific file, then try multi-year all-data file
    csv_path = robinhood_dir / f"Neel Individual {year} complete.csv"
    if not csv_path.exists():
        csv_path = robinhood_dir / "Neel Individual 2021-2025 all data.csv"
    
    if csv_path.exists():
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                activity_date = row.get('Activity Date', '')
                description = row.get('Description', '')
                trans_code = row.get('Trans Code', '')
                amount_str = row.get('Amount', '')
                
                if not activity_date or not amount_str:
                    continue
                
                date_match = re.match(r'(\d+)/(\d+)/(\d+)', activity_date)
                if not date_match:
                    continue
                    
                month_num = int(date_match.group(1))
                year_num = int(date_match.group(3))
                
                if year_num != year:
                    continue
                
                amount_clean = amount_str.replace('$', '').replace(',', '').replace('(', '').replace(')', '')
                try:
                    amount = abs(float(amount_clean))
                except ValueError:
                    continue
                
                is_spending = False
                if trans_code == 'ACH' and 'Withdrawal' in description:
                    is_spending = True
                elif trans_code == 'XENT_CC' and 'Credit Card balance payment' in description:
                    is_spending = True
                elif trans_code == 'XENT' and 'Brokerage to Spending' in description:
                    is_spending = True
                
                if is_spending:
                    monthly_spending[month_num] = monthly_spending.get(month_num, 0) + amount
    
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
    
    for month in range(1, 13):
        month_key = f"{year}-{month:02d}"
        
        spending = monthly_spending.get(month, 0.0)
        options_income = options_monthly.get(month_key, 0.0)
        dividend_income = dividends_monthly.get(month_key, 0.0)
        interest_income = interest_monthly.get(month_key, 0.0)
        salary_income = salary_monthly.get(month, 0.0)
        rental_income = rental_monthly.get(month, 0.0)
        
        # Track totals
        total_options += options_income
        total_dividends += dividend_income
        total_interest += interest_income
        total_salary += salary_income
        total_rental += rental_income
        
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
            dividend_income=round(dividend_income, 2),  # Separate dividend income
            interest_income=round(interest_income, 2),  # Separate interest income
            rental_income=round(rental_income, 2),  # Separate rental income
            salary_income=round(salary_income, 2),  # Salary only (not including rental)
            net_cash_flow=round(net_cash_flow, 2),
            cumulative_net=round(cumulative_net, 2),
            cumulative_spending=round(cumulative_spending, 2),
            cumulative_income=round(cumulative_income, 2)
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
        projected_annual_deficit=round(projected_annual_deficit, 2)
    )


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
    symbols = {}
    
    # Build holdings data (same as original endpoint)
    for row in result:
        account_id, account_name, account_type, symbol, qty, price, value, description = row
        qty = float(qty) if qty else 0
        price = float(price) if price else 0
        value = float(value) if value else 0
        
        if qty < 100:
            continue
            
        options_count = int(qty // 100)
        
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
                "accounts": []
            }
        
        symbols[symbol]["shares"] += qty
        symbols[symbol]["value"] += value
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
    
    # Calculate totals for symbols
    for sym in symbols:
        symbols[sym]["options"] = int(symbols[sym]["shares"] // 100)
        symbol_premium = symbols[sym]["premium_per_contract"]
        symbols[sym]["weekly_income"] = symbols[sym]["options"] * symbol_premium
        symbols[sym]["monthly_income"] = symbols[sym]["weekly_income"] * 4
        symbols[sym]["yearly_income"] = symbols[sym]["weekly_income"] * weeks_per_year
        symbols[sym]["value"] = round(symbols[sym]["value"], 0)
        symbols[sym]["shares"] = int(symbols[sym]["shares"])
        symbols[sym]["account_count"] = len(symbols[sym]["accounts"])
    
    symbols_list = sorted(symbols.values(), key=lambda x: x["options"], reverse=True)
    
    # Calculate totals for each account
    for account_name in accounts:
        account = accounts[account_name]
        account["total_options"] = sum(h["options"] for h in account["holdings"])
        account["weekly_income"] = sum(h["weekly_income"] for h in account["holdings"])
        account["monthly_income"] = account["weekly_income"] * 4
        account["yearly_income"] = account["weekly_income"] * weeks_per_year
        account["total_value"] = round(account["total_value"], 0)
    
    # Portfolio totals
    total_options = sum(a["total_options"] for a in accounts.values())
    total_weekly = sum(a["weekly_income"] for a in accounts.values())
    total_monthly = total_weekly * 4
    total_yearly = total_weekly * weeks_per_year
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
    
    return {
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
            "yearly_yield_percent": round(yearly_yield, 2)
        },
        "sold_options_snapshot": sold_data.get("snapshot"),
        "symbols": symbols_list,
        "accounts": [accounts[name] for name in account_order if accounts[name]["total_options"] > 0]
    }


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
    
    # Parse expiration date
    try:
        exp_date = datetime.strptime(position.expiration_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    # Create or get a snapshot for manual entries
    snapshot = db.query(SoldOptionsSnapshot).filter(
        SoldOptionsSnapshot.source == 'manual',
        SoldOptionsSnapshot.account_name == position.account_name,
        SoldOptionsSnapshot.parsing_status == 'success'
    ).order_by(SoldOptionsSnapshot.snapshot_date.desc()).first()
    
    if not snapshot:
        snapshot = SoldOptionsSnapshot(
            source='manual',
            account_name=position.account_name,
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


@router.get("/premium-settings")
async def get_premium_settings(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Get current premium settings for all symbols."""
    from app.modules.strategies.models import OptionPremiumSetting
    
    settings = db.query(OptionPremiumSetting).all()
    
    result = {}
    for setting in settings:
        result[setting.symbol] = {
            "premium_per_contract": float(setting.premium_per_contract),
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


@router.post("/recommendations/check-now")
async def trigger_recommendation_check(
    send_notifications: bool = Query(default=True, description="Send notifications if recommendations found"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Manually trigger a recommendation check (for testing scheduler logic)."""
    from app.core.scheduler import trigger_manual_check
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        trigger_manual_check(send_notifications=send_notifications)
        return {
            "success": True,
            "message": "Recommendation check triggered",
            "notifications_sent": send_notifications
        }
    except Exception as e:
        logger.error(f"Error triggering recommendation check: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


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


# ============================================================================
# NOTIFICATION HISTORY ENDPOINTS
# ============================================================================

@router.get("/notifications/history")
async def get_notification_history(
    status: Optional[str] = Query(None, description="Filter by status: new, acknowledged, acted, dismissed"),
    strategy_type: Optional[str] = Query(None, description="Filter by strategy type"),
    priority: Optional[str] = Query(None, description="Filter by priority: urgent, high, medium, low"),
    symbol: Optional[str] = Query(None, description="Filter by stock symbol"),
    notification_mode: Optional[str] = Query(None, description="Filter by notification mode: verbose, smart, or all (default: all)"),
    days_back: int = Query(30, description="Number of days to look back"),
    limit: int = Query(100, description="Maximum number of records to return"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get historical notifications/recommendations with optional filters.
    Returns records sorted by created_at (most recent first).
    
    notification_mode:
    - 'verbose': Shows ALL snapshots (every evaluation)
    - 'smart': Shows only new/changed recommendations
    - None/'all': Shows everything (default)
    """
    from app.modules.strategies.recommendations import get_recommendation_history
    
    records = get_recommendation_history(
        db=db,
        status=status,
        strategy_type=strategy_type,
        priority=priority,
        symbol=symbol,
        notification_mode=notification_mode,
        days_back=days_back,
        limit=limit
    )
    
    # Convert to dict format
    history = []
    
    for rec in records:
        # Extract account_name from context_snapshot if not set in record
        account_name = rec.account_name
        if not account_name and rec.context_snapshot:
            context = rec.context_snapshot if isinstance(rec.context_snapshot, dict) else {}
            account_name = context.get("account_name") or context.get("account")
        
        # Extract symbol from context_snapshot if not set in record
        symbol = rec.symbol
        if not symbol and rec.context_snapshot:
            context = rec.context_snapshot if isinstance(rec.context_snapshot, dict) else {}
            symbol = context.get("symbol")
        
        history.append({
            "id": rec.id,
            "recommendation_id": rec.recommendation_id,
            "type": rec.recommendation_type,
            "category": rec.category,
            "priority": rec.priority,
            "title": rec.title,
            "description": rec.description,
            "rationale": rec.rationale,
            "action": rec.action,
            "action_type": rec.action_type,
            "potential_income": float(rec.potential_income) if rec.potential_income else None,
            "potential_risk": rec.potential_risk,
            "symbol": symbol,
            "account_name": account_name,
            "status": rec.status,
            "context": rec.context_snapshot,
            "created_at": _format_dt_as_utc(rec.created_at),
            "expires_at": _format_dt_as_utc(rec.expires_at),
            "acknowledged_at": _format_dt_as_utc(rec.acknowledged_at),
            "acted_at": _format_dt_as_utc(rec.acted_at),
            "dismissed_at": _format_dt_as_utc(rec.dismissed_at),
            "notification_sent": rec.notification_sent,
            "notification_sent_at": _format_dt_as_utc(rec.notification_sent_at),
            "notification_mode": getattr(rec, 'notification_mode', None),
        })
    
    return {
        "history": history,
        "count": len(history),
        "filters": {
            "status": status,
            "strategy_type": strategy_type,
            "priority": priority,
            "symbol": symbol,
            "notification_mode": notification_mode,
            "days_back": days_back
        }
    }


@router.get("/notifications/v2/current")
async def get_v2_current_notifications(
    mode: str = Query("all", description="Filter mode: verbose, smart, or all"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get current V2 notifications - same data as Telegram receives.
    
    This returns all active V2 recommendations with their latest snapshots,
    formatted identically to what the Telegram bot sends.
    
    mode:
    - 'verbose': All active recommendations (every snapshot)
    - 'smart': Only new/changed recommendations  
    - 'all': Everything (same as verbose)
    """
    from app.modules.strategies.v2_notification_service import get_v2_notification_service
    
    v2_service = get_v2_notification_service(db)
    
    # Get notifications using the same logic as Telegram
    notifications = v2_service.get_all_notifications_to_send(
        mode='both' if mode == 'all' else mode,
        include_sell_opportunities=True
    )
    
    # Combine verbose and smart, removing duplicates
    all_notifs = []
    seen_ids = set()
    
    for notif in notifications.get('verbose', []):
        if notif['id'] not in seen_ids:
            notif['notification_mode'] = 'verbose'
            all_notifs.append(notif)
            seen_ids.add(notif['id'])
    
    # For smart mode filter, only show smart notifications
    if mode == 'smart':
        smart_ids = {n['id'] for n in notifications.get('smart', [])}
        all_notifs = [n for n in all_notifs if n['id'] in smart_ids]
        for notif in all_notifs:
            notif['notification_mode'] = 'smart'
    
    # Format timestamps
    for notif in all_notifs:
        if notif.get('created_at'):
            # Already in ISO format from service
            pass
        if notif.get('evaluated_at'):
            pass
    
    return {
        "history": all_notifs,
        "count": len(all_notifs),
        "mode": mode,
        "v2_enabled": True,
        "source": "v2_snapshots",
        "verbose_count": len(notifications.get('verbose', [])),
        "smart_count": len(notifications.get('smart', [])),
    }


@router.get("/notifications/v2/history")
async def get_v2_notification_history(
    mode: str = Query("all", description="Filter mode: verbose, smart, or all"),
    status: Optional[str] = Query(None, description="Filter by rec status: active, resolved"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    days_back: int = Query(30, description="Number of days to look back"),
    limit: int = Query(100, description="Maximum records"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get V2 notification history with snapshot information.
    
    This returns notifications based on the V2 recommendation/snapshot model,
    including snapshot numbers and change tracking.
    
    mode:
    - 'verbose': All snapshots that were notified in verbose mode
    - 'smart': Only snapshots notified in smart mode  
    - 'all': Everything
    """
    from app.modules.strategies.recommendation_models import (
        PositionRecommendation,
        RecommendationSnapshot
    )
    from datetime import timedelta
    
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    
    # Build query
    query = db.query(RecommendationSnapshot).join(
        PositionRecommendation
    ).filter(
        RecommendationSnapshot.evaluated_at >= cutoff
    )
    
    # Filter by mode - interpret like notification display modes, not database flags
    # 'verbose' = show ALL snapshots (every evaluation, like verbose mode shows everything)
    # 'smart' = only snapshots where something changed (like smart mode only shows changes)  
    # 'all' = same as verbose
    if mode == 'smart':
        # Smart mode: only show snapshots where action, target, or priority changed
        from sqlalchemy import or_
        query = query.filter(
            or_(
                RecommendationSnapshot.action_changed == True,
                RecommendationSnapshot.target_changed == True,
                RecommendationSnapshot.priority_changed == True,
                RecommendationSnapshot.snapshot_number == 1  # First snapshot is always "new"
            )
        )
    # 'verbose' and 'all' show everything - no additional filter
    
    # Filter by status
    if status:
        query = query.filter(PositionRecommendation.status == status)
    
    # Filter by symbol
    if symbol:
        query = query.filter(PositionRecommendation.symbol.ilike(f"%{symbol}%"))
    
    # Order and limit
    snapshots = query.order_by(
        RecommendationSnapshot.evaluated_at.desc()
    ).limit(limit).all()
    
    # Use v2_notification_service for consistent formatting
    from app.modules.strategies.v2_notification_service import get_v2_notification_service
    v2_service = get_v2_notification_service(db)
    
    # Format results using the same logic as /current endpoint
    history = []
    for snap in snapshots:
        rec = snap.recommendation
        
        # Use the notification service to build the item - ensures consistent formatting
        notif_item = v2_service._build_notification_item(rec, snap)
        
        # Add history-specific fields and ensure timestamps are formatted correctly
        notif_item.update({
            # History-specific identity fields
            "id": f"v2_{rec.recommendation_id}_snap{snap.snapshot_number}",
            "recommendation_id": rec.recommendation_id,
            "v2_recommendation_id": rec.id,
            "snapshot_id": snap.id,
            
            # Override timestamps with proper UTC formatting
            "evaluated_at": _format_dt_as_utc(snap.evaluated_at),
            "notification_sent_at": _format_dt_as_utc(snap.notification_sent_at),
            "created_at": _format_dt_as_utc(snap.created_at),
            
            # Status fields  
            "status": rec.status,
            "recommendation_status": rec.status,
            "notification_mode": snap.notification_mode,
            "verbose_notification_sent": snap.verbose_notification_sent,
            "smart_notification_sent": snap.smart_notification_sent,
        })
        
        history.append(notif_item)
    
    return {
        "history": history,
        "count": len(history),
        "mode": mode,
        "v2_enabled": True,
    }


@router.put("/notifications/{record_id}/status")
async def update_notification_status(
    record_id: int,
    status: str = Query(..., description="New status: acknowledged, acted, dismissed"),
    action_taken: Optional[str] = Query(None, description="Description of action taken (for 'acted' status)"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Update the status of a notification/recommendation.
    
    Status values:
    - acknowledged: User has seen the notification
    - acted: User took the recommended action
    - dismissed: User chose not to act on the recommendation
    """
    from app.modules.strategies.recommendations import update_recommendation_status
    
    valid_statuses = ['acknowledged', 'acted', 'dismissed', 'expired']
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    record = update_recommendation_status(
        db=db,
        record_id=record_id,
        new_status=status,
        action_taken=action_taken
    )
    
    if not record:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return {
        "success": True,
        "notification": {
            "id": record.id,
            "status": record.status,
            "acknowledged_at": record.acknowledged_at.isoformat() if record.acknowledged_at else None,
            "acted_at": record.acted_at.isoformat() if record.acted_at else None,
            "dismissed_at": record.dismissed_at.isoformat() if record.dismissed_at else None,
            "action_taken": record.action_taken
        }
    }


@router.get("/notifications/stats")
async def get_notification_stats(
    days_back: int = Query(30, description="Number of days to analyze"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get statistics about notifications/recommendations.
    """
    from app.modules.strategies.models import StrategyRecommendationRecord
    from sqlalchemy import func
    from datetime import timedelta
    
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    
    # Total count
    total = db.query(func.count(StrategyRecommendationRecord.id)).filter(
        StrategyRecommendationRecord.created_at > cutoff
    ).scalar()
    
    # By status
    status_counts = db.query(
        StrategyRecommendationRecord.status,
        func.count(StrategyRecommendationRecord.id)
    ).filter(
        StrategyRecommendationRecord.created_at > cutoff
    ).group_by(StrategyRecommendationRecord.status).all()
    
    # By priority
    priority_counts = db.query(
        StrategyRecommendationRecord.priority,
        func.count(StrategyRecommendationRecord.id)
    ).filter(
        StrategyRecommendationRecord.created_at > cutoff
    ).group_by(StrategyRecommendationRecord.priority).all()
    
    # By strategy type
    type_counts = db.query(
        StrategyRecommendationRecord.recommendation_type,
        func.count(StrategyRecommendationRecord.id)
    ).filter(
        StrategyRecommendationRecord.created_at > cutoff
    ).group_by(StrategyRecommendationRecord.recommendation_type).all()
    
    return {
        "days_back": days_back,
        "total": total,
        "by_status": {s: c for s, c in status_counts},
        "by_priority": {p: c for p, c in priority_counts},
        "by_strategy": {t: c for t, c in type_counts}
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
# FEEDBACK ENDPOINTS (V4 Learning)
# ============================================================================

@router.post("/notifications/{recommendation_id}/feedback")
async def submit_feedback(
    recommendation_id: str,
    feedback: str = Query(..., description="Natural language feedback from user"),
    source: str = Query("web", description="Source: web, telegram, api"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Submit feedback on a recommendation for V4 learning.
    
    Accepts natural language feedback like:
    - "premium is too small, only $8"
    - "I don't want to cap NVDA upside right now"
    - "8 weeks is too long to lock up capital"
    
    The feedback is parsed by AI to extract structured insights.
    """
    from app.modules.strategies.feedback_service import (
        parse_feedback_with_ai,
        save_feedback,
        get_recommendation_by_id
    )
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Ensure feedback table exists (auto-create if not)
        _ensure_feedback_table_exists(db)
        
        # Get recommendation context
        recommendation_context = get_recommendation_by_id(db, recommendation_id)
        
        if not recommendation_context:
            # Still save feedback even if we can't find the recommendation
            logger.warning(f"Recommendation {recommendation_id} not found, saving feedback anyway")
            recommendation_context = {"id": recommendation_id}
        
        # Parse feedback with AI (gracefully handle failures)
        parsed = None
        try:
            parsed = await parse_feedback_with_ai(recommendation_context, feedback)
        except Exception as e:
            logger.warning(f"AI parsing failed (will save raw feedback): {e}")
            # Use fallback parsing
            from app.modules.strategies.feedback_service import _fallback_parse
            parsed = _fallback_parse(feedback)
        
        # Save to database
        feedback_record = save_feedback(
            db=db,
            recommendation_id=recommendation_id,
            raw_feedback=feedback,
            source=source,
            parsed_feedback=parsed,
            recommendation_context=recommendation_context
        )
        
        return {
            "success": True,
            "feedback_id": feedback_record.id,
            "recommendation_id": recommendation_id,
            "parsed": {
                "reason_code": feedback_record.reason_code,
                "reason_detail": feedback_record.reason_detail,
                "threshold_hint": float(feedback_record.threshold_hint) if feedback_record.threshold_hint else None,
                "actionable_insight": feedback_record.actionable_insight,
            } if parsed else None,
            "message": "Feedback recorded. Thank you for helping improve the algorithm!"
        }
        
    except Exception as e:
        logger.error(f"Error saving feedback: {e}", exc_info=True)
        # Return error but don't crash
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save feedback: {str(e)}. Please try again or contact support."
        )


def _ensure_feedback_table_exists(db: Session):
    """
    Ensure the recommendation_feedback table exists.
    Creates it if not present (for dev convenience).
    """
    from sqlalchemy import inspect
    from app.modules.strategies.models import RecommendationFeedback
    from app.core.database import engine
    
    inspector = inspect(engine)
    if 'recommendation_feedback' not in inspector.get_table_names():
        # Create the table
        RecommendationFeedback.__table__.create(engine, checkfirst=True)
        import logging
        logging.getLogger(__name__).info("Created recommendation_feedback table")


@router.get("/feedback/insights")
async def get_feedback_insights_endpoint(
    days_back: int = Query(30, description="Days of feedback to analyze"),
    min_occurrences: int = Query(3, description="Minimum occurrences to report a pattern"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get insights from collected feedback for V4 algorithm improvements.
    
    Analyzes patterns in user feedback and suggests algorithm adjustments.
    """
    from app.modules.strategies.feedback_service import get_feedback_insights
    
    insights = get_feedback_insights(
        db=db,
        days_back=days_back,
        min_occurrences=min_occurrences
    )
    
    return insights


@router.get("/feedback/history")
async def get_feedback_history(
    days_back: int = Query(30, description="Days of feedback to retrieve"),
    reason_code: Optional[str] = Query(None, description="Filter by reason code"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    limit: int = Query(100, description="Maximum records to return"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get history of user feedback on recommendations.
    """
    from app.modules.strategies.models import RecommendationFeedback
    from datetime import timedelta
    
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    
    query = db.query(RecommendationFeedback).filter(
        RecommendationFeedback.created_at >= cutoff
    )
    
    if reason_code:
        query = query.filter(RecommendationFeedback.reason_code == reason_code)
    if symbol:
        query = query.filter(RecommendationFeedback.symbol == symbol.upper())
    
    records = query.order_by(RecommendationFeedback.created_at.desc()).limit(limit).all()
    
    return {
        "feedback": [
            {
                "id": r.id,
                "recommendation_id": r.recommendation_id,
                "source": r.source,
                "raw_feedback": r.raw_feedback,
                "reason_code": r.reason_code,
                "reason_detail": r.reason_detail,
                "threshold_hint": float(r.threshold_hint) if r.threshold_hint else None,
                "symbol": r.symbol,
                "account_name": r.account_name,
                "sentiment": r.sentiment,
                "actionable_insight": r.actionable_insight,
                "created_at": _format_dt_as_utc(r.created_at),
            }
            for r in records
        ],
        "count": len(records),
        "filters": {
            "days_back": days_back,
            "reason_code": reason_code,
            "symbol": symbol
        }
    }


# ============================================================================
# TELEGRAM WEBHOOK ENDPOINTS (for reply-based feedback)
# ============================================================================

@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Webhook endpoint for Telegram to send message updates.
    
    When a user replies to a recommendation notification, Telegram sends
    the reply here, and we process it as feedback.
    
    Setup (one-time):
    1. Set TELEGRAM_WEBHOOK_SECRET in your environment
    2. Call POST /telegram/setup-webhook with your public HTTPS URL
    
    Security:
    - Verifies X-Telegram-Bot-Api-Secret-Token header
    """
    import os
    from app.shared.services.telegram_webhook import (
        verify_telegram_webhook,
        extract_reply_info,
        process_telegram_reply,
        send_telegram_acknowledgment
    )
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Verify the request is from Telegram
    secret = os.getenv('TELEGRAM_WEBHOOK_SECRET', '')
    provided_token = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    
    if not verify_telegram_webhook(secret, provided_token):
        logger.warning("Invalid Telegram webhook secret")
        return {"ok": False, "error": "Invalid secret token"}
    
    try:
        # Parse the update from Telegram
        update = await request.json()
        logger.info(f"Received Telegram update: {update.get('update_id', 'unknown')}")
        
        # Extract reply information
        reply_info = extract_reply_info(update)
        
        if not reply_info:
            # Not a reply or not relevant - just acknowledge
            return {"ok": True, "message": "Update received (not a reply)"}
        
        logger.info(f"Processing reply to message {reply_info.get('original_message_id')}")
        
        # Process the reply as feedback
        result = await process_telegram_reply(db, reply_info)
        
        # Send acknowledgment back to user
        await send_telegram_acknowledgment(
            chat_id=reply_info.get("chat_id"),
            result=result,
            reply_to_message_id=reply_info.get("message_id")
        )
        
        return {"ok": True, "result": result}
        
    except Exception as e:
        logger.error(f"Error processing Telegram webhook: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


@router.post("/telegram/setup-webhook")
async def setup_telegram_webhook(
    webhook_url: str = Query(..., description="Full HTTPS URL for the webhook (e.g., https://yourdomain.com/api/v1/strategies/telegram/webhook)"),
    secret_token: Optional[str] = Query(None, description="Secret token for webhook verification (optional but recommended)"),
    user=Depends(get_current_user)
):
    """
    Set up the Telegram webhook for reply-based feedback.
    
    Requirements:
    - webhook_url must be HTTPS
    - webhook_url must be publicly accessible
    
    Example:
        POST /telegram/setup-webhook?webhook_url=https://myserver.com/api/v1/strategies/telegram/webhook&secret_token=my_secret
    
    After setup, when users reply to recommendation notifications on Telegram,
    their replies will be processed as feedback.
    """
    import os
    from app.shared.services.telegram_webhook import set_telegram_webhook
    import logging
    
    logger = logging.getLogger(__name__)
    
    if not webhook_url.startswith("https://"):
        return {
            "success": False,
            "error": "Webhook URL must use HTTPS"
        }
    
    # Use provided secret or generate from env
    secret = secret_token or os.getenv('TELEGRAM_WEBHOOK_SECRET')
    
    result = set_telegram_webhook(webhook_url, secret)
    
    if result.get("ok"):
        logger.info(f"Telegram webhook set to: {webhook_url}")
        return {
            "success": True,
            "message": "Webhook configured successfully",
            "webhook_url": webhook_url,
            "secret_configured": bool(secret),
            "telegram_response": result
        }
    else:
        return {
            "success": False,
            "error": result.get("error") or result.get("description", "Unknown error"),
            "telegram_response": result
        }


@router.get("/telegram/webhook-info")
async def get_telegram_webhook_info_endpoint(
    user=Depends(get_current_user)
):
    """
    Get current Telegram webhook configuration.
    
    Shows:
    - Current webhook URL
    - Pending updates
    - Last error (if any)
    """
    from app.shared.services.telegram_webhook import get_telegram_webhook_info
    
    info = get_telegram_webhook_info()
    
    if info.get("error"):
        return {
            "success": False,
            "error": info["error"]
        }
    
    result = info.get("result", {})
    return {
        "success": True,
        "webhook_url": result.get("url", ""),
        "has_custom_certificate": result.get("has_custom_certificate", False),
        "pending_update_count": result.get("pending_update_count", 0),
        "last_error_date": result.get("last_error_date"),
        "last_error_message": result.get("last_error_message"),
        "max_connections": result.get("max_connections"),
        "allowed_updates": result.get("allowed_updates", []),
    }


@router.delete("/telegram/webhook")
async def delete_telegram_webhook_endpoint(
    user=Depends(get_current_user)
):
    """
    Delete the Telegram webhook.
    
    This switches Telegram back to polling mode.
    Use this if you want to disable reply-based feedback.
    """
    from app.shared.services.telegram_webhook import delete_telegram_webhook
    import logging
    
    logger = logging.getLogger(__name__)
    
    result = delete_telegram_webhook()
    
    if result.get("ok"):
        logger.info("Telegram webhook deleted")
        return {
            "success": True,
            "message": "Webhook deleted successfully"
        }
    else:
        return {
            "success": False,
            "error": result.get("error") or result.get("description", "Unknown error")
        }


@router.get("/telegram/feedback-tracking")
async def get_telegram_feedback_tracking(
    days_back: int = Query(7, description="Days of tracking data to retrieve"),
    include_processed: bool = Query(True, description="Include already-processed messages"),
    limit: int = Query(50, description="Maximum records to return"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get Telegram message tracking data.
    
    Shows which Telegram messages have been sent and whether
    they've received replies/feedback.
    """
    from datetime import timedelta
    from app.modules.strategies.models import TelegramMessageTracking
    
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    
    query = db.query(TelegramMessageTracking).filter(
        TelegramMessageTracking.sent_at >= cutoff
    )
    
    if not include_processed:
        query = query.filter(TelegramMessageTracking.feedback_processed == False)
    
    records = query.order_by(TelegramMessageTracking.sent_at.desc()).limit(limit).all()
    
    return {
        "tracking_data": [
            {
                "id": r.id,
                "telegram_message_id": r.telegram_message_id,
                "recommendation_count": len(r.recommendation_ids) if r.recommendation_ids else 0,
                "recommendation_ids": r.recommendation_ids,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "reply_received": r.reply_received,
                "reply_text": r.reply_text,
                "reply_received_at": r.reply_received_at.isoformat() if r.reply_received_at else None,
                "feedback_processed": r.feedback_processed,
            }
            for r in records
        ],
        "count": len(records),
        "days_back": days_back
    }


@router.post("/telegram/poll-replies")
async def poll_telegram_replies(
    user=Depends(get_current_user)
):
    """
    Manually poll Telegram for new reply feedback.
    
    Use this when webhook is not configured (localhost development).
    Checks for new replies to notification messages and processes them as feedback.
    
    Returns:
        - status: 'success', 'no_updates', or 'error'
        - updates_received: Number of Telegram updates found
        - feedback_saved: Number of feedback records created
    """
    from app.shared.services.telegram_poller import poll_and_process_replies
    
    result = await poll_and_process_replies()
    return result


@router.get("/telegram/pending-updates")
async def get_pending_telegram_updates(
    user=Depends(get_current_user)
):
    """
    Check how many Telegram updates are pending (not yet processed).
    
    Useful for debugging and monitoring the Telegram integration.
    """
    import requests
    from app.core.config import settings
    
    bot_token = settings.TELEGRAM_BOT_TOKEN
    if not bot_token:
        raise HTTPException(status_code=500, detail="TELEGRAM_BOT_TOKEN not configured")
    
    try:
        resp = requests.get(f"https://api.telegram.org/bot{bot_token}/getWebhookInfo")
        webhook_info = resp.json()
        
        resp2 = requests.get(f"https://api.telegram.org/bot{bot_token}/getUpdates?limit=0")
        updates_info = resp2.json()
        
        return {
            "webhook_configured": bool(webhook_info.get("result", {}).get("url")),
            "webhook_url": webhook_info.get("result", {}).get("url", ""),
            "pending_update_count": webhook_info.get("result", {}).get("pending_update_count", 0),
            "updates_available": len(updates_info.get("result", [])),
            "message": "Use POST /telegram/poll-replies to process pending updates"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check Telegram status: {str(e)}")


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

