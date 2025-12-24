"""
Chunk 1 Validation Tests for V3 Algorithm

Tests:
1. timing_optimizer is deleted / no imports
2. New covered call works without timing predictions
3. TA-based wait still works
4. No errors in logs
"""

import pytest
import sys
from datetime import date, datetime
from unittest.mock import MagicMock, patch
from dataclasses import dataclass


# ============================================================================
# Mock objects for testing
# ============================================================================

@dataclass
class MockIndicators:
    """Mock technical indicators"""
    current_price: float = 175.0
    rsi_14: float = 55.0
    rsi_status: str = 'neutral'
    bb_position: str = 'middle'
    bb_upper: float = 180.0
    bb_middle: float = 175.0
    bb_lower: float = 170.0
    trend: str = 'bullish'
    nearest_support: float = 170.0
    nearest_resistance: float = 185.0
    weekly_volatility: float = 0.02
    prob_90_high: float = 185.0
    earnings_within_week: bool = False
    earnings_date: date = None


@dataclass
class MockIndicatorsOversold:
    """Mock technical indicators for oversold stock"""
    current_price: float = 175.0
    rsi_14: float = 25.0  # Oversold!
    rsi_status: str = 'oversold'
    bb_position: str = 'below_lower'
    bb_upper: float = 180.0
    bb_middle: float = 175.0
    bb_lower: float = 170.0
    trend: str = 'bearish'
    nearest_support: float = 165.0
    nearest_resistance: float = 180.0
    weekly_volatility: float = 0.03
    prob_90_high: float = 185.0
    earnings_within_week: bool = False
    earnings_date: date = None


@dataclass
class MockStrikeRec:
    """Mock strike recommendation"""
    recommended_strike: float = 185.0
    rationale: str = 'Delta 10 strike at 5.7% above current price'
    source: str = 'technical_analysis'


# ============================================================================
# TEST 1: Verify timing_optimizer is deleted
# ============================================================================

def test_timing_optimizer_not_exists():
    """timing_optimizer.py should not exist"""
    import os
    strategies_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    strategies_path = os.path.join(strategies_dir, 'app', 'modules', 'strategies')
    timing_optimizer_path = os.path.join(strategies_path, 'timing_optimizer.py')
    
    assert not os.path.exists(timing_optimizer_path), \
        f"timing_optimizer.py still exists at {timing_optimizer_path}"


def test_no_timing_optimizer_imports():
    """No imports of timing_optimizer in the codebase"""
    import os
    import re
    
    strategies_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    strategies_path = os.path.join(strategies_dir, 'app', 'modules', 'strategies')
    
    timing_import_pattern = re.compile(r'(import.*timing_optimizer|from.*timing_optimizer)')
    
    for root, dirs, files in os.walk(strategies_path):
        # Skip __pycache__ directories
        dirs[:] = [d for d in dirs if d != '__pycache__']
        
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                with open(filepath, 'r') as f:
                    content = f.read()
                    matches = timing_import_pattern.findall(content)
                    assert not matches, \
                        f"Found timing_optimizer import in {filepath}: {matches}"


# ============================================================================
# TEST 2: New covered call works (normal stock - should SELL)
# ============================================================================

def test_new_covered_call_sells_normal_stock():
    """Normal stock should get SELL recommendation, no timing predictions"""
    
    class MockTAServiceNormal:
        def should_wait_to_sell(self, symbol):
            return False, 'Stock in normal trading range', {}
        
        def get_technical_indicators(self, symbol):
            return MockIndicators()
        
        def recommend_strike_price(self, symbol, option_type, expiration_weeks, probability_target):
            return MockStrikeRec()
    
    with patch('app.modules.strategies.strategies.new_covered_call.get_technical_analysis_service') as mock_ta, \
         patch('app.modules.strategies.strategies.new_covered_call.get_sold_options_by_account') as mock_sold:
        
        mock_ta.return_value = MockTAServiceNormal()
        mock_sold.return_value = {}
        
        from app.modules.strategies.strategies.new_covered_call import NewCoveredCallStrategy
        
        # Create mock db
        mock_db = MagicMock()
        mock_result = [
            ('Fidelity Individual', 'AAPL', 200, 175.0, 35000, 'Apple Inc')
        ]
        mock_db.execute.return_value = mock_result
        
        strategy = NewCoveredCallStrategy(mock_db, {})
        recs = strategy.generate_recommendations({})
        
        # Should have at least one recommendation
        assert len(recs) > 0, "No recommendations generated for normal stock"
        
        rec = recs[0]
        
        # Should be a SELL recommendation
        assert rec.action_type == 'sell', f"Expected 'sell' action_type, got '{rec.action_type}'"
        
        # Should have correct strike
        assert rec.context.get('recommended_strike') == 185.0, \
            f"Expected strike 185.0, got {rec.context.get('recommended_strike')}"
        
        # NO timing predictions in output
        full_text = f'{rec.title} {rec.description} {rec.rationale}'.lower()
        timing_keywords = ['monday', 'iv bump', 'fomc', 'vix', 'friday afternoon', 'wait for monday']
        found_timing = [kw for kw in timing_keywords if kw in full_text]
        
        assert not found_timing, f"Found timing predictions: {found_timing}"


