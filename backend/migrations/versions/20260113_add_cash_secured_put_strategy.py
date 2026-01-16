"""Add cash_secured_put strategy configuration

Revision ID: add_cash_secured_put_strategy
Revises: add_rlhf_algorithm_version
Create Date: 2026-01-13

Adds the cash_secured_put strategy to the strategy_configs table.
This strategy recommends selling cash-secured puts on portfolio stocks
when technical analysis conditions are favorable (oversold/at support).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision = 'add_cash_secured_put_strategy'
down_revision = 'add_rlhf_algorithm_version'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add cash_secured_put strategy configuration."""
    conn = op.get_bind()

    # Check if strategy already exists
    existing = conn.execute(text(
        "SELECT strategy_type FROM strategy_configs WHERE strategy_type = 'cash_secured_put'"
    )).fetchone()

    if not existing:
        conn.execute(text("""
            INSERT INTO strategy_configs
            (strategy_type, name, description, category, enabled, notification_enabled, notification_priority_threshold, parameters)
            VALUES
            ('cash_secured_put',
             'Cash-Secured Put Strategy',
             'Recommends selling cash-secured puts on portfolio stocks when TA conditions are favorable (oversold/at support)',
             'income_generation',
             true,
             true,
             'high',
             '{"min_score": 80, "min_premium": 30, "target_delta": 0.10}'::jsonb)
        """))
        print("Added strategy: cash_secured_put")
    else:
        print("Strategy already exists: cash_secured_put")


def downgrade() -> None:
    """Remove cash_secured_put strategy configuration."""
    conn = op.get_bind()
    conn.execute(text("""
        DELETE FROM strategy_configs
        WHERE strategy_type = 'cash_secured_put'
    """))
