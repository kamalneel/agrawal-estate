"""
Strategy-policy deviation detection for the Investments page.

Implements the two-book model in docs/INVESTMENTS-PAGE-SPEC.md
("Strategy model & policy deviations"):

- CORE exits (call assignments / sales of durables) must be recovered —
  re-bought, or actively re-entered via short puts. Ledger states:
  recovered / recovering / idle.
- INVENTORY (volatility wheel names) held without an exit call written
  is idle inventory.

Classification is user-declared in data/investment_policy.json.
This module reads existing tables only; no schema changes.
"""

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import text as _text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

POLICY_PATH = Path(__file__).resolve().parents[4] / "data" / "investment_policy.json"


def load_policy() -> Dict:
    with open(POLICY_PATH) as f:
        return json.load(f)


def _latest_open_options(db: Session) -> List[Dict]:
    """Open (unexpired) short options from each account's latest snapshot."""
    rows = db.execute(_text("""
        WITH latest AS (
            SELECT account_name, MAX(snapshot_date) AS snap
            FROM sold_options_snapshots
            GROUP BY account_name
        )
        SELECT s.account_name, o.symbol, o.option_type, o.contracts_sold, o.expiration_date
        FROM sold_options o
        JOIN sold_options_snapshots s ON s.id = o.snapshot_id
        JOIN latest l ON l.account_name = s.account_name AND l.snap = s.snapshot_date
        WHERE o.expiration_date >= CURRENT_DATE
    """)).fetchall()
    return [dict(account_name=r.account_name, symbol=r.symbol, option_type=r.option_type,
                 contracts=int(r.contracts_sold or 0)) for r in rows]


def _account_names(db: Session) -> Dict[str, str]:
    rows = db.execute(_text(
        "SELECT account_id, account_name FROM investment_accounts"
    )).fetchall()
    return {r.account_id: r.account_name for r in rows}


def _current_prices(db: Session) -> Dict[str, float]:
    """Current price per symbol, from the most recently updated row.

    Was `MAX(current_price)` until 2026-08-08, which returns the *stalest*
    price whenever a dead feed happens to hold a higher number. Alisha's
    Brokerage has not updated since 2026-01-07 (known data gap, see the page
    spec), so MAX served TSLA at $423.74 from June against a live $328.55 —
    a 29% error feeding the core-exit gap math on this page.
    """
    rows = db.execute(_text("""
        SELECT DISTINCT ON (symbol) symbol, current_price AS px
        FROM investment_holdings
        WHERE current_price IS NOT NULL
        ORDER BY symbol, last_updated DESC NULLS LAST
    """)).fetchall()
    return {r.symbol: float(r.px) for r in rows}