# ============================================================================
# TEST 3: TA-based wait still works (oversold stock - should WAIT)
# ============================================================================

def test_new_covered_call_waits_for_oversold_stock():
    """Oversold stock (RSI < 30) should get WAIT recommendation with TA reason"""
    
    class MockTAServiceOversold:
        def should_wait_to_sell(self, symbol):
            # TA says wait because oversold
            return True, 'RSI at 25 (oversold) - stock likely to bounce', {'rsi': 25}
        
        def get_technical_indicators(self, symbol):
            return MockIndicatorsOversold()
        
        def recommend_strike_price(self, symbol, option_type, expiration_weeks, probability_target):
            return MockStrikeRec()
    
    with patch('app.modules.strategies.strategies.new_covered_call.get_technical_analysis_service') as mock_ta, \
         patch('app.modules.strategies.strategies.new_covered_call.get_sold_options_by_account') as mock_sold:
        
        mock_ta.return_value = MockTAServiceOversold()
        mock_sold.return_value = {}
        
        from app.modules.strategies.strategies.new_covered_call import NewCoveredCallStrategy
        
        # Create mock db
        mock_db = MagicMock()
        mock_result = [
            ('Fidelity Individual', 'AAPL', 200, 175.0, 35000, 'Apple Inc')
        ]
        mock_db.execute.return_value = mock_result
        
        strategy = NewCoveredCallStrategy(mock_db, {})
        recs = strategy.generate_recommendations({})
        
        # Should have at least one recommendation
        assert len(recs) > 0, "No recommendations generated for oversold stock"
        
        rec = recs[0]
        
        # Should be a WAIT/monitor recommendation
        assert rec.action_type == 'monitor', f"Expected 'monitor' action_type, got '{rec.action_type}'"
        
        # Should mention RSI or oversold in rationale
        full_text = f'{rec.title} {rec.description} {rec.rationale}'.lower()
        assert 'rsi' in full_text or 'oversold' in full_text or 'bounce' in full_text, \
            f"Expected TA-based reason with RSI/oversold/bounce, got: {full_text}"
        
        # Still NO timing predictions
        timing_keywords = ['monday', 'iv bump', 'fomc', 'vix', 'friday afternoon']
        found_timing = [kw for kw in timing_keywords if kw in full_text]
        
        assert not found_timing, f"Found timing predictions in WAIT rec: {found_timing}"


# ============================================================================
# TEST 4: V3 config timing optimization disabled
# ============================================================================

def test_v3_timing_optimization_disabled():
    """V3 config should have timing optimization disabled"""
    from app.modules.strategies.algorithm_config import get_config, is_feature_enabled
    
    config = get_config('v3')
    
    # Timing should be disabled
    assert config['timing']['enable_timing_optimization'] == False, \
        "V3 should have timing optimization disabled"
    
    # is_feature_enabled should return False
    assert is_feature_enabled('timing', 'v3') == False, \
        "is_feature_enabled('timing', 'v3') should return False"


def test_v3_config_has_correct_delta_targets():
    """V3 config should have Delta 10 for weekly, Delta 30 for ITM"""
    from app.modules.strategies.algorithm_config import get_config
    
    config = get_config('v3')
    
    # Delta targets
    assert config['strike_selection']['weekly_delta_target'] == 0.90, \
        "Weekly delta should be 0.90 (Delta 10)"
    
    assert config['strike_selection']['itm_escape_delta_target'] == 0.70, \
        "ITM escape delta should be 0.70 (Delta 30)"
    
    assert config['strike_selection']['pullback_delta_target'] == 0.70, \
        "Pullback delta should be 0.70 (Delta 30)"


# ============================================================================
# Run tests if executed directly
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])

