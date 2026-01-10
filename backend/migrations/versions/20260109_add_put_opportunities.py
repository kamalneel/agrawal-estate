"""Add put opportunities and outcomes tables for cash-secured put strategy

Revision ID: 20260109_put_opportunities
Revises: 20260106_uncovered_positions
Create Date: 2026-01-09

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = '20260109_put_opportunities'
down_revision = '20260106_uncovered'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Table to track put selling opportunities and recommendations
    op.create_table(
        'put_opportunities',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('symbol', sa.String(20), nullable=False, index=True),
        sa.Column('account_name', sa.String(100), nullable=True),
        
        # Recommendation details
        sa.Column('recommendation_date', sa.Date(), nullable=False, index=True),
        sa.Column('score', sa.Numeric(10, 2), nullable=True),
        sa.Column('grade', sa.String(5), nullable=True),
        
        # Option details
        sa.Column('strike', sa.Numeric(10, 2), nullable=False),
        sa.Column('expiration', sa.Date(), nullable=False),
        sa.Column('bid_price', sa.Numeric(10, 4), nullable=True),
        sa.Column('ask_price', sa.Numeric(10, 4), nullable=True),
        sa.Column('delta', sa.Numeric(6, 4), nullable=True),
        sa.Column('premium_per_contract', sa.Numeric(10, 2), nullable=True),
        
        # Stock price at recommendation
        sa.Column('stock_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('otm_pct', sa.Numeric(6, 2), nullable=True),
        
        # Technical indicators at recommendation time
        sa.Column('rsi', sa.Numeric(6, 2), nullable=True),
        sa.Column('bb_position_pct', sa.Numeric(6, 2), nullable=True),
        sa.Column('bb_lower', sa.Numeric(10, 2), nullable=True),
        sa.Column('bb_upper', sa.Numeric(10, 2), nullable=True),
        sa.Column('trend', sa.String(20), nullable=True),
        
        # TA scoring breakdown
        sa.Column('rsi_score', sa.Integer(), nullable=True),
        sa.Column('bb_score', sa.Integer(), nullable=True),
        sa.Column('premium_score', sa.Integer(), nullable=True),
        sa.Column('ta_score', sa.Integer(), nullable=True),
        
        # Status tracking
        sa.Column('status', sa.String(30), nullable=False, server_default='recommended', index=True),
        # Status values: 'recommended', 'acted', 'skipped', 'expired_profitable', 'assigned', 'closed_early'
        
        # Full context for debugging
        sa.Column('full_context', JSONB, nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True, onupdate=sa.func.now()),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for common queries
    op.create_index('idx_put_opportunities_symbol_date', 'put_opportunities', ['symbol', 'recommendation_date'])
    op.create_index('idx_put_opportunities_grade', 'put_opportunities', ['grade'])
    op.create_index('idx_put_opportunities_expiration', 'put_opportunities', ['expiration'])
    
    # Table to track outcomes and user actions on put opportunities
    op.create_table(
        'put_outcomes',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('opportunity_id', sa.Integer(), nullable=False, index=True),
        
        # User action
        sa.Column('action_taken', sa.String(30), nullable=False),
        # Values: 'sold', 'skipped', 'partial'
        sa.Column('action_date', sa.DateTime(), nullable=True),
        sa.Column('contracts_sold', sa.Integer(), nullable=True),
        sa.Column('premium_received', sa.Numeric(10, 2), nullable=True),
        sa.Column('fill_price', sa.Numeric(10, 4), nullable=True),
        
        # Outcome (filled after expiration or close)
        sa.Column('expiration_outcome', sa.String(30), nullable=True),
        # Values: 'expired_otm', 'assigned', 'closed_early', 'rolled'
        sa.Column('outcome_date', sa.DateTime(), nullable=True),
        sa.Column('close_price', sa.Numeric(10, 4), nullable=True),
        sa.Column('final_pnl', sa.Numeric(10, 2), nullable=True),
        
        # Assignment details (if assigned)
        sa.Column('assignment_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('shares_assigned', sa.Integer(), nullable=True),
        
        # User feedback (explicit RLHF)
        sa.Column('user_feedback', JSONB, nullable=True),
        # Example: {"skip_reason": "premium_too_low", "comment": "Need at least $50"}
        
        # Prediction validation
        sa.Column('was_prediction_correct', sa.Boolean(), nullable=True),
        sa.Column('stock_price_at_expiry', sa.Numeric(10, 2), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True, onupdate=sa.func.now()),
        
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['opportunity_id'], ['put_opportunities.id'], ondelete='CASCADE')
    )
    
    # Create index for outcome analysis
    op.create_index('idx_put_outcomes_action', 'put_outcomes', ['action_taken'])
    op.create_index('idx_put_outcomes_expiration', 'put_outcomes', ['expiration_outcome'])
    
    # Table to track learned user preferences for put selling
    op.create_table(
        'put_user_preferences',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        
        # Symbol-level preferences
        sa.Column('symbol', sa.String(20), nullable=True, index=True),
        # NULL symbol = global preference
        
        # Learned preferences
        sa.Column('preference_score', sa.Numeric(6, 2), nullable=True),
        # Positive = user likes this, Negative = user avoids this
        
        sa.Column('acceptance_rate', sa.Numeric(5, 2), nullable=True),
        # Percentage of recommendations acted upon
        
        sa.Column('min_premium_threshold', sa.Numeric(10, 2), nullable=True),
        # Learned minimum premium user will act on
        
        sa.Column('min_score_threshold', sa.Integer(), nullable=True),
        # Learned minimum score user will act on
        
        sa.Column('sample_size', sa.Integer(), nullable=True, server_default='0'),
        # Number of observations this preference is based on
        
        # Context
        sa.Column('notes', sa.Text(), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True, onupdate=sa.func.now()),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create unique constraint for symbol preferences
    op.create_index('idx_put_preferences_symbol_unique', 'put_user_preferences', ['symbol'], unique=True)


def downgrade() -> None:
    op.drop_index('idx_put_preferences_symbol_unique', table_name='put_user_preferences')
    op.drop_table('put_user_preferences')
    
    op.drop_index('idx_put_outcomes_expiration', table_name='put_outcomes')
    op.drop_index('idx_put_outcomes_action', table_name='put_outcomes')
    op.drop_table('put_outcomes')
    
    op.drop_index('idx_put_opportunities_expiration', table_name='put_opportunities')
    op.drop_index('idx_put_opportunities_grade', table_name='put_opportunities')
    op.drop_index('idx_put_opportunities_symbol_date', table_name='put_opportunities')
    op.drop_table('put_opportunities')

