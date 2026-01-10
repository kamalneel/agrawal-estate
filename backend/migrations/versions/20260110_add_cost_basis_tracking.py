"""Add cost basis tracking tables for capital gains

This migration adds support for detailed cost basis tracking:
1. stock_lot - tracks each purchase lot with cost basis
2. stock_lot_sale - matches sales to specific lots for gain/loss calculation

This enables accurate capital gains reporting instead of estimates.

Revision ID: 20260110_cost_basis
Revises: 20260106_uncovered
Create Date: 2026-01-10

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260110_cost_basis'
down_revision = '20260106_uncovered'
branch_labels = None
depends_on = None


def upgrade():
    # Create stock_lot table - tracks each purchase lot
    op.create_table('stock_lot',
        sa.Column('lot_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('purchase_date', sa.Date(), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('cost_basis', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('cost_per_share', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('account_id', sa.String(length=50), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('purchase_transaction_id', sa.Integer(), nullable=True),
        sa.Column('quantity_remaining', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
        sa.Column('lot_method', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('lot_id')
    )
    op.create_index('idx_stock_lot_symbol', 'stock_lot', ['symbol'], unique=False)
    op.create_index('idx_stock_lot_source', 'stock_lot', ['source'], unique=False)
    op.create_index('idx_stock_lot_status', 'stock_lot', ['status'], unique=False)
    op.create_index('idx_stock_lot_purchase_date', 'stock_lot', ['purchase_date'], unique=False)

    # Create stock_lot_sale table - matches sales to lots
    op.create_table('stock_lot_sale',
        sa.Column('sale_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lot_id', sa.Integer(), nullable=False),
        sa.Column('sale_date', sa.Date(), nullable=False),
        sa.Column('sale_transaction_id', sa.Integer(), nullable=True),
        sa.Column('quantity_sold', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('proceeds', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('proceeds_per_share', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('cost_basis', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('gain_loss', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('holding_period_days', sa.Integer(), nullable=False),
        sa.Column('is_long_term', sa.Boolean(), nullable=False),
        sa.Column('tax_year', sa.Integer(), nullable=False),
        sa.Column('wash_sale', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('wash_sale_disallowed', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('sale_id'),
        sa.ForeignKeyConstraint(['lot_id'], ['stock_lot.lot_id'], ondelete='CASCADE')
    )
    op.create_index('idx_stock_lot_sale_lot', 'stock_lot_sale', ['lot_id'], unique=False)
    op.create_index('idx_stock_lot_sale_tax_year', 'stock_lot_sale', ['tax_year'], unique=False)
    op.create_index('idx_stock_lot_sale_date', 'stock_lot_sale', ['sale_date'], unique=False)
    op.create_index('idx_stock_lot_sale_is_long_term', 'stock_lot_sale', ['is_long_term'], unique=False)


def downgrade():
    op.drop_index('idx_stock_lot_sale_is_long_term', table_name='stock_lot_sale')
    op.drop_index('idx_stock_lot_sale_date', table_name='stock_lot_sale')
    op.drop_index('idx_stock_lot_sale_tax_year', table_name='stock_lot_sale')
    op.drop_index('idx_stock_lot_sale_lot', table_name='stock_lot_sale')
    op.drop_table('stock_lot_sale')

    op.drop_index('idx_stock_lot_purchase_date', table_name='stock_lot')
    op.drop_index('idx_stock_lot_status', table_name='stock_lot')
    op.drop_index('idx_stock_lot_source', table_name='stock_lot')
    op.drop_index('idx_stock_lot_symbol', table_name='stock_lot')
    op.drop_table('stock_lot')
