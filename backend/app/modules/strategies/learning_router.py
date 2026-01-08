"""
Learning & RLHF API Endpoints

Provides endpoints for:
1. Viewing reconciliation matches
2. Weekly learning summaries
3. Pattern analysis
4. V4 candidate management
5. Manual reconciliation triggers
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, List
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.timezone import format_datetime_for_api
from app.modules.strategies.learning_models import (
    RecommendationExecutionMatch,
    PositionOutcome,
    WeeklyLearningSummary,
    AlgorithmChange,
)
from app.modules.strategies.reconciliation_service import (
    ReconciliationService,
    get_reconciliation_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/learning", tags=["Learning & RLHF"])


# =============================================================================
# RECONCILIATION ENDPOINTS
# =============================================================================

@router.post("/reconcile")
async def trigger_reconciliation(
    target_date: Optional[date] = Query(default=None, description="Date to reconcile (defaults to yesterday)"),
    days_back: Optional[int] = Query(default=None, description="Number of days to reconcile (alternative to target_date)"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Manually trigger reconciliation for a specific date or date range.
    
    - If days_back is provided, reconciles from (today - days_back) through yesterday
    - If target_date is provided, reconciles just that single date
    - If neither, defaults to yesterday only
    """
    service = get_reconciliation_service(db)
    
    if days_back is not None:
        # Reconcile a range of days
        results = []
        total_matches = 0
        for i in range(days_back, 0, -1):
            day = date.today() - timedelta(days=i)
            result = service.reconcile_day(day)
            results.append({"date": day.isoformat(), **result})
            total_matches += result.get("matches_saved", 0)
        
        return {
            "status": "success",
            "message": f"Reconciliation completed for {days_back} days",
            "total_matches_saved": total_matches,
            "days_reconciled": len(results),
            "results": results
        }
    else:
        # Single day reconciliation
        if target_date is None:
            target_date = date.today() - timedelta(days=1)
        
        result = service.reconcile_day(target_date)
        
        return {
            "status": "success",
            "message": f"Reconciliation completed for {target_date}",
            "result": result
        }


