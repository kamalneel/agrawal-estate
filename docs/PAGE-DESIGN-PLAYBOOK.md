# Page Design Playbook

Distilled from the Income page redesign (2026-07-03 → 2026-07-07, ~15
feedback rounds with Neel). Apply this method to Options Execution,
Investments, and every other first-class page. Each principle below was
learned from a concrete correction — do not relearn them.

## The method (order matters)

1. **Anchor on the objective.** Re-read the page's objective in
   [OBJECTIVES.md](OBJECTIVES.md). Write the page's *test question* — the
   sentence the user will ask it (Income: "what did I earn this
   week/month/year, across everything?"). Every element must serve it.
2. **Fix the data before the UI.** Wrong/partial data made every earlier
   Income UI misleading. Sequence: data foundation → shared service →
   API → UI, with a validation gate at each step (tie to an external
   authority where possible — we tied realized P/L to the filed 8949).
3. **Define terms with the user first, in writing** (spec doc + KB rule),
   then encode ONE definition server-side that every widget consumes.
   Two totals on one screen = a definition bug, not a display bug.
4. **Redesign the whole page hierarchy, not a corner.** Adding a good
   widget to a cluttered page made it worse ("no hierarchy of
   information"). Propose levels, get approval, then cut.
5. **Iterate on screenshots.** Small rounds, user reacts to the real
   page. Capture every stated preference as a KB rule immediately.

## Information hierarchy (the four levels)

- **Level 1 — Headline + the page's ONLY period control.** One number
  answering the test question. Weekly (Friday-ending) / Monthly / Yearly
  toggle with ‹ › time navigation. Everything below follows this period.
- **Level 2 — Goals.** Actuals-vs-target gauges (1%/mo holdings, 2%/mo
  cash) directly under the headline. Current period shows *pace-to-date*,
  not full-month target (don't be red all month). Green ≥100% / amber
  ≥70% / red. Gauges are clickable → the "why" breakdown.
- **Level 3 — Composition + trend.** Stacked chart in importance order +
  a table whose rows tie the headline to the cent.
- **Level 4 — By account.** Cards/rows in the canonical account order.

One period model. One total. Delete anything that duplicates either
(we deleted the old hero, its selectors, the Income Sources card grid,
and the BBD tiles).

## Importance hierarchy

- **Sources:** Options > Equity Sales > Salary > Rent > Dividends+Interest
  (+Lending). Order tabs, chips, chart stacks, and table columns this way.
  Merge the small ones ("Div + Int") rather than give them space.
- **Accounts:** ALWAYS the canonical order (see
  canonical-account-hierarchy KB rule; `frontend/src/lib/accountOrder.ts`
  / backend `ACCOUNT_ORDER`). Never sort accounts by amount.
- **Space follows money.** Dim zeros to "—"; never render grids of $0
  (the eight-account card grid failure). Small-but-nonzero gets one
  quiet line, not a panel.

## Non-negotiable display rules

- **Negative = red, everywhere, without hovering.** Tables: sign-colored
  cells AND row tint (beware `!important` in shared CSS — it silently ate
  inline colors once). Charts: `stackOffset="sign"` for stacked bars
  (Recharts otherwise draws positive bars from negative baselines —
  a real rendering bug we hit), split green/red gradient at the zero
  crossing for line/area charts, sign-colored dots, dashed zero line,
  white Net overlay on diverging stacks.
- **Gross AND net for flow data.** Net-only hides activity: a roll month
  showed "$37" when $3.4k was sold and $3.4k spent closing. Show
  Sold / Bought Back / Net wherever premiums or similar flows appear.
- **Projections never mix silently with actuals.** Labeled italic line /
  separate column, excluded from totals. Recurring known amounts
  (salary_projections) count as actuals only for ELAPSED periods;
  schedules (lease rent) clamp to elapsed months — receipt basis.
- **Tax badges:** taxable (amber) / sheltered (gray) on every account
  mention; taxable-vs-sheltered is the user's first grouping question.

## Drill-down rules ("double-clickable everything")

- Every headline number, chip, and gauge must open a breakdown. Guess the
  user's next question and answer it at the top: for P/L it was
  "taxable or sheltered?" then "which account?" → two group cards with
  per-account subtotals + click-to-filter, ABOVE the row table.
- **Drills open scoped to the period clicked** (band passes period +
  granularity), with a clearable scope pill.
- **Full in-place time navigation inside the drill** (year row + month
  pill row) — never force back-out-and-return.
- Seed legacy detail views with the year the user was viewing.
- Show provenance where numbers were derived (basis_source column) and
  surface unresolved data as flagged counts — never silently wrong.

## Data plumbing patterns that made it work

- One unified service, query-time aggregation, no new tables; legacy
  endpoints become thin wrappers so every consumer agrees.
- `taxable_only` as a first-class server-side mode (account-type filter),
  fetched as a second dataset so toggles swap chart+table together.
- Friday-ending weeks everywhere income is weekly.
- Dynamic bases computed monthly with carry-forward + `partial` flags for
  months with incomplete history (put capacity); manual inputs the broker
  won't expose (margin lines) live in `data/goal_settings.json`.
- MCP sync keeps snapshots/history accumulating; verify derived figures
  (collateral = cash − buying power) to the cent before every save.

## Reusable inventory (don't rebuild)

- `UnifiedIncomeBand` — headline + period control pattern
- `GoalsStrip` / `GoalDrill` — target gauges + per-position/account "why"
- `EquitySalesDetail` — scoped drill with group cards, filters, month nav
- `lib/accountOrder.ts` — canonical account sorting
- Endpoints: `/income/unified`, `/income/goal-settings`,
  `/income/put-capacity`, `/income/goal-drill`,
  `/investments/realized-pnl(+/sales)`
- Shared lot engine: `app/shared/services/cost_basis_service.py`

## Next applications

- **Options Selling page:** test question = "what should I do today, and
  am I on pace for 1%/2%?" Levels: goals+pace → per-position guidance
  (idle collateral, ITM risk like SPCX 200p, roll candidates) → open
  positions by expiry → history. Re-home the calls-vs-holdings /
  puts-vs-cash panels here. V6 engine feeds Level 2.
- **Investments page:** test question = "am I following my policy?"
  (trillion-club for holdings, volatile/hot for puts). Policy compliance
  badges at Level 1, per-position policy table, drills to trade history.
