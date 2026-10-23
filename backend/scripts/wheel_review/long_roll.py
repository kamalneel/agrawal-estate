"""The CBRS rule, applied retroactively: when a stuck option's same-strike
weekly roll pays almost nothing, roll it ~12 weeks out at the same strike
instead, and leave it alone until that expiry.

Trigger (actual fills): a same-strike roll where the leg bought back cost
>=5% of the strike (in the money) and the roll netted <= CREDIT_MAX of the
strike per share. First trigger per chain.

Compared at H = the long option's expiry (or today if it has not expired),
following ONLY the contracts rolled on the trigger day (their "lineage":
each later roll of those legs, pro rata when a day also opens new contracts):
  actual = lineage premium flows from the trigger day to H
           + lineage shares assigned before H, valued at S_H vs the strike
           + lineage legs still open at H, marked with Black-Scholes
  long   = the same buy-back + a WEEKS-week same-strike option sold that
           day - its value at H (intrinsic at expiry; Black-Scholes if H=today)
Calibrated on 23 Oct against live CBRS January puts: realized vol x0.7 (=
the quoted 79% implied) plus the 4% rate reproduces the $3.59 time value on
the $160; realized vol alone gave $10.83. The long option is priced at the stock price implied by the actual buy-back
fill (so both legs see the same intraday price), with the stock's 26-week
realized vol x VOL_MULT. No historical option prices exist: the long leg is
an estimate; the actual side is exact except legs still open at H."""
import json, sys, math, os
from collections import defaultdict
from datetime import date, timedelta
W = sys.argv[1]
CREDIT_MAX = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0025
VOL_MULT = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
WEEKS = int(sys.argv[4]) if len(sys.argv) > 4 else 12
QUIET = len(sys.argv) > 5
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from daily_prices import Daily
DP = Daily(f'{W}/daily.json')
N = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
R_RATE = 0.04   # carry: without it deep puts are overpriced (CBRS Jan $160: $1.25 of the gap)
def bs(S, K, T, v, typ):
    """Black-Scholes with a 4% rate, floored at intrinsic (listed options are American)."""
    intr = max(S - K, 0) if typ == 'call' else max(K - S, 0)
    if T <= 0 or not v or v <= 0: return intr
    d1 = (math.log(S / K) + (R_RATE + 0.5 * v * v) * T) / (v * math.sqrt(T)); d2 = d1 - v * math.sqrt(T)
    df = math.exp(-R_RATE * T)
    p = S * N(d1) - K * df * N(d2) if typ == 'call' else K * df * N(-d2) - S * N(-d1)
    return max(p, intr)
def implied_spot(px, K, T, v, typ):
    """Stock price at which the option was worth what was paid for it."""
    lo, hi = K * 0.2, K * 5
    for _ in range(80):
        m = (lo + hi) / 2; val = bs(m, K, T, v, typ)
        if (val > px) == (typ == 'call'): hi = m
        else: lo = m
    return (lo + hi) / 2
D = date.fromisoformat
TODAY = date(2026, 10, 23)
C = json.load(open(f'{W}/chains.json'))

def lineage_value(c, d0, start_legs, H, S_H, v_H):
    """Follow start_legs {(k, e): q} (opened on d0, premium already counted)
    to H. Returns (flows after d0, assigned value, open mark)."""
    typ = c['type']
    by = defaultdict(list)
    for l in c['legs']:
        if d0 < D(l['d']) <= H: by[l['d']].append(l)
    lin = dict(start_legs); flows = 0.0; assigned = 0.0
    def settle_expired(upto):
        nonlocal assigned
        for (k, e), q in list(lin.items()):
            if q <= 1e-9 or D(e) > upto: continue
            # expired by now without a buy-back: assigned if in the money at expiry
            S_e = DP.on(c['symbol'], D(e))
            if S_e is not None and ((typ == 'put' and S_e < k) or (typ == 'call' and S_e > k)):
                assigned += ((S_H - k) if typ == 'put' else -(S_H - k)) * q * 100
            lin[(k, e)] = 0.0
    for d in sorted(by):
        dd = D(d)
        # legs that expired before this day
        for (k, e), q in list(lin.items()):
            if q > 1e-9 and D(e) < dd: settle_expired(dd - timedelta(days=1)); break
        btcs = [l for l in by[d] if l['t'] == 'BTC']; stos = [l for l in by[d] if l['t'] == 'STO']
        closed = 0.0
        for b in btcs:
            key = (b['k'], b['e']); have = lin.get(key, 0.0)
            if have <= 1e-9: continue
            take = min(have, b['q']); flows += b['amt'] * take / b['q']; lin[key] = have - take; closed += take
        if closed and stos:
            tot = sum(s['q'] for s in stos); f = min(1.0, closed / tot)
            for s in stos:
                flows += s['amt'] * f; key = (s['k'], s['e']); lin[key] = lin.get(key, 0.0) + s['q'] * f
    settle_expired(H)
    open_mark = -sum(bs(S_H, k, (D(e) - H).days / 365, v_H, typ) * q * 100 for (k, e), q in lin.items() if q > 1e-9)
    return flows, assigned, open_mark

