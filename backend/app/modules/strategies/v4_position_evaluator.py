"""
V4 Position Evaluator - Conviction-Based Options Income

V4 Philosophy:
1. Believe in holdings - we own quality stocks
2. Hold forever - long-term mindset
3. Mean reversion is inevitable - stocks cycle
4. Primary goal: weekly options income
5. Tactical timing - sell when up, buy when down
6. Avoid forced assignment - maintain control

Decision Framework:
1. Time Cushion Check (≤2 days → must act)
2. Intrinsic/Time Value Assessment
3. Cost Basis Check (for puts)
4. Dual-Benefit Compression Analysis
5. Tactical Timing Application
"""

from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
import logging

from app.modules.strategies.algorithm_config import V4_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class V4EvaluationResult:
    """Result of V4 position evaluation with rich reasoning."""
    # Core decision
    action: str  # HOLD, CLOSE, ROLL, COMPRESS, WAIT_FOR_PULLBACK, WAIT_FOR_RECOVERY, LET_EXPIRE
    position_id: str
    symbol: str

    # V4: Reasoning (the key differentiator)
    reason: str  # Full reasoning text for notification
    reason_short: str  # One-line summary
    philosophy_applied: str  # Which V4 belief drove this decision

    # Follow-up tracking (for two-part actions)
    has_follow_up: bool = False
    follow_up_condition: Optional[str] = None  # e.g., "stock_drops_3_pct"
    follow_up_threshold: Optional[float] = None  # e.g., 0.03
    follow_up_action: Optional[str] = None  # e.g., "RE_ENTER"

    # Position details
    details: Dict[str, Any] = field(default_factory=dict)

    # For roll/compress actions
    new_strike: Optional[float] = None
    new_expiration: Optional[date] = None
    net_cost: Optional[float] = None

    # V4 metrics
    intrinsic_pct: Optional[float] = None  # % of option value that is intrinsic
    time_value: Optional[float] = None
    escape_weeks: Optional[int] = None  # Weeks needed to escape
    compression_value: Optional[float] = None  # Dual-benefit value
    compression_cost: Optional[float] = None

    # Cost basis info (for puts)
    cost_basis: Optional[float] = None
    assignment_acceptable: Optional[bool] = None


