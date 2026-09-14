"""Regression tests pinned to the filed TY2025 return (Diwakar Taxes, 2026-02-19).

The reconciliation (docs/2025-TAX-RETURN-RECONCILIATION.md) showed the federal
formulas reproduce the return to the dollar on the return's own inputs; these
tests keep that true. Run: pytest tests/test_tax_forecast_formulas.py -v
"""
import pytest

from app.modules.tax.forecast import (
    _calculate_federal_tax,
    _calculate_taxable_income,
    _calculate_ca_state_tax,
    _calculate_ca_taxable_income,
)
from app.modules.income.paystub_parser import parse_adamx_paystub_text, PaystubValidationError


# --- Filed TY2025 return, Form 1040 ---
RETURN_AGI = 279_049
RETURN_TAXABLE = 242_854
RETURN_PREFERENTIAL = 17_739          # QD&CG worksheet line 4 (2,783 QD + 14,956 LTCG)
RETURN_TAX_LINE_16 = 42_383
RETURN_QBI = 4_695
RETURN_RENTAL_NET = 23_476
RETURN_CA_TAXABLE = 274_439          # Form 540 line 19
RETURN_CA_TAX_LINE_31 = 18_400


def test_federal_tax_matches_filed_return():
    tax = _calculate_federal_tax(RETURN_TAXABLE, "MFJ", 2025, preferential_income=RETURN_PREFERENTIAL)
    assert abs(tax - RETURN_TAX_LINE_16) <= 1


def test_taxable_income_and_qbi_match_filed_return():
    ti, qbi = _calculate_taxable_income(RETURN_AGI, {}, 2025, rental_net_income=RETURN_RENTAL_NET)
    assert abs(ti - RETURN_TAXABLE) <= 1
    assert abs(qbi - RETURN_QBI) <= 1


def test_ca_tax_matches_filed_return_schedule_y():
    """FTB 2025 Schedule Y on the return's CA taxable income → 540 line 31."""
    tax = _calculate_ca_state_tax(RETURN_CA_TAXABLE, "MFJ", 2025)
    assert abs(tax - RETURN_CA_TAX_LINE_31) <= 1


def test_ca_standard_deduction_2025():
    ca_agi = 285_851  # federal AGI + 6,802 HSA add-back, Form 540 line 17
    assert abs(_calculate_ca_taxable_income(ca_agi, {}, 2025) - RETURN_CA_TAXABLE) <= 1


# --- Paystub parser (AdamX / Gusto format) ---
ADAMX_STUB = """Pay summary
Earnings statement Company 1702 Meridian Avenue
AdamX Inc. Suite L-150
San Jose, CA 95125
6504307843 Neel Kamal
XXX-XX-1888
3392 Saint Michael Drive
Palo Alto, CA 94306
Gross earnings
Pay period: 09/01/26 - 09/15/26
Earning Rate Hours Current YTD Hours YTD Earnings
Pay date: 09/15/26
Salaried $360,000 Salary (09/01/2026 - 09/15/2026) $173.07 86.6700 $15,000.00 Total hours: 86.6700
Salaried Total 86.6700 $15,000.00 606.6900 $65,000.00
Taxes withheld
Net pay
Employee tax Current YTD
$9,915.56
Social Security Tax $930.00 $4,030.00
Federal Income Tax $2,569.50 $9,015.18 YTD $45,969.04
Medicare $217.50 $942.50
California SDI $195.00 $845.00
California State Tax $1,172.44 $4,198.28 Pay splits
••••7358 — $9,915.56
Gross earnings
$15,000.00
YTD $65,000.00
Employee taxes withheld
$5,084.44
YTD $19,030.96
Employee benefits contributions
$0.00
YTD $0.00
Post-tax deductions
$0.00
YTD $0.00
Reimbursements
$0.00
YTD $0.00"""


def test_adamx_paystub_parses_and_validates():
    f = parse_adamx_paystub_text(ADAMX_STUB, "stub.pdf")
    assert f.person == "Neel" and f.employer == "AdamX Inc."
    assert str(f.pay_date) == "2026-09-15" and str(f.period_start) == "2026-09-01"
    assert f.annual_rate == 360_000
    assert f.gross == 15_000 and f.gross_ytd == 65_000
    assert f.federal_withheld == 2_569.50 and f.federal_withheld_ytd == 9_015.18
    assert f.state_withheld == 1_172.44 and f.state_withheld_ytd == 4_198.28
    assert f.social_security == 930 and f.medicare == 217.50 and f.sdi == 195
    assert f.net == 9_915.56 and f.net_ytd == 45_969.04
    assert f.taxes_current == 5_084.44 and f.taxes_ytd == 19_030.96
    assert f.warnings == []


def test_adamx_paystub_rejects_mismatched_totals():
    bad = ADAMX_STUB.replace("Federal Income Tax $2,569.50", "Federal Income Tax $2,000.00")
    with pytest.raises(PaystubValidationError):
        parse_adamx_paystub_text(bad, "bad.pdf")
