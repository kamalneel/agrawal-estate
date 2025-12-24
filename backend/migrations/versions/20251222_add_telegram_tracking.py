"""Add recommendation feedback and telegram tracking tables

Revision ID: 20251222_feedback_and_telegram
Revises: 
Create Date: 2025-12-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251222_feedback_and_telegram'
down_revision = '20251216_father_stocks'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create recommendation_feedback table (for V4 learning)
    op.create_table(
        'recommendation_feedback',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('recommendation_id', sa.String(100), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('raw_feedback', sa.Text(), nullable=False),
        sa.Column('reason_code', sa.String(50), nullable=True),
        sa.Column('reason_detail', sa.Text(), nullable=True),
        sa.Column('threshold_hint', sa.Numeric(10, 2), nullable=True),
        sa.Column('symbol_specific', sa.Boolean(), nullable=True),
        sa.Column('sentiment', sa.String(20), nullable=True),
        sa.Column('actionable_insight', sa.Text(), nullable=True),
        sa.Column('recommendation_type', sa.String(50), nullable=True),
        sa.Column('symbol', sa.String(20), nullable=True),
        sa.Column('account_name', sa.String(200), nullable=True),
        sa.Column('context_snapshot', sa.JSON(), nullable=True),
        sa.Column('parsing_status', sa.String(20), default='pending'),
        sa.Column('parsing_error', sa.Text(), nullable=True),
        sa.Column('parsed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for recommendation_feedback
    op.create_index('idx_feedback_recommendation_id', 'recommendation_feedback', ['recommendation_id'])
    op.create_index('idx_feedback_reason_code', 'recommendation_feedback', ['reason_code'])
    op.create_index('idx_feedback_symbol', 'recommendation_feedback', ['symbol'])
    op.create_index('idx_feedback_created_at', 'recommendation_feedback', ['created_at'])
    
    # Create telegram_message_tracking table
    op.create_table(
        'telegram_message_tracking',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('telegram_message_id', sa.Integer(), nullable=False),
        sa.Column('telegram_chat_id', sa.String(50), nullable=False),
        sa.Column('recommendation_ids', sa.JSON(), nullable=False),
        sa.Column('message_text', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.Column('reply_received', sa.Boolean(), default=False),
        sa.Column('reply_text', sa.Text(), nullable=True),
        sa.Column('reply_received_at', sa.DateTime(), nullable=True),
        sa.Column('feedback_processed', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for telegram_message_tracking
    op.create_index(
        'idx_telegram_message_id',
        'telegram_message_tracking',
        ['telegram_message_id', 'telegram_chat_id']
    )
    op.create_index(
        'idx_telegram_sent_at',
        'telegram_message_tracking',
        ['sent_at']
    )


def downgrade() -> None:
    # Drop telegram_message_tracking
    op.drop_index('idx_telegram_sent_at', table_name='telegram_message_tracking')
    op.drop_index('idx_telegram_message_id', table_name='telegram_message_tracking')
    op.drop_table('telegram_message_tracking')
    
    # Drop recommendation_feedback
    op.drop_index('idx_feedback_created_at', table_name='recommendation_feedback')
    op.drop_index('idx_feedback_symbol', table_name='recommendation_feedback')
    op.drop_index('idx_feedback_reason_code', table_name='recommendation_feedback')
    op.drop_index('idx_feedback_recommendation_id', table_name='recommendation_feedback')
    op.drop_table('recommendation_feedback')

