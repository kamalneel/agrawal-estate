"""
Seed script for equity data from Carta.
Based on screenshot from 11/27/2025.

Run with: python -m scripts.seed_equity
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date
from decimal import Decimal

from app.core.database import SessionLocal
from app.modules.equity.models import (
    EquityCompany,
    EquityGrant,
    EquityShares,
    EquityRSA,
    EquitySAFE,
)


def seed_equity_data():
    """Seed equity data from Carta portfolio screenshot."""
    db = SessionLocal()
    
    try:
        # Check if data already exists
        existing = db.query(EquityCompany).first()
        if existing:
            print("Equity data already exists. Skipping seed.")
            print("To re-seed, delete existing data first.")
            return
        
        print("Seeding equity data from Carta...")
        
        # 1. MapUp Inc.
        mapup = EquityCompany(
            name="MapUp Inc.",
            status="active",
            qsbs_eligible="N",
        )
        db.add(mapup)
        db.flush()
        
        # MapUp NSO grant - 112,500 options, all vested
        mapup_grant = EquityGrant(
            company_id=mapup.id,
            grant_id="E9-2",
            grant_type="NSO",
            grant_date=date(2025, 5, 11),
            total_options=112500,
            exercise_price=Decimal("0.01"),  # Placeholder - update with actual
            vested_options=112500,
            exercised_options=0,
            status="active",
        )
        db.add(mapup_grant)
        print(f"  Added MapUp Inc.: 112,500 NSO options")
        
        # 2. Vocalo Inc., DBA Boostup
        boostup = EquityCompany(
            name="Vocalo Inc.",
            dba_name="Boostup",
            status="active",
            qsbs_eligible="Y",
            qsbs_notes="Shares may be eligible for QSBS tax savings",
        )
        db.add(boostup)
        db.flush()
        
        # Boostup ISO grant - 366,497 options (terminated/expired)
        boostup_grant = EquityGrant(
            company_id=boostup.id,
            grant_id="E5-85",
            grant_type="ISO",
            grant_date=date(2023, 3, 23),
            total_options=366497,
            exercise_price=Decimal("0.01"),  # Placeholder
            vested_options=129801,
            exercised_options=0,
            status="terminated",
            notes="Terminated, Expired",
        )
        db.add(boostup_grant)
        
        # Boostup SAFE - $10,000 (canceled)
        boostup_safe = EquitySAFE(
            company_id=boostup.id,
            safe_id="SAFE-7",
            investment_date=date(2018, 6, 11),
            principal_amount=Decimal("10000.00"),
            status="canceled",
            notes="Canceled",
        )
        db.add(boostup_safe)
        
        # Boostup Shares - 29,744 shares (from PS2-8)
        boostup_shares = EquityShares(
            company_id=boostup.id,
            certificate_id="PS2-8",
            share_type="preferred",
            acquisition_date=date(2020, 4, 20),
            num_shares=29744,
            source="purchase",
            status="held",
        )
        db.add(boostup_shares)
        
        # Additional Boostup shares to match 1,662,884 total
        boostup_shares_2 = EquityShares(
            company_id=boostup.id,
            certificate_id="CS-BOOSTUP",
            share_type="common",
            num_shares=1633140,  # 1,662,884 - 29,744
            source="grant",
            status="held",
        )
        db.add(boostup_shares_2)
        
        # Boostup RSAs - 4,746
        boostup_rsa = EquityRSA(
            company_id=boostup.id,
            total_shares=4746,
            vested_shares=4746,
            status="fully_vested",
        )
        db.add(boostup_rsa)
        print(f"  Added Vocalo/Boostup: 366,497 ISO options, 1,662,884 shares, 4,746 RSAs, $10K SAFE (canceled)")
        
        # 3. Aviatrix
        aviatrix = EquityCompany(
            name="Aviatrix",
            status="active",
            current_fmv=Decimal("3.75"),
            fmv_date=date(2025, 11, 27),
        )
        db.add(aviatrix)
        db.flush()
        
        # Aviatrix Grant 1 - 218,000 ISO (terminated, partially exercised)
        aviatrix_grant1 = EquityGrant(
            company_id=aviatrix.id,
            grant_id="E9-33",
            grant_type="ISO",
            grant_date=date(2016, 7, 21),
            total_options=218000,
            exercise_price=Decimal("0.50"),  # Placeholder
            vested_options=218000,
            exercised_options=100000,  # Approximate based on total exercised
            status="terminated",
            notes="Terminated, Partially Exercised, Expired",
        )
        db.add(aviatrix_grant1)
        
        # Aviatrix Grant 2 - 120,000 ISO (terminated, partially exercised)
        aviatrix_grant2 = EquityGrant(
            company_id=aviatrix.id,
            grant_id="E3-105",
            grant_type="ISO",
            grant_date=date(2018, 5, 17),
            total_options=120000,
            exercise_price=Decimal("1.00"),  # Placeholder
            vested_options=120000,
            exercised_options=80000,  # Approximate
            status="terminated",
            notes="Terminated, Partially Exercised, Expired",
        )
        db.add(aviatrix_grant2)
        
        # Aviatrix Grant 3 - 85,000 ISO (terminated, partially exercised)
        aviatrix_grant3 = EquityGrant(
            company_id=aviatrix.id,
            grant_id="E5-127",
            grant_type="ISO",
            grant_date=date(2019, 4, 25),
            total_options=85000,
            exercise_price=Decimal("1.50"),  # Placeholder
            vested_options=85000,
            exercised_options=52478,  # Remaining to match 232,478 total
            status="terminated",
            notes="Terminated, Partially Exercised, Expired",
        )
        db.add(aviatrix_grant3)
        
        # Aviatrix shares from exercises - 232,478 total
        aviatrix_shares = EquityShares(
            company_id=aviatrix.id,
            certificate_id="AVIATRIX-SHARES",
            share_type="common",
            num_shares=232478,
            source="exercise",
            status="held",
            notes="From exercised ISO options",
        )
        db.add(aviatrix_shares)
        print(f"  Added Aviatrix: 423,000 total options (232,478 exercised), 232,478 shares, FMV $3.75")
        
        # 4. NeurOps Inc.
        neurops = EquityCompany(
            name="NeurOps Inc.",
            status="active",
        )
        db.add(neurops)
        db.flush()
        
        # NeurOps shares - 25,000 (fully vested, canceled)
        neurops_shares = EquityShares(
            company_id=neurops.id,
            certificate_id="CS-1",
            share_type="common",
            acquisition_date=date(2019, 8, 15),
            num_shares=25000,
            source="grant",
            status="canceled",
            notes="Fully Vested, Canceled",
        )
        db.add(neurops_shares)
        print(f"  Added NeurOps Inc.: 25,000 shares (canceled)")
        
        db.commit()
        print("\n✅ Equity data seeded successfully!")
        
        # Print summary
        print("\nSummary:")
        companies = db.query(EquityCompany).all()
        for company in companies:
            print(f"\n{company.dba_name or company.name}:")
            
            grants = db.query(EquityGrant).filter(EquityGrant.company_id == company.id).all()
            for g in grants:
                print(f"  - {g.grant_type} Grant {g.grant_id}: {g.total_options:,} options, {g.vested_options:,} vested, {g.exercised_options:,} exercised")
            
            shares = db.query(EquityShares).filter(EquityShares.company_id == company.id).all()
            for s in shares:
                print(f"  - Shares {s.certificate_id}: {s.num_shares:,} {s.share_type} ({s.status})")
            
            rsas = db.query(EquityRSA).filter(EquityRSA.company_id == company.id).all()
            for r in rsas:
                print(f"  - RSA: {r.total_shares:,} shares, {r.vested_shares:,} vested")
            
            safes = db.query(EquitySAFE).filter(EquitySAFE.company_id == company.id).all()
            for sf in safes:
                print(f"  - SAFE {sf.safe_id}: ${sf.principal_amount:,.2f} ({sf.status})")
        
    except Exception as e:
        db.rollback()
        print(f"Error seeding data: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_equity_data()

















