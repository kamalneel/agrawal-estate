"""Counterfactuals per chain. All results are relative to simply holding the
shares (calls) / not trading (puts), measured at the actual chain's end date.
Exact where possible: buy-back costs come from the actual BTC fills."""
import json, sys, bisect
from collections import defaultdict
from datetime import date, timedelta
sys.path.insert(0, '/Users/neelpersonal/Coding-Projects/agrawal-estate-planner/backend')
from app.core.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
W = sys.argv[1]
C = json.load(open(f'{W}/chains.json'))
px = defaultdict(list)
for r in db.execute(text("SELECT symbol, price_date, close_price FROM symbol_price_history ORDER BY 1, 2")):
    px[r.symbol].append((r.price_date, float(r.close_price)))
now = {r.symbol: float(r.p) for r in db.execute(text("SELECT symbol, max(current_price) p FROM investment_holdings WHERE current_price IS NOT NULL GROUP BY 1"))}
def price(sym, d):
    s = px.get(sym)
    if not s: return None
    i = bisect.bisect_right([x[0] for x in s], d) - 1
    return s[i][1] if i >= 0 and (d - s[i][0]).days <= 10 else None
D = lambda s: date.fromisoformat(s)

def roll_days(c):
    """[(date, btc_legs, sto_legs)] for days with a BTC, in order."""
    by = defaultdict(lambda: ([], []))
    for l in c['legs']:
        by[l['d']][0 if l['t'] == 'BTC' else 1].append(l)
    return [(d, *by[d]) for d in sorted(by)]

def end_date(c):
    ds = [D(l['d']) for l in c['legs']] + [D(x['e']) for x in c['assigned'] + c['expired']]
    return min(max(ds), date.today())

res = []
for c in C:
    typ, sym = c['type'], c['symbol']
    days = roll_days(c)
    H = end_date(c)
    S_H = price(sym, H) or now.get(sym)
    R = c['result']
    shares_by_strike = None
    row = dict(symbol=sym, account=c['account'], type=typ, start=c['start'], end=str(H), R=R,
               net=c['net'], assign_cost=c['assign_cost'], status=c['status'], otm0=c['otm0'],
               r4w0=c['ret4w0'], r12w0=c['ret12w0'], rolls=c['rolls'], weeks=c['weeks'])
    # walk the chain: cumulative premium before each BTC day
    cum = 0.0
    trig = {}
    for d, btcs, stos in days:
        if btcs:
            q = sum(b['q'] for b in btcs)
            cost_ps = -sum(b['amt'] for b in btcs) / (q * 100) if q else 0
            k = btcs[0]['k']
            itm_ps = cost_ps   # buy-back price per share ≈ intrinsic for weeklies
            for x in (0.03, 0.05, 0.10):
                if x not in trig and itm_ps >= x * k:
                    after_btc = cum + sum(b['amt'] for b in btcs)
                    # B: buy back here and stop (keep shares / no shares)
                    B = after_btc
                    # A3: let the leg be assigned at its expiry instead of rolling
                    e = D(btcs[0]['e']); S_e = price(sym, e) or (k + cost_ps if typ == 'call' else k - cost_ps)
                    sh = q * 100
                    if typ == 'call':
                        # shares gone at k; vs holding to the chain's end
                        A = cum - (S_H - k) * sh if S_H else None
                    else:
                        # bought at k; vs not trading, valued at the chain's end
                        A = cum + (S_H - k) * sh if S_H else None
                    trig[x] = dict(date=d, B=round(B), A=round(A) if A is not None else None,
                                   cost_ps=round(cost_ps, 2), k=k, q=q)
        cum += sum(l['amt'] for l in btcs + stos)
    row['trig'] = {str(int(x*100)): v for x, v in trig.items()}
    res.append(row)
json.dump(res, open(f'{W}/cf.json', 'w'), default=str)

def summarize(typ, x):
    L = [r for r in res if r['type'] == typ]
    fired = [r for r in L if str(x) in r['trig']]
    act = sum(r['R'] for r in fired)
    B = sum(r['trig'][str(x)]['B'] for r in fired)
    A = sum(r['trig'][str(x)]['A'] for r in fired if r['trig'][str(x)]['A'] is not None)
    helped = sum(1 for r in fired if r['trig'][str(x)]['B'] > r['R'])
    print(f"{typ:4} ITM≥{x:>2}%: fires on {len(fired):3} chains | actual {act:>10,.0f} | buy back & stop {B:>10,.0f} ({B-act:+,.0f}; better in {helped}/{len(fired)}) | let assign {A:>10,.0f} ({A-act:+,.0f})")
for typ in ('call', 'put'):
    for x in (3, 5, 10):
        summarize(typ, x)
