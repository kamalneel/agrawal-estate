"""bbd_metric_gain — store net flows and dollar gain on each BBD metric row.

Revision ID: 20260925_bbd_metric_gain
Revises: 20260924_option_chains
Create Date: 2026-09-25

BBD audit F3: the page's dollar-growth cards were actual_value −
baseline_value, i.e. the change in account balance, so a year in which
$238K was withdrawn showed "+$47,809" beside a +25% return, and the
"market appreciation only" dollars were byte-identical to the combined
ones. The percent columns were already flow-adjusted (Modified Dietz);
the dollars were not.

Each growth row now carries the period's net external flows (pure_growth
also counts options premium as an inflow) and gain_value = actual −
baseline − net_flows. Summary cards read gain_value.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260925_bbd_metric_gain'
down_revision = '20260924_option_chains'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bbd_performance_metrics', sa.Column('net_flows', sa.Numeric(18, 2), nullable=True))
    op.add_column('bbd_performance_metrics', sa.Column('gain_value', sa.Numeric(18, 2), nullable=True))


def downgrade() -> None:
    op.drop_column('bbd_performance_metrics', 'gain_value')
    op.drop_column('bbd_performance_metrics', 'net_flows')
