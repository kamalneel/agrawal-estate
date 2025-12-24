"""
IRS Wage and Income Transcript Parser.

Parses IRS Wage and Income Transcripts to extract:
- Form W-2 data (wages, 401k contributions via deferred compensation)
- Form 5498 data (IRA contributions, Roth IRA contributions, rollovers, FMV)
- Form 1099-R data (distributions)
"""

import re
from pathlib import Path
from typing import Any, Optional, Dict, List
from decimal import Decimal

from app.ingestion.parsers.base import BaseParser, ParseResult, ParsedRecord, RecordType


class IRSTranscriptParser(BaseParser):
    """
    Parser for IRS Wage and Income Transcripts.
    These transcripts contain Form 5498 (IRA contributions) and W-2 data.
    """
    
    source_name = "irs_transcript"
    supported_extensions = [".pdf"]
    
    TRANSCRIPT_IDENTIFIERS = [
        "wage and income transcript",
        "form 5498",
        "form w-2",
        "individual retirement arrangement contribution",
        "tracking number:",
        "response date:",
    ]
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if this is an IRS Wage and Income Transcript PDF."""
        if file_path.suffix.lower() != '.pdf':
            return False
        
        try:
            import pdfplumber
            
            with pdfplumber.open(file_path) as pdf:
                if len(pdf.pages) == 0:
                    return False
                
                # Check first page for identifiers
                first_page_text = (pdf.pages[0].extract_text() or "").lower()
                
                matches = sum(1 for identifier in self.TRANSCRIPT_IDENTIFIERS 
                             if identifier in first_page_text)
                
                # Need at least 2 matches to be confident
                return matches >= 2
                    
        except Exception:
            pass
        
        return False
    
    def parse(self, file_path: Path) -> ParseResult:
        """Parse IRS Wage and Income Transcript PDF."""
        import pdfplumber
        
        records = []
        warnings = []
        errors = []
        metadata = {
            "file_type": "irs_transcript",
            "source": "irs_transcript",
        }
        
        try:
            with pdfplumber.open(file_path) as pdf:
                # Extract all text
                full_text = ""
                for page in pdf.pages:
                    full_text += (page.extract_text() or "") + "\n"
                
                # Determine owner from filename
                filename = file_path.stem
                owner = self._extract_owner_from_filename(filename)
                
                # Extract tax year
                tax_year = self._extract_tax_year(full_text, filename)
                
                if not tax_year:
                    warnings.append("Could not determine tax year from transcript")
                    return ParseResult(
                        success=False,
                        source_name=self.source_name,
                        file_path=file_path,
                        records=[],
                        warnings=warnings,
                        errors=["Could not determine tax year"],
                        metadata=metadata
                    )
                
                metadata["tax_year"] = tax_year
                metadata["owner"] = owner
                
                # Extract W-2 data
                w2_data = self._extract_w2_data(full_text)
                
                # Extract Form 5498 data (IRA contributions)
                form_5498_data = self._extract_form_5498_data(full_text)
                
                # Create a consolidated retirement contribution record
                retirement_record = {
                    "source": "irs_transcript",
                    "owner": owner,
                    "tax_year": tax_year,
                    "w2_data": w2_data,
                    "ira_data": form_5498_data,
                    # Aggregated values for easy access
                    "total_401k": sum(w2.get("deferred_compensation", 0) for w2 in w2_data),
                    "total_ira_contributions": sum(ira.get("ira_contributions", 0) for ira in form_5498_data),
                    "total_roth_ira_contributions": sum(ira.get("roth_ira_contributions", 0) for ira in form_5498_data),
                    "total_rollover": sum(ira.get("rollover_contributions", 0) for ira in form_5498_data),
                    "total_sep_contributions": sum(ira.get("sep_contributions", 0) for ira in form_5498_data),
                    "total_simple_contributions": sum(ira.get("simple_contributions", 0) for ira in form_5498_data),
                    "ira_fmv": [ira.get("fair_market_value", 0) for ira in form_5498_data if ira.get("fair_market_value", 0) > 0],
                }
                
                records.append(ParsedRecord(
                    record_type=RecordType.TAX_RECORD,
                    data=retirement_record,
                    source_row=0
                ))
                
                metadata["w2_count"] = len(w2_data)
                metadata["form_5498_count"] = len(form_5498_data)
                
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
    
    def _extract_owner_from_filename(self, filename: str) -> str:
        """Extract owner name from filename like 'Neel 2024' or 'Jaya 2023'."""
        filename_lower = filename.lower()
        if 'neel' in filename_lower:
            return 'Neel'
        elif 'jaya' in filename_lower:
            return 'Jaya'
        return 'Unknown'
    
    def _extract_tax_year(self, text: str, filename: str) -> Optional[int]:
        """Extract tax year from transcript."""
        # Try from filename first (e.g., "Neel 2024")
        year_match = re.search(r'20\d{2}', filename)
        if year_match:
            return int(year_match.group())
        
        # Try from "Tax Period Requested: December, 2024"
        match = re.search(r'Tax Period Requested:.*?(\d{4})', text)
        if match:
            return int(match.group(1))
        
        # Try from response date
        match = re.search(r'Response Date:\s*\d{2}-\d{2}-(\d{4})', text)
        if match:
            year = int(match.group(1))
            # Response is typically for previous year
            return year - 1
        
        return None
    
    def _extract_w2_data(self, text: str) -> List[Dict[str, Any]]:
        """Extract all W-2 form data from transcript."""
        w2_records = []
        
        # Split by W-2 sections
        w2_sections = re.split(r'Form W-2 Wage and Tax Statement', text)
        
        for section in w2_sections[1:]:  # Skip first (before any W-2)
            w2 = {}
            
            # Employer EIN
            ein_match = re.search(r"Employer Identification Number \(EIN\):[\s]*([X\d]+)", section)
            if ein_match:
                w2["employer_ein"] = ein_match.group(1)
            
            # Wages
            wages_match = re.search(r'Wages, Tips and Other Compensation:[\s.]*\$([\d,]+(?:\.\d+)?)', section)
            if wages_match:
                w2["wages"] = self._parse_amount(wages_match.group(1))
            
            # Federal tax withheld
            fed_match = re.search(r'Federal Income Tax Withheld:[\s.]*\$([\d,]+(?:\.\d+)?)', section)
            if fed_match:
                w2["federal_tax_withheld"] = self._parse_amount(fed_match.group(1))
            
            # Social Security wages
            ss_wages_match = re.search(r'Social Security Wages:[\s.]*\$([\d,]+(?:\.\d+)?)', section)
            if ss_wages_match:
                w2["social_security_wages"] = self._parse_amount(ss_wages_match.group(1))
            
            # Medicare wages
            med_wages_match = re.search(r'Medicare Wages and Tips:[\s.]*\$([\d,]+(?:\.\d+)?)', section)
            if med_wages_match:
                w2["medicare_wages"] = self._parse_amount(med_wages_match.group(1))
            
            # Deferred Compensation (401k contributions)
            deferred_match = re.search(r'Deferred Compensation:[\s.]*\$([\d,]+(?:\.\d+)?)', section)
            if deferred_match:
                w2["deferred_compensation"] = self._parse_amount(deferred_match.group(1))
            
            # HSA contributions (Code W)
            hsa_match = re.search(r'Code "W" Employer Contributions to a Health Savings Account:[\s.]*\$([\d,]+(?:\.\d+)?)', section)
            if hsa_match:
                w2["hsa_contributions"] = self._parse_amount(hsa_match.group(1))
            
            # Designated Roth 401k (Code AA)
            roth_401k_match = re.search(r'Code "AA" Designated Roth Contributions under a Section 401\(k\) Plan:[\s.]*\$([\d,]+(?:\.\d+)?)', section)
            if roth_401k_match:
                w2["roth_401k"] = self._parse_amount(roth_401k_match.group(1))
            
            # Retirement Plan Indicator
            if 'Retirement Plan Indicator:' in section:
                w2["has_retirement_plan"] = 'Yes' in section.split('Retirement Plan Indicator:')[1][:50]
            
            if w2.get("wages", 0) > 0 or w2.get("deferred_compensation", 0) > 0:
                w2_records.append(w2)
        
        return w2_records
    
    def _extract_form_5498_data(self, text: str) -> List[Dict[str, Any]]:
        """Extract all Form 5498 IRA contribution data from transcript."""
        ira_records = []
        
        # Split by Form 5498 sections
        sections = re.split(r'Form 5498 Individual Retirement Arrangement Contribution Information', text)
        
        for section in sections[1:]:  # Skip first (before any 5498)
            ira = {}
            
            # Trustee FIN
            fin_match = re.search(r"Trustee/Issuer's Federal Identification Number \(FIN\):[\s]*([X\d]+)", section)
            if fin_match:
                ira["trustee_fin"] = fin_match.group(1)
            
            # Account number
            acct_match = re.search(r'Account Number \(Optional\):[\s.]*([X\d]+)', section)
            if acct_match:
                ira["account_number"] = acct_match.group(1)
            
            # IRA Contributions (Box 1)
            ira_match = re.search(r'IRA Contributions:[\s.]*\$([\d,]+(?:\.\d+)?)', section)
            if ira_match:
                ira["ira_contributions"] = self._parse_amount(ira_match.group(1))
            
            # Rollover Contributions (Box 2)
            rollover_match = re.search(r'Rollover Contributions:[\s.]*\$([\d,]+(?:\.\d+)?)', section)
            if rollover_match:
                ira["rollover_contributions"] = self._parse_amount(rollover_match.group(1))
            
            # Roth Conversion Amount (Box 3)
            roth_conv_match = re.search(r'Roth Conversion Amount:[\s.]*\$([\d,]+(?:\.\d+)?)', section)
            if roth_conv_match:
                ira["roth_conversion"] = self._parse_amount(roth_conv_match.group(1))
            
            # Fair Market Value (Box 5)
            fmv_match = re.search(r'Fair Market Value of Account:[\s.]*\$([\d,]+(?:\.\d+)?)', section)
            if fmv_match:
                ira["fair_market_value"] = self._parse_amount(fmv_match.group(1))
            
            # SEP Contributions (Box 8)
            sep_match = re.search(r'SEP Contributions:[\s.]*\$([\d,]+(?:\.\d+)?)', section)
            if sep_match:
                ira["sep_contributions"] = self._parse_amount(sep_match.group(1))
            
            # SIMPLE Contributions (Box 9)
            simple_match = re.search(r'SIMPLE Contributions:[\s.]*\$([\d,]+(?:\.\d+)?)', section)
            if simple_match:
                ira["simple_contributions"] = self._parse_amount(simple_match.group(1))
            
            # Roth IRA Contributions (Box 10)
            roth_match = re.search(r'Roth IRA Contributions:[\s.]*\$([\d,]+(?:\.\d+)?)', section)
            if roth_match:
                ira["roth_ira_contributions"] = self._parse_amount(roth_match.group(1))
            
            # Account type indicators
            ira["is_traditional_ira"] = 'IRA Code:' in section and 'Checked' in section.split('IRA Code:')[1][:20] if 'IRA Code:' in section else False
            ira["is_roth_ira"] = 'Roth IRA Code:' in section and 'Checked' in section.split('Roth IRA Code:')[1][:20] if 'Roth IRA Code:' in section else False
            ira["is_sep"] = 'SEP Code:' in section and 'Checked' in section.split('SEP Code:')[1][:20] if 'SEP Code:' in section else False
            ira["is_simple"] = 'Simple Code:' in section and 'Checked' in section.split('Simple Code:')[1][:20] if 'Simple Code:' in section else False
            
            # Only add if there's meaningful data
            if (ira.get("ira_contributions", 0) > 0 or 
                ira.get("roth_ira_contributions", 0) > 0 or
                ira.get("rollover_contributions", 0) > 0 or
                ira.get("fair_market_value", 0) > 0 or
                ira.get("sep_contributions", 0) > 0 or
                ira.get("simple_contributions", 0) > 0):
                ira_records.append(ira)
        
        return ira_records
    
    def _parse_amount(self, amount_str: str) -> float:
        """Parse a dollar amount string to float."""
        if not amount_str:
            return 0.0
        cleaned = amount_str.replace(',', '').replace('$', '').strip()
        try:
            return float(cleaned)
        except ValueError:
            return 0.0









