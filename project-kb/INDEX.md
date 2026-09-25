# Knowledge Base Index

Auto-maintained master index. Updated by Claude when entries are added or removed.

---

## Playbook — Universal

### Communication
- [Preferences Captured Over Time](playbook/universal/communication/preferences-captured-over-time.md) — communication style is iteratively captured, not pre-specified; covers email, notifications, content, personal messages
- [Deliverables Stay Local](playbook/universal/communication/deliverables-stay-local.md) — reports are PDFs under data/documents/reports or docs in docs/, never a claude.ai Artifact or hosted page; short prose, tables, "Inferred" tags

### Design
- [Always Use Design Tokens](playbook/universal/design/always-use-design-tokens.md) — never hardcode colors/spacing, use CSS variables from tokens.css
- [Canonical Account Hierarchy](playbook/universal/design/canonical-account-hierarchy.md) — fixed account order everywhere (Neel Brok/IRA/Roth, Jaya Brok/IRA/Roth, Alisha, HSA); never sort accounts by amount
- [Page Design Playbook](../docs/PAGE-DESIGN-PLAYBOOK.md) — the method distilled from the Income page: 4-level hierarchy, one period model/one total, importance ordering, sign-coloring, gross+net, scoped drill-downs, reusable components

### Finance
- [Buy in Round Lots of 100 Shares](playbook/universal/finance/buy-in-round-lots-of-100.md) — every position a multiple of 100, floor 100, so covered calls can be sold against all of it
- [Definition of Income](playbook/universal/finance/definition-of-income.md) — realized-only, all accounts, tax-independent; call assignment = income at sale, put assignment = strike-basis lot
- [A Bookkeeping Category Is a Ledger, Not an Income Stream](playbook/universal/finance/category-is-a-ledger-not-a-stream.md) — define income by counterparty+direction+kind; never wire a Monarch category straight to an income card
- [Attribute Income to the Period It Is For](playbook/universal/finance/attribute-income-to-its-stated-period.md) — count a payment in the month its memo names, not the day it cleared; reconcile to the contract
- [Run Counterparty and Refund Rules Before the Category-Kind Filter](playbook/universal/finance/classify-by-rule-before-category-kind.md) — a kind filter on the raw category silently deleted $18K of rent and $13K of refunds; one classify() for every consumer
- [Dollar Growth Is Flow-Adjusted, Like the Percent](playbook/universal/finance/dollar-growth-is-flow-adjusted.md) — gain = ending − beginning − net flows, stored on the metric row; balance change is not growth; averages compound
- [Every Call Assignment in a Taxable Account Gets a Tax-Lot Notice](playbook/universal/finance/call-assignment-tax-lot-notice.md) — Robinhood assigns on the account default (FIFO) and corrects lots only until 9 PM ET on settlement; set Highest Cost, notice every time, lot engine must match

### Process
- [Three Authoritative Data Sources](playbook/universal/process/three-authoritative-data-sources.md) — all data enters via PDF/CSV statements, activity CSVs, or Robinhood paste
- [Check Data Freshness First, and Ask For What Is Missing](playbook/universal/process/check-freshness-and-ask-first.md) — stale data looks like a real number; check MAX(date) per stream up front and request the file or reconnect, don't wait to be corrected
- [A Recurring Line That Vanishes Is a Data Defect](playbook/universal/process/missing-recurring-line-is-a-defect.md) — check expected lines mechanically and flag the gap in red; know the cadence first (school bills Sep–May)
- [Check Derived Tables Before Declaring "No Data"](playbook/universal/process/check-derived-tables-before-declaring-no-data.md) — w2_records, tax returns, margin table, processed folders and the ingestion log before "not on file"; the 2024 W-2s were there all along
- [Verify a Suspected Gap Against the Source Before Asking](playbook/universal/process/verify-a-gap-against-the-source-before-asking.md) — a zero is a hypothesis: check the broker's realized-trade record and the archived export; Mar–Apr 2025 options were real quiet, not a missing import
- [Test a Strategy Engine Live, Beside the Old One](playbook/universal/process/test-a-strategy-engine-live-beside-the-old-one.md) — preview page beside the live one; one observation at a time during trading; explain, one question, agree, encode as a knob, push
- [Reconcile the Forecast to the Filed Document Line by Line](playbook/universal/process/reconcile-forecast-to-the-filed-return.md) — table, formula check on the document's inputs, waterfall, classify each gap (bug / data / assumption / formula / definition)

