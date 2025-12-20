"""
Unified Robinhood Parser

Handles parsing of copy-pasted data from Robinhood, detecting and parsing:
1. Stock holdings
2. Options list view (Positions Held)
3. Options detail view (with Average credit)

This replaces the separate parsers and provides a single entry point for all
Robinhood data import.
"""

import re
from datetime import datetime, date
from decimal import Decimal
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class ParsedStock:
    """Represents a parsed stock holding."""
    symbol: str
    name: str
    shares: float
    market_value: float
    current_price: float
    raw_lines: List[str] = field(default_factory=list)


@dataclass
class ParsedOption:
    """Represents a parsed option position."""
    symbol: str
    strike_price: float
    option_type: str  # 'call' or 'put'
    expiration_date: Optional[str]  # MM/DD or MM/DD/YYYY format
    contracts: int
    current_premium: Optional[float]
    original_premium: Optional[float]  # From "Average credit" in detail view
    gain_loss_percent: Optional[float]
    total_return_percent: Optional[float]  # From detail view
    date_sold: Optional[str]
    raw_text: str


@dataclass
class ParseResult:
    """Result of parsing Robinhood data."""
    stocks: List[ParsedStock] = field(default_factory=list)
    options: List[ParsedOption] = field(default_factory=list)
    detected_format: str = "unknown"
    warnings: List[str] = field(default_factory=list)
    raw_text: str = ""
    has_options_section: bool = False  # True if "Options" header was detected
    has_stocks_section: bool = False  # True if "Stocks" header was detected


def detect_format(text: str) -> str:
    """
    Detect what format the pasted text is in.
    
    Returns: 'stocks', 'options_list', 'options_detail', 'mixed', or 'unknown'
    """
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    
    # Options detail view indicators
    if any('Average credit' in l for l in lines):
        return 'options_detail'
    
    if any('Total return' in l for l in lines):
        return 'options_detail'
    
    if any('Contracts' in l and '-' in l for l in lines):
        return 'options_detail'
    
    # Check for explicit section headers (case-insensitive)
    # This handles cases where user has "Options" and "Stocks" headers
    # even if one section is empty
    has_options_header = any(re.match(r'^Options$', l, re.IGNORECASE) for l in lines)
    has_stocks_header = any(re.match(r'^Stocks?$', l, re.IGNORECASE) for l in lines)
    
    # Options list indicators
    has_option_pattern = any(re.match(r'^[A-Z]+\s+\$[\d.]+\s+(Call|Put)$', l, re.IGNORECASE) for l in lines)
    has_sells = any(re.search(r'\d+\s+sells?', l, re.IGNORECASE) for l in lines)
    
    # Stock indicators
    has_shares = any(re.search(r'[\d,.]+\s+shares?', l, re.IGNORECASE) for l in lines)
    
    # If both section headers are present, treat as mixed format
    # This handles the case where user has "Options" header with no data
    # and "Stocks" header with data
    if has_options_header and has_stocks_header:
        return 'mixed'
    
    # If only Options header is present (even with no data), treat as options_list
    # This handles the case where user has "Options" header but no actual options data
    if has_options_header and not has_stocks_header:
        return 'options_list'
    
    # If only Stocks header is present (even with no data), treat as stocks
    # This handles the case where user has "Stocks" header but no actual stock data
    if has_stocks_header and not has_options_header:
        return 'stocks'
    
    # Positions Held header
    if any('Positions Held' in l for l in lines):
        if has_option_pattern or has_sells:
            if has_shares:
                return 'mixed'
            return 'options_list'
        if has_shares:
            return 'stocks'
    
    if has_option_pattern or has_sells:
        if has_shares:
            return 'mixed'
        return 'options_list'
    
    if has_shares:
        return 'stocks'
    
    return 'unknown'


