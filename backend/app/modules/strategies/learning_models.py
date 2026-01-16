"""
RLHF (Reinforcement Learning from Human Feedback) Models

These models track the relationship between algorithm recommendations
and user executions, enabling systematic learning and improvement.

Design Philosophy:
- Algorithm stays pure (data-driven)
- Human feedback is observed, not directly encoded
- Patterns are detected, not assumed
- Changes are proposed, not automatic

Three main tables:
1. RecommendationExecutionMatch - Links recommendations to executions
2. PositionOutcome - Tracks what happened after execution
3. WeeklyLearningSummary - Aggregates weekly insights
"""

from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, String, DateTime, Date, Text, 
    Numeric, ForeignKey, JSON, Boolean, Index
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class RecommendationExecutionMatch(Base):
    """
    Links algorithm recommendations to actual user executions.
    
    This is the core table for RLHF - it captures the delta between
    what the algorithm suggested and what the user actually did.
    
    Match Types:
    - consent: User followed recommendation closely
    - modify: User executed but with changes (different strike, expiration, etc.)
    - reject: Recommendation was sent but user didn't act
    - independent: User executed without a recommendation
    - no_action: Recommendation sent, no execution needed (position resolved itself)
    """
    __tablename__ = 'recommendation_execution_matches'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # ===== RECOMMENDATION SIDE =====
    # From StrategyRecommendationRecord
    recommendation_id = Column(String(100), nullable=True)  # Null for independent actions
    recommendation_record_id = Column(Integer, ForeignKey('strategy_recommendations.id'), nullable=True)
    recommendation_date = Column(Date, nullable=False)
    recommendation_time = Column(DateTime, nullable=True)  # When notification was sent
    
    # Recommendation details (denormalized for historical analysis)
    recommendation_type = Column(String(50), nullable=True)  # 'weekly_roll', 'itm_roll', 'pull_back', 'new_sell', etc.
    recommended_action = Column(String(50), nullable=True)  # 'sell', 'roll', 'close', 'buy_to_close'
    recommended_symbol = Column(String(20), nullable=True)
    recommended_strike = Column(Numeric(10, 2), nullable=True)
    recommended_expiration = Column(Date, nullable=True)
    recommended_premium = Column(Numeric(10, 2), nullable=True)
    recommended_option_type = Column(String(10), nullable=True)  # 'call' or 'put'
    recommended_contracts = Column(Integer, nullable=True)
    recommendation_priority = Column(String(20), nullable=True)  # 'urgent', 'high', 'medium', 'low'
    recommendation_context = Column(JSON, nullable=True)  # Full context snapshot
    
    # ===== EXECUTION SIDE =====
    # From InvestmentTransaction (STO, BTC, etc.)
    execution_id = Column(Integer, ForeignKey('investment_transactions.id'), nullable=True)
    execution_date = Column(Date, nullable=True)
    execution_time = Column(DateTime, nullable=True)  # Approximate time of execution
    
    # Execution details (denormalized)
    execution_action = Column(String(50), nullable=True)  # 'STO', 'BTC', 'OEXP'
    execution_symbol = Column(String(20), nullable=True)
    execution_strike = Column(Numeric(10, 2), nullable=True)
    execution_expiration = Column(Date, nullable=True)
    execution_premium = Column(Numeric(10, 2), nullable=True)
    execution_option_type = Column(String(10), nullable=True)
    execution_contracts = Column(Integer, nullable=True)
    execution_account = Column(String(200), nullable=True)
    
    # ===== MATCH ANALYSIS =====
    match_type = Column(String(20), nullable=False)  # 'consent', 'modify', 'reject', 'independent', 'no_action'
    match_confidence = Column(Numeric(5, 2), nullable=True)  # 0-100, how confident are we in this match
    
    # What was different (populated for 'modify' type)
    modification_details = Column(JSON, nullable=True)
    # Example: {
    #   'strike_diff': 5.0,           # User chose strike $5 higher
    #   'expiration_diff_days': 7,    # User chose 7 days later
    #   'premium_diff': 0.15,         # User got $0.15 more premium
    #   'contracts_diff': 0           # Same number of contracts
    # }
    
    # Time analysis
    hours_to_execution = Column(Numeric(10, 2), nullable=True)  # Hours between notification and execution
    market_conditions_at_rec = Column(JSON, nullable=True)  # Stock price, IV, etc. at recommendation
    market_conditions_at_exec = Column(JSON, nullable=True)  # Stock price, IV, etc. at execution
    
    # ===== USER FEEDBACK =====
    # Optional - if user provides reason for divergence
    user_reason_code = Column(String(50), nullable=True)
    # Codes: 'timing', 'premium_low', 'iv_low', 'earnings_concern', 'gut_feeling', 
    #        'better_opportunity', 'risk_too_high', 'already_exposed', 'other'
    user_reason_text = Column(Text, nullable=True)
    feedback_id = Column(Integer, ForeignKey('recommendation_feedback.id'), nullable=True)
    
    # ===== REVIEW STATUS =====
    # Tracks if user has seen/acknowledged this match (for feed-like UX)
    reviewed_at = Column(DateTime, nullable=True)  # When user reviewed/acknowledged
    
    # ===== METADATA =====
    week_number = Column(Integer, nullable=True)  # ISO week number for grouping
    year = Column(Integer, nullable=True)
    algorithm_version = Column(String(20), nullable=True)  # e.g., 'v3.4' - for epoch filtering
    reconciled_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    reconciled_by = Column(String(20), default='system')  # 'system' or 'manual'
    notes = Column(Text, nullable=True)

    # ===== RLHF DATA QUALITY =====
    # For excluding erroneous data from learning without deleting
    excluded_from_learning = Column(Boolean, default=False, nullable=False)
    exclusion_reason = Column(String(50), nullable=True)
    # Reasons: 'algorithm_bug', 'data_source_error', 'parsing_error',
    #          'duplicate', 'test_data', 'manual_review'
    exclusion_notes = Column(Text, nullable=True)
    excluded_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    outcome = relationship("PositionOutcome", back_populates="match", uselist=False)

    __table_args__ = (
        Index('idx_rem_recommendation_id', 'recommendation_id'),
        Index('idx_rem_recommendation_date', 'recommendation_date'),
        Index('idx_rem_execution_date', 'execution_date'),
        Index('idx_rem_match_type', 'match_type'),
        Index('idx_rem_symbol', 'recommended_symbol'),
        Index('idx_rem_week', 'year', 'week_number'),
        Index('idx_rem_excluded', 'excluded_from_learning'),
    )


