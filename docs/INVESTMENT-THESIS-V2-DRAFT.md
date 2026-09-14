# Investment Thesis v2 — working draft (NOT policy yet)

Status: **discussion in progress, 2026-09-13.** Nothing in
`data/allocation_targets.json`, `data/investment_policy.json` or the V6
engine changes until Neel and Claude are aligned. This file captures the
conversation as it happens so nothing is lost between sessions. Supersedes
nothing yet; the current policy is
[ai-value-chain-thesis](../project-kb/wiki/concepts/ai-value-chain-thesis.md)
(2026-08-08) and the two-book model in `investment_policy.json`.

## What Neel said (his framing, lightly condensed)

**Round 1.** The old thesis was ownership by AI layer — Physical AI and
Infrastructure AI, everything AI. Now income matters too: a holding that
does not produce income gets treated "softer." Intel has done the best on
the Income tab, so bring it into Infrastructure AI for the time being.
That raises how to decide buy / sell / keep / never-buy. Answer: two
books — **long-term conviction** (TSLA, AAPL, SpaceX, NVDA, AVGO, AMD,
MSFT, GOOG — the trillion-dollar names, still split Physical /
Infrastructure) and **short-term** (no long thesis, its own categories).

**Round 2** (answering "own Intel, or harvest Intel?"). Both: own it
because it produces the best returns, but with a short-term feeling — so
sell puts *and* calls on it.

The model as stated:
- **Long-term book, ~70–80% of the portfolio.** The trillion-dollar names
  with a long game. **Never sold.** Income from dividends and covered
  calls. **No put selling** on these — already own, or should own, as
  much as wanted. Exception: if a call gets assigned, recover (that is a
  put sold to get back in).
- **Short-term book, ~20%.** Names without a long thesis. Return from
  selling calls on owned shares, **and puts sold on margin.**
- **Margin is for puts, and puts are for the short-term book.** Lines:
  Neel brokerage $250K, Jaya brokerage $150K (matches
  `data/goal_settings.json`).

## Facts on the table

- INTC since first trade 2026-04-29 (~4½ months): +$33.2K net premium
  (198 STO/BTC legs, $88K sold / $55K bought back), +$3.3K realized,
  −$9K unrealized on 950 sh / $101.6K basis. ≈ +$27.5K on ~$100K.
- AAPL ($600K of core) produced $15.5K premium YTD 2026 — INTC out-earned
  it ~8:1 per dollar, because INTC is wheeled and AAPL is not.
- 2026 YTD premium by symbol: AVGO 39.5K, SOXL 34.1K, INTC 33.2K, AMD
  25.2K, RKLB 23.5K, MU 19.2K, TSLA 19.0K, SPCX 16.0K, AAPL 15.5K.
- Today's split is already in range: core-ish names ≈ $2.36M of $2.7M
  (≈87%); everything else ≈ $340K (≈13%).
- Margin drawn today: $204,892 of the $400K lines (Neel $73.8K, Jaya
  $131.1K). Cash & collateral net −$127,780. The 2026-09-11 rebalancing
  audit found deployable cash $25K and the largest single securable put
  $21.7K — every buy card unplaceable.
- Current engine contract for INTC: inventory → "Off-thesis — exit, roll
  5 calls → ATM $102." Neel does not want that exit.

## Open questions (one at a time)

1. ~~Own Intel or harvest Intel?~~ → both; short-term feeling; puts and
   calls.
2. **Asked 2026-09-13:** when a short-term put is assigned, what is the
   rule — wheel the shares out with ATM calls (frees the margin for the
   next put) or keep them as short-term holdings the way INTC was kept
   (locks the margin as shares)? Today's $205K of drawn margin is mostly
   kept assignments, which is why the plan's puts cannot be placed.

## Tensions noted, not yet resolved

- "Margin for puts" and "keep what gets assigned" cannot both be true for
  long: every kept assignment converts put capacity into shares.