def parse_robinhood_data(text: str, account_name: Optional[str] = None) -> ParseResult:
    """
    Main entry point for parsing Robinhood data.
    
    Automatically detects the format and parses accordingly.
    """
    result = ParseResult(raw_text=text)
    
    # Check for explicit section headers before parsing
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    result.has_options_section = any(re.match(r'^Options$', l, re.IGNORECASE) for l in lines)
    result.has_stocks_section = any(re.match(r'^Stocks?$', l, re.IGNORECASE) for l in lines)
    
    detected = detect_format(text)
    result.detected_format = detected
    
    logger.info(f"Detected format: {detected}")
    if result.has_options_section:
        logger.info("Options section header detected")
    if result.has_stocks_section:
        logger.info("Stocks section header detected")
    
    if detected == 'options_detail':
        option = parse_options_detail_view(text)
        if option:
            result.options.append(option)
    
    elif detected == 'options_list':
        result.options = parse_options_list_view(text)
    
    elif detected == 'stocks':
        result.stocks = parse_stock_holdings(text)
    
    elif detected == 'mixed':
        # Parse both stocks and options
        result.stocks = parse_stock_holdings(text)
        result.options = parse_options_list_view(text)
    
    else:
        result.warnings.append("Could not detect data format. Please ensure you copied from Robinhood.")
    
    return result


def parse_stock_holdings(text: str) -> List[ParsedStock]:
    """
    Parse stock holdings from Robinhood.
    
    Expected format when copying from Robinhood app:
    
    AAPL
    Apple Inc
    1,700 Shares
    $277.55          <- This is the PRICE PER SHARE
    +$2.34 (+0.85%)  <- Daily change (skip this)
    
    The dollar amount AFTER the shares line is the current price per share.
    We calculate: market_value = shares × price_per_share
    """
    holdings = []
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Look for a stock symbol line (all uppercase, 1-5 letters)
        # But NOT option patterns like "AAPL $285 Call"
        symbol_match = re.match(r'^([A-Z]{1,5})$', line)
        
        if symbol_match and not _is_option_context(lines, i):
            symbol = symbol_match.group(1)
            
            holding = ParsedStock(
                symbol=symbol,
                name=symbol,
                shares=0.0,
                market_value=0.0,
                current_price=0.0,
                raw_lines=[line]
            )
            
            # Track if we've seen shares (to know what the dollar amount means)
            seen_shares = False
            price_per_share = 0.0
            
            # Look ahead for name, shares, and price
            j = i + 1
            while j < min(i + 6, len(lines)):
                next_line = lines[j]
                
                # Check for shares - handles both "1,700 Shares" and "1.56K shares" formats
                # Robinhood uses "K" suffix for 1000+ shares (e.g., "1.56K shares" = 1,560)
                shares_match = re.match(r'^([\d,]+\.?\d*)\s*(K)?\s*Shares?$', next_line, re.IGNORECASE)
                if shares_match:
                    shares_value = float(shares_match.group(1).replace(',', ''))
                    # Check for "K" suffix (thousands)
                    if shares_match.group(2) and shares_match.group(2).upper() == 'K':
                        shares_value *= 1000
                        logger.debug(f"{symbol}: Parsed {shares_match.group(1)}K as {shares_value} shares")
                    holding.shares = shares_value
                    seen_shares = True
                    holding.raw_lines.append(next_line)
                    j += 1
                    continue
                
                # Check for dollar amount (price per share OR total value)
                # In Robinhood paste format, this is the PRICE PER SHARE
                if not next_line.startswith(('+', '-', '−')):
                    value_match = re.match(r'^\$?([\d,]+\.?\d*)$', next_line)
                    if value_match:
                        dollar_amount = float(value_match.group(1).replace(',', ''))
                        holding.raw_lines.append(next_line)
                        
                        # If we've already seen shares, this dollar amount is the price per share
                        if seen_shares and holding.shares > 0:
                            price_per_share = dollar_amount
                            holding.current_price = dollar_amount
                            holding.market_value = round(holding.shares * dollar_amount, 2)
                            logger.debug(f"{symbol}: {holding.shares} shares × ${dollar_amount:.2f} = ${holding.market_value:,.2f}")
                        else:
                            # Haven't seen shares yet, store temporarily
                            # This might be the price if we see shares later
                            price_per_share = dollar_amount
                        
                        j += 1
                        continue
                
                # Check for company name
                if (_is_company_name(next_line) and 
                    not re.match(r'^[A-Z]{1,5}$', next_line)):
                    holding.name = next_line
                    holding.raw_lines.append(next_line)
                    j += 1
                    continue
                
                # Skip daily change lines
                if 'Today' in next_line or next_line.startswith(('+', '-', '−')):
                    holding.raw_lines.append(next_line)
                    j += 1
                    continue
                
                # If we hit another symbol, stop
                if re.match(r'^[A-Z]{1,5}$', next_line):
                    break
                
                j += 1
            
            # If we have shares and a price but haven't calculated market_value yet
            # (this handles cases where price appeared before shares)
            if holding.shares > 0 and price_per_share > 0 and holding.market_value == 0:
                holding.current_price = price_per_share
                holding.market_value = round(holding.shares * price_per_share, 2)
                logger.debug(f"{symbol} (deferred): {holding.shares} shares × ${price_per_share:.2f} = ${holding.market_value:,.2f}")
            
            # Validation: if market_value seems too small (less than price), 
            # it might be that we captured price as market_value incorrectly
            if holding.shares > 0 and holding.market_value > 0:
                implied_price = holding.market_value / holding.shares
                # If implied price is unreasonably low (< $0.01), recalculate
                if implied_price < 0.01 and holding.current_price > 0:
                    holding.market_value = round(holding.shares * holding.current_price, 2)
                    logger.warning(f"{symbol}: Recalculated market_value to ${holding.market_value:,.2f}")
            
            if holding.shares > 0 or holding.market_value > 0:
                holdings.append(holding)
                logger.info(f"Parsed holding: {symbol} - {holding.shares} shares @ ${holding.current_price:.2f} = ${holding.market_value:,.2f}")
                i = j
                continue
        
        i += 1
    
    return holdings


