"""Add put premium fields to option_premium_settings

Revision ID: add_put_premium_settings
Revises: add_tax_document_uploads
Create Date: 2026-01-23

Adds separate PUT premium tracking to option_premium_settings table.
The existing premium_per_contract field is now used for CALL premiums.

Also adds contract count and net total fields for both calls and puts
to track the data used in the 4-week average calculation.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_put_premium_settings'
down_revision = '20260122_tax_docs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add put premium columns to option_premium_settings."""
    # Add PUT premium column
    op.add_column('option_premium_settings',
        sa.Column('put_premium_per_contract', sa.Numeric(10, 2), nullable=True))

    # Add tracking columns for CALL data
    op.add_column('option_premium_settings',
        sa.Column('call_contracts_sold', sa.Integer(), nullable=True))
    op.add_column('option_premium_settings',
        sa.Column('call_net_total', sa.Numeric(12, 2), nullable=True))

    # Add tracking columns for PUT data
    op.add_column('option_premium_settings',
        sa.Column('put_contracts_sold', sa.Integer(), nullable=True))
    op.add_column('option_premium_settings',
        sa.Column('put_net_total', sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    """Remove put premium columns from option_premium_settings."""
    op.drop_column('option_premium_settings', 'put_net_total')
    op.drop_column('option_premium_settings', 'put_contracts_sold')
    op.drop_column('option_premium_settings', 'call_net_total')
    op.drop_column('option_premium_settings', 'call_contracts_sold')
    op.drop_column('option_premium_settings', 'put_premium_per_contract')
