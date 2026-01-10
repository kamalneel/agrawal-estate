"""
Strategy implementations for recommendations.
"""

from app.modules.strategies.strategies.sell_unsold_contracts import SellUnsoldContractsStrategy
from app.modules.strategies.strategies.early_roll_opportunity import EarlyRollOpportunityStrategy
from app.modules.strategies.strategies.premium_adjustment import PremiumAdjustmentStrategy
from app.modules.strategies.strategies.diversification import DiversificationStrategy
from app.modules.strategies.strategies.bull_put_spread import BullPutSpreadStrategy

# New strategies with technical analysis
from app.modules.strategies.strategies.close_early_opportunity import CloseEarlyOpportunityStrategy
from app.modules.strategies.strategies.roll_options import RollOptionsStrategy
from app.modules.strategies.strategies.new_covered_call import NewCoveredCallStrategy
from app.modules.strategies.strategies.mega_cap_bull_put import MegaCapBullPutStrategy

# Earnings awareness strategy
from app.modules.strategies.strategies.earnings_alert import EarningsAlertStrategy

# Triple Witching handler (V2)
from app.modules.strategies.strategies.triple_witching_handler import TripleWitchingStrategy

# V3.4: Cash-Secured Put Strategy
from app.modules.strategies.strategies.cash_secured_put import CashSecuredPutStrategy

# Strategy registry - maps strategy_type to strategy class
STRATEGY_REGISTRY = {
    # Original strategies
    "sell_unsold_contracts": SellUnsoldContractsStrategy,
    "early_roll_opportunity": EarlyRollOpportunityStrategy,
    "adjust_premium_expectation": PremiumAdjustmentStrategy,
    "diversify_holdings": DiversificationStrategy,
    "bull_put_spread": BullPutSpreadStrategy,
    # New strategies with technical analysis
    "close_early_opportunity": CloseEarlyOpportunityStrategy,
    "roll_options": RollOptionsStrategy,
    "new_covered_call": NewCoveredCallStrategy,
    "mega_cap_bull_put": MegaCapBullPutStrategy,
    # Earnings awareness
    "earnings_alert": EarningsAlertStrategy,
    # Triple Witching (V2)
    "triple_witching": TripleWitchingStrategy,
    # V3.4: Cash-Secured Put (income generation)
    "cash_secured_put": CashSecuredPutStrategy,
}

__all__ = [
    "SellUnsoldContractsStrategy",
    "EarlyRollOpportunityStrategy",
    "PremiumAdjustmentStrategy",
    "DiversificationStrategy",
    "BullPutSpreadStrategy",
    "CloseEarlyOpportunityStrategy",
    "RollOptionsStrategy",
    "NewCoveredCallStrategy",
    "MegaCapBullPutStrategy",
    "EarningsAlertStrategy",
    "TripleWitchingStrategy",
    "CashSecuredPutStrategy",
    "STRATEGY_REGISTRY",
]

