"""Add owner column to father_mutual_fund_holdings.

Revision ID: 20260306_mf_owner
Revises: 20260219_tax_dependents
Create Date: 2026-03-06

Adds owner column to father_mutual_fund_holdings so the table
can store holdings for multiple family members (Father, Mother).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20260306_mf_owner'
down_revision = '20260219_tax_dependents'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'father_mutual_fund_holdings',
        sa.Column('owner', sa.String(50), nullable=True, server_default='Father'),
    )
    # Backfill existing rows
    op.execute("UPDATE father_mutual_fund_holdings SET owner = 'Father' WHERE owner IS NULL")
    # Make non-nullable after backfill
    op.alter_column('father_mutual_fund_holdings', 'owner', nullable=False)
    op.create_index('idx_father_mf_owner', 'father_mutual_fund_holdings', ['owner'])


def downgrade():
    op.drop_index('idx_father_mf_owner', table_name='father_mutual_fund_holdings')
    op.drop_column('father_mutual_fund_holdings', 'owner')
