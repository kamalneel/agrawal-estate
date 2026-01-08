#!/usr/bin/env python3
"""
Test Script for RLHF Learning System

This script tests the RLHF system by:
1. Running reconciliation for the past 7 days
2. Generating a weekly summary
3. Displaying the results

Run this to verify the RLHF system is working correctly.
"""

import sys
import os
from datetime import date, timedelta
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.core.database import SessionLocal
from app.modules.strategies.reconciliation_service import ReconciliationService

def test_rlhf_system():
    """Test the RLHF learning system with recent data."""

    db = SessionLocal()
    try:
        print("=" * 70)
        print("RLHF LEARNING SYSTEM TEST")
        print("=" * 70)
        print()

        service = ReconciliationService(db)

        # Test 1: Reconcile past 7 days
        print("📊 TEST 1: Running reconciliation for past 7 days...")
        print()

        today = date.today()
        total_matches = 0

        for i in range(7, 0, -1):
            day = today - timedelta(days=i)
            print(f"  Reconciling {day}...", end=" ")

            result = service.reconcile_day(day)
            matches_saved = result.get("matches_saved", 0)
            total_matches += matches_saved

            print(f"✓ {matches_saved} matches")

        print()
        print(f"✅ Total matches created: {total_matches}")
        print()

        # Test 2: Display match breakdown
        print("📈 TEST 2: Match type breakdown...")
        print()

        from app.modules.strategies.learning_models import RecommendationExecutionMatch
        from sqlalchemy import func

        # Get counts by match type
        match_counts = db.query(
            RecommendationExecutionMatch.match_type,
            func.count(RecommendationExecutionMatch.id)
        ).group_by(RecommendationExecutionMatch.match_type).all()

        if match_counts:
            for match_type, count in match_counts:
                icon = {
                    'consent': '✅',
                    'modify': '✏️',
                    'reject': '❌',
                    'independent': '🆕',
                    'no_action': '⏸️'
                }.get(match_type, '❓')
                print(f"  {icon} {match_type.upper()}: {count}")
        else:
            print("  No matches found yet")

        print()

        # Test 3: Calculate divergence rate
        print("📊 TEST 3: Divergence analysis...")
        print()

        consent = sum(count for mt, count in match_counts if mt == 'consent')
        modify = sum(count for mt, count in match_counts if mt == 'modify')
        reject = sum(count for mt, count in match_counts if mt == 'reject')
        total_with_rec = consent + modify + reject

        if total_with_rec > 0:
            divergence_rate = (modify + reject) / total_with_rec * 100
            consent_rate = consent / total_with_rec * 100

            print(f"  📈 Consent Rate: {consent_rate:.1f}%")
            print(f"  📉 Divergence Rate: {divergence_rate:.1f}%")
            print(f"     ├─ Modified: {modify}")
            print(f"     └─ Rejected: {reject}")
        else:
            print("  Not enough data yet to calculate divergence")

        print()

        # Test 4: Generate weekly summary
        print("📅 TEST 4: Generating weekly summary...")
        print()

        last_week = today - timedelta(days=7)
        iso_cal = last_week.isocalendar()

        try:
            summary = service.generate_weekly_summary(iso_cal.year, iso_cal.week)

            print(f"  Week: {iso_cal.year}-W{iso_cal.week:02d}")
            print(f"  Recommendations: {summary.total_recommendations}")
            print(f"  Executions: {summary.total_executions}")
            print()

            if summary.patterns_observed:
                print(f"  🔍 Patterns Detected: {len(summary.patterns_observed)}")
                for pattern in summary.patterns_observed:
                    print(f"     • {pattern.get('description', 'Unknown pattern')}")
                print()

            if summary.v4_candidates:
                print(f"  💡 V4 Candidates: {len(summary.v4_candidates)}")
                for candidate in summary.v4_candidates:
                    print(f"     • {candidate.get('description', 'Unknown candidate')}")
                print()

        except Exception as e:
            print(f"  ⚠️ Could not generate summary: {e}")
            print()

        # Test 5: Show recent modifications
        print("✏️ TEST 5: Recent modifications...")
        print()

        recent_mods = db.query(RecommendationExecutionMatch).filter(
            RecommendationExecutionMatch.match_type == 'modify',
            RecommendationExecutionMatch.modification_details != None
        ).order_by(RecommendationExecutionMatch.recommendation_date.desc()).limit(5).all()

        if recent_mods:
            for i, match in enumerate(recent_mods, 1):
                symbol = match.recommended_symbol or "Unknown"
                date_str = match.recommendation_date.isoformat() if match.recommendation_date else "Unknown"
                details = match.modification_details or {}

                print(f"  {i}. {symbol} ({date_str})")
                if 'strike_diff' in details:
                    print(f"     Strike: ${details['strike_diff']:+.2f}")
                if 'expiration_diff_days' in details:
                    print(f"     DTE: {details['expiration_diff_days']:+d} days")
                print()
        else:
            print("  No modifications found yet")

        print()
        print("=" * 70)
        print("✅ RLHF SYSTEM TEST COMPLETE!")
        print("=" * 70)
        print()
        print("Next steps:")
        print("1. View detailed matches: http://localhost:8000/api/learning/matches")
        print("2. View weekly summaries: http://localhost:8000/api/learning/weekly-summaries")
        print("3. View divergence analytics: http://localhost:8000/api/learning/analytics/divergence-rate")
        print()
        print("The frontend dashboard is being built next...")
        print()

    except Exception as e:
        print(f"❌ Error testing RLHF system: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

    return True

if __name__ == "__main__":
    success = test_rlhf_system()
    sys.exit(0 if success else 1)
