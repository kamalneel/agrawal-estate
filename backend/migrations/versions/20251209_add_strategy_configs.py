"""Add strategy configs table.

Revision ID: 20251209_strategy_configs
Revises: 20251208_strategy_recommendations
Create Date: 2025-12-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251209_strat_configs'
down_revision = '20251208_strat_recs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create strategy_configs table
    op.create_table(
        'strategy_configs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('strategy_type', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notification_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notification_priority_threshold', sa.String(length=20), nullable=True, server_default='high'),
        sa.Column('parameters', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('strategy_type', name='uq_strategy_config_type')
    )
    
    # Add indexes
    op.create_index('idx_strategy_configs_type', 'strategy_configs', ['strategy_type'])
    op.create_index('idx_strategy_configs_enabled', 'strategy_configs', ['enabled'])
    
    # Insert default strategy configurations
    op.execute("""
        INSERT INTO strategy_configs (strategy_type, name, description, category, enabled, notification_enabled, notification_priority_threshold, parameters, created_at, updated_at)
        VALUES
        ('sell_unsold_contracts', 'Sell Unsold Contracts', 'Generates recommendations for holdings with unsold contracts that could generate income', 'income_generation', true, true, 'high', '{"min_weekly_income": 50}', NOW(), NOW()),
        ('early_roll_opportunity', 'Early Roll Opportunities', 'Alerts when positions reach profit threshold (default 80%) with days remaining, suggesting early roll', 'optimization', true, true, 'high', '{"profit_threshold": 0.80}', NOW(), NOW()),
        ('adjust_premium_expectation', 'Premium Setting Adjustments', 'Suggests updating premium settings when actual premiums differ significantly from configured values', 'optimization', true, true, 'medium', '{"difference_threshold_percent": 15}', NOW(), NOW()),
        ('diversify_holdings', 'Diversification Recommendations', 'Alerts when portfolio is too concentrated in a single symbol', 'risk_management', true, true, 'medium', '{"concentration_threshold_percent": 35}', NOW(), NOW())
    """)


def downgrade() -> None:
    op.drop_index('idx_strategy_configs_enabled', table_name='strategy_configs')
    op.drop_index('idx_strategy_configs_type', table_name='strategy_configs')
    op.drop_table('strategy_configs')

