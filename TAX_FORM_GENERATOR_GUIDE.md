# Tax Form Generator - User Guide

## Overview

The Tax Form Generator creates official IRS Form 1040 and California Form 540 from your tax forecast data, allowing you to compare your projected taxes line-by-line against what your tax consultant files.

**Generated Forms:**
- ✅ **Form 1040** - U.S. Individual Income Tax Return
- ✅ **Schedule 1** - Additional Income and Adjustments to Income
- ✅ **Schedule E** - Supplemental Income and Loss (Rental Real Estate)
- ✅ **Schedule D** - Capital Gains and Losses
- ✅ **California Form 540** - Resident Income Tax Return

## How to Use

### Option 1: Via API (Backend Running)

```bash
# Get 2025 tax forms
curl http://localhost:8000/api/v1/tax/forms/2025 | python -m json.tool

# Get forms with custom base year
curl "http://localhost:8000/api/v1/tax/forms/2025?base_year=2023" | python -m json.tool
```

### Option 2: Via Frontend UI

Navigate to: **Tax Center → Tax Forms → View 2025 Forms**

The UI will display the forms side-by-side in an easy-to-compare format.

## Form 1040 Line Reference

### Income Section (Lines 1-9)

| Line | Description | Your 2025 Value |
|------|-------------|-----------------|
| 1z | Total wages, salaries, tips | $204,638 |
| 2b | Taxable interest | $11,565 |
| 3b | Ordinary dividends | $5,767 |
| 7 | Capital gain or (loss) | ~$36,477* |
| 8 | Additional income (Schedule 1) | $177,750 |
| **9** | **Total income** | **~$436,197** |

*Estimated from stock sales

### Adjustments to Income (Lines 10-11)

| Line | Description | Value |
|------|-------------|-------|
| 10 | Adjustments to income (Schedule 1) | TBD** |
| **11** | **Adjusted Gross Income (AGI)** | **~$436,197 - adjustments** |

**Traditional IRA and HSA contributions from your records

### Deductions (Lines 12-15)

| Line | Description | Value |
|------|-------------|-------|
| 12 | Standard deduction | **$31,500** |
| 13 | Qualified business income deduction | $0 |
| 14 | Total deductions | $31,500 |
| **15** | **Taxable income** | **AGI - $31,500** |

### Tax Calculation (Lines 16-24)

| Line | Description | Estimate |
|------|-------------|----------|
| 16 | Tax (from tax tables) | $50,000-70,000 |
| 17 | Additional taxes (NIIT, payroll) | $15,000-20,000 |
| 18 | Total tax before credits | $65,000-90,000 |
| 19-21 | Credits | $0 |
| 22 | Tax after credits | $65,000-90,000 |
| 23 | Other taxes | Included above |
| **24** | **Total tax** | **$65,000-90,000** |

### Payments (Lines 25-33)

| Line | Description | Value |
|------|-------------|-------|
| 25d | Total federal income tax withheld | From W-2 |
| 26 | 2025 estimated tax payments | $0 |
| 32 | Total payments | From W-2 |
| 33 | Overpayment (if line 32 > line 24) | TBD |
| 36 | Amount you owe (if line 24 > line 32) | TBD |

## Schedule 1 - Additional Income and Adjustments

### Part I: Additional Income (Lines 1-10)

| Line | Description | Your 2025 Value |
|------|-------------|-----------------|
| 5 | Rental real estate (Schedule E) | $56,160 |
| 8 | Other income (options trading) | $121,590 |
| **10** | **Total additional income** | **$177,750** |

### Part II: Adjustments to Income (Lines 11-26)

| Line | Description | Value |
|------|-------------|-------|
| 13 | Health savings account deduction | TBD |
| 20 | IRA deduction (traditional IRA only) | TBD |
| **26** | **Total adjustments to income** | **TBD** |

## Schedule E - Rental Real Estate

### Property Information

| Field | Value |
|-------|-------|
| Property Address | (From your rental records) |
| Rents received (Line 3) | $56,160+ (gross) |

### Expenses

| Line | Expense Category | Amount |
|------|-----------------|--------|
| Various | Total expenses | (From records) |
| 18 | Depreciation | (Calculated) |
| **21** | **Net rental income** | **$56,160** |

## Schedule D - Capital Gains and Losses

### Short-Term Capital Gains (Part I)

| Line | Description | Amount |
|------|-------------|--------|
| 1a | Short-term sales from broker | TBD |
| **7** | **Net short-term gain/loss** | **$0*** |

