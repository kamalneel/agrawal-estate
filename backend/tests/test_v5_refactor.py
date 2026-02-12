"""
V5 Refactoring Tests

Verifies that the decomposed V5 engines produce identical behavior to the
monolithic v5_notification_service.py and v5_position_evaluator.py.

Test Groups:
1. Smoke Tests - all modules import, classes instantiate
2. Engine Unit Tests - each engine produces correct output types
3. Integration Tests - orchestrator delegates correctly, facade works
"""

import pytest
from dataclasses import dataclass, field
from datetime import date, timedelta, datetime
from decimal import Decimal
from unittest.mock import Mock, MagicMock, patch
from typing import Optional


# ============================================================================
# MOCK HELPERS
# ============================================================================

@dataclass
class MockPosition:
    """Mock position matching SoldOption interface."""
    id: int = 1
    symbol: str = "AAPL"
    strike_price: Decimal = Decimal("150.0")
    option_type: str = "call"
    expiration_date: date = None
    contracts_sold: int = 1
    original_premium: float = 2.50
    current_premium: float = 0.50
    premium_per_contract: float = 0.50
    account_name: str = "Test Account"
    gain_loss_percent: float = 80.0
    snapshot: object = None
    days_held: int = 5
    total_days: int = 7

    def __post_init__(self):
        if self.expiration_date is None:
            self.expiration_date = date.today() + timedelta(days=7)


@dataclass
class MockIndicators:
    """Mock technical indicators."""
    current_price: float = 145.0
    rsi_14: float = 50.0
    trend: str = "neutral"
    weekly_volatility: float = 0.02


@dataclass
class MockStrikeRec:
    """Mock strike recommendation."""
    recommended_strike: float = 155.0
    rationale: str = "Delta 10 target"


@dataclass
class MockOptionQuote:
    """Mock option quote."""
    bid: float = 1.50
    ask: float = 1.60
    last_price: float = 1.55


@dataclass
class MockSnapshot:
    """Mock snapshot for positions."""
    id: int = 100
    account_name: str = "Test Account"


def make_mock_ta_service(current_price=145.0, rsi=50.0, trend="neutral", should_wait=False):
    """Create a mock TA service."""
    ta = Mock()
    ta.get_technical_indicators.return_value = MockIndicators(
        current_price=current_price, rsi_14=rsi, trend=trend
    )
    ta.should_wait_to_sell.return_value = (should_wait, "test reason", None)
    ta.recommend_strike_price.return_value = MockStrikeRec(
        recommended_strike=round(current_price * 1.05, 0)
    )
    return ta


def make_mock_option_fetcher(bid=1.50, ask=1.60):
    """Create a mock option chain fetcher."""
    fetcher = Mock()
    fetcher.get_option_quote.return_value = MockOptionQuote(bid=bid, ask=ask)
    return fetcher


# ============================================================================
# 1. SMOKE TESTS - Imports and Instantiation
# ============================================================================

