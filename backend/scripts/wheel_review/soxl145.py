"""Neel 23 Oct: 'when it comes back, maybe in a couple of weeks, it will easily
cross 145.' SOXL $83.41 -> $145 is +74%. How often has SOXL done that?"""
import json, math, sys
import pandas as pd, numpy as np
W = sys.argv[1]
raw = json.load(open(f'{W}/daily_long.json'))
def ser(sym):
    x = pd.Series({r[0]: r[2] for r in raw[sym]}); x.index = pd.to_datetime(x.index); return x.sort_index()
s = ser('SOXL'); smh = ser('SMH').reindex(s.index).ffill()
print('last rows:'); print(pd.DataFrame({'SOXL': s, 'SMH': smh}).tail(18).round(2))
need = 145 / 83.41 - 1
print(f'\nneed +{need:.1%}')
# any start day: max close within N trading days >= start*1.74
for N in (10, 15, 20, 40, 60):
    fmax = s[::-1].rolling(N, min_periods=1).max()[::-1].shift(-1)
    hit = (fmax / s - 1 >= need)
    print(f'any day, +74% within {N} days: {hit.mean():.2%} of days ({hit.sum()} days)')
# best 10-day and 20-day gains ever, de-clustered
for N in (10, 20):
    g = (s.shift(-N) / s - 1)
    fmax = s[::-1].rolling(N, min_periods=1).max()[::-1].shift(-1) / s - 1
    top = fmax.sort_values(ascending=False)
    seen = []
    print(f'\nbest max-gain within {N} trading days (de-clustered 30d):')
    for d, v in top.items():
        if any(abs((d - x).days) < 45 for x in seen): continue
        seen.append(d)
        print(f'  {d.date()} SOXL {s[d]:.2f} -> max +{v:.0%}')
        if len(seen) == 8: break
# crash episodes like today: >=35% below 15d high
hi15 = s.rolling(15).max(); dd = s / hi15 - 1
eps = []; last = -999
for i in range(260, len(s)):
    if dd.iloc[i] <= -0.35 and i - last > 30:
        eps.append(i); last = i
print(f'\n{len(eps)} crash episodes (>=35% below 15-day high):')
print(' date        SOXL   dd    max10   max20   max60   back-to-prior-high-12%(=145-equiv)')
c = {10: 0, 20: 0, 60: 0}; cb = 0
for i in eps:
    p = s.iloc[i]
    row = []
    for N in (10, 20, 60):
        m = s.iloc[i+1:i+1+N].max() / p - 1 if i + 1 < len(s) else float('nan')
        row.append(m)
        if m >= need: c[N] += 1
    # Neel's analogue: back to within 12% of the 15-day high (145 vs 164)
    tgt = hi15.iloc[i] * 145 / 164
    w = s.iloc[i+1:i+61]
    hitd = (w >= tgt).idxmax() if (w >= tgt).any() else None
    if hitd is not None: cb += 1
    print(f' {s.index[i].date()} {p:7.2f} {dd.iloc[i]:5.0%}  {row[0]:+5.0%}  {row[1]:+5.0%}  {row[2]:+5.0%}   {"wk " + str(round((s.index.get_loc(hitd)-i)/5,1)) if hitd is not None else "no"}')
print(f'+74% within 10d: {c[10]}/{len(eps)}, 20d: {c[20]}/{len(eps)}, 60d: {c[60]}/{len(eps)}; back to prior-high-12% within 12 wks: {cb}/{len(eps)}')
# SMH move needed: what SMH level was SOXL 145 at recently?
r = s.loc['2026-09-01':]
print('\nSOXL vs SMH since Sep:'); print(pd.DataFrame({'SOXL': r, 'SMH': smh.loc['2026-09-01':]}).iloc[::3].round(2))

# 2026 regime only, and SMH-equivalent move
y = s.loc['2026-01-01':]
for N in (10, 20):
    fmax = s[::-1].rolling(N, min_periods=1).max()[::-1].shift(-1)
    hit = (fmax / s - 1 >= need).loc['2026-01-01':'2026-09-25']
    print(f'2026 only, +74% within {N} days: {hit.mean():.1%} of days')
sneed = 600 / 527.05 - 1
for N in (10, 20):
    fmax = smh[::-1].rolling(N, min_periods=1).max()[::-1].shift(-1)
    hit = (fmax / smh - 1 >= sneed)
    print(f'SMH +{sneed:.1%} within {N} days: all {hit.mean():.2%}; 2026 {hit.loc["2026-01-01":"2026-09-25"].mean():.1%}')
# from the crash LOW of each 2026 episode (hindsight best case)
for a, b in (('2026-03-01', '2026-04-15'), ('2026-06-01', '2026-06-30'), ('2026-07-15', '2026-08-15')):
    w = s.loc[a:b]; lo = w.idxmin(); i = s.index.get_loc(lo)
    print(f'{lo.date()} low {s[lo]:.2f}: max10 {s.iloc[i+1:i+11].max()/s[lo]-1:+.0%}, max20 {s.iloc[i+1:i+21].max()/s[lo]-1:+.0%}')
