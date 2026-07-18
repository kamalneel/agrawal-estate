"""
Ghost freeze-curve: "if I had frozen the options game on date T and just
held my shares and cash, what would I have today?" — computed for every
anchor date with a cash snapshot (near-daily since 2026-02-16).

Definition of freezing at T (agreed with Neel, 2026-07-18):
  - buy back all open short options at that day's marks (ghost pays it),
  - then hold the T-date shares and cash untouched through today,
  - external deposits/withdrawals after T flow into the ghost as inert
    cash, so new capital doesn't masquerade as options performance.

delta(T) = ghost_value_today(T) − actual_value_today
  > 0  → freezing on T would have left him richer (buy-and-hold won)
  < 0  → the options game since T added value

Documented approximations (also returned in the API payload):
  - dividends: no adjustment — both worlds are assumed to collect
    roughly the same; where holdings diverge this slightly flatters the
    options game (small: dividends are a rounding error on this book).
  - symbols with no live price (fully exited: META, TQQQ, …) are valued
    at their last known price and flagged.
  - open-option buyback uses the nearest options snapshot within
    NEAR_DAYS of the anchor.

See docs/INVESTMENTS-PAGE-SPEC.md, "vs. Buy & Hold (ghost freeze-curve)".
"""

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text as _text
from sqlalchemy.orm import Session

NEAR_DAYS = 10  # max distance when matching a snapshot to an anchor


# ---------------------------------------------------------------- prefetch

def _lot_events(db: Session) -> List[Tuple[date, str, float]]:
    """(event_date, symbol, share_delta) for every purchase and sale."""
    rows = db.execute(_text("""
        SELECT purchase_date AS d, symbol, quantity AS q FROM stock_lot
        UNION ALL
        SELECT s.sale_date AS d, l.symbol, -s.quantity_sold AS q
        FROM stock_lot_sale s JOIN stock_lot l ON l.lot_id = s.lot_id
        ORDER BY d
    """)).fetchall()
    return [(r.d, r.symbol, float(r.q)) for r in rows if r.d]


def _shares_today(db: Session) -> Dict[str, float]:
    """Authoritative current share counts (MCP-synced holdings)."""
    rows = db.execute(_text("""
        SELECT symbol, SUM(quantity) AS q FROM investment_holdings
        GROUP BY symbol HAVING SUM(quantity) > 0
    """)).fetchall()
    return {r.symbol: float(r.q) for r in rows}


def _shares_at(anchor: date, today_shares: Dict[str, float],
               events: List[Tuple[date, str, float]]) -> Dict[str, float]:
    """Share counts at the anchor, reconstructed BACKWARD from verified
    current holdings minus lot events after the anchor. Walking forward
    from all-time lots instead drags in phantom residue from pre-2024
    positions whose sales never reached the lot engine (UAL/ZM/WYNN…,
    found on first run 2026-07-18) — backward reconstruction cancels
    anything untouched during the window."""
    shares = dict(today_shares)
    for d, sym, dq in events:
        if d > anchor:
            shares[sym] = shares.get(sym, 0.0) - dq
    return {s: q for s, q in shares.items() if q > 0.0001}


def _prices_today(db: Session) -> Tuple[Dict[str, float], Dict[str, str]]:
    """symbol → best-known current price; second map flags stale sources."""
    prices: Dict[str, float] = {}
    stale: Dict[str, str] = {}
    for r in db.execute(_text("""
        SELECT symbol, MAX(current_price) AS px FROM investment_holdings
        WHERE current_price IS NOT NULL GROUP BY symbol
    """)).fetchall():
        prices[r.symbol] = float(r.px)
    for r in db.execute(_text("""
        SELECT DISTINCT ON (symbol) symbol, close_price, price_date
        FROM symbol_price_history ORDER BY symbol, price_date DESC
    """)).fetchall():
        if r.symbol not in prices:
            prices[r.symbol] = float(r.close_price)
            stale[r.symbol] = f"price history {r.price_date}"
    # last resort: most recent sale price from the lot engine
    for r in db.execute(_text("""
        SELECT DISTINCT ON (l.symbol) l.symbol,
               s.proceeds / NULLIF(s.quantity_sold, 0) AS px, s.sale_date
        FROM stock_lot_sale s JOIN stock_lot l ON l.lot_id = s.lot_id
        ORDER BY l.symbol, s.sale_date DESC
    """)).fetchall():
        if r.symbol not in prices and r.px:
            prices[r.symbol] = float(r.px)
            stale[r.symbol] = f"last sale {r.sale_date}"
    return prices, stale


