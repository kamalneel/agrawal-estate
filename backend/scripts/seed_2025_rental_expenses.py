"""
Seed 2025 rental expenses from consultant's Schedule E and add dependent for CTC.

This script:
1. Populates PropertyRentalExpense with actual 2025 data from the tax consultant's
   filed Schedule E for 303 Hartstene Drive
2. Adds Alisha Agrawal as a tax dependent for 2025 (Child Tax Credit)
3. Updates W2 dependent_care_benefits for Jaya's 2025 W-2 ($808)

Run with: cd backend && python -m scripts.seed_2025_rental_expenses
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from decimal import Decimal

from app.core.database import SessionLocal
from app.modules.real_estate.models import PropertyRentalExpense, Property
from app.modules.income.models import TaxDependent, W2Record


# 2025 Schedule E expenses from consultant's filed return
EXPENSES_2025 = [
    ('advertising', Decimal('600')),
    ('auto_and_travel', Decimal('250')),
    ('cleaning_and_maintenance', Decimal('1500')),
    ('insurance', Decimal('700')),
    ('legal_and_professional_fee', Decimal('300')),
    ('supplies', Decimal('800')),
    ('property_tax', Decimal('11995')),
    ('other', Decimal('5040')),  # HOA dues reported as "other" on Schedule E line 19
]


def seed_rental_expenses():
    """Seed 2025 rental expenses from consultant data."""
    db = SessionLocal()
    try:
        # Find 303 Hartstene property
        prop = db.query(Property).filter(
            Property.address.ilike("%Hartstene%")
        ).first()

        if not prop:
            print("Hartstene property not found. Run property seeding first.")
            return

        print(f"Found property: {prop.address} (ID: {prop.id})")

        created = 0
        updated = 0
        for category, amount in EXPENSES_2025:
            existing = db.query(PropertyRentalExpense).filter(
                PropertyRentalExpense.property_id == prop.id,
                PropertyRentalExpense.tax_year == 2025,
                PropertyRentalExpense.category == category,
            ).first()

            if existing:
                if float(existing.amount) != float(amount):
                    existing.amount = amount
                    updated += 1
                    print(f"  Updated {category}: ${amount:,.2f}")
                else:
                    print(f"  Skipped {category}: already ${amount:,.2f}")
            else:
                db.add(PropertyRentalExpense(
                    property_id=prop.id,
                    tax_year=2025,
                    category=category,
                    amount=amount,
                ))
                created += 1
                print(f"  Created {category}: ${amount:,.2f}")

        total = sum(amt for _, amt in EXPENSES_2025)
        print(f"\nTotal 2025 expenses: ${total:,.2f}")
        print(f"Created: {created}, Updated: {updated}")

        db.commit()
        print("Rental expenses committed.")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


def seed_dependent():
    """Add Alisha Agrawal as tax dependent for 2025."""
    db = SessionLocal()
    try:
        existing = db.query(TaxDependent).filter(
            TaxDependent.name == "Alisha Agrawal",
            TaxDependent.tax_year == 2025,
        ).first()

        if existing:
            print(f"Dependent already exists: {existing.name} (2025)")
            return

        dep = TaxDependent(
            name="Alisha Agrawal",
            relationship_type="child",
            date_of_birth=date(2021, 7, 15),
            tax_year=2025,
            qualifies_for_ctc=True,
        )
        db.add(dep)
        db.commit()
        print(f"Added dependent: Alisha Agrawal (2025, CTC eligible)")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


def seed_dependent_care_benefits():
    """Update W2 dependent_care_benefits for Jaya's 2025 W-2."""
    db = SessionLocal()
    try:
        w2 = db.query(W2Record).filter(
            W2Record.tax_year == 2025,
            W2Record.employee_name.ilike("%Jaya%"),
        ).first()

        if not w2:
            print("Jaya's 2025 W-2 not found. Skipping dependent care benefits update.")
            return

        if float(w2.dependent_care_benefits or 0) > 0:
            print(f"Dependent care benefits already set: ${w2.dependent_care_benefits}")
            return

        w2.dependent_care_benefits = Decimal('808')
        db.commit()
        print(f"Updated {w2.employee_name}'s 2025 W-2: dependent_care_benefits = $808")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Seeding 2025 Rental Expenses")
    print("=" * 60)
    seed_rental_expenses()

    print()
    print("=" * 60)
    print("Seeding Tax Dependent")
    print("=" * 60)
    seed_dependent()

    print()
    print("=" * 60)
    print("Seeding Dependent Care Benefits")
    print("=" * 60)
    seed_dependent_care_benefits()

    print()
    print("Done!")
