"""V6 Action Queue engine — Stage 1: Engines 4 (stuck) + 1 (uncovered calls).

One feed, two renderers (see docs/OPTIONS-EXECUTION-PAGE-SPEC.md): this
module produces the queue the Options Execution page renders in full and
the email notification renders as its urgent/high slice. Item context
keys match notification_organizer's schema.

Decision tables are transcribed from docs/OPTIONS-STRATEGY-V6-ENGINES.md
(V6.1). Runs entirely off synced data — no external calls.
"""
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

TIER1 = {"AAPL", "MSFT", "NVDA", "AVGO", "GOOGL", "AMZN", "META", "LLY"}
NON_TAXABLE_TYPES = {"ira", "roth_ira", "traditional_ira", "401k", "hsa", "retirement"}
CANONICAL_ORDER = ["Neel's Brokerage", "Neel's Retirement", "Neel's Roth IRA",
                   "Jaya's Brokerage", "Jaya's IRA", "Jaya's Roth IRA",
                   "Alisha's Brokerage", "Agrawal Family HSA"]


def _friday(d: date) -> date:
    return d + timedelta(days=(4 - d.weekday()) % 7)


def _acct_rank(name: str) -> int:
    try:
        return CANONICAL_ORDER.index(name)
    except ValueError:
        return 99


