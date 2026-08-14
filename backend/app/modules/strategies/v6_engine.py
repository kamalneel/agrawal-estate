"""V6 Action Queue engine — Stage 1: Engines 4 (stuck) + 1 (uncovered calls).

One feed, two renderers (see docs/OPTIONS-EXECUTION-PAGE-SPEC.md): this
module produces the queue the Options Execution page renders in full and
the email notification renders as its urgent/high slice. Item context
keys match notification_organizer's schema.

Decision tables are transcribed from docs/OPTIONS-STRATEGY-V6-ENGINES.md
(V6.1). Runs entirely off synced data — no external calls.
"""
import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.strategies.technical_signals import (
    get_entry_timing, get_roll_streak, _index_roll_transactions, _walk_roll_chain,
)
# Strike/premium heuristics are shared with the Investments allocation plan —
# one definition so the two pages cannot quote different numbers for the same
# symbol. See app/shared/services/option_premium.py.
from app.shared.services.option_premium import (
    OTM_ATM, OTM_TIER1_SHELTERED, OTM_TIER1_TAXABLE, OTM_TSLA,
    RATE_ATM_WEEKLY, RATE_TIER1_WEEKLY, strike_for, weekly_premium,
)

# GOOG (Class C) and GOOGL (Class A) are the same company (Alphabet) —
# both get Core/Tier-1 treatment. Caught 2026-07-22: GOOG was falling
# through to Tier-2 wheel logic (ATM strike, assignment-friendly) purely
# because only "GOOGL" was listed, even though it's the identical durable.
# AMD moved here 2026-07-23 on Neel's explicit override (was classified
# Inventory 2026-07-22 based on market cap/trading history — his call to
# move it back, not a correction of that analysis).
TIER1 = {"AAPL", "MSFT", "NVDA", "AVGO", "GOOGL", "GOOG", "AMZN", "META", "LLY", "AMD"}
NON_TAXABLE_TYPES = {"ira", "roth_ira", "traditional_ira", "401k", "hsa", "retirement"}
CANONICAL_ORDER = ["Neel's Brokerage", "Neel's Retirement", "Neel's Roth IRA",
                   "Jaya's Brokerage", "Jaya's IRA", "Jaya's Roth IRA",
                   "Alisha's Brokerage", "Agrawal Family HSA"]
MARGIN_ID_TO_NAME = {"neel_brokerage": "Neel's Brokerage", "jaya_brokerage": "Jaya's Brokerage"}


def _friday(d: date) -> date:
    return d + timedelta(days=(4 - d.weekday()) % 7)


_EARNINGS_PATH = Path(__file__).resolve().parents[4] / "data" / "earnings_calendar.json"
_POLICY_PATH = Path(__file__).resolve().parents[4] / "data" / "investment_policy.json"


def _get_roll_streak_ctx(db: Session, account_id: Optional[str], symbol: str,
                          option_type: str, strike: float, depth: float) -> Optional[Dict]:
    """Guarded wrapper: no account_id (join miss) or any error → None,
    never blocks the card (cyclical-vs-runaway signal, Neel 2026-07-21)."""
    if not account_id:
        return None
    try:
        return get_roll_streak(db, account_id, symbol, option_type, strike, depth)
    except Exception:
        return None


def _roll_timing_note(dte: int) -> str:
    """Day-of-week guidance for rolling a deep-ITM position expiring this
    week (Neel, 2026-07-22): rolling Mon/Tue overpays — meaningful time
    value hasn't decayed yet, so buying back the current option costs
    more than it needs to. Waiting until Thu risks early assignment on a
    deep-ITM position even though official expiry is Friday. Wednesday
    (dte=2) is the target window — decay has done its work, assignment
    risk is still low."""
    if dte >= 3:
        return (" Still 3+ days out: rolling today overpays for time value that hasn't decayed yet — "
                 "target Wednesday (2 days out) instead of rolling early.")
    if dte == 2:
        return " Good window to roll today — time value mostly decayed, assignment risk still low."
    if dte == 1:
        return (" Caution: early-assignment risk on a deep-ITM position rises sharply this close to "
                 "expiry, even though official expiry is tomorrow. Roll today rather than waiting for Friday.")
    return " Last day before expiry — assignment likely if still ITM at the close. Roll now if you haven't."


def _streak_text(streak: Optional[Dict]) -> str:
    if not streak or streak.get("weeks_rolled", 0) < 2:
        return ""
    weeks = streak["weeks_rolled"]
    trend = streak.get("trend")
    if trend == "worsening":
        return (f" ⚠ Rolled {weeks} weeks running, ITM% {streak['itm_pct_at_start']:.0f}%→"
                f"{streak['itm_pct_now']:.0f}% (worsening) — cyclical-dip assumption weakening; "
                "consider evaluating a close instead of another roll.")
    if trend == "stable":
        return (f" Rolled {weeks} weeks running, ITM% holding near {streak['itm_pct_now']:.0f}% "
                "(stable) — consistent with a cyclical dip, roll continues to look reasonable.")
    if trend == "improving":
        return (f" Rolled {weeks} weeks running, ITM% improving {streak['itm_pct_at_start']:.0f}%→"
                f"{streak['itm_pct_now']:.0f}% — cycle may be exhausting soon.")
    return f" Rolled {weeks} weeks running (not enough price history to judge the trend)."


def _load_policy_ignore_list() -> set:
    """Symbols with no options market (money-market funds, cash sweeps) —
    the 'ignore' list in investment_policy.json. Engine 1 must never
    recommend covered calls on these (FDRXX bug, 2026-07-15)."""
    try:
        with open(_POLICY_PATH) as f:
            return set(json.load(f).get("ignore", []))
    except Exception:
        return set()


def _load_earnings_calendar() -> Dict:
    """Symbol → next-earnings info, refreshed by /refresh via MCP.
    Returns {} on any problem — earnings awareness is an annotation,
    never a reason for the queue to fail."""
    try:
        with open(_EARNINGS_PATH) as f:
            data = json.load(f)
        cal = dict(data.get("earnings", {}))
        cal["_lookahead"] = int(data.get("lookahead_days", 16))
        return cal
    except Exception:
        return {}


_ALLOCATION_TARGETS_PATH = Path(__file__).resolve().parents[4] / "data" / "allocation_targets.json"


