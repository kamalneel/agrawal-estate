"""
Actual Tax Service

Handles aggregating and comparing actual tax data from uploaded documents
against forecasted values.
"""

from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.modules.tax.models import ActualTaxItem, TaxDocumentUpload


# Expected documents for a complete tax file
EXPECTED_DOCUMENTS = {
    'W-2': {'description': 'Wages and salary', 'min_expected': 1},
    '1099-INT': {'description': 'Interest income', 'min_expected': 0},
    '1099-DIV': {'description': 'Dividend income', 'min_expected': 0},
    '1099-B': {'description': 'Brokerage transactions', 'min_expected': 0},
    '1099-R': {'description': 'Retirement distributions', 'min_expected': 0},
    '1098': {'description': 'Mortgage interest', 'min_expected': 0},
    'K-1': {'description': 'Partnership income', 'min_expected': 0},
    'PROPERTY-TAX': {'description': 'Property tax bills', 'min_expected': 0},
}

# Document type to form fields mapping
# Each document type has fields that should be extracted
DOCUMENT_FIELD_MAPPING = {
    'W-2': [
        {'field': 'wages', 'form_line': '1040:1', 'label': 'Wages, tips, other compensation (Box 1)', 'required': True},
        {'field': 'federal_withheld', 'form_line': '1040:25a', 'label': 'Federal income tax withheld (Box 2)', 'required': True},
        {'field': 'social_security_wages', 'form_line': 'W2:3', 'label': 'Social Security wages (Box 3)', 'required': False},
        {'field': 'social_security_tax', 'form_line': 'W2:4', 'label': 'Social Security tax withheld (Box 4)', 'required': False},
        {'field': 'medicare_wages', 'form_line': 'W2:5', 'label': 'Medicare wages (Box 5)', 'required': False},
        {'field': 'medicare_tax', 'form_line': 'W2:6', 'label': 'Medicare tax withheld (Box 6)', 'required': False},
        {'field': 'state_wages', 'form_line': 'W2:16', 'label': 'State wages (Box 16)', 'required': False},
        {'field': 'state_withheld', 'form_line': 'W2:17', 'label': 'State income tax withheld (Box 17)', 'required': False},
    ],
    '1099-INT': [
        {'field': 'interest_income', 'form_line': '1040:2b', 'label': 'Interest income (Box 1)', 'required': True},
        {'field': 'early_withdrawal_penalty', 'form_line': 'SCH1:17', 'label': 'Early withdrawal penalty (Box 2)', 'required': False},
        {'field': 'federal_withheld', 'form_line': '1040:25b', 'label': 'Federal income tax withheld (Box 4)', 'required': False},
        {'field': 'tax_exempt_interest', 'form_line': '1040:2a', 'label': 'Tax-exempt interest (Box 8)', 'required': False},
    ],
    '1099-DIV': [
        {'field': 'ordinary_dividends', 'form_line': '1040:3b', 'label': 'Total ordinary dividends (Box 1a)', 'required': True},
        {'field': 'qualified_dividends', 'form_line': '1040:3a', 'label': 'Qualified dividends (Box 1b)', 'required': True},
        {'field': 'capital_gain_distributions', 'form_line': 'SCHD:13', 'label': 'Capital gain distributions (Box 2a)', 'required': False},
        {'field': 'federal_withheld', 'form_line': '1040:25b', 'label': 'Federal income tax withheld (Box 4)', 'required': False},
        {'field': 'section_199a', 'form_line': '1099DIV:5', 'label': 'Section 199A dividends (Box 5)', 'required': False},
    ],
    '1099-B': [
        {'field': 'proceeds', 'form_line': 'SCHD:1d', 'label': 'Total proceeds (Box 1d)', 'required': True},
        {'field': 'cost_basis', 'form_line': 'SCHD:1e', 'label': 'Cost or other basis (Box 1e)', 'required': True},
        {'field': 'gain_loss', 'form_line': '1040:7', 'label': 'Net gain or loss', 'required': False},
        {'field': 'short_term_gain', 'form_line': 'SCHD:7', 'label': 'Short-term gain/loss', 'required': False},
        {'field': 'long_term_gain', 'form_line': 'SCHD:15', 'label': 'Long-term gain/loss', 'required': False},
        {'field': 'federal_withheld', 'form_line': '1040:25b', 'label': 'Federal income tax withheld (Box 4)', 'required': False},
    ],
    '1099-R': [
        {'field': 'gross_distribution', 'form_line': '1040:4a', 'label': 'Gross distribution (Box 1)', 'required': True},
        {'field': 'taxable_amount', 'form_line': '1040:4b', 'label': 'Taxable amount (Box 2a)', 'required': True},
        {'field': 'federal_withheld', 'form_line': '1040:25b', 'label': 'Federal income tax withheld (Box 4)', 'required': False},
        {'field': 'state_withheld', 'form_line': '1099R:12', 'label': 'State tax withheld (Box 12)', 'required': False},
    ],
    '1099-MISC': [
        {'field': 'rents', 'form_line': 'SCHE:3', 'label': 'Rents (Box 1)', 'required': False},
        {'field': 'royalties', 'form_line': 'SCHE:4', 'label': 'Royalties (Box 2)', 'required': False},
        {'field': 'other_income', 'form_line': 'SCH1:8z', 'label': 'Other income (Box 3)', 'required': False},
        {'field': 'federal_withheld', 'form_line': '1040:25b', 'label': 'Federal income tax withheld (Box 4)', 'required': False},
    ],
    '1099-NEC': [
        {'field': 'nonemployee_compensation', 'form_line': 'SCHC:1', 'label': 'Nonemployee compensation (Box 1)', 'required': True},
        {'field': 'federal_withheld', 'form_line': '1040:25b', 'label': 'Federal income tax withheld (Box 4)', 'required': False},
    ],
    '1099-K': [
        {'field': 'gross_amount', 'form_line': 'SCHC:1', 'label': 'Gross amount of payment card transactions (Box 1a)', 'required': True},
        {'field': 'federal_withheld', 'form_line': '1040:25b', 'label': 'Federal income tax withheld (Box 4)', 'required': False},
    ],
    '1098': [
        {'field': 'mortgage_interest', 'form_line': 'SCHA:8a', 'label': 'Mortgage interest received (Box 1)', 'required': True},
        {'field': 'points_paid', 'form_line': 'SCHA:8c', 'label': 'Points paid on purchase (Box 6)', 'required': False},
        {'field': 'property_taxes', 'form_line': 'SCHA:5b', 'label': 'Real estate taxes (Box 10)', 'required': False},
    ],
    'K-1': [
        {'field': 'ordinary_income', 'form_line': 'SCHE:28', 'label': 'Ordinary business income (Box 1)', 'required': False},
        {'field': 'rental_income', 'form_line': 'SCHE:28', 'label': 'Net rental real estate income (Box 2)', 'required': False},
        {'field': 'interest_income', 'form_line': '1040:2b', 'label': 'Interest income (Box 5)', 'required': False},
        {'field': 'dividends', 'form_line': '1040:3b', 'label': 'Dividends (Box 6a)', 'required': False},
        {'field': 'capital_gains', 'form_line': 'SCHD:11', 'label': 'Net short-term capital gain (Box 8)', 'required': False},
        {'field': 'section_199a', 'form_line': 'K1:20', 'label': 'Section 199A income (Box 20)', 'required': False},
    ],
    'PROPERTY-TAX': [
        {'field': 'property_tax', 'form_line': 'SCHA:5b', 'label': 'Real estate taxes paid', 'required': True},
        {'field': 'property_address', 'form_line': 'INFO', 'label': 'Property address', 'required': False},
    ],
    'CHARITABLE': [
        {'field': 'cash_donations', 'form_line': 'SCHA:11', 'label': 'Cash contributions', 'required': False},
        {'field': 'noncash_donations', 'form_line': 'SCHA:12', 'label': 'Non-cash contributions', 'required': False},
    ],
    'OTHER': [
        {'field': 'amount', 'form_line': 'OTHER', 'label': 'Amount', 'required': False},
        {'field': 'description', 'form_line': 'INFO', 'label': 'Description', 'required': False},
    ],
}

