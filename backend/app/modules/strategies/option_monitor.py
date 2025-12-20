"""
Option Chain Monitoring Service for Early Roll Detection.

This service monitors sold options positions and alerts when they've reached
a profit threshold (default 80%) that makes early rolling advantageous.

Strategy Background:
- Selling weekly covered calls at delta 90 (deep in-the-money)
- Normally wait until Friday expiration to roll
- If stock drops/stagnates, option premium decays faster
- When 80%+ profit achieved early (e.g., Tuesday/Wednesday), roll early
- This captures more premium over time by redeploying capital
"""

import yfinance as yf
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class OptionPosition:
    """Represents a sold option position to monitor."""
    symbol: str
    strike_price: float
    option_type: str  # 'call' or 'put'
    expiration_date: date
    contracts: int
    original_premium: float  # What we sold it for
    sold_option_id: Optional[int] = None  # DB reference
    account_name: Optional[str] = None  # Account name
    current_premium: Optional[float] = None  # Current premium from Robinhood paste
    gain_loss_percent: Optional[float] = None  # Gain/loss % from Robinhood paste


@dataclass 
class OptionQuote:
    """Current market data for an option."""
    contract_symbol: str
    strike: float
    bid: float
    ask: float
    last_price: float
    volume: int
    open_interest: int
    implied_volatility: float
    in_the_money: bool


@dataclass
class RollAlert:
    """Alert for early roll opportunity."""
    position: OptionPosition
    current_premium: float
    profit_amount: float
    profit_percent: float
    days_to_expiry: int
    recommendation: str
    urgency: str  # 'low', 'medium', 'high'


