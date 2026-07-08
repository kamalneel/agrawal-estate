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
- [Definition of Income](playbook/universal/finance/definition-of-income.md) — realized-only, all accounts, tax-independent; call assignment = income at sale, put assignment = strike-basis lot

### Process
- [Three Authoritative Data Sources](playbook/universal/process/three-authoritative-data-sources.md) — all data enters via PDF/CSV statements, activity CSVs, or Robinhood paste

### Technical
- [No Direct DB Modifications](playbook/universal/technical/no-direct-db-modifications.md) — all data changes must come from authoritative sources
- [Document Philosophy Before Coding](playbook/universal/technical/document-philosophy-before-coding.md) — write spec docs before implementing algorithms
- [Algorithm Upgrade Checklist](playbook/universal/technical/algorithm-upgrade-checklist.md) — verify all dependent systems when upgrading algorithms
- [Deduplication: Hybrid Crossover](playbook/universal/technical/deduplication-hybrid-crossover.md) — per-type crossover + count-based matching for CSV imports
- [Cross-Source Dedup Type Normalization](playbook/universal/technical/cross-source-dedup-type-normalization.md) — normalize type codes before hashing; CSV vs MCP hash schemes let duplicates through (NFLX split incident)
- [Assignment Rows Require CSV Freshness](playbook/universal/technical/assignment-rows-require-csv-freshness.md) — assignments only arrive via official CSV; stale CSV = lots drift from holdings
- [Market Data Source Order](playbook/universal/technical/market-data-source-order.md) — Robinhood MCP first, Schwab second, Yahoo never on must-succeed paths (repeated rate-limit failures)

## Playbook — Project-Specific

*(none yet)*

---

## Wiki — Companies
- [FanbaseAI, Inc.](wiki/companies/fanbase-ai.md) — Delaware C-Corp, dissolving, Section 1244 eligible

## Wiki — People
- [Neel Kamal](wiki/people/neel-kamal.md) — primary user/developer, options trader, family finance manager

## Wiki — Concepts
- [Buy-Borrow-Die Strategy](wiki/concepts/buy-borrow-die.md) — buy assets, borrow against them, avoid capital gains
- [Options Selling Strategy](wiki/concepts/options-selling-strategy.md) — weekly income via covered calls/puts, V6 algorithm (puts primary, runaway vs. oscillating, account-type delta)
- [Data Ingestion Pipeline](wiki/concepts/data-ingestion-pipeline.md) — file-based import with automatic deduplication
- [Communication Agent](wiki/concepts/communication-agent.md) — Gmail/Calendar/Drive MCP integration; drafts email, manages calendar, preferences captured iteratively

## North Star
- [Application Objectives](../docs/OBJECTIVES.md) — what the app is for: unified income (fixed + dynamic), options execution vs 1%/2% monthly targets, trillion-club investment policy, spending categorization, BBD adherence
- [Income Unification Spec](../docs/INCOME-UNIFICATION-SPEC.md) — agreed income definition (realized-only, all accounts, call-assignment = income at sale) and design for the unified weekly/monthly/annual view
- [Options Execution Page Spec](../docs/OPTIONS-EXECUTION-PAGE-SPEC.md) — test question, one-feed/two-renderers (email = queue's urgent slice), 4-level hierarchy, staged V6 build
- [Cleanup Backlog](../docs/CLEANUP-BACKLOG.md) — running list for the cleanup phase: broken tsc build, yfinance migration, dead engines (v2–v4), plaid, god files, docs archive

## Strategy Spec Docs (V6)
- [V6 Philosophy](../docs/OPTIONS-STRATEGY-V6-PHILOSOPHY.md) — the "why": beliefs, lessons, account-type rules, runaway vs. oscillating
- [V6 Engine Spec](../docs/OPTIONS-STRATEGY-V6-ENGINES.md) — the "what": 4-engine decision tables, delta targets, sizing rules

---

## Raw Data
- See [raw/README.md](raw/README.md) for source documentation

## Artifacts
(none yet)
