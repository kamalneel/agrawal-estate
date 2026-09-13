"""Per-symbol cash-secured-put collateral, replayed from the option ledger.

WHY THIS EXISTS
---------------
Put premium is a return on the CASH securing the put, not on any shares — at
the moment a put is sold you may own none of the stock. `performance_service`
needs the cash each symbol tied up, per day, to put that premium over.

WHERE THE NUMBER COMES FROM (v2, 2026-09-12)
--------------------------------------------
The transaction ledger. A cash-secured put's collateral is strike x 100 x
contracts, and every leg carries symbol, expiry and strike in its
description ("SOXL 9/18/2026 Put $150.00"). Replaying STO opens against
BTC / OEXP / OASGN closes gives the exact open collateral at every day's
close, for any period the ledger covers — Neel, 2026-09-12: "you need the
denominator, and you have the stock price ... we are just looking for how
much cash was utilized towards selling puts."

v1 parsed the pasted Robinhood positions screen (`sold_options_snapshots`)
instead. That worked, but only from 2025-12-03 when those snapshots begin —
which left eleven months of 2025 put premium with no denominator — and it
carried a systematic one-day skew: snapshots are stamped in UTC and taken in
the Pacific evening, so a "2026-06-09" snapshot is really June 8's close. On
that date it showed $274,000 with AVGO $460 puts still open; those puts were
assigned during the June 9 session and the ledger's end-of-day $182,000 is
the truth.

VALIDATION
----------
The snapshot parse is retained as a cross-check. Against 426 account-days
where both exist the ledger replay matches exactly on 91%; the rest are the
UTC-day skew above, i.e. the snapshot describing the prior close. Open
collateral "today" agrees to the dollar ($151,000). `validate()` reports the
match rate so a drift in either source is visible.

Legs still open past their expiry with no closing row are released on the
expiry date — an expiration the ledger did not record still frees the cash.
"""
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

SHARES_PER_CONTRACT = 100

#: "SOXL 9/18/2026 Put $150.00", optionally prefixed
#: "Option Expiration for " on OEXP rows.
PUT_DESC_RE = re.compile(
    r'(?:Option Expiration for\s+)?([A-Z][A-Z0-9.]{0,5})\s+'
    r'(\d{1,2})/(\d{1,2})/(\d{4})\s+Put\s+\$([\d,]+(?:\.\d+)?)', re.I)

#: One sold option leg as pasted from the positions screen (snapshot source,
#: cross-check only). The bullet class and case-insensitive "sells" cover all
#: three historical paste formats.
LEG_RE = re.compile(
    r'^([A-Z][A-Z0-9.]{0,5})\s+\$([\d,]+(?:\.\d+)?)\s+(Put|Call)\s*$'
    r'\s*^([\d/]+)\s*[·•∙‧]\s*([\d.]+)\s+sells?\s*$',
    re.M | re.I)

#: account_cash_balance_history / sold_options_snapshots account_name ->
#: investment_accounts.account_id
ACCOUNT_ID = {
    "Neel's Brokerage": "neel_brokerage",
    "Jaya's Brokerage": "jaya_brokerage",
    "Neel's Retirement": "neel_retirement",
    "Jaya's IRA": "jaya_ira",
    "Jaya's Roth IRA": "jaya_roth_ira",
    "Neel's Roth IRA": "neel_roth_ira",
}


# ---------------------------------------------------------------- ledger ---

def _daily_put_collateral(db: Session, start: date, end: date):
    """(account_id, day) -> {symbol: open collateral at that day's close}.

    Replays every put leg from the beginning of the ledger (not just the
    period) so positions opened before `start` are counted as open.
    """
    rows = db.execute(text("""
        SELECT account_id, transaction_date AS d, transaction_type AS t,
               quantity AS q, description
        FROM investment_transactions
        WHERE description ILIKE '%%put%%'
          AND transaction_type IN ('STO', 'BTC', 'OEXP', 'OASGN')
          AND transaction_date <= :end
        ORDER BY transaction_date, id
    """), {"end": end}).mappings().all()

    book: Dict[Tuple, float] = defaultdict(float)       # open contracts
    events: List[Tuple[date, str, str, float]] = []     # (day, acct, sym, Δ$)
    for r in rows:
        m = PUT_DESC_RE.search(r["description"] or "")
        if not m:
            continue
        sym = m.group(1).upper()
        exp = date(int(m.group(4)), int(m.group(2)), int(m.group(3)))
        strike = float(m.group(5).replace(",", ""))
        key = (r["account_id"], sym, exp, strike)
        q = float(r["q"] or 0)
        per_contract = strike * SHARES_PER_CONTRACT
        if r["t"] == "STO":
            book[key] += q
            events.append((r["d"], r["account_id"], sym, q * per_contract))
        else:
            take = min(q, book[key])
            book[key] -= take
            if take:
                events.append((r["d"], r["account_id"], sym, -take * per_contract))
    # Unclosed past expiry: the cash was freed on expiry regardless.
    for (acct, sym, exp, strike), q in book.items():
        if q > 0 and exp <= end:
            events.append((exp, acct, sym, -q * strike * SHARES_PER_CONTRACT))
    events.sort()

    daily: Dict[Tuple[str, date], Dict[str, float]] = {}
    running: Dict[Tuple[str, str], float] = defaultdict(float)
    i, d = 0, min(start, events[0][0]) if events else start
    while d <= end:
        while i < len(events) and events[i][0] <= d:
            _, acct, sym, delta = events[i]
            running[(acct, sym)] += delta
            i += 1
        if d >= start and d.weekday() < 5:
            for (acct, sym), v in running.items():
                if v > 0.5:
                    daily.setdefault((acct, d), {})[sym] = v
        d += timedelta(days=1)
    # The book as it stands at `end` — "what is open right now", which is
    # NOT the same as each account's last day with any put open.
    open_at_end = {k: v for k, v in running.items() if v > 0.5}
    return daily, open_at_end


