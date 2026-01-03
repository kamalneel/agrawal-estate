"""
Ingestion services for saving parsed records to the database.
"""

from typing import Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.ingestion.parsers.base import ParsedRecord, RecordType
from app.shared.models.ingestion import IngestionLog


def create_ingestion_log(
    db: Session,
    file_name: str,
    file_path: str,
    source: str,
    module: str,
) -> IngestionLog:
    """Create a new ingestion log entry."""
    log = IngestionLog(
        file_name=file_name,
        file_path=file_path,
        source=source,
        module=module,
        status="processing",
        started_at=datetime.utcnow(),
    )
    db.add(log)
    db.flush()
    return log


def complete_ingestion_log(
    db: Session,
    log: IngestionLog,
    status: str,
    records_created: int = 0,
    records_updated: int = 0,
    records_skipped: int = 0,
    error_message: Optional[str] = None,
):
    """Update ingestion log with completion status."""
    log.status = status
    log.records_created = records_created
    log.records_updated = records_updated
    log.records_skipped = records_skipped
    log.error_message = error_message
    log.completed_at = datetime.utcnow()
    db.flush()


def save_records(db: Session, records: list, ingestion_id: Optional[int] = None) -> dict:
    """
    Save parsed records to the database.
    Returns dict with created, updated, skipped counts.
    """
    from app.modules.investments.models import InvestmentTransaction, InvestmentHolding, InvestmentAccount
    from app.modules.cash.models import CashTransaction, CashAccount
    
    created = 0
    updated = 0
    skipped = 0
    has_sto_transactions = False
    
    for record in records:
        try:
            if record.record_type == RecordType.TRANSACTION:
                result = save_investment_transaction(db, record, ingestion_id)
                # Check if this is an STO transaction (for auto-update trigger)
                if record.data.get("transaction_type") == "STO":
                    has_sto_transactions = True
            elif record.record_type == RecordType.DIVIDEND:
                # Dividends are also transactions, save them the same way
                result = save_investment_transaction(db, record, ingestion_id)
            elif record.record_type == RecordType.HOLDING:
                result = save_investment_holding(db, record, ingestion_id)
            elif record.record_type == RecordType.CASH_SNAPSHOT:
                result = save_cash_transaction(db, record, ingestion_id)
            elif record.record_type == RecordType.TAX_RECORD:
                result = save_tax_return(db, record, ingestion_id)
            elif record.record_type == RecordType.ACCOUNT_SUMMARY:
                result = save_portfolio_snapshot(db, record, ingestion_id)
            else:
                skipped += 1
                continue
            
            if result == "created":
                created += 1
            elif result == "updated":
                updated += 1
            else:
                skipped += 1
                
        except Exception as e:
            print(f"Error saving record: {e}")
            skipped += 1
    
    # Auto-update premium settings if we have new STO transactions
    if has_sto_transactions:
        try:
            from app.modules.strategies.services import update_premium_settings_from_averages
            update_result = update_premium_settings_from_averages(db, weeks=4, min_transactions=1)
            # Don't commit here - let the caller commit after reviewing results
            print(f"Auto-updated premium settings: {update_result['updated']} symbols updated, {update_result['skipped']} skipped")
        except Exception as e:
            print(f"Error auto-updating premium settings: {e}")
            # Don't fail the ingestion if auto-update fails
    
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }


