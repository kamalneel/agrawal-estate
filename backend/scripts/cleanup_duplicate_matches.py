#!/usr/bin/env python3
"""
Clean up duplicate recommendation-execution matches.

Removes duplicate matches, keeping only the most recent one for each unique combination.
"""

import sys
from pathlib import Path
from sqlalchemy import func
from datetime import datetime

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.database import SessionLocal
from app.modules.strategies.learning_models import RecommendationExecutionMatch

def cleanup_duplicates():
    """Remove duplicate matches, keeping the most recent one."""
    db = SessionLocal()
    
    try:
        print("🔍 Finding duplicate matches...")
        
        # Find duplicates based on:
        # 1. recommendation_record_id + execution_id + recommendation_date (for matches with both)
        # 2. recommendation_record_id + recommendation_date + NULL execution_id (for reject/no_action)
        # 3. execution_id + recommendation_date + match_type='independent' (for independent)
        
        # Group 1: Matches with both recommendation and execution
        duplicates_group1 = db.query(
            RecommendationExecutionMatch.recommendation_record_id,
            RecommendationExecutionMatch.execution_id,
            RecommendationExecutionMatch.recommendation_date,
            func.count(RecommendationExecutionMatch.id).label('count'),
            func.max(RecommendationExecutionMatch.id).label('keep_id')
        ).filter(
            RecommendationExecutionMatch.recommendation_record_id.isnot(None),
            RecommendationExecutionMatch.execution_id.isnot(None)
        ).group_by(
            RecommendationExecutionMatch.recommendation_record_id,
            RecommendationExecutionMatch.execution_id,
            RecommendationExecutionMatch.recommendation_date
        ).having(func.count(RecommendationExecutionMatch.id) > 1).all()
        
        deleted_count = 0
        
        for dup in duplicates_group1:
            # Delete all except the most recent (highest ID)
            deleted = db.query(RecommendationExecutionMatch).filter(
                RecommendationExecutionMatch.recommendation_record_id == dup.recommendation_record_id,
                RecommendationExecutionMatch.execution_id == dup.execution_id,
                RecommendationExecutionMatch.recommendation_date == dup.recommendation_date,
                RecommendationExecutionMatch.id != dup.keep_id
            ).delete(synchronize_session=False)
            deleted_count += deleted
            print(f"  Removed {deleted} duplicates for rec_id={dup.recommendation_record_id}, exec_id={dup.execution_id}, date={dup.recommendation_date}")
        
        # Group 2: Reject/no_action matches (recommendation but no execution)
        duplicates_group2 = db.query(
            RecommendationExecutionMatch.recommendation_record_id,
            RecommendationExecutionMatch.recommendation_date,
            RecommendationExecutionMatch.match_type,
            func.count(RecommendationExecutionMatch.id).label('count'),
            func.max(RecommendationExecutionMatch.id).label('keep_id')
        ).filter(
            RecommendationExecutionMatch.recommendation_record_id.isnot(None),
            RecommendationExecutionMatch.execution_id.is_(None)
        ).group_by(
            RecommendationExecutionMatch.recommendation_record_id,
            RecommendationExecutionMatch.recommendation_date,
            RecommendationExecutionMatch.match_type
        ).having(func.count(RecommendationExecutionMatch.id) > 1).all()
        
        for dup in duplicates_group2:
            deleted = db.query(RecommendationExecutionMatch).filter(
                RecommendationExecutionMatch.recommendation_record_id == dup.recommendation_record_id,
                RecommendationExecutionMatch.recommendation_date == dup.recommendation_date,
                RecommendationExecutionMatch.match_type == dup.match_type,
                RecommendationExecutionMatch.execution_id.is_(None),
                RecommendationExecutionMatch.id != dup.keep_id
            ).delete(synchronize_session=False)
            deleted_count += deleted
            print(f"  Removed {deleted} duplicates for rec_id={dup.recommendation_record_id}, date={dup.recommendation_date}, type={dup.match_type}")
        
        # Group 3: Independent executions
        duplicates_group3 = db.query(
            RecommendationExecutionMatch.execution_id,
            RecommendationExecutionMatch.recommendation_date,
            func.count(RecommendationExecutionMatch.id).label('count'),
            func.max(RecommendationExecutionMatch.id).label('keep_id')
        ).filter(
            RecommendationExecutionMatch.execution_id.isnot(None),
            RecommendationExecutionMatch.match_type == 'independent'
        ).group_by(
            RecommendationExecutionMatch.execution_id,
            RecommendationExecutionMatch.recommendation_date
        ).having(func.count(RecommendationExecutionMatch.id) > 1).all()
        
        for dup in duplicates_group3:
            deleted = db.query(RecommendationExecutionMatch).filter(
                RecommendationExecutionMatch.execution_id == dup.execution_id,
                RecommendationExecutionMatch.recommendation_date == dup.recommendation_date,
                RecommendationExecutionMatch.match_type == 'independent',
                RecommendationExecutionMatch.id != dup.keep_id
            ).delete(synchronize_session=False)
            deleted_count += deleted
            print(f"  Removed {deleted} duplicates for exec_id={dup.execution_id}, date={dup.recommendation_date}, type=independent")
        
        db.commit()
        
        print(f"\n✅ Cleanup complete! Removed {deleted_count} duplicate matches.")
        print(f"   Kept the most recent match for each unique combination.")
        
        # Show final count
        total_matches = db.query(RecommendationExecutionMatch).count()
        print(f"\n📊 Total matches remaining: {total_matches}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error during cleanup: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("🧹 Cleaning up duplicate recommendation-execution matches...\n")
    cleanup_duplicates()



