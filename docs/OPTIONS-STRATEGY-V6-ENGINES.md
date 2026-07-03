# Options Strategy — V6 Engine Spec

**Version:** 6.1  
**Status:** ✅ ACTIVE  
**Created:** 2026-05-23  
**Updated:** 2026-05-29 (V6.1 — Two-Tier Classification)  
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

### Tier-aware delta selection (V6.1)

**Tier 1 (mega-cap hold — AAPL, MSFT, NVDA, AVGO, GOOGL, AMZN, META, LLY):**

The goal is income supplementation without getting called away.

| Account | Delta Target | Notes |
|---|---|---|
| IRA | 15 delta (15% chance ITM) | Protect the long-term position while earning some premium |
| Taxable | 10–15 delta | Conservative — the shares carry embedded gains; losing them is the bad outcome |

**TSLA carve-out — applies in both IRA and taxable:**
- Delta 10–12 only (88–90% probability OTM)
- Only fire when RSI > 75 (stock is already significantly overbought)
- Expected: ~$100–125/contract/week — accept this; do not stretch for more
- If the call goes ITM: roll at zero cost, never panic-close (TSLA $70K lesson)
- TSLA calls in taxable accounts also risk triggering wash sale rules on rolls — confirm tax situation if applicable

**Tier 2 (sub-$1T wheel — PLTR, HOOD, COIN, AMD, SHOP, INTC, RKLB, etc.):**

The goal is aggressive income from shares acquired via put assignment. Getting called away is the plan.

| Account | Delta Target | Notes |
|---|---|---|
| IRA | 80 delta (80% chance ITM — aggressive) | Assignment is wanted; high premium is the priority |
| Taxable | 80 delta | Same — assignment was planned when the put was sold; consistent follow-through |

**Additional rules (all tiers):**
- Strike must be at or above the average cost basis for the account (never sell at a loss if assigned).
- Tier 1: prefer the strike that satisfies the delta target; don't go lower OTM just for safety (you'll earn almost nothing).
- Tier 2: strike can be at or near ATM — the goal is high premium and expected assignment.
- Expiration: Friday of the same week or next Friday. Never more than 2 weeks out for a new entry.

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

This is the primary income engine in V6. See Philosophy §1–§8 for the full context. In V6.1, put strategy splits by tier.

### When to fire

A stock qualifies if:
- It is in the portfolio holdings OR it is on the approved target list (stocks we believe in and would own more of)
- Available cash in the account is sufficient to cover the put (strike × 100 × contracts)
- Technical conditions are favorable (see below)
- Not within 5 days of earnings

### Tier 1: Mega-Cap Put Rules (AAPL, MSFT, NVDA, AVGO, GOOGL, AMZN, META, LLY)

Puts on mega-cap stocks are used to accumulate more of a stock we want to hold forever — not for aggressive wheeling.

**IRA accounts:**
- Delta target: 70–80 (aggressive)
- Assignment is always fine — no tax, cost basis becomes the strike
- Use RSI < 40 as entry signal

**Taxable accounts:**
- Delta target: 90 (conservative)
- Max % of available cash per position: 30%
- Assignment requires cost basis check (see Philosophy §3)
- Never sell TSLA puts in taxable if sitting on large embedded gains — assignment would dramatically raise average cost

**Entry conditions (Tier 1):**

| Indicator | Favorable | Neutral | Unfavorable |
|---|---|---|---|
| RSI | < 40 | 40–60 | > 60 |
| Recent move | Down 3%+ from recent high | Flat | Up 5%+ recently |
| Stock pattern | Oscillating | Unknown | Runaway |

**For runaway mega-cap stocks:**
- Go lower delta (50–60), further OTM
- "Get paid to wait" — earn premium while waiting for price to stabilize
- Expiration: 2–3 weeks out (not weekly — too much risk on a runaway)

### Tier 2: Sub-$1T Aggressive Wheel Puts (PLTR, HOOD, COIN, AMD, SHOP, INTC, RKLB, CRCL, FIG, MSTR, NFLX, etc.)

Sub-$1T puts are the aggressive income engine. Assignment is welcomed and planned.

