---
type: concept
name: AI Value-Chain Thesis (50/50 Allocation)
last-compiled: 2026-08-08
sources: ["Neel, 2026-08-08 — 'we need to invest in these eight companies... which are going to make money on AI'"]
---

# AI Value-Chain Thesis (50/50 Allocation)

## Summary
Neel's stated equity policy as of 2026-08-08: **50% of the portfolio into
the AI value chain, 50% into the existing core (AAPL, TSLA, SpaceX).**
The thesis is deliberately *not* "chip stocks" — it's "who captures the
economics of AI," layer by layer, from cloud down to the interconnect.

## The four layers (AI half)

| Layer | Rationale | Names |
|---|---|---|
| Hyperscalers | Capture the most AI revenue, closest to the customer | AMZN (AWS), MSFT (Azure), GOOGL (Google Cloud) |
| GPUs | The compute itself | NVDA, AMD |
| Fab & core infrastructure | Whoever physically produces the chip | TSM (= TSMC; TSM is the NYSE ADR ticker) |
| Custom ASIC | In-house accelerators + switching silicon | AVGO |
| Inference beneficiaries | Inference shifts value to memory + interconnect | MU (memory), MRVL (networking) |

## The core half
AAPL, TSLA, SPCX — held for their own reasons, not part of the AI thesis.
Target 50% combined; per-name split inside the core was not specified.

## Resolved 2026-08-08 (same session)
- **AVGO is in**, as its own custom-ASIC layer. Nine names total.
- **ASML is out.** Neel's reason: "it doesn't fit, given that it is
  international." Note the tension — TSMC is Taiwanese and stays in; both
  trade in the US as ADRs, so the international objection applies to
  ASML alone by Neel's decision, not by a general rule. Don't generalize
  "no international" from this.
- **TSM = TSMC.** TSM is just the NYSE ADR ticker; there is nothing to add.

## Sizing
All nine names size in round lots of 100 — see
[Buy in Round Lots of 100 Shares](../../playbook/universal/finance/buy-in-round-lots-of-100.md).
This makes exact equal weighting impossible: MU at ~$878/share has an
$87,756 floor, so it lands ~3.9% while the equal-weight target is 5.56%.

## Weighting: premium-tilted, not equal (2026-08-08)
Neel: "we do not have to make it equal… what distribution will give me the
best chance to maximize my call earnings?" Weight within the AI half is
**proportional to covered-call premium yield**, then rounded to 100-share
lots. Yield is computed at the V6 taxable Tier-1 target (delta 15, weekly).

Caveat that must accompany any such table: with Schwab tokens expired and
yfinance broken, there is **no live IV source** — yields are modeled from
realized volatility (50/50 blend of 1y and 60d) via Black-Scholes. The
*ranking* is robust; the absolute yields are not. Fix the data source
before treating the numbers as tradeable.

## Implementation (built 2026-08-08)
- Targets: `data/allocation_targets.json` (declared share counts, round lots).
- Service: `app/modules/investments/allocation_service.py` →
  `GET /api/v1/investments/allocation-plan`.
- UI: "Allocation Targets" section on the Investments page, above Winners &
  Losers. Spec: `docs/INVESTMENTS-PAGE-SPEC.md`, "Allocation targets &
  execution".
- Strike/premium come from `app/shared/services/option_premium.py`, shared
  with `v6_engine` so Investments and Options Execution cannot disagree.

## How to apply
- Positions outside both buckets are off-thesis by construction: as of
  2026-08-08 that's INTC, IBIT, LLY, RKLB, FIG (~$158K).
- Weights come from `get_pure_performance()`
  (`app/shared/services/cost_basis_service.py`). SPCX has no live quote —
  hold it at cost basis and say so, or the denominator is wrong.
- This is a target, not a trade instruction. Neel sells via options
  (see [Options Selling Strategy](options-selling-strategy.md)), so
  trimming NVDA/AAPL/TSLA toward target should route through covered calls
  rather than outright sales where possible.
