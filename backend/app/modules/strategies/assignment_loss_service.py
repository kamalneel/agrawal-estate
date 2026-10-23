"""
Assignment-loss tracking — Neel's idea, 2026-07-22. Redefined for calls
2026-08-08 (see below) after Neel flagged the original call formula as
not a real loss.

PUT assignment (unchanged): forced to buy at the strike while the market
was lower that moment → loss = max(strike - price_at_assignment, 0) *
shares. A put assignment creates a BRAND-NEW lot — there's no prior
purchase price to compare against, so strike-vs-market-that-moment is
the only meaningful "did I overpay" question, and it's real: you could
have bought the same shares cheaper in the open market right then.

CALL assignment (redefined 2026-08-08): forced to SELL shares you
already owned. Strike-vs-market-that-moment answered "vs. just closing
the position myself, what did the assignment mechanism cost me" — a
real number, but Neel's point: it isn't "a loss" in any meaningful
sense (2026-08-08, re: an $89 SPCX example: "that doesn't make sense...
The $89 loss is not a loss"). What actually answers "did I lose or make
money" for a call is cost_basis vs. strike — what you originally paid
for the shares vs. what you were forced to sell them for. So for calls:
loss = (cost_basis_per_share - strike) * shares — SIGNED (not clamped
at zero like puts): positive = real loss, negative = the assignment was
actually profitable vs. cost and is shown as such, not hidden.

Cost basis for calls (redefined 2026-09-20): the HIGHEST-COST lots first,
in every account — "we know at what price we bought that Tesla based on
the last purchase; the assumption will be that we sold the one we bought
at the highest price, not the average or the lowest" (Neel, after the
9/18 TSLA assignments showed +$63K on average cost while the $435/$375
lots delivered made them a −$28K loss). Lots come from the lot engine
(stock_lot, plus what it already consumed for this sale), consumed
highest cost first; `cost_basis_per_share` is the average of the lots
actually consumed. Falls back to the old average-cost figure (source
'live' / 'reconstructed') only when no lots are on file. The 2026-08-08
average-cost definition is superseded.

The headline is shown as puts + calls (Neel, 2026-09-20): `by_type`.

Both loss figures are deliberately GROSS — not netted against premium,
which is already counted once, elsewhere, as income; netting here would
double-count it in the opposite direction. `cost_basis_per_share` is
reported as its own field (source 'live' = Robinhood's own
average_buy_price captured at sync time since 2026-08-08; 'reconstructed'
= weighted average of BUY transaction history for assignments before
that, flagged `incomplete` when the reconstruction can't account for
all the assigned shares — a real gap, not hidden).

`premium_collected` (redefined 2026-08-12): the true NET premium across
the WHOLE weekly roll chain leading to the assigned contract — every
STO open minus every BTC close, back to the first time this position was
ever sold — not just the final leg's own STO. The original version only
matched transactions with an identical description (same strike +
expiration) as the assigned contract, which in practice meant "the one
STO that opened this exact week's contract" — looked like a total,
wasn't one (Neel, re: a $9,005 figure that turned out to be a single
transaction). See `_walk_roll_chain` in technical_signals.py for the
walk-back. Also used, batched, by the open-positions board
(v6_engine.py) for the same figure on still-open contracts.
"""

from datetime import date
from typing import Dict, Optional

from sqlalchemy import text as _text
from sqlalchemy.orm import Session

from app.modules.strategies.technical_signals import (
    _parse_strike, _parse_expiration, _price_near, _cost_basis_near, _reconstruct_cost_basis,
    _index_roll_transactions, _walk_roll_chain,
)


def _parse_option_type(description: Optional[str]) -> Optional[str]:
    if not description:
        return None
    d = description.lower()
    if "put" in d:
        return "put"
    if "call" in d:
        return "call"
    return None


def assignment_date(recorded: date, description: Optional[str]) -> date:
    """The day the assignment actually happened: the recorded date, but never
    later than the contract's expiry. MCP-inferred rows carry the sync date
    that noticed the vanished position, which can be days after expiry
    (CBRS $165 put, expired Fri 10/9/2026, recorded Sun 10/11). Early
    assignments, recorded before expiry, keep their own date."""
    exp_d = _parse_expiration(description)
    return min(recorded, exp_d) if exp_d else recorded


