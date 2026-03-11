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

    Aggregates across ALL recent snapshots for each account so that partial
    uploads don't wipe out previously-captured symbols.  For each symbol,
    the data from the most recent snapshot that mentions it is used.
    Options whose expiration_date has already passed are excluded.

    Returns a dictionary mapping account_name -> {by_symbol: {...}, snapshot: {...}}
    This allows us to match sold options to specific accounts.
    """
    from sqlalchemy import func
    from datetime import date as date_type, timedelta, datetime as dt_type
    import logging
    logger = logging.getLogger(__name__)

    today = date_type.today()
    # Only look back 30 days for snapshots — options rarely last longer
    cutoff = dt_type.combine(today - timedelta(days=30), dt_type.min.time())

    # Get recent successful snapshots, ordered newest-first
    snapshots = db.query(SoldOptionsSnapshot).filter(
        SoldOptionsSnapshot.parsing_status == 'success',
        SoldOptionsSnapshot.account_name.isnot(None),
        SoldOptionsSnapshot.snapshot_date >= cutoff,
    ).order_by(SoldOptionsSnapshot.id.desc()).all()

    # Group snapshots by account name
    snapshots_by_account: Dict[str, list] = {}
    for s in snapshots:
        snapshots_by_account.setdefault(s.account_name, []).append(s)

    result = {}

    for account_name, account_snapshots in snapshots_by_account.items():
        # The most recent snapshot provides the "snapshot" metadata
        latest_snapshot = account_snapshots[0]

        # For each symbol, take data from the most recent snapshot that mentions it.
        # Since account_snapshots is already newest-first, the first occurrence wins.
        #
        # Key rule: if the LATEST snapshot doesn't mention a symbol, it's closed —
        # the user's current positions are the source of truth.  We only fall back
        # to older snapshots for symbols that the latest snapshot also contains
        # (to pick up additional strikes/expiries from partial uploads).
        by_symbol: Dict[str, list] = {}
        seen_symbols: set = set()
        total_contracts = 0

        # Build the set of symbols present in the latest snapshot
        latest_options = db.query(SoldOption).filter(
            SoldOption.snapshot_id == latest_snapshot.id
        ).all()
        latest_symbols: set = set()
        for opt in latest_options:
            latest_symbols.add(opt.symbol)

        for snapshot in account_snapshots:
            if snapshot.id == latest_snapshot.id:
                options = latest_options  # reuse already-fetched rows
            else:
                options = db.query(SoldOption).filter(
                    SoldOption.snapshot_id == snapshot.id
                ).all()

            # Collect symbols present in this snapshot
            snapshot_symbols: Dict[str, list] = {}
            for opt in options:
                snapshot_symbols.setdefault(opt.symbol, []).append(opt)

            is_older_snapshot = (snapshot.id != latest_snapshot.id)

            for symbol, opts in snapshot_symbols.items():
                if symbol in seen_symbols:
                    continue  # Already have newer data for this symbol

                # If this symbol is NOT in the latest snapshot, it's been
                # closed/expired — skip it regardless of expiration date.
                if is_older_snapshot and symbol not in latest_symbols:
                    seen_symbols.add(symbol)
                    continue

                # Filter out individually expired options
                valid_opts = []
                for opt in opts:
                    if opt.expiration_date is not None and opt.expiration_date < today:
                        continue
                    valid_opts.append({
                        "id": opt.id,
                        "strike_price": float(opt.strike_price),
                        "option_type": opt.option_type,
                        "contracts_sold": opt.contracts_sold,
                    })

                if valid_opts:
                    by_symbol[symbol] = valid_opts
                    total_contracts += sum(o["contracts_sold"] for o in valid_opts)

                seen_symbols.add(symbol)

        result[account_name] = {
            "snapshot": {
                "id": latest_snapshot.id,
                "source": latest_snapshot.source,
                "account_name": account_name,
                "snapshot_date": latest_snapshot.snapshot_date.isoformat(),
            },
            "by_symbol": by_symbol,
            "total_contracts": total_contracts,
        }

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
    Calculate 4-week NET premium per contract by symbol, separated by option type.

    CORRECT Algorithm:
    1. Get ALL STO (Sell To Open) and BTC (Buy To Close) transactions from last N weeks
    2. Separate CALLS from PUTS based on description
    3. For each symbol and option type:
       - Total STO amount (income)
       - Total BTC amount (buy-back cost)
       - Net Premium = STO - BTC
       - Total Contracts = sum of STO contract quantities
       - Premium per Contract = Net Premium / Total Contracts
    4. Divide by N weeks to get weekly average per contract

    Returns:
        {
            "AAPL": {
                "call_premium_per_contract": 51.50,  # NET weekly premium for calls
                "put_premium_per_contract": 85.00,   # NET weekly premium for puts
                "call_contracts": 12,
                "put_contracts": 4,
                "call_net_total": 618.00,
                "put_net_total": 340.00,
                "date_range": "2025-11-21 to 2025-12-18",
                "last_updated": "2025-12-08"
            },
            ...
        }
    """
    from app.modules.investments.models import InvestmentTransaction
    from datetime import date, timedelta
    from collections import defaultdict

    # Get date N weeks ago
    cutoff_date = date.today() - timedelta(days=weeks * 7)

    # Get ALL STO and BTC transactions from last N weeks
    all_transactions = db.query(InvestmentTransaction).filter(
        InvestmentTransaction.transaction_type.in_(['STO', 'BTC']),
        InvestmentTransaction.symbol.isnot(None),
        InvestmentTransaction.symbol != '',
        InvestmentTransaction.transaction_date >= cutoff_date
    ).all()

    # Structure: {symbol: {'call': {'sto_amount': 0, 'btc_amount': 0, 'contracts': 0}, 'put': {...}}}
    symbol_data = defaultdict(lambda: {
        'call': {'sto_amount': 0, 'btc_amount': 0, 'contracts': 0, 'dates': []},
        'put': {'sto_amount': 0, 'btc_amount': 0, 'contracts': 0, 'dates': []}
    })

    for txn in all_transactions:
        # Extract underlying symbol (e.g., "TSLA 01/17/2026 450.00 C" -> "TSLA")
        underlying = txn.symbol.split()[0] if txn.symbol else None
        if not underlying:
            continue

        # Determine option type from description
        description = (txn.description or '').lower()
        if 'call' in description:
            option_type = 'call'
        elif 'put' in description:
            option_type = 'put'
        else:
            continue  # Skip if can't determine type

        amount = abs(float(txn.amount)) if txn.amount else 0
        quantity = abs(float(txn.quantity)) if txn.quantity else 1

        data = symbol_data[underlying][option_type]
        data['dates'].append(txn.transaction_date)

        if txn.transaction_type == 'STO':
            data['sto_amount'] += amount
            data['contracts'] += int(quantity)
        elif txn.transaction_type == 'BTC':
            data['btc_amount'] += amount

    # Calculate net premium per contract for each symbol
    result = {}
    for symbol, type_data in symbol_data.items():
        symbol_result = {
            "last_updated": datetime.utcnow().isoformat()
        }

        all_dates = []

        # Calculate CALL premium
        call_data = type_data['call']
        if call_data['contracts'] > 0:
            call_net = call_data['sto_amount'] - call_data['btc_amount']
            call_per_contract = call_net / call_data['contracts']
            call_weekly = call_per_contract  # Already represents typical weekly premium

            symbol_result["call_premium_per_contract"] = round(call_weekly, 2)
            symbol_result["call_contracts"] = call_data['contracts']
            symbol_result["call_net_total"] = round(call_net, 2)
            all_dates.extend(call_data['dates'])

        # Calculate PUT premium
        put_data = type_data['put']
        if put_data['contracts'] > 0:
            put_net = put_data['sto_amount'] - put_data['btc_amount']
            put_per_contract = put_net / put_data['contracts']
            put_weekly = put_per_contract  # Already represents typical weekly premium

            symbol_result["put_premium_per_contract"] = round(put_weekly, 2)
            symbol_result["put_contracts"] = put_data['contracts']
            symbol_result["put_net_total"] = round(put_net, 2)
            all_dates.extend(put_data['dates'])

        # Only include symbols that have at least one option type with data
        if all_dates:
            symbol_result["date_range"] = f"{min(all_dates)} to {max(all_dates)}"

            # For backward compatibility, set premium_per_contract to call premium if available
            if "call_premium_per_contract" in symbol_result:
                symbol_result["premium_per_contract"] = symbol_result["call_premium_per_contract"]
            elif "put_premium_per_contract" in symbol_result:
                symbol_result["premium_per_contract"] = symbol_result["put_premium_per_contract"]

            result[symbol] = symbol_result

    return result