class TestSmokeImports:
    """Verify all modules import correctly and classes can be created."""

    def test_base_imports(self):
        from app.modules.strategies.v5.base import (
            V5EvaluationResult,
            LIFE_SUPPORT_THRESHOLDS,
            get_v5_config,
            calculate_intrinsic_time_value,
            estimate_current_premium,
            get_iv_category,
            get_stuck_category,
            calculate_escape_strike,
            get_next_friday,
            estimate_roll_credits,
        )
        assert V5EvaluationResult is not None
        assert isinstance(LIFE_SUPPORT_THRESHOLDS, dict)
        assert "high_iv" in LIFE_SUPPORT_THRESHOLDS

    def test_engine_uncovered_imports(self):
        from app.modules.strategies.v5.engine_uncovered import UncoveredEngine
        assert UncoveredEngine is not None

    def test_engine_puts_imports(self):
        from app.modules.strategies.v5.engine_puts import PutEngine
        assert PutEngine is not None

    def test_engine_profit_imports(self):
        from app.modules.strategies.v5.engine_profit import ProfitEngine
        assert ProfitEngine is not None

    def test_engine_underwater_imports(self):
        from app.modules.strategies.v5.engine_underwater import UnderwaterEngine
        assert UnderwaterEngine is not None

    def test_orchestrator_imports(self):
        from app.modules.strategies.v5.orchestrator import V5Orchestrator, V5_VERSION_TAG
        assert V5Orchestrator is not None
        assert V5_VERSION_TAG == "v5_standalone"

    def test_facade_notification_service_imports(self):
        """Verify the facade re-exports everything consumers need."""
        from app.modules.strategies.v5_notification_service import (
            V5NotificationService,
            get_v5_notification_service,
            V5_VERSION_TAG,
        )
        assert V5_VERSION_TAG == "v5_standalone"
        assert V5NotificationService is not None

    def test_facade_position_evaluator_imports(self):
        """Verify the evaluator facade re-exports everything."""
        from app.modules.strategies.v5_position_evaluator import (
            V5PositionEvaluator,
            V5EvaluationResult,
            get_v5_evaluator,
        )
        assert V5PositionEvaluator is not None
        assert V5EvaluationResult is not None

    def test_v5_package_init_imports(self):
        """Verify the v5 package __init__ exports."""
        from app.modules.strategies.v5 import V5EvaluationResult, LIFE_SUPPORT_THRESHOLDS
        assert V5EvaluationResult is not None

    def test_v5_evaluation_result_identity(self):
        """V5EvaluationResult from facade == from v5.base (same class)."""
        from app.modules.strategies.v5_position_evaluator import V5EvaluationResult as FromFacade
        from app.modules.strategies.v5.base import V5EvaluationResult as FromBase
        assert FromFacade is FromBase


# ============================================================================
# 2. ENGINE UNIT TESTS - Verify output types and behavior
# ============================================================================

class TestBaseHelpers:
    """Test shared helper functions in v5/base.py."""

    def test_get_iv_category(self):
        from app.modules.strategies.v5.base import get_iv_category
        assert get_iv_category("HOOD") == "high_iv"
        assert get_iv_category("AAPL") == "low_iv"
        assert get_iv_category("PLTR") == "medium_iv"

    def test_get_stuck_category(self):
        from app.modules.strategies.v5.base import get_stuck_category
        assert get_stuck_category(3.0, "medium_iv") == "HEALTHY"
        assert get_stuck_category(10.0, "medium_iv") == "STUCK"
        assert get_stuck_category(18.0, "medium_iv") == "LIFE_SUPPORT"
        assert get_stuck_category(25.0, "medium_iv") == "DROWNING"

    def test_calculate_intrinsic_time_value_call_itm(self):
        from app.modules.strategies.v5.base import calculate_intrinsic_time_value
        pos = MockPosition(strike_price=Decimal("100"), option_type="call")
        intrinsic, time_val = calculate_intrinsic_time_value(pos, 110.0, 12.0)
        assert intrinsic == 10.0  # 110 - 100
        assert time_val == 2.0   # 12 - 10

    def test_calculate_intrinsic_time_value_call_otm(self):
        from app.modules.strategies.v5.base import calculate_intrinsic_time_value
        pos = MockPosition(strike_price=Decimal("100"), option_type="call")
        intrinsic, time_val = calculate_intrinsic_time_value(pos, 90.0, 2.0)
        assert intrinsic == 0.0  # OTM
        assert time_val == 2.0   # All time value

    def test_calculate_intrinsic_time_value_put_itm(self):
        from app.modules.strategies.v5.base import calculate_intrinsic_time_value
        pos = MockPosition(strike_price=Decimal("100"), option_type="put")
        intrinsic, time_val = calculate_intrinsic_time_value(pos, 90.0, 12.0)
        assert intrinsic == 10.0
        assert time_val == 2.0

    def test_calculate_escape_strike_call(self):
        from app.modules.strategies.v5.base import calculate_escape_strike
        # Call ITM: price=155, strike=150 → escape to 160
        new_strike = calculate_escape_strike(150.0, 155.0, "call", True)
        assert new_strike == 160.0  # Next $5 increment above price

    def test_calculate_escape_strike_put(self):
        from app.modules.strategies.v5.base import calculate_escape_strike
        # Put ITM: price=145, strike=150 → escape to 145
        new_strike = calculate_escape_strike(150.0, 145.0, "put", True)
        assert new_strike == 145.0

    def test_get_next_friday(self):
        from app.modules.strategies.v5.base import get_next_friday
        friday = get_next_friday()
        assert friday.weekday() == 4  # Friday
        assert friday > date.today()


