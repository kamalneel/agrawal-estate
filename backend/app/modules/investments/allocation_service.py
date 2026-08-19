"""Allocation targets vs. actual, and the option orders that close the gap.

Spec: docs/INVESTMENTS-PAGE-SPEC.md, "Allocation targets & execution".
Policy: project-kb/wiki/concepts/ai-value-chain-thesis.md.

Two buckets at 50/50 (Physical AI, Infrastructure AI), everything else
sells to zero. Targets are declared SHARE COUNTS in
`data/allocation_targets.json`, never computed here — see the spec for why
the volatility work behind them is frozen rather than re-run per request.

Neel does not buy or sell stock directly: below target he sells ATM puts and
takes assignment, above target he sells ATM calls and gets called away,
earning premium on both sides. So every gap is expressed as a contract
count, not a dollar order.

One exception (Neel, 2026-08-11): a buy target whose put isn't fully
collateralized anywhere is stuck waiting on exit/trim proceeds that may
take weeks, even though there's often smaller, genuinely spare cash sitting
idle in some other account today. "There is no point waiting to acquire
the money because I have some money." Rather than wait for the full
collateral, `share_buy` (see below) proposes buying whatever whole shares
that spare cash affords outright -- but only when RSI says the entry is
actually cheap; buying more of an overbought name just because cash sits
idle would be timing, not patience.
"""
import json
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text as _text
from sqlalchemy.orm import Session

from app.shared.services.cost_basis_service import get_pure_performance
from app.shared.services.option_premium import atm_order, next_expiration, strike_for, OTM_ATM
from app.modules.strategies.technical_signals import get_entry_timing, _price_near

# A rolled call already sitting within this band of the LIVE ATM target
# doesn't need re-rolling just because spot drifted a little since the
# plan was last computed. Widened 3%->5% same day (Neel, 2026-08-11):
# rolled TSLA $355->$340 (3 contracts) and $350->$335 (1 contract) —
# all 4 needed contracts, confirmed via the transaction ledger — but
# $340 priced out at +3.20% vs the live target, just outside the
# original 3% band, so 3 of the 4 stayed uncredited while $350/$355
# (genuinely untouched, +6-8%) correctly still needed a roll. "Close
# enough, not exact" was the explicit intent (Neel: "I don't have to go
# for the exact number") — 5% credits $335/$340 while still correctly
# leaving $350/$355 flagged.
ATM_TOLERANCE_PCT = 0.05

TARGETS_PATH = Path(__file__).resolve().parents[4] / "data" / "allocation_targets.json"

# A gap smaller than one contract is not actionable — the round-lot rule
# means there is no such thing as a 40-share order here.
SHARES_PER_CONTRACT = 100

# Accounts where a sale is not a taxable event. Trimming a position with
# embedded gains out of one of these instead of a taxable account is the
# single largest lever in this plan: the same 600 NVDA shares cost ~$36K in
# tax from Jaya's Brokerage (basis $18.93) and ~nothing from Jaya's IRA
# (basis $215.00).
SHELTERED_ACCOUNTS = {
    "neel_retirement", "neel_roth_ira", "jaya_ira", "jaya_roth_ira", "family_hsa",
}


def load_targets() -> Dict:
    with open(TARGETS_PATH) as f:
        return json.load(f)


def _fresh_prices(db: Session) -> Dict[str, float]:
    """Current price per symbol from the most recently updated holdings row.

    NOT `MAX(current_price)` — that is what `policy_service._current_prices`
    did, and it silently returns the *stalest* price whenever a dead feed
    holds a higher number. Alisha's Brokerage has been dead since
    2026-01-07 (a known data gap in the page spec), so MAX was serving
    TSLA at $423.74 from June against a live $328.55: a 29% error, straight
    into strike selection. Freshest row wins instead.
    """
    rows = db.execute(_text("""
        SELECT DISTINCT ON (symbol) symbol, current_price
        FROM investment_holdings
        WHERE current_price IS NOT NULL
        ORDER BY symbol, last_updated DESC NULLS LAST
    """)).fetchall()
    return {r.symbol: float(r.current_price) for r in rows}


def _excluded_accounts(cfg: Dict) -> List[str]:
    """Accounts outside the strategy — see `exclude_accounts` in the config.

    Must be applied consistently to holdings, the progress baseline and cash,
    or the base and the baseline disagree and progress reads as phantom
    movement.
    """
    return list((cfg.get("exclude_accounts") or {}).get("accounts") or [])


def _holdings_by_account(db: Session, alias: Dict[str, str],
                         exclude: List[str]) -> Dict[str, List[Dict]]:
    """Live share counts per (symbol, account), with share-class aliasing.

    Deliberately NOT the lot engine. `stock_lot` is authoritative for cost
    basis but undercounts shares wherever transaction history was never
    ingested — the HSA's 161 NVDA, all 100 GOOG, 201 of the SPCX. Using it
    for allocation produced a materially wrong plan: GOOGL read "at target"
    when the real position is 100 over, and NVDA's trim came out 161 shares
    light. What you own is `investment_holdings`; what it cost is the lots.
    """
    # CASH and money-market sweeps are not positions — including them would
    # put FDRXX in the allocation denominator.
    rows = db.execute(_text("""
        SELECT account_id, symbol, SUM(quantity) AS qty
        FROM investment_holdings
        WHERE quantity > 0 AND symbol NOT IN ('CASH', 'FDRXX')
          AND NOT (account_id = ANY(:ex))
        GROUP BY account_id, symbol
    """), {"ex": exclude}).fetchall()
    # Cost basis per (account, symbol) from the lots, for tax-aware routing.
    basis = {(r.account_id, r.symbol): float(r.cps or 0) for r in db.execute(_text("""
        SELECT account_id, symbol,
               SUM(quantity_remaining * cost_per_share) / NULLIF(SUM(quantity_remaining), 0) AS cps
        FROM stock_lot WHERE quantity_remaining > 0 AND NOT (account_id = ANY(:ex))
        GROUP BY account_id, symbol
    """), {"ex": exclude}).fetchall()}
    out: Dict[str, List[Dict]] = {}
    for r in rows:
        sym = alias.get(r.symbol, r.symbol)
        out.setdefault(sym, []).append({
            "account_id": r.account_id,
            "held_as": r.symbol,          # surfaces GOOG under the GOOGL row
            "shares": float(r.qty),
            "sheltered": r.account_id in SHELTERED_ACCOUNTS,
            "cost_per_share": basis.get((r.account_id, r.symbol)),
        })
    # Merge share classes held in the SAME account into one leg. GOOG and
    # GOOGL in Jaya's Brokerage were two separate entries with the same
    # account_id, so the router treated them as two accounts and allocated a
    # contract to each — double-counting the same 100 GOOGL lot and never
    # seeing the GOOG one.
    for sym, accs in out.items():
        merged: Dict[str, Dict] = {}
        for a in accs:
            m = merged.get(a["account_id"])
            if m is None:
                merged[a["account_id"]] = dict(a, held_as=[a["held_as"]])
            else:
                m["shares"] += a["shares"]
                m["held_as"].append(a["held_as"])
                if m["cost_per_share"] is None:
                    m["cost_per_share"] = a["cost_per_share"]
        out[sym] = sorted(merged.values(), key=lambda a: -a["shares"])
    return out