class OptionChainFetcher:
    """
    Fetches option chain data from Yahoo Finance with intelligent caching.
    
    Uses the yahoo_cache module for:
    - 5 minute cache during market hours
    - 30 minute cache outside market hours
    - 60 minute cache on weekends
    
    This prevents 429 rate limiting errors from Yahoo Finance.
    """
    
    def __init__(self):
        # Legacy cache removed - using yahoo_cache module
        pass
    
    def get_option_chain(self, symbol: str, expiration_date: date) -> Optional[Dict]:
        """
        Fetch option chain for a symbol and expiration date.
        
        Returns dict with 'calls' and 'puts' DataFrames.
        Uses cached data when available to avoid rate limiting.
        """
        from app.modules.strategies.yahoo_cache import (
            get_option_expirations,
            get_option_chain as cached_get_option_chain
        )
        
        try:
            # Get available expirations (cached)
            available_expirations = get_option_expirations(symbol)
            if not available_expirations:
                logger.warning(f"No options available for {symbol}")
                return None
            
            # Find matching expiration
            exp_str = expiration_date.strftime("%Y-%m-%d")
            if exp_str not in available_expirations:
                # Find closest expiration
                closest = min(available_expirations, 
                             key=lambda x: abs((datetime.strptime(x, "%Y-%m-%d").date() - expiration_date).days))
                logger.info(f"Exact expiration {exp_str} not found for {symbol}, using {closest}")
                exp_str = closest
            
            # Fetch option chain (cached)
            opt_chain = cached_get_option_chain(symbol, exp_str)
            
            if opt_chain is None:
                return None
            
            result = {
                'expiration': exp_str,
                'calls': opt_chain.calls,
                'puts': opt_chain.puts
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching option chain for {symbol}: {e}")
            return None
    
    def get_option_quote(
        self, 
        symbol: str, 
        strike_price: float, 
        option_type: str,  # 'call' or 'put'
        expiration_date: date
    ) -> Optional[OptionQuote]:
        """
        Get current quote for a specific option contract.
        """
        chain = self.get_option_chain(symbol, expiration_date)
        if not chain:
            return None
        
        # Select calls or puts
        options_df = chain['calls'] if option_type.lower() == 'call' else chain['puts']
        
        if options_df.empty:
            return None
        
        # Find the option with matching strike
        # Use a small tolerance for float comparison
        matching = options_df[abs(options_df['strike'] - strike_price) < 0.01]
        
        if matching.empty:
            # Try to find closest strike
            closest_idx = (abs(options_df['strike'] - strike_price)).idxmin()
            matching = options_df.loc[[closest_idx]]
            logger.info(f"Exact strike {strike_price} not found, using {matching.iloc[0]['strike']}")
        
        row = matching.iloc[0]
        
        return OptionQuote(
            contract_symbol=row['contractSymbol'],
            strike=row['strike'],
            bid=row['bid'] if row['bid'] else 0,
            ask=row['ask'] if row['ask'] else 0,
            last_price=row['lastPrice'] if row['lastPrice'] else 0,
            volume=int(row['volume']) if row['volume'] else 0,
            open_interest=int(row['openInterest']) if row['openInterest'] else 0,
            implied_volatility=row['impliedVolatility'] if row['impliedVolatility'] else 0,
            in_the_money=row['inTheMoney']
        )


class OptionRollMonitor:
    """
    Monitors sold options and generates alerts for early rolling opportunities.
    
    Logic:
    - Fetch current option prices for all open positions
    - Calculate profit percentage: (original_premium - current_premium) / original_premium
    - If profit >= threshold (default 80%), generate alert
    - Consider days to expiry for urgency
    """
    
    def __init__(self, profit_threshold: float = 0.80):
        """
        Initialize the monitor.
        
        Args:
            profit_threshold: Minimum profit percentage to trigger alert (0.80 = 80%)
        """
        self.profit_threshold = profit_threshold
        self.fetcher = OptionChainFetcher()
    
    def check_position(self, position: OptionPosition) -> Optional[RollAlert]:
        """
        Check a single position for early roll opportunity.
        
        Returns RollAlert if threshold met, None otherwise.
        
        OPTIMIZATION: Uses stored current_premium from Robinhood paste when available,
        avoiding expensive API calls. Only falls back to API if no stored data.
        """
        current_premium = None
        
        # PRIORITY 1: Use stored premium from Robinhood paste (NO API CALL!)
        if position.current_premium is not None and position.current_premium > 0:
            current_premium = position.current_premium
            logger.debug(f"{position.symbol}: Using stored premium ${current_premium:.2f} from paste")
        
        # PRIORITY 2: Fall back to API only if no stored data
        if current_premium is None:
            quote = self.fetcher.get_option_quote(
                symbol=position.symbol,
                strike_price=position.strike_price,
                option_type=position.option_type,
                expiration_date=position.expiration_date
            )
            
            if not quote:
                logger.warning(f"Could not get quote for {position.symbol} {position.strike_price} {position.option_type}")
                return None
            
            # Use mid-price or bid for current value
            current_premium = quote.bid if quote.bid > 0 else quote.last_price
        
        if current_premium is None or current_premium <= 0:
            logger.warning(f"Invalid current premium for {position.symbol}: {current_premium}")
            return None
        
        # Calculate profit
        # We SOLD the option, so profit = what we received - what we pay to close
        profit_amount = position.original_premium - current_premium
        profit_percent = profit_amount / position.original_premium if position.original_premium > 0 else 0
        
        # Calculate days to expiry
        days_to_expiry = (position.expiration_date - date.today()).days
        
        # Determine urgency based on days to expiry and profit
        if profit_percent >= 0.90:
            urgency = 'high'
        elif profit_percent >= 0.80 and days_to_expiry >= 3:
            urgency = 'medium'
        else:
            urgency = 'low'
        
        # Generate recommendation
        if profit_percent >= self.profit_threshold:
            if days_to_expiry >= 3:
                recommendation = (
                    f"ROLL EARLY: {profit_percent*100:.1f}% profit captured with {days_to_expiry} days remaining. "
                    f"Close position at ${current_premium:.2f} and roll to next week."
                )
            elif days_to_expiry >= 1:
                recommendation = (
                    f"CONSIDER ROLLING: {profit_percent*100:.1f}% profit with {days_to_expiry} day(s) left. "
                    f"Evaluate if worth rolling or let expire."
                )
            else:
                recommendation = (
                    f"EXPIRING TODAY: {profit_percent*100:.1f}% profit. "
                    f"Let expire or close and roll to next week."
                )
            
            return RollAlert(
                position=position,
                current_premium=current_premium,
                profit_amount=profit_amount,
                profit_percent=profit_percent,
                days_to_expiry=days_to_expiry,
                recommendation=recommendation,
                urgency=urgency
            )
        
        return None
    
    def check_all_positions(self, positions: List[OptionPosition]) -> List[RollAlert]:
        """
        Check all positions and return list of alerts.
        """
        alerts = []
        
        for position in positions:
            try:
                alert = self.check_position(position)
                if alert:
                    alerts.append(alert)
            except Exception as e:
                logger.error(f"Error checking position {position.symbol}: {e}")
        
        # Sort by profit percentage descending
        alerts.sort(key=lambda x: x.profit_percent, reverse=True)
        
        return alerts
    
    def format_alert_message(self, alerts: List[RollAlert]) -> str:
        """
        Format alerts into a readable message for notifications.
        """
        if not alerts:
            return "No early roll opportunities at this time."
        
        lines = [
            "🔔 OPTION ROLL ALERT",
            f"Found {len(alerts)} position(s) ready for early rolling:",
            ""
        ]
        
        for i, alert in enumerate(alerts, 1):
            pos = alert.position
            lines.extend([
                f"{i}. {pos.symbol} ${pos.strike_price} {pos.option_type.upper()}",
                f"   Expiry: {pos.expiration_date.strftime('%m/%d')} ({alert.days_to_expiry} days)",
                f"   Contracts: {pos.contracts}",
                f"   Original Premium: ${pos.original_premium:.2f}",
                f"   Current Premium: ${alert.current_premium:.2f}",
                f"   Profit: ${alert.profit_amount:.2f} ({alert.profit_percent*100:.1f}%)",
                f"   Urgency: {alert.urgency.upper()}",
                f"   ➜ {alert.recommendation}",
                ""
            ])
        
        return "\n".join(lines)


def get_positions_from_db(db_session) -> List[OptionPosition]:
    """
    Load open positions from the database.
    
    IMPORTANT: Per DATA_SOURCE_ARCHITECTURE.md, we ONLY use positions from the
    LATEST snapshot per account. Positions not in the latest snapshot are considered CLOSED.
    
    Returns positions that:
    - Are from the LATEST snapshot for their account
    - Have status 'open'
    - Have an expiration date in the future
    - Can determine original_premium (directly set, or calculated from gain/loss %)
    """
    from app.modules.strategies.models import SoldOption, SoldOptionsSnapshot
    from sqlalchemy import func
    
    today = date.today()
    
    # Per DATA_SOURCE_ARCHITECTURE.md: Only use positions from LATEST snapshot per account
    # First, get the latest snapshot ID for each account
    latest_snapshots_subquery = db_session.query(
        SoldOptionsSnapshot.account_name,
        func.max(SoldOptionsSnapshot.id).label('latest_id')
    ).filter(
        SoldOptionsSnapshot.parsing_status == 'success'
    ).group_by(SoldOptionsSnapshot.account_name).subquery()
    
    # Only get positions from those latest snapshots
    all_options = db_session.query(SoldOption).join(SoldOptionsSnapshot).join(
        latest_snapshots_subquery,
        SoldOptionsSnapshot.id == latest_snapshots_subquery.c.latest_id
    ).filter(
        SoldOption.expiration_date >= today,
        SoldOption.status == 'open'
    ).all()
    
    logger.info(f"get_positions_from_db: Found {len(all_options)} positions from latest snapshots")
    
    positions = []
    for opt in all_options:
        original_premium = None
        
        # Priority 1: Use explicitly set original_premium
        if opt.original_premium:
            original_premium = float(opt.original_premium)
        
        # Priority 2: Calculate from gain/loss % and current premium
        elif opt.premium_per_contract and opt.gain_loss_percent is not None:
            curr_premium = float(opt.premium_per_contract)
            gain_loss = float(opt.gain_loss_percent)
            
            if gain_loss != 100:
                original_premium = curr_premium / (1 - gain_loss / 100)
                logger.debug(f"{opt.symbol}: Calculated original_premium=${original_premium:.2f} from current=${curr_premium:.2f}, gain/loss={gain_loss}%")
        
        # Priority 3: Fall back to current premium (less accurate but better than nothing)
        elif opt.premium_per_contract:
            original_premium = float(opt.premium_per_contract)
            logger.debug(f"{opt.symbol}: Using current premium as original (no gain/loss data)")
        
        if original_premium is None:
            logger.warning(f"Skipping {opt.symbol} ${opt.strike_price} - cannot determine original premium")
            continue
        
        account_name = opt.snapshot.account_name if opt.snapshot else None
        logger.debug(f"Position: {opt.symbol} ${opt.strike_price} {opt.option_type} - {account_name}")
        
        # Get current premium from Robinhood paste (avoids API calls!)
        current_premium = float(opt.premium_per_contract) if opt.premium_per_contract else None
        gain_loss_percent = float(opt.gain_loss_percent) if opt.gain_loss_percent else None
        
        positions.append(OptionPosition(
            symbol=opt.symbol,
            strike_price=float(opt.strike_price),
            option_type=opt.option_type,
            expiration_date=opt.expiration_date,
            contracts=opt.contracts_sold,
            original_premium=original_premium,
            sold_option_id=opt.id,
            account_name=account_name,
            current_premium=current_premium,
            gain_loss_percent=gain_loss_percent
        ))
    
    return positions


def save_alerts_to_db(db_session, alerts: List[RollAlert]) -> int:
    """
    Save alerts to the database for tracking.
    
    Returns number of new alerts created.
    """
    from app.modules.strategies.models import OptionRollAlert
    from sqlalchemy import func
    
    count = 0
    for alert in alerts:
        pos = alert.position
        
        # Check if we already have an unacknowledged alert for this position today
        existing = db_session.query(OptionRollAlert).filter(
            OptionRollAlert.sold_option_id == pos.sold_option_id,
            OptionRollAlert.alert_acknowledged == 'N',
            func.date(OptionRollAlert.alert_triggered_at) == date.today()
        ).first() if pos.sold_option_id else None
        
        if existing:
            # Update existing alert
            existing.current_premium = Decimal(str(alert.current_premium))
            existing.profit_percent = Decimal(str(alert.profit_percent * 100))
        else:
            # Create new alert
            new_alert = OptionRollAlert(
                sold_option_id=pos.sold_option_id,
                symbol=pos.symbol,
                strike_price=Decimal(str(pos.strike_price)),
                option_type=pos.option_type,
                expiration_date=pos.expiration_date,
                contracts=pos.contracts,
                original_premium=Decimal(str(pos.original_premium)),
                current_premium=Decimal(str(alert.current_premium)),
                profit_percent=Decimal(str(alert.profit_percent * 100)),
                alert_type='early_roll_opportunity'
            )
            db_session.add(new_alert)
            count += 1
    
    db_session.commit()
    return count


# For testing
if __name__ == "__main__":
    # Test with sample position
    monitor = OptionRollMonitor(profit_threshold=0.80)
    
    # Example: Simulate a position
    test_position = OptionPosition(
        symbol="AAPL",
        strike_price=275.0,
        option_type="call",
        expiration_date=date.today() + timedelta(days=2),
        contracts=1,
        original_premium=5.00  # Sold at $5.00
    )
    
    alert = monitor.check_position(test_position)
    if alert:
        print(monitor.format_alert_message([alert]))
    else:
        print(f"No alert for {test_position.symbol} - current price doesn't meet threshold")

