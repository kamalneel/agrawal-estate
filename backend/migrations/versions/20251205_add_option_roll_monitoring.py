"""Add option roll monitoring tables.

Revision ID: 20251205_roll_monitor
Revises: sold_options_001
Create Date: 2025-12-05

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251205_roll_monitor'
down_revision = 'sold_options_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add original_premium column to sold_options if it doesn't exist
    try:
        op.add_column('sold_options', 
            sa.Column('original_premium', sa.Numeric(10, 2), nullable=True)
        )
    except Exception:
        pass  # Column might already exist
    
    # Create option_roll_alerts table
    op.create_table(
        'option_roll_alerts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('sold_option_id', sa.Integer(), sa.ForeignKey('sold_options.id', ondelete='CASCADE'), nullable=True),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('strike_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('option_type', sa.String(10), nullable=False),
        sa.Column('expiration_date', sa.Date(), nullable=True),
        sa.Column('contracts', sa.Integer(), nullable=False, default=1),
        sa.Column('original_premium', sa.Numeric(10, 2), nullable=False),
        sa.Column('current_premium', sa.Numeric(10, 2), nullable=False),
        sa.Column('profit_percent', sa.Numeric(10, 2), nullable=False),
        sa.Column('alert_type', sa.String(50), nullable=False),
        sa.Column('alert_triggered_at', sa.DateTime(), nullable=False),
        sa.Column('alert_acknowledged', sa.String(1), default='N'),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.Column('action_taken', sa.String(50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    
    # Add indexes
    op.create_index('idx_roll_alerts_symbol', 'option_roll_alerts', ['symbol'])
    op.create_index('idx_roll_alerts_triggered', 'option_roll_alerts', ['alert_triggered_at'])
    op.create_index('idx_roll_alerts_acknowledged', 'option_roll_alerts', ['alert_acknowledged'])


def downgrade() -> None:
    op.drop_index('idx_roll_alerts_acknowledged', 'option_roll_alerts')
    op.drop_index('idx_roll_alerts_triggered', 'option_roll_alerts')
    op.drop_index('idx_roll_alerts_symbol', 'option_roll_alerts')
    op.drop_table('option_roll_alerts')
    
    try:
        op.drop_column('sold_options', 'original_premium')
    except Exception:
        pass

