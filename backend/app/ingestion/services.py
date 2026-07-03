"""
Ingestion services for saving parsed records to the database.

Uses HYBRID deduplication approach for transactions:
1. Find crossover point (max date in DB for each account)
2. Skip all rows before crossover (already imported)
3. For rows at/after crossover, use count-based logic to handle identical transactions
"""

from typing import Optional, List, Dict
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date
import hashlib

from decimal import Decimal

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


def _make_transaction_key(record_data: dict) -> str:
    """Create a unique key for a transaction based on business fields."""
    txn_date = record_data.get("transaction_date")
    if isinstance(txn_date, datetime):
        txn_date = txn_date.date()
    amount = record_data.get('amount')
    amount = float(amount) if amount is not None else 0.0
    return (
        f"{txn_date}|"
        f"{record_data.get('transaction_type', '')}|"
        f"{record_data.get('symbol', '')}|"
        f"{amount:.2f}|"
        f"{record_data.get('description', '')}"
    )


def _normalize_description(desc) -> str:
    """Normalize a transaction description for comparison: trim whitespace
    and render every dollar figure with two decimals ("$215" == "$215.00")."""
    import re
    if not desc:
        return ""
    return re.sub(r"\$(\d+(?:\.\d+)?)",
                  lambda m: f"${float(m.group(1)):.2f}",
                  desc.strip())


def _reconcile_fee_variant(db: Session, account_id: str, source: str,
                           data: dict, consumed_ids: set) -> Optional[str]:
    """Fee-tolerant dedup: find a DB row that is the same fill as `data` but
    recorded with a gross vs net-of-fees amount (MCP bridge vs official
    activity CSV). Keeps the SMALLER signed amount — fees only ever reduce
    cash, so the smaller value is the fee-inclusive official figure.

    Returns "updated" (existing row corrected to the new, net amount),
    "skipped" (existing row already has the better amount), or None (no
    fee-variant match; caller proceeds normally). consumed_ids guards
    one-to-one matching when a batch has identical rows.
    """
    from app.modules.investments.models import InvestmentTransaction

    txn_type = data.get("transaction_type", "")
    amount = data.get("amount")
    quantity = data.get("quantity")
    tolerance = _fee_tolerance(txn_type, quantity, amount)
    if not tolerance or amount is None:
        return None

    symbol = data.get("symbol", "")
    symbol_variants = ["", "UNKNOWN"] if symbol in ("", "UNKNOWN", None) else [symbol]
    candidates = db.query(InvestmentTransaction).filter(
        InvestmentTransaction.account_id == account_id,
        InvestmentTransaction.source == source,
        InvestmentTransaction.transaction_date == data.get("transaction_date"),
        InvestmentTransaction.transaction_type.in_(_get_equivalent_types(txn_type)),
        InvestmentTransaction.symbol.in_(symbol_variants),
        InvestmentTransaction.quantity == quantity,
    ).all()

    # Prefer the closest amount so an exact twin wins over a fee variant
    candidates.sort(key=lambda c: abs(float(c.amount) - float(amount)))

    desc = _normalize_description(data.get("description"))
    for candidate in candidates:
        if candidate.id in consumed_ids:
            continue
        # Same-day/same-premium option fills on different strikes exist; the
        # description carries the strike, so require it to match when both
        # sides have one. Normalized because sources format dollar values
        # differently ("$215" vs "$215.00").
        cand_desc = _normalize_description(candidate.description)
        if txn_type in _OPTION_TRADE_TYPES and desc and cand_desc and cand_desc != desc:
            continue
        diff = abs(float(candidate.amount) - float(amount))
        if diff < 0.005:
            # Equal amounts: the exact-dup counting upstream compares raw
            # descriptions, so it already accounts for rows whose raw
            # description matches too (identical fills must still import
            # as separate rows). Only claim the row when the descriptions
            # differ merely in format ("$215" vs "$215.00").
            if ((candidate.description or "").strip()
                    == (data.get("description") or "").strip()):
                continue
            consumed_ids.add(candidate.id)
            return "skipped"
        if diff <= tolerance:
            consumed_ids.add(candidate.id)
            if float(amount) < float(candidate.amount):
                candidate.amount = amount
                return "updated"
            return "skipped"
    return None


