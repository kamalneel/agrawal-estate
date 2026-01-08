#!/usr/bin/env python3
"""
Reconcile multiple days at once.

Usage:
    python scripts/reconcile_date_range.py --days 7
    python scripts/reconcile_date_range.py --start 2026-01-01 --end 2026-01-07
"""

import sys
import argparse
from pathlib import Path
from datetime import date, timedelta

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.database import SessionLocal
from app.modules.strategies.reconciliation_service import ReconciliationService

def main():
    parser = argparse.ArgumentParser(description='Reconcile multiple days')
    parser.add_argument('--days', type=int, default=7, help='Number of days to reconcile (default: 7)')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    # Determine date range
    if args.start and args.end:
        start_date = date.fromisoformat(args.start)
        end_date = date.fromisoformat(args.end)
    else:
        end_date = date.today() - timedelta(days=1)  # Yesterday
        start_date = end_date - timedelta(days=args.days - 1)
    
    db = SessionLocal()
    try:
        service = ReconciliationService(db)
        
        print(f"🔄 Reconciling from {start_date} to {end_date}...")
        print("=" * 60)
        
        total_matches = 0
        total_independent = 0
        
        current_date = start_date
        while current_date <= end_date:
            print(f"\n📅 Reconciling {current_date}...")
            result = service.reconcile_day(current_date)
            
            matches = result.get('matches_saved', 0)
            independent = result.get('independent_actions', 0)
            recs = result.get('recommendations_count', 0)
            execs = result.get('executions_count', 0)
            
            print(f"   Recommendations: {recs}, Executions: {execs}")
            print(f"   Matches saved: {matches}, Independent: {independent}")
            
            total_matches += matches
            total_independent += independent
            
            current_date += timedelta(days=1)
        
        print("\n" + "=" * 60)
        print(f"✅ Reconciliation complete!")
        print(f"   Total matches: {total_matches}")
        print(f"   Total independent: {total_independent}")
        print(f"   Total records: {total_matches + total_independent}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()