def _open_short_contracts(db: Session) -> Dict[tuple, int]:
    """Open short contracts keyed by (symbol, option_type), all accounts.

    A name with 5 puts already sold needs 5 more to reach 10, not 10 more.
    Same source as policy_service._latest_open_options — latest snapshot per
    account, unexpired only.
    """
    rows = db.execute(_text("""
        WITH latest AS (
            SELECT account_name, MAX(snapshot_date) AS snap
            FROM sold_options_snapshots
            GROUP BY account_name
        )
        SELECT o.symbol, o.option_type, SUM(o.contracts_sold) AS contracts
        FROM sold_options o
        JOIN sold_options_snapshots s ON s.id = o.snapshot_id
        JOIN latest l ON l.account_name = s.account_name AND l.snap = s.snapshot_date
        WHERE o.expiration_date >= CURRENT_DATE
        GROUP BY o.symbol, o.option_type
    """)).fetchall()
    out: Dict[tuple, int] = {}
    for r in rows:
        out[(r.symbol, (r.option_type or "").lower())] = int(r.contracts or 0)
    return out


def _open_call_strikes(db: Session) -> Dict[str, List[Tuple[float, int]]]:
    """Per-symbol (strike, contracts_sold) for open short calls, latest
    snapshot per account, unexpired. Strike-level detail
    _open_short_contracts() throws away — needed by the ATM_TOLERANCE_PCT
    check above to tell an already-near-ATM call apart from one still
    sitting deep OTM, which the aggregate count can't distinguish."""
    rows = db.execute(_text("""
        WITH latest AS (
            SELECT account_name, MAX(snapshot_date) AS snap
            FROM sold_options_snapshots GROUP BY account_name
        )
        SELECT o.symbol, o.strike_price, o.contracts_sold
        FROM sold_options o
        JOIN sold_options_snapshots s ON s.id = o.snapshot_id
        JOIN latest l ON l.account_name = s.account_name AND l.snap = s.snapshot_date
        WHERE o.expiration_date >= CURRENT_DATE AND LOWER(o.option_type) = 'call'
    """)).fetchall()
    out: Dict[str, List[Tuple[float, int]]] = {}
    for r in rows:
        out.setdefault(r.symbol, []).append((float(r.strike_price), int(r.contracts_sold or 0)))
    return out


def _open_call_strikes_by_account(db: Session) -> Dict[Tuple[str, str], List[Tuple[float, int]]]:
    """Same as _open_call_strikes but keyed by (symbol, account_id) too.

    Needed because the aggregate "already near ATM" credit fixes the
    TOTAL contracts still needed for a trim/exit, but says nothing about
    WHICH account's shares that credit belongs to — _route_trim_lots then
    picks accounts purely by tax cost, blind to whether an account's own
    shares are already backing an open call. Found 2026-08-14: INTC exit
    recommended "sell 1 call" in Neel's Brokerage even though its only
    100 shares were already fully covered by an existing (deeply ITM)
    call — the account never needed a NEW contract, its shares just
    weren't credited out of the routing pool."""
    rows = db.execute(_text("""
        WITH latest AS (
            SELECT account_name, MAX(snapshot_date) AS snap
            FROM sold_options_snapshots GROUP BY account_name
        )
        SELECT o.symbol, ia.account_id, o.strike_price, o.contracts_sold
        FROM sold_options o
        JOIN sold_options_snapshots s ON s.id = o.snapshot_id
        JOIN latest l ON l.account_name = s.account_name AND l.snap = s.snapshot_date
        LEFT JOIN investment_accounts ia ON ia.account_name = s.account_name
        WHERE o.expiration_date >= CURRENT_DATE AND LOWER(o.option_type) = 'call'
    """)).fetchall()
    out: Dict[Tuple[str, str], List[Tuple[float, int]]] = {}
    for r in rows:
        if not r.account_id:
            continue
        out.setdefault((r.symbol, r.account_id), []).append(
            (float(r.strike_price), int(r.contracts_sold or 0)))
    return out


def _credited_call_contracts(strikes: List[Tuple[float, int]], px: float,
                             atm_target: float, rolled: Dict[float, int]) -> int:
    """How many of these open call contracts already count as "done" for
    a trim/exit: genuinely ITM (heading to assignment regardless of roll
    history), or verified near-ATM via an actual roll (see
    _recent_call_rolldowns). Shared between the aggregate credit (how
    many MORE contracts the trim still needs) and the per-account routing
    reduction (whose shares are already spoken for, see
    _open_call_strikes_by_account) — same test, different scope."""
    credit = 0
    for st, c in strikes:
        if st < px:
            credit += c
        elif st <= atm_target * (1 + ATM_TOLERANCE_PCT):
            credit += min(c, rolled.get(st, 0))
    return credit


def _recent_call_rolldowns(db: Session, lookback_days: int = 14) -> Dict[str, Dict[float, int]]:
    """Per-symbol {new_strike: contracts} for same-day BTC+STO call pairs in
    the last `lookback_days` that represent maintaining an ALREADY-near-ATM
    position — as opposed to a strike that merely happens to sit near
    today's ATM target by coincidence.

    Added 2026-08-11 after ATM_TOLERANCE_PCT alone produced a false
    positive: AAPL's routine Tier-1 income call (STO $310, 9/4 exp, rolled
    UP from $300 on 08-04 — ordinary strike management, unrelated to
    rebalancing) drifted to within the tolerance band purely because AAPL's
    spot price rose toward it over the following days, and got miscounted
    as "already done" rebalancing progress. The first fix required the
    roll to be a DECREASE (rolled down = deliberate trim progress) — but
    that broke a real case 2026-08-14: NVDA's weekly ATM-tracking roll
    ($225.00 -> $227.50, a few cents UP because spot itself ticked up)
    IS genuine trim maintenance, just not a decrease, so it went
    uncredited and the queue kept asking to re-roll a position already
    freshly rolled.

    The real distinguishing signal was never direction — it's whether the
    OLD strike was ALSO near-ATM at the time of the roll (NVDA's $225 was,
    the same day, essentially spot; AAPL's $300 on 08-04 was a genuine
    Tier-1 far-OTM strike that only LOOKED close in hindsight once spot
    caught up days later). So: any same-day roll qualifies, direction
    aside, but only if the price on that historical date shows the old
    strike was already within ATM_TOLERANCE_PCT back then — using today's
    price for that check (as a pure strike-vs-strike comparison would)
    doesn't work, since by today AAPL's spot has moved enough that both
    $300 and $310 look close now, same as the original bug.
    """
    rows = db.execute(_text("""
        WITH pairs AS (
            SELECT account_id, symbol, transaction_date,
                   transaction_type,
                   substring(description from '\\$([0-9.,]+)\\s*$') AS strike_txt,
                   quantity
            FROM investment_transactions
            WHERE transaction_type IN ('BTC', 'STO')
              AND description ILIKE '%Call%'
              AND transaction_date >= CURRENT_DATE - make_interval(days => :lookback)
        )
        SELECT b.symbol, b.account_id, b.transaction_date,
               REPLACE(b.strike_txt, ',', '')::numeric AS old_strike,
               REPLACE(s.strike_txt, ',', '')::numeric AS new_strike,
               LEAST(b.quantity, s.quantity) AS contracts
        FROM pairs b
        JOIN pairs s
          ON s.account_id = b.account_id AND s.symbol = b.symbol
         -- Close and reopen aren't always same-day (TSLA's real roll:
         -- BTC $355 on 08-10, STO $340 the next day, 08-11) — a few
         -- days' window still means "this was one roll," not two
         -- unrelated trades.
         AND s.transaction_date BETWEEN b.transaction_date AND b.transaction_date + INTERVAL '3 days'
         AND b.transaction_type = 'BTC' AND s.transaction_type = 'STO'
    """), {"lookback": lookback_days}).fetchall()
    out: Dict[str, Dict[float, int]] = {}
    for r in rows:
        old_strike = float(r.old_strike)
        # Was the strike being replaced ALREADY near-ATM, using the price
        # AS OF that roll date (not today's) — the whole point being that
        # today's price can't tell a maintenance roll from a coincidence.
        hist_price, _src = _price_near(db, r.account_id, r.symbol, r.transaction_date)
        if hist_price is None:
            continue  # no historical price to judge against -- don't guess
        hist_atm_target = strike_for(hist_price, OTM_ATM)
        if old_strike > hist_atm_target * (1 + ATM_TOLERANCE_PCT):
            continue  # old strike was genuinely far-OTM at roll time -- not a maintenance roll
        sym_map = out.setdefault(r.symbol, {})
        new_strike = float(r.new_strike)
        sym_map[new_strike] = sym_map.get(new_strike, 0) + int(r.contracts or 0)
    return out


