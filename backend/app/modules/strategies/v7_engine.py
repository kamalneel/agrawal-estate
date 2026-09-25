"""V7 action queue — PREVIEW. Two books, four layers.

Built 2026-09-13 from docs/INVESTMENT-THESIS-V2-DRAFT.md and
data/policy_v2.json. Runs beside v6_engine (which stays live); this feeds
only the V7 preview page so Neel can judge it against V6 during a live
trading day before anything is switched.

THE MODEL (Neel, 2026-09-13)
----------------------------
Long-term book (~80%): $1T+ names (+ AMD override). Never sold. Income
from dividends and delta 10-15 covered calls. No puts except re-entry
after a call assignment. Stuck calls: roll weekly for a credit, never pay
intrinsic; buy back on a dip (time value is not penalty); the roll before
ex-dividend goes 3-4 weeks out.

Short-term book (~20%): a named list — INTC SOXL RKLB CBRS ZM MRVL.
Calls at delta 20-40, the technicals pick the number, never ATM, no
difference between assigned and bought shares. Puts on these names
against cash and margin, to maximise option income.

Margin is for puts; puts are for the short-term book. When margin is
drawn by shares instead, the system says "drawn by $X — sell about $X of
stock" and stops; which position is Neel's call, and there is no hurry.

FOUR LAYERS
-----------
1  Long-term calls (sell, roll, dip buy-back, ex-div roll, re-entry put)
2  Short-term calls (sell delta 20-40; ITM at expiry -> let assign)
3  Short-term puts (per account, capacity-aware, 20% throttle)
4  Recovery (margin drawn by shares; 80/20 drift) — notices, not picks

Strike and premium figures are the same heuristics V6 uses
(app/shared/services/option_premium.py) — estimates, not quotes.
Assumptions Claude made where Neel has not spoken are marked
"assumption" in the card's `why` and in policy_v2.json.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.shared.services.option_premium import (
    RATE_ATM_WEEKLY, RATE_TIER1_WEEKLY, next_expiration, strike_for, weekly_premium, atm_order,
)
from app.modules.strategies.technical_signals import get_entry_timing
from app.modules.strategies.v6_engine import (
    NON_TAXABLE_TYPES, CANONICAL_ORDER, MARGIN_ID_TO_NAME, _load_policy_ignore_list,
    _load_earnings_calendar,
)

logger = logging.getLogger(__name__)

_POLICY_V2 = Path(__file__).resolve().parents[4] / "data" / "policy_v2.json"

def K(pol: Dict, key: str):
    """A tunable from policy_v2.json "knobs" — every number the engine uses
    that Neel may want to turn (gear icon on the V7 page)."""
    return pol["knobs"][key]["value"]


def load_policy_v2() -> Dict:
    return json.loads(_POLICY_V2.read_text())


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def _holdings(db: Session) -> Tuple[Dict[Tuple[str, str], Dict], Dict[str, float], Dict[str, str], Dict[str, str]]:
    rows = db.execute(text("""
        SELECT a.account_name, a.account_id, a.account_type, h.symbol, h.quantity,
               h.current_price, h.cost_basis, h.last_updated
        FROM investment_holdings h
        JOIN investment_accounts a ON a.account_id = h.account_id AND a.source = h.source
        WHERE a.is_active = 'Y' AND h.quantity > 0 AND h.symbol != 'CASH'
        ORDER BY h.last_updated ASC
    """)).fetchall()
    holdings, price, acct_type, acct_id = {}, {}, {}, {}
    for r in rows:
        if r.current_price:
            price[r.symbol] = float(r.current_price)   # last write = freshest (same trick as V6)
        holdings[(r.account_name, r.symbol)] = {
            "qty": float(r.quantity),
            "cost_basis": float(r.cost_basis) if r.cost_basis else None,
            "account_id": r.account_id,
        }
        acct_type[r.account_name] = (r.account_type or "").lower()
        acct_id[r.account_name] = r.account_id
    hist = {r.symbol: float(r.close_price) for r in db.execute(text("""
        SELECT DISTINCT ON (symbol) symbol, close_price FROM symbol_price_history
        ORDER BY symbol, price_date DESC""")).fetchall()}
    for s, p in hist.items():
        price.setdefault(s, p)
    return holdings, price, acct_type, acct_id


def _chains(db: Session, max_age_hours: int = 30) -> Dict[Tuple[str, str], List[Dict]]:
    """The live option chain, keyed (symbol, 'call'|'put'), each a list of
    contracts sorted by expiry then strike. Level 3 of the sync
    (2026-09-24): before this the engine knew the mark on contracts we
    already held and nothing else, so every strike and premium on a card
    was a Black-Scholes estimate off one at-the-money implied vol — that
    is how NVDA's delta-15 strike came out $7.50 above the market's.

    Stale snapshots are ignored rather than trusted: a chain older than
    max_age_hours is worse than no chain, because the estimate at least
    uses today's spot."""
    rows = db.execute(text("""
        SELECT symbol, option_type, expiration_date, strike_price, bid, ask, mark,
               delta, implied_vol, open_interest, volume, as_of
        FROM option_chain_quotes
        WHERE as_of >= NOW() - (:h || ' hours')::interval
        ORDER BY symbol, option_type, expiration_date, strike_price
    """), {"h": max_age_hours}).fetchall()
    out: Dict[Tuple[str, str], List[Dict]] = {}
    for r in rows:
        out.setdefault((r.symbol, r.option_type), []).append({
            "expiration": r.expiration_date, "strike": float(r.strike_price),
            "bid": float(r.bid) if r.bid is not None else None,
            "ask": float(r.ask) if r.ask is not None else None,
            "mark": float(r.mark) if r.mark is not None else None,
            "delta": float(r.delta) if r.delta is not None else None,
            "iv": float(r.implied_vol) if r.implied_vol is not None else None,
            "oi": r.open_interest, "volume": r.volume, "as_of": r.as_of,
        })
    return out


def chain_pick(chains: Dict, sym: str, kind: str, exp: date, target_delta_pct: float) -> Optional[Dict]:
    """The listed contract closest to the target delta at that expiry —
    what the market actually offers, not what Black-Scholes computes.
    Returns None when the chain has nothing for that symbol/expiry, and
    the caller falls back to the estimate."""
    rows = [c for c in chains.get((sym, kind), [])
            if c["expiration"] == exp and c["delta"] is not None]
    if not rows:
        return None
    want = target_delta_pct / 100.0
    return min(rows, key=lambda c: abs(abs(c["delta"]) - want))


def chain_quote(chains: Dict, sym: str, kind: str, exp: date, strike: float) -> Optional[Dict]:
    """The listed contract at this exact strike and expiry, if quoted."""
    for c in chains.get((sym, kind), []):
        if c["expiration"] == exp and abs(c["strike"] - strike) < 0.005:
            return c
    return None


def spread_note(c: Optional[Dict]) -> str:
    """'bid 0.13 / ask 0.70' when the quote is wide enough to matter — the
    SOXL and ZM rolls that kept cancelling unfilled were wide books, and a
    card that only showed a mark could not say so."""
    if not c or c.get("bid") is None or c.get("ask") is None or not c.get("mark"):
        return ""
    width = c["ask"] - c["bid"]
    if width <= 0 or width / max(c["mark"], 0.01) < 0.25:
        return ""
    return f" · WIDE bid ${c['bid']:,.2f}/ask ${c['ask']:,.2f}"


def _implied_vols(db: Session, max_age_days: int = 5) -> Dict[str, float]:
    """Latest stored at-the-money implied vol per symbol (fraction), if it
    is recent. The sync writes it alongside the close (skill step 3b)."""
    rows = db.execute(text("""
        SELECT DISTINCT ON (symbol) symbol, implied_vol, price_date FROM symbol_price_history
        WHERE implied_vol IS NOT NULL ORDER BY symbol, price_date DESC
    """)).fetchall()
    today = date.today()
    return {r.symbol: float(r.implied_vol) for r in rows if (today - r.price_date).days <= max_age_days}


def _closes(db: Session) -> Dict[str, List[Tuple[date, float]]]:
    """Recent daily closes per symbol, oldest first — today's move, the
    bounce-since-buy-back check, realized volatility, the 10-day average."""
    rows = db.execute(text("""
        SELECT symbol, price_date, close_price FROM (
            SELECT symbol, price_date, close_price,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY price_date DESC) rn
            FROM symbol_price_history) x
        WHERE rn <= 70 ORDER BY symbol, price_date
    """)).fetchall()
    out: Dict[str, List[Tuple[date, float]]] = {}
    for r in rows:
        out.setdefault(r.symbol, []).append((r.price_date, float(r.close_price)))
    return out


def _day_move_pct(closes: List[Tuple[date, float]], spot: float, today: date) -> Optional[float]:
    """Today's move vs the last close before today."""
    prev = [c for d, c in closes if d < today]
    if not prev or not prev[-1]:
        return None
    return (spot / prev[-1] - 1) * 100


def _recent_buybacks(db: Session, since: date) -> Dict[Tuple[str, str], Dict]:
    """(account_name, symbol) -> the latest BTC on a call with no STO on the
    same symbol after it: the shares are deliberately uncovered (Rule B's
    'buy back on the dip, wait for the bounce')."""
    rows = db.execute(text("""
        SELECT a.account_name, t.symbol, t.transaction_date, t.transaction_type, t.description
        FROM investment_transactions t JOIN investment_accounts a ON a.account_id = t.account_id
        WHERE t.transaction_type IN ('BTC', 'STO') AND t.transaction_date >= :since
          AND t.description ILIKE '%call%'
        ORDER BY t.transaction_date, t.id
    """), {"since": since}).fetchall()
    last: Dict[Tuple[str, str], Dict] = {}
    for r in rows:
        key = (r.account_name, r.symbol)
        if r.transaction_type == "BTC":
            last[key] = {"date": r.transaction_date, "description": r.description}
        else:
            last.pop(key, None)  # a later STO re-covered the shares
    return last


def _open_options(db: Session, today: date) -> List[Dict]:
    rows = db.execute(text("""
        SELECT s.account_name, s.snapshot_date, so.symbol, so.strike_price, so.option_type,
               so.expiration_date, so.contracts_sold, so.premium_per_contract AS mark,
               so.original_premium
        FROM sold_options so
        JOIN sold_options_snapshots s ON s.id = so.snapshot_id
        WHERE so.snapshot_id IN (SELECT MAX(id) FROM sold_options_snapshots GROUP BY account_name)
          AND (so.expiration_date IS NULL OR so.expiration_date >= :today)
    """), {"today": today}).fetchall()
    out = []
    for r in rows:
        out.append({
            "account": r.account_name, "symbol": r.symbol, "strike": float(r.strike_price),
            "type": r.option_type, "expiration": r.expiration_date,
            "dte": (r.expiration_date - today).days if r.expiration_date else None,
            "contracts": int(r.contracts_sold),
            "mark": float(r.mark) if r.mark is not None else None,
            "original": float(r.original_premium) if r.original_premium is not None else None,
            "as_of": r.snapshot_date,
        })
    return out


def _cash(db: Session) -> Dict[str, Dict]:
    rows = db.execute(text("""
        SELECT DISTINCT ON (account_name) account_name, snapshot_date, cash_balance,
               margin_used, options_collateral, true_cash
        FROM account_cash_balance_history
        WHERE account_name != 'Portfolio (Synthetic)'
        ORDER BY account_name, snapshot_date DESC
    """)).fetchall()
    return {r.account_name: {
        "as_of": r.snapshot_date, "cash": float(r.cash_balance or 0),
        "margin_used": float(r.margin_used or 0), "collateral": float(r.options_collateral or 0),
        "true_cash": float(r.true_cash or 0)} for r in rows}


