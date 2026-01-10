"""
Tax Form Generator - IRS Form 1040 and California Form 540

Generates tax return forms in the official IRS/CA format for comparison
with professionally prepared returns.

Based on:
- IRS Form 1040 (2025)
- California Form 540 (2025)
- Supporting Schedules (1, E, D, B)
"""

from typing import Dict, Any, List, Optional
from decimal import Decimal
from pydantic import BaseModel


class Form1040Line(BaseModel):
    """Single line item on Form 1040."""
    line_number: str
    description: str
    amount: float
    note: Optional[str] = None


class Form1040(BaseModel):
    """IRS Form 1040 - U.S. Individual Income Tax Return."""

    # Header
    tax_year: int
    filing_status: str
    taxpayer_name: str
    spouse_name: Optional[str] = None

    # Income Section (Lines 1-9)
    line_1a: float = 0  # Total wages, salaries, tips (W-2 Box 1)
    line_1z: float = 0  # Total wages (calculated)
    line_2a: float = 0  # Tax-exempt interest
    line_2b: float = 0  # Taxable interest
    line_3a: float = 0  # Qualified dividends
    line_3b: float = 0  # Ordinary dividends
    line_4a: float = 0  # IRA distributions
    line_4b: float = 0  # Taxable amount
    line_5a: float = 0  # Pensions and annuities
    line_5b: float = 0  # Taxable amount
    line_6a: float = 0  # Social security benefits
    line_6b: float = 0  # Taxable amount
    line_7: float = 0   # Capital gain or (loss) (Schedule D)
    line_8: float = 0   # Additional income from Schedule 1, line 10
    line_9: float = 0   # Total income (add lines 1z through 8)

    # Adjustments (Lines 10-11)
    line_10: float = 0  # Adjustments to income from Schedule 1, line 26
    line_11: float = 0  # Adjusted Gross Income (AGI) (line 9 minus line 10)

    # Deductions (Lines 12-15)
    line_12: float = 0  # Standard deduction or itemized deductions
    line_12_type: str = "standard"  # "standard" or "itemized"
    line_13: float = 0  # Qualified business income deduction
    line_14: float = 0  # Add lines 12 and 13
    line_15: float = 0  # Taxable income (line 11 minus line 14)

    # Tax and Credits (Lines 16-24)
    line_16: float = 0  # Tax (from tax tables or Tax Computation Worksheet)
    line_17: float = 0  # Amount from Schedule 2, line 3 (additional taxes)
    line_18: float = 0  # Add lines 16 and 17
    line_19: float = 0  # Child tax credit and credit for other dependents
    line_20: float = 0  # Amount from Schedule 3, line 8 (other credits)
    line_21: float = 0  # Add lines 19 and 20
    line_22: float = 0  # Subtract line 21 from line 18
    line_23: float = 0  # Other taxes from Schedule 2, line 21
    line_24: float = 0  # Total tax (add lines 22 and 23)

    # Payments (Lines 25-33)
    line_25a: float = 0  # Federal income tax withheld (W-2)
    line_25b: float = 0  # Federal income tax withheld (1099)
    line_25c: float = 0  # Federal income tax withheld (other)
    line_25d: float = 0  # Total federal income tax withheld
    line_26: float = 0   # 2025 estimated tax payments
    line_27: float = 0   # Earned income credit (EIC)
    line_28: float = 0   # Additional child tax credit
    line_29: float = 0   # American opportunity credit
    line_30: float = 0   # Reserved for future use
    line_31: float = 0   # Amount from Schedule 3, line 15
    line_32: float = 0   # Add lines 25d through 31 (total payments)
    line_33: float = 0   # If line 32 > line 24, overpayment

    # Refund or Amount Owed (Lines 34-38)
    line_34: float = 0   # Amount of line 33 you want refunded
    line_35a: float = 0  # Amount of line 33 you want applied to 2026 estimated tax
    line_36: float = 0   # Amount you owe (line 24 minus line 32)
    line_37: float = 0   # Estimated tax penalty
    line_38: float = 0   # Amount you owe (line 36 plus line 37)


