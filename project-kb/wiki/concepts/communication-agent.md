---
type: concept
name: Communication Agent
last-compiled: 2026-05-24
sources: [MCP tool list in Claude Code session, user description 2026-05-24]
---

# Communication Agent

## Summary

Claude Code in the Agrawal Estate Planner project has MCP (Model Context Protocol) integrations that connect it to Neel's Google account (`alyagrawal@gmail.com`). This gives Claude the ability to read, draft, and organize communications across Gmail, Google Calendar, and Google Drive — acting as a personal communication agent.

## Key Details

**Connected account**: alyagrawal@gmail.com

### Gmail Capabilities
- Search and read email threads (`search_threads`, `get_thread`)
- Create email drafts (`create_draft`) — Claude drafts, Neel sends
- List existing drafts (`list_drafts`)
- Manage labels: create, update, delete, apply/remove from messages or threads

### Google Calendar Capabilities
- List calendars and events
- Create, update, and delete events
- Respond to invitations
- Suggest available meeting times

### Google Drive Capabilities
- Authenticate and access Drive files (OAuth flow required)

## What It Cannot Do
- Send emails directly — it only drafts
- Read email attachments
- Access other accounts or identities
- Operate autonomously (always requires a session with Neel)

## Design Intent

The agent is a **personal communication layer**. Initially it operates between Claude and Neel only, but the intent is broader:
- Draft personal relationship communications (family, friends)
- Draft content for video scripts, voiceover, captions
- Handle professional and financial communications
- Surface inbox context before writing anything

Communication **preferences are not specified upfront** — they are captured iteratively as corrections and confirmations accumulate in `playbook/universal/communication/`.

## Related Playbook Rules
- `playbook/universal/communication/preferences-captured-over-time.md` — how preferences are built up over time
