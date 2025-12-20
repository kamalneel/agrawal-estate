"""
Generic CSV parser for unrecognized formats.

This parser is used as a fallback when no specific parser matches.
It attempts to intelligently map columns to our schema.
"""

import csv
from pathlib import Path
from datetime import datetime
from typing import Any

from app.ingestion.parsers.base import BaseParser, ParseResult, ParsedRecord, RecordType


class GenericCSVParser(BaseParser):
    """
    Generic CSV parser for files that don't match known formats.
    
    Uses heuristics to detect column meanings based on names.
    """
    
    source_name = "generic"
    supported_extensions = [".csv"]
    
    # Common column name patterns
    DATE_COLUMNS = {"date", "transaction date", "activity date", "trade date", "settle date"}
    SYMBOL_COLUMNS = {"symbol", "ticker", "stock", "instrument"}
    AMOUNT_COLUMNS = {"amount", "value", "total", "net amount", "proceeds"}
    QUANTITY_COLUMNS = {"quantity", "qty", "shares", "units"}
    TYPE_COLUMNS = {"type", "action", "trans code", "transaction type", "activity"}
    DESCRIPTION_COLUMNS = {"description", "desc", "memo", "notes"}
    PRICE_COLUMNS = {"price", "share price", "unit price", "price per share"}
    
    def can_parse(self, file_path: Path) -> bool:
        """Generic parser can attempt to parse any CSV."""
        return file_path.suffix.lower() == ".csv"
    
    def parse(self, file_path: Path) -> ParseResult:
        """Parse CSV using column heuristics."""
        records = []
        warnings = []
        errors = []
        
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            headers = {h.lower().strip(): h for h in reader.fieldnames or []}
            
            # Map detected columns
            column_map = self._detect_columns(headers)
            
            if not column_map:
                return ParseResult(
                    success=False,
                    source_name=self.source_name,
                    file_path=file_path,
                    records=[],
                    warnings=[],
                    errors=["Could not detect any recognizable columns"],
                    metadata={}
                )
            
            warnings.append(f"Using generic parser with column mapping: {column_map}")
            
            for row_num, row in enumerate(reader, start=2):
                try:
                    record = self._parse_row(row, column_map, row_num)
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
                "file_type": "generic_csv",
                "column_mapping": column_map,
                "record_count": len(records)
            }
        )
    
    def _detect_columns(self, headers: dict[str, str]) -> dict[str, str]:
        """Detect which columns map to which fields."""
        mapping = {}
        
        for pattern_set, field_name in [
            (self.DATE_COLUMNS, "date"),
            (self.SYMBOL_COLUMNS, "symbol"),
            (self.AMOUNT_COLUMNS, "amount"),
            (self.QUANTITY_COLUMNS, "quantity"),
            (self.TYPE_COLUMNS, "type"),
            (self.DESCRIPTION_COLUMNS, "description"),
            (self.PRICE_COLUMNS, "price"),
        ]:
            for header_lower, header_original in headers.items():
                if header_lower in pattern_set:
                    mapping[field_name] = header_original
                    break
        
        return mapping
    
    def _parse_row(self, row: dict[str, Any], column_map: dict[str, str], row_num: int) -> ParsedRecord | None:
        """Parse a row using the detected column mapping."""
        
        # Try to parse date
        transaction_date = None
        if "date" in column_map:
            date_str = row.get(column_map["date"], "").strip()
            for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d/%m/%Y"]:
                try:
                    transaction_date = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue
        
        data = {
            "source": self.source_name,
            "account_id": "generic",
            "transaction_date": transaction_date,
            "transaction_type": row.get(column_map.get("type", ""), "UNKNOWN").strip().upper() if "type" in column_map else "UNKNOWN",
            "symbol": row.get(column_map.get("symbol", ""), "").strip().upper() if "symbol" in column_map else "",
            "description": row.get(column_map.get("description", ""), "").strip() if "description" in column_map else "",
            "quantity": self._normalize_amount(row.get(column_map.get("quantity", ""), "")) if "quantity" in column_map else None,
            "price_per_share": self._normalize_amount(row.get(column_map.get("price", ""), "")) if "price" in column_map else None,
            "amount": self._normalize_amount(row.get(column_map.get("amount", ""), "")) if "amount" in column_map else None,
        }
        
        return ParsedRecord(
            record_type=RecordType.TRANSACTION,
            data=data,
            source_row=row_num
        )

