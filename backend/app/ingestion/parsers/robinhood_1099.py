"""
Robinhood Consolidated 1099 CSV parser.

Parses the machine-readable 1099 CSV downloaded from Robinhood Tax Center.
This file contains 1099-DIV, 1099-INT, and 1099-B records in a flat CSV format
where the first column identifies the record type.

Only 1099-B equity rows are saved — they create StockLot + StockLotSale records
for accurate capital gains tracking. Options rows (CALL/PUT in description) are
skipped because they are already captured via STO/BTC in the activity CSV.
"""

import csv
import re
from pathlib import Path
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from app.ingestion.parsers.base import BaseParser, ParseResult, ParsedRecord, RecordType


# Robinhood account number → internal account_id
# Account numbers visible on monthly statements and in the 1099 file.
ACCOUNT_NUMBER_MAP = {
    "170317739": "neel_brokerage",
    "593591191": "neel_cash",
    "925668238": "neel_brokerage_2",
}

# Partial company name → ticker symbol
# Used to extract symbol from equity description (e.g. "APPLE INC. COMMON STOCK" → "AAPL")
COMPANY_SYMBOL_MAP = {
    "APPLE": "AAPL",
    "NVIDIA": "NVDA",
    "TESLA": "TSLA",
    "MICROSOFT": "MSFT",
    "ROBINHOOD MARKETS": "HOOD",
    "PALANTIR": "PLTR",
    "BROADCOM": "AVGO",
    "ALIBABA": "BABA",
    "COREWEAVE": "CRWV",
    "ROCKET LAB": "RKLB",
    "STRATEGY INC": "MSTR",
    "MICROSTRATEGY": "MSTR",
    "SPDR GOLD": "GLD",
    "VANGUARD S&P 500": "VOO",
    "ISHARES BITCOIN TRUST": "IBIT",
    "ADVANCED MICRO DEVICES": "AMD",
    "INTEL": "INTC",
    "ALPHABET": "GOOGL",
    "AMAZON": "AMZN",
    "META PLATFORMS": "META",
    "SHOPIFY": "SHOP",
    "COINBASE": "COIN",
    "CIRCLE INTERNET": "CRCL",
    "FIGMA": "FIG",
    "MICRON": "MU",
}

_OPTION_RE = re.compile(r'\b(CALL|PUT)\b', re.IGNORECASE)

# 1099-B column indices (zero-based, after splitting on comma)
_COL = {
    "row_type":          0,
    "account_number":    1,
    "tax_year":          2,
    "date_acquired":     3,
    "sale_date":         4,
    "description":       5,
    "shares":            6,
    "cost_basis":        7,
    "proceeds":          8,
    "term":              9,
    "wash_disallowed":  12,
    "non_covered":      17,
}


class Robinhood1099Parser(BaseParser):
    """Parser for Robinhood Consolidated 1099 CSV (Tax Center download)."""

    source_name = "robinhood_1099"
    supported_extensions = [".csv"]

    def can_parse(self, file_path: Path) -> bool:
        if file_path.suffix.lower() != ".csv":
            return False
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                first_line = f.readline()
            return first_line.startswith("1099-")
        except Exception:
            return False

    def parse(self, file_path: Path) -> ParseResult:
        records = []
        warnings = []
        skipped_options = 0

        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for row_num, row in enumerate(reader, start=1):
                if not row or not row[0].strip():
                    continue
                if row[0].strip() != "1099-B":
                    continue
                # Skip the header row
                if len(row) > 1 and row[1].strip() == "ACCOUNT NUMBER":
                    continue
                try:
                    record = self._parse_1099b_row(row, row_num)
                    if record is None:
                        skipped_options += 1
                    else:
                        records.append(record)
                except Exception as e:
                    warnings.append(f"Row {row_num}: {e}")

        return ParseResult(
            success=True,
            source_name=self.source_name,
            file_path=file_path,
            records=records,
            warnings=warnings,
            errors=[],
            metadata={
                "record_count": len(records),
                "skipped_options": skipped_options,
            },
        )

    def _parse_1099b_row(self, row: list, row_num: int) -> Optional[ParsedRecord]:
        def col(idx: int) -> str:
            return row[idx].strip() if idx < len(row) else ""

        description = col(_COL["description"])

        # Skip options — already in activity CSV as STO/BTC
        if _OPTION_RE.search(description):
            return None

        # Skip aggregate/totals rows (no description or no sale date)
        sale_date_str = col(_COL["sale_date"])
        if not description or not sale_date_str:
            return None

        sale_date = _parse_yyyymmdd(sale_date_str)
        if not sale_date:
            return None

        purchase_date = _parse_yyyymmdd(col(_COL["date_acquired"]))
        account_number = col(_COL["account_number"])
        tax_year_str = col(_COL["tax_year"])
        tax_year = int(tax_year_str) if tax_year_str.isdigit() else sale_date.year

        shares = _parse_decimal(col(_COL["shares"]))
        cost_basis = _parse_decimal(col(_COL["cost_basis"])) or Decimal("0")
        proceeds = _parse_decimal(col(_COL["proceeds"]))
        wash_disallowed = _parse_decimal(col(_COL["wash_disallowed"])) or Decimal("0")
        non_covered = col(_COL["non_covered"]) == "1"
        term = col(_COL["term"]).upper()

        if shares is None or proceeds is None:
            return None

        symbol = _extract_symbol(description)
        account_id = ACCOUNT_NUMBER_MAP.get(account_number, f"robinhood_{account_number}")

        return ParsedRecord(
            record_type=RecordType.CAPITAL_GAIN,
            data={
                "source": self.source_name,
                "account_id": account_id,
                "account_number": account_number,
                "tax_year": tax_year,
                "symbol": symbol,
                "description": description,
                "purchase_date": purchase_date,
                "sale_date": sale_date,
                "shares": shares,
                "cost_basis": cost_basis,
                "proceeds": proceeds,
                "term": term,
                "is_long_term": term == "LONG",
                "wash_sale_disallowed": wash_disallowed,
                "non_covered": non_covered,
            },
            source_row=row_num,
        )


# ── helpers ──────────────────────────────────────────────────────────────────

def _parse_yyyymmdd(s: str) -> Optional[date]:
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        try:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        except ValueError:
            return None
    return None


def _parse_decimal(s: str) -> Optional[Decimal]:
    s = s.strip().replace(",", "")
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _extract_symbol(description: str) -> str:
    desc_upper = description.upper()
    for company, symbol in COMPANY_SYMBOL_MAP.items():
        if company in desc_upper:
            return symbol
    # Fallback: first token (works for "HOOD COMMON STOCK" → "HOOD")
    return description.split()[0].upper() if description else "UNKNOWN"
