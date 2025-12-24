"""
Options Notification Algorithm Configuration

This module defines algorithm versions (V1, V2, etc.) with all configurable parameters.
Switch versions via ALGORITHM_VERSION environment variable or .env file.

Usage:
    from app.modules.strategies.algorithm_config import get_config, ALGORITHM_VERSION
    
    config = get_config()
    profit_threshold = config['early_roll']['profit_threshold']
"""

import os
from pathlib import Path
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# VERSION SELECTION
# =============================================================================
# Load .env file if it exists (for ALGORITHM_VERSION)
def _load_algorithm_version() -> str:
    """Load ALGORITHM_VERSION from environment or .env file."""
    # First check environment variable
    version = os.getenv("ALGORITHM_VERSION")
    if version:
        return version.lower()
    
    # Try to load from .env file
    try:
        env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
        if env_path.exists():
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('ALGORITHM_VERSION='):
                        version = line.split('=', 1)[1].strip().strip('"').strip("'")
                        logger.info(f"Loaded ALGORITHM_VERSION={version} from .env file")
                        return version.lower()
    except Exception as e:
        logger.warning(f"Error reading .env file: {e}")
    
    # Default to v2
    return "v2"

ALGORITHM_VERSION = _load_algorithm_version()
logger.info(f"Algorithm version: {ALGORITHM_VERSION}")

# =============================================================================
# V1 CONFIGURATION (Original - December 2024)
# Documentation: docs/OPTIONS-NOTIFICATION-ALGORITHM-V1.md
# =============================================================================
V1_CONFIG: Dict[str, Any] = {
    "version": "v1",
    "description": "Original algorithm with conservative thresholds",
    
    # Early Roll Strategy
    "early_roll": {
        "profit_threshold": 0.80,              # 80% profit to roll
        "earnings_week_profit_threshold": 0.60, # 60% during earnings week
        "short_dte_threshold": None,           # Not implemented in V1
    },
    
    # Roll Options Strategy
    "roll_options": {
        "enable_end_of_week_roll": True,       # V1 has auto end-of-week rolls
        "max_debit_pct_of_new_premium": 0.50,
        "max_roll_weeks": 1,                   # V1 only considers 1 week
    },
    
    # ITM Roll Optimizer
    "itm_roll": {
        "itm_threshold_percent": 1.0,
        "cost_weight": 0.35,
        "prob_weight": 0.35,
        "time_weight": 0.20,
        "return_weight": 0.10,
    },
    
    # Strike Selection
    "strike_selection": {
        "probability_target": 0.90,            # Delta 10
    },
    
    # Timing (Not in V1)
    "timing": {
        "enable_timing_optimization": False,
        "friday_cutoff_time": None,
        "low_vix_threshold": None,
    },
    
    # Liquidity (Not in V1)
    "liquidity": {
        "enable_liquidity_check": False,
        "skip_if_poor_liquidity": False,
        "suggest_alternatives": False,
    },
    
    # Execution Guidance (Not in V1)
    "execution": {
        "enable_execution_guidance": False,
    },
    
    # Preemptive Roll (Not in V1)
    "preemptive_roll": {
        "enabled": False,
    },
    
    # Dividend Alerts (Not in V1)
    "dividend": {
        "enabled": False,
    },
    
    # Triple Witching (Not in V1)
    "triple_witching": {
        "enabled": False,
        "alert_days_before": 0,
    },
    
    # Earnings
    "earnings": {
        "days_before_alert": 5,
    },
    
    # General
    "min_weekly_income": 50,
}

