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
from app.modules.strategies.option_monitor import OptionChainFetcher

logger = logging.getLogger(__name__)

# Global option chain fetcher for real-time premiums
_option_chain_fetcher = None

def _get_option_chain_fetcher():
    """Get or create the global option chain fetcher."""
    global _option_chain_fetcher
    if _option_chain_fetcher is None:
        _option_chain_fetcher = OptionChainFetcher()
    return _option_chain_fetcher

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
                # Only count CALLS - puts don't require share backing (they're cash-secured)
                account_sold = 0
                if account_name in sold_by_account:
                    account_sold_opts = sold_by_account[account_name].get("by_symbol", {}).get(symbol, [])
                    account_sold = sum(
                        opt["contracts_sold"] for opt in account_sold_opts
                        if opt.get("option_type", "").lower() == "call"
                    )
                
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
        
        # Get option chain fetcher for real-time premiums
        option_fetcher = _get_option_chain_fetcher()
        
        # Generate recommendations for each account/symbol with unsold contracts
        for (account_name, symbol), data in account_symbol_data.items():
            unsold = data["total_options"] - data["total_sold"]
            
            if unsold > 0:
                logger.info(f"[SELL_DEBUG] Processing {symbol} with {unsold} unsold contracts")
                
                # Calculate Delta 10 strike price FIRST (needed for premium lookup)
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
                    
                    # Calculate actual % OTM for logging
                    pct_otm = ((strike / current_price) - 1) * 100 if current_price else 0
                    logger.info(f"[SELL_DEBUG] {symbol}: FINAL STRIKE=${strike:.2f} ({pct_otm:.1f}% OTM), source={strike_source}, current_price=${current_price:.2f}")
                    logger.info(f"[SELL_DEBUG] {symbol}: rationale={strike_rationale[:100]}...")
                else:
                    strike = None
                    strike_str = "delta 10"
                    strike_rationale = "Strike calculation unavailable - use Robinhood's 90% probability strike"
                    strike_source = "unavailable"
                    logger.warning(f"[SELL_DEBUG] {symbol}: NO STRIKE RECOMMENDATION - using fallback text")
                
                # Build context with actual numbers
                next_friday = _get_next_friday()
                exp_str = next_friday.strftime('%b %d')
                
                # ================================================================
                # GET REAL-TIME PREMIUM FROM OPTIONS CHAIN
                # ================================================================
                real_premium_per_contract = None
                premium_source = "estimated"
                
                if strike:
                    try:
                        logger.info(f"[SELL_DEBUG] {symbol}: Fetching premium for strike=${strike}, expiration={next_friday}")
                        option_quote = option_fetcher.get_option_quote(
                            symbol=symbol,
                            strike_price=strike,
                            option_type="call",
                            expiration_date=next_friday
                        )
                        if option_quote:
                            # Use bid price (what you'd actually get when selling)
                            # Multiply by 100 for per-contract amount
                            logger.info(f"[SELL_DEBUG] {symbol}: Got quote - bid=${option_quote.bid}, ask={option_quote.ask}, last={option_quote.last_price}")
                            if option_quote.bid and option_quote.bid > 0:
                                real_premium_per_contract = option_quote.bid * 100
                                premium_source = "live_bid"
                            elif option_quote.last_price and option_quote.last_price > 0:
                                real_premium_per_contract = option_quote.last_price * 100
                                premium_source = "last_price"
                            else:
                                premium_source = "unavailable"
                            if real_premium_per_contract:
                                logger.info(f"[SELL_DEBUG] {symbol}: Premium=${real_premium_per_contract:.2f}/contract, source={premium_source}")
                        else:
                            logger.warning(f"[SELL_DEBUG] {symbol}: No option quote returned for ${strike}")
                            premium_source = "unavailable"
                    except Exception as e:
                        logger.warning(f"[SELL_DEBUG] {symbol}: Could not fetch premium: {e}")
                        premium_source = "unavailable"
                else:
                    premium_source = "unavailable"
                
                # DO NOT use fallback estimates - they can be dangerously inaccurate
                # Instead, show "premium not available" and let user check actual price
                if real_premium_per_contract is None:
                    premium_source = "unavailable"
                    total_premium = None
                    logger.warning(f"[SELL_DEBUG] {symbol}: Premium data unavailable - will show 'premium not available'")
                else:
                    total_premium = real_premium_per_contract * unsold
                
                # Determine priority based on total potential income (or default to medium if unavailable)
                if total_premium is not None:
                    if total_premium > 500:
                        priority = "high"
                    elif total_premium > 200:
                        priority = "medium"
                    else:
                        priority = "low"
                else:
                    priority = "medium"  # Default when premium unavailable
                
                # Title includes strike, expiration, stock price, and premium if available
                if current_price:
                    if total_premium is not None:
                        title = f"Sell {unsold} {symbol} call(s) at {strike_str} for {exp_str} · Stock ${current_price:.0f} · Earn ${total_premium:.0f}"
                    else:
                        title = f"Sell {unsold} {symbol} call(s) at {strike_str} for {exp_str} · Stock ${current_price:.0f} · Premium not available"
                else:
                    if total_premium is not None:
                        title = f"Sell {unsold} {symbol} call(s) at {strike_str} for {exp_str} · Earn ${total_premium:.0f}"
                    else:
                        title = f"Sell {unsold} {symbol} call(s) at {strike_str} for {exp_str} · Premium not available"
                
                # Description - show premium if available, otherwise prompt user to check
                if total_premium is not None:
                    if unsold == 1:
                        description = (
                            f"You have {unsold} unsold contract for {symbol}. "
                            f"Premium: ${real_premium_per_contract:.0f}"
                        )
                    else:
                        description = (
                            f"You have {unsold} unsold contracts for {symbol}. "
                            f"Premium: ${real_premium_per_contract:.0f}/contract (${total_premium:.0f} total)"
                        )
                else:
                    description = (
                        f"You have {unsold} unsold contract(s) for {symbol}. "
                        f"Check Robinhood for current premium."
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
                    potential_income=total_premium,
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
                        "premium_per_contract": real_premium_per_contract,  # None if unavailable
                        "total_premium": total_premium,  # None if unavailable
                        "premium_source": premium_source,  # "live_bid", "last_price", or "unavailable"
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

