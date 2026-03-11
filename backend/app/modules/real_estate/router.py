"""
Real Estate API routes.
Handles properties, mortgages, valuations, equity tracking, and rental management.
All data is stored in and retrieved from the database.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel as PydanticModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.real_estate import services


# ── Pydantic request models ──

class RentalAgreementRequest(PydanticModel):
    property_id: int
    lease_start_date: date
    lease_end_date: date
    tenant_names: str
    monthly_rent: float
    monthly_hoa: Optional[float] = None
    security_deposit: Optional[float] = None
    notes: Optional[str] = None


class RentalExpenseRequest(PydanticModel):
    property_id: int
    tax_year: int
    category: str
    amount: float
    description: Optional[str] = None


class RentalIncomeRequest(PydanticModel):
    property_id: int
    tax_year: int
    annual_income: Optional[float] = None
    cost_of_property: Optional[float] = None

router = APIRouter()

# Property images (stored in frontend public folder)
PROPERTY_IMAGES = {
    "303 Hartstene Drive": [
        {
            "url": "/properties/303-hartstene/Photo-MLS-01.jpg",
            "caption": "Open concept kitchen with modern finishes",
            "type": "interior"
        },
        {
            "url": "/properties/303-hartstene/Photo-MLS-02.jpg",
            "caption": "Living room with floor-to-ceiling windows",
            "type": "interior"
        },
        {
            "url": "/properties/303-hartstene/Photo-MLS-03.jpg",
            "caption": "Waterfront community with walking trails",
            "type": "exterior"
        },
        {
            "url": "/properties/303-hartstene/Photo-MLS-05.jpg",
            "caption": "Bedroom with natural light",
            "type": "interior"
        },
        {
            "url": "/properties/303-hartstene/Photo-MLS-06.jpg",
            "caption": "Modern bathroom",
            "type": "interior"
        },
        {
            "url": "/properties/303-hartstene/Photo-MLS-07.jpg",
            "caption": "Additional living space",
            "type": "interior"
        },
        {
            "url": "/properties/303-hartstene/Photo-MLS-10 (1).jpg",
            "caption": "Interior view",
            "type": "interior"
        },
        {
            "url": "/properties/303-hartstene/Photo-MLS-11.jpg",
            "caption": "Home interior",
            "type": "interior"
        },
        {
            "url": "/properties/303-hartstene/Photo-MLS-12.jpg",
            "caption": "Room view",
            "type": "interior"
        },
        {
            "url": "/properties/303-hartstene/Photo-MLS-13.jpg",
            "caption": "Interior detail",
            "type": "interior"
        },
        {
            "url": "/properties/303-hartstene/Photo-MLS-14.jpg",
            "caption": "Home feature",
            "type": "interior"
        },
        {
            "url": "/properties/303-hartstene/Photo-MLS-36.jpg",
            "caption": "Property view",
            "type": "interior"
        },
        {
            "url": "/properties/303-hartstene/Photo-MLS-37.jpg",
            "caption": "Home exterior",
            "type": "exterior"
        },
        {
            "url": "/properties/303-hartstene/Photo-MLS-38.jpg",
            "caption": "Neighborhood view",
            "type": "exterior"
        },
        {
            "url": "/properties/303-hartstene/Photo-MLS-39.jpg",
            "caption": "Community amenities",
            "type": "exterior"
        },
        {
            "url": "/properties/303-hartstene/Photo-MLS-41.jpg",
            "caption": "Bay trail access",
            "type": "exterior"
        }
    ]
}

# Property highlights (enrichment data)
PROPERTY_HIGHLIGHTS = {
    "303 Hartstene Drive": [
        "Waterfront community with walking trails",
        "Near Oracle headquarters and tech corridor",
        "Excellent Redwood Shores schools",
        "Minutes from SFO and 101",
        "HOA maintained common areas"
    ]
}


@router.get("/properties")
async def list_properties(db: Session = Depends(get_db)):
    """List all real estate properties from database."""
    summary = services.get_property_summary(db)
    
    # Enrich with images and highlights
    for prop in summary['properties']:
        prop['images'] = PROPERTY_IMAGES.get(prop['address'], [])
        prop['highlights'] = PROPERTY_HIGHLIGHTS.get(prop['address'], [])
    
    return {
        "properties": summary['properties'],
        "total_value": summary['total_value'],
        "total_equity": summary['total_equity'],
        "total_mortgage_balance": summary['total_mortgage_balance'],
        "property_count": summary['property_count']
    }


@router.get("/properties/{property_id}")
async def get_property_details(property_id: int, db: Session = Depends(get_db)):
    """Get full details for a property including mortgage and valuation history."""
    detail = services.get_property_detail(db, property_id)
    
    if not detail:
        raise HTTPException(status_code=404, detail="Property not found")
    
    # Enrich with images, highlights, and external links
    prop = detail['property']
    prop['images'] = PROPERTY_IMAGES.get(prop['address'], [])
    prop['highlights'] = PROPERTY_HIGHLIGHTS.get(prop['address'], [])
    
    # Add Zillow URL if it's the Hartstene property
    if "Hartstene" in prop['address']:
        prop['zillow_url'] = "https://www.zillow.com/homedetails/303-Hartstene-Dr-Redwood-City-CA-94065/2079949221_zpid/"
        prop['valuation_source'] = "Zillow Zestimate"
        prop['stories'] = 3
        prop['parking'] = "2-car garage"
        prop['property_style'] = "Contemporary Townhome"
    
    return detail


@router.post("/properties")
async def create_property(db: Session = Depends(get_db)):
    """Add a new property."""
    return {"property": None, "message": "Property creation not implemented yet"}


@router.get("/mortgages")
async def list_mortgages(db: Session = Depends(get_db)):
    """List all mortgages."""
    # Query for active mortgages
    from app.modules.real_estate.models import Mortgage
    mortgages = db.query(Mortgage).filter(Mortgage.is_active == 'Y').all()
    
    if not mortgages:
        return {"mortgages": [], "message": "No active mortgages - all properties are fully paid off"}
    
    return {
        "mortgages": [
            {
                "id": m.id,
                "property_id": m.property_id,
                "lender": m.lender,
                "current_balance": float(m.current_balance) if m.current_balance else 0,
                "interest_rate": float(m.interest_rate) if m.interest_rate else None,
                "monthly_payment": float(m.monthly_payment) if m.monthly_payment else None,
            }
            for m in mortgages
        ]
    }


@router.get("/mortgages/{mortgage_id}")
async def get_mortgage_details(mortgage_id: int, db: Session = Depends(get_db)):
    """Get mortgage details including amortization schedule."""
    from app.modules.real_estate.models import Mortgage
    mortgage = db.query(Mortgage).filter(Mortgage.id == mortgage_id).first()
    
    if not mortgage:
        return {
            "mortgage": None,
            "remaining_balance": 0,
            "payments": [],
            "amortization": [],
            "message": "Mortgage not found"
        }
    
    return {
        "mortgage": {
            "id": mortgage.id,
            "lender": mortgage.lender,
            "original_amount": float(mortgage.original_amount) if mortgage.original_amount else 0,
            "current_balance": float(mortgage.current_balance) if mortgage.current_balance else 0,
            "interest_rate": float(mortgage.interest_rate) if mortgage.interest_rate else None,
        },
        "remaining_balance": float(mortgage.current_balance) if mortgage.current_balance else 0,
        "payments": [],
        "amortization": [],
    }


@router.get("/equity-summary")
async def get_equity_summary(db: Session = Depends(get_db)):
    """Get total real estate equity across all properties."""
    summary = services.get_property_summary(db)
    
    return {
        "total_property_value": summary['total_value'],
        "total_mortgage_balance": summary['total_mortgage_balance'],
        "total_equity": summary['total_equity'],
        "by_property": [
            {
                "id": p['id'],
                "address": p['full_address'],
                "value": p['value'],
                "mortgage_balance": p['mortgage_balance'],
                "equity": p['equity'],
                "equity_percent": p['equity_percent']
            }
            for p in summary['properties']
        ]
    }


@router.get("/valuations")
async def list_valuations(
    db: Session = Depends(get_db),
    property_id: Optional[int] = None
):
    """List property valuations/appraisals."""
    if property_id:
        prop = services.get_property_by_id(db, property_id)
        if not prop:
            raise HTTPException(status_code=404, detail="Property not found")
        
        valuations = services.get_valuations(db, property_id)
        
        purchase_price = float(prop.purchase_price) if prop.purchase_price else 0
        current_value = float(prop.current_value) if prop.current_value else 0
        total_appreciation = current_value - purchase_price
        appreciation_percent = (total_appreciation / purchase_price * 100) if purchase_price > 0 else 0
        
        return {
            "valuations": [
                {"date": v.valuation_date.isoformat(), "value": float(v.value), "source": v.valuation_source}
                for v in valuations
            ],
            "property_id": property_id,
            "current_value": current_value,
            "purchase_price": purchase_price,
            "total_appreciation": total_appreciation,
            "appreciation_percent": round(appreciation_percent, 2)
        }
    else:
        # Return valuations for all properties
        properties = services.get_all_properties(db)
        all_valuations = []
        
        for prop in properties:
            valuations = services.get_valuations(db, prop.id)
            all_valuations.extend([
                {
                    "property_id": prop.id,
                    "address": prop.address,
                    "date": v.valuation_date.isoformat(),
                    "value": float(v.value),
                    "source": v.valuation_source
                }
                for v in valuations
            ])
        
        return {"valuations": all_valuations}


@router.post("/seed")
async def seed_property_data(db: Session = Depends(get_db)):
    """
    Seed the real estate property data into the database.
    This is idempotent - can be called multiple times without creating duplicates.
    """
    stats = services.seed_hartstene_property(db)
    return {
        "status": "success",
        "message": "Property data seeded successfully",
        "stats": stats
    }


# ── Rental Agreements ─────────────────────────────────────────

@router.get("/rental-agreements")
async def list_rental_agreements(
    property_id: int,
    db: Session = Depends(get_db),
):
    """List all rental agreements for a property."""
    agreements = services.get_rental_agreements(db, property_id)
    return {"agreements": agreements}


@router.post("/rental-agreements")
async def create_or_update_rental_agreement(
    req: RentalAgreementRequest,
    db: Session = Depends(get_db),
):
    """Create or update a rental agreement."""
    agreement = services.upsert_rental_agreement(
        db=db,
        property_id=req.property_id,
        lease_start_date=req.lease_start_date,
        lease_end_date=req.lease_end_date,
        tenant_names=req.tenant_names,
        monthly_rent=Decimal(str(req.monthly_rent)),
        monthly_hoa=Decimal(str(req.monthly_hoa)) if req.monthly_hoa is not None else None,
        security_deposit=Decimal(str(req.security_deposit)) if req.security_deposit is not None else None,
        notes=req.notes,
    )
    return {"status": "success", "id": agreement.id}


# ── Rental Expenses ───────────────────────────────────────────

@router.get("/rental-expenses")
async def list_rental_expenses(
    property_id: int,
    tax_year: int,
    db: Session = Depends(get_db),
):
    """Get expenses for a property and year."""
    expenses = services.get_expenses_by_year(db, property_id, tax_year)
    return {"expenses": expenses, "categories": services.EXPENSE_CATEGORIES}


@router.post("/rental-expenses")
async def create_or_update_expense(
    req: RentalExpenseRequest,
    db: Session = Depends(get_db),
):
    """Create or update a rental expense."""
    expense = services.upsert_expense(
        db=db,
        property_id=req.property_id,
        tax_year=req.tax_year,
        category=req.category,
        amount=Decimal(str(req.amount)),
        description=req.description,
    )
    return {"status": "success", "id": expense.id}


@router.delete("/rental-expenses/{expense_id}")
async def remove_expense(expense_id: int, db: Session = Depends(get_db)):
    """Delete an expense."""
    if not services.delete_expense(db, expense_id):
        raise HTTPException(status_code=404, detail="Expense not found")
    return {"status": "deleted"}


# ── Rental Income / Annual Summary ────────────────────────────

@router.post("/rental-income")
async def set_annual_income(
    req: RentalIncomeRequest,
    db: Session = Depends(get_db),
):
    """Set annual income and/or cost of property for a tax year."""
    summary = services.upsert_annual_income(
        db=db,
        property_id=req.property_id,
        tax_year=req.tax_year,
        annual_income=Decimal(str(req.annual_income)) if req.annual_income is not None else None,
        cost_of_property=Decimal(str(req.cost_of_property)) if req.cost_of_property is not None else None,
    )
    return {"status": "success", "id": summary.id}


@router.get("/rental-summary")
async def get_rental_summary(
    property_id: int,
    tax_year: int,
    db: Session = Depends(get_db),
):
    """Get annual income/expense summary for a property."""
    return services.get_annual_summary(db, property_id, tax_year)


@router.post("/rental-income/project")
async def project_rental_income(db: Session = Depends(get_db)):
    """Project rental_monthly_income rows from active rental agreements.
    Creates rows for months covered by agreements that don't already have income data."""
    stats = services.project_rental_income_from_agreements(db)
    return {"status": "success", **stats}


# ── Rental Documents ──────────────────────────────────────────

@router.get("/rental-documents")
async def list_rental_documents(
    property_id: int,
    db: Session = Depends(get_db),
):
    """List all rental documents for a property."""
    docs = services.get_rental_documents(db, property_id)
    return {"documents": docs}


@router.post("/rental-documents/{property_id}")
async def upload_rental_doc(
    property_id: int,
    file: UploadFile = File(...),
    document_type: str = Form("other"),
    tax_year: Optional[int] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Upload a rental document."""
    try:
        doc = await services.upload_rental_document(
            db=db,
            property_id=property_id,
            file=file,
            document_type=document_type,
            tax_year=tax_year,
            notes=notes,
        )
        return {
            "status": "success",
            "id": doc.id,
            "file_name": doc.file_name,
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/rental-documents/{doc_id}/download")
async def download_rental_doc(doc_id: int, db: Session = Depends(get_db)):
    """Download a rental document."""
    file_path = services.get_rental_document_path(db, doc_id)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream",
    )


@router.delete("/rental-documents/{doc_id}")
async def remove_rental_doc(doc_id: int, db: Session = Depends(get_db)):
    """Delete a rental document."""
    if not services.delete_rental_document(db, doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted"}
