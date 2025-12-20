#!/usr/bin/env python3
"""
Diagnostic script to investigate the November 2025 dividend income spike.

User reports: ~$500/month normally but $5000 in November 2025.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.core.config import settings

DIVIDEND_TYPES = ['DIVIDEND', 'CDIV', 'QUAL DIV REINVEST', 'REINVEST DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND']


def diagnose_november_dividends():
    """Diagnose the November 2025 dividend spike."""
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as conn:
        print("=" * 70)
        print("MONTHLY DIVIDEND INCOME - 2025")
        print("=" * 70)
        
        # Monthly totals for 2025
        result = conn.execute(text("""
            SELECT 
                TO_CHAR(transaction_date, 'YYYY-MM') as month,
                COUNT(*) as count,
                SUM(amount) as total
            FROM investment_transactions
            WHERE transaction_type IN :types
            AND EXTRACT(YEAR FROM transaction_date) = 2025
            GROUP BY TO_CHAR(transaction_date, 'YYYY-MM')
            ORDER BY month
        """), {"types": tuple(DIVIDEND_TYPES)})
        
        monthly_data = list(result)
        for row in monthly_data:
            flag = " <-- ANOMALY!" if row.total and row.total > 1000 else ""
            print(f"  {row.month}: {row.count:3d} transactions, ${row.total or 0:,.2f}{flag}")
        
        print("\n" + "=" * 70)
        print("NOVEMBER 2025 - DETAILED BREAKDOWN BY ACCOUNT")
        print("=" * 70)
        
        result = conn.execute(text("""
            SELECT 
                account_id,
                COUNT(*) as count,
                SUM(amount) as total
            FROM investment_transactions
            WHERE transaction_type IN :types
            AND transaction_date >= '2025-11-01'
            AND transaction_date < '2025-12-01'
            GROUP BY account_id
            ORDER BY SUM(amount) DESC
        """), {"types": tuple(DIVIDEND_TYPES)})
        
        for row in result:
            print(f"  {row.account_id}: {row.count} txns, ${row.total or 0:,.2f}")
        
        print("\n" + "=" * 70)
        print("NOVEMBER 2025 - ALL DIVIDEND TRANSACTIONS")
        print("=" * 70)
        
        result = conn.execute(text("""
            SELECT 
                transaction_date,
                symbol,
                amount,
                account_id,
                transaction_type,
                description,
                id
            FROM investment_transactions
            WHERE transaction_type IN :types
            AND transaction_date >= '2025-11-01'
            AND transaction_date < '2025-12-01'
            ORDER BY transaction_date, symbol, amount DESC
        """), {"types": tuple(DIVIDEND_TYPES)})
        
        transactions = list(result)
        print(f"  Total: {len(transactions)} transactions\n")
        
        for row in transactions:
            print(f"  {row.transaction_date} | {row.symbol:6s} | ${row.amount:>10,.2f} | {row.account_id} | {row.transaction_type}")
            if row.description:
                print(f"           Description: {row.description[:80]}")
        
        print("\n" + "=" * 70)
        print("CHECKING FOR POTENTIAL DUPLICATES IN NOVEMBER")
        print("=" * 70)
        
        # Find potential duplicates based on date + amount + account
        result = conn.execute(text("""
            SELECT 
                transaction_date,
                account_id,
                ROUND(amount::numeric, 2) as amount,
                COUNT(*) as copies,
                STRING_AGG(DISTINCT transaction_type, ', ') as types,
                STRING_AGG(DISTINCT symbol, ', ') as symbols,
                STRING_AGG(id::text, ', ') as ids
            FROM investment_transactions
            WHERE transaction_type IN :types
            AND transaction_date >= '2025-11-01'
            AND transaction_date < '2025-12-01'
            GROUP BY transaction_date, account_id, ROUND(amount::numeric, 2)
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC, amount DESC
        """), {"types": tuple(DIVIDEND_TYPES)})
        
        duplicates = list(result)
        
        if not duplicates:
            print("  No duplicates found based on date + amount + account!")
            print("\n  This may be REAL dividend income. Possible causes:")
            print("  - Special dividend payouts")
            print("  - Annual/quarterly distributions")
            print("  - Year-end fund distributions")
        else:
            print(f"  Found {len(duplicates)} potential duplicate groups:\n")
            total_duplicate_amount = 0
            for row in duplicates:
                # Each duplicate over 1 copy represents overcounted amount
                overcounted = row.amount * (row.copies - 1)
                total_duplicate_amount += overcounted
                print(f"  {row.transaction_date} | ${row.amount:,.2f} | {row.account_id}")
                print(f"    Copies: {row.copies}, Types: {row.types}, Symbols: {row.symbols}")
                print(f"    IDs: {row.ids}")
                print(f"    Overcounted: ${overcounted:,.2f}")
                print()
            
            print(f"\n  TOTAL OVERCOUNTED DUE TO DUPLICATES: ${total_duplicate_amount:,.2f}")
        
        print("\n" + "=" * 70)
        print("INGESTION LOG CHECK - November files")
        print("=" * 70)
        
        # Check what files were ingested
        result = conn.execute(text("""
            SELECT 
                id,
                file_name,
                file_path,
                ingested_at,
                record_count,
                status
            FROM ingestion_log
            WHERE ingested_at >= '2025-11-01'
            ORDER BY ingested_at DESC
            LIMIT 20
        """))
        
        logs = list(result)
        if logs:
            for row in logs:
                print(f"  {row.ingested_at} | {row.file_name}")
                print(f"    Path: {row.file_path}, Records: {row.record_count}, Status: {row.status}")
        else:
            print("  No ingestion logs found for November")


if __name__ == '__main__':
    diagnose_november_dividends()

