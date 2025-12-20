#!/usr/bin/env python3
"""
Cleanup script for November 2025 dividend duplicates.

Root cause: CSV files with 2024 historical data were imported on 2025-11-27,
but the parser used the Activity Date (download date) instead of the actual
dividend pay date from the description.

This script removes the incorrectly dated November 2025 transactions that are
duplicates of existing 2024 transactions.

Per DATA_INTEGRITY_BEST_PRACTICES.md, this is an acceptable direct database
modification because it's fixing parsing errors in previously ingested data.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.core.config import settings

DIVIDEND_TYPES = ['DIVIDEND', 'CDIV', 'QUAL DIV REINVEST', 'REINVEST DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND']

# Ingestion IDs that contain the problematic data
PROBLEMATIC_INGESTIONS = [14, 69, 72]


def cleanup_november_duplicates(dry_run: bool = True):
    """
    Clean up incorrectly dated November 2025 dividend transactions.
    """
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as conn:
        print("=" * 70)
        print("NOVEMBER 2025 DIVIDEND CLEANUP")
        print("=" * 70)
        
        # Get current state
        result = conn.execute(text("""
            SELECT 
                COUNT(*) as count,
                SUM(amount) as total
            FROM investment_transactions
            WHERE transaction_type IN :types
            AND transaction_date >= '2025-11-01'
            AND transaction_date < '2025-12-01'
        """), {"types": tuple(DIVIDEND_TYPES)})
        
        before = result.fetchone()
        print(f"\nCurrent November 2025 dividends: {before.count} transactions, ${before.total or 0:,.2f}")
        
        # Find transactions to delete (from problematic ingestions)
        print("\n" + "-" * 70)
        print("TRANSACTIONS TO DELETE (from problematic ingestions)")
        print("-" * 70)
        
        result = conn.execute(text("""
            SELECT 
                id,
                transaction_date,
                symbol,
                amount,
                account_id,
                transaction_type,
                ingestion_id,
                description
            FROM investment_transactions
            WHERE transaction_type IN :types
            AND transaction_date >= '2025-11-01'
            AND transaction_date < '2025-12-01'
            AND ingestion_id IN :ingestion_ids
            ORDER BY ingestion_id, amount DESC
        """), {"types": tuple(DIVIDEND_TYPES), "ingestion_ids": tuple(PROBLEMATIC_INGESTIONS)})
        
        to_delete = list(result)
        total_to_remove = sum(row.amount for row in to_delete)
        
        print(f"\nFound {len(to_delete)} transactions to delete (${total_to_remove:,.2f}):\n")
        
        for row in to_delete[:20]:  # Show first 20
            print(f"  ID {row.id}: {row.transaction_date} | {row.symbol or '(blank)':6s} | ${row.amount:>10,.2f} | {row.account_id}")
            if row.description:
                # Highlight the actual date in description
                print(f"           Desc: {row.description[:70]}")
        
        if len(to_delete) > 20:
            print(f"\n  ... and {len(to_delete) - 20} more")
        
        # Also find legitimate November 2025 transactions that should STAY
        print("\n" + "-" * 70)
        print("TRANSACTIONS TO KEEP (legitimate November 2025 dividends)")
        print("-" * 70)
        
        result = conn.execute(text("""
            SELECT 
                id,
                transaction_date,
                symbol,
                amount,
                account_id,
                description
            FROM investment_transactions
            WHERE transaction_type IN :types
            AND transaction_date >= '2025-11-01'
            AND transaction_date < '2025-12-01'
            AND (ingestion_id IS NULL OR ingestion_id NOT IN :ingestion_ids)
            ORDER BY amount DESC
        """), {"types": tuple(DIVIDEND_TYPES), "ingestion_ids": tuple(PROBLEMATIC_INGESTIONS)})
        
        to_keep = list(result)
        total_to_keep = sum(row.amount for row in to_keep)
        
        print(f"\n{len(to_keep)} transactions will remain (${total_to_keep:,.2f}):\n")
        
        for row in to_keep:
            print(f"  ID {row.id}: {row.transaction_date} | {row.symbol or '(blank)':6s} | ${row.amount:>10,.2f} | {row.account_id}")
            if row.description:
                print(f"           Desc: {row.description[:70]}")
        
        # Calculate expected result
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"\n  Before: {before.count} transactions, ${before.total or 0:,.2f}")
        print(f"  To delete: {len(to_delete)} transactions, ${total_to_remove:,.2f}")
        print(f"  After:  {len(to_keep)} transactions, ${total_to_keep:,.2f}")
        
        if dry_run:
            print("\n" + "=" * 70)
            print("DRY RUN - No changes made")
            print("Run with --execute to actually delete these transactions")
            print("=" * 70)
        else:
            print("\n" + "=" * 70)
            print("EXECUTING CLEANUP...")
            print("=" * 70)
            
            if to_delete:
                ids_to_delete = [row.id for row in to_delete]
                
                result = conn.execute(text("""
                    DELETE FROM investment_transactions
                    WHERE id IN :ids
                """), {"ids": tuple(ids_to_delete)})
                
                conn.commit()
                print(f"\n  ✓ Deleted {result.rowcount} duplicate transactions")
                print(f"  ✓ Removed ${total_to_remove:,.2f} from November 2025 dividend totals")
                
                # Verify final state
                result = conn.execute(text("""
                    SELECT 
                        COUNT(*) as count,
                        SUM(amount) as total
                    FROM investment_transactions
                    WHERE transaction_type IN :types
                    AND transaction_date >= '2025-11-01'
                    AND transaction_date < '2025-12-01'
                """), {"types": tuple(DIVIDEND_TYPES)})
                
                after = result.fetchone()
                print(f"\n  FINAL STATE: {after.count} transactions, ${after.total or 0:,.2f}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Clean up incorrectly dated November 2025 dividend duplicates'
    )
    parser.add_argument(
        '--execute', 
        action='store_true',
        help='Actually execute the cleanup (default is dry run)'
    )
    
    args = parser.parse_args()
    
    cleanup_november_duplicates(dry_run=not args.execute)


if __name__ == '__main__':
    main()

