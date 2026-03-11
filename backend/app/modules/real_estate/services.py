"""
Real Estate Services - Database operations for properties, valuations, and rental management.
"""

import hashlib
import mimetypes
import os
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.core.config import settings
from app.modules.real_estate.models import (
    Property, PropertyValuation, Mortgage,
    RentalAgreement, PropertyRentalSummary, PropertyRentalExpense, RentalDocument,
)


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
        property_type="rental",
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
    
    # ── Seed rental agreements (from actual signed lease PDFs) ──
    stats['rental_agreements_seeded'] = 0
    rental_agreements_data = [
        {   # 2020 original lease - CAR Form LR
            'lease_start_date': date(2021, 3, 20),
            'lease_end_date': date(2022, 3, 19),
            'tenant_names': 'Tenant (COVID-era)',
            'monthly_rent': Decimal('6500'),
            'security_deposit': Decimal('6500'),
            'notes': 'CAR Form LR. Original COVID lease.',
        },
        {   # 2022-2023 extension addendum
            'lease_start_date': date(2022, 3, 19),
            'lease_end_date': date(2023, 3, 31),
            'tenant_names': 'Tenant (extension)',
            'monthly_rent': Decimal('5450'),
            'notes': 'Extension addendum. Prorated first partial month $1,796.',
        },
        {   # 2023 lease - Namit & Anubhuti Jain
            'lease_start_date': date(2023, 4, 7),
            'lease_end_date': date(2024, 4, 6),
            'tenant_names': 'Namit Jain & Anubhuti Jain',
            'monthly_rent': Decimal('5300'),
            'security_deposit': Decimal('5300'),
            'notes': 'First month prorated $4,240 (04/07-04/30). HOA paid by landlord.',
        },
        {   # 2024 lease - Namit & Anubhuti Jain (renewal)
            'lease_start_date': date(2024, 5, 1),
            'lease_end_date': date(2025, 4, 30),
            'tenant_names': 'Namit Jain & Anubhuti Jain',
            'monthly_rent': Decimal('5300'),
            'notes': 'Year 2 renewal. Security deposit carried over. HOA paid by landlord.',
        },
        {   # 2025-26 lease - Eric & Leslie
            'lease_start_date': date(2025, 4, 1),
            'lease_end_date': date(2026, 3, 31),
            'tenant_names': 'Eric Morales & Leslie A Trevitt',
            'monthly_rent': Decimal('5800'),
            'monthly_hoa': Decimal('420'),
        },
        {   # 2026-27 lease - Eric & Leslie
            'lease_start_date': date(2026, 4, 1),
            'lease_end_date': date(2027, 3, 31),
            'tenant_names': 'Eric Morales & Leslie A Trevitt',
            'monthly_rent': Decimal('5800'),
            'monthly_hoa': Decimal('420'),
        },
    ]

    for ra in rental_agreements_data:
        existing_ra = db.query(RentalAgreement).filter(
            RentalAgreement.property_id == prop.id,
            RentalAgreement.lease_start_date == ra['lease_start_date'],
        ).first()
        if not existing_ra:
            db.add(RentalAgreement(property_id=prop.id, **ra))
            stats['rental_agreements_seeded'] += 1

    # ── Seed 2022 expenses (from tax filing) ──
    stats['expenses_seeded'] = 0
    expenses_2022 = [
        ('advertising', Decimal('70')),
        ('auto_and_travel', Decimal('0')),
        ('cleaning_and_maintenance', Decimal('0')),
        ('insurance', Decimal('1241')),
        ('legal_and_professional_fee', Decimal('150')),
        ('mortgage_interest', Decimal('0')),
        ('repairs', Decimal('3450')),
        ('supplies', Decimal('0')),
        ('property_tax', Decimal('9728')),
        ('hoa', Decimal('4400')),
        ('maintenance', Decimal('0')),
    ]

    for category, amount in expenses_2022:
        existing_exp = db.query(PropertyRentalExpense).filter(
            PropertyRentalExpense.property_id == prop.id,
            PropertyRentalExpense.tax_year == 2022,
            PropertyRentalExpense.category == category,
        ).first()
        if not existing_exp:
            db.add(PropertyRentalExpense(
                property_id=prop.id,
                tax_year=2022,
                category=category,
                amount=amount,
            ))
            stats['expenses_seeded'] += 1

    # ── Seed annual income summaries ──
    # Derived from actual signed lease PDFs:
    #   2021: Tenant Mar 20-Dec ($6,500 x ~9.4 months) ≈ $61,100
    #   2022: Tenant Jan-Mar 19 ($6,500 x 2.6) + Extension Mar 19-Dec ($5,450 x 9.4) ≈ $68,080
    #   2023: Extension Jan-Mar ($5,450 x 3) + Namit Apr 7-Dec ($5,300 x ~8.8) = $63,000 (from tax filing: $64,000)
    #   2024: Namit Jan-Apr ($5,300 x 4) + Namit May-Dec ($5,300 x 8) = $63,600
    #   2025: Namit Jan-Mar ($5,300 x 3) + Eric Apr-Dec ($5,800 x 9) = $68,100
    annual_income_data = [
        (2021, Decimal('61100')),
        (2022, Decimal('64000')),
        (2023, Decimal('63000')),
        (2024, Decimal('63600')),
        (2025, Decimal('68100')),
    ]
    stats['annual_summaries_seeded'] = 0
    for year, income in annual_income_data:
        existing_summary = db.query(PropertyRentalSummary).filter(
            PropertyRentalSummary.property_id == prop.id,
            PropertyRentalSummary.tax_year == year,
        ).first()
        if not existing_summary:
            db.add(PropertyRentalSummary(
                property_id=prop.id,
                tax_year=year,
                annual_income=income,
                cost_of_property=Decimal('760000'),
            ))
            stats['annual_summaries_seeded'] += 1
        else:
            # Update income if not already set
            if not existing_summary.annual_income:
                existing_summary.annual_income = income

    # ── Seed 2025 HOA expense (from lease: $420/mo x 12 = $5,040) ──
    existing_hoa_2025 = db.query(PropertyRentalExpense).filter(
        PropertyRentalExpense.property_id == prop.id,
        PropertyRentalExpense.tax_year == 2025,
        PropertyRentalExpense.category == 'hoa',
    ).first()
    if not existing_hoa_2025:
        db.add(PropertyRentalExpense(
            property_id=prop.id,
            tax_year=2025,
            category='hoa',
            amount=Decimal('5040'),
        ))
        stats['expenses_seeded'] += 1

    # ── Seed lease documents from iCloud ──
    stats['documents_seeded'] = 0
    icloud_base = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/303 Hartstene Drive"
    lease_docs = [
        (icloud_base / "Renting 2020" / "Lease Agreement.pdf", 2020, "Lease Agreement 2020"),
        (icloud_base / "Renting 2023" / "Residential Lease Agreement for 303 Hartstne Drive for Namit and Anubhuti.pdf", 2023, "Lease Agreement 2023 - Namit & Anubhuti"),
        (icloud_base / "Renting 2024" / "Residential Lease Agreement for 303 Hartstne Drive for Namit and Anubhuti May 2024.pdf", 2024, "Lease Agreement 2024 - Namit & Anubhuti"),
        (icloud_base / "Renting 2025" / "SIGNED Rental Agreement for 303 Hartstene Drive 2025-26.pdf", 2025, "Signed Lease 2025-26 - Eric & Leslie"),
        (icloud_base / "Renting 2026" / "2026 - Rental_Agreement_303_Hartstene_Drive_2026-27.pdf", 2026, "Lease Agreement 2026-27 - Eric & Leslie"),
    ]

    for source_path, year, notes_text in lease_docs:
        if source_path.exists():
            try:
                upload_rental_document_from_path(
                    db=db,
                    property_id=prop.id,
                    source_path=source_path,
                    document_type="lease_agreement",
                    tax_year=year,
                    notes=notes_text,
                )
                stats['documents_seeded'] += 1
            except ValueError:
                pass  # duplicate document, skip

    db.commit()

    return stats


