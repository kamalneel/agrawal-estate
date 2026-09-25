"""option_chain_quotes — real strikes, greeks and prices from the chain.

Revision ID: 20260924_option_chains
Revises: 20260916_price_history_iv
Create Date: 2026-09-24

Level 3 of the sync (Neel, 2026-09-18: "three kinds of sync — account
state, live prices, option chains"; built 2026-09-24). Until now the
engine knew the mark on contracts we already hold and nothing about any
other strike, so every strike and premium on a card was a Black-Scholes
estimate off one at-the-money implied vol. That is how NVDA's delta-15
strike came out at $235 when the market's was $227.50, and why a card
could not warn about SOXL's $2.90-wide bid/ask.

One row per live contract, replaced in place on each sync — this is a
current snapshot, not history (the underlyings' history lives in
symbol_price_history). About 4-5k rows for the tracked universe.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260924_option_chains'
down_revision = '20260916_price_history_iv'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'option_chain_quotes',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('symbol', sa.String(16), nullable=False),
        sa.Column('expiration_date', sa.Date, nullable=False),
        sa.Column('strike_price', sa.Numeric(12, 4), nullable=False),
        sa.Column('option_type', sa.String(4), nullable=False),      # call | put
        sa.Column('bid', sa.Numeric(12, 4)),
        sa.Column('ask', sa.Numeric(12, 4)),
        sa.Column('mark', sa.Numeric(12, 4)),
        sa.Column('delta', sa.Numeric(8, 4)),
        sa.Column('gamma', sa.Numeric(10, 6)),
        sa.Column('theta', sa.Numeric(10, 4)),
        sa.Column('vega', sa.Numeric(10, 4)),
        sa.Column('implied_vol', sa.Numeric(8, 4)),
        sa.Column('open_interest', sa.Integer),
        sa.Column('volume', sa.Integer),
        sa.Column('underlying_price', sa.Numeric(12, 4)),
        sa.Column('as_of', sa.DateTime, nullable=False),
        sa.Column('source', sa.String(40), nullable=False, server_default='robinhood_mcp'),
    )
    op.create_unique_constraint(
        'uq_option_chain_contract', 'option_chain_quotes',
        ['symbol', 'expiration_date', 'strike_price', 'option_type'])
    # the engine's hot path: "every strike for this symbol and expiry"
    op.create_index('ix_option_chain_symbol_exp', 'option_chain_quotes',
                    ['symbol', 'expiration_date'])


def downgrade() -> None:
    op.drop_index('ix_option_chain_symbol_exp', table_name='option_chain_quotes')
    op.drop_constraint('uq_option_chain_contract', 'option_chain_quotes', type_='unique')
    op.drop_table('option_chain_quotes')