def _recent_call_assignments(db: Session, since: date) -> List[Dict]:
    """Long-term shares called away recently — the one case where a put on
    a long-term name is allowed (re-entry)."""
    from app.modules.strategies.assignment_detection_service import _parse_strike
    rows = db.execute(text("""
        SELECT t.account_id, a.account_name, t.symbol, t.transaction_date, t.quantity, t.description
        FROM investment_transactions t JOIN investment_accounts a ON a.account_id = t.account_id
        WHERE t.transaction_type = 'OASGN' AND t.description ILIKE '%call%' AND t.transaction_date >= :since
    """), {"since": since}).fetchall()
    out = []
    for r in rows:
        k = _parse_strike(r.description)
        if k and r.quantity:
            out.append({"account": r.account_name, "account_id": r.account_id, "symbol": r.symbol,
                        "date": r.transaction_date, "contracts": int(float(r.quantity)), "strike": float(k)})
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _acct_rank(name: str) -> int:
    return CANONICAL_ORDER.index(name) if name in CANONICAL_ORDER else 99


def _assignment_tax(db: Session, account_id: str, account_type: str, symbol: str,
                    shares: float, strike: float, on: date) -> Dict:
    """What letting `shares` go at `strike` costs in tax — the 'repercussion'
    (Neel, 2026-09-20): zero outside the two taxable brokerages; in them,
    the gain on the lots the account's disposal method delivers (Highest
    Cost since 2026-09-14), at the rough LT/ST rates the lot notices use.
    Negative when the top lots are under water (TSLA's $435/$375 lots)."""
    if (account_type or "").lower() != "brokerage":
        return {"taxable": False, "gain": 0.0, "tax": 0.0, "lots": []}
    from app.modules.tax.assignment_tax_notice_service import _open_lots, lot_scenarios, account_method
    lots = _open_lots(db, account_id, symbol)
    if not lots:
        return {"taxable": True, "gain": None, "tax": None, "lots": []}
    sc = lot_scenarios(lots, shares, strike, on)
    key = "highest_cost" if account_method(account_id, on) == "highest_cost" else "fifo"
    pick = sc[key]
    tax = sc["rough_tax_high"] if key == "highest_cost" else sc["rough_tax_fifo"]
    return {"taxable": True, "gain": pick["gain"], "lt_gain": pick["lt_gain"], "st_gain": pick["st_gain"],
            "tax": tax, "method": key, "lots": pick["lots"], "short": pick["short"]}


def _rsi(db: Session, account_id: str, symbol: str) -> Optional[Dict]:
    try:
        e = get_entry_timing(db, account_id, symbol)
    except Exception:  # noqa: BLE001
        return None
    return e if e.get("available") else None


def _realized_vol(closes: List[Tuple[date, float]], lookback: int) -> Optional[float]:
    """Annualised realized volatility (fraction) from the last `lookback`
    daily closes. None with fewer than 10 points."""
    c = [v for _, v in closes[-(lookback + 1):]]
    if len(c) < 11:
        return None
    rets = [math.log(c[i] / c[i - 1]) for i in range(1, len(c)) if c[i - 1] > 0 and c[i] > 0]
    if len(rets) < 10:
        return None
    m = sum(rets) / len(rets)
    var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var * 252)


