"""
Schwab PDF Statement Parser.

Parses Schwab/Fidelity HSA monthly statements to extract:
- Account information (owner, type, nickname)
- Current holdings/positions
- Account value summary
"""

import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple
from decimal import Decimal

from app.ingestion.parsers.base import BaseParser, ParseResult, ParsedRecord, RecordType


class SchwabPDFParser(BaseParser):
    """
    Parser for Schwab PDF account statements.
    Also handles Fidelity HSA statements that are administered by Schwab.
    """
    
    source_name = "schwab"
    supported_extensions = [".pdf", ".PDF"]
    
    # Patterns to identify Schwab statements
    SCHWAB_IDENTIFIERS = [
        "schwab",
        "schwab.com",
        "charles schwab",
        "schwab one",
    ]
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if this is a Schwab PDF statement."""
        if file_path.suffix.lower() != '.pdf':
            return False
        
        try:
            import pdfplumber
            
            with pdfplumber.open(file_path) as pdf:
                if len(pdf.pages) == 0:
                    return False
                
                # Check first page for Schwab identifiers
                first_page_text = pdf.pages[0].extract_text() or ""
                text_lower = first_page_text.lower()
                
                for identifier in self.SCHWAB_IDENTIFIERS:
                    if identifier in text_lower:
                        return True
                    
        except Exception:
            pass
        
        return False
    
    def parse(self, file_path: Path) -> ParseResult:
        """Parse Schwab PDF statement and extract holdings."""
        import pdfplumber
        
        records = []
        warnings = []
        errors = []
        metadata = {
            "file_type": "pdf_statement",
            "source": "schwab",
        }
        
        try:
            with pdfplumber.open(file_path) as pdf:
                # Extract account info from first page
                first_page_text = pdf.pages[0].extract_text() or ""
                
                owner, account_name, account_number = self._extract_account_info(first_page_text)
                statement_date = self._extract_statement_date(first_page_text)
                portfolio_value = self._extract_portfolio_value(first_page_text)
                
                # Determine account type from name
                account_type = self._determine_account_type(account_name, first_page_text)
                
                # Create account_id
                account_id = f"{owner.lower()}_{account_type}" if owner != "Unknown" else f"schwab_{account_type}"
                
                metadata["owner"] = owner
                metadata["account_name"] = account_name
                metadata["account_type"] = account_type
                metadata["account_number"] = account_number
                
                # Extract holdings from all pages
                holdings = []
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    page_holdings = self._extract_holdings(page_text)
                    holdings.extend(page_holdings)
                
                # Extract cash balance
                cash_balance = self._extract_cash_balance(first_page_text)
                
                # Deduplicate holdings (same symbol might appear in summary and detail)
                seen_symbols = set()
                unique_holdings = []
                for h in holdings:
                    if h["symbol"] not in seen_symbols:
                        seen_symbols.add(h["symbol"])
                        unique_holdings.append(h)
                
                # Add cash as a holding if we have cash
                if cash_balance and cash_balance > 0:
                    unique_holdings.append({
                        "symbol": "CASH",
                        "name": "Cash & Cash Investments",
                        "quantity": Decimal(str(cash_balance)),
                        "price": Decimal("1.00"),
                        "market_value": Decimal(str(cash_balance)),
                    })
                
                # Create holding records
                for holding in unique_holdings:
                    record_data = {
                        "source": "schwab",
                        "account_id": account_id,
                        "owner": owner,
                        "account_type": account_type,
                        "symbol": holding["symbol"],
                        "quantity": holding["quantity"],
                        "description": holding.get("name"),
                        "market_value": holding.get("market_value"),
                        "current_price": holding.get("price"),
                        "statement_date": statement_date,
                    }
                    
                    records.append(ParsedRecord(
                        record_type=RecordType.HOLDING,
                        data=record_data,
                        source_row=0
                    ))
                
                # Calculate portfolio value from holdings if not found on page 1
                if not portfolio_value and holdings:
                    portfolio_value = sum(h.get("market_value", 0) or 0 for h in unique_holdings)
                
                # Create portfolio snapshot record
                if statement_date and portfolio_value:
                    summary_data = {
                        "source": "schwab",
                        "account_id": account_id,
                        "owner": owner,
                        "account_type": account_type,
                        "statement_date": statement_date,
                        "portfolio_value": portfolio_value,
                    }
                    records.append(ParsedRecord(
                        record_type=RecordType.ACCOUNT_SUMMARY,
                        data=summary_data,
                        source_row=0
                    ))
                    metadata["statement_date"] = statement_date.isoformat()
                    metadata["portfolio_value"] = portfolio_value
                
                metadata["holdings_count"] = len(unique_holdings)
                
                if not unique_holdings:
                    warnings.append("No holdings found in PDF.")
                
        except ImportError:
            errors.append("pdfplumber library not installed.")
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
        """Extract owner name, account name, and account number."""
        owner = "Unknown"
        account_name = ""
        account_number = ""
        
        lines = text.split('\n')
        for line in lines[:20]:
            # Look for account number pattern
            match = re.search(r'(\d{4}-\d{4})', line)
            if match:
                account_number = match.group(1)
        
        # Try to find account name from "Account of" or nickname patterns
        match = re.search(r"Account\s*of\s*AccountNickname\s*(\w+(?:'s)?\w*)", text, re.IGNORECASE)
        if match:
            account_name = match.group(1).strip()
        
        # Also check for specific patterns like "Alisha'sAccount"
        match = re.search(r"(\w+)'s\s*Account", text)
        if match:
            name_part = match.group(1)
            account_name = f"{name_part}'s Account"
            
            # If account name contains a person's name, that's the owner
            name_upper = name_part.upper()
            if name_upper in ["ALICIA", "ALISHA"]:
                owner = "Alisha"
            elif name_upper == "NEEL":
                owner = "Neel"
            elif name_upper == "JAYA":
                owner = "Jaya"
        
        # If owner still unknown, look for names in the text
        if owner == "Unknown":
            text_upper = text.upper()
            # Look for name patterns, but prioritize account nickname over legal name
            for line in text.split('\n')[:15]:
                line_upper = line.upper()
                if "NEEL" in line_upper and "KAMAL" in line_upper:
                    # This is likely the legal owner, not necessarily the beneficial owner
                    # Don't override if we found a name from the account nickname
                    if owner == "Unknown":
                        owner = "Neel"
        
        return owner, account_name, account_number
    
    def _extract_statement_date(self, text: str) -> Optional[datetime]:
        """Extract statement end date."""
        # Look for "October 1-31, 2025" or "StatementPeriod October1-31,2025"
        patterns = [
            r'(?:Statement\s*Period\s*)?(\w+)\s*(\d{1,2})\s*[-–]\s*(\d{1,2})\s*,\s*(\d{4})',
            r'(\w+)\s*(\d{1,2})\s*[-–]\s*(\d{1,2})\s*,\s*(\d{4})',
        ]
        
        months = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                month_name = match.group(1).lower()
                end_day = int(match.group(3))
                year = int(match.group(4))
                
                if month_name in months:
                    return datetime(year, months[month_name], end_day)
        
        return None
    
    def _extract_portfolio_value(self, text: str) -> Optional[float]:
        """Extract ending account value."""
        # Look for dollar amounts after "Ending" keywords
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            line_lower = line.lower().replace(' ', '')
            
            # Check if this line mentions ending value
            if 'endingaccountvalue' in line_lower or 'endingvalue' in line_lower:
                # Look for dollar amount on this line or next line
                for check_line in [line, lines[i+1] if i+1 < len(lines) else '']:
                    # Extract all dollar amounts
                    amounts = re.findall(r'\$([\d,]+\.?\d*)', check_line)
                    if amounts:
                        # First amount is typically the ending value
                        value_str = amounts[0].replace(',', '')
                        try:
                            return float(value_str)
                        except ValueError:
                            continue
        
        # Fallback: look for standalone dollar amounts after ending keywords
        patterns = [
            r'Ending\s*Account\s*Value\s*\$?([\d,]+\.?\d*)',
            r'\$(\d{1,3}(?:,\d{3})*\.?\d*)\s+\$\d',  # First of two dollar amounts
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '')
                try:
                    return float(value_str)
                except ValueError:
                    continue
        
        return None
    
    def _determine_account_type(self, account_name: str, text: str) -> str:
        """Determine account type from name and text."""
        text_lower = text.lower()
        name_lower = account_name.lower() if account_name else ""
        
        if "hsa" in text_lower or "health" in name_lower:
            return "hsa"
        elif "ira" in text_lower or "ira" in name_lower:
            return "ira"
        elif "401k" in text_lower or "401k" in name_lower:
            return "retirement"
        elif "roth" in text_lower:
            return "roth_ira"
        else:
            return "brokerage"
    
    def _extract_cash_balance(self, text: str) -> Optional[float]:
        """Extract cash balance from the statement."""
        # Look for "Cash & Cash Investments" or similar sections
        # Pattern: "Cash & Cash Investments $599.87"
        patterns = [
            r'Cash\s*&?\s*Cash\s*Investments?\s*\$?([\d,]+\.?\d*)',
            r'Cash\s*Balance\s*\$?([\d,]+\.?\d*)',
            r'CASH\s*&\s*CASH\s*INVESTMENTS\s*\$?([\d,]+\.?\d*)',
            r'Sweep\s*Money\s*Funds?\s*\$?([\d,]+\.?\d*)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '')
                try:
                    return float(value_str)
                except ValueError:
                    continue
        
        return None
    
    def _extract_holdings(self, text: str) -> list:
        """Extract holdings from page text."""
        holdings = []
        
        # Only parse positions sections, not open orders
        # Skip if this appears to be in the "Pending / Open Activity" section
        if "Pending" in text and "Open Activity" in text:
            # Check if we're in the positions section or open orders
            positions_end = text.find("Pending / Open Activity")
            if positions_end > 0:
                text = text[:positions_end]
        
        # Pattern for equities section:
        # Symbol Description Quantity Price($) Market Value($) ...
        # AAPL APPLEINC 2.0000 270.37000 540.74 ...
        
        # More specific pattern that requires 5-digit precision prices (actual holdings)
        equity_pattern = r'([A-Z]{1,5})\s+([A-Z][A-Z\s]+(?:INC|CORP|CO|ETF|FUND|,)?)\s+(\d+\.\d{4})\s+(\d+\.\d{4,5})\s+([\d,]+\.\d{2})'
        
        for match in re.finditer(equity_pattern, text):
            symbol = match.group(1)
            name = match.group(2).strip().rstrip(',')
            quantity = float(match.group(3))
            price = float(match.group(4))
            market_value = float(match.group(5).replace(',', ''))
            
            # Skip if this looks like header text or invalid data
            if quantity <= 0 or symbol in ['CUSIP', 'SYMBOL', 'TYPE']:
                continue
            
            # Skip cash entries (handled separately)
            if symbol.upper() == 'CASH':
                continue
            
            holdings.append({
                "symbol": symbol,
                "name": name,
                "quantity": quantity,
                "price": price,
                "market_value": market_value,
            })
        
        return holdings

