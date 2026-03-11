"""Add tax_dependents table and dependent_care_benefits to w2_records.

Revision ID: 20260219_tax_dependents
Revises: 20260213_business_investment
Create Date: 2026-02-19
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20260219_tax_dependents'
down_revision = '20260213_business_investment'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tax_dependents table
    op.create_table(
        'tax_dependents',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('relationship_type', sa.String(50), nullable=False),
        sa.Column('date_of_birth', sa.Date(), nullable=False),
        sa.Column('tax_year', sa.Integer(), nullable=False),
        sa.Column('ssn_last_four', sa.String(4), nullable=True),
        sa.Column('qualifies_for_ctc', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'tax_year', name='uq_tax_dependent_name_year'),
    )
    op.create_index('idx_tax_dependent_year', 'tax_dependents', ['tax_year'])

    # Add dependent_care_benefits (Box 10) to w2_records
    op.add_column('w2_records', sa.Column(
        'dependent_care_benefits', sa.Numeric(18, 2), nullable=False, server_default='0'
    ))


def downgrade() -> None:
    op.drop_column('w2_records', 'dependent_care_benefits')
    op.drop_index('idx_tax_dependent_year', table_name='tax_dependents')
    op.drop_table('tax_dependents')
