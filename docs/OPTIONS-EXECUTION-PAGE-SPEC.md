# Options Execution Page — Spec

Status: **approved design, staged build** (Neel, 2026-07-08).
Serves Objective 2 in [OBJECTIVES.md](OBJECTIVES.md); method per
[PAGE-DESIGN-PLAYBOOK.md](PAGE-DESIGN-PLAYBOOK.md); rules from
[OPTIONS-STRATEGY-V6-PHILOSOPHY.md](OPTIONS-STRATEGY-V6-PHILOSOPHY.md) /
[OPTIONS-STRATEGY-V6-ENGINES.md](OPTIONS-STRATEGY-V6-ENGINES.md).

## Test question

> **"What should I do today — and am I on pace for 1%/2%?"**

## Architecture: one feed, two renderers

The V6 engine produces ONE recommendation feed. The **email notification
is the feed's top slice** (urgent+high, changes-only) — its language is
already right (priority dots, SELL/ROLL/CLOSE/ALERT verb badges, one-line
spec, "Earn ~$X", account cards in canonical order). The **page is the
whole feed** plus context email can't carry. Same items, same IDs. When
V6 ships, the email formatter is re-pointed at it (formatter unchanged).

## Hierarchy

- **L1 — This week + pace.** Expiry week (Friday-ending), premium
  collected this week, Goals gauges (reused from Income).
- **L2 — Action Queue.** Replaces Conviction Portfolio, Live Yield
  Monitor, Early Roll Monitor, Put Entry Opportunities, Acquisition Puts
  (approved kill). Header = email summary strip. Items ordered
  urgent → high → medium → low; each: priority dot, verb badge, one-line
  spec, Earn ~$X, expandable "why" (engine + rule + numbers).
- **L3 — Open positions board.** All short options grouped by expiry,
  accounts in canonical order, strike vs stock, capture % (gross
  sold/current), ITM/near/OTM status colors.
- **L4 — History** (collapsed; links into income drills).

## V6 build stages (approved: staged)

1. **Stage 1 (this build): Engines 4 + 1.**
   - Engine 4 (stuck): ITM calls via the intrinsic-% table (<40 normal /
     40–60 evaluate compression / 60–80 wait / >80 alert+wait; compression
     ≤4 weeks, target delta 30, IRA compresses more aggressively).
     Tested puts: DTE≤2 near/ITM → roll out 1 week; deep ITM → roll
     down+out at ~net-zero (oscillating default; runaway = verify thesis).
   - Engine 1 (uncovered calls): uncovered shares ≥100 → SELL, tier-aware
     delta (Tier1 IRA 15Δ / taxable 10–15Δ; TSLA carve-out 10–12Δ + RSI>75
     gate; Tier2 80Δ), strike ≥ avg cost, expiry this/next Friday.
2. Stage 2: Engines 2 (new puts, 80/20 rule, tier sizing) + 3 (profit
   taking) + RSI signals; email re-pointed to V6; v2–v4 retired.

Data: latest synced positions (`sold_options` per-account snapshots,
holdings with synced prices) — no external calls in the request path;
response carries `data_as_of`. Stock prices for unheld symbols are
estimated from deep-ITM marks and flagged `price_estimated`.

## Endpoint

`GET /api/v1/strategies/v6/action-queue` →
`{generated_at, data_as_of, week_ending, summary{urgent,high,medium,low},
items[], positions[]}` — item context keys match the notification
organizer's schema so the email can consume the same feed.
