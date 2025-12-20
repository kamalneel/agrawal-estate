"""
Base model classes and mixins for all database models.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, String
from sqlalchemy.orm import declared_attr

from app.core.database import Base


class TimestampMixin:
    """Mixin that adds created_at and updated_at columns."""
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class BaseModel(Base, TimestampMixin):
    """Base model with common fields for all entities."""
    
    __abstract__ = True
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    @declared_attr
    def __tablename__(cls) -> str:
        """Auto-generate table name from class name."""
        # Convert CamelCase to snake_case
        name = cls.__name__
        return ''.join(['_' + c.lower() if c.isupper() else c for c in name]).lstrip('_')