class TestProfitEngine:
    """Test Engine 3: Profit-taking / OTM evaluation."""

    def setup_method(self):
        self.ta_service = make_mock_ta_service()
        self.option_fetcher = make_mock_option_fetcher()
        from app.modules.strategies.v5.engine_profit import ProfitEngine
        self.engine = ProfitEngine(
            ta_service=self.ta_service,
            option_fetcher=self.option_fetcher
        )

    def test_early_profit_returns_close(self):
        """70%+ profit → CLOSE."""
        pos = MockPosition(original_premium=2.0, current_premium=0.40)
        result = self.engine.evaluate_early_profit(
            position=pos,
            profit_pct=0.80,
            original_premium=2.0,
            current_premium=0.40,
            current_price=145.0,
            days_to_exp=5
        )
        assert result.action == "CLOSE"
        assert result.symbol == "AAPL"
        assert "Lock In Profits" in result.reason
        assert result.philosophy_applied == "lock_in_profits"

    def test_otm_high_profit_close_with_followup(self):
        """OTM with 80%+ profit → CLOSE with follow-up."""
        pos = MockPosition()
        indicators = MockIndicators()
        result = self.engine.evaluate_otm(
            position=pos,
            itm_pct=-5.0,  # OTM
            current_price=145.0,
            current_premium=0.40,
            profit_pct=0.85,
            days_to_exp=5,
            indicators=indicators
        )
        assert result.action == "CLOSE"
        assert result.has_follow_up is True
        assert result.follow_up_condition == "stock_pulls_back"

    def test_otm_moderate_profit_short_dte_rolls(self):
        """OTM 60%+ profit with <=7 DTE → ROLL."""
        pos = MockPosition(expiration_date=date.today() + timedelta(days=5))
        indicators = MockIndicators()
        result = self.engine.evaluate_otm(
            position=pos,
            itm_pct=-3.0,
            current_price=145.0,
            current_premium=0.80,
            profit_pct=0.65,
            days_to_exp=5,
            indicators=indicators
        )
        assert result.action == "ROLL"
        assert result.new_strike is not None
        assert result.new_expiration is not None

    def test_otm_moderate_profit_long_dte_holds(self):
        """OTM 60%+ profit with >7 DTE → HOLD."""
        pos = MockPosition(expiration_date=date.today() + timedelta(days=14))
        indicators = MockIndicators()
        result = self.engine.evaluate_otm(
            position=pos,
            itm_pct=-3.0,
            current_price=145.0,
            current_premium=0.80,
            profit_pct=0.65,
            days_to_exp=14,
            indicators=indicators
        )
        assert result.action == "HOLD"

    def test_otm_low_profit_holds(self):
        """OTM with low profit → HOLD."""
        pos = MockPosition()
        indicators = MockIndicators()
        result = self.engine.evaluate_otm(
            position=pos,
            itm_pct=-5.0,
            current_price=145.0,
            current_premium=1.50,
            profit_pct=0.40,
            days_to_exp=5,
            indicators=indicators
        )
        assert result.action == "HOLD"

    def test_time_cushion_otm_high_profit_rolls(self):
        """OTM <=2 DTE with 80%+ profit → ROLL to continue earning."""
        pos = MockPosition(expiration_date=date.today() + timedelta(days=1))
        result = self.engine.evaluate_time_cushion_otm(
            position=pos,
            profit_pct=0.85,
            current_price=145.0,
            current_premium=0.30,
            intrinsic_pct=0.0
        )
        assert result.action == "ROLL"

    def test_time_cushion_otm_low_profit_expires(self):
        """OTM <=2 DTE with low profit → LET_EXPIRE."""
        pos = MockPosition(expiration_date=date.today() + timedelta(days=1))
        result = self.engine.evaluate_time_cushion_otm(
            position=pos,
            profit_pct=0.50,
            current_price=145.0,
            current_premium=1.25,
            intrinsic_pct=0.0
        )
        assert result.action == "LET_EXPIRE"

    def test_fallback_high_profit_closes(self):
        """Fallback with 70%+ profit → CLOSE."""
        pos = MockPosition(gain_loss_percent=75.0)
        result = self.engine.evaluate_fallback(pos)
        assert result.action == "CLOSE"
        assert result.details.get("ta_unavailable") is True

    def test_fallback_low_profit_holds(self):
        """Fallback with low profit → HOLD."""
        pos = MockPosition(gain_loss_percent=30.0)
        result = self.engine.evaluate_fallback(pos)
        assert result.action == "HOLD"


