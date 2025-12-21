"""
ITM Roll Optimizer

When a position goes In The Money (ITM), this optimizer analyzes all possible
roll combinations to find the optimal balance of:
1. Net Cost (minimize debit, ideally achieve credit)
2. Time (prefer shorter duration, less capital tied up)
3. Safety (higher probability of staying OTM)

Presents top 3 options: Conservative, Moderate, Aggressive
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, date, timedelta
import logging
import numpy as np

# V2.2 Refactoring: Use centralized utility functions
from app.modules.strategies.utils.option_calculations import calculate_itm_status

logger = logging.getLogger(__name__)


@dataclass
class RollOption:
    """A single roll option with all relevant metrics."""
    expiration_date: date
    expiration_weeks: int
    new_strike: float
    
    # Cost analysis
    buy_back_cost: float  # Cost to close current position (per share)
    new_premium: float  # Premium received for new position (per share)
    net_cost: float  # buy_back_cost - new_premium (negative = credit)
    net_cost_total: float  # net_cost * 100 * contracts
    
    # Risk metrics
    probability_otm: float  # Probability of staying OTM (0-100%)
    delta: float  # Option delta
    
    # Scoring
    score: float
    category: str  # 'conservative', 'moderate', 'aggressive'
    
    # Context
    days_to_expiry: int
    strike_distance_pct: float  # % above current price (for calls)
    annualized_return_if_otm: float  # If position closes OTM


@dataclass  
class ITMRollAnalysis:
    """Complete analysis for an ITM position."""
    symbol: str
    current_strike: float
    current_price: float
    option_type: str
    contracts: int
    account_name: Optional[str]
    
    # Current position cost
    buy_back_cost: float  # Per share cost to close
    buy_back_total: float  # Total cost to close
    
    # ITM status
    itm_percent: float
    days_to_current_expiry: int
    
    # Roll options
    options: List[RollOption]
    
    # Recommendations
    conservative: Optional[RollOption]
    moderate: Optional[RollOption]
    aggressive: Optional[RollOption]
    
    # Technical analysis context
    technical_signals: Dict[str, Any]
    recommendation_summary: str


class ITMRollOptimizer:
    """
    Optimizes roll decisions for In-The-Money options.
    
    Analyzes cost matrix across multiple expirations and strikes
    to find optimal roll combinations.
    """
    
    def __init__(self, ta_service=None, option_fetcher=None):
        """
        Initialize optimizer.
        
        Args:
            ta_service: TechnicalAnalysisService instance
            option_fetcher: OptionChainFetcher instance
        """
        from app.modules.strategies.technical_analysis import get_technical_analysis_service
        from app.modules.strategies.option_monitor import OptionChainFetcher
        
        self.ta_service = ta_service or get_technical_analysis_service()
        self.fetcher = option_fetcher or OptionChainFetcher()
    
    def analyze_itm_position(
        self,
        symbol: str,
        current_strike: float,
        option_type: str,
        current_expiration: date,
        contracts: int = 1,
        account_name: Optional[str] = None,
        max_weeks_out: int = 6,
        max_net_debit: float = 5.0  # Maximum acceptable per-share debit
    ) -> Optional[ITMRollAnalysis]:
        """
        Analyze an ITM position and generate roll options.
        
        Args:
            symbol: Stock symbol
            current_strike: Current option strike price
            option_type: 'call' or 'put'
            current_expiration: Current option expiration date
            contracts: Number of contracts
            account_name: Account name for context
            max_weeks_out: Maximum weeks to consider for roll
            max_net_debit: Maximum acceptable net debit per share
            
        Returns:
            ITMRollAnalysis with top 3 roll options
        """
        try:
            # Get technical indicators
            indicators = self.ta_service.get_technical_indicators(symbol)
            if not indicators:
                logger.error(f"Could not get indicators for {symbol}")
                return None
            
            current_price = indicators.current_price
            
            # V2.2: Use centralized ITM calculation
            itm_calc = calculate_itm_status(current_price, current_strike, option_type)
            is_itm = itm_calc['is_itm']
            itm_pct = itm_calc['itm_pct']
            intrinsic_value = itm_calc['intrinsic_value']
            
            # Get current option price (buy-back cost)
            current_option_price = self._get_current_option_price(
                symbol, current_strike, option_type, current_expiration
            )
            
            # Calculate time value estimate
            days_left = (current_expiration - date.today()).days
            extrinsic_estimate = indicators.weekly_volatility * current_price * np.sqrt(max(days_left, 1) / 252) * 0.4
            
            if current_option_price is None:
                logger.warning(f"Could not get current option price for {symbol}")
                # Estimate based on intrinsic value + time value
                current_option_price = intrinsic_value + extrinsic_estimate
            
            # VALIDATION: Buy-back cost should be at least the intrinsic value
            # If market data shows less than intrinsic, it's likely bad data
            if current_option_price < intrinsic_value * 0.95:  # Allow 5% tolerance for market inefficiency
                logger.warning(
                    f"Buy-back cost ${current_option_price:.2f} is less than intrinsic ${intrinsic_value:.2f} "
                    f"for {symbol} - using corrected value"
                )
                current_option_price = intrinsic_value + extrinsic_estimate
            
            buy_back_cost = current_option_price
            buy_back_total = buy_back_cost * 100 * contracts
            
            # For deep ITM positions, increase max_net_debit proportionally
            # A 35% ITM position needs to allow larger debits to find any viable roll
            effective_max_debit = max_net_debit
            if itm_pct > 10:
                # Allow up to 50% of intrinsic value as debit for deep ITM
                effective_max_debit = max(max_net_debit, intrinsic_value * 0.5)
                logger.info(f"Deep ITM ({itm_pct:.1f}%): Increased max_net_debit to ${effective_max_debit:.2f}")
            
            days_to_current_expiry = (current_expiration - date.today()).days
            
            # Scan roll options
            roll_options = self._scan_roll_options(
                symbol=symbol,
                current_strike=current_strike,
                option_type=option_type,
                current_price=current_price,
                buy_back_cost=buy_back_cost,
                contracts=contracts,
                indicators=indicators,
                max_weeks_out=max_weeks_out,
                max_net_debit=effective_max_debit,  # Use adjusted debit limit for deep ITM
                current_expiration=current_expiration  # Pass current expiration to skip same-week rolls
            )
            
            if not roll_options:
                logger.warning(f"No valid roll options found for {symbol}")
                return None
            
            # Score and categorize options
            self._score_options(roll_options, indicators)
            
            # Select top 3 by category
            conservative, moderate, aggressive = self._select_top_options(roll_options)
            
            # Build technical signals summary
            tech_signals = self._summarize_technical_signals(indicators, itm_pct)
            
            # Generate recommendation summary
            summary = self._generate_summary(
                conservative, moderate, aggressive, 
                itm_pct, buy_back_cost, tech_signals
            )
            
            return ITMRollAnalysis(
                symbol=symbol,
                current_strike=current_strike,
                current_price=current_price,
                option_type=option_type,
                contracts=contracts,
                account_name=account_name,
                buy_back_cost=buy_back_cost,
                buy_back_total=buy_back_total,
                itm_percent=itm_pct,
                days_to_current_expiry=days_to_current_expiry,
                options=roll_options,
                conservative=conservative,
                moderate=moderate,
                aggressive=aggressive,
                technical_signals=tech_signals,
                recommendation_summary=summary
            )
            
        except Exception as e:
            logger.error(f"Error analyzing ITM position for {symbol}: {e}", exc_info=True)
            return None
    
    def _get_current_option_price(
        self, 
        symbol: str, 
        strike: float, 
        option_type: str, 
        expiration: date
    ) -> Optional[float]:
        """Get the current market price of an option."""
        try:
            chain = self.fetcher.get_option_chain(symbol, expiration)
            if not chain:
                return None
            
            key = 'calls' if option_type.lower() == 'call' else 'puts'
            options_df = chain.get(key)
            
            if options_df is None or options_df.empty:
                return None
            
            # Find the strike
            matching = options_df[
                (options_df['strike'] >= strike - 0.5) & 
                (options_df['strike'] <= strike + 0.5)
            ]
            
            if matching.empty:
                return None
            
            # Use mid price
            row = matching.iloc[0]
            bid = row.get('bid', 0) or 0
            ask = row.get('ask', 0) or 0
            
            if bid > 0 and ask > 0:
                return (bid + ask) / 2
            elif ask > 0:
                return ask
            else:
                return row.get('lastPrice', None)
                
        except Exception as e:
            logger.error(f"Error getting option price: {e}")
            return None
    
    def _scan_roll_options(
        self,
        symbol: str,
        current_strike: float,
        option_type: str,
        current_price: float,
        buy_back_cost: float,
        contracts: int,
        indicators,
        max_weeks_out: int,
        max_net_debit: float,
        current_expiration: date = None
    ) -> List[RollOption]:
        """Scan multiple expirations and strikes for roll options."""
        roll_options = []
        
        today = date.today()
        
        # Scan 1 to max_weeks_out
        for weeks in range(1, max_weeks_out + 1):
            # Find Friday of that week
            target_date = today + timedelta(weeks=weeks)
            days_ahead = (4 - target_date.weekday()) % 7
            expiration = target_date + timedelta(days=days_ahead)
            
            # Skip if this expiration is same as or before current expiration
            # (rolling to same week doesn't make sense)
            if current_expiration and expiration <= current_expiration:
                logger.debug(f"Skipping expiration {expiration} - same as or before current {current_expiration}")
                continue
            
            # Get option chain for this expiration
            try:
                chain = self.fetcher.get_option_chain(symbol, expiration)
                if not chain:
                    continue
                
                key = 'calls' if option_type.lower() == 'call' else 'puts'
                options_df = chain.get(key)
                
                if options_df is None or options_df.empty:
                    continue
                
                # Calculate strike range to scan
                # For ITM positions, we need to roll to strikes that get us OTM or closer to ATM
                # For calls: from current strike UP (higher strikes = more OTM)
                # For puts: from current price DOWN (lower strikes = more OTM)
                if option_type.lower() == 'call':
                    min_strike = current_strike  # At least current strike
                    max_strike = current_price * 1.15  # Up to 15% above current price
                else:
                    # For PUTS: Roll DOWN to get OTM
                    # If deep ITM, we need to go significantly lower
                    # Target: ATM or slightly OTM (5-15% below current stock price)
                    min_strike = current_price * 0.85  # Down to 15% below current price
                    # IMPORTANT: For meaningful rolls, max strike should be BELOW current price
                    # to get at least ATM, not at current strike which keeps us ITM
                    max_strike = min(current_strike, current_price * 1.02)  # At most 2% above current price (slightly OTM)
                    
                    # If stock is DEEP below strike (>10% ITM), force rolling to OTM strikes
                    itm_amount = (current_strike - current_price) / current_strike
                    if itm_amount > 0.10:  # >10% ITM
                        max_strike = current_price * 0.98  # Force below current price (OTM territory)
                
                # Filter strikes in range
                valid_strikes = options_df[
                    (options_df['strike'] >= min_strike) & 
                    (options_df['strike'] <= max_strike)
                ]
                
                for _, row in valid_strikes.iterrows():
                    new_strike = row['strike']
                    
                    # Get premium (use mid price)
                    bid = row.get('bid', 0) or 0
                    ask = row.get('ask', 0) or 0
                    
                    if bid > 0 and ask > 0:
                        new_premium = (bid + ask) / 2
                    elif bid > 0:
                        new_premium = bid
                    else:
                        continue  # Skip if no valid price
                    
                    # Calculate net cost
                    net_cost = buy_back_cost - new_premium  # Positive = debit, Negative = credit
                    
                    # Skip if debit is too large
                    if net_cost > max_net_debit:
                        continue
                    
                    # Get delta for probability
                    delta = abs(row.get('delta', 0.3) or 0.3)
                    probability_otm = (1 - delta) * 100
                    
                    # Calculate strike distance
                    if option_type.lower() == 'call':
                        strike_distance_pct = ((new_strike - current_price) / current_price) * 100
                    else:
                        strike_distance_pct = ((current_price - new_strike) / current_price) * 100
                    
                    days_to_expiry = (expiration - today).days
                    
                    # Calculate annualized return if OTM
                    # If we end OTM, we keep the full new premium
                    if net_cost < 0:  # Credit received
                        # Return = credit / capital at risk
                        # Approximate capital at risk as the spread from current price to strike
                        capital_at_risk = abs(new_strike - current_price) * 100
                        if capital_at_risk > 0:
                            raw_return = abs(net_cost) / capital_at_risk
                            annualized_return = raw_return * (365 / days_to_expiry) * 100
                        else:
                            annualized_return = 0
                    else:
                        annualized_return = 0  # Debit = no return
                    
                    roll_option = RollOption(
                        expiration_date=expiration,
                        expiration_weeks=weeks,
                        new_strike=new_strike,
                        buy_back_cost=buy_back_cost,
                        new_premium=new_premium,
                        net_cost=net_cost,
                        net_cost_total=net_cost * 100 * contracts,
                        probability_otm=probability_otm,
                        delta=delta,
                        score=0,  # Will be calculated
                        category='',  # Will be assigned
                        days_to_expiry=days_to_expiry,
                        strike_distance_pct=strike_distance_pct,
                        annualized_return_if_otm=annualized_return
                    )
                    
                    roll_options.append(roll_option)
                    
            except Exception as e:
                logger.warning(f"Error scanning week {weeks} for {symbol}: {e}")
                continue
        
        return roll_options
    
    def _score_options(self, options: List[RollOption], indicators) -> None:
        """
        Score each option based on multiple factors.
        
        Scoring weights:
        - Net Cost: 40% (prefer credits, minimize debits)
        - Time: 20% (prefer shorter, less capital tied up)
        - Safety: 30% (prefer higher probability OTM)
        - TA Adjustment: 10% (adjust based on technical signals)
        """
        if not options:
            return
        
        # Normalize each factor
        net_costs = [o.net_cost for o in options]
        days_list = [o.days_to_expiry for o in options]
        prob_otm_list = [o.probability_otm for o in options]
        
        min_cost, max_cost = min(net_costs), max(net_costs)
        min_days, max_days = min(days_list), max(days_list)
        min_prob, max_prob = min(prob_otm_list), max(prob_otm_list)
        
        cost_range = max_cost - min_cost if max_cost != min_cost else 1
        days_range = max_days - min_days if max_days != min_days else 1
        prob_range = max_prob - min_prob if max_prob != min_prob else 1
        
        # Technical analysis adjustments
        # If RSI > 70 (overbought), can be more aggressive (expect pullback)
        # If RSI < 30 (oversold), be more conservative (expect bounce up)
        ta_aggression_bonus = 0
        if indicators.rsi_14 > 70:
            ta_aggression_bonus = 0.1  # Bonus for aggressive options
        elif indicators.rsi_14 < 30:
            ta_aggression_bonus = -0.1  # Penalty for aggressive options
        
        for option in options:
            # Cost score: lower (more negative) is better
            # Transform so credits (negative) get high score
            cost_score = 1 - (option.net_cost - min_cost) / cost_range
            
            # Time score: shorter is better
            time_score = 1 - (option.days_to_expiry - min_days) / days_range
            
            # Safety score: higher probability OTM is better
            safety_score = (option.probability_otm - min_prob) / prob_range
            
            # Base score
            base_score = (
                0.40 * cost_score +
                0.20 * time_score +
                0.30 * safety_score
            )
            
            # TA adjustment (aggressive options get bonus/penalty based on RSI)
            # Aggressive = low probability OTM
            aggression_level = 1 - safety_score  # Higher = more aggressive
            ta_adjustment = ta_aggression_bonus * aggression_level * 0.10
            
            option.score = base_score + ta_adjustment
    
    def _select_top_options(
        self, 
        options: List[RollOption]
    ) -> Tuple[Optional[RollOption], Optional[RollOption], Optional[RollOption]]:
        """
        Select top 3 options by category.
        
        Conservative: Highest probability OTM, even if more costly/longer
        Moderate: Best overall balance
        Aggressive: Shortest time, lowest cost, even if riskier
        """
        if not options:
            return None, None, None
        
        # Sort by different criteria for each category
        
        # Conservative: Prioritize safety (probability OTM)
        by_safety = sorted(options, key=lambda x: -x.probability_otm)
        conservative = by_safety[0] if by_safety else None
        if conservative:
            conservative.category = 'conservative'
        
        # Aggressive: Prioritize low cost and short time
        by_aggressive = sorted(options, key=lambda x: (x.net_cost, x.days_to_expiry))
        aggressive = by_aggressive[0] if by_aggressive else None
        if aggressive:
            aggressive.category = 'aggressive'
        
        # Moderate: Best overall score (but not the same as conservative or aggressive)
        by_score = sorted(options, key=lambda x: -x.score)
        moderate = None
        for opt in by_score:
            if opt != conservative and opt != aggressive:
                moderate = opt
                break
        if moderate:
            moderate.category = 'moderate'
        else:
            # If we only have 2 or fewer unique options
            moderate = by_score[0] if by_score else None
            if moderate:
                moderate.category = 'moderate'
        
        return conservative, moderate, aggressive
    
    def _summarize_technical_signals(self, indicators, itm_pct: float) -> Dict[str, Any]:
        """Summarize technical signals relevant to the roll decision."""
        signals = {
            "rsi": round(indicators.rsi_14, 1),
            "rsi_signal": "overbought" if indicators.rsi_14 > 70 else "oversold" if indicators.rsi_14 < 30 else "neutral",
            "trend": indicators.trend,
            "weekly_volatility_pct": round(indicators.weekly_volatility * 100, 2),
            "current_price": indicators.current_price,
            "itm_percent": round(itm_pct, 1),
        }
        
        # Add support/resistance if available
        if indicators.nearest_support:
            signals["nearest_support"] = indicators.nearest_support
        if indicators.nearest_resistance:
            signals["nearest_resistance"] = indicators.nearest_resistance
        
        # Recommendation based on signals
        if indicators.rsi_14 > 70:
            signals["ta_recommendation"] = "Stock is overbought - may pull back. Consider moderate/aggressive roll."
        elif indicators.rsi_14 < 30:
            signals["ta_recommendation"] = "Stock is oversold - may bounce higher. Consider conservative roll."
        elif indicators.trend == "bullish":
            signals["ta_recommendation"] = "Strong uptrend - be conservative, go further out."
        else:
            signals["ta_recommendation"] = "Mixed signals - moderate approach recommended."
        
        return signals
    
    def _generate_summary(
        self,
        conservative: Optional[RollOption],
        moderate: Optional[RollOption],
        aggressive: Optional[RollOption],
        itm_pct: float,
        buy_back_cost: float,
        tech_signals: Dict[str, Any]
    ) -> str:
        """Generate a human-readable summary of the analysis."""
        parts = [f"Position is {itm_pct:.1f}% ITM. Buy-back cost: ${buy_back_cost:.2f}/share."]
        
        if tech_signals.get("ta_recommendation"):
            parts.append(tech_signals["ta_recommendation"])
        
        # Highlight the moderate option as default recommendation
        if moderate:
            net_str = f"${abs(moderate.net_cost):.2f} {'credit' if moderate.net_cost < 0 else 'debit'}"
            parts.append(
                f"Recommended: Roll to {moderate.expiration_date.strftime('%b %d')} "
                f"${moderate.new_strike:.0f} strike ({moderate.probability_otm:.0f}% prob OTM, "
                f"{net_str}/share)"
            )
        
        return " ".join(parts)


def get_itm_roll_optimizer() -> ITMRollOptimizer:
    """Factory function to get an ITMRollOptimizer instance."""
    return ITMRollOptimizer()


