"""Add Father's Mutual Fund Holdings table

Revision ID: add_father_mf_holdings
Revises: add_mf_alpha_rating
Create Date: 2025-12-15

Adds table for tracking Father's mutual fund holdings with:
- Investment date
- Fund name
- Folio number
- Initial invested amount
- Amount as of March 31, 2025
- Current amount
- 1-year, 3-year, 5-year performance
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision = 'add_father_mf_holdings'
down_revision = 'add_mf_alpha_rating'
branch_labels = None
depends_on = None


def upgrade():
    """Create Father's Mutual Fund Holdings table."""
    
    op.create_table(
        'father_mutual_fund_holdings',
        sa.Column('id', sa.Integer(), nullable=False),
        # Investment details
        sa.Column('investment_date', sa.Date(), nullable=False),
        sa.Column('fund_name', sa.String(length=300), nullable=False),
        sa.Column('folio_number', sa.String(length=50), nullable=True),
        # Amounts
        sa.Column('initial_invested_amount', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('amount_march_2025', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('current_amount', sa.Numeric(precision=18, scale=2), nullable=True),
        # Performance metrics (in percentage)
        sa.Column('return_1y', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('return_3y', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('return_5y', sa.Numeric(precision=8, scale=2), nullable=True),
        # Optional metadata
        sa.Column('fund_category', sa.String(length=100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        # Timestamps
        sa.Column('last_updated', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('idx_father_mf_fund_name', 'father_mutual_fund_holdings', ['fund_name'])
    op.create_index('idx_father_mf_investment_date', 'father_mutual_fund_holdings', ['investment_date'])


def downgrade():
    """Drop Father's Mutual Fund Holdings table."""
    op.drop_index('idx_father_mf_investment_date', table_name='father_mutual_fund_holdings')
    op.drop_index('idx_father_mf_fund_name', table_name='father_mutual_fund_holdings')
    op.drop_table('father_mutual_fund_holdings')