**IRA accounts:**
- Delta target: 80 (aggressive — high premium, high assignment probability)
- Assignment is always fine — no tax, immediately sell covered calls post-assignment
- Entry signal: RSI < 50 is sufficient (don't wait for extreme oversold — these stocks move too fast)

**Taxable accounts:**
- Delta target: 80 (same aggressive stance — planned assignment is a consistent strategy, not a surprise)
- Max % of available Tier 2 allocation per position: 50% (spread across 2–3 names)
- Short-term gains from assignment are expected and acceptable — size accordingly

**Entry conditions (Tier 2):**

| Indicator | Favorable | Neutral | Unfavorable |
|---|---|---|---|
| RSI | < 50 | 50–65 | > 65 |
| Recent move | Flat or down | Up 3–5% | Up 10%+ |
| IV rank | High (above 30th percentile) | Medium | Very low |

**What to do after Tier 2 assignment:**

Immediately apply Engine 1 (Tier 2 rules): sell delta 80 covered calls. When those shares get called away, sell delta 80 puts again. This is the full wheel cycle — every assignment and call-away is planned.

### Account-wide allocation check (V6.1 — 80/20 Rule)

Before recommending a new put, verify the account's tier allocation:

```
Tier 1 exposure = (value of Tier 1 holdings + Tier 1 put cash reserved) / total account value
Tier 2 exposure = (value of Tier 2 holdings + Tier 2 put cash reserved) / total account value

Target: Tier 1 ≥ 80%, Tier 2 ≤ 20%
```

If Tier 2 is already at or above 20%, do not recommend a new Tier 2 put even if conditions are favorable. Prioritize Tier 1 opportunities or hold cash.

### Position sizing

```
Max contracts = floor(available_cash * max_pct / (strike * 100))

Where:
  max_pct (IRA, Tier 1): 0.80 of Tier 1 cash allocation
  max_pct (taxable, Tier 1): 0.30 of Tier 1 cash allocation
  max_pct (IRA, Tier 2): 0.50 of Tier 2 cash allocation
  max_pct (taxable, Tier 2): 0.50 of Tier 2 cash allocation
```

Don't max out every position. If 3 puts are already running across the portfolio, be selective about adding a 4th.

### What to recommend

```
Action: SELL PUT
Symbol: [SYMBOL]
Tier: TIER 1 (MEGA-CAP) / TIER 2 (SUB-$1T WHEEL)
Account: [ACCOUNT]
Strike: $[X] (delta [Y], [Z]% OTM)
Expiration: [DATE]
Premium: ~$[W]/contract
Cash Required: $[X*100 per contract]
Pattern: OSCILLATING / RUNAWAY
Assignment Plan: [for Tier 1: own more shares; for Tier 2: sell covered calls at delta 80]
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
# ── Tier 1: Mega-cap hold tier ──────────────────────────────────────────────
TIER1_PUT_DELTA_IRA = 70–80          # target delta for IRA Tier 1 puts
TIER1_PUT_DELTA_TAXABLE = 90         # target delta for taxable Tier 1 puts
TIER1_CALL_DELTA_IRA = 15            # target delta for IRA Tier 1 calls
TIER1_CALL_DELTA_TAXABLE = 10–15     # target delta for taxable Tier 1 calls

# TSLA carve-out (applies in both IRA and taxable)
TSLA_CALL_DELTA_MAX = 12             # never exceed delta 12 for TSLA calls
TSLA_CALL_RSI_MIN = 75               # only sell TSLA calls when RSI > 75

# LLY: named inclusion in Tier 1 despite ~$750B market cap
# Apply Tier 1 rules: CALL_DELTA 10–15, conservative puts only

# ── Tier 2: Sub-$1T aggressive wheel tier ──────────────────────────────────
TIER2_PUT_DELTA = 80                 # both IRA and taxable — aggressive wheel
TIER2_CALL_DELTA = 80                # both IRA and taxable — aggressive wheel
TIER2_RSI_PUT_ENTRY = 50             # enter puts below this (wider than Tier 1)

# ── Portfolio allocation ────────────────────────────────────────────────────
TIER1_TARGET_PCT = 0.80              # each account: 80% in Tier 1
TIER2_MAX_PCT = 0.20                 # each account: max 20% in Tier 2

# ── Position sizing ─────────────────────────────────────────────────────────
TIER1_CASH_MAX_IRA = 0.80            # of Tier 1 cash allocation
TIER1_CASH_MAX_TAXABLE = 0.30        # of Tier 1 cash allocation
TIER2_CASH_MAX = 0.50                # per position, of Tier 2 cash allocation

# ── Shared ──────────────────────────────────────────────────────────────────
PROFIT_TAKE_THRESHOLD = 0.60         # close at 60%+ profit
MAX_ESCAPE_WEEKS = 4                 # from V4; still applies
INTRINSIC_CROSSOVER = 0.60           # above this: stock must move (calls)

CASH_FLOOR_TAXABLE = 0.30            # keep 30% cash free in taxable (Tier 1)
CASH_FLOOR_IRA = 0.20                # keep 20% cash free in IRA (Tier 1)

RSI_OVERSOLD = 30                    # don't sell calls below this
RSI_OVERBOUGHT = 60                  # don't sell Tier 1 puts above this
RSI_CALL_ENTRY = 60                  # sell calls above this
RSI_PUT_ENTRY_TIER1 = 40             # sell Tier 1 puts below this
RSI_PUT_ENTRY_TIER2 = 50             # sell Tier 2 puts below this (more lenient)

MIN_DAYS_TO_EXPIRY_ENTRY = 5         # don't open new positions < 5 DTE
ROLL_NEAR_EXPIRY_DAYS = 2            # roll if < 2 days to expiry and ITM/near-ATM
```

---

## Decision Flow Summary

```
For each account:
  Classify each holding and cash target as Tier 1 (mega-cap) or Tier 2 (sub-$1T wheel)
  Check 80/20 allocation: if Tier 2 ≥ 20%, do not add new Tier 2 positions

  For each holding (100+ shares):
    [Engine 1] If no open call → evaluate new call
      Tier 1: delta 10–15 (TSLA: delta 10–12 only if RSI > 75)
      Tier 2: delta 80 (aggressive wheel — assignment expected)

  For each open call:
    [Engine 3] If profit ≥ 60% → evaluate early close
    [Engine 4] If ITM → assess intrinsic %, trigger stuck logic

  For available cash (Tier 1 allocation):
    [Engine 2] For each Tier 1 target stock → evaluate put
      RSI < 40 + oscillating → enter at delta 70–80 (IRA) or 90 (taxable)
      Runaway → lower delta (50–60), 2–3 week expiry

  For available cash (Tier 2 allocation, if Tier 2 < 20%):
    [Engine 2] For each Tier 2 target stock → evaluate put
      RSI < 50 → enter at delta 80 both accounts
      Plan: if assigned, immediately sell delta 80 calls (Engine 1)

  For each open put:
    [Engine 3] If profit ≥ 60% → close, evaluate re-entry
    [Engine 4] If near ATM or ITM → assess pattern, roll or hold

  Check cross-engine rules (earnings, cash floor, account isolation)
  Generate ranked recommendations (highest priority first)
```

---

*Companion document: `OPTIONS-STRATEGY-V6-PHILOSOPHY.md`*
