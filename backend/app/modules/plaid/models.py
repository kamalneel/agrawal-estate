"""
Plaid database models for storing linked accounts and access tokens.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class PlaidItem(Base):
    """
    Represents a Plaid Item (a connection to a financial institution).
    Each Item can have multiple accounts.
    """
    __tablename__ = "plaid_items"
    
    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(String(255), unique=True, nullable=False, index=True)
    access_token = Column(Text, nullable=False)  # Encrypted in production
    institution_id = Column(String(100), nullable=True)
    institution_name = Column(String(255), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Consent expiration (for European institutions)
    consent_expiration_time = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime, nullable=True)
    
    # Relationships
    accounts = relationship("PlaidAccount", back_populates="item", cascade="all, delete-orphan")


class PlaidAccount(Base):
    """
    Represents a single account from a Plaid Item.
    Stores account metadata and sync status.
    """
    __tablename__ = "plaid_accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("plaid_items.id"), nullable=False)
    account_id = Column(String(255), unique=True, nullable=False, index=True)
    
    # Account details
    name = Column(String(255), nullable=False)
    official_name = Column(String(255), nullable=True)
    type = Column(String(50), nullable=False)  # investment, depository, credit, etc.
    subtype = Column(String(50), nullable=True)  # brokerage, 401k, checking, etc.
    mask = Column(String(10), nullable=True)  # Last 4 digits
    
    # Current balances (updated on sync)
    current_balance = Column(String(50), nullable=True)
    available_balance = Column(String(50), nullable=True)
    iso_currency_code = Column(String(10), default="USD")
    
    # Status
    is_active = Column(Boolean, default=True)
    is_hidden = Column(Boolean, default=False)  # User can hide accounts
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    item = relationship("PlaidItem", back_populates="accounts")


class PlaidInvestmentTransaction(Base):
    """
    Stores investment transactions fetched from Plaid.
    Used for RLHF reconciliation.
    """
    __tablename__ = "plaid_investment_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(String(255), nullable=False, index=True)
    investment_transaction_id = Column(String(255), unique=True, nullable=False, index=True)
    
    # Transaction details
    date = Column(DateTime, nullable=False, index=True)
    name = Column(String(500), nullable=False)
    type = Column(String(50), nullable=False)  # buy, sell, transfer, etc.
    subtype = Column(String(50), nullable=True)
    
    # Security info
    security_id = Column(String(255), nullable=True)
    ticker_symbol = Column(String(20), nullable=True, index=True)
    security_name = Column(String(255), nullable=True)
    security_type = Column(String(50), nullable=True)  # equity, option, etf, etc.
    
    # Option-specific fields
    option_type = Column(String(10), nullable=True)  # call, put
    strike_price = Column(String(50), nullable=True)
    expiration_date = Column(DateTime, nullable=True)
    underlying_symbol = Column(String(20), nullable=True)
    
    # Amounts
    quantity = Column(String(50), nullable=True)
    price = Column(String(50), nullable=True)
    amount = Column(String(50), nullable=True)  # Total transaction amount
    fees = Column(String(50), nullable=True)
    
    iso_currency_code = Column(String(10), default="USD")
    
    # Raw data for debugging
    raw_data = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Index for efficient queries
    __table_args__ = (
        # Composite index for date range queries by ticker
        # Index('ix_plaid_txn_ticker_date', 'ticker_symbol', 'date'),
    )


class PlaidHolding(Base):
    """
    Stores current holdings/positions fetched from Plaid.
    Updated on each sync.
    """
    __tablename__ = "plaid_holdings"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(String(255), nullable=False, index=True)
    security_id = Column(String(255), nullable=True)
    
    # Security info
    ticker_symbol = Column(String(20), nullable=True, index=True)
    security_name = Column(String(255), nullable=True)
    security_type = Column(String(50), nullable=True)
    
    # Option-specific
    option_type = Column(String(10), nullable=True)
    strike_price = Column(String(50), nullable=True)
    expiration_date = Column(DateTime, nullable=True)
    underlying_symbol = Column(String(20), nullable=True)
    
    # Position details
    quantity = Column(String(50), nullable=False)
    cost_basis = Column(String(50), nullable=True)
    institution_price = Column(String(50), nullable=True)
    institution_value = Column(String(50), nullable=True)
    institution_price_as_of = Column(DateTime, nullable=True)
    
    iso_currency_code = Column(String(10), default="USD")
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

