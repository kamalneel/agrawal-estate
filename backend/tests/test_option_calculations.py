"""
Test Suite for Option Calculations Utility Module

V3.0 UPDATED: Tests for V3 simplified logic.

V3 Changes:
- Threshold checks ALWAYS return can_roll=True (no ITM% limits)
- Economic checks ALWAYS return economically_sound=True (use is_acceptable_cost)
- Only close when cannot find zero-cost roll within 52 weeks

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

# V3: Thresholds are REMOVED - all positions should return should_close=False
THRESHOLD_SCENARIOS_V3 = [
    # V3: ALL positions return should_close=False, can_roll=True
    # (itm_pct, is_triple_witching, expected_should_close)
    ("V3: 2% ITM", 2.0, False, False),
    ("V3: 5% ITM", 5.0, False, False),
    ("V3: 10% ITM", 10.0, False, False),
    ("V3: 20% ITM", 20.0, False, False),
    ("V3: 35% ITM (FIG)", 35.0, False, False),
    ("V3: Triple Witching 3%", 3.0, True, False),
    ("V3: Triple Witching 7%", 7.0, True, False),
]

# V3: 20% cost rule tests
COST_RULE_SCENARIOS_V3 = [
    # (net_cost, original_premium, expected_acceptable, reason)
    ("Credit always OK", -1.00, 2.00, True, "Any credit is acceptable"),
    ("Exact 20% threshold", 0.40, 2.00, True, "At threshold"),
    ("Just under 20%", 0.39, 2.00, True, "Under threshold"),
    ("Just over 20%", 0.41, 2.00, False, "Over threshold"),
    ("Large debit", 1.00, 2.00, False, "Way over"),
    ("Zero cost", 0.00, 2.00, True, "Zero is acceptable"),
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
# TESTS - Threshold Enforcement (V3: REMOVED)
# =============================================================================

class TestThresholdEnforcement:
    """V3: Test that threshold checks NEVER recommend close."""
    
    @pytest.mark.parametrize(
        "name,itm_pct,is_triple_witching,expected_should_close",
        THRESHOLD_SCENARIOS_V3
    )
    def test_v3_no_threshold_closes(
        self, name, itm_pct, is_triple_witching, expected_should_close
    ):
        """V3: All ITM positions should be rollable (no threshold closes)."""
        from app.modules.strategies.utils.option_calculations import check_itm_thresholds
        
        result = check_itm_thresholds(
            current_price=100.0,  # Dummy values - V3 ignores these for threshold decision
            strike=100.0 * (1 + itm_pct/100),  # Create ITM scenario
            option_type="call",
            is_triple_witching=is_triple_witching
        )
        
        # V3: should_close is ALWAYS False
        assert result['should_close'] == False, f"{name}: V3 should never auto-close based on ITM%"
        assert result.get('can_roll') == True, f"{name}: V3 should always allow rolling"


# =============================================================================
# TESTS - V3 Cost Rule (20% rule)
# =============================================================================

class TestV3CostRule:
    """Test V3's simple 20% cost rule."""
    
    @pytest.mark.parametrize(
        "name,net_cost,original_premium,expected_acceptable,reason",
        COST_RULE_SCENARIOS_V3
    )
    def test_v3_cost_rule(self, name, net_cost, original_premium, expected_acceptable, reason):
        """Test V3's simple 20% cost rule."""
        from app.modules.strategies.utils.option_calculations import is_acceptable_cost
        
        result = is_acceptable_cost(net_cost=net_cost, original_premium=original_premium)
        
        assert result['acceptable'] == expected_acceptable, f"{name}: {reason}"
    
    def test_credit_always_acceptable(self):
        """Any credit should be acceptable."""
        from app.modules.strategies.utils.option_calculations import is_acceptable_cost
        
        result = is_acceptable_cost(net_cost=-5.00, original_premium=1.00)
        assert result['acceptable'] == True
        assert result['is_credit'] == True
    
    def test_20_percent_boundary(self):
        """Test the 20% boundary exactly."""
        from app.modules.strategies.utils.option_calculations import is_acceptable_cost
        
        # Original premium $5.00, max debit = $1.00
        exactly_20 = is_acceptable_cost(net_cost=1.00, original_premium=5.00)
        assert exactly_20['acceptable'] == True, "Exactly 20% should be acceptable"
        
        over_20 = is_acceptable_cost(net_cost=1.01, original_premium=5.00)
        assert over_20['acceptable'] == False, "Over 20% should be rejected"


