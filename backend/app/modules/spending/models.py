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
    # NOT listed (so SPENDING): "Adamx" and "AdamX Work Trip - Vegas" — work
    # expenses Neel paid personally. AdamX (his employer) reimburses them,
    # and the reimbursements NET against spending as one visible negative
    # line; see COUNTERPARTY_RULES "Work expenses (reimbursed)".
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
    # The Worldmark ownership — an investment made for future revenue in the
    # form of Airbnb (Neel, 2026-09-11). Nothing from Airbnb itself appears
    # here yet; the ledger is Worldmark charges, negative until the unit
    # earns (2027), at which point it behaves exactly like 303 Hartstene
    # above — same machinery, no new decision needed. Bookings ON Airbnb
    # for the family's own trips are vacations, re-routed by
    # COUNTERPARTY_RULES.
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

#: Every spelling Monarch has used for a returned purchase. "Refund from
#: <person>" is how a PayPal reversal arrives (Denise Hall, 2026-08-31).
REFUND_STATEMENT_PREFIXES = ("refund:", "refund from")


def is_refund(amount, original_statement: str | None,
              merchant: str | None = None) -> bool:
    """True for a returned purchase that should net against its category.

    Tested BEFORE the category's kind (see `classify`). On 2026-08-28 two
    $3,455 charges were refunded within three days, and Monarch filed the
    refunds under "Business Income" and "Other Income". With the kind filter
    first, the charges counted and the refunds vanished: August read
    $6,910 (30%) too high. A row that says "Refund" is a refund whatever
    category it was dropped into.
    """
    if amount is None or amount <= 0:
        return False
    stmt = (original_statement or "").strip().lower()
    merch = (merchant or "").strip().lower()
    return stmt.startswith(REFUND_STATEMENT_PREFIXES) or \
        merch.startswith(REFUND_STATEMENT_PREFIXES)


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

# Counterparty rules: category-INDEPENDENT. A row whose statement or merchant
# names one of these counterparties is spending under the given label, no
# matter what Monarch filed it as.
#
# Why this exists: on 2026-07-06 and 2026-07-31 the $9,000 rent wires to the
# new landlord arrived as category "Transfer". Transfer is an excluded kind,
# and the kind check ran on the raw category before any rulebook rule could
# see the row — so both months' rent silently vanished from the page (July
# read $9,461 against ~$18,500 real). Every month of 2025 had carried rent.
#
# The rule from project-kb (category-is-a-ledger-not-a-stream): identify a
# stream by counterparty + direction + kind, never by category membership.
# The landlord list is explicit so that a change of landlord fails loudly
# (rent goes missing and the missing-recurring flag fires) rather than
# silently re-filing under whatever Monarch guessed.
#
# Keep needles specific: "lee" alone would match half the merchants in the
# Bay Area; "; lee" and "chk 3210" are the exact forms BofA's statement uses.
#: (label, kind, needles[, direction]) — direction "out" / "in" limits the
#: rule to outflows / inflows; omitted means both.
COUNTERPARTY_RULES: list[tuple] = [
    # Current home, from 2026-06. Landlord Eric Chang.
    ("Home Rent", CategoryKind.SPENDING, ("eric chang",)),
    # Previous home, through 2026-05. Landlord Yuan Lee.
    ("Home Rent", CategoryKind.SPENDING, ("yuan lee", "; lee", "chk 3210")),
    # A card autopay that the bank bounced (ACH return R01, insufficient
    # funds). The card issuer reverses the payment, which appears on the card
    # as a charge for the payment amount alongside the +payment it undoes.
    # It is a transfer that failed, not consumption — but Monarch guesses a
    # category from the merchant string: "Insurance" on 2026-08-22 ($1,256,
    # Costco Citi), "Auto Payment" on 2025-12-22 ($2,414, same card).
    ("Returned card payment", CategoryKind.TRANSFER,
     ("autopay rtn", "insufficient fun")),
    # Bookings ON Airbnb are vacations — consumption, Travel & Vacation.
    # Monarch files some of them under "Investment - AirBnb Business", the
    # ledger for the Worldmark ownership, purely on the word (2026-06-16,
    # $464). Neel, 2026-09-11: "Airbnb is something I sometimes book for
    # vacation. Worldmark is an investment for future revenue in the form
    # of Airbnb." Outflows only: when the unit starts earning (2027), payouts
    # will arrive from the same merchant as INFLOWS and belong to the
    # investment ledger, not here.
    ("Travel & Vacation", CategoryKind.SPENDING, ("airbnb",), "out"),
    # The Worldmark ownership itself, and Onalani LLC, a pass-through payee
    # for Worldmark (Neel, 2026-09-11). Pinned here so a Monarch guess
    # ("Travel & Vacation", Uncategorized — both have happened) can never
    # move them out of the investment ledger.
    ("Investment - AirBnb Business", CategoryKind.BUSINESS,
     ("worldmark", "onalani")),
    # Chase's own savings <-> checking transfers are stamped "ODP TRANSFER"
    # (overdraft protection). Monarch reads "ODP" as Office Depot and filed
    # a $2,313 transfer as Shopping on 2026-04-10.
    ("Transfer", CategoryKind.TRANSFER, ("odp transfer",)),
    # Employer reimbursements. Neel, 2026-09-11: "AdamX deposits are all
    # reimbursements from my work, not a salary ... we won't know which
    # [purchases] are reimbursed, those are small amounts, so just
    # wholesale deduct it from my credit card expense." So the deposit is
    # a SPENDING-kind inflow that nets (NETTING_LABELS) — one visible
    # negative line in the month it lands — and never income.
    ("Work expenses (reimbursed)", CategoryKind.SPENDING,
     ("adamxai", "adamx inc"), "in"),
    # A friend: money to or from him settles shared dinners and activities
    # (Neel, 2026-09-11). Outflows are spending; inflows NET against it
    # (see NETTING_LABELS) — he is paying his half back, not paying Neel.
    ("Split bills", CategoryKind.SPENDING, ("ankur richhariya",)),
    # Zelle has two recurring payees that are spending, not transfers
    # (Neel, 2026-09-11). Fariba is the dog sitter (Monarch: Pets, once
    # Charity, once Transfer). Lianxiang Liu is the masseuse — the ~$25
    # weekly tip, which Monarch filed as Transfer and so never counted.
    ("Dog sitter", CategoryKind.SPENDING, ("fariba",), "out"),
    ("Massage", CategoryKind.SPENDING, ("lianxiang",), "out"),
]

