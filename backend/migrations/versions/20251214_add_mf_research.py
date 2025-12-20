"""Add Mutual Fund Research module

Revision ID: add_mf_research
Revises: add_india_investments
Create Date: 2025-12-14

Adds tables for mutual fund research and comparison:
- mutual_fund_research: Fund details, metrics, recommendation scores
- mutual_fund_nav_history: Historical NAV data
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic
revision = 'add_mf_research'
down_revision = 'add_india_investments'
branch_labels = None
depends_on = None


def upgrade():
    """Create mutual fund research tables."""
    
    # Mutual Fund Research
    op.create_table(
        'mutual_fund_research',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scheme_code', sa.String(length=20), nullable=False),
        sa.Column('scheme_name', sa.String(length=500), nullable=False),
        sa.Column('fund_house', sa.String(length=200), nullable=True),
        sa.Column('scheme_type', sa.String(length=100), nullable=True),
        sa.Column('scheme_category', sa.String(length=200), nullable=True),
        sa.Column('fund_category', sa.String(length=100), nullable=True),
        sa.Column('isin_growth', sa.String(length=50), nullable=True),
        sa.Column('isin_div_reinvestment', sa.String(length=50), nullable=True),
        sa.Column('current_nav', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('nav_date', sa.Date(), nullable=True),
        sa.Column('return_1y', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('return_3y', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('return_5y', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('return_10y', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('volatility', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('sharpe_ratio', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('beta', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('aum', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('expense_ratio', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('exit_load', sa.String(length=100), nullable=True),
        sa.Column('recommendation_score', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('recommendation_rank', sa.Integer(), nullable=True),
        sa.Column('recommendation_reason', sa.Text(), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.String(length=1), nullable=True, server_default='Y'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scheme_code', name='uq_mf_research_scheme_code')
    )
    op.create_index('idx_mf_research_category', 'mutual_fund_research', ['fund_category'])
    op.create_index('idx_mf_research_score', 'mutual_fund_research', ['recommendation_score'])
    op.create_index('idx_mf_research_rank', 'mutual_fund_research', ['recommendation_rank'])
    
    # Mutual Fund NAV History
    op.create_table(
        'mutual_fund_nav_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scheme_code', sa.String(length=20), nullable=False),
        sa.Column('nav_date', sa.Date(), nullable=False),
        sa.Column('nav', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=True, server_default='mfapi.in'),
        sa.Column('last_updated', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scheme_code', 'nav_date', name='uq_mf_nav_history')
    )
    op.create_index('idx_mf_nav_scheme_date', 'mutual_fund_nav_history', ['scheme_code', 'nav_date'])


def downgrade():
    """Drop mutual fund research tables."""
    op.drop_table('mutual_fund_nav_history')
    op.drop_table('mutual_fund_research')