# Form 1040 line mappings
FORM_1040_LINES = {
    '1040:1': 'Wages, salaries, tips',
    '1040:2a': 'Tax-exempt interest',
    '1040:2b': 'Taxable interest',
    '1040:3a': 'Qualified dividends',
    '1040:3b': 'Ordinary dividends',
    '1040:4a': 'IRA distributions',
    '1040:4b': 'Taxable IRA distributions',
    '1040:5a': 'Pensions and annuities',
    '1040:5b': 'Taxable pensions',
    '1040:6a': 'Social Security benefits',
    '1040:6b': 'Taxable Social Security',
    '1040:7': 'Capital gain or loss',
    '1040:8': 'Other income (Schedule 1)',
    '1040:9': 'Total income',
    '1040:10': 'Adjustments to income',
    '1040:11': 'Adjusted Gross Income',
    '1040:12': 'Standard or itemized deductions',
    '1040:13': 'Qualified business income deduction',
    '1040:14': 'Taxable income',
    '1040:15': 'Tax',
    '1040:16': 'Tax',
    '1040:17': 'Credits',
    '1040:18': 'Additional taxes',
    '1040:22': 'Total tax',
    '1040:24': 'Total tax',
    '1040:25': 'Federal income tax withheld',
    '1040:26': 'Estimated tax payments',
    '1040:33': 'Total payments',
    '1040:34': 'Refund',
    '1040:37': 'Amount owed',
}


