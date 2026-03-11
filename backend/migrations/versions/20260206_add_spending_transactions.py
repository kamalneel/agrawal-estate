"""Add spending_transactions table for Monarch Money imports

Revision ID: 20260206_spending_transactions
Revises: 20260207_bbd_performance_metrics
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260206_spending_transactions'
down_revision = '20260207_bbd_performance_metrics'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'spending_transactions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),

        sa.Column('transaction_date', sa.Date(), nullable=False),
        sa.Column('merchant', sa.String(255), nullable=True),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('account', sa.String(255), nullable=True),
        sa.Column('original_statement', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('amount', sa.Numeric(18, 2), nullable=False),
        sa.Column('tags', sa.String(500), nullable=True),
        sa.Column('owner', sa.String(50), nullable=True),

        # Deduplication
        sa.Column('record_hash', sa.String(64), nullable=False, unique=True),

        # Provenance
        sa.Column('ingestion_id', sa.Integer(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Indexes
    op.create_index('idx_spending_date', 'spending_transactions', ['transaction_date'])
    op.create_index('idx_spending_category', 'spending_transactions', ['category'])
    op.create_index('idx_spending_merchant', 'spending_transactions', ['merchant'])
    op.create_index('idx_spending_account', 'spending_transactions', ['account'])
    op.create_index('idx_spending_owner', 'spending_transactions', ['owner'])
    op.create_index('idx_spending_date_category', 'spending_transactions', ['transaction_date', 'category'])
    op.create_index('idx_spending_record_hash', 'spending_transactions', ['record_hash'], unique=True)


def downgrade():
    op.drop_index('idx_spending_record_hash', table_name='spending_transactions')
    op.drop_index('idx_spending_date_category', table_name='spending_transactions')
    op.drop_index('idx_spending_owner', table_name='spending_transactions')
    op.drop_index('idx_spending_account', table_name='spending_transactions')
    op.drop_index('idx_spending_merchant', table_name='spending_transactions')
    op.drop_index('idx_spending_category', table_name='spending_transactions')
    op.drop_index('idx_spending_date', table_name='spending_transactions')
    op.drop_table('spending_transactions')
