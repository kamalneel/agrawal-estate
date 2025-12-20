"""Add bull put spread strategy config

Revision ID: b5e708e1f6b0
Revises: 20251209_weekly_tracking
Create Date: 2025-12-09 23:28:24.779459

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5e708e1f6b0'
down_revision: Union[str, None] = '20251209_weekly_tracking'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Insert bull put spread strategy configuration
    op.execute("""
        INSERT INTO strategy_configs (strategy_type, name, description, category, enabled, notification_enabled, notification_priority_threshold, parameters, created_at, updated_at)
        VALUES
        ('bull_put_spread', 'Bull Put Spread Opportunities', 'Identifies bull put spread opportunities on portfolio holdings, ranked by potential profit', 'income_generation', true, true, 'high', '{"sell_delta_min": 15, "sell_delta_max": 25, "buy_delta_min": 5, "buy_delta_max": 10, "min_credit": 0.50, "min_rr": 2.0, "spread_width_min": 2.5, "spread_width_max": 10.0, "max_holdings_to_analyze": 20}', NOW(), NOW())
        ON CONFLICT (strategy_type) DO NOTHING
    """)


def downgrade() -> None:
    # Remove bull put spread strategy configuration
    op.execute("""
        DELETE FROM strategy_configs WHERE strategy_type = 'bull_put_spread'
    """)

