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

    # Default to V4 (conviction-based evaluator with intrinsic/time value model)
    return "v4"

ALGORITHM_VERSION = _load_algorithm_version()
logger.info(f"Algorithm version: {ALGORITHM_VERSION}")

# =============================================================================
# RLHF LEARNING CONFIGURATION
# Controls which data is used for RLHF learning
# =============================================================================
from datetime import date

RLHF_CONFIG = {
    # Current algorithm version for tagging matches
    # Update this when algorithm changes significantly
    "algorithm_version": "v4",

    # Only data after this date is considered for learning
    # Update this when starting a new "learning epoch" (major algorithm change)
    "min_valid_date": date(2026, 1, 20),  # V4 epoch start
    
    # Maximum age in days for data to be included in pattern detection
    # Even within valid epoch, older data is weighted less
    "pattern_detection_max_days": 30,
    
    # Minimum feedback needed before generating V4 candidates
    # Quality over quantity - don't need feedback on everything
    "min_modifications_for_pattern": 3,
    "min_rejections_for_pattern": 3,
}

def get_rlhf_config():
    """Get RLHF configuration."""
    return RLHF_CONFIG

def start_new_rlhf_epoch(version: str, min_date: date):
    """
    Start a new RLHF learning epoch.
    
    Call this when algorithm version changes significantly.
    This updates the config - old data won't be used for learning.
    """
    global RLHF_CONFIG
    RLHF_CONFIG["algorithm_version"] = version
    RLHF_CONFIG["min_valid_date"] = min_date
    logger.info(f"Started new RLHF epoch: {version} from {min_date}")

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
# V4 CONFIGURATION (Intrinsic Value Model - January 2026)
# Documentation: docs/OPTIONS-NOTIFICATION-ALGORITHM-V4.md
# =============================================================================
V4_CONFIG: Dict[str, Any] = {
    "version": "v4",
    "description": "Conviction-based options income: believe in holdings, mean reversion, tactical timing",

    # ===== FOUNDATIONAL PHILOSOPHY =====
    # These beliefs drive ALL decisions in V4
    "philosophy": {
        # 1. Every stock owned is believed in - otherwise why own it?
        "believe_in_holdings": True,

        # 2. Holdings are forever - not trading in/out
        "hold_forever": True,

        # 3. Stocks are cyclical - down will go up, up will go down
        "mean_reversion": True,

        # 4. Primary goal: earn weekly options income on holdings
        "primary_goal": "weekly_options_income",

        # 5. Avoid unnecessary risk via tactical timing
        "tactical_timing": True,

        # 6. Avoid forced assignment - give time cushion for recovery
        "avoid_forced_assignment": True,
    },

    # ===== TIME CUSHION RULE =====
    # When expiry is near (1-2 days), roll out by a week to give cushion
    # Cushion allows: if up → time to go down, if down → time to go up
    "time_cushion": {
        "enabled": True,
        "min_days_to_expiry": 2,          # If ≤2 days left, consider rolling
        "roll_out_weeks": 1,               # Roll by 1 week for cushion
        "reason": "avoid_forced_assignment",
    },

    # ===== CORE THRESHOLDS (inherited from V3) =====
    "profit_threshold": 0.60,      # Roll weekly when 60%+ profit captured
    "max_debit_pct": 0.20,         # Maximum acceptable debit = 20% of original premium

    # ===== V4 NEW: EARLY PROFIT CAPTURE =====
    # When 70%+ of premium is captured, recommend closing early
    # Philosophy: Don't let a winner become a loser. Lock in profits.
    "early_close_threshold": 0.70,  # Close when 70%+ profit captured

    # ===== V4 KEY CHANGE: ESCAPE DURATION =====
    # V3 allowed 12 months (52 weeks) - V4 caps at 4 weeks
    # Philosophy: Better to pay debit for 4-week escape than get "free" 12-week trap
    "max_escape_weeks": 4,         # CHANGED from max_roll_months: 12
    "prefer_debit_over_extension": True,  # Pay debit to stay within 4 weeks
    "extension_debit_limit": 5.00,        # Max debit to avoid going beyond 4 weeks

    # ===== V4 NEW: INTRINSIC/TIME VALUE MODEL =====
    # Categorizes positions by intrinsic % of option price
    # Lower intrinsic % = more time value = time decay helps
    # Higher intrinsic % = more intrinsic = need stock movement
    "intrinsic_value": {
        "time_helps_threshold": 0.40,        # Below 40% intrinsic: time decay helps
        "crossover_low": 0.40,               # Crossover zone start
        "crossover_high": 0.60,              # Crossover zone end
        "stock_must_move_threshold": 0.60,   # Above 60%: need stock movement

        # Category definitions for position assessment
        "categories": {
            "safe": {"max": 0.25, "strategy": "normal_management"},
            "low_bad": {"min": 0.25, "max": 0.40, "strategy": "can_wait"},
            "medium": {"min": 0.40, "max": 0.55, "strategy": "decision_point"},
            "med_high": {"min": 0.55, "max": 0.70, "strategy": "need_stock_movement"},
            "high_bad": {"min": 0.70, "max": 0.85, "strategy": "stock_must_move_significantly"},
            "catastrophic": {"min": 0.85, "strategy": "cut_loss_or_accept_assignment"},
        },
    },

    # ===== V4 NEW: COMPRESSION COST MODEL (DUAL-BENEFIT) =====
    # Compression has TWO benefits, not just one:
    #   Benefit 1: Weekly income - get back to earning weekly premium
    #   Benefit 2: Cycle capture - ability to exit cleanly on stock drops
    #
    # Without compression, far-dated options are "trapped":
    #   - Can't capitalize on stock drops (option still has time value)
    #   - Stock may recover by expiry, putting you ITM again
    #
    # Decision: Compress when Total Value > Compression Cost
    "compression": {
        "enabled": True,

        # --- BENEFIT 1: Weekly Income ---
        # Value = Weeks to Expiry × Weekly Premium (from option_premium_settings)
        "weekly_income_source": "option_premium_settings",  # Database table
        "default_weekly_income": 50.0,  # Fallback weekly income PER CONTRACT if not configured per symbol

        # --- BENEFIT 2: Cycle Capture ---
        # Value = Probability of Favorable Cycle × Exit Cost Savings
        # Exit Cost Savings = Far-dated exit cost - Weekly exit cost
        "cycle_capture": {
            "enabled": True,
            "favorable_cycle_probability": 0.60,  # 60% chance of favorable drop
            # Exit cost savings estimated as: far-dated time value - weekly time value
        },

        # --- DECISION THRESHOLDS ---
        # Compare Total Value (Benefit 1 + Benefit 2) to Compression Cost
        "compress_when_value_exceeds_cost": True,
        "consider_threshold": 0.90,  # Consider when value > 90% of cost

        # --- LEGACY: Simple weeks-based thresholds (fallback) ---
        "compress_threshold_weeks": 2,
        "consider_threshold_weeks": 4,
        "too_expensive_threshold_weeks": 4,
    },

    # ===== V4 NEW: PROGRESSIVE PULLBACK =====
    # For over-extended positions (>4 weeks out), use each mean reversion
    # as a stepping stone rather than trying to fix in one move
    "progressive_pullback": {
        "enabled": True,
        "min_weeks_to_trigger": 4,           # Only for positions >4 weeks out

        # Stock drop triggers (percentage)
        "trigger_evaluate": 0.05,            # 5% drop: evaluate options
        "trigger_act": 0.10,                 # 10% drop: act on compression
        "trigger_full_escape": 0.00,         # Below strike: full escape to weekly

        # Cost limits at each trigger
        "max_cost_at_evaluate": 10.00,       # Max $10 at 5% drop
        "max_cost_at_act": 8.00,             # Max $8 at 10% drop
    },

    # ===== V4 NEW: TACTICAL TIMING =====
    # Optimize entry/exit timing based on stock direction
    # General rule: Sell options when stock is UP, buy back when stock is DOWN
    # KEY INSIGHT: Don't ROLL - separate the legs to optimize each one
    #   - Rolling = Buy + Sell at same time (one leg is always suboptimal)
    #   - Instead: Buy back when DOWN (good), Sell when UP (good)
    "tactical_timing": {
        "enabled": True,

        # --- SEPARATE BUY AND SELL (Don't Roll) ---
        # Rolling combines buy+sell, but you can't optimize both simultaneously
        # Stock DOWN: Buy back NOW (cheap), Sell LATER (when up)
        # Stock UP: Sell NOW (rich), Buy back LATER (when down)
        "separate_buy_sell": True,
        "avoid_rolling_when_suboptimal": True,

        # --- EARLY CLOSE FOR FLEXIBILITY ---
        # When option is nearly worthless, close early to enable tactical re-entry
        "early_close": {
            "enabled": True,
            "min_profit_pct": 0.80,              # >80% profit captured
            "min_otm_pct": 0.10,                 # >10% OTM (safe)
            "reason": "gain_reentry_flexibility", # Close early to sell at better time
        },

        # --- CALL RE-ENTRY (after closing a profitable call) ---
        "call_reentry": {
            "min_drop_to_wait": 0.03,             # 3% down day triggers wait (don't sell into weakness)
            "recovery_threshold": 0.02,           # 2% up from close to re-enter
            "same_week_cutoff_day": "Wednesday",  # Last day to sell for same-week expiry
            "use_ta_signals": True,               # Use RSI, support levels for timing
        },

        # --- PUT RE-ENTRY (after closing a profitable put) ---
        # Inverse of calls: sell puts when stock is DOWN, buy back when UP
        "put_reentry": {
            "min_rise_to_wait": 0.03,             # 3% up day triggers wait (don't sell into strength)
            "pullback_threshold": 0.02,           # 2% down from close to re-enter
        },
    },

    # ===== V4 NEW: PUT SELLING =====
    # Opportunistic put selling when stocks drop significantly
    # Part of the "wheel" strategy: sell puts → if assigned → sell calls
    "put_selling": {
        "enabled": True,

        # --- TRIGGER CONDITIONS (OR logic - either triggers consideration) ---
        "triggers": {
            # Condition A: Volatility-based drop (variable by stock)
            "drop_threshold": {
                "method": "atr_multiple",         # Use Average True Range
                "atr_period": 14,                 # 14-day ATR (standard)
                "multiplier": 2.0,                # Trigger at 2x normal daily move
            },
            # Condition B: Technical signals
            "technical": {
                "rsi_oversold": 30,               # RSI below 30
                "support_breach": True,           # Hits key support level
            },
            "logic": "OR",                        # Either condition triggers
        },

        # --- WHICH STOCKS QUALIFY ---
        "qualified_stocks": "current_holdings",   # Only stocks already in portfolio

        # --- STRIKE SELECTION ---
        "delta_target": 0.20,                     # Delta 20 for puts

        # --- EXPIRATION ---
        "expiration": "weekly",                   # Friday to Friday, same as calls

        # --- CAPITAL ---
        "capital_source": "fixed_cash_balances",  # Use fixed cash balances (below)

        # --- ASSIGNMENT ASSESSMENT ---
        # Key insight: Assignment is GOOD if it improves your cost basis
        "assignment_assessment": {
            "compare_to_cost_basis": True,        # Always check vs existing holdings
            "acceptable_premium_over_basis": 0.02, # 2% above cost basis still acceptable

            # Decision matrix:
            # strike < cost_basis         → Assignment IMPROVES avg cost → HOLD acceptable
            # strike ≈ cost_basis (±2%)   → Assignment NEUTRAL          → HOLD acceptable
            # strike > cost_basis + 2%    → Assignment WORSENS avg cost → Consider CLOSE
        },

        # --- POST-ASSIGNMENT ---
        "post_assignment": "sell_covered_calls",  # Wheel continues automatically
    },

    # ===== V4 NEW: FIXED CASH BALANCES =====
    # Since cash data is hard to extract from brokerage statements,
    # we use fixed cash balances per account for put selling calculations.
    # Available cash = fixed_balance - sum(put_strike × 100 × contracts)
    "fixed_cash_balances": {
        "Neel's Retirement": 150_000,     # $150k available for puts
        "Neel's Brokerage": 120_000,      # $120k available for puts
        "Jaya's Roth IRA": 150_000,       # $150k available for puts
        # Add other accounts as needed
    },

    # Minimum cash to keep available (not deploy everything)
    "min_cash_reserve": 10_000,           # Keep at least $10k undeployed

    # Minimum available cash to recommend a new put
    "min_cash_for_new_put": 5_000,        # Need at least $5k free to recommend

    # ===== STRIKE SELECTION (inherited from V3) =====
    "strike_selection": {
        "weekly_delta_target": 0.90,      # Delta 10 for weekly income rolls (90% OTM)
        "itm_escape_delta_target": 0.70,  # Delta 30 for ITM escapes (70% OTM)
        "pullback_delta_target": 0.70,    # Delta 30 for pull-backs (70% OTM)
    },

    # ===== ITM ESCAPE DEBIT LIMITS (from V3.3) =====
    "itm_escape_debit_limits": {
        "slight_itm_max": 2.00,    # 0-3% ITM
        "moderate_itm_max": 3.00,  # 3-7% ITM
        "deep_itm_max": 5.00,      # 7%+ ITM
    },

    # ===== PULL-BACK (inherited from V3) =====
    "min_weeks_for_pullback": 1,   # Check pull-back for positions >1 week out

    # ===== RISK MANAGEMENT (inherited from V3) =====
    "earnings_lookback_days": 5,   # Alert if earnings within 5 trading days
    "dividend_lookback_days": 7,   # Alert if ex-dividend within 7 days
    "excessive_earnings_threshold": 10,  # Warn if 10+ earnings per quarter

    # ===== LIQUIDITY (inherited from V3) =====
    "liquidity": {
        "enable_liquidity_check": True,
        "min_open_interest": 50,
        "max_spread_pct": 0.10,    # 10% max spread
    },

    # ===== SCAN SCHEDULE (inherited from V3) =====
    "scan_times": {
        "main": "06:00",           # Comprehensive daily scan
        "post_open": "08:00",      # Urgent state changes
        "midday": "12:00",         # Pull-backs and opportunities
        "pre_close": "12:45",      # Last chance actions
        "evening": "20:00",        # Next day planning
    },

    # ===== URGENCY THRESHOLDS (inherited from V3) =====
    "urgent_deepening_threshold": 10,  # Alert at 8 AM if position >10% deeper ITM

    # ===== SPECIAL DATES (inherited from V3) =====
    "triple_witching_months": [3, 6, 9, 12],  # March, June, September, December

    # ===== FEATURES =====
    "timing": {
        "enable_timing_optimization": False,
    },

    # Keep these for backwards compatibility with shared code
    "early_roll": {
        "profit_threshold": 0.60,
        "earnings_week_profit_threshold": 0.60,
        "short_dte_threshold": 0.60,
    },

    "roll_options": {
        "enable_end_of_week_roll": False,
        "max_roll_weeks": 4,  # V4: capped at 4 weeks (was 52 in V3)
    },

    "itm_roll": {
        "itm_threshold_percent": 0.0,  # No minimum - any ITM triggers escape
    },

    "preemptive_roll": {
        "enabled": False,
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
        "enable_execution_guidance": True,
    },

    "min_weekly_income": 50,

    # ===== SMART ASSIGNMENT (inherited from V3) =====
    "smart_assignment": {
        "enabled": True,
        "accounts": ["IRA", "ROTH_IRA", "ROTH IRA"],
        "max_itm_pct": 2.0,
        "min_itm_pct": 0.1,
        "min_roll_weeks": 2,
        "min_roll_debit": 15,
        "monday_skip_threshold": 3.0,
        "monday_wait_threshold": 1.0,
    },
}

