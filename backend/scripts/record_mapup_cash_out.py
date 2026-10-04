"""Record the MapUp option cash-out in the equity ledger (net worth).

SOURCE DOCUMENTS (data/tax-documents/2026/mapup/)
  2023-05-04 MapUp Advisor Agreement — independent-contractor advisor; NSO
    for 4% of common, vesting monthly over 3 years from 2023-01-01.
  2026-09-29 Option Cancellation Agreement (Project Compass) — Exhibit A:
    112,500 options, granted 2025-05-11, exercise price $0.71, all vested,
    NEVER EXERCISED. Cancelled at the Bestpass, Inc. closing for (i) closing
    consideration and (ii) a pro rata share of any Earnout Consideration
    (SPA §2.06), contingent.
  Bank feed (spending_transactions) — 2026-10-02 wire from TOLLPASS LLC,
    $249,062.27, into Savings ...7358  ==  112,500 x ($2.9239 - $0.71).

WHAT WAS WRONG IN THE LEDGER
  The grant was recorded as "fully exercised at $0 strike" and a phantom
  112,500-share certificate "MAPUP-EXERCISED" sat in equity_shares as held,
  valued at the $1.00 FMV = $112,500 of net worth that never existed as
  shares. The options were cash-settled; no stock was ever issued.

WHAT THIS DOES (idempotent — re-running changes nothing)
  grant E9-2      exercise_price 0.71, exercised 0, status cancelled_cash_out
  shares row      status 'cancelled' (never issued), kept for the audit trail
  company         status 'acquired' (Bestpass), note with the earnout
  capital event   'option_cash_out' $249,062.27 on 2026-10-02

The money itself is already in the Income page (one-time) and the tax
forecast (Schedule C / SE) straight from the bank row; this script only
fixes the ASSET side so net worth stops carrying MapUp as an open position.

Run:  ./venv/bin/python scripts/record_mapup_cash_out.py [--dry-run]
"""
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal  # noqa: E402
from app.modules.equity.models import (  # noqa: E402
    EquityCapitalEvent, EquityCompany, EquityGrant, EquityShares,
)

COMPANY = "MapUp Inc."
GRANT_ID = "E9-2"
STRIKE = Decimal("0.71")
PROCEEDS = Decimal("249062.27")
PAID_ON = date(2026, 10, 2)
SIGNED_ON = date(2026, 9, 29)
PER_SHARE = (PROCEEDS / 112500 + STRIKE).quantize(Decimal("0.0001"))   # 2.9239


def main(dry_run: bool) -> None:
    db = SessionLocal()
    try:
        company = db.query(EquityCompany).filter(EquityCompany.name == COMPANY).one()
        grant = db.query(EquityGrant).filter(
            EquityGrant.company_id == company.id, EquityGrant.grant_id == GRANT_ID).one()
        shares = db.query(EquityShares).filter(
            EquityShares.company_id == company.id).all()
        existing = db.query(EquityCapitalEvent).filter(
            EquityCapitalEvent.company_id == company.id,
            EquityCapitalEvent.event_type == "option_cash_out").first()

        print(f"before: grant status={grant.status} strike={grant.exercise_price} "
              f"exercised={grant.exercised_options}; shares={[ (s.certificate_id, s.status, s.num_shares) for s in shares]}; "
              f"company status={company.status}; event={'present' if existing else 'none'}")

        grant.exercise_price = STRIKE
        grant.exercised_options = 0
        grant.status = "cancelled_cash_out"
        grant.termination_date = PAID_ON
        grant.notes = (f"Cancelled for cash at the Bestpass acquisition (agreement {SIGNED_ON}, paid "
                       f"{PAID_ON}): 112,500 x (${PER_SHARE} - ${STRIKE}) = ${PROCEEDS:,}. Never exercised. "
                       f"Pro rata earnout (SPA s2.06) still contingent.")
        for s in shares:
            if s.status == "held":
                s.status = "cancelled"
                s.sold_date = PAID_ON
                s.sold_price_per_share = PER_SHARE
                s.notes = ("Never issued — the options were cash-settled at closing, not exercised. "
                           "Row kept for the audit trail; status 'cancelled' removes it from net worth.")
        company.status = "acquired"
        company.notes = ((company.notes + "\n") if company.notes else "") + (
            f"Acquired by Bestpass, Inc. (Project Compass), SPA {SIGNED_ON}. Neel's options cash-settled "
            f"{PAID_ON} for ${PROCEEDS:,} via TOLLPASS LLC; earnout contingent. Documents: "
            f"data/tax-documents/2026/mapup/") if "Acquired by Bestpass" not in (company.notes or "") else company.notes
        if not existing:
            db.add(EquityCapitalEvent(
                company_id=company.id, event_date=PAID_ON, event_type="option_cash_out",
                amount=PROCEEDS, contributor="Bestpass, Inc. / TOLLPASS LLC",
                description=(f"Option cancellation at closing: 112,500 NSOs x (${PER_SHARE} - ${STRIKE} strike). "
                             f"Wire to Savings ...7358."),
                notes="Ordinary nonemployee compensation (1099-NEC expected Jan 2027). "
                      "Pro rata share of any Earnout Consideration (SPA s2.06) still contingent.",
            ))
        if dry_run:
            db.rollback()
            print("dry run — rolled back")
        else:
            db.commit()
            print(f"after:  grant status={grant.status} strike={grant.exercise_price} exercised={grant.exercised_options}; "
                  f"company status={company.status}; capital event recorded")
    finally:
        db.close()


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
