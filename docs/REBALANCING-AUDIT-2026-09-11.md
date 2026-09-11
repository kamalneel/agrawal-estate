# Rebalancing Audit — 2026-09-11

Triggered by Neel: *"It feels like the rebalancing part has taken over my feed,
and other recommendations are suppressed."* Audit of the allocation plan
(`data/allocation_targets.json`, `allocation_service.py`) and its effect on the
V6 action queue.

## Finding 1 — the plan was not executing

Measured from the plan's own `progression` block, since the 2026-08-25 policy date:

| | |
|---|---|
| Days elapsed | 16 |
| Shares needed | 2,562 |
| Shares moved | **58** |
| Gap closed | **2.3%** |
| Weeks to target at that rate | **98.7** |
| Premium collected over the same window | $17,732 |

The 58 shares were SPCX drifting past its own `hold` target — not a trim or buy
anyone executed. Every headline line was at zero: NVDA trim 761 → 0, TSLA 400 → 0,
AAPL 300 → 0, GOOGL 100 → 0, and all 843 buy-side shares → 0.

This is precisely the failure the progression note warns about: *"if premium
climbs and shares do not, the plan is not working no matter how good the income
looks."*

## Finding 2 — the feed was crowded out

Of 22 queue items:

- **77%** were rebalancing-driven (Engine 5/6 or carrying `context.rebalance`)
- **100% of the medium-priority tier** — 8 of 8
- The 5 survivors were all passive Engine 4 WATCH cards. **Zero actionable
  non-rebalancing recommendations remained.**
- Engine 1 emitted nothing.

## Finding 3 — two structural blocks

**Buys were unplaceable.** $305,300 of collateral required against a
`largest_single_put_affordable` of $20,997. Collateral cannot be pooled across
accounts, so all five buy symbols were flagged `unaffordable_today` and sat in
the queue as permanent low-priority noise.

**Trims could not complete.** NVDA needed a 761-share trim with every call at
$240 against a $218 spot — 10% OTM. More fundamentally, the plan's execution
model ("above target → sell ATM calls and get called away") is in direct
conflict with the Tier-1 keep rule and with the tax cost of assignment in
taxable accounts. That contradiction regenerates the same cards indefinitely.

## Decisions taken

### Deferred out of the plan (`deferred_ai` bucket)

| Symbol | Collateral | Reason |
|---|---|---|
| TSM 200 | $83,200 | Never held, stale reference price, unaffordable by 4× |
| AMZN 200 | $54,400 | Never held. Reference $274.48 vs real $251.63 — the engine was recommending a **$272 put on a $251 stock**, an instant deep-ITM assignment. A wrong card, not merely a noisy one. |
| MU 200 | $97,600 | Card targeted Jaya's Roth IRA, which holds **$658** |

Deferred, **not deleted**: deletion would drop them from `_load_wanted_symbols`,
and MU is actually held (~57 sh) — an unlisted symbol reads as off-thesis, so
Engine 6 would begin recommending closes on MU puts. A deferred bucket keeps the
symbol wanted, generates no orders, and is excluded from the progression
denominator.

**Retained**: MSFT and MRVL (MRVL at ~$47k is the nearest to affordable);
NVDA 761 and GOOGL 100 trims, which are the real near-term work.

### Still open — AAPL

The plan wants a 300-share trim. There are **15 contracts open at $315 against a
~$335 spot** in Neel's Brokerage — 1,500 shares against a 300-share target. At a
$108.43 basis even the intended 300-share trim realizes roughly $63,000 of gain.
Either the target or the contract count is wrong. **Awaiting Neel's decision.**

## Engine changes

1. **Unplaceable put cards suppressed** (`v6_engine.py`). A card requiring more
   collateral than any single account can secure is not "low priority," it is
   unplaceable. `_rebalance_lookup` now carries
   `feasibility.largest_single_put_affordable` through as `affordable_ceiling`.
   Fails open on a missing ceiling. The share-buy fallback still fires, so no
   actionable alternative is lost.

2. **Tax-aware roll routing** (`allocation_service.py`) — the highest-value fix.
   Rolling an existing call down to ATM is a decision to deliver those specific
   shares, and was being chosen on strike distance alone; only the naked-share
   path (`_route_trim_lots`) was tax-aware. With the book fully covered,
   `new_contracts` is 0 and *every* leg came through the untaxed path, making the
   tax-aware router dead code for the case that matters. NVDA routed a contract
   to Jaya's Brokerage at a **$18.93 basis (~$19,900 of gain)** when 961 sheltered
   shares were available. Roll legs now sort `(tax, distance)`, sheltered scoring
   0.0 — identical to `_route_trim_lots`, so a harvestable loss in a taxable
   account still correctly outranks a sheltered sale.
   - NVDA: 7 contracts, now **100% sheltered** (Jaya's IRA 6 + Neel's Retirement 1)
   - GOOGL: routes to Jaya's Brokerage, harvesting a **$4,149 loss** rather than
     destroying a $6,149 one inside the IRA

3. **Stale reference prices** (`allocation_service.py`). Two parts: the root
   cause is fixed by adding `symbol_price_history` as a second live price tier
   (MRVL now prices at a real $235.66 instead of the $218.72 reference), and a
   guard withholds any *order* priced off a reference older than 30 days. The row
   still renders — the gap is real, the strike is not. New row field `price_stale`.

4. **Engine 1 suppression narrowed** from symbol-wide to account-scoped
   (`v6_engine.py`). A symbol being trimmed *somewhere* was silencing income
   cards in accounts the trim never touches. Unknown routing keeps the old
   symbol-wide behaviour.

5. **Priority-tier cap — deliberately NOT implemented.** Proposed during the
   audit, then rejected: changes 1–4 fixed the cause, and a blunt cap would hide
   real orders while addressing neither the volume nor the suppression. Left out
   rather than shipped as a workaround.

## Result

| | Before | After |
|---|---|---|
| Queue items | 22 | 22 |
| Rebalancing-driven (broad) | 77% | 64% |
| Engine 5/6 order cards | 59% | **32%** |
| Medium tier that is rebalancing | 100% | 70% |
| Engine 1 income cards | **0** | **3** |
| Put collateral demanded | $305,300 | $70,700 |
| Symbols unaffordable today | 5 | 2 |
| NVDA trim tax exposure | ~$19,900 | **$0** |

The three Engine 1 cards restored are exactly the lots the audit identified as
wrongly suppressed — Jaya's IRA GOOGL 100, the HSA's NVDA 161 — plus SOXL 600.

## Not covered

- The positions board shows Neel's Brokerage with $75,754 "uncovered cash" while
  feasibility reports `deployable_cash: 0` for the same account (it is margin).
  These two numbers disagree about whether there is money. Unresolved.
- No test coverage exists for `allocation_service` or `v6_engine`. All
  verification here was against the live endpoints.