def update_holding_from_transaction(
    db: Session, 
    account_id: str, 
    source: str,
    symbol: str, 
    transaction_type: str, 
    quantity: Optional[float],
    price_per_share: Optional[float],
    transaction_date
) -> None:
    """
    Update holdings based on a transaction.
    
    - BUY: Increase quantity
    - SELL: Decrease quantity
    - OASGN (Option Assignment): Can result in buying/selling shares
    - Other types (dividends, transfers, options premiums): Don't affect share count
    
    This keeps holdings in sync with transactions throughout the month.
    End-of-month statements will serve as authoritative snapshots.
    """
    from app.modules.investments.models import InvestmentHolding, InvestmentAccount
    
    # Only process transactions that affect share holdings
    # Skip if no symbol (cash transactions, IRA contributions, etc.)
    if not symbol or symbol in ("", "CASH", "UNKNOWN"):
        return
    
    # Skip options contracts (they have symbols like "HOOD 12/5/2025 Put $120.00")
    if any(x in symbol for x in [" PUT ", " CALL ", "PUT $", "CALL $", "/"]):
        return
    
    # Determine quantity change based on transaction type
    quantity_change = 0.0
    if quantity is not None:
        if transaction_type == "BUY":
            quantity_change = float(quantity)
        elif transaction_type == "SELL":
            quantity_change = -float(quantity)
        elif transaction_type == "OASGN":
            # Option assignment - usually results in buying shares (put assignment)
            # The quantity in the transaction should reflect shares, not contracts
            quantity_change = float(quantity) * 100  # 1 contract = 100 shares
        elif transaction_type == "SPLIT":
            # Stock splits change quantity but are handled differently
            # For now, we'll skip and let statement snapshots handle it
            return
    
    if quantity_change == 0:
        return
    
    # Get or create the holding record
    existing_holding = db.query(InvestmentHolding).filter(
        InvestmentHolding.account_id == account_id,
        InvestmentHolding.symbol == symbol,
    ).first()
    
    if existing_holding:
        # Update existing holding
        old_quantity = float(existing_holding.quantity or 0)
        new_quantity = old_quantity + quantity_change
        
        # Don't allow negative quantities (shouldn't happen, but safety check)
        if new_quantity < 0:
            new_quantity = 0
        
        existing_holding.quantity = new_quantity
        
        # Update price if we have it
        if price_per_share:
            existing_holding.current_price = float(price_per_share)
            existing_holding.market_value = new_quantity * float(price_per_share)
        
        existing_holding.last_updated = transaction_date
    else:
        # Create new holding (only for buys, not sells)
        if quantity_change > 0:
            # Look up account to get source
            account = db.query(InvestmentAccount).filter(
                InvestmentAccount.account_id == account_id,
            ).first()
            
            holding = InvestmentHolding(
                source=source,
                account_id=account_id,
                symbol=symbol,
                quantity=quantity_change,
                current_price=float(price_per_share) if price_per_share else None,
                market_value=quantity_change * float(price_per_share) if price_per_share else None,
                last_updated=transaction_date,
            )
            db.add(holding)
    
    db.flush()


# Account ID mapping: Maps various account ID formats to canonical account IDs
# This ensures consistency and prevents duplicate accounts
ACCOUNT_ID_MAPPING = {
    # Robinhood variations → canonical IDs
    'robinhood_neel_individual': 'neel_brokerage',
    'robinhood_jaya_individual': 'jaya_brokerage',
    'robinhood_neel_retirement': 'neel_retirement',
    'robinhood_jaya_retirement': 'jaya_ira',
    'robinhood_alisha_individual': 'alisha_brokerage',
    'robinhood_default': 'neel_brokerage',
    # Handle variations without underscores (e.g., alishasbrokerage → alisha_brokerage)
    'alishasbrokerage': 'alisha_brokerage',
    'neelsbrokerage': 'neel_brokerage',
    'jayasbrokerage': 'jaya_brokerage',
    'neelsretirement': 'neel_retirement',
    'jayasira': 'jaya_ira',
    # Handle "neal" misspelling variations
    'neal_roth_ira': 'neel_roth_ira',
    'neal_brokerage': 'neel_brokerage',
    'neal_retirement': 'neel_retirement',
    'robinhood_neal_individual': 'neel_brokerage',
    'robinhood_neal_retirement': 'neel_retirement',
    # TD Ameritrade
    'neel_roth_ira_538': 'neel_retirement',
    'tda_roth_ira_347': 'neel_retirement',
    # Generic
    'generic': 'neel_brokerage',
}


