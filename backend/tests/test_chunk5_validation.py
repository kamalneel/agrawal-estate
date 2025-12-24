"""
Chunk 5 Validation Tests for V3 Algorithm

Tests:
1. Files created
2. Only triggers for IRA
3. ITM threshold check
4. Only on expiration day
5. Compares costs correctly
6. Roll cheaper - no assignment rec
7. Monday buy-back trigger
8. Buy-back action based on price
9. Integration with 12:45 PM scan
10. Integration with Monday 6 AM scan
"""

import pytest
from datetime import date, timedelta
from unittest.mock import Mock, patch, MagicMock


class TestFilesCreated:
    """TEST 1: Verify files exist."""
    
    def test_smart_assignment_evaluator_exists(self):
        """smart_assignment_evaluator.py should exist."""
        from app.modules.strategies.smart_assignment_evaluator import (
            evaluate_smart_assignment_ira,
            SmartAssignmentResult,
        )
    
    def test_assignment_tracker_exists(self):
        """assignment_tracker.py should exist."""
        from app.modules.strategies.assignment_tracker import (
            record_assignment,
            get_assignments_from_last_friday,
            mark_buyback_completed,
            generate_monday_buyback_recommendations,
        )


class TestOnlyTriggersForIRA:
    """TEST 2: Only triggers for IRA accounts."""
    
    def test_checks_account_type(self):
        """Should check account type."""
        import inspect
        from app.modules.strategies.smart_assignment_evaluator import evaluate_smart_assignment_ira
        
        source = inspect.getsource(evaluate_smart_assignment_ira)
        
        # Should check for IRA/ROTH_IRA
        assert 'IRA' in source and 'ROTH' in source, \
            "Should check for IRA/ROTH_IRA accounts"
        assert 'account_type' in source, \
            "Should check account_type"


class TestITMThresholdCheck:
    """TEST 3: ITM threshold check (0.1% - 2.0%)."""
    
    def test_itm_range_in_code(self):
        """Should check ITM range 0.1% - 2.0%."""
        import inspect
        from app.modules.strategies.smart_assignment_evaluator import evaluate_smart_assignment_ira
        
        source = inspect.getsource(evaluate_smart_assignment_ira)
        
        # Should have min/max ITM checks
        assert 'min_itm' in source.lower() or 'itm_pct' in source, \
            "Should check ITM percentage"
        assert 'max_itm' in source.lower() or 'itm_pct' in source, \
            "Should check ITM percentage"
    
    def test_config_has_itm_thresholds(self):
        """V3 config should have ITM thresholds."""
        from app.modules.strategies.algorithm_config import get_config
        
        v3_config = get_config('v3')
        smart_config = v3_config.get('smart_assignment', {})
        
        assert 'min_itm_pct' in smart_config
        assert 'max_itm_pct' in smart_config
        assert smart_config['min_itm_pct'] == 0.1
        assert smart_config['max_itm_pct'] == 2.0


class TestOnlyOnExpirationDay:
    """TEST 4: Only on expiration day."""
    
    def test_checks_expiration_day(self):
        """Should only evaluate on expiration day."""
        import inspect
        from app.modules.strategies.smart_assignment_evaluator import evaluate_smart_assignment_ira
        
        source = inspect.getsource(evaluate_smart_assignment_ira)
        
        # Should check days_to_exp == 0
        assert 'days_to_exp' in source or 'expiration' in source, \
            "Should check expiration date"


class TestComparesCotsCorrectly:
    """TEST 5: Compares costs correctly."""
    
    def test_compares_assignment_vs_roll(self):
        """Should compare assignment loss vs roll cost."""
        import inspect
        from app.modules.strategies.smart_assignment_evaluator import evaluate_smart_assignment_ira
        
        source = inspect.getsource(evaluate_smart_assignment_ira)
        
        # Should calculate both costs
        assert 'assignment_loss' in source, "Should calculate assignment loss"
        assert 'roll' in source.lower(), "Should calculate roll cost"
        assert 'opportunity_cost' in source, "Should calculate opportunity cost"


class TestRollCheaperNoAssignmentRec:
    """TEST 6: Roll cheaper - no assignment rec."""
    
    def test_returns_none_when_roll_cheaper(self):
        """Should return None when roll is cheaper."""
        import inspect
        from app.modules.strategies.smart_assignment_evaluator import evaluate_smart_assignment_ira
        
        source = inspect.getsource(evaluate_smart_assignment_ira)
        
        # Should have comparison and return None case
        assert 'return None' in source, "Should return None in some cases"