def get_assignment_loss(db: Session) -> Dict:
    # DISTINCT ON collapses provisional MCP-inferred detections (source
    # 'robinhood_mcp_inferred[_pending_confirmation]') against the same
    # real-world event once the official CSV's confirmed row lands —
    # the two never share a transaction_date (detection necessarily lags
    # the true settle date by ~1 sync), so a date-keyed dedup can't catch
    # this pairing; (account_id, symbol, description) identifies the
    # contract regardless of which row recorded it. Prefer the
    # CSV-confirmed 'robinhood' source when both exist (2026-07-28
    # incident: GOOGL + GOOG puts each double-counted this way).
    rows = db.execute(_text("""
        SELECT DISTINCT ON (account_id, symbol, description)
               transaction_date, account_id, symbol, description, quantity
        FROM investment_transactions
        WHERE transaction_type = 'OASGN'
        ORDER BY account_id, symbol, description,
                 (source NOT LIKE 'robinhood_mcp_inferred%') DESC,
                 transaction_date ASC
    """)).fetchall()

    acct_names = {r.account_id: r.account_name for r in db.execute(_text(
        "SELECT account_id, account_name FROM investment_accounts")).fetchall()}

    events = []
    skipped_no_data = 0
    for r in rows:
        strike = _parse_strike(r.description)
        opt_type = _parse_option_type(r.description)
        if strike is None or opt_type is None:
            continue
        qty = float(r.quantity)
        shares = qty * 100
        # An assignment cannot happen after the contract expires. MCP-inferred
        # rows carry the SYNC date that noticed the vanished position, which
        # can be days later — the CBRS $165 put expiring Fri 10/9/2026 was
        # recorded 10/11 and priced at Monday's $146.62 instead of Friday's
        # $164.17, a $1,838 "loss" for a real $83 (Neel, 2026-10-12).
        when = assignment_date(r.transaction_date, r.description)

        # Price at assignment: required (and drives loss) for puts;
        # for calls it's context only now (loss comes from cost basis
        # instead), so a miss there doesn't block the call event.
        price, price_source = _price_near(db, r.account_id, r.symbol, when)

        cost_basis_per_share = cost_basis_source = cost_basis_incomplete = None
        if opt_type == "put":
            if price is None:
                skipped_no_data += 1
                continue  # honest omission — no fabricated price
            loss = max(strike - price, 0.0) * shares
            if loss <= 0:
                continue  # assignment happened at/through the strike — no gap to report
        else:
            # NOT sourced from robinhood_realized_trades, despite that table
            # existing and covering these events (tried and reverted
            # 2026-08-14). Robinhood's realized_gain folds the assigned
            # contract's premium INTO the stock sale: it booked the
            # 2026-05-22 NFLX assignment at $89.64948/share against an
            # $87.00 strike, and the $1,325.74 difference is exactly the
            # premium on that contract (STO 3 @ 794.85 + 2 @ 529.89 =
            # $1,324.74). Using it double-counts premium, which is already
            # income in the options stream — precisely what the module
            # docstring forbids. The table is still populated for
            # verification; it just cannot be this figure.
            # Highest-cost lots first (Neel, 2026-09-20). Lots as the book
            # stood before this sale, consumed dearest-first; the per-share
            # figure is the average of what was consumed.
            cb = cb_source = None
            incomplete = False
            try:
                from app.modules.tax.assignment_tax_notice_service import _lots_before_sale, _consume
                lots = _lots_before_sale(db, r.account_id, r.symbol, r.transaction_date)
                if lots:
                    high = _consume(sorted(lots, key=lambda l: (-l[2], l[0])), shares, strike, r.transaction_date)
                    used = sum(l["shares"] for l in high["lots"])
                    if used > 0:
                        cb = sum(l["shares"] * l["cost_per_share"] for l in high["lots"]) / used
                        cb_source = "highest_cost_lots"
                        incomplete = high["short"] > 1e-6
            except Exception:
                cb = None
            if cb is None:
                cb, cb_source, _ = _cost_basis_near(db, r.account_id, r.symbol, r.transaction_date)
            if cb is None:
                cb, incomplete = _reconstruct_cost_basis(
                    db, r.account_id, r.symbol, r.transaction_date, shares)
            if cb is None:
                skipped_no_data += 1
                continue  # honest omission — no fabricated cost basis
            cb_source = cb_source or "reconstructed"
            cost_basis_per_share = round(cb, 2)
            cost_basis_source = cb_source
            cost_basis_incomplete = incomplete
            # Signed, unlike puts: a call sold above what it cost is a
            # real gain, not something to clamp away (Neel, 2026-08-08).
            loss = (cb - strike) * shares

        # True net premium across the WHOLE roll chain that led to this
        # contract, not just its own STO (Neel, 2026-08-12: a $9,005
        # "premium collected" figure turned out to be one transaction, not
        # a total — he expected "since I first sold this put and rolled it
        # week over week, what's the total" — see _walk_roll_chain for the
        # full walk-back and why it nets STO opens against BTC closes
        # rather than summing STOs alone). Identity is (strike, expiration)
        # parsed from this exact OASGN's own description, not raw text —
        # same scheme _index_roll_transactions indexes by, so the lookup
        # below is a plain dict get, not another query.
        expiration = _parse_expiration(r.description)
        sto_by_leg, btc_by_date = _index_roll_transactions(db, r.account_id, r.symbol, opt_type)
        final_leg = sto_by_leg.get((strike, expiration)) if expiration else None
        if final_leg:
            chain = _walk_roll_chain(sto_by_leg, btc_by_date, strike, expiration,
                                     final_leg["date"], final_leg["amount"])
            premium, chain_weeks = chain["net_premium"], chain["chain_weeks"]
            premium_incomplete = chain["incomplete"]
        else:
            premium, chain_weeks, premium_incomplete = 0.0, 0, False

        events.append({
            "date": when.isoformat(),
            "month": when.strftime("%Y-%m"),
            "account_id": r.account_id,
            "account_name": acct_names.get(r.account_id, r.account_id),
            "symbol": r.symbol,
            "option_type": opt_type,
            "strike": strike,
            "price_at_assignment": round(price, 2) if price is not None else None,
            "price_source": price_source,  # "daily" or "weekly" — transparency on precision
            "shares": shares,
            "loss": round(loss, 2),  # signed for calls; puts always > 0 (filtered above)
            "premium_collected": round(premium, 2),  # net across the whole roll chain
            "premium_chain_weeks": chain_weeks,
            "premium_incomplete": premium_incomplete,  # chain hit a real ledger gap, not a clean start
            "cost_basis_per_share": cost_basis_per_share,
            "cost_basis_source": cost_basis_source,  # "live" | "reconstructed" | None
            "cost_basis_incomplete": cost_basis_incomplete,
        })

    by_month: Dict[str, float] = {}
    by_month_type: Dict[str, Dict[str, float]] = {}
    for e in events:
        by_month[e["month"]] = by_month.get(e["month"], 0.0) + e["loss"]
        bt = by_month_type.setdefault(e["month"], {"put": 0.0, "call": 0.0})
        bt[e["option_type"]] += e["loss"]

    cur_month = date.today().strftime("%Y-%m")
    cur_t = by_month_type.get(cur_month, {"put": 0.0, "call": 0.0})
    return {
        "events": sorted(events, key=lambda e: e["date"], reverse=True),
        "by_month": {k: round(v, 2) for k, v in sorted(by_month.items())},
        "by_month_type": {k: {t: round(v, 2) for t, v in d.items()} for k, d in sorted(by_month_type.items())},
        "this_month_loss": round(by_month.get(cur_month, 0.0), 2),
        "this_month_puts": round(cur_t["put"], 2),
        "this_month_calls": round(cur_t["call"], 2),
        "total_loss": round(sum(by_month.values()), 2),
        "total_puts": round(sum(d["put"] for d in by_month_type.values()), 2),
        "total_calls": round(sum(d["call"] for d in by_month_type.values()), 2),
        "total_premium_on_assigned_contracts": round(sum(e["premium_collected"] for e in events), 2),
        "skipped_no_price_data": skipped_no_data,
    }


