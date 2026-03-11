# Tax Center App

## Goal

The Tax Center is the comprehensive hub for all tax-related activities, providing:
1. Historical tax records spanning 20+ years
2. Tax forecasting with quarterly estimated payment tracking
3. Tax form generation (Form 1040, CA Form 540)
4. Cost basis tracking for capital gains
5. **Tax document management** - Store, organize, and process incoming tax documents (1099s, W-2s, etc.) to build the actual tax file for each year

The distinction between **forecasted** and **actual** tax data is critical:
- **Forecasted**: Projections based on income, investments, and expected transactions throughout the year
- **Actual**: Final figures derived from official tax documents received from financial institutions

---

## Features

### Current Features

1. **Tax Returns History**
   - Display 20+ years of historical tax data
   - AGI, federal tax, state tax, other taxes
   - Effective tax rates by year
   - Tax forecasts for current/future years

2. **Quarterly Estimated Tax Payments**
   - Track quarterly due dates (Apr 15, Jun 15, Sep 15, Jan 15)
   - Record estimated payments made
   - W-2 withholding tracking
   - Payment status indicators (past due, due soon, paid, partial)

3. **Tax Forecasting Engine**
   - Project AGI based on income sources
   - Calculate federal and state tax liability
   - Safe harbor compliance checking
   - Underpayment penalty estimation
   - Expense forecasting integration

4. **Tax Form Generation**
   - IRS Form 1040 (U.S. Individual Income Tax Return)
   - California Form 540
   - Schedule D (Capital Gains and Losses)
   - Schedule E (Supplemental Income)
   - PDF generation for official filing

5. **Cost Basis Tracking**
   - Stock lot management (purchases)
   - FIFO/LIFO lot matching for sales
   - Wash sale detection
   - Long-term vs short-term gain classification
   - Capital gains summary

---

## Roadmap

### Phase 1: Tax Document Management (January 2026)

**Goal**: Enable storage, organization, and processing of incoming tax documents to build the actual tax file for each tax year.

#### 1.1 Document Upload & Storage
- [ ] Create local folder structure for tax documents: `data/tax-documents/{year}/`
- [ ] Support document types:
  - **1099-INT** - Interest income
  - **1099-DIV** - Dividend income
  - **1099-B** - Brokerage transactions (capital gains)
  - **1099-R** - Retirement distributions
  - **1099-MISC** - Miscellaneous income
  - **1099-NEC** - Non-employee compensation
  - **1099-K** - Payment card transactions
  - **W-2** - Wages and salary
  - **W-2G** - Gambling winnings
  - **1098** - Mortgage interest
  - **1098-T** - Tuition statement
  - **K-1** - Partnership/S-Corp income
  - **Property tax bills**
  - **Charitable donation receipts**
  - **Other tax-related documents**
- [ ] Upload interface with drag-and-drop support
- [ ] Automatic document type detection (based on content/filename)
- [ ] Document metadata (institution, date received, document date)

#### 1.2 Document Processing & Review
- [ ] AI-powered document parsing to extract key figures:
  - Total income/interest/dividends
  - Capital gains and losses
  - Taxes withheld
  - Institution identifiers (EIN)
- [ ] Side-by-side comparison: extracted values vs forecasted values
- [ ] Flag discrepancies between documents and forecasts
- [ ] Manual override capability for extracted values

#### 1.3 Actual Tax File
- [ ] New "Actual Tax File" view for each tax year
- [ ] Aggregate data from all processed documents
- [ ] Line-by-line mapping to Form 1040
- [ ] Show sources for each line item (which document)
- [ ] Completeness tracker:
  - Expected documents (based on known accounts)
  - Received documents
  - Missing documents

#### 1.4 UI Enhancements
- [ ] Add "Actual Tax File" link on the 2025 tax year page
- [ ] Two navigation paths:
  1. **Actual Tax File** - Aggregated tax data from documents
  2. **Tax Documents** - Browse/download all uploaded documents
- [ ] Document viewer with download capability
- [ ] Search/filter documents by type, institution, year
- [ ] Document status indicators (pending review, processed, verified)

### Phase 2: Document Intelligence (Future)

- [ ] OCR for scanned documents
- [ ] Automatic reconciliation with investment transactions
- [ ] Expected document checklist based on known accounts
- [ ] Email integration to auto-import tax documents
- [ ] Document expiration and retention policies

### Phase 3: Tax Preparation Integration (Future)

- [ ] Export to tax preparation software (TurboTax, H&R Block)
- [ ] IRS e-file integration
- [ ] California FTB integration
- [ ] Audit trail and documentation

---

## Architecture

### Frontend