# =============================================================================
# TESTS - Economic Sanity (V3: DEPRECATED - Always True)
# =============================================================================

class TestEconomicSanity:
    """V3: Economic checks are deprecated - always return True."""
    
    def test_v3_always_economically_sound(self):
        """V3: check_roll_economics always returns True."""
        from app.modules.strategies.utils.option_calculations import check_roll_economics
        
        # Even "bad" economics should return True in V3
        result = check_roll_economics(
            close_cost=5.00,
            roll_options=[],
            current_price=100.0,
            option_type="call"
        )
        
        assert result['economically_sound'] == True, "V3 deprecated - should always be True"


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
# V3 TESTS - New Behavior
# =============================================================================

class TestV3Behavior:
    """V3 specific behavior tests."""
    
    def test_fig_35_percent_itm_can_roll(self):
        """V3: FIG at 35% ITM should still try to find zero-cost roll."""
        from app.modules.strategies.utils.option_calculations import (
            calculate_itm_status,
            check_itm_thresholds
        )
        
        # FIG scenario: $60 put with stock at $39
        status = calculate_itm_status(current_price=39.0, strike=60.0, option_type="put")
        
        assert status['is_itm'] == True
        assert status['itm_pct'] >= 35.0  # Should be exactly 35%
        
        # V3: No threshold closes - should still try to roll
        threshold = check_itm_thresholds(
            current_price=39.0, strike=60.0, option_type="put"
        )
        
        # V3: should_close is ALWAYS False
        assert threshold['should_close'] == False, "V3: Never auto-close based on ITM%"
        assert threshold['can_roll'] == True, "V3: Always try to find zero-cost roll"
    
    def test_avgo_triple_witching_can_roll(self):
        """V3: AVGO on Triple Witching should still try to roll."""
        from app.modules.strategies.utils.option_calculations import (
            calculate_itm_status,
            check_itm_thresholds
        )
        
        # AVGO scenario: $362.5 put with stock at $336 on Triple Witching
        status = calculate_itm_status(current_price=336.0, strike=362.5, option_type="put")
        
        assert status['is_itm'] == True
        
        # V3: No special Triple Witching threshold
        threshold = check_itm_thresholds(
            current_price=336.0, strike=362.5, option_type="put",
            is_triple_witching=True
        )
        
        # V3: should_close is ALWAYS False
        assert threshold['should_close'] == False, "V3: No Triple Witching thresholds"
    
    def test_would_be_itm_still_works(self):
        """would_be_itm helper still correctly identifies ITM positions."""
        from app.modules.strategies.utils.option_calculations import would_be_itm
        
        # FIG scenario: stock at $39
        assert would_be_itm(39.0, 42.0, "put") == True, "$42 strike would be ITM"
        assert would_be_itm(39.0, 35.0, "put") == False, "$35 strike would be OTM"
    
    def test_v3_20_percent_rule(self):
        """V3: Use is_acceptable_cost for 20% rule."""
        from app.modules.strategies.utils.option_calculations import is_acceptable_cost
        
        # Original premium $2.00, max debit = $0.40
        under = is_acceptable_cost(net_cost=0.30, original_premium=2.00)
        assert under['acceptable'] == True, "Under 20% should be acceptable"
        
        over = is_acceptable_cost(net_cost=0.50, original_premium=2.00)
        assert over['acceptable'] == False, "Over 20% should be rejected"


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

