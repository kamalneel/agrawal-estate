"""
India Investments module database models.
"""

from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Text, UniqueConstraint, Index, ForeignKey
from datetime import datetime

from app.shared.models.base import BaseModel


class IndiaBankAccount(BaseModel):
    """Bank accounts in India (ICICI, SBI, PNB, etc.)."""
    
    __tablename__ = "india_bank_accounts"
    
    account_name = Column(String(200), nullable=False)  # e.g., "ICICI Bank", "SBI Account"
    bank_name = Column(String(100), nullable=False)  # e.g., "ICICI", "SBI", "PNB"
    account_number = Column(String(100), nullable=True)
    owner = Column(String(50), nullable=False)  # 'Neel' or 'Father'
    account_type = Column(String(50), nullable=True)  # 'savings', 'current', 'fd'
    
    # Cash balance (for savings/current accounts)
    cash_balance = Column(Numeric(18, 2), default=0)
    
    # Metadata
    is_active = Column(String(1), default='Y')
    notes = Column(Text, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('bank_name', 'account_number', 'owner', name='uq_india_bank_account'),
    )


class IndiaInvestmentAccount(BaseModel):
    """Investment accounts in India (Zerodha, etc.)."""
    
    __tablename__ = "india_investment_accounts"
    
    account_name = Column(String(200), nullable=False)  # e.g., "Zerodha Account 1"
    platform = Column(String(100), nullable=False)  # e.g., "Zerodha"
    account_number = Column(String(100), nullable=True)
    owner = Column(String(50), nullable=False)  # 'Neel' or 'Father'
    
    # Linked bank account (informational)
    linked_bank_account_id = Column(Integer, ForeignKey('india_bank_accounts.id'), nullable=True)
    
    # Metadata
    is_active = Column(String(1), default='Y')
    notes = Column(Text, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('platform', 'account_number', 'owner', name='uq_india_investment_account'),
    )


class IndiaStock(BaseModel):
    """Stocks held in Indian investment accounts."""
    
    __tablename__ = "india_stocks"
    
    investment_account_id = Column(Integer, ForeignKey('india_investment_accounts.id'), nullable=False)
    symbol = Column(String(20), nullable=False)  # NSE/BSE symbol
    company_name = Column(String(200), nullable=True)
    
    # Holdings
    quantity = Column(Numeric(18, 8), nullable=False)
    average_price = Column(Numeric(18, 4), nullable=True)  # Average purchase price
    current_price = Column(Numeric(18, 4), nullable=True)  # Current market price
    
    # Values
    cost_basis = Column(Numeric(18, 2), nullable=True)  # Total cost
    current_value = Column(Numeric(18, 2), nullable=True)  # Current market value
    profit_loss = Column(Numeric(18, 2), nullable=True)  # P&L
    
    # Metadata
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('investment_account_id', 'symbol', name='uq_india_stock'),
        Index('idx_india_stock_symbol', 'symbol'),
    )


class IndiaMutualFund(BaseModel):
    """Mutual funds held in Indian investment accounts."""
    
    __tablename__ = "india_mutual_funds"
    
    investment_account_id = Column(Integer, ForeignKey('india_investment_accounts.id'), nullable=False)
    fund_name = Column(String(200), nullable=False)
    fund_code = Column(String(50), nullable=True)  # AMFI code or similar
    category = Column(String(50), nullable=False)  # 'india_fund' or 'international_fund'
    
    # Holdings
    units = Column(Numeric(18, 8), nullable=False)
    nav = Column(Numeric(18, 4), nullable=True)  # Net Asset Value per unit
    purchase_price = Column(Numeric(18, 4), nullable=True)  # Average purchase NAV
    
    # Values
    cost_basis = Column(Numeric(18, 2), nullable=True)  # Total investment
    current_value = Column(Numeric(18, 2), nullable=True)  # Current value (units × NAV)
    profit_loss = Column(Numeric(18, 2), nullable=True)  # P&L
    
    # Metadata
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('investment_account_id', 'fund_name', 'fund_code', name='uq_india_mutual_fund'),
        Index('idx_india_mf_category', 'category'),
    )


class IndiaFixedDeposit(BaseModel):
    """Fixed deposits in Indian bank accounts."""
    
    __tablename__ = "india_fixed_deposits"
    
    bank_account_id = Column(Integer, ForeignKey('india_bank_accounts.id'), nullable=False)
    fd_number = Column(String(100), nullable=True)
    description = Column(String(200), nullable=True)
    
    # FD details
    principal = Column(Numeric(18, 2), nullable=False)  # Initial deposit amount
    interest_rate = Column(Numeric(5, 2), nullable=False)  # Annual interest rate (e.g., 7.5)
    start_date = Column(Date, nullable=False)
    maturity_date = Column(Date, nullable=False)
    
    # Calculated values
    current_value = Column(Numeric(18, 2), nullable=True)  # Principal + accrued interest
    accrued_interest = Column(Numeric(18, 2), nullable=True)  # Interest accrued so far
    maturity_value = Column(Numeric(18, 2), nullable=True)  # Value at maturity
    
    # Metadata
    is_active = Column(String(1), default='Y')
    notes = Column(Text, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('bank_account_id', 'fd_number', name='uq_india_fd'),
        Index('idx_india_fd_maturity', 'maturity_date'),
    )