#: One transaction that is really two. Matched by statement needle AND exact
#: amount, so it can only ever hit the one row it describes. Each part
#: carries its own label, kind and (optionally) the (year, month) it is for.
#: The DB row is never touched; the split happens at query time.
SPLIT_ROWS: list[dict] = [
    # 2026-05-20, $19,580 wire to the new landlord. Neel, 2026-09-11: "the
    # $19,580 was the deposit plus June rent." Rent is $9,000; the rest is
    # the security deposit — an asset held by the landlord, not spend.
    {
        "needle": "outgoing wire transfer to eric chang",
        "amount": 19580.00,
        "parts": [
            (9000.00, "Home Rent", CategoryKind.SPENDING, (2026, 6)),
            (10580.00, "Security deposit", CategoryKind.TRANSFER, None),
        ],
    },
]

#: Spending labels whose INFLOWS net against their outflows even without a
#: "Refund" statement: a friend settling a shared bill, an employer
#: reimbursing an expense filed as spending.
NETTING_LABELS = {"Split bills", "Work expenses (reimbursed)"}

#: Subscriptions Neel has said he cancelled, with the date he said so. Any
#: charge from the merchant after that date is flagged on the headline —
#: this is the "$10 to Yahoo" case, which he had spotted once and which
#: kept billing for a year under five different categories.
CANCELLED_SUBSCRIPTIONS: dict[str, date] = {
    "finance bronze": date(2026, 9, 11),   # Yahoo Finance Bronze, $9.95/mo
}

#: Labels a counterparty rule can produce.
COUNTERPARTY_LABELS = {rule[0] for rule in COUNTERPARTY_RULES}

