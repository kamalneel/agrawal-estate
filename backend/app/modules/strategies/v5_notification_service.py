"""
V5 Notification Service - Thin facade over v5/orchestrator.py

All logic has been decomposed into:
- v5/engine_uncovered.py  (Engine 1: uncovered positions)
- v5/engine_puts.py       (Engine 2: cash-secured puts)
- v5/engine_profit.py     (Engine 3: profit-taking / OTM)
- v5/engine_underwater.py (Engine 4: ITM / stuck / life-support)
- v5/orchestrator.py      (coordination, formatting, persistence)

This file re-exports the public API so that scheduler.py, router.py,
and strategy_service.py continue to work with zero changes.
"""

import logging
from sqlalchemy.orm import Session

# Re-export everything consumers need
from app.modules.strategies.v5.orchestrator import V5Orchestrator, V5_VERSION_TAG
from app.modules.strategies.v5.base import V5EvaluationResult

logger = logging.getLogger(__name__)

# Log on module load to verify which notification service is being used
logger.info(f"[VERSION] V5NotificationService module loaded (facade) - version tag: {V5_VERSION_TAG}")


class V5NotificationService(V5Orchestrator):
    """
    V5 Notification Service - facade that delegates to V5Orchestrator.

    Preserves the full public API:
    - get_all_v5_notifications()
    - format_telegram_message()
    - save_v5_to_history()
    - get_uncovered_positions()
    - get_active_follow_up_conditions()
    - evaluator.evaluate()  (via _CombinedEvaluator)
    """

    def __init__(self, db: Session):
        super().__init__(db)

    # === Methods delegated to engines but kept for backward compat ===

    def evaluate_and_notify(self, positions, cost_basis_map=None, weekly_income_map=None):
        """Delegate to internal _evaluate_and_notify."""
        return self._evaluate_and_notify(positions, cost_basis_map, weekly_income_map)

    def get_uncovered_positions(self):
        """Delegate to uncovered engine."""
        return self.uncovered_engine.get_uncovered_positions()


def get_v5_notification_service(db: Session) -> V5NotificationService:
    """Factory function to get V5 notification service."""
    return V5NotificationService(db)