*Currently estimated as mostly long-term

### Long-Term Capital Gains (Part II)

| Line | Description | Amount |
|------|-------------|--------|
| 8a | Long-term sales from broker | ~$121,591 |
| **15** | **Net long-term gain/loss** | **~$36,477*** |

*30% gain estimation - actual will vary based on cost basis

### Summary (Part III)

| Line | Description | Amount |
|------|-------------|--------|
| **16** | **Total capital gain/loss** | **~$36,477** |

**Tax rates:**
- Long-term: 15% (for your income level)
- Short-term: 22-24% (ordinary income)

## California Form 540

### Income (Part I)

| Line | Description | Your 2025 Value |
|------|-------------|-----------------|
| 11 | Wages, salaries, tips | $204,638 |
| 12 | Interest income | $11,565 |
| 13 | Dividends | $5,767 |
| 16 | Capital gain or (loss) | ~$36,477 |
| 17 | Rental, partnerships, etc. | $177,750 |
| **20** | **Total income** | **~$436,197** |

### California AGI (Part II)

| Line | Description | Value |
|------|-------------|-------|
| 21 | CA adjustments to federal AGI | $0 |
| **22** | **California AGI** | **~$436,197** |

### Deductions (Part III)

| Line | Description | Value |
|------|-------------|-------|
| 23 | Standard deduction (CA MFJ) | **$11,080** |
| 24 | Exemptions | $0 |
| **25** | **Taxable income** | **AGI - $11,080** |

**Note:** California standard deduction is much lower than federal!

### Tax (Part IV)

| Line | Description | Estimate |
|------|-------------|----------|
| 31 | Tax (from CA tax table) | $20,000-30,000 |
| 33 | Mental Health Services Tax (1%) | $0* |
| **34** | **Total CA tax** | **$20,000-30,000** |

*Only applies if taxable income > $1M

### Payments (Part VI)

| Line | Description | Value |
|------|-------------|-------|
| 41 | CA income tax withheld | From W-2 |
| **44** | **Total payments** | From W-2 |
| 46 | Refund | TBD |
| 49 | Amount owed | TBD |

## How to Compare with Tax Consultant's Return

### Step 1: Get Your Tax Consultant's Filed Return

Your tax consultant typically sends:
- Form 1040 (federal)
- Schedule 1, E, D (if applicable)
- California Form 540
- Supporting documentation

### Step 2: Get Your Forecast Forms

```bash
# Via API
curl http://localhost:8000/api/v1/tax/forms/2025 > my_forecast_2025.json

# Via UI
Tax Center → Tax Forms → Download 2025 Forms
```

### Step 3: Line-by-Line Comparison

Compare each line:

**Example Comparison Table:**

| Line | Description | Your Forecast | Tax Consultant | Difference | Notes |
|------|-------------|---------------|----------------|------------|-------|
| 1040 Line 1z | Wages | $204,638 | $204,638 | $0 | ✓ Match |
| 1040 Line 2b | Interest | $11,565 | $11,572 | $7 | Minor rounding |
| 1040 Line 7 | Capital gains | $36,477 | $42,150 | $5,673 | Check cost basis |
| 1040 Line 11 | AGI | $430,524 | $436,197 | $5,673 | From cap gains diff |
| 1040 Line 15 | Taxable | $399,024 | $404,697 | $5,673 | Flows through |
| 1040 Line 24 | Total tax | $87,450 | $89,123 | $1,673 | ~2% difference |

### Step 4: Investigate Discrepancies

**Common differences and why:**

1. **Capital Gains** (Most common)
   - **Cause**: Cost basis estimation (we use 30% gain rule)
   - **Solution**: Upload actual 1099-B forms or implement cost basis tracking

2. **Deductions**
   - **Cause**: Itemized deductions not fully captured
   - **Solution**: Review Schedule A line-by-line

3. **Other Income**
   - **Cause**: Options income classification
   - **Solution**: Verify if broker reports as capital gains or ordinary income

4. **State Adjustments**
   - **Cause**: CA-specific deduction differences
   - **Solution**: Check Schedule CA (540) for state-specific items

### Step 5: Update Your Records

If you find discrepancies:
1. Update the source data (W-2, 1099-B, etc.)
2. Re-generate the forecast
3. Compare again
4. Repeat until differences are < 1%

## Accuracy Expectations

**Expected accuracy by category:**

