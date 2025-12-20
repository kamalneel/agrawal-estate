"""
Robinhood CSV parser.

Handles Robinhood export formats:
- Transaction history CSV
- Portfolio/holdings CSV
"""

import csv
import re
from pathlib import Path
from datetime import datetime
from typing import Any, Optional

from app.ingestion.parsers.base import BaseParser, ParseResult, ParsedRecord, RecordType


class RobinhoodParser(BaseParser):
    """
    Parser for Robinhood CSV exports.
    
    Robinhood provides several export types:
    1. Transaction History - All buys, sells, dividends
    2. Account Statement - Monthly/yearly summaries
    
    Account inference from filename:
    - "Jaya IRA" → jaya_ira
    - "Jaya Retirement" → jaya_retirement  
    - "Jaya Investment/Brokerage" → jaya_brokerage
    - "Neel Retirement" → neel_retirement
    - "Neel Investment/Individual/Brokerage" → neel_brokerage
    - "Alisha" → alisha_brokerage
    """
    
    source_name = "robinhood"
    supported_extensions = [".csv"]
    
    # Column patterns for different Robinhood export types
    TRANSACTION_COLUMNS = {
        "Activity Date", "Process Date", "Settle Date", 
        "Instrument", "Description", "Trans Code",
        "Quantity", "Price", "Amount"
    }
    
    HOLDINGS_COLUMNS = {
        "Symbol", "Quantity", "Average Cost", "Market Value"
    }
    
    # Filename patterns to account ID mapping
    # ORDER MATTERS - most specific patterns first!
    # 
    # Strategy for handling varied naming conventions:
    # 1. "Roth" anywhere → Roth IRA (most specific, check first)
    # 2. "non-retirement" or brokerage terms → Brokerage (check before IRA/retirement)
    # 3. "IRA" or "Retirement" → Traditional IRA
    #
    # Examples that will work:
    # - "Neel's Roth IRA Dec 2025.csv" → neel_roth_ira
    # - "Neel Roth.csv" → neel_roth_ira  
    # - "Neel's IRA.csv" → neel_retirement
    # - "Neel retirement Dec.csv" → neel_retirement
    # - "Neel's Individual.csv" → neel_brokerage
    # - "Neel Primary Account.csv" → neel_brokerage
    # - "Neel non-retirement.csv" → neel_brokerage
    # - "Neel Investment Nov Statement.csv" → neel_brokerage
    #
    ACCOUNT_PATTERNS = [
        # === NEEL ACCOUNTS ===
        # 1. Roth IRA - "roth" anywhere (most specific, check first)
        # Handle both "neel" and "neal" spellings
        (r"(neel|neal).*roth", "neel_roth_ira"),
        # 2. Brokerage - check BEFORE ira/retirement to catch "non-retirement"
        (r"(neel|neal).*(individual|investment|brokerage|primary|non.?retirement|taxable)", "neel_brokerage"),
        # 3. Traditional IRA - "ira" or "retirement" (but not roth)
        (r"(neel|neal).*(ira|retirement)", "neel_retirement"),
        
        # === JAYA ACCOUNTS ===
        # 1. Roth IRA
        (r"jaya.*roth", "jaya_roth_ira"),
        # 2. Brokerage
        (r"jaya.*(individual|investment|brokerage|primary|non.?retirement|taxable)", "jaya_brokerage"),
        # 3. Traditional IRA
        (r"jaya.*(ira|retirement)", "jaya_ira"),
        
        # === ALISHA ACCOUNTS ===
        # 1. Roth IRA
        (r"alisha.*roth", "alisha_roth_ira"),
        # 2. Brokerage
        (r"alisha.*(individual|investment|brokerage|primary|non.?retirement|taxable)", "alisha_brokerage"),
        # 3. Traditional IRA
        (r"alisha.*(ira|retirement)", "alisha_ira"),
        # 4. Default for Alisha (just name with no specifier)
        (r"alisha", "alisha_brokerage"),
    ]
    
    def _infer_account_from_filename(self, file_path: Path) -> str:
        """
        Infer the account ID from the filename.
        
        Examples:
        - "Jaya IRA.csv" → "jaya_ira"
        - "Neel Investment Nov Statement.csv" → "neel_brokerage"
        - "Alisha Investment.csv" → "alisha_brokerage"
        
        Returns "robinhood_default" if no pattern matches.
        """
        filename = file_path.stem.lower()  # Get filename without extension, lowercase
        
        for pattern, account_id in self.ACCOUNT_PATTERNS:
            if re.search(pattern, filename):
                return account_id
        
        return "robinhood_default"
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if file matches Robinhood format."""
        if file_path.suffix.lower() not in self.supported_extensions:
            return False
            
        headers = self._read_csv_headers(file_path)
        
        # Check for transaction format
        if self.TRANSACTION_COLUMNS.issubset(headers):
            return True
            
        # Check for holdings format
        if self.HOLDINGS_COLUMNS.issubset(headers):
            return True
            
        return False
    
    def parse(self, file_path: Path) -> ParseResult:
        """Parse Robinhood CSV file."""
        headers = self._read_csv_headers(file_path)
        
        # Infer account from filename
        account_id = self._infer_account_from_filename(file_path)
        
        if self.TRANSACTION_COLUMNS.issubset(headers):
            return self._parse_transactions(file_path, account_id)
        elif self.HOLDINGS_COLUMNS.issubset(headers):
            return self._parse_holdings(file_path, account_id)
        else:
            return ParseResult(
                success=False,
                source_name=self.source_name,
                file_path=file_path,
                records=[],
                warnings=[],
                errors=["Unrecognized Robinhood file format"],
                metadata={}
            )
    
    def _parse_transactions(self, file_path: Path, account_id: str) -> ParseResult:
        """Parse Robinhood transaction history CSV."""
        records = []
        warnings = []
        errors = []
        
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            
            for row_num, row in enumerate(reader, start=2):  # Start at 2 (1 = header)
                try:
                    record = self._parse_transaction_row(row, row_num, account_id)
                    if record:
                        records.append(record)
                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")
        
        # Consider success if we got any records, even with some errors
        return ParseResult(
            success=len(records) > 0,
            source_name=self.source_name,
            file_path=file_path,
            records=records,
            warnings=warnings + errors,  # Move errors to warnings if we still have records
            errors=[] if len(records) > 0 else errors,
            metadata={
                "file_type": "transaction_history",
                "record_count": len(records),
                "error_count": len(errors),
                "account_id": account_id
            }
        )
    
    def _parse_transaction_row(self, row: dict[str, Any], row_num: int, account_id: str) -> ParsedRecord | None:
        """Parse a single transaction row."""
        raw_trans_code = row.get("Trans Code")
        if raw_trans_code is None:
            return None
        trans_code = raw_trans_code.strip().upper()
        
        # Skip empty trans codes
        if trans_code == "":
            return None
        
        # Map Robinhood trans codes to our types
        # Include ALL transaction types for proper income tracking
        trans_type_map = {
            # Stock transactions
            "BUY": "BUY",
            "SELL": "SELL",
            # Dividend types
            "DIV": "DIVIDEND",
            "CDIV": "DIVIDEND",  # Cash dividend
            "DIVNRA": "DIVIDEND",  # Dividend NRA tax
            # Options transactions - preserve original codes for income tracking
            "STO": "STO",   # Sell To Open (options income)
            "BTC": "BTC",   # Buy To Close (options cost)
            "OEXP": "OEXP", # Option Expiration
            "OASGN": "OASGN", # Options assignment
            "OEXCS": "OEXCS", # Options exercise
            # Interest and other income
            "INT": "INTEREST",
            "SLIP": "SLIP",  # Stock Lending Income Program
            # Other types
            "SPL": "SPLIT",
            "ACH": "TRANSFER",
            "DRFRO": "TRANSFER",  # Direct Rollover
            "FUTSWP": "TRANSFER",  # Event Contracts Inter-Entity Cash Transfer
        }
        
        trans_type = trans_type_map.get(trans_code, "OTHER")
        
        # Determine record type
        if trans_type == "DIVIDEND":
            record_type = RecordType.DIVIDEND
        else:
            record_type = RecordType.TRANSACTION
        
        # Parse date - safely handle None values
        date_str = (row.get("Activity Date") or "").strip()
        try:
            transaction_date = datetime.strptime(date_str, "%m/%d/%Y").date() if date_str else None
        except ValueError:
            transaction_date = None
        
        # Skip rows without valid dates (likely footer rows)
        if not transaction_date:
            return None
        
        # Normalize symbol - use empty string consistently for non-stock transactions
        symbol = (row.get("Instrument") or "").strip().upper()
        if symbol in ("", "UNKNOWN", "N/A", "-"):
            symbol = ""  # Normalize to empty string for consistency
        
        data = {
            "source": self.source_name,
            "account_id": account_id,  # Inferred from filename
            "transaction_date": transaction_date,
            "transaction_type": trans_type,
            "symbol": symbol,
            "description": (row.get("Description") or "").strip(),
            "quantity": self._normalize_amount(row.get("Quantity") or ""),
            "price_per_share": self._normalize_amount(row.get("Price") or ""),
            "amount": self._normalize_amount(row.get("Amount") or ""),
        }
        
        return ParsedRecord(
            record_type=record_type,
            data=data,
            source_row=row_num
        )
    
    def _parse_holdings(self, file_path: Path, account_id: str) -> ParseResult:
        """Parse Robinhood holdings/portfolio CSV."""
        records = []
        warnings = []
        errors = []
        
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            
            for row_num, row in enumerate(reader, start=2):
                try:
                    symbol = (row.get("Symbol") or "").strip().upper()
                    # Skip empty rows
                    if not symbol:
                        continue
                        
                    data = {
                        "source": self.source_name,
                        "account_id": account_id,  # Inferred from filename
                        "symbol": symbol,
                        "quantity": self._normalize_amount(row.get("Quantity") or ""),
                        "cost_basis": self._normalize_amount(row.get("Average Cost") or ""),
                        "market_value": self._normalize_amount(row.get("Market Value") or ""),
                    }
                    
                    records.append(ParsedRecord(
                        record_type=RecordType.HOLDING,
                        data=data,
                        source_row=row_num
                    ))
                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")
        
        return ParseResult(
            success=len(errors) == 0,
            source_name=self.source_name,
            file_path=file_path,
            records=records,
            warnings=warnings,
            errors=errors,
            metadata={
                "file_type": "holdings",
                "record_count": len(records),
                "account_id": account_id
            }
        )