#: Monarch account name -> (display name, fixed position). Accounts are
#: always shown in THIS order, never sorted by amount (project-kb:
#: canonical-account-hierarchy). Monarch's own names are opaque —
#: "CREDIT CARD (...2417)" is the Amazon card (403 Amazon rows) — so the
#: display name says what the account is for. Unknown accounts sort last,
#: alphabetically, under their raw name.
ACCOUNT_DISPLAY: list[tuple[str, str]] = [
    ("Robinhood Credit Card **8154 (...8154)", "Robinhood card"),
    ("Checking (...8935)", "Robinhood checking"),
    ("Savings (...7358)", "Robinhood savings"),
    ("Spending (...dabe)", "Robinhood spending (retired 2026-06)"),
    ("Home Expense 9486 (...9486)", "BofA home expense 9486"),
    ("Neel Salary 9487 (...9487)", "BofA salary 9487"),
    ("Neel Business Expense 9485 (...9485)", "BofA business 9485"),
    ("PREMIER SAVINGS (...3059)", "Chase savings 3059"),
    ("PREMIER PLUS CKG (...5973)", "Chase checking 5973"),
    ("Costco Anywhere Visa Card by Citi (...1453)", "Costco Citi card"),
    ("CREDIT CARD (...2417)", "Amazon card 2417"),
    ("CREDIT CARD (...5149)", "Card 5149 (deprecated)"),
    ("PayPal", "PayPal"),
]
ACCOUNT_ORDER = {name: i for i, (name, _) in enumerate(ACCOUNT_DISPLAY)}
ACCOUNT_NAMES = dict(ACCOUNT_DISPLAY)

#: Accounts that stopped on purpose. A retired account's dead tail is not a
#: freshness problem; every other account that stops is.
RETIRED_ACCOUNTS: dict[str, str] = {
    "Spending (...dabe)": "superseded by Checking (...8935) and Savings "
                          "(...7358) after the 2026-06 Robinhood reconnect",
    "CREDIT CARD (...5149)": "deprecated — Neel, 2026-09-11 (last row "
                             "2026-06-19)",
}

#: Lines that have appeared every month for 20 months. A month without one is
#: a data defect until proven otherwise (the July/August 2026 rent incident
#: above), so the summary flags it rather than quietly reporting a low total.
#: Checked against DISPLAY labels for complete months only. Also the lines
#: whose early payment (on/after the 25th) is attributed to the next month.
#:
#: NOT school: Stratford bills September through May and nothing over the
#: summer, so "Education" flagged June–August every year. Only add a line
#: here if it is genuinely due every calendar month.
EXPECTED_MONTHLY_LABELS = ("Home Rent",)

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
    # --- Neel, 2026-09-11 -------------------------------------------------
    # Costco is groceries (Monarch had split it Groceries 65 / Shopping 49).
    ("costco", "Groceries"),
    # People. Joann Riggio was a counselor Neel used; Denise Hall is Alisha's
    # English tutor (Monarch filed her under "Joann Riggio" and then under
    # "Dipti salary" — both person-named categories it invented).
    ("joann riggio", "Counseling"),
    ("denise hall", "Alisha's Education"),
    # "Yanghall" is Denise Hall's PayPal handle as it appears on the
    # Robinhood card. 2026-08-28: paid via PayPal-on-card with the wrong
    # PayPal option, she refunded (08-30), paid again from PayPal (08-28,
    # refunded 08-31), and finally on 09-01. One tutoring payment, three
    # attempts; the two refunds pair to zero here (Neel, 2026-09-11).
    ("yanghall", "Alisha's Education"),
    # Health, the three recurring lines Neel wants to see by name: the gym
    # (YMCA), massage (Cloud 9 Spa, both spouses), and medication
    # (Gifthealth — Neel's). Doctors and dentists stay in Medical / Dentist.
    ("ymca", "Gym"),
    ("cloud 9 spa", "Massage"),
    ("cloud spa burlingame", "Massage"),
    ("gifthealth", "Neel's Medication"),
    # Streaming — "Netflix, Hulu and others, those are the easy ones to
    # miss." Their own line, so every month shows what is still billing.
    ("netflix", "Streaming"),
    ("hulu", "Streaming"),
    ("spotify", "Streaming"),
    ("youtube", "Streaming"),
    ("audible", "Streaming"),
    ("disney", "Streaming"),
    # Paid reading. Yahoo Finance Bronze ("Finance Bronze", $9.95/mo) had
    # been filed under five categories; see CANCELLED_SUBSCRIPTIONS.
    ("finance bronze", "News"),
    ("stratechery", "News"),
    # AI tools (Monarch splits Anthropic between AI Tools and Software).
    ("anthropic", "AI Tools"),
    ("cursor", "AI Tools"),
    # Everything Tesla — charging, service, subscription — is the car.
    ("tesla", "Auto"),
    # Isha (yoga / Inner Engineering / Yatra) is Jaya's. Needles are the
    # program names, never bare "isha": "Alisha" contains it.
    ("isha inner", "Jaya Personal Expense"),
    ("isha child", "Jaya Personal Expense"),
    ("isha yoga", "Jaya Personal Expense"),
    ("isha life", "Jaya Personal Expense"),
    ("isha yatra", "Jaya Personal Expense"),
    ("isha jal", "Jaya Personal Expense"),
    ("isha pancha", "Jaya Personal Expense"),
    ("isha soak", "Jaya Personal Expense"),
    ("isha foundation", "Jaya Personal Expense"),
    # Jaya's executive coach for job interviews (Neel, 2026-09-11).
    ("talent sherpas", "Jaya's Education"),
]


