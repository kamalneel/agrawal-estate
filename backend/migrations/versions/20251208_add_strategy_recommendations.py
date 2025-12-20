"""Add strategy recommendations tracking table.

Revision ID: 20251208_strategy_recommendations
Revises: 20251208_premium_settings
Create Date: 2025-12-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251208_strat_recs'
down_revision = '20251208_premium_settings'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create strategy_recommendations table
    op.create_table(
        'strategy_recommendations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('recommendation_id', sa.String(length=100), nullable=False),
        sa.Column('recommendation_type', sa.String(length=50), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('priority', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('action', sa.String(length=500), nullable=True),
        sa.Column('potential_income', sa.Numeric(10, 2), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True, server_default='pending'),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.Column('acted_at', sa.DateTime(), nullable=True),
        sa.Column('action_taken', sa.String(length=200), nullable=True),
        sa.Column('context_snapshot', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add indexes for common queries
    op.create_index('idx_recommendations_id', 'strategy_recommendations', ['recommendation_id'])
    op.create_index('idx_recommendations_type', 'strategy_recommendations', ['recommendation_type'])
    op.create_index('idx_recommendations_status', 'strategy_recommendations', ['status'])
    op.create_index('idx_recommendations_created', 'strategy_recommendations', ['created_at'])


def downgrade() -> None:
    op.drop_index('idx_recommendations_created', table_name='strategy_recommendations')
    op.drop_index('idx_recommendations_status', table_name='strategy_recommendations')
    op.drop_index('idx_recommendations_type', table_name='strategy_recommendations')
    op.drop_index('idx_recommendations_id', table_name='strategy_recommendations')
    op.drop_table('strategy_recommendations')

