"""
Mutual Fund Recommendation Engine - Scores and ranks funds based on technical metrics.
"""

from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


# Scoring weights for the recommendation formula
# These can be adjusted based on investment preferences
SCORING_WEIGHTS = {
    "return_1y": 0.15,      # 15% weight on 1-year returns
    "return_3y": 0.20,      # 20% weight on 3-year returns
    "return_5y": 0.25,      # 25% weight on 5-year returns (most important)
    "return_10y": 0.15,     # 15% weight on 10-year returns
    "sharpe_ratio": 0.15,    # 15% weight on risk-adjusted returns
    "volatility": -0.10,    # -10% weight (lower is better, so negative)
}

# Minimum thresholds for scoring
MIN_RETURN_1Y = 8.0   # Minimum 8% 1-year return
MIN_RETURN_3Y = 10.0  # Minimum 10% 3-year return
MIN_RETURN_5Y = 12.0  # Minimum 12% 5-year return
MIN_SHARPE = 0.5      # Minimum Sharpe ratio


def normalize_score(value: Optional[float], min_val: float, max_val: float, reverse: bool = False) -> float:
    """
    Normalize a value to 0-100 score.
    
    Args:
        value: The value to normalize
        min_val: Minimum expected value
        max_val: Maximum expected value
        reverse: If True, lower values score higher (for volatility)
    
    Returns:
        Score between 0-100
    """
    if value is None:
        return 0
    
    if reverse:
        # For volatility: lower is better
        if value <= min_val:
            return 100
        if value >= max_val:
            return 0
        return 100 * (1 - (value - min_val) / (max_val - min_val))
    else:
        # For returns: higher is better
        if value <= min_val:
            return 0
        if value >= max_val:
            return 100
        return 100 * ((value - min_val) / (max_val - min_val))


