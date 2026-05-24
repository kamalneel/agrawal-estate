# Knowledge Base Index

Auto-maintained master index. Updated by Claude when entries are added or removed.

---

## Playbook — Universal

### Communication
- [Preferences Captured Over Time](playbook/universal/communication/preferences-captured-over-time.md) — communication style is iteratively captured, not pre-specified; covers email, notifications, content, personal messages

### Design
- [Always Use Design Tokens](playbook/universal/design/always-use-design-tokens.md) — never hardcode colors/spacing, use CSS variables from tokens.css

### Finance
*(no entries yet — add rules for investment philosophy, risk tolerance, financial decision principles)*

### Process
- [Three Authoritative Data Sources](playbook/universal/process/three-authoritative-data-sources.md) — all data enters via PDF/CSV statements, activity CSVs, or Robinhood paste

### Technical
- [No Direct DB Modifications](playbook/universal/technical/no-direct-db-modifications.md) — all data changes must come from authoritative sources
- [Document Philosophy Before Coding](playbook/universal/technical/document-philosophy-before-coding.md) — write spec docs before implementing algorithms
- [Algorithm Upgrade Checklist](playbook/universal/technical/algorithm-upgrade-checklist.md) — verify all dependent systems when upgrading algorithms
- [Deduplication: Hybrid Crossover](playbook/universal/technical/deduplication-hybrid-crossover.md) — per-type crossover + count-based matching for CSV imports

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

## Strategy Spec Docs (V6)
- [V6 Philosophy](../docs/OPTIONS-STRATEGY-V6-PHILOSOPHY.md) — the "why": beliefs, lessons, account-type rules, runaway vs. oscillating
- [V6 Engine Spec](../docs/OPTIONS-STRATEGY-V6-ENGINES.md) — the "what": 4-engine decision tables, delta targets, sizing rules

---

## Raw Data
- See [raw/README.md](raw/README.md) for source documentation

## Artifacts
(none yet)
