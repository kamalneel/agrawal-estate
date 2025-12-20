"""
Mutual Fund Research and Comparison models.
"""

from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Text, UniqueConstraint, Index
from datetime import datetime

from app.shared.models.base import BaseModel


class MutualFundResearch(BaseModel):
    """Mutual funds being researched/compared."""
    
    __tablename__ = "mutual_fund_research"
    
    # Basic Info
    scheme_code = Column(String(20), nullable=False, unique=True)  # AMFI scheme code
    scheme_name = Column(String(500), nullable=False)
    fund_house = Column(String(200), nullable=True)  # AMC name (e.g., "PPFAS", "DSP")
    
    # Classification
    scheme_type = Column(String(100), nullable=True)  # e.g., "Open Ended Schemes"
    scheme_category = Column(String(200), nullable=True)  # e.g., "Equity Scheme - Large Cap Fund"
    fund_category = Column(String(100), nullable=True)  # e.g., "Large Cap", "Flexi Cap", "International"
    
    # ISIN codes
    isin_growth = Column(String(50), nullable=True)
    isin_div_reinvestment = Column(String(50), nullable=True)
    
    # Current NAV
    current_nav = Column(Numeric(18, 4), nullable=True)
    nav_date = Column(Date, nullable=True)
    
    # Historical Returns (calculated from NAV history)
    return_1y = Column(Numeric(8, 4), nullable=True)  # 1 year return %
    return_3y = Column(Numeric(8, 4), nullable=True)  # 3 year return %
    return_5y = Column(Numeric(8, 4), nullable=True)  # 5 year return %
    return_10y = Column(Numeric(8, 4), nullable=True)  # 10 year return %
    
    # Risk Metrics
    volatility = Column(Numeric(8, 4), nullable=True)  # Standard deviation of returns
    sharpe_ratio = Column(Numeric(8, 4), nullable=True)  # Risk-adjusted return
    beta = Column(Numeric(8, 4), nullable=True)  # Market correlation
    alpha = Column(Numeric(8, 4), nullable=True)  # Excess return vs benchmark
    
    # Fund Size & Costs
    aum = Column(Numeric(18, 2), nullable=True)  # Assets Under Management (in crores)
    expense_ratio = Column(Numeric(6, 4), nullable=True)  # Expense ratio %
    exit_load = Column(String(100), nullable=True)  # Exit load details
    
    # Recommendation Score (calculated by recommendation engine)
    recommendation_score = Column(Numeric(8, 2), nullable=True)  # 0-100 score
    recommendation_rank = Column(Integer, nullable=True)  # Rank among all funds
    recommendation_reason = Column(Text, nullable=True)  # Why this score
    
    # Ratings
    value_research_rating = Column(Integer, nullable=True)  # 1-5 stars from Value Research
    
    # Metadata
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(Text, nullable=True)
    is_active = Column(String(1), default='Y')
    
    __table_args__ = (
        Index('idx_mf_research_category', 'fund_category'),
        Index('idx_mf_research_score', 'recommendation_score'),
        Index('idx_mf_research_rank', 'recommendation_rank'),
    )


class MutualFundNAVHistory(BaseModel):
    """Historical NAV data for mutual funds."""
    
    __tablename__ = "mutual_fund_nav_history"
    
    scheme_code = Column(String(20), nullable=False)
    nav_date = Column(Date, nullable=False)
    nav = Column(Numeric(18, 4), nullable=False)
    
    # Metadata
    source = Column(String(50), default='mfapi.in')
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('scheme_code', 'nav_date', name='uq_mf_nav_history'),
        Index('idx_mf_nav_scheme_date', 'scheme_code', 'nav_date'),
    )

