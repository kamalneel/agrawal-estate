"""Add enrichment fields to father_mutual_fund_holdings

Revision ID: 20251216_father_mf_enrich
Revises: 
Create Date: 2025-12-16

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251216_father_mf_enrich'
down_revision = 'add_father_mf_holdings'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to father_mutual_fund_holdings
    op.add_column('father_mutual_fund_holdings', sa.Column('scheme_code', sa.String(length=20), nullable=True))
    op.add_column('father_mutual_fund_holdings', sa.Column('isin', sa.String(length=20), nullable=True))
    op.add_column('father_mutual_fund_holdings', sa.Column('return_10y', sa.Numeric(precision=8, scale=2), nullable=True))
    op.add_column('father_mutual_fund_holdings', sa.Column('volatility', sa.Numeric(precision=8, scale=4), nullable=True))
    op.add_column('father_mutual_fund_holdings', sa.Column('sharpe_ratio', sa.Numeric(precision=8, scale=4), nullable=True))
    op.add_column('father_mutual_fund_holdings', sa.Column('alpha', sa.Numeric(precision=8, scale=4), nullable=True))
    op.add_column('father_mutual_fund_holdings', sa.Column('beta', sa.Numeric(precision=8, scale=4), nullable=True))
    op.add_column('father_mutual_fund_holdings', sa.Column('aum', sa.Numeric(precision=18, scale=2), nullable=True))
    op.add_column('father_mutual_fund_holdings', sa.Column('expense_ratio', sa.Numeric(precision=6, scale=4), nullable=True))
    op.add_column('father_mutual_fund_holdings', sa.Column('fund_rating', sa.Integer(), nullable=True))
    op.add_column('father_mutual_fund_holdings', sa.Column('fund_start_date', sa.Date(), nullable=True))
    op.add_column('father_mutual_fund_holdings', sa.Column('crisil_rating', sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column('father_mutual_fund_holdings', 'crisil_rating')
    op.drop_column('father_mutual_fund_holdings', 'fund_start_date')
    op.drop_column('father_mutual_fund_holdings', 'fund_rating')
    op.drop_column('father_mutual_fund_holdings', 'expense_ratio')
    op.drop_column('father_mutual_fund_holdings', 'aum')
    op.drop_column('father_mutual_fund_holdings', 'beta')
    op.drop_column('father_mutual_fund_holdings', 'alpha')
    op.drop_column('father_mutual_fund_holdings', 'sharpe_ratio')
    op.drop_column('father_mutual_fund_holdings', 'volatility')
    op.drop_column('father_mutual_fund_holdings', 'return_10y')
    op.drop_column('father_mutual_fund_holdings', 'isin')
    op.drop_column('father_mutual_fund_holdings', 'scheme_code')

