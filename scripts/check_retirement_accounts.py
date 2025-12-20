#!/usr/bin/env python3
"""
Check if retirement account income is being incorrectly included in AGI forecast
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.modules.investments.models import InvestmentAccount, InvestmentTransaction
from app.modules.income import db_queries
from sqlalchemy import func, extract, and_, or_

def main():
    db = SessionLocal()
    try:
        print("=" * 80)
        print("CHECKING RETIREMENT ACCOUNT EXCLUSION IN 2025 FORECAST")
        print("=" * 80)
        print()
        
        # Get all accounts
        all_accounts = db.query(InvestmentAccount).all()
        
        print("ALL ACCOUNTS IN DATABASE:")
        print(f"{'Account Name':<40} {'Account Type':<20} {'Account ID'}")
        print("-" * 80)
        
        retirement_accounts = []
        brokerage_accounts = []
        null_type_accounts = []
        
        for acc in all_accounts:
            acc_type = acc.account_type or 'NULL'
            print(f"{acc.account_name or 'N/A':<40} {acc_type:<20} {acc.account_id}")
            
            if acc_type in ['401k', 'ira', 'roth_ira', 'retirement']:
                retirement_accounts.append((acc.account_name, acc.account_id, acc.account_type))
            elif acc_type == 'NULL':
                null_type_accounts.append((acc.account_name, acc.account_id))
            else:
                brokerage_accounts.append((acc.account_name, acc.account_id))
        
        print()
        print("=" * 80)
        print("2025 INCOME BREAKDOWN BY ACCOUNT TYPE")
        print("=" * 80)
        print()
        
        # Check options income
        print("OPTIONS INCOME (STO/BTC transactions):")
        print("-" * 80)
        
        # From retirement accounts (should be 0)
        retirement_options_query = db.query(
            InvestmentAccount.account_name,
            func.sum(InvestmentTransaction.amount).label('total')
        ).join(
            InvestmentAccount,
            and_(
                InvestmentTransaction.account_id == InvestmentAccount.account_id,
                InvestmentTransaction.source == InvestmentAccount.source
            )
        ).filter(
            InvestmentTransaction.transaction_type.in_(['STO', 'BTC']),
            extract('year', InvestmentTransaction.transaction_date) == 2025,
            InvestmentAccount.account_type.in_(['401k', 'ira', 'roth_ira', 'retirement'])
        ).group_by(InvestmentAccount.account_name)
        
        retirement_options = retirement_options_query.all()
        retirement_options_total = sum(float(row.total or 0) for row in retirement_options)
        
        if retirement_options:
            print("⚠️  RETIREMENT ACCOUNTS WITH OPTIONS INCOME (SHOULD BE EXCLUDED):")
            for row in retirement_options:
                print(f"  {row.account_name}: ${float(row.total or 0):,.2f}")
        else:
            print("✓ No options income from retirement accounts")
        print()
        
        # From brokerage accounts (should be included)
        brokerage_options_query = db.query(
            InvestmentAccount.account_name,
            func.sum(InvestmentTransaction.amount).label('total')
        ).join(
            InvestmentAccount,
            and_(
                InvestmentTransaction.account_id == InvestmentAccount.account_id,
                InvestmentTransaction.source == InvestmentAccount.source
            )
        ).filter(
            InvestmentTransaction.transaction_type.in_(['STO', 'BTC']),
            extract('year', InvestmentTransaction.transaction_date) == 2025,
            or_(
                InvestmentAccount.account_type.is_(None),
                InvestmentAccount.account_type == 'brokerage',
                InvestmentAccount.account_type == 'individual',
            )
        ).group_by(InvestmentAccount.account_name)
        
        brokerage_options = brokerage_options_query.all()
        brokerage_options_total = sum(float(row.total or 0) for row in brokerage_options)
        
        print("BROKERAGE ACCOUNTS WITH OPTIONS INCOME (SHOULD BE INCLUDED):")
        for row in brokerage_options:
            print(f"  {row.account_name}: ${float(row.total or 0):,.2f}")
        print()
        
        # Check what get_income_summary returns
        print("=" * 80)
        print("INCOME SUMMARY FROM db_queries.get_income_summary(2025):")
        print("=" * 80)
        summary = db_queries.get_income_summary(db, year=2025)
        print(f"Options Income: ${summary.get('options_income', 0):,.2f}")
        print(f"Dividend Income: ${summary.get('dividend_income', 0):,.2f}")
        print(f"Interest Income: ${summary.get('interest_income', 0):,.2f}")
        print()
        
        # Compare
        print("=" * 80)
        print("VERIFICATION:")
        print("=" * 80)
        print(f"Retirement Accounts Options Income: ${retirement_options_total:,.2f}")
        print(f"Brokerage Accounts Options Income: ${brokerage_options_total:,.2f}")
        print(f"Total Options Income (all accounts): ${retirement_options_total + brokerage_options_total:,.2f}")
        print(f"Income Summary Options Income: ${summary.get('options_income', 0):,.2f}")
        print()
        
        if abs(summary.get('options_income', 0) - brokerage_options_total) > 1:
            print("⚠️  WARNING: Mismatch detected!")
            print("   The income summary might be including retirement accounts.")
        else:
            print("✓ Income summary matches brokerage accounts only (retirement accounts excluded)")
        
        # Check NULL account_type accounts
        if null_type_accounts:
            print()
            print("=" * 80)
            print("ACCOUNTS WITH NULL account_type (treated as brokerage by default):")
            print("=" * 80)
            for name, acc_id in null_type_accounts:
                print(f"  {name} ({acc_id})")
                # Check if this looks like a retirement account
                if any(term in (name or '').lower() for term in ['retirement', '401k', 'ira', 'roth']):
                    print(f"    ⚠️  WARNING: This might be a retirement account but has NULL type!")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()


