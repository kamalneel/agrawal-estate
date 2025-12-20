"""
Base parser interface for all file parsers.
All source-specific parsers must implement this interface.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from dataclasses import dataclass
from enum import Enum


class RecordType(Enum):
    """Types of records that can be parsed."""
    TRANSACTION = "transaction"
    HOLDING = "holding"
    DIVIDEND = "dividend"
    ACCOUNT_SUMMARY = "account_summary"
    TAX_RECORD = "tax_record"
    INCOME_ENTRY = "income_entry"
    CASH_SNAPSHOT = "cash_snapshot"


@dataclass
class ParsedRecord:
    """A single parsed record with metadata."""
    record_type: RecordType
    data: dict[str, Any]
    source_row: int  # Row number in source file for debugging


@dataclass
class ParseResult:
    """Result of parsing a file."""
    success: bool
    source_name: str
    file_path: Path
    records: list[ParsedRecord]
    warnings: list[str]
    errors: list[str]
    metadata: dict[str, Any]  # File-level metadata (account info, date range, etc.)


class BaseParser(ABC):
    """
    Abstract base class for all file parsers.
    
    Each financial data source (Robinhood, Schwab, etc.) should have
    its own parser that implements this interface.
    """
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """
        Unique identifier for this data source.
        Examples: 'robinhood', 'schwab', 'county_tax'
        """
        pass
    
    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """
        File extensions this parser can handle.
        Examples: ['.csv'], ['.csv', '.xlsx']
        """
        pass
    
    @abstractmethod
    def can_parse(self, file_path: Path) -> bool:
        """
        Check if this parser can handle the given file.
        
        This should inspect the file contents (headers, structure)
        to determine if it matches the expected format for this source.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            True if this parser can handle the file
        """
        pass
    
    @abstractmethod
    def parse(self, file_path: Path) -> ParseResult:
        """
        Parse the file and return structured records.
        
        Args:
            file_path: Path to the file to parse
            
        Returns:
            ParseResult containing all parsed records and any warnings/errors
        """
        pass
    
    def _read_csv_headers(self, file_path: Path) -> set[str]:
        """
        Utility method to read CSV headers.
        Handles common edge cases like BOM, extra whitespace.
        """
        import csv
        
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            try:
                headers = next(reader)
                return {h.strip() for h in headers}
            except StopIteration:
                return set()
    
    def _normalize_amount(self, value: str) -> float | None:
        """
        Utility method to normalize monetary amounts.
        Handles $, commas, parentheses for negatives.
        """
        if not value or value.strip() == '':
            return None
            
        value = value.strip()
        
        # Handle parentheses as negative
        is_negative = value.startswith('(') and value.endswith(')')
        if is_negative:
            value = value[1:-1]
        
        # Remove currency symbols and commas
        value = value.replace('$', '').replace(',', '').strip()
        
        try:
            amount = float(value)
            return -amount if is_negative else amount
        except ValueError:
            return None

