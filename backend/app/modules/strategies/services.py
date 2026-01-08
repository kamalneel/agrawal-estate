"""
Services for strategies module including AI-powered options screenshot parsing.

Note: The parse_robinhood_options_text function has been removed.
Use the unified parser at app.ingestion.robinhood_unified_parser instead.
"""

import os
import base64
import json
import re
from datetime import datetime, date
from decimal import Decimal
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path

from sqlalchemy.orm import Session

from app.modules.strategies.models import SoldOptionsSnapshot, SoldOption
from app.core.timezone import format_datetime_for_api


def parse_options_screenshot_with_ai(image_data: bytes, source: str = "robinhood") -> Tuple[List[Dict], str]:
    """
    Use OpenAI Vision API to parse a screenshot of options positions.
    
    Returns:
        Tuple of (list of parsed options, raw extracted text)
    """
    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Encode image to base64
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        # Determine image type from header
        if image_data[:8] == b'\x89PNG\r\n\x1a\n':
            media_type = "image/png"
        elif image_data[:2] == b'\xff\xd8':
            media_type = "image/jpeg"
        else:
            media_type = "image/png"  # Default to PNG
        
        # Create prompt for parsing options
        prompt = """Analyze this screenshot of stock options positions. Extract ALL options shown.

For each option, provide:
1. symbol: The stock ticker (e.g., "AAPL", "TSLA")
2. strike_price: The strike price (number only, e.g., 285)
3. option_type: "call" or "put"
4. expiration_date: The expiration date in YYYY-MM-DD format if visible
5. contracts_sold: Number of contracts (look for "X Sells" or similar)
6. premium: Current premium/price per contract (e.g., 2.84)
7. gain_loss_percent: Percentage gain/loss if shown (e.g., 54.35 for +54.35%)
8. raw_text: The original text line for this option

Return the data as a JSON array. Example:
[
  {
    "symbol": "AAPL",
    "strike_price": 285,
    "option_type": "call",
    "expiration_date": "2024-12-05",
    "contracts_sold": 1,
    "premium": 2.84,
    "gain_loss_percent": 54.35,
    "raw_text": "AAPL $285 Call 12/5 · 1 Sell $2.84 +54.35%"
  }
]

Important:
- Parse ALL options visible in the screenshot
- For dates like "12/5", assume the current or next year
- If contracts count isn't explicit, default to 1
- Negative gain/loss should be negative numbers (e.g., -28.85)
- Only return the JSON array, no other text"""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=4096
        )
        
        raw_text = response.choices[0].message.content
        
        # Parse the JSON response
        # Try to extract JSON from the response
        json_match = re.search(r'\[[\s\S]*\]', raw_text)
        if json_match:
            options_data = json.loads(json_match.group())
        else:
            options_data = []
        
        return options_data, raw_text
        
    except Exception as e:
        print(f"Error parsing screenshot with AI: {e}")
        return [], str(e)


def normalize_expiration_date(date_str: str) -> Optional[date]:
    """
    Normalize various date formats to a standard date object.
    """
    if not date_str:
        return None
    
    today = datetime.now()
    
    # Try various formats
    formats_to_try = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%m/%d",
    ]
    
    for fmt in formats_to_try:
        try:
            parsed = datetime.strptime(date_str, fmt)
            # If no year was in the format, use current or next year
            if fmt == "%m/%d":
                # If the date has passed this year, assume next year
                parsed = parsed.replace(year=today.year)
                if parsed.date() < today.date():
                    parsed = parsed.replace(year=today.year + 1)
            return parsed.date()
        except ValueError:
            continue
    
    return None


def save_parsed_options(
    db: Session,
    snapshot_id: int,
    options_data: List[Dict]
) -> int:
    """
    Save parsed options to the database.
    
    Returns the number of options saved.
    """
    count = 0
    
    for opt in options_data:
        try:
            # Parse expiration date
            exp_date = None
            if opt.get("expiration_date"):
                exp_date = normalize_expiration_date(opt["expiration_date"])
            
            sold_option = SoldOption(
                snapshot_id=snapshot_id,
                symbol=opt.get("symbol", "UNKNOWN").upper(),
                strike_price=Decimal(str(opt.get("strike_price", 0))),
                option_type=opt.get("option_type", "call").lower(),
                expiration_date=exp_date,
                contracts_sold=int(opt.get("contracts_sold", 1)),
                premium_per_contract=Decimal(str(opt.get("premium", 0))) if opt.get("premium") else None,
                gain_loss_percent=Decimal(str(opt.get("gain_loss_percent", 0))) if opt.get("gain_loss_percent") else None,
                status="open",
                raw_text=opt.get("raw_text", "")[:500]  # Limit to 500 chars
            )
            db.add(sold_option)
            count += 1
        except Exception as e:
            print(f"Error saving option {opt}: {e}")
            continue
    
    return count


