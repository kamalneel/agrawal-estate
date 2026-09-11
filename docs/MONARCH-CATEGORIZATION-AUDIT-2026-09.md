# Monarch Categorization Audit (2026-09-11)

Why: Neel stopped recategorizing in Monarch about a year ago, when he
started handing the export to Claude instead. Monarch's auto-categorization
has drifted since. This audit measures the drift and feeds the `/monarch`
skill (`.claude/commands/monarch.md`), which applies the mapping on every
future export. Numbers from the live DB, 2026-09-11.

Two purposes the mapping serves (Neel):

1. **How much am I spending, on what.**
2. **Catch the mistakes** — a subscription forgotten and still billing
   (the "$10 to Yahoo" case), a transfer read as a purchase, a refund read
   as income.

## Findings

### F1. The Yahoo subscription is still billing

"Finance Bronze" ($9.95, monthly on the 25th/26th, Robinhood card) is
`YAH*FINANCE BRONZE` — Yahoo Finance Bronze. Neel found it once and meant
to cancel; it has charged every month through 2026-08-26 ($119/yr). Monarch
has filed it under five different categories (Financial & Legal Services,
Financial Fees, Loan Repayment, Auto Maintenance, Miscellaneous), which is
exactly how a small recurring charge hides.

### F2. Recurring charges (subscription detector, Sep 2025 → Sep 2026)

Monthly cadence, steady amount, ≥ 4 charges:

| $/yr | Charge | Merchant | Category today | Last |
|---|---|---|---|---|
| 1,282 | 106.84 | AT&T | Internet & Cable | 09-03 |
| 363 | 30.25 | AGI Insurance (renters/condo) | Insurance | 08-25 |
| 300 | 25.00 | Chase monthly service fee | Financial Fees | 03-17 (stopped) |
| 276 | 22.99 | YouTube | Entertainment | 08-25 |
| 228 | 18.99 | Spotify | Entertainment | 09-07 |
| 216 | 17.99 | Netflix | Entertainment | 09-01 |
| 180 | 15.00 | Stratechery | Software | 09-07 |
| 179 | 14.95 | Audible | Entertainment | 08-17 |
| 119 | 9.95 | Yahoo Finance Bronze | five categories | 08-26 |
| 96 | 4.00 ×2 | News Laundry (two PayPal subscriptions?) | News | 08-18 |

Total ≈ $3,240/yr of subscriptions, none of them grouped anywhere on the
page today. (Stratford and the dance class also match the pattern but are
tuition, not subscriptions.)

### F3. Transfers filed as spending

- 2026-04-10 $2,313 "ODP TRANSFER TO CHECKING …5973" from Chase savings →
  **Shopping / Office Depot**. It is Chase's overdraft-protection transfer;
  the matching +$2,313 sits in Chase checking as Transfer. Fixed by rule.
- 2026-08-22 $1,256 and 2025-12-22 $2,414 bounced Citi autopays →
  **Insurance / Auto Payment**. Fixed by rule (returned card payment).
- Rent wires to the landlord → **Transfer** (Jul/Aug 2026). Fixed by rule.

### F4. Refunds filed as income

Eleven in 2026 ($13.3K): airline refunds (Emirates $3,896, Saudia $1,788,
Blue Lagoon, Icelandia), the two $3,455 Denise Hall / Yanghall reversals,
Perkins and Presidential real-estate application refunds. All under
"Other Income" or "Business Income". Fixed by rule; flagged on the
headline until corrected in Monarch.

### F5. Person-named and orphan categories

| Category | Rows | $ | What's in it |
|---|---|---|---|
| Joann Riggio | 6 | 4,775 | five $240–360 card charges to Joann Riggio in 2025; one $3,455 "Payment to Denise Hall" (PayPal, 2026-08-28) |
| Dipti salary | 1 | 3,455 | the re-sent "Payment to Denise Hall" (2026-09-01) |
| Adamx | 5 | 635 | Jan 2025: a $500 Zelle to Ankur Richhariya, Target, Smart & Final, Dollar Tree, New India Bazar, and an +$80 Mercury ACH from AdamXai |
| Jaya Personal Expense | 9 | 4,489 | CPA exam, Isha Life, Isha Yatra Kailash, Yogiplate |
| Jaya's Education | 3 | 1,289 | Kipling, LinkedIn, Tuition Web |
| Child Incentive | 1 | 96 | one Target charge |
| Check | 1 | 224 | check #609 |
| Loan Repayment | 3 | 775 | Finance Bronze, Plentea, Stratford — none of them a loan |
| Cash & ATM | 7 | 2,493 | mostly BofA rows that are now filed Transfer |
| ONE TIME | 5 | 86,476 | Subaru, IRS, FTB, ICICI wire, Tesla |
| ANNUAL EXPENSES | 7 | 1,488 | DMV, Monarch subscription |

### F6. Merchants split across categories (2026)

