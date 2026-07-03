"""Seed margin_monthly_balances for Jun–Nov 2025 (both accounts).

Revision ID: 20260501_margin_jun_nov_2025
Revises: 20260501_margin_balances
Create Date: 2026-05-01

Real statement data from Robinhood PDFs.
Positive closing_balance = cash on hand (no margin).
Negative closing_balance = margin borrowed.
"""
from alembic import op

revision = '20260501_margin_jun_nov_2025'
down_revision = '20260501_margin_balances'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        INSERT INTO margin_monthly_balances
            (account_name, year, month, opening_balance, closing_balance, portfolio_value, source)
        VALUES
            -- Neel Investment (#170317739) Jun–Nov 2025
            ('neel_brokerage', 2025,  6,      NULL,       77.29,   959571.27, 'statement'),
            ('neel_brokerage', 2025,  7,     77.29,        0.00,   963986.87, 'statement'),
            ('neel_brokerage', 2025,  8,      0.00,     6000.00,  1018641.24, 'statement'),
            ('neel_brokerage', 2025,  9,   6000.00,     6077.29,  1157551.46, 'statement'),
            ('neel_brokerage', 2025, 10,   6077.29,     1000.00,  1177168.67, 'statement'),
            ('neel_brokerage', 2025, 11,   1000.00,    -5975.42,  1154354.77, 'statement'),
            -- Jaya Investment (#701552176) Jun–Nov 2025
            ('jaya_brokerage', 2025,  6,      NULL,       29.17,   528002.54, 'statement'),
            ('jaya_brokerage', 2025,  7,     29.17,   114279.17,   555013.85, 'statement'),
            ('jaya_brokerage', 2025,  8, 114279.17,    56000.00,   552654.54, 'statement'),
            ('jaya_brokerage', 2025,  9,  56000.00,    56000.00,   664743.03, 'statement'),
            ('jaya_brokerage', 2025, 10,  56000.00,    20029.17,   681962.55, 'statement'),
            ('jaya_brokerage', 2025, 11,  20029.17,        0.00,   677601.21, 'statement')
        ON CONFLICT (account_name, year, month) DO NOTHING
    """)


def downgrade():
    op.execute("""
        DELETE FROM margin_monthly_balances
        WHERE account_name IN ('neel_brokerage', 'jaya_brokerage')
          AND year = 2025
          AND month BETWEEN 6 AND 11
    """)
