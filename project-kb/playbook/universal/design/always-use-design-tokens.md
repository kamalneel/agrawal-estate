---
scope: universal
project: null
category: design
applies-to: all frontend React components, CSS, inline styles
created: 2026-04-06
source-context: "Extracted from docs/UI_DESIGN_SYSTEM.md — design system foundation"
---

# Always Use Design Tokens (CSS Variables)

Never use hardcoded colors, spacing, or font values. Always use the design tokens defined in `frontend/src/styles/tokens.css`.

## Why

The app uses a dark theme with "Agrawal Green" (#00D632) as the accent. Hardcoded values break theme consistency, make updates painful, and create visual inconsistencies across pages.

## How to apply

- Use `var(--color-*)` for all colors (bg, text, accent, semantic)
- Use `var(--space-*)` for spacing (1=4px through 8=32px)
- Use `var(--radius-*)` for border radius
- Use `var(--font-size-*)` for typography
- Reference `docs/UI_DESIGN_SYSTEM.md` for the full token list
- When adding a new component, check existing components for patterns before inventing new styles
