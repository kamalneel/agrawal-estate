"""
Equity Portfolio API routes.
Handles startup equity from Carta: options, shares, RSAs, SAFEs.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from decimal import Decimal
from datetime import date

from app.core.database import get_db
from app.modules.equity.services import (
    get_all_companies,
    get_company_by_id,
    get_equity_summary,
    get_company_detail,
    create_company,
    create_grant,
    create_shares,
    create_rsa,
    create_safe,
)
from app.modules.equity.models import (
    EquityCompany,
    EquityGrant,
    EquityShares,
    EquityRSA,
    EquitySAFE,
)

router = APIRouter()


# Pydantic models for request/response
class CompanyCreate(BaseModel):
    name: str
    dba_name: Optional[str] = None
    status: str = 'active'
    current_fmv: Optional[float] = None
    fmv_date: Optional[date] = None
    qsbs_eligible: str = 'N'
    qsbs_notes: Optional[str] = None
    notes: Optional[str] = None


class CompanyUpdate(BaseModel):
    """Partial update model for company - all fields optional."""
    name: Optional[str] = None
    dba_name: Optional[str] = None
    status: Optional[str] = None
    current_fmv: Optional[float] = None
    fmv_date: Optional[date] = None
    qsbs_eligible: Optional[str] = None
    qsbs_notes: Optional[str] = None
    notes: Optional[str] = None


class GrantCreate(BaseModel):
    company_id: int
    grant_id: Optional[str] = None
    grant_type: str  # 'ISO' or 'NSO'
    grant_date: Optional[date] = None
    total_options: int
    exercise_price: float
    vested_options: int = 0
    exercised_options: int = 0
    status: str = 'active'
    expiration_date: Optional[date] = None


class SharesCreate(BaseModel):
    company_id: int
    certificate_id: Optional[str] = None
    share_type: str  # 'common', 'preferred', 'restricted'
    acquisition_date: Optional[date] = None
    num_shares: int
    cost_basis_per_share: Optional[float] = None
    source: Optional[str] = None
    status: str = 'held'


class RSACreate(BaseModel):
    company_id: int
    rsa_id: Optional[str] = None
    grant_date: Optional[date] = None
    total_shares: int
    vested_shares: int = 0
    status: str = 'active'
    election_83b_filed: str = 'N'


class SAFECreate(BaseModel):
    company_id: int
    safe_id: Optional[str] = None
    investment_date: Optional[date] = None
    principal_amount: float
    valuation_cap: Optional[float] = None
    discount_rate: Optional[float] = None
    status: str = 'outstanding'


@router.get("/summary")
async def get_summary(db: Session = Depends(get_db)):
    """
    Get summary of all equity holdings across all companies.
    Returns total estimated value, holdings by company.
    """
    return get_equity_summary(db)


@router.get("/companies")
async def list_companies(db: Session = Depends(get_db)):
    """List all companies where equity is held."""
    companies = get_all_companies(db)
    
    return {
        "companies": [
            {
                "id": c.id,
                "name": c.name,
                "dba_name": c.dba_name,
                "status": c.status,
                "current_fmv": float(c.current_fmv) if c.current_fmv else None,
                "fmv_date": c.fmv_date.isoformat() if c.fmv_date else None,
                "qsbs_eligible": c.qsbs_eligible == 'Y',
            }
            for c in companies
        ]
    }


@router.get("/companies/{company_id}")
async def get_company(company_id: int, db: Session = Depends(get_db)):
    """Get detailed holdings for a specific company."""
    detail = get_company_detail(db, company_id)
    
    if not detail:
        raise HTTPException(status_code=404, detail="Company not found")
    
    return detail


@router.post("/companies")
async def add_company(company: CompanyCreate, db: Session = Depends(get_db)):
    """Add a new company."""
    try:
        new_company = create_company(db, company.model_dump())
        db.commit()
        
        return {
            "success": True,
            "company": {
                "id": new_company.id,
                "name": new_company.name,
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/companies/{company_id}")
async def update_company(
    company_id: int,
    data: CompanyUpdate,
    db: Session = Depends(get_db)
):
    """Update a company's information (partial update supported)."""
    company = get_company_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Only update fields that were explicitly set
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(company, key, value)
    
    db.commit()
    
    return {
        "success": True,
        "message": "Company updated",
        "company": {
            "id": company.id,
            "name": company.name,
            "current_fmv": float(company.current_fmv) if company.current_fmv else None,
            "fmv_date": company.fmv_date.isoformat() if company.fmv_date else None,
        }
    }


