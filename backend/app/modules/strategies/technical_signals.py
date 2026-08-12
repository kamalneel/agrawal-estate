"""
Real technical signals for the V6 action queue — replaces text-only
"check RSI yourself" hints with actually-computed numbers.

Built 2026-07-21 after Neel identified two behaviors the engine described
but never verified:
  1. He avoids selling calls into a stock that's declined several days
     running, expecting mean reversion (e.g. TSLA $415→$380) — but the
     engine's "Entry timing: sell now if RSI>60..." text was never
     computed, just printed.
  2. He rolls deep-ITM puts (SOXL, CBRS, INTC, SPCX) forward at an
     unchanged strike for credit, betting the dip is cyclical — but the
     engine's own caveat ("runaway would mean evaluate closing") had no
     mechanism to tell cyclical from runaway.

Deliberately sourced ONLY from already-synced data (investment_holdings_
history for daily prices, investment_transactions for roll history) — no
Yahoo/Schwab revival (see docs/INVESTMENTS-PAGE-SPEC.md market-data-source
rule). This means signals are only as available as the sync's own
history; both functions report unavailability honestly rather than
estimate from thin data.
"""

import re
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import text as _text
from sqlalchemy.orm import Session

_STRIKE_RE = re.compile(r"\$([\d,]+\.?\d*)\s*$")


def compute_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    """Wilder's RSI. None if there isn't enough history."""
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _daily_closes(db: Session, account_id: str, symbol: str, lookback_days: int) -> tuple[List[float], str]:
    """Daily price series derived from held-share snapshots (market_value /
    quantity) when the account actually owns the stock — real for every
    Engine-1 candidate by construction (Engine 1 only fires on symbols with
    >=100 shares actually held). Falls back to symbol_price_history (weekly
    bars, symbol-level — not tied to any one account's holdings) for a
    symbol written as an option against cash rather than owned shares, e.g.
    a cash-secured put with zero underlying position in that account
    (2026-07-29: AMD in Neel's Brokerage had 0 holdings-history rows, so its
    RSI silently never appeared until this fallback). Returns (closes,
    source) — source is 'daily' or 'weekly' so callers can label which."""
    rows = db.execute(_text("""
        SELECT market_value / NULLIF(quantity, 0) AS px
        FROM investment_holdings_history
        WHERE account_id = :acct AND symbol = :sym AND quantity > 0
          AND market_value IS NOT NULL AND snapshot_date >= :cutoff
        ORDER BY snapshot_date
    """), {"acct": account_id, "sym": symbol,
           "cutoff": date.today() - timedelta(days=lookback_days)}).fetchall()
    closes = [float(r.px) for r in rows if r.px]
    if closes:
        return closes, "daily"

    rows = db.execute(_text("""
        SELECT close_price FROM symbol_price_history
        WHERE symbol = :sym ORDER BY price_date DESC LIMIT 30
    """), {"sym": symbol}).fetchall()
    return [float(r.close_price) for r in reversed(rows)], "weekly"


_RECOVERY_CONFIRM_PCT = 3.0   # a single day must gain at least this much to count
_RECOVERY_CONFIRM_DAYS = 2    # this many such days (not necessarily consecutive-only) clear it


