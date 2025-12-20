"""
Cash API routes.
Provides endpoints for cash balance tracking across bank and brokerage accounts.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date
from decimal import Decimal
from pydantic import BaseModel

from app.core.database import get_db
from app.modules.cash.services import (
    get_all_cash_balances,
    get_cash_history,
    get_robinhood_cash_balances,
    get_bank_cash_balances,
    upsert_cash_account,
    add_cash_snapshot,
)
from app.modules.cash.models import CashAccount, CashSnapshot

router = APIRouter()


class CashAccountCreate(BaseModel):
    """Request body for creating a cash account."""
    source: str  # 'bank_of_america', 'chase'
    account_id: str  # Last 4 digits or masked account number
    owner: str  # 'Neel', 'Jaya', 'Joint'
    account_type: str = 'checking'  # 'checking', 'savings', 'money_market'
    account_name: Optional[str] = None
    current_balance: Optional[float] = None


class CashSnapshotCreate(BaseModel):
    """Request body for adding a cash snapshot."""
    source: str
    account_id: str
    snapshot_date: date
    balance: float
    owner: Optional[str] = None
    account_type: Optional[str] = None


@router.get("/summary")
async def get_cash_summary(db: Session = Depends(get_db)):
    """
    Get summary of all cash balances across all sources.
    
    Returns:
    - Total cash across all accounts
    - Breakdown by source (Bank of America, Chase, Robinhood)
    - Breakdown by owner (Neel, Jaya, Joint)
    """
    return get_all_cash_balances(db)


@router.get("/accounts")
async def list_cash_accounts(
    db: Session = Depends(get_db),
    source: Optional[str] = None,
    owner: Optional[str] = None,
):
    """
    List all cash accounts.
    Optionally filter by source or owner.
    """
    query = db.query(CashAccount).filter(CashAccount.is_active == 'Y')
    
    if source:
        query = query.filter(CashAccount.source == source)
    if owner:
        query = query.filter(CashAccount.owner == owner)
    
    accounts = query.all()
    
    return {
        "accounts": [
            {
                "id": acc.id,
                "source": acc.source,
                "account_id": acc.account_id,
                "account_name": acc.account_name,
                "account_type": acc.account_type,
                "owner": acc.owner,
                "current_balance": float(acc.current_balance) if acc.current_balance else None,
                "last_updated": acc.last_updated.isoformat() if acc.last_updated else None,
            }
            for acc in accounts
        ],
        "count": len(accounts)
    }


@router.post("/accounts")
async def create_cash_account(
    account: CashAccountCreate,
    db: Session = Depends(get_db)
):
    """Create or update a cash account."""
    try:
        result = upsert_cash_account(
            db=db,
            source=account.source,
            account_id=account.account_id,
            owner=account.owner,
            account_type=account.account_type,
            account_name=account.account_name,
            current_balance=Decimal(str(account.current_balance)) if account.current_balance else None,
        )
        db.commit()
        
        return {
            "success": True,
            "account": {
                "id": result.id,
                "source": result.source,
                "account_id": result.account_id,
                "owner": result.owner,
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/history")
async def get_history(
    db: Session = Depends(get_db),
    months: int = Query(default=12, le=60),
):
    """
    Get cash balance history over time.
    Returns monthly data points for charting.
    """
    history = get_cash_history(db, months=months)
    
    return {
        "history": history,
        "months": months,
    }


@router.get("/robinhood")
async def get_robinhood_cash(db: Session = Depends(get_db)):
    """
    Get cash balances from Robinhood brokerage accounts only.
    Excludes retirement accounts (401k cash).
    """
    balances = get_robinhood_cash_balances(db)
    total = sum(b['balance'] for b in balances)
    
    return {
        "accounts": balances,
        "total": total,
        "count": len(balances),
    }


@router.get("/banks")
async def get_bank_cash(db: Session = Depends(get_db)):
    """
    Get cash balances from bank accounts (Bank of America, Chase).
    """
    balances = get_bank_cash_balances(db)
    total = sum(b['balance'] for b in balances)
    
    return {
        "accounts": balances,
        "total": total,
        "count": len(balances),
    }


@router.post("/snapshots")
async def add_snapshot(
    snapshot: CashSnapshotCreate,
    db: Session = Depends(get_db)
):
    """Add a cash balance snapshot from a statement."""
    try:
        result = add_cash_snapshot(
            db=db,
            source=snapshot.source,
            account_id=snapshot.account_id,
            snapshot_date=snapshot.snapshot_date,
            balance=Decimal(str(snapshot.balance)),
            owner=snapshot.owner,
            account_type=snapshot.account_type,
        )
        db.commit()
        
        return {
            "success": True,
            "snapshot": {
                "id": result.id,
                "source": result.source,
                "account_id": result.account_id,
                "snapshot_date": result.snapshot_date.isoformat(),
                "balance": float(result.balance),
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/snapshots")
async def list_snapshots(
    db: Session = Depends(get_db),
    source: Optional[str] = None,
    account_id: Optional[str] = None,
    limit: int = Query(default=50, le=200),
):
    """List cash snapshots with optional filters."""
    query = db.query(CashSnapshot)
    
    if source:
        query = query.filter(CashSnapshot.source == source)
    if account_id:
        query = query.filter(CashSnapshot.account_id == account_id)
    
    snapshots = query.order_by(CashSnapshot.snapshot_date.desc()).limit(limit).all()
    
    return {
        "snapshots": [
            {
                "id": snap.id,
                "source": snap.source,
                "account_id": snap.account_id,
                "owner": snap.owner,
                "account_type": snap.account_type,
                "snapshot_date": snap.snapshot_date.isoformat() if snap.snapshot_date else None,
                "balance": float(snap.balance) if snap.balance else 0,
            }
            for snap in snapshots
        ],
        "count": len(snapshots)
    }


@router.get("/by-source/{source}")
async def get_cash_by_source(
    source: str,
    db: Session = Depends(get_db)
):
    """Get cash details for a specific source."""
    if source == 'robinhood':
        balances = get_robinhood_cash_balances(db)
    else:
        # Get from CashSnapshots
        balances = [b for b in get_bank_cash_balances(db) if b['source'] == source]
    
    total = sum(b['balance'] for b in balances)
    
    return {
        "source": source,
        "accounts": balances,
        "total": total,
        "count": len(balances),
    }