@router.post("/grants")
async def add_grant(grant: GrantCreate, db: Session = Depends(get_db)):
    """Add a new stock option grant."""
    # Verify company exists
    company = get_company_by_id(db, grant.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    try:
        new_grant = create_grant(db, grant.model_dump())
        db.commit()
        
        return {
            "success": True,
            "grant": {
                "id": new_grant.id,
                "grant_id": new_grant.grant_id,
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/grants")
async def list_grants(
    company_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all stock option grants."""
    query = db.query(EquityGrant)
    
    if company_id:
        query = query.filter(EquityGrant.company_id == company_id)
    if status:
        query = query.filter(EquityGrant.status == status)
    
    grants = query.all()
    
    return {
        "grants": [
            {
                "id": g.id,
                "company_id": g.company_id,
                "grant_id": g.grant_id,
                "grant_type": g.grant_type,
                "grant_date": g.grant_date.isoformat() if g.grant_date else None,
                "total_options": g.total_options,
                "vested_options": g.vested_options,
                "exercised_options": g.exercised_options,
                "exercise_price": float(g.exercise_price) if g.exercise_price else None,
                "status": g.status,
            }
            for g in grants
        ]
    }


@router.post("/shares")
async def add_shares(shares: SharesCreate, db: Session = Depends(get_db)):
    """Add shares (from exercise or direct purchase)."""
    company = get_company_by_id(db, shares.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    try:
        new_shares = create_shares(db, shares.model_dump())
        db.commit()
        
        return {
            "success": True,
            "shares": {
                "id": new_shares.id,
                "certificate_id": new_shares.certificate_id,
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/shares")
async def list_shares(
    company_id: Optional[int] = None,
    status: str = "held",
    db: Session = Depends(get_db)
):
    """List all shares held."""
    query = db.query(EquityShares).filter(EquityShares.status == status)
    
    if company_id:
        query = query.filter(EquityShares.company_id == company_id)
    
    shares = query.all()
    
    return {
        "shares": [
            {
                "id": s.id,
                "company_id": s.company_id,
                "certificate_id": s.certificate_id,
                "share_type": s.share_type,
                "num_shares": s.num_shares,
                "acquisition_date": s.acquisition_date.isoformat() if s.acquisition_date else None,
                "cost_basis_per_share": float(s.cost_basis_per_share) if s.cost_basis_per_share else None,
                "source": s.source,
                "status": s.status,
            }
            for s in shares
        ]
    }


@router.post("/rsas")
async def add_rsa(rsa: RSACreate, db: Session = Depends(get_db)):
    """Add a Restricted Stock Award."""
    company = get_company_by_id(db, rsa.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    try:
        new_rsa = create_rsa(db, rsa.model_dump())
        db.commit()
        
        return {
            "success": True,
            "rsa": {
                "id": new_rsa.id,
                "rsa_id": new_rsa.rsa_id,
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/safes")
async def add_safe(safe: SAFECreate, db: Session = Depends(get_db)):
    """Add a SAFE investment."""
    company = get_company_by_id(db, safe.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    try:
        new_safe = create_safe(db, safe.model_dump())
        db.commit()
        
        return {
            "success": True,
            "safe": {
                "id": new_safe.id,
                "safe_id": new_safe.safe_id,
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/safes")
async def list_safes(
    company_id: Optional[int] = None,
    status: str = "outstanding",
    db: Session = Depends(get_db)
):
    """List all SAFE investments."""
    query = db.query(EquitySAFE).filter(EquitySAFE.status == status)
    
    if company_id:
        query = query.filter(EquitySAFE.company_id == company_id)
    
    safes = query.all()
    
    return {
        "safes": [
            {
                "id": s.id,
                "company_id": s.company_id,
                "safe_id": s.safe_id,
                "principal_amount": float(s.principal_amount) if s.principal_amount else None,
                "investment_date": s.investment_date.isoformat() if s.investment_date else None,
                "valuation_cap": float(s.valuation_cap) if s.valuation_cap else None,
                "status": s.status,
            }
            for s in safes
        ]
    }


@router.get("/tax-implications")
async def get_tax_implications(
    year: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Get tax implications for equity holdings.
    Includes ISO/NSO treatment, AMT considerations, QSBS benefits.
    """
    summary = get_equity_summary(db)
    
    # Calculate potential tax implications
    implications = {
        "iso_grants": [],
        "nso_grants": [],
        "qsbs_eligible": [],
        "amt_warning": False,
        "notes": [],
    }
    
    for company_data in summary['holdings_by_company']:
        company = get_company_by_id(db, company_data['id'])
        
        if company_data['qsbs_eligible']:
            implications['qsbs_eligible'].append({
                "company": company_data['name'],
                "note": "May qualify for Section 1202 QSBS exclusion (up to $10M or 10x basis)"
            })
        
        # Check for ISO AMT implications
        grants = db.query(EquityGrant).filter(
            EquityGrant.company_id == company_data['id'],
            EquityGrant.grant_type == 'ISO',
            EquityGrant.exercised_options > 0
        ).all()
        
        for grant in grants:
            if company.current_fmv and grant.exercise_price:
                spread = float(company.current_fmv) - float(grant.exercise_price)
                if spread > 0:
                    implications['amt_warning'] = True
                    implications['notes'].append(
                        f"ISO exercise at {company_data['name']} may trigger AMT on bargain element"
                    )
    
    return {
        "year": year or "current",
        "implications": implications,
    }

