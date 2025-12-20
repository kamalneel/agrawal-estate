"""Add India Investments module

Revision ID: add_india_investments
Revises: enhance_recommendations_history
Create Date: 2025-12-14

Adds tables for India investments:
- india_bank_accounts: Bank accounts (ICICI, SBI, PNB, etc.)
- india_investment_accounts: Investment accounts (Zerodha, etc.)
- india_stocks: Stocks held in investment accounts
- india_mutual_funds: Mutual funds held in investment accounts
- india_fixed_deposits: Fixed deposits in bank accounts
- exchange_rates: USD to INR exchange rate
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import text


# revision identifiers, used by Alembic
revision = 'add_india_investments'
down_revision = '20251210_enhance_rec_history'  # Latest migration
branch_labels = None
depends_on = None


def upgrade():
    """Create India investments tables."""
    
    # India Bank Accounts
    op.create_table(
        'india_bank_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_name', sa.String(length=200), nullable=False),
        sa.Column('bank_name', sa.String(length=100), nullable=False),
        sa.Column('account_number', sa.String(length=100), nullable=True),
        sa.Column('owner', sa.String(length=50), nullable=False),
        sa.Column('account_type', sa.String(length=50), nullable=True),
        sa.Column('cash_balance', sa.Numeric(precision=18, scale=2), nullable=True, server_default='0'),
        sa.Column('is_active', sa.String(length=1), nullable=True, server_default='Y'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bank_name', 'account_number', 'owner', name='uq_india_bank_account')
    )
    
    # India Investment Accounts
    op.create_table(
        'india_investment_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_name', sa.String(length=200), nullable=False),
        sa.Column('platform', sa.String(length=100), nullable=False),
        sa.Column('account_number', sa.String(length=100), nullable=True),
        sa.Column('owner', sa.String(length=50), nullable=False),
        sa.Column('linked_bank_account_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.String(length=1), nullable=True, server_default='Y'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['linked_bank_account_id'], ['india_bank_accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('platform', 'account_number', 'owner', name='uq_india_investment_account')
    )
    
    # India Stocks
    op.create_table(
        'india_stocks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('investment_account_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('company_name', sa.String(length=200), nullable=True),
        sa.Column('quantity', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('average_price', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('current_price', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('cost_basis', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('current_value', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('profit_loss', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['investment_account_id'], ['india_investment_accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('investment_account_id', 'symbol', name='uq_india_stock')
    )
    op.create_index('idx_india_stock_symbol', 'india_stocks', ['symbol'])
    
    # India Mutual Funds
    op.create_table(
        'india_mutual_funds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('investment_account_id', sa.Integer(), nullable=False),
        sa.Column('fund_name', sa.String(length=200), nullable=False),
        sa.Column('fund_code', sa.String(length=50), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('units', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('nav', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('purchase_price', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('cost_basis', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('current_value', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('profit_loss', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['investment_account_id'], ['india_investment_accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('investment_account_id', 'fund_name', 'fund_code', name='uq_india_mutual_fund')
    )
    op.create_index('idx_india_mf_category', 'india_mutual_funds', ['category'])
    
    # India Fixed Deposits
    op.create_table(
        'india_fixed_deposits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('fd_number', sa.String(length=100), nullable=True),
        sa.Column('description', sa.String(length=200), nullable=True),
        sa.Column('principal', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('interest_rate', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('maturity_date', sa.Date(), nullable=False),
        sa.Column('current_value', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('accrued_interest', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('maturity_value', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('is_active', sa.String(length=1), nullable=True, server_default='Y'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['bank_account_id'], ['india_bank_accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bank_account_id', 'fd_number', name='uq_india_fd')
    )
    op.create_index('idx_india_fd_maturity', 'india_fixed_deposits', ['maturity_date'])
    
    # Exchange Rates
    op.create_table(
        'exchange_rates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('from_currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('to_currency', sa.String(length=3), nullable=False, server_default='INR'),
        sa.Column('rate', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('updated_by', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('from_currency', 'to_currency', name='uq_exchange_rate')
    )
    
    # Insert default exchange rate
    conn = op.get_bind()
    conn.execute(text("""
        INSERT INTO exchange_rates (from_currency, to_currency, rate, updated_at)
        VALUES ('USD', 'INR', 83.0, NOW())
        ON CONFLICT (from_currency, to_currency) DO NOTHING
    """))
    conn.commit()


def downgrade():
    """Drop India investments tables."""
    op.drop_table('exchange_rates')
    op.drop_table('india_fixed_deposits')
    op.drop_table('india_mutual_funds')
    op.drop_table('india_stocks')
    op.drop_table('india_investment_accounts')
    op.drop_table('india_bank_accounts')