def _pending_assignments(db: Session, prices: Dict[str, float],
                         alias: Dict[str, str]) -> Dict[str, Dict]:
    """Shares arriving from short puts that are currently in the money.

    An ITM short put is not "collateral" in any useful sense — it is stock
    you have already agreed to buy, at a strike above where it trades. The
    plan has to net these in, or it recommends buying a name that is about
    to be delivered anyway, and misses that a position will overshoot its
    target the moment the contracts settle.
    """
    rows = db.execute(_text("""
        WITH latest AS (
            SELECT account_name, MAX(snapshot_date) AS snap
            FROM sold_options_snapshots GROUP BY account_name
        )
        SELECT o.symbol, o.strike_price, o.contracts_sold, o.expiration_date
        FROM sold_options o
        JOIN sold_options_snapshots s ON s.id = o.snapshot_id
        JOIN latest l ON l.account_name = s.account_name AND l.snap = s.snapshot_date
        WHERE o.expiration_date >= CURRENT_DATE AND LOWER(o.option_type) = 'put'
    """)).fetchall()
    # Sold puts routinely cover symbols with no share position (SOXL, CBRS),
    # so investment_holdings has no price for them. Fall back to the price
    # history, which carries Robinhood live quotes per the
    # market-data-source-order rule. Without this the ITM test silently fell
    # through to "OTM" and reported $155,500 of deep-ITM SOXL/CBRS collateral
    # as cash about to come back.
    px = dict(prices)
    for r in db.execute(_text("""
        SELECT DISTINCT ON (symbol) symbol, close_price FROM symbol_price_history
        ORDER BY symbol, price_date DESC
    """)).fetchall():
        px.setdefault(r.symbol, float(r.close_price))

    out: Dict[str, Dict] = {}
    for r in rows:
        sym = alias.get(r.symbol, r.symbol)
        spot = px.get(r.symbol) if r.symbol in px else px.get(sym)
        strike = float(r.strike_price or 0)
        n = int(r.contracts_sold or 0)
        coll = strike * SHARES_PER_CONTRACT * n
        d = out.setdefault(sym, {"shares": 0, "collateral": 0.0, "cash_returning": 0.0,
                                 "unknown_collateral": 0.0, "next_expiry": None, "itm": False})
        d["collateral"] += coll
        exp = str(r.expiration_date)
        d["next_expiry"] = exp if d["next_expiry"] is None else min(d["next_expiry"], exp)
        if spot is None:
            # Unknown is neither outcome. Counting it as either direction is a
            # guess presented as a fact; report it separately instead.
            d["unknown_collateral"] += coll
        elif spot < strike:
            d["shares"] += n * SHARES_PER_CONTRACT
            d["itm"] = True
        else:
            d["cash_returning"] += coll
    return out


def _lots_by_account(db: Session, exclude: List[str],
                     alias: Optional[Dict[str, str]] = None) -> Dict[tuple, List[Dict]]:
    """Open tax lots per (symbol, account), highest cost basis first.

    Routing has to see individual lots, not the account average. TSLA's
    average basis in Jaya's Brokerage is $200.08, which made the account look
    uniformly attractive — but it is 370 shares bought above $375 sitting on
    top of 630 shares at $85.39. Ranking on the average sent all four
    contracts there and would have sold 30 shares out of the cheap lot.
    """
    al = alias or {}
    out: Dict[tuple, List[Dict]] = {}
    for r in db.execute(_text("""
        SELECT symbol, account_id, purchase_date, quantity_remaining AS qty, cost_per_share AS cps
        FROM stock_lot
        WHERE quantity_remaining > 0 AND NOT (account_id = ANY(:ex))
    """), {"ex": exclude}).fetchall():
        # Alias here too, or GOOG's lots sit under a key the GOOGL row never
        # looks up and its basis is invisible to the tax router.
        out.setdefault((al.get(r.symbol, r.symbol), r.account_id), []).append({
            "purchase_date": str(r.purchase_date),
            "shares": float(r.qty),
            "cost_per_share": float(r.cps or 0),
        })
    # Basis fallback for positions the lot engine never built lots for.
    # Jaya's Brokerage GOOG/GOOGL are the live case: 200 shares acquired by
    # put assignment in July, both transactions present in
    # investment_transactions, zero rows in stock_lot. Without this the tax
    # router is blind to a real $3,482 harvestable loss and silently ranks
    # the position as if it had no basis at all.
    #
    # Deliberately ONLY fills pairs with zero lots — mixing derived lots into
    # a partially-covered position would double-count. Positions with partial
    # coverage (IBIT 1400 of 1500, SPCX) stay flagged rather than guessed.
    covered = {k for k in out}
    held = db.execute(_text("""
        SELECT account_id, symbol, SUM(quantity) AS qty FROM investment_holdings
        WHERE quantity > 0 AND symbol NOT IN ('CASH', 'FDRXX')
          AND NOT (account_id = ANY(:ex))
        GROUP BY account_id, symbol
    """), {"ex": exclude}).fetchall()
    missing = [(al.get(r.symbol, r.symbol), r.account_id) for r in held
               if (al.get(r.symbol, r.symbol), r.account_id) not in covered]
    if missing:
        # Query by the ORIGINAL ticker, not the aliased one — GOOG's
        # transactions are filed under 'GOOG', so searching for 'GOOGL'
        # silently returned nothing and lost a $1,906 harvestable loss.
        syms = sorted({r.symbol for r in held
                       if (al.get(r.symbol, r.symbol), r.account_id) in missing})
        accts = sorted({a for _, a in missing})
        for r in db.execute(_text("""
            SELECT symbol, account_id, transaction_date, quantity, price_per_share
            FROM investment_transactions
            WHERE symbol = ANY(:s) AND account_id = ANY(:a)
              AND transaction_type IN ('BUY', 'ASSIGNED', 'OASGN')
              AND quantity >= 1 AND price_per_share IS NOT NULL
        """), {"s": syms, "a": accts}).fetchall():
            key = (al.get(r.symbol, r.symbol), r.account_id)
            if key not in missing:
                continue
            out.setdefault(key, []).append({
                "purchase_date": str(r.transaction_date),
                "shares": float(r.quantity),
                "cost_per_share": float(r.price_per_share),
                "derived_from_transactions": True,
            })
    for k in out:
        out[k].sort(key=lambda l: -l["cost_per_share"])
    return out


