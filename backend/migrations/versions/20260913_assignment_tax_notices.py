"""Add assignment_tax_notices: one row per call-assignment tax-lot notice sent.

Revision ID: 20260913_assignment_tax_notices
Revises: 20260912_payslip_withholding
Create Date: 2026-09-13

Neel, 2026-09-13: "every time there is a call assignment ... send me a
note regarding the tax implications." Robinhood disposes assigned shares
by the account's default method (FIFO unless changed) and only lets the
lots be corrected until 9 PM ET on the settlement date, so the note has
a deadline and must never be sent twice or missed. This table is the
dedup ledger: a notice key is (kind, account, symbol, event date, strike).
"""
from alembic import op
import sqlalchemy as sa

revision = '20260913_assignment_tax_notices'
down_revision = '20260912_payslip_withholding'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'assignment_tax_notices',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('notice_key', sa.String(200), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),          # 'pending' | 'assigned'
        sa.Column('account_id', sa.String(100), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('event_date', sa.Date(), nullable=False),        # expiration (pending) or assignment date
        sa.Column('strike', sa.Numeric(12, 2), nullable=False),
        sa.Column('shares', sa.Numeric(18, 4), nullable=False),
        sa.Column('fifo_gain', sa.Numeric(14, 2), nullable=True),
        sa.Column('highest_cost_gain', sa.Numeric(14, 2), nullable=True),
        sa.Column('deadline', sa.DateTime(), nullable=True),       # 9 PM ET on the settlement date
        sa.Column('email_sent', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('email_id', sa.String(100), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('notice_key', name='uq_assignment_tax_notice'),
    )


def downgrade() -> None:
    op.drop_table('assignment_tax_notices')
