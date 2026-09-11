# Spending Page — Audit (2026-09-06)

Question the audit was run against: **"How am I spending my money?"**
Method: [PAGE-DESIGN-PLAYBOOK.md](PAGE-DESIGN-PLAYBOOK.md); spec under audit:
[SPENDING-PAGE-SPEC.md](SPENDING-PAGE-SPEC.md). Every number below was
pulled from the live Postgres on 2026-09-06.

## Status — fixed the same day (2026-09-06)

| # | Finding | Done |
|---|---|---|
| D1 | Rent excluded since June | `COUNTERPARTY_RULES` run before kind; July $18,429, Aug $24,792 (Jul 31 wire attributed to August). Monarch category still says Transfer — fix there too. |
| D2 | Refunds filed as income | Refund test runs before kind; 11 refunds in 2026 ($13.3K) now net, paired to the charge they reverse. Flagged on the headline until recategorized in Monarch. |
| D3 | Outflows dead since Jul 20 | Statement importer now imports cash codes (sign from Debit/Credit column, cross-checked); July + August imported, tail 2026-08-26. |
| D4 | Monarch double-lists transfers | Importer collapses the terse twin; August re-imported. July's pairs (Jul 4/6/7/31) need the July export re-run. |
| D5 | Two outflow definitions | `/cash-flow/*` deleted with its three panels; `/outflows` is the reconciliation line only. |
| D6 | Month categories ≠ headline | Every category listed; non-monthly grouped under a subtotal; footer = headline. |
| D7 | Category drill broken | `/transactions` and `/filters` use display labels. |
| D8 | BBD's own definition | BBD calls `monthly_spending_totals()`. |
| D9 | One global freshness date | `/freshness`: per-account tails over all history, retired list, outflow tail, last complete month (the default period). Two-sided amber. |
| D10 | Loose ends | Uncategorized and misfiled-refund counts on the headline. Deposits still count as rent (open: is the $19,580 deposit + June rent?). `/categories`, `/trends` deleted. |
| UI | Tokens | Page and stylesheet rebuilt on `tokens.css`; zero literal colours. |

Not yet built: L2 baselines beyond "vs average recurring month", the
category → group map, and the by-month-by-group stacked chart (Part 3).
Open for Neel: whether Card 5149 is retired (dead since 06-19), the June
rent flag (deposit wire covered it?), and recategorizing D1/D2 in Monarch.

## Verdict

The categorized (Monarch) side is close to right and is the right headline.
Three things make the page wrong today, and the rest of the page is built
around the wrong quantity:

1. **Rent has been missing since June.** Two $9,000 wires to the landlord
   (Jul 6, Jul 31) are filed as `Transfer` in Monarch and drop out. July
   reads $9,461; it is ~$18,500.
2. **August is overstated by $6,910** of charges that were fully refunded
   two days later, because the refunds were filed as *income* and the
   income filter runs before the refund check.
3. **The brokerage-outflow side has been dead since Jul 20** and has no
   refresh path: the statement importer deliberately skips cash movements,
   and no activity CSV has landed since early July.

Beyond the data, six of the page's eight panels show *money leaving the
brokerage* (funding), not spending — a second definition on the same
screen, using a third query that disagrees with the first two. The page
answers "what left Robinhood" well and "how am I spending" poorly.

---

## Part 1 — Data findings

Ranked by effect on the number you see.

### D1. Rent is excluded from spending since June 2026 — HIGH

| date | row | Monarch category | counted? |
|---|---|---|---|
| 2026-01 → 05 | $8,000/mo to Yuan Lee (CHK 3210) | Rent | yes |
| 2026-05-20 | $19,580 wire to Eric Chang (deposit + first month) | Rent | yes |
| 2026-07-06 | $9,000 "Wire to Eric Chang" | **Transfer** | **no** |
| 2026-07-31 | $9,000 "Wire to Eric Chang" | **Transfer** | **no** |