### Technical
- [No Direct DB Modifications](playbook/universal/technical/no-direct-db-modifications.md) — all data changes must come from authoritative sources
- [Document Philosophy Before Coding](playbook/universal/technical/document-philosophy-before-coding.md) — write spec docs before implementing algorithms
- [Algorithm Upgrade Checklist](playbook/universal/technical/algorithm-upgrade-checklist.md) — verify all dependent systems when upgrading algorithms
- [Deduplication: Hybrid Crossover](playbook/universal/technical/deduplication-hybrid-crossover.md) — per-type crossover + count-based matching for CSV imports
- [Cross-Source Dedup Type Normalization](playbook/universal/technical/cross-source-dedup-type-normalization.md) — normalize type codes before hashing; CSV vs MCP hash schemes let duplicates through (NFLX split incident)
- [Assignment Rows Require CSV Freshness](playbook/universal/technical/assignment-rows-require-csv-freshness.md) — assignments only arrive via official CSV; stale CSV = lots drift from holdings
- [Market Data Source Order](playbook/universal/technical/market-data-source-order.md) — Robinhood MCP first, Schwab second, Yahoo never on must-succeed paths (repeated rate-limit failures)
- [Validate a Parser Against the Source Document's Own Totals](playbook/universal/technical/validate-parser-against-source-totals.md) — sum extracted rows against the statement's printed summary and abort on mismatch; a row regex fails silently
- [Derived Tables Need an Explicit Rebuild Trigger](playbook/universal/technical/derived-tables-need-a-rebuild-trigger.md) — hook the rebuild to whoever actually writes the source rows; a manual script is not a trigger
- [One Definition Per Stored Series](playbook/universal/technical/one-definition-per-stored-series.md) — every writer of a value column produces the same quantity, components stored explicitly; portfolio_value switched from net to securities-only when daily rows took over and margin read as growth
- [A Forced Recompute Clears the Cache First](playbook/universal/technical/forced-recompute-clears-the-cache.md) — upsert-only caches keep rows that stopped being produced; force deletes all, or key rows on a settings hash
- [Route Statement Pages by Account Number, Never Ship a No-Op Parser](playbook/universal/technical/route-statement-pages-by-account-number.md) — Robinhood PDFs are combined statements; map each page's account number; a parser that returns nothing on purpose is a silent gap
- [A Synthesised Series Needs a Control Total Inside the Period](playbook/universal/technical/synthesised-series-need-in-period-control-totals.md) — a backfill that reconciled only at the seam was $217K–$458K high for ten months; check every in-period statement and abort on a miss
- [Lot Quantities Are Post-Split Units](playbook/universal/technical/lot-quantities-are-post-split-units.md) — stock_lot scales open lots at a split; replay transactions for as-of-day share counts and price them raw
- [Filter to Taxable Accounts at Every Source That Feeds a Tax Number](playbook/universal/technical/filter-taxable-accounts-at-every-tax-source.md) — shared engines include all accounts by design; the tax path passes an explicit scope (87K IRA-gain leak, TY2025)
- [The Same Fact Under Two Spellings Is a Duplicate](playbook/universal/technical/same-fact-two-spellings-is-a-duplicate.md) — canonical category keys + upsert per key; two rental-expense batches double-counted 7,090

## Playbook — Project-Specific

### Tax
- [How We Do Taxes — Annual Cycle](playbook/project-specific/tax/README.md) — the cycle from forecasting to CPA package to post-filing reconciliation; links every tax rule
- [Option Premium Is Taxed When the Position Closes](playbook/project-specific/tax/option-premium-is-taxed-when-the-position-closes.md) — income at collection, tax at BTC/expiry/assignment; assigned-put premium defers into share basis; no count-based closure rates
- [California Is Its Own Computation](playbook/project-specific/tax/california-is-its-own-computation.md) — HSA add-back, CA standard deduction, FTB rate schedule (2025 Schedule Y listed), exemption credits, FTB 5805
- ["Total Tax" Means the Return Total](playbook/project-specific/tax/total-tax-means-the-return-total.md) — 1040 line 24 + 540 line 64; payroll withholding is a separate informational line
- [MAGI Cliffs Drive Decisions](playbook/project-specific/tax/magi-cliffs-drive-decisions.md) — EV credit 300K, NIIT 250K, IRA phase-outs, CTC 400K; show headroom, flag when forecast error exceeds it
- [A 1099-R Gross Distribution Is Not Income Until the Code Says So](playbook/project-specific/tax/gross-1099-r-is-not-income.md) — code G rollovers and 8606 conversions are 0 taxable; 130K of gross on the TY2025 return

---

## Wiki — Companies
- [FanbaseAI, Inc.](wiki/companies/fanbase-ai.md) — Delaware C-Corp, dissolving, Section 1244 eligible

## Wiki — People
- [Neel Kamal](wiki/people/neel-kamal.md) — primary user/developer, options trader, family finance manager

## Wiki — Concepts
- [Buy-Borrow-Die Strategy](wiki/concepts/buy-borrow-die.md) — buy assets, borrow against them, avoid capital gains
- [AI Value-Chain Thesis](wiki/concepts/ai-value-chain-thesis.md) — 50% AI value chain (hyperscalers, GPUs, TSMC, custom ASIC, inference memory+networking) / 50% core AAPL-TSLA-SpaceX; stated 2026-08-08
- [Options Selling Strategy](wiki/concepts/options-selling-strategy.md) — weekly income via covered calls/puts, V6 algorithm (puts primary, runaway vs. oscillating, account-type delta)
- [Data Ingestion Pipeline](wiki/concepts/data-ingestion-pipeline.md) — file-based import with automatic deduplication
- [Communication Agent](wiki/concepts/communication-agent.md) — Gmail/Calendar/Drive MCP integration; drafts email, manages calendar, preferences captured iteratively

## North Star
- [Application Objectives](../docs/OBJECTIVES.md) — what the app is for: unified income (fixed + dynamic), options execution vs 1%/2% monthly targets, trillion-club investment policy, spending categorization, BBD adherence
- [Income Unification Spec](../docs/INCOME-UNIFICATION-SPEC.md) — agreed income definition (realized-only, all accounts, call-assignment = income at sale) and design for the unified weekly/monthly/annual view
- [Options Execution Page Spec](../docs/OPTIONS-EXECUTION-PAGE-SPEC.md) — test question, one-feed/two-renderers (email = queue's urgent slice), 4-level hierarchy, staged V6 build
- [Investments Page Spec](../docs/INVESTMENTS-PAGE-SPEC.md) — pure price performance excluding income (value − cost basis, exact not approximated), winners/losers, trillion-club policy deferred (no market-cap source exists)
- [Spending Page Spec](../docs/SPENDING-PAGE-SPEC.md) — one definition (classify(): counterparty → refund → kind → label), period attribution for rent, per-account freshness, cash movements from statement PDFs
- [Spending Page Audit 2026-09](../docs/SPENDING-PAGE-AUDIT-2026-09.md) — the incidents behind the rules above (rent as Transfer, refunds as income, dead outflows), what was fixed, what is still open
- [2025 Tax Return Reconciliation](../docs/2025-TAX-RETURN-RECONCILIATION.md) — filed return vs forecast line by line: 54% miss, waterfall, root causes classified, prioritized fixes
- [2026 Tax Estimate](../docs/2026-TAX-ESTIMATE.md) — as of 2026-09-12: paid to date from paystubs, YTD liability, full-year scenarios, safe-harbor payments due 9/15 and 1/15
- [BBD Page Audit 2026-09](../docs/BBD-PAGE-AUDIT-2026-09.md) — F1 (one portfolio-value definition: net liquidation, signed cash) and F2 (stale cache row) fixed 2026-09-25; still open: margin table stale since Apr 2026, growth $ ignores flows, hard-coded 2025 expenses card, early-2025 options gaps
- [Cleanup Backlog](../docs/CLEANUP-BACKLOG.md) — running list for the cleanup phase: broken tsc build, yfinance migration, dead engines (v2–v4), plaid, god files, docs archive

## Strategy Spec Docs (V6)
- [V6 Philosophy](../docs/OPTIONS-STRATEGY-V6-PHILOSOPHY.md) — the "why": beliefs, lessons, account-type rules, runaway vs. oscillating
- [V6 Engine Spec](../docs/OPTIONS-STRATEGY-V6-ENGINES.md) — the "what": 4-engine decision tables, delta targets, sizing rules
- [V7 Spec — Two Books, Four Layers (preview)](../docs/OPTIONS-STRATEGY-V7-SPEC.md) — long-term ($1T+, never sold, delta 10-15 calls, re-entry puts only) / short-term (named list, delta 20-40 calls, puts on margin); recovery is a notice with a dollar amount; V6 stays live
- [Investment Thesis v2 — working draft](../docs/INVESTMENT-THESIS-V2-DRAFT.md) — the 2026-09-13 conversation, round by round, that produced V7; open questions listed

---

## Raw Data
- See [raw/README.md](raw/README.md) for source documentation

## Artifacts
(none yet)
