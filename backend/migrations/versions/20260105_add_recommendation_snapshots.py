"""Add recommendation snapshots architecture

This migration adds the new hierarchical recommendation model:
- position_recommendations: Core identity (one per position)
- recommendation_snapshots: Point-in-time captures
- recommendation_executions: Links to user actions

Revision ID: 20260105_rec_snapshots
Revises: 20260102_plaid
Create Date: 2026-01-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = '20260105_rec_snapshots'
down_revision = '20260102_plaid'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ================================================================
    # Table 1: position_recommendations (Identity)
    # ================================================================
    op.create_table(
        'position_recommendations',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        
        # Identity
        sa.Column('recommendation_id', sa.String(200), nullable=False, unique=True),
        
        # Source position
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('account_name', sa.String(200), nullable=False),
        sa.Column('source_strike', sa.Numeric(10, 2), nullable=False),
        sa.Column('source_expiration', sa.Date(), nullable=False),
        sa.Column('option_type', sa.String(10), nullable=False),
        sa.Column('source_contracts', sa.Integer(), nullable=True),
        sa.Column('source_original_premium', sa.Numeric(10, 2), nullable=True),
        
        # Lifecycle
        sa.Column('status', sa.String(30), nullable=False, server_default='active'),
        sa.Column('resolution_type', sa.String(50), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        
        # Timing
        sa.Column('first_detected_at', sa.DateTime(), nullable=False),
        sa.Column('last_snapshot_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        
        # Stats
        sa.Column('total_snapshots', sa.Integer(), server_default='0'),
        sa.Column('total_notifications_sent', sa.Integer(), server_default='0'),
        sa.Column('days_active', sa.Integer(), nullable=True),
        
        # Metadata
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Indexes for position_recommendations
    op.create_index('idx_posrec_status', 'position_recommendations', ['status'])
    op.create_index('idx_posrec_symbol', 'position_recommendations', ['symbol'])
    op.create_index('idx_posrec_account', 'position_recommendations', ['account_name'])
    op.create_index('idx_posrec_source_exp', 'position_recommendations', ['source_expiration'])
    op.create_index('idx_posrec_first_detected', 'position_recommendations', ['first_detected_at'])
    op.create_index('idx_posrec_recommendation_id', 'position_recommendations', ['recommendation_id'])
    
    # ================================================================
    # Table 2: recommendation_snapshots (Point-in-time)
    # ================================================================
    op.create_table(
        'recommendation_snapshots',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('recommendation_id', sa.Integer(), sa.ForeignKey('position_recommendations.id'), nullable=False),
        sa.Column('snapshot_number', sa.Integer(), nullable=False),
        
        # When
        sa.Column('evaluated_at', sa.DateTime(), nullable=False),
        sa.Column('scan_type', sa.String(30), nullable=True),
        
        # Algorithm's advice
        sa.Column('recommended_action', sa.String(50), nullable=False),
        sa.Column('priority', sa.String(20), nullable=False),
        sa.Column('decision_state', sa.String(50), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        
        # Target parameters
        sa.Column('target_strike', sa.Numeric(10, 2), nullable=True),
        sa.Column('target_expiration', sa.Date(), nullable=True),
        sa.Column('target_premium', sa.Numeric(10, 2), nullable=True),
        sa.Column('estimated_cost_to_close', sa.Numeric(10, 2), nullable=True),
        sa.Column('net_cost', sa.Numeric(10, 2), nullable=True),
        
        # Source position state
        sa.Column('current_premium', sa.Numeric(10, 2), nullable=True),
        sa.Column('profit_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('days_to_expiration', sa.Integer(), nullable=True),
        sa.Column('is_itm', sa.Boolean(), nullable=True),
        sa.Column('itm_pct', sa.Numeric(5, 2), nullable=True),
        
        # Market conditions
        sa.Column('stock_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('stock_bid', sa.Numeric(10, 2), nullable=True),
        sa.Column('stock_ask', sa.Numeric(10, 2), nullable=True),
        sa.Column('implied_volatility', sa.Numeric(5, 2), nullable=True),
        
        # Technical analysis
        sa.Column('rsi', sa.Numeric(5, 2), nullable=True),
        sa.Column('trend', sa.String(20), nullable=True),
        sa.Column('bollinger_position', sa.String(30), nullable=True),
        sa.Column('weekly_volatility', sa.Numeric(5, 2), nullable=True),
        sa.Column('support_level', sa.Numeric(10, 2), nullable=True),
        sa.Column('resistance_level', sa.Numeric(10, 2), nullable=True),
        
        # Change tracking
        sa.Column('action_changed', sa.Boolean(), server_default='false'),
        sa.Column('target_changed', sa.Boolean(), server_default='false'),
        sa.Column('priority_changed', sa.Boolean(), server_default='false'),
        sa.Column('previous_action', sa.String(50), nullable=True),
        sa.Column('previous_target_strike', sa.Numeric(10, 2), nullable=True),
        sa.Column('previous_target_expiration', sa.Date(), nullable=True),
        sa.Column('previous_priority', sa.String(20), nullable=True),
        
        # Full context
        sa.Column('full_context', JSONB(), nullable=True),
        
        # Notification tracking
        sa.Column('notification_sent', sa.Boolean(), server_default='false'),
        sa.Column('notification_sent_at', sa.DateTime(), nullable=True),
        sa.Column('notification_channel', sa.String(30), nullable=True),
        sa.Column('telegram_message_id', sa.Integer(), nullable=True),
        sa.Column('notification_decision', sa.String(50), nullable=True),
        
        # Metadata
        sa.Column('created_at', sa.DateTime(), nullable=False),
        
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('recommendation_id', 'snapshot_number', name='uq_rec_snapshot')
    )
    
    # Indexes for recommendation_snapshots
    op.create_index('idx_snap_recommendation_id', 'recommendation_snapshots', ['recommendation_id'])
    op.create_index('idx_snap_evaluated_at', 'recommendation_snapshots', ['evaluated_at'])
    op.create_index('idx_snap_action', 'recommendation_snapshots', ['recommended_action'])
    op.create_index('idx_snap_notification_sent', 'recommendation_snapshots', ['notification_sent'])
    
    # ================================================================
    # Table 3: recommendation_executions (User actions)
    # ================================================================
    op.create_table(
        'recommendation_executions',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('recommendation_id', sa.Integer(), sa.ForeignKey('position_recommendations.id'), nullable=False),
        sa.Column('snapshot_id', sa.Integer(), sa.ForeignKey('recommendation_snapshots.id'), nullable=True),
        
        # What user did
        sa.Column('execution_action', sa.String(50), nullable=True),
        sa.Column('execution_strike', sa.Numeric(10, 2), nullable=True),
        sa.Column('execution_expiration', sa.Date(), nullable=True),
        sa.Column('execution_premium', sa.Numeric(10, 2), nullable=True),
        sa.Column('execution_contracts', sa.Integer(), nullable=True),
        sa.Column('execution_net_cost', sa.Numeric(10, 2), nullable=True),
        
        # Match analysis
        sa.Column('match_type', sa.String(30), nullable=False),
        sa.Column('match_confidence', sa.Numeric(5, 2), nullable=True),
        sa.Column('modification_details', JSONB(), nullable=True),
        
        # Timing
        sa.Column('executed_at', sa.DateTime(), nullable=True),
        sa.Column('hours_after_snapshot', sa.Numeric(10, 2), nullable=True),
        sa.Column('hours_after_first_notification', sa.Numeric(10, 2), nullable=True),
        sa.Column('notification_count_before_action', sa.Integer(), nullable=True),
        
        # User feedback
        sa.Column('user_reason_code', sa.String(50), nullable=True),
        sa.Column('user_reason_text', sa.Text(), nullable=True),
        
        # Outcome
        sa.Column('outcome_status', sa.String(30), nullable=True),
        sa.Column('outcome_pnl', sa.Numeric(10, 2), nullable=True),
        sa.Column('outcome_tracked_at', sa.DateTime(), nullable=True),
        
        # Counterfactual
        sa.Column('counterfactual_outcome', JSONB(), nullable=True),
        
        # Metadata
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Indexes for recommendation_executions
    op.create_index('idx_recexec_recommendation_id', 'recommendation_executions', ['recommendation_id'])
    op.create_index('idx_recexec_snapshot_id', 'recommendation_executions', ['snapshot_id'])
    op.create_index('idx_recexec_match_type', 'recommendation_executions', ['match_type'])
    op.create_index('idx_recexec_executed_at', 'recommendation_executions', ['executed_at'])


def downgrade() -> None:
    # Drop recommendation_executions
    op.drop_index('idx_recexec_executed_at', table_name='recommendation_executions')
    op.drop_index('idx_recexec_match_type', table_name='recommendation_executions')
    op.drop_index('idx_recexec_snapshot_id', table_name='recommendation_executions')
    op.drop_index('idx_recexec_recommendation_id', table_name='recommendation_executions')
    op.drop_table('recommendation_executions')
    
    # Drop recommendation_snapshots
    op.drop_index('idx_snap_notification_sent', table_name='recommendation_snapshots')
    op.drop_index('idx_snap_action', table_name='recommendation_snapshots')
    op.drop_index('idx_snap_evaluated_at', table_name='recommendation_snapshots')
    op.drop_index('idx_snap_recommendation_id', table_name='recommendation_snapshots')
    op.drop_table('recommendation_snapshots')
    
    # Drop position_recommendations
    op.drop_index('idx_posrec_recommendation_id', table_name='position_recommendations')
    op.drop_index('idx_posrec_first_detected', table_name='position_recommendations')
    op.drop_index('idx_posrec_source_exp', table_name='position_recommendations')
    op.drop_index('idx_posrec_account', table_name='position_recommendations')
    op.drop_index('idx_posrec_symbol', table_name='position_recommendations')
    op.drop_index('idx_posrec_status', table_name='position_recommendations')
    op.drop_table('position_recommendations')


