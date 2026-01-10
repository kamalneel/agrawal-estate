"""
Strategy Service

V3: Uses unified PositionEvaluator for options positions.
Other strategies (earnings_alert, new_covered_call) still run separately.

Manages strategy configurations and generates recommendations using enabled strategies.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.modules.strategies.models import StrategyConfig as StrategyConfigModel
from app.modules.strategies.strategy_base import StrategyConfig, BaseStrategy
from app.modules.strategies.recommendations import StrategyRecommendation
from app.modules.strategies.strategies import STRATEGY_REGISTRY

# V3 imports
from app.modules.strategies.position_evaluator import (
    PositionEvaluator, 
    EvaluationResult,
    SmartScanFilter,
    get_position_evaluator,
    get_scan_filter
)
from app.modules.strategies.option_monitor import get_positions_from_db


class StrategyService:
    """Service for managing and executing strategies."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_all_strategy_configs(self) -> List[StrategyConfig]:
        """Get all strategy configurations from database."""
        configs = self.db.query(StrategyConfigModel).all()
        
        result = []
        for config in configs:
            result.append(StrategyConfig(
                strategy_type=config.strategy_type,
                name=config.name,
                description=config.description or "",
                category=config.category,
                enabled=config.enabled,
                notification_enabled=config.notification_enabled,
                notification_priority_threshold=config.notification_priority_threshold or "high",
                parameters=config.parameters or {}
            ))
        
        return result
    
    def get_strategy_config(self, strategy_type: str) -> Optional[StrategyConfig]:
        """Get configuration for a specific strategy."""
        config = self.db.query(StrategyConfigModel).filter(
            StrategyConfigModel.strategy_type == strategy_type
        ).first()
        
        if not config:
            return None
        
        return StrategyConfig(
            strategy_type=config.strategy_type,
            name=config.name,
            description=config.description or "",
            category=config.category,
            enabled=config.enabled,
            notification_enabled=config.notification_enabled,
            notification_priority_threshold=config.notification_priority_threshold or "high",
            parameters=config.parameters or {}
        )
    
    def update_strategy_config(
        self,
        strategy_type: str,
        enabled: Optional[bool] = None,
        notification_enabled: Optional[bool] = None,
        notification_priority_threshold: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> StrategyConfig:
        """Update strategy configuration."""
        config = self.db.query(StrategyConfigModel).filter(
            StrategyConfigModel.strategy_type == strategy_type
        ).first()
        
        if not config:
            raise ValueError(f"Strategy {strategy_type} not found")
        
        if enabled is not None:
            config.enabled = enabled
        if notification_enabled is not None:
            config.notification_enabled = notification_enabled
        if notification_priority_threshold is not None:
            config.notification_priority_threshold = notification_priority_threshold
        if parameters is not None:
            # Merge with existing parameters
            existing = config.parameters or {}
            existing.update(parameters)
            config.parameters = existing
        
        self.db.commit()
        self.db.refresh(config)
        
        return StrategyConfig(
            strategy_type=config.strategy_type,
            name=config.name,
            description=config.description or "",
            category=config.category,
            enabled=config.enabled,
            notification_enabled=config.notification_enabled,
            notification_priority_threshold=config.notification_priority_threshold or "high",
            parameters=config.parameters or {}
        )
    
    def get_enabled_strategies(self) -> List[BaseStrategy]:
        """Get all enabled strategy instances."""
        configs = self.db.query(StrategyConfigModel).filter(
            StrategyConfigModel.enabled == True
        ).all()
        
        strategies = []
        for config in configs:
            strategy_class = STRATEGY_REGISTRY.get(config.strategy_type)
            if strategy_class:
                strategy_config = StrategyConfig(
                    strategy_type=config.strategy_type,
                    name=config.name,
                    description=config.description or "",
                    category=config.category,
                    enabled=config.enabled,
                    notification_enabled=config.notification_enabled,
                    notification_priority_threshold=config.notification_priority_threshold or "high",
                    parameters=config.parameters or {}
                )
                strategies.append(strategy_class(self.db, strategy_config))
        
        return strategies
    
    def generate_recommendations(
        self,
        params: Optional[Dict[str, Any]] = None
    ) -> List[StrategyRecommendation]:
        """
        Generate recommendations using all enabled strategies.
        
        V3: Uses unified PositionEvaluator for options positions.
        
        Args:
            params: Global parameters (like default_premium, etc.)
        
        Returns:
            List of recommendations from all enabled strategies (deduplicated)
        """
        if params is None:
            params = {}
        
        import logging
        logger = logging.getLogger(__name__)
        
        # =====================================================================
        # V3: Use unified PositionEvaluator instead of multiple strategies
        # =====================================================================
        from app.modules.strategies.algorithm_config import ALGORITHM_VERSION
        
        if ALGORITHM_VERSION.lower() == 'v3':
            logger.info("V3 MODE: Using unified PositionEvaluator")
            return self.generate_v3_recommendations(params)
        
        # =====================================================================
        # V1/V2: Legacy mode - run multiple strategies (DEPRECATED)
        # =====================================================================
        logger.info(f"LEGACY MODE ({ALGORITHM_VERSION}): Running multiple strategies")
        
        all_recommendations = []
        enabled_strategies = self.get_enabled_strategies()
        
        logger.info(f"Generating recommendations using {len(enabled_strategies)} enabled strategies")
        
        # Check if today is Triple Witching Day (V2 feature)
        from app.modules.strategies.algorithm_config import is_feature_enabled
        is_triple_witching_enabled = is_feature_enabled("triple_witching")
        is_triple_witching_day = False
        
        if is_triple_witching_enabled:
            from app.modules.strategies.strategies.triple_witching_handler import is_triple_witching
            is_triple_witching_day = is_triple_witching()
            if is_triple_witching_day:
                logger.warning("🔴 TRIPLE WITCHING DAY DETECTED - Applying special handling")
        
        for strategy in enabled_strategies:
            try:
                logger.info(f"Running strategy: {strategy.strategy_type} ({strategy.name})")
                recommendations = strategy.generate_recommendations(params)
                logger.info(f"Strategy {strategy.strategy_type} generated {len(recommendations)} recommendations")
                all_recommendations.extend(recommendations)
            except Exception as e:
                # Log error but continue with other strategies
                logger.error(f"Error generating recommendations for {strategy.strategy_type}: {e}", exc_info=True)
        
        # Apply Triple Witching overrides if it's Triple Witching Day
        if is_triple_witching_day and is_triple_witching_enabled:
            from app.modules.strategies.strategies.triple_witching_handler import apply_triple_witching_overrides
            logger.info(f"Applying Triple Witching overrides to {len(all_recommendations)} recommendations")
            
            # Convert recommendations to dicts for override, then back
            modified_recommendations = []
            for rec in all_recommendations:
                # Convert to dict for modification
                rec_dict = rec.model_dump() if hasattr(rec, 'model_dump') else rec.dict()
                
                # Apply overrides
                modified = apply_triple_witching_overrides(rec_dict, None)
                
                # If the override changed the action, log it
                if modified.get('triple_witching_override'):
                    override = modified.get('triple_witching_override', {})
                    logger.info(f"Triple Witching override for {rec.symbol}: {override.get('reason', 'N/A')}")
                
                # Create new recommendation with modified data
                modified_rec = StrategyRecommendation(**modified)
                modified_recommendations.append(modified_rec)
            
            all_recommendations = modified_recommendations
        
        # Log summary before deduplication
        by_type_before = {}
        for rec in all_recommendations:
            rec_type = rec.type
            by_type_before[rec_type] = by_type_before.get(rec_type, 0) + 1
        logger.info(f"Recommendations before deduplication by type: {by_type_before}")
        
        # Deduplicate recommendations for the same position
        deduped = self._deduplicate_by_position(all_recommendations)
        
        # Log summary after deduplication
        by_type_after = {}
        for rec in deduped:
            rec_type = rec.type
            by_type_after[rec_type] = by_type_after.get(rec_type, 0) + 1
        logger.info(f"Recommendations after deduplication by type: {by_type_after}")
        
        # Sort by priority
        prioritized = self._prioritize(deduped)
        
        # Log final summary
        by_type_final = {}
        for rec in prioritized:
            rec_type = rec.type
            by_type_final[rec_type] = by_type_final.get(rec_type, 0) + 1
        logger.info(f"Final recommendations by type: {by_type_final} (total: {len(prioritized)})")
        
        return prioritized
    
    def _deduplicate_by_position(
        self,
        recommendations: List[StrategyRecommendation]
    ) -> List[StrategyRecommendation]:
        """
        Deduplicate recommendations for the same option position.
        
        If multiple strategies recommend action on the same position (symbol + strike + 
        expiration + account), merge them into a single recommendation.
        
        Priority order for merging:
        1. close_early_opportunity (has volatility risk context)
        2. early_roll_opportunity (has roll context)
        3. roll_options (ITM rolls)
        4. Others
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Group by position key
        by_position: Dict[str, List[StrategyRecommendation]] = {}
        other_recs: List[StrategyRecommendation] = []  # Recs without position context
        
        for rec in recommendations:
            ctx = rec.context or {}
            symbol = ctx.get("symbol")
            strike = ctx.get("strike_price")
            expiration = ctx.get("expiration_date")
            account = ctx.get("account") or ctx.get("account_name") or rec.account_name
            
            # For bull put spreads, use sell_strike and buy_strike instead of single strike
            if rec.type in ["bull_put_spread", "mega_cap_bull_put"]:
                sell_strike = ctx.get("sell_strike")
                buy_strike = ctx.get("buy_strike")
                if symbol and sell_strike and buy_strike and expiration:
                    # Use both strikes for bull put spreads
                    # Note: If both strategies find the same strikes/expiration for same symbol, they'll be deduplicated
                    # The preference logic below will choose bull_put_spread if symbol is in portfolio
                    key = f"bull_put_{symbol}_{sell_strike}_{buy_strike}_{expiration}"
                    if key not in by_position:
                        by_position[key] = []
                    by_position[key].append(rec)
                else:
                    other_recs.append(rec)
            elif symbol and strike and expiration:
                # Standard position-based recommendations
                key = f"{symbol}_{strike}_{expiration}_{account or 'none'}"
                if key not in by_position:
                    by_position[key] = []
                by_position[key].append(rec)
            else:
                other_recs.append(rec)
        
        # Get portfolio symbols for preference logic (across ALL accounts)
        portfolio_symbols = set()
        try:
            from app.modules.investments.services import get_all_holdings
            holdings_data = get_all_holdings(self.db)
            logger.info(f"Deduplication: Checking portfolio symbols across {len(holdings_data)} accounts")
            for account in holdings_data:
                for holding in account.get('holdings', []):
                    symbol = holding.get('symbol')
                    if symbol and symbol != 'CASH':
                        portfolio_symbols.add(symbol)
            logger.info(f"Deduplication: Found {len(portfolio_symbols)} unique portfolio symbols: {sorted(portfolio_symbols)}")
        except Exception as e:
            logger.warning(f"Could not get portfolio symbols for deduplication: {e}", exc_info=True)
        
        # Merge duplicates
        deduped = []
        strategy_priority = {
            "close_early_opportunity": 1,  # Has volatility risk - most actionable
            "early_roll_opportunity": 2,   # Has roll suggestion
            "roll_options": 3,             # ITM roll with options
        }
        
        def get_sort_key(rec: StrategyRecommendation) -> tuple:
            """Get sort key for recommendations: (priority, is_portfolio_strategy, is_portfolio_symbol)"""
            ctx = rec.context or {}
            symbol = ctx.get("symbol", "")
            is_portfolio_symbol = symbol in portfolio_symbols
            is_portfolio_strategy = rec.type == "bull_put_spread"
            
            # Priority order:
            # 1. Strategy priority (lower is better)
            # 2. If symbol is in portfolio, prefer bull_put_spread over mega_cap_bull_put
            # 3. Otherwise, keep original order
            priority = strategy_priority.get(rec.type, 99)
            
            # For bull put strategies, if symbol is in portfolio, prefer bull_put_spread
            if rec.type in ["bull_put_spread", "mega_cap_bull_put"] and is_portfolio_symbol:
                if is_portfolio_strategy:
                    # bull_put_spread for portfolio symbol gets priority
                    return (priority, 0, True)
                else:
                    # mega_cap_bull_put for portfolio symbol should be deprioritized
                    return (priority, 1, True)
            
            return (priority, 99, is_portfolio_symbol)
        
        for key, recs in by_position.items():
            if len(recs) == 1:
                deduped.append(recs[0])
            else:
                # Multiple strategies for same position - merge them
                logger.info(f"Deduping {len(recs)} recommendations for position: {key}")
                
                # Sort by strategy priority, preferring portfolio strategies for portfolio symbols
                recs.sort(key=get_sort_key)
                
                # Take the primary recommendation (highest priority strategy)
                primary = recs[0]
                
                # Log which strategy was chosen and why
                if len(recs) > 1:
                    ctx = primary.context or {}
                    symbol = ctx.get("symbol", "")
                    if symbol in portfolio_symbols and primary.type == "mega_cap_bull_put":
                        logger.warning(f"Chose mega_cap_bull_put for {symbol} even though it's in portfolio - bull_put_spread may not have found opportunity")
                    elif symbol in portfolio_symbols and primary.type == "bull_put_spread":
                        logger.info(f"Chose bull_put_spread for {symbol} (portfolio symbol) over mega_cap_bull_put")
                
                # Merge context from other recommendations
                merged_types = [r.type for r in recs]
                
                # If we have both close_early and early_roll, update the description
                # to clarify the action is "close and roll"
                if "close_early_opportunity" in merged_types and "early_roll_opportunity" in merged_types:
                    # Get roll context from early_roll recommendation
                    roll_rec = next((r for r in recs if r.type == "early_roll_opportunity"), None)
                    roll_ctx = roll_rec.context if roll_rec else {}
                    
                    # Get close context  
                    close_rec = next((r for r in recs if r.type == "close_early_opportunity"), None)
                    close_ctx = close_rec.context if close_rec else {}
                    
                    # Use close context for current position, roll context for new position
                    ctx = primary.context or {}
                    contracts = ctx.get("contracts", 1)
                    symbol = ctx.get("symbol", "")
                    strike = ctx.get("strike_price", "")
                    opt_type = ctx.get("option_type", "call")
                    profit_pct = ctx.get("profit_percent", 0)
                    current_premium = ctx.get("current_premium", 0)
                    
                    # Roll details from early_roll context
                    new_strike = roll_ctx.get("new_strike", strike)
                    new_expiration = roll_ctx.get("new_expiration", "")
                    estimated_total_income = roll_ctx.get("estimated_total_income", 0)
                    current_exp = ctx.get("expiration_date", "")
                    
                    # Format dates as MM/DD
                    try:
                        from datetime import datetime as dt
                        current_exp_str = dt.fromisoformat(current_exp).strftime("%-m/%d") if current_exp else ""
                        new_exp_str = dt.fromisoformat(new_expiration).strftime("%-m/%d") if new_expiration else "next week"
                    except:
                        current_exp_str = current_exp[:5] if current_exp else ""
                        new_exp_str = new_expiration[:5] if new_expiration else "next week"
                    
                    # Title per user's format:
                    # "Close & Roll 7 TSLA $490 (12/12) → $490 (12/19) - Earn ~$1122"
                    title = (
                        f"Close & Roll {contracts} {symbol} ${strike} ({current_exp_str}) → "
                        f"${new_strike} ({new_exp_str}) - Earn ~${estimated_total_income:.0f}"
                    )
                    
                    description = f"Close at ${current_premium:.2f} to lock {profit_pct:.0f}% profit, roll to ${new_strike} for {new_exp_str}."
                    
                    action = f"Buy to close ${strike} at ${current_premium:.2f}, sell ${new_strike} {opt_type} for {new_exp_str}"
                    
                    # Create merged recommendation
                    primary = StrategyRecommendation(
                        id=primary.id,
                        type="close_and_roll",  # New merged type
                        category="optimization",
                        priority=primary.priority,
                        title=title,
                        description=description,
                        rationale=primary.rationale,
                        action=action,
                        action_type="roll",
                        potential_income=estimated_total_income,
                        potential_risk=primary.potential_risk,
                        time_horizon="immediate",
                        symbol=primary.symbol,
                        account_name=primary.account_name,
                        context={
                            **primary.context,
                            **roll_ctx,
                            "merged_from": merged_types,
                        },
                        expires_at=primary.expires_at
                    )
                    
                    logger.info(f"Merged close_early + early_roll into close_and_roll for {symbol} ${strike}")
                
                deduped.append(primary)
        
        # Add back non-position recommendations
        deduped.extend(other_recs)
        
        return deduped
    
    def _prioritize(
        self,
        recommendations: List[StrategyRecommendation]
    ) -> List[StrategyRecommendation]:
        """
        Sort recommendations by account order, then by priority within each account.
        
        Account order (as specified):
        1. Neel's Brokerage (Investment)
        2. Neel's IRA (Retirement)
        3. Neel's Roth IRA
        4. Jaya's Brokerage (Investment)
        5. Jaya's IRA
        6. Jaya's Roth IRA
        7. Alicia's accounts
        8. Unknown/Other
        """
        # Account order - match partial names for flexibility
        def get_account_order(account_name: str) -> int:
            if not account_name:
                return 99
            name_lower = account_name.lower()
            
            # Neel's accounts (1-3)
            if "neel" in name_lower:
                if "roth" in name_lower:
                    return 3  # Neel's Roth IRA
                elif "ira" in name_lower or "retirement" in name_lower:
                    return 2  # Neel's IRA/Retirement
                else:
                    return 1  # Neel's Brokerage/Investment
            
            # Jaya's accounts (4-6)
            elif "jaya" in name_lower:
                if "roth" in name_lower:
                    return 6  # Jaya's Roth IRA
                elif "ira" in name_lower:
                    return 5  # Jaya's IRA
                else:
                    return 4  # Jaya's Brokerage/Investment
            
            # Alicia's accounts (7)
            elif "alicia" in name_lower:
                return 7
            
            return 99  # Unknown
        
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        
        return sorted(
            recommendations,
            key=lambda r: (
                get_account_order(r.account_name),  # Account order first
                priority_order.get(r.priority, 99),  # Then priority
                -(r.potential_income or 0),  # Higher income first
                r.created_at  # Older first for same priority
            )
        )
    
    def get_strategy_info(self, strategy_type: str) -> Optional[Dict[str, Any]]:
        """Get information about a strategy including its default parameters."""
        strategy_class = STRATEGY_REGISTRY.get(strategy_type)
        if not strategy_class:
            return None
        
        # Create a temporary instance to get defaults
        temp_config = StrategyConfig(
            strategy_type=strategy_type,
            name=strategy_class.name,
            description=strategy_class.description,
            category=strategy_class.category,
            parameters={}
        )
        
        return {
            "strategy_type": strategy_type,
            "name": strategy_class.name,
            "description": strategy_class.description,
            "category": strategy_class.category,
            "default_parameters": strategy_class.default_parameters
        }
    
    # =========================================================================
    # V3 UNIFIED POSITION EVALUATOR
    # =========================================================================
    
    def generate_v3_recommendations(
        self,
        params: Optional[Dict[str, Any]] = None
    ) -> List[StrategyRecommendation]:
        """
        V3 Unified recommendation generation.
        
        Uses PositionEvaluator for all options positions:
        - ONE recommendation per position
        - Priority: Pull-back > ITM > Profitable > No Action
        - Cost-neutral rolls (≤20% of original premium)
        - No race conditions
        
        Other strategies (earnings_alert, new_covered_call, etc.) still run separately.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if params is None:
            params = {}
        
        all_recommendations: List[StrategyRecommendation] = []
        
        # Get SmartScanFilter to prevent duplicates
        scan_filter = get_scan_filter()
        
        # =====================================================================
        # STEP 1: Evaluate all options positions with V3 PositionEvaluator
        # =====================================================================
        logger.info("V3: Running unified PositionEvaluator for all options positions")
        
        try:
            positions = get_positions_from_db(self.db)
            logger.info(f"V3: Found {len(positions)} open positions to evaluate")
            
            evaluator = get_position_evaluator()
            
            for position in positions:
                try:
                    result = evaluator.evaluate(position)
                    
                    if result:
                        # Check if we should send (not a duplicate)
                        position_id = f"{position.symbol}_{position.strike_price}_{position.expiration_date}"
                        if scan_filter.should_send(position_id, result):
                            rec = self._convert_evaluation_to_recommendation(result, position)
                            if rec:
                                all_recommendations.append(rec)
                                logger.info(f"V3: {position.symbol} - {result.action} (priority: {result.priority})")
                        else:
                            logger.debug(f"V3: Filtered duplicate for {position.symbol}")
                    else:
                        logger.debug(f"V3: No action for {position.symbol} ${position.strike_price}")
                        
                except Exception as e:
                    logger.error(f"V3: Error evaluating {position.symbol}: {e}", exc_info=True)
            
            logger.info(f"V3: Generated {len(all_recommendations)} position recommendations")
            
        except Exception as e:
            logger.error(f"V3: Error getting positions: {e}", exc_info=True)
        
        # =====================================================================
        # STEP 2: Run non-position strategies (earnings, new_covered_call, etc.)
        # =====================================================================
        # These strategies don't evaluate individual positions, so they run separately
        non_position_strategies = [
            'earnings_alert',
            'new_covered_call',  # Handles both WAIT and SELL for uncovered positions
            # 'sell_unsold_contracts',  # DISABLED: Redundant - new_covered_call now does this with TA
            'diversification',
            'triple_witching_handler',
            'cash_secured_put',  # V3.4: Put selling recommendations based on TA
        ]
        
        enabled_strategies = self.get_enabled_strategies()
        for strategy in enabled_strategies:
            if strategy.strategy_type in non_position_strategies:
                try:
                    logger.info(f"V3: Running supplementary strategy: {strategy.strategy_type}")
                    recs = strategy.generate_recommendations(params)
                    all_recommendations.extend(recs)
                    logger.info(f"V3: {strategy.strategy_type} generated {len(recs)} recommendations")
                except Exception as e:
                    logger.error(f"V3: Error in {strategy.strategy_type}: {e}", exc_info=True)
        
        # =====================================================================
        # STEP 3: Sort by priority
        # =====================================================================
        prioritized = self._prioritize(all_recommendations)
        
        logger.info(f"V3: Total recommendations: {len(prioritized)}")
        return prioritized
    
    def _convert_evaluation_to_recommendation(
        self,
        result: EvaluationResult,
        position
    ) -> Optional[StrategyRecommendation]:
        """
        Convert V3 EvaluationResult to StrategyRecommendation.
        """
        from datetime import datetime, timedelta
        
        # Map action to strategy type
        action_to_type = {
            'PULL_BACK': 'roll_options',
            'ROLL_ITM': 'roll_options',
            'ROLL_WEEKLY': 'roll_options',
            'CLOSE_CATASTROPHIC': 'roll_options',
            'NEAR_ITM_WARNING': 'roll_options',
            'EXDIV_TOMORROW': 'roll_options',
            'EXDIV_ASSIGNMENT_RISK': 'roll_options',
            'TRIPLE_WITCHING_TOMORROW': 'roll_options',
            'TRIPLE_WITCHING_EXPIRY': 'roll_options',
        }
        
        strategy_type = action_to_type.get(result.action, 'roll_options')
        
        # Build title based on action
        if result.action == 'PULL_BACK':
            pb_data = result.pull_back_data or {}
            title = (
                f"PULL BACK {position.symbol} ${position.strike_price} - "
                f"{pb_data.get('from_weeks', '?')}wk → {pb_data.get('to_weeks', '?')}wk"
            )
            action_type = 'roll'
            
        elif result.action == 'ROLL_ITM':
            zc_data = result.zero_cost_data or {}
            net_str = f"${abs(result.net_cost):.2f} {'credit' if result.net_cost < 0 else 'debit'}" if result.net_cost else ""
            title = (
                f"ROLL ITM {position.symbol} ${position.strike_price}→${result.new_strike:.0f} "
                f"({zc_data.get('weeks_out', '?')}wk, {net_str})"
            )
            action_type = 'roll'
            
        elif result.action == 'ROLL_WEEKLY':
            title = (
                f"ROLL {position.symbol} ${position.strike_price}→${result.new_strike:.0f} "
                f"(weekly)"
            )
            action_type = 'roll'
            
        elif result.action == 'CLOSE_CATASTROPHIC':
            title = f"🚨 CLOSE {position.symbol} ${position.strike_price} - Cannot escape within 12 months"
            action_type = 'close'
        
        elif result.action == 'NEAR_ITM_WARNING':
            # Position is dangerously close to strike - preemptive warning
            otm_pct = result.details.get('otm_pct', 0)
            days_left = result.details.get('days_to_expiry', 0)
            risk_level = result.details.get('risk_level', 'elevated')
            emoji = "🚨" if risk_level == 'urgent' else "⚠️"
            title = (
                f"{emoji} NEAR ITM: {position.symbol} ${position.strike_price} - "
                f"Only {otm_pct:.1f}% OTM, {days_left}d to expiry"
            )
            action_type = 'roll'
        
        elif result.action == 'EXDIV_TOMORROW':
            # Ex-dividend date is tomorrow - assignment risk for ITM calls
            title = (
                f"📅 EX-DIV TOMORROW: {position.symbol} ${position.strike_price} - "
                f"ITM calls may be assigned early"
            )
            action_type = 'monitor'
        
        elif result.action == 'EXDIV_ASSIGNMENT_RISK':
            # Ex-dividend date before expiration - early assignment risk
            exdiv_date = result.details.get('exdiv_date', 'soon')
            days_to_exdiv = result.details.get('days_to_exdiv', '?')
            title = (
                f"📅 EX-DIV RISK: {position.symbol} ${position.strike_price} - "
                f"Ex-div in {days_to_exdiv}d, watch for early assignment"
            )
            action_type = 'monitor'
        
        elif result.action == 'TRIPLE_WITCHING_TOMORROW':
            # Triple Witching is tomorrow - warning to prepare
            expiring_count = result.details.get('expiring_count', 0)
            title = (
                f"🔴 TRIPLE WITCHING TOMORROW - {expiring_count} positions expiring. "
                f"Prepare action plan tonight."
            )
            action_type = 'monitor'
        
        elif result.action == 'TRIPLE_WITCHING_EXPIRY':
            # Position expiring on Triple Witching Day
            tw_action = result.details.get('action', 'MONITOR')
            is_itm = result.details.get('is_itm', False)
            itm_otm_pct = result.details.get('itm_otm_pct', 0)
            emoji = "🔴" if is_itm else "🟡"
            title = (
                f"{emoji} TRIPLE WITCHING: {position.symbol} ${position.strike_price} - "
                f"{abs(itm_otm_pct):.1f}% {'ITM' if is_itm else 'OTM'}"
            )
            action_type = result.details.get('timing', 'Close before 3 PM ET')
            
        else:
            return None
        
        # Build context - ensure all values are JSON serializable
        def sanitize_for_json(obj):
            """Convert numpy types and other non-JSON-serializable types to Python types."""
            import numpy as np
            if isinstance(obj, (np.bool_, np.integer, np.floating)):
                return obj.item()
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, dict):
                return {k: sanitize_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [sanitize_for_json(item) for item in obj]
            elif hasattr(obj, 'isoformat'):
                return obj.isoformat()
            return obj
        
        context = {
            'symbol': position.symbol,
            'current_strike': float(position.strike_price),
            'option_type': position.option_type,
            'expiration': position.expiration_date.isoformat(),
            'contracts': int(position.contracts),
            'account': position.account_name,
            'account_name': position.account_name,
            'v3_action': result.action,
            **{k: sanitize_for_json(v) for k, v in result.details.items()},
        }
        
        if result.new_strike:
            context['new_strike'] = float(result.new_strike)
        if result.new_expiration:
            context['new_expiration'] = result.new_expiration.isoformat()
        if result.net_cost is not None:
            context['net_cost'] = float(result.net_cost)
        if result.zero_cost_data:
            context['zero_cost_data'] = sanitize_for_json(result.zero_cost_data)
        if result.pull_back_data:
            context['pull_back_data'] = sanitize_for_json(result.pull_back_data)
        
        # Include TA summary and decision rationale for V2 snapshot enrichment
        if result.ta_summary:
            context['ta_summary'] = result.ta_summary
        if result.decision_rationale:
            context['decision_rationale'] = result.decision_rationale
        
        # Build action string
        if result.action in ('ROLL_ITM', 'ROLL_WEEKLY', 'PULL_BACK'):
            action_str = (
                f"Buy to close ${position.strike_price} {position.option_type}, "
                f"sell ${result.new_strike:.0f} for {result.new_expiration.strftime('%b %d') if result.new_expiration else 'N/A'}"
            )
        else:
            action_str = f"Close {position.contracts}x ${position.strike_price} {position.option_type}"
        
        # Create unique ID including account
        account_slug = (position.account_name or "unknown").replace(" ", "_").replace("'", "")
        rec_id = f"v3_{result.action.lower()}_{position.symbol}_{position.strike_price}_{account_slug}"
        
        return StrategyRecommendation(
            id=rec_id,
            type=strategy_type,
            category='optimization',
            priority=result.priority,
            title=title,
            description=result.reason,
            rationale=result.reason,
            action=action_str,
            action_type=action_type,
            potential_income=None,
            potential_risk='low' if result.action == 'ROLL_WEEKLY' else 'medium',
            time_horizon='immediate' if result.priority == 'urgent' else 'this_week',
            symbol=position.symbol,
            account_name=position.account_name,
            context=context,
            # Don't set created_at - let StrategyRecommendation.__init__ handle it with proper timezone
            expires_at=datetime.combine(position.expiration_date, datetime.max.time()) if position.expiration_date else None
        )


