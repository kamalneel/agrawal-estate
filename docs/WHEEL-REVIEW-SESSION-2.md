# Wheel Review — Session 2 (2026-10-23)

Session 1 was `OPTIONS-STRATEGY-V7-ANTIPATTERNS.md`. This one asks a sharper
question, in Neel's words:

> "The net-net for both sides is that I have lost money. At a high level, it
> would look like I'm making a mistake … but that's too high a level read,
> because if I was not doing wheeling, I would not even buy many of these
> stocks. … What are the big items where I made a mistake? Either I should
> not have sold the option to begin with, or I should not have closed it by
> taking a loss, or I should have let it get assigned, or I should have
> deferred it further in time. The competing theory is that I have decided to
> sell every week … I want to put that theory to the question mark."

**Answer in one line:** selling every week is not the problem. The losses are
calls that got stuck in one sharp rally (sold 30 Mar – 8 Apr 2026 at a normal
4–18% out, then rolled one week at a time through April–May). Outside that
rally, stuck calls rolled at the same strike came back and made money.

> **Correction, same day.** The first version of Finding 1 said the March calls
> were sold within 2% of the stock and proposed a 2% floor. That was wrong: the
> weekly price bars are dated Monday but hold Friday's close, so a call sold on
> Monday was compared with a price from later that week — in a rally, a normal
> call looked near the money in hindsight. Neel's question ("is it happening
> because I'm already stuck?") exposed it. Distances now use the prior day's
> close from daily prices (`scripts/wheel_review/daily.py`, `classify.py`).
> Findings 2–4 were then redone on daily prices too; the 13-week-roll result
> shrank to the rally alone, and both V9 candidates were withdrawn.

---

## Method

Every option position was rebuilt as a **roll chain**: the first sale, each
same-day buy-back-and-resell, and how it ended (assigned, expired, bought back,
or still open). 867 chains: 688 calls, 179 puts, Dec 2024 – Oct 2026.

Each chain is scored against the obvious alternative:

- **Calls**: against holding the same shares with no call. Result = net premium
  (every sale minus every buy-back) − upside given up at assignment (market that
  day − strike).
- **Puts**: against not trading. Result = net premium − assignment loss (strike −
  market on the assignment day). A second view values the assigned shares at
  today's price.

Prices: daily closes from Yahoo (`daily.py`), read only through
`daily_prices.py` — "before a trade" is the prior day's close, valuations use the
close on the day. Checks: call premium reconciles to the Income page within $194. Three rows are excluded as duplicates (AMD, Neel's Retirement, 10/5 —
a 3-contract trade also recorded as three 1-contract trades, on both sides).
Scripts: `backend/scripts/wheel_review/`.

## Headline

| | Premium (net) | Given up / lost at assignment | Result |
|---|---|---|---|
| Calls | +$235.6K | −$206.9K | **+$28.7K** |
| Puts | +$252.5K | −$127.8K (assignment day) | **+$124.7K** |
| Puts, assigned shares at today's price | | | **+$53.7K** |

Both sides made money as option strategies. The red numbers on the Investments
page are mostly the *shares* — what assigned stocks did after assignment, and
calls given up in one rally.

## Finding 1 (corrected) — The losses are stuck calls in one rally, not near-the-money sales

Every call sale classified by what it was — **new** (nothing open), **new, next
week** (the previous call had just expired or been bought back cheap), **new after
trouble** (the previous call was assigned or bought back in the money within 4
days), or **roll** (bought back and resold the same day) — and by its distance
from the prior day's close.

**New sales close to the stock were not the problem.** 30 new calls were sold
within 2% of the stock (or in the money): **+$11.6K**. Only 7 got stuck.

**Near-the-money sales are almost all rolls of stuck calls.** Of 228 roll legs
resold in the money or within 2%, 182 were rolling a call that was already in
the money — Neel's pattern: stuck, roll the same strike, wait for the come-down.

**Getting stuck is where the money went — but only in one rally:**

