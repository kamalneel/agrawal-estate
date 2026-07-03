# Options Strategy — V6 Philosophy

**Version:** 6.1  
**Status:** ✅ ACTIVE  
**Created:** 2026-05-23  
**Updated:** 2026-05-29 (V6.1 — Two-Tier Classification)  
**Supersedes:** V4 (V5 was implemented in code but never documented)  
**Author:** Neel Kamal (dictated); compiled by Claude

---

## What This Document Is

This is the "why." It captures how Neel thinks about selling options — the beliefs, the lessons, and the judgment calls that can't be reduced to a formula. Read this before reading the engine spec. When in doubt about a decision, come back here.

---

## The Foundation (Unchanged from V1–V4)

These beliefs have not changed. They underpin every V6 decision.

**I hold these stocks because I believe in them.** If I didn't believe, I wouldn't own them. That means being assigned is not a disaster — it means I own more of something I already wanted.

**I am not a trader. I am an owner who happens to sell options.** I don't buy and sell stocks to make money. I sell options on top of stocks I already own (or want to own) to generate a weekly income stream. The options income is the business. The stocks are the inventory.

**Mean reversion is real.** Stocks go up, stocks go down, but they cycle. This is not a hope — it is the observed reality. The strategy relies on this. Patience is how you get paid.

**The only goal is weekly income.** Not monthly. Not quarterly. Every week, the clock resets. I want premium collected every week. A week where I'm stuck in a position and can't earn is a week of lost income.

**Don't make stupid decisions.** Don't panic-close when the stock moves against you. Don't sell when conditions are bad. Wait. The cycle will come.

---

## How My Thinking Has Evolved (V6 Updates)

### 1. Puts Are Now the Primary Income Engine

I used to treat covered calls as the main event and puts as a side strategy for idle cash. V6 flips this.

**The key realization:** When puts get assigned, I switch to covered calls on those shares. When those calls expire, I can sell puts again. This is the wheel — and the put leg is often the higher-premium leg because you're selling on weakness (high IV, high fear). Calls are sold on strength (lower IV, lower fear).

In practice: put income has outpaced call income in most months. The puts are working harder.

**V6 rule: Run the wheel intentionally.** Don't just sell puts opportunistically. Plan for assignment. Know what you'll do next.

### 2. Delta Targeting Is Account-Dependent

Old approach: delta 20–30 for puts (conservative, high probability of expiry OTM).

**V6 approach: Split by account type.**

| Account Type | Delta Target | Why |
|---|---|---|
| IRA (Retirement) | 70–80 delta | No tax on assignment, no margin, trade freely — be aggressive |
| Taxable (Brokerage) | 90 delta | Tax-sensitive, margin available, hold-forever mindset — be conservative |

The IRA accounts can absorb assignment without any consequences. If it gets assigned, I own more at a lower price with zero tax event. So I push the delta higher to earn more premium per contract.

The taxable account has tax implications and margin. I'm more cautious here — delta 90 means I'm almost certain the put expires worthless, which is the goal.

### 3. Assignment Is the Plan, Not the Risk

V4 treated assignment as something to avoid or at least assess. V6 treats assignment as a planned outcome in IRA accounts.

**In IRA accounts:** Assignment is always fine. No tax, no margin call, no cost basis worry. The shares are now mine at the strike price, which is lower than where I chose to sell the put. I wanted these shares. I now have them cheaper.

**In taxable accounts:** Assignment requires a cost basis check.

| Scenario | What to Do |
|---|---|
| Strike < my cost basis | Assignment lowers my average cost. Let it happen. |
| Strike ≈ my cost basis (within 2%) | Neutral — let it happen. |
| Strike > my cost basis | I'd be buying at a price higher than I've already paid. Consider rolling the put out instead. |
| I'm sitting on a large gain (like TSLA at $425 with avg $90) | Assignment is fine — I own cheap shares and am buying more at a much higher average. But the covered call income on the original shares is protected. |
| I'm near breakeven or at a loss (like MSFT at $480 avg with stock at $407) | Assignment could help tax-loss harvest if I then sell. Think it through. |
| Stock has run significantly above my avg (like AVGO $325 strike, $275 avg) | Borderline — the premium is good but I'm buying high relative to history. Evaluate carefully. |