Every month of 2025 carried $7,500–$8,328 of rent. June–August 2026 carry
$0 on the page. The rulebook in `spending/models.py` cannot rescue this:
`display_category()` runs *after* `_base_query` has already filtered on the
raw category's kind, so a rule "wire to Eric Chang → Home Rent" would never
see the row.

**Fix**
- Recategorize both wires as `Rent` in Monarch (authoritative source), then
  re-import. This is the immediate fix.
- Structural: run the rulebook *before* kind classification, and add a
  positive rent rule keyed on counterparty (per
  `category-is-a-ledger-not-a-stream`): "wire to eric chang" → Home Rent,
  kind SPENDING, regardless of Monarch's category. A landlord change then
  fails loudly instead of silently zeroing rent.
- Add a **missing-recurring detector** (see D9): rent, school, insurance
  have appeared every month for 20 months; a month without them is a data
  defect until proven otherwise.

### D2. August counts $6,910 of fully-refunded charges — HIGH (current month)

| date | row | category | amount |
|---|---|---|---|
| 08-28 | Yanghall, RH card | Uncategorized | −3,455 |
| 08-30 | "Refund: Yanghall1", RH card | **Business Income** | +3,455 |
| 08-28 | Denise Hall, PayPal | **"Joann Riggio"** | −3,455 |
| 08-31 | "Refund from Denise Hall", PayPal | **Other Income** | +3,455 |

Both charges count as spend. Neither refund nets: the category filter
(INCOME kind) rejects them before the `refund:` check, and the second does
not match the `refund:` prefix anyway. August shows $22,702; net of these
it is $15,792 (before the rent in D1). That is a 30% error on the month
you are most likely to look at.

**Fix**
- Recategorize both refunds in Monarch (they are not income).
- In `_base_query`, test for refund *before* kind: a row whose statement
  begins "Refund" is a refund whatever its category. Broaden the match to
  `refund:` and `refund from`.
- Surface person-named categories ("Joann Riggio", "Adamx", "Check") as a
  flagged count on the page. They default to SPENDING silently today.

### D3. Brokerage outflows have no refresh path — HIGH

- `investment_transactions` CASH_MOVEMENT: `neel_brokerage` last row
  2026-07-20, `jaya_brokerage` 2026-07-09.
- Monarch's Checking/Savings show brokerage transfers the ledger lacks:
  Jul 31 $2,000, Aug 8 $1,000, Aug 12 $5,000, Aug 22 $10,000.
- The August statement PDF *was* imported (dividends through 08-24, margin
  08-13), but `import_robinhood_statement_pdf.py` imports only dividends,
  interest, lending and margin by design. Cash movements arrive only via
  the activity CSV, last ingested 2026-07-01/03.
- The page's stale-warning class fires only when Monarch trails outflows.
  Today outflows trail Monarch by 42 days and nothing is amber.

**Fix**
- Extend the statement importer to the cash codes (XENT, XENT_CC, ACH,
  RTP → CASH_MOVEMENT). Same safety argument the script already makes for
  margin: the MCP feed never emits these types, so no dedup collision.
- Make the freshness stamp two-sided (either source stale → amber).

### D4. Monarch double-reports brokerage transfers since the Aug 26 reconnect — MEDIUM

Every brokerage → Checking/Savings transfer since Jul 4 exists twice: once
as "From Brokerage" and once as "Transfer from Robinhood Brokerage account
ending in…" (same account, day, amount; different statement text, so
different `record_hash`). Pairs on Jul 4, 6, 7, 31, Aug 8, 12, 22. All are
`Transfer`, so the Spending total is unaffected today, but any real spend
row that Monarch re-describes the same way will double. Also
2026-08-18 Worldmark ×3 identical rows ($163.35, AirBnb) — verify.

**Fix** in `import_monarch_spending_csv.py`: for the Robinhood cash
accounts, normalise "From Brokerage"/"Transfer from Robinhood Brokerage…"
to one statement before hashing, and report same-day-same-amount pairs in
the dry run.

