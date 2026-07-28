"""
Spending module database models.
Stores categorized spending transactions imported from Monarch Money CSV exports.
"""

from datetime import date
from enum import Enum

from sqlalchemy import Column, Integer, String, Numeric, Date, Text, Index
from app.shared.models.base import BaseModel


class CategoryKind(str, Enum):
    """What kind of money event a category represents.

    `spending_transactions` is fed by Monarch, which aggregates every
    non-brokerage account — so it is a *transactions* table, not a spending
    table. A positive amount in it can be three completely different things,
    and the sign alone cannot tell them apart:

      - a tenant's rent landing in Bank of America   -> INCOME
      - a returned jacket refunded to a card         -> SPENDING (nets)
      - moving money between your own accounts       -> TRANSFER

    Classify by CATEGORY, never by sign. Sign then means direction *within*
    a kind, which is all a sign should ever mean. The old model had one
    "excluded" bucket for all three plus an `amount < 0` filter, which hid
    income, and silently deleted $9K of refunds so every category
    overstated what was actually spent.
    """

    #: Consumption. Negative = spend, positive = refund and nets against it.
    SPENDING = "spending"
    #: Earnings. Belongs on the Income page, never on Spending.
    INCOME = "income"
    #: Internal movement between accounts. Belongs nowhere; counting it
    #: either way inflates both sides.
    TRANSFER = "transfer"
    #: An income-producing asset where BOTH sides live in one category.
    #: Nets to a single stream on the Income page — negative while it is
    #: still being built out, positive once it earns.
    BUSINESS = "business"


# Only non-SPENDING categories are listed; anything absent defaults to
# SPENDING (see `kind_of`). That default is deliberate — a new Monarch
# category is far more likely to be an expense than anything else, and an
# unclassified expense is a visible number rather than a silent omission.
#
# Apostrophes: Monarch emits curly ones (U+2019) in user-created names while
# these constants were written with straight ones, and matching is exact
# string. Any category containing an apostrophe MUST appear under both
# spellings. Caught 2026-07-25: "Tesla’s loan payment" arrived curly and was
# counting as spending.
CATEGORY_KINDS: dict[str, CategoryKind] = {
    # --- internal movement -------------------------------------------------
    "Transfer": CategoryKind.TRANSFER,
    "Credit Card Payment": CategoryKind.TRANSFER,
    "Balance Adjustments": CategoryKind.TRANSFER,
    "Investment": CategoryKind.TRANSFER,
    "Loan Repayment": CategoryKind.TRANSFER,
    "Loan from Neel's Investment": CategoryKind.TRANSFER,
    "Loan from Neel’s Investment": CategoryKind.TRANSFER,
    "Tesla's loan payment": CategoryKind.TRANSFER,
    "Tesla’s loan payment": CategoryKind.TRANSFER,
    # --- earnings ----------------------------------------------------------
    "Paychecks": CategoryKind.INCOME,
    "Jaya's Salary": CategoryKind.INCOME,
    "Jaya’s Salary": CategoryKind.INCOME,
    "Other Income": CategoryKind.INCOME,
    "Business Income": CategoryKind.INCOME,
    "Interest": CategoryKind.INCOME,
    # --- income-producing assets (both sides net) --------------------------
    # 303 Hartstene: owned outright and let out. Rent received and property
    # costs (HOA, tax, repairs) share one category, so it nets to +$65,108
    # (2025) rather than reading as a $13,921 expense.
    "303 Hartstene Dr": CategoryKind.BUSINESS,
    # Airbnb: partial ownership, build-out only. Negative until 2027 revenue,
    # at which point it behaves exactly like 303 Hartstene above — same
    # machinery, no new decision needed.
    "Investment - AirBnb Business": CategoryKind.BUSINESS,
}

#: The Airbnb build-out (see CATEGORY_KINDS). Imported by the income module
#: so the two views can never disagree about which rows are Airbnb.
AIRBNB_CATEGORY = "Investment - AirBnb Business"

#: The owned rental property, likewise shared with the income module.
HARTSTENE_CATEGORY = "303 Hartstene Dr"


