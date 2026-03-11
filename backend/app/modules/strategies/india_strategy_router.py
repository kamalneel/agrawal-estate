"""
Router for India Strategy holdings - goal-based Indian stock portfolio.
"""

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.modules.strategies.models import IndiaStrategyHolding

router = APIRouter()


# --- Pydantic Models ---

class IndiaHoldingCreate(BaseModel):
    symbol: str
    exchange: str = "NSE"
    name: Optional[str] = None
    shares: float = 0
    avg_cost_inr: Optional[float] = None
    current_price_inr: Optional[float] = None
    target_value_inr: Optional[float] = None
    account_name: str = "Default"
    notes: Optional[str] = None


class IndiaHoldingUpdate(BaseModel):
    symbol: Optional[str] = None
    exchange: Optional[str] = None
    name: Optional[str] = None
    shares: Optional[float] = None
    avg_cost_inr: Optional[float] = None
    current_price_inr: Optional[float] = None
    target_value_inr: Optional[float] = None
    account_name: Optional[str] = None
    notes: Optional[str] = None


class IndiaHoldingResponse(BaseModel):
    id: int
    symbol: str
    exchange: str
    name: Optional[str]
    shares: float
    avgCostInr: Optional[float]
    currentPriceInr: Optional[float]
    targetValueInr: Optional[float]
    currentValueInr: Optional[float]
    gapToTargetInr: Optional[float]
    accountName: str
    notes: Optional[str]
    createdAt: datetime
    updatedAt: datetime


class IndiaAccountSummary(BaseModel):
    accountName: str
    totalValueInr: float
    totalTargetInr: float
    holdingsCount: int


# --- Helpers ---

def _to_response(h: IndiaStrategyHolding) -> IndiaHoldingResponse:
    shares = float(h.shares or 0)
    price = float(h.current_price_inr) if h.current_price_inr else None
    current_val = shares * price if price else None
    target = float(h.target_value_inr) if h.target_value_inr else None
    gap = (target - current_val) if (target is not None and current_val is not None) else None

    return IndiaHoldingResponse(
        id=h.id,
        symbol=h.symbol,
        exchange=h.exchange,
        name=h.name,
        shares=shares,
        avgCostInr=float(h.avg_cost_inr) if h.avg_cost_inr else None,
        currentPriceInr=price,
        targetValueInr=target,
        currentValueInr=current_val,
        gapToTargetInr=gap,
        accountName=h.account_name,
        notes=h.notes,
        createdAt=h.created_at,
        updatedAt=h.updated_at,
    )


# --- Endpoints ---

@router.get("/india-strategy/holdings", response_model=List[IndiaHoldingResponse])
async def get_holdings(
    account_name: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get all India strategy holdings, optionally filtered by account."""
    query = db.query(IndiaStrategyHolding)
    if account_name:
        query = query.filter(IndiaStrategyHolding.account_name == account_name)
    holdings = query.order_by(
        IndiaStrategyHolding.account_name,
        IndiaStrategyHolding.symbol,
    ).all()
    return [_to_response(h) for h in holdings]


@router.get("/india-strategy/accounts", response_model=List[IndiaAccountSummary])
async def get_accounts(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get summary of holdings grouped by account."""
    holdings = db.query(IndiaStrategyHolding).all()
    accounts: dict = {}
    for h in holdings:
        acct = h.account_name
        if acct not in accounts:
            accounts[acct] = {"total_value": 0.0, "total_target": 0.0, "count": 0}
        shares = float(h.shares or 0)
        price = float(h.current_price_inr) if h.current_price_inr else 0
        accounts[acct]["total_value"] += shares * price
        accounts[acct]["total_target"] += float(h.target_value_inr or 0)
        accounts[acct]["count"] += 1

    return [
        IndiaAccountSummary(
            accountName=name,
            totalValueInr=data["total_value"],
            totalTargetInr=data["total_target"],
            holdingsCount=data["count"],
        )
        for name, data in sorted(accounts.items())
    ]


@router.post("/india-strategy/holdings", response_model=IndiaHoldingResponse)
async def create_holding(
    holding: IndiaHoldingCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Add a new India strategy holding."""
    new = IndiaStrategyHolding(
        symbol=holding.symbol.upper().strip(),
        exchange=holding.exchange.upper().strip(),
        name=holding.name,
        shares=holding.shares,
        avg_cost_inr=holding.avg_cost_inr,
        current_price_inr=holding.current_price_inr,
        target_value_inr=holding.target_value_inr,
        account_name=holding.account_name,
        notes=holding.notes,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(new)
    db.commit()
    db.refresh(new)
    return _to_response(new)


@router.put("/india-strategy/holdings/{holding_id}", response_model=IndiaHoldingResponse)
async def update_holding(
    holding_id: int,
    updates: IndiaHoldingUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Update an India strategy holding."""
    h = db.query(IndiaStrategyHolding).filter(
        IndiaStrategyHolding.id == holding_id
    ).first()
    if not h:
        raise HTTPException(status_code=404, detail="Holding not found")

    update_data = updates.dict(exclude_unset=True)
    if "symbol" in update_data:
        update_data["symbol"] = update_data["symbol"].upper().strip()
    if "exchange" in update_data:
        update_data["exchange"] = update_data["exchange"].upper().strip()

    for field, value in update_data.items():
        setattr(h, field, value)
    h.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(h)
    return _to_response(h)


@router.delete("/india-strategy/holdings/{holding_id}")
async def delete_holding(
    holding_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Delete an India strategy holding."""
    h = db.query(IndiaStrategyHolding).filter(
        IndiaStrategyHolding.id == holding_id
    ).first()
    if not h:
        raise HTTPException(status_code=404, detail="Holding not found")
    db.delete(h)
    db.commit()
    return {"status": "deleted", "id": holding_id}