### D5. Two outflow definitions on one page — MEDIUM

`/outflows` (the L1 reconciliation line) and `/cash-flow/{year}` +
`/cash-flow/{year}/{month}` (the summary cards, bar chart and month-view
"Actual" table) disagree:

| | `/outflows` | `/cash-flow/*` |
|---|---|---|
| types | XENT_CC, XENT, CASH_MOVEMENT, RTP | CASH_MOVEMENT only |
| pre-Dec-2025 double-ingest | deduped | not deduped |
| 2025 card payments (XENT_CC, 60 rows, 30 dup) | included | **omitted** |
| month attribution | calendar | shifted by `KNOWN_RECURRING_EXPENSES` (rent $8,000, RH card $7,484, Chase Amazon $1,200 — all stale) |

Playbook rule: two totals on one screen is a definition bug. Delete the
`/cash-flow/*` endpoints and the three panels they feed; `/outflows` is the
one definition, and it is a reconciliation line, not a headline.

### D6. Month view categories don't sum to the headline — MEDIUM

Month view filters the category table and donut to `is_monthly`, hiding
Taxes, Insurance, Travel, ONE TIME and trips with no indicator. March 2026:
headline $80,964; visible categories sum to ~$16,200 because the $55,722
Subaru and $32,250 of IRS/FTB payments are hidden. Show every category;
group non-monthly rows under a labelled subtotal so rows tie to the
headline to the cent.

### D7. Category click-to-drill is broken for every derived category — MEDIUM