def calculate_recommendation_score(fund_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate recommendation score for a mutual fund.
    
    Uses a weighted formula considering:
    - Historical returns (1y, 3y, 5y, 10y)
    - Risk-adjusted returns (Sharpe ratio)
    - Volatility (lower is better)
    
    Returns:
        {
            "score": 75.5,
            "breakdown": {
                "return_1y_score": 80,
                "return_3y_score": 75,
                ...
            },
            "reason": "Strong 5-year returns with good risk-adjusted performance"
        }
    """
    scores = {}
    total_score = 0.0
    
    # Normalize and score each metric
    # Returns scoring (higher is better)
    if fund_data.get("return_1y") is not None:
        score = normalize_score(fund_data["return_1y"], MIN_RETURN_1Y, 30.0)
        scores["return_1y_score"] = score
        total_score += score * SCORING_WEIGHTS["return_1y"]
    
    if fund_data.get("return_3y") is not None:
        score = normalize_score(fund_data["return_3y"], MIN_RETURN_3Y, 25.0)
        scores["return_3y_score"] = score
        total_score += score * SCORING_WEIGHTS["return_3y"]
    
    if fund_data.get("return_5y") is not None:
        score = normalize_score(fund_data["return_5y"], MIN_RETURN_5Y, 22.0)
        scores["return_5y_score"] = score
        total_score += score * SCORING_WEIGHTS["return_5y"]
    
    if fund_data.get("return_10y") is not None:
        score = normalize_score(fund_data["return_10y"], MIN_RETURN_5Y, 20.0)
        scores["return_10y_score"] = score
        total_score += score * SCORING_WEIGHTS["return_10y"]
    
    # Sharpe ratio scoring (higher is better)
    if fund_data.get("sharpe_ratio") is not None:
        score = normalize_score(fund_data["sharpe_ratio"], MIN_SHARPE, 3.0)
        scores["sharpe_ratio_score"] = score
        total_score += score * SCORING_WEIGHTS["sharpe_ratio"]
    
    # Volatility scoring (lower is better, so reverse=True)
    if fund_data.get("volatility") is not None:
        score = normalize_score(fund_data["volatility"], 10.0, 30.0, reverse=True)
        scores["volatility_score"] = score
        total_score += score * abs(SCORING_WEIGHTS["volatility"])
    
    # Generate reason
    reason_parts = []
    if fund_data.get("return_5y") and fund_data["return_5y"] >= 15:
        reason_parts.append("Strong 5-year returns")
    if fund_data.get("sharpe_ratio") and fund_data["sharpe_ratio"] >= 1.0:
        reason_parts.append("good risk-adjusted performance")
    if fund_data.get("volatility") and fund_data["volatility"] <= 15:
        reason_parts.append("low volatility")
    if fund_data.get("return_10y") and fund_data["return_10y"] >= 15:
        reason_parts.append("consistent long-term performance")
    
    reason = ", ".join(reason_parts) if reason_parts else "Moderate performance across metrics"
    
    return {
        "score": round(total_score, 2),
        "breakdown": scores,
        "reason": reason
    }


def calculate_all_scores_and_rank(db: Session, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Calculate scores for all funds and rank them.
    
    Args:
        db: Database session
        category: Optional filter by fund category
    
    Returns:
        List of funds with scores and ranks, sorted by score descending
    """
    from app.modules.india_investments.mf_research_models import MutualFundResearch
    
    query = db.query(MutualFundResearch).filter(MutualFundResearch.is_active == 'Y')
    if category:
        query = query.filter(MutualFundResearch.fund_category == category)
    
    funds = query.all()
    
    results = []
    for fund in funds:
        fund_data = {
            "return_1y": float(fund.return_1y) if fund.return_1y else None,
            "return_3y": float(fund.return_3y) if fund.return_3y else None,
            "return_5y": float(fund.return_5y) if fund.return_5y else None,
            "return_10y": float(fund.return_10y) if fund.return_10y else None,
            "sharpe_ratio": float(fund.sharpe_ratio) if fund.sharpe_ratio else None,
            "volatility": float(fund.volatility) if fund.volatility else None,
        }
        
        recommendation = calculate_recommendation_score(fund_data)
        
        # Update fund with score
        fund.recommendation_score = Decimal(str(recommendation["score"]))
        fund.recommendation_reason = recommendation["reason"]
        
        results.append({
            "id": fund.id,
            "scheme_code": fund.scheme_code,
            "scheme_name": fund.scheme_name,
            "fund_house": fund.fund_house,
            "fund_category": fund.fund_category,
            "scheme_category": fund.scheme_category,
            "current_nav": float(fund.current_nav) if fund.current_nav else None,
            "return_1y": fund_data["return_1y"],
            "return_3y": fund_data["return_3y"],
            "return_5y": fund_data["return_5y"],
            "return_10y": fund_data["return_10y"],
            "sharpe_ratio": fund_data["sharpe_ratio"],
            "volatility": fund_data["volatility"],
            "beta": float(fund.beta) if fund.beta else None,
            "alpha": float(fund.alpha) if fund.alpha else None,
            "aum": float(fund.aum) if fund.aum else None,
            "expense_ratio": float(fund.expense_ratio) if fund.expense_ratio else None,
            "exit_load": fund.exit_load,
            "value_research_rating": fund.value_research_rating,
            "recommendation_score": recommendation["score"],
            "recommendation_rank": None,  # Will be set below
            "recommendation_reason": recommendation["reason"],
            "score_breakdown": recommendation["breakdown"],
        })
    
    # Sort by score descending
    results.sort(key=lambda x: x["recommendation_score"] or 0, reverse=True)
    
    # Assign ranks
    for i, fund in enumerate(results, start=1):
        fund["recommendation_rank"] = i
        # Update rank in database
        db_fund = db.query(MutualFundResearch).filter(
            MutualFundResearch.id == fund["id"]
        ).first()
        if db_fund:
            db_fund.recommendation_rank = i
    
    db.commit()
    
    return results

