"""Part B: Neel's own stuck chains (cf.json, first buy-back >=5% of strike),
with the same features as the generic test. Episodes = one per symbol and
trigger week (AVGO across three accounts is one event)."""
import json, sys
import pandas as pd
W = sys.argv[1]
sys.argv = [sys.argv[0], W]
import runaway as R
cf = json.load(open(f'{W}/cf.json'))
rows = []
for c in cf:
    t = c['trig'].get('5')
    if not t: continue
    sym = c['symbol']
    if sym not in R.px.columns: continue
    T = pd.Timestamp(t['date'])
    i = R.px.index.searchsorted(T) - 1             # prior close
    i0 = R.px.index.searchsorted(pd.Timestamp(c['start'])) - 1
    f = R.feats(sym, i, t['k'], c['type'], i0)
    rows.append(dict(sym=sym, acct=c['account'], typ=c['type'], start=c['start'], trig=t['date'],
                     rally=('2026-03-01' <= t['date'] <= '2026-05-31'), R=c['R'], B=t['B'],
                     buyback_better=t['B'] > c['R'], open=('open' in c['status']), **f))
df = pd.DataFrame(rows)
df['week'] = pd.to_datetime(df.trig).dt.to_period('W')
ep = df.groupby(['typ', 'sym', 'week']).agg(
    n=('R', 'size'), rally=('rally', 'max'), R=('R', 'sum'), B=('B', 'sum'),
    open=('open', 'max'), **{k: (k, 'first') for k in
    ['trig', 'depth', 'move5_sig', 'move_sale', 'pre60', 'vs_extreme', 'ma200', 'qqq20', 'qqq_dd60', 'qqq_ma200', 'vix', 'vix_chg20', 'breadth']}
).reset_index()
ep['bb_better'] = ep.B > ep.R
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 200)
cols = ['sym', 'trig', 'n', 'R', 'B', 'open', 'depth', 'move5_sig', 'move_sale', 'pre60', 'vs_extreme', 'qqq20', 'qqq_dd60', 'vix', 'vix_chg20', 'breadth']
for typ in ('call', 'put'):
    e = ep[ep.typ == typ].sort_values('trig')
    print(f'\n===== {typ}: {len(e)} episodes ({e.n.sum()} chains)')
    print(e[cols + ['rally']].to_string(index=False, float_format=lambda x: f'{x:7.2f}'))
    print('\n  medians, rally vs other:')
    print(e.groupby('rally')[cols[6:]].median().to_string(float_format=lambda x: f'{x:7.3f}'))
ep.to_json(f'{W}/runaway_own.json', orient='records', date_format='iso', default_handler=str)
