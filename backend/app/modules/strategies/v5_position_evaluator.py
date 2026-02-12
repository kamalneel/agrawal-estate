"""
V5 Position Evaluator - Thin facade over v5/ engines.

All logic has been decomposed into:
- v5/base.py              (V5EvaluationResult, shared helpers, config)
- v5/engine_profit.py     (Engine 3: profit-taking / OTM)
- v5/engine_underwater.py (Engine 4: ITM / stuck / life-support)

This file re-exports the public API so that router.py and other
consumers continue to work with zero changes.
"""

import logging
from typing import Optional

from app.modules.strategies.v5.base import (
    V5EvaluationResult,
    LIFE_SUPPORT_THRESHOLDS,
    get_v5_config,
    calculate_intrinsic_time_value,
    estimate_current_premium,
    get_iv_category,
    get_stuck_category,
    calculate_escape_strike,
    estimate_roll_credits,
)
from app.modules.strategies.v5.engine_profit import ProfitEngine
from app.modules.strategies.v5.engine_underwater import UnderwaterEngine
from app.modules.strategies.v5.orchestrator import _CombinedEvaluator

logger = logging.getLogger(__name__)


class V5PositionEvaluator:
    """
    V5 Position Evaluator - facade that delegates to ProfitEngine + UnderwaterEngine.

    Preserves the public API:
    - evaluate(position, cost_basis, weekly_income) -> Optional[V5EvaluationResult]
    """

    def __init__(self, ta_service=None, option_fetcher=None, db=None):
        """Initialize V5 evaluator."""
        if ta_service is None:
            from app.modules.strategies.technical_analysis import get_technical_analysis_service
            ta_service = get_technical_analysis_service()

        if option_fetcher is None:
            from app.modules.strategies.option_monitor import OptionChainFetcher
            option_fetcher = OptionChainFetcher()

        self.ta_service = ta_service
        self.option_fetcher = option_fetcher
        self.db = db
        self.config = get_v5_config()

        # Create engine instances
        self._profit_engine = ProfitEngine(ta_service=ta_service, option_fetcher=option_fetcher)
        self._underwater_engine = UnderwaterEngine(
            ta_service=ta_service, option_fetcher=option_fetcher, db=db
        )

        # Create combined evaluator
        self._evaluator = _CombinedEvaluator(
            ta_service=ta_service,
            option_fetcher=option_fetcher,
            profit_engine=self._profit_engine,
            underwater_engine=self._underwater_engine,
            db=db
        )

    def evaluate(
        self,
        position,
        cost_basis: Optional[float] = None,
        weekly_income: Optional[float] = None
    ) -> Optional[V5EvaluationResult]:
        """
        Main V5 evaluation logic - delegates to _CombinedEvaluator.

        Same interface as before refactoring.
        """
        return self._evaluator.evaluate(position, cost_basis, weekly_income)


def get_v5_evaluator(ta_service=None, option_fetcher=None, db=None) -> V5PositionEvaluator:
    """Factory function to get V5 evaluator instance."""
    return V5PositionEvaluator(ta_service, option_fetcher, db)