def parse_options_list_view(text: str) -> List[ParsedOption]:
    """
    Parse options from the list view format.
    
    Handles TWO Robinhood display modes:
    
    1. "Last Price" mode:
       IBIT $54 Call
       12/5 · 15 sells
       $0.01           <- Current premium per contract
       -87.50%         <- Return percentage
    
    2. "Total Return" mode:
       AAPL $292.5 Call
       12/12 · 17 sells
       +$1,666.00      <- Total dollar return (NOT premium!)
       +88.29%         <- Return percentage
    
    Skips "Pending Orders" section - these are unexecuted orders like:
       AVGO $315 Put
       12/19 • 1 buy to close
       $0.30 Limit
    """
    options = []
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    
    # Skip "Pending Orders" section - look for section boundaries
    # Pending orders have "buy to close" / "buys to close" which we don't want
    # We only want "Positions Held" which have "sell" / "sells"
    start_index = 0
    in_pending_section = False
    
    for idx, line in enumerate(lines):
        if re.match(r'^Pending\s*Orders?$', line, re.IGNORECASE):
            in_pending_section = True
            logger.info(f"Found 'Pending Orders' section at line {idx}, skipping...")
            continue
        if re.match(r'^Positions?\s*Held$', line, re.IGNORECASE):
            in_pending_section = False
            start_index = idx + 1
            logger.info(f"Found 'Positions Held' section at line {idx}, starting parse from line {start_index}")
            break
    
    # If we found a Pending Orders section but no Positions Held, skip all
    if in_pending_section:
        logger.warning("Found 'Pending Orders' but no 'Positions Held' section - returning empty list")
        return []
    
    i = start_index
    while i < len(lines):
        line = lines[i]
        
        # Look for: SYMBOL $PRICE Call/Put
        option_match = re.match(r'^([A-Z]+)\s+\$?([\d.]+)\s+(Call|Put)$', line, re.IGNORECASE)
        
        if option_match:
            symbol = option_match.group(1).upper()
            strike_price = float(option_match.group(2))
            option_type = option_match.group(3).lower()
            
            option = ParsedOption(
                symbol=symbol,
                strike_price=strike_price,
                option_type=option_type,
                expiration_date=None,
                contracts=1,
                current_premium=None,
                original_premium=None,
                gain_loss_percent=None,
                total_return_percent=None,
                date_sold=None,
                raw_text=line
            )
            
            # Look for expiration and contracts: "12/5 · 15 sells" or "12/5 • 17 sells"
            # Also detect and skip pending orders: "12/5 · 1 buy to close" or "12/5 • 2 buys to close"
            if i + 1 < len(lines):
                date_line = lines[i + 1]
                
                # Check if this is a pending order (buy to close) - skip these
                pending_match = re.match(
                    r'^(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s*[·•]\s*\d+\s*buys?\s+to\s+close$',
                    date_line, 
                    re.IGNORECASE
                )
                if pending_match:
                    logger.debug(f"Skipping pending order: {symbol} ${strike_price} {option_type}")
                    i += 1  # Move past this entry
                    continue  # Skip adding this to options
                
                # Check for actual position (sells)
                date_match = re.match(
                    r'^(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s*[·•]\s*(\d+)\s*sells?$',
                    date_line, 
                    re.IGNORECASE
                )
                if date_match:
                    option.expiration_date = date_match.group(1)
                    option.contracts = int(date_match.group(2))
                    option.raw_text += f" | {date_line}"
                    i += 1
            
            # Next line could be either:
            # - Current premium: "$0.14" (Last Price mode)
            # - Dollar return: "+$1,666.00" or "-$500.00" (Total Return mode)
            dollar_return_value = None
            
            if i + 1 < len(lines):
                value_line = lines[i + 1]
                
                # Check for "Last Price" mode: simple price like "$0.14" or "0.14"
                # Must NOT start with + or - and should be a simple number
                premium_match = re.match(r'^\$?([\d.]+)$', value_line)
                
                # Check for "Total Return" mode: dollar amount like "+$1,666.00" or "-$500.00"
                # Has +/- prefix and possibly commas
                dollar_return_match = re.match(r'^([+-])\$?([\d,]+\.?\d*)$', value_line)
                
                if premium_match and not value_line.startswith('+') and not value_line.startswith('-'):
                    # This is a current premium (Last Price mode)
                    option.current_premium = float(premium_match.group(1))
                    option.raw_text += f" | {value_line}"
                    i += 1
                elif dollar_return_match:
                    # This is a dollar return amount (Total Return mode)
                    # Extract the value for later calculation
                    sign = 1 if dollar_return_match.group(1) == '+' else -1
                    amount_str = dollar_return_match.group(2).replace(',', '')
                    dollar_return_value = sign * float(amount_str)
                    option.raw_text += f" | {value_line} (dollar return)"
                    i += 1
            
            # Look for gain/loss percentage: "+54.35%" or "-28.85%"
            if i + 1 < len(lines):
                gl_line = lines[i + 1]
                gl_match = re.match(r'^([+-]?[\d.]+)%$', gl_line)
                if gl_match:
                    option.gain_loss_percent = float(gl_match.group(1))
                    option.raw_text += f" | {gl_line}"
                    i += 1
            
            # Calculate original premium
            if option.current_premium and option.gain_loss_percent is not None:
                # Method 1: We have current premium (Last Price mode)
                option.original_premium = _calculate_original_premium(
                    option.current_premium,
                    option.gain_loss_percent
                )
            elif dollar_return_value is not None and option.gain_loss_percent is not None and option.contracts > 0:
                # Method 2: We have dollar return (Total Return mode)
                # Calculate original premium from dollar return and percentage
                # dollar_return = original_premium * contracts * 100 * (gain_loss_percent / 100)
                # So: original_premium = dollar_return / (contracts * 100 * gain_loss_percent / 100)
                #                      = dollar_return / (contracts * gain_loss_percent)
                if option.gain_loss_percent != 0:
                    # dollar_return = profit_per_share * contracts * 100
                    # profit_per_share = original_premium * gain_loss_percent / 100
                    # So: dollar_return = original_premium * gain_loss_percent / 100 * contracts * 100
                    #     dollar_return = original_premium * gain_loss_percent * contracts
                    #     original_premium = dollar_return / (gain_loss_percent * contracts)
                    original = dollar_return_value / (option.gain_loss_percent / 100 * option.contracts * 100)
                    if original > 0:
                        option.original_premium = round(original, 4)
                        # Also calculate current premium from original and G/L
                        # current = original * (1 - gain_loss_percent/100)
                        option.current_premium = round(original * (1 - option.gain_loss_percent / 100), 4)
            
            # Only add options that have meaningful data (expiration date is required for tracking)
            # This prevents incomplete pending order entries from being added
            if option.expiration_date:
                options.append(option)
            else:
                logger.debug(f"Skipping option without expiration date: {option.symbol} ${option.strike_price} {option.option_type}")
        
        i += 1
    
    return options