# Whole-category remapping, for when Monarch's category is right about the
# rows but wrong about the grouping. Merchant overrides above beat these.
CATEGORY_RENAMES: dict[str, str] = {
    # Fuel is a running cost of the car, so it belongs with servicing rather
    # than in a category of its own (Neel, 2026-07-28: "all things auto").
    # Deliberately NOT merged: "Auto Payment" (a loan, debt service rather
    # than a running cost) and "Parking & Tolls".
    "Gas": "Auto",
    # Neel, 2026-09-11: one "Auto" line for the running cost of the cars.
    # Still separate: "Auto Payment" (the loan — debt service) and
    # "Parking & Tolls".
    "Auto Maintenance": "Auto",
    # Keep the per-person lines (Jaya Personal Expense, Jaya's Education,
    # Child Incentive) — Neel, 2026-09-11.
    # Person-named categories Monarch invented (Neel, 2026-09-11). Dipti was
    # the family's domestic help; Joann Riggio a counselor. Rows for other
    # people that landed in these are re-homed by merchant override first.
    "Dipti salary": "Household Help",
    "Joann Riggio": "Counseling",
    # Work spend Neel tagged for reimbursement, on the same line as the
    # reimbursements that net against it.
    "Adamx": "Work expenses (reimbursed)",
    "AdamX Work Trip - Vegas": "Work expenses (reimbursed)",
}


def counterparty_rule(merchant: str | None,
                      original_statement: str | None,
                      amount=None) -> tuple[str, CategoryKind] | None:
    """(label, kind) from COUNTERPARTY_RULES, or None if nothing matches."""
    haystack = f"{original_statement or ''} {merchant or ''}".lower()
    amt = float(amount) if amount is not None else 0.0
    for rule in COUNTERPARTY_RULES:
        label, kind, needles = rule[0], rule[1], rule[2]
        direction = rule[3] if len(rule) > 3 else None
        if direction == "out" and amt >= 0:
            continue
        if direction == "in" and amt <= 0:
            continue
        if any(n in haystack for n in needles):
            return label, kind
    return None


class RowClass:
    """How one Monarch row is treated by the Spending page.

    kind      what kind of money event it is (after the rulebook)
    label     the category it displays under
    is_refund a returned purchase that nets against its category
    counted   whether the Spending page includes it at all
    """
    __slots__ = ("kind", "label", "is_refund", "counted")

    def __init__(self, kind: CategoryKind, label: str, is_refund: bool,
                 counted: bool):
        self.kind = kind
        self.label = label
        self.is_refund = is_refund
        self.counted = counted


def classify(category: str | None, merchant: str | None,
             original_statement: str | None, amount) -> RowClass:
    """The ONE decision about a row, made in this order:

    1. Counterparty rule  -> the rule's kind and label, whatever Monarch's
                             category says (rent is spending even when filed
                             as Transfer; a bounced autopay is a transfer
                             even when filed as Insurance)
    2. Refund test        -> nets, whatever Monarch's category says
                             (only for rows Monarch filed as spending or
                             income; a refund inside a business or transfer
                             ledger stays with that ledger)
    3. Category kind      -> spending / income / transfer / business
    4. Display label      -> the rulebook (display_category)

    Steps 1 and 2 running BEFORE step 3 is the whole point. With the kind
    check first, a rent wire filed as "Transfer" and a refund filed as
    "Other Income" were both silently dropped — see COUNTERPARTY_RULES and
    is_refund for the two incidents. Every consumer of spending rows must go
    through this function so the page, the outflow reconciliation and the
    BBD model can never disagree about what a row is.
    """
    amt = float(amount) if amount is not None else 0.0
    cp = counterparty_rule(merchant, original_statement, amt)
    if cp is not None:
        label, kind = cp
    else:
        kind = kind_of(category)
        label = display_category(category, merchant, original_statement)

    refund = (is_refund(amt, original_statement, merchant)
              and kind in (CategoryKind.SPENDING, CategoryKind.INCOME)) \
        or (amt > 0 and label in NETTING_LABELS)

    if amt < 0:
        counted = kind == CategoryKind.SPENDING
    else:
        # Any other inflow — a deposit, a returned security deposit, a tax
        # refund — is excluded outright, never netted.
        counted = refund

    return RowClass(kind, label, refund, counted)


