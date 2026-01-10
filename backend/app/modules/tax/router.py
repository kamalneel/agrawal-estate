"""
Tax Center API routes.
Handles income taxes and property taxes with historical data.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from decimal import Decimal
import json
from io import BytesIO

from app.core.database import get_db
from app.core.auth import get_current_user
from app.modules.tax.models import IncomeTaxReturn
from app.modules.tax.planning import get_tax_planning_analysis, TaxPlanningAnalysis
from app.modules.tax.forecast import calculate_tax_forecast
from app.modules.tax.form_generator import generate_tax_forms, TaxFormPackage
from app.modules.tax.pdf_generator import (
    generate_form_1040_pdf,
    generate_california_540_pdf,
    generate_tax_forms_pdf
)
from app.modules.tax.cost_basis_service import CostBasisService
from app.modules.tax.models import StockLot, StockLotSale

router = APIRouter()


class TaxReturnSummary(BaseModel):
    """Summary of a tax return."""
    year: int
    agi: float
    federal_tax: float
    state_tax: float
    other_tax: float
    total_tax: float
    effective_rate: Optional[float] = None
    federal_rate: Optional[float] = None
    state_rate: Optional[float] = None
    other_rate: Optional[float] = None


class TaxHistory(BaseModel):
    """Historical tax data."""
    years: List[TaxReturnSummary]
    total_federal: float
    total_state: float
    total_other: float
    total_taxes: float
    average_effective_rate: float


def _calculate_other_taxes(details_json: Optional[str]) -> float:
    """Calculate other taxes from details JSON."""
    if not details_json:
        return 0
    
    try:
        details = json.loads(details_json)
    except:
        return 0
    
    other_tax = 0
    
    # Sum payroll taxes (Social Security + Medicare + SDI)
    payroll = details.get("payroll_taxes", {})
    if isinstance(payroll, dict):
        # Direct dict format: {"social_security": X, "medicare_withheld": Y, "sdi": Z}
        other_tax += payroll.get("social_security", 0) or 0
        other_tax += payroll.get("medicare_withheld", 0) or 0
        other_tax += payroll.get("medicare", 0) or 0  # Alternative key name
        other_tax += payroll.get("sdi", 0) or 0
    elif isinstance(payroll, list):
        # List of employer entries format
        for p in payroll:
            if isinstance(p, dict):
                other_tax += p.get("social_security", 0) or 0
                other_tax += p.get("medicare_withheld", 0) or 0
                other_tax += p.get("medicare", 0) or 0
                other_tax += p.get("sdi", 0) or 0
    
    # Sum additional taxes (NIIT, AMT, etc.)
    additional = details.get("additional_taxes", {})
    if isinstance(additional, dict):
        other_tax += additional.get("niit", 0) or 0
        other_tax += additional.get("amt", 0) or 0
        other_tax += additional.get("self_employment", 0) or 0
    
    return other_tax


@router.get("/returns", response_model=TaxHistory)
async def get_tax_returns(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    include_forecast: bool = Query(default=True, description="Include forecast for 2025")
):
    """Get all tax returns with summary."""
    returns = db.query(IncomeTaxReturn).order_by(IncomeTaxReturn.tax_year.desc()).all()
    
    years = []
    total_federal = 0
    total_state = 0
    total_other = 0
    total_agi = 0
    
    for tr in returns:
        federal = tr.federal_tax or 0
        state = tr.state_tax or 0
        agi = tr.agi or 0
        other = _calculate_other_taxes(tr.details_json)
        total = federal + state + other
        
        # Calculate rates
        federal_rate = (federal / agi * 100) if agi > 0 else 0
        state_rate = (state / agi * 100) if agi > 0 else 0
        other_rate = (other / agi * 100) if agi > 0 else 0
        effective_rate = (total / agi * 100) if agi > 0 else 0
        
        years.append(TaxReturnSummary(
            year=tr.tax_year,
            agi=agi,
            federal_tax=federal,
            state_tax=state,
            other_tax=other,
            total_tax=total,
            effective_rate=round(effective_rate, 2),
            federal_rate=round(federal_rate, 1),
            state_rate=round(state_rate, 1),
            other_rate=round(other_rate, 1),
        ))
        
        total_federal += federal
        total_state += state
        total_other += other
        total_agi += agi
    
    # Add forecasts for 2025 and 2026 if requested
    if include_forecast:
        forecast_years = [2026, 2025]  # Add in reverse order so 2025 appears before 2026
        for forecast_year in forecast_years:
            has_year = any(tr.tax_year == forecast_year for tr in returns)
            if not has_year:
                try:
                    # Use 2024 as base year for deductions
                    base_year = 2024
                    forecast = calculate_tax_forecast(db, forecast_year=forecast_year, base_year=base_year)
                    federal = forecast.get("federal_tax", 0)
                    state = forecast.get("state_tax", 0)
                    other = forecast.get("other_tax", 0)
                    agi = forecast.get("agi", 0)
                    total = federal + state + other
                    
                    federal_rate = (federal / agi * 100) if agi > 0 else 0
                    state_rate = (state / agi * 100) if agi > 0 else 0
                    other_rate = (other / agi * 100) if agi > 0 else 0
                    effective_rate = (total / agi * 100) if agi > 0 else 0
                    
                    years.insert(0, TaxReturnSummary(
                        year=forecast_year,
                        agi=agi,
                        federal_tax=federal,
                        state_tax=state,
                        other_tax=other,
                        total_tax=total,
                        effective_rate=round(effective_rate, 2),
                        federal_rate=round(federal_rate, 1),
                        state_rate=round(state_rate, 1),
                        other_rate=round(other_rate, 1),
                    ))
                except Exception as e:
                    # Log the error for debugging
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to generate {forecast_year} forecast: {str(e)}", exc_info=True)
                    # If forecast fails, just skip it
                    pass
    
    total_taxes = total_federal + total_state + total_other
    avg_rate = (total_taxes / total_agi * 100) if total_agi > 0 else 0
    
    return TaxHistory(
        years=years,
        total_federal=total_federal,
        total_state=total_state,
        total_other=total_other,
        total_taxes=total_taxes,
        average_effective_rate=round(avg_rate, 2),
    )


@router.get("/returns/{year}")
async def get_tax_return_year(
    year: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Get detailed tax return for a specific year."""
    tr = db.query(IncomeTaxReturn).filter(IncomeTaxReturn.tax_year == year).first()
    
    if not tr:
        raise HTTPException(status_code=404, detail=f"No tax return found for {year}")
    
    federal = tr.federal_tax or 0
    state = tr.state_tax or 0
    agi = tr.agi or 0
    
    # Parse details
    details = {}
    if tr.details_json:
        try:
            details = json.loads(tr.details_json)
        except:
            pass
    
    other = _calculate_other_taxes(tr.details_json)
    total = federal + state + other
    effective_rate = (total / agi * 100) if agi > 0 else 0
    
    return {
        "year": tr.tax_year,
        "agi": agi,
        "federal_tax": federal,
        "federal_withheld": tr.federal_withheld,
        "federal_owed": tr.federal_owed,
        "federal_refund": tr.federal_refund,
        "state_tax": state,
        "state_withheld": tr.state_withheld,
        "state_owed": tr.state_owed,
        "state_refund": tr.state_refund,
        "other_tax": other,
        "total_tax": total,
        "effective_rate": round(effective_rate, 2),
        "filing_status": tr.filing_status,
        "details": details,
    }