def _hifo_gain(lots: List[Dict], shares: float, price: float, offset: float = 0.0) -> tuple:
    """Realized gain from selling `shares` highest-basis-first, skipping the
    first `offset` shares already allocated. Returns (gain, lots_touched)."""
    gain, touched, skip, left = 0.0, [], offset, shares
    for l in lots:
        avail = l["shares"]
        if skip > 0:
            take_skip = min(avail, skip)
            skip -= take_skip
            avail -= take_skip
        if avail <= 0 or left <= 0:
            continue
        t = min(avail, left)
        g = t * (price - l["cost_per_share"])
        gain += g
        touched.append({"purchase_date": l["purchase_date"], "shares": round(t, 4),
                        "cost_per_share": l["cost_per_share"], "realized_gain": round(g, 2)})
        left -= t
    return gain, touched


def _route_trim_lots(sym: str, accounts: List[Dict], shares_needed: float, price: float,
                     lots: Dict[tuple, List[Dict]]) -> Dict:
    """Allocate whole contracts to accounts, cheapest tax first, lot-aware.

    Greedy per 100-share block: each block goes to whichever account's NEXT
    100 shares realize the least gain. Sheltered accounts are free and always
    win. This is what makes "sell the $435 lots" expressible as an order —
    3 contracts in Jaya's and 1 in Neel's, rather than 4 in the account whose
    average happens to look best.
    """
    eligible = [a for a in accounts if a["shares"] >= SHARES_PER_CONTRACT]
    if not eligible:
        return {"legs": [], "gain_avoided_vs_worst": 0.0, "basis_unknown": False, "lot_aware": True}

    used = {a["account_id"]: 0.0 for a in eligible}
    blocks = int(shares_needed) // SHARES_PER_CONTRACT
    for _ in range(blocks):
        best, best_gain = None, None
        for a in eligible:
            aid = a["account_id"]
            if used[aid] + SHARES_PER_CONTRACT > a["shares"]:
                continue
            if a["sheltered"]:
                # A sheltered sale has NO tax effect — that is worth 0, not
                # worth -infinity. Ranking it as always-best was right for a
                # position sitting on a gain (avoid the tax) and backwards for
                # one sitting on a loss: a loss realised inside an IRA is
                # simply destroyed, while the same loss in a taxable account
                # offsets real gains. Scoring sheltered at 0 and sorting
                # ascending gets both cases right — harvestable losses first,
                # then sheltered, then gains cheapest-first.
                g = 0.0
            else:
                g, _t = _hifo_gain(lots.get((sym, aid), []), SHARES_PER_CONTRACT, price, used[aid])
            if best_gain is None or g < best_gain:
                best, best_gain = aid, g
        if best is None:
            break
        used[best] += SHARES_PER_CONTRACT

    legs, total_gain = [], 0.0
    for a in eligible:
        aid = a["account_id"]
        if used[aid] <= 0:
            continue
        acct_lots = lots.get((sym, aid), [])
        g, touched = _hifo_gain(acct_lots, used[aid], price)
        if a["sheltered"]:
            g, touched = 0.0, []
        total_gain += g
        legs.append({
            "account_id": aid,
            "shares": used[aid],
            "contracts": int(used[aid]) // SHARES_PER_CONTRACT,
            "sheltered": a["sheltered"],
            "cost_per_share": a["cost_per_share"],
            "realized_gain": None if (not a["sheltered"] and not acct_lots) else round(g, 2),
            "lots": touched,
            "instruction": "sell",
        })

    # Worst case: the same number of contracts taken oldest-lot-first (FIFO)
    # from the taxable account holding enough — what happens with no lot
    # selection. The gap is the whole reason lot control matters here.
    worst = 0.0
    for a in eligible:
        if a["sheltered"]:
            continue
        acct_lots = sorted(lots.get((sym, a["account_id"]), []),
                           key=lambda l: l["cost_per_share"])   # cheapest first
        if not acct_lots:
            continue
        take = min(shares_needed, a["shares"])
        g, _t = _hifo_gain(acct_lots, take, price)
        worst = max(worst, g)
    return {
        "legs": legs,
        "realized_gain": round(total_gain, 2),
        "gain_avoided_vs_worst": round(max(0.0, worst - total_gain), 2),
        "basis_unknown": any(l["realized_gain"] is None for l in legs),
        "lot_aware": True,
    }


