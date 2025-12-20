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


@router.get("/portfolio-history")
async def get_portfolio_history(
    db: Session = Depends(get_db),
    owner: Optional[str] = None,
    account_id: Optional[str] = None,
):
    """
    Get historical portfolio values from statement snapshots.
    Returns monthly data points for the chart.
    Can filter by owner (all accounts for that person) or account_id (specific account).
    """
    from sqlalchemy import func
    
    query = db.query(
        PortfolioSnapshot.statement_date,
        func.sum(PortfolioSnapshot.portfolio_value).label('total_value')
    ).group_by(
        PortfolioSnapshot.statement_date
    ).order_by(PortfolioSnapshot.statement_date)
    
    # Filter by specific account if provided (takes precedence)
    if account_id:
        query = query.filter(PortfolioSnapshot.account_id == account_id)
    elif owner:
        query = query.filter(PortfolioSnapshot.owner == owner)
    
    snapshots = query.all()
    
    # Group by date for total portfolio value
    date_totals = {}
    for snapshot in snapshots:
        date_str = snapshot.statement_date.strftime("%Y-%m")
        if date_str not in date_totals:
            date_totals[date_str] = 0
        date_totals[date_str] += float(snapshot.total_value)
    
    # Format for chart
    history = [
        {
            "month": date_str,
            "value": round(value, 2),
            "formatted": f"{datetime.strptime(date_str, '%Y-%m').strftime('%b %Y')}"
        }
        for date_str, value in sorted(date_totals.items())
    ]
    
    return {
        "history": history,
        "total_snapshots": len(snapshots),
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
    
    # Define time periods to calculate
    period_configs = [
        ("30d", 30, "30 Days"),
        ("90d", 90, "90 Days"),
        ("1y", 365, "1 Year"),
    ]
    
    for period_key, days, label in period_configs:
        target_date = today - timedelta(days=days)
        
        # Find the closest snapshot to the target date (looking back)
        closest_snapshot = None
        min_diff = float('inf')
        
        for s in snapshots:
            # Only consider snapshots older than target date
            diff = (target_date - s.statement_date).days
            if diff >= 0 and diff < min_diff:
                min_diff = diff
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
