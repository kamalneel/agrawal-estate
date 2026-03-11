"""
India stock price refresh service using Yahoo Finance API.

Fetches live prices for NSE/BSE stocks via Yahoo Finance query API.
No extra dependencies needed - uses requests (already installed).
"""

import requests
import logging
from decimal import Decimal
from typing import Optional, Dict, List
from datetime import datetime
from sqlalchemy.orm import Session

from app.modules.india_investments.models import FatherStockHolding, FatherMutualFundHolding

logger = logging.getLogger(__name__)

YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
MFAPI_BASE_URL = "https://api.mfapi.in/mf"

# Map of father's fund names to MFapi scheme codes (reused from router)
FATHER_FUND_SCHEME_CODES = {
    "PPF": None,
    "Reliance": None,
    "SBI Global": "119598",
    "SBI MNC Fund (G)": "119700",
    "ICICI Asset Allocator": "120606",
    "ICICI Banking Plus SIP": "120594",
    "ICICI Pru Banking & Financial Services (G)": "120594",
    "ICICI Blue Chip Plus SIP": "120586",
    "ICICI Pru Large Cap Fund (G)": "120586",
    "ICICI Balance Limited": "120574",
    "ICICI Pru Balanced Advantage Fund (G)": "120574",
    "ICICI Pru Dynamic Asset Allocation Active FOF-Reg (G)": "149652",
    "Franklin Prima Plus SIP": "100470",
    "Franklin India Mid Cap Fund (G)": "100470",
    "Franklin Focused Equity Fund": "100498",
    "ABSL Banking Plus SIP": "119551",
    "Aditya Birla SL Banking & Financial Services (G)": "100177",
    "ABSL Frontline SIP": "100177",
    "Aditya Birla SL Large Cap Fund (G)": "100177",
    "ABSL Business Cycle Fund": "149486",
    "Aditya Birla SL Business Cycle Fund (G)": "149486",
    "Edelweiss Small Cap": "147946",
    "Edelweiss Aggressive Hybrid Fund": "120348",
    "Edelweiss Balance Advantage": "120351",
    "Edelweiss Balanced Advantage Fund (G)": "120351",
    "Elelwise Multi Asset Omni Fund": "150583",
    "DSP Aggressive Hybrid Fund": "100056",
    "DSP Flexi Cap Quality 30 Index Fund": "150936",
    "Mirae Asset Mutual Fund": "118834",
    "Mirae Asset Small Cap Fund - Regular (G)": "147622",
    "HSBC Aggressive Hybrid Fund (G)": "120222",
    "Invesco Indian Business Cycle Fund": "150481",
}