class V4PositionEvaluator:
    """
    V4 Position Evaluator - Conviction-based options income strategy.

    Key differences from V3:
    - Generates rich reasoning explaining the "why"
    - Tracks follow-up conditions for two-part actions
    - Applies V4 philosophy (mean reversion, hold forever, etc.)
    - Uses dual-benefit compression formula
    - Separates buy and sell timing
    """

    def __init__(self, ta_service=None, option_fetcher=None, db=None):
        """Initialize V4 evaluator."""
        if ta_service is None:
            from app.modules.strategies.technical_analysis import get_technical_analysis_service
            ta_service = get_technical_analysis_service()

        if option_fetcher is None:
            from app.modules.strategies.option_monitor import OptionChainFetcher
            option_fetcher = OptionChainFetcher()

        self.ta_service = ta_service
        self.option_fetcher = option_fetcher
        self.db = db
        self.config = V4_CONFIG

    def evaluate(
        self,
        position,
        cost_basis: Optional[float] = None,
        weekly_income: Optional[float] = None
    ) -> Optional[V4EvaluationResult]:
        """
        Main V4 evaluation logic.

        Decision order:
        1. Time Cushion Check (≤2 days → must act immediately)
        2. Cost Basis Check (for puts - is assignment acceptable?)
        3. Intrinsic/Time Value Assessment
        4. Dual-Benefit Compression Analysis
        5. Tactical Timing (wait for optimal entry/exit)

        Args:
            position: Position object with required attributes
            cost_basis: User's cost basis for the underlying (for puts)
            weekly_income: Expected weekly premium for this symbol

        Returns:
            V4EvaluationResult with rich reasoning
        """
        try:
            # Get current price and indicators
            indicators = self.ta_service.get_technical_indicators(position.symbol)
            if not indicators:
                logger.warning(f"Cannot get indicators for {position.symbol}, using fallback evaluation")
                # Fallback: use stored data from position to make basic decision
                return self._fallback_evaluation(position)

            current_price = indicators.current_price

            # Calculate basic metrics
            today = date.today()
            days_to_exp = (position.expiration_date - today).days

            # Calculate ITM status (convert Decimal to float for calculations)
            from app.modules.strategies.utils.option_calculations import calculate_itm_status
            strike_price = float(position.strike_price) if position.strike_price else 0.0
            itm_calc = calculate_itm_status(
                current_price, strike_price, position.option_type
            )
            is_itm = itm_calc['is_itm']
            itm_pct = itm_calc['itm_pct']

            # Get current premium (convert Decimal to float)
            original_premium_raw = getattr(position, 'original_premium', 1.0)
            original_premium = float(original_premium_raw) if original_premium_raw else 1.0

            # Try multiple attribute names for current premium
            # SoldOption model uses 'premium_per_contract', others might use 'current_premium'
            current_premium_raw = getattr(position, 'current_premium', None) or \
                                  getattr(position, 'premium_per_contract', None)
            if current_premium_raw is not None:
                current_premium = float(current_premium_raw)
            else:
                current_premium = self._estimate_current_premium(position, indicators)

            profit_pct = (original_premium - current_premium) / original_premium if original_premium > 0 else 0

            # Calculate intrinsic/time value
            intrinsic_value, time_value = self._calculate_intrinsic_time_value(
                position, current_price, current_premium
            )
            intrinsic_pct = intrinsic_value / current_premium if current_premium > 0 else 0

            # ================================================================
            # STEP 1: Time Cushion Check (≤2 days → must act)
            # ================================================================
            if days_to_exp <= self.config['time_cushion']['min_days_to_expiry']:
                return self._handle_time_cushion(
                    position, is_itm, itm_pct, intrinsic_pct,
                    current_price, current_premium, profit_pct
                )

            # ================================================================
            # STEP 2: Early Profit Capture Check (≥70% profit → close)
            # ================================================================
            # V4 Philosophy: Lock in profits early. If you've captured 70%+ of
            # the premium, there's little left to gain but risk remains.
            early_close_threshold = self.config.get('early_close_threshold', 0.70)
            if profit_pct >= early_close_threshold:
                return self._handle_early_profit_capture(
                    position, profit_pct, original_premium, current_premium,
                    current_price, days_to_exp
                )

            # ================================================================
            # STEP 3: Cost Basis Check (for puts)
            # ================================================================
            if position.option_type == 'put' and cost_basis is not None:
                assignment_result = self._check_assignment_acceptability(
                    position, cost_basis, current_price, is_itm, itm_pct, days_to_exp
                )
                if assignment_result:
                    return assignment_result

            # ================================================================
            # STEP 4: Intrinsic/Time Value Assessment
            # ================================================================
            if is_itm:
                # Deep ITM handling
                return self._handle_itm_position(
                    position, is_itm, itm_pct, intrinsic_pct, intrinsic_value, time_value,
                    current_price, current_premium, profit_pct, days_to_exp,
                    weekly_income, cost_basis
                )
            else:
                # OTM position handling
                return self._handle_otm_position(
                    position, itm_pct, current_price, current_premium,
                    profit_pct, days_to_exp, indicators
                )

        except Exception as e:
            logger.error(f"V4 evaluation error for {position.symbol}: {e}", exc_info=True)
            return None

    def _calculate_intrinsic_time_value(
        self,
        position,
        current_price: float,
        current_premium: float
    ) -> Tuple[float, float]:
        """Calculate intrinsic and time value of an option."""
        strike = float(position.strike_price) if position.strike_price else 0.0
        if position.option_type == 'call':
            intrinsic = max(0, current_price - strike)
        else:  # put
            intrinsic = max(0, strike - current_price)

        # Time value = premium - intrinsic (for short options, we pay this)
        time_value = max(0, current_premium - intrinsic)

        return intrinsic, time_value

    def _calculate_escape_strike(
        self,
        current_strike: float,
        current_price: float,
        option_type: str,
        is_itm: bool
    ) -> float:
        """
        Calculate the escape strike - a strike that gets us to ATM or slightly OTM.

        V4 Philosophy: When ITM, roll UP for calls (or DOWN for puts) to escape.
        Target: strike at current price rounded to nearest $5 increment.

        For calls ITM: new strike = current_price rounded UP to nearest $5
        For puts ITM: new strike = current_price rounded DOWN to nearest $5
        If OTM: keep same strike
        """
        if not is_itm:
            return current_strike

        # Determine strike increment based on stock price
        if current_price >= 100:
            increment = 5.0
        elif current_price >= 50:
            increment = 2.5
        else:
            increment = 1.0

        if option_type == 'call':
            # For ITM calls: roll UP - round current price UP to nearest increment
            # This gets us closer to OTM
            new_strike = (current_price // increment + 1) * increment
            # Don't go below current strike (that would go deeper ITM)
            return max(new_strike, current_strike)
        else:
            # For ITM puts: roll DOWN - round current price DOWN to nearest increment
            new_strike = (current_price // increment) * increment
            # Don't go above current strike (that would go deeper ITM)
            return min(new_strike, current_strike)

    def _calculate_roll_targets(
        self,
        position,
        current_premium: float,
        current_price: float,
        force_escape: bool = False
    ) -> Tuple[float, date, float]:
        """
        Calculate roll targets: new strike, new expiration, and estimated net credit.

        For standard weekly rolls:
        - If ITM: Roll to escape strike (ATM or slightly OTM)
        - If OTM: Keep same strike
        - Roll to next Friday
        - Estimate net credit from selling new premium minus closing cost

        Args:
            position: The option position
            current_premium: Current premium to close
            current_price: Current stock price
            force_escape: If True, always calculate escape strike even if OTM

        Returns:
            (new_strike, new_expiration, estimated_net_credit)
        """
        strike = float(position.strike_price) if position.strike_price else 0.0
        option_type = getattr(position, 'option_type', 'call')
        contracts = getattr(position, 'contracts_sold', 1) or 1
        current_expiration = getattr(position, 'expiration_date', None)

        # Calculate next Friday for roll target
        # IMPORTANT: Must be AFTER the current position's expiration
        today = date.today()
        days_to_friday = (4 - today.weekday()) % 7
        if days_to_friday == 0:
            days_to_friday = 7  # Next Friday, not today
        new_expiration = today + timedelta(days=days_to_friday)

        # Ensure new expiration is AFTER current expiration (not same date!)
        try:
            if current_expiration:
                # Convert to date object if needed
                if isinstance(current_expiration, str):
                    try:
                        current_expiration = datetime.strptime(current_expiration, '%Y-%m-%d').date()
                    except:
                        pass
                elif isinstance(current_expiration, datetime):
                    # Handle datetime objects (convert to date)
                    current_expiration = current_expiration.date()
                elif hasattr(current_expiration, 'date'):
                    # Handle any other object with a date() method
                    current_expiration = current_expiration.date()

                if isinstance(current_expiration, date) and new_expiration <= current_expiration:
                    # Roll to the NEXT Friday after current expiration
                    new_expiration = current_expiration + timedelta(days=7)
        except Exception as e:
            logger.warning(f"Error calculating new expiration for {position.symbol}: {e}, using default")
            # Keep the default new_expiration calculated above

        # Check if ITM
        if option_type == 'call':
            is_itm = current_price > strike
        else:
            is_itm = current_price < strike

        # Calculate escape strike if ITM (or forced)
        if is_itm or force_escape:
            new_strike = self._calculate_escape_strike(strike, current_price, option_type, True)
        else:
            new_strike = strike

        # ================================================================
        # USE LIVE OPTION CHAIN DATA for accurate roll calculations
        # ================================================================

        # Get current position's expiration date for fetching its quote
        current_exp_date = getattr(position, 'expiration_date', None)
        if current_exp_date:
            if isinstance(current_exp_date, datetime):
                current_exp_date = current_exp_date.date()
            elif isinstance(current_exp_date, str):
                try:
                    current_exp_date = datetime.strptime(current_exp_date, '%Y-%m-%d').date()
                except:
                    current_exp_date = None

        # Get close cost (ask price to buy back current position)
        close_cost_per_share = current_premium  # fallback to current_premium
        if current_exp_date and self.option_fetcher:
            try:
                current_quote = self.option_fetcher.get_option_quote(
                    symbol=position.symbol,
                    strike_price=strike,
                    option_type=option_type,
                    expiration_date=current_exp_date
                )
                if current_quote:
                    # Use ask price (what we'd pay to buy back)
                    close_cost_per_share = current_quote.ask if current_quote.ask else (current_quote.last_price or current_premium)
                    logger.debug(f"V4 Roll {position.symbol}: Live close cost = ${close_cost_per_share:.2f}/share (ask)")
            except Exception as e:
                logger.warning(f"V4 Roll: Failed to get current option quote for {position.symbol}: {e}")

        # Get new premium (bid price for new position at new_strike, new_expiration)
        estimated_new_premium = current_premium * 2.0  # fallback estimate
        if self.option_fetcher:
            try:
                new_quote = self.option_fetcher.get_option_quote(
                    symbol=position.symbol,
                    strike_price=new_strike,
                    option_type=option_type,
                    expiration_date=new_expiration
                )
                if new_quote:
                    # Use bid price (what we'd receive when selling)
                    estimated_new_premium = new_quote.bid if new_quote.bid else (new_quote.last_price or estimated_new_premium)
                    logger.debug(f"V4 Roll {position.symbol}: Live new premium = ${estimated_new_premium:.2f}/share (bid)")
            except Exception as e:
                logger.warning(f"V4 Roll: Failed to get new option quote for {position.symbol}: {e}")

        # Net credit = new premium - close cost (per share)
        net_credit_per_share = estimated_new_premium - close_cost_per_share

        # Total for all contracts (per share * 100 shares * contracts)
        close_cost = close_cost_per_share * contracts * 100
        new_premium_total = estimated_new_premium * contracts * 100
        net_credit = net_credit_per_share * contracts * 100

        logger.info(f"V4 Roll {position.symbol}: Close ${close_cost_per_share:.2f} → New ${estimated_new_premium:.2f} = Net {'Credit' if net_credit > 0 else 'Debit'} ${abs(net_credit):.0f}")

        return new_strike, new_expiration, net_credit

    def _handle_time_cushion(
        self,
        position,
        is_itm: bool,
        itm_pct: float,
        intrinsic_pct: float,
        current_price: float,
        current_premium: float,
        profit_pct: float
    ) -> V4EvaluationResult:
        """
        Handle positions with ≤2 days to expiry.

        V4 Philosophy: Avoid forced assignment - roll to next week.
        """
        min_days = self.config['time_cushion']['min_days_to_expiry']
        roll_weeks = self.config['time_cushion']['roll_out_weeks']

        if is_itm:
            # ITM with time cushion → MUST roll to avoid assignment
            # Calculate roll targets - will use escape strike to get OTM
            new_strike, new_exp, net_credit = self._calculate_roll_targets(
                position, current_premium, current_price
            )
            strike = float(position.strike_price) if position.strike_price else 0.0
            option_type = getattr(position, 'option_type', 'call')
            strike_change = abs(new_strike - strike)

            # Format message based on whether we're rolling UP/DOWN to escape
            if strike_change > 0:
                if option_type == 'call':
                    escape_msg = f"Rolling UP from ${strike:.0f} to ${new_strike:.0f} to escape ITM"
                else:
                    escape_msg = f"Rolling DOWN from ${strike:.0f} to ${new_strike:.0f} to escape ITM"
            else:
                escape_msg = f"Rolling to ${new_strike:.0f}"

            reason = (
                f"**Time Cushion Alert**: Position expires in ≤{min_days} days and is ITM ({itm_pct:.1f}%).\n\n"
                f"V4 Philosophy: Avoid forced assignment. {escape_msg}.\n"
                f"Stock: ${current_price:.2f} | Current strike: ${strike:.0f} | New strike: ${new_strike:.0f}\n\n"
                f"Roll ${strike:.0f} {position.option_type} to ${new_strike:.0f} {new_exp.strftime('%m/%d')} · "
                f"{'Earn' if net_credit > 0 else 'Cost'} ~${abs(net_credit):.0f}"
            )
            if strike_change > 0:
                reason_short = f"Time cushion - roll {option_type} ${strike:.0f}→${new_strike:.0f} {new_exp.strftime('%m/%d')} to escape ITM"
            else:
                reason_short = f"Time cushion ({min_days}d), ITM {itm_pct:.1f}% - roll to ${new_strike:.0f} {new_exp.strftime('%m/%d')}"

            return V4EvaluationResult(
                action='ROLL',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='avoid_forced_assignment',
                new_strike=new_strike,
                new_expiration=new_exp,
                net_cost=-net_credit if net_credit > 0 else abs(net_credit),
                details={
                    'days_to_exp': min_days,
                    'is_itm': is_itm,
                    'itm_pct': itm_pct,
                    'trigger': 'time_cushion',
                    'estimated_credit': net_credit,
                    'original_strike': strike,
                    'strike_change': strike_change,
                    'current_price': current_price,
                    'escape_applied': strike_change > 0
                },
                intrinsic_pct=intrinsic_pct
            )
        else:
            # OTM with time cushion
            early_close_threshold = self.config.get('early_close_threshold', 0.70)

            if profit_pct >= 0.80:
                # Highly profitable → roll to next week for continued income
                # Calculate roll targets
                new_strike, new_exp, net_credit = self._calculate_roll_targets(
                    position, current_premium, current_price
                )
                strike = float(position.strike_price) if position.strike_price else 0.0

                reason = (
                    f"**Time Cushion + Profitable**: Position expires in ≤{min_days} days, "
                    f"OTM with {profit_pct*100:.0f}% profit.\n\n"
                    f"V4 Philosophy: Primary goal is weekly income. Roll to next week to continue earning.\n\n"
                    f"Roll ${strike:.0f} {position.option_type} to ${new_strike:.0f} {new_exp.strftime('%m/%d')} · "
                    f"Earn ~${net_credit:.0f}"
                )
                reason_short = f"Time cushion, {profit_pct*100:.0f}% profit - roll to ${new_strike:.0f} {new_exp.strftime('%m/%d')}"

                return V4EvaluationResult(
                    action='ROLL',
                    position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                    symbol=position.symbol,
                    reason=reason,
                    reason_short=reason_short,
                    philosophy_applied='weekly_options_income',
                    new_strike=new_strike,
                    new_expiration=new_exp,
                    net_cost=-net_credit if net_credit > 0 else abs(net_credit),
                    details={
                        'days_to_exp': min_days,
                        'profit_pct': profit_pct,
                        'trigger': 'time_cushion_profitable',
                        'estimated_credit': net_credit
                    }
                )
            elif profit_pct >= early_close_threshold:
                # Profit above early close threshold (default 70%) but below 80%
                # → Close to lock in profits rather than letting expire
                strike = float(position.strike_price) if position.strike_price else 0.0
                contracts = getattr(position, 'contracts_sold', 1) or 1
                original_premium_raw = getattr(position, 'original_premium', 1.0)
                original_premium = float(original_premium_raw) if original_premium_raw else 1.0
                profit_captured = (original_premium - current_premium) * contracts * 100
                cost_to_close = current_premium * contracts * 100

                reason = (
                    f"**CLOSE - Lock In Profits**: Position expires in ≤{min_days} days, "
                    f"OTM with {profit_pct*100:.0f}% profit (${profit_captured:.0f} captured).\n\n"
                    f"V4 Philosophy: Don't let a winner become a loser. "
                    f"With {profit_pct*100:.0f}% captured, buy to close at ~${current_premium:.2f}/contract "
                    f"(${cost_to_close:.0f} total) to lock in gains.\n\n"
                    f"**Action**: Buy to close {contracts} {position.symbol} ${strike:.0f} {position.option_type}."
                )
                reason_short = f"{profit_pct*100:.0f}% profit captured - buy to close for ${cost_to_close:.0f}"

                return V4EvaluationResult(
                    action='CLOSE',
                    position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                    symbol=position.symbol,
                    reason=reason,
                    reason_short=reason_short,
                    philosophy_applied='lock_in_profits',
                    details={
                        'days_to_exp': min_days,
                        'profit_pct': profit_pct,
                        'profit_captured': profit_captured,
                        'cost_to_close': cost_to_close,
                        'trigger': 'time_cushion_early_close',
                        'current_price': current_price,
                    }
                )
            else:
                # Below early close threshold → let expire worthless
                reason = (
                    f"**Let Expire**: Position expires in ≤{min_days} days, "
                    f"OTM with {profit_pct*100:.0f}% profit.\n\n"
                    f"V4 Philosophy: Position is OTM and will likely expire worthless. "
                    f"No action needed - full premium captured."
                )
                reason_short = f"OTM, {profit_pct*100:.0f}% profit - let expire"

                return V4EvaluationResult(
                    action='LET_EXPIRE',
                    position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                    symbol=position.symbol,
                    reason=reason,
                    reason_short=reason_short,
                    philosophy_applied='weekly_options_income',
                    details={
                        'days_to_exp': min_days,
                        'profit_pct': profit_pct,
                        'trigger': 'expire_worthless'
                    }
                )

    def _handle_early_profit_capture(
        self,
        position,
        profit_pct: float,
        original_premium: float,
        current_premium: float,
        current_price: float,
        days_to_exp: int
    ) -> V4EvaluationResult:
        """
        Handle positions where 70%+ of premium has been captured.

        V4 Philosophy: Lock in profits early. If you've captured 70%+ of
        the premium, the remaining 30% isn't worth the risk of reversal.
        Close the position and free up capital for a new trade.
        """
        strike = float(position.strike_price) if position.strike_price else 0.0
        contracts = getattr(position, 'contracts_sold', 1) or 1
        profit_captured = (original_premium - current_premium) * contracts * 100
        cost_to_close = current_premium * contracts * 100

        reason = (
            f"**CLOSE - Lock In Profits**: You've captured {profit_pct*100:.0f}% of the premium "
            f"(${profit_captured:.0f} profit).\n\n"
            f"V4 Philosophy: Don't let a winner become a loser. With {days_to_exp} days left, "
            f"the remaining ${cost_to_close:.0f} isn't worth the risk of reversal.\n\n"
            f"**Action**: Buy to close at ~${current_premium:.2f} per contract.\n"
            f"Original premium: ${original_premium:.2f} | Current: ${current_premium:.2f} | "
            f"Stock: ${current_price:.2f}"
        )
        reason_short = f"{profit_pct*100:.0f}% profit captured - close to lock in ${profit_captured:.0f}"

        return V4EvaluationResult(
            action='CLOSE',
            position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
            symbol=position.symbol,
            reason=reason,
            reason_short=reason_short,
            philosophy_applied='lock_in_profits',
            details={
                'profit_pct': profit_pct,
                'profit_captured': profit_captured,
                'cost_to_close': cost_to_close,
                'original_premium': original_premium,
                'current_premium': current_premium,
                'days_to_exp': days_to_exp,
                'trigger': 'early_profit_capture'
            }
        )

    def _check_assignment_acceptability(
        self,
        position,
        cost_basis: float,
        current_price: float,
        is_itm: bool,
        itm_pct: float,
        days_to_exp: int
    ) -> Optional[V4EvaluationResult]:
        """
        For puts: Check if assignment would be acceptable based on cost basis.

        V4 Philosophy: If assignment improves our average cost, it's acceptable.
        """
        strike = float(position.strike_price) if position.strike_price else 0.0

        # Calculate if assignment improves cost basis
        assignment_improves_basis = strike < cost_basis

        if is_itm and assignment_improves_basis:
            # ITM put but assignment would IMPROVE our average
            reason = (
                f"**HOLD - Assignment Acceptable**: Put is ITM ({itm_pct:.1f}%), "
                f"but assignment at ${strike:.2f} would improve your cost basis (${cost_basis:.2f}).\n\n"
                f"V4 Philosophy: We believe in our holdings. Assignment at a lower price "
                f"improves our position. Either the put expires OTM (keep premium) or "
                f"we acquire shares at a better price.\n\n"
                f"Stock: ${current_price:.2f} | Strike: ${strike:.2f} | Cost Basis: ${cost_basis:.2f}"
            )
            reason_short = f"ITM put, but strike ${strike:.0f} < cost basis ${cost_basis:.0f} - assignment OK"

            return V4EvaluationResult(
                action='HOLD',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='believe_in_holdings',
                details={
                    'is_itm': is_itm,
                    'itm_pct': itm_pct,
                    'cost_basis': cost_basis,
                    'strike': strike,
                    'assignment_improves_basis': True
                },
                cost_basis=cost_basis,
                assignment_acceptable=True
            )

        return None  # Continue with normal evaluation

    def _handle_itm_position(
        self,
        position,
        is_itm: bool,
        itm_pct: float,
        intrinsic_pct: float,
        intrinsic_value: float,
        time_value: float,
        current_price: float,
        current_premium: float,
        profit_pct: float,
        days_to_exp: int,
        weekly_income: Optional[float],
        cost_basis: Optional[float]
    ) -> V4EvaluationResult:
        """
        Handle ITM positions using V4 intrinsic/time value model.

        Categories:
        - Shallow ITM (intrinsic <50%): Wait for mean reversion
        - Moderate ITM (intrinsic 50-80%): Consider tactical close
        - Deep ITM (intrinsic >80%): Compress to weekly or close + wait
        """
        # Determine escape weeks using 4-week cap
        max_escape_weeks = self.config.get('max_escape_weeks', 4)

        # Estimate weeks to escape based on typical stock movement
        # Rough heuristic: 1% move per week on average
        weeks_to_escape = min(int(itm_pct / 1.0) + 1, max_escape_weeks)

        if intrinsic_pct < 0.50:
            # Shallow ITM - wait for mean reversion
            reason = (
                f"**HOLD - Mean Reversion Expected**: Position is shallow ITM ({itm_pct:.1f}%), "
                f"intrinsic is only {intrinsic_pct*100:.0f}% of premium.\n\n"
                f"V4 Philosophy: Mean reversion is inevitable. Stock will likely move back OTM. "
                f"Time value ({time_value:.2f}) still significant.\n\n"
                f"Stock: ${current_price:.2f} | Strike: ${float(position.strike_price):.2f} | "
                f"Days to exp: {days_to_exp}"
            )
            reason_short = f"Shallow ITM ({itm_pct:.1f}%), wait for mean reversion"

            return V4EvaluationResult(
                action='HOLD',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='mean_reversion',
                details={
                    'itm_pct': itm_pct,
                    'intrinsic_pct': intrinsic_pct,
                    'time_value': time_value
                },
                intrinsic_pct=intrinsic_pct,
                time_value=time_value,
                escape_weeks=weeks_to_escape
            )

        elif intrinsic_pct < 0.80:
            # Moderate ITM - tactical decision
            reason = (
                f"**Moderate ITM**: Position is {itm_pct:.1f}% ITM, "
                f"intrinsic is {intrinsic_pct*100:.0f}% of premium.\n\n"
                f"V4 Philosophy: Stock could revert, but risk is increasing. "
                f"Monitor closely. Consider closing on any bounce (stock up day).\n\n"
                f"Estimated escape: {weeks_to_escape} weeks"
            )
            reason_short = f"Moderate ITM ({itm_pct:.1f}%), monitor for bounce"

            return V4EvaluationResult(
                action='HOLD',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='tactical_timing',
                has_follow_up=True,
                follow_up_condition='stock_bounces',
                follow_up_threshold=0.02,  # 2% bounce
                follow_up_action='CLOSE',
                details={
                    'itm_pct': itm_pct,
                    'intrinsic_pct': intrinsic_pct
                },
                intrinsic_pct=intrinsic_pct,
                escape_weeks=weeks_to_escape
            )

        else:
            # Deep ITM (intrinsic >80%)
            # Apply dual-benefit compression formula
            return self._evaluate_compression(
                position, itm_pct, intrinsic_pct, intrinsic_value, time_value,
                current_price, current_premium, days_to_exp, weekly_income
            )

    def _evaluate_compression(
        self,
        position,
        itm_pct: float,
        intrinsic_pct: float,
        intrinsic_value: float,
        time_value: float,
        current_price: float,
        current_premium: float,
        days_to_exp: int,
        weekly_income: Optional[float]
    ) -> V4EvaluationResult:
        """
        Evaluate whether to compress a deep ITM position to weekly.

        Dual-benefit formula:
        Total Value = Weekly Income + (Cycle Capture * Probability)
        Compress when Total Value > Compression Cost
        """
        if weekly_income is None:
            weekly_income = self.config['compression']['default_weekly_income']

        # IMPORTANT: weekly_income from OptionPremiumSetting is PER CONTRACT (total dollars).
        # All other values (current_premium, intrinsic_value, time_value) are PER SHARE.
        # Convert to per-share for consistent units.
        weekly_income_per_share = weekly_income / 100.0

        # Calculate compression value (dual benefit)
        favorable_prob = self.config['compression']['cycle_capture']['favorable_cycle_probability']

        # Benefit 1: Weekly income (per share)
        benefit_weekly = weekly_income_per_share

        # Benefit 2: Cycle capture (ability to exit on drops)
        # Estimate: if stock drops 5%, we could close at profit
        # Value this at the expected gain * probability
        cycle_capture_value = current_premium * 0.20 * favorable_prob  # 20% of premium * 60% prob

        total_value = benefit_weekly + cycle_capture_value

        # Compression cost = intrinsic value we'd crystallize by rolling to OTM
        compression_cost = intrinsic_value

        compress_ratio = total_value / compression_cost if compression_cost > 0 else float('inf')

        should_compress = compress_ratio >= self.config['compression']['consider_threshold']

        if should_compress:
            # Calculate roll targets for compression - USE ESCAPE STRIKE to get OTM
            strike = float(position.strike_price) if position.strike_price else 0.0
            option_type = getattr(position, 'option_type', 'call')
            contracts = getattr(position, 'contracts_sold', 1) or 1
            current_expiration = getattr(position, 'expiration_date', None)

            # Target: ESCAPE STRIKE (ATM or slightly OTM), next Friday
            # V4 Philosophy: Roll UP for calls (DOWN for puts) to escape ITM
            today = date.today()
            days_to_friday = (4 - today.weekday()) % 7
            if days_to_friday == 0:
                days_to_friday = 7
            new_expiration = today + timedelta(days=days_to_friday)

            # Ensure new expiration is AFTER current expiration (not same date!)
            try:
                if current_expiration:
                    # Convert to date object if needed
                    if isinstance(current_expiration, str):
                        try:
                            current_expiration = datetime.strptime(current_expiration, '%Y-%m-%d').date()
                        except:
                            pass
                    elif isinstance(current_expiration, datetime):
                        # Handle datetime objects (convert to date)
                        current_expiration = current_expiration.date()
                    elif hasattr(current_expiration, 'date'):
                        # Handle any other object with a date() method
                        current_expiration = current_expiration.date()

                    if isinstance(current_expiration, date) and new_expiration <= current_expiration:
                        # Roll to the NEXT Friday after current expiration
                        days_after = current_expiration + timedelta(days=1)
                        days_to_next_friday = (4 - days_after.weekday()) % 7
                        if days_to_next_friday == 0:
                            days_to_next_friday = 7
                        new_expiration = days_after + timedelta(days=days_to_next_friday)
            except Exception as e:
                logger.warning(f"Error calculating compression expiration for {position.symbol}: {e}, using default")
                # Keep the default new_expiration calculated above

            # Calculate escape strike - get us to ATM or slightly OTM
            new_strike = self._calculate_escape_strike(strike, current_price, option_type, is_itm=True)
            strike_change = abs(new_strike - strike)

            # Estimate net cost of the roll (per share)
            # Buy back current position at current_premium, sell new at estimated new premium
            # Rolling from deep ITM to OTM is almost always a NET DEBIT
            # because you're buying back expensive intrinsic that the new position doesn't have
            estimated_new_premium = weekly_income_per_share
            if strike_change > 0:
                # Further OTM = less premium on the new position
                premium_reduction = min(0.5, strike_change * 0.03)
                estimated_new_premium = weekly_income_per_share * (1 - premium_reduction)

            # Net: sell new - buy back current (negative = debit)
            estimated_net_credit = estimated_new_premium - current_premium

            # Format strike direction for message
            if option_type == 'call' and new_strike > strike:
                strike_direction = f"UP from ${strike:.0f} to ${new_strike:.0f}"
            elif option_type == 'put' and new_strike < strike:
                strike_direction = f"DOWN from ${strike:.0f} to ${new_strike:.0f}"
            else:
                strike_direction = f"${new_strike:.0f}"

            # Calculate per-contract amounts for display
            contracts = getattr(position, 'contracts_sold', 1) or 1
            net_per_contract = estimated_net_credit * 100  # per-share to per-contract
            total_roll_cost = net_per_contract * contracts

            reason = (
                f"**COMPRESS + Roll {strike_direction}**: Deep ITM ({itm_pct:.1f}%), "
                f"intrinsic is {intrinsic_pct*100:.0f}% of premium.\n\n"
                f"**Strategy**: Roll to weekly AND move strike to escape ITM.\n"
                f"Stock: ${current_price:.2f} | Current strike: ${strike:.0f} | New strike: ${new_strike:.0f}\n\n"
                f"**Roll Economics** (per share):\n"
                f"- Buy back current: ${current_premium:.2f}\n"
                f"- Sell new weekly: ~${estimated_new_premium:.2f}\n"
                f"- Net: {'Credit' if estimated_net_credit > 0 else 'Debit'} ${abs(estimated_net_credit):.2f}/share\n"
                f"- Total ({contracts} contract{'s' if contracts > 1 else ''}): "
                f"{'Earn' if total_roll_cost > 0 else 'Cost'} ~${abs(total_roll_cost):.0f}\n\n"
                f"**Why Compress**: Weekly income (${weekly_income_per_share:.2f}/share/week) + cycle capture "
                f"lets you recoup the debit over time.\n\n"
                f"Roll ${strike:.0f} {position.option_type} to ${new_strike:.0f} {new_expiration.strftime('%m/%d')} · "
                f"{'Earn' if total_roll_cost > 0 else 'Cost'} ~${abs(total_roll_cost):.0f}"
            )
            if strike_change > 0:
                reason_short = f"Roll {option_type} ${strike:.0f}→${new_strike:.0f} {new_expiration.strftime('%m/%d')} to escape ITM"
            else:
                reason_short = f"Compress to weekly ${new_strike:.0f} {new_expiration.strftime('%m/%d')} (value ${total_value:.2f} > cost ${compression_cost:.2f})"

            return V4EvaluationResult(
                action='COMPRESS',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='dual_benefit_compression',
                new_strike=new_strike,
                new_expiration=new_expiration,
                net_cost=-total_roll_cost,  # total dollars: negative = credit, positive = debit
                details={
                    'itm_pct': itm_pct,
                    'intrinsic_pct': intrinsic_pct,
                    'benefit_weekly': benefit_weekly,
                    'cycle_capture_value': cycle_capture_value,
                    'total_value': total_value,
                    'compression_cost': compression_cost,
                    'compress_ratio': compress_ratio,
                    'estimated_net_credit': estimated_net_credit,
                    'current_premium': current_premium,
                    'estimated_new_premium': estimated_new_premium,
                },
                intrinsic_pct=intrinsic_pct,
                compression_value=total_value,
                compression_cost=compression_cost
            )
        else:
            # Compression not worth it - close and wait for recovery
            reason = (
                f"**CLOSE + Wait for Recovery**: Deep ITM ({itm_pct:.1f}%), "
                f"but compression not favorable.\n\n"
                f"**Analysis**:\n"
                f"- Value/Cost Ratio: {compress_ratio:.2f}x (below {self.config['compression']['consider_threshold']}x threshold)\n"
                f"- Better to close now and wait for stock to recover before re-entry.\n\n"
                f"V4 Philosophy: Tactical timing - close on this move, re-enter when stock drops.\n\n"
                f"Will notify when stock drops 3% for re-entry opportunity."
            )
            reason_short = f"Deep ITM, close + wait for {position.symbol} recovery"

            return V4EvaluationResult(
                action='CLOSE',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='tactical_timing',
                has_follow_up=True,
                follow_up_condition='stock_drops_3_pct',
                follow_up_threshold=0.03,
                follow_up_action='RE_ENTER',
                details={
                    'itm_pct': itm_pct,
                    'compress_ratio': compress_ratio,
                    'wait_for_recovery': True
                },
                intrinsic_pct=intrinsic_pct
            )

    def _handle_otm_position(
        self,
        position,
        itm_pct: float,
        current_price: float,
        current_premium: float,
        profit_pct: float,
        days_to_exp: int,
        indicators
    ) -> V4EvaluationResult:
        """
        Handle OTM positions.

        V4 Approach:
        - High profit (≥80%): Close early for flexibility, or roll
        - Moderate profit: Hold, let time decay work
        - Near ATM: Monitor for potential ITM move
        """
        otm_pct = abs(itm_pct)  # OTM percentage

        if profit_pct >= 0.80:
            # High profit - consider early close for flexibility
            reason = (
                f"**Early Close for Flexibility**: {profit_pct*100:.0f}% profit captured, "
                f"position is {otm_pct:.1f}% OTM.\n\n"
                f"V4 Philosophy: Close early to gain re-entry flexibility. "
                f"Locking in {profit_pct*100:.0f}% allows repositioning.\n\n"
                f"After closing, wait for stock to pull back before selling new option."
            )
            reason_short = f"{profit_pct*100:.0f}% profit, close for flexibility"

            return V4EvaluationResult(
                action='CLOSE',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='tactical_timing',
                has_follow_up=True,
                follow_up_condition='stock_pulls_back',
                follow_up_threshold=0.02,
                follow_up_action='SELL_NEW',
                details={
                    'profit_pct': profit_pct,
                    'otm_pct': otm_pct,
                    'early_close': True
                }
            )

        elif profit_pct >= 0.60:
            # Good profit - standard roll decision
            if days_to_exp <= 7:
                # Calculate roll targets
                new_strike, new_exp, net_credit = self._calculate_roll_targets(
                    position, current_premium, current_price
                )
                strike = float(position.strike_price) if position.strike_price else 0.0
                contracts = getattr(position, 'contracts_sold', 1) or 1

                reason = (
                    f"**Roll to Next Week**: {profit_pct*100:.0f}% profit, "
                    f"expiring in {days_to_exp} days.\n\n"
                    f"V4 Philosophy: Primary goal is weekly income. "
                    f"Roll to continue earning.\n\n"
                    f"Roll ${strike:.0f} {position.option_type} to ${new_strike:.0f} {new_exp.strftime('%m/%d')}"
                )
                reason_short = f"{profit_pct*100:.0f}% profit, roll to {new_exp.strftime('%m/%d')}"

                return V4EvaluationResult(
                    action='ROLL',
                    position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                    symbol=position.symbol,
                    reason=reason,
                    reason_short=reason_short,
                    philosophy_applied='weekly_options_income',
                    new_strike=new_strike,
                    new_expiration=new_exp,
                    net_cost=-net_credit if net_credit > 0 else abs(net_credit),  # Negative = credit
                    details={
                        'profit_pct': profit_pct,
                        'days_to_exp': days_to_exp,
                        'estimated_credit': net_credit
                    }
                )
            else:
                # More time left - hold
                reason = (
                    f"**HOLD**: {profit_pct*100:.0f}% profit with {days_to_exp} days remaining.\n\n"
                    f"V4 Philosophy: Let time decay continue working. No action needed yet."
                )
                reason_short = f"{profit_pct*100:.0f}% profit, {days_to_exp}d left - hold"

                return V4EvaluationResult(
                    action='HOLD',
                    position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                    symbol=position.symbol,
                    reason=reason,
                    reason_short=reason_short,
                    philosophy_applied='weekly_options_income',
                    details={
                        'profit_pct': profit_pct,
                        'days_to_exp': days_to_exp
                    }
                )

        else:
            # Lower profit - hold and wait
            reason = (
                f"**HOLD**: {profit_pct*100:.0f}% profit, position is {otm_pct:.1f}% OTM.\n\n"
                f"V4 Philosophy: Position is working as expected. "
                f"Time decay will continue to erode premium. No action needed."
            )
            reason_short = f"{profit_pct*100:.0f}% profit, {otm_pct:.1f}% OTM - hold"

            return V4EvaluationResult(
                action='HOLD',
                position_id=str(position.id) if hasattr(position, 'id') else position.symbol,
                symbol=position.symbol,
                reason=reason,
                reason_short=reason_short,
                philosophy_applied='weekly_options_income',
                details={
                    'profit_pct': profit_pct,
                    'otm_pct': otm_pct,
                    'days_to_exp': days_to_exp
                }
            )

    def _estimate_current_premium(self, position, indicators) -> float:
        """Estimate current premium if not provided."""
        # Simple estimate based on original premium and time decay
        original_raw = getattr(position, 'original_premium', 1.0)
        original = float(original_raw) if original_raw else 1.0
        days_held = getattr(position, 'days_held', 0)
        total_days = getattr(position, 'total_days', 30)

        if total_days > 0:
            decay_factor = max(0.1, 1 - (days_held / total_days))
            return original * decay_factor
        return original * 0.5  # Default estimate

    def _fallback_evaluation(self, position) -> Optional[V4EvaluationResult]:
        """
        Fallback evaluation when technical indicators are unavailable.

        Uses stored position data (gain_loss_percent, expiration, etc.) to make
        basic recommendations. This ensures positions still get evaluated even
        when external APIs (Yahoo Finance, Schwab) are failing.
        """
        try:
            symbol = position.symbol
            strike = float(position.strike_price) if position.strike_price else 0.0
            option_type = getattr(position, 'option_type', 'call')
            contracts = getattr(position, 'contracts_sold', 1) or 1

            # Get stored gain/loss percentage from position
            gain_loss_pct = getattr(position, 'gain_loss_percent', None)
            if gain_loss_pct is not None:
                profit_pct = float(gain_loss_pct) / 100  # Convert from percentage
            else:
                profit_pct = 0.0

            # Calculate days to expiration
            today = date.today()
            exp_date = position.expiration_date
            if exp_date:
                if isinstance(exp_date, datetime):
                    exp_date = exp_date.date()
                days_to_exp = (exp_date - today).days
            else:
                days_to_exp = 7  # Default assumption

            # Get premiums for display
            original_premium = float(getattr(position, 'original_premium', 0) or 0)
            current_premium = float(getattr(position, 'premium_per_contract', 0) or 0)

            # Decision based on profit percentage and days to expiry
            # V4 Philosophy: Lock in profits ≥70%, watch positions with ≤3 days

            if profit_pct >= 0.70:
                # High profit - recommend CLOSE
                profit_captured = (original_premium - current_premium) * contracts * 100 if original_premium > current_premium else profit_pct * original_premium * contracts * 100
                cost_to_close = current_premium * contracts * 100

                reason = (
                    f"**CLOSE - Lock In Profits**: You've captured {profit_pct*100:.0f}% of the premium.\n\n"
                    f"V4 Philosophy: Don't let a winner become a loser. "
                    f"With {days_to_exp} days left, lock in your profits.\n\n"
                    f"⚠️ Note: Price data unavailable - using stored position data.\n"
                    f"Original premium: ${original_premium:.2f} | Current: ${current_premium:.2f}"
                )
                reason_short = f"{profit_pct*100:.0f}% profit - close to lock in gains"

                return V4EvaluationResult(
                    action='CLOSE',
                    position_id=str(position.id) if hasattr(position, 'id') else symbol,
                    symbol=symbol,
                    reason=reason,
                    reason_short=reason_short,
                    philosophy_applied='lock_in_profits',
                    details={
                        'profit_pct': profit_pct,
                        'days_to_exp': days_to_exp,
                        'trigger': 'fallback_high_profit',
                        'ta_unavailable': True
                    }
                )

            elif days_to_exp <= 3:
                # Expiring soon - recommend attention
                if profit_pct >= 0.50:
                    # Good profit, near expiry - consider roll or let expire
                    reason = (
                        f"**TIME CUSHION**: Position expires in {days_to_exp} days with {profit_pct*100:.0f}% profit.\n\n"
                        f"V4 Philosophy: Avoid forced assignment. Consider rolling to next week.\n\n"
                        f"⚠️ Note: Price data unavailable - check current stock price before acting."
                    )
                    reason_short = f"{days_to_exp}d to expiry, {profit_pct*100:.0f}% profit - review for roll"

                    return V4EvaluationResult(
                        action='ROLL',
                        position_id=str(position.id) if hasattr(position, 'id') else symbol,
                        symbol=symbol,
                        reason=reason,
                        reason_short=reason_short,
                        philosophy_applied='avoid_forced_assignment',
                        details={
                            'profit_pct': profit_pct,
                            'days_to_exp': days_to_exp,
                            'trigger': 'fallback_time_cushion',
                            'ta_unavailable': True
                        }
                    )
                else:
                    # Low profit, near expiry - needs attention
                    reason = (
                        f"**ATTENTION NEEDED**: Position expires in {days_to_exp} days with only {profit_pct*100:.0f}% profit.\n\n"
                        f"V4 Philosophy: Avoid forced assignment. Review current price and consider action.\n\n"
                        f"⚠️ Note: Price data unavailable - check current stock price to assess ITM status."
                    )
                    reason_short = f"{days_to_exp}d to expiry, {profit_pct*100:.0f}% profit - review needed"

                    return V4EvaluationResult(
                        action='HOLD',
                        position_id=str(position.id) if hasattr(position, 'id') else symbol,
                        symbol=symbol,
                        reason=reason,
                        reason_short=reason_short,
                        philosophy_applied='avoid_forced_assignment',
                        details={
                            'profit_pct': profit_pct,
                            'days_to_exp': days_to_exp,
                            'trigger': 'fallback_needs_attention',
                            'ta_unavailable': True
                        }
                    )

            elif profit_pct < -0.30:
                # Significant loss - flag for attention
                reason = (
                    f"**REVIEW NEEDED**: Position is showing {profit_pct*100:.0f}% loss.\n\n"
                    f"V4 Philosophy: This may indicate the position is ITM. "
                    f"Review current stock price to determine next steps.\n\n"
                    f"⚠️ Note: Price data unavailable - check stock price manually."
                )
                reason_short = f"{profit_pct*100:.0f}% loss - review for potential ITM"

                return V4EvaluationResult(
                    action='HOLD',
                    position_id=str(position.id) if hasattr(position, 'id') else symbol,
                    symbol=symbol,
                    reason=reason,
                    reason_short=reason_short,
                    philosophy_applied='tactical_timing',
                    details={
                        'profit_pct': profit_pct,
                        'days_to_exp': days_to_exp,
                        'trigger': 'fallback_significant_loss',
                        'ta_unavailable': True
                    }
                )

            else:
                # Normal position - HOLD
                reason = (
                    f"**HOLD**: Position has {profit_pct*100:.0f}% profit with {days_to_exp} days remaining.\n\n"
                    f"V4 Philosophy: Let time decay continue working.\n\n"
                    f"⚠️ Note: Price data unavailable - using stored position data."
                )
                reason_short = f"{profit_pct*100:.0f}% profit, {days_to_exp}d left - hold"

                return V4EvaluationResult(
                    action='HOLD',
                    position_id=str(position.id) if hasattr(position, 'id') else symbol,
                    symbol=symbol,
                    reason=reason,
                    reason_short=reason_short,
                    philosophy_applied='weekly_options_income',
                    details={
                        'profit_pct': profit_pct,
                        'days_to_exp': days_to_exp,
                        'trigger': 'fallback_hold',
                        'ta_unavailable': True
                    }
                )

        except Exception as e:
            logger.error(f"Fallback evaluation failed for {position.symbol}: {e}")
            return None


def get_v4_evaluator(ta_service=None, option_fetcher=None, db=None) -> V4PositionEvaluator:
    """Factory function to get V4 evaluator instance."""
    return V4PositionEvaluator(ta_service, option_fetcher, db)
