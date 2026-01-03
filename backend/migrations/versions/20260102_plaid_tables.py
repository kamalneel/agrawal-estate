"""Add Plaid tables for investment tracking

Revision ID: 20260102_plaid
Revises: 20250102_rlhf_learning
Create Date: 2026-01-02 16:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260102_plaid'
down_revision: Union[str, None] = '20250102_rlhf_learning'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create plaid_items table
    op.create_table(
        'plaid_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.String(255), nullable=False),
        sa.Column('access_token', sa.Text(), nullable=False),
        sa.Column('institution_id', sa.String(100), nullable=True),
        sa.Column('institution_name', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('error_code', sa.String(100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('consent_expiration_time', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_plaid_items_id', 'plaid_items', ['id'])
    op.create_index('ix_plaid_items_item_id', 'plaid_items', ['item_id'], unique=True)
    
    # Create plaid_accounts table
    op.create_table(
        'plaid_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('official_name', sa.String(255), nullable=True),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('subtype', sa.String(50), nullable=True),
        sa.Column('mask', sa.String(10), nullable=True),
        sa.Column('current_balance', sa.String(50), nullable=True),
        sa.Column('available_balance', sa.String(50), nullable=True),
        sa.Column('iso_currency_code', sa.String(10), default='USD'),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('is_hidden', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['item_id'], ['plaid_items.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_plaid_accounts_id', 'plaid_accounts', ['id'])
    op.create_index('ix_plaid_accounts_account_id', 'plaid_accounts', ['account_id'], unique=True)
    
    # Create plaid_investment_transactions table
    op.create_table(
        'plaid_investment_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.String(255), nullable=False),
        sa.Column('investment_transaction_id', sa.String(255), nullable=False),
        sa.Column('date', sa.DateTime(), nullable=False),
        sa.Column('name', sa.String(500), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('subtype', sa.String(50), nullable=True),
        sa.Column('security_id', sa.String(255), nullable=True),
        sa.Column('ticker_symbol', sa.String(20), nullable=True),
        sa.Column('security_name', sa.String(255), nullable=True),
        sa.Column('security_type', sa.String(50), nullable=True),
        sa.Column('option_type', sa.String(10), nullable=True),
        sa.Column('strike_price', sa.String(50), nullable=True),
        sa.Column('expiration_date', sa.DateTime(), nullable=True),
        sa.Column('underlying_symbol', sa.String(20), nullable=True),
        sa.Column('quantity', sa.String(50), nullable=True),
        sa.Column('price', sa.String(50), nullable=True),
        sa.Column('amount', sa.String(50), nullable=True),
        sa.Column('fees', sa.String(50), nullable=True),
        sa.Column('iso_currency_code', sa.String(10), default='USD'),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_plaid_inv_txn_id', 'plaid_investment_transactions', ['id'])
    op.create_index('ix_plaid_inv_txn_account', 'plaid_investment_transactions', ['account_id'])
    op.create_index('ix_plaid_inv_txn_inv_id', 'plaid_investment_transactions', ['investment_transaction_id'], unique=True)
    op.create_index('ix_plaid_inv_txn_date', 'plaid_investment_transactions', ['date'])
    op.create_index('ix_plaid_inv_txn_ticker', 'plaid_investment_transactions', ['ticker_symbol'])
    
    # Create plaid_holdings table
    op.create_table(
        'plaid_holdings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.String(255), nullable=False),
        sa.Column('security_id', sa.String(255), nullable=True),
        sa.Column('ticker_symbol', sa.String(20), nullable=True),
        sa.Column('security_name', sa.String(255), nullable=True),
        sa.Column('security_type', sa.String(50), nullable=True),
        sa.Column('option_type', sa.String(10), nullable=True),
        sa.Column('strike_price', sa.String(50), nullable=True),
        sa.Column('expiration_date', sa.DateTime(), nullable=True),
        sa.Column('underlying_symbol', sa.String(20), nullable=True),
        sa.Column('quantity', sa.String(50), nullable=False),
        sa.Column('cost_basis', sa.String(50), nullable=True),
        sa.Column('institution_price', sa.String(50), nullable=True),
        sa.Column('institution_value', sa.String(50), nullable=True),
        sa.Column('institution_price_as_of', sa.DateTime(), nullable=True),
        sa.Column('iso_currency_code', sa.String(10), default='USD'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_plaid_holdings_id', 'plaid_holdings', ['id'])
    op.create_index('ix_plaid_holdings_account', 'plaid_holdings', ['account_id'])
    op.create_index('ix_plaid_holdings_ticker', 'plaid_holdings', ['ticker_symbol'])


def downgrade() -> None:
    op.drop_table('plaid_holdings')
    op.drop_table('plaid_investment_transactions')
    op.drop_table('plaid_accounts')
    op.drop_table('plaid_items')

