---
scope: universal
project: null
category: communication
applies-to: every report, summary, audit or page produced for Neel or Jaya
created: 2026-09-25
source-context: "Jaya's money summary was published as a claude.ai Artifact; Neel: 'delete it from Claude.ai. I do not want this data to go on a public site.' Repeat of an earlier incident."
---

# Deliverables Stay Local

Financial reports, summaries and audits are delivered as files in this
repo or on this machine — a PDF under `data/documents/reports/`, a markdown
doc under `docs/` — plus a terminal summary. Never publish them as a
claude.ai Artifact or to any hosted page, even a private one, and never
offer to. If a shareable link is wanted, that is Neel's call and his
Google Drive, asked for explicitly.

## Why

Family account balances, salaries and margin positions were put on a
hosted URL without asking. It was private to the account, but that is not
the point: the data left the machine, and there is no delete action for
an artifact, only overwriting it. Neel had said the same thing in an
earlier session. The tool guidance that pushes "finished deliverables" to
a published page does not override this.

## How to apply

- Build reports as HTML rendered to PDF with headless Chrome
  (`/Applications/Google Chrome.app/.../Google Chrome --headless=new
  --print-to-pdf=...`) and save under `data/documents/reports/`, which is
  gitignored.
- Keep prose short: numbers in tables, one or two plain sentences per
  section, an "Inferred" tag on every guess with a checklist at the end.
- Send the file in the conversation (SendUserFile) rather than a link.
- The memory note [[no-claude-ai-artifacts]] records the same rule at the
  user level.