def get_put_collateral(db: Session, start: date, end: date) -> Dict:
    """Average put collateral per (account, symbol) and per account, plus
    what is open on the last day of the period.

    Averaged over the trading days in the period, so a put open 12 of 207
    days averages to a fraction of its size — that IS the point: the cash
    was only committed on those days.
    """
    daily, open_at_end = _daily_put_collateral(db, start, end)
    trading_days = sum(1 for n in range((end - start).days + 1)
                       if (start + timedelta(n)).weekday() < 5) or 1

    total_pair: Dict[Tuple[str, str], float] = defaultdict(float)
    total_acct: Dict[str, float] = defaultdict(float)
    for (acct, day), by_sym in daily.items():
        for sym, v in by_sym.items():
            total_pair[(acct, sym)] += v
            total_acct[acct] += v

    current: Dict[str, float] = defaultdict(float)
    for (_acct, sym), v in open_at_end.items():
        current[sym] += v

    by_pair = {k: v / trading_days for k, v in total_pair.items()}
    by_symbol: Dict[str, float] = defaultdict(float)
    for (_a, sym), v in by_pair.items():
        by_symbol[sym] += v
    return {
        "current_by_symbol": dict(current),
        "by_pair": by_pair,
        "by_symbol": dict(by_symbol),
        "by_account": {a: v / trading_days for a, v in total_acct.items()},
        "observed_days": {a: trading_days for a in total_acct},
    }


# ------------------------------------------------- snapshot cross-check ---

def parse_legs(raw: Optional[str]) -> List[Tuple[str, str, float]]:
    """-> [(symbol, 'put'|'call', collateral_dollars)] for one pasted screen."""
    out = []
    for symbol, strike, kind, _exp, contracts in LEG_RE.findall(raw or ""):
        try:
            out.append((symbol.upper(), kind.lower(),
                        float(strike.replace(",", "")) * SHARES_PER_CONTRACT
                        * float(contracts)))
        except ValueError:
            continue
    return out


def _snapshot_put_collateral(db: Session, start: date, end: date):
    rows = db.execute(text("""
        SELECT account_name, snapshot_date, raw_extracted_text AS txt
        FROM sold_options_snapshots
        WHERE parsing_status = 'success'
          AND snapshot_date >= :start AND snapshot_date < :end_exclusive
        ORDER BY snapshot_date
    """), {"start": start, "end_exclusive": end + timedelta(days=1)}).mappings().all()
    daily: Dict[Tuple[str, date], float] = {}
    for r in rows:
        acct = ACCOUNT_ID.get(r["account_name"])
        if not acct:
            continue
        daily[(acct, r["snapshot_date"].date())] = sum(
            v for _s, k, v in parse_legs(r["txt"]) if k == "put")
    return daily


def validate(db: Session, start: date, end: date) -> Dict:
    """Ledger replay vs the pasted-screen snapshots, where both exist.

    Expect ~90% exact; the remainder is the snapshot's UTC-date skew (it
    describes the prior Pacific close). A falling rate means one source has
    drifted — most likely a new paste format or a missing closing row.
    """
    daily, _ = _daily_put_collateral(db, start, end)
    ledger = {k: sum(v.values()) for k, v in daily.items()}
    snap = _snapshot_put_collateral(db, max(start, date(2025, 12, 3)), end)
    compared = exact = 0
    mismatches = []
    for key, want in snap.items():
        if key[1].weekday() >= 5:
            continue   # weekend snapshot = prior Friday's close; no ledger day
        compared += 1
        got = ledger.get(key, 0.0)
        if abs(got - want) < 1:
            exact += 1
        else:
            mismatches.append({"account_id": key[0], "date": str(key[1]),
                               "ledger": round(got, 2), "snapshot": round(want, 2)})
    mismatches.sort(key=lambda m: -abs(m["ledger"] - m["snapshot"]))
    return {"compared": compared, "exact": exact,
            "match_rate": round(exact / compared, 4) if compared else None,
            "mismatches": mismatches[:10]}