# =============================================================================
# V2 CONFIGURATION (Enhanced - December 2024)
# Documentation: docs/OPTIONS-NOTIFICATION-ALGORITHM-V2.md
# =============================================================================
V2_CONFIG: Dict[str, Any] = {
    "version": "v2",
    "description": "Enhanced algorithm with lower thresholds, preemptive rolls, liquidity checks",
    
    # Early Roll Strategy - UPDATED
    "early_roll": {
        "profit_threshold": 0.60,              # CHANGED from 0.80
        "earnings_week_profit_threshold": 0.45, # CHANGED from 0.60
        "short_dte_threshold": 0.35,           # NEW: <3 days to expiration
    },
    
    # Roll Options Strategy - UPDATED
    "roll_options": {
        "enable_end_of_week_roll": False,      # REMOVED in V2
        "max_debit_pct_of_new_premium": 0.50,
        "max_debit_pct_earnings": 0.75,        # NEW: more lenient before earnings
        "max_debit_pct_high_profit": 0.15,     # NEW: when 80%+ captured
        "max_debit_pct_expiring_soon": 1.0,    # NEW: last 1-2 days
        "max_roll_weeks": 3,                   # NEW: multi-week analysis
        "min_marginal_premium": 0.15,          # NEW: must add $0.15+/week
        "scenario_comparison_tolerance": 0.90, # NEW: roll if within 90% of best
    },
    
    # ITM Roll Optimizer - ENHANCED in V2.1
    "itm_roll": {
        "itm_threshold_percent": 1.0,         # Minimum ITM% to trigger ITM flow
        "cost_weight": 0.35,
        "prob_weight": 0.35,
        "time_weight": 0.20,
        "return_weight": 0.10,
        "max_weeks_preemptive": 3,             # NEW
        "max_weeks_deep_itm": 6,               # NEW
        # V2.1: ITM Close Thresholds (when to CLOSE instead of ROLL)
        "catastrophic_itm_pct": 20.0,          # >20% ITM = disaster, never roll
        "deep_itm_pct": 10.0,                  # >10% ITM = too deep to roll
        "normal_close_threshold_pct": 5.0,    # >5% ITM = close on normal days
        "triple_witching_close_threshold_pct": 3.0,  # >3% ITM = close on Triple Witching
        # V2.1: Economic sanity thresholds
        "min_roll_savings_dollars": 50,        # Must save $50+ to justify roll
        "min_roll_savings_percent": 10,        # Must save 10%+ to justify roll
        "min_strike_variation_pct": 2.0,       # Conservative/Moderate/Aggressive must differ by 2%+
    },
    
    # Strike Selection - UNCHANGED
    "strike_selection": {
        "probability_target": 0.90,            # Delta 10
        "conservative_target": 0.90,
        "aggressive_target": 0.80,             # NEW: optional for max income
    },
    
    # Strategic Timing - NEW in V2
    "timing": {
        "enable_timing_optimization": True,
        "friday_cutoff_time": "14:00",         # After 2pm suggest Monday
        "min_premium_pct_of_stock": 0.003,     # 0.3% threshold
        "low_vix_threshold": 15,
        "avoid_morning_chaos": True,
        "morning_volatility_start": "09:30",
        "morning_volatility_end": "10:30",
    },
    
    # Liquidity Checks - NEW in V2
    "liquidity": {
        "enable_liquidity_check": True,
        "min_open_interest": 100,
        "min_daily_volume": 20,
        "max_spread_pct_excellent": 0.03,
        "max_spread_pct_good": 0.05,
        "max_spread_pct_fair": 0.10,
        "skip_if_poor_liquidity": True,
        "suggest_alternatives": True,
        "max_strike_adjustment_pct": 0.02,
    },
    
    # Execution Guidance - NEW in V2
    "execution": {
        "enable_execution_guidance": True,
        "tight_spread_threshold": 0.05,
        "wide_spread_threshold": 0.10,
        "quick_move_seconds": 60,
        "normal_wait_seconds": 120,
        "patient_wait_seconds": 180,
        "walk_increment_pct": 0.25,
        "afternoon_rush_start": "15:30",
    },
    
    # Preemptive Roll - NEW in V2
    "preemptive_roll": {
        "enabled": True,
        "approaching_threshold_pct": 3.0,      # Alert within 3% of strike
        "urgent_threshold_pct": 1.5,           # Urgent within 1.5%
        "min_days_to_expiration": 2,
        "momentum_lookback_days": 3,
        "min_volume_multiple": 1.2,
    },
    
    # Dividend Alerts - NEW in V2
    "dividend": {
        "enabled": True,
        "days_before_exdiv_alert": 7,
        "high_assignment_risk_threshold": 0.80,
        "min_dividend_pct_for_risk": 0.002,    # 0.2% of stock price
    },
    
    # Triple Witching - NEW in V2
    "triple_witching": {
        "enabled": True,
        "alert_days_before": 1,           # Alert 1 day before
        "shallow_itm_threshold": 3.0,     # vs 5.0 on normal days
        "deep_itm_threshold": 10.0,       # vs 15.0 on normal days
        "near_money_threshold": 2.0,      # Close positions within 2%
        "safe_otm_threshold": 5.0,        # Let expire if >5% OTM
        "high_vix_threshold": 25,         # VIX level for aggressive selling
        "expected_spread_multiple": 2.5,  # Spreads are 2.5x normal
        "min_slippage_per_contract": 50,
        "max_slippage_per_contract": 150,
    },
    
    # Earnings - UNCHANGED
    "earnings": {
        "days_before_alert": 5,
    },
    
    # General
    "min_weekly_income": 50,
}

