"""
TD Ameritrade PDF Statement Parser.

Parses TD Ameritrade monthly brokerage statements to extract:
- Account information (owner, account number)
- Portfolio value summary (portfolio snapshots)
- Transactions (buys, sells, dividends) - historical records

NOTE: PDFs are historical documents. Holdings from PDFs are NOT extracted because
they would overwrite current positions with old data. Current holdings should come 
from CSV exports or paste data which represent the live/current state.
"""

import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List, Dict
from decimal import Decimal

from app.ingestion.parsers.base import BaseParser, ParseResult, ParsedRecord, RecordType


class TDAmeritradePDFParser(BaseParser):
    """
    Parser for TD Ameritrade PDF brokerage statements.
    
    TDA statements have a specific structure:
    - Page 1-2: Cover letter and disclosures
    - Page 3: Portfolio Summary with totals
    - Pages 4+: Account Positions with holdings
    - Later pages: Account Activity with transactions
    """
    
    source_name = "tdameritrade"
    supported_extensions = [".pdf", ".PDF"]
    
    # Patterns to identify TD Ameritrade statements
    TDA_IDENTIFIERS = [
        "td ameritrade",
        "tdameritrade",
        "td ameritrade clearing",
        "tda -",
        "800-669-3900",  # TDA customer service number
    ]
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if this is a TD Ameritrade PDF statement."""
        if file_path.suffix.lower() != '.pdf':
            return False
        
        # Quick check: filename often contains "TDA"
        if "TDA" in file_path.name or "tdameritrade" in file_path.name.lower():
            return True
        
        try:
            import pdfplumber
            
            with pdfplumber.open(file_path) as pdf:
                if len(pdf.pages) < 3:
                    return False
                
                # Check first few pages for TDA identifiers
                for page_num in range(min(3, len(pdf.pages))):
                    page_text = pdf.pages[page_num].extract_text() or ""
                    text_lower = page_text.lower()
                    
                    for identifier in self.TDA_IDENTIFIERS:
                        if identifier in text_lower:
                            return True
                    
        except Exception:
            pass
        
        return False
    
    def parse(self, file_path: Path) -> ParseResult:
        """Parse TD Ameritrade PDF statement and extract holdings + transactions."""
        import pdfplumber
        
        records = []
        warnings = []
        errors = []
        metadata = {
            "file_type": "pdf_statement",
            "source": "tdameritrade",
        }
        
        try:
            with pdfplumber.open(file_path) as pdf:
                full_text = ""
                for page in pdf.pages:
                    full_text += (page.extract_text() or "") + "\n"
                
                # Extract account info
                account_number, owner = self._extract_account_info(full_text)
                statement_date = self._extract_statement_date(full_text, file_path.name)
                
                # Determine account type from filename or content
                account_type = self._determine_account_type(file_path.name, full_text)
                
                # Create account_id
                if owner and owner != "Unknown":
                    account_id = f"{owner.lower()}_{account_type}_{account_number[-3:]}" if account_number else f"{owner.lower()}_{account_type}"
                else:
                    account_id = f"tda_{account_type}_{account_number[-3:]}" if account_number else f"tda_{account_type}"
                
                metadata["owner"] = owner
                metadata["account_number"] = account_number
                metadata["account_type"] = account_type
                metadata["account_id"] = account_id
                
                # Extract portfolio value
                portfolio_value = self._extract_portfolio_value(full_text)
                
                # Extract holdings ONLY to calculate portfolio value if not found directly
                # We do NOT create HOLDING records from PDFs - they're historical and would
                # overwrite current positions with old data
                holdings = self._extract_holdings(full_text)
                
                # Calculate portfolio value from holdings if not found
                if not portfolio_value and holdings:
                    portfolio_value = sum(h.get("market_value", 0) or 0 for h in holdings)
                
                # Extract transactions from Account Activity section
                # Transactions are historical records that don't overwrite current state
                transactions = self._extract_transactions(full_text)
                
                # Create transaction records (historical, additive - these are OK from PDFs)
                for txn in transactions:
                    record_data = {
                        "source": "tdameritrade",
                        "account_id": account_id,
                        "owner": owner,
                        "transaction_date": txn.get("trade_date"),
                        "transaction_type": txn.get("transaction_type", "OTHER"),
                        "symbol": txn.get("symbol", "UNKNOWN"),
                        "description": txn.get("description"),
                        "quantity": txn.get("quantity"),
                        "price_per_share": txn.get("price"),
                        "amount": txn.get("amount"),
                    }
                    
                    records.append(ParsedRecord(
                        record_type=RecordType.TRANSACTION,
                        data=record_data,
                        source_row=0
                    ))
                
                # Create portfolio snapshot
                if statement_date and portfolio_value:
                    summary_data = {
                        "source": "tdameritrade",
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
                    metadata["statement_date"] = statement_date.isoformat() if statement_date else None
                    metadata["portfolio_value"] = portfolio_value
                
                metadata["snapshots_count"] = 1 if (statement_date and portfolio_value) else 0
                metadata["transactions_count"] = len(transactions)
                
                if not records:
                    warnings.append("No portfolio snapshot or transactions found in PDF.")
                
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
    
    def _extract_account_info(self, text: str) -> Tuple[str, str]:
        """Extract account number and owner name."""
        account_number = ""
        owner = "Unknown"
        
        # Look for account number pattern: "Account # 866-800538"
        match = re.search(r'Account\s*#?\s*(\d{3}-\d{6})', text)
        if match:
            account_number = match.group(1)
        
        # Look for owner name - usually in the address block
        # Pattern: "NEEL KAMAL" followed by address
        lines = text.split('\n')
        for i, line in enumerate(lines[:30]):
            # Look for name in all caps followed by address
            if re.match(r'^[A-Z]+ [A-Z]+$', line.strip()):
                name = line.strip()
                # Check if next line looks like an address
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if re.match(r'^\d+', next_line) or 'PO BOX' in next_line.upper():
                        # Extract first name as owner
                        first_name = name.split()[0].title()
                        owner = first_name
                        break
        
        return account_number, owner
    
    def _extract_statement_date(self, text: str, filename: str) -> Optional[datetime]:
        """Extract statement end date from text or filename."""
        # Try filename first: "TDA - Brokerage Statement_2020-07-31_151.PDF"
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            return datetime(year, month, day)
        
        # Look for statement period in text
        # Pattern: "Statement Reporting Period: 07/01/20 - 07/31/20"
        match = re.search(r'(\d{2})/(\d{2})/(\d{2,4})\s*[-–]\s*(\d{2})/(\d{2})/(\d{2,4})', text)
        if match:
            end_month = int(match.group(4))
            end_day = int(match.group(5))
            end_year = int(match.group(6))
            if end_year < 100:
                end_year += 2000
            return datetime(end_year, end_month, end_day)
        
        return None
    
    def _extract_portfolio_value(self, text: str) -> Optional[float]:
        """Extract total portfolio value."""
        # Look for "Total $732,377.47" pattern in Portfolio Summary
        patterns = [
            r'Total\s+\$([\d,]+\.?\d*)',
            r'Total\s+Account\s+Value\s*\$?([\d,]+\.?\d*)',
            r'Current\s+Value\s+\$?([\d,]+\.?\d*)',
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
    
    def _determine_account_type(self, filename: str, text: str) -> str:
        """Determine account type from filename and content."""
        filename_lower = filename.lower()
        text_lower = text.lower()
        
        if "retirement" in filename_lower or "ira" in text_lower:
            if "roth" in text_lower:
                return "roth_ira"
            return "ira"
        elif "401k" in text_lower:
            return "retirement"
        elif "hsa" in text_lower:
            return "hsa"
        else:
            return "brokerage"
    
    def _extract_holdings(self, text: str) -> List[Dict]:
        """Extract holdings from Account Positions section."""
        holdings = []
        
        # TDA holdings format (symbol AFTER description):
        # Description | Symbol | Quantity | Price | Market Value | Date | Cost Basis | Avg Cost | Unrealized G/L
        # AMAZON COM INC | AMZN | 25 | 3,164.68 | 79,117.00 | 06/11/20 | 64,704.20 | 2,588.17 | 14,412.80
        # APPLE INC COM | AAPL | 500 | 425.04 | 212,520.00 | 03/23/20 | 166,035.12 | 332.07 | 46,484.88
        
        # Pattern: Description SYMBOL Quantity Price MarketValue [Date] CostBasis AvgCost Unrealized
        patterns = [
            # Full format with cost basis - symbol after description
            r'([A-Z][A-Z\s]+(?:INC|CORP|CO|ETF|FUND|LTD|HLDGS?|ADR)?)\s+([A-Z]{1,5})\s+(\d+\.?\d*)\s+\$?\s*([\d,]+\.?\d+)\s+([\d,]+\.?\d+)\s+(\d{2}/\d{2}/\d{2})\s+([\d,]+\.?\d+)\s+([\d,]+\.?\d+)\s+\(?([\d,]+\.?\d+)\)?',
            # Format without parentheses on unrealized
            r'([A-Z][A-Z\s]+(?:INC|CORP|CO|ETF|FUND|LTD|HLDGS?|ADR)?)\s+([A-Z]{1,5})\s+(\d+\.?\d*)\s+\$?\s*([\d,]+\.?\d+)\s+([\d,]+\.?\d+)\s+(\d{2}/\d{2}/\d{2})\s+([\d,]+\.?\d+)\s+([\d,]+\.?\d+)\s+(-?[\d,]+\.?\d+)',
        ]
        
        seen_symbols = set()
        
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                try:
                    description = match.group(1).strip().rstrip(',')
                    symbol = match.group(2).strip()
                    
                    # Skip if already seen (dedup)
                    if symbol in seen_symbols:
                        continue
                    
                    # Skip header-like text
                    if symbol in ['CUSIP', 'SYMBOL', 'TYPE', 'COM', 'INC', 'CORP', 'DATE']:
                        continue
                    
                    quantity = float(match.group(3).replace(',', ''))
                    price = float(match.group(4).replace(',', ''))
                    market_value = float(match.group(5).replace(',', ''))
                    
                    # Extract cost basis
                    cost_basis = None
                    unrealized_gain = None
                    
                    try:
                        cost_basis = float(match.group(7).replace(',', ''))
                    except (ValueError, IndexError, TypeError):
                        pass
                    
                    try:
                        gain_str = match.group(9).replace(',', '').replace('(', '-').replace(')', '')
                        unrealized_gain = float(gain_str)
                    except (ValueError, IndexError, TypeError):
                        pass
                    
                    if quantity > 0 and market_value > 0:
                        holdings.append({
                            "symbol": symbol,
                            "description": description,
                            "quantity": quantity,
                            "price": price,
                            "market_value": market_value,
                            "cost_basis": cost_basis,
                            "unrealized_gain": unrealized_gain,
                        })
                        seen_symbols.add(symbol)
                        
                except (ValueError, IndexError):
                    continue
        
        # Also look for cash/IDA balances
        cash_match = re.search(r'(?:IDA|Insrd Dep Acct|Cash)\s+\$?\s*([\d,]+\.?\d*)', text)
        if cash_match:
            try:
                cash_value = float(cash_match.group(1).replace(',', ''))
                if cash_value > 0 and "CASH" not in seen_symbols:
                    holdings.append({
                        "symbol": "CASH",
                        "description": "Cash & Insured Deposit Account",
                        "quantity": cash_value,
                        "price": 1.0,
                        "market_value": cash_value,
                    })
            except ValueError:
                pass
        
        return holdings
    
    def _extract_transactions(self, text: str) -> List[Dict]:
        """Extract transactions from Account Activity section."""
        transactions = []
        
        # Only extract from Account Activity section
        activity_start = text.find("Account Activity")
        if activity_start == -1:
            return transactions
        
        activity_text = text[activity_start:]
        
        # TDA transaction format:
        # Trade Date | Settle Date | Acct Type | Transaction | Symbol/CUSIP | Quantity | Price | Amount
        # 07/07/20 | 07/09/20 | Cash | Buy - Securities Purchased | AAPL | 100 | 376.97 | (37,697.00)
        
        # Pattern for buy/sell transactions
        txn_pattern = r'(\d{2}/\d{2}/\d{2})\s+\d{2}/\d{2}/\d{2}\s+Cash\s+(Buy|Sell)\s*[-–]?\s*Securities\s*(?:Purchased|Sold)?\s+([A-Z][A-Z\s]+(?:INC|CORP|CO|ETF)?)\s+([A-Z]{1,5})\s+(\d+\.?\d*)-?\s+([\d,]+\.?\d+)\s+\(?([\d,]+\.?\d+)\)?'
        
        for match in re.finditer(txn_pattern, activity_text):
            try:
                trade_date_str = match.group(1)
                txn_type = match.group(2).upper()
                description = match.group(3).strip()
                symbol = match.group(4)
                quantity = float(match.group(5).replace(',', ''))
                price = float(match.group(6).replace(',', ''))
                amount = float(match.group(7).replace(',', ''))
                
                # Parse date
                parts = trade_date_str.split('/')
                month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
                if year < 100:
                    year += 2000
                trade_date = datetime(year, month, day)
                
                # Adjust amount sign
                if txn_type == "BUY":
                    amount = -abs(amount)
                else:
                    amount = abs(amount)
                
                transactions.append({
                    "trade_date": trade_date,
                    "transaction_type": txn_type,
                    "symbol": symbol,
                    "description": description,
                    "quantity": quantity,
                    "price": price,
                    "amount": amount,
                })
                
            except (ValueError, IndexError):
                continue
        
        # Also look for dividend transactions
        div_pattern = r'(\d{2}/\d{2}/\d{2})\s+\d{2}/\d{2}/\d{2}\s+Cash\s+Div/Int\s*[-–]?\s*Income\s+([A-Z][A-Z\s]+(?:INC|CORP|ETF)?)\s+([A-Z]{1,5})?\s*[-–]?\s*[\d.]+\s+([\d,]+\.?\d+)'
        
        for match in re.finditer(div_pattern, activity_text):
            try:
                trade_date_str = match.group(1)
                description = match.group(2).strip()
                symbol = match.group(3) or "DIV"
                amount = float(match.group(4).replace(',', ''))
                
                # Parse date
                parts = trade_date_str.split('/')
                month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
                if year < 100:
                    year += 2000
                trade_date = datetime(year, month, day)
                
                transactions.append({
                    "trade_date": trade_date,
                    "transaction_type": "DIVIDEND",
                    "symbol": symbol,
                    "description": f"Dividend - {description}",
                    "quantity": None,
                    "price": None,
                    "amount": amount,
                })
                
            except (ValueError, IndexError):
                continue
        
        return transactions

