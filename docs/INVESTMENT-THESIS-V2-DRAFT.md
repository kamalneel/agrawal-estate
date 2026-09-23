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

## V7 preview built (2026-09-13, night)

Neel: "this can only be tested when we are live during trading hours,
which will be tomorrow. Create another UI of V7 so I can check it."
Built: `data/policy_v2.json`, `backend/app/modules/strategies/v7_engine.py`,
`GET /strategies/v7/preview`, page **More → Notifications V7 (preview)**
(`/strategies/v7-preview`). Spec: `docs/OPTIONS-STRATEGY-V7-SPEC.md`.
V6 untouched and still live. First run on Friday's close: 14 long-term
call cards (AAPL/TSLA/MSFT/IBIT ITM rolls, NVDA $240 buy-backs at 86-89%
captured, AVGO/NVDA waits on RSI, one GOOGL sell), 1 short-term (INTC
$100 ITM, hold to expiry — assumption), 4 short-term puts (MRVL/RKLB in
Neel's, RKLB/SOXL in Jaya's), 2 recovery notices (margin drawn $73,841 /
$131,051). Books read 92.7% / 9.4%.

## 2026-09-15 (Tuesday, trading) — two rules built from live feedback

- **When to roll an ITM long-term call.** Thursday by default; Friday
  morning if RSI > 70; immediately when the expiring contract's time value
  is ≤ $0.10 (early-exercise floor) or the ex-div rule applies; never
  Friday afternoon. Why: the same-strike credit is TV(next) − TV(this),
  and TV(this) decays fastest at the end (AAPL $315: ~$0.75 Tue → ~$0.98
  Thu); every un-rolled day is a day the dip can settle it for free, and
  an early or 2-week roll leaves an at-the-money call to buy back at
  maximum time value when the dip comes. Roll day is relative to each
  contract's own expiry. Applies in every account.