| | Stuck (rolled while in the money) | Never stuck |
|---|---|---|
| Mar–Apr 2026 | 20 chains, **−$232.5K** | 100 chains, +$26.9K |
| Every other month | 59 chains, **+$41.0K** | 509 chains, +$191.4K |

Outside March–April, "what has gone up will come down" held: stuck calls rolled
at the same strike made money. In March–April it did not. The calls themselves
were ordinary when sold:

| Opened | Stock | Strike vs. prior close | Result |
|---|---|---|---|
| 31 Mar | RKLB (Neel's Retirement) | 18.5% out | −$43.1K |
| 30 Mar | NVDA (Jaya's IRA) | 4.5% out | −$41.3K |
| 30 Mar | AVGO (Neel's Brokerage) | 4.8% out | −$33.6K |
| 30 Mar | AVGO (Neel's Retirement) | 4.8% out | −$33.6K |
| 30 Mar | NVDA (Jaya's Brokerage) | 4.5% out | −$26.2K |
| 8 Apr | TSLA (both brokerages) | 8.2% out | −$38.2K |
| 30 Mar | AVGO (Jaya's Brokerage) | 4.8% out | −$16.9K |
| 31 Mar | NVDA (two accounts) | 6.0% out | −$15.3K |

So there is no entry rule to learn here. The question moves to Finding 2: once a
call is stuck, how to tell an ordinary pull-back-and-return from a run that does
not come back — early enough to act.

## Finding 2 — A stuck call: weekly same-strike rolling is right, except in a runaway

Tested at the first roll where the call was ≥5% in the money (53 chains). The
buy-back and let-assign rows use the actual fills; the 13-week roll is priced with
Black-Scholes at the stock's daily realized volatility (no historical option
prices exist).

| Instead of rolling weekly | Mar–Apr 2026 (20) | Other months (33) |
|---|---|---|
| Buy back and stop selling | +$45.4K | **−$111.6K** |
| Let it be assigned | −$82.2K | −$0.6K |
| Roll 13 weeks out, same strike — rolls that have expired | **+$168.6K** (19) | **−$8.0K** (19) |
| Roll 13 weeks out, same strike — still open today | (1) | +$42.7K (14), unsettled |

In ordinary months Neel's patience is the right call: buying back costs far more,
and the long roll is no better on rolls that have run their course. Only in the
March–April rally would something else have paid — buying back, or rolling long.

Depth does not pick out the runaway. Triggering the long roll only at 10% or 15%
in the money still makes ordinary months worse (−$24.5K either way). So there is
no rule here yet: **the open question is what, early on, distinguished the
March–April rally from an ordinary pull-back-and-return** — answered in Finding 5.

## Finding 3 — A stuck put: keep rolling weekly

Same tests on puts (≥5% in the money), ordinary months:

| Instead of rolling weekly | Result |
|---|---|
| Buy back and stop | −$134.3K |
| Let it be assigned | −$178.8K |
| Roll 13 weeks out, same strike (expired rolls) | −$18.3K |

Weekly rolling wins on every comparison. **V8's 8-week put exit**, back-tested on the
9 chains still in the money at week 8: **+$4.5K** — small, slightly positive; its
main case remains freeing margin.

## Finding 4 — Put losses come after assignment, on stocks that had run up

Assigned put chains by the stock's 12-week move before the put was sold (prior
close), with the shares valued today:

| 12 weeks before the sale | Chains | Shares | On assignment day | Today |
|---|---|---|---|---|
| Down or flat | 2 | 300 | −$1.7K | +$10.2K |
| Up 5–20% | 6 | 900 | −$8.9K | +$1.8K |
| Up 20–50% | 6 | 1,100 | −$16.1K | **−$41.3K** |
| Up >50% | 5 | 1,600 | +$8.9K | **−$56.6K** |

Puts sold after a >20% three-month run left 2,700 shares now worth $98K less than
they cost — SOXL, RKLB, AVGO, SPCX, GOOGL. V8's checks look back about 10 days and
miss a three-month run.

As a rule it is still modest: "no put after a >30% 12-week run" would have given up
$133.8K of premium to avoid those chains' −$32.8K today — a net +$32.8K, measured at
today's prices, so it moves with them. Worth discussing as a *farther strike* rather
than *no put*; not proposed yet.

## Finding 5 — The runaway signal: a broad relief rally after a sell-off

The March–April calls were sold while the market was down: QQQ was 11% below its
60-day high on 30–31 March. They then got stuck in a rally that lifted almost
everything at once. In mid-April, 76–79% of the tracked names were up more than 5%
over ten days. The ordinary stuck calls had neither: at the median sale QQQ was
3.5% off its high, and 32% of names were moving together.

**The signal.** All three conditions are known on the day of the roll:

1. when the call was sold, QQQ was ≥7% below its 60-day high;
2. today, ≥60% of the tracked names are up >5% over the last 10 trading days;
3. the call is ≥5% in the money.

A rally out of a sell-off is the market going back to where it was, not
overshooting. So "what has gone up will come down" does not apply.

**Tested on ten years of prices first.** `runaway.py` and `runaway2.py` use daily
closes from 2015 to 2026 for the 31 symbols traded. Each week a call is sold one
weekly standard deviation out. Once it is ≥5% in the money it is rolled weekly at
the same strike, and each roll collects its Black-Scholes time value.

| Stuck call | Episodes | Not back within 13 weeks | Buying back beat rolling | Median waiting cost (% of strike) |
|---|---|---|---|---|
| Signal on | 21 | 76% | **76%** | +21.5% |
| Signal off | 348 | 48% | 39% | −6.9% |

It fired in Feb–Mar 2016, Apr 2020, Jul and Oct 2022, Jan 2023 and Apr–May 2025.
It never fired on the 2026 rally, so it is not fitted to it. It is about equally
strong in both halves: 75% in 2016–2020, 77% in 2021–2026.

**On Neel's own calls** (`runaway_own_rolls.py`). The signal was checked at every
roll while a call was ≥5% in the money:

- It fired on 19 chains, all in the 2026 rally, and on none in ordinary months.
- Buying back at the roll where it first fired, at the actual fill, gives
  −$158.0K instead of −$245.5K: **+$87.5K**.
- It was better on 8 chains, the big ones (AVGO, NVDA, RKLB), and worse on 8
  small ones (HOOD, MSFT, GOOGL −$7.1K, MSTR, COIN, RKLB). On 3 it made no
  difference.
- The 34 chains it did not fire on, including every ordinary stuck call, keep
  their +$24.4K.

It is rare: six episodes in ten years. The universe is today's holdings, which are
survivors, and that flatters "stocks go up". So read the gap between the two rows,
not the levels. Buying back is the exact measure. Rolling long at the signal may do
better, but that cannot be measured without historical option prices.

**The mirror for puts does not hold.** The mirror case is a broad sell-off from
near the highs: QQQ within 3% of its high at the sale, and ≥60% of names down >5%
over 10 days. That covers 30 stuck puts (Mar 2018, Feb 2020, Apr 2024, Feb 2025).
77% came back within 13 weeks, and buying back was better only 10% of the time.
Sell-offs from the highs came back; rallies out of sell-offs did not go back down.
There is no put rule.

**Armed now.** QQQ closed 7.1% below its 60-day high on 23 Oct, so any call sold
now meets condition 1.

## CBRS, 23 October 2026

**Position.**

- 545 shares: 500 from five put contracts assigned at $220, $165, $190 and
  2 × $160 (the two $160s were assigned early today), plus 45 bought.
- Three puts still open in Neel's Brokerage: $160 ×2 (30 Oct) and $175 ×1 (13 Nov).
- The stock is at $113.22, 63% below its first close ($311 on 14 May).
- The campaign so far is −$23.1K.

**What the signal says.**

- **The market part of the fall looks like the kind that came back.** The put
  mirror fires: 68% of names are down >5% in 10 days (SOXL −40%, semis −10 to −17%),
  QQQ is 7.1% off its high, and the puts were sold with QQQ 1–5% off its high. In
  that setup, stuck puts came back 77% of the time.
- **But most of the fall is CBRS's own: −45% in 20 days, against −5% for QQQ.** The
  signal cannot see that part. Stocks in this universe that fell ≥30% in 20 days
  mostly came back (75%), but they are survivors (SOXL, MSTR, COIN, AMD). The slice
  that matches CBRS is stocks within 18 months of listing, and there it is a coin
  flip: of 14 stuck puts, 50% came back. HOOD (Dec 2021), PLTR (2021–22) and FIG
  (Jan 2026) did not. CBRS is 162 days old. Its 14 Oct lock-up release fell in its
  steepest week, and two more releases come on 28 Oct and 9 Nov.
- **At this depth the weekly roll pays nothing.** Time value left is $0.17 on the
  $160s and $0.57 on the $175 (3 weeks out), and V8 estimates the roll credit at
  $0–$2 a contract. Weekly rolling won in Finding 3 because each roll collected time
  value while waiting: about 0.65% of the strike a week in the historical stuck
  puts, and about 0.1% here. Holding these puts amounts to owning 300 more shares at
  $160 and $175 with no income, and they can be assigned any day.

**So the CBRS decision is about size, not timing.** If all three puts are assigned,
the position is 845 shares (about $96K), bought at about $174 on average. Weekly
rolling, letting them be assigned, and buying back (about $15.6K at today's marks)
all carry the same loss today. They differ only in whether the extra 300 shares are
held into the lock-up releases.

**Neel's alternative, and the better way to wait: roll 2–3 months out, not one
week.** Live mid prices at 12:30 PT, with CBRS at $112.34:

| Roll | Credit per share | Market's odds CBRS is above the strike at expiry |
|---|---|---|
| $160 (30 Oct) → $160, 18 Dec | +$2.10 | ~10% |
| $160 (30 Oct) → $160, 15 Jan | **+$3.70** | ~13% |
| $160 (30 Oct) → $155, 15 Jan | −$0.75 | ~15% |
| $175 (13 Nov) → $175, 15 Jan | +$2.15 | ~10% |

The long roll fixes what is wrong with the weekly one at this depth:

- **It gets paid.** About $0.31 a week, against roughly nothing for the weekly
  roll (the 30 Oct put trades at intrinsic).
- **It stops early assignment.** A January put carrying $3.59 of time value is not
  worth exercising early.
- **It cuts the exposure.** Deltas of 0.76–0.80 mean about 230 share-equivalents
  instead of 300.

What it does not change: it is still the same bet at the same strike. The credit
(about $955 for all three) is small against the $15.6K in the money, and on
15 January the most likely position is the same decision again. January is the
liquid monthly (open interest 1,316 on the $160, against 23 for December). The
spreads are $3–5 wide, so roll as one spread order near the mid.

## Finding 6 — The long roll for deep options, applied retroactively: about even

This is Neel's CBRS idea, tested on every chain where it would have applied.
**The rule:** when a stuck option's same-strike roll pays almost nothing (≥5% in
the money, roll netting ≤0.25% of the strike), roll 12 weeks out at the same strike
and leave it alone until that expiry. It would have applied to 14 put chains and 15
call chains.

**How it was tested** (`long_roll.py`):

- Only the contracts actually rolled that day are followed, through their later
  rolls, assignments and expiries, and compared at the long option's expiry.
- The long option is priced with Black-Scholes at the stock price implied by the
  real buy-back fill.
- Calibration: today's CBRS January quotes need about 0.7–0.8× realized volatility
  plus a 4% rate. Realized volatility alone overpriced the long put about 3×.

**Results** (central case: 0.8× realized volatility; 12 weeks):

| | Chains | Long roll better in | Long roll vs what happened |
|---|---|---|---|
| Puts, settled | 9 | 6 | −$11.5K |
| Puts, still running (CBRS, SOXL, RKLB ×2, AVGO) | 5 | 4 | +$0.7K |
| Calls, settled | 10 | 8 | −$10.3K |

Across the other assumptions (0.7–1.0× vol, 8 or 12 weeks, a 0.25–0.5% trigger),
puts range from −$13.6K to +$2.2K and calls from −$16.7K to +$9.4K. **It is a
wash.**

The pattern is the useful part. The long roll **wins small and often**: while the
stock stays down, it collects $0.2–2.6K more than the weekly rolls. It **loses big
and rarely**: when the stock comes back toward the strike, the weekly roll collects
rich near-the-money premium again, and it can move the strike for free.

- **AVGO $360 put (Feb–Apr 2026):** the stock rallied through the strike, and the
  weekly rolls collected $12.7K on the way, against $1.0K for the long roll.
- **AAPL $300 calls ×17 (Jul–Oct 2026):** on a dip, the weekly rolls walked the
  strike from $300 to $310 to $315 at even money. The long roll would have stayed
  at $300: −$31.6K.

In the CBRS-like cases, more than 20% in the money (FIG, INTC, SOXL, CBRS), the
difference is small either way (−$1.7K to +$0.7K).

For CBRS, then, the choice is not about money. The long roll stops the early
assignments, cuts the exposure, and needs no weekly management. The weekly roll
keeps the upside if CBRS climbs back toward the strike. Untested: a hybrid that
parks the option long while it is deep, then returns to weekly once the stock is
back within ~5% of the strike. It might keep the small wins and avoid the big
losses.

## Answers to the four questions

| Neel's question | Calls | Puts |
|---|---|---|
| Should not have sold it | No — the March calls were sold 4–18% out; new near-money sales made +$11.6K | Possibly, after a >20% three-month run |
| Should not have closed at a loss | Right: closing costs −$111.6K in ordinary months. The exception is a relief rally, where buying back was +$87.5K (Finding 5) | Right (−$134.3K) |
| Should have let it be assigned | No (neutral in ordinary months, −$82K in the rally) | No (−$178.8K) |
| Should have deferred further | Only in the rally (+$168.6K, estimated); not in ordinary months (−$8.0K) | No |
| "Sell every week" is the problem | **No** | **No** |

## V9 candidates

1. ~~`call_min_otm_pct = 2`~~ — withdrawn: a look-ahead artefact (see the correction).
2. ~~`call_itm_long_roll`~~ — withdrawn: on daily prices it helps only in the March–April
   rally and is slightly worse otherwise. Replaced by the open question in Finding 2.
3. **Puts: no change to rolling.** The 8-week cap stays (+$4.5K, and margin).
4. **Open for discussion:** a farther put strike after a >20% three-month run.
5. **`call_relief_rally_exit` (proposed, Finding 5).**
   - **Rule:** stop rolling weekly and buy back when all three hold: the call is
     ≥5% in the money; it was sold while QQQ was ≥7% below its 60-day high; and
     ≥60% of the tracked names are up >5% over 10 trading days.
   - **Back-test:** +$87.5K on Neel's chains (all in the 2026 rally; it never fired
     otherwise); on ten years of prices, buying back beat rolling 76% of the time
     with the signal on and 39% with it off.
   - **Knobs:** 7%, 60%, 5%, 10 days, 5%.
   - **Needs:** the breadth figure, from 10-day closes for the tracked names. The
     engine does not compute it yet.

## Open threads

- The long-roll estimate needs real prices. Store option-chain quotes for open
  positions at each sync (`option_chain_quotes` is empty) so the next review can
  measure, not model.
- The weekly price bars (Monday-dated, Friday close) are also what the app's own
  assignment-loss and campaign figures read when no daily price exists. Check
  `_price_near` for the same look-ahead.
- The AMD 10/5 duplicate rows in Neel's Retirement need tracing at the source.
