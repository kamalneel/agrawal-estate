"""
Income module database models.
"""

from sqlalchemy import Column, Integer, String, Numeric, Date, Text, UniqueConstraint, ForeignKey, Index, JSON
from sqlalchemy.orm import relationship

from app.shared.models.base import BaseModel


class RentalProperty(BaseModel):
    """Rental properties for tracking income and expenses."""
    
    __tablename__ = "rental_properties"
    
    property_address = Column(String(500), nullable=False, unique=True)
    property_name = Column(String(200), nullable=True)  # Optional friendly name
    
    # Property details
    purchase_date = Column(Date, nullable=True)
    purchase_price = Column(Numeric(18, 2), nullable=True)
    current_value = Column(Numeric(18, 2), nullable=True)
    
    is_active = Column(String(1), default='Y')
    notes = Column(Text, nullable=True)
    
    # Relationships
    annual_summaries = relationship("RentalAnnualSummary", back_populates="property")
    monthly_income = relationship("RentalMonthlyIncome", back_populates="property")
    expenses = relationship("RentalExpense", back_populates="property")


class RentalAnnualSummary(BaseModel):
    """Annual summary of rental income and expenses for a property."""
    
    __tablename__ = "rental_annual_summaries"
    
    property_id = Column(Integer, ForeignKey("rental_properties.id"), nullable=False)
    tax_year = Column(Integer, nullable=False)
    
    # Income
    annual_income = Column(Numeric(18, 2), nullable=False, default=0)
    
    # Total expenses (sum of all expense categories)
    total_expenses = Column(Numeric(18, 2), nullable=False, default=0)
    
    # Net income (income - expenses)
    net_income = Column(Numeric(18, 2), nullable=False, default=0)
    
    # JSON blob for expense breakdown (for quick access)
    expense_breakdown = Column(JSON, nullable=True)
    
    # Source tracking
    source_file = Column(String(500), nullable=True)
    ingestion_id = Column(Integer, nullable=True)
    
    # Relationships
    property = relationship("RentalProperty", back_populates="annual_summaries")
    
    __table_args__ = (
        UniqueConstraint('property_id', 'tax_year', name='uq_rental_annual_summary'),
        Index('idx_rental_summary_year', 'tax_year'),
    )


class RentalMonthlyIncome(BaseModel):
    """Monthly rental income entries."""
    
    __tablename__ = "rental_monthly_income"
    
    property_id = Column(Integer, ForeignKey("rental_properties.id"), nullable=False)
    tax_year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)  # 1-12
    
    gross_amount = Column(Numeric(18, 2), nullable=False)
    
    # Source tracking
    ingestion_id = Column(Integer, nullable=True)
    
    # Relationships
    property = relationship("RentalProperty", back_populates="monthly_income")
    
    __table_args__ = (
        UniqueConstraint('property_id', 'tax_year', 'month', name='uq_rental_monthly'),
        Index('idx_rental_monthly_year', 'tax_year'),
    )


class RentalExpense(BaseModel):
    """Individual rental expense entries by category."""
    
    __tablename__ = "rental_expenses"
    
    property_id = Column(Integer, ForeignKey("rental_properties.id"), nullable=False)
    tax_year = Column(Integer, nullable=False)
    
    category = Column(String(100), nullable=False)  # 'insurance', 'repairs', 'property_tax', etc.
    amount = Column(Numeric(18, 2), nullable=False)
    
    description = Column(Text, nullable=True)
    
    # Source tracking
    ingestion_id = Column(Integer, nullable=True)
    
    # Relationships
    property = relationship("RentalProperty", back_populates="expenses")
    
    __table_args__ = (
        UniqueConstraint('property_id', 'tax_year', 'category', name='uq_rental_expense'),
        Index('idx_rental_expense_year', 'tax_year'),
    )


class IncomeSource(BaseModel):
    """Income sources (employers, rental properties, investment accounts)."""
    
    __tablename__ = "income_sources"
    
    name = Column(String(200), nullable=False)
    income_type = Column(String(50), nullable=False)  # 'salary', 'stock', 'rental', 'passive'
    
    # For salary
    employer = Column(String(200), nullable=True)
    
    # For rental
    property_address = Column(String(500), nullable=True)
    
    # For stock/passive
    institution = Column(String(200), nullable=True)
    account_id = Column(String(100), nullable=True)
    
    is_active = Column(String(1), default='Y')
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    
    notes = Column(Text, nullable=True)
    
    # Relationships
    entries = relationship("IncomeEntry", back_populates="source")


