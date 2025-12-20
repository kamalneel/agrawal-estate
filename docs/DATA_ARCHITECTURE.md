# Data Architecture & Best Practices

## Overview

This document covers data sources, integrity rules, deduplication strategies, and management patterns for the Agrawal Estate Planner.

---

## Critical Rule: No Direct Database Modifications

**NEVER modify data directly in the database.** All data changes must come from one of the three authoritative sources.

If you (the AI assistant) are asked to directly insert, update, or delete records, you MUST:

1. **STOP and alert the user** with this message:
   > ⚠️ **Data Integrity Warning**: You're asking me to modify the database directly. Per our data integrity best practices, all data should come from an authoritative source. Would you like to:
   > 1. Upload a PDF statement
   > 2. Process a CSV transaction file
   > 3. Use the copy-paste parser in the UI

2. **Only proceed with direct modification** if explicitly confirmed AND it's for:
   - Fixing a bug in previously ingested data
   - Deleting duplicate/erroneous records
   - Emergency data recovery

---

## Three Authoritative Data Sources

### 1. PDF/CSV Account Statements
**Source of Truth for:** Historical Portfolio Values, Cost Basis, Cash Balance

| Data | Update Frequency | Notes |
|------|------------------|-------|
| Historical Portfolio Value | Monthly | Official month-end value |
| Cost Basis | Monthly | For tax purposes |
| Cash Balance | Monthly | Accurate cash position |

**How to Import:** Upload via Data Import page or drop in `/data/inbox/investments/`

### 2. Activity Report CSV
**Source of Truth for:** Transactions (STO, BTC, Dividends, Buy/Sell)

| Data | Update Frequency | Notes |
|------|------------------|-------|
| STO (Sell to Open) | As needed | Options sold |
| BTC (Buy to Close) | As needed | Options bought back |
| Dividends | Quarterly | Dividend payments |
| Buy/Sell Orders | As needed | Stock transactions |

**How to Import:** Upload activity CSV via Data Import page

### 3. Robinhood Paste (Copy from App)
**Source of Truth for:** Current Holdings & Options Status (Real-Time)

| Data | Update Frequency | Notes |
|------|------------------|-------|
| Current Holdings | Real-time | Symbols, quantities, prices |
| Market Values | Real-time | Calculated from shares × price |
| Options Status | Real-time | Which options are open/closed |

**What it updates:**
- ✅ `investment_holdings` table (symbol, quantity, price)
- ✅ `sold_options` table (options status)
- ✅ `portfolio_snapshots` with current date
- ✅ Removes holdings no longer in account

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                   AUTHORITATIVE SOURCES                      │
├─────────────────┬─────────────────┬─────────────────────────┤
│  PDF Statement  │  CSV Exports    │  Copy-Paste from RH     │
│  (Monthly)      │  (Transactions) │  (Real-time)            │
└────────┬────────┴────────┬────────┴────────────┬────────────┘
         │                 │                      │
         ▼                 ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    INGESTION LAYER                           │
│  • Parsers validate and normalize data                       │
│  • Creates ingestion_log entry (provenance)                  │
│  • Deduplication checks                                      │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                      DATABASE                                │
│  • investment_holdings     • investment_transactions         │
│  • portfolio_snapshots     • sold_options                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Live Price Architecture

The system uses **Yahoo Finance for live prices** instead of storing prices from paste data.

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Robinhood      │     │    Database     │     │  Yahoo Finance  │
│  Paste          │────▶│  (shares only)  │     │  (live prices)  │
└─────────────────┘     └────────┬────────┘     └────────┬────────┘
                                 │                       │
                                 ▼                       ▼
                        ┌────────────────────────────────────────┐
                        │          /holdings/live API            │
                        │  market_value = shares × live_price    │
                        └────────────────────────────────────────┘
```

**API Endpoint:** `GET /api/v1/investments/holdings/live`

---

## Deduplication Strategies

### 1. Composite Natural Keys (Primary Defense)

Use **composite unique constraints** on natural key fields:

```python
__table_args__ = (
    UniqueConstraint(
        'source', 'account_id', 'transaction_date', 
        'transaction_type', 'symbol', 'quantity', 'amount',
        name='uq_investment_transaction'
    ),
)
```

**Field Selection for Different Record Types:**

| Record Type | Natural Key Fields |
|-------------|-------------------|
| Investment Transaction | source, account_id, date, type, symbol, quantity, amount |
| Dividend | source, account_id, date, amount |
| Cash Transaction | account_id, date, description, amount |
| Portfolio Snapshot | source, account_id, statement_date |
| Holding | source, account_id, symbol |

### 2. Cross-Account Deduplication

For exports without account information, check across ALL accounts:

```python
cross_account_existing = db.query(InvestmentTransaction).filter(
    InvestmentTransaction.source == source,
    InvestmentTransaction.transaction_date == transaction_date,
    InvestmentTransaction.symbol.in_(symbol_variants),
    InvestmentTransaction.transaction_type == transaction_type,
    InvestmentTransaction.amount == amount,
).first()

