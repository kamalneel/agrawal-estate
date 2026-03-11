"""
Batch update mutual fund research metrics (Alpha, Beta, Sharpe, AUM, Expense Ratio, Volatility).
Data sourced from Groww.in and Tickertape.in as of March 2026.

Usage: python -m scripts.update_mf_metrics
Run from the backend directory.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.modules.india_investments.mf_research_models import MutualFundResearch


# Data sourced from Groww.in (primary - has Beta) and Tickertape.in (supplementary)
# All metrics are 3-year trailing as of March 2026
FUND_METRICS = [
    {
        "scheme_code": "105758",
        "name": "HDFC Mid Cap Opportunities Fund - Growth Plan (Regular)",
        "sharpe_ratio": 0.89,       # Tickertape (Regular plan)
        "alpha": 5.20,              # Groww (Direct, closest proxy)
        "beta": 0.85,               # Groww (Direct)
        "aum": 94256.90,            # Tickertape (in crores)
        "expense_ratio": 1.36,      # Tickertape (Regular plan)
        "volatility": 13.02,        # Tickertape
    },
    {
        "scheme_code": "118419",
        "name": "Bandhan Large & Mid Cap Fund - Direct Plan Growth",
        "sharpe_ratio": 1.34,       # Groww
        "alpha": 6.70,              # Groww
        "beta": 1.02,               # Groww
        "aum": 14780.40,            # Tickertape
        "expense_ratio": 0.53,      # Tickertape
        "volatility": 13.22,        # Groww
    },
    {
        "scheme_code": "120492",
        "name": "JM Flexicap Fund (Direct) - Growth Option",
        "sharpe_ratio": 1.02,       # Groww
        "alpha": 3.34,              # Groww
        "beta": 1.05,               # Groww
        "aum": 5158.73,             # Tickertape
        "expense_ratio": 0.62,      # Tickertape (Direct)
        "volatility": 14.75,        # Groww
    },
    {
        "scheme_code": "145552",
        "name": "Motilal Oswal Nasdaq 100 FoF - Direct Plan Growth",
        "sharpe_ratio": 1.11,       # Groww
        "alpha": 4.60,              # Tickertape
        "beta": None,               # Groww shows 0 (tracks ETF, not equity benchmark)
        "aum": 5881.85,             # Tickertape
        "expense_ratio": 0.22,      # Tickertape
        "volatility": 20.14,        # Tickertape
    },
    {
        "scheme_code": "140296",
        "name": "Edelweiss Europe Dynamic Equity Offshore Fund - Direct",
        "sharpe_ratio": 1.28,       # Groww
        "alpha": None,              # Not available (international, no domestic benchmark)
        "beta": None,               # Not available (international fund)
        "aum": 224.86,              # Tickertape
        "expense_ratio": 1.49,      # Tickertape
        "volatility": 16.58,        # Tickertape
    },
    {
        "scheme_code": "118989",
        "name": "HDFC Mid Cap Growth Direct Plan",
        # Note: This is the same fund as HDFC Mid Cap Opportunities Fund Direct Plan
        "sharpe_ratio": 1.41,       # Groww
        "alpha": 5.20,              # Groww
        "beta": 0.85,               # Groww
        "aum": 94256.90,            # Tickertape (shared AUM with regular)
        "expense_ratio": 0.74,      # Tickertape (Direct)
        "volatility": 13.69,        # Groww
    },
    {
        "scheme_code": "140225",
        "name": "Edelweiss Mid Cap Fund - Regular Plan Growth",
        # Using Direct plan metrics as proxy (Regular plan has similar risk profile)
        "sharpe_ratio": 1.31,       # Groww (Direct)
        "alpha": 4.64,              # Groww (Direct)
        "beta": 0.93,               # Groww (Direct)
        "aum": 13801.71,            # Tickertape
        "expense_ratio": 1.80,      # Estimated Regular plan (Direct is 0.42)
        "volatility": 15.34,        # Groww
    },
    {
        "scheme_code": "147701",
        "name": "Motilal Oswal Large and Midcap Fund - Regular Growth",
        "sharpe_ratio": 0.93,       # Groww (Regular)
        "alpha": 4.32,              # Groww (Regular)
        "beta": 1.21,               # Groww (Regular)
        "aum": 15017.31,            # Groww
        "expense_ratio": 1.69,      # Groww (Regular)
        "volatility": 18.77,        # Groww
    },
    {
        "scheme_code": "118777",
        "name": "Nippon India Small Cap Bonus Growth Direct Plan",
        # Using Direct Growth metrics (Bonus variant shares same portfolio)
        "sharpe_ratio": 0.93,       # Groww
        "alpha": 3.50,              # Groww
        "beta": 0.85,               # Groww
        "aum": 67641.50,            # Tickertape
        "expense_ratio": 0.66,      # Tickertape
        "volatility": 16.75,        # Groww
    },
    {
        "scheme_code": "119835",
        "name": "SBI Contra Growth Direct Plan",
        "sharpe_ratio": 1.17,       # Groww
        "alpha": 3.83,              # Groww
        "beta": 0.93,               # Groww
        "aum": 49111.50,            # Tickertape
        "expense_ratio": 0.71,      # Tickertape
        "volatility": 12.07,        # Groww
    },
    {
        "scheme_code": "100363",
        "name": "ICICI Prudential Technology Fund - Growth (Regular)",
        # Using Direct plan risk metrics as proxy
        "sharpe_ratio": -0.78,      # Tickertape (Regular)
        "alpha": 5.79,              # Groww (Direct, closest proxy)
        "beta": 0.83,               # Groww (Direct)
        "aum": 13572.40,            # Tickertape
        "expense_ratio": 1.01,      # Tickertape (Regular)
        "volatility": 16.66,        # Tickertape
    },
    {
        "scheme_code": "120505",
        "name": "Axis Mid Cap Growth Direct Plan",
        "sharpe_ratio": 1.04,       # Groww
        "alpha": 0.84,              # Groww
        "beta": 0.83,               # Groww
        "aum": 31977.12,            # Tickertape
        "expense_ratio": 0.57,      # Tickertape
        "volatility": 14.14,        # Groww
    },
    {
        "scheme_code": "120164",
        "name": "Kotak Small Cap Growth Direct Plan",
        "sharpe_ratio": 0.63,       # Groww
        "alpha": -1.31,             # Groww
        "beta": 0.85,               # Groww
        "aum": 16367.84,            # Tickertape
        "expense_ratio": 0.55,      # Tickertape
        "volatility": 17.12,        # Groww
    },
    {
        "scheme_code": "120594",
        "name": "ICICI Prudential Technology Growth Direct Plan",
        "sharpe_ratio": 0.26,       # Groww
        "alpha": 5.79,              # Groww
        "beta": 0.83,               # Groww
        "aum": 13572.40,            # Tickertape (shared with Regular)
        "expense_ratio": 0.48,      # Estimated Direct plan
        "volatility": 18.53,        # Groww
    },
    {
        "scheme_code": "120377",
        "name": "ICICI Pru Balanced Advantage Growth Direct Plan",
        "sharpe_ratio": 1.39,       # Groww
        "alpha": None,              # Groww shows 0 (hybrid fund, benchmark mismatch)
        "beta": None,               # Groww shows 0 (hybrid fund)
        "aum": 71150.75,            # Tickertape
        "expense_ratio": 0.86,      # Tickertape
        "volatility": 5.44,         # Groww
    },
    {
        "scheme_code": "INF846K01D",
        "name": "Axis Large Cap Growth Direct Plan",
        "sharpe_ratio": 0.72,       # Groww
        "alpha": -0.77,             # Groww
        "beta": 0.90,               # Groww
        "aum": 32436.77,            # Tickertape
        "expense_ratio": 0.72,      # Tickertape
        "volatility": 11.05,        # Groww
    },
]


def update_fund_metrics():
    """Update all fund metrics in the database."""
    db = SessionLocal()
    try:
        updated = 0
        not_found = []

        for fund_data in FUND_METRICS:
            scheme_code = fund_data["scheme_code"]
            fund = db.query(MutualFundResearch).filter(
                MutualFundResearch.scheme_code == scheme_code
            ).first()

            if not fund:
                not_found.append(f"{scheme_code}: {fund_data['name']}")
                continue

            # Update metrics
            if fund_data.get("sharpe_ratio") is not None:
                fund.sharpe_ratio = Decimal(str(fund_data["sharpe_ratio"]))
            if fund_data.get("alpha") is not None:
                fund.alpha = Decimal(str(fund_data["alpha"]))
            if fund_data.get("beta") is not None:
                fund.beta = Decimal(str(fund_data["beta"]))
            if fund_data.get("aum") is not None:
                fund.aum = Decimal(str(fund_data["aum"]))
            if fund_data.get("expense_ratio") is not None:
                fund.expense_ratio = Decimal(str(fund_data["expense_ratio"]))
            if fund_data.get("volatility") is not None:
                fund.volatility = Decimal(str(fund_data["volatility"]))

            fund.last_updated = datetime.utcnow()
            updated += 1
            print(f"  Updated: {fund.scheme_name} ({scheme_code})")

        db.commit()
        print(f"\nTotal updated: {updated}")

        if not_found:
            print(f"\nNot found in DB ({len(not_found)}):")
            for nf in not_found:
                print(f"  - {nf}")

    finally:
        db.close()


if __name__ == "__main__":
    print("Updating mutual fund research metrics...")
    print("=" * 60)
    update_fund_metrics()
    print("\nDone.")
