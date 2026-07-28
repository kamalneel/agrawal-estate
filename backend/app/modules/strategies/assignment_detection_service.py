"""
Assignment detection — MCP-only, no CSV (Neel, 2026-07-23).

Robinhood's MCP surface has no dedicated assignment/notification event —
checked broadly (orders, PnL history, positions, watchlists, corporate
actions) and confirmed none exists. So this infers assignment from
signals already flowing through every sync:

  1. A short option contract open in the PRIOR synced snapshot is gone
     from the CURRENT one (sold_options_snapshots, saved every sync).
  2. No STC/BTC transaction exists for that exact contract in the
     intervening window (a real close/roll already explains it — skip).
  2b. No same-type replacement (put->put / call->call) at a nearby
     strike appeared in the same snapshot (see _looks_like_roll). Added
     2026-07-24 after signal 2 alone missed a real roll: the position-
     snapshot sync and the transaction-history sync don't land at the
     same moment, so a same-day roll's BTC/STO fill can still be
     un-synced when detection runs, making signal 2 look clear when it
     isn't. This check uses only the snapshot data already in hand (no
     sync-lag dependency) — a real assignment always flips option TYPE
     (put assigned -> shares appear -> covered with a CALL; call
     assigned -> shares called away -> recovered with a PUT), so a
     same-type reappearance is the clean fingerprint of a plain roll.

Signals 1+2 are sufficient on their own (Neel's call, 2026-07-23) — a
detection is written and shown in the UI as soon as both hold. A third,
corroborating signal is also checked:

  3. The same account's share count for the underlying changed by
     exactly +/-(contracts x 100) in that same window
     (investment_holdings_history) — puts add shares, calls remove them.

Signal 3 is opportunistic, not required — it depends on the daily
holdings-history snapshot landing on the right day, and can simply be
absent even for a real assignment if that snapshot hasn't caught up
yet. Three outcomes:

  - Matches the expected +/-(contracts x 100) -> high-confidence,
    written straight away.
  - Unavailable (no holdings-history row landed in this window) ->
    genuinely ambiguous. Still written (not withheld) but flagged
    'pending_confirmation', and folded into a one-time, batched email
    to Neel — reply-to routes back to the assistant inbox so a single
    reply can confirm/dispute the whole batch.
  - Present but WRONG (esp. share count flat when it should have moved)
    -> this is the actual signature of a plain OTM expiration, not an
    assignment (OEXP isn't recorded via MCP either, so "vanished + no
    closing order" alone can't tell the two apart) — skipped outright,
    not written, not emailed.

Note: a written detection lands in investment_transactions immediately,
but the $ figure in Assignment Loss for it depends separately on
symbol_price_history covering that date — which only refreshes
periodically (see docs/ROBINHOOD_MCP_SYNC.md / refresh.md step 8), not
every sync. A freshly-detected assignment can show in the ledger with
its loss still pending until the next price-history refresh.

Idempotent: keyed on (account_id, symbol, description) same as a real
OASGN row, so re-running never double-inserts or double-emails.
"""

import hashlib
import re
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text as _text
from sqlalchemy.orm import Session

from app.shared.services.notifications import get_notification_service

_STRIKE_RE = re.compile(r"\$([\d,]+\.?\d*)\s*$")


def _parse_strike(description: Optional[str]) -> Optional[float]:
    if not description:
        return None
    m = _STRIKE_RE.search(description.strip())
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_option_type(description: Optional[str]) -> Optional[str]:
    if not description:
        return None
    d = description.lower()
    if "put" in d:
        return "put"
    if "call" in d:
        return "call"
    return None


def _contracts_at_snapshot(db: Session, snapshot_id: int) -> Dict[Tuple, int]:
    """(symbol, strike, option_type, expiration_date) -> contracts_sold
    for ONE specific snapshot row (not a whole day — see
    _latest_snapshot_per_day for why that distinction matters)."""
    rows = db.execute(_text("""
        SELECT symbol, strike_price, option_type, expiration_date, contracts_sold
        FROM sold_options WHERE snapshot_id = :sid
    """), {"sid": snapshot_id}).fetchall()
    out: Dict[Tuple, int] = {}
    for r in rows:
        key = (r.symbol, float(r.strike_price), r.option_type, r.expiration_date)
        out[key] = out.get(key, 0) + int(r.contracts_sold)
    return out