### 4. The Wheel Philosophy: What to Do After Assignment

When a put gets assigned:
1. I now own 100 shares per contract at the strike price.
2. Immediately begin selling covered calls on those shares.
3. Target a call strike that is either: (a) at or above my cost basis (strike I was assigned at), or (b) at the current stock price if it has already recovered.
4. When the call expires worthless or gets called away, evaluate: sell puts again, or let the cash sit for a better opportunity.

The wheel is not infinite. If a stock has "run away" (see below), I don't just keep selling puts below a stock that keeps climbing. I reassess the universe of stocks and redeploy.

### 5. Redeployment Logic After Assignment

When a put gets assigned and I end up with cash after selling the shares (or if I want to redeploy the capital into puts on a different stock), here is the decision logic:

**Step 1: Should I buy this stock back?**

Not automatically. A stock that just ran away on a structural catalyst (AI chips, tariff resolution, earnings beat that changes the long-term thesis) may not be cheap again for a long time. Don't chase.

Example: iBit (Bitcoin ETF) showed a pattern of correlation with risk-on/risk-off macro. That's not a sector I have conviction in. I exited.

Example: AVGO was assigned during the May 2026 rally. Chip stocks were winning because of genuine AI demand. This was a "runaway" (see below). Redeployment into another chip stock made more sense than immediately selling puts on AVGO again at the elevated price.

**Step 2: Sector fit — what is working?**

Evaluate which sectors have structural tailwinds right now. In May 2026, chips (NVDA, AVGO, MU) were winning because of real AI demand. Software was mixed. Consumer discretionary was volatile (TSLA). Prioritize sectors with structural momentum.

**Step 3: Market cap filter.**

For taxable accounts: trillion+ market cap only. These are companies that are more likely to survive a bad quarter, recover from a correction, and won't get wiped out by a single event. IRA accounts can go smaller — mid-cap is fine if conviction is there.

**Step 4: Portfolio balance (minor constraint).**

Don't become 80% NVDA. Diversify across 3–5 active positions. But this is a minor constraint — if NVDA is clearly the best opportunity, it's OK to be overweight temporarily.

**Step 5: Highest IV wins.**

All else equal, sell puts on the stock with the highest implied volatility. IV is the market paying you to take risk. Higher IV = more premium per contract for the same delta.

### 6. Two Patterns: Runaway vs. Oscillating

This is the most important new concept in V6. It came from hard lessons.

**The TSLA mistake:** In May 2026, TSLA had a pattern of sharp moves followed by reversions. I sold calls, it ran up, I panicked and closed 9 contracts at a massive loss (~$35K each, total ~$70K). Then TSLA dropped back to $400. The panic close cost me more than just waiting one more week would have.

**The AVGO pattern:** AVGO moved from $190 to $250+ in a matter of weeks during the April–May 2026 AI tariff resolution. Rolling a put at or near zero cost for weeks was the right move — each week's loss on the option was almost exactly offset by the premium collected. I was rolling at zero, not losing, while the stock ran.

**The distinction:**

| Pattern | Characteristics | How to Tell | Strategy |
|---|---|---|---|
| **Runaway** | Stock moves on structural fundamental change. Keeps going even when RSI is overbought. Each correction is shallow. New highs follow quickly. | Ask: "Is there a real, durable reason this stock is up? Has the fundamental thesis changed?" AI chip demand, GPU shortage, tariff resolution = structural. | Roll the put at zero cost. Don't close for a loss. The premium barely covers the roll, but you're not losing. Wait for the cycle to exhaust itself. |
| **Oscillating** | Stock moves on sentiment, macro fear/greed, or news that doesn't change the long-term thesis. Returns to prior levels within weeks. | Ask: "Is this move driven by a news cycle or a business change?" Fed rate concerns, meme momentum, tariff rumors = sentiment. | Use RSI and mean reversion. Oversold = good entry. Overbought = close or roll. The pattern is repeating and predictable. |

