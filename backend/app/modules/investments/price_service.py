"""
Stock price service for fetching historical prices and calculating changes.
Uses Schwab API as primary source, yfinance/Yahoo Finance API as fallback.
"""

import yfinance as yf
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from functools import lru_cache
import logging
import time
import pytz

logger = logging.getLogger(__name__)


def get_prices_schwab_first(symbols: List[str]) -> Dict[str, dict]:
    """
    Get current prices for symbols, using Schwab as primary source.
    Falls back to Yahoo Finance if Schwab fails.
    
    Returns dict with symbol -> {"current_price": float, "source": str}
    """
    results = {}
    symbols_needing_fallback = []
    
    if not symbols:
        return results
    
    # Try Schwab first (batch request for efficiency)
    try:
        from app.modules.strategies.schwab_service import get_stock_quotes_batch_schwab, is_schwab_configured
        
        if is_schwab_configured():
            logger.info(f"Fetching prices from Schwab for {len(symbols)} symbols...")
            quotes = get_stock_quotes_batch_schwab(symbols)
            
            for symbol in symbols:
                quote = quotes.get(symbol)
                if quote and quote.get("lastPrice"):
                    results[symbol] = {
                        "current_price": round(float(quote["lastPrice"]), 2),
                        "source": "schwab"
                    }
                    logger.debug(f"Got price for {symbol} from Schwab: ${quote['lastPrice']}")
                else:
                    symbols_needing_fallback.append(symbol)
        else:
            logger.warning("Schwab not configured, using Yahoo for all symbols")
            symbols_needing_fallback = symbols
    except ImportError:
        logger.warning("Schwab service not available, using Yahoo for all symbols")
        symbols_needing_fallback = symbols
    except Exception as e:
        logger.warning(f"Schwab service error: {e}, falling back to Yahoo")
        symbols_needing_fallback = [s for s in symbols if s not in results]
    
    # Fall back to Yahoo for any remaining symbols
    if symbols_needing_fallback:
        logger.info(f"Falling back to Yahoo for {len(symbols_needing_fallback)} symbols")
        yahoo_prices = get_live_prices_fast(symbols_needing_fallback)
        for symbol, price in yahoo_prices.items():
            if price and symbol not in results:
                results[symbol] = {
                    "current_price": round(float(price), 2),
                    "source": "yahoo"
                }
    
    return results

# Cache for live prices (symbol -> (price, timestamp))
_price_cache: Dict[str, Tuple[float, datetime]] = {}
# Cache for previous close prices (symbol -> previous_close)
_prev_close_cache: Dict[str, float] = {}
CACHE_TTL_SECONDS = 60  # Cache prices for 60 seconds (default)


def _is_test_mode() -> bool:
    """Check if OPTIONS_TEST_MODE is enabled."""
    try:
        from app.core.config import settings
        return getattr(settings, 'OPTIONS_TEST_MODE', False)
    except Exception:
        return False


def _use_infinite_cache_off_hours() -> bool:
    """Check if infinite cache is enabled for off-hours."""
    try:
        from app.core.config import settings
        return getattr(settings, 'OPTIONS_INFINITE_CACHE_OFF_HOURS', True)
    except Exception:
        return True


def _get_price_cache_ttl() -> int:
    """
    Get cache TTL based on market hours and configuration.

    Test Mode: 24 hours (use stored data, no API calls)
    Market Hours: 60 seconds (data changes frequently)
    Off-Hours with INFINITE_CACHE: 24 hours (prices don't change)
    Off-Hours without INFINITE_CACHE: 30 minutes
    """
    try:
        # Test mode = infinite cache (24 hours)
        if _is_test_mode():
            logger.debug("[PRICE_CACHE] Test mode enabled - using 24h cache")
            return 86400  # 24 hours

        PT = pytz.timezone('America/Los_Angeles')
        now = datetime.now(PT)
        hour = now.hour
        minute = now.minute
        weekday = now.weekday()

        # Convert to minutes since midnight
        current_time = hour * 60 + minute
        market_open = 6 * 60 + 30   # 6:30 AM PT
        market_close = 13 * 60      # 1:00 PM PT

        # During market hours - short cache
        if weekday < 5 and market_open <= current_time <= market_close:
            return 60  # 1 minute

        # Outside market hours
        if _use_infinite_cache_off_hours():
            # Use 24-hour cache - prices don't change when market is closed
            logger.debug("[PRICE_CACHE] Market closed, using 24h cache (infinite mode)")
            return 86400  # 24 hours
        else:
            return 1800  # 30 minutes

    except Exception:
        return 60  # Default to 1 minute if timezone fails


