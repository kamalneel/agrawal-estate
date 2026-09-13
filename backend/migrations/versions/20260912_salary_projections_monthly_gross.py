"""Add monthly_gross to salary_projections.

Revision ID: 20260912_salary_gross
Revises: 8597cf945e92
Create Date: 2026-09-12

The Income page reports salary GROSS at every granularity — a W-2 year is
spread across the months worked, and an open year needs a stated gross rate
in a column rather than in the notes field where it had been living as prose.
monthly_net stays: BBD take-home maths use it, and it is the cross-check
against Monarch deposits.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260912_salary_gross'
down_revision = '8597cf945e92'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('salary_projections',
                  sa.Column('monthly_gross', sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column('salary_projections', 'monthly_gross')