**Technical study findings (AVGO/TSLA/AAPL — May 2026 DB data):**

- AVGO: April–May 2026 showed $85K STO / $86K BTC events nearly every week — rolling at near-zero while the stock climbed 30%+. This is the "runaway" in real data. The right call was patience, not panic.
- TSLA: May 15, 2026 showed a single $45K BTC event (panic close). Within the same week, TSLA had been making multiple large moves (up, then partial recovery). The stock dropped back shortly after the panic close. This is the "oscillating" pattern with a catastrophic early exit.
- AAPL: Smaller-scale version of TSLA behavior — large rolling events, but smaller losses, and more predictable oscillation. Current live test confirms the oscillating hypothesis.

**How to use this in practice:**

Before selling a put on any stock, classify it:
- Runaway stocks: Sell higher delta (more aggressive). Roll at zero if it moves against you. Never panic-close.
- Oscillating stocks: Use RSI < 30 as entry signal. Expect to close near OTM at 60–80% profit. Respect the cycle.

**How to classify (at decision time):**

Ask these questions:
1. Is there a recent earnings report, product launch, or macro change (tariffs, rates) that created this move?
2. Is the move above or below normal ATR (Average True Range)? Way above = potential runaway.
3. Has the stock been making new highs, or bouncing between established levels?

Structural catalyst + new highs + above-ATR move = likely runaway.  
Sentiment + range-bound + within ATR = likely oscillating.

If unclear: default to oscillating behavior (more conservative).

### 7. Account-Type Strategy Summary

| Decision | IRA (Retirement) | Taxable (Brokerage) |
|---|---|---|
| Put delta | 70–80 (aggressive) | 90 (conservative) |
| Assignment comfort | Always fine | Requires cost basis check |
| Stock universe | Small/mid-cap OK | Trillion+ preferred |
| Tax on assignment | None | Capital gains possible |
| Margin available | No (hard cash limit) | Yes (large buffer) |
| Mindset | Trade freely | Hold forever |
| When overextended | Roll immediately (no tax) | Think before rolling |

---

### 8. Two-Tier Stock Classification (V6.1)

This is the most important structural addition in V6.1. It came from recognizing that mega-cap stocks ($1T+ market cap) and sub-$1T stocks have fundamentally different risk profiles, and treating them identically leads to bad outcomes.

**The core problem with mixing tiers:**

If I hold Palantir (sub-$1T) the same way I hold Apple (mega-cap), I get burned. PLTR can drop 12% in a single day on no meaningful news — just sentiment. When that happens on a covered call position, the covered call becomes worthless and I'm holding shares at a high cost basis waiting for a recovery that may take weeks. Meanwhile I missed income. The wheel works on PLTR only if I don't care about holding it long-term.

But AAPL dropping 12% in a day is a once-a-decade event and always recovers. That's a different proposition.

**The two tiers:**

#### Tier 1: Mega-Cap Hold Tier ($1T+ Market Cap)

*Who belongs here:* AAPL, MSFT, NVDA, AVGO, GOOGL, AMZN, META

*Named inclusions despite sub-$1T:* LLY (~$750B but treated as mega-cap — conviction hold, want to own for decades, behaves like a mega-cap from a volatility and recovery standpoint)

*Named carve-out despite $1T+:* TSLA (special rules — see below)

*Strategy:*
- Hold for long-term appreciation. These are forever stocks.
- Sell calls as income supplement — but conservatively. The goal is NOT to get called away.
- Delta 10–15 for calls: earn premium, preserve the position.
- If assigned on a call: the shares are gone, and I've lost the long-term compounding. This is the bad outcome. Don't let it happen by being greedy on delta.
- Never sell puts on these in taxable accounts if sitting on large embedded gains — the assignment would dramatically raise cost basis.
- Income from options is welcome but secondary. Appreciation is the real return.

