"""
Models for strategies module including sold options tracking.
"""

from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import Column, Integer, String, DateTime, Date, Text, Numeric, ForeignKey, JSON, Boolean, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


class SoldOptionsSnapshot(Base):
    """Represents a single screenshot upload of sold options."""
    __tablename__ = 'sold_options_snapshots'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False)  # 'robinhood', 'schwab', etc.
    account_name = Column(String(200), nullable=True)  # Which account this applies to
    snapshot_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    image_path = Column(String(500), nullable=True)
    raw_extracted_text = Column(Text, nullable=True)
    parsing_status = Column(String(20), nullable=False, default='pending')
    parsing_error = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to sold options
    options = relationship("SoldOption", back_populates="snapshot", cascade="all, delete-orphan")


class SoldOption(Base):
    """Individual sold option parsed from a screenshot."""
    __tablename__ = 'sold_options'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(Integer, ForeignKey('sold_options_snapshots.id', ondelete='CASCADE'), nullable=False)
    symbol = Column(String(20), nullable=False)
    strike_price = Column(Numeric(10, 2), nullable=False)
    option_type = Column(String(10), nullable=False)  # 'call' or 'put'
    expiration_date = Column(Date, nullable=True)
    contracts_sold = Column(Integer, nullable=False)
    premium_per_contract = Column(Numeric(10, 2), nullable=True)  # Current premium (from latest snapshot)
    original_premium = Column(Numeric(10, 2), nullable=True)  # Premium when sold (for profit tracking)
    gain_loss_percent = Column(Numeric(10, 2), nullable=True)
    status = Column(String(20), nullable=True)  # 'open', 'closed', 'expired'
    raw_text = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship back to snapshot
    snapshot = relationship("SoldOptionsSnapshot", back_populates="options")


class OptionRollAlert(Base):
    """Tracks alerts for early option rolling opportunities."""
    __tablename__ = 'option_roll_alerts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sold_option_id = Column(Integer, ForeignKey('sold_options.id', ondelete='CASCADE'), nullable=True)
    
    # Option details (denormalized for historical tracking)
    symbol = Column(String(20), nullable=False)
    strike_price = Column(Numeric(10, 2), nullable=False)
    option_type = Column(String(10), nullable=False)  # 'call' or 'put'
    expiration_date = Column(Date, nullable=True)
    contracts = Column(Integer, nullable=False, default=1)
    
    # Premium tracking
    original_premium = Column(Numeric(10, 2), nullable=False)  # What we sold it for
    current_premium = Column(Numeric(10, 2), nullable=False)   # Current market price
    profit_percent = Column(Numeric(10, 2), nullable=False)    # Profit percentage
    
    # Alert status
    alert_type = Column(String(50), nullable=False)  # 'early_roll_opportunity'
    alert_triggered_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    alert_acknowledged = Column(String(1), default='N')  # 'Y' or 'N'
    acknowledged_at = Column(DateTime, nullable=True)
    action_taken = Column(String(50), nullable=True)  # 'rolled', 'closed', 'ignored'
    
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class OptionPremiumSetting(Base):
    """Stores weekly premium per contract settings for each symbol."""
    __tablename__ = 'option_premium_settings'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, unique=True)
    premium_per_contract = Column(Numeric(10, 2), nullable=False)  # Weekly premium per contract
    is_auto_updated = Column(Boolean, default=True)  # Whether this is auto-updated from 4-week average
    last_auto_update = Column(DateTime, nullable=True)  # When it was last auto-updated
    manual_override = Column(Boolean, default=False)  # If True, don't auto-update
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class StrategyRecommendationRecord(Base):
    """Tracks strategy recommendations shown to user for learning and analytics."""
    __tablename__ = 'strategy_recommendations'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    recommendation_id = Column(String(100), nullable=False)  # Unique ID from StrategyRecommendation
    recommendation_type = Column(String(50), nullable=False)  # e.g., "sell_unsold_contracts"
    category = Column(String(50), nullable=False)  # e.g., "income_generation"
    priority = Column(String(20), nullable=False)  # "low", "medium", "high", "urgent"
    
    # Content snapshot (full recommendation details)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)  # Full description
    rationale = Column(Text, nullable=True)  # Reasoning behind recommendation
    action = Column(String(500), nullable=True)
    action_type = Column(String(50), nullable=True)  # "sell", "roll", "adjust", etc.
    
    # Financial details
    potential_income = Column(Numeric(10, 2), nullable=True)
    potential_risk = Column(String(50), nullable=True)
    
    # Symbol/Account info (for easier querying)
    symbol = Column(String(20), nullable=True)  # Stock symbol if applicable
    account_name = Column(String(200), nullable=True)  # Account if applicable
    
    # Status tracking
    status = Column(String(20), default='new')  # new, acknowledged, acted, dismissed, expired
    acknowledged_at = Column(DateTime, nullable=True)
    acted_at = Column(DateTime, nullable=True)
    action_taken = Column(String(200), nullable=True)  # What user actually did
    dismissed_at = Column(DateTime, nullable=True)
    
    # Context snapshot (JSON) - stores full context when recommendation was made
    context_snapshot = Column(JSON, nullable=True)
    
    # Notification tracking
    notification_sent = Column(Boolean, default=False)
    notification_sent_at = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_rec_created_at', 'created_at'),
        Index('idx_rec_status', 'status'),
        Index('idx_rec_type', 'recommendation_type'),
        Index('idx_rec_symbol', 'symbol'),
        Index('idx_rec_recommendation_id', 'recommendation_id', unique=True),  # Required for upsert
    )


