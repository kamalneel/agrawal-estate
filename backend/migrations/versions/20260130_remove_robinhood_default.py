"""Remove robinhood_default account data

Cleans up erroneous robinhood_default account created by fallback
in the Robinhood CSV parser when filenames didn't match patterns.
This account has $0 value and its data was already mapped to
neel_brokerage during ingestion.

Revision ID: remove_robinhood_default
Revises: populate_cost_basis
Create Date: 2026-01-30

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'remove_robinhood_default'
down_revision = 'populate_cost_basis'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Delete all robinhood_default account data."""
    conn = op.get_bind()

    for table in ('investment_holdings', 'portfolio_snapshots', 'investment_accounts'):
        conn.execute(
            sa.text(f"DELETE FROM {table} WHERE account_id = 'robinhood_default'")
        )


def downgrade() -> None:
    """No-op: cannot restore deleted data."""
    pass