class TestUnderwaterEngine:
    """Test Engine 4: Underwater / ITM position management."""

    def setup_method(self):
        self.ta_service = make_mock_ta_service(current_price=160.0)
        self.option_fetcher = make_mock_option_fetcher(bid=12.0, ask=12.50)
        from app.modules.strategies.v5.engine_underwater import UnderwaterEngine
        self.engine = UnderwaterEngine(
            ta_service=self.ta_service,
            option_fetcher=self.option_fetcher,
            db=None
        )

    def test_shallow_itm_holds(self):
        """Shallow ITM (<50% intrinsic) → HOLD for mean reversion."""
        pos = MockPosition(
            strike_price=Decimal("150"),
            option_type="call",
            current_premium=5.0,
        )
        result = self.engine.evaluate(
            position=pos,
            is_itm=True,
            itm_pct=3.0,
            intrinsic_pct=0.30,  # Only 30% intrinsic
            intrinsic_value=1.5,
            time_value=3.5,
            current_price=154.5,
            current_premium=5.0,
            profit_pct=-1.0,
            days_to_exp=7,
        )
        assert result.action == "HOLD"
        assert "Mean Reversion" in result.reason

    def test_moderate_itm_holds_with_followup(self):
        """Moderate ITM (50-80% intrinsic) → HOLD with follow-up."""
        pos = MockPosition(
            strike_price=Decimal("150"),
            option_type="call",
            current_premium=10.0,
        )
        result = self.engine.evaluate(
            position=pos,
            is_itm=True,
            itm_pct=8.0,
            intrinsic_pct=0.65,
            intrinsic_value=6.5,
            time_value=3.5,
            current_price=162.0,
            current_premium=10.0,
            profit_pct=-3.0,
            days_to_exp=7,
        )
        assert result.action == "HOLD"
        assert result.has_follow_up is True
        assert result.follow_up_condition == "stock_bounces"

    def test_deep_itm_compresses(self):
        """Deep ITM (80%+ intrinsic, favorable ratio) → COMPRESS."""
        pos = MockPosition(
            strike_price=Decimal("150"),
            option_type="call",
            expiration_date=date.today() + timedelta(days=7),
            current_premium=15.0,
        )
        result = self.engine.evaluate(
            position=pos,
            is_itm=True,
            itm_pct=15.0,
            intrinsic_pct=0.90,
            intrinsic_value=13.5,
            time_value=1.5,
            current_price=172.5,
            current_premium=15.0,
            profit_pct=-5.0,
            days_to_exp=7,
            weekly_income=200.0,  # Good weekly income
        )
        # Should be COMPRESS or CLOSE depending on ratio
        assert result.action in ("COMPRESS", "CLOSE")

    def test_time_cushion_itm_rolls(self):
        """ITM with <=2 DTE → roll at same strike."""
        pos = MockPosition(
            strike_price=Decimal("150"),
            option_type="call",
            expiration_date=date.today() + timedelta(days=1),
        )
        result = self.engine.evaluate_time_cushion_itm(
            position=pos,
            is_itm=True,
            itm_pct=5.0,
            intrinsic_pct=0.40,
            current_price=157.5,
            current_premium=8.0,
        )
        assert result.action in ("ROLL", "ROLL_BIWEEKLY", "ROLL_MONTHLY")
        assert result.new_strike == 150.0  # Same strike - V5 philosophy
        assert result.new_expiration is not None

    def test_not_itm_returns_none(self):
        """Non-ITM position returns None (not this engine's job)."""
        pos = MockPosition(strike_price=Decimal("160"), option_type="call")
        result = self.engine.evaluate(
            position=pos,
            is_itm=False,
            itm_pct=-5.0,
            intrinsic_pct=0.0,
            intrinsic_value=0.0,
            time_value=2.0,
            current_price=152.0,
            current_premium=2.0,
            profit_pct=0.20,
            days_to_exp=7,
        )
        assert result is None


