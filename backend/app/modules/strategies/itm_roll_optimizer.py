"""
ITM Roll Optimizer

V3.0 ENHANCED: Find zero-cost roll within 52 weeks.

When a position goes In The Money (ITM), this optimizer:
1. Scans expirations from 1 week to 52 weeks
2. Finds SHORTEST duration achieving zero-cost (≤20% of original premium)
3. Uses Delta 30 (70% OTM probability) for ITM escapes per V3 Addendum
4. Returns top 3 options: Conservative, Moderate, Aggressive

V3 Changes:
- Increased max_weeks_out from 6 to 52 (1 year)
- Uses Delta 30 instead of Delta 10 for ITM escapes
- Simplified cost rule: max debit = 20% of original premium
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
    
    # V3.1 FIX: Track whether OTM escape is achievable
    can_escape_to_otm: bool = False  # True if any option achieves OTM (>50% prob OTM)
    is_catastrophic: bool = False  # True if no viable escape to OTM within 52 weeks
    best_otm_option: Optional[RollOption] = None  # Best OTM option (even if expensive)
    min_debit_for_otm: Optional[float] = None  # Minimum debit required to reach OTM


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
        max_weeks_out: int = 52,  # V3: Up to 52 weeks (1 year)
        max_net_debit: float = 5.0,  # V3: Should be 20% of original premium
        delta_target: float = 0.70  # V3 Addendum: Delta 30 for ITM escapes
    ) -> Optional[ITMRollAnalysis]:
        """
        V3 ENHANCED: Analyze an ITM position and generate roll options.
        
        V3 Strategy:
        - Scan up to 52 weeks (not just 6) to find zero-cost escape
        - Use max_net_debit = 20% of original premium
        - Use Delta 30 (probability_target=0.70) for ITM escapes
        - Return SHORTEST duration achieving zero-cost
        
        Args:
            symbol: Stock symbol
            current_strike: Current option strike price
            option_type: 'call' or 'put'
            current_expiration: Current option expiration date
            contracts: Number of contracts
            account_name: Account name for context
            max_weeks_out: Maximum weeks to consider (V3 default: 52)
            max_net_debit: Maximum acceptable net debit per share (V3: 20% of original premium)
            delta_target: V3 Addendum - probability OTM target
                          0.70 (Delta 30) for ITM escapes
                          0.90 (Delta 10) for weekly rolls
            
        Returns:
            ITMRollAnalysis with top 3 roll options, or None if no viable rolls
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
                current_expiration=current_expiration,  # Pass current expiration to skip same-week rolls
                delta_target=delta_target  # V3 Addendum: Use specified delta target
            )
            
            if not roll_options:
                logger.warning(f"No valid roll options found for {symbol}")
                return None
            
            # V3.1 FIX: Analyze whether OTM escape is achievable
            # OTM = probability_otm > 50% (more likely to stay OTM than go ITM)
            otm_options = [opt for opt in roll_options if opt.probability_otm > 50]
            can_escape_to_otm = len(otm_options) > 0
            
            # Find the best OTM option (highest probability OTM within cost constraints)
            best_otm_option = None
            if otm_options:
                best_otm_option = max(otm_options, key=lambda x: x.probability_otm)
            
            # Calculate minimum debit required to reach any OTM strike
            # Look at ALL options, even those filtered out for cost
            min_debit_for_otm = None
            if option_type.lower() == 'call':
                # For calls, OTM means strike > current_price
                otm_threshold = current_price
            else:
                # For puts, OTM means strike < current_price
                otm_threshold = current_price
            
            for opt in roll_options:
                is_otm = (option_type.lower() == 'call' and opt.new_strike > current_price) or \
                         (option_type.lower() == 'put' and opt.new_strike < current_price)
                if is_otm:
                    if min_debit_for_otm is None or opt.net_cost < min_debit_for_otm:
                        min_debit_for_otm = opt.net_cost
            
            # V3.1 FIX: Determine if position is CATASTROPHIC
            # Catastrophic = deep ITM (>15%) AND cannot escape to OTM within cost constraints
            is_catastrophic = False
            if itm_pct > 15 and not can_escape_to_otm:
                is_catastrophic = True
                logger.warning(
                    f"[CATASTROPHIC] {symbol}: {itm_pct:.1f}% ITM, no OTM escape possible. "
                    f"Best probability OTM: {max(opt.probability_otm for opt in roll_options):.0f}%"
                )
            
            # Score and categorize options
            self._score_options(roll_options, indicators)
            
            # Select top 3 by category
            conservative, moderate, aggressive = self._select_top_options(roll_options)
            
            # V3.1 FIX: If catastrophic, override the recommendation
            if is_catastrophic:
                # For catastrophic positions, prioritize the option with highest probability OTM
                # even if it's still <50% probability
                by_prob_otm = sorted(roll_options, key=lambda x: -x.probability_otm)
                if by_prob_otm:
                    # Use the highest prob OTM as conservative (might still be ITM but best we can do)
                    conservative = by_prob_otm[0]
                    conservative.category = 'conservative'
            
            # Build technical signals summary
            tech_signals = self._summarize_technical_signals(indicators, itm_pct)
            
            # Generate recommendation summary
            summary = self._generate_summary(
                conservative, moderate, aggressive, 
                itm_pct, buy_back_cost, tech_signals
            )
            
            # V3.1 FIX: Add catastrophic warning to summary
            if is_catastrophic:
                summary = (
                    f"⚠️ CATASTROPHIC: Position is {itm_pct:.1f}% ITM. "
                    f"No OTM escape possible within cost constraints. "
                    f"Consider CLOSING position. " + summary
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
                recommendation_summary=summary,
                can_escape_to_otm=can_escape_to_otm,
                is_catastrophic=is_catastrophic,
                best_otm_option=best_otm_option,
                min_debit_for_otm=min_debit_for_otm
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
        current_expiration: date = None,
        delta_target: float = 0.70  # V3 Addendum: Delta 30 for ITM escapes
    ) -> List[RollOption]:
        """
        V3.1 FIX: Scan for ITM escape options, prioritizing OTM strikes.
        
        FIXED: Now anchors to CURRENT STOCK PRICE, not current strike.
        The goal is to ESCAPE ITM by reaching an OTM strike (Delta 30).
        
        Algorithm:
        1. Calculate the Delta 30 target strike (should be OTM)
        2. For each expiration, check if we can afford to reach OTM
        3. Include both OTM and improved-ITM options for comparison
        4. Flag whether OTM escape is achievable
        
        Scans in batches for efficiency when searching up to 52 weeks:
        - Weeks 1-4: Check every week
        - Weeks 6-12: Check every 2 weeks  
        - Weeks 16-52: Check every 4 weeks
        """
        roll_options = []
        
        today = date.today()
        
        # V3: Scan schedule for efficiency (up to 52 weeks)
        scan_weeks = [1, 2, 3, 4]
        if max_weeks_out > 4:
            scan_weeks.extend([6, 8])
        if max_weeks_out > 8:
            scan_weeks.extend([12])
        if max_weeks_out > 12:
            scan_weeks.extend([16, 24])
        if max_weeks_out > 24:
            scan_weeks.extend([36, 52])
        
        # Filter to max_weeks_out
        scan_weeks = [w for w in scan_weeks if w <= max_weeks_out]
        
        for weeks in scan_weeks:
            # Find Friday of that week
            target_date = today + timedelta(weeks=weeks)
            days_ahead = (4 - target_date.weekday()) % 7
            expiration = target_date + timedelta(days=days_ahead)
            
            # Skip if this expiration is same as or before current expiration
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
                
                # V3.1 FIX: Calculate target strike based on CURRENT STOCK PRICE
                # The goal is to reach an OTM strike, not just improve slightly
                strike_rec = self.ta_service.recommend_strike_price(
                    symbol=symbol,
                    option_type=option_type,
                    expiration_weeks=weeks,
                    probability_target=delta_target
                )
                
                if strike_rec:
                    target_strike = strike_rec.recommended_strike
                else:
                    # Fallback: estimate Delta 30 strike based on stock price
                    # For CALLS: Delta 30 = strike ~3-5% ABOVE current price
                    # For PUTS: Delta 30 = strike ~3-5% BELOW current price
                    if option_type.lower() == 'call':
                        target_strike = current_price * 1.04  # ~4% OTM
                    else:
                        target_strike = current_price * 0.96  # ~4% OTM
                
                # V3.1 FIX: Strike range now anchored to CURRENT STOCK PRICE
                # We want to find strikes from current price outward to OTM
                if option_type.lower() == 'call':
                    # For CALLS: Look at strikes from ATM to well OTM
                    # We'll include some ITM strikes too to show the cost difference
                    min_strike = current_price * 0.95  # Slightly ITM for comparison
                    max_strike = current_price * 1.15  # Well OTM
                    
                    # Log the target for debugging
                    logger.info(
                        f"[ITM_FIX] {symbol}: Stock ${current_price:.0f}, "
                        f"Target OTM strike: ${target_strike:.0f}, "
                        f"Scanning range: ${min_strike:.0f}-${max_strike:.0f}"
                    )
                else:
                    # For PUTS: Look at strikes from ATM to well OTM (below price)
                    min_strike = current_price * 0.85  # Well OTM
                    max_strike = current_price * 1.05  # Slightly ITM for comparison
                
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


