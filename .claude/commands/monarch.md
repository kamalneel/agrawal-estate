# Monarch — import a transaction export and apply Neel's mapping

Run this whenever Neel hands over a Monarch transaction CSV (usually a
path under `~/Delete/Transactions_<timestamp>.csv`). The job is not just
to load rows: it is to make the data say what Neel wants to see, and to
surface the things he keeps this ledger to catch. Two purposes, in his
words:

1. **"How much am I spending, on what."**
2. **"Transactions that are there by mistake"** — a subscription he forgot
   to cancel and is still paying (the $10/month Yahoo case), a transfer
   read as a purchase, a refund read as income.

Neel stopped recategorizing inside Monarch in 2025. Monarch's own guesses
have drifted since (`docs/MONARCH-CATEGORIZATION-AUDIT-2026-09.md`). The
mapping now lives in code and is applied at query time, so **never rewrite
`spending_transactions` rows** (project-kb: no-direct-db-modifications).
The rulebook is `backend/app/modules/spending/models.py`:

- `COUNTERPARTY_RULES` — category-independent: names a counterparty or
  statement pattern and fixes both kind and label (landlord wires → Home
  Rent; bounced autopay → transfer; Airbnb bookings → Travel & Vacation;
  Worldmark / Onalani → the investment ledger; ODP transfers → transfer).
- `MERCHANT_CATEGORY_OVERRIDES`, `CATEGORY_RENAMES`, `RENT_SPLIT_RULES`,
  `TRIPS`, `NON_MONTHLY_CATEGORIES`, `EXPECTED_MONTHLY_LABELS`.
- `is_refund` — a "Refund…" row nets whatever category Monarch chose.
- Everything goes through `classify()`; every page and model reads
  `services.spending_rows()`. One definition.

## Steps

1. **Inspect before importing.** Row count, date range, per-account
   date range (accounts absent from the export are left untouched by the
   importer). Compare the range against `SELECT MAX(transaction_date)
   FROM spending_transactions` and against `/api/v1/spending/freshness`.
   If the export starts after existing coverage ends, there is a gap —
   say so and ask for an export that overlaps by at least a week.
2. **Dry-run** `backend/scripts/import_monarch_spending_csv.py <csv>`
   (dry by default). Read the output for: account renames the
   `ACCOUNT_ALIASES` map does not know (a "new" account appearing beside
   a dead one — extend the map, never import both); double-listed
   brokerage transfers being collapsed; rows kept in gaps. Then `--save`.
   Copy the file to `data/processed/spending/monarch/` with a descriptive
   name (`<from> to <to> Transactions from Monarch.csv`).
3. **Verify coverage.** `services.get_freshness()` — every account live
   or retired, no lagging feed; `find_holes()` for the months covered — no
   hole in the card. Weekly row counts per account for the last three
   months should show no empty week for the card.
4. **Run the mapping audit on the new rows** (the checks below) and fix
   what has a standing decision; ask about what does not.
5. **Report**: period totals as the page now shows them, what the rules
   changed, the subscription list, and the questions.

## The mapping audit (every import)

Run these against the newly imported date range. Each has a standing
decision or a question.

| Check | What to look for | Action |
|---|---|---|
| Refunds as income | positive rows whose statement starts "Refund" under Other/Business Income | rule already nets them; list them so Neel fixes Monarch |
| Transfers as spending | outflows > $1,000 in a spending category whose statement says transfer / wire / autopay / ODP / ACH withdrawal to own account | add a `COUNTERPARTY_RULES` entry if the pattern is new |
| Bounced payments | "RTN", "INSUFFICIENT", "RETURN CHECK FEE" | reversal is a transfer (rule); the fee is spending; **tell Neel which account bounced and whether the bill was re-paid** |
| Person-named / one-off categories | a category that is a person's name or appears < 3 times | ask what it is; map to a real category or a business ledger |
| Split merchants | one merchant under two or more categories in the period | apply the standing decision or add an override |
| Uncategorized | rows with no category | seed known chains in `import_rh_spending_csv.SEED_CATEGORIES`; leave unknowns visible |
| Missing recurring | a complete month without Home Rent | data defect until proven otherwise (project-kb rule) |
| Subscriptions | same merchant, monthly cadence, steady amount (run the detector in the audit doc) | list every one with $/yr and last charge; **flag any Neel has not confirmed he still wants** |
| New merchants > $500 | first-ever appearance | name them in the report |

## Standing decisions

Recorded as Neel gives them; the rulebook encodes them. Add here first,
then in code.

- **Rent** is identified by landlord (Eric Chang from 2026-06; Yuan Lee
  before), never by Monarch's category. Paid on/after the 25th → next
  month.
- **Worldmark** is the investment made for future Airbnb revenue; its
  ledger is "Investment - AirBnb Business" (kind BUSINESS, netted on the
  Income page). **Onalani LLC** is a pass-through payee for Worldmark —
  same ledger. Nothing from Airbnb itself appears yet; when payouts start
  they are inflows to this ledger.
- **Bookings on Airbnb** are family vacations → Travel & Vacation.
- **A refund is a refund** whatever category Monarch put it in.
- **A bounced card autopay** is a transfer; the return fee is spending.
- **Chase "ODP TRANSFER"** rows are transfers, not Office Depot.
- **School (Stratford)** bills September–May; a missing summer month is
  not a defect.
- Amazon, Blue Bottle, City of Palo Alto, Red Rock Volleyball, Gas →
  see `MERCHANT_CATEGORY_OVERRIDES` / `CATEGORY_RENAMES`.
