"""Add Airbnb timeshare investment tables

Revision ID: 20260207_airbnb_tables
Revises: 20260206_spending_transactions
Create Date: 2026-02-07

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260207_airbnb_tables'
down_revision = '20260206_spending_transactions'
branch_labels = None
depends_on = None


def upgrade():
    # Properties
    op.create_table(
        'airbnb_properties',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('property_type', sa.String(100), nullable=True),
        sa.Column('points_per_week', sa.Integer(), nullable=True),
        sa.Column('income_per_week_best', sa.Numeric(10, 2), nullable=True),
        sa.Column('income_per_week_worst', sa.Numeric(10, 2), nullable=True),
        sa.Column('housekeeping_per_week', sa.Numeric(10, 2), nullable=True),
        sa.Column('management_fee_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('capital_cost_rate_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('status', sa.String(20), server_default='prospective'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Points Blocks
    op.create_table(
        'airbnb_points_blocks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('property_id', sa.Integer(), sa.ForeignKey('airbnb_properties.id', ondelete='CASCADE'), nullable=False),
        sa.Column('block_type', sa.String(20), nullable=False),
        sa.Column('points', sa.Integer(), nullable=False),
        sa.Column('cost_to_acquire', sa.Numeric(12, 2), nullable=True, server_default='0'),
        sa.Column('annual_cost_rate_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_airbnb_block_property', 'airbnb_points_blocks', ['property_id'])

    # Documents
    op.create_table(
        'airbnb_documents',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('property_id', sa.Integer(), sa.ForeignKey('airbnb_properties.id', ondelete='CASCADE'), nullable=False),
        sa.Column('document_type', sa.String(50), nullable=False),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_hash', sa.String(64), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('mime_type', sa.String(100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_airbnb_doc_property', 'airbnb_documents', ['property_id'])

    # Links
    op.create_table(
        'airbnb_links',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('property_id', sa.Integer(), sa.ForeignKey('airbnb_properties.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('url', sa.String(1000), nullable=False),
        sa.Column('link_type', sa.String(50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_airbnb_link_property', 'airbnb_links', ['property_id'])


def downgrade():
    op.drop_index('idx_airbnb_link_property', table_name='airbnb_links')
    op.drop_table('airbnb_links')
    op.drop_index('idx_airbnb_doc_property', table_name='airbnb_documents')
    op.drop_table('airbnb_documents')
    op.drop_index('idx_airbnb_block_property', table_name='airbnb_points_blocks')
    op.drop_table('airbnb_points_blocks')
    op.drop_table('airbnb_properties')
