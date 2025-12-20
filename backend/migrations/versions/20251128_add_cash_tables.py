"""Add cash tables for tracking bank and brokerage cash balances.

Revision ID: add_cash_tables
Revises: 20251128_add_equity_tables
Create Date: 2025-11-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_cash_tables'
down_revision: Union[str, None] = 'e8f7a6b5c4d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create cash_accounts table
    op.create_table(
        'cash_accounts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('account_id', sa.String(100), nullable=False),
        sa.Column('account_name', sa.String(200), nullable=True),
        sa.Column('account_type', sa.String(50), nullable=True),
        sa.Column('owner', sa.String(50), nullable=True),
        sa.Column('current_balance', sa.Numeric(18, 2), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.String(1), default='Y'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('source', 'account_id', name='uq_cash_account'),
    )
    op.create_index('idx_cash_account_owner', 'cash_accounts', ['owner'])
    
    # Create cash_snapshots table
    op.create_table(
        'cash_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('account_id', sa.String(100), nullable=False),
        sa.Column('owner', sa.String(50), nullable=True),
        sa.Column('account_type', sa.String(50), nullable=True),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('balance', sa.Numeric(18, 2), nullable=False),
        sa.Column('statement_period_start', sa.Date(), nullable=True),
        sa.Column('statement_period_end', sa.Date(), nullable=True),
        sa.Column('ingestion_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('source', 'account_id', 'snapshot_date', name='uq_cash_snapshot'),
    )
    op.create_index('idx_cash_snapshot_date', 'cash_snapshots', ['snapshot_date'])
    op.create_index('idx_cash_snapshot_owner', 'cash_snapshots', ['owner'])
    
    # Create cash_transactions table
    op.create_table(
        'cash_transactions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('account_id', sa.String(100), nullable=False),
        sa.Column('transaction_date', sa.Date(), nullable=False),
        sa.Column('transaction_type', sa.String(50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('amount', sa.Numeric(18, 2), nullable=False),
        sa.Column('running_balance', sa.Numeric(18, 2), nullable=True),
        sa.Column('record_hash', sa.String(64), nullable=True),
        sa.Column('ingestion_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('idx_cash_transaction_date', 'cash_transactions', ['transaction_date'])
    op.create_index('idx_cash_transaction_account', 'cash_transactions', ['source', 'account_id'])
    op.create_index('idx_cash_transaction_hash', 'cash_transactions', ['record_hash'])


def downgrade() -> None:
    op.drop_index('idx_cash_transaction_hash', table_name='cash_transactions')
    op.drop_index('idx_cash_transaction_account', table_name='cash_transactions')
    op.drop_index('idx_cash_transaction_date', table_name='cash_transactions')
    op.drop_table('cash_transactions')
    
    op.drop_index('idx_cash_snapshot_owner', table_name='cash_snapshots')
    op.drop_index('idx_cash_snapshot_date', table_name='cash_snapshots')
    op.drop_table('cash_snapshots')
    
    op.drop_index('idx_cash_account_owner', table_name='cash_accounts')
    op.drop_table('cash_accounts')

