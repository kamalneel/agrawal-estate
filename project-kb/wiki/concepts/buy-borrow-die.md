---
type: concept
name: Buy-Borrow-Die Strategy
last-compiled: 2026-04-06
sources: [docs/apps/BUY-BORROW-DIE.md, docs/BBD-CALCULATIONS.md]
---

# Buy-Borrow-Die Strategy

## Summary
A wealth-building strategy that involves buying appreciating assets, borrowing against them (instead of selling and triggering capital gains), and passing them on with a stepped-up cost basis at death. One of the core strategy modules in the estate planner.

## Key Details
- Dedicated app module: `BUY-BORROW-DIE`
- Has its own calculation engine: `docs/BBD-CALCULATIONS.md`
- Integrates with investment portfolio and real estate modules for collateral tracking
- Tax-optimization focused — avoids realizing capital gains

## What We Know
- Active module in the estate planner
- Uses leverage against existing portfolio positions
- Calculations track loan-to-value ratios, margin requirements, and tax savings

## Open Questions
- Current LTV thresholds and margin call triggers
- Integration with the options selling strategy (premium income servicing debt)

## Related Playbook Rules
- `no-direct-db-modifications` — BBD calculations derive from authoritative portfolio data
