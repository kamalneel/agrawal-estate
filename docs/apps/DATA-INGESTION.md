# Data Ingestion App

## Goal

Provide a unified interface for importing financial data from various sources including PDF statements, CSV exports, and manual entry. Handle deduplication and data validation automatically.

---

## Features

### Current Features

1. **File Upload**
   - PDF statement parsing
   - CSV import
   - Drag-and-drop interface
   - Batch upload support

2. **Account Inference**
   - Automatic account detection from filenames
   - Institution identification
   - Account type classification

3. **Data Extraction**
   - Transaction parsing
   - Balance extraction
   - Position identification
   - Date normalization

4. **Deduplication**
   - Duplicate transaction detection
   - Merge conflict resolution
   - Manual override capability

5. **Validation**
   - Data integrity checks
   - Balance reconciliation
   - Error reporting

---

## Roadmap

- [ ] Real-time parsing progress
- [ ] Machine learning for better extraction
- [ ] Email attachment auto-import
- [ ] API integrations with brokerages

---

## Architecture

### Frontend
- **Page:** `/pages/DataIngestion.tsx`
- **Route:** `/data-ingestion`

### Backend
- **Module:** `/backend/app/ingestion/`
- **Parsers:** PDF, CSV, specific institution formats

### Data Model

Key tables:
- `ingestion_jobs` - Upload records
- `ingestion_errors` - Parsing errors