- The allocation plan acquires long-term names by selling ATM puts
  (MSFT +100, MRVL, TSM, AMZN, ZM). "No puts on the long-term book" needs
  an exception for buy gaps, or the buy program changes to share buys.
- Short-term puts on margin are secured by the long-term shares. A
  sector drawdown assigns the short-term book all at once and the margin
  call lands on the never-sell names. Cushion today is comfortable (Jaya
  69% above maintenance); to be quantified against a −30% semis scenario.
- Income as a selection criterion selects for volatility (SOXL, INTC, MU,
  RKLB lead the premium table). "Softer on non-producers" must apply to
  the short-term book only, or it argues for selling the durables.

## Round 3 (2026-09-13, later)

- Q2 answered: **on a short-term put assignment, go aggressive on calls
  and target assignment — free the margin.** The margin/assignment game
  is for the non-trillion-dollar names only. (This is the inventory wheel
  the engine already runs; the label "Off-thesis — exit" is wrong for
  names Neel wants to keep wheeling — those are a wheel list, re-entered
  by put, not an exit list.)
- Noted: INTC's 950 shares sit in jaya_ira / jaya_roth_ira /
  neel_retirement — **no margin involved**. The $205K of drawn margin is
  in the two brokerages and was consumed by **TSLA put assignments**
  ($435, $375 lots in Jaya's; $435 in Neel's) — puts on a *long-term*
  name, which the new rule ("no puts on the long-term book") forbids.
  The margin problem is the old rule's, not the short-term book's.
- TSLA 300 in Jaya's: agreed to let the 3 × $340 calls (exp 9/18)
  deliver the shares rather than sell and buy the calls back. Lots must
  be the $435/$375 put-assignment lots, not FIFO — see the new rule
  `call-assignment-tax-lot-notice` and the notice service built today.
- **Found while building the notice:** Neel's Brokerage has 15 × AAPL
  $315 and 2 × $322.50 calls expiring 9/18, AAPL at $332 — in the money.
  If left alone that sells **1,700 of 1,800 AAPL** for ~**$354K of
  long-term gain** (no lot choice helps; every lot is ~$108). The plan's
  AAPL trim is 300 shares. Decision needed before Friday: roll them, or
  accept it. Also Neel's TSLA $335 ×1 (swing $35K on lots) and IBIT
  $39 ×15 (a loss either way, 1,400 of 1,500 covered by lots).

## Round 4 (2026-09-13, evening)

- AAPL 9/18 calls in Neel's Brokerage: Neel intends to let the **2 ×
  $322.50** assign (200 sh → ~$64.5K proceeds, ~$43K long-term gain,
  every AAPL lot is ~$108 so lot choice is moot) and use the proceeds to
  take Neel's drawn margin (~$74K) to ≈ zero, then use the line for
  short-term puts. The **15 × $315** — "sell the 15 contract" — read by
  Claude as *roll* (re-sell further out), NOT let 1,500 shares go;
  **confirmation asked**, because the alternative is $311K of gain and
  1,500 of 1,800 AAPL leaving the long-term book.
- Long-term book, puts: **the only reason to sell a put on a
  trillion-dollar name is re-entry after a call assignment.** If such a
  put is assigned, no aggressive calls — the shares are held.
  Consequence Claude flagged: the allocation plan's buy program (MSFT
  +100, TSM, AMZN acquired via ATM puts) is not allowed under this rule;
  buy gaps in the long-term book would be filled by share purchases from
  trim proceeds. To confirm.

## Notifications v2 — Neel's proposed layering (2026-09-13, captured, not built)

Neel: after the thesis is settled, reorganise the notifications into a
**healthy set** that always runs and a **recovery set** that fires when
something goes wrong.

Healthy set (always on):
1. **Calls on the long-term book** — consistently, on all of them; timing
   (when to sell, when to buy back) from technical analysis as today.
2. **Calls on the short-term book, slightly aggressive — delta 20.**
   Goal is option income; *not* proactively seeking assignment, but
   taking more risk for more premium. These names are chosen for the
   short-term bucket precisely because their volatility pays.