def _cash_by_date(db: Session) -> Dict[date, float]:
    """Only dates where ALL six accounts have a real cash snapshot.
    Before 2026-06-09 the history holds a single zero row per day; using
    those made the May-assignment weeks look like a $1M ghost collapse
    (cash went invisible while shares left). A backfill of official
    activity CSVs for May–June could extend this window later — the
    transaction ledger alone was validated 2026-07-18 and is $214K short
    over six weeks, so reconstruction without the backfill is untrustworthy."""
    rows = db.execute(_text("""
        SELECT snapshot_date, SUM(true_cash) AS c
        FROM account_cash_balance_history
        WHERE true_cash IS NOT NULL
        GROUP BY snapshot_date
        HAVING COUNT(*) >= 6
        ORDER BY snapshot_date
    """)).fetchall()
    return {r.snapshot_date: float(r.c) for r in rows}


def _buyback_by_date(db: Session) -> Dict[date, float]:
    """Cost to close all open short options as of each options-snapshot day
    (sum across each account's snapshot on that day)."""
    rows = db.execute(_text("""
        WITH per_acct_day AS (
            SELECT s.account_name, s.snapshot_date::date AS d,
                   MAX(s.snapshot_date) AS latest
            FROM sold_options_snapshots s
            GROUP BY s.account_name, s.snapshot_date::date
        )
        SELECT p.d, SUM(o.premium_per_contract * o.contracts_sold * 100) AS cost
        FROM per_acct_day p
        JOIN sold_options_snapshots s
          ON s.account_name = p.account_name AND s.snapshot_date = p.latest
        JOIN sold_options o ON o.snapshot_id = s.id
        WHERE o.expiration_date > p.d AND o.premium_per_contract IS NOT NULL
        GROUP BY p.d ORDER BY p.d
    """)).fetchall()
    return {r.d: float(r.cost or 0) for r in rows}


def _flows(db: Session) -> List[Tuple[date, float]]:
    """External deposits/withdrawals (signed), ordered by date."""
    rows = db.execute(_text("""
        SELECT transaction_date AS d, SUM(amount) AS amt
        FROM investment_transactions
        WHERE transaction_type = 'CASH_MOVEMENT'
        GROUP BY transaction_date ORDER BY transaction_date
    """)).fetchall()
    return [(r.d, float(r.amt or 0)) for r in rows]


def _nearest_at_or_before(d: date, series: Dict[date, float]) -> Optional[float]:
    best = None
    for k in series:
        if k <= d and (best is None or k > best) and (d - k).days <= NEAR_DAYS:
            best = k
    return series.get(best) if best else None


# ------------------------------------------------------------------- curve

