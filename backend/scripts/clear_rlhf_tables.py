#!/usr/bin/env python3
"""
Clear all RLHF/learning tables to start fresh.

This script deletes all data from:
- recommendation_execution_matches
- position_outcomes
- weekly_learning_summaries
- algorithm_changes

Use this when you want to start fresh with RLHF data collection.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.modules.strategies.learning_models import (
    RecommendationExecutionMatch,
    PositionOutcome,
    WeeklyLearningSummary,
    AlgorithmChange,
)

def main():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("Clearing RLHF/Learning Tables")
        print("=" * 60)
        
        # Count records before deletion
        match_count = db.query(RecommendationExecutionMatch).count()
        outcome_count = db.query(PositionOutcome).count()
        summary_count = db.query(WeeklyLearningSummary).count()
        algorithm_count = db.query(AlgorithmChange).count()
        
        print(f"\nCurrent data:")
        print(f"  - Matches: {match_count}")
        print(f"  - Outcomes: {outcome_count}")
        print(f"  - Weekly Summaries: {summary_count}")
        print(f"  - Algorithm Changes: {algorithm_count}")
        
        # Confirm deletion
        total = match_count + outcome_count + outcome_count + algorithm_count
        if total == 0:
            print("\n✅ All tables are already empty!")
            return
        
        print(f"\n⚠️  About to delete {total} total records from RLHF tables.")
        
        # Allow skipping confirmation via command line argument
        import sys
        if len(sys.argv) > 1 and sys.argv[1] == '--yes':
            print("Proceeding with deletion (--yes flag provided)...")
        else:
            response = input("Are you sure? Type 'yes' to confirm: ")
            if response.lower() != 'yes':
                print("❌ Cancelled. No data was deleted.")
                return
        
        # Delete in order (respecting foreign keys)
        print("\nDeleting data...")
        
        # 1. Delete position outcomes (may reference matches)
        deleted_outcomes = db.query(PositionOutcome).delete()
        print(f"  ✅ Deleted {deleted_outcomes} position outcomes")
        
        # 2. Delete matches
        deleted_matches = db.query(RecommendationExecutionMatch).delete()
        print(f"  ✅ Deleted {deleted_matches} matches")
        
        # 3. Delete weekly summaries
        deleted_summaries = db.query(WeeklyLearningSummary).delete()
        print(f"  ✅ Deleted {deleted_summaries} weekly summaries")
        
        # 4. Delete algorithm changes
        deleted_algorithms = db.query(AlgorithmChange).delete()
        print(f"  ✅ Deleted {deleted_algorithms} algorithm changes")
        
        # Commit
        db.commit()
        
        print("\n" + "=" * 60)
        print("✅ Successfully cleared all RLHF tables!")
        print("=" * 60)
        print("\nYou can now run reconciliation fresh and all new matches")
        print("will have strike and premium data populated correctly.")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()