def get_sold_options_by_account(db: Session) -> Dict[str, Dict]:
    """
    Get sold options grouped by account name.
    
    Returns a dictionary mapping account_name -> {by_symbol: {...}, snapshot: {...}}
    This allows us to match sold options to specific accounts.
    """
    from sqlalchemy import func
    
    # Get all successful snapshots grouped by account (latest per account)
    subquery = db.query(
        SoldOptionsSnapshot.account_name,
        func.max(SoldOptionsSnapshot.id).label('max_id')
    ).filter(
        SoldOptionsSnapshot.parsing_status == 'success',
        SoldOptionsSnapshot.account_name.isnot(None)
    ).group_by(SoldOptionsSnapshot.account_name).subquery()
    
    # Get the actual snapshots
    snapshots = db.query(SoldOptionsSnapshot).join(
        subquery, SoldOptionsSnapshot.id == subquery.c.max_id
    ).all()
    
    result = {}
    
    for snapshot in snapshots:
        account_name = snapshot.account_name
        
        # Get all options for this snapshot
        options = db.query(SoldOption).filter(
            SoldOption.snapshot_id == snapshot.id
        ).all()
        
        # Group by symbol
        by_symbol = {}
        total_contracts = 0
        
        for opt in options:
            if opt.symbol not in by_symbol:
                by_symbol[opt.symbol] = []
            
            by_symbol[opt.symbol].append({
                "id": opt.id,
                "strike_price": float(opt.strike_price),
                "option_type": opt.option_type,  # 'call' or 'put' - needed to filter covered calls vs cash-secured puts
                "contracts_sold": opt.contracts_sold,
            })
            total_contracts += opt.contracts_sold
        
        result[account_name] = {
            "snapshot": {
                "id": snapshot.id,
                "source": snapshot.source,
                "account_name": account_name,
                "snapshot_date": snapshot.snapshot_date.isoformat(),
            },
            "by_symbol": by_symbol,
            "total_contracts": total_contracts
        }
    
    # Debug: Log what we're returning
    import logging
    logger = logging.getLogger(__name__)
    logger.debug(f"get_sold_options_by_account returning {len(result)} accounts: {list(result.keys())}")
    for acc_name, data in result.items():
        logger.debug(f"  {acc_name}: {len(data.get('by_symbol', {}))} symbols, MU in symbols: {'MU' in data.get('by_symbol', {})}")
    
    return result


def get_current_sold_options(db: Session, source: Optional[str] = None) -> Dict:
    """
    Get the most recent sold options data.
    
    Returns a dictionary with:
    - snapshot info (date, source)
    - list of sold options grouped by symbol
    - summary statistics
    """
    from sqlalchemy import func
    
    # Get the most recent snapshot(s) - one per source if no source specified
    query = db.query(SoldOptionsSnapshot).filter(
        SoldOptionsSnapshot.parsing_status == 'success'
    )
    
    if source:
        query = query.filter(SoldOptionsSnapshot.source == source)
    
    # Get latest snapshot
    latest_snapshot = query.order_by(SoldOptionsSnapshot.snapshot_date.desc()).first()
    
    if not latest_snapshot:
        return {
            "has_data": False,
            "snapshot": None,
            "options": [],
            "by_symbol": {},
            "summary": {
                "total_contracts": 0,
                "unique_symbols": 0
            }
        }
    
    # Get all options for this snapshot
    options = db.query(SoldOption).filter(
        SoldOption.snapshot_id == latest_snapshot.id
    ).all()
    
    # Group by symbol
    by_symbol = {}
    total_contracts = 0
    
    for opt in options:
        if opt.symbol not in by_symbol:
            by_symbol[opt.symbol] = []
        
        by_symbol[opt.symbol].append({
            "id": opt.id,
            "strike_price": float(opt.strike_price),
            "option_type": opt.option_type,
            "expiration_date": opt.expiration_date.isoformat() if opt.expiration_date else None,
            "contracts_sold": opt.contracts_sold,
            "premium": float(opt.premium_per_contract) if opt.premium_per_contract else None,
            "gain_loss_percent": float(opt.gain_loss_percent) if opt.gain_loss_percent else None,
            "status": opt.status
        })
        total_contracts += opt.contracts_sold
    
    return {
        "has_data": True,
        "snapshot": {
            "id": latest_snapshot.id,
            "source": latest_snapshot.source,
            "account_name": latest_snapshot.account_name,
            "snapshot_date": latest_snapshot.snapshot_date.isoformat(),
            "created_at": format_datetime_for_api(latest_snapshot.created_at)
        },
        "options": [
            {
                "symbol": opt.symbol,
                "strike_price": float(opt.strike_price),
                "option_type": opt.option_type,
                "expiration_date": opt.expiration_date.isoformat() if opt.expiration_date else None,
                "contracts_sold": opt.contracts_sold,
                "premium": float(opt.premium_per_contract) if opt.premium_per_contract else None,
                "gain_loss_percent": float(opt.gain_loss_percent) if opt.gain_loss_percent else None
            }
            for opt in options
        ],
        "by_symbol": by_symbol,
        "summary": {
            "total_contracts": total_contracts,
            "unique_symbols": len(by_symbol)
        }
    }


