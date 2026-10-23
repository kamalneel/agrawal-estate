"""The runaway signal: once a short option is stuck (>=5% in the money), what
— known that day — told a run that does not come back from an ordinary
pull-back-and-return?

Part A: generic episodes from 10y of daily closes (daily_long.json), so the
signal is not fitted to one rally. Each week a call (put) is "sold" at the
prior close +/- 1 weekly sigma; if a Friday close is >=5% through the strike,
it is stuck. From there it is rolled weekly at the same strike. Came back = a
Friday close back across the strike within 13 weeks. Waiting cost = intrinsic
at the end (0 if it came back) - intrinsic at the trigger, % of strike
(> 0: buying back at the trigger would have been cheaper). Weekly roll credits
are ignored — they favour waiting a little. One chain per symbol at a time.

Part B: Neel's own stuck call chains (cf.json trigger >=5%), same features.
Everything uses closes strictly before the decision day."""
import json, math, sys, bisect
from datetime import date, timedelta
import pandas as pd, numpy as np
W = sys.argv[1]
raw = json.load(open(f'{W}/daily_long.json'))
px = pd.DataFrame({s: pd.Series({r[0]: r[2] for r in rows}) for s, rows in raw.items()})
px.index = pd.to_datetime(px.index); px = px.sort_index()
GAUGES = ['QQQ', 'SPY', 'SMH', '^VIX']
STOCKS = [s for s in px.columns if s not in GAUGES]
ret = np.log(px).diff()
sig = ret.rolling(126, min_periods=60).std() * math.sqrt(252)

from math import erf, sqrt, log
N = lambda x: 0.5 * (1 + erf(x / sqrt(2)))
def time_value(S, k, sgn, v, t=5/252):
    """Black-Scholes time value of a one-week option at the same strike —
    the credit a weekly same-strike roll collects (rates ignored)."""
    if not v or v <= 0: return 0.0
    d1 = (log(S / k) + 0.5 * v * v * t) / (v * sqrt(t)); d2 = d1 - v * sqrt(t)
    p = S * N(d1) - k * N(d2) if sgn > 0 else k * N(-d2) - S * N(-d1)
    return max(p - max(sgn * (S - k), 0), 0.0)

def feats(sym, i, k, typ, i0):
    """Features known at the close of row i (the trigger), for an option with
    strike k sold at row i0 (prior close).  sgn: +1 calls (up is against you),
    -1 puts."""
    s = px[sym]; sgn = 1 if typ == 'call' else -1
    S = s.iloc[i]
    f = {}
    f['depth'] = sgn * (S / k - 1)
    f['move5'] = sgn * (S / s.iloc[i - 5] - 1)                    # the last week
    f['move_sale'] = sgn * (S / s.iloc[i0] - 1)                   # since the sale
    f['pre60'] = sgn * (s.iloc[i0] / s.iloc[max(i0 - 60, 0)] - 1)   # trend into the sale
    f['sig'] = sig[sym].iloc[i]
    f['move5_sig'] = f['move5'] / (f['sig'] * math.sqrt(5 / 252)) if f['sig'] else None
    hist = s.iloc[max(i - 252, 0):i - 4].dropna()
    # calls: above the prior year's high = new ground; puts: below the year's low
    f['vs_extreme'] = sgn * (S / (hist.max() if sgn > 0 else hist.min()) - 1) if len(hist) > 60 else None
    # puts/calls: where the move started relative to the prior year's range
    f['ma200'] = sgn * (S / s.iloc[max(i - 200, 0):i].mean() - 1) if i > 120 else None
    q = px['QQQ']
    f['qqq20'] = sgn * (q.iloc[i] / q.iloc[i - 20] - 1)
    f['qqq5'] = sgn * (q.iloc[i] / q.iloc[i - 5] - 1)
    f['qqq_dd60'] = q.iloc[i0] / q.iloc[max(i0 - 60, 0):i0 + 1].max() - 1   # market drawdown at the sale
    f['qqq_ma200'] = q.iloc[i] / q.iloc[i - 200:i].mean() - 1
    v = px['^VIX']
    f['vix'] = v.iloc[i]; f['vix_chg20'] = v.iloc[i] - v.iloc[i - 20]
    w = (px[STOCKS].iloc[i] / px[STOCKS].iloc[i - 10] - 1).dropna()
    f['breadth'] = float(((sgn * w) > 0.05).mean())                  # share of the universe moving with it
    return f

