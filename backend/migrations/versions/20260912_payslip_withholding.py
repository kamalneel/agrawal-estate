"""salary_payslips: carry the withholding the stub prints, not just gross.

Revision ID: 20260912_payslip_withholding
Revises: 20260912_salary_payslips
Create Date: 2026-09-12

Neel, 2026-09-12: "I want to give you my 2026 pay stubs so that you know how
much I am taking in deductions from my pay. That way, you can calculate how
much tax I have already paid." A stub is the authoritative record of tax
already paid for a year with no W-2 yet; the tax forecast reads the latest
YTD row per person instead of spreading a guess over ten months.

Current-period columns are what this stub withheld; *_ytd columns are the
employer's running totals as printed, which is what the return will show.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260912_payslip_withholding'
down_revision = '20260912_salary_payslips'
branch_labels = None
depends_on = None

COLUMNS = [
    'federal_withheld', 'state_withheld', 'social_security', 'medicare', 'sdi',
    'retirement_401k', 'benefits_pretax', 'post_tax_deductions',
    'gross_ytd', 'net_ytd', 'federal_withheld_ytd', 'state_withheld_ytd',
    'social_security_ytd', 'medicare_ytd', 'sdi_ytd', 'retirement_401k_ytd',
    'benefits_pretax_ytd',
]


def upgrade() -> None:
    for col in COLUMNS:
        op.add_column('salary_payslips', sa.Column(col, sa.Numeric(12, 2), nullable=True))
    op.add_column('salary_payslips', sa.Column('annual_rate', sa.Numeric(12, 2), nullable=True))
    op.add_column('salary_payslips', sa.Column('source_file', sa.String(300), nullable=True))


def downgrade() -> None:
    op.drop_column('salary_payslips', 'source_file')
    op.drop_column('salary_payslips', 'annual_rate')
    for col in reversed(COLUMNS):
        op.drop_column('salary_payslips', col)
