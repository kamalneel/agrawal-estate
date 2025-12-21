"""
Test Suite for Option Calculations Utility Module

This test suite serves two purposes:
1. Unit tests for the new utility functions
2. Regression tests to ensure refactoring doesn't change behavior

Run with: pytest tests/test_option_calculations.py -v
"""

import pytest
from datetime import date, timedelta


# =============================================================================
# TEST FIXTURES - Known scenarios with expected outcomes
# =============================================================================

ITM_CALCULATION_SCENARIOS = [
    # (current_price, strike, option_type, expected_is_itm, expected_itm_pct, expected_intrinsic)
    
    # CALL options
    ("Call OTM far", 95.0, 100.0, "call", False, 0.0, 0.0),
    ("Call OTM slight", 99.0, 100.0, "call", False, 0.0, 0.0),
    ("Call ATM", 100.0, 100.0, "call", False, 0.0, 0.0),
    ("Call ITM shallow", 102.0, 100.0, "call", True, 2.0, 2.0),
    ("Call ITM normal", 105.0, 100.0, "call", True, 5.0, 5.0),
    ("Call ITM deep", 110.0, 100.0, "call", True, 10.0, 10.0),
    ("Call ITM catastrophic", 125.0, 100.0, "call", True, 25.0, 25.0),
    
    # PUT options
    ("Put OTM far", 105.0, 100.0, "put", False, 0.0, 0.0),
    ("Put OTM slight", 101.0, 100.0, "put", False, 0.0, 0.0),
    ("Put ATM", 100.0, 100.0, "put", False, 0.0, 0.0),
    ("Put ITM shallow", 98.0, 100.0, "put", True, 2.0, 2.0),
    ("Put ITM normal", 95.0, 100.0, "put", True, 5.0, 5.0),
    ("Put ITM deep", 90.0, 100.0, "put", True, 10.0, 10.0),
    ("Put ITM catastrophic", 65.0, 100.0, "put", True, 35.0, 35.0),
    
    # Real-world scenarios from bug reports
    ("FIG disaster", 39.0, 60.0, "put", True, 35.0, 21.0),  # V2.2 test case
    ("AVGO deep ITM", 336.0, 362.5, "put", True, 7.31, 26.5),  # V2.2 test case
]

THRESHOLD_SCENARIOS = [
    # (itm_pct, is_triple_witching, expected_should_close, expected_recommendation)
    
    # Normal day
    ("Normal: 2% ITM", 2.0, False, False, None),
    ("Normal: 4% ITM", 4.0, False, False, None),
    ("Normal: 5% ITM (threshold)", 5.0, False, True, "CLOSE_DONT_ROLL"),
    ("Normal: 7% ITM", 7.0, False, True, "CLOSE_DONT_ROLL"),
    ("Normal: 10% ITM (deep)", 10.0, False, True, "CLOSE_DONT_ROLL"),
    ("Normal: 15% ITM", 15.0, False, True, "CLOSE_DONT_ROLL"),
    ("Normal: 20% ITM (catastrophic)", 20.0, False, True, "CLOSE_IMMEDIATELY"),
    ("Normal: 35% ITM (disaster)", 35.0, False, True, "CLOSE_IMMEDIATELY"),
    
    # Triple Witching day (stricter)
    ("TW: 2% ITM", 2.0, True, False, None),
    ("TW: 3% ITM (threshold)", 3.0, True, True, "CLOSE_DONT_ROLL"),
    ("TW: 5% ITM", 5.0, True, True, "CLOSE_DONT_ROLL"),
    ("TW: 7.3% ITM (AVGO case)", 7.31, True, True, "CLOSE_DONT_ROLL"),
]

ECONOMIC_SANITY_SCENARIOS = [
    # (close_cost, best_roll_cost, expected_economically_sound, reason)
    
    ("Roll costs MORE", 5.00, 6.00, False, "Roll cost >= close cost"),
    ("Roll costs SAME", 5.00, 5.00, False, "Roll cost >= close cost"),
    ("Roll saves $10 (not enough $)", 5.00, 4.90, False, "Minimal savings"),
    ("Roll saves $0.50 (10% - threshold)", 5.00, 4.50, True, "Acceptable"),
    ("Roll saves $1.00 (20%)", 5.00, 4.00, True, "Good savings"),
]

