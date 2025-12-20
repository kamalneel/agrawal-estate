"""
Script to add 13 mutual funds and update their data.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import Session
from decimal import Decimal
from app.core.database import SessionLocal
from app.modules.india_investments.mf_research_models import MutualFundResearch
from app.modules.india_investments.mf_research_service import fetch_and_store_fund_data
from app.modules.india_investments.mf_recommendation_engine import calculate_all_scores_and_rank

# Fund data from user
FUNDS_DATA = [
    {
        "name": "Mirae NYSE FANG+ FoF Direct",
        "scheme_code": "148928",  # Direct plan
        "category": "US Tech",
        "aum": 2463,
        "expense_ratio": 0.07,
        "return_1y": 54.2,
        "return_3y": None,
        "return_5y": None,
        "beta": None,
        "alpha": None,
        "vr_rating": None,
    },
    {
        "name": "Edelweiss US Tech FoF Direct",
        "scheme_code": "148063",  # Edelweiss US Technology Equity Fund of Fund- Direct Plan- Growth
        "category": "US Tech",
        "aum": 3600,
        "expense_ratio": 0.73,
        "return_1y": 30.0,
        "return_3y": 36.4,
        "return_5y": 15.1,
        "beta": None,
        "alpha": None,
        "vr_rating": 3,
    },
    {
        "name": "Motilal Oswal Nasdaq 100 FoF",
        "scheme_code": None,  # Need to search
        "category": "US Broad",
        "aum": 3883,
        "expense_ratio": 0.30,
        "return_1y": 26.6,
        "return_3y": 33.6,
        "return_5y": None,
        "beta": None,
        "alpha": None,
        "vr_rating": 4,
    },
    {
        "name": "Franklin US Opportunities FoF",
        "scheme_code": None,  # Not found in API - may need manual entry
        "category": "US Broad",
        "aum": 2500,
        "expense_ratio": 0.85,
        "return_1y": 18.0,
        "return_3y": 24.4,
        "return_5y": 11.7,
        "beta": None,
        "alpha": None,
        "vr_rating": 3,
    },
    {
        "name": "Quant Flexi Cap Direct",
        "scheme_code": "120843",  # Direct plan
        "category": "Flexi-Cap",
        "aum": 6890,
        "expense_ratio": 0.68,
        "return_1y": -2.5,
        "return_3y": 16.6,
        "return_5y": 27.3,
        "beta": 1.06,
        "alpha": 11.08,
        "vr_rating": 4,
    },
    {
        "name": "Parag Parikh Flexi Cap Direct",
        "scheme_code": "122639",  # Direct plan
        "category": "Flexi-Cap",
        "aum": 129783,
        "expense_ratio": 0.63,
        "return_1y": 8.0,
        "return_3y": 21.5,
        "return_5y": 21.2,
        "beta": None,
        "alpha": -7.11,
        "vr_rating": 5,
    },
    {
        "name": "HDFC Flexi Cap Direct",
        "scheme_code": "118955",  # Direct plan
        "category": "Flexi-Cap",
        "aum": 85560,
        "expense_ratio": 0.70,
        "return_1y": 9.0,
        "return_3y": 22.1,
        "return_5y": 28.4,
        "beta": None,
        "alpha": -3.82,
        "vr_rating": 5,
    },
    {
        "name": "JM Flexicap Direct",
        "scheme_code": None,  # Need to search
        "category": "Flexi-Cap",
        "aum": 5990,
        "expense_ratio": 0.50,
        "return_1y": -6.0,
        "return_3y": 22.1,
        "return_5y": 25.6,
        "beta": None,
        "alpha": None,
        "vr_rating": 4,
    },
    {
        "name": "ICICI Pru US Bluechip Direct",
        "scheme_code": "120186",  # ICICI Prudential US Bluechip Equity Fund - Direct Plan - Growth
        "category": "US Broad",
        "aum": 3357,
        "expense_ratio": 2.00,
        "return_1y": 13.2,
        "return_3y": 18.9,
        "return_5y": 14.5,
        "beta": None,
        "alpha": None,
        "vr_rating": 3,
    },
    {
        "name": "Nippon US Equity Opp Direct",
        "scheme_code": "134923",  # Nippon India US Equity Opportunities Fund- Direct Plan- Growth Plan- Growth Option
        "category": "US Broad",
        "aum": 2800,
        "expense_ratio": 1.80,
        "return_1y": 15.0,
        "return_3y": 20.0,
        "return_5y": 16.0,
        "beta": None,
        "alpha": None,
        "vr_rating": 3,
    },
    {
        "name": "Axis Global Innovation FoF",
        "scheme_code": None,  # Need to search
        "category": "Global",
        "aum": 2100,
        "expense_ratio": 0.95,
        "return_1y": 22.0,
        "return_3y": 28.0,
        "return_5y": None,
        "beta": None,
        "alpha": None,
        "vr_rating": 4,
    },
    {
        "name": "Edelweiss Europe Dynamic",
        "scheme_code": None,  # Need to search
        "category": "Europe",
        "aum": 1500,
        "expense_ratio": 0.90,
        "return_1y": 18.5,
        "return_3y": 22.8,
        "return_5y": 16.4,
        "beta": None,
        "alpha": None,
        "vr_rating": 3,
    },
    {
        "name": "Bandhan Large & Mid Cap Direct",
        "scheme_code": None,  # Need to search
        "category": "Large+Mid",
        "aum": 1828,
        "expense_ratio": 0.85,
        "return_1y": 8.5,
        "return_3y": 23.8,
        "return_5y": 23.8,
        "beta": None,
        "alpha": None,
        "vr_rating": None,
    },
]

def search_fund(name: str):
    """Search for a fund and return scheme code."""
    import requests
    try:
        # Try different search queries
        queries = [
            name,
            name.replace(" Direct", ""),
            name.replace(" FoF", ""),
            name.replace(" Fund", ""),
            name.replace(" Opportunities", ""),
        ]
        for query in queries:
            response = requests.get(f"https://api.mfapi.in/mf/search", params={"q": query}, timeout=10)
            if response.ok:
                results = response.json()
                if not results:
                    continue
                # Look for Direct plan with Growth
                for result in results:
                    scheme_name = result.get("schemeName", "")
                    if "Direct" in scheme_name and "Growth" in scheme_name:
                        return result.get("schemeCode")
                # If no Direct found, look for any with Growth
                for result in results:
                    if "Growth" in result.get("schemeName", ""):
                        return result.get("schemeCode")
                # If still nothing, take first result
                if results:
                    return results[0].get("schemeCode")
    except Exception as e:
        print(f"Error searching for {name}: {e}")
    return None

def main():
    db: Session = SessionLocal()
    try:
        # First, deactivate all existing funds
        print("Deactivating existing funds...")
        existing_funds = db.query(MutualFundResearch).filter(MutualFundResearch.is_active == 'Y').all()
        for fund in existing_funds:
            fund.is_active = 'N'
        db.commit()
        print(f"Deactivated {len(existing_funds)} existing funds")
        
        # Add new funds
        added = 0
        for fund_data in FUNDS_DATA:
            scheme_code = fund_data["scheme_code"]
            if not scheme_code:
                print(f"Searching for {fund_data['name']}...")
                scheme_code = search_fund(fund_data["name"])
                if not scheme_code:
                    print(f"  ❌ Could not find scheme code for {fund_data['name']}")
                    continue
                print(f"  ✓ Found scheme code: {scheme_code}")
            
            # Add fund
            print(f"Adding {fund_data['name']} (scheme_code: {scheme_code})...")
            try:
                # If scheme_code is None, create fund manually
                if not scheme_code:
                    print(f"  ⚠️  No scheme code found - creating fund manually...")
                    fund = MutualFundResearch(
                        scheme_code=f"MANUAL_{fund_data['name'].replace(' ', '_')[:50]}",
                        scheme_name=fund_data['name'],
                        fund_category=fund_data['category'],
                        is_active='Y',
                    )
                    db.add(fund)
                    db.flush()
                    result = {"id": fund.id, "scheme_code": fund.scheme_code}
                else:
                    result = fetch_and_store_fund_data(db, scheme_code_str)
                    if not result:
                        print(f"  ❌ Failed to fetch data for {fund_data['name']}")
                        continue
                
                # Update manual fields
                scheme_code_str = str(scheme_code) if scheme_code else None
                if not scheme_code_str or scheme_code_str.startswith("MANUAL_"):
                    # For manually created funds, find by name
                    fund = db.query(MutualFundResearch).filter(
                        MutualFundResearch.scheme_name == fund_data['name']
                    ).first()
                else:
                    fund = db.query(MutualFundResearch).filter(
                        MutualFundResearch.scheme_code == scheme_code_str
                    ).first()
                
                if fund:
                    fund.aum = Decimal(str(fund_data["aum"])) if fund_data["aum"] else None
                    fund.expense_ratio = Decimal(str(fund_data["expense_ratio"])) if fund_data["expense_ratio"] else None
                    fund.beta = Decimal(str(fund_data["beta"])) if fund_data["beta"] else None
                    fund.alpha = Decimal(str(fund_data["alpha"])) if fund_data["alpha"] else None
                    fund.value_research_rating = fund_data["vr_rating"] if fund_data["vr_rating"] else None
                    fund.fund_category = fund_data["category"]
                    
                    # Override returns if provided (user data takes precedence)
                    if fund_data.get("return_1y") is not None:
                        fund.return_1y = Decimal(str(fund_data["return_1y"]))
                    if fund_data.get("return_3y") is not None:
                        fund.return_3y = Decimal(str(fund_data["return_3y"]))
                    if fund_data.get("return_5y") is not None:
                        fund.return_5y = Decimal(str(fund_data["return_5y"]))
                    
                    db.commit()
                    print(f"  ✓ Added and updated {fund_data['name']}")
                    added += 1
                else:
                    print(f"  ❌ Fund not found after adding")
            except Exception as e:
                print(f"  ❌ Error adding {fund_data['name']}: {e}")
                db.rollback()
        
        # Recalculate scores
        print("\nRecalculating recommendation scores...")
        calculate_all_scores_and_rank(db)
        print(f"\n✓ Successfully added {added} funds")
        
    finally:
        db.close()

if __name__ == "__main__":
    main()

