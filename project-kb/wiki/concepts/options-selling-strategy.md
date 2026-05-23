---
type: concept
name: Options Selling Strategy
last-compiled: 2026-05-23
sources: [docs/OPTIONS_STRATEGIES.md, docs/V3-TRADING-PHILOSOPHY.md, docs/OPTIONS-NOTIFICATION-ALGORITHM-V4.md, docs/OPTIONS-STRATEGY-V6-PHILOSOPHY.md, docs/OPTIONS-STRATEGY-V6-ENGINES.md]
---

# Options Selling Strategy

## Summary
A weekly income generation strategy using covered calls and cash-secured puts. The system provides recommendations via a 4-engine architecture. Core philosophy: generate weekly premium income while managing risk through patience and mean reversion. **Puts are now the primary income engine** (V6 shift).

## Key Details
- **Current algorithm**: V6 (V5 was code-only, never documented; V4 archived)
- **V6 spec docs**: `docs/OPTIONS-STRATEGY-V6-PHILOSOPHY.md` (why) + `docs/OPTIONS-STRATEGY-V6-ENGINES.md` (decision tables)
- **Core philosophy**: "Generate weekly income from covered calls/puts while managing risk through patience and mean reversion awareness"
- **Key V6 additions**: Account-type delta targeting, runaway vs. oscillating stock classification, wheel strategy, tax-aware assignment, post-assignment redeployment logic
- **Transaction types**: STO (Sell to Open), BTC (Buy to Close)
- **4 Engines**: Uncovered Calls (1), Cash-Secured Puts (2), Profit Taking (3), Stuck Positions (4)
- **Delta targets**: IRA puts = 70–80, Taxable puts = 90, IRA calls = 30, Taxable calls = 20

## What We Know
- Puts are now primary income engine — put income has outpaced call income in recent months
- Runaway vs. oscillating pattern is the most critical classification before entering any position
  - Runaway (structural catalyst): roll at zero cost, don't panic-close
  - Oscillating (sentiment/macro): use RSI < 40 as entry, expect mean reversion
- TSLA May 2026 lesson: panic-closing 9 contracts cost ~$70K; stock reverted within days
- AVGO May 2026 lesson: rolling at near-zero for weeks is acceptable during a runaway
- Account-type strategy: IRA = aggressive delta, trade freely; Taxable = conservative delta, trillion+ stocks only
- Preferred expirations: weekly (1–2 weeks) for new entries; never extend beyond 4 weeks

## Open Questions
- When to update V6 engine code to match the new delta targets and pattern classification
- RLHF learning system effectiveness metrics

## Related Playbook Rules
- `document-philosophy-before-coding` — originated from V4 upgrade learnings
- `algorithm-upgrade-checklist` — originated from V4 upgrade learnings