ROLL_INTO_ITM_SCENARIOS = [
    # (current_price, new_strike, option_type, expected_blocked)
    
    # PUT: ITM when stock < strike
    # So new strike > stock = ITM (bad), new strike < stock = OTM (good)
    ("Put roll to OTM", 39.0, 36.0, "put", False),  # $36 strike, stock $39 -> OTM (stock > strike)
    ("Put roll into ITM", 39.0, 42.0, "put", True),  # $42 strike, stock $39 -> ITM (stock < strike)
    ("Put roll to OTM v2", 39.0, 35.0, "put", False),  # $35 strike, stock $39 -> OTM
    
    # CALL: ITM when stock > strike  
    # So new strike < stock = ITM (bad), new strike > stock = OTM (good)
    ("Call roll into ITM", 110.0, 105.0, "call", True),  # $105 strike, stock $110 -> ITM
    ("Call roll to OTM", 110.0, 115.0, "call", False),  # $115 strike, stock $110 -> OTM
]


# =============================================================================
# TESTS - ITM Calculations
# =============================================================================

class TestITMCalculations:
    """Test ITM percentage and intrinsic value calculations."""
    
    @pytest.mark.parametrize(
        "name,current_price,strike,option_type,expected_is_itm,expected_itm_pct,expected_intrinsic",
        ITM_CALCULATION_SCENARIOS
    )
    def test_itm_calculation(
        self, name, current_price, strike, option_type, 
        expected_is_itm, expected_itm_pct, expected_intrinsic
    ):
        """Test that ITM calculations match expected values."""
        # Import the utility function (will be created)
        from app.modules.strategies.utils.option_calculations import calculate_itm_status
        
        result = calculate_itm_status(current_price, strike, option_type)
        
        assert result['is_itm'] == expected_is_itm, f"{name}: is_itm mismatch"
        assert abs(result['itm_pct'] - expected_itm_pct) < 0.1, f"{name}: itm_pct mismatch (got {result['itm_pct']}, expected {expected_itm_pct})"
        assert abs(result['intrinsic_value'] - expected_intrinsic) < 0.1, f"{name}: intrinsic mismatch"


# =============================================================================
# TESTS - Threshold Enforcement
# =============================================================================

class TestThresholdEnforcement:
    """Test ITM threshold logic for CLOSE vs ROLL decisions."""
    
    @pytest.mark.parametrize(
        "name,itm_pct,is_triple_witching,expected_should_close,expected_recommendation",
        THRESHOLD_SCENARIOS
    )
    def test_threshold_check(
        self, name, itm_pct, is_triple_witching, 
        expected_should_close, expected_recommendation
    ):
        """Test that threshold checks return correct decisions."""
        from app.modules.strategies.utils.option_calculations import check_itm_thresholds
        
        result = check_itm_thresholds(itm_pct, is_triple_witching)
        
        assert result['should_close'] == expected_should_close, f"{name}: should_close mismatch"
        
        if expected_recommendation:
            assert result.get('recommendation') == expected_recommendation, f"{name}: recommendation mismatch"


# =============================================================================
# TESTS - Economic Sanity
# =============================================================================

class TestEconomicSanity:
    """Test economic viability checks for rolls."""
    
    @pytest.mark.parametrize(
        "name,close_cost,roll_cost,expected_sound,reason",
        ECONOMIC_SANITY_SCENARIOS
    )
    def test_economic_check(self, name, close_cost, roll_cost, expected_sound, reason):
        """Test that economic checks catch bad rolls."""
        from app.modules.strategies.utils.option_calculations import check_roll_economics
        
        result = check_roll_economics(
            close_cost=close_cost,
            roll_cost=roll_cost,
            contracts=1
        )
        
        assert result['economically_sound'] == expected_sound, f"{name}: {reason}"


# =============================================================================
# TESTS - Roll Into ITM Prevention
# =============================================================================

class TestRollIntoITMPrevention:
    """Test that we don't roll INTO another ITM position."""
    
    @pytest.mark.parametrize(
        "name,current_price,new_strike,option_type,expected_blocked",
        ROLL_INTO_ITM_SCENARIOS
    )
    def test_roll_into_itm(self, name, current_price, new_strike, option_type, expected_blocked):
        """Test that rolling into ITM is blocked."""
        from app.modules.strategies.utils.option_calculations import would_be_itm
        
        result = would_be_itm(current_price, new_strike, option_type)
        
        assert result == expected_blocked, f"{name}: would_be_itm mismatch"


