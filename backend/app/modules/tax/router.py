"""
Tax Center API routes.
Handles income taxes and property taxes with historical data.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
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
    
    # Add forecast if requested and no 2025 return exists
    if include_forecast:
        has_2025 = any(tr.tax_year == 2025 for tr in returns)
        if not has_2025:
            try:
                forecast = calculate_tax_forecast(db, forecast_year=2025, base_year=2024)
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
                    year=2025,
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
                logger.error(f"Failed to generate 2025 forecast: {str(e)}", exc_info=True)
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
        
        return {
            "year": forecast["tax_year"],
            "agi": agi,
            "federal_tax": forecast.get("federal_tax", 0),
            "federal_withheld": None,  # Forecast doesn't have withheld amounts
            "federal_owed": None,
            "federal_refund": None,
            "state_tax": forecast.get("state_tax", 0),
            "state_withheld": None,
            "state_owed": None,
            "state_refund": None,
            "other_tax": other_tax,
            "total_tax": total_tax,
            "effective_rate": effective_rate,
            "filing_status": forecast.get("filing_status"),
            "is_forecast": True,
            "details": forecast.get("details", {}),
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