def _latest_snapshot_per_day(db: Session, account_name: str) -> List[Tuple[date, int]]:
    """One (date, snapshot_id) per calendar day — the LATEST sync that
    day, not every sync summed together.

    sold_options_snapshots gets a fresh row every sync (4x/day), and each
    one re-lists every currently-open contract. A contract open all day
    shows up in 4+ separate snapshot rows for that single day. The first
    version of this detector summed contracts_sold across every same-day
    row, which multiplied a single 1-contract position into "4 contracts"
    just because it was observed 4 times — inflating detected assignment
    quantities (and therefore loss $) by however many times that sync ran
    that day. Real case: a 1-contract GOOGL $370 put, captured 5x on
    2026-07-22, got recorded as a 5-contract, $25,710 assignment instead
    of the real 1-contract, $5,142 one — caught when Neel checked his
    actual Robinhood account and saw 100 shares, not 500. Picking only
    the day's last snapshot avoids this."""
    rows = db.execute(_text("""
        SELECT DISTINCT ON (snapshot_date::date) snapshot_date::date AS d, id
        FROM sold_options_snapshots
        WHERE account_name = :acct
        ORDER BY snapshot_date::date, snapshot_date DESC
    """), {"acct": account_name}).fetchall()
    return sorted([(r.d, r.id) for r in rows], key=lambda x: x[0])


def _explaining_transaction_exists(db: Session, account_id: str, symbol: str,
                                   description: str, since: date, until: date) -> bool:
    """A real BTC (or STC, for a long) between the two snapshots already
    explains the contract's disappearance — not an assignment."""
    row = db.execute(_text("""
        SELECT 1 FROM investment_transactions
        WHERE account_id = :acct AND symbol = :sym AND description = :desc
          AND transaction_type IN ('BTC', 'STC')
          AND transaction_date BETWEEN :since AND :until
        LIMIT 1
    """), {"acct": account_id, "sym": symbol, "desc": description,
           "since": since, "until": until}).fetchone()
    return row is not None


def _share_delta(db: Session, account_id: str, symbol: str, since: date, until: date) -> Optional[float]:
    """Change in held shares for this account+symbol between the two
    snapshot dates, from the daily holdings history.

    Direction matters here, not just proximity. A symmetric +/-3-day
    "nearest" window let a single row — the FIRST holdings-history entry
    ever recorded for an account+symbol, dated the assignment day itself
    — get matched as both the "before" and "after" value (both 7/22 and
    7/23 fell within 3 days of the only row, dated 7/23), computing a
    false delta of 0 and wrongly clearing a real assignment as
    "contradicted" (looked like plain expiration). Fixed 2026-07-24.

    "Before" only looks backward, and treats no row found as 0 shares —
    investment_holdings_history only ever gets a row when quantity > 0
    (see _price_near), so its absence for a synced account genuinely
    means no position, not missing data. "After" only looks forward, and
    stays None (genuinely unknown, not assumed 0) if nothing has landed
    yet — that's the real gap (holdings-history sync lags the position
    snapshot by a day or so), and guessing here would be worse than
    admitting it's ambiguous."""
    before_row = db.execute(_text("""
        SELECT quantity FROM investment_holdings_history
        WHERE account_id = :acct AND symbol = :sym
          AND snapshot_date BETWEEN :d - INTERVAL '10 days' AND :d
        ORDER BY snapshot_date DESC LIMIT 1
    """), {"acct": account_id, "sym": symbol, "d": since}).fetchone()
    before = float(before_row.quantity) if before_row else 0.0

    after_row = db.execute(_text("""
        SELECT quantity FROM investment_holdings_history
        WHERE account_id = :acct AND symbol = :sym
          AND snapshot_date BETWEEN :d AND :d + INTERVAL '5 days'
        ORDER BY snapshot_date ASC LIMIT 1
    """), {"acct": account_id, "sym": symbol, "d": until}).fetchone()
    if after_row is None:
        return None
    return float(after_row.quantity) - before