The category table shows display labels (Amazon, Home Rent, Home Utility,
Blue Bottle, Alisha's Education, Auto Maintenance ∪ Gas). Clicking one sets
`filterCategory` to that label; `/transactions?category=` filters the raw
DB column → zero rows. The transactions table badge shows the raw category
("Shopping" for Amazon) and the filter dropdown lists raw categories.
Apply `display_category()` in `get_spending_transactions` (filter and
label) and `get_available_filters`.

### D8. A third spending definition in BBD — LOW

`bbd_performance_service._get_monthly_spending` uses
`EXCLUDED_CATEGORIES + amount < 0` — no refund netting, no rulebook.
Point it at a shared `spending_rows()` helper.

### D9. Freshness is one global date — MEDIUM

`monarch_through` is `MAX(transaction_date)` over all accounts (08-31),
which hides per-account tails (KB rule `check-freshness-and-ask-first`):

| account | last row | status |
|---|---|---|
| RH card, Checking, Savings, BofA 9486/9487, PayPal | 08-31 | live |
| BofA Premier ×2, Amazon card (…2417) | 08-28 | live |
| Costco Citi | 08-22 | lagging |
| Business Expense 9485 | 08-19 | lagging |
| CREDIT CARD (…5149) | 06-19 | dead or unused |
| Spending (…dabe) | 06-06 | retired (superseded by Checking/Savings) |

Add `/spending/freshness`: every account ever seen, its tail, a retired
list, and the outflow tail; amber >7 days, red for a live account that
stopped.

### D10. Definitional loose ends — LOW

- **Security deposits.** $19,580 to Eric Chang is counted as rent; Yuan
  Lee's $4,000 deposit return is excluded, not netted. Deposits are an
  asset, not spend — rule them to `Transfer` and show "deposits
  outstanding" somewhere. 2026 Home Rent is overstated by the deposit
  portion.
- **Uncategorized 2026**: 29 rows, $4.3K out, dominated by the Yanghall row
  in D2. Fine once D2 is fixed.
- Dead code: `/categories` and `/trends` are unused by the page and
  `/categories` ignores the rulebook; `top_merchants`, `mom_change`,
  `annual_expenses` are computed and never rendered.

---

## Part 2 — What the page does not tell you

With D1/D2 corrected, 2026 recurring spend runs $14K–$26K a month
(median ≈ $19K) plus $8–9K rent. The page cannot currently answer any of:

1. **What is my floor?** Fixed (rent, school, insurance, utilities,
   phone/internet, subscriptions) vs variable (food, shopping, kids'
   activities, travel). The current "recurring vs non-monthly" split is by
   category *name*, not by fixed/variable.
2. **Is this month normal?** No baseline. May 2026 recurring was $36,479
   against ~$19K typical — the $19,580 deposit — and nothing said so.
3. **Where does it actually go?** Merchant view is computed and hidden.
   2026: Costco $11.7K, Stratford $10.6K, City of Palo Alto $6.3K, Anthem
   $8.0K, Red Rock Volleyball $4.3K, Amazon $4.1K, YMCA $3.9K, Expedia
   $3.7K, Geico $2.4K, Gifthealth $2.4K, Taekwon Kids $2.0K.
4. **What were the big one-offs this year?** Subaru $56.0K, taxes $32.3K,
   deposit $19.6K, movers $1.9K. Hidden in month view, buried in year view.
5. **Spend vs income.** Objective 5 (BBD) needs expense coverage; the
   Income page has the numerator and this page never shows the ratio.
6. **By account / by person**, in canonical order. Today it is a filter.
7. **Recurring subscriptions** as one line: Software $1.5K, AI Tools $0.7K,
   Phone $1.3K, Internet $0.9K, News — ≈ $4.4K/yr.

---

## Part 3 — Target hierarchy (per playbook)

- **L1 Headline.** Total spend for the period (Monarch, categorized), the
  page's only period control (Month / Year with ‹ ›), defaulting to the
  latest *complete* month with data — not the calendar month (today the
  page opens on an empty September). Sub-line: Fixed / Variable / One-time.
  Two freshness stamps from `/spending/freshness`. Brokerage outflows as a
  quiet reconciliation line, judged over a quarter, never a month.
- **L2 Is this normal?** Each group vs its trailing-6-month median; top
  five movers up/down with the merchant behind each; missing expected
  recurring lines (rent, school, insurance) flagged red. Optional targets in
  `data/spending_targets.json`, mirroring `goal_settings.json`.
- **L3 Composition + trend.** Stacked monthly bars by *group* (Housing,
  Kids & School, Food, Auto, Insurance & Health, Shopping, Travel, Taxes,
  Subscriptions, Other — ~10 groups over Monarch's 60+ categories, defined
  server-side next to the rulebook), `stackOffset="sign"`, and a table whose
  rows tie to L1 to the cent. Every row drills, scoped to the period.
- **L4 By account (canonical order) and top merchants.**
- **L5 Transactions** with display categories and working filters.

**Delete:** Recurring Outflows / Transfers In / One-Time cards, Monthly Cash
Flow chart, month-view "Actual" brokerage table, `/cash-flow/*`,
`KNOWN_RECURRING_EXPENSES` from this page's path.

**Tokens:** `Spending.tsx` has 21 hardcoded colours and `Spending.module.css`
19 (`#EF4444`, `#10B981`, `#3B82F6`, `rgba(255,255,255,…)`, the
`CATEGORY_COLORS` list). All go to `tokens.css` per
`always-use-design-tokens`.

---

## Part 4 — Sequence

1. **Data (this week).** D1 + D2 in Monarch, re-import. Extend the
   statement importer to cash movements (D3). Importer dedup for
   re-described rows (D4). `/spending/freshness` (D9).
2. **One definition.** `spending_rows()` helper with rulebook-before-kind,
   refund-before-kind, deposit rule; used by `/summary`, `/transactions`,
   `/filters`, `/outflows`, BBD (D5, D7, D8). Delete `/cash-flow/*`,
   `/categories`, `/trends`.
3. **Groups + baselines.** Category → group map; trailing-median and
   missing-recurring services.
4. **UI rebuild** per Part 3, iterating on screenshots.
