"""Shared strike + premium heuristics for short-option recommendations.

Extracted from `v6_engine` 2026-08-08 so the Investments allocation plan and
the Options Execution queue quote the SAME numbers for the same symbol. Two
pages computing premium two ways is how "the app told me $2,160 over here
and $890 over there" happens — one definition, or they drift.

These are **heuristics, not quotes.** They price the delta-TARGET strike off
spot and a flat per-notional rate; they know nothing about the actual chain,
IV, or bid/ask. Every surface that renders them must label them "est."
Replace with real chain data when a working feed exists — as of 2026-08-08
there is none (Schwab tokens revoked, yfinance chain endpoint broken).
"""
from datetime import date, timedelta

# OTM offsets by policy tier — the strike each delta rule wants, as a
# fraction of spot. Transcribed from docs/OPTIONS-STRATEGY-V6-ENGINES.md.
OTM_TIER1_TAXABLE = 0.055   # delta 10-15
OTM_TIER1_SHELTERED = 0.045  # delta 15
OTM_TSLA = 0.06             # delta 10-12 carve-out
OTM_ATM = -0.01             # Tier-2 wheel "ATM": spot less 1%, assignment wanted

# Weekly premium as a fraction of notional (contracts * 100 * spot).
# The far-OTM Tier-1 strike collects little; the ATM strike collects ~4x.
RATE_TIER1_WEEKLY = 0.0030
RATE_ATM_WEEKLY = 0.012


def friday_on_or_after(d: date) -> date:
    """The Friday of d's week (d itself if d is a Friday)."""
    return d + timedelta(days=(4 - d.weekday()) % 7)


def next_expiration(today: date) -> date:
    """Which weekly to sell today.

    Mon-Wed → this Friday. Thu/Fri → next Friday: by Thursday the current
    week's contract is nearly worthless and selling it is not a real order.
    Mirrors the `today.weekday() <= 2` branch v6_engine uses.
    """
    this_friday = friday_on_or_after(today)
    if today.weekday() <= 2:
        return this_friday
    return friday_on_or_after(this_friday + timedelta(days=3))


def strike_for(spot: float, otm_pct: float) -> float:
    """Strike the delta rule wants. Negative otm_pct = below spot (ATM/ITM)."""
    return spot * (1 + otm_pct)


def weekly_premium(contracts: int, spot: float, rate: float) -> int:
    """Estimated premium in dollars for `contracts` weeklies at `rate`.

    Valid only when the recommended strike is at/near the delta target the
    rate was calibrated for — a strike moved elsewhere (e.g. raised to a
    cost-basis floor) collects something else entirely, and callers must
    not pair this figure with a moved strike.
    """
    return int(contracts * 100 * spot * rate)


def atm_order(contracts: int, spot: float) -> dict:
    """The ATM short-option order used by the allocation plan.

    "Aggressive" is fixed at ATM (Neel, 2026-08-08): max premium, roughly
    even odds of assignment per expiry. Deliberately NOT labelled "delta
    80" — that label was retired in v6_engine for being misleading, since a
    true delta-80 contract is deep ITM and matched neither documented
    policy.

    Strike is rounded to the nearest WHOLE DOLLAR, not the nearest cent
    (Neel, 2026-08-11, re: an INTC card reading "roll to ATM ~$96.20" —
    real listed strikes near spot trade in $1 increments; $96.20 was never
    a real, placeable contract, just raw spot*0.99 with no chain awareness,
    same gap this module's own docstring already flags. Confirmed live
    against the actual chain: INTC $95/$96/$97 exist, $96.20 does not.
    Whole-dollar rounding matches how every OTHER strike in v6_engine is
    already displayed (`.0f`) — this was the one spot still showing raw
    cents. Still a heuristic, not a real chain lookup — only guaranteed
    real because large/mid-cap names near this price range list in $1
    steps, not because anything here checked the live chain."""
    return {
        "strike": float(round(strike_for(spot, OTM_ATM))),
        "est_premium": weekly_premium(contracts, spot, RATE_ATM_WEEKLY),
        "estimated": True,
    }
