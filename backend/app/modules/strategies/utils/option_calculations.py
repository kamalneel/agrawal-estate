"""
Option Calculations Utility Module

SINGLE SOURCE OF TRUTH for all option-related calculations:
- ITM/OTM status
- Intrinsic value
- ITM percentage
- Threshold checking
- Economic viability

This module eliminates code duplication across:
- roll_options.py
- itm_roll_optimizer.py
- triple_witching_handler.py
- earnings_alert.py
- technical_analysis.py

V2.2 Refactoring - December 2024
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION - Single source of truth for thresholds
# =============================================================================

@dataclass(frozen=True)
class ITMThresholds:
    """ITM thresholds for determining CLOSE vs ROLL decisions."""
    catastrophic_pct: float = 20.0    # >20% ITM = disaster, never roll
    deep_pct: float = 10.0            # >10% ITM = too deep to roll
    normal_close_pct: float = 5.0     # >5% ITM = close on normal days
    triple_witching_pct: float = 3.0  # >3% ITM = close on Triple Witching


@dataclass(frozen=True)
class EconomicThresholds:
    """Economic thresholds for roll viability."""
    min_savings_dollars: float = 50.0   # Must save $50+ per contract to justify roll
    min_savings_percent: float = 10.0   # Or 10%+ savings
    min_strike_variation_pct: float = 2.0  # Roll options must differ by 2%+


# Default thresholds (can be overridden by config)
_ITM_THRESHOLDS = ITMThresholds()
_ECONOMIC_THRESHOLDS = EconomicThresholds()


def get_threshold_config() -> Dict[str, Any]:
    """
    Get current threshold configuration.
    
    Returns dict with all threshold values for inspection/logging.
    """
    return {
        'itm': {
            'catastrophic_pct': _ITM_THRESHOLDS.catastrophic_pct,
            'deep_pct': _ITM_THRESHOLDS.deep_pct,
            'normal_close_pct': _ITM_THRESHOLDS.normal_close_pct,
            'triple_witching_pct': _ITM_THRESHOLDS.triple_witching_pct,
        },
        'economic': {
            'min_savings_dollars': _ECONOMIC_THRESHOLDS.min_savings_dollars,
            'min_savings_percent': _ECONOMIC_THRESHOLDS.min_savings_percent,
            'min_strike_variation_pct': _ECONOMIC_THRESHOLDS.min_strike_variation_pct,
        }
    }


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
# ITM THRESHOLD CHECKING
# =============================================================================

def check_itm_thresholds(
    itm_pct: float,
    is_triple_witching: bool = False
) -> Dict[str, Any]:
    """
    Check if ITM percentage exceeds thresholds for CLOSE vs ROLL decision.
    
    Thresholds (from most severe to least):
    - CATASTROPHIC (>20%): Close immediately, position has failed
    - DEEP (>10%): Too deep to roll effectively
    - NORMAL (>5%): Close on normal days
    - TRIPLE WITCHING (>3%): Close on Triple Witching days (stricter)
    
    Args:
        itm_pct: ITM percentage (from calculate_itm_status)
        is_triple_witching: Whether today is Triple Witching day
        
    Returns:
        dict with:
            - should_close (bool): Whether to close instead of roll
            - recommendation (str): 'CLOSE_IMMEDIATELY', 'CLOSE_DONT_ROLL', or None
            - reason (str): Human-readable explanation
            - urgency (str): 'CRITICAL', 'urgent', 'high', or None
            - threshold_used (float): Which threshold was triggered
            - explanation (list): Detailed explanation lines
    """
    thresholds = _ITM_THRESHOLDS
    
    # Check from most severe to least
    
    if itm_pct >= thresholds.catastrophic_pct:
        return {
            'should_close': True,
            'recommendation': 'CLOSE_IMMEDIATELY',
            'reason': f'CATASTROPHIC: {itm_pct:.1f}% ITM (threshold: {thresholds.catastrophic_pct}%)',
            'urgency': 'CRITICAL',
            'threshold_used': thresholds.catastrophic_pct,
            'is_triple_witching': is_triple_witching,
            'explanation': [
                f'Position is {itm_pct:.1f}% ITM - this is a disaster',
                'Rolling will not fix this - only delay the inevitable loss',
                'Close immediately and redeploy capital to recover faster',
                'This position has fundamentally failed'
            ]
        }
    
    if itm_pct >= thresholds.deep_pct:
        return {
            'should_close': True,
            'recommendation': 'CLOSE_DONT_ROLL',
            'reason': f'DEEP ITM: {itm_pct:.1f}% ITM (threshold: {thresholds.deep_pct}%)',
            'urgency': 'urgent',
            'threshold_used': thresholds.deep_pct,
            'is_triple_witching': is_triple_witching,
            'explanation': [
                f'Position is {itm_pct:.1f}% ITM - beyond effective rolling range',
                'Rolls at this depth have poor economics',
                'Better to close and redeploy capital'
            ]
        }
    
    if is_triple_witching and itm_pct >= thresholds.triple_witching_pct:
        return {
            'should_close': True,
            'recommendation': 'CLOSE_DONT_ROLL',
            'reason': f'TRIPLE WITCHING: {itm_pct:.1f}% ITM (threshold: {thresholds.triple_witching_pct}%)',
            'urgency': 'high',
            'threshold_used': thresholds.triple_witching_pct,
            'is_triple_witching': True,
            'triple_witching_note': 'Stricter threshold on Triple Witching Day due to execution quality',
            'explanation': [
                f'Position is {itm_pct:.1f}% ITM on Triple Witching Day',
                f'Triple Witching threshold is {thresholds.triple_witching_pct}% (vs normal {thresholds.normal_close_pct}%)',
                'Poor execution quality today makes rolling unwise',
                'Close in 10:30 AM - 2:30 PM ET window'
            ]
        }
    
    if itm_pct >= thresholds.normal_close_pct:
        return {
            'should_close': True,
            'recommendation': 'CLOSE_DONT_ROLL',
            'reason': f'EXCEEDS THRESHOLD: {itm_pct:.1f}% ITM (threshold: {thresholds.normal_close_pct}%)',
            'urgency': 'high',
            'threshold_used': thresholds.normal_close_pct,
            'is_triple_witching': is_triple_witching,
            'explanation': [
                f'Position is {itm_pct:.1f}% ITM - exceeds {thresholds.normal_close_pct}% rolling threshold',
                'Beyond this threshold, rolling economics are poor',
                'Recommended: Close and redeploy capital'
            ]
        }
    
    # Below all thresholds - rolling may be acceptable
    return {
        'should_close': False,
        'recommendation': None,
        'reason': f'{itm_pct:.1f}% ITM - within rolling range',
        'urgency': None,
        'threshold_used': None,
        'is_triple_witching': is_triple_witching,
        'can_roll': True
    }


# =============================================================================
# ECONOMIC VIABILITY CHECKING
# =============================================================================

def check_roll_economics(
    close_cost: float,
    roll_cost: float,
    contracts: int = 1,
    new_strike: Optional[float] = None,
    current_price: Optional[float] = None,
    option_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Check if rolling is economically viable vs closing.
    
    Economic checks:
    1. Roll cost must be less than close cost
    2. Savings must be meaningful ($50+ per contract OR 10%+)
    3. If new_strike provided, checks that new position won't be ITM
    
    Args:
        close_cost: Cost to close position now (per share)
        roll_cost: Net cost to roll (buy_back - new_premium, per share)
        contracts: Number of contracts
        new_strike: Optional - new strike price to validate
        current_price: Optional - current stock price (needed with new_strike)
        option_type: Optional - 'call' or 'put' (needed with new_strike)
        
    Returns:
        dict with:
            - economically_sound (bool): Whether roll is viable
            - reason (str): Why or why not
            - savings_per_share (float): How much saved per share
            - savings_per_contract (float): How much saved per contract
            - savings_pct (float): Percentage savings
            - recommendation (str): 'ROLL' or 'CLOSE'
    """
    thresholds = _ECONOMIC_THRESHOLDS
    
    # Check 1: Roll cost must be less than close cost
    if roll_cost >= close_cost:
        return {
            'economically_sound': False,
            'reason': f'Roll cost ${roll_cost:.2f} ≥ close cost ${close_cost:.2f}',
            'recommendation': 'CLOSE',
            'savings_per_share': 0,
            'savings_per_contract': 0,
            'savings_pct': 0,
            'analysis': {
                'close_cost': round(close_cost, 2),
                'roll_cost': round(roll_cost, 2),
                'difference': round(roll_cost - close_cost, 2),
                'conclusion': 'Rolling costs same or more than closing - no economic benefit'
            }
        }
    
    # Calculate savings
    savings_per_share = close_cost - roll_cost
    savings_per_contract = savings_per_share * 100  # 100 shares per contract
    savings_pct = (savings_per_share / close_cost * 100) if close_cost > 0 else 0
    
    # Check 2: Savings must be meaningful
    min_dollars = thresholds.min_savings_dollars
    min_pct = thresholds.min_savings_percent
    
    if savings_per_contract < min_dollars and savings_pct < min_pct:
        return {
            'economically_sound': False,
            'reason': f'Minimal savings: ${savings_per_contract:.0f}/contract ({savings_pct:.1f}%)',
            'recommendation': 'CLOSE',
            'savings_per_share': round(savings_per_share, 2),
            'savings_per_contract': round(savings_per_contract, 0),
            'savings_pct': round(savings_pct, 1),
            'analysis': {
                'close_cost': round(close_cost, 2),
                'roll_cost': round(roll_cost, 2),
                'savings': round(savings_per_share, 2),
                'min_required_dollars': min_dollars,
                'min_required_pct': min_pct,
                'conclusion': f'Saving ${savings_per_contract:.0f} is not worth the complexity and ongoing risk'
            }
        }
    
    # Check 3: If new_strike provided, check if new position would be ITM
    if new_strike is not None and current_price is not None and option_type is not None:
        if would_be_itm(current_price, new_strike, option_type):
            new_status = calculate_itm_status(current_price, new_strike, option_type)
            return {
                'economically_sound': False,
                'reason': f'New position would be {new_status["itm_pct"]:.1f}% ITM (strike ${new_strike} vs stock ${current_price:.0f})',
                'recommendation': 'CLOSE',
                'savings_per_share': round(savings_per_share, 2),
                'savings_per_contract': round(savings_per_contract, 0),
                'savings_pct': round(savings_pct, 1),
                'analysis': {
                    'new_strike': new_strike,
                    'current_price': round(current_price, 2),
                    'new_itm_pct': round(new_status['itm_pct'], 1),
                    'conclusion': 'Rolling into another ITM position - problem not solved'
                }
            }
    
    # All checks passed
    return {
        'economically_sound': True,
        'reason': f'Roll saves ${savings_per_contract:.0f}/contract ({savings_pct:.1f}%)',
        'recommendation': 'ROLL',
        'savings_per_share': round(savings_per_share, 2),
        'savings_per_contract': round(savings_per_contract, 0),
        'savings_pct': round(savings_pct, 1),
        'analysis': {
            'close_cost': round(close_cost, 2),
            'roll_cost': round(roll_cost, 2),
            'savings': round(savings_per_share, 2),
            'conclusion': f'Roll economics acceptable - saves ${savings_per_contract:.0f}/contract'
        }
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
    
    Used to prevent rolling INTO another ITM position.
    
    Args:
        current_price: Current stock price
        new_strike: Proposed new strike price
        option_type: 'call' or 'put'
        
    Returns:
        True if new position would be ITM, False if OTM
        
    Examples:
        >>> would_be_itm(39.0, 42.0, 'put')  # $42 strike with $39 stock
        True  # ITM because stock < strike for put
        
        >>> would_be_itm(39.0, 35.0, 'put')  # $35 strike with $39 stock  
        False  # OTM because stock > strike for put
    """
    option_type_lower = option_type.lower()
    
    if option_type_lower == "call":
        # CALL is ITM when stock > strike
        return current_price > new_strike
    elif option_type_lower == "put":
        # PUT is ITM when stock < strike
        return current_price < new_strike
    else:
        raise ValueError(f"Invalid option_type: {option_type}")


def validate_roll_options(roll_options: List[Dict]) -> Dict[str, Any]:
    """
    Validate that roll optimizer returned valid, distinct options.
    
    Checks:
    1. Must have at least 3 options
    2. Strikes must not all be identical
    3. Strike range must be >= MIN_STRIKE_VARIATION_PCT
    
    Args:
        roll_options: List of roll option dicts with 'strike' field
        
    Returns:
        dict with 'valid' (bool) and 'error' (str if invalid)
    """
    if not roll_options:
        return {
            'valid': False,
            'error': 'No roll options provided'
        }
    
    if len(roll_options) < 3:
        return {
            'valid': False,
            'error': f'Expected 3 options (Conservative/Moderate/Aggressive), got {len(roll_options)}'
        }
    
    # Extract strikes
    strikes = [opt.get('strike') for opt in roll_options if opt.get('strike') is not None]
    
    if len(strikes) < 3:
        return {
            'valid': False,
            'error': f'Only {len(strikes)} options have valid strikes'
        }
    
    # Check if all strikes are identical
    unique_strikes = set(strikes)
    if len(unique_strikes) == 1:
        return {
            'valid': False,
            'error': f'All options have identical strike ${strikes[0]:.0f} - optimizer failed',
            'strikes': strikes
        }
    
    # Check strike range
    min_strike = min(strikes)
    max_strike = max(strikes)
    strike_range_pct = ((max_strike - min_strike) / min_strike * 100) if min_strike > 0 else 0
    
    min_variation = _ECONOMIC_THRESHOLDS.min_strike_variation_pct
    
    if strike_range_pct < min_variation:
        return {
            'valid': False,
            'error': f'Strike range only {strike_range_pct:.1f}% - options too similar (need {min_variation}%+)',
            'strikes': strikes,
            'range_pct': round(strike_range_pct, 1)
        }
    
    return {
        'valid': True,
        'strikes': strikes,
        'strike_range': max_strike - min_strike,
        'range_pct': round(strike_range_pct, 1)
    }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_position_status(
    current_price: float,
    strike: float,
    option_type: str,
    is_triple_witching: bool = False
) -> Dict[str, Any]:
    """
    Get complete status and recommendation for a position.
    
    Combines ITM calculation with threshold checking for a complete picture.
    
    Args:
        current_price: Current stock price
        strike: Option strike price
        option_type: 'call' or 'put'
        is_triple_witching: Whether today is Triple Witching
        
    Returns:
        Combined dict with ITM status and threshold decision
    """
    itm_status = calculate_itm_status(current_price, strike, option_type)
    
    if itm_status['is_itm']:
        threshold = check_itm_thresholds(itm_status['itm_pct'], is_triple_witching)
    else:
        threshold = {
            'should_close': False,
            'recommendation': None,
            'reason': 'Position is OTM',
            'can_roll': False  # OTM positions don't need roll analysis
        }
    
    return {
        **itm_status,
        **threshold
    }

