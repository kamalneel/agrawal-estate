#!/usr/bin/env python3
"""
Script to clean up duplicate options transactions in the database.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.core.config import settings

OPTIONS_TYPES = ['STO', 'BTC', 'OEXP']


def cleanup_duplicate_options(dry_run: bool = True):
    """Clean up duplicate options transactions."""
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as conn:
        print("=" * 60)
        print("CURRENT STATE - Options Transactions")
        print("=" * 60)
        
        result = conn.execute(text("""
            SELECT transaction_type, COUNT(*) as count, SUM(amount) as total
            FROM investment_transactions
            WHERE transaction_type IN :types
            GROUP BY transaction_type
            ORDER BY total DESC
        """), {"types": tuple(OPTIONS_TYPES)})
        
        for row in result:
            print(f"  {row.transaction_type}: {row.count} transactions, ${row.total:,.2f}")
        
        result = conn.execute(text("""
            SELECT COUNT(*) as count, SUM(amount) as total
            FROM investment_transactions
            WHERE transaction_type IN ('STO', 'BTC')
        """))
        before = result.fetchone()
        print(f"\n  TOTAL (STO+BTC): {before.count} transactions, ${before.total:,.2f}")
        
        print("\n" + "=" * 60)
        print("FINDING DUPLICATES...")
        print("=" * 60)
        
        # Find duplicates - for options, also consider symbol in deduplication
        result = conn.execute(text("""
            SELECT 
                transaction_date,
                account_id,
                symbol,
                ROUND(amount::numeric, 2) as amount,
                COUNT(*) as copies,
                STRING_AGG(DISTINCT transaction_type, ', ') as types,
                STRING_AGG(id::text, ', ' ORDER BY id) as ids
            FROM investment_transactions
            WHERE transaction_type IN :types
            GROUP BY transaction_date, account_id, symbol, ROUND(amount::numeric, 2)
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC, transaction_date DESC
        """), {"types": tuple(OPTIONS_TYPES)})
        
        duplicates = list(result)
        
        if not duplicates:
            print("  No duplicates found!")
            return
        
        print(f"  Found {len(duplicates)} duplicate groups\n")
        
        for row in duplicates[:15]:
            ids = row.ids.split(', ')
            keep_id = ids[0]
            delete_ids = ids[1:]
            
            symbol_str = row.symbol or 'N/A'
            print(f"  {row.transaction_date} | {symbol_str[:10]:10s} | ${row.amount:>10,.2f} | {row.account_id}")
            print(f"    Types: {row.types}, Copies: {row.copies}")
            print(f"    Keep ID: {keep_id}, Delete: {len(delete_ids)} IDs")
        
        if len(duplicates) > 15:
            print(f"\n  ... and {len(duplicates) - 15} more duplicate groups")
        
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
                WHERE transaction_type IN ('STO', 'BTC')
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
                WHERE transaction_type IN ('STO', 'BTC')
            """))
            after = result.fetchone()
            
            print(f"\n  AFTER CLEANUP:")
            print(f"  Before: {before.count} transactions, ${before.total:,.2f}")
            print(f"  After:  {after.count} transactions, ${after.total:,.2f}")
            print(f"  Removed: {before.count - after.count} duplicates, ${before.total - after.total:,.2f}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Clean up duplicate options transactions')
    parser.add_argument('--execute', action='store_true', 
                       help='Actually execute the cleanup (default is dry run)')
    
    args = parser.parse_args()
    
    cleanup_duplicate_options(dry_run=not args.execute)


if __name__ == '__main__':
    main()