def get_live_prices_fast(symbols: List[str]) -> Dict[str, float]:
    """
    Fetch live prices from Yahoo Finance using direct API (faster than yfinance).
    
    Returns dict of symbol -> current price.
    Uses caching to avoid excessive API calls.
    """
    if not symbols:
        return {}
    
    results = {}
    symbols_to_fetch = []
    now = datetime.now()
    
    # Check cache first with dynamic TTL based on market hours
    cache_ttl = _get_price_cache_ttl()
    
    for symbol in symbols:
        if symbol == 'CASH':
            results[symbol] = 1.0
            continue
            
        if symbol in _price_cache:
            cached_price, cached_time = _price_cache[symbol]
            if (now - cached_time).total_seconds() < cache_ttl:
                results[symbol] = cached_price
                continue
        
        symbols_to_fetch.append(symbol)
    
    # Fetch uncached symbols
    if symbols_to_fetch:
        logger.info(f"Fetching live prices for {len(symbols_to_fetch)} symbols: {symbols_to_fetch}")
        
        for symbol in symbols_to_fetch:
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
                headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
                resp = requests.get(url, headers=headers, timeout=5)
                
                if resp.status_code == 200:
                    data = resp.json()
                    meta = data['chart']['result'][0]['meta']
                    price = meta['regularMarketPrice']
                    results[symbol] = round(price, 2)
                    _price_cache[symbol] = (price, now)
                    # Cache previous close for daily change calculations
                    prev_close = meta.get('chartPreviousClose') or meta.get('previousClose', price)
                    _prev_close_cache[symbol] = round(prev_close, 2)
                else:
                    logger.warning(f"Failed to fetch price for {symbol}: HTTP {resp.status_code}")
                    
            except Exception as e:
                logger.warning(f"Error fetching price for {symbol}: {e}")
        
        # Small delay to avoid rate limiting
        if len(symbols_to_fetch) > 5:
            time.sleep(0.1)
    
    return results