def wheel_share_split(db: Session, events: list):
    """How a stock's calls divide between the wheel and covered calls, per
    account: put-assigned shares ÷ all shares ever acquired there (lots).
    Shared by Put Campaigns (the wheel's part) and Covered Call Income (the
    rest) so every call is counted once, in exactly one of the two.
    Returns (wheel_fraction(acct, sym) -> 0..1, assigned, acquired)."""
    from collections import defaultdict
    assigned = defaultdict(float)
    for e in events:
        if e["option_type"] == "put":
            assigned[(e["account_id"], e["symbol"])] += e["shares"]
    acquired = {(r.account_id, r.symbol): float(r.q) for r in db.execute(_text(
        "SELECT account_id, symbol, SUM(quantity) AS q FROM stock_lot GROUP BY 1, 2"))}

    def wheel_fraction(acct: str, sym: str) -> float:
        a = assigned.get((acct, sym), 0.0)
        tot = acquired.get((acct, sym), 0.0)
        if a <= 0:
            return 0.0
        return 1.0 if tot <= 0 else min(a / tot, 1.0)

    return wheel_fraction, dict(assigned), acquired


def net_call_premium(db: Session) -> Dict:
    """(account_id, symbol) -> {net, first, last} for every call sold minus
    every call bought back. The Income page's own filter (STO/BTC/STC/BTO
    joined to the account on source, description contains "call")."""
    return {(r.account_id, r.symbol): {"net": float(r.net or 0), "first": r.first, "last": r.last}
            for r in db.execute(_text("""
        SELECT it.account_id, it.symbol, SUM(it.amount) AS net,
               MIN(it.transaction_date) AS first, MAX(it.transaction_date) AS last
        FROM investment_transactions it
        JOIN investment_accounts ia ON it.account_id = ia.account_id AND it.source = ia.source
        WHERE it.transaction_type IN ('STO', 'BTC', 'STC', 'BTO') AND it.description ILIKE '%call%'
        GROUP BY 1, 2"""))}


