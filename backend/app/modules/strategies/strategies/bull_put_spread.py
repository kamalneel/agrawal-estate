"""
Bull Put Spread Strategy

Identifies opportunities to sell bull put spreads on portfolio holdings.
Analyzes all holdings, ranks by potential profit, and recommends the best opportunities.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
import logging

from app.modules.strategies.strategy_base import BaseStrategy, StrategyConfig
from app.modules.strategies.recommendations import StrategyRecommendation
from app.modules.strategies.option_monitor import OptionChainFetcher
from app.modules.investments.services import get_all_holdings
from app.modules.investments.models import InvestmentHolding

logger = logging.getLogger(__name__)


class BullPutSpreadStrategy(BaseStrategy):
    """Strategy for identifying bull put spread opportunities."""
    
    strategy_type = "bull_put_spread"
    name = "Bull Put Spread Opportunities"
    description = "Identifies bull put spread opportunities on portfolio holdings, ranked by potential profit"
    category = "income_generation"
    default_parameters = {
        "sell_delta_min": 15,  # Minimum delta for selling put
        "sell_delta_max": 25,  # Maximum delta for selling put
        "buy_delta_min": 5,    # Minimum delta for buying protective put
        "buy_delta_max": 15,   # Maximum delta for buying protective put
        "min_days_to_expiry": 21,  # Minimum days until expiration
        "max_days_to_expiry": 45,  # Maximum days until expiration
        "min_credit_per_contract": 1.00,  # Minimum credit to justify trade
        "min_risk_reward_ratio": 2.0,  # Minimum risk/reward ratio (risk $X to make $Y)
        "spread_width_min": 3,  # Minimum spread width ($)
        "spread_width_max": 10,  # Maximum spread width ($)
        "min_iv_rank": 40,  # Minimum IV rank (premiums should be decent)
        "max_holdings_to_analyze": 20,  # Maximum number of holdings to analyze
    }
    
    def generate_recommendations(self, params: Dict[str, Any]) -> List[StrategyRecommendation]:
        """Generate bull put spread recommendations for portfolio holdings."""
        recommendations = []
        
        try:
            # Get all holdings
            holdings_data = get_all_holdings(self.db)
            logger.info(f"Bull Put Spread: Retrieved {len(holdings_data)} accounts with holdings")
            
            # Extract unique symbols from all accounts
            symbols = set()
            for account in holdings_data:
                for holding in account.get('holdings', []):
                    symbol = holding.get('symbol')
                    if symbol and symbol != 'CASH' and symbol:
                        symbols.add(symbol)
            
            if not symbols:
                logger.info("Bull Put Spread: No holdings found for analysis")
                return recommendations
            
            logger.info(f"Bull Put Spread: Analyzing {len(symbols)} symbols: {sorted(symbols)}")
        except Exception as e:
            logger.error(f"Bull Put Spread: Error getting holdings: {e}", exc_info=True)
            return recommendations
        
        # Limit to top holdings by value or all if < max
        symbols_list = list(symbols)[:self.get_parameter("max_holdings_to_analyze", 20)]
        logger.info(f"Analyzing {len(symbols_list)} holdings for bull put spread opportunities: {symbols_list}")
        
        # Analyze each symbol
        opportunities = []
        fetcher = OptionChainFetcher()
        
        for symbol in symbols_list:
            try:
                opportunity = self._analyze_symbol(symbol, fetcher, params)
                if opportunity:
                    opportunities.append(opportunity)
            except Exception as e:
                logger.warning(f"Error analyzing {symbol} for bull put spread: {e}")
                continue
        
        # Sort by potential profit (descending)
        opportunities.sort(key=lambda x: x.get('net_credit', 0), reverse=True)
        
        logger.info(f"Bull Put Spread: Found {len(opportunities)} total opportunities across {len(symbols_list)} symbols")
        if opportunities:
            logger.info(f"Bull Put Spread: Top opportunities: {[(opp.get('symbol'), opp.get('net_credit', 0)) for opp in opportunities[:5]]}")
        
        # Take top 2 opportunities (as requested)
        top_opportunities = opportunities[:2]
        
        # Convert to recommendations
        for opp in top_opportunities:
            recommendation = self._create_recommendation(opp)
            if recommendation:
                recommendations.append(recommendation)
        
        logger.info(f"Bull Put Spread: Generated {len(recommendations)} recommendations from {len(opportunities)} opportunities")
        return recommendations
    
    def _analyze_symbol(
        self,
        symbol: str,
        fetcher: OptionChainFetcher,
        params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Analyze a symbol for bull put spread opportunities."""
        from app.modules.strategies.option_data_service import (
            get_stock_info,
            get_option_expirations
        )
        
        try:
            # Get current stock price (Schwab preferred, Yahoo fallback)
            stock_info = get_stock_info(symbol)
            if not stock_info:
                logger.warning(f"Could not get info for {symbol}")
                return None
            
            current_price = stock_info.get('currentPrice') or stock_info.get('regularMarketPrice')
            
            if not current_price or current_price < 10:
                # Skip stocks under $10 (too risky for spreads)
                return None
            
            # Get available expirations (Schwab preferred, Yahoo fallback)
            available_expirations = get_option_expirations(symbol)
            if not available_expirations:
                return None
            
            # Find expiration in our target range (21-45 days)
            target_date = date.today() + timedelta(days=self.get_parameter("min_days_to_expiry", 21))
            max_date = date.today() + timedelta(days=self.get_parameter("max_days_to_expiry", 45))
            
            best_expiration = None
            for exp_str in available_expirations:
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                if target_date <= exp_date <= max_date:
                    best_expiration = exp_date
                    break
            
            if not best_expiration:
                # Use closest expiration in range
                closest = None
                min_diff = float('inf')
                for exp_str in available_expirations:
                    exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                    diff = abs((exp_date - target_date).days)
                    if diff < min_diff and exp_date >= date.today() + timedelta(days=14):
                        min_diff = diff
                        closest = exp_date
                best_expiration = closest
            
            if not best_expiration:
                return None
            
            # Get option chain
            option_chain = fetcher.get_option_chain(symbol, best_expiration)
            if not option_chain or 'puts' not in option_chain:
                return None
            
            puts_df = option_chain['puts']
            if puts_df.empty:
                return None
            
            # Find best bull put spread
            sell_delta_min = self.get_parameter("sell_delta_min", 15)
            sell_delta_max = self.get_parameter("sell_delta_max", 25)
            buy_delta_min = self.get_parameter("buy_delta_min", 5)
            buy_delta_max = self.get_parameter("buy_delta_max", 15)
            min_credit = self.get_parameter("min_credit_per_contract", 1.00)
            min_rr = self.get_parameter("min_risk_reward_ratio", 2.0)
            spread_width_min = self.get_parameter("spread_width_min", 3)
            spread_width_max = self.get_parameter("spread_width_max", 10)
            
            best_spread = None
            best_score = 0
            
            # Try different strike combinations
            for _, put_row in puts_df.iterrows():
                sell_strike = float(put_row['strike'])
                sell_bid = float(put_row.get('bid', 0))
                sell_delta = abs(float(put_row.get('inTheMoney', 0)))  # Approximate delta
                
                # Check if sell strike is in our delta range
                # For puts, delta is negative, so we use absolute value
                # We want strikes that are slightly OTM (delta 15-25)
                strike_pct_otm = (current_price - sell_strike) / current_price * 100
                
                # Approximate delta from OTM percentage
                # Rough approximation: 1% OTM ≈ delta 10, 2% OTM ≈ delta 20
                approx_delta = max(0, 50 - (strike_pct_otm * 10))
                
                if not (sell_delta_min <= approx_delta <= sell_delta_max):
                    continue
                
                if sell_bid < 0.50:  # Skip if premium too low
                    continue
                
                # Find protective put (lower strike)
                for _, buy_row in puts_df.iterrows():
                    buy_strike = float(buy_row['strike'])
                    
                    if buy_strike >= sell_strike:  # Must be lower
                        continue
                    
                    spread_width = sell_strike - buy_strike
                    if not (spread_width_min <= spread_width <= spread_width_max):
                        continue
                    
                    buy_ask = float(buy_row.get('ask', 0))
                    if buy_ask <= 0:
                        continue
                    
                    # Calculate spread metrics
                    net_credit = sell_bid - buy_ask
                    if net_credit < min_credit:
                        continue
                    
                    capital_required = spread_width * 100
                    max_profit = net_credit * 100
                    max_loss = capital_required - max_profit
                    
                    if max_loss <= 0:
                        continue
                    
                    risk_reward = max_profit / max_loss
                    if risk_reward < min_rr:
                        continue
                    
                    # Calculate probability (rough estimate from strike distance)
                    sell_otm_pct = (current_price - sell_strike) / current_price * 100
                    prob_profit = min(95, max(60, 100 - (sell_otm_pct * 5)))  # Rough estimate
                    
                    # Score: prioritize higher credit and better risk/reward
                    score = (net_credit * 100) * risk_reward * (prob_profit / 100)
                    
                    if score > best_score:
                        best_score = score
                        best_spread = {
                            'symbol': symbol,
                            'current_price': current_price,
                            'expiration': best_expiration,
                            'sell_strike': sell_strike,
                            'sell_bid': sell_bid,
                            'buy_strike': buy_strike,
                            'buy_ask': buy_ask,
                            'net_credit': net_credit,
                            'capital_required': capital_required,
                            'max_profit': max_profit,
                            'max_loss': max_loss,
                            'risk_reward': risk_reward,
                            'spread_width': spread_width,
                            'prob_profit': prob_profit,
                            'days_to_expiry': (best_expiration - date.today()).days,
                            'score': score,
                        }
            
            return best_spread
            
        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}", exc_info=True)
            return None
    
    def _create_recommendation(self, opportunity: Dict[str, Any]) -> Optional[StrategyRecommendation]:
        """Create a recommendation from an opportunity."""
        try:
            symbol = opportunity['symbol']
            sell_strike = opportunity['sell_strike']
            buy_strike = opportunity['buy_strike']
            net_credit = opportunity['net_credit']
            max_profit = opportunity['max_profit']
            max_loss = opportunity['max_loss']
            prob_profit = opportunity['prob_profit']
            days_to_expiry = opportunity['days_to_expiry']
            
            # Determine priority based on profit and probability
            if max_profit >= 200 and prob_profit >= 80:
                priority = "high"
            elif max_profit >= 150 and prob_profit >= 75:
                priority = "medium"
            else:
                priority = "low"
            
            title = f"Bull put spread: {symbol} ${sell_strike}/${buy_strike} - ${net_credit:.2f} credit"
            
            description = (
                f"Sell {symbol} ${sell_strike} put and buy ${buy_strike} put for net credit of ${net_credit:.2f} "
                f"(${max_profit:.0f} per contract). Capital required: ${opportunity['capital_required']:.0f}. "
                f"Max loss: ${max_loss:.0f}. Probability of profit: {prob_profit:.0f}%. "
                f"Expires in {days_to_expiry} days."
            )
            
            action = (
                f"Sell {symbol} ${sell_strike} put (bid: ${opportunity['sell_bid']:.2f}) and "
                f"buy {symbol} ${buy_strike} put (ask: ${opportunity['buy_ask']:.2f}) for "
                f"net credit of ${net_credit:.2f} per contract"
            )
            
            recommendation = StrategyRecommendation(
                id=f"bull_put_{symbol}_{sell_strike}_{buy_strike}_{opportunity['expiration'].isoformat()}",
                type=self.strategy_type,
                category=self.category,
                priority=priority,
                title=title,
                description=description,
                rationale=(
                    f"Bull put spread on {symbol} offers ${max_profit:.0f} potential profit with "
                    f"{prob_profit:.0f}% probability. Risk/reward ratio: {opportunity['risk_reward']:.2f}:1. "
                    f"Stock currently at ${opportunity['current_price']:.2f}, spread is {opportunity['spread_width']:.1f} points wide."
                ),
                action=action,
                action_type="spread",
                potential_income=max_profit,
                potential_risk="moderate" if max_loss < 500 else "high",
                time_horizon=f"{days_to_expiry}_days",
                context={
                    "symbol": symbol,
                    "current_price": opportunity['current_price'],
                    "sell_strike": sell_strike,
                    "buy_strike": buy_strike,
                    "sell_bid": opportunity['sell_bid'],
                    "buy_ask": opportunity['buy_ask'],
                    "net_credit": net_credit,
                    "capital_required": opportunity['capital_required'],
                    "max_profit": max_profit,
                    "max_loss": max_loss,
                    "risk_reward_ratio": opportunity['risk_reward'],
                    "spread_width": opportunity['spread_width'],
                    "probability_profit": prob_profit,
                    "expiration_date": opportunity['expiration'].isoformat(),
                    "days_to_expiry": days_to_expiry,
                    "account": "Neel's Investment",  # Focus on Neel's account as requested
                },
                expires_at=datetime.utcnow() + timedelta(days=days_to_expiry)
            )
            
            return recommendation
            
        except Exception as e:
            logger.error(f"Error creating recommendation: {e}", exc_info=True)
            return None

