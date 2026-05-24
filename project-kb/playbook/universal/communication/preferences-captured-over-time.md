---
scope: universal
project: null
category: communication
applies-to: email drafts, notifications, video scripts, personal messages, agent responses
created: 2026-05-24
source-context: "KB design session — establishing communication category. Preferences to be captured iteratively as patterns emerge across email, content creation, and personal relationships."
---

# Communication Preferences Are Captured Iteratively

Do not invent communication style. Capture real preferences as they are expressed during sessions, then encode them as atomic rules in this category.

## Why

Communication style is personal and emerges from real examples, not specifications. Preferences for tone, length, formality, and structure will reveal themselves in corrections and confirmations during actual drafting sessions.

## How to apply

When drafting any communication (email, notification, script, message), use the rules in this category. When Neel corrects a draft or says "more like this", flag it:

> "Should I capture this as a communication rule?"

Add the correction as a new atomic file in `playbook/universal/communication/`. Link it from `INDEX.md`.

## Scope of "Communication"

This category covers all language Neel produces or that is produced on his behalf:
- **Agent-to-Neel**: how Claude responds in sessions (tone, length, format)
- **Email**: drafts created via Gmail MCP agent
- **Notifications**: alerts from the estate planner app
- **Personal relationships**: messages to family, friends
- **Content creation**: video scripts, voiceover language, captions
- **Professional**: any external communication
