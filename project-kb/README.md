# Agrawal Estate Planner — Knowledge Base

A living, markdown-based knowledge base for the Agrawal Estate Planner project. Maintained by Claude (LLM), rarely edited by hand.

## Structure

```
project-kb/
├── CLAUDE.md              # How Claude uses this KB
├── README.md              # This file
├── INDEX.md               # Master index of all entries
├── raw/                   # Source data (transcripts, notes, clipped articles)
├── wiki/                  # LLM-compiled knowledge articles
│   ├── companies/         # Entity profiles
│   ├── people/            # People profiles
│   └── concepts/          # Technical and financial concepts
├── playbook/              # Rules & learnings
│   ├── universal/         # Applies to all work
│   │   ├── design/        # UI/UX rules
│   │   ├── process/       # Workflow and methodology rules
│   │   └── technical/     # Code and architecture rules
│   └── project-specific/  # Per-module or per-entity rules
└── artifacts/             # Index of finished outputs
```

## Three Kinds of Content

1. **Raw data** — source material (transcripts, emails, notes, API data). Stored in `raw/`.
2. **Compiled wiki** — LLM-generated knowledge articles. Stored in `wiki/`. Don't edit by hand.
3. **Playbook rules** — learnings from working iterations. Scoped as "universal" or "project-specific". Stored in `playbook/`.

## How It Works

- Claude reads applicable rules and wiki entries at the start of each task.
- During work, Claude flags potential new rules when corrections or preferences are expressed.
- At the end of a task, Claude proposes learnings for the playbook.
- Say **"capture learnings"** or **"update the KB"** to trigger a scan of the conversation.

## Principles

- KB is pulled, not pushed — only load what's relevant to the current task.
- Playbook entries are small and atomic — one rule per file.
- Every learning is timestamped and scoped.
- Wiki is LLM-maintained — fix raw sources to fix wiki entries.
