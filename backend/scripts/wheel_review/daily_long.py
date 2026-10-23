"""10 years of daily closes for the review's symbols plus market gauges
(QQQ, SPY, SMH, ^VIX) -> daily_long.json, same shape as daily.json.
Used only for the generic (out-of-sample) runaway test."""
import json, sys, time, urllib.request
from datetime import datetime, timezone
W = sys.argv[1]
syms = sorted(json.load(open(f'{W}/daily.json'))) + ['QQQ', 'SPY', 'SMH', '^VIX']
out, missing = {}, []
p1 = int(datetime(2015, 1, 1, tzinfo=timezone.utc).timestamp()); p2 = int(time.time())
for s in syms:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{s.replace('^','%5E')}?interval=1d&period1={p1}&period2={p2}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=30))['chart']['result'][0]
        q = d['indicators']['quote'][0]
        tz = d['meta'].get('gmtoffset', -14400)
        rows = []
        for t, o, c in zip(d['timestamp'], q['open'], q['close']):
            if c is None: continue
            rows.append([datetime.fromtimestamp(t + tz, tz=timezone.utc).strftime('%Y-%m-%d'), o, c])
        out[s] = rows
    except Exception as e:
        missing.append((s, str(e)[:60]))
    time.sleep(0.3)
json.dump(out, open(f'{W}/daily_long.json', 'w'))
print('fetched', len(out), 'missing', missing)
for s, r in out.items(): print(s, r[0][0], len(r))
