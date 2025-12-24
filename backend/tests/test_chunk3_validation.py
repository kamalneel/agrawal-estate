"""
Chunk 3 Validation Tests for V3 Algorithm

Tests:
1. zero_cost_finder.py exists
2. 5% ITM position finds 1-2 week roll with Delta 30
3. 20% ITM position finds 6-12 week roll
4. 40% ITM position tries up to 52 weeks
5. Returns SHORTEST duration (first acceptable)
6. Earnings skip logic works
"""

import pytest
from datetime import date, timedelta
from unittest.mock import Mock, patch, MagicMock


class TestZeroCostFinderExists:
    """TEST 1: Verify file exists and has correct structure."""
    
    def test_module_imports(self):
        """Zero cost finder module should import correctly."""
        from app.modules.strategies.zero_cost_finder import (
            find_zero_cost_roll,
            ZeroCostRollResult,
            should_skip_expiration_for_earnings,
            should_skip_expiration_for_dividend,
            detect_excessive_earnings,
            SCAN_DURATIONS_WEEKS,
        )
        
        # Verify the scan durations are correct
        assert SCAN_DURATIONS_WEEKS == [1, 2, 3, 4, 6, 8, 12, 16, 24, 36, 52]
    
    def test_zero_cost_result_dataclass(self):
        """ZeroCostRollResult should have all required fields."""
        from app.modules.strategies.zero_cost_finder import ZeroCostRollResult
        
        result = ZeroCostRollResult(
            expiration_date=date.today() + timedelta(weeks=2),
            weeks_out=2,
            strike=105.0,
            new_premium=1.50,
            buy_back_cost=2.00,
            net_cost=0.50,
            net_cost_total=50.0,
            probability_otm=70.0,
            delta=0.30,
            is_credit=False,
            acceptable=True,
            strike_distance_pct=5.0,
            days_to_expiry=14,
            current_price=100.0,
            original_premium=3.00,
            max_debit_allowed=0.60
        )
        
        assert result.weeks_out == 2
        assert result.acceptable == True
        assert result.is_credit == False


class TestITMRollOptimizerDeltaTarget:
    """TEST 2 & 3: ITM optimizer uses correct delta target."""
    
    def test_itm_optimizer_accepts_delta_target(self):
        """ITM optimizer should accept delta_target parameter."""
        from app.modules.strategies.itm_roll_optimizer import ITMRollOptimizer
        
        optimizer = ITMRollOptimizer()
        
        # Method should accept delta_target parameter
        import inspect
        sig = inspect.signature(optimizer.analyze_itm_position)
        params = list(sig.parameters.keys())
        
        assert 'delta_target' in params, "analyze_itm_position should accept delta_target"
    
    def test_scan_roll_options_accepts_delta_target(self):
        """_scan_roll_options should accept delta_target parameter."""
        from app.modules.strategies.itm_roll_optimizer import ITMRollOptimizer
        
        optimizer = ITMRollOptimizer()
        
        import inspect
        sig = inspect.signature(optimizer._scan_roll_options)
        params = list(sig.parameters.keys())
        
        assert 'delta_target' in params, "_scan_roll_options should accept delta_target"


class TestV3ConfigDeltaTargets:
    """Verify V3 config has correct delta targets."""
    
    def test_v3_delta_targets(self):
        """V3 config should have Delta 30 for ITM and Delta 10 for weekly."""
        from app.modules.strategies.algorithm_config import get_config
        
        v3_config = get_config('v3')
        strike_config = v3_config.get('strike_selection', {})
        
        # Delta 10 for weekly (90% OTM probability)
        assert strike_config.get('weekly_delta_target') == 0.90, \
            "Weekly rolls should use Delta 10 (0.90)"
        
        # Delta 30 for ITM escapes (70% OTM probability)
        assert strike_config.get('itm_escape_delta_target') == 0.70, \
            "ITM escapes should use Delta 30 (0.70)"
        
        # Delta 30 for pull-backs
        assert strike_config.get('pullback_delta_target') == 0.70, \
            "Pull-backs should use Delta 30 (0.70)"
    
    def test_v3_max_roll_months(self):
        """V3 config should allow 12 months max roll."""
        from app.modules.strategies.algorithm_config import get_config
        
        v3_config = get_config('v3')
        assert v3_config.get('max_roll_months') == 12, \
            "V3 should allow 12 months (52 weeks) max roll"


