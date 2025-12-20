"""
India Investments service layer for business logic.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.modules.india_investments.models import (
    IndiaBankAccount,
    IndiaInvestmentAccount,
    IndiaStock,
    IndiaMutualFund,
    IndiaFixedDeposit,
    ExchangeRate,
)


def calculate_fd_current_value(principal: Decimal, interest_rate: Decimal, start_date: date, maturity_date: date, current_date: Optional[date] = None) -> Dict[str, Decimal]:
    """
    Calculate current value, accrued interest, and maturity value for a fixed deposit.
    
    Uses simple interest: Interest = Principal × Rate × (Days / 365)
    
    Args:
        principal: Initial deposit amount
        interest_rate: Annual interest rate (e.g., 7.5 for 7.5%)
        start_date: FD start date
        maturity_date: FD maturity date
        current_date: Current date (defaults to today)
    
    Returns:
        {
            'current_value': principal + accrued_interest,
            'accrued_interest': calculated interest,
            'maturity_value': principal + full_term_interest,
            'days_to_maturity': days remaining
        }
    """
    if current_date is None:
        current_date = date.today()
    
    if current_date < start_date:
        current_date = start_date
    
    # Calculate days held
    days_held = (current_date - start_date).days
    if days_held < 0:
        days_held = 0
    
    # Calculate accrued interest (simple interest)
    accrued_interest = principal * (interest_rate / 100) * (Decimal(days_held) / 365)
    
    # Current value = principal + accrued interest
    current_value = principal + accrued_interest
    
    # Calculate maturity value
    days_to_maturity = (maturity_date - current_date).days if maturity_date > current_date else 0
    total_days = (maturity_date - start_date).days
    if total_days < 0:
        total_days = 0
    full_term_interest = principal * (interest_rate / 100) * (Decimal(total_days) / 365)
    maturity_value = principal + full_term_interest
    
    return {
        'current_value': current_value,
        'accrued_interest': accrued_interest,
        'maturity_value': maturity_value,
        'days_to_maturity': days_to_maturity
    }


def get_all_india_investments(db: Session, owner: Optional[str] = None) -> Dict[str, Any]:
    """
    Get all India investments grouped by account and category.
    
    Returns:
        {
            'bank_accounts': [...],
            'investment_accounts': [...],
            'stocks': [...],
            'mutual_funds': [...],
            'fixed_deposits': [...],
            'cash_balances': [...],
            'total_value_inr': total,
            'exchange_rate': rate
        }
    """
    # Get exchange rate
    exchange_rate = db.query(ExchangeRate).filter(
        ExchangeRate.from_currency == 'USD',
        ExchangeRate.to_currency == 'INR'
    ).first()
    
    rate = float(exchange_rate.rate) if exchange_rate and exchange_rate.rate else 83.0  # Default fallback
    
    # Filter by owner if specified
    bank_accounts_query = db.query(IndiaBankAccount).filter(IndiaBankAccount.is_active == 'Y')
    investment_accounts_query = db.query(IndiaInvestmentAccount).filter(IndiaInvestmentAccount.is_active == 'Y')
    
    if owner:
        bank_accounts_query = bank_accounts_query.filter(IndiaBankAccount.owner == owner)
        investment_accounts_query = investment_accounts_query.filter(IndiaInvestmentAccount.owner == owner)
    
    bank_accounts = bank_accounts_query.all()
    investment_accounts = investment_accounts_query.all()
    
    # Get all stocks
    investment_account_ids = [acc.id for acc in investment_accounts]
    stocks = []
    mutual_funds = []
    
    if investment_account_ids:
        stocks = db.query(IndiaStock).filter(
            IndiaStock.investment_account_id.in_(investment_account_ids)
        ).all()
        
        mutual_funds = db.query(IndiaMutualFund).filter(
            IndiaMutualFund.investment_account_id.in_(investment_account_ids)
        ).all()
    
    # Get all fixed deposits
    bank_account_ids = [acc.id for acc in bank_accounts]
    fixed_deposits = []
    
    if bank_account_ids:
        fixed_deposits = db.query(IndiaFixedDeposit).filter(
            IndiaFixedDeposit.bank_account_id.in_(bank_account_ids),
            IndiaFixedDeposit.is_active == 'Y'
        ).all()
    
    # Calculate current values for FDs
    today = date.today()
    for fd in fixed_deposits:
        if fd.maturity_date and fd.start_date:
            calc = calculate_fd_current_value(
                fd.principal,
                fd.interest_rate,
                fd.start_date,
                fd.maturity_date,
                today
            )
            fd.current_value = calc['current_value']
            fd.accrued_interest = calc['accrued_interest']
            fd.maturity_value = calc['maturity_value']
    
    # Calculate totals
    total_cash = sum(float(acc.cash_balance or 0) for acc in bank_accounts)
    total_stocks = sum(float(stock.current_value or 0) for stock in stocks)
    total_mutual_funds = sum(float(mf.current_value or 0) for mf in mutual_funds)
    total_fds = sum(float(fd.current_value or fd.principal or 0) for fd in fixed_deposits)
    
    total_value_inr = total_cash + total_stocks + total_mutual_funds + total_fds
    
    return {
        'bank_accounts': [
            {
                'id': acc.id,
                'account_name': acc.account_name,
                'bank_name': acc.bank_name,
                'account_number': acc.account_number,
                'owner': acc.owner,
                'cash_balance': float(acc.cash_balance or 0),
            }
            for acc in bank_accounts
        ],
        'investment_accounts': [
            {
                'id': acc.id,
                'account_name': acc.account_name,
                'platform': acc.platform,
                'account_number': acc.account_number,
                'owner': acc.owner,
                'linked_bank_account_id': acc.linked_bank_account_id,
            }
            for acc in investment_accounts
        ],
        'stocks': [
            {
                'id': stock.id,
                'investment_account_id': stock.investment_account_id,
                'symbol': stock.symbol,
                'company_name': stock.company_name,
                'quantity': float(stock.quantity or 0),
                'average_price': float(stock.average_price or 0),
                'current_price': float(stock.current_price or 0),
                'cost_basis': float(stock.cost_basis or 0),
                'current_value': float(stock.current_value or 0),
                'profit_loss': float(stock.profit_loss or 0),
            }
            for stock in stocks
        ],
        'mutual_funds': [
            {
                'id': mf.id,
                'investment_account_id': mf.investment_account_id,
                'fund_name': mf.fund_name,
                'fund_code': mf.fund_code,
                'category': mf.category,
                'units': float(mf.units or 0),
                'nav': float(mf.nav or 0),
                'purchase_price': float(mf.purchase_price or 0),
                'cost_basis': float(mf.cost_basis or 0),
                'current_value': float(mf.current_value or 0),
                'profit_loss': float(mf.profit_loss or 0),
            }
            for mf in mutual_funds
        ],
        'fixed_deposits': [
            {
                'id': fd.id,
                'bank_account_id': fd.bank_account_id,
                'fd_number': fd.fd_number,
                'description': fd.description,
                'principal': float(fd.principal or 0),
                'interest_rate': float(fd.interest_rate or 0),
                'start_date': fd.start_date.isoformat() if fd.start_date else None,
                'maturity_date': fd.maturity_date.isoformat() if fd.maturity_date else None,
                'current_value': float(fd.current_value or fd.principal or 0),
                'accrued_interest': float(fd.accrued_interest or 0),
                'maturity_value': float(fd.maturity_value or 0),
                'days_to_maturity': (fd.maturity_date - today).days if fd.maturity_date and fd.maturity_date > today else 0,
            }
            for fd in fixed_deposits
        ],
        'total_value_inr': total_value_inr,
        'total_value_usd': total_value_inr / rate if rate > 0 else 0,
        'exchange_rate': rate,
    }


def get_dashboard_india_investments(db: Session) -> Dict[str, Any]:
    """
    Get India investments for dashboard (only Neel's accounts).
    """
    return get_all_india_investments(db, owner='Neel')