# Migration pattern
if cross_account_existing.account_id in ["robinhood_default"] and account_id not in ["robinhood_default"]:
    cross_account_existing.account_id = account_id  # Migrate to specific account
```

### 3. Pre-Save Duplicate Check Pattern

```python
def save_investment_transaction(db, record, ingestion_id=None):
    # 1. Check exact duplicate using natural key
    existing = db.query(InvestmentTransaction).filter(...).first()
    if existing:
        return "skipped"
    
    # 2. Check cross-account duplicate
    cross_account_existing = db.query(InvestmentTransaction).filter(...).first()
    if cross_account_existing:
        return "skipped" or "updated"
    
    # 3. Create new record
    try:
        db.add(transaction)
        db.flush()
        return "created"
    except IntegrityError:
        db.rollback()
        return "skipped"
```

---

## Account Linkage Patterns

### Account ID Convention

Use `{owner}_{account_type}` format:

```
neel_brokerage      # Neel's brokerage/individual account
neel_retirement     # Neel's traditional IRA
neel_roth_ira       # Neel's Roth IRA
jaya_ira            # Jaya's traditional IRA
jaya_brokerage      # Jaya's brokerage
```

### Filename-Based Account Inference

```python
# Order matters! Most specific patterns first
ACCOUNT_PATTERNS = [
    (r"neel.*roth", "neel_roth_ira"),
    (r"neel.*(individual|investment|brokerage)", "neel_brokerage"),
    (r"neel.*(ira|retirement)", "neel_retirement"),
]
```

---

## Data Normalization

### Transaction Type Normalization

```python
TRANS_TYPE_NORMALIZATION = {
    "DIV": "DIVIDEND",
    "CDIV": "DIVIDEND",
    "CASH DIVIDEND": "DIVIDEND",
    "INT": "INTEREST",
    "BANK INTEREST": "INTEREST",
    "STO": "STO",
    "BTC": "BTC",
}
```

### Amount Normalization

```python
def _normalize_amount(self, value):
    # Handle parentheses as negative: (100.00) → -100.00
    is_negative = value.startswith('(') and value.endswith(')')
    if is_negative:
        value = value[1:-1]
    
    # Remove currency symbols and commas
    value = value.replace('$', '').replace(',', '').strip()
    amount = float(value)
    return -amount if is_negative else amount
```

### Date Normalization

```python
def _parse_date(self, date_str):
    formats = ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%B %d, %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None
```

---

## Common Pitfalls & Solutions

| Pitfall | Problem | Solution |
|---------|---------|----------|
| **Dividend Double-Counting** | Same dividend as "CDIV" and "DIVIDEND" | Normalize types, dedupe on amount + date |
| **Options Premium Double-Counting** | STO from both CSV and statement | Include symbol in dedup key (option symbols unique) |
| **Holdings Overwritten to Zero** | Import overwrites unmentioned holdings | Only update/create holdings that appear, don't delete |
| **Account Misattribution** | Generic export to wrong account | Filename-based inference + cross-account dedup |
| **Brokerage Cash Double-Counting** | Cash counted in both portfolio and Cash & Savings | Only include bank cash in Cash & Savings |

---

## Cleanup Script Patterns

### Dry Run by Default

```python
def cleanup_duplicates(dry_run: bool = True):
    if dry_run:
        print("DRY RUN - No changes made")
        print("Run with --execute to actually delete")
```

### Show Before/After Stats

```python
before = conn.execute("SELECT COUNT(*), SUM(amount) FROM transactions WHERE ...")
# Execute cleanup
after = conn.execute("SELECT COUNT(*), SUM(amount) FROM transactions WHERE ...")
print(f"Removed: {before.count - after.count} duplicates")
```

---

## File Processing Workflow

### Directory Structure

```
data/
├── inbox/              # Drop files here for processing
│   ├── investments/
│   │   ├── robinhood/
│   │   ├── schwab/
│   │   └── fidelity/
│   ├── income/
│   ├── tax/
│   └── cash/
├── processed/          # Successfully processed files
├── failed/             # Files that failed processing
└── documents/          # Permanent document storage
```

---

## Quick Reference

| Data Type | Authoritative Source | Location |
|-----------|---------------------|----------|
| Holdings (current) | PDF Statement | `/data/inbox/investments/*/` |
| Transactions | CSV Export | `/data/inbox/investments/*/` |
| Options positions | Copy-paste or PDF | UI or inbox |
| Cash balances | PDF Statement | `/data/inbox/investments/*/` |
| Dividends | CSV Export | `/data/inbox/investments/*/` |

---

*Last Updated: December 2025*