3. **Puts on the short-term book** against cash — cash-secured, or
   margin cash — to maximise option income.

Recovery set (fires on a deviation, thinks differently from the three):
4. Something went wrong — e.g. a call was assigned. How to get back to
   the normal state: **80% long-term / 20% short-term, margin reserved
   for puts.** Steps to return to healthy.

### How this maps onto V6 today (docs/OPTIONS-STRATEGY-V6-ENGINES.md)

| Layer | V6 today | What changes |
|---|---|---|
| 1 Long-term calls | Engine 1, Tier 1: delta 10–15 (TSLA 10–12, RSI>75 gate) | Same. Tier 1 list = `investment_policy.json` core. |
| 2 Short-term calls | Engine 1, Tier 2: **delta 80**, "getting called away is the plan" | **Delta 80 → 20.** The short-term book becomes hold-and-harvest, not a wheel-out. |
| 3 Short-term puts | Engine 2, Tier 2: delta 80, RSI<50, 80/20 throttle | Broadly same. **Engine 2 Tier 1 (mega-cap puts) is removed** except re-entry after a call assignment. |
| 4 Recovery | Engine 4 (stuck positions), Engine 5/6 (rebalance, off-thesis collateral) | New concept: a named "deviation → path back to 80/20 + margin ≈ 0" notice, not just per-position stuck handling. |

### Tensions to resolve before building

- **Layer 2 vs Round 3.** Round 3 said: on a short-term put assignment,
  "go aggressive on calls and target an assignment — free the margin."
  Layer 2 says short-term calls are delta 20 and assignment is not
  sought. Both hold only if they apply to different states: **healthy**
  (short-term shares held against cash — e.g. INTC in the IRAs) → delta
  20; **recovery** (shares that arrived by assignment on drawn margin) →
  aggressive calls until the margin is back to ≈ 0. Proposed reading; to
  confirm.
- **Flow imbalance.** Delta-80 puts assign ~80% of the time; delta-20
  calls assign ~20%. The short-term book fills faster than it empties,
  so it will drift past 20% and margin stays drawn. V6's 80/20 throttle
  (no new Tier-2 put once Tier 2 ≥ 20%) is the brake; layer 4 is the
  release. Both need to be real for the system to be stable.
- "Maximise option income" as the put objective selects the most
  volatile names; the 20% cap, not judgement per name, is what bounds
  the risk to the long-term shares that secure the margin.

## Round 5 (2026-09-13, night) — AAPL and the "never pay to get out" principle

