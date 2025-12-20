"""
Charles Schwab CSV parser.

Handles Schwab export formats:
- Transaction history
- Positions/holdings
- Account summary
"""

import csv
from pathlib import Path
from datetime import datetime
from typing import Any

from app.ingestion.parsers.base import BaseParser, ParseResult, ParsedRecord, RecordType


class SchwabParser(BaseParser):
    """
    Parser for Charles Schwab CSV exports.
    
    Schwab CSVs have some quirks:
    - First few rows often contain account info (need to skip)
    - Multiple sections in one file sometimes
    - Different column names than other brokers
    """
    
    source_name = "schwab"
    supported_extensions = [".csv"]
    
    # Schwab uses different column names
    TRANSACTION_COLUMNS = {
        "Date", "Action", "Symbol", "Description", 
        "Quantity", "Price", "Amount"
    }
    
    POSITIONS_COLUMNS = {
        "Symbol", "Description", "Quantity", "Price", 
        "Market Value", "Cost Basis"
    }
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if file matches Schwab format."""
        if file_path.suffix.lower() not in self.supported_extensions:
            return False
        
        # Schwab files often have metadata rows at top
        # Try to find header row
        headers = self._find_headers(file_path)
        
        if self.TRANSACTION_COLUMNS.issubset(headers):
            return True
        if self.POSITIONS_COLUMNS.issubset(headers):
            return True
            
        return False
    
    def _find_headers(self, file_path: Path) -> set[str]:
        """
        Find header row in Schwab file.
        Schwab sometimes puts account info in first rows.
        """
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            # Check first 10 rows for headers
            for i, line in enumerate(f):
                if i >= 10:
                    break
                    
                # Try to parse as CSV
                parts = line.strip().split(',')
                headers = {p.strip().strip('"') for p in parts}
                
                # Check if this looks like a header row
                if any(col in headers for col in ["Symbol", "Date", "Action", "Description"]):
                    return headers
        
        return set()
    
    def parse(self, file_path: Path) -> ParseResult:
        """Parse Schwab CSV file."""
        headers = self._find_headers(file_path)
        
        if self.TRANSACTION_COLUMNS.issubset(headers):
            return self._parse_transactions(file_path)
        elif self.POSITIONS_COLUMNS.issubset(headers):
            return self._parse_positions(file_path)
        else:
            return ParseResult(
                success=False,
                source_name=self.source_name,
                file_path=file_path,
                records=[],
                warnings=[],
                errors=["Unrecognized Schwab file format"],
                metadata={}
            )
    
    def _parse_transactions(self, file_path: Path) -> ParseResult:
        """Parse Schwab transaction history."""
        records = []
        warnings = []
        errors = []
        
        # Find where data starts
        header_row = self._find_header_row_number(file_path)
        
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            # Skip to header row
            for _ in range(header_row):
                next(f)
            
            reader = csv.DictReader(f)
            
            for row_num, row in enumerate(reader, start=header_row + 2):
                try:
                    record = self._parse_transaction_row(row, row_num)
                    if record:
                        records.append(record)
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
                "file_type": "transaction_history",
                "record_count": len(records)
            }
        )
    
    def _find_header_row_number(self, file_path: Path) -> int:
        """Find the row number containing headers."""
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            for i, line in enumerate(f):
                if "Symbol" in line or "Date" in line and "Action" in line:
                    return i
        return 0
    
    def _parse_transaction_row(self, row: dict[str, Any], row_num: int) -> ParsedRecord | None:
        """Parse a single Schwab transaction row."""
        action = row.get("Action", "").strip()
        
        # Skip empty or total rows
        if not action or "Total" in action:
            return None
        
        # Map Schwab actions to our types
        action_map = {
            "Buy": "BUY",
            "Sell": "SELL",
            "Reinvest Dividend": "DIVIDEND",
            "Cash Dividend": "DIVIDEND",
            "Qual Div Reinvest": "DIVIDEND",
            "Stock Split": "SPLIT",
            "Journal": "TRANSFER",
            "Wire Funds": "TRANSFER",
            "MoneyLink Transfer": "TRANSFER",
        }
        
        trans_type = action_map.get(action, "OTHER")
        
        # Determine record type
        if "Dividend" in action:
            record_type = RecordType.DIVIDEND
        else:
            record_type = RecordType.TRANSACTION
        
        # Parse date - Schwab uses various formats
        date_str = row.get("Date", "").strip()
        transaction_date = None
        for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"]:
            try:
                transaction_date = datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue
        
        data = {
            "source": self.source_name,
            "account_id": "schwab_default",  # Could extract from filename or file header
            "transaction_date": transaction_date,
            "transaction_type": trans_type,
            "symbol": row.get("Symbol", "").strip().upper(),
            "description": row.get("Description", "").strip(),
            "quantity": self._normalize_amount(row.get("Quantity", "")),
            "price_per_share": self._normalize_amount(row.get("Price", "")),
            "amount": self._normalize_amount(row.get("Amount", "")),
            "fees": self._normalize_amount(row.get("Fees & Comm", "")),
        }
        
        return ParsedRecord(
            record_type=record_type,
            data=data,
            source_row=row_num
        )
    
    def _parse_positions(self, file_path: Path) -> ParseResult:
        """Parse Schwab positions/holdings file."""
        records = []
        warnings = []
        errors = []
        
        header_row = self._find_header_row_number(file_path)
        
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            for _ in range(header_row):
                next(f)
            
            reader = csv.DictReader(f)
            
            for row_num, row in enumerate(reader, start=header_row + 2):
                symbol = row.get("Symbol", "").strip()
                
                # Skip empty or cash rows
                if not symbol or symbol in ("Cash", "Account Total"):
                    continue
                
                try:
                    data = {
                        "source": self.source_name,
                        "account_id": "schwab_default",
                        "symbol": symbol.upper(),
                        "description": row.get("Description", "").strip(),
                        "quantity": self._normalize_amount(row.get("Quantity", "")),
                        "current_price": self._normalize_amount(row.get("Price", "")),
                        "market_value": self._normalize_amount(row.get("Market Value", "")),
                        "cost_basis": self._normalize_amount(row.get("Cost Basis", "")),
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
                "file_type": "positions",
                "record_count": len(records)
            }
        )

