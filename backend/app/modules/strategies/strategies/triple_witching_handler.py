"""
Triple Witching Day Strategy Handler

PURPOSE: Special handling for quarterly options expiration days when stock options,
index options, and stock index futures all expire simultaneously.

OCCURS: 3rd Friday of March, June, September, and December

MARKET CHARACTERISTICS:
- 2-3x normal trading volume
- Intraday volatility spikes 150-300%
- Wide bid-ask spreads (2-5x normal)
- "Pinning" effect at major strikes
- IV inflation followed by crush at 4pm ET
- Final hour (3:00-4:00 PM ET) extreme chaos

INTEGRATION:
- This strategy automatically triggers on Triple Witching days
- It overrides normal V2 recommendations with more conservative logic
- Can be enabled/disabled via algorithm_config
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date, timedelta, time
from dataclasses import dataclass
import logging
import pytz

from app.modules.strategies.strategy_base import BaseStrategy
from app.modules.strategies.recommendations import StrategyRecommendation
# V2.2 Refactoring: Use centralized utility functions
from app.modules.strategies.utils.option_calculations import calculate_itm_status

logger = logging.getLogger(__name__)

# Timezone
ET = pytz.timezone('America/New_York')
PT = pytz.timezone('America/Los_Angeles')

# ============================================================================
# CONFIGURATION PARAMETERS
# ============================================================================

# Triple Witching Detection
TRIPLE_WITCHING_MONTHS = [3, 6, 9, 12]  # March, June, September, December
TRIPLE_WITCHING_WEEK = 3  # 3rd week of month
TRIPLE_WITCHING_DAY = 4  # Friday (0=Monday, 4=Friday)

# Thresholds (MORE CONSERVATIVE than normal days)
SHALLOW_ITM_THRESHOLD_WITCHING = 3.0  # vs 5.0 normal
DEEP_ITM_THRESHOLD_WITCHING = 10.0  # vs 15.0 normal
NEAR_MONEY_THRESHOLD_WITCHING = 2.0  # vs 3.0 normal
SAFE_OTM_THRESHOLD_WITCHING = 5.0  # vs 3.0 normal

# Timing Windows (all times in ET)
OPENING_CHAOS_START = time(6, 30)
OPENING_CHAOS_END = time(7, 0)
MORNING_WINDOW_START = time(7, 0)
MORNING_WINDOW_END = time(10, 30)
BEST_WINDOW_START = time(10, 30)
BEST_WINDOW_END = time(14, 30)
CLOSING_SAFE_DEADLINE = time(14, 30)
FINAL_HOUR_START = time(15, 0)
MARKET_CLOSE = time(16, 0)

# Execution Quality
EXPECTED_SPREAD_MULTIPLE = 2.5  # Spreads are 2.5x normal
EXPECTED_FILL_TIME_MULTIPLE = 3  # Fills take 3x longer
MIN_SLIPPAGE_PER_CONTRACT = 50  # Minimum $50 slippage expected
MAX_SLIPPAGE_PER_CONTRACT = 150  # Maximum $150 slippage expected

# Roll Criteria (MORE STRICT)
MAX_ROLL_DURATION_WITCHING = 4  # Max 4 weeks (vs 6-8 normal)
MAX_ROLL_ITM_PCT = 3.0  # Only roll if <3% ITM
MIN_STRIKE_BUFFER_PCT = 10.0  # New strike must be 10%+ away

# Alert Thresholds
DANGER_ZONE_BUFFER = 0.02  # Alert when within 2% of strike
SAFE_ZONE_BUFFER = 0.05  # Alert when 5% away from strike
DISASTER_ZONE = 0.03  # Alert when 3% ITM

# Strategy Overrides
HIGH_VIX_THRESHOLD = 25


# ============================================================================
# DETECTION FUNCTIONS
# ============================================================================

def is_triple_witching(check_date: date = None) -> bool:
    """
    Detect if given date is Triple Witching Day.
    
    Returns True if it's the 3rd Friday of Mar, Jun, Sep, or Dec
    """
    if check_date is None:
        check_date = date.today()
    
    # Must be Friday
    if check_date.weekday() != 4:
        return False
    
    # Must be Mar, Jun, Sep, or Dec
    if check_date.month not in TRIPLE_WITCHING_MONTHS:
        return False
    
    # Find the 3rd Friday of the month
    first_day = check_date.replace(day=1)
    # Find first Friday
    days_until_friday = (4 - first_day.weekday()) % 7
    first_friday = first_day + timedelta(days=days_until_friday)
    # Third Friday is 2 weeks later
    third_friday = first_friday + timedelta(days=14)
    
    return check_date == third_friday


def get_next_triple_witching() -> date:
    """
    Find the next Triple Witching date.
    """
    today = date.today()
    
    # Check remaining months this year
    for month in TRIPLE_WITCHING_MONTHS:
        if month < today.month:
            continue
        
        # Calculate third Friday of this month
        first_day = date(today.year, month, 1)
        days_until_friday = (4 - first_day.weekday()) % 7
        first_friday = first_day + timedelta(days=days_until_friday)
        third_friday = first_friday + timedelta(days=14)
        
        if third_friday >= today:
            return third_friday
    
    # If no more this year, return March of next year
    first_day = date(today.year + 1, 3, 1)
    days_until_friday = (4 - first_day.weekday()) % 7
    first_friday = first_day + timedelta(days=days_until_friday)
    third_friday = first_friday + timedelta(days=14)
    return third_friday


def days_until_triple_witching() -> int:
    """Get number of days until next Triple Witching."""
    return (get_next_triple_witching() - date.today()).days


def get_current_window_et() -> Dict[str, Any]:
    """
    Get current trading window status in ET.
    """
    now_et = datetime.now(ET)
    current_time = now_et.time()
    
    if current_time < OPENING_CHAOS_START:
        return {
            "window": "PRE_MARKET",
            "quality": "N/A",
            "can_trade": False,
            "message": "Pre-market - Wait for market open"
        }
    elif OPENING_CHAOS_START <= current_time < OPENING_CHAOS_END:
        return {
            "window": "OPENING_CHAOS",
            "quality": "POOR",
            "can_trade": False,
            "message": "🔴 Opening chaos - DO NOT TRADE"
        }
    elif OPENING_CHAOS_END <= current_time < MORNING_WINDOW_END:
        return {
            "window": "MORNING",
            "quality": "FAIR",
            "can_trade": True,
            "message": "🟡 Morning window - Acceptable for closing disasters"
        }
    elif BEST_WINDOW_START <= current_time < BEST_WINDOW_END:
        return {
            "window": "BEST",
            "quality": "GOOD",
            "can_trade": True,
            "message": "🟢 Best trading window - Primary execution time"
        }
    elif BEST_WINDOW_END <= current_time < FINAL_HOUR_START:
        return {
            "window": "CLOSING",
            "quality": "FAIR",
            "can_trade": True,
            "message": "🟡 Last chance to close risky positions"
        }
    elif FINAL_HOUR_START <= current_time < MARKET_CLOSE:
        return {
            "window": "FINAL_HOUR",
            "quality": "TERRIBLE",
            "can_trade": False,
            "message": "🔴 Final hour - DO NOT TRADE"
        }
    else:
        return {
            "window": "AFTER_HOURS",
            "quality": "N/A",
            "can_trade": False,
            "message": "After hours - Wait for Monday"
        }


# ============================================================================
# POSITION ANALYSIS
# ============================================================================

@dataclass
class TripleWitchingAnalysis:
    """Analysis result for a position on Triple Witching day."""
    symbol: str
    strike: float
    option_type: str
    expiration: date
    contracts: int
    account_name: Optional[str]
    
    # Position state
    stock_price: float
    is_itm: bool
    itm_otm_pct: float  # Positive = OTM, Negative = ITM
    expires_today: bool
    
    # Recommendation
    action: str  # CLOSE_MORNING, CLOSE_MIDDAY, MONITOR, LET_EXPIRE, etc.
    priority: str  # urgent, high, medium, low
    timing: str
    message: str
    rationale: str
    avoid_windows: List[str]
    
    # Roll guidance (if applicable)
    roll_allowed: bool
    roll_criteria: Optional[Dict[str, Any]]
    alternative_action: Optional[str]


def analyze_expiring_position_on_triple_witching(
    position,
    stock_price: float
) -> TripleWitchingAnalysis:
    """
    Determine action for positions expiring on Triple Witching Day.
    """
    strike = position.strike_price
    option_type = position.option_type.lower()
    expires_today = position.expiration_date == date.today()
    
    # V2.2: Use centralized ITM calculation
    itm_calc = calculate_itm_status(stock_price, strike, option_type)
    is_itm = itm_calc['is_itm']
    itm_pct = itm_calc['itm_pct']
    otm_pct = itm_calc['otm_pct']
    # itm_otm_pct: negative for ITM, positive for OTM
    itm_otm_pct = -itm_pct if is_itm else otm_pct
    
    # Base analysis structure
    base = {
        "symbol": position.symbol,
        "strike": strike,
        "option_type": option_type,
        "expiration": position.expiration_date,
        "contracts": position.contracts,
        "account_name": position.account_name,
        "stock_price": stock_price,
        "is_itm": is_itm,
        "itm_otm_pct": itm_otm_pct,
        "expires_today": expires_today,
    }
    
    # Decision tree for positions expiring today
    if expires_today:
        if is_itm:
            itm_pct = abs(itm_otm_pct)
            
            if itm_pct > DEEP_ITM_THRESHOLD_WITCHING:
                # Deep ITM - disaster territory
                return TripleWitchingAnalysis(
                    **base,
                    action='CLOSE_MORNING',
                    priority='urgent',
                    timing='7:00-10:00 AM ET (after opening chaos settles)',
                    message=f'🚨 TRIPLE WITCHING: {itm_pct:.1f}% ITM - Close in morning session',
                    rationale='Deep ITM - accept assignment or close early, do not try to fix in chaos',
                    avoid_windows=['6:30-7:00 AM ET (opening)', '3:00-4:00 PM ET (final hour)'],
                    roll_allowed=False,
                    roll_criteria=None,
                    alternative_action='Accept assignment'
                )
            elif itm_pct <= SHALLOW_ITM_THRESHOLD_WITCHING:
                # Shallow ITM - tactical roll possible
                return TripleWitchingAnalysis(
                    **base,
                    action='CLOSE_OR_ROLL_MIDDAY',
                    priority='high',
                    timing='10:00 AM - 2:30 PM ET',
                    message=f'⚠️ TRIPLE WITCHING: {itm_pct:.1f}% ITM - Consider tactical roll',
                    rationale='Shallow ITM - rolling to higher strike may make sense',
                    avoid_windows=['6:30-7:00 AM ET', '3:00-4:00 PM ET'],
                    roll_allowed=True,
                    roll_criteria={
                        'max_itm_for_roll': MAX_ROLL_ITM_PCT,
                        'new_strike_buffer': MIN_STRIKE_BUFFER_PCT,
                        'max_roll_duration': MAX_ROLL_DURATION_WITCHING,
                        'require_credit': False
                    },
                    alternative_action='Close position and redeploy Monday'
                )
            else:
                # Medium ITM (3-10%)
                return TripleWitchingAnalysis(
                    **base,
                    action='CLOSE_MIDDAY',
                    priority='high',
                    timing='10:00 AM - 2:30 PM ET',
                    message=f'⚠️ TRIPLE WITCHING: {itm_pct:.1f}% ITM - Close before 3 PM',
                    rationale='Medium ITM - close to avoid final hour chaos',
                    avoid_windows=['3:00-4:00 PM ET'],
                    roll_allowed=False,
                    roll_criteria=None,
                    alternative_action='Accept assignment if you miss window'
                )
        else:
            # OTM positions
            otm_pct = abs(itm_otm_pct)
            
            if otm_pct > SAFE_OTM_THRESHOLD_WITCHING:
                # Very safe
                return TripleWitchingAnalysis(
                    **base,
                    action='LET_EXPIRE',
                    priority='low',
                    timing='No action needed',
                    message=f'✅ TRIPLE WITCHING: {otm_pct:.1f}% OTM - Let expire safely',
                    rationale='Far OTM - volatility works in your favor, save commissions',
                    avoid_windows=[],
                    roll_allowed=False,
                    roll_criteria=None,
                    alternative_action=None
                )
            elif otm_pct >= NEAR_MONEY_THRESHOLD_WITCHING:
                # Probably safe, but watch
                return TripleWitchingAnalysis(
                    **base,
                    action='MONITOR',
                    priority='medium',
                    timing='Watch final hour',
                    message=f'🟡 TRIPLE WITCHING: {otm_pct:.1f}% OTM - Monitor for pinning',
                    rationale='Close to strike - watch for pinning effect in final hour',
                    avoid_windows=['3:00-4:00 PM ET (highest pinning risk)'],
                    roll_allowed=False,
                    roll_criteria=None,
                    alternative_action='Close if stock moves within 1% of strike'
                )
            else:
                # Too close, pinning risk
                return TripleWitchingAnalysis(
                    **base,
                    action='CLOSE_BEFORE_FINAL_HOUR',
                    priority='high',
                    timing='10:00 AM - 2:30 PM ET',
                    message=f'⚠️ TRIPLE WITCHING: {otm_pct:.1f}% OTM - Close before 3 PM',
                    rationale='Too close to strike - pinning could push you ITM in final hour',
                    avoid_windows=['3:00-4:00 PM ET (highest pinning risk)'],
                    roll_allowed=False,
                    roll_criteria=None,
                    alternative_action='Let expire if you miss window (risky)'
                )
    else:
        # Position NOT expiring today
        return TripleWitchingAnalysis(
            **base,
            action='WAIT_FOR_MONDAY',
            priority='low',
            timing='No action needed today',
            message='✅ Not expiring today - No action needed',
            rationale='Position has time, avoid Triple Witching chaos',
            avoid_windows=[],
            roll_allowed=False,
            roll_criteria=None,
            alternative_action='Review Monday'
        )


# ============================================================================
# SELLING NEW OPTIONS GUIDANCE
# ============================================================================

def recommend_timing_for_new_sales_on_triple_witching(vix: float = 18.0) -> Dict[str, Any]:
    """
    Optimize timing for selling new options on Triple Witching Day.
    """
    current_window = get_current_window_et()
    recommendations = []
    
    # Time-based recommendations
    if current_window["window"] == "OPENING_CHAOS":
        if vix > HIGH_VIX_THRESHOLD:
            recommendations.append({
                'window': 'MORNING_AGGRESSIVE',
                'timing': 'NOW (high IV)',
                'action': 'CONSIDER_SELLING',
                'message': '🟢 Morning IV spike - Good time to sell premium',
                'strategy': 'Use limit orders 10-15% above mid, volatility is elevated',
                'caution': 'Use limits only, do not use market orders',
                'quality': 'GOOD'
            })
        else:
            recommendations.append({
                'window': 'MORNING_CHAOS',
                'timing': 'WAIT',
                'action': 'DO_NOT_SELL',
                'message': '🔴 Opening chaos - Wait for stability',
                'strategy': 'Wait until 10:30 AM for volatility to settle',
                'rationale': 'Price discovery in progress, poor fills likely',
                'quality': 'POOR'
            })
    
    elif current_window["window"] in ["MORNING", "BEST"]:
        if current_window["window"] == "BEST":
            recommendations.append({
                'window': 'MIDDAY_CALM',
                'timing': 'NOW to 2:30 PM',
                'action': 'ACCEPTABLE_WINDOW',
                'message': '🟡 Midday window - Acceptable time to sell',
                'strategy': 'Use limit orders, start at mid, be patient',
                'caution': 'IV may be inflated vs normal days - premiums might look fat but could crush',
                'quality': 'ACCEPTABLE'
            })
        else:
            recommendations.append({
                'window': 'MORNING_WINDOW',
                'timing': 'Consider waiting until 10:30 AM',
                'action': 'WAIT_OR_ACCEPTABLE',
                'message': '🟡 Morning window - Fair conditions',
                'strategy': 'If urgent, use limit orders. Otherwise wait for best window.',
                'quality': 'FAIR'
            })
    
    elif current_window["window"] in ["CLOSING", "FINAL_HOUR"]:
        recommendations.append({
            'window': 'FINAL_HOUR',
            'timing': 'WAIT',
            'action': 'DO_NOT_SELL',
            'message': '🔴 Final hour chaos - DO NOT SELL',
            'strategy': 'Wait until Monday for clean pricing',
            'rationale': 'Worst fills of the day, extreme volatility, pinning effects',
            'quality': 'TERRIBLE'
        })
    
    else:
        # After hours or pre-market
        recommendations.append({
            'window': 'OUTSIDE_HOURS',
            'timing': 'WAIT_FOR_MONDAY',
            'action': 'OPTIMAL_TIMING',
            'message': '✅ BEST STRATEGY: Wait until Monday',
            'strategy': 'Monday will have normalized IV, clean pricing, better execution',
            'rationale': 'Triple Witching IV crush happens at 4 PM, Monday = clean slate',
            'quality': 'BEST'
        })
    
    # Overall recommendation
    best_strategy = {
        'PRIMARY_RECOMMENDATION': 'Wait until Monday',
        'rationale': [
            'IV crush at 4 PM makes Sunday/Monday premiums lower (bad for selling)',
            'BUT execution quality is much better (good for you)',
            'Holiday weeks may have compressed premiums',
            'Net result: Usually better to wait unless morning IV spike >VIX 25'
        ],
        'exception': f'If VIX >{HIGH_VIX_THRESHOLD} in morning window, sell aggressively into the IV spike'
    }
    
    return {
        'is_triple_witching': True,
        'current_window': current_window,
        'current_recommendations': recommendations,
        'overall_strategy': best_strategy,
        'vix': vix
    }


# ============================================================================
# EXECUTION GUIDANCE
# ============================================================================

def get_triple_witching_execution_guidance(
    action_type: str,
    bid: float,
    ask: float
) -> Dict[str, Any]:
    """
    Provide execution guidance specific to Triple Witching conditions.
    
    action_type: 'close', 'roll', 'sell_new'
    """
    current_window = get_current_window_et()
    mid = (bid + ask) / 2
    spread = ask - bid
    
    guidance = {
        'general_rules': [
            '❌ NEVER use market orders',
            '⏱️ Be patient - fills take 2-5x longer than normal',
            '📊 Start limits further from mid than usual',
            '🎯 Accept that you will give up more to slippage',
            '⚡ Be ready to cancel and wait for Monday if fills are terrible'
        ],
        'current_window': current_window,
        'spread_info': {
            'bid': bid,
            'ask': ask,
            'mid': mid,
            'spread': spread,
            'spread_pct': (spread / mid * 100) if mid > 0 else 0,
            'expected_witching_spread': spread * EXPECTED_SPREAD_MULTIPLE
        }
    }
    
    if not current_window["can_trade"]:
        guidance['strategy'] = {
            'recommendation': 'DO_NOT_TRADE_NOW',
            'message': current_window["message"],
            'wait_until': 'Next trading window or Monday'
        }
        return guidance
    
    if action_type == 'close':
        # Closing a short position (buying it back)
        if current_window["window"] == "MORNING":
            guidance['strategy'] = {
                'window': 'Morning',
                'start_price': round(mid + (spread * 0.35), 2),  # 35% toward ask vs 25% normal
                'adjustment': 'Move toward ask more aggressively than normal day',
                'patience': 'Wait 3-5 minutes between adjustments (vs 2 min normal)',
                'max_price': ask,
                'expected_fill': round(mid + (spread * 0.40), 2)
            }
        else:  # BEST window
            guidance['strategy'] = {
                'window': 'Midday',
                'start_price': round(mid + (spread * 0.25), 2),
                'adjustment': 'Walk toward ask slowly',
                'patience': 'Wait 3-5 minutes between adjustments',
                'max_price': round(ask - (spread * 0.1), 2),
                'expected_fill': round(mid + (spread * 0.30), 2)
            }
    
    elif action_type == 'sell_new':
        # Selling to open new position
        if current_window["window"] == "MORNING":
            guidance['strategy'] = {
                'window': 'Morning',
                'start_price': round(ask - (spread * 0.15), 2),  # Closer to ask than normal
                'adjustment': 'Start high, you have leverage if IV is elevated',
                'patience': 'Wait 5 minutes, then walk down to mid',
                'min_price': round(mid + (spread * 0.10), 2),
                'expected_fill': round(mid + (spread * 0.20), 2)
            }
        else:  # BEST window
            guidance['strategy'] = {
                'window': 'Midday',
                'start_price': round(mid + (spread * 0.20), 2),
                'adjustment': 'Be more aggressive than normal, volatility is elevated',
                'patience': 'Walk down to mid over 5-10 minutes',
                'min_price': mid,
                'expected_fill': round(mid + (spread * 0.10), 2)
            }
    
    elif action_type == 'roll':
        guidance['strategy'] = {
            'method': 'SEQUENTIAL ONLY',
            'message': 'Do NOT use spread orders on Triple Witching',
            'steps': [
                '1. Close old position first (see close guidance above)',
                '2. Wait for fill confirmation',
                '3. Then sell new position (see sell_new guidance above)',
                '4. NEVER execute both legs simultaneously today'
            ],
            'timing': '10:00 AM - 2:30 PM ET only',
            'alternative': 'Consider closing today, selling new Monday for better fills'
        }
    
    return guidance


# ============================================================================
# STRATEGY OVERRIDE FUNCTIONS
# ============================================================================

def apply_triple_witching_overrides(
    recommendation: Dict[str, Any],
    position,
    vix: float = 18.0
) -> Dict[str, Any]:
    """
    Modify standard V2 recommendations for Triple Witching Day.
    
    Overrides apply when is_triple_witching(today) == True
    """
    if not is_triple_witching():
        return recommendation  # No overrides needed
    
    # Add Triple Witching marker
    recommendation['is_triple_witching'] = True
    
    # Override 1: Never recommend rolling on Triple Witching unless shallow ITM
    strategy = recommendation.get('type', '') or recommendation.get('strategy', '')
    
    if 'roll' in strategy.lower():
        # Calculate ITM percentage
        stock_price = recommendation.get('context', {}).get('current_price', 0)
        strike = recommendation.get('context', {}).get('current_strike', 0)
        option_type = recommendation.get('context', {}).get('option_type', 'call')
        
        if stock_price and strike:
            # V2.2: Use centralized ITM calculation
            itm_calc = calculate_itm_status(stock_price, strike, option_type)
            itm_pct = itm_calc['itm_pct']
            intrinsic_value = itm_calc['intrinsic_value']
            
            if itm_pct > SHALLOW_ITM_THRESHOLD_WITCHING:
                # Get symbol info for title
                symbol = recommendation.get('context', {}).get('symbol', recommendation.get('symbol', ''))
                buy_back_cost = recommendation.get('context', {}).get('buy_back_cost', 0)
                buy_back_total = recommendation.get('context', {}).get('buy_back_total', 0)
                
                recommendation['action'] = 'CLOSE_DONT_ROLL'
                recommendation['title'] = f"🔴 TRIPLE WITCHING: CLOSE {symbol} - {itm_pct:.1f}% ITM (Don't roll today)"
                
                recommendation['triple_witching_override'] = {
                    'original_action': 'roll',
                    'new_action': 'CLOSE_DONT_ROLL',
                    'original_title': recommendation.get('title', ''),
                    'reason': 'Too deep ITM to roll on Triple Witching - poor fills expected',
                    'alternative': 'Close today (10 AM-2:30 PM ET), sell fresh Monday for better execution',
                    'itm_pct': round(itm_pct, 1),
                    'intrinsic_value': round(intrinsic_value, 2),
                    'close_cost_per_share': round(buy_back_cost, 2) if buy_back_cost else round(intrinsic_value * 1.05, 2),
                    'close_cost_total': round(buy_back_total, 2) if buy_back_total else None,
                }
                
                # IMPORTANT: Flag to hide roll options table in UI
                recommendation['hide_roll_options'] = True
                recommendation['show_close_guidance'] = True
    
    # Override 2: Adjust profit thresholds for expiring positions
    if recommendation.get('type') == 'early_roll_opportunity':
        position_exp = recommendation.get('context', {}).get('current_expiration')
        if position_exp:
            try:
                exp_date = date.fromisoformat(position_exp) if isinstance(position_exp, str) else position_exp
                if exp_date == date.today():
                    profit_pct = recommendation.get('context', {}).get('profit_percent', 0) / 100
                    if profit_pct >= 0.50:  # 50%+ profit
                        recommendation['action'] = 'CLOSE_DONT_ROLL'
                        recommendation['triple_witching_override'] = {
                            'reason': "Take 50%+ profit, don't roll on Triple Witching",
                            'timing': '10:00 AM - 2:30 PM ET'
                        }
            except (ValueError, TypeError):
                pass
    
    # Override 3: Adjust execution timing
    current_window = get_current_window_et()
    
    if current_window["window"] == "OPENING_CHAOS":
        recommendation['timing_override'] = 'WAIT_FOR_STABILITY'
        if recommendation.get('description'):
            recommendation['description'] += '\n⏸️ Wait until 7:00 AM ET for opening chaos to settle'
    
    if current_window["window"] == "FINAL_HOUR":
        recommendation['timing_override'] = 'TOO_LATE_TODAY'
        recommendation['priority'] = 'low'  # Can't act anyway
        if recommendation.get('description'):
            recommendation['description'] += '\n🔴 Final hour - do not trade, wait for Monday'
    
    # Override 4: Add comprehensive execution guidance for Triple Witching
    # (reusing current_window from above)
    recommendation['triple_witching_execution'] = {
        'is_triple_witching': True,
        'current_window': current_window['window'],
        'window_quality': current_window['quality'],
        'window_message': current_window['message'],
        
        # Time windows in ET
        'best_window': '10:30 AM - 2:30 PM ET',
        'avoid_windows': [
            '6:30-7:00 AM ET (opening chaos)',
            '3:00-4:00 PM ET (final hour - extreme pinning)'
        ],
        
        # Slippage expectations
        'expected_slippage': f'${MIN_SLIPPAGE_PER_CONTRACT}-{MAX_SLIPPAGE_PER_CONTRACT} per contract',
        'slippage_vs_normal': f'{EXPECTED_SPREAD_MULTIPLE}x normal spreads',
        'fill_time': f'{EXPECTED_FILL_TIME_MULTIPLE}x longer fills',
        
        # Execution strategy
        'execution_strategy': [
            'Use LIMIT orders only - NEVER market orders',
            'Start at mid price, be prepared to adjust',
            'Wait 3-5 minutes between price adjustments',
            'Accept some slippage to get filled'
        ],
        
        # Why act today vs Monday
        'timing_rationale': (
            'Close today to free margin and avoid assignment risk. '
            'Monday will have normalized IV but you need to act now for ITM positions.'
        ),
        
        # Specific guidance based on action
        'close_guidance': {
            'start_price': 'Mid price',
            'max_price': 'Ask (if urgent)',
            'adjustment_interval': '3-5 minutes',
            'expected_fill_location': 'Mid + 25-40% of spread'
        }
    }
    
    # Legacy caution field for backwards compatibility
    recommendation['triple_witching_caution'] = {
        'expected_slippage': f'${MIN_SLIPPAGE_PER_CONTRACT}-{MAX_SLIPPAGE_PER_CONTRACT} per contract',
        'spread_multiplier': f'{EXPECTED_SPREAD_MULTIPLE}x normal',
        'fill_time': f'{EXPECTED_FILL_TIME_MULTIPLE}x longer than normal',
        'recommendation': 'Use limit orders only, be very patient'
    }
    
    # Override 5: Selling new options - default to Monday
    if recommendation.get('type') in ['sell_unsold_contracts', 'new_covered_call']:
        if vix < HIGH_VIX_THRESHOLD:
            recommendation['action'] = 'WAIT_FOR_MONDAY'
            recommendation['triple_witching_override'] = {
                'reason': 'IV will normalize Monday, better fills, cleaner pricing',
                'vix': vix,
                'threshold': HIGH_VIX_THRESHOLD
            }
        else:
            recommendation['timing'] = '10:30 AM - 2:30 PM ET (if VIX >25)'
            recommendation['triple_witching_override'] = {
                'reason': f'High VIX ({vix:.1f}) - opportunity to sell premium, but use caution'
            }
    
    return recommendation


# ============================================================================
# STRATEGY CLASS
# ============================================================================

class TripleWitchingStrategy(BaseStrategy):
    """
    Triple Witching Day Strategy
    
    Generates special alerts and recommendations on Triple Witching days.
    Also provides overrides for other strategies.
    """
    
    strategy_type = "triple_witching"
    name = "Triple Witching Handler"
    description = "Special handling for quarterly Triple Witching expiration days"
    category = "risk_management"
    default_parameters = {
        "enabled": True,
        "alert_days_before": 1,  # Alert 1 day before Triple Witching
    }
    
    def generate_recommendations(self, params: Dict[str, Any]) -> List[StrategyRecommendation]:
        """Generate Triple Witching alerts and recommendations."""
        recommendations = []
        
        today = date.today()
        is_witching = is_triple_witching(today)
        days_until = days_until_triple_witching()
        alert_days = self.get_parameter("alert_days_before", 1)
        
        # Check if we should alert
        if not is_witching and days_until > alert_days:
            return recommendations  # Not near Triple Witching
        
        # Get positions from database
        from app.modules.strategies.option_monitor import get_positions_from_db
        positions = get_positions_from_db(self.db)
        
        if not positions:
            return recommendations
        
        # Get technical analysis service for prices
        from app.modules.strategies.technical_analysis import get_technical_analysis_service
        ta_service = get_technical_analysis_service()
        
        # Generate alerts based on context
        if is_witching:
            # IT'S TRIPLE WITCHING DAY
            recommendations.extend(
                self._generate_witching_day_alerts(positions, ta_service)
            )
        elif days_until == 1:
            # DAY BEFORE TRIPLE WITCHING
            recommendations.append(
                self._generate_eve_alert(positions)
            )
        
        return recommendations
    
    def _generate_witching_day_alerts(
        self,
        positions,
        ta_service
    ) -> List[StrategyRecommendation]:
        """Generate alerts for Triple Witching day."""
        recommendations = []
        today = date.today()
        current_window = get_current_window_et()
        
        # Categorize positions
        expiring_today = [p for p in positions if p.expiration_date == today]
        not_expiring = [p for p in positions if p.expiration_date != today]
        
        # Analyze each expiring position
        urgent_positions = []
        watch_positions = []
        safe_positions = []
        
        for position in expiring_today:
            try:
                indicators = ta_service.get_technical_indicators(position.symbol)
                if not indicators:
                    continue
                
                analysis = analyze_expiring_position_on_triple_witching(
                    position, indicators.current_price
                )
                
                if analysis.priority == 'urgent':
                    urgent_positions.append(analysis)
                elif analysis.priority == 'high':
                    watch_positions.append(analysis)
                else:
                    safe_positions.append(analysis)
            except Exception as e:
                logger.error(f"Error analyzing {position.symbol} for Triple Witching: {e}")
                continue
        
        # Generate master alert
        master_alert = self._generate_master_alert(
            expiring_today, urgent_positions, watch_positions, safe_positions, current_window
        )
        if master_alert:
            recommendations.append(master_alert)
        
        # Generate individual alerts for urgent positions
        for analysis in urgent_positions:
            rec = self._analysis_to_recommendation(analysis)
            if rec:
                recommendations.append(rec)
        
        # Generate timing guidance for new sales
        if not_expiring or (len(expiring_today) < len(positions)):
            timing_rec = self._generate_timing_alert(current_window)
            if timing_rec:
                recommendations.append(timing_rec)
        
        return recommendations
    
    def _generate_master_alert(
        self,
        expiring_positions,
        urgent,
        watch,
        safe,
        current_window
    ) -> Optional[StrategyRecommendation]:
        """Generate master Triple Witching summary alert."""
        if not expiring_positions:
            return None
        
        title = f"🔴 TRIPLE WITCHING DAY - {len(expiring_positions)} positions expiring"
        
        # Build summary
        summary_parts = [
            f"**{len(urgent)} URGENT** - Need immediate action",
            f"**{len(watch)} WATCH** - Monitor closely",
            f"**{len(safe)} SAFE** - Can let expire",
            "",
            f"**Current Window**: {current_window['message']}",
        ]
        
        if urgent:
            summary_parts.extend([
                "",
                "**URGENT POSITIONS:**",
            ])
            for a in urgent[:5]:  # Show top 5
                summary_parts.append(f"• {a.symbol} ${a.strike} {a.option_type} - {a.message}")
        
        description = "\n".join(summary_parts)
        
        # Trading windows
        rationale_parts = [
            "**TRADING WINDOWS TODAY:**",
            "🔴 6:30-7:00 AM ET - DO NOT TRADE (opening chaos)",
            "🟡 7:00-10:30 AM ET - Fair (close disasters only)",
            "🟢 10:30 AM-2:30 PM ET - BEST (primary window)",
            "🟡 2:30-3:00 PM ET - Fair (last chance)",
            "🔴 3:00-4:00 PM ET - DO NOT TRADE (final hour)",
            "",
            "**CRITICAL REMINDERS:**",
            "• NEVER use market orders",
            "• Expect 2-3x normal spreads",
            "• Fills take 5-10 minutes",
            "• Accept higher slippage today",
        ]
        
        rationale = "\n".join(rationale_parts)
        
        return StrategyRecommendation(
            id=f"triple_witching_master_{date.today().isoformat()}",
            type=self.strategy_type,
            category=self.category,
            priority="urgent" if urgent else "high",
            title=title,
            description=description,
            rationale=rationale,
            action=f"Review {len(urgent)} urgent positions in best window (10:30 AM - 2:30 PM ET)",
            action_type="alert",
            potential_income=None,
            potential_risk="high",
            time_horizon="today",
            symbol=None,
            account_name=None,
            context={
                "is_triple_witching": True,
                "expiring_count": len(expiring_positions),
                "urgent_count": len(urgent),
                "watch_count": len(watch),
                "safe_count": len(safe),
                "current_window": current_window,
                "trading_windows": {
                    "avoid": ["6:30-7:00 AM ET", "3:00-4:00 PM ET"],
                    "best": "10:30 AM - 2:30 PM ET"
                }
            },
            expires_at=datetime.combine(date.today(), time(16, 0))
        )
    
    def _analysis_to_recommendation(
        self,
        analysis: TripleWitchingAnalysis
    ) -> Optional[StrategyRecommendation]:
        """Convert analysis to recommendation."""
        account_slug = (analysis.account_name or "unknown").replace(" ", "_").replace("'", "")
        
        return StrategyRecommendation(
            id=f"triple_witching_{analysis.symbol}_{analysis.strike}_{date.today().isoformat()}_{account_slug}",
            type=self.strategy_type,
            category=self.category,
            priority=analysis.priority,
            title=analysis.message,
            description=f"{analysis.symbol} ${analysis.strike} {analysis.option_type} - {analysis.rationale}",
            rationale=f"Stock at ${analysis.stock_price:.2f}. {analysis.rationale}",
            action=f"{analysis.action}: {analysis.timing}",
            action_type="alert",
            potential_income=None,
            potential_risk="high" if analysis.is_itm else "medium",
            time_horizon="today",
            symbol=analysis.symbol,
            account_name=analysis.account_name,
            context={
                "is_triple_witching": True,
                "stock_price": analysis.stock_price,
                "strike": analysis.strike,
                "itm_otm_pct": analysis.itm_otm_pct,
                "is_itm": analysis.is_itm,
                "action": analysis.action,
                "timing": analysis.timing,
                "avoid_windows": analysis.avoid_windows,
                "roll_allowed": analysis.roll_allowed,
                "roll_criteria": analysis.roll_criteria,
                "alternative": analysis.alternative_action
            },
            expires_at=datetime.combine(date.today(), time(16, 0))
        )
    
    def _generate_timing_alert(
        self,
        current_window: Dict[str, Any]
    ) -> Optional[StrategyRecommendation]:
        """Generate alert about selling new options timing."""
        timing_guidance = recommend_timing_for_new_sales_on_triple_witching()
        
        if current_window["window"] in ["FINAL_HOUR", "AFTER_HOURS"]:
            message = "✅ TRIPLE WITCHING: Wait until Monday to sell new options"
            priority = "low"
        elif current_window["window"] == "BEST":
            message = "🟡 TRIPLE WITCHING: Acceptable window to sell (10:30 AM - 2:30 PM ET)"
            priority = "medium"
        else:
            message = "⏸️ TRIPLE WITCHING: Wait for better window or Monday"
            priority = "low"
        
        return StrategyRecommendation(
            id=f"triple_witching_timing_{date.today().isoformat()}",
            type=self.strategy_type,
            category=self.category,
            priority=priority,
            title=message,
            description="Triple Witching Day affects option pricing and execution quality",
            rationale=timing_guidance["overall_strategy"]["PRIMARY_RECOMMENDATION"],
            action="Use limit orders only, expect wider spreads",
            action_type="alert",
            potential_income=None,
            potential_risk="low",
            time_horizon="today",
            symbol=None,
            account_name=None,
            context={
                "is_triple_witching": True,
                "timing_guidance": timing_guidance,
                "current_window": current_window
            },
            expires_at=datetime.combine(date.today(), time(16, 0))
        )
    
    def _generate_eve_alert(
        self,
        positions
    ) -> StrategyRecommendation:
        """Generate day-before Triple Witching alert."""
        next_witching = get_next_triple_witching()
        expiring_on_witching = [
            p for p in positions if p.expiration_date == next_witching
        ]
        
        return StrategyRecommendation(
            id=f"triple_witching_eve_{date.today().isoformat()}",
            type=self.strategy_type,
            category=self.category,
            priority="high",
            title=f"⚠️ TRIPLE WITCHING TOMORROW - {len(expiring_on_witching)} positions expiring",
            description=(
                f"Tomorrow ({next_witching.strftime('%b %d')}) is Triple Witching Day.\n"
                f"You have {len(expiring_on_witching)} positions expiring.\n\n"
                "PREPARE NOW:\n"
                "• Review positions near the money\n"
                "• Set price alerts\n"
                "• Plan action for ITM positions\n"
                "• Prepare limit orders (don't submit yet)"
            ),
            rationale=(
                "Triple Witching = 2-3x volume, 150-300% volatility, wide spreads. "
                "Best to prepare today rather than react tomorrow."
            ),
            action="Review expiring positions and prepare action plan",
            action_type="alert",
            potential_income=None,
            potential_risk="medium",
            time_horizon="tomorrow",
            symbol=None,
            account_name=None,
            context={
                "triple_witching_date": next_witching.isoformat(),
                "expiring_count": len(expiring_on_witching),
                "positions": [
                    {
                        "symbol": p.symbol,
                        "strike": p.strike_price,
                        "option_type": p.option_type,
                        "contracts": p.contracts,
                        "account": p.account_name
                    }
                    for p in expiring_on_witching[:10]  # First 10
                ]
            },
            expires_at=datetime.combine(next_witching, time(6, 30))
        )


# ============================================================================
# UTILITY EXPORTS
# ============================================================================

# Export key functions for use by other modules
__all__ = [
    'TripleWitchingStrategy',
    'is_triple_witching',
    'get_next_triple_witching',
    'days_until_triple_witching',
    'apply_triple_witching_overrides',
    'get_current_window_et',
    'analyze_expiring_position_on_triple_witching',
    'recommend_timing_for_new_sales_on_triple_witching',
    'get_triple_witching_execution_guidance',
]

