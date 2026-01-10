"""
Tax module database models.
"""

from sqlalchemy import Column, Integer, String, Numeric, Date, Text, UniqueConstraint, ForeignKey, Index, Boolean, DateTime
from sqlalchemy.orm import relationship

from app.shared.models.base import BaseModel, TimestampMixin
from app.core.database import Base


class TaxProperty(BaseModel):
    """Properties for tax tracking."""
    
    __tablename__ = "tax_properties"
    
    address = Column(String(500), nullable=False)
    city = Column(String(100), nullable=True)
    state = Column(String(50), nullable=True)
    zip_code = Column(String(20), nullable=True)
    county = Column(String(100), nullable=True)
    
    parcel_number = Column(String(100), nullable=True)  # Tax parcel/APN number
    property_type = Column(String(50), nullable=True)  # 'primary_residence', 'rental', 'land'
    
    acquired_date = Column(Date, nullable=True)
    disposed_date = Column(Date, nullable=True)
    
    is_active = Column(String(1), default='Y')
    
    # Relationships
    tax_records = relationship("PropertyTaxRecord", back_populates="property")


class PropertyTaxRecord(BaseModel):
    """Annual property tax records - supports 20+ years of history."""
    
    __tablename__ = "property_tax_records"
    
    property_id = Column(Integer, ForeignKey("tax_properties.id"), nullable=False)
    
    tax_year = Column(Integer, nullable=False)
    installment = Column(Integer, default=1)  # Some counties have 2 installments
    
    assessed_value = Column(Numeric(18, 2), nullable=True)
    land_value = Column(Numeric(18, 2), nullable=True)
    improvement_value = Column(Numeric(18, 2), nullable=True)
    
    tax_amount = Column(Numeric(18, 2), nullable=False)
    paid_amount = Column(Numeric(18, 2), nullable=True)
    paid_date = Column(Date, nullable=True)
    
    due_date = Column(Date, nullable=True)
    is_paid = Column(String(1), default='N')
    
    notes = Column(Text, nullable=True)
    
    # Provenance
    ingestion_id = Column(Integer, nullable=True)
    
    # Relationships
    property = relationship("TaxProperty", back_populates="tax_records")
    
    __table_args__ = (
        UniqueConstraint('property_id', 'tax_year', 'installment', name='uq_property_tax_record'),
        Index('idx_tax_year', 'tax_year'),
    )


class TaxDocument(BaseModel):
    """Tax-related documents (bills, receipts, returns)."""
    
    __tablename__ = "tax_documents"
    
    property_id = Column(Integer, ForeignKey("tax_properties.id"), nullable=True)
    
    document_type = Column(String(50), nullable=False)  # 'tax_bill', 'receipt', 'return'
    tax_year = Column(Integer, nullable=True)
    
    title = Column(String(200), nullable=False)
    file_path = Column(String(500), nullable=True)
    
    notes = Column(Text, nullable=True)


class IncomeTaxReturn(BaseModel):
    """Income tax return records."""
    
    __tablename__ = "income_tax_returns"
    
    tax_year = Column(Integer, nullable=False, unique=True)
    
    # Federal Tax
    agi = Column(Numeric(18, 2), nullable=True)  # Adjusted Gross Income
    federal_tax = Column(Numeric(18, 2), nullable=True)  # Total federal tax
    federal_withheld = Column(Numeric(18, 2), nullable=True)  # Amount withheld
    federal_owed = Column(Numeric(18, 2), nullable=True)  # Amount owed with return
    federal_refund = Column(Numeric(18, 2), nullable=True)  # Refund received
    
    # State Tax
    state_tax = Column(Numeric(18, 2), nullable=True)  # Total state tax
    state_withheld = Column(Numeric(18, 2), nullable=True)  # Amount withheld
    state_owed = Column(Numeric(18, 2), nullable=True)  # Amount owed with return
    state_refund = Column(Numeric(18, 2), nullable=True)  # Refund received
    
    # Other
    effective_rate = Column(Numeric(5, 2), nullable=True)  # Effective tax rate
    filing_status = Column(String(50), nullable=True)  # 'single', 'mfj', 'mfs', 'hoh'
    
    source_file = Column(String(500), nullable=True)  # Source PDF file
    details_json = Column(Text, nullable=True)  # JSON with detailed breakdown
    
    # Provenance
    ingestion_id = Column(Integer, nullable=True)
    
    __table_args__ = (
        Index('idx_income_tax_year', 'tax_year'),
    )


