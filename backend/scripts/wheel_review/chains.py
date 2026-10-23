"""Rebuild every option roll chain and score it. Output: chains.json"""
import json, sys, bisect, math
from collections import defaultdict
from datetime import date, timedelta
sys.path.insert(0, '/Users/neelpersonal/Coding-Projects/agrawal-estate-planner/backend')
from app.core.database import SessionLocal
from sqlalchemy import text
from app.modules.strategies.technical_signals import _parse_strike, _parse_expiration

db = SessionLocal()
OUT = sys.argv[1]

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from daily_prices import Daily
DP = Daily(os.path.join(os.path.dirname(OUT), 'daily.json'))
hold = {}
for r in db.execute(text("SELECT symbol, max(current_price) p FROM investment_holdings WHERE current_price IS NOT NULL GROUP BY 1")):
    hold[r.symbol] = float(r.p)
price = DP.on              # close on a day (valuation at expiry / chain end)
ret = DP.ret               # move before a day, from the prior close
rvol = DP.vol

rows = db.execute(text("""
    SELECT it.id, it.transaction_date d, it.account_id a, it.symbol s, it.transaction_type ttype,
           it.description, it.quantity q, it.amount amt
    FROM investment_transactions it
    JOIN investment_accounts ia ON it.account_id = ia.account_id AND it.source = ia.source
    WHERE it.transaction_type IN ('STO','BTC','OASGN','OEXP')
      AND (it.description ILIKE '%call%' OR it.description ILIKE '%put%')
      AND it.id NOT IN (31129, 31130, 31131, 31132, 31133, 31134)  -- AMD 10/5 duplicated singles
    ORDER BY it.transaction_date, it.id
""")).fetchall()

# assignments may be MCP-inferred (different source) — add those too
asg_extra = db.execute(text("""
    SELECT DISTINCT ON (account_id, symbol, description) transaction_date d, account_id a, symbol s, description, quantity q
    FROM investment_transactions WHERE transaction_type='OASGN'
    ORDER BY account_id, symbol, description, (source NOT LIKE 'robinhood_mcp_inferred%') DESC, transaction_date
""")).fetchall()

groups = defaultdict(list)
for r in rows:
    typ = 'call' if 'call' in r.description.lower() else 'put'
    k, e = _parse_strike(r.description), _parse_expiration(r.description)
    if k is None or e is None: continue
    groups[(r.a, r.s, typ)].append(dict(d=r.d, t=r.ttype, k=k, e=e, q=float(r.q or 0), amt=float(r.amt or 0)))
assigned = defaultdict(float)   # (a,s,typ,k,e) -> contracts
for r in asg_extra:
    typ = 'call' if 'call' in r.description.lower() else 'put'
    k, e = _parse_strike(r.description), _parse_expiration(r.description)
    if k and e: assigned[(r.a, r.s, typ, k, e)] += float(r.q or 0)

today = date.today()
chains = []
UNMATCHED = []
for (a, s, typ), evs in groups.items():
    open_legs = {}   # (k,e) -> {'q':, 'chain':}
    chain_of = {}
    cur = []
    by_day = defaultdict(list)
    for ev in evs: by_day[ev['d']].append(ev)
    days = sorted(by_day)
    def new_chain(d):
        c = dict(account=a, symbol=s, type=typ, start=d, legs=[], net=0.0, rolls=0,
                 debit_rolls=0, debit_paid=0.0, end=None, end_type=None, strikes=[])
        chains.append(c); return c
    def close_expired(upto):
        for key in list(open_legs):
            k, e = key
            if e < upto:
                L = open_legs.pop(key)
                q_asg = assigned.get((a, s, typ, k, e), 0)
                c = L['chain']
                if q_asg > 0:
                    c['assigned'].append(dict(k=k, e=e, q=min(q_asg, L['q'])))
                    if L['q'] > q_asg:
                        c['expired'].append(dict(k=k, e=e, q=L['q'] - q_asg))
                else:
                    c['expired'].append(dict(k=k, e=e, q=L['q']))
                c['last'] = max(c.get('last', e), e)
    for d in days:
        close_expired(d)
        evs_d = by_day[d]
        btcs = [x for x in evs_d if x['t'] == 'BTC']
        stos = [x for x in evs_d if x['t'] == 'STO']
        closed_chains = []
        def take_btc(b):
            key = (b['k'], b['e'])
            L = open_legs.get(key)
            if not L or L['q'] <= 1e-6:
                return False
            c = L['chain']; c['net'] += b['amt']
            c['legs'].append(dict(d=d, t='BTC', k=b['k'], e=b['e'], q=b['q'], amt=b['amt']))
            L['q'] -= b['q']
            if L['q'] <= 1e-6: open_legs.pop(key)
            closed_chains.append((c, b))
            return True
        # pass 1: buy-backs of legs opened on an earlier day (the roll's close)
        later = [b for b in btcs if not take_btc(b)]
        target = closed_chains[0][0] if closed_chains else None
        roll_debit = sum(b['amt'] for _, b in closed_chains)
        roll_credit = 0.0
        for o in stos:
            key = (o['k'], o['e'])
            if key in open_legs:
                c = open_legs[key]['chain']
            else:
                c = target or new_chain(d)
                if not target: target = c
            open_legs.setdefault(key, dict(q=0, chain=c))['q'] += o['q']
            c['net'] += o['amt']; c['legs'].append(dict(d=d, t='STO', k=o['k'], e=o['e'], q=o['q'], amt=o['amt']))
            c['strikes'].append(o['k'])
            roll_credit += o['amt']
        is_roll = bool(closed_chains) and bool(stos)
        # pass 2: buy-backs of legs opened today (same-day open and close)
        for b in later:
            if not take_btc(b):
                UNMATCHED.append(dict(a=a, s=s, typ=typ, d=str(d), k=b['k'], e=str(b['e']), q=b['q'], amt=b['amt']))
        if is_roll:
            target['rolls'] += 1
            if roll_credit + roll_debit < 0:
                target['debit_rolls'] += 1; target['debit_paid'] += roll_credit + roll_debit
        for c in chains:
            c.setdefault('assigned', []); c.setdefault('expired', [])
    close_expired(today + timedelta(days=1)) if False else None
    for key, L in open_legs.items():
        L['chain'].setdefault('open', []).append(dict(k=key[0], e=key[1], q=L['q']))

