"""
Income Services - Parse Robinhood transaction files for options and dividend income.
"""

import csv
import os
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class OptionsTransaction:
    """Represents a single options transaction."""
    date: datetime
    symbol: str
    description: str
    trans_code: str  # STO, BTC, OEXP, OASGN
    quantity: int
    price: float
    amount: float
    account_name: str
    option_type: str  # 'call' or 'put'
    strike: Optional[float] = None
    expiry: Optional[str] = None


@dataclass
class DividendTransaction:
    """Represents a dividend payment."""
    date: datetime
    symbol: str
    description: str
    amount: float
    account_name: str
    shares: Optional[float] = None
    dividend_per_share: Optional[float] = None


@dataclass
class InterestTransaction:
    """Represents an interest payment."""
    date: datetime
    description: str
    amount: float
    account_name: str
    source: str = 'robinhood'  # or 'bank' for future bank statements


@dataclass
class StockSaleTransaction:
    """Represents a stock sale transaction."""
    date: datetime
    symbol: str
    description: str
    quantity: float
    price: float
    proceeds: float  # Gross proceeds from sale
    account_name: str


@dataclass
class StockLendingTransaction:
    """Represents stock lending income."""
    date: datetime
    symbol: str
    description: str
    amount: float
    account_name: str


@dataclass
class AccountIncome:
    """Income data for a single account."""
    account_name: str
    owner: str  # 'Neel' or 'Jaya'
    account_type: str  # 'individual', 'retirement', 'ira'
    total_options_income: float = 0.0
    total_dividend_income: float = 0.0
    total_interest_income: float = 0.0
    total_stock_lending: float = 0.0
    total_stock_sales_proceeds: float = 0.0  # Gross proceeds from stock sales
    options_transactions: List[OptionsTransaction] = field(default_factory=list)
    dividend_transactions: List[DividendTransaction] = field(default_factory=list)
    interest_transactions: List[InterestTransaction] = field(default_factory=list)
    stock_sale_transactions: List[StockSaleTransaction] = field(default_factory=list)
    stock_lending_transactions: List[StockLendingTransaction] = field(default_factory=list)
    monthly_options: Dict[str, float] = field(default_factory=dict)
    monthly_dividends: Dict[str, float] = field(default_factory=dict)
    monthly_interest: Dict[str, float] = field(default_factory=dict)
    monthly_stock_sales: Dict[str, float] = field(default_factory=dict)
    monthly_stock_lending: Dict[str, float] = field(default_factory=dict)