# ── Rental Agreements CRUD ────────────────────────────────────


def get_rental_agreements(db: Session, property_id: int) -> List[Dict[str, Any]]:
    """Get all rental agreements for a property, newest first."""
    agreements = db.query(RentalAgreement).filter(
        RentalAgreement.property_id == property_id
    ).order_by(desc(RentalAgreement.lease_start_date)).all()

    return [
        {
            'id': a.id,
            'property_id': a.property_id,
            'lease_start_date': a.lease_start_date.isoformat(),
            'lease_end_date': a.lease_end_date.isoformat(),
            'tenant_names': a.tenant_names,
            'monthly_rent': float(a.monthly_rent),
            'monthly_hoa': float(a.monthly_hoa) if a.monthly_hoa else None,
            'security_deposit': float(a.security_deposit) if a.security_deposit else None,
            'annual_rent': float(a.monthly_rent * 12),
            'notes': a.notes,
        }
        for a in agreements
    ]


def upsert_rental_agreement(
    db: Session,
    property_id: int,
    lease_start_date: date,
    lease_end_date: date,
    tenant_names: str,
    monthly_rent: Decimal,
    monthly_hoa: Optional[Decimal] = None,
    security_deposit: Optional[Decimal] = None,
    notes: Optional[str] = None,
) -> RentalAgreement:
    """Create or update a rental agreement."""
    existing = db.query(RentalAgreement).filter(
        RentalAgreement.property_id == property_id,
        RentalAgreement.lease_start_date == lease_start_date,
    ).first()

    if existing:
        existing.lease_end_date = lease_end_date
        existing.tenant_names = tenant_names
        existing.monthly_rent = monthly_rent
        existing.monthly_hoa = monthly_hoa
        existing.security_deposit = security_deposit
        if notes is not None:
            existing.notes = notes
        db.commit()
        return existing
    else:
        agreement = RentalAgreement(
            property_id=property_id,
            lease_start_date=lease_start_date,
            lease_end_date=lease_end_date,
            tenant_names=tenant_names,
            monthly_rent=monthly_rent,
            monthly_hoa=monthly_hoa,
            security_deposit=security_deposit,
            notes=notes,
        )
        db.add(agreement)
        db.commit()
        return agreement