def _normalize_account_id(account_id: str) -> str:
    """Normalize account_id using the mapping to ensure consistency."""
    account_id_lower = account_id.lower()
    # First check exact match
    if account_id_lower in ACCOUNT_ID_MAPPING:
        return ACCOUNT_ID_MAPPING[account_id_lower]
    
    # Handle "neal" misspelling - normalize to "neel"
    if 'neal' in account_id_lower and 'neel' not in account_id_lower:
        account_id_lower = account_id_lower.replace('neal', 'neel')
        if account_id_lower in ACCOUNT_ID_MAPPING:
            return ACCOUNT_ID_MAPPING[account_id_lower]
    
    # Check if it matches a pattern (e.g., robinhood_*_individual)
    for pattern, canonical in ACCOUNT_ID_MAPPING.items():
        if account_id_lower.startswith(pattern.split('_')[0] + '_') and pattern.endswith('_individual'):
            # Check if it's a robinhood_owner_individual pattern
            parts = account_id_lower.split('_')
            if len(parts) >= 3 and parts[0] == 'robinhood' and parts[2] == 'individual':
                return ACCOUNT_ID_MAPPING.get(pattern, account_id)
    
    return account_id_lower  # Return normalized version


def _generate_account_name(account_id: str, account_type: str) -> str:
    """Generate a proper account name from account_id and account_type.
    
    Examples:
    - 'neel_roth_ira' -> "Neel's Roth IRA"
    - 'jaya_brokerage' -> "Jaya's Brokerage"
    - 'alisha_ira' -> "Alisha's IRA"
    """
    # Normalize account_id first
    normalized_id = _normalize_account_id(account_id)
    account_id_lower = normalized_id.lower()
    
    # Extract owner name
    owners_map = {
        'neel': 'Neel',
        'neal': 'Neel',  # Handle misspelling
        'jaya': 'Jaya',
        'alisha': 'Alisha',
        'family': 'Family'
    }
    
    owner = None
    for key, value in owners_map.items():
        if key in account_id_lower:
            owner = value
            break
    
    if not owner:
        # Fallback: capitalize first part
        parts = account_id_lower.split('_')
        if parts:
            owner = parts[0].capitalize()
    
    # Generate account type display name
    type_display_map = {
        'roth_ira': 'Roth IRA',
        'ira': 'IRA',
        'retirement': 'Retirement',
        'brokerage': 'Brokerage',
        'individual': 'Brokerage',
        'investment': 'Brokerage',
        'hsa': 'HSA',
    }
    
    # Use provided account_type or infer from account_id
    if not account_type or account_type == 'brokerage':
        if 'roth' in account_id_lower:
            type_display = 'Roth IRA'
        elif 'ira' in account_id_lower:
            type_display = 'IRA'
        elif 'retirement' in account_id_lower:
            type_display = 'Retirement'
        else:
            type_display = type_display_map.get(account_type, 'Brokerage')
    else:
        type_display = type_display_map.get(account_type, account_type.replace('_', ' ').title())
    
    return f"{owner}'s {type_display}"


def _parse_owner_and_type_from_account_id(account_id: str) -> tuple[str, str]:
    """Extract owner and account_type from account_id like 'alisha_brokerage' -> ('alisha', 'brokerage')."""
    import re
    # First normalize the account_id using the mapping
    normalized_id = _normalize_account_id(account_id)
    account_id_lower = normalized_id.lower()
    
    # Known owners (handle both neel and neal)
    owners = ['neel', 'neal', 'jaya', 'alisha', 'family']
    owner = None
    account_type = 'brokerage'
    
    # Try to find owner in account_id
    for o in owners:
        if o in account_id_lower:
            # Normalize neal to neel
            owner = 'neel' if o == 'neal' else o
            # Remove owner name and common separators to get account type
            remaining = account_id_lower.replace(o, '').strip('_').strip()
            if remaining:
                # Map common variations
                if 'roth' in remaining:
                    account_type = 'roth_ira'
                elif 'ira' in remaining or 'retirement' in remaining:
                    account_type = 'ira' if 'roth' not in remaining else 'roth_ira'
                elif 'hsa' in remaining:
                    account_type = 'hsa'
                elif remaining in ['brokerage', 'individual', 'investment', 'primary']:
                    account_type = 'brokerage'
                else:
                    account_type = remaining
            break
    
    if not owner:
        # Fallback: try to extract from common patterns
        if 'default' in account_id_lower:
            owner = 'unknown'
        else:
            # Assume first part before underscore or first word is owner
            parts = re.split(r'[_\s]+', account_id_lower)
            if parts:
                owner = parts[0]
                if len(parts) > 1:
                    account_type = '_'.join(parts[1:])
    
    return owner or 'unknown', account_type