class ActualTaxService:
    """Service for managing actual tax data from documents."""

    def __init__(self, db: Session):
        self.db = db

    def get_actual_tax_items(self, year: int) -> List[ActualTaxItem]:
        """Get all actual tax items for a year."""
        return self.db.query(ActualTaxItem).filter(
            ActualTaxItem.tax_year == year
        ).order_by(ActualTaxItem.form_line).all()

    def get_actual_tax_data(self, year: int) -> Dict:
        """
        Get aggregated actual tax data by form line.

        Args:
            year: Tax year

        Returns:
            Dict with aggregated values by form line
        """
        items = self.get_actual_tax_items(year)

        # Group by form line
        by_line = {}
        for item in items:
            if item.form_line not in by_line:
                by_line[item.form_line] = {
                    'description': item.description or FORM_1040_LINES.get(item.form_line, ''),
                    'amount': Decimal(0),
                    'sources': [],
                    'is_manual': False
                }

            by_line[item.form_line]['amount'] += Decimal(str(item.amount))
            by_line[item.form_line]['sources'].append({
                'id': item.id,
                'amount': float(item.amount),
                'document_id': item.source_document_id,
                'is_manual': item.is_manual_entry,
                'notes': item.notes
            })
            if item.is_manual_entry:
                by_line[item.form_line]['is_manual'] = True

        # Convert to float for JSON serialization
        result = {}
        for line, data in by_line.items():
            result[line] = {
                'description': data['description'],
                'amount': float(data['amount']),
                'sources': data['sources'],
                'is_manual': data['is_manual']
            }

        return {
            'tax_year': year,
            'items': result,
            'total_items': len(items)
        }

    def get_comparison(self, year: int, forecast_data: Dict) -> Dict:
        """
        Compare actual tax data against forecast.

        Args:
            year: Tax year
            forecast_data: Dict of forecasted values by form line

        Returns:
            Dict with line-by-line comparison
        """
        actual_data = self.get_actual_tax_data(year)
        actual_items = actual_data.get('items', {})

        comparison = {}
        all_lines = set(list(actual_items.keys()) + list(forecast_data.keys()))

        for line in sorted(all_lines):
            actual_amount = actual_items.get(line, {}).get('amount', 0)
            forecast_amount = forecast_data.get(line, 0)
            difference = actual_amount - forecast_amount

            comparison[line] = {
                'description': actual_items.get(line, {}).get('description') or FORM_1040_LINES.get(line, ''),
                'actual': actual_amount,
                'forecast': forecast_amount,
                'difference': difference,
                'difference_pct': round((difference / forecast_amount * 100), 2) if forecast_amount else 0,
                'has_actual': line in actual_items,
                'has_forecast': line in forecast_data
            }

        return {
            'tax_year': year,
            'comparison': comparison,
            'summary': {
                'lines_with_actual': sum(1 for c in comparison.values() if c['has_actual']),
                'lines_with_forecast': sum(1 for c in comparison.values() if c['has_forecast']),
                'lines_with_both': sum(1 for c in comparison.values() if c['has_actual'] and c['has_forecast']),
                'total_actual_difference': sum(c['difference'] for c in comparison.values())
            }
        }

    def get_completeness(self, year: int) -> Dict:
        """
        Check document completeness for a year.

        Args:
            year: Tax year

        Returns:
            Dict with completeness analysis
        """
        # Get document counts by type
        doc_counts = self.db.query(
            TaxDocumentUpload.document_type,
            func.count(TaxDocumentUpload.id).label('count')
        ).filter(
            TaxDocumentUpload.tax_year == year
        ).group_by(TaxDocumentUpload.document_type).all()

        doc_counts_dict = {row[0]: row[1] for row in doc_counts}

        # Check against expected documents
        completeness = {}
        missing = []
        received = []

        for doc_type, info in EXPECTED_DOCUMENTS.items():
            count = doc_counts_dict.get(doc_type, 0)
            is_complete = count >= info['min_expected']

            completeness[doc_type] = {
                'description': info['description'],
                'expected': info['min_expected'],
                'received': count,
                'complete': is_complete
            }

            if count > 0:
                received.append(doc_type)
            elif info['min_expected'] > 0:
                missing.append(doc_type)

        # Calculate overall completeness
        total_expected = sum(1 for info in EXPECTED_DOCUMENTS.values() if info['min_expected'] > 0)
        total_complete = sum(1 for c in completeness.values() if c['complete'] and c['expected'] > 0)

        return {
            'tax_year': year,
            'completeness': completeness,
            'missing_required': missing,
            'received': received,
            'total_documents': sum(doc_counts_dict.values()),
            'overall_pct': round((total_complete / total_expected * 100), 1) if total_expected > 0 else 100
        }

    def add_manual_item(
        self,
        year: int,
        form_line: str,
        amount: Decimal,
        description: Optional[str] = None,
        notes: Optional[str] = None
    ) -> ActualTaxItem:
        """
        Add a manual tax item (not from a document).

        Args:
            year: Tax year
            form_line: Form line reference (e.g., '1040:1')
            amount: Amount
            description: Description of the item
            notes: Additional notes

        Returns:
            Created ActualTaxItem
        """
        item = ActualTaxItem(
            tax_year=year,
            form_line=form_line,
            description=description or FORM_1040_LINES.get(form_line, ''),
            amount=amount,
            source_document_id=None,
            is_manual_entry=True,
            notes=notes
        )

        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)

        return item

    def add_item_from_document(
        self,
        year: int,
        form_line: str,
        amount: Decimal,
        document_id: int,
        description: Optional[str] = None,
        notes: Optional[str] = None
    ) -> ActualTaxItem:
        """
        Add a tax item extracted from a document.

        Args:
            year: Tax year
            form_line: Form line reference
            amount: Amount
            document_id: Source document ID
            description: Description
            notes: Additional notes

        Returns:
            Created ActualTaxItem
        """
        item = ActualTaxItem(
            tax_year=year,
            form_line=form_line,
            description=description or FORM_1040_LINES.get(form_line, ''),
            amount=amount,
            source_document_id=document_id,
            is_manual_entry=False,
            notes=notes
        )

        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)

        return item

    def delete_item(self, item_id: int) -> bool:
        """
        Delete a tax item.

        Args:
            item_id: Item ID

        Returns:
            True if deleted, False if not found
        """
        item = self.db.query(ActualTaxItem).filter(ActualTaxItem.id == item_id).first()
        if not item:
            return False

        self.db.delete(item)
        self.db.commit()
        return True

    def update_item(
        self,
        item_id: int,
        amount: Optional[Decimal] = None,
        description: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Optional[ActualTaxItem]:
        """
        Update a tax item.

        Args:
            item_id: Item ID
            amount: New amount
            description: New description
            notes: New notes

        Returns:
            Updated item or None if not found
        """
        item = self.db.query(ActualTaxItem).filter(ActualTaxItem.id == item_id).first()
        if not item:
            return None

        if amount is not None:
            item.amount = amount
        if description is not None:
            item.description = description
        if notes is not None:
            item.notes = notes

        self.db.commit()
        self.db.refresh(item)

        return item

    def get_document_fields(self, document_type: str) -> List[Dict]:
        """
        Get the form fields that should be extracted for a document type.

        Args:
            document_type: Type of document (e.g., 'W-2', '1099-INT')

        Returns:
            List of field definitions with form_line, label, required
        """
        return DOCUMENT_FIELD_MAPPING.get(document_type.upper(), DOCUMENT_FIELD_MAPPING['OTHER'])

    def process_document(
        self,
        document_id: int,
        extracted_values: List[Dict],
        year: int
    ) -> List[ActualTaxItem]:
        """
        Process a document by saving its extracted values as ActualTaxItems.

        Args:
            document_id: ID of the document being processed
            extracted_values: List of dicts with {form_line, amount, description, notes}
            year: Tax year

        Returns:
            List of created ActualTaxItem records
        """
        import json

        # Get the document
        doc = self.db.query(TaxDocumentUpload).filter(
            TaxDocumentUpload.id == document_id
        ).first()

        if not doc:
            raise ValueError(f"Document {document_id} not found")

        # Delete any existing items from this document (re-processing)
        self.db.query(ActualTaxItem).filter(
            ActualTaxItem.source_document_id == document_id
        ).delete()

        created_items = []

        for value in extracted_values:
            if value.get('amount') is None or value.get('amount') == '':
                continue

            amount = Decimal(str(value['amount']))
            if amount == 0:
                continue

            item = ActualTaxItem(
                tax_year=year,
                form_line=value['form_line'],
                description=value.get('description') or value.get('label', ''),
                amount=amount,
                source_document_id=document_id,
                is_manual_entry=False,
                notes=value.get('notes')
            )

            self.db.add(item)
            created_items.append(item)

        # Update document status and store extracted data
        doc.status = 'processed'
        doc.extracted_data = json.dumps(extracted_values)

        self.db.commit()

        # Refresh all items to get IDs
        for item in created_items:
            self.db.refresh(item)

        return created_items

    def get_items_by_document(self, document_id: int) -> List[ActualTaxItem]:
        """
        Get all tax items that were extracted from a specific document.

        Args:
            document_id: Document ID

        Returns:
            List of ActualTaxItem records
        """
        return self.db.query(ActualTaxItem).filter(
            ActualTaxItem.source_document_id == document_id
        ).all()
