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
one cluster of near-the-money calls sold in a dip (30 Mar – 8 Apr 2026), made
worse by rolling them one week at a time. Weekly selling at a normal distance
made money in every month on record.

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

## Finding 1 — Call losses are one episode, not a habit

Losing call chains total −$269K. **About 90% of it is 11 chains opened between
30 Mar and 8 Apr 2026**:

| Opened | Stock | Strike vs. stock | First expiry | Result |
|---|---|---|---|---|
| 31 Mar | RKLB (Neel's Retirement) | at the money | 2 days | −$43.1K |
| 30 Mar | NVDA (Jaya's IRA) | 1% in the money | 3 days | −$41.3K |
| 30 Mar | AVGO (Neel's Brokerage) | at the money | 3 days | −$33.6K |
| 30 Mar | AVGO (Neel's Retirement) | at the money | 3 days | −$33.6K |
| 30 Mar | NVDA (Jaya's Brokerage) | 1% in the money | 3 days | −$26.2K |
| 8 Apr | TSLA (both brokerages) | 7% out | 9 days | −$38.2K |
| 30 Mar | AVGO (Jaya's Brokerage) | at the money | 3 days | −$16.9K |
| 31 Mar | NVDA (two accounts) | 1% in the money | 1–2 days | −$15.3K |

By month, calls were **+$9K to +$30K in every month** except March 2026
(−$170K) and April (−$35K).

The NVDA chain in Jaya's IRA shows the shape: 10 calls at $175 for 3 days for
**$380** with NVDA at $177. On 8 Apr, with NVDA at $189, buying back would have
cost $3,020. Instead it was rolled weekly at $180 for six weeks, each roll
collecting $400–500 of time value while the call sat $20–29 in the money, and
was assigned on 15 May at $225 — **$45,320 of upside for $4K of premium**.

### What made those calls bad: the entry

| Strike at sale | Chains | Result |
|---|---|---|
| In the money | 29 | −$61.4K |
| 0–2% out | 32 | −$109.5K |
| 2–5% out | 138 | +$48.5K |
| 5–10% out | 219 | +$54.7K |
| >10% out | 156 | +$69.7K |

A rule of **no call within 2% of the stock** would have blocked 61 chains:
−$198K avoided in the episode, $27.5K of premium given up in other months —
**net +$171K**. Calls sold after a decline also did worse (4-week move down
3–10%: −$54.8K), but as a rule it costs more elsewhere (net +$72K) and overlaps
with the distance rule.

**Already true in V8.** Long-term calls sell at delta 11–15 (≈6–10% out), and
no call within 2% has been opened since V7 went live on 16 Sep. Two gaps remain:
the short-term book allows delta 40 on a 3-day expiry, which can sit within 2%;
and a manual trade has no floor at all.

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
| Should not have sold it | **Yes — when within 2% of the stock** (+$171K) | Weak signal on stocks that ran up |
| Should not have closed at a loss | Right — closing was worse (−$66K) | Right (−$153K) |
| Should have let it be assigned | No — worse (−$98K) | No — worse (−$109K) |
| Should have deferred further | **Yes — 13 weeks, same strike** (+$111K est.) | No — weekly is better |
| "Sell every week" is the problem | **No** — ≥2% out made money every month | No |

## V9 candidates (proposed, not built)

1. **`call_min_otm_pct = 2`** — no new call with a strike within 2% of the stock,
   in any book, whatever the delta says. Mostly true already; this makes it a
   floor that the short-term delta-40 setting and the 3-day minimum cannot slip
   under. Evidence: +$171K on history, $27.5K forgone.
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
