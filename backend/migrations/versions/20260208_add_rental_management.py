"""Add rental management tables (agreements, summaries, expenses, documents)

Revision ID: 20260208_rental_management
Revises: 20260207_block_housekeeping
Create Date: 2026-02-08

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260208_rental_management'
down_revision = '20260207_block_housekeeping'
branch_labels = None
depends_on = None


def upgrade():
    # Rental Agreements
    op.create_table(
        'rental_agreements',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('property_id', sa.Integer(), sa.ForeignKey('properties.id', ondelete='CASCADE'), nullable=False),
        sa.Column('lease_start_date', sa.Date(), nullable=False),
        sa.Column('lease_end_date', sa.Date(), nullable=False),
        sa.Column('tenant_names', sa.String(500), nullable=False),
        sa.Column('monthly_rent', sa.Numeric(10, 2), nullable=False),
        sa.Column('monthly_hoa', sa.Numeric(10, 2), nullable=True),
        sa.Column('security_deposit', sa.Numeric(10, 2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('property_id', 'lease_start_date', name='uq_rental_agreement_property_start'),
    )
    op.create_index('idx_rental_agreement_property', 'rental_agreements', ['property_id'])

    # Rental Annual Summaries (v2 - linked to properties table)
    op.create_table(
        'rental_annual_summaries_v2',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('property_id', sa.Integer(), sa.ForeignKey('properties.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tax_year', sa.Integer(), nullable=False),
        sa.Column('annual_income', sa.Numeric(12, 2), nullable=True),
        sa.Column('cost_of_property', sa.Numeric(12, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('property_id', 'tax_year', name='uq_rental_annual_summary_v2'),
    )
    op.create_index('idx_rental_annual_summary_v2_property', 'rental_annual_summaries_v2', ['property_id'])

    # Rental Annual Expenses
    op.create_table(
        'rental_annual_expenses',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('property_id', sa.Integer(), sa.ForeignKey('properties.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tax_year', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('property_id', 'tax_year', 'category', name='uq_rental_expense_year_cat'),
    )
    op.create_index('idx_rental_expense_property_year', 'rental_annual_expenses', ['property_id', 'tax_year'])

    # Rental Documents
    op.create_table(
        'rental_documents',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('property_id', sa.Integer(), sa.ForeignKey('properties.id', ondelete='CASCADE'), nullable=False),
        sa.Column('document_type', sa.String(50), nullable=False),
        sa.Column('tax_year', sa.Integer(), nullable=True),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_hash', sa.String(64), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('mime_type', sa.String(100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_rental_doc_property', 'rental_documents', ['property_id'])


def downgrade():
    op.drop_index('idx_rental_doc_property', table_name='rental_documents')
    op.drop_table('rental_documents')
    op.drop_index('idx_rental_expense_property_year', table_name='rental_annual_expenses')
    op.drop_table('rental_annual_expenses')
    op.drop_index('idx_rental_annual_summary_v2_property', table_name='rental_annual_summaries_v2')
    op.drop_table('rental_annual_summaries_v2')
    op.drop_index('idx_rental_agreement_property', table_name='rental_agreements')
    op.drop_table('rental_agreements')
