---
scope: universal
project: null
category: finance
applies-to: any allocation target, rebalance suggestion, or buy recommendation
created: 2026-08-08
source-context: "AI value-chain allocation — Neel: 'I generally want to buy in the quantity of 100 because I want to sell options on those.'"
---

# Buy in Round Lots of 100 Shares

Every equity position should be a multiple of 100 shares, with **100 as the
hard floor**. Never propose a target in dollars alone — convert it to a
share count rounded to the nearest 100, then report the dollar figure that
share count actually implies.

## Why

One option contract = 100 shares. A position of 40 or 250 shares cannot be
fully worked with covered calls; the odd lot is dead capital in a portfolio
whose income engine is options selling. See
[Options Selling Strategy](../../../wiki/concepts/options-selling-strategy.md).

## How to apply

- Target shares = `max(100, round(target_dollars / price / 100) * 100)`.
- State the resulting dollar amount and % — round-lot granularity will not
  land exactly on an equal-weight target, and that gap is real, not a
  rounding display artifact.
- High-priced names are the binding constraint: at $877/share, MU's minimum
  viable position is $87,756 — you cannot express a 1.5% allocation in it.
  Call this out rather than silently proposing a sub-100 lot.
- The floor applies to names being *added* too: "start a position" means
  buy at least 100 shares, not a token amount.
