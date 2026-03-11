"""Add V4 follow_up_conditions table for two-part recommendation tracking

Revision ID: add_v4_follow_up_conditions
Revises: add_account_cash_balances
Create Date: 2026-01-20

V4 introduces two-part recommendations like "CLOSE + wait for recovery".
This table tracks the follow-up conditions so the system can notify
when the second part should be executed.

Example flow:
1. V4 recommends: "CLOSE now, re-enter when stock drops 3%"
2. System creates FollowUpCondition with reference_price and threshold
3. On each scan, system checks if stock has dropped 3%
4. When triggered, system sends follow-up notification
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_v4_follow_up_conditions'
down_revision = 'add_account_cash_balances'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create follow_up_conditions table for V4 two-part recommendations."""
    op.create_table('follow_up_conditions',
        # Primary key
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),

        # Link to original recommendation
        sa.Column('recommendation_id', sa.Integer(), sa.ForeignKey('position_recommendations.id'), nullable=False),
        sa.Column('snapshot_id', sa.Integer(), sa.ForeignKey('recommendation_snapshots.id'), nullable=False),

        # Position identity (denormalized for quick querying)
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('account_name', sa.String(200), nullable=True),

        # Condition specification
        sa.Column('condition_type', sa.String(50), nullable=False),  # stock_drops_3_pct, stock_bounces, etc.
        sa.Column('threshold_pct', sa.Numeric(5, 4), nullable=True),  # 0.03 for 3%
        sa.Column('threshold_price', sa.Numeric(10, 2), nullable=True),  # Absolute price if applicable

        # Reference point (when condition was set)
        sa.Column('reference_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('reference_date', sa.DateTime(), nullable=False),

        # Follow-up action to recommend when triggered
        sa.Column('follow_up_action', sa.String(30), nullable=False),  # RE_ENTER, SELL_NEW, etc.

        # Trigger tracking
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('triggered_at', sa.DateTime(), nullable=True),
        sa.Column('trigger_price', sa.Numeric(10, 2), nullable=True),

        # Follow-up notification
        sa.Column('follow_up_notification_sent', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('follow_up_notification_at', sa.DateTime(), nullable=True),
        sa.Column('follow_up_snapshot_id', sa.Integer(), nullable=True),

        # Expiration
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('expired', sa.Boolean(), nullable=False, server_default='false'),

        # Metadata
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),

        # Primary key constraint
        sa.PrimaryKeyConstraint('id')
    )

    # Indexes for common queries
    op.create_index('idx_follow_up_symbol', 'follow_up_conditions', ['symbol'])
    op.create_index('idx_follow_up_active', 'follow_up_conditions', ['is_active'])
    op.create_index('idx_follow_up_recommendation', 'follow_up_conditions', ['recommendation_id'])


def downgrade() -> None:
    """Drop follow_up_conditions table."""
    op.drop_index('idx_follow_up_recommendation', table_name='follow_up_conditions')
    op.drop_index('idx_follow_up_active', table_name='follow_up_conditions')
    op.drop_index('idx_follow_up_symbol', table_name='follow_up_conditions')
    op.drop_table('follow_up_conditions')
