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
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Manually trigger reconciliation for a specific date.
    
    Matches recommendations sent on that date to executions.
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)
    
    service = get_reconciliation_service(db)
    result = service.reconcile_day(target_date)
    
    return {
        "status": "success",
        "message": f"Reconciliation completed for {target_date}",
        "result": result
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
    
    matches = query.order_by(
        desc(RecommendationExecutionMatch.recommendation_date)
    ).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "matches": [
            {
                "id": m.id,
                "date": m.recommendation_date.isoformat() if m.recommendation_date else None,
                "match_type": m.match_type,
                "confidence": float(m.match_confidence) if m.match_confidence else None,
                "recommendation": {
                    "id": m.recommendation_id,
                    "type": m.recommendation_type,
                    "action": m.recommended_action,
                    "symbol": m.recommended_symbol,
                    "strike": float(m.recommended_strike) if m.recommended_strike else None,
                    "expiration": m.recommended_expiration.isoformat() if m.recommended_expiration else None,
                    "premium": float(m.recommended_premium) if m.recommended_premium else None,
                    "priority": m.recommendation_priority,
                } if m.recommendation_id else None,
                "execution": {
                    "id": m.execution_id,
                    "date": m.execution_date.isoformat() if m.execution_date else None,
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
                "week": f"{m.year}-W{m.week_number}" if m.year and m.week_number else None,
            }
            for m in matches
        ]
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