def calculate_unsold_options(
    holdings_by_symbol: Dict[str, int],  # symbol -> total options available
    sold_options: Dict[str, List[Dict]]  # symbol -> list of sold options
) -> Dict[str, Dict]:
    """
    Calculate which options are unsold based on holdings and sold options.
    
    Returns a dictionary with status per symbol:
    {
        "AAPL": {
            "available": 7,
            "sold": 1,
            "unsold": 6,
            "status": "partial"  # "none", "partial", "full"
        }
    }
    """
    result = {}
    
    for symbol, available in holdings_by_symbol.items():
        sold_count = 0
        if symbol in sold_options:
            # Only count CALLS - puts don't require share backing (they're cash-secured)
            sold_count = sum(
                opt["contracts_sold"] for opt in sold_options[symbol]
                if opt.get("option_type", "").lower() == "call"
            )
        
        unsold = max(0, available - sold_count)
        
        if sold_count == 0:
            status = "none"
        elif unsold == 0:
            status = "full"
        else:
            status = "partial"
        
        result[symbol] = {
            "available": available,
            "sold": sold_count,
            "unsold": unsold,
            "status": status
        }
    
    return result


def calculate_4_week_average_premiums(
    db: Session,
    weeks: int = 4
) -> Dict[str, Dict]:
    """
    Calculate 4-week running average of weekly option premiums per symbol.
    
    This function:
    1. Gets ALL STO transactions from the last N weeks
    2. Filters to only weekly options (7-8 days to expiration)
    3. Calculates average premium per share across ALL accounts
    4. Returns data for auto-updating premium settings
    
    Returns:
        {
            "AAPL": {
                "avg_premium_per_share": 0.5150,
                "premium_per_contract": 51.50,  # per share * 100
                "transaction_count": 6,
                "date_range": "2025-11-21 to 2025-12-04",
                "last_updated": "2025-12-08"
            },
            ...
        }
    """
    from app.modules.investments.models import InvestmentTransaction
    from sqlalchemy import func, desc
    from datetime import date, timedelta
    import re
    from collections import defaultdict
    
    # Get date N weeks ago
    cutoff_date = date.today() - timedelta(days=weeks * 7)
    
    def parse_expiration_date(description):
        """Extract expiration date from option description."""
        if not description:
            return None
        match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', description)
        if match:
            month, day, year = map(int, match.groups())
            try:
                return date(year, month, day)
            except:
                return None
        return None
    
    # Get ALL STO transactions from last N weeks
    all_sto = db.query(InvestmentTransaction).filter(
        InvestmentTransaction.transaction_type == 'STO',
        InvestmentTransaction.symbol.isnot(None),
        InvestmentTransaction.symbol != '',
        InvestmentTransaction.transaction_date >= cutoff_date
    ).all()
    
    # Group by symbol and filter to weekly options
    symbol_data = defaultdict(list)
    
    for txn in all_sto:
        quantity = abs(float(txn.quantity)) if txn.quantity else 1
        amount = abs(float(txn.amount)) if txn.amount else 0
        price_per_share = float(txn.price_per_share) if txn.price_per_share else 0
        
        # Premium per share (use price_per_share field if available, otherwise calculate)
        premium_per_share = price_per_share if price_per_share > 0 else (amount / quantity) / 100
        
        # Parse expiration date
        exp_date = parse_expiration_date(txn.description)
        days_to_expiry = None
        if exp_date and txn.transaction_date:
            days_to_expiry = (exp_date - txn.transaction_date).days
        
        # Only include weekly options (7-8 days to expiration)
        if days_to_expiry and 7 <= days_to_expiry <= 8:
            symbol_data[txn.symbol].append({
                'date': txn.transaction_date,
                'premium_per_share': premium_per_share,
                'days_to_expiry': days_to_expiry,
                'contracts': int(quantity),
                'account_id': txn.account_id,
                'description': txn.description
            })
    
    # Calculate averages for each symbol
    result = {}
    for symbol, transactions in symbol_data.items():
        if len(transactions) > 0:
            # Calculate average premium per share across ALL transactions
            avg_premium_per_share = sum(t['premium_per_share'] for t in transactions) / len(transactions)
            
            # Convert to premium per contract (multiply by 100)
            premium_per_contract = avg_premium_per_share * 100
            
            # Get date range
            dates = [t['date'] for t in transactions]
            min_date = min(dates)
            max_date = max(dates)
            
            result[symbol] = {
                "avg_premium_per_share": round(avg_premium_per_share, 4),
                "premium_per_contract": round(premium_per_contract, 2),
                "transaction_count": len(transactions),
                "date_range": f"{min_date} to {max_date}",
                "last_updated": datetime.utcnow().isoformat(),
                "accounts": len(set(t['account_id'] for t in transactions))  # Number of unique accounts
            }
    
    return result


