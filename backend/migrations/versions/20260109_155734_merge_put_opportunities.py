"""merge put opportunities

Revision ID: d2cc1339240a
Revises: 78ecf02e63f2, 20260109_put_opportunities
Create Date: 2026-01-09 15:57:34.551899

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2cc1339240a'
down_revision: Union[str, None] = ('78ecf02e63f2', '20260109_put_opportunities')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

