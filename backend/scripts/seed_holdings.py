#!/usr/bin/env python3
"""
Seed script for investment holdings.

Run this script to populate the database with your actual holdings.
Edit the HOLDINGS list below with your real data.

Usage:
    cd backend
    source venv/bin/activate
    python scripts/seed_holdings.py
"""

import sys
from pathlib import Path

# Add the backend app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.modules.investments.services import bulk_import_holdings, get_all_holdings

# =============================================================================
# EDIT YOUR HOLDINGS HERE
# =============================================================================
# Each holding should have:
#   - owner: 'Neel', 'Jaya', or 'Family'
#   - account_type: 'brokerage', 'retirement', 'ira', 'roth_ira', 'hsa'
#   - symbol: Stock/ETF ticker symbol
#   - quantity: Number of shares
#   - current_price: Current price per share (optional, for value calculation)
#   - description: Security name (optional)
#
# Example prices are approximate - update them for accurate portfolio values!
# =============================================================================

HOLDINGS = [
    # ==== NEEL'S BROKERAGE (Individual/Equity Account) ====
    {'owner': 'Neel', 'account_type': 'brokerage', 'symbol': 'AAPL', 'quantity': 1700, 'current_price': 234.00, 'description': 'Apple Inc.'},
    {'owner': 'Neel', 'account_type': 'brokerage', 'symbol': 'NVDA', 'quantity': 200, 'current_price': 141.00, 'description': 'NVIDIA Corp.'},
    {'owner': 'Neel', 'account_type': 'brokerage', 'symbol': 'AVGO', 'quantity': 170, 'current_price': 168.00, 'description': 'Broadcom Inc.'},
    {'owner': 'Neel', 'account_type': 'brokerage', 'symbol': 'IBIT', 'quantity': 700, 'current_price': 57.00, 'description': 'iShares Bitcoin Trust'},
    {'owner': 'Neel', 'account_type': 'brokerage', 'symbol': 'HOOD', 'quantity': 200, 'current_price': 42.00, 'description': 'Robinhood Markets'},
    {'owner': 'Neel', 'account_type': 'brokerage', 'symbol': 'PLTR', 'quantity': 124, 'current_price': 71.00, 'description': 'Palantir Technologies'},
    {'owner': 'Neel', 'account_type': 'brokerage', 'symbol': 'TSLA', 'quantity': 100, 'current_price': 352.00, 'description': 'Tesla Inc.'},
    {'owner': 'Neel', 'account_type': 'brokerage', 'symbol': 'META', 'quantity': 28, 'current_price': 590.00, 'description': 'Meta Platforms'},
    {'owner': 'Neel', 'account_type': 'brokerage', 'symbol': 'BABA', 'quantity': 100, 'current_price': 90.00, 'description': 'Alibaba Group'},
    {'owner': 'Neel', 'account_type': 'brokerage', 'symbol': 'FIG', 'quantity': 100, 'current_price': 35.00, 'description': 'Simplify'},
    {'owner': 'Neel', 'account_type': 'brokerage', 'symbol': 'MSFT', 'quantity': 3, 'current_price': 425.00, 'description': 'Microsoft Corp.'},
    
    # ==== NEEL'S IRA ====
    {'owner': 'Neel', 'account_type': 'ira', 'symbol': 'MSFT', 'quantity': 78, 'current_price': 425.00, 'description': 'Microsoft Corp.'},
    {'owner': 'Neel', 'account_type': 'ira', 'symbol': 'META', 'quantity': 51, 'current_price': 590.00, 'description': 'Meta Platforms'},
    {'owner': 'Neel', 'account_type': 'ira', 'symbol': 'PLTR', 'quantity': 174, 'current_price': 71.00, 'description': 'Palantir Technologies'},
    {'owner': 'Neel', 'account_type': 'ira', 'symbol': 'MU', 'quantity': 100, 'current_price': 98.00, 'description': 'Micron Technology'},
    {'owner': 'Neel', 'account_type': 'ira', 'symbol': 'TSM', 'quantity': 100, 'current_price': 195.00, 'description': 'Taiwan Semiconductor'},
    {'owner': 'Neel', 'account_type': 'ira', 'symbol': 'NFLX', 'quantity': 16, 'current_price': 940.00, 'description': 'Netflix Inc.'},
    {'owner': 'Neel', 'account_type': 'ira', 'symbol': 'RKLB', 'quantity': 100, 'current_price': 28.00, 'description': 'Rocket Lab USA'},
    {'owner': 'Neel', 'account_type': 'ira', 'symbol': 'MSTR', 'quantity': 37, 'current_price': 475.00, 'description': 'MicroStrategy'},
    {'owner': 'Neel', 'account_type': 'ira', 'symbol': 'AVGO', 'quantity': 10, 'current_price': 168.00, 'description': 'Broadcom Inc.'},
    {'owner': 'Neel', 'account_type': 'ira', 'symbol': 'AAPL', 'quantity': 5, 'current_price': 234.00, 'description': 'Apple Inc.'},
    
    # ==== NEEL'S 401K/RETIREMENT ====
    {'owner': 'Neel', 'account_type': 'retirement', 'symbol': 'PLTR', 'quantity': 211, 'current_price': 71.00, 'description': 'Palantir Technologies'},
    {'owner': 'Neel', 'account_type': 'retirement', 'symbol': 'HOOD', 'quantity': 200, 'current_price': 42.00, 'description': 'Robinhood Markets'},
    {'owner': 'Neel', 'account_type': 'retirement', 'symbol': 'MSTR', 'quantity': 60, 'current_price': 475.00, 'description': 'MicroStrategy'},
    {'owner': 'Neel', 'account_type': 'retirement', 'symbol': 'VOO', 'quantity': 18, 'current_price': 560.00, 'description': 'Vanguard S&P 500 ETF'},
    {'owner': 'Neel', 'account_type': 'retirement', 'symbol': 'AVGO', 'quantity': 10, 'current_price': 168.00, 'description': 'Broadcom Inc.'},
    {'owner': 'Neel', 'account_type': 'retirement', 'symbol': 'GOOG', 'quantity': 10, 'current_price': 180.00, 'description': 'Alphabet Inc.'},
    {'owner': 'Neel', 'account_type': 'retirement', 'symbol': 'COIN', 'quantity': 1, 'current_price': 310.00, 'description': 'Coinbase Global'},
    
    # ==== JAYA'S BROKERAGE (Individual/Equity Account) ====
    # NOTE: You mentioned Jaya has NO Walt Disney - so not including DIS here
    {'owner': 'Jaya', 'account_type': 'brokerage', 'symbol': 'IBIT', 'quantity': 200, 'current_price': 57.00, 'description': 'iShares Bitcoin Trust'},
    # Add Jaya's other brokerage holdings here
    
    # ==== JAYA'S IRA ====
    {'owner': 'Jaya', 'account_type': 'ira', 'symbol': 'COIN', 'quantity': 92, 'current_price': 310.00, 'description': 'Coinbase Global'},
    # Add Jaya's other IRA holdings here
    
    # ==== FAMILY HSA (if applicable) ====
    # {'owner': 'Family', 'account_type': 'hsa', 'symbol': 'VTI', 'quantity': 100, 'current_price': 280.00, 'description': 'Vanguard Total Stock Market ETF'},
]