- **Runaway thesis (SPCX).** Neel bought back the $152.50 calls at $3.01
  on non-technical grounds (RSI 67 — technicals said don't). RSI cannot
  be the release (high before and during a runaway; V6 philosophy §6).
  Rule: declare the thesis in `policy_v2.json runaway_theses`; the engine
  stops selling calls on the symbol in every account, shows open calls as
  buy-back-to-uncap, and resolves the thesis at **+5% from the
  declaration price or 10 trading days**, whichever first — then the
  delta 10-15 call goes back on. SPCX declared 2026-09-14 at $151.88 →
  release $159.47 or 2026-09-28.

## 2026-09-15 (later) — winning calls, and knobs

- **Rule A (default for a winning/OTM long-term call):** hold it; on the
  Friday it expires, sell next week's delta 10-15 the same day. No early
  close just because a % threshold crossed — rolling on a down day gives a
  worse strike. The old "60% captured → buy back" trigger is retired.
- **Rule B (the exception):** when the stock is down (today ≤ −1.5% or
  RSI < 45) and the call is cheap (≥ 80% captured), buy back, **do not
  re-sell yet**, wait for the bounce (+2% from the buy-back day's close or
  2 trading days), then sell the delta 10-15 call off the higher price.
  Suppressed inside an earnings window (shares would sit uncovered
  across the date). The engine detects the buy-back from the ledger (BTC
  with no STO after) — nothing to declare.
- **Knobs.** Every number the engine uses now lives in
  `policy_v2.json` "knobs" (26 of them), editable from the gear icon on
  the V7 page; a save writes the file and rebuilds, so git shows every
  change. First candidate to turn: TSLA $390 today is 77% captured on a
  −0.1% day — Rule B does not fire at 80% / −1.5%; Neel's own read was
  "the stock is way down", which is a two-day −2% — a "dip window" knob
  (days) may be wanted.

## 2026-09-16 (Wednesday, trading) — one rule for every name

- **No per-stock windows** (Neel): if a knob needs changing, it changes
  for everyone. So the thing that makes SOXL "special" is measured, not
  named: **20-day realized volatility** from our own daily closes (SOXL
  111%, CBRS 116%, MRVL 88%, INTC/ZM 67%, RKLB 55%).
- **Short-term call delta = RSI base (20/30/40) → mean-reversion override
  (≥5% below the 10-day average → 20; ≥5% above → 40) → × reference vol
  (65%) ÷ the name's realized vol → clamped 10–40.** SOXL today: −5.9%
  vs 10-day → base 20 × 65/111 → **delta 12 → ~$132**, est ~$0.90 (Neel
  had picked $130 at $1.12). INTC: 30 × 65/67 → 29, unchanged.
- **Strike and premium from the name's own volatility and the days to
  expiry** (spot·e^(σ√T·z); Black-Scholes with realized vol as the IV
  stand-in), replacing the fixed %-above-spot tables in both books. AAPL
  delta 12 → ~$346 instead of the table's $351; matches the chain better.
- **New calls go on next Friday when this Friday has < 3 days left**
  (Wednesday: "not this week, but the end of next week").
- **Concentration:** no new short-term put on a name already ≥ 30% of
  the short-term book (holdings + put collateral); ranking prefers the
  names owned least. SOXL at 34.6% with 200 more shares arriving Friday
  was being asked for more — the ranking had looked at RSI only.
- Rule B needs ≥ 4 days to expiry unless the call is ≥ 95% captured
  (free to close): SPCX $160 at 86%, 3 days, 11% of room → Rule A's.
- Knobs: 34 now, six groups, gear icon on the page.
- **Short-term puts, settled (2026-09-16):** the put delta is the mirror
  of the call rule — depressed / oversold name → closer put (base 40),
  extended / overbought → farther (base 20), then × reference vol ÷ the
  name's realized vol, clamped 10–40. Candidates ranked by **return per
  unit of risk** (weekly yield on collateral ÷ volatility, ×1.25 when
  ≥5% below the 10-day average), after the 30% concentration cap.
  Today: ZM $90 (delta 39, 2.2%/wk) > RKLB $61 (35, 1.5%) > CBRS > MRVL;
  SOXL and INTC capped. Neel's example — "Zoom is at its monthly low, the
  chance it goes down more is low, so the return is solid" — is the ZM
  row. The engine's old ranking (RSI entry, then least owned) had put
  RKLB first by accident. V6's ATM put strike retired.
- **Long-term calls wait while RSI < 40** (restores the RSI half of V6's
  entry gate; the "two +3% sessions" half stays retired). AVGO: bought
  back Monday at ~$345, $341 now, RSI 34, only −2.7% vs a 10-day average
  that fell with it — a call sold here caps the recovery. NVDA RSI 45 →
  sell. Knob lt_wait_rsi.
- **ITM short puts had no rule at all** (the AVGO $380 put drew no card).
  Now the mirror of the stuck-call rule: never pay intrinsic; roll the
  same strike for a credit on the Thursday of expiry week, immediately
  at the time-value floor; the alternative is assignment (long-term name
  → hold the shares; short-term → then calls), shown with what it would
  cost against the account's room. Planned assignments apply to puts too.

## 2026-09-16 — V7 goes live

Neel: "V7 is shaping up well. I hardly see myself going back to V6. Put
this in production, both in the UI and in the email." Done via
`settings.LIVE_STRATEGY_ENGINE = "v7"`: the Option Execution page and the
scan emails now carry V7's cards in the queue shape they always used
(priority: ROLL-now/floor → urgent; ROLL, LET ASSIGN, NOTICE → high;
SELL, SELL PUT, BUY BACK → medium; WAIT/HOLD/LET EXPIRE → low). V6 is
one setting away. The preview page stays as the lab. This draft becomes
the working history of V7; the spec is docs/OPTIONS-STRATEGY-V7-SPEC.md.

## 2026-09-17 (Thursday) — puts on everything

- Neel: "we should be selling puts on anything and everything as long as
  it has high volatility and I can earn — include all holdings, short-
  and long-term, in my put bucket." The 2026-09-13 rule "no puts on
  long-term names except re-entry" is **retired**. Concentration is
  handled by the per-name cap (short-term book) and the return/risk
  ranking; a long-term name that assigns grows the long-term book.
- OTM short put at expiry: roll on the last **morning** (SPCX $150: $225
  today vs ~$280 Friday morning — the expiring put's time value bleeds
  out overnight, the new one loses a few percent). Never Friday afternoon.
- MSFT $450 assigns Friday instead of AAPL $322.50 (Neel): MSFT is $50
  ITM, a same-strike roll costs a debit (rule 1); AAPL rolls for +$425.
  Tax: MSFT gain $6,510 (~$2.4K) vs AAPL $41,605 (~$13.8K). Frees $45K.

## 2026-09-19/20 (weekend) — V7 cleanup, one rule at a time

Neel: "there are too many rules and therefore there will be conflicts …
ask me one question, get clear clarity, and then you be responsible for
cleanup and getting to a sane place." Claude's audit found the file had
become a transcript (every rule with its date and its retired
predecessor) and four places stating rules that disagreed. Cleanup runs
one question at a time; each answer is encoded and the retired text
moves here.

- **Re-entry after a call assignment is not automatic.** The dedicated
  Layer-1 "sell a put to re-enter" card is gone. A called-away name goes
  back into the put ranking like any other, judged on (1) which put
  makes money and (2) whether assignment would unbalance the 20% book —
  the per-name cap. Neel's example: SOXL (600 sh) and INTC would
  unbalance; CBRS and MRVL would not. Healthy state = 80/20 with the
  $400K of margin lines selling puts.
- **Short-term ITM call, settled** (was an unconfirmed assumption): on
  the Thursday of expiry week, no roll credit → LET ASSIGN (never pay a
  debit); credit and RSI ≥ 65 → ROLL (overbought, the run is likely to
  come back under the strike — patience); credit and RSI < 65 → LET
  ASSIGN (not stretched; the same money earns more as a put on the
  next-ranked name). Knob `st_assign_rsi` = 65, "a good starting point,
  we fine-tune it as we go." INTC $100 ×4 in Retirement (RSI 63, $504
  credit) → let assign Thursday, $40K back to the ranking. Replaces
  `st_let_assign_dte`.