# score
out = []
for c in chains:
    c.setdefault('assigned', []); c.setdefault('expired', []); c.setdefault('open', [])
    if not c['legs']: continue
    sym, typ = c['symbol'], c['type']
    first = next(l for l in c['legs'] if l['t'] == 'STO')
    s0 = DP.before(sym, first['d'])   # prior close: known before the sale
    c['first_strike'], c['first_exp'] = first['k'], str(first['e'])
    c['spot0'] = s0
    c['otm0'] = ((first['k'] / s0 - 1) if typ == 'call' else (1 - first['k'] / s0)) if s0 else None
    c['ret4w0'] = ret(sym, first['d'], 4)
    c['ret12w0'] = ret(sym, first['d'], 12)
    c['vol0'] = rvol(sym, first['d'])
    ks = c['strikes']
    c['rolled_toward'] = any((ks[i] < ks[i-1]) if typ == 'call' else (ks[i] > ks[i-1]) for i in range(1, len(ks)))
    c['rolled_away'] = any((ks[i] > ks[i-1]) if typ == 'call' else (ks[i] < ks[i-1]) for i in range(1, len(ks)))
    weeks = (max([l['d'] for l in c['legs']]) - c['start']).days / 7
    c['weeks'] = round(weeks, 1)
    # outcome
    give = 0.0; asg_detail = []
    for x in c['assigned']:
        sp = price(sym, x['e'])
        if sp is None: continue
        g = (max(sp - x['k'], 0) if typ == 'call' else max(x['k'] - sp, 0)) * x['q'] * 100
        give += g; asg_detail.append(dict(k=x['k'], e=str(x['e']), q=x['q'], spot=sp, give=round(g)))
    c['assign_cost'] = round(give, 2)
    c['assign_detail'] = asg_detail
    # open legs: intrinsic now (not cost to close — info only)
    now = hold.get(sym) or DP.on(sym, today)
    c['open_intrinsic'] = round(sum((max(now - o['k'], 0) if typ == 'call' else max(o['k'] - now, 0)) * o['q'] * 100 for o in c['open']), 2) if now else None
    c['result'] = round(c['net'] - give, 2)
    c['status'] = 'open' if c['open'] else ('assigned' if c['assigned'] else 'closed/expired')
    c['start'] = str(c['start'])
    for l in c['legs']: l['d'] = str(l['d']); l['e'] = str(l['e'])
    for k in ('assigned', 'expired', 'open'):
        for x in c[k]: x['e'] = str(x['e'])
    out.append(c)
json.dump(out, open(OUT, 'w'), default=str, indent=0)
json.dump(UNMATCHED, open(OUT.replace('.json','_unmatched.json'),'w'), default=str)
calls = [c for c in out if c['type'] == 'call']; puts = [c for c in out if c['type'] == 'put']
print('chains', len(out), 'calls', len(calls), 'puts', len(puts))
for t, L in (('call', calls), ('put', puts)):
    print(t, 'net prem', round(sum(c['net'] for c in L)), 'assign cost', round(sum(c['assign_cost'] for c in L)), 'result', round(sum(c['result'] for c in L)))
