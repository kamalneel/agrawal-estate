"""merge_cost_basis_heads

Revision ID: 52ebadecdfa6
Revises: d2cc1339240a, 20260110_cost_basis
Create Date: 2026-01-09 20:23:49.363640

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '52ebadecdfa6'
down_revision: Union[str, None] = ('d2cc1339240a', '20260110_cost_basis')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