class StrategyConfig(Base):
    """Configuration for individual recommendation strategies."""
    __tablename__ = 'strategy_configs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_type = Column(String(50), nullable=False, unique=True)  # e.g., "sell_unsold_contracts"
    name = Column(String(100), nullable=False)  # Display name
    description = Column(Text, nullable=True)  # What this strategy does
    category = Column(String(50), nullable=False)  # "income_generation", "optimization", "risk_management"
    
    # Enable/disable
    enabled = Column(Boolean, default=True, nullable=False)
    notification_enabled = Column(Boolean, default=True, nullable=False)
    
    # Notification settings
    notification_priority_threshold = Column(String(20), default='high')  # Minimum priority to notify
    
    # Strategy-specific parameters (JSON)
    parameters = Column(JSON, nullable=True)  # e.g., {"profit_threshold": 0.80, "min_income": 50}
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class RecommendationNotification(Base):
    """Tracks when recommendations were sent via notifications."""
    __tablename__ = 'recommendation_notifications'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    recommendation_id = Column(String(100), nullable=False)  # ID from StrategyRecommendation
    notification_type = Column(String(50), nullable=False)  # 'new', 'update', 'expired', 'priority_escalated'
    priority = Column(String(20), nullable=False)  # Priority at time of notification
    previous_priority = Column(String(20), nullable=True)  # For priority escalation tracking
    
    # Notification details
    channels_sent = Column(JSON, nullable=True)  # {'telegram': True, 'email': False}
    sent_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Cooldown management
    next_notification_allowed_at = Column(DateTime, nullable=True)  # When next notification for this rec is allowed
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class WeeklyRecommendationTracking(Base):
    """Tracks weekly recommendation limits and prevents duplicates."""
    __tablename__ = 'weekly_recommendation_tracking'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_type = Column(String(50), nullable=False)  # e.g., 'bull_put_spread'
    week_start_date = Column(Date, nullable=False)  # Monday of the week
    recommendation_id = Column(String(100), nullable=False)  # ID from StrategyRecommendation
    potential_profit = Column(Numeric(10, 2), nullable=False)  # Profit potential for ranking
    sent_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_weekly_rec_week_strategy', 'week_start_date', 'strategy_type'),
    )
