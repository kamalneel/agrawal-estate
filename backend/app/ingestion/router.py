"""
Data Ingestion API routes.
Handles file scanning, processing, and import status.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pathlib import Path
import shutil
import logging

from app.core.database import get_db
from app.core.config import settings
from app.ingestion.services import save_records

logger = logging.getLogger(__name__)

router = APIRouter()


def get_all_parsers():
    """Get all available parsers."""
    from app.ingestion.parsers.robinhood import RobinhoodParser
    from app.ingestion.parsers.robinhood_pdf import RobinhoodPDFParser
    from app.ingestion.parsers.fidelity_csv import FidelityCSVParser
    from app.ingestion.parsers.schwab_pdf import SchwabPDFParser
    from app.ingestion.parsers.chase import ChaseParser
    
    return [
        RobinhoodPDFParser(),
        RobinhoodParser(),
        FidelityCSVParser(),
        SchwabPDFParser(),
        ChaseParser(),
    ]


@router.post("/scan")
async def trigger_inbox_scan(db: Session = Depends(get_db)):
    """
    Trigger a scan of all inbox folders.
    Processes any new files found.
    """
    parsers = get_all_parsers()
    
    # Define inbox folders to scan
    inbox_folders = [
        settings.INBOX_DIR / "investments" / "robinhood",
        settings.INBOX_DIR / "investments" / "schwab",
        settings.INBOX_DIR / "investments" / "fidelity",
        settings.INBOX_DIR / "investments" / "other",
        settings.INBOX_DIR / "cash" / "chase",
        settings.INBOX_DIR / "cash" / "bank_of_america",
    ]
    
    folders_scanned = []
    files_found = 0
    files_processed = 0
    files_failed = 0
    results = []
    
    for folder in inbox_folders:
        if not folder.exists():
            continue
            
        folders_scanned.append(str(folder))
        
        # Get all files (not hidden, not directories)
        files = [f for f in folder.iterdir() if f.is_file() and not f.name.startswith('.')]
        files_found += len(files)
        
        for file_path in files:
            # Try each parser
            parsed = False
            for parser in parsers:
                try:
                    if parser.can_parse(file_path):
                        result = parser.parse(file_path)
                        
                        if result.success and result.records:
                            # Save records to database
                            save_result = save_records(db, result.records)
                            db.commit()
                            
                            # Move file to processed folder
                            processed_dir = settings.PROCESSED_DIR / folder.relative_to(settings.INBOX_DIR)
                            processed_dir.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(file_path), str(processed_dir / file_path.name))
                            
                            files_processed += 1
                            results.append({
                                "file": file_path.name,
                                "parser": parser.source_name,
                                "status": "success",
                                "records": save_result
                            })
                            parsed = True
                            break
                        elif result.errors:
                            results.append({
                                "file": file_path.name,
                                "parser": parser.source_name,
                                "status": "error",
                                "errors": result.errors
                            })
                except Exception as e:
                    results.append({
                        "file": file_path.name,
                        "parser": parser.source_name if parser else "unknown",
                        "status": "exception",
                        "error": str(e)
                    })
            
            if not parsed:
                files_failed += 1
    
    return {
        "status": "scan_complete",
        "folders_scanned": folders_scanned,
        "files_found": files_found,
        "files_processed": files_processed,
        "files_failed": files_failed,
        "results": results
    }


@router.get("/status")
async def get_ingestion_status(db: Session = Depends(get_db)):
    """Get current ingestion processing status."""
    return {
        "is_processing": False,
        "current_file": None,
        "queue_size": 0
    }


@router.get("/history")
async def get_ingestion_history(
    db: Session = Depends(get_db),
    module: Optional[str] = None,
    source: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50
):
    """
    Get history of file ingestions.
    Filter by module (investments, tax, etc.), source (robinhood, schwab, etc.), or status.
    """
    return {
        "ingestions": [],
        "total": 0
    }


@router.get("/history/{ingestion_id}")
async def get_ingestion_details(ingestion_id: int, db: Session = Depends(get_db)):
    """Get detailed results for a specific ingestion."""
    return {
        "ingestion": None,
        "records_created": [],
        "records_updated": [],
        "errors": []
    }


@router.post("/retry/{ingestion_id}")
async def retry_failed_ingestion(ingestion_id: int, db: Session = Depends(get_db)):
    """Retry a previously failed file ingestion."""
    return {"status": "retry_initiated", "ingestion_id": ingestion_id}


@router.get("/preview")
async def preview_file(file_path: str, db: Session = Depends(get_db)):
    """
    Preview what a file contains before processing.
    Returns parsed data without committing to database.
    """
    return {
        "file_path": file_path,
        "detected_source": None,
        "detected_type": None,
        "record_count": 0,
        "sample_records": [],
        "warnings": []
    }


@router.delete("/failed/{ingestion_id}")
async def dismiss_failed_ingestion(ingestion_id: int, db: Session = Depends(get_db)):
    """Dismiss/acknowledge a failed ingestion."""
    return {"status": "dismissed", "ingestion_id": ingestion_id}


@router.post("/process-all")
async def process_all_inbox_files(db: Session = Depends(get_db)):
    """
    Process all files in all inbox folders.
    Returns result in format expected by frontend.
    """
    parsers = get_all_parsers()
    
    # Define inbox folders to scan
    inbox_folders = [
        ("investments/robinhood", settings.INBOX_DIR / "investments" / "robinhood"),
        ("investments/schwab", settings.INBOX_DIR / "investments" / "schwab"),
        ("investments/fidelity", settings.INBOX_DIR / "investments" / "fidelity"),
        ("investments/other", settings.INBOX_DIR / "investments" / "other"),
        ("cash/chase", settings.INBOX_DIR / "cash" / "chase"),
        ("cash/bank_of_america", settings.INBOX_DIR / "cash" / "bank_of_america"),
        ("income/salary", settings.INBOX_DIR / "income" / "salary"),
        ("tax/returns", settings.INBOX_DIR / "tax" / "returns"),
    ]
    
    files_processed = 0
    records_imported = 0
    errors = []
    details = []
    
    for folder_name, folder_path in inbox_folders:
        if not folder_path.exists():
            continue
        
        # Get all files (not hidden, not directories)
        files = [f for f in folder_path.iterdir() if f.is_file() and not f.name.startswith('.')]
        
        if not files:
            continue
        
        folder_files = []
        folder_records = 0
        
        for file_path in files:
            # Try each parser
            parsed = False
            for parser in parsers:
                try:
                    if parser.can_parse(file_path):
                        result = parser.parse(file_path)
                        
                        if result.success and result.records:
                            # Save records to database
                            save_result = save_records(db, result.records)
                            db.commit()
                            
                            # Move file to processed folder
                            processed_dir = settings.PROCESSED_DIR / folder_path.relative_to(settings.INBOX_DIR)
                            processed_dir.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(file_path), str(processed_dir / file_path.name))
                            
                            files_processed += 1
                            folder_files.append(file_path.name)
                            folder_records += save_result.get("created", 0) + save_result.get("updated", 0)
                            records_imported += save_result.get("created", 0) + save_result.get("updated", 0)
                            parsed = True
                            break
                        elif result.errors:
                            errors.extend([f"{file_path.name}: {e}" for e in result.errors])
                except Exception as e:
                    errors.append(f"{file_path.name}: {str(e)}")
            
            if not parsed and not any(file_path.name in e for e in errors):
                errors.append(f"{file_path.name}: No compatible parser found")
        
        if folder_files:
            details.append({
                "folder": folder_name,
                "files": folder_files,
                "records": folder_records
            })
    
    return {
        "success": True,
        "files_processed": files_processed,
        "records_imported": records_imported,
        "errors": errors,
        "details": details
    }


@router.get("/inbox-status")
async def get_inbox_status():
    """Get status of all inbox folders."""
    inbox_folders = [
        ("investments/robinhood", settings.INBOX_DIR / "investments" / "robinhood"),
        ("investments/schwab", settings.INBOX_DIR / "investments" / "schwab"),
        ("investments/other", settings.INBOX_DIR / "investments" / "other"),
        ("income/salary", settings.INBOX_DIR / "income" / "salary"),
        ("income/rental", settings.INBOX_DIR / "income" / "rental"),
        ("income/dividends", settings.INBOX_DIR / "income" / "dividends"),
        ("tax/property_tax", settings.INBOX_DIR / "tax" / "property_tax"),
        ("tax/returns", settings.INBOX_DIR / "tax" / "returns"),
        ("real_estate/mortgages", settings.INBOX_DIR / "real_estate" / "mortgages"),
        ("real_estate/valuations", settings.INBOX_DIR / "real_estate" / "valuations"),
        ("estate_planning/documents", settings.INBOX_DIR / "estate_planning" / "documents"),
    ]
    
    status = []
    for name, path in inbox_folders:
        file_count = 0
        if path.exists():
            # Exclude hidden files like .DS_Store
            file_count = len([f for f in path.iterdir() if f.is_file() and not f.name.startswith('.')])
        status.append({
            "folder": name,
            "path": str(path),
            "pending_files": file_count
        })
    
    return {"folders": status}


# ============================================================================
# ROBINHOOD PASTE IMPORT (Unified Parser)
# ============================================================================

@router.post("/robinhood-paste/preview")
async def preview_robinhood_paste(
    data: dict,
    db: Session = Depends(get_db)
):
    """
    Preview pasted Robinhood data before saving.
    
    Detects format (stocks, options list, options detail, or mixed) and returns
    parsed data for user confirmation.
    """
    from app.ingestion.robinhood_unified_parser import parse_robinhood_data
    
    text = data.get("text", "")
    account_name = data.get("account_name")
    
    if not text.strip():
        raise HTTPException(status_code=400, detail="No text provided")
    
    # Parse the data
    result = parse_robinhood_data(text, account_name)
    
    # Check if empty sections require confirmation
    requires_confirmation = False
    confirmation_message = ""
    
    if result.has_stocks_section and not result.stocks:
        requires_confirmation = True
        if result.has_options_section and not result.options:
            confirmation_message = "You have empty Options and Stocks sections. This will clear ALL options and stocks for this account. Do you want to proceed?"
        else:
            confirmation_message = "You have an empty Stocks section. This will clear ALL stocks for this account. Do you want to proceed?"
    elif result.has_options_section and not result.options:
        requires_confirmation = True
        confirmation_message = "You have an empty Options section. This will clear ALL options for this account. Do you want to proceed?"
    
    return {
        "success": True,
        "detected_format": result.detected_format,
        "stocks_count": len(result.stocks),
        "options_count": len(result.options),
        "has_options_section": result.has_options_section,
        "has_stocks_section": result.has_stocks_section,
        "requires_confirmation": requires_confirmation,
        "confirmation_message": confirmation_message,
        "stocks": [
            {
                "symbol": s.symbol,
                "name": s.name,
                "shares": s.shares,
                "market_value": s.market_value,
                "current_price": s.current_price
            }
            for s in result.stocks
        ],
        "options": [
            {
                "symbol": o.symbol,
                "strike_price": o.strike_price,
                "option_type": o.option_type,
                "expiration_date": o.expiration_date,
                "contracts": o.contracts,
                "current_premium": o.current_premium,
                "original_premium": o.original_premium,
                "gain_loss_percent": o.gain_loss_percent
            }
            for o in result.options
        ],
        "warnings": result.warnings
    }


@router.post("/robinhood-paste/save")
async def save_robinhood_paste(
    data: dict,
    db: Session = Depends(get_db)
):
    """
    Save pasted Robinhood data to database.
    
    Saves:
    - Stock holdings to investment_holdings table
    - Options to sold_options table (via snapshot)
    
    Expects account_name to map to the correct account.
    """
    from app.ingestion.robinhood_unified_parser import (
        parse_robinhood_data, 
        normalize_expiration_date
    )
    from app.modules.investments.models import InvestmentAccount, InvestmentHolding, PortfolioSnapshot
    from app.modules.strategies.models import SoldOptionsSnapshot, SoldOption
    from decimal import Decimal
    from datetime import datetime, date
    
    text = data.get("text", "")
    account_name = data.get("account_name")
    save_stocks = data.get("save_stocks", True)
    save_options = data.get("save_options", True)
    confirm_empty_sections = data.get("confirm_empty_sections", False)  # User must explicitly confirm
    
    if not text.strip():
        raise HTTPException(status_code=400, detail="No text provided")
    
    if not account_name:
        raise HTTPException(status_code=400, detail="Account name is required")
    
    # Parse the data
    result = parse_robinhood_data(text, account_name)
    
    # Check if confirmation is required for empty sections
    if (result.has_stocks_section and not result.stocks) or (result.has_options_section and not result.options):
        if not confirm_empty_sections:
            raise HTTPException(
                status_code=400, 
                detail="Empty sections detected. Please confirm that you want to clear all data for empty sections."
            )
    
    stocks_saved = 0
    stocks_updated = 0
    options_saved = 0
    
    # Save/update stock holdings
    # Only save/update if we have actual stock data
    # If has_stocks_section is True but stocks is empty, skip saving (don't clear existing data)
    if save_stocks and result.stocks:
        account_id = _normalize_account_id(account_name)
        
        # Ensure account exists
        account = db.query(InvestmentAccount).filter(
            InvestmentAccount.account_id == account_id,
            InvestmentAccount.source == 'robinhood'
        ).first()
        
        if not account:
            _owner, account_type = _parse_account_name(account_name)
            account = InvestmentAccount(
                account_id=account_id,
                account_name=account_name,
                source='robinhood',
                account_type=account_type,
                is_active='Y'
            )
            db.add(account)
            db.flush()
            logger.info(f"Created new account: {account_name} ({account_id})")
        
        # Track symbols in the new data for cleanup
        new_symbols = set()
        
        for stock in result.stocks:
            symbol = stock.symbol.upper()
            new_symbols.add(symbol)
            
            # Validate: market_value should be shares × price
            # If market_value seems wrong, recalculate
            if stock.shares > 0 and stock.current_price > 0:
                expected_value = stock.shares * stock.current_price
                if abs(expected_value - stock.market_value) > 1:  # Allow $1 rounding difference
                    logger.warning(f"{symbol}: market_value ${stock.market_value:.2f} doesn't match shares×price ${expected_value:.2f}, using calculated value")
                    stock.market_value = expected_value
            
            # Additional validation: reject obviously wrong values
            # Price should be between $0.01 and $100,000
            if stock.current_price < 0.01 or stock.current_price > 100000:
                logger.warning(f"{symbol}: Skipping - price ${stock.current_price:.4f} seems invalid")
                continue
            
            # Market value should be reasonable (> $1 for any meaningful holding)
            if stock.shares > 0 and stock.market_value < 1:
                logger.warning(f"{symbol}: Skipping - market_value ${stock.market_value:.2f} seems invalid for {stock.shares} shares")
                continue
            
            # Check if holding exists
            existing = db.query(InvestmentHolding).filter(
                InvestmentHolding.account_id == account_id,
                InvestmentHolding.source == 'robinhood',
                InvestmentHolding.symbol == symbol
            ).first()
            
            if existing:
                # Update existing holding
                existing.quantity = Decimal(str(stock.shares))
                existing.current_price = Decimal(str(round(stock.current_price, 4)))
                existing.market_value = Decimal(str(round(stock.market_value, 2)))
                existing.description = stock.name if stock.name != stock.symbol else existing.description
                existing.last_updated = datetime.utcnow()
                stocks_updated += 1
                logger.info(f"Updated {symbol}: {stock.shares} shares @ ${stock.current_price:.2f} = ${stock.market_value:,.2f}")
            else:
                # Create new holding
                holding = InvestmentHolding(
                    account_id=account_id,
                    source='robinhood',
                    symbol=symbol,
                    description=stock.name if stock.name != stock.symbol else None,
                    quantity=Decimal(str(stock.shares)),
                    current_price=Decimal(str(round(stock.current_price, 4))),
                    market_value=Decimal(str(round(stock.market_value, 2))),
                    last_updated=datetime.utcnow()
                )
                db.add(holding)
                stocks_saved += 1
                logger.info(f"Created {symbol}: {stock.shares} shares @ ${stock.current_price:.2f} = ${stock.market_value:,.2f}")
        
        # Remove holdings that are no longer in the account
        # (User sold the stock entirely)
        # Only cleanup if we have a section header (explicit complete list)
        # If no section header, this is a partial update - don't delete anything
        if result.has_stocks_section:
            current_holdings = db.query(InvestmentHolding).filter(
                InvestmentHolding.account_id == account_id,
                InvestmentHolding.source == 'robinhood'
            ).all()
            
            for holding in current_holdings:
                if holding.symbol not in new_symbols:
                    logger.info(f"Removing {holding.symbol} from {account_name} - no longer in holdings")
                    db.delete(holding)
    elif save_stocks and result.has_stocks_section and not result.stocks:
        # Stocks section header detected but empty - user has cleared all stocks
        account_id = _normalize_account_id(account_name)
        
        # Ensure account exists
        account = db.query(InvestmentAccount).filter(
            InvestmentAccount.account_id == account_id,
            InvestmentAccount.source == 'robinhood'
        ).first()
        
        if not account:
            _owner, account_type = _parse_account_name(account_name)
            account = InvestmentAccount(
                account_id=account_id,
                account_name=account_name,
                source='robinhood',
                account_type=account_type,
                is_active='Y'
            )
            db.add(account)
            db.flush()
            logger.info(f"Created new account: {account_name} ({account_id})")
        
        # Clear all stocks for this account
        current_holdings = db.query(InvestmentHolding).filter(
            InvestmentHolding.account_id == account_id,
            InvestmentHolding.source == 'robinhood'
        ).all()
        
        for holding in current_holdings:
            logger.info(f"Removing {holding.symbol} from {account_name} - stocks section is empty (all stocks cleared)")
            db.delete(holding)
    
    # Save options
    # Only save if we have actual options data
    # If has_options_section is True but options is empty, clear all options for this account
    snapshot_id = None
    if save_options and result.options:
        # Create snapshot
        snapshot = SoldOptionsSnapshot(
            source='robinhood',
            account_name=account_name,
            snapshot_date=datetime.utcnow(),
            parsing_status='success',
            raw_extracted_text=text[:5000]  # Limit stored text
        )
        db.add(snapshot)
        db.flush()
        snapshot_id = snapshot.id
        
        for opt in result.options:
            exp_date = normalize_expiration_date(opt.expiration_date) if opt.expiration_date else None
            
            sold_option = SoldOption(
                snapshot_id=snapshot_id,
                symbol=opt.symbol.upper(),
                strike_price=Decimal(str(opt.strike_price)),
                option_type=opt.option_type.lower(),
                expiration_date=exp_date,
                contracts_sold=opt.contracts,
                premium_per_contract=Decimal(str(opt.current_premium)) if opt.current_premium else None,
                original_premium=Decimal(str(opt.original_premium)) if opt.original_premium else None,
                gain_loss_percent=Decimal(str(opt.gain_loss_percent)) if opt.gain_loss_percent else None,
                status="open",
                raw_text=opt.raw_text[:500] if opt.raw_text else None
            )
            db.add(sold_option)
            options_saved += 1
    elif save_options and result.has_options_section and not result.options:
        # Options section header detected but empty - user has cleared all options
        # Delete all snapshots for this account (cascade will delete associated options)
        existing_snapshots = db.query(SoldOptionsSnapshot).filter(
            SoldOptionsSnapshot.source == 'robinhood',
            SoldOptionsSnapshot.account_name == account_name
        ).all()
        
        for snapshot in existing_snapshots:
            logger.info(f"Deleting options snapshot {snapshot.id} for {account_name} - options section is empty (all options cleared)")
            db.delete(snapshot)
    
    # Update portfolio snapshot with new data
    if (save_stocks and (stocks_saved > 0 or stocks_updated > 0)) or (save_options and options_saved > 0):
        account_id = _normalize_account_id(account_name)
        
        # Calculate total portfolio value from current holdings
        holdings = db.query(InvestmentHolding).filter(
            InvestmentHolding.account_id == account_id,
            InvestmentHolding.source == 'robinhood'
        ).all()
        
        total_portfolio_value = sum(
            float(h.market_value) if h.market_value else 0
            for h in holdings
        )
        
        # Get owner and account_type
        parts = account_id.split('_')
        owner = parts[0].title() if parts else 'Unknown'
        account_type = '_'.join(parts[1:]) if len(parts) > 1 else 'brokerage'
        
        today = date.today()
        
        # Find existing snapshot for today or most recent
        existing_snapshot = db.query(PortfolioSnapshot).filter(
            PortfolioSnapshot.source == 'robinhood',
            PortfolioSnapshot.account_id == account_id,
            PortfolioSnapshot.statement_date == today
        ).first()
        
        if existing_snapshot:
            existing_snapshot.portfolio_value = Decimal(str(round(total_portfolio_value, 2)))
            existing_snapshot.securities_value = Decimal(str(round(total_portfolio_value, 2)))
            existing_snapshot.updated_at = datetime.utcnow()
            logger.info(f"Updated snapshot for {account_name}: ${total_portfolio_value:,.2f}")
        else:
            # Create new snapshot for today
            new_snapshot = PortfolioSnapshot(
                source='robinhood',
                account_id=account_id,
                owner=owner,
                account_type=account_type,
                statement_date=today,
                portfolio_value=Decimal(str(round(total_portfolio_value, 2))),
                securities_value=Decimal(str(round(total_portfolio_value, 2))),
                cash_balance=Decimal('0')
            )
            db.add(new_snapshot)
            logger.info(f"Created snapshot for {account_name}: ${total_portfolio_value:,.2f}")
    
    db.commit()
    
    # CRITICAL: Clear recommendations cache after updating positions
    # This ensures notifications use fresh position data, not stale cached data
    from app.core.cache import clear_cache
    cleared_count = clear_cache("recommendations:")
    logger.info(f"Cleared {cleared_count} recommendations cache entries after position update for {account_name}")
    
    return {
        "success": True,
        "account_name": account_name,
        "stocks_saved": stocks_saved,
        "stocks_updated": stocks_updated,
        "options_saved": options_saved,
        "snapshot_id": snapshot_id,
        "detected_format": result.detected_format
    }


def _normalize_account_id(account_name: str) -> str:
    """Convert account name to account_id format."""
    # "Neel's Brokerage" -> "neel_brokerage"
    # "Jaya's Roth IRA" -> "jaya_roth_ira"
    import re
    
    # Remove apostrophe-s
    normalized = account_name.lower().replace("'s", "").replace("'s", "")
    # Replace spaces with underscores
    normalized = re.sub(r'\s+', '_', normalized.strip())
    # Remove any other special characters
    normalized = re.sub(r'[^a-z0-9_]', '', normalized)
    
    return normalized


def _parse_account_name(account_name: str) -> tuple:
    """Parse account name into owner and account_type."""
    # "Neel's Brokerage" -> ("Neel", "brokerage")
    # "Jaya's Roth IRA" -> ("Jaya", "roth_ira")
    
    parts = account_name.split("'s ")
    if len(parts) == 2:
        owner = parts[0]
        account_type = parts[1].lower().replace(" ", "_")
    else:
        # Fallback
        parts = account_name.split("'s ")
        if len(parts) == 2:
            owner = parts[0]
            account_type = parts[1].lower().replace(" ", "_")
        else:
            owner = "Unknown"
            account_type = account_name.lower().replace(" ", "_")
    
    return owner, account_type


@router.post("/merge-accounts")
async def merge_accounts(
    source_account_id: str,
    target_account_id: str,
    db: Session = Depends(get_db)
):
    """
    Merge one account into another.
    - Moves all holdings from source to target (aggregating quantities)
    - Moves all transactions from source to target
    - Deletes the source account
    """
    from app.modules.investments.models import InvestmentHolding, InvestmentTransaction, InvestmentAccount
    
    # Verify both accounts exist
    source_account = db.query(InvestmentAccount).filter(
        InvestmentAccount.account_id == source_account_id
    ).first()
    target_account = db.query(InvestmentAccount).filter(
        InvestmentAccount.account_id == target_account_id
    ).first()
    
    if not source_account:
        raise HTTPException(status_code=404, detail=f"Source account '{source_account_id}' not found")
    if not target_account:
        raise HTTPException(status_code=404, detail=f"Target account '{target_account_id}' not found")
    
    # Merge holdings
    source_holdings = db.query(InvestmentHolding).filter(
        InvestmentHolding.account_id == source_account_id
    ).all()
    
    holdings_merged = 0
    for src_holding in source_holdings:
        # Check if target has this symbol
        target_holding = db.query(InvestmentHolding).filter(
            InvestmentHolding.account_id == target_account_id,
            InvestmentHolding.symbol == src_holding.symbol
        ).first()
        
        if target_holding:
            # Aggregate quantities
            target_holding.quantity = float(target_holding.quantity or 0) + float(src_holding.quantity or 0)
            if src_holding.market_value:
                target_holding.market_value = float(target_holding.market_value or 0) + float(src_holding.market_value or 0)
            db.delete(src_holding)
        else:
            # Move holding to target account
            src_holding.account_id = target_account_id
        holdings_merged += 1
    
    # Move transactions
    transactions_moved = db.query(InvestmentTransaction).filter(
        InvestmentTransaction.account_id == source_account_id
    ).update({InvestmentTransaction.account_id: target_account_id})
    
    # Delete source account
    db.delete(source_account)
    db.commit()
    
    return {
        "success": True,
        "message": f"Merged '{source_account_id}' into '{target_account_id}'",
        "holdings_merged": holdings_merged,
        "transactions_moved": transactions_moved
    }

