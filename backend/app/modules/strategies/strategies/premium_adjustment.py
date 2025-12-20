"""
Premium Adjustment Strategy

Suggests updating premium settings when actual premiums differ significantly from configured values.
"""

from typing import List, Dict, Any
from datetime import date
import logging

from app.modules.strategies.strategy_base import BaseStrategy, StrategyConfig
from app.modules.strategies.recommendations import StrategyRecommendation
from app.modules.strategies.services import calculate_4_week_average_premiums
from app.modules.strategies.models import OptionPremiumSetting

logger = logging.getLogger(__name__)


class PremiumAdjustmentStrategy(BaseStrategy):
    """Strategy for identifying premium setting adjustments needed."""
    
    strategy_type = "adjust_premium_expectation"
    name = "Premium Setting Adjustments"
    description = "Suggests updating premium settings when actual premiums differ significantly from configured values"
    category = "optimization"
    default_parameters = {
        "difference_threshold_percent": 15.0
    }
    
    def generate_recommendations(self, params: Dict[str, Any]) -> List[StrategyRecommendation]:
        """Check if premium settings need adjustment based on actual data."""
        recommendations = []
        
        try:
            difference_threshold = self.get_parameter("difference_threshold_percent", 15.0)
            logger.info(f"Premium Adjustment: Checking with threshold {difference_threshold}%")
            
            # Calculate 4-week averages
            averages = calculate_4_week_average_premiums(self.db, weeks=4)
            logger.info(f"Premium Adjustment: Calculated averages for {len(averages)} symbols")
            
            # Get current settings
            settings = self.db.query(OptionPremiumSetting).all()
            settings_dict = {s.symbol: s for s in settings}
            logger.info(f"Premium Adjustment: Found {len(settings)} premium settings")
        except Exception as e:
            logger.error(f"Premium Adjustment: Error analyzing premium settings: {e}", exc_info=True)
            return recommendations
        
        for symbol, avg_data in averages.items():
            calculated_premium = avg_data["premium_per_contract"]
            transaction_count = avg_data["transaction_count"]
            
            # Skip if not enough data
            if transaction_count < 3:
                continue
            
            setting = settings_dict.get(symbol)
            
            if setting:
                current_premium = float(setting.premium_per_contract)
                difference = calculated_premium - current_premium
                difference_percent = (difference / current_premium * 100) if current_premium > 0 else 0
                
                # Only recommend if difference is significant
                if abs(difference_percent) > difference_threshold and not setting.manual_override:
                    priority = "high" if abs(difference_percent) > 30 else "medium"
                    
                    recommendation = StrategyRecommendation(
                        id=f"adjust_premium_{symbol}_{date.today().isoformat()}",
                        type=self.strategy_type,
                        category=self.category,
                        priority=priority,
                        title=f"Update {symbol} premium setting - actual is {difference_percent:+.0f}% different",
                        description=(
                            f"Your {symbol} premium setting is ${current_premium:.0f}/contract, but "
                            f"4-week average shows ${calculated_premium:.0f}/contract "
                            f"({difference_percent:+.0f}% difference)."
                        ),
                        rationale=(
                            f"Recent market activity shows {symbol} premiums are {difference_percent:+.0f}% "
                            f"different from your setting. Updating will improve income projections accuracy."
                        ),
                        action=f"Update {symbol} premium setting from ${current_premium:.0f} to ${calculated_premium:.0f}",
                        action_type="adjust",
                        potential_income=None,
                        potential_risk="none",
                        time_horizon="immediate",
                        context={
                            "symbol": symbol,
                            "current_setting": current_premium,
                            "calculated_average": calculated_premium,
                            "difference": difference,
                            "difference_percent": difference_percent,
                            "transaction_count": transaction_count,
                            "date_range": avg_data["date_range"]
                        }
                    )
                    recommendations.append(recommendation)
        
        return recommendations