def _looks_like_roll(curr: Dict[Tuple, int], vanished_key: Tuple) -> bool:
    """A real assignment always changes option TYPE — a put assignment
    hands you shares, which get covered with a CALL; a call assignment
    takes shares away, recovered with a PUT. A same-snapshot new
    position of the SAME type at a nearby strike (put->put, call->call)
    is the mechanical fingerprint of a plain strike/expiration ROLL, not
    an assignment. Checked directly against the snapshot data (already
    in hand, no sync lag) rather than the transactions table, which can
    lag behind the snapshot by the time detection runs (see
    _explaining_transaction_exists — that's the check this backstops)."""
    symbol, strike, opt_type, _exp = vanished_key
    for (sym2, strike2, type2, _exp2), qty2 in curr.items():
        if qty2 <= 0 or sym2 != symbol or type2 != opt_type:
            continue
        if (sym2, strike2, type2, _exp2) == vanished_key:
            continue
        if strike and abs(strike2 - strike) / strike <= 0.15:
            return True
    return False


def _already_recorded(db: Session, account_id: str, symbol: str, description: str) -> bool:
    row = db.execute(_text("""
        SELECT 1 FROM investment_transactions
        WHERE account_id = :acct AND symbol = :sym AND description = :desc
          AND transaction_type = 'OASGN'
        LIMIT 1
    """), {"acct": account_id, "sym": symbol, "desc": description}).fetchone()
    return row is not None


def _send_confirmation_email(records: List[Dict]) -> None:
    """One consolidated email per run for every signal-3-unconfirmed
    detection (never one email per record — a historical backlog would
    otherwise flood the inbox). Reply-to routes back to the assistant
    inbox so a single reply can confirm/dispute all of them."""
    if not records:
        return
    svc = get_notification_service()
    plural = "s" if len(records) != 1 else ""
    title = f"Confirm {len(records)} assignment{plural}? (share count didn't corroborate)"
    lines = []
    for r in records:
        delta_note = (
            f"observed share change {r['share_delta_observed']:+.0f} "
            f"(expected {r['share_delta_expected']:+.0f} if assigned)"
            if r["share_delta_observed"] is not None
            else "no holdings-history snapshot landed in this window to check"
        )
        lines.append(
            f"- *{r['symbol']}* ${r['strike']:.2f} {r['option_type']}, exp {r['expiration_date']}, "
            f"{r['contracts']} contract(s), *{r['account_name']}*, between "
            f"{r['detected_between'][0]} and {r['detected_between'][1]} — {delta_note}"
        )
    message = (
        f"{len(records)} short option position{plural} disappeared with no matching close/roll "
        f"order on file — {'it looks' if len(records) == 1 else 'they look'} like assignments, "
        f"but the share-count check didn't land cleanly for {'it' if len(records) == 1 else 'each'}:\n\n"
        + "\n".join(lines) +
        f"\n\n{'This is' if len(records) == 1 else 'These are'} already showing in Assignment Loss "
        f"/ the Exit Recovery ledger. Reply to confirm, or flag any that were actually something "
        f"else (e.g. a manual exercise or an untracked close)."
    )
    svc.send_alert(title=title, message=message, priority="medium")


