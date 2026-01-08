"""drop_v1_fk_constraint_for_v2_migration

Revision ID: 78ecf02e63f2
Revises: 1719bac7b2e7
Create Date: 2026-01-06 22:13:26.199905

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78ecf02e63f2'
down_revision: Union[str, None] = '1719bac7b2e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the foreign key constraint that links to V1 strategy_recommendations table
    # This is needed because we're now storing V2 snapshot IDs instead
    op.drop_constraint(
        'recommendation_execution_matches_recommendation_record_id_fkey',
        'recommendation_execution_matches',
        type_='foreignkey'
    )
    
    # Add a new column for V2 snapshot reference (optional, for clarity)
    op.add_column(
        'recommendation_execution_matches',
        sa.Column('v2_snapshot_id', sa.Integer(), nullable=True)
    )
    
    # Add comment to indicate this is now for V2
    # (recommendation_record_id now stores V2 snapshot IDs after cleanup)


def downgrade() -> None:
    # Drop the v2_snapshot_id column
    op.drop_column('recommendation_execution_matches', 'v2_snapshot_id')
    
    # Re-add the foreign key constraint
    op.create_foreign_key(
        'recommendation_execution_matches_recommendation_record_id_fkey',
        'recommendation_execution_matches',
        'strategy_recommendations',
        ['recommendation_record_id'],
        ['id']
    )

