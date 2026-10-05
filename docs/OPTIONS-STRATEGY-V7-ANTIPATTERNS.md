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