def get_holdings_with_live_prices(db) -> Dict[str, any]:
    """
    Get all holdings with live prices from Yahoo Finance.
    
    Returns holdings grouped by account with:
    - Live prices from Yahoo Finance
    - Calculated market values (shares × live price)
    - Cash balances from portfolio snapshots
    - Price update timestamp
    """
    from decimal import Decimal
    from app.modules.investments.models import InvestmentHolding, InvestmentAccount, PortfolioSnapshot
    
    # Get all active accounts
    accounts = db.query(InvestmentAccount).filter(
        InvestmentAccount.is_active == 'Y'
    ).all()
    
    # Get all holdings
    all_holdings = db.query(InvestmentHolding).filter(
        InvestmentHolding.quantity > 0
    ).all()
    
    # Get unique symbols (excluding CASH)
    symbols = list(set(
        h.symbol for h in all_holdings 
        if h.symbol and h.symbol != 'CASH'
    ))
    
    # Fetch live prices
    live_prices = get_live_prices_fast(symbols)
    price_fetch_time = datetime.utcnow().isoformat() + 'Z'
    
    # Group holdings by account
    holdings_by_account = {}
    for h in all_holdings:
        if h.account_id not in holdings_by_account:
            holdings_by_account[h.account_id] = []
        holdings_by_account[h.account_id].append(h)
    
    # Build result
    result = []
    grand_total = 0
    
    for account in accounts:
        account_id = account.account_id
        holdings = holdings_by_account.get(account_id, [])
        
        # Get cash balance from latest snapshot
        latest_snapshot = db.query(PortfolioSnapshot).filter(
            PortfolioSnapshot.account_id == account_id
        ).order_by(PortfolioSnapshot.statement_date.desc()).first()
        
        # Parse owner from account_id
        parts = account_id.split('_')
        owner = parts[0].title() if parts else 'Unknown'
        account_type = '_'.join(parts[1:]) if len(parts) > 1 else 'brokerage'
        
        # Calculate holdings with live prices
        holdings_data = []
        securities_value = 0
        
        for h in sorted(holdings, key=lambda x: x.symbol):
            qty = float(h.quantity) if h.quantity else 0
            symbol = h.symbol
            
            # Use live price if available, otherwise fallback to stored price
            if symbol in live_prices:
                live_price = live_prices[symbol]
                market_value = qty * live_price
                price_source = 'live'
            else:
                live_price = float(h.current_price) if h.current_price else 0
                market_value = float(h.market_value) if h.market_value else qty * live_price
                price_source = 'cached'
            
            securities_value += market_value

            # Daily change from previous close
            prev_close = _prev_close_cache.get(symbol, live_price)
            price_change = live_price - prev_close
            price_change_pct = (price_change / prev_close * 100) if prev_close > 0 else 0
            holding_change = qty * price_change

            holdings_data.append({
                'symbol': symbol,
                'name': h.description or symbol,
                'shares': qty,
                'currentPrice': round(live_price, 2),
                'totalValue': round(market_value, 2),
                'priceSource': price_source,
                'costBasis': float(h.cost_basis) if h.cost_basis else None,
                'change': round(holding_change, 2),
                'changePercent': round(price_change_pct, 2),
            })
        
        # Get cash balance from snapshot
        cash_balance = 0
        snapshot_date = None
        if latest_snapshot:
            snapshot_value = float(latest_snapshot.portfolio_value) if latest_snapshot.portfolio_value else 0
            stored_securities = float(latest_snapshot.securities_value) if latest_snapshot.securities_value else 0
            cash_balance = float(latest_snapshot.cash_balance) if latest_snapshot.cash_balance else 0
            snapshot_date = latest_snapshot.statement_date.isoformat() if latest_snapshot.statement_date else None
            
            # If no explicit cash balance, try to infer from difference
            if cash_balance == 0 and snapshot_value > stored_securities:
                cash_balance = snapshot_value - stored_securities
        
        # Add cash as a holding if significant
        if cash_balance > 10:
            holdings_data.append({
                'symbol': 'CASH',
                'name': 'Cash & Cash Equivalents',
                'shares': round(cash_balance, 2),
                'currentPrice': 1.0,
                'totalValue': round(cash_balance, 2),
                'priceSource': 'statement',
                'costBasis': None,
                'change': 0,
                'changePercent': 0,
            })

        total_value = securities_value + cash_balance
        grand_total += total_value

        # Calculate account-level daily change (sum of all holding changes)
        account_change = sum(h.get('change', 0) for h in holdings_data)
        prev_total = total_value - account_change
        account_change_pct = (account_change / prev_total * 100) if prev_total > 0 else 0

        # Calculate percentages
        for holding in holdings_data:
            holding['percentOfPortfolio'] = round(
                (holding['totalValue'] / total_value * 100) if total_value > 0 else 0,
                2
            )

        # Sort by value descending
        holdings_data.sort(key=lambda x: x['totalValue'], reverse=True)

        result.append({
            'id': account_id,
            'name': account.account_name or f"{owner}'s {account_type.replace('_', ' ').title()}",
            'owner': owner,
            'type': account_type,
            'value': round(total_value, 2),
            'securitiesValue': round(securities_value, 2),
            'cashBalance': round(cash_balance, 2),
            'change': round(account_change, 2),
            'changePercent': round(account_change_pct, 2),
            'holdings': holdings_data,
            'lastStatementDate': snapshot_date,
            'pricesUpdatedAt': price_fetch_time,
        })
    
    # Sort by standard order
    from app.modules.investments.services import get_account_sort_key
    result.sort(key=lambda x: get_account_sort_key(x['id']))
    
    return {
        'accounts': result,
        'totalValue': round(grand_total, 2),
        'pricesUpdatedAt': price_fetch_time,
        'priceSource': 'yahoo_finance',
    }


