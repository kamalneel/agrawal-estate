"""
Sell Unsold Contracts Strategy

ALGORITHM VERSION AWARE:
- V1/V2: Same logic, uses config for min_weekly_income parameter

Generates recommendations for holdings with unsold contracts that could generate income.
Includes Delta 10 strike price recommendations based on technical analysis.
"""

from typing import List, Dict, Any
from datetime import date, timedelta
from sqlalchemy import text
import logging

from app.modules.strategies.strategy_base import BaseStrategy, StrategyConfig
from app.modules.strategies.recommendations import StrategyRecommendation
from app.modules.strategies.services import get_sold_options_by_account
from app.modules.strategies.models import OptionPremiumSetting
from app.modules.strategies.technical_analysis import get_technical_analysis_service
from app.modules.strategies.algorithm_config import get_config, ALGORITHM_VERSION

logger = logging.getLogger(__name__)

# Load config
_config = get_config()


def _get_next_friday() -> date:
    """Get the date of the next Friday."""
    today = date.today()
    days_ahead = 4 - today.weekday()  # Friday = 4
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


class SellUnsoldContractsStrategy(BaseStrategy):
    """Strategy for identifying unsold contracts that could generate income."""
    
    strategy_type = "sell_unsold_contracts"
    name = "Sell Unsold Contracts"
    description = f"[{ALGORITHM_VERSION.upper()}] Generates recommendations for holdings with unsold contracts"
    category = "income_generation"
    default_parameters = {
        "min_weekly_income": _config.get("min_weekly_income", 50.0)
    }
    
    def generate_recommendations(self, params: Dict[str, Any]) -> List[StrategyRecommendation]:
        """Generate recommendations for unsold contracts."""
        recommendations = []
        
        min_weekly_income = self.get_parameter("min_weekly_income", 50.0)
        default_premium = params.get("default_premium", 60)
        symbol_premiums = params.get("symbol_premiums", {})
        
        # Load premium settings
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
        
        # Get holdings and sold options
        result = self.db.execute(text("""
            SELECT 
                ia.account_name,
                ih.symbol,
                ih.quantity,
                ih.current_price,
                ih.market_value,
                ih.description
            FROM investment_holdings ih
            JOIN investment_accounts ia ON ih.account_id = ia.account_id AND ih.source = ia.source
            WHERE ih.quantity >= 100
            AND ih.symbol NOT LIKE '%CASH%'
            AND ih.symbol NOT LIKE '%MONEY%'
            AND ih.symbol NOT LIKE '%FDRXX%'
            AND ia.account_type IN ('brokerage', 'retirement', 'ira', 'roth_ira')
            ORDER BY ih.market_value DESC
        """))
        
        # Get sold options by account
        sold_by_account = get_sold_options_by_account(self.db)
        
        # Group by (symbol, account) - create separate recommendations per account
        account_symbol_data = {}
        for row in result:
            account_name, symbol, qty, price, value, description = row
            qty = float(qty) if qty else 0
            price = float(price) if price else 0
            
            options_count = int(qty // 100)
            
            # Key by (account, symbol) tuple
            key = (account_name, symbol)
            
            if key not in account_symbol_data:
                # Count sold for this specific account
                account_sold = 0
                if account_name in sold_by_account:
                    account_sold_opts = sold_by_account[account_name].get("by_symbol", {}).get(symbol, [])
                    account_sold = sum(opt["contracts_sold"] for opt in account_sold_opts)
                
                account_symbol_data[key] = {
                    "symbol": symbol,
                    "account_name": account_name,
                    "description": description or symbol,
                    "total_options": options_count,
                    "total_sold": account_sold,
                }
            else:
                # Same account might have multiple lots of same symbol
                account_symbol_data[key]["total_options"] += options_count
        
        # Get technical analysis service for strike recommendations
        ta_service = get_technical_analysis_service()
        
        # Generate recommendations for each account/symbol with unsold contracts
        for (account_name, symbol), data in account_symbol_data.items():
            unsold = data["total_options"] - data["total_sold"]
            
            if unsold > 0:
                premium = get_premium(symbol)
                weekly_income = unsold * premium
                
                # Skip if below minimum income threshold
                if weekly_income < min_weekly_income:
                    continue
                
                yearly_income = weekly_income * 50  # 50 weeks/year
                
                # Calculate Delta 10 strike price
                strike_recommendation = ta_service.recommend_strike_price(
                    symbol=symbol,
                    option_type="call",
                    expiration_weeks=1,
                    probability_target=0.90  # Delta 10 = 90% OTM
                )
                
                # Get current price for context
                indicators = ta_service.get_technical_indicators(symbol)
                current_price = indicators.current_price if indicators else None
                
                # Format strike info
                if strike_recommendation:
                    strike = strike_recommendation.recommended_strike
                    strike_str = f"${strike:.0f}" if strike >= 100 else f"${strike:.2f}"
                    strike_rationale = strike_recommendation.rationale
                    strike_source = getattr(strike_recommendation, 'source', 'unknown')
                else:
                    strike = None
                    strike_str = "delta 10"
                    strike_rationale = "Strike calculation unavailable - use Robinhood's 90% probability strike"
                    strike_source = "unavailable"
                
                # Determine priority based on potential income
                if yearly_income > 10000:
                    priority = "high"
                elif yearly_income > 5000:
                    priority = "medium"
                else:
                    priority = "low"
                
                # Build context with actual numbers
                next_friday = _get_next_friday()
                exp_str = next_friday.strftime('%b %d')
                
                # Title includes strike, expiration, and current stock price
                if current_price:
                    title = f"Sell {unsold} {symbol} call(s) at {strike_str} for {exp_str} · Stock ${current_price:.0f}"
                else:
                    title = f"Sell {unsold} {symbol} call(s) at {strike_str} for {exp_str}"
                
                description = (
                    f"You have {unsold} unsold contract(s) for {symbol} that could generate "
                    f"${weekly_income:.0f}/week (${yearly_income:.0f}/year) in additional income."
                )
                
                rationale_parts = [
                    f"Delta 10 strike at {strike_str} = 90% probability of staying OTM",
                    strike_rationale
                ]
                if indicators and indicators.rsi_14:
                    rsi_status = "overbought" if indicators.rsi_14 > 70 else "oversold" if indicators.rsi_14 < 30 else "neutral"
                    rationale_parts.append(f"RSI: {indicators.rsi_14:.0f} ({rsi_status})")
                
                # Create unique ID per account
                account_slug = (account_name or "unknown").replace(" ", "_").replace("'", "")
                
                recommendation = StrategyRecommendation(
                    id=f"sell_unsold_{symbol}_{date.today().isoformat()}_{account_slug}",
                    type=self.strategy_type,
                    category=self.category,
                    priority=priority,
                    title=title,
                    description=description,
                    rationale=". ".join(rationale_parts),
                    action=f"Sell {unsold} {symbol} covered call(s) at {strike_str} strike expiring {exp_str}",
                    action_type="sell",
                    potential_income=weekly_income,
                    potential_risk="low",
                    time_horizon="this_week",
                    symbol=symbol,
                    account_name=account_name,
                    context={
                        "symbol": symbol,
                        "account_name": account_name,
                        "unsold_contracts": unsold,
                        "total_options": data["total_options"],
                        "sold_contracts": data["total_sold"],
                        "premium_per_contract": premium,
                        "weekly_income": weekly_income,
                        "yearly_income": yearly_income,
                        "strike_price": strike,
                        "current_price": current_price,
                        "strike_rationale": strike_rationale,
                        "strike_source": strike_source,  # "options_chain" = live delta, "fallback_estimate" = calculated
                        "option_type": "call",
                        "expiration_date": next_friday.isoformat(),
                        "technical_analysis": {
                            "rsi": indicators.rsi_14 if indicators else None,
                            "trend": indicators.trend if indicators else None,
                            "weekly_volatility": indicators.weekly_volatility if indicators else None,
                        } if indicators else None
                    }
                )
                recommendations.append(recommendation)
        
        return recommendations

