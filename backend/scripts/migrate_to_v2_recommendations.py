#!/usr/bin/env python3
"""
Migration Script: Migrate Historical Data to V2 Recommendation Model

This script migrates existing data from the legacy `strategy_recommendations`
table to the new V2 model (`position_recommendations` + `recommendation_snapshots`).

Usage:
    python scripts/migrate_to_v2_recommendations.py [--dry-run] [--days 30]

Options:
    --dry-run    Preview what would be migrated without making changes
    --days N     Only migrate recommendations from the last N days (default: all)
"""

import sys
import os
import argparse
from datetime import datetime, date, timedelta
from decimal import Decimal
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.modules.strategies.models import StrategyRecommendationRecord, RecommendationNotification
from app.modules.strategies.recommendation_models import (
    PositionRecommendation,
    RecommendationSnapshot,
    generate_recommendation_id
)


def migrate_recommendations(db: Session, dry_run: bool = False, days_back: int = None):
    """
    Migrate historical recommendations to the V2 model.
    
    Strategy:
    1. Group legacy recommendations by position identity
    2. Create one PositionRecommendation per unique position
    3. Create RecommendationSnapshots for each legacy recommendation
    
    The key insight is that the legacy table has duplicate entries for
    the same position (one per evaluation), which we now model as snapshots.
    """
    print("=" * 60)
    print("V2 Recommendation Model Migration")
    print("=" * 60)
    
    if dry_run:
        print("\n🔍 DRY RUN MODE - No changes will be made\n")
    
    # Query legacy recommendations
    query = db.query(StrategyRecommendationRecord).filter(
        StrategyRecommendationRecord.context_snapshot.isnot(None)
    )
    
    if days_back:
        cutoff = datetime.utcnow() - timedelta(days=days_back)
        query = query.filter(StrategyRecommendationRecord.created_at >= cutoff)
        print(f"📅 Migrating recommendations from last {days_back} days")
    else:
        print("📅 Migrating all historical recommendations")
    
    query = query.order_by(StrategyRecommendationRecord.created_at)
    legacy_recs = query.all()
    
    print(f"📊 Found {len(legacy_recs)} legacy recommendations to process")
    
    # Group by position identity
    position_groups = defaultdict(list)
    skipped = 0
    
    for rec in legacy_recs:
        context = rec.context_snapshot or {}
        
        # Extract position identity
        symbol = context.get('symbol')
        account_name = context.get('account_name') or context.get('account')
        source_strike = context.get('current_strike') or context.get('strike_price')
        source_expiration_str = context.get('current_expiration') or context.get('expiration_date')
        option_type = context.get('option_type', 'call')
        
        if not symbol or not source_strike or not source_expiration_str:
            skipped += 1
            continue
        
        # Parse expiration
        if isinstance(source_expiration_str, str):
            try:
                source_expiration = date.fromisoformat(source_expiration_str)
            except ValueError:
                skipped += 1
                continue
        else:
            source_expiration = source_expiration_str
        
        # Generate unique position key
        rec_id = generate_recommendation_id(
            symbol, float(source_strike), source_expiration, option_type, account_name or 'Unknown'
        )
        
        position_groups[rec_id].append({
            'legacy_rec': rec,
            'symbol': symbol,
            'account_name': account_name or 'Unknown',
            'source_strike': float(source_strike),
            'source_expiration': source_expiration,
            'option_type': option_type,
            'context': context
        })
    
    print(f"🔑 Grouped into {len(position_groups)} unique position identities")
    print(f"⏭️  Skipped {skipped} recommendations (missing required fields)")
    
    # Process each position group
    created_recommendations = 0
    created_snapshots = 0
    
    for rec_id, entries in position_groups.items():
        # Sort entries by creation time
        entries.sort(key=lambda x: x['legacy_rec'].created_at)
        
        first_entry = entries[0]
        
        if not dry_run:
            # Check if V2 recommendation already exists
            existing = db.query(PositionRecommendation).filter(
                PositionRecommendation.recommendation_id == rec_id
            ).first()
            
            if existing:
                # Skip - already migrated
                continue
            
            # Create PositionRecommendation
            v2_rec = PositionRecommendation(
                recommendation_id=rec_id,
                symbol=first_entry['symbol'],
                account_name=first_entry['account_name'],
                source_strike=Decimal(str(first_entry['source_strike'])),
                source_expiration=first_entry['source_expiration'],
                option_type=first_entry['option_type'],
                source_contracts=first_entry['context'].get('contracts'),
                source_original_premium=Decimal(str(first_entry['context'].get('original_premium'))) if first_entry['context'].get('original_premium') else None,
                status='expired' if first_entry['source_expiration'] < date.today() else 'active',
                first_detected_at=first_entry['legacy_rec'].created_at,
                last_snapshot_at=entries[-1]['legacy_rec'].created_at,
                total_snapshots=len(entries),
                total_notifications_sent=0,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            db.add(v2_rec)
            db.flush()  # Get the ID
            
            created_recommendations += 1
            
            # Create snapshots for each legacy entry
            prev_snapshot = None
            for i, entry in enumerate(entries, 1):
                legacy_rec = entry['legacy_rec']
                context = entry['context']
                
                # Determine action from recommendation type
                action = legacy_rec.action_type.upper() if legacy_rec.action_type else 'UNKNOWN'
                if 'roll' in legacy_rec.recommendation_type.lower():
                    action = 'ROLL_WEEKLY'
                elif 'itm' in legacy_rec.recommendation_type.lower():
                    action = 'ROLL_ITM'
                elif 'pull_back' in legacy_rec.recommendation_type.lower():
                    action = 'PULL_BACK'
                elif 'close' in legacy_rec.recommendation_type.lower():
                    action = 'CLOSE'
                elif 'sell' in legacy_rec.recommendation_type.lower():
                    action = 'SELL'
                
                # Target parameters
                target_strike = context.get('new_strike') or context.get('target_strike')
                target_expiration_str = context.get('new_expiration') or context.get('target_expiration')
                target_expiration = None
                if target_expiration_str:
                    if isinstance(target_expiration_str, str):
                        try:
                            target_expiration = date.fromisoformat(target_expiration_str)
                        except:
                            pass
                    else:
                        target_expiration = target_expiration_str
                
                # Detect changes
                action_changed = prev_snapshot and prev_snapshot.recommended_action != action
                target_changed = prev_snapshot and (
                    prev_snapshot.target_strike != (Decimal(str(target_strike)) if target_strike else None) or
                    prev_snapshot.target_expiration != target_expiration
                )
                priority_changed = prev_snapshot and prev_snapshot.priority != legacy_rec.priority
                
                snapshot = RecommendationSnapshot(
                    recommendation_id=v2_rec.id,
                    snapshot_number=i,
                    evaluated_at=legacy_rec.created_at,
                    scan_type=None,  # Unknown from legacy data
                    
                    recommended_action=action,
                    priority=legacy_rec.priority,
                    decision_state=action,
                    reason=legacy_rec.rationale,
                    
                    target_strike=Decimal(str(target_strike)) if target_strike else None,
                    target_expiration=target_expiration,
                    target_premium=Decimal(str(context.get('target_premium'))) if context.get('target_premium') else None,
                    net_cost=Decimal(str(context.get('net_cost'))) if context.get('net_cost') else None,
                    
                    current_premium=Decimal(str(context.get('current_premium') or context.get('buy_back_cost'))) if context.get('current_premium') or context.get('buy_back_cost') else None,
                    profit_pct=Decimal(str(context.get('profit_percent'))) if context.get('profit_percent') else None,
                    is_itm=context.get('is_itm', False),
                    itm_pct=Decimal(str(context.get('itm_percent'))) if context.get('itm_percent') else None,
                    
                    stock_price=Decimal(str(context.get('current_price'))) if context.get('current_price') else None,
                    
                    action_changed=action_changed,
                    target_changed=target_changed,
                    priority_changed=priority_changed,
                    previous_action=prev_snapshot.recommended_action if prev_snapshot else None,
                    previous_target_strike=prev_snapshot.target_strike if prev_snapshot else None,
                    previous_target_expiration=prev_snapshot.target_expiration if prev_snapshot else None,
                    previous_priority=prev_snapshot.priority if prev_snapshot else None,
                    
                    full_context=context,
                    
                    notification_sent=legacy_rec.notification_sent,
                    notification_sent_at=legacy_rec.notification_sent_at,
                    
                    created_at=datetime.utcnow()
                )
                
                db.add(snapshot)
                created_snapshots += 1
                prev_snapshot = snapshot
        else:
            # Dry run - just count
            created_recommendations += 1
            created_snapshots += len(entries)
    
    if not dry_run:
        db.commit()
        print("\n✅ Migration committed to database")
    
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"📦 Position Recommendations created: {created_recommendations}")
    print(f"📸 Snapshots created: {created_snapshots}")
    print(f"📊 Average snapshots per recommendation: {created_snapshots / max(created_recommendations, 1):.1f}")
    
    if dry_run:
        print("\n💡 Run without --dry-run to apply changes")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate historical recommendations to V2 model"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying database"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Only migrate recommendations from last N days"
    )
    
    args = parser.parse_args()
    
    db = SessionLocal()
    try:
        migrate_recommendations(db, dry_run=args.dry_run, days_back=args.days)
    finally:
        db.close()


if __name__ == "__main__":
    main()