def _load_wanted_symbols() -> set:
    """Every symbol the AI value-chain allocation plan actually wants held
    (physical_ai + infrastructure_ai + hold_other buckets, aliases
    resolved) — the complement of this is "off-thesis." Feeds Engine 6
    (Neel, 2026-08-11): a put sold on a name that was never part of the
    plan (CBRS, SOXL — not on the exit list either, just never in the
    plan at all) ties up collateral for nothing; closing it, not rolling
    it, is what actually frees that cash for a wanted buy. Returns empty
    on any problem — fails open, same as _load_policy_ignore_list, so a
    config gap never blocks the rest of the queue."""
    try:
        with open(_ALLOCATION_TARGETS_PATH) as f:
            cfg = json.load(f)
        wanted = set()
        for bucket in (cfg.get("buckets") or {}).values():
            wanted.update((bucket.get("targets") or {}).keys())
        aliases = (cfg.get("aliases") or {}).items()
        for a, b in aliases:
            if not a.startswith("_"):
                wanted.add(a)  # the alias symbol itself also reads as wanted
        return wanted
    except Exception:
        return set()


def _acct_rank(name: str) -> int:
    try:
        return CANONICAL_ORDER.index(name)
    except ValueError:
        return 99


def _put_capacity_by_account(db: Session) -> Dict[str, float]:
    """Total put-selling capacity per account, as of now: margin line +
    cash balance (margin accounts) or cash incl. locked collateral
    (everyone else). Same definition as /income/put-capacity, but
    per-account and using the latest snapshot rather than monthly
    buckets. This is TOTAL capacity — still includes whatever is
    currently locked by open puts; callers subtract that separately to
    get the undeployed/available amount."""
    settings_path = Path(__file__).resolve().parents[4] / "data" / "goal_settings.json"
    limits = {}
    if settings_path.exists():
        limits = json.loads(settings_path.read_text()).get("margin_limits", {})
    margin_names = {MARGIN_ID_TO_NAME.get(k, k): v for k, v in limits.items()}

    cash_rows = db.execute(text("""
        SELECT DISTINCT ON (account_name) account_name, true_cash
        FROM account_cash_balance_history
        WHERE account_name != 'Portfolio (Synthetic)'
        ORDER BY account_name, snapshot_date DESC
    """)).fetchall()
    cash = {r.account_name: float(r.true_cash or 0) for r in cash_rows}

    capacity: Dict[str, float] = {}
    for name, line in margin_names.items():
        capacity[name] = line + cash.get(name, 0.0)
    for name, bal in cash.items():
        if name not in margin_names:
            capacity[name] = bal
    return capacity


def _rebalance_lookup(db: Session) -> Dict[str, Dict]:
    """Per-symbol rebalance intent from the Investments allocation plan.

    This is what makes the two pages agree. Without it Engine 1 tells Neel to
    sell delta-15 NVDA calls to KEEP the stock in the same week the
    Investments page tells him to roll to ATM and let 761 shares go — same
    symbol, opposite instruction, and the email is what he acts on.

    Fails open: any error here leaves the queue exactly as it was, because a
    broken allocation plan must never block weekly income generation.
    """
    try:
        from app.modules.investments.allocation_service import get_allocation_plan
        plan = get_allocation_plan(db)
    except Exception as e:                     # noqa: BLE001 - deliberate
        logger.warning(f"[V6] allocation plan unavailable, rebalance overlay off: {e}")
        return {}
    out: Dict[str, Dict] = {}
    rows = [r for b in plan.get("buckets", []) for r in b.get("rows", [])]
    rows += plan.get("exit_rows", [])
    for r in rows:
        if r.get("action") in ("buy", "trim", "exit") and r.get("contracts", 0) > 0:
            out[r["symbol"]] = {
                "action": r["action"],
                "target_shares": r.get("target_shares"),
                "current_shares": r.get("current_shares"),
                "contracts": r.get("contracts"),
                "gap_shares": r.get("gap_shares"),
                "routing": r.get("routing") or {},
                "order": r.get("order") or {},
                "price": r.get("price"),
                "share_buy": r.get("share_buy"),
            }
    return out


