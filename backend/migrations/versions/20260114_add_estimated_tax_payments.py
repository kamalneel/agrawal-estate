"""Add estimated_tax_payments table for tracking manual tax payments

Revision ID: 20260114_est_tax_payments
Revises: None (root)
Create Date: 2026-01-14 10:00:00.000000

Renamed 2026-08-14: this file shipped with the unedited template id
'a1b2c3d4e5f6', which is also the real id of
20251202_add_retirement_contributions.py. Two files declaring one revision
made every alembic command fail ("Revision a1b2c3d4e5f6 is present more
than once"), and left 20251202_add_sold_options_tracking.py's
down_revision ambiguous. It resolves to the retirement migration — same
date, and this one postdates it by six weeks. Only the id changed; the
revision stays a root, as it already was in practice.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260114_est_tax_payments'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create estimated_tax_payments table
    op.create_table('estimated_tax_payments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tax_year', sa.Integer(), nullable=False),
        sa.Column('payment_date', sa.Date(), nullable=False),
        sa.Column('payment_type', sa.String(length=20), nullable=False),  # 'federal' or 'state'
        sa.Column('state_code', sa.String(length=2), nullable=True),  # 'CA', 'NY', etc.
        sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('quarter', sa.Integer(), nullable=True),
        sa.Column('payment_method', sa.String(length=50), nullable=True),
        sa.Column('confirmation_number', sa.String(length=100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_estimated_tax_year', 'estimated_tax_payments', ['tax_year'], unique=False)
    op.create_index('idx_estimated_payment_date', 'estimated_tax_payments', ['payment_date'], unique=False)
    op.create_index('idx_estimated_payment_type', 'estimated_tax_payments', ['payment_type'], unique=False)

    # Insert seed data for the user's payments
    op.execute("""
        INSERT INTO estimated_tax_payments (tax_year, payment_date, payment_type, state_code, amount, quarter, payment_method, notes, created_at, updated_at)
        VALUES
        (2025, '2025-10-15', 'federal', NULL, 12000.00, 3, 'IRS Direct Pay', 'Q3 estimated payment', NOW(), NOW()),
        (2025, '2026-01-14', 'federal', NULL, 25000.00, 4, 'IRS Direct Pay', 'Q4 estimated payment', NOW(), NOW()),
        (2025, '2026-01-14', 'state', 'CA', 10000.00, 4, 'CA FTB Web Pay', 'Q4 estimated payment', NOW(), NOW())
    """)


def downgrade() -> None:
    op.drop_index('idx_estimated_payment_type', table_name='estimated_tax_payments')
    op.drop_index('idx_estimated_payment_date', table_name='estimated_tax_payments')
    op.drop_index('idx_estimated_tax_year', table_name='estimated_tax_payments')
    op.drop_table('estimated_tax_payments')