def get_policy_deviations(db: Session) -> Dict:
    policy = load_policy()
    core = set(policy.get("core", []))
    inventory = set(policy.get("inventory", []))
    ignore = set(policy.get("ignore", []))
    window_days = int(policy.get("core_exit_window_days", 365))
    cutoff = date.today() - timedelta(days=window_days)

    acct_names = _account_names(db)
    prices = _current_prices(db)
    open_opts = _latest_open_options(db)

    def open_contracts(account_name: Optional[str], symbol: str, option_type: str) -> int:
        return sum(o["contracts"] for o in open_opts
                   if o["symbol"] == symbol and o["option_type"] == option_type
                   and (account_name is None or o["account_name"] == account_name))

    # ---------------- Core exit ledger ----------------
    # Exit events: per (account, symbol, sale_date) from the lot engine.
    events = db.execute(_text("""
        SELECT l.account_id, l.symbol, s.sale_date,
               SUM(s.quantity_sold) AS shares,
               SUM(s.proceeds) / NULLIF(SUM(s.quantity_sold), 0) AS sale_px
        FROM stock_lot_sale s
        JOIN stock_lot l ON l.lot_id = s.lot_id
        WHERE s.sale_date >= :cutoff
        GROUP BY l.account_id, l.symbol, s.sale_date
        ORDER BY l.account_id, l.symbol, s.sale_date
    """), {"cutoff": cutoff}).fetchall()

    # Post-event acquisitions (new lots) for FIFO allocation to exits.
    acquisitions = db.execute(_text("""
        SELECT account_id, symbol, purchase_date, SUM(quantity) AS shares
        FROM stock_lot
        WHERE purchase_date >= :cutoff
        GROUP BY account_id, symbol, purchase_date
        ORDER BY account_id, symbol, purchase_date
    """), {"cutoff": cutoff}).fetchall()

    acq_by_key: Dict[tuple, List[Dict]] = {}
    for a in acquisitions:
        acq_by_key.setdefault((a.account_id, a.symbol), []).append(
            {"date": a.purchase_date, "shares": float(a.shares)})

    # Put premiums collected per (account, symbol) since a date — decision
    # metric input (cost-of-waiting offset), not income reporting.
    def put_premium_since(account_id: str, symbol: str, since: date) -> float:
        row = db.execute(_text("""
            SELECT COALESCE(SUM(amount), 0) AS prem
            FROM investment_transactions
            WHERE account_id = :acct AND symbol = :sym
              AND transaction_type IN ('STO', 'BTC')
              AND description ILIKE '%put%'
              AND transaction_date > :since
        """), {"acct": account_id, "sym": symbol, "since": since}).fetchone()
        return float(row.prem or 0)

    core_exits = []
    for (acct, sym), _grp in {(e.account_id, e.symbol): None for e in events
                              if e.symbol in core}.items():
        # materiality floor: fractional/sub-share events (DRIP slivers,
        # split dust) don't belong on a decision ledger
        sym_events = [e for e in events
                      if e.account_id == acct and e.symbol == sym and float(e.shares) >= 1]
        acqs = [dict(a) for a in acq_by_key.get((acct, sym), [])]
        for ev in sym_events:
            sold = float(ev.shares)
            # FIFO: consume acquisitions dated after this event
            recovered = 0.0
            for a in acqs:
                if a["date"] <= ev.sale_date or a["shares"] <= 0:
                    continue
                take = min(a["shares"], sold - recovered)
                a["shares"] -= take
                recovered += take
                if recovered >= sold:
                    break
            unrecovered = max(sold - recovered, 0.0)
            px_now = prices.get(sym)
            sale_px = float(ev.sale_px or 0)
            gap = round((px_now - sale_px) * unrecovered, 2) if (px_now and unrecovered) else None
            puts_open = open_contracts(acct_names.get(acct), sym, "put")
            if unrecovered <= 0.0001:
                status = "recovered"
            elif puts_open > 0:
                status = "recovering"
            else:
                status = "idle"
            core_exits.append({
                "account_id": acct,
                "account_name": acct_names.get(acct, acct),
                "symbol": sym,
                "exit_date": ev.sale_date.isoformat(),
                "shares_sold": round(sold, 4),
                "sale_px": round(sale_px, 2),
                "price_now": px_now,
                "shares_recovered": round(recovered, 4),
                "shares_unrecovered": round(unrecovered, 4),
                "open_put_contracts": puts_open,
                "put_premium_since": round(put_premium_since(acct, sym, ev.sale_date), 2),
                "gap": gap,
                "days_since_exit": (date.today() - ev.sale_date).days,
                "status": status,
            })
    core_exits.sort(key=lambda x: ({"idle": 0, "recovering": 1, "recovered": 2}[x["status"]],
                                   -(x["gap"] or 0)))

    # ---------------- Idle inventory ----------------
    holdings = db.execute(_text("""
        SELECT account_id, symbol, quantity
        FROM investment_holdings
        WHERE quantity >= 100
    """)).fetchall()

    idle_inventory = []
    for h in holdings:
        if h.symbol not in inventory:
            continue
        acct_name = acct_names.get(h.account_id, h.account_id)
        lots = int(float(h.quantity) // 100)
        calls_open = open_contracts(acct_name, h.symbol, "call")
        uncovered = lots - calls_open
        if uncovered > 0:
            px = prices.get(h.symbol)
            idle_inventory.append({
                "account_id": h.account_id,
                "account_name": acct_name,
                "symbol": h.symbol,
                "shares": float(h.quantity),
                "coverable_contracts": lots,
                "open_call_contracts": calls_open,
                "uncovered_contracts": uncovered,
                "idle_value": round(uncovered * 100 * px, 2) if px else None,
            })
    idle_inventory.sort(key=lambda x: -(x["idle_value"] or 0))

    # ---------------- Distraction P&L (aggregate) ----------------
    # Total gap on unrecovered core exits vs. put income earned in the
    # inventory book over the same window.
    total_gap = sum(e["gap"] or 0 for e in core_exits if e["status"] != "recovered")
    earliest_open_exit = min((e["exit_date"] for e in core_exits if e["status"] != "recovered"),
                             default=None)
    inventory_put_income = 0.0
    if earliest_open_exit and inventory:
        row = db.execute(_text("""
            SELECT COALESCE(SUM(amount), 0) AS prem
            FROM investment_transactions
            WHERE transaction_type IN ('STO', 'BTC')
              AND description ILIKE '%put%'
              AND symbol = ANY(:syms)
              AND transaction_date > :since
        """), {"syms": list(inventory), "since": earliest_open_exit}).fetchone()
        inventory_put_income = float(row.prem or 0)

    # Symbols held but not classified — surfaced for the user to sort.
    held_symbols = {h.symbol for h in db.execute(_text(
        "SELECT DISTINCT symbol FROM investment_holdings WHERE quantity > 0")).fetchall()
        for h in [h]}
    unclassified = sorted(held_symbols - core - inventory - ignore)

    return {
        "as_of": date.today().isoformat(),
        "policy": {"core": sorted(core), "inventory": sorted(inventory),
                   "unclassified": unclassified},
        "core_exits": core_exits,
        "idle_inventory": idle_inventory,
        "distraction": {
            "open_exit_gap": round(total_gap, 2),
            "inventory_put_income_since": round(inventory_put_income, 2),
            "since": earliest_open_exit,
        },
    }
