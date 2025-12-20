"""
Robinhood PDF Statement Parser.

Parses Robinhood monthly/quarterly statements to extract:
- Account information (owner, type)
- Current holdings/positions
- Account value summary
"""

import re
from pathlib import Path
from datetime import datetime
from typing import Any, Optional, Tuple
from decimal import Decimal

from app.ingestion.parsers.base import BaseParser, ParseResult, ParsedRecord, RecordType


class RobinhoodPDFParser(BaseParser):
    """
    Parser for Robinhood PDF account statements.
    
    Robinhood statements contain:
    1. Account holder name on page 1
    2. Account type and number on page 1
    3. Portfolio Summary table on page 3+
    """
    
    source_name = "robinhood"
    supported_extensions = [".pdf"]
    
    # Patterns to identify Robinhood statements
    ROBINHOOD_IDENTIFIERS = [
        "robinhood",
        "robinhood securities",
        "robinhood financial",
        "500 colonial center parkway",
        "lake mary, fl",
    ]
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if this is a Robinhood PDF statement."""
        if file_path.suffix.lower() != '.pdf':
            return False
        
        try:
            import pdfplumber
            
            with pdfplumber.open(file_path) as pdf:
                if len(pdf.pages) == 0:
                    return False
                
                # Check first page for Robinhood identifiers
                first_page_text = pdf.pages[0].extract_text() or ""
                text_lower = first_page_text.lower()
                
                for identifier in self.ROBINHOOD_IDENTIFIERS:
                    if identifier in text_lower:
                        return True
                    
        except Exception:
            pass
        
        return False
    
    def parse(self, file_path: Path) -> ParseResult:
        """Parse Robinhood PDF statement and extract holdings."""
        import pdfplumber
        
        records = []
        warnings = []
        errors = []
        metadata = {
            "file_type": "pdf_statement",
            "source": "robinhood",
        }
        
        try:
            with pdfplumber.open(file_path) as pdf:
                # MULTI-ACCOUNT SUPPORT: Scan all pages for account headers
                # A single PDF may contain multiple accounts (e.g., IRA + Roth IRA)
                accounts = self._detect_accounts_in_pdf(pdf)
                
                # Get statement date from first page
                first_page_text = pdf.pages[0].extract_text() or ""
                statement_date = self._extract_statement_date(first_page_text)
                
                # Get owner from filename if not in PDF
                owner_from_file, type_from_file = self._parse_filename(file_path.name)
                
                # If no accounts detected, fall back to single-account mode
                if not accounts:
                    owner, account_type, account_number = self._extract_account_info(first_page_text)
                    if owner == "Unknown":
                        owner = owner_from_file
                    if account_type == "brokerage" and type_from_file != "brokerage":
                        account_type = type_from_file
                    
                    portfolio_value, cash_balance, securities_value = self._extract_portfolio_values(first_page_text)
                    accounts = [{
                        "owner": owner,
                        "account_type": account_type,
                        "account_number": account_number,
                        "start_page": 0,
                        "end_page": len(pdf.pages),
                        "portfolio_value": portfolio_value,
                        "cash_balance": cash_balance,
                    }]
                
                metadata["owner"] = accounts[0]["owner"] if accounts else "Unknown"
                metadata["account_type"] = accounts[0]["account_type"] if accounts else "brokerage"
                metadata["account_number"] = accounts[0].get("account_number", "")
                metadata["accounts_found"] = len(accounts)
                
                total_holdings = 0
                
                # Process each account separately
                for acct in accounts:
                    owner = acct["owner"]
                    if owner == "Unknown":
                        owner = owner_from_file
                    
                    account_type = acct["account_type"]
                    account_number = acct.get("account_number", "")
                    
                    # Create unique account_id for each account type
                    if account_type == "roth_ira":
                        account_id = f"{owner.lower()}_roth_ira"
                        account_name = f"{owner}'s Roth IRA"
                    elif account_type == "ira" or account_type == "traditional_ira":
                        account_id = f"{owner.lower()}_ira"
                        account_name = f"{owner}'s IRA"
                    elif account_type == "brokerage":
                        account_id = f"{owner.lower()}_brokerage"
                        account_name = f"{owner}'s Brokerage"
                    else:
                        account_id = f"{owner.lower()}_{account_type}"
                        account_name = f"{owner}'s {account_type.replace('_', ' ').title()}"
                    
                    # Extract holdings for this account's page range
                    holdings = self._extract_holdings_from_page_range(
                        pdf, acct["start_page"], acct["end_page"]
                    )
                    
                    # Create records for each holding
                    for holding in holdings:
                        if self._is_option(holding.get("symbol", "")):
                            continue
                        
                        record_data = {
                            "source": "robinhood",
                            "account_name": account_name,
                            "account_id": account_id,
                            "owner": owner,
                            "account_type": account_type,
                            "symbol": holding["symbol"],
                            "quantity": holding["quantity"],
                            "name": holding.get("name"),
                            "description": holding.get("name"),
                            "market_value": holding.get("market_value"),
                            "current_price": holding.get("price"),
                            "as_of_date": statement_date,
                            "statement_date": statement_date,
                        }
                        
                        records.append(ParsedRecord(
                            record_type=RecordType.HOLDING,
                            data=record_data,
                            source_row=0
                        ))
                        total_holdings += 1
                    
                    # Get portfolio value - from detected account or calculate from holdings
                    portfolio_value = acct.get("portfolio_value", 0)
                    cash_balance = acct.get("cash_balance")
                    calculated_value = sum(h.get("market_value", 0) or 0 for h in holdings)
                    
                    if not portfolio_value and calculated_value > 0:
                        portfolio_value = calculated_value
                    
                    # If portfolio value includes cash + securities, use the higher value
                    if portfolio_value and calculated_value > portfolio_value:
                        portfolio_value = calculated_value
                    
                    # Create account summary record
                    if statement_date and portfolio_value:
                        summary_data = {
                            "source": "robinhood",
                            "account_id": account_id,
                            "owner": owner,
                            "account_type": account_type,
                            "statement_date": statement_date,
                            "portfolio_value": portfolio_value,
                            "cash_balance": cash_balance,
                            "securities_value": calculated_value,
                        }
                        records.append(ParsedRecord(
                            record_type=RecordType.ACCOUNT_SUMMARY,
                            data=summary_data,
                            source_row=0
                        ))
                    metadata["statement_date"] = statement_date.isoformat()
                    metadata["portfolio_value"] = portfolio_value
                
                if len([r for r in records if r.record_type == RecordType.HOLDING]) == 0:
                    warnings.append("No holdings found in PDF. The account may be empty or the format is not recognized.")
                
                metadata["holdings_count"] = len([r for r in records if r.record_type == RecordType.HOLDING])
                
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
    
    def _extract_account_info(self, text: str) -> Tuple[str, str, str]:
        """Extract owner name, account type, and account number from first page text."""
        owner = "Unknown"
        account_type = "brokerage"
        account_number = ""
        
        lines = text.split('\n')
        
        # Known family member names to look for
        known_names = {
            'NEEL': 'Neel',
            'JAYA': 'Jaya',
            'ALICIA': 'Alicia',
            'KAMAL': 'Neel',  # Neel Kamal
            'AGRAWAL': None,  # Last name, need first name
        }
        
        for i, line in enumerate(lines[:25]):  # Check first 25 lines
            line = line.strip()
            
            # Check if line contains a known name anywhere (handles "help@robinhood.com Neel Kamal")
            line_upper = line.upper()
            for name_key, name_value in known_names.items():
                if name_key in line_upper and name_value:
                    owner = name_value
                    break
            
            # Look for names in ALL CAPS format (e.g., "JAYA AGRAWAL", "NEEL KAMAL")
            words = line.split()
            if 2 <= len(words) <= 3:
                # Check if all words are uppercase and alphabetic
                if all(w.isupper() and w.isalpha() for w in words):
                    first_word = words[0]
                    if first_word in known_names and known_names[first_word]:
                        owner = known_names[first_word]
                    elif len(words) >= 2 and words[0].isalpha():
                        # Use first name, title-cased
                        owner = words[0].title()
            
            # Also check for "Firstname Lastname" format (mixed case)
            elif 2 <= len(words) <= 3 and all(w.isalpha() for w in words):
                if all(w[0].isupper() for w in words):
                    first_word = words[0].upper()
                    if first_word in known_names and known_names[first_word]:
                        owner = known_names[first_word]
                    elif not any(x in line.lower() for x in ['page', 'account', 'summary', 'portfolio', 'colonial', 'center']):
                        owner = words[0].title()
            
            # Look for account type and number
            if 'Individual Account' in line:
                account_type = "brokerage"
                match = re.search(r'#[:\s]*(\d+)', line)
                if match:
                    account_number = match.group(1)
            elif 'Traditional IRA' in line or 'IRA Account' in line:
                account_type = "ira"
                match = re.search(r'#[:\s]*(\d+)', line)
                if match:
                    account_number = match.group(1)
            elif 'Roth IRA' in line:
                account_type = "roth_ira"
                match = re.search(r'#[:\s]*(\d+)', line)
                if match:
                    account_number = match.group(1)
            elif 'Retirement' in line:
                account_type = "retirement"
                match = re.search(r'#[:\s]*(\d+)', line)
                if match:
                    account_number = match.group(1)
        
        return owner, account_type, account_number
    
    def _extract_first_name(self, full_name: str) -> str:
        """Extract first name and normalize it."""
        parts = full_name.strip().split()
        if parts:
            first_name = parts[0].title()
            # Map common variations
            name_map = {
                'Neel': 'Neel',
                'Jaya': 'Jaya',
                'Alicia': 'Alicia',
            }
            return name_map.get(first_name, first_name)
        return "Unknown"
    
    def _parse_filename(self, filename: str) -> Tuple[str, str]:
        """Extract owner and account type from filename as fallback."""
        filename_lower = filename.lower()
        
        owner = "Unknown"
        if "neel" in filename_lower:
            owner = "Neel"
        elif "jaya" in filename_lower:
            owner = "Jaya"
        elif "alicia" in filename_lower:
            owner = "Alicia"
        
        account_type = "brokerage"
        if "ira" in filename_lower or "retirement" in filename_lower:
            account_type = "ira"
        elif "401k" in filename_lower:
            account_type = "retirement"
        
        return owner, account_type
    
    def _detect_accounts_in_pdf(self, pdf) -> list:
        """
        Detect multiple accounts in a single PDF.
        Returns list of account info dicts with page ranges.
        """
        accounts = []
        
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            
            # Look for account type indicators
            account_info = None
            
            # Check for Roth IRA Account header
            if re.search(r'Roth\s+IRA\s+Account\s*#[:\s]*(\d+)', text, re.IGNORECASE):
                match = re.search(r'Roth\s+IRA\s+Account\s*#[:\s]*(\d+)', text, re.IGNORECASE)
                account_info = {
                    "account_type": "roth_ira",
                    "account_number": match.group(1) if match else "",
                    "start_page": page_num,
                }
            # Check for Traditional IRA Account header
            elif re.search(r'Traditional\s+IRA\s+Account\s*#[:\s]*(\d+)', text, re.IGNORECASE):
                match = re.search(r'Traditional\s+IRA\s+Account\s*#[:\s]*(\d+)', text, re.IGNORECASE)
                account_info = {
                    "account_type": "ira",
                    "account_number": match.group(1) if match else "",
                    "start_page": page_num,
                }
            # Check for Individual Account header (brokerage)
            elif re.search(r'Individual\s+Account\s*#[:\s]*(\d+)', text, re.IGNORECASE):
                match = re.search(r'Individual\s+Account\s*#[:\s]*(\d+)', text, re.IGNORECASE)
                account_info = {
                    "account_type": "brokerage",
                    "account_number": match.group(1) if match else "",
                    "start_page": page_num,
                }
            
            if account_info:
                # Extract owner from page
                owner, _, _ = self._extract_account_info(text)
                account_info["owner"] = owner
                
                # Extract portfolio values from this page
                portfolio_value, cash_balance, _ = self._extract_portfolio_values(text)
                account_info["portfolio_value"] = portfolio_value
                account_info["cash_balance"] = cash_balance
                
                # Close the previous account's page range
                if accounts:
                    accounts[-1]["end_page"] = page_num
                
                accounts.append(account_info)
        
        # Set end_page for the last account
        if accounts:
            accounts[-1]["end_page"] = len(pdf.pages)
        
        return accounts
    
    def _extract_holdings_from_page_range(self, pdf, start_page: int, end_page: int) -> list:
        """Extract holdings from a specific page range (for multi-account PDFs)."""
        holdings = []
        found_portfolio_section = False
        
        for page_num in range(start_page, end_page):
            if page_num >= len(pdf.pages):
                break
            
            page = pdf.pages[page_num]
            text = page.extract_text() or ""
            
            # Check if this is a portfolio summary page
            is_portfolio_page = "Portfolio Summary" in text or "Securities Held" in text
            
            if is_portfolio_page:
                found_portfolio_section = True
            
            # Parse holdings from relevant pages
            if is_portfolio_page or (found_portfolio_section and self._has_stock_data(text)):
                page_holdings = self._parse_holdings_text(text)
                holdings.extend(page_holdings)
            
            # Stop if we've moved to transaction history
            if found_portfolio_section and "Transaction History" in text and len(holdings) > 0:
                break
        
        return holdings
    
    def _extract_holdings_from_pages(self, pdf) -> list:
        """Extract holdings from Portfolio Summary pages."""
        holdings = []
        found_portfolio_section = False
        
        # Search all pages for portfolio summary / holdings
        for page_num, page in enumerate(pdf.pages[1:], start=2):  # Start from page 2
            text = page.extract_text() or ""
            
            # Check if this is a portfolio summary page
            is_portfolio_page = "Portfolio Summary" in text or "Securities Held" in text
            
            if is_portfolio_page:
                found_portfolio_section = True
            
            # Parse holdings from any page that might have them
            # Look for stock symbol patterns even without "Portfolio Summary" header
            if is_portfolio_page or (found_portfolio_section and self._has_stock_data(text)):
                page_holdings = self._parse_holdings_text(text)
                holdings.extend(page_holdings)
            
            # Stop if we've moved to transaction history
            if found_portfolio_section and "Transaction History" in text and len(holdings) > 0:
                break
        
        return holdings
    
    def _has_stock_data(self, text: str) -> bool:
        """Check if text contains stock holding data."""
        # Look for patterns like "SYMBOL Margin QTY"
        import re
        return bool(re.search(r'[A-Z]{2,5}\s+(?:Margin|Cash)\s+[\d,]+', text))
    
    def _parse_holdings_text(self, text: str) -> list:
        """Parse holdings from portfolio summary text."""
        holdings = []
        lines = text.split('\n')
        
        current_name = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Skip headers and page info
            if any(x in line for x in ['Page ', 'Portfolio Summary', 'Securities Held', 'Sym/Cusip', 'Est. Dividend']):
                continue
            
            # Check if this is a company name line (text without numbers at start)
            if self._is_company_name_line(line):
                current_name = line
                continue
            
            # Try to parse as a holdings line
            # Format: "SYMBOL Margin QTY $PRICE $VALUE ..."
            holding = self._parse_holding_line(line, current_name)
            if holding:
                holdings.append(holding)
                current_name = None  # Reset after using
        
        return holdings
    
    def _is_company_name_line(self, line: str) -> bool:
        """Check if line is a company name (no $ or numbers at start)."""
        # Company names don't start with $ or numbers
        if line[0].isdigit() or line.startswith('$') or line.startswith('-'):
            return False
        
        # Should be mostly letters
        alpha_chars = sum(1 for c in line if c.isalpha())
        if alpha_chars < len(line) * 0.5:
            return False
        
        # Skip if it looks like a symbol line (has Margin or specific price patterns)
        if 'Margin' in line or re.search(r'\$\d+\.\d+', line):
            return False
        
        # Skip option descriptions
        if re.search(r'\d{1,2}/\d{1,2}/\d{4}', line):  # Date pattern
            return False
        
        return True
    
    def _parse_holding_line(self, line: str, company_name: str = None) -> Optional[dict]:
        """
        Parse a holdings line.
        Formats:
          1. "SYMBOL Margin QTY $PRICE $VALUE ..." (symbol at start)
          2. "Company Name SYMBOL Margin QTY $PRICE $VALUE ..." (name then symbol)
        """
        # Pattern 1: Symbol at start of line
        pattern1 = r'^([A-Z]{1,5})\s+(?:Margin|Cash)\s+([\d,]+(?:\.\d+)?)\s+\$([\d,]+\.\d+)\s+\$([\d,]+\.\d+)'
        
        # Pattern 2: Company name then symbol (e.g., "Apple AAPL Margin 100 $270.37 $27,037.00")
        pattern2 = r'^(.+?)\s+([A-Z]{1,5})\s+(?:Margin|Cash)\s+([\d,]+(?:\.\d+)?)\s+\$([\d,]+\.\d+)\s+\$([\d,]+\.\d+)'
        
        # Try pattern 1 first (symbol at start)
        match = re.match(pattern1, line)
        if match:
            symbol = match.group(1)
            quantity = self._parse_number(match.group(2))
            price = self._parse_number(match.group(3))
            market_value = self._parse_number(match.group(4))
            
            if quantity and quantity > 0:
                return {
                    "symbol": symbol,
                    "name": company_name,
                    "quantity": quantity,
                    "price": price,
                    "market_value": market_value,
                }
        
        # Try pattern 2 (name then symbol)
        match = re.match(pattern2, line)
        if match:
            name_from_line = match.group(1).strip()
            symbol = match.group(2)
            quantity = self._parse_number(match.group(3))
            price = self._parse_number(match.group(4))
            market_value = self._parse_number(match.group(5))
            
            if quantity and quantity > 0:
                return {
                    "symbol": symbol,
                    "name": name_from_line or company_name,
                    "quantity": quantity,
                    "price": price,
                    "market_value": market_value,
                }
        
        return None
    
    def _is_option(self, symbol: str) -> bool:
        """Check if this is an option position (has date in name)."""
        # Options have format like "AAPL 11/07/2025 Call $267.50"
        return bool(re.search(r'\d{1,2}/\d{1,2}/\d{4}', symbol))
    
    def _parse_number(self, value: str) -> Optional[float]:
        """Parse a number from string, handling commas."""
        if not value:
            return None
        
        cleaned = value.replace(',', '').replace('$', '').strip()
        
        try:
            return float(cleaned)
        except ValueError:
            return None
    
    def _extract_statement_date(self, text: str) -> Optional[datetime]:
        """Extract statement end date from first page text."""
        # Look for date range pattern: "10/01/2025 to 10/31/2025"
        pattern = r'(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})'
        match = re.search(pattern, text)
        if match:
            try:
                # Use the end date of the statement period
                end_date_str = match.group(2)
                return datetime.strptime(end_date_str, "%m/%d/%Y")
            except ValueError:
                pass
        return None
    
    def _extract_portfolio_values(self, text: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Extract portfolio value, cash balance, and securities value from first page.
        
        Returns: (portfolio_value, cash_balance, securities_value)
        """
        portfolio_value = None
        cash_balance = None
        securities_value = None
        
        lines = text.split('\n')
        
        for line in lines:
            # Portfolio Value - look for closing balance (second value)
            # Format: "Portfolio Value $664,743.03 $681,962.55"
            if 'Portfolio Value' in line:
                # Extract all dollar amounts from the line
                amounts = re.findall(r'\$([\d,]+(?:\.\d+)?)', line)
                if len(amounts) >= 2:
                    # Use the closing balance (second value)
                    portfolio_value = self._parse_number(amounts[1])
                elif len(amounts) == 1:
                    portfolio_value = self._parse_number(amounts[0])
            
            # Total Securities value
            if 'Total Securities' in line:
                amounts = re.findall(r'\$([\d,]+(?:\.\d+)?)', line)
                if len(amounts) >= 2:
                    securities_value = self._parse_number(amounts[1])
                elif len(amounts) == 1:
                    securities_value = self._parse_number(amounts[0])
            
            # Cash/Deposit Sweep Balance
            if 'Deposit Sweep' in line or 'Brokerage Cash' in line:
                amounts = re.findall(r'\$([\d,]+(?:\.\d+)?)', line)
                if len(amounts) >= 2:
                    # Add to cash balance
                    val = self._parse_number(amounts[1])
                    if val:
                        cash_balance = (cash_balance or 0) + val
                elif len(amounts) == 1:
                    val = self._parse_number(amounts[0])
                    if val:
                        cash_balance = (cash_balance or 0) + val
        
        return portfolio_value, cash_balance, securities_value
