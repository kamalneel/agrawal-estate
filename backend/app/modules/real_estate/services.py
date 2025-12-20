"""
Real Estate Services - Database operations for properties and valuations.
"""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.modules.real_estate.models import Property, PropertyValuation, Mortgage


def get_property_by_address(db: Session, address: str) -> Optional[Property]:
    """Get a property by address (case-insensitive partial match)."""
    return db.query(Property).filter(
        Property.address.ilike(f"%{address}%")
    ).first()


def get_property_by_id(db: Session, property_id: int) -> Optional[Property]:
    """Get a property by ID."""
    return db.query(Property).filter(Property.id == property_id).first()


def get_all_properties(db: Session, active_only: bool = True) -> List[Property]:
    """Get all properties."""
    query = db.query(Property)
    if active_only:
        query = query.filter(Property.is_active == 'Y')
    return query.all()


def upsert_property(
    db: Session,
    address: str,
    city: str,
    state: str,
    zip_code: str,
    property_type: str,
    purchase_date: Optional[date] = None,
    purchase_price: Optional[Decimal] = None,
    current_value: Optional[Decimal] = None,
    current_value_date: Optional[date] = None,
    square_feet: Optional[int] = None,
    lot_size: Optional[Decimal] = None,
    bedrooms: Optional[int] = None,
    bathrooms: Optional[Decimal] = None,
    year_built: Optional[int] = None,
    notes: Optional[str] = None,
) -> Property:
    """Create or update a property. Uses address for deduplication."""
    existing = db.query(Property).filter(
        Property.address == address
    ).first()
    
    if existing:
        # Update existing property
        existing.city = city
        existing.state = state
        existing.zip_code = zip_code
        existing.property_type = property_type
        if purchase_date:
            existing.purchase_date = purchase_date
        if purchase_price is not None:
            existing.purchase_price = purchase_price
        if current_value is not None:
            existing.current_value = current_value
        if current_value_date:
            existing.current_value_date = current_value_date
        if square_feet:
            existing.square_feet = square_feet
        if lot_size is not None:
            existing.lot_size = lot_size
        if bedrooms:
            existing.bedrooms = bedrooms
        if bathrooms is not None:
            existing.bathrooms = bathrooms
        if year_built:
            existing.year_built = year_built
        if notes:
            existing.notes = notes
        return existing
    else:
        # Create new property
        prop = Property(
            address=address,
            city=city,
            state=state,
            zip_code=zip_code,
            property_type=property_type,
            purchase_date=purchase_date,
            purchase_price=purchase_price,
            current_value=current_value,
            current_value_date=current_value_date,
            square_feet=square_feet,
            lot_size=lot_size,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            year_built=year_built,
            notes=notes,
            is_active='Y',
        )
        db.add(prop)
        db.flush()
        return prop


def upsert_valuation(
    db: Session,
    property_id: int,
    valuation_date: date,
    value: Decimal,
    source: str = 'manual',
    notes: Optional[str] = None,
) -> PropertyValuation:
    """Create or update a property valuation. Uses property_id + date for deduplication."""
    existing = db.query(PropertyValuation).filter(
        PropertyValuation.property_id == property_id,
        PropertyValuation.valuation_date == valuation_date
    ).first()
    
    if existing:
        # Update existing valuation
        existing.value = value
        existing.valuation_source = source
        if notes:
            existing.notes = notes
        return existing
    else:
        # Create new valuation
        val = PropertyValuation(
            property_id=property_id,
            valuation_date=valuation_date,
            value=value,
            valuation_source=source,
            notes=notes,
        )
        db.add(val)
        return val


def get_valuations(db: Session, property_id: int) -> List[PropertyValuation]:
    """Get all valuations for a property, ordered by date."""
    return db.query(PropertyValuation).filter(
        PropertyValuation.property_id == property_id
    ).order_by(PropertyValuation.valuation_date).all()


def get_latest_valuation(db: Session, property_id: int) -> Optional[PropertyValuation]:
    """Get the most recent valuation for a property."""
    return db.query(PropertyValuation).filter(
        PropertyValuation.property_id == property_id
    ).order_by(desc(PropertyValuation.valuation_date)).first()


