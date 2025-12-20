"""Add rental income tables

Revision ID: 7a8df288786b
Revises: add_cash_tables
Create Date: 2025-11-27 23:49:33.051376

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a8df288786b'
down_revision: Union[str, None] = 'add_cash_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create rental properties table
    op.create_table('rental_properties',
        sa.Column('property_address', sa.String(length=500), nullable=False),
        sa.Column('property_name', sa.String(length=200), nullable=True),
        sa.Column('purchase_date', sa.Date(), nullable=True),
        sa.Column('purchase_price', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('current_value', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('is_active', sa.String(length=1), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('property_address')
    )
    
    # Create rental annual summaries table
    op.create_table('rental_annual_summaries',
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('tax_year', sa.Integer(), nullable=False),
        sa.Column('annual_income', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('total_expenses', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('net_income', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('expense_breakdown', sa.JSON(), nullable=True),
        sa.Column('source_file', sa.String(length=500), nullable=True),
        sa.Column('ingestion_id', sa.Integer(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['property_id'], ['rental_properties.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('property_id', 'tax_year', name='uq_rental_annual_summary')
    )
    op.create_index('idx_rental_summary_year', 'rental_annual_summaries', ['tax_year'], unique=False)
    
    # Create rental expenses table
    op.create_table('rental_expenses',
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('tax_year', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('ingestion_id', sa.Integer(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['property_id'], ['rental_properties.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('property_id', 'tax_year', 'category', name='uq_rental_expense')
    )
    op.create_index('idx_rental_expense_year', 'rental_expenses', ['tax_year'], unique=False)
    
    # Create rental monthly income table
    op.create_table('rental_monthly_income',
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('tax_year', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('gross_amount', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('ingestion_id', sa.Integer(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['property_id'], ['rental_properties.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('property_id', 'tax_year', 'month', name='uq_rental_monthly')
    )
    op.create_index('idx_rental_monthly_year', 'rental_monthly_income', ['tax_year'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_rental_monthly_year', table_name='rental_monthly_income')
    op.drop_table('rental_monthly_income')
    op.drop_index('idx_rental_expense_year', table_name='rental_expenses')
    op.drop_table('rental_expenses')
    op.drop_index('idx_rental_summary_year', table_name='rental_annual_summaries')
    op.drop_table('rental_annual_summaries')
    op.drop_table('rental_properties')