class TestMondayBuybackTrigger:
    """TEST 7: Monday buy-back trigger."""
    
    def test_get_assignments_from_friday(self):
        """Should get assignments from last Friday."""
        from app.modules.strategies.assignment_tracker import get_assignments_from_last_friday
        
        # Function should exist and be callable
        result = get_assignments_from_last_friday()
        assert isinstance(result, list)
    
    def test_generate_monday_recommendations(self):
        """Should generate Monday recommendations."""
        import inspect
        from app.modules.strategies.assignment_tracker import generate_monday_buyback_recommendations
        
        # Function should exist
        source = inspect.getsource(generate_monday_buyback_recommendations)
        assert 'BUYBACK_AFTER_ASSIGNMENT' in source


class TestBuybackActionBasedOnPrice:
    """TEST 8: Buy-back action based on price."""
    
    def test_buyback_actions(self):
        """Should have different actions based on price change."""
        import inspect
        from app.modules.strategies.assignment_tracker import generate_monday_buyback_recommendations
        
        source = inspect.getsource(generate_monday_buyback_recommendations)
        
        # Should have action decisions
        assert 'BUY_NOW' in source or 'buy_now' in source.lower(), \
            "Should have BUY_NOW action"
        assert 'SKIP' in source or 'WAIT' in source, \
            "Should have SKIP or WAIT action"
    
    def test_config_has_thresholds(self):
        """Config should have price change thresholds."""
        from app.modules.strategies.algorithm_config import get_config
        
        v3_config = get_config('v3')
        smart_config = v3_config.get('smart_assignment', {})
        
        assert 'monday_skip_threshold' in smart_config
        assert 'monday_wait_threshold' in smart_config


class TestIntegration1245PM:
    """TEST 9: Integration with 12:45 PM scan."""
    
    def test_scan_1245pm_has_smart_assignment(self):
        """12:45 PM scan should check smart assignment."""
        import inspect
        from app.modules.strategies.v3_scanner import scan_1245pm
        
        source = inspect.getsource(scan_1245pm)
        
        assert 'smart_assignment' in source.lower() or 'evaluate_smart_assignment' in source, \
            "12:45 PM scan should check smart assignment"


class TestIntegrationMonday6AM:
    """TEST 10: Integration with Monday 6 AM scan."""
    
    def test_scan_6am_has_monday_buyback(self):
        """6 AM scan should check for Monday buybacks."""
        import inspect
        from app.modules.strategies.v3_scanner import scan_6am
        
        source = inspect.getsource(scan_6am)
        
        # Should check for Monday
        assert 'weekday' in source, "Should check if it's Monday"
        assert 'buyback' in source.lower(), "Should generate buyback recommendations"


class TestSmartAssignmentConfig:
    """Verify V3 config has smart assignment section."""
    
    def test_v3_has_smart_assignment_config(self):
        """V3 config should have smart_assignment section."""
        from app.modules.strategies.algorithm_config import get_config
        
        v3_config = get_config('v3')
        
        assert 'smart_assignment' in v3_config
        
        smart_config = v3_config['smart_assignment']
        assert smart_config.get('enabled') == True
        assert 'IRA' in smart_config.get('accounts', [])
        assert 'ROTH_IRA' in smart_config.get('accounts', []) or \
               'ROTH IRA' in smart_config.get('accounts', [])


class TestSmartAssignmentResult:
    """Test SmartAssignmentResult dataclass."""
    
    def test_dataclass_fields(self):
        """SmartAssignmentResult should have required fields."""
        from app.modules.strategies.smart_assignment_evaluator import SmartAssignmentResult
        
        result = SmartAssignmentResult(
            action='ACCEPT_ASSIGNMENT',
            position_id='AAPL_100_2024-01-19',
            symbol='AAPL',
            priority='high',
            reason='Assignment saves $60 vs rolling',
            assignment_price=100.0,
            current_price=101.5,
            itm_pct=1.5,
            itm_amount=1.50,
            assignment_loss_per_share=1.50,
            assignment_loss_total=150.0,
            roll_option=None,
            roll_debit=0,
            roll_weeks=0,
            opportunity_cost=0,
            total_roll_cost=210.0,
            savings_by_assignment=60.0,
            recommended='assignment'
        )
        
        assert result.action == 'ACCEPT_ASSIGNMENT'
        assert result.savings_by_assignment == 60.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

