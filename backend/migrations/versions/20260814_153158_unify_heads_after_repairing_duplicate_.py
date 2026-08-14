"""unify heads after repairing duplicate revision id

Revision ID: 8597cf945e92
Revises: 20260114_est_tax_payments, 20260502_bbd_settings, 20260814_rh_realized_trades
Create Date: 2026-08-14 15:31:58.489893

Schema no-op — this exists only to join three parallel branches into one
head so `alembic revision` works without naming a parent every time.

Alembic had been unusable for some months (2026-08-14): a data script with
no `revision` variable sat in versions/ and broke every command, and the
template id 'a1b2c3d4e5f6' was declared by two different migrations. While
it was broken, schema changes were applied to the database by hand, so
alembic_version drifted behind reality — it read 20260526_active_puts while
two later migrations were already live. After repairing both faults the DB
was `stamp`ed (not upgraded — replaying history would have collided with
tables that already exist); every table was verified present first.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8597cf945e92'
down_revision: Union[str, None] = ('20260114_est_tax_payments', '20260502_bbd_settings', '20260814_rh_realized_trades')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

