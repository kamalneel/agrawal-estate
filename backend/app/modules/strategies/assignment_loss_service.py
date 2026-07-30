"""
Assignment-loss tracking — Neel's idea, 2026-07-22.

Concept: the only concrete, non-theoretical "loss" from a forced options
assignment is the gap between the strike price and the market price AT
THE MOMENT OF ASSIGNMENT — not cost-basis-vs-today's-price, which drifts
forever and reflects a belief the stock recovers (a forecast, not a
fact). This isolates the assignment EVENT's own cost, separate from
premium income (already tracked as the Cash Goal on this page) and
separate from subsequent price action.

For a put assignment: forced to buy at the strike while the market was
lower → loss = max(strike - price_at_assignment, 0) * shares.
For a call assignment: forced to sell at the strike while the market was
higher → loss = max(price_at_assignment - strike, 0) * shares.
Both are the same idea: the option's intrinsic value at the moment it
was exercised against Neel. This is deliberately GROSS — not netted
against the premium collected on that contract — because the premium is
already counted once, elsewhere, as income; netting it here would
double-count it in the opposite direction. Premium is still reported
alongside each event for context.
"""

from datetime import date
from typing import Dict, Optional

from sqlalchemy import text as _text
from sqlalchemy.orm import Session

from app.modules.strategies.technical_signals import _parse_strike, _price_near


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
    skipped_no_price = 0
    for r in rows:
        strike = _parse_strike(r.description)
        opt_type = _parse_option_type(r.description)
        if strike is None or opt_type is None:
            continue
        price, source = _price_near(db, r.account_id, r.symbol, r.transaction_date)
        if price is None:
            skipped_no_price += 1
            continue  # honest omission — no fabricated price

        qty = float(r.quantity)
        loss_per_share = (max(strike - price, 0.0) if opt_type == "put"
                          else max(price - strike, 0.0))
        loss = loss_per_share * qty * 100
        if loss <= 0:
            continue  # assignment happened at/through the strike — no gap to report

        # premium originally collected on this exact contract (same
        # symbol+strike+expiration+type = identical description text)
        premium_row = db.execute(_text("""
            SELECT SUM(amount) AS prem FROM investment_transactions
            WHERE account_id = :acct AND symbol = :sym AND description = :desc
              AND transaction_type = 'STO' AND transaction_date <= :d
        """), {"acct": r.account_id, "sym": r.symbol, "desc": r.description,
               "d": r.transaction_date}).fetchone()
        premium = float(premium_row.prem or 0) if premium_row else 0.0

        events.append({
            "date": r.transaction_date.isoformat(),
            "month": r.transaction_date.strftime("%Y-%m"),
            "account_id": r.account_id,
            "account_name": acct_names.get(r.account_id, r.account_id),
            "symbol": r.symbol,
            "option_type": opt_type,
            "strike": strike,
            "price_at_assignment": round(price, 2),
            "price_source": source,  # "daily" or "weekly" — transparency on precision
            "shares": qty * 100,
            "loss": round(loss, 2),
            "premium_collected": round(premium, 2),
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
        "skipped_no_price_data": skipped_no_price,
    }
