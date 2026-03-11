"""Add india_strategy_holdings table

Revision ID: 20260131_india_strategy
Revises: remove_robinhood_default
Create Date: 2026-01-31

Stores user's Indian stock portfolio with goal-based target values.
Separate from the existing india_investments module (Father's holdings).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260131_india_strategy'
down_revision = 'remove_robinhood_default'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create india_strategy_holdings table."""
    op.create_table(
        'india_strategy_holdings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('exchange', sa.String(10), nullable=False, server_default='NSE'),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('shares', sa.Numeric(12, 4), nullable=False, server_default='0'),
        sa.Column('avg_cost_inr', sa.Numeric(12, 2), nullable=True),
        sa.Column('current_price_inr', sa.Numeric(12, 2), nullable=True),
        sa.Column('target_value_inr', sa.Numeric(14, 2), nullable=True),
        sa.Column('account_name', sa.String(200), nullable=False, server_default='Default'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('idx_india_strategy_symbol', 'india_strategy_holdings', ['symbol'])
    op.create_index('idx_india_strategy_account', 'india_strategy_holdings', ['account_name'])


def downgrade() -> None:
    """Drop india_strategy_holdings table."""
    op.drop_index('idx_india_strategy_account', table_name='india_strategy_holdings')
    op.drop_index('idx_india_strategy_symbol', table_name='india_strategy_holdings')
    op.drop_table('india_strategy_holdings')
