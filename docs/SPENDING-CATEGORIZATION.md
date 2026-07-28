# Spending Categorization Principles

Living document for classifying Monarch Money categories.

## Two axes (revised 2026-07-26)

`spending_transactions` is fed by Monarch, which aggregates **every**
non-brokerage account. It is therefore a *transactions* table, not a spending
table — money flows both ways through it. Classification happens on two
independent axes.

### Axis 1 — what kind of money event is this? (`models.CategoryKind`)

| Kind | Meaning | Destination |
|------|---------|-------------|
| `SPENDING` | Consumption | Spending page. Negative = spend; **positive = refund and nets against its category** |
| `INCOME` | Earnings | Income page |
| `TRANSFER` | Movement between your own accounts | Nowhere — counting it either way inflates both sides |
| `BUSINESS` | Income-producing asset whose two sides share one category | Income page, **netted** into one stream |

**Classify by category, never by sign.** A positive amount is three different
things depending on the category — a tenant's rent (INCOME), a returned
jacket (SPENDING refund), or a transfer between accounts (TRANSFER) — and the
sign cannot tell them apart. Sign means direction *within* a kind, which is
all a sign should ever mean.

> **Why this replaced the old three-tier model.** The old model had one
> `EXCLUDED` bucket for transfers, income *and* businesses, plus an
> `amount < 0` filter on every query. Consequences, all found on 2026-07-26:
> a paid-off rental netting **+$65,108** was reported as a **$13,921 expense**;
> **$167,152** of inflows in non-excluded categories were silently dropped;
> and ~$9K of refunds never reduced any category, so every total overstated
> real spend. `EXCLUDED_CATEGORIES` still exists but is now *derived* from
> `CATEGORY_KINDS`, so the two cannot drift.

### Axis 2 — cadence (SPENDING only)

| Tier | Treatment |
|------|-----------|
| `NON_MONTHLY` | Counted in totals, charts and tables; excluded from "Avg Monthly" |
| `MONTHLY` | Everything else — the default |

## The rulebook (added 2026-07-28)

Monarch's own categories are frequently not the ones Neel wants to see. Rather
than editing them by hand every export, corrections live as **rules applied at
query time**, in `spending/models.py :: display_category`.

**They apply to every future Monarch import automatically.** Nothing is
rewritten in `spending_transactions`, so Monarch stays the source of truth
(playbook: `no-direct-db-modifications`) — and because the rules run when the
page is read, editing one re-labels all history *and* every future import in
the same instant. No reprocessing, no backfill.

Four layers, most specific first:

| # | Rule | Where | Example |
|---|------|-------|---------|
| 1 | **Merchant override** | `MERCHANT_CATEGORY_OVERRIDES` | `red rock volleyball` → `Alisha's Education` |
| 2 | **Rent split** | `RENT_SPLIT_RULES` | payee Eric Chang / Yuan Lee → `Home Rent`; letting agents & movers → `Home Search & Moving` |
| 3 | **Category rename** | `CATEGORY_RENAMES` | `Gas` → `Auto Maintenance` |
| 4 | Monarch's own category | — | the default |

### Current rules

| Rule | Effect | Why |
|------|--------|-----|
| `red rock volleyball` → `Alisha's Education` | $4,260 (2026) out of Entertainment & Recreation | Monarch had it in two categories at once — 4 rows in E&R, one already moved to Education |
| `city of palo` → `Home Utility` | $16,873 renamed from Gas & Electric | The city bills power, water and refuse together |
| `amazon` → `Amazon` | $10,170 / 371 rows out of Shopping (+ Misc, Furniture, Gifts) | Too big to bury; Shopping told you nothing |
| `blue bottle` → `Blue Bottle` | $1,685 / 180 rows out of Coffee Shops | 36% of the category on its own |
| `Gas` → `Auto Maintenance` | Fuel joins servicing | "All things auto" |
| Rent payees → `Home Rent` | Both homes on one line, no address | Neel knows which house he lives in |

### Writing a new rule — the substring trap

Matching is a case-insensitive substring on the **merchant only**. Pick a
needle that cannot catch a neighbour:

- `red rock volleyball`, **not** `red rock` — the latter also catches Red
  Rock *Coffee*, an unrelated $6.25 coffee shop.
- `city of palo`, **not** `palo alto` — the latter also catches a dentist
  ($6,796), Palo Alto Bagels, and other merchants that merely sit in the city.

If a correction later gets made in Monarch itself, delete the rule here and
Monarch's category flows through unchanged.

## Rules for classifying a new category

1. Is it movement between your own accounts? → `TRANSFER`
2. Is it earnings? → `INCOME`
3. Is it an asset that both earns and costs, under one category? → `BUSINESS`
4. Otherwise → `SPENDING`, then pick a cadence: once a year or less, or a
   large one-off → `NON_MONTHLY`; else `MONTHLY`.

Unlisted categories default to `SPENDING` / `MONTHLY`. That default is
deliberate: a new Monarch category is far likelier to be an expense than
anything else, and a misfiled expense is a visible number rather than a
silent omission.

## Full Category Table

### EXCLUDED (not spending)
Defined in `models.py :: EXCLUDED_CATEGORIES`

| Category | Reason |
|----------|--------|
| Transfer | Internal money movement |
| Credit Card Payment | Debt repayment, not spending |
| Paychecks | Income |
| Interest | Income |
| Loan from Neel's Investment | Internal transfer |
| Other Income | Income |
| Business Income | Income |
| Balance Adjustments | Not real spending |
| Investment | Not spending |
| Jaya's Salary | Income |
| Loan Repayment | Debt, not spending |
| Tesla's loan payment | Debt payment |