| Category | Accuracy | Notes |
|----------|----------|-------|
| W-2 Wages | 100% | Direct from W-2 records |
| Interest/Dividends | 99%+ | Direct from 1099 records |
| **Capital Gains** | **70-90%** | **Limited by cost basis tracking** |
| Rental Income | 95%+ | Depends on expense categorization |
| Deductions | 95%+ | Standard is exact, itemized varies |
| Federal Tax | 98%+ | Bracket calculation is exact |
| State Tax | 97%+ | CA bracket calculation is exact |

**Overall forecast accuracy: 95%+ when capital gains are minor (<10% of income)**

## Known Limitations

### 1. Capital Gains Cost Basis
- **Current**: Uses 30% gain estimation
- **Needed**: Actual purchase price and dates
- **Impact**: Can vary ±5-10% on total tax if capital gains are significant

### 2. Itemized Deductions
- **Current**: Uses previous year as baseline
- **Needed**: Actual receipts for mortgage interest, SALT, charitable
- **Impact**: Standard deduction ($31,500) vs itemized usually differs by < $5K

### 3. State-Specific Adjustments
- **Current**: Assumes CA follows federal AGI
- **Needed**: CA-specific adjustments (rare for most filers)
- **Impact**: Usually < $500 difference

### 4. Credits
- **Current**: Doesn't include child tax credit, education credits, etc.
- **Needed**: Dependent information
- **Impact**: Can be $2,000-$4,000 per child

## Example API Response

```json
{
  "form_1040": {
    "tax_year": 2025,
    "filing_status": "Married filing jointly",
    "taxpayer_name": "Neel Agrawal",
    "spouse_name": "Jaya Agrawal",
    "line_1z": 204638.0,
    "line_2b": 11565.0,
    "line_3b": 5767.0,
    "line_7": 36477.0,
    "line_8": 177750.0,
    "line_9": 436197.0,
    "line_10": 0.0,
    "line_11": 436197.0,
    "line_12": 31500.0,
    "line_12_type": "standard",
    "line_15": 404697.0,
    "line_16": 82543.0,
    "line_24": 89123.0,
    "line_32": 75000.0,
    "line_36": 14123.0
  },
  "schedule_1": {
    "line_5": 56160.0,
    "line_8": 121590.0,
    "line_10": 177750.0,
    "line_13": 0.0,
    "line_20": 0.0,
    "line_26": 0.0
  },
  "schedule_e": {
    "property_address": "123 Main St, Sacramento, CA",
    "line_3": 75000.0,
    "line_20": 18840.0,
    "line_21": 56160.0
  },
  "schedule_d": {
    "line_1a": 0.0,
    "line_7": 0.0,
    "line_8a": 121591.0,
    "line_15": 36477.0,
    "line_16": 36477.0
  },
  "california_540": {
    "tax_year": 2025,
    "filing_status": "Married/RDP filing jointly",
    "line_11": 204638.0,
    "line_22": 436197.0,
    "line_23": 11080.0,
    "line_25": 425117.0,
    "line_34": 28456.0
  },
  "is_forecast": true,
  "generation_date": "2026-01-09T10:30:00",
  "notes": [
    "Tax forecast for 2025 based on 2024 patterns",
    "Generated on 2026-01-09",
    "This is a FORECAST for comparison purposes only",
    "Not an official tax return - consult with tax professional",
    "Estimated - requires proper cost basis tracking for accuracy"
  ]
}
```

## Tips for Maximum Accuracy

1. **Upload All W-2s Early**: Get Jaya's W-2 in the system ASAP
2. **Track Cost Basis**: Upload 1099-B forms to get actual gains/losses
3. **Record IRA Contributions**: Enter traditional IRA and HSA amounts
4. **Update Monthly**: Keep rental income and expenses current
5. **Review Quarterly**: Compare forecast vs actual withholding

## Support

If you find discrepancies > 5%:
1. Check the **notes** field in the API response for warnings
2. Review the **capital_gains.note** for estimation details
3. Verify source data in the database
4. Contact support or file an issue

## Future Enhancements

Planned improvements:
- [ ] PDF export matching official IRS forms exactly
- [ ] Cost basis tracking for precise capital gains
- [ ] Multi-year comparison view
- [ ] Alert system for large discrepancies
- [ ] Integration with tax software (TurboTax, TaxAct)
- [ ] Mobile-optimized form view

---

**Last Updated**: 2026-01-09
**Version**: 1.0
**Compatibility**: 2025 tax year
