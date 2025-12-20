"""
Earnings Alert Strategy

Proactively alerts about positions that have earnings within the week.

ALGORITHM VERSION AWARE:
- V1/V2: Same logic, uses config for days_before_earnings parameter

This is a HEADS-UP notification that gives you time to decide:
- Close profitable positions before earnings (lock in gains)
- Roll ITM positions before binary event
- Monitor OTM positions that might become ITM after earnings gap

The notification provides:
- Days until earnings
- Current P/L on the position
- Whether position is ITM/OTM
- Recommended action based on position state
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
import logging

from app.modules.strategies.strategy_base import BaseStrategy
from app.modules.strategies.recommendations import StrategyRecommendation
from app.modules.strategies.option_monitor import get_positions_from_db, OptionRollMonitor
from app.modules.strategies.technical_analysis import get_technical_analysis_service
from app.modules.strategies.algorithm_config import get_config, ALGORITHM_VERSION

logger = logging.getLogger(__name__)

# Load config
_config = get_config()


class EarningsAlertStrategy(BaseStrategy):
    """
    Strategy for alerting about positions with upcoming earnings.
    
    Provides heads-up notification so you can take action before
    the binary earnings event.
    """
    
    strategy_type = "earnings_alert"
    name = "Earnings Alert"
    description = f"[{ALGORITHM_VERSION.upper()}] Alerts when positions have earnings within {_config['earnings']['days_before_alert']} trading days"
    category = "risk_management"
    default_parameters = {
        "days_before_earnings": _config["earnings"]["days_before_alert"],
        "profit_threshold_close": 0.50,  # Recommend closing if >50% profit
    }
    
    def generate_recommendations(self, params: Dict[str, Any]) -> List[StrategyRecommendation]:
        """Generate earnings alert recommendations."""
        recommendations = []
        
        days_before = self.get_parameter("days_before_earnings", 5)
        profit_threshold = self.get_parameter("profit_threshold_close", 0.50)
        
        logger.info(f"[EARNINGS_ALERT] Starting earnings alert scan - looking for earnings within {days_before} days")
        
        # Get open positions from database
        positions = get_positions_from_db(self.db)
        
        if not positions:
            logger.warning("[EARNINGS_ALERT] No positions found in database - skipping")
            return recommendations
        
        logger.info(f"[EARNINGS_ALERT] Found {len(positions)} positions to check for upcoming earnings")
        
        ta_service = get_technical_analysis_service()
        monitor = OptionRollMonitor(profit_threshold=profit_threshold)
        today = date.today()
        
        # Cache indicators per symbol
        indicators_cache: Dict[str, Any] = {}
        symbols_checked = set()
        earnings_found = []
        
        for position in positions:
            try:
                symbol = position.symbol
                
                # Get technical indicators (includes earnings date)
                if symbol not in indicators_cache:
                    logger.debug(f"[EARNINGS_ALERT] Fetching indicators for {symbol}")
                    indicators = ta_service.get_technical_indicators(symbol)
                    indicators_cache[symbol] = indicators
                    symbols_checked.add(symbol)
                    
                    # Log earnings date info for each symbol (only once)
                    if indicators and indicators.earnings_date:
                        days_to = (indicators.earnings_date - today).days
                        logger.info(f"[EARNINGS_ALERT] {symbol}: Earnings on {indicators.earnings_date} ({days_to} days away)")
                        earnings_found.append((symbol, indicators.earnings_date, days_to))
                    else:
                        logger.debug(f"[EARNINGS_ALERT] {symbol}: No earnings date found or no indicators")
                else:
                    indicators = indicators_cache[symbol]
                
                if not indicators:
                    logger.debug(f"[EARNINGS_ALERT] {symbol}: No indicators available - skipping")
                    continue
                    
                if not indicators.earnings_date:
                    logger.debug(f"[EARNINGS_ALERT] {symbol}: No earnings date in indicators - skipping")
                    continue
                
                # Check if earnings is within our alert window
                days_to_earnings = (indicators.earnings_date - today).days
                
                if days_to_earnings < 0:
                    logger.debug(f"[EARNINGS_ALERT] {symbol}: Earnings already passed ({days_to_earnings} days ago) - skipping")
                    continue
                    
                if days_to_earnings > days_before:
                    logger.debug(f"[EARNINGS_ALERT] {symbol}: Earnings too far away ({days_to_earnings} days > {days_before} threshold) - skipping")
                    continue
                
                # We have earnings within the window - generate alert
                logger.info(f"[EARNINGS_ALERT] 🎯 {symbol}: GENERATING ALERT - earnings in {days_to_earnings} days (within {days_before} day window)")
                rec = self._generate_earnings_alert(
                    position, indicators, monitor, days_to_earnings
                )
                if rec:
                    recommendations.append(rec)
                    logger.info(f"[EARNINGS_ALERT] ✅ {symbol}: Alert generated with priority '{rec.priority}'")
                else:
                    logger.warning(f"[EARNINGS_ALERT] {symbol}: _generate_earnings_alert returned None")
                    
            except Exception as e:
                logger.error(f"[EARNINGS_ALERT] Error checking earnings for {position.symbol}: {e}", exc_info=True)
                continue
        
        # Summary log
        logger.info(f"[EARNINGS_ALERT] ═══ SCAN COMPLETE ═══")
        logger.info(f"[EARNINGS_ALERT] Symbols checked: {len(symbols_checked)}")
        logger.info(f"[EARNINGS_ALERT] Upcoming earnings found: {len(earnings_found)}")
        for sym, earn_date, days in earnings_found:
            logger.info(f"[EARNINGS_ALERT]   • {sym}: {earn_date} ({days} days)")
        logger.info(f"[EARNINGS_ALERT] Alerts generated: {len(recommendations)}")
        
        return recommendations
    
    def _generate_earnings_alert(
        self,
        position,
        indicators,
        monitor: OptionRollMonitor,
        days_to_earnings: int
    ) -> Optional[StrategyRecommendation]:
        """Generate an earnings alert for a position."""
        
        current_price = indicators.current_price
        strike = position.strike_price
        earnings_date = indicators.earnings_date
        
        # Determine ITM status
        if position.option_type.lower() == "call":
            is_itm = current_price > strike
            itm_pct = (current_price - strike) / strike * 100 if is_itm else 0
            otm_pct = (strike - current_price) / strike * 100 if not is_itm else 0
        else:
            is_itm = current_price < strike
            itm_pct = (strike - current_price) / strike * 100 if is_itm else 0
            otm_pct = (current_price - strike) / strike * 100 if not is_itm else 0
        
        # Check profit status
        alert = monitor.check_position(position)
        profit_pct = (alert.profit_percent * 100) if alert else 0
        has_profit = profit_pct >= 50  # 50%+ profit captured
        
        # Determine recommended action
        if is_itm:
            action_type = "roll"
            action = f"Roll before earnings - position is {itm_pct:.1f}% ITM"
            priority = "urgent"
            risk = "high"
        elif has_profit:
            action_type = "close"
            action = f"Consider closing - {profit_pct:.0f}% profit captured before binary event"
            priority = "high"
            risk = "low"
        else:
            action_type = "monitor"
            action = f"Monitor - {otm_pct:.1f}% OTM, earnings may cause gap"
            priority = "medium"
            risk = "medium"
        
        # Urgency based on days to earnings
        if days_to_earnings == 0:
            urgency = "TODAY"
            priority = "urgent"
        elif days_to_earnings == 1:
            urgency = "TOMORROW"
            priority = "urgent" if is_itm else priority
        else:
            urgency = f"in {days_to_earnings} days"
        
        # Build context
        context = {
            "symbol": position.symbol,
            "strike_price": position.strike_price,
            "option_type": position.option_type,
            "expiration_date": position.expiration_date.isoformat(),
            "contracts": position.contracts,
            "account": position.account_name,
            "earnings_date": earnings_date.isoformat(),
            "days_to_earnings": days_to_earnings,
            "current_price": current_price,
            "is_itm": is_itm,
            "itm_percent": round(itm_pct, 1) if is_itm else None,
            "otm_percent": round(otm_pct, 1) if not is_itm else None,
            "profit_percent": round(profit_pct, 1),
            "recommended_action": action_type,
        }
        
        # Title
        position_status = f"{itm_pct:.0f}% ITM" if is_itm else f"{otm_pct:.0f}% OTM"
        title = (
            f"📊 EARNINGS {urgency}: {position.symbol} ${strike} {position.option_type} "
            f"({position_status}) · Stock ${current_price:.0f}"
        )
        
        # Description
        description = (
            f"{position.symbol} earnings on {earnings_date.strftime('%b %d')} ({urgency}). "
            f"{position.contracts}x ${strike} {position.option_type} is {position_status}. "
            f"{action}"
        )
        
        # Rationale
        rationale_parts = [
            f"📊 **EARNINGS ALERT**: {position.symbol} reports {urgency} ({earnings_date.strftime('%b %d')})",
            "",
            f"**Position**: {position.contracts}x ${strike} {position.option_type} in {position.account_name}",
            f"**Current Status**: {position_status} (stock at ${current_price:.2f})",
            f"**Profit Captured**: {profit_pct:.0f}%",
            "",
            "**Earnings Risk**:",
            "• Stocks can gap 5-15% on earnings surprises",
            "• Binary event - outcome is unpredictable",
            f"• Consider {'rolling' if is_itm else 'closing'} before the event",
        ]
        
        rationale = "\n".join(rationale_parts)
        
        # Account slug for unique ID
        account_slug = (position.account_name or "unknown").replace(" ", "_").replace("'", "")
        
        return StrategyRecommendation(
            id=f"earnings_alert_{position.symbol}_{position.strike_price}_{earnings_date.isoformat()}_{account_slug}",
            type=self.strategy_type,
            category=self.category,
            priority=priority,
            title=title,
            description=description,
            rationale=rationale,
            action=action,
            action_type=action_type,
            potential_income=None,
            potential_risk=risk,
            time_horizon="immediate" if days_to_earnings <= 1 else "this_week",
            symbol=position.symbol,
            account_name=position.account_name,
            context=context,
            expires_at=datetime.combine(earnings_date + timedelta(days=1), datetime.max.time())
        )

