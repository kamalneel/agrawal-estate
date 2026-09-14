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
)

logger = logging.getLogger(__name__)

_POLICY_V2 = Path(__file__).resolve().parents[4] / "data" / "policy_v2.json"

#: A call whose mark is at most this fraction of what it was sold for is
#: "mostly time value gone" — the dip buy-back / profit-take trigger.
DIP_BUYBACK_CAPTURE = 0.60
#: Roll before ex-div this many days ahead, and go this far out.
EXDIV_LOOKAHEAD_DAYS = 10
EXDIV_ROLL_WEEKS = 4
#: Below this many DTE an ITM short-term call is treated as "at expiry".
SHORT_TERM_LET_ASSIGN_DTE = 2


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


def _short_term_delta(rsi: Optional[float], pol: Dict) -> int:
    """Delta 20-40 picked by RSI (policy_v2 short_term.calls.rsi_to_delta).
    No RSI on file -> the middle of the window."""
    m = pol["short_term"]["calls"]["rsi_to_delta"]
    if rsi is None:
        return 30
    if rsi < 40:
        return m["below_40"]
    if rsi <= 55:
        return m["40_to_55"]
    return m["above_55"]


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

        if book == "long":
            lt = pol["long_term"]["calls"]
            if sym == "TSLA":
                otm, delta_txt = lt["otm_pct_tsla"], "10-12"
                wait = not (rsi is not None and rsi > 75)
                wait_reason = (f"RSI {rsi:.0f} — TSLA carve-out fires only above 75" if rsi is not None
                               else "no RSI on file — TSLA carve-out needs RSI > 75")
            else:
                otm = lt["otm_pct_sheltered"] if sheltered(acct) else lt["otm_pct_taxable"]
                delta_txt = "15" if sheltered(acct) else "10-15"
                wait = bool(rsi_ctx and rsi_ctx.get("wait"))
                wait_reason = (rsi_ctx or {}).get("reason") or ""
            strike = strike_for(spot, otm)
            floor = ""
            if cost_ps and strike < cost_ps:
                strike, floor = cost_ps, " (raised to cost-basis floor)"
            est = weekly_premium(n, spot, RATE_TIER1_WEEKLY)
            action = "WAIT" if wait else "SELL"
            card(1, action, acct, sym,
                 f"{sym}: {'hold off — ' if wait else ''}sell {n} call{'s' if n > 1 else ''} at delta {delta_txt}",
                 f"strike ~${strike:,.0f}{floor} · exp {_fmt_exp(exp)} · est ${est:,} this week"
                 + (f" · RSI {rsi:.0f}" if rsi is not None else ""),
                 (f"{wait_reason}. " if wait else "")
                 + "Long-term book: income without getting called away. Delta 10-15 by the V7 policy; "
                   "the shares are never sold, so the strike stays far enough out that assignment is unlikely.",
                 earn=None if wait else est,
                 context={"book": "long", "rsi": rsi, "spot": spot, "uncovered": int(uncovered)})
        else:
            st = pol["short_term"]["calls"]
            delta = _short_term_delta(rsi, pol)
            otm = st["otm_pct_by_delta"][str(delta)]
            strike = strike_for(spot, otm)
            floor = ""
            if cost_ps and strike < cost_ps:
                strike, floor = cost_ps, " (raised to cost-basis floor)"
            # premium scales between the far-OTM and ATM rates with delta
            rate = RATE_TIER1_WEEKLY + (RATE_ATM_WEEKLY - RATE_TIER1_WEEKLY) * (delta - 10) / 40
            est = weekly_premium(n, spot, rate)
            rsi_note = (f"RSI {rsi:.0f} → delta {delta}" if rsi is not None
                        else f"no RSI on file → delta {delta} (middle of the window)")
            card(2, "SELL", acct, sym,
                 f"{sym}: sell {n} call{'s' if n > 1 else ''} at delta {delta}",
                 f"strike ~${strike:,.0f}{floor} · exp {_fmt_exp(exp)} · est ${est:,} this week · {rsi_note}",
                 "Short-term book: calls between delta 20 and 40, the technicals pick the number — "
                 "low RSI means the bounce is coming, so nearer 20; never at the money. "
                 "Same rule whether the shares were assigned or bought.",
                 earn=est,
                 assumption=("cost-basis floor kept from V6 (never sell at a loss if assigned) — not discussed"
                             if floor else None),
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
                exdiv_soon = ex_date is not None and 0 <= (ex_date - today).days <= EXDIV_LOOKAHEAD_DAYS
                roll_credit = weekly_premium(n, spot, RATE_TIER1_WEEKLY)  # next week's time value, rough
                if exdiv_soon and (o["dte"] is None or o["expiration"] < ex_date + timedelta(days=EXDIV_ROLL_WEEKS * 7)):
                    out = ex_date + timedelta(days=EXDIV_ROLL_WEEKS * 7)
                    card(1, "ROLL", acct, sym,
                         f"{sym} ${k:,.0f} call ITM — ex-dividend {_fmt_exp(ex_date)}: roll {EXDIV_ROLL_WEEKS} weeks out, same strike",
                         f"{n} contract{'s' if n > 1 else ''} · ${intrinsic:,.2f} in the money · "
                         f"time value ${tv:,.2f}" if tv is not None else f"{n} contract{'s' if n > 1 else ''} · ${intrinsic:,.2f} in the money",
                         f"Rule 3: a deep-ITM weekly's time value falls below the ${ex['dividend']:.2f} dividend and gets "
                         f"exercised early the day before ex-div ({ex_date:%b %-d}). A {EXDIV_ROLL_WEEKS}-week contract "
                         f"carries enough time value to survive it. Same strike, still a credit. Buy back on the dip after.",
                         context={"exdiv": ex["date"], "roll_to": out.isoformat()})
                else:
                    card(1, "ROLL", acct, sym,
                         f"{sym} ${k:,.0f} call ITM — roll to next week, same strike",
                         f"{n} contract{'s' if n > 1 else ''} · exp {_fmt_exp(o['expiration'])} · ${intrinsic:,.2f} in the money"
                         + (f" · time value ${tv:,.2f}" if tv is not None else "")
                         + f" · roll credit est ${roll_credit:,}",
                         "Rule 1: never pay intrinsic to get out. Roll weekly at the same strike for a credit and "
                         "wait for the dip — what goes up comes down. One-week cadence so a short dip can be used "
                         "the week it happens (rule 2: buy back on the dip, time value is not penalty).",
                         earn=roll_credit,
                         context={"intrinsic": intrinsic, "time_value": tv})
            else:
                # OTM: the dip buy-back / profit take
                if mark is not None and o["original"] and o["original"] > 0 and mark <= o["original"] * (1 - DIP_BUYBACK_CAPTURE) \
                        and (o["dte"] is None or o["dte"] >= 2):
                    cost = mark * 100 * n
                    # what the replacement call would bring — the other half of the decision
                    resell = weekly_premium(n, spot, RATE_TIER1_WEEKLY)
                    card(1, "BUY BACK", acct, sym,
                         f"{sym} ${k:,.0f} call — {100 * (1 - mark / o['original']):.0f}% captured: buy back for ${cost:,.0f}, resell est ${resell:,}",
                         f"{n} contract{'s' if n > 1 else ''} · mark ${mark:,.2f} vs ${o['original']:,.2f} sold · "
                         f"kept ${(o['original'] - mark) * 100 * n:,.0f} of ${o['original'] * 100 * n:,.0f} · exp {_fmt_exp(o['expiration'])}",
                         f"Rule 2: time value is not penalty — but it is not free. The ${cost:,.0f} left in this contract "
                         f"decays to zero by expiry on its own; paying it now buys the shares back early so a new call "
                         f"(est ${resell:,} for next week at delta 10-15) can be sold on the bounce. Worth it only if the "
                         f"new call clears the ${cost:,.0f}.",
                         earn=max(resell - int(cost), 0),
                         context={"captured_pct": round(100 * (1 - mark / o["original"]), 1), "buyback_cost": cost, "resell_est": resell})
        else:
            if itm and o["dte"] is not None and o["dte"] <= SHORT_TERM_LET_ASSIGN_DTE:
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
    cap_pct = pol["split_target"]["short_term_pct"]
    lines = {MARGIN_ID_TO_NAME.get(k, k): v for k, v in pol["margin"]["lines"].items()}

    put_candidates = []
    for sym in sorted(short_term):
        spot = price.get(sym)
        if not spot:
            continue
        any_acct = next((h["account_id"] for (_, s), h in holdings.items() if s == sym), None)
        rsi_ctx = _rsi(db, any_acct, sym) if any_acct else None
        rsi = rsi_ctx.get("rsi") if rsi_ctx else None
        fav = "favourable" if (rsi is not None and rsi < 50) else "unfavourable" if (rsi is not None and rsi > 65) else "neutral"
        put_candidates.append({"symbol": sym, "spot": spot, "rsi": rsi, "entry": fav})
    put_candidates.sort(key=lambda c: ({"favourable": 0, "neutral": 1, "unfavourable": 2}[c["entry"]], -(c["spot"])))

    for acct in sorted(cash, key=_acct_rank):
        c = cash[acct]
        line = lines.get(acct, 0.0)
        capacity = (line + c["cash"] if line else c["cash"]) - c["collateral"] - (c["margin_used"] if line else 0)
        if capacity < 5000:
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
            n = min(n, 2)
            order = atm_order(n, p["spot"])
            card(3, "SELL PUT", acct, p["symbol"],
                 f"{p['symbol']}: sell {n} put{'s' if n > 1 else ''} at ~${order['strike']:,.0f} ({p['entry']} entry"
                 + (f", RSI {p['rsi']:.0f}" if p["rsi"] is not None else "") + ")",
                 f"collateral ${order['strike'] * 100 * n:,.0f} of ${capacity:,.0f} undeployed"
                 + (" (margin-backed)" if line else " (cash-secured)") + f" · est ${order['est_premium']:,} this week",
                 "Layer 3: puts on the short-term list against cash and margin to maximise option income. "
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
