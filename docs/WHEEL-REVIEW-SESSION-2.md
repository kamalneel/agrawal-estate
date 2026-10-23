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
> Findings 2–4 still use the weekly bars in places and are being re-checked.

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

Checks: call premium reconciles to the Income page within $194 (233,613 vs
233,807). Three rows are excluded as duplicates (AMD, Neel's Retirement, 10/5 —
a 3-contract trade also recorded as three 1-contract trades, on both sides).
Scripts: `backend/scripts/wheel_review/`.

## Headline

| | Premium (net) | Given up / lost at assignment | Result |
|---|---|---|---|
| Calls | +$233.6K | −$206.8K | **+$26.8K** |
| Puts | +$252.5K | −$119.3K (assignment day) | **+$133.2K** |
| Puts, assigned shares at today's price | | | **+$83.0K** |

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

## Finding 2 — When a call goes in the money, roll long, not weekly

Tested at the first roll where the call was ≥5% in the money (46 chains):

| Instead of rolling weekly | vs. actual | How measured |
|---|---|---|
| Buy back and stop selling | **−$66K** (worse) | actual fills |
| Let it be assigned | **−$98K** (worse) | actual fills |
| Roll ~13 weeks out, same strike | **+$111K** (better) | Black-Scholes estimate |
| Roll ~13 weeks out, up to the strike that costs nothing | +$69K | Black-Scholes estimate |

Outside March–April the long roll still helps (+$27K across 28 chains); the
roll-up version does not (−$21K). So the robust version is **same strike, 13
weeks**: it collects a quarter's time value at once instead of a week's, and
gives the stock time to come back.

Caveat: no historical option prices exist, so the long roll is priced with
Black-Scholes at each stock's 26-week realized volatility. Real implied vol is
usually higher, which would make the long roll pay *more* — but treat the size
as an estimate, not a fact. The buy-back and let-assign rows are exact.

This answers two of Neel's four questions for calls: **"should not have closed
at a loss"** — right, closing was worse; **"should have let it get assigned"** —
no, worse still.

## Finding 3 — Puts: keep rolling weekly

Same tests on puts (49 chains reached ≥5% in the money):

| Instead of rolling weekly | vs. actual |
|---|---|
| Buy back and stop | −$153K (worse) |
| Let it be assigned | −$109K (worse) |
| Roll ~13 weeks out, same strike | −$118K (worse, estimate) |

Weekly rolling is the right tool for puts. Opposite to calls: a put in trouble
is on a falling stock, where weekly premium is rich; a call in trouble is on a
rising one, where a week of time value is small against the move.

**V8's 8-week put exit (added 16 Oct)**, back-tested on the 8 chains still in the
money at week 8: −$511 — a wash. Its case is freeing margin, not profit.

## Finding 4 — Put losses come after assignment, on stocks that had run up

Assigned put chains, grouped by the stock's 12-week move before the put was sold,
with shares valued today (put premium included):

| 12 weeks before | Chains | Shares | Value today |
|---|---|---|---|
| Down or flat | 5 | 800 | +$10.8K |
| Up 5–20% | 4 | 500 | −$16.4K |
| Up 20–50% | 7 | 1,200 | −$20.3K |
| Up >50% | 5 | 1,700 | −$43.8K |

SOXL had run +499%, RKLB +55–105%, AVGO +20–35%, SPCX and GOOGL +23% before the
puts that put those shares in the book. V8's checks look back ~10 days and miss a
three-month run.

**But as a rule it is weak.** "No put after a >30% 12-week run" would have avoided
about $131K of share losses and given up $110K of premium: net +$21K, measured at
today's prices, so it can vanish if those stocks recover. Not proposed.

## Answers to the four questions

| Neel's question | Calls | Puts |
|---|---|---|
| Should not have sold it | No — the March calls were sold 4–18% out; new near-money sales made +$11.6K | Weak signal on stocks that ran up |
| Should not have closed at a loss | Right — closing was worse (−$66K) | Right (−$153K) |
| Should have let it be assigned | No — worse (−$98K) | No — worse (−$109K) |
| Should have deferred further | **Yes — 13 weeks, same strike** (+$111K est.) | No — weekly is better |
| "Sell every week" is the problem | **No** — never-stuck calls made money every month; stuck calls made money outside one rally | No |

## V9 candidates (proposed, not built)

1. ~~`call_min_otm_pct = 2`~~ — withdrawn (see the correction above).
2. **`call_itm_long_roll`** — when a call is ≥5% in the money at its roll, roll
   the same strike ~13 weeks out instead of one week. Replaces V8's deep-out
   trigger (4 weeks above the strike, then a strike near the stock), which waits
   too long and asks for too much. Evidence: +$111K estimated, +$27K outside the
   episode. Tension: Neel's 16 Oct point that a far-out call is "not ready to
   encash the drop" — the data says the extra quarter of time value is worth more
   than catching the dip.
3. **Puts: no change.** Weekly rolling stands; the 8-week cap stays for margin.

## Open threads

- The long-roll estimate needs real prices. Start storing option-chain quotes for
  open positions at each sync (`option_chain_quotes` is empty) so the next review
  can measure, not model.
- The AMD 10/5 duplicate rows in Neel's Retirement need tracing at the source.
- Put-side: whether a *farther* strike (rather than no put) after a 12-week run
  keeps the premium and avoids the top. Not tested.