class TestUncoveredEngine:
    """Test Engine 1: Uncovered position detection."""

    def test_build_sell_notification_structure(self):
        """SELL notification has all required fields."""
        from app.modules.strategies.v5.engine_uncovered import UncoveredEngine

        ta_service = make_mock_ta_service(current_price=150.0, should_wait=False)
        db = Mock()
        engine = UncoveredEngine(db=db, ta_service=ta_service)

        position = {
            "account_name": "Neel's Brokerage",
            "symbol": "AAPL",
            "quantity": 200,
            "options_count": 2,
            "sold_count": 0,
            "uncovered": 2,
            "current_price": 150.0,
            "market_value": 30000.0,
        }

        with patch('app.modules.strategies.option_monitor.OptionChainFetcher') as MockFetcher:
            MockFetcher.return_value.get_option_quote.return_value = MockOptionQuote(bid=1.50)
            notif = engine._build_sell_notification(
                position=position,
                indicators=MockIndicators(current_price=150.0),
                strike_rec=MockStrikeRec(recommended_strike=155.0),
            )

        assert notif['action'] == 'SELL'
        assert notif['symbol'] == 'AAPL'
        assert notif['account_name'] == "Neel's Brokerage"
        assert notif['is_uncovered'] is True
        assert notif['contracts'] == 2
        assert notif['target_strike'] == 155.0
        assert 'source_strike' in notif
        assert 'source_expiration' in notif
        assert 'option_type' in notif

    def test_build_wait_notification_structure(self):
        """WAIT notification has all required fields."""
        from app.modules.strategies.v5.engine_uncovered import UncoveredEngine

        ta_service = make_mock_ta_service(current_price=150.0, should_wait=True)
        db = Mock()
        engine = UncoveredEngine(db=db, ta_service=ta_service)

        position = {
            "account_name": "Neel's Brokerage",
            "symbol": "AAPL",
            "quantity": 100,
            "options_count": 1,
            "sold_count": 0,
            "uncovered": 1,
            "current_price": 150.0,
            "market_value": 15000.0,
        }

        notif = engine._build_wait_notification(
            position=position,
            indicators=MockIndicators(current_price=150.0),
            strike_rec=MockStrikeRec(recommended_strike=155.0),
            next_friday=date.today() + timedelta(days=5),
            reason="RSI oversold"
        )

        assert notif['action'] == 'WAIT'
        assert notif['is_uncovered'] is True
        assert 'tactical_timing' in notif['philosophy']