*Income-generating reality (from live data, June 2026 expiry):*

Not all mega-cap stocks generate meaningful call income. At delta 10 (90% probability OTM):

| Ticker | Weekly Yield (delta 10) | Verdict |
|---|---|---|
| AVGO | ~0.65%/week | Active income — sell calls consistently |
| META | ~0.28%/week | Moderate — sell calls when RSI > 60 |
| TSLA | ~0.28%/week | Special rules only (see TSLA carve-out) |
| NVDA | ~0.26%/week | Moderate — sell calls when RSI > 60 |
| AMZN | ~0.26%/week | Moderate — sell calls when RSI > 60 |
| MSFT | ~0.24%/week | Low — sell calls on extended rallies |
| GOOGL | ~0.24%/week | Low — sell calls on extended rallies |
| LLY | ~0.23%/week | Low — sell calls on extended rallies only |
| AAPL | ~0.16%/week | Hold for appreciation only. Skip calls most weeks. |

*TSLA carve-out:*

TSLA is $1T+ but must be handled differently from the other mega-cap stocks. The TSLA $70K lesson (May 2026) established this.

**Why TSLA is different:** It has the volatility of a sub-$1T stock but the market cap of a mega-cap. A single week can see $50–100 moves. Selling even "conservative" delta 20–30 calls means a 5% TSLA move will burn you. The shares also carry large embedded gains in taxable accounts — getting called away is a taxable event at a much higher effective price than the original cost basis.

**TSLA carve-out rules:**
1. Sell calls at delta 10–12 only (90–88% probability OTM)
2. Only when RSI > 75 (stock already significantly overbought)
3. Expected yield: ~$100–125/contract/week — accept this; don't stretch for more
4. Never sell puts on TSLA in taxable accounts if sitting on large gains
5. If the call goes ITM anyway: roll at zero cost, never panic-close (learned the hard way)

#### Tier 2: Sub-$1T Aggressive Wheel Tier

*Who belongs here:* PLTR, HOOD, COIN, AMD, SHOP, INTC, RKLB, NFLX, CRCL, FIG, MSTR, and any new name under $1T market cap

*Strategy:*
- Do NOT hold these long-term. They're inventory for the wheel, not forever stocks.
- The goal IS assignment — aggressive delta 80 on both put and call legs.
- When a put gets assigned, immediately sell delta 80 covered calls on those shares.
- When the call gets assigned (shares called away), immediately sell delta 80 puts again.
- The high assignment frequency is the feature, not a bug — it generates premium on every cycle.
- No emotional attachment to these positions. Getting called away or assigned is the plan.

*Why aggressive delta on both legs:*

At delta 80, the premium is meaningful. At delta 20 (conservative), the sub-$1T stocks generate ~0.40–0.91%/week but carry the same underlying volatility risk. Going to delta 80 generates 3–5× more premium and the assignment acceptance is already built into the strategy. You're choosing to own or not own based on price levels, not trying to avoid assignment.

*From live data, June 2026 expiry (delta ≈ 20 puts):*

| Ticker | Weekly Yield (delta 20) | Pattern |
|---|---|---|
| RKLB | ~1.85%/week | Very small cap — aggressive only in IRA |
| INTC | ~1.54%/week | Turnaround story — moderate conviction |
| CRCL | ~1.40%/week | New entrant, elevated IV |
| AMD | ~1.29%/week | Solid semi with chips tailwind |
| FIG | ~1.15%/week | Small cap — IRA only |
| MSTR | ~1.12%/week | BTC proxy — treat like crypto exposure |
| COIN | ~1.05%/week | Crypto-correlated — elevated IV |
| SHOP | ~0.99%/week | Commerce platform — consistent |
| PLTR | ~0.91%/week | Government AI — durable thesis |
| HOOD | ~0.91%/week | Retail brokerage — consistent |
| NFLX | ~0.40%/week | Lower IV, more like mega-cap behavior |