class PositionOutcome(Base):
    """
    Tracks what happened to a position after recommendation/execution.
    
    This enables counterfactual analysis:
    - What did the user actually get?
    - What would have happened if they followed the algorithm?
    - Was the user's modification beneficial?
    """
    __tablename__ = 'position_outcomes'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey('recommendation_execution_matches.id'), nullable=False)
    
    # ===== POSITION IDENTIFICATION =====
    symbol = Column(String(20), nullable=False)
    strike = Column(Numeric(10, 2), nullable=False)
    expiration_date = Column(Date, nullable=False)
    option_type = Column(String(10), nullable=False)  # 'call' or 'put'
    contracts = Column(Integer, nullable=False, default=1)
    account = Column(String(200), nullable=True)
    
    # ===== ACTUAL OUTCOME =====
    final_status = Column(String(30), nullable=False)
    # Statuses: 'expired_worthless', 'closed_profit', 'closed_loss', 
    #           'assigned', 'rolled', 'open' (still active)
    
    # Premium tracking
    premium_received = Column(Numeric(10, 2), nullable=True)  # Initial premium from STO
    premium_paid_to_close = Column(Numeric(10, 2), nullable=True)  # If closed via BTC
    net_profit = Column(Numeric(10, 2), nullable=True)  # Final P&L
    profit_percent = Column(Numeric(10, 2), nullable=True)  # Profit as % of premium received
    
    # Stock price tracking
    stock_price_at_open = Column(Numeric(10, 2), nullable=True)
    stock_price_at_close = Column(Numeric(10, 2), nullable=True)
    stock_price_at_expiration = Column(Numeric(10, 2), nullable=True)
    
    # Time tracking
    days_held = Column(Integer, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    
    # ===== COUNTERFACTUAL (What would algorithm have yielded?) =====
    # Only populated when user modified recommendation
    counterfactual_outcome = Column(JSON, nullable=True)
    # Example: {
    #   'algorithm_strike': 175.0,
    #   'algorithm_expiration': '2025-01-10',
    #   'algorithm_premium': 1.25,
    #   'hypothetical_status': 'expired_worthless',
    #   'hypothetical_profit': 125.0,
    #   'user_actual_profit': 140.0,
    #   'delta': 15.0,  # Positive = user did better
    #   'user_was_right': True
    # }
    
    # ===== OUTCOME QUALITY ASSESSMENT =====
    outcome_quality = Column(String(20), nullable=True)
    # 'optimal': Best possible outcome given market conditions
    # 'good': Profitable and reasonable
    # 'acceptable': Small profit or break-even
    # 'suboptimal': Could have done better with available info
    # 'bad': Significant loss that was avoidable
    
    # Was the user's deviation from algorithm beneficial?
    deviation_assessment = Column(String(20), nullable=True)
    # 'user_better': User's modification outperformed algorithm
    # 'algorithm_better': Algorithm would have been better
    # 'neutral': Similar outcomes
    # 'n/a': User followed algorithm (consent) or no recommendation (independent)
    
    # ===== LEARNING FLAGS =====
    # Did this outcome teach us something?
    learning_value = Column(String(20), nullable=True)
    # 'high': Clear pattern that could improve algorithm
    # 'medium': Interesting but not conclusive
    # 'low': Noise, luck, or one-off situation
    
    learning_notes = Column(Text, nullable=True)  # What we learned
    
    # ===== METADATA =====
    tracked_at = Column(DateTime, nullable=True)  # When outcome was first recorded
    completed_at = Column(DateTime, nullable=True)  # When position fully resolved
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship back to match
    match = relationship("RecommendationExecutionMatch", back_populates="outcome")
    
    __table_args__ = (
        Index('idx_po_match_id', 'match_id'),
        Index('idx_po_symbol', 'symbol'),
        Index('idx_po_final_status', 'final_status'),
        Index('idx_po_expiration', 'expiration_date'),
        Index('idx_po_deviation', 'deviation_assessment'),
    )


class WeeklyLearningSummary(Base):
    """
    Weekly aggregation of learning insights.
    
    Generated every Saturday, this table captures:
    - How the week went
    - Patterns detected in user behavior
    - Comparison of user vs algorithm performance
    - V4 algorithm improvement candidates
    
    This is the human review interface - you look at this weekly
    to decide what (if anything) to change in the algorithm.
    """
    __tablename__ = 'weekly_learning_summaries'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # ===== WEEK IDENTIFICATION =====
    year = Column(Integer, nullable=False)
    week_number = Column(Integer, nullable=False)  # ISO week number
    week_start = Column(Date, nullable=False)
    week_end = Column(Date, nullable=False)
    
    # ===== MATCH COUNTS =====
    total_recommendations = Column(Integer, nullable=False, default=0)
    total_executions = Column(Integer, nullable=False, default=0)
    
    # By match type
    consent_count = Column(Integer, nullable=False, default=0)  # Followed algorithm
    modify_count = Column(Integer, nullable=False, default=0)   # Modified algorithm suggestion
    reject_count = Column(Integer, nullable=False, default=0)   # Ignored algorithm
    independent_count = Column(Integer, nullable=False, default=0)  # Acted without recommendation
    no_action_count = Column(Integer, nullable=False, default=0)  # Let position resolve
    
    # By recommendation type
    recommendations_by_type = Column(JSON, nullable=True)
    # Example: {'weekly_roll': 8, 'itm_roll': 2, 'new_sell': 5, 'pull_back': 1}
    
    # ===== PERFORMANCE COMPARISON =====
    # Actual P&L from user's actions
    actual_pnl = Column(Numeric(12, 2), nullable=True)
    actual_trades = Column(Integer, nullable=True)
    actual_win_rate = Column(Numeric(5, 2), nullable=True)  # % of trades profitable
    
    # Hypothetical P&L if user followed algorithm 100%
    algorithm_hypothetical_pnl = Column(Numeric(12, 2), nullable=True)
    algorithm_hypothetical_win_rate = Column(Numeric(5, 2), nullable=True)
    
    # Delta (positive = user did better)
    pnl_delta = Column(Numeric(12, 2), nullable=True)
    delta_explanation = Column(Text, nullable=True)
    
    # Who was right more often?
    user_better_count = Column(Integer, nullable=True)  # Times user modification was better
    algorithm_better_count = Column(Integer, nullable=True)  # Times algorithm would have been better
    neutral_count = Column(Integer, nullable=True)  # Similar outcomes
    
    # ===== PATTERNS DETECTED =====
    patterns_observed = Column(JSON, nullable=True)
    # Example: [
    #   {
    #     'pattern_id': 'prefer_longer_dte',
    #     'description': 'User consistently chooses longer DTE than recommended',
    #     'occurrences': 5,
    #     'avg_modification': {'dte_diff_days': 7},
    #     'outcome_when_modified': {'avg_profit_delta': 12.50},
    #     'confidence': 'high'
    #   },
    #   {
    #     'pattern_id': 'reject_low_premium',
    #     'description': 'User rejects recommendations with premium < $0.25',
    #     'occurrences': 3,
    #     'threshold_observed': 0.25,
    #     'outcome_if_followed': {'hypothetical_profit': 45.00},
    #     'confidence': 'medium'
    #   }
    # ]
    
    # ===== V4 CANDIDATES =====
    v4_candidates = Column(JSON, nullable=True)
    # Example: [
    #   {
    #     'candidate_id': 'v4_dte_adjustment',
    #     'change_type': 'parameter',
    #     'description': 'Adjust default DTE from 21-28 to 28-35 days',
    #     'evidence': 'User modified DTE in 5/8 recommendations this week',
    #     'impact_estimate': 'Would reduce modifications by 60%',
    #     'priority': 'high',
    #     'risk': 'May reduce premium capture',
    #     'decision': null  # 'implement', 'defer', 'reject'
    #   },
    #   {
    #     'candidate_id': 'v4_min_premium',
    #     'change_type': 'filter',
    #     'description': 'Add minimum premium filter ($0.25)',
    #     'evidence': 'User rejected 3 low-premium recommendations',
    #     'impact_estimate': 'Would reduce noise in recommendations',
    #     'priority': 'medium',
    #     'risk': 'May miss some opportunities',
    #     'decision': null
    #   }
    # ]
    
    # ===== SYMBOL-SPECIFIC INSIGHTS =====
    symbol_insights = Column(JSON, nullable=True)
    # Example: {
    #   'NVDA': {'user_prefers_conservative': True, 'avg_strike_diff': 5.0},
    #   'AAPL': {'always_follows_algorithm': True}
    # }
    
    # ===== HUMAN REVIEW =====
    review_status = Column(String(20), default='pending')  # 'pending', 'reviewed', 'acted'
    review_notes = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    
    # Decisions made based on this week's analysis
    decisions_made = Column(JSON, nullable=True)
    # Example: [
    #   {'candidate_id': 'v4_dte_adjustment', 'decision': 'implement', 'notes': 'Will try for 2 weeks'},
    #   {'candidate_id': 'v4_min_premium', 'decision': 'defer', 'notes': 'Need more data'}
    # ]
    
    # ===== METADATA =====
    generated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    notification_sent = Column(Boolean, default=False)
    notification_sent_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_wls_year_week', 'year', 'week_number', unique=True),
        Index('idx_wls_week_start', 'week_start'),
        Index('idx_wls_review_status', 'review_status'),
    )


