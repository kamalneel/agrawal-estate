"""Add salary_projections table for BBD income offset.

Revision ID: 20260208_salary_projections
Revises: 20260208_rental_management
Create Date: 2026-02-08
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers
revision = '20260208_salary_projections'
down_revision = '20260208_rental_management'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'salary_projections',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('person', sa.String(100), nullable=False),
        sa.Column('monthly_net', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('effective_from', sa.String(7), nullable=False),
        sa.Column('effective_to', sa.String(7), nullable=True),
        sa.Column('notes', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('person', 'effective_from', name='uq_salary_projection_person_from'),
    )

    # Seed with Jaya's 2025 salary from W-2 data
    # Net income = wages - federal_tax - state_tax - social_security - medicare
    # $124,300/yr net => ~$10,358/mo
    op.execute(
        sa.text("""
            INSERT INTO salary_projections (person, monthly_net, effective_from, effective_to, notes, created_at, updated_at)
            VALUES ('Jaya', 10358, '2025-01', '2025-12', 'Aviatrix W-2 net income', NOW(), NOW())
        """)
    )


def downgrade() -> None:
    op.drop_table('salary_projections')
