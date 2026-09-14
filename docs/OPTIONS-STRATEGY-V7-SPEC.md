# Options Strategy V7 — Two Books, Four Layers (PREVIEW)

Status: **preview, 2026-09-13.** V6 stays the live notification engine
(`v6_engine.py`, `investment_policy.json`, `allocation_targets.json`,
`docs/OPTIONS-STRATEGY-V6-*.md`). V7 runs beside it and feeds only the
**Notifications V7 (preview)** page (`/strategies/v7-preview`,
`GET /api/v1/strategies/v7/preview`). Nothing switches until Neel has
watched it against V6 during live trading days and says so.

Every rule below was stated by Neel in the conversation recorded in
[INVESTMENT-THESIS-V2-DRAFT.md](INVESTMENT-THESIS-V2-DRAFT.md); the
policy that drives the engine is `data/policy_v2.json`. Where Neel has
not spoken, the engine makes an assumption and **labels the card**
("assumption" chip); those are listed at the end.

## The model

| | Long-term book (~80%) | Short-term book (~20%) |
|---|---|---|
| Membership | $1T+ market cap, or override (AMD). TSLA AAPL SPCX NVDA AVGO AMD MSFT GOOG/GOOGL MU IBIT LLY | A named list: INTC SOXL RKLB CBRS ZM MRVL |
| Shares | Never sold | Come and go |
| Calls | Delta 10-15 (TSLA 10-12, RSI > 75), consistently, on all of them | Delta 20-40, technicals pick the number; low RSI → nearer 20; never ATM; same rule for assigned or bought shares |
| Puts | Only to re-enter after a call assignment; if assigned, hold | Against cash and margin, to maximise option income |
| Buy gaps | Shares, from trim proceeds — never puts | — |
| Stuck ITM call | Roll weekly, same strike, credit; never pay intrinsic. Buy back on the dip (time value is not penalty). Roll before ex-div 3-4 weeks out | *assumption:* let assign at expiry, re-enter with a put |

Margin (Neel $250K, Jaya $150K) is for puts, and puts are for the
short-term book. Operating assumption: what goes up comes down.

## The four layers

1. **Long-term calls** — SELL / WAIT (RSI), ROLL (ITM, weekly, same
   strike), ROLL 4 weeks (ex-div within 10 days), BUY BACK (≥60% of the
   premium captured, ≥2 DTE), SELL PUT to re-enter (call assignment in
   the last 14 days).
2. **Short-term calls** — SELL at delta 20/30/40 by RSI (<40 / 40-55 /
   >55); HOLD then LET ASSIGN when ITM at expiry (assumption).
3. **Short-term puts** — per account: capacity = margin line + cash −
   open collateral − margin drawn; candidates ranked by RSI entry
   (favourable < 50); max 2 contracts per card; none once the short-term
   book is ≥ 20%.
4. **Recovery** — notices, never picks: "Margin drawn by $X in
   {account}" with the line, collateral and cash; "short-term book above
   20%"; held names on neither list.

## What V7 retires from V6

Tier-2 "delta 80, assignment is the plan" calls · Tier-1 (mega-cap) put
rules · Engine 6 "free collateral on off-thesis puts" · the buy program's
ATM puts on long-term names · Engine 4's "prefer a small debit to
compress" for long-term names · the `core`/`inventory` and five-bucket
schemas.

## Assumptions to confirm with Neel

- Short-term stuck-call rule (preview: let assign at expiry).
- Short-term put strike (preview: V6's ATM whole-dollar).
- Cost-basis floor on short-term calls (preview: kept from V6).
- TSM / AMZN / META — still long-term share-purchase targets?
- Ex-dividend dates other than AVGO are projected; confirm each in the
  week before.

## Going live (not yet)

`LIVE_STRATEGY_ENGINE=v6|v7` in settings selects which queue feeds the
email notification and Option Execution page. Revert is flipping it
back. Before that: fixture tests for each rule above, and a replay of V7
against stored snapshots next to what V6 actually said.
