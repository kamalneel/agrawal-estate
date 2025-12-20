"""Add weekly recommendation tracking table.

Revision ID: 20251209_weekly_tracking
Revises: 20251209_notif_tracking
Create Date: 2025-12-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251209_weekly_tracking'
down_revision = '20251209_notif_tracking'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create weekly_recommendation_tracking table
    op.create_table(
        'weekly_recommendation_tracking',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('strategy_type', sa.String(length=50), nullable=False),
        sa.Column('week_start_date', sa.Date(), nullable=False),
        sa.Column('recommendation_id', sa.String(length=100), nullable=False),
        sa.Column('potential_profit', sa.Numeric(10, 2), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add index
    op.create_index('idx_weekly_rec_week_strategy', 'weekly_recommendation_tracking', ['week_start_date', 'strategy_type'])


def downgrade() -> None:
    op.drop_index('idx_weekly_rec_week_strategy', table_name='weekly_recommendation_tracking')
    op.drop_table('weekly_recommendation_tracking')



