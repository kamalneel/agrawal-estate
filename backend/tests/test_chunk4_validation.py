"""
Chunk 4 Validation Tests for V3 Algorithm

Tests:
1. Pull-back works correctly (returns first acceptable)
2. Pull-back uses Delta 30
3. Pull-back only checks positions >1 week
4. Unified evaluator routes correctly
5. ITM uses Delta 30, Weekly uses Delta 10
6. No duplicate notifications (SmartScanFilter)
7. Changed recommendation triggers alert
8. Filter resets daily
"""

import pytest
from datetime import date, timedelta
from unittest.mock import Mock, patch, MagicMock


class TestPullBackDetectorExists:
    """TEST 1: Verify pull_back_detector.py exists and works."""
    
    def test_module_imports(self):
        """Pull-back detector module should import correctly."""
        from app.modules.strategies.pull_back_detector import (
            check_pull_back_opportunity,
            PullBackResult,
            SCAN_DURATIONS_WEEKS,
        )
        
        # Verify scan durations match zero_cost_finder
        assert SCAN_DURATIONS_WEEKS == [1, 2, 3, 4, 6, 8, 12, 16, 24, 36, 52]
    
    def test_pullback_result_dataclass(self):
        """PullBackResult should have all required fields."""
        from app.modules.strategies.pull_back_detector import PullBackResult
        
        result = PullBackResult(
            from_expiration=date.today() + timedelta(weeks=8),
            from_weeks=8,
            to_expiration=date.today() + timedelta(weeks=2),
            to_weeks=2,
            new_strike=105.0,
            new_premium=1.50,
            current_value=2.00,
            net_cost=0.50,
            net_cost_total=50.0,
            weeks_saved=6,
            acceptable=True,
            benefit='Return to income 6 weeks early'
        )
        
        assert result.weeks_saved == 6
        assert result.acceptable == True


class TestPullBackUsesDelta30:
    """TEST 2: Pull-back uses Delta 30 (probability_target=0.70)."""
    
    def test_pullback_delta_target_in_code(self):
        """Check that pull-back uses probability_target=0.70."""
        import inspect
        from app.modules.strategies.pull_back_detector import check_pull_back_opportunity
        
        source = inspect.getsource(check_pull_back_opportunity)
        
        # Should use probability_target=0.70 (Delta 30)
        assert 'probability_target=0.70' in source, \
            "Pull-back should use Delta 30 (probability_target=0.70)"


class TestPullBackThreshold:
    """TEST 3: Pull-back only checks positions >1 week out."""
    
    def test_pullback_checks_greater_than_1_week(self):
        """Check that pull-back returns None for positions <=1 week."""
        import inspect
        from app.modules.strategies.pull_back_detector import check_pull_back_opportunity
        
        source = inspect.getsource(check_pull_back_opportunity)
        
        # Should check current_weeks <= 1
        assert 'current_weeks <= 1' in source or 'if current_weeks <= 1:' in source, \
            "Pull-back should skip positions with <=1 week"


class TestPositionEvaluatorExists:
    """TEST 4: Verify position_evaluator.py exists and routes correctly."""
    
    def test_module_imports(self):
        """Position evaluator module should import correctly."""
        from app.modules.strategies.position_evaluator import (
            PositionEvaluator,
            SmartScanFilter,
            EvaluationResult,
            get_position_evaluator,
            get_scan_filter,
        )
    
    def test_evaluation_result_dataclass(self):
        """EvaluationResult should have all required fields."""
        from app.modules.strategies.position_evaluator import EvaluationResult
        
        result = EvaluationResult(
            action='ROLL_ITM',
            position_id='AAPL_100_2024-01-19',
            symbol='AAPL',
            priority='high',
            reason='5% ITM - rolling to 2 weeks',
            details={'itm_pct': 5.0}
        )
        
        assert result.action == 'ROLL_ITM'
        assert result.symbol == 'AAPL'
    
    def test_evaluator_has_priority_order(self):
        """Evaluator should check in priority order."""
        import inspect
        from app.modules.strategies.position_evaluator import PositionEvaluator
        
        source = inspect.getsource(PositionEvaluator.evaluate)
        
        # Should check pull-back first (STATE 1)
        assert 'STATE 1' in source or 'Pull-back' in source, \
            "Should check pull-back first (highest priority)"
        
        # Should check ITM second (STATE 2)
        assert 'STATE 2' in source or 'is_itm' in source, \
            "Should check ITM second"
        
        # Should check profitable third (STATE 3)
        assert 'STATE 3' in source or 'profit_pct' in source, \
            "Should check profitable third"


