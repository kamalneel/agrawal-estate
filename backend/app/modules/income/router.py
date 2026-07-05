"""
Income Management API routes.
Handles salary, stock income (options & dividends), rental income, and passive income.

ARCHITECTURE: All endpoints query the database directly.
The database is the SINGLE SOURCE OF TRUTH.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from pydantic import BaseModel as PydanticBaseModel

from app.core.database import get_db
from app.modules.income.rental_service import get_rental_service
from app.modules.income.salary_service import get_salary_service, reset_salary_service
from app.modules.income import db_queries


class SalaryProjectionCreate(PydanticBaseModel):
    person: str
    monthly_net: float
    effective_from: str  # YYYY-MM
    effective_to: Optional[str] = None
    notes: Optional[str] = None

router = APIRouter()


# =============================================================================
# INCOME SUMMARY - Single source of truth for all income totals
# =============================================================================

@router.get("/summary")
async def get_income_summary(
    year: Optional[int] = Query(default=None, description="Filter by year (None = all years)"),
    db: Session = Depends(get_db)
):
    """
    Get complete income summary across all sources.
    Returns totals for options, dividends, interest.
    
    This is THE authoritative source for income totals.
    """
    return db_queries.get_income_summary(db, year=year)


# =============================================================================
# OPTIONS INCOME - Direct database queries
# =============================================================================

@router.get("/options")
async def get_options_income(
    year: Optional[int] = Query(default=None, description="Filter by year"),
    db: Session = Depends(get_db)
):
    """
    Get consolidated options income across all accounts.
    Includes monthly breakdown, by-account breakdown, and transactions.
    """
    summary = db_queries.get_options_income_summary(db, year=year)
    monthly = db_queries.get_options_income_monthly(db, year=year)
    by_account = db_queries.get_options_income_by_account(db, year=year)
    by_symbol = db_queries.get_options_income_by_symbol(db, year=year)
    transactions = db_queries.get_options_transactions(db, year=year, limit=100)

    return {
        'total_income': summary['total_income'],
        'transaction_count': summary['transaction_count'],
        'monthly': monthly,
        'by_account': by_account,
        'by_symbol': by_symbol,
        'transactions': transactions
    }


@router.get("/options/by-type")
async def get_options_by_type(taxable_only: bool = False, db: Session = Depends(get_db)):
    """
    Monthly options income split into calls vs puts.
    Returns { 'YYYY-MM': { calls: float, puts: float } }
    """
    return db_queries.get_options_income_by_type_monthly(db, taxable_only=taxable_only)


@router.get("/options/chart")
async def get_options_chart_data(
    start_year: Optional[int] = Query(default=None, description="Start year for chart data"),
    db: Session = Depends(get_db)
):
    """
    Get monthly options income data formatted for charting.
    """
    return {
        "data": db_queries.get_monthly_chart_data(db, 'options', start_year=start_year)
    }


# =============================================================================
# DIVIDEND INCOME - Direct database queries
# =============================================================================

@router.get("/dividends")
async def get_dividend_income(
    year: Optional[int] = Query(default=None, description="Filter by year"),
    db: Session = Depends(get_db)
):
    """
    Get consolidated dividend income across all accounts.
    Includes monthly breakdown, by-account breakdown, by-symbol breakdown, and transactions.
    """
    summary = db_queries.get_dividend_income_summary(db, year=year)
    monthly = db_queries.get_dividend_income_monthly(db, year=year)
    by_account = db_queries.get_dividend_income_by_account(db, year=year)
    by_symbol = db_queries.get_dividend_by_symbol(db, year=year)
    transactions = db_queries.get_dividend_transactions(db, year=year, limit=50)
    
    return {
        'total_income': summary['total_income'],
        'transaction_count': summary['transaction_count'],
        'monthly': monthly,
        'by_account': by_account,
        'by_symbol': by_symbol,
        'transactions': transactions
    }


@router.get("/dividends/chart")
async def get_dividend_chart_data(
    start_year: Optional[int] = Query(default=None, description="Start year for chart data"),
    db: Session = Depends(get_db)
):
    """
    Get monthly dividend income data formatted for charting.
    """
    return {
        "data": db_queries.get_monthly_chart_data(db, 'dividends', start_year=start_year)
    }


# =============================================================================
# INTEREST INCOME - Direct database queries
# =============================================================================

@router.get("/interest")
async def get_interest_income(
    year: Optional[int] = Query(default=None, description="Filter by year"),
    db: Session = Depends(get_db)
):
    """
    Get consolidated interest income across all accounts.
    Includes monthly breakdown, by-account breakdown, and transactions.
    """
    summary = db_queries.get_interest_income_summary(db, year=year)
    monthly = db_queries.get_interest_income_monthly(db, year=year)
    by_account = db_queries.get_interest_income_by_account(db, year=year)
    transactions = db_queries.get_interest_transactions(db, year=year, limit=50)
    
    return {
        'total_income': summary['total_income'],
        'transaction_count': summary['transaction_count'],
        'monthly': monthly,
        'by_account': by_account,
        'transactions': transactions
    }


@router.get("/interest/chart")
async def get_interest_chart_data(
    start_year: Optional[int] = Query(default=None, description="Start year for chart data"),
    db: Session = Depends(get_db)
):
    """
    Get monthly interest income data formatted for charting.
    """
    return {
        "data": db_queries.get_monthly_chart_data(db, 'interest', start_year=start_year)
    }


# =============================================================================
# STOCK SALES & LENDING - These need database query implementations
# For now, return empty data (TODO: implement if needed)
# =============================================================================

@router.get("/stock-sales")
async def get_stock_sales(db: Session = Depends(get_db)):
    """
    Get consolidated stock sales proceeds across all accounts.
    TODO: Implement with direct DB queries if needed.
    """
    return {
        'total_proceeds': 0,
        'transaction_count': 0,
        'monthly': {},
        'by_symbol': {},
        'by_account': {}
    }


@router.get("/stock-sales/chart")
async def get_stock_sales_chart_data(
    start_year: Optional[int] = Query(default=None, description="Start year for chart data"),
    db: Session = Depends(get_db)
):
    """Get monthly stock sales data for charting."""
    return {"data": []}


@router.get("/stock-lending")
async def get_stock_lending(db: Session = Depends(get_db)):
    """
    Get consolidated stock lending income across all accounts.
    TODO: Implement with direct DB queries if needed.
    """
    return {
        'total_income': 0,
        'transaction_count': 0,
        'monthly': {},
        'by_account': {}
    }


@router.get("/stock-lending/chart")
async def get_stock_lending_chart_data(
    start_year: Optional[int] = Query(default=None, description="Start year for chart data"),
    db: Session = Depends(get_db)
):
    """Get monthly stock lending data for charting."""
    return {"data": []}


# =============================================================================
# ACCOUNT-SPECIFIC ENDPOINTS - Direct database queries
# =============================================================================

@router.get("/accounts/{account_name}/income-by-symbol")
async def get_account_income_by_symbol(
    account_name: str,
    year: Optional[int] = Query(default=None, description="Filter by year (None = all time)"),
    month: Optional[int] = Query(default=None, description="Filter by month (1-12, None = full year)"),
    db: Session = Depends(get_db)
):
    """
    Get options and dividend income by symbol for a specific account,
    filtered by time period.
    """
    from app.modules.investments.models import InvestmentAccount

    account = db.query(InvestmentAccount).filter(
        InvestmentAccount.account_name == account_name
    ).first()

    if not account:
        return {'options_by_symbol': {}, 'dividends_by_symbol': {}}

    options_by_symbol = db_queries.get_options_income_by_symbol(
        db, year=year, month=month, account_id=account.account_id
    )
    dividends_by_symbol = db_queries.get_dividend_by_symbol(
        db, year=year, month=month, account_id=account.account_id
    )

    return {
        'options_by_symbol': options_by_symbol,
        'dividends_by_symbol': dividends_by_symbol,
    }


@router.get("/accounts/{account_name}/options")
async def get_account_options_detail(
    account_name: str,
    db: Session = Depends(get_db)
):
    """
    Get detailed options income for a specific account.
    Returns monthly data for all years.
    """
    from app.modules.investments.models import InvestmentAccount
    
    # Find the account
    account = db.query(InvestmentAccount).filter(
        InvestmentAccount.account_name == account_name
    ).first()
    
    if not account:
        return {'error': 'Account not found', 'total_income': 0, 'monthly': {}, 'available_months': []}
    
    summary = db_queries.get_options_income_summary(db, account_id=account.account_id)
    monthly = db_queries.get_options_income_monthly(db, account_id=account.account_id)
    
    # Derive owner from account_name (e.g., "Neel's Individual" -> "Neel")
    owner = account.account_name.split("'")[0] if account.account_name and "'" in account.account_name else 'Unknown'
    
    return {
        'account_name': account_name,
        'owner': owner,
        'account_type': account.account_type,
        'total_income': summary['total_income'],
        'transaction_count': summary['transaction_count'],
        'monthly': monthly,
        'available_months': sorted(monthly.keys())
    }


@router.get("/accounts/{account_name}/options/weekly")
async def get_account_options_weekly(
    account_name: str,
    year: int = Query(..., description="Year"),
    month: int = Query(..., description="Month (1-12)"),
    db: Session = Depends(get_db)
):
    """
    Get weekly breakdown of options income for a specific account and month.
    Returns data organized by symbol and week with totals.
    Uses Mon-Fri trading weeks and separates puts from calls.
    """
    from app.modules.investments.models import InvestmentAccount, InvestmentTransaction
    from sqlalchemy import extract
    from datetime import datetime, date, timedelta
    import calendar
    import re

    # Find the account
    account = db.query(InvestmentAccount).filter(
        InvestmentAccount.account_name == account_name
    ).first()

    # Compute trading weeks that overlap this month
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    # Find the Monday of the week containing the first day of the month
    first_monday = first_day - timedelta(days=first_day.weekday())

    # Build list of trading weeks (each defined by its Monday)
    weeks_list = []
    monday = first_monday
    week_index = 1
    while monday <= last_day:
        friday = monday + timedelta(days=4)
        # Only include weeks that overlap with the month
        week_start_in_month = max(monday, first_day)
        week_end_in_month = min(friday, last_day)

        if week_start_in_month <= week_end_in_month:
            month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            m_abbr = month_names[week_start_in_month.month - 1]
            if week_start_in_month == week_end_in_month:
                label = f"{m_abbr} {week_start_in_month.day}"
                range_str = label
            else:
                end_m_abbr = month_names[week_end_in_month.month - 1]
                if week_start_in_month.month == week_end_in_month.month:
                    label = f"{m_abbr} {week_start_in_month.day}-{week_end_in_month.day}"
                else:
                    label = f"{m_abbr} {week_start_in_month.day}-{end_m_abbr} {week_end_in_month.day}"
                range_str = label

            weeks_list.append({
                'key': f'week{week_index}',
                'label': label,
                'range': range_str,
                'monday': monday,
            })
            week_index += 1

        monday += timedelta(days=7)

    week_keys = [w['key'] for w in weeks_list]
    # Map Monday date -> week key
    monday_to_week = {w['monday']: w['key'] for w in weeks_list}

    if not account:
        return {
            'error': 'Account not found',
            'month': f"{year}-{month:02d}",
            'month_formatted': datetime(year, month, 1).strftime('%B %Y'),
            'month_total': 0,
            'weekly_data': {},
            'symbols': [],
            'weeks': [{'key': w['key'], 'label': w['label'], 'range': w['range']} for w in weeks_list],
            'weekly_totals': {k: 0 for k in week_keys},
            'weekly_counts': {k: 0 for k in week_keys},
            'transaction_count': 0,
        }

    # Get transactions for the specified month
    transactions = db.query(InvestmentTransaction).filter(
        InvestmentTransaction.account_id == account.account_id,
        InvestmentTransaction.transaction_type.in_(['STO', 'BTC', 'STC', 'BTO']),
        extract('year', InvestmentTransaction.transaction_date) == year,
        extract('month', InvestmentTransaction.transaction_date) == month
    ).all()

    # Initialize weekly totals
    weekly_totals = {k: {'count': 0, 'amount': 0.0} for k in week_keys}

    # Organize by symbol and week
    by_symbol = {}
    month_total = 0.0

    def _is_put(description: str) -> bool:
        """Check if transaction description indicates a put option."""
        if not description:
            return False
        return bool(re.search(r'\bPut\b', description, re.IGNORECASE))

    for txn in transactions:
        base_symbol = txn.symbol or 'OTHER'
        # Separate puts from calls
        desc = txn.description or ''
        if _is_put(desc):
            symbol = f"{base_symbol} (Put)"
        else:
            symbol = base_symbol

        txn_date = txn.transaction_date
        if isinstance(txn_date, datetime):
            txn_date = txn_date.date()
        txn_monday = txn_date - timedelta(days=txn_date.weekday())
        week_key = monday_to_week.get(txn_monday)
        if not week_key:
            # Transaction falls on a weekend or outside computed weeks; assign to nearest
            closest = min(weeks_list, key=lambda w: abs((w['monday'] - txn_monday).days))
            week_key = closest['key']

        amount = float(txn.amount or 0)
        is_sto = txn.transaction_type == 'STO'
        contract_count = abs(txn.quantity) if txn.quantity else 1

        if symbol not in by_symbol:
            by_symbol[symbol] = {k: {'count': 0, 'amount': 0.0} for k in week_keys}
            by_symbol[symbol]['total_count'] = 0
            by_symbol[symbol]['total_amount'] = 0.0

        if is_sto:
            by_symbol[symbol][week_key]['count'] += contract_count
            by_symbol[symbol]['total_count'] += contract_count
            weekly_totals[week_key]['count'] += contract_count
        by_symbol[symbol][week_key]['amount'] += amount
        by_symbol[symbol]['total_amount'] += amount

        weekly_totals[week_key]['amount'] += amount

        month_total += amount

    # Convert to the format expected by frontend
    weekly_data = {}
    for symbol, data in by_symbol.items():
        entry = {k: {'count': data[k]['count'], 'amount': data[k]['amount']} for k in week_keys}
        entry['total_count'] = data['total_count']
        entry['total_amount'] = data['total_amount']
        weekly_data[symbol] = entry

    # Sort symbols by total amount
    sorted_symbols = sorted(by_symbol.keys(), key=lambda s: by_symbol[s]['total_amount'], reverse=True)

    return {
        'month': f"{year}-{month:02d}",
        'month_formatted': datetime(year, month, 1).strftime('%B %Y'),
        'month_total': month_total,
        'weekly_data': weekly_data,
        'symbols': sorted_symbols,
        'weeks': [{'key': w['key'], 'label': w['label'], 'range': w['range']} for w in weeks_list],
        'weekly_totals': {k: weekly_totals[k]['amount'] for k in week_keys},
        'weekly_counts': {k: weekly_totals[k]['count'] for k in week_keys},
        'transaction_count': len(transactions),
    }


@router.get("/rental")
async def get_rental_income():
    """
    Get rental income summary including all properties.
    Shows gross income, expenses breakdown, and net income.
    """
    service = get_rental_service()
    return service.get_rental_summary()


@router.get("/rental/chart")
async def get_rental_chart_data(
    year: int = Query(default=None, description="Filter by year")
):
    """
    Get monthly rental income data formatted for charting.
    """
    service = get_rental_service()
    return {
        "data": service.get_monthly_chart_data(year=year)
    }


@router.post("/rental/reload")
async def reload_rental_data():
    """
    Reload rental income data from files.
    """
    global _rental_service
    from app.modules.income.rental_service import RentalIncomeService, _rental_service
    
    # Create new service instance to force reload
    service = RentalIncomeService()
    service.load_all_properties()
    
    # Update the singleton
    import app.modules.income.rental_service as rental_module
    rental_module._rental_service = service
    
    return {
        "status": "success",
        "message": "Rental data reloaded",
        "properties_loaded": len(service.properties)
    }


@router.get("/salary")
async def get_salary_income(db: Session = Depends(get_db)):
    """
    Get salary income summary including all employees.
    Shows gross income, net income, and tax breakdowns by year.
    """
    service = get_salary_service(db=db)
    return service.get_salary_summary()


# =============================================================================
# SALARY PROJECTIONS - Config for BBD income offset
# (Must be registered before /salary/{year} to avoid path conflict)
# =============================================================================

@router.get("/salary/projections")
async def list_salary_projections(db: Session = Depends(get_db)):
    """List all salary projection records."""
    from sqlalchemy import text
    rows = db.execute(text(
        "SELECT id, person, monthly_net, effective_from, effective_to, notes "
        "FROM salary_projections ORDER BY person, effective_from"
    )).fetchall()
    return {
        'projections': [
            {
                'id': r[0],
                'person': r[1],
                'monthly_net': float(r[2]),
                'effective_from': r[3],
                'effective_to': r[4],
                'notes': r[5],
            }
            for r in rows
        ]
    }


@router.post("/salary/projections")
async def create_salary_projection(body: SalaryProjectionCreate, db: Session = Depends(get_db)):
    """Create or upsert a salary projection by (person, effective_from)."""
    from sqlalchemy import text
    existing = db.execute(text(
        "SELECT id FROM salary_projections WHERE person = :person AND effective_from = :ef"
    ), {'person': body.person, 'ef': body.effective_from}).fetchone()

    if existing:
        db.execute(text(
            "UPDATE salary_projections SET monthly_net = :mn, effective_to = :et, notes = :n, updated_at = NOW() "
            "WHERE id = :id"
        ), {'mn': body.monthly_net, 'et': body.effective_to, 'n': body.notes, 'id': existing[0]})
        row_id = existing[0]
    else:
        result = db.execute(text(
            "INSERT INTO salary_projections (person, monthly_net, effective_from, effective_to, notes, created_at, updated_at) "
            "VALUES (:p, :mn, :ef, :et, :n, NOW(), NOW()) RETURNING id"
        ), {'p': body.person, 'mn': body.monthly_net, 'ef': body.effective_from, 'et': body.effective_to, 'n': body.notes})
        row_id = result.fetchone()[0]

    db.commit()
    return {
        'id': row_id,
        'person': body.person,
        'monthly_net': body.monthly_net,
        'effective_from': body.effective_from,
        'effective_to': body.effective_to,
        'notes': body.notes,
    }


@router.delete("/salary/projections/{projection_id}")
async def delete_salary_projection(projection_id: int, db: Session = Depends(get_db)):
    """Delete a salary projection."""
    from sqlalchemy import text
    result = db.execute(text(
        "DELETE FROM salary_projections WHERE id = :id RETURNING id"
    ), {'id': projection_id})
    deleted = result.fetchone()
    if not deleted:
        raise HTTPException(status_code=404, detail="Projection not found")
    db.commit()
    return {'status': 'deleted', 'id': projection_id}


@router.get("/salary/{year}")
async def get_salary_income_by_year(year: int, db: Session = Depends(get_db)):
    """
    Get salary income filtered by year.
    """
    service = get_salary_service(db=db)
    return service.get_salary_by_year(year)


@router.post("/salary/reload")
async def reload_salary_data(db: Session = Depends(get_db)):
    """
    Reload salary income data from files.
    """
    reset_salary_service()
    service = get_salary_service(db=db)
    
    return {
        "status": "success",
        "message": "Salary data reloaded",
        "employees_loaded": len(service.salaries)
    }


@router.post("/salary/import-w2")
async def import_w2_data(db: Session = Depends(get_db)):
    """
    Import all W-2 data from PDF files into the database.
    This only needs to be run once; future lookups will use the database.
    """
    from app.modules.income.salary_service import SalaryService
    
    service = SalaryService(db=db)
    result = service.import_w2_to_database()
    
    # Reset the singleton to force reload from database
    reset_salary_service()
    
    return result


@router.get("/salary/employee/{employee_name}")
async def get_employee_salary_detail(
    employee_name: str,
    db: Session = Depends(get_db)
):
    """
    Get detailed W-2 history for a specific employee.
    Returns all W-2 records with yearly breakdowns and employer details.
    """
    from sqlalchemy import text
    
    # Normalize employee name for matching
    name_pattern = f"%{employee_name.replace('_', ' ').title()}%"
    
    # Get all W-2 records for this employee
    result = db.execute(text("""
        SELECT 
            tax_year,
            employer,
            wages,
            federal_tax_withheld,
            state_tax_withheld,
            social_security_tax,
            medicare_tax,
            retirement_401k,
            net_income,
            source_file
        FROM w2_records
        WHERE employee_name LIKE :name
        ORDER BY tax_year DESC, wages DESC
    """), {'name': name_pattern})
    
    records = []
    yearly_totals = {}
    
    for row in result.fetchall():
        year = row[0]
        record = {
            'year': year,
            'employer': row[1],
            'wages': float(row[2] or 0),
            'federal_tax': float(row[3] or 0),
            'state_tax': float(row[4] or 0),
            'social_security_tax': float(row[5] or 0),
            'medicare_tax': float(row[6] or 0),
            'retirement_401k': float(row[7] or 0),
            'net_income': float(row[8] or 0),
            'source': row[9] or ''
        }
        records.append(record)
        
        # Aggregate yearly totals
        if year not in yearly_totals:
            yearly_totals[year] = {
                'year': year,
                'total_wages': 0,
                'total_federal_tax': 0,
                'total_state_tax': 0,
                'employers': []
            }
        yearly_totals[year]['total_wages'] += record['wages']
        yearly_totals[year]['total_federal_tax'] += record['federal_tax']
        yearly_totals[year]['total_state_tax'] += record['state_tax']
        yearly_totals[year]['employers'].append(record['employer'])
    
    # Calculate totals
    total_wages = sum(r['wages'] for r in records)
    total_federal_tax = sum(r['federal_tax'] for r in records)
    total_state_tax = sum(r['state_tax'] for r in records)
    
    return {
        'employee_name': employee_name.replace('_', ' ').title(),
        'total_wages': total_wages,
        'total_federal_tax': total_federal_tax,
        'total_state_tax': total_state_tax,
        'years_count': len(yearly_totals),
        'records': records,
        'yearly_summary': sorted(yearly_totals.values(), key=lambda x: x['year'], reverse=True)
    }


@router.get("/sources")
async def list_income_sources(db: Session = Depends(get_db)):
    """List all income sources (placeholder for salary, rental, etc.)."""
    # Get actual salary data
    salary_service = get_salary_service()
    salary_summary = salary_service.get_salary_summary()
    
    sources = []
    
    # Add salary sources
    for emp in salary_summary.get('employees', []):
        sources.append({
            "id": f"salary_{emp['name'].lower().replace(' ', '_')}",
            "name": f"{emp['name']}'s Salary",
            "type": "salary",
            "status": "active" if emp['total_gross'] > 0 else "pending_upload",
            "description": f"{emp['employer']} - W2 income",
            "total_gross": emp['total_gross'],
            "total_net": emp['total_net'],
        })
    
    # Add placeholder for Neel's salary if not found
    if not any('neel' in s['id'].lower() for s in sources):
        sources.append({
            "id": "salary_neel",
            "name": "Neel's Salary", 
            "type": "salary",
            "status": "pending_upload",
            "description": "W2 income - awaiting file upload"
        })
    
    sources.extend([
        {
            "id": "rental_income",
            "name": "Rental Income",
            "type": "rental",
            "status": "pending_upload",
            "description": "Property rental income - awaiting CSV upload"
        },
        {
            "id": "investment_income",
            "name": "Investment Income",
            "type": "investment",
            "status": "active",
            "description": "Options, dividends, and interest from Robinhood accounts"
        }
    ])
    
    return {"sources": sources}


@router.get("/sources/{source_id}")
async def get_income_source(source_id: str, db: Session = Depends(get_db)):
    """Get details for a specific income source."""
    if source_id == "investment_income":
        service = get_income_service()
        return service.get_income_summary()
    
    return {
        "source": {
            "id": source_id,
            "status": "pending_upload",
            "message": "This income source requires file upload to populate data."
        }
    }


@router.post("/sources")
async def create_income_source(db: Session = Depends(get_db)):
    """Create a new income source."""
    return {"source": None}


@router.get("/entries")
async def list_income_entries(
    db: Session = Depends(get_db),
    source_id: Optional[int] = None,
    income_type: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    tax_year: Optional[int] = None
):
    """
    List income entries with optional filters.
    Income types: salary, stock, rental, passive
    """
    return {"entries": [], "total": 0}


@router.post("/reload")
async def reload_income_data(db: Session = Depends(get_db)):
    """
    Reload/refresh income data.
    
    Since we now use direct database queries, this endpoint:
    1. Imports any new CSV data to the database (with deduplication)
    2. Returns current database statistics
    
    The database IS the source of truth - no in-memory cache to reload.
    """
    from app.modules.income.services import IncomeService
    from app.modules.investments.models import InvestmentAccount
    
    # Import any new CSV data to database
    import_service = IncomeService()
    import_result = import_service.import_csv_to_database()
    
    # Get account count from database
    account_count = db.query(InvestmentAccount).filter(
        InvestmentAccount.is_active == 'Y'
    ).count()
    
    return {
        "status": "success",
        "message": "Income data reloaded successfully",
        "accounts_loaded": account_count,
        "import_stats": {
            "files_processed": import_result.get("files_processed", 0),
            "records_imported": import_result.get("records_imported", 0),
            "records_skipped": import_result.get("records_skipped", 0),
        }
    }


@router.post("/import-to-database")
async def import_income_to_database():
    """
    Import all income transaction data from CSV files to the database.
    This is idempotent - uses deduplication to prevent duplicates.
    """
    from app.modules.income.services import IncomeService
    
    service = IncomeService()
    result = service.import_csv_to_database()
    
    return {
        "status": "success" if not result.get('errors') else "partial",
        "message": "Income data imported to database",
        **result
    }


@router.get("/monthly-positions")
async def get_monthly_positions(db: Session = Depends(get_db)):
    """
    Monthly equity and cash positions for the income table.

    Equity: last trading-day stock value per month from investment_holdings_history.
    Cash:   most recent account_cash_balance_history snapshot on or before the last day
            of each month (carry-forward so gaps between pastes are filled in).

    Returns { equity: {'YYYY-MM': float}, cash: {'YYYY-MM': float} }
    """
    from sqlalchemy import text

    equity_rows = db.execute(text("""
        SELECT
            TO_CHAR(snapshot_date, 'YYYY-MM') AS month,
            SUM(market_value) AS total
        FROM investment_holdings_history
        WHERE snapshot_date = (
            SELECT MAX(h2.snapshot_date)
            FROM investment_holdings_history h2
            WHERE TO_CHAR(h2.snapshot_date, 'YYYY-MM') = TO_CHAR(investment_holdings_history.snapshot_date, 'YYYY-MM')
        )
        GROUP BY month
        ORDER BY month
    """)).fetchall()

    cash_rows = db.execute(text("""
        WITH months AS (
            SELECT DISTINCT TO_CHAR(snapshot_date, 'YYYY-MM') AS month
            FROM account_cash_balance_history
        )
        SELECT
            m.month,
            (
                SELECT SUM(c.true_cash)
                FROM account_cash_balance_history c
                WHERE c.snapshot_date <= (TO_DATE(m.month, 'YYYY-MM') + INTERVAL '1 month' - INTERVAL '1 day')::date
                  AND c.snapshot_date = (
                      SELECT MAX(c2.snapshot_date)
                      FROM account_cash_balance_history c2
                      WHERE c2.account_name = c.account_name
                        AND c2.snapshot_date <= (TO_DATE(m.month, 'YYYY-MM') + INTERVAL '1 month' - INTERVAL '1 day')::date
                  )
            ) AS total_cash
        FROM months m
        ORDER BY m.month
    """)).fetchall()

    equity = {row.month: float(row.total or 0) for row in equity_rows}
    cash   = {row.month: float(row.total_cash or 0) for row in cash_rows}

    # Fill cash for months that have equity but no cash snapshot yet (carry-forward from latest available)
    sorted_months = sorted(set(equity.keys()) | set(cash.keys()))
    last_cash = 0.0
    for m in sorted_months:
        if m in cash:
            last_cash = cash[m]
        elif last_cash > 0:
            cash[m] = last_cash

    return {"equity": equity, "cash": cash}


# ===== Unified income (Phase 3 — docs/INCOME-UNIFICATION-SPEC.md) =====

@router.get("/unified")
async def get_unified_income_endpoint(
    granularity: str = Query(default="month", description="week (Friday-ending) | month | year"),
    start: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    taxable_only: bool = Query(default=False, description="Only taxable-account investment income (salary/rental always included)"),
    db: Session = Depends(get_db)
):
    """ALL income in one view — fixed (salary, rent) + dynamic (options,
    dividends, interest, lending, realized equity-sale P/L) — per period,
    all accounts, actual-receipt basis, Friday-ending weeks.
    """
    from datetime import date as _date
    from app.modules.income.unified_service import get_unified_income
    try:
        return get_unified_income(
            db, granularity=granularity,
            start=_date.fromisoformat(start) if start else None,
            end=_date.fromisoformat(end) if end else None,
            taxable_only=taxable_only)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/goal-settings")
async def get_goal_settings():
    """Yield-tracker goal settings (see data/goal_settings.json).
    Margin limits are manual — Robinhood does not expose the total line."""
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[4] / "data" / "goal_settings.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="goal_settings.json not found")
    return json.loads(path.read_text())


@router.get("/put-capacity")
async def get_put_capacity(db: Session = Depends(get_db)):
    """Put-selling capacity ("cash" base for the 2%/mo goal), monthly.

    capacity = sum over margin accounts of (margin line + cash balance;
    negative cash = margin consumed by assignments) + cash incl. locked put
    collateral in all other accounts (true_cash already includes collateral).
    Margin lines come from data/goal_settings.json (not exposed by broker);
    margin balances from statement history; per-account cash from sync
    snapshots (history begins 2026-06; earlier months carry margin component
    only and are flagged partial).
    """
    import json
    from pathlib import Path
    from sqlalchemy import text
    from datetime import date as _date

    settings_path = Path(__file__).resolve().parents[4] / "data" / "goal_settings.json"
    limits = json.loads(settings_path.read_text()).get("margin_limits", {}) if settings_path.exists() else {}
    id_to_name = {"neel_brokerage": "Neel's Brokerage", "jaya_brokerage": "Jaya's Brokerage"}
    margin_names = set(id_to_name.values())

    # margin component: statement monthly closing balances
    margin_rows = db.execute(text(
        "SELECT account_name, year, month, closing_balance FROM margin_monthly_balances"
    )).fetchall()
    margin_by_month: dict = {}
    last_bal: dict = {}
    for r in sorted(margin_rows, key=lambda x: (x.year, x.month)):
        key = f"{r.year}-{r.month:02d}"
        margin_by_month.setdefault(key, {})[r.account_name] = float(r.closing_balance or 0)

    # per-account cash snapshots (true_cash includes locked collateral)
    cash_rows = db.execute(text(
        """SELECT account_name, snapshot_date, true_cash FROM account_cash_balance_history
           WHERE account_name != 'Portfolio (Synthetic)' ORDER BY snapshot_date"""
    )).fetchall()

    today = _date.today()
    months = sorted(set(margin_by_month) | {r.snapshot_date.strftime("%Y-%m") for r in cash_rows})
    result = []
    for mk in months:
        if mk > today.strftime("%Y-%m"):
            continue
        month_end = mk + "-31"
        # latest cash snapshot per account on/before month end (carry-forward)
        latest: dict = {}
        for r in cash_rows:
            if r.snapshot_date.strftime("%Y-%m-%d") <= month_end:
                latest[r.account_name] = float(r.true_cash or 0)
        # margin balances: this month's, else carry forward
        for acct, bal in margin_by_month.get(mk, {}).items():
            last_bal[acct] = bal
        margin_component = 0.0
        cash_component = 0.0
        have_cash_history = False
        for acct_id, line in limits.items():
            name = id_to_name.get(acct_id, acct_id)
            # prefer live cash snapshot over statement history for the balance
            bal = latest.get(name)
            if bal is None:
                bal = last_bal.get(acct_id, last_bal.get(name))
            if bal is not None:
                margin_component += line + bal
            else:
                margin_component += line
        for name, cash in latest.items():
            if name in margin_names:
                continue
            cash_component += cash
            have_cash_history = True
        result.append({
            "month": mk,
            "capacity": round(margin_component + cash_component, 2),
            "margin_component": round(margin_component, 2),
            "cash_component": round(cash_component, 2),
            "partial": not have_cash_history,
        })
    return {"months": result, "current": result[-1] if result else None}
