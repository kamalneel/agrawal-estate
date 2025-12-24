"""
Option Calculations Utility Module

V3.0 SIMPLIFIED - Single source of truth for option calculations:
- ITM/OTM status
- Intrinsic value
- ITM percentage
- Simple cost validation (20% rule only)

V3 CHANGES:
- REMOVED: ITM threshold checking (5%, 10%, 20% thresholds)
- REMOVED: Economic sanity checks (min $50 savings, 10% savings)
- REMOVED: Roll option validation
- SIMPLIFIED: Only ONE cost rule: max debit = 20% of original premium

This module eliminates code duplication across:
- roll_options.py
- itm_roll_optimizer.py
- triple_witching_handler.py
"""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# V3 CONFIGURATION - Simplified to one cost rule
# =============================================================================

# V3: Single cost rule - max debit is 20% of original premium
MAX_DEBIT_PCT = 0.20  # 20% of original premium


# =============================================================================
# ITM STATUS CALCULATION
# =============================================================================

def calculate_itm_status(
    current_price: float,
    strike: float,
    option_type: str
) -> Dict[str, Any]:
    """
    Calculate ITM status, percentage, and intrinsic value for an option.
    
    This is the SINGLE SOURCE OF TRUTH for ITM calculations.
    All other modules should use this function instead of inline calculations.
    
    Args:
        current_price: Current stock price
        strike: Option strike price
        option_type: 'call' or 'put'
        
    Returns:
        dict with:
            - is_itm (bool): Whether position is in the money
            - itm_pct (float): ITM percentage (0 if OTM)
            - itm_amount (float): Dollar amount ITM (0 if OTM)
            - intrinsic_value (float): Same as itm_amount (for clarity)
            - otm_pct (float): OTM percentage (0 if ITM)
            - distance_pct (float): Absolute distance from strike as percentage
            
    Examples:
        >>> calculate_itm_status(102.0, 100.0, 'call')
        {'is_itm': True, 'itm_pct': 2.0, 'itm_amount': 2.0, ...}
        
        >>> calculate_itm_status(39.0, 60.0, 'put')  # FIG case
        {'is_itm': True, 'itm_pct': 35.0, 'itm_amount': 21.0, ...}
    """
    option_type_lower = option_type.lower()
    
    if option_type_lower == "call":
        # CALL: ITM when stock > strike
        is_itm = current_price > strike
        if is_itm:
            itm_amount = current_price - strike
            itm_pct = (itm_amount / strike) * 100
            otm_pct = 0.0
        else:
            itm_amount = 0.0
            itm_pct = 0.0
            otm_pct = ((strike - current_price) / current_price) * 100 if current_price > 0 else 0.0
            
    elif option_type_lower == "put":
        # PUT: ITM when stock < strike
        is_itm = current_price < strike
        if is_itm:
            itm_amount = strike - current_price
            itm_pct = (itm_amount / strike) * 100
            otm_pct = 0.0
        else:
            itm_amount = 0.0
            itm_pct = 0.0
            otm_pct = ((current_price - strike) / current_price) * 100 if current_price > 0 else 0.0
    else:
        raise ValueError(f"Invalid option_type: {option_type}. Must be 'call' or 'put'.")
    
    # Distance from strike (absolute)
    distance_pct = abs(current_price - strike) / strike * 100 if strike > 0 else 0.0
    
    return {
        'is_itm': is_itm,
        'itm_pct': round(itm_pct, 2),
        'itm_amount': round(itm_amount, 2),
        'intrinsic_value': round(itm_amount, 2),  # Alias for clarity
        'otm_pct': round(otm_pct, 2),
        'distance_pct': round(distance_pct, 2),
        'current_price': current_price,
        'strike': strike,
        'option_type': option_type_lower,
    }


# =============================================================================
# V3: SIMPLE COST VALIDATION (20% RULE)
# =============================================================================

def is_acceptable_cost(
    net_cost: float,
    original_premium: float
) -> Dict[str, Any]:
    """
    V3 SIMPLIFIED: Check if roll cost is acceptable.
    
    ONE SIMPLE RULE: Debit must be ≤ 20% of original premium.
    Any credit is automatically acceptable.
    
    Args:
        net_cost: Net cost of roll (positive = debit, negative = credit)
        original_premium: Original premium received when selling the option
        
    Returns:
        dict with:
            - acceptable (bool): Whether cost is acceptable
            - reason (str): Explanation
            - max_debit (float): Maximum acceptable debit
    """
    max_debit = original_premium * MAX_DEBIT_PCT
    
    # Any credit is automatically acceptable
    if net_cost <= 0:
        return {
            'acceptable': True,
            'reason': f'Credit of ${abs(net_cost):.2f} - always acceptable',
            'max_debit': round(max_debit, 2),
            'net_cost': round(net_cost, 2),
            'is_credit': True
        }
    
    # Check if debit is within 20% threshold
    if net_cost <= max_debit:
        return {
            'acceptable': True,
            'reason': f'Debit ${net_cost:.2f} ≤ max ${max_debit:.2f} (20% of ${original_premium:.2f})',
            'max_debit': round(max_debit, 2),
            'net_cost': round(net_cost, 2),
            'is_credit': False
        }
    
    # Debit exceeds 20% threshold
    return {
        'acceptable': False,
        'reason': f'Debit ${net_cost:.2f} > max ${max_debit:.2f} (20% of ${original_premium:.2f})',
        'max_debit': round(max_debit, 2),
        'net_cost': round(net_cost, 2),
        'is_credit': False,
        'search_longer': True  # Hint to try longer expirations
    }


