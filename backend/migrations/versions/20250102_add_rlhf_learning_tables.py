"""Add RLHF learning tables for recommendation vs execution tracking

Revision ID: 20250102_rlhf_learning
Revises: 20251222_feedback_and_telegram
Create Date: 2025-01-02

This migration creates the tables needed for the RLHF (Reinforcement Learning
from Human Feedback) system that tracks:
1. How recommendations match to actual executions
2. Position outcomes for counterfactual analysis
3. Weekly learning summaries for pattern detection
4. Algorithm changes for audit trail
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250102_rlhf_learning'
down_revision = '20251222_feedback_and_telegram'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # TABLE 1: recommendation_execution_matches
    # Links recommendations to actual executions
    # =========================================================================
    op.create_table(
        'recommendation_execution_matches',
        
        # Primary key
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        
        # Recommendation side
        sa.Column('recommendation_id', sa.String(100), nullable=True),
        sa.Column('recommendation_record_id', sa.Integer(), nullable=True),
        sa.Column('recommendation_date', sa.Date(), nullable=False),
        sa.Column('recommendation_time', sa.DateTime(), nullable=True),
        sa.Column('recommendation_type', sa.String(50), nullable=True),
        sa.Column('recommended_action', sa.String(50), nullable=True),
        sa.Column('recommended_symbol', sa.String(20), nullable=True),
        sa.Column('recommended_strike', sa.Numeric(10, 2), nullable=True),
        sa.Column('recommended_expiration', sa.Date(), nullable=True),
        sa.Column('recommended_premium', sa.Numeric(10, 2), nullable=True),
        sa.Column('recommended_option_type', sa.String(10), nullable=True),
        sa.Column('recommended_contracts', sa.Integer(), nullable=True),
        sa.Column('recommendation_priority', sa.String(20), nullable=True),
        sa.Column('recommendation_context', sa.JSON(), nullable=True),
        
        # Execution side
        sa.Column('execution_id', sa.Integer(), nullable=True),
        sa.Column('execution_date', sa.Date(), nullable=True),
        sa.Column('execution_time', sa.DateTime(), nullable=True),
        sa.Column('execution_action', sa.String(50), nullable=True),
        sa.Column('execution_symbol', sa.String(20), nullable=True),
        sa.Column('execution_strike', sa.Numeric(10, 2), nullable=True),
        sa.Column('execution_expiration', sa.Date(), nullable=True),
        sa.Column('execution_premium', sa.Numeric(10, 2), nullable=True),
        sa.Column('execution_option_type', sa.String(10), nullable=True),
        sa.Column('execution_contracts', sa.Integer(), nullable=True),
        sa.Column('execution_account', sa.String(200), nullable=True),
        
        # Match analysis
        sa.Column('match_type', sa.String(20), nullable=False),
        sa.Column('match_confidence', sa.Numeric(5, 2), nullable=True),
        sa.Column('modification_details', sa.JSON(), nullable=True),
        sa.Column('hours_to_execution', sa.Numeric(10, 2), nullable=True),
        sa.Column('market_conditions_at_rec', sa.JSON(), nullable=True),
        sa.Column('market_conditions_at_exec', sa.JSON(), nullable=True),
        
        # User feedback
        sa.Column('user_reason_code', sa.String(50), nullable=True),
        sa.Column('user_reason_text', sa.Text(), nullable=True),
        sa.Column('feedback_id', sa.Integer(), nullable=True),
        
        # Metadata
        sa.Column('week_number', sa.Integer(), nullable=True),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('reconciled_at', sa.DateTime(), nullable=False),
        sa.Column('reconciled_by', sa.String(20), default='system'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        
        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['recommendation_record_id'], ['strategy_recommendations.id']),
        sa.ForeignKeyConstraint(['execution_id'], ['investment_transactions.id']),
        sa.ForeignKeyConstraint(['feedback_id'], ['recommendation_feedback.id']),
    )
    
    # Indexes for recommendation_execution_matches
    op.create_index('idx_rem_recommendation_id', 'recommendation_execution_matches', ['recommendation_id'])
    op.create_index('idx_rem_recommendation_date', 'recommendation_execution_matches', ['recommendation_date'])
    op.create_index('idx_rem_execution_date', 'recommendation_execution_matches', ['execution_date'])
    op.create_index('idx_rem_match_type', 'recommendation_execution_matches', ['match_type'])
    op.create_index('idx_rem_symbol', 'recommendation_execution_matches', ['recommended_symbol'])
    op.create_index('idx_rem_week', 'recommendation_execution_matches', ['year', 'week_number'])
    
    # =========================================================================
    # TABLE 2: position_outcomes
    # Tracks what happened to positions after execution
    # =========================================================================
    op.create_table(
        'position_outcomes',
        
        # Primary key and foreign key
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('match_id', sa.Integer(), nullable=False),
        
        # Position identification
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('strike', sa.Numeric(10, 2), nullable=False),
        sa.Column('expiration_date', sa.Date(), nullable=False),
        sa.Column('option_type', sa.String(10), nullable=False),
        sa.Column('contracts', sa.Integer(), nullable=False, default=1),
        sa.Column('account', sa.String(200), nullable=True),
        
        # Actual outcome
        sa.Column('final_status', sa.String(30), nullable=False),
        sa.Column('premium_received', sa.Numeric(10, 2), nullable=True),
        sa.Column('premium_paid_to_close', sa.Numeric(10, 2), nullable=True),
        sa.Column('net_profit', sa.Numeric(10, 2), nullable=True),
        sa.Column('profit_percent', sa.Numeric(10, 2), nullable=True),
        
        # Stock price tracking
        sa.Column('stock_price_at_open', sa.Numeric(10, 2), nullable=True),
        sa.Column('stock_price_at_close', sa.Numeric(10, 2), nullable=True),
        sa.Column('stock_price_at_expiration', sa.Numeric(10, 2), nullable=True),
        
        # Time tracking
        sa.Column('days_held', sa.Integer(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        
        # Counterfactual analysis
        sa.Column('counterfactual_outcome', sa.JSON(), nullable=True),
        
        # Outcome assessment
        sa.Column('outcome_quality', sa.String(20), nullable=True),
        sa.Column('deviation_assessment', sa.String(20), nullable=True),
        
        # Learning flags
        sa.Column('learning_value', sa.String(20), nullable=True),
        sa.Column('learning_notes', sa.Text(), nullable=True),
        
        # Metadata
        sa.Column('tracked_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        
        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['match_id'], ['recommendation_execution_matches.id']),
    )
    
    # Indexes for position_outcomes
    op.create_index('idx_po_match_id', 'position_outcomes', ['match_id'])
    op.create_index('idx_po_symbol', 'position_outcomes', ['symbol'])
    op.create_index('idx_po_final_status', 'position_outcomes', ['final_status'])
    op.create_index('idx_po_expiration', 'position_outcomes', ['expiration_date'])
    op.create_index('idx_po_deviation', 'position_outcomes', ['deviation_assessment'])
    
    # =========================================================================
    # TABLE 3: weekly_learning_summaries
    # Weekly aggregation of learning insights
    # =========================================================================
    op.create_table(
        'weekly_learning_summaries',
        
        # Primary key
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        
        # Week identification
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('week_number', sa.Integer(), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('week_end', sa.Date(), nullable=False),
        
        # Match counts
        sa.Column('total_recommendations', sa.Integer(), nullable=False, default=0),
        sa.Column('total_executions', sa.Integer(), nullable=False, default=0),
        sa.Column('consent_count', sa.Integer(), nullable=False, default=0),
        sa.Column('modify_count', sa.Integer(), nullable=False, default=0),
        sa.Column('reject_count', sa.Integer(), nullable=False, default=0),
        sa.Column('independent_count', sa.Integer(), nullable=False, default=0),
        sa.Column('no_action_count', sa.Integer(), nullable=False, default=0),
        sa.Column('recommendations_by_type', sa.JSON(), nullable=True),
        
        # Performance comparison
        sa.Column('actual_pnl', sa.Numeric(12, 2), nullable=True),
        sa.Column('actual_trades', sa.Integer(), nullable=True),
        sa.Column('actual_win_rate', sa.Numeric(5, 2), nullable=True),
        sa.Column('algorithm_hypothetical_pnl', sa.Numeric(12, 2), nullable=True),
        sa.Column('algorithm_hypothetical_win_rate', sa.Numeric(5, 2), nullable=True),
        sa.Column('pnl_delta', sa.Numeric(12, 2), nullable=True),
        sa.Column('delta_explanation', sa.Text(), nullable=True),
        sa.Column('user_better_count', sa.Integer(), nullable=True),
        sa.Column('algorithm_better_count', sa.Integer(), nullable=True),
        sa.Column('neutral_count', sa.Integer(), nullable=True),
        
        # Patterns and insights
        sa.Column('patterns_observed', sa.JSON(), nullable=True),
        sa.Column('v4_candidates', sa.JSON(), nullable=True),
        sa.Column('symbol_insights', sa.JSON(), nullable=True),
        
        # Human review
        sa.Column('review_status', sa.String(20), default='pending'),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('decisions_made', sa.JSON(), nullable=True),
        
        # Metadata
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('notification_sent', sa.Boolean(), default=False),
        sa.Column('notification_sent_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        
        # Constraints
        sa.PrimaryKeyConstraint('id'),
    )
    
    # Indexes for weekly_learning_summaries
    op.create_index('idx_wls_year_week', 'weekly_learning_summaries', ['year', 'week_number'], unique=True)
    op.create_index('idx_wls_week_start', 'weekly_learning_summaries', ['week_start'])
    op.create_index('idx_wls_review_status', 'weekly_learning_summaries', ['review_status'])
    
    # =========================================================================
    # TABLE 4: algorithm_changes
    # Audit trail of algorithm modifications
    # =========================================================================
    op.create_table(
        'algorithm_changes',
        
        # Primary key
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        
        # Change identification
        sa.Column('change_id', sa.String(50), nullable=False, unique=True),
        sa.Column('change_type', sa.String(30), nullable=False),
        sa.Column('from_version', sa.String(20), nullable=False),
        sa.Column('to_version', sa.String(20), nullable=False),
        
        # Change details
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('change_details', sa.JSON(), nullable=False),
        
        # Evidence
        sa.Column('evidence_summary', sa.Text(), nullable=True),
        sa.Column('weekly_summary_ids', sa.JSON(), nullable=True),
        sa.Column('pattern_ids', sa.JSON(), nullable=True),
        
        # Decision
        sa.Column('decision', sa.String(20), nullable=False),
        sa.Column('decision_reason', sa.Text(), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        
        # Implementation
        sa.Column('implemented', sa.Boolean(), default=False),
        sa.Column('implemented_at', sa.DateTime(), nullable=True),
        sa.Column('rollback_plan', sa.Text(), nullable=True),
        
        # Validation
        sa.Column('validation_criteria', sa.JSON(), nullable=True),
        sa.Column('validation_status', sa.String(20), nullable=True),
        sa.Column('validation_results', sa.JSON(), nullable=True),
        sa.Column('validated_at', sa.DateTime(), nullable=True),
        
        # Final status
        sa.Column('final_status', sa.String(20), nullable=True),
        sa.Column('final_notes', sa.Text(), nullable=True),
        
        # Metadata
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        
        # Constraints
        sa.PrimaryKeyConstraint('id'),
    )
    
    # Indexes for algorithm_changes
    op.create_index('idx_ac_change_type', 'algorithm_changes', ['change_type'])
    op.create_index('idx_ac_decision', 'algorithm_changes', ['decision'])
    op.create_index('idx_ac_implemented', 'algorithm_changes', ['implemented'])
    op.create_index('idx_ac_to_version', 'algorithm_changes', ['to_version'])


def downgrade() -> None:
    # Drop algorithm_changes
    op.drop_index('idx_ac_to_version', table_name='algorithm_changes')
    op.drop_index('idx_ac_implemented', table_name='algorithm_changes')
    op.drop_index('idx_ac_decision', table_name='algorithm_changes')
    op.drop_index('idx_ac_change_type', table_name='algorithm_changes')
    op.drop_table('algorithm_changes')
    
    # Drop weekly_learning_summaries
    op.drop_index('idx_wls_review_status', table_name='weekly_learning_summaries')
    op.drop_index('idx_wls_week_start', table_name='weekly_learning_summaries')
    op.drop_index('idx_wls_year_week', table_name='weekly_learning_summaries')
    op.drop_table('weekly_learning_summaries')
    
    # Drop position_outcomes
    op.drop_index('idx_po_deviation', table_name='position_outcomes')
    op.drop_index('idx_po_expiration', table_name='position_outcomes')
    op.drop_index('idx_po_final_status', table_name='position_outcomes')
    op.drop_index('idx_po_symbol', table_name='position_outcomes')
    op.drop_index('idx_po_match_id', table_name='position_outcomes')
    op.drop_table('position_outcomes')
    
    # Drop recommendation_execution_matches
    op.drop_index('idx_rem_week', table_name='recommendation_execution_matches')
    op.drop_index('idx_rem_symbol', table_name='recommendation_execution_matches')
    op.drop_index('idx_rem_match_type', table_name='recommendation_execution_matches')
    op.drop_index('idx_rem_execution_date', table_name='recommendation_execution_matches')
    op.drop_index('idx_rem_recommendation_date', table_name='recommendation_execution_matches')
    op.drop_index('idx_rem_recommendation_id', table_name='recommendation_execution_matches')
    op.drop_table('recommendation_execution_matches')