#: Monarch's own marker for a returned purchase: original_statement begins
#: "Refund: <merchant>". This is the ONLY inflow the Spending page nets.
#:
#: Everything else that arrives as a positive amount is excluded outright, not
#: netted — a rule learned the hard way on 2026-07-27, when June read $3,437
#: against $17,750 of real spending. The $14,313 difference was an
#: uncategorized $7,500 ACH deposit from Bank of America, a $4,214 security
#: deposit returned by the previous landlord, and ~$2,500 of genuine refunds.
#: Only the last group belongs in a spending total.
#:
#: Deliberately conservative: a Costco or Amazon return that Monarch did not
#: tag will not net, so that category reads slightly high. Overstating spend
#: is the safe direction; an unexplained inflow quietly cancelling real
#: purchases is not.
REFUND_STATEMENT_PREFIX = "refund:"


def is_refund(amount, original_statement: str | None) -> bool:
    """True for a returned purchase that should net against its category."""
    return bool(
        amount is not None and amount > 0
        and (original_statement or "").strip().lower().startswith(
            REFUND_STATEMENT_PREFIX)
    )


def kind_of(category: str | None) -> CategoryKind:
    """Classify a category. Unknown/blank categories are SPENDING."""
    if not category:
        return CategoryKind.SPENDING
    return CATEGORY_KINDS.get(category, CategoryKind.SPENDING)


def categories_of_kind(*kinds: CategoryKind) -> set[str]:
    return {c for c, k in CATEGORY_KINDS.items() if k in kinds}


#: Everything the Spending page must not count. Derived from CATEGORY_KINDS
#: so the two can never drift; kept as a name because the BBD service and
#: the /outflows reconciliation still consume it.
EXCLUDED_CATEGORIES = categories_of_kind(
    CategoryKind.TRANSFER, CategoryKind.INCOME, CategoryKind.BUSINESS
)

#: Routed to the Income page as netted streams.
BUSINESS_CATEGORIES = categories_of_kind(CategoryKind.BUSINESS)


# Categories included in total spending but excluded from "Avg Monthly" calculation
# (one-time or annual expenses that would inflate the monthly average)
NON_MONTHLY_CATEGORIES = {
    "Taxes",
    "Insurance",
    "Travel & Vacation",
    "ANNUAL EXPENSES",
    "ONE TIME",
    # Derived label from RENT_SPLIT_RULES: application/screening fees and
    # movers. A one-off cost of changing homes, so it must not inflate the
    # monthly average the way the rent itself legitimately does.
    "Home Search & Moving",
    # Trip-specific Monarch tags
    "AdamX Work Trip - Vegas",
    "Bali trip",
    "Europe Trip 2025",
    "India Trip 2024",
}

# Monarch files every housing payment under one "Rent" category, which mixed
# four unrelated things and made the category unreadable: May 2026 showed
# $27,618 and June showed a NET REFUND, so the move between homes — the
# largest change in the household's cost structure this year — was invisible.
#
# Split by counterparty rather than by date. Dates overlap during a move (the
# new landlord was paid on 2026-05-20 while the old one was still being paid
# through 2026-05-04), so a date boundary cannot separate them; the
# counterparty can. Matching is on original_statement, which carries the full
# payee, falling back to merchant.
#
# Both homes report as one "Home Rent" line — Neel already knows which house
# he lives in, so the address was noise (2026-07-28). The two rules are kept
# separate anyway: they encode WHICH counterparty is rent (vs. the movers and
# letting agents below), and re-splitting by address later is a one-word
# change to either label.
#
# Same derived-classification pattern as TRIPS below: the DB is never
# rewritten (Monarch stays the source of truth, per the
# no-direct-db-modifications rule) — this only affects display. If these
# become real Monarch categories later, delete the matching rule and the
# category flows through on its own.
RENT_SPLIT_RULES: list[tuple[str, tuple[str, ...]]] = [
    # Current home, from 2026-06. Landlord Eric Chang. The $1 and $2 wires on
    # 2026-05-14/19 are test transfers preceding the $19,580 deposit.
    ("Home Rent", ("eric chang",)),
    # Previous home. Landlord Yuan Lee. June 2026 carries the returned
    # security deposit ($4,000) and a utility refund ($214.27) as INFLOWS,
    # which correctly net against this line rather than reading as rent.
    ("Home Rent", ("yuan lee", "; lee", "chk 3210")),
    # Finding the next home: application and screening fees, plus the movers.
    # One-time costs of the move, not rent — see NON_MONTHLY_CATEGORIES.
    ("Home Search & Moving",
     ("rentapplication", "rent application", "rentspree", "real estate",
      "realt", "movers")),
]