rows = []
for c in C:
    typ, sym = c['type'], c['symbol']
    by = defaultdict(list)
    for l in c['legs']: by[l['d']].append(l)
    for d in sorted(by):
        ls = by[d]
        btcs = [l for l in ls if l['t'] == 'BTC']; stos = [l for l in ls if l['t'] == 'STO']
        if not btcs or not stos: continue
        k = btcs[0]['k']
        if any(l['k'] != k for l in btcs + stos): continue          # same-strike rolls only
        q = sum(b['q'] for b in btcs)
        if abs(sum(s['q'] for s in stos) - q) > 1e-9: continue        # same size
        cost_ps = -sum(b['amt'] for b in btcs) / (q * 100)
        net_ps = sum(l['amt'] for l in btcs + stos) / (q * 100)
        if cost_ps < 0.05 * k or net_ps > CREDIT_MAX * k: continue
        dd = D(d); v = DP.vol(sym, dd)
        if not v: break
        v *= VOL_MULT
        t_old = max((D(btcs[0]['e']) - dd).days, 0) / 365
        S = implied_spot(cost_ps, k, t_old, v, typ)
        exp = dd + timedelta(weeks=WEEKS); exp -= timedelta(days=(exp.weekday() - 4) % 7)
        H = min(exp, TODAY); S_H = DP.on(sym, H); v_H = (DP.vol(sym, H) or v / VOL_MULT) * VOL_MULT
        if not S_H: break
        buy = sum(b['amt'] for b in btcs); sell = sum(s['amt'] for s in stos)
        start = defaultdict(float)
        for s in stos: start[(s['k'], s['e'])] += s['q']
        flows, assigned, open_mark = lineage_value(c, dd, start, H, S_H, v_H)
        actual = buy + sell + flows + assigned + open_mark
        long_prem = bs(S, k, (exp - dd).days / 365, v, typ) * q * 100
        long_end = -bs(S_H, k, (exp - H).days / 365, v_H, typ) * q * 100
        long = buy + long_prem + long_end
        rows.append(dict(typ=typ, sym=sym, acct=c['account'], d=d, k=k, q=q, S=round(S, 2),
                         depth=round((S / k - 1) * (1 if typ == 'call' else -1), 3), v=round(v, 2),
                         exp=str(exp), settled=exp <= TODAY, S_H=round(S_H, 2),
                         recovered=(S_H < k) if typ == 'call' else (S_H > k),
                         weekly_net=round(buy + sell), long_net=round(buy + long_prem),
                         actual=round(actual), long=round(long), diff=round(long - actual)))
        break
json.dump(rows, open(f'{W}/long_roll_{CREDIT_MAX}_{VOL_MULT}_{WEEKS}.json', 'w'))
print(f"trigger: same-strike roll, >=5% ITM, netted <= {CREDIT_MAX:.2%} of strike | vol x{VOL_MULT} | {WEEKS} weeks")
for typ in ('put', 'call'):
    R = [r for r in rows if r['typ'] == typ]
    for lab, sel in (('settled', [r for r in R if r['settled']]), ('still running', [r for r in R if not r['settled']])):
        if not sel: continue
        a = sum(r['actual'] for r in sel); l = sum(r['long'] for r in sel)
        print(f"  {typ:4} {lab:13} {len(sel):3} chains | actual {a:>10,} | long roll {l:>10,} | long - actual {l-a:>+10,} | long better in {sum(r['diff'] > 0 for r in sel)}/{len(sel)}")
    s = [r for r in R if r['settled']]
    for lab, sel in (('  stock came back', [r for r in s if r['recovered']]), ('  did not come back', [r for r in s if not r['recovered']])):
        if sel: print(f"      {lab:20} {len(sel):3} | long - actual {sum(r['diff'] for r in sel):>+10,}")
if not QUIET:
    for typ in ('put', 'call'):
        print(typ)
        for r in sorted([r for r in rows if r['typ'] == typ], key=lambda r: r['diff']):
            print(f"  {r['sym']:5} {r['acct'][:15]:15} {r['d']} K{r['k']:>7} q{r['q']:>3.0f} S{r['S']:>8} depth{r['depth']:+.2f} v{r['v']:.2f} -> {r['exp']} S_H{r['S_H']:>8} {'settled' if r['settled'] else 'RUNNING'} "
                  f"weekly {r['weekly_net']:>6} long {r['long_net']:>6} | actual {r['actual']:>8} long {r['long']:>8} diff {r['diff']:>+8}")
