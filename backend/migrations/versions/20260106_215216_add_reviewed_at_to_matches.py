"""add_reviewed_at_to_matches

Revision ID: 1719bac7b2e7
Revises: 20260106_uncovered
Create Date: 2026-01-06 21:52:16.884295

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1719bac7b2e7'
down_revision: Union[str, None] = '20260106_uncovered'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add reviewed_at column to track when user reviewed/acknowledged a match
    op.add_column(
        'recommendation_execution_matches',
        sa.Column('reviewed_at', sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('recommendation_execution_matches', 'reviewed_at')

