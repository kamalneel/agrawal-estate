# Options UX audit — 23 Oct 2026

Neel's path today: Options Execution → Income → click "Assignment Loss" → Investments
(auto-scrolls to Put Campaigns). From Options Execution, the same words land on a
different table (Assignment Loss, the screenshot). This audit lists every surface that
reports an options outcome, where the numbers disagree, what is dead, and a target layout.

Live numbers below are from the running backend at ~5 PM PT, 23 Oct.

## 1. Inventory

| Surface | Page / route | Component | Endpoint → service | What it measures | Links to |
|---|---|---|---|---|---|
| Action Queue + Open Positions | Options Execution `/strategies/options-selling` | `pages/OptionsExecution.tsx` | `/strategies/v6/action-queue` → `v7_engine.build_live_action_queue` (V8) | What to do today; per open contract the net premium across its roll chain ("Total Collected (Nwk)") | "See V7 (previous) →" `/strategies/v8-preview` |
| Premium today / this week | Options Execution header | same | `queue.premium` | Sold − bought back, today and week (today +$3,939, week +$15,660) | — |
| Goals strip | Options Execution **and** Income | `GoalsStrip` | `/income/goal-settings`, `/income/put-capacity`, … | Holdings / Cash goal vs. target | drill (Income only) |
| **Assignment Loss — this month** | Options Execution | `AssignmentLossThisMonth` (no props) | `/strategies/v6/assignment-loss` → `assignment_loss_service.get_assignment_loss` | **Puts + calls**: puts = strike − market that day; calls = cost basis − strike (highest-cost lots) | `/investments#assignment-loss` (the screenshot table) |
| **Assignment Loss — period** cell | Income, goals strip | `AssignmentLossThisMonth putsOnly` | same | **Puts only** | `/investments#assignment-loss` — lands on a puts **+ calls** headline |
| **Assignment Loss \*** column | Income, monthly table | `Income.tsx` ~4364 | same, `by_month_type.put` | **Puts only**, context, not in Total | `/investments#put-campaigns` |
| Equity Sales column | Income | `Income.tsx` / `/income/unified` | unified income | Every share sale incl. **call assignments** at the lot method's basis | drill → `EquitySalesDetail` |
| Options column / Monthly Options Income | Income | `UnifiedIncomeBand`, `OptionsDetail` | `/income/unified`, `/income/options/by-type` | Net premium by month, calls vs puts | drill |
| **Assignment Loss** card (chart + 80 events) | Investments | `AssignmentLossCard` | `/strategies/v6/assignment-loss` | Puts + calls as above, monthly bar chart, per-event calculation; net premium of the chains that ended in assignment | — |
| **Put Campaigns** | Investments (right below) | `PutCampaigns` | `/strategies/v6/put-campaigns` → `get_put_campaigns` | Per stock: loss when assigned, shares today (held × today + sale proceeds − strike × shares), put premium, call premium on those shares, campaign all-in, adj. basis | — |
| **Covered Call Income** | Investments (right below) | `CoveredCallIncome` | `/strategies/v6/covered-call-income` → `covered_call_service` | Calls on **bought** shares: net premium − upside given up (**market − strike** at assignment), × covered % | — |
| vs. Buy & Hold (ghost curve) | Investments | `Investments.tsx` | `/investments/ghost-curve` | "If I had frozen the options game on date X" | drill per point |
| Strategy Deviations | Investments | `Investments.tsx` | `/investments/policy-deviations` | Core exits awaiting re-entry, idle inventory, puts since | — |
| V7/V8 queue | `/strategies/v8-preview`, sidebar More → "**Notifications V7 (previous)**" | `pages/V8Preview.tsx` | `/strategies/{v7,v8}/preview`, `/strategies/v7/knobs` | Same queue under V7 rules, V7/V8 toggle, knob editor | — |
| **Notifications** (legacy) | `/` (the app's **landing route**) and main sidebar "Notifications" | `pages/Notifications.tsx` (2,050 lines, last edited 2026-03-11) | `/strategies/notifications/v2/history`, `check-now-v5`, Schwab token, Telegram replies, RLHF feedback | V2–V5 recommendation feed | — |
| Learning dashboard | `/strategies/learning` — **no sidebar link** | `pages/LearningDashboard.tsx` (2,776 lines) | `learning_router` | RLHF matches / outcomes | — |
| Options Selling (old page) | **not routed** | `pages/OptionsSelling.tsx` (4,370 lines) | — | Pre-V6 options page | — |
| AccountOptionsDetail | **never rendered** | `Income.tsx` lines 1081–1473 | — | Old per-account options drill | — |

## 2. What doesn't tie out (live)

**One phrase, three numbers, two destinations — October 2026:**

| Where Neel sees "Assignment Loss" | Shows | Click goes to | Which headlines |
|---|---|---|---|
| Options Execution card | **−$23,224** (puts −$14,698 + calls −$8,526) | Assignment Loss card | −$23,224 ✓ |
| Income goals-strip cell | **−$14,698** (puts only) | Assignment Loss card | −$23,224 ✗ |
| Income table column | **−$14,698** (puts only) | Put Campaigns | no monthly figure; all-time −$221,030 |

**Calls are measured three different ways.** The same IBIT $39 call assignment
(9 Oct, 1,500 sh):
- Assignment Loss card: **−$7,626** — cost basis $44.08 − strike, highest-cost lots.
- Covered Call Income: **−$11,325** upside given up — market $46.55 − strike.
- Income → Equity Sales: in October's −$13,530, at the lot method's basis.

All-time: Assignment Loss calls −$138,891 vs. Covered Call Income upside given up
−$184,552. Income's own footnote says call assignments belong in Equity Sales and are
deliberately not assignment loss (Neel, 2026-10-15) — but the Options Execution card
and the Investments card still add them in.

**Put figures agree but repeat.** Assignment Loss puts −$221,030 = Put Campaigns
"loss when assigned" −$221,030 (43 puts). The card's "net premium collected"
$154,378 = put chains $116,625 (= Put Campaigns' put premium) + call chains $37,753
(chains that ended in a call assignment — a scope that appears nowhere else).

**Put Campaigns totals today:** loss when assigned −$221,030 → shares today −$272,488;
+ put premium $116,625 + call premium $72,414 = **campaign −$83,449**.
**Covered Call Income:** net premium $163,440 − upside given up $184,552 = **−$21,112**.

## 3. What is working

- **Options Execution's scope** (today + pace, no history — Neel, 2026-07-22) is right,
  and it is where the day is spent.
- **Income's Assignment Loss column** is clean: puts only, context only, not in Total,
  and its footnote explains why calls live in Equity Sales.
- **Put Campaigns** is the view Neel says gives "the right picture": follows each
  assignment to today, folds in both premiums, adj. basis, arithmetic on hover.
- **Roll-chain premium** is one function (`_walk_roll_chain`) used by the board, the
  card and the campaigns, so premium figures agree everywhere.

## 4. What is not

1. **Two destinations for one click.** Options Execution and the Income goals cell go to
   the Assignment Loss card; the Income column goes to Put Campaigns.
2. **Two definitions under one name.** "Assignment Loss" is puts + calls on Options
   Execution and Investments, puts-only on Income.
3. **The Assignment Loss card is superseded.** Its put half is Put Campaigns' "loss when
   assigned"; its call half is a share-sale result Income already books in Equity Sales,
   and a third call measure beside Covered Call Income's.
4. **No call sibling to Put Campaigns.** Covered Call Income answers the right question
   for bought shares, but in a different shape (Covered %, Since, Net premium, Upside,
   Net), so it doesn't read as the other half of the wheel.
5. **The landing page is dead.** `/` and the main-nav "Notifications" open the V5-era
   page; its tables were last written Jan 2026 (`strategy_recommendations` 22 Jan,
   `recommendation_notifications` 6 Jan). Meanwhile "Notifications V7 (previous)" in More
   is actually the V7/V8 engine page — two things called Notifications, neither the live one.
6. **Three stacked, unlinked sections** on Investments (Assignment Loss, Put Campaigns,
   Covered Call Income) between the wealth chart and vs. Buy & Hold; nothing links to
   Covered Call Income.

## 5. No longer needed

| Item | Size | Why |
|---|---|---|
| `pages/OptionsSelling.tsx` (+ .module.css) | 4,370 lines | Not routed; replaced by Options Execution |
| `AccountOptionsDetail` in `Income.tsx` | ~390 lines | Defined, never rendered |
| `pages/Notifications.tsx` as `/` and main-nav item | 2,050 lines | V2–V5 feed, frozen since Jan 2026; Schwab/Telegram/RLHF controls for retired flows |
| `AssignmentLossCard` on Investments | 300 lines | Put half = Put Campaigns; call half = Equity Sales (see §4.3) |
| `LearningDashboard` (`/strategies/learning`) | 2,776 lines | No nav link; RLHF era; `position_outcomes` empty. Its weekly summary job still writes (`weekly_learning_summaries`, last 17 Oct) with no reader |
| Backend: v2/v4/v5 notification services + their routes | — | Only the legacy page calls them; no scheduled job in `scheduler.py` runs the scans (verify before removal) |

## 6. Recommended structure

**One idea per place, one definition per word.**

- **Options Execution** (daily): unchanged, except the card becomes
  **"Put assignments — this month"**, puts only (−$14,698 today, same as Income), and it
  links to **`/investments#put-campaigns`** with this month's assignments highlighted.
  If there were call assignments this month, a second line "Calls called away — N"
  links to `#call-campaigns`.
- **Income** (monthly read): keep the puts-only column. Point the goals-strip cell at
  `#put-campaigns` too, so every "assignment" click lands in one place.
- **Investments → one "Wheel" block, two sibling tables, same design:**
  - **Put Campaigns** (as is) + absorb from the old card the **monthly bar chart**
    (loss when assigned by month) and the **per-event calculation** line in the
    expanded rows.
  - **Call Campaigns** (new; replaces Covered Call Income, same `PutCampaigns.module.css`
    columns pattern): per stock, calls on bought shares — calls sold, assignments,
    shares called away, net premium, **upside given up when assigned**, and **campaign**
    = net premium − upside given up. Wheel-share calls stay in Put Campaigns, so each
    call still counts once.
  - Retire the Assignment Loss card. The endpoint stays (Income and the Options
    Execution card read `by_month_type.put`); the call-loss figure leaves the UI.
- **Landing + nav:** `/` redirects to Options Execution; drop "Notifications" from the
  main nav; rename "Notifications V7 (previous)" → **"Engine preview"** (where a V9
  overlay would appear).

**The one design decision for Neel:** what a call campaign's headline should be —
(a) premium − upside given up **at assignment** (today's Covered Call Income
definition, an opportunity cost), or (b) the mirror of Put Campaigns' "followed to
today": premium − what the called-away shares would be worth **today** above the
strike. (a) is what was agreed on 23 Oct; (b) is the exact sibling of the put view.

**Decided (Neel, 23 Oct):** (a). A call campaign's bottom line is premium − upside given
up on the day of assignment, Covered Call Income's measure; only the layout changes.

## 7. Migration order

1. ✅ **Links + definitions** (done 23 Oct): Options Execution card puts-only and →
   `#put-campaigns`; Income goals cell → `#put-campaigns`.
2. ✅ **Call Campaigns** (done 24 Oct): reshape Covered Call Income into the Put Campaigns layout, anchor
   `#call-campaigns`.
3. ✅ **Fold and retire the Assignment Loss card** (done 24 Oct): chart + calculation into Put Campaigns,
   remove the card.
4. ✅ **Dead code** (done 24 Oct): delete `OptionsSelling.tsx`, `AccountOptionsDetail`; `/` → Options
   Execution; rename the engine-preview nav item.
5. ✅ **Legacy notifications + learning** (done 25 Oct, Neel's OK): remove the page, the v2–v5
   routes and services, and the RLHF jobs.

### Step 1, as built (23 Oct)

- The Options Execution card is now **Put Assignment Loss — this month**, puts only:
  −$14,698 for October, the same figure Income shows.
- Every assignment-loss figure goes to Put Campaigns with its period in the link
  (`/investments?assigned=2026-10#put-campaigns`). That covers the Options Execution card,
  Income's top-strip cell, and each month's cell in Income's table; the column header
  still opens the whole table. On arrival Put Campaigns shows the period's figure
  ("Assigned in Oct 2026: −$14,698 · 3 puts on CBRS"). It lists that period's stocks
  first and highlights them and their assignment rows, opens the stock if there is only
  one, and has a "show all" link to clear the period.
- Put Campaigns' events add up to `by_month_type.put` exactly, both per month and per
  year (Oct −$14,698, Sep −$16,893, 2026 −$193,996), so the figure you click is the
  figure you land on.

### Step 2, as built (24 Oct)

Covered Call Income is now **Call Campaigns** (`#call-campaigns`, endpoint
`/strategies/v6/call-campaigns`). It sits directly under Put Campaigns and
uses the same stylesheet and layout:

- **Headline figures:** net premium after buy-backs, upside given up
  (33 calls assigned, 6,363 shares) and the campaign all in. The totals are
  unchanged from Covered Call Income: $163,440 − $184,552 = −$21,112.
- **Columns:** Stock (with a "closed" tag once none of the bought shares
  are held), Covered, Since, Called away (shares and number of assignments),
  Avg strike, Net premium, Upside given up, Campaign.
- **Expanded rows:**
  - one row per account;
  - one row per assignment, showing strike against that day's market and
    what the calls in that roll chain paid (e.g. IBIT: "incl. +$615 (9wk)").
    That chain figure is context only: it is already inside the net premium,
    which also counts every call that expired, so these rows do not add up
    to it. Hovering upside given up shows the arithmetic.
- **Measure:** upside given up is taken on the day of each assignment
  (decision (a)).

### Step 3, as built (24 Oct)

The Assignment Loss section is gone from Investments (`AssignmentLossCard.tsx` deleted).
What it had that Put Campaigns did not:

- **Monthly chart** → in Put Campaigns, under the headline figures: loss when
  assigned by month, puts only, with every month from the first assignment shown
  (zero months included). The current month is amber. Clicking a bar highlights
  that month's puts (the same `?assigned=` as the links from step 1); clicking it
  again clears it.
- **Per-assignment arithmetic** → hover over "Loss when assigned" in an expanded row:
  "($160.00 strike − $110.82 market) × 200 sh = −$9,828". The `~` mark for a
  nearest-close market price carries over (`price_source` added to the Put Campaigns
  events).
- **Dropped on purpose:** the calls half (cost basis − strike) is a share-sale
  result that Income already books in Equity Sales, and call assignments now have
  Call Campaigns. Also dropped: the "$154,378 net premium on assigned positions"
  figure. It mixed put chains with chains that ended in a call assignment, a mix
  used nowhere else; put premium is Put Campaigns' own column.
- Old `#assignment-loss` links now land on Put Campaigns. The
  `/strategies/v6/assignment-loss` endpoint stays: the Options Execution card and
  Income read the puts figure from it.

### Step 4, as built (24 Oct)

- **The app now opens on Option Execution.** `/` redirects to `/strategies/options-selling`,
  and the login lands there too.
- **The sidebar no longer has "Notifications".** The V2–V5 page can still be
  reached at `/notifications` until step 5 decides its fate. (Step 5 removed it.)
- **"Notifications V7 (previous)" is now "Engine preview"**, in the sidebar's More
  group. The page title reads "Engine preview — V8 (live)" / "— V7 (previous)", and
  Option Execution's link to it reads "Engine preview →".
- **Deleted:** `pages/OptionsSelling.tsx` and `.module.css` (4,370 lines; not
  routed) and `AccountOptionsDetail` with its data type in `Income.tsx` (~320 lines;
  never rendered). The type-check of Income shows no new unused code, so nothing
  else depended on it.

### Step 5, as built (25 Oct)

**What is gone:**
- **Pages.** `pages/Notifications.tsx` (2,050 lines) and `pages/LearningDashboard.tsx`
  (2,776 lines), with their CSS, plus `TechnicalAnalysisModal`, which only Notifications
  opened. `/notifications` and `/strategies/learning` now redirect to Option Execution, so
  old bookmarks still land somewhere.
- **Routes in `strategies/router.py`** (27 routes; 7,348 → 5,701 lines):
  - the V2–V5 "check now" and preview routes;
  - notification history (`/notifications/history`, `/v2/current`, `/v2/history`,
    `/{id}/status`, `/stats`);
  - recommendation feedback (`/notifications/{id}/feedback`, `/feedback/insights`,
    `/feedback/history`);
  - all seven Telegram webhook/poll routes, which turned replies to recommendation messages
    into feedback;
  - `/debug/cache-status`, `/debug/test-mode` and `/v4-validation`.
- **The learning router** (`learning_router.py`, 1,819 lines, every `/strategies/learning/*`
  route).
- **Scheduler jobs:** the three RLHF jobs (daily reconciliation 9 PM, outcome tracking 10 PM,
  Saturday 9 AM learning summary). Also the unscheduled V2/V4/V5 scan methods (`check_and_notify`,
  `check_and_notify_v2/_v4/_v5`, `_run_versioned_check`, the `trigger_*_check` helpers).
  `scheduler.py` went from 1,631 to 461 lines.
- **Service modules** that nothing live imports any more, found by an import graph from
  `app.main` before and after:
  - `feedback_service`, `recommendation_service`, `reconciliation_service`;
  - `v2_notification_service`, `v4_notification_service`;
  - `v4_position_evaluator`, `v4_sanitizer`, `v5_position_evaluator`;
  - `weekly_recommendation_filter`, `shared/services/telegram_poller`,
    `shared/services/telegram_webhook`.
- **Scripts and tests that only exercised those modules:**
  - `test_rlhf_system.py`, `tests/test_v4_baseline.py`, `test_v4_validation.py`,
    `test_v5_refactor.py`;
  - `scripts/reconcile_date_range.py`, `test_reconciliation_fix.py`, `poll_telegram.sh`
    (never in cron/launchd), `test_scheduler.sh`.

**What stays, deliberately:**
- **Live scheduler jobs:** the V8 email after each sync (`notify_after_sync` →
  `check_and_notify_v6`), the 8:15 PM portfolio snapshot, the 6 AM expense reminders, the
  6:30 AM assignment tax-lot notices and the price-alert checker. Telegram *sending* is in
  `shared/services/notifications.py`, untouched.
- **All database tables.** `learning_models.py` and `RecommendationNotification` are kept
  so the table definitions stay; nothing writes to them now.
- **The V5 engine and `StrategyService`.** The Strategy Settings page (sidebar) and
  `/options-selling/recommendations` still use them, so they are out of this step's
  scope.
- **`/schwab/token-status` and `/schwab/authenticate`.** Schwab is the backend's second
  price source (playbook: market-data-source-order); these two routes are the only way
  to log back in, and Notifications was their only button. The token on disk dates from
  2026-06-22, so its 7-day refresh token lapsed on 29 Jun — Schwab has been off since.
  Re-log in by POSTing `/api/v1/strategies/schwab/authenticate` if it is ever wanted.

**Checks:**
- The app imports cleanly. After `--reload`, the live backend serves action-queue,
  put-campaigns, call-campaigns and assignment-loss (200), and the removed routes return 404.
- Call Campaigns totals are unchanged (−$21,112.01).
- pyflakes shows no new warnings in `router.py`, `scheduler.py` or `main.py`; it shows 6
  fewer stale V5 imports.
- `tsc` reports no errors involving App.tsx or a missing module; pytest still collects 190 tests.