def _route_trim(accounts: List[Dict], shares_needed: float, price: float) -> Dict:
    """Which account to sell calls in, and what the choice is worth.

    Ranks by tax cost of the sale — sheltered first, then lowest embedded
    gain — and reports the saving against the worst choice so the number is
    visible rather than implied. Only whole contracts count: 61 shares in
    the HSA cannot be called away.
    """
    def gain_ps(a):
        """Embedded gain per share. None where the lot engine has no basis
        for this account — unknown, NOT zero. Treating missing basis as zero
        made a $0-basis assumption and reported the entire position value as
        gain avoided (GOOGL in Jaya's Brokerage has no lots at all)."""
        if a["sheltered"]:
            return 0.0
        if a["cost_per_share"] is None:
            return None
        return max(0.0, price - a["cost_per_share"])

    eligible = [a for a in accounts if a["shares"] >= SHARES_PER_CONTRACT]
    if not eligible:
        return {"legs": [], "gain_avoided_vs_worst": 0.0, "basis_unknown": False}

    # Sheltered first, then lowest known gain; unknown-basis accounts sort
    # last among taxable ones rather than being ranked as if free.
    ranked = sorted(eligible, key=lambda a: (
        0 if a["sheltered"] else 1,
        float("inf") if gain_ps(a) is None else gain_ps(a),
    ))

    legs, remaining = [], shares_needed
    for a in ranked:
        if remaining < SHARES_PER_CONTRACT:
            break
        take = min(int(a["shares"]) // SHARES_PER_CONTRACT * SHARES_PER_CONTRACT,
                   int(remaining) // SHARES_PER_CONTRACT * SHARES_PER_CONTRACT)
        if take <= 0:
            continue
        g = gain_ps(a)
        legs.append({
            "account_id": a["account_id"],
            "shares": take,
            "contracts": take // SHARES_PER_CONTRACT,
            "sheltered": a["sheltered"],
            "cost_per_share": a["cost_per_share"],
            "realized_gain": None if g is None else round(take * g, 2),
        })
        remaining -= take

    # Gain avoided by routing here instead of the worst eligible account.
    # Reported as GAIN, not tax — the rate is Neel's, not ours to assume.
    known = [a for a in ranked if gain_ps(a) is not None]
    placed = sum(l["shares"] for l in legs)
    avoided = 0.0
    if known and all(l["realized_gain"] is not None for l in legs):
        worst_ps = max(gain_ps(a) for a in known)
        avoided = round(placed * worst_ps - sum(l["realized_gain"] for l in legs), 2)
    return {
        "legs": legs,
        "gain_avoided_vs_worst": avoided,
        "basis_unknown": any(l["realized_gain"] is None for l in legs),
    }


def _route_buy(accounts: List[Dict], cash: Dict[str, Dict], strike: float) -> Dict:
    """Which account to sell puts in.

    Prefers an account that already holds the name — Neel's explicit ask is
    one account per symbol so there are fewer positions to manage — but only
    if it can actually secure the contract. A Roth with $25 in it "holds" MU
    and is still the wrong answer.
    """
    need = strike * SHARES_PER_CONTRACT
    holders = [a["account_id"] for a in accounts if a["shares"] > 0]
    funded = {k: v["deployable_cash"] for k, v in cash.items() if v["deployable_cash"] >= need}
    for h in holders:
        if h in funded:
            return {"buy_account": h, "consolidates": True, "funded": True}
    if funded:
        best = max(funded, key=funded.get)
        return {"buy_account": best, "consolidates": best in holders, "funded": True}
    # Nothing can secure it today — say so instead of naming an account that
    # would reject the order.
    best_any = max(cash, key=lambda k: cash[k]["deployable_cash"]) if cash else None
    return {
        "buy_account": holders[0] if holders else best_any,
        "consolidates": bool(holders),
        "funded": False,
        "shortfall": round(need - (max((v["deployable_cash"] for v in cash.values()), default=0)), 2),
    }


def _cash_by_account(db: Session, exclude: List[str]) -> Dict[str, Dict]:
    """Cash per account_id, split into total vs. what can actually secure a
    NEW put.

    These are different numbers and conflating them overstates capacity by
    an order of magnitude. `_calc_true_cash` (used by the True Portfolio
    strip) adds options collateral back for IRAs — correct for "what is this
    account worth", since locked collateral is still the owner's money. It is
    wrong for "what can I sell a put against today": that collateral is
    already committed to existing puts. Neel's Retirement reads $244,762
    true cash and only $27,262 deployable.

    Deployable: IRA = cash_balance (collateral already spent). Brokerage =
    cash − margin_used, floored at 0 — an account already $94K into margin
    has no unencumbered cash to secure anything.
    """
    try:
        from app.ingestion.router import _calc_true_cash
        from app.modules.strategies.models import AccountCashBalance
    except ImportError:
        return {}
    name_to_id = {r.account_name: r.account_id for r in db.execute(_text(
        "SELECT account_id, account_name FROM investment_accounts")).fetchall()}
    brokerage = {"Neel's Brokerage", "Jaya's Brokerage", "Alisha's Brokerage"}
    out: Dict[str, Dict] = {}
    for row in db.query(AccountCashBalance).all():
        if name_to_id.get(row.account_name) in exclude:
            continue
        is_brok = row.account_name in brokerage
        fmt = "brokerage" if is_brok else "ira"
        cash = float(row.cash_balance or 0)
        coll = float(row.options_collateral or 0)
        margin = float(row.margin_used or 0)
        total = _calc_true_cash(cash, coll, float(row.pending_orders or 0), margin, fmt)
        deployable = max(0.0, cash - margin) if is_brok else max(0.0, cash)
        out[name_to_id.get(row.account_name, row.account_name)] = {
            "account_name": row.account_name,
            "total_cash": round(total, 2),
            "deployable_cash": round(deployable, 2),
            "collateral_committed": round(coll, 2),
            "margin_used": round(margin, 2),
            "sheltered": name_to_id.get(row.account_name) in SHELTERED_ACCOUNTS,
        }
    return out


def _baseline_shares(db: Session, as_of: str, alias: Dict[str, str],
                     exclude: List[str]) -> Dict[str, float]:
    """Share counts on the day the policy was set, from daily history.

    No new storage and no snapshot step: `investment_holdings_history` has
    per-symbol quantities every day back to 2026-02-16, so progress is
    computable retroactively and stays correct even if this feature is
    turned on months late.

    Returns {} when history does not actually reach the policy date — the
    caller then treats today's holdings as the baseline (progress = 0).
    History lags by a day or two, so taking "latest snapshot <= policy date"
    unconditionally compared a 2-day-old snapshot against today and reported
    100 phantom shares moved, 6.2% executed, before a single order existed.
    """
    row = db.execute(_text("""
        SELECT MAX(snapshot_date) AS d FROM investment_holdings_history
        WHERE snapshot_date <= :d
    """), {"d": as_of}).fetchone()
    if not row or not row.d or str(row.d) < as_of:
        return {}
    out: Dict[str, float] = {}
    for r in db.execute(_text("""
        SELECT symbol, SUM(quantity) AS q FROM investment_holdings_history
        WHERE snapshot_date = :d AND symbol NOT IN ('CASH', 'FDRXX')
          AND NOT (account_id = ANY(:ex))
        GROUP BY symbol
    """), {"d": row.d, "ex": exclude}).fetchall():
        sym = alias.get(r.symbol, r.symbol)
        out[sym] = out.get(sym, 0.0) + float(r.q or 0)
    return out


def _premium_since(db: Session, since: str, symbols: List[str]) -> float:
    """Net options premium collected on plan symbols since the policy date.

    Shown *next to* shares moved, never instead of it. At ATM roughly half
    the contracts expire unassigned, so premium can run for months while the
    position does not move at all — that divergence is the single thing this
    plan can get wrong while feeling like it is working.
    """
    if not symbols:
        return 0.0
    r = db.execute(_text("""
        SELECT COALESCE(SUM(amount), 0) AS p FROM investment_transactions
        WHERE symbol = ANY(:s) AND transaction_date >= :d
          AND transaction_type IN ('STO', 'BTC')
    """), {"s": symbols, "d": since}).fetchone()
    return round(float(r.p or 0), 2)


def get_allocation_plan(db: Session) -> Dict:
    cfg = load_targets()
    perf = get_pure_performance(db)
    lots = {p["symbol"]: p for p in perf.get("open_positions", [])}
    alias = {k: v for k, v in (cfg.get("aliases") or {}).items() if not k.startswith("_")}
    exclude = _excluded_accounts(cfg)
    accounts_by_sym = _holdings_by_account(db, alias, exclude)
    # Shares come from holdings, not lots — see _holdings_by_account.
    held_shares = {s: sum(a["shares"] for a in acc) for s, acc in accounts_by_sym.items()}
    live = _fresh_prices(db)
    for a, b in alias.items():
        if b not in live and a in live:
            live[b] = live[a]
    ref_block = cfg.get("reference_prices", {}) or {}
    ref_prices = ref_block.get("prices", {}) or {}
    ref_as_of = ref_block.get("as_of")
    open_short = _open_short_contracts(db)
    call_strikes = _open_call_strikes(db)
    call_strikes_by_acct = _open_call_strikes_by_account(db)
    rolldowns = _recent_call_rolldowns(db)
    non_optionable = cfg.get("non_optionable", {}) or {}
    exp = next_expiration(date.today())
    policy_as_of = cfg.get("as_of") or str(date.today())
    cash_by_acct = _cash_by_account(db, exclude)
    baseline = _baseline_shares(db, policy_as_of, alias, exclude)
    pending = _pending_assignments(db, live, alias)
    lots_by_acct = _lots_by_account(db, exclude, alias)

    def price_of(sym: str):
        """(price, source). Live always wins; config reference is the
        fallback for target names not yet held, where the app has no quote
        source at all."""
        if sym in live:
            return live[sym], "live"
        if sym in ref_prices:
            return float(ref_prices[sym]), "reference"
        return None, "none"

    def current_value(sym: str, shares: float, px: Optional[float]) -> Optional[float]:
        if px is not None:
            return shares * px
        # Unpriced but held: fall back to lot cost basis so the denominator
        # stays complete rather than silently dropping the position out.
        p = lots.get(sym)
        return (p.get("cost_basis") if p else 0.0) or 0.0

    # Base = every position actually held, priced consistently. Includes
    # off-thesis names (still capital today) so percentages sum against the
    # real book, not just the target universe.
    base = 0.0
    for sym, sh in held_shares.items():
        px, _ = price_of(sym)
        base += current_value(sym, sh, px) or 0.0

    def build_row(sym: str, target_shares: Optional[int], action_kind: str) -> Dict:
        cur_shares = held_shares.get(sym, 0.0)
        accts = accounts_by_sym.get(sym, [])
        px, px_source = price_of(sym)
        cur_val = current_value(sym, cur_shares, px) or 0.0
        tgt_shares = 0 if target_shares is None else int(target_shares)
        tgt_val = (tgt_shares * px) if px is not None else None
        gap_shares = tgt_shares - cur_shares
        optionable = sym not in non_optionable

        if action_kind == "exit":
            action = "exit" if cur_shares > 0 else "done"
        elif gap_shares >= SHARES_PER_CONTRACT:
            action = "buy"
        elif gap_shares <= -SHARES_PER_CONTRACT:
            action = "trim"
        else:
            action = "hold"

        contracts = int(abs(gap_shares)) // SHARES_PER_CONTRACT
        # Shares the round-lot rule cannot express as a contract. MU is the
        # live case: 40 held against a 200 target is a 160-share gap, of
        # which only 100 is sellable as a put — the other 60 is an odd lot
        # that stays odd unless bought outright.
        residual = int(abs(gap_shares)) % SHARES_PER_CONTRACT
        option_type = "put" if action == "buy" else "call" if action in ("trim", "exit") else None
        already = open_short.get((sym, option_type), 0) if option_type else 0

        # Netting differs by side, because an open contract means different
        # things on each:
        #   PUTS (buy side)  — an open short put will assign and deliver the
        #     shares. It is genuinely progress toward the target, so net it
        #     out: 5 already sold means 5 more, not 10.
        #   CALLS (sell side) — the open calls are Tier-1 far-OTM contracts
        #     written to KEEP the stock (delta 10-15). They occupy the shares
        #     so no new call can be written against them, but they will not
        #     produce the trim. Reporting "sell 0 calls" would read as
        #     "nothing to do" when the real instruction is to roll them down
        #     to ATM. So: uncovered shares get a SELL, covered shares get a
        #     ROLL, and the row says which.
        new_contracts = max(0, contracts - already)
        roll_contracts = 0
        if option_type == "call":
            # `contracts` calls need to reach ATM to produce the trim.
            # Subtract however many are ALREADY credited as done — that's
            # completed work, not just a smaller pool to pick from (the
            # bug in the first version of this fix: capping against the
            # not-yet-near-ATM pool instead of reducing the requirement
            # itself left this unchanged at 4 even with 1 real roll
            # already done).
            #
            # "Done" means either: genuinely ITM already (heading to
            # assignment regardless of roll history — an old strike the
            # stock simply grew past needs no roll to be "finished"), or
            # verified near-ATM via an actual roll AT THE TIME it happened
            # (2026-08-11: a static percentage-of-today's-spot check alone
            # can't tell "rolled to maintain ATM" apart from "an old
            # far-OTM strike the stock later happened to grow near" —
            # only the transaction ledger, checked against the PRICE ON
            # THAT DATE, can — see _recent_call_rolldowns).
            already_near_atm = 0
            if px is not None:
                atm_target = strike_for(px, OTM_ATM)
                rolled = rolldowns.get(sym, {})
                already_near_atm = _credited_call_contracts(
                    call_strikes.get(sym, []), px, atm_target, rolled)
            remaining_trim = max(0, contracts - already_near_atm)
            still_open_not_done = max(0, already - already_near_atm)
            roll_contracts = min(remaining_trim, still_open_not_done)
        net = new_contracts if option_type == "put" else new_contracts

        order = None
        if optionable and px is not None and option_type and (new_contracts or roll_contracts):
            o = atm_order(new_contracts or roll_contracts, px)
            order = {
                "option_type": option_type,
                "instruction": "sell" if new_contracts else "roll",
                "contracts": new_contracts or roll_contracts,
                "sell_contracts": new_contracts,
                "roll_contracts": roll_contracts,
                "strike": o["strike"],
                "est_premium": o["est_premium"],
                "expiration": str(exp),
                "estimated": True,
            }

        # Shares already committed by ITM short puts, and where that lands
        # the position once they settle.
        pend = pending.get(sym)
        incoming = pend["shares"] if pend else 0
        projected = cur_shares + incoming
        overshoot = projected - tgt_shares if incoming else 0

        # Why a row has no order — silence reads as "nothing to do", which is
        # wrong for a 20-share LLY position that still needs exiting.
        guidance = None
        if order is None and option_type == "put" and already >= contracts > 0:
            guidance = (f"{already} put{'' if already == 1 else 's'} already open — covers the "
                        f"{contracts} needed. Nothing to sell.")
        elif order is None:
            if not optionable:
                guidance = non_optionable.get(sym) or "No options market — hold or trade outright."
            elif px is None:
                guidance = "No price source — cannot size an order."
            elif action == "hold":
                guidance = "At target."
            elif action == "done":
                guidance = "Position closed."
            elif contracts == 0:
                n_sh = int(abs(gap_shares))
                guidance = (f"{n_sh} share{'' if n_sh == 1 else 's'} — under one contract, "
                            "so no option expresses it. Trade outright.")

        # Where to place it. Trims route to the least-taxed account holding
        # whole lots; buys route to the account already holding the name so
        # the position stays in one place (Neel's consolidation ask).
        routing = None
        if px is not None and action in ("trim", "exit") and contracts > 0:
            # An assigned call sells at the STRIKE, not at spot — so the strike
            # is what sets the realized gain. Passing spot understated TSLA's
            # harvested loss by ~$1,900 on 400 shares, and the gap widens the
            # further the strike sits from spot.
            sale_px = order["strike"] if order else px
            atm_target = strike_for(px, OTM_ATM)
            rolled = rolldowns.get(sym, {})

            # Two mechanically DIFFERENT kinds of leg, not one blended pool
            # (2026-08-14, second bug in one day on this same routing):
            #
            # ROLL legs — an account's own EXISTING call that isn't yet
            # credited (not ITM, not verified near-ATM). There's no "which
            # account's shares" choice here: you roll YOUR OWN open
            # contract, full stop. Read straight off call_strikes_by_acct.
            #
            # SELL legs — brand-new contracts, which can ONLY go against
            # shares with NO existing call AT ALL (any strike, credited or
            # not) — an account whose shares already back an uncredited
            # call has zero naked shares left; selling a fresh contract
            # there would be a second call against the same 100 shares,
            # which isn't a real order. Found on INTC: Jaya's IRA had just
            # sold 3 calls at $110 (genuinely still OTM, so uncredited —
            # correctly gets a ROLL leg) but its 300 shares, already fully
            # spoken for by that contract, were ALSO being routed for a
            # fresh "sell 3" on top, because the old single-pool routing
            # only excluded CREDITED coverage, not all existing coverage.
            roll_legs = []
            for a in accts:
                aid = a["account_id"]
                for st, c in call_strikes_by_acct.get((sym, aid), []):
                    credited = _credited_call_contracts([(st, c)], px, atm_target, rolled)
                    uncredited = c - credited
                    if uncredited > 0:
                        roll_legs.append({
                            "account_id": aid, "shares": uncredited * SHARES_PER_CONTRACT,
                            "contracts": uncredited, "sheltered": a["sheltered"],
                            "cost_per_share": a["cost_per_share"], "realized_gain": None,
                            "lots": [], "instruction": "roll", "_dist": abs(st - atm_target),
                        })
            # A TRIM only needs enough contracts near ATM to reach the
            # target, not necessarily every currently-uncovered contract
            # moved — NVDA has held 16 open calls against only ~8 needed
            # for its 761-share trim; rolling all 14 uncredited ones toward
            # ATM would overshoot the 1,000-share target by hundreds of
            # shares once they all assign. Cap at roll_contracts (already
            # computed above as the genuine remaining need), closest-to-
            # ATM strikes first — those finish with the least work, and an
            # EXIT (target 0) has no such ceiling since every share is
            # meant to leave regardless (roll_contracts there already
            # equals every uncredited contract, so the cap is a no-op).
            roll_legs.sort(key=lambda l: l["_dist"])
            capped, cap_left = [], roll_contracts
            for leg in roll_legs:
                if cap_left <= 0:
                    break
                take = min(leg["contracts"], cap_left)
                leg = {**leg, "contracts": take, "shares": take * SHARES_PER_CONTRACT}
                del leg["_dist"]
                capped.append(leg)
                cap_left -= take
            # One account can hold call_strikes_by_acct entries at MULTIPLE
            # strikes at once (SPCX in Neel's Brokerage: 1 @ $145, 1 @ $150,
            # both uncredited) — each produced its own leg above, which
            # rendered as two separate, identically-worded "roll 1 call"
            # cards for the same account (found 2026-08-19). The strike
            # itself doesn't survive into the card text (it shows the
            # shared ATM target, not each leg's own current strike), so
            # merge same-account legs into one before returning.
            merged: Dict[str, Dict] = {}
            for leg in capped:
                aid = leg["account_id"]
                if aid in merged:
                    merged[aid]["contracts"] += leg["contracts"]
                    merged[aid]["shares"] += leg["shares"]
                else:
                    merged[aid] = dict(leg)
            roll_legs = list(merged.values())

            sell_legs, gain_avoided, basis_unknown = [], 0.0, False
            if new_contracts > 0:
                naked_accts = [
                    {**a, "shares": max(0.0, a["shares"] - SHARES_PER_CONTRACT * sum(
                        c for _st, c in call_strikes_by_acct.get((sym, a["account_id"]), [])))}
                    for a in accts
                ]
                sell_routing = _route_trim_lots(
                    sym, naked_accts, new_contracts * SHARES_PER_CONTRACT, sale_px, lots_by_acct)
                sell_legs = sell_routing["legs"]
                gain_avoided = sell_routing["gain_avoided_vs_worst"]
                basis_unknown = sell_routing["basis_unknown"]

            routing = {"legs": sell_legs + roll_legs, "gain_avoided_vs_worst": gain_avoided,
                      "basis_unknown": basis_unknown, "lot_aware": True}
        elif action == "buy" and px is not None:
            routing = _route_buy(accts, cash_by_acct, order["strike"] if order else px)

        # Progress since the policy date, in SHARES. With no history covering
        # the policy date, today's position IS the baseline — the plan starts
        # now and progress is honestly zero.
        b0 = baseline.get(sym, cur_shares) if baseline else cur_shares
        moved = (cur_shares - b0) if b0 is not None else None
        needed = (tgt_shares - b0) if b0 is not None else None
        closed_pct = None
        if needed:
            closed_pct = round(max(0.0, min(100.0, 100 * (moved / needed))), 1)
        elif needed == 0:
            closed_pct = 100.0

        return {
            "symbol": sym,
            "accounts": accts,
            "routing": routing,
            "baseline_shares": b0,
            "shares_moved": moved,
            "gap_closed_pct": closed_pct,
            "incoming_shares": incoming,
            "projected_shares": projected,
            "overshoot_shares": overshoot,
            "pending_expiry": pend["next_expiry"] if pend else None,
            "pending_collateral": round(pend["collateral"], 2) if pend else 0.0,
            "current_shares": cur_shares,
            "current_value": round(cur_val, 2),
            "current_pct": round(100 * cur_val / base, 2) if base else None,
            "target_shares": tgt_shares,
            "target_value": round(tgt_val, 2) if tgt_val is not None else None,
            "target_pct": round(100 * tgt_val / base, 2) if (tgt_val is not None and base) else None,
            "gap_shares": gap_shares,
            "gap_value": round((tgt_val - cur_val), 2) if tgt_val is not None else None,
            "action": action,
            "contracts": contracts,
            "residual_shares": residual,
            "open_contracts": already,
            "net_contracts": net,
            "order": order,
            "guidance": guidance,
            "optionable": optionable,
            "non_optionable_reason": non_optionable.get(sym),
            "price": round(px, 2) if px is not None else None,
            "price_source": px_source,
            "price_as_of": ref_as_of if px_source == "reference" else None,
        }

    buckets: List[Dict] = []
    for key, b in (cfg.get("buckets") or {}).items():
        rows = [build_row(s, n, "target") for s, n in (b.get("targets") or {}).items()]
        rows.sort(key=lambda r: -(r["target_value"] or 0))
        cur_sum = sum(r["current_value"] for r in rows)
        tgt_sum = sum(r["target_value"] or 0 for r in rows)
        # Bucket progress is summed in ABSOLUTE shares needed vs moved —
        # signed sums would let a NVDA trim cancel an MU buy and report
        # progress where none happened.
        need = sum(abs(r["target_shares"] - r["baseline_shares"])
                   for r in rows if r["baseline_shares"] is not None)
        did = sum(min(abs(r["shares_moved"] or 0),
                      abs(r["target_shares"] - r["baseline_shares"]))
                  for r in rows if r["baseline_shares"] is not None
                  and (r["shares_moved"] or 0) * (r["target_shares"] - r["baseline_shares"]) > 0)
        buckets.append({
            "key": key,
            "label": b.get("label", key),
            "note": b.get("note"),
            "target_pct": b.get("target_pct"),
            "rows": rows,
            "current_value": round(cur_sum, 2),
            "current_pct": round(100 * cur_sum / base, 2) if base else None,
            "target_value": round(tgt_sum, 2),
            "target_computed_pct": round(100 * tgt_sum / base, 2) if base else None,
            "shares_needed": round(need),
            "shares_moved": round(did),
            "gap_closed_pct": round(100 * did / need, 1) if need else 100.0,
        })

    # Buy-shares fallback for unfunded, cheap-RSI buy targets (Neel,
    # 2026-08-11, see module docstring). Runs AFTER every row exists so it
    # never changes any existing put/`funded` result -- purely additive.
    #
    # Reserve spare cash against every buy target that's already funded, in
    # bucket/declaration order, using the REAL total collateral (strike *
    # 100 * all contracts) rather than the single-contract check
    # `_route_buy` uses for "funded" -- otherwise two funded-looking targets
    # sharing one account (e.g. AMZN + MRVL both routed to the same IRA)
    # would each look like they have the account's full cash still free,
    # when placing both wouldn't actually fit. Only after this reservation
    # is what's left genuinely uncommitted.
    buy_rows = [r for bkt in buckets for r in bkt["rows"] if r["action"] == "buy"]
    spare_cash = {k: v["deployable_cash"] for k, v in cash_by_acct.items()}
    for r in buy_rows:
        o = r.get("order")
        acct = (r.get("routing") or {}).get("buy_account")
        if o and (r["routing"] or {}).get("funded") and acct in spare_cash:
            need = o["strike"] * SHARES_PER_CONTRACT * (o.get("sell_contracts") or o.get("contracts") or 0)
            spare_cash[acct] = max(0.0, spare_cash[acct] - need)

    for r in buy_rows:
        if (r["routing"] or {}).get("funded", True) or not r.get("price"):
            continue  # already fundable via puts, or unpriced -- nothing to add
        sym = r["symbol"]
        holder_ids = [a["account_id"] for a in r["accounts"] if a["shares"] > 0]
        entry = get_entry_timing(db, holder_ids[0] if holder_ids else "neel_brokerage", sym)
        rsi = entry.get("rsi") if entry.get("available") else None
        if rsi is None or rsi >= 50:
            continue  # no signal, or not actually cheap -- don't buy into strength
        # Prefer an account already holding the name (consolidation, same
        # rule _route_buy uses), else whichever account has the most spare
        # cash left after the reservation pass above.
        candidates = {a: spare_cash[a] for a in holder_ids if a in spare_cash and spare_cash[a] > 0}
        acct = max(candidates, key=candidates.get) if candidates else (
            max(spare_cash, key=spare_cash.get) if spare_cash else None)
        if not acct:
            continue
        shares = int(spare_cash[acct] // r["price"])
        if shares < 1:
            continue
        cash_used = round(shares * r["price"], 2)
        r["share_buy"] = {
            "account_id": acct, "shares": shares, "cash_used": cash_used,
            "rsi": round(rsi, 1), "consolidates": acct in holder_ids,
        }
        spare_cash[acct] = round(spare_cash[acct] - cash_used, 2)

    exit_cfg = cfg.get("exit", {}) or {}
    exit_rows = [build_row(s, 0, "exit") for s in (exit_cfg.get("symbols") or [])
                 if held_shares.get(s, 0) > 0]
    exit_rows.sort(key=lambda r: -r["current_value"])

    # Feasibility: ATM puts tie up strike * 100 * contracts in collateral.
    # A plan that cannot be placed must say so rather than list orders.
    collateral_needed = sum(
        r["order"]["strike"] * 100 * r["order"]["sell_contracts"]
        for bkt in buckets for r in bkt["rows"]
        if r["order"] and r["order"]["option_type"] == "put"
    )
    proceeds = sum(r["current_value"] for r in exit_rows) + sum(
        -(r["gap_value"] or 0) for bkt in buckets for r in bkt["rows"] if r["action"] == "trim"
    )
    total_cash = round(sum(v["total_cash"] for v in cash_by_acct.values()), 2) if cash_by_acct else None
    deployable = round(sum(v["deployable_cash"] for v in cash_by_acct.values()), 2) if cash_by_acct else 0.0
    funded_by = deployable + proceeds
    # A cash-secured put can only be sold where the cash sits, so the binding
    # constraint is the single largest account, not the sum.
    biggest = max((v["deployable_cash"] for v in cash_by_acct.values()), default=0.0)
    unaffordable = sorted({
        r["symbol"] for bkt in buckets for r in bkt["rows"]
        if r["order"] and r["order"]["option_type"] == "put"
        and r["order"]["strike"] * SHARES_PER_CONTRACT > biggest
    })
    # Forward view of collateral already committed to open puts. Reporting
    # only today's free cash understated capacity: $381,750 sits in puts that
    # all expire within days. But it does not all come back as cash — the ITM
    # ones convert to stock, much of it in names outside the plan.
    plan_universe = {r["symbol"] for bkt in buckets for r in bkt["rows"]}
    locked = round(sum(p["collateral"] for p in pending.values()), 2)
    returning = round(sum(p["cash_returning"] for p in pending.values()), 2)
    converting = round(locked - returning, 2)
    off_plan = sorted({s for s, p in pending.items()
                       if p["shares"] > 0 and s not in plan_universe})
    off_plan_value = round(sum(p["collateral"] - p["cash_returning"]
                               for s, p in pending.items()
                               if p["shares"] > 0 and s not in plan_universe), 2)
    next_exp = min((p["next_expiry"] for p in pending.values() if p["next_expiry"]), default=None)

    feasibility = {
        "put_collateral_needed": round(collateral_needed, 2),
        "total_cash": total_cash,
        "deployable_cash": deployable,
        "collateral_locked_in_open_puts": locked,
        "collateral_returning_as_cash": returning,
        "collateral_converting_to_stock": converting,
        "collateral_converting_off_plan": off_plan_value,
        "off_plan_assignments": off_plan,
        "next_put_expiry": next_exp,
        "cash_after_expiry": round(deployable + returning, 2),
        "cash_by_account": cash_by_acct,
        "largest_single_put_affordable": round(biggest, 2),
        "unaffordable_today": unaffordable,
        "exit_and_trim_proceeds": round(proceeds, 2),
        "headroom": round(funded_by - collateral_needed, 2),
        "covered": funded_by >= collateral_needed,
        "covered_by_cash_alone": deployable >= collateral_needed,
        "note": ("Selling ATM puts ties up the full strike notional as collateral, and a "
                 "cash-secured put can only be sold where the cash actually sits — so the "
                 "limit is the largest single account, not the total. Deployable cash "
                 "excludes collateral already securing open puts and any account already "
                 "drawn on margin. The buy program is funded by exit and trim proceeds, "
                 "which means the sells must clear first. Staged, not simultaneous."),
    }

    stale = [r["symbol"] for bkt in buckets for r in bkt["rows"] if r["price_source"] == "reference"]
    plan_syms = [r["symbol"] for bkt in buckets for r in bkt["rows"]]
    tot_need = sum(b["shares_needed"] for b in buckets)
    tot_did = sum(b["shares_moved"] for b in buckets)
    days = (date.today() - date.fromisoformat(policy_as_of)).days
    # Velocity needs a real window. Annualising two days of noise produced
    # "700 shares/week, 2.5 weeks to target" on the day the policy was set,
    # off a baseline snapshot that was itself two days stale. Below a week,
    # report position only and say why.
    MIN_DAYS = 7
    measurable = days >= MIN_DAYS
    rate = (tot_did / days * 7) if (measurable and days > 0) else None
    progression = {
        "since": policy_as_of,
        "days_elapsed": days,
        "measurable": measurable,
        "shares_needed": tot_need,
        "shares_moved": tot_did,
        "gap_closed_pct": round(100 * tot_did / tot_need, 1) if tot_need else 100.0,
        "shares_per_week": round(rate, 1) if rate else None,
        "weeks_to_target": round((tot_need - tot_did) / rate, 1) if rate else None,
        "premium_since": _premium_since(db, policy_as_of, plan_syms),
        "note": ("Progress is counted in SHARES, not dollars. At ATM roughly half the "
                 "contracts expire unassigned, so premium can accumulate for months while "
                 "the position does not move — if premium climbs and shares do not, the "
                 "plan is not working no matter how good the income looks."),
        "early_note": (None if measurable else
                       f"Policy set {policy_as_of} ({days}d ago). Velocity and ETA need at "
                       f"least {MIN_DAYS} days of history to mean anything."),
    }

    return {
        "as_of": perf.get("as_of") or str(date.today()),
        "policy_as_of": policy_as_of,
        "base_value": round(base, 2),
        # Surfaced, not silent: an excluded account quietly shrinking the
        # denominator is the kind of thing that is impossible to notice later.
        "excluded_accounts": exclude,
        "expiration": str(exp),
        "buckets": buckets,
        "exit_rows": exit_rows,
        "feasibility": feasibility,
        "progression": progression,
        "reference_priced_symbols": stale,
        "premium_disclaimer": (
            "Strike and premium are heuristics from the same helper the Options "
            "Execution page uses, not live quotes — no working option-chain feed "
            "exists as of 2026-08-08."
        ),
    }