class Schedule1(BaseModel):
    """Schedule 1 - Additional Income and Adjustments to Income."""

    # Part I: Additional Income (Lines 1-10)
    line_1: float = 0   # Taxable refunds, credits, or offsets of state and local income taxes
    line_2a: float = 0  # Alimony received
    line_3: float = 0   # Business income or (loss) (Schedule C)
    line_4: float = 0   # Other gains or (losses) (Form 4797)
    line_5: float = 0   # Rental real estate, royalties, partnerships, S corps, trusts (Schedule E)
    line_6: float = 0   # Farm income or (loss) (Schedule F)
    line_7: float = 0   # Unemployment compensation
    line_8: float = 0   # Other income
    line_9: float = 0   # Total other income (add lines 1 through 8)
    line_10: float = 0  # Combine lines 9 and Schedule 1 additional income

    # Part II: Adjustments to Income (Lines 11-26)
    line_11: float = 0  # Educator expenses
    line_12: float = 0  # Business expenses (reservists, performing artists, fee-basis officials)
    line_13: float = 0  # Health savings account deduction
    line_14: float = 0  # Moving expenses (military)
    line_15: float = 0  # Deductible part of self-employment tax
    line_16: float = 0  # Self-employed SEP, SIMPLE, and qualified plans
    line_17: float = 0  # Self-employed health insurance deduction
    line_18: float = 0  # Penalty on early withdrawal of savings
    line_19a: float = 0 # Alimony paid
    line_20: float = 0  # IRA deduction
    line_21: float = 0  # Student loan interest deduction
    line_22: float = 0  # Reserved for future use
    line_23: float = 0  # Archer MSA deduction
    line_24: float = 0  # Other adjustments
    line_25: float = 0  # Total adjustments (add lines 11 through 24)
    line_26: float = 0  # Total adjustments to income


class ScheduleE(BaseModel):
    """Schedule E - Supplemental Income and Loss (Rental Real Estate)."""

    # Part I: Income or Loss From Rental Real Estate
    property_address: str

    # Income
    line_3: float = 0   # Rents received
    line_4: float = 0   # Royalties received

    # Expenses
    line_5: float = 0   # Advertising
    line_6: float = 0   # Auto and travel
    line_7: float = 0   # Cleaning and maintenance
    line_8: float = 0   # Commissions
    line_9: float = 0   # Insurance
    line_10: float = 0  # Legal and other professional fees
    line_11: float = 0  # Management fees
    line_12: float = 0  # Mortgage interest
    line_13: float = 0  # Other interest
    line_14: float = 0  # Repairs
    line_15: float = 0  # Supplies
    line_16: float = 0  # Taxes
    line_17: float = 0  # Utilities
    line_18: float = 0  # Depreciation
    line_19: float = 0  # Other expenses
    line_20: float = 0  # Total expenses (add lines 5 through 19)

    # Net Income/Loss
    line_21: float = 0  # Subtract line 20 from line 3 (rents)
    line_22: float = 0  # Deductible rental real estate loss
    line_26: float = 0  # Total rental real estate income or (loss)