> ⚠️ **Apostrophes must be listed twice.** Monarch exports curly apostrophes
> (`’`, U+2019) in user-created category names, but these constants were
> written with straight ones (`'`). Membership is exact-string
> (`category NOT IN :excluded`), so a single-spelling entry silently lets the
> category count as spending. Any category with an apostrophe belongs in
> `EXCLUDED_CATEGORIES` under **both** spellings. Found 2026-07-25:
> `Tesla’s loan payment` (2 rows, $669) had been counting as spend.

### NON_MONTHLY (annual / one-time)
Defined in `models.py :: NON_MONTHLY_CATEGORIES`

| Category | Reason |
|----------|--------|
| Taxes | Annual estimated/quarterly tax payments |
| Insurance | Annual or semi-annual premiums |
| Travel & Vacation | Lumpy, trip-based spending |
| ANNUAL EXPENSES | Explicitly tagged annual |
| ONE TIME | Explicitly tagged one-time |
| AdamX Work Trip - Vegas | Trip tag, one-time |
| Bali trip | Trip tag, one-time |
| Europe Trip 2025 | Trip tag, one-time |
| India Trip 2024 | Trip tag, one-time |

### MONTHLY (recurring)
All other categories default to MONTHLY.

| Category | Notes |
|----------|-------|
| Auto Maintenance | |
| Auto Payment | |
| Cash & ATM | |
| Charity | |
| Child Activities | |
| Child Incentive | |
| Clothing | |
| Coffee Shops | |
| Dentist | |
| Education | |
| Electronics | |
| Entertainment & Recreation | |
| Financial & Legal Services | |
| Financial Fees | |
| Fitness | |
| Furniture & Housewares | |
| Gas | |
| Gas & Electric | Utility |
| Gifts | |
| Groceries | |
| Home Improvement | |
| Internet & Cable | Utility |
| Medical | |
| Miscellaneous | |
| News | Subscription |
| Parking & Tolls | |
| Personal | |
| Pets | |
| Phone | Utility |
| Public Transit | |
| Rent | |
| Restaurants & Bars | |
| Shopping | |
| Software | Subscription |
| Taxi & Ride Shares | |
| Uncategorized | |

### Additional MONTHLY categories (from 2025 CSV custom tags)

| Category | Notes |
|----------|-------|
| AI Tools | Subscription software |
| Adamx | Business expense |
| Jaya Personal Expense | |
| Jaya's Education | |
| Joann Riggio | Payee-as-category |
| 303 Hartstene Dr | Property expense |

### New in the 2026-07-25 Monarch export

| Category | Rows / 2026 | Tier | Notes |
|----------|-------------|------|-------|
| Child Care | 2 / $100 | MONTHLY | Rule 3 default |
| Check | 1 / $224 | MONTHLY | Rule 3 default; revisit if checks become common |
| Business Income | 1 / −$40 | EXCLUDED | Income |
| Tesla’s loan payment | 2 / $669 | EXCLUDED | Curly-apostrophe twin of the existing entry |
| Investment - AirBnb Business | 5 / $8,090 | EXCLUDED | Capital deployment, not consumption — see below |

#### `Investment - AirBnb Business` (resolved 2026-07-25, Neel)

Excluded from spending. It is an investment that happens to bill monthly:
costs run through 2026 with **no offsetting revenue until 2027**, at which
point Airbnb income becomes a new stream alongside rental and investment
income. Treating it as household spending would overstate consumption for a
year and then leave the revenue stranded on the income side.

**It is not invisible — it moved, it didn't vanish.** As of 2026-07-25 it
renders on the **Income page** as a `fixed` stream that reads negative until
2027 revenue starts. The exclusion here is what makes that safe: because the
category is in `EXCLUDED_CATEGORIES`, a row cannot be counted on both pages.
Both modules import `spending.models.AIRBNB_CATEGORY` rather than repeating
the string, so the two views cannot drift apart.

See [INCOME-UNIFICATION-SPEC.md](INCOME-UNIFICATION-SPEC.md) → *Pre-revenue
streams* for the sign convention and the 2027 revenue decision.

## Trip-Based Classification

In addition to category-based classification, spending can be classified by **date range** using the `TRIPS` list in `models.py`. ALL spending within a trip's date range is treated as non-monthly, regardless of Monarch category (e.g., dog sitter, restaurants, gas during a trip).

To add a new trip, tell Claude the dates and destination:
> "March 14-28, Bali"

This gets added to `models.py :: TRIPS` as:
```python
{"name": "Bali Trip", "start": date(2025, 3, 14), "end": date(2025, 3, 28)}
```

### Current Trips

| Trip | Start | End |
|------|-------|-----|
| Vegas NYE 2025 | 2025-12-28 | 2026-01-01 |

### Priority Rules
- Trip date range takes priority over category classification
- A "Groceries" transaction during a trip counts toward the trip, not monthly groceries
- NON_MONTHLY categories still apply for transactions outside any trip date range

## Changelog

| Date | Change |
|------|--------|
| 2026-02-06 | Initial categorization. Created three-tier system. EXCLUDED: 11 categories. NON_MONTHLY: 9 categories. All others default to MONTHLY. Added 2025 CSV custom categories to appropriate tiers. |
| 2026-02-06 | Added trip-based date-range classification. Vegas NYE 2025 (Dec 28 - Jan 1). Annual expenses breakdown in summary API and frontend. |
| 2026-07-25 | 2026 YTD Monarch export imported. Fixed curly-apostrophe exclusion bug (`Tesla’s loan payment`). Added `Business Income` → EXCLUDED. New categories `Child Care`, `Check` → MONTHLY by default. `Investment - AirBnb Business` ($8,090) left MONTHLY pending Neel's call. |
