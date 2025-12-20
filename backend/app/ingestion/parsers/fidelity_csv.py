"""
Fidelity CSV Statement Parser.

Parses Fidelity HSA and brokerage CSV statements to extract:
- Account information (type, number)
- Current holdings/positions
- Account value summary
"""

import re
import csv
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from io import StringIO

from app.ingestion.parsers.base import BaseParser, ParseResult, ParsedRecord, RecordType


class FidelityCSVParser(BaseParser):
    """
    Parser for Fidelity CSV account statements.
    Handles HSA and brokerage account statements.
    """
    
    source_name = "fidelity"
    supported_extensions = [".csv", ".CSV"]
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if this is a Fidelity CSV statement."""
        if file_path.suffix.lower() != '.csv':
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read(2000)
                
            # Look for Fidelity-specific patterns
            fidelity_patterns = [
                "Health Savings Account",
                "FIDELITY",
                "Symbol/CUSIP",
                "FXAIX",
                "FSMDX",
                "FDRXX",
            ]
            
            for pattern in fidelity_patterns:
                if pattern in content:
                    return True
                    
        except Exception:
            pass
        
        return False
    
    def parse(self, file_path: Path) -> ParseResult:
        """Parse Fidelity CSV statement and extract holdings."""
        records = []
        warnings = []
        errors = []
        metadata = {
            "file_type": "csv_statement",
            "source": "fidelity",
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract account info from first section
            account_type, account_number, ending_value = self._extract_account_summary(content)
            
            # Determine account type string and owner
            if "health" in account_type.lower() or "hsa" in account_type.lower():
                acc_type = "hsa"
                owner = "Agrawal Family"  # HSA is family account
                account_id = "family_hsa"
            else:
                owner = "Neel"  # Default for other accounts
                acc_type = "brokerage"
                account_id = f"{owner.lower()}_{acc_type}"
            
            metadata["owner"] = owner
            metadata["account_type"] = acc_type
            metadata["account_number"] = account_number
            
            # Extract statement date from filename
            statement_date = self._extract_date_from_filename(file_path.name)
            metadata["statement_date"] = statement_date.isoformat() if statement_date else None
            
            # Extract holdings
            holdings = self._extract_holdings(content)
            
            # Create holding records
            for holding in holdings:
                record_data = {
                    "source": "fidelity",
                    "account_id": account_id,
                    "owner": owner,
                    "account_type": acc_type,
                    "symbol": holding["symbol"],
                    "quantity": holding["quantity"],
                    "description": holding.get("description"),
                    "market_value": holding.get("ending_value"),
                    "current_price": holding.get("price"),
                    "cost_basis": holding.get("cost_basis"),
                    "statement_date": statement_date,
                }
                
                records.append(ParsedRecord(
                    record_type=RecordType.HOLDING,
                    data=record_data,
                    source_row=0
                ))
            
            # Calculate portfolio value from holdings if not in summary
            if not ending_value and holdings:
                ending_value = sum(h.get("ending_value", 0) or 0 for h in holdings)
            
            # Create portfolio snapshot record
            if statement_date and ending_value:
                summary_data = {
                    "source": "fidelity",
                    "account_id": account_id,
                    "owner": owner,
                    "account_type": acc_type,
                    "statement_date": statement_date,
                    "portfolio_value": ending_value,
                }
                records.append(ParsedRecord(
                    record_type=RecordType.ACCOUNT_SUMMARY,
                    data=summary_data,
                    source_row=0
                ))
                metadata["portfolio_value"] = ending_value
            
            metadata["holdings_count"] = len(holdings)
            
            if not holdings:
                warnings.append("No holdings found in CSV.")
                
        except Exception as e:
            errors.append(f"Error parsing CSV: {str(e)}")
        
        return ParseResult(
            success=len(errors) == 0 and len(records) > 0,
            source_name=self.source_name,
            file_path=file_path,
            records=records,
            warnings=warnings,
            errors=errors,
            metadata=metadata
        )
    
    def _extract_account_summary(self, content: str) -> tuple:
        """Extract account type, number, and ending value from summary section."""
        account_type = ""
        account_number = ""
        ending_value = None
        
        lines = content.split('\n')
        
        for i, line in enumerate(lines[:10]):
            # Look for the account summary line
            # Format: Account Type,Account,Beginning mkt Value,...,Ending mkt Value,...
            if "Account Type" in line and "Ending" in line:
                # Next line should have values
                if i + 1 < len(lines):
                    values = lines[i + 1].split(',')
                    if len(values) >= 5:
                        account_type = values[0].strip()
                        account_number = values[1].strip()
                        # Ending mkt Value is typically column 4 (index 4)
                        try:
                            ending_value = float(values[4].strip())
                        except (ValueError, IndexError):
                            pass
                break
        
        return account_type, account_number, ending_value
    
    def _extract_date_from_filename(self, filename: str) -> Optional[datetime]:
        """Extract statement date from filename like 'Statement10312025.csv'."""
        # Pattern: Statement + MMDDYYYY
        match = re.search(r'Statement(\d{1,2})(\d{2})(\d{4})', filename)
        if match:
            month = int(match.group(1))
            day = int(match.group(2))
            year = int(match.group(3))
            try:
                return datetime(year, month, day)
            except ValueError:
                pass
        
        # Try other patterns
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
        if match:
            try:
                return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass
        
        return None
    
    def _extract_holdings(self, content: str) -> List[dict]:
        """Extract holdings from CSV content."""
        holdings = []
        
        # Find the holdings section (starts with Symbol/CUSIP header)
        lines = content.split('\n')
        in_holdings_section = False
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Detect start of holdings section
            if "Symbol/CUSIP" in line:
                in_holdings_section = True
                continue
            
            # Skip section headers and subtotals
            if in_holdings_section:
                if line.startswith('Subtotal') or line.startswith('Account Type'):
                    continue
                if 'Mutual Funds' in line or 'Core Account' in line:
                    continue
                if line.startswith(','):
                    continue
                
                # Parse holding line
                # Format: SYMBOL,Description,Quantity,Price,Beginning Value,Ending Value,Cost Basis
                parts = line.split(',')
                
                if len(parts) >= 6:
                    symbol = parts[0].strip()
                    
                    # Skip non-holding lines
                    if not symbol or symbol.isdigit() or len(symbol) > 10:
                        continue
                    
                    try:
                        description = parts[1].strip()
                        quantity = self._parse_number(parts[2])
                        price = self._parse_number(parts[3])
                        ending_value = self._parse_number(parts[5])
                        
                        # Handle cost basis (might be "not applicable")
                        cost_basis = None
                        if len(parts) > 6:
                            cost_str = parts[6].strip()
                            if cost_str and cost_str.lower() != 'not applicable':
                                cost_basis = self._parse_number(cost_str)
                        
                        if quantity and quantity > 0:
                            holdings.append({
                                "symbol": symbol,
                                "description": description,
                                "quantity": quantity,
                                "price": price,
                                "ending_value": ending_value,
                                "cost_basis": cost_basis,
                            })
                    except (ValueError, IndexError):
                        continue
        
        return holdings
    
    def _parse_number(self, value: str) -> Optional[float]:
        """Parse a number from string, handling various formats."""
        if not value:
            return None
        
        cleaned = value.strip().replace(',', '').replace('$', '')
        
        try:
            return float(cleaned)
        except ValueError:
            return None