def parse_options_detail_view(text: str) -> Optional[ParsedOption]:
    """
    Parse options from the detail view format (Screenshot 2).
    
    Expected format:
    Your position
    
    Market value    -$15.00
    Current price   $0.01
    Average credit  $0.23      <-- This is the original premium!
    Contracts       -15
    Expiration date 12/5
    Date sold       11/26
    Total return    +$330.00 (+95.65%)
    """
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    
    option = ParsedOption(
        symbol="",
        strike_price=0.0,
        option_type="call",
        expiration_date=None,
        contracts=1,
        current_premium=None,
        original_premium=None,
        gain_loss_percent=None,
        total_return_percent=None,
        date_sold=None,
        raw_text=text[:500]
    )
    
    for line in lines:
        # Symbol and strike from header (e.g., "IBIT $54 Call" or from context)
        symbol_match = re.match(r'^([A-Z]+)\s+\$?([\d.]+)\s+(Call|Put)', line, re.IGNORECASE)
        if symbol_match:
            option.symbol = symbol_match.group(1).upper()
            option.strike_price = float(symbol_match.group(2))
            option.option_type = symbol_match.group(3).lower()
            continue
        
        # Also match format like "Current IBIT price"
        ticker_price_match = re.search(r'Current\s+([A-Z]+)\s+price', line, re.IGNORECASE)
        if ticker_price_match and not option.symbol:
            option.symbol = ticker_price_match.group(1).upper()
            continue
        
        # "breakeven price" pattern: "IBIT breakeven price $54.23"
        breakeven_match = re.match(r'^([A-Z]+)\s+breakeven\s+price\s+\$?([\d.]+)', line, re.IGNORECASE)
        if breakeven_match:
            if not option.symbol:
                option.symbol = breakeven_match.group(1).upper()
            # Can derive strike from breakeven - strike ≈ breakeven for calls
            continue
        
        # Current price
        current_match = re.match(r'^Current\s+price\s+\$?([\d.]+)$', line, re.IGNORECASE)
        if current_match:
            option.current_premium = float(current_match.group(1))
            continue
        
        # Average credit (THE KEY DATA - original premium)
        credit_match = re.match(r'^Average\s+credit\s+\$?([\d.]+)$', line, re.IGNORECASE)
        if credit_match:
            option.original_premium = float(credit_match.group(1))
            continue
        
        # Contracts
        contracts_match = re.match(r'^Contracts\s+(-?\d+)$', line, re.IGNORECASE)
        if contracts_match:
            option.contracts = abs(int(contracts_match.group(1)))
            continue
        
        # Expiration date
        exp_match = re.match(r'^Expiration\s+date\s+(\d{1,2}/\d{1,2}(?:/\d{2,4})?)$', line, re.IGNORECASE)
        if exp_match:
            option.expiration_date = exp_match.group(1)
            continue
        
        # Date sold
        sold_match = re.match(r'^Date\s+sold\s+(\d{1,2}/\d{1,2}(?:/\d{2,4})?)$', line, re.IGNORECASE)
        if sold_match:
            option.date_sold = sold_match.group(1)
            continue
        
        # Total return with percentage
        return_match = re.search(r'Total\s+return.*\(\+?([-\d.]+)%\)', line, re.IGNORECASE)
        if return_match:
            option.total_return_percent = float(return_match.group(1))
            continue
        
        # Today's return (less useful but capture it)
        today_match = re.search(r"Today's\s+return.*\(\+?([-\d.]+)%\)", line, re.IGNORECASE)
        if today_match and option.gain_loss_percent is None:
            # Use today's return as gain_loss_percent if we don't have total return
            pass  # We'll prefer total_return if available
    
    # Use total_return as gain_loss if available
    if option.total_return_percent is not None:
        option.gain_loss_percent = option.total_return_percent
    
    # Only return if we got meaningful data
    if option.symbol and (option.original_premium or option.current_premium):
        return option
    
    return None