def main():
    """Run the seed script."""
    print("=" * 60)
    print("Investment Holdings Seed Script")
    print("=" * 60)
    print()
    
    db = SessionLocal()
    
    try:
        # Import holdings
        print(f"Importing {len(HOLDINGS)} holdings...")
        stats = bulk_import_holdings(db, HOLDINGS)
        
        print(f"\nResults:")
        print(f"  Created: {stats['created']}")
        print(f"  Updated: {stats['updated']}")
        print(f"  Errors:  {stats['errors']}")
        
        # Display current state
        print("\n" + "=" * 60)
        print("Current Holdings Summary")
        print("=" * 60)
        
        accounts = get_all_holdings(db)
        
        total_value = 0
        for acc in accounts:
            print(f"\n{acc['name']} ({acc['owner']}):")
            print(f"  Account Type: {acc['type']}")
            print(f"  Total Value: ${acc['value']:,.2f}")
            print(f"  Holdings: {len(acc['holdings'])}")
            
            total_value += acc['value']
            
            for h in acc['holdings'][:5]:  # Show top 5
                print(f"    - {h['symbol']}: {h['shares']:,.2f} shares @ ${h['currentPrice']:.2f} = ${h['totalValue']:,.2f}")
            
            if len(acc['holdings']) > 5:
                print(f"    ... and {len(acc['holdings']) - 5} more")
        
        print("\n" + "=" * 60)
        print(f"TOTAL PORTFOLIO VALUE: ${total_value:,.2f}")
        print("=" * 60)
        
    finally:
        db.close()


if __name__ == '__main__':
    main()