def save_investment_transactions_hybrid(
    db: Session,
    records: List[ParsedRecord],
    ingestion_id: Optional[int] = None
) -> Dict[str, int]:
    """
    Save investment transactions using HYBRID deduplication approach.

    Algorithm:
    1. Group records by account
    2. For each account, find crossover date (max date already in DB)
    3. Skip all records before crossover date (no DB queries needed)
    4. For records at/after crossover, use count-based logic:
       - Count identical transactions in CSV
       - Count identical transactions in DB
       - Import the difference (csv_count - db_count)

    This handles:
    - Overlapping date range uploads (skip old, import new)
    - Same file uploaded twice (counts match, skip all)
    - Identical transactions on same day (import correct count)
    """
    from app.modules.investments.models import InvestmentTransaction, InvestmentAccount

    created = 0
    updated = 0
    skipped = 0
    has_sto_transactions = False
    accounts_with_buys: set = set()
    consumed_ids: set = set()  # DB rows already matched by fee-tolerant dedup

    if not records:
        return {"created": 0, "updated": 0, "skipped": 0, "has_sto": False}

    # Step 1: Normalize account IDs and group records by account
    records_by_account = defaultdict(list)
    for record in records:
        data = record.data
        account_id = _normalize_account_id(data.get("account_id", "default"))
        data["account_id"] = account_id  # Update with normalized ID
        records_by_account[account_id].append(record)

    # Step 2: Process each account
    for account_id, account_records in records_by_account.items():
        source = account_records[0].data.get("source", "unknown")

        # Find unique transaction types in the incoming records
        incoming_types = set(r.data.get("transaction_type", "") for r in account_records)

        # Calculate crossover date per transaction type
        # This prevents other transaction types from affecting our crossover
        crossover_by_type = {}
        for txn_type in incoming_types:
            crossover_result = db.query(func.max(InvestmentTransaction.transaction_date)).filter(
                InvestmentTransaction.account_id == account_id,
                InvestmentTransaction.source == source,
                InvestmentTransaction.transaction_type == txn_type
            ).scalar()
            crossover_by_type[txn_type] = crossover_result

        # Separate records: before crossover vs at/after crossover (per type)
        before_crossover = []
        at_or_after_crossover = []

        for record in account_records:
            txn_date = record.data.get("transaction_date")
            if isinstance(txn_date, datetime):
                txn_date = txn_date.date()

            txn_type = record.data.get("transaction_type", "")
            crossover_date = crossover_by_type.get(txn_type)

            if crossover_date and txn_date < crossover_date:
                before_crossover.append(record)
            else:
                at_or_after_crossover.append(record)

        # Skip everything before crossover — but still reconcile amounts:
        # a skipped row may be the official (net-of-fees) version of a fill
        # already stored gross by the MCP bridge.
        for record in before_crossover:
            if _reconcile_fee_variant(db, account_id, source, record.data,
                                      consumed_ids) == "updated":
                updated += 1
        skipped += len(before_crossover)

        if not at_or_after_crossover:
            continue

        # Step 3: Count-based logic for records at/after crossover
        # Group by key and count
        csv_counts = defaultdict(int)
        csv_records_by_key = defaultdict(list)
        for record in at_or_after_crossover:
            key = _make_transaction_key(record.data)
            csv_counts[key] += 1
            csv_records_by_key[key].append(record)

        # Query DB for counts of each key
        # We need to check each unique key
        db_counts = defaultdict(int)
        for key in csv_counts.keys():
            parts = key.split("|")
            txn_date_str, txn_type, symbol, amount_str, description = parts[0], parts[1], parts[2], parts[3], parts[4]
            txn_date = datetime.strptime(txn_date_str, "%Y-%m-%d").date()
            amount = float(amount_str)

            # Handle symbol variants (empty string vs UNKNOWN)
            symbol_variants = [symbol]
            if symbol == "" or symbol == "UNKNOWN":
                symbol_variants = ["", "UNKNOWN"]

            # Get equivalent transaction types
            equivalent_types = _get_equivalent_types(txn_type)

            count = db.query(func.count(InvestmentTransaction.id)).filter(
                InvestmentTransaction.account_id == account_id,
                InvestmentTransaction.source == source,
                InvestmentTransaction.transaction_date == txn_date,
                InvestmentTransaction.transaction_type.in_(equivalent_types),
                InvestmentTransaction.symbol.in_(symbol_variants),
                InvestmentTransaction.amount == amount,
                InvestmentTransaction.description == description
            ).scalar() or 0

            db_counts[key] = count

        # Step 4: Import the difference for each key
        for key, csv_count in csv_counts.items():
            db_count = db_counts.get(key, 0)
            to_import = csv_count - db_count

            if to_import <= 0:
                skipped += csv_count
                continue

            # Import 'to_import' records with this key
            records_to_import = csv_records_by_key[key][db_count:db_count + to_import]
            skipped += csv_count - to_import  # Skip the ones we already have

            for idx, record in enumerate(records_to_import):
                data = record.data

                # Fee-tolerant dedup: same fill already stored with a gross
                # (MCP) vs net (official CSV) amount is NOT a new transaction.
                outcome = _reconcile_fee_variant(db, account_id, source, data,
                                                 consumed_ids)
                if outcome == "updated":
                    updated += 1
                    continue
                if outcome == "skipped":
                    skipped += 1
                    continue

                # Ensure account exists
                _ensure_account_exists(db, account_id, source, data)

                # Check for STO transactions
                if data.get("transaction_type") == "STO":
                    has_sto_transactions = True

                # Track accounts with BUY/SELL for cost basis recalculation
                if data.get("transaction_type") in ("BUY", "SELL", "OASGN"):
                    accounts_with_buys.add(account_id)

                # Generate record hash with unique counter to allow identical transactions
                # The counter (db_count + idx) ensures each instance gets a unique hash
                instance_num = db_count + idx
                hash_data = (
                    f"{source}:{account_id}:{data.get('transaction_date')}:"
                    f"{data.get('symbol', '')}:{data.get('transaction_type', '')}:"
                    f"{data.get('quantity')}:{data.get('amount')}:{data.get('description', '')}:"
                    f"instance_{instance_num}"
                )
                record_hash = hashlib.sha256(hash_data.encode()).hexdigest()

                # Create transaction
                transaction = InvestmentTransaction(
                    source=source,
                    account_id=account_id,
                    transaction_date=data.get("transaction_date"),
                    symbol=data.get("symbol", ""),
                    description=data.get("description"),
                    transaction_type=data.get("transaction_type"),
                    quantity=data.get("quantity"),
                    price_per_share=data.get("price_per_share") or data.get("price"),
                    amount=data.get("amount"),
                    fees=data.get("fees", 0),
                    record_hash=record_hash,
                    ingestion_id=ingestion_id,
                )
                db.add(transaction)
                created += 1

        db.flush()

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "has_sto": has_sto_transactions,
        "accounts_with_buys": accounts_with_buys,
    }


