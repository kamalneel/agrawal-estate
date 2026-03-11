"""
Real estate module database models.
"""

from sqlalchemy import Column, Integer, String, Numeric, Date, Text, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship

from app.shared.models.base import BaseModel


class Property(BaseModel):
    """Real estate properties."""

    __tablename__ = "properties"

    address = Column(String(500), nullable=False)
    city = Column(String(100), nullable=True)
    state = Column(String(50), nullable=True)
    zip_code = Column(String(20), nullable=True)

    property_type = Column(String(50), nullable=False)  # 'primary_residence', 'rental', 'vacation', 'land'

    purchase_date = Column(Date, nullable=True)
    purchase_price = Column(Numeric(18, 2), nullable=True)

    current_value = Column(Numeric(18, 2), nullable=True)
    current_value_date = Column(Date, nullable=True)

    square_feet = Column(Integer, nullable=True)
    lot_size = Column(Numeric(10, 2), nullable=True)  # Acres
    bedrooms = Column(Integer, nullable=True)
    bathrooms = Column(Numeric(3, 1), nullable=True)
    year_built = Column(Integer, nullable=True)

    is_active = Column(String(1), default='Y')
    sold_date = Column(Date, nullable=True)
    sold_price = Column(Numeric(18, 2), nullable=True)

    notes = Column(Text, nullable=True)

    # Relationships
    mortgages = relationship("Mortgage", back_populates="property")
    valuations = relationship("PropertyValuation", back_populates="property")
    rental_agreements = relationship("RentalAgreement", back_populates="property", cascade="all, delete-orphan")
    rental_annual_summaries = relationship("PropertyRentalSummary", back_populates="property", cascade="all, delete-orphan")
    rental_expenses = relationship("PropertyRentalExpense", back_populates="property", cascade="all, delete-orphan")
    rental_documents = relationship("RentalDocument", back_populates="property", cascade="all, delete-orphan")


class Mortgage(BaseModel):
    """Mortgages/loans on properties."""
    
    __tablename__ = "mortgages"
    
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    
    lender = Column(String(200), nullable=False)
    loan_number = Column(String(100), nullable=True)
    loan_type = Column(String(50), nullable=True)  # 'conventional', 'fha', 'va', 'jumbo'
    
    original_amount = Column(Numeric(18, 2), nullable=False)
    current_balance = Column(Numeric(18, 2), nullable=True)
    balance_as_of_date = Column(Date, nullable=True)
    
    interest_rate = Column(Numeric(5, 3), nullable=True)  # e.g., 6.500
    is_fixed_rate = Column(String(1), default='Y')
    
    start_date = Column(Date, nullable=True)
    term_months = Column(Integer, nullable=True)  # e.g., 360 for 30-year
    maturity_date = Column(Date, nullable=True)
    
    monthly_payment = Column(Numeric(18, 2), nullable=True)
    escrow_amount = Column(Numeric(18, 2), nullable=True)
    
    is_active = Column(String(1), default='Y')
    paid_off_date = Column(Date, nullable=True)
    
    notes = Column(Text, nullable=True)
    
    # Relationships
    property = relationship("Property", back_populates="mortgages")
    payments = relationship("MortgagePayment", back_populates="mortgage")


class MortgagePayment(BaseModel):
    """Individual mortgage payments."""
    
    __tablename__ = "mortgage_payments"
    
    mortgage_id = Column(Integer, ForeignKey("mortgages.id"), nullable=False)
    
    payment_date = Column(Date, nullable=False)
    total_payment = Column(Numeric(18, 2), nullable=False)
    
    principal = Column(Numeric(18, 2), nullable=True)
    interest = Column(Numeric(18, 2), nullable=True)
    escrow = Column(Numeric(18, 2), nullable=True)
    extra_principal = Column(Numeric(18, 2), nullable=True)
    
    remaining_balance = Column(Numeric(18, 2), nullable=True)
    
    # Provenance
    ingestion_id = Column(Integer, nullable=True)
    
    # Relationships
    mortgage = relationship("Mortgage", back_populates="payments")
    
    __table_args__ = (
        Index('idx_payment_date', 'payment_date'),
    )


class PropertyValuation(BaseModel):
    """Property valuations/appraisals over time."""
    
    __tablename__ = "property_valuations"
    
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    
    valuation_date = Column(Date, nullable=False)
    value = Column(Numeric(18, 2), nullable=False)
    
    valuation_source = Column(String(100), nullable=True)  # 'appraisal', 'zillow', 'redfin', 'manual'
    
    notes = Column(Text, nullable=True)
    
    # Relationships
    property = relationship("Property", back_populates="valuations")
    
    __table_args__ = (
        Index('idx_valuation_date', 'valuation_date'),
    )


class RentalAgreement(BaseModel):
    """Rental/lease agreements for a property."""

    __tablename__ = "rental_agreements"

    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    lease_start_date = Column(Date, nullable=False)
    lease_end_date = Column(Date, nullable=False)
    tenant_names = Column(String(500), nullable=False)
    monthly_rent = Column(Numeric(10, 2), nullable=False)
    monthly_hoa = Column(Numeric(10, 2), nullable=True)
    security_deposit = Column(Numeric(10, 2), nullable=True)
    notes = Column(Text, nullable=True)

    property = relationship("Property", back_populates="rental_agreements")

    __table_args__ = (
        UniqueConstraint('property_id', 'lease_start_date', name='uq_rental_agreement_property_start'),
        Index('idx_rental_agreement_property', 'property_id'),
    )


class PropertyRentalSummary(BaseModel):
    """Annual income summary for a rental property."""

    __tablename__ = "rental_annual_summaries_v2"

    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    tax_year = Column(Integer, nullable=False)
    annual_income = Column(Numeric(12, 2), nullable=True)
    cost_of_property = Column(Numeric(12, 2), nullable=True)

    property = relationship("Property", back_populates="rental_annual_summaries")

    __table_args__ = (
        UniqueConstraint('property_id', 'tax_year', name='uq_rental_annual_summary_v2'),
        Index('idx_rental_annual_summary_v2_property', 'property_id'),
    )


class PropertyRentalExpense(BaseModel):
    """Annual expenses by category for a rental property (IRS Schedule E)."""

    __tablename__ = "rental_annual_expenses"

    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    tax_year = Column(Integer, nullable=False)
    category = Column(String(100), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False, default=0)
    description = Column(Text, nullable=True)

    property = relationship("Property", back_populates="rental_expenses")

    __table_args__ = (
        UniqueConstraint('property_id', 'tax_year', 'category', name='uq_rental_expense_year_cat'),
        Index('idx_rental_expense_property_year', 'property_id', 'tax_year'),
    )


class RentalDocument(BaseModel):
    """Uploaded documents for a rental property."""

    __tablename__ = "rental_documents"

    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    document_type = Column(String(50), nullable=False)  # lease_agreement, tax_record, other
    tax_year = Column(Integer, nullable=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(64), nullable=True)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)

    property = relationship("Property", back_populates="rental_documents")

    __table_args__ = (
        Index('idx_rental_doc_property', 'property_id'),
    )