def save_investment_transaction(db: Session, record: ParsedRecord, ingestion_id: Optional[int] = None) -> str:
    """Save an investment transaction record and update holdings."""
    from app.modules.investments.models import InvestmentTransaction, InvestmentAccount
    import hashlib
    import json
    
    data = record.data
    source = data.get("source", "unknown")
    account_id_str = data.get("account_id", "default")
    
    # Normalize account_id using mapping to ensure consistency
    account_id_str = _normalize_account_id(account_id_str)
    
    # Ensure account exists (for reference, though not a foreign key)
    account = db.query(InvestmentAccount).filter(
        InvestmentAccount.account_id == account_id_str,
        InvestmentAccount.source == source,
    ).first()
    
    if not account:
        # Try to find existing account with same owner and account_type
        # This handles cases where account_id format differs (e.g., alisha_brokerage vs alishasbrokerage)
        owner, account_type = _parse_owner_and_type_from_account_id(account_id_str)
        
        # Look for existing account with same owner and account_type
        # Check both exact account_type and variations
        account_type_variants = [account_type]
        if account_type == 'brokerage':
            account_type_variants.extend(['individual', 'investment', 'primary'])
        elif account_type == 'ira':
            account_type_variants.extend(['retirement', 'traditional_ira'])
        
        existing_accounts = db.query(InvestmentAccount).filter(
            InvestmentAccount.source == source,
        ).all()
        
        # Check if any existing account matches owner and account_type
        for existing in existing_accounts:
            existing_owner, existing_type = _parse_owner_and_type_from_account_id(existing.account_id)
            if existing_owner == owner and existing_type in account_type_variants:
                # Use existing account instead of creating new one
                account = existing
                break
        
        # If still no account found, create new one
        if not account:
            # Generate proper account name
            account_name = data.get("account_name")
            if not account_name or account_name == account_id_str:
                account_name = _generate_account_name(account_id_str, account_type)
            
            # Ensure account_type is correct (especially for roth_ira)
            final_account_type = data.get("account_type") or account_type
            if 'roth' in account_id_str.lower() and final_account_type != 'roth_ira':
                final_account_type = 'roth_ira'
            
            account = InvestmentAccount(
                account_id=account_id_str,
                account_name=account_name,
                source=source,
                account_type=final_account_type,
            )
            db.add(account)
            db.flush()
    
    # Transaction uses denormalized string account_id, not foreign key
    transaction_date = data.get("transaction_date")
    symbol = data.get("symbol", "")
    transaction_type = data.get("transaction_type", "")
    quantity = data.get("quantity")
    amount = data.get("amount")
    price_per_share = data.get("price_per_share") or data.get("price")
    
    # Check for duplicate using the composite unique key fields
    existing = db.query(InvestmentTransaction).filter(
        InvestmentTransaction.source == source,
        InvestmentTransaction.account_id == account_id_str,
        InvestmentTransaction.transaction_date == transaction_date,
        InvestmentTransaction.symbol == symbol,
        InvestmentTransaction.transaction_type == transaction_type,
        InvestmentTransaction.quantity == quantity,
        InvestmentTransaction.amount == amount,
    ).first()
    
    if existing:
        return "skipped"
    
    # CROSS-ACCOUNT DEDUPLICATION: For sources like Robinhood where exports don't
    # include account info, also check if this transaction exists in ANY account
    # from the same source (to prevent duplicates when importing generic exports)
    # 
    # Handle symbol normalization: empty string and 'UNKNOWN' should be treated as equivalent
    from sqlalchemy import or_
    symbol_variants = [symbol]
    if symbol == "" or symbol == "UNKNOWN":
        symbol_variants = ["", "UNKNOWN"]
    
    cross_account_existing = db.query(InvestmentTransaction).filter(
        InvestmentTransaction.source == source,
        InvestmentTransaction.transaction_date == transaction_date,
        InvestmentTransaction.symbol.in_(symbol_variants),
        InvestmentTransaction.transaction_type == transaction_type,
        InvestmentTransaction.amount == amount,
    ).first()
    
    if cross_account_existing:
        # If the existing transaction is in a generic account (like "robinhood_default")
        # and we now have a specific account (like "jaya_ira"), update it
        generic_accounts = ["robinhood_default", "schwab_default", "fidelity_default", "default"]
        if cross_account_existing.account_id in generic_accounts and account_id_str not in generic_accounts:
            # Migrate to the specific account
            cross_account_existing.account_id = account_id_str
            db.flush()
            
            # NOTE: We intentionally DO NOT update holdings from transaction imports.
            # Holdings should ONLY come from the Robinhood paste (copy-paste from web UI),
            # which is the authoritative source for current positions.
            # Transaction CSVs are for income/expense tracking, not position quantities.
            # See: https://github.com/... (holdings duplication bug fix)
            
            return "updated"
        return "skipped"
    
    # Generate record hash for additional deduplication
    hash_data = f"{source}:{account_id_str}:{transaction_date}:{symbol}:{transaction_type}:{quantity}:{amount}"
    record_hash = hashlib.sha256(hash_data.encode()).hexdigest()
    
    # Create new transaction with explicit flush to catch duplicates immediately
    try:
        transaction = InvestmentTransaction(
            source=source,
            account_id=account_id_str,
            transaction_date=transaction_date,
            symbol=symbol,
            description=data.get("description"),
            transaction_type=transaction_type,
            quantity=quantity,
            price_per_share=price_per_share,
            amount=amount,
            fees=data.get("fees", 0),
            record_hash=record_hash,
            ingestion_id=ingestion_id,
        )
        db.add(transaction)
        db.flush()  # Flush immediately to catch unique constraint violations
        
        # NOTE: We intentionally DO NOT update holdings from transaction imports.
        # Holdings should ONLY come from the Robinhood paste (copy-paste from web UI),
        # which is the authoritative source for current positions.
        # Transaction CSVs are for income/expense tracking, not position quantities.
        # This prevents duplicate holdings when account_id inference differs between
        # paste and CSV import.
        
        return "created"
    except Exception as e:
        db.rollback()
        # Check if it's a unique constraint violation (duplicate)
        if "UniqueViolation" in str(type(e).__name__) or "unique constraint" in str(e).lower():
            return "skipped"
        raise


