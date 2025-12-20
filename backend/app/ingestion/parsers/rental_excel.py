"""
Rental Income Excel parser.

Handles Excel files containing rental property income and expense data.
Format example:
- Property address
- Tax year / Date of Service
- Annual Income
- Monthly breakdown (Jan-Dec)
- Expense categories (Advertising, Insurance, Repairs, etc.)
"""

import re
from pathlib import Path
from datetime import datetime, date
from typing import Any

import pandas as pd

from app.ingestion.parsers.base import BaseParser, ParseResult, ParsedRecord, RecordType


class RentalExcelParser(BaseParser):
    """
    Parser for rental income Excel spreadsheets.
    
    Expected format is a key-value style Excel with:
    - Property information (address, service dates)
    - Annual and monthly income
    - Itemized expenses
    """
    
    source_name = "rental"
    supported_extensions = [".xlsx", ".xls"]
    
    # Keywords to identify rental income files
    RENTAL_KEYWORDS = [
        "rental information",
        "rental income",
        "property address",
        "address of the property",
    ]
    
    # Expense categories we expect to find
    EXPENSE_CATEGORIES = {
        "advertising": "advertising",
        "auto and travel": "auto_travel",
        "cleaning and maintenance": "cleaning_maintenance",
        "insurance": "insurance",
        "legal and professional fee": "legal_professional",
        "mortgage interest": "mortgage_interest",
        "repairs": "repairs",
        "supplies": "supplies",
        "property tax": "property_tax",
        "hoa": "hoa",
        "maintenance": "maintenance",
        "maintenance (paint job)": "maintenance_paint",
        "utilities": "utilities",
        "management fees": "management_fees",
    }
    
    MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", 
              "jul", "aug", "sep", "oct", "nov", "dec"]
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if file matches rental income Excel format."""
        if file_path.suffix.lower() not in self.supported_extensions:
            return False
        
        try:
            df = pd.read_excel(file_path, header=None, nrows=10)
            
            # Check if any cell contains rental-related keywords
            for col in df.columns:
                for value in df[col].astype(str).str.lower():
                    for keyword in self.RENTAL_KEYWORDS:
                        if keyword in value:
                            return True
            
            # Also check first column header (which contains the title)
            first_col_name = str(df.columns[0]).lower() if len(df.columns) > 0 else ""
            for keyword in self.RENTAL_KEYWORDS:
                if keyword in first_col_name:
                    return True
                    
            return False
        except Exception:
            return False
    
    def parse(self, file_path: Path) -> ParseResult:
        """Parse rental income Excel file."""
        records = []
        warnings = []
        errors = []
        
        try:
            # Read the Excel file
            df = pd.read_excel(file_path, header=None)
            
            # Extract data from the key-value format
            data = self._extract_data(df)
            
            if not data.get("property_address"):
                errors.append("Could not find property address in file")
                return ParseResult(
                    success=False,
                    source_name=self.source_name,
                    file_path=file_path,
                    records=[],
                    warnings=warnings,
                    errors=errors,
                    metadata={}
                )
            
            # Determine tax year from filename or content
            tax_year = self._extract_tax_year(file_path.name, data)
            data["tax_year"] = tax_year
            data["source_file"] = file_path.name
            
            # Create a rental summary record
            summary_record = ParsedRecord(
                record_type=RecordType.INCOME_ENTRY,
                data={
                    "source": self.source_name,
                    "record_subtype": "rental_summary",
                    "property_address": data.get("property_address"),
                    "tax_year": tax_year,
                    "annual_income": data.get("annual_income", 0),
                    "total_expenses": data.get("total_expenses", 0),
                    "net_income": data.get("annual_income", 0) - data.get("total_expenses", 0),
                    "expenses": data.get("expenses", {}),
                    "monthly_income": data.get("monthly_income", {}),
                    "property_cost": data.get("property_cost"),
                    "source_file": file_path.name,
                },
                source_row=1
            )
            records.append(summary_record)
            
            # Create individual monthly income records
            monthly_income = data.get("monthly_income", {})
            for month, amount in monthly_income.items():
                if amount and amount > 0:
                    # Determine the month number
                    month_num = self.MONTHS.index(month.lower()) + 1 if month.lower() in self.MONTHS else 1
                    income_date = date(tax_year, month_num, 1)
                    
                    monthly_record = ParsedRecord(
                        record_type=RecordType.INCOME_ENTRY,
                        data={
                            "source": self.source_name,
                            "record_subtype": "rental_monthly",
                            "property_address": data.get("property_address"),
                            "tax_year": tax_year,
                            "income_date": income_date,
                            "month": month,
                            "gross_amount": amount,
                            "source_file": file_path.name,
                        },
                        source_row=1
                    )
                    records.append(monthly_record)
            
            # Create expense records
            expenses = data.get("expenses", {})
            for category, amount in expenses.items():
                if amount and amount > 0:
                    expense_record = ParsedRecord(
                        record_type=RecordType.INCOME_ENTRY,
                        data={
                            "source": self.source_name,
                            "record_subtype": "rental_expense",
                            "property_address": data.get("property_address"),
                            "tax_year": tax_year,
                            "expense_category": category,
                            "amount": amount,
                            "source_file": file_path.name,
                        },
                        source_row=1
                    )
                    records.append(expense_record)
            
        except Exception as e:
            errors.append(f"Failed to parse file: {str(e)}")
        
        return ParseResult(
            success=len(errors) == 0,
            source_name=self.source_name,
            file_path=file_path,
            records=records,
            warnings=warnings,
            errors=errors,
            metadata={
                "file_type": "rental_income",
                "record_count": len(records),
                "tax_year": data.get("tax_year") if 'data' in dir() else None,
            }
        )
    
    def _extract_data(self, df: pd.DataFrame) -> dict:
        """Extract data from key-value style Excel."""
        data = {
            "property_address": None,
            "annual_income": 0,
            "expenses": {},
            "monthly_income": {},
            "total_expenses": 0,
            "property_cost": None,
        }
        
        # Iterate through rows looking for key-value pairs
        for idx, row in df.iterrows():
            if pd.isna(row.iloc[0]):
                continue
                
            key = str(row.iloc[0]).strip().lower()
            value = row.iloc[1] if len(row) > 1 and not pd.isna(row.iloc[1]) else None
            
            # Property address
            if "address" in key and "property" in key:
                data["property_address"] = str(value) if value else None
            
            # Annual income
            elif "income received" in key or "rental income" in key:
                data["annual_income"] = self._parse_amount(value)
            
            # Cost of property
            elif "cost of property" in key:
                data["property_cost"] = self._parse_amount(value)
            
            # Monthly income (check if key is a month name)
            elif key in self.MONTHS:
                amount = self._parse_amount(value)
                if amount:
                    data["monthly_income"][key.capitalize()] = amount
            
            # Expense categories
            else:
                for expense_key, expense_name in self.EXPENSE_CATEGORIES.items():
                    if expense_key in key:
                        amount = self._parse_amount(value)
                        if amount and amount > 0:
                            data["expenses"][expense_name] = amount
                            data["total_expenses"] += amount
                        break
        
        return data
    
    def _parse_amount(self, value) -> float:
        """Parse an amount value, handling various formats."""
        if value is None or pd.isna(value):
            return 0
        
        if isinstance(value, (int, float)):
            return float(value)
        
        # String parsing
        value_str = str(value).strip()
        
        # Remove currency symbols and commas
        value_str = value_str.replace('$', '').replace(',', '').strip()
        
        # Handle parentheses as negative
        if value_str.startswith('(') and value_str.endswith(')'):
            value_str = '-' + value_str[1:-1]
        
        try:
            return float(value_str)
        except ValueError:
            return 0
    
    def _extract_tax_year(self, filename: str, data: dict) -> int:
        """Extract tax year from filename or data."""
        # Try to find year in filename (e.g., "2024", "2025")
        year_match = re.search(r'20[12][0-9]', filename)
        if year_match:
            return int(year_match.group())
        
        # Try to find "Tax Year XXXX" pattern
        year_match = re.search(r'[Tt]ax\s*[Yy]ear\s*(\d{4})', filename)
        if year_match:
            return int(year_match.group(1))
        
        # Default to current year
        return datetime.now().year