def get_price_changes(symbols: List[str]) -> Dict[str, dict]:
    """
    Get price changes for a list of stock symbols.
    
    Returns dict with:
    - current_price: latest price
    - change_1d: 1-day change %
    - change_30d: 30-day change %
    - change_90d: 90-day change %
    - change_1d_value: 1-day change $ per share
    - change_30d_value: 30-day change $ per share
    - change_90d_value: 90-day change $ per share
    """
    results = {}
    
    if not symbols:
        return results
    
    try:
        # Fetch data for all symbols at once (more efficient)
        tickers = yf.Tickers(" ".join(symbols))
        
        # Calculate date ranges
        today = datetime.now()
        date_30d = today - timedelta(days=30)
        date_90d = today - timedelta(days=90)
        
        for symbol in symbols:
            try:
                ticker = tickers.tickers.get(symbol)
                if not ticker:
                    continue
                
                # Get historical data for 90 days
                hist = ticker.history(period="3mo")
                
                if hist.empty:
                    continue
                
                current_price = float(hist['Close'].iloc[-1])
                
                # Get prices at different points
                price_1d_ago = None
                price_30d_ago = None
                price_90d_ago = None
                
                if len(hist) >= 2:
                    price_1d_ago = float(hist['Close'].iloc[-2])
                
                # Find price closest to 30 days ago
                for idx, row_date in enumerate(hist.index):
                    if row_date.date() <= date_30d.date():
                        price_30d_ago = float(hist['Close'].iloc[idx])
                    if row_date.date() <= date_90d.date():
                        price_90d_ago = float(hist['Close'].iloc[idx])
                
                # If we don't have 30/90 day data, use earliest available
                if price_30d_ago is None and len(hist) > 20:
                    price_30d_ago = float(hist['Close'].iloc[0])
                if price_90d_ago is None and len(hist) > 60:
                    price_90d_ago = float(hist['Close'].iloc[0])
                
                # Calculate changes
                results[symbol] = {
                    "current_price": round(current_price, 2),
                    "change_1d": round(((current_price - price_1d_ago) / price_1d_ago * 100), 2) if price_1d_ago else None,
                    "change_30d": round(((current_price - price_30d_ago) / price_30d_ago * 100), 2) if price_30d_ago else None,
                    "change_90d": round(((current_price - price_90d_ago) / price_90d_ago * 100), 2) if price_90d_ago else None,
                    "change_1d_value": round(current_price - price_1d_ago, 2) if price_1d_ago else None,
                    "change_30d_value": round(current_price - price_30d_ago, 2) if price_30d_ago else None,
                    "change_90d_value": round(current_price - price_90d_ago, 2) if price_90d_ago else None,
                    "price_1d_ago": round(price_1d_ago, 2) if price_1d_ago else None,
                    "price_30d_ago": round(price_30d_ago, 2) if price_30d_ago else None,
                    "price_90d_ago": round(price_90d_ago, 2) if price_90d_ago else None,
                }
                
            except Exception as e:
                logger.warning(f"Error fetching price for {symbol}: {e}")
                results[symbol] = {
                    "current_price": None,
                    "change_1d": None,
                    "change_30d": None,
                    "change_90d": None,
                    "error": str(e)
                }
    
    except Exception as e:
        logger.error(f"Error fetching prices: {e}")
    
    return results