def save_investment_holding(db: Session, record: ParsedRecord, ingestion_id: Optional[int] = None) -> str:
    """Save an investment holding record."""
    from app.modules.investments.models import InvestmentHolding, InvestmentAccount
    
    data = record.data
    source = data.get("source", "unknown")
    account_name = data.get("account_name", "Unknown")
    
    # Generate account_id from data if provided, otherwise from account_name
    account_id_str = data.get("account_id") 
    if not account_id_str:
        # Generate account_id from owner and account_type
        owner = data.get("owner", "unknown").lower()
        account_type = data.get("account_type", "brokerage")
        account_id_str = f"{owner}_{account_type}"
    
    # Normalize account_id using mapping to ensure consistency
    account_id_str = _normalize_account_id(account_id_str)
    
    # Get or create account
    account = db.query(InvestmentAccount).filter(
        InvestmentAccount.account_id == account_id_str,
        InvestmentAccount.source == source,
    ).first()
    
    if not account:
        # Try to find existing account with same owner and account_type
        # This handles cases where account_id format differs (e.g., alisha_brokerage vs alishasbrokerage)
        owner, account_type = _parse_owner_and_type_from_account_id(account_id_str)
        
        # Look for existing account with same owner and account_type
        # Check both exact account_type and variations
        account_type_variants = [account_type]
        if account_type == 'brokerage':
            account_type_variants.extend(['individual', 'investment', 'primary'])
        elif account_type == 'ira':
            account_type_variants.extend(['retirement', 'traditional_ira'])
        
        existing_accounts = db.query(InvestmentAccount).filter(
            InvestmentAccount.source == source,
        ).all()
        
        # Check if any existing account matches owner and account_type
        for existing in existing_accounts:
            existing_owner, existing_type = _parse_owner_and_type_from_account_id(existing.account_id)
            if existing_owner == owner and existing_type in account_type_variants:
                # Use existing account instead of creating new one
                account = existing
                break
        
        # If still no account found, create new one
        if not account:
            # Generate proper account name if not provided
            if not account_name or account_name == "Unknown" or account_name == account_id_str:
                owner, inferred_type = _parse_owner_and_type_from_account_id(account_id_str)
                account_name = _generate_account_name(account_id_str, inferred_type)
            
            # Ensure account_type is correct
            final_account_type = data.get("account_type", account_type)
            if 'roth' in account_id_str.lower() and final_account_type != 'roth_ira':
                final_account_type = 'roth_ira'
            
            account = InvestmentAccount(
                account_id=account_id_str,
                account_name=account_name,
                source=source,
                account_type=final_account_type,
            )
            db.add(account)
            db.flush()
    
    # Check for existing holding with same symbol (use account_id varchar, not id integer)
    existing = db.query(InvestmentHolding).filter(
        InvestmentHolding.account_id == account.account_id,
        InvestmentHolding.symbol == data.get("symbol"),
    ).first()
    
    new_quantity = float(data.get("quantity") or 0)
    new_value = float(data.get("market_value") or 0)
    new_price = data.get("current_price")
    
    if existing:
        # AGGREGATE holdings with same symbol (don't overwrite!)
        # This handles cases where margin and cash positions are reported separately
        old_quantity = float(existing.quantity or 0)
        old_value = float(existing.market_value or 0)
        
        # If new data has significantly different quantity, it's likely a new batch
        # Check if this is an update (same timestamp) or aggregation (same processing batch)
        statement_date = data.get("as_of_date") or data.get("statement_date")
        
        # If the existing holding was updated today and quantities differ, aggregate
        # Otherwise, treat as a full replacement
        from datetime import datetime, timedelta
        is_same_batch = (
            existing.last_updated and 
            statement_date and
            existing.last_updated == statement_date
        )
        
        if is_same_batch and new_quantity != old_quantity:
            # Same statement date - aggregate the holdings (margin + cash)
            existing.quantity = old_quantity + new_quantity
            existing.market_value = old_value + new_value
            # Keep the price (should be the same for both lots)
            if new_price:
                existing.current_price = new_price
        else:
            # Different statement date or same quantities - replace with new data
            existing.quantity = new_quantity
            existing.market_value = new_value
            existing.current_price = new_price
            existing.last_updated = statement_date
        
        existing.cost_basis = data.get("average_cost") or data.get("cost_basis") or existing.cost_basis
        return "updated"
    
    # Create new holding
    holding = InvestmentHolding(
        source=source,
        account_id=account.account_id,  # Use the varchar account_id
        symbol=data.get("symbol"),
        description=data.get("description") or data.get("name"),
        quantity=data.get("quantity"),
        cost_basis=data.get("average_cost") or data.get("cost_basis"),
        current_price=data.get("current_price"),
        market_value=data.get("market_value"),
        last_updated=data.get("as_of_date") or data.get("statement_date"),
        ingestion_id=ingestion_id,
    )
    db.add(holding)
    return "created"


