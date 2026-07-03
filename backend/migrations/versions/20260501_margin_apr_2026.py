"""Seed margin_monthly_balances for April 2026 (both accounts).

Revision ID: 20260501_margin_apr_2026
Revises: 20260501_margin_jan_may_2025
Create Date: 2026-05-01

Real statement data from Robinhood PDFs (04/01/2026 to 04/30/2026).
Negative closing_balance = margin borrowed.
"""
from alembic import op

revision = '20260501_margin_apr_2026'
down_revision = '20260501_margin_jan_may_2025'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        INSERT INTO margin_monthly_balances
            (account_name, year, month, opening_balance, closing_balance, portfolio_value, source)
        VALUES
            -- Neel Investment (#170317739) April 2026
            ('neel_brokerage', 2026, 4, -103171.44, -96565.78, 996834.84, 'statement'),
            -- Jaya Investment (#701552176) April 2026
            ('jaya_brokerage', 2026, 4,  -47412.45, -46655.11, 555783.89, 'statement')
        ON CONFLICT (account_name, year, month) DO NOTHING
    """)


def downgrade():
    op.execute("""
        DELETE FROM margin_monthly_balances
        WHERE account_name IN ('neel_brokerage', 'jaya_brokerage')
          AND year = 2026
          AND month = 4
    """)