def build_action_queue(db: Session) -> Dict:
    today = date.today()
    week_ending = _friday(today)
    rebalance = _rebalance_lookup(db)

    # ---- data: latest option snapshot per account -------------------------
    # account_id joined in for technical_signals lookups (investment_
    # transactions / investment_holdings_history key on account_id, not
    # the display name sold_options_snapshots stores).
    pos_rows = db.execute(text("""
        SELECT s.account_name, ia.account_id, s.snapshot_date, so.symbol, so.strike_price,
               so.option_type, so.expiration_date, so.contracts_sold,
               so.premium_per_contract AS current_mark, so.original_premium
        FROM sold_options so
        JOIN sold_options_snapshots s ON s.id = so.snapshot_id
        LEFT JOIN investment_accounts ia ON ia.account_name = s.account_name
        WHERE so.snapshot_id IN (
            SELECT MAX(id) FROM sold_options_snapshots
            WHERE parsing_status = 'success' OR parsing_status IS NOT NULL
            GROUP BY account_name)
          AND (so.expiration_date IS NULL OR so.expiration_date >= :today)
    """), {"today": today}).fetchall()

    hold_rows = db.execute(text("""
        SELECT a.account_name, a.account_id, a.account_type, h.symbol, h.quantity,
               h.current_price, h.cost_basis, h.last_updated
        FROM investment_holdings h
        JOIN investment_accounts a
          ON a.account_id = h.account_id AND a.source = h.source
        WHERE a.is_active = 'Y' AND h.quantity > 0 AND h.symbol != 'CASH'
        ORDER BY h.last_updated ASC
    """)).fetchall()

    data_as_of = max((r.snapshot_date for r in pos_rows), default=None)

    acct_type = {r.account_name: (r.account_type or "").lower() for r in hold_rows}
    price: Dict[str, float] = {}
    holdings: Dict[tuple, dict] = {}
    for r in hold_rows:
        # Symbols held in more than one account (e.g. TSLA in both Neel's
        # Brokerage and Alisha's, which is deliberately never synced — see
        # docs/ROBINHOOD_MCP_SYNC.md) previously let whichever row the DB
        # happened to return LAST win, with no regard for freshness — a
        # stale, months-old Alisha/HSA price could silently shadow a
        # same-day synced one (2026-08-05: TSLA showed $423.74 from a
        # 2026-06-03 Alisha row instead of the real $321.46, producing a
        # false "deep ITM, wait" alert). ORDER BY last_updated ASC above
        # makes the last write in this loop the most recently synced row,
        # deterministically.
        if r.current_price:
            price[r.symbol] = float(r.current_price)
        holdings[(r.account_name, r.symbol)] = {
            "qty": float(r.quantity),
            "cost_basis": float(r.cost_basis) if r.cost_basis else None,
            "account_id": r.account_id,
        }

    # Real quote for option-only underlyings (no owned shares, so nothing
    # in `price` above) — e.g. SOXL/CBRS cash-secured puts. Sourced from
    # symbol_price_history, which the MCP bridge now upserts every sync
    # from the same equity_marks quote already fetched for the paste
    # (2026-07-30: previously fetched and silently discarded for any
    # symbol without an owned equity_position, so these had no real price
    # anywhere and each option contract independently guessed a different
    # one — see hist_price fallback in stock_price() below).
    hist_price: Dict[str, float] = {
        r.symbol: float(r.close_price) for r in db.execute(text("""
            SELECT DISTINCT ON (symbol) symbol, close_price
            FROM symbol_price_history ORDER BY symbol, price_date DESC
        """)).fetchall()
    }

    def is_sheltered(account: str) -> bool:
        return acct_type.get(account, "") in NON_TAXABLE_TYPES

    def stock_price(sym: str, strike: float, mark: float, opt: str):
        """Synced (owned-share) price first — real and current by
        construction. Else a real quote from symbol_price_history for a
        symbol with no owned shares (flagged as estimated since it isn't
        necessarily today's price). Else, last resort, a deep-ITM estimate
        backed out from this specific option's own mark (flagged — and can
        disagree contract-to-contract for the same stock, since it assumes
        ~zero extrinsic value, which is only true when deep enough ITM)."""
        if sym in price:
            return price[sym], False
        if sym in hist_price:
            return hist_price[sym], True
        if mark and strike and mark > 0.05 * strike:
            est = strike - mark if opt == "put" else strike + mark
            return max(est, 0.01), True
        return None, False

    items: List[Dict] = []
    board: List[Dict] = []

    earnings_cal = _load_earnings_calendar()
    wanted_symbols = _load_wanted_symbols()

    def add_item(priority, action, engine, rule, title, account, symbol,
                 detail, why, earn=None, context=None):
        ctx = dict(context or {})
        # Earnings awareness (Neel, 2026-07-14): premium quoted across an
        # earnings date is event-inflated and IV crushes after the call.
        # Every item for a reporting symbol carries the callout so both the
        # queue and the notification emails surface it.
        er = earnings_cal.get(symbol)
        if er:
            er_date = date.fromisoformat(er["date"])
            days_to_er = (er_date - today).days
            if 0 <= days_to_er <= earnings_cal.get("_lookahead", 16):
                timing = {"am": "before open", "pm": "after close"}.get(er.get("timing"), "")
                verified = "" if er.get("verified", True) else " (unconfirmed)"
                ctx["next_earnings"] = {"date": er["date"], "timing": er.get("timing"),
                                        "days": days_to_er, "verified": er.get("verified", True)}
                why = (f"📅 {symbol} earnings {er_date.strftime('%-m/%-d')} {timing}{verified} "
                       f"({days_to_er}d away) — premium through that date is event-inflated and IV "
                       f"crushes after the call. Factor it into entry/roll timing. " + why)
        items.append({
            "id": f"v6_{engine}_{account}_{symbol}_{len(items)}",
            "priority": priority, "action": action, "engine": engine,
            "rule": rule, "title": title, "account": account,
            "symbol": symbol, "detail": detail, "why": why, "earn": earn,
            "context": ctx,
        })

    # ---- Engine 4: stuck positions ----------------------------------------
    covered_calls: Dict[tuple, int] = {}
    # One ledger index per (account, symbol, option_type), reused across
    # every board row that shares it (e.g. two open SPCX calls at
    # different strikes both hit the same cache entry) — this page already
    # had one quadratic-query performance incident, so ~98 open contracts
    # get at most a few dozen queries total here, not one each (Neel,
    # 2026-08-12, asking for this same "total collected across all rolls"
    # figure on the open-positions board: "make sure... you're not making
    # mistakes and that you write safe code... on a bigger table").
    _roll_chain_cache: Dict[Tuple[str, str, str], Tuple[Dict, Dict]] = {}

    def _roll_chain_for(acct_id: Optional[str], sym_: str, opt_: str, strike_: float, exp_):
        """Total collected across every roll leading to this OPEN
        position, or None when the ledger has no matching leg (old
        position predating tracked history, etc.) — never fabricated."""
        if not acct_id or not exp_:
            return None
        cache_key = (acct_id, sym_, opt_)
        idx = _roll_chain_cache.get(cache_key)
        if idx is None:
            idx = _index_roll_transactions(db, acct_id, sym_, opt_)
            _roll_chain_cache[cache_key] = idx
        sto_by_leg, btc_by_date = idx
        leg = sto_by_leg.get((strike_, exp_))
        if leg is None:
            return None
        return _walk_roll_chain(sto_by_leg, btc_by_date, strike_, exp_, leg["date"], leg["amount"])

    for p in pos_rows:
        sym, strike = p.symbol, float(p.strike_price)
        mark = float(p.current_mark or 0)
        orig = float(p.original_premium or 0)
        contracts = int(p.contracts_sold)
        opt = (p.option_type or "call").lower()
        exp = p.expiration_date
        dte = (exp - today).days if exp else 999
        account = p.account_name
        p_acct_id = p.account_id
        stock, estimated = stock_price(sym, strike, mark, opt)
        capture_pct = round((orig - mark) / orig * 100, 1) if orig else None

        if opt == "call":
            covered_calls[(account, sym)] = covered_calls.get((account, sym), 0) + contracts * 100

        chain = _roll_chain_for(p_acct_id, sym, opt, strike, exp)

        board.append({
            "account": account, "symbol": sym, "type": opt, "strike": strike,
            "expiration": str(exp) if exp else None, "dte": dte,
            "contracts": contracts, "stock_price": stock,
            "price_estimated": estimated, "current_mark": mark,
            "original_premium": orig, "capture_pct": capture_pct,
            "itm": bool(stock and ((opt == "call" and stock > strike)
                                   or (opt == "put" and stock < strike))),
            "total_collected": chain["net_premium"] if chain else None,
            "total_collected_weeks": chain["chain_weeks"] if chain else None,
            "total_collected_incomplete": chain["incomplete"] if chain else None,
        })

        if stock is None:
            continue
        base_ctx = {"symbol": sym, "strike_price": strike, "option_type": opt,
                    "contracts": contracts, "current_price": stock,
                    "expiration_date": str(exp) if exp else "",
                    "current_premium": mark, "profit_percent": capture_pct or 0}

        # ---- Engine 6: free collateral on off-thesis puts ------------------
        # Neel, 2026-08-11: TSLA/NVDA/GOOGL-style rebalancing rolls can take
        # weeks (they only complete via natural weekly assignment) and he's
        # not in a rush there. What IS urgent: puts sold on names that were
        # never part of the AI value-chain plan (CBRS, SOXL here — not even
        # on the exit list, just never in the plan) lock up collateral for
        # nothing. Closing one — not rolling it, which would only extend the
        # unwanted exposure — frees that cash for a wanted buy instead.
        # Scoped strictly to off-thesis names only (confirmed with Neel):
        # a wanted-but-mistimed put (GOOGL over target, AMD at target, SPCX's
        # excess wheel activity) does NOT trigger this — those stay on the
        # normal, lower-urgency path below. wanted_symbols empty (config
        # failed to load) means skip entirely, not flag everything.
        if opt == "put" and wanted_symbols and sym not in wanted_symbols:
            collateral = strike * contracts * 100
            close_cost = mark * contracts * 100
            add_item(
                "high", "CLOSE", 6, "Off-thesis put — free collateral",
                f"{sym}: not in the allocation plan — close to free ${collateral:,.0f}", account, sym,
                f"buy to close {contracts} put{'s' if contracts > 1 else ''} at ${strike:g}, "
                f"expiring {exp.strftime('%m/%d') if exp else '?'}. Current stock price: ${stock:,.0f}. "
                f"Costs ≈${close_cost:,.0f} to close, frees ${collateral:,.0f} collateral.",
                f"{sym} isn't part of the AI value-chain allocation plan — assignment would deliver a stock "
                "not on the buy list. Closing (not rolling — a roll just extends this same unwanted exposure) "
                "frees the collateral for a wanted put instead (SPCX/MU/MSFT/TSM/AMZN/MRVL, per the allocation plan).",
                context={**base_ctx, "off_thesis": True,
                         "collateral_freed": round(collateral, 2), "close_cost": round(close_cost, 2)})
            continue

        # Surface RSI on existing-position ALERT/ROLL cards too (Neel,
        # 2026-07-28): these show no entry-timing signal at all today, but
        # RSI still matters for a held ITM position — e.g. an overbought
        # RSI on a deep-ITM call suggests the run has room to keep going
        # (assignment likely stands), not just whether to enter a new sale.
        entry = get_entry_timing(db, p_acct_id, sym) if p_acct_id else {"available": False}
        if entry.get("available") and entry.get("rsi") is not None:
            base_ctx["entry_timing"] = {
                "rsi": entry["rsi"], "wait": entry.get("wait", False),
                "reason": entry.get("reason") or f"RSI {entry['rsi']:.0f}",
                "consecutive_down_days": entry.get("consecutive_down_days"),
                "change_pct": entry.get("change_pct"),
                "price_source": entry.get("price_source"),
            }

        # Rebalance overlay for EXISTING positions (Neel, 2026-08-12): Engine
        # 5 only emits its own dedicated cards for NEW orders it wants
        # placed — it says nothing on an ALREADY-OPEN put/call for a symbol
        # that also carries a rebalance target, so this ROLL/WATCH card read
        # identically whether assignment here was wanted (aligned with a buy
        # target) or actively unwanted (a trim/exit target, where assignment
        # would ADD shares to a symbol Neel is trying to REDUCE — e.g. GOOGL:
        # 400 held vs a 200 target). "Are you asking me to roll because you
        # forgot we wanted assignment?" — this makes the answer explicit
        # instead of silent. Badge only set when actually aligned (same
        # context.rebalance shape Engine 1/5 already use, so the frontend's
        # existing REBALANCING badge just works); a put that conflicts with
        # a trim/exit target gets a caution instead of the badge, since
        # showing "REBALANCING" there would imply the opposite of what's
        # true.
        rb_sym = rebalance.get(sym)
        rebalance_note = ""
        if rb_sym:
            tgt = rb_sym.get("target_shares")
            tgt_txt = f" ({tgt:,} sh)" if tgt is not None else ""
            if opt == "put" and rb_sym["action"] == "buy":
                base_ctx["rebalance"] = {"action": "buy", "target_shares": tgt,
                                          "gap_shares": rb_sym.get("gap_shares")}
                rebalance_note = (f" This put also counts toward the {sym} buy target{tgt_txt} — "
                                  "assignment here is wanted, in line with rebalancing, not a risk.")
            elif opt == "put" and rb_sym["action"] in ("trim", "exit"):
                rebalance_note = (f" ⚠ Unrelated to rebalancing — {sym} is a TRIM target{tgt_txt}; "
                                  "assignment on THIS put would ADD shares, working against that. "
                                  "Manage it on its own income merits, not as a rebalancing play.")
            elif opt == "call" and rb_sym["action"] in ("trim", "exit"):
                base_ctx["rebalance"] = {"action": rb_sym["action"], "target_shares": tgt,
                                          "gap_shares": rb_sym.get("gap_shares")}
                rebalance_note = (f" This call is part of the {sym} {rb_sym['action']} — assignment "
                                  "here is the intended outcome, not a risk.")

        if opt == "call" and stock > strike:
            intrinsic = stock - strike
            ipct = round(intrinsic / mark * 100, 0) if mark else 100
            spec = f"{sym} {contracts}x CALL ${strike:g} {exp.strftime('%m/%d') if exp else ''} · stock ${stock:,.0f} · {ipct:.0f}% intrinsic"
            if ipct > 80:
                add_item("high", "WATCH", 4, "ITM call >80% intrinsic",
                         f"{sym} call deep ITM — wait, don't roll", account, sym, spec,
                         "Mostly intrinsic: compression too expensive. Set price alerts "
                         "(-5% evaluate, -10% compress, at-strike full exit). Cut only if thesis changed."
                         + rebalance_note,
                         context=base_ctx)
            elif ipct > 60:
                add_item("medium", "WATCH", 4, "ITM call 60-80% intrinsic",
                         f"{sym} call ITM — wait for mean reversion, don't roll", account, sym, spec,
                         "Stock must move back; do NOT compress (too expensive at this intrinsic level)."
                         + rebalance_note,
                         context=base_ctx)
            elif ipct > 40:
                shel = is_sheltered(account)
                # Both "compress" and "wait for pullback" are assignment-
                # AVOIDANCE moves — nonsensical advice on a call that's
                # part of a trim/exit, where assignment IS the goal (Neel,
                # 2026-08-14, re: a TSLA $335 call: "why is the UI asking
                # me to roll?" — the rebalance_note said assignment here
                # is the intended outcome, right next to a ROLL action
                # telling him to fight that same assignment). Trim/exit-
                # aligned calls get WATCH instead — nothing to place,
                # letting it run toward assignment IS the position working.
                if rb_sym and rb_sym["action"] in ("trim", "exit"):
                    add_item("medium", "WATCH", 4, "ITM call 40-60% intrinsic (crossover)",
                             f"{sym} call — let it ride toward assignment", account, sym, spec,
                             f"This call is part of the {sym} {rb_sym['action']} — compressing or waiting "
                             "for a pullback would both mean fighting the assignment this position exists "
                             "to deliver. No action: letting it run to expiry (or getting called away "
                             "before then) is the trim working, not a risk to manage.",
                             context=base_ctx)
                else:
                    add_item("high", "ROLL", 4, "ITM call 40-60% intrinsic (crossover)",
                             f"{sym} call — evaluate compression", account, sym, spec,
                             f"Crossover zone: compress (≤4 weeks total, target delta 30, small debit OK) "
                             f"or wait for pullback. {'IRA: compress more aggressively.' if shel else 'Taxable: slightly more patient, but avoid the 12-week trap.'}",
                             context=base_ctx)
            elif dte <= 2:
                if rb_sym and rb_sym["action"] in ("trim", "exit"):
                    add_item("medium", "WATCH", 4, "ITM call at expiry",
                             f"{sym} call ITM, expires in {dte}d — let it assign", account, sym, spec,
                             f"This call is part of the {sym} {rb_sym['action']} — rolling up/out would "
                             "delay the exact assignment this position is meant to deliver. No action: "
                             "let it expire in the money and get called away.",
                             context=base_ctx)
                else:
                    add_item("urgent", "ROLL", 4, "ITM call at expiry",
                             f"{sym} call ITM, expires in {dte}d", account, sym, spec,
                             "Time-dominated ITM call at expiry: roll up/out to next week or accept assignment (called away = plan for Tier 2).",
                             context=base_ctx)

        elif opt == "put" and stock < strike * 1.02:
            itm = stock < strike
            depth = round((strike - stock) / strike * 100, 1) if itm else 0
            spec = (f"{sym} {contracts}x PUT ${strike:g} {exp.strftime('%m/%d') if exp else ''} · stock ${stock:,.0f}"
                    + (f" · {depth:.0f}% ITM" if itm else " · near ATM")
                    + (" (est.)" if estimated else ""))
            # Roll TARGET — strike, date, credit — not just the strategy in
            # words (Neel, 2026-08-12: "you're not telling me to roll it to
            # what amount and what date" / "you used to say how much money
            # will be made"). Next Friday out; strike walks down to current
            # stock price when ITM ("roll down and out"), stays put when
            # merely near-ATM. est_premium is the NEW leg's gross credit
            # only, same convention as every other card in this file — the
            # buy-to-close cost on the leg being replaced isn't priced (no
            # live chain feed), so this is not a true net roll credit, just
            # what "net-zero-or-credit" is measured against.
            roll_exp = exp + timedelta(days=7) if exp else None
            roll_strike = round(stock) if itm else strike
            roll_premium = weekly_premium(contracts, stock, RATE_ATM_WEEKLY)
            roll_txt = (f" Roll to strike ${roll_strike:,.0f}, expiring "
                        f"{roll_exp.strftime('%m/%d') if roll_exp else '?'} — new leg collects "
                        f"≈${roll_premium:,} (est., gross — net of closing the current leg).")
            roll_ctx = {"roll_to_strike": roll_strike,
                        "roll_to_expiration": str(roll_exp) if roll_exp else None,
                        "roll_to_premium": roll_premium}
            if dte <= 2:
                add_item("urgent" if itm else "high", "ROLL", 4,
                         "Tested put at expiry",
                         f"{sym} put {'ITM' if itm else 'near ATM'}, expires in {dte}d",
                         account, sym, spec,
                         "1-2 days to expiry and still tested: roll out 1 week; if deeper ITM, roll down+out "
                         "at ~net-zero. Oscillating assumed — do not panic-close (AVGO lesson). Verify no "
                         "thesis-changing news." + roll_txt + (_roll_timing_note(dte) if itm else "") + rebalance_note,
                         earn=roll_premium,
                         context={**base_ctx, **roll_ctx})
            elif itm and depth >= 10 and exp and exp <= week_ending:
                streak = _get_roll_streak_ctx(db, p_acct_id, sym, opt, strike, depth)
                add_item("high", "ROLL", 4, "Deep tested put",
                         f"{sym} put {depth:.0f}% ITM", account, sym, spec,
                         "Roll down and out at net-zero-or-credit while the cycle exhausts; acceptable for multiple "
                         "weeks. Runaway (structural news) would instead mean evaluate closing."
                         + roll_txt + _roll_timing_note(dte) + _streak_text(streak) + rebalance_note,
                         earn=roll_premium,
                         context={**base_ctx, **roll_ctx, **({"roll_streak": streak} if streak else {})})
            elif itm and depth >= 10:
                # Expires AFTER this week's Friday ⇒ already rolled into the
                # next cycle (Neel, 2026-07-09: 'those have already been
                # rolled'). Re-rolling mid-cycle is optional, not urgent —
                # downgrade to a monitor until the position's week arrives.
                streak = _get_roll_streak_ctx(db, p_acct_id, sym, opt, strike, depth)
                add_item("medium", "WATCH", 4, "Deep tested put — rolled this cycle",
                         f"{sym} put {depth:.0f}% ITM, rolled to {exp.strftime('%m/%d')}",
                         account, sym, spec,
                         "Already rolled into next week's expiry; this cycle's action is done. Monitor — an "
                         "opportunistic further roll-down only if it nets zero-or-credit. Becomes a ROLL again "
                         "when its expiry week arrives and it's still ITM."
                         + _streak_text(streak) + rebalance_note,
                         context={**base_ctx, **({"roll_streak": streak} if streak else {})})
            elif itm:
                add_item("low", "WATCH", 4, "Tested put — theta working",
                         f"{sym} put slightly ITM, {dte}d left", account, sym, spec,
                         "More than 5 days out: let theta work (RSI<30 stocks are already beaten up)."
                         + rebalance_note,
                         context=base_ctx)

    # ---- Engine 1: uncovered calls ----------------------------------------
    non_optionable = _load_policy_ignore_list()
    for (account, sym), h in holdings.items():
        if sym in non_optionable:
            continue  # money-market funds / cash sweeps have no options
        shares = h["qty"]
        uncovered = shares - covered_calls.get((account, sym), 0)
        n = int(uncovered // 100)
        if n < 1 or sym not in price:
            continue
        stock = price[sym]

        # Surface uncovered-call opportunities directly on the position
        # board (not just as Action Queue SELL items) so the Calls group
        # on a per-account view shows what's NOT sold, not only what is.
        board.append({
            "account": account, "symbol": sym, "type": "call", "strike": None,
            "expiration": None, "dte": None, "contracts": n,
            "stock_price": stock, "price_estimated": False, "current_mark": None,
            "original_premium": None, "capture_pct": None, "itm": False,
            "uncovered": True, "uncovered_shares": int(uncovered),
        })

        shel = is_sheltered(account)
        tier1 = sym in TIER1

        # ---- Rebalance overlay -------------------------------------------
        # A symbol ABOVE its allocation target is being deliberately reduced,
        # so its calls go ATM to get assigned. That directly overrides the
        # Tier-1 "income without getting called away" rule, which exists to
        # PREVENT assignment. The override is scoped and temporary: it applies
        # only while the position is more than one contract above target, and
        # the moment it is in range the symbol reverts to normal Tier-1
        # treatment. The two-book model is the resting state; rebalancing is
        # a regime, not a replacement.
        rb = rebalance.get(sym)
        rebalancing = bool(rb and rb["action"] in ("trim", "exit"))
        if rebalancing:
            # Engine 5 owns this symbol entirely. Emitting a Tier-1 card here
            # too would put "sell delta-15 calls to KEEP the stock" in the
            # same email as "roll to ATM and let it go" — the exact
            # contradiction this overlay exists to remove. Engine 1 also
            # cannot express the real instruction: NVDA's 1,761 shares are
            # already covered by 16 calls, so Engine 1 sees only the HSA's
            # 161 uncovered and would recommend one new call while the actual
            # trade is rolling seven existing ones down.
            continue

        if sym == "TSLA":
            delta, otm = "10-12", OTM_TSLA
            gate = "TSLA carve-out: fire only when RSI > 75; roll at zero cost if ITM, never panic-close."
        elif tier1:
            delta, otm = ("15" if shel else "10-15"), (OTM_TIER1_SHELTERED if shel else OTM_TIER1_TAXABLE)
            gate = "Tier 1 hold: income without getting called away."
        else:
            # Tier 2: two documented policies conflict (V6 table 2026-07-09
            # says ATM/max-premium; Neel's stated convention 2026-07-12 says
            # delta-20 exit calls, ≈6% OTM ≈ 80% chance of profit). Until he
            # picks one, present BOTH strikes — never the misleading
            # "delta 80" label (that read as a real delta and matched
            # neither: a true delta-80 call is deep ITM).
            delta, otm = "ATM", OTM_ATM
            gate = ("Tier 2 wheel — two valid strikes: ATM = max premium, likely assigned "
                    "(fast exit); delta-20 (~6% OTM) = keep the stock most weeks, exit on a "
                    "rally. Policy not yet fixed — choose per situation.")

        # Real entry-timing check (Neel, 2026-07-21): he was skipping calls
        # into a multi-day decline expecting reversion (TSLA $415→$380) —
        # the old text just told him to go check RSI himself. Computed from
        # investment_holdings_history, which always has data for an
        # Engine-1 candidate (it requires >=100 shares actually held) once
        # the position is >2 weeks old. Fails OPEN (no annotation, today's
        # static text stands) when history is too thin — a data gap must
        # never silently block income generation.
        acct_id = h.get("account_id")
        entry = get_entry_timing(db, acct_id, sym) if acct_id else {"available": False}
        entry_ctx = None
        if sym == "TSLA":
            # TSLA's own carve-out is stricter and inverted: default WAIT,
            # fire only when strongly overbought (RSI>75).
            if entry.get("available") and entry.get("rsi") is not None:
                rsi = entry["rsi"]
                tsla_wait = not (rsi > 75)
                entry_ctx = {"rsi": rsi, "wait": tsla_wait,
                             "reason": (f"RSI {rsi:.0f} — needs >75 to fire" if tsla_wait
                                        else f"RSI {rsi:.0f} — carve-out clear"),
                             "consecutive_down_days": entry.get("consecutive_down_days"),
                             "change_pct": entry.get("change_pct"),
                             "price_source": entry.get("price_source")}
        elif entry.get("available") and entry.get("rsi") is not None:
            # Attach regardless of wait: RSI is worth showing even when it
            # isn't triggering a hold (2026-07-29 — was gated on wait=True
            # only, so a SELL card with RSI available but not oversold
            # showed no RSI at all, unlike the Engine-4 cards).
            entry_ctx = {"rsi": entry.get("rsi"), "wait": bool(entry.get("wait")),
                         "reason": entry.get("reason") or f"RSI {entry['rsi']:.0f}",
                         "consecutive_down_days": entry.get("consecutive_down_days"),
                         "change_pct": entry.get("change_pct"),
                         "price_source": entry.get("price_source")}
        entry_wait = bool(entry_ctx and entry_ctx.get("wait"))

        target = strike_for(stock, otm)   # strike the delta rule wants
        approx = target
        cost_ps = (h["cost_basis"] / shares) if (h["cost_basis"] and shares) else None
        floor_note = ""
        if cost_ps and approx < cost_ps:
            approx, floor_note = cost_ps, " (raised to cost basis floor)"
        # rough weekly premium: delta% of a ~2% weekly move value.
        # NOTE: this heuristic prices the delta-TARGET strike. It is only
        # valid when the recommended strike is at/near that target.
        est = weekly_premium(n, stock,
                             RATE_TIER1_WEEKLY if (tier1 or sym == "TSLA") else RATE_ATM_WEEKLY)
        per_share = est / (n * 100) if n else 0
        exp = week_ending if today.weekday() <= 2 else _friday(week_ending + timedelta(days=3))

        # Cost-basis floor far above spot ⇒ a near-dated call at the floored
        # strike pays ~nothing; showing the ATM-priced earn next to the
        # floored strike is a lie (IBIT bug, 2026-07-13: card said
        # "~$49 … Earn ~$630" when the $49 weekly was bid $0.01). Present
        # the real decision instead, with earn=0 for the floored strike.
        floor_gap_pct = ((approx - target) / stock * 100) if floor_note else 0.0
        if floor_gap_pct > 5:
            action_txt = (
                f"{int(uncovered):,} uncovered shares, but the cost-basis floor "
                f"${cost_ps:,.2f} sits {floor_gap_pct:.0f}% above spot — a near-dated call there "
                f"pays ≈$0, so there is no premium without breaking the floor. Decide: "
                f"(a) skip this cycle and wait for spot to recover toward basis, or "
                f"(b) Tier-2 wheel exit below basis: strike ~${target:,.0f} pays ≈${est:,} "
                f"(≈${per_share:.2f}/sh) but assignment realizes the loss vs basis. "
                "The earn figure is intentionally omitted for the floored strike."
            )
            add_item("medium", "SELL", 1, "Uncovered holdings ≥ 100 shares",
                     f"{sym}: {n} call{'s' if n > 1 else ''} available — basis floor binds", account, sym,
                     f"sell {n} call{'s' if n > 1 else ''} · strike ~${approx:,.0f} (basis floor) collects ≈$0 "
                     f"· alt strike ~${target:,.0f} collects ≈${est:,} · exp {exp.strftime('%m/%d')} · stock ${stock:,.0f}",
                     action_txt + (f" ⏸ Also: {entry_ctx['reason']} — entry timing says wait regardless." if entry_wait else ""),
                     earn=0,
                     context={"symbol": sym, "recommended_strike": round(approx, 2),
                              "floored_strike_pays": 0, "alt_strike": round(target, 2),
                              "alt_strike_premium": est, "option_type": "call",
                              "uncovered_contracts": n, "unsold_contracts": n,
                              "current_price": stock, "expiration_date": str(exp),
                              "total_premium": 0,
                              **({"entry_timing": entry_ctx} if entry_ctx else {})})
        else:
            # Detail reads as the ORDER to place: what to sell, at which
            # strike, for how much premium. "~$101 (delta 80)" read like a
            # sale price and confused the strike with the premium
            # (Neel, 2026-07-15). Premium figures are heuristics, not
            # quotes — labeled "est." until the sync carries chain data.
            if tier1 or sym == "TSLA":
                strike_txt = f"strike ~${approx:,.0f}{floor_note} (delta {delta})"
            else:
                d20 = stock * 1.06
                # Explicit "strike $X (why)" for both options — not "ATM
                # ~$X", the same ambiguous pattern already fixed on the
                # Engine-5 rebalancing card 2026-08-11 (is that the strike
                # or the current price?). Current stock price is stated
                # separately below regardless of which branch fires.
                strike_txt = (f"strike ${approx:,.0f}{floor_note} (ATM, max premium, likely assigned) "
                              f"or strike ${d20:,.0f} (delta-20, keeps the stock)")
            # Real computed entry-timing reason replaces the old static
            # "Entry timing: sell now if RSI>60..." hint when we have one;
            # falls back to the static text when history is too thin
            # (fail open — see get_entry_timing).
            entry_line = (f"⏸ WAIT — {entry_ctx['reason']}. Historically this pattern reverts; "
                          "consider holding off this week." if entry_wait
                          else f"Entry timing: {entry_ctx['reason']}, clear to sell." if entry_ctx
                          else "Entry timing: sell now if RSI>60; RSI<40 wait; RSI<30 do not sell.")
            # Entry timing is an income-optimisation gate — "wait for a better
            # RSI to sell this call". It does not apply to a rebalance: the
            # trade is a position decision, not a premium decision, and
            # holding off for a nicer entry just leaves the book off-target.
            add_item("medium", "SELL", 1, "Uncovered holdings ≥ 100 shares",
                     f"{sym}: {n} call{'s' if n > 1 else ''} available"
                     + (" — entry timing says wait" if entry_wait else ""), account, sym,
                     f"sell {n} call{'s' if n > 1 else ''} at {strike_txt}, "
                     f"expiring {exp.strftime('%m/%d')}. Current stock price: ${stock:,.0f}.",
                     f"{int(uncovered):,} uncovered shares earning nothing toward the 1%/mo holdings goal. {gate} "
                     + entry_line,
                     earn=est,
                     context={"symbol": sym, "recommended_strike": round(approx, 2),
                              "target_delta": delta,
                              "option_type": "call", "uncovered_contracts": n,
                              "unsold_contracts": n, "current_price": stock,
                              "expiration_date": str(exp), "total_premium": est,
                              "limit_per_share": round(per_share, 2),
                              **({"entry_timing": entry_ctx} if entry_ctx else {})})

    # ---- Engine 5: rebalance buys -----------------------------------------
    # Engine 1 structurally cannot see these. It iterates `holdings`, and
    # requires >=100 shares to write a call — so MRVL, TSM and AMZN at zero
    # shares produce nothing, no matter how large the gap. Acquiring is
    # expressed as short ATM puts: assignment delivers the stock at the
    # strike and pays premium for the wait.
    acct_id_to_name = {r.account_id: r.account_name for r in db.execute(text(
        "SELECT account_id, account_name FROM investment_accounts")).fetchall()}

    for sym, rb in sorted(rebalance.items(), key=lambda kv: -(kv[1].get("order") or {}).get("est_premium", 0)):
        # ---- sell side: one card per account leg, because the account is
        # the tax decision. The Investments page already picked the legs
        # lowest-tax-first; this just renders each as a placeable order.
        if rb["action"] in ("trim", "exit"):
            order = rb.get("order") or {}
            legs = (rb.get("routing") or {}).get("legs") or []
            if not order.get("strike") or not legs:
                continue
            roll = order.get("instruction") == "roll"
            verb = "roll" if roll else "sell"
            tgt = rb.get("target_shares") or 0
            for leg in legs:
                lc = int(leg.get("contracts") or 0)
                if lc < 1:
                    continue
                acct_name = acct_id_to_name.get(leg["account_id"], leg["account_id"])
                lots = leg.get("lots") or []
                lots_txt = "; ".join(f"{int(l['shares'])} sh @ ${l['cost_per_share']:,.2f}"
                                     for l in lots[:4])
                g = leg.get("realized_gain")
                tax_txt = ""
                if leg.get("sheltered"):
                    tax_txt = " Sheltered account — the sale is not a taxable event."
                elif g is not None:
                    tax_txt = (f" Delivers (highest basis first): {lots_txt}. Realizes "
                               f"{'a LOSS of ' if g < 0 else 'a gain of '}${abs(g):,.0f}.")
                # Detail states the strike as an exact, real number and the
                # stock price separately (Neel, 2026-08-11: "ATM ~$96.20"
                # read as ambiguous — is that the strike or the current
                # price? — and $96.20 wasn't even a real listed strike,
                # just spot*0.99 with two decimals of false precision).
                # Same fix already applied to the Engine-1 SELL card
                # 2026-07-15 for the identical confusion; atm_order() now
                # rounds to the nearest whole dollar so this number is
                # always at least a plausible real strike.
                price_txt = f" Current stock price: ${rb['price']:,.2f}." if rb.get("price") else ""
                # Medium, not low (Neel, 2026-08-14, reverting the 2026-08-11
                # demotion): the REBALANCE overall is patient — "not in a
                # rush to get to the new place right away" — but each of
                # these cards is still a real, placeable order for THIS
                # week's expiry (strike/premium computed for the current
                # cycle), not a standing "no action needed" note. Demoting
                # it to low buried it under the collapsed "show low
                # priority" toggle by default, which cost real weekly
                # premium/progress rather than just deferring urgency —
                # conflated "the multi-week trim isn't urgent" with "this
                # week's specific order isn't worth seeing." Engine 6's
                # off-thesis-put closes are still the highest-urgency item
                # (that stays "high"); this is one notch below that, same
                # as an ordinary Engine-1 income sell, not buried with it.
                add_item(
                    "medium", "ROLL" if roll else "SELL", 5, "Rebalancing",
                    f"{sym}: {verb} {lc} call{'s' if lc > 1 else ''} to reach {tgt:,} target",
                    acct_name, sym,
                    f"{verb} {lc} call{'s' if lc > 1 else ''} at strike ${order['strike']:,.0f}, "
                    f"expiring {order.get('expiration')}.{price_txt} Collects ≈"
                    f"${int((order.get('est_premium') or 0) * lc / max(1, order.get('contracts') or 1)):,}",
                    (f"Rebalancing — {sym}: holding {rb['current_shares']:,.0f} against a "
                     f"{tgt:,} target, {abs(int(rb['gap_shares'])):,} to release."
                     + (" The existing calls are far OTM and will never assign; rolling them "
                        "down to ATM is what actually produces the exit." if roll else "")
                     + " Assignment is the intended outcome, not a risk." + tax_txt),
                    earn=int((order.get("est_premium") or 0) * lc / max(1, order.get("contracts") or 1)),
                    context={"symbol": sym, "recommended_strike": order["strike"],
                             "target_delta": "ATM", "option_type": "call",
                             "unsold_contracts": lc, "current_price": rb.get("price"),
                             "expiration_date": order.get("expiration"),
                             "total_premium": order.get("est_premium"),
                             "rebalance": {"action": rb["action"], "target_shares": tgt,
                                           "gap_shares": rb.get("gap_shares"),
                                           "sheltered": leg.get("sheltered"),
                                           "realized_gain": g}})
            continue
        if rb["action"] != "buy":
            continue
        order = rb.get("order") or {}
        routing = rb.get("routing") or {}
        acct = routing.get("buy_account")
        n = int(order.get("contracts") or 0)
        if n < 1 or not order.get("strike"):
            # Nothing sellable: either open puts already cover the gap, or
            # the remainder is an odd lot. Both are already explained on the
            # Investments page; emitting a card here would be noise.
            continue
        acct_name = acct_id_to_name.get(acct, MARGIN_ID_TO_NAME.get(acct, acct))
        funded = routing.get("funded", True)
        short = routing.get("shortfall") or 0
        # Same fix as the trim/exit card above: exact whole-dollar strike
        # (atm_order() already rounds it — this was purely a display
        # issue, .2f exposing false precision on a value that's now
        # always a real number) and current stock price stated
        # separately, not implied by "ATM ~$X" (2026-08-11).
        price_txt = f" Current stock price: ${rb['price']:,.2f}." if rb.get("price") else ""
        add_item(
            "medium" if funded else "low", "SELL", 5, "Rebalancing",
            f"{sym}: {n} put{'s' if n > 1 else ''} to acquire toward {rb.get('target_shares'):,} target"
            + ("" if funded else " — not funded yet"),
            acct_name or "—", sym,
            f"sell {n} put{'s' if n > 1 else ''} at strike ${order['strike']:,.0f}, "
            f"expiring {order.get('expiration')}.{price_txt} Collects ≈${order.get('est_premium', 0):,}",
            (f"Rebalancing — holding {rb['current_shares']:,.0f} of a {rb.get('target_shares'):,} target. "
             f"Selling ATM puts acquires the shares at the strike and pays premium while waiting; "
             f"assignment is the intended outcome, not a risk."
             + ("" if funded else
                f" ⚠ No account can secure this yet — short ${short:,.0f} of collateral. "
                f"It becomes placeable once the exit and trim proceeds land.")),
            earn=order.get("est_premium"),
            context={"symbol": sym, "recommended_strike": order["strike"],
                     "target_delta": "ATM", "option_type": "put",
                     "unsold_contracts": n, "current_price": rb.get("price"),
                     "expiration_date": order.get("expiration"),
                     "total_premium": order.get("est_premium"),
                     "rebalance": {"action": "buy",
                                   "target_shares": rb.get("target_shares"),
                                   "gap_shares": rb.get("gap_shares"),
                                   "funded": funded}})

        # Unfunded + RSI says it's actually cheap right now: buy whatever
        # spare cash affords outright instead of waiting on exit/trim
        # proceeds to fully collateralize the put (Neel, 2026-08-11 — "no
        # point waiting to acquire the money because I have some money").
        # allocation_service already vetted this (RSI < 50, spare cash not
        # already claimed by another funded rebalance target) — see
        # allocation_service.py module docstring for the full rule.
        sb = rb.get("share_buy")
        if not funded and sb:
            sb_acct = acct_id_to_name.get(sb["account_id"], MARGIN_ID_TO_NAME.get(sb["account_id"], sb["account_id"]))
            add_item(
                "medium", "BUY", 5, "Rebalancing — buy shares (put unfunded)",
                f"{sym}: buy {sb['shares']} shares outright — put needs ${short:,.0f} more than any account has",
                sb_acct or "—", sym,
                f"buy {sb['shares']} shares at ${rb['price']:,.2f} ≈ ${sb['cash_used']:,.0f}"
                + (f" in {sb_acct}" if sb_acct else "") + ".",
                (f"RSI {sb['rsi']:.0f} — genuinely cheap, not just idle cash chasing a name. "
                 f"The full {n}-put position (${order['strike'] * 100 * n:,.0f} collateral) is "
                 f"still the target once exit/trim proceeds land; this is real progress now "
                 f"instead of waiting on that."
                 + (f" Consolidates into the account that already holds {sym}." if sb.get("consolidates") else "")),
                context={"symbol": sym, "current_price": rb.get("price"),
                         "share_buy": sb,
                         "rebalance": {"action": "buy", "target_shares": rb.get("target_shares"),
                                       "gap_shares": rb.get("gap_shares"), "funded": False}})

    # ---- available cash per account (unsold puts — symmetric to uncovered
    # calls above, but on the cash side). Not tied to a symbol: this is
    # capacity not yet deployed as any put, the Engine-2 entry point.
    capacity_by_account = _put_capacity_by_account(db)
    locked_by_account: Dict[str, float] = {}
    for p in pos_rows:
        if (p.option_type or "").lower() == "put":
            locked_by_account[p.account_name] = (
                locked_by_account.get(p.account_name, 0.0)
                + float(p.strike_price) * int(p.contracts_sold) * 100)
    for account, capacity in capacity_by_account.items():
        available = capacity - locked_by_account.get(account, 0.0)
        if available >= 1000:
            board.append({
                "account": account, "symbol": "CASH", "type": "put", "strike": None,
                "expiration": None, "dte": None, "contracts": 0,
                "stock_price": None, "price_estimated": False, "current_mark": None,
                "original_premium": None, "capture_pct": None, "itm": False,
                "uncovered": True, "uncovered_cash": round(available, 2),
            })

    # ---- assemble ----------------------------------------------------------
    prio_rank = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
    # Within a priority tier: things to DO (sell/roll) before things to
    # WATCH, then soonest expiry first, then account/symbol.
    # (Neel, 2026-07-15: same-priority items sorted alphabetically felt
    # random — actionable items and nearest expiries should lead.)
    action_rank = {"SELL": 0, "ROLL": 0, "BUY": 0, "WATCH": 1}
    items.sort(key=lambda i: (
        prio_rank[i["priority"]],
        action_rank.get(i["action"], 1),
        i["context"].get("expiration_date") or "9999-99-99",
        _acct_rank(i["account"]),
        i["symbol"],
    ))
    board.sort(key=lambda b: (b["expiration"] or "9999", _acct_rank(b["account"]), b["symbol"]))
    summary = {p: sum(1 for i in items if i["priority"] == p) for p in prio_rank}
    return {
        "generated_at": str(today), "data_as_of": str(data_as_of) if data_as_of else None,
        "week_ending": str(week_ending), "engine_version": "v6.1-stage1",
        "summary": {**summary, "total": len(items)},
        "items": items, "positions": board,
    }
