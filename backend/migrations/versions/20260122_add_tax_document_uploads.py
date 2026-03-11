"""Add tax document uploads and actual tax items tables

This migration adds support for:
1. tax_document_uploads - storing uploaded tax documents (1099s, W-2s, etc.)
2. actual_tax_items - extracted/manual tax data from documents

Revision ID: 20260122_tax_docs
Revises: 20260120_v4_conditions
Create Date: 2026-01-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260122_tax_docs'
down_revision = 'add_v4_follow_up_conditions'
branch_labels = None
depends_on = None


def upgrade():
    # Create tax_document_uploads table
    op.create_table('tax_document_uploads',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tax_year', sa.Integer(), nullable=False),
        sa.Column('document_type', sa.String(length=50), nullable=False),
        sa.Column('institution_name', sa.String(length=255), nullable=True),
        sa.Column('institution_ein', sa.String(length=20), nullable=True),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('file_hash', sa.String(length=64), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('upload_date', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('document_date', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True, server_default='uploaded'),
        sa.Column('extracted_data', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_tax_doc_year', 'tax_document_uploads', ['tax_year'], unique=False)
    op.create_index('idx_tax_doc_type', 'tax_document_uploads', ['document_type'], unique=False)
    op.create_index('idx_tax_doc_status', 'tax_document_uploads', ['status'], unique=False)

    # Create actual_tax_items table
    op.create_table('actual_tax_items',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tax_year', sa.Integer(), nullable=False),
        sa.Column('form_line', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('source_document_id', sa.Integer(), nullable=True),
        sa.Column('is_manual_entry', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['source_document_id'], ['tax_document_uploads.id'], ondelete='SET NULL')
    )
    op.create_index('idx_actual_tax_year', 'actual_tax_items', ['tax_year'], unique=False)
    op.create_index('idx_actual_tax_form_line', 'actual_tax_items', ['form_line'], unique=False)


def downgrade():
    # Drop actual_tax_items first (has FK to tax_document_uploads)
    op.drop_index('idx_actual_tax_form_line', table_name='actual_tax_items')
    op.drop_index('idx_actual_tax_year', table_name='actual_tax_items')
    op.drop_table('actual_tax_items')

    # Drop tax_document_uploads
    op.drop_index('idx_tax_doc_status', table_name='tax_document_uploads')
    op.drop_index('idx_tax_doc_type', table_name='tax_document_uploads')
    op.drop_index('idx_tax_doc_year', table_name='tax_document_uploads')
    op.drop_table('tax_document_uploads')
