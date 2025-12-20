"""Add sold options tracking tables

Revision ID: sold_options_001
Revises: 20251202_add_retirement_contributions
Create Date: 2025-12-02 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'sold_options_001'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Table to store each screenshot upload session
    op.create_table('sold_options_snapshots',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),  # 'robinhood', 'schwab', etc.
        sa.Column('account_name', sa.String(length=200), nullable=True),  # Which account this applies to
        sa.Column('snapshot_date', sa.DateTime(), nullable=False),  # When the screenshot was taken/uploaded
        sa.Column('image_path', sa.String(length=500), nullable=True),  # Path to stored image
        sa.Column('raw_extracted_text', sa.Text(), nullable=True),  # Raw OCR/AI extracted text
        sa.Column('parsing_status', sa.String(length=20), nullable=False),  # 'pending', 'success', 'failed'
        sa.Column('parsing_error', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_sold_snapshot_date', 'sold_options_snapshots', ['snapshot_date'], unique=False)
    op.create_index('idx_sold_snapshot_source', 'sold_options_snapshots', ['source'], unique=False)
    
    # Table to store individual sold options parsed from screenshots
    op.create_table('sold_options',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('snapshot_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),  # e.g., 'AAPL', 'TSLA'
        sa.Column('strike_price', sa.Numeric(precision=10, scale=2), nullable=False),  # e.g., 285.00
        sa.Column('option_type', sa.String(length=10), nullable=False),  # 'call' or 'put'
        sa.Column('expiration_date', sa.Date(), nullable=True),  # When the option expires
        sa.Column('contracts_sold', sa.Integer(), nullable=False),  # Number of contracts
        sa.Column('premium_per_contract', sa.Numeric(precision=10, scale=2), nullable=True),  # Current premium
        sa.Column('gain_loss_percent', sa.Numeric(precision=10, scale=2), nullable=True),  # e.g., +54.35%
        sa.Column('status', sa.String(length=20), nullable=True),  # 'open', 'closed', 'expired'
        sa.Column('raw_text', sa.String(length=500), nullable=True),  # Original text from screenshot
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['snapshot_id'], ['sold_options_snapshots.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_sold_opt_symbol', 'sold_options', ['symbol'], unique=False)
    op.create_index('idx_sold_opt_expiration', 'sold_options', ['expiration_date'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_sold_opt_expiration', table_name='sold_options')
    op.drop_index('idx_sold_opt_symbol', table_name='sold_options')
    op.drop_table('sold_options')
    op.drop_index('idx_sold_snapshot_source', table_name='sold_options_snapshots')
    op.drop_index('idx_sold_snapshot_date', table_name='sold_options_snapshots')
    op.drop_table('sold_options_snapshots')

