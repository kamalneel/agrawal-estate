#!/usr/bin/env python3
"""
Test script to verify reconciliation fix for strike_price and premium extraction.

This script:
1. Generates new recommendations (which will have context_snapshot with strike_price/premium_per_contract)
2. Triggers reconciliation for today's date
3. Checks if the new matches have recommended_strike and recommended_premium populated
"""

import sys
import os
from datetime import date, datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.modules.strategies.strategy_service import StrategyService
from app.modules.strategies.reconciliation_service import get_reconciliation_service
from app.modules.strategies.learning_models import RecommendationExecutionMatch
from sqlalchemy import desc

def main():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("Testing Reconciliation Fix")
        print("=" * 60)
        
        # Step 1: Generate recommendations
        print("\n1. Generating recommendations...")
        service = StrategyService(db)
        recommendations = service.generate_recommendations({
            "default_premium": 60,
            "profit_threshold": 0.80
        })
        print(f"   Generated {len(recommendations)} recommendations")
        
        # Save recommendations to history
        if recommendations:
            from app.modules.strategies.recommendations import OptionsStrategyRecommendationService
            rec_service = OptionsStrategyRecommendationService(db)
            saved_count = rec_service.save_recommendations_to_history(recommendations)
            print(f"   Saved {saved_count} recommendations to history")
            
            # Show a sample recommendation context
            if saved_count > 0:
                from app.modules.strategies.models import StrategyRecommendationRecord
                latest_rec = db.query(StrategyRecommendationRecord).order_by(
                    desc(StrategyRecommendationRecord.created_at)
                ).first()
                if latest_rec and latest_rec.context_snapshot:
                    ctx = latest_rec.context_snapshot
                    print(f"\n   Sample recommendation context keys:")
                    print(f"   - strike_price: {ctx.get('strike_price', 'NOT FOUND')}")
                    print(f"   - premium_per_contract: {ctx.get('premium_per_contract', 'NOT FOUND')}")
                    print(f"   - total_premium: {ctx.get('total_premium', 'NOT FOUND')}")
                    print(f"   - new_strike: {ctx.get('new_strike', 'NOT FOUND')}")
        
        # Step 2: Trigger reconciliation for today
        print("\n2. Triggering reconciliation for today...")
        reconciliation_service = get_reconciliation_service(db)
        today = date.today()
        result = reconciliation_service.reconcile_day(today)
        print(f"   Reconciliation result: {result}")
        
        # Step 3: Check recent matches
        print("\n3. Checking recent matches for populated strike/premium...")
        recent_matches = db.query(RecommendationExecutionMatch).order_by(
            desc(RecommendationExecutionMatch.recommendation_date)
        ).limit(10).all()
        
        print(f"\n   Found {len(recent_matches)} recent matches")
        print("\n   Match Details:")
        print("   " + "-" * 56)
        
        populated_strike = 0
        populated_premium = 0
        
        for match in recent_matches:
            has_strike = match.recommended_strike is not None
            has_premium = match.recommended_premium is not None
            
            if has_strike:
                populated_strike += 1
            if has_premium:
                populated_premium += 1
            
            symbol = match.recommended_symbol or "N/A"
            strike_str = f"${match.recommended_strike}" if has_strike else "$?"
            premium_str = f"${match.recommended_premium:.2f}" if has_premium else "$?"
            
            print(f"   {symbol:6} | Strike: {strike_str:8} | Premium: {premium_str:10} | Type: {match.match_type}")
        
        print("   " + "-" * 56)
        print(f"\n   Summary:")
        print(f"   - Matches with strike populated: {populated_strike}/{len(recent_matches)}")
        print(f"   - Matches with premium populated: {populated_premium}/{len(recent_matches)}")
        
        if populated_strike > 0 or populated_premium > 0:
            print("\n   ✅ SUCCESS: Some matches have strike/premium populated!")
        else:
            print("\n   ⚠️  WARNING: No matches have strike/premium populated yet.")
            print("      This might be because:")
            print("      - No executions matched today's recommendations yet")
            print("      - Recommendations need to be executed first")
            print("      - Check back after trades are executed")
        
        print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()