def get_property_summary(db: Session) -> Dict[str, Any]:
    """Get summary of all properties."""
    properties = get_all_properties(db)
    
    total_value = Decimal('0')
    total_equity = Decimal('0')
    total_mortgage = Decimal('0')
    
    property_list = []
    
    for prop in properties:
        value = prop.current_value or Decimal('0')
        purchase_price = float(prop.purchase_price) if prop.purchase_price else 0
        current_value = float(value)
        
        # Calculate mortgage balance
        mortgage_balance = Decimal('0')
        for mortgage in prop.mortgages:
            if mortgage.is_active == 'Y':
                mortgage_balance += mortgage.current_balance or Decimal('0')
        
        equity = value - mortgage_balance
        
        total_value += value
        total_mortgage += mortgage_balance
        total_equity += equity
        
        # Calculate appreciation
        total_appreciation = current_value - purchase_price
        appreciation_percent = (total_appreciation / purchase_price * 100) if purchase_price > 0 else 0
        
        # Calculate annual appreciation rate
        years_owned = 0
        if prop.purchase_date:
            from datetime import date
            days_owned = (date.today() - prop.purchase_date).days
            years_owned = days_owned / 365.25
        annual_appreciation_rate = (appreciation_percent / years_owned) if years_owned > 0 else 0
        
        property_list.append({
            'id': prop.id,
            'address': prop.address,
            'full_address': f"{prop.address}, {prop.city}, {prop.state} {prop.zip_code}",
            'city': prop.city,
            'state': prop.state,
            'zip_code': prop.zip_code,
            'property_type': prop.property_type,
            'property_type_display': prop.property_type.replace('_', ' ').title() if prop.property_type else 'Unknown',
            'value': float(value),
            'current_value': current_value,
            'purchase_price': purchase_price,
            'purchase_date': prop.purchase_date.isoformat() if prop.purchase_date else None,
            'purchase_year': prop.purchase_date.year if prop.purchase_date else None,
            'current_value_date': prop.current_value_date.isoformat() if prop.current_value_date else None,
            'valuation_source': 'Zillow Zestimate',
            'mortgage_balance': float(mortgage_balance),
            'equity': float(equity),
            'equity_percent': float(equity / value * 100) if value > 0 else 0,
            'total_appreciation': total_appreciation,
            'appreciation_percent': round(appreciation_percent, 2),
            'annual_appreciation_rate': round(annual_appreciation_rate, 2),
            'has_mortgage': float(mortgage_balance) > 0,
            'is_paid_off': float(mortgage_balance) == 0,
            'square_feet': prop.square_feet,
            'lot_size': float(prop.lot_size) if prop.lot_size else None,
            'bedrooms': prop.bedrooms,
            'bathrooms': float(prop.bathrooms) if prop.bathrooms else None,
            'year_built': prop.year_built,
            'stories': 3 if 'Hartstene' in prop.address else None,
            'parking': '2-car garage' if 'Hartstene' in prop.address else None,
            'property_style': 'Contemporary Townhome' if 'Hartstene' in prop.address else None,
            'zillow_url': 'https://www.zillow.com/homedetails/303-Hartstene-Dr-Redwood-City-CA-94065/2079949221_zpid/' if 'Hartstene' in prop.address else None,
            'notes': prop.notes,
        })
    
    return {
        'total_value': float(total_value),
        'total_mortgage_balance': float(total_mortgage),
        'total_equity': float(total_equity),
        'property_count': len(properties),
        'properties': property_list,
    }


