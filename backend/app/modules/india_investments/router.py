"""
India Investments API routes.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel

from app.core.database import get_db
from app.modules.india_investments.models import (
    IndiaBankAccount,
    IndiaInvestmentAccount,
    IndiaStock,
    IndiaMutualFund,
    IndiaFixedDeposit,
    ExchangeRate,
    FatherMutualFundHolding,
    FatherStockHolding,
)
from app.modules.india_investments.services import (
    get_all_india_investments,
    get_dashboard_india_investments,
    calculate_fd_current_value,
)

router = APIRouter()


# Pydantic models for request bodies
class BankAccountCreate(BaseModel):
    account_name: str
    bank_name: str
    account_number: Optional[str] = None
    owner: str  # 'Neel' or 'Father'
    account_type: Optional[str] = None
    cash_balance: float = 0
    notes: Optional[str] = None


class InvestmentAccountCreate(BaseModel):
    account_name: str
    platform: str  # 'Zerodha'
    account_number: Optional[str] = None
    owner: str  # 'Neel' or 'Father'
    linked_bank_account_id: Optional[int] = None
    notes: Optional[str] = None


class StockCreate(BaseModel):
    investment_account_id: int
    symbol: str
    company_name: Optional[str] = None
    quantity: float
    average_price: Optional[float] = None
    current_price: Optional[float] = None
    cost_basis: Optional[float] = None


class MutualFundCreate(BaseModel):
    investment_account_id: int
    fund_name: str
    fund_code: Optional[str] = None
    category: str  # 'india_fund' or 'international_fund'
    units: float
    nav: Optional[float] = None
    purchase_price: Optional[float] = None
    cost_basis: Optional[float] = None


class FixedDepositCreate(BaseModel):
    bank_account_id: int
    fd_number: Optional[str] = None
    description: Optional[str] = None
    principal: float
    interest_rate: float
    start_date: date
    maturity_date: date
    notes: Optional[str] = None


class ExchangeRateUpdate(BaseModel):
    rate: float


class FatherMutualFundHoldingCreate(BaseModel):
    investment_date: date
    fund_name: str
    folio_number: Optional[str] = None
    initial_invested_amount: float
    amount_march_2025: Optional[float] = None
    current_amount: Optional[float] = None
    return_1y: Optional[float] = None
    return_3y: Optional[float] = None
    return_5y: Optional[float] = None
    fund_category: Optional[str] = None
    notes: Optional[str] = None


class FatherMutualFundHoldingUpdate(BaseModel):
    investment_date: Optional[date] = None
    fund_name: Optional[str] = None
    folio_number: Optional[str] = None
    initial_invested_amount: Optional[float] = None
    amount_march_2025: Optional[float] = None
    current_amount: Optional[float] = None
    return_1y: Optional[float] = None
    return_3y: Optional[float] = None
    return_5y: Optional[float] = None
    fund_category: Optional[str] = None
    notes: Optional[str] = None


# Bank Accounts
@router.get("/bank-accounts")
async def list_bank_accounts(
    db: Session = Depends(get_db),
    owner: Optional[str] = None
):
    """List all bank accounts."""
    query = db.query(IndiaBankAccount).filter(IndiaBankAccount.is_active == 'Y')
    if owner:
        query = query.filter(IndiaBankAccount.owner == owner)
    
    accounts = query.all()
    return {
        "accounts": [
            {
                "id": acc.id,
                "account_name": acc.account_name,
                "bank_name": acc.bank_name,
                "account_number": acc.account_number,
                "owner": acc.owner,
                "account_type": acc.account_type,
                "cash_balance": float(acc.cash_balance or 0),
                "notes": acc.notes,
            }
            for acc in accounts
        ]
    }


@router.post("/bank-accounts")
async def create_bank_account(
    account: BankAccountCreate,
    db: Session = Depends(get_db)
):
    """Create a new bank account."""
    bank_account = IndiaBankAccount(
        account_name=account.account_name,
        bank_name=account.bank_name,
        account_number=account.account_number,
        owner=account.owner,
        account_type=account.account_type,
        cash_balance=Decimal(str(account.cash_balance)),
        notes=account.notes,
    )
    db.add(bank_account)
    db.commit()
    db.refresh(bank_account)
    
    return {
        "success": True,
        "account": {
            "id": bank_account.id,
            "account_name": bank_account.account_name,
            "bank_name": bank_account.bank_name,
            "owner": bank_account.owner,
        }
    }


# Investment Accounts
@router.get("/investment-accounts")
async def list_investment_accounts(
    db: Session = Depends(get_db),
    owner: Optional[str] = None
):
    """List all investment accounts."""
    query = db.query(IndiaInvestmentAccount).filter(IndiaInvestmentAccount.is_active == 'Y')
    if owner:
        query = query.filter(IndiaInvestmentAccount.owner == owner)
    
    accounts = query.all()
    return {
        "accounts": [
            {
                "id": acc.id,
                "account_name": acc.account_name,
                "platform": acc.platform,
                "account_number": acc.account_number,
                "owner": acc.owner,
                "linked_bank_account_id": acc.linked_bank_account_id,
                "notes": acc.notes,
            }
            for acc in accounts
        ]
    }


@router.post("/investment-accounts")
async def create_investment_account(
    account: InvestmentAccountCreate,
    db: Session = Depends(get_db)
):
    """Create a new investment account."""
    investment_account = IndiaInvestmentAccount(
        account_name=account.account_name,
        platform=account.platform,
        account_number=account.account_number,
        owner=account.owner,
        linked_bank_account_id=account.linked_bank_account_id,
        notes=account.notes,
    )
    db.add(investment_account)
    db.commit()
    db.refresh(investment_account)
    
    return {
        "success": True,
        "account": {
            "id": investment_account.id,
            "account_name": investment_account.account_name,
            "platform": investment_account.platform,
            "owner": investment_account.owner,
        }
    }


# Stocks
@router.get("/stocks")
async def list_stocks(
    db: Session = Depends(get_db),
    investment_account_id: Optional[int] = None
):
    """List all stocks."""
    query = db.query(IndiaStock)
    if investment_account_id:
        query = query.filter(IndiaStock.investment_account_id == investment_account_id)
    
    stocks = query.all()
    return {
        "stocks": [
            {
                "id": stock.id,
                "investment_account_id": stock.investment_account_id,
                "symbol": stock.symbol,
                "company_name": stock.company_name,
                "quantity": float(stock.quantity or 0),
                "average_price": float(stock.average_price or 0),
                "current_price": float(stock.current_price or 0),
                "cost_basis": float(stock.cost_basis or 0),
                "current_value": float(stock.current_value or 0),
                "profit_loss": float(stock.profit_loss or 0),
            }
            for stock in stocks
        ]
    }


@router.post("/stocks")
async def create_stock(
    stock: StockCreate,
    db: Session = Depends(get_db)
):
    """Create or update a stock holding."""
    # Calculate current value and P&L
    current_value = stock.quantity * (stock.current_price or 0)
    cost_basis = stock.cost_basis or (stock.quantity * (stock.average_price or 0))
    profit_loss = current_value - cost_basis
    
    india_stock = IndiaStock(
        investment_account_id=stock.investment_account_id,
        symbol=stock.symbol.upper(),
        company_name=stock.company_name,
        quantity=Decimal(str(stock.quantity)),
        average_price=Decimal(str(stock.average_price)) if stock.average_price else None,
        current_price=Decimal(str(stock.current_price)) if stock.current_price else None,
        cost_basis=Decimal(str(cost_basis)),
        current_value=Decimal(str(current_value)),
        profit_loss=Decimal(str(profit_loss)),
    )
    db.add(india_stock)
    db.commit()
    db.refresh(india_stock)
    
    return {
        "success": True,
        "stock": {
            "id": india_stock.id,
            "symbol": india_stock.symbol,
            "current_value": float(india_stock.current_value or 0),
        }
    }


# Mutual Funds
@router.get("/mutual-funds")
async def list_mutual_funds(
    db: Session = Depends(get_db),
    investment_account_id: Optional[int] = None
):
    """List all mutual funds."""
    query = db.query(IndiaMutualFund)
    if investment_account_id:
        query = query.filter(IndiaMutualFund.investment_account_id == investment_account_id)
    
    mutual_funds = query.all()
    return {
        "mutual_funds": [
            {
                "id": mf.id,
                "investment_account_id": mf.investment_account_id,
                "fund_name": mf.fund_name,
                "fund_code": mf.fund_code,
                "category": mf.category,
                "units": float(mf.units or 0),
                "nav": float(mf.nav or 0),
                "purchase_price": float(mf.purchase_price or 0),
                "cost_basis": float(mf.cost_basis or 0),
                "current_value": float(mf.current_value or 0),
                "profit_loss": float(mf.profit_loss or 0),
            }
            for mf in mutual_funds
        ]
    }


@router.post("/mutual-funds")
async def create_mutual_fund(
    mf: MutualFundCreate,
    db: Session = Depends(get_db)
):
    """Create or update a mutual fund holding."""
    # Calculate current value and P&L
    current_value = mf.units * (mf.nav or 0)
    cost_basis = mf.cost_basis or (mf.units * (mf.purchase_price or 0))
    profit_loss = current_value - cost_basis
    
    india_mf = IndiaMutualFund(
        investment_account_id=mf.investment_account_id,
        fund_name=mf.fund_name,
        fund_code=mf.fund_code,
        category=mf.category,
        units=Decimal(str(mf.units)),
        nav=Decimal(str(mf.nav)) if mf.nav else None,
        purchase_price=Decimal(str(mf.purchase_price)) if mf.purchase_price else None,
        cost_basis=Decimal(str(cost_basis)),
        current_value=Decimal(str(current_value)),
        profit_loss=Decimal(str(profit_loss)),
    )
    db.add(india_mf)
    db.commit()
    db.refresh(india_mf)
    
    return {
        "success": True,
        "mutual_fund": {
            "id": india_mf.id,
            "fund_name": india_mf.fund_name,
            "current_value": float(india_mf.current_value or 0),
        }
    }


# Fixed Deposits
@router.get("/fixed-deposits")
async def list_fixed_deposits(
    db: Session = Depends(get_db),
    bank_account_id: Optional[int] = None
):
    """List all fixed deposits."""
    from datetime import date as date_type
    
    query = db.query(IndiaFixedDeposit).filter(IndiaFixedDeposit.is_active == 'Y')
    if bank_account_id:
        query = query.filter(IndiaFixedDeposit.bank_account_id == bank_account_id)
    
    fixed_deposits = query.all()
    
    # Calculate current values
    today = date_type.today()
    result = []
    for fd in fixed_deposits:
        if fd.maturity_date and fd.start_date:
            calc = calculate_fd_current_value(
                fd.principal,
                fd.interest_rate,
                fd.start_date,
                fd.maturity_date,
                today
            )
            result.append({
                "id": fd.id,
                "bank_account_id": fd.bank_account_id,
                "fd_number": fd.fd_number,
                "description": fd.description,
                "principal": float(fd.principal or 0),
                "interest_rate": float(fd.interest_rate or 0),
                "start_date": fd.start_date.isoformat() if fd.start_date else None,
                "maturity_date": fd.maturity_date.isoformat() if fd.maturity_date else None,
                "current_value": float(calc['current_value']),
                "accrued_interest": float(calc['accrued_interest']),
                "maturity_value": float(calc['maturity_value']),
                "days_to_maturity": calc['days_to_maturity'],
                "notes": fd.notes,
            })
    
    return {"fixed_deposits": result}


@router.post("/fixed-deposits")
async def create_fixed_deposit(
    fd: FixedDepositCreate,
    db: Session = Depends(get_db)
):
    """Create a new fixed deposit."""
    from datetime import date as date_type
    
    # Calculate initial values
    today = date_type.today()
    calc = calculate_fd_current_value(
        Decimal(str(fd.principal)),
        Decimal(str(fd.interest_rate)),
        fd.start_date,
        fd.maturity_date,
        today
    )
    
    india_fd = IndiaFixedDeposit(
        bank_account_id=fd.bank_account_id,
        fd_number=fd.fd_number,
        description=fd.description,
        principal=Decimal(str(fd.principal)),
        interest_rate=Decimal(str(fd.interest_rate)),
        start_date=fd.start_date,
        maturity_date=fd.maturity_date,
        current_value=calc['current_value'],
        accrued_interest=calc['accrued_interest'],
        maturity_value=calc['maturity_value'],
        notes=fd.notes,
    )
    db.add(india_fd)
    db.commit()
    db.refresh(india_fd)
    
    return {
        "success": True,
        "fixed_deposit": {
            "id": india_fd.id,
            "current_value": float(india_fd.current_value or 0),
        }
    }


# Exchange Rate
@router.get("/exchange-rate")
async def get_exchange_rate(db: Session = Depends(get_db)):
    """Get current USD to INR exchange rate."""
    try:
        rate = db.query(ExchangeRate).filter(
            ExchangeRate.from_currency == 'USD',
            ExchangeRate.to_currency == 'INR'
        ).first()
        
        if not rate:
            # Create default rate if none exists
            rate = ExchangeRate(
                from_currency='USD',
                to_currency='INR',
                rate=Decimal('83.0'),
            )
            db.add(rate)
            db.commit()
            db.refresh(rate)
        
        return {
            "from_currency": rate.from_currency,
            "to_currency": rate.to_currency,
            "rate": float(rate.rate),
            "updated_at": rate.updated_at.isoformat() if rate.updated_at else None,
        }
    except Exception as e:
        # If tables don't exist, return default rate
        import traceback
        traceback.print_exc()
        return {
            "from_currency": "USD",
            "to_currency": "INR",
            "rate": 83.0,
            "updated_at": None,
        }


@router.put("/exchange-rate")
async def update_exchange_rate(
    rate_update: ExchangeRateUpdate,
    db: Session = Depends(get_db)
):
    """Update USD to INR exchange rate."""
    rate = db.query(ExchangeRate).filter(
        ExchangeRate.from_currency == 'USD',
        ExchangeRate.to_currency == 'INR'
    ).first()
    
    if not rate:
        rate = ExchangeRate(
            from_currency='USD',
            to_currency='INR',
            rate=Decimal(str(rate_update.rate)),
        )
        db.add(rate)
    else:
        rate.rate = Decimal(str(rate_update.rate))
        rate.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(rate)
    
    return {
        "success": True,
        "rate": float(rate.rate),
        "updated_at": rate.updated_at.isoformat() if rate.updated_at else None,
    }


# Summary endpoint
@router.get("/summary")
async def get_summary(
    db: Session = Depends(get_db),
    owner: Optional[str] = None
):
    """Get summary of all India investments."""
    try:
        return get_all_india_investments(db, owner=owner)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching India investments: {str(e)}")


@router.get("/dashboard")
async def get_dashboard_data(db: Session = Depends(get_db)):
    """Get India investments for dashboard (only Neel's accounts)."""
    return get_dashboard_india_investments(db)


# Father's Mutual Fund Holdings
@router.get("/father-mutual-funds")
async def list_father_mutual_funds(db: Session = Depends(get_db)):
    """List all of Father's mutual fund holdings."""
    holdings = db.query(FatherMutualFundHolding).order_by(
        FatherMutualFundHolding.investment_date.desc()
    ).all()
    
    # Calculate totals
    total_invested = sum(float(h.initial_invested_amount or 0) for h in holdings)
    total_march_2025 = sum(float(h.amount_march_2025 or 0) for h in holdings)
    total_current = sum(float(h.current_amount or 0) for h in holdings)
    
    return {
        "holdings": [
            {
                "id": h.id,
                "investment_date": h.investment_date.isoformat() if h.investment_date else None,
                "fund_name": h.fund_name,
                "folio_number": h.folio_number,
                "scheme_code": h.scheme_code,
                "isin": h.isin,
                "initial_invested_amount": float(h.initial_invested_amount or 0),
                "amount_march_2025": float(h.amount_march_2025) if h.amount_march_2025 else None,
                "current_amount": float(h.current_amount) if h.current_amount else None,
                # Returns
                "return_1y": float(h.return_1y) if h.return_1y else None,
                "return_3y": float(h.return_3y) if h.return_3y else None,
                "return_5y": float(h.return_5y) if h.return_5y else None,
                "return_10y": float(h.return_10y) if h.return_10y else None,
                # Risk metrics
                "volatility": float(h.volatility) if h.volatility else None,
                "sharpe_ratio": float(h.sharpe_ratio) if h.sharpe_ratio else None,
                "alpha": float(h.alpha) if h.alpha else None,
                "beta": float(h.beta) if h.beta else None,
                # Fund details (from Kuvera)
                "aum": float(h.aum) if h.aum else None,
                "expense_ratio": float(h.expense_ratio) if h.expense_ratio else None,
                "fund_rating": h.fund_rating,
                "fund_start_date": h.fund_start_date.isoformat() if h.fund_start_date else None,
                "crisil_rating": h.crisil_rating,
                "fund_category": h.fund_category,
                "notes": h.notes,
                "last_updated": h.last_updated.isoformat() if h.last_updated else None,
            }
            for h in holdings
        ],
        "summary": {
            "total_invested": total_invested,
            "total_march_2025": total_march_2025,
            "total_current": total_current,
            "total_gain_loss": total_current - total_invested if total_current else None,
            "count": len(holdings),
        }
    }


@router.post("/father-mutual-funds")
async def create_father_mutual_fund(
    holding: FatherMutualFundHoldingCreate,
    db: Session = Depends(get_db)
):
    """Create a new Father's mutual fund holding."""
    march_2025_cutoff = date(2025, 3, 31)
    
    # Determine March 2025 value based on investment date
    amount_march_2025 = None
    if holding.amount_march_2025:
        amount_march_2025 = Decimal(str(holding.amount_march_2025))
    elif holding.investment_date > march_2025_cutoff:
        # Investment after March 2025: Set baseline = initial amount
        amount_march_2025 = Decimal(str(holding.initial_invested_amount))
    
    new_holding = FatherMutualFundHolding(
        investment_date=holding.investment_date,
        fund_name=holding.fund_name,
        folio_number=holding.folio_number,
        initial_invested_amount=Decimal(str(holding.initial_invested_amount)),
        amount_march_2025=amount_march_2025,
        current_amount=Decimal(str(holding.current_amount)) if holding.current_amount else None,
        return_1y=Decimal(str(holding.return_1y)) if holding.return_1y else None,
        return_3y=Decimal(str(holding.return_3y)) if holding.return_3y else None,
        return_5y=Decimal(str(holding.return_5y)) if holding.return_5y else None,
        fund_category=holding.fund_category,
        notes=holding.notes,
    )
    db.add(new_holding)
    db.commit()
    db.refresh(new_holding)
    
    return {
        "success": True,
        "holding": {
            "id": new_holding.id,
            "fund_name": new_holding.fund_name,
            "initial_invested_amount": float(new_holding.initial_invested_amount or 0),
            "amount_march_2025": float(new_holding.amount_march_2025) if new_holding.amount_march_2025 else None,
        }
    }


@router.put("/father-mutual-funds/{holding_id}")
async def update_father_mutual_fund(
    holding_id: int,
    updates: FatherMutualFundHoldingUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing Father's mutual fund holding."""
    holding = db.query(FatherMutualFundHolding).filter(
        FatherMutualFundHolding.id == holding_id
    ).first()
    
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    
    # Track if we need to recalculate dependent values
    recalculate_values = False
    march_2025_cutoff = date(2025, 3, 31)
    
    # Update only provided fields
    if updates.investment_date is not None:
        holding.investment_date = updates.investment_date
        recalculate_values = True  # Investment date changed - recalculate
    if updates.fund_name is not None:
        holding.fund_name = updates.fund_name
    if updates.folio_number is not None:
        holding.folio_number = updates.folio_number
    if updates.initial_invested_amount is not None:
        holding.initial_invested_amount = Decimal(str(updates.initial_invested_amount))
        recalculate_values = True  # Initial amount changed - recalculate
    if updates.amount_march_2025 is not None:
        holding.amount_march_2025 = Decimal(str(updates.amount_march_2025))
    if updates.current_amount is not None:
        holding.current_amount = Decimal(str(updates.current_amount))
    if updates.return_1y is not None:
        holding.return_1y = Decimal(str(updates.return_1y))
    if updates.return_3y is not None:
        holding.return_3y = Decimal(str(updates.return_3y))
    if updates.return_5y is not None:
        holding.return_5y = Decimal(str(updates.return_5y))
    if updates.fund_category is not None:
        holding.fund_category = updates.fund_category
    if updates.notes is not None:
        holding.notes = updates.notes
    
    # SYSTEMATIC: Auto-recalculate March 2025 and current amount when key fields change
    if recalculate_values and holding.investment_date and holding.initial_invested_amount:
        if holding.investment_date > march_2025_cutoff:
            # Investment after March 2025: Set March 2025 = Initial Amount (baseline)
            holding.amount_march_2025 = holding.initial_invested_amount
            
            # Calculate current amount based on available returns
            if holding.return_1y is not None:
                # Use 1Y return prorated for time since investment
                from datetime import datetime as dt
                months_since_investment = (dt.now().date() - holding.investment_date).days / 30.44
                annual_return = float(holding.return_1y) / 100
                monthly_return = annual_return / 12
                prorated_return = monthly_return * months_since_investment
                current_value = float(holding.initial_invested_amount) * (1 + prorated_return)
                holding.current_amount = Decimal(str(round(current_value, 2)))
        # else: Investment before March 2025 - leave March 2025 value as manually entered
    
    holding.last_updated = datetime.utcnow()
    db.commit()
    db.refresh(holding)
    
    return {
        "success": True,
        "holding": {
            "id": holding.id,
            "fund_name": holding.fund_name,
            "current_amount": float(holding.current_amount) if holding.current_amount else None,
            "amount_march_2025": float(holding.amount_march_2025) if holding.amount_march_2025 else None,
        }
    }


@router.delete("/father-mutual-funds/{holding_id}")
async def delete_father_mutual_fund(
    holding_id: int,
    db: Session = Depends(get_db)
):
    """Delete a Father's mutual fund holding."""
    holding = db.query(FatherMutualFundHolding).filter(
        FatherMutualFundHolding.id == holding_id
    ).first()
    
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    
    db.delete(holding)
    db.commit()
    
    return {"success": True, "message": f"Holding {holding_id} deleted"}


# Mapping of common fund names to MFapi scheme codes
FATHER_FUND_SCHEME_CODES = {
    # Non-MF assets
    "PPF": None,  # PPF is not a mutual fund
    "Reliance": None,  # Need more info on this
    
    # SBI
    "SBI Global": "119598",  # SBI International Access US Equity FoF
    "SBI MNC Fund (G)": "119700",  # SBI Magnum MNC Fund
    
    # ICICI Prudential
    "ICICI Asset Allocator": "120606",  # ICICI Prudential Asset Allocator Fund
    "ICICI Banking Plus SIP": "120594",  # ICICI Prudential Banking & Financial Services Fund
    "ICICI Pru Banking & Financial Services (G)": "120594",  # Same as above
    "ICICI Blue Chip Plus SIP": "120586",  # ICICI Prudential Bluechip Fund
    "ICICI Pru Large Cap Fund (G)": "120586",  # Same as ICICI Blue Chip
    "ICICI Balance Limited": "120574",  # ICICI Prudential Balanced Advantage Fund
    "ICICI Pru Balanced Advantage Fund (G)": "120574",  # Same as above
    "ICICI Pru Dynamic Asset Allocation Active FOF-Reg (G)": "149652",  # ICICI Pru Dynamic Asset Allocation FoF
    
    # Franklin Templeton
    "Franklin Prima Plus SIP": "100470",  # Franklin India Prima Fund
    "Franklin India Mid Cap Fund (G)": "100470",  # Franklin India Prima Fund (was renamed)
    "Franklin Focused Equity Fund": "100498",  # Franklin India Focused Equity Fund
    
    # Aditya Birla Sun Life
    "ABSL Banking Plus SIP": "119551",  # ABSL Banking & PSU Debt Fund
    "Aditya Birla SL Banking & Financial Services (G)": "100177",  # ABSL Financial Services Fund
    "ABSL Frontline SIP": "100177",  # Aditya Birla Sun Life Frontline Equity Fund
    "Aditya Birla SL Large Cap Fund (G)": "100177",  # Same as frontline
    "ABSL Business Cycle Fund": "149486",  # ABSL Business Cycle Fund
    "Aditya Birla SL Business Cycle Fund (G)": "149486",  # Same as above
    
    # Edelweiss
    "Edelweiss Small Cap": "147946",  # Edelweiss Small Cap Fund
    "Edelweiss Aggressive Hybrid Fund": "120348",  # Edelweiss Aggressive Hybrid Fund
    "Edelweiss Balance Advantage": "120351",  # Edelweiss Balanced Advantage Fund
    "Edelweiss Balanced Advantage Fund (G)": "120351",  # Same as above
    "Elelwise Multi Asset Omni Fund": "150583",  # Edelweiss Multi Asset Allocation Fund (misspelled in data)
    
    # DSP
    "DSP Aggressive Hybrid Fund": "100056",  # DSP Equity & Bond Fund
    "DSP Flexi Cap Quality 30 Index Fund": "150936",  # DSP Flexi Cap Fund
    
    # Mirae Asset
    "Mirae Asset Mutual Fund": "118834",  # Mirae Asset Large Cap Fund
    "Mirae Asset Small Cap Fund - Regular (G)": "147622",  # Mirae Asset Small Cap Fund
    
    # HSBC
    "HSBC Aggressive Hybrid Fund (G)": "120222",  # HSBC Aggressive Hybrid Fund
    
    # Invesco
    "Invesco Indian Business Cycle Fund": "150481",  # Invesco India Business Cycle Fund
}


@router.post("/father-mutual-funds/refresh-returns")
async def refresh_father_mutual_fund_returns(db: Session = Depends(get_db)):
    """Fetch and update 1Y, 3Y, 5Y returns from MFapi.in for all father's mutual fund holdings."""
    from app.modules.india_investments.mf_research_service import (
        get_scheme_nav_history,
        calculate_returns
    )
    
    holdings = db.query(FatherMutualFundHolding).all()
    updated = []
    errors = []
    
    for holding in holdings:
        fund_name = holding.fund_name
        scheme_code = FATHER_FUND_SCHEME_CODES.get(fund_name)
        
        if not scheme_code:
            errors.append({
                "fund_name": fund_name,
                "error": "No scheme code mapped"
            })
            continue
        
        try:
            # Fetch NAV history from API
            nav_history = get_scheme_nav_history(scheme_code, days=3650)
            
            if not nav_history:
                errors.append({
                    "fund_name": fund_name,
                    "error": "No NAV data returned from API"
                })
                continue
            
            # Calculate returns
            returns = calculate_returns(nav_history)
            
            # Update holding
            if returns.get("return_1y") is not None:
                holding.return_1y = Decimal(str(returns["return_1y"]))
            if returns.get("return_3y") is not None:
                holding.return_3y = Decimal(str(returns["return_3y"]))
            if returns.get("return_5y") is not None:
                holding.return_5y = Decimal(str(returns["return_5y"]))
            
            holding.last_updated = datetime.utcnow()
            
            updated.append({
                "fund_name": fund_name,
                "return_1y": returns.get("return_1y"),
                "return_3y": returns.get("return_3y"),
                "return_5y": returns.get("return_5y"),
            })
        except Exception as e:
            errors.append({
                "fund_name": fund_name,
                "error": str(e)
            })
    
    db.commit()
    
    return {
        "success": True,
        "updated": len(updated),
        "errors": len(errors),
        "details": {
            "updated": updated,
            "errors": errors,
        }
    }


@router.post("/father-mutual-funds/enrich-holdings")
async def enrich_father_mutual_fund_holdings(db: Session = Depends(get_db)):
    """
    Enrich Father's mutual fund holdings with data from Kuvera API.
    Fetches: AUM, Expense Ratio, Fund Rating, Volatility, etc.
    """
    from app.modules.india_investments.kuvera_service import enrich_fund_data, get_isin_from_mfapi
    
    holdings = db.query(FatherMutualFundHolding).all()
    updated = []
    errors = []
    
    for holding in holdings:
        fund_name = holding.fund_name
        scheme_code = FATHER_FUND_SCHEME_CODES.get(fund_name) or holding.scheme_code
        
        if not scheme_code:
            errors.append({
                "fund_name": fund_name,
                "error": "No scheme code mapped"
            })
            continue
        
        try:
            # Get ISIN if not already stored
            isin = holding.isin
            if not isin:
                isin = get_isin_from_mfapi(scheme_code)
                if isin:
                    holding.isin = isin
                    holding.scheme_code = scheme_code
            
            if not isin:
                errors.append({
                    "fund_name": fund_name,
                    "error": "Could not get ISIN from MFapi"
                })
                continue
            
            # Fetch enriched data from Kuvera
            kuvera_data = enrich_fund_data(scheme_code=scheme_code, isin=isin)
            
            if not kuvera_data:
                errors.append({
                    "fund_name": fund_name,
                    "error": "No data returned from Kuvera API"
                })
                continue
            
            # Update holding with Kuvera data
            if kuvera_data.get('aum') is not None:
                holding.aum = Decimal(str(kuvera_data['aum']))
            if kuvera_data.get('expense_ratio') is not None:
                holding.expense_ratio = Decimal(str(kuvera_data['expense_ratio']))
            if kuvera_data.get('fund_rating') is not None:
                holding.fund_rating = kuvera_data['fund_rating']
            if kuvera_data.get('volatility') is not None:
                holding.volatility = Decimal(str(kuvera_data['volatility']))
            if kuvera_data.get('crisil_rating'):
                holding.crisil_rating = kuvera_data['crisil_rating']
            if kuvera_data.get('start_date'):
                holding.fund_start_date = kuvera_data['start_date']
            if kuvera_data.get('fund_category'):
                holding.fund_category = kuvera_data['fund_category']
            
            # Update returns from Kuvera if available (more recent than our calculated)
            returns = kuvera_data.get('returns', {})
            if returns.get('year_1') is not None:
                holding.return_1y = Decimal(str(returns['year_1']))
            if returns.get('year_3') is not None:
                holding.return_3y = Decimal(str(returns['year_3']))
            if returns.get('year_5') is not None:
                holding.return_5y = Decimal(str(returns['year_5']))
            
            holding.last_updated = datetime.utcnow()
            
            updated.append({
                "fund_name": fund_name,
                "isin": isin,
                "aum": kuvera_data.get('aum'),
                "expense_ratio": kuvera_data.get('expense_ratio'),
                "fund_rating": kuvera_data.get('fund_rating'),
                "volatility": kuvera_data.get('volatility'),
            })
            
        except Exception as e:
            errors.append({
                "fund_name": fund_name,
                "error": str(e)
            })
    
    db.commit()
    
    return {
        "success": True,
        "enriched": len(updated),
        "errors": len(errors),
        "details": {
            "enriched": updated,
            "errors": errors,
        }
    }


# ==================== Father's Stock Holdings ====================

class FatherStockHoldingCreate(BaseModel):
    investment_date: date
    symbol: str
    company_name: Optional[str] = None
    quantity: float
    average_price: Optional[float] = None
    initial_invested_amount: float
    amount_march_2025: Optional[float] = None
    current_price: Optional[float] = None
    current_amount: Optional[float] = None
    sector: Optional[str] = None
    notes: Optional[str] = None


@router.get("/father-stocks")
async def list_father_stocks(db: Session = Depends(get_db)):
    """List all of Father's stock holdings."""
    holdings = db.query(FatherStockHolding).order_by(
        FatherStockHolding.investment_date.desc()
    ).all()
    
    # Calculate totals
    total_invested = sum(float(h.initial_invested_amount or 0) for h in holdings)
    total_march_2025 = sum(float(h.amount_march_2025 or 0) for h in holdings)
    total_current = sum(float(h.current_amount or 0) for h in holdings)
    
    return {
        "holdings": [
            {
                "id": h.id,
                "investment_date": h.investment_date.isoformat() if h.investment_date else None,
                "symbol": h.symbol,
                "company_name": h.company_name,
                "quantity": float(h.quantity) if h.quantity else 0,
                "average_price": float(h.average_price) if h.average_price else None,
                "initial_invested_amount": float(h.initial_invested_amount or 0),
                "amount_march_2025": float(h.amount_march_2025) if h.amount_march_2025 else None,
                "current_price": float(h.current_price) if h.current_price else None,
                "current_amount": float(h.current_amount) if h.current_amount else None,
                "sector": h.sector,
                "notes": h.notes,
                "last_updated": h.last_updated.isoformat() if h.last_updated else None,
            }
            for h in holdings
        ],
        "summary": {
            "total_invested": total_invested,
            "total_march_2025": total_march_2025,
            "total_current": total_current,
            "total_gain_loss": total_march_2025 - total_invested if total_march_2025 else None,
            "count": len(holdings),
        }
    }


@router.post("/father-stocks")
async def create_father_stock(
    holding: FatherStockHoldingCreate,
    db: Session = Depends(get_db)
):
    """Create a new Father's stock holding."""
    new_holding = FatherStockHolding(
        investment_date=holding.investment_date,
        symbol=holding.symbol.upper(),
        company_name=holding.company_name,
        quantity=Decimal(str(holding.quantity)),
        average_price=Decimal(str(holding.average_price)) if holding.average_price else None,
        initial_invested_amount=Decimal(str(holding.initial_invested_amount)),
        amount_march_2025=Decimal(str(holding.amount_march_2025)) if holding.amount_march_2025 else None,
        current_price=Decimal(str(holding.current_price)) if holding.current_price else None,
        current_amount=Decimal(str(holding.current_amount)) if holding.current_amount else None,
        sector=holding.sector,
        notes=holding.notes,
    )
    
    db.add(new_holding)
    db.commit()
    db.refresh(new_holding)
    
    return {"success": True, "id": new_holding.id}


@router.put("/father-stocks/{holding_id}")
async def update_father_stock(
    holding_id: int,
    holding: FatherStockHoldingCreate,
    db: Session = Depends(get_db)
):
    """Update a Father's stock holding."""
    db_holding = db.query(FatherStockHolding).filter(
        FatherStockHolding.id == holding_id
    ).first()
    
    if not db_holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    
    db_holding.investment_date = holding.investment_date
    db_holding.symbol = holding.symbol.upper()
    db_holding.company_name = holding.company_name
    db_holding.quantity = Decimal(str(holding.quantity))
    db_holding.average_price = Decimal(str(holding.average_price)) if holding.average_price else None
    db_holding.initial_invested_amount = Decimal(str(holding.initial_invested_amount))
    db_holding.amount_march_2025 = Decimal(str(holding.amount_march_2025)) if holding.amount_march_2025 else None
    db_holding.current_price = Decimal(str(holding.current_price)) if holding.current_price else None
    db_holding.current_amount = Decimal(str(holding.current_amount)) if holding.current_amount else None
    db_holding.sector = holding.sector
    db_holding.notes = holding.notes
    db_holding.last_updated = datetime.utcnow()
    
    db.commit()
    
    return {"success": True, "id": holding_id}


@router.delete("/father-stocks/{holding_id}")
async def delete_father_stock(
    holding_id: int,
    db: Session = Depends(get_db)
):
    """Delete a Father's stock holding."""
    holding = db.query(FatherStockHolding).filter(
        FatherStockHolding.id == holding_id
    ).first()
    
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    
    db.delete(holding)
    db.commit()
    
    return {"success": True, "message": f"Holding {holding_id} deleted"}