def get_ghost_curve(db: Session) -> Dict:
    events = _lot_events(db)
    prices, stale = _prices_today(db)
    cash_hist = _cash_by_date(db)
    buyback_hist = _buyback_by_date(db)
    flows = _flows(db)

    if not cash_hist:
        return {"anchors": [], "error": "no cash history"}

    anchors = sorted(cash_hist.keys())
    today = date.today()
    total_flows = sum(a for _, a in flows)

    # actual value today: live equity + current true cash − cost to close
    # today's open short options (symmetry with the ghost's buyback-at-T)
    equity_today = float(db.execute(_text("""
        SELECT COALESCE(SUM(quantity * current_price), 0)
        FROM investment_holdings WHERE current_price IS NOT NULL
    """)).scalar() or 0)
    cash_today = float(db.execute(_text(
        "SELECT COALESCE(SUM(net_total), 0) FROM account_cash_balances"
    )).scalar() or 0)
    # IRAs: true cash = net_total + collateral (owner's locked money)
    cash_today = float(db.execute(_text("""
        SELECT COALESCE(SUM(
            CASE WHEN margin_used > 0 THEN cash_balance - margin_used
                 ELSE cash_balance + COALESCE(options_collateral, 0)
                      + COALESCE(pending_orders, 0) END), 0)
        FROM account_cash_balances
    """)).scalar() or 0)
    buyback_today = _nearest_at_or_before(today, buyback_hist) or 0.0
    actual_today = equity_today + cash_today - buyback_today

    # assignment markers
    assign_rows = db.execute(_text("""
        SELECT transaction_date, symbol, SUM(quantity) AS q
        FROM investment_transactions WHERE transaction_type = 'OASGN'
        GROUP BY transaction_date, symbol ORDER BY transaction_date
    """)).fetchall()
    assignments = [{"date": r.transaction_date.isoformat(), "symbol": r.symbol,
                    "contracts": float(r.q or 0)} for r in assign_rows]

    # share counts per anchor, reconstructed backward from today's holdings
    today_shares = _shares_today(db)
    curve = []
    for anchor in anchors:
        shares = _shares_at(anchor, today_shares, events)
        ghost_equity = sum(q * prices.get(sym, 0.0) for sym, q in shares.items())
        unpriced = [sym for sym in shares if sym not in prices]
        ghost_cash = cash_hist[anchor]
        buyback = _nearest_at_or_before(anchor, buyback_hist) or 0.0
        flows_after = total_flows - sum(a for d, a in flows if d <= anchor)
        ghost_value = ghost_equity + ghost_cash - buyback + flows_after
        curve.append({
            "anchor": anchor.isoformat(),
            "ghost_value_today": round(ghost_value, 2),
            "delta": round(ghost_value - actual_today, 2),
            "unpriced_symbols": unpriced,
        })

    # premium context: total options premium collected over the window
    premium = float(db.execute(_text("""
        SELECT COALESCE(SUM(amount), 0) FROM investment_transactions
        WHERE transaction_type IN ('STO', 'BTC') AND transaction_date >= :d0
    """), {"d0": anchors[0]}).scalar() or 0)

    worst = max(curve, key=lambda c: c["delta"]) if curve else None
    # only report stale prices for symbols the ghost actually holds somewhere
    used_symbols = set()
    for anchor in (anchors[0], anchors[-1]):
        used_symbols |= set(_shares_at(anchor, today_shares, events))
    used_stale = {s: v for s, v in stale.items() if s in used_symbols}
    return {
        "as_of": today.isoformat(),
        "actual_today": round(actual_today, 2),
        "curve": curve,
        "anchors_from": anchors[0].isoformat(),
        "anchors_limited_reason": ("full 6-account cash snapshots begin 2026-06-09; "
                                   "earlier anchors need a May–June activity-CSV backfill"),
        "assignments": [a for a in assignments if a["date"] >= anchors[0].isoformat()],
        "premium_collected_window": round(premium, 2),
        "worst_anchor": worst,
        "stale_prices": used_stale,
        "approximations": [
            "dividends not adjusted (both worlds assumed equal)",
            "open-option buyback from nearest snapshot within 10 days",
            f"fully-exited symbols valued at last known price: {sorted(used_stale)}" if used_stale else None,
        ],
    }


# ------------------------------------------------------------------- detail

