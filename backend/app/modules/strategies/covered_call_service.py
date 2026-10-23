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

from typing import Dict

from sqlalchemy import text as _text
from sqlalchemy.orm import Session

from app.modules.strategies.assignment_loss_service import (
    get_assignment_loss, net_call_premium, wheel_share_split,
)


def get_covered_call_income(db: Session) -> Dict:
    loss = get_assignment_loss(db)["events"]

    # The complement of Put Campaigns' share — one split, so every call is
    # counted once, in exactly one of the two sections.
    wheel_fraction, assigned, acquired = wheel_share_split(db, loss)

    def covered(acct: str, sym: str) -> float:
        return 1.0 - wheel_fraction(acct, sym)

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
    for (acct_id, sym), c in net_call_premium(db).items():
        f = covered(acct_id, sym)
        s = row(sym)
        s["premium_all"] += c["net"]
        if f <= 0:
            continue
        acct_row(s, acct_id)["net_premium"] += c["net"] * f
        s["net_premium"] += c["net"] * f
        s["first"] = min(filter(None, [s["first"], c["first"].isoformat()]))
        s["last"] = max(filter(None, [s["last"], c["last"].isoformat()]))

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