# =============================================================================
# V3 CONFIGURATION (Simplified Strategy-Aligned - December 2024)
# Documentation: docs/OPTIONS-NOTIFICATION-ALGORITHM-V3.md
# =============================================================================
V3_CONFIG: Dict[str, Any] = {
    "version": "v3",
    "description": "Simplified algorithm: 3 states, 12 params, strategy-aligned",
    
    # ===== CORE THRESHOLDS =====
    "profit_threshold": 0.60,      # Roll weekly when 60%+ profit captured
    "max_debit_pct": 0.20,         # Maximum acceptable debit = 20% of original premium
    "max_roll_months": 12,         # Never roll beyond 12 months (52 weeks)
    
    # ===== STRIKE SELECTION =====
    "strike_selection": {
        "weekly_delta_target": 0.90,      # Delta 10 for weekly income rolls (90% OTM)
        "itm_escape_delta_target": 0.70,  # Delta 30 for ITM escapes (70% OTM)
        "pullback_delta_target": 0.70,    # Delta 30 for pull-backs (70% OTM)
    },
    
    # ===== PULL-BACK =====
    "min_weeks_for_pullback": 1,   # Check pull-back for positions >1 week out
    
    # ===== RISK MANAGEMENT =====
    "earnings_lookback_days": 5,   # Alert if earnings within 5 trading days
    "dividend_lookback_days": 7,   # Alert if ex-dividend within 7 days
    "excessive_earnings_threshold": 10,  # Warn if 10+ earnings per quarter
    
    # ===== LIQUIDITY =====
    "liquidity": {
        "enable_liquidity_check": True,
        "min_open_interest": 50,
        "max_spread_pct": 0.10,    # 10% max spread
    },
    
    # ===== SCAN SCHEDULE (Pacific Time) =====
    "scan_times": {
        "main": "06:00",           # Comprehensive daily scan
        "post_open": "08:00",      # Urgent state changes
        "midday": "12:00",         # Pull-backs and opportunities
        "pre_close": "12:45",      # Last chance actions
        "evening": "20:00",        # Next day planning
    },
    
    # ===== URGENCY THRESHOLDS =====
    "urgent_deepening_threshold": 10,  # Alert at 8 AM if position >10% deeper ITM
    
    # ===== SPECIAL DATES =====
    "triple_witching_months": [3, 6, 9, 12],  # March, June, September, December
    
    # ===== FEATURES (V3 removes many V2 features) =====
    "timing": {
        "enable_timing_optimization": False,  # REMOVED in V3
    },
    
    # Keep these for backwards compatibility with shared code
    "early_roll": {
        "profit_threshold": 0.60,
        "earnings_week_profit_threshold": 0.60,  # Same as normal in V3
        "short_dte_threshold": 0.60,             # Same as normal in V3
    },
    
    "roll_options": {
        "enable_end_of_week_roll": False,
        "max_roll_weeks": 52,  # Up to 12 months
    },
    
    "itm_roll": {
        "itm_threshold_percent": 0.0,  # No minimum - any ITM triggers escape
        # V3 REMOVES all threshold percentages
        # "catastrophic_itm_pct": REMOVED
        # "deep_itm_pct": REMOVED
        # "normal_close_threshold_pct": REMOVED
    },
    
    "preemptive_roll": {
        "enabled": False,  # REMOVED in V3 - merged into position evaluator
    },
    
    "dividend": {
        "enabled": True,
        "days_before_exdiv_alert": 7,
    },
    
    "triple_witching": {
        "enabled": True,
        "alert_days_before": 1,
    },
    
    "earnings": {
        "days_before_alert": 5,
    },
    
    "execution": {
        "enable_execution_guidance": True,  # Keep execution guidance
    },
    
    "min_weekly_income": 50,
    
    # ===== SMART ASSIGNMENT (V3 - IRA ONLY) =====
    "smart_assignment": {
        "enabled": True,
        "accounts": ["IRA", "ROTH_IRA", "ROTH IRA"],  # Only these account types
        "max_itm_pct": 2.0,          # Maximum 2% ITM to consider
        "min_itm_pct": 0.1,          # Minimum 0.1% ITM (truly borderline)
        "min_roll_weeks": 2,         # Only if roll would be 2+ weeks
        "min_roll_debit": 15,        # OR roll debit >$15/contract
        "monday_skip_threshold": 3.0, # Skip buyback if >3% above assignment
        "monday_wait_threshold": 1.0, # Suggest waiting if 1-3% above
    },
}