def _decline_with_hysteresis(closes: List[float]) -> Dict:
    """Sticky 'declining' state walked forward across the whole closes
    series: triggers on 3+ consecutive down days AND >=5% cumulative drop
    over the trailing window (same signal as before) — but once triggered,
    stays declining until _RECOVERY_CONFIRM_DAYS individual days each gain
    >= _RECOVERY_CONFIRM_PCT%. A single big bounce only counts once; small
    day-to-day noise doesn't accumulate.

    Added 2026-07-30 after backtesting the plain 'any up day clears it'
    version against INTC/AVGO/SPCX: INTC bounced +8.6% on 2026-07-21 (which
    would have cleared the flag under a 2-any-up-days rule) then fell
    another ~22% over the next six sessions — a false recovery. This
    version stayed correctly 'declining' through that whole stretch because
    07-20's own move (+2.1%) was too small to count, so only one
    confirming day had accrued when the drop resumed. Recomputed fresh
    from source data every call — no persisted state — so a symbol's
    trigger point is only visible within the lookback window passed in.
    """
    n = len(closes)
    in_decline = False
    confirm_count = 0
    trigger_change_pct: Optional[float] = None
    for i in range(1, n):
        window = min(5, i)
        chg = (closes[i] - closes[i - window]) / closes[i - window] * 100 if closes[i - window] else 0.0
        down_days = 0
        j = i
        while j > 0 and closes[j] < closes[j - 1]:
            down_days += 1
            j -= 1
        fresh_trigger = down_days >= 3 and chg <= -5.0
        day_ret = (closes[i] - closes[i - 1]) / closes[i - 1] * 100 if closes[i - 1] else 0.0

        if fresh_trigger and not in_decline:
            in_decline = True
            confirm_count = 0
            trigger_change_pct = chg
        if in_decline:
            confirm_count = confirm_count + 1 if day_ret >= _RECOVERY_CONFIRM_PCT else 0
            if confirm_count >= _RECOVERY_CONFIRM_DAYS:
                in_decline = False
                confirm_count = 0
                trigger_change_pct = None

    return {
        "declining": in_decline,
        "confirm_progress": confirm_count,
        "trigger_change_pct": round(trigger_change_pct, 1) if trigger_change_pct is not None else None,
    }


def get_entry_timing(db: Session, account_id: str, symbol: str,
                     lookback_days: int = 45, min_history: int = 15) -> Dict:
    """RSI-14 + consecutive-down-day check for covered-call entry timing.

    Returns {'available': False, 'reason': ...} when history is too thin
    (e.g. a position assigned <2 weeks ago) — callers must fail OPEN
    (fall back to today's static text) rather than block a trade on a
    data gap.
    """
    closes, price_source = _daily_closes(db, account_id, symbol, lookback_days)
    if len(closes) < min_history:
        return {"available": False, "reason": f"only {len(closes)} price points on file (need {min_history}+)"}

    rsi = compute_rsi(closes)
    unit = "session" if price_source == "daily" else "week"

    down_periods = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] < closes[i - 1]:
            down_periods += 1
        else:
            break

    window = min(5, len(closes) - 1)
    change_pct = ((closes[-1] - closes[-1 - window]) / closes[-1 - window] * 100
                  if window > 0 and closes[-1 - window] else 0.0)

    oversold = rsi is not None and rsi < 40
    decline_state = _decline_with_hysteresis(closes)
    declining = decline_state["declining"]

    reasons = []
    if oversold:
        reasons.append(f"RSI {rsi:.0f} (oversold)" + (" — weekly bars, no owned-share price history" if price_source == "weekly" else ""))
    if declining:
        if decline_state["confirm_progress"] > 0:
            remaining = _RECOVERY_CONFIRM_DAYS - decline_state["confirm_progress"]
            reasons.append(f"recovering from a {decline_state['trigger_change_pct']:+.1f}% decline — "
                            f"{remaining} more {_RECOVERY_CONFIRM_PCT:.0f}%+ {unit} needed to clear")
        else:
            reasons.append(f"declining ({decline_state['trigger_change_pct']:+.1f}% drop that triggered it) — "
                            f"needs {_RECOVERY_CONFIRM_DAYS} {_RECOVERY_CONFIRM_PCT:.0f}%+ {unit}s to clear, none yet")

    return {
        "available": True,
        "rsi": round(rsi, 1) if rsi is not None else None,
        "price_source": price_source,
        "consecutive_down_days": down_periods,
        "change_pct": round(change_pct, 1),
        "wait": oversold or declining,
        "reason": " and ".join(reasons) if reasons else None,
    }


