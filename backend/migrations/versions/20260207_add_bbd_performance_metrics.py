"""Add bbd_performance_metrics table for Assumptions vs Reality tracking

Revision ID: 20260207_bbd_performance_metrics
Revises: 20260204_add_pending_orders
Create Date: 2026-02-07

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260207_bbd_performance_metrics'
down_revision = '20260204_add_pending_orders'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bbd_performance_metrics',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('period_type', sa.String(10), nullable=False),  # 'year', 'month', 'week'
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('metric_type', sa.String(20), nullable=False),  # 'portfolio_growth', 'options_yield'
        sa.Column('actual_value', sa.Numeric(18, 2), nullable=True),
        sa.Column('actual_percent', sa.Numeric(10, 4), nullable=True),
        sa.Column('expected_value', sa.Numeric(18, 2), nullable=True),
        sa.Column('expected_percent', sa.Numeric(10, 4), nullable=True),
        sa.Column('baseline_value', sa.Numeric(18, 2), nullable=True),
        sa.Column('variance_percent', sa.Numeric(10, 4), nullable=True),
        sa.Column('variance_value', sa.Numeric(18, 2), nullable=True),
        sa.Column('data_completeness', sa.String(20), server_default='complete'),
        sa.Column('computed_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),

        # Unique constraint
        sa.UniqueConstraint('period_type', 'period_start', 'metric_type', name='uq_bbd_metric_period'),
    )

    # Indexes
    op.create_index('idx_bbd_metric_type', 'bbd_performance_metrics', ['metric_type'])
    op.create_index('idx_bbd_period_type_start', 'bbd_performance_metrics', ['period_type', 'period_start'])


def downgrade():
    op.drop_index('idx_bbd_period_type_start', table_name='bbd_performance_metrics')
    op.drop_index('idx_bbd_metric_type', table_name='bbd_performance_metrics')
    op.drop_table('bbd_performance_metrics')
