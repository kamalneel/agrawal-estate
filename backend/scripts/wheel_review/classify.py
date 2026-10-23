"""Classify every call sale (STO leg) by what it was — net new vs. roll — and
by its strike's distance from the stock's PRIOR-DAY close (no look-ahead).
Writes chains_daily.json (chains with corrected entry fields)."""
import json, sys, bisect
from collections import defaultdict
from datetime import date, timedelta
W = sys.argv[1]
C = json.load(open(f'{W}/chains.json'))
daily = json.load(open(f'{W}/daily.json'))
DD = {s: ([r[0] for r in rows], rows) for s, rows in daily.items()}
D = date.fromisoformat

def prior_close(sym, d):            # last close strictly before day d
    if sym not in DD: return None
    days, rows = DD[sym]; i = bisect.bisect_left(days, d) - 1
    return rows[i][2] if i >= 0 else None
def close_on(sym, d):               # close on day d, else last before
    if sym not in DD: return None
    days, rows = DD[sym]; i = bisect.bisect_right(days, d) - 1
    return rows[i][2] if i >= 0 else None
def ret(sym, d, weeks):
    a = prior_close(sym, str(D(d) - timedelta(weeks=weeks))); b = prior_close(sym, d)
    return b / a - 1 if a and b else None
def dist(typ, k, s):                # + = out of the money
    return (k / s - 1) if typ == 'call' else (1 - k / s)
def bucket(x):
    if x is None: return 'n/a'
    return 'ITM' if x < 0 else '0-2%' if x < .02 else '2-5%' if x < .05 else '5-10%' if x < .10 else '>10%'

# chain end per (account, symbol, type) for "what came just before"
ends = defaultdict(list)
for c in C:
    last = max([l['d'] for l in c['legs']] + [x['e'] for x in c['assigned'] + c['expired']])
    # how it ended: assigned / bought back in the money / expired or cheap close
    btc_last = [l for l in c['legs'] if l['t'] == 'BTC' and l['d'] == max(x['d'] for x in c['legs'])]
    if c['assigned']:
        how = 'assigned'
    elif btc_last and not any(l['t'] == 'STO' and l['d'] == btc_last[0]['d'] for l in c['legs']):
        q = sum(b['q'] for b in btc_last); ps = -sum(b['amt'] for b in btc_last) / (q * 100)
        s = prior_close(c['symbol'], btc_last[0]['d'])
        itm = s is not None and dist(c['type'], btc_last[0]['k'], s) < 0
        how = 'bought back in the money' if itm else 'bought back cheap'
    else:
        how = 'expired'
    ends[(c['account'], c['symbol'], c['type'])].append((last, how, c))

for c in C:
    typ, sym = c['type'], c['symbol']
    first = next(l for l in c['legs'] if l['t'] == 'STO')
    s0 = prior_close(sym, first['d'])
    c['spot0d'] = s0
    c['otm0d'] = dist(typ, first['k'], s0) if s0 else None
    c['otm0d_sameday'] = dist(typ, first['k'], close_on(sym, first['d'])) if close_on(sym, first['d']) else None
    c['ret4w0d'] = ret(sym, first['d'], 4); c['ret12w0d'] = ret(sym, first['d'], 12)
    # what came just before (within 4 calendar days)
    prev = [(e, how) for (e, how, cc) in ends[(c['account'], sym, typ)]
            if cc is not c and D(first['d']) - timedelta(days=4) <= D(e) <= D(first['d'])]
    if not prev:
        c['entry'] = 'new'
    else:
        hows = {h for _, h in prev}
        c['entry'] = ('new after trouble' if hows & {'assigned', 'bought back in the money'}
                      else 'new, next week')
    # roll legs: distance of each re-sale, and whether the leg bought back was in the money
    c['roll_legs'] = []
    by = defaultdict(list)
    for l in c['legs']: by[l['d']].append(l)
    for d in sorted(by):
        b = [l for l in by[d] if l['t'] == 'BTC']; o = [l for l in by[d] if l['t'] == 'STO']
        if b and o:
            s = prior_close(sym, d)
            if s:
                c['roll_legs'].append(dict(d=d, from_itm=dist(typ, b[0]['k'], s) < 0,
                                           to_dist=dist(typ, o[0]['k'], s)))
    c['got_stuck'] = any(r['from_itm'] for r in c['roll_legs'])
json.dump(C, open(f'{W}/chains_daily.json', 'w'), default=str)

calls = [c for c in C if c['type'] == 'call']
order = ['ITM', '0-2%', '2-5%', '5-10%', '>10%', 'n/a']
print('NEW CALL SALES (chain starts) by strike distance from the prior close')
print(f"{'':6} | {'new':>22} | {'new, next week':>22} | {'new after trouble':>22}")
for b in order:
    cells = []
    for kind in ('new', 'new, next week', 'new after trouble'):
        L = [c for c in calls if c['entry'] == kind and bucket(c['otm0d']) == b]
        cells.append(f"{len(L):3} {sum(c['result'] for c in L):>12,.0f}")
    print(f"{b:6} | {cells[0]:>22} | {cells[1]:>22} | {cells[2]:>22}")
print()
print('Old (weekly bar, look-ahead) vs corrected distance, for chains the old method put within 2%:')
old = [c for c in calls if c['otm0'] is not None and c['otm0'] < .02]
from collections import Counter
print('  ', len(old), 'chains →', Counter(bucket(c['otm0d']) for c in old), ' result', round(sum(c['result'] for c in old)))
print()
print('ROLL LEGS (bought back and resold the same day)')
rl = [(c, r) for c in calls for r in c['roll_legs']]
print(f"  {len(rl)} roll legs; bought back while in the money: {sum(1 for _, r in rl if r['from_itm'])}")
for b in order[:-1]:
    L = [r for _, r in rl if bucket(r['to_dist']) == b]
    st = sum(1 for r in L if r['from_itm'])
    print(f"   resold {b:6}: {len(L):4} legs ({st} of them rolling a call that was in the money)")
print()
print('CHAINS THAT STARTED >=2% OUT: did they get stuck (rolled while in the money)?')
for kind in ('new', 'new, next week', 'new after trouble'):
    L = [c for c in calls if c['entry'] == kind and c['otm0d'] is not None and c['otm0d'] >= .02]
    a = [c for c in L if c['got_stuck']]; b = [c for c in L if not c['got_stuck']]
    print(f"  {kind:18} stuck {len(a):3} {sum(c['result'] for c in a):>11,.0f} | never stuck {len(b):3} {sum(c['result'] for c in b):>10,.0f}")
