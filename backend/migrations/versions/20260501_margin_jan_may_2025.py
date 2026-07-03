"""Seed margin_monthly_balances for Jan–May 2025 (both accounts).

Revision ID: 20260501_margin_jan_may_2025
Revises: 20260501_margin_jun_nov_2025
Create Date: 2026-05-01

Real statement data from Robinhood PDFs.
Positive closing_balance = cash on hand (no margin).
"""
from alembic import op

revision = '20260501_margin_jan_may_2025'
down_revision = '20260501_margin_jun_nov_2025'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        INSERT INTO margin_monthly_balances
            (account_name, year, month, opening_balance, closing_balance, portfolio_value, source)
        VALUES
            -- Neel Investment (#170317739) Jan–May 2025
            ('neel_brokerage', 2025,  1,      NULL,   217527.08,  1151703.07, 'statement'),
            ('neel_brokerage', 2025,  2, 217527.08,    36400.00,  1027579.02, 'statement'),
            ('neel_brokerage', 2025,  3,  36400.00,      169.79,   946361.57, 'statement'),
            ('neel_brokerage', 2025,  4,    169.79,        0.00,   916968.83, 'statement'),
            ('neel_brokerage', 2025,  5,      0.00,    58600.00,   977567.24, 'statement'),
            -- Jaya Investment (#701552176) Jan–May 2025
            ('jaya_brokerage', 2025,  1,      0.00,   120700.00,   497667.37, 'statement'),
            ('jaya_brokerage', 2025,  2, 120700.00,    15729.17,   429784.54, 'statement'),
            ('jaya_brokerage', 2025,  3,  15729.17,        0.00,   396298.64, 'statement'),
            ('jaya_brokerage', 2025,  4,      0.00,        0.00,   411649.98, 'statement'),
            ('jaya_brokerage', 2025,  5,      0.00,    31250.00,   529045.40, 'statement')
        ON CONFLICT (account_name, year, month) DO NOTHING
    """)


def downgrade():
    op.execute("""
        DELETE FROM margin_monthly_balances
        WHERE account_name IN ('neel_brokerage', 'jaya_brokerage')
          AND year = 2025
          AND month BETWEEN 1 AND 5
    """)
