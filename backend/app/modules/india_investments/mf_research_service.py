"""
Mutual Fund Research Service - Fetches data from MFapi.in and calculates metrics.
"""

import requests
import logging
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func

logger = logging.getLogger(__name__)

MFAPI_BASE_URL = "https://api.mfapi.in/mf"


def search_mutual_funds(query: str) -> List[Dict[str, Any]]:
    """
    Search for mutual funds by name.
    
    Returns list of {schemeCode, schemeName}
    """
    try:
        response = requests.get(f"{MFAPI_BASE_URL}/search", params={"q": query}, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error searching mutual funds: {e}")
        return []


def get_scheme_info(scheme_code: str) -> Optional[Dict[str, Any]]:
    """
    Get scheme information and latest NAV from MFapi.in.
    
    Returns:
        {
            "meta": {
                "fund_house": "...",
                "scheme_type": "...",
                "scheme_category": "...",
                "scheme_code": "...",
                "scheme_name": "...",
                "isin_growth": "...",
            },
            "data": [
                {"date": "26-10-2024", "nav": "892.45600"},
                ...
            ]
        }
    """
    try:
        response = requests.get(f"{MFAPI_BASE_URL}/{scheme_code}/latest", timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") == "SUCCESS":
            return data
        return None
    except Exception as e:
        logger.error(f"Error fetching scheme info for {scheme_code}: {e}")
        return None


def get_scheme_nav_history(scheme_code: str, days: int = 3650) -> List[Dict[str, Any]]:
    """
    Get historical NAV data for a scheme.
    
    Args:
        scheme_code: AMFI scheme code
        days: Number of days of history to fetch (default 10 years)
    
    Returns:
        List of {"date": "DD-MM-YYYY", "nav": "123.45"}
    """
    try:
        response = requests.get(f"{MFAPI_BASE_URL}/{scheme_code}", timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") == "SUCCESS":
            nav_data = data.get("data", [])
            
            # Parse dates and sort
            parsed_data = []
            for item in nav_data:
                try:
                    nav_date = datetime.strptime(item["date"], "%d-%m-%Y").date()
                    nav_value = Decimal(item["nav"])
                    parsed_data.append({
                        "date": nav_date,
                        "nav": nav_value
                    })
                except (ValueError, KeyError) as e:
                    logger.warning(f"Error parsing NAV entry: {e}")
                    continue
            
            # Sort by date (newest first)
            parsed_data.sort(key=lambda x: x["date"], reverse=True)
            
            # Limit to requested days
            cutoff_date = date.today() - timedelta(days=days)
            filtered_data = [item for item in parsed_data if item["date"] >= cutoff_date]
            
            return filtered_data
        return []
    except Exception as e:
        logger.error(f"Error fetching NAV history for {scheme_code}: {e}")
        return []


def calculate_returns(nav_history: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """
    Calculate historical returns from NAV history.
    
    Returns:
        {
            "return_1y": 12.5,
            "return_3y": 15.2,
            "return_5y": 18.3,
            "return_10y": 20.1,
        }
    """
    if not nav_history or len(nav_history) < 2:
        return {
            "return_1y": None,
            "return_3y": None,
            "return_5y": None,
            "return_10y": None,
        }
    
    # Sort by date (oldest first for calculation)
    sorted_history = sorted(nav_history, key=lambda x: x["date"])
    latest_nav = float(sorted_history[-1]["nav"])
    today = date.today()
    
    returns = {}
    
    # Calculate returns for different periods
    periods = {
        "return_1y": 365,
        "return_3y": 365 * 3,
        "return_5y": 365 * 5,
        "return_10y": 365 * 10,
    }
    
    for return_key, days in periods.items():
        target_date = today - timedelta(days=days)
        
        # Find NAV closest to target date
        closest_nav = None
        min_diff = float('inf')
        
        for item in sorted_history:
            diff = abs((item["date"] - target_date).days)
            if diff < min_diff and item["date"] <= target_date:
                min_diff = diff
                closest_nav = item
        
        if closest_nav:
            past_nav = float(closest_nav["nav"])
            years = (today - closest_nav["date"]).days / 365.0
            if years > 0 and past_nav > 0:
                # CAGR formula: ((Current/Previous)^(1/years) - 1) * 100
                cagr = ((latest_nav / past_nav) ** (1 / years) - 1) * 100
                returns[return_key] = round(cagr, 2)
            else:
                returns[return_key] = None
        else:
            returns[return_key] = None
    
    return returns


def calculate_volatility(nav_history: List[Dict[str, Any]], days: int = 365) -> Optional[float]:
    """
    Calculate volatility (standard deviation of returns) for the last N days.
    """
    if not nav_history or len(nav_history) < 2:
        return None
    
    # Get last N days of data
    cutoff_date = date.today() - timedelta(days=days)
    recent_data = [item for item in nav_history if item["date"] >= cutoff_date]
    recent_data.sort(key=lambda x: x["date"])
    
    if len(recent_data) < 2:
        return None
    
    # Calculate daily returns
    daily_returns = []
    for i in range(1, len(recent_data)):
        prev_nav = float(recent_data[i-1]["nav"])
        curr_nav = float(recent_data[i]["nav"])
        if prev_nav > 0:
            daily_return = (curr_nav - prev_nav) / prev_nav
            daily_returns.append(daily_return)
    
    if len(daily_returns) < 2:
        return None
    
    # Calculate standard deviation
    try:
        import statistics
        volatility = statistics.stdev(daily_returns) * (252 ** 0.5) * 100  # Annualized volatility
        return round(volatility, 2)
    except:
        return None


def calculate_sharpe_ratio(return_1y: Optional[float], volatility: Optional[float], risk_free_rate: float = 6.0) -> Optional[float]:
    """
    Calculate Sharpe ratio: (Return - Risk Free Rate) / Volatility
    
    Args:
        return_1y: 1-year return %
        volatility: Annualized volatility %
        risk_free_rate: Risk-free rate (default 6% for India)
    """
    if return_1y is None or volatility is None or volatility == 0:
        return None
    
    sharpe = (return_1y - risk_free_rate) / volatility
    return round(sharpe, 2)


def fetch_and_store_fund_data(db: Session, scheme_code: str) -> Optional[Dict[str, Any]]:
    """
    Fetch fund data from MFapi.in and store/update in database.
    
    Returns the created/updated MutualFundResearch object as dict.
    """
    from app.modules.india_investments.mf_research_models import MutualFundResearch, MutualFundNAVHistory
    
    # Fetch scheme info
    scheme_info = get_scheme_info(scheme_code)
    if not scheme_info:
        return None
    
    meta = scheme_info.get("meta", {})
    nav_data = scheme_info.get("data", [])
    
    # Get latest NAV
    latest_nav_entry = nav_data[0] if nav_data else None
    current_nav = None
    nav_date = None
    
    if latest_nav_entry:
        try:
            current_nav = Decimal(latest_nav_entry["nav"])
            nav_date = datetime.strptime(latest_nav_entry["date"], "%d-%m-%Y").date()
        except (ValueError, KeyError):
            pass
    
    # Fetch full NAV history for calculations
    nav_history = get_scheme_nav_history(scheme_code, days=3650)
    
    # Calculate returns
    returns = calculate_returns(nav_history)
    
    # Calculate volatility
    volatility = calculate_volatility(nav_history, days=365)
    
    # Calculate Sharpe ratio
    sharpe_ratio = calculate_sharpe_ratio(returns.get("return_1y"), volatility)
    
    # Extract fund category from scheme_category
    scheme_category = meta.get("scheme_category", "")
    fund_category = None
    if "Large Cap" in scheme_category:
        fund_category = "Large Cap"
    elif "Mid Cap" in scheme_category:
        fund_category = "Mid Cap"
    elif "Small Cap" in scheme_category:
        fund_category = "Small Cap"
    elif "Flexi Cap" in scheme_category:
        fund_category = "Flexi Cap"
    elif "Multi Cap" in scheme_category:
        fund_category = "Multi Cap"
    elif "International" in scheme_category or "Global" in scheme_category:
        fund_category = "International"
    elif "ELSS" in scheme_category:
        fund_category = "ELSS"
    else:
        # Try to extract from category string
        parts = scheme_category.split("-")
        if len(parts) > 1:
            fund_category = parts[-1].strip()
    
    # Get or create research record
    research = db.query(MutualFundResearch).filter(
        MutualFundResearch.scheme_code == scheme_code
    ).first()
    
    if not research:
        research = MutualFundResearch(
            scheme_code=scheme_code,
            scheme_name=meta.get("scheme_name", ""),
            fund_house=meta.get("fund_house", ""),
            scheme_type=meta.get("scheme_type"),
            scheme_category=scheme_category,
            fund_category=fund_category,
            isin_growth=meta.get("isin_growth"),
            isin_div_reinvestment=meta.get("isin_div_reinvestment"),
        )
        db.add(research)
    
    # Update fields
    research.scheme_name = meta.get("scheme_name", research.scheme_name)
    research.fund_house = meta.get("fund_house", research.fund_house)
    research.scheme_type = meta.get("scheme_type", research.scheme_type)
    research.scheme_category = scheme_category
    research.fund_category = fund_category
    research.current_nav = current_nav
    research.nav_date = nav_date
    research.return_1y = Decimal(str(returns["return_1y"])) if returns["return_1y"] else None
    research.return_3y = Decimal(str(returns["return_3y"])) if returns["return_3y"] else None
    research.return_5y = Decimal(str(returns["return_5y"])) if returns["return_5y"] else None
    research.return_10y = Decimal(str(returns["return_10y"])) if returns["return_10y"] else None
    research.volatility = Decimal(str(volatility)) if volatility else None
    research.sharpe_ratio = Decimal(str(sharpe_ratio)) if sharpe_ratio else None
    research.last_updated = datetime.utcnow()
    
    db.flush()
    
    # Store NAV history
    for nav_item in nav_history[:3650]:  # Limit to 10 years
        existing = db.query(MutualFundNAVHistory).filter(
            MutualFundNAVHistory.scheme_code == scheme_code,
            MutualFundNAVHistory.nav_date == nav_item["date"]
        ).first()
        
        if not existing:
            nav_history_record = MutualFundNAVHistory(
                scheme_code=scheme_code,
                nav_date=nav_item["date"],
                nav=nav_item["nav"],
            )
            db.add(nav_history_record)
    
    db.commit()
    
    return {
        "id": research.id,
        "scheme_code": research.scheme_code,
        "scheme_name": research.scheme_name,
        "fund_house": research.fund_house,
        "fund_category": research.fund_category,
        "current_nav": float(research.current_nav) if research.current_nav else None,
        "return_1y": float(research.return_1y) if research.return_1y else None,
        "return_3y": float(research.return_3y) if research.return_3y else None,
        "return_5y": float(research.return_5y) if research.return_5y else None,
        "return_10y": float(research.return_10y) if research.return_10y else None,
        "volatility": float(research.volatility) if research.volatility else None,
        "sharpe_ratio": float(research.sharpe_ratio) if research.sharpe_ratio else None,
    }