- **Security deposits are an asset, not spend.** The 2026-05-20 $19,580
  wire to Eric Chang was June's rent ($9,000) plus the deposit ($10,580);
  it is split at query time (`SPLIT_ROWS`), rent attributed to June, the
  deposit a transfer. Use `SPLIT_ROWS` for any future one-row-two-things
  case; match on statement plus exact amount so it can only hit that row.
- **Costco** is Groceries, always.
- **People.** Joann Riggio was a counselor → Counseling. Denise Hall is
  Alisha's English tutor → Alisha's Education; she is paid through PayPal
  and appears as "Yanghall" when the PayPal payment rides the Robinhood
  card — same person, same line. Dipti was domestic help →
  Household Help. Ankur Richhariya is a friend; money either way settles
  shared dinners/activities → Split bills, inflows net.
- **AdamX** is Neel's employer. Deposits from AdamX (Mercury ACH, "AdamX
  Inc") are reimbursements of expenses Neel paid personally, never salary
  or income. We cannot tell which purchases were reimbursed ("small
  amounts"), so the deposit is deducted wholesale: it appears as one
  negative "Work expenses (reimbursed)" line in the month it lands and
  nets against spending. Adamx-tagged spend sits under the same line.
- **Zelle payees that are spending:** Fariba → Dog sitter; Lianxiang Liu
  → Massage (the weekly tip). Any other Zelle to a person filed as
  Transfer is suspect — ask.
- **Per-person lines stay** (Jaya Personal Expense, Jaya's Education,
  Child Incentive). Isha programs → Jaya Personal Expense. Talent Sherpas
  (Jaya's executive coach for job interviews) → Jaya's Education.
- **AI Tools:** Anthropic, Cursor. **Auto:** one line for the cars' running
  costs (Tesla, fuel, service); Auto Payment (the loan) and Parking &
  Tolls stay separate.
- **Card 5149 is deprecated** (retired list).
- **Trips roll up by date window** (`TRIPS`): everything in the window —
  restaurants, rides, hotels — counts as the trip, non-monthly. Neel will
  name future vacations as they happen; add the window then. Stay dates,
  never booking dates; a trip lists its lodging bookings by (date,
  merchant) to claim them; an explicit booking beats any other trip's
  window. Inside the window a trip takes only trip-shaped spend
  (`TRIP_LABELS`: food, rides, fuel, lodging, shopping, personal care,
  the dog sitter) — rent, tuition, insurance, utilities, subscriptions,
  taxes and one-time items that merely fall on those dates stay put (the
  first pass gave Yosemite a $10,000 FTB payment and India a month's
  rent). Food bills post ±2 days around a trip, so a window has 2 days
  of slack either side, limited to food / rides / fuel / entertainment
  from merchants outside the household's regular rotation. Refunds never
  join a trip by date, only by reversing a charge that is in it. After
  adding a trip, print the slack-day rows it claimed and show them to
  Neel — the data carries no city, so a local restaurant two days after
  a trip is indistinguishable from a trip one.
- **2026 trips recorded** (Neel, 2026-09-11): Yosemite Jan 16–20 (wedding
  anniversary); India Feb 23–Mar 18 with flights booked Jan 22, Jan 24,
  Feb 25, Feb 27; Great Wolf Lodge Apr 9–10; Santa Cruz Aug 15–16 (Jaya's
  birthday, Airbnb booked Aug 11); Woodside Aug 29–30 (Rakhi, Airbnb
  booked Aug 12). Iceland (June) was cancelled.
- **Subscriptions are NOT one line.** Categorize each by what it is, and
  give the easy-to-miss ones their own visible line: Streaming (Netflix,
  Hulu, YouTube, Spotify, Audible, Disney), News (Stratechery, Yahoo
  Finance).
- **Health, three recurring lines by name:** Gym (YMCA), Massage (Cloud 9
  Spa, both spouses), Medication (Gifthealth). Doctors/dentists stay in
  Medical / Dentist.
- **Cancelled subscriptions** go in `CANCELLED_SUBSCRIPTIONS` with the
  date; any later charge is a red flag on the headline. Yahoo Finance
  Bronze: cancelled per Neel 2026-09-11 (it had charged through 08-26).

### Awaiting Neel's answer

Zelle payees filed as Transfer — spending or not: Dena Baez, Manjit
Kaur, Baltazar Arroyo, Yomara Lopez de Morales, Anoop Kohli, Jay Prakash.
The $463.68 Airbnb of 06-16 (cancelled Iceland trip) shows no refund. Zelle payees filed as Transfer: Dena Baez, Manjit
Kaur, Baltazar Arroyo, Yomara Lopez de Morales, Anoop Kohli, Jay Prakash.

## Gap fill from Robinhood's own downloads

When Monarch has a hole (a dropped feed: the card empty for a stretch
inside a month), ask Neel for the Robinhood card / checking / savings CSV
and run `backend/scripts/import_rh_spending_csv.py <csv…>`. It imports
only rows after existing coverage or inside a detected hole, with a
same-amount ±3-day check, and tells checking from savings by content.
Monarch remains the categorization authority everywhere it has rows.

## Never

- Never publish anything outside this repo.
- Never edit rows in the DB to fix a category — add a rule.
- Never call a quiet account "lagging" by a flat threshold; freshness is
  judged against each account's own rhythm, and statement-fed streams by
  whether the last complete month is in.
