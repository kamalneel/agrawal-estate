"""
Weekly Recommendation Filter

Implements the logic for:
- Maximum 3 recommendations per week
- One recommendation per day
- Only send if new recommendation is better (higher profit) than previous ones
- Track recommendations sent this week
"""

import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.modules.strategies.models import WeeklyRecommendationTracking

logger = logging.getLogger(__name__)


def get_week_start_date(d: Optional[date] = None) -> date:
    """Get the Monday of the week for a given date."""
    if d is None:
        d = date.today()
    # Monday is 0, so subtract days to get to Monday
    days_since_monday = d.weekday()
    return d - timedelta(days=days_since_monday)


def get_recommendations_sent_this_week(
    db: Session,
    strategy_type: str
) -> List[Dict[str, Any]]:
    """Get all recommendations sent this week for a strategy."""
    week_start = get_week_start_date()
    
    records = db.query(WeeklyRecommendationTracking).filter(
        WeeklyRecommendationTracking.strategy_type == strategy_type,
        WeeklyRecommendationTracking.week_start_date == week_start
    ).order_by(WeeklyRecommendationTracking.potential_profit.desc()).all()
    
    return [
        {
            "recommendation_id": r.recommendation_id,
            "potential_profit": float(r.potential_profit),
            "sent_at": r.sent_at,
        }
        for r in records
    ]


def get_recommendations_sent_today(
    db: Session,
    strategy_type: str
) -> List[Dict[str, Any]]:
    """Get recommendations sent today for a strategy."""
    today = date.today()
    week_start = get_week_start_date()
    
    records = db.query(WeeklyRecommendationTracking).filter(
        WeeklyRecommendationTracking.strategy_type == strategy_type,
        WeeklyRecommendationTracking.week_start_date == week_start,
        func.date(WeeklyRecommendationTracking.sent_at) == today
    ).all()
    
    return [
        {
            "recommendation_id": r.recommendation_id,
            "potential_profit": float(r.potential_profit),
            "sent_at": r.sent_at,
        }
        for r in records
    ]


def should_send_recommendation(
    db: Session,
    strategy_type: str,
    recommendation: Dict[str, Any],
    min_profit_delta: float = 10.0
) -> tuple[bool, str]:
    """
    Determine if a recommendation should be sent based on weekly limits.
    
    Returns:
        (should_send: bool, reason: str)
    """
    week_recs = get_recommendations_sent_this_week(db, strategy_type)
    today_recs = get_recommendations_sent_today(db, strategy_type)
    
    potential_profit = recommendation.get("context", {}).get("max_profit", 0)
    rec_id = recommendation.get("id", "")
    
    # Check if already sent this week
    if any(r["recommendation_id"] == rec_id for r in week_recs):
        return False, "Already sent this week"
    
    # Check weekly limit (max 3)
    if len(week_recs) >= 3:
        return False, f"Weekly limit reached (3 recommendations already sent)"
    
    # Check daily limit (max 1 per day)
    if len(today_recs) >= 1:
        return False, f"Daily limit reached (1 recommendation already sent today)"
    
    # Check if this is better than previous recommendations
    if len(week_recs) > 0:
        # Get the lowest profit from previous recommendations
        min_previous_profit = min(r["potential_profit"] for r in week_recs)
        
        # Only send if this is significantly better (higher profit)
        if potential_profit <= min_previous_profit + min_profit_delta:
            return False, f"Not better than previous recommendations (profit ${potential_profit:.0f} vs ${min_previous_profit:.0f})"
    
    return True, "OK"


def record_recommendation_sent(
    db: Session,
    strategy_type: str,
    recommendation: Dict[str, Any]
):
    """Record that a recommendation was sent."""
    week_start = get_week_start_date()
    potential_profit = recommendation.get("context", {}).get("max_profit", 0)
    rec_id = recommendation.get("id", "")
    
    tracking = WeeklyRecommendationTracking(
        strategy_type=strategy_type,
        week_start_date=week_start,
        recommendation_id=rec_id,
        potential_profit=potential_profit
    )
    db.add(tracking)
    db.commit()
    
    logger.info(f"Recorded {strategy_type} recommendation {rec_id} sent this week (profit: ${potential_profit:.0f})")