class StockLot(Base, TimestampMixin):
    """
    Stock lot for cost basis tracking.

    Each lot represents a purchase of shares at a specific price on a specific date.
    Used for accurate capital gains calculations with FIFO, LIFO, or specific ID methods.
    """

    __tablename__ = "stock_lot"

    lot_id = Column(Integer, primary_key=True, autoincrement=True)

    # Stock identification
    symbol = Column(String(20), nullable=False)

    # Purchase details
    purchase_date = Column(Date, nullable=False)
    quantity = Column(Numeric(18, 6), nullable=False)  # Original quantity purchased
    cost_basis = Column(Numeric(18, 2), nullable=False)  # Total cost basis
    cost_per_share = Column(Numeric(18, 4), nullable=False)  # Cost per share

    # Account tracking
    account_id = Column(String(50), nullable=True)  # Which account (Robinhood, ETrade, etc)
    source = Column(String(50), nullable=False)  # 'robinhood', 'etrade', 'manual', etc.
    purchase_transaction_id = Column(Integer, nullable=True)  # Link to original transaction if available

    # Remaining quantity (decreases as shares are sold)
    quantity_remaining = Column(Numeric(18, 6), nullable=False)

    # Status
    status = Column(String(20), nullable=False, default='open')  # 'open', 'closed', 'partial'

    # Lot matching method
    lot_method = Column(String(20), nullable=True)  # 'FIFO', 'LIFO', 'specific_id', 'avg_cost'

    # Notes
    notes = Column(Text, nullable=True)

    # Relationships
    sales = relationship("StockLotSale", back_populates="lot", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_stock_lot_symbol', 'symbol'),
        Index('idx_stock_lot_source', 'source'),
        Index('idx_stock_lot_status', 'status'),
        Index('idx_stock_lot_purchase_date', 'purchase_date'),
    )


class StockLotSale(Base, TimestampMixin):
    """
    Stock lot sale record - matches a sale to a specific lot.

    When shares are sold, this table tracks which lot(s) the shares came from
    and calculates the realized gain/loss for tax purposes.
    """

    __tablename__ = "stock_lot_sale"

    sale_id = Column(Integer, primary_key=True, autoincrement=True)

    # Link to the lot being sold from
    lot_id = Column(Integer, ForeignKey("stock_lot.lot_id", ondelete="CASCADE"), nullable=False)

    # Sale details
    sale_date = Column(Date, nullable=False)
    sale_transaction_id = Column(Integer, nullable=True)  # Link to original transaction if available

    # Quantity and proceeds
    quantity_sold = Column(Numeric(18, 6), nullable=False)
    proceeds = Column(Numeric(18, 2), nullable=False)  # Total proceeds from sale
    proceeds_per_share = Column(Numeric(18, 4), nullable=False)  # Sale price per share

    # Cost basis for this portion
    cost_basis = Column(Numeric(18, 2), nullable=False)  # Cost basis of shares sold

    # Gain/Loss calculation
    gain_loss = Column(Numeric(18, 2), nullable=False)  # Proceeds - Cost Basis

    # Holding period
    holding_period_days = Column(Integer, nullable=False)  # Days between purchase and sale
    is_long_term = Column(Boolean, nullable=False)  # True if held > 365 days

    # Tax year
    tax_year = Column(Integer, nullable=False)  # Year when gain/loss is realized

    # Wash sale tracking
    wash_sale = Column(Boolean, nullable=False, default=False)  # True if this is a wash sale
    wash_sale_disallowed = Column(Numeric(18, 2), nullable=True)  # Loss disallowed due to wash sale

    # Notes
    notes = Column(Text, nullable=True)

    # Relationships
    lot = relationship("StockLot", back_populates="sales")

    __table_args__ = (
        Index('idx_stock_lot_sale_lot', 'lot_id'),
        Index('idx_stock_lot_sale_tax_year', 'tax_year'),
        Index('idx_stock_lot_sale_date', 'sale_date'),
        Index('idx_stock_lot_sale_is_long_term', 'is_long_term'),
    )