def generic(typ, z=1.0, trig=0.05, horizon=13, start='2016-01-01'):
    sgn = 1 if typ == 'call' else -1
    idx = px.index
    fridays = [i for i in range(1, len(idx)) if (i + 1 == len(idx) or idx[i + 1].week != idx[i].week)]
    fri_set = sorted(fridays)
    out = []
    for sym in STOCKS:
        s = px[sym]
        busy_until = -1
        for j in range(1, len(fri_set)):
            i0 = fri_set[j - 1]; i1 = fri_set[j]          # sold at last Friday's close, expires this Friday
            if idx[i1] < pd.Timestamp(start) or i0 <= busy_until: continue
            if pd.isna(s.iloc[i0]) or pd.isna(s.iloc[i1]) or pd.isna(sig[sym].iloc[i0]) or i0 < 260: continue
            k = s.iloc[i0] * (1 + sgn * z * sig[sym].iloc[i0] * math.sqrt(5 / 252))
            if sgn * (s.iloc[i1] / k - 1) < trig: continue
            # stuck at i1. Roll weekly at k: back = a later Friday close across k
            later = [f for f in fri_set[j + 1:j + 1 + horizon]]
            if len(later) < horizon: continue                  # not enough future
            end = None
            for f in later:
                if sgn * (s.iloc[f] - k) <= 0: end = f; break
            back = end is not None
            iend = end if back else later[-1]
            # roll credits: a new one-week option at k on each Friday still stuck, from the trigger on
            rolled = [i1] + [f for f in later if f < iend]
            credits = sum(time_value(s.iloc[f], k, sgn, sig[sym].iloc[f]) for f in rolled)
            I0 = max(sgn * (s.iloc[i1] - k), 0); Iend = 0.0 if back else max(sgn * (s.iloc[iend] - k), 0)
            r = dict(sym=sym, typ=typ, date=str(idx[i1].date()), k=k, back=back,
                     weeks=(later.index(iend) + 1), wait_cost=(Iend - I0 - credits) / k, credits=credits / k,
                     wait_better=(Iend - I0 - credits) <= 0)
            r.update(feats(sym, i1, k, typ, i0))
            out.append(r)
            busy_until = iend
    return pd.DataFrame(out)

def table(df, col, edges, label=None):
    d = df.dropna(subset=[col])
    cut = pd.cut(d[col], edges)
    g = d.groupby(cut, observed=True).agg(n=('back', 'size'), runaway=('back', lambda b: 1 - b.mean()), buyback_better=('wait_better', lambda b: 1 - b.mean()),
                                          cost=('wait_cost', 'mean'))
    print(f"  {label or col}"); print(g.to_string(float_format=lambda x: f'{x:6.2f}'))

if __name__ == '__main__':
    for typ in ('call', 'put'):
        df = generic(typ)
        df.to_json(f'{W}/runaway_{typ}.json', orient='records')
        print(f"\n===== {typ}s: {len(df)} stuck episodes, runaway (not back in 13w) {1-df.back.mean():.0%}, buy-back better {1-df.wait_better.mean():.0%}, "
              f"mean waiting cost {df.wait_cost.mean():+.3f} of strike")
        for per, d in (('2016-2020', df[df.date < '2021']), ('2021-2026', df[df.date >= '2021'])):
            print(f"  {per}: n={len(d)} runaway {1-d.back.mean():.0%} cost {d.wait_cost.mean():+.3f}")
        table(df, 'depth', [0.05, 0.08, 0.12, 0.2, 1, 9])
        table(df, 'move5_sig', [-9, 1, 2, 3, 4, 99], 'move in the last week, in weekly sigmas')
        table(df, 'pre60', [-9, -0.2, -0.05, 0.05, 0.2, 0.5, 99], 'trend in the 60 days before the sale')
        table(df, 'vs_extreme', [-9, -0.2, -0.05, 0, 0.1, 99], 'vs prior-year high (calls) / low (puts)')
        table(df, 'ma200', [-9, 0, 0.15, 0.3, 0.6, 99], 'vs 200-day average (direction of the move)')
        table(df, 'qqq20', [-9, -0.03, 0, 0.03, 0.06, 99], 'QQQ 20-day move (direction of the move)')
        table(df, 'qqq_dd60', [-9, -0.15, -0.08, -0.03, 0.01], 'QQQ drawdown from 60-day high at the sale')
        table(df, 'qqq_ma200', [-9, -0.05, 0, 0.05, 0.1, 99], 'QQQ vs its 200-day average')
        table(df, 'vix', [0, 15, 20, 25, 35, 99])
        table(df, 'vix_chg20', [-99, -8, -3, 0, 3, 8, 99], 'VIX change over 20 days')
        table(df, 'breadth', [-0.01, 0.1, 0.25, 0.4, 0.6, 1.01], 'share of universe moved >5% same way in 10 days')
