"""
Plaid API routes for managing bank connections and investment data.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import logging

from app.core.database import get_db
from app.core.auth import get_current_user
from app.modules.plaid.service import get_plaid_service, PlaidService
from app.modules.plaid.models import PlaidItem, PlaidAccount, PlaidInvestmentTransaction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plaid", tags=["Plaid"])


# Request/Response Models

class PublicTokenRequest(BaseModel):
    """Request body for exchanging a public token."""
    public_token: str


class LinkTokenResponse(BaseModel):
    """Response for link token creation."""
    link_token: str
    expiration: str


class ItemResponse(BaseModel):
    """Response for a Plaid item."""
    id: int
    item_id: str
    institution_name: Optional[str]
    is_active: bool
    accounts_count: int
    last_synced_at: Optional[str]
    created_at: str


class AccountResponse(BaseModel):
    """Response for a Plaid account."""
    id: int
    account_id: str
    name: str
    official_name: Optional[str]
    type: str
    subtype: Optional[str]
    mask: Optional[str]
    current_balance: Optional[str]
    is_active: bool


class TransactionResponse(BaseModel):
    """Response for investment transactions."""
    transactions: List[dict]
    total_count: int


class SyncResponse(BaseModel):
    """Response for sync operations."""
    success: bool
    new_transactions: int
    message: str


# Routes

@router.get("/link-token", response_model=LinkTokenResponse)
async def create_link_token(
    current_user: str = Depends(get_current_user),
):
    """
    Create a Plaid Link token for initializing Plaid Link in the frontend.
    This token is used to launch the Plaid Link flow to connect bank accounts.
    """
    try:
        service = get_plaid_service()
        result = service.create_link_token()
        return LinkTokenResponse(
            link_token=result["link_token"],
            expiration=str(result["expiration"]),
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create link token: {e}")
        raise HTTPException(status_code=500, detail="Failed to create Plaid Link token")


@router.post("/exchange-token")
async def exchange_public_token(
    request: PublicTokenRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Exchange a public token from Plaid Link for an access token.
    This completes the account linking process.
    """
    try:
        service = get_plaid_service()
        plaid_item = service.exchange_public_token(request.public_token, db)
        
        return {
            "success": True,
            "item_id": plaid_item.id,
            "institution_name": plaid_item.institution_name,
            "accounts_count": len(plaid_item.accounts),
            "message": f"Successfully linked {plaid_item.institution_name or 'account'}"
        }
    except Exception as e:
        logger.error(f"Failed to exchange public token: {e}")
        raise HTTPException(status_code=500, detail="Failed to link account")