class IncomeEntry(BaseModel):
    """Individual income entries."""
    
    __tablename__ = "income_entries"
    
    source_id = Column(Integer, ForeignKey("income_sources.id"), nullable=False)
    
    income_date = Column(Date, nullable=False)
    income_type = Column(String(50), nullable=False)  # Denormalized for easier querying
    
    gross_amount = Column(Numeric(18, 2), nullable=False)
    net_amount = Column(Numeric(18, 2), nullable=True)
    
    # For salary
    pay_period_start = Column(Date, nullable=True)
    pay_period_end = Column(Date, nullable=True)
    federal_tax = Column(Numeric(18, 2), nullable=True)
    state_tax = Column(Numeric(18, 2), nullable=True)
    social_security = Column(Numeric(18, 2), nullable=True)
    medicare = Column(Numeric(18, 2), nullable=True)
    other_deductions = Column(Numeric(18, 2), nullable=True)
    
    tax_year = Column(Integer, nullable=False)
    
    description = Column(Text, nullable=True)
    
    # Provenance
    ingestion_id = Column(Integer, nullable=True)
    
    # Relationships
    source = relationship("IncomeSource", back_populates="entries")
    
    __table_args__ = (
        # Natural key for deduplication
        UniqueConstraint('source_id', 'income_date', 'gross_amount', name='uq_income_entry'),
        Index('idx_income_date', 'income_date'),
        Index('idx_income_tax_year', 'tax_year'),
    )


class W2Record(BaseModel):
    """W-2 wage and tax statement data - persisted from parsed W-2 PDFs."""
    
    __tablename__ = "w2_records"
    
    # Key identifiers
    employee_name = Column(String(200), nullable=False)
    employer = Column(String(300), nullable=False)
    tax_year = Column(Integer, nullable=False)
    
    # Box 1 - Wages, tips, other compensation
    wages = Column(Numeric(18, 2), nullable=False, default=0)
    # Box 2 - Federal income tax withheld
    federal_tax_withheld = Column(Numeric(18, 2), nullable=False, default=0)
    # Box 3 - Social security wages
    social_security_wages = Column(Numeric(18, 2), nullable=False, default=0)
    # Box 4 - Social security tax withheld
    social_security_tax = Column(Numeric(18, 2), nullable=False, default=0)
    # Box 5 - Medicare wages and tips
    medicare_wages = Column(Numeric(18, 2), nullable=False, default=0)
    # Box 6 - Medicare tax withheld
    medicare_tax = Column(Numeric(18, 2), nullable=False, default=0)
    # Box 12 D - 401(k) contributions
    retirement_401k = Column(Numeric(18, 2), nullable=False, default=0)
    # Box 16 - State wages
    state_wages = Column(Numeric(18, 2), nullable=False, default=0)
    # Box 17 - State income tax
    state_tax_withheld = Column(Numeric(18, 2), nullable=False, default=0)
    
    # Calculated net income (wages - taxes)
    net_income = Column(Numeric(18, 2), nullable=False, default=0)
    
    # Source tracking
    source_file = Column(String(500), nullable=True)
    
    __table_args__ = (
        # One W-2 per employee per employer per year
        UniqueConstraint('employee_name', 'employer', 'tax_year', name='uq_w2_record'),
        Index('idx_w2_employee', 'employee_name'),
        Index('idx_w2_year', 'tax_year'),
    )


class RetirementContribution(BaseModel):
    """
    Retirement contributions data from IRS Wage and Income Transcripts.
    Consolidates Form 5498 (IRA) and W-2 (401k) data per person per year.
    """
    
    __tablename__ = "retirement_contributions"
    
    # Key identifiers
    owner = Column(String(100), nullable=False)  # 'Neel' or 'Jaya'
    tax_year = Column(Integer, nullable=False)
    
    # 401(k) from W-2 deferred compensation
    contributions_401k = Column(Numeric(18, 2), nullable=False, default=0)
    roth_401k = Column(Numeric(18, 2), nullable=False, default=0)
    
    # IRA contributions from Form 5498
    ira_contributions = Column(Numeric(18, 2), nullable=False, default=0)
    roth_ira_contributions = Column(Numeric(18, 2), nullable=False, default=0)
    rollover_contributions = Column(Numeric(18, 2), nullable=False, default=0)
    sep_contributions = Column(Numeric(18, 2), nullable=False, default=0)
    simple_contributions = Column(Numeric(18, 2), nullable=False, default=0)
    
    # HSA from W-2
    hsa_contributions = Column(Numeric(18, 2), nullable=False, default=0)
    
    # Fair Market Values (JSON array of account FMVs)
    ira_fmv = Column(JSON, nullable=True)
    
    # W-2 wages for context
    total_wages = Column(Numeric(18, 2), nullable=False, default=0)
    
    # Source tracking
    source_file = Column(String(500), nullable=True)
    ingestion_id = Column(Integer, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('owner', 'tax_year', name='uq_retirement_contribution_owner_year'),
        Index('idx_retirement_contributions_owner', 'owner'),
        Index('idx_retirement_contributions_year', 'tax_year'),
    )

