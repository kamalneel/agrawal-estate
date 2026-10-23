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

    # Finding 5 — the runaway signal (after cf.py)
    venv/bin/python scripts/wheel_review/daily_long.py $OUT          # 10y daily closes + QQQ/SPY/SMH/^VIX
    venv/bin/python scripts/wheel_review/runaway.py $OUT             # generic stuck-option episodes, feature buckets
    venv/bin/python scripts/wheel_review/runaway2.py $OUT            # the relief-rally signal; put mirror; young listings
    venv/bin/python scripts/wheel_review/runaway_own.py $OUT         # Neel's stuck chains, same features
    venv/bin/python scripts/wheel_review/runaway_own_rolls.py $OUT   # signal checked at every stuck roll; buy-back at the fill

    # Finding 6 — the long roll for deep options (args: credit max, vol multiple, weeks)
    venv/bin/python scripts/wheel_review/long_roll.py $OUT 0.0025 0.8 12
    venv/bin/python scripts/wheel_review/soxl.py $OUT -0.35 0.9          # SOXL crashes: weekly vs long roll
    venv/bin/python scripts/wheel_review/soxl145.py $OUT                  # SOXL back to $145 (+74%): history, 2026, SMH

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

- `runaway.py`: ten years, 31 symbols. Each week a call (put) is sold one
  weekly standard deviation out; ≥5% in the money by Friday = stuck; rolled
  weekly at the same strike (Black-Scholes time value credited) until a Friday
  close is back across the strike, or 13 weeks. The universe is today's
  holdings, which are survivors, so compare buckets, not levels.

Known data issue excluded by id: Neel's Retirement AMD 10/5/2026 — three
1-contract STO and BTC rows duplicating a 3-contract trade (ids 31129–31134).
