"""
Ingestion tracking models.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from app.shared.models.base import BaseModel


class IngestionLog(BaseModel):
    """Track all file ingestion attempts."""
    
    __tablename__ = "ingestion_log"
    
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(64), nullable=True)  # SHA256 of file contents
    
    source = Column(String(50), nullable=False)  # 'robinhood', 'schwab', etc.
    module = Column(String(50), nullable=False)  # 'investments', 'tax', etc.
    
    status = Column(String(20), nullable=False, default="pending")  # pending, processing, success, failed
    
    records_in_file = Column(Integer, default=0)
    records_created = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    records_skipped = Column(Integer, default=0)
    
    error_message = Column(Text, nullable=True)
    warnings = Column(Text, nullable=True)  # JSON array of warnings
    
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    provenance_records = relationship("RecordProvenance", back_populates="ingestion")


class RecordProvenance(BaseModel):
    """Track which source file each record came from."""
    
    __tablename__ = "record_provenance"
    
    ingestion_id = Column(Integer, ForeignKey("ingestion_log.id"), nullable=False)
    
    table_name = Column(String(100), nullable=False)
    record_id = Column(Integer, nullable=False)
    action = Column(String(20), nullable=False)  # 'created', 'updated', 'skipped'
    
    # Relationships
    ingestion = relationship("IngestionLog", back_populates="provenance_records")

