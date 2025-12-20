#!/usr/bin/env python3
"""
Compare 2024 Actual AGI vs 2025 Forecast AGI
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.modules.tax.forecast import calculate_tax_forecast, _get_forecast_income
from app.modules.tax.models import IncomeTaxReturn

# 2024 Actual AGI Components (from tax return PDF)
agi_2024_components = {
    "W-2 Wages": 322220,
    "Taxable Interest": 10893,
    "Qualified Dividends": 2837,
    "Ordinary Dividends": 2889,
    "Total Dividends": 2837 + 2889,  # 5,726
    "Capital Gains": 129982,
    "Additional Income (Schedule 1)": 23998,  # Likely includes rental income
    "Total AGI": 489982
}

def main():
    db = SessionLocal()
    try:
        # Get 2025 forecast
        print("Calculating 2025 forecast...")
        forecast_income = _get_forecast_income(db, 2025)
        forecast = calculate_tax_forecast(db, forecast_year=2025, base_year=2024)
        
        # Map forecast income to AGI components
        agi_2025_components = {
            "W-2 Wages": forecast_income["w2_income"].get("total_wages", 0),
            "Taxable Interest": forecast_income.get("interest_income", 0),
        }
        
        # Combine qualified and ordinary dividends
        total_dividends = forecast_income.get("dividend_income", 0)
        agi_2025_components["Total Dividends"] = total_dividends
        
        # Options income (treated as capital gains/ordinary income)
        options_income = forecast_income.get("options_income", 0)
        
        # Rental income (net after expenses/depreciation)
        rental_income = forecast_income.get("rental_income", 0)
        
        # For 2025, we'll combine rental + options as "Other Income"
        # (similar to Schedule 1 additional income in 2024)
        agi_2025_components["Other Income (Rental + Options)"] = rental_income + options_income
        
        # Capital gains - we don't have this in forecast yet, assume 0 or same as 2024
        agi_2025_components["Capital Gains"] = 0  # Not forecasted yet
        
        agi_2025_components["Total AGI"] = forecast.get("agi", 0)
        
        # Print comparison table
        print()
        print("=" * 100)
        print("2024 ACTUAL vs 2025 FORECAST - AGI COMPONENTS COMPARISON")
        print("=" * 100)
        print()
        print(f"{'Income Source':<40} {'2024 Actual':>15} {'2025 Forecast':>15} {'Delta':>15} {'% Change':>12}")
        print("-" * 100)
        
        # Compare W-2 Wages
        w2_2024 = agi_2024_components["W-2 Wages"]
        w2_2025 = agi_2025_components["W-2 Wages"]
        delta_w2 = w2_2025 - w2_2024
        pct_w2 = (delta_w2 / w2_2024 * 100) if w2_2024 > 0 else 0
        print(f"{'W-2 Wages':<40} ${w2_2024:>14,.0f} ${w2_2025:>14,.0f} ${delta_w2:>14,.0f} {pct_w2:>11.1f}%")
        
        # Compare Interest
        int_2024 = agi_2024_components["Taxable Interest"]
        int_2025 = agi_2025_components["Taxable Interest"]
        delta_int = int_2025 - int_2024
        pct_int = (delta_int / int_2024 * 100) if int_2024 > 0 else 0
        print(f"{'Taxable Interest':<40} ${int_2024:>14,.0f} ${int_2025:>14,.0f} ${delta_int:>14,.0f} {pct_int:>11.1f}%")
        
        # Compare Dividends
        div_2024 = agi_2024_components["Total Dividends"]
        div_2025 = agi_2025_components["Total Dividends"]
        delta_div = div_2025 - div_2024
        pct_div = (delta_div / div_2024 * 100) if div_2024 > 0 else 0
        print(f"{'Dividends (Total)':<40} ${div_2024:>14,.0f} ${div_2025:>14,.0f} ${delta_div:>14,.0f} {pct_div:>11.1f}%")
        
        # Compare Capital Gains
        cg_2024 = agi_2024_components["Capital Gains"]
        cg_2025 = agi_2025_components["Capital Gains"]
        delta_cg = cg_2025 - cg_2024
        pct_cg = (delta_cg / cg_2024 * 100) if cg_2024 > 0 else 0
        print(f"{'Capital Gains':<40} ${cg_2024:>14,.0f} ${cg_2025:>14,.0f} ${delta_cg:>14,.0f} {pct_cg:>11.1f}%")
        
        # Compare Other Income (Schedule 1 in 2024 vs Rental+Options in 2025)
        other_2024 = agi_2024_components["Additional Income (Schedule 1)"]
        other_2025 = agi_2025_components["Other Income (Rental + Options)"]
        delta_other = other_2025 - other_2024
        pct_other = (delta_other / other_2024 * 100) if other_2024 > 0 else 0
        print(f"{'Other Income (Schedule 1/Rental+Options)':<40} ${other_2024:>14,.0f} ${other_2025:>14,.0f} ${delta_other:>14,.0f} {pct_other:>11.1f}%")
        
        print("-" * 100)
        
        # Total AGI
        agi_2024_total = agi_2024_components["Total AGI"]
        agi_2025_total = agi_2025_components["Total AGI"]
        delta_total = agi_2025_total - agi_2024_total
        pct_total = (delta_total / agi_2024_total * 100) if agi_2024_total > 0 else 0
        print(f"{'TOTAL AGI':<40} ${agi_2024_total:>14,.0f} ${agi_2025_total:>14,.0f} ${delta_total:>14,.0f} {pct_total:>11.1f}%")
        
        print()
        print("=" * 100)
        print("KEY INSIGHTS:")
        print("=" * 100)
        print(f"• W-2 Income Change: ${delta_w2:,.0f} ({pct_w2:+.1f}%)")
        print(f"• Investment Income Change: ${delta_div + delta_int:,.0f}")
        print(f"• Other Income Change: ${delta_other:,.0f} ({pct_other:+.1f}%)")
        print(f"• Overall AGI Change: ${delta_total:,.0f} ({pct_total:+.1f}%)")
        print()
        
        # Show breakdown of 2025 components
        print("2025 Forecast Breakdown:")
        print(f"  - Jaya's W-2: ${forecast_income['w2_income'].get('total_wages', 0):,.0f}")
        print(f"  - Neel's W-2: $0 (as specified)")
        print(f"  - Options Income: ${options_income:,.0f}")
        print(f"  - Dividend Income: ${total_dividends:,.0f}")
        print(f"  - Interest Income: ${int_2025:,.0f}")
        print(f"  - Rental Income (net): ${rental_income:,.0f}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()