RENT_CATEGORY = "Rent"

# Merchant -> category corrections applied on top of whatever Monarch says.
#
# Use this when a merchant is reliably miscategorised, or is split across
# categories because it was recategorised part-way through. Red Rock
# Volleyball is both: four rows sat in "Entertainment & Recreation" while the
# 2026-07-21 row had already been moved to "Education", so the same activity
# was being counted in two places.
#
# Matching is a case-insensitive substring on the MERCHANT only — not the
# statement — and it must be specific enough to be unambiguous. "red rock"
# alone would also catch Red Rock Coffee, an unrelated $6.25 coffee shop.
#
# Same derived-classification pattern as TRIPS and RENT_SPLIT_RULES: the DB
# is never rewritten, so Monarch stays the source of truth. If a correction
# is later made in Monarch itself, delete the line here and it flows through
# unchanged.
MERCHANT_CATEGORY_OVERRIDES: list[tuple[str, str]] = [
    ("red rock volleyball", "Alisha's Education"),
    # The city bills electricity, water and refuse together, so "Gas &
    # Electric" understated what it is. Monarch spells the merchant three
    # ways ("City of Palo", "City of Palo Alto", "City Of Palo Alto") and all
    # three are the same utility account.
    #
    # Match "city of palo", NOT "palo alto" — the latter also catches a
    # dentist ($6,796), Palo Alto Bagels and other local merchants that
    # merely have the city in their names.
    ("city of palo", "Home Utility"),
    # Amazon is 371 rows / $10,170 — big enough that burying it inside
    # "Shopping" told you nothing about either. Monarch also scatters it
    # across Miscellaneous, Furniture & Housewares and Gifts; this pulls all
    # of them into one line. ("Refund Amazon" sits in Transfer, an excluded
    # category, so it never reaches here.)
    ("amazon", "Amazon"),
    # Blue Bottle is 180 rows / $1,685 — 36% of Coffee Shops on its own, and
    # a habit worth seeing separately from the occasional Starbucks. Two
    # spellings ("Blue Bottle Coffee" and "…, Inc") both match. What's left
    # in Coffee Shops is every other cafe.
    ("blue bottle", "Blue Bottle"),
]


# Whole-category remapping, for when Monarch's category is right about the
# rows but wrong about the grouping. Merchant overrides above beat these.
CATEGORY_RENAMES: dict[str, str] = {
    # Fuel is a running cost of the car, so it belongs with servicing rather
    # than in a category of its own (Neel, 2026-07-28: "all things auto").
    # Deliberately NOT merged: "Auto Payment" (a loan, debt service rather
    # than a running cost) and "Parking & Tolls".
    "Gas": "Auto Maintenance",
}


def display_category(category: str | None, merchant: str | None,
                     original_statement: str | None) -> str:
    """The category a row is shown under — the whole rulebook, in order.

    1. Merchant override      most specific, always wins
    2. Rent split             by counterparty, within the Rent category
    3. Category rename        whole-category remap
    4. Monarch's own category the default

    Applied at QUERY time, not at import. Every future Monarch export is
    therefore corrected automatically the moment it lands — no reprocessing,
    and no rewriting of `spending_transactions`, so Monarch stays the source
    of truth (project-kb: no-direct-db-modifications). Editing a rule here
    re-labels history and future imports in the same instant.
    """
    m = (merchant or "").lower()
    for needle, corrected in MERCHANT_CATEGORY_OVERRIDES:
        if needle in m:
            return corrected
    if category == RENT_CATEGORY:
        return split_rent_label(merchant, original_statement)
    if category in CATEGORY_RENAMES:
        return CATEGORY_RENAMES[category]
    return category or "Uncategorized"


def split_rent_label(merchant: str | None, original_statement: str | None) -> str:
    """Display label for a `Rent` row. Falls back to the raw category so an
    unmatched payee stays visible rather than being silently reassigned."""
    haystack = f"{original_statement or ''} {merchant or ''}".lower()
    for label, needles in RENT_SPLIT_RULES:
        if any(n in haystack for n in needles):
            return label
    return RENT_CATEGORY


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
