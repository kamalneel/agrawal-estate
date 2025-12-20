# Historical Cost Basis Data Retrieval Guide

## Your Situation Summary
- **Accounts**: 5 accounts total
- **History**: Buying since 2015
- **Brokerage Evolution**: Scottrade → TD Ameritrade (2017) → Schwab (2020) → Robinhood (recent)
- **Goal**: Get complete historical cost basis for all holdings

---

## ⚠️ IMPORTANT: Cost Basis Transfer Requirements

**You're absolutely correct!** When you transferred from Schwab to Robinhood via ACATS (Automated Customer Account Transfer Service), **Schwab was REQUIRED to transfer cost basis information** to Robinhood. This is an IRS and FINRA requirement.

### Regulatory Requirements:
- **IRS Requirement**: For covered securities (stocks acquired after Jan 1, 2011), brokers MUST transfer:
  - Total adjusted cost basis
  - Original acquisition date
  - Holding period adjustments
- **FINRA Rule**: Brokers cannot impede or refuse to transfer cost basis information
- **Timeline**: Cost basis must be transferred within 15 calendar days of transfer settlement

### What This Means:
✅ **Robinhood already has your cost basis** - it was transferred from Schwab during the ACATS process  
✅ **Robinhood uses this for tax reporting** - they need it to file your 1099-B when you sell  
✅ **Your holdings exports should include "Average Cost"** - which reflects the transferred cost basis

### Where to Find It in Robinhood:
1. **Holdings CSV Export** - The "Average Cost" column includes transferred cost basis
2. **Account Statements** - PDF statements show cost basis for positions
3. **App/Web Interface** - Individual holdings show average cost basis
4. **Tax Lots** (if available) - Some brokerages show lot-level detail (check if Robinhood provides this)

---

## Best Strategy: Start with Robinhood (Simplest Path)

**Since Robinhood already has your transferred cost basis, start there first!** This is much simpler than trying to piece together data from multiple sources.

### Schwab (Your Best Source for Historical Data)

Schwab has absorbed:
- ✅ TD Ameritrade records (since 2020 acquisition, completed May 2024)
- ✅ Scottrade records (via TD Ameritrade, since 2017)

**What Schwab Has Available:**
- 4 years of detailed account history
- 10 years of account statements (PDFs)
- 7 years of tax documents (1099-B forms with cost basis)
- 2 years of trade confirmations
- Cost basis information via GainsKeeper tool

#### Method 1: Transaction History Export (Web Interface)

**Steps:**
1. Log into **Schwab.com** (or Schwab Alliance portal)
2. Go to **Accounts** → **History**
3. Select each account individually
4. Set date range (can export up to 90 days at a time, max 2 years back)
5. Click **Export** → Choose **CSV** format
6. **Repeat for each account** (all 5 accounts)
7. **Repeat for multiple date ranges** to cover full history

**Limitations:**
- ⚠️ Can only export 90 days at a time
- ⚠️ Maximum 2 years back through web interface
- ⚠️ Must do each account separately

**Your Parser Status:** ✅ You already have `SchwabParser` that can parse these CSVs

#### Method 2: Tax Lot Extractor (Chrome Extension) - **RECOMMENDED**

