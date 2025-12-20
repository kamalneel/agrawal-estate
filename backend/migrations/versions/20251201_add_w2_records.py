"""Add W2 records table for persisting parsed W-2 data

Revision ID: f9a8b7c6d5e4
Revises: e8f7a6b5c4d3
Create Date: 2025-12-01 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9a8b7c6d5e4'
down_revision: Union[str, None] = '7a8df288786b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create w2_records table for persisting parsed W-2 data
    op.create_table('w2_records',
        sa.Column('employee_name', sa.String(length=200), nullable=False),
        sa.Column('employer', sa.String(length=300), nullable=False),
        sa.Column('tax_year', sa.Integer(), nullable=False),
        # Box 1 - Wages
        sa.Column('wages', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        # Box 2 - Federal tax withheld
        sa.Column('federal_tax_withheld', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        # Box 3 - Social security wages
        sa.Column('social_security_wages', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        # Box 4 - Social security tax
        sa.Column('social_security_tax', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        # Box 5 - Medicare wages
        sa.Column('medicare_wages', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        # Box 6 - Medicare tax
        sa.Column('medicare_tax', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        # Box 12 D - 401(k)
        sa.Column('retirement_401k', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        # Box 16 - State wages
        sa.Column('state_wages', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        # Box 17 - State tax
        sa.Column('state_tax_withheld', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        # Calculated net income
        sa.Column('net_income', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        # Source tracking
        sa.Column('source_file', sa.String(length=500), nullable=True),
        # Base model columns
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_name', 'employer', 'tax_year', name='uq_w2_record')
    )
    op.create_index('idx_w2_employee', 'w2_records', ['employee_name'], unique=False)
    op.create_index('idx_w2_year', 'w2_records', ['tax_year'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_w2_year', table_name='w2_records')
    op.drop_index('idx_w2_employee', table_name='w2_records')
    op.drop_table('w2_records')

