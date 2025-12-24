"""
Equity module database models for startup holdings.
"""

from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Text, ForeignKey, Index
from datetime import datetime

from app.shared.models.base import BaseModel


class EquityCompany(BaseModel):
    """Companies where equity is held (startups from Carta)."""
    
    __tablename__ = "equity_companies"
    
    name = Column(String(200), nullable=False)
    dba_name = Column(String(200), nullable=True)  # "Doing Business As" name
    
    # Company info
    status = Column(String(50), default='active')  # 'active', 'acquired', 'ipo', 'shutdown'
    founded_date = Column(Date, nullable=True)
    
    # Valuation
    current_fmv = Column(Numeric(18, 4), nullable=True)  # Fair Market Value per share
    fmv_date = Column(Date, nullable=True)
    last_409a_date = Column(Date, nullable=True)
    
    # QSBS eligibility
    qsbs_eligible = Column(String(1), default='N')  # 'Y' or 'N'
    qsbs_notes = Column(Text, nullable=True)
    
    # Additional info
    industry = Column(String(100), nullable=True)
    website = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    
    logo_url = Column(String(500), nullable=True)


class EquityGrant(BaseModel):
    """Stock option grants (ISO or NSO)."""
    
    __tablename__ = "equity_grants"
    
    company_id = Column(Integer, ForeignKey('equity_companies.id'), nullable=False)
    
    # Grant identification
    grant_id = Column(String(50), nullable=True)  # e.g., "E9-2", "E5-85"
    grant_type = Column(String(20), nullable=False)  # 'ISO', 'NSO'
    
    # Grant details
    grant_date = Column(Date, nullable=True)
    total_options = Column(Integer, nullable=False)
    exercise_price = Column(Numeric(18, 4), nullable=False)
    
    # Vesting
    vested_options = Column(Integer, default=0)
    exercised_options = Column(Integer, default=0)
    
    # Status
    status = Column(String(50), default='active')  # 'active', 'terminated', 'expired', 'fully_exercised'
    expiration_date = Column(Date, nullable=True)
    termination_date = Column(Date, nullable=True)
    
    # Vesting schedule
    vesting_start_date = Column(Date, nullable=True)
    vesting_cliff_months = Column(Integer, nullable=True)  # typically 12 months
    vesting_total_months = Column(Integer, nullable=True)  # typically 48 months
    
    notes = Column(Text, nullable=True)


class EquityShares(BaseModel):
    """Shares held (from exercised options or direct purchase)."""
    
    __tablename__ = "equity_shares"
    
    company_id = Column(Integer, ForeignKey('equity_companies.id'), nullable=False)
    
    # Share identification
    certificate_id = Column(String(50), nullable=True)  # e.g., "PS2-8", "CS-1"
    share_type = Column(String(50), nullable=False)  # 'common', 'preferred', 'restricted'
    
    # Share details
    acquisition_date = Column(Date, nullable=True)
    num_shares = Column(Integer, nullable=False)
    cost_basis_per_share = Column(Numeric(18, 4), nullable=True)
    
    # Source of shares
    source = Column(String(50), nullable=True)  # 'exercise', 'rsa_vesting', 'purchase', 'grant'
    source_grant_id = Column(Integer, ForeignKey('equity_grants.id'), nullable=True)
    
    # Status
    status = Column(String(50), default='held')  # 'held', 'sold', 'canceled'
    sold_date = Column(Date, nullable=True)
    sold_price_per_share = Column(Numeric(18, 4), nullable=True)
    
    notes = Column(Text, nullable=True)


class EquityRSA(BaseModel):
    """Restricted Stock Awards/Agreements."""
    
    __tablename__ = "equity_rsas"
    
    company_id = Column(Integer, ForeignKey('equity_companies.id'), nullable=False)
    
    # RSA identification
    rsa_id = Column(String(50), nullable=True)
    
    # RSA details
    grant_date = Column(Date, nullable=True)
    total_shares = Column(Integer, nullable=False)
    purchase_price = Column(Numeric(18, 4), nullable=True)  # often $0.0001 or similar
    
    # Vesting
    vested_shares = Column(Integer, default=0)
    
    # Status
    status = Column(String(50), default='active')  # 'active', 'fully_vested', 'canceled'
    
    # 83(b) election
    election_83b_filed = Column(String(1), default='N')  # 'Y' or 'N'
    election_83b_date = Column(Date, nullable=True)
    
    notes = Column(Text, nullable=True)


class EquitySAFE(BaseModel):
    """Simple Agreement for Future Equity."""
    
    __tablename__ = "equity_safes"
    
    company_id = Column(Integer, ForeignKey('equity_companies.id'), nullable=False)
    
    # SAFE identification
    safe_id = Column(String(50), nullable=True)  # e.g., "SAFE-7"
    
    # Investment details
    investment_date = Column(Date, nullable=True)
    principal_amount = Column(Numeric(18, 2), nullable=False)
    
    # Terms
    valuation_cap = Column(Numeric(18, 2), nullable=True)
    discount_rate = Column(Numeric(5, 2), nullable=True)  # e.g., 20.00 for 20%
    safe_type = Column(String(50), nullable=True)  # 'post-money', 'pre-money', 'mfn'
    
    # Conversion
    status = Column(String(50), default='outstanding')  # 'outstanding', 'converted', 'canceled'
    converted_date = Column(Date, nullable=True)
    converted_shares = Column(Integer, nullable=True)
    conversion_price = Column(Numeric(18, 4), nullable=True)
    
    notes = Column(Text, nullable=True)


class EquityExercise(BaseModel):
    """Record of option exercises (Form 3921 data)."""
    
    __tablename__ = "equity_exercises"
    
    grant_id = Column(Integer, ForeignKey('equity_grants.id'), nullable=False)
    
    # Exercise details
    exercise_date = Column(Date, nullable=False)
    num_shares = Column(Integer, nullable=False)
    exercise_price = Column(Numeric(18, 4), nullable=False)
    fmv_at_exercise = Column(Numeric(18, 4), nullable=True)  # Fair Market Value on exercise date
    
    # Resulting shares
    shares_id = Column(Integer, ForeignKey('equity_shares.id'), nullable=True)
    
    # Tax info
    bargain_element = Column(Numeric(18, 2), nullable=True)  # (FMV - Exercise Price) * shares
    
    # Form 3921 fields (for ISO exercises)
    form_3921_box1_date_granted = Column(Date, nullable=True)
    form_3921_box2_date_exercised = Column(Date, nullable=True)
    form_3921_box3_exercise_price = Column(Numeric(18, 4), nullable=True)
    form_3921_box4_fmv_exercise = Column(Numeric(18, 4), nullable=True)
    form_3921_box5_shares_transferred = Column(Integer, nullable=True)
    
    notes = Column(Text, nullable=True)

















