"""
Estate planning module database models.
"""

from sqlalchemy import Column, Integer, String, Numeric, Date, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.shared.models.base import BaseModel


class EstateDocument(BaseModel):
    """Estate planning documents (wills, trusts, POAs, etc.)."""
    
    __tablename__ = "estate_documents"
    
    document_type = Column(String(50), nullable=False)  # 'will', 'trust', 'poa', 'healthcare_directive', 'other'
    title = Column(String(200), nullable=False)
    
    file_path = Column(String(500), nullable=True)
    
    effective_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    
    attorney_name = Column(String(200), nullable=True)
    attorney_firm = Column(String(200), nullable=True)
    
    location = Column(String(500), nullable=True)  # Where physical copy is stored
    
    notes = Column(Text, nullable=True)
    
    is_current = Column(String(1), default='Y')


class Beneficiary(BaseModel):
    """Beneficiaries for estate planning."""
    
    __tablename__ = "beneficiaries"
    
    name = Column(String(200), nullable=False)
    relation_type = Column(String(100), nullable=True)  # 'spouse', 'child', 'sibling', 'charity', etc.
    
    date_of_birth = Column(Date, nullable=True)
    
    address = Column(String(500), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(200), nullable=True)
    
    ssn_last_four = Column(String(4), nullable=True)  # Last 4 of SSN for identification
    
    is_minor = Column(String(1), default='N')
    guardian_name = Column(String(200), nullable=True)  # If minor
    
    notes = Column(Text, nullable=True)
    
    is_active = Column(String(1), default='Y')
    
    # Relationships
    allocations = relationship("AssetAllocation", back_populates="beneficiary")


class AssetAllocation(BaseModel):
    """How assets are allocated to beneficiaries."""
    
    __tablename__ = "asset_allocations"
    
    beneficiary_id = Column(Integer, ForeignKey("beneficiaries.id"), nullable=False)
    
    asset_type = Column(String(50), nullable=False)  # 'investment_account', 'property', 'insurance', 'general'
    asset_description = Column(String(500), nullable=True)
    
    # Can be percentage or fixed amount
    allocation_type = Column(String(20), nullable=False)  # 'percentage', 'fixed', 'remainder'
    allocation_percentage = Column(Numeric(5, 2), nullable=True)
    allocation_amount = Column(Numeric(18, 2), nullable=True)
    
    is_contingent = Column(String(1), default='N')  # Contingent beneficiary
    
    notes = Column(Text, nullable=True)
    
    # Relationships
    beneficiary = relationship("Beneficiary", back_populates="allocations")


class ImportantContact(BaseModel):
    """Important contacts for estate planning."""
    
    __tablename__ = "important_contacts"
    
    name = Column(String(200), nullable=False)
    role = Column(String(100), nullable=False)  # 'attorney', 'executor', 'trustee', 'accountant', 'financial_advisor', 'insurance_agent'
    
    firm = Column(String(200), nullable=True)
    
    address = Column(String(500), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(200), nullable=True)
    
    specialty = Column(String(200), nullable=True)
    
    notes = Column(Text, nullable=True)
    
    is_active = Column(String(1), default='Y')

