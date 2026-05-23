# Options Strategy — V6 Engine Spec

**Version:** 6.0  
**Status:** ✅ ACTIVE  
**Created:** 2026-05-23  
**Companion:** `OPTIONS-STRATEGY-V6-PHILOSOPHY.md` (read this first)  
**Supersedes:** V4 engine spec (V5 was code-only, never documented)

---

## Overview

There are 4 engines. Each fires independently and produces recommendations.

| Engine | What It Does | Fires When |
|---|---|---|
| Engine 1: Uncovered Calls | Sell covered calls on shares with no active call | Holdings with 100+ shares and no open call |
| Engine 2: Cash-Secured Puts | Sell puts on target stocks using available cash | Available cash + favorable conditions |
| Engine 3: Profit Taking | Roll or close winning positions early | Position is at 60%+ profit |
| Engine 4: Stuck Positions | Manage ITM or underwater positions | Call is ITM or put is deeply tested |

---

## Engine 1: Uncovered Calls (Sell New Covered Calls)

### When to fire

A stock qualifies if:
- Holdings: 100+ shares in any account
- No open covered call on those shares
- Stock is NOT in a runaway pattern (see Philosophy — don't sell calls on a stock that's in a confirmed uptrend)

### How to pick the strike

| Account | Delta Target | Notes |
|---|---|---|
| IRA | 30 delta (30% chance ITM) | Aggressive enough to earn meaningful premium |
| Taxable | 20 delta (20% chance ITM) | Conservative; want it to expire worthless most of the time |

