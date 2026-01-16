"""Add algorithm_version to recommendation_execution_matches

Revision ID: add_rlhf_algorithm_version
Revises: 20260110_add_cost_basis_tracking
Create Date: 2026-01-11

This migration adds an algorithm_version column to track which version
of the algorithm generated the recommendation. This enables "learning epochs"
where old data can be filtered out when algorithm version changes significantly.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_rlhf_algorithm_version'
down_revision = '52ebadecdfa6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add algorithm_version column to recommendation_execution_matches
    op.add_column(
        'recommendation_execution_matches',
        sa.Column('algorithm_version', sa.String(20), nullable=True)
    )
    
    # Add index for filtering by algorithm version
    op.create_index(
        'idx_rem_algorithm_version',
        'recommendation_execution_matches',
        ['algorithm_version']
    )


def downgrade() -> None:
    op.drop_index('idx_rem_algorithm_version', 'recommendation_execution_matches')
    op.drop_column('recommendation_execution_matches', 'algorithm_version')
