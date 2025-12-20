"""
Equity module services for startup holdings management.
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Dict, List, Optional, Any
from decimal import Decimal
from datetime import date

from app.modules.equity.models import (
    EquityCompany,
    EquityGrant,
    EquityShares,
    EquityRSA,
    EquitySAFE,
    EquityExercise,
)


def get_all_companies(db: Session) -> List[EquityCompany]:
    """Get all equity companies."""
    return db.query(EquityCompany).filter(
        EquityCompany.status != 'shutdown'
    ).all()


def get_company_by_id(db: Session, company_id: int) -> Optional[EquityCompany]:
    """Get a company by ID."""
    return db.query(EquityCompany).filter(EquityCompany.id == company_id).first()


def get_company_holdings(db: Session, company_id: int) -> Dict[str, Any]:
    """Get all holdings for a specific company."""
    company = get_company_by_id(db, company_id)
    if not company:
        return None
    
    grants = db.query(EquityGrant).filter(EquityGrant.company_id == company_id).all()
    shares = db.query(EquityShares).filter(EquityShares.company_id == company_id).all()
    rsas = db.query(EquityRSA).filter(EquityRSA.company_id == company_id).all()
    safes = db.query(EquitySAFE).filter(EquitySAFE.company_id == company_id).all()
    
    return {
        'company': company,
        'grants': grants,
        'shares': shares,
        'rsas': rsas,
        'safes': safes,
    }


def get_equity_summary(db: Session) -> Dict[str, Any]:
    """Get summary of all equity holdings."""
    companies = get_all_companies(db)
    
    total_estimated_value = Decimal('0')
    total_cost_basis = Decimal('0')
    holdings_by_company = []
    
    for company in companies:
        company_value = Decimal('0')
        company_cost = Decimal('0')
        
        # Get ALL grants to show totals, but only count 'active' for exercisable value
        all_grants = db.query(EquityGrant).filter(
            EquityGrant.company_id == company.id
        ).all()
        
        total_options = 0
        vested_options = 0
        exercised_options = 0
        
        for grant in all_grants:
            total_options += grant.total_options or 0
            vested_options += grant.vested_options or 0
            exercised_options += grant.exercised_options or 0
            
            # Only count options value for ACTIVE grants (not expired/forfeited/fully_exercised)
            if grant.status == 'active' and company.current_fmv and grant.exercise_price is not None:
                spread = company.current_fmv - grant.exercise_price
                if spread > 0:
                    exercisable = (grant.vested_options or 0) - (grant.exercised_options or 0)
                    if exercisable > 0:
                        company_value += spread * exercisable
        
        # Calculate shares value - ONLY 'held' status counts
        shares = db.query(EquityShares).filter(
            EquityShares.company_id == company.id,
            EquityShares.status == 'held'
        ).all()
        
        total_shares = 0
        for share in shares:
            total_shares += share.num_shares or 0
            if company.current_fmv:
                company_value += company.current_fmv * (share.num_shares or 0)
            if share.cost_basis_per_share:
                company_cost += share.cost_basis_per_share * (share.num_shares or 0)
        
        # Calculate RSAs value
        rsas = db.query(EquityRSA).filter(
            EquityRSA.company_id == company.id,
            EquityRSA.status.in_(['active', 'fully_vested'])
        ).all()
        
        total_rsas = 0
        for rsa in rsas:
            total_rsas += rsa.vested_shares or 0
            if company.current_fmv:
                company_value += company.current_fmv * (rsa.vested_shares or 0)
        
        # Calculate SAFEs value (at principal) - only outstanding
        safes = db.query(EquitySAFE).filter(
            EquitySAFE.company_id == company.id,
            EquitySAFE.status == 'outstanding'
        ).all()
        
        safe_principal = Decimal('0')
        for safe in safes:
            safe_principal += safe.principal_amount or 0
        
        total_estimated_value += company_value + safe_principal
        total_cost_basis += company_cost
        
        holdings_by_company.append({
            'id': company.id,
            'name': company.dba_name or company.name,
            'status': company.status,
            'current_fmv': float(company.current_fmv) if company.current_fmv else None,
            'fmv_date': company.fmv_date.isoformat() if company.fmv_date else None,
            'qsbs_eligible': company.qsbs_eligible == 'Y',
            'total_options': total_options,
            'vested_options': vested_options,
            'exercised_options': exercised_options,
            'total_shares': total_shares,
            'total_rsas': total_rsas,
            'safe_principal': float(safe_principal),
            'estimated_value': float(company_value + safe_principal),
        })
    
    return {
        'total_estimated_value': float(total_estimated_value),
        'total_cost_basis': float(total_cost_basis),
        'total_unrealized_gain': float(total_estimated_value - total_cost_basis),
        'num_companies': len(companies),
        'holdings_by_company': holdings_by_company,
    }


def get_company_detail(db: Session, company_id: int) -> Optional[Dict[str, Any]]:
    """Get detailed holdings for a company."""
    company = get_company_by_id(db, company_id)
    if not company:
        return None
    
    grants = db.query(EquityGrant).filter(EquityGrant.company_id == company_id).all()
    shares = db.query(EquityShares).filter(EquityShares.company_id == company_id).all()
    rsas = db.query(EquityRSA).filter(EquityRSA.company_id == company_id).all()
    safes = db.query(EquitySAFE).filter(EquitySAFE.company_id == company_id).all()
    
    # Get exercises for all grants
    exercises = []
    for grant in grants:
        grant_exercises = db.query(EquityExercise).filter(
            EquityExercise.grant_id == grant.id
        ).all()
        exercises.extend(grant_exercises)
    
    return {
        'company': {
            'id': company.id,
            'name': company.name,
            'dba_name': company.dba_name,
            'status': company.status,
            'current_fmv': float(company.current_fmv) if company.current_fmv else None,
            'fmv_date': company.fmv_date.isoformat() if company.fmv_date else None,
            'qsbs_eligible': company.qsbs_eligible == 'Y',
            'qsbs_notes': company.qsbs_notes,
            'notes': company.notes,
        },
        'grants': [
            {
                'id': g.id,
                'grant_id': g.grant_id,
                'grant_type': g.grant_type,
                'grant_date': g.grant_date.isoformat() if g.grant_date else None,
                'total_options': g.total_options,
                'vested_options': g.vested_options,
                'exercised_options': g.exercised_options,
                'unvested_options': g.total_options - (g.vested_options or 0),
                'exercisable_options': (g.vested_options or 0) - (g.exercised_options or 0),
                'exercise_price': float(g.exercise_price) if g.exercise_price else None,
                'status': g.status,
                'expiration_date': g.expiration_date.isoformat() if g.expiration_date else None,
            }
            for g in grants
        ],
        'shares': [
            {
                'id': s.id,
                'certificate_id': s.certificate_id,
                'share_type': s.share_type,
                'num_shares': s.num_shares,
                'acquisition_date': s.acquisition_date.isoformat() if s.acquisition_date else None,
                'cost_basis_per_share': float(s.cost_basis_per_share) if s.cost_basis_per_share else None,
                'source': s.source,
                'status': s.status,
            }
            for s in shares
        ],
        'rsas': [
            {
                'id': r.id,
                'rsa_id': r.rsa_id,
                'total_shares': r.total_shares,
                'vested_shares': r.vested_shares,
                'grant_date': r.grant_date.isoformat() if r.grant_date else None,
                'status': r.status,
                'election_83b_filed': r.election_83b_filed == 'Y',
            }
            for r in rsas
        ],
        'safes': [
            {
                'id': sf.id,
                'safe_id': sf.safe_id,
                'principal_amount': float(sf.principal_amount) if sf.principal_amount else None,
                'investment_date': sf.investment_date.isoformat() if sf.investment_date else None,
                'valuation_cap': float(sf.valuation_cap) if sf.valuation_cap else None,
                'discount_rate': float(sf.discount_rate) if sf.discount_rate else None,
                'status': sf.status,
            }
            for sf in safes
        ],
        'exercises': [
            {
                'id': e.id,
                'grant_id': e.grant_id,
                'exercise_date': e.exercise_date.isoformat() if e.exercise_date else None,
                'num_shares': e.num_shares,
                'exercise_price': float(e.exercise_price) if e.exercise_price else None,
                'fmv_at_exercise': float(e.fmv_at_exercise) if e.fmv_at_exercise else None,
                'bargain_element': float(e.bargain_element) if e.bargain_element else None,
            }
            for e in exercises
        ],
    }


def create_company(db: Session, data: Dict[str, Any]) -> EquityCompany:
    """Create a new equity company."""
    company = EquityCompany(**data)
    db.add(company)
    db.flush()
    return company


def create_grant(db: Session, data: Dict[str, Any]) -> EquityGrant:
    """Create a new equity grant."""
    grant = EquityGrant(**data)
    db.add(grant)
    db.flush()
    return grant


def create_shares(db: Session, data: Dict[str, Any]) -> EquityShares:
    """Create new shares record."""
    shares = EquityShares(**data)
    db.add(shares)
    db.flush()
    return shares


def create_rsa(db: Session, data: Dict[str, Any]) -> EquityRSA:
    """Create a new RSA."""
    rsa = EquityRSA(**data)
    db.add(rsa)
    db.flush()
    return rsa


def create_safe(db: Session, data: Dict[str, Any]) -> EquitySAFE:
    """Create a new SAFE."""
    safe = EquitySAFE(**data)
    db.add(safe)
    db.flush()
    return safe

