# V7 — What Not To Do

Status: **open thread, started 2026-10-04.** Neel: *"Basically my V7 is made
of what to do. Let's enrich that with rules on what not to do using my past
data and learning."*

[OPTIONS-STRATEGY-V7-SPEC.md](OPTIONS-STRATEGY-V7-SPEC.md) is the rulebook
of what to do. This is its mirror: patterns the last 18 months of real
trades say cost money. Every entry carries the evidence, because the point
is to argue with the data rather than with memory.

**House rule for this thread** (Neel, 2026-10-04): *"For every rule on what
not to do we come up with, give me evidence from my data to show the
hurt."* No entry without a dollar figure traced to real fills. A pattern
that cannot be priced from the ledger is a hypothesis and belongs in the
open questions at the bottom, not in the numbered rules.

**Data window:** 2026-04-01 → today. Buy-to-close records start
2025-05-16, so anything earlier would show premium with no cost against it
and is excluded. 2,400 sell-to-open and 2,017 buy-to-close rows; 78
assignments.

**The headline the thread exists to explain:**

| Period | Calls net | Puts net | Total |
|---|---|---|---|
| Apr 2025 – Apr 2026 | +$189,674 | −$13,142 | +$176,532 |
| **May 2026 (melt-up)** | **−$384,787** | +$41,269 | **−$343,517** |
| Jun 2026 – today | +$83,525 | −$29,532 | +$53,993 |

Net premium collected over the window is **+$428,744** of real cash. Set
against what assignments cost — upside given up on calls, overpayment on
puts — the program is roughly **−$113,000 versus having done nothing**.
Excluding May 2026 it is **+$230,525**. One month is 94% of every dollar
covered calls have cost.

---

## 1. Do not assume mean reversion on the long-term book

Neel raised this himself and half-answered it: *"Do not sell too quickly
(like I did for Nvidia and Tesla) — but is that really a learning, because
MU and a few others never got back like Tesla and Nvidia did?"*

The data says it is a learning, and a sharper one than "don't sell too
quickly." Of the 19 call assignments that cost more than $2,000 in given-up
upside, **15 never traded back under the strike within 13 weeks**:

| Came back under the strike | Never did |
|---|---|
| RKLB $85, $90, $85 · AAPL $285 | NVDA $160, $180 ×2 · MU $330 · AVGO $325 ×3 · GOOGL $302 · MSFT $450 · TSLA $335, $340 · CRCL, HOOD ×2, PLTR |

The four that reverted are **RKLB three times and AAPL once** — the
high-volatility short-term name, plus the one mega-cap that chopped
sideways. Everything in the mega-cap long-term book that ran, kept running.
MU was called at $330 and sits at $1,074.

**The hurt:** the 15 that never came back gave up **$244,867** of upside and
paid **$30,484** of premium to do it — eight dollars lost for every dollar
earned. The 4 that did come back gave up $81,451 against $5,394. So even the
"it came back" cases were not free; the difference is that waiting was
eventually vindicated in four cases out of nineteen.

**The operating assumption — "what goes up comes down" — holds for the
short-term book and fails for the long-term book.** That matters because it
is the stated justification for rolling a stuck call forever rather than
letting it assign. Rule 5's tax test already makes the *decision* well; the
*reason* attached to it is wrong for A names, and a wrong reason will
eventually produce a wrong decision.

**Candidate rule:** on a long-term name, "roll and wait for the dip" needs a
stop — a number of weeks, or a distance above the strike, past which the
assumption is treated as broken. Not yet specified.

## 2. Do not roll the same strike while the stock runs away

Every one of May 2026's disasters was a **long roll chain at a fixed
strike**, set in a quiet week and carried forward as the stock left it
behind:

| Assigned | Strike | Market | Upside given up | Premium earned | Chain |
|---|---|---|---|---|---|
| NVDA | $180 | $236 | **$55,740** | $4,052 | 7 weeks |
| RKLB | $85 | $143 | **$46,784** | $3,714 | 9 weeks |
| MU | $330 | $776 | **$44,601** | $801 | 12 weeks |
| AVGO | $325 ×3 | $414 | **$89,140** | $5,005 | 7 weeks |

MU is the clearest: **twelve weeks of rolling for $801, to give up
$44,601.** The same-strike roll is the right move for a call that is
slightly in the money and will likely come back. It is the wrong move for
one the stock has left for dead, and nothing in the rules currently
distinguishes them by *how far* the stock has run or *how long* the chain
has been carried.

