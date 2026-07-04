# Cleanup & Refactoring Backlog

Running list of cleanup items identified while working toward
[OBJECTIVES.md](OBJECTIVES.md). Work these as a dedicated cleanup phase;
add items here as they surface. Last updated: 2026-07-04.

## Build & tooling

1. **Frontend `npm run build` is broken repo-wide** (predates income work).
   `tsc` fails on every page: missing CSS-module type declarations — add a
   `src/vite-env.d.ts` with `declare module '*.module.css'` — plus dozens of
   accumulated TS6133 unused-import errors. Fix the shim first (one file),
   then sweep unused imports. Until then only `vite build` / dev server work.
2. **Bundle size**: single 1.55 MB JS chunk; code-split the big pages
   (dynamic `import()`), especially IndiaInvestments / OptionsSelling /
   LearningDashboard.

## Data & ingestion

3. **yfinance migration**: move `strategies/yahoo_cache.py` consumers to
   Robinhood MCP / `schwab_service` per the
   [market-data-source-order](../project-kb/playbook/universal/technical/market-data-source-order.md)
   rule. No new yfinance call sites.
4. **Type normalization before hashing** in all parsers + MCP bridge
   (SPL vs SPLIT incident — see cross-source-dedup KB rule) + run the
   duplicate check after any hashing change.
5. **CSV freshness indicator** in the UI (assignments only arrive via
   official CSV; stale CSV = silent lot drift — see KB rule). Include a
   reminder to export the activity CSV monthly.
6. **Rental future-dated rows** (entries through 2027 in
   `rental_monthly_income`): decide projected-vs-actual handling in the
   unified income view (currently reported as-is).
7. **Alisha's account + Fidelity HSA have no transaction feeds** — holdings
   exist with no history; ingest or explicitly mark out-of-scope.

## Dead / redundant code

8. **Retire v2/v3/v4 notification engines** (~5,000 lines) and their
   `algorithm_config` blocks once V6 is implemented as the running engine
   (do together with the V6 work, not before).
9. **Plaid module** (~1,000 backend lines + page + sidebar entry):
   contradicts the file-based-ingestion principle; verify dead and remove.
10. **`/income/stock-lending` endpoint stub** returns zeros while SLIP rows
    exist; wire to the unified query or remove in favor of `/income/unified`.
11. **Duplicate income summary paths**: `db_queries.get_income_summary`
    (authoritative, now complete) vs `services.get_income_summary`
    (dashboard) — consolidate to one.
12. **RLHF/learning system value check** (learning_router 1.8k lines,
    LearningDashboard 2.8k, five RLHF_* docs at repo root): decide keep /
    simplify / drop against the objectives.

## Structure

13. **Split `strategies/router.py`** (6,956 lines, 85 endpoints) into
    per-domain routers.
14. **Decompose god pages**: IndiaInvestments (4.6k), OptionsSelling (4.4k),
    Income (3.7k), LearningDashboard (2.8k).
15. **Root-dir hygiene**: move one-off analyses (DEBUG_FORECAST.md,
    compare_agi.py, AVGO_STRATEGY_ANALYSIS.md, portfolio PDFs, RLHF_* docs,
    loose 1099 PDF) into docs/archive/ and data/; root should hold only
    real entry points.
16. **Docs archive**: OPTIONS-NOTIFICATION-ALGORITHM V1–V4,
    V3-IMPLEMENTATION-NOTES, V3.3-ADDENDUM → docs/archive/ (superseded by
    V6 docs; ALGORITHM-HISTORY.md stays as the index).
