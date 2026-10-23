"""Test the candidate signals on the generic episodes (runaway_call/put.json
from runaway.py).  Calls: a broad relief rally — the market had sold off when
the call was sold, then most of the universe jumped together.  Puts: the
mirror, plus the two things CBRS is — a stock-specific collapse, and a
recent listing."""
import json, sys
import pandas as pd
W = sys.argv[1]
raw = json.load(open(f'{W}/daily_long.json'))
first_day = {s: rows[0][0] for s, rows in raw.items()}
def show(name, d):
    if len(d) == 0: print(f'  {name:58} n=0'); return
    print(f"  {name:58} n={len(d):3}  not back in 13w {1-d.back.mean():4.0%}  "
          f"buy-back better {1-d.wait_better.mean():4.0%}  mean waiting cost {d.wait_cost.mean():+.3f}  "
          f"credits {d.credits.mean():.3f}")

c = pd.read_json(f'{W}/runaway_call.json', convert_dates=False)
print('CALLS (generic, 10 years)')
show('all stuck calls', c)
for dd, br in ((-0.07, 0.6), (-0.07, 0.5), (-0.10, 0.6), (-0.05, 0.6)):
    sig = (c.qqq_dd60 <= dd) & (c.breadth >= br)
    show(f'relief rally: QQQ <= {dd:.0%} at sale & breadth >= {br}', c[sig])
    show('  ... everything else', c[~sig])
sig = (c.qqq_dd60 <= -0.07) & (c.breadth >= 0.6)
for per, d in (('2016-2020', c[c.date < '2021']), ('2021-2026', c[c.date >= '2021'])):
    show(f'  {per} signal', d[sig[d.index]]); show(f'  {per} no signal', d[~sig[d.index]])
print('  fired on:'); print(c[sig].groupby(c[sig].date.str[:7]).sym.apply(lambda s: ' '.join(sorted(set(s)))).to_string())
show('breadth >= 0.6 alone', c[c.breadth >= 0.6])
show('VIX fell >= 4 pts in 20d & breadth >= 0.6', c[(c.vix_chg20 <= -4) & (c.breadth >= 0.6)])

p = pd.read_json(f'{W}/runaway_put.json', convert_dates=False)
p['age_days'] = (pd.to_datetime(p.date) - pd.to_datetime(p.sym.map(first_day))).dt.days
print('\nPUTS (generic, 10 years)')
show('all stuck puts', p)
show('mirror: QQQ at its high at sale & breadth (down) >= 0.6', p[(p.qqq_dd60 > -0.03) & (p.breadth >= 0.6)])
show('market falling: QQQ 20d <= -5%', p[p.qqq20 >= 0.05])   # qqq20 is direction-signed: + = down for puts
own = (p.qqq20 < 0.02)
show("stock's own fall: QQQ 20d not down > 2%", p[own])
show("  ... and stock >= 20% below its 200-day average", p[own & (p.ma200 >= 0.20)])
show("  ... and stock >= 35% below its 200-day average", p[own & (p.ma200 >= 0.35)])
show('stuck >= 20% in the money', p[p.depth >= 0.20])
show('within 18 months of listing', p[p.age_days <= 550])
print('  by symbol:'); print(p[p.age_days <= 550].groupby('sym').agg(n=('back', 'size'), back=('back', 'mean'), cost=('wait_cost', 'mean')).to_string(float_format=lambda x: f'{x:.2f}'))
show('older than 18 months', p[p.age_days > 550])