**Candidate rule:** cap the roll chain. Past N weeks at the same strike with
the stock more than X% above it, stop rolling and take the assignment — the
premium is no longer paying for the risk.

## 3. Do not sell puts into a name that is already falling

The mirror finding, and it contradicts a rule currently in the engine. Of
33 put assignments costing more than $2,000, **24 are still under water**:

- **SOXL** $200 and $195 — assigned at $116 and $101
- **SPCX** $205, $200, $168, $165 — four separate assignments, all under
- **AVGO** $460, $460, $450 — three on a single day (2026-06-09), all under
- **TSLA** $435 twice, **GOOGL** $390 twice, **CBRS** $220

Only 9 recovered: RKLB ×4, AVGO $360, AMD $500, NVDA $215, INTC $110, $111.

**The hurt:** the 24 still under water overpaid **$155,880** against market
at the moment of assignment, and collected **$76,208** of premium on those
chains — a two-to-one loss. The 9 that recovered overpaid $40,369 against
$24,524. Note what this says about the premium: it was never small. The
chains that went wrong were well paid and still lost.

Some of this is selection bias — a put only assigns when the stock falls.
But the engine's current rule says a **depressed name (≥5% below its 10-day
average) gets a *closer* put, base delta 40**, on the reasoning that "the
bounce is coming." On this sample the bounce mostly did not come. That rule
should be tested against outcomes rather than assumed.

### Corrected 2026-10-04 — it is EXTENDED names that lose, not depressed

Measuring only puts that *assigned* is selection bias: a put assigns only
when the stock falls. Re-run across **every** put chain since 2025-06,
bucketed by where the stock sat on the day it was sold:

| When sold | Chains | Net premium | Collateral | Weekly yield | Assigned |
|---|---|---|---|---|---|
| Depressed (≥5% below 10-day avg) | 126 | $63,204 | $3,992,000 | 1.58% | **34%** |
| Normal band | 121 | $88,146 | $4,877,200 | **1.81%** | 35% |
| **Extended (≥5% above)** | 95 | $42,757 | $4,452,000 | **0.96%** | **36%** |

Assignment rates are flat across all three — depressed is not more
dangerous, and is marginally the safest. **Extended is the losing bucket:
half the yield of the normal band for the highest assignment rate.**

