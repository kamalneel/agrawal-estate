"""Shared database models."""

from app.shared.models.base import BaseModel, TimestampMixin
from app.shared.models.ingestion import IngestionLog, RecordProvenance

__all__ = [
    "BaseModel",
    "TimestampMixin", 
    "IngestionLog",
    "RecordProvenance"
]
