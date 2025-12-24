#!/usr/bin/env python3
"""
Script to clean up duplicate dividend transactions in the database.

Problem: Dividend transactions were imported multiple times with different
transaction_type codes (CDIV, DIVIDEND, etc.) from different sources.

Solution: Keep only one copy of each unique transaction based on:
- transaction_date
- amount  
- account_id

Prefer keeping CDIV type as canonical (original Robinhood CSV format).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.core.config import settings

DIVIDEND_TYPES = ['DIVIDEND', 'CDIV', 'QUAL DIV REINVEST', 'REINVEST DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND']


def cleanup_duplicate_dividends(dry_run: bool = True):
    """
    Clean up duplicate dividend transactions.
    """
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as conn:
        print("=" * 60)
        print("CURRENT STATE - Dividend Transactions")
        print("=" * 60)
        
        result = conn.execute(text("""
            SELECT transaction_type, COUNT(*) as count, SUM(amount) as total
            FROM investment_transactions
            WHERE transaction_type IN :types
            GROUP BY transaction_type
            ORDER BY total DESC
        """), {"types": tuple(DIVIDEND_TYPES)})
        
        for row in result:
            print(f"  {row.transaction_type}: {row.count} transactions, ${row.total:,.2f}")
        
        # Get total before cleanup
        result = conn.execute(text("""
            SELECT COUNT(*) as count, SUM(amount) as total
            FROM investment_transactions
            WHERE transaction_type IN :types
        """), {"types": tuple(DIVIDEND_TYPES)})
        before = result.fetchone()
        print(f"\n  TOTAL: {before.count} transactions, ${before.total:,.2f}")
        
        print("\n" + "=" * 60)
        print("FINDING DUPLICATES...")
        print("=" * 60)
        
        # Find all duplicate groups - prefer CDIV (original Robinhood format)
        result = conn.execute(text("""
            SELECT 
                transaction_date,
                account_id,
                ROUND(amount::numeric, 2) as amount,
                COUNT(*) as copies,
                STRING_AGG(DISTINCT transaction_type, ', ') as types,
                STRING_AGG(id::text, ', ' ORDER BY 
                    CASE transaction_type 
                        WHEN 'CDIV' THEN 1
                        WHEN 'DIVIDEND' THEN 2
                        WHEN 'CASH DIVIDEND' THEN 3
                        WHEN 'QUALIFIED DIVIDEND' THEN 4
                        WHEN 'QUAL DIV REINVEST' THEN 5
                        WHEN 'REINVEST DIVIDEND' THEN 6
                        ELSE 7
                    END,
                    id
                ) as ids
            FROM investment_transactions
            WHERE transaction_type IN :types
            GROUP BY transaction_date, account_id, ROUND(amount::numeric, 2)
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC, transaction_date DESC
        """), {"types": tuple(DIVIDEND_TYPES)})
        
        duplicates = list(result)
        
        if not duplicates:
            print("  No duplicates found!")
            return
        
        print(f"  Found {len(duplicates)} duplicate groups\n")
        
        # Show first 15 examples
        for row in duplicates[:15]:
            ids = row.ids.split(', ')
            keep_id = ids[0]
            delete_ids = ids[1:]
            
            print(f"  {row.transaction_date} | ${row.amount:,.2f} | {row.account_id}")
            print(f"    Types: {row.types}, Copies: {row.copies}")
            print(f"    Keep ID: {keep_id}, Delete IDs: {', '.join(delete_ids)}")
        
        if len(duplicates) > 15:
            print(f"\n  ... and {len(duplicates) - 15} more duplicate groups")
        
        # Get all IDs to delete
        ids_to_delete = []
        for row in duplicates:
            ids = row.ids.split(', ')
            ids_to_delete.extend(ids[1:])
        
        print(f"\n  Total transactions to delete: {len(ids_to_delete)}")
        
        if dry_run:
            print("\n" + "=" * 60)
            print("DRY RUN - No changes made")
            print("Run with --execute to actually delete duplicates")
            print("=" * 60)
            
            result = conn.execute(text("""
                SELECT COUNT(*) as count, SUM(amount) as total
                FROM investment_transactions
                WHERE transaction_type IN :types
                AND id NOT IN :ids
            """), {"types": tuple(DIVIDEND_TYPES), "ids": tuple(ids_to_delete) if ids_to_delete else (0,)})
            after = result.fetchone()
            
            print(f"\n  After cleanup would be: {after.count} transactions, ${after.total:,.2f}")
            print(f"  Reduction: {before.count - after.count} transactions, ${before.total - after.total:,.2f}")
            
        else:
            print("\n" + "=" * 60)
            print("EXECUTING CLEANUP...")
            print("=" * 60)
            
            if ids_to_delete:
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
            
            result = conn.execute(text("""
                SELECT COUNT(*) as count, SUM(amount) as total
                FROM investment_transactions
                WHERE transaction_type IN :types
            """), {"types": tuple(DIVIDEND_TYPES)})
            after = result.fetchone()
            
            print(f"\n  AFTER CLEANUP:")
            print(f"  Before: {before.count} transactions, ${before.total:,.2f}")
            print(f"  After:  {after.count} transactions, ${after.total:,.2f}")
            print(f"  Removed: {before.count - after.count} duplicates, ${before.total - after.total:,.2f} over-counted")
            
            # Normalize transaction types
            print("\n  Normalizing transaction types (DIVIDEND -> CDIV)...")
            result = conn.execute(text("""
                UPDATE investment_transactions
                SET transaction_type = 'CDIV'
                WHERE transaction_type = 'DIVIDEND'
            """))
            conn.commit()
            print(f"  Updated {result.rowcount} transactions to CDIV type")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Clean up duplicate dividend transactions')
    parser.add_argument('--execute', action='store_true', 
                       help='Actually execute the cleanup (default is dry run)')
    
    args = parser.parse_args()
    
    cleanup_duplicate_dividends(dry_run=not args.execute)


if __name__ == '__main__':
    main()









