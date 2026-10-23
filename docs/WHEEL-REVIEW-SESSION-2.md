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
March–April rally from an ordinary pull-back-and-return.**

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

## Answers to the four questions

| Neel's question | Calls | Puts |
|---|---|---|
| Should not have sold it | No — the March calls were sold 4–18% out; new near-money sales made +$11.6K | Possibly, after a >20% three-month run |
| Should not have closed at a loss | Right — closing costs −$111.6K in ordinary months | Right (−$134.3K) |
| Should have let it be assigned | No (neutral in ordinary months, −$82K in the rally) | No (−$178.8K) |
| Should have deferred further | Only in the rally (+$168.6K); not in ordinary months (−$8.0K) | No |
| "Sell every week" is the problem | **No** | **No** |

## V9 candidates

1. ~~`call_min_otm_pct = 2`~~ — withdrawn: a look-ahead artefact (see the correction).
2. ~~`call_itm_long_roll`~~ — withdrawn: on daily prices it helps only in the March–April
   rally and is slightly worse otherwise. Replaced by the open question in Finding 2.
3. **Puts: no change to rolling.** The 8-week cap stays (+$4.5K, and margin).
4. **Open for discussion:** a farther put strike after a >20% three-month run.

## Open threads

- **The runaway signal.** What told the March–April rally apart early — the size of
  the first week's move, several holdings jumping together, or the market as a
  whole? That is the one place a rule could have saved money (Finding 2).
- The long-roll estimate needs real prices. Store option-chain quotes for open
  positions at each sync (`option_chain_quotes` is empty) so the next review can
  measure, not model.
- The weekly price bars (Monday-dated, Friday close) are also what the app's own
  assignment-loss and campaign figures read when no daily price exists. Check
  `_price_near` for the same look-ahead.
- The AMD 10/5 duplicate rows in Neel's Retirement need tracing at the source.
