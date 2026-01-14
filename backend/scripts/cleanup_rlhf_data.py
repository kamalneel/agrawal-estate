"""
Script to validate and clean RLHF data.

Usage:
    # Check data health (dry run)
    python scripts/cleanup_rlhf_data.py --check

    # Remove duplicates
    python scripts/cleanup_rlhf_data.py --cleanup-duplicates

    # Remove data before epoch start
    python scripts/cleanup_rlhf_data.py --cleanup-old

    # Full cleanup (duplicates + old data)
    python scripts/cleanup_rlhf_data.py --full-cleanup

    # === NEW: Erroneous Data Handling ===
    # Find recommendations with invalid strikes (> 30% OTM)
    python scripts/cleanup_rlhf_data.py --find-invalid-strikes

    # Mark invalid strike recommendations as excluded (soft delete)
    python scripts/cleanup_rlhf_data.py --exclude-invalid-strikes --no-dry-run

    # Exclude by symbol pattern (e.g., CRCL)
    python scripts/cleanup_rlhf_data.py --exclude-by-pattern "CRCL" --reason algorithm_bug --no-dry-run

    # Show excluded records
    python scripts/cleanup_rlhf_data.py --show-excluded

    # Restore excluded records
    python scripts/cleanup_rlhf_data.py --restore-by-pattern "CRCL" --no-dry-run
"""

import argparse
import sys
from datetime import date, datetime

# Add the parent directory to the path
sys.path.insert(0, '/Users/neelpersonal/Coding-Projects/agrawal-estate-planner/backend')

from sqlalchemy import func as sql_func
from app.core.database import SessionLocal
from app.modules.strategies.learning_models import (
    RecommendationExecutionMatch,
    PositionOutcome,
)
from app.modules.strategies.models import StrategyRecommendationRecord
from app.modules.strategies.algorithm_config import get_rlhf_config


def check_data_health(db):
    """Check the health of RLHF data."""
    print("\n=== RLHF Data Health Check ===\n")

    rlhf_config = get_rlhf_config()
    min_valid_date = rlhf_config["min_valid_date"]

    # Total counts
    total_matches = db.query(RecommendationExecutionMatch).count()
    total_outcomes = db.query(PositionOutcome).count()

    print(f"Algorithm Version: {rlhf_config['algorithm_version']}")
    print(f"Epoch Start Date: {min_valid_date}")
    print(f"\nTotal Matches: {total_matches}")
    print(f"Total Outcomes: {total_outcomes}")

    # Matches by type
    type_counts = db.query(
        RecommendationExecutionMatch.match_type,
        sql_func.count(RecommendationExecutionMatch.id)
    ).group_by(RecommendationExecutionMatch.match_type).all()

    print("\nMatches by Type:")
    for match_type, count in type_counts:
        print(f"  {match_type}: {count}")

    # Find duplicates
    duplicates_query = db.query(
        RecommendationExecutionMatch.recommendation_record_id,
        RecommendationExecutionMatch.recommendation_date,
        sql_func.count(RecommendationExecutionMatch.id).label('count')
    ).filter(
        RecommendationExecutionMatch.recommendation_record_id.isnot(None)
    ).group_by(
        RecommendationExecutionMatch.recommendation_record_id,
        RecommendationExecutionMatch.recommendation_date
    ).having(
        sql_func.count(RecommendationExecutionMatch.id) > 1
    ).all()

    duplicate_count = len(duplicates_query)

    # Matches outside current epoch
    outside_epoch = db.query(RecommendationExecutionMatch).filter(
        RecommendationExecutionMatch.recommendation_date < min_valid_date
    ).count()

    # Matches with missing recommendation_time
    missing_time = db.query(RecommendationExecutionMatch).filter(
        RecommendationExecutionMatch.recommendation_id.isnot(None),
        RecommendationExecutionMatch.recommendation_time.is_(None)
    ).count()

    # Orphaned outcomes
    orphaned_outcomes = db.query(PositionOutcome).filter(
        ~PositionOutcome.match_id.in_(
            db.query(RecommendationExecutionMatch.id)
        )
    ).count()

    print("\n=== Issues ===\n")
    issues = []

    if duplicate_count > 0:
        issues.append(f"- {duplicate_count} duplicate match groups found")
    if outside_epoch > 0:
        issues.append(f"- {outside_epoch} matches before epoch start ({min_valid_date})")
    if missing_time > 0:
        issues.append(f"- {missing_time} matches with recommendation but no timestamp")
    if orphaned_outcomes > 0:
        issues.append(f"- {orphaned_outcomes} orphaned outcomes without parent match")

    if issues:
        for issue in issues:
            print(issue)
    else:
        print("No issues found! Data is healthy.")

    return {
        "duplicates": duplicate_count,
        "outside_epoch": outside_epoch,
        "missing_time": missing_time,
        "orphaned_outcomes": orphaned_outcomes
    }


