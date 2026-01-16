"""
Notification Organizer for Strategy Recommendations

Groups notifications by account and adds profit estimation.
This creates cleaner, more actionable messages for Telegram.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


def estimate_premium(
    symbol: str,
    strike: float,
    current_price: float,
    contracts: int = 1,
    weekly_income: Optional[float] = None
) -> float:
    """
    Estimate the premium for a covered call option.
    
    Uses either:
    1. weekly_income from context if available
    2. Simple volatility-based estimate (2-4% of stock price for weeklies)
    
    Args:
        symbol: Stock symbol
        strike: Strike price
        current_price: Current stock price
        contracts: Number of contracts
        weekly_income: Pre-calculated weekly income if available
    
    Returns:
        Estimated premium in dollars (total, not per share)
    """
    if weekly_income and weekly_income > 0:
        return weekly_income
    
    if strike <= 0 or current_price <= 0:
        return 0.0
    
    # Distance from current price (OTM percentage)
    otm_pct = (strike - current_price) / current_price if strike > current_price else 0
    
    # Base premium estimate: ~0.5-2% of stock price for weekly OTM calls
    # Higher for volatile stocks, lower for stable stocks
    # We use a simple heuristic: 1% base, reduced by OTM distance
    base_premium_pct = 0.01  # 1% of stock price
    
    # Reduce premium for further OTM strikes
    otm_reduction = max(0.2, 1 - otm_pct * 3)  # Reduce by 3x OTM%, min 20%
    
    premium_per_share = current_price * base_premium_pct * otm_reduction
    
    # Per contract (100 shares)
    return premium_per_share * 100 * contracts


def group_by_account(recommendations: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group recommendations by full account name (including account type).
    
    Groups by individual accounts like:
    - "Neel's Brokerage"
    - "Neel's IRA"
    - "Jaya's Brokerage"
    - etc.
    
    Args:
        recommendations: List of recommendation dicts
    
    Returns:
        Dict mapping full account name to list of recommendations
    """
    groups = defaultdict(list)
    
    for rec in recommendations:
        context = rec.get("context", {})
        account = rec.get("account_name") or context.get("account_name") or context.get("account", "")
        
        # Normalize account name - keep full name to distinguish account types
        if account:
            # Clean up the account name but keep the full identifier
            # e.g., "Neel's Brokerage" stays as "Neel's Brokerage"
            # e.g., "neel_brokerage" becomes "Neel's Brokerage"
            account_clean = _normalize_account_name(account)
        else:
            account_clean = "Unknown"
        
        groups[account_clean].append(rec)
    
    return dict(groups)


def _normalize_account_name(account: str) -> str:
    """
    Normalize account name to a consistent display format.
    
    Examples:
    - "Neel's Brokerage" -> "Neel's Brokerage"
    - "neel_brokerage" -> "Neel's Brokerage"
    - "Jaya's IRA" -> "Jaya's IRA"
    - "jaya_ira" -> "Jaya's IRA"
    """
    if not account:
        return "Unknown"
    
    # If already in "Name's Type" format, just clean it up
    if "'" in account:
        return account.strip()
    
    # Convert snake_case to display format
    # e.g., "neel_brokerage" -> "Neel's Brokerage"
    account_lower = account.lower().strip()
    
    # Map of account_id patterns to display names
    account_mappings = {
        "neel_brokerage": "Neel's Brokerage",
        "neel_ira": "Neel's IRA",
        "neel_retirement": "Neel's Retirement",
        "neel_roth": "Neel's Roth IRA",
        "neel_roth_ira": "Neel's Roth IRA",
        "jaya_brokerage": "Jaya's Brokerage",
        "jaya_ira": "Jaya's IRA",
        "jaya_retirement": "Jaya's Retirement",
        "jaya_roth": "Jaya's Roth IRA",
        "jaya_roth_ira": "Jaya's Roth IRA",
        "alicia_brokerage": "Alicia's Brokerage",
        "alicia_ira": "Alicia's IRA",
    }
    
    if account_lower in account_mappings:
        return account_mappings[account_lower]
    
    # Check for partial matches
    for key, display_name in account_mappings.items():
        if key in account_lower or account_lower in key:
            return display_name
    
    # If no mapping found, try to format nicely
    # e.g., "some_account" -> "Some Account"
    return account.replace("_", " ").title()