def save_cash_transaction(db: Session, record: ParsedRecord, ingestion_id: Optional[int] = None) -> str:
    """Save a cash/bank transaction record."""
    from app.modules.cash.models import CashTransaction, CashAccount
    
    data = record.data
    
    # Get or create bank account
    account = db.query(CashAccount).filter(
        CashAccount.account_name == data.get("account_name", "Unknown"),
        CashAccount.institution == data.get("institution", "unknown"),
    ).first()
    
    if not account:
        account = CashAccount(
            account_name=data.get("account_name", "Unknown"),
            institution=data.get("institution", "unknown"),
            account_type=data.get("account_type", "checking"),
        )
        db.add(account)
        db.flush()
    
    # Check for duplicate
    existing = db.query(CashTransaction).filter(
        CashTransaction.account_id == account.id,
        CashTransaction.transaction_date == data.get("transaction_date"),
        CashTransaction.description == data.get("description"),
        CashTransaction.amount == data.get("amount"),
    ).first()
    
    if existing:
        return "skipped"
    
    # Create new transaction
    transaction = CashTransaction(
        account_id=account.id,
        transaction_date=data.get("transaction_date"),
        description=data.get("description"),
        amount=data.get("amount"),
        balance=data.get("balance"),
        transaction_type=data.get("transaction_type"),
        category=data.get("category"),
        ingestion_id=ingestion_id,
    )
    db.add(transaction)
    return "created"


