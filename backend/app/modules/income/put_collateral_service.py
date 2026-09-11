"""Per-symbol cash-secured-put collateral, parsed from position snapshots.

WHY THIS EXISTS
---------------
Put premium is a return on the CASH securing the put, not on any shares — at
the moment a put is sold you may own none of the stock. `performance_service`
therefore reports put income per symbol as bare dollars, because nothing in
the holdings tables says how much cash each symbol tied up.

`account_cash_balance_history.options_collateral` has the figure, but only
per ACCOUNT. The per-symbol breakdown exists only inside
`sold_options_snapshots.raw_extracted_text` — the pasted Robinhood positions
screen — as lines like:

    SOXL $150 Put
    9/18/2026 · 2 sells

Collateral for one leg is strike x 100 x contracts. Neel, 2026-09-11: "if the
account has $50,000 in cash and only $40,000 of that was used as put
collateral, then the denominator ... should be the $40,000".

THREE TEXT FORMATS
------------------
The paste format changed over time and all three are still in the table:

    SOXL $150 Put / 9/18/2026 · 2 sells     (current)
    CBRS $250 Put / 6/12 · 1 Sell           (older: no year, capitalised)
    AMD  $500 Put / 6/26 • 2 sells          (older: U+2022 bullet, not U+00B7)

Matching only the first form parsed 162/190 account-days; accepting all three
parses 187/190 (98%).

VALIDATION
----------
Every parse is checked against the account total already recorded in
`account_cash_balance_history.options_collateral` — the source's own figure,
per the validate-parser-against-source-totals rule. `validate()` returns the
match rate so a format drift shows up as a falling number rather than as
silently wrong yields.

The three known misses: two are sub-$120 rounding differences, and Jaya's
Brokerage on 2026-07-22 parsed $53,500 against a recorded $16,500 — two
snapshots that day caught the account mid-roll.
"""
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

#: One sold option leg. The bullet class and the case-insensitive "sells"
#: are what make this cover all three historical paste formats.
LEG_RE = re.compile(
    r'^([A-Z][A-Z0-9.]{0,5})\s+\$([\d,]+(?:\.\d+)?)\s+(Put|Call)\s*$'
    r'\s*^([\d/]+)\s*[·•∙‧]\s*([\d.]+)\s+sells?\s*$',
    re.M | re.I)

SHARES_PER_CONTRACT = 100

#: account_cash_balance_history.account_name -> investment_accounts.account_id
ACCOUNT_ID = {
    "Neel's Brokerage": "neel_brokerage",
    "Jaya's Brokerage": "jaya_brokerage",
    "Neel's Retirement": "neel_retirement",
    "Jaya's IRA": "jaya_ira",
    "Jaya's Roth IRA": "jaya_roth_ira",
    "Neel's Roth IRA": "neel_roth_ira",
}


def parse_legs(raw: Optional[str]) -> List[Tuple[str, str, float]]:
    """-> [(symbol, 'put'|'call', collateral_dollars)] for one snapshot."""
    out = []
    for symbol, strike, kind, _exp, contracts in LEG_RE.findall(raw or ""):
        try:
            value = (float(strike.replace(",", ""))
                     * SHARES_PER_CONTRACT * float(contracts))
        except ValueError:
            continue
        out.append((symbol.upper(), kind.lower(), value))
    return out