@router.get("/planning/analysis", response_model=TaxPlanningAnalysis)
async def get_planning_analysis(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Get tax planning analysis and recommendations."""
    return get_tax_planning_analysis(db)


@router.get("/forecast/{year}")
async def get_tax_forecast(
    year: int,
    base_year: Optional[int] = Query(default=2024, description="Base year for deductions"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get tax forecast for a given year.
    Uses historical tax data (deductions, filing status) and projected income.
    """
    try:
        forecast = calculate_tax_forecast(db, forecast_year=year, base_year=base_year)
        
        # Format response similar to get_tax_return_year
        other_tax = forecast.get("other_tax", 0)
        total_tax = forecast.get("total_tax", 0)
        agi = forecast.get("agi", 0)
        effective_rate = forecast.get("effective_rate", 0)
        
        # Get W-2 withholding info
        w2_withholding = forecast.get("w2_withholding", {})
        
        return {
            "year": forecast["tax_year"],
            "agi": agi,
            "federal_tax": forecast.get("federal_tax", 0),
            "federal_withheld": w2_withholding.get("federal"),
            "federal_owed": None,
            "federal_refund": None,
            "state_tax": forecast.get("state_tax", 0),
            "state_withheld": w2_withholding.get("state"),
            "state_owed": None,
            "state_refund": None,
            "other_tax": other_tax,
            "total_tax": total_tax,
            "effective_rate": effective_rate,
            "filing_status": forecast.get("filing_status"),
            "is_forecast": True,
            "details": forecast.get("details", {}),
            # Payment schedule for quarterly estimated taxes
            "payment_schedule": forecast.get("payment_schedule", []),
            "w2_withholding": w2_withholding,
            "estimated_tax_needed": forecast.get("estimated_tax_needed", 0),
            "safe_harbor": forecast.get("safe_harbor", {}),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating forecast: {str(e)}")


@router.get("/forms/{year}", response_model=TaxFormPackage)
async def get_tax_forms(
    year: int,
    base_year: Optional[int] = Query(default=2024, description="Base year for deductions"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Generate official IRS Form 1040 and California Form 540 for comparison.

    Returns complete tax form package with:
    - Form 1040 (U.S. Individual Income Tax Return)
    - Schedule 1 (Additional Income and Adjustments)
    - Schedule E (Rental Income) if applicable
    - Schedule D (Capital Gains) if applicable
    - California Form 540

    Use this to compare against tax consultant's filed return line-by-line.
    """
    try:
        forms = generate_tax_forms(db, tax_year=year, base_year=base_year)
        return forms
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating tax forms: {str(e)}")


@router.get("/forms/{year}/pdf/1040")
async def download_form_1040_pdf(
    year: int,
    base_year: Optional[int] = Query(default=2024, description="Base year for deductions"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Download IRS Form 1040 as PDF.

    Returns a professional PDF version of Form 1040 matching the official IRS form layout.
    """
    try:
        forms = generate_tax_forms(db, tax_year=year, base_year=base_year)

        # Generate PDF
        buffer = BytesIO()
        generate_form_1040_pdf(forms.form_1040, buffer)
        buffer.seek(0)

        # Return as downloadable PDF
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=Form_1040_{year}_Forecast.pdf"
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating PDF: {str(e)}")


@router.get("/forms/{year}/pdf/540")
async def download_form_540_pdf(
    year: int,
    base_year: Optional[int] = Query(default=2024, description="Base year for deductions"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Download California Form 540 as PDF.

    Returns a professional PDF version of CA Form 540 matching the official state form layout.
    """
    try:
        forms = generate_tax_forms(db, tax_year=year, base_year=base_year)

        if not forms.california_540:
            raise HTTPException(status_code=404, detail="California Form 540 not available")

        # Generate PDF
        buffer = BytesIO()
        generate_california_540_pdf(forms.california_540, buffer)
        buffer.seek(0)

        # Return as downloadable PDF
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=CA_Form_540_{year}_Forecast.pdf"
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating PDF: {str(e)}")


@router.get("/forms/{year}/pdf")
async def download_all_forms_pdf(
    year: int,
    base_year: Optional[int] = Query(default=2024, description="Base year for deductions"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Download complete tax form package as PDF.

    Returns a multi-page PDF containing Form 1040 and California Form 540.
    """
    try:
        forms = generate_tax_forms(db, tax_year=year, base_year=base_year)

        # Generate combined PDF
        buffer = generate_tax_forms_pdf(forms)

        # Return as downloadable PDF
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=Tax_Forms_{year}_Forecast.pdf"
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating PDF: {str(e)}")


# ==================== Cost Basis Tracking Endpoints ====================

@router.get("/cost-basis/{year}")
async def get_capital_gains_summary(
    year: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get capital gains summary for a tax year.

    Returns realized gains broken down by short-term vs long-term,
    total proceeds, cost basis, and per-symbol breakdown.
    """
    service = CostBasisService(db)
    return service.get_capital_gains_summary(year)


@router.get("/cost-basis/{year}/realized")
async def get_realized_gains(
    year: int,
    symbol: Optional[str] = Query(default=None),
    is_long_term: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get all realized capital gains transactions for a tax year.

    Query parameters:
    - symbol: Filter by stock symbol
    - is_long_term: Filter by long-term (true) or short-term (false)
    """
    service = CostBasisService(db)
    sales = service.get_realized_gains(year, symbol=symbol, is_long_term=is_long_term)

    # Convert to dict format
    results = []
    for sale in sales:
        lot = db.query(StockLot).filter(StockLot.lot_id == sale.lot_id).first()
        results.append({
            "sale_id": sale.sale_id,
            "symbol": lot.symbol if lot else None,
            "sale_date": sale.sale_date.isoformat(),
            "purchase_date": lot.purchase_date.isoformat() if lot else None,
            "quantity_sold": float(sale.quantity_sold),
            "proceeds": float(sale.proceeds),
            "proceeds_per_share": float(sale.proceeds_per_share),
            "cost_basis": float(sale.cost_basis),
            "gain_loss": float(sale.gain_loss),
            "holding_period_days": sale.holding_period_days,
            "is_long_term": sale.is_long_term,
            "wash_sale": sale.wash_sale,
            "notes": sale.notes
        })

    return {
        "tax_year": year,
        "transactions": results,
        "count": len(results)
    }


@router.get("/cost-basis/lots")
async def get_stock_lots(
    symbol: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default="open", description="'open', 'closed', or 'all'"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get stock lots (open or closed positions).

    Query parameters:
    - symbol: Filter by stock symbol
    - status: 'open' (default), 'closed', or 'all'
    """
    service = CostBasisService(db)

    if status == "closed":
        lots = service.get_closed_lots(symbol=symbol)
    elif status == "all":
        query = db.query(StockLot)
        if symbol:
            query = query.filter(StockLot.symbol == symbol.upper())
        lots = query.order_by(StockLot.purchase_date.desc()).all()
    else:  # open
        lots = service.get_open_lots(symbol=symbol)

    results = []
    for lot in lots:
        results.append({
            "lot_id": lot.lot_id,
            "symbol": lot.symbol,
            "purchase_date": lot.purchase_date.isoformat(),
            "quantity": float(lot.quantity),
            "quantity_remaining": float(lot.quantity_remaining),
            "cost_basis": float(lot.cost_basis),
            "cost_per_share": float(lot.cost_per_share),
            "account_id": lot.account_id,
            "source": lot.source,
            "status": lot.status,
            "lot_method": lot.lot_method,
            "notes": lot.notes
        })

    return {
        "lots": results,
        "count": len(results)
    }


@router.get("/cost-basis/unrealized")
async def get_unrealized_gains(
    symbol: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get unrealized gains for open positions.

    Note: This endpoint requires current market prices.
    Currently returns placeholder data. Will be enhanced to fetch live prices.
    """
    service = CostBasisService(db)

    # TODO: Fetch current prices from market data API
    # For now, return 0 to indicate this feature needs price data
    current_prices = {}

    lots = service.get_open_lots(symbol=symbol)

    # Return lot information without unrealized gains until we have price data
    results = []
    for lot in lots:
        results.append({
            "symbol": lot.symbol,
            "quantity_remaining": float(lot.quantity_remaining),
            "cost_basis": float(lot.cost_per_share * lot.quantity_remaining),
            "cost_per_share": float(lot.cost_per_share),
            "purchase_date": lot.purchase_date.isoformat(),
            "note": "Current price data needed for unrealized gain calculation"
        })

    return {
        "open_positions": results,
        "note": "Market data integration required for unrealized gains"
    }


@router.post("/cost-basis/lots")
async def create_stock_lot(
    lot_data: Dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Create a new stock lot manually.

    Request body:
    {
        "symbol": "AAPL",
        "purchase_date": "2024-01-15",
        "quantity": 100,
        "cost_basis": 18500.00,
        "source": "manual",
        "account_id": "my_account",
        "lot_method": "FIFO",
        "notes": "Optional notes"
    }
    """
    from datetime import datetime

    service = CostBasisService(db)

    try:
        lot = service.create_lot(
            symbol=lot_data["symbol"],
            purchase_date=datetime.fromisoformat(lot_data["purchase_date"]).date(),
            quantity=Decimal(str(lot_data["quantity"])),
            cost_basis=Decimal(str(lot_data["cost_basis"])),
            source=lot_data.get("source", "manual"),
            account_id=lot_data.get("account_id"),
            lot_method=lot_data.get("lot_method", "FIFO"),
            notes=lot_data.get("notes")
        )

        return {
            "success": True,
            "lot_id": lot.lot_id,
            "message": f"Created lot for {lot_data['quantity']} shares of {lot_data['symbol']}"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cost-basis/sales")
async def process_stock_sale(
    sale_data: Dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Process a stock sale (matches to lots and records gain/loss).

    Request body:
    {
        "symbol": "AAPL",
        "sale_date": "2025-01-10",
        "quantity_sold": 50,
        "proceeds": 9500.00,
        "source": "manual",
        "account_id": "my_account",
        "lot_method": "FIFO",
        "notes": "Optional notes"
    }
    """
    from datetime import datetime
    from decimal import Decimal

    service = CostBasisService(db)

    try:
        sales = service.process_sale(
            symbol=sale_data["symbol"],
            sale_date=datetime.fromisoformat(sale_data["sale_date"]).date(),
            quantity_sold=Decimal(str(sale_data["quantity_sold"])),
            proceeds=Decimal(str(sale_data["proceeds"])),
            source=sale_data.get("source", "manual"),
            account_id=sale_data.get("account_id"),
            lot_method=sale_data.get("lot_method", "FIFO"),
            notes=sale_data.get("notes")
        )

        total_gain = sum(float(s.gain_loss) for s in sales)

        return {
            "success": True,
            "num_lots_matched": len(sales),
            "total_gain_loss": total_gain,
            "sales": [
                {
                    "sale_id": s.sale_id,
                    "lot_id": s.lot_id,
                    "quantity": float(s.quantity_sold),
                    "gain_loss": float(s.gain_loss),
                    "is_long_term": s.is_long_term
                }
                for s in sales
            ],
            "message": f"Processed sale of {sale_data['quantity_sold']} shares of {sale_data['symbol']}"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cost-basis/import/robinhood")
async def import_robinhood_transactions(
    transactions: List[Dict[str, Any]],
    account_id: str = Query(default="robinhood_main"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Import Robinhood transactions in bulk.

    Request body: Array of transactions:
    [
        {
            "symbol": "AAPL",
            "date": "2024-01-15",
            "type": "buy",
            "quantity": 100,
            "amount": 18500.00
        },
        ...
    ]
    """
    from datetime import datetime

    service = CostBasisService(db)

    # Convert date strings to date objects
    for txn in transactions:
        if isinstance(txn["date"], str):
            txn["date"] = datetime.fromisoformat(txn["date"]).date()

    try:
        lots_created, sales_created = service.import_robinhood_transactions(
            transactions, account_id=account_id
        )

        return {
            "success": True,
            "lots_created": lots_created,
            "sales_created": sales_created,
            "transactions_processed": len(transactions),
            "message": f"Imported {len(transactions)} transactions"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cost-basis/sync")
async def sync_from_investment_transactions(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    clear_existing: bool = Query(default=False, description="Clear existing lots before syncing")
):
    """
    Sync Cost Basis Tracker from existing investment_transactions table.
    
    This imports all BUY and SELL transactions from your investment accounts
    into the Cost Basis Tracker for accurate gain/loss calculations.
    """
    from sqlalchemy import text
    from datetime import datetime
    from decimal import Decimal
    
    service = CostBasisService(db)
    
    # Optionally clear existing data
    if clear_existing:
        db.query(StockLotSale).delete()
        db.query(StockLot).delete()
        db.commit()
    
    # Query all BUY and SELL transactions from taxable accounts
    # Exclude retirement accounts (IRA, Roth, 401k, HSA)
    non_taxable_types = ['ira', 'roth_ira', 'traditional_ira', '401k', 'hsa', 'retirement']
    
    query = text("""
        SELECT 
            it.transaction_date,
            it.transaction_type,
            it.symbol,
            it.quantity,
            it.amount,
            it.price_per_share,
            it.account_id,
            it.source
        FROM investment_transactions it
        JOIN investment_accounts ia ON it.account_id = ia.account_id AND it.source = ia.source
        WHERE it.transaction_type IN ('BUY', 'BOUGHT', 'SELL', 'SOLD')
          AND it.symbol IS NOT NULL 
          AND it.symbol != ''
          AND it.quantity > 0
          AND LOWER(COALESCE(ia.account_type, '')) NOT IN :non_taxable
        ORDER BY it.transaction_date ASC
    """)
    
    result = db.execute(query, {"non_taxable": tuple(non_taxable_types)}).fetchall()
    
    lots_created = 0
    sales_created = 0
    errors = []
    
    for row in result:
        try:
            txn_date = row.transaction_date
            txn_type = row.transaction_type.upper()
            symbol = row.symbol.upper()
            quantity = Decimal(str(abs(row.quantity or 0)))
            amount = Decimal(str(abs(row.amount or 0)))
            account_id = row.account_id or "unknown"
            source = row.source or "unknown"
            
            if quantity <= 0 or amount <= 0:
                continue
            
            if txn_type in ["BUY", "BOUGHT"]:
                # Check if lot already exists (avoid duplicates)
                existing = db.query(StockLot).filter(
                    StockLot.symbol == symbol,
                    StockLot.purchase_date == txn_date,
                    StockLot.quantity == quantity,
                    StockLot.cost_basis == amount
                ).first()
                
                if not existing:
                    service.create_lot(
                        symbol=symbol,
                        purchase_date=txn_date,
                        quantity=quantity,
                        cost_basis=amount,
                        source=source,
                        account_id=account_id,
                        lot_method="FIFO"
                    )
                    lots_created += 1
                    
            elif txn_type in ["SELL", "SOLD"]:
                # Check if sale already exists
                existing = db.query(StockLotSale).filter(
                    StockLotSale.sale_date == txn_date,
                    StockLotSale.quantity_sold == quantity,
                    StockLotSale.proceeds == amount
                ).first()
                
                if not existing:
                    try:
                        sales = service.process_sale(
                            symbol=symbol,
                            sale_date=txn_date,
                            quantity_sold=quantity,
                            proceeds=amount,
                            source=source,
                            account_id=account_id,
                            lot_method="FIFO"
                        )
                        sales_created += len(sales)
                    except ValueError as e:
                        # No matching lots found - this can happen if buy was before our data
                        errors.append(f"{symbol} on {txn_date}: {str(e)}")
                        
        except Exception as e:
            errors.append(f"Error processing {row}: {str(e)}")
            db.rollback()
    
    return {
        "success": True,
        "lots_created": lots_created,
        "sales_created": sales_created,
        "transactions_processed": len(result),
        "errors": errors[:10] if errors else [],  # Limit errors shown
        "total_errors": len(errors),
        "message": f"Synced {lots_created} lots and {sales_created} sales from investment transactions"
    }


# Property Tax Endpoints (original)

@router.get("/properties")
async def list_tax_properties(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """List all properties with tax records."""
    return {"properties": []}


@router.get("/properties/{property_id}")
async def get_property_taxes(
    property_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Get tax history for a specific property."""
    return {"property": None, "tax_records": []}


@router.get("/records")
async def list_tax_records(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    property_id: Optional[int] = None,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None
):
    """List property tax records with optional filters."""
    return {"records": [], "total": 0}


@router.get("/summary")
async def get_tax_summary(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    year: Optional[int] = None
):
    """Get tax summary across all properties."""
    return {
        "total_assessed_value": 0,
        "total_tax_paid": 0,
        "by_property": [],
        "year_over_year": []
    }


@router.get("/history/{property_id}")
async def get_tax_history_chart(
    property_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    years: int = Query(default=20, le=30)
):
    """Get tax history data formatted for charting."""
    return {
        "property_id": property_id,
        "years": [],
        "assessed_values": [],
        "tax_amounts": []
    }