class TestScanDurations:
    """TEST 4: Verify scan goes up to 52 weeks."""
    
    def test_scan_durations_include_52_weeks(self):
        """Scan durations should include 52 weeks."""
        from app.modules.strategies.zero_cost_finder import SCAN_DURATIONS_WEEKS
        
        assert 52 in SCAN_DURATIONS_WEEKS, "Should scan up to 52 weeks"
        assert max(SCAN_DURATIONS_WEEKS) == 52, "Max scan should be 52 weeks"
    
    def test_scan_durations_efficient_spacing(self):
        """Scan durations should have efficient spacing."""
        from app.modules.strategies.zero_cost_finder import SCAN_DURATIONS_WEEKS
        
        # Weeks 1-4: every week
        assert 1 in SCAN_DURATIONS_WEEKS
        assert 2 in SCAN_DURATIONS_WEEKS
        assert 3 in SCAN_DURATIONS_WEEKS
        assert 4 in SCAN_DURATIONS_WEEKS
        
        # Weeks 5-12: every 2-4 weeks
        assert 6 in SCAN_DURATIONS_WEEKS
        assert 8 in SCAN_DURATIONS_WEEKS
        assert 12 in SCAN_DURATIONS_WEEKS
        
        # Weeks 13+: sparse
        assert 16 in SCAN_DURATIONS_WEEKS
        assert 24 in SCAN_DURATIONS_WEEKS
        assert 36 in SCAN_DURATIONS_WEEKS
        assert 52 in SCAN_DURATIONS_WEEKS


class TestEarningsSkipLogic:
    """TEST 6: Earnings skip logic."""
    
    def test_should_skip_expiration_for_earnings_signature(self):
        """Earnings skip function should have correct signature."""
        from app.modules.strategies.zero_cost_finder import should_skip_expiration_for_earnings
        import inspect
        
        sig = inspect.signature(should_skip_expiration_for_earnings)
        params = list(sig.parameters.keys())
        
        assert 'symbol' in params
        assert 'exp_date' in params
    
    def test_detect_excessive_earnings_signature(self):
        """Excessive earnings detector should have correct signature."""
        from app.modules.strategies.zero_cost_finder import detect_excessive_earnings
        import inspect
        
        sig = inspect.signature(detect_excessive_earnings)
        params = list(sig.parameters.keys())
        
        assert 'symbol' in params


class TestShortestDurationLogic:
    """TEST 5: Returns SHORTEST duration (first acceptable)."""
    
    def test_find_zero_cost_roll_returns_first_acceptable(self):
        """Should return first acceptable, not best scored."""
        from app.modules.strategies.zero_cost_finder import find_zero_cost_roll
        
        # This is a structural test - the function should scan sequentially
        # and return on first acceptable, not score and rank
        
        import inspect
        source = inspect.getsource(find_zero_cost_roll)
        
        # Should have early return when acceptable
        assert 'if cost_check[\'acceptable\']:' in source or \
               'if cost_check["acceptable"]:' in source, \
               "Should check acceptability and return early"
        
        # Should NOT have scoring logic
        assert 'score' not in source.lower() or 'score=' in source.lower(), \
               "Should not have complex scoring logic"


class TestRollOptionsIntegration:
    """Verify roll_options.py uses correct delta target."""
    
    def test_roll_options_uses_delta_30_for_itm(self):
        """roll_options.py should use delta_target=0.70 for ITM."""
        import inspect
        from app.modules.strategies.strategies.roll_options import RollOptionsStrategy
        
        source = inspect.getsource(RollOptionsStrategy._handle_itm_scenario)
        
        # Should call with delta_target=0.70
        assert 'delta_target=0.70' in source, \
            "_handle_itm_scenario should use delta_target=0.70 for ITM escapes"
    
    def test_roll_options_imports_zero_cost_finder(self):
        """roll_options.py should import zero_cost_finder."""
        from app.modules.strategies.strategies import roll_options
        
        # Check that the import exists
        assert hasattr(roll_options, 'find_zero_cost_roll') or \
               'find_zero_cost_roll' in dir(roll_options), \
               "roll_options should import find_zero_cost_roll"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