def build_action_queue(db: Session) -> Dict:
    today = date.today()
    week_ending = _friday(today)

    # ---- data: latest option snapshot per account -------------------------
    pos_rows = db.execute(text("""
        SELECT s.account_name, s.snapshot_date, so.symbol, so.strike_price,
               so.option_type, so.expiration_date, so.contracts_sold,
               so.premium_per_contract AS current_mark, so.original_premium
        FROM sold_options so
        JOIN sold_options_snapshots s ON s.id = so.snapshot_id
        WHERE so.snapshot_id IN (
            SELECT MAX(id) FROM sold_options_snapshots
            WHERE parsing_status = 'success' OR parsing_status IS NOT NULL
            GROUP BY account_name)
          AND (so.expiration_date IS NULL OR so.expiration_date >= :today)
    """), {"today": today}).fetchall()

    hold_rows = db.execute(text("""
        SELECT a.account_name, a.account_type, h.symbol, h.quantity,
               h.current_price, h.cost_basis
        FROM investment_holdings h
        JOIN investment_accounts a
          ON a.account_id = h.account_id AND a.source = h.source
        WHERE a.is_active = 'Y' AND h.quantity > 0 AND h.symbol != 'CASH'
    """)).fetchall()

    data_as_of = max((r.snapshot_date for r in pos_rows), default=None)

    acct_type = {r.account_name: (r.account_type or "").lower() for r in hold_rows}
    price: Dict[str, float] = {}
    holdings: Dict[tuple, dict] = {}
    for r in hold_rows:
        if r.current_price:
            price[r.symbol] = float(r.current_price)
        holdings[(r.account_name, r.symbol)] = {
            "qty": float(r.quantity),
            "cost_basis": float(r.cost_basis) if r.cost_basis else None,
        }

    def is_sheltered(account: str) -> bool:
        return acct_type.get(account, "") in NON_TAXABLE_TYPES

    def stock_price(sym: str, strike: float, mark: float, opt: str):
        """Synced price, else deep-ITM estimate from the mark (flagged)."""
        if sym in price:
            return price[sym], False
        if mark and strike and mark > 0.05 * strike:
            est = strike - mark if opt == "put" else strike + mark
            return max(est, 0.01), True
        return None, False

    items: List[Dict] = []
    board: List[Dict] = []

    def add_item(priority, action, engine, rule, title, account, symbol,
                 detail, why, earn=None, context=None):
        items.append({
            "id": f"v6_{engine}_{account}_{symbol}_{len(items)}",
            "priority": priority, "action": action, "engine": engine,
            "rule": rule, "title": title, "account": account,
            "symbol": symbol, "detail": detail, "why": why, "earn": earn,
            "context": context or {},
        })

    # ---- Engine 4: stuck positions ----------------------------------------
    covered_calls: Dict[tuple, int] = {}
    for p in pos_rows:
        sym, strike = p.symbol, float(p.strike_price)
        mark = float(p.current_mark or 0)
        orig = float(p.original_premium or 0)
        contracts = int(p.contracts_sold)
        opt = (p.option_type or "call").lower()
        exp = p.expiration_date
        dte = (exp - today).days if exp else 999
        account = p.account_name
        stock, estimated = stock_price(sym, strike, mark, opt)
        capture_pct = round((orig - mark) / orig * 100, 1) if orig else None

        if opt == "call":
            covered_calls[(account, sym)] = covered_calls.get((account, sym), 0) + contracts * 100

        board.append({
            "account": account, "symbol": sym, "type": opt, "strike": strike,
            "expiration": str(exp) if exp else None, "dte": dte,
            "contracts": contracts, "stock_price": stock,
            "price_estimated": estimated, "current_mark": mark,
            "original_premium": orig, "capture_pct": capture_pct,
            "itm": bool(stock and ((opt == "call" and stock > strike)
                                   or (opt == "put" and stock < strike))),
        })

        if stock is None:
            continue
        base_ctx = {"symbol": sym, "strike_price": strike, "option_type": opt,
                    "contracts": contracts, "current_price": stock,
                    "expiration_date": str(exp) if exp else "",
                    "current_premium": mark, "profit_percent": capture_pct or 0}

        if opt == "call" and stock > strike:
            intrinsic = stock - strike
            ipct = round(intrinsic / mark * 100, 0) if mark else 100
            spec = f"{sym} {contracts}x CALL ${strike:g} {exp.strftime('%m/%d') if exp else ''} · stock ${stock:,.0f} · {ipct:.0f}% intrinsic"
            if ipct > 80:
                add_item("high", "ALERT", 4, "ITM call >80% intrinsic",
                         f"{sym} call deep ITM — wait", account, sym, spec,
                         "Mostly intrinsic: compression too expensive. Set price alerts "
                         "(-5% evaluate, -10% compress, at-strike full exit). Cut only if thesis changed.",
                         context=base_ctx)
            elif ipct > 60:
                add_item("medium", "ALERT", 4, "ITM call 60-80% intrinsic",
                         f"{sym} call ITM — wait for mean reversion", account, sym, spec,
                         "Stock must move back; do NOT compress (too expensive at this intrinsic level).",
                         context=base_ctx)
            elif ipct > 40:
                shel = is_sheltered(account)
                add_item("high", "ROLL", 4, "ITM call 40-60% intrinsic (crossover)",
                         f"{sym} call — evaluate compression", account, sym, spec,
                         f"Crossover zone: compress (≤4 weeks total, target delta 30, small debit OK) "
                         f"or wait for pullback. {'IRA: compress more aggressively.' if shel else 'Taxable: slightly more patient, but avoid the 12-week trap.'}",
                         context=base_ctx)
            elif dte <= 2:
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
            if dte <= 2:
                add_item("urgent" if itm else "high", "ROLL", 4,
                         "Tested put at expiry",
                         f"{sym} put {'ITM' if itm else 'near ATM'}, expires in {dte}d",
                         account, sym, spec,
                         "1-2 days to expiry and still tested: roll out 1 week; if deeper ITM, roll down+out "
                         "at ~net-zero. Oscillating assumed — do not panic-close (AVGO lesson). Verify no thesis-changing news.",
                         context=base_ctx)
            elif itm and depth >= 10:
                add_item("high", "ROLL", 4, "Deep tested put",
                         f"{sym} put {depth:.0f}% ITM", account, sym, spec,
                         "Roll down and out at net-zero-or-credit while the cycle exhausts; acceptable for multiple "
                         "weeks. Runaway (structural news) would instead mean evaluate closing.",
                         context=base_ctx)
            elif itm:
                add_item("low", "ALERT", 4, "Tested put — theta working",
                         f"{sym} put slightly ITM, {dte}d left", account, sym, spec,
                         "More than 5 days out: let theta work (RSI<30 stocks are already beaten up).",
                         context=base_ctx)

    # ---- Engine 1: uncovered calls ----------------------------------------
    for (account, sym), h in holdings.items():
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
        if sym == "TSLA":
            delta, otm = "10-12", 0.06
            gate = "TSLA carve-out: fire only when RSI > 75; roll at zero cost if ITM, never panic-close."
        elif tier1:
            delta, otm = ("15" if shel else "10-15"), (0.045 if shel else 0.055)
            gate = "Tier 1 hold: income without getting called away."
        else:
            delta, otm = "80", -0.01
            gate = "Tier 2 wheel: assignment is the plan — strike at/near ATM for max premium."
        approx = stock * (1 + otm)
        cost_ps = (h["cost_basis"] / shares) if (h["cost_basis"] and shares) else None
        floor_note = ""
        if cost_ps and approx < cost_ps:
            approx, floor_note = cost_ps, " (raised to cost basis floor)"
        # rough weekly premium: delta% of a ~2% weekly move value
        est = int(n * 100 * stock * 0.0030) if tier1 or sym == "TSLA" else int(n * 100 * stock * 0.012)
        exp = week_ending if today.weekday() <= 2 else _friday(week_ending + timedelta(days=3))
        add_item("medium", "SELL", 1, "Uncovered holdings ≥ 100 shares",
                 f"{sym}: {n} call{'s' if n > 1 else ''} available", account, sym,
                 f"{sym} {n}x CALL ~${approx:,.0f}{floor_note} (delta {delta}) {exp.strftime('%m/%d')} · stock ${stock:,.0f}",
                 f"{int(uncovered):,} uncovered shares earning nothing toward the 1%/mo holdings goal. {gate} "
                 "Entry timing: sell now if RSI>60; RSI<40 wait; RSI<30 do not sell.",
                 earn=est,
                 context={"symbol": sym, "recommended_strike": round(approx, 2),
                          "option_type": "call", "uncovered_contracts": n,
                          "unsold_contracts": n, "current_price": stock,
                          "expiration_date": str(exp), "total_premium": est})

    # ---- assemble ----------------------------------------------------------
    prio_rank = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
    items.sort(key=lambda i: (prio_rank[i["priority"]], _acct_rank(i["account"]), i["symbol"]))
    board.sort(key=lambda b: (b["expiration"] or "9999", _acct_rank(b["account"]), b["symbol"]))
    summary = {p: sum(1 for i in items if i["priority"] == p) for p in prio_rank}
    return {
        "generated_at": str(today), "data_as_of": str(data_as_of) if data_as_of else None,
        "week_ending": str(week_ending), "engine_version": "v6.1-stage1",
        "summary": {**summary, "total": len(items)},
        "items": items, "positions": board,
    }