def get_property_detail(db: Session, property_id: int) -> Optional[Dict[str, Any]]:
    """Get detailed information for a property including valuations."""
    prop = get_property_by_id(db, property_id)
    if not prop:
        return None
    
    valuations = get_valuations(db, property_id)
    
    # Calculate appreciation
    purchase_price = float(prop.purchase_price) if prop.purchase_price else 0
    current_value = float(prop.current_value) if prop.current_value else 0
    total_appreciation = current_value - purchase_price
    appreciation_percent = (total_appreciation / purchase_price * 100) if purchase_price > 0 else 0
    
    # Calculate equity
    mortgage_balance = Decimal('0')
    for mortgage in prop.mortgages:
        if mortgage.is_active == 'Y':
            mortgage_balance += mortgage.current_balance or Decimal('0')
    
    equity = (prop.current_value or Decimal('0')) - mortgage_balance
    
    return {
        'property': {
            'id': prop.id,
            'address': prop.address,
            'full_address': f"{prop.address}, {prop.city}, {prop.state} {prop.zip_code}",
            'city': prop.city,
            'state': prop.state,
            'zip_code': prop.zip_code,
            'property_type': prop.property_type,
            'property_type_display': prop.property_type.replace('_', ' ').title(),
            'purchase_date': prop.purchase_date.isoformat() if prop.purchase_date else None,
            'purchase_price': purchase_price,
            'current_value': current_value,
            'current_value_date': prop.current_value_date.isoformat() if prop.current_value_date else None,
            'square_feet': prop.square_feet,
            'lot_size': float(prop.lot_size) if prop.lot_size else None,
            'bedrooms': prop.bedrooms,
            'bathrooms': float(prop.bathrooms) if prop.bathrooms else None,
            'year_built': prop.year_built,
            'notes': prop.notes,
            'is_active': prop.is_active == 'Y',
            'total_appreciation': total_appreciation,
            'appreciation_percent': round(appreciation_percent, 2),
            'equity': float(equity),
            'equity_percent': float(equity / prop.current_value * 100) if prop.current_value else 0,
            'has_mortgage': float(mortgage_balance) > 0,
            'mortgage_balance': float(mortgage_balance),
            'is_paid_off': float(mortgage_balance) == 0,
        },
        'valuation_history': [
            {
                'date': v.valuation_date.isoformat(),
                'value': float(v.value),
                'source': v.valuation_source,
            }
            for v in valuations
        ],
        'mortgage': None,  # TODO: Add mortgage details if needed
    }


def seed_hartstene_property(db: Session) -> Dict[str, Any]:
    """
    Seed the Hartstene Drive property data into the database.
    Uses upsert logic to prevent duplicates.
    Returns statistics about what was created/updated.
    """
    from datetime import date
    
    stats = {'property_created': False, 'property_updated': False, 'valuations_added': 0, 'valuations_updated': 0}
    
    # Check if property already exists
    existing = db.query(Property).filter(
        Property.address == "303 Hartstene Drive"
    ).first()
    
    if existing:
        stats['property_updated'] = True
    else:
        stats['property_created'] = True
    
    # Upsert the property
    prop = upsert_property(
        db=db,
        address="303 Hartstene Drive",
        city="Redwood City",
        state="CA",
        zip_code="94065",
        property_type="primary_residence",
        purchase_date=date(2011, 1, 1),
        purchase_price=Decimal('760000'),
        current_value=Decimal('1700000'),
        current_value_date=date(2024, 11, 27),
        square_feet=1850,
        lot_size=Decimal('0.05'),
        bedrooms=3,
        bathrooms=Decimal('2.5'),
        year_built=2010,
        notes="Fully paid off since purchase. Located in desirable Redwood Shores community with bay views and trail access.",
    )
    db.flush()
    
    # Valuation history
    valuation_data = [
        (date(2011, 1, 1), Decimal('760000'), "Purchase Price"),
        (date(2012, 1, 1), Decimal('720000'), "Zillow"),
        (date(2013, 1, 1), Decimal('800000'), "Zillow"),
        (date(2014, 1, 1), Decimal('920000'), "Zillow"),
        (date(2015, 1, 1), Decimal('1050000'), "Zillow"),
        (date(2016, 1, 1), Decimal('1150000'), "Zillow"),
        (date(2017, 1, 1), Decimal('1250000'), "Zillow"),
        (date(2018, 1, 1), Decimal('1400000'), "Zillow"),
        (date(2019, 1, 1), Decimal('1450000'), "Zillow"),
        (date(2020, 1, 1), Decimal('1480000'), "Zillow"),
        (date(2021, 1, 1), Decimal('1550000'), "Zillow"),
        (date(2022, 1, 1), Decimal('1750000'), "Zillow"),
        (date(2023, 1, 1), Decimal('1680000'), "Zillow"),
        (date(2024, 1, 1), Decimal('1700000'), "Zillow"),
        (date(2024, 11, 27), Decimal('1700000'), "Zillow Zestimate"),
    ]
    
    for val_date, value, source in valuation_data:
        existing_val = db.query(PropertyValuation).filter(
            PropertyValuation.property_id == prop.id,
            PropertyValuation.valuation_date == val_date
        ).first()
        
        if existing_val:
            stats['valuations_updated'] += 1
        else:
            stats['valuations_added'] += 1
        
        upsert_valuation(
            db=db,
            property_id=prop.id,
            valuation_date=val_date,
            value=value,
            source=source,
        )
    
    db.commit()
    
    return stats




