"""
Mutual Fund Research API routes.
"""

from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel

from app.core.database import get_db
from app.modules.india_investments.mf_research_models import MutualFundResearch
from app.modules.india_investments.mf_research_service import (
    search_mutual_funds,
    fetch_and_store_fund_data,
)
from app.modules.india_investments.mf_recommendation_engine import (
    calculate_all_scores_and_rank,
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class FundAddRequest(BaseModel):
    scheme_code: str


@router.get("/search")
async def search_funds(
    q: str = Query(..., description="Search query for mutual fund name"),
    db: Session = Depends(get_db)
):
    """Search for mutual funds by name."""
    results = search_mutual_funds(q)
    return {
        "query": q,
        "results": results,
        "count": len(results)
    }


@router.post("/add")
async def add_fund_for_research(
    request: FundAddRequest,
    db: Session = Depends(get_db)
):
    """Add a mutual fund to research/comparison table."""
    try:
        result = fetch_and_store_fund_data(db, request.scheme_code)
        if not result:
            raise HTTPException(status_code=404, detail=f"Fund with scheme code {request.scheme_code} not found")
        
        # Recalculate all scores and ranks
        calculate_all_scores_and_rank(db)
        
        return {
            "success": True,
            "fund": result,
            "message": f"Added {result['scheme_name']} to research"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding fund: {str(e)}")


@router.get("/compare")
async def compare_funds(
    db: Session = Depends(get_db),
    category: Optional[str] = Query(None, description="Filter by fund category"),
    limit: int = Query(50, description="Maximum number of funds to return")
):
    """Get all funds for comparison with scores and ranks."""
    funds = calculate_all_scores_and_rank(db, category=category)
    
    return {
        "funds": funds[:limit],
        "total": len(funds),
        "category": category,
    }


@router.get("/fund/{scheme_code}")
async def get_fund_details(
    scheme_code: str,
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific fund."""
    fund = db.query(MutualFundResearch).filter(
        MutualFundResearch.scheme_code == scheme_code
    ).first()
    
    if not fund:
        raise HTTPException(status_code=404, detail="Fund not found")
    
    return {
        "id": fund.id,
        "scheme_code": fund.scheme_code,
        "scheme_name": fund.scheme_name,
        "fund_house": fund.fund_house,
        "scheme_type": fund.scheme_type,
        "scheme_category": fund.scheme_category,
        "fund_category": fund.fund_category,
        "current_nav": float(fund.current_nav) if fund.current_nav else None,
        "nav_date": fund.nav_date.isoformat() if fund.nav_date else None,
        "return_1y": float(fund.return_1y) if fund.return_1y else None,
        "return_3y": float(fund.return_3y) if fund.return_3y else None,
        "return_5y": float(fund.return_5y) if fund.return_5y else None,
        "return_10y": float(fund.return_10y) if fund.return_10y else None,
        "volatility": float(fund.volatility) if fund.volatility else None,
        "sharpe_ratio": float(fund.sharpe_ratio) if fund.sharpe_ratio else None,
        "beta": float(fund.beta) if fund.beta else None,
        "alpha": float(fund.alpha) if fund.alpha else None,
        "aum": float(fund.aum) if fund.aum else None,
        "expense_ratio": float(fund.expense_ratio) if fund.expense_ratio else None,
        "exit_load": fund.exit_load,
        "value_research_rating": fund.value_research_rating,
        "recommendation_score": float(fund.recommendation_score) if fund.recommendation_score else None,
        "recommendation_rank": fund.recommendation_rank,
        "recommendation_reason": fund.recommendation_reason,
        "last_updated": fund.last_updated.isoformat() if fund.last_updated else None,
    }


@router.patch("/fund/{scheme_code}")
async def update_fund_details(
    scheme_code: str,
    update_data: dict,
    db: Session = Depends(get_db)
):
    """Update fund details (AUM, expense ratio, beta, alpha, VR rating, exit load)."""
    fund = db.query(MutualFundResearch).filter(
        MutualFundResearch.scheme_code == scheme_code
    ).first()
    
    if not fund:
        raise HTTPException(status_code=404, detail="Fund not found")
    
    # Update allowed fields
    if "aum" in update_data:
        fund.aum = Decimal(str(update_data["aum"])) if update_data["aum"] is not None else None
    if "expense_ratio" in update_data:
        fund.expense_ratio = Decimal(str(update_data["expense_ratio"])) if update_data["expense_ratio"] is not None else None
    if "beta" in update_data:
        fund.beta = Decimal(str(update_data["beta"])) if update_data["beta"] is not None else None
    if "alpha" in update_data:
        fund.alpha = Decimal(str(update_data["alpha"])) if update_data["alpha"] is not None else None
    if "value_research_rating" in update_data:
        fund.value_research_rating = update_data["value_research_rating"] if update_data["value_research_rating"] is not None else None
    if "exit_load" in update_data:
        fund.exit_load = update_data["exit_load"] if update_data["exit_load"] else None
    
    fund.last_updated = datetime.utcnow()
    db.commit()
    db.refresh(fund)
    
    # Return updated fund data in same format as GET endpoint
    return {
        "id": fund.id,
        "scheme_code": fund.scheme_code,
        "scheme_name": fund.scheme_name,
        "fund_house": fund.fund_house,
        "scheme_type": fund.scheme_type,
        "scheme_category": fund.scheme_category,
        "fund_category": fund.fund_category,
        "current_nav": float(fund.current_nav) if fund.current_nav else None,
        "nav_date": fund.nav_date.isoformat() if fund.nav_date else None,
        "return_1y": float(fund.return_1y) if fund.return_1y else None,
        "return_3y": float(fund.return_3y) if fund.return_3y else None,
        "return_5y": float(fund.return_5y) if fund.return_5y else None,
        "return_10y": float(fund.return_10y) if fund.return_10y else None,
        "volatility": float(fund.volatility) if fund.volatility else None,
        "sharpe_ratio": float(fund.sharpe_ratio) if fund.sharpe_ratio else None,
        "beta": float(fund.beta) if fund.beta else None,
        "alpha": float(fund.alpha) if fund.alpha else None,
        "aum": float(fund.aum) if fund.aum else None,
        "expense_ratio": float(fund.expense_ratio) if fund.expense_ratio else None,
        "exit_load": fund.exit_load,
        "value_research_rating": fund.value_research_rating,
        "recommendation_score": float(fund.recommendation_score) if fund.recommendation_score else None,
        "recommendation_rank": fund.recommendation_rank,
        "recommendation_reason": fund.recommendation_reason,
        "last_updated": fund.last_updated.isoformat() if fund.last_updated else None,
    }


@router.post("/refresh/{scheme_code}")
async def refresh_fund_data(
    scheme_code: str,
    db: Session = Depends(get_db)
):
    """Refresh data for a specific fund from MFapi.in."""
    try:
        result = fetch_and_store_fund_data(db, scheme_code)
        if not result:
            raise HTTPException(status_code=404, detail="Fund not found")
        
        # Recalculate all scores
        calculate_all_scores_and_rank(db)
        
        return {
            "success": True,
            "fund": result,
            "message": "Fund data refreshed"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error refreshing fund: {str(e)}")


@router.get("/categories")
async def get_fund_categories(db: Session = Depends(get_db)):
    """Get list of all fund categories."""
    categories = db.query(MutualFundResearch.fund_category).filter(
        MutualFundResearch.is_active == 'Y',
        MutualFundResearch.fund_category.isnot(None)
    ).distinct().all()
    
    return {
        "categories": [cat[0] for cat in categories if cat[0]]
    }


@router.post("/refresh-all")
async def refresh_all_funds(db: Session = Depends(get_db)):
    """Refresh data for all funds in the research table."""
    try:
        funds = db.query(MutualFundResearch).filter(
            MutualFundResearch.is_active == 'Y'
        ).all()
        
        if not funds:
            return {
                "success": True,
                "message": "No funds to refresh",
                "refreshed": 0,
                "failed": 0
            }
        
        refreshed = 0
        failed = 0
        errors = []
        
        for fund in funds:
            try:
                result = fetch_and_store_fund_data(db, fund.scheme_code)
                if result:
                    refreshed += 1
                else:
                    failed += 1
                    errors.append(f"{fund.scheme_name}: Failed to fetch data")
            except Exception as e:
                failed += 1
                errors.append(f"{fund.scheme_name}: {str(e)}")
                logger.error(f"Error refreshing fund {fund.scheme_code}: {e}")
        
        # Recalculate all scores and ranks after refresh
        calculate_all_scores_and_rank(db)
        
        return {
            "success": True,
            "message": f"Refreshed {refreshed} funds, {failed} failed",
            "refreshed": refreshed,
            "failed": failed,
            "total": len(funds),
            "errors": errors[:10]  # Limit to first 10 errors
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error refreshing funds: {str(e)}")