**Rule, settled 2026-10-04** (Neel: *"skip extended names, put that
collateral into the other two buckets"*): no new put on a name ≥
`mr_threshold_pct` above its 10-day average. Knob `put_skip_extended` = 1.
Today that skips SOXL (+10%) and SPCX (+6%), and the freed collateral
ranks into AVGO, RKLB and ZM instead.

**Still open:** separating "cheap" from "falling." A name below its average
because it chopped is a different trade from one in a sustained downtrend,
and a 10-day average cannot tell them apart — it follows the stock down, so
a steady slide never reads as depressed (AVGO on 2026-09-16: −2.7% against
its average while 6% below the previous Friday).

## 4. Do not repeat a strike on the same name on the same day

**AVGO, 2026-06-09: three put assignments at $460, $450 and $460**, all in
one day, all still under water, $34,000 of combined cost. That is not three
decisions; it is one decision made three times because nothing counted the
exposure across accounts at the time.

The per-name concentration cap (30% of the short-term book) and the
put-book skew ceiling (35%) were both built later and would now catch it.
Listed here so the reason they exist is not forgotten.

## 5. Do not trade names outside the two books

The names in neither book — COIN, HOOD, PLTR, MSTR, CRCL — across **390
contracts**:

| | Premium | Assignment cost | Net |
|---|---|---|---|
| Calls | $32,004 | $23,484 | +$8,520 |
| Puts | $19,797 | $33,606 | −$13,809 |
| | | | **−$5,289** |

Three hundred and ninety contracts of work for a net loss. CRCL alone: a
$200 put assigned with the stock at $67. The books exist because the names
in them are understood; the names outside were traded because the premium
looked good.

## 6. Do not let implied volatility alone pick the name

**The hurt**, measured on assigned chains only — premium earned on the
chain against what the assignment cost at that moment:

| | Overpaid | Premium on those chains | Net |
|---|---|---|---|
| RKLB | $25,150 | $12,232 | **−$12,918** |
| SPCX | $24,060 | $12,347 | **−$11,713** |
| SOXL | $35,626 | $32,340 | **−$3,286** |
| INTC | $6,306 | $5,803 | −$503 |
| CBRS | $3,627 | $5,057 | **+$1,430** |

SOXL is the instructive one. At ~110% implied vol it is the richest premium
on the board and earned **$37,222** across all its puts — and on the chains
that assigned, the premium nearly covered the damage ($32,340 against
$35,626). The vol was paying roughly what the risk cost. RKLB and SPCX were
not: they lost two dollars for every one earned. High IV is the market
pricing a real distribution, not a gift — the question is only whether it
prices it generously enough, and the answer differs by name.

The vol-scaled delta rule (2026-09-16) addresses this by pushing the strike
farther out as vol rises, which is the right shape; this entry records why
it exists.

---

## Open questions for the thread

1. Does rule 1 differ by book, or by market regime? The sample is one
   strong bull market in AI names — 15/19 not reverting may be a fact about
   2025–26 rather than about mega-caps.
2. What is the stop for a same-strike roll chain (rule 2) — weeks, distance,
   or premium-to-risk ratio?
3. Should the "depressed → closer put" rule survive rule 3? It is the
   engine's current behaviour and the data is against it.
4. What is the counterfactual worth measuring: buy-and-hold, or
   buy-and-hold with no options at all? The −$113,000 figure assumes the
   first.

---

## How these ship: V8 runs beside V7

Neel, 2026-10-04: *"Shall we put these new ones in V8 and run it in
parallel so I can give you feedback before moving to V8?"* — the same loop
that built V7 (see `memory/v7-live-trading-feedback-loop.md`).

**V8 is not a fork.** It is the same engine reading `data/policy_v8.json`
layered over `data/policy_v2.json`: V8 inherits every V7 key and overrides
only what it deliberately changes, so a V7 fix reaches V8 automatically and
the two can never drift apart in code. Live V7 is untouched —
`put_skip_extended` back to 0 and `roll_abandon_pct` to 999 in the live
policy.

- `GET /strategies/v8/preview` — the V8 queue, four layers
- `GET /strategies/v8/diff` — what V8 does differently from live V7, card
  by card, which is the point of running them together

### Rules in V8, not in V7

| Rule | Knob | From |
|---|---|---|
| Skip puts on extended names | `put_skip_extended` = 1 | Anti-pattern 3 |
| Stop waiting for the come-down past 20% above the strike (vol-scaled) | `roll_abandon_pct` = 20 | Anti-pattern 2 |
| Skip calls on depressed long-term names | `call_skip_depressed` = 1 | Anti-pattern 8 |
| Skip puts on overbought names (RSI ≥ 65) | `put_skip_overbought` = 1 | Anti-pattern 9 |
| Volatility may only push a put farther out | `put_vol_scale_farther_only` = 1 | Anti-pattern 9 |

### First diff, 2026-10-04

One card changes, and it is the right one:

> **IBIT $39 ×15, Neel's Brokerage.** V7: *roll now, time value $0.08 is at
> the floor.* V8: **let 1,500 shares go** — IBIT is 22% above the strike,
> past the line where this book has never traded back, and Neel's Brokerage
> shows a −6.5% tax on the lots. Mean reversion is off the table and
> leaving is free, so the roll is dead money.

That is the MU pattern caught a week early: IBIT has been rolled at $39 at
the time-value floor repeatedly, for almost nothing, while the stock walked
away from the strike.

---

## 7. Once a put is deep in the money: roll it, do not wheel it

Neel, 2026-10-04, reframing anti-pattern 3: *"The real dilemma for puts is:
once you are in a depressed situation like SOXL, what can you do? (1) Take
the put and start wheeling, or (2) stay hopeful and keep rolling. We can't
really say do not fall prey to the depressed situation, because that would
mean stopping to sell puts altogether."*

Right — depressed situations are not avoidable, they are the business. The
answerable question is what to do once you are in one. **SOXL ran both
experiments at the same time on the same name**, which is as clean a test
as this ledger will ever produce.

Six weeks, 2026-08-26 → today:

| | Capital | Premium banked | Return | Position now |
|---|---|---|---|---|
| **A — kept rolling** the $150 put ×2 | $30,000 | **$2,394** | **7.98%** | SOXL $163.67, the put is now **out of the money** |
| **B — took assignment** at $195/$200, wheeled 400 sh | $78,500 | $1,921 | 2.45% | shares worth $65,468, **−$13,032** |

Rolling returned **three times** as much per dollar and ends with the
position resolving for free. Wheeling banked less and carries a $13,032
mark.

**Why, and it is not luck.** Look at the calls sold on those assigned
shares: **$140, $150, $130, $136, $140** — every one *below* the $195–200
the shares cost. Wheeling a depressed name means writing calls under your
own basis, which is not income, it is capitulation in instalments. If they
assign, the loss is realised. SOXL at $163.67 now has those $140 calls
$23 in the money.

This is the same fact anti-pattern 8 measures from the other side: **calls
on depressed names pay almost nothing (0.08%)**, so the call leg of the
wheel has nothing to give exactly when you need it.

**Rule:** while an in-the-money put still rolls for a credit, roll it. Take
assignment when the roll stops paying — not as a strategy for harvesting a
depressed name. The existing `put_roll_rsi` and `roll_thin_credit_ps` tests
already encode this; what was missing was the reason.

## 8. Calls on depressed names earn nothing

Every call chain sold since 2025-06, bucketed by where the stock sat on the
day of sale — the mirror of the put table in anti-pattern 3:

| When sold | Chains | Net premium | Notional | Yield | Assigned |
|---|---|---|---|---|---|
| **Depressed** | 174 | **$14,713** | $19.4M | **0.08%** | 6% |
| Normal | 439 | $97,777 | $72.8M | 0.13% | 8% |
| **Extended** | 238 | **$74,257** | $25.3M | **0.29%** | 14% |

Exactly inverted from puts, and economically obvious once seen: a stock
that has just run has rich call premium and thin put premium.

- **Extended is where call money is made** — 3× the normal band's yield for
  modestly more assignment risk. This vindicates the 2026-10-02 change
  (`lt_delta_mr_step`: extended → sell closer) and argues for pushing it.
- **Depressed is 174 chains of work for $14,713.** On the same name in the
  same week, the *put* paid 1.58% against the call's 0.08% — twenty times
  the return on the other side of the book.

**Candidate rule:** skip calls on depressed long-term names, the mirror of
`put_skip_extended`. Counter-argument on the record: a 6% assignment rate
means the shares are almost never lost, and $14,713 is still $14,713.
Undecided.

## 9. Do not sell a put into an overbought name, and never let volatility pull a put closer

Neel, 2026-10-07, on the live card *"TSM: sell 1 put at ~$465 (delta 36,
#2 by return/risk)"* with TSM at $474.95 after a long run: *"When a stock
is oversold, that is the time to sell puts — for trillion-dollar companies
the decline is cyclical, not catastrophic. TSMC has gone up significantly.
This would have been the time to sell calls, not puts."*

He was right, and the engine's own rule agreed with him before a later step
overrode it. The card's trace: `RSI 69 → base 20 × 65%/36% vol → delta 36`.

1. **RSI 69 → base delta 20.** The farther put for an overbought name.
   Correct.
2. **× vol_reference_pct ÷ the name's vol.** That scaling was written for
   short-term *calls* (a wild name gets a farther strike). Applied to a put
   on a calm mega-cap it multiplies by 65 / 36 = 1.8 and turns the "farther"
   put into a delta-36 put **2% under spot**, closer than a normal-RSI name
   would get. The RSI signal is cancelled and then reversed.
3. **The ranking rewards it.** Candidates rank by weekly yield, and a
   delta-36 put out-yields a delta-20 put on anything, so the error is what
   put TSM at #2.

Anti-pattern 3's measurement says the same thing from the ledger: puts sold
on extended names paid 0.96%/wk at a 36% assignment rate, against 1.81% /
35% in the normal band. The extended test there is distance above the
10-day average (≥ 5%); TSM at RSI 69 was *inside* 5% and slipped through,
and `put_skip_extended` is off in live V7 anyway. Nothing gated on RSI.

**Rules (V8):**

- `put_skip_overbought` = 1 — no new put on a name whose RSI is at or above
  `put_rsi_unfavourable` (65, the same line `assign_rsi` uses to call a name
  overbought). No put at all, rather than a far one: for a put-only name the
  put *is* the entry, and Neel only wants to own it after it has cooled.
  The collateral goes to the next name in the ranking. One rule for every
  name, held or not.
- `put_vol_scale_farther_only` = 1 — for puts, the volatility scaling may
  only lower the delta below the RSI base, never raise it. A volatile name
  still gets a farther put; a calm one keeps its base.

On 2026-10-07 the first rule removes TSM (RSI 69) and NVDA (70) from the put
list. The second changes every calm name below the line — the put lands at
its RSI base instead of up to 1.8× it.