def get_single_stock_info(symbol: str) -> Optional[dict]:
    """Get detailed info for a single stock."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        return {
            "symbol": symbol,
            "name": info.get("longName") or info.get("shortName"),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "previous_close": info.get("previousClose"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "dividend_yield": info.get("dividendYield"),
            "52_week_high": info.get("fiftyTwoWeekHigh"),
            "52_week_low": info.get("fiftyTwoWeekLow"),
        }
    except Exception as e:
        logger.error(f"Error fetching info for {symbol}: {e}")
        return None


def update_holdings_with_live_prices(db) -> Dict[str, any]:
    """
    Update all holdings in the database with current Yahoo Finance prices.
    
    This function:
    1. Gets all unique symbols from holdings
    2. Fetches current prices from Yahoo Finance
    3. Updates current_price and market_value for each holding
    
    Returns stats about the update operation.
    """
    from decimal import Decimal
    from app.modules.investments.models import InvestmentHolding
    
    stats = {
        "symbols_fetched": 0,
        "holdings_updated": 0,
        "holdings_skipped": 0,
        "errors": [],
        "price_updates": {},
        "total_value_before": 0,
        "total_value_after": 0,
    }
    
    try:
        # Get all holdings with quantity > 0
        holdings = db.query(InvestmentHolding).filter(
            InvestmentHolding.quantity > 0
        ).all()
        
        if not holdings:
            return stats
        
        # Calculate total value before update
        stats["total_value_before"] = sum(
            float(h.market_value) if h.market_value else 0
            for h in holdings
        )
        
        # Get unique symbols (exclude CASH)
        symbols = list(set(
            h.symbol for h in holdings 
            if h.symbol and h.symbol != 'CASH'
        ))
        
        if not symbols:
            return stats
        
        # Fetch current prices - Schwab first, then Yahoo fallback
        logger.info(f"Fetching prices for {len(symbols)} symbols: {symbols}")
        price_data = get_prices_schwab_first(symbols)
        stats["symbols_fetched"] = len(price_data)
        
        # Track sources
        schwab_count = sum(1 for p in price_data.values() if p.get("source") == "schwab")
        yahoo_count = sum(1 for p in price_data.values() if p.get("source") == "yahoo")
        logger.info(f"Price sources: Schwab={schwab_count}, Yahoo={yahoo_count}")
        
        # Update each holding
        for holding in holdings:
            if holding.symbol == 'CASH':
                stats["holdings_skipped"] += 1
                continue
                
            symbol_prices = price_data.get(holding.symbol)
            if not symbol_prices or not symbol_prices.get("current_price"):
                stats["holdings_skipped"] += 1
                stats["errors"].append(f"No price data for {holding.symbol}")
                continue
            
            current_price = symbol_prices["current_price"]
            quantity = float(holding.quantity) if holding.quantity else 0
            new_market_value = current_price * quantity
            
            # Track what's changing
            old_price = float(holding.current_price) if holding.current_price else 0
            old_value = float(holding.market_value) if holding.market_value else 0
            
            # Update the holding
            holding.current_price = Decimal(str(current_price))
            holding.market_value = Decimal(str(round(new_market_value, 2)))
            holding.last_updated = datetime.utcnow()
            
            stats["holdings_updated"] += 1
            stats["price_updates"][holding.symbol] = {
                "old_price": old_price,
                "new_price": current_price,
                "price_change": round(current_price - old_price, 2),
                "old_value": old_value,
                "new_value": round(new_market_value, 2),
                "value_change": round(new_market_value - old_value, 2),
            }
        
        # Commit all changes
        db.commit()
        
        # Calculate total value after update
        stats["total_value_after"] = sum(
            float(h.market_value) if h.market_value else 0
            for h in holdings
        )
        
        logger.info(f"Updated {stats['holdings_updated']} holdings with live prices")

    except Exception as e:
        logger.error(f"Error updating holdings with live prices: {e}")
        db.rollback()
        stats["errors"].append(str(e))

    return stats


# Cache for stock growth data (1 hour TTL)
_growth_cache: Dict[str, dict] = {}
_growth_cache_time: float = 0
_GROWTH_CACHE_TTL = 3600  # 1 hour


def get_stock_growth_data(symbols: List[str]) -> Dict[str, dict]:
    """
    Fetch YTD, 1Y, and 5Y stock price growth for a list of symbols.
    Uses Schwab API (no rate limits) with yfinance as fallback.
    Returns {symbol: {growth_ytd: float|None, growth_1y: float|None, growth_5y: float|None}}.
    Cached for 1 hour.
    """
    global _growth_cache, _growth_cache_time

    if not symbols:
        return {}

    now = time.time()
    # Check if cache is still valid and has all requested symbols
    if now - _growth_cache_time < _GROWTH_CACHE_TTL and all(s in _growth_cache for s in symbols):
        return {s: _growth_cache[s] for s in symbols}

    result = {}

    # Try Schwab first (no rate limits, supports up to 20 years daily)
    schwab_available = False
    for symbol in symbols:
        try:
            from app.modules.strategies.schwab_service import get_price_history_schwab, is_schwab_configured
            if not is_schwab_configured():
                logger.info("[GROWTH] Schwab not configured, falling back to yfinance")
                break  # Fall through to yfinance for all symbols

            schwab_available = True
            # Fetch 5Y of daily data (covers YTD, 1Y, and 5Y)
            data = get_price_history_schwab(symbol, period_days=5 * 365, frequency="daily")
            if data and data.get("candles"):
                candles = data["candles"]
                result[symbol] = _calc_growth_from_candles(candles)
                logger.info(f"[GROWTH] {symbol}: {result[symbol]}")
                continue
            else:
                logger.warning(f"[GROWTH] Schwab returned no candles for {symbol}")
        except Exception as e:
            logger.warning(f"[GROWTH] Schwab price history failed for {symbol}: {e}")

        # Fallback: yfinance
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5y")
            if hist is not None and not hist.empty:
                close_list = [
                    {"datetime": idx.to_pydatetime(), "close": float(row["Close"])}
                    for idx, row in hist.iterrows()
                ]
                result[symbol] = _calc_growth_from_candles(close_list)
                continue
        except Exception as e:
            logger.debug(f"yfinance history failed for {symbol}: {e}")

        result[symbol] = {'growth_ytd': None, 'growth_1y': None, 'growth_5y': None}

    # Only update cache if we got at least some real data (avoid caching all-null failures)
    has_real_data = any(
        v.get('growth_ytd') is not None or v.get('growth_1y') is not None or v.get('growth_5y') is not None
        for v in result.values()
    )
    if has_real_data:
        _growth_cache.update(result)
        _growth_cache_time = now

    return result


def _calc_growth_from_candles(candles: List[dict]) -> dict:
    """Calculate YTD, 1Y and 5Y growth from a list of candle dicts with 'datetime' and 'close'."""
    if not candles or len(candles) < 2:
        return {'growth_ytd': None, 'growth_1y': None, 'growth_5y': None}

    last_price = candles[-1]["close"]
    now = datetime.now()

    # Find closest candle to target dates
    def find_closest_price(target_date):
        best = None
        best_diff = None
        for c in candles:
            dt = c["datetime"]
            if not hasattr(dt, 'date'):
                continue
            diff = abs((dt - target_date).total_seconds())
            # Only consider candles before or near the target (within 10 days)
            if diff < 10 * 86400 and (best_diff is None or diff < best_diff):
                best = c["close"]
                best_diff = diff
        return best

    def calc_pct(old_price):
        if old_price and old_price > 0:
            return round((last_price - old_price) / old_price * 100, 1)
        return None

    # YTD: first trading day of current year
    ytd_target = datetime(now.year, 1, 2)
    ytd_price = find_closest_price(ytd_target)

    # 1Y: same date last year
    one_year_ago = now - timedelta(days=365)
    price_1y = find_closest_price(one_year_ago)

    # 5Y: same date 5 years ago
    five_years_ago = now - timedelta(days=5 * 365)
    price_5y = find_closest_price(five_years_ago)

    return {
        'growth_ytd': calc_pct(ytd_price),
        'growth_1y': calc_pct(price_1y),
        'growth_5y': calc_pct(price_5y),
    }









