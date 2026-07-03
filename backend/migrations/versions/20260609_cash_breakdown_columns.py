"""Add full cash breakdown columns to account_cash_balances.

Revision ID: 20260609_cash_breakdown
Revises: 20260526_active_puts
Create Date: 2026-06-09

Adds margin_total, margin_used, options_collateral, pending_orders, net_total
columns to support the Robinhood cash section copy-paste feature.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260609_cash_breakdown'
down_revision = '20260526_active_puts'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('account_cash_balances', sa.Column('margin_total',       sa.Numeric(12, 2), nullable=True))
    op.add_column('account_cash_balances', sa.Column('margin_used',        sa.Numeric(12, 2), nullable=True))
    op.add_column('account_cash_balances', sa.Column('options_collateral', sa.Numeric(12, 2), nullable=True))
    op.add_column('account_cash_balances', sa.Column('pending_orders',     sa.Numeric(12, 2), nullable=True))
    op.add_column('account_cash_balances', sa.Column('net_total',          sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column('account_cash_balances', 'net_total')
    op.drop_column('account_cash_balances', 'pending_orders')
    op.drop_column('account_cash_balances', 'options_collateral')
    op.drop_column('account_cash_balances', 'margin_used')
    op.drop_column('account_cash_balances', 'margin_total')