def _ensure_account_exists(db: Session, account_id: str, source: str, data: dict):
    """Ensure the investment account exists, creating it if necessary."""
    from app.modules.investments.models import InvestmentAccount

    account = db.query(InvestmentAccount).filter(
        InvestmentAccount.account_id == account_id,
        InvestmentAccount.source == source,
    ).first()

    if not account:
        owner, account_type = _parse_owner_and_type_from_account_id(account_id)
        account_name = data.get("account_name")
        if not account_name or account_name == account_id:
            account_name = _generate_account_name(account_id, account_type)

        final_account_type = data.get("account_type") or account_type
        if 'roth' in account_id.lower() and final_account_type != 'roth_ira':
            final_account_type = 'roth_ira'

        account = InvestmentAccount(
            account_id=account_id,
            account_name=account_name,
            source=source,
            account_type=final_account_type,
        )
        db.add(account)
        db.flush()


def save_1099_b_records(
    db: Session,
    records: List[ParsedRecord],
    ingestion_id: Optional[int] = None,
) -> Dict[str, int]:
    """
    Save 1099-B equity capital gain records as StockLot + StockLotSale pairs.

    Each record represents a fully realized sale: we create a synthetic StockLot
    for the purchase (using DATE ACQUIRED and COST BASIS from the 1099) and a
    StockLotSale for the disposition. Options rows are already excluded by the
    parser, so every record here is a stock or ETF sale.

    Deduplication: match on (symbol, account_id, source, purchase_date,
    cost_basis, quantity). If the lot exists, also check the sale before
    creating a duplicate.
    """
    from app.modules.tax.models import StockLot, StockLotSale

    created = 0
    skipped = 0

    for record in records:
        d = record.data
        symbol: str = d["symbol"]
        account_id: str = d["account_id"]
        purchase_date: Optional[date] = d["purchase_date"]
        sale_date: date = d["sale_date"]
        shares: Decimal = d["shares"]
        cost_basis: Decimal = d["cost_basis"]
        proceeds: Decimal = d["proceeds"]
        is_long_term: bool = d["is_long_term"]
        tax_year: int = d["tax_year"]
        wash_disallowed: Decimal = d["wash_sale_disallowed"]
        description: str = d.get("description", "")

        if shares <= 0:
            skipped += 1
            continue

        # ── Find or create StockLot ────────────────────────────────────────
        lot_query = db.query(StockLot).filter(
            StockLot.symbol == symbol,
            StockLot.account_id == account_id,
            StockLot.source == "robinhood_1099",
            StockLot.cost_basis == cost_basis,
            StockLot.quantity == shares,
        )
        if purchase_date:
            lot_query = lot_query.filter(StockLot.purchase_date == purchase_date)

        lot = lot_query.first()

        if lot is None:
            effective_purchase_date = purchase_date or sale_date
            cost_per_share = (cost_basis / shares).quantize(Decimal("0.0001"))
            lot = StockLot(
                symbol=symbol,
                purchase_date=effective_purchase_date,
                quantity=shares,
                cost_basis=cost_basis,
                cost_per_share=cost_per_share,
                quantity_remaining=Decimal("0"),
                status="closed",
                account_id=account_id,
                source="robinhood_1099",
                notes=description,
            )
            db.add(lot)
            db.flush()  # get lot_id

        # ── Find or create StockLotSale ────────────────────────────────────
        existing_sale = db.query(StockLotSale).filter(
            StockLotSale.lot_id == lot.lot_id,
            StockLotSale.sale_date == sale_date,
            StockLotSale.quantity_sold == shares,
            StockLotSale.proceeds == proceeds,
        ).first()

        if existing_sale:
            skipped += 1
            continue

        holding_days = (
            (sale_date - lot.purchase_date).days
            if purchase_date
            else (366 if is_long_term else 100)
        )
        proceeds_per_share = (proceeds / shares).quantize(Decimal("0.0001"))
        gain_loss = proceeds - cost_basis

        sale = StockLotSale(
            lot_id=lot.lot_id,
            sale_date=sale_date,
            quantity_sold=shares,
            proceeds=proceeds,
            proceeds_per_share=proceeds_per_share,
            cost_basis=cost_basis,
            gain_loss=gain_loss,
            holding_period_days=holding_days,
            is_long_term=is_long_term,
            tax_year=tax_year,
            wash_sale=wash_disallowed > 0,
            wash_sale_disallowed=wash_disallowed if wash_disallowed > 0 else None,
            notes=description,
        )
        db.add(sale)
        created += 1

    db.flush()
    return {"created": created, "updated": 0, "skipped": skipped}


