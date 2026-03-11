"""
Airbnb timeshare investment module database models.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Numeric, Text, ForeignKey, DateTime, Index
from sqlalchemy.orm import relationship

from app.shared.models.base import BaseModel


class AirbnbProperty(BaseModel):
    """Properties for Airbnb timeshare investment tracking."""

    __tablename__ = "airbnb_properties"

    name = Column(String(255), nullable=False)
    property_type = Column(String(100), nullable=True)  # e.g., "WorldMark"
    points_per_week = Column(Integer, nullable=True)
    income_per_week_best = Column(Numeric(10, 2), nullable=True)
    income_per_week_worst = Column(Numeric(10, 2), nullable=True)
    housekeeping_per_week = Column(Numeric(10, 2), nullable=True)
    management_fee_pct = Column(Numeric(5, 2), nullable=True)  # e.g., 20.00
    capital_cost_rate_pct = Column(Numeric(5, 2), nullable=True)  # e.g., 8.00
    status = Column(String(20), default='prospective')  # prospective, active, sold
    notes = Column(Text, nullable=True)

    # Relationships
    blocks = relationship("AirbnbPointsBlock", back_populates="property", cascade="all, delete-orphan")
    documents = relationship("AirbnbDocument", back_populates="property", cascade="all, delete-orphan")
    links = relationship("AirbnbLink", back_populates="property", cascade="all, delete-orphan")


class AirbnbPointsBlock(BaseModel):
    """Owned or borrowed points tranches for a property."""

    __tablename__ = "airbnb_points_blocks"

    property_id = Column(Integer, ForeignKey("airbnb_properties.id", ondelete="CASCADE"), nullable=False)
    block_type = Column(String(20), nullable=False)  # 'owned' or 'borrowed'
    points = Column(Integer, nullable=False)
    cost_to_acquire = Column(Numeric(12, 2), nullable=True, default=0)
    annual_cost_rate_pct = Column(Numeric(5, 2), nullable=True)  # 10% owned, 6% borrowed
    housekeeping_per_week = Column(Numeric(10, 2), nullable=True)  # Override property default; borrowed gets tokens (~$100)

    # Relationships
    property = relationship("AirbnbProperty", back_populates="blocks")

    __table_args__ = (
        Index('idx_airbnb_block_property', 'property_id'),
    )


class AirbnbDocument(BaseModel):
    """File uploads per Airbnb property."""

    __tablename__ = "airbnb_documents"

    property_id = Column(Integer, ForeignKey("airbnb_properties.id", ondelete="CASCADE"), nullable=False)
    document_type = Column(String(50), nullable=False)  # contract, legal, insurance, tax, other
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(64), nullable=True)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)

    # Relationships
    property = relationship("AirbnbProperty", back_populates="documents")

    __table_args__ = (
        Index('idx_airbnb_doc_property', 'property_id'),
    )


class AirbnbLink(BaseModel):
    """URLs/links per Airbnb property."""

    __tablename__ = "airbnb_links"

    property_id = Column(Integer, ForeignKey("airbnb_properties.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    url = Column(String(1000), nullable=False)
    link_type = Column(String(50), nullable=True)  # listing, legal, reference, other
    notes = Column(Text, nullable=True)

    # Relationships
    property = relationship("AirbnbProperty", back_populates="links")

    __table_args__ = (
        Index('idx_airbnb_link_property', 'property_id'),
    )
