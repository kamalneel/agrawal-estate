#!/usr/bin/env python3
"""
Script to undo the effects of a specific ingestion or set of ingestions.

Usage:
    # List recent ingestions
    python scripts/undo_ingestion.py --list
    
    # List recent Robinhood PDF ingestions
    python scripts/undo_ingestion.py --list --source robinhood
    
    # Preview what would be deleted for specific ingestion IDs
    python scripts/undo_ingestion.py --preview --ids 395,396,397,398
    
    # Actually delete records for specific ingestion IDs
    python scripts/undo_ingestion.py --delete --ids 395,396,397,398
"""

import argparse
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings


def get_db_session():
    """Create a database session."""
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def list_recent_ingestions(db, source=None, limit=20):
    """List recent ingestions."""
    from app.shared.models.ingestion import IngestionLog
    
    query = db.query(IngestionLog).order_by(IngestionLog.started_at.desc())
    
    if source:
        query = query.filter(IngestionLog.source == source)
    
    logs = query.limit(limit).all()
    
    print(f"\n{'ID':<6} {'Source':<12} {'File Name':<50} {'Records':<10} {'Date'}")
    print("-" * 100)
    
    for log in logs:
        records = f"{log.records_created or 0}c/{log.records_updated or 0}u"
        date_str = log.started_at.strftime("%Y-%m-%d %H:%M") if log.started_at else "N/A"
        print(f"{log.id:<6} {log.source:<12} {log.file_name[:48]:<50} {records:<10} {date_str}")
    
    print(f"\nTotal: {len(logs)} ingestions shown")


def preview_deletion(db, ingestion_ids):
    """Preview what would be deleted for given ingestion IDs."""
    from app.modules.investments.models import InvestmentHolding, InvestmentTransaction, PortfolioSnapshot
    from app.modules.cash.models import CashTransaction, CashSnapshot
    from app.shared.models.ingestion import IngestionLog
    
    print(f"\n=== Preview: Records that would be deleted for ingestion IDs: {ingestion_ids} ===\n")
    
    # Show which files these IDs correspond to
    logs = db.query(IngestionLog).filter(IngestionLog.id.in_(ingestion_ids)).all()
    print("Files:")
    for log in logs:
        print(f"  - ID {log.id}: {log.file_name} ({log.source})")
    print()
    
    # Count records in each table
    tables = [
        ("InvestmentHolding", InvestmentHolding),
        ("InvestmentTransaction", InvestmentTransaction),
        ("PortfolioSnapshot", PortfolioSnapshot),
        ("CashTransaction", CashTransaction),
        ("CashSnapshot", CashSnapshot),
    ]
    
    total = 0
    for name, model in tables:
        count = db.query(model).filter(model.ingestion_id.in_(ingestion_ids)).count()
        if count > 0:
            print(f"  {name}: {count} records")
            
            # Show sample records
            samples = db.query(model).filter(model.ingestion_id.in_(ingestion_ids)).limit(5).all()
            for sample in samples:
                if hasattr(sample, 'symbol'):
                    print(f"    - {sample.symbol} (ingestion_id={sample.ingestion_id})")
                elif hasattr(sample, 'account_id'):
                    print(f"    - account={sample.account_id} (ingestion_id={sample.ingestion_id})")
            if count > 5:
                print(f"    ... and {count - 5} more")
            
            total += count
    
    print(f"\nTotal records that would be deleted: {total}")
    return total


def delete_records(db, ingestion_ids):
    """Delete records for given ingestion IDs."""
    from app.modules.investments.models import InvestmentHolding, InvestmentTransaction, PortfolioSnapshot
    from app.modules.cash.models import CashTransaction, CashSnapshot
    from app.shared.models.ingestion import IngestionLog
    
    print(f"\n=== Deleting records for ingestion IDs: {ingestion_ids} ===\n")
    
    # Delete from each table
    tables = [
        ("InvestmentHolding", InvestmentHolding),
        ("InvestmentTransaction", InvestmentTransaction),
        ("PortfolioSnapshot", PortfolioSnapshot),
        ("CashTransaction", CashTransaction),
        ("CashSnapshot", CashSnapshot),
    ]
    
    total = 0
    for name, model in tables:
        count = db.query(model).filter(model.ingestion_id.in_(ingestion_ids)).delete(synchronize_session=False)
        if count > 0:
            print(f"  Deleted {count} records from {name}")
            total += count
    
    # Mark ingestion logs as rolled back
    db.query(IngestionLog).filter(IngestionLog.id.in_(ingestion_ids)).update(
        {"status": "rolled_back", "error_message": "Manually rolled back via undo script"},
        synchronize_session=False
    )
    
    db.commit()
    print(f"\nTotal deleted: {total} records")
    print("Ingestion logs marked as 'rolled_back'")


def main():
    parser = argparse.ArgumentParser(description="Undo ingestion effects")
    parser.add_argument("--list", action="store_true", help="List recent ingestions")
    parser.add_argument("--source", type=str, help="Filter by source (e.g., robinhood)")
    parser.add_argument("--preview", action="store_true", help="Preview what would be deleted")
    parser.add_argument("--delete", action="store_true", help="Actually delete records")
    parser.add_argument("--ids", type=str, help="Comma-separated ingestion IDs")
    parser.add_argument("--limit", type=int, default=20, help="Limit for list (default: 20)")
    
    args = parser.parse_args()
    
    db = get_db_session()
    
    try:
        if args.list:
            list_recent_ingestions(db, source=args.source, limit=args.limit)
        
        elif args.preview:
            if not args.ids:
                print("Error: --ids required for preview")
                sys.exit(1)
            ids = [int(x.strip()) for x in args.ids.split(",")]
            preview_deletion(db, ids)
        
        elif args.delete:
            if not args.ids:
                print("Error: --ids required for delete")
                sys.exit(1)
            ids = [int(x.strip()) for x in args.ids.split(",")]
            
            # First preview
            total = preview_deletion(db, ids)
            
            if total == 0:
                print("\nNo records to delete.")
                return
            
            # Confirm
            response = input(f"\nAre you sure you want to delete {total} records? (yes/no): ")
            if response.lower() == "yes":
                delete_records(db, ids)
            else:
                print("Cancelled.")
        
        else:
            parser.print_help()
    
    finally:
        db.close()


if __name__ == "__main__":
    main()