class TestPutEngine:
    """Test Engine 2: Cash-secured put recommendations."""

    def test_score_put_opportunity_oversold(self):
        """Oversold stock scores higher."""
        from app.modules.strategies.v5.engine_puts import PutEngine

        engine = PutEngine(db=Mock(), ta_service=Mock())

        # Oversold
        indicators_oversold = MockIndicators(current_price=100.0, rsi_14=25.0, trend="oversold_bounce")
        score1 = engine._score_put_opportunity("AAPL", indicators_oversold, cost_basis=110.0)

        # Normal
        indicators_normal = MockIndicators(current_price=100.0, rsi_14=55.0, trend="neutral")
        score2 = engine._score_put_opportunity("AAPL", indicators_normal, cost_basis=90.0)

        assert score1 > score2

    def test_score_below_cost_basis_bonus(self):
        """Stock below cost basis gets bonus score."""
        from app.modules.strategies.v5.engine_puts import PutEngine

        engine = PutEngine(db=Mock(), ta_service=Mock())

        indicators = MockIndicators(current_price=95.0, rsi_14=45.0, trend="neutral")

        # Below cost basis
        score_below = engine._score_put_opportunity("AAPL", indicators, cost_basis=100.0)
        # Above cost basis
        score_above = engine._score_put_opportunity("AAPL", indicators, cost_basis=90.0)

        assert score_below > score_above


# ============================================================================
# 3. INTEGRATION TESTS - Full delegation chain
# ============================================================================

class TestCombinedEvaluator:
    """Test the _CombinedEvaluator that replaces V5PositionEvaluator.evaluate()."""

    def setup_method(self):
        self.ta_service = make_mock_ta_service(current_price=145.0)
        self.option_fetcher = make_mock_option_fetcher()

    def test_evaluator_accessible_via_facade(self):
        """V5PositionEvaluator facade has evaluate() method."""
        from app.modules.strategies.v5_position_evaluator import V5PositionEvaluator
        evaluator = V5PositionEvaluator(
            ta_service=self.ta_service,
            option_fetcher=self.option_fetcher,
            db=None
        )
        assert hasattr(evaluator, 'evaluate')
        assert callable(evaluator.evaluate)

    def test_evaluate_otm_position(self):
        """OTM position through evaluator → delegates to ProfitEngine."""
        from app.modules.strategies.v5_position_evaluator import V5PositionEvaluator
        evaluator = V5PositionEvaluator(
            ta_service=self.ta_service,
            option_fetcher=self.option_fetcher,
            db=None
        )
        pos = MockPosition(
            strike_price=Decimal("155"),
            option_type="call",
            original_premium=2.0,
            current_premium=1.50,
            premium_per_contract=1.50,
            expiration_date=date.today() + timedelta(days=7),
        )
        result = evaluator.evaluate(pos)
        assert result is not None
        assert result.action == "HOLD"  # OTM, low profit → hold

    def test_evaluate_high_profit_position(self):
        """High profit position → CLOSE (early profit capture)."""
        from app.modules.strategies.v5_position_evaluator import V5PositionEvaluator
        evaluator = V5PositionEvaluator(
            ta_service=self.ta_service,
            option_fetcher=self.option_fetcher,
            db=None
        )
        pos = MockPosition(
            strike_price=Decimal("155"),
            option_type="call",
            original_premium=2.0,
            current_premium=0.30,
            premium_per_contract=0.30,
            expiration_date=date.today() + timedelta(days=7),
        )
        result = evaluator.evaluate(pos)
        assert result is not None
        assert result.action == "CLOSE"

    def test_evaluate_near_expiry_otm(self):
        """Near expiry OTM → LET_EXPIRE or ROLL depending on profit."""
        from app.modules.strategies.v5_position_evaluator import V5PositionEvaluator
        evaluator = V5PositionEvaluator(
            ta_service=self.ta_service,
            option_fetcher=self.option_fetcher,
            db=None
        )
        pos = MockPosition(
            strike_price=Decimal("155"),
            option_type="call",
            original_premium=2.0,
            current_premium=1.80,
            premium_per_contract=1.80,
            expiration_date=date.today() + timedelta(days=1),
        )
        result = evaluator.evaluate(pos)
        assert result is not None
        assert result.action in ("LET_EXPIRE", "CLOSE", "ROLL")

    def test_evaluate_itm_position(self):
        """ITM position → delegates to UnderwaterEngine."""
        from app.modules.strategies.v5_position_evaluator import V5PositionEvaluator
        # Price above strike = ITM for call
        ta = make_mock_ta_service(current_price=160.0)
        evaluator = V5PositionEvaluator(
            ta_service=ta,
            option_fetcher=self.option_fetcher,
            db=None
        )
        pos = MockPosition(
            strike_price=Decimal("150"),
            option_type="call",
            original_premium=2.0,
            current_premium=11.0,
            premium_per_contract=11.0,
            expiration_date=date.today() + timedelta(days=7),
        )
        result = evaluator.evaluate(pos)
        assert result is not None
        # ITM call should get HOLD, COMPRESS, ROLL, or CLOSE
        assert result.action in ("HOLD", "COMPRESS", "ROLL", "CLOSE",
                                 "ROLL_BIWEEKLY", "ROLL_MONTHLY")


