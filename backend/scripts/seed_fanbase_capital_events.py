"""
Seed FanbaseAI capital events from ICICI bank statement analysis.

These are business payments (employee salaries, contractor payments) made
from Neel's ICICI account for FanbaseAI operations.

Total: ₹24,58,481.80 / ~$29,620 USD (at ₹83/$)

Run with: cd backend && python -m scripts.seed_fanbase_capital_events
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.core.database import SessionLocal
from app.modules.equity.models import EquityCompany, EquityCapitalEvent


# Exchange rate used for conversion
INR_PER_USD = Decimal("83")

# ICICI bank statement transactions for FanbaseAI
TRANSACTIONS = [
    {
        "date": date(2023, 8, 7),
        "payee": "INVADEHQ P",
        "description": "Payroll Aug 2023",
        "inr": Decimal("250713.70"),
    },
    {
        "date": date(2023, 9, 11),
        "payee": "INVADEHQ P",
        "description": "Payroll Sep 2023",
        "inr": Decimal("203492.70"),
    },
    {
        "date": date(2023, 10, 10),
        "payee": "INVADEHQ P",
        "description": "Payroll Oct 2023",
        "inr": Decimal("600000.00"),
    },
    {
        "date": date(2023, 10, 26),
        "payee": "Chetan Jag",
        "description": "Salary Oct 2023",
        "inr": Decimal("140017.70"),
    },
    {
        "date": date(2023, 10, 28),
        "payee": "Mohd Omer",
        "description": "Salary Oct 2023",
        "inr": Decimal("25005.90"),
    },
    {
        "date": date(2023, 11, 1),
        "payee": "Rohan Garg",
        "description": "Payment Nov 2023",
        "inr": Decimal("500000.00"),
    },
    {
        "date": date(2023, 11, 1),
        "payee": "Rohan Garg",
        "description": "Payment Nov 2023 (additional)",
        "inr": Decimal("149240.00"),
    },
    {
        "date": date(2023, 11, 16),
        "payee": "Rohan Garg",
        "description": "Payment Nov 2023",
        "inr": Decimal("30000.00"),
    },
    {
        "date": date(2023, 11, 28),
        "payee": "Chetan Jag",
        "description": "Dec 2023 payment",
        "inr": Decimal("70000.00"),
    },
    {
        "date": date(2023, 11, 28),
        "payee": "Mohd Omer",
        "description": "Nov+Dec 2023 payment",
        "inr": Decimal("50000.00"),
    },
    {
        "date": date(2023, 11, 28),
        "payee": "Rohan Garg",
        "description": "Payment Nov 2023",
        "inr": Decimal("150000.00"),
    },
    {
        "date": date(2024, 1, 6),
        "payee": "Chetan Jag",
        "description": "Jan 2024 payment",
        "inr": Decimal("70000.00"),
    },
    {
        "date": date(2024, 1, 6),
        "payee": "Mohd Omer",
        "description": "Jan 2024 payment",
        "inr": Decimal("25000.00"),
    },
    {
        "date": date(2024, 3, 6),
        "payee": "Chetan Jag",
        "description": "Mar 2024 payment",
        "inr": Decimal("70005.90"),
    },
    {
        "date": date(2024, 3, 6),
        "payee": "Mohd Omer",
        "description": "Mar 2024 salary",
        "inr": Decimal("25005.90"),
    },
    {
        "date": date(2024, 3, 24),
        "payee": "Himanshu Varshn",
        "description": "Payment Mar 2024",
        "inr": Decimal("100000.00"),
    },
]


def inr_to_usd(inr_amount: Decimal) -> Decimal:
    """Convert INR to USD at approximate rate."""
    return (inr_amount / INR_PER_USD).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def seed_fanbase_capital_events():
    """Seed FanbaseAI capital events from ICICI bank statement data."""
    db = SessionLocal()

    try:
        # Find FanbaseAI company
        company = db.query(EquityCompany).filter(
            EquityCompany.name.ilike("%fanbase%")
        ).first()

        if not company:
            print("FanbaseAI company not found in equity_companies table.")
            print("Looking for any company with 'fanbase' in the name...")
            all_companies = db.query(EquityCompany).all()
            print(f"Found {len(all_companies)} companies:")
            for c in all_companies:
                print(f"  - {c.id}: {c.name} ({c.dba_name or 'no DBA'})")
            print("\nPlease ensure FanbaseAI exists in the equity_companies table first.")
            return

        print(f"Found company: {company.name} (ID: {company.id})")

        # Check for existing capital events (idempotent)
        existing_events = db.query(EquityCapitalEvent).filter(
            EquityCapitalEvent.company_id == company.id,
            EquityCapitalEvent.event_type == "capital_contribution",
        ).count()

        if existing_events > 0:
            print(f"Found {existing_events} existing capital events for {company.name}.")
            print("Skipping seed to avoid duplicates. Delete existing events first to re-seed.")
            return

        print(f"\nSeeding {len(TRANSACTIONS)} capital events...")

        total_usd = Decimal("0")
        total_inr = Decimal("0")

        for txn in TRANSACTIONS:
            usd_amount = inr_to_usd(txn["inr"])
            total_usd += usd_amount
            total_inr += txn["inr"]

            desc = f"{txn['payee']} - {txn['description']} (₹{txn['inr']:,.2f})"

            event = EquityCapitalEvent(
                company_id=company.id,
                event_date=txn["date"],
                event_type="capital_contribution",
                amount=usd_amount,
                description=desc,
                contributor="Neel Agrawal",
            )
            db.add(event)
            print(f"  {txn['date']} | {txn['payee']:<18} | ₹{txn['inr']:>12,.2f} | ${usd_amount:>10,.2f}")

        # Update company record
        company.total_capital_invested = total_usd
        company.section_1244_eligible = "Y"

        db.commit()

        print(f"\n{'='*70}")
        print(f"Total INR: ₹{total_inr:,.2f}")
        print(f"Total USD: ${total_usd:,.2f} (at ₹{INR_PER_USD}/$)")
        print(f"Events created: {len(TRANSACTIONS)}")
        print(f"Company total_capital_invested updated to ${total_usd:,.2f}")
        print(f"Company section_1244_eligible set to 'Y'")
        print(f"\nDone! FanbaseAI capital events seeded successfully.")

    except Exception as e:
        db.rollback()
        print(f"Error seeding data: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_fanbase_capital_events()
