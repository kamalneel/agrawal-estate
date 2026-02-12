"""
V5 Notification Engine - Decomposed into 4 independent engines.

Public API:
- V5EvaluationResult: Shared result dataclass
- V5Orchestrator: Main orchestrator that calls all engines
- UncoveredEngine: Engine 1 - uncovered position detection
- PutEngine: Engine 2 - cash-secured put recommendations
- ProfitEngine: Engine 3 - OTM profit-taking evaluation
- UnderwaterEngine: Engine 4 - ITM/stuck/life-support/drowning
"""

from app.modules.strategies.v5.base import V5EvaluationResult, LIFE_SUPPORT_THRESHOLDS

__all__ = [
    'V5EvaluationResult',
    'LIFE_SUPPORT_THRESHOLDS',
]