def display_category(category: str | None, merchant: str | None,
                     original_statement: str | None) -> str:
    """The category a row is shown under — the whole rulebook, in order.

    0. Counterparty rule      category-independent (see COUNTERPARTY_RULES)
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


# Trips: date-range-based classification. ALL spending within a trip's date
# range is treated as non-monthly (restaurants, rides, hotels, dog sitter),
# regardless of category. Windows are STAY dates, never booking dates.
# Lodging is usually booked days earlier, so a trip may also claim specific
# bookings by (date, merchant needle) — those rows join the trip too.
#
# Posting lag: "sometimes the food bills post earlier or after the trip,
# plus or minus 2 days" (Neel, 2026-09-11). So each window gets
# TRIP_POSTING_SLACK_DAYS of slack either side — but only for the kinds of
# spend a trip produces (TRIP_SLACK_LABELS), and only from merchants that are
# NOT part of the household's regular rotation (services.regular_merchants:
# seen on 6+ days in the last year). Inside the window itself everything
# counts, as before. Without both limits the slack days pulled in Blue
# Bottle, Cloud 9 and a $3,455 tutoring payment.
TRIP_POSTING_SLACK_DAYS = 2
TRIP_SLACK_LABELS = {
    "Restaurants & Bars", "Coffee Shops", "Groceries", "Taxi & Ride Shares",
    "Parking & Tolls", "Auto", "Travel & Vacation", "Entertainment & Recreation",
}
#: What a trip window may claim INSIDE the window: the spend a trip
#: produces. Fixed bills that merely fall on those dates — rent, tuition,
#: insurance, utilities, subscriptions, medical, fees, taxes — stay where
#: they are. Without this the three-week India window took March's rent
#: and read $21.9K; the Yosemite weekend took a tuition payment.
TRIP_LABELS = TRIP_SLACK_LABELS | {
    "Shopping", "Clothing", "Personal", "Massage", "Dog sitter", "Pets",
    "Electronics", "Gifts", "Miscellaneous", "Uncategorized", "Cash & ATM",
    "Split bills",
}
#: Keyed by the merchant's FIRST WORD, because Monarch spells one place
#: several ways ("Zareen's" / "Zareen's Restaurant & Catering"). Three
#: distinct days in a year is enough to be "the rotation".
REGULAR_MERCHANT_MIN_DAYS = 3

# Neel names vacations as they happen (2026-09-11); add the window then.
# To add: {"name": ..., "start": date(...), "end": date(...),
#          "bookings": [(date(...), "merchant needle"), ...]}
TRIPS = [
    {"name": "Vegas NYE 2025", "start": date(2025, 12, 28), "end": date(2026, 1, 1)},
    # Neel, 2026-09-11 (windows confirmed from the card's away-days).
    {"name": "Wedding anniversary — Yosemite",
     "start": date(2026, 1, 16), "end": date(2026, 1, 20)},
    {"name": "India 2026",
     "start": date(2026, 2, 23), "end": date(2026, 3, 18),
     "bookings": [(date(2026, 1, 22), "saudi arabian"), (date(2026, 1, 22), "expedia"),
                  (date(2026, 1, 24), "expedia"), (date(2026, 2, 25), "air india"),
                  (date(2026, 2, 27), "expedia")]},
    {"name": "Great Wolf Lodge",
     "start": date(2026, 4, 9), "end": date(2026, 4, 10)},
    # Neel, 2026-09-11. The Airbnb booked 08-11 ($1,051) is taken as the
    # Santa Cruz stay and the one booked 08-12 ($744) as Woodside — the
    # two bookings, two weekends; swap if wrong.
    {"name": "Jaya's birthday weekend — Santa Cruz",
     "start": date(2026, 8, 15), "end": date(2026, 8, 16),
     "bookings": [(date(2026, 8, 11), "airbnb")]},
    # Airbnb split the Woodside payment: $744 on 08-12 and $744 on 08-14,
    # same reservation (HMCCR4MMYE). Monarch delivered only the first;
    # the second came from the Robinhood card download.
    {"name": "Rakhi celebration — Woodside",
     "start": date(2026, 8, 29), "end": date(2026, 8, 30),
     "bookings": [(date(2026, 8, 12), "airbnb"), (date(2026, 8, 14), "airbnb")]},
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
