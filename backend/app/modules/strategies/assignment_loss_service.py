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
actually profitable vs. cost and is shown as such, not hidden. Plain
average cost, not FIFO/lot-selection (Neel: "I'm not using this for tax
calculation... this is to truly calculate if I lost money or made
money") — average-cost accounting means a partial sale never changes
the remaining shares' average cost, so summing every BUY through the
assignment date is correct regardless of what else happened to the
position in between.

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

        # Price at assignment: required (and drives loss) for puts;
        # for calls it's context only now (loss comes from cost basis
        # instead), so a miss there doesn't block the call event.
        price, price_source = _price_near(db, r.account_id, r.symbol, r.transaction_date)

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
            cb, cb_source, _ = _cost_basis_near(db, r.account_id, r.symbol, r.transaction_date)
            incomplete = False
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
            "date": r.transaction_date.isoformat(),
            "month": r.transaction_date.strftime("%Y-%m"),
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
    for e in events:
        by_month[e["month"]] = by_month.get(e["month"], 0.0) + e["loss"]

    cur_month = date.today().strftime("%Y-%m")
    return {
        "events": sorted(events, key=lambda e: e["date"], reverse=True),
        "by_month": {k: round(v, 2) for k, v in sorted(by_month.items())},
        "this_month_loss": round(by_month.get(cur_month, 0.0), 2),
        "total_loss": round(sum(by_month.values()), 2),
        "total_premium_on_assigned_contracts": round(sum(e["premium_collected"] for e in events), 2),
        "skipped_no_price_data": skipped_no_data,
    }
