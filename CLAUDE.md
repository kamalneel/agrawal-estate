# Agrawal Estate Planner — Claude Instructions

## Knowledge Base

This project has a living knowledge base at `project-kb/`. Before starting any task:

1. Read `project-kb/CLAUDE.md` for full KB behavior instructions
2. Read applicable playbook rules from `project-kb/playbook/` relevant to the task
3. Read wiki entries from `project-kb/wiki/` if working on a known entity
4. Announce which rules you loaded before starting work

See `project-kb/INDEX.md` for a master index of all entries.

## Architecture

- **Backend**: Python 3.13 + FastAPI (`backend/`)
- **Frontend**: React + TypeScript + Vite (`frontend/`)
- **Database**: PostgreSQL
- **Docs**: `docs/` — module specs, algorithm docs, design system

## Key Rules

- **No direct DB modifications** — all data comes from authoritative sources (see `project-kb/playbook/universal/technical/no-direct-db-modifications.md`)
- **Use design tokens** — never hardcode colors/spacing (see `project-kb/playbook/universal/design/always-use-design-tokens.md`)
- **Document philosophy before coding** — write specs before implementing algorithms

## Data Flow

Three authoritative data sources feed the system: PDF/CSV statements, activity CSVs, and Robinhood copy-paste. See `docs/DATA_ARCHITECTURE.md` for details.

## Capturing Learnings

During work, flag potential new rules when corrections or preferences are expressed. At the end of a task, propose learnings for the playbook. Say "capture learnings" or "update the KB" to trigger a scan.
