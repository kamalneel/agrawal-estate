"""Add business investment fields to equity_companies and new partner/capital event tables.

Revision ID: 20260213_business_investment
Revises: 20260208_salary_projections
Create Date: 2026-02-13
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20260213_business_investment'
down_revision = '20260208_salary_projections'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to equity_companies
    op.add_column('equity_companies', sa.Column('investment_type', sa.String(50), server_default='startup_equity', nullable=True))
    op.add_column('equity_companies', sa.Column('entity_type', sa.String(50), nullable=True))
    op.add_column('equity_companies', sa.Column('ein', sa.String(20), nullable=True))
    op.add_column('equity_companies', sa.Column('state_of_incorporation', sa.String(50), nullable=True))
    op.add_column('equity_companies', sa.Column('incorporation_date', sa.Date(), nullable=True))
    op.add_column('equity_companies', sa.Column('dissolution_date', sa.Date(), nullable=True))
    op.add_column('equity_companies', sa.Column('dissolution_status', sa.String(50), nullable=True))
    op.add_column('equity_companies', sa.Column('total_capital_invested', sa.Numeric(18, 2), nullable=True))
    op.add_column('equity_companies', sa.Column('total_revenue_earned', sa.Numeric(18, 2), nullable=True))
    op.add_column('equity_companies', sa.Column('section_1244_eligible', sa.String(1), server_default='N', nullable=True))

    # Create equity_partners table
    op.create_table(
        'equity_partners',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('equity_companies.id'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('role', sa.String(50), nullable=True),
        sa.Column('ownership_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('capital_contributed', sa.Numeric(18, 2), nullable=True),
        sa.Column('is_primary', sa.String(1), server_default='N', nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create equity_capital_events table
    op.create_table(
        'equity_capital_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('equity_companies.id'), nullable=False),
        sa.Column('event_date', sa.Date(), nullable=True),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('amount', sa.Numeric(18, 2), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('contributor', sa.String(200), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )

    # Seed FanbaseAI data
    op.execute(sa.text("""
        INSERT INTO equity_companies (
            name, status, investment_type, entity_type, ein,
            state_of_incorporation, dissolution_status,
            total_capital_invested, total_revenue_earned,
            section_1244_eligible, notes, created_at, updated_at
        ) VALUES (
            'FanbaseAI, Inc.', 'closing', 'business_investment', 'c_corp', '99-1952708',
            'Delaware', 'in_progress',
            25000.00, 15000.00,
            'Y', 'Delaware C Corp incorporated via Stripe Atlas on 3/14/2024.
Co-founded by Neel Kamal (70%) and Chetan Jagannatha Rao (30%). Being dissolved with $0 remaining.
Section 1244 ordinary loss deduction eligible for 2026 tax return.

CORPORATE DETAILS:
  Authorized shares: 10,000,000 Common Stock (par $0.00001)
  Issued shares: 9,500,000 (Neel 6,650,000 + Chetan 2,850,000)
  Officers: Neel Kamal (President/CEO, Secretary)
  Directors: Neel Kamal, Chetan Jagannatha Rao
  Fiscal year: Calendar (Dec 31)
  DE File Number: 3267275
  IRS Name Control: FANB
  Tax filing: Form 1120

ADDRESSES:
  Principal Office: 380 Hamilton Ave #217, Palo Alto, CA 94301
  DE Registered Office: 651 N Broad St, Suite 201, Middletown, DE 19709
  Representative: Neel Kamal | Phone: (650) 800-3586

REGISTERED AGENT:
  Legalinc Corporate Services Inc.
  131 Continental Dr, Suite 305, Newark, DE 19713
  Plan active through Mar 14, 2027 (auto-renews 28 days before incorporation date)
  NOTE: Must cancel RA plan as part of dissolution.

STOCK DETAILS:
  Neel Kamal: 6,650,000 shares purchased 3/25/2024 for $66.50 (IP assignment), 83(b) filed
  Chetan Jagannatha Rao: 2,850,000 shares purchased 3/25/2024 for $28.50 (IP assignment), 83(b) filed
  Vesting: 4-year, 25% cliff 3/14/2025, 1/48th monthly thereafter
  Both 83(b) elections filed timely via Stripe Atlas and delivered to IRS (confirmed USPS certified mail)

TAX DESIGNEE (Form 8821):
  John Moseley, 10601 Clarence Dr Suite 250, Frisco TX 75033
  Phone: (866) 767-5850 | Years: 2023-2025

DOCUMENTS ON FILE: Certificate of Incorporation, Bylaws, Board Approvals, Stock Purchase Agreements,
  83(b) Elections + Proofs, CIIAA agreements, SS-4, CP 575 Letter, Form 8821
  Stored in: data/fanbase-corp-docs/',
            NOW(), NOW()
        )
    """))

    # Get the FanbaseAI company ID for FK references
    # Use a subquery approach compatible with most DBs
    op.execute(sa.text("""
        INSERT INTO equity_partners (company_id, name, role, ownership_pct, capital_contributed, is_primary, notes, created_at, updated_at)
        SELECT id, 'Neel Kamal', 'both', 70.00, 25000.00, 'Y', 'Co-founder, President/CEO, Secretary, Director. 6,650,000 shares.', NOW(), NOW()
        FROM equity_companies WHERE name = 'FanbaseAI, Inc.'
    """))

    op.execute(sa.text("""
        INSERT INTO equity_partners (company_id, name, role, ownership_pct, capital_contributed, is_primary, notes, created_at, updated_at)
        SELECT id, 'Chetan Jagannatha Rao', 'both', 30.00, 0.00, 'N', 'Co-founder, Director. 2,850,000 shares.', NOW(), NOW()
        FROM equity_companies WHERE name = 'FanbaseAI, Inc.'
    """))

    op.execute(sa.text("""
        INSERT INTO equity_capital_events (company_id, event_date, event_type, amount, description, contributor, created_at, updated_at)
        SELECT id, '2024-01-01', 'capital_contribution', 25000.00, 'Personal capital investment into FanbaseAI', 'Neel Kamal', NOW(), NOW()
        FROM equity_companies WHERE name = 'FanbaseAI, Inc.'
    """))

    op.execute(sa.text("""
        INSERT INTO equity_capital_events (company_id, event_date, event_type, amount, description, contributor, created_at, updated_at)
        SELECT id, '2025-12-31', 'revenue', 15000.00, 'Total revenue earned from customers', NULL, NOW(), NOW()
        FROM equity_companies WHERE name = 'FanbaseAI, Inc.'
    """))


def downgrade() -> None:
    # Remove seed data
    op.execute(sa.text("DELETE FROM equity_capital_events WHERE company_id IN (SELECT id FROM equity_companies WHERE name = 'FanbaseAI, Inc.')"))
    op.execute(sa.text("DELETE FROM equity_partners WHERE company_id IN (SELECT id FROM equity_companies WHERE name = 'FanbaseAI, Inc.')"))
    op.execute(sa.text("DELETE FROM equity_companies WHERE name = 'FanbaseAI, Inc.'"))

    op.drop_table('equity_capital_events')
    op.drop_table('equity_partners')

    op.drop_column('equity_companies', 'section_1244_eligible')
    op.drop_column('equity_companies', 'total_revenue_earned')
    op.drop_column('equity_companies', 'total_capital_invested')
    op.drop_column('equity_companies', 'dissolution_status')
    op.drop_column('equity_companies', 'dissolution_date')
    op.drop_column('equity_companies', 'incorporation_date')
    op.drop_column('equity_companies', 'state_of_incorporation')
    op.drop_column('equity_companies', 'ein')
    op.drop_column('equity_companies', 'entity_type')
    op.drop_column('equity_companies', 'investment_type')