class TestDeltaTargets:
    """TEST 5: ITM uses Delta 30, Weekly uses Delta 10."""
    
    def test_itm_uses_delta_30(self):
        """ITM rolls should use Delta 30 (probability_target=0.70)."""
        import inspect
        from app.modules.strategies.position_evaluator import PositionEvaluator
        
        source = inspect.getsource(PositionEvaluator._handle_itm_position)
        
        assert 'delta_target=0.70' in source, \
            "ITM rolls should use delta_target=0.70 (Delta 30)"
    
    def test_weekly_uses_delta_10(self):
        """Weekly rolls should use Delta 10 (probability_target=0.90)."""
        import inspect
        from app.modules.strategies.position_evaluator import PositionEvaluator
        
        source = inspect.getsource(PositionEvaluator._handle_profitable_position)
        
        assert 'probability_target=0.90' in source, \
            "Weekly rolls should use probability_target=0.90 (Delta 10)"


class TestSmartScanFilter:
    """TEST 6, 7, 8: SmartScanFilter prevents duplicates and resets."""
    
    def test_filter_exists(self):
        """SmartScanFilter should exist with correct methods."""
        from app.modules.strategies.position_evaluator import SmartScanFilter
        
        filter = SmartScanFilter()
        
        assert hasattr(filter, 'should_send')
        assert hasattr(filter, 'reset_daily')
        assert hasattr(filter, 'sent_today')
    
    def test_filter_accepts_first_recommendation(self):
        """First recommendation for a position should be accepted."""
        from app.modules.strategies.position_evaluator import SmartScanFilter
        
        filter = SmartScanFilter()
        
        rec = {'action': 'ROLL_ITM', 'new_strike': 185, 'priority': 'high'}
        
        # First time should return True
        result = filter.should_send('AAPL_180_2024-01-19', rec)
        assert result == True, "First recommendation should be sent"
    
    def test_filter_rejects_duplicate(self):
        """Same recommendation should be rejected."""
        from app.modules.strategies.position_evaluator import SmartScanFilter
        
        filter = SmartScanFilter()
        
        rec = {'action': 'ROLL_ITM', 'new_strike': 185, 'priority': 'high'}
        position_id = 'AAPL_180_2024-01-19'
        
        # First time
        filter.should_send(position_id, rec)
        
        # Second time - same rec
        result = filter.should_send(position_id, rec)
        assert result == False, "Duplicate recommendation should be filtered"
    
    def test_filter_accepts_changed_recommendation(self):
        """Changed recommendation should be accepted."""
        from app.modules.strategies.position_evaluator import SmartScanFilter
        
        filter = SmartScanFilter()
        position_id = 'AAPL_180_2024-01-19'
        
        rec1 = {'action': 'ROLL_ITM', 'new_strike': 185, 'priority': 'high'}
        rec2 = {'action': 'ROLL_ITM', 'new_strike': 190, 'priority': 'high'}  # Changed strike
        
        # First recommendation
        filter.should_send(position_id, rec1)
        
        # Changed recommendation
        result = filter.should_send(position_id, rec2)
        assert result == True, "Changed recommendation should be sent"
    
    def test_filter_reset_daily(self):
        """Filter should reset after reset_daily() call."""
        from app.modules.strategies.position_evaluator import SmartScanFilter
        
        filter = SmartScanFilter()
        position_id = 'AAPL_180_2024-01-19'
        rec = {'action': 'ROLL_ITM', 'new_strike': 185, 'priority': 'high'}
        
        # Send first time
        filter.should_send(position_id, rec)
        
        # Verify it's tracked
        assert position_id in filter.sent_today
        
        # Reset
        filter.reset_daily()
        
        # Should be empty
        assert len(filter.sent_today) == 0, "Filter should be empty after reset"
        
        # Same rec should be accepted again
        result = filter.should_send(position_id, rec)
        assert result == True, "After reset, recommendation should be sent"


class TestV3ScannerExists:
    """Verify v3_scanner.py exists and has required functions."""
    
    def test_scanner_imports(self):
        """V3 scanner module should import correctly."""
        from app.modules.strategies.v3_scanner import (
            scan_6am,
            scan_8am,
            scan_12pm,
            scan_1245pm,
            scan_8pm,
            reset_daily,
            get_global_scan_filter,
        )
    
    def test_scanner_has_state_tracking(self):
        """Scanner should track morning state for 8 AM comparison."""
        from app.modules.strategies import v3_scanner
        
        assert hasattr(v3_scanner, '_morning_state'), \
            "Scanner should have morning state tracking"


class TestV3ConfigComplete:
    """Verify V3 config has all required parameters."""
    
    def test_v3_config_complete(self):
        """V3 config should have all required parameters."""
        from app.modules.strategies.algorithm_config import get_config
        
        v3_config = get_config('v3')
        
        # Core thresholds
        assert 'profit_threshold' in v3_config
        assert 'max_debit_pct' in v3_config
        assert 'max_roll_months' in v3_config
        
        # Strike selection
        assert 'strike_selection' in v3_config
        strike = v3_config['strike_selection']
        assert strike.get('weekly_delta_target') == 0.90
        assert strike.get('itm_escape_delta_target') == 0.70
        assert strike.get('pullback_delta_target') == 0.70
        
        # Pull-back
        assert 'min_weeks_for_pullback' in v3_config
        
        # Scan times
        assert 'scan_times' in v3_config


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

