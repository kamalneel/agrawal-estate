#!/usr/bin/env python3
"""
Backfill script to update existing recommendation_execution_matches with strike and premium data.

This script:
1. Finds all matches with NULL recommended_strike or recommended_premium
2. Re-extracts the data from the recommendation's context_snapshot using the updated logic
3. Updates the matches in the database
"""

import sys
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.modules.strategies.learning_models import RecommendationExecutionMatch
from app.modules.strategies.models import StrategyRecommendationRecord

def extract_strike_from_context(context: dict) -> Decimal | None:
    """Extract strike from context using the updated logic."""
    if not context:
        return None
    
    strike = (
        context.get('strike') or 
        context.get('recommended_strike') or 
        context.get('strike_price') or
        context.get('target_strike') or
        context.get('new_strike')
    )
    
    if strike:
        try:
            return Decimal(str(strike))
        except (ValueError, InvalidOperation):
            return None
    
    return None

def extract_premium_from_context(context: dict) -> Decimal | None:
    """Extract premium from context using the updated logic."""
    if not context:
        return None
    
    # Try premium_per_contract first
    premium = (
        context.get('premium') or 
        context.get('expected_premium') or 
        context.get('premium_per_contract') or
        context.get('target_premium') or
        context.get('potential_premium') or
        context.get('net_credit')
    )
    
    if premium:
        try:
            return Decimal(str(premium))
        except (ValueError, InvalidOperation):
            pass
    
    # If we didn't find per-contract premium, try total_premium and divide by contracts
    if not premium and context.get('total_premium'):
        contracts = context.get('contracts') or context.get('unsold_contracts') or 1
        if contracts > 0:
            try:
                total_premium = float(context.get('total_premium'))
                premium = total_premium / contracts
                return Decimal(str(premium))
            except (ValueError, InvalidOperation, ZeroDivisionError):
                pass
    
    return None

def main():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("Backfilling Match Strike and Premium Data")
        print("=" * 60)
        
        # Find all matches with NULL strike or premium
        matches_to_update = db.query(RecommendationExecutionMatch).filter(
            (RecommendationExecutionMatch.recommended_strike.is_(None)) |
            (RecommendationExecutionMatch.recommended_premium.is_(None))
        ).all()
        
        print(f"\nFound {len(matches_to_update)} matches with missing strike or premium")
        
        updated_count = 0
        skipped_count = 0
        
        for match in matches_to_update:
            try:
                # Get the recommendation record if we have the ID
                rec = None
                if match.recommendation_record_id:
                    rec = db.query(StrategyRecommendationRecord).filter(
                        StrategyRecommendationRecord.id == match.recommendation_record_id
                    ).first()
                
                # If no recommendation record, try to find by recommendation_id
                if not rec and match.recommendation_id:
                    rec = db.query(StrategyRecommendationRecord).filter(
                        StrategyRecommendationRecord.recommendation_id == match.recommendation_id
                    ).first()
                
                if not rec or not rec.context_snapshot:
                    skipped_count += 1
                    continue
                
                context = rec.context_snapshot if isinstance(rec.context_snapshot, dict) else {}
                
                # Extract strike and premium
                new_strike = extract_strike_from_context(context)
                new_premium = extract_premium_from_context(context)
                
                # Only update if we found new values
                updated = False
                if new_strike and not match.recommended_strike:
                    match.recommended_strike = new_strike
                    updated = True
                
                if new_premium and not match.recommended_premium:
                    match.recommended_premium = new_premium
                    updated = True
                
                if updated:
                    updated_count += 1
                    symbol = match.recommended_symbol or 'N/A'
                    strike_str = f"${new_strike}" if new_strike else "N/A"
                    premium_str = f"${new_premium:.2f}" if new_premium else "N/A"
                    print(f"  ✅ Updated {symbol}: strike={strike_str}, premium={premium_str}")
                else:
                    skipped_count += 1
                    
            except Exception as e:
                print(f"  ❌ Error processing match {match.id}: {e}")
                skipped_count += 1
                continue
        
        # Commit all updates
        if updated_count > 0:
            db.commit()
            print(f"\n✅ Successfully updated {updated_count} matches")
        else:
            print(f"\n⚠️  No matches were updated")
        
        print(f"⏭️  Skipped {skipped_count} matches (no recommendation or context data)")
        print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()