**Tool:** [Charles Schwab Tax Lot Extractor](https://chromewebstore.google.com/detail/charles-schwab-tax-lot-ex/nfngfaakmkihccflfeikhdogangajljc)

**Advantages:**
- ✅ Extracts **cost basis** directly from positions page
- ✅ Processes **multiple accounts** in one session
- ✅ Exports CSV/JSON format
- ✅ Runs in browser (no data leaves your computer)
- ✅ Includes tax lot details (cost basis per lot)

**Steps:**
1. Install the Chrome extension from Chrome Web Store
2. Log into Schwab.com
3. Navigate to **Positions** page for each account
4. Click extension icon → **"Start Extraction"**
5. Extension automatically extracts:
   - Symbol
   - Quantity
   - Cost basis
   - Unrealized gain/loss
   - Holding period info
6. Export as CSV
7. Repeat for each of your 5 accounts

**Your Parser Status:** Your `SchwabParser` can parse position CSVs with cost basis (line 231)

#### Method 3: Account Statements (PDF)

**Steps:**
1. Log into Schwab
2. Go to **Accounts** → **Statements & Tax Documents**
3. Download **all statements** from 2015-present (10 years available)
4. Use **month-end statements** for cost basis snapshots

**Your Parser Status:** ✅ You have `SchwabPDFParser` that extracts cost basis from statements

#### Method 4: GainsKeeper Tool

**Steps:**
1. Log into Schwab Alliance portal
2. Navigate to **GainsKeeper** (in Tools section)
3. View realized/unrealized gains/losses
4. Export cost basis reports

**Note:** This may require additional export functionality to be checked

---

### Robinhood (Your PRIMARY Source - Has Transferred Cost Basis) - **START HERE**

Since your accounts were transferred from Schwab via ACATS, **Robinhood already has all your cost basis information** including original purchase dates from Scottrade/TD Ameritrade/Schwab. This is your simplest path!

#### Method 1: Holdings CSV Export - **MOST RECOMMENDED** ✅

**What You Get:**
- Current positions with **"Average Cost"** column (includes transferred cost basis)
- Quantity, Market Value
- This reflects the weighted average cost basis that includes your Schwab/Scottrade purchases

**Steps:**
1. Log into **Robinhood.com** (web, not app)
2. Go to each account individually
3. Navigate to **Account** → **Investing** → **Holdings**
4. Look for **"Export"** or **"Download"** button (may be in settings/options)
5. Export as CSV
6. **Repeat for all 5 accounts**

**OR via Mobile App:**
1. Open Robinhood app
2. Go to **Account** icon → **Investing** → **Holdings**
3. Look for export/share option
4. Download CSV

**What the CSV Contains:**
- Symbol
- Quantity  
- **Average Cost** ← This is your cost basis (includes transferred cost basis!)
- Market Value

**Your Parser Status:** ✅ Your `RobinhoodParser` already extracts this! (Line 287: `"cost_basis": self._normalize_amount(row.get("Average Cost") or "")`)

**This is the easiest method - the cost basis is already there!**

**Bonus: View Individual Tax Lots (Mobile App Only)**
- Robinhood's mobile app allows viewing individual tax lots (but not web)
- When selling: Open stock → Trade → Sell → Tap "Tax lots" (top right)
- Shows: Acquisition date, quantity per lot, cost per share
- **For transferred shares:** Shows the date they were deposited into Robinhood (which should reflect original purchase date if transfer included that info)
- Useful for verifying lot-level detail, but CSV export gives you the aggregate average cost basis

#### Method 2: Account Statements (PDF)

**What You Get:**
- Month-end snapshots with cost basis for all positions
- Historical records going back to when you opened accounts at Robinhood

**Steps:**
1. Log into Robinhood
2. Go to **Reports and Statements**
3. Download **all monthly statements** since account opening
4. Each statement shows cost basis for positions

**Your Parser Status:** ✅ You have `RobinhoodPDFParser` that extracts cost basis

#### Method 3: Activity Reports (Transaction History)

**What You Get:**
- Complete transaction history (buy/sell/dividends) from 2015-present
- Useful for verifying and recalculating cost basis if needed

**Steps:**
1. Open **Robinhood app** or website
2. Tap **Account** icon → **Reports and Statements**
3. Under **Account Activity Reports**, tap **Reports**
4. Tap **Generate New Report**
5. Set date range: **2015** to **present**
6. Select transaction types: Orders, Dividends, Transfers
7. Tap **Generate Report**
8. Wait (minutes to 24 hours)
9. Download CSV when ready
10. **Repeat for each account** (all 5)

**Advantages:**
- Complete transaction history for verification
- Can use with your cost basis calculator to verify Robinhood's numbers

**Your Parser Status:** ✅ You have `RobinhoodParser` that can parse transaction CSVs

#### Method 2: Chrome Extension - Robinhood Trades Downloader

**Tool:** [Robinhood Trades Downloader](https://chromewebstore.google.com/detail/robinhood-trades-download/fhbhfdoemoabnpjgbeoncaoifakhmlgh)

**Steps:**
1. Install extension from Chrome Web Store
2. Log into **Robinhood.com** (web, not app)
3. Navigate to account
4. Extension adds export button
5. Click to download full transaction history
6. Exports as CSV with all trades

**Note:** Use with caution - third-party tools. Check what data it extracts.

---

## Recommended Action Plan (UPDATED - Start with Robinhood!)

### Phase 1: Get Current Cost Basis from Robinhood (Quick Win) ⚡

**Since Robinhood has your transferred cost basis, start here:**

1. **Export Holdings CSV from Robinhood** (Recommended):
   - Log into Robinhood.com for each of your 5 accounts
   - Export current holdings (includes "Average Cost" with transferred cost basis)
   - Import via your existing `RobinhoodParser`
   - **This should give you cost basis immediately!**

2. **Verify with Account Statements**:
   - Download latest account statements from Robinhood
   - Compare cost basis numbers
   - Import via `RobinhoodPDFParser`

3. **Use Your Cost Basis Calculator** (Optional verification):
   - Export transaction history from Robinhood (2015-present)
   - Use your new `calculate_cost_basis_from_transactions()` function
   - Compare calculated vs. Robinhood's reported cost basis
   - Any discrepancies might indicate data issues

**Expected Result:** You should have complete cost basis for all current holdings from Robinhood exports alone!

### Phase 2: Historical Transaction Data (For Verification & Recalculation)

**Only needed if you want to verify Robinhood's cost basis or have missing data:**

1. **Robinhood Transaction History**:
   - Generate full transaction report (2015-present) for each account
   - Import all transactions
   - Use your new cost basis calculation function to verify Robinhood's numbers
   - **Note:** Robinhood's "Average Cost" should already match your calculated cost basis (they use weighted average)

2. **Schwab Transaction History** (Only if still accessible and needed):
   - Only necessary if Robinhood is missing data (unlikely after ACATS transfer)
   - Export transaction history if you still have Schwab access
   - Use for historical reference/verification

### Phase 3: Use Your New Cost Basis Calculator

Once you have transaction history imported:

```bash
# Recalculate cost basis for all holdings
POST /api/v1/investments/holdings/recalculate-cost-basis

# Or for specific account/symbol
POST /api/v1/investments/holdings/recalculate-cost-basis?account_id=neel_brokerage&symbol=AAPL

# Preview calculation without updating
GET /api/v1/investments/holdings/{account_id}/{symbol}/cost-basis
```

---

## Data Source Priority (UPDATED)

### For Current Cost Basis (Recommended Order):

1. **BEST: Robinhood Holdings CSV Export** ⭐
   - **Includes transferred cost basis from Schwab/TD Ameritrade/Scottrade**
   - Shows "Average Cost" which reflects all historical purchases
   - Official Robinhood data (what they'll use for tax reporting)
   - Easiest to extract - one export per account
   - Your parser already handles this!

2. **Good: Robinhood Account Statements (PDF)**
   - Month-end snapshots with cost basis
   - Historical record
   - Good for verification

3. **Verification: Transaction History + Calculation**
   - Export transaction history (2015-present)
   - Use your weighted average calculator
   - Verify against Robinhood's reported cost basis
   - Should match if transfer was successful

4. **Fallback Only: Schwab (if still accessible)**
   - Only if Robinhood data is missing/incorrect
   - Tax Lot Extractor for lot-level detail
   - Historical reference

### For Transaction History (To Recalculate):

1. **Schwab History Export**: Use web interface (chunk by 90-day periods)
2. **Robinhood Reports**: Generate full date range reports
3. **Account Statements**: PDFs have historical snapshots

---

## What Your System Can Already Handle

✅ **Parsers Available:**
- `SchwabParser` - CSV transaction history & positions
- `SchwabPDFParser` - PDF statements with cost basis
- `RobinhoodParser` - CSV transaction history & holdings
- `RobinhoodPDFParser` - PDF statements
- `TDAmeritradePDFParser` - Historical TD Ameritrade statements

✅ **Database Structure:**
- `InvestmentTransaction` table stores all buy/sell transactions
- `InvestmentHolding` table stores current positions with cost_basis field
- Your new `calculate_cost_basis_from_transactions()` function can recalculate

✅ **Import Process:**
- You have ingestion endpoints at `/api/v1/ingestion/upload`
- Files go to `inbox/investments/schwab/` or `inbox/investments/robinhood/`
- Auto-detects and parses files

---

## Important Notes

⚠️ **Account Mapping:**
- Make sure you map old TD Ameritrade/Scottrade account numbers to your current account structure
- Your `ACCOUNT_ID_MAPPING` in `ingestion/services.py` handles some Robinhood mappings

⚠️ **Potential Data Issues (But Shouldn't Happen):**
- **If Robinhood missing cost basis after transfer:** This violates IRS requirements - contact Robinhood support
- **If cost basis seems incorrect:** Compare with tax documents (1099-B forms)
- **Non-covered securities** (purchased before 2011): May not have detailed lot-level info, but average cost should still transfer
- **Delays:** Cost basis can take up to 15 days after transfer to appear (should be settled by now)

✅ **What Should Work:**
- Robinhood Holdings CSV should have "Average Cost" for all positions
- This includes weighted average of all purchases (Schwab + Robinhood)
- Should match what you'd calculate from transaction history

⚠️ **Cost Basis Methods:**
- Different brokerages might use FIFO vs. Weighted Average
- Your new calculator uses Weighted Average (standard for most tax purposes)
- Verify against tax documents for discrepancies

---

## Quick Start Checklist (UPDATED - Simplified!)

### Primary Path (Robinhood Has Your Cost Basis):

- [ ] **Export Holdings CSV from Robinhood for all 5 accounts** ⭐ (START HERE)
  - Log into Robinhood.com → Each account → Holdings → Export CSV
  - Or use mobile app if export available
- [ ] Import CSVs via your ingestion system (`/api/v1/ingestion/upload`)
- [ ] Verify cost basis appears in your database (`/api/v1/investments/holdings`)
- [ ] Download latest Robinhood account statements (PDF) for verification
- [ ] Compare Robinhood's cost basis with your data

### Verification Path (Optional but Recommended):

- [ ] Generate Robinhood Activity Reports (2015-present) for all 5 accounts
- [ ] Import transaction history via your Robinhood parser
- [ ] Run cost basis recalculation: `POST /api/v1/investments/holdings/recalculate-cost-basis`
- [ ] Compare calculated cost basis vs. Robinhood's reported cost basis
- [ ] Any discrepancies? Check for data gaps or transfer issues

### Fallback Path (Only if Robinhood Data Missing):

- [ ] If Robinhood missing data, check if Schwab access still available
- [ ] Use Schwab Tax Lot Extractor if needed
- [ ] Export historical statements from Schwab if needed

---

## Key Insight: Trust Robinhood First

Since the ACATS transfer was **required by law** to include cost basis, and Robinhood needs this information for tax reporting, **Robinhood should already have accurate cost basis** for all your transferred positions. Start there - it's the easiest path!

