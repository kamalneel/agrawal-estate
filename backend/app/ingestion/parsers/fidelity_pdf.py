"""
Fidelity PDF statement parser ("INVESTMENT REPORT" quarterly and year-end).

Emits one ACCOUNT_SUMMARY per tracked account section: the period-end
balance (Ending Account Value), split into core cash (the FDRXX money-market
position, priced at $1) and securities (everything else). The split is
validated against the statement's own "Total Holdings" line and the file is
rejected when the pieces do not reproduce the printed total (playbook:
validate a parser against the source document's totals).

The statement also prints the period's Beginning Account Value, which is the
prior period-end close; that is emitted as a second snapshot dated the day
before the period starts, so a Q1 or year-end statement also yields the
previous Dec 31 balance.

Fidelity files can carry several accounts (the family's HSA and Jaya's
Individual TOD account sit in one envelope); pages are grouped by account
number and only accounts in FIDELITY_ACCOUNTS are recorded.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.ingestion.parsers.base import BaseParser, ParseResult, ParsedRecord, RecordType


#: Fidelity account number (digits only, hyphen removed) -> (account_id, owner, account_type)
FIDELITY_ACCOUNTS = {
    "235964125": ("family_hsa", "Jaya", "hsa"),
}

TOTALS_TOLERANCE = 1.00


class FidelityPDFParser(BaseParser):
    source_name = "fidelity"
    supported_extensions = [".pdf"]

    _ACCOUNT_NUMBER = re.compile(r'Account (?:Number|#):?\s*([A-Z0-9]{3}-?\d{6})')
    _PERIOD = re.compile(r'([A-Z][a-z]+ \d{1,2}, \d{4})\s*-\s*([A-Z][a-z]+ \d{1,2}, \d{4})')
    _AMOUNT = re.compile(r'\$([\d,]+\.\d{2})')
    # Core money-market line: "... $7,392.35 7,466.480 $1.0000 $7,466.48 ..." — the
    # quantity (3 decimals) printed right before the $1.0000 unit price is the cash.
    _CORE_QTY = re.compile(r'([\d,]+\.\d{3})\s+\$1\.0000')

    def can_parse(self, file_path: Path) -> bool:
        if file_path.suffix.lower() != '.pdf':
            return False
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                if not pdf.pages:
                    return False
                text = (pdf.pages[0].extract_text() or "").lower()
                return "investment report" in text and "fidelity" in text
        except Exception:
            return False

    def parse(self, file_path: Path) -> ParseResult:
        import pdfplumber

        records: List[ParsedRecord] = []
        warnings: List[str] = []
        errors: List[str] = []
        metadata: Dict[str, Any] = {"file_type": "pdf_statement", "source": "fidelity", "accounts": []}

        # Group pages by the account number printed on them.
        sections: Dict[str, List[tuple]] = {}
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                m = self._ACCOUNT_NUMBER.search(text)
                if not m:
                    continue
                sections.setdefault(m.group(1).replace('-', ''), []).append((page_num, text))

        for account_number, pages in sections.items():
            label = f"{file_path.name} account #{account_number}"
            summary_page = next((t for _, t in pages if 'Your Account Value' in t), None)
            if summary_page is None:
                continue  # a holdings/activity page for an account whose cover page was not read

            mapped = FIDELITY_ACCOUNTS.get(account_number)
            ending = self._first_amount_after(summary_page, 'Ending Account Value')
            if not mapped:
                warnings.append(f"{label}: not a tracked account (closing value {ending}); skipped")
                continue
            account_id, owner, account_type = mapped

            period = self._PERIOD.search(summary_page)
            if period is None or ending is None:
                errors.append(f"{label}: could not read the statement period or Ending Account Value")
                continue
            period_start = datetime.strptime(period.group(1), "%B %d, %Y").date()
            period_end = datetime.strptime(period.group(2), "%B %d, %Y").date()

            holdings_page = next((t for _, t in pages if 'Total Holdings' in t), None)
            cash = sec = None
            if holdings_page is not None:
                total_holdings = self._first_amount_after(holdings_page, 'Total Holdings')
                core = self._core_cash(holdings_page)
                if total_holdings is not None and abs(total_holdings - ending) > TOTALS_TOLERANCE:
                    errors.append(f"{label}: Total Holdings {total_holdings:,.2f} does not match "
                                  f"Ending Account Value {ending:,.2f}; file rejected")
                    continue
                if core is not None:
                    cash = core
                    sec = round(ending - core, 2)
            else:
                warnings.append(f"{label}: no Holdings page; cash/securities split not recorded")

            base = {"source": self.source_name, "account_id": account_id, "owner": owner,
                    "account_type": account_type, "account_number": account_number}
            records.append(ParsedRecord(record_type=RecordType.ACCOUNT_SUMMARY, source_row=pages[0][0], data={
                **base, "statement_date": period_end, "portfolio_value": ending,
                "cash_balance": cash, "securities_value": sec,
            }))
            metadata["accounts"].append({"account_id": account_id, "statement_date": period_end.isoformat(),
                                         "portfolio_value": ending})

            # Prior period-end close, printed as this period's beginning value.
            beginning = self._first_amount_after(summary_page, 'Beginning Account Value')
            if beginning is not None:
                prior_end = period_start - timedelta(days=1)
                begin_cash = self._core_beginning_cash(holdings_page) if holdings_page else None
                records.append(ParsedRecord(record_type=RecordType.ACCOUNT_SUMMARY, source_row=pages[0][0], data={
                    **base, "statement_date": prior_end, "portfolio_value": beginning,
                    "cash_balance": begin_cash,
                    "securities_value": round(beginning - begin_cash, 2) if begin_cash is not None else None,
                }))
                metadata["accounts"].append({"account_id": account_id, "statement_date": prior_end.isoformat(),
                                             "portfolio_value": beginning, "from": "beginning balance"})

        if not records and not errors:
            warnings.append(f"{file_path.name}: no tracked account summary found")

        return ParseResult(success=not errors, source_name=self.source_name, file_path=file_path,
                           records=records, warnings=warnings, errors=errors, metadata=metadata)

    # ── helpers ──────────────────────────────────────────────────────────

    def _first_amount_after(self, text: str, prefix: str) -> Optional[float]:
        for raw in text.split('\n'):
            line = raw.strip()
            if line.startswith(prefix):
                amts = self._AMOUNT.findall(line)
                if amts:
                    return float(amts[0].replace(',', ''))
        return None

    def _core_cash(self, holdings_text: str) -> Optional[float]:
        """Ending core cash: the money-market quantity at $1.0000, within the Core Account block."""
        block = self._core_block(holdings_text)
        m = self._CORE_QTY.search(block)
        return float(m.group(1).replace(',', '')) if m else None

    def _core_beginning_cash(self, holdings_text: str) -> Optional[float]:
        """Quarterly layout prints the core line as '<desc> $<beginning MV> <qty> $1.0000 $<ending MV> ...';
        the first dollar amount on that line is the beginning value. Year-end statements omit it."""
        block = self._core_block(holdings_text)
        for raw in block.split('\n'):
            if self._CORE_QTY.search(raw):
                amts = self._AMOUNT.findall(raw)
                qty = self._CORE_QTY.search(raw)
                # Beginning MV is printed before the quantity; ending MV after the unit price.
                if amts and raw.find('$' + amts[0]) < raw.find(qty.group(1)):
                    return float(amts[0].replace(',', ''))
        return None

    @staticmethod
    def _core_block(holdings_text: str) -> str:
        start = holdings_text.find('Core Account')
        end = holdings_text.find('Total Core Account')
        if start == -1:
            return ''
        return holdings_text[start:end if end != -1 else None]
