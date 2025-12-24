"""
Option Strategy Utilities

This module provides shared utility functions used across all option strategies.
Centralizing these calculations eliminates code duplication and ensures consistency.

V3.0 Refactoring - December 2024
- Simplified to core functions only
- Added is_acceptable_cost for V3 20% rule
- Legacy V2 functions kept for backward compatibility
"""

from .option_calculations import (
    # V3 Core functions
    calculate_itm_status,
    is_acceptable_cost,
    get_position_status,
    # V2 Legacy functions (kept for backward compatibility)
    check_itm_thresholds,
    check_roll_economics,
    validate_roll_options,
    would_be_itm,
)

__all__ = [
    # V3 Core
    'calculate_itm_status',
    'is_acceptable_cost',
    'get_position_status',
    # V2 Legacy
    'check_itm_thresholds', 
    'check_roll_economics',
    'validate_roll_options',
    'would_be_itm',
]

