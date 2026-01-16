"""
Technical Analysis Service

Provides technical analysis for options trading decisions:
- Support/Resistance levels
- RSI (Relative Strength Index)
- Bollinger Bands
- Volatility metrics
- Probability ranges
- Earnings date checks
- Moving averages
"""

import logging
import requests
import numpy as np
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from functools import lru_cache
import time

# V2.2 Refactoring: Use centralized utility functions
from app.modules.strategies.utils.option_calculations import calculate_itm_status

logger = logging.getLogger(__name__)

# Cache for API results to avoid rate limiting
_price_cache: Dict[str, Tuple[datetime, Dict]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes (default)


def _get_cache_ttl() -> int:
    """
    Get cache TTL based on market hours.
    
    During market hours (6:30 AM - 1:00 PM PT, Mon-Fri): 5 minutes
    Outside market hours: 1 hour (reduces unnecessary API calls)
    """
    try:
        now = datetime.now(pytz.timezone('America/Los_Angeles'))
        hour = now.hour
        minute = now.minute
        weekday = now.weekday()
        
        # Weekend - use long cache
        if weekday >= 5:
            return 3600  # 1 hour
        
        # Convert to minutes since midnight for easier comparison
        current_time = hour * 60 + minute
        market_open = 6 * 60 + 30   # 6:30 AM PT
        market_close = 13 * 60      # 1:00 PM PT (market closes 1 PM PT)
        
        # During market hours
        if market_open <= current_time <= market_close:
            return 300  # 5 minutes
        
        # Outside market hours
        return 1800  # 30 minutes (not as long as weekend, but still reduced)
    except Exception:
        return 300  # Default to 5 minutes if timezone fails


@dataclass
class TechnicalIndicators:
    """Technical indicators for a stock."""
    symbol: str
    current_price: float
    
    # 52-week range
    year_high: float
    year_low: float
    
    # Moving averages
    ma_50: Optional[float] = None
    ma_200: Optional[float] = None
    
    # Volatility
    daily_volatility: float = 0.0
    weekly_volatility: float = 0.0
    annualized_volatility: float = 0.0
    
    # RSI
    rsi_14: float = 50.0
    rsi_status: str = "neutral"  # "overbought", "oversold", "neutral"
    
    # Bollinger Bands
    bb_upper: float = 0.0
    bb_middle: float = 0.0
    bb_lower: float = 0.0
    bb_position: str = "middle"  # "above_upper", "near_upper", "middle", "near_lower", "below_lower"
    
    # Support/Resistance
    resistance_levels: List[float] = None
    support_levels: List[float] = None
    nearest_resistance: Optional[float] = None
    nearest_support: Optional[float] = None
    
    # Probability ranges (based on historical volatility)
    prob_68_low: float = 0.0
    prob_68_high: float = 0.0
    prob_90_low: float = 0.0
    prob_90_high: float = 0.0
    prob_95_low: float = 0.0
    prob_95_high: float = 0.0
    
    # Trend
    trend: str = "neutral"  # "bullish", "bearish", "neutral"
    
    # Earnings
    earnings_date: Optional[date] = None
    earnings_within_week: bool = False
    
    # Analysis timestamp
    analyzed_at: datetime = None
    
    def __post_init__(self):
        if self.resistance_levels is None:
            self.resistance_levels = []
        if self.support_levels is None:
            self.support_levels = []
        if self.analyzed_at is None:
            self.analyzed_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        if result.get('earnings_date'):
            result['earnings_date'] = result['earnings_date'].isoformat()
        if result.get('analyzed_at'):
            result['analyzed_at'] = result['analyzed_at'].isoformat()
        return result


@dataclass
class VolatilityRisk:
    """Assessment of volatility risk for options."""
    symbol: str
    risk_level: str  # "low", "medium", "high"
    risk_factors: List[str]
    recommendation: str
    should_close_early: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StrikeRecommendation:
    """Recommended strike price for options."""
    symbol: str
    option_type: str  # "call" or "put"
    recommended_strike: float
    probability_otm: float
    rationale: str
    expiration_suggestion: str
    nearest_technical_level: Optional[float] = None  # May not be available
    source: str = "unknown"  # "options_chain" or "fallback_estimate"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TechnicalAnalysisService:
    """
    Service for performing technical analysis on stocks.
    
    Uses direct Yahoo Finance API calls to avoid rate limiting issues
    with the yfinance library.
    """
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
    
    def _fetch_historical_data(
        self,
        symbol: str,
        range_period: str = "3mo"
    ) -> Optional[Dict]:
        """
        Fetch historical data - tries Schwab first, then Yahoo as fallback.
        
        Args:
            symbol: Stock symbol
            range_period: Period to fetch ("1mo", "3mo", "6mo", "1y")
        
        Returns:
            Dict with price data (Yahoo-compatible format) or None if failed
        """
        cache_key = f"{symbol}_{range_period}"
        
        # Check cache with dynamic TTL based on market hours
        if cache_key in _price_cache:
            cached_time, cached_data = _price_cache[cache_key]
            cache_ttl = _get_cache_ttl()
            if (datetime.now() - cached_time).total_seconds() < cache_ttl:
                return cached_data
        
        # Convert range_period to days
        period_to_days = {
            "1mo": 30,
            "3mo": 90,
            "6mo": 180,
            "1y": 365
        }
        period_days = period_to_days.get(range_period, 90)
        
        # TRY SCHWAB FIRST (no rate limiting issues)
        result = self._fetch_schwab_history(symbol, period_days)
        if result:
            _price_cache[cache_key] = (datetime.now(), result)
            return result
        
        # FALLBACK TO YAHOO if Schwab unavailable
        result = self._fetch_yahoo_data(symbol, range_period)
        if result:
            _price_cache[cache_key] = (datetime.now(), result)
            return result
        
        return None
    
    def _fetch_schwab_history(
        self,
        symbol: str,
        period_days: int = 90
    ) -> Optional[Dict]:
        """
        Fetch historical data from Schwab API.
        
        Returns data in Yahoo-compatible format for easy integration.
        """
        try:
            from app.modules.strategies.schwab_service import get_price_history_schwab
            
            history = get_price_history_schwab(symbol, period_days=period_days)
            
            if not history or not history.get("candles"):
                return None
            
            candles = history["candles"]
            
            # Convert to Yahoo-compatible format
            timestamps = [int(c["datetime"].timestamp()) for c in candles]
            closes = [c["close"] for c in candles]
            highs = [c["high"] for c in candles]
            lows = [c["low"] for c in candles]
            opens = [c["open"] for c in candles]
            volumes = [c["volume"] for c in candles]
            
            current_price = closes[-1] if closes else None
            
            result = {
                "meta": {
                    "symbol": symbol,
                    "regularMarketPrice": current_price,
                    "_source": "schwab"
                },
                "timestamp": timestamps,
                "indicators": {
                    "quote": [{
                        "close": closes,
                        "high": highs,
                        "low": lows,
                        "open": opens,
                        "volume": volumes
                    }]
                }
            }
            
            logger.info(f"[SCHWAB] Got {len(candles)} days of history for {symbol}")
            return result
            
        except Exception as e:
            logger.debug(f"[SCHWAB] Could not get history for {symbol}: {e}")
            return None
    
    def _fetch_yahoo_data(
        self,
        symbol: str,
        range_period: str = "3mo"
    ) -> Optional[Dict]:
        """
        Fetch historical data from Yahoo Finance (fallback).
        """
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            params = {
                "interval": "1d",
                "range": range_period
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if 'chart' in data and 'result' in data['chart'] and data['chart']['result']:
                    result = data['chart']['result'][0]
                    logger.debug(f"[YAHOO] Got history for {symbol}")
                    return result
            else:
                logger.warning(f"Yahoo API returned {response.status_code} for {symbol}")
                
        except Exception as e:
            logger.error(f"Error fetching Yahoo data for {symbol}: {e}")
        
        return None
    
    def _fetch_earnings_date(self, symbol: str) -> Optional[date]:
        """
        Fetch next earnings date for a symbol.
        
        Uses cached earnings dates from yahoo_cache to avoid rate limiting.
        Earnings dates are cached for 24 hours since they rarely change.
        """
        try:
            from app.modules.strategies.yahoo_cache import get_earnings_date
            return get_earnings_date(symbol)
        except Exception as e:
            logger.debug(f"[EARNINGS_FETCH] {symbol}: Could not fetch earnings - {e}")
            return None
    
    def get_technical_indicators(self, symbol: str) -> Optional[TechnicalIndicators]:
        """
        Get comprehensive technical indicators for a symbol.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            TechnicalIndicators object or None if data unavailable
        """
        # Fetch 3-month and 1-year data (Schwab first, Yahoo fallback)
        data_3m = self._fetch_historical_data(symbol, "3mo")
        data_1y = self._fetch_historical_data(symbol, "1y")
        
        if not data_3m:
            logger.warning(f"Could not fetch data for {symbol}")
            return None
        
        try:
            meta = data_3m.get('meta', {})
            current_price = meta.get('regularMarketPrice', 0)
            
            if not current_price:
                return None
            
            quote = data_3m.get('indicators', {}).get('quote', [{}])[0]
            closes = [c for c in quote.get('close', []) if c is not None]
            highs = [h for h in quote.get('high', []) if h is not None]
            lows = [l for l in quote.get('low', []) if l is not None]
            
            if not closes:
                return None
            
            # Initialize indicators
            indicators = TechnicalIndicators(
                symbol=symbol,
                current_price=current_price,
                year_high=max(highs) if highs else current_price,
                year_low=min(lows) if lows else current_price
            )
            
            # 52-week data
            if data_1y:
                quote_1y = data_1y.get('indicators', {}).get('quote', [{}])[0]
                closes_1y = [c for c in quote_1y.get('close', []) if c is not None]
                highs_1y = [h for h in quote_1y.get('high', []) if h is not None]
                lows_1y = [l for l in quote_1y.get('low', []) if l is not None]
                
                if highs_1y and lows_1y:
                    indicators.year_high = max(highs_1y)
                    indicators.year_low = min(lows_1y)
                
                if len(closes_1y) >= 50:
                    indicators.ma_50 = float(np.mean(closes_1y[-50:]))
                if len(closes_1y) >= 200:
                    indicators.ma_200 = float(np.mean(closes_1y[-200:]))
                elif len(closes_1y) >= 100:
                    indicators.ma_200 = float(np.mean(closes_1y))
            
            # Volatility
            if len(closes) > 1:
                returns = np.diff(closes) / np.array(closes[:-1])
                indicators.daily_volatility = float(np.std(returns))
                indicators.weekly_volatility = indicators.daily_volatility * np.sqrt(5)
                indicators.annualized_volatility = indicators.daily_volatility * np.sqrt(252)
            
            # RSI (14-day)
            if len(closes) >= 15:
                deltas = np.diff(closes[-15:])
                gains = np.where(deltas > 0, deltas, 0)
                losses = np.where(deltas < 0, -deltas, 0)
                avg_gain = np.mean(gains)
                avg_loss = np.mean(losses)
                
                if avg_loss != 0:
                    rs = avg_gain / avg_loss
                    indicators.rsi_14 = float(100 - (100 / (1 + rs)))
                else:
                    indicators.rsi_14 = 100.0
                
                if indicators.rsi_14 > 70:
                    indicators.rsi_status = "overbought"
                elif indicators.rsi_14 < 30:
                    indicators.rsi_status = "oversold"
                else:
                    indicators.rsi_status = "neutral"
            
            # Bollinger Bands (20-day, 2σ)
            if len(closes) >= 20:
                bb_closes = closes[-20:]
                indicators.bb_middle = float(np.mean(bb_closes))
                bb_std = float(np.std(bb_closes))
                indicators.bb_upper = indicators.bb_middle + 2 * bb_std
                indicators.bb_lower = indicators.bb_middle - 2 * bb_std
                
                if current_price > indicators.bb_upper:
                    indicators.bb_position = "above_upper"
                elif current_price > indicators.bb_middle + bb_std:
                    indicators.bb_position = "near_upper"
                elif current_price < indicators.bb_lower:
                    indicators.bb_position = "below_lower"
                elif current_price < indicators.bb_middle - bb_std:
                    indicators.bb_position = "near_lower"
                else:
                    indicators.bb_position = "middle"
            
            # Support/Resistance levels
            unique_highs = sorted(set(highs), reverse=True)
            unique_lows = sorted(set(lows))
            
            indicators.resistance_levels = [
                round(h, 2) for h in unique_highs[:5] if h > current_price
            ]
            indicators.support_levels = [
                round(l, 2) for l in unique_lows[:5] if l < current_price
            ]
            
            if indicators.resistance_levels:
                indicators.nearest_resistance = min(indicators.resistance_levels)
            if indicators.support_levels:
                indicators.nearest_support = max(indicators.support_levels)
            
            # Probability ranges (1-week)
            wv = indicators.weekly_volatility
            indicators.prob_68_low = round(current_price * (1 - wv), 2)
            indicators.prob_68_high = round(current_price * (1 + wv), 2)
            indicators.prob_90_low = round(current_price * (1 - 1.28 * wv), 2)
            indicators.prob_90_high = round(current_price * (1 + 1.28 * wv), 2)
            indicators.prob_95_low = round(current_price * (1 - 2 * wv), 2)
            indicators.prob_95_high = round(current_price * (1 + 2 * wv), 2)
            
            # Trend
            if indicators.ma_50 and indicators.ma_200:
                if current_price > indicators.ma_50 > indicators.ma_200:
                    indicators.trend = "bullish"
                elif current_price < indicators.ma_50 < indicators.ma_200:
                    indicators.trend = "bearish"
                else:
                    indicators.trend = "neutral"
            
            # Earnings date
            try:
                indicators.earnings_date = self._fetch_earnings_date(symbol)
                if indicators.earnings_date:
                    days_to_earnings = (indicators.earnings_date - date.today()).days
                    indicators.earnings_within_week = 0 <= days_to_earnings <= 7
            except:
                pass
            
            return indicators
            
        except Exception as e:
            logger.error(f"Error calculating indicators for {symbol}: {e}")
            return None
    
    def assess_volatility_risk(
        self,
        symbol: str,
        expiration_date: date,
        profit_captured_pct: float
    ) -> VolatilityRisk:
        """
        Assess volatility risk for an option position.
        
        Used for "Options Expiring Soon" recommendation to determine
        if an option should be closed early due to volatility risk.
        
        Args:
            symbol: Stock symbol
            expiration_date: Option expiration date
            profit_captured_pct: Percentage of max profit already captured (0-100)
        
        Returns:
            VolatilityRisk assessment
        """
        indicators = self.get_technical_indicators(symbol)
        
        if not indicators:
            return VolatilityRisk(
                symbol=symbol,
                risk_level="unknown",
                risk_factors=["Could not fetch technical data"],
                recommendation="Unable to assess - check manually",
                should_close_early=False
            )
        
        risk_factors = []
        risk_score = 0
        
        days_to_expiry = (expiration_date - date.today()).days
        
        # Check earnings
        if indicators.earnings_within_week:
            risk_factors.append(f"Earnings on {indicators.earnings_date} (before expiration)")
            risk_score += 40
        
        # Check RSI extremes
        # RSI > 70 = overbought (stock has run up a lot, may reverse down - good for your sold call)
        # RSI < 30 = oversold (stock has dropped a lot, may bounce up - risk for sold call)
        if indicators.rsi_status == "overbought":
            risk_factors.append(
                f"RSI at {indicators.rsi_14:.1f} (overbought) - stock may reverse down soon, "
                f"locking in your profit is safe"
            )
            risk_score += 20
        elif indicators.rsi_status == "oversold":
            risk_factors.append(
                f"RSI at {indicators.rsi_14:.1f} (oversold) - stock may bounce up, "
                f"close position before potential rally"
            )
            risk_score += 20
        
        # Check Bollinger Band position
        # Bollinger Bands measure volatility - price near upper band means stock has had a big run-up
        # For sold calls: if price keeps rising toward your strike, you could get assigned
        # But extended moves at upper band often reverse (mean reversion)
        if indicators.bb_position in ["above_upper", "near_upper"]:
            risk_factors.append(
                f"Stock at ${indicators.current_price:.2f}, near upper Bollinger Band (${indicators.bb_upper:.2f}) - "
                f"extended move may continue OR reverse"
            )
            risk_score += 15
        elif indicators.bb_position in ["below_lower", "near_lower"]:
            risk_factors.append(
                f"Stock at ${indicators.current_price:.2f}, near lower Bollinger Band (${indicators.bb_lower:.2f}) - "
                f"may bounce back up"
            )
            risk_score += 15
        
        # Check volatility
        if indicators.annualized_volatility > 0.40:  # 40% annualized vol
            risk_factors.append(f"High volatility ({indicators.annualized_volatility*100:.1f}% annualized)")
            risk_score += 15
        
        # Check if near resistance/support
        if indicators.nearest_resistance:
            pct_to_resistance = (indicators.nearest_resistance - indicators.current_price) / indicators.current_price * 100
            if pct_to_resistance < 3:
                risk_factors.append(f"Near resistance at ${indicators.nearest_resistance:.2f} ({pct_to_resistance:.1f}% away)")
                risk_score += 10
        
        # Determine risk level
        if risk_score >= 50:
            risk_level = "high"
        elif risk_score >= 25:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        # Determine if should close early
        # Close early if: high profit captured AND elevated risk
        should_close = profit_captured_pct >= 70 and risk_score >= 30
        
        if should_close:
            recommendation = f"CLOSE NOW: {profit_captured_pct:.0f}% profit captured with {len(risk_factors)} risk factor(s)"
        elif risk_level == "high":
            recommendation = f"MONITOR CLOSELY: High volatility risk detected"
        else:
            recommendation = f"HOLD: Risk level is {risk_level}, profit at {profit_captured_pct:.0f}%"
        
        return VolatilityRisk(
            symbol=symbol,
            risk_level=risk_level,
            risk_factors=risk_factors,
            recommendation=recommendation,
            should_close_early=should_close
        )
    
    def _get_strike_from_options_chain(
        self,
        symbol: str,
        option_type: str,
        expiration_date: str,
        target_delta: float = 0.10,
        current_price: float = None
    ) -> Optional[tuple]:
        """
        Fetch actual options chain and find strike with target delta.
        
        This provides REAL market-based strike recommendations instead of
        hardcoded volatility estimates.
        
        Args:
            symbol: Stock symbol
            option_type: "call" or "put"
            expiration_date: Expiration date string (YYYY-MM-DD)
            target_delta: Target delta (0.10 = Delta 10)
            current_price: Current stock price (for OTM filtering)
        
        Returns:
            Tuple of (strike, actual_delta, probability_otm) or None
        """
        try:
            from app.modules.strategies.option_monitor import OptionChainFetcher
            from datetime import datetime
            
            logger.info(f"[STRIKE_DEBUG] {symbol}: Requesting chain for expiration={expiration_date}, target_delta={target_delta}, current_price=${current_price}")
            
            # Use OptionChainFetcher which prefers Schwab over Yahoo
            fetcher = OptionChainFetcher()
            exp_date = datetime.strptime(expiration_date, "%Y-%m-%d").date()
            chain = fetcher.get_option_chain(symbol, exp_date)
            
            if chain is None:
                logger.warning(f"[STRIKE_DEBUG] {symbol}: Chain returned None for {expiration_date}")
                return None
            
            # Log the chain source
            logger.info(f"[STRIKE_DEBUG] {symbol}: Got chain from Schwab/Yahoo")
            
            # Get the right side of the chain
            if option_type.lower() == "call":
                options_df = chain['calls']
            else:
                options_df = chain['puts']
            
            if options_df is None or len(options_df) == 0:
                logger.warning(f"[STRIKE_DEBUG] {symbol}: No {option_type}s in chain")
                return None
            
            # Log available columns and sample data
            logger.info(f"[STRIKE_DEBUG] {symbol}: Chain has {len(options_df)} {option_type}s, columns: {list(options_df.columns)}")
            
            # Check if delta column exists and has data
            has_delta_col = 'delta' in options_df.columns
            delta_non_null_count = 0
            if has_delta_col:
                delta_non_null_count = options_df['delta'].notna().sum()
            logger.info(f"[STRIKE_DEBUG] {symbol}: has_delta_column={has_delta_col}, non_null_deltas={delta_non_null_count}/{len(options_df)}")
            
            # Filter to OTM options only
            if current_price:
                if option_type.lower() == "call":
                    # Calls are OTM when strike > current_price
                    options_df = options_df[options_df['strike'] > current_price]
                else:
                    # Puts are OTM when strike < current_price
                    options_df = options_df[options_df['strike'] < current_price]
            
            if len(options_df) == 0:
                logger.warning(f"[STRIKE_DEBUG] {symbol}: No OTM {option_type}s after filtering (current_price=${current_price})")
                return None
            
            logger.info(f"[STRIKE_DEBUG] {symbol}: After OTM filter: {len(options_df)} strikes")
            
            # Find the strike closest to target delta
            # For calls: delta is positive and decreases as strike increases
            # For puts: delta is negative, we use absolute value
            best_strike = None
            best_delta = None
            best_diff = float('inf')
            strikes_with_delta = 0
            
            # Log first few strikes with their deltas for debugging
            sample_strikes = []
            
            for _, row in options_df.iterrows():
                strike = row['strike']
                delta = row.get('delta')
                bid = row.get('bid', 0)
                
                # Skip if no delta data
                if delta is None or (isinstance(delta, float) and np.isnan(delta)):
                    continue
                
                strikes_with_delta += 1
                
                # Use absolute delta for comparison
                abs_delta = abs(delta)
                
                # Collect sample for logging
                if len(sample_strikes) < 10:
                    sample_strikes.append(f"${strike}:d={abs_delta:.3f}:bid=${bid}")
                
                # Find closest to target
                diff = abs(abs_delta - target_delta)
                if diff < best_diff:
                    best_diff = diff
                    best_strike = strike
                    best_delta = abs_delta
            
            logger.info(f"[STRIKE_DEBUG] {symbol}: Found {strikes_with_delta} strikes with delta data")
            if sample_strikes:
                logger.info(f"[STRIKE_DEBUG] {symbol}: Sample strikes: {', '.join(sample_strikes)}")
            
            if best_strike is not None:
                probability_otm = (1 - best_delta) * 100
                pct_otm = ((best_strike / current_price) - 1) * 100 if current_price and option_type.lower() == "call" else 0
                logger.info(f"[STRIKE_DEBUG] {symbol}: SELECTED strike=${best_strike} (delta={best_delta:.3f}, {pct_otm:.1f}% OTM, prob_otm={probability_otm:.1f}%)")
                return (best_strike, best_delta, probability_otm)
            
            logger.warning(f"[STRIKE_DEBUG] {symbol}: No strike found with valid delta data!")
            return None
            
        except Exception as e:
            logger.warning(f"[STRIKE_DEBUG] {symbol}: Error fetching options chain: {e}")
            return None
    
    def _get_next_friday(self, weeks_out: int = 1) -> str:
        """Get the expiration date (Friday) for N weeks out."""
        from datetime import date, timedelta
        today = date.today()
        # Find next Friday
        days_ahead = 4 - today.weekday()  # Friday = 4
        if days_ahead <= 0:
            days_ahead += 7
        next_friday = today + timedelta(days=days_ahead)
        # Add additional weeks
        target_friday = next_friday + timedelta(weeks=weeks_out - 1)
        return target_friday.strftime("%Y-%m-%d")
    
    def recommend_strike_price(
        self,
        symbol: str,
        option_type: str,  # "call" or "put"
        expiration_weeks: int = 1,
        probability_target: float = 0.90,
        target_expiration_date: str = None  # Optional: Use exact expiration date instead of calculating from weeks
    ) -> Optional[StrikeRecommendation]:
        """
        Recommend a strike price for selling options.
        
        PRIORITY ORDER:
        1. Fetch REAL delta from options chain (most accurate)
        2. Fall back to hardcoded volatility estimates (if chain unavailable)
        
        Used for:
        - New Covered Call Opportunity
        - Roll Options strike selection
        - Bull Put Spread strike selection
        
        Args:
            symbol: Stock symbol
            option_type: "call" or "put"
            expiration_weeks: Weeks until expiration (used if target_expiration_date not provided)
            probability_target: Target probability of staying OTM (0.90 = 90%)
            target_expiration_date: Optional exact expiration date (YYYY-MM-DD) - overrides expiration_weeks
        
        Returns:
            StrikeRecommendation or None
        """
        indicators = self.get_technical_indicators(symbol)
        
        if not indicators:
            return None
        
        current_price = indicators.current_price
        target_delta = 1.0 - probability_target  # 90% OTM = delta 0.10
        
        logger.info(f"[STRIKE_DEBUG] {symbol}: recommend_strike_price called - current_price=${current_price:.2f}, target_delta={target_delta:.2f}, weeks={expiration_weeks}")
        
        # ===== PRIORITY 1: Try to get REAL delta from options chain =====
        # V3.1: Use provided expiration date if available, otherwise calculate from weeks
        if target_expiration_date:
            expiration_date = target_expiration_date
            logger.info(f"[STRIKE_DEBUG] {symbol}: Using provided expiration_date={expiration_date}")
        else:
            expiration_date = self._get_next_friday(expiration_weeks)
            logger.info(f"[STRIKE_DEBUG] {symbol}: Calculated expiration_date={expiration_date}")
        chain_result = self._get_strike_from_options_chain(
            symbol=symbol,
            option_type=option_type,
            expiration_date=expiration_date,
            target_delta=target_delta,
            current_price=current_price
        )
        
        if chain_result:
            recommended_strike, actual_delta, probability_otm = chain_result
            pct_otm = ((recommended_strike / current_price) - 1) * 100 if option_type.lower() == "call" else ((current_price / recommended_strike) - 1) * 100

            # SANITY CHECK: Reject strikes that are unreasonably far OTM
            # For weekly options targeting delta 10, the strike should be within ~15% OTM
            # Allow up to 30% for high-IV stocks, but anything beyond that is likely bad data
            MAX_REASONABLE_OTM_PCT = 30.0
            if abs(pct_otm) > MAX_REASONABLE_OTM_PCT:
                logger.warning(
                    f"[STRIKE_SANITY] {symbol}: Rejecting strike ${recommended_strike} from options chain - "
                    f"{abs(pct_otm):.1f}% OTM exceeds maximum {MAX_REASONABLE_OTM_PCT}% threshold "
                    f"(stock at ${current_price:.2f}, delta {actual_delta:.2f}). Using fallback calculation."
                )
                chain_result = None  # Fall through to fallback below
            else:
                rationale = (
                    f"Delta {actual_delta:.2f} strike from live options chain "
                    f"({probability_otm:.0f}% probability OTM, {abs(pct_otm):.1f}% {'above' if option_type.lower() == 'call' else 'below'} ${current_price:.2f})"
                )

                logger.info(f"{symbol}: Using LIVE options chain - ${recommended_strike} strike (delta {actual_delta:.2f})")

                # Round to nearest standard strike
                if recommended_strike > 100:
                    recommended_strike = round(recommended_strike)
                else:
                    recommended_strike = round(recommended_strike * 2) / 2

                return StrikeRecommendation(
                    symbol=symbol,
                    option_type=option_type,
                    recommended_strike=recommended_strike,
                    rationale=rationale,
                    probability_otm=probability_otm,
                    expiration_suggestion=f"Expiring {expiration_date}",
                    source="options_chain"
                )

        # ===== PRIORITY 2: Fall back to hardcoded volatility estimates =====
        logger.info(f"[STRIKE_DEBUG] {symbol}: Options chain returned None - USING FALLBACK volatility estimate")
        
        # Hardcoded volatility buckets (fallback only)
        very_high_iv_stocks = {
            "TSLA", "COIN", "MSTR", "PLTR", "RKLB", "HOOD", "GME", "AMC",
            "BABA", "JD", "PDD", "NIO", "XPEV", "LI", "BIDU",
            "RIVN", "LCID", "SOFI", "AFRM", "UPST",
            "SMCI", "ARM", "IONQ", "RGTI", "QUBT",
        }
        
        high_iv_stocks = {
            "NVDA", "AMD", "MU", "AVGO", "MRVL",
            "NFLX", "SHOP", "SQ", "SNAP", "ROKU",
            "CRWD", "DDOG", "NET", "ZS",
        }
        
        medium_iv_stocks = {
            "META", "GOOGL", "GOOG", "AMZN", "MSFT", "AAPL",
            "CRM", "ADBE", "ORCL", "IBM",
            "V", "MA", "PYPL",
        }
        
        if symbol.upper() in very_high_iv_stocks:
            delta_10_otm_pct = 0.10  # 10% OTM (conservative estimate)
        elif symbol.upper() in high_iv_stocks:
            delta_10_otm_pct = 0.065
        elif symbol.upper() in medium_iv_stocks:
            delta_10_otm_pct = 0.050
        else:
            delta_10_otm_pct = 0.040  # Conservative default
        
        # Adjust for expiration period
        period_adjustment = np.sqrt(expiration_weeks)
        period_vol = delta_10_otm_pct * period_adjustment
        
        if option_type.lower() == "call":
            prob_strike = current_price * (1 + period_vol)
            recommended_strike = prob_strike
            rationale = f"Delta 10 strike at ${prob_strike:.0f} ({period_vol*100:.1f}% above ${current_price:.2f}) based on historical volatility"
        else:
            prob_strike = current_price * (1 - period_vol)
            recommended_strike = prob_strike
            rationale = f"Delta 10 strike at ${prob_strike:.0f} ({period_vol*100:.1f}% below ${current_price:.2f}) based on historical volatility"
        
        # Round to nearest $0.50 or $1 depending on price
        if recommended_strike > 100:
            recommended_strike = round(recommended_strike)
        else:
            recommended_strike = round(recommended_strike * 2) / 2
        
        # Expiration suggestion
        if expiration_weeks == 1:
            exp_suggestion = "Next Friday"
        elif expiration_weeks <= 2:
            exp_suggestion = f"{expiration_weeks} weeks out"
        else:
            exp_suggestion = f"{expiration_weeks} weeks out (extended for safety)"
        
        return StrikeRecommendation(
            symbol=symbol,
            option_type=option_type,
            recommended_strike=recommended_strike,
            probability_otm=probability_target * 100,
            rationale=rationale,
            expiration_suggestion=exp_suggestion,
            source="fallback_estimate"
        )
    
    def should_wait_to_sell(self, symbol: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Determine if we should wait before selling a new covered call.
        
        Used for "New Covered Call Opportunity" when stock dropped and
        option was closed for profit. Determines if stock is likely to
        bounce (wait) or is just correcting (safe to sell).
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Tuple of (should_wait, reason, analysis_data)
        """
        indicators = self.get_technical_indicators(symbol)
        
        if not indicators:
            return False, "Could not fetch data - proceed with caution", {}
        
        analysis = {
            "symbol": symbol,
            "current_price": indicators.current_price,
            "rsi": indicators.rsi_14,
            "bb_position": indicators.bb_position,
            "trend": indicators.trend
        }
        
        # Check for oversold conditions (likely bounce)
        if indicators.rsi_14 < 30:
            return True, f"RSI at {indicators.rsi_14:.1f} (oversold) - stock likely to bounce, wait to sell", analysis
        
        # Check if at lower Bollinger Band (likely bounce)
        if indicators.bb_position in ["below_lower", "near_lower"]:
            return True, f"Price near lower Bollinger Band - likely to bounce back toward middle", analysis
        
        # Check if near support
        if indicators.nearest_support:
            pct_to_support = (indicators.current_price - indicators.nearest_support) / indicators.current_price * 100
            if pct_to_support < 2:
                return True, f"Price near support at ${indicators.nearest_support:.2f} - likely to bounce", analysis
        
        # If correcting from overbought (safe to sell)
        if indicators.bb_position in ["middle", "near_upper"]:
            return False, f"Price in middle of Bollinger Bands - correction, safe to sell call", analysis
        
        if indicators.rsi_14 > 50:
            return False, f"RSI at {indicators.rsi_14:.1f} - stock still has momentum, safe to sell call", analysis
        
        # Default: don't wait
        return False, "Technical indicators neutral - safe to proceed with selling call", analysis
    
    def analyze_itm_position(
        self,
        symbol: str,
        strike_price: float,
        option_type: str = "call"
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Analyze an in-the-money position to determine action.
        
        Used for "Roll Options - Scenario C" when option goes ITM.
        Determines if stock will reverse (wait) or continue (roll out).
        
        Args:
            symbol: Stock symbol
            strike_price: Current option strike price
            option_type: "call" or "put"
        
        Returns:
            Tuple of (action, reason, analysis_data)
            action: "wait", "roll_1_week", "roll_3_4_weeks"
        """
        indicators = self.get_technical_indicators(symbol)
        
        if not indicators:
            return "wait", "Could not fetch data - monitor manually", {}
        
        analysis = {
            "symbol": symbol,
            "current_price": indicators.current_price,
            "strike_price": strike_price,
            "rsi": indicators.rsi_14,
            "bb_position": indicators.bb_position,
            "trend": indicators.trend,
            "itm_amount": abs(indicators.current_price - strike_price)
        }
        
        # V2.2: Use centralized ITM calculation
        itm_calc = calculate_itm_status(indicators.current_price, strike_price, option_type)
        itm_pct = itm_calc['itm_pct'] if itm_calc['is_itm'] else 0  # Used in logic below
        analysis["itm_percent"] = itm_pct if itm_calc['is_itm'] else -itm_calc['otm_pct']
        
        # Check for reversal signals
        reversal_signals = []
        continuation_signals = []
        
        # RSI
        if indicators.rsi_14 > 70:
            reversal_signals.append(f"RSI at {indicators.rsi_14:.1f} (overbought)")
        elif indicators.rsi_14 < 30:
            reversal_signals.append(f"RSI at {indicators.rsi_14:.1f} (oversold)")
        else:
            if option_type.lower() == "call" and indicators.rsi_14 > 55:
                continuation_signals.append(f"RSI at {indicators.rsi_14:.1f} (momentum)")
        
        # Bollinger Bands
        if indicators.bb_position == "above_upper":
            reversal_signals.append("Price above upper Bollinger Band")
        elif indicators.bb_position == "near_upper":
            reversal_signals.append("Price near upper Bollinger Band")
        elif indicators.bb_position == "below_lower":
            reversal_signals.append("Price below lower Bollinger Band")
        
        # Resistance
        if option_type.lower() == "call" and indicators.nearest_resistance:
            pct_to_resistance = (indicators.nearest_resistance - indicators.current_price) / indicators.current_price * 100
            if pct_to_resistance < 2:
                reversal_signals.append(f"Near resistance at ${indicators.nearest_resistance:.2f}")
        
        analysis["reversal_signals"] = reversal_signals
        analysis["continuation_signals"] = continuation_signals
        
        # Determine action
        if len(reversal_signals) >= 2:
            return "wait", f"WAIT - {len(reversal_signals)} reversal signals: {', '.join(reversal_signals)}", analysis
        
        if len(reversal_signals) == 1 and itm_pct < 3:
            return "wait", f"WAIT - Slightly ITM ({itm_pct:.1f}%) with reversal signal: {reversal_signals[0]}", analysis
        
        if itm_pct >= 5 or len(continuation_signals) > 0:
            # Deep ITM or showing continuation - roll out 3-4 weeks
            return "roll_3_4_weeks", f"ROLL 3-4 WEEKS - Stock at {indicators.current_price:.2f}, {itm_pct:.1f}% ITM with momentum", analysis
        
        # Moderate ITM, could go either way
        return "roll_1_week", f"ROLL 1 WEEK - Moderate ITM ({itm_pct:.1f}%), no strong signals either way", analysis


# Global instance
_ta_service: Optional[TechnicalAnalysisService] = None


def get_technical_analysis_service() -> TechnicalAnalysisService:
    """Get or create the global technical analysis service."""
    global _ta_service
    if _ta_service is None:
        _ta_service = TechnicalAnalysisService()
    return _ta_service