- The 15 × $315 = 1,500 AAPL are long-term and **never sold**. Friday:
  the 2 × $322.50 assign (200 sh, ≈$64.5K, Neel's margin → ≈0); the 15
  **roll to next week at $315**, and again, and again.
- General principle (Neel): **never get out of an ITM call by paying a
  debit.** Roll one week at a time, same strike, for a credit, until the
  stock dips below the strike at an expiration and the call expires —
  then resume. One-week granularity so a temporary dip can be used the
  week it happens. Operating assumption: "it will temporarily come down."
- Conflicts with V6 spec Engine 4 ("prefer paying a small debit over
  getting trapped for 3+ months at no cost", "don't fall into the
  12-week trap") — for long-term names the spec must change to Neel's
  principle, or the principle needs a stop condition. To decide.
- Claude's challenge: the penalty is not zero, it is paid as foregone
  upside — every $1 AAPL rises adds $1,500 to the call's intrinsic; at
  $332 that is already $25.5K owed against $315. And early assignment
  around AAPL's ex-dividend (~Nov 10, $0.26/sh) can force the sale when
  a deep-ITM weekly's time value drops below the dividend — rolling
  cannot prevent that. Question asked: what is the rule if it does *not*
  come down — a level at which to pay to roll up, or take assignment and
  re-enter with puts (his own long-term-put exception)?

## Round 6 (2026-09-13, night) — stuck-call rule for the long-term book, settled

Operating assumption (Neel, reaffirmed after challenge): **what goes up
comes down.** The system does not plan for a stock that runs from $330
to $350 to $370 without a dip. When the dip comes, use it.

The rule for an ITM call on a long-term name:
1. **Roll weekly, same strike, for a credit. Never pay intrinsic to get
   out** (a close at $17.90 × 1,500 = $26,850 is the panic-close; not
   done). Weekly cadence so a short dip can be used the week it happens.
2. **Buy back on the dip — time value is not penalty.** If the stock
   drops under the strike mid-week and the call is mostly time value
   (e.g. $1.50 with AAPL at $312), pay it, close, and sell fresh calls
   on the bounce. Do not wait for Friday and risk the bounce first.
3. **Ex-dividend exception:** the roll immediately before an ex-dividend
   date goes **3–4 weeks out** instead of 1, same strike, credit — so the
   call's time value on the day before ex-div exceeds the dividend and
   early exercise does not take the shares. (AAPL: ~Nov 10, $0.26. A
   weekly $17 ITM carries $0.67 today; $20 ITM in November would carry
   ~$0.20 → exercised. A 4-week carries $2–3 → safe.) The dip buy-back
   still applies afterwards, at a little more time value.

Spec note: V6 Engine 4's intrinsic-% table already says "wait" above 80%
(AAPL is at 96%). Its "prefer a small debit" line applies to the 40–60%
crossover — for long-term names that line is superseded by rule 1;
Neel's stop is the dip, not a debit.

## Rounds 7–9 (2026-09-13, late) — short-term calls and margin recovery, settled

- **Buy program (decision 1, taken as settled):** buy gaps in the
  long-term book are filled by buying shares from trim proceeds, never
  by selling puts. The only put on a trillion-dollar name is re-entry
  after a call assignment.
- **Short-term calls: delta 20–40, the technicals pick the number.** Low
  RSI → nearer 20 (the bounce is coming; a 40-delta call "blows up").
  Never at the money. **No distinction** between shares that arrived by
  assignment and shares bought outright — "a short-term call is a
  short-term call." Example: INTC assigned at $90; delta 10 ≈ $100 (the
  long-term treatment), delta 20 ≈ $98, Neel would go ≈ $95, not $92–93.
  → Retires V6 Tier-2 "delta 80, assignment is the plan" and Round 3's
  "go aggressive to free the margin."
- **Layer 4 / margin recovery: a notice, not a recommendation.** When
  margin is drawn beyond what puts are using, the note and the UI say
  *"Margin overdrawn by $X — sell $X of stock to get back to normal"* and
  stop there; which position to sell is Neel's call (he may take more
  risk than the 20–40 window on that one). No urgency: the only cost of
  the abnormal state is lower income — puts earn ~2%/month, calls ~1%,
  so an overdrawn $100K earns call income instead of put income until
  cleared. And a put assignment means the stock dipped, which means it
  comes back.

Remaining open: which names are the short-term book (a list or a rule),
what "softer on non-income producers" means concretely (LLY, IBIT), and
whether the long-term bucket targets change.

## Rounds 10–11 (2026-09-13, late) — the two lists

- **Short-term book is a named list: INTC, SOXL, RKLB, CBRS, ZM, MRVL.**
  (Moves ZM out of `conviction_other` and MRVL out of Infrastructure AI.)
- **Long-term book is the $1T+ rule.** MU, IBIT and LLY are long-term on
  that rule — checked against live Robinhood fundamentals 2026-09-11:
  MU **$1.10T**, LLY **$1.05T**, AVGO $1.72T, TSLA $1.44T. IBIT is a
  fund ($61B AUM) tracking Bitcoin, itself >$1T — long-term by the
  asset, not the wrapper. Sub-$1T for reference: AMD $843B, INTC $544B,
  MRVL $207B, RKLB $38B, ZM $28B.
- Note for the build: the Robinhood MCP `get_equity_fundamentals`
  returns `market_cap` — the Investments spec's "trillion-club policy
  deferred (no market-cap source exists)" is no longer true.
