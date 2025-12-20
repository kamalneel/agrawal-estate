"""
Income Management API routes.
Handles salary, stock income (options & dividends), rental income, and passive income.

ARCHITECTURE: All endpoints query the database directly.
The database is the SINGLE SOURCE OF TRUTH.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from app.core.database import get_db
from app.modules.income.rental_service import get_rental_service
from app.modules.income.salary_service import get_salary_service, reset_salary_service
from app.modules.income import db_queries

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
    transactions = db_queries.get_options_transactions(db, year=year, limit=100)
    
    return {
        'total_income': summary['total_income'],
        'transaction_count': summary['transaction_count'],
        'monthly': monthly,
        'by_account': by_account,
        'transactions': transactions
    }


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
    """
    from app.modules.investments.models import InvestmentAccount, InvestmentTransaction
    from sqlalchemy import extract
    from datetime import datetime
    
    # Find the account
    account = db.query(InvestmentAccount).filter(
        InvestmentAccount.account_name == account_name
    ).first()
    
    if not account:
        return {
            'error': 'Account not found',
            'month': f"{year}-{month:02d}",
            'month_formatted': datetime(year, month, 1).strftime('%B %Y'),
            'month_total': 0,
            'weekly_data': {},
            'symbols': [],
            'weekly_totals': {'week1': 0, 'week2': 0, 'week3': 0, 'week4': 0, 'week5': 0},
            'weekly_counts': {'week1': 0, 'week2': 0, 'week3': 0, 'week4': 0, 'week5': 0},
            'transaction_count': 0,
        }
    
    # Get transactions for the specified month
    transactions = db.query(InvestmentTransaction).filter(
        InvestmentTransaction.account_id == account.account_id,
        InvestmentTransaction.transaction_type.in_(['STO', 'BTC']),
        extract('year', InvestmentTransaction.transaction_date) == year,
        extract('month', InvestmentTransaction.transaction_date) == month
    ).all()
    
    # Initialize weekly totals
    weekly_totals = {
        'week1': {'count': 0, 'amount': 0.0},
        'week2': {'count': 0, 'amount': 0.0},
        'week3': {'count': 0, 'amount': 0.0},
        'week4': {'count': 0, 'amount': 0.0},
        'week5': {'count': 0, 'amount': 0.0},
    }
    
    # Organize by symbol and week
    by_symbol = {}
    month_total = 0.0
    
    for txn in transactions:
        symbol = txn.symbol or 'OTHER'
        day = txn.transaction_date.day
        week = min((day - 1) // 7 + 1, 5)  # Week 1-5
        week_key = f'week{week}'
        amount = float(txn.amount or 0)
        contract_count = abs(txn.quantity) if txn.quantity else 1
        
        if symbol not in by_symbol:
            by_symbol[symbol] = {
                'week1': {'count': 0, 'amount': 0.0},
                'week2': {'count': 0, 'amount': 0.0},
                'week3': {'count': 0, 'amount': 0.0},
                'week4': {'count': 0, 'amount': 0.0},
                'week5': {'count': 0, 'amount': 0.0},
                'total_count': 0,
                'total_amount': 0.0,
            }
        
        by_symbol[symbol][week_key]['count'] += contract_count
        by_symbol[symbol][week_key]['amount'] += amount
        by_symbol[symbol]['total_count'] += contract_count
        by_symbol[symbol]['total_amount'] += amount
        
        weekly_totals[week_key]['count'] += contract_count
        weekly_totals[week_key]['amount'] += amount
        
        month_total += amount
    
    # Convert to the format expected by frontend
    weekly_data = {}
    for symbol, data in by_symbol.items():
        weekly_data[symbol] = {
            'week1': {'count': data['week1']['count'], 'amount': data['week1']['amount']},
            'week2': {'count': data['week2']['count'], 'amount': data['week2']['amount']},
            'week3': {'count': data['week3']['count'], 'amount': data['week3']['amount']},
            'week4': {'count': data['week4']['count'], 'amount': data['week4']['amount']},
            'week5': {'count': data['week5']['count'], 'amount': data['week5']['amount']},
            'total': {'count': data['total_count'], 'amount': data['total_amount']},
        }
    
    # Sort symbols by total amount
    sorted_symbols = sorted(by_symbol.keys(), key=lambda s: by_symbol[s]['total_amount'], reverse=True)
    
    return {
        'month': f"{year}-{month:02d}",
        'month_formatted': datetime(year, month, 1).strftime('%B %Y'),
        'month_total': month_total,
        'weekly_data': weekly_data,
        'symbols': sorted_symbols,
        'weekly_totals': {
            'week1': weekly_totals['week1']['amount'],
            'week2': weekly_totals['week2']['amount'],
            'week3': weekly_totals['week3']['amount'],
            'week4': weekly_totals['week4']['amount'],
            'week5': weekly_totals['week5']['amount'],
        },
        'weekly_counts': {
            'week1': weekly_totals['week1']['count'],
            'week2': weekly_totals['week2']['count'],
            'week3': weekly_totals['week3']['count'],
            'week4': weekly_totals['week4']['count'],
            'week5': weekly_totals['week5']['count'],
        },
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