def cleanup_duplicates(db, dry_run=True):
    """Remove duplicate matches."""
    print("\n=== Cleaning Up Duplicates ===\n")

    # Find duplicate groups
    duplicates_query = db.query(
        RecommendationExecutionMatch.recommendation_record_id,
        RecommendationExecutionMatch.recommendation_date,
        sql_func.count(RecommendationExecutionMatch.id).label('count'),
        sql_func.max(RecommendationExecutionMatch.id).label('keep_id')
    ).filter(
        RecommendationExecutionMatch.recommendation_record_id.isnot(None)
    ).group_by(
        RecommendationExecutionMatch.recommendation_record_id,
        RecommendationExecutionMatch.recommendation_date
    ).having(
        sql_func.count(RecommendationExecutionMatch.id) > 1
    ).all()

    ids_to_delete = []

    for rec_id, rec_date, count, keep_id in duplicates_query:
        group_matches = db.query(RecommendationExecutionMatch).filter(
            RecommendationExecutionMatch.recommendation_record_id == rec_id,
            RecommendationExecutionMatch.recommendation_date == rec_date
        ).order_by(RecommendationExecutionMatch.reconciled_at.desc()).all()

        # Keep the first one (most recently reconciled), delete others
        for i, match in enumerate(group_matches):
            if i > 0:
                ids_to_delete.append(match.id)

        print(f"  {rec_date}: recommendation_record_id={rec_id}, keeping ID={keep_id}, deleting {count-1} duplicates")

    print(f"\nTotal duplicates to remove: {len(ids_to_delete)}")

    if dry_run:
        print("\n[DRY RUN] No changes made. Run with --no-dry-run to execute.")
    elif ids_to_delete:
        # Delete outcomes first
        outcome_count = db.query(PositionOutcome).filter(
            PositionOutcome.match_id.in_(ids_to_delete)
        ).delete(synchronize_session=False)

        # Delete matches
        deleted = db.query(RecommendationExecutionMatch).filter(
            RecommendationExecutionMatch.id.in_(ids_to_delete)
        ).delete(synchronize_session=False)

        db.commit()
        print(f"\nDeleted {deleted} duplicate matches and {outcome_count} associated outcomes.")
    else:
        print("\nNo duplicates to remove.")

    return len(ids_to_delete)


def cleanup_old_data(db, dry_run=True):
    """Remove matches before the epoch start date."""
    print("\n=== Cleaning Up Old Data ===\n")

    rlhf_config = get_rlhf_config()
    min_valid_date = rlhf_config["min_valid_date"]

    # Count old matches
    old_match_ids = [m.id for m in db.query(RecommendationExecutionMatch.id).filter(
        RecommendationExecutionMatch.recommendation_date < min_valid_date
    ).all()]

    match_count = len(old_match_ids)
    outcome_count = db.query(PositionOutcome).filter(
        PositionOutcome.match_id.in_(old_match_ids)
    ).count() if old_match_ids else 0

    print(f"Epoch start date: {min_valid_date}")
    print(f"Matches before epoch: {match_count}")
    print(f"Associated outcomes: {outcome_count}")

    if dry_run:
        print("\n[DRY RUN] No changes made. Run with --no-dry-run to execute.")
    elif old_match_ids:
        # Delete outcomes first
        db.query(PositionOutcome).filter(
            PositionOutcome.match_id.in_(old_match_ids)
        ).delete(synchronize_session=False)

        # Delete matches
        deleted = db.query(RecommendationExecutionMatch).filter(
            RecommendationExecutionMatch.recommendation_date < min_valid_date
        ).delete(synchronize_session=False)

        db.commit()
        print(f"\nDeleted {deleted} old matches and {outcome_count} associated outcomes.")
    else:
        print("\nNo old data to remove.")

    return match_count


