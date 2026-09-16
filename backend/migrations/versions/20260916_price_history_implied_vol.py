"""symbol_price_history.implied_vol — the market's implied volatility, per symbol per day.

Revision ID: 20260916_price_history_iv
Revises: 20260913_assignment_tax_notices
Create Date: 2026-09-16

The V7 engine priced strikes and premiums from 20-day REALIZED vol. On
NVDA that was 52% against a market implied 32%: the delta-15 strike
landed at $235 (market delta 0.05, $0.25) instead of $227.50 (delta
0.14, $0.76) and the estimate read $855 against a real ~$450 (Neel,
2026-09-16: "I'm getting different numbers. Why the gap?"). The sync
now stores an at-the-money implied vol alongside the close; the engine
uses it and falls back to realized only when it is missing.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260916_price_history_iv'
down_revision = '20260913_assignment_tax_notices'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('symbol_price_history', sa.Column('implied_vol', sa.Numeric(8, 4), nullable=True))


def downgrade() -> None:
    op.drop_column('symbol_price_history', 'implied_vol')
