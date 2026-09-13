"""Add salary_payslips: factual per-pay-date gross.

Revision ID: 20260912_salary_payslips
Revises: 20260912_salary_gross
Create Date: 2026-09-12

A stated monthly rate is a model; a paystub is a fact. Neel, 2026-09-12:
"you have Neel's salary picture. Do not spread it across all months. Use it
factually." Rows here are dated pay events and take precedence over both
the W-2 spread and any gross projection for the months they cover — so the
current month reads what has actually been paid, not a full-month rate.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260912_salary_payslips'
down_revision = '20260912_salary_gross'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'salary_payslips',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('person', sa.String(100), nullable=False),
        sa.Column('employer', sa.String(200), nullable=True),
        sa.Column('pay_date', sa.Date(), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=True),
        sa.Column('period_end', sa.Date(), nullable=True),
        sa.Column('gross', sa.Numeric(12, 2), nullable=False),
        sa.Column('net', sa.Numeric(12, 2), nullable=True),
        sa.Column('source', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('person', 'pay_date', 'period_start', name='uq_salary_payslip'),
    )


def downgrade() -> None:
    op.drop_table('salary_payslips')