# ============================================================================
# NEW: Erroneous Data Handling (Soft Delete via Exclusion)
# ============================================================================

def find_invalid_strike_recommendations(db, max_otm_percent=30.0):
    """
    Find recommendations with strikes that are unreasonably far OTM.

    This detects bugs like the CRCL $265 strike (217% OTM for $83 stock).
    """
    print(f"\n=== Finding Invalid Strike Recommendations (>{max_otm_percent}% OTM) ===\n")

    # Query recommendations with context
    recs = db.query(StrategyRecommendationRecord).filter(
        StrategyRecommendationRecord.recommendation_type.in_([
            'new_covered_call', 'roll_options', 'cash_secured_put'
        ]),
        StrategyRecommendationRecord.context_snapshot.isnot(None),
        StrategyRecommendationRecord.excluded_from_learning == False
    ).order_by(StrategyRecommendationRecord.created_at.desc()).all()

    invalid_recs = []

    for rec in recs:
        context = rec.context_snapshot
        if not context:
            continue

        # Extract price and strike from context
        current_price = context.get('current_price') or context.get('stock_price')
        recommended_strike = context.get('recommended_strike') or context.get('new_strike')

        if not current_price or not recommended_strike:
            continue

        current_price = float(current_price)
        recommended_strike = float(recommended_strike)

        # Calculate OTM percentage
        if rec.recommendation_type in ('new_covered_call', 'roll_options'):
            # For calls: strike above current price is OTM
            if recommended_strike > current_price:
                otm_pct = ((recommended_strike / current_price) - 1) * 100
            else:
                otm_pct = 0  # ITM, not a problem
        else:
            # For puts: strike below current price is OTM
            if recommended_strike < current_price:
                otm_pct = ((current_price / recommended_strike) - 1) * 100
            else:
                otm_pct = 0

        if otm_pct > max_otm_percent:
            invalid_recs.append({
                'record': rec,
                'current_price': current_price,
                'recommended_strike': recommended_strike,
                'otm_percent': otm_pct,
            })

    return invalid_recs


def exclude_invalid_strikes(db, max_otm_percent=30.0, dry_run=True):
    """Mark recommendations with invalid strikes as excluded."""
    print(f"\n=== Excluding Invalid Strike Recommendations (>{max_otm_percent}% OTM) ===\n")

    invalid = find_invalid_strike_recommendations(db, max_otm_percent)

    if not invalid:
        print("No invalid strike recommendations found.")
        return 0

    print(f"Found {len(invalid)} invalid strike recommendations:\n")
    for item in invalid:
        rec = item['record']
        print(f"[{rec.id}] {rec.symbol}: {rec.title[:60]}...")
        print(f"    Stock: ${item['current_price']:.2f}, Strike: ${item['recommended_strike']:.0f}")
        print(f"    OTM: {item['otm_percent']:.1f}% (exceeds {max_otm_percent}%)")
        print()

    if dry_run:
        print("[DRY RUN] No changes made. Run with --no-dry-run to execute.")
        return 0

    now = datetime.utcnow()
    notes = f"Strike > {max_otm_percent}% OTM - likely data bug"

    for item in invalid:
        rec = item['record']
        rec.excluded_from_learning = True
        rec.exclusion_reason = 'algorithm_bug'
        rec.exclusion_notes = notes
        rec.excluded_at = now

        # Also exclude any corresponding RLHF matches
        matches = db.query(RecommendationExecutionMatch).filter(
            RecommendationExecutionMatch.recommendation_record_id == rec.id
        ).all()

        for match in matches:
            match.excluded_from_learning = True
            match.exclusion_reason = 'algorithm_bug'
            match.exclusion_notes = notes
            match.excluded_at = now

    db.commit()
    print(f"Excluded {len(invalid)} recommendations and their RLHF matches.")
    return len(invalid)


