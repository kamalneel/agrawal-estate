"""
V2 Recommendation Models

This module defines the SQLAlchemy models for the V2 recommendation system:
- PositionRecommendation: Core identity (one per position)
- RecommendationSnapshot: Point-in-time captures
- RecommendationExecution: Links to user actions
"""

from datetime import datetime, date
from typing import Optional
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Date, Boolean, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
import hashlib

from app.core.database import Base


def generate_recommendation_id(
    symbol: str,
    account_name: str,
    strike: float = None,
    expiration: date = None,
    option_type: str = "call"
) -> str:
    """
    Generate a unique, deterministic recommendation ID based on position identity.
    
    For SOLD options (strike + expiration provided):
        Format: rec_{symbol}_{account_hash}_{strike}_{expiration}_{type}
    
    For UNCOVERED positions (no strike/expiration):
        Format: rec_{symbol}_{account_hash}_uncovered_{type}
    
    This ensures the same position always gets the same recommendation ID,
    allowing the system to track it across multiple evaluations.
    """
    # Create a short hash of the account name for cleaner IDs
    account_hash = hashlib.md5(account_name.encode()).hexdigest()[:8]
    
    if strike is not None and expiration is not None:
        # Sold option position
        exp_str = expiration.strftime('%Y%m%d') if isinstance(expiration, date) else str(expiration).replace('-', '')
        rec_id = f"rec_{symbol}_{account_hash}_{strike}_{exp_str}_{option_type}"
    else:
        # Uncovered position (no sold option yet)
        rec_id = f"rec_{symbol}_{account_hash}_uncovered_{option_type}"
    
    return rec_id


