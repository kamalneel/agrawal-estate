# Knowledge Base Index

Auto-maintained master index. Updated by Claude when entries are added or removed.

---

## Playbook — Universal

### Communication
- [Preferences Captured Over Time](playbook/universal/communication/preferences-captured-over-time.md) — communication style is iteratively captured, not pre-specified; covers email, notifications, content, personal messages

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

### Process
- [Three Authoritative Data Sources](playbook/universal/process/three-authoritative-data-sources.md) — all data enters via PDF/CSV statements, activity CSVs, or Robinhood paste
- [Check Data Freshness First, and Ask For What Is Missing](playbook/universal/process/check-freshness-and-ask-first.md) — stale data looks like a real number; check MAX(date) per stream up front and request the file or reconnect, don't wait to be corrected
- [A Recurring Line That Vanishes Is a Data Defect](playbook/universal/process/missing-recurring-line-is-a-defect.md) — check expected lines mechanically and flag the gap in red; know the cadence first (school bills Sep–May)

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

## Playbook — Project-Specific

*(none yet)*

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
- [Cleanup Backlog](../docs/CLEANUP-BACKLOG.md) — running list for the cleanup phase: broken tsc build, yfinance migration, dead engines (v2–v4), plaid, god files, docs archive

## Strategy Spec Docs (V6)
- [V6 Philosophy](../docs/OPTIONS-STRATEGY-V6-PHILOSOPHY.md) — the "why": beliefs, lessons, account-type rules, runaway vs. oscillating
- [V6 Engine Spec](../docs/OPTIONS-STRATEGY-V6-ENGINES.md) — the "what": 4-engine decision tables, delta targets, sizing rules

---

## Raw Data
- See [raw/README.md](raw/README.md) for source documentation

## Artifacts
(none yet)
