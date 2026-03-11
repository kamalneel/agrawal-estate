"""Add housekeeping_per_week to airbnb_points_blocks

Revision ID: 20260207_block_housekeeping
Revises: 20260207_airbnb_tables
Create Date: 2026-02-07

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260207_block_housekeeping'
down_revision = '20260207_airbnb_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'airbnb_points_blocks',
        sa.Column('housekeeping_per_week', sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('airbnb_points_blocks', 'housekeeping_per_week')
