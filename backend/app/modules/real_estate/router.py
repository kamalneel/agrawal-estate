"""
Real Estate API routes.
Handles properties, mortgages, valuations, and equity tracking.
All data is stored in and retrieved from the database.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.modules.real_estate import services

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
