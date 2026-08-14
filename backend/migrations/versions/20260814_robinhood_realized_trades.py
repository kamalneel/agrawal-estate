"""Robinhood per-trade realized P&L, for assignment loss.

Why this table exists (Neel, 2026-08-14): the call-assignment figure was
computed as (reconstructed average cost - strike) * shares, and the
reconstruction summed BUY rows while ignoring SPLIT rows. NFLX split 10:1
in Nov 2025, so pre-split dollars were divided by pre-split share counts
and compared to a post-split strike -- a $733.36/share cost basis against
an $87 strike, reporting a $323,178 "loss" on an assignment Robinhood
records as a $1,065.71 GAIN. Five other events were wrong the same way.

Rather than patch the reconstruction and keep guessing, store the broker's
own realized gain per closing trade and use that. It needs no cost-basis
estimate, no split handling, and no lot reconstruction.

Revision ID: 20260814_rh_realized_trades
Revises: 20260808_cost_basis_history
Create Date: 2026-08-14
"""
from alembic import op
import sqlalchemy as sa

revision = '20260814_rh_realized_trades'
down_revision = '20260808_cost_basis_history'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'robinhood_realized_trades',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('source', sa.String(50), nullable=False, server_default='robinhood_mcp'),
        sa.Column('account_id', sa.String(50), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('trade_date', sa.Date(), nullable=False),
        sa.Column('quantity', sa.Numeric(18, 8), nullable=False),
        sa.Column('price', sa.Numeric(18, 8), nullable=True),
        sa.Column('realized_gain', sa.Numeric(18, 2), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        # Robinhood can report several closing trades for the same symbol on
        # one day (partial fills, separate lots), so quantity is part of the
        # identity -- keying on (account, symbol, date) alone would collapse
        # them into one and silently drop realized gain.
        sa.UniqueConstraint('account_id', 'symbol', 'trade_date', 'quantity',
                            name='uq_rh_realized_trade'),
    )
    op.create_index('ix_rh_realized_lookup', 'robinhood_realized_trades',
                    ['account_id', 'symbol', 'trade_date'])


def downgrade() -> None:
    op.drop_index('ix_rh_realized_lookup', table_name='robinhood_realized_trades')
    op.drop_table('robinhood_realized_trades')