class AlgorithmChange(Base):
    """
    Tracks changes made to the algorithm based on learning.
    
    This provides an audit trail of what was changed, why,
    and whether it improved things.
    """
    __tablename__ = 'algorithm_changes'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # ===== CHANGE IDENTIFICATION =====
    change_id = Column(String(50), nullable=False, unique=True)  # e.g., 'v4_dte_adjustment_20250102'
    change_type = Column(String(30), nullable=False)
    # Types: 'parameter', 'filter', 'logic', 'preference', 'data_source'
    
    # What version this creates
    from_version = Column(String(20), nullable=False)  # e.g., 'v3.0'
    to_version = Column(String(20), nullable=False)    # e.g., 'v3.1' or 'v4.0'
    
    # ===== CHANGE DETAILS =====
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    
    # What exactly changed
    change_details = Column(JSON, nullable=False)
    # Example: {
    #   'parameter': 'default_dte_range',
    #   'old_value': [21, 28],
    #   'new_value': [28, 35],
    #   'affected_strategies': ['weekly_roll', 'new_sell']
    # }
    
    # ===== EVIDENCE =====
    # What learning led to this change
    evidence_summary = Column(Text, nullable=True)
    weekly_summary_ids = Column(JSON, nullable=True)  # IDs of WeeklyLearningSummary that contributed
    pattern_ids = Column(JSON, nullable=True)  # Which patterns this addresses
    
    # ===== DECISION =====
    decision = Column(String(20), nullable=False)  # 'implement', 'defer', 'reject'
    decision_reason = Column(Text, nullable=True)
    decided_at = Column(DateTime, nullable=True)
    
    # ===== IMPLEMENTATION =====
    implemented = Column(Boolean, default=False)
    implemented_at = Column(DateTime, nullable=True)
    rollback_plan = Column(Text, nullable=True)
    
    # ===== VALIDATION =====
    # How do we know if this worked?
    validation_criteria = Column(JSON, nullable=True)
    # Example: {
    #   'success_metric': 'modification_rate_decrease',
    #   'target': 0.40,  # Reduce modifications by 40%
    #   'observation_period_weeks': 4
    # }
    
    validation_status = Column(String(20), nullable=True)  # 'pending', 'success', 'failure', 'mixed'
    validation_results = Column(JSON, nullable=True)
    validated_at = Column(DateTime, nullable=True)
    
    # Did we keep or rollback?
    final_status = Column(String(20), nullable=True)  # 'kept', 'rolled_back', 'modified'
    final_notes = Column(Text, nullable=True)
    
    # ===== METADATA =====
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_ac_change_type', 'change_type'),
        Index('idx_ac_decision', 'decision'),
        Index('idx_ac_implemented', 'implemented'),
        Index('idx_ac_to_version', 'to_version'),
    )

