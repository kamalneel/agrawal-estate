"""
Robinhood PDF Statement Parser.

Extracts the month-end **Account Summary** from a Robinhood statement as one
ACCOUNT_SUMMARY record per account section: the statement's own Portfolio
Value, Total Securities and cash lines, dated the statement period end.
That is the authoritative month-end value for `portfolio_snapshots`
(docs/BBD-CALCULATIONS.md, "Portfolio value") and, for margin accounts, the
signed brokerage cash line that feeds `margin_monthly_balances`.

Everything else on a statement (holdings, transactions, dividends) is not
read here — those come from the MCP refresh and activity CSVs. Income rows
from statements are handled by `backend/scripts/import_robinhood_statement_pdf.py`.

History: until 2026-09-25 this parser returned nothing ("Robinhood PDFs
provide no value"), which is why 2026 had no statement month-ends and the
BBD page ran on securities-only daily rows (BBD audit F1).
"""

import re
from pathlib import Path
from datetime import datetime
from typing import Any, Optional, Tuple
from decimal import Decimal

from app.ingestion.parsers.base import BaseParser, ParseResult, ParsedRecord, RecordType


#: Statement account number → app account. Statements print the RHS account
#: number; Neel's brokerage also appears as 5XE31773 in the trading API.
#: Untracked accounts (Alisha's, the joint account, the Agentic and Airbnb
#: cash accounts) are deliberately absent: a statement for one of them is
#: reported and skipped, never written under the wrong account.
STATEMENT_ACCOUNTS = {
    "701552176": ("jaya_brokerage", "Jaya", "brokerage"),
    "534052659": ("jaya_ira", "Jaya", "ira"),
    "704155779": ("jaya_roth_ira", "Jaya", "roth_ira"),
    "170317739": ("neel_brokerage", "Neel", "brokerage"),
    "5XE31773": ("neel_brokerage", "Neel", "brokerage"),
    "439569591": ("neel_retirement", "Neel", "retirement"),
    "514429901": ("neel_roth_ira", "Neel", "roth_ira"),
}

#: securities + cash must reproduce the printed Portfolio Value this closely,
#: or the file is rejected (playbook: validate a parser against the source
#: document's own totals).
TOTALS_TOLERANCE = 1.00


class RobinhoodPDFParser(BaseParser):
    """
    Parser for Robinhood PDF account statements.

    Robinhood statements contain:
    1. Account holder name on page 1
    2. Account type and number on page 1
    3. Account Summary (Portfolio Value / Total Securities / cash lines) on page 1
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
        """One ACCOUNT_SUMMARY record per account section found in the PDF.

        A section is any page carrying an "<type> Account #:<number>" header
        together with an Account Summary block. Statements are normally one
        account per file; the loop also handles combined files.
        """
        import pdfplumber

        records: list[ParsedRecord] = []
        warnings: list[str] = []
        errors: list[str] = []
        metadata: dict[str, Any] = {"file_type": "pdf_statement", "source": "robinhood", "accounts": []}

        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                header = re.search(
                    r'(Individual|Traditional IRA|Roth IRA|Retirement)\s+Account\s*#[:\s]*([A-Z0-9]+)', text)
                if not header or 'Portfolio Value' not in text:
                    continue

                account_number = header.group(2)
                period_end = self._extract_statement_date(text)
                summary = self._extract_account_summary(text)
                label = f"{file_path.name} p{page_num + 1} account #{account_number}"

                mapped = STATEMENT_ACCOUNTS.get(account_number)
                if not mapped:
                    warnings.append(
                        f"{label}: not a tracked account (closing value "
                        f"{summary.get('portfolio_value')}); skipped")
                    continue
                account_id, owner, account_type = mapped

                if period_end is None or summary.get("portfolio_value") is None:
                    errors.append(f"{label}: could not read statement period or Portfolio Value")
                    continue

                pv = summary["portfolio_value"]
                sec = summary.get("securities_value")
                cash = summary.get("cash_balance")
                if sec is not None and cash is not None and abs((sec + cash) - pv) > TOTALS_TOLERANCE:
                    errors.append(
                        f"{label}: Total Securities {sec:,.2f} + cash {cash:,.2f} = {sec + cash:,.2f} "
                        f"does not match Portfolio Value {pv:,.2f}; file rejected")
                    continue

                data = {
                    "source": self.source_name,
                    "account_id": account_id,
                    "owner": owner,
                    "account_type": account_type,
                    "account_number": account_number,
                    "statement_date": period_end.date(),
                    "portfolio_value": pv,
                    "cash_balance": cash,
                    "securities_value": sec,
                }
                if account_type == "brokerage":
                    # Signed "Brokerage Cash Balance" line (negative = margin) for margin_monthly_balances
                    data["brokerage_cash_opening"] = summary.get("brokerage_cash_opening")
                    data["brokerage_cash_closing"] = summary.get("brokerage_cash_closing")
                records.append(ParsedRecord(record_type=RecordType.ACCOUNT_SUMMARY, data=data, source_row=page_num + 1))
                metadata["accounts"].append({"account_id": account_id, "statement_date": period_end.date().isoformat(),
                                             "portfolio_value": pv})

        if not records and not errors:
            warnings.append(f"{file_path.name}: no tracked account summary found")

        return ParseResult(
            success=not errors,
            source_name=self.source_name,
            file_path=file_path,
            records=records,
            warnings=warnings,
            errors=errors,
            metadata=metadata,
        )

    # Amounts print as "$1,234.56" or "($1,234.56)" (negative, e.g. margin).
    _AMOUNT = re.compile(r'(\()?\$([\d,]+\.\d{2})(\))?')

    def _amounts(self, line: str) -> list:
        out = []
        for open_p, num, close_p in self._AMOUNT.findall(line):
            v = float(num.replace(',', ''))
            out.append(-v if (open_p and close_p) else v)
        return out

    def _extract_account_summary(self, text: str) -> dict:
        """Closing-balance column of the Account Summary block.

        Brokerage:  cash = Brokerage Cash Balance (signed) + Deposit Sweep Balance
        IRA:        cash = Net Account Balance
        Each line prints "Opening Closing"; the closing value is the last amount.
        """
        out: dict[str, Any] = {}
        sweep = None
        for raw in text.split('\n'):
            line = raw.strip()
            amts = self._amounts(line)
            if not amts:
                continue
            if line.startswith('Portfolio Value'):
                out["portfolio_value"] = amts[-1] if len(amts) >= 2 else amts[0]
            elif line.startswith('Total Securities'):
                out["securities_value"] = amts[-1] if len(amts) >= 2 else amts[0]
            elif line.startswith('Brokerage Cash Balance'):
                out["brokerage_cash_opening"] = amts[0] if len(amts) >= 2 else None
                out["brokerage_cash_closing"] = amts[-1] if len(amts) >= 2 else amts[0]
            elif line.startswith('Deposit Sweep Balance'):
                sweep = amts[-1] if len(amts) >= 2 else amts[0]
            elif line.startswith('Net Account Balance'):
                out["cash_balance"] = amts[-1] if len(amts) >= 2 else amts[0]
        if "brokerage_cash_closing" in out:
            out["cash_balance"] = out["brokerage_cash_closing"] + (sweep or 0.0)
        return out
    
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
