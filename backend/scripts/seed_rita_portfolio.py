"""
Seed script: Rita Agrawal's mutual fund portfolio.

Run from backend directory:
    python scripts/seed_rita_portfolio.py
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.modules.india_investments.models import FatherMutualFundHolding


RITA_HOLDINGS = [
    {
        "investment_date": date(2010, 5, 26),
        "fund_name": "ICICI Pru Balanced Advantage Fund",
        "folio_number": "114583021-51",
        "initial_invested_amount": Decimal("1200000"),
        "amount_march_2025": Decimal("2513126"),
        "fund_category": "Hybrid - Balanced Advantage",
        "notes": "Tranches: 26/05/2010 4L, 14/10/2016 1L, 26/02/2018 5L, + 1 more tranche",
    },
    {
        "investment_date": date(2010, 9, 8),
        "fund_name": "ICICI Pru SIP",
        "folio_number": "11458302-51",
        "initial_invested_amount": Decimal("535500"),
        "amount_march_2025": Decimal("2235822"),
        "fund_category": "Equity",
        "notes": "Tranches: 08/09/2010 4,10,500, 16/10/2017 1,25,000",
    },
    {
        "investment_date": date(2013, 4, 30),
        "fund_name": "ICICI Pru Fund",
        "folio_number": "11458302-51",
        "initial_invested_amount": Decimal("150000"),
        "amount_march_2025": Decimal("741001"),
        "fund_category": "Equity",
        "notes": "Tranches: 30/04/2013 50K, 27/05/2013 1L",
    },
    {
        "investment_date": date(2010, 9, 8),
        "fund_name": "ABSL SIP",
        "folio_number": "101-5590752",
        "initial_invested_amount": Decimal("611000"),
        "amount_march_2025": Decimal("1734443"),
        "fund_category": "Equity",
        "notes": "Tranches: 08/09/2010 3,36,000, 27/05/2013 2,75,000",
    },
    {
        "investment_date": date(2017, 9, 12),
        "fund_name": "Tata Fund",
        "folio_number": "3802553-26",
        "initial_invested_amount": Decimal("460000"),
        "amount_march_2025": Decimal("902024"),
        "fund_category": "Equity",
        "notes": "Single tranche: 12/09/2017 4,60,000",
    },
    {
        "investment_date": date(2016, 3, 22),
        "fund_name": "Franklin Blue Chip SIP",
        "folio_number": "19884653",
        "initial_invested_amount": Decimal("436000"),
        "amount_march_2025": Decimal("836060"),
        "fund_category": "Equity - Large Cap",
        "notes": "Single tranche: 22/03/2016 4,36,000",
    },
    {
        "investment_date": date(2021, 3, 18),
        "fund_name": "DSP Tax Saver Fund",
        "folio_number": "4155312-19",
        "initial_invested_amount": Decimal("200000"),
        "amount_march_2025": Decimal("367447"),
        "fund_category": "Equity - ELSS",
        "notes": "Tranches: 18/03/2021 1L, 17/03/2022 1L",
    },
    {
        "investment_date": date(2025, 2, 5),
        "fund_name": "DSP Tiger Fund",
        "folio_number": "4155312-19",
        "initial_invested_amount": Decimal("500000"),
        "amount_march_2025": Decimal("521250"),
        "fund_category": "Equity - Thematic",
        "notes": "Single tranche: 05/02/2025 5L",
    },
    {
        "investment_date": date(2019, 1, 30),
        "fund_name": "Edelweiss Small Cap Fund",
        "folio_number": "9102821116",
        "initial_invested_amount": Decimal("50000"),
        "amount_march_2025": Decimal("194230"),
        "fund_category": "Equity - Small Cap",
        "notes": "Single tranche: 30/01/2019 50K",
    },
    {
        "investment_date": date(2022, 1, 8),
        "fund_name": "Edelweiss Focused Equity Fund",
        "folio_number": "9102821116",
        "initial_invested_amount": Decimal("300000"),
        "amount_march_2025": Decimal("411985"),
        "fund_category": "Equity - Focused",
        "notes": "Tranches: 08/01/2022 2L, 04/07/2024 1L",
    },
    {
        "investment_date": date(2024, 2, 28),
        "fund_name": "Edelweiss Technology Fund",
        "folio_number": "9102821116",
        "initial_invested_amount": Decimal("100000"),
        "amount_march_2025": Decimal("103288"),
        "fund_category": "Equity - Sectoral (Technology)",
        "notes": "Single tranche: 28/02/2024 1L",
    },
    {
        "investment_date": date(2025, 5, 2),
        "fund_name": "Edelweiss Consumption Fund",
        "folio_number": "9102821116",
        "initial_invested_amount": Decimal("300000"),
        "amount_march_2025": Decimal("305369"),
        "fund_category": "Equity - Thematic (Consumption)",
        "notes": "Single tranche: 02/05/2025 3L. Invested after Mar 2025.",
    },
    {
        "investment_date": date(2019, 3, 1),
        "fund_name": "DSP Low Duration Fund",
        "folio_number": "567396456",
        "initial_invested_amount": Decimal("1700000"),
        "amount_march_2025": Decimal("2665155"),
        "fund_category": "Debt - Low Duration",
        "notes": "Tranches: 01/03/2019 5L, 12/01/2021 6L, 11/01/2022 3L, 21/07/2022 1L, 07/04/2024 2L",
    },
    {
        "investment_date": date(2025, 2, 5),
        "fund_name": "DSP MultiCap Fund",
        "folio_number": "567396456",
        "initial_invested_amount": Decimal("200000"),
        "amount_march_2025": Decimal("201553"),
        "fund_category": "Equity - Multi Cap",
        "notes": "Single tranche: 05/02/2025 2L",
    },
    {
        "investment_date": date(2022, 7, 27),
        "fund_name": "Nippon India Large Cap Fund",
        "folio_number": "429267504652",
        "initial_invested_amount": Decimal("500000"),
        "amount_march_2025": Decimal("637458"),
        "fund_category": "Equity - Large Cap",
        "notes": "Tranches: 27/07/2022 2L, 07/04/2024 2L, 07/04/2024 1L",
    },
    {
        "investment_date": date(2024, 2, 27),
        "fund_name": "SBI Energy Opportunity Fund",
        "folio_number": "37148392",
        "initial_invested_amount": Decimal("200000"),
        "amount_march_2025": Decimal("190206"),
        "fund_category": "Equity - Sectoral (Energy)",
        "notes": "Tranches: 27/02/2024 1L, 07/04/2025 1L",
    },
    {
        "investment_date": date(2024, 4, 16),
        "fund_name": "PGIM India Fund",
        "folio_number": "91021583263",
        "initial_invested_amount": Decimal("200000"),
        "amount_march_2025": Decimal("216957"),
        "fund_category": "Equity",
        "notes": "Single tranche: 16/04/2024 2L",
    },
    {
        "investment_date": date(2024, 4, 23),
        "fund_name": "Bank of India Fund",
        "folio_number": "9108141462",
        "initial_invested_amount": Decimal("100000"),
        "amount_march_2025": Decimal("101956"),
        "fund_category": "Equity",
        "notes": "Single tranche: 23/04/2024 1L",
    },
    {
        "investment_date": date(2011, 2, 24),
        "fund_name": "UTI ULIP",
        "folio_number": "580253436203",
        "initial_invested_amount": Decimal("140000"),
        "amount_march_2025": Decimal("248560"),
        "fund_category": "Insurance - ULIP",
        "notes": "Single tranche: 24/02/2011 1,40,000",
    },
    {
        "investment_date": date(2012, 3, 26),
        "fund_name": "UTI Large Cap and Mid Cap Fund",
        "folio_number": None,
        "initial_invested_amount": Decimal("50000"),
        "amount_march_2025": Decimal("146624"),
        "fund_category": "Equity - Large & Mid Cap",
    },
    {
        "investment_date": date(2017, 8, 23),
        "fund_name": "UTI Large Cap Fund",
        "folio_number": None,
        "initial_invested_amount": Decimal("300000"),
        "amount_march_2025": Decimal("623334"),
        "fund_category": "Equity - Large Cap",
    },
    {
        "investment_date": date(2024, 5, 10),
        "fund_name": "UTI Multi-Asset Fund",
        "folio_number": None,
        "initial_invested_amount": Decimal("200000"),
        "amount_march_2025": Decimal("209526"),
        "fund_category": "Hybrid - Multi Asset",
    },
    {
        "investment_date": date(2024, 5, 13),
        "fund_name": "ICICI Pru Opportunities Fund",
        "folio_number": None,
        "initial_invested_amount": Decimal("200000"),
        "amount_march_2025": Decimal("213336"),
        "fund_category": "Equity - Thematic",
    },
    {
        "investment_date": date(2024, 5, 13),
        "fund_name": "HDFC Manufacturing Fund",
        "folio_number": None,
        "initial_invested_amount": Decimal("100000"),
        "amount_march_2025": Decimal("93345"),
        "fund_category": "Equity - Sectoral (Manufacturing)",
    },
    {
        "investment_date": date(2022, 8, 6),
        "fund_name": "Mahindra Manulife Fund",
        "folio_number": None,
        "initial_invested_amount": Decimal("1100000"),
        "amount_march_2025": Decimal("1201228"),
        "fund_category": "Equity",
    },
    {
        "investment_date": date(2022, 8, 6),
        "fund_name": "Quant Flexi Cap Fund",
        "folio_number": None,
        "initial_invested_amount": Decimal("500000"),
        "amount_march_2025": Decimal("732197"),
        "fund_category": "Equity - Flexi Cap",
    },
    {
        "investment_date": date(2022, 8, 6),
        "fund_name": "Kotak Contra Fund",
        "folio_number": None,
        "initial_invested_amount": Decimal("500000"),
        "amount_march_2025": Decimal("803689"),
        "fund_category": "Equity - Contra",
    },
    {
        "investment_date": date(2022, 8, 6),
        "fund_name": "JM Focused Fund",
        "folio_number": None,
        "initial_invested_amount": Decimal("900000"),
        "amount_march_2025": Decimal("990637"),
        "fund_category": "Equity - Focused",
    },
    {
        "investment_date": date(2008, 1, 30),
        "fund_name": "PPF",
        "folio_number": None,
        "initial_invested_amount": Decimal("1060000"),
        "amount_march_2025": Decimal("1596965"),
        "fund_category": "Government Scheme",
        "notes": "Public Provident Fund - guaranteed returns",
    },
    {
        "investment_date": date(2010, 8, 21),
        "fund_name": "Sahara Fund (1)",
        "folio_number": None,
        "initial_invested_amount": Decimal("117000"),
        "amount_march_2025": None,
        "fund_category": "Equity",
        "notes": "Valuation not available",
    },
    {
        "investment_date": date(2017, 11, 15),
        "fund_name": "Sahara Fund (2)",
        "folio_number": None,
        "initial_invested_amount": Decimal("100000"),
        "amount_march_2025": None,
        "fund_category": "Equity",
        "notes": "Valuation not available",
    },
    {
        "investment_date": date(2025, 5, 14),
        "fund_name": "SCSS (Senior Citizen Savings Scheme)",
        "folio_number": None,
        "initial_invested_amount": Decimal("1500000"),
        "amount_march_2025": None,
        "fund_category": "Government Scheme",
        "notes": "Pays 30,000 every quarter. Invested after Mar 2025.",
    },
    {
        "investment_date": date(2025, 7, 29),
        "fund_name": "HSBC Large and Mid-Cap SIP",
        "folio_number": None,
        "initial_invested_amount": Decimal("104000"),
        "amount_march_2025": None,
        "fund_category": "Equity - Large & Mid Cap",
        "notes": "Ongoing monthly SIP of 13K/month from Jul 2025. Tranches: 29/07-29/12/2025 (6x13K), 29/01/2026 13K, 29/02/2026 13K = 1,04,000 total",
    },
]


def main():
    db: Session = SessionLocal()
    try:
        # Check for existing Mother holdings
        existing = db.query(FatherMutualFundHolding).filter(
            FatherMutualFundHolding.owner == 'Mother'
        ).count()

        if existing > 0:
            print(f"Found {existing} existing Mother holdings. Skipping seed to avoid duplicates.")
            print("To re-seed, first delete existing Mother holdings:")
            print("  DELETE FROM father_mutual_fund_holdings WHERE owner = 'Mother';")
            return

        added = 0
        for h in RITA_HOLDINGS:
            holding = FatherMutualFundHolding(
                owner='Mother',
                investment_date=h["investment_date"],
                fund_name=h["fund_name"],
                folio_number=h.get("folio_number"),
                initial_invested_amount=h["initial_invested_amount"],
                amount_march_2025=h.get("amount_march_2025"),
                fund_category=h.get("fund_category"),
                notes=h.get("notes"),
            )
            db.add(holding)
            added += 1
            print(f"  + {h['fund_name']}: {h['initial_invested_amount']}")

        db.commit()

        # Print summary
        total_invested = sum(float(h["initial_invested_amount"]) for h in RITA_HOLDINGS)
        total_march = sum(
            float(h["amount_march_2025"])
            for h in RITA_HOLDINGS
            if h.get("amount_march_2025")
        )

        print(f"\nSeeded {added} holdings for Rita Agrawal (Mother)")
        print(f"Total invested: {total_invested:,.0f}")
        print(f"Total Mar 2025 valuation: {total_march:,.0f}")
        print(f"Gain: {total_march - total_invested:,.0f}")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
