"""Add bbd_settings table for configurable BBD assumptions.

Revision ID: 20260502_bbd_settings
Revises: 20260501_margin_jan_may_2025
Create Date: 2026-05-02

Stores the single-row settings record with defaults:
  - assumed_annual_growth: 8% (pure market growth target)
  - assumed_combined_return: 16% (8% growth + ~8% reinvested options, used for borrow target)
  - assumed_monthly_yield: 1%/month options income target
  - assumed_annual_margin_rate: 5% margin interest
  - margin_ltv: 70% loan-to-value
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

revision = '20260502_bbd_settings'
down_revision = '20260501_margin_jan_may_2025'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bbd_settings',
        sa.Column('id', sa.Integer(), primary_key=True, default=1),
        sa.Column('assumed_annual_growth', sa.Numeric(6, 4), nullable=False, server_default='0.0800'),
        sa.Column('assumed_combined_return', sa.Numeric(6, 4), nullable=False, server_default='0.1600'),
        sa.Column('assumed_monthly_yield', sa.Numeric(6, 4), nullable=False, server_default='0.0100'),
        sa.Column('assumed_annual_margin_rate', sa.Numeric(6, 4), nullable=False, server_default='0.0500'),
        sa.Column('margin_ltv', sa.Numeric(6, 4), nullable=False, server_default='0.7000'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.execute("""
        INSERT INTO bbd_settings (id, assumed_annual_growth, assumed_combined_return,
            assumed_monthly_yield, assumed_annual_margin_rate, margin_ltv)
        VALUES (1, 0.0800, 0.1600, 0.0100, 0.0500, 0.7000)
    """)


def downgrade():
    op.drop_table('bbd_settings')
