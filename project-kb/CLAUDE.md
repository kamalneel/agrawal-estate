# Knowledge Base — Instructions for Claude

This file tells Claude how to use the project knowledge base (`project-kb/`).

## At the Start of Any Task

1. **Read applicable playbook rules** from `playbook/universal/` relevant to the task category (design, process, technical).
2. **Read project-specific rules** from `playbook/project-specific/[name]/` if they exist for the entity being worked on.
3. **Read the wiki entry** if one exists for the entity being worked on (check `wiki/companies/`, `wiki/people/`, `wiki/concepts/`).
4. **Announce which rules you loaded** before starting work. Example:
   > Loaded rules: `no-direct-db-modifications`, `always-use-design-tokens`. Wiki: `buy-borrow-die.md`.

Pull on demand — do NOT load the entire KB. Only read what is relevant to the current task.

## During Iteration

When the user corrects you or expresses a preference, flag it inline:

> "Should I capture this as a universal [category] rule, or specific to [project]?"

Keep flags lightweight — one line, no interruption to flow.

## At the End of a Task

Proactively ask: **"What learnings from this session should go into the playbook?"**

- Propose 2-3 candidate entries with suggested scope (universal vs project-specific)
- Wait for user approval before writing
- Update `INDEX.md` when adding entries

## Manual Trigger

When the user says **"capture learnings"** or **"update the KB"**, scan the conversation and propose entries.

## Adding Content

### Playbook Rules

Each rule is a single `.md` file in `playbook/universal/<category>/` or `playbook/project-specific/<project>/`.

Format:

```markdown
---
scope: universal | project-specific
project: <name or null>
category: design | process | technical | other
applies-to: what artifacts this applies to
created: YYYY-MM-DD
source-context: "What we were doing when this was learned"
---

# Rule Name

The rule itself, clearly stated.

## Why
The reason — often a past incident or preference.

## How to apply
When/where this rule kicks in. Specific enough to act on.
```

### Wiki Entries

Each wiki entry is a single `.md` file in `wiki/companies/`, `wiki/people/`, or `wiki/concepts/`.

Format:

```markdown
---
type: company | person | concept
name: <Name>
last-compiled: YYYY-MM-DD
sources: [list of raw files or docs this was compiled from]
---

# Name

## Summary
## Key Details
## What We Know
## Open Questions
## Related Playbook Rules
```

### Raw Data

Place source material in `raw/` with subfolders per source type. Document new sources in `raw/README.md`.

## Updating INDEX.md

After adding any content, update `project-kb/INDEX.md` with a one-line entry under the appropriate section. Keep it concise — this is the master lookup table.

## Key Principles

- **Pull, not push.** Don't load everything — read on-demand based on the task.
- **Atomic entries.** One rule per file. One entity per wiki file.
- **Timestamped and scoped.** Universal vs project-specific determines reuse.
- **Wiki is LLM-maintained.** If a wiki entry is wrong, fix the raw source or recompile.
- **When in doubt, capture.** Small learnings compound across sessions.