@router.get("/items", response_model=List[ItemResponse])
async def get_linked_items(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Get all linked Plaid items (financial institutions).
    """
    try:
        service = get_plaid_service()
        items = service.get_all_items(db)
        
        return [
            ItemResponse(
                id=item.id,
                item_id=item.item_id,
                institution_name=item.institution_name,
                is_active=item.is_active,
                accounts_count=len([a for a in item.accounts if a.is_active]),
                last_synced_at=str(item.last_synced_at) if item.last_synced_at else None,
                created_at=str(item.created_at),
            )
            for item in items
        ]
    except ValueError:
        # Plaid not configured
        return []
    except Exception as e:
        logger.error(f"Failed to get items: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch linked accounts")


@router.get("/items/{item_id}/accounts", response_model=List[AccountResponse])
async def get_item_accounts(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Get accounts for a specific Plaid item.
    """
    service = get_plaid_service()
    item = service.get_item_by_id(item_id, db)
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    return [
        AccountResponse(
            id=acc.id,
            account_id=acc.account_id,
            name=acc.name,
            official_name=acc.official_name,
            type=acc.type,
            subtype=acc.subtype,
            mask=acc.mask,
            current_balance=acc.current_balance,
            is_active=acc.is_active,
        )
        for acc in item.accounts if acc.is_active
    ]


@router.get("/items/{item_id}/holdings")
async def get_item_holdings(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Get current holdings for a Plaid item.
    """
    service = get_plaid_service()
    item = service.get_item_by_id(item_id, db)
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    try:
        return service.get_investment_holdings(item.access_token)
    except Exception as e:
        logger.error(f"Failed to get holdings: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch holdings")


@router.get("/items/{item_id}/transactions")
async def get_item_transactions(
    item_id: int,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Get investment transactions for a Plaid item.
    """
    service = get_plaid_service()
    item = service.get_item_by_id(item_id, db)
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
        end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else None
        
        return service.get_investment_transactions(item.access_token, start, end)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    except Exception as e:
        logger.error(f"Failed to get transactions: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch transactions")


@router.post("/items/{item_id}/sync", response_model=SyncResponse)
async def sync_item_transactions(
    item_id: int,
    days: int = Query(30, description="Number of days to sync"),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Sync investment transactions from Plaid to the local database.
    """
    service = get_plaid_service()
    item = service.get_item_by_id(item_id, db)
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    try:
        start_date = datetime.now() - timedelta(days=days)
        new_count = service.sync_transactions_to_db(item, db, start_date)
        
        return SyncResponse(
            success=True,
            new_transactions=new_count,
            message=f"Synced {new_count} new transactions"
        )
    except Exception as e:
        logger.error(f"Failed to sync transactions: {e}")
        raise HTTPException(status_code=500, detail="Failed to sync transactions")


@router.post("/items/{item_id}/refresh")
async def refresh_item_data(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Request Plaid to refresh investment data for an item.
    """
    service = get_plaid_service()
    item = service.get_item_by_id(item_id, db)
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    success = service.refresh_investments(item.access_token)
    
    if success:
        return {"success": True, "message": "Refresh initiated. New data will be available shortly."}
    else:
        raise HTTPException(status_code=500, detail="Failed to refresh investment data")


@router.delete("/items/{item_id}")
async def remove_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Remove (disconnect) a Plaid item.
    """
    service = get_plaid_service()
    item = service.get_item_by_id(item_id, db)
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    success = service.remove_item(item, db)
    
    if success:
        return {"success": True, "message": "Account disconnected successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to disconnect account")


@router.get("/transactions")
async def get_all_transactions(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    ticker: Optional[str] = Query(None, description="Filter by ticker symbol"),
    transaction_type: Optional[str] = Query(None, description="Filter by type (buy, sell)"),
    limit: int = Query(100, description="Max results"),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Get stored investment transactions from the database.
    Useful for RLHF reconciliation.
    """
    query = db.query(PlaidInvestmentTransaction)
    
    if start_date:
        query = query.filter(PlaidInvestmentTransaction.date >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        query = query.filter(PlaidInvestmentTransaction.date <= datetime.strptime(end_date, "%Y-%m-%d"))
    if ticker:
        query = query.filter(PlaidInvestmentTransaction.ticker_symbol.ilike(f"%{ticker}%"))
    if transaction_type:
        query = query.filter(PlaidInvestmentTransaction.type == transaction_type)
    
    transactions = query.order_by(PlaidInvestmentTransaction.date.desc()).limit(limit).all()
    
    return {
        "transactions": [
            {
                "id": t.id,
                "date": str(t.date.date()) if t.date else None,
                "ticker": t.ticker_symbol,
                "name": t.name,
                "type": t.type,
                "subtype": t.subtype,
                "quantity": t.quantity,
                "price": t.price,
                "amount": t.amount,
                "option_type": t.option_type,
                "strike_price": t.strike_price,
                "expiration_date": str(t.expiration_date.date()) if t.expiration_date else None,
                "underlying_symbol": t.underlying_symbol,
            }
            for t in transactions
        ],
        "count": len(transactions),
    }


@router.post("/sync-all", response_model=SyncResponse)
async def sync_all_items(
    days: int = Query(30, description="Number of days to sync"),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Sync transactions from all linked Plaid items.
    """
    try:
        service = get_plaid_service()
        items = service.get_all_items(db)
        
        total_new = 0
        start_date = datetime.now() - timedelta(days=days)
        
        for item in items:
            try:
                new_count = service.sync_transactions_to_db(item, db, start_date)
                total_new += new_count
            except Exception as e:
                logger.error(f"Failed to sync item {item.id}: {e}")
        
        return SyncResponse(
            success=True,
            new_transactions=total_new,
            message=f"Synced {total_new} new transactions from {len(items)} accounts"
        )
    except ValueError:
        return SyncResponse(
            success=False,
            new_transactions=0,
            message="Plaid not configured"
        )