# =============================================================================
# VERSION REGISTRY
# =============================================================================
VERSIONS: Dict[str, Dict[str, Any]] = {
    "v1": V1_CONFIG,
    "v2": V2_CONFIG,
    "v3": V3_CONFIG,
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_config(version: str = None) -> Dict[str, Any]:
    """
    Get configuration for specified version.
    
    Args:
        version: "v1", "v2", etc. If None, uses ALGORITHM_VERSION env var.
        
    Returns:
        Configuration dictionary for the specified version.
        
    Raises:
        ValueError: If version is not found.
    """
    if version is None:
        version = ALGORITHM_VERSION
    
    version = version.lower()
    
    if version not in VERSIONS:
        available = ", ".join(VERSIONS.keys())
        raise ValueError(f"Unknown algorithm version '{version}'. Available: {available}")
    
    config = VERSIONS[version]
    logger.info(f"Using algorithm {version}: {config['description']}")
    return config


def get_param(section: str, key: str, default: Any = None, version: str = None) -> Any:
    """
    Get a specific parameter from config.
    
    Args:
        section: Config section (e.g., "early_roll", "liquidity")
        key: Parameter key within section
        default: Default value if not found
        version: Version to use (defaults to ALGORITHM_VERSION)
        
    Returns:
        Parameter value or default.
    """
    config = get_config(version)
    section_config = config.get(section, {})
    return section_config.get(key, default)


def is_feature_enabled(feature: str, version: str = None) -> bool:
    """
    Check if a V2 feature is enabled in current version.
    
    Args:
        feature: One of "preemptive_roll", "dividend", "liquidity", 
                 "execution", "timing", "performance"
        version: Version to check (defaults to ALGORITHM_VERSION)
                 
    Returns:
        True if feature is enabled.
    """
    config = get_config(version)
    
    feature_checks = {
        "preemptive_roll": ("preemptive_roll", "enabled"),
        "dividend": ("dividend", "enabled"),
        "liquidity": ("liquidity", "enable_liquidity_check"),
        "execution": ("execution", "enable_execution_guidance"),
        "timing": ("timing", "enable_timing_optimization"),
        "end_of_week_roll": ("roll_options", "enable_end_of_week_roll"),
        "triple_witching": ("triple_witching", "enabled"),
    }
    
    if feature not in feature_checks:
        return False
    
    section, key = feature_checks[feature]
    return config.get(section, {}).get(key, False)


def get_profit_threshold(is_earnings_week: bool = False, days_to_expiration: int = None, version: str = None) -> float:
    """
    Get the appropriate profit threshold based on context.
    
    Args:
        is_earnings_week: True if within 5 days of earnings
        days_to_expiration: Days until option expires
        version: Algorithm version to use
        
    Returns:
        Profit threshold (0.0 to 1.0)
    """
    config = get_config(version)
    early_roll_config = config.get("early_roll", {})
    
    # Short DTE takes precedence (V2 only)
    if days_to_expiration is not None and days_to_expiration <= 3:
        short_dte_threshold = early_roll_config.get("short_dte_threshold")
        if short_dte_threshold is not None:
            return short_dte_threshold
    
    # Earnings week
    if is_earnings_week:
        return early_roll_config.get("earnings_week_profit_threshold", 0.60)
    
    # Normal
    return early_roll_config.get("profit_threshold", 0.80)


# =============================================================================
# LOGGING
# =============================================================================
# Log version on module load
logger.info(f"Algorithm config loaded: version={ALGORITHM_VERSION}")