@router.delete("/clear-matches")
async def clear_all_matches(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Clear all RLHF match data to start fresh.
    
    Use this when resetting the learning system after algorithm changes.
    """
    from app.modules.strategies.learning_models import (
        PositionOutcome,
        WeeklyLearningSummary,
        AlgorithmChange,
    )
    
    # Count before deletion
    match_count = db.query(RecommendationExecutionMatch).count()
    outcome_count = db.query(PositionOutcome).count()
    summary_count = db.query(WeeklyLearningSummary).count()
    
    # Delete in order (respecting foreign keys)
    db.query(PositionOutcome).delete()
    db.query(RecommendationExecutionMatch).delete()
    db.query(WeeklyLearningSummary).delete()
    db.commit()
    
    logger.info(f"Cleared RLHF data: {match_count} matches, {outcome_count} outcomes, {summary_count} summaries")
    
    return {
        "status": "success",
        "message": "All RLHF match data cleared",
        "deleted": {
            "matches": match_count,
            "outcomes": outcome_count,
            "summaries": summary_count
        }
    }


@router.post("/track-outcomes")
async def trigger_outcome_tracking(
    as_of_date: Optional[date] = Query(default=None, description="Track outcomes as of this date"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Trigger position outcome tracking.
    
    Checks completed positions and records their outcomes.
    """
    if as_of_date is None:
        as_of_date = date.today()
    
    service = get_reconciliation_service(db)
    result = service.track_position_outcomes(as_of_date)
    
    return {
        "status": "success",
        "message": f"Outcome tracking completed as of {as_of_date}",
        "result": result
    }


@router.get("/matches")
async def get_matches(
    start_date: Optional[date] = Query(default=None, description="Start date filter"),
    end_date: Optional[date] = Query(default=None, description="End date filter"),
    match_type: Optional[str] = Query(default=None, description="Filter by match type"),
    symbol: Optional[str] = Query(default=None, description="Filter by symbol"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get reconciliation matches with optional filters.
    
    Returns list of recommendation-to-execution matches.
    """
    query = db.query(RecommendationExecutionMatch)
    
    if start_date:
        query = query.filter(RecommendationExecutionMatch.recommendation_date >= start_date)
    if end_date:
        query = query.filter(RecommendationExecutionMatch.recommendation_date <= end_date)
    if match_type:
        query = query.filter(RecommendationExecutionMatch.match_type == match_type)
    if symbol:
        query = query.filter(
            RecommendationExecutionMatch.recommended_symbol.ilike(f'%{symbol}%')
        )
    
    total = query.count()
    
    # Count unreviewed matches
    unreviewed_count = query.filter(
        RecommendationExecutionMatch.reviewed_at.is_(None)
    ).count()
    
    # Sort: unreviewed first (by date desc), then reviewed (by date desc)
    # Use CASE to prioritize unreviewed: NULL reviewed_at = 0 (first), else 1
    from sqlalchemy import case
    matches = query.order_by(
        case((RecommendationExecutionMatch.reviewed_at.is_(None), 0), else_=1),
        desc(RecommendationExecutionMatch.recommendation_date)
    ).offset(offset).limit(limit).all()
    
    # Pre-fetch recommendations for fallback lookup
    from app.modules.strategies.models import StrategyRecommendationRecord
    recommendation_ids = [m.recommendation_record_id for m in matches if m.recommendation_record_id]
    recommendations_by_id = {}
    if recommendation_ids:
        recs = db.query(StrategyRecommendationRecord).filter(
            StrategyRecommendationRecord.id.in_(recommendation_ids)
        ).all()
        recommendations_by_id = {rec.id: rec for rec in recs}
    
    def extract_strike_from_context(context):
        """Extract strike using updated logic."""
        if not context or not isinstance(context, dict):
            return None
        strike = (
            context.get('strike') or 
            context.get('recommended_strike') or 
            context.get('strike_price') or
            context.get('target_strike') or
            context.get('new_strike')
        )
        return float(strike) if strike else None
    
    def extract_premium_from_context(context):
        """Extract premium using updated logic."""
        if not context or not isinstance(context, dict):
            return None
        
        # For roll recommendations, prioritize new_premium (premium for the new position)
        # Check roll-specific keys first
        premium = (
            context.get('new_premium') or  # Premium for new position in roll
            context.get('estimated_new_premium') or  # Alternative key for new premium
            context.get('new_premium_income') or  # Income from new position
            # Standard premium keys
            context.get('premium') or 
            context.get('expected_premium') or 
            context.get('premium_per_contract') or
            context.get('target_premium') or
            context.get('potential_premium') or
            context.get('net_credit')
        )
        
        # If we found a premium, return it
        if premium:
            return float(premium)
        
        # Try total_premium / contracts
        if context.get('total_premium'):
            contracts = context.get('contracts') or context.get('unsold_contracts') or 1
            if contracts > 0:
                return float(context.get('total_premium')) / contracts
        
        return None
    
    matches_data = []
    for m in matches:
        # Start with match data
        rec_strike = float(m.recommended_strike) if m.recommended_strike else None
        rec_premium = float(m.recommended_premium) if m.recommended_premium else None
        
        # Fallback: extract from recommendation context if match has NULL values
        if (rec_strike is None or rec_premium is None) and m.recommendation_record_id:
            rec = recommendations_by_id.get(m.recommendation_record_id)
            if rec and rec.context_snapshot:
                context = rec.context_snapshot
                if rec_strike is None:
                    rec_strike = extract_strike_from_context(context)
                if rec_premium is None:
                    rec_premium = extract_premium_from_context(context)
        
        # Extract contracts and account_name from match or recommendation context
        rec_contracts = m.recommended_contracts
        rec_account = None
        if m.recommendation_record_id:
            rec = recommendations_by_id.get(m.recommendation_record_id)
            if rec:
                # Get account_name from recommendation record or context
                rec_account = rec.account_name
                if not rec_account and rec.context_snapshot:
                    context = rec.context_snapshot
                    rec_account = context.get('account_name') or context.get('account')
                # Get contracts from context if not in match
                if rec_contracts is None and rec.context_snapshot:
                    context = rec.context_snapshot
                    rec_contracts = context.get('contracts') or context.get('unsold_contracts')
        
        match_data = {
            "id": m.id,
            "date": m.recommendation_date.isoformat() if m.recommendation_date else None,
            "match_type": m.match_type,
            "confidence": float(m.match_confidence) if m.match_confidence else None,
            "recommendation": {
                "id": m.recommendation_id,
                "type": m.recommendation_type,
                "action": m.recommended_action,
                "symbol": m.recommended_symbol,
                "strike": rec_strike,
                "expiration": m.recommended_expiration.isoformat() if m.recommended_expiration else None,
                "premium": rec_premium,
                "contracts": int(rec_contracts) if rec_contracts else None,
                "account": rec_account,
                "priority": m.recommendation_priority,
                "date": m.recommendation_date.isoformat() if m.recommendation_date else None,
                "time": m.recommendation_time.isoformat() if m.recommendation_time else None,
            } if m.recommendation_id else None,
            "execution": {
                "id": m.execution_id,
                "date": m.execution_date.isoformat() if m.execution_date else None,
                "time": m.execution_time.isoformat() if m.execution_time else None,
                "action": m.execution_action,
                "symbol": m.execution_symbol,
                "strike": float(m.execution_strike) if m.execution_strike else None,
                "expiration": m.execution_expiration.isoformat() if m.execution_expiration else None,
                "premium": float(m.execution_premium) if m.execution_premium else None,
                "contracts": m.execution_contracts,
                "account": m.execution_account,
            } if m.execution_id else None,
            "modification": m.modification_details if m.modification_details else None,
            "hours_to_execution": float(m.hours_to_execution) if m.hours_to_execution else None,
            "user_reason": m.user_reason_code,
            "reviewed_at": m.reviewed_at.isoformat() if m.reviewed_at else None,
            "week": f"{m.year}-W{m.week_number}" if m.year and m.week_number else None,
        }
        matches_data.append(match_data)
    
    return {
        "total": total,
        "unreviewed_count": unreviewed_count,
        "matches": matches_data
    }


@router.get("/matches/{match_id}")
async def get_match_detail(
    match_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Get detailed information about a specific match."""
    match = db.query(RecommendationExecutionMatch).filter(
        RecommendationExecutionMatch.id == match_id
    ).first()
    
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    # Get outcome if available
    outcome = db.query(PositionOutcome).filter(
        PositionOutcome.match_id == match_id
    ).first()
    
    return {
        "match": {
            "id": match.id,
            "date": match.recommendation_date.isoformat() if match.recommendation_date else None,
            "match_type": match.match_type,
            "confidence": float(match.match_confidence) if match.match_confidence else None,
            "recommendation_context": match.recommendation_context,
            "modification_details": match.modification_details,
            "market_conditions_at_rec": match.market_conditions_at_rec,
            "market_conditions_at_exec": match.market_conditions_at_exec,
            "hours_to_execution": float(match.hours_to_execution) if match.hours_to_execution else None,
            "user_reason_code": match.user_reason_code,
            "user_reason_text": match.user_reason_text,
            "notes": match.notes,
        },
        "outcome": {
            "id": outcome.id,
            "symbol": outcome.symbol,
            "strike": float(outcome.strike),
            "expiration": outcome.expiration_date.isoformat(),
            "option_type": outcome.option_type,
            "contracts": outcome.contracts,
            "final_status": outcome.final_status,
            "premium_received": float(outcome.premium_received) if outcome.premium_received else None,
            "premium_paid_to_close": float(outcome.premium_paid_to_close) if outcome.premium_paid_to_close else None,
            "net_profit": float(outcome.net_profit) if outcome.net_profit else None,
            "profit_percent": float(outcome.profit_percent) if outcome.profit_percent else None,
            "days_held": outcome.days_held,
            "counterfactual": outcome.counterfactual_outcome,
            "deviation_assessment": outcome.deviation_assessment,
            "learning_value": outcome.learning_value,
            "learning_notes": outcome.learning_notes,
        } if outcome else None
    }


@router.patch("/matches/{match_id}/reason")
async def update_match_reason(
    match_id: int,
    reason_code: str = Query(..., description="Reason code for the deviation"),
    reason_text: Optional[str] = Query(default=None, description="Free-form explanation"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Add or update the user's reason for a match.
    
    Reason codes:
    - timing: Timing-related decision
    - premium_low: Premium was too low
    - iv_low: IV was too low
    - earnings_concern: Worried about earnings
    - gut_feeling: Intuition-based decision
    - better_opportunity: Found a better trade
    - risk_too_high: Risk was unacceptable
    - already_exposed: Already had exposure to symbol
    - other: Other reason (use reason_text)
    """
    match = db.query(RecommendationExecutionMatch).filter(
        RecommendationExecutionMatch.id == match_id
    ).first()
    
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    valid_codes = [
        'timing', 'premium_low', 'iv_low', 'earnings_concern',
        'gut_feeling', 'better_opportunity', 'risk_too_high',
        'already_exposed', 'other', 'skipped'
    ]
    
    if reason_code not in valid_codes:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid reason code. Must be one of: {valid_codes}"
        )
    
    match.user_reason_code = reason_code
    match.user_reason_text = reason_text
    match.updated_at = datetime.utcnow()
    
    db.commit()
    
    return {
        "status": "success",
        "message": "Reason updated",
        "match_id": match_id,
        "reason_code": reason_code
    }


@router.patch("/matches/{match_id}/review")
async def mark_match_reviewed(
    match_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Mark a match as reviewed/acknowledged by the user.
    
    This allows feed-like UX where reviewed items sink to the bottom.
    """
    match = db.query(RecommendationExecutionMatch).filter(
        RecommendationExecutionMatch.id == match_id
    ).first()
    
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    match.reviewed_at = datetime.utcnow()
    match.updated_at = datetime.utcnow()
    
    db.commit()
    
    return {
        "status": "success",
        "message": "Match marked as reviewed",
        "match_id": match_id,
        "reviewed_at": match.reviewed_at.isoformat()
    }


@router.patch("/matches/review-all")
async def mark_all_matches_reviewed(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Mark all unreviewed matches as reviewed.
    
    Useful for "Mark all as read" functionality.
    """
    updated = db.query(RecommendationExecutionMatch).filter(
        RecommendationExecutionMatch.reviewed_at.is_(None)
    ).update(
        {"reviewed_at": datetime.utcnow(), "updated_at": datetime.utcnow()},
        synchronize_session=False
    )
    
    db.commit()
    
    return {
        "status": "success",
        "message": f"Marked {updated} matches as reviewed",
        "count": updated
    }


# =============================================================================
# WEEKLY SUMMARY ENDPOINTS
# =============================================================================

@router.get("/weekly-summaries")
async def get_weekly_summaries(
    year: Optional[int] = Query(default=None),
    limit: int = Query(default=10, le=52),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Get list of weekly learning summaries."""
    query = db.query(WeeklyLearningSummary)
    
    if year:
        query = query.filter(WeeklyLearningSummary.year == year)
    
    summaries = query.order_by(
        desc(WeeklyLearningSummary.year),
        desc(WeeklyLearningSummary.week_number)
    ).limit(limit).all()
    
    return {
        "summaries": [
            {
                "id": s.id,
                "year": s.year,
                "week": s.week_number,
                "week_label": f"{s.year}-W{s.week_number:02d}",
                "date_range": f"{s.week_start.isoformat()} to {s.week_end.isoformat()}",
                "total_recommendations": s.total_recommendations,
                "total_executions": s.total_executions,
                "match_breakdown": {
                    "consent": s.consent_count,
                    "modify": s.modify_count,
                    "reject": s.reject_count,
                    "independent": s.independent_count,
                    "no_action": s.no_action_count,
                },
                "actual_pnl": float(s.actual_pnl) if s.actual_pnl else None,
                "algorithm_pnl": float(s.algorithm_hypothetical_pnl) if s.algorithm_hypothetical_pnl else None,
                "pnl_delta": float(s.pnl_delta) if s.pnl_delta else None,
                "patterns_count": len(s.patterns_observed) if s.patterns_observed else 0,
                "v4_candidates_count": len(s.v4_candidates) if s.v4_candidates else 0,
                "review_status": s.review_status,
            }
            for s in summaries
        ]
    }


@router.get("/weekly-summaries/{year}/{week}")
async def get_weekly_summary_detail(
    year: int,
    week: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Get detailed weekly learning summary."""
    summary = db.query(WeeklyLearningSummary).filter(
        WeeklyLearningSummary.year == year,
        WeeklyLearningSummary.week_number == week
    ).first()
    
    if not summary:
        raise HTTPException(status_code=404, detail="Weekly summary not found")
    
    return {
        "id": summary.id,
        "year": summary.year,
        "week": summary.week_number,
        "week_start": summary.week_start.isoformat(),
        "week_end": summary.week_end.isoformat(),
        
        "recommendations": {
            "total": summary.total_recommendations,
            "by_type": summary.recommendations_by_type,
        },
        
        "executions": {
            "total": summary.total_executions,
        },
        
        "match_breakdown": {
            "consent": summary.consent_count,
            "consent_pct": round(summary.consent_count / max(summary.total_recommendations, 1) * 100, 1),
            "modify": summary.modify_count,
            "modify_pct": round(summary.modify_count / max(summary.total_recommendations, 1) * 100, 1),
            "reject": summary.reject_count,
            "reject_pct": round(summary.reject_count / max(summary.total_recommendations, 1) * 100, 1),
            "independent": summary.independent_count,
            "no_action": summary.no_action_count,
        },
        
        "performance": {
            "actual_pnl": float(summary.actual_pnl) if summary.actual_pnl else None,
            "actual_trades": summary.actual_trades,
            "actual_win_rate": float(summary.actual_win_rate) if summary.actual_win_rate else None,
            "algorithm_hypothetical_pnl": float(summary.algorithm_hypothetical_pnl) if summary.algorithm_hypothetical_pnl else None,
            "algorithm_win_rate": float(summary.algorithm_hypothetical_win_rate) if summary.algorithm_hypothetical_win_rate else None,
            "pnl_delta": float(summary.pnl_delta) if summary.pnl_delta else None,
            "delta_explanation": summary.delta_explanation,
            "user_better_count": summary.user_better_count,
            "algorithm_better_count": summary.algorithm_better_count,
            "neutral_count": summary.neutral_count,
        },
        
        "patterns": summary.patterns_observed or [],
        "v4_candidates": summary.v4_candidates or [],
        "symbol_insights": summary.symbol_insights or {},
        
        "review": {
            "status": summary.review_status,
            "notes": summary.review_notes,
            "reviewed_at": summary.reviewed_at.isoformat() if summary.reviewed_at else None,
            "decisions": summary.decisions_made,
        }
    }


@router.post("/weekly-summaries/generate")
async def generate_weekly_summary(
    year: int = Query(..., description="Year"),
    week: int = Query(..., description="ISO week number"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Manually generate a weekly learning summary."""
    service = get_reconciliation_service(db)
    summary = service.generate_weekly_summary(year, week)
    
    return {
        "status": "success",
        "message": f"Generated summary for {year}-W{week}",
        "summary_id": summary.id
    }


@router.patch("/weekly-summaries/{year}/{week}/review")
async def update_weekly_review(
    year: int,
    week: int,
    review_notes: Optional[str] = Query(default=None),
    review_status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Update the review status and notes for a weekly summary."""
    summary = db.query(WeeklyLearningSummary).filter(
        WeeklyLearningSummary.year == year,
        WeeklyLearningSummary.week_number == week
    ).first()
    
    if not summary:
        raise HTTPException(status_code=404, detail="Weekly summary not found")
    
    if review_notes is not None:
        summary.review_notes = review_notes
    
    if review_status:
        if review_status not in ['pending', 'reviewed', 'acted']:
            raise HTTPException(status_code=400, detail="Invalid review status")
        summary.review_status = review_status
        if review_status == 'reviewed':
            summary.reviewed_at = datetime.utcnow()
    
    summary.updated_at = datetime.utcnow()
    db.commit()
    
    return {
        "status": "success",
        "message": "Review updated"
    }


# =============================================================================
# V4 CANDIDATE ENDPOINTS
# =============================================================================

@router.get("/v4-candidates")
async def get_v4_candidates(
    status: Optional[str] = Query(default=None, description="Filter by decision status"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get all V4 algorithm change candidates.
    
    Aggregates candidates from weekly summaries and tracks decisions.
    """
    # Get candidates from recent weekly summaries
    summaries = db.query(WeeklyLearningSummary).filter(
        WeeklyLearningSummary.v4_candidates != None
    ).order_by(desc(WeeklyLearningSummary.year), desc(WeeklyLearningSummary.week_number)).limit(12).all()
    
    # Flatten and deduplicate candidates
    candidates = {}
    for summary in summaries:
        for candidate in (summary.v4_candidates or []):
            cid = candidate.get('candidate_id')
            if cid and cid not in candidates:
                candidate['first_seen_week'] = f"{summary.year}-W{summary.week_number}"
                candidate['last_seen_week'] = f"{summary.year}-W{summary.week_number}"
                candidate['occurrences'] = 1
                candidates[cid] = candidate
            elif cid:
                candidates[cid]['last_seen_week'] = f"{summary.year}-W{summary.week_number}"
                candidates[cid]['occurrences'] += 1
    
    # Get decisions from algorithm_changes table
    changes = db.query(AlgorithmChange).all()
    decisions = {c.change_id: c.decision for c in changes}
    
    # Apply decisions to candidates
    result = []
    for cid, candidate in candidates.items():
        candidate['decision'] = decisions.get(cid)
        if status is None or candidate.get('decision') == status:
            result.append(candidate)
    
    return {
        "candidates": result,
        "total": len(result)
    }


@router.post("/v4-candidates/{candidate_id}/decide")
async def decide_on_v4_candidate(
    candidate_id: str,
    decision: str = Query(..., description="Decision: implement, defer, reject"),
    reason: Optional[str] = Query(default=None, description="Reason for decision"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Record a decision on a V4 candidate.
    
    Decisions:
    - implement: Will be implemented
    - defer: Need more data / wait
    - reject: Won't implement
    """
    if decision not in ['implement', 'defer', 'reject']:
        raise HTTPException(status_code=400, detail="Invalid decision")
    
    # Check if decision already exists
    existing = db.query(AlgorithmChange).filter(
        AlgorithmChange.change_id == candidate_id
    ).first()
    
    if existing:
        existing.decision = decision
        existing.decision_reason = reason
        existing.decided_at = datetime.utcnow()
        existing.updated_at = datetime.utcnow()
    else:
        # Create new change record
        change = AlgorithmChange(
            change_id=candidate_id,
            change_type='parameter',  # Default, can be updated
            from_version='v3.0',
            to_version='v4.0',
            title=f"Candidate: {candidate_id}",
            description=reason or "Decision recorded",
            change_details={},
            decision=decision,
            decision_reason=reason,
            decided_at=datetime.utcnow(),
        )
        db.add(change)
    
    db.commit()
    
    return {
        "status": "success",
        "candidate_id": candidate_id,
        "decision": decision
    }


# =============================================================================
# ANALYTICS ENDPOINTS
# =============================================================================

@router.get("/analytics/divergence-rate")
async def get_divergence_rate(
    days: int = Query(default=30, le=365),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Calculate the divergence rate over a period.
    
    Divergence = (modify + reject) / total recommendations
    """
    start_date = date.today() - timedelta(days=days)
    
    # Get all matches in the period
    all_matches = db.query(RecommendationExecutionMatch).filter(
        RecommendationExecutionMatch.recommendation_date >= start_date
    ).all()
    
    if not all_matches:
        return {"divergence_rate": 0, "sample_size": 0}
    
    # Count each type
    consent = sum(1 for m in all_matches if m.match_type == 'consent')
    modify = sum(1 for m in all_matches if m.match_type == 'modify')
    reject = sum(1 for m in all_matches if m.match_type == 'reject')
    independent = sum(1 for m in all_matches if m.match_type == 'independent')
    
    # Total recommendations (excludes independent actions since those had no recommendation)
    rec_matches = [m for m in all_matches if m.recommendation_id is not None]
    total_with_rec = len(rec_matches)
    
    divergence = (modify + reject) / total_with_rec * 100 if total_with_rec > 0 else 0
    consent_rate = consent / total_with_rec * 100 if total_with_rec > 0 else 0
    
    return {
        "period_days": days,
        "total_recommendations": total_with_rec,
        "total_matches": len(all_matches),  # Total including independent
        "consent": consent,
        "modify": modify,
        "reject": reject,
        "independent": independent,
        "divergence_rate": round(divergence, 1),
        "consent_rate": round(consent_rate, 1),
        "by_week": _group_by_week(all_matches)
    }


@router.get("/analytics/algorithm-accuracy")
async def get_algorithm_accuracy(
    days: int = Query(default=90, le=365),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Calculate algorithm accuracy based on outcomes.
    
    Compares outcomes when user followed algorithm vs when they diverged.
    """
    start_date = date.today() - timedelta(days=days)
    
    # Get matches with outcomes
    matches = db.query(RecommendationExecutionMatch).join(
        PositionOutcome
    ).filter(
        RecommendationExecutionMatch.recommendation_date >= start_date
    ).all()
    
    if not matches:
        return {"message": "No completed outcomes in period", "sample_size": 0}
    
    consent_outcomes = []
    diverge_outcomes = []
    
    for match in matches:
        if match.outcome:
            profit = float(match.outcome.net_profit or 0)
            if match.match_type == 'consent':
                consent_outcomes.append(profit)
            elif match.match_type in ['modify', 'reject']:
                diverge_outcomes.append(profit)
    
    consent_pnl = sum(consent_outcomes)
    diverge_pnl = sum(diverge_outcomes)
    
    consent_win_rate = sum(1 for p in consent_outcomes if p > 0) / max(len(consent_outcomes), 1) * 100
    diverge_win_rate = sum(1 for p in diverge_outcomes if p > 0) / max(len(diverge_outcomes), 1) * 100
    
    return {
        "period_days": days,
        "when_followed": {
            "count": len(consent_outcomes),
            "total_pnl": consent_pnl,
            "avg_pnl": consent_pnl / max(len(consent_outcomes), 1),
            "win_rate": round(consent_win_rate, 1)
        },
        "when_diverged": {
            "count": len(diverge_outcomes),
            "total_pnl": diverge_pnl,
            "avg_pnl": diverge_pnl / max(len(diverge_outcomes), 1),
            "win_rate": round(diverge_win_rate, 1)
        },
        "delta": consent_pnl - diverge_pnl,
        "recommendation": "Follow algorithm more" if consent_pnl > diverge_pnl else "Your modifications are working"
    }


@router.get("/analytics/top-modifications")
async def get_top_modifications(
    days: int = Query(default=90, le=365),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get the most common modifications made by user.
    
    Helps identify consistent preferences for algorithm adjustment.
    """
    start_date = date.today() - timedelta(days=days)
    
    # Get modification matches
    mods = db.query(RecommendationExecutionMatch).filter(
        RecommendationExecutionMatch.recommendation_date >= start_date,
        RecommendationExecutionMatch.match_type == 'modify',
        RecommendationExecutionMatch.modification_details != None
    ).all()
    
    # Analyze modifications
    dte_diffs = []
    strike_diffs = []
    premium_diffs = []
    
    for mod in mods:
        details = mod.modification_details or {}
        if 'expiration_diff_days' in details:
            dte_diffs.append(details['expiration_diff_days'])
        if 'strike_diff' in details:
            strike_diffs.append(details['strike_diff'])
        if 'premium_diff' in details:
            premium_diffs.append(details['premium_diff'])
    
    return {
        "period_days": days,
        "total_modifications": len(mods),
        "dte_modifications": {
            "count": len(dte_diffs),
            "avg_change": sum(dte_diffs) / max(len(dte_diffs), 1),
            "direction": "longer" if sum(dte_diffs) > 0 else "shorter"
        } if dte_diffs else None,
        "strike_modifications": {
            "count": len(strike_diffs),
            "avg_change": sum(strike_diffs) / max(len(strike_diffs), 1),
            "direction": "higher" if sum(strike_diffs) > 0 else "lower"
        } if strike_diffs else None,
        "premium_modifications": {
            "count": len(premium_diffs),
            "avg_change": sum(premium_diffs) / max(len(premium_diffs), 1),
        } if premium_diffs else None,
        "recommendations": _generate_mod_recommendations(dte_diffs, strike_diffs)
    }


def _group_by_week(matches: List[RecommendationExecutionMatch]) -> List[dict]:
    """Group matches by week for trend analysis."""
    weeks = {}
    for m in matches:
        key = f"{m.year}-W{m.week_number}" if m.year and m.week_number else "unknown"
        if key not in weeks:
            weeks[key] = {"consent": 0, "modify": 0, "reject": 0}
        weeks[key][m.match_type] = weeks[key].get(m.match_type, 0) + 1
    
    return [{"week": k, **v} for k, v in sorted(weeks.items())]


def _generate_mod_recommendations(dte_diffs: list, strike_diffs: list) -> List[str]:
    """Generate recommendations based on modification patterns."""
    recs = []
    
    if dte_diffs and len(dte_diffs) >= 5:
        avg = sum(dte_diffs) / len(dte_diffs)
        if avg > 5:
            recs.append(f"Consider increasing default DTE by {avg:.0f} days")
        elif avg < -5:
            recs.append(f"Consider decreasing default DTE by {abs(avg):.0f} days")
    
    if strike_diffs and len(strike_diffs) >= 5:
        avg = sum(strike_diffs) / len(strike_diffs)
        if abs(avg) > 3:
            recs.append(f"Consider adjusting strike selection by ${avg:.0f}")
    
    return recs if recs else ["No strong patterns detected yet"]


# =============================================================================
# V2 SNAPSHOT-BASED RECOMMENDATION ENDPOINTS
# =============================================================================

@router.get("/v2/recommendations")
async def get_v2_recommendations(
    status: Optional[str] = Query(default="active", description="Filter by status: active, resolved, expired"),
    symbol: Optional[str] = Query(default=None, description="Filter by symbol"),
    account: Optional[str] = Query(default=None, description="Filter by account"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get recommendations using the V2 snapshot-based model.
    
    Returns recommendations with their snapshot history.
    """
    from app.modules.strategies.recommendation_models import (
        PositionRecommendation,
        RecommendationSnapshot
    )
    
    query = db.query(PositionRecommendation)
    
    if status:
        query = query.filter(PositionRecommendation.status == status)
    if symbol:
        query = query.filter(PositionRecommendation.symbol.ilike(f'%{symbol}%'))
    if account:
        query = query.filter(PositionRecommendation.account_name.ilike(f'%{account}%'))
    
    total = query.count()
    
    recommendations = query.order_by(
        desc(PositionRecommendation.last_snapshot_at)
    ).offset(offset).limit(limit).all()
    
    result = []
    for rec in recommendations:
        # Get latest snapshot
        latest_snapshot = db.query(RecommendationSnapshot).filter(
            RecommendationSnapshot.recommendation_id == rec.id
        ).order_by(desc(RecommendationSnapshot.snapshot_number)).first()
        
        result.append({
            "id": rec.id,
            "recommendation_id": rec.recommendation_id,
            "symbol": rec.symbol,
            "account_name": rec.account_name,
            "source_strike": float(rec.source_strike) if rec.source_strike else None,
            "source_expiration": rec.source_expiration.isoformat() if rec.source_expiration else None,
            "option_type": rec.option_type,
            "status": rec.status,
            "resolution_type": rec.resolution_type,
            "first_detected_at": rec.first_detected_at.isoformat() if rec.first_detected_at else None,
            "last_snapshot_at": rec.last_snapshot_at.isoformat() if rec.last_snapshot_at else None,
            "resolved_at": rec.resolved_at.isoformat() if rec.resolved_at else None,
            "total_snapshots": rec.total_snapshots,
            "total_notifications_sent": rec.total_notifications_sent,
            "days_active": rec.days_active,
            "latest_snapshot": {
                "snapshot_number": latest_snapshot.snapshot_number,
                "recommended_action": latest_snapshot.recommended_action,
                "priority": latest_snapshot.priority,
                "target_strike": float(latest_snapshot.target_strike) if latest_snapshot.target_strike else None,
                "target_expiration": latest_snapshot.target_expiration.isoformat() if latest_snapshot.target_expiration else None,
                "net_cost": float(latest_snapshot.net_cost) if latest_snapshot.net_cost else None,
                "reason": latest_snapshot.reason,
                "action_changed": latest_snapshot.action_changed,
                "target_changed": latest_snapshot.target_changed,
                "notification_sent": latest_snapshot.notification_sent,
                "evaluated_at": format_datetime_for_api(latest_snapshot.evaluated_at),
            } if latest_snapshot else None
        })
    
    return {
        "total": total,
        "recommendations": result
    }


@router.get("/v2/recommendations/{recommendation_id}")
async def get_v2_recommendation_detail(
    recommendation_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get detailed information about a V2 recommendation including all snapshots.
    """
    from app.modules.strategies.recommendation_models import (
        PositionRecommendation,
        RecommendationSnapshot,
        RecommendationExecution
    )
    
    rec = db.query(PositionRecommendation).filter(
        PositionRecommendation.id == recommendation_id
    ).first()
    
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    
    # Get all snapshots
    snapshots = db.query(RecommendationSnapshot).filter(
        RecommendationSnapshot.recommendation_id == rec.id
    ).order_by(RecommendationSnapshot.snapshot_number).all()
    
    # Get executions
    executions = db.query(RecommendationExecution).filter(
        RecommendationExecution.recommendation_id == rec.id
    ).all()
    
    return {
        "recommendation": {
            "id": rec.id,
            "recommendation_id": rec.recommendation_id,
            "symbol": rec.symbol,
            "account_name": rec.account_name,
            "source_strike": float(rec.source_strike) if rec.source_strike else None,
            "source_expiration": rec.source_expiration.isoformat() if rec.source_expiration else None,
            "option_type": rec.option_type,
            "source_contracts": rec.source_contracts,
            "source_original_premium": float(rec.source_original_premium) if rec.source_original_premium else None,
            "status": rec.status,
            "resolution_type": rec.resolution_type,
            "resolution_notes": rec.resolution_notes,
            "first_detected_at": rec.first_detected_at.isoformat() if rec.first_detected_at else None,
            "last_snapshot_at": rec.last_snapshot_at.isoformat() if rec.last_snapshot_at else None,
            "resolved_at": format_datetime_for_api(rec.resolved_at),
            "total_snapshots": rec.total_snapshots,
            "total_notifications_sent": rec.total_notifications_sent,
            "days_active": rec.days_active,
        },
        "snapshots": [{
            "id": s.id,
            "snapshot_number": s.snapshot_number,
            "evaluated_at": format_datetime_for_api(s.evaluated_at),
            "scan_type": s.scan_type,
            "recommended_action": s.recommended_action,
            "priority": s.priority,
            "decision_state": s.decision_state,
            "reason": s.reason,
            "target_strike": float(s.target_strike) if s.target_strike else None,
            "target_expiration": s.target_expiration.isoformat() if s.target_expiration else None,
            "target_premium": float(s.target_premium) if s.target_premium else None,
            "net_cost": float(s.net_cost) if s.net_cost else None,
            "current_premium": float(s.current_premium) if s.current_premium else None,
            "profit_pct": float(s.profit_pct) if s.profit_pct else None,
            "stock_price": float(s.stock_price) if s.stock_price else None,
            "is_itm": s.is_itm,
            "itm_pct": float(s.itm_pct) if s.itm_pct else None,
            "action_changed": s.action_changed,
            "target_changed": s.target_changed,
            "priority_changed": s.priority_changed,
            "previous_action": s.previous_action,
            "previous_target_strike": float(s.previous_target_strike) if s.previous_target_strike else None,
            "notification_sent": s.notification_sent,
            "notification_sent_at": s.notification_sent_at.isoformat() if s.notification_sent_at else None,
            "notification_decision": s.notification_decision,
        } for s in snapshots],
        "executions": [{
            "id": e.id,
            "snapshot_id": e.snapshot_id,
            "match_type": e.match_type,
            "execution_action": e.execution_action,
            "execution_strike": float(e.execution_strike) if e.execution_strike else None,
            "execution_expiration": e.execution_expiration.isoformat() if e.execution_expiration else None,
            "execution_premium": float(e.execution_premium) if e.execution_premium else None,
            "executed_at": e.executed_at.isoformat() if e.executed_at else None,
            "hours_after_snapshot": float(e.hours_after_snapshot) if e.hours_after_snapshot else None,
            "notification_count_before_action": e.notification_count_before_action,
            "modification_details": e.modification_details,
            "outcome_status": e.outcome_status,
            "outcome_pnl": float(e.outcome_pnl) if e.outcome_pnl else None,
        } for e in executions]
    }


@router.get("/v2/snapshot-timeline/{symbol}")
async def get_snapshot_timeline(
    symbol: str,
    days: int = Query(default=30, le=90, description="Days of history"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get a timeline of all snapshots for a symbol.
    
    Useful for visualizing how recommendations evolved over time.
    """
    from app.modules.strategies.recommendation_models import (
        PositionRecommendation,
        RecommendationSnapshot
    )
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    # Get all recommendations for this symbol
    recs = db.query(PositionRecommendation).filter(
        PositionRecommendation.symbol.ilike(f'%{symbol}%'),
        PositionRecommendation.first_detected_at >= cutoff
    ).all()
    
    rec_ids = [r.id for r in recs]
    
    # Get all snapshots for these recommendations
    snapshots = db.query(RecommendationSnapshot).filter(
        RecommendationSnapshot.recommendation_id.in_(rec_ids)
    ).order_by(RecommendationSnapshot.evaluated_at).all()
    
    timeline = []
    for s in snapshots:
        rec = next((r for r in recs if r.id == s.recommendation_id), None)
        timeline.append({
            "timestamp": format_datetime_for_api(s.evaluated_at),
            "recommendation_id": rec.recommendation_id if rec else None,
            "source_strike": float(rec.source_strike) if rec and rec.source_strike else None,
            "source_expiration": rec.source_expiration.isoformat() if rec and rec.source_expiration else None,
            "snapshot_number": s.snapshot_number,
            "action": s.recommended_action,
            "priority": s.priority,
            "target_strike": float(s.target_strike) if s.target_strike else None,
            "target_expiration": s.target_expiration.isoformat() if s.target_expiration else None,
            "stock_price": float(s.stock_price) if s.stock_price else None,
            "action_changed": s.action_changed,
            "notification_sent": s.notification_sent,
        })
    
    return {
        "symbol": symbol.upper(),
        "period_days": days,
        "total_recommendations": len(recs),
        "total_snapshots": len(snapshots),
        "timeline": timeline
    }


@router.post("/v2/reconcile")
async def trigger_v2_reconciliation(
    target_date: Optional[date] = Query(default=None, description="Date to reconcile (defaults to yesterday)"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Trigger V2 reconciliation for a specific date.
    
    This links executions to the new snapshot-based recommendation model.
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)
    
    service = get_reconciliation_service(db)
    result = service.reconcile_day_v2(target_date)
    
    return {
        "status": "success",
        "message": f"V2 reconciliation completed for {target_date}",
        "result": result
    }


@router.post("/v2/recommendations/{recommendation_id}/act")
async def mark_recommendation_acted(
    recommendation_id: int,
    action_type: str = Query(..., description="Action taken: roll, close, hold, buy_back"),
    new_strike: Optional[float] = Query(None, description="New strike price if rolled"),
    new_expiration: Optional[date] = Query(None, description="New expiration if rolled"),
    notes: Optional[str] = Query(None, description="Optional notes about the action"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Mark a V2 recommendation as acted upon in real-time.
    
    This:
    1. Resolves the current recommendation
    2. If rolled, creates a new recommendation for the new position
    3. Updates notification state
    
    Call this when user takes action on a recommendation.
    The reconciliation service will later validate against actual executions.
    """
    from app.modules.strategies.recommendation_models import PositionRecommendation, RecommendationSnapshot
    from app.modules.strategies.recommendation_service import RecommendationService
    from decimal import Decimal
    
    rec_service = RecommendationService(db)
    
    # Get the recommendation
    rec = db.query(PositionRecommendation).filter(
        PositionRecommendation.id == recommendation_id
    ).first()
    
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    
    if rec.status != 'active':
        raise HTTPException(status_code=400, detail=f"Recommendation is already {rec.status}")
    
    # Resolve the recommendation
    resolution_type = f"user_acted_{action_type.lower()}"
    rec_service.resolve_recommendation(
        recommendation_id=rec.id,
        resolution_type=resolution_type,
        notes=notes or f"User marked as {action_type}"
    )
    
    result = {
        "status": "success",
        "message": f"Recommendation {rec.recommendation_id} resolved as {resolution_type}",
        "resolved_recommendation": {
            "id": rec.id,
            "recommendation_id": rec.recommendation_id,
            "symbol": rec.symbol,
            "account_name": rec.account_name,
            "source_strike": float(rec.source_strike) if rec.source_strike else None,
            "source_expiration": rec.source_expiration.isoformat() if rec.source_expiration else None,
            "resolution_type": resolution_type,
        },
        "new_recommendation": None
    }
    
    # If rolled, create a new recommendation for the new position
    if action_type.lower() == 'roll' and new_strike and new_expiration:
        # Check if there's already an active recommendation for the new position
        existing_new = db.query(PositionRecommendation).filter(
            and_(
                PositionRecommendation.symbol == rec.symbol,
                PositionRecommendation.account_name == rec.account_name,
                PositionRecommendation.source_strike == Decimal(str(new_strike)),
                PositionRecommendation.source_expiration == new_expiration,
                PositionRecommendation.status == 'active'
            )
        ).first()
        
        if existing_new:
            result["message"] += f"; existing recommendation found for new position"
            result["new_recommendation"] = {
                "id": existing_new.id,
                "recommendation_id": existing_new.recommendation_id,
                "symbol": existing_new.symbol,
                "source_strike": float(existing_new.source_strike) if existing_new.source_strike else None,
                "source_expiration": existing_new.source_expiration.isoformat() if existing_new.source_expiration else None,
                "status": "already_exists"
            }
        else:
            # Create placeholder recommendation for the new position
            # The next scan will create a proper snapshot with evaluation
            from app.modules.strategies.recommendation_models import generate_recommendation_id
            
            new_rec_id = generate_recommendation_id(
                symbol=rec.symbol,
                account_name=rec.account_name,
                source_strike=Decimal(str(new_strike)),
                source_expiration=new_expiration,
                option_type=rec.option_type
            )
            
            new_rec = PositionRecommendation(
                recommendation_id=new_rec_id,
                symbol=rec.symbol,
                account_name=rec.account_name,
                source_strike=Decimal(str(new_strike)),
                source_expiration=new_expiration,
                option_type=rec.option_type,
                source_contracts=rec.source_contracts,
                status='active',
                first_detected_at=datetime.utcnow(),
            )
            
            db.add(new_rec)
            db.commit()
            db.refresh(new_rec)
            
            result["message"] += f"; new recommendation created for rolled position"
            result["new_recommendation"] = {
                "id": new_rec.id,
                "recommendation_id": new_rec.recommendation_id,
                "symbol": new_rec.symbol,
                "source_strike": float(new_rec.source_strike) if new_rec.source_strike else None,
                "source_expiration": new_rec.source_expiration.isoformat() if new_rec.source_expiration else None,
                "status": "created"
            }
    
    return result


@router.post("/v2/notifications/send")
async def trigger_v2_notifications(
    mode: str = Query("both", description="Notification mode: verbose, smart, or both"),
    scan_type: Optional[str] = Query(None, description="Scan type identifier"),
    dry_run: bool = Query(False, description="If true, don't actually send notifications"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Trigger V2-native notifications manually.
    
    Useful for testing or forcing a notification outside the scheduled times.
    """
    from app.modules.strategies.v2_notification_service import get_v2_notification_service
    from app.shared.services.notifications import get_notification_service
    
    v2_service = get_v2_notification_service(db)
    notification_service = get_notification_service()
    
    # Get notifications to send
    notifications = v2_service.get_notifications_to_send(mode=mode, scan_type=scan_type)
    
    result = {
        "verbose_count": len(notifications['verbose']),
        "smart_count": len(notifications['smart']),
        "verbose_notifications": [],
        "smart_notifications": [],
        "messages_sent": []
    }
    
    # Add preview data
    for notif in notifications['verbose'][:10]:  # Limit to 10 for response
        result["verbose_notifications"].append({
            "symbol": notif['symbol'],
            "account_name": notif['account_name'],
            "action": notif['action'],
            "snapshot_number": notif['snapshot_number'],
            "priority": notif['priority'],
            "source_strike": notif.get('source_strike'),
            "target_strike": notif.get('target_strike'),
            "action_changed": notif.get('action_changed'),
            "target_changed": notif.get('target_changed'),
        })
    
    for notif in notifications['smart'][:10]:
        result["smart_notifications"].append({
            "symbol": notif['symbol'],
            "account_name": notif['account_name'],
            "action": notif['action'],
            "snapshot_number": notif['snapshot_number'],
            "priority": notif['priority'],
            "source_strike": notif.get('source_strike'),
            "target_strike": notif.get('target_strike'),
            "action_changed": notif.get('action_changed'),
            "target_changed": notif.get('target_changed'),
        })
    
    if dry_run:
        result["status"] = "dry_run"
        result["message"] = "Notifications prepared but not sent"
        
        # Show what would be sent
        if notifications['verbose']:
            result["messages_sent"].append({
                "mode": "verbose",
                "message_preview": v2_service.format_telegram_message(notifications['verbose'], 'verbose')[:500] + "..."
            })
        if notifications['smart']:
            result["messages_sent"].append({
                "mode": "smart",
                "message_preview": v2_service.format_telegram_message(notifications['smart'], 'smart')[:500] + "..."
            })
        
        return result
    
    # Actually send
    sent = []
    
    if mode in ('verbose', 'both') and notifications['verbose']:
        message = v2_service.format_telegram_message(notifications['verbose'], 'verbose')
        if message and notification_service.telegram_enabled:
            success, msg_id = notification_service._send_telegram(message)
            if success:
                for notif in notifications['verbose']:
                    v2_service.mark_snapshot_notified(notif['snapshot_id'], 'verbose', message_id=msg_id)
                sent.append({"mode": "verbose", "count": len(notifications['verbose']), "message_id": msg_id})
    
    if mode in ('smart', 'both') and notifications['smart']:
        message = v2_service.format_telegram_message(notifications['smart'], 'smart')
        if message and notification_service.telegram_enabled:
            success, msg_id = notification_service._send_telegram(message)
            if success:
                for notif in notifications['smart']:
                    v2_service.mark_snapshot_notified(notif['snapshot_id'], 'smart', message_id=msg_id)
                sent.append({"mode": "smart", "count": len(notifications['smart']), "message_id": msg_id})
    
    result["status"] = "sent" if sent else "no_notifications"
    result["message"] = f"Sent {len(sent)} notification(s)"
    result["messages_sent"] = sent
    
    return result


@router.get("/v2/notifications/preview")
async def preview_v2_notifications(
    mode: str = Query("both", description="Notification mode: verbose, smart, or both"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Preview what V2 notifications would look like without sending.
    
    Returns formatted messages for each mode.
    """
    from app.modules.strategies.v2_notification_service import get_v2_notification_service
    
    v2_service = get_v2_notification_service(db)
    notifications = v2_service.get_notifications_to_send(mode=mode)
    
    result = {
        "verbose_count": len(notifications['verbose']),
        "smart_count": len(notifications['smart']),
        "verbose_message": "",
        "smart_message": "",
        "by_account": {}
    }
    
    if notifications['verbose']:
        result["verbose_message"] = v2_service.format_telegram_message(notifications['verbose'], 'verbose')
    
    if notifications['smart']:
        result["smart_message"] = v2_service.format_telegram_message(notifications['smart'], 'smart')
    
    # Group by account for analysis
    from collections import defaultdict
    by_account = defaultdict(lambda: {"verbose": [], "smart": []})
    
    for notif in notifications['verbose']:
        by_account[notif['account_name']]["verbose"].append({
            "symbol": notif['symbol'],
            "action": notif['action'],
            "snapshot": notif['snapshot_number'],
        })
    
    for notif in notifications['smart']:
        by_account[notif['account_name']]["smart"].append({
            "symbol": notif['symbol'],
            "action": notif['action'],
            "snapshot": notif['snapshot_number'],
        })
    
    result["by_account"] = dict(by_account)
    
    return result
