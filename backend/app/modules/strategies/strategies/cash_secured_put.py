"""
Cash-Secured Put Strategy (V3.4)

Recommends selling cash-secured puts on portfolio stocks when:
1. Technical conditions are favorable (oversold/at support)
2. Premium is attractive relative to capital requirement
3. User has available cash and is willing to own more

Philosophy: Sell puts when stocks are BEATEN DOWN, not flying high.
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.modules.strategies.strategy_base import BaseStrategy, StrategyRecommendation
from app.modules.strategies.technical_analysis import get_technical_analysis_service
from app.modules.strategies.schwab_service import get_options_chain_schwab, get_stock_quote_schwab

logger = logging.getLogger(__name__)


class CashSecuredPutStrategy(BaseStrategy):
    """
    V3.4 Cash-Secured Put Selling Strategy
    
    Analyzes portfolio stocks for put selling opportunities based on:
    - Technical Analysis (RSI, Bollinger Bands)
    - Premium attractiveness (ROI on capital)
    - Probability of profit (delta-based)
    """
    
    # Scoring thresholds
    GRADE_A_PLUS = 90
    GRADE_A = 80
    GRADE_B_PLUS = 70
    GRADE_B = 60
    GRADE_C = 50
    
    # Recommendation thresholds
    MIN_SCORE_FOR_RECOMMENDATION = 80  # Grade A
    MIN_PREMIUM_PER_CONTRACT = 30  # $30 minimum
    TARGET_DELTA = 0.10  # 10 delta = 90% probability OTM
    DELTA_RANGE = (0.08, 0.15)  # Acceptable delta range
    
    @property
    def strategy_type(self) -> str:
        return "cash_secured_put"
    
    @property
    def name(self) -> str:
        return "Cash-Secured Put Strategy"
    
    @property
    def description(self) -> str:
        return "Recommends selling cash-secured puts on portfolio stocks when TA conditions are favorable (oversold/at support)"
    
    @property
    def category(self) -> str:
        return "income"
    
    @property
    def default_parameters(self) -> Dict[str, Any]:
        return {
            "min_score": self.MIN_SCORE_FOR_RECOMMENDATION,
            "min_premium": self.MIN_PREMIUM_PER_CONTRACT,
            "target_delta": self.TARGET_DELTA,
        }
    
    def __init__(self, db: Session, config=None):
        # Handle both new-style (config object) and simple db-only calls
        if config is None:
            from app.modules.strategies.strategy_base import StrategyConfig
            config = StrategyConfig(
                strategy_type="cash_secured_put",
                name="Cash-Secured Put Strategy",
                description="Sell puts when TA is favorable",
                category="income",
                parameters={}
            )
        super().__init__(db, config)
        self.ta_service = get_technical_analysis_service()
    
    def generate_recommendations(self, params: Dict[str, Any] = None) -> List[StrategyRecommendation]:
        """Generate put selling recommendations for all portfolio stocks."""
        if params is None:
            params = {}
        recommendations = []
        
        # Get all unique symbols from portfolio
        symbols = self._get_portfolio_symbols()
        if not symbols:
            logger.info("No portfolio symbols found for put analysis")
            return recommendations
        
        logger.info(f"Analyzing {len(symbols)} portfolio symbols for put opportunities")
        
        # Get next Friday for expiration
        target_expiration = self._get_next_friday()
        
        for symbol in symbols:
            try:
                opportunity = self._analyze_symbol(symbol, target_expiration)
                if opportunity:
                    rec = self._create_recommendation(opportunity)
                    if rec:
                        recommendations.append(rec)
                        # Also save to put_opportunities table for RLHF tracking
                        self._save_opportunity(opportunity)
            except Exception as e:
                logger.warning(f"Error analyzing {symbol} for puts: {e}")
                continue
        
        # Sort by combined score (best first)
        recommendations.sort(key=lambda r: r.context.get('combined_score', 0), reverse=True)
        
        logger.info(f"Generated {len(recommendations)} put recommendations")
        return recommendations
    
    def _get_portfolio_symbols(self) -> List[str]:
        """Get all unique symbols from user's portfolio."""
        try:
            result = self.db.execute(text("""
                SELECT DISTINCT symbol 
                FROM investment_holdings 
                WHERE quantity > 0
                  AND symbol NOT IN ('FDRXX', 'SPAXX', 'VMFXX', 'VMMXX')
                  AND symbol NOT LIKE '%XX'
                  AND LENGTH(symbol) <= 5
                ORDER BY symbol
            """))
            symbols = [row[0] for row in result.fetchall()]
            return symbols
        except Exception as e:
            logger.error(f"Error fetching portfolio symbols: {e}")
            return []
    
    def _get_next_friday(self) -> date:
        """Get the next Friday's date for expiration."""
        today = date.today()
        days_ahead = 4 - today.weekday()  # Friday is weekday 4
        if days_ahead <= 0:
            days_ahead += 7
        return today + timedelta(days=days_ahead)
    
    def _analyze_symbol(self, symbol: str, expiration: date) -> Optional[Dict[str, Any]]:
        """
        Analyze a symbol for put selling opportunity.
        
        Returns opportunity dict if favorable, None otherwise.
        """
        # Get technical indicators
        indicators = self.ta_service.get_technical_indicators(symbol)
        if not indicators:
            logger.debug(f"{symbol}: No TA data available")
            return None
        
        current_price = indicators.current_price
        rsi = indicators.rsi_14
        bb_upper = indicators.bb_upper
        bb_lower = indicators.bb_lower
        
        # Calculate Bollinger Band position (0% = lower, 100% = upper)
        bb_range = bb_upper - bb_lower
        bb_position_pct = ((current_price - bb_lower) / bb_range * 100) if bb_range > 0 else 50
        
        # Get put option chain
        chain_data = get_options_chain_schwab(symbol, expiration.isoformat(), 'PUT')
        if not chain_data:
            logger.debug(f"{symbol}: No options chain available")
            return None
        
        options = chain_data.get('puts', [])
        if not options:
            logger.debug(f"{symbol}: No put options found")
            return None
        
        # Find best option (closest to target delta)
        best_option = self._find_best_option(options, current_price)
        if not best_option:
            logger.debug(f"{symbol}: No suitable strike found")
            return None
        
        strike = best_option.get('strike', 0)
        bid = best_option.get('bid', 0) or 0
        delta = best_option.get('delta', 0) or 0
        
        if bid <= 0:
            return None
        
        # Calculate metrics
        otm_pct = ((current_price - strike) / current_price) * 100
        premium_per_contract = bid * 100
        capital_at_risk = strike * 100
        roi_pct = (premium_per_contract / capital_at_risk) * 100 if capital_at_risk > 0 else 0
        prob_otm = (1 - abs(delta)) * 100 if delta else 90
        
        # Calculate scores
        rsi_score = self._calculate_rsi_score(rsi)
        bb_score = self._calculate_bb_score(bb_position_pct)
        premium_score = min(roi_pct * 100, 30)  # Cap at 30 points
        ta_score = 50 + rsi_score + bb_score  # Base 50 + adjustments
        combined_score = ta_score + premium_score
        
        # Determine grade
        grade = self._get_grade(combined_score)
        
        # Build opportunity dict
        opportunity = {
            'symbol': symbol,
            'current_price': current_price,
            'strike': strike,
            'expiration': expiration,
            'bid': bid,
            'ask': best_option.get('ask', 0),
            'delta': delta,
            'premium_per_contract': premium_per_contract,
            'capital_at_risk': capital_at_risk,
            'otm_pct': otm_pct,
            'roi_pct': roi_pct,
            'prob_otm': prob_otm,
            # TA details
            'rsi': rsi,
            'bb_position_pct': bb_position_pct,
            'bb_lower': bb_lower,
            'bb_upper': bb_upper,
            'bb_middle': indicators.bb_middle,
            'trend': indicators.trend,
            # Scores
            'rsi_score': rsi_score,
            'bb_score': bb_score,
            'premium_score': premium_score,
            'ta_score': ta_score,
            'combined_score': combined_score,
            'grade': grade,
            # Reasons
            'rsi_reason': self._get_rsi_reason(rsi),
            'bb_reason': self._get_bb_reason(bb_position_pct),
        }
        
        return opportunity
    
    def _find_best_option(self, options: List[Dict], current_price: float) -> Optional[Dict]:
        """Find the put option closest to target delta with positive bid."""
        best_option = None
        
        # First pass: find option closest to 10 delta
        for opt in options:
            delta = abs(opt.get('delta', 0) or 0)
            bid = opt.get('bid', 0) or 0
            
            if bid > 0 and self.DELTA_RANGE[0] <= delta <= self.DELTA_RANGE[1]:
                if best_option is None:
                    best_option = opt
                elif abs(delta - self.TARGET_DELTA) < abs(abs(best_option.get('delta', 0) or 0) - self.TARGET_DELTA):
                    best_option = opt
        
        # Fallback: find strike ~8-10% below current price
        if not best_option:
            target_strike = current_price * 0.92
            for opt in options:
                strike = opt.get('strike', 0)
                bid = opt.get('bid', 0) or 0
                if strike <= target_strike and bid > 0:
                    if best_option is None or strike > best_option.get('strike', 0):
                        best_option = opt
        
        return best_option
    
    def _calculate_rsi_score(self, rsi: float) -> int:
        """Calculate RSI contribution to score."""
        if rsi < 30:
            return 30  # Oversold - excellent
        elif rsi < 40:
            return 20  # Near oversold - good
        elif rsi < 50:
            return 10  # Neutral-bullish
        elif rsi < 60:
            return 0   # Neutral
        elif rsi < 70:
            return -10  # Getting hot
        else:
            return -20  # Overbought - risky
    
    def _calculate_bb_score(self, bb_position_pct: float) -> int:
        """Calculate Bollinger Band position contribution to score."""
        if bb_position_pct < 20:
            return 30  # At support - excellent
        elif bb_position_pct < 35:
            return 20  # Lower half - good
        elif bb_position_pct < 50:
            return 10  # Below middle
        elif bb_position_pct < 65:
            return 0   # At middle
        elif bb_position_pct < 80:
            return -10  # Upper half
        else:
            return -20  # At resistance - risky
    
    def _get_grade(self, score: float) -> str:
        """Get letter grade from combined score."""
        if score >= self.GRADE_A_PLUS:
            return "A+"
        elif score >= self.GRADE_A:
            return "A"
        elif score >= self.GRADE_B_PLUS:
            return "B+"
        elif score >= self.GRADE_B:
            return "B"
        elif score >= self.GRADE_C:
            return "C"
        else:
            return "D"
    
    def _get_rsi_reason(self, rsi: float) -> str:
        """Get human-readable RSI reason."""
        if rsi < 30:
            return f"🟢 RSI {rsi:.0f} (OVERSOLD - excellent)"
        elif rsi < 40:
            return f"🟢 RSI {rsi:.0f} (near oversold - good)"
        elif rsi < 50:
            return f"🟡 RSI {rsi:.0f} (neutral-bullish)"
        elif rsi < 60:
            return f"🟡 RSI {rsi:.0f} (neutral)"
        elif rsi < 70:
            return f"🟠 RSI {rsi:.0f} (getting hot)"
        else:
            return f"🔴 RSI {rsi:.0f} (OVERBOUGHT - risky)"
    
    def _get_bb_reason(self, bb_position_pct: float) -> str:
        """Get human-readable Bollinger Band reason."""
        if bb_position_pct < 20:
            return f"🟢 BB {bb_position_pct:.0f}% (at support - excellent)"
        elif bb_position_pct < 35:
            return f"🟢 BB {bb_position_pct:.0f}% (lower half - good)"
        elif bb_position_pct < 50:
            return f"🟡 BB {bb_position_pct:.0f}% (below middle)"
        elif bb_position_pct < 65:
            return f"🟡 BB {bb_position_pct:.0f}% (at middle)"
        elif bb_position_pct < 80:
            return f"🟠 BB {bb_position_pct:.0f}% (upper half)"
        else:
            return f"🔴 BB {bb_position_pct:.0f}% (at resistance - risky)"
    
    def _create_recommendation(self, opportunity: Dict[str, Any]) -> Optional[StrategyRecommendation]:
        """Create a StrategyRecommendation from an opportunity."""
        # Apply filters
        if opportunity['combined_score'] < self.MIN_SCORE_FOR_RECOMMENDATION:
            logger.debug(f"{opportunity['symbol']}: Score {opportunity['combined_score']:.0f} below threshold")
            return None
        
        if opportunity['premium_per_contract'] < self.MIN_PREMIUM_PER_CONTRACT:
            logger.debug(f"{opportunity['symbol']}: Premium ${opportunity['premium_per_contract']:.0f} below threshold")
            return None
        
        symbol = opportunity['symbol']
        strike = opportunity['strike']
        expiration = opportunity['expiration']
        premium = opportunity['premium_per_contract']
        grade = opportunity['grade']
        
        # Build title
        title = (
            f"SELL PUT: {symbol} ${strike:.0f} @ ${opportunity['bid']:.2f} "
            f"· Grade {grade} · Earn ${premium:.0f}"
        )
        
        # Build description
        description = (
            f"Sell {symbol} ${strike:.0f} put expiring {expiration.strftime('%b %d')} "
            f"for ${premium:.0f}/contract. "
            f"{opportunity['otm_pct']:.1f}% OTM with ~{opportunity['prob_otm']:.0f}% win rate."
        )
        
        # Build rationale with TA
        rationale = (
            f"{opportunity['rsi_reason']}. {opportunity['bb_reason']}. "
            f"Premium offers {opportunity['roi_pct']:.2f}% ROI on ${opportunity['capital_at_risk']:,.0f} capital."
        )
        
        # Build decision rationale (plain English for UI)
        decision_rationale = self._build_decision_rationale(opportunity)
        
        # Build TA summary for UI
        ta_summary = {
            'current_price': round(opportunity['current_price'], 2),
            'strike_price': round(strike, 2),
            'option_type': 'PUT',
            'is_itm': False,
            'otm_pct': round(opportunity['otm_pct'], 1),
            'days_to_expiry': (expiration - date.today()).days,
            'bollinger': {
                'upper': round(opportunity['bb_upper'], 2),
                'middle': round(opportunity['bb_middle'], 2),
                'lower': round(opportunity['bb_lower'], 2),
                'position_pct': round(opportunity['bb_position_pct'], 0),
                'position_desc': self._get_bb_position_desc(opportunity['bb_position_pct']),
            },
            'rsi': {
                'value': round(opportunity['rsi'], 1),
                'status': self._get_rsi_status(opportunity['rsi']),
            },
        }
        
        return StrategyRecommendation(
            id=f"put_{symbol}_{strike}_{expiration.isoformat()}",
            type=self.strategy_type,
            category=self.category,
            priority="high" if grade in ["A+", "A"] else "medium",
            title=title,
            description=description,
            rationale=rationale,
            action=f"Sell {symbol} ${strike:.0f} Put expiring {expiration.strftime('%b %d')}",
            action_type="sell_put",
            potential_income=round(premium, 2),
            potential_risk="medium",  # Assignment risk
            time_horizon="this_week",
            symbol=symbol,
            account_name=None,  # User chooses account
            context={
                **opportunity,
                'expiration': expiration.isoformat(),
                'ta_summary': ta_summary,
                'decision_rationale': decision_rationale,
            },
            expires_at=datetime.combine(expiration, datetime.max.time())
        )
    
    def _build_decision_rationale(self, opp: Dict[str, Any]) -> str:
        """Build plain English decision rationale."""
        symbol = opp['symbol']
        
        # Situation
        situation = (
            f"{symbol} is trading at ${opp['current_price']:.2f} with the "
            f"${opp['strike']:.0f} put available for ${opp['bid']:.2f} "
            f"(${opp['premium_per_contract']:.0f}/contract)."
        )
        
        # TA context
        ta_context = (
            f"The stock is at {opp['bb_position_pct']:.0f}% of its Bollinger Band range "
            f"(${opp['bb_lower']:.0f} - ${opp['bb_upper']:.0f}) with RSI at {opp['rsi']:.0f}. "
        )
        
        # Recommendation
        if opp['rsi'] < 40 and opp['bb_position_pct'] < 35:
            recommendation = (
                "This is an EXCELLENT setup for selling puts. The stock is oversold "
                "and near support, suggesting limited downside risk. High probability "
                "of keeping the full premium."
            )
        elif opp['rsi'] < 50 and opp['bb_position_pct'] < 50:
            recommendation = (
                "Good setup for selling puts. Technical conditions are favorable "
                "with the stock in the lower half of its range. Reasonable probability "
                "of success."
            )
        elif opp['rsi'] > 70 or opp['bb_position_pct'] > 80:
            recommendation = (
                "CAUTION: The stock appears overbought/extended. A pullback is possible, "
                "which could put your put in danger. Consider waiting for better conditions."
            )
        else:
            recommendation = (
                "Neutral conditions. The premium is attractive but technical setup "
                "is neither strongly favorable nor unfavorable. Proceed with awareness."
            )
        
        return f"{situation}\n\n{ta_context}\n\n{recommendation}"
    
    def _get_bb_position_desc(self, bb_pct: float) -> str:
        """Get short BB position description."""
        if bb_pct < 20:
            return "at support"
        elif bb_pct < 35:
            return "lower half"
        elif bb_pct < 50:
            return "below middle"
        elif bb_pct < 65:
            return "middle"
        elif bb_pct < 80:
            return "upper half"
        else:
            return "at resistance"
    
    def _get_rsi_status(self, rsi: float) -> str:
        """Get short RSI status."""
        if rsi < 30:
            return "oversold"
        elif rsi < 40:
            return "near oversold"
        elif rsi < 60:
            return "neutral"
        elif rsi < 70:
            return "near overbought"
        else:
            return "overbought"
    
    def _save_opportunity(self, opportunity: Dict[str, Any]) -> None:
        """Save opportunity to database for RLHF tracking."""
        try:
            import json
            # Create a JSON-serializable version of the context
            context_copy = {k: (v.isoformat() if isinstance(v, date) else v) 
                          for k, v in opportunity.items()}
            
            self.db.execute(
                text("""
                    INSERT INTO put_opportunities (
                        symbol, recommendation_date, score, grade,
                        strike, expiration, bid_price, ask_price, delta,
                        premium_per_contract, stock_price, otm_pct,
                        rsi, bb_position_pct, bb_lower, bb_upper, trend,
                        rsi_score, bb_score, premium_score, ta_score,
                        status, full_context, created_at
                    ) VALUES (
                        :symbol, :recommendation_date, :score, :grade,
                        :strike, :expiration, :bid_price, :ask_price, :delta,
                        :premium_per_contract, :stock_price, :otm_pct,
                        :rsi, :bb_position_pct, :bb_lower, :bb_upper, :trend,
                        :rsi_score, :bb_score, :premium_score, :ta_score,
                        'recommended', :full_context::jsonb, NOW()
                    )
                    ON CONFLICT DO NOTHING
                """),
                {
                    'symbol': opportunity['symbol'],
                    'recommendation_date': date.today(),
                    'score': float(opportunity['combined_score']),
                    'grade': opportunity['grade'],
                    'strike': float(opportunity['strike']),
                    'expiration': opportunity['expiration'],
                    'bid_price': float(opportunity['bid']),
                    'ask_price': float(opportunity.get('ask', 0)),
                    'delta': float(opportunity['delta']),
                    'premium_per_contract': float(opportunity['premium_per_contract']),
                    'stock_price': float(opportunity['current_price']),
                    'otm_pct': float(opportunity['otm_pct']),
                    'rsi': float(opportunity['rsi']),
                    'bb_position_pct': float(opportunity['bb_position_pct']),
                    'bb_lower': float(opportunity['bb_lower']),
                    'bb_upper': float(opportunity['bb_upper']),
                    'trend': opportunity.get('trend'),
                    'rsi_score': int(opportunity['rsi_score']),
                    'bb_score': int(opportunity['bb_score']),
                    'premium_score': float(opportunity['premium_score']),
                    'ta_score': int(opportunity['ta_score']),
                    'full_context': json.dumps(context_copy),
                }
            )
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.warning(f"Failed to save put opportunity for {opportunity['symbol']}: {e}")

