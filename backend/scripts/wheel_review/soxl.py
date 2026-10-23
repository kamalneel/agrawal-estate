"""SOXL-specific: after SOXL falls hard and fast (>= DROP below its 15-day
high), what happened next — and would a deep put have done better rolled
weekly at the same strike, or rolled once ~12 weeks out?

Episodes: first close at or below the drop line; the next episode only after
30 trading days. Forward path from daily closes 2015-2026 (split-adjusted).
Strikes are set where Neel's are today, as multiples of the trigger close
(SOXL $83.48: $110 = 1.32x, $120 = 1.44x, $135 = 1.62x).

Weekly: sell a one-week put at K each Friday while SOXL is below K, buy it back
at intrinsic at expiry; stop when a Friday close is back at or above K. Long:
sell one 12-week put at K on the trigger day. Both measured at week 12, per
share, excluding the buy-back of today's put (common to both). Black-Scholes
with a 4% rate; vol = 63-day realized x VM, VM calibrated on the 23 Oct live
SOXL quotes (Jan $110 put $36.33, 10/30 $110 put $26.90)."""
import json, math, sys
import pandas as pd, numpy as np
W = sys.argv[1]; DROP = float(sys.argv[2]) if len(sys.argv) > 2 else -0.35
raw = json.load(open(f'{W}/daily_long.json'))
def ser(sym):
    x = pd.Series({r[0]: r[2] for r in raw[sym]}); x.index = pd.to_datetime(x.index); return x.sort_index()
s = ser('SOXL'); smh = ser('SMH').reindex(s.index).ffill()
r = np.log(s).diff(); vol63 = r.rolling(63).std() * math.sqrt(252)
N = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
R = 0.04
def put(S, K, T, v):
    intr = max(K - S, 0)
    if T <= 0: return intr
    d1 = (math.log(S / K) + (R + v * v / 2) * T) / (v * math.sqrt(T)); d2 = d1 - v * math.sqrt(T)
    return max(K * math.exp(-R * T) * N(-d2) - S * N(-d1), intr)
# calibrate VM on today's quotes
S0, v0 = 83.48, vol63.iloc[-1]
for vm in (0.7, 0.8, 0.9, 1.0):
    print(f'VM {vm}: Jan $110 model {put(S0, 110, 84/365, v0*vm):.2f} (live 36.33) | 1-week $110 model {put(S0, 110, 7/365, v0*vm):.2f} (live 26.90)')
VM = float(sys.argv[3]) if len(sys.argv) > 3 else 0.9

hi15 = s.rolling(15).max(); dd = s / hi15 - 1
idx = s.index; eps = []; last = -999
for i in range(260, len(s) - 1):
    if dd.iloc[i] <= DROP and i - last > 30:
        eps.append(i); last = i
fridays = [i for i in range(len(idx)) if i + 1 == len(idx) or idx[i + 1].week != idx[i].week]
rows = []
for i in eps:
    S = s.iloc[i]; v = vol63.iloc[i] * VM
    fr = [f for f in fridays if f > i][:12]
    row = dict(date=str(idx[i].date()), S=round(S, 2), drop=round(dd.iloc[i], 2), vol=round(vol63.iloc[i], 2))
    for wk in (2, 4, 8, 12):
        j = i + wk * 5
        row[f'r{wk}w'] = round(s.iloc[j] / S - 1, 2) if j < len(s) else None
    j12 = min(i + 60, len(s) - 1)
    row['max12w'] = round(s.iloc[i + 1:j12 + 1].max() / S - 1, 2); row['min12w'] = round(s.iloc[i + 1:j12 + 1].min() / S - 1, 2)
    row['smh12w'] = round(smh.iloc[j12] / smh.iloc[i] - 1, 3) if i + 60 < len(s) else None
    row['complete'] = len(fr) == 12
    for mult in (1.32, 1.44, 1.62):
        K = S * mult
        # weekly
        tot = put(S, K, 7 / 365, v); stopped = False; wk_back = None
        for n, f in enumerate(fr):
            Sf = s.iloc[f]; tot -= max(K - Sf, 0)
            if Sf >= K: stopped = True; wk_back = n + 1; break
            if n < len(fr) - 1: tot += put(Sf, K, 7 / 365, vol63.iloc[f] * VM)
        lng = put(S, K, 84 / 365, v) - max(K - s.iloc[fr[-1]], 0) if fr else None
        row[f'wk{mult}'] = round(tot / K, 3); row[f'lg{mult}'] = round(lng / K, 3); row[f'back{mult}'] = wk_back
    rows.append(row)
df = pd.DataFrame(rows)
pd.set_option('display.width', 250)
print(f"\nSOXL episodes: close >= {-DROP:.0%} below its 15-day high (n={len(df)})")
print(df[['date', 'S', 'drop', 'vol', 'r2w', 'r4w', 'r8w', 'r12w', 'max12w', 'min12w', 'smh12w', 'back1.32', 'back1.44', 'back1.62']].to_string(index=False))
c = df[df.complete]
print(f"\nComplete episodes: {len(c)}")
for mult, lab in ((1.32, '$110-like (+32%)'), (1.44, '$120-like (+44%)'), (1.62, '$135-like (+62%)')):
    back = c[f'back{mult}'].notna().mean()
    wk = c[f'wk{mult}']; lg = c[f'lg{mult}']
    print(f"  strike {lab:18} back above strike within 12w: {back:4.0%} | weekly {wk.mean():+.3f} vs long {lg.mean():+.3f} of strike (mean); "
          f"long better in {(lg > wk).sum()}/{len(c)}; median diff {(lg - wk).median():+.3f}")
print('\n  per-episode, long - weekly (fraction of strike), $110-like:')
print('  ' + '  '.join(f"{d}:{x:+.2f}" for d, x in zip(c.date, c['lg1.32'] - c['wk1.32'])))
# leverage decay: SOXL 12w vs 3x SMH 12w
cc = c.dropna(subset=['smh12w'])
print('\n  12-week SOXL return vs 3x SMH (decay):', '  '.join(f"{d}: {a:+.0%} vs {3*b:+.0%}" for d, a, b in zip(cc.date, cc.r12w, cc.smh12w)))
df.to_json(f'{W}/soxl_episodes.json', orient='records')

# Roll period: sell a P-week put at K, at each expiry buy back at intrinsic; stop
# once an expiry close is back at or above K; measured at week 12.
def roll_period(i, K, P):
    fr = [f for f in fridays if f > i][:12]
    if len(fr) < 12: return None
    S = s.iloc[i]; tot = put(S, K, P * 7 / 365, vol63.iloc[i] * VM)
    exps = list(range(P - 1, 12, P))
    if exps[-1] != 11: exps.append(11)
    prev = -1
    for n in exps:
        Sf = s.iloc[fr[n]]; tot -= max(K - Sf, 0)
        if Sf >= K: return tot / K
        if n < 11:
            nxt = min(P, 11 - n)
            tot += put(Sf, K, nxt * 7 / 365, vol63.iloc[fr[n]] * VM)
    return tot / K
print('\nRoll period (weeks) — mean / median result as a fraction of strike, complete episodes:')
for mult in (1.32, 1.44, 1.62):
    out = []
    for P in (1, 2, 3, 4, 6, 12):
        v = [roll_period(i, s.iloc[i] * mult, P) for i in eps]; v = [x for x in v if x is not None]
        out.append(f"{P}w {np.mean(v):+.3f}/{np.median(v):+.3f}")
    print(f'  K = {mult}x  ' + ' | '.join(out))