| Merchant | 2026 $ | Split |
|---|---|---|
| Costco | 12,273 | Groceries 29 / Shopping 6 |
| Zelle | 8,317 | Transfer 28 / Pets 6 / Rent, Hartstene, Charity 1 each |
| Amazon | 4,261 | Shopping 131 / Gifts, Furniture, Misc 1 each (rulebook already merges) |
| Red Rock Volleyball | 4,260 | Entertainment 4 / Education 1 (rulebook already merges) |
| Tesla | 1,144 | Auto Maintenance 18 / Auto Payment 2 / loan 1 / Uncategorized 2 |
| Anthropic | 842 | Software 11 / AI Tools 9 |
| Bikanervala | 215 | Restaurants 4 / Travel 4 |
| LinkedIn | 260 | Software 6 / Jaya's Education 1 |

### F7. Category drift, manual era (≤ Jun 2025) vs now

| Merchant | Was | Now |
|---|---|---|
| Costco | Shopping | Groceries |
| Expedia | Europe Trip 2025 | Travel & Vacation |
| PayPal | Personal | Transfer |
| Stratford School | Loan Repayment | Education |
| Stripe | Entertainment | Financial & Legal |
| Panda Express, Lyft, Curb | trip categories | Restaurants / Taxi |

The trip categories are the visible loss: in the manual era a trip's
restaurants, rides and hotels were tagged to the trip ("Europe Trip 2025",
96 rows, $10.2K). Nothing in 2026 is tagged that way; the page's only trip
window is Vegas NYE. The June 2026 Iceland trip (Blue Lagoon, Icelandia,
Emirates) and the July 4 San Francisco day are spread across ordinary
categories.

### F8. Uncategorized

27 rows, $4.4K all time, $3,455 of it the refunded Yanghall charge. The
rest is Isha classes ($350), Fisherman's Wharf on Jul 4 ($200), Fox One,
Cursor, USPS, Tesla ($9.99 ×2).

## Decisions taken (in `spending/models.py` COUNTERPARTY_RULES)

- Landlord wires → Home Rent, spending.
- Returned card autopay → transfer.
- Airbnb bookings (outflows) → Travel & Vacation; Worldmark and Onalani →
  the investment ledger.
- "ODP TRANSFER" → transfer.
- Refunds net whatever category Monarch chose.

## Answered 2026-09-11 (encoded; see the `/monarch` skill)

- Joann Riggio: a counselor Neel used → Counseling. Denise Hall: Alisha's
  English tutor → Alisha's Education. Dipti: domestic help → Household
  Help. Ankur Richhariya: a friend, split bills, inflows net.
- AdamX is the employer; its deposits are reimbursements of personally
  paid expenses, not salary. The Adamx-tagged spend and the reimbursements
  are transfers. **Note:** reimbursements received total ~$25.7K (Mercury
  $10.2K, AdamX Inc $15.4K) against only ~$1.2K of Adamx-tagged spend, so
  most reimbursed expenses still sit in ordinary categories and count as
  personal spending — open question below.
- Costco → Groceries. Yahoo Finance Bronze → cancelled (flag if it charges
  again). Subscriptions categorized individually, with Streaming and News
  as their own lines. Health as three named lines: Gym, Massage,
  Medication.

## Answered 2026-09-11, second round (encoded)

- Reimbursed work expenses cannot be identified individually ("small
  amounts"); AdamX deposits are deducted wholesale as one negative line,
  "Work expenses (reimbursed)", in the month they land. The Sep 9 $15,448
  deposit takes September from $20.5K to $5.2K — lumpy by design.
- Per-person lines stay. Isha programs → Jaya Personal Expense.
- Trips roll up by stay-date window; Neel names future vacations.
- Anthropic and Cursor → AI Tools. Tesla, fuel, service → Auto.
- The $19,580 wire: June rent $9,000 + deposit $10,580, split at query
  time; deposits are transfers.
- Card 5149 deprecated (retired list).
- Zelle: Fariba → Dog sitter ($1,270 in 2026); Lianxiang Liu → Massage
  (the weekly tip, $20–50 since July, previously filed Transfer and never
  counted).

## Still open

1. ~~2026 trip windows~~ Confirmed and encoded: Yosemite Jan 16–20, India
   Feb 23–Mar 18, Great Wolf Lodge Apr 9–10, Santa Cruz Aug 15–16,
   Woodside Aug 29–30. Iceland (June) cancelled; the $463.68 Airbnb booked
   06-16 shows no refund. Trip windows take trip-shaped spend only
   (`TRIP_LABELS`), claim their bookings explicitly, and allow ±2 days of
   posting slack for non-regular food/ride merchants.
2. **Zelle to people filed as Transfer** — spending or not? Dena Baez
   ($340, May 26), Manjit Kaur ($180, May), Baltazar Arroyo ($150, Jun
   22), Yomara Lopez de Morales ($150, Jan 2025), Anoop Kohli ($47), Jay
   Prakash ($100).
