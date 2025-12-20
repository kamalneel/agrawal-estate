"""Add technical analysis strategies

Revision ID: add_ta_strategies
Revises: 
Create Date: 2025-12-10

Adds the new strategy configurations for:
- close_early_opportunity: Close options early when profit + volatility risk
- roll_options: Smart rolling with technical analysis
- new_covered_call: Sell new calls with TA guidance
- mega_cap_bull_put: Bull put spreads on mega-cap stocks
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic
revision = 'add_ta_strategies'
down_revision = 'b5e708e1f6b0'
branch_labels = None
depends_on = None


def upgrade():
    """Add new strategy configurations."""
    conn = op.get_bind()
    
    # Check if strategies already exist
    existing = conn.execute(text(
        "SELECT strategy_type FROM strategy_configs WHERE strategy_type IN "
        "('close_early_opportunity', 'roll_options', 'new_covered_call', 'mega_cap_bull_put')"
    )).fetchall()
    existing_types = {row[0] for row in existing}
    
    strategies = [
        {
            'strategy_type': 'close_early_opportunity',
            'name': 'Close Early Opportunity',
            'description': 'Alert when options should be closed early due to profit + volatility risk',
            'category': 'risk_management',
            'enabled': True,
            'notification_enabled': True,
            'notification_priority_threshold': 'high',
            'parameters': '{"min_profit_percent": 70, "min_risk_score": 30}'
        },
        {
            'strategy_type': 'roll_options',
            'name': 'Roll Options Strategy',
            'description': 'Smart rolling with technical analysis for strike selection',
            'category': 'optimization',
            'enabled': True,
            'notification_enabled': True,
            'notification_priority_threshold': 'high',
            'parameters': '{"profit_threshold_early": 80, "profit_threshold_low": 50, "itm_threshold_percent": 1.0}'
        },
        {
            'strategy_type': 'new_covered_call',
            'name': 'New Covered Call Opportunity',
            'description': 'Identifies when to sell new covered calls with TA guidance',
            'category': 'income_generation',
            'enabled': True,
            'notification_enabled': True,
            'notification_priority_threshold': 'high',
            'parameters': '{"min_contracts_uncovered": 1, "expiration_weeks": 1}'
        },
        {
            'strategy_type': 'mega_cap_bull_put',
            'name': 'Mega Cap Bull Put Spreads',
            'description': 'Bull put spread opportunities on $200B+ market cap stocks',
            'category': 'income_generation',
            'enabled': True,
            'notification_enabled': True,
            'notification_priority_threshold': 'high',
            'parameters': '{"min_market_cap_billions": 200, "spread_width_min": 5, "spread_width_max": 10, "min_credit_percent": 20, "target_probability": 75, "max_alerts": 0, "expiration_weeks": 1}'
        },
    ]
    
    for strategy in strategies:
        if strategy['strategy_type'] not in existing_types:
            conn.execute(text("""
                INSERT INTO strategy_configs 
                (strategy_type, name, description, category, enabled, notification_enabled, notification_priority_threshold, parameters)
                VALUES 
                (:strategy_type, :name, :description, :category, :enabled, :notification_enabled, :notification_priority_threshold, :parameters::jsonb)
            """), strategy)
            print(f"Added strategy: {strategy['strategy_type']}")
        else:
            print(f"Strategy already exists: {strategy['strategy_type']}")
    
    conn.commit()


def downgrade():
    """Remove new strategy configurations."""
    conn = op.get_bind()
    conn.execute(text("""
        DELETE FROM strategy_configs 
        WHERE strategy_type IN ('close_early_opportunity', 'roll_options', 'new_covered_call', 'mega_cap_bull_put')
    """))
    conn.commit()