class TestOrchestratorFormatting:
    """Test orchestrator formatting methods match original behavior."""

    def _get_orchestrator_class(self):
        from app.modules.strategies.v5.orchestrator import V5Orchestrator
        return V5Orchestrator

    def test_format_action_display(self):
        """Action display formatting matches expected values."""
        V5Orchestrator = self._get_orchestrator_class()

        # Can't instantiate without DB, so test the method directly
        fmt = V5Orchestrator._format_action_display
        # It's an instance method, so we need a dummy self
        dummy = type('Dummy', (), {})()

        assert fmt(dummy, 'HOLD') == 'HOLD'
        assert fmt(dummy, 'CLOSE') == 'CLOSE'
        assert fmt(dummy, 'ROLL') == 'ROLL'
        assert fmt(dummy, 'COMPRESS') == 'COMPRESS'
        assert fmt(dummy, 'LET_EXPIRE') == 'LET EXPIRE'
        assert fmt(dummy, 'ROLL_BIWEEKLY') == 'ROLL (2wk)'
        assert fmt(dummy, 'ROLL_MONTHLY') == 'ROLL (4wk)'

    def test_format_title_roll_biweekly(self):
        """ROLL_BIWEEKLY title format matches V5 spec."""
        V5Orchestrator = self._get_orchestrator_class()
        dummy = type('Dummy', (), {})()

        title = V5Orchestrator._format_title(
            dummy,
            action='ROLL_BIWEEKLY',
            symbol='HOOD',
            contracts=1,
            option_type='put',
            source_strike=45.0,
            target_strike=45.0,
            target_expiration=date(2026, 2, 14),
            biweekly_credit=0.30,
        )
        assert "ROLL (2wk)" in title
        assert "HOOD" in title
        assert "$45" in title
        assert "Credit $0.30" in title

    def test_format_title_roll_monthly(self):
        """ROLL_MONTHLY title format."""
        V5Orchestrator = self._get_orchestrator_class()
        dummy = type('Dummy', (), {})()

        title = V5Orchestrator._format_title(
            dummy,
            action='ROLL_MONTHLY',
            symbol='HOOD',
            contracts=1,
            option_type='put',
            source_strike=45.0,
            target_strike=45.0,
            target_expiration=date(2026, 2, 28),
            monthly_credit=0.85,
        )
        assert "ROLL (4wk)" in title
        assert "Credit $0.85" in title

    def test_format_title_standard_roll(self):
        """Standard ROLL title format."""
        V5Orchestrator = self._get_orchestrator_class()
        dummy = type('Dummy', (), {})()

        title = V5Orchestrator._format_title(
            dummy,
            action='ROLL',
            symbol='AAPL',
            contracts=2,
            option_type='call',
            source_strike=150.0,
            source_expiration=date(2026, 2, 7),
            target_strike=155.0,
            target_expiration=date(2026, 2, 14),
            total_premium=200.0,
        )
        assert "Roll" in title
        assert "AAPL" in title
        assert "$150" in title
        assert "$155" in title
        assert "Earn $200" in title


