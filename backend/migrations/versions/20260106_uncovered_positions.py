"""Add support for uncovered positions in V2 recommendations

This migration:
1. Makes source_strike and source_expiration nullable (for uncovered positions)
2. Adds position_type column to distinguish sold_option vs uncovered

Revision ID: 20260106_uncovered
Revises: 20260106_notification_mode
Create Date: 2026-01-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260106_uncovered'
down_revision = '20260106_notification_mode'
branch_labels = None
depends_on = None


def upgrade():
    # Make source_strike nullable
    op.alter_column(
        'position_recommendations',
        'source_strike',
        existing_type=sa.Numeric(10, 2),
        nullable=True
    )
    
    # Make source_expiration nullable
    op.alter_column(
        'position_recommendations',
        'source_expiration',
        existing_type=sa.Date(),
        nullable=True
    )
    
    # Add position_type column
    op.add_column(
        'position_recommendations',
        sa.Column('position_type', sa.String(20), nullable=True, server_default='sold_option')
    )
    
    # Update existing records to have position_type = 'sold_option'
    op.execute("""
        UPDATE position_recommendations 
        SET position_type = 'sold_option' 
        WHERE position_type IS NULL
    """)


def downgrade():
    # Remove position_type column
    op.drop_column('position_recommendations', 'position_type')
    
    # Make source_expiration non-nullable (only works if no NULL values)
    op.alter_column(
        'position_recommendations',
        'source_expiration',
        existing_type=sa.Date(),
        nullable=False
    )
    
    # Make source_strike non-nullable (only works if no NULL values)
    op.alter_column(
        'position_recommendations',
        'source_strike',
        existing_type=sa.Numeric(10, 2),
        nullable=False
    )


