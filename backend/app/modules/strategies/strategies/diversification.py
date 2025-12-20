"""
Diversification Strategy

Alerts when portfolio is too concentrated in a single symbol.
"""

from typing import List, Dict, Any
from datetime import date
from sqlalchemy import text

from app.modules.strategies.strategy_base import BaseStrategy, StrategyConfig
from app.modules.strategies.recommendations import StrategyRecommendation
from app.modules.strategies.services import get_sold_options_by_account


class DiversificationStrategy(BaseStrategy):
    """Strategy for identifying concentration risk."""
    
    strategy_type = "diversify_holdings"
    name = "Diversification Recommendations"
    description = "Alerts when portfolio is too concentrated in a single symbol"
    category = "risk_management"
    default_parameters = {
        "concentration_threshold_percent": 35.0
    }
    
    def generate_recommendations(self, params: Dict[str, Any]) -> List[StrategyRecommendation]:
        """Check for concentration risk in options portfolio."""
        recommendations = []
        
        concentration_threshold = self.get_parameter("concentration_threshold_percent", 35.0)
        default_premium = params.get("default_premium", 60)
        symbol_premiums = params.get("symbol_premiums", {})
        
        # Load premium settings
        from app.modules.strategies.models import OptionPremiumSetting
        db_premiums = {}
        db_settings = self.db.query(OptionPremiumSetting).all()
        for setting in db_settings:
            db_premiums[setting.symbol] = float(setting.premium_per_contract)
        
        default_symbol_premiums = {
            "AAPL": 50, "TSLA": 150, "NVDA": 100, "IBIT": 40,
            "AVGO": 80, "COIN": 120, "PLTR": 60, "META": 90,
            "MSFT": 60, "MU": 70, "TSM": 50, "MSTR": 200,
        }
        
        effective_premiums = {**default_symbol_premiums, **db_premiums, **symbol_premiums}
        
        def get_premium(symbol):
            return effective_premiums.get(symbol, default_premium)
        
        # Get holdings
        result = self.db.execute(text("""
            SELECT 
                ih.symbol,
                ih.quantity
            FROM investment_holdings ih
            JOIN investment_accounts ia ON ih.account_id = ia.account_id AND ih.source = ia.source
            WHERE ih.quantity >= 100
            AND ih.symbol NOT LIKE '%CASH%'
            AND ih.symbol NOT LIKE '%MONEY%'
            AND ih.symbol NOT LIKE '%FDRXX%'
            AND ia.account_type IN ('brokerage', 'retirement', 'ira', 'roth_ira')
        """))
        
        # Calculate income by symbol
        symbol_income = {}
        total_income = 0
        
        for row in result:
            symbol, qty = row
            qty = float(qty) if qty else 0
            options_count = int(qty // 100)
            premium = get_premium(symbol)
            weekly_income = options_count * premium
            
            symbol_income[symbol] = weekly_income
            total_income += weekly_income
        
        if total_income == 0:
            return recommendations
        
        # Find concentration
        sorted_symbols = sorted(symbol_income.items(), key=lambda x: x[1], reverse=True)
        top_symbol, top_income = sorted_symbols[0]
        concentration_percent = (top_income / total_income * 100) if total_income > 0 else 0
        
        # Recommend diversification if above threshold
        if concentration_percent > concentration_threshold and len(sorted_symbols) > 1:
            # Find symbols with unsold contracts
            sold_by_account = get_sold_options_by_account(self.db)
            alternative_symbols = []
            
            for symbol, income in sorted_symbols[1:6]:  # Top 5 alternatives
                # Check if has unsold contracts
                result = self.db.execute(text("""
                    SELECT 
                        ia.account_name,
                        ih.symbol,
                        ih.quantity
                    FROM investment_holdings ih
                    JOIN investment_accounts ia ON ih.account_id = ia.account_id AND ih.source = ia.source
                    WHERE ih.symbol = :symbol
                    AND ih.quantity >= 100
                    AND ia.account_type IN ('brokerage', 'retirement', 'ira', 'roth_ira')
                """), {"symbol": symbol})
                
                for row in result:
                    account_name, sym, qty = row
                    qty = float(qty) if qty else 0
                    options_count = int(qty // 100)
                    
                    # Check sold
                    account_sold = 0
                    if account_name in sold_by_account:
                        account_sold_opts = sold_by_account[account_name].get("by_symbol", {}).get(symbol, [])
                        account_sold = sum(opt["contracts_sold"] for opt in account_sold_opts)
                    
                    if options_count > account_sold:
                        if symbol not in alternative_symbols:
                            alternative_symbols.append(symbol)
                        break
            
            if alternative_symbols:
                recommendation = StrategyRecommendation(
                    id=f"diversify_concentration_{date.today().isoformat()}",
                    type=self.strategy_type,
                    category=self.category,
                    priority="medium",
                    title=f"Consider diversifying - {concentration_percent:.0f}% of income from {top_symbol}",
                    description=(
                        f"{top_symbol} represents {concentration_percent:.0f}% of your potential options income. "
                        f"Consider selling options on other holdings to reduce concentration risk."
                    ),
                    rationale=(
                        f"Diversification reduces risk from single-stock volatility. You have "
                        f"{len(alternative_symbols)} other symbol(s) with unsold contracts available: "
                        f"{', '.join(alternative_symbols[:3])}."
                    ),
                    action=f"Review and sell options on {', '.join(alternative_symbols[:2])} to diversify",
                    action_type="review",
                    potential_income=None,
                    potential_risk="medium",  # Risk being mitigated
                    time_horizon="this_month",
                    context={
                        "concentrated_symbol": top_symbol,
                        "concentration_percent": concentration_percent,
                        "alternative_symbols": alternative_symbols,
                        "total_symbols": len(sorted_symbols),
                        "top_5_symbols": [s[0] for s in sorted_symbols[:5]]
                    }
                )
                recommendations.append(recommendation)
        
        return recommendations

