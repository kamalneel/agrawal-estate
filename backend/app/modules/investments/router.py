"""
Investment Portfolio API routes.
Handles investment accounts, holdings, and transactions from Robinhood, Schwab, etc.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, datetime, timezone
from decimal import Decimal
from pydantic import BaseModel

from app.core.database import get_db
from app.modules.investments.services import (
    get_all_holdings,
    get_holdings_by_owner,
    get_holdings_summary,
    upsert_holding,
    delete_holding,
    bulk_import_holdings,
    get_or_create_account,
    calculate_cost_basis_from_transactions,
    recalculate_all_cost_bases,
)
from app.modules.investments.models import (
    InvestmentAccount,
    InvestmentHolding,
    InvestmentTransaction,
    PortfolioSnapshot,
)
from app.modules.investments.price_service import (
    get_price_changes, 
    update_holdings_with_live_prices,
    get_holdings_with_live_prices,
    get_live_prices_fast,
)

router = APIRouter()


# Pydantic models for request bodies
class HoldingCreate(BaseModel):
    """Request body for creating/updating a holding."""
    owner: str
    account_type: str
    symbol: str
    quantity: float
    cost_basis: Optional[float] = None
    current_price: Optional[float] = None
    description: Optional[str] = None


class HoldingBulkImport(BaseModel):
    """Request body for bulk importing holdings."""
    holdings: List[HoldingCreate]


class HoldingDelete(BaseModel):
    """Request body for deleting a holding."""
    owner: str
    account_type: str
    symbol: str


@router.get("/accounts")
async def list_investment_accounts(db: Session = Depends(get_db)):
    """List all investment accounts (Robinhood, Schwab, etc.).
    
    Uses the same logic and sorting as get_all_holdings() for consistency.
    """
    from app.modules.investments.models import PortfolioSnapshot
    from app.modules.investments.services import get_account_sort_key
    
    accounts = db.query(InvestmentAccount).filter(
        InvestmentAccount.is_active == 'Y'
    ).all()
    
    result = []
    for acc in accounts:
        # Get latest snapshot for last update timestamp
        # Use updated_at (DateTime) instead of statement_date (Date) to get exact time
        latest_snapshot = db.query(PortfolioSnapshot).filter(
            PortfolioSnapshot.account_id == acc.account_id
        ).order_by(PortfolioSnapshot.updated_at.desc()).first()
        
        last_updated = None
        if latest_snapshot:
            # Use updated_at for exact timestamp, fallback to statement_date if needed
            if latest_snapshot.updated_at:
                # Ensure UTC timezone is indicated with 'Z' suffix for JavaScript
                dt = latest_snapshot.updated_at
                if dt.tzinfo is None:
                    # If naive datetime, assume it's UTC and add 'Z'
                    last_updated = dt.isoformat() + 'Z'
                else:
                    # If timezone-aware, convert to UTC and add 'Z'
                    last_updated = dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
            elif latest_snapshot.statement_date:
                last_updated = latest_snapshot.statement_date.isoformat()
        
        # Use the same naming convention as get_all_holdings()
        # Parse owner from account_id for consistent naming
        parts = acc.account_id.split('_')
        owner = parts[0].title() if parts else 'Unknown'
        account_type = '_'.join(parts[1:]) if len(parts) > 1 else 'brokerage'
        
        # Use account_name if available, otherwise generate same way as holdings endpoint
        account_name = acc.account_name or f"{owner}'s {account_type.title()}"
        
        result.append({
            "id": acc.id,
            "source": acc.source,
            "account_id": acc.account_id,
            "name": account_name,  # Use consistent naming
            "type": acc.account_type,
            "last_updated": last_updated,
        })
    
    # Sort using the same logic as get_all_holdings()
    result.sort(key=lambda x: get_account_sort_key(x['account_id']))
    
    return {"accounts": result}


@router.get("/accounts/{account_id}")
async def get_account_details(account_id: str, db: Session = Depends(get_db)):
    """Get details for a specific investment account."""
    # Try to find by account_id string first
    account = db.query(InvestmentAccount).filter(
        InvestmentAccount.account_id == account_id
    ).first()
    
    if not account:
        # Try by numeric id
        try:
            numeric_id = int(account_id)
            account = db.query(InvestmentAccount).filter(
                InvestmentAccount.id == numeric_id
            ).first()
        except ValueError:
            pass
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    holdings = db.query(InvestmentHolding).filter(
        InvestmentHolding.account_id == account.account_id,
        InvestmentHolding.quantity > 0
    ).all()
    
    return {
        "account": {
            "id": account.id,
            "source": account.source,
            "account_id": account.account_id,
            "name": account.account_name,
            "type": account.account_type,
        },
        "holdings": [
            {
                "symbol": h.symbol,
                "quantity": float(h.quantity) if h.quantity else 0,
                "cost_basis": float(h.cost_basis) if h.cost_basis else None,
                "current_price": float(h.current_price) if h.current_price else None,
                "market_value": float(h.market_value) if h.market_value else None,
            }
            for h in holdings
        ],
    }


@router.get("/holdings")
async def list_all_holdings(
    db: Session = Depends(get_db),
    owner: Optional[str] = None,
):
    """
    List all holdings across accounts.
    Returns holdings grouped by account with portfolio percentages.
    """
    if owner:
        accounts = get_holdings_by_owner(db, owner)
    else:
        accounts = get_all_holdings(db)
    
    total_value = sum(acc['value'] for acc in accounts)
    
    return {
        "accounts": accounts,
        "total_value": total_value,
    }


@router.get("/holdings/live")
async def get_holdings_live(db: Session = Depends(get_db)):
    """
    Get all holdings with LIVE prices from Yahoo Finance.
    
    This endpoint:
    - Fetches current prices from Yahoo Finance API
    - Calculates market values using: shares × live_price
    - Includes cash balances from portfolio snapshots
    - Returns price source indicator (live vs cached)
    
    Returns holdings grouped by account with live valuations.
    """
    return get_holdings_with_live_prices(db)


@router.get("/option-income")
async def get_option_income(db: Session = Depends(get_db)):
    """
    Get net option income (STO - BTC) grouped by symbol for covered calls,
    and total put income separately. Also returns total cash balances.
    """
    from sqlalchemy import text
    from datetime import date

    # Net covered call income per symbol (aggregated)
    call_rows = db.execute(text(
        "SELECT symbol, SUM(amount) as net_income "
        "FROM investment_transactions "
        "WHERE transaction_type IN ('STO', 'BTC') "
        "AND description ILIKE '%Call%' "
        "GROUP BY symbol "
        "ORDER BY net_income DESC"
    )).fetchall()

    call_income = {row[0]: float(row[1]) for row in call_rows}

    # Net covered call income per account per symbol
    acct_call_rows = db.execute(text(
        "SELECT account_id, symbol, SUM(amount) as net_income "
        "FROM investment_transactions "
        "WHERE transaction_type IN ('STO', 'BTC') "
        "AND description ILIKE '%Call%' "
        "GROUP BY account_id, symbol"
    )).fetchall()

    call_income_by_account: dict = {}
    for row in acct_call_rows:
        acct = row[0]
        if acct not in call_income_by_account:
            call_income_by_account[acct] = {}
        call_income_by_account[acct][row[1]] = float(row[2])

    # Total put income
    put_row = db.execute(text(
        "SELECT COALESCE(SUM(amount), 0) "
        "FROM investment_transactions "
        "WHERE transaction_type IN ('STO', 'BTC') "
        "AND description ILIKE '%Put%'"
    )).fetchone()
    put_income = float(put_row[0]) if put_row else 0.0

    # Total cash balances
    cash_rows = db.execute(text(
        "SELECT COALESCE(SUM(cash_balance), 0) FROM account_cash_balances"
    )).fetchone()
    total_cash = float(cash_rows[0]) if cash_rows else 0.0

    # 4-week income: last 4 completed Mon-Fri business weeks
    from datetime import timedelta

    today = date.today()
    weekday = today.weekday()  # 0=Mon ... 4=Fri, 5=Sat, 6=Sun

    if weekday >= 5:
        # Saturday/Sunday: most recent completed week ended this Friday
        end_friday = today - timedelta(days=weekday - 4)
    else:
        # Monday-Friday: we're mid-week, last completed week ended prev Friday
        end_friday = today - timedelta(days=weekday + 3)

    # 4 complete weeks: Monday of oldest week to Friday of newest week
    start_monday = end_friday - timedelta(days=25)

    params = {'start': start_monday.isoformat(), 'end': end_friday.isoformat()}

    # 4-week call income per symbol
    weekly_call_rows = db.execute(text(
        "SELECT symbol, SUM(amount) as net_income "
        "FROM investment_transactions "
        "WHERE transaction_type IN ('STO', 'BTC') "
        "AND description ILIKE '%Call%' "
        "AND transaction_date >= :start AND transaction_date <= :end "
        "GROUP BY symbol"
    ), params).fetchall()

    monthly_call_income = {row[0]: float(row[1]) for row in weekly_call_rows}

    # 4-week put income total
    weekly_put_row = db.execute(text(
        "SELECT COALESCE(SUM(amount), 0) "
        "FROM investment_transactions "
        "WHERE transaction_type IN ('STO', 'BTC') "
        "AND description ILIKE '%Put%' "
        "AND transaction_date >= :start AND transaction_date <= :end"
    ), params).fetchone()
    monthly_put_income = float(weekly_put_row[0]) if weekly_put_row else 0.0

    # 4-week call income per account per symbol
    weekly_acct_rows = db.execute(text(
        "SELECT account_id, symbol, SUM(amount) as net_income "
        "FROM investment_transactions "
        "WHERE transaction_type IN ('STO', 'BTC') "
        "AND description ILIKE '%Call%' "
        "AND transaction_date >= :start AND transaction_date <= :end "
        "GROUP BY account_id, symbol"
    ), params).fetchall()

    monthly_call_by_account: dict = {}
    for row in weekly_acct_rows:
        acct = row[0]
        if acct not in monthly_call_by_account:
            monthly_call_by_account[acct] = {}
        monthly_call_by_account[acct][row[1]] = float(row[2])

    return {
        "callIncomeBySymbol": call_income,
        "callIncomeByAccount": call_income_by_account,
        "putIncomeTotal": put_income,
        "totalCash": total_cash,
        "monthlyCallBySymbol": monthly_call_income,
        "monthlyCallByAccount": monthly_call_by_account,
        "monthlyPutTotal": monthly_put_income,
        "fourWeekRange": f"{start_monday.isoformat()} to {end_friday.isoformat()}",
    }


@router.post("/holdings/refresh-prices")
async def refresh_all_prices(db: Session = Depends(get_db)):
    """
    Refresh all holdings with live prices from Yahoo Finance.
    
    This updates the database with current prices, which is useful for:
    - Ensuring stored prices are up-to-date
    - Background price updates
    
    Returns stats about the update operation.
    """
    stats = update_holdings_with_live_prices(db)
    return {
        "success": True,
        "stats": stats,
    }


@router.get("/holdings/summary")
async def get_summary(db: Session = Depends(get_db)):
    """Get a summary of all holdings."""
    return get_holdings_summary(db)


@router.post("/holdings")
async def create_or_update_holding(
    holding: HoldingCreate,
    db: Session = Depends(get_db)
):
    """Create or update a single holding position."""
    try:
        result = upsert_holding(
            db=db,
            owner=holding.owner,
            account_type=holding.account_type,
            symbol=holding.symbol,
            quantity=Decimal(str(holding.quantity)),
            cost_basis=Decimal(str(holding.cost_basis)) if holding.cost_basis else None,
            current_price=Decimal(str(holding.current_price)) if holding.current_price else None,
            description=holding.description,
        )
        db.commit()
        
        return {
            "success": True,
            "holding": {
                "symbol": result.symbol,
                "quantity": float(result.quantity),
                "account_id": result.account_id,
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/holdings/bulk")
async def bulk_import(
    data: HoldingBulkImport,
    db: Session = Depends(get_db)
):
    """Bulk import multiple holdings at once."""
    holdings_data = [
        {
            'owner': h.owner,
            'account_type': h.account_type,
            'symbol': h.symbol,
            'quantity': h.quantity,
            'cost_basis': h.cost_basis,
            'current_price': h.current_price,
            'description': h.description,
        }
        for h in data.holdings
    ]
    
    stats = bulk_import_holdings(db, holdings_data)
    
    return {
        "success": True,
        "stats": stats,
    }


@router.delete("/holdings")
async def remove_holding(
    holding: HoldingDelete,
    db: Session = Depends(get_db)
):
    """Delete a holding position."""
    deleted = delete_holding(
        db=db,
        owner=holding.owner,
        account_type=holding.account_type,
        symbol=holding.symbol,
    )
    db.commit()
    
    if deleted:
        return {"success": True, "message": f"Deleted {holding.symbol}"}
    else:
        raise HTTPException(status_code=404, detail="Holding not found")


@router.get("/transactions")
async def list_transactions(
    db: Session = Depends(get_db),
    account_id: Optional[str] = None,
    symbol: Optional[str] = None,
    transaction_type: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=100, le=500)
):
    """
    List investment transactions with filters.
    Transaction types: BUY, SELL, DIV, TRANSFER, SPLIT
    """
    query = db.query(InvestmentTransaction)
    
    if account_id:
        query = query.filter(InvestmentTransaction.account_id == account_id)
    if symbol:
        query = query.filter(InvestmentTransaction.symbol == symbol.upper())
    if transaction_type:
        query = query.filter(InvestmentTransaction.transaction_type == transaction_type.upper())
    if start_date:
        query = query.filter(InvestmentTransaction.transaction_date >= start_date)
    if end_date:
        query = query.filter(InvestmentTransaction.transaction_date <= end_date)
    
    transactions = query.order_by(
        InvestmentTransaction.transaction_date.desc()
    ).limit(limit).all()
    
    return {
        "transactions": [
            {
                "id": t.id,
                "date": t.transaction_date.isoformat() if t.transaction_date else None,
                "type": t.transaction_type,
                "symbol": t.symbol,
                "quantity": float(t.quantity) if t.quantity else None,
                "amount": float(t.amount) if t.amount else None,
                "price_per_share": float(t.price_per_share) if t.price_per_share else None,
            }
            for t in transactions
        ],
        "total": len(transactions)
    }


@router.post("/snapshot/daily")
async def trigger_daily_snapshot(db: Session = Depends(get_db)):
    """
    Manually trigger a daily portfolio snapshot.

    Takes a snapshot of all holdings with current prices and writes to
    portfolio_snapshots and investment_holdings_history tables.
    Idempotent via upsert — safe to call multiple times per day.
    """
    from app.modules.investments.snapshot_service import take_daily_snapshot

    stats = take_daily_snapshot(db)
    return {
        "success": True,
        "message": f"Snapshot complete: {stats['accounts_snapshot']} accounts, "
                   f"{stats['holdings_snapshot']} holdings",
        "stats": stats,
    }


@router.get("/capital-events")
async def get_capital_events(
    db: Session = Depends(get_db),
    period: Optional[str] = Query(None, description="Time period: 30d, 90d, ytd, 1y, 2y, 5y, or omit for all"),
    min_amount: float = Query(5000, description="Minimum absolute amount to include"),
):
    """
    Get BUY/SELL capital events for chart overlay and transaction table.
    Returns individual events and monthly summaries.
    """
    from sqlalchemy import func
    from datetime import timedelta
    from collections import defaultdict

    # Calculate cutoff date based on period
    filters = [InvestmentTransaction.transaction_type.in_(['BUY', 'SELL'])]
    if period:
        today = date.today()
        period_days = {'1d': 1, '1w': 7, '30d': 30, '90d': 90, '1y': 365, '2y': 730, '5y': 1825}
        if period == 'ytd':
            cutoff = date(today.year, 1, 1)
        elif period in period_days:
            cutoff = today - timedelta(days=period_days[period])
        else:
            cutoff = None
        if cutoff:
            filters.append(InvestmentTransaction.transaction_date >= cutoff)

    if min_amount > 0:
        filters.append(
            func.abs(InvestmentTransaction.amount) >= min_amount
        )

    # Query transactions joined with accounts for account_name
    rows = db.query(
        InvestmentTransaction,
        InvestmentAccount.account_name,
    ).outerjoin(
        InvestmentAccount,
        InvestmentTransaction.account_id == InvestmentAccount.account_id,
    ).filter(*filters).order_by(
        InvestmentTransaction.transaction_date.desc()
    ).all()

    events = []
    for txn, account_name in rows:
        d = txn.transaction_date
        amt = float(txn.amount) if txn.amount else 0
        events.append({
            "date": d.isoformat(),
            "formatted": d.strftime("%b %d, %Y"),
            "month_key": d.strftime("%b %Y"),
            "date_key": d.isoformat(),
            "type": txn.transaction_type,
            "symbol": txn.symbol,
            "quantity": float(txn.quantity) if txn.quantity else None,
            "amount": abs(amt),
            "price_per_share": float(txn.price_per_share) if txn.price_per_share else None,
            "account_id": txn.account_id,
            "account_name": account_name or txn.account_id,
            "description": txn.description or "",
        })

    # Build monthly summary
    monthly = defaultdict(lambda: {
        "total_buys": 0, "total_sells": 0, "buy_count": 0, "sell_count": 0,
        "buy_symbols": [], "sell_symbols": [],
    })
    for e in events:
        mk = e["month_key"]
        if e["type"] == "BUY":
            monthly[mk]["total_buys"] += e["amount"]
            monthly[mk]["buy_count"] += 1
            if e["symbol"] not in monthly[mk]["buy_symbols"]:
                monthly[mk]["buy_symbols"].append(e["symbol"])
        else:
            monthly[mk]["total_sells"] += e["amount"]
            monthly[mk]["sell_count"] += 1
            if e["symbol"] not in monthly[mk]["sell_symbols"]:
                monthly[mk]["sell_symbols"].append(e["symbol"])

    monthly_summary = []
    for month, data in monthly.items():
        monthly_summary.append({
            "month": month,
            "total_buys": round(data["total_buys"], 2),
            "total_sells": round(data["total_sells"], 2),
            "net_flow": round(data["total_buys"] - data["total_sells"], 2),
            "buy_count": data["buy_count"],
            "sell_count": data["sell_count"],
            "top_buys": ", ".join(data["buy_symbols"][:3]),
            "top_sells": ", ".join(data["sell_symbols"][:3]),
        })

    return {
        "events": events,
        "monthly_summary": monthly_summary,
    }


import re

OPTION_RE = re.compile(r'(Put|Call)\s+\$?([\d,.]+)')


def _parse_option_type_strike(desc: str):
    """Parse option type (Put/Call) and strike price from option description."""
    m = OPTION_RE.search(desc or '')
    return (m.group(1), float(m.group(2).replace(',', ''))) if m else (None, None)


@router.get("/capital-events/option-chains")
async def get_option_chains(
    db: Session = Depends(get_db),
    period: Optional[str] = Query(None, description="Time period: 30d, 90d, ytd, 1y, 2y, 5y, or omit for all"),
    min_amount: float = Query(5000, description="Minimum absolute amount to include"),
):
    """
    Get option chain analysis for forced capital events (put/call assignments).
    Returns net premium earned, roll count, and full trade history for each chain.
    """
    from sqlalchemy import text, func
    from datetime import timedelta

    # 1. Get BUY/SELL events matching filters (same as capital-events)
    filters = [InvestmentTransaction.transaction_type.in_(['BUY', 'SELL'])]
    if period:
        today = date.today()
        period_days = {'1d': 1, '1w': 7, '30d': 30, '90d': 90, '1y': 365, '2y': 730, '5y': 1825}
        if period == 'ytd':
            cutoff = date(today.year, 1, 1)
        elif period in period_days:
            cutoff = today - timedelta(days=period_days[period])
        else:
            cutoff = None
        if cutoff:
            filters.append(InvestmentTransaction.transaction_date >= cutoff)

    if min_amount > 0:
        filters.append(func.abs(InvestmentTransaction.amount) >= min_amount)

    rows = db.query(InvestmentTransaction).filter(*filters).order_by(
        InvestmentTransaction.transaction_date.desc()
    ).all()

    option_chains = {}

    for txn in rows:
        desc = txn.description or ""
        # Check if this is a forced (option-assigned) transaction
        if 'option' not in desc.lower() or 'assigned' not in desc.lower():
            continue

        d = txn.transaction_date
        key = f"{d.isoformat()}|{txn.symbol}|{txn.account_id}|{txn.transaction_type}"

        # 2. Find OASGN record to get assignment details
        oasgn = db.query(InvestmentTransaction).filter(
            InvestmentTransaction.account_id == txn.account_id,
            InvestmentTransaction.symbol == txn.symbol,
            InvestmentTransaction.transaction_type == 'OASGN',
            InvestmentTransaction.transaction_date.between(
                d - timedelta(days=1), d + timedelta(days=1)
            ),
        ).first()

        if oasgn:
            oasgn_desc = oasgn.description or ""
            option_type, final_strike = _parse_option_type_strike(oasgn_desc)
            if not option_type:
                continue
            contracts = abs(int(oasgn.quantity)) if oasgn.quantity else 1
        else:
            # Fallback: infer from the BUY/SELL transaction itself
            # SELL = call assignment, BUY = put assignment
            option_type = "Call" if txn.transaction_type == "SELL" else "Put"
            # Parse contract count from description: "3 PLTR Options Assigned"
            contract_match = re.search(r'(\d+)\s+\w+\s+Options?\s+Assigned', desc, re.IGNORECASE)
            contracts = int(contract_match.group(1)) if contract_match else 1
            # final_strike will be determined from nearby STO/BTC trades
            final_strike = None

        # 3. Get all STO/BTC for this symbol+account, filter by option type
        sto_btc = db.query(InvestmentTransaction).filter(
            InvestmentTransaction.account_id == txn.account_id,
            InvestmentTransaction.symbol == txn.symbol,
            InvestmentTransaction.transaction_type.in_(['STO', 'BTC']),
            InvestmentTransaction.description.ilike(f'%{option_type}%'),
        ).order_by(InvestmentTransaction.transaction_date.asc()).all()

        # 4. Filter by contract count to separate chains with different sizes
        #    (e.g., RKLB $80 with 5 contracts vs RKLB $84 with 3 contracts)
        chain_trades = []
        for t in sto_btc:
            t_desc = t.description or ""
            t_type, t_strike = _parse_option_type_strike(t_desc)
            if t_type != option_type:
                continue
            t_contracts = abs(int(t.quantity)) if t.quantity else 1
            # Only include trades with matching contract count
            if t_contracts != contracts:
                continue
            # Only include trades before/on the assignment date
            if t.transaction_date > d:
                continue
            chain_trades.append(t)

        if not chain_trades:
            continue

        # If final_strike unknown (no OASGN), infer from the last STO expiring near assignment
        if final_strike is None and chain_trades:
            # Find the STO closest to assignment date (the final position)
            last_sto = None
            for t in reversed(chain_trades):
                if t.transaction_type == 'STO':
                    last_sto = t
                    break
            if last_sto:
                _, final_strike = _parse_option_type_strike(last_sto.description or "")
            if final_strike is None:
                final_strike = 0

        # 5. Trace chain backward from final strike
        # Build the chain by following BTC→STO date pairs
        filtered_trades = []
        current_strikes = {final_strike}

        # Work backward through trades
        for t in reversed(chain_trades):
            t_desc = t.description or ""
            _, t_strike = _parse_option_type_strike(t_desc)
            if t_strike is None:
                continue

            if t.transaction_type == 'BTC':
                # BTC closes a position at this strike
                if t_strike in current_strikes:
                    filtered_trades.append(t)
                    # After closing, we need to find the STO that opened it
                    # The STO could be at a different strike (if rolled)
            elif t.transaction_type == 'STO':
                # STO opens a position
                # Check if a BTC for this strike's successor is already in the chain
                # or if this is the original/rolled position
                filtered_trades.append(t)
                current_strikes.add(t_strike)

        # If chain tracing didn't reduce much, just use all matching trades
        # (the contract count filter already provides good separation)
        trades_to_use = chain_trades

        # 6. Compute chain metrics
        net_premium = sum(float(t.amount) for t in trades_to_use if t.amount)
        sto_trades = [t for t in trades_to_use if t.transaction_type == 'STO']
        btc_trades = [t for t in trades_to_use if t.transaction_type == 'BTC']
        rolls_count = len(btc_trades)

        first_date = trades_to_use[0].transaction_date if trades_to_use else d
        _, starting_strike = _parse_option_type_strike(
            sto_trades[0].description if sto_trades else ""
        )
        duration_days = (d - first_date).days if first_date else 0

        # Build trades list
        trades_list = []
        for t in trades_to_use:
            t_desc = t.description or ""
            _, t_strike = _parse_option_type_strike(t_desc)
            # Extract expiry from description (format: "SYMBOL M/D/YYYY Put/Call $XXX")
            expiry_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', t_desc)
            expiry = expiry_match.group(1) if expiry_match else ""
            t_contracts = abs(int(t.quantity)) if t.quantity else 1
            trades_list.append({
                "date": t.transaction_date.isoformat(),
                "formatted": t.transaction_date.strftime("%b %d, %Y"),
                "type": t.transaction_type,
                "strike": t_strike,
                "expiry": expiry,
                "amount": round(float(t.amount), 2) if t.amount else 0,
                "contracts": t_contracts,
            })

        option_chains[key] = {
            "is_forced": True,
            "option_type": option_type.lower(),
            "net_premium": round(net_premium, 2),
            "rolls": rolls_count,
            "chain_start_date": first_date.isoformat() if first_date else None,
            "starting_strike": starting_strike,
            "final_strike": final_strike,
            "duration_days": duration_days,
            "contracts": contracts,
            "trades": trades_list,
        }

    return {"option_chains": option_chains}


@router.get("/portfolio-history")
async def get_portfolio_history(
    db: Session = Depends(get_db),
    owner: Optional[str] = None,
    account_id: Optional[str] = None,
    period: Optional[str] = Query(None, description="Time period: 1d, 1w, 30d, 90d, or omit for all"),
):
    """
    Get historical portfolio values from statement snapshots.
    For monthly ('all') view: takes the latest snapshot per account per month,
    then sums across accounts. This ensures every account is represented even
    when they don't all have snapshots on the same calendar date.
    For period views (1d, 1w, 30d, 90d): sums across accounts per date.
    """
    from sqlalchemy import func, and_
    from datetime import timedelta

    # Only include snapshots from active, known accounts
    active_account_ids = {
        a.account_id for a in db.query(InvestmentAccount.account_id).filter(
            InvestmentAccount.is_active == 'Y'
        ).all()
    }

    # Build base filters
    filters = [PortfolioSnapshot.account_id.in_(active_account_ids)]
    if account_id:
        filters.append(PortfolioSnapshot.account_id == account_id)
    elif owner:
        filters.append(PortfolioSnapshot.owner == owner)

    # Calculate cutoff date based on period
    if period:
        today = date.today()
        period_days = {'1d': 1, '1w': 7, '30d': 30, '90d': 90, '1y': 365, '2y': 730, '5y': 1825}
        if period == 'ytd':
            cutoff = date(today.year, 1, 1)
        elif period in period_days:
            cutoff = today - timedelta(days=period_days[period])
        else:
            cutoff = None
        if cutoff:
            filters.append(PortfolioSnapshot.statement_date >= cutoff)

    # Short periods (1d, 1w, 30d, 90d): daily data points
    # Longer periods (ytd, 1y, 2y, 5y, all): monthly aggregation using
    # latest snapshot per account per month to avoid missing-account gaps
    use_daily = period in ('1d', '1w', '30d', '90d')

    if not use_daily:
        # Monthly aggregation: latest snapshot per account per month, then sum
        latest_dates_q = db.query(
            PortfolioSnapshot.account_id,
            PortfolioSnapshot.source,
            func.to_char(PortfolioSnapshot.statement_date, 'YYYY-MM').label('month'),
            func.max(PortfolioSnapshot.statement_date).label('max_date'),
        )
        for f in filters:
            latest_dates_q = latest_dates_q.filter(f)
        latest_dates = latest_dates_q.group_by(
            PortfolioSnapshot.account_id,
            PortfolioSnapshot.source,
            func.to_char(PortfolioSnapshot.statement_date, 'YYYY-MM'),
        ).subquery()

        rows = db.query(
            latest_dates.c.month,
            PortfolioSnapshot.portfolio_value,
        ).join(
            latest_dates,
            and_(
                PortfolioSnapshot.account_id == latest_dates.c.account_id,
                PortfolioSnapshot.source == latest_dates.c.source,
                PortfolioSnapshot.statement_date == latest_dates.c.max_date,
            )
        ).order_by(latest_dates.c.month).all()

        monthly: dict = {}
        for r in rows:
            monthly[r.month] = monthly.get(r.month, 0) + float(r.portfolio_value)

        history = [
            {
                "month": k,
                "value": round(v, 2),
                "formatted": datetime.strptime(k, "%Y-%m").strftime("%b %Y"),
            }
            for k, v in sorted(monthly.items())
        ]
    else:
        # Daily view for short periods
        query = db.query(
            PortfolioSnapshot.statement_date,
            func.sum(PortfolioSnapshot.portfolio_value).label('total_value')
        )
        for f in filters:
            query = query.filter(f)
        query = query.group_by(
            PortfolioSnapshot.statement_date
        ).order_by(PortfolioSnapshot.statement_date)

        snapshots = query.all()
        history = []
        for snapshot in snapshots:
            d = snapshot.statement_date
            history.append({
                "month": d.strftime("%Y-%m-%d"),
                "value": round(float(snapshot.total_value), 2),
                "formatted": d.strftime("%b %d, %Y"),
            })

    return {
        "history": history,
        "total_snapshots": len(history),
    }


@router.get("/performance")
async def get_portfolio_performance(
    db: Session = Depends(get_db),
    period: str = Query(default="1Y", pattern="^(1M|3M|6M|1Y|3Y|5Y|ALL)$")
):
    """Get portfolio performance over specified period."""
    summary = get_holdings_summary(db)
    
    # Get history for performance calculation
    from sqlalchemy import func
    snapshots = db.query(
        PortfolioSnapshot.statement_date,
        func.sum(PortfolioSnapshot.portfolio_value).label('total_value')
    ).group_by(PortfolioSnapshot.statement_date).order_by(PortfolioSnapshot.statement_date).all()
    
    history = [
        {"date": s.statement_date.isoformat(), "value": float(s.total_value)}
        for s in snapshots
    ]
    
    start_value = history[0]["value"] if history else 0
    end_value = history[-1]["value"] if history else summary['totalValue']
    gain_loss = end_value - start_value
    gain_loss_percent = (gain_loss / start_value * 100) if start_value > 0 else 0
    
    return {
        "period": period,
        "start_value": start_value,
        "end_value": end_value,
        "gain_loss": gain_loss,
        "gain_loss_percent": round(gain_loss_percent, 2),
        "history": history
    }


@router.get("/growth-summary")
async def get_growth_summary(db: Session = Depends(get_db)):
    """
    Get portfolio growth over multiple time periods (30 days, 90 days, 1 year).
    Uses monthly portfolio snapshots to calculate returns.
    """
    from datetime import date, timedelta
    from sqlalchemy import func, and_
    
    # Get current portfolio value from holdings
    summary = get_holdings_summary(db)
    current_value = summary.get('totalValue', 0)
    
    # Get all monthly snapshots, ordered by date
    snapshots = db.query(
        PortfolioSnapshot.statement_date,
        func.sum(PortfolioSnapshot.portfolio_value).label('total_value')
    ).group_by(PortfolioSnapshot.statement_date).order_by(PortfolioSnapshot.statement_date.desc()).all()
    
    if not snapshots:
        return {
            "current_value": current_value,
            "periods": {}
        }
    
    today = date.today()
    periods = {}
    
    # Define time periods: 1D (yesterday), YTD (Jan 1), 1Y
    period_configs = [
        ("1d", 1, "1 Day"),
        ("ytd", None, "YTD"),
        ("1y", 365, "1 Year"),
    ]

    for period_key, days, label in period_configs:
        if period_key == 'ytd':
            target_date = date(today.year, 1, 1)
        else:
            target_date = today - timedelta(days=days)

        # Find the closest snapshot to the target date
        closest_snapshot = None
        min_diff = float('inf')

        for s in snapshots:
            diff = abs((target_date - s.statement_date).days)
            # For 1D, find closest snapshot (could be today or yesterday)
            # For others, find snapshot on or before target date
            if period_key == '1d':
                if diff < min_diff:
                    min_diff = diff
                    closest_snapshot = s
            else:
                back_diff = (target_date - s.statement_date).days
                if back_diff >= 0 and back_diff < min_diff:
                    min_diff = back_diff
                    closest_snapshot = s

        if closest_snapshot:
            past_value = float(closest_snapshot.total_value)
            change = current_value - past_value
            change_percent = (change / past_value * 100) if past_value > 0 else 0

            periods[period_key] = {
                "label": label,
                "past_value": round(past_value, 2),
                "current_value": round(current_value, 2),
                "change": round(change, 2),
                "change_percent": round(change_percent, 2),
                "snapshot_date": closest_snapshot.statement_date.isoformat(),
            }
    
    return {
        "current_value": current_value,
        "periods": periods
    }


@router.get("/allocation")
async def get_asset_allocation(db: Session = Depends(get_db)):
    """Get current asset allocation breakdown."""
    summary = get_holdings_summary(db)
    
    return {
        "by_asset_class": {},
        "by_sector": {},
        "by_account": summary.get('byType', {}),
        "by_owner": summary.get('byOwner', {}),
    }


@router.get("/dividends")
async def get_dividend_summary(
    db: Session = Depends(get_db),
    year: Optional[int] = None
):
    """Get dividend income summary."""
    query = db.query(InvestmentTransaction).filter(
        InvestmentTransaction.transaction_type == 'DIVIDEND'
    )
    
    if year:
        from sqlalchemy import extract
        query = query.filter(
            extract('year', InvestmentTransaction.transaction_date) == year
        )
    
    dividends = query.all()
    
    total = sum(float(d.amount) if d.amount else 0 for d in dividends)
    
    # Group by symbol
    by_symbol = {}
    for d in dividends:
        sym = d.symbol or 'UNKNOWN'
        if sym not in by_symbol:
            by_symbol[sym] = 0
        by_symbol[sym] += float(d.amount) if d.amount else 0
    
    return {
        "total": total,
        "by_symbol": [{"symbol": k, "amount": v} for k, v in sorted(by_symbol.items(), key=lambda x: -x[1])],
        "by_month": []
    }


@router.get("/price-changes")
async def get_holdings_price_changes(
    db: Session = Depends(get_db),
    account_id: Optional[str] = None,
):
    """
    Get price changes (1-day, 30-day, 90-day) for all holdings or holdings in a specific account.
    Fetches real-time data from Yahoo Finance.
    """
    # Get holdings
    query = db.query(InvestmentHolding).filter(InvestmentHolding.quantity > 0)
    
    if account_id:
        query = query.filter(InvestmentHolding.account_id == account_id)
    
    holdings = query.all()
    
    # Get unique symbols
    symbols = list(set(h.symbol for h in holdings if h.symbol))
    
    # Fetch price changes
    price_data = get_price_changes(symbols)
    
    # Combine with holdings
    result = []
    for h in holdings:
        prices = price_data.get(h.symbol, {})
        result.append({
            "symbol": h.symbol,
            "account_id": h.account_id,
            "quantity": float(h.quantity) if h.quantity else 0,
            "current_price": prices.get("current_price"),
            "change_1d": prices.get("change_1d"),
            "change_30d": prices.get("change_30d"),
            "change_90d": prices.get("change_90d"),
            "change_1d_value": prices.get("change_1d_value"),
            "change_30d_value": prices.get("change_30d_value"),
            "change_90d_value": prices.get("change_90d_value"),
        })
    
    return {
        "holdings": result,
        "price_data": price_data,
    }


# Note: The /holdings/parse-text endpoint has been removed.
# Use the unified parser at /api/v1/ingestion/robinhood-paste/save instead.


@router.post("/update-prices")
async def update_all_prices(db: Session = Depends(get_db)):
    """
    Update all holdings with current prices from Yahoo Finance.
    
    This endpoint fetches live prices for all stock symbols in the database
    and updates the current_price and market_value fields.
    
    Returns:
        - symbols_fetched: Number of symbols we got prices for
        - holdings_updated: Number of holdings updated
        - holdings_skipped: Number of holdings skipped (no price data)
        - total_value_before: Total portfolio value before update
        - total_value_after: Total portfolio value after update
        - price_updates: Details of each price change by symbol
    """
    stats = update_holdings_with_live_prices(db)
    
    return {
        "success": True,
        "message": f"Updated {stats['holdings_updated']} holdings with live Yahoo Finance prices",
        "stats": stats,
    }


@router.get("/update-prices")
async def get_price_update_preview(db: Session = Depends(get_db)):
    """
    Preview what prices would be updated (without actually updating).
    
    Useful for seeing how much prices have changed since last update.
    """
    from app.modules.investments.models import InvestmentHolding
    
    # Get all holdings
    holdings = db.query(InvestmentHolding).filter(
        InvestmentHolding.quantity > 0
    ).all()
    
    if not holdings:
        return {"holdings": [], "symbols": []}
    
    # Get unique symbols
    symbols = list(set(
        h.symbol for h in holdings 
        if h.symbol and h.symbol != 'CASH'
    ))
    
    # Fetch current prices
    price_data = get_price_changes(symbols)
    
    # Build preview
    preview = []
    total_current_value = 0
    total_live_value = 0
    
    for holding in holdings:
        if holding.symbol == 'CASH':
            continue
            
        current_price_db = float(holding.current_price) if holding.current_price else 0
        current_value_db = float(holding.market_value) if holding.market_value else 0
        quantity = float(holding.quantity) if holding.quantity else 0
        
        live_price = price_data.get(holding.symbol, {}).get("current_price", 0) or 0
        live_value = quantity * live_price
        
        total_current_value += current_value_db
        total_live_value += live_value
        
        if live_price > 0:
            preview.append({
                "symbol": holding.symbol,
                "account_id": holding.account_id,
                "quantity": quantity,
                "stored_price": current_price_db,
                "live_price": live_price,
                "price_change": round(live_price - current_price_db, 2),
                "price_change_pct": round((live_price - current_price_db) / current_price_db * 100, 2) if current_price_db > 0 else 0,
                "stored_value": current_value_db,
                "live_value": round(live_value, 2),
                "value_change": round(live_value - current_value_db, 2),
            })
    
    return {
        "preview": sorted(preview, key=lambda x: abs(x["value_change"]), reverse=True),
        "summary": {
            "total_stored_value": round(total_current_value, 2),
            "total_live_value": round(total_live_value, 2),
            "total_change": round(total_live_value - total_current_value, 2),
            "total_change_pct": round((total_live_value - total_current_value) / total_current_value * 100, 2) if total_current_value > 0 else 0,
            "symbols_count": len(symbols),
            "holdings_count": len(preview),
        }
    }


@router.post("/holdings/recalculate-cost-basis")
async def recalculate_cost_basis(
    db: Session = Depends(get_db),
    source: Optional[str] = None,
    account_id: Optional[str] = None,
    symbol: Optional[str] = None,
):
    """
    Recalculate cost basis for holdings from transaction history.
    
    Uses weighted average method to calculate cost basis from all BUY and SELL transactions.
    This will update the cost_basis field in InvestmentHolding records.
    
    Args:
        source: Optional - Filter by source (e.g., 'robinhood')
        account_id: Optional - Calculate for specific account only
        symbol: Optional - Calculate for specific symbol only (requires account_id)
    
    Returns:
        Stats about the recalculation operation
    """
    if symbol and not account_id:
        raise HTTPException(
            status_code=400,
            detail="account_id is required when symbol is specified"
        )
    
    if account_id and symbol:
        # Calculate for a single holding
        calculated = calculate_cost_basis_from_transactions(
            db=db,
            account_id=account_id,
            symbol=symbol,
            source=source
        )
        
        if calculated is None:
            return {
                "success": False,
                "message": f"No transactions found for {symbol} in {account_id}",
                "calculated_cost_basis": None
            }
        
        # Update the holding
        holding = db.query(InvestmentHolding).filter(
            InvestmentHolding.account_id == account_id,
            InvestmentHolding.symbol == symbol.upper()
        ).first()
        
        if holding:
            old_cost_basis = float(holding.cost_basis) if holding.cost_basis else None
            holding.cost_basis = calculated
            db.commit()
            
            return {
                "success": True,
                "message": f"Updated cost basis for {symbol} in {account_id}",
                "old_cost_basis": old_cost_basis,
                "new_cost_basis": float(calculated),
                "quantity": float(holding.quantity) if holding.quantity else 0,
                "avg_cost_per_share": float(calculated / holding.quantity) if holding.quantity and holding.quantity > 0 else None
            }
        else:
            return {
                "success": False,
                "message": f"Holding not found for {symbol} in {account_id}",
                "calculated_cost_basis": float(calculated)
            }
    
    # Recalculate all holdings
    stats = recalculate_all_cost_bases(db=db, source=source)
    
    return {
        "success": True,
        "message": "Cost basis recalculation completed",
        "stats": stats
    }


@router.get("/stock-growth")
def get_stock_growth(db: Session = Depends(get_db)):
    """1Y/5Y/YTD growth + holding period for all held symbols.

    Growth = synced live price vs. anchor closes from symbol_price_history
    (Robinhood MCP historicals, ingested via /ingestion/price-history) —
    per the market-data-source-order KB rule; the old yfinance path
    returned null for every symbol. Anchor = latest stored close on or
    before the target date (weekly bars ⇒ within a few days).
    """
    from sqlalchemy import func as sqlfunc, text as _text
    from datetime import timedelta

    # Get unique symbols with quantity > 0
    symbols_query = db.query(InvestmentHolding.symbol).filter(
        InvestmentHolding.quantity > 0,
        InvestmentHolding.symbol != 'CASH',
        InvestmentHolding.symbol.isnot(None),
    ).distinct().all()
    symbols = [row[0] for row in symbols_query if row[0]]

    if not symbols:
        return {}

    price_rows = db.query(
        InvestmentHolding.symbol,
        sqlfunc.max(InvestmentHolding.current_price),
    ).filter(InvestmentHolding.symbol.in_(symbols)).group_by(
        InvestmentHolding.symbol).all()
    current = {r[0]: float(r[1]) for r in price_rows if r[1]}

    today = date.today()
    anchors = {
        "growth_ytd": date(today.year - 1, 12, 31),
        "growth_1y": today - timedelta(days=365),
        "growth_5y": today - timedelta(days=365 * 5),
    }
    growth_data = {s: {} for s in symbols}
    for key, target in anchors.items():
        rows = db.execute(_text("""
            SELECT DISTINCT ON (symbol) symbol, close_price
            FROM symbol_price_history
            WHERE symbol = ANY(:syms) AND price_date <= :target
              AND price_date > :target - INTERVAL '21 days'
            ORDER BY symbol, price_date DESC
        """), {"syms": symbols, "target": target}).fetchall()
        for r in rows:
            base = float(r.close_price)
            now = current.get(r.symbol)
            if base and now:
                growth_data[r.symbol][key] = round((now - base) / base * 100, 2)

    # Get earliest purchase date per symbol from transactions
    earliest_dates = db.query(
        InvestmentTransaction.symbol,
        sqlfunc.min(InvestmentTransaction.transaction_date).label('earliest_date')
    ).filter(
        InvestmentTransaction.symbol.in_(symbols),
        InvestmentTransaction.transaction_type.in_(['BUY', 'REINVEST']),
    ).group_by(InvestmentTransaction.symbol).all()

    date_map = {row.symbol: row.earliest_date for row in earliest_dates}
    today = date.today()

    result = {}
    for symbol in symbols:
        entry = growth_data.get(symbol, {})
        earliest = date_map.get(symbol)
        holding_days = None
        if earliest:
            delta = today - (earliest.date() if hasattr(earliest, 'date') else earliest)
            holding_days = delta.days

        result[symbol] = {
            'growth_ytd': entry.get('growth_ytd'),
            'growth_1y': entry.get('growth_1y'),
            'growth_5y': entry.get('growth_5y'),
            'holding_period_days': holding_days,
        }

    return result


@router.get("/holdings/{account_id}/{symbol}/cost-basis")
async def get_cost_basis_calculation(
    account_id: str,
    symbol: str,
    db: Session = Depends(get_db),
    source: Optional[str] = None,
):
    """
    Calculate and return cost basis for a specific holding without updating it.
    
    Useful for previewing what the cost basis would be based on transaction history.
    
    Returns:
        Calculated cost basis and details about the calculation
    """
    from app.modules.investments.models import InvestmentTransaction
    
    calculated = calculate_cost_basis_from_transactions(
        db=db,
        account_id=account_id,
        symbol=symbol,
        source=source
    )
    
    # Get the holding to show current cost basis
    holding = db.query(InvestmentHolding).filter(
        InvestmentHolding.account_id == account_id,
        InvestmentHolding.symbol == symbol.upper()
    ).first()
    
    # Get transaction count for context
    query = db.query(InvestmentTransaction).filter(
        InvestmentTransaction.account_id == account_id,
        InvestmentTransaction.symbol == symbol.upper(),
        InvestmentTransaction.transaction_type.in_(['BUY', 'SELL'])
    )
    if source:
        query = query.filter(InvestmentTransaction.source == source)
    transaction_count = query.count()
    
    result = {
        "account_id": account_id,
        "symbol": symbol.upper(),
        "calculated_cost_basis": float(calculated) if calculated is not None else None,
        "transaction_count": transaction_count,
        "has_transactions": transaction_count > 0,
    }
    
    if holding:
        result["current_cost_basis"] = float(holding.cost_basis) if holding.cost_basis else None
        result["quantity"] = float(holding.quantity) if holding.quantity else 0
        if holding.quantity and holding.quantity > 0 and calculated:
            result["calculated_avg_cost_per_share"] = float(calculated / holding.quantity)
            result["current_avg_cost_per_share"] = float(holding.cost_basis / holding.quantity) if holding.cost_basis else None
    else:
        result["holding_exists"] = False
    
    return result


# ===== Realized P/L (shared lot engine; income unification Phase 2) =====

@router.get("/realized-pnl")
async def get_realized_pnl(
    granularity: str = Query(default="month", description="week (Friday-ending) | month | year"),
    account_id: Optional[str] = Query(default=None),
    start: Optional[date] = Query(default=None),
    end: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Realized stock-sale P/L by period, all accounts (retirement included).

    Backed by the shared lot engine (stock_lot_sale). Weeks end on Friday
    per docs/INCOME-UNIFICATION-SPEC.md. Unresolved-basis rows are excluded
    from P/L and surfaced via unresolved_count/unresolved_proceeds.
    """
    from app.shared.services.cost_basis_service import get_realized_pnl_by_period
    try:
        rows = get_realized_pnl_by_period(
            db, granularity=granularity, account_id=account_id,
            start=start, end=end)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"granularity": granularity, "account_id": account_id, "periods": rows}