class IncomeService:
    """Service to parse and aggregate income from Robinhood transaction files."""

    # Transaction codes that represent options activity
    OPTIONS_CODES = {'STO', 'BTC', 'OEXP', 'OASGN'}
    
    # Transaction codes for dividends
    DIVIDEND_CODES = {'CDIV'}
    
    # Transaction codes for interest
    INTEREST_CODES = {'INT'}
    
    # Stock lending income
    STOCK_LENDING_CODES = {'SLIP'}
    
    # Stock buy/sell transactions (uppercase to match .upper() transformation)
    STOCK_BUY_CODES = {'BUY'}
    STOCK_SELL_CODES = {'SELL'}

    def __init__(self, data_dir: str = None):
        """Initialize the service with the data directory."""
        if data_dir is None:
            # Default to the processed robinhood folder
            base_dir = Path(__file__).parent.parent.parent.parent.parent
            data_dir = base_dir / "data" / "processed" / "investments" / "robinhood"
        self.data_dir = Path(data_dir)
        self.accounts: Dict[str, AccountIncome] = {}

    def _parse_amount(self, amount_str: str) -> float:
        """Parse amount string like '$123.45' or '($123.45)' to float."""
        if not amount_str or amount_str.strip() == '':
            return 0.0
        
        # Remove whitespace
        amount_str = amount_str.strip()
        
        # Check for negative (parentheses)
        is_negative = '(' in amount_str and ')' in amount_str
        
        # Remove currency symbols and parentheses
        cleaned = re.sub(r'[$(),]', '', amount_str)
        
        try:
            value = float(cleaned)
            return -value if is_negative else value
        except ValueError:
            return 0.0

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime."""
        if not date_str or date_str.strip() == '':
            return None
        
        date_str = date_str.strip()
        
        # Try different formats
        formats = [
            '%m/%d/%Y',  # 11/21/2025
            '%m/%d/%y',  # 11/21/25
            '%Y-%m-%d',  # 2025-11-21
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        return None

    def _parse_option_description(self, description: str) -> Tuple[Optional[str], Optional[str], Optional[float]]:
        """
        Parse option description like 'AAPL 11/28/2025 Call $280.00'
        Returns (option_type, expiry, strike)
        """
        if not description:
            return None, None, None
        
        # Pattern: SYMBOL DATE TYPE $STRIKE
        # e.g., "AAPL 11/28/2025 Call $280.00"
        pattern = r'(\w+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(Call|Put)\s+\$?([\d,.]+)'
        match = re.search(pattern, description, re.IGNORECASE)
        
        if match:
            option_type = match.group(3).lower()
            expiry = match.group(2)
            strike = float(match.group(4).replace(',', ''))
            return option_type, expiry, strike
        
        return None, None, None

    def _extract_dividend_info(self, description: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Extract shares and dividend per share from description.
        e.g., 'Cash Div: R/D 2025-11-10 P/D 2025-11-13 - 1700 shares at 0.26'
        Returns (shares, dividend_per_share)
        """
        if not description:
            return None, None
        
        pattern = r'(\d+(?:\.\d+)?)\s+shares\s+at\s+([\d.]+)'
        match = re.search(pattern, description)
        
        if match:
            shares = float(match.group(1))
            dps = float(match.group(2))
            return shares, dps
        
        return None, None

    def _determine_account_info(self, filename: str) -> Tuple[str, str, str]:
        """
        Determine account owner, name, and type from filename.
        Returns (owner, account_name, account_type)
        """
        filename_lower = filename.lower()
        
        # Determine owner
        if 'jaya' in filename_lower:
            owner = 'Jaya'
        elif 'neel' in filename_lower:
            owner = 'Neel'
        else:
            owner = 'Unknown'
        
        # Determine account type
        if 'retirement' in filename_lower or 'ira' in filename_lower:
            account_type = 'retirement'
        else:
            account_type = 'individual'
        
        # Create account name
        if account_type == 'retirement':
            account_name = f"{owner}'s Retirement"
        else:
            account_name = f"{owner}'s Individual"
        
        return owner, account_name, account_type

    def _parse_csv_file(self, filepath: Path) -> List[dict]:
        """Parse a single CSV file and return list of transactions."""
        transactions = []
        
        try:
            # First pass: find the header line
            header_idx = 0
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                for i, line in enumerate(f):
                    if 'Activity Date' in line or 'activity date' in line.lower():
                        header_idx = i
                        break
            
            # Second pass: read CSV from header using DictReader
            # Use newline='' to let csv module handle line endings properly for multi-line fields
            with open(filepath, 'r', encoding='utf-8-sig', newline='') as f:
                # Skip lines before header
                for _ in range(header_idx):
                    next(f)
                
                reader = csv.DictReader(f)
                
                for row in reader:
                    # Skip empty rows or disclaimer rows
                    activity_date = row.get('Activity Date', '')
                    if not activity_date or activity_date.strip() == '':
                        continue
                    if 'data provided' in activity_date.lower():
                        continue
                    
                    transactions.append(row)
                    
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
        
        return transactions

    def _process_transaction(self, row: dict, account_name: str, owner: str, account_type: str):
        """Process a single transaction row."""
        trans_code = row.get('Trans Code', '').strip().upper()
        
        if not trans_code:
            return
        
        # Get or create account
        if account_name not in self.accounts:
            self.accounts[account_name] = AccountIncome(
                account_name=account_name,
                owner=owner,
                account_type=account_type
            )
        
        account = self.accounts[account_name]
        
        # Parse common fields
        date = self._parse_date(row.get('Activity Date', ''))
        if not date:
            return
        
        amount = self._parse_amount(row.get('Amount', ''))
        symbol = row.get('Instrument', '').strip()
        description = row.get('Description', '').strip()
        quantity_str = row.get('Quantity', '').strip()
        price_str = row.get('Price', '').strip()
        
        try:
            quantity = int(float(quantity_str)) if quantity_str else 0
        except (ValueError, TypeError):
            quantity = 0
        
        price = self._parse_amount(price_str)
        
        month_key = date.strftime('%Y-%m')
        
        # Process based on transaction type
        if trans_code in self.OPTIONS_CODES:
            # Options transaction
            option_type, expiry, strike = self._parse_option_description(description)
            
            txn = OptionsTransaction(
                date=date,
                symbol=symbol,
                description=description,
                trans_code=trans_code,
                quantity=quantity,
                price=price,
                amount=amount,
                account_name=account_name,
                option_type=option_type or 'unknown',
                strike=strike,
                expiry=expiry
            )
            account.options_transactions.append(txn)
            
            # Track monthly options income
            # STO = income (positive), BTC = expense (negative)
            if month_key not in account.monthly_options:
                account.monthly_options[month_key] = 0.0
            account.monthly_options[month_key] += amount
            account.total_options_income += amount
            
        elif trans_code in self.DIVIDEND_CODES:
            # Dividend transaction
            shares, dps = self._extract_dividend_info(description)
            
            txn = DividendTransaction(
                date=date,
                symbol=symbol,
                description=description,
                amount=amount,
                account_name=account_name,
                shares=shares,
                dividend_per_share=dps
            )
            account.dividend_transactions.append(txn)
            
            # Track monthly dividends
            if month_key not in account.monthly_dividends:
                account.monthly_dividends[month_key] = 0.0
            account.monthly_dividends[month_key] += amount
            account.total_dividend_income += amount
            
        elif trans_code in self.INTEREST_CODES:
            txn = InterestTransaction(
                date=date,
                description=description or 'Interest Payment',
                amount=amount,
                account_name=account_name,
                source='robinhood'
            )
            account.interest_transactions.append(txn)
            
            # Track monthly interest
            if month_key not in account.monthly_interest:
                account.monthly_interest[month_key] = 0.0
            account.monthly_interest[month_key] += amount
            account.total_interest_income += amount
            
        elif trans_code in self.STOCK_LENDING_CODES:
            txn = StockLendingTransaction(
                date=date,
                symbol=symbol,
                description=description or 'Stock Lending',
                amount=amount,
                account_name=account_name
            )
            account.stock_lending_transactions.append(txn)
            
            # Track monthly stock lending
            if month_key not in account.monthly_stock_lending:
                account.monthly_stock_lending[month_key] = 0.0
            account.monthly_stock_lending[month_key] += amount
            account.total_stock_lending += amount
            
        elif trans_code in self.STOCK_SELL_CODES:
            # Stock sale - track proceeds (positive amount means income)
            txn = StockSaleTransaction(
                date=date,
                symbol=symbol,
                description=description,
                quantity=quantity,
                price=price,
                proceeds=amount,  # Proceeds from sale
                account_name=account_name
            )
            account.stock_sale_transactions.append(txn)
            
            # Track monthly stock sales (only positive proceeds)
            if amount > 0:
                if month_key not in account.monthly_stock_sales:
                    account.monthly_stock_sales[month_key] = 0.0
                account.monthly_stock_sales[month_key] += amount
                account.total_stock_sales_proceeds += amount

    def load_all_transactions(self) -> Dict[str, AccountIncome]:
        """Load and process all CSV files from the data directory."""
        self.accounts = {}  # Reset
        
        if not self.data_dir.exists():
            print(f"Data directory not found: {self.data_dir}")
            return self.accounts
        
        # Find all CSV files
        csv_files = list(self.data_dir.glob('*.csv'))
        
        for csv_file in csv_files:
            # Determine account info from filename
            owner, account_name, account_type = self._determine_account_info(csv_file.name)
            
            # Parse the CSV
            transactions = self._parse_csv_file(csv_file)
            
            # Process each transaction
            for row in transactions:
                self._process_transaction(row, account_name, owner, account_type)
        
        return self.accounts

    def get_consolidated_options_income(self) -> Dict:
        """Get consolidated options income across all accounts."""
        if not self.accounts:
            self.load_all_transactions()
        
        total_income = 0.0
        by_account = {}
        monthly_consolidated = defaultdict(float)
        all_transactions = []
        
        for account_name, account in self.accounts.items():
            total_income += account.total_options_income
            by_account[account_name] = {
                'owner': account.owner,
                'account_type': account.account_type,
                'total': account.total_options_income,
                'transaction_count': len(account.options_transactions),
                'monthly': account.monthly_options,
            }
            
            # Consolidate monthly data
            for month, amount in account.monthly_options.items():
                monthly_consolidated[month] += amount
            
            # Add transactions with account info
            for txn in account.options_transactions:
                all_transactions.append({
                    'date': txn.date.isoformat(),
                    'symbol': txn.symbol,
                    'description': txn.description,
                    'trans_code': txn.trans_code,
                    'quantity': txn.quantity,
                    'price': txn.price,
                    'amount': txn.amount,
                    'account': account_name,
                    'option_type': txn.option_type,
                    'strike': txn.strike,
                    'expiry': txn.expiry,
                })
        
        # Sort monthly data
        sorted_monthly = dict(sorted(monthly_consolidated.items()))
        
        # Sort transactions by date descending
        all_transactions.sort(key=lambda x: x['date'], reverse=True)
        
        return {
            'total_income': total_income,
            'by_account': by_account,
            'monthly': sorted_monthly,
            'transactions': all_transactions[:200],  # Limit to recent 200
            'transaction_count': len(all_transactions),
        }

    def get_consolidated_dividend_income(self) -> Dict:
        """Get consolidated dividend income across all accounts."""
        if not self.accounts:
            self.load_all_transactions()
        
        total_income = 0.0
        by_account = {}
        monthly_consolidated = defaultdict(float)
        by_symbol = defaultdict(float)
        all_transactions = []
        
        for account_name, account in self.accounts.items():
            total_income += account.total_dividend_income
            by_account[account_name] = {
                'owner': account.owner,
                'account_type': account.account_type,
                'total': account.total_dividend_income,
                'transaction_count': len(account.dividend_transactions),
                'monthly': account.monthly_dividends,
            }
            
            # Consolidate monthly data
            for month, amount in account.monthly_dividends.items():
                monthly_consolidated[month] += amount
            
            # Track by symbol
            for txn in account.dividend_transactions:
                by_symbol[txn.symbol] += txn.amount
                all_transactions.append({
                    'date': txn.date.isoformat(),
                    'symbol': txn.symbol,
                    'description': txn.description,
                    'amount': txn.amount,
                    'account': account_name,
                    'shares': txn.shares,
                    'dividend_per_share': txn.dividend_per_share,
                })
        
        # Sort monthly data
        sorted_monthly = dict(sorted(monthly_consolidated.items()))
        
        # Sort by_symbol by amount descending
        sorted_by_symbol = dict(sorted(by_symbol.items(), key=lambda x: x[1], reverse=True))
        
        # Sort transactions by date descending
        all_transactions.sort(key=lambda x: x['date'], reverse=True)
        
        return {
            'total_income': total_income,
            'by_account': by_account,
            'monthly': sorted_monthly,
            'by_symbol': sorted_by_symbol,
            'transactions': all_transactions[:100],  # Limit to recent 100
            'transaction_count': len(all_transactions),
        }

    def get_consolidated_interest_income(self) -> Dict:
        """Get consolidated interest income across all accounts."""
        if not self.accounts:
            self.load_all_transactions()
        
        total_income = 0.0
        by_account = {}
        monthly_consolidated = defaultdict(float)
        all_transactions = []
        
        for account_name, account in self.accounts.items():
            total_income += account.total_interest_income
            by_account[account_name] = {
                'owner': account.owner,
                'account_type': account.account_type,
                'total': account.total_interest_income,
                'transaction_count': len(account.interest_transactions),
                'monthly': account.monthly_interest,
            }
            
            # Consolidate monthly data
            for month, amount in account.monthly_interest.items():
                monthly_consolidated[month] += amount
            
            # Add transactions with account info
            for txn in account.interest_transactions:
                all_transactions.append({
                    'date': txn.date.isoformat(),
                    'description': txn.description,
                    'amount': txn.amount,
                    'account': account_name,
                    'source': txn.source,
                })
        
        # Sort monthly data
        sorted_monthly = dict(sorted(monthly_consolidated.items()))
        
        # Sort transactions by date descending
        all_transactions.sort(key=lambda x: x['date'], reverse=True)
        
        return {
            'total_income': total_income,
            'by_account': by_account,
            'monthly': sorted_monthly,
            'transactions': all_transactions[:100],  # Limit to recent 100
            'transaction_count': len(all_transactions),
        }

    def get_monthly_interest_chart_data(self, start_year: int = 2024) -> List[Dict]:
        """
        Get monthly interest income data formatted for charting.
        """
        if not self.accounts:
            self.load_all_transactions()
        
        # Consolidate all monthly interest data
        monthly_consolidated = defaultdict(float)
        
        for account in self.accounts.values():
            for month, amount in account.monthly_interest.items():
                monthly_consolidated[month] += amount
        
        # Generate all months from start_year to now
        current = datetime.now()
        chart_data = []
        
        year = start_year
        month = 1
        
        while year < current.year or (year == current.year and month <= current.month):
            month_key = f"{year}-{month:02d}"
            amount = monthly_consolidated.get(month_key, 0.0)
            
            chart_data.append({
                'month': month_key,
                'formatted': datetime(year, month, 1).strftime('%b %Y'),
                'value': amount,
                'year': year,
            })
            
            month += 1
            if month > 12:
                month = 1
                year += 1
        
        return chart_data

    def get_consolidated_stock_sales(self) -> Dict:
        """Get consolidated stock sales proceeds across all accounts."""
        if not self.accounts:
            self.load_all_transactions()
        
        total_proceeds = 0.0
        by_account = {}
        monthly_consolidated = defaultdict(float)
        by_symbol = defaultdict(lambda: {'proceeds': 0.0, 'quantity': 0.0, 'transactions': 0})
        all_transactions = []
        
        for account_name, account in self.accounts.items():
            total_proceeds += account.total_stock_sales_proceeds
            by_account[account_name] = {
                'owner': account.owner,
                'account_type': account.account_type,
                'total': account.total_stock_sales_proceeds,
                'transaction_count': len(account.stock_sale_transactions),
                'monthly': account.monthly_stock_sales,
            }
            
            # Consolidate monthly data
            for month, amount in account.monthly_stock_sales.items():
                monthly_consolidated[month] += amount
            
            # Add transactions with account info
            for txn in account.stock_sale_transactions:
                all_transactions.append({
                    'date': txn.date.isoformat(),
                    'symbol': txn.symbol,
                    'description': txn.description,
                    'quantity': txn.quantity,
                    'price': txn.price,
                    'proceeds': txn.proceeds,
                    'account': account_name,
                })
                # Track by symbol
                by_symbol[txn.symbol]['proceeds'] += txn.proceeds
                by_symbol[txn.symbol]['quantity'] += txn.quantity
                by_symbol[txn.symbol]['transactions'] += 1
        
        # Sort monthly data
        sorted_monthly = dict(sorted(monthly_consolidated.items()))
        
        # Sort transactions by date descending
        all_transactions.sort(key=lambda x: x['date'], reverse=True)
        
        # Convert by_symbol to list sorted by proceeds
        symbols_list = [
            {'symbol': sym, **data}
            for sym, data in sorted(by_symbol.items(), key=lambda x: x[1]['proceeds'], reverse=True)
        ]
        
        return {
            'total_proceeds': total_proceeds,
            'by_account': by_account,
            'monthly': sorted_monthly,
            'by_symbol': symbols_list[:20],  # Top 20 symbols
            'transactions': all_transactions[:100],  # Recent 100 transactions
            'transaction_count': len(all_transactions),
        }

    def get_consolidated_stock_lending(self) -> Dict:
        """Get consolidated stock lending income across all accounts."""
        if not self.accounts:
            self.load_all_transactions()
        
        total_income = 0.0
        by_account = {}
        monthly_consolidated = defaultdict(float)
        by_symbol = defaultdict(lambda: {'amount': 0.0, 'transactions': 0})
        all_transactions = []
        
        for account_name, account in self.accounts.items():
            total_income += account.total_stock_lending
            by_account[account_name] = {
                'owner': account.owner,
                'account_type': account.account_type,
                'total': account.total_stock_lending,
                'transaction_count': len(account.stock_lending_transactions),
                'monthly': account.monthly_stock_lending,
            }
            
            # Consolidate monthly data
            for month, amount in account.monthly_stock_lending.items():
                monthly_consolidated[month] += amount
            
            # Add transactions with account info
            for txn in account.stock_lending_transactions:
                all_transactions.append({
                    'date': txn.date.isoformat(),
                    'symbol': txn.symbol,
                    'description': txn.description,
                    'amount': txn.amount,
                    'account': account_name,
                })
                # Track by symbol
                by_symbol[txn.symbol]['amount'] += txn.amount
                by_symbol[txn.symbol]['transactions'] += 1
        
        # Sort monthly data
        sorted_monthly = dict(sorted(monthly_consolidated.items()))
        
        # Sort transactions by date descending
        all_transactions.sort(key=lambda x: x['date'], reverse=True)
        
        # Convert by_symbol to list sorted by amount
        symbols_list = [
            {'symbol': sym, **data}
            for sym, data in sorted(by_symbol.items(), key=lambda x: x[1]['amount'], reverse=True)
        ]
        
        return {
            'total_income': total_income,
            'by_account': by_account,
            'monthly': sorted_monthly,
            'by_symbol': symbols_list[:20],  # Top 20 symbols
            'transactions': all_transactions[:100],  # Recent 100 transactions
            'transaction_count': len(all_transactions),
        }

    def get_monthly_stock_sales_chart_data(self, start_year: int = 2024) -> List[Dict]:
        """Get monthly stock sales proceeds data formatted for charting."""
        if not self.accounts:
            self.load_all_transactions()
        
        # Consolidate all monthly stock sales data
        monthly_consolidated = defaultdict(float)
        
        for account in self.accounts.values():
            for month, amount in account.monthly_stock_sales.items():
                monthly_consolidated[month] += amount
        
        # Generate all months from start_year to now
        current = datetime.now()
        chart_data = []
        
        year = start_year
        month = 1
        
        while year < current.year or (year == current.year and month <= current.month):
            month_key = f"{year}-{month:02d}"
            amount = monthly_consolidated.get(month_key, 0.0)
            
            chart_data.append({
                'month': month_key,
                'formatted': datetime(year, month, 1).strftime('%b %Y'),
                'value': amount,
                'year': year,
            })
            
            month += 1
            if month > 12:
                month = 1
                year += 1
        
        return chart_data

    def get_monthly_stock_lending_chart_data(self, start_year: int = 2024) -> List[Dict]:
        """Get monthly stock lending income data formatted for charting."""
        if not self.accounts:
            self.load_all_transactions()
        
        # Consolidate all monthly stock lending data
        monthly_consolidated = defaultdict(float)
        
        for account in self.accounts.values():
            for month, amount in account.monthly_stock_lending.items():
                monthly_consolidated[month] += amount
        
        # Generate all months from start_year to now
        current = datetime.now()
        chart_data = []
        
        year = start_year
        month = 1
        
        while year < current.year or (year == current.year and month <= current.month):
            month_key = f"{year}-{month:02d}"
            amount = monthly_consolidated.get(month_key, 0.0)
            
            chart_data.append({
                'month': month_key,
                'formatted': datetime(year, month, 1).strftime('%b %Y'),
                'value': amount,
                'year': year,
            })
            
            month += 1
            if month > 12:
                month = 1
                year += 1
        
        return chart_data

    def get_income_summary(self) -> Dict:
        """Get a complete income summary across all sources."""
        if not self.accounts:
            self.load_all_transactions()
        
        total_options = 0.0
        total_dividends = 0.0
        total_interest = 0.0
        total_stock_lending = 0.0
        total_stock_sales = 0.0
        accounts_summary = []
        
        for account_name, account in self.accounts.items():
            total_options += account.total_options_income
            total_dividends += account.total_dividend_income
            total_interest += account.total_interest_income
            total_stock_lending += account.total_stock_lending
            total_stock_sales += account.total_stock_sales_proceeds
            
            accounts_summary.append({
                'name': account_name,
                'owner': account.owner,
                'type': account.account_type,
                'options_income': account.total_options_income,
                'dividend_income': account.total_dividend_income,
                'interest_income': account.total_interest_income,
                'stock_lending': account.total_stock_lending,
                'stock_sales': account.total_stock_sales_proceeds,
                'total': (
                    account.total_options_income + 
                    account.total_dividend_income + 
                    account.total_interest_income +
                    account.total_stock_lending
                ),
            })
        
        # Sort accounts by total descending
        accounts_summary.sort(key=lambda x: x['total'], reverse=True)
        
        return {
            'total_investment_income': total_options + total_dividends + total_interest + total_stock_lending,
            'options_income': total_options,
            'dividend_income': total_dividends,
            'interest_income': total_interest,
            'stock_lending': total_stock_lending,
            'stock_sales_proceeds': total_stock_sales,
            'accounts': accounts_summary,
            'account_count': len(accounts_summary),
        }

    def get_monthly_options_chart_data(self, start_year: int = 2014) -> List[Dict]:
        """
        Get monthly options income data formatted for charting.
        Returns data from start_year to present.
        """
        if not self.accounts:
            self.load_all_transactions()
        
        # Consolidate all monthly options data
        monthly_consolidated = defaultdict(float)
        
        for account in self.accounts.values():
            for month, amount in account.monthly_options.items():
                monthly_consolidated[month] += amount
        
        # Generate all months from start_year to now
        current = datetime.now()
        chart_data = []
        
        year = start_year
        month = 1
        
        while year < current.year or (year == current.year and month <= current.month):
            month_key = f"{year}-{month:02d}"
            amount = monthly_consolidated.get(month_key, 0.0)
            
            chart_data.append({
                'month': month_key,
                'formatted': datetime(year, month, 1).strftime('%b %Y'),
                'value': amount,
                'year': year,
            })
            
            month += 1
            if month > 12:
                month = 1
                year += 1
        
        return chart_data

    def get_monthly_dividend_chart_data(self, start_year: int = 2020) -> List[Dict]:
        """
        Get monthly dividend income data formatted for charting.
        """
        if not self.accounts:
            self.load_all_transactions()
        
        # Consolidate all monthly dividend data
        monthly_consolidated = defaultdict(float)
        
        for account in self.accounts.values():
            for month, amount in account.monthly_dividends.items():
                monthly_consolidated[month] += amount
        
        # Generate all months from start_year to now
        current = datetime.now()
        chart_data = []
        
        year = start_year
        month = 1
        
        while year < current.year or (year == current.year and month <= current.month):
            month_key = f"{year}-{month:02d}"
            amount = monthly_consolidated.get(month_key, 0.0)
            
            chart_data.append({
                'month': month_key,
                'formatted': datetime(year, month, 1).strftime('%b %Y'),
                'value': amount,
                'year': year,
            })
            
            month += 1
            if month > 12:
                month = 1
                year += 1
        
        return chart_data

    def get_account_options_detail(self, account_name: str) -> Dict:
        """
        Get detailed options income for a specific account.
        Includes monthly data and list of available months.
        """
        if not self.accounts:
            self.load_all_transactions()
        
        if account_name not in self.accounts:
            return {
                'account_name': account_name,
                'error': 'Account not found',
                'total_income': 0,
                'monthly': {},
                'available_months': [],
                'transactions': [],
            }
        
        account = self.accounts[account_name]
        
        # Get all available months sorted (most recent first)
        available_months = sorted(account.monthly_options.keys(), reverse=True)
        
        # Format transactions
        transactions = []
        for txn in account.options_transactions:
            transactions.append({
                'date': txn.date.isoformat(),
                'symbol': txn.symbol,
                'description': txn.description,
                'trans_code': txn.trans_code,
                'quantity': txn.quantity,
                'price': txn.price,
                'amount': txn.amount,
                'option_type': txn.option_type,
                'strike': txn.strike,
                'expiry': txn.expiry,
            })
        
        return {
            'account_name': account_name,
            'owner': account.owner,
            'account_type': account.account_type,
            'total_income': account.total_options_income,
            'monthly': account.monthly_options,
            'available_months': available_months,
            'transactions': transactions,
            'transaction_count': len(transactions),
        }

    def get_account_options_weekly_breakdown(self, account_name: str, year: int, month: int) -> Dict:
        """
        Get weekly breakdown of options income for a specific account and month.
        Returns data organized by symbol and week.
        """
        if not self.accounts:
            self.load_all_transactions()
        
        if account_name not in self.accounts:
            return {
                'account_name': account_name,
                'month': f"{year}-{month:02d}",
                'error': 'Account not found',
                'weekly_data': {},
                'symbols': [],
                'totals': {'week1': 0, 'week2': 0, 'week3': 0, 'week4': 0, 'week5': 0},
            }
        
        account = self.accounts[account_name]
        month_key = f"{year}-{month:02d}"
        
        # Filter transactions for the specified month
        month_transactions = [
            txn for txn in account.options_transactions
            if txn.date.year == year and txn.date.month == month
        ]
        
        # Organize by symbol and week
        # Week 1: days 1-7, Week 2: days 8-14, Week 3: days 15-21, Week 4: days 22-28, Week 5: days 29-31
        def get_week(day: int) -> str:
            if day <= 7:
                return 'week1'
            elif day <= 14:
                return 'week2'
            elif day <= 21:
                return 'week3'
            elif day <= 28:
                return 'week4'
            else:
                return 'week5'
        
        # Initialize data structures
        symbols_data = defaultdict(lambda: {
            'week1': {'count': 0, 'amount': 0.0, 'transactions': []},
            'week2': {'count': 0, 'amount': 0.0, 'transactions': []},
            'week3': {'count': 0, 'amount': 0.0, 'transactions': []},
            'week4': {'count': 0, 'amount': 0.0, 'transactions': []},
            'week5': {'count': 0, 'amount': 0.0, 'transactions': []},
            'total_count': 0,
            'total_amount': 0.0,
        })
        
        weekly_totals = {
            'week1': {'count': 0, 'amount': 0.0},
            'week2': {'count': 0, 'amount': 0.0},
            'week3': {'count': 0, 'amount': 0.0},
            'week4': {'count': 0, 'amount': 0.0},
            'week5': {'count': 0, 'amount': 0.0},
        }
        
        month_total = 0.0
        
        for txn in month_transactions:
            week = get_week(txn.date.day)
            symbol = txn.symbol or 'UNKNOWN'
            
            # Add to symbol data
            symbols_data[symbol][week]['count'] += abs(txn.quantity) if txn.quantity else 1
            symbols_data[symbol][week]['amount'] += txn.amount
            symbols_data[symbol][week]['transactions'].append({
                'date': txn.date.isoformat(),
                'description': txn.description,
                'trans_code': txn.trans_code,
                'quantity': txn.quantity,
                'amount': txn.amount,
                'option_type': txn.option_type,
            })
            symbols_data[symbol]['total_count'] += abs(txn.quantity) if txn.quantity else 1
            symbols_data[symbol]['total_amount'] += txn.amount
            
            # Add to weekly totals
            weekly_totals[week]['count'] += abs(txn.quantity) if txn.quantity else 1
            weekly_totals[week]['amount'] += txn.amount
            
            month_total += txn.amount
        
        # Convert to serializable format and sort symbols by total amount
        weekly_data = {}
        for symbol, data in symbols_data.items():
            weekly_data[symbol] = {
                'week1': {'count': data['week1']['count'], 'amount': data['week1']['amount']},
                'week2': {'count': data['week2']['count'], 'amount': data['week2']['amount']},
                'week3': {'count': data['week3']['count'], 'amount': data['week3']['amount']},
                'week4': {'count': data['week4']['count'], 'amount': data['week4']['amount']},
                'week5': {'count': data['week5']['count'], 'amount': data['week5']['amount']},
                'total_count': data['total_count'],
                'total_amount': data['total_amount'],
            }
        
        # Sort symbols by total amount descending
        sorted_symbols = sorted(
            weekly_data.keys(),
            key=lambda s: weekly_data[s]['total_amount'],
            reverse=True
        )
        
        return {
            'account_name': account_name,
            'month': month_key,
            'month_formatted': datetime(year, month, 1).strftime('%B %Y'),
            'month_total': month_total,
            'weekly_data': weekly_data,
            'symbols': sorted_symbols,
            'weekly_totals': {
                'week1': weekly_totals['week1']['amount'],
                'week2': weekly_totals['week2']['amount'],
                'week3': weekly_totals['week3']['amount'],
                'week4': weekly_totals['week4']['amount'],
                'week5': weekly_totals['week5']['amount'],
            },
            'weekly_counts': {
                'week1': weekly_totals['week1']['count'],
                'week2': weekly_totals['week2']['count'],
                'week3': weekly_totals['week3']['count'],
                'week4': weekly_totals['week4']['count'],
                'week5': weekly_totals['week5']['count'],
            },
            'transaction_count': len(month_transactions),
        }


    def load_from_database(self) -> bool:
        """
        Load income transactions from the database.
        Returns True if data was found and loaded.
        
        Uses investment_accounts as the source of truth and maps transactions
        to canonical account IDs for consistency with the Investments module.
        """
        from app.core.database import SessionLocal
        from app.modules.investments.models import InvestmentTransaction, InvestmentAccount
        
        db = SessionLocal()
        try:
            # ACCOUNT MAPPING: Map transaction account_ids to canonical investment account_ids
            # This ensures consistency between Investments and Income modules
            account_mapping = {
                # Robinhood transaction IDs → canonical IDs
                'robinhood_neel_individual': 'neel_brokerage',
                'robinhood_jaya_individual': 'jaya_brokerage',
                'robinhood_neel_retirement': 'neel_retirement',
                'robinhood_jaya_retirement': 'jaya_ira',  # Maps to IRA, not generic retirement
                'robinhood_alisha_individual': 'alisha_brokerage',
                'robinhood_default': 'neel_brokerage',  # Default to Neel's main account
                # TD Ameritrade
                'neel_roth_ira_538': 'neel_retirement',
                'tda_roth_ira_347': 'neel_retirement',
                # Generic
                'generic': 'neel_brokerage',
            }
            
            # Load all active investment accounts for reference
            inv_accounts = db.query(InvestmentAccount).filter(
                InvestmentAccount.is_active == 'Y'
            ).all()
            
            # Build account info lookup
            account_info = {}
            for acc in inv_accounts:
                parts = acc.account_id.split('_')
                owner = parts[0].title() if parts else 'Unknown'
                acc_type = '_'.join(parts[1:]) if len(parts) > 1 else 'brokerage'
                
                account_info[acc.account_id] = {
                    'name': acc.account_name,
                    'owner': owner,
                    'type': acc_type,
                }
            
            # Check for income-related transactions in database
            income_types = ['STO', 'BTC', 'OEXP', 'OASGN', 'CDIV', 'DIVIDEND', 'INT', 'INTEREST', 'SLIP', 'SELL']
            
            transactions = db.query(InvestmentTransaction).filter(
                InvestmentTransaction.transaction_type.in_(income_types)
            ).order_by(InvestmentTransaction.transaction_date.desc()).all()
            
            if not transactions:
                # Even if no transactions, create empty accounts for all investment accounts
                self.accounts = {}
                for acc_id, info in account_info.items():
                    self.accounts[info['name']] = AccountIncome(
                        account_name=info['name'],
                        owner=info['owner'],
                        account_type=info['type']
                    )
                return len(self.accounts) > 0
            
            # Initialize accounts for all investment accounts (even if no income yet)
            self.accounts = {}
            for acc_id, info in account_info.items():
                self.accounts[info['name']] = AccountIncome(
                    account_name=info['name'],
                    owner=info['owner'],
                    account_type=info['type']
                )
            
            for txn in transactions:
                # Map transaction account_id to canonical investment account_id
                txn_account_id = txn.account_id or 'robinhood_default'
                canonical_id = account_mapping.get(txn_account_id, txn_account_id)
                
                # Get account info (fallback to parsing if not in investment_accounts)
                if canonical_id in account_info:
                    info = account_info[canonical_id]
                    owner = info['owner']
                    account_type = info['type']
                    account_name = info['name']
                else:
                    # Fallback: parse from account_id
                    owner = 'Neel'
                    account_type = 'brokerage'
                    if 'jaya' in canonical_id.lower():
                        owner = 'Jaya'
                    elif 'alisha' in canonical_id.lower():
                        owner = 'Alisha'
                    elif 'family' in canonical_id.lower():
                        owner = 'Family'
                    if 'retirement' in canonical_id.lower() or 'ira' in canonical_id.lower():
                        account_type = 'retirement'
                    elif 'hsa' in canonical_id.lower():
                        account_type = 'hsa'
                    account_name = f"{owner}'s {account_type.replace('_', ' ').title()}"
                
                # Get or create account
                if account_name not in self.accounts:
                    self.accounts[account_name] = AccountIncome(
                        account_name=account_name,
                        owner=owner,
                        account_type=account_type
                    )
                
                account = self.accounts[account_name]
                trans_type = txn.transaction_type.upper()
                
                # Parse transaction date
                date = txn.transaction_date
                if not date:
                    continue
                
                # Convert to datetime for consistency
                if hasattr(date, 'year'):
                    date = datetime(date.year, date.month, date.day)
                
                amount = float(txn.amount) if txn.amount else 0
                symbol = txn.symbol or ''
                description = txn.description or ''
                quantity = int(float(txn.quantity)) if txn.quantity else 0
                price = float(txn.price_per_share) if txn.price_per_share else 0
                
                month_key = date.strftime('%Y-%m')
                
                # Process based on transaction type
                if trans_type in ('STO', 'BTC', 'OEXP', 'OASGN'):
                    # Options transaction
                    option_type, expiry, strike = self._parse_option_description(description)
                    
                    txn_obj = OptionsTransaction(
                        date=date,
                        symbol=symbol,
                        description=description,
                        trans_code=trans_type,
                        quantity=quantity,
                        price=price,
                        amount=amount,
                        account_name=account_name,
                        option_type=option_type or 'unknown',
                        strike=strike,
                        expiry=expiry
                    )
                    account.options_transactions.append(txn_obj)
                    
                    if month_key not in account.monthly_options:
                        account.monthly_options[month_key] = 0.0
                    account.monthly_options[month_key] += amount
                    account.total_options_income += amount
                    
                elif trans_type in ('CDIV', 'DIVIDEND'):
                    # Dividend transaction
                    shares, dps = self._extract_dividend_info(description)
                    
                    txn_obj = DividendTransaction(
                        date=date,
                        symbol=symbol,
                        description=description,
                        amount=amount,
                        account_name=account_name,
                        shares=shares,
                        dividend_per_share=dps
                    )
                    account.dividend_transactions.append(txn_obj)
                    
                    if month_key not in account.monthly_dividends:
                        account.monthly_dividends[month_key] = 0.0
                    account.monthly_dividends[month_key] += amount
                    account.total_dividend_income += amount
                    
                elif trans_type in ('INT', 'INTEREST'):
                    # Interest transaction
                    txn_obj = InterestTransaction(
                        date=date,
                        description=description or 'Interest Payment',
                        amount=amount,
                        account_name=account_name,
                        source='robinhood'
                    )
                    account.interest_transactions.append(txn_obj)
                    
                    if month_key not in account.monthly_interest:
                        account.monthly_interest[month_key] = 0.0
                    account.monthly_interest[month_key] += amount
                    account.total_interest_income += amount
                    
                elif trans_type == 'SLIP':
                    # Stock lending income
                    txn_obj = StockLendingTransaction(
                        date=date,
                        symbol=symbol,
                        description=description or 'Stock Lending',
                        amount=amount,
                        account_name=account_name
                    )
                    account.stock_lending_transactions.append(txn_obj)
                    
                    if month_key not in account.monthly_stock_lending:
                        account.monthly_stock_lending[month_key] = 0.0
                    account.monthly_stock_lending[month_key] += amount
                    account.total_stock_lending += amount
                    
                elif trans_type == 'SELL' and amount > 0:
                    # Stock sale
                    txn_obj = StockSaleTransaction(
                        date=date,
                        symbol=symbol,
                        description=description,
                        quantity=quantity,
                        price=price,
                        proceeds=amount,
                        account_name=account_name
                    )
                    account.stock_sale_transactions.append(txn_obj)
                    
                    if month_key not in account.monthly_stock_sales:
                        account.monthly_stock_sales[month_key] = 0.0
                    account.monthly_stock_sales[month_key] += amount
                    account.total_stock_sales_proceeds += amount
            
            return len(self.accounts) > 0
            
        except Exception as e:
            print(f"Error loading income from database: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            db.close()

    def import_csv_to_database(self) -> Dict:
        """
        Import CSV transaction data to the database.
        Uses record_hash for deduplication to prevent duplicate entries.
        Returns statistics about the import.
        """
        import hashlib
        from decimal import Decimal
        from app.core.database import SessionLocal
        from app.modules.investments.models import InvestmentTransaction
        
        if not self.data_dir.exists():
            return {"error": f"Data directory not found: {self.data_dir}", "imported": 0}
        
        db = SessionLocal()
        stats = {'files_processed': 0, 'records_imported': 0, 'records_skipped': 0, 'errors': []}
        
        # Track hashes seen in this import to avoid batch duplicates
        seen_hashes = set()
        
        try:
            csv_files = list(self.data_dir.glob('*.csv'))
            
            # Map generated account IDs to canonical account IDs
            canonical_account_map = {
                'robinhood_neel_individual': 'neel_brokerage',
                'robinhood_jaya_individual': 'jaya_brokerage',
                'robinhood_neel_retirement': 'neel_retirement',
                'robinhood_jaya_retirement': 'jaya_ira',
                'robinhood_alisha_individual': 'alisha_brokerage',
            }
            
            # Check if canonical accounts already have STO/BTC data
            # If so, skip ALL STO/BTC imports to prevent duplicates from multiple CSV files
            accounts_with_options = set()
            for canonical_id in canonical_account_map.values():
                count = db.query(InvestmentTransaction).filter(
                    InvestmentTransaction.account_id == canonical_id,
                    InvestmentTransaction.transaction_type.in_(['STO', 'BTC'])
                ).count()
                if count > 0:
                    accounts_with_options.add(canonical_id)
            
            for csv_file in csv_files:
                stats['files_processed'] += 1
                
                # Determine account info from filename
                owner, account_name, account_type = self._determine_account_info(csv_file.name)
                raw_account_id = f"robinhood_{owner.lower()}_{account_type}"
                # Map to canonical account ID
                account_id = canonical_account_map.get(raw_account_id, raw_account_id)
                
                # Parse the CSV
                transactions = self._parse_csv_file(csv_file)
                
                for row in transactions:
                    try:
                        trans_code = row.get('Trans Code', '').strip().upper()
                        if not trans_code:
                            continue
                        
                        # Parse common fields
                        date = self._parse_date(row.get('Activity Date', ''))
                        if not date:
                            continue
                        
                        amount = self._parse_amount(row.get('Amount', ''))
                        symbol = row.get('Instrument', '').strip().upper() or 'UNKNOWN'
                        description = row.get('Description', '').strip()
                        quantity_str = row.get('Quantity', '').strip()
                        price_str = row.get('Price', '').strip()
                        
                        try:
                            quantity = Decimal(quantity_str) if quantity_str else None
                        except (ValueError, TypeError, Exception):
                            quantity = None
                        
                        price = Decimal(str(self._parse_amount(price_str))) if price_str else None
                        amount_decimal = Decimal(str(amount))
                        
                        txn_date = date.date() if hasattr(date, 'date') else date
                        
                        # Create a business key for deduplication (date, type, symbol, amount)
                        # This identifies the same transaction across different CSV files
                        business_key = f"{account_id}|{txn_date}|{trans_code}|{symbol}|{amount:.2f}"
                        
                        # Skip if we've already seen this business key in this import batch
                        if business_key in seen_hashes:
                            stats['records_skipped'] += 1
                            continue
                        seen_hashes.add(business_key)
                        
                        # Skip STO/BTC for accounts that already have options data
                        # This prevents duplicates from multiple overlapping CSV files
                        if trans_code in ('STO', 'BTC') and account_id in accounts_with_options:
                            stats['records_skipped'] += 1
                            continue
                        
                        # For other transaction types, check database directly
                        if trans_code not in ('STO', 'BTC'):
                            existing = db.query(InvestmentTransaction).filter(
                                InvestmentTransaction.account_id == account_id,
                                InvestmentTransaction.transaction_date == txn_date,
                                InvestmentTransaction.transaction_type == trans_code,
                                InvestmentTransaction.symbol == symbol,
                                InvestmentTransaction.amount == amount_decimal
                            ).first()
                            
                            if existing:
                                stats['records_skipped'] += 1
                                continue
                        
                        # Generate hash for new record
                        hash_input = f"robinhood|{business_key}|{quantity or ''}"
                        record_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:32]
                        
                        # Create new transaction record
                        txn = InvestmentTransaction(
                            source='robinhood',
                            account_id=account_id,
                            transaction_date=txn_date,
                            transaction_type=trans_code,
                            symbol=symbol,
                            quantity=quantity,
                            amount=amount_decimal,
                            price_per_share=price,
                            description=description,
                            record_hash=record_hash,
                        )
                        db.add(txn)
                        stats['records_imported'] += 1
                        
                    except Exception as e:
                        stats['errors'].append(f"Error processing row in {csv_file.name}: {str(e)}")
                
                # Commit after each file to avoid batch conflicts
                db.commit()
            
            return stats
            
        except Exception as e:
            db.rollback()
            stats['errors'].append(f"Database error: {str(e)}")
            return stats
        finally:
            db.close()


# Singleton instance
_income_service: Optional[IncomeService] = None


def get_income_service() -> IncomeService:
    """Get or create the income service singleton."""
    global _income_service
    if _income_service is None:
        _income_service = IncomeService()
        # Try loading from database first
        loaded_from_db = _income_service.load_from_database()
        if not loaded_from_db:
            # Fall back to loading from CSV files
            _income_service.load_all_transactions()
    return _income_service


def reset_income_service() -> None:
    """Reset the income service singleton to force reload of data."""
    global _income_service
    _income_service = None

