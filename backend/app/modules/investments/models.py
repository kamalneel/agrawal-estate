"""
Investment module database models.
"""

from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Text, UniqueConstraint, Index
from datetime import datetime

from app.shared.models.base import BaseModel


class InvestmentAccount(BaseModel):
    """Investment accounts (Robinhood, Schwab, 401k, etc.)."""
    
    __tablename__ = "investment_accounts"
    
    source = Column(String(50), nullable=False)  # 'robinhood', 'schwab'
    account_id = Column(String(100), nullable=False)  # ID from source
    account_name = Column(String(200), nullable=True)
    account_type = Column(String(50), nullable=True)  # 'brokerage', '401k', 'ira', 'roth_ira'
    institution = Column(String(100), nullable=True)
    
    is_active = Column(String(1), default='Y')
    
    __table_args__ = (
        UniqueConstraint('source', 'account_id', name='uq_investment_account'),
    )


class InvestmentTransaction(BaseModel):
    """Investment transactions with deduplication support."""
    
    __tablename__ = "investment_transactions"
    
    # Natural key fields for deduplication
    source = Column(String(50), nullable=False)
    account_id = Column(String(100), nullable=False)
    transaction_date = Column(Date, nullable=False)
    transaction_type = Column(String(20), nullable=False)  # BUY, SELL, DIVIDEND, TRANSFER, SPLIT
    symbol = Column(String(20), nullable=False)
    quantity = Column(Numeric(18, 8), nullable=True)
    amount = Column(Numeric(18, 2), nullable=False)
    
    # Additional fields
    price_per_share = Column(Numeric(18, 4), nullable=True)
    fees = Column(Numeric(18, 2), default=0)
    description = Column(Text, nullable=True)
    
    # Deduplication hash
    record_hash = Column(String(64), nullable=False, index=True)
    
    # Provenance
    ingestion_id = Column(Integer, nullable=True)
    
    __table_args__ = (
        UniqueConstraint(
            'source', 'account_id', 'transaction_date', 
            'transaction_type', 'symbol', 'quantity', 'amount',
            name='uq_investment_transaction'
        ),
        Index('idx_transaction_date', 'transaction_date'),
        Index('idx_transaction_symbol', 'symbol'),
    )


class InvestmentHolding(BaseModel):
    """Current holdings/positions - updated with each import."""
    
    __tablename__ = "investment_holdings"
    
    # Natural key
    source = Column(String(50), nullable=False)
    account_id = Column(String(100), nullable=False)
    symbol = Column(String(20), nullable=False)
    
    # Current values (updated on each import)
    quantity = Column(Numeric(18, 8), nullable=False)
    cost_basis = Column(Numeric(18, 2), nullable=True)
    current_price = Column(Numeric(18, 4), nullable=True)
    market_value = Column(Numeric(18, 2), nullable=True)
    
    # Metadata
    description = Column(String(200), nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow)
    ingestion_id = Column(Integer, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('source', 'account_id', 'symbol', name='uq_holding'),
    )


class InvestmentHoldingHistory(BaseModel):
    """Historical snapshots of holdings for tracking value over time."""
    
    __tablename__ = "investment_holdings_history"
    
    source = Column(String(50), nullable=False)
    account_id = Column(String(100), nullable=False)
    symbol = Column(String(20), nullable=False)
    snapshot_date = Column(Date, nullable=False)
    
    quantity = Column(Numeric(18, 8), nullable=False)
    market_value = Column(Numeric(18, 2), nullable=True)
    
    __table_args__ = (
        UniqueConstraint('source', 'account_id', 'symbol', 'snapshot_date', name='uq_holding_history'),
    )


class PortfolioSnapshot(BaseModel):
    """Monthly portfolio value snapshots from account statements."""
    
    __tablename__ = "portfolio_snapshots"
    
    # Which account this snapshot is for
    source = Column(String(50), nullable=False)  # 'robinhood', 'schwab'
    account_id = Column(String(100), nullable=False)
    owner = Column(String(50), nullable=True)  # 'Neel', 'Jaya'
    account_type = Column(String(50), nullable=True)  # 'brokerage', 'ira'
    
    # Statement period
    statement_date = Column(Date, nullable=False)  # End date of statement period
    
    # Values from statement
    portfolio_value = Column(Numeric(18, 2), nullable=False)
    cash_balance = Column(Numeric(18, 2), nullable=True)
    securities_value = Column(Numeric(18, 2), nullable=True)
    
    # Provenance
    ingestion_id = Column(Integer, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('source', 'account_id', 'statement_date', name='uq_portfolio_snapshot'),
        Index('idx_snapshot_date', 'statement_date'),
        Index('idx_snapshot_owner', 'owner'),
    )

