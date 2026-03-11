"""Add pending_orders table for V5

Revision ID: 20260204_add_pending_orders
Revises: 20260131_add_india_strategy_holdings
Create Date: 2026-02-04

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260204_add_pending_orders'
down_revision = '20260131_india_strategy'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pending_orders',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('snapshot_id', sa.Integer(), sa.ForeignKey('sold_options_snapshots.id', ondelete='CASCADE'), nullable=False),

        # Order identification
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('order_type', sa.String(30), nullable=False),  # 'ROLL', 'SELL_TO_OPEN', 'BUY_TO_CLOSE'
        sa.Column('option_type', sa.String(10), nullable=True),  # 'call' or 'put'

        # Roll details
        sa.Column('from_expiration', sa.Date(), nullable=True),
        sa.Column('to_expiration', sa.Date(), nullable=True),
        sa.Column('strike_price', sa.Numeric(10, 2), nullable=True),

        # Order details
        sa.Column('contracts', sa.Integer(), nullable=False, default=1),
        sa.Column('limit_price', sa.Numeric(10, 2), nullable=True),

        # Account info
        sa.Column('account_name', sa.String(200), nullable=True),

        # Linking to position
        sa.Column('linked_position_id', sa.Integer(), sa.ForeignKey('sold_options.id', ondelete='SET NULL'), nullable=True),

        # Status tracking
        sa.Column('status', sa.String(20), nullable=False, default='pending'),

        # Raw text
        sa.Column('raw_text', sa.String(500), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create indexes
    op.create_index('idx_pending_order_symbol', 'pending_orders', ['symbol'])
    op.create_index('idx_pending_order_status', 'pending_orders', ['status'])
    op.create_index('idx_pending_order_account', 'pending_orders', ['account_name'])


def downgrade():
    op.drop_index('idx_pending_order_account', table_name='pending_orders')
    op.drop_index('idx_pending_order_status', table_name='pending_orders')
    op.drop_index('idx_pending_order_symbol', table_name='pending_orders')
    op.drop_table('pending_orders')