- **Three buckets, not two** (Neel: "I am not understanding this
  question — let me give my point of view"): **A** long-term shares
  (80%), **B** short-term shares (20%), **C** the put bucket — the $400K
  of margin lines, selling puts on A + B + a put-only list of names in
  neither book ("things that I will come up with"). The 20% is shares
  only; put collateral never counts toward it. Encoded: the 20% throttle
  on new puts is retired (bucket C is bounded by the lines; B over 20% is
  a layer-4 notice and short-term calls assigning is how it comes back);
  `put_only` list added to `policy_v2.json`; a put-only name that
  assigns lands in B and takes the same per-name balance check.
- **Bucket C's first two names: PANW, CRWD** (Neel, 2026-09-20). Daily
  closes since June loaded so they rank with RSI and realized vol; the
  sync prices them with IV from now on. First ranking: PANW #2 in Jaya's
  Brokerage (2 puts ~$330, delta 25, 1.3%/wk).
- **TSM, AMZN, META: out of the long-term book, into put-only** (Neel,
  2026-09-20). "Undecided" since 9/13 is closed; there is no buy program
  in V7 — the way into A is a put from bucket C that assigns. Daily
  closes since June loaded for all three.
- **When to stop rolling a long-term ITM call — settled** (Neel,
  2026-09-20): "whatever goes up comes down, and whatever goes down goes
  up — but *when*, and does it make sense to wait that long? That
  judgment is the technicals'." RSI high → the come-down is near, roll.
  RSI not high and the roll paying next to nothing → the come-down is
  months away and rolling for zero is dead money; weigh the cost of
  leaving, which is **tax only**: zero in the four sheltered accounts;
  in the two brokerages, the gain on the lots Highest Cost delivers —
  negative for TSLA (the $435/$375 lots), ~21% of proceeds for AAPL
  (every lot ~$108). MSFT $450 on 9/18 was the worked example: $40 ITM,
  zero credit, RSI not high, ~$2.4K tax on $45K → left it, puts on MSFT
  are the way back. Encoded as rule 5 with three knobs: `assign_rsi` 65
  (both books; replaces `st_assign_rsi`), `roll_thin_credit_ps` $0.50,
  `lt_assign_max_tax_pct` 10%. The engine now *proposes* the trim with
  the tax figure on the card; planned_assignments stays as Neel's
  override. First run: AAPL $315/$322.50/$325 all "roll — tax 21%";
  IBIT $39 at the floor with RSI 68 → roll now (would be "let assign,
  tax −6.5%" once RSI drops under 65).
- **ITM short put — settled** (Neel, 2026-09-20: "roll, the bounce is
  coming"): the mirror of the call rule. RSI ≤ `put_roll_rsi` (35) →
  oversold, ROLL; roll paying ≥ $0.50/share → ROLL; otherwise the
  recovery is far → take the shares if the account has the room
  (long-term name: held; short-term / put-only: into B, then calls).
  Roll credits are now priced as of Thursday (TV 8 days − TV 1 day):
  the AVGO $380 put had paid $230/$717/$140/$185/$65 on five weekly
  rolls while $18–32 ITM and the engine had said $0.
- Sheltered accounts take the same long-term verdict with tax at zero
  ("yes, let it assign in the sheltered accounts too").

## 2026-09-21 (Monday, trading)

- **SPCX runaway thesis released** after 5 trading days, flat ($151.87
  vs $151.88). Neel: "the runaway moment came from Intel and AMD
  instead." Entries now carry `released`; the engine honours it.
- **Layer-4 margin notice stays as a standing reminder** (Neel).
- META $700 put sold in Jaya's Brokerage (9/25, +$594); META +10% the
  same morning to $732 — already $33 OTM.
- **Runaway baseline, from INTC and AMD 9/14 → 9/18** (for the
  definition of "runaway"):
  INTC $97.19 → $108.60 (+11.7% in 4 sessions; +4.0%, +7.7% on the
  16th/17th, volume 120M → 150M → 175M vs ~90M; RSI 50 → 62).
  AMD $493.41 → $559.82 (+13.5%; +6.4%, +2.7% on the 17th/18th, volume
  22M → 28M → 32M vs ~17M; RSI 51 → 65).
  SPCX same window: $148.15 → $152.71 (+3.1%), RSI 62.
  Common shape: RSI started ~50 (neutral, not overbought), two
  consecutive big up days with volume 1.5–2× the prior average, ending
  around RSI 62–65 — still under the 70 that would make the engine
  "wait". Rolling for credit vs. letting the call go is the question the
  new rule 5 answers; the runaway declaration is for BEFORE the move.

## 2026-09-23 (Wednesday, trading)

- **AAPL in Jaya's Brokerage: keep and roll** (Neel, "change of heart").
  Matches rule 5 as built — the $325 call is $14.29 ITM with RSI 68 and
  a 21.5% tax cost on the lots ($8.26 and $220.50), both above the
  lines, so the engine already said roll. No change.
- **GOOG out, GOOGL in** (Neel): same company, GOOGL is the more
  volatile and far more liquid of the two classes, which is what the
  weekly roll needs. One position, 100 sh in Jaya's Brokerage.
- planned_assignments cleaned: the three 9/18 entries moved to
  `completed`.
- **Up-day early roll needs a time-value guard** (Neel, 2026-09-23, on a
  ZM $95 card): "is there risk of the call at 95 getting assigned? If
  not then shouldn't we wait another day — most of the cost at the
  moment is of the time value." Right: ZM $91.90, the call $3.10 OTM
  with 2 days left, delta 0.21, and every cent of its $0.28-0.42 is time
  value that decays to zero by Friday. The refinement was built on
  "theta timing is a wash", which only holds when the expiring call is
  near worthless. New knob `up_day_roll_max_tv_pct` = **15%**: take the
  up-day roll only when closing costs at most that share of the new
  call's premium. Set low deliberately — the decay you give up is
  near-certain, the better strike is a coin flip. (ZM: 21% on the 6:40
  mark, 31% live, and the bid $0.13 / ask $0.70 spread makes the real
  cost worse — it waits.)
- **Skew ceiling on the put book**, not a balancing objective (Neel:
  "even distribution is not a huge goal — the problem would have been if
  it was heavily skewed. If 50% of the put money was going to Zoom that
  would be wrong; I don't see a problem with the current"). The ranking
  stays purely return/risk; new knob
  `put_max_symbol_pct_of_put_book` = **35%** is a veto, and sizing trims
  contracts to stay under it. Put book today $367K: META 19.1%, PANW
  19.1%, ZM 14.7%, AVGO 10.4%, GOOGL 9.8%, SOXL 8.2%, MRVL 6.3%, CBRS
  5.2%, SPCX 4.1%, RKLB 3.3%. Today's two ZM cards take it to ~24% —
  under the ceiling, so they stand.