class PositionRecommendation(Base):
    """
    Represents a recommendation for a specific position.
    
    One PositionRecommendation can have many RecommendationSnapshots,
    each representing a point-in-time evaluation of the position.
    
    The recommendation_id is deterministic based on position identity,
    so the same position always maps to the same recommendation.
    """
    __tablename__ = 'position_recommendations'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Identity - unique, deterministic based on position
    recommendation_id = Column(String(200), nullable=False, unique=True)
    
    # Source position details
    symbol = Column(String(20), nullable=False, index=True)
    account_name = Column(String(200), nullable=False, index=True)
    # For sold options: strike and expiration are set
    # For uncovered positions: these are NULL
    source_strike = Column(Numeric(10, 2), nullable=True)
    source_expiration = Column(Date, nullable=True, index=True)
    option_type = Column(String(10), nullable=False, default='call')
    source_contracts = Column(Integer, nullable=True)
    source_original_premium = Column(Numeric(10, 2), nullable=True)
    
    # Position type: 'sold_option' or 'uncovered'
    position_type = Column(String(20), nullable=True, default='sold_option')
    
    # Lifecycle
    status = Column(String(30), nullable=False, default='active', index=True)
    # active, resolved, expired, position_closed
    
    resolution_type = Column(String(50), nullable=True)
    # user_acted, user_modified, user_ignored, expired, system_resolved
    
    resolution_notes = Column(Text, nullable=True)
    
    # Timing
    first_detected_at = Column(DateTime, nullable=False, index=True)
    last_snapshot_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    
    # Stats
    total_snapshots = Column(Integer, default=0)
    total_notifications_sent = Column(Integer, default=0)
    days_active = Column(Integer, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    snapshots = relationship("RecommendationSnapshot", back_populates="recommendation", cascade="all, delete-orphan")
    executions = relationship("RecommendationExecution", back_populates="recommendation", cascade="all, delete-orphan")


class RecommendationSnapshot(Base):
    """
    Point-in-time capture of a recommendation evaluation.
    
    Each time the algorithm evaluates a position, it creates a new snapshot
    with the current recommended action, target parameters, market conditions, etc.
    
    Snapshots enable:
    - Tracking how recommendations change over time
    - Comparing what was recommended vs what user did
    - Debugging why certain advice was given
    """
    __tablename__ = 'recommendation_snapshots'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    recommendation_id = Column(Integer, ForeignKey('position_recommendations.id'), nullable=False, index=True)
    snapshot_number = Column(Integer, nullable=False)
    
    # When this snapshot was taken
    evaluated_at = Column(DateTime, nullable=False, index=True)
    scan_type = Column(String(30), nullable=True)  # scheduled_6am, scheduled_12pm, manual, etc.
    
    # Algorithm's advice
    recommended_action = Column(String(50), nullable=False, index=True)
    # ROLL, CLOSE, CLOSE_DONT_ROLL, HOLD, MONITOR
    
    priority = Column(String(20), nullable=False)  # urgent, high, medium, low
    decision_state = Column(String(50), nullable=True)  # itm_needs_roll, profitable_early_close, etc.
    reason = Column(Text, nullable=True)
    
    # Target parameters (what to roll/close to)
    target_strike = Column(Numeric(10, 2), nullable=True)
    target_expiration = Column(Date, nullable=True)
    target_premium = Column(Numeric(10, 2), nullable=True)
    estimated_cost_to_close = Column(Numeric(10, 2), nullable=True)
    net_cost = Column(Numeric(10, 2), nullable=True)
    
    # Source position state at evaluation time
    current_premium = Column(Numeric(10, 2), nullable=True)
    profit_pct = Column(Numeric(5, 2), nullable=True)
    days_to_expiration = Column(Integer, nullable=True)
    is_itm = Column(Boolean, nullable=True)
    itm_pct = Column(Numeric(5, 2), nullable=True)
    
    # Market conditions
    stock_price = Column(Numeric(10, 2), nullable=True)
    stock_bid = Column(Numeric(10, 2), nullable=True)
    stock_ask = Column(Numeric(10, 2), nullable=True)
    implied_volatility = Column(Numeric(5, 2), nullable=True)
    
    # Technical analysis
    rsi = Column(Numeric(5, 2), nullable=True)
    trend = Column(String(20), nullable=True)
    bollinger_position = Column(String(30), nullable=True)
    weekly_volatility = Column(Numeric(5, 2), nullable=True)
    support_level = Column(Numeric(10, 2), nullable=True)
    resistance_level = Column(Numeric(10, 2), nullable=True)
    
    # Change tracking (vs previous snapshot)
    action_changed = Column(Boolean, default=False)
    target_changed = Column(Boolean, default=False)
    priority_changed = Column(Boolean, default=False)
    previous_action = Column(String(50), nullable=True)
    previous_target_strike = Column(Numeric(10, 2), nullable=True)
    previous_target_expiration = Column(Date, nullable=True)
    previous_priority = Column(String(20), nullable=True)
    
    # Full context as JSON for debugging
    full_context = Column(JSONB, nullable=True)
    
    # Notification tracking
    notification_sent = Column(Boolean, default=False, index=True)
    notification_sent_at = Column(DateTime, nullable=True)
    notification_channel = Column(String(30), nullable=True)  # telegram, web, both
    telegram_message_id = Column(Integer, nullable=True)
    notification_decision = Column(String(50), nullable=True)  # sent, skipped_duplicate, etc.
    
    # V2 notification mode tracking
    notification_mode = Column(String(20), nullable=True)  # verbose, smart
    verbose_notification_sent = Column(Boolean, default=False)
    verbose_notification_at = Column(DateTime, nullable=True)
    smart_notification_sent = Column(Boolean, default=False)
    smart_notification_at = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    recommendation = relationship("PositionRecommendation", back_populates="snapshots")
    executions = relationship("RecommendationExecution", back_populates="snapshot")
    
    # Ensure unique snapshot numbers per recommendation
    __table_args__ = (
        UniqueConstraint('recommendation_id', 'snapshot_number', name='uq_rec_snapshot'),
    )


class RecommendationExecution(Base):
    """
    Records what the user actually did in response to a recommendation.
    
    Links a recommendation (and optionally a specific snapshot) to the
    actual trade execution, enabling RLHF learning:
    - Did user follow advice?
    - Did they modify parameters?
    - What was the outcome?
    """
    __tablename__ = 'recommendation_executions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    recommendation_id = Column(Integer, ForeignKey('position_recommendations.id'), nullable=False, index=True)
    snapshot_id = Column(Integer, ForeignKey('recommendation_snapshots.id'), nullable=True, index=True)
    
    # What user actually did
    execution_action = Column(String(50), nullable=True)  # roll, close, ignore, etc.
    execution_strike = Column(Numeric(10, 2), nullable=True)
    execution_expiration = Column(Date, nullable=True)
    execution_premium = Column(Numeric(10, 2), nullable=True)
    execution_contracts = Column(Integer, nullable=True)
    execution_net_cost = Column(Numeric(10, 2), nullable=True)
    
    # How well did user follow advice?
    match_type = Column(String(30), nullable=False, index=True)
    # exact_match, modified_strike, modified_expiration, different_action, ignored
    
    match_confidence = Column(Numeric(5, 2), nullable=True)  # 0-100%
    modification_details = Column(JSONB, nullable=True)
    
    # Timing analysis
    executed_at = Column(DateTime, nullable=True, index=True)
    hours_after_snapshot = Column(Numeric(10, 2), nullable=True)
    hours_after_first_notification = Column(Numeric(10, 2), nullable=True)
    notification_count_before_action = Column(Integer, nullable=True)
    
    # User feedback
    user_reason_code = Column(String(50), nullable=True)
    user_reason_text = Column(Text, nullable=True)
    
    # Outcome tracking
    outcome_status = Column(String(30), nullable=True)  # profit, loss, pending
    outcome_pnl = Column(Numeric(10, 2), nullable=True)
    outcome_tracked_at = Column(DateTime, nullable=True)
    
    # Counterfactual: what would have happened if user followed advice exactly?
    counterfactual_outcome = Column(JSONB, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    recommendation = relationship("PositionRecommendation", back_populates="executions")
    snapshot = relationship("RecommendationSnapshot", back_populates="executions")
