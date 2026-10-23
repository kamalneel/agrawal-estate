"""Splits and put-side checks on daily prices (after chains/classify/cf/rollout)."""
import json, sys, os
from collections import defaultdict
from datetime import date
sys.path.insert(0, '/Users/neelpersonal/Coding-Projects/agrawal-estate-planner/backend')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.database import SessionLocal
from sqlalchemy import text
from daily_prices import Daily
W = sys.argv[1]; db = SessionLocal(); DP = Daily(f'{W}/daily.json')
C = json.load(open(f'{W}/chains_daily.json'))
RO = json.load(open(f'{W}/rollout.json'))
CF = json.load(open(f'{W}/cf.json'))
ep = lambda start: start[:7] in ('2026-03', '2026-04')
D = date.fromisoformat
now = {r.symbol: float(r.p) for r in db.execute(text("SELECT symbol, max(current_price) p FROM investment_holdings WHERE current_price IS NOT NULL GROUP BY 1"))}
def now_px(s): return now.get(s) or DP.on(s, date.today())

print('BUY-BACK / LET-ASSIGN at 5% (exact fills), split by period')
agg = defaultdict(lambda: [0, 0, 0, 0])
for r in CF:
    t = r['trig'].get('5')
    if not t: continue
    k = (r['type'], 'Mar-Apr' if ep(r['start']) else 'other'); a = agg[k]
    a[0] += 1; a[1] += r['R']; a[2] += t['B']; a[3] += (t['A'] if t['A'] is not None else r['R'])
for k, (n, a, b, l) in sorted(agg.items()):
    print(f"  {k[0]:4} {k[1]:8} n={n:3} actual {a:>10,.0f} | buy back & stop {b-a:>+10,.0f} | let assign {l-a:>+10,.0f}")

print('\n13-WEEK ROLL at 5% (Black-Scholes on daily realized vol), split by period')
agg = defaultdict(lambda: [0, 0, 0, 0])
for x in RO:
    k = (x['typ'], 'Mar-Apr' if ep(x['start']) else 'other'); a = agg[k]
    a[0] += 1; a[1] += x['actual']; a[2] += x['same']; a[3] += x['up']
for k, (n, a, s, u) in sorted(agg.items()):
    print(f"  {k[0]:4} {k[1]:8} n={n:3} actual {a:>10,} | same strike {s-a:>+10,} | zero-cost strike {u-a:>+10,}")
openish = [x for x in RO if x['open_at_today']]
print(f"  ({len(openish)} of these 13-week rolls would still be open today — valued at today's intrinsic)")

print('\nASSIGNED PUTS by the 12-week move before the sale (prior close), valued today')
P = [c for c in C if c['type'] == 'put']
def today_val(c):
    sh = sum(x['q'] for x in c['assigned']) * 100
    if not sh: return c['net']
    s = now_px(c['symbol']); k = c['assigned'][-1]['k']
    return c['net'] + ((s - k) * sh if s else -c['assign_cost'])
def b12(v):
    if v is None: return 'n/a'
    return 'down/flat' if v < 0.05 else 'up 5-20%' if v < .2 else 'up 20-50%' if v < .5 else 'up >50%'
agg = defaultdict(lambda: [0, 0, 0.0, 0.0])
for c in P:
    sh = sum(x['q'] for x in c['assigned']) * 100
    if not sh: continue
    a = agg[b12(c['ret12w0d'])]; a[0] += 1; a[1] += sh; a[2] += c['result']; a[3] += today_val(c)
for k in ('down/flat', 'up 5-20%', 'up 20-50%', 'up >50%', 'n/a'):
    if k in agg:
        n, sh, r, t = agg[k]; print(f"  {k:10} chains {n:3} shares {sh:6.0f} | assignment day {r:>9,.0f} | today {t:>9,.0f}")
print(f"  all put chains: premium {sum(c['net'] for c in P):,.0f} | assignment day {sum(c['result'] for c in P):,.0f} | today {sum(today_val(c) for c in P):,.0f}")
for thr in (0.2, 0.3, 0.5):
    b = [c for c in P if c['ret12w0d'] is not None and c['ret12w0d'] > thr]
    print(f"  skip puts after a >{int(thr*100)}% 12-week run: blocks {len(b)} | premium forgone {sum(c['net'] for c in b):,.0f} | their value today {sum(today_val(c) for c in b):,.0f}")

print('\nV8 8-WEEK PUT CAP: take the shares at the first roll >= 8 weeks in, still in the money')
n = act = cf = 0
for c in P:
    st = D(c['start']); by = defaultdict(list)
    for l in c['legs']: by[l['d']].append(l)
    cum = 0
    for d in sorted(by):
        ls = by[d]; btcs = [l for l in ls if l['t'] == 'BTC']
        if btcs and (D(d) - st).days >= 56:
            q = sum(b['q'] for b in btcs); k = btcs[0]['k']; cost = -sum(b['amt'] for b in btcs) / (q * 100)
            if cost > 0.01 * k:
                end = min(max([D(l['d']) for l in c['legs']] + [D(x['e']) for x in c['assigned']]), date.today())
                S = DP.on(c['symbol'], end)
                if S is not None:
                    n += 1; act += c['result']; cf += cum + (S - k) * q * 100
            break
        cum += sum(l['amt'] for l in ls)
print(f"  {n} chains | actual {act:,.0f} | cap {cf:,.0f} ({cf-act:+,.0f})")
