#!/usr/bin/env python3
"""
Migration script to update transaction types for spending tracking.

Updates old TRANSFER/OTHER transactions to the new CASH_MOVEMENT type
based on their description, so the Buy/Borrow/Die page can query them.

Run: python scripts/migrate_cash_movement_types.py
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.modules.investments.models import InvestmentTransaction


def migrate_transaction_types():
    """Update transaction types for spending-related transactions."""
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        # Find transactions that should be CASH_MOVEMENT
        # These are transactions with descriptions indicating spending/transfers
        cash_movement_transactions = db.query(InvestmentTransaction).filter(
            InvestmentTransaction.transaction_type.in_(['TRANSFER', 'OTHER']),
            or_(
                # ACH transactions
                InvestmentTransaction.description.ilike('%ACH Withdrawal%'),
                InvestmentTransaction.description.ilike('%ACH Deposit%'),
                InvestmentTransaction.description.ilike('%ACH REVERSAL%'),
                # XENT transactions (Brokerage <-> Spending)
                InvestmentTransaction.description.ilike('%Brokerage to Spending%'),
                InvestmentTransaction.description.ilike('%Spending to Brokerage%'),
                InvestmentTransaction.description.ilike('%Transfer from Brokerage%'),
                InvestmentTransaction.description.ilike('%Transfer from Spending%'),
                # Credit Card
                InvestmentTransaction.description.ilike('%Credit Card balance payment%'),
                InvestmentTransaction.description.ilike('%Cash back from Robinhood Credit Card%'),
                # Instant bank transfer
                InvestmentTransaction.description.ilike('%Instant bank transfer%'),
            )
        ).all()
        
        print(f"Found {len(cash_movement_transactions)} transactions to update to CASH_MOVEMENT")
        
        for txn in cash_movement_transactions:
            old_type = txn.transaction_type
            txn.transaction_type = 'CASH_MOVEMENT'
            print(f"  {txn.transaction_date} | {old_type} -> CASH_MOVEMENT | ${txn.amount} | {txn.description[:50]}")
        
        # Find transactions that should be INTERNAL_TRANSFER
        internal_transfers = db.query(InvestmentTransaction).filter(
            InvestmentTransaction.transaction_type.in_(['TRANSFER', 'OTHER']),
            or_(
                InvestmentTransaction.description.ilike('%Transfer from Brokerage to Traditional IRA%'),
                InvestmentTransaction.description.ilike('%Transfer from Brokerage to Roth IRA%'),
                InvestmentTransaction.description.ilike('%Direct Rollover%'),
            )
        ).all()
        
        print(f"\nFound {len(internal_transfers)} transactions to update to INTERNAL_TRANSFER")
        
        for txn in internal_transfers:
            old_type = txn.transaction_type
            txn.transaction_type = 'INTERNAL_TRANSFER'
            print(f"  {txn.transaction_date} | {old_type} -> INTERNAL_TRANSFER | ${txn.amount} | {txn.description[:50]}")
        
        # Find Gold fee transactions
        gold_fees = db.query(InvestmentTransaction).filter(
            InvestmentTransaction.transaction_type.in_(['TRANSFER', 'OTHER']),
            or_(
                InvestmentTransaction.description.ilike('%Gold Subscription Fee%'),
                InvestmentTransaction.description.ilike('%Gold Fee%'),
            )
        ).all()
        
        print(f"\nFound {len(gold_fees)} transactions to update to FEE")
        
        for txn in gold_fees:
            old_type = txn.transaction_type
            txn.transaction_type = 'FEE'
            print(f"  {txn.transaction_date} | {old_type} -> FEE | ${txn.amount} | {txn.description[:50]}")
        
        # Find Gold deposit boost (income)
        gold_boost = db.query(InvestmentTransaction).filter(
            InvestmentTransaction.transaction_type.in_(['TRANSFER', 'OTHER']),
            InvestmentTransaction.description.ilike('%Gold Deposit Boost%'),
        ).all()
        
        print(f"\nFound {len(gold_boost)} transactions to update to INTEREST")
        
        for txn in gold_boost:
            old_type = txn.transaction_type
            txn.transaction_type = 'INTEREST'
            print(f"  {txn.transaction_date} | {old_type} -> INTEREST | ${txn.amount} | {txn.description[:50]}")
        
        # Commit changes
        total_updated = len(cash_movement_transactions) + len(internal_transfers) + len(gold_fees) + len(gold_boost)
        
        if total_updated > 0:
            # Auto-confirm for non-interactive mode
            import sys
            if '--yes' in sys.argv or not sys.stdin.isatty():
                print(f"\nAuto-confirming update of {total_updated} transactions...")
                db.commit()
                print(f"✓ Successfully updated {total_updated} transactions")
            else:
                confirm = input(f"\nUpdate {total_updated} transactions? (y/n): ")
                if confirm.lower() == 'y':
                    db.commit()
                    print(f"\n✓ Successfully updated {total_updated} transactions")
                else:
                    db.rollback()
                    print("\n✗ Cancelled - no changes made")
        else:
            print("\nNo transactions to update")
            
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate_transaction_types()
