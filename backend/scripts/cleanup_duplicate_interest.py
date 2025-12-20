#!/usr/bin/env python3
"""
Script to clean up duplicate interest transactions in the database.

Problem: Interest transactions were imported multiple times with different
transaction_type codes (INT, INTEREST, BANK INTEREST, etc.) from different
sources (CSV exports, PDF statements). This causes income to be double/triple counted.

Solution: Keep only one copy of each unique transaction based on:
- transaction_date
- amount  
- account_id
- description (normalized)

Prefer keeping INT type as canonical (original Robinhood CSV format).
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.core.config import settings


def cleanup_duplicate_interest(dry_run: bool = True):
    """
    Clean up duplicate interest transactions.
    
    Args:
        dry_run: If True, only report what would be deleted. If False, actually delete.
    """
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as conn:
        # First, let's see the current state
        print("=" * 60)
        print("CURRENT STATE - Interest Transactions")
        print("=" * 60)
        
        result = conn.execute(text("""
            SELECT transaction_type, COUNT(*) as count, SUM(amount) as total
            FROM investment_transactions
            WHERE transaction_type IN ('INT', 'INTEREST', 'BANK INTEREST', 'BOND INTEREST')
            GROUP BY transaction_type
            ORDER BY total DESC
        """))
        
        for row in result:
            print(f"  {row.transaction_type}: {row.count} transactions, ${row.total:,.2f}")
        
        # Get total before cleanup
        result = conn.execute(text("""
            SELECT COUNT(*) as count, SUM(amount) as total
            FROM investment_transactions
            WHERE transaction_type IN ('INT', 'INTEREST', 'BANK INTEREST', 'BOND INTEREST')
        """))
        before = result.fetchone()
        print(f"\n  TOTAL: {before.count} transactions, ${before.total:,.2f}")
        
        # Find duplicates - same date, amount, account, with similar descriptions
        # Group by transaction_date, account_id, amount (rounded to cents)
        print("\n" + "=" * 60)
        print("FINDING DUPLICATES...")
        print("=" * 60)
        
        # Find all duplicate groups
        result = conn.execute(text("""
            SELECT 
                transaction_date,
                account_id,
                ROUND(amount::numeric, 2) as amount,
                COUNT(*) as copies,
                STRING_AGG(DISTINCT transaction_type, ', ') as types,
                STRING_AGG(id::text, ', ' ORDER BY 
                    CASE transaction_type 
                        WHEN 'INT' THEN 1  -- Prefer INT (original Robinhood)
                        WHEN 'INTEREST' THEN 2
                        WHEN 'BANK INTEREST' THEN 3
                        WHEN 'BOND INTEREST' THEN 4
                        ELSE 5
                    END,
                    id  -- Then by oldest ID
                ) as ids
            FROM investment_transactions
            WHERE transaction_type IN ('INT', 'INTEREST', 'BANK INTEREST', 'BOND INTEREST')
            GROUP BY transaction_date, account_id, ROUND(amount::numeric, 2)
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC, transaction_date DESC
        """))
        
        duplicates = list(result)
        
        if not duplicates:
            print("  No duplicates found!")
            return
        
        print(f"  Found {len(duplicates)} duplicate groups\n")
        
        # Collect IDs to delete (all except the first in each group)
        ids_to_delete = []
        
        for row in duplicates[:20]:  # Show first 20 examples
            ids = row.ids.split(', ')
            keep_id = ids[0]  # Keep first (preferred) ID
            delete_ids = ids[1:]  # Delete the rest
            ids_to_delete.extend(delete_ids)
            
            print(f"  {row.transaction_date} | ${row.amount:,.2f} | {row.account_id}")
            print(f"    Types: {row.types}, Copies: {row.copies}")
            print(f"    Keep ID: {keep_id}, Delete IDs: {', '.join(delete_ids)}")
        
        if len(duplicates) > 20:
            print(f"\n  ... and {len(duplicates) - 20} more duplicate groups")
        
        # Get all IDs to delete
        ids_to_delete = []
        for row in duplicates:
            ids = row.ids.split(', ')
            ids_to_delete.extend(ids[1:])  # Delete all except first
        
        print(f"\n  Total transactions to delete: {len(ids_to_delete)}")
        
        if dry_run:
            print("\n" + "=" * 60)
            print("DRY RUN - No changes made")
            print("Run with --execute to actually delete duplicates")
            print("=" * 60)
            
            # Calculate what the result would be
            result = conn.execute(text("""
                SELECT COUNT(*) as count, SUM(amount) as total
                FROM investment_transactions
                WHERE transaction_type IN ('INT', 'INTEREST', 'BANK INTEREST', 'BOND INTEREST')
                AND id NOT IN :ids
            """), {"ids": tuple(ids_to_delete) if ids_to_delete else (0,)})
            after = result.fetchone()
            
            print(f"\n  After cleanup would be: {after.count} transactions, ${after.total:,.2f}")
            print(f"  Reduction: {before.count - after.count} transactions, ${before.total - after.total:,.2f}")
            
        else:
            print("\n" + "=" * 60)
            print("EXECUTING CLEANUP...")
            print("=" * 60)
            
            if ids_to_delete:
                # Delete in batches to avoid issues
                batch_size = 100
                deleted_count = 0
                
                for i in range(0, len(ids_to_delete), batch_size):
                    batch = ids_to_delete[i:i + batch_size]
                    result = conn.execute(text("""
                        DELETE FROM investment_transactions
                        WHERE id IN :ids
                    """), {"ids": tuple(batch)})
                    deleted_count += result.rowcount
                
                conn.commit()
                print(f"  Deleted {deleted_count} duplicate transactions")
            
            # Show final state
            result = conn.execute(text("""
                SELECT COUNT(*) as count, SUM(amount) as total
                FROM investment_transactions
                WHERE transaction_type IN ('INT', 'INTEREST', 'BANK INTEREST', 'BOND INTEREST')
            """))
            after = result.fetchone()
            
            print(f"\n  AFTER CLEANUP:")
            print(f"  Before: {before.count} transactions, ${before.total:,.2f}")
            print(f"  After:  {after.count} transactions, ${after.total:,.2f}")
            print(f"  Removed: {before.count - after.count} duplicates, ${before.total - after.total:,.2f} over-counted")
            
            # Also normalize transaction types - change INTEREST to INT for consistency
            print("\n  Normalizing transaction types (INTEREST -> INT)...")
            result = conn.execute(text("""
                UPDATE investment_transactions
                SET transaction_type = 'INT'
                WHERE transaction_type = 'INTEREST'
            """))
            conn.commit()
            print(f"  Updated {result.rowcount} transactions to INT type")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Clean up duplicate interest transactions')
    parser.add_argument('--execute', action='store_true', 
                       help='Actually execute the cleanup (default is dry run)')
    
    args = parser.parse_args()
    
    cleanup_duplicate_interest(dry_run=not args.execute)


if __name__ == '__main__':
    main()







