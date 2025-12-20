"""
Database-first income queries.

This module provides direct database queries for income data.
All calculations happen at the database level for consistency.

PRINCIPLE: The database is the SINGLE SOURCE OF TRUTH.
"""

from typing import Dict, List, Optional, Any
from datetime import date
from decimal import Decimal
from sqlalchemy import func, extract, case, and_, or_
from sqlalchemy.orm import Session

from app.modules.investments.models import InvestmentTransaction, InvestmentAccount


def get_options_income_summary(
    db: Session,
    year: Optional[int] = None,
    account_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get options income summary directly from database.
    Includes ALL accounts (brokerage, retirement, IRA, etc.)
    
    Args:
        db: Database session
        year: Optional year filter (None = all years)
        account_id: Optional account filter (None = all accounts)
    
    Returns:
        Dict with total_income, transaction_count, and monthly breakdown
    """
    # Base query for STO/BTC transactions
    query = db.query(
        func.sum(InvestmentTransaction.amount).label('total'),
        func.count(InvestmentTransaction.id).label('count')
    ).join(
        InvestmentAccount,
        and_(
            InvestmentTransaction.account_id == InvestmentAccount.account_id,
            InvestmentTransaction.source == InvestmentAccount.source
        )
    ).filter(
        InvestmentTransaction.transaction_type.in_(['STO', 'BTC']),
    )
    
    # Apply filters
    if year:
        query = query.filter(extract('year', InvestmentTransaction.transaction_date) == year)
    if account_id:
        query = query.filter(InvestmentTransaction.account_id == account_id)
    
    result = query.first()
    total = float(result.total or 0)
    count = result.count or 0
    
    return {
        'total_income': total,
        'transaction_count': count
    }


def get_options_income_monthly(
    db: Session,
    year: Optional[int] = None,
    account_id: Optional[str] = None
) -> Dict[str, float]:
    """
    Get monthly options income breakdown.
    
    Returns:
        Dict mapping 'YYYY-MM' to total amount
    """
    query = db.query(
        func.to_char(InvestmentTransaction.transaction_date, 'YYYY-MM').label('month'),
        func.sum(InvestmentTransaction.amount).label('total')
    ).join(
        InvestmentAccount,
        and_(
            InvestmentTransaction.account_id == InvestmentAccount.account_id,
            InvestmentTransaction.source == InvestmentAccount.source
        )
    ).filter(
        InvestmentTransaction.transaction_type.in_(['STO', 'BTC']),
    )
    
    if year:
        query = query.filter(extract('year', InvestmentTransaction.transaction_date) == year)
    if account_id:
        query = query.filter(InvestmentTransaction.account_id == account_id)
    
    query = query.group_by('month').order_by('month')
    
    return {row.month: float(row.total or 0) for row in query.all()}


def get_options_income_by_account(
    db: Session,
    year: Optional[int] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Get options income broken down by account.
    
    Returns:
        Dict mapping account_name to {owner, account_type, total, monthly}
    """
    # Get all active investment accounts
    # Note: is_active is stored as varchar 'true'/'false' in some databases
    accounts = db.query(InvestmentAccount).filter(
        InvestmentAccount.is_active == 'Y'
    ).all()
    
    result = {}
    
    for account in accounts:
        # Get totals for this account
        summary = get_options_income_summary(db, year=year, account_id=account.account_id)
        monthly = get_options_income_monthly(db, year=year, account_id=account.account_id)
        
        # Derive owner from account_name (e.g., "Neel's Brokerage" -> "Neel")
        owner = account.account_name.split("'")[0] if account.account_name and "'" in account.account_name else 'Unknown'
        
        result[account.account_name] = {
            'owner': owner,
            'account_type': account.account_type or 'unknown',
            'total': summary['total_income'],
            'transaction_count': summary['transaction_count'],
            'monthly': monthly
        }
    
    return result


def get_options_transactions(
    db: Session,
    year: Optional[int] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get options transactions (STO/BTC) ordered by date descending.
    
    Returns a list of transaction dicts with date, symbol, description, 
    trans_code, quantity, amount, and account fields.
    """
    query = db.query(
        InvestmentTransaction.transaction_date,
        InvestmentTransaction.symbol,
        InvestmentTransaction.description,
        InvestmentTransaction.transaction_type,
        InvestmentTransaction.quantity,
        InvestmentTransaction.amount,
        InvestmentAccount.account_name
    ).join(
        InvestmentAccount,
        and_(
            InvestmentTransaction.account_id == InvestmentAccount.account_id,
            InvestmentTransaction.source == InvestmentAccount.source
        )
    ).filter(
        InvestmentTransaction.transaction_type.in_(['STO', 'BTC', 'OEXP'])
    )
    
    if year:
        query = query.filter(extract('year', InvestmentTransaction.transaction_date) == year)
    
    query = query.order_by(InvestmentTransaction.transaction_date.desc()).limit(limit)
    
    results = []
    for row in query.all():
        results.append({
            'date': row.transaction_date.isoformat() if row.transaction_date else None,
            'symbol': row.symbol or '',
            'description': row.description or '',
            'trans_code': row.transaction_type or '',
            'quantity': int(row.quantity) if row.quantity else 0,
            'amount': float(row.amount) if row.amount else 0,
            'account': row.account_name or ''
        })
    
    return results


def get_dividend_income_summary(
    db: Session,
    year: Optional[int] = None,
    account_id: Optional[str] = None
) -> Dict[str, Any]:
    """Get dividend income summary from database."""
    query = db.query(
        func.sum(InvestmentTransaction.amount).label('total'),
        func.count(InvestmentTransaction.id).label('count')
    ).join(
        InvestmentAccount,
        and_(
            InvestmentTransaction.account_id == InvestmentAccount.account_id,
            InvestmentTransaction.source == InvestmentAccount.source
        )
    ).filter(
        InvestmentTransaction.transaction_type.in_(['DIVIDEND', 'CDIV', 'QUAL DIV REINVEST', 'REINVEST DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND']),
    )
    
    if year:
        query = query.filter(extract('year', InvestmentTransaction.transaction_date) == year)
    if account_id:
        query = query.filter(InvestmentTransaction.account_id == account_id)
    
    result = query.first()
    
    return {
        'total_income': float(result.total or 0),
        'transaction_count': result.count or 0
    }


def get_dividend_income_monthly(
    db: Session,
    year: Optional[int] = None,
    account_id: Optional[str] = None
) -> Dict[str, float]:
    """Get monthly dividend income breakdown."""
    query = db.query(
        func.to_char(InvestmentTransaction.transaction_date, 'YYYY-MM').label('month'),
        func.sum(InvestmentTransaction.amount).label('total')
    ).join(
        InvestmentAccount,
        and_(
            InvestmentTransaction.account_id == InvestmentAccount.account_id,
            InvestmentTransaction.source == InvestmentAccount.source
        )
    ).filter(
        InvestmentTransaction.transaction_type.in_(['DIVIDEND', 'CDIV', 'QUAL DIV REINVEST', 'REINVEST DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND']),
    )
    
    if year:
        query = query.filter(extract('year', InvestmentTransaction.transaction_date) == year)
    if account_id:
        query = query.filter(InvestmentTransaction.account_id == account_id)
    
    query = query.group_by('month').order_by('month')
    
    return {row.month: float(row.total or 0) for row in query.all()}


def get_dividend_income_by_account(
    db: Session,
    year: Optional[int] = None
) -> Dict[str, Dict[str, Any]]:
    """Get dividend income broken down by account."""
    accounts = db.query(InvestmentAccount).filter(
        InvestmentAccount.is_active == 'Y'
    ).all()
    
    result = {}
    
    for account in accounts:
        summary = get_dividend_income_summary(db, year=year, account_id=account.account_id)
        monthly = get_dividend_income_monthly(db, year=year, account_id=account.account_id)
        
        # Derive owner from account_name (e.g., "Neel's Brokerage" -> "Neel")
        owner = account.account_name.split("'")[0] if account.account_name and "'" in account.account_name else 'Unknown'
        
        result[account.account_name] = {
            'owner': owner,
            'account_type': account.account_type or 'unknown',
            'total': summary['total_income'],
            'transaction_count': summary['transaction_count'],
            'monthly': monthly
        }
    
    return result


def get_interest_income_summary(
    db: Session,
    year: Optional[int] = None,
    account_id: Optional[str] = None
) -> Dict[str, Any]:
    """Get interest income summary from database."""
    query = db.query(
        func.sum(InvestmentTransaction.amount).label('total'),
        func.count(InvestmentTransaction.id).label('count')
    ).join(
        InvestmentAccount,
        and_(
            InvestmentTransaction.account_id == InvestmentAccount.account_id,
            InvestmentTransaction.source == InvestmentAccount.source
        )
    ).filter(
        InvestmentTransaction.transaction_type.in_(['INTEREST', 'INT', 'BANK INTEREST', 'BOND INTEREST']),
    )
    
    if year:
        query = query.filter(extract('year', InvestmentTransaction.transaction_date) == year)
    if account_id:
        query = query.filter(InvestmentTransaction.account_id == account_id)
    
    result = query.first()
    
    return {
        'total_income': float(result.total or 0),
        'transaction_count': result.count or 0
    }


def get_interest_income_monthly(
    db: Session,
    year: Optional[int] = None,
    account_id: Optional[str] = None
) -> Dict[str, float]:
    """Get monthly interest income breakdown."""
    query = db.query(
        func.to_char(InvestmentTransaction.transaction_date, 'YYYY-MM').label('month'),
        func.sum(InvestmentTransaction.amount).label('total')
    ).join(
        InvestmentAccount,
        and_(
            InvestmentTransaction.account_id == InvestmentAccount.account_id,
            InvestmentTransaction.source == InvestmentAccount.source
        )
    ).filter(
        InvestmentTransaction.transaction_type.in_(['INTEREST', 'INT', 'BANK INTEREST', 'BOND INTEREST']),
    )
    
    if year:
        query = query.filter(extract('year', InvestmentTransaction.transaction_date) == year)
    if account_id:
        query = query.filter(InvestmentTransaction.account_id == account_id)
    
    query = query.group_by('month').order_by('month')
    
    return {row.month: float(row.total or 0) for row in query.all()}


def get_interest_income_by_account(
    db: Session,
    year: Optional[int] = None
) -> Dict[str, Dict[str, Any]]:
    """Get interest income broken down by account."""
    accounts = db.query(InvestmentAccount).filter(
        InvestmentAccount.is_active == 'Y'
    ).all()
    
    result = {}
    
    for account in accounts:
        summary = get_interest_income_summary(db, year=year, account_id=account.account_id)
        monthly = get_interest_income_monthly(db, year=year, account_id=account.account_id)
        
        # Derive owner from account_name (e.g., "Neel's Brokerage" -> "Neel")
        owner = account.account_name.split("'")[0] if account.account_name and "'" in account.account_name else 'Unknown'
        
        result[account.account_name] = {
            'owner': owner,
            'account_type': account.account_type or 'unknown',
            'total': summary['total_income'],
            'transaction_count': summary['transaction_count'],
            'monthly': monthly
        }
    
    return result


def get_dividend_transactions(
    db: Session,
    year: Optional[int] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Get dividend transactions ordered by date descending.
    """
    query = db.query(
        InvestmentTransaction.transaction_date,
        InvestmentTransaction.symbol,
        InvestmentTransaction.amount,
        InvestmentAccount.account_name
    ).join(
        InvestmentAccount,
        and_(
            InvestmentTransaction.account_id == InvestmentAccount.account_id,
            InvestmentTransaction.source == InvestmentAccount.source
        )
    ).filter(
        InvestmentTransaction.transaction_type.in_(['DIVIDEND', 'CDIV', 'QUAL DIV REINVEST', 'REINVEST DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND']),
    )
    
    if year:
        query = query.filter(extract('year', InvestmentTransaction.transaction_date) == year)
    
    query = query.order_by(InvestmentTransaction.transaction_date.desc()).limit(limit)
    
    results = []
    for row in query.all():
        results.append({
            'date': row.transaction_date.isoformat() if row.transaction_date else None,
            'symbol': row.symbol or '',
            'amount': float(row.amount) if row.amount else 0,
            'account': row.account_name or ''
        })
    
    return results


def get_dividend_by_symbol(
    db: Session,
    year: Optional[int] = None
) -> Dict[str, float]:
    """
    Get total dividend income grouped by symbol.
    """
    query = db.query(
        InvestmentTransaction.symbol,
        func.sum(InvestmentTransaction.amount).label('total')
    ).join(
        InvestmentAccount,
        and_(
            InvestmentTransaction.account_id == InvestmentAccount.account_id,
            InvestmentTransaction.source == InvestmentAccount.source
        )
    ).filter(
        InvestmentTransaction.transaction_type.in_(['DIVIDEND', 'CDIV', 'QUAL DIV REINVEST', 'REINVEST DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND']),
        InvestmentTransaction.symbol.isnot(None),
    )
    
    if year:
        query = query.filter(extract('year', InvestmentTransaction.transaction_date) == year)
    
    query = query.group_by(InvestmentTransaction.symbol).order_by(func.sum(InvestmentTransaction.amount).desc())
    
    return {row.symbol: float(row.total or 0) for row in query.all() if row.symbol}


def get_interest_transactions(
    db: Session,
    year: Optional[int] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Get interest transactions ordered by date descending.
    """
    query = db.query(
        InvestmentTransaction.transaction_date,
        InvestmentTransaction.description,
        InvestmentTransaction.amount,
        InvestmentAccount.account_name,
        InvestmentAccount.source
    ).join(
        InvestmentAccount,
        and_(
            InvestmentTransaction.account_id == InvestmentAccount.account_id,
            InvestmentTransaction.source == InvestmentAccount.source
        )
    ).filter(
        InvestmentTransaction.transaction_type.in_(['INTEREST', 'INT', 'BANK INTEREST', 'BOND INTEREST']),
    )
    
    if year:
        query = query.filter(extract('year', InvestmentTransaction.transaction_date) == year)
    
    query = query.order_by(InvestmentTransaction.transaction_date.desc()).limit(limit)
    
    results = []
    for row in query.all():
        results.append({
            'date': row.transaction_date.isoformat() if row.transaction_date else None,
            'description': row.description or 'Interest',
            'amount': float(row.amount) if row.amount else 0,
            'account': row.account_name or '',
            'source': row.source or ''
        })
    
    return results


def get_income_summary(
    db: Session,
    year: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get complete income summary across all types.
    
    This is the SINGLE source of truth for income totals.
    """
    options = get_options_income_summary(db, year=year)
    dividends = get_dividend_income_summary(db, year=year)
    interest = get_interest_income_summary(db, year=year)
    
    # Get account-level breakdown
    accounts = db.query(InvestmentAccount).filter(
        InvestmentAccount.is_active == 'Y'
    ).all()
    
    account_summaries = []
    for account in accounts:
        acc_options = get_options_income_summary(db, year=year, account_id=account.account_id)
        acc_dividends = get_dividend_income_summary(db, year=year, account_id=account.account_id)
        acc_interest = get_interest_income_summary(db, year=year, account_id=account.account_id)
        
        # Derive owner from account_name
        owner = account.account_name.split("'")[0] if account.account_name and "'" in account.account_name else 'Unknown'
        
        account_summaries.append({
            'name': account.account_name,
            'account_id': account.account_id,
            'owner': owner,
            'account_type': account.account_type or 'unknown',
            'options_income': acc_options['total_income'],
            'dividend_income': acc_dividends['total_income'],
            'interest_income': acc_interest['total_income'],
            'total': acc_options['total_income'] + acc_dividends['total_income'] + acc_interest['total_income']
        })
    
    # Sort by total descending
    account_summaries.sort(key=lambda x: x['total'], reverse=True)
    
    return {
        'options_income': options['total_income'],
        'dividend_income': dividends['total_income'],
        'interest_income': interest['total_income'],
        'total_income': options['total_income'] + dividends['total_income'] + interest['total_income'],
        'accounts': account_summaries
    }


def get_monthly_chart_data(
    db: Session,
    income_type: str,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Get monthly data formatted for charts.
    
    Args:
        income_type: 'options', 'dividends', or 'interest'
        start_year: Optional start year filter
        end_year: Optional end year filter
    
    Returns:
        List of {month: 'YYYY-MM', value: float, year: int, formatted: str}
    """
    type_map = {
        'options': ['STO', 'BTC'],
        'dividends': ['DIVIDEND', 'CDIV', 'QUAL DIV REINVEST', 'REINVEST DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND'],
        'interest': ['INTEREST', 'INT', 'BANK INTEREST', 'BOND INTEREST']
    }
    
    transaction_types = type_map.get(income_type, [])
    if not transaction_types:
        return []
    
    query = db.query(
        func.to_char(InvestmentTransaction.transaction_date, 'YYYY-MM').label('month'),
        func.sum(InvestmentTransaction.amount).label('total')
    ).filter(
        InvestmentTransaction.transaction_type.in_(transaction_types)
    )
    
    if start_year:
        query = query.filter(extract('year', InvestmentTransaction.transaction_date) >= start_year)
    if end_year:
        query = query.filter(extract('year', InvestmentTransaction.transaction_date) <= end_year)
    
    query = query.group_by('month').order_by('month')
    
    result = []
    for row in query.all():
        year = int(row.month.split('-')[0])
        month_num = int(row.month.split('-')[1])
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        formatted = f"{month_names[month_num - 1]} {year}"
        
        result.append({
            'month': row.month,
            'value': float(row.total or 0),
            'year': year,
            'formatted': formatted
        })
    
    return result