def get_ghost_detail(db: Session, anchor: date) -> Dict:
    """Two-line series (actual vs ghost) from anchor→today + divergence."""
    events = _lot_events(db)
    prices_now, _stale = _prices_today(db)
    cash_hist = _cash_by_date(db)
    buyback_hist = _buyback_by_date(db)
    flows = _flows(db)

    ghost_cash0 = _nearest_at_or_before(anchor, cash_hist)
    if ghost_cash0 is None:
        return {"error": f"no cash snapshot near {anchor}"}
    buyback0 = _nearest_at_or_before(anchor, buyback_hist) or 0.0

    # ghost share counts frozen at the anchor (backward reconstruction —
    # see _shares_at for why forward replay is unsafe)
    today_shares = _shares_today(db)
    ghost_shares = _shares_at(anchor, today_shares, events)

    # weekly price grid from anchor → today
    px_rows = db.execute(_text("""
        SELECT symbol, price_date, close_price FROM symbol_price_history
        WHERE price_date >= :a ORDER BY price_date
    """), {"a": anchor}).fetchall()
    grid: Dict[date, Dict[str, float]] = {}
    for r in px_rows:
        grid.setdefault(r.price_date, {})[r.symbol] = float(r.close_price)

    last_px: Dict[str, float] = {}
    ghost_series = []
    for d in sorted(grid.keys()):
        last_px.update(grid[d])
        equity = sum(q * last_px.get(sym, prices_now.get(sym, 0.0))
                     for sym, q in ghost_shares.items())
        flows_to_d = sum(a for fd, a in flows if anchor < fd <= d)
        ghost_series.append({"date": d.isoformat(),
                             "value": round(equity + ghost_cash0 - buyback0 + flows_to_d, 2)})
    # today's point
    equity_now = sum(q * prices_now.get(sym, last_px.get(sym, 0.0))
                     for sym, q in ghost_shares.items())
    flows_all = sum(a for fd, a in flows if fd > anchor)
    ghost_series.append({"date": date.today().isoformat(),
                         "value": round(equity_now + ghost_cash0 - buyback0 + flows_all, 2)})

    # actual series: holdings history totals + cash history + buyback
    act_rows = db.execute(_text("""
        SELECT snapshot_date, SUM(quantity * COALESCE(market_value / NULLIF(quantity, 0), 0)) AS mv
        FROM investment_holdings_history
        WHERE snapshot_date >= :a GROUP BY snapshot_date ORDER BY snapshot_date
    """), {"a": anchor}).fetchall()
    actual_series = []
    for r in act_rows:
        c = _nearest_at_or_before(r.snapshot_date, cash_hist)
        b = _nearest_at_or_before(r.snapshot_date, buyback_hist) or 0.0
        if c is None:
            continue
        actual_series.append({"date": r.snapshot_date.isoformat(),
                              "value": round(float(r.mv or 0) + c - b, 2)})

    # divergence table
    now_shares = {s: q for s, q in today_shares.items() if q > 0.0001}
    divergence = []
    for sym in sorted(set(ghost_shares) | set(now_shares)):
        g, n = ghost_shares.get(sym, 0.0), now_shares.get(sym, 0.0)
        if abs(g - n) < 0.0001:
            continue
        divergence.append({
            "symbol": sym, "ghost_shares": round(g, 2), "actual_shares": round(n, 2),
            "delta_shares": round(n - g, 2),
            "delta_value": round((n - g) * prices_now.get(sym, 0.0), 2),
        })
    divergence.sort(key=lambda x: -abs(x["delta_value"]))

    premium = float(db.execute(_text("""
        SELECT COALESCE(SUM(amount), 0) FROM investment_transactions
        WHERE transaction_type IN ('STO', 'BTC') AND transaction_date > :a
    """), {"a": anchor}).scalar() or 0)

    return {
        "anchor": anchor.isoformat(),
        "ghost_series": ghost_series,
        "actual_series": actual_series,
        "divergence": divergence,
        "premium_since": round(premium, 2),
    }
