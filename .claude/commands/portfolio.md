# Portfolio Snapshot

When this skill is invoked, run the following two Python scripts via Bash to pull live data from the database, then present a clean summary and wait for questions.

## Step 1 — Stock Holdings

Run this script from the `backend/` directory:

```bash
cd /Users/neelpersonal/Coding-Projects/agrawal-estate-planner/backend && python3 -c "
from app.core.database import SessionLocal
from app.modules.investments.models import InvestmentHolding, InvestmentAccount
from sqlalchemy import and_

db = SessionLocal()
rows = db.query(InvestmentHolding, InvestmentAccount).join(
    InvestmentAccount,
    and_(InvestmentHolding.account_id == InvestmentAccount.account_id,
         InvestmentHolding.source == InvestmentAccount.source)
).filter(
    InvestmentHolding.quantity > 0,
    InvestmentHolding.source == 'robinhood',
).order_by(InvestmentAccount.account_name, InvestmentHolding.market_value.desc()).all()

current_acct = None
total_value = 0
print('STOCK HOLDINGS')
print('=' * 70)
for h, a in rows:
    if a.account_name != current_acct:
        print(f'\n{a.account_name}  (last pasted: {h.last_updated.strftime(\"%b %d, %Y\") if h.last_updated else \"unknown\"})')
        print(f'  {\"Symbol\":<8} {\"Shares\":>8}  {\"Price\":>10}  {\"Mkt Value\":>14}  {\"Options Cap\":>11}')
        print(f'  {\"-\"*8} {\"-\"*8}  {\"-\"*10}  {\"-\"*14}  {\"-\"*11}')
        current_acct = a.account_name
    qty = float(h.quantity or 0)
    price = float(h.current_price or 0)
    value = float(h.market_value or 0)
    contracts = int(qty // 100)
    total_value += value
    cap_str = f'{contracts} contracts' if contracts > 0 else 'too few'
    print(f'  {h.symbol:<8} {qty:>8.0f}  \${price:>9.2f}  \${value:>13,.2f}  {cap_str:>11}')

print(f'\n{\"=\" * 70}')
print(f'TOTAL PORTFOLIO VALUE: \${total_value:,.2f}')
db.close()
"
```

## Step 2 — Open Options Positions

Run this script to get the most recent options snapshot per account:

```bash
cd /Users/neelpersonal/Coding-Projects/agrawal-estate-planner/backend && python3 -c "
from app.core.database import SessionLocal
from app.modules.strategies.models import SoldOption, SoldOptionsSnapshot
from sqlalchemy import func

db = SessionLocal()

# Get the latest snapshot id per account
latest = db.query(
    SoldOptionsSnapshot.account_name,
    func.max(SoldOptionsSnapshot.id).label('max_id')
).group_by(SoldOptionsSnapshot.account_name).all()

latest_ids = [row.max_id for row in latest]

snapshots = db.query(SoldOptionsSnapshot).filter(
    SoldOptionsSnapshot.id.in_(latest_ids)
).order_by(SoldOptionsSnapshot.account_name).all()

print('OPEN OPTIONS POSITIONS')
print('=' * 80)

total_options = 0
for snap in snapshots:
    opts = db.query(SoldOption).filter(
        SoldOption.snapshot_id == snap.id,
        SoldOption.status != 'closed'
    ).order_by(SoldOption.symbol, SoldOption.expiration_date).all()
    
    if not opts:
        continue
    
    print(f'\n{snap.account_name}  (snapshot: {snap.snapshot_date.strftime(\"%b %d, %Y %I:%M %p\")})')
    print(f'  {\"Symbol\":<8} {\"Type\":<5} {\"Strike\":>8} {\"Expiry\":<12} {\"Contracts\":>9} {\"Premium\":>10} {\"Status\":<10}')
    print(f'  {\"-\"*8} {\"-\"*5} {\"-\"*8} {\"-\"*12} {\"-\"*9} {\"-\"*10} {\"-\"*10}')
    
    for o in opts:
        strike = f'\${float(o.strike_price):.2f}' if o.strike_price else 'N/A'
        premium = f'\${float(o.premium_per_contract):.2f}' if o.premium_per_contract else 'N/A'
        expiry = o.expiration_date.strftime('%b %d, %Y') if o.expiration_date else 'N/A'
        print(f'  {o.symbol:<8} {(o.option_type or \"\"):<5} {strike:>8} {expiry:<12} {(o.contracts_sold or 0):>9} {premium:>10} {(o.status or \"\"):<10}')
        total_options += 1

print(f'\n{\"=\" * 80}')
print(f'TOTAL OPEN OPTION POSITIONS: {total_options}')
db.close()
"
```