@router.get("/realized-pnl/sales")
async def list_realized_sales(
    year: Optional[int] = Query(default=None),
    start: Optional[date] = Query(default=None),
    end: Optional[date] = Query(default=None),
    account_id: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Per-sale realized P/L rows (drill-down for the unified income view)."""
    from sqlalchemy import text
    where, params = [], {}
    if year:
        where.append("s.tax_year = :year"); params["year"] = year
    if start:
        where.append("s.sale_date >= :start"); params["start"] = start
    if end:
        where.append("s.sale_date <= :end"); params["end"] = end
    if account_id:
        where.append("l.account_id = :acct"); params["acct"] = account_id
    if symbol:
        where.append("l.symbol = :sym"); params["sym"] = symbol.upper()
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = db.execute(text(f"""
        SELECT s.sale_date, a.account_name, a.account_type, l.symbol, s.quantity_sold,
               s.proceeds, s.cost_basis, s.gain_loss, s.is_long_term, s.notes
        FROM stock_lot_sale s
        JOIN stock_lot l ON l.lot_id = s.lot_id
        LEFT JOIN investment_accounts a ON a.account_id = l.account_id
        {where_sql}
        ORDER BY s.sale_date DESC, l.symbol
    """), params).fetchall()
    non_taxable = ('ira', 'roth_ira', 'traditional_ira', '401k', 'hsa', 'retirement')
    return {"sales": [{
        "sale_date": str(r.sale_date), "account": r.account_name or "—",
        "taxable": (r.account_type or '') not in non_taxable,
        "symbol": r.symbol, "quantity": float(r.quantity_sold),
        "proceeds": float(r.proceeds), "cost_basis": float(r.cost_basis),
        "gain_loss": float(r.gain_loss), "is_long_term": r.is_long_term,
        "basis_source": (r.notes or "").replace("BASIS_RESOLVED:", "") or "purchase records",
        "unresolved": r.notes == "BASIS_UNKNOWN",
    } for r in rows]}


@router.get("/pure-performance")
async def get_pure_performance_endpoint(db: Session = Depends(get_db)):
    """Pure investment performance (Investments page L1/L2) — value vs. cost
    basis, structurally independent of income. See docs/INVESTMENTS-PAGE-SPEC.md.
    """
    from app.shared.services.cost_basis_service import get_pure_performance
    return get_pure_performance(db)


@router.get("/policy-deviations")
async def get_policy_deviations_endpoint(db: Session = Depends(get_db)):
    """Two-book strategy deviations (Investments page): core exit-recovery
    ledger and idle inventory. See docs/INVESTMENTS-PAGE-SPEC.md,
    'Strategy model & policy deviations'.
    """
    from app.modules.investments.policy_service import get_policy_deviations
    return get_policy_deviations(db)


@router.get("/ghost-curve")
async def get_ghost_curve_endpoint(db: Session = Depends(get_db)):
    """Freeze-curve: for every anchor date, what freezing the options game
    then would be worth today vs. actual. See docs/INVESTMENTS-PAGE-SPEC.md,
    'vs. Buy & Hold (ghost freeze-curve)'."""
    from app.modules.investments.ghost_service import get_ghost_curve
    return get_ghost_curve(db)


@router.get("/ghost-curve/detail")
async def get_ghost_detail_endpoint(anchor: str, db: Session = Depends(get_db)):
    """Drill-down for one anchor: actual-vs-ghost series + divergence table."""
    from datetime import date as _date
    from app.modules.investments.ghost_service import get_ghost_detail
    try:
        anchor_date = _date.fromisoformat(anchor)
    except ValueError:
        raise HTTPException(status_code=400, detail="anchor must be YYYY-MM-DD")
    return get_ghost_detail(db, anchor_date)
