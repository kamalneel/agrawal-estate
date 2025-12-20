"""
Chase Bank PDF Statement Parser.

Parses Chase bank statements to extract:
- Account type (checking, savings)
- Statement date
- Ending balance

Handles consolidated statements with multiple accounts.
"""

import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List, Dict

from app.ingestion.parsers.base import BaseParser, ParseResult, ParsedRecord, RecordType


class ChaseParser(BaseParser):
    """
    Parser for Chase Bank PDF statements.
    
    Chase statements can be:
    1. Single account statements
    2. Consolidated statements showing multiple accounts
    
    This parser handles both formats.
    """
    
    source_name = "chase"
    supported_extensions = [".pdf"]
    
    # Patterns to identify Chase statements
    CHASE_IDENTIFIERS = [
        "chase",
        "jpmorgan chase",
        "chase.com",
        "chase bank",
    ]
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if this is a Chase PDF statement."""
        if file_path.suffix.lower() != '.pdf':
            return False
        
        # Check filename first - Chase statements often have specific naming
        filename_lower = file_path.name.lower()
        if "chase" in filename_lower or filename_lower.startswith("statement"):
            pass
        
        try:
            import pdfplumber
            
            with pdfplumber.open(file_path) as pdf:
                if len(pdf.pages) == 0:
                    return False
                
                # Check first page for Chase identifiers
                first_page_text = pdf.pages[0].extract_text() or ""
                text_lower = first_page_text.lower()
                
                for identifier in self.CHASE_IDENTIFIERS:
                    if identifier in text_lower:
                        return True
                    
        except Exception:
            pass
        
        return False
    
    def parse(self, file_path: Path) -> ParseResult:
        """Parse Chase PDF statement and extract balances for all accounts."""
        import pdfplumber
        
        records = []
        warnings = []
        errors = []
        metadata = {
            "file_type": "pdf_statement",
            "source": "chase",
        }
        
        try:
            with pdfplumber.open(file_path) as pdf:
                # Extract text from all pages
                full_text = ""
                for page in pdf.pages[:5]:  # Check first 5 pages
                    full_text += (page.extract_text() or "") + "\n"
                
                # Extract statement date
                statement_date = self._extract_statement_date(full_text, file_path.name)
                
                # Try to determine owner from filename or content
                owner = self._extract_owner_from_text(full_text, file_path.name)
                
                # Check if this is a consolidated statement
                if "consolidated balance summary" in full_text.lower():
                    # Extract multiple accounts from consolidated statement
                    accounts = self._extract_consolidated_accounts(full_text)
                    
                    for acc in accounts:
                        if statement_date and acc.get('balance') is not None:
                            record_data = {
                                "source": "chase",
                                "account_id": f"chase_{acc['account_last4']}",
                                "owner": owner,
                                "account_type": acc['account_type'],
                                "snapshot_date": statement_date,
                                "balance": acc['balance'],
                                "account_number_masked": f"****{acc['account_last4']}",
                            }
                            
                            records.append(ParsedRecord(
                                record_type=RecordType.CASH_SNAPSHOT,
                                data=record_data,
                                source_row=0
                            ))
                    
                    metadata["consolidated"] = True
                    metadata["accounts_found"] = len(accounts)
                else:
                    # Single account statement
                    account_type, account_number = self._extract_account_info(full_text)
                    ending_balance = self._extract_ending_balance(full_text)
                    
                    metadata["account_type"] = account_type
                    metadata["account_number"] = account_number
                    metadata["ending_balance"] = ending_balance
                    
                    # Create account_id
                    if account_number:
                        account_id = f"chase_{account_number[-4:]}"
                    else:
                        match = re.search(r'statements?-(\d{4})', file_path.name.lower())
                        if match:
                            account_id = f"chase_{match.group(1)}"
                        else:
                            account_id = f"chase_unknown"
                    
                    if statement_date and ending_balance is not None:
                        record_data = {
                            "source": "chase",
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
                
                metadata["statement_date"] = statement_date.isoformat() if statement_date else None
                
                if not records:
                    if not statement_date:
                        warnings.append("Could not extract statement date from PDF")
                    warnings.append("Could not extract any account balances from PDF")
                
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
    
    def _extract_consolidated_accounts(self, text: str) -> List[Dict]:
        """
        Extract multiple accounts from Chase consolidated balance summary.
        
        Format:
        CONSOLIDATED BALANCE SUMMARY
        Checking & Savings ACCOUNT BEGINNING BALANCE ENDING BALANCE
        THIS PERIOD THIS PERIOD
        Chase Premier Plus Checking 000000101725973 $9,054.68 $9,054.76
        Chase Premier Savings 000003733333059 5,358.84 1,968.41
        Total $14,413.52 $11,023.17
        """
        accounts = []
        
        # Pattern for account lines in consolidated summary
        # Format: "Account Name AccountNumber BeginBal EndBal"
        # Example: "Chase Premier Plus Checking 000000101725973 $9,054.68 $9,054.76"
        # Example: "Chase Premier Savings 000003733333059 5,358.84 1,968.41"
        
        patterns = [
            # Pattern with $ on both amounts
            r'(Chase\s+(?:Premier\s+)?(?:Plus\s+)?(?:Checking|Savings|Money\s+Market))\s+(\d{12,15})\s+\$?([\d,]+\.?\d*)\s+\$?([\d,]+\.?\d*)',
            # Pattern without $ symbols
            r'(Chase\s+(?:Premier\s+)?(?:Plus\s+)?(?:Checking|Savings|Money\s+Market))\s+(\d{12,15})\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                account_name = match[0].strip()
                account_number = match[1].strip()
                # beginning_balance = match[2]
                ending_balance_str = match[3].replace(',', '')
                
                # Determine account type from name
                if 'savings' in account_name.lower():
                    account_type = 'savings'
                elif 'money market' in account_name.lower():
                    account_type = 'money_market'
                else:
                    account_type = 'checking'
                
                try:
                    ending_balance = float(ending_balance_str)
                    
                    # Get last 4 digits
                    account_last4 = account_number[-4:]
                    
                    # Check if we already have this account
                    existing = [a for a in accounts if a['account_last4'] == account_last4]
                    if not existing:
                        accounts.append({
                            'account_name': account_name,
                            'account_number': account_number,
                            'account_last4': account_last4,
                            'account_type': account_type,
                            'balance': ending_balance,
                        })
                except ValueError:
                    continue
        
        return accounts
    
    def _extract_account_info(self, text: str) -> Tuple[str, Optional[str]]:
        """Extract account type and number from statement text."""
        account_type = "checking"  # Default
        account_number = None
        
        text_lower = text.lower()
        
        # Determine account type
        if "savings" in text_lower:
            account_type = "savings"
        elif "money market" in text_lower:
            account_type = "money_market"
        elif "total checking" in text_lower or "checking" in text_lower:
            account_type = "checking"
        
        # Try to extract account number
        patterns = [
            r'account\s*(?:number|#)?\s*:?\s*\.{0,3}(\d{4})',
            r'ending\s+in\s+(\d{4})',
            r'account\s+\*+(\d{4})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                account_number = match.group(1)
                break
        
        return account_type, account_number
    
    def _extract_statement_date(self, text: str, filename: str) -> Optional[datetime]:
        """Extract statement ending date from text or filename."""
        # First try to extract from text - more reliable
        
        # Pattern 1: "throughNovember 19, 2025" (Chase often removes the space)
        pattern1 = r'through\s*([A-Za-z]+)\s*(\d{1,2}),?\s*(\d{4})'
        match = re.search(pattern1, text, re.IGNORECASE)
        if match:
            try:
                month_str = match.group(1)
                day = int(match.group(2))
                year = int(match.group(3))
                return datetime.strptime(f"{month_str} {day} {year}", "%B %d %Y")
            except ValueError:
                pass
        
        # Pattern 2: "Statement Period: Month Day - Month Day, Year"
        pattern2 = r'statement\s+period[:\s]+[A-Za-z]+\s+\d{1,2}\s*[-–]\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})'
        match = re.search(pattern2, text, re.IGNORECASE)
        if match:
            try:
                month_str = match.group(1)
                day = int(match.group(2))
                year = int(match.group(3))
                return datetime.strptime(f"{month_str} {day} {year}", "%B %d %Y")
            except ValueError:
                pass
        
        # Pattern 3: "MM/DD/YYYY through MM/DD/YYYY"
        pattern3 = r'through\s+(\d{1,2})/(\d{1,2})/(\d{4})'
        match = re.search(pattern3, text)
        if match:
            try:
                month = int(match.group(1))
                day = int(match.group(2))
                year = int(match.group(3))
                return datetime(year, month, day)
            except ValueError:
                pass
        
        # Fallback: Try filename - Chase uses format like "20251119-statements-3059-.pdf"
        # But be careful - processed files have timestamp prefix like "20251127_225423_20251119-..."
        # So look for the pattern AFTER any processing prefix
        filename_match = re.search(r'(\d{4})(\d{2})(\d{2})-statements', filename)
        if filename_match:
            try:
                year = int(filename_match.group(1))
                month = int(filename_match.group(2))
                day = int(filename_match.group(3))
                return datetime(year, month, day)
            except ValueError:
                pass
        
        return None
    
    def _extract_ending_balance(self, text: str) -> Optional[float]:
        """Extract ending/closing balance from text (for single account statements)."""
        patterns = [
            r'ending\s+balance\s*[:\s]*\$?([\d,]+(?:\.\d{2})?)',
            r'closing\s+balance\s*[:\s]*\$?([\d,]+(?:\.\d{2})?)',
            r'balance\s+on\s+[^$]*\$?([\d,]+(?:\.\d{2})?)',
            r'total\s+(?:in\s+)?(?:checking|savings)\s*\$?([\d,]+(?:\.\d{2})?)',
            r'(?:your\s+)?(?:new\s+)?(?:ending\s+)?balance\s*\$?([\d,]+(?:\.\d{2})?)',
            r'ending\s+balance\s+\$?([\d,]+(?:\.\d{2})?)',
        ]
        
        text_lower = text.lower()
        
        for pattern in patterns:
            matches = re.findall(pattern, text_lower)
            if matches:
                try:
                    balance_str = matches[-1].replace(',', '')
                    balance = float(balance_str)
                    if 0 <= balance <= 100000000:
                        return balance
                except ValueError:
                    continue
        
        return None
    
    def _extract_owner_from_text(self, text: str, filename: str) -> str:
        """Try to extract owner from text or filename."""
        # Check filename first
        filename_lower = filename.lower()
        if "neel" in filename_lower:
            return "Neel"
        elif "jaya" in filename_lower:
            return "Jaya"
        
        # Check text for trust/family name
        if "kamal family" in text.lower() or "neel kamal" in text.lower() or "jaya agrawal" in text.lower():
            return "Joint"
        
        return "Joint"