def exclude_by_pattern(db, pattern, reason='algorithm_bug', notes=None, dry_run=True):
    """Exclude recommendations matching a symbol or title pattern."""
    print(f"\n=== Excluding Recommendations Matching '{pattern}' ===\n")

    # Find matching recommendations
    recs = db.query(StrategyRecommendationRecord).filter(
        (StrategyRecommendationRecord.symbol.like(f'%{pattern}%')) |
        (StrategyRecommendationRecord.title.like(f'%{pattern}%')),
        StrategyRecommendationRecord.excluded_from_learning == False
    ).all()

    if not recs:
        print(f"No recommendations found matching: {pattern}")
        return 0

    print(f"Found {len(recs)} recommendations matching '{pattern}':\n")
    for rec in recs[:10]:
        print(f"  [{rec.id}] {rec.symbol or 'N/A'}: {rec.title[:60]}...")
    if len(recs) > 10:
        print(f"  ... and {len(recs) - 10} more")

    if dry_run:
        print("\n[DRY RUN] No changes made. Run with --no-dry-run to execute.")
        return 0

    now = datetime.utcnow()
    notes = notes or f"Excluded by pattern: {pattern}"

    for rec in recs:
        rec.excluded_from_learning = True
        rec.exclusion_reason = reason
        rec.exclusion_notes = notes
        rec.excluded_at = now

        # Also exclude RLHF matches
        matches = db.query(RecommendationExecutionMatch).filter(
            RecommendationExecutionMatch.recommendation_record_id == rec.id
        ).all()

        for match in matches:
            match.excluded_from_learning = True
            match.exclusion_reason = reason
            match.exclusion_notes = notes
            match.excluded_at = now

    db.commit()
    print(f"\nExcluded {len(recs)} recommendations.")
    return len(recs)


def show_excluded(db, limit=50):
    """Show excluded recommendations."""
    print(f"\n=== Excluded Recommendations (limit {limit}) ===\n")

    recs = db.query(StrategyRecommendationRecord).filter(
        StrategyRecommendationRecord.excluded_from_learning == True
    ).order_by(StrategyRecommendationRecord.excluded_at.desc()).limit(limit).all()

    if not recs:
        print("No excluded recommendations found.")
        return

    for rec in recs:
        print(f"[{rec.id}] {rec.symbol or 'N/A'}: {rec.title[:50]}...")
        print(f"    Reason: {rec.exclusion_reason} | Notes: {rec.exclusion_notes or 'N/A'}")
        print(f"    Excluded at: {rec.excluded_at}")
        print()


def restore_by_pattern(db, pattern, dry_run=True):
    """Restore (un-exclude) recommendations matching a pattern."""
    print(f"\n=== Restoring Excluded Recommendations Matching '{pattern}' ===\n")

    recs = db.query(StrategyRecommendationRecord).filter(
        (StrategyRecommendationRecord.symbol.like(f'%{pattern}%')) |
        (StrategyRecommendationRecord.title.like(f'%{pattern}%')),
        StrategyRecommendationRecord.excluded_from_learning == True
    ).all()

    if not recs:
        print(f"No excluded recommendations found matching: {pattern}")
        return 0

    print(f"Found {len(recs)} excluded recommendations matching '{pattern}':\n")
    for rec in recs[:10]:
        print(f"  [{rec.id}] {rec.symbol or 'N/A'}: {rec.title[:60]}...")

    if dry_run:
        print("\n[DRY RUN] No changes made. Run with --no-dry-run to execute.")
        return 0

    for rec in recs:
        rec.excluded_from_learning = False
        rec.exclusion_reason = None
        rec.exclusion_notes = None
        rec.excluded_at = None

        # Also restore RLHF matches
        matches = db.query(RecommendationExecutionMatch).filter(
            RecommendationExecutionMatch.recommendation_record_id == rec.id
        ).all()

        for match in matches:
            match.excluded_from_learning = False
            match.exclusion_reason = None
            match.exclusion_notes = None
            match.excluded_at = None

    db.commit()
    print(f"\nRestored {len(recs)} recommendations.")
    return len(recs)