def save_records(db: Session, records: list, ingestion_id: Optional[int] = None) -> dict:
    """
    Save parsed records to the database.
    Returns dict with created, updated, skipped counts.

    Uses HYBRID deduplication for transactions:
    - Skip records before crossover date (max date in DB)
    - Use count-based logic for records at/after crossover
    """
    from app.modules.investments.models import InvestmentTransaction, InvestmentHolding, InvestmentAccount
    from app.modules.cash.models import CashTransaction, CashAccount

    created = 0
    updated = 0
    skipped = 0
    has_sto_transactions = False

    # Separate transaction records from other types
    transaction_records = []
    spending_records = []
    capital_gain_records = []
    other_records = []

    for record in records:
        if record.record_type in (RecordType.TRANSACTION, RecordType.DIVIDEND):
            transaction_records.append(record)
        elif record.record_type == RecordType.SPENDING:
            spending_records.append(record)
        elif record.record_type == RecordType.CAPITAL_GAIN:
            capital_gain_records.append(record)
        else:
            other_records.append(record)

    # Process transactions using hybrid approach
    if transaction_records:
        txn_result = save_investment_transactions_hybrid(db, transaction_records, ingestion_id)
        created += txn_result["created"]
        updated += txn_result.get("updated", 0)
        skipped += txn_result["skipped"]
        has_sto_transactions = txn_result.get("has_sto", False)

    # Process spending records
    if spending_records:
        spend_result = save_spending_transactions(db, spending_records, ingestion_id)
        created += spend_result["created"]
        skipped += spend_result["skipped"]

    # Process 1099-B capital gain records
    if capital_gain_records:
        gain_result = save_1099_b_records(db, capital_gain_records, ingestion_id)
        created += gain_result["created"]
        skipped += gain_result["skipped"]

    # Process other record types as before
    for record in other_records:
        try:
            if record.record_type == RecordType.HOLDING:
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

    # Auto-recalculate cost basis for accounts that had BUY/SELL/OASGN transactions
    accounts_with_buys = txn_result.get("accounts_with_buys", set()) if transaction_records else set()
    if accounts_with_buys:
        try:
            from app.modules.investments.services import calculate_cost_basis_from_transactions
            from app.modules.investments.models import InvestmentHolding
            cost_basis_updated = 0
            for acct_id in accounts_with_buys:
                holdings = db.query(InvestmentHolding).filter(
                    InvestmentHolding.account_id == acct_id,
                    InvestmentHolding.quantity > 0,
                    InvestmentHolding.symbol != 'CASH',
                ).all()
                for holding in holdings:
                    calculated = calculate_cost_basis_from_transactions(db, acct_id, holding.symbol)
                    if calculated is not None and calculated > 0:
                        holding.cost_basis = calculated
                        cost_basis_updated += 1
            db.flush()
            print(f"Auto-recalculated cost basis: {cost_basis_updated} holdings updated for accounts {accounts_with_buys}")
        except Exception as e:
            print(f"Error auto-recalculating cost basis: {e}")

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