def fetch_yahoo_stock_prices(symbols: List[str]) -> Dict[str, float]:
    """
    Fetch current stock prices from Yahoo Finance for NSE-listed symbols.

    Args:
        symbols: List of NSE symbols (e.g., ['RELIANCE', 'TCS', 'INFY'])

    Returns:
        Dict mapping symbol -> current price in INR
    """
    if not symbols:
        return {}

    # Yahoo Finance uses .NS suffix for NSE stocks
    yahoo_symbols = [f"{s}.NS" for s in symbols]
    results = {}

    # Yahoo API accepts comma-separated symbols (batch up to 20)
    for i in range(0, len(yahoo_symbols), 20):
        batch = yahoo_symbols[i:i + 20]
        try:
            response = requests.get(
                YAHOO_QUOTE_URL,
                params={
                    "symbols": ",".join(batch),
                    "fields": "regularMarketPrice,shortName",
                },
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            for quote in data.get("quoteResponse", {}).get("result", []):
                symbol = quote.get("symbol", "").replace(".NS", "")
                price = quote.get("regularMarketPrice")
                if symbol and price is not None:
                    results[symbol] = price

        except Exception as e:
            logger.error(f"Error fetching Yahoo prices for batch: {e}")

    return results


def fetch_mf_latest_nav(scheme_code: str) -> Optional[float]:
    """Fetch the latest NAV for a mutual fund from MFapi.in."""
    try:
        response = requests.get(f"{MFAPI_BASE_URL}/{scheme_code}/latest", timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("status") == "SUCCESS":
            nav_data = data.get("data", [])
            if nav_data:
                return float(nav_data[0]["nav"])
    except Exception as e:
        logger.error(f"Error fetching NAV for scheme {scheme_code}: {e}")
    return None


def refresh_father_stock_prices(db: Session) -> Dict:
    """
    Refresh current prices for all of Father's stock holdings using Yahoo Finance.

    Updates current_price and current_amount for each holding.
    """
    holdings = db.query(FatherStockHolding).all()
    if not holdings:
        return {"updated": 0, "errors": 0, "details": {"updated": [], "errors": []}}

    # Collect unique symbols
    symbols = list(set(h.symbol for h in holdings if h.symbol))
    prices = fetch_yahoo_stock_prices(symbols)

    updated = []
    errors = []

    for holding in holdings:
        symbol = holding.symbol
        if symbol not in prices:
            errors.append({"symbol": symbol, "error": "Price not found on Yahoo Finance"})
            continue

        price = prices[symbol]
        quantity = float(holding.quantity or 0)
        current_amount = quantity * price

        holding.current_price = Decimal(str(round(price, 4)))
        holding.current_amount = Decimal(str(round(current_amount, 2)))
        holding.last_updated = datetime.utcnow()

        updated.append({
            "symbol": symbol,
            "price": price,
            "current_amount": current_amount,
        })

    db.commit()
    return {
        "updated": len(updated),
        "errors": len(errors),
        "details": {"updated": updated, "errors": errors},
    }


def refresh_father_mf_current_amounts(db: Session) -> Dict:
    """
    Refresh current_amount for Father's mutual fund holdings using latest NAV from MFapi.

    For funds with scheme codes, fetches the latest NAV and recalculates current_amount.
    """
    holdings = db.query(FatherMutualFundHolding).all()
    if not holdings:
        return {"updated": 0, "errors": 0, "details": {"updated": [], "errors": []}}

    updated = []
    errors = []

    for holding in holdings:
        scheme_code = FATHER_FUND_SCHEME_CODES.get(holding.fund_name) or holding.scheme_code
        if not scheme_code:
            errors.append({"fund_name": holding.fund_name, "error": "No scheme code mapped"})
            continue

        nav = fetch_mf_latest_nav(scheme_code)
        if nav is None:
            errors.append({"fund_name": holding.fund_name, "error": "Could not fetch NAV"})
            continue

        # Estimate current amount using initial investment and NAV growth
        # If we have the initial NAV (from avg cost / purchase price), we can calculate precisely
        # Otherwise we use the return-based estimation already in the system
        # For now, update the holding's return data and let the existing logic handle it

        # Simpler approach: if we have amount_march_2025 and 1y return, estimate current
        initial = float(holding.initial_invested_amount or 0)
        if initial <= 0:
            continue

        # Use scheme NAV history to get a more precise current amount
        try:
            from app.modules.india_investments.mf_research_service import get_scheme_nav_history, calculate_returns
            nav_history = get_scheme_nav_history(scheme_code, days=365)
            if nav_history:
                returns = calculate_returns(nav_history)
                return_1y = returns.get("return_1y")
                if return_1y is not None:
                    holding.return_1y = Decimal(str(return_1y))

                # Calculate current amount based on investment date and returns
                if holding.investment_date:
                    from datetime import date
                    years_held = (date.today() - holding.investment_date).days / 365.25
                    if years_held > 0 and nav_history:
                        latest_nav = float(nav_history[0]["nav"])
                        # Find NAV closest to investment date
                        sorted_navs = sorted(nav_history, key=lambda x: x["date"])
                        closest_to_start = None
                        for n in sorted_navs:
                            if n["date"] >= holding.investment_date:
                                closest_to_start = n
                                break
                        if not closest_to_start:
                            closest_to_start = sorted_navs[-1]

                        start_nav = float(closest_to_start["nav"])
                        if start_nav > 0:
                            growth = latest_nav / start_nav
                            current_amount = initial * growth
                            holding.current_amount = Decimal(str(round(current_amount, 2)))

                            updated.append({
                                "fund_name": holding.fund_name,
                                "current_amount": current_amount,
                                "return_1y": return_1y,
                            })
                            holding.last_updated = datetime.utcnow()
                            continue

        except Exception as e:
            logger.warning(f"NAV history calculation failed for {holding.fund_name}: {e}")

        errors.append({"fund_name": holding.fund_name, "error": "Could not calculate current amount"})

    db.commit()
    return {
        "updated": len(updated),
        "errors": len(errors),
        "details": {"updated": updated, "errors": errors},
    }