def main():
    parser = argparse.ArgumentParser(description="RLHF Data Cleanup Script")

    # Original arguments
    parser.add_argument("--check", action="store_true", help="Check data health")
    parser.add_argument("--cleanup-duplicates", action="store_true", help="Remove duplicate matches")
    parser.add_argument("--cleanup-old", action="store_true", help="Remove data before epoch start")
    parser.add_argument("--full-cleanup", action="store_true", help="Full cleanup (duplicates + old)")

    # New: Erroneous data handling
    parser.add_argument("--find-invalid-strikes", action="store_true",
                        help="Find recommendations with unreasonably far OTM strikes")
    parser.add_argument("--exclude-invalid-strikes", action="store_true",
                        help="Mark invalid strike recommendations as excluded")
    parser.add_argument("--max-otm-percent", type=float, default=30.0,
                        help="Maximum OTM percentage to consider valid (default: 30)")
    parser.add_argument("--exclude-by-pattern", type=str, metavar="PATTERN",
                        help="Exclude recommendations matching a symbol/title pattern")
    parser.add_argument("--show-excluded", action="store_true",
                        help="Show excluded recommendations")
    parser.add_argument("--restore-by-pattern", type=str, metavar="PATTERN",
                        help="Restore (un-exclude) recommendations matching a pattern")
    parser.add_argument("--reason", type=str, default="algorithm_bug",
                        choices=['algorithm_bug', 'data_source_error', 'parsing_error',
                                 'duplicate', 'test_data', 'manual_review'],
                        help="Reason for exclusion")
    parser.add_argument("--notes", type=str, help="Additional notes about the exclusion")

    # Common
    parser.add_argument("--no-dry-run", action="store_true",
                        help="Actually execute changes (default is dry run)")

    args = parser.parse_args()

    dry_run = not args.no_dry_run

    if dry_run and not args.show_excluded and not args.find_invalid_strikes:
        print("\n*** DRY RUN MODE - No changes will be made ***")
        print("*** Use --no-dry-run to execute changes ***\n")

    db = SessionLocal()

    try:
        # Original operations
        if args.check:
            check_data_health(db)

        if args.cleanup_duplicates or args.full_cleanup:
            cleanup_duplicates(db, dry_run)

        if args.cleanup_old or args.full_cleanup:
            cleanup_old_data(db, dry_run)

        # New: Erroneous data handling
        if args.find_invalid_strikes:
            invalid = find_invalid_strike_recommendations(db, args.max_otm_percent)
            if invalid:
                print(f"Found {len(invalid)} invalid strike recommendations:\n")
                for item in invalid:
                    rec = item['record']
                    print(f"[{rec.id}] {rec.symbol}: {rec.title[:60]}...")
                    print(f"    Stock: ${item['current_price']:.2f}, Strike: ${item['recommended_strike']:.0f}")
                    print(f"    OTM: {item['otm_percent']:.1f}%")
                    print()
            else:
                print("No invalid strike recommendations found.")

        if args.exclude_invalid_strikes:
            exclude_invalid_strikes(db, args.max_otm_percent, dry_run)

        if args.exclude_by_pattern:
            exclude_by_pattern(db, args.exclude_by_pattern, args.reason, args.notes, dry_run)

        if args.show_excluded:
            show_excluded(db)

        if args.restore_by_pattern:
            restore_by_pattern(db, args.restore_by_pattern, dry_run)

        # Default: show help if no action specified
        if not any([args.check, args.cleanup_duplicates, args.cleanup_old, args.full_cleanup,
                    args.find_invalid_strikes, args.exclude_invalid_strikes,
                    args.exclude_by_pattern, args.show_excluded, args.restore_by_pattern]):
            check_data_health(db)

    finally:
        db.close()


if __name__ == "__main__":
    main()