class ExchangeRate(BaseModel):
    """USD to INR exchange rate for dashboard conversion."""
    
    __tablename__ = "exchange_rates"
    
    from_currency = Column(String(3), nullable=False, default='USD')
    to_currency = Column(String(3), nullable=False, default='INR')
    rate = Column(Numeric(10, 4), nullable=False)  # 1 USD = X INR
    
    # Metadata
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(50), nullable=True)  # User who updated
    
    __table_args__ = (
        UniqueConstraint('from_currency', 'to_currency', name='uq_exchange_rate'),
    )


class FatherMutualFundHolding(BaseModel):
    """Father's mutual fund holdings with detailed tracking."""
    
    __tablename__ = "father_mutual_fund_holdings"
    
    # Investment details
    investment_date = Column(Date, nullable=False)  # Date when investment was made
    fund_name = Column(String(300), nullable=False)  # Name of the mutual fund
    folio_number = Column(String(50), nullable=True)  # Folio number
    
    # Fund identifiers (for API lookups)
    scheme_code = Column(String(20), nullable=True)  # AMFI scheme code
    isin = Column(String(20), nullable=True)  # ISIN for Kuvera API
    
    # Amounts
    initial_invested_amount = Column(Numeric(18, 2), nullable=False)  # Initial investment
    amount_march_2025 = Column(Numeric(18, 2), nullable=True)  # Amount as of March 31, 2025
    current_amount = Column(Numeric(18, 2), nullable=True)  # Current/latest amount
    
    # Performance metrics (in percentage)
    return_1y = Column(Numeric(8, 2), nullable=True)  # 1-year return %
    return_3y = Column(Numeric(8, 2), nullable=True)  # 3-year return %
    return_5y = Column(Numeric(8, 2), nullable=True)  # 5-year return %
    return_10y = Column(Numeric(8, 2), nullable=True)  # 10-year return %
    
    # Risk metrics (from Kuvera API)
    volatility = Column(Numeric(8, 4), nullable=True)  # Standard deviation
    sharpe_ratio = Column(Numeric(8, 4), nullable=True)  # Risk-adjusted return
    alpha = Column(Numeric(8, 4), nullable=True)  # Excess return vs benchmark
    beta = Column(Numeric(8, 4), nullable=True)  # Market correlation
    
    # Fund details (from Kuvera API)
    aum = Column(Numeric(18, 2), nullable=True)  # Assets Under Management (in crores)
    expense_ratio = Column(Numeric(6, 4), nullable=True)  # Expense ratio %
    fund_rating = Column(Integer, nullable=True)  # 1-5 stars (Kuvera rating)
    fund_start_date = Column(Date, nullable=True)  # Fund inception date
    crisil_rating = Column(String(50), nullable=True)  # CRISIL risk rating
    
    # Optional metadata
    fund_category = Column(String(100), nullable=True)  # e.g., "Equity", "Debt", "Hybrid"
    notes = Column(Text, nullable=True)
    
    # Timestamps
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_father_mf_fund_name', 'fund_name'),
        Index('idx_father_mf_investment_date', 'investment_date'),
    )


class FatherStockHolding(BaseModel):
    """Father's stock holdings with detailed tracking."""
    
    __tablename__ = "father_stock_holdings"
    
    # Investment details
    investment_date = Column(Date, nullable=False)  # Date when investment was made
    symbol = Column(String(20), nullable=False)  # NSE/BSE symbol (e.g., RELIANCE)
    company_name = Column(String(200), nullable=True)  # Full company name
    
    # Holdings
    quantity = Column(Numeric(18, 4), nullable=False)  # Number of shares
    average_price = Column(Numeric(18, 4), nullable=True)  # Average purchase price per share
    
    # Values
    initial_invested_amount = Column(Numeric(18, 2), nullable=False)  # Total cost basis
    amount_march_2025 = Column(Numeric(18, 2), nullable=True)  # Value as of March 31, 2025
    current_price = Column(Numeric(18, 4), nullable=True)  # Current market price per share
    current_amount = Column(Numeric(18, 2), nullable=True)  # Current market value
    
    # Optional metadata
    sector = Column(String(100), nullable=True)  # e.g., "Oil & Gas", "IT"
    notes = Column(Text, nullable=True)
    
    # Timestamps
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_father_stock_symbol', 'symbol'),
        Index('idx_father_stock_investment_date', 'investment_date'),
    )