def _vs_sma_pct(closes: List[Tuple[date, float]], spot: float, n: int) -> Optional[float]:
    c = [v for _, v in closes[-n:]]
    if len(c) < max(5, n // 2):
        return None
    return (spot / (sum(c) / len(c)) - 1) * 100


def _ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _z_for_delta(delta: float) -> float:
    """z with N(z) = 1 − delta (call strike distance in σ√T units).
    Acklam-free approximation via bisection on the erf — good to 1e-4."""
    target = 1 - delta
    lo, hi = -6.0, 6.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if _ncdf(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def call_delta(spot: float, strike: float, vol: Optional[float], dte: int) -> Optional[float]:
    """Chance the call finishes in the money, from realized vol (r = 0)."""
    if not vol or strike <= 0 or spot <= 0:
        return None
    T = max(dte, 1) / 365
    sd = vol * math.sqrt(T)
    return _ncdf((math.log(spot / strike) + 0.5 * sd * sd) / sd)


def same_strike_roll_credit_ps(spot: float, strike: float, vol: Optional[float], dte_now: int, kind: str) -> float:
    """Credit per share for rolling an ITM call or put one week at the same
    strike, priced AS OF THE ROLL DAY (Thursday, 1 day left), not today:
    time value of the new contract (8 days) minus what is left in the
    expiring one (1 day). Neel, 2026-09-20: the AVGO $380 put paid $230 /
    $717 / $140 / $185 / $65 on five weekly rolls while $18-32 in the money
    — the earlier estimate (next week minus TODAY's remaining time value)
    said $0. With r = 0 an ITM put's time value equals the same-strike
    call's value (parity), so both kinds price off call_premium."""
    dte_roll = 1 if dte_now is None or dte_now > 1 else max(dte_now, 1)
    def tv(d: int) -> float:
        c = call_premium(spot, strike, vol, d, 1, RATE_ATM_WEEKLY) / 100.0
        return c - max(spot - strike, 0.0) if kind == "call" else c
    return tv(dte_roll + 7) - tv(dte_roll)


def strike_for_delta(spot: float, delta_pct: float, vol: Optional[float], dte: int, fallback_otm: float) -> float:
    """Call strike at the target delta from the name's own volatility and
    the days to expiry: spot · exp(σ√T · z). Falls back to a flat distance
    when there is no volatility on file."""
    if not vol or dte <= 0:
        return spot * (1 + fallback_otm)
    T = max(dte, 1) / 365
    return spot * math.exp(vol * math.sqrt(T) * _z_for_delta(delta_pct / 100))


def call_premium(spot: float, strike: float, vol: Optional[float], dte: int, contracts: int, fallback_rate: float) -> int:
    """Black-Scholes call value (r = 0) with realized vol standing in for
    IV — an estimate, labelled so. Flat-rate fallback without vol."""
    if not vol or dte <= 0 or strike <= 0:
        return weekly_premium(contracts, spot, fallback_rate)
    T = max(dte, 1) / 365
    sd = vol * math.sqrt(T)
    d1 = (math.log(spot / strike) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    px = spot * _ncdf(d1) - strike * _ncdf(d2)
    return int(max(px, 0.0) * 100 * contracts)


def _short_term_delta(rsi: Optional[float], pol: Dict, vol: Optional[float] = None,
                      vs_sma: Optional[float] = None) -> Tuple[int, str]:
    """Short-term call delta, one rule for every name (Neel, 2026-09-16):
    base from RSI (20/30/40), overridden by mean reversion (≥ threshold
    below the 10-day average → 20, above → 40), then scaled by the name's
    realized volatility against a reference — a name twice as volatile
    gets half the delta — and clamped to the window. Returns (delta, why)."""
    thr = K(pol, "mr_threshold_pct")
    if vs_sma is not None and vs_sma <= -thr:
        base, why = 20, f"{vs_sma:+.1f}% vs 10-day avg → base 20 (bounce is the trade)"
    elif vs_sma is not None and vs_sma >= thr:
        base, why = 40, f"{vs_sma:+.1f}% vs 10-day avg → base 40"
    elif rsi is None:
        base, why = 30, "no RSI on file → base 30"
    elif rsi < K(pol, "st_rsi_low"):
        base, why = 20, f"RSI {rsi:.0f} → base 20"
    elif rsi <= K(pol, "st_rsi_high"):
        base, why = 30, f"RSI {rsi:.0f} → base 30"
    else:
        base, why = 40, f"RSI {rsi:.0f} → base 40"
    if vol:
        ref = K(pol, "vol_reference_pct") / 100
        scaled = base * ref / vol
        why += f" × {ref * 100:.0f}%/{vol * 100:.0f}% vol"
    else:
        scaled = base
        why += " (no vol on file)"
    d = int(round(max(K(pol, "st_delta_min"), min(K(pol, "st_delta_max"), scaled))))
    return d, why + f" → delta {d}"


def _short_term_delta_legacy(rsi: Optional[float], pol: Dict) -> int:
    """Delta 20-40 picked by RSI (policy_v2 short_term.calls.rsi_to_delta).
    No RSI on file -> the middle of the window."""
    if rsi is None:
        return 30
    if rsi < K(pol, "st_rsi_low"):
        return 20
    if rsi <= K(pol, "st_rsi_high"):
        return 30
    return 40


def _trading_days_between(a: date, b: date) -> int:
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def _up_day_worth_it(up_day: bool, mark: Optional[float], n: int, est_new: int,
                     pol: Dict) -> Tuple[bool, str]:
    """The up-day early roll only pays when the expiring call is nearly
    worthless. Neel, 2026-09-23 (ZM $95, 2 days out, $3.10 OTM): "most of
    the cost at the moment is of the time value" — closing it cost $42 of
    a $136 new premium, 31%, while simply waiting collects that $42 as
    decay. The refinement was built on "theta timing is a wash", which
    holds only when there is little time value left to give up. Below the
    knob, roll; above it, wait for expiry."""
    if not up_day:
        return False, ""
    cost = (mark or 0.0) * 100 * n
    if est_new <= 0:
        return up_day, ""
    pct = cost / est_new * 100
    if pct <= K(pol, "up_day_roll_max_tv_pct"):
        return True, f"closing costs ${cost:,.0f}, {pct:.0f}% of the new premium"
    return False, (f"up day, but closing this call costs ${cost:,.0f} — {pct:.0f}% of the ${est_new:,} new premium "
                   f"(over the {K(pol, 'up_day_roll_max_tv_pct'):.0f}% line): that time value is collected by waiting")


def _runaway_status(pol: Dict, sym: str, spot: Optional[float], today: date) -> Optional[Dict]:
    """Active runaway thesis on `sym`, or None. Resolved when the price is
    up release_pct from the declaration or release_days trading days have
    passed — the returned dict says which, so the card can say it."""
    rt = pol.get("runaway_theses", {})
    for e in rt.get("entries", []):
        if e["symbol"] != sym:
            continue
        declared = date.fromisoformat(e["declared"])
        p0 = float(e["price_at_declaration"])
        target = p0 * (1 + K(pol, "runaway_release_pct") / 100)
        days = _trading_days_between(declared, today)
        deadline_days = int(K(pol, "runaway_release_days"))
        moved = spot is not None and spot >= target
        expired = days >= deadline_days
        released = bool(e.get("released"))   # Neel called it off early (SPCX, 2026-09-21)
        return {"entry": e, "target": target, "days": days, "deadline_days": deadline_days,
                "resolved": moved or expired or released,
                "how": "released" if released else "moved" if moved else "expired" if expired else None,
                "p0": p0}
    return None


def _fmt_exp(d: Optional[date]) -> str:
    return d.strftime("%-m/%-d") if d else "—"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def build_v7_queue(db: Session) -> Dict:
    today = date.today()
    pol = load_policy_v2()
    long_term = set(pol["long_term"]["symbols"])
    short_term = set(pol["short_term"]["symbols"])
    put_only = set(pol.get("put_only", {}).get("symbols", []))   # bucket C's own names (2026-09-20)
    exdiv = pol.get("ex_dividend_estimates", {})
    ignore = _load_policy_ignore_list()

    holdings, price, acct_type, acct_id = _holdings(db)
    chains = _chains(db)
    options = _open_options(db, today)
    cash = _cash(db)
    closes = _closes(db)
    ivs = _implied_vols(db)
    lines = {MARGIN_ID_TO_NAME.get(k_, k_): v_ for k_, v_ in pol["margin"]["lines"].items()}
    buybacks = _recent_buybacks(db, today - timedelta(days=10))

    def vol_of(sym: str) -> Tuple[Optional[float], str]:
        """(vol, source) — the market's implied vol when the sync has stored a
        recent one, else 20-day realized. NVDA 2026-09-16: realized 52% vs
        implied 32% put the delta-15 strike at $235 instead of $227.50 and
        the estimate at 3x the chain. Implied is what the chain prices."""
        if sym in ivs:
            return ivs[sym], "IV"
        return _realized_vol(closes.get(sym, []), int(K(pol, "vol_lookback_days"))), "realized"

    earnings_cal = _load_earnings_calendar()

    def earnings_within(sym: str, days: int) -> Optional[str]:
        er = earnings_cal.get(sym)
        if not er:
            return None
        try:
            d = date.fromisoformat(er["date"])
        except Exception:  # noqa: BLE001
            return None
        return er["date"] if 0 <= (d - today).days <= days else None

    def sheltered(acct: str) -> bool:
        return acct_type.get(acct, "") in NON_TAXABLE_TYPES

    covered: Dict[Tuple[str, str], int] = {}
    for o in options:
        if o["type"] == "call":
            covered[(o["account"], o["symbol"])] = covered.get((o["account"], o["symbol"]), 0) + o["contracts"] * 100

    layers: Dict[int, List[Dict]] = {1: [], 2: [], 3: [], 4: []}
    counter = [0]

    def card(layer, action, account, symbol, title, detail, why, earn=None, assumption=None, context=None):
        counter[0] += 1
        layers[layer].append({
            "id": f"v7_{layer}_{counter[0]}", "layer": layer, "action": action,
            "account": account, "symbol": symbol, "title": title, "detail": detail,
            "why": why, "earn": earn, "assumption": assumption, "context": context or {},
        })

    # ---------------- Layer 1 + 2: calls on owned shares ----------------
    for (acct, sym), h in sorted(holdings.items(), key=lambda kv: (_acct_rank(kv[0][0]), kv[0][1])):
        if sym in ignore or sym not in price:
            continue
        book = "long" if sym in long_term else "short" if sym in short_term else None
        if book is None:
            if h["qty"] * price[sym] < 1000:
                continue  # Alisha's 2-share odds and ends — not a policy question
            card(4, "REVIEW", acct, sym,
                 f"{sym}: on neither list",
                 f"{h['qty']:,.0f} sh (${h['qty'] * price[sym]:,.0f}) — not long-term, not short-term",
                 "Every held name must be on one list or the other for the engine to act. "
                 "Add it to policy_v2.json (long_term or short_term) or decide it is an exit.")
            continue
        spot = price[sym]
        uncovered = h["qty"] - covered.get((acct, sym), 0)
        n = int(uncovered // 100)
        if n < 1:
            continue
        rsi_ctx = _rsi(db, h["account_id"], sym)
        rsi = rsi_ctx.get("rsi") if rsi_ctx else None
        cost_ps = (h["cost_basis"] / h["qty"]) if (h["cost_basis"] and h["qty"]) else None
        exp = next_expiration(today)
        if (exp - today).days < int(K(pol, "new_call_min_dte")):
            exp = exp + timedelta(days=7)  # too little week left — sell next Friday's

        # Bounce-wait after a dip buy-back — both books (Neel, 2026-09-15):
        # the point of closing on the dip was to sell the next call off a
        # higher price. Wait +bounce_pct from the buy-back day's close, or
        # bounce_days trading days, then sell. (A runaway thesis, checked
        # below for the long-term book, outranks this.)
        bb = buybacks.get((acct, sym))
        rw_active = book == "long" and (lambda r: r and not r["resolved"])(_runaway_status(pol, sym, spot, today))
        if bb and not rw_active:
            bb_close = next((c for d, c in closes.get(sym, []) if d == bb["date"]), None)
            if bb_close is None:
                bb_close = next((c for d, c in reversed(closes.get(sym, [])) if d <= bb["date"]), None)
            target = bb_close * (1 + K(pol, "bounce_pct") / 100) if bb_close else None
            waited = _trading_days_between(bb["date"], today)
            released = (target is not None and spot >= target) or waited >= int(K(pol, "bounce_days"))
            if not released:
                left = int(K(pol, "bounce_days")) - waited
                card(1 if book == "long" else 2, "WAIT", acct, sym,
                     f"{sym}: bought back {bb['date']:%-m/%-d} on the dip — wait for the bounce before selling the next call",
                     f"{n} contract{'s' if n > 1 else ''} uncovered · now ${spot:,.2f}"
                     + (f" vs ${bb_close:,.2f} at buy-back · sell when ≥ ${target:,.2f} (+{K(pol, 'bounce_pct'):.1f}%)" if target else "")
                     + f" or in {left} trading day{'s' if left != 1 else ''}"
                     + (f" · RSI {rsi:.0f}" if rsi is not None else ""),
                     "Rule B: the point of closing on the dip was to sell the next call off a higher price — a "
                     "higher strike, a safer cushion. Re-selling today would give the strike the dip just took "
                     "away. The clock keeps the shares from sitting uncovered indefinitely.",
                     context={"book": book, "rsi": rsi, "spot": spot, "bounce_wait": True})
                continue
        bounce_note = f"Bounce after the {bb['date']:%-m/%-d} buy-back has arrived — sell off this price. " if bb else ""

        if book == "long":
            lt = pol["long_term"]["calls"]
            rw = _runaway_status(pol, sym, spot, today)
            if rw:
                e = rw["entry"]
                if not rw["resolved"]:
                    card(1, "WAIT", acct, sym,
                         f"{sym}: runaway thesis declared {e['declared']} — no new call until +{K(pol, 'runaway_release_pct'):.0f}% or {rw['deadline_days']} trading days",
                         f"{n} contract{'s' if n > 1 else ''} uncovered · now ${spot:,.2f} vs ${rw['p0']:,.2f} at declaration · "
                         f"release at ${rw['target']:,.2f} or in {rw['deadline_days'] - rw['days']} trading day{'s' if rw['deadline_days'] - rw['days'] != 1 else ''}"
                         + (f" · RSI {rsi:.0f}" if rsi is not None else ""),
                         f"You overrode the technicals: {e['reason']} RSI cannot say when a runaway is over (it is "
                         f"high before and during one), so the thesis resolves on price or on time — whichever "
                         f"comes first — and only then does the delta 10-15 call go back on, at the higher price.",
                         context={"book": "long", "rsi": rsi, "spot": spot, "runaway": True})
                    continue
                # resolved: fall through to the normal SELL, but say why it is back
                resolved_note = (f"Runaway thesis of {e['declared']} resolved — "
                                 + (f"{sym} reached ${rw['target']:,.2f} (+{K(pol, 'runaway_release_pct'):.0f}%): sell the call up here. "
                                    if rw['how'] == 'moved' else
                                    f"{rw['deadline_days']} trading days passed without the move: resume income. ")
                                 + "Remove the entry from policy_v2.json runaway_theses. ")
            else:
                resolved_note = ""
            vol, vol_src = vol_of(sym)
            dte_new = max((exp - today).days, 1)
            if sym == "TSLA":
                target_delta, delta_txt = K(pol, "lt_delta_tsla"), f"{K(pol, 'lt_delta_tsla'):.0f}"
                gate = K(pol, "lt_tsla_rsi_gate")
                wait = not (rsi is not None and rsi > gate)
                wait_reason = (f"RSI {rsi:.0f} — TSLA carve-out fires only above {gate:.0f}" if rsi is not None
                               else f"no RSI on file — TSLA carve-out needs RSI > {gate:.0f}")
            else:
                target_delta = K(pol, "lt_delta_sheltered") if sheltered(acct) else K(pol, "lt_delta_taxable")
                delta_txt = f"{target_delta:.0f}"
                # V6's "declining — needs two +3% sessions" gate is retired
                # (Neel, 2026-09-16: NVDA had recovered +2.2% off Monday's low
                # and it still said hold off). Wait only while the name is
                # depressed — ≥ threshold below its 10-day average, where a
                # call caps the recovery. The bounce-wait after a buy-back is
                # handled above.
                vs_lt = _vs_sma_pct(closes.get(sym, []), spot, max(int(K(pol, "vol_lookback_days")) // 2, 5))
                depressed_sma = vs_lt is not None and vs_lt <= -K(pol, "mr_threshold_pct")
                # RSI too: a 10-day average follows a slide down, so the gap stays
                # small while the stock keeps falling (AVGO 2026-09-16: -2.7% vs
                # average, RSI 34, 6% under Friday). Restored from V6's gate.
                oversold = rsi is not None and rsi < K(pol, "lt_wait_rsi")
                wait = depressed_sma or oversold
                wait_reason = (" and ".join(
                    ([f"{vs_lt:+.1f}% vs 10-day average"] if depressed_sma else [])
                    + ([f"RSI {rsi:.0f} < {K(pol, 'lt_wait_rsi'):.0f}"] if oversold else []))
                    + " — oversold; a call sold here caps the recovery") if wait else ""
            picked = chain_pick(chains, sym, "call", exp, target_delta)
            strike = picked["strike"] if picked else strike_for_delta(spot, target_delta, vol, dte_new, 0.055)
            floor = ""
            if K(pol, "cost_floor_enabled") and cost_ps and strike < cost_ps:
                strike, floor, picked = cost_ps, " (raised to cost-basis floor)", chain_quote(chains, sym, "call", exp, cost_ps)
            est = (int(round(picked["mark"] * 100 * n)) if picked and picked["mark"]
                   else call_premium(spot, strike, vol, dte_new, n, RATE_TIER1_WEEKLY))
            quoted = " · quoted" if picked and picked["mark"] else ""
            action = "WAIT" if wait else "SELL"
            card(1, action, acct, sym,
                 f"{sym}: {'hold off — ' if wait else ''}sell {n} call{'s' if n > 1 else ''} at delta {delta_txt}",
                 f"strike ${strike:,.2f}{floor} · exp {_fmt_exp(exp)} · est ${est:,}{quoted}"
                 + (f" (delta {abs(picked['delta']):.2f})" if picked and picked["delta"] else "")
                 + spread_note(picked)
                 + (f" · {vol_src} {vol * 100:.0f}%" if vol else "")
                 + (f" · RSI {rsi:.0f}" if rsi is not None else ""),
                 resolved_note + (f"{wait_reason}. " if wait else "")
                 + bounce_note
                 + "Long-term book: income without getting called away. Delta 10-15 by the V7 policy; "
                   "the shares are never sold, so the strike stays far enough out that assignment is unlikely.",
                 earn=None if wait else est,
                 context={"book": "long", "rsi": rsi, "spot": spot, "uncovered": int(uncovered)})
        else:
            vol, vol_src = vol_of(sym)
            vs_sma = _vs_sma_pct(closes.get(sym, []), spot, max(int(K(pol, "vol_lookback_days")) // 2, 5))
            delta, rsi_note = _short_term_delta(rsi, pol, vol, vs_sma)
            dte_new = max((exp - today).days, 1)
            picked = chain_pick(chains, sym, "call", exp, delta)
            strike = picked["strike"] if picked else strike_for_delta(spot, delta, vol, dte_new, 0.025)
            floor = ""
            if K(pol, "cost_floor_enabled") and cost_ps and strike < cost_ps:
                strike, floor, picked = cost_ps, " (raised to cost-basis floor)", chain_quote(chains, sym, "call", exp, cost_ps)
            rate = RATE_TIER1_WEEKLY + (RATE_ATM_WEEKLY - RATE_TIER1_WEEKLY) * (delta - 10) / 40
            est = (int(round(picked["mark"] * 100 * n)) if picked and picked["mark"]
                   else call_premium(spot, strike, vol, dte_new, n, rate))
            quoted = " · quoted" if picked and picked["mark"] else ""
            card(2, "SELL", acct, sym,
                 f"{sym}: sell {n} call{'s' if n > 1 else ''} at delta {delta}",
                 f"strike ${strike:,.2f}{floor} · exp {_fmt_exp(exp)} · est ${est:,}{quoted}"
                 + (f" (delta {abs(picked['delta']):.2f})" if picked and picked["delta"] else "")
                 + spread_note(picked) + f" · {rsi_note}",
                 bounce_note + "Short-term book, one rule for every name: RSI picks a base delta (20/30/40), "
                 "being ≥ threshold below the 10-day average forces 20 (the bounce is the trade), then the "
                 "delta is scaled by the name's own 20-day realized volatility against the reference — a name "
                 "twice as volatile gets half the delta. Strike and premium come from that volatility and the "
                 "days to expiry, not a fixed distance. Never at the money.",
                 earn=est,
                 assumption=None,
                 context={"book": "short", "rsi": rsi, "delta": delta, "spot": spot, "uncovered": int(uncovered)})

    # Calls Neel has decided to let assign (policy_v2 planned_assignments):
    # the long-term book's one exit — a trim he chose, usually to repay
    # margin. LET ASSIGN instead of ROLL, with the tax-lot reminder.
    planned = {(e["account"], e["symbol"], float(e["strike"])): e
               for e in pol.get("planned_assignments", {}).get("entries", [])}

    # ---------------- Layer 1 + 2: open calls (stuck / winning) ----------------
    for o in sorted(options, key=lambda o: (_acct_rank(o["account"]), o["symbol"])):
        if o["type"] != "call" or o["symbol"] not in price:
            continue
        sym, acct, spot, k = o["symbol"], o["account"], price[o["symbol"]], o["strike"]
        book = "long" if sym in long_term else "short" if sym in short_term else None
        if book is None:
            continue
        itm = spot > k
        mark = o["mark"]
        n = o["contracts"]
        plan = planned.get((acct, sym, k))
        if plan:
            proceeds = k * 100 * n
            card(1 if book == "long" else 2, "LET ASSIGN", acct, sym,
                 f"{sym} ${k:,.0f} call — planned: let {n * 100:,} shares go {_fmt_exp(o['expiration'])}",
                 f"{n} contract{'s' if n > 1 else ''} · ${spot - k:,.2f} in the money · proceeds ${proceeds:,.0f} at strike"
                 + (" · Highest Cost lots" if sheltered(acct) is False else ""),
                 f"Decided {plan['decided']}: {plan['reason']} Do not roll. If it slips out of the money by "
                 f"expiry, the shares stay and the plan waits for the next call.",
                 context={"planned": True, "proceeds": proceeds})
            continue
        if book == "long":
            if itm:
                intrinsic = spot - k
                tv = (mark - intrinsic) if mark is not None else None
                ex = exdiv.get(sym)
                ex_date = date.fromisoformat(ex["date"]) if ex else None
                exdiv_soon = ex_date is not None and 0 <= (ex_date - today).days <= int(K(pol, 'exdiv_lookahead_days'))
                roll_credit = weekly_premium(n, spot, RATE_TIER1_WEEKLY)  # next week's time value, rough
                if exdiv_soon and (o["dte"] is None or o["expiration"] < ex_date + timedelta(days=int(K(pol, 'exdiv_roll_weeks')) * 7)):
                    out = ex_date + timedelta(days=int(K(pol, 'exdiv_roll_weeks')) * 7)
                    card(1, "ROLL", acct, sym,
                         f"{sym} ${k:,.0f} call ITM — ex-dividend {_fmt_exp(ex_date)}: roll {int(K(pol, 'exdiv_roll_weeks'))} weeks out, same strike",
                         f"{n} contract{'s' if n > 1 else ''} · ${intrinsic:,.2f} in the money · "
                         f"time value ${tv:,.2f}" if tv is not None else f"{n} contract{'s' if n > 1 else ''} · ${intrinsic:,.2f} in the money",
                         f"Rule 3: a deep-ITM weekly's time value falls below the ${ex['dividend']:.2f} dividend and gets "
                         f"exercised early the day before ex-div ({ex_date:%b %-d}). A {int(K(pol, 'exdiv_roll_weeks'))}-week contract "
                         f"carries enough time value to survive it. Same strike, still a credit. Buy back on the dip after.",
                         context={"exdiv": ex["date"], "roll_to": out.isoformat()})
                else:
                    # WHEN to roll (Neel, 2026-09-15). A same-strike roll's credit
                    # is time value(next) − time value(this); the expiring
                    # contract decays fastest in its last days while next
                    # week's barely moves, so the credit grows through the
                    # week (~$0.75 Tue → ~$0.98 Thu on AAPL $315, 2026-09-15).
                    # And every un-rolled day is a day the dip can settle it
                    # for free — an early roll leaves an at-the-money call to
                    # buy back at max time value when the dip finally comes.
                    # So: Thursday by default; Friday morning if RSI > 70 (the
                    # dip is more likely, stretch); NOW only when the expiring
                    # contract's time value is at the early-exercise floor.
                    # Never Friday afternoon: an unfilled roll assigns at the
                    # close.
                    rsi_ctx = _rsi(db, acct_id.get(acct), sym)
                    rsi = rsi_ctx.get("rsi") if rsi_ctx else None
                    dte = o["dte"] if o["dte"] is not None else 5
                    exp_d = o["expiration"]
                    floor_hit = tv is not None and tv <= K(pol, 'roll_tv_floor')
                    stretch = rsi is not None and rsi > K(pol, 'roll_stretch_rsi')
                    # the roll day is relative to THIS contract's expiry, not the calendar week
                    roll_date = exp_d - timedelta(days=0 if stretch else 1) if exp_d else None
                    roll_day = (f"{'Friday morning' if stretch else 'Thursday'} {_fmt_exp(roll_date)}") if roll_date else "Thursday"
                    due_today = dte <= (0 if stretch else 1)
                    # WHETHER to keep rolling (Neel, 2026-09-20). "Whatever
                    # goes up comes down" — but how long it takes is the
                    # question, and the technicals answer it. RSI high: the
                    # come-down is near, roll and wait. RSI not high and the
                    # roll paying next to nothing: the come-down is a
                    # months-long one, and rolling for zero for months is
                    # dead money — so weigh the cost of leaving: the tax on
                    # the lots Highest Cost delivers. Zero in the sheltered
                    # accounts, negative when the top lots are under water
                    # (TSLA $335: −$10K lot), large when every lot is old
                    # and cheap (AAPL $315: ~$310K of gain). Cheap to leave
                    # → LET ASSIGN and the name re-enters via the put
                    # ranking; expensive → carry it. MSFT $450 on 9/18 was
                    # the worked example: $40 ITM, zero credit, RSI not
                    # high, ~$2.4K of tax on $45K — leave.
                    vol_, _src = vol_of(sym)
                    credit_ps = same_strike_roll_credit_ps(spot, k, vol_, dte, "call")
                    roll_credit = int(round(max(credit_ps, 0) * 100 * n))
                    proceeds = k * 100 * n
                    taxc = _assignment_tax(db, acct_id.get(acct), acct_type.get(acct, ""), sym, n * 100, k, exp_d or today)
                    tax = taxc.get("tax")
                    tax_pct = (tax / proceeds * 100) if (tax is not None and proceeds) else None
                    assign_rsi = K(pol, "assign_rsi")
                    thin = credit_ps <= K(pol, "roll_thin_credit_ps")
                    max_tax_pct = K(pol, "lt_assign_max_tax_pct")
                    rsi_txt = f"RSI {rsi:.0f}" if rsi is not None else "no RSI on file"
                    if taxc["taxable"] and tax is not None:
                        tax_txt = (f"tax ≈ {'−' if tax < 0 else ''}${abs(tax):,.0f} ({tax_pct:+.1f}% of ${proceeds:,.0f}; "
                                   f"gain {'−' if taxc['gain'] < 0 else ''}${abs(taxc['gain']):,.0f}, "
                                   f"{'Highest Cost' if taxc['method'] == 'highest_cost' else 'FIFO'} lots)")
                    elif taxc["taxable"]:
                        tax_txt = "tax unknown — no lots on file"
                    else:
                        tax_txt = "no tax — sheltered account"
                    if rsi is not None and rsi >= assign_rsi:
                        verdict, why_v = "ROLL", (f"{rsi_txt} ≥ {assign_rsi:.0f}: overbought, the come-down is near — "
                                                 f"roll and wait for it")
                    elif not thin:
                        verdict, why_v = "ROLL", (f"the same-strike roll still pays ${credit_ps:.2f}/share "
                                                 f"(> ${K(pol, 'roll_thin_credit_ps'):.2f} thin-credit line) — carrying it is paid for")
                    elif tax is None and taxc["taxable"]:
                        verdict, why_v = "ROLL", "the tax cost of leaving is unknown (no lots on file) — carry it until it is"
                    elif tax_pct is None or tax_pct <= max_tax_pct:
                        verdict, why_v = "LET ASSIGN", (f"{rsi_txt} < {assign_rsi:.0f} and the roll pays ${max(credit_ps, 0):.2f}/share: "
                                                       f"the come-down is a long one and rolling for nothing is dead money; "
                                                       f"leaving is cheap ({tax_txt}, under the {max_tax_pct:.0f}% line) — let the shares go, "
                                                       f"${proceeds:,.0f} returns to the put ranking, and a put on {sym} is the way back in")
                    else:
                        verdict, why_v = "ROLL", (f"{rsi_txt} < {assign_rsi:.0f} and the roll pays ${max(credit_ps, 0):.2f}/share — "
                                                 f"a long wait — but leaving is expensive ({tax_txt}, over the {max_tax_pct:.0f}% line): carry it")
                    verdict_ctx = {"verdict": verdict, "credit_ps": round(credit_ps, 2), "roll_credit": roll_credit,
                                   "tax": tax, "tax_pct": round(tax_pct, 1) if tax_pct is not None else None,
                                   "proceeds": proceeds, "taxable": taxc["taxable"]}
                    if floor_hit:
                        action, when = "ROLL", f"now — time value ${tv:,.2f} is at the ${K(pol, 'roll_tv_floor'):.2f} early-exercise floor"
                        # the floor forces a decision today: same verdict, just now
                        if verdict == "LET ASSIGN":
                            action = "LET ASSIGN"
                    elif due_today:
                        action = verdict
                        when = "today" + (" (morning, not afternoon)" if dte == 0 else "")
                    else:
                        action, when = "WAIT", roll_day
                    tv_txt = f" · time value left ${tv:,.2f}" if tv is not None else ""
                    detail = (f"{n} contract{'s' if n > 1 else ''} · exp {_fmt_exp(o['expiration'])} · ${intrinsic:,.2f} in the money"
                              + tv_txt + f" · roll credit est ${roll_credit:,} · {rsi_txt} · {tax_txt}"
                              + spread_note(chain_quote(chains, sym, "call", o["expiration"], k)))
                    if action == "LET ASSIGN":
                        title = f"{sym} ${k:,.0f} call ITM — let {n * 100:,} shares go {_fmt_exp(o['expiration'])}"
                    elif action == "ROLL":
                        title = f"{sym} ${k:,.0f} call ITM — roll {when}, same strike"
                    else:
                        title = (f"{sym} ${k:,.0f} call ITM — {roll_day}: "
                                 + ("let it assign, as things stand" if verdict == "LET ASSIGN" else "roll, as things stand"))
                    card(1, action, acct, sym, title, detail,
                         why_v + ". Rule 1 still holds: never pay a debit to get out. "
                         + ("Decided on Thursday with that day's RSI, credit and lots; until then the dip can settle it for free. "
                            if action == "WAIT" else "")
                         + "Roll timing: Thursday by default, Friday morning when RSI is high, immediately at the "
                         f"${K(pol, 'roll_tv_floor'):.2f} time-value floor; never Friday afternoon.",
                         earn=roll_credit if action == "ROLL" else None,
                         context={"intrinsic": intrinsic, "time_value": tv, "roll_day": roll_day, "rsi": rsi,
                                  "floor_hit": floor_hit, **verdict_ctx})
            else:
                # OTM: the dip buy-back / profit take
                rw = _runaway_status(pol, sym, spot, today)
                dlt = call_delta(spot, k, vol_of(sym)[0], o["dte"] if o["dte"] is not None else 5)
                if rw and not rw["resolved"] and mark is not None:
                    # A runaway thesis is about DISTANCE (Neel, 2026-09-15): the
                    # cap that gets bought back is the one close enough to take
                    # the shares on the first day of the move. A cap far enough
                    # above is room for the run and stays — until the price
                    # climbs into the cushion, which this re-checks every run.
                    # Distance, time and volatility together: the call's delta.
                    # A $10 gap with 2 days left is a normal delta-10 call; the
                    # same gap with 9 days left is a real chance of assignment
                    # during the run (Neel, 2026-09-16, SPCX $160).
                    thr = K(pol, "runaway_uncap_delta") / 100
                    gap_pct = (k / spot - 1) * 100
                    if dlt is not None and dlt >= thr:
                        cost = mark * 100 * n
                        card(1, "BUY BACK", acct, sym,
                             f"{sym} ${k:,.0f} call — runaway thesis, delta {dlt:.2f} with {o['dte']} days left: buy back to uncap, ${cost:,.0f}",
                             f"{n} contract{'s' if n > 1 else ''} · {gap_pct:+.1f}% above spot · mark ${mark:,.2f} vs ${o['original'] or 0:,.2f} sold · exp {_fmt_exp(o['expiration'])} · "
                             f"release at ${rw['target']:,.2f} or in {rw['deadline_days'] - rw['days']} trading days",
                             f"{rw['entry']['reason']} At delta {dlt:.2f} this cap has a real chance of taking the shares "
                             f"during the run (threshold {thr:.2f}). A call with a lower delta — further out, or nearer "
                             f"expiry — is room for the run and stays.",
                             context={"runaway": True, "buyback_cost": cost, "gap_pct": round(gap_pct, 1), "delta": round(dlt, 2)})
                        continue
                    # low delta: the call is room for the run — fall through to normal handling
                captured = (1 - mark / o["original"]) * 100 if (mark is not None and o["original"]) else None
                move = _day_move_pct(closes.get(sym, []), spot, today)
                rsi_ctx = _rsi(db, acct_id.get(acct), sym)
                rsi = rsi_ctx.get("rsi") if rsi_ctx else None
                dip = (move is not None and move <= K(pol, "dip_move_pct")) or (rsi is not None and rsi < K(pol, "dip_rsi"))
                cheap = captured is not None and captured >= K(pol, "cheap_captured_pct")
                er = earnings_within(sym, int(K(pol, "bounce_days")) + 2)
                dte = o["dte"] if o["dte"] is not None else 5
                cost = (mark or 0) * 100 * n
                # Rule B needs enough week left to matter — or a call so far
                # captured that closing is free (Neel, 2026-09-15: SPCX $160
                # at 86% with 3 days left and 11% of room is Rule A's, not B's).
                enough_time = dte >= int(K(pol, "rule_b_min_dte")) or (captured is not None and captured >= K(pol, "free_close_captured_pct"))
                if dip and cheap and not er and dte >= 1 and enough_time:
                    # Rule B: buy back on the dip, wait for the bounce, sell higher.
                    card(1, "BUY BACK", acct, sym,
                         f"{sym} ${k:,.0f} call — dip: buy back for ${cost:,.0f}, wait for the bounce, sell higher",
                         f"{n} contract{'s' if n > 1 else ''} · {captured:.0f}% captured (mark ${mark:,.2f} vs ${o['original']:,.2f}) · "
                         + (f"today {move:+.1f}%" if move is not None else "move n/a")
                         + (f" · RSI {rsi:.0f}" if rsi is not None else "") + f" · exp {_fmt_exp(o['expiration'])}",
                         f"Rule B: the stock is down and the call is cheap. Closing now costs ${cost:,.0f} and buys a higher "
                         f"strike: the next call goes on once {sym} is +{K(pol, 'bounce_pct'):.1f}% from today's close, or in "
                         f"{int(K(pol, 'bounce_days'))} trading days at the latest. Re-selling today would cap at the dip price.",
                         context={"captured_pct": round(captured, 1), "buyback_cost": cost, "day_move_pct": move, "rsi": rsi})
                elif dte <= 1 or (dte < int(K(pol, "rule_b_min_dte")) and move is not None and move >= K(pol, "rule_a_up_day_pct")):
                    # Rule A: winning call at expiry — roll Friday, don't lose Monday.
                    # Refinement (Neel, 2026-09-16): in the last days, an up day is
                    # the moment — theta timing is a wash, the price path decides.
                    up_day = dte >= 1 and move is not None and move >= K(pol, "rule_a_up_day_pct")
                    td = K(pol, "lt_delta_tsla") if sym == "TSLA" else (K(pol, "lt_delta_sheltered") if sheltered(acct) else K(pol, "lt_delta_taxable"))
                    vol, vol_src = vol_of(sym)
                    nxt = strike_for_delta(spot, td, vol, 7, 0.055)
                    est = call_premium(spot, nxt, vol, 7, n, RATE_TIER1_WEEKLY)
                    up_day, tv_note = _up_day_worth_it(up_day, mark, n, est, pol)
                    roll_now = dte == 0 or up_day
                    if rw and not rw["resolved"]:
                        # Under a runaway thesis the roll's second leg — a new call —
                        # is exactly what the thesis forbids. Let this one expire.
                        card(1, "LET EXPIRE", acct, sym,
                             f"{sym} ${k:,.0f} call — let it expire {_fmt_exp(o['expiration'])}; runaway thesis, no new call yet",
                             f"{n} contract{'s' if n > 1 else ''} · {captured:.0f}% captured · delta {(dlt if dlt is not None else 0):.2f} · "
                             f"release at ${rw['target']:,.2f} or in {rw['deadline_days'] - rw['days']} trading days",
                             f"{rw['entry']['reason']} This cap is low-delta and expires on its own; the next call waits "
                             f"for the thesis to resolve (+{K(pol, 'runaway_release_pct'):.0f}% or the clock).",
                             context={"runaway": True, "captured_pct": round(captured, 1) if captured is not None else None})
                        continue
                    card(1, "ROLL" if roll_now else "WAIT", acct, sym,
                         (f"{sym} ${k:,.0f} call — up {move:+.1f}% today: roll now, sell next week's delta {td:.0f} (~${nxt:,.0f})" if up_day
                          else f"{sym} ${k:,.0f} call expires today — roll: sell next week's delta {td:.0f} (~${nxt:,.0f})" if dte == 0
                          else f"{sym} ${k:,.0f} call expires tomorrow — roll Friday, not today"),
                         f"{n} contract{'s' if n > 1 else ''} · {captured:.0f}% captured · exp {_fmt_exp(o['expiration'])} · next est ${est:,}"
                         + (f" · today {move:+.1f}%" if move is not None else ""),
                         ("Rule A, up-day refinement: in the last days of a winning call the buy-back you save by "
                          "waiting is what the new call loses to decay — a wash — so the price path decides, and an "
                          f"up day of ≥{K(pol, 'rule_a_up_day_pct'):.1f}% is the moment to set the next strike. "
                          if up_day else
                          "Rule A: a winning call is left to expire and the next one is sold the same Friday — no "
                          "Monday lost, and no early close just because a threshold crossed. An up day in the last "
                          "days brings the roll forward; only a dip (Rule B) or the ex-dividend rule changes it otherwise."),
                         earn=est if roll_now else None,
                         context={"captured_pct": round(captured, 1) if captured is not None else None})
                elif dip and cheap and not er and dte >= 1 and not enough_time:
                    pass  # Rule A: expires within days, room to spare — hold, roll Friday (no card until Thursday)
                elif er and dip and cheap:
                    card(1, "HOLD", acct, sym,
                         f"{sym} ${k:,.0f} call — dip, but earnings {er}: keep the cover",
                         f"{n} contract{'s' if n > 1 else ''} · {captured:.0f}% captured · exp {_fmt_exp(o['expiration'])}",
                         "Rule B would close this on the dip, but the shares would sit uncovered across an earnings "
                         "date. The cover stays.")
        else:
            if itm:
                # Short-term ITM call (Neel, 2026-09-20). Assignment is the
                # normal exit in this book — no planned_assignments entry —
                # but not the automatic one. Thursday of expiry week:
                #   1. the same-strike roll pays nothing → LET ASSIGN (rule 1,
                #      never pay a debit, same as long-term);
                #   2. it pays a credit → RSI decides. Overbought (≥ st_assign_rsi)
                #      means the run is likely to come back under the strike —
                #      be patient, ROLL. Not stretched means no reason to expect
                #      it back, and the same money earns more as a put on the
                #      next-ranked name — LET ASSIGN and redeploy.
                # Before Thursday: WAIT, same as the long-term roll timing
                # (the credit grows through the week; the dip may settle it).
                intrinsic = spot - k
                tv = (mark - intrinsic) if mark is not None else None
                vol_, _src = vol_of(sym)
                roll_credit_ps = same_strike_roll_credit_ps(spot, k, vol_, o["dte"], "call")
                roll_credit = int(round(max(roll_credit_ps, 0) * 100 * n))
                rsi_ctx = _rsi(db, acct_id.get(acct), sym)
                rsi = rsi_ctx.get("rsi") if rsi_ctx else None
                assign_rsi = K(pol, "assign_rsi")
                dte = o["dte"] if o["dte"] is not None else 5
                floor_hit = tv is not None and tv <= K(pol, 'roll_tv_floor')
                due = dte <= 1 or floor_hit
                proceeds = k * 100 * n
                rsi_txt = f"RSI {rsi:.0f}" if rsi is not None else "no RSI on file"
                if roll_credit_ps <= 0.05:
                    verdict, why_v = "LET ASSIGN", (f"the same-strike roll pays nothing (next week's time value ≈ this week's) — "
                                                   f"never pay a debit to keep short-term shares")
                elif rsi is not None and rsi >= assign_rsi:
                    verdict, why_v = "ROLL", (f"{rsi_txt} ≥ {assign_rsi:.0f}: overbought, the run is likely to come back under "
                                             f"${k:,.0f} — patience pays, roll for the ${roll_credit:,} credit")
                else:
                    verdict, why_v = "LET ASSIGN", (f"{rsi_txt} < {assign_rsi:.0f}: not stretched, no reason to expect it back under "
                                                   f"${k:,.0f}; the ${roll_credit:,} roll credit is less than ${proceeds:,.0f} earns "
                                                   f"back in the put ranking")
                detail = (f"{n} contract{'s' if n > 1 else ''} · exp {_fmt_exp(o['expiration'])} · ${intrinsic:,.2f} in the money"
                          + (f" · time value left ${tv:,.2f}" if tv is not None else "")
                          + f" · roll credit est ${roll_credit:,} · {rsi_txt}"
                          + (f" · frees ${proceeds:,.0f}" if verdict == "LET ASSIGN" else ""))
                why = ("Short-term ITM call: assignment is the normal exit here, not a failure — but only when the roll "
                       "pays nothing or the name is not overbought. " + why_v + ". Rule 1 still holds: never a debit. "
                       f"After assignment the name simply re-enters the put ranking (yield vs. share of the book).")
                if due:
                    card(2, verdict, acct, sym,
                         (f"{sym} ${k:,.0f} call ITM — let the shares go {_fmt_exp(o['expiration'])}" if verdict == "LET ASSIGN"
                          else f"{sym} ${k:,.0f} call ITM — roll {'now' if floor_hit else 'today'}, same strike"),
                         detail, why, earn=roll_credit if verdict == "ROLL" else None,
                         context={"intrinsic": intrinsic, "time_value": tv, "rsi": rsi, "roll_credit": roll_credit,
                                  "verdict": verdict, "proceeds": proceeds})
                else:
                    roll_date = o["expiration"] - timedelta(days=1) if o["expiration"] else None
                    card(2, "WAIT", acct, sym,
                         f"{sym} ${k:,.0f} call ITM — Thursday {_fmt_exp(roll_date)}: "
                         + ("let it assign as things stand" if verdict == "LET ASSIGN" else "roll, as things stand"),
                         detail, why + " Decided on Thursday with that day's RSI and credit; until then the dip can settle it for free.",
                         context={"intrinsic": intrinsic, "time_value": tv, "rsi": rsi, "roll_credit": roll_credit,
                                  "verdict": verdict, "proceeds": proceeds})
            else:
                # Winning short-term call: the same Rules A/B as the long-term
                # book (2026-09-17 — CBRS $215 and RKLB $70 at expiry drew
                # nothing because these rules only lived in the long branch).
                captured = (1 - mark / o["original"]) * 100 if (mark is not None and o["original"]) else None
                move = _day_move_pct(closes.get(sym, []), spot, today)
                rsi_ctx = _rsi(db, acct_id.get(acct), sym)
                rsi = rsi_ctx.get("rsi") if rsi_ctx else None
                dip = (move is not None and move <= K(pol, "dip_move_pct")) or (rsi is not None and rsi < K(pol, "dip_rsi"))
                cheap = captured is not None and captured >= K(pol, "cheap_captured_pct")
                er = earnings_within(sym, int(K(pol, "bounce_days")) + 2)
                dte = o["dte"] if o["dte"] is not None else 5
                cost = (mark or 0) * 100 * n
                enough_time = dte >= int(K(pol, "rule_b_min_dte")) or (captured is not None and captured >= K(pol, "free_close_captured_pct"))
                up_day = dte >= 1 and dte < int(K(pol, "rule_b_min_dte")) and move is not None and move >= K(pol, "rule_a_up_day_pct")
                if dip and cheap and not er and dte >= 1 and enough_time:
                    card(2, "BUY BACK", acct, sym,
                         f"{sym} ${k:,.0f} call — dip: buy back for ${cost:,.0f}, wait for the bounce, sell higher",
                         f"{n} contract{'s' if n > 1 else ''} · {captured:.0f}% captured (mark ${mark:,.2f} vs ${o['original']:,.2f}) · "
                         + (f"today {move:+.1f}%" if move is not None else "move n/a") + (f" · RSI {rsi:.0f}" if rsi is not None else "")
                         + f" · exp {_fmt_exp(o['expiration'])}",
                         "Rule B, short-term book: the stock is down and the call is cheap — close now, wait for the bounce "
                         f"(+{K(pol, 'bounce_pct'):.1f}% or {int(K(pol, 'bounce_days'))} trading days), then sell the next call at the "
                         "delta 20-40 rule off the higher price.",
                         context={"captured_pct": round(captured, 1), "buyback_cost": cost, "day_move_pct": move, "rsi": rsi})
                elif dte <= 1 or up_day:
                    vol_n, _vs = vol_of(sym)
                    vs_n = _vs_sma_pct(closes.get(sym, []), spot, max(int(K(pol, "vol_lookback_days")) // 2, 5))
                    d_n, why_n = _short_term_delta(rsi, pol, vol_n, vs_n)
                    nxt = strike_for_delta(spot, d_n, vol_n, 7, 0.025)
                    est = call_premium(spot, nxt, vol_n, 7, n, RATE_ATM_WEEKLY)
                    up_day, tv_note = _up_day_worth_it(up_day, mark, n, est, pol)
                    roll_now = dte == 0 or up_day
                    card(2, "ROLL" if roll_now else "WAIT", acct, sym,
                         (f"{sym} ${k:,.0f} call — up {move:+.1f}% today: roll now, sell next week's delta {d_n} (~${nxt:,.0f})" if up_day
                          else f"{sym} ${k:,.0f} call expires today — roll: sell next week's delta {d_n} (~${nxt:,.0f})" if dte == 0
                          else f"{sym} ${k:,.0f} call expires tomorrow — roll Friday, not today"),
                         f"{n} contract{'s' if n > 1 else ''} · {captured:.0f}% captured · exp {_fmt_exp(o['expiration'])} · next est ${est:,} · {why_n}"
                         + (f" · today {move:+.1f}%" if move is not None else ""),
                         ("Rule A, up-day refinement: in the last days of a winning call the price path decides; an up day is "
                          "the moment to set the next strike. " if up_day else
                          (tv_note + ". " if tv_note else
                           "Rule A: a winning call is left to expire and the next one sold the same Friday — no Monday lost. "))
                         + "Short-term book: the next call at the delta 20-40 rule.",
                         earn=est if roll_now else None,
                         context={"captured_pct": round(captured, 1) if captured is not None else None, "rsi": rsi})

    # ---------------- Layer 1/2: open short PUTS in the money ----------------
    # V7 had no rule for an existing short put that goes in the money (the
    # AVGO $380 put, 2026-09-16, drew no card at all). Mirror of the stuck-
    # call rule: never pay intrinsic to get out; roll the same strike for a
    # credit on the Thursday of its expiry week, immediately once the time
    # value hits the floor; the alternative is assignment — allowed, and on
    # a long-term name the shares are simply held — when the cash/margin is
    # there and the shares are wanted (record it in planned_assignments).
    for o in sorted(options, key=lambda o: (_acct_rank(o["account"]), o["symbol"])):
        if o["type"] != "put" or o["symbol"] not in price:
            continue
        sym, acct, spot, k, n = o["symbol"], o["account"], price[o["symbol"]], o["strike"], o["contracts"]
        # put-only names (bucket C) are handled like short-term ones here
        book = "long" if sym in long_term else "short" if (sym in short_term or sym in put_only) else None
        if spot >= k:
            # Out of the money. At expiry: roll on the last MORNING — the
            # expiring put's time value bleeds out overnight, the new one
            # loses only a few percent (SPCX $150, 2026-09-17: $225 today,
            # ~$280 Friday morning). Never Friday afternoon.
            dte_p = o["dte"] if o["dte"] is not None else 5
            if dte_p <= 1 and book is not None:
                n_ = o["contracts"]
                vol_p, _src = vol_of(sym)
                # put premium next week at the same strike, via parity: put = call − S + K
                call_px = call_premium(spot, k, vol_p, 7, 1, RATE_ATM_WEEKLY) / 100
                put_px = max(call_px - spot + k, 0.0)
                est = int(put_px * 100 * n_)
                left = (o["mark"] or 0) * 100 * n_
                freed = k * 100 * n_
                card(1 if book == "long" else 2, "LET EXPIRE" if dte_p == 0 else "WAIT", acct, sym,
                     (f"{sym} ${k:,.0f} put expires today — let it go; ${freed:,.0f} frees for the best put (layer 3)" if dte_p == 0
                      else f"{sym} ${k:,.0f} put expires tomorrow — let it expire; ${freed:,.0f} goes back to the put ranking"),
                     f"{n_} contract{'s' if n_ > 1 else ''} · ${spot - k:,.2f} out of the money · ${left:,.0f} of time value left to bleed · "
                     f"same-name renewal would pay est ${est:,}",
                     "An out-of-the-money put at expiry keeps its last time value if left alone. The freed collateral is "
                     "not automatically re-sold on the same name — layer 3 ranks every name by weekly yield at the "
                     "risk-normalised delta and puts the cash where it earns most (on expiry day the layer-3 card already "
                     "counts this collateral as available).",
                     context={"frees": freed})
            continue
        intrinsic = k - spot
        mark = o["mark"]
        tv = (mark - intrinsic) if mark is not None else None
        dte = o["dte"] if o["dte"] is not None else 5
        plan = planned.get((acct, sym, k))
        cost_to_own = k * 100 * n
        layer = 1 if book == "long" else 2
        if plan:
            card(layer, "LET ASSIGN", acct, sym,
                 f"{sym} ${k:,.0f} put — planned: take {n * 100:,} shares {_fmt_exp(o['expiration'])} for ${cost_to_own:,.0f}",
                 f"{n} contract{'s' if n > 1 else ''} · ${intrinsic:,.2f} in the money · exp {_fmt_exp(o['expiration'])}",
                 f"Decided {plan['decided']}: {plan['reason']}",
                 context={"planned": True})
            continue
        floor_hit = tv is not None and tv <= K(pol, "put_roll_tv_floor")
        due = dte <= 1
        acct_c = cash.get(acct, {})
        line = lines.get(acct)
        # brokerage: line + cash − collateral − drawn; IRA: cash_balance is
        # already net of collateral (the bridge writes buying power there)
        room = (line + acct_c.get("cash", 0) - acct_c.get("collateral", 0) - acct_c.get("margin_used", 0)) if line else acct_c.get("cash", 0)
        credit_ps_p = same_strike_roll_credit_ps(spot, k, vol_of(sym)[0], dte, "put")
        roll_credit = int(round(max(credit_ps_p, 0) * 100 * n))
        # WHETHER to keep rolling (Neel, 2026-09-20) — the mirror of the
        # call rule. RSI low = oversold, "the bounce is coming": roll and
        # wait for it. RSI not low and the roll paying next to nothing:
        # the recovery is far; take the shares (long-term name: bought
        # below the strike, held; short-term / put-only: into B, then
        # calls) — if the account has the room. Rolling a real credit is
        # always fine (AVGO $380 paid $65-$717 a week while $18-32 ITM).
        rsi_ctx = _rsi(db, acct_id.get(acct), sym)
        rsi = rsi_ctx.get("rsi") if rsi_ctx else None
        roll_rsi = K(pol, "put_roll_rsi")
        thin = credit_ps_p <= K(pol, "roll_thin_credit_ps")
        rsi_txt = f"RSI {rsi:.0f}" if rsi is not None else "no RSI on file"
        fits = room is None or cost_to_own <= room
        if rsi is not None and rsi <= roll_rsi:
            verdict, why_v = "ROLL", f"{rsi_txt} ≤ {roll_rsi:.0f}: oversold, the bounce is coming — roll and wait for it"
        elif not thin:
            verdict, why_v = "ROLL", (f"the same-strike roll still pays ${credit_ps_p:.2f}/share "
                                     f"(> ${K(pol, 'roll_thin_credit_ps'):.2f} thin-credit line) — carrying it is paid for")
        elif not fits:
            verdict, why_v = "ROLL", (f"{rsi_txt} > {roll_rsi:.0f} and the roll pays ${max(credit_ps_p, 0):.2f}/share — "
                                     f"the recovery is far, but taking ${cost_to_own:,.0f} of shares does not fit the "
                                     f"${room:,.0f} of room: roll")
        else:
            verdict, why_v = "LET ASSIGN", (f"{rsi_txt} > {roll_rsi:.0f} and the roll pays ${max(credit_ps_p, 0):.2f}/share: "
                                           f"the recovery is far and rolling for nothing is dead money — take the "
                                           f"{n * 100:,} shares at ${k:,.0f} (${cost_to_own:,.0f} of ${room:,.0f} room)"
                                           + (", they are long-term shares bought below the strike" if book == "long"
                                              else ", into the short-term book, then calls on them"))
        if floor_hit:
            action = "LET ASSIGN" if verdict == "LET ASSIGN" else "ROLL"
            when = f"now — time value ${tv:,.2f} at the floor"
        elif due:
            action, when = verdict, "today"
        else:
            action, when = "WAIT", f"Thursday {_fmt_exp(o['expiration'] - timedelta(days=1)) if o['expiration'] else ''}"
        if action == "LET ASSIGN":
            title = f"{sym} ${k:,.0f} put ITM — take {n * 100:,} shares {_fmt_exp(o['expiration'])} for ${cost_to_own:,.0f}"
        elif action == "ROLL":
            title = f"{sym} ${k:,.0f} put ITM — roll {when}, same strike"
        else:
            title = f"{sym} ${k:,.0f} put ITM — {when}: " + ("take the shares, as things stand" if verdict == "LET ASSIGN" else "roll, as things stand")
        card(layer, action, acct, sym, title,
             f"{n} contract{'s' if n > 1 else ''} · exp {_fmt_exp(o['expiration'])} · ${intrinsic:,.2f} in the money"
             + (f" · time value left ${tv:,.2f}" if tv is not None else "")
             + f" · roll credit est ${roll_credit:,} · {rsi_txt} · assignment would take ${cost_to_own:,.0f}"
             + (f" of ${room:,.0f} room" if room is not None else ""),
             why_v + ". Never pay intrinsic to get out. "
             + ("Decided on Thursday with that day's RSI and credit. " if action == "WAIT" else "")
             + f"Roll timing: Thursday of expiry week, immediately once time value is ≤ ${K(pol, 'put_roll_tv_floor'):.2f} "
               "(early-assignment risk); never Friday afternoon. planned_assignments overrides either way.",
             earn=roll_credit if action == "ROLL" else None,
             context={"intrinsic": intrinsic, "time_value": tv, "cost_to_own": cost_to_own, "room": room,
                      "rsi": rsi, "roll_credit": roll_credit, "verdict": verdict})

    # (Re-entry puts after a call assignment were a dedicated Layer-1 card
    # until 2026-09-20. Neel: re-entry is not automatic — the called-away
    # name goes back into the put ranking like any other and is picked when
    # it earns the slot on yield AND does not unbalance the book.)

    # ---------------- Layer 3: short-term puts ----------------
    total_value = sum(h["qty"] * price.get(s, 0) for (_, s), h in holdings.items())
    st_value = sum(h["qty"] * price.get(s, 0) for (_, s), h in holdings.items() if s in short_term)
    st_put_collateral = sum(o["strike"] * 100 * o["contracts"] for o in options
                            if o["type"] == "put" and o["symbol"] in short_term)
    # Three buckets (Neel, 2026-09-20): A long-term shares (80%), B short-
    # term shares (20%), C the put bucket — the margin lines, puts on A + B
    # + a put-only list. The 20% is SHARES ONLY; put collateral never
    # counts toward it, whichever name it is on. `st_exposure` (shares +
    # short-term put collateral) survives only as the what-if for the
    # per-name balance check below: "if this put assigns, how much of B
    # is this one name?"
    st_exposure = st_value + st_put_collateral
    st_pct = (st_value / total_value * 100) if total_value else 0.0
    cap_pct = K(pol, "short_term_cap_pct")

    # Existing exposure per short-term name (holdings + put collateral,
    # every account): a put is a commitment to own MORE of the name, so a
    # name already a big share of the book is skipped, whatever its RSI
    # says (Neel, 2026-09-16: 800 SOXL on the way and V7 asked for more).
    st_by_sym: Dict[str, float] = {}
    for (_, s_), h_ in holdings.items():
        if s_ in short_term or s_ in put_only:
            st_by_sym[s_] = st_by_sym.get(s_, 0.0) + h_["qty"] * price.get(s_, 0)
    for o in options:
        if o["type"] == "put" and (o["symbol"] in short_term or o["symbol"] in put_only):
            st_by_sym[o["symbol"]] = st_by_sym.get(o["symbol"], 0.0) + o["strike"] * 100 * o["contracts"]
    book_total = max(st_exposure, 1.0)
    max_sym_pct = K(pol, "st_max_symbol_pct_of_book")

    # Skew ceiling on the put book itself (Neel, 2026-09-23): "even
    # distribution is not a huge goal — the problem would have been if it
    # was heavily skewed. If 50% of the put money was going to Zoom that
    # would be wrong; I don't see a problem with the current." So the
    # ranking stays purely profit-driven and this is a veto, not another
    # variable to balance: no name may pass put_max_symbol_pct_of_put_book
    # of all put collateral. ZM was 15% of $367K with two more cards
    # queued that would have taken it to 27%.
    put_by_sym: Dict[str, float] = {}
    for o in options:
        if o["type"] == "put":
            put_by_sym[o["symbol"]] = put_by_sym.get(o["symbol"], 0.0) + o["strike"] * 100 * o["contracts"]
    put_book_total = sum(put_by_sym.values())
    max_put_pct = K(pol, "put_max_symbol_pct_of_put_book")

    # Put candidates, one rule for every name (Neel, 2026-09-16): the put
    # delta is the mirror of the call rule — a depressed / oversold name
    # gets a CLOSER put (its further downside is the weaker case), an
    # extended / overbought one a farther put — scaled by the name's own
    # realized volatility. Then rank by return per unit of risk (weekly
    # yield on collateral ÷ volatility), with a bonus for names below
    # their 10-day average, after the concentration cap.
    put_dte = max((next_expiration(today) - today).days, 1)
    if put_dte < int(K(pol, "new_call_min_dte")):
        put_dte += 7
    put_exp = today + timedelta(days=put_dte)
    put_candidates = []
    concentrated = []
    # Every name held, both books (Neel, 2026-09-17: "puts on anything and
    # everything as long as it has high volatility and I can earn"). The
    # concentration cap applies to short-term names (share of the
    # short-term book); a long-term name that assigns just grows the
    # long-term book, which is what it is for.
    held_syms = {s_ for (_, s_) in holdings.keys() if s_ not in ignore}
    put_universe = sorted((long_term | short_term | put_only) & (held_syms | set(price)))
    for sym in put_universe:
        spot = price.get(sym)
        if not spot:
            continue
        # put-only names (bucket C's own list) land in the short-term book
        # if assigned, so they take the same balance check
        book = "short" if sym in short_term else "put-only" if sym in put_only else "long"
        sym_pct = st_by_sym.get(sym, 0.0) / book_total * 100 if book != "long" else 0.0
        if book != "long" and sym_pct >= max_sym_pct:
            concentrated.append(f"{sym} {sym_pct:.0f}% of book B")
            continue
        put_pct = put_by_sym.get(sym, 0.0) / put_book_total * 100 if put_book_total else 0.0
        if put_pct >= max_put_pct:
            concentrated.append(f"{sym} {put_pct:.0f}% of the put book")
            continue
        any_acct = next((h["account_id"] for (_, s), h in holdings.items() if s == sym), None) or "neel_brokerage"
        rsi_ctx = _rsi(db, any_acct, sym)
        rsi = rsi_ctx.get("rsi") if rsi_ctx else None
        vol, vol_src = vol_of(sym)
        vs_sma = _vs_sma_pct(closes.get(sym, []), spot, max(int(K(pol, "vol_lookback_days")) // 2, 5))
        thr = K(pol, "mr_threshold_pct")
        if vs_sma is not None and vs_sma <= -thr:
            base, why = 40, f"{vs_sma:+.1f}% vs 10-day avg → base 40 (depressed: closer put)"
        elif vs_sma is not None and vs_sma >= thr:
            base, why = 20, f"{vs_sma:+.1f}% vs 10-day avg → base 20 (extended: farther put)"
        elif rsi is None:
            base, why = 30, "no RSI on file → base 30"
        elif rsi < K(pol, "st_rsi_low"):
            base, why = 40, f"RSI {rsi:.0f} → base 40"
        elif rsi <= K(pol, "st_rsi_high"):
            base, why = 30, f"RSI {rsi:.0f} → base 30"
        else:
            base, why = 20, f"RSI {rsi:.0f} → base 20"
        if vol:
            ref = K(pol, "vol_reference_pct") / 100
            delta = int(round(max(K(pol, "st_delta_min"), min(K(pol, "st_delta_max"), base * ref / vol))))
            why += f" × {ref * 100:.0f}%/{vol * 100:.0f}% vol → delta {delta}"
            picked = chain_pick(chains, sym, "put", put_exp, delta)
            if picked and picked["mark"]:
                strike, put_px = picked["strike"], picked["mark"]
                why += f" → quoted ${strike:,.2f} (delta {abs(picked['delta']):.2f})"
            else:
                T = put_dte / 365
                strike = float(round(spot * math.exp(-vol * math.sqrt(T) * _z_for_delta(delta / 100))))
                call_px = call_premium(spot, strike, vol, put_dte, 1, RATE_ATM_WEEKLY) / 100
                put_px = max(call_px - spot + strike, 0.0)   # put-call parity, r = 0
        else:
            delta = base
            picked = chain_pick(chains, sym, "put", put_exp, delta)
            if picked and picked["mark"]:
                strike, put_px = picked["strike"], picked["mark"]
                why += f" (no vol on file) → quoted ${strike:,.2f} (delta {abs(picked['delta']):.2f})"
            else:
                why += " (no vol on file — ATM)"
                strike = float(round(spot))
                put_px = weekly_premium(1, spot, RATE_ATM_WEEKLY) / 100
        yld_wk = put_px / strike * 100 * 7 / put_dte if strike else 0.0
        # Score = weekly yield on collateral at the rule's delta. Risk is
        # already in the delta (a 40 is a 40 on every name, and volatile
        # names get a lower one); dividing by volatility again cancelled it
        # and left every name at ~3.7 (Neel, 2026-09-17: IBIT #3 at $61 a
        # contract while MU paid $1,976). Yield is the potential.
        score = yld_wk
        if put_px * 100 < K(pol, "put_min_premium_per_contract"):
            continue  # not worth a slot
        depressed = vs_sma is not None and vs_sma <= -thr
        if depressed:
            score *= K(pol, "put_depressed_bonus")
        put_candidates.append({"symbol": sym, "spot": spot, "rsi": rsi, "vol": vol, "vs_sma": vs_sma, "book": book,
                               "book_pct": sym_pct, "delta": delta, "why": why, "strike": strike,
                               "put_px": put_px, "yield_wk": yld_wk, "score": score, "depressed": depressed,
                               "quote": picked})
    put_candidates.sort(key=lambda c: -c["score"])
    ranking_txt = " > ".join(f"{c['symbol']} {c['score']:.2f}%/wk" for c in put_candidates)

    # collateral coming free today: OTM puts expiring today
    freeing_today: Dict[str, float] = {}
    for o in options:
        if o["type"] == "put" and o["dte"] == 0 and price.get(o["symbol"], 0) >= o["strike"]:
            freeing_today[o["account"]] = freeing_today.get(o["account"], 0.0) + o["strike"] * 100 * o["contracts"]
    # a name picked in one account counts against its share of the book for the next
    reserved: Dict[str, float] = {}
    for acct in sorted(cash, key=_acct_rank):
        c = cash[acct]
        line = lines.get(acct, 0.0)
        capacity = (line + c["cash"] if line else c["cash"]) - c["collateral"] - (c["margin_used"] if line else 0)
        capacity += freeing_today.get(acct, 0.0)
        if capacity < K(pol, "put_min_capacity"):
            continue
        # (Until 2026-09-20 a short-term book at or above 20% blocked every
        # new put. The put bucket is its own thing now, bounded by the
        # margin lines; what keeps B in shape is the per-name balance
        # check and the Layer-4 notice when B drifts over.)
        # best yield that FITS, sized to the capacity, then the next with what is left
        picks, remaining = [], capacity
        for p in put_candidates:
            if p["strike"] * 100 > remaining:
                continue
            if p["book"] == "short":
                already = st_by_sym.get(p["symbol"], 0.0) + reserved.get(p["symbol"], 0.0)
                if already / book_total * 100 >= max_sym_pct:
                    continue  # picked elsewhere this run, now at the cap
            n = min(int(remaining // (p["strike"] * 100)), int(K(pol, "put_max_contracts")))
            # trim so this name stays under the put-book skew ceiling, counting
            # what earlier accounts already took this run
            held_put = put_by_sym.get(p["symbol"], 0.0) + reserved.get(p["symbol"], 0.0)
            while n > 0:
                add = p["strike"] * 100 * n
                if (held_put + add) / max(put_book_total + add, 1.0) * 100 <= max_put_pct:
                    break
                n -= 1
            if n == 0:
                continue
            picks.append((p, n)); remaining -= p["strike"] * 100 * n
            reserved[p["symbol"]] = reserved.get(p["symbol"], 0.0) + p["strike"] * 100 * n
            if len(picks) == 2 or remaining < K(pol, "put_min_capacity"):
                break
        for rank, (p, n) in enumerate(picks, 1):
            est = int(p["put_px"] * 100 * n)
            card(3, "SELL PUT", acct, p["symbol"],
                 f"{p['symbol']}: sell {n} put{'s' if n > 1 else ''} at ~${p['strike']:,.0f} (delta {p['delta']}, #{rank} by return/risk"
                 + (", depressed" if p["depressed"] else "")
                 + (f", {p['book_pct']:.0f}% of the short-term book)" if p["book"] == "short"
                    else f", put-only name — {p['book_pct']:.0f}% of the short-term book if assigned)" if p["book"] == "put-only"
                    else ", long-term name)"),
                 f"exp {_fmt_exp(put_exp)} · collateral ${p['strike'] * 100 * n:,.0f} of ${capacity:,.0f} undeployed"
                 + (" (margin-backed)" if line else " (cash-secured)")
                 + f" · est ${est:,}" + (" · quoted" if p.get("quote") else "")
                 + spread_note(p.get("quote"))
                 + f" · {p['yield_wk']:.1f}%/wk on collateral · {p['why']}",
                 "Layer 3: puts on every name you hold, both books, against cash and margin. The put delta is the mirror of the "
                 "call rule — a depressed or oversold name gets a closer put, an extended one a farther put — scaled "
                 "by the name's own volatility, so risk is in the delta. Candidates are then ranked by weekly yield on "
                 f"collateral at that delta (×{K(pol, 'put_depressed_bonus'):.2f} when ≥{K(pol, 'mr_threshold_pct'):.0f}% below the 10-day average), "
                 "and the best yield that fits the account's capacity is sized to it: "
                 f"{ranking_txt}. Names at or above {max_sym_pct:.0f}% of book B, or {max_put_pct:.0f}% of the put book, are skipped"
                 + (f" (today: {', '.join(concentrated)})" if concentrated else "") + ". "
                 "Capacity = margin line + cash − open collateral − margin already drawn.",
                 earn=est,
                 context={"capacity": capacity, "st_pct": round(st_pct, 1), "score": round(p["score"], 2),
                          "delta": p["delta"], "vol": p["vol"], "vs_sma": p["vs_sma"]})

    # ---------------- Layer 4: recovery state ----------------
    state_accounts = []
    for acct in sorted(cash, key=_acct_rank):
        c = cash[acct]
        line = lines.get(acct)
        drawn = c["margin_used"] if line else 0.0
        state_accounts.append({"account": acct, "line": line, "margin_used": c["margin_used"],
                               "collateral": c["collateral"], "cash": c["cash"], "as_of": str(c["as_of"])})
        if line and drawn > 1000:
            card(4, "NOTICE", acct, "—",
                 f"Margin drawn by ${drawn:,.0f} in {acct}",
                 f"line ${line:,.0f} · collateral reserved for open puts ${c['collateral']:,.0f} · cash ${c['cash']:,.0f}",
                 f"Margin is for puts. ${drawn:,.0f} of borrowed money is financing stock instead. Selling about "
                 f"${drawn:,.0f} of stock returns this account to normal — which position is your call, and there is "
                 f"no hurry: the cost of staying here is put income (~2%/mo) becoming call income (~1%/mo) on that amount.")
    lt_value = total_value - st_value
    other_value = sum(h["qty"] * price.get(s, 0) for (_, s), h in holdings.items()
                      if s not in short_term and s not in long_term and s not in ignore)
    lt_pct = (lt_value / total_value * 100) if total_value else 0.0
    if st_pct > cap_pct:
        card(4, "NOTICE", "Portfolio", "—",
             f"Short-term book is {st_pct:.1f}% — above the {cap_pct}% target",
             f"short-term shares ${st_value:,.0f} of ${total_value:,.0f} (put collateral on short-term names, not counted: ${st_put_collateral:,.0f})",
             "80/20 is the healthy state, shares only. It drifts back as short-term calls assign (their normal exit); "
             "the per-name balance check keeps new puts from piling onto the names already large in the book.")

    for L in layers.values():
        L.sort(key=lambda c: (_acct_rank(c["account"]), c["symbol"]))

    return {
        "as_of": today.isoformat(),
        "policy_status": pol["status"],
        "data_as_of": {"options": str(max((o["as_of"] for o in options), default=None)),
                       "cash": str(max((c["as_of"] for c in cash.values()), default=None))},
        "split": {"long_term_pct": round(lt_pct, 1), "short_term_pct": round(st_pct, 1),
                  "other_pct": round(other_value / total_value * 100, 1) if total_value else 0.0,
                  "target": pol["split_target"], "total_value": round(total_value),
                  "short_term_value": round(st_value), "short_term_put_collateral": round(st_put_collateral)},
        "accounts": state_accounts,
        "lists": {"long_term": sorted(long_term), "short_term": sorted(short_term),
                  "put_only": sorted(put_only)},
        "layers": [
            {"n": 1, "name": "Long-term calls", "items": layers[1]},
            {"n": 2, "name": "Short-term calls", "items": layers[2]},
            {"n": 3, "name": "Short-term puts", "items": layers[3]},
            {"n": 4, "name": "Recovery", "items": layers[4]},
        ],
        "counts": {str(k): len(v) for k, v in layers.items()},
    }


# ---------------------------------------------------------------------------
# Production adapter — V7 in the shape the Option Execution page and the
# notification email already consume (Neel, 2026-09-16: "put this in
# production, both in the UI and in the email"). Nothing downstream
# changes; only the engine behind it.
# ---------------------------------------------------------------------------

_PRIORITY_BY_ACTION = {
    "LET ASSIGN": "high", "NOTICE": "high", "ROLL": "high", "BUY BACK": "medium",
    "SELL": "medium", "SELL PUT": "medium", "REVIEW": "medium",
    "WAIT": "low", "HOLD": "low", "LET EXPIRE": "low",
}


def _v6_shape(card: Dict, layer_name: str, today: date) -> Dict:
    ctx = dict(card.get("context") or {})
    ctx["layer"] = card["layer"]
    ctx["layer_name"] = layer_name
    if card.get("assumption"):
        ctx["assumption"] = card["assumption"]
    # the page's RSI chip and "wait" styling read context.entry_timing
    if ctx.get("rsi") is not None:
        ctx.setdefault("entry_timing", {"rsi": ctx["rsi"], "wait": card["action"] == "WAIT"})
    priority = _PRIORITY_BY_ACTION.get(card["action"], "medium")
    # a roll that is due NOW (time-value floor / expiry day) is urgent
    if card["action"] == "ROLL" and ("now" in card["title"] or "today" in card["title"]):
        priority = "urgent"
    action = {"SELL PUT": "SELL", "LET ASSIGN": "ASSIGN", "LET EXPIRE": "HOLD", "BUY BACK": "CLOSE",
              "NOTICE": "WATCH", "REVIEW": "WATCH"}.get(card["action"], card["action"])
    return {
        "id": card["id"], "priority": priority, "action": action,
        "engine": card["layer"], "rule": f"L{card['layer']} {layer_name}",
        "title": card["title"], "account": card["account"], "symbol": card["symbol"],
        "detail": f"{card['title']} · {card['detail']}" if card["detail"] else card["title"],
        "why": card["why"], "earn": card.get("earn"), "context": ctx,
    }


def build_action_queue(db: Session) -> Dict:
    """V7 in V6's queue contract: {generated_at, data_as_of, week_ending,
    engine_version, summary, items, positions}. The positions board is
    V6's (it is data, not recommendations)."""
    from app.modules.strategies.v6_engine import build_action_queue as _v6
    from app.shared.services.option_premium import friday_on_or_after
    v7 = build_v7_queue(db)
    v6 = _v6(db)   # for the positions board only
    today = date.today()
    items = [_v6_shape(c, L["name"], today) for L in v7["layers"] for c in L["items"]]
    order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
    items.sort(key=lambda i: (order[i["priority"]], _acct_rank(i["account"]), i["symbol"]))
    summary = {p: sum(1 for i in items if i["priority"] == p) for p in order}
    return {
        "generated_at": str(today), "data_as_of": v6.get("data_as_of"),
        "week_ending": str(friday_on_or_after(today)), "engine_version": "v7",
        "premium": premium_summary(db, today),
        "summary": {**summary, "total": len(items)},
        "items": items, "positions": v6.get("positions", []),
        "v7": {"split": v7["split"], "accounts": v7["accounts"], "lists": v7["lists"]},
    }


def build_live_action_queue(db: Session) -> Dict:
    """The queue the page and the email use — V7 or V6 per
    settings.LIVE_STRATEGY_ENGINE."""
    from app.core.config import settings
    if (settings.LIVE_STRATEGY_ENGINE or "v7").lower() == "v6":
        from app.modules.strategies.v6_engine import build_action_queue as _v6
        return _v6(db)
    return build_action_queue(db)


def premium_summary(db: Session, today: Optional[date] = None) -> Dict:
    """Net option premium — every STO minus every BTC — for today and the
    week to date (Monday onward), all accounts, with per-account detail.
    Neel, 2026-09-17: "the total return of the effort of the day" in every
    scan email, progressing through the day. Only fills the sync has
    imported count, so a scan reflects the sync before it.
    """
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    rows = db.execute(text("""
        SELECT a.account_name, t.transaction_date, t.transaction_type, t.amount
        FROM investment_transactions t JOIN investment_accounts a ON a.account_id = t.account_id
        WHERE t.transaction_type IN ('STO', 'BTC') AND t.transaction_date BETWEEN :m AND :t
    """), {"m": monday, "t": today}).fetchall()
    def agg(rs):
        sto = sum(float(r.amount) for r in rs if r.transaction_type == "STO")
        btc = sum(float(r.amount) for r in rs if r.transaction_type == "BTC")   # negative
        return {"sold": round(sto), "bought_back": round(-btc), "net": round(sto + btc),
                "fills": len(rs), "accounts": sorted({r.account_name for r in rs}, key=_acct_rank)}
    today_rows = [r for r in rows if r.transaction_date == today]
    by_acct = {}
    for r in today_rows:
        by_acct.setdefault(r.account_name, []).append(r)
    return {
        "today": {**agg(today_rows), "date": today.isoformat(),
                  "by_account": {a: agg(rs)["net"] for a, rs in sorted(by_acct.items(), key=lambda kv: _acct_rank(kv[0]))}},
        "week": {**agg(rows), "since": monday.isoformat()},
    }
