"""
Investment holdings calculation and management service.

This service provides:
1. Manual holdings management (create, update, delete)
2. Holdings aggregation by owner/account type
3. Current position tracking
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.modules.investments.models import (
    InvestmentAccount,
    InvestmentHolding,
    InvestmentTransaction,
)


# Account type mapping for display
ACCOUNT_TYPE_DISPLAY = {
    'brokerage': 'Brokerage Account',
    'individual': 'Brokerage Account',
    'retirement': 'Retirement Account',
    '401k': 'Retirement Account',
    'ira': 'IRA Account',
    'roth_ira': 'Roth IRA Account',
    'hsa': 'Health Savings Account',
}

# Owner color mapping for UI
OWNER_COLORS = {
    'Neel': '#00D632',
    'Jaya': '#A855F7',
    'Alisha': '#808080',
    'Family': '#FF5A5A',
}

# Account display order - defines the order accounts appear in the UI
# Lower number = shown first
ACCOUNT_ORDER = {
    # Neel's accounts first
    'neel_brokerage': 1,
    'neel_retirement': 2,
    'neel_roth_ira': 3,
    # Jaya's accounts next
    'jaya_brokerage': 4,
    'jaya_ira': 5,
    'jaya_roth_ira': 6,
    # Alisha's accounts
    'alisha_brokerage': 7,
    'alisha_ira': 8,
    'alisha_roth_ira': 9,
    # Family accounts last
    'family_hsa': 10,
}

def get_account_sort_key(account_id: str) -> int:
    """Get sort key for account ordering."""
    return ACCOUNT_ORDER.get(account_id, 99)  # Unknown accounts go to end


def get_or_create_account(
    db: Session,
    owner: str,
    account_type: str,
    source: str = 'manual'
) -> InvestmentAccount:
    """Get or create an investment account."""
    # Create a unique account_id from owner and type
    account_id = f"{owner.lower()}_{account_type.lower()}"
    
    account = db.query(InvestmentAccount).filter(
        InvestmentAccount.source == source,
        InvestmentAccount.account_id == account_id
    ).first()
    
    if not account:
        account = InvestmentAccount(
            source=source,
            account_id=account_id,
            account_name=f"{owner}'s {account_type.title()}",
            account_type=account_type,
            is_active='Y'
        )
        db.add(account)
        db.flush()
    
    return account


def upsert_holding(
    db: Session,
    owner: str,
    account_type: str,
    symbol: str,
    quantity: Decimal,
    cost_basis: Optional[Decimal] = None,
    current_price: Optional[Decimal] = None,
    description: Optional[str] = None,
    source: str = 'manual'
) -> InvestmentHolding:
    """
    Create or update a holding position.
    
    Args:
        db: Database session
        owner: Owner name (Neel, Jaya, Family)
        account_type: Account type (brokerage, retirement, ira, hsa)
        symbol: Stock/ETF symbol
        quantity: Number of shares
        cost_basis: Total cost basis (optional)
        current_price: Current price per share (optional)
        description: Security description (optional)
        source: Data source (default: 'manual')
    
    Returns:
        The created or updated InvestmentHolding
    """
    # Ensure account exists
    account = get_or_create_account(db, owner, account_type, source)
    account_id = account.account_id
    
    # Check if holding exists
    existing = db.query(InvestmentHolding).filter(
        InvestmentHolding.source == source,
        InvestmentHolding.account_id == account_id,
        InvestmentHolding.symbol == symbol.upper()
    ).first()
    
    market_value = None
    if current_price and quantity:
        market_value = Decimal(str(current_price)) * Decimal(str(quantity))
    
    if existing:
        # Update existing holding
        existing.quantity = Decimal(str(quantity))
        if cost_basis is not None:
            existing.cost_basis = Decimal(str(cost_basis))
        if current_price is not None:
            existing.current_price = Decimal(str(current_price))
        if market_value is not None:
            existing.market_value = market_value
        if description:
            existing.description = description
        existing.last_updated = datetime.utcnow()
        return existing
    else:
        # Create new holding
        holding = InvestmentHolding(
            source=source,
            account_id=account_id,
            symbol=symbol.upper(),
            quantity=Decimal(str(quantity)),
            cost_basis=Decimal(str(cost_basis)) if cost_basis else None,
            current_price=Decimal(str(current_price)) if current_price else None,
            market_value=market_value,
            description=description,
            last_updated=datetime.utcnow(),
        )
        db.add(holding)
        return holding


def delete_holding(
    db: Session,
    owner: str,
    account_type: str,
    symbol: str,
    source: str = 'manual'
) -> bool:
    """Delete a holding position. Returns True if deleted."""
    account_id = f"{owner.lower()}_{account_type.lower()}"
    
    result = db.query(InvestmentHolding).filter(
        InvestmentHolding.source == source,
        InvestmentHolding.account_id == account_id,
        InvestmentHolding.symbol == symbol.upper()
    ).delete()
    
    return result > 0


def get_all_holdings(db: Session) -> List[Dict[str, Any]]:
    """
    Get all holdings grouped by account.
    
    Returns a list of accounts with their holdings.
    Also includes cash-only accounts by checking portfolio snapshots.
    """
    from app.modules.investments.models import PortfolioSnapshot
    
    # Get all active accounts
    accounts = db.query(InvestmentAccount).filter(
        InvestmentAccount.is_active == 'Y'
    ).all()
    
    result = []
    
    for account in accounts:
        # Get holdings for this account
        holdings = db.query(InvestmentHolding).filter(
            InvestmentHolding.source == account.source,
            InvestmentHolding.account_id == account.account_id,
            InvestmentHolding.quantity > 0
        ).order_by(InvestmentHolding.market_value.desc().nullslast()).all()
        
        # Get latest portfolio snapshot for total value (includes cash)
        latest_snapshot = db.query(PortfolioSnapshot).filter(
            PortfolioSnapshot.account_id == account.account_id
        ).order_by(PortfolioSnapshot.statement_date.desc()).first()
        
        # Parse owner from account_id
        parts = account.account_id.split('_')
        owner = parts[0].title() if parts else 'Unknown'
        account_type = '_'.join(parts[1:]) if len(parts) > 1 else 'brokerage'
        
        # Calculate holdings value
        holdings_value = sum(
            float(h.market_value) if h.market_value else 0
            for h in holdings
        )
        
        # Use portfolio snapshot value if higher (includes cash)
        # Or use holdings value if no snapshot
        snapshot_value = float(latest_snapshot.portfolio_value) if latest_snapshot and latest_snapshot.portfolio_value else 0
        total_value = max(holdings_value, snapshot_value)
        
        # Skip if no value at all
        if total_value == 0 and not holdings:
            continue
        
        holdings_data = []
        for h in holdings:
            qty = float(h.quantity) if h.quantity else 0
            price = float(h.current_price) if h.current_price else 0
            value = float(h.market_value) if h.market_value else qty * price
            pct = (value / total_value * 100) if total_value > 0 else 0
            
            holdings_data.append({
                'symbol': h.symbol,
                'name': h.description or h.symbol,
                'shares': qty,
                'currentPrice': price,
                'totalValue': value,
                'percentOfPortfolio': round(pct, 2),
                'costBasis': float(h.cost_basis) if h.cost_basis else None,
            })
        
        # Add cash as a pseudo-holding if there's a difference
        cash_value = snapshot_value - holdings_value
        if cash_value > 100:  # Only show if significant
            holdings_data.append({
                'symbol': 'CASH',
                'name': 'Cash & Cash Equivalents',
                'shares': cash_value,
                'currentPrice': 1.0,
                'totalValue': cash_value,
                'percentOfPortfolio': round((cash_value / total_value * 100) if total_value > 0 else 0, 2),
                'costBasis': None,
            })
        
        # Get last update timestamp from latest snapshot
        last_updated = None
        if latest_snapshot:
            last_updated = latest_snapshot.statement_date.isoformat() if latest_snapshot.statement_date else None
        
        result.append({
            'id': account.account_id,
            'name': account.account_name or f"{owner}'s {account_type.title()}",
            'owner': owner,
            'type': account_type,
            'value': total_value,
            'holdings': holdings_data,
            'color': OWNER_COLORS.get(owner, '#808080'),
            'last_updated': last_updated,
            'source': account.source,
        })
    
    # Sort accounts by defined order (Neel → Jaya → Alisha → Family)
    result.sort(key=lambda x: get_account_sort_key(x['id']))
    
    return result


def get_holdings_by_owner(db: Session, owner: str) -> List[Dict[str, Any]]:
    """Get all holdings for a specific owner."""
    all_holdings = get_all_holdings(db)
    return [h for h in all_holdings if h['owner'].lower() == owner.lower()]


def get_holdings_summary(db: Session) -> Dict[str, Any]:
    """Get a summary of all holdings."""
    all_holdings = get_all_holdings(db)
    
    total_value = sum(acc['value'] for acc in all_holdings)
    
    # Group by owner
    by_owner = {}
    for acc in all_holdings:
        owner = acc['owner']
        if owner not in by_owner:
            by_owner[owner] = {'value': 0, 'accounts': 0}
        by_owner[owner]['value'] += acc['value']
        by_owner[owner]['accounts'] += 1
    
    # Group by account type
    by_type = {}
    for acc in all_holdings:
        acc_type = acc['type']
        if acc_type not in by_type:
            by_type[acc_type] = {'value': 0, 'accounts': 0}
        by_type[acc_type]['value'] += acc['value']
        by_type[acc_type]['accounts'] += 1
    
    return {
        'totalValue': total_value,
        'accountCount': len(all_holdings),
        'byOwner': by_owner,
        'byType': by_type,
    }


# Note: The parse_robinhood_holdings_text function has been removed.
# Use the unified parser at app.ingestion.robinhood_unified_parser instead.


def bulk_import_holdings(
    db: Session,
    holdings_data: List[Dict[str, Any]],
    source: str = 'manual'
) -> Dict[str, int]:
    """
    Bulk import holdings from a list of dictionaries.
    
    Each dict should have: owner, account_type, symbol, quantity
    Optional: cost_basis, current_price, description
    
    Returns stats on created/updated records.
    """
    stats = {'created': 0, 'updated': 0, 'errors': 0}
    
    for item in holdings_data:
        try:
            # Check if holding already exists
            owner = item['owner']
            account_type = item['account_type']
            symbol = item['symbol']
            account_id = f"{owner.lower()}_{account_type.lower()}"
            
            existing = db.query(InvestmentHolding).filter(
                InvestmentHolding.source == source,
                InvestmentHolding.account_id == account_id,
                InvestmentHolding.symbol == symbol.upper()
            ).first()
            
            upsert_holding(
                db=db,
                owner=owner,
                account_type=account_type,
                symbol=symbol,
                quantity=item['quantity'],
                cost_basis=item.get('cost_basis'),
                current_price=item.get('current_price'),
                description=item.get('description'),
                source=source
            )
            
            if existing:
                stats['updated'] += 1
            else:
                stats['created'] += 1
                
        except Exception as e:
            stats['errors'] += 1
    
    db.commit()
    return stats


def calculate_cost_basis_from_transactions(
    db: Session,
    account_id: str,
    symbol: str,
    source: Optional[str] = None
) -> Optional[Decimal]:
    """
    Calculate cost basis for a holding from transaction history using weighted average method.
    
    This function:
    - Retrieves all BUY and SELL transactions for the symbol in the account
    - Uses weighted average method (most common for tax reporting)
    - Returns the total cost basis for the current holding quantity
    
    Args:
        db: Database session
        account_id: Account ID (e.g., 'neel_brokerage')
        symbol: Stock symbol (e.g., 'AAPL')
        source: Optional source filter (e.g., 'robinhood')
    
    Returns:
        Total cost basis as Decimal, or None if no transactions found
    """
    # Build query for BUY and SELL transactions
    query = db.query(InvestmentTransaction).filter(
        InvestmentTransaction.account_id == account_id,
        InvestmentTransaction.symbol == symbol.upper(),
        InvestmentTransaction.transaction_type.in_(['BUY', 'SELL'])
    ).order_by(InvestmentTransaction.transaction_date, InvestmentTransaction.id)
    
    if source:
        query = query.filter(InvestmentTransaction.source == source)
    
    transactions = query.all()
    
    if not transactions:
        return None
    
    # Weighted average calculation
    # Track: total_cost (cumulative cost basis), total_quantity (cumulative shares)
    total_cost = Decimal('0')
    total_quantity = Decimal('0')
    
    for txn in transactions:
        if not txn.quantity or txn.quantity <= 0:
            continue
        
        qty = Decimal(str(txn.quantity))
        txn_amount = Decimal(str(txn.amount)) if txn.amount else Decimal('0')
        fees = Decimal(str(txn.fees)) if txn.fees else Decimal('0')
        
        if txn.transaction_type == 'BUY':
            # Add shares and cost
            total_cost += txn_amount + fees  # Total cost includes fees
            total_quantity += qty
        elif txn.transaction_type == 'SELL':
            # Reduce quantity proportionally
            # In weighted average, selling doesn't change the average cost per share
            # It just reduces the quantity held
            if total_quantity > 0:
                # Calculate average cost per share before the sell
                avg_cost_per_share = total_cost / total_quantity
                
                # Reduce quantity
                total_quantity -= qty
                
                # Adjust cost basis proportionally
                # Remaining cost basis = remaining shares × average cost per share
                total_cost = avg_cost_per_share * total_quantity
                
                # Don't allow negative quantities (shouldn't happen with proper data)
                if total_quantity < 0:
                    total_quantity = Decimal('0')
                    total_cost = Decimal('0')
    
    # Return the remaining cost basis
    return total_cost if total_quantity > 0 else Decimal('0')


def recalculate_all_cost_bases(db: Session, source: Optional[str] = None) -> Dict[str, Any]:
    """
    Recalculate cost basis for all holdings based on transaction history.
    
    This updates the cost_basis field in InvestmentHolding records by calculating
    from transaction history using weighted average method.
    
    Args:
        db: Database session
        source: Optional source filter (e.g., 'robinhood'). If None, processes all holdings.
    
    Returns:
        Dictionary with stats about the operation:
        - holdings_processed: Number of holdings processed
        - holdings_updated: Number of holdings with cost basis updated
        - holdings_no_transactions: Number of holdings with no transaction history
        - holdings_no_change: Number of holdings where cost basis didn't change
        - errors: List of errors encountered
    """
    stats = {
        'holdings_processed': 0,
        'holdings_updated': 0,
        'holdings_no_transactions': 0,
        'holdings_no_change': 0,
        'errors': []
    }
    
    # Get all holdings
    query = db.query(InvestmentHolding).filter(InvestmentHolding.quantity > 0)
    if source:
        query = query.filter(InvestmentHolding.source == source)
    
    holdings = query.all()
    
    for holding in holdings:
        try:
            stats['holdings_processed'] += 1
            
            # Calculate cost basis from transactions
            calculated_cost_basis = calculate_cost_basis_from_transactions(
                db=db,
                account_id=holding.account_id,
                symbol=holding.symbol,
                source=holding.source
            )
            
            if calculated_cost_basis is None:
                stats['holdings_no_transactions'] += 1
                continue
            
            # Compare with existing cost basis
            existing_cost_basis = Decimal(str(holding.cost_basis)) if holding.cost_basis else None
            
            # Update if different (allow for small rounding differences)
            if existing_cost_basis is None or abs(calculated_cost_basis - existing_cost_basis) > Decimal('0.01'):
                holding.cost_basis = calculated_cost_basis
                stats['holdings_updated'] += 1
            else:
                stats['holdings_no_change'] += 1
                
        except Exception as e:
            error_msg = f"Error processing {holding.symbol} in {holding.account_id}: {str(e)}"
            stats['errors'].append(error_msg)
    
    db.commit()
    return stats








