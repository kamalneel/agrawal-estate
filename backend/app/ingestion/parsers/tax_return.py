"""
Tax Return PDF Parser.

Parses IRS Form 1040 and related schedules to extract:
- Tax year
- Adjusted Gross Income (AGI)
- Federal total tax
- State total tax
- Filing status
- Schedule E (Rental Income)
- Schedule B (Interest and Dividends)
- Schedule D (Capital Gains)
- W-2 income details
"""

import re
import json
from pathlib import Path
from typing import Any, Optional, Dict, List

from app.ingestion.parsers.base import BaseParser, ParseResult, ParsedRecord, RecordType


class TaxReturnParser(BaseParser):
    """
    Parser for IRS Form 1040 and related schedules.
    """
    
    source_name = "tax_return"
    supported_extensions = [".pdf"]
    
    TAX_RETURN_IDENTIFIERS = [
        "form 8879",
        "form 1040",
        "irs e-file",
        "tax return",
        "adjusted gross income",
    ]
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if this is a tax return PDF."""
        if file_path.suffix.lower() != '.pdf':
            return False
        
        try:
            import pdfplumber
            
            with pdfplumber.open(file_path) as pdf:
                if len(pdf.pages) == 0:
                    return False
                
                for page in pdf.pages[:3]:
                    page_text = (page.extract_text() or "").lower()
                    
                    for identifier in self.TAX_RETURN_IDENTIFIERS:
                        if identifier in page_text:
                            return True
                    
        except Exception:
            pass
        
        return False
    
    def parse(self, file_path: Path) -> ParseResult:
        """Parse tax return PDF and extract comprehensive tax data."""
        import pdfplumber
        
        records = []
        warnings = []
        errors = []
        metadata = {
            "file_type": "tax_return",
            "source": "tax_return",
        }
        
        try:
            with pdfplumber.open(file_path) as pdf:
                first_page_text = pdf.pages[0].extract_text() or ""
                
                tax_data = {}
                
                # Check format type
                if 'FEDERAL TAX SUMMARY' in first_page_text or (
                    len(pdf.pages) > 1 and 'FEDERAL TAX SUMMARY' in (pdf.pages[1].extract_text() or '')
                ):
                    for i in range(min(3, len(pdf.pages))):
                        page_text = pdf.pages[i].extract_text() or ''
                        if 'FEDERAL TAX SUMMARY' in page_text:
                            tax_data = self._parse_tax_preparer_format(page_text, pdf)
                            break
                elif 'Tax Summary' in first_page_text and '1040' in first_page_text:
                    # Alternative tax summary format (e.g., "2022 Tax Summary (1040)")
                    tax_data = self._parse_tax_summary_format(first_page_text, pdf)
                else:
                    tax_data = self._parse_form_8879_format(pdf)
                
                # Extract detailed schedules
                details = self._extract_all_schedules(pdf)
                tax_data['details'] = details
                
                if tax_data.get('year'):
                    metadata.update(tax_data)
                    
                    record_data = {
                        "source": "tax_return",
                        "year": tax_data.get('year'),
                        "agi": tax_data.get('agi', 0),
                        "federal_tax": tax_data.get('federal_tax', 0),
                        "state_tax": tax_data.get('state_tax', 0),
                        "federal_withheld": tax_data.get('federal_withheld', 0),
                        "state_withheld": tax_data.get('state_withheld', 0),
                        "federal_owed": tax_data.get('federal_owed', 0),
                        "federal_refund": tax_data.get('federal_refund', 0),
                        "state_owed": tax_data.get('state_owed', 0),
                        "state_refund": tax_data.get('state_refund', 0),
                        "filing_status": tax_data.get('filing_status'),
                        "effective_rate": tax_data.get('effective_rate'),
                        "details": details,
                    }
                    
                    records.append(ParsedRecord(
                        record_type=RecordType.TAX_RECORD,
                        data=record_data,
                        source_row=0
                    ))
                else:
                    warnings.append("Could not extract tax year from document")
                
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
    
    def _extract_all_schedules(self, pdf) -> Dict[str, Any]:
        """Extract data from all relevant schedules."""
        details = {
            "income_sources": {},
            "rental_properties": [],
            "capital_gains": {},
            "deductions": {},
            "payroll_taxes": {},
            "w2_breakdown": [],
        }
        
        all_text = ""
        for page in pdf.pages:
            all_text += (page.extract_text() or "") + "\n"
        
        # Extract 1040 main form income
        details["income_sources"] = self._extract_1040_income(all_text)
        
        # Extract Schedule E (Rental Income)
        for page in pdf.pages:
            text = page.extract_text() or ""
            if 'Supplemental Income and Loss' in text or ('Schedule E' in text and 'Rents received' in text):
                rental_data = self._extract_schedule_e(text)
                if rental_data:
                    details["rental_properties"].extend(rental_data)
        
        # Extract Schedule B (Interest and Dividends)
        for page in pdf.pages:
            text = page.extract_text() or ""
            if 'Schedule B' in text and 'Interest and' in text:
                schedule_b = self._extract_schedule_b(text)
                if schedule_b.get("total_interest") and schedule_b["total_interest"] > 0:
                    details["income_sources"]["interest_income"] = schedule_b["total_interest"]
                if schedule_b.get("total_dividends") and schedule_b["total_dividends"] > 0:
                    # Only use if it's a reasonable value (not picking up wrong number)
                    if schedule_b["total_dividends"] < 1000000:  # Sanity check
                        details["income_sources"]["ordinary_dividends"] = schedule_b["total_dividends"]
        
        # Extract Schedule D (Capital Gains)
        for page in pdf.pages:
            text = page.extract_text() or ""
            if ('Schedule D' in text or 'Capital Gains and Losses' in text) and ('Short-Term' in text or 'Long-Term' in text):
                cap_gains = self._extract_schedule_d(text)
                if cap_gains:
                    details["capital_gains"].update(cap_gains)
        
        # Sum rental income if we have properties
        if details["rental_properties"]:
            total_rental = sum(p.get("net_income", 0) for p in details["rental_properties"])
            if total_rental != 0:
                details["income_sources"]["rental_income"] = total_rental
        
        return details
    
    def _extract_1040_income(self, text: str) -> Dict[str, float]:
        """Extract income sources from Form 1040."""
        income = {}
        
        # W-2 wages - various formats
        patterns = [
            # Format 2024: "Total amount from Form(s) W-2, box 1 ... 322,220."
            r'W-2.*?box 1.*?([\d,]+)\.',
            # Format 2023: "Income 1a Total amount from Form(s) W-2...1 a . . . . 4 .5 3. , 6. 1 .5"
            r'Total amount from Form.*?W-2.*?1\s*a[.\s]+([\d,.\s]+?)(?:\n|$)',
            # Format 2021: "1 Wages, salaries...W-2 . . . 1 . . . 3. 3 .4 , .0 8 .2"
            r'Wages.*?salaries.*?W-2[.\s]+1[.\s]+([\d,.\s]+?)(?:\n|$)',
            # Format 2019: "1 Wages, salaries...1. . . 5 1 2 , 1 9 2"
            r'1\s+Wages.*?tips.*?1[.\s]+([\d,.\s]+?)(?:\n|$)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = self._clean_number(match.group(1))
                # Sanity check: W2 wages should be between $10K and $2M
                if 10000 < val < 2000000:
                    income["w2_wages"] = val
                    break
        
        # Qualified dividends (line 3a)
        patterns = [
            r'Qualified dividends[~.\s]+3a[~.\s]+([\d,.\s]+)',
            r'3a[~.\s]+Qualified dividends[~.\s]+([\d,.\s]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = self._clean_number(match.group(1))
                if val > 0:
                    income["qualified_dividends"] = val
                    break
        
        # Capital gains (line 7)
        patterns = [
            r'Capital gain.*?line 7[~.\s]+([\d,.\s]+)',
            r'7[~.\s]+Capital gain[~.\s]+([\d,.\s]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = self._clean_number(match.group(1))
                if val > 100:
                    income["capital_gains"] = val
                    break
        
        return income
    
    def _clean_number(self, text: str) -> int:
        """Clean a number that may have dots/spaces between digits (PDF extraction artifact)."""
        # Remove all dots and spaces, keep only digits and commas
        cleaned = re.sub(r'[.\s]+', '', text)
        # Remove commas and convert to int
        digits_only = re.sub(r'[^\d]', '', cleaned)
        return int(digits_only) if digits_only else 0
    
    def _extract_schedule_e(self, text: str) -> List[Dict[str, Any]]:
        """Extract rental property data from Schedule E."""
        properties = []
        seen_addresses = set()  # Track addresses to avoid duplicates
        
        # Find property address
        address_match = re.search(
            r'1a\s+Physical address.*?\n[A-Z]?\s*(.+?(?:DR|DRIVE|ST|STREET|AVE|AVENUE|BLVD|CT|COURT|WAY|LN|LANE|RD|ROAD|PL|PLACE)[,\s]+.+?(?:\d{5}(?:-\d{4})?))',
            text, 
            re.IGNORECASE | re.DOTALL
        )
        
        if not address_match:
            # Try alternative pattern
            address_match = re.search(
                r'[A-Z]\s+(\d+\s+[A-Z]+.*?(?:CA|California)\s*\d{5})',
                text,
                re.IGNORECASE
            )
        
        address = address_match.group(1).strip() if address_match else "Unknown Property"
        address = re.sub(r'\s+', ' ', address)  # Clean up whitespace
        
        # Check for duplicate (normalize address for comparison)
        address_key = re.sub(r'[^A-Z0-9]', '', address.upper())
        if address_key in seen_addresses:
            return properties  # Skip duplicate
        seen_addresses.add(address_key)
        
        property_data = {
            "address": address,
            "rent_received": 0,
            "total_expenses": 0,
            "depreciation": 0,
            "net_income": 0,
        }
        
        # Extract rents received (line 3) - handle dots/spaces/tildes in numbers
        # Format 1: "3 Rents received . . . 3 . . . 4. 1 ,. 6 5. 0" (dots)
        # Format 2: "3 Rents received ~~~ 3 63,600." (tildes)
        rent_patterns = [
            r'Rents received[~.\s]+3[~.\s]+([\d,.\s]+?)(?:\n|$)',
            r'3\s+Rents received[~.\s]+3[~.\s]+([\d,.\s]+)',
            r'23a\s+Total.*?line 3.*?23a[~.\s]+([\d,.\s]+)',  # Line 23a total rents
        ]
        for pattern in rent_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = self._clean_number(match.group(1))
                if val > 100:  # Reasonable rent amount
                    property_data["rent_received"] = val
                    break
        
        # Extract total expenses (line 20)
        # Format 1: "20. . . . . . . . . 2 6. , 1 .3 8" (dots)
        # Format 2: "20 Total expenses ~~~ 20 45,282." (tildes)
        expense_patterns = [
            r'Add lines 5 through 19[~.\s]+2\s*0[~.\s]+([\d,.\s]+?)(?:\n|$)',
            r'Total expenses[~.\s]+2\s*0[~.\s]+([\d,.\s]+?)(?:\n|$)',
            r'20\s+Total expenses[~.\s]+20[~.\s]+([\d,.\s]+)',
            r'23e[.\s]+Total.*?line 20[.\s]+23e[.\s]+([\d,.\s]+)',  # Line 23e
        ]
        for pattern in expense_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = self._clean_number(match.group(1))
                if val > 0:
                    property_data["total_expenses"] = val
                    break
        
        # Extract depreciation (line 18)
        # Format 1: "1 8 . . . . . . . . .1 5. , 8 .8 2" (dots)
        # Format 2: "18 Depreciation ~~~ 18 22,419." (tildes)
        depreciation_patterns = [
            r'Depreciation.*?1\s*8[~.\s]+([\d,.\s]+?)(?:\n|$)',
            r'18\s+Depreciation[~.\s]+18[~.\s]+([\d,.\s]+)',
            r'23d[.\s]+Total.*?line 18[.\s]+23d[.\s]+([\d,.\s]+)',  # Line 23d
        ]
        for pattern in depreciation_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = self._clean_number(match.group(1))
                if val > 0:
                    property_data["depreciation"] = val
                    break
        
        # Extract net income (line 21 or 26)
        net_patterns = [
            r'21\s+Subtract line 20.*?21[.\s]+([\d,.\s]+?)(?:\n|$)',
            r'26\s+Total rental.*?26[.\s]+([\d,.\s]+?)(?:\n|$)',
        ]
        for pattern in net_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = self._clean_number(match.group(1))
                property_data["net_income"] = val
                break
        
        # Calculate net income if not found
        if property_data["net_income"] == 0 and property_data["rent_received"] > 0:
            property_data["net_income"] = property_data["rent_received"] - property_data["total_expenses"]
        
        # Only add if we found meaningful data
        if property_data["rent_received"] > 0 or property_data["total_expenses"] > 0:
            properties.append(property_data)
        
        return properties
    
    def _extract_schedule_b(self, text: str) -> Dict[str, float]:
        """Extract interest and dividend data from Schedule B."""
        result = {}
        
        # Total interest (line 2 or 4) - format: "2 . . . . . . . . . 2. 1"
        interest_patterns = [
            r'Add the amounts on line 1[.\s]+2[.\s]+([\d,.\s]+)',
            r'Subtract line 3.*?4[.\s]+([\d,.\s]+)',
        ]
        for pattern in interest_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = self._clean_number(match.group(1))
                if val > 0:
                    result["total_interest"] = val
                    break
        
        # Total ordinary dividends (line 6) - often appears on next line or in Form 1040
        # Try Schedule B line 6 first
        dividend_patterns = [
            r'Add the amounts on line 5[.\s]+.*?6[.\s]+([\d,.\s]+)',
            r'line 6[.\s]+([\d,.\s]+)',
        ]
        for pattern in dividend_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = self._clean_number(match.group(1))
                if val > 0:
                    result["total_dividends"] = val
                    break
        
        # If not found, try to sum up individual dividend entries
        if "total_dividends" not in result:
            # Look for dividend amounts in the list (numbers at end of lines in Part II)
            # This is a fallback approach
            pass
        
        return result
    
    def _extract_schedule_d(self, text: str) -> Dict[str, float]:
        """Extract capital gains data from Schedule D."""
        result = {}
        
        # Short-term gain/loss (line 7)
        short_term_patterns = [
            r'7\s+Net short-term.*?7[.\s]+([\d,.\s]+?)(?:\n|$)',
            r'Net short-term capital gain.*?7[.\s]+([\d,.\s]+)',
        ]
        for pattern in short_term_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = self._clean_number(match.group(1))
                # Check if it's a loss (in parentheses)
                context = text[max(0, match.start()-10):match.end()+10]
                if '(' in context and ')' in context:
                    val = -val
                if val != 0:
                    result["short_term"] = val
                    break
        
        # Long-term gain/loss (line 15)
        long_term_patterns = [
            r'15\s+Net long-term.*?15[.\s]+([\d,.\s]+?)(?:\n|Part)',
            r'Net long-term capital gain.*?15[.\s]+([\d,.\s]+)',
        ]
        for pattern in long_term_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = self._clean_number(match.group(1))
                context = text[max(0, match.start()-10):match.end()+10]
                if '(' in context and ')' in context:
                    val = -val
                if val != 0:
                    result["long_term"] = val
                    break
        
        # Total (line 16)
        total_patterns = [
            r'16\s+Combine.*?16[.\s]+([\d,.\s]+?)(?:\n|¥|$)',
            r'Combine lines 7 and 15.*?16[.\s]+([\d,.\s]+)',
        ]
        for pattern in total_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = self._clean_number(match.group(1))
                context = text[max(0, match.start()-10):match.end()+10]
                if '(' in context and ')' in context:
                    val = -val
                if val != 0:
                    result["total"] = val
                    break
        
        return result
    
    def _parse_tax_summary_format(self, summary_text: str, pdf) -> Dict[str, Any]:
        """Parse the tax summary format (e.g., '2022 Tax Summary (1040)')."""
        data = {}
        
        # Extract year from header
        year_match = re.search(r'(\d{4})\s+Tax Summary', summary_text)
        if year_match:
            data['year'] = int(year_match.group(1))
        
        # Only parse from the Federal Information section
        federal_section = summary_text
        if 'Federal Information' in summary_text:
            federal_start = summary_text.find('Federal Information')
            # Find the end of federal section (before State/CA section)
            ca_start = summary_text.find('California Information', federal_start)
            if ca_start == -1:
                ca_start = summary_text.find('State Information', federal_start)
            if ca_start > 0:
                federal_section = summary_text[federal_start:ca_start]
            else:
                federal_section = summary_text[federal_start:]
        
        # Parse values from federal section - handle dot-separated format
        lines = federal_section.split('\n')
        for line in lines:
            line_clean = line.strip()
            
            if 'Adjusted Gross Income' in line_clean:
                # Format: "Adjusted Gross Income . . . . $. 4. 2. 5. ,.4 .7 .7"
                match = re.search(r'\$[.\s]*([\d,.\s]+)', line_clean)
                if match:
                    data['agi'] = self._clean_number(match.group(1))
            
            elif line_clean.startswith('Total Tax') and 'withheld' not in line_clean.lower():
                match = re.search(r'\$[.\s]*([\d,.\s]+)', line_clean)
                if match:
                    val = self._clean_number(match.group(1))
                    # Sanity check - federal tax should be substantial
                    if val > 1000:
                        data['federal_tax'] = val
            
            elif 'Filing status' in line_clean:
                if 'Married Filing Joint' in line_clean:
                    data['filing_status'] = 'MFJ'
                elif 'Single' in line_clean:
                    data['filing_status'] = 'Single'
                elif 'Head of Household' in line_clean:
                    data['filing_status'] = 'HOH'
        
        # Extract CA state tax
        state_tax = self._extract_ca_540_tax(pdf)
        if state_tax:
            data['state_tax'] = state_tax
        
        return data
    
    def _parse_tax_preparer_format(self, summary_text: str, pdf) -> Dict[str, Any]:
        """Parse the tax preparer summary format."""
        data = {}
        
        for page in pdf.pages[:2]:
            text = page.extract_text() or ''
            year_match = re.search(r'(\d{4})\s+TAX RETURN', text)
            if year_match:
                data['year'] = int(year_match.group(1))
                break
        
        lines = summary_text.split('\n')
        for line in lines:
            line_upper = line.upper()
            
            if 'ADJUSTED GROSS INCOME' in line_upper:
                match = re.search(r'\$?([\d,]+)', line)
                if match:
                    data['agi'] = int(match.group(1).replace(',', ''))
            
            elif 'TOTAL TAX:' in line_upper:
                match = re.search(r'\$?([\d,]+)', line)
                if match:
                    data['federal_tax'] = int(match.group(1).replace(',', ''))
            
            elif 'BALANCE DUE' in line_upper:
                match = re.search(r'\$?([\d,]+)', line)
                if match:
                    data['federal_owed'] = int(match.group(1).replace(',', ''))
            
            elif 'EFFECTIVE TAX RATE' in line_upper:
                match = re.search(r'([\d.]+)%', line)
                if match:
                    data['effective_rate'] = float(match.group(1))
        
        state_tax = self._extract_ca_540_tax(pdf)
        if state_tax:
            data['state_tax'] = state_tax
        
        return data
    
    def _parse_form_8879_format(self, pdf) -> Dict[str, Any]:
        """Parse the standard IRS Form 8879 format."""
        data = {}
        
        federal_text = pdf.pages[0].extract_text() or ''
        
        year_match = re.search(r'December 31,?\s*(\d{4})', federal_text)
        if year_match:
            data['year'] = int(year_match.group(1))
        
        lines = federal_text.split('\n')
        for line in lines:
            if 'Adjusted gross income' in line:
                data['agi'] = self._parse_form_value(line, 1)
            elif 'Total tax' in line and 'withheld' not in line.lower():
                data['federal_tax'] = self._parse_form_value(line, 2)
            elif 'withheld' in line.lower() and ('W-2' in line or '1099' in line):
                data['federal_withheld'] = self._parse_form_value(line, 3)
            elif 'refunded' in line.lower():
                data['federal_refund'] = self._parse_form_value(line, 4)
            elif 'Amount you owe' in line:
                data['federal_owed'] = self._parse_form_value(line, 5)
        
        if len(pdf.pages) > 1:
            ca_text = pdf.pages[1].extract_text() or ''
            if 'California' in ca_text:
                for line in ca_text.split('\n'):
                    if 'Refund' in line and 'Amount you owe' not in line:
                        data['state_refund'] = self._parse_form_value(line, 3)
        
        state_tax = self._extract_ca_540_tax(pdf)
        if state_tax:
            data['state_tax'] = state_tax
        
        return data
    
    def _parse_form_value(self, line: str, line_num: int) -> int:
        """Parse a value from Form 8879 line."""
        pattern = rf'(\s{line_num}\.[\s\.]*)(\d[\d\s\.,]*?)[\s\.]*$'
        match = re.search(pattern, line)
        if match:
            value_part = match.group(2)
            digits = re.sub(r'[^\d]', '', value_part)
            return int(digits) if digits else 0
        
        pattern2 = rf'{line_num}[\s\.]+(\d[\d\s\.,]*?)[\s\.]*$'
        match = re.search(pattern2, line)
        if match:
            value_part = match.group(1)
            digits = re.sub(r'[^\d]', '', value_part)
            return int(digits) if digits else 0
        
        return 0
    
    def _extract_ca_540_tax(self, pdf) -> Optional[int]:
        """Extract total California tax from Form 540."""
        for page in pdf.pages:
            text = page.extract_text() or ''
            
            if ('540' in text and 'California' in text) or 'Form 540' in text:
                lines = text.split('\n')
                for line in lines:
                    if 'This is your total tax' in line or ('64' in line[:5] and 'Add line' in line):
                        match = re.search(r'[¥\$]\s*([\d,]+)\s*\.?\s*0?0?', line)
                        if match:
                            val = int(match.group(1).replace(',', ''))
                            if val > 100:
                                return val
                        
                        amounts = re.findall(r'\$?\s*([\d,]+)\s*\.?\s*0?0?\s*$', line)
                        if amounts:
                            val = int(amounts[-1].replace(',', ''))
                            if val > 100:
                                return val
        
        return None
