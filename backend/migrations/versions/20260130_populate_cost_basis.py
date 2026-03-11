"""Populate cost_basis values for investment holdings

Data-only migration. Sets cost_basis = per_share_cost × quantity
for each account/symbol pair based on known purchase prices.
For family_hsa, falls back to current_price × quantity.

Revision ID: populate_cost_basis
Revises: add_put_premium_settings
Create Date: 2026-01-30

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'populate_cost_basis'
down_revision = 'add_put_premium_settings'
branch_labels = None
depends_on = None


# Per-share cost basis by account_id -> symbol -> cost_per_share
COST_BASIS_DATA = {
    'neel_brokerage': {
        'MSFT': 344.44, 'AAPL': 108.43, 'NVDA': 152.85, 'IBIT': 47.34,
        'TSLA': 95.88, 'AVGO': 233.54, 'META': 613.49, 'BABA': 162.89,
        'PLTR': 80.31, 'HOOD': 112.78, 'FIG': 47.97,
    },
    'neel_retirement': {
        'AVGO': 163.65, 'NVDA': 155.82, 'IBIT': 33.39, 'META': 650.00,
        'AAPL': 183.88, 'MSFT': 489.58, 'MSTR': 292.99, 'NFLX': 85.58,
        'RKLB': 69.30, 'GOOG': 323.44, 'AGQ': 222.56, 'RING': 74.86,
        'LLY': 1025.18,
    },
    'neel_roth_ira': {
        'IBIT': 52.57,
    },
    'jaya_brokerage': {
        'AAPL': 114.38, 'TSLA': 122.23, 'NVDA': 18.93, 'IBIT': 34.59,
        'CRCL': 146.59,
    },
    'jaya_ira': {
        'NVDA': 52.00, 'IBIT': 29.92, 'HOOD': 111.82, 'COIN': 315.81,
        'MU': 238.40, 'TSM': 293.51,
    },
    'jaya_roth_ira': {
        'HOOD': 129.88, 'NVDA': 181.24,
    },
    'alisha_brokerage': {
        'AAPL': 198.61, 'FIG': 56.44, 'IBIT': 56.10, 'HOOD': 108.88,
        'TSLA': 327.80,
    },
}


def upgrade() -> None:
    """Set cost_basis = per_share_cost × quantity for known holdings."""
    conn = op.get_bind()

    # Update known account/symbol pairs
    for account_id, symbols in COST_BASIS_DATA.items():
        for symbol, cost_per_share in symbols.items():
            conn.execute(
                sa.text(
                    "UPDATE investment_holdings "
                    "SET cost_basis = :cost_per_share * quantity "
                    "WHERE account_id = :account_id AND symbol = :symbol"
                ),
                {'cost_per_share': cost_per_share, 'account_id': account_id, 'symbol': symbol},
            )

    # HSA fallback: cost_basis = current_price × quantity
    conn.execute(
        sa.text(
            "UPDATE investment_holdings "
            "SET cost_basis = current_price * quantity "
            "WHERE account_id = 'family_hsa' AND cost_basis IS NULL"
        )
    )


def downgrade() -> None:
    """Clear populated cost_basis values."""
    conn = op.get_bind()

    # Clear all accounts we touched
    all_account_ids = list(COST_BASIS_DATA.keys()) + ['family_hsa']
    for account_id in all_account_ids:
        conn.execute(
            sa.text(
                "UPDATE investment_holdings "
                "SET cost_basis = NULL "
                "WHERE account_id = :account_id"
            ),
            {'account_id': account_id},
        )