def get_put_campaigns(db: Session) -> Dict:
    """Put campaigns, per stock — Neel, 2026-10-22: the assignment loss is
    a snapshot; "that stock then goes up or down", so what is it worth now?
    The wheel-trader view: for every put that was assigned, the shares'
    result since (still held → today's price; sold → what they sold for)
    plus the net premium collected across the roll chain that led to it.

        shares_result = held × today + sale proceeds − strike × shares
        campaign      = shares_result + put premium + call premium
        adjusted basis = strike − (put premium + call premium) / shares

    Each assignment is traced to its own lot (account, symbol, cost = the
    strike, bought within 3 days of the assignment) — the lot engine knows
    whether those shares are still held and, if not, what they fetched.
    Which lot a later sale consumed follows the lot engine's method (FIFO
    or highest-cost), so in an account that also held bought shares a sale
    may be attributed to the other lot; the per-stock total is unaffected.
    No lot match → valued as still held at today's price, flagged
    `traced: False`.

    Call premium (2026-10-23, Neel: "fold the calls into Put Campaigns"):
    the wheel's third phase. In each account a stock's net call premium is
    split by shares — put-assigned ÷ all acquired (wheel_share_split); the
    rest is Covered Call Income's. Within an account the wheel part is
    shared among that account's assignments by shares. A call assignment's
    sale is already in shares_result (the lot's proceeds), so no upside
    term is needed here: the campaign counts the cash that actually moved.
    """
    all_events = get_assignment_loss(db)["events"]
    events = [e for e in all_events if e["option_type"] == "put"]
    wheel_fraction, assigned, _acq = wheel_share_split(db, all_events)
    calls = net_call_premium(db)

    held_px = {(r.account_id, r.symbol): float(r.current_price) for r in db.execute(_text(
        "SELECT account_id, symbol, current_price FROM investment_holdings WHERE current_price IS NOT NULL"))}
    last_px = {r.symbol: (float(r.close_price), r.price_date) for r in db.execute(_text("""
        SELECT DISTINCT ON (symbol) symbol, close_price, price_date
        FROM symbol_price_history ORDER BY symbol, price_date DESC"""))}
    any_held = {}
    for (_a, s), p in held_px.items():
        any_held.setdefault(s, p)

    used_lots = set()
    rows = []
    for e in sorted(events, key=lambda e: e["date"]):
        lots = db.execute(_text("""
            SELECT l.lot_id, l.quantity, l.quantity_remaining,
                   COALESCE((SELECT SUM(s.quantity_sold) FROM stock_lot_sale s WHERE s.lot_id = l.lot_id), 0) AS sold,
                   COALESCE((SELECT SUM(s.proceeds) FROM stock_lot_sale s WHERE s.lot_id = l.lot_id), 0) AS proceeds,
                   (SELECT MAX(s.sale_date) FROM stock_lot_sale s WHERE s.lot_id = l.lot_id) AS last_sale
            FROM stock_lot l
            WHERE l.account_id = :a AND l.symbol = :s
              AND ABS(l.purchase_date - CAST(:d AS date)) <= 3
              AND ABS(l.cost_per_share - :k) < 0.02
            ORDER BY ABS(l.quantity - :q), ABS(l.purchase_date - CAST(:d AS date))
        """), dict(a=e["account_id"], s=e["symbol"], d=e["date"], k=e["strike"], q=e["shares"])).fetchall()
        lot = next((l for l in lots if l.lot_id not in used_lots), None)

        price = held_px.get((e["account_id"], e["symbol"])) or any_held.get(e["symbol"])
        if price is None and e["symbol"] in last_px:
            price = last_px[e["symbol"]][0]

        shares = e["shares"]
        cost = e["strike"] * shares
        if lot is not None:
            used_lots.add(lot.lot_id)
            scale = shares / float(lot.quantity) if float(lot.quantity) else 1.0
            sold = float(lot.sold) * scale
            proceeds = float(lot.proceeds) * scale
            held = max(shares - sold, 0.0)
            traced = True
            last_sale = lot.last_sale.isoformat() if lot.last_sale else None
        else:
            sold, proceeds, held, traced, last_sale = 0.0, 0.0, shares, False, None

        if held > 1e-6 and price is None:
            shares_result = None   # honest gap — no fabricated price
        else:
            shares_result = held * (price or 0.0) + proceeds - cost

        # This assignment's share of the account's wheel call premium.
        key = (e["account_id"], e["symbol"])
        acct_calls = calls.get(key, {}).get("net", 0.0) * wheel_fraction(*key)
        call_premium = acct_calls * shares / assigned[key] if assigned.get(key) else 0.0
        premium_ps = (e["premium_collected"] + call_premium) / shares if shares else 0.0

        rows.append({
            "date": e["date"], "account_name": e["account_name"], "symbol": e["symbol"],
            "strike": e["strike"], "shares": shares,
            "price_at_assignment": e["price_at_assignment"],
            "loss_at_assignment": -e["loss"],               # signed: negative = loss
            "shares_held": round(held, 4), "shares_sold": round(sold, 4),
            "sale_proceeds": round(proceeds, 2), "last_sale": last_sale,
            "price_today": price,
            "shares_result": round(shares_result, 2) if shares_result is not None else None,
            "premium_collected": e["premium_collected"],
            "premium_chain_weeks": e["premium_chain_weeks"],
            "premium_incomplete": e["premium_incomplete"],
            "call_premium": round(call_premium, 2),
            "adjusted_basis": round(e["strike"] - premium_ps, 2),
            "campaign": round(shares_result + e["premium_collected"] + call_premium, 2) if shares_result is not None else None,
            "traced": traced,
        })

    by_sym: Dict[str, Dict] = {}
    for r in rows:
        s = by_sym.setdefault(r["symbol"], {
            "symbol": r["symbol"], "assignments": 0, "shares": 0.0, "shares_held": 0.0,
            "strike_x_shares": 0.0, "loss_at_assignment": 0.0, "shares_result": 0.0,
            "premium_collected": 0.0, "call_premium": 0.0, "campaign": 0.0, "unpriced": 0, "untraced": 0,
            "price_today": r["price_today"], "first": r["date"], "last": r["date"], "events": []})
        s["assignments"] += 1
        s["shares"] += r["shares"]
        s["shares_held"] += r["shares_held"]
        s["strike_x_shares"] += r["strike"] * r["shares"]
        s["loss_at_assignment"] += r["loss_at_assignment"]
        s["premium_collected"] += r["premium_collected"]
        s["call_premium"] += r["call_premium"]
        s["first"], s["last"] = min(s["first"], r["date"]), max(s["last"], r["date"])
        if r["shares_result"] is None:
            s["unpriced"] += 1
        else:
            s["shares_result"] += r["shares_result"]
            s["campaign"] += r["campaign"]
        if not r["traced"]:
            s["untraced"] += 1
        s["events"].append(r)

    stocks = []
    for s in by_sym.values():
        sxs = s.pop("strike_x_shares")
        s["avg_strike"] = round(sxs / s["shares"], 2) if s["shares"] else None
        s["adjusted_basis"] = (round((sxs - s["premium_collected"] - s["call_premium"]) / s["shares"], 2)
                               if s["shares"] else None)
        for k in ("loss_at_assignment", "shares_result", "premium_collected", "call_premium", "campaign"):
            s[k] = round(s[k], 2)
        s["status"] = "held" if s["shares_held"] >= s["shares"] - 1e-6 else "closed" if s["shares_held"] < 1e-6 else "partly sold"
        s["events"].sort(key=lambda r: r["date"], reverse=True)
        stocks.append(s)
    stocks.sort(key=lambda s: s["campaign"])

    tot = lambda k: round(sum(s[k] for s in stocks), 2)
    return {
        "stocks": stocks,
        "totals": {k: tot(k) for k in ("loss_at_assignment", "shares_result", "premium_collected", "call_premium", "campaign")},
        "assignments": len(rows),
        "unpriced": sum(s["unpriced"] for s in stocks),
        "untraced": sum(s["untraced"] for s in stocks),
    }
