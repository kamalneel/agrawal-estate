---
scope: universal
project: null
category: technical
applies-to: algorithm implementations, major feature additions
created: 2026-04-06
source-context: "Extracted from docs/ALGORITHM-UPGRADE-BEST-PRACTICES.md — V4 implementation learnings"
---

# Document the Philosophy Before Writing Code

Before implementing any algorithm or major feature, create a specification document covering: foundational beliefs, core philosophy, key principles, decision priority order, anti-patterns, and real examples.

## Why

The V4 algorithm upgrade showed that without a written philosophy, implementation decisions drift. Code that doesn't trace back to documented principles leads to inconsistent behavior and makes debugging harder. The philosophy doc becomes the test oracle.

## How to apply

1. Before writing code, create a spec doc with: (a) one-sentence purpose, (b) 5-8 guiding principles, (c) priority order when principles conflict, (d) anti-patterns with explanations, (e) real scenarios with step-by-step reasoning.
2. Identify ALL dependent systems (`grep` for references) and create a dependency map.
3. Only then begin implementation.