def _parse_strike(description: Optional[str]) -> Optional[float]:
    if not description:
        return None
    m = _STRIKE_RE.search(description.strip())
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _roll_events(db: Session, account_id: str, symbol: str, option_type: str) -> List[Dict]:
    """Same-day BTC+STO pairs for this position, newest first. Handles
    multiple distinct strikes rolling the same day (e.g. SOXL $195 and
    $200 both rolled 7/21) via greedy nearest-strike pairing."""
    label = option_type.capitalize()  # 'Put' or 'Call' — matches description text
    rows = db.execute(_text("""
        SELECT transaction_date, transaction_type, description
        FROM investment_transactions
        WHERE account_id = :acct AND symbol = :sym
          AND transaction_type IN ('STO', 'BTC') AND description ILIKE :label
        ORDER BY transaction_date
    """), {"acct": account_id, "sym": symbol, "label": f"%{label}%"}).fetchall()

    by_date: Dict[date, Dict[str, List[float]]] = {}
    for r in rows:
        strike = _parse_strike(r.description)
        if strike is None:
            continue
        d = by_date.setdefault(r.transaction_date, {"BTC": [], "STO": []})
        d[r.transaction_type].append(strike)

    events = []
    for d in sorted(by_date.keys()):
        btcs, stos = sorted(by_date[d]["BTC"]), sorted(by_date[d]["STO"])
        used = [False] * len(stos)
        for b in btcs:
            best_i, best_diff = None, None
            for i, s in enumerate(stos):
                if used[i]:
                    continue
                diff = abs(s - b)
                if best_diff is None or diff < best_diff:
                    best_i, best_diff = i, diff
            if best_i is not None:
                used[best_i] = True
                events.append({"date": d, "from_strike": b, "to_strike": stos[best_i]})
    events.sort(key=lambda e: e["date"], reverse=True)
    return events


def _roll_chain_premium(db: Session, account_id: str, symbol: str, option_type: str,
                        final_description: str, final_open_date: date,
                        final_amount: float) -> Dict:
    """True net premium across the WHOLE weekly roll chain that fed into
    one specific contract -- not just that one contract's own STO.

    Neel, 2026-08-12, on an assignment-loss row reading "$9,005 premium
    collected": that figure was literally one STO transaction -- the exact
    contract that happened to be open at assignment -- with nothing summed.
    What he actually wanted: "since the first time I've sold this put and
    been rolling it week over week, what is the total premium collected."
    Gross-summing every STO in the chain overstates it though (it ignores
    what was paid to close each prior leg before rolling) -- so this sums
    STO opens MINUS BTC closes across the whole chain, which is what was
    actually pocketed in cash over the life of the position.

    Walks backward one roll at a time: the BTC on the day this leg opened
    (same account/symbol/type) is what funded it. Nearest-strike matching
    on that day handles parallel chains at other strikes rolling the same
    day (e.g. SPCX ran a $200 and a $162.50 put chain concurrently) without
    crossing them. Stops the moment a leg's open date has no same-day BTC
    -- that STO was the chain's true first sale, not a roll continuation
    (clean stop, `incomplete=False`). Capped at 104 hops (~2 years of
    weeklies) so a data anomaly can't loop.

    `incomplete=True` (Neel, 2026-08-12, verifying a Neel's Brokerage SPCX
    chain that stopped at 3 weeks): a BTC WAS found — proving an earlier
    leg really was rolled into this one — but that earlier leg's own STO
    is missing from the ledger (this account's history has a real gap
    around 2026-07-10: a BTC closes "SPCX 7/17 Put $200" on 7/15, but no
    STO ever opened it). That's different from a clean chain start: there
    IS more history, it just can't be priced, so the total is a real but
    partial floor, not the whole chain — surfaced honestly rather than
    silently presented as complete."""
    label = option_type.capitalize()
    total = final_amount
    weeks = 1
    incomplete = False
    cur_desc, cur_date = final_description, final_open_date
    cur_strike = _parse_strike(final_description)
    seen = {cur_desc}
    for _ in range(104):
        btc_rows = db.execute(_text("""
            SELECT description, amount FROM investment_transactions
            WHERE account_id = :acct AND symbol = :sym AND transaction_type = 'BTC'
              AND transaction_date = :d AND description ILIKE :label
        """), {"acct": account_id, "sym": symbol, "d": cur_date, "label": f"%{label}%"}).fetchall()
        if not btc_rows:
            break  # clean chain start -- no evidence of an earlier leg
        best = min(btc_rows, key=lambda r: abs((_parse_strike(r.description) or 1e9) - (cur_strike or 0)))
        if best.description in seen:
            break  # guard against a malformed/cyclical match
        sto_row = db.execute(_text("""
            SELECT transaction_date, amount FROM investment_transactions
            WHERE account_id = :acct AND symbol = :sym AND description = :desc
              AND transaction_type = 'STO' ORDER BY transaction_date DESC LIMIT 1
        """), {"acct": account_id, "sym": symbol, "desc": best.description}).fetchone()
        if not sto_row:
            incomplete = True  # a prior leg existed (this BTC closed it) but its open is missing
            break
        total += float(best.amount) + float(sto_row.amount)
        seen.add(best.description)
        weeks += 1
        cur_desc, cur_date = best.description, sto_row.transaction_date
        cur_strike = _parse_strike(best.description)
    return {"net_premium": round(total, 2), "chain_weeks": weeks, "incomplete": incomplete}