def sort_by_profit(recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort recommendations by estimated profit (highest first).
    
    ROLL recommendations come first (more urgent), then SELL recommendations.
    Within each category, sort by total premium/profit.
    """
    def get_sort_key(rec):
        rec_type = rec.get("type", "")
        context = rec.get("context", {})
        
        # Priority: urgent actions first
        type_priority = {
            "close_early_opportunity": 0,
            "roll_options": 1,
            "early_roll_opportunity": 2,
            "sell_unsold_contracts": 3,
            "new_covered_call": 4,
        }
        priority = type_priority.get(rec_type, 5)
        
        # Total premium/profit (negative for sorting descending)
        # V3: Prefer total_premium from real-time data
        total_premium = context.get("total_premium", 0) or 0
        premium_per_contract = context.get("premium_per_contract", 0) or 0
        potential_income = rec.get("potential_income", 0) or 0
        
        # Use total_premium first, then potential_income, then per-contract
        estimated_profit = total_premium or potential_income or premium_per_contract
        
        return (priority, -estimated_profit)
    
    return sorted(recommendations, key=get_sort_key)


def format_single_recommendation(rec: Dict[str, Any], include_account: bool = True) -> str:
    """
    Format a single recommendation with profit estimation.
    
    Args:
        rec: Recommendation dict
        include_account: Whether to include account name
    
    Returns:
        Formatted string for this recommendation
    """
    rec_type = rec.get("type", "")
    context = rec.get("context", {})
    
    # Extract common fields
    symbol = context.get("symbol", "")
    strike = context.get("strike_price", 0) or context.get("recommended_strike", 0)
    opt_type = context.get("option_type", "call")
    contracts = context.get("contracts", 1) or context.get("uncovered_contracts", 1)
    current_price = context.get("current_price", 0)
    account = rec.get("account_name") or context.get("account_name") or context.get("account", "")
    profit_pct = context.get("profit_percent", 0)
    weekly_income = context.get("weekly_income", 0)
    
    # Account tag (short)
    account_short = ""
    if include_account and account:
        account_short = account.split("'")[0] if "'" in account else account[:10]
    
    # Get premium - prefer real-time from context, fall back to estimate
    # V3: Use premium_per_contract from real-time options chain
    premium_per_contract = context.get("premium_per_contract", 0) or 0
    total_premium = context.get("total_premium", 0) or 0
    
    # Calculate estimated premium only as fallback
    estimated_premium = 0
    if not premium_per_contract or premium_per_contract <= 0:
        estimated_premium = estimate_premium(
            symbol=symbol,
            strike=float(strike) if strike else 0,
            current_price=float(current_price) if current_price else 0,
            contracts=int(contracts) if contracts else 1,
            weekly_income=float(weekly_income) if weekly_income else None
        )
    
    # Format based on recommendation type
    if rec_type == "close_early_opportunity":
        current_premium = context.get("current_premium", 0)
        exp_date = context.get("expiration_date", "")
        exp_str = _format_date(exp_date)
        dte = _calculate_dte(exp_date)
        dte_str = f" ({dte}d)" if dte > 0 and exp_date else ""

        price_str = f"@ ${current_premium:.2f}" if current_premium else ""
        line = f"CLOSE: {contracts} {symbol} ${strike} {opt_type}s {exp_str}{dte_str} {price_str}"
        if profit_pct:
            line += f" ({profit_pct:.0f}%)"
        if account_short:
            line += f" {account_short}"
        return line
    
    elif rec_type in ["early_roll_opportunity", "roll_options"]:
        old_strike = context.get("old_strike", context.get("current_strike", strike))
        current_exp = context.get("current_expiration", context.get("expiration_date", ""))
        new_strike = context.get("new_strike", strike)
        new_exp = context.get("new_expiration", "")

        # Format dates
        current_exp_str = _format_date(current_exp)
        new_exp_str = _format_date(new_exp)
        new_dte = _calculate_dte(new_exp)
        dte_str = f" ({new_dte}d)" if new_dte > 0 and new_exp else ""

        line = f"ROLL: {symbol} {contracts}x ${old_strike} {opt_type}"
        if current_exp_str:
            line += f" {current_exp_str}"
        if new_strike:
            line += f" → ${float(new_strike):.0f} {opt_type}"
        if new_exp_str:
            line += f" {new_exp_str}{dte_str}"
        if current_price:
            line += f" · Stock ${current_price:.0f}"
        if profit_pct:
            line += f" ({profit_pct:.0f}%)"
        if account_short:
            line += f" {account_short}"
        return line
    
    elif rec_type in ["new_covered_call", "sell_unsold_contracts"]:
        unsold = context.get("unsold_contracts", contracts)
        rec_strike = context.get("strike_price", 0) or context.get("recommended_strike", strike)
        exp_date = context.get("expiration_date", "")

        # Format expiration
        exp_str = _format_date(exp_date)
        if not exp_str:
            # Calculate next Friday
            today = date.today()
            days_ahead = 4 - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            next_friday = today + timedelta(days=days_ahead)
            exp_str = next_friday.strftime('%b %d %Y')

        # Calculate DTE
        dte = _calculate_dte(exp_date) if exp_date else 0
        dte_str = f" ({dte}d)" if dte > 0 else ""

        if rec_strike and float(rec_strike) > 0:
            strike_str = f"${float(rec_strike):.0f}" if float(rec_strike) >= 100 else f"${float(rec_strike):.2f}"
            line = f"SELL: {unsold} {symbol} {strike_str} {opt_type}s {exp_str}{dte_str}"
        else:
            line = f"SELL: {unsold} {symbol} {opt_type}s {exp_str}{dte_str}"

        if current_price:
            line += f" · Stock ${current_price:.0f}"

        # Add premium info - prefer real-time data from context
        premium_per_contract = context.get("premium_per_contract", 0)
        total_premium = context.get("total_premium", 0)
        premium_source = context.get("premium_source", "")

        if premium_per_contract and premium_per_contract > 0:
            # Show per-contract premium (real-time when available)
            if unsold > 1 and total_premium > 0:
                line += f" (${premium_per_contract:.0f}/ct, ${total_premium:.0f} total)"
            else:
                line += f" (${premium_per_contract:.0f})"
        elif estimated_premium > 0:
            # Fallback to estimated premium
            line += f" (~${estimated_premium:.0f})"

        if account_short:
            line += f" {account_short}"

        return line
    
    elif rec_type in ["bull_put_spread", "mega_cap_bull_put"]:
        sell_strike = context.get("sell_strike", "")
        buy_strike = context.get("buy_strike", "")
        credit = context.get("net_credit", 0)
        label = "BULL PUT" if rec_type == "bull_put_spread" else "BULL PUT (not in portfolio)"
        if sell_strike and buy_strike:
            return f"{label}: {symbol} ${float(sell_strike):.0f}/${float(buy_strike):.0f} (${credit:.2f} cr)"
        return f"{label}: {symbol}"
    
    else:
        # Default - use title
        return f"• {rec.get('title', str(rec))}"


def _format_date(date_str: str) -> str:
    """Format a date string to 'Dec 26 2025' format with year."""
    if not date_str:
        return ""
    try:
        if 'T' in date_str:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.strftime('%b %d %Y')
    except:
        return date_str[5:10] if len(date_str) >= 10 else date_str


def _calculate_dte(date_str: str) -> int:
    """Calculate days to expiration."""
    if not date_str:
        return 0
    try:
        if 'T' in date_str:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
        today = date.today()
        exp_date = dt.date() if hasattr(dt, 'date') else dt
        dte = (exp_date - today).days
        return max(0, dte)  # Don't show negative DTE
    except:
        return 0


def format_grouped_message(recommendations: List[Dict[str, Any]]) -> str:
    """
    Format recommendations grouped by individual account with real-time premium data.
    
    This is the main function to create the consolidated message.
    Groups by specific accounts (Brokerage, IRA, Retirement) not just by owner.
    
    Example output:
    ```
    *Neel's Brokerage - 3 Recommendations:*
    • SELL: 15 IBIT $53 calls Dec 26 · Stock $51 ($22/ct, $338 total)
    • SELL: 1 NVDA $195 calls Dec 26 · Stock $183 ($220)
    • SELL: 1 MSFT $509 calls Dec 26 · Stock $484 ($180)
    
    *Neel's IRA - 2 Recommendations:*
    • SELL: 1 MU $100 calls Dec 26 · Stock $95 ($150)
    • SELL: 1 TSM $200 calls Dec 26 · Stock $190 ($180)
    
    *Jaya's Brokerage - 2 Recommendations:*
    • SELL: 1 NVDA $195 calls Dec 26 · Stock $183 ($220)
    • ROLL: AVGO 2x $362.5 put → $350 Jan 2 · Stock $340
    
    7:12 AM
    ```
    """
    if not recommendations:
        return ""
    
    # Group by account
    grouped = group_by_account(recommendations)
    
    lines = []
    
    # Sort accounts in a consistent order:
    # 1. Neel's Brokerage, Neel's IRA, Neel's Retirement/Roth
    # 2. Jaya's Brokerage, Jaya's IRA, Jaya's Retirement/Roth
    # 3. Others
    def get_account_sort_key(account_name: str) -> tuple:
        name_lower = account_name.lower()
        
        # Owner order: Neel=0, Jaya=1, Alicia=2, others=99
        if "neel" in name_lower:
            owner_order = 0
        elif "jaya" in name_lower:
            owner_order = 1
        elif "alicia" in name_lower:
            owner_order = 2
        else:
            owner_order = 99
        
        # Account type order: Brokerage=0, IRA=1, Retirement=2, Roth=3, others=99
        if "brokerage" in name_lower or "investment" in name_lower:
            type_order = 0
        elif "ira" in name_lower and "roth" not in name_lower:
            type_order = 1
        elif "retirement" in name_lower:
            type_order = 2
        elif "roth" in name_lower:
            type_order = 3
        else:
            type_order = 99
        
        return (owner_order, type_order, account_name)
    
    sorted_accounts = sorted(grouped.keys(), key=get_account_sort_key)
    
    for account in sorted_accounts:
        account_recs = grouped[account]
        
        # Sort recommendations by profit within the account
        sorted_recs = sort_by_profit(account_recs)
        
        # Header for this account - use full account name directly
        count = len(sorted_recs)
        header = f"*{account} - {count} Recommendation{'s' if count > 1 else ''}:*"
        lines.append(header)
        
        # Format each recommendation (without account name since it's in header)
        for rec in sorted_recs:
            formatted = format_single_recommendation(rec, include_account=False)
            lines.append(f"• {formatted}")
        
        lines.append("")  # Blank line between accounts
    
    # Remove trailing empty line
    while lines and lines[-1] == "":
        lines.pop()
    
    # Add timestamp
    now = datetime.now()
    time_str = now.strftime("%I:%M %p").lstrip('0')
    lines.append(f"_{time_str}_")
    
    return "\n".join(lines)


def format_ungrouped_message(recommendations: List[Dict[str, Any]]) -> str:
    """
    Format recommendations without grouping (original style but with profit).
    
    Falls back to this for very short lists or mixed priorities.
    """
    if not recommendations:
        return ""
    
    lines = []
    
    # Sort by profit
    sorted_recs = sort_by_profit(recommendations)
    
    for rec in sorted_recs:
        formatted = format_single_recommendation(rec, include_account=True)
        lines.append(formatted)
    
    # Add timestamp
    now = datetime.now()
    time_str = now.strftime("%I:%M %p").lstrip('0')
    lines.append(f"_{time_str}_")
    
    return "\n".join(lines)


def organize_and_format(recommendations: List[Dict[str, Any]], group_threshold: int = 3) -> str:
    """
    Main entry point: Organize and format recommendations.
    
    Args:
        recommendations: List of recommendation dicts
        group_threshold: Minimum recommendations to trigger grouping
    
    Returns:
        Formatted message string ready for Telegram
    """
    if not recommendations:
        return ""
    
    # Group if we have enough recommendations
    if len(recommendations) >= group_threshold:
        return format_grouped_message(recommendations)
    else:
        return format_ungrouped_message(recommendations)

