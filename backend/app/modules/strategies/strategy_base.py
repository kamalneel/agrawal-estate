"""
Base Strategy Pattern for Recommendations

Each recommendation type is a strategy that can be enabled/disabled and configured.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel

from app.modules.strategies.recommendations import StrategyRecommendation


class StrategyConfig(BaseModel):
    """Configuration for a strategy."""
    strategy_type: str
    name: str
    description: str
    category: str
    enabled: bool = True
    notification_enabled: bool = True
    notification_priority_threshold: str = "high"
    parameters: Dict[str, Any] = {}


class BaseStrategy(ABC):
    """Base class for all recommendation strategies."""
    
    def __init__(self, db, config: StrategyConfig):
        self.db = db
        self.config = config
    
    @property
    @abstractmethod
    def strategy_type(self) -> str:
        """Unique identifier for this strategy."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Display name for this strategy."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what this strategy does."""
        pass
    
    @property
    @abstractmethod
    def category(self) -> str:
        """Category: income_generation, optimization, risk_management."""
        pass
    
    @property
    @abstractmethod
    def default_parameters(self) -> Dict[str, Any]:
        """Default parameters for this strategy."""
        pass
    
    @abstractmethod
    def generate_recommendations(
        self,
        params: Dict[str, Any]
    ) -> List[StrategyRecommendation]:
        """
        Generate recommendations for this strategy.
        
        Args:
            params: Global parameters (like default_premium, etc.)
        
        Returns:
            List of recommendations
        """
        pass
    
    def get_parameter(self, key: str, default: Any = None) -> Any:
        """Get a parameter value, falling back to default."""
        return self.config.parameters.get(key, self.default_parameters.get(key, default))
    
    def should_notify(self, recommendation: StrategyRecommendation) -> bool:
        """Check if this recommendation should trigger a notification."""
        if not self.config.notification_enabled:
            return False
        
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        rec_priority = priority_order.get(recommendation.priority, 99)
        threshold_priority = priority_order.get(self.config.notification_priority_threshold, 99)
        
        return rec_priority <= threshold_priority