def _price_near(db: Session, account_id: str, symbol: str, target: date):
    """Real price near a date: whichever of two real sources lands
    CLOSER to the target date wins — daily (held-share history, only
    exists on days the account actually held nonzero shares) or
    symbol-level close (symbol_price_history, always available
    regardless of holdings). Unconditionally preferring 'daily' used to
    pick a 5-day-stale account-specific price over a same-day
    symbol-level close (Neel, 2026-08-12: two accounts assigned the same
    SPCX put chain on the same day showed different assignment prices —
    $125.89 vs $133.29 — because one account's shares had been called
    away days earlier by an unrelated covered call, leaving no 'daily'
    price point anywhere near the assignment date in that account, so
    the old logic fell back 5 days instead of to the closer, same-day
    symbol_price_history close). Never fabricated — returns None if
    nothing is within tolerance on either source."""
    daily = db.execute(_text("""
        SELECT snapshot_date, market_value / NULLIF(quantity, 0) AS px
        FROM investment_holdings_history
        WHERE account_id = :acct AND symbol = :sym AND quantity > 0
          AND market_value IS NOT NULL
          AND snapshot_date BETWEEN :d - INTERVAL '5 days' AND :d + INTERVAL '5 days'
        ORDER BY ABS(snapshot_date - :d) ASC LIMIT 1
    """), {"acct": account_id, "sym": symbol, "d": target}).fetchone()
    weekly = db.execute(_text("""
        SELECT price_date, close_price
        FROM symbol_price_history
        WHERE symbol = :sym
          AND price_date BETWEEN :d - INTERVAL '10 days' AND :d + INTERVAL '10 days'
        ORDER BY ABS(price_date - :d) ASC LIMIT 1
    """), {"sym": symbol, "d": target}).fetchone()

    candidates = []
    if daily and daily.px:
        candidates.append((abs((daily.snapshot_date - target).days), float(daily.px), "daily"))
    if weekly and weekly.close_price:
        candidates.append((abs((weekly.price_date - target).days), float(weekly.close_price), "weekly"))
    if not candidates:
        return None, None
    candidates.sort(key=lambda c: c[0])  # closer wins; ties keep 'daily' (added first, stable sort)
    return candidates[0][1], candidates[0][2]