**Additional rules:**
- Strike must be at or above the average cost basis for the account. Never sell a call at a strike below your cost basis (you'd be forced to sell at a loss if assigned).
- Prefer the strike closest to ATM while satisfying the delta target. Don't go far OTM just to feel safe — you'll earn almost nothing.
- Expiration: Friday of the same week or next Friday. Never more than 2 weeks out for a new entry (unless the stock is in a runaway and you want more time cushion).

### Entry timing

| RSI | Action |
|---|---|
| RSI > 60 | Good — stock is elevated, sell now |
| RSI 40–60 | Neutral — sell now, accept lower premium |
| RSI < 40 | Wait. Stock is weak. Selling a call on a falling stock means a lower strike and lower premium. Wait for recovery. |
| RSI < 30 | Do not sell a call. This stock needs to recover first. |

**Day-of-week rule:**
- Ideal entry: Monday or Tuesday for same-week expiry (5 days of theta decay)
- Last day to enter for same-week: Wednesday (2 days remaining)
- If Wednesday passes with no good entry: sell for the following Friday instead

### What to recommend

```
Action: SELL CALL
Symbol: [SYMBOL]
Account: [ACCOUNT]
Strike: $[X] (delta [Y])
Expiration: [DATE]
Premium: ~$[Z]/contract
Reason: [RSI/timing rationale]
```

---

## Engine 2: Cash-Secured Puts (Sell New Puts)

This is the primary income engine in V6. See Philosophy §1–§7 for the full context.

### When to fire

A stock qualifies if:
- It is in the portfolio holdings OR it is on the approved target list (stocks we believe in and would own more of)
- Available cash in the account is sufficient to cover the put (strike × 100 × contracts)
- Technical conditions are favorable (see below)
- Not within 5 days of earnings

### Account-based rules

**IRA accounts (aggressive):**
- Delta target: 70–80
- Max % of available cash per position: 80% (IRA is smaller, concentrated OK)
- Stock universe: any stock on the approved list, including mid-cap
- Assignment comfort: always fine — no tax, no margin concern

**Taxable accounts (conservative):**
- Delta target: 90
- Max % of available cash per position: 30% (keep cash available for opportunities)
- Stock universe: trillion+ market cap only (AAPL, MSFT, NVDA, AVGO, GOOGL, AMZN, META, TSLA at scale)
- Assignment requires cost basis check (see Philosophy §3)

### Entry conditions

| Indicator | Favorable | Neutral | Unfavorable |
|---|---|---|---|
| RSI | < 40 | 40–60 | > 60 |
| Recent move | Down 3%+ from recent high | Flat | Up 5%+ recently |
| Stock pattern | Oscillating (sentiment-driven) | Unknown | Runaway (structural catalyst) |

**Stock pattern is the most important filter:**
- If the stock is in runaway mode: do NOT sell a new put at today's elevated price. Wait for the structural catalyst to be priced in. A runaway stock that corrects 10% is still expensive if the runaway was 30% up.
- If the stock is oscillating: RSI < 40 is a green light. Enter now.

### Strike selection

**For oscillating stocks:**
- Target the strike at delta target (70–80 IRA, 90 taxable)
- Make sure the strike is below a meaningful support level if identifiable
- Never sell a put at a strike above your cost basis in a taxable account without explicitly confirming the tax situation

**For runaway stocks (if selling puts at all):**
- Go lower delta (50–60), further OTM
- This is a "get paid to wait" situation — you're earning premium while waiting for the price to stabilize
- Expiration: 2–3 weeks out (not weekly — too much risk on a runaway)

### Position sizing

```
Max contracts = floor(available_cash * max_pct / (strike * 100))

Where:
  max_pct = 0.80 for IRA
  max_pct = 0.30 for taxable
```

Don't max out every position. If 3 positions are already running, be selective about adding a 4th.

### What to recommend

```
Action: SELL PUT
Symbol: [SYMBOL]
Account: [ACCOUNT]
Strike: $[X] (delta [Y], [Z]% OTM)
Expiration: [DATE]
Premium: ~$[W]/contract
Cash Required: $[X*100 per contract]
Pattern: OSCILLATING / RUNAWAY
Assignment Plan: [what happens if assigned]
```

---

## Engine 3: Profit Taking (Roll Winners Early)

### When to fire

A position qualifies for early roll if:
- Current profit on the position is ≥ 60% of the original premium
- Days to expiration > 5 (don't close with less than 5 days — let theta work)
- A better opportunity exists for the freed capital (this is the trigger for closes, not just profit)

### Decision table

| Profit % | Days to Expiry | Action |
|---|---|---|
| ≥ 80% | Any | Close immediately. Collect profit. Redeploy. |
| 60–80% | < 14 days | Close. Not enough time value left to justify the risk. |
| 60–80% | ≥ 14 days | Evaluate: Is there a better trade available? If yes, close. If not, let theta run. |
| < 60% | Any | Do not close early. Let it work. |

### For puts that are winning

When a put is at 60–80% profit:
1. Close the put.
2. Immediately evaluate: should we sell a new put on the same stock (if still oversold), or has it recovered enough to switch to a call?
3. If the stock has recovered to neutral/overbought RSI: do not sell a new put. The opportunity has passed. Wait for the next dip.
4. If the stock is still oversold: sell a new put at the same or slightly higher strike.

### For calls that are winning

When a call is at 60–80% profit:
1. Close the call.
2. Do not sell a new call immediately if the stock is still falling (low RSI). Wait for recovery.
3. If the stock is at neutral RSI and no strong signal: sell the next week's call.
4. If the stock has recovered and RSI is rising: sell aggressively (same-week or next Friday).

---

## Engine 4: Stuck Positions (Manage ITM/Underwater)

This engine handles calls that are ITM and puts that are deeply tested (stock has moved far against the position). The V4 intrinsic value model applies here with V6 account-type awareness.

### For ITM covered calls

**Step 1: Assess intrinsic percentage**

```
Intrinsic % = (Stock Price - Strike) / Option Price  [for calls]
```

| Intrinsic % | Category | Strategy |
|---|---|---|
| < 40% | Time dominates | Normal management. Can wait. |
| 40–60% | Crossover | Evaluate: compress or wait for pullback |
| 60–80% | Stock must move | Wait for mean reversion. Do NOT compress (too expensive). |
| > 80% | Mostly intrinsic | Set price alerts. Wait. Or cut loss if thesis has changed. |

**Step 2: If waiting (stock must move back down)**
- Set alert at -5% from current price: evaluate compression
- Set alert at -10%: compress or raise strike
- Set alert at strike: full exit to weekly, resume income

**Step 3: If compressing**
- Max extension: 4 weeks from today (not from current expiry — 4 weeks total)
- Prefer paying a small debit ($3–5) over getting trapped for 3+ months at no cost
- Target delta 30 on the new position
- Separate the legs: buy back first if stock is down, sell the new one when stock recovers slightly

**V6 addition — account-aware compression:**

For IRA accounts: compress more aggressively (even if it costs a small debit). No tax friction on the trade, and missed income in IRA is not tax-advantaged.

For taxable accounts: the debit is paid with after-tax dollars. Be slightly more patient before compressing. But don't fall into the 12-week trap.

### For tested puts (stock moving against the put)

"Tested" means the stock has dropped and the put is now at or near the money.

**Step 1: Classify the pattern**

| Pattern | Signs | Action |
|---|---|---|
| Oscillating | No fundamental change, RSI < 30, stock was overbought recently | Hold. Mean reversion is coming. Roll if needed. |
| Runaway down | Structural bad news (earnings miss that changes thesis, sector collapse) | Evaluate closing. This is different from normal volatility. |
| Unknown | No clear signal | Treat as oscillating (conservative assumption). |

**Step 2: Roll decision for oscillating stocks**

If the put is near ATM and you have more than 5 days to expiry:
- Do nothing. Let theta work. RSI < 30 means the stock is already beaten up.
- If expiry is in 1–2 days and the put is still near ATM or ITM: roll out by 1 week. Give it time.

If the put is ITM and the stock shows no signs of recovery:
- Roll down and out: buy back the current put, sell a new put at a lower strike, further out in time
- Target: net zero cost or small credit on the roll
- The AVGO lesson: it is acceptable to roll at near-zero cost for multiple weeks while waiting for the cycle to exhaust. Do not panic-close just because the stock is still moving against you.

**Step 3: Roll decision for runaway puts**

If you've determined this is a runaway:
- Roll down and out at zero cost, but lower your strike meaningfully (not just $5)
- If you can't lower the strike meaningfully (stock has moved too far, cost is too high): evaluate closing for a loss and redeploying
- The goal is to not keep rolling a put on AVGO at $190 when AVGO is now at $270 — you're locking up capital that could be deployed better elsewhere

**Step 4: After assignment (put assigned)**

1. You now own shares at the strike price.
2. Immediately sell covered calls using Engine 1 rules.
3. For IRA: sell at delta 30 (earn income while holding).
4. For taxable: check if the assigned price is below cost basis — if so, selling calls at or above cost basis gives you a good outcome.

---

## Cross-Engine Rules

These apply across all 4 engines.

**Account isolation.** Each account's positions are managed independently. Neel's Brokerage and Jaya's Brokerage are separate. Don't combine positions across accounts.

**One recommendation at a time per symbol per account.** Don't recommend selling a call AND a put on the same symbol in the same account simultaneously.

**Earnings blackout.** Within 5 days of earnings: no new positions. Existing positions: flag for potential early close.

**Cash floor.** In taxable accounts, never commit more than 70% of total available cash across all puts simultaneously. Leave 30% as a buffer for rolls and assignments.

**In IRA accounts,** there is no margin. Cash available is the hard limit. The engine must verify that the full assignment cost (strike × 100 × contracts) is covered by available cash.

---

## Configuration Reference

```
PUT_DELTA_IRA = 70–80          # target delta for IRA puts
PUT_DELTA_TAXABLE = 90         # target delta for taxable puts
CALL_DELTA_IRA = 30            # target delta for IRA calls
CALL_DELTA_TAXABLE = 20        # target delta for taxable calls

PROFIT_TAKE_THRESHOLD = 0.60   # close at 60%+ profit
MAX_ESCAPE_WEEKS = 4           # from V4; still applies
INTRINSIC_CROSSOVER = 0.60     # above this: stock must move (calls)

CASH_FLOOR_TAXABLE = 0.30      # keep 30% cash free in taxable
CASH_FLOOR_IRA = 0.20          # keep 20% cash free in IRA

RSI_OVERSOLD = 30              # don't sell calls below this
RSI_OVERBOUGHT = 60            # don't sell puts above this
RSI_CALL_ENTRY = 60            # sell calls above this
RSI_PUT_ENTRY = 40             # sell puts below this

MIN_DAYS_TO_EXPIRY_ENTRY = 5   # don't open new positions < 5 DTE
ROLL_NEAR_EXPIRY_DAYS = 2      # roll if < 2 days to expiry and ITM/near-ATM
```

---

## Decision Flow Summary

```
For each account:
  For each holding (100+ shares):
    [Engine 1] If no open call → evaluate new call (timing + delta)

  For each open call:
    [Engine 3] If profit ≥ 60% → evaluate early close
    [Engine 4] If ITM → assess intrinsic %, trigger stuck logic

  For available cash:
    [Engine 2] For each target stock → evaluate new put (pattern + delta + sizing)

  For each open put:
    [Engine 3] If profit ≥ 60% → close, evaluate re-entry
    [Engine 4] If near ATM or ITM → assess pattern, roll or hold

  Check cross-engine rules (earnings, cash floor, account isolation)
  Generate ranked recommendations (highest priority first)
```

---

*Companion document: `OPTIONS-STRATEGY-V6-PHILOSOPHY.md`*
