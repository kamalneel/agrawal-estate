"""Add Father Stock Holdings table

Revision ID: 20251216_father_stocks
Revises: 20251216_father_mf_enrich
Create Date: 2025-12-16

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251216_father_stocks'
down_revision = '20251216_father_mf_enrich'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'father_stock_holdings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('investment_date', sa.Date(), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('company_name', sa.String(length=200), nullable=True),
        sa.Column('quantity', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('average_price', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('initial_invested_amount', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('amount_march_2025', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('current_price', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('current_amount', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('sector', sa.String(length=100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_father_stock_symbol', 'father_stock_holdings', ['symbol'], unique=False)
    op.create_index('idx_father_stock_investment_date', 'father_stock_holdings', ['investment_date'], unique=False)


def downgrade():
    op.drop_index('idx_father_stock_investment_date', table_name='father_stock_holdings')
    op.drop_index('idx_father_stock_symbol', table_name='father_stock_holdings')
    op.drop_table('father_stock_holdings')


