"""Neel's stuck calls, signal checked at EVERY roll while >=5% in the money
(not only the first): QQQ >=7% below its 60-day high when the chain's first
call was sold, and >=60% of the tracked names up >5% over the 10 days before
the roll. If it fires, B = buy back at that roll's actual fill and stop."""
import json, sys
from collections import defaultdict
import pandas as pd
W = sys.argv[1]
raw = json.load(open(f'{W}/daily_long.json'))
px = pd.DataFrame({s: pd.Series({r[0]: r[2] for r in rows}) for s, rows in raw.items()}); px.index = pd.to_datetime(px.index); px = px.sort_index()
STOCKS = [s for s in px.columns if s not in ('QQQ', 'SPY', 'SMH', '^VIX')]
q = px['QQQ']
def prior(d): return px.index.searchsorted(pd.Timestamp(d)) - 1
def qqq_dd(i): return q.iloc[i] / q.iloc[max(i - 60, 0):i + 1].max() - 1
def breadth(i):
    w = (px[STOCKS].iloc[i] / px[STOCKS].iloc[i - 10] - 1).dropna(); return float((w > 0.05).mean())
C = [c for c in json.load(open(f'{W}/chains.json')) if c['type'] == 'call']
cf = {(c['symbol'], c['account'], c['start']): c for c in json.load(open(f'{W}/cf.json')) if c['type'] == 'call'}
rows = []
for c in C:
    by = defaultdict(lambda: ([], []))
    for l in c['legs']: by[l['d']][0 if l['t'] == 'BTC' else 1].append(l)
    dd0 = qqq_dd(prior(c['start'])); cum = 0.0; fired = None; stuck = False
    for d in sorted(by):
        btcs, stos = by[d]
        if btcs:
            qn = sum(b['q'] for b in btcs); cost = -sum(b['amt'] for b in btcs) / (qn * 100)
            if cost >= 0.05 * btcs[0]['k']:
                stuck = True
                if dd0 <= -0.07 and breadth(prior(d)) >= 0.6 and not fired:
                    fired = dict(date=d, B=cum + sum(b['amt'] for b in btcs))
        cum += sum(l['amt'] for l in btcs + stos)
    if not stuck: continue
    R = cf[(c['symbol'], c['account'], c['start'])]['R']
    rows.append(dict(sym=c['symbol'], acct=c['account'], start=c['start'], rally='2026-03-01' <= c['start'] <= '2026-05-31',
                     fired=fired['date'] if fired else None, R=R, B=fired['B'] if fired else None))
df = pd.DataFrame(rows)
f = df[df.fired.notna()]
print(f"stuck call chains: {len(df)}  signal fired on {len(f)}")
print(f.sort_values('fired')[['sym', 'acct', 'start', 'fired', 'R', 'B']].to_string(index=False, float_format=lambda x: f'{x:,.0f}'))
for lab, g in f.groupby('rally'):
    print(f"  {'Mar-May 2026' if lab else 'other months'}: {len(g)} chains  actual {g.R.sum():,.0f}  buy back when it fired {g.B.sum():,.0f}  difference {g.B.sum() - g.R.sum():+,.0f}  better in {(g.B > g.R).sum()}/{len(g)}")
nf = df[df.fired.isna()]
print(f"  not fired: {len(nf)} chains ({nf.rally.sum()} from Mar-May 2026)  actual {nf.R.sum():,.0f}")
print(nf[nf.rally][['sym', 'acct', 'start', 'R']].to_string(index=False))
