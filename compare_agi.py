#!/usr/bin/env python3
"""
Compare 2024 Actual AGI vs 2025 Forecast AGI
"""

# 2024 Actual AGI Components (from tax return PDF)
agi_2024 = {
    "W-2 Wages": 322220,
    "Taxable Interest": 10893,
    "Qualified Dividends": 2837,
    "Ordinary Dividends": 2889,
    "Capital Gains": 129982,
    "Additional Income (Schedule 1)": 23998,
    "Total AGI": 489982
}

# Note: The forecast will be calculated from actual 2025 income data
# This script will help format the comparison once we have the forecast

print("=" * 80)
print("2024 vs 2025 AGI COMPARISON")
print("=" * 80)
print()
print(f"{'Income Source':<35} {'2024 Actual':>15} {'2025 Forecast':>15} {'Delta':>15} {'% Change':>10}")
print("-" * 90)

# We'll populate this from the forecast API
# For now, showing 2024 structure
for source, amount in agi_2024.items():
    if source != "Total AGI":
        print(f"{source:<35} ${amount:>14,.0f} {'TBD':>15} {'TBD':>15} {'TBD':>10}")

print("-" * 90)
print(f"{'TOTAL AGI':<35} ${agi_2024['Total AGI']:>14,.0f} {'TBD':>15} {'TBD':>15} {'TBD':>10}")
print()


