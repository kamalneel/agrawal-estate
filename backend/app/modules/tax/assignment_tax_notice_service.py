"""Call-assignment tax-lot notices.

WHY (Neel, 2026-09-13)
----------------------
A covered call that gets assigned SELLS shares, and in a taxable account
which shares were sold decides the tax. Robinhood disposes the delivered
shares by the account's default tax-lot method — FIFO unless changed —
and FIFO reaches the oldest, lowest-basis lots first. On Jaya's TSLA that
is the 2024 lot at $85.39: the 3 × $340 calls expiring 2026-09-18 would
realise +$83,793 of long-term gain under FIFO, or −$10,622 of harvestable
short-term loss if the two put-assignment lots ($435, $375) go instead.
A $94K swing in taxable income, decided by a default setting.

Robinhood's own rules (support article "Tax lots", read 2026-09-13):
- "Your default tax lot disposal method applies only to (i) stocks,
  (ii) ETFs, and (iii) shares resulting from options exercise or
  assignment."  → assignments follow the account default.
- Defaults offered: FIFO (default), LIFO, Highest Cost, Lowest Cost.
  App: Account → Menu → Investing → Tax lots disposal method → Edit.
- "Any update to your default tax lot disposal method before 8 PM ET
  applies to all trades executed on the same trading day and any trades
  moving forward."
- "If you need to make adjustments to a tax lot order after it has been
  placed or executed, contact us before 9 PM ET on the settlement date
  for the order."  → settlement is T+1, so a Friday assignment can be
  corrected until Monday 9 PM ET. Support is in-app / robinhood.com/contact
  (24/7 chat, callback 7 AM–9 PM ET weekdays); there is no support email.

So the rule: every call assignment in a TAXABLE account produces one
notice, and ideally the notice arrives BEFORE the assignment — while the
default method can still be switched for that day's trades.

TWO KINDS OF NOTICE
-------------------
pending  — a short call in a taxable account is in the money and expires
           within `lookahead_days`. Sent once per (account, symbol,
           expiry, strike). Says: set Highest Cost before 8 PM ET on the
           expiration day, and what FIFO vs Highest Cost would realise.
assigned — an OASGN Call row landed in a taxable account (official CSV or
           MCP-inferred). Sent once per (account, symbol, date, strike).
           Says: deadline 9 PM ET on the settlement date, and the exact
           support message naming the lots to use.

The lot engine (scripts/rebuild_stock_lots.py) is FIFO. If an account's
Robinhood default is changed, the engine must be told the method and the
effective date, or realised P/L here diverges from the 1099-B. That is a
separate change; this module only reports.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.tax.models import AssignmentTaxNotice

logger = logging.getLogger(__name__)

#: account_type values that are taxable — the only ones where lots matter
TAXABLE_TYPES = ("brokerage",)

#: Rough marginal rates for the "what this is worth" line. Federal LTCG 20%
#: + NIIT 3.8% + CA 9.3%; ST at ordinary 35% + 3.8% + 9.3%. Labelled rough
#: in the email; the exact figure is the tax module's job.
ROUGH_RATE_LT = 0.331
ROUGH_RATE_ST = 0.481

DISPOSAL_PATH = "Account → Menu → Investing → Tax lots disposal method → Edit disposal method"


def account_method(account_id: str, on: date) -> str:
    """The broker-side disposal method for this account on this date, from
    data/goal_settings.json (same reader the lot engine uses)."""
    try:
        from scripts.rebuild_stock_lots import load_disposal_methods, disposal_method
        return disposal_method(load_disposal_methods(), account_id, on)
    except Exception:  # noqa: BLE001
        return "fifo"


def _us_holidays() -> set:
    try:
        from scripts.backfill_holdings_history import US_HOLIDAYS
        return set(US_HOLIDAYS)
    except Exception:  # noqa: BLE001
        return set()


def next_business_day(d: date) -> date:
    hol = _us_holidays()
    n = d + timedelta(days=1)
    while n.weekday() >= 5 or n in hol:
        n += timedelta(days=1)
    return n


def settlement_deadline(trade_date: date) -> datetime:
    """9 PM ET on the T+1 settlement date, expressed in ET wall time."""
    s = next_business_day(trade_date)
    return datetime(s.year, s.month, s.day, 21, 0)


# ---------------------------------------------------------------------------
# Lot scenarios
# ---------------------------------------------------------------------------

Lot = Tuple[date, float, float]  # (purchase_date, shares, cost_per_share)


def _consume(lots: List[Lot], shares: float, price: float, sale_date: date) -> Dict:
    """Sell `shares` at `price` from `lots` in the given order."""
    left, gain, lt_gain, st_gain, used = shares, 0.0, 0.0, 0.0, []
    for pd, qty, cps in lots:
        if left <= 1e-9:
            break
        take = min(left, qty)
        g = take * (price - cps)
        long_term = (sale_date - pd).days > 365
        gain += g
        if long_term:
            lt_gain += g
        else:
            st_gain += g
        used.append({"purchase_date": pd, "shares": take, "cost_per_share": cps,
                     "gain": g, "long_term": long_term})
        left -= take
    return {"gain": gain, "lt_gain": lt_gain, "st_gain": st_gain, "lots": used,
            "short": max(left, 0.0)}


def lot_scenarios(lots: List[Lot], shares: float, price: float, sale_date: date) -> Dict:
    """FIFO vs Highest Cost for selling `shares` at `price`.

    Highest Cost is the minimum-gain choice for a given sale and is what
    the notice recommends; LT/ST rate differences can in principle make a
    slightly lower-basis long-term lot cheaper after tax, which the rough
    tax line makes visible without pretending to optimise it.
    """
    fifo = _consume(sorted(lots, key=lambda l: (l[0], -l[2])), shares, price, sale_date)
    high = _consume(sorted(lots, key=lambda l: (-l[2], l[0])), shares, price, sale_date)
    return {"fifo": fifo, "highest_cost": high,
            "swing": fifo["gain"] - high["gain"],
            "rough_tax_fifo": fifo["lt_gain"] * ROUGH_RATE_LT + fifo["st_gain"] * ROUGH_RATE_ST,
            "rough_tax_high": high["lt_gain"] * ROUGH_RATE_LT + high["st_gain"] * ROUGH_RATE_ST}


def _open_lots(db: Session, account_id: str, symbol: str) -> List[Lot]:
    rows = db.execute(text("""
        SELECT purchase_date, quantity_remaining, cost_per_share FROM stock_lot
        WHERE account_id = :a AND symbol = :s AND quantity_remaining > 0
    """), {"a": account_id, "s": symbol}).fetchall()
    return [(r.purchase_date, float(r.quantity_remaining), float(r.cost_per_share)) for r in rows]


def _lots_before_sale(db: Session, account_id: str, symbol: str, sale_date: date) -> List[Lot]:
    """Open lots plus whatever the (FIFO) lot engine already consumed for
    sales on `sale_date` — i.e. the book as it stood before the assignment,
    so both scenarios are computed from the same starting point whether or
    not the rebuild has run yet."""
    lots = {}
    for pd, q, c in _open_lots(db, account_id, symbol):
        lots[(pd, c)] = lots.get((pd, c), 0.0) + q
    sold = db.execute(text("""
        SELECT l.purchase_date, s.quantity_sold, l.cost_per_share
        FROM stock_lot_sale s JOIN stock_lot l ON l.lot_id = s.lot_id
        WHERE l.account_id = :a AND l.symbol = :s AND s.sale_date = :d
    """), {"a": account_id, "s": symbol, "d": sale_date}).fetchall()
    for r in sold:
        k = (r.purchase_date, float(r.cost_per_share))
        lots[k] = lots.get(k, 0.0) + float(r.quantity_sold)
    return [(pd, q, c) for (pd, c), q in lots.items()]


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------

def _taxable_accounts(db: Session) -> Dict[str, Tuple[str, str]]:
    """account_id -> (display name, source) for taxable, active accounts."""
    rows = db.execute(text("""
        SELECT account_id, account_name, source FROM investment_accounts
        WHERE is_active = 'Y' AND account_type IN :types
    """), {"types": TAXABLE_TYPES}).fetchall()
    return {r.account_id: (r.account_name, r.source) for r in rows}


def pending_candidates(db: Session, today: date, lookahead_days: int = 1) -> List[Dict]:
    """Short calls in taxable accounts, in the money, expiring within the window."""
    accts = _taxable_accounts(db)
    if not accts:
        return []
    name_to_id = {n: a for a, (n, _) in accts.items()}
    rows = db.execute(text("""
        SELECT s.account_name, so.symbol, so.strike_price, so.expiration_date, so.contracts_sold
        FROM sold_options so
        JOIN sold_options_snapshots s ON s.id = so.snapshot_id
        WHERE so.snapshot_id IN (
            SELECT MAX(id) FROM sold_options_snapshots GROUP BY account_name)
          AND so.option_type = 'call'
          AND so.expiration_date BETWEEN :today AND :until
    """), {"today": today, "until": today + timedelta(days=lookahead_days)}).fetchall()
    prices = {r.symbol: float(r.current_price) for r in db.execute(text("""
        SELECT DISTINCT ON (symbol) symbol, current_price FROM investment_holdings
        WHERE current_price IS NOT NULL ORDER BY symbol, last_updated DESC NULLS LAST
    """)).fetchall()}
    out = []
    for r in rows:
        acct = name_to_id.get(r.account_name)
        if not acct:
            continue
        px = prices.get(r.symbol)
        strike = float(r.strike_price)
        if px is None or px <= strike:
            continue  # not in the money — no assignment expected
        out.append({"kind": "pending", "account_id": acct, "account_name": r.account_name,
                    "symbol": r.symbol, "strike": strike, "event_date": r.expiration_date,
                    "contracts": int(r.contracts_sold), "spot": px})
    return out


def assigned_candidates(db: Session, since: date) -> List[Dict]:
    """OASGN Call rows in taxable accounts since `since` (official CSV or inferred)."""
    accts = _taxable_accounts(db)
    if not accts:
        return []
    rows = db.execute(text("""
        SELECT account_id, symbol, transaction_date, quantity, description
        FROM investment_transactions
        WHERE transaction_type = 'OASGN' AND transaction_date >= :since
          AND account_id IN :accts AND description ILIKE '%call%'
        ORDER BY transaction_date
    """), {"since": since, "accts": tuple(accts)}).fetchall()
    from app.modules.strategies.assignment_detection_service import _parse_strike
    out = []
    for r in rows:
        strike = _parse_strike(r.description)
        if strike is None or not r.quantity:
            continue
        out.append({"kind": "assigned", "account_id": r.account_id,
                    "account_name": accts[r.account_id][0], "symbol": r.symbol,
                    "strike": float(strike), "event_date": r.transaction_date,
                    "contracts": int(float(r.quantity))})
    return out


def _key(c: Dict) -> str:
    return f"{c['kind']}:{c['account_id']}:{c['symbol']}:{c['event_date']}:{c['strike']:.2f}"


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------

def _money(v: float) -> str:
    return f"{'-' if v < 0 else '+'}${abs(v):,.0f}"


def _lot_lines(lots: List[Dict]) -> str:
    return "\n".join(
        f"  • {l['shares']:,.0f} sh bought {l['purchase_date']:%b %-d, %Y} at ${l['cost_per_share']:,.2f} "
        f"→ {_money(l['gain'])} ({'long' if l['long_term'] else 'short'}-term)"
        for l in lots)


def build_notice(c: Dict, sc: Dict) -> Tuple[str, str]:
    """(subject, body) — body is the markdown subset notifications.py renders."""
    shares = c["contracts"] * 100
    sym, strike, acct = c["symbol"], c["strike"], c["account_name"]
    fifo, high = sc["fifo"], sc["highest_cost"]
    swing = sc["swing"]
    ev = c["event_date"]
    method_set = account_method(c["account_id"], ev) == "highest_cost"
    if c["kind"] == "pending":
        head = (f"*{c['contracts']} × {sym} ${strike:,.2f} call{'s' if c['contracts'] > 1 else ''} in {acct} "
                f"expire {ev:%A %b %-d} and are in the money* ({sym} ${c['spot']:,.2f}). "
                f"Barring a drop below ${strike:,.2f}, {shares:,} shares are sold at ${strike:,.2f} that night.\n\n")
        if method_set:
            subject = (f"{sym} ${strike:,.0f} call assignment likely {ev:%a %-m/%-d} in {acct} — "
                       f"Highest Cost is set, expect {_money(high['gain'])} (FIFO would be {_money(fifo['gain'])})")
            action = (f"*{acct} is set to Highest Cost* (per data/goal_settings.json), so the assignment should "
                      f"deliver the lots listed under Highest Cost above — nothing to do unless the trade "
                      f"confirmation shows otherwise. If it does, you can still fix it until *9 PM ET on "
                      f"{settlement_deadline(ev):%A %b %-d}* (the settlement date) with the support message below.")
        else:
            subject = (f"{sym} ${strike:,.0f} call assignment likely {ev:%a %-m/%-d} in {acct} — "
                       f"set the lots before 8 PM ET (FIFO {_money(fifo['gain'])} vs Highest Cost {_money(high['gain'])})")
            action = (f"*Do this before 8 PM ET on {ev:%A}:* open Robinhood → {DISPOSAL_PATH} → choose *Highest Cost* "
                      f"for {acct}. Robinhood: \"any update to your default tax lot disposal method before 8 PM ET applies "
                      f"to all trades executed on the same trading day and any trades moving forward\" — and the default "
                      f"\"applies to … shares resulting from options exercise or assignment.\"\n\n"
                      f"If it assigns on FIFO anyway, you can still fix it until *9 PM ET on "
                      f"{settlement_deadline(ev):%A %b %-d}* (the settlement date) — see the support message below.")
    else:
        dl = settlement_deadline(ev)
        subject = (f"{sym} ${strike:,.0f} call ASSIGNED {ev:%-m/%-d} in {acct} — fix the lots before "
                   f"{dl:%a %-m/%-d} 9 PM ET (FIFO {_money(fifo['gain'])} vs Highest Cost {_money(high['gain'])})")
        head = (f"*{c['contracts']} × {sym} ${strike:,.2f} call{'s' if c['contracts'] > 1 else ''} in {acct} "
                f"were assigned on {ev:%A %b %-d}:* {shares:,} shares sold at ${strike:,.2f}.\n\n")
        if method_set:
            action = (f"*{acct} is set to Highest Cost*, so the sale should already show the Highest Cost lots "
                      f"above. Check the trade confirmation. If it went FIFO anyway, the fix window is "
                      f"*{dl:%A %b %-d}, 9 PM ET* (the settlement date) — send the support message below "
                      f"(in-app: Account → Help → Contact us, or robinhood.com/contact — 24/7 chat).")
        else:
            action = (f"*Deadline: {dl:%A %b %-d}, 9 PM ET* — Robinhood corrects the lots on an executed order only "
                      f"\"before 9 PM ET on the settlement date.\" {acct}'s default is FIFO, so the sale went FIFO. "
                      f"Send the support message below now (in-app: Account → Help → Contact us, "
                      f"or robinhood.com/contact — 24/7 chat; there is no support email).")

    support_msg = (
        f"Hello — on {ev:%B %-d, %Y}, {c['contracts']} {sym} ${strike:,.2f} call contract"
        f"{'s' if c['contracts'] > 1 else ''} expiring {ev:%B %-d, %Y} were assigned in my account "
        f"({acct}), selling {shares:,} shares of {sym}. Please apply specific lot identification to that "
        f"sale instead of FIFO, using these lots:\n"
        + "\n".join(f"  – {l['shares']:,.0f} shares purchased {l['purchase_date']:%B %-d, %Y} at "
                    f"${l['cost_per_share']:,.2f} per share" for l in high["lots"])
        + f"\nTotal: {shares:,} shares. Please confirm once the cost basis on the trade confirmation "
          f"reflects these lots. Thank you."
    )

    body = (
        head
        + f"*What the two methods realise on {shares:,} shares at ${strike:,.2f}:*\n"
        + f"FIFO (Robinhood default): *{_money(fifo['gain'])}* "
          f"({_money(fifo['lt_gain'])} long-term, {_money(fifo['st_gain'])} short-term)\n"
        + _lot_lines(fifo["lots"]) + "\n"
        + f"Highest Cost: *{_money(high['gain'])}* "
          f"({_money(high['lt_gain'])} long-term, {_money(high['st_gain'])} short-term)\n"
        + _lot_lines(high["lots"]) + "\n"
        + f"Difference in taxable income: *{_money(swing)}* — roughly "
          f"${abs(sc['rough_tax_fifo'] - sc['rough_tax_high']):,.0f} of tax "
          f"(federal + NIIT + CA at marginal rates; the tax module has the exact figure).\n\n"
        + action + "\n\n"
        + "*Support message — paste as-is:*\n`" + support_msg.replace("\n", "` \n`") + "`\n\n"
        + "_Rule: call-assignment-tax-lot-notice (project-kb). The lot engine follows each account's "
          "configured method from its effective date (data/goal_settings.json)._"
    )
    return subject, body


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_assignment_tax_notices(db: Session, today: Optional[date] = None,
                               lookahead_days: int = 1, lookback_days: int = 10,
                               send: bool = True, record: bool = True) -> Dict:
    """Find unsent notices, build them, email them, record them.

    send=False, record=False is a dry run: builds everything, touches
    nothing. Returns {"sent": [...], "skipped": n, "errors": [...]} —
    `sent` carries subject and body so a caller can see what went out.
    """
    today = today or date.today()
    cands = pending_candidates(db, today, lookahead_days) + \
        assigned_candidates(db, today - timedelta(days=lookback_days))
    sent, skipped, errors = [], 0, []
    svc = None
    for c in cands:
        key = _key(c)
        if db.query(AssignmentTaxNotice).filter_by(notice_key=key).first():
            skipped += 1
            continue
        shares = c["contracts"] * 100
        lots = (_open_lots(db, c["account_id"], c["symbol"]) if c["kind"] == "pending"
                else _lots_before_sale(db, c["account_id"], c["symbol"], c["event_date"]))
        if not lots:
            errors.append(f"{key}: no lots in the lot engine — cannot compare methods")
            continue
        sc = lot_scenarios(lots, shares, c["strike"], c["event_date"])
        subject, body = build_notice(c, sc)
        ok, msg_id = False, None
        if send:
            try:
                from app.shared.services.notifications import get_notification_service
                from app.shared.services.notifications import _md_to_html
                svc = svc or get_notification_service()
                ok, msg_id = svc._send_email(subject=subject, html_body=_md_to_html(body), plain_text=body)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{key}: email failed: {e}")
        if record:
            db.add(AssignmentTaxNotice(
                notice_key=key, kind=c["kind"], account_id=c["account_id"], symbol=c["symbol"],
                event_date=c["event_date"], strike=Decimal(str(c["strike"])), shares=Decimal(shares),
                fifo_gain=Decimal(f"{sc['fifo']['gain']:.2f}"),
                highest_cost_gain=Decimal(f"{sc['highest_cost']['gain']:.2f}"),
                deadline=settlement_deadline(c["event_date"]), email_sent=bool(ok), email_id=msg_id, body=body,
            ))
            db.commit()
        sent.append({"key": key, "subject": subject, "email_sent": ok, "body": body})
        logger.info("[tax-lots] notice %s (email=%s): %s", key, ok, subject)
    return {"sent": sent, "skipped": skipped, "errors": errors}
