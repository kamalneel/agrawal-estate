"""Add account cash balances for put selling calculations

Revision ID: add_account_cash_balances
Revises: add_rlhf_data_exclusion
Create Date: 2026-01-13

Stores cash balances per account for calculating cash-secured put income.
This is separate from stock holdings - represents cash available for put selling.
"""
from alembic import op
import sqlalchemy as sa
from decimal import Decimal


# revision identifiers, used by Alembic.
revision = 'add_account_cash_balances'
down_revision = 'add_rlhf_data_exclusion'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create account cash balances table."""
    op.create_table(
        'account_cash_balances',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('account_name', sa.String(200), nullable=False),
        sa.Column('cash_balance', sa.Numeric(12, 2), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )

    # Create unique index on account_name
    op.create_index('idx_cash_balance_account', 'account_cash_balances', ['account_name'], unique=True)

    # Insert initial data
    op.execute("""
        INSERT INTO account_cash_balances (account_name, cash_balance, notes)
        VALUES
            ('Neel''s Brokerage', 100000.00, 'Initial balance for put selling'),
            ('Jaya''s Brokerage', 120000.00, 'Initial balance for put selling')
    """)


def downgrade() -> None:
    """Drop account cash balances table."""
    op.drop_index('idx_cash_balance_account', table_name='account_cash_balances')
    op.drop_table('account_cash_balances')
