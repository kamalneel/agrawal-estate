"""
Cash aggregation and management service.

Aggregates cash balances from:
1. Bank of America statements
2. Chase statements

NOTE: Brokerage cash (Robinhood, Schwab) is NOT included here because it's
already counted in Public Equity via portfolio_value in PortfolioSnapshots.
Including it here would double-count the cash.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.modules.cash.models import CashAccount, CashSnapshot, CashTransaction
from app.modules.investments.models import PortfolioSnapshot


# Source display names
SOURCE_DISPLAY = {
    'bank_of_america': 'Bank of America',
    'chase': 'Chase',
    'robinhood': 'Robinhood',
}

# Owner colors for UI
OWNER_COLORS = {
    'Neel': '#00A3FF',
    'Jaya': '#A855F7',
    'Joint': '#00D632',
}


def get_robinhood_cash_balances(db: Session) -> List[Dict[str, Any]]:
    """
    Get cash balances from Robinhood accounts.
    Uses the latest PortfolioSnapshot for each account.
    Only includes brokerage accounts (401k cash doesn't count as liquid).
    
    NOTE: This function is NOT used in get_all_cash_balances() to avoid
    double-counting. Brokerage cash is already included in the Public Equity
    total via portfolio_value. This function is kept for reference/debugging.
    """
    # Get the latest snapshot for each brokerage account
    subquery = db.query(
        PortfolioSnapshot.account_id,
        func.max(PortfolioSnapshot.statement_date).label('max_date')
    ).filter(
        PortfolioSnapshot.source == 'robinhood',
        PortfolioSnapshot.account_type.in_(['brokerage', 'individual', None])  # Exclude retirement accounts
    ).group_by(PortfolioSnapshot.account_id).subquery()
    
    snapshots = db.query(PortfolioSnapshot).join(
        subquery,
        (PortfolioSnapshot.account_id == subquery.c.account_id) &
        (PortfolioSnapshot.statement_date == subquery.c.max_date)
    ).filter(
        PortfolioSnapshot.source == 'robinhood',
        PortfolioSnapshot.cash_balance.isnot(None),
        PortfolioSnapshot.cash_balance > 0
    ).all()
    
    results = []
    for snap in snapshots:
        results.append({
            'source': 'robinhood',
            'source_display': SOURCE_DISPLAY.get('robinhood', 'Robinhood'),
            'account_id': snap.account_id,
            'account_name': f"Robinhood {snap.owner or 'Account'}",
            'account_type': 'brokerage',
            'owner': snap.owner or 'Unknown',
            'balance': float(snap.cash_balance) if snap.cash_balance else 0,
            'as_of_date': snap.statement_date.isoformat() if snap.statement_date else None,
        })
    
    return results


def get_bank_cash_balances(db: Session) -> List[Dict[str, Any]]:
    """
    Get cash balances from bank accounts (Bank of America, Chase).
    Uses the latest CashSnapshot for each account.
    """
    # Get the latest snapshot for each bank account
    subquery = db.query(
        CashSnapshot.source,
        CashSnapshot.account_id,
        func.max(CashSnapshot.snapshot_date).label('max_date')
    ).filter(
        CashSnapshot.source.in_(['bank_of_america', 'chase'])
    ).group_by(
        CashSnapshot.source,
        CashSnapshot.account_id
    ).subquery()
    
    snapshots = db.query(CashSnapshot).join(
        subquery,
        (CashSnapshot.source == subquery.c.source) &
        (CashSnapshot.account_id == subquery.c.account_id) &
        (CashSnapshot.snapshot_date == subquery.c.max_date)
    ).all()
    
    results = []
    for snap in snapshots:
        results.append({
            'source': snap.source,
            'source_display': SOURCE_DISPLAY.get(snap.source, snap.source.title()),
            'account_id': snap.account_id,
            'account_name': f"{SOURCE_DISPLAY.get(snap.source, snap.source)} {snap.account_type or 'Account'}".title(),
            'account_type': snap.account_type or 'checking',
            'owner': snap.owner or 'Joint',
            'balance': float(snap.balance) if snap.balance else 0,
            'as_of_date': snap.snapshot_date.isoformat() if snap.snapshot_date else None,
        })
    
    return results


def get_all_cash_balances(db: Session) -> Dict[str, Any]:
    """
    Get all cash balances from all sources.
    Returns aggregated data for the Cash dashboard.
    
    NOTE: We only include BANK cash here (Bank of America, Chase).
    Brokerage cash (Robinhood, Schwab) is NOT included because it's already
    counted in the Public Equity total via portfolio_value from PortfolioSnapshots.
    Including it here would result in double-counting.
    """
    # Get bank cash only - brokerage cash is already in Public Equity
    bank_cash = get_bank_cash_balances(db)
    
    # All accounts = bank accounts only
    all_accounts = bank_cash
    
    # Calculate totals
    total_cash = sum(acc['balance'] for acc in all_accounts)
    
    # Group by source
    by_source = {}
    for acc in all_accounts:
        source = acc['source']
        if source not in by_source:
            by_source[source] = {
                'display_name': acc['source_display'],
                'total': 0,
                'accounts': []
            }
        by_source[source]['total'] += acc['balance']
        by_source[source]['accounts'].append(acc)
    
    # Group by owner
    by_owner = {}
    for acc in all_accounts:
        owner = acc['owner']
        if owner not in by_owner:
            by_owner[owner] = {
                'total': 0,
                'color': OWNER_COLORS.get(owner, '#808080'),
                'accounts': []
            }
        by_owner[owner]['total'] += acc['balance']
        by_owner[owner]['accounts'].append(acc)
    
    return {
        'total_cash': total_cash,
        'account_count': len(all_accounts),
        'accounts': all_accounts,
        'by_source': by_source,
        'by_owner': by_owner,
    }


def get_cash_history(db: Session, months: int = 12) -> List[Dict[str, Any]]:
    """
    Get cash balance history over time.
    Combines data from CashSnapshots and PortfolioSnapshots.
    """
    from datetime import timedelta
    from dateutil.relativedelta import relativedelta
    
    # Calculate start date
    end_date = date.today()
    start_date = end_date - relativedelta(months=months)
    
    history = []
    
    # Get bank cash history
    bank_snapshots = db.query(
        CashSnapshot.snapshot_date,
        func.sum(CashSnapshot.balance).label('total')
    ).filter(
        CashSnapshot.snapshot_date >= start_date
    ).group_by(
        CashSnapshot.snapshot_date
    ).order_by(
        CashSnapshot.snapshot_date
    ).all()
    
    # Get Robinhood cash history (from PortfolioSnapshots)
    robinhood_snapshots = db.query(
        PortfolioSnapshot.statement_date,
        func.sum(PortfolioSnapshot.cash_balance).label('total')
    ).filter(
        PortfolioSnapshot.source == 'robinhood',
        PortfolioSnapshot.statement_date >= start_date,
        PortfolioSnapshot.account_type.in_(['brokerage', 'individual', None]),
        PortfolioSnapshot.cash_balance.isnot(None)
    ).group_by(
        PortfolioSnapshot.statement_date
    ).order_by(
        PortfolioSnapshot.statement_date
    ).all()
    
    # Combine by date (using month granularity)
    monthly_totals = {}
    
    for snap in bank_snapshots:
        month_key = snap.snapshot_date.strftime('%Y-%m')
        if month_key not in monthly_totals:
            monthly_totals[month_key] = {'bank': 0, 'robinhood': 0}
        monthly_totals[month_key]['bank'] = float(snap.total or 0)
    
    for snap in robinhood_snapshots:
        month_key = snap.statement_date.strftime('%Y-%m')
        if month_key not in monthly_totals:
            monthly_totals[month_key] = {'bank': 0, 'robinhood': 0}
        monthly_totals[month_key]['robinhood'] = float(snap.total or 0)
    
    # Format for chart
    for month_key in sorted(monthly_totals.keys()):
        data = monthly_totals[month_key]
        total = data['bank'] + data['robinhood']
        
        # Parse month for display
        year, month = month_key.split('-')
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        formatted = f"{month_names[int(month) - 1]} {year}"
        
        history.append({
            'month': month_key,
            'formatted': formatted,
            'value': total,
            'bank': data['bank'],
            'robinhood': data['robinhood'],
            'year': int(year),
        })
    
    return history


def upsert_cash_account(
    db: Session,
    source: str,
    account_id: str,
    owner: str,
    account_type: str = 'checking',
    account_name: Optional[str] = None,
    current_balance: Optional[Decimal] = None,
) -> CashAccount:
    """Create or update a cash account."""
    existing = db.query(CashAccount).filter(
        CashAccount.source == source,
        CashAccount.account_id == account_id
    ).first()
    
    if existing:
        existing.owner = owner
        existing.account_type = account_type
        if account_name:
            existing.account_name = account_name
        if current_balance is not None:
            existing.current_balance = current_balance
        existing.last_updated = datetime.utcnow()
        return existing
    else:
        account = CashAccount(
            source=source,
            account_id=account_id,
            owner=owner,
            account_type=account_type,
            account_name=account_name or f"{source.title()} {account_type.title()}",
            current_balance=current_balance,
            is_active='Y'
        )
        db.add(account)
        return account


def add_cash_snapshot(
    db: Session,
    source: str,
    account_id: str,
    snapshot_date: date,
    balance: Decimal,
    owner: Optional[str] = None,
    account_type: Optional[str] = None,
    ingestion_id: Optional[int] = None,
) -> CashSnapshot:
    """Add a cash balance snapshot."""
    # Check for existing snapshot on same date
    existing = db.query(CashSnapshot).filter(
        CashSnapshot.source == source,
        CashSnapshot.account_id == account_id,
        CashSnapshot.snapshot_date == snapshot_date
    ).first()
    
    if existing:
        existing.balance = balance
        if owner:
            existing.owner = owner
        if account_type:
            existing.account_type = account_type
        return existing
    else:
        snapshot = CashSnapshot(
            source=source,
            account_id=account_id,
            snapshot_date=snapshot_date,
            balance=balance,
            owner=owner,
            account_type=account_type,
            ingestion_id=ingestion_id,
        )
        db.add(snapshot)
        return snapshot