class ScheduleD(BaseModel):
    """Schedule D - Capital Gains and Losses."""

    # Part I: Short-Term Capital Gains and Losses
    line_1a: float = 0  # Short-term transactions from broker (Form 1099-B)
    line_1b: float = 0  # Short-term transactions not reported
    line_2: float = 0   # Short-term gain from Form 6252
    line_3: float = 0   # Short-term gain from Form 4684, 6781, 8824
    line_4: float = 0   # Short-term gain or (loss) from partnerships, S corps
    line_5: float = 0   # Short-term capital loss carryover
    line_6: float = 0   # Net short-term capital gain or (loss)
    line_7: float = 0   # Combine lines 1a through 6

    # Part II: Long-Term Capital Gains and Losses
    line_8a: float = 0  # Long-term transactions from broker (Form 1099-B)
    line_8b: float = 0  # Long-term transactions not reported
    line_9: float = 0   # Long-term gain from Form 6252
    line_10: float = 0  # Long-term gain from Form 4684, 6781, 8824
    line_11: float = 0  # Long-term gain or (loss) from partnerships, S corps
    line_12: float = 0  # Capital gain distributions
    line_13: float = 0  # Long-term capital loss carryover
    line_14: float = 0  # Net long-term capital gain or (loss)
    line_15: float = 0  # Combine lines 8a through 14

    # Part III: Summary
    line_16: float = 0  # Combine lines 7 and 15 (net capital gain or loss)
    line_17: bool = False  # Are lines 15 and 16 both gains?
    line_18: float = 0  # 28% rate gain or (loss)
    line_19: float = 0  # Unrecaptured section 1250 gain
    line_20: float = 0  # Net capital gain (if line 17 is yes)
    line_21: float = 0  # Net capital loss (if line 16 is a loss)


class CaliforniaForm540(BaseModel):
    """California Form 540 - Resident Income Tax Return."""

    tax_year: int
    filing_status: str
    taxpayer_name: str
    spouse_name: Optional[str] = None

    # Part I: Income
    line_11: float = 0  # Wages, salaries, tips (W-2)
    line_12: float = 0  # Interest income
    line_13: float = 0  # Dividends
    line_14: float = 0  # State income tax refund
    line_15: float = 0  # Business income or (loss)
    line_16: float = 0  # Capital gain or (loss)
    line_17: float = 0  # Rental, royalties, partnerships, etc.
    line_18: float = 0  # Farm income or (loss)
    line_19: float = 0  # Other income
    line_20: float = 0  # Total income (add lines 11-19)

    # Part II: Adjustments to Income
    line_21: float = 0  # Adjustments to federal AGI
    line_22: float = 0  # California AGI (line 20 minus line 21)

    # Part III: Deductions
    line_23: float = 0  # Standard deduction or itemized deductions
    line_23_type: str = "standard"
    line_24: float = 0  # Exemptions
    line_25: float = 0  # Taxable income (line 22 minus lines 23 and 24)

    # Part IV: Tax and Credits
    line_31: float = 0  # Tax (from tax table or rate schedule)
    line_32: float = 0  # Alternative minimum tax
    line_33: float = 0  # Mental Health Services Tax (1% on income over $1M)
    line_34: float = 0  # Total tax (add lines 31-33)
    line_35: float = 0  # Credits
    line_36: float = 0  # Subtract line 35 from line 34

    # Part V: Other Taxes
    line_37: float = 0  # Other taxes
    line_38: float = 0  # Total tax (add lines 36 and 37)

    # Part VI: Payments
    line_41: float = 0  # CA income tax withheld
    line_42: float = 0  # 2025 estimated tax payments
    line_43: float = 0  # Other payments and credits
    line_44: float = 0  # Total payments (add lines 41-43)

    # Part VII: Refund or Amount Owed
    line_45: float = 0  # Overpayment (if line 44 > line 38)
    line_46: float = 0  # Amount to be refunded
    line_47: float = 0  # Amount owed (if line 38 > line 44)
    line_48: float = 0  # Estimated tax penalty
    line_49: float = 0  # Amount you owe (line 47 plus line 48)


class TaxFormPackage(BaseModel):
    """Complete tax return package."""

    form_1040: Form1040
    schedule_1: Optional[Schedule1] = None
    schedule_e: Optional[ScheduleE] = None
    schedule_d: Optional[ScheduleD] = None
    california_540: Optional[CaliforniaForm540] = None

    # Metadata
    is_forecast: bool = True
    generation_date: str
    notes: List[str] = []
