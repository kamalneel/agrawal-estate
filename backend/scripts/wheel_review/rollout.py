"""Estimate: at the first roll where a call/put is >=5% in the money, roll
out ~13 weeks (same strike, or up/down to the strike that nets zero) instead
of one week, then do nothing until that expiry. Black-Scholes at the stock's
26-week realized vol — no historical option chains exist, so this is an
estimate, unlike the buy-back test (actual fills)."""
import json, sys, bisect, math
from collections import defaultdict
from datetime import date, timedelta
sys.path.insert(0, '/Users/neelpersonal/Coding-Projects/agrawal-estate-planner/backend')
from app.core.database import SessionLocal
from sqlalchemy import text
db = SessionLocal(); W = sys.argv[1]
C = json.load(open(f'{W}/chains.json'))
px = defaultdict(list)
for r in db.execute(text("SELECT symbol, price_date, close_price FROM symbol_price_history ORDER BY 1, 2")):
    px[r.symbol].append((r.price_date, float(r.close_price)))
def price(sym, d):
    s = px.get(sym); i = bisect.bisect_right([x[0] for x in s], d) - 1 if s else -1
    return s[i][1] if i >= 0 else None
def rvol(sym, d):
    s = [(x, p) for (x, p) in px.get(sym, []) if d - timedelta(weeks=26) <= x <= d]
    if len(s) < 8: return None
    r = [math.log(s[i][1] / s[i-1][1]) / math.sqrt(max((s[i][0] - s[i-1][0]).days, 1) / 365) for i in range(1, len(s))]
    m = sum(r) / len(r); return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))
N = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
def bs(S, K, T, v, typ):
    if T <= 0 or v <= 0: return max(S - K, 0) if typ == 'call' else max(K - S, 0)
    d1 = (math.log(S / K) + 0.5 * v * v * T) / (v * math.sqrt(T)); d2 = d1 - v * math.sqrt(T)
    c = S * N(d1) - K * N(d2)
    return c if typ == 'call' else c - S + K
D = date.fromisoformat
today = date.today()
out = defaultdict(lambda: [0, 0.0, 0.0, 0.0])
detail = []
for c in C:
    typ, sym = c['type'], c['symbol']
    by = defaultdict(list)
    for l in c['legs']: by[l['d']].append(l)
    cum = 0.0
    for d in sorted(by):
        ls = by[d]; btcs = [l for l in ls if l['t'] == 'BTC']
        if btcs:
            q = sum(b['q'] for b in btcs); k = btcs[0]['k']
            cost_ps = -sum(b['amt'] for b in btcs) / (q * 100)
            if cost_ps >= 0.05 * k:
                dd = D(d); S = price(sym, dd); v = rvol(sym, dd)
                if not S or not v: break
                T = 13 * 7 / 365; exp = dd + timedelta(weeks=13)
                buy = sum(b['amt'] for b in btcs)  # actual buy-back (negative)
                # same strike, 13 weeks
                same = bs(S, k, T, v, typ) * q * 100
                # strike that nets zero against the buy-back, 13 weeks out
                lo, hi = (k, S * 2) if typ == 'call' else (S * 0.3, k)
                for _ in range(60):
                    mid = (lo + hi) / 2
                    val = bs(S, mid, T, v, typ) * q * 100
                    if (val + buy >= 0) == (typ == 'call'): lo = mid
                    else: hi = mid
                k2 = lo if typ == 'call' else hi
                end = min(exp, today); S_end = price(sym, end) or S
                def outcome(K):
                    return -(max(S_end - K, 0) if typ == 'call' else max(K - S_end, 0)) * q * 100
                r_same = cum + buy + same + outcome(k)
                r_up = cum + buy + bs(S, k2, T, v, typ) * q * 100 + outcome(k2)
                a = out[typ]; a[0] += 1; a[1] += c['result']; a[2] += r_same; a[3] += r_up
                detail.append(dict(sym=sym, acct=c['account'], d=d, k=k, k2=round(k2, 1), S=S, v=round(v, 2),
                                   actual=round(c['result']), same=round(r_same), up=round(r_up),
                                   horizon=str(end), open_at_today=exp > today))
                break
        cum += sum(l['amt'] for l in ls)
for typ, (n, a, s, u) in out.items():
    print(f"{typ}: {n} chains reached 5% ITM | actual {a:,.0f} | roll 13wk same strike {s:,.0f} ({s-a:+,.0f}) | roll 13wk to the zero-cost strike {u:,.0f} ({u-a:+,.0f})")
json.dump(detail, open(f'{W}/rollout.json', 'w'))
for x in sorted(detail, key=lambda x: x['actual'])[:10]:
    print(f"  {x['sym']:5} {x['acct'][:14]:14} {x['d']} K {x['k']} → zero-cost K {x['k2']} vol {x['v']} | actual {x['actual']:>8,} same {x['same']:>8,} up {x['up']:>8,} {'(still open today)' if x['open_at_today'] else ''}")
