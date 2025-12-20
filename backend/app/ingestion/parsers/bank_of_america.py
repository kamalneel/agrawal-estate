"""
Bank of America PDF Statement Parser.

Parses Bank of America eStatements to extract:
- Account type (checking, savings)
- Statement date
- Ending balance
"""

import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

from app.ingestion.parsers.base import BaseParser, ParseResult, ParsedRecord, RecordType


class BankOfAmericaParser(BaseParser):
    """
    Parser for Bank of America PDF eStatements.
    
    Bank of America statements contain:
    1. Account type and number
    2. Statement period
    3. Ending balance
    """
    
    source_name = "bank_of_america"
    supported_extensions = [".pdf"]
    
    # Patterns to identify Bank of America statements
    BOA_IDENTIFIERS = [
        "bank of america",
        "bankofamerica",
        "bankofamerica.com",
        "boa.com",
    ]
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if this is a Bank of America PDF statement."""
        if file_path.suffix.lower() != '.pdf':
            return False
        
        try:
            import pdfplumber
            
            with pdfplumber.open(file_path) as pdf:
                if len(pdf.pages) == 0:
                    return False
                
                # Check first page for Bank of America identifiers
                first_page_text = pdf.pages[0].extract_text() or ""
                text_lower = first_page_text.lower()
                
                for identifier in self.BOA_IDENTIFIERS:
                    if identifier in text_lower:
                        return True
                    
        except Exception:
            pass
        
        return False
    
    def parse(self, file_path: Path) -> ParseResult:
        """Parse Bank of America PDF statement and extract balance."""
        import pdfplumber
        
        records = []
        warnings = []
        errors = []
        metadata = {
            "file_type": "pdf_statement",
            "source": "bank_of_america",
        }
        
        try:
            with pdfplumber.open(file_path) as pdf:
                # Extract text from first page
                first_page_text = pdf.pages[0].extract_text() or ""
                
                # Extract account info
                account_type, account_number = self._extract_account_info(first_page_text)
                statement_date = self._extract_statement_date(first_page_text)
                ending_balance = self._extract_ending_balance(first_page_text)
                
                # Try to determine owner from filename
                owner = self._extract_owner_from_filename(file_path.name)
                
                metadata["account_type"] = account_type
                metadata["account_number"] = account_number
                metadata["statement_date"] = statement_date.isoformat() if statement_date else None
                metadata["ending_balance"] = ending_balance
                
                # Create account_id
                account_id = f"boa_{account_number[-4:] if account_number else 'unknown'}"
                
                if statement_date and ending_balance is not None:
                    record_data = {
                        "source": "bank_of_america",
                        "account_id": account_id,
                        "owner": owner,
                        "account_type": account_type,
                        "snapshot_date": statement_date,
                        "balance": ending_balance,
                        "account_number_masked": f"****{account_number[-4:]}" if account_number else None,
                    }
                    
                    records.append(ParsedRecord(
                        record_type=RecordType.CASH_SNAPSHOT,
                        data=record_data,
                        source_row=0
                    ))
                else:
                    if not statement_date:
                        warnings.append("Could not extract statement date from PDF")
                    if ending_balance is None:
                        warnings.append("Could not extract ending balance from PDF")
                
        except ImportError:
            errors.append("pdfplumber library not installed. Run: pip install pdfplumber")
        except Exception as e:
            errors.append(f"Error parsing PDF: {str(e)}")
        
        return ParseResult(
            success=len(errors) == 0 and len(records) > 0,
            source_name=self.source_name,
            file_path=file_path,
            records=records,
            warnings=warnings,
            errors=errors,
            metadata=metadata
        )
    
    def _extract_account_info(self, text: str) -> Tuple[str, Optional[str]]:
        """Extract account type and number from statement text."""
        account_type = "checking"  # Default
        account_number = None
        
        text_lower = text.lower()
        
        # Determine account type - BofA uses specific product names
        if "savings" in text_lower:
            account_type = "savings"
        elif "money market" in text_lower:
            account_type = "money_market"
        elif "adv relationship banking" in text_lower:
            account_type = "checking"
        elif "checking" in text_lower:
            account_type = "checking"
        
        # Try to extract account number
        # BofA format: "Account number: 0004 2776 9486"
        patterns = [
            r'account\s+number\s*:?\s*(\d{4})\s*(\d{4})\s*(\d{4})',  # Format: 0004 2776 9486
            r'account\s*#?\s*:?\s*(\d{8,12})',
            r'account\s+number\s*:?\s*(\d{8,12})',
            r'(\d{4})\s*-\s*(\d{4})\s*-\s*(\d{4})',  # Format: 1234-5678-9012
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                if len(match.groups()) == 3:
                    account_number = ''.join(match.groups())
                else:
                    account_number = match.group(1)
                break
        
        return account_type, account_number
    
    def _extract_statement_date(self, text: str) -> Optional[datetime]:
        """Extract statement ending date from text."""
        # Bank of America specific format: "for October 8, 2025 to November 3, 2025"
        # or "Ending balance on November 3, 2025"
        
        # Pattern 1: "to Month Day, Year" (end of date range)
        pattern1 = r'to\s+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})'
        match = re.search(pattern1, text)
        if match:
            try:
                month_str = match.group(1)
                day = int(match.group(2))
                year = int(match.group(3))
                return datetime.strptime(f"{month_str} {day} {year}", "%B %d %Y")
            except ValueError:
                pass
        
        # Pattern 2: "Ending balance on Month Day, Year"
        pattern2 = r'[Ee]nding\s+balance\s+on\s+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})'
        match = re.search(pattern2, text)
        if match:
            try:
                month_str = match.group(1)
                day = int(match.group(2))
                year = int(match.group(3))
                return datetime.strptime(f"{month_str} {day} {year}", "%B %d %Y")
            except ValueError:
                pass
        
        # Pattern 3: "Month Day, Year - Month Day, Year" or "Month Day, Year through Month Day, Year"
        pattern3 = r'(?:through|-)\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})'
        match = re.search(pattern3, text)
        if match:
            try:
                month_str = match.group(1)
                day = int(match.group(2))
                year = int(match.group(3))
                return datetime.strptime(f"{month_str} {day} {year}", "%B %d %Y")
            except ValueError:
                pass
        
        # Pattern 4: "MM/DD/YYYY - MM/DD/YYYY" or "MM/DD/YYYY through MM/DD/YYYY"
        pattern4 = r'(?:through|to|-)\s*(\d{1,2})/(\d{1,2})/(\d{4})'
        match = re.search(pattern4, text)
        if match:
            try:
                month = int(match.group(1))
                day = int(match.group(2))
                year = int(match.group(3))
                return datetime(year, month, day)
            except ValueError:
                pass
        
        # Pattern 5: Look for "Closing Date" or "Statement Date"
        pattern5 = r'(?:closing|statement)\s+date\s*:?\s*(\d{1,2})/(\d{1,2})/(\d{4})'
        match = re.search(pattern5, text.lower())
        if match:
            try:
                month = int(match.group(1))
                day = int(match.group(2))
                year = int(match.group(3))
                return datetime(year, month, day)
            except ValueError:
                pass
        
        return None
    
    def _extract_ending_balance(self, text: str) -> Optional[float]:
        """Extract ending/closing balance from text."""
        # Bank of America specific: "Ending balance on November 3, 2025 $2,850.03"
        # The balance follows the date
        
        # Pattern 1: "Ending balance on [date] $X,XXX.XX"
        pattern1 = r'[Ee]nding\s+balance\s+on\s+[A-Za-z]+\s+\d{1,2},?\s*\d{4}\s+\$?([\d,]+(?:\.\d{2})?)'
        match = re.search(pattern1, text)
        if match:
            try:
                balance_str = match.group(1).replace(',', '')
                return float(balance_str)
            except ValueError:
                pass
        
        # Look for various balance patterns
        patterns = [
            r'ending\s+balance\s*[:\s]*\$?([\d,]+(?:\.\d{2})?)',
            r'closing\s+balance\s*[:\s]*\$?([\d,]+(?:\.\d{2})?)',
            r'balance\s+(?:on|as\s+of)\s+[^$]*\$?([\d,]+(?:\.\d{2})?)',
            r'(?:your\s+)?ending\s+(?:daily\s+)?balance\s*[:\s]*\$?([\d,]+(?:\.\d{2})?)',
            r'total\s+(?:in\s+)?(?:checking|savings)\s*[:\s]*\$?([\d,]+(?:\.\d{2})?)',
        ]
        
        text_lower = text.lower()
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    balance_str = match.group(1).replace(',', '')
                    balance = float(balance_str)
                    # Sanity check
                    if 0 <= balance <= 100000000:
                        return balance
                except ValueError:
                    continue
        
        return None
    
    def _extract_owner_from_filename(self, filename: str) -> str:
        """Try to extract owner from filename."""
        filename_lower = filename.lower()
        
        if "neel" in filename_lower:
            return "Neel"
        elif "jaya" in filename_lower:
            return "Jaya"
        
        # Default to Joint for bank accounts
        return "Joint"