def update_premium_settings_from_averages(
    db: Session,
    weeks: int = 4,
    min_contracts: int = 1
) -> Dict[str, Any]:
    """
    Auto-update premium settings based on 4-week NET premium calculation.

    Updates both CALL and PUT premiums separately for each symbol.

    Only updates symbols that:
    1. Have at least min_contracts sold in the last N weeks
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

    # Calculate averages with new algorithm (NET premium / contracts)
    averages = calculate_4_week_average_premiums(db, weeks)

    updated_count = 0
    skipped_count = 0
    details = {}

    for symbol, data in averages.items():
        # Check if there's enough data (at least min_contracts for either calls or puts)
        call_contracts = data.get('call_contracts', 0)
        put_contracts = data.get('put_contracts', 0)
        total_contracts = call_contracts + put_contracts

        if total_contracts < min_contracts:
            skipped_count += 1
            details[symbol] = {
                "status": "skipped",
                "reason": f"Insufficient data: {total_contracts} < {min_contracts} contracts"
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
                    "current_call_premium": float(setting.premium_per_contract) if setting.premium_per_contract else None,
                    "current_put_premium": float(setting.put_premium_per_contract) if setting.put_premium_per_contract else None
                }
                continue

            # Update if auto-update is enabled
            if setting.is_auto_updated:
                old_call = float(setting.premium_per_contract) if setting.premium_per_contract else None
                old_put = float(setting.put_premium_per_contract) if setting.put_premium_per_contract else None

                # Update CALL premium if we have call data
                if 'call_premium_per_contract' in data:
                    setting.premium_per_contract = Decimal(str(data['call_premium_per_contract']))
                    setting.call_contracts_sold = data.get('call_contracts')
                    setting.call_net_total = Decimal(str(data.get('call_net_total', 0)))

                # Update PUT premium if we have put data
                if 'put_premium_per_contract' in data:
                    setting.put_premium_per_contract = Decimal(str(data['put_premium_per_contract']))
                    setting.put_contracts_sold = data.get('put_contracts')
                    setting.put_net_total = Decimal(str(data.get('put_net_total', 0)))

                setting.last_auto_update = datetime.utcnow()
                updated_count += 1
                details[symbol] = {
                    "status": "updated",
                    "old_call_premium": old_call,
                    "new_call_premium": data.get('call_premium_per_contract'),
                    "call_contracts": call_contracts,
                    "old_put_premium": old_put,
                    "new_put_premium": data.get('put_premium_per_contract'),
                    "put_contracts": put_contracts
                }
            else:
                skipped_count += 1
                details[symbol] = {
                    "status": "skipped",
                    "reason": "Auto-update disabled"
                }
        else:
            # Create new setting with auto-update enabled
            setting = OptionPremiumSetting(
                symbol=symbol,
                premium_per_contract=Decimal(str(data['call_premium_per_contract'])) if 'call_premium_per_contract' in data else None,
                call_contracts_sold=data.get('call_contracts'),
                call_net_total=Decimal(str(data.get('call_net_total', 0))) if 'call_net_total' in data else None,
                put_premium_per_contract=Decimal(str(data['put_premium_per_contract'])) if 'put_premium_per_contract' in data else None,
                put_contracts_sold=data.get('put_contracts'),
                put_net_total=Decimal(str(data.get('put_net_total', 0))) if 'put_net_total' in data else None,
                is_auto_updated=True,
                last_auto_update=datetime.utcnow(),
                manual_override=False
            )
            db.add(setting)
            updated_count += 1
            details[symbol] = {
                "status": "created",
                "call_premium": data.get('call_premium_per_contract'),
                "call_contracts": call_contracts,
                "put_premium": data.get('put_premium_per_contract'),
                "put_contracts": put_contracts
            }

    db.flush()

    return {
        "updated": updated_count,
        "skipped": skipped_count,
        "total_symbols": len(averages),
        "details": details
    }

