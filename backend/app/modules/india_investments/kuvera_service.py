"""
Kuvera API Service - Fetches fund metrics from mf.captnemo.in/kuvera
Provides: AUM, Expense Ratio, Fund Rating, Volatility, etc.
"""

import requests
import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

KUVERA_API_BASE = "https://mf.captnemo.in/kuvera"


def get_fund_by_isin(isin: str) -> Optional[Dict[str, Any]]:
    """
    Fetch fund data from Kuvera API using ISIN.
    
    Args:
        isin: ISIN code (e.g., "INF879O01027")
    
    Returns:
        Dict with fund data or None if not found
    """
    if not isin:
        return None
        
    try:
        response = requests.get(f"{KUVERA_API_BASE}/{isin}", timeout=15)
        response.raise_for_status()
        
        data = response.json()
        
        if isinstance(data, list) and len(data) > 0:
            fund = data[0]
            
            # Parse fund start date
            start_date = None
            if fund.get('start_date'):
                try:
                    start_date = datetime.strptime(fund['start_date'], "%Y-%m-%d").date()
                except ValueError:
                    pass
            
            # Convert AUM from lakhs to crores (divide by 100)
            aum_crores = None
            if fund.get('aum'):
                aum_crores = float(fund['aum']) / 100  # API returns in lakhs
            
            return {
                'name': fund.get('name'),
                'short_name': fund.get('short_name'),
                'isin': fund.get('ISIN'),
                'fund_house': fund.get('fund_name'),
                'fund_category': fund.get('fund_category'),
                'aum': aum_crores,
                'expense_ratio': float(fund['expense_ratio']) if fund.get('expense_ratio') else None,
                'expense_ratio_date': fund.get('expense_ratio_date'),
                'fund_rating': fund.get('fund_rating'),
                'fund_rating_date': fund.get('fund_rating_date'),
                'volatility': float(fund['volatility']) if fund.get('volatility') else None,
                'crisil_rating': fund.get('crisil_rating'),
                'start_date': start_date,
                'nav': float(fund['nav']['nav']) if fund.get('nav') else None,
                'nav_date': fund['nav'].get('date') if fund.get('nav') else None,
                'returns': fund.get('returns', {}),
            }
        
        return None
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching Kuvera data for ISIN {isin}: {e}")
        return None
    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"Error parsing Kuvera response for ISIN {isin}: {e}")
        return None


def get_isin_from_mfapi(scheme_code: str) -> Optional[str]:
    """
    Fetch ISIN from MFapi.in using scheme code.
    
    Args:
        scheme_code: AMFI scheme code (e.g., "122639")
    
    Returns:
        ISIN code or None
    """
    if not scheme_code:
        return None
        
    try:
        response = requests.get(f"https://api.mfapi.in/mf/{scheme_code}/latest", timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('status') == 'SUCCESS':
            meta = data.get('meta', {})
            return meta.get('isin_growth') or meta.get('isin_div_reinvestment')
        
        return None
        
    except Exception as e:
        logger.error(f"Error fetching ISIN for scheme {scheme_code}: {e}")
        return None


def enrich_fund_data(scheme_code: str = None, isin: str = None) -> Optional[Dict[str, Any]]:
    """
    Get complete fund data by ISIN (preferred) or scheme code.
    
    If ISIN is provided, fetches directly from Kuvera (fast path).
    If only scheme_code is provided, first fetches ISIN from MFapi.in.
    
    Args:
        scheme_code: AMFI scheme code (fallback for ISIN lookup)
        isin: ISIN code (preferred - uses Kuvera directly)
    
    Returns:
        Dict with enriched fund data including returns, AUM, expense ratio, etc.
    """
    # Fast path: Use ISIN directly if available
    if isin:
        kuvera_data = get_fund_by_isin(isin)
        if kuvera_data:
            kuvera_data['scheme_code'] = scheme_code
            kuvera_data['isin'] = isin
            return kuvera_data
    
    # Slow path: Get ISIN from scheme code first
    if scheme_code:
        isin = get_isin_from_mfapi(scheme_code)
        if isin:
            kuvera_data = get_fund_by_isin(isin)
            if kuvera_data:
                kuvera_data['scheme_code'] = scheme_code
                kuvera_data['isin'] = isin
                return kuvera_data
    
    logger.warning(f"Could not get fund data for scheme {scheme_code}, ISIN {isin}")
    return None