## Step 3 — Present and Answer Questions

After running both scripts, present the output clearly under two sections:
- **Stock Holdings** — summarize total portfolio value, call out any accounts with stale data (last pasted > 7 days ago)
- **Open Options** — summarize total open positions, group by account

Then say: "Ask me anything about your holdings or options — position sizing, income projections, what to sell next, risk concentration, etc."

Be ready to run additional queries against the database to answer specific questions. The database connection string is:
`postgresql://agrawal_user:agrawal_secure_2024@localhost:5432/agrawal_estate`

Key tables:
- `investment_holdings` — current stock positions
- `investment_accounts` — account metadata  
- `sold_options` + `sold_options_snapshots` — open options positions
- `investment_transactions` — all historical STO/BTC/BUY/SELL transactions
- `portfolio_snapshots` — monthly portfolio value history

---

## Step 4 — V5 Recommendation Framework

When the user asks for a recommendation on any position (e.g. "what should I do with TSLA?", "should I roll?", "what can I sell?"), apply the V5 algorithm logic below. Always fetch live Schwab option chain data to support the analysis.

### Fetching Live Option Data

Use this snippet (run from `backend/` with `./venv/bin/python`):

```python
from app.modules.strategies.schwab_service import get_options_chain_schwab

result = get_options_chain_schwab('SYMBOL', expiration_date='YYYY-MM-DD', option_type='CALL')
# result['calls'] / result['puts'] — list of {strike, bid, ask, delta, openInterest, inTheMoney, expirationDate}
# result['underlying_price'] — current stock price
```

To fetch multiple expirations at once, omit `expiration_date`. To compare roll credits across weeks:
- Close cost = `ask` of the current option (what you pay to buy back)
- New premium = `bid` of the target option (what you receive when selling)
- Net credit = New premium bid − Close cost ask (positive = credit, negative = debit)

---

### V5 Core Philosophy

1. **Every share should generate income** — uncovered shares are idle capital
2. **Mean reversion is inevitable** — don't panic on ITM, be patient
3. **Weekly income is the primary goal** — prefer compressing over extending
4. **Hold forever** — never forced into selling shares
5. **Avoid forced assignment** — manage positions before expiry
6. **Don't let a winner become a loser** — take profits at 70%+

---

### Step 1: Classify Each Open Position

#### IV Category (determines all thresholds)
| IV Level | Symbols |
|---|---|
| **high_iv** | TSLA, HOOD, COIN, MARA, RIOT, GME, RIVN |
| **low_iv** | AAPL, MSFT, GOOGL, AMZN, META |
| **medium_iv** | Everything else (NVDA, AVGO, RKLB, IBIT, PLTR, MU, NFLX, etc.) |

#### ITM% Calculation
```
For calls: ITM% = (current_price - strike) / strike × 100  [only when current_price > strike]
For puts:  ITM% = (strike - current_price) / strike × 100  [only when strike > current_price]
OTM positions: ITM% = 0
```

#### Stuck Category by ITM% and IV
| Category | high_iv | medium_iv | low_iv | Meaning |
|---|---|---|---|---|
| **HEALTHY** | <5% ITM | <5% ITM | <5% ITM | Standard management |
| **STUCK** | 5–30% ITM | 5–17% ITM | 5–10% ITM | Weekly rolls still yield credit |
| **LIFE_SUPPORT** | 30–35% ITM | 17–22% ITM | 10–15% ITM | Weekly debit, biweekly/monthly still credit |
| **DROWNING** | >35% ITM | >22% ITM | >15% ITM | All rolls are debits — close immediately |