**Pages:**
- `/pages/Tax.tsx` - Main Tax Center page (1,600+ lines)
- `/pages/TaxForms.tsx` - Tax form generation
- `/pages/CostBasis.tsx` - Capital gains tracking
- `/pages/TaxDocuments.tsx` - **NEW** Document management page
- `/pages/ActualTaxFile.tsx` - **NEW** Actual tax file view

**Routes:**
- `/tax` - Tax Center overview
- `/tax/forms` - Tax form generation
- `/tax/cost-basis` - Cost basis tracking
- `/tax/{year}/documents` - **NEW** Documents for specific year
- `/tax/{year}/actual` - **NEW** Actual tax file for specific year

### Backend

**Module:** `/backend/app/modules/tax/`

**Existing Files:**
- `router.py` - REST API endpoints
- `forecast.py` - Tax forecasting engine
- `form_generator.py` - Form 1040/540 generation
- `cost_basis_service.py` - Capital gains tracking
- `pdf_generator.py` - PDF generation
- `planning.py` - Tax planning analysis
- `models.py` - Database models

**New Files (Phase 1):**
- `document_service.py` - **NEW** Document management service
- `document_parser.py` - **NEW** Document parsing and extraction
- `actual_tax_service.py` - **NEW** Aggregate actual tax data

### Data Model

**Existing Tables:**
- `income_tax_returns` - Historical tax filings
- `estimated_tax_payments` - Quarterly payments
- `stock_lot` - Stock purchase lots
- `stock_lot_sale` - Sale records
- `tax_properties` - Property records
- `property_tax_records` - Property tax history

**New Tables (Phase 1):**

```sql
-- Tax documents received from institutions
CREATE TABLE tax_documents (
    id UUID PRIMARY KEY,
    tax_year INTEGER NOT NULL,
    document_type VARCHAR(50) NOT NULL,  -- '1099-INT', 'W-2', etc.
    institution_name VARCHAR(255),
    institution_ein VARCHAR(20),
    file_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    upload_date TIMESTAMP NOT NULL,
    document_date DATE,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, processed, verified
    extracted_data JSONB,  -- Parsed values from document
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Actual tax line items derived from documents
CREATE TABLE actual_tax_items (
    id UUID PRIMARY KEY,
    tax_year INTEGER NOT NULL,
    form_line VARCHAR(50) NOT NULL,  -- '1040:1' for Form 1040 Line 1
    description VARCHAR(255),
    amount DECIMAL(15, 2) NOT NULL,
    source_document_id UUID REFERENCES tax_documents(id),
    is_manual_entry BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### File Storage

**Local Storage Structure:**
```
data/
└── tax-documents/
    └── 2025/
        ├── 1099-int/
        │   ├── chase-bank-1099-int.pdf
        │   └── ally-bank-1099-int.pdf
        ├── 1099-div/
        │   ├── schwab-1099-div.pdf
        │   └── vanguard-1099-div.pdf
        ├── 1099-b/
        │   ├── robinhood-1099-b.pdf
        │   └── schwab-1099-b.pdf
        ├── w2/
        │   └── employer-w2.pdf
        └── other/
            └── charitable-donations.pdf
```

### API Endpoints (Phase 1)

```
# Document Management
POST   /api/tax/documents/upload          - Upload tax document
GET    /api/tax/documents/{year}          - List documents for year
GET    /api/tax/documents/{year}/{id}     - Get document details
DELETE /api/tax/documents/{year}/{id}     - Delete document
GET    /api/tax/documents/{year}/{id}/download - Download document file

# Document Processing
POST   /api/tax/documents/{id}/parse      - Parse document and extract data
PUT    /api/tax/documents/{id}/extracted  - Update extracted values

# Actual Tax File
GET    /api/tax/actual/{year}             - Get aggregated actual tax data
GET    /api/tax/actual/{year}/comparison  - Compare actual vs forecast
GET    /api/tax/actual/{year}/completeness - Check document completeness
```

---

## User Workflow

### January-April Tax Document Collection (Phase 1)

1. **Receive document** from financial institution (mail or download)
2. **Upload document** to Tax Center via drag-and-drop or file picker
3. **System processes** document:
   - Stores in appropriate folder
   - Attempts to extract key values
   - Creates database record
4. **Review extraction** and correct any parsing errors
5. **System aggregates** all documents into Actual Tax File
6. **Compare** actual vs forecasted values
7. **Identify discrepancies** and investigate
8. **Use Actual Tax File** for tax preparation/filing

---

## Success Metrics

- All tax documents for 2025 uploaded and organized by April 2026
- Actual vs Forecasted comparison available for all income categories
- Zero missing documents at tax filing time
- Document retrieval in under 3 seconds