def _is_option_context(lines: List[str], index: int) -> bool:
    """Check if a symbol line is in an options context (followed by option-like lines)."""
    if index + 1 < len(lines):
        next_line = lines[index + 1]
        # Check if next line looks like an option expiry/sells line
        if re.search(r'\d+\s+sells?', next_line, re.IGNORECASE):
            return True
        # Check if it's part of an option pattern
        if re.match(r'^\d{1,2}/\d{1,2}', next_line):
            return True
    return False


def _is_company_name(line: str) -> bool:
    """Check if a line looks like a company name."""
    # Company names usually have lowercase letters, spaces, or are longer
    if re.match(r'^[A-Z]{1,5}$', line):
        return False
    if 'Shares' in line or '$' in line or '%' in line:
        return False
    if 'Today' in line or 'sell' in line.lower():
        return False
    return True


def _calculate_original_premium(current_premium: float, gain_loss_percent: float) -> Optional[float]:
    """
    Calculate original premium from current premium and gain/loss percentage.
    
    For sold options:
    - gain_loss_percent = (original - current) / original * 100
    - Solving for original: original = current / (1 - gain_loss_percent/100)
    
    Note: This formula breaks down for extreme percentages (>100% gain or <-100% loss).
    """
    if gain_loss_percent == 100:
        return None  # Division by zero
    
    try:
        original = current_premium / (1 - gain_loss_percent / 100)
        
        # Sanity check - original premium can't be negative
        if original < 0:
            logger.warning(f"Calculated negative original premium: {original} from current={current_premium}, gl={gain_loss_percent}%")
            return None
        
        return round(original, 4)
    except Exception:
        return None


def normalize_expiration_date(date_str: str) -> Optional[date]:
    """
    Normalize expiration date string to a date object.
    
    Handles formats like:
    - "12/5" -> assumes current/next year
    - "12/5/25" -> 2025
    - "12/5/2025" -> 2025
    - "1/16/2026" -> 2026
    """
    if not date_str:
        return None
    
    try:
        parts = date_str.split('/')
        
        if len(parts) == 2:
            # MM/DD format - assume current or next year
            month, day = int(parts[0]), int(parts[1])
            today = date.today()
            
            # Try current year first
            try:
                result = date(today.year, month, day)
                # If date is more than 30 days in the past, assume next year
                if (today - result).days > 30:
                    result = date(today.year + 1, month, day)
                return result
            except ValueError:
                return None
        
        elif len(parts) == 3:
            month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
            
            # Handle 2-digit year
            if year < 100:
                year += 2000
            
            return date(year, month, day)
    
    except Exception as e:
        logger.warning(f"Could not parse date '{date_str}': {e}")
    
    return None