#### Intrinsic % (from V4, still used in V5)
```
Intrinsic value (calls) = max(0, current_price − strike)
Time value = current_premium − intrinsic_value
Intrinsic % = intrinsic_value / current_premium × 100
```
| Intrinsic % | Category | Implication |
|---|---|---|
| 0–25% | SAFE | Time is your friend, theta is working |
| 25–40% | LOW BAD | Still manageable with patience |
| 40–55% | MEDIUM | Decision point — evaluate compression |
| 55–70% | MED-HIGH | Stock must move, compression expensive |
| 70%+ | HIGH BAD / CATASTROPHIC | Close or accept assignment |

#### Profit % on open position
```
profit_pct = (original_premium − current_premium) / original_premium
```

---

### Step 2: Apply Decision Logic

#### A. OTM Positions (stock hasn't crossed strike)

| Condition | Action | Notes |
|---|---|---|
| profit_pct ≥ 70% | **CLOSE** | Lock in profits — don't let winner become loser |
| profit_pct ≥ 80% AND ≤2 days to expiry | **CLOSE + RE-ENTER** | Close and immediately sell next week |
| ≤2 days to expiry, profitable | **ROLL to next week** | Time cushion rule — never let expire with risk |
| profit_pct 50–70%, >7 days left | **HOLD** | Let theta work |
| profit_pct <50%, >7 days left | **HOLD** | Continue collecting decay |

#### B. ITM Positions — by stuck category

**HEALTHY (<5% ITM):**
- Look for weekly same-strike roll for net credit
- If credit available → ROLL
- If slight debit (≤$1/contract) and mean reversion likely → HOLD/WAIT

**STUCK:**
- Fetch weekly same-strike roll credit from Schwab
- If weekly credit ≥ $0 → ROLL weekly (keep income flowing)
- If weekly is debit → Check biweekly/monthly for credit
- Do NOT compress to a far-dated expiry (V4 lesson: 4-week max extension)

**LIFE_SUPPORT:**
- Weekly roll is a debit — skip it
- Check biweekly: if credit → ROLL_BIWEEKLY
- Check monthly: if credit → ROLL_MONTHLY
- Set price alert for mean reversion (when stock pulls back, reassess)

**DROWNING:**
- All roll durations are debits
- **CLOSE immediately** — stop the bleeding
- Accept the loss; reinvest capital in fresh positions

#### C. Uncovered Shares (shares with no sold calls, ≥100 shares)

| Stock Condition | Action | Logic |
|---|---|---|
| Stock up or flat from cost basis | **SELL call** | Good time to capture premium |
| Stock down significantly | **WAIT** | Don't sell at bottom — wait for recovery |

For SELL recommendations, target **Delta 10–15 OTM calls** (weekly expiry). Higher delta = more premium but more risk.

---

### Step 3: Formulate the Recommendation

For every recommendation, always include:
1. **Action** — HOLD / CLOSE / ROLL / ROLL_BIWEEKLY / ROLL_MONTHLY / SELL / WAIT
2. **Stuck category** — HEALTHY / STUCK / LIFE_SUPPORT / DROWNING (for ITM) or OTM % cushion
3. **Specific trade** — exact strike, expiry, and net credit/debit from live Schwab data
4. **Why** — which V5 belief or rule drives this
5. **Risk** — what could go wrong and at what price level

For roll recommendations always show:
```
BTC [current expiry] $[strike] [type] @ $[ask] — cost: $[ask × contracts × 100]
STO [new expiry]     $[strike] [type] @ $[bid] — income: $[bid × contracts × 100]
Net credit: $[net × contracts × 100]  |  Per contract: $[net]
```

---

### Key Rules from Trading History

- **4-week max extension** — Never roll out more than 4 weeks to escape ITM (V4 lesson: MU got trapped at 3 months)
- **Compress over extend** — If same strike is available at a shorter expiry for credit, always prefer it
- **Weekly income first** — The goal is weekly cash flow, not avoiding all risk
- **AAPL has 17 contracts** — Neel's brokerage; largest position, treat with care on roll timing
- **TSLA May 15 $410 calls** — 9 Neel + 9 Jaya; currently OTM by ~$36, healthy cushion
- **AVGO $325 calls** — Watch for assignment risk given deep ITM nature when they appear
