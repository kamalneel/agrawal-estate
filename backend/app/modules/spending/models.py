"""
Spending module database models.
Stores categorized spending transactions imported from Monarch Money CSV exports.
"""

from datetime import date

from sqlalchemy import Column, Integer, String, Numeric, Date, Text, Index
from app.shared.models.base import BaseModel


# Categories to exclude from spending analysis (transfers, income, etc.)
EXCLUDED_CATEGORIES = {
    "Transfer",
    "Credit Card Payment",
    "Paychecks",
    "Interest",
    "Loan from Neel's Investment",
    "Other Income",
    "Balance Adjustments",
    "Investment",
    "Jaya's Salary",
    "Loan Repayment",
    "Tesla's loan payment",
}

# Categories included in total spending but excluded from "Avg Monthly" calculation
# (one-time or annual expenses that would inflate the monthly average)
NON_MONTHLY_CATEGORIES = {
    "Taxes",
    "Insurance",
    "Travel & Vacation",
    "ANNUAL EXPENSES",
    "ONE TIME",
    # Trip-specific Monarch tags
    "AdamX Work Trip - Vegas",
    "Bali trip",
    "Europe Trip 2025",
    "India Trip 2024",
}

# Trips: date-range-based classification. ALL spending within a trip's date range
# is treated as non-monthly (restaurants, dog sitter, etc.), regardless of category.
# To add a new trip: {"name": "Trip Name", "start": date(YYYY, M, D), "end": date(YYYY, M, D)}
TRIPS = [
    {"name": "Vegas NYE 2025", "start": date(2025, 12, 28), "end": date(2026, 1, 1)},
]


class SpendingTransaction(BaseModel):
    """Categorized spending transactions from Monarch Money."""

    __tablename__ = "spending_transactions"

    transaction_date = Column(Date, nullable=False)
    merchant = Column(String(255), nullable=True)
    category = Column(String(100), nullable=True)
    account = Column(String(255), nullable=True)
    original_statement = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    amount = Column(Numeric(18, 2), nullable=False)
    tags = Column(String(500), nullable=True)
    owner = Column(String(50), nullable=True)

    # Deduplication hash
    record_hash = Column(String(64), nullable=False, unique=True, index=True)

    # Provenance
    ingestion_id = Column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_spending_date", "transaction_date"),
        Index("idx_spending_category", "category"),
        Index("idx_spending_merchant", "merchant"),
        Index("idx_spending_account", "account"),
        Index("idx_spending_owner", "owner"),
        Index("idx_spending_date_category", "transaction_date", "category"),
    )
