"""Enhance strategy_recommendations table for full history tracking.

Revision ID: 20251210_enhance_rec_history
Revises: 20251210_add_ta_strategies
Create Date: 2025-12-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text

# revision identifiers, used by Alembic.
revision = '20251210_enhance_rec_history'
down_revision = 'add_ta_strategies'
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect
    from sqlalchemy.sql import text
    
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Get existing columns
    try:
        existing_columns = [col['name'] for col in inspector.get_columns('strategy_recommendations')]
    except Exception:
        existing_columns = []
    
    # Add new columns to strategy_recommendations table (only if they don't exist)
    if 'description' not in existing_columns:
        op.add_column('strategy_recommendations', 
                      sa.Column('description', sa.Text(), nullable=True))
    if 'rationale' not in existing_columns:
        op.add_column('strategy_recommendations', 
                      sa.Column('rationale', sa.Text(), nullable=True))
    if 'action_type' not in existing_columns:
        op.add_column('strategy_recommendations', 
                      sa.Column('action_type', sa.String(length=50), nullable=True))
    if 'potential_risk' not in existing_columns:
        op.add_column('strategy_recommendations', 
                      sa.Column('potential_risk', sa.String(length=50), nullable=True))
    if 'symbol' not in existing_columns:
        op.add_column('strategy_recommendations', 
                      sa.Column('symbol', sa.String(length=20), nullable=True))
    if 'account_name' not in existing_columns:
        op.add_column('strategy_recommendations', 
                      sa.Column('account_name', sa.String(length=200), nullable=True))
    if 'dismissed_at' not in existing_columns:
        op.add_column('strategy_recommendations', 
                      sa.Column('dismissed_at', sa.DateTime(), nullable=True))
    if 'notification_sent' not in existing_columns:
        op.add_column('strategy_recommendations', 
                      sa.Column('notification_sent', sa.Boolean(), nullable=True, server_default='false'))
    if 'notification_sent_at' not in existing_columns:
        op.add_column('strategy_recommendations', 
                      sa.Column('notification_sent_at', sa.DateTime(), nullable=True))
    
    # Update default status from 'pending' to 'new'
    try:
        conn.execute(text("UPDATE strategy_recommendations SET status = 'new' WHERE status = 'pending'"))
    except Exception:
        pass  # Ignore if update fails
    
    # Add index for symbol lookup (only if it doesn't exist)
    try:
        existing_indexes = [idx['name'] for idx in inspector.get_indexes('strategy_recommendations')]
        if 'idx_rec_symbol' not in existing_indexes:
            op.create_index('idx_rec_symbol', 'strategy_recommendations', ['symbol'])
    except Exception:
        # Try to create index anyway, will fail gracefully if it exists
        try:
            op.create_index('idx_rec_symbol', 'strategy_recommendations', ['symbol'])
        except Exception:
            pass  # Index might already exist


def downgrade() -> None:
    op.drop_index('idx_rec_symbol', table_name='strategy_recommendations')
    op.drop_column('strategy_recommendations', 'notification_sent_at')
    op.drop_column('strategy_recommendations', 'notification_sent')
    op.drop_column('strategy_recommendations', 'dismissed_at')
    op.drop_column('strategy_recommendations', 'account_name')
    op.drop_column('strategy_recommendations', 'symbol')
    op.drop_column('strategy_recommendations', 'potential_risk')
    op.drop_column('strategy_recommendations', 'action_type')
    op.drop_column('strategy_recommendations', 'rationale')
    op.drop_column('strategy_recommendations', 'description')
    op.execute("UPDATE strategy_recommendations SET status = 'pending' WHERE status = 'new'")

