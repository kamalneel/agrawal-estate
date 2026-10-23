# Wheel review scripts (session 2, 2026-10-23)

Reproduce the numbers in `docs/WHEEL-REVIEW-SESSION-2.md`. Each takes an
output directory; run from `backend/` with the venv:

    OUT=/tmp/wheel && mkdir -p $OUT
    PYTHONPATH=$PWD venv/bin/python scripts/wheel_review/daily.py $OUT        # daily closes (Yahoo) — first
    PYTHONPATH=$PWD venv/bin/python scripts/wheel_review/chains.py $OUT/chains.json
    PYTHONPATH=$PWD venv/bin/python scripts/wheel_review/classify.py $OUT     # new vs roll, prior-close distance
    PYTHONPATH=$PWD venv/bin/python scripts/wheel_review/cf.py $OUT           # buy-back / let-assign (actual fills)
    PYTHONPATH=$PWD venv/bin/python scripts/wheel_review/rollout.py $OUT      # 13-week roll (Black-Scholes estimate)
    PYTHONPATH=$PWD venv/bin/python scripts/wheel_review/report.py $OUT       # splits, put checks, 8-week cap

Prices come only from `daily_prices.py` (daily closes). The DB's weekly bars are
dated Monday but hold Friday's close — using them leaked each week's move into
Monday trades, which produced the withdrawn Finding 1.

- `chains.py` rebuilds every roll chain (first sale → each same-day roll →
  assigned / expired / bought back / open) from `investment_transactions`,
  with the Income page's filter, and scores it against simply holding the
  shares (calls) or not trading (puts). Read-only.
- `cf.py`: at the first roll where the buy-back was ≥3/5/10% of the strike,
  (B) buy back and stop, (A) let it be assigned — exact, from actual fills.
- `rollout.py`: at the first roll ≥5% in the money, roll ~13 weeks out
  instead of one — estimated with Black-Scholes at 26-week realized vol
  (no historical option chains exist).

Known data issue excluded by id: Neel's Retirement AMD 10/5/2026 — three
1-contract STO and BTC rows duplicating a 3-contract trade (ids 31129–31134).
