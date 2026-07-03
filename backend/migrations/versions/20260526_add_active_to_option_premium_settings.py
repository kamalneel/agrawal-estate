"""Add active flag to option_premium_settings for retired put symbols.

Revision ID: 20260526_add_active_to_option_premium_settings
Revises: 20260501_margin_apr_2026
Create Date: 2026-05-26

Symbols marked active=False are excluded from the puts history table
on the Options Income page (unless they have an open position).
"""
from alembic import op
import sqlalchemy as sa

revision = '20260526_active_puts'
down_revision = '20260501_margin_apr_2026'
branch_labels = None
depends_on = None

RETIRED_SYMBOLS = ['AGQ', 'BABA', 'COIN', 'CRCL', 'FIG', 'IBIT', 'MSTR']


def upgrade() -> None:
    op.add_column(
        'option_premium_settings',
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true')
    )
    op.execute(
        f"UPDATE option_premium_settings SET active = false WHERE symbol IN ({','.join(repr(s) for s in RETIRED_SYMBOLS)})"
    )


def downgrade() -> None:
    op.drop_column('option_premium_settings', 'active')