def _cost_basis_near(db: Session, account_id: str, symbol: str, target: date):
    """Average cost per share near a date, for a CALL assignment's
    'vs. cost basis' figure (Neel, 2026-08-08 — a put assignment has no
    prior cost basis to compare against; it CREATES a lot at the strike,
    so this is only ever called for calls).

    Two sources, preferred in order:
      1. 'live' — Robinhood's own average_buy_price, captured every sync
         since 2026-08-08 into investment_cost_basis_history (average-cost
         accounting, already adjusted for partial sells — authoritative,
         not reconstructed).
      2. 'reconstructed' — weighted average of every BUY transaction for
         this account+symbol up to `target`, for assignments that
         predate live capture. Deliberately NOT FIFO/lot-order (Neel,
         2026-08-08: "I'm not using this for tax calculation... this is
         to truly calculate if I lost money"): in average-cost accounting
         a partial sale doesn't change the remaining shares' average
         cost, so summing every buy through the target date is the
         correct running average regardless of any assignments/sales
         that happened in between — no lot-matching needed.
    Returns (avg_cost_per_share, source, incomplete) — incomplete=True
    when the reconstructed share count falls short of `shares_involved`
    (a real gap in transaction history, e.g. a pre-backfill boundary;
    surfaced honestly rather than silently trusted)."""
    row = db.execute(_text("""
        SELECT avg_cost_per_share FROM investment_cost_basis_history
        WHERE account_id = :acct AND symbol = :sym
          AND snapshot_date BETWEEN :d - INTERVAL '5 days' AND :d + INTERVAL '5 days'
        ORDER BY ABS(snapshot_date - :d) ASC LIMIT 1
    """), {"acct": account_id, "sym": symbol, "d": target}).fetchone()
    if row and row.avg_cost_per_share:
        return float(row.avg_cost_per_share), "live", False
    return None, None, None


def _reconstruct_cost_basis(db: Session, account_id: str, symbol: str,
                            before: date, shares_involved: float):
    """Weighted average of every BUY transaction for this account+symbol
    on or before `before` — see _cost_basis_near for why this is a plain
    average, not FIFO. Returns (avg_cost_per_share, incomplete)."""
    rows = db.execute(_text("""
        SELECT quantity, amount FROM investment_transactions
        WHERE account_id = :acct AND symbol = :sym AND transaction_type = 'BUY'
          AND transaction_date <= :d
    """), {"acct": account_id, "sym": symbol, "d": before}).fetchall()
    total_shares = sum(float(r.quantity) for r in rows)
    total_cost = sum(-float(r.amount) for r in rows)  # BUY amounts are negative
    if total_shares <= 0:
        return None, True
    return total_cost / total_shares, total_shares < shares_involved - 0.01


def get_roll_streak(db: Session, account_id: str, symbol: str, option_type: str,
                    current_strike: float, current_itm_pct: float) -> Optional[Dict]:
    """Consecutive-week roll streak ending at the live position, and
    whether ITM depth is worsening vs. the streak's first roll — the
    cyclical-vs-runaway signal Neel asked for, 2026-07-21."""
    events = _roll_events(db, account_id, symbol, option_type)
    if not events:
        return None
    # sanity: the most recent roll should match the live position; if not,
    # the transaction history doesn't line up with this card (stale sync,
    # account mismatch) — don't guess.
    if abs(events[0]["to_strike"] - current_strike) > max(current_strike * 0.1, 1.0):
        return None

    chain = [events[0]]
    for ev in events[1:]:
        prev = chain[-1]
        gap_days = (prev["date"] - ev["date"]).days
        strike_cont = abs(ev["to_strike"] - prev["from_strike"]) <= max(prev["from_strike"] * 0.1, 1.0)
        if 4 <= gap_days <= 10 and strike_cont:
            chain.append(ev)
        else:
            break

    weeks = len(chain)
    if weeks < 2:
        return {"weeks_rolled": weeks, "trend": None}

    first = chain[-1]
    start_price, source = _price_near(db, account_id, symbol, first["date"])
    if start_price is None:
        return {"weeks_rolled": weeks, "trend": None}

    if option_type == "put":
        start_itm_pct = max((first["from_strike"] - start_price) / first["from_strike"] * 100, 0)
    else:
        start_itm_pct = max((start_price - first["from_strike"]) / first["from_strike"] * 100, 0)

    delta_pts = current_itm_pct - start_itm_pct
    trend = "worsening" if delta_pts >= 5 else "improving" if delta_pts <= -5 else "stable"

    return {
        "weeks_rolled": weeks,
        "first_roll_date": first["date"].isoformat(),
        "itm_pct_at_start": round(start_itm_pct, 1),
        "itm_pct_now": round(current_itm_pct, 1),
        "trend": trend,
        "start_price_source": source,
    }