# =============================================================================
# REGRESSION TESTS - V2.1/V2.2 Bug Fixes
# =============================================================================

class TestV2Regressions:
    """Ensure V2.1 and V2.2 bug fixes still work."""
    
    def test_fig_35_percent_itm_should_close(self):
        """FIG at 35% ITM should recommend CLOSE IMMEDIATELY, not ROLL."""
        from app.modules.strategies.utils.option_calculations import (
            calculate_itm_status,
            check_itm_thresholds
        )
        
        # FIG scenario: $60 put with stock at $39
        status = calculate_itm_status(current_price=39.0, strike=60.0, option_type="put")
        
        assert status['is_itm'] == True
        assert status['itm_pct'] >= 35.0  # Should be exactly 35%
        
        threshold = check_itm_thresholds(status['itm_pct'], is_triple_witching=False)
        
        assert threshold['should_close'] == True
        assert threshold['recommendation'] == 'CLOSE_IMMEDIATELY'
    
    def test_avgo_7pct_itm_triple_witching_should_close(self):
        """AVGO at 7.3% ITM on Triple Witching should recommend CLOSE."""
        from app.modules.strategies.utils.option_calculations import (
            calculate_itm_status,
            check_itm_thresholds
        )
        
        # AVGO scenario: $362.5 put with stock at $336 on Triple Witching
        status = calculate_itm_status(current_price=336.0, strike=362.5, option_type="put")
        
        assert status['is_itm'] == True
        assert abs(status['itm_pct'] - 7.31) < 0.5  # ~7.3%
        
        # On Triple Witching, threshold is 3%
        threshold = check_itm_thresholds(status['itm_pct'], is_triple_witching=True)
        
        assert threshold['should_close'] == True
        assert threshold['recommendation'] == 'CLOSE_DONT_ROLL'
    
    def test_roll_into_itm_blocked(self):
        """Rolling into another ITM position should be blocked."""
        from app.modules.strategies.utils.option_calculations import would_be_itm
        
        # FIG scenario: stock at $39, trying to roll to $36 strike
        # For a PUT, strike $36 with stock $39 = OTM (stock > strike)
        # But strike $42 with stock $39 = ITM (stock < strike)
        
        assert would_be_itm(39.0, 42.0, "put") == True, "Should block roll to $42 (ITM)"
        assert would_be_itm(39.0, 35.0, "put") == False, "Should allow roll to $35 (OTM)"
    
    def test_minimal_savings_blocked(self):
        """Roll with minimal savings should recommend CLOSE instead."""
        from app.modules.strategies.utils.option_calculations import check_roll_economics
        
        # Saving only $4 on a $100 position (4%) - should block
        result = check_roll_economics(close_cost=10.0, roll_cost=9.96, contracts=1)
        
        assert result['economically_sound'] == False, "Should block minimal savings"


# =============================================================================
# SNAPSHOT COMPARISON TEST (Run before/after refactor)
# =============================================================================

class TestSnapshotComparison:
    """Compare current behavior to baseline snapshots."""
    
    def test_snapshot_itm_calculations(self):
        """Verify ITM calculations haven't changed from baseline."""
        # This test compares against a known baseline
        # Run this BEFORE refactoring to establish baseline
        # Run AFTER refactoring to verify no changes
        
        baseline = {
            ("call", 102.0, 100.0): {"is_itm": True, "itm_pct": 2.0, "intrinsic": 2.0},
            ("put", 98.0, 100.0): {"is_itm": True, "itm_pct": 2.0, "intrinsic": 2.0},
            ("call", 95.0, 100.0): {"is_itm": False, "itm_pct": 0.0, "intrinsic": 0.0},
            ("put", 105.0, 100.0): {"is_itm": False, "itm_pct": 0.0, "intrinsic": 0.0},
            ("put", 39.0, 60.0): {"is_itm": True, "itm_pct": 35.0, "intrinsic": 21.0},  # FIG
        }
        
        from app.modules.strategies.utils.option_calculations import calculate_itm_status
        
        for (opt_type, price, strike), expected in baseline.items():
            result = calculate_itm_status(price, strike, opt_type)
            
            assert result['is_itm'] == expected['is_itm'], f"Snapshot mismatch: {opt_type} {price}/{strike}"
            assert abs(result['itm_pct'] - expected['itm_pct']) < 0.1
            assert abs(result['intrinsic_value'] - expected['intrinsic']) < 0.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

