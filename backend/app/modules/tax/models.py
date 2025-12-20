"""
Tax module database models.
"""

from sqlalchemy import Column, Integer, String, Numeric, Date, Text, UniqueConstraint, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.shared.models.base import BaseModel


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

