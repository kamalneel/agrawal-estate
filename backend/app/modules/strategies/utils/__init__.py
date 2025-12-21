"""
Option Strategy Utilities

This module provides shared utility functions used across all option strategies.
Centralizing these calculations eliminates code duplication and ensures consistency.

V2.2 Refactoring - December 2024
"""

from .option_calculations import (
    calculate_itm_status,
    check_itm_thresholds,
    check_roll_economics,
    would_be_itm,
    get_threshold_config,
)

__all__ = [
    'calculate_itm_status',
    'check_itm_thresholds', 
    'check_roll_economics',
    'would_be_itm',
    'get_threshold_config',
]

