"""
Schwab API Service for Options Data

Provides reliable options data with Greeks (delta, gamma, theta, vega) using
the Charles Schwab API.

This replaces Yahoo Finance for options data because:
1. Reliable rate limits (120 req/min)
2. Always has delta values
3. No rate limiting issues

Setup:
1. Register at developer.schwab.com
2. Create an app to get App Key and Secret
3. Add credentials to .env:
   SCHWAB_APP_KEY=your_app_key
   SCHWAB_APP_SECRET=your_app_secret
   SCHWAB_CALLBACK_URL=https://127.0.0.1:8182/
"""

import os
import json
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import threading

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Schwab client singleton
_schwab_client = None
_schwab_lock = threading.Lock()
_auth_in_progress = False

# Token file location
TOKEN_FILE = Path(__file__).parent.parent.parent.parent / "schwab_token.json"


def get_schwab_credentials() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Get Schwab API credentials from environment."""
    app_key = os.getenv("SCHWAB_APP_KEY")
    app_secret = os.getenv("SCHWAB_APP_SECRET")
    callback_url = os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182/")
    return app_key, app_secret, callback_url


def is_schwab_configured() -> bool:
    """Check if Schwab API is configured."""
    app_key, app_secret, _ = get_schwab_credentials()
    return bool(app_key and app_secret)


def get_schwab_client():
    """
    Get or create the Schwab API client.
    
    First time setup requires browser-based OAuth authentication.
    After initial auth, token is cached for future use.
    """
    global _schwab_client, _auth_in_progress
    
    if _schwab_client is not None:
        return _schwab_client
    
    with _schwab_lock:
        # Double-check after acquiring lock
        if _schwab_client is not None:
            return _schwab_client
        
        if _auth_in_progress:
            logger.warning("Schwab auth already in progress")
            return None
        
        app_key, app_secret, callback_url = get_schwab_credentials()
        
        if not app_key or not app_secret:
            logger.warning("Schwab API not configured - missing SCHWAB_APP_KEY or SCHWAB_APP_SECRET")
            return None
        
        try:
            from schwab import auth
            
            # Check if we have a cached token
            if TOKEN_FILE.exists():
                try:
                    logger.info(f"Loading Schwab token from {TOKEN_FILE}")
                    _schwab_client = auth.client_from_token_file(
                        str(TOKEN_FILE),
                        app_key,
                        app_secret
                    )
                    logger.info("Schwab client loaded from cached token")
                    return _schwab_client
                except Exception as e:
                    logger.warning(f"Failed to load cached token: {e}")
                    TOKEN_FILE.unlink(missing_ok=True)
            
            # Need fresh authentication
            logger.info("Schwab requires browser authentication - run schwab_auth.py manually")
            logger.info("=" * 60)
            logger.info("TO AUTHENTICATE SCHWAB API:")
            logger.info("1. Run: cd backend && ./venv/bin/python -c \"from app.modules.strategies.schwab_service import authenticate_schwab; authenticate_schwab()\"")
            logger.info("2. A browser will open for Schwab login")
            logger.info("3. After login, the token will be saved")
            logger.info("=" * 60)
            return None
            
        except ImportError as e:
            logger.error(f"schwab-py not installed: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to create Schwab client: {e}")
            return None


def authenticate_schwab():
    """
    Interactive authentication for Schwab API.
    
    This opens a browser for OAuth login. Run this manually once to get the token.
    """
    global _schwab_client
    
    app_key, app_secret, callback_url = get_schwab_credentials()
    
    if not app_key or not app_secret:
        print("ERROR: Missing Schwab credentials in .env file")
        print("Required: SCHWAB_APP_KEY and SCHWAB_APP_SECRET")
        return False
    
    try:
        from schwab import auth
        
        print("=" * 60)
        print("SCHWAB API AUTHENTICATION")
        print("=" * 60)
        print(f"App Key: {app_key[:10]}...")
        print(f"Callback URL: {callback_url}")
        print(f"Token will be saved to: {TOKEN_FILE}")
        print()
        print("A browser window will open for Schwab login...")
        print("After login, you'll be redirected to a localhost URL.")
        print("The authentication will complete automatically.")
        print("=" * 60)
        
        _schwab_client = auth.easy_client(
            app_key,
            app_secret,
            callback_url,
            str(TOKEN_FILE)
        )
        
        print()
        print("✅ Authentication successful!")
        print(f"Token saved to: {TOKEN_FILE}")
        return True
        
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return False


def get_options_chain_schwab(
    symbol: str,
    expiration_date: Optional[str] = None,
    option_type: str = "ALL"
) -> Optional[Dict[str, Any]]:
    """
    Get options chain with Greeks from Schwab API.
    
    Args:
        symbol: Stock symbol (e.g., "NVDA")
        expiration_date: Optional expiration date (YYYY-MM-DD)
        option_type: "CALL", "PUT", or "ALL"
    
    Returns:
        Dict with 'calls' and 'puts' lists, each containing options with:
        - strike: Strike price
        - bid: Bid price
        - ask: Ask price
        - delta: Delta value (what we need!)
        - gamma, theta, vega: Other Greeks
        - expirationDate: Expiration date
    """
    client = get_schwab_client()
    
    if client is None:
        logger.warning(f"Schwab client not available for {symbol}")
        return None
    
    try:
        from schwab.client import Client
        
        # Build request parameters
        kwargs = {
            "contract_type": Client.Options.ContractType.ALL if option_type == "ALL" 
                else Client.Options.ContractType.CALL if option_type == "CALL"
                else Client.Options.ContractType.PUT,
            "include_underlying_quote": True,
            "strategy": Client.Options.Strategy.SINGLE,
        }
        
        # Add expiration filter if specified
        if expiration_date:
            from_date = datetime.strptime(expiration_date, "%Y-%m-%d").date()
            to_date = from_date + timedelta(days=1)
            kwargs["from_date"] = from_date
            kwargs["to_date"] = to_date
        
        logger.info(f"[SCHWAB] Fetching options chain for {symbol}")
        response = client.get_option_chain(symbol, **kwargs)
        response.raise_for_status()
        data = response.json()
        
        # Parse the response
        result = {
            "symbol": symbol,
            "underlying_price": None,
            "calls": [],
            "puts": []
        }
        
        # Get underlying price
        if "underlying" in data:
            result["underlying_price"] = data["underlying"].get("last")
        
        # Parse call options
        call_map = data.get("callExpDateMap", {})
        for exp_date, strikes in call_map.items():
            # exp_date format: "2024-12-27:3" (date:days_to_exp)
            exp_date_clean = exp_date.split(":")[0]
            for strike_price, options in strikes.items():
                for opt in options:
                    result["calls"].append({
                        "strike": float(strike_price),
                        "bid": opt.get("bid", 0),
                        "ask": opt.get("ask", 0),
                        "last": opt.get("last", 0),
                        "delta": opt.get("delta"),
                        "gamma": opt.get("gamma"),
                        "theta": opt.get("theta"),
                        "vega": opt.get("vega"),
                        "volume": opt.get("totalVolume", 0),
                        "openInterest": opt.get("openInterest", 0),
                        "expirationDate": exp_date_clean,
                        "inTheMoney": opt.get("inTheMoney", False),
                    })
        
        # Parse put options
        put_map = data.get("putExpDateMap", {})
        for exp_date, strikes in put_map.items():
            exp_date_clean = exp_date.split(":")[0]
            for strike_price, options in strikes.items():
                for opt in options:
                    result["puts"].append({
                        "strike": float(strike_price),
                        "bid": opt.get("bid", 0),
                        "ask": opt.get("ask", 0),
                        "last": opt.get("last", 0),
                        "delta": opt.get("delta"),
                        "gamma": opt.get("gamma"),
                        "theta": opt.get("theta"),
                        "vega": opt.get("vega"),
                        "volume": opt.get("totalVolume", 0),
                        "openInterest": opt.get("openInterest", 0),
                        "expirationDate": exp_date_clean,
                        "inTheMoney": opt.get("inTheMoney", False),
                    })
        
        logger.info(f"[SCHWAB] Got {len(result['calls'])} calls, {len(result['puts'])} puts for {symbol}")
        
        # Log sample delta values for debugging
        if result['calls']:
            sample = result['calls'][:3]
            sample_str = ", ".join([f"${c['strike']}:d={c['delta']}" for c in sample if c['delta'] is not None])
            logger.info(f"[SCHWAB] Sample calls: {sample_str}")
        
        return result
        
    except Exception as e:
        logger.error(f"[SCHWAB] Failed to get options chain for {symbol}: {e}")
        return None


def find_strike_by_delta(
    symbol: str,
    option_type: str,
    expiration_date: str,
    target_delta: float = 0.10,
    current_price: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """
    Find the strike closest to target delta.
    
    This is the key function for strike selection - uses REAL delta from Schwab.
    
    Args:
        symbol: Stock symbol
        option_type: "call" or "put"
        expiration_date: Expiration date (YYYY-MM-DD)
        target_delta: Target delta (0.10 = Delta 10)
        current_price: Current stock price (for OTM filtering)
    
    Returns:
        Dict with strike, delta, bid, ask, etc. or None
    """
    chain = get_options_chain_schwab(symbol, expiration_date, option_type.upper())
    
    if chain is None:
        return None
    
    options = chain["calls"] if option_type.lower() == "call" else chain["puts"]
    
    if not options:
        logger.warning(f"[SCHWAB] No {option_type}s found for {symbol} {expiration_date}")
        return None
    
    # Use underlying price if current_price not provided
    if current_price is None:
        current_price = chain.get("underlying_price")
    
    # Filter to OTM only
    if current_price:
        if option_type.lower() == "call":
            options = [o for o in options if o["strike"] > current_price]
        else:
            options = [o for o in options if o["strike"] < current_price]
    
    # Filter to options with delta data
    options_with_delta = [o for o in options if o.get("delta") is not None]
    
    if not options_with_delta:
        logger.warning(f"[SCHWAB] No options with delta data for {symbol}")
        return None
    
    # Find closest to target delta
    best_option = None
    best_diff = float("inf")
    
    for opt in options_with_delta:
        abs_delta = abs(opt["delta"])
        diff = abs(abs_delta - target_delta)
        
        if diff < best_diff:
            best_diff = diff
            best_option = opt
    
    if best_option:
        logger.info(f"[SCHWAB] {symbol}: Found strike ${best_option['strike']} with delta {best_option['delta']:.3f} (target: {target_delta})")
    
    return best_option


def get_option_expirations_schwab(symbol: str) -> List[str]:
    """
    Get available option expiration dates from Schwab.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        List of expiration dates in YYYY-MM-DD format
    """
    chain = get_options_chain_schwab(symbol, expiration_date=None)  # Get all expirations
    
    if chain is None:
        return []
    
    # Collect unique expiration dates from both calls and puts
    expirations = set()
    
    for opt in chain.get("calls", []):
        if opt.get("expirationDate"):
            expirations.add(opt["expirationDate"])
    
    for opt in chain.get("puts", []):
        if opt.get("expirationDate"):
            expirations.add(opt["expirationDate"])
    
    result = sorted(list(expirations))
    logger.info(f"[SCHWAB] Got {len(result)} expirations for {symbol}")
    return result


def get_schwab_status() -> Dict[str, Any]:
    """Get Schwab API status for debugging."""
    app_key, app_secret, callback_url = get_schwab_credentials()
    
    status = {
        "configured": bool(app_key and app_secret),
        "app_key_set": bool(app_key),
        "app_secret_set": bool(app_secret),
        "callback_url": callback_url,
        "token_file_exists": TOKEN_FILE.exists(),
        "token_file_path": str(TOKEN_FILE),
        "client_ready": _schwab_client is not None,
    }
    
    if TOKEN_FILE.exists():
        try:
            stat = TOKEN_FILE.stat()
            status["token_file_modified"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
        except:
            pass
    
    return status