def save_tax_return(db: Session, record: ParsedRecord, ingestion_id: Optional[int] = None) -> str:
    """Save a tax return record."""
    import json
    from app.modules.tax.models import IncomeTaxReturn
    
    data = record.data
    year = data.get("year")
    
    if not year:
        return "skipped"
    
    # Prepare details JSON
    details = data.get("details", {})
    details_json = json.dumps(details) if details else None
    
    # Check for existing record for this year
    existing = db.query(IncomeTaxReturn).filter(
        IncomeTaxReturn.tax_year == year
    ).first()
    
    if existing:
        # Update existing record if new data is better
        if data.get("agi") and (not existing.agi or existing.agi == 0):
            existing.agi = data.get("agi")
        if data.get("federal_tax") and (not existing.federal_tax or existing.federal_tax == 0):
            existing.federal_tax = data.get("federal_tax")
        if data.get("state_tax") and (not existing.state_tax or existing.state_tax == 0):
            existing.state_tax = data.get("state_tax")
        if data.get("effective_rate"):
            existing.effective_rate = data.get("effective_rate")
        if data.get("source_file"):
            existing.source_file = data.get("source_file")
        # Always update details_json if we have new details
        if details_json:
            existing.details_json = details_json
        return "updated"
    
    # Create new record
    tax_return = IncomeTaxReturn(
        tax_year=year,
        agi=data.get("agi", 0),
        federal_tax=data.get("federal_tax", 0),
        federal_withheld=data.get("federal_withheld"),
        federal_owed=data.get("federal_owed"),
        federal_refund=data.get("federal_refund"),
        state_tax=data.get("state_tax", 0),
        state_withheld=data.get("state_withheld"),
        state_owed=data.get("state_owed"),
        state_refund=data.get("state_refund"),
        effective_rate=data.get("effective_rate"),
        filing_status=data.get("filing_status"),
        source_file=data.get("source_file"),
        details_json=details_json,
        ingestion_id=ingestion_id,
    )
    db.add(tax_return)
    return "created"


def save_portfolio_snapshot(db: Session, record: ParsedRecord, ingestion_id: Optional[int] = None) -> str:
    """
    Save a portfolio snapshot record (from account statements).
    Uses upsert logic - updates if snapshot for same account/date exists.
    """
    from app.modules.investments.models import PortfolioSnapshot
    
    data = record.data
    
    source = data.get("source", "unknown")
    account_id = data.get("account_id", "unknown")
    statement_date = data.get("statement_date")
    portfolio_value = data.get("portfolio_value")
    
    if not statement_date or not portfolio_value:
        return "skipped"
    
    # Check for existing snapshot with same source, account_id, and date
    existing = db.query(PortfolioSnapshot).filter(
        PortfolioSnapshot.source == source,
        PortfolioSnapshot.account_id == account_id,
        PortfolioSnapshot.statement_date == statement_date,
    ).first()
    
    if existing:
        # Update existing snapshot if values changed
        if existing.portfolio_value != portfolio_value:
            existing.portfolio_value = portfolio_value
            existing.cash_balance = data.get("cash_balance")
            existing.securities_value = data.get("securities_value")
            existing.owner = data.get("owner")
            existing.account_type = data.get("account_type")
            return "updated"
        return "skipped"  # Same values, no update needed
    
    # Create new snapshot
    snapshot = PortfolioSnapshot(
        source=source,
        account_id=account_id,
        owner=data.get("owner"),
        account_type=data.get("account_type"),
        statement_date=statement_date,
        portfolio_value=portfolio_value,
        cash_balance=data.get("cash_balance"),
        securities_value=data.get("securities_value"),
        ingestion_id=ingestion_id,
    )
    db.add(snapshot)
    return "created"



