"""
Monarch Money CSV Parser.

Parses Monarch Money CSV exports containing categorized spending transactions.
Expected columns: Date, Merchant, Category, Account, Original Statement, Notes, Amount, Tags, Owner
"""

import csv
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from app.ingestion.parsers.base import BaseParser, ParseResult, ParsedRecord, RecordType


class MonarchParser(BaseParser):
    """Parser for Monarch Money CSV exports."""

    source_name = "monarch"
    supported_extensions = [".csv"]

    REQUIRED_HEADERS = {"Date", "Merchant", "Category", "Account", "Amount"}

    def can_parse(self, file_path: Path) -> bool:
        """Check if this CSV has the Monarch Money headers."""
        if file_path.suffix.lower() != ".csv":
            return False
        headers = self._read_csv_headers(file_path)
        return self.REQUIRED_HEADERS.issubset(headers)

    def parse(self, file_path: Path) -> ParseResult:
        """Parse Monarch Money CSV and return spending records."""
        records = []
        warnings = []
        errors = []
        metadata = {"file_type": "csv", "source": "monarch"}

        try:
            # First pass: count identical rows for instance numbering
            row_counts: dict[str, int] = defaultdict(int)
            all_rows: list[dict] = []

            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    all_rows.append(row)
                    key = self._make_row_key(row)
                    row_counts[key] += 1

            # Second pass: assign instance numbers and build records
            instance_tracker: dict[str, int] = defaultdict(int)

            for row_num, row in enumerate(all_rows, start=2):  # row 2 = first data row
                try:
                    date_str = row.get("Date", "").strip()
                    if not date_str:
                        warnings.append(f"Row {row_num}: missing date, skipped")
                        continue

                    amount_str = row.get("Amount", "").strip()
                    amount = self._normalize_amount(amount_str)
                    if amount is None:
                        warnings.append(f"Row {row_num}: invalid amount '{amount_str}', skipped")
                        continue

                    txn_date = datetime.strptime(date_str, "%Y-%m-%d").date()

                    merchant = row.get("Merchant", "").strip()
                    category = row.get("Category", "").strip()
                    account = row.get("Account", "").strip()
                    original_statement = row.get("Original Statement", "").strip()
                    notes = row.get("Notes", "").strip()
                    tags = row.get("Tags", "").strip()
                    owner = row.get("Owner", "").strip()

                    # Instance numbering for identical rows
                    key = self._make_row_key(row)
                    instance_num = instance_tracker[key]
                    instance_tracker[key] += 1

                    # Build hash
                    hash_input = (
                        f"{date_str}|{merchant}|{account}|{amount:.2f}|"
                        f"{original_statement}|instance_{instance_num}"
                    )
                    record_hash = hashlib.sha256(hash_input.encode()).hexdigest()

                    records.append(ParsedRecord(
                        record_type=RecordType.SPENDING,
                        data={
                            "transaction_date": txn_date,
                            "merchant": merchant,
                            "category": category,
                            "account": account,
                            "original_statement": original_statement,
                            "notes": notes,
                            "amount": amount,
                            "tags": tags,
                            "owner": owner,
                            "record_hash": record_hash,
                        },
                        source_row=row_num,
                    ))

                except Exception as e:
                    warnings.append(f"Row {row_num}: {e}")

            metadata["total_rows"] = len(all_rows)
            metadata["records_parsed"] = len(records)

        except Exception as e:
            errors.append(f"Error parsing CSV: {e}")

        return ParseResult(
            success=len(errors) == 0 and len(records) > 0,
            source_name=self.source_name,
            file_path=file_path,
            records=records,
            warnings=warnings,
            errors=errors,
            metadata=metadata,
        )

    @staticmethod
    def _make_row_key(row: dict) -> str:
        """Create a dedup key from raw row fields."""
        return (
            f"{row.get('Date', '')}|{row.get('Merchant', '')}|"
            f"{row.get('Account', '')}|{row.get('Amount', '')}|"
            f"{row.get('Original Statement', '')}"
        )
