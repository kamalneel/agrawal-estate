"""
Covered Call Income — Neel, 2026-10-23. Calls sold on shares you hold to
keep, measured the way a covered-call overlay is: against yourself holding
the same shares without the calls.

    net = net premium (every STO − every BTC, so roll buy-backs are in)
          − upside given up (call assigned below the market that day)

Calls still open are NOT marked to what they would cost to close: that
assumes exiting today, which Neel does not plan to do (2026-10-23: "that
assumes that I'm going to sell everything and exit today"). Their premium
counts as received; any upside they give up lands when they are assigned.

"Upside given up" is strike vs. market at a call assignment. On 2026-08-08
Neel rejected that as the call's assignment LOSS ("the $89 loss is not a
loss") — it is not money he had. It is the price of capping the upside,
which is exactly what this view asks: did selling calls earn more than it
gave away?

Wheel shares are kept out. Shares that came from an assigned put belong to
the Put Campaign (get_put_campaigns), so in each account a stock's calls
are counted in proportion to the shares that were bought rather than put
to you: covered = (lot shares ever acquired − put-assigned shares) / lot
shares ever acquired. A stock held only through puts (SOXL, CBRS, …) is
left out entirely. Proportional by shares, not by time held — an
approximation, reported per stock as `covered_pct`.

Premium uses the Income page's own filter (STO/BTC/STC/BTO joined to the
account on source, description contains "call"), so the two cannot drift.
"""

from collections import defaultdict
from typing import Dict

from sqlalchemy import text as _text
from sqlalchemy.orm import Session

from app.modules.strategies.assignment_loss_service import get_assignment_loss


def get_covered_call_income(db: Session) -> Dict:
    loss = get_assignment_loss(db)["events"]

    # Put-assigned vs. all shares ever acquired, per account + symbol.
    assigned = defaultdict(float)
    for e in loss:
        if e["option_type"] == "put":
            assigned[(e["account_id"], e["symbol"])] += e["shares"]
    acquired = {(r.account_id, r.symbol): float(r.q) for r in db.execute(_text(
        "SELECT account_id, symbol, SUM(quantity) AS q FROM stock_lot GROUP BY 1, 2"))}

    def covered(acct: str, sym: str) -> float:
        a = assigned.get((acct, sym), 0.0)
        tot = acquired.get((acct, sym), 0.0)
        if tot <= 0:
            return 0.0 if a > 0 else 1.0
        return max(tot - a, 0.0) / tot

    acct_names = {r.account_id: r.account_name for r in db.execute(_text(
        "SELECT account_id, account_name FROM investment_accounts"))}

    stocks: Dict[str, Dict] = {}

    def row(sym: str) -> Dict:
        return stocks.setdefault(sym, {
            "symbol": sym, "net_premium": 0.0, "premium_all": 0.0, "upside_given_up": 0.0,
            "assignments": 0, "shares_called": 0.0,
            "unpriced_assignments": 0, "first": None, "last": None, "accounts": {}})

    def acct_row(s: Dict, acct: str) -> Dict:
        return s["accounts"].setdefault(acct, {
            "account_name": acct_names.get(acct, acct), "covered_pct": round(covered(acct, s["symbol"]) * 100, 1),
            "net_premium": 0.0, "upside_given_up": 0.0})

    # 1. Net call premium, per account + symbol.
    for r in db.execute(_text("""
        SELECT it.account_id, it.symbol, SUM(it.amount) AS net,
               MIN(it.transaction_date) AS first, MAX(it.transaction_date) AS last
        FROM investment_transactions it
        JOIN investment_accounts ia ON it.account_id = ia.account_id AND it.source = ia.source
        WHERE it.transaction_type IN ('STO', 'BTC', 'STC', 'BTO') AND it.description ILIKE '%call%'
        GROUP BY 1, 2
    """)):
        f = covered(r.account_id, r.symbol)
        s = row(r.symbol)
        s["premium_all"] += float(r.net or 0)
        if f <= 0:
            continue
        a = acct_row(s, r.account_id)
        a["net_premium"] += float(r.net or 0) * f
        s["net_premium"] += float(r.net or 0) * f
        s["first"] = min(filter(None, [s["first"], r.first.isoformat()]))
        s["last"] = max(filter(None, [s["last"], r.last.isoformat()]))

    # 2. Upside given up at each call assignment.
    events = []
    for e in loss:
        if e["option_type"] != "call":
            continue
        f = covered(e["account_id"], e["symbol"])
        if f <= 0:
            continue
        s = row(e["symbol"])
        s["assignments"] += 1
        s["shares_called"] += e["shares"] * f
        px = e["price_at_assignment"]
        if px is None:
            s["unpriced_assignments"] += 1
            given = None
        else:
            given = max(px - e["strike"], 0.0) * e["shares"] * f
            s["upside_given_up"] += given
            acct_row(s, e["account_id"])["upside_given_up"] += given
        events.append({"date": e["date"], "account_name": e["account_name"], "symbol": e["symbol"],
                       "strike": e["strike"], "price_at_assignment": px, "shares": e["shares"],
                       "covered_pct": round(f * 100, 1),
                       "upside_given_up": round(given, 2) if given is not None else None})

    out = []
    for s in stocks.values():
        if not s["accounts"]:
            continue   # every share came from a put — the Put Campaign's
        s["net"] = s["net_premium"] - s["upside_given_up"]
        # Share-weighted across accounts: bought shares / all shares ever acquired.
        acq = sum(q for (a, sym), q in acquired.items() if sym == s["symbol"])
        bought = sum(max(q - assigned.get((a, sym), 0.0), 0.0) for (a, sym), q in acquired.items() if sym == s["symbol"])
        s["covered_pct"] = round(100 * bought / acq, 1) if acq else 100.0
        for k in ("net_premium", "premium_all", "upside_given_up", "net", "shares_called"):
            s[k] = round(s[k], 2)
        accts = []
        for a in s["accounts"].values():
            a["net"] = round(a["net_premium"] - a["upside_given_up"], 2)
            for k in ("net_premium", "upside_given_up"):
                a[k] = round(a[k], 2)
            accts.append(a)
        s["accounts"] = sorted(accts, key=lambda a: a["net"])
        s["events"] = sorted([e for e in events if e["symbol"] == s["symbol"]], key=lambda e: e["date"], reverse=True)
        out.append(s)
    out.sort(key=lambda s: s["net"])

    tot = lambda k: round(sum(s[k] for s in out), 2)
    return {
        "stocks": out,
        "totals": {k: tot(k) for k in ("net_premium", "upside_given_up", "net")},
        "unpriced_assignments": sum(s["unpriced_assignments"] for s in out),
    }
