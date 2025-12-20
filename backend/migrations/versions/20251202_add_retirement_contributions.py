"""Add retirement contributions table for IRS transcript data.

Revision ID: a1b2c3d4e5f6
Revises: f9a8b7c6d5e4
Create Date: 2025-12-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f9a8b7c6d5e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create retirement_contributions table to store IRS transcript data
    op.create_table(
        'retirement_contributions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner', sa.String(100), nullable=False),  # 'Neel' or 'Jaya'
        sa.Column('tax_year', sa.Integer(), nullable=False),
        
        # 401(k) from W-2 deferred compensation
        sa.Column('contributions_401k', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        sa.Column('roth_401k', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        
        # IRA contributions from Form 5498
        sa.Column('ira_contributions', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        sa.Column('roth_ira_contributions', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        sa.Column('rollover_contributions', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        sa.Column('sep_contributions', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        sa.Column('simple_contributions', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        
        # HSA from W-2
        sa.Column('hsa_contributions', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        
        # Fair Market Values (JSON array of account FMVs)
        sa.Column('ira_fmv', sa.JSON(), nullable=True),
        
        # W-2 wages for context
        sa.Column('total_wages', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        
        # Source tracking
        sa.Column('source_file', sa.String(500), nullable=True),
        sa.Column('ingestion_id', sa.Integer(), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner', 'tax_year', name='uq_retirement_contribution_owner_year'),
    )
    
    # Create indexes
    op.create_index('idx_retirement_contributions_owner', 'retirement_contributions', ['owner'])
    op.create_index('idx_retirement_contributions_year', 'retirement_contributions', ['tax_year'])


def downgrade() -> None:
    op.drop_index('idx_retirement_contributions_year', table_name='retirement_contributions')
    op.drop_index('idx_retirement_contributions_owner', table_name='retirement_contributions')
    op.drop_table('retirement_contributions')

