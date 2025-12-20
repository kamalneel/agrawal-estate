"""
Salary Income Service - Parse salary payslips and W-2 forms (PDF).
Persists W-2 data to database for efficient lookups.
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import select

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


@dataclass
class W2Income:
    """Represents W-2 wage and tax statement data."""
    employee_name: str
    employer: str
    year: int
    
    # Box 1 - Wages, tips, other compensation
    wages: float = 0.0
    # Box 2 - Federal income tax withheld
    federal_tax_withheld: float = 0.0
    # Box 3 - Social security wages
    social_security_wages: float = 0.0
    # Box 4 - Social security tax withheld
    social_security_tax: float = 0.0
    # Box 5 - Medicare wages and tips
    medicare_wages: float = 0.0
    # Box 6 - Medicare tax withheld
    medicare_tax: float = 0.0
    # Box 12 D - 401(k) contributions
    retirement_401k: float = 0.0
    # Box 16 - State wages
    state_wages: float = 0.0
    # Box 17 - State income tax
    state_tax_withheld: float = 0.0
    
    # Derived: net income = gross - federal - state - ss - medicare
    @property
    def net_income(self) -> float:
        return self.wages - self.federal_tax_withheld - self.state_tax_withheld - self.social_security_tax - self.medicare_tax


@dataclass
class SalaryPayslip:
    """Represents a single payslip."""
    employee_name: str
    employer: str
    pay_date: datetime
    period_start: datetime
    period_end: datetime
    year: int
    
    # Current period amounts
    gross_pay_period: float = 0.0
    net_pay_period: float = 0.0
    
    # Year-to-date amounts
    gross_pay_ytd: float = 0.0
    net_pay_ytd: float = 0.0
    federal_tax_ytd: float = 0.0
    state_tax_ytd: float = 0.0
    social_security_ytd: float = 0.0
    medicare_ytd: float = 0.0
    retirement_401k_ytd: float = 0.0
    
    # Breakdown
    regular_salary_ytd: float = 0.0
    bonus_ytd: float = 0.0
    other_income_ytd: float = 0.0


@dataclass
class SalaryIncome:
    """Aggregated salary income for a person."""
    name: str
    employer: str
    payslips: List[SalaryPayslip] = field(default_factory=list)
    
    # Yearly totals (keyed by year)
    yearly_gross: Dict[int, float] = field(default_factory=dict)
    yearly_net: Dict[int, float] = field(default_factory=dict)
    yearly_federal_tax: Dict[int, float] = field(default_factory=dict)
    yearly_state_tax: Dict[int, float] = field(default_factory=dict)


class SalaryService:
    """Service to parse and aggregate salary income from payslips and W-2 forms."""

    def __init__(self, data_dir: str = None, db: Session = None):
        """Initialize the service with the data directory and optional db session."""
        if data_dir is None:
            base_dir = Path(__file__).parent.parent.parent.parent.parent
            data_dir = base_dir / "data" / "inbox" / "income" / "salary"
        self.data_dir = Path(data_dir)
        # Also search for W-2s in tax returns directory
        self.tax_returns_dir = Path(__file__).parent.parent.parent.parent.parent / "data" / "inbox" / "tax" / "returns"
        self.salaries: Dict[str, SalaryIncome] = {}
        self.w2_data: Dict[str, List[W2Income]] = {}  # Keyed by normalized employee name
        self.db = db

    def _parse_amount(self, text: str) -> float:
        """Parse a dollar amount from text."""
        if not text:
            return 0.0
        # Remove commas and handle negative amounts (with - suffix or prefix)
        cleaned = text.replace(',', '').replace('$', '').strip()
        is_negative = cleaned.endswith('-') or cleaned.startswith('-')
        cleaned = cleaned.replace('-', '')
        try:
            amount = float(cleaned)
            return -amount if is_negative else amount
        except ValueError:
            return 0.0

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse a date string in MM/DD/YYYY format."""
        try:
            return datetime.strptime(date_str.strip(), '%m/%d/%Y')
        except ValueError:
            return None

    def _extract_ytd_value(self, text: str, pattern: str) -> float:
        """Extract a year-to-date value using regex pattern."""
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return self._parse_amount(match.group(1))
        return 0.0

    def _is_w2_form(self, text: str, filepath: Path) -> bool:
        """Check if the PDF text looks like a W-2 form."""
        # First check filename - if it has W-2 or W2 in the name, it's likely a W-2
        filename_lower = filepath.name.lower()
        if 'w-2' in filename_lower or 'w2' in filename_lower:
            return True
        
        # Check content indicators
        w2_indicators = [
            'W-2',
            'W2',
            'Wage and Tax',
            'Wages, tips',
            'Federal income tax withheld',
            'OMB No. 1545-0008',
            'Social security wages',
            'Medicare wages',
        ]
        text_lower = text.lower()
        matches = sum(1 for ind in w2_indicators if ind.lower() in text_lower)
        return matches >= 2

    def _parse_w2(self, filepath: Path) -> Optional[W2Income]:
        """Parse a W-2 form PDF with support for multiple formats."""
        if pdfplumber is None:
            print("pdfplumber not installed, cannot parse PDFs")
            return None
            
        try:
            with pdfplumber.open(filepath) as pdf:
                if len(pdf.pages) == 0:
                    return None
                    
                page = pdf.pages[0]
                text = page.extract_text() or ""
                
                # Check if this is a W-2
                if not self._is_w2_form(text, filepath):
                    return None
                
                # Extract tables to get structured data
                tables = page.extract_tables()
                
                # Initialize values
                wages = 0.0
                federal_tax = 0.0
                ss_wages = 0.0
                ss_tax = 0.0
                medicare_wages = 0.0
                medicare_tax = 0.0
                state_tax = 0.0
                state_wages = 0.0
                retirement_401k = 0.0
                employee_name = ""
                employer = ""
                year = 0
                
                # ===== GET EMPLOYEE NAME AND EMPLOYER FROM FILENAME (most reliable) =====
                filename_lower = filepath.name.lower()
                if 'neel' in filename_lower:
                    employee_name = "Neel Kamal"
                elif 'jaya' in filename_lower:
                    employee_name = "Jaya Agrawal"
                
                # Get employer from filename
                employer_keywords = {
                    'cisco': 'Cisco Systems Inc',
                    'splunk': 'Splunk Inc',
                    'boost': 'BoostUp.ai',
                    'aviatrix': 'Aviatrix Systems',
                    'wavefront': 'Wavefront',
                    'couchbase': 'Couchbase',
                    'heartflow': 'HeartFlow',
                    'dewinter': 'Dewinter Group',
                    'kranz': 'Kranz & Associates',
                }
                for keyword, emp_name in employer_keywords.items():
                    if keyword in filename_lower:
                        employer = emp_name
                        break
                
                # ===== GET YEAR =====
                # First from directory path (most reliable for tax returns)
                for part in filepath.parts:
                    if re.match(r'^20\d{2}$', part):
                        year = int(part)
                        break
                
                # Then from filename
                if year == 0:
                    filename_year = re.search(r'(20\d{2})', filepath.name)
                    if filename_year:
                        year = int(filename_year.group(1))
                
                # Then from text
                if year == 0:
                    year_match = re.search(r'\b(20\d{2})\b', text)
                    if year_match:
                        year = int(year_match.group(1))
                
                # ===== PARSE W-2 VALUES - Multiple strategies =====
                
                # Strategy 1: Look for labeled boxes in tables (Cisco format)
                for table in tables:
                    for row in table:
                        if not row:
                            continue
                        row_text = ' '.join(str(cell) for cell in row if cell)
                        
                        # Box 1 - Wages (various label formats)
                        if wages == 0:
                            match = re.search(r'(?:Wages,?\s*tips,?\s*other\s*comp|1\s+Wages)[.\s]*([\d,]+\.?\d*)', row_text, re.IGNORECASE)
                            if match:
                                wages = self._parse_amount(match.group(1))
                        
                        # Box 2 - Federal tax
                        if federal_tax == 0:
                            match = re.search(r'(?:Federal\s*income\s*tax|2\s+Federal)[.\s]*([\d,]+\.?\d*)', row_text, re.IGNORECASE)
                            if match:
                                federal_tax = self._parse_amount(match.group(1))
                        
                        # Box 3 - Social security wages
                        if ss_wages == 0:
                            match = re.search(r'(?:Social\s*security\s*wages|3\s+Social)[.\s]*([\d,]+\.?\d*)', row_text, re.IGNORECASE)
                            if match:
                                ss_wages = self._parse_amount(match.group(1))
                        
                        # Box 4 - Social security tax
                        if ss_tax == 0:
                            match = re.search(r'(?:Social\s*security\s*tax|4\s+Social)[.\s]*([\d,]+\.?\d*)', row_text, re.IGNORECASE)
                            if match:
                                ss_tax = self._parse_amount(match.group(1))
                        
                        # Box 5 - Medicare wages
                        if medicare_wages == 0:
                            match = re.search(r'(?:Medicare\s*wages|5\s+Medicare)[.\s]*([\d,]+\.?\d*)', row_text, re.IGNORECASE)
                            if match:
                                medicare_wages = self._parse_amount(match.group(1))
                        
                        # Box 6 - Medicare tax
                        if medicare_tax == 0:
                            match = re.search(r'(?:Medicare\s*tax|6\s+Medicare)[.\s]*([\d,]+\.?\d*)', row_text, re.IGNORECASE)
                            if match:
                                medicare_tax = self._parse_amount(match.group(1))
                        
                        # Box 17 - State income tax
                        if state_tax == 0:
                            match = re.search(r'(?:State\s*income\s*tax|17\s*State)[.\s]*([\d,]+\.?\d*)', row_text, re.IGNORECASE)
                            if match:
                                state_tax = self._parse_amount(match.group(1))
                        
                        # Employer name from table
                        if not employer:
                            for kw, emp_name in employer_keywords.items():
                                if kw in row_text.lower():
                                    employer = emp_name
                                    break
                            if not employer:
                                emp_match = re.search(r"Employer'?s?\s*name.*?([\w\s]+(?:Inc|LLC|Corp)\.?)", row_text, re.IGNORECASE)
                                if emp_match:
                                    employer = emp_match.group(1).strip()
                        
                        # Employee name from table
                        if not employee_name:
                            if 'JAYA AGRAWAL' in row_text.upper():
                                employee_name = 'Jaya Agrawal'
                            elif 'NEEL KAMAL' in row_text.upper():
                                employee_name = 'Neel Kamal'
                
                # Strategy 2: Parse raw text for numeric patterns (Splunk format)
                # This format often has values in the first few lines
                lines = text.split('\n')
                
                # Look for paired values like "126114.84 18005.76"
                for line in lines[:20]:  # First 20 lines usually contain the data
                    amounts = re.findall(r'([\d,]+\.?\d+)', line)
                    if len(amounts) >= 2:
                        # Check if these could be wages and federal tax
                        val1 = self._parse_amount(amounts[0])
                        val2 = self._parse_amount(amounts[1])
                        
                        # Wages are typically larger, federal tax is smaller but significant
                        if wages == 0 and val1 > 10000 and val2 > 1000 and val1 > val2 * 2:
                            # Could be wages and federal tax
                            wages = val1
                            federal_tax = val2
                
                # Strategy 3: Look for specific patterns in full text
                if wages == 0:
                    # Pattern: "1 Wages,tips,othercomp.\n30189.87"
                    match = re.search(r'1\s*Wages[^\n]*\n([\d,]+\.?\d+)', text, re.IGNORECASE)
                    if match:
                        wages = self._parse_amount(match.group(1))
                
                if federal_tax == 0:
                    match = re.search(r'2\s*Federal[^\n]*\n([\d,]+\.?\d+)', text, re.IGNORECASE)
                    if match:
                        federal_tax = self._parse_amount(match.group(1))
                
                if ss_wages == 0:
                    match = re.search(r'3\s*Social[^\n]*\n([\d,]+\.?\d+)', text, re.IGNORECASE)
                    if match:
                        ss_wages = self._parse_amount(match.group(1))
                
                if ss_tax == 0:
                    match = re.search(r'4\s*Social[^\n]*\n([\d,]+\.?\d+)', text, re.IGNORECASE)
                    if match:
                        ss_tax = self._parse_amount(match.group(1))
                
                if medicare_wages == 0:
                    match = re.search(r'5\s*Medicare[^\n]*\n([\d,]+\.?\d+)', text, re.IGNORECASE)
                    if match:
                        medicare_wages = self._parse_amount(match.group(1))
                
                if medicare_tax == 0:
                    match = re.search(r'6\s*Medicare[^\n]*\n([\d,]+\.?\d+)', text, re.IGNORECASE)
                    if match:
                        medicare_tax = self._parse_amount(match.group(1))
                
                # State tax - look for CA line
                if state_tax == 0:
                    match = re.search(r'CA\s+[\d-]+\s+([\d,]+\.?\d+)\s+([\d,]+\.?\d+)', text)
                    if match:
                        state_wages = self._parse_amount(match.group(1))
                        state_tax = self._parse_amount(match.group(2))
                
                if state_wages == 0:
                    match = re.search(r'16\s*State\s*wages[^\n]*([\d,]+\.?\d+)', text, re.IGNORECASE)
                    if match:
                        state_wages = self._parse_amount(match.group(1))
                
                if state_tax == 0:
                    match = re.search(r'17\s*State\s*income\s*tax[^\n]*([\d,]+\.?\d+)', text, re.IGNORECASE)
                    if match:
                        state_tax = self._parse_amount(match.group(1))
                
                # Box 12 D - 401(k) contributions
                k401_match = re.search(r'(?:12d?|D)\s*([\d,]+\.?\d+)', text)
                if k401_match:
                    retirement_401k = self._parse_amount(k401_match.group(1))
                
                # ===== EXTRACT EMPLOYER FROM TEXT =====
                if not employer:
                    # Common employer patterns
                    for kw, emp_name in employer_keywords.items():
                        if kw in text.lower():
                            employer = emp_name
                            break
                    
                    # TriNet special handling (PEO)
                    if not employer and 'trinet' in text.lower():
                        employer = "TriNet (PEO)"
                
                # ===== EXTRACT EMPLOYEE NAME FROM TEXT =====
                if not employee_name:
                    # Look for known names
                    if 'jaya agrawal' in text.lower():
                        employee_name = 'Jaya Agrawal'
                    elif 'neel kamal' in text.lower():
                        employee_name = 'Neel Kamal'
                    else:
                        # Look for name pattern
                        name_match = re.search(r'(?:Employee|Name)[^\n]*\n([A-Z][a-z]+\s+[A-Z][a-z]+)', text)
                        if name_match:
                            employee_name = name_match.group(1).strip()
                
                # ===== VALIDATE AND RETURN =====
                if wages == 0:
                    print(f"Could not extract wages from {filepath}")
                    return None
                
                # Fill in missing values if we have enough context
                if ss_wages == 0:
                    ss_wages = min(wages, 160200)  # SS wage base for 2023
                if medicare_wages == 0:
                    medicare_wages = wages
                
                return W2Income(
                    employee_name=employee_name,
                    employer=employer,
                    year=year,
                    wages=wages,
                    federal_tax_withheld=federal_tax,
                    social_security_wages=ss_wages,
                    social_security_tax=ss_tax,
                    medicare_wages=medicare_wages,
                    medicare_tax=medicare_tax,
                    retirement_401k=retirement_401k,
                    state_wages=state_wages,
                    state_tax_withheld=state_tax,
                )
                
        except Exception as e:
            print(f"Error parsing W-2 {filepath}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _parse_cisco_payslip(self, filepath: Path) -> Optional[SalaryPayslip]:
        """Parse a Cisco payslip PDF."""
        if pdfplumber is None:
            print("pdfplumber not installed, cannot parse PDFs")
            return None
            
        try:
            with pdfplumber.open(filepath) as pdf:
                text = ""
                for page in pdf.pages:
                    text += page.extract_text() or ""
                
                if not text:
                    return None
                
                # Extract employee name
                name_match = re.search(r'Pers\. No \d+\s*\n([A-Za-z ]+)', text)
                employee_name = name_match.group(1).strip() if name_match else "Unknown"
                
                # Extract dates
                period_start = None
                period_end = None
                pay_date = None
                
                start_match = re.search(r'Period Beginning:\s*(\d{2}/\d{2}/\d{4})', text)
                if start_match:
                    period_start = self._parse_date(start_match.group(1))
                
                end_match = re.search(r'Period Ending:\s*(\d{2}/\d{2}/\d{4})', text)
                if end_match:
                    period_end = self._parse_date(end_match.group(1))
                
                date_match = re.search(r'Check Date:\s*(\d{2}/\d{2}/\d{4})', text)
                if date_match:
                    pay_date = self._parse_date(date_match.group(1))
                
                if not pay_date:
                    return None
                
                year = pay_date.year
                
                # Extract Gross Pay YTD
                gross_ytd_match = re.search(r'Gross Pay\s+[\d,]+\.?\d*\s+([\d,]+\.?\d*)', text)
                gross_pay_ytd = self._parse_amount(gross_ytd_match.group(1)) if gross_ytd_match else 0.0
                
                # Extract Net Pay YTD
                net_ytd_match = re.search(r'Total Net Pay\s+[\d,]+\.?\d*\s+([\d,]+\.?\d*)', text)
                net_pay_ytd = self._parse_amount(net_ytd_match.group(1)) if net_ytd_match else 0.0
                
                # Extract Federal Withholding YTD
                federal_match = re.search(r'Withholding Tax\s+[\d,]+\.?\d*-?\s+([\d,]+\.?\d*)-?', text)
                federal_tax_ytd = self._parse_amount(federal_match.group(1)) if federal_match else 0.0
                
                # Extract CA State Withholding YTD (look for Tax Deductions: California section)
                # Format: "Tax Deductions: California ... \nWithholding Tax 1,415.36- 8,704.93-"
                state_match = re.search(r'Tax Deductions: California.*?\nWithholding Tax\s+([\d,]+\.?\d*)-?\s+([\d,]+\.?\d*)-?', text, re.DOTALL)
                state_tax_ytd = self._parse_amount(state_match.group(2)) if state_match else 0.0
                
                # Extract Social Security YTD
                ss_match = re.search(r'Social Security Tax\s+[\d,]+\.?\d*-?\s+([\d,]+\.?\d*)-?', text)
                social_security_ytd = self._parse_amount(ss_match.group(1)) if ss_match else 0.0
                
                # Extract Medicare YTD
                medicare_match = re.search(r'Medicare Tax\s+[\d,]+\.?\d*-?\s+([\d,]+\.?\d*)-?', text)
                medicare_ytd = self._parse_amount(medicare_match.group(1)) if medicare_match else 0.0
                
                # Extract Regular Salary YTD
                salary_match = re.search(r'Regular Salary\s+[\d.]+\s+[\d,]+\.?\d*\s+([\d,]+\.?\d*)', text)
                regular_salary_ytd = self._parse_amount(salary_match.group(1)) if salary_match else 0.0
                
                # Extract 401k YTD
                k401_match = re.search(r'401\(k\) PreTax\s+[\w\s]*[\d,]+\.?\d*-?\s+([\d,]+\.?\d*)-?', text)
                retirement_401k_ytd = self._parse_amount(k401_match.group(1)) if k401_match else 0.0
                
                return SalaryPayslip(
                    employee_name=employee_name,
                    employer="Cisco Systems Inc",
                    pay_date=pay_date,
                    period_start=period_start or pay_date,
                    period_end=period_end or pay_date,
                    year=year,
                    gross_pay_ytd=gross_pay_ytd,
                    net_pay_ytd=net_pay_ytd,
                    federal_tax_ytd=federal_tax_ytd,
                    state_tax_ytd=state_tax_ytd,
                    social_security_ytd=social_security_ytd,
                    medicare_ytd=medicare_ytd,
                    retirement_401k_ytd=retirement_401k_ytd,
                    regular_salary_ytd=regular_salary_ytd,
                )
                
        except Exception as e:
            print(f"Error parsing payslip {filepath}: {e}")
            return None

    def _normalize_name(self, name: str) -> str:
        """Normalize employee name for matching."""
        # Convert to lowercase and remove extra spaces
        normalized = name.lower().strip()
        # Handle common variations (e.g., "Neel Kamal" -> "neel")
        # For this family, we know Neel and Jaya are the key names
        if 'neel' in normalized:
            return 'Neel'
        elif 'jaya' in normalized:
            return 'Jaya'
        return name.title()

    def load_all_payslips(self) -> Dict[str, SalaryIncome]:
        """Load all payslip and W-2 data. Tries database first, then parses files."""
        self.salaries = {}
        self.w2_data = {}
        
        # Load payslips from salary directory (always parse these as they're frequently updated)
        if self.data_dir.exists():
            pdf_files = list(self.data_dir.glob('*.pdf'))
            
            for pdf_file in pdf_files:
                payslip = self._parse_cisco_payslip(pdf_file)
                if payslip:
                    name = self._normalize_name(payslip.employee_name)
                    
                    if name not in self.salaries:
                        self.salaries[name] = SalaryIncome(
                            name=name,
                            employer=payslip.employer,
                        )
                    
                    self.salaries[name].payslips.append(payslip)
                    
                    # Update yearly totals (use the most recent YTD for each year)
                    year = payslip.year
                    current_gross = self.salaries[name].yearly_gross.get(year, 0)
                    if payslip.gross_pay_ytd > current_gross:
                        self.salaries[name].yearly_gross[year] = payslip.gross_pay_ytd
                        self.salaries[name].yearly_net[year] = payslip.net_pay_ytd
                        self.salaries[name].yearly_federal_tax[year] = payslip.federal_tax_ytd
                        self.salaries[name].yearly_state_tax[year] = payslip.state_tax_ytd
        else:
            print(f"Salary data directory not found: {self.data_dir}")
        
        # Load W-2 data - try database first, fall back to parsing files
        loaded_from_db = self._load_w2_from_database()
        if not loaded_from_db:
            # No data in database, parse files directly
            self._load_w2_forms()
        
        return self.salaries

    def _load_w2_forms(self):
        """Load W-2 forms from tax returns directory and integrate into salary data."""
        if not self.tax_returns_dir.exists():
            print(f"Tax returns directory not found: {self.tax_returns_dir}")
            return
        
        # Find all W-2 PDFs recursively
        w2_patterns = ['**/W-2*.pdf', '**/w-2*.pdf', '**/W2*.pdf', '**/w2*.pdf', '**/*W-2*.pdf', '**/*w2*.pdf', '**/*W2.pdf', '**/*w2.pdf']
        w2_files = []
        for pattern in w2_patterns:
            w2_files.extend(self.tax_returns_dir.glob(pattern))
        
        # Remove duplicates
        w2_files = list(set(w2_files))
        
        for w2_file in w2_files:
            w2 = self._parse_w2(w2_file)
            if w2 and w2.wages > 0:
                name = self._normalize_name(w2.employee_name)
                
                # Store W-2 data
                if name not in self.w2_data:
                    self.w2_data[name] = []
                self.w2_data[name].append(w2)
                
                # Also add to salaries for unified access
                if name not in self.salaries:
                    self.salaries[name] = SalaryIncome(
                        name=name,
                        employer=w2.employer,
                    )
                
                # Update yearly totals from W-2
                # W-2 is authoritative for annual totals
                year = w2.year
                current_gross = self.salaries[name].yearly_gross.get(year, 0)
                
                # Track if we had payslip data (which has more reliable employer info)
                had_payslip_data = len(self.salaries[name].payslips) > 0
                
                # W-2 wages should be SUMMED across all employers for the same year
                # (someone can have multiple W-2s from different employers)
                self.salaries[name].yearly_gross[year] = current_gross + w2.wages
                self.salaries[name].yearly_net[year] = self.salaries[name].yearly_net.get(year, 0) + w2.net_income
                self.salaries[name].yearly_federal_tax[year] = self.salaries[name].yearly_federal_tax.get(year, 0) + w2.federal_tax_withheld
                self.salaries[name].yearly_state_tax[year] = self.salaries[name].yearly_state_tax.get(year, 0) + w2.state_tax_withheld
                # Only update employer from W-2 if we don't have payslip data
                # (payslips have more reliable employer info)
                # For multiple employers, we keep the first one found
                if w2.employer and not had_payslip_data and not self.salaries[name].employer:
                    self.salaries[name].employer = w2.employer

    def _load_w2_from_database(self) -> bool:
        """Load W-2 data from database. Returns True if data was found."""
        if self.db is None:
            return False
        
        from app.modules.income.models import W2Record
        
        try:
            records = self.db.query(W2Record).all()
            if not records:
                return False
            
            for record in records:
                name = self._normalize_name(record.employee_name)
                
                w2 = W2Income(
                    employee_name=record.employee_name,
                    employer=record.employer,
                    year=record.tax_year,
                    wages=float(record.wages),
                    federal_tax_withheld=float(record.federal_tax_withheld),
                    social_security_wages=float(record.social_security_wages),
                    social_security_tax=float(record.social_security_tax),
                    medicare_wages=float(record.medicare_wages),
                    medicare_tax=float(record.medicare_tax),
                    retirement_401k=float(record.retirement_401k),
                    state_wages=float(record.state_wages),
                    state_tax_withheld=float(record.state_tax_withheld),
                )
                
                # Store W-2 data
                if name not in self.w2_data:
                    self.w2_data[name] = []
                self.w2_data[name].append(w2)
                
                # Also add to salaries for unified access
                if name not in self.salaries:
                    self.salaries[name] = SalaryIncome(
                        name=name,
                        employer=w2.employer,
                    )
                
                # Update yearly totals from W-2
                # W-2 wages should be SUMMED across all employers for the same year
                year = w2.year
                current_gross = self.salaries[name].yearly_gross.get(year, 0)
                had_payslip_data = len(self.salaries[name].payslips) > 0
                
                self.salaries[name].yearly_gross[year] = current_gross + w2.wages
                self.salaries[name].yearly_net[year] = self.salaries[name].yearly_net.get(year, 0) + w2.net_income
                self.salaries[name].yearly_federal_tax[year] = self.salaries[name].yearly_federal_tax.get(year, 0) + w2.federal_tax_withheld
                self.salaries[name].yearly_state_tax[year] = self.salaries[name].yearly_state_tax.get(year, 0) + w2.state_tax_withheld
                # Only update employer from W-2 if we don't have payslip data
                # For multiple employers, we keep the first one found
                if w2.employer and not had_payslip_data and not self.salaries[name].employer:
                    self.salaries[name].employer = w2.employer
            
            return len(records) > 0
        except Exception as e:
            print(f"Error loading W-2 from database: {e}")
            return False

    def import_w2_to_database(self) -> Dict:
        """Parse all W-2 files and import them to the database."""
        if self.db is None:
            return {"error": "No database session available"}
        
        from app.modules.income.models import W2Record
        
        if not self.tax_returns_dir.exists():
            return {"error": f"Tax returns directory not found: {self.tax_returns_dir}"}
        
        # Find all W-2 PDFs recursively
        w2_patterns = ['**/W-2*.pdf', '**/w-2*.pdf', '**/W2*.pdf', '**/w2*.pdf', '**/*W-2*.pdf', '**/*w2*.pdf', '**/*W2.pdf', '**/*w2.pdf']
        w2_files = []
        for pattern in w2_patterns:
            w2_files.extend(self.tax_returns_dir.glob(pattern))
        
        # Remove duplicates
        w2_files = list(set(w2_files))
        
        imported = 0
        skipped = 0
        errors = []
        
        for w2_file in w2_files:
            try:
                w2 = self._parse_w2(w2_file)
                if w2 and w2.wages > 0:
                    # Check if already exists - first by exact employer match
                    existing = self.db.query(W2Record).filter(
                        W2Record.employee_name == w2.employee_name,
                        W2Record.employer == w2.employer,
                        W2Record.tax_year == w2.year
                    ).first()
                    
                    # Also check by wages amount - same employee, year, and wages = same W2
                    # (handles cases where employer name varies: "Aviatrix" vs "TriNet (Aviatrix)")
                    if not existing:
                        existing = self.db.query(W2Record).filter(
                            W2Record.employee_name == w2.employee_name,
                            W2Record.tax_year == w2.year,
                            W2Record.wages == Decimal(str(w2.wages))
                        ).first()
                    
                    if existing:
                        # Update if wages are higher (more complete data)
                        if w2.wages > float(existing.wages):
                            existing.wages = Decimal(str(w2.wages))
                            existing.federal_tax_withheld = Decimal(str(w2.federal_tax_withheld))
                            existing.social_security_wages = Decimal(str(w2.social_security_wages))
                            existing.social_security_tax = Decimal(str(w2.social_security_tax))
                            existing.medicare_wages = Decimal(str(w2.medicare_wages))
                            existing.medicare_tax = Decimal(str(w2.medicare_tax))
                            existing.retirement_401k = Decimal(str(w2.retirement_401k))
                            existing.state_wages = Decimal(str(w2.state_wages))
                            existing.state_tax_withheld = Decimal(str(w2.state_tax_withheld))
                            existing.net_income = Decimal(str(w2.net_income))
                            existing.source_file = str(w2_file)
                            imported += 1
                        else:
                            skipped += 1
                    else:
                        # Create new record
                        record = W2Record(
                            employee_name=w2.employee_name,
                            employer=w2.employer,
                            tax_year=w2.year,
                            wages=Decimal(str(w2.wages)),
                            federal_tax_withheld=Decimal(str(w2.federal_tax_withheld)),
                            social_security_wages=Decimal(str(w2.social_security_wages)),
                            social_security_tax=Decimal(str(w2.social_security_tax)),
                            medicare_wages=Decimal(str(w2.medicare_wages)),
                            medicare_tax=Decimal(str(w2.medicare_tax)),
                            retirement_401k=Decimal(str(w2.retirement_401k)),
                            state_wages=Decimal(str(w2.state_wages)),
                            state_tax_withheld=Decimal(str(w2.state_tax_withheld)),
                            net_income=Decimal(str(w2.net_income)),
                            source_file=str(w2_file),
                        )
                        self.db.add(record)
                        imported += 1
                else:
                    errors.append(f"Could not parse: {w2_file}")
            except Exception as e:
                errors.append(f"Error processing {w2_file}: {str(e)}")
        
        self.db.commit()
        
        return {
            "status": "success",
            "files_processed": len(w2_files),
            "records_imported": imported,
            "records_skipped": skipped,
            "errors": errors[:10] if errors else []  # Limit errors in response
        }

    def get_salary_summary(self) -> Dict:
        """Get summary of all salary income."""
        if not self.salaries:
            self.load_all_payslips()
        
        employees = []
        total_gross = 0.0
        total_net = 0.0
        
        for name, salary in self.salaries.items():
            employee_data = {
                'name': name,
                'employer': salary.employer,
                'yearly_data': [],
                'total_gross': sum(salary.yearly_gross.values()),
                'total_net': sum(salary.yearly_net.values()),
            }
            
            for year in sorted(salary.yearly_gross.keys(), reverse=True):
                employee_data['yearly_data'].append({
                    'year': year,
                    'gross': salary.yearly_gross.get(year, 0),
                    'net': salary.yearly_net.get(year, 0),
                    'federal_tax': salary.yearly_federal_tax.get(year, 0),
                    'state_tax': salary.yearly_state_tax.get(year, 0),
                })
            
            total_gross += employee_data['total_gross']
            total_net += employee_data['total_net']
            employees.append(employee_data)
        
        return {
            'employees': employees,
            'total_gross_income': total_gross,
            'total_net_income': total_net,
            'employee_count': len(employees),
        }

    def get_salary_by_year(self, year: int) -> Dict:
        """Get salary income filtered by year."""
        if not self.salaries:
            self.load_all_payslips()
        
        employees = []
        total_gross = 0.0
        total_net = 0.0
        
        for name, salary in self.salaries.items():
            if year in salary.yearly_gross:
                employee_data = {
                    'name': name,
                    'employer': salary.employer,
                    'year': year,
                    'gross': salary.yearly_gross.get(year, 0),
                    'net': salary.yearly_net.get(year, 0),
                    'federal_tax': salary.yearly_federal_tax.get(year, 0),
                    'state_tax': salary.yearly_state_tax.get(year, 0),
                }
                total_gross += employee_data['gross']
                total_net += employee_data['net']
                employees.append(employee_data)
        
        return {
            'year': year,
            'employees': employees,
            'total_gross_income': total_gross,
            'total_net_income': total_net,
        }


# Singleton instance
_salary_service: Optional[SalaryService] = None


def get_salary_service(db: Session = None) -> SalaryService:
    """Get or create the salary service singleton."""
    global _salary_service
    if _salary_service is None:
        _salary_service = SalaryService(db=db)
        _salary_service.load_all_payslips()
    elif db is not None and _salary_service.db is None:
        # Update db session if provided and not already set
        _salary_service.db = db
    return _salary_service


def reset_salary_service() -> None:
    """Reset the salary service singleton to force reload."""
    global _salary_service
    _salary_service = None

