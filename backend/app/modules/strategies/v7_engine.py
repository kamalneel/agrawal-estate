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
        return {"entry": e, "target": target, "days": days, "deadline_days": deadline_days,
                "resolved": moved or expired, "how": "moved" if moved else "expired" if expired else None,
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
    long_term = set(pol["long_term"]["symbols"]) | set(pol["long_term"].get("undecided", []))
    short_term = set(pol["short_term"]["symbols"])
    exdiv = pol.get("ex_dividend_estimates", {})
    ignore = _load_policy_ignore_list()

    holdings, price, acct_type, acct_id = _holdings(db)
    options = _open_options(db, today)
    cash = _cash(db)
    reentry = _recent_call_assignments(db, today - timedelta(days=14))
    closes = _closes(db)
    buybacks = _recent_buybacks(db, today - timedelta(days=10))
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
            vol = _realized_vol(closes.get(sym, []), int(K(pol, "vol_lookback_days")))
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
                wait = bool(rsi_ctx and rsi_ctx.get("wait"))
                wait_reason = (rsi_ctx or {}).get("reason") or ""
            strike = strike_for_delta(spot, target_delta, vol, dte_new, 0.055)
            floor = ""
            if K(pol, "cost_floor_enabled") and cost_ps and strike < cost_ps:
                strike, floor = cost_ps, " (raised to cost-basis floor)"
            est = call_premium(spot, strike, vol, dte_new, n, RATE_TIER1_WEEKLY)
            action = "WAIT" if wait else "SELL"
            card(1, action, acct, sym,
                 f"{sym}: {'hold off — ' if wait else ''}sell {n} call{'s' if n > 1 else ''} at delta {delta_txt}",
                 f"strike ~${strike:,.0f}{floor} · exp {_fmt_exp(exp)} · est ${est:,}"
                 + (f" · vol {vol * 100:.0f}%" if vol else "")
                 + (f" · RSI {rsi:.0f}" if rsi is not None else ""),
                 resolved_note + (f"{wait_reason}. " if wait else "")
                 + bounce_note
                 + "Long-term book: income without getting called away. Delta 10-15 by the V7 policy; "
                   "the shares are never sold, so the strike stays far enough out that assignment is unlikely.",
                 earn=None if wait else est,
                 context={"book": "long", "rsi": rsi, "spot": spot, "uncovered": int(uncovered)})
        else:
            vol = _realized_vol(closes.get(sym, []), int(K(pol, "vol_lookback_days")))
            vs_sma = _vs_sma_pct(closes.get(sym, []), spot, max(int(K(pol, "vol_lookback_days")) // 2, 5))
            delta, rsi_note = _short_term_delta(rsi, pol, vol, vs_sma)
            dte_new = max((exp - today).days, 1)
            strike = strike_for_delta(spot, delta, vol, dte_new, 0.025)
            floor = ""
            if K(pol, "cost_floor_enabled") and cost_ps and strike < cost_ps:
                strike, floor = cost_ps, " (raised to cost-basis floor)"
            rate = RATE_TIER1_WEEKLY + (RATE_ATM_WEEKLY - RATE_TIER1_WEEKLY) * (delta - 10) / 40
            est = call_premium(spot, strike, vol, dte_new, n, rate)
            card(2, "SELL", acct, sym,
                 f"{sym}: sell {n} call{'s' if n > 1 else ''} at delta {delta}",
                 f"strike ~${strike:,.0f}{floor} · exp {_fmt_exp(exp)} · est ${est:,} · {rsi_note}",
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
                    if floor_hit:
                        action, when = "ROLL", f"now — time value ${tv:,.2f} is at the ${K(pol, 'roll_tv_floor'):.2f} early-exercise floor"
                    elif due_today:
                        action, when = "ROLL", "today" + (" (morning, not afternoon)" if dte == 0 else "")
                    else:
                        action, when = "WAIT", roll_day
                    tv_txt = f" · time value left ${tv:,.2f}" if tv is not None else ""
                    card(1, action, acct, sym,
                         f"{sym} ${k:,.0f} call ITM — roll {when}, same strike" if action == "ROLL"
                         else f"{sym} ${k:,.0f} call ITM — roll {roll_day}, not yet",
                         f"{n} contract{'s' if n > 1 else ''} · exp {_fmt_exp(o['expiration'])} · ${intrinsic:,.2f} in the money"
                         + tv_txt + f" · roll credit est ${roll_credit:,}"
                         + (f" · RSI {rsi:.0f}" if rsi is not None else ""),
                         "Rule 1: never pay intrinsic to get out; roll weekly at the same strike for a credit. "
                         "The credit is next week's time value minus this week's, and this week's decays fastest "
                         "at the end — so later in the week pays more, and every un-rolled day is a day the dip "
                         "can settle it for free (an early roll leaves an at-the-money call to buy back at max "
                         "time value when the dip comes). Thursday by default, Friday morning when RSI is high, "
                         f"immediately once the expiring contract's time value is ≤ ${K(pol, 'roll_tv_floor'):.2f} "
                         "(nothing left to wait for, early-exercise risk rising). Never Friday afternoon.",
                         earn=roll_credit if action == "ROLL" else None,
                         context={"intrinsic": intrinsic, "time_value": tv, "roll_day": roll_day, "rsi": rsi,
                                  "floor_hit": floor_hit})
            else:
                # OTM: the dip buy-back / profit take
                rw = _runaway_status(pol, sym, spot, today)
                if rw and not rw["resolved"] and mark is not None:
                    # A runaway thesis is about DISTANCE (Neel, 2026-09-15): the
                    # cap that gets bought back is the one close enough to take
                    # the shares on the first day of the move. A cap far enough
                    # above is room for the run and stays — until the price
                    # climbs into the cushion, which this re-checks every run.
                    cushion = K(pol, "runaway_cushion_pct")
                    gap_pct = (k / spot - 1) * 100
                    if gap_pct <= cushion:
                        cost = mark * 100 * n
                        card(1, "BUY BACK", acct, sym,
                             f"{sym} ${k:,.0f} call — runaway thesis, only {gap_pct:.1f}% above spot: buy back to uncap, ${cost:,.0f}",
                             f"{n} contract{'s' if n > 1 else ''} · mark ${mark:,.2f} vs ${o['original'] or 0:,.2f} sold · exp {_fmt_exp(o['expiration'])} · "
                             f"cushion {cushion:.0f}% · release at ${rw['target']:,.2f} or in {rw['deadline_days'] - rw['days']} trading days",
                             f"{rw['entry']['reason']} This cap is inside the {cushion:.0f}% cushion — it would take the shares "
                             f"on the first day of the move. A cap further out is left alone.",
                             context={"runaway": True, "buyback_cost": cost, "gap_pct": round(gap_pct, 1)})
                        continue
                    # outside the cushion: the call is room for the run — fall through to normal handling
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
                    up_day = dte > 1 and move is not None and move >= K(pol, "rule_a_up_day_pct")
                    td = K(pol, "lt_delta_tsla") if sym == "TSLA" else (K(pol, "lt_delta_sheltered") if sheltered(acct) else K(pol, "lt_delta_taxable"))
                    vol = _realized_vol(closes.get(sym, []), int(K(pol, "vol_lookback_days")))
                    nxt = strike_for_delta(spot, td, vol, 7, 0.055)
                    est = call_premium(spot, nxt, vol, 7, n, RATE_TIER1_WEEKLY)
                    roll_now = dte == 0 or up_day
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
            if itm and o["dte"] is not None and o["dte"] <= int(K(pol, 'st_let_assign_dte')):
                card(2, "LET ASSIGN", acct, sym,
                     f"{sym} ${k:,.0f} call ITM at expiry — let the shares go",
                     f"{n} contract{'s' if n > 1 else ''} · exp {_fmt_exp(o['expiration'])} · ${spot - k:,.2f} in the money",
                     "Short-term book: assignment is acceptable; re-enter with a put afterwards.",
                     assumption="Neel has not stated the stuck-call rule for short-term names. Preview assumes let-assign.")
            elif itm:
                card(2, "HOLD", acct, sym,
                     f"{sym} ${k:,.0f} call ITM — hold, decide at expiry",
                     f"{n} contract{'s' if n > 1 else ''} · exp {_fmt_exp(o['expiration'])} · ${spot - k:,.2f} in the money",
                     "Short-term book. If still ITM at expiry it is let go (see assumption).",
                     assumption="Short-term stuck-call rule not stated; preview holds until expiry.")

    # ---------------- Layer 1: re-entry puts on long-term names ----------------
    for a in reentry:
        if a["symbol"] not in long_term:
            continue
        spot = price.get(a["symbol"])
        if not spot:
            continue
        n = a["contracts"]
        order = atm_order(n, spot)
        card(1, "SELL PUT", a["account"], a["symbol"],
             f"{a['symbol']}: {n * 100:,} shares were called away {a['date']:%-m/%-d} — sell {n} put{'s' if n > 1 else ''} to re-enter",
             f"strike ~${order['strike']:,.0f} · est ${order['est_premium']:,} this week · (called at ${a['strike']:,.0f})",
             "The one put allowed on a long-term name: re-entry after a call assignment. If assigned, the "
             "shares are simply held — no aggressive calls.",
             earn=order["est_premium"])

    # ---------------- Layer 3: short-term puts ----------------
    total_value = sum(h["qty"] * price.get(s, 0) for (_, s), h in holdings.items())
    st_value = sum(h["qty"] * price.get(s, 0) for (_, s), h in holdings.items() if s in short_term)
    st_put_collateral = sum(o["strike"] * 100 * o["contracts"] for o in options
                            if o["type"] == "put" and o["symbol"] in short_term)
    st_exposure = st_value + st_put_collateral
    st_pct = (st_exposure / (total_value + st_put_collateral) * 100) if total_value else 0.0
    cap_pct = K(pol, "short_term_cap_pct")
    lines = {MARGIN_ID_TO_NAME.get(k, k): v for k, v in pol["margin"]["lines"].items()}

    # Existing exposure per short-term name (holdings + put collateral,
    # every account): a put is a commitment to own MORE of the name, so a
    # name already a big share of the book is skipped, whatever its RSI
    # says (Neel, 2026-09-16: 800 SOXL on the way and V7 asked for more).
    st_by_sym: Dict[str, float] = {}
    for (_, s_), h_ in holdings.items():
        if s_ in short_term:
            st_by_sym[s_] = st_by_sym.get(s_, 0.0) + h_["qty"] * price.get(s_, 0)
    for o in options:
        if o["type"] == "put" and o["symbol"] in short_term:
            st_by_sym[o["symbol"]] = st_by_sym.get(o["symbol"], 0.0) + o["strike"] * 100 * o["contracts"]
    book_total = max(st_exposure, 1.0)
    max_sym_pct = K(pol, "st_max_symbol_pct_of_book")

    put_candidates = []
    concentrated = []
    for sym in sorted(short_term):
        spot = price.get(sym)
        if not spot:
            continue
        sym_pct = st_by_sym.get(sym, 0.0) / book_total * 100
        if sym_pct >= max_sym_pct:
            concentrated.append(f"{sym} {sym_pct:.0f}%")
            continue
        any_acct = next((h["account_id"] for (_, s), h in holdings.items() if s == sym), None)
        rsi_ctx = _rsi(db, any_acct, sym) if any_acct else None
        rsi = rsi_ctx.get("rsi") if rsi_ctx else None
        fav = ("favourable" if (rsi is not None and rsi < K(pol, "put_rsi_favourable")) else
               "unfavourable" if (rsi is not None and rsi > K(pol, "put_rsi_unfavourable")) else "neutral")
        put_candidates.append({"symbol": sym, "spot": spot, "rsi": rsi, "entry": fav, "book_pct": sym_pct})
    put_candidates.sort(key=lambda c: ({"favourable": 0, "neutral": 1, "unfavourable": 2}[c["entry"]], c["book_pct"], -(c["spot"])))

    for acct in sorted(cash, key=_acct_rank):
        c = cash[acct]
        line = lines.get(acct, 0.0)
        capacity = (line + c["cash"] if line else c["cash"]) - c["collateral"] - (c["margin_used"] if line else 0)
        if capacity < K(pol, "put_min_capacity"):
            continue
        if st_pct >= cap_pct:
            card(3, "HOLD", acct, "—",
                 f"No new short-term put — short-term book is {st_pct:.1f}% of the portfolio (cap {cap_pct}%)",
                 f"undeployed capacity ${capacity:,.0f}",
                 "The 20% cap, not judgement per name, is what bounds the risk to the long-term shares that "
                 "secure the margin. Capacity waits until a short-term position leaves.")
            continue
        picks = [p for p in put_candidates if p["spot"] * 100 <= capacity][:2]
        for p in picks:
            n = max(1, int(capacity // (p["spot"] * 100)))
            n = min(n, int(K(pol, "put_max_contracts")))
            order = atm_order(n, p["spot"])
            card(3, "SELL PUT", acct, p["symbol"],
                 f"{p['symbol']}: sell {n} put{'s' if n > 1 else ''} at ~${order['strike']:,.0f} ({p['entry']} entry"
                 + (f", RSI {p['rsi']:.0f}" if p["rsi"] is not None else "") + f", {p['book_pct']:.0f}% of the book)",
                 f"collateral ${order['strike'] * 100 * n:,.0f} of ${capacity:,.0f} undeployed"
                 + (" (margin-backed)" if line else " (cash-secured)") + f" · est ${order['est_premium']:,} this week",
                 "Layer 3: puts on the short-term list against cash and margin to maximise option income. "
                 "Ranked by RSI entry, then by how little of the book the name already is — a put is a commitment "
                 f"to own more, so names at or above {max_sym_pct:.0f}% of the book are skipped"
                 + (f" (today: {', '.join(concentrated)})" if concentrated else "") + ". "
                 "Capacity = margin line + cash − open collateral − margin already drawn.",
                 earn=order["est_premium"],
                 assumption="Put strike: V6's ATM whole-dollar kept — Neel has not stated a put delta.",
                 context={"capacity": capacity, "st_pct": round(st_pct, 1)})

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
             f"short-term ${st_value:,.0f} held + ${st_put_collateral:,.0f} put collateral of ${total_value:,.0f}",
             "80/20 is the healthy state. No new short-term puts until it drifts back; nothing else to do.")

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
                  "undecided": pol["long_term"].get("undecided", [])},
        "layers": [
            {"n": 1, "name": "Long-term calls", "items": layers[1]},
            {"n": 2, "name": "Short-term calls", "items": layers[2]},
            {"n": 3, "name": "Short-term puts", "items": layers[3]},
            {"n": 4, "name": "Recovery", "items": layers[4]},
        ],
        "counts": {str(k): len(v) for k, v in layers.items()},
    }