# ── Rental Expenses CRUD ──────────────────────────────────────

# Standard IRS Schedule E expense categories
EXPENSE_CATEGORIES = [
    'advertising',
    'auto_and_travel',
    'cleaning_and_maintenance',
    'commissions',
    'insurance',
    'legal_and_professional_fee',
    'management_fees',
    'mortgage_interest',
    'other',
    'repairs',
    'supplies',
    'property_tax',
    'utilities',
    'hoa',
    'maintenance',
]


def get_expenses_by_year(db: Session, property_id: int, tax_year: int) -> List[Dict[str, Any]]:
    """Get all expenses for a property and year."""
    expenses = db.query(PropertyRentalExpense).filter(
        PropertyRentalExpense.property_id == property_id,
        PropertyRentalExpense.tax_year == tax_year,
    ).order_by(PropertyRentalExpense.category).all()

    return [
        {
            'id': e.id,
            'property_id': e.property_id,
            'tax_year': e.tax_year,
            'category': e.category,
            'category_display': e.category.replace('_', ' ').title(),
            'amount': float(e.amount),
            'description': e.description,
        }
        for e in expenses
    ]


def upsert_expense(
    db: Session,
    property_id: int,
    tax_year: int,
    category: str,
    amount: Decimal,
    description: Optional[str] = None,
) -> PropertyRentalExpense:
    """Create or update an expense."""
    existing = db.query(PropertyRentalExpense).filter(
        PropertyRentalExpense.property_id == property_id,
        PropertyRentalExpense.tax_year == tax_year,
        PropertyRentalExpense.category == category,
    ).first()

    if existing:
        existing.amount = amount
        if description is not None:
            existing.description = description
        db.commit()
        return existing
    else:
        expense = PropertyRentalExpense(
            property_id=property_id,
            tax_year=tax_year,
            category=category,
            amount=amount,
            description=description,
        )
        db.add(expense)
        db.commit()
        return expense


def delete_expense(db: Session, expense_id: int) -> bool:
    """Delete an expense."""
    expense = db.query(PropertyRentalExpense).filter(PropertyRentalExpense.id == expense_id).first()
    if not expense:
        return False
    db.delete(expense)
    db.commit()
    return True


# ── Annual Income CRUD ────────────────────────────────────────


def get_annual_summary(db: Session, property_id: int, tax_year: int) -> Dict[str, Any]:
    """Get annual income/expense summary for a property."""
    summary = db.query(PropertyRentalSummary).filter(
        PropertyRentalSummary.property_id == property_id,
        PropertyRentalSummary.tax_year == tax_year,
    ).first()

    expenses = get_expenses_by_year(db, property_id, tax_year)
    total_expenses = sum(e['amount'] for e in expenses)
    annual_income = float(summary.annual_income) if summary and summary.annual_income else 0
    cost_of_property = float(summary.cost_of_property) if summary and summary.cost_of_property else None

    return {
        'property_id': property_id,
        'tax_year': tax_year,
        'annual_income': annual_income,
        'cost_of_property': cost_of_property,
        'expenses': expenses,
        'total_expenses': round(total_expenses, 2),
        'net_income': round(annual_income - total_expenses, 2),
    }


