"""
Cash module database models.

Tracks cash balances across:
- Bank accounts (Bank of America, Chase)
- Brokerage accounts (Robinhood cash balances)
"""

from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Text, UniqueConstraint, Index
from datetime import datetime

from app.shared.models.base import BaseModel


class CashAccount(BaseModel):
    """Bank and brokerage cash accounts."""
    
    __tablename__ = "cash_accounts"
    
    # Account identification
    source = Column(String(50), nullable=False)  # 'bank_of_america', 'chase', 'robinhood'
    account_id = Column(String(100), nullable=False)  # Account number (masked)
    account_name = Column(String(200), nullable=True)  # "Checking", "Savings", "Brokerage"
    account_type = Column(String(50), nullable=True)  # 'checking', 'savings', 'brokerage', 'money_market'
    owner = Column(String(50), nullable=True)  # 'Neel', 'Jaya', 'Joint'
    
    # Current balance (latest known)
    current_balance = Column(Numeric(18, 2), nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    is_active = Column(String(1), default='Y')
    
    __table_args__ = (
        UniqueConstraint('source', 'account_id', name='uq_cash_account'),
        Index('idx_cash_account_owner', 'owner'),
    )


class CashSnapshot(BaseModel):
    """Historical cash balance snapshots from statements."""
    
    __tablename__ = "cash_snapshots"
    
    # Account reference
    source = Column(String(50), nullable=False)
    account_id = Column(String(100), nullable=False)
    owner = Column(String(50), nullable=True)
    account_type = Column(String(50), nullable=True)
    
    # Snapshot date (statement date)
    snapshot_date = Column(Date, nullable=False)
    
    # Balance
    balance = Column(Numeric(18, 2), nullable=False)
    
    # Optional details from statement
    statement_period_start = Column(Date, nullable=True)
    statement_period_end = Column(Date, nullable=True)
    
    # Provenance
    ingestion_id = Column(Integer, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('source', 'account_id', 'snapshot_date', name='uq_cash_snapshot'),
        Index('idx_cash_snapshot_date', 'snapshot_date'),
        Index('idx_cash_snapshot_owner', 'owner'),
    )


class CashTransaction(BaseModel):
    """Cash transactions (deposits, withdrawals, transfers)."""
    
    __tablename__ = "cash_transactions"
    
    # Account reference
    source = Column(String(50), nullable=False)
    account_id = Column(String(100), nullable=False)
    
    # Transaction details
    transaction_date = Column(Date, nullable=False)
    transaction_type = Column(String(50), nullable=False)  # 'deposit', 'withdrawal', 'transfer', 'interest', 'fee'
    description = Column(Text, nullable=True)
    amount = Column(Numeric(18, 2), nullable=False)  # Positive for deposits, negative for withdrawals
    
    # Running balance (if available)
    running_balance = Column(Numeric(18, 2), nullable=True)
    
    # Deduplication
    record_hash = Column(String(64), nullable=True, index=True)
    
    # Provenance
    ingestion_id = Column(Integer, nullable=True)
    
    __table_args__ = (
        Index('idx_cash_transaction_date', 'transaction_date'),
        Index('idx_cash_transaction_account', 'source', 'account_id'),
    )



