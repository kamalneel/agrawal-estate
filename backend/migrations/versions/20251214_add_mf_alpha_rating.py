"""Add Alpha and Value Research Rating to Mutual Fund Research

Revision ID: add_mf_alpha_rating
Revises: add_mf_research
Create Date: 2025-12-14

Adds alpha and value_research_rating columns to mutual_fund_research table.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision = 'add_mf_alpha_rating'
down_revision = 'add_mf_research'
branch_labels = None
depends_on = None


def upgrade():
    """Add alpha and value_research_rating columns."""
    # Check if columns already exist before adding
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('mutual_fund_research')]
    
    if 'alpha' not in columns:
        op.add_column('mutual_fund_research', 
            sa.Column('alpha', sa.Numeric(precision=8, scale=4), nullable=True)
        )
    
    if 'value_research_rating' not in columns:
        op.add_column('mutual_fund_research',
            sa.Column('value_research_rating', sa.Integer(), nullable=True)
        )


def downgrade():
    """Remove alpha and value_research_rating columns."""
    op.drop_column('mutual_fund_research', 'value_research_rating')
    op.drop_column('mutual_fund_research', 'alpha')