Note: MU data was unavailable at time of compilation (transient API errors). Add when accessible.

At delta 80, expect 3–5× these yield numbers — sub-$1T aggressive wheel is the income engine.

#### The 80/20 Portfolio Allocation Rule

Every account — IRA and taxable alike — should maintain approximately:
- **80% in Tier 1** (mega-cap hold): long-term value growth
- **20% in Tier 2** (sub-$1T wheel): active income generation

This applies to each account independently, not the portfolio as a whole. The IRA cannot borrow against Tier 1 holdings, so aggressive sub-$1T wheeling in IRA must be funded by 20% cash/positions, not leverage.

**Why maintain Tier 1 in IRA even though it's "tax-free":**
IRA accounts benefit from compounding on appreciation — NVDA going 10× in the IRA is enormous tax-free gain. Using 100% of IRA cash for sub-$1T wheeling trades that away. The 80/20 rule preserves long-term compounding while still running active income.

**Why maintain Tier 2 in taxable even though it triggers tax events:**
The sub-$1T wheel in taxable generates short-term gains (expected, planned). The premium income from aggressive puts/calls is the return. The tax is a cost of that income, not a surprise. Size the position so after-tax income is still meaningful.

---

## What Has Not Changed

- **Sell on strength, buy on weakness.** Sell calls when the stock is up. Buy back calls when the stock is down. Sell puts when the stock is down. Buy back puts when the stock is up. Never fight momentum by doing the opposite.
- **Never extend duration beyond 4 weeks.** A trapped 3-month position is worse than paying a small debit to compress. Income lost while waiting is real money.
- **Separate the legs.** Don't always roll simultaneously. If conditions favor buying first and selling later (or vice versa), do them separately.
- **RSI and Bollinger Bands matter for entry, not exit.** Use them to time when to open a position. Don't use them to decide when to close a winning position — just take the profit.

---

## Anti-Patterns (What NOT to Do)

**Panic-close because the stock moved.** TSLA's $70K lesson: the stock came back. Every time I've panic-closed, the stock moved in my favor within days. Patience is almost always the right call.

**Chase a runaway stock with a new put.** If AVGO just went from $200 to $270 in 3 weeks, selling a $265 put is not a discount — it's chasing. Wait for the cycle to exhaust or find a different stock.

**Ignore account type when selecting delta.** IRA and taxable require different aggression levels. Treating them the same means either leaving money on the table (IRA too conservative) or taking on inappropriate tax risk (taxable too aggressive).

**Use iBit or crypto-correlated assets for puts.** These are sentiment-driven, correlated with macro risk-on/off, and the fundamentals don't support "I want to own more of this." Avoid.

**Sell puts during earnings week.** IV crush risk is asymmetric. The premium might look good, but the overnight move can erase weeks of income.

**Apply the same delta to mega-cap and sub-$1T stocks.** Selling delta 80 calls on AAPL to earn more premium will get you called away on a stock you want to hold forever. Selling delta 10 calls on RKLB leaves most of the available premium on the table when the goal is aggressive wheeling.

**Treat LLY like a sub-$1T wheel target.** LLY is ~$750B but conviction and intended hold period put it in Tier 1. Aggressive wheeling LLY would mean regularly getting called away from a forever position. The $1T threshold is a heuristic; conviction level is the actual filter.

**Let TSLA drift into standard delta 20–30 calls.** "Just a little more aggressive this week" is how the $70K loss happened. TSLA carve-out rules exist exactly because the one exception always seems tempting. Delta 10–12, RSI > 75, always.

**Run sub-$1T stocks to 100% of any account.** The 80/20 allocation is a ceiling on Tier 2, not a suggestion. Concentrating an entire account in PLTR, RKLB, and COIN is speculative exposure with no long-term anchor. Keep Tier 1 as the foundation.

---

*Next: See `OPTIONS-STRATEGY-V6-ENGINES.md` for the decision tables used by each recommendation engine.*
