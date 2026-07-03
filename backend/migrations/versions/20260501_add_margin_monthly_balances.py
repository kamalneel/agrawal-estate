"""Add margin_monthly_balances table and seed statement data.

Revision ID: 20260501_margin_balances
Revises: 20260306_mf_owner
Create Date: 2026-05-01

Stores real monthly brokerage cash balances from Robinhood statements.
Negative closing_balance = margin borrowed; positive = cash on hand.
Seed data covers Dec 2025 through Mar 2026 for both brokerage accounts.
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

revision = '20260501_margin_balances'
down_revision = '20260306_mf_owner'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'margin_monthly_balances',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('account_name', sa.String(200), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('opening_balance', sa.Numeric(14, 2), nullable=True),
        sa.Column('closing_balance', sa.Numeric(14, 2), nullable=True),
        sa.Column('portfolio_value', sa.Numeric(18, 2), nullable=True),
        sa.Column('source', sa.String(50), nullable=True, server_default='statement'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        'idx_margin_balance_account_period',
        'margin_monthly_balances',
        ['account_name', 'year', 'month'],
        unique=True,
    )

    # Seed real statement data
    # Negative closing_balance = margin borrowed from Robinhood.
    # Feb 2026 Neel / Mar 2026 Jaya spikes are car purchases via margin (BBD strategy).
    op.execute("""
        INSERT INTO margin_monthly_balances
            (account_name, year, month, opening_balance, closing_balance, portfolio_value, source)
        VALUES
            -- Neel Investment (#170317739)
            ('neel_brokerage', 2025, 12, -5975.42,   -10436.87,  1138682.40, 'statement'),
            ('neel_brokerage', 2026,  1, -10436.87,  -20010.70,  1077052.83, 'statement'),
            ('neel_brokerage', 2026,  2, -20010.70,  -129606.87,  999297.26, 'statement'),
            ('neel_brokerage', 2026,  3, -129606.87, -103171.44,  945456.72, 'statement'),
            -- Jaya Investment (#701552176)
            ('jaya_brokerage', 2025, 12,     0.00,    72500.00,  687459.86, 'statement'),
            ('jaya_brokerage', 2026,  1, 72500.00,    81000.00,  648305.93, 'statement'),
            ('jaya_brokerage', 2026,  2, 81000.00,    10010.80,  617961.94, 'statement'),
            ('jaya_brokerage', 2026,  3, 10010.80,   -47412.45,  530322.49, 'statement')
    """)


def downgrade():
    op.drop_index('idx_margin_balance_account_period', table_name='margin_monthly_balances')
    op.drop_table('margin_monthly_balances')
