"""Add recommendation notification tracking table.

Revision ID: 20251209_notif_tracking
Revises: 20251209_strat_configs
Create Date: 2025-12-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251209_notif_tracking'
down_revision = '20251209_strat_configs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create recommendation_notifications table
    op.create_table(
        'recommendation_notifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('recommendation_id', sa.String(length=100), nullable=False),
        sa.Column('notification_type', sa.String(length=50), nullable=False),
        sa.Column('priority', sa.String(length=20), nullable=False),
        sa.Column('previous_priority', sa.String(length=20), nullable=True),
        sa.Column('channels_sent', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.Column('next_notification_allowed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add indexes
    op.create_index('idx_rec_notif_rec_id', 'recommendation_notifications', ['recommendation_id'])
    op.create_index('idx_rec_notif_sent_at', 'recommendation_notifications', ['sent_at'])
    op.create_index('idx_rec_notif_next_allowed', 'recommendation_notifications', ['next_notification_allowed_at'])


def downgrade() -> None:
    op.drop_index('idx_rec_notif_next_allowed', table_name='recommendation_notifications')
    op.drop_index('idx_rec_notif_sent_at', table_name='recommendation_notifications')
    op.drop_index('idx_rec_notif_rec_id', table_name='recommendation_notifications')
    op.drop_table('recommendation_notifications')



