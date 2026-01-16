"""Add acquisition watchlist table for put selling

Revision ID: add_acquisition_watchlist
Revises: add_cash_secured_put_strategy
Create Date: 2026-01-13

Stores stocks the user wants to acquire via cash-secured puts,
regardless of TA score. Different from income-generation puts.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_acquisition_watchlist'
down_revision = 'add_cash_secured_put_strategy'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create acquisition watchlist table."""
    op.create_table(
        'acquisition_watchlist',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('target_price', sa.Numeric(10, 2), nullable=True),  # Price user wants to buy at
        sa.Column('notes', sa.Text(), nullable=True),  # User notes about why they want this stock
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True, onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )

    # Create unique index on symbol (only one entry per symbol)
    op.create_index('idx_acquisition_watchlist_symbol', 'acquisition_watchlist', ['symbol'], unique=True)


def downgrade() -> None:
    """Drop acquisition watchlist table."""
    op.drop_index('idx_acquisition_watchlist_symbol', table_name='acquisition_watchlist')
    op.drop_table('acquisition_watchlist')
