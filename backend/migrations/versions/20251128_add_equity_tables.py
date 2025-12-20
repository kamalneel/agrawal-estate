"""Add equity tables for startup holdings

Revision ID: e8f7a6b5c4d3
Revises: 20251127_add_income_tax_returns
Create Date: 2025-11-28 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8f7a6b5c4d3'
down_revision: Union[str, None] = '7c06dfb788ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create equity_companies table
    op.create_table('equity_companies',
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('dba_name', sa.String(length=200), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True, default='active'),
        sa.Column('founded_date', sa.Date(), nullable=True),
        sa.Column('current_fmv', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('fmv_date', sa.Date(), nullable=True),
        sa.Column('last_409a_date', sa.Date(), nullable=True),
        sa.Column('qsbs_eligible', sa.String(length=1), nullable=True, default='N'),
        sa.Column('qsbs_notes', sa.Text(), nullable=True),
        sa.Column('industry', sa.String(length=100), nullable=True),
        sa.Column('website', sa.String(length=200), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('logo_url', sa.String(length=500), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create equity_grants table (stock options)
    op.create_table('equity_grants',
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('grant_id', sa.String(length=50), nullable=True),
        sa.Column('grant_type', sa.String(length=20), nullable=False),
        sa.Column('grant_date', sa.Date(), nullable=True),
        sa.Column('total_options', sa.Integer(), nullable=False),
        sa.Column('exercise_price', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('vested_options', sa.Integer(), nullable=True, default=0),
        sa.Column('exercised_options', sa.Integer(), nullable=True, default=0),
        sa.Column('status', sa.String(length=50), nullable=True, default='active'),
        sa.Column('expiration_date', sa.Date(), nullable=True),
        sa.Column('termination_date', sa.Date(), nullable=True),
        sa.Column('vesting_start_date', sa.Date(), nullable=True),
        sa.Column('vesting_cliff_months', sa.Integer(), nullable=True),
        sa.Column('vesting_total_months', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['equity_companies.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_equity_grants_company', 'equity_grants', ['company_id'], unique=False)
    
    # Create equity_shares table
    op.create_table('equity_shares',
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('certificate_id', sa.String(length=50), nullable=True),
        sa.Column('share_type', sa.String(length=50), nullable=False),
        sa.Column('acquisition_date', sa.Date(), nullable=True),
        sa.Column('num_shares', sa.Integer(), nullable=False),
        sa.Column('cost_basis_per_share', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=True),
        sa.Column('source_grant_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True, default='held'),
        sa.Column('sold_date', sa.Date(), nullable=True),
        sa.Column('sold_price_per_share', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['equity_companies.id']),
        sa.ForeignKeyConstraint(['source_grant_id'], ['equity_grants.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_equity_shares_company', 'equity_shares', ['company_id'], unique=False)
    
    # Create equity_rsas table (Restricted Stock Awards)
    op.create_table('equity_rsas',
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('rsa_id', sa.String(length=50), nullable=True),
        sa.Column('grant_date', sa.Date(), nullable=True),
        sa.Column('total_shares', sa.Integer(), nullable=False),
        sa.Column('purchase_price', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('vested_shares', sa.Integer(), nullable=True, default=0),
        sa.Column('status', sa.String(length=50), nullable=True, default='active'),
        sa.Column('election_83b_filed', sa.String(length=1), nullable=True, default='N'),
        sa.Column('election_83b_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['equity_companies.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_equity_rsas_company', 'equity_rsas', ['company_id'], unique=False)
    
    # Create equity_safes table
    op.create_table('equity_safes',
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('safe_id', sa.String(length=50), nullable=True),
        sa.Column('investment_date', sa.Date(), nullable=True),
        sa.Column('principal_amount', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('valuation_cap', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('discount_rate', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('safe_type', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True, default='outstanding'),
        sa.Column('converted_date', sa.Date(), nullable=True),
        sa.Column('converted_shares', sa.Integer(), nullable=True),
        sa.Column('conversion_price', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['equity_companies.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_equity_safes_company', 'equity_safes', ['company_id'], unique=False)
    
    # Create equity_exercises table
    op.create_table('equity_exercises',
        sa.Column('grant_id', sa.Integer(), nullable=False),
        sa.Column('exercise_date', sa.Date(), nullable=False),
        sa.Column('num_shares', sa.Integer(), nullable=False),
        sa.Column('exercise_price', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('fmv_at_exercise', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('shares_id', sa.Integer(), nullable=True),
        sa.Column('bargain_element', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('form_3921_box1_date_granted', sa.Date(), nullable=True),
        sa.Column('form_3921_box2_date_exercised', sa.Date(), nullable=True),
        sa.Column('form_3921_box3_exercise_price', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('form_3921_box4_fmv_exercise', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('form_3921_box5_shares_transferred', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['grant_id'], ['equity_grants.id']),
        sa.ForeignKeyConstraint(['shares_id'], ['equity_shares.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_equity_exercises_grant', 'equity_exercises', ['grant_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_equity_exercises_grant', table_name='equity_exercises')
    op.drop_table('equity_exercises')
    op.drop_index('idx_equity_safes_company', table_name='equity_safes')
    op.drop_table('equity_safes')
    op.drop_index('idx_equity_rsas_company', table_name='equity_rsas')
    op.drop_table('equity_rsas')
    op.drop_index('idx_equity_shares_company', table_name='equity_shares')
    op.drop_table('equity_shares')
    op.drop_index('idx_equity_grants_company', table_name='equity_grants')
    op.drop_table('equity_grants')
    op.drop_table('equity_companies')