def update_premium_settings_from_averages(
    db: Session,
    weeks: int = 4,
    min_transactions: int = 1
) -> Dict[str, Any]:
    """
    Auto-update premium settings based on 4-week running average.
    
    Only updates symbols that:
    1. Have at least min_transactions in the last N weeks
    2. Are not manually overridden (manual_override = False)
    3. Have is_auto_updated = True
    
    Returns:
        {
            "updated": 5,
            "skipped": 3,
            "details": {...}
        }
    """
    from app.modules.strategies.models import OptionPremiumSetting
    from typing import Any
    
    # Calculate averages
    averages = calculate_4_week_average_premiums(db, weeks)
    
    updated_count = 0
    skipped_count = 0
    details = {}
    
    for symbol, data in averages.items():
        # Skip if not enough transactions
        if data['transaction_count'] < min_transactions:
            skipped_count += 1
            details[symbol] = {
                "status": "skipped",
                "reason": f"Insufficient data: {data['transaction_count']} < {min_transactions} transactions"
            }
            continue
        
        # Get or create setting
        setting = db.query(OptionPremiumSetting).filter(
            OptionPremiumSetting.symbol == symbol
        ).first()
        
        if setting:
            # Check if manually overridden
            if setting.manual_override:
                skipped_count += 1
                details[symbol] = {
                    "status": "skipped",
                    "reason": "Manually overridden",
                    "current_premium": float(setting.premium_per_contract),
                    "calculated_premium": data['premium_per_contract']
                }
                continue
            
            # Update if auto-update is enabled
            if setting.is_auto_updated:
                old_premium = float(setting.premium_per_contract)
                setting.premium_per_contract = Decimal(str(data['premium_per_contract']))
                setting.last_auto_update = datetime.utcnow()
                updated_count += 1
                details[symbol] = {
                    "status": "updated",
                    "old_premium": old_premium,
                    "new_premium": data['premium_per_contract'],
                    "transaction_count": data['transaction_count'],
                    "accounts": data['accounts']
                }
            else:
                skipped_count += 1
                details[symbol] = {
                    "status": "skipped",
                    "reason": "Auto-update disabled",
                    "current_premium": float(setting.premium_per_contract)
                }
        else:
            # Create new setting with auto-update enabled
            setting = OptionPremiumSetting(
                symbol=symbol,
                premium_per_contract=Decimal(str(data['premium_per_contract'])),
                is_auto_updated=True,
                last_auto_update=datetime.utcnow(),
                manual_override=False
            )
            db.add(setting)
            updated_count += 1
            details[symbol] = {
                "status": "created",
                "premium": data['premium_per_contract'],
                "transaction_count": data['transaction_count'],
                "accounts": data['accounts']
            }
    
    db.flush()
    
    return {
        "updated": updated_count,
        "skipped": skipped_count,
        "total_symbols": len(averages),
        "details": details
    }