def upsert_annual_income(
    db: Session,
    property_id: int,
    tax_year: int,
    annual_income: Optional[Decimal] = None,
    cost_of_property: Optional[Decimal] = None,
) -> PropertyRentalSummary:
    """Create or update annual income for a year."""
    existing = db.query(PropertyRentalSummary).filter(
        PropertyRentalSummary.property_id == property_id,
        PropertyRentalSummary.tax_year == tax_year,
    ).first()

    if existing:
        if annual_income is not None:
            existing.annual_income = annual_income
        if cost_of_property is not None:
            existing.cost_of_property = cost_of_property
        db.commit()
        return existing
    else:
        s = PropertyRentalSummary(
            property_id=property_id,
            tax_year=tax_year,
            annual_income=annual_income,
            cost_of_property=cost_of_property,
        )
        db.add(s)
        db.commit()
        return s


# ── Rental Documents ──────────────────────────────────────────


def _ensure_rental_doc_dir(property_id: int) -> Path:
    """Ensure directory for rental documents exists."""
    dir_path = settings.RENTAL_DOCUMENTS_DIR / str(property_id)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def _compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal."""
    filename = os.path.basename(filename)
    for char in ['/', '\\', '..', '<', '>', ':', '"', '|', '?', '*']:
        filename = filename.replace(char, '_')
    return filename


async def upload_rental_document(
    db: Session,
    property_id: int,
    file: UploadFile,
    document_type: str,
    tax_year: Optional[int] = None,
    notes: Optional[str] = None,
) -> RentalDocument:
    """Upload a rental document via HTTP."""
    dir_path = _ensure_rental_doc_dir(property_id)

    from datetime import datetime
    original_filename = _sanitize_filename(file.filename or "document")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_ext = Path(original_filename).suffix or ".pdf"
    base_name = Path(original_filename).stem
    new_filename = f"{base_name}_{timestamp}{file_ext}"
    file_path = dir_path / new_filename

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    file_hash = _compute_file_hash(file_path)

    # Check for duplicate
    existing = db.query(RentalDocument).filter(
        RentalDocument.property_id == property_id,
        RentalDocument.file_hash == file_hash,
    ).first()
    if existing:
        file_path.unlink(missing_ok=True)
        raise ValueError(f"Duplicate document. Already uploaded as '{existing.file_name}'")

    doc = RentalDocument(
        property_id=property_id,
        document_type=document_type,
        tax_year=tax_year,
        file_name=original_filename,
        file_path=str(file_path.relative_to(settings.BASE_DIR)),
        file_hash=file_hash,
        file_size=len(content),
        mime_type=file.content_type,
        notes=notes,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def upload_rental_document_from_path(
    db: Session,
    property_id: int,
    source_path: Path,
    document_type: str,
    tax_year: Optional[int] = None,
    notes: Optional[str] = None,
) -> RentalDocument:
    """Copy a local file into the rental documents store."""
    if not source_path.exists():
        raise ValueError(f"File not found: {source_path}")

    dir_path = _ensure_rental_doc_dir(property_id)

    from datetime import datetime
    original_filename = _sanitize_filename(source_path.name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_ext = source_path.suffix or ".pdf"
    base_name = source_path.stem
    new_filename = f"{base_name}_{timestamp}{file_ext}"
    dest_path = dir_path / new_filename

    shutil.copy2(str(source_path), str(dest_path))

    file_hash = _compute_file_hash(dest_path)
    file_size = dest_path.stat().st_size

    # Check for duplicate
    existing = db.query(RentalDocument).filter(
        RentalDocument.property_id == property_id,
        RentalDocument.file_hash == file_hash,
    ).first()
    if existing:
        dest_path.unlink(missing_ok=True)
        raise ValueError(f"Duplicate document. Already uploaded as '{existing.file_name}'")

    mime_type, _ = mimetypes.guess_type(str(dest_path))

    doc = RentalDocument(
        property_id=property_id,
        document_type=document_type,
        tax_year=tax_year,
        file_name=original_filename,
        file_path=str(dest_path.relative_to(settings.BASE_DIR)),
        file_hash=file_hash,
        file_size=file_size,
        mime_type=mime_type or "application/octet-stream",
        notes=notes,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def get_rental_documents(db: Session, property_id: int) -> List[Dict[str, Any]]:
    """Get all rental documents for a property."""
    docs = db.query(RentalDocument).filter(
        RentalDocument.property_id == property_id
    ).order_by(desc(RentalDocument.tax_year), RentalDocument.file_name).all()

    return [
        {
            'id': d.id,
            'property_id': d.property_id,
            'document_type': d.document_type,
            'tax_year': d.tax_year,
            'file_name': d.file_name,
            'file_size': d.file_size,
            'mime_type': d.mime_type,
            'notes': d.notes,
            'created_at': d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]


def get_rental_document_path(db: Session, doc_id: int) -> Optional[Path]:
    """Get the full file path for a rental document."""
    doc = db.query(RentalDocument).filter(RentalDocument.id == doc_id).first()
    if not doc:
        return None
    return settings.BASE_DIR / doc.file_path


def delete_rental_document(db: Session, doc_id: int) -> bool:
    """Delete a rental document and its file."""
    doc = db.query(RentalDocument).filter(RentalDocument.id == doc_id).first()
    if not doc:
        return False
    try:
        file_path = settings.BASE_DIR / doc.file_path
        if file_path.exists():
            file_path.unlink()
    except Exception:
        pass
    db.delete(doc)
    db.commit()
    return True


# ── Rental Income Projection from Agreements ─────────────────


def project_rental_income_from_agreements(db: Session) -> Dict[str, Any]:
    """Project rental_monthly_income rows from active rental_agreements.

    For each property with rental agreements:
    1. Find the matching rental_properties entry (income module)
    2. For each month covered by an agreement, if no rental_monthly_income
       row exists, insert one with gross_amount = monthly_rent + monthly_hoa
    3. Returns stats on what was created.
    """
    from sqlalchemy import text

    stats = {'months_created': 0, 'months_existing': 0, 'properties_matched': 0}

    # Get all properties with rental agreements
    properties_with_agreements = db.query(Property).filter(
        Property.property_type == 'rental',
        Property.is_active == 'Y',
    ).all()

    for prop in properties_with_agreements:
        # Match to rental_properties (income module) by address substring
        # e.g. "303 Hartstene Drive" should match "303 Hartstene Dr, Redwood City CA 94065"
        address_prefix = prop.address.split(',')[0].strip() if prop.address else ''
        if not address_prefix:
            continue

        # Normalize: take first 2 words (number + street name) for fuzzy match
        addr_words = address_prefix.split()[:2]
        if len(addr_words) < 2:
            continue
        search_pattern = f"%{addr_words[0]}%{addr_words[1]}%"

        rental_prop_row = db.execute(text(
            "SELECT id FROM rental_properties WHERE property_address LIKE :pattern AND is_active = 'Y' LIMIT 1"
        ), {'pattern': search_pattern}).fetchone()

        if not rental_prop_row:
            continue

        rental_property_id = rental_prop_row[0]
        stats['properties_matched'] += 1

        # Get all agreements for this property, ordered by start date
        agreements = db.query(RentalAgreement).filter(
            RentalAgreement.property_id == prop.id,
        ).order_by(RentalAgreement.lease_start_date).all()

        for agreement in agreements:
            gross_amount = float(agreement.monthly_rent or 0) + float(agreement.monthly_hoa or 0)
            if gross_amount <= 0:
                continue

            # Generate all months covered by this agreement
            start = agreement.lease_start_date
            end = agreement.lease_end_date
            yr, mo = start.year, start.month

            while date(yr, mo, 1) <= end:
                # Check if row already exists
                existing = db.execute(text(
                    "SELECT id FROM rental_monthly_income "
                    "WHERE property_id = :pid AND tax_year = :yr AND month = :mo"
                ), {'pid': rental_property_id, 'yr': yr, 'mo': mo}).fetchone()

                if existing:
                    stats['months_existing'] += 1
                else:
                    db.execute(text(
                        "INSERT INTO rental_monthly_income "
                        "(property_id, tax_year, month, gross_amount, created_at, updated_at) "
                        "VALUES (:pid, :yr, :mo, :amt, NOW(), NOW())"
                    ), {'pid': rental_property_id, 'yr': yr, 'mo': mo, 'amt': gross_amount})
                    stats['months_created'] += 1

                # Next month
                mo += 1
                if mo > 12:
                    mo = 1
                    yr += 1

    db.commit()
    return stats