# Mapping of equivalent transaction types for deduplication
# These are different codes that represent the same type of transaction
EQUIVALENT_TRANSACTION_TYPES = {
    # Dividend types - all represent cash dividends
    'CDIV': ['CDIV', 'DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND'],
    'DIVIDEND': ['CDIV', 'DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND'],
    'CASH DIVIDEND': ['CDIV', 'DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND'],
    'QUALIFIED DIVIDEND': ['CDIV', 'DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND'],
    # Interest types - all represent interest income
    'INT': ['INT', 'INTEREST', 'SLIP'],
    'INTEREST': ['INT', 'INTEREST', 'SLIP'],
    'SLIP': ['INT', 'INTEREST', 'SLIP'],  # Sweep interest
}


def _get_equivalent_types(transaction_type: str) -> list:
    """Get list of equivalent transaction types for deduplication."""
    return EQUIVALENT_TRANSACTION_TYPES.get(transaction_type, [transaction_type])


# Trade rows can arrive from two feeds: the MCP bridge (gross amounts — the
# order API exposes no fee data) and the official activity CSV (net of
# regulatory fees). Same fill, amounts differ by cents, so the exact-amount
# dedup key misses them. These codes get a fee-sized amount tolerance.
_OPTION_TRADE_TYPES = ("STO", "BTC", "STC", "BTO")
_EQUITY_TRADE_TYPES = ("BUY", "SELL")


