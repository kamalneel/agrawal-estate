"""Add RLHF data exclusion columns for data quality management

Revision ID: add_rlhf_data_exclusion
Revises: add_acquisition_watchlist
Create Date: 2026-01-13

Adds columns to track erroneous or invalid RLHF data without deleting it.
This is the standard approach for handling bad data in ML systems:
- Preserve audit trail
- Allow bulk exclusion
- Document why data was excluded
- Enable reversal if needed

Common exclusion reasons:
- 'algorithm_bug': Bug in recommendation algorithm (e.g., invalid strike calculation)
- 'data_source_error': Bad data from external source (Schwab API, etc.)
- 'parsing_error': Error in parsing user input or positions
- 'duplicate': Duplicate recommendation that shouldn't be counted
- 'test_data': Test data that got into production
- 'manual_review': Excluded after manual review
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_rlhf_data_exclusion'
down_revision = 'add_acquisition_watchlist'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add exclusion tracking columns to RLHF tables."""

    # Add to strategy_recommendations table (source of recommendations)
    op.add_column('strategy_recommendations',
        sa.Column('excluded_from_learning', sa.Boolean(), nullable=False, server_default='false')
    )
    op.add_column('strategy_recommendations',
        sa.Column('exclusion_reason', sa.String(50), nullable=True)
    )
    op.add_column('strategy_recommendations',
        sa.Column('exclusion_notes', sa.Text(), nullable=True)
    )
    op.add_column('strategy_recommendations',
        sa.Column('excluded_at', sa.DateTime(), nullable=True)
    )

    # Add index for querying excluded records
    op.create_index('idx_rec_excluded', 'strategy_recommendations', ['excluded_from_learning'])

    # Add to recommendation_execution_matches table (RLHF learning data)
    op.add_column('recommendation_execution_matches',
        sa.Column('excluded_from_learning', sa.Boolean(), nullable=False, server_default='false')
    )
    op.add_column('recommendation_execution_matches',
        sa.Column('exclusion_reason', sa.String(50), nullable=True)
    )
    op.add_column('recommendation_execution_matches',
        sa.Column('exclusion_notes', sa.Text(), nullable=True)
    )
    op.add_column('recommendation_execution_matches',
        sa.Column('excluded_at', sa.DateTime(), nullable=True)
    )

    # Add index for querying excluded records
    op.create_index('idx_rem_excluded', 'recommendation_execution_matches', ['excluded_from_learning'])


def downgrade() -> None:
    """Remove exclusion tracking columns."""
    # Remove from recommendation_execution_matches
    op.drop_index('idx_rem_excluded', table_name='recommendation_execution_matches')
    op.drop_column('recommendation_execution_matches', 'excluded_at')
    op.drop_column('recommendation_execution_matches', 'exclusion_notes')
    op.drop_column('recommendation_execution_matches', 'exclusion_reason')
    op.drop_column('recommendation_execution_matches', 'excluded_from_learning')

    # Remove from strategy_recommendations
    op.drop_index('idx_rec_excluded', table_name='strategy_recommendations')
    op.drop_column('strategy_recommendations', 'excluded_at')
    op.drop_column('strategy_recommendations', 'exclusion_notes')
    op.drop_column('strategy_recommendations', 'exclusion_reason')
    op.drop_column('strategy_recommendations', 'excluded_from_learning')