def detect_and_record_assignments(db: Session, lookback_days: int = 10) -> Dict:
    """Walk each account's option snapshots for contracts that vanished
    with no explaining close/roll order (signals 1+2 — sufficient on
    their own, per Neel 2026-07-23). Record each one immediately so it
    shows in the UI. Separately check the share-count corroboration
    (signal 3); when it doesn't land, still record but flag
    'pending_confirmation' and email Neel once (batched per run) to
    close the loop.

    Only walks snapshot-date pairs within the last `lookback_days` —
    NOT full history. A first real run (2026-07-23) walked the entire
    snapshot corpus back to 2025-12 and flagged 168 historical OTM
    expirations as candidate assignments, because OEXP (plain
    expiration) isn't recorded via MCP either — "vanished + no closing
    order" alone can't tell assignment from ordinary expiration, and
    signal-3 share-count history didn't exist that far back to break the
    tie. Bounding to a recent rolling window keeps this a per-sync
    incremental check (resilient to an occasional missed sync) without
    ever repeating that backfill. Idempotent — safe to call every sync."""
    accounts = db.execute(_text(
        "SELECT DISTINCT account_id, account_name FROM investment_accounts"
    )).fetchall()
    acct_id_by_name = {r.account_name: r.account_id for r in accounts}

    high_confidence, pending_confirmation = [], []
    cutoff = date.today() - timedelta(days=lookback_days)

    for account_name, account_id in acct_id_by_name.items():
        day_snapshots = [(d, sid) for d, sid in _latest_snapshot_per_day(db, account_name) if d >= cutoff]
        if len(day_snapshots) < 2:
            continue
        for i in range(1, len(day_snapshots)):
            prev_date, prev_sid = day_snapshots[i - 1]
            curr_date, curr_sid = day_snapshots[i]
            prev = _contracts_at_snapshot(db, prev_sid)
            curr = _contracts_at_snapshot(db, curr_sid)

            for key, prev_contracts in prev.items():
                curr_contracts = curr.get(key, 0)
                if curr_contracts >= prev_contracts:
                    continue  # still open or grew — not a disappearance
                vanished = prev_contracts - curr_contracts
                symbol, strike, opt_type, exp = key
                if exp is None:
                    continue  # can't identify/describe the contract without an expiration
                strike_txt = f"{strike:.2f}" if strike != int(strike) else f"{int(strike)}.00"
                description = f"{symbol} {exp.strftime('%-m/%-d/%Y')} {opt_type.capitalize()} ${strike_txt}"

                if _already_recorded(db, account_id, symbol, description):
                    continue
                if _explaining_transaction_exists(db, account_id, symbol, description, prev_date, curr_date):
                    continue  # a real close/roll already accounts for this
                if _looks_like_roll(curr, key):
                    continue  # same-type replacement at a nearby strike — a roll, not an assignment

                # Signals 1+2 hold. Signal 3 now decides what happens next:
                # matches -> confirmed; unavailable -> genuinely ambiguous
                # (email); present but WRONG (esp. 0 when shares should have
                # moved) -> that's the actual signature of a plain OTM
                # expiration, not an assignment, so skip it outright rather
                # than recording or emailing about a non-event.
                delta = _share_delta(db, account_id, symbol, prev_date, curr_date)
                expected = vanished * 100 * (1 if opt_type == "put" else -1)
                share_confirmed = delta is not None and abs(delta - expected) < 1.0
                share_contradicted = delta is not None and not share_confirmed
                if share_contradicted:
                    continue  # share count didn't move as assignment requires — looks like expiration

                record = {
                    "account_id": account_id, "account_name": account_name,
                    "symbol": symbol, "strike": strike, "option_type": opt_type,
                    "expiration_date": exp.isoformat(), "contracts": vanished,
                    "description": description,
                    "detected_between": [prev_date.isoformat(), curr_date.isoformat()],
                    "share_delta_observed": delta, "share_delta_expected": expected,
                    "share_confirmed": share_confirmed,
                }

                source = "robinhood_mcp_inferred" if share_confirmed else "robinhood_mcp_inferred_pending_confirmation"
                record_hash = hashlib.sha256(
                    f"{source}|{account_id}|{curr_date.isoformat()}|{symbol}|{description}".encode()
                ).hexdigest()
                db.execute(_text("""
                    INSERT INTO investment_transactions
                        (source, account_id, transaction_date, symbol, description,
                         transaction_type, quantity, price_per_share, amount, fees, record_hash,
                         created_at, updated_at)
                    VALUES (:source, :acct, :d, :sym, :desc, 'OASGN', :qty, 0.0, 0.0, 0.0, :hash,
                            NOW(), NOW())
                """), {"source": source, "acct": account_id, "d": curr_date, "sym": symbol,
                       "desc": description, "qty": vanished, "hash": record_hash})

                if share_confirmed:
                    high_confidence.append(record)
                else:
                    pending_confirmation.append(record)

    db.commit()
    _send_confirmation_email(pending_confirmation)
    return {
        "high_confidence": high_confidence,
        "pending_confirmation": pending_confirmation,
        "total_detected": len(high_confidence) + len(pending_confirmation),
    }