def _fee_tolerance(transaction_type: str, quantity, amount) -> float:
    """Max plausible regulatory-fee gap between gross and net for one row."""
    try:
        qty = abs(float(quantity)) if quantity is not None else 0.0
        amt = abs(float(amount)) if amount is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
    if not qty:
        return 0.0
    if transaction_type in _OPTION_TRADE_TYPES:
        # ORF/OCC/SEC/TAF run well under $0.25 per contract
        return 0.25 * qty + 0.10
    if transaction_type in _EQUITY_TRADE_TYPES:
        # SEC fee scales with notional (sells), TAF with shares
        return 0.10 + 0.02 * qty + 0.0001 * amt
    return 0.0


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
    # Use equivalent transaction types to catch CDIV/DIVIDEND, INT/INTEREST duplicates
    equivalent_types = _get_equivalent_types(transaction_type)

    # Handle symbol normalization: empty string and 'UNKNOWN' should be treated as equivalent
    symbol_variants = [symbol]
    if symbol == "" or symbol == "UNKNOWN" or symbol is None:
        symbol_variants = ["", "UNKNOWN"]

    existing = db.query(InvestmentTransaction).filter(
        InvestmentTransaction.source == source,
        InvestmentTransaction.account_id == account_id_str,
        InvestmentTransaction.transaction_date == transaction_date,
        InvestmentTransaction.symbol.in_(symbol_variants),
        InvestmentTransaction.transaction_type.in_(equivalent_types),
        InvestmentTransaction.quantity == quantity,
        InvestmentTransaction.amount == amount,
    ).first()

    if existing:
        return "skipped"

    # FEE-TOLERANT DEDUPLICATION: catch the same fill arriving once with a
    # gross amount (MCP bridge) and once net of regulatory fees (official
    # activity CSV). Match on every key field except amount, within a
    # fee-sized tolerance, and keep the SMALLER signed amount — fees only
    # ever reduce cash, so the smaller value is the fee-inclusive official
    # figure. Order-independent: official-after-MCP updates the stored row,
    # MCP-after-official is skipped.
    tolerance = _fee_tolerance(transaction_type, quantity, amount)
    if tolerance and amount is not None:
        near_candidates = db.query(InvestmentTransaction).filter(
            InvestmentTransaction.source == source,
            InvestmentTransaction.account_id == account_id_str,
            InvestmentTransaction.transaction_date == transaction_date,
            InvestmentTransaction.symbol.in_(symbol_variants),
            InvestmentTransaction.transaction_type.in_(equivalent_types),
            InvestmentTransaction.quantity == quantity,
            InvestmentTransaction.amount != amount,
        ).all()
        for candidate in near_candidates:
            # For options, same-day/same-premium fills on different strikes
            # exist; the description carries the strike, so require it to
            # match when both sides have one (bridge and official CSV use
            # the identical description format).
            if (transaction_type in _OPTION_TRADE_TYPES
                    and candidate.description and data.get("description")
                    and candidate.description.strip() != data.get("description", "").strip()):
                continue
            if abs(float(candidate.amount) - float(amount)) <= tolerance:
                if float(amount) < float(candidate.amount):
                    candidate.amount = amount
                    db.flush()
                    return "updated"
                return "skipped"

    # CROSS-ACCOUNT DEDUPLICATION: For sources like Robinhood where exports don't
    # include account info, also check if this transaction exists in ANY account
    # from the same source (to prevent duplicates when importing generic exports)
    # Note: symbol_variants already defined above with UNKNOWN/empty handling
    cross_account_existing = db.query(InvestmentTransaction).filter(
        InvestmentTransaction.source == source,
        InvestmentTransaction.transaction_date == transaction_date,
        InvestmentTransaction.symbol.in_(symbol_variants),
        InvestmentTransaction.transaction_type.in_(equivalent_types),  # Use equivalent types
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
    
    # Create new transaction with savepoint for error recovery
    # Using a savepoint allows us to rollback just this INSERT without
    # affecting the rest of the transaction (like the ingestion_log)
    try:
        # Begin a savepoint (nested transaction)
        savepoint = db.begin_nested()
        
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
        
        # Commit the savepoint (not the main transaction)
        savepoint.commit()
        
        # NOTE: We intentionally DO NOT update holdings from transaction imports.
        # Holdings should ONLY come from the Robinhood paste (copy-paste from web UI),
        # which is the authoritative source for current positions.
        # Transaction CSVs are for income/expense tracking, not position quantities.
        # This prevents duplicate holdings when account_id inference differs between
        # paste and CSV import.
        
        return "created"
    except Exception as e:
        # Rollback only the savepoint, NOT the main transaction
        # This preserves the ingestion_log and other already-saved transactions
        if 'savepoint' in dir() and savepoint:
            try:
                savepoint.rollback()
            except Exception:
                pass  # Savepoint might already be rolled back
        
        # Check if it's a unique constraint violation (duplicate)
        if "UniqueViolation" in str(type(e).__name__) or "unique constraint" in str(e).lower():
            return "skipped"
        
        # For other errors, log and skip rather than failing the whole batch
        print(f"Error saving transaction: {e}")
        return "skipped"


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
    db.flush()  # Flush to make visible for duplicate checks in same batch
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
    db.flush()  # Flush to make visible for duplicate checks in same batch
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
    db.flush()  # Flush to make visible for duplicate checks in same batch
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
    # Flush immediately so subsequent queries in the same transaction can see this record
    # This prevents duplicate key errors when multiple files have the same snapshot date
    db.flush()
    return "created"


def save_spending_transactions(
    db: Session,
    records: List[ParsedRecord],
    ingestion_id: Optional[int] = None,
) -> Dict[str, int]:
    """
    Save spending transactions using simple hash-based deduplication.
    Each record already has a unique record_hash computed by the parser.
    """
    from app.modules.spending.models import SpendingTransaction

    created = 0
    skipped = 0

    for record in records:
        data = record.data
        record_hash = data.get("record_hash")

        existing = db.query(SpendingTransaction.id).filter(
            SpendingTransaction.record_hash == record_hash
        ).first()

        if existing:
            skipped += 1
            continue

        txn = SpendingTransaction(
            transaction_date=data["transaction_date"],
            merchant=data.get("merchant"),
            category=data.get("category"),
            account=data.get("account"),
            original_statement=data.get("original_statement"),
            notes=data.get("notes"),
            amount=data["amount"],
            tags=data.get("tags"),
            owner=data.get("owner"),
            record_hash=record_hash,
            ingestion_id=ingestion_id,
        )
        db.add(txn)
        created += 1

    db.flush()
    return {"created": created, "updated": 0, "skipped": skipped}

