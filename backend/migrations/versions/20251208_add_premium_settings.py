"""Add option premium settings table.

Revision ID: 20251208_premium_settings
Revises: 20251205_roll_monitor
Create Date: 2025-12-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251208_premium_settings'
down_revision = '20251205_roll_monitor'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create option_premium_settings table
    op.create_table(
        'option_premium_settings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('premium_per_contract', sa.Numeric(10, 2), nullable=False),
        sa.Column('is_auto_updated', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('last_auto_update', sa.DateTime(), nullable=True),
        sa.Column('manual_override', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol', name='uq_option_premium_symbol')
    )
    
    # Add index on symbol for faster lookups
    op.create_index('idx_premium_settings_symbol', 'option_premium_settings', ['symbol'])


def downgrade() -> None:
    op.drop_index('idx_premium_settings_symbol', table_name='option_premium_settings')
    op.drop_table('option_premium_settings')