class TestResultToNotification:
    """Test that V5EvaluationResult converts to notification dict correctly."""

    def test_result_to_notification_has_all_fields(self):
        """Notification dict has all required fields for save_v5_to_history."""
        from app.modules.strategies.v5.base import V5EvaluationResult
        from app.modules.strategies.v5.orchestrator import V5Orchestrator

        result = V5EvaluationResult(
            action='ROLL',
            position_id='123',
            symbol='AAPL',
            reason='Test reason',
            reason_short='Test short',
            philosophy_applied='test_philosophy',
            new_strike=155.0,
            new_expiration=date.today() + timedelta(days=7),
            net_cost=-100.0,
            stuck_category='STUCK',
            iv_category='medium_iv',
            weekly_credit=0.50,
            biweekly_credit=1.00,
            monthly_credit=2.00,
            has_follow_up=True,
            follow_up_condition='stock_bounces',
            follow_up_threshold=0.02,
            follow_up_action='CLOSE',
            intrinsic_pct=0.30,
            time_value=1.50,
        )

        pos = MockPosition(
            strike_price=Decimal("150"),
            option_type="call",
            expiration_date=date.today() + timedelta(days=2),
            contracts_sold=2,
            account_name="Neel's Brokerage",
        )

        # Call _result_to_notification directly
        dummy = type('Dummy', (), {
            '_format_title': lambda self, **kw: "Test title",
            '_format_action_display': lambda self, a: a,
        })()

        notif = V5Orchestrator._result_to_notification(dummy, result, pos)

        # Check all required fields for save_v5_to_history
        assert notif['id'] == '123'
        assert notif['symbol'] == 'AAPL'
        assert notif['account_name'] == "Neel's Brokerage"
        assert notif['action'] == 'ROLL'
        assert notif['source_strike'] is not None
        assert notif['source_expiration'] is not None
        assert notif['option_type'] == 'call'
        assert notif['contracts'] == 2
        assert notif['target_strike'] == 155.0
        assert notif['net_cost'] == -100.0
        # V5 fields
        assert notif['stuck_category'] == 'STUCK'
        assert notif['iv_category'] == 'medium_iv'
        assert notif['weekly_credit'] == 0.50
        assert notif['has_follow_up'] is True
        assert notif['follow_up_condition'] == 'stock_bounces'


class TestNotificationSchemaCompatibility:
    """Verify engine outputs pass the notification schema validator."""

    def test_uncovered_sell_passes_schema(self):
        """Uncovered SELL notification passes validation."""
        from app.modules.strategies.notification_schema import validate_notification_dict
        from app.modules.strategies.v5.engine_uncovered import UncoveredEngine

        ta_service = make_mock_ta_service(current_price=150.0)
        engine = UncoveredEngine(db=Mock(), ta_service=ta_service)

        position = {
            "account_name": "Neel's Brokerage",
            "symbol": "AAPL",
            "quantity": 200,
            "options_count": 2,
            "sold_count": 0,
            "uncovered": 2,
            "current_price": 150.0,
            "market_value": 30000.0,
        }

        with patch('app.modules.strategies.option_monitor.OptionChainFetcher') as MockFetcher:
            MockFetcher.return_value.get_option_quote.return_value = MockOptionQuote(bid=1.50)
            notif = engine._build_sell_notification(
                position=position,
                indicators=MockIndicators(current_price=150.0),
                strike_rec=MockStrikeRec(recommended_strike=155.0),
            )

        errors = validate_notification_dict(notif)
        assert errors == [], f"Schema validation errors: {errors}"

    def test_put_recommendation_passes_schema(self):
        """Cash-secured put notification passes validation."""
        from app.modules.strategies.notification_schema import validate_notification_dict
        from app.modules.strategies.v5.engine_puts import PutEngine

        engine = PutEngine(db=Mock(), ta_service=Mock())
        notif = engine._build_put_recommendation(
            account_name="Neel's Brokerage",
            available_cash=50000.0,
            opportunity={
                'symbol': 'AAPL',
                'strike': 140.0,
                'indicators': MockIndicators(current_price=150.0),
                'score': 3.0,
                'required_cash': 14000.0,
                'premium_estimate': 75.0,
            }
        )

        errors = validate_notification_dict(notif)
        assert errors == [], f"Schema validation errors: {errors}"