def _daily_put_collateral(db: Session, start: date, end: date):
    """(account_id, day) -> {symbol: collateral}, latest snapshot per day."""
    rows = db.execute(text("""
        SELECT account_name, snapshot_date, raw_extracted_text AS txt
        FROM sold_options_snapshots
        WHERE parsing_status = 'success'
          AND snapshot_date >= :start AND snapshot_date < :end_exclusive
        ORDER BY snapshot_date
    """), {"start": start,
           # snapshot_date is a TIMESTAMP; comparing it to a date would drop
           # everything after midnight on the final day.
           "end_exclusive": end + timedelta(days=1)}).mappings().all()

    daily: Dict[Tuple[str, date], Dict[str, float]] = {}
    for r in rows:
        account_id = ACCOUNT_ID.get(r["account_name"])
        if not account_id:
            continue
        by_symbol: Dict[str, float] = defaultdict(float)
        for symbol, kind, value in parse_legs(r["txt"]):
            if kind == "put":
                by_symbol[symbol] += value
        # Ordered by timestamp, so a later snapshot replaces an earlier one
        # for the same day rather than being added to it.
        daily[(account_id, r["snapshot_date"].date())] = dict(by_symbol)
    return daily


def get_put_collateral(db: Session, start: date, end: date) -> Dict:
    """Average put collateral per (account, symbol) and per account.

    Averaged over the days the account HAS a snapshot, so a symbol carrying
    puts on 10 of 40 observed days averages a quarter of its leg size — that
    is the point, since the cash was only committed on those days.
    """
    daily = _daily_put_collateral(db, start, end)

    days_per_account: Dict[str, int] = defaultdict(int)
    total_per_pair: Dict[Tuple[str, str], float] = defaultdict(float)
    total_per_account: Dict[str, float] = defaultdict(float)
    for (account_id, _day), by_symbol in daily.items():
        days_per_account[account_id] += 1
        for symbol, value in by_symbol.items():
            total_per_pair[(account_id, symbol)] += value
            total_per_account[account_id] += value

    by_pair = {k: v / days_per_account[k[0]] for k, v in total_per_pair.items()
               if days_per_account.get(k[0])}
    by_symbol: Dict[str, float] = defaultdict(float)
    for (_account_id, symbol), value in by_pair.items():
        by_symbol[symbol] += value

    # Collateral open on the LATEST snapshot per account — "am I selling puts
    # on this right now", as distinct from the period average.
    latest_day: Dict[str, date] = {}
    for account_id, day in daily:
        if day > latest_day.get(account_id, date.min):
            latest_day[account_id] = day
    current: Dict[str, float] = defaultdict(float)
    for account_id, day in latest_day.items():
        for symbol, value in daily[(account_id, day)].items():
            current[symbol] += value

    return {
        "current_by_symbol": dict(current),
        "by_pair": by_pair,
        "by_symbol": dict(by_symbol),
        "by_account": {a: total_per_account[a] / days_per_account[a]
                       for a in days_per_account if days_per_account[a]},
        "observed_days": dict(days_per_account),
    }


def validate(db: Session, start: date, end: date) -> Dict:
    """Parsed per-symbol collateral vs the account total Robinhood recorded.

    A falling match rate means the paste format drifted again.
    """
    daily = _daily_put_collateral(db, start, end)
    parsed = {k: sum(v.values()) for k, v in daily.items()}
    recorded = {
        (ACCOUNT_ID.get(r["account_name"]), r["snapshot_date"]): float(r["options_collateral"])
        for r in db.execute(text("""
            SELECT account_name, snapshot_date, options_collateral
            FROM account_cash_balance_history
            WHERE options_collateral IS NOT NULL AND options_collateral <> 0
              AND snapshot_date >= :start AND snapshot_date <= :end
        """), {"start": start, "end": end}).mappings().all()}

    compared, exact, mismatches = 0, 0, []
    for key, want in recorded.items():
        if key not in parsed:
            continue
        compared += 1
        got = parsed[key]
        if abs(got - want) < 1:
            exact += 1
        else:
            mismatches.append({"account_id": key[0], "date": str(key[1]),
                               "parsed": round(got, 2), "recorded": round(want, 2)})
    mismatches.sort(key=lambda m: -abs(m["parsed"] - m["recorded"]))
    return {
        "compared": compared,
        "exact": exact,
        "match_rate": round(exact / compared, 4) if compared else None,
        "mismatches": mismatches[:10],
    }
