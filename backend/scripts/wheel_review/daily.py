"""Daily closes from Yahoo for every symbol with an option chain → daily.json
{symbol: [[YYYY-MM-DD, open, close], ...]}  Run first."""
import json, sys, time, urllib.request
from datetime import datetime, timezone
W = sys.argv[1]
sys.path.insert(0, '/Users/neelpersonal/Coding-Projects/agrawal-estate-planner/backend')
from app.core.database import SessionLocal
from sqlalchemy import text
syms = sorted(r[0] for r in SessionLocal().execute(text(
    "SELECT DISTINCT symbol FROM investment_transactions WHERE transaction_type IN ('STO','BTC','OASGN')")) if r[0])
out, missing = {}, []
p1 = int(datetime(2024, 9, 1, tzinfo=timezone.utc).timestamp()); p2 = int(time.time())
for s in syms:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?interval=1d&period1={p1}&period2={p2}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=20))['chart']['result'][0]
        q = d['indicators']['quote'][0]
        tz = d['meta'].get('gmtoffset', -14400)
        rows = []
        for t, o, c in zip(d['timestamp'], q['open'], q['close']):
            if c is None: continue
            day = datetime.fromtimestamp(t + tz, tz=timezone.utc).strftime('%Y-%m-%d')
            rows.append([day, o, c])
        out[s] = rows
    except Exception as e:
        missing.append((s, str(e)[:60]))
    time.sleep(0.3)
json.dump(out, open(f'{W}/daily.json', 'w'))
print('symbols', len(syms), 'fetched', len(out), 'missing', missing)
print('NVDA sample', [r for r in out.get('NVDA', []) if '2026-03-26' <= r[0] <= '2026-04-02'])