# =============================================================================
# V5 CONFIGURATION (V4 + LIFE_SUPPORT - February 2026)
# Documentation: docs/OPTIONS-NOTIFICATION-ALGORITHM-V5.md
# =============================================================================
V5_CONFIG: Dict[str, Any] = {
    "version": "v5",
    "description": "V4 + LIFE_SUPPORT category for stuck positions",

    # ===== INHERIT ALL V4 SETTINGS =====
    **V4_CONFIG,

    # Override version identifier
    "version": "v5",
    "description": "V4 + LIFE_SUPPORT category for stuck positions",

    # ===== V5 NEW: LIFE_SUPPORT CONFIGURATION =====
    # When weekly rolls yield $0 or debit, but bi-weekly/monthly still credit,
    # extend roll duration to keep position "on life support" until mean reversion
    "life_support": {
        "enabled": True,

        # Thresholds by IV category (ITM% where each category starts)
        # life_support_starts: Weekly = $0, but bi-weekly/monthly still credit
        # drowning_starts: Even monthly = $0, position is unsalvageable
        "thresholds": {
            "high_iv": {"life_support_starts": 30, "drowning_starts": 35},
            "medium_iv": {"life_support_starts": 17, "drowning_starts": 22},
            "low_iv": {"life_support_starts": 10, "drowning_starts": 15},
        },

        # Roll periods to try (in order of preference)
        # If weekly fails, try biweekly; if biweekly fails, try monthly
        "roll_periods": ["biweekly", "monthly"],

        # Known high-IV symbols (40%+ annual IV)
        "high_iv_symbols": ["HOOD", "TSLA", "MARA", "RIOT", "COIN", "GME", "AMC", "RIVN", "LCID"],

        # Known low-IV symbols (<20% annual IV)
        "low_iv_symbols": ["AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "BRK.B", "JNJ", "PG", "KO"],
    },
}

# =============================================================================
# VERSION REGISTRY
# =============================================================================
VERSIONS: Dict[str, Dict[str, Any]] = {
    "v1": V1_CONFIG,
    "v2": V2_CONFIG,
    "v3": V3_CONFIG,
    "v4": V4_CONFIG,
    "v5": V5_CONFIG,  # V5: V4 + LIFE_SUPPORT
    # V6 (added 2026-07-22, emails pointed here) doesn't read this config —
    # v6_engine.py is fully self-contained. This entry exists only so legacy
    # v3-era modules that call get_config() at import time (earnings_alert.py,
    # early_roll_opportunity.py, etc.) don't crash the whole app on startup.
    "v6": V5_CONFIG,
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


def get_fixed_cash_balance(account_name: str, version: str = None) -> float:
    """
    Get the fixed cash balance for an account.

    Args:
        account_name: Account name (e.g., "Neel's Retirement")
        version: Version to use (defaults to ALGORITHM_VERSION)

    Returns:
        Fixed cash balance for the account, or 0 if not configured.
    """
    config = get_config(version)
    fixed_balances = config.get("fixed_cash_balances", {})
    return float(fixed_balances.get(account_name, 0))


def get_available_cash_for_puts(account_name: str, existing_puts: list = None, version: str = None) -> float:
    """
    Calculate available cash for new put positions.

    Formula: available = fixed_balance - reserved_for_existing_puts - min_reserve

    Args:
        account_name: Account name (e.g., "Neel's Retirement")
        existing_puts: List of existing put positions with strike_price and contracts_sold
        version: Version to use (defaults to ALGORITHM_VERSION)

    Returns:
        Available cash for new puts (can be negative if over-allocated).
    """
    config = get_config(version)

    # Get fixed cash balance
    fixed_balance = get_fixed_cash_balance(account_name, version)
    if fixed_balance <= 0:
        return 0.0

    # Calculate cash reserved for existing puts
    reserved = 0.0
    if existing_puts:
        for put in existing_puts:
            strike = float(getattr(put, 'strike_price', 0) or 0)
            contracts = int(getattr(put, 'contracts_sold', 1) or 1)
            reserved += strike * 100 * contracts

    # Subtract minimum reserve
    min_reserve = config.get("min_cash_reserve", 10_000)

    available = fixed_balance - reserved - min_reserve

    logger.debug(f"[Cash] {account_name}: fixed=${fixed_balance:,.0f}, reserved=${reserved:,.0f}, "
                 f"min_reserve=${min_reserve:,.0f}, available=${available:,.0f}")

    return available


def should_recommend_new_put(account_name: str, existing_puts: list = None,
                             target_strike: float = None, version: str = None) -> tuple:
    """
    Check if we should recommend a new cash-secured put for an account.

    Args:
        account_name: Account name
        existing_puts: List of existing put positions
        target_strike: Strike price of the proposed new put (optional)
        version: Algorithm version

    Returns:
        Tuple of (should_recommend: bool, available_cash: float, reason: str)
    """
    config = get_config(version)

    available = get_available_cash_for_puts(account_name, existing_puts, version)
    min_for_new = config.get("min_cash_for_new_put", 5_000)

    if available < min_for_new:
        return (False, available, f"Insufficient cash: ${available:,.0f} available, need ${min_for_new:,.0f}")

    # If target strike specified, check if we can afford it
    if target_strike:
        required = target_strike * 100  # 1 contract
        if available < required:
            return (False, available, f"Cannot afford ${target_strike} put (need ${required:,.0f}, have ${available:,.0f})")

    return (True, available, f"${available:,.0f} available for new puts")


# =============================================================================
# LOGGING
# =============================================================================
# Log version on module load
logger.info(f"Algorithm config loaded: version={ALGORITHM_VERSION}")

