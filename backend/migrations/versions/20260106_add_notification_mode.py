"""Add notification_mode columns for verbose vs smart notifications

Revision ID: 20260106_notification_mode
Revises: 20260105_add_recommendation_snapshots
Create Date: 2026-01-06

This migration adds notification_mode tracking to support dual notification modes:
- verbose: Every snapshot triggers a notification
- smart: Only snapshots with changes trigger notifications

Both modes can send to Telegram simultaneously, while UI can filter by mode.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260106_notification_mode'
down_revision = '20260105_rec_snapshots'
branch_labels = None
depends_on = None


def upgrade():
    # Add notification_mode to strategy_recommendations (V1)
    op.add_column(
        'strategy_recommendations',
        sa.Column('notification_mode', sa.String(20), nullable=True)
    )
    op.create_index(
        'idx_rec_notification_mode',
        'strategy_recommendations',
        ['notification_mode']
    )
    
    # Add notification_mode to recommendation_notifications
    op.add_column(
        'recommendation_notifications',
        sa.Column('notification_mode', sa.String(20), nullable=True, server_default='smart')
    )
    
    # Add verbose/smart tracking columns to recommendation_snapshots (V2)
    op.add_column(
        'recommendation_snapshots',
        sa.Column('notification_mode', sa.String(20), nullable=True)
    )
    op.add_column(
        'recommendation_snapshots',
        sa.Column('verbose_notification_sent', sa.Boolean(), nullable=True, server_default='false')
    )
    op.add_column(
        'recommendation_snapshots',
        sa.Column('verbose_notification_at', sa.DateTime(), nullable=True)
    )
    op.add_column(
        'recommendation_snapshots',
        sa.Column('smart_notification_sent', sa.Boolean(), nullable=True, server_default='false')
    )
    op.add_column(
        'recommendation_snapshots',
        sa.Column('smart_notification_at', sa.DateTime(), nullable=True)
    )
    
    # Create index for filtering by mode
    op.create_index(
        'idx_snap_notification_mode',
        'recommendation_snapshots',
        ['notification_mode']
    )
    
    # Update existing records: mark all existing notifications as 'smart' mode
    # (they were created before verbose mode existed)
    op.execute("""
        UPDATE strategy_recommendations 
        SET notification_mode = 'smart' 
        WHERE notification_sent = true AND notification_mode IS NULL
    """)
    
    op.execute("""
        UPDATE recommendation_notifications 
        SET notification_mode = 'smart' 
        WHERE notification_mode IS NULL
    """)


def downgrade():
    # Remove from recommendation_snapshots
    op.drop_index('idx_snap_notification_mode', table_name='recommendation_snapshots')
    op.drop_column('recommendation_snapshots', 'smart_notification_at')
    op.drop_column('recommendation_snapshots', 'smart_notification_sent')
    op.drop_column('recommendation_snapshots', 'verbose_notification_at')
    op.drop_column('recommendation_snapshots', 'verbose_notification_sent')
    op.drop_column('recommendation_snapshots', 'notification_mode')
    
    # Remove from recommendation_notifications
    op.drop_column('recommendation_notifications', 'notification_mode')
    
    # Remove from strategy_recommendations
    op.drop_index('idx_rec_notification_mode', table_name='strategy_recommendations')
    op.drop_column('strategy_recommendations', 'notification_mode')

