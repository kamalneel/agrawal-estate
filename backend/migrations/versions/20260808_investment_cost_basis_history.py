"""Add investment_cost_basis_history table.

Revision ID: 20260808_cost_basis_history
Revises: 20260609_cash_breakdown
Create Date: 2026-08-08

Per-account, per-symbol average cost per share over time, sourced from
Robinhood's own average_buy_price (average-cost accounting, already
adjusted for partial sells) via the MCP sync — see
scripts/robinhood_mcp_bridge.py and POST /ingestion/cost-basis.

Independent side-table (mirrors symbol_price_history's shape/role)
rather than a column on investment_holdings_history, so it never
touches the nightly snapshot job or its existing dedup constraint.
Feeds assignment_loss_service.py's "vs. cost basis" figure for CALL
assignments (Neel, 2026-08-08): the strike-vs-market "Loss" column
already there answers "what did being assigned cost me vs. the market
that day" — this answers the different question "did I make or lose
real money vs. what I paid," which only applies to calls (a put
assignment creates a new lot AT the strike, so there's no prior cost
basis to compare against).
"""
from alembic import op
import sqlalchemy as sa

revision = '20260808_cost_basis_history'
down_revision = '20260609_cash_breakdown'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'investment_cost_basis_history',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('account_id', sa.String(100), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('avg_cost_per_share', sa.Numeric(18, 4), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('source', 'account_id', 'symbol', 'snapshot_date', name='uq_cost_basis_history'),
    )
    op.create_index('idx_cost_basis_history_lookup', 'investment_cost_basis_history',
                     ['account_id', 'symbol', 'snapshot_date'])


def downgrade() -> None:
    op.drop_index('idx_cost_basis_history_lookup', table_name='investment_cost_basis_history')
    op.drop_table('investment_cost_basis_history')
