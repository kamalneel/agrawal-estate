"""
Mega Cap Bull Put Spread Strategy

Scans all mega-cap stocks ($200B+ market cap) for bull put spread opportunities.
Uses technical analysis to find stocks at support levels with good premium.

Configuration:
- Expiration: Weekly (next Friday)
- Spread width: $5-10 (optimized per stock)  
- Min credit: ≥20% of spread width
- Alert limit: Configurable 1-5 or All (default: All)
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date, timedelta
import logging
import requests
import time

from app.modules.strategies.strategy_base import BaseStrategy
from app.modules.strategies.recommendations import StrategyRecommendation
from app.modules.strategies.technical_analysis import get_technical_analysis_service
from app.modules.strategies.option_monitor import OptionChainFetcher

logger = logging.getLogger(__name__)

# Mega-cap stocks with market cap > $200B (as of Dec 2024)
# Updated periodically - these are the most liquid options markets
MEGA_CAP_SYMBOLS = [
    # Tech
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA", 
    "AVGO", "ORCL", "CRM", "AMD", "ADBE", "CSCO", "ACN", "NFLX",
    # Finance
    "BRK-B", "JPM", "V", "MA", "BAC", "WFC", "MS", "GS",
    # Healthcare
    "UNH", "LLY", "JNJ", "ABBV", "MRK", "PFE", "TMO", "ABT",
    # Consumer
    "WMT", "HD", "COST", "MCD", "PG", "KO", "PEP", "NKE",
    # Energy
    "XOM", "CVX",
    # Industrial
    "CAT", "GE", "HON", "UNP", "RTX",
    # Other
    "TMUS", "VZ", "T",
]


class MegaCapBullPutStrategy(BaseStrategy):
    """
    Strategy for bull put spreads on mega-cap stocks.
    
    Aggressive on options (closer strikes) but conservative on companies.
    Uses technical analysis to find good entry points.
    """
    
    strategy_type = "mega_cap_bull_put"
    name = "Bull Put"
    description = "Bull put spread opportunities on $200B+ market cap stocks"
    category = "income_generation"
    default_parameters = {
        "min_market_cap_billions": 200,
        "spread_width_min": 5,
        "spread_width_max": 10,
        "min_credit_percent": 20,  # Minimum credit as % of spread width
        "target_probability": 75,  # Target probability OTM
        "max_alerts": 10,  # Limit to top 10 opportunities (was 0 = unlimited)
        "expiration_weeks": 1,  # Weekly
    }
    
    def generate_recommendations(self, params: Dict[str, Any]) -> List[StrategyRecommendation]:
        """Generate bull put spread recommendations for mega-cap stocks."""
        recommendations = []
        
        logger.info(f"Mega Cap Bull Put: Starting analysis of {len(MEGA_CAP_SYMBOLS)} mega-cap stocks")
        
        try:
            ta_service = get_technical_analysis_service()
            fetcher = OptionChainFetcher()
        except Exception as e:
            logger.error(f"Mega Cap Bull Put: Error initializing services: {e}", exc_info=True)
            return recommendations
        
        min_credit_pct = self.get_parameter("min_credit_percent", 20) / 100.0
        spread_width_min = self.get_parameter("spread_width_min", 5)
        spread_width_max = self.get_parameter("spread_width_max", 10)
        max_alerts = self.get_parameter("max_alerts", 0)
        
        opportunities = []
        
        # Analyze each mega-cap symbol
        for symbol in MEGA_CAP_SYMBOLS:
            try:
                opportunity = self._analyze_symbol(
                    symbol, ta_service, fetcher,
                    spread_width_min, spread_width_max, min_credit_pct
                )
                if opportunity:
                    opportunities.append(opportunity)
                
                # Small delay to avoid rate limiting
                time.sleep(0.1)
                
            except Exception as e:
                logger.debug(f"Error analyzing {symbol}: {e}")
                continue
        
        # Sort by score (best opportunities first)
        opportunities.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        # Apply alert limit
        if max_alerts > 0:
            opportunities = opportunities[:max_alerts]
        
        # Convert to recommendations
        for opp in opportunities:
            rec = self._create_recommendation(opp, ta_service)
            if rec:
                recommendations.append(rec)
        
        logger.info(f"Generated {len(recommendations)} mega-cap bull put recommendations")
        return recommendations
    
    def _analyze_symbol(
        self,
        symbol: str,
        ta_service,
        fetcher,
        spread_width_min: float,
        spread_width_max: float,
        min_credit_pct: float
    ) -> Optional[Dict[str, Any]]:
        """Analyze a symbol for bull put spread opportunity."""
        
        # Get technical indicators
        indicators = ta_service.get_technical_indicators(symbol)
        if not indicators:
            return None
        
        current_price = indicators.current_price
        if current_price < 20:  # Skip low-priced stocks
            return None
        
        # Skip if near earnings (too risky)
        if indicators.earnings_within_week:
            logger.debug(f"Skipping {symbol} - earnings within week")
            return None
        
        # Skip if oversold (might drop more)
        if indicators.rsi_14 < 25:
            logger.debug(f"Skipping {symbol} - oversold (RSI {indicators.rsi_14:.1f})")
            return None
        
        # Get next Friday
        next_friday = self._get_next_friday()
        
        # Get option chain
        try:
            chain = fetcher.get_option_chain(symbol, next_friday)
            if not chain or 'puts' not in chain:
                return None
            
            puts_df = chain['puts']
            if puts_df.empty:
                return None
        except Exception as e:
            logger.debug(f"Could not get options for {symbol}: {e}")
            return None
        
        # Get recommended strike from technical analysis
        strike_rec = ta_service.recommend_strike_price(
            symbol=symbol,
            option_type="put",
            expiration_weeks=1,
            probability_target=0.80  # 80% for the short put
        )
        
        if not strike_rec:
            return None
        
        target_sell_strike = strike_rec.recommended_strike
        
        # Find best spread around the target strike
        best_spread = None
        best_score = 0
        
        for _, sell_row in puts_df.iterrows():
            sell_strike = float(sell_row['strike'])
            
            # Only consider strikes near our target
            if abs(sell_strike - target_sell_strike) / target_sell_strike > 0.05:
                continue
            
            sell_bid = float(sell_row.get('bid', 0))
            if sell_bid < 0.30:  # Skip if premium too low
                continue
            
            # Find buy strike (lower)
            for _, buy_row in puts_df.iterrows():
                buy_strike = float(buy_row['strike'])
                
                if buy_strike >= sell_strike:
                    continue
                
                spread_width = sell_strike - buy_strike
                if not (spread_width_min <= spread_width <= spread_width_max):
                    continue
                
                buy_ask = float(buy_row.get('ask', 0))
                if buy_ask <= 0:
                    continue
                
                # Calculate spread metrics
                net_credit = sell_bid - buy_ask
                if net_credit < spread_width * min_credit_pct:
                    continue
                
                capital_required = spread_width * 100
                max_profit = net_credit * 100
                max_loss = capital_required - max_profit
                
                if max_loss <= 0:
                    continue
                
                risk_reward = max_profit / max_loss
                
                # Estimate probability (rough)
                otm_pct = (current_price - sell_strike) / current_price * 100
                prob_profit = min(95, max(60, 50 + otm_pct * 8))
                
                # Score: prioritize credit and probability
                score = (net_credit * 100) * (prob_profit / 100) * risk_reward
                
                # Bonus for being near support
                if indicators.nearest_support:
                    support_distance = (sell_strike - indicators.nearest_support) / sell_strike * 100
                    if support_distance < 3:  # Within 3% of support
                        score *= 1.2
                
                if score > best_score:
                    best_score = score
                    best_spread = {
                        'symbol': symbol,
                        'current_price': current_price,
                        'sell_strike': sell_strike,
                        'buy_strike': buy_strike,
                        'sell_bid': sell_bid,
                        'buy_ask': buy_ask,
                        'net_credit': net_credit,
                        'spread_width': spread_width,
                        'capital_required': capital_required,
                        'max_profit': max_profit,
                        'max_loss': max_loss,
                        'risk_reward': risk_reward,
                        'prob_profit': prob_profit,
                        'expiration': next_friday,
                        'score': score,
                        'indicators': indicators,
                    }
        
        return best_spread
    
    def _create_recommendation(
        self,
        opportunity: Dict[str, Any],
        ta_service
    ) -> Optional[StrategyRecommendation]:
        """Create recommendation from opportunity."""
        
        symbol = opportunity['symbol']
        sell_strike = opportunity['sell_strike']
        buy_strike = opportunity['buy_strike']
        net_credit = opportunity['net_credit']
        max_profit = opportunity['max_profit']
        max_loss = opportunity['max_loss']
        prob_profit = opportunity['prob_profit']
        expiration = opportunity['expiration']
        indicators = opportunity['indicators']
        
        # Determine priority
        if max_profit >= 150 and prob_profit >= 75:
            priority = "high"
        elif max_profit >= 100 and prob_profit >= 70:
            priority = "medium"
        else:
            priority = "low"
        
        context = {
            "symbol": symbol,
            "sell_strike": sell_strike,
            "buy_strike": buy_strike,
            "sell_bid": opportunity['sell_bid'],
            "buy_ask": opportunity['buy_ask'],
            "net_credit": net_credit,
            "spread_width": opportunity['spread_width'],
            "capital_required": opportunity['capital_required'],
            "max_profit": max_profit,
            "max_loss": max_loss,
            "risk_reward_ratio": round(opportunity['risk_reward'], 2),
            "probability_profit": round(prob_profit, 1),
            "expiration_date": expiration.isoformat(),
            "days_to_expiry": (expiration - date.today()).days,
            # Technical analysis for UI popup
            "technical_analysis": {
                "current_price": indicators.current_price,
                "rsi": round(indicators.rsi_14, 1),
                "rsi_status": indicators.rsi_status,
                "bb_position": indicators.bb_position,
                "trend": indicators.trend,
                "nearest_support": indicators.nearest_support,
                "nearest_resistance": indicators.nearest_resistance,
                "weekly_volatility": round(indicators.weekly_volatility * 100, 2),
                "earnings_date": indicators.earnings_date.isoformat() if indicators.earnings_date else None,
            }
        }
        
        # Short title for Telegram
        title = f"Bull Put: {symbol} ${sell_strike:.0f}/${buy_strike:.0f} (${net_credit:.2f} credit)"
        
        return StrategyRecommendation(
            id=f"mega_bull_put_{symbol}_{sell_strike}_{buy_strike}_{date.today().isoformat()}",
            type=self.strategy_type,
            category=self.category,
            priority=priority,
            title=title,
            description=(
                f"{symbol} bull put spread: Sell ${sell_strike:.0f} put / Buy ${buy_strike:.0f} put "
                f"for ${net_credit:.2f} credit. Expires {expiration.strftime('%b %d')}. "
                f"Max profit: ${max_profit:.0f}, Max loss: ${max_loss:.0f}"
            ),
            rationale=(
                f"Stock at ${indicators.current_price:.2f}, RSI {indicators.rsi_14:.1f} ({indicators.rsi_status}). "
                f"Put spread below current price with {prob_profit:.0f}% probability of profit. "
                f"Capital required: ${opportunity['capital_required']:.0f}."
            ),
            action=(
                f"Sell {symbol} ${sell_strike:.0f} put at ${opportunity['sell_bid']:.2f}, "
                f"Buy {symbol} ${buy_strike:.0f} put at ${opportunity['buy_ask']:.2f}"
            ),
            action_type="spread",
            potential_income=max_profit,
            potential_risk="moderate" if max_loss < 500 else "high",
            time_horizon=f"{(expiration - date.today()).days}_days",
            context=context,
            expires_at=datetime.combine(expiration, datetime.max.time())
        )
    
    def _get_next_friday(self) -> date:
        """Get next Friday's date."""
        today = date.today()
        days_ahead = 4 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return today + timedelta(days=days_ahead)