# =============================================================================
# LEGACY COMPATIBILITY - These functions are DEPRECATED in V3
# =============================================================================

def check_itm_thresholds(
    current_price: float = None,
    strike: float = None,
    option_type: str = None,
    is_triple_witching: bool = False,
    **kwargs
) -> Dict[str, Any]:
    """
    V3 DEPRECATED: No longer checks ITM thresholds.
    
    V3 Strategy: Never close based on ITM percentage.
    Instead, find zero-cost roll up to 52 weeks.
    Only close if cannot escape within 52 weeks.
    
    Returns: Always says "can roll" for V3 compatibility.
    """
    # Calculate ITM status for info purposes only
    itm_pct = 0.0
    intrinsic_value = 0.0
    if current_price and strike and option_type:
        status = calculate_itm_status(current_price, strike, option_type)
        itm_pct = status['itm_pct']
        intrinsic_value = status['intrinsic_value']
    
    # V3: Never close based on ITM% - always try to find zero-cost roll
    return {
        'should_close': False,
        'recommendation': None,
        'reason': f'V3: {itm_pct:.1f}% ITM - find zero-cost roll (up to 52 weeks)',
        'urgency': None,
        'itm_pct': itm_pct,
        'intrinsic_value': intrinsic_value,
        'is_triple_witching': is_triple_witching,
        'can_roll': True,
        'v3_note': 'V3 removed ITM thresholds - always try to find zero-cost roll'
    }


def check_roll_economics(
    close_cost: float = 0,
    roll_options: list = None,
    current_price: float = None,
    option_type: str = None,
    **kwargs
) -> Dict[str, Any]:
    """
    V3 DEPRECATED: Economic sanity checks removed.
    
    V3 Strategy: Only use 20% cost rule via is_acceptable_cost().
    No minimum savings requirements.
    Rolling into slightly ITM is acceptable if it's the best zero-cost option.
    
    Returns: Always says "economically sound" for V3 compatibility.
    """
    return {
        'economically_sound': True,
        'reason': 'V3: Use is_acceptable_cost() for 20% rule',
        'v3_note': 'V3 removed economic sanity checks - use is_acceptable_cost() instead'
    }


def validate_roll_options(roll_options: list = None, **kwargs) -> Dict[str, Any]:
    """
    V3 DEPRECATED: Roll option validation removed.
    
    V3 uses simpler zero-cost finder logic.
    
    Returns: Always valid for V3 compatibility.
    """
    return {
        'valid': True,
        'v3_note': 'V3 removed roll option validation'
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def would_be_itm(
    current_price: float,
    new_strike: float,
    option_type: str
) -> bool:
    """
    Check if a new position at new_strike would be ITM.
    
    Note: V3 allows rolling into slightly ITM if it's the best zero-cost option.
    This function is for informational purposes.
    
    Args:
        current_price: Current stock price
        new_strike: Proposed new strike price
        option_type: 'call' or 'put'
        
    Returns:
        True if new position would be ITM, False if OTM
    """
    option_type_lower = option_type.lower()
    
    if option_type_lower == "call":
        return current_price > new_strike
    elif option_type_lower == "put":
        return current_price < new_strike
    else:
        raise ValueError(f"Invalid option_type: {option_type}")


def get_position_status(
    current_price: float,
    strike: float,
    option_type: str,
    is_triple_witching: bool = False
) -> Dict[str, Any]:
    """
    V3 SIMPLIFIED: Get position status without threshold checking.
    
    Returns ITM status for informational purposes.
    V3 does NOT use thresholds to determine close vs roll.
    """
    itm_status = calculate_itm_status(current_price, strike, option_type)
    
    # V3: No threshold checking - always try to find zero-cost roll
    return {
        **itm_status,
        'should_close': False,  # V3: Never auto-close based on ITM%
        'can_roll': itm_status['is_itm'],  # Only need to roll if ITM
        'v3_strategy': 'Find zero-cost roll up to 52 weeks'
    }

