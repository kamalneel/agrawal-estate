"""
Tax Document Service

Handles uploading, storing, and retrieving tax documents (1099s, W-2s, etc.)
"""

import hashlib
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.tax.models import TaxDocumentUpload


# Document type folders mapping
DOCUMENT_TYPE_FOLDERS = {
    '1099-INT': '1099-int',
    '1099-DIV': '1099-div',
    '1099-B': '1099-b',
    '1099-R': '1099-r',
    '1099-MISC': '1099-misc',
    '1099-NEC': '1099-nec',
    '1099-K': '1099-k',
    'W-2': 'w-2',
    '1098': '1098',
    'K-1': 'k-1',
    'PROPERTY-TAX': 'property-tax',
    'CHARITABLE': 'charitable',
    'OTHER': 'other',
}


class TaxDocumentService:
    """Service for managing tax document uploads."""

    def __init__(self, db: Session):
        self.db = db

    def _ensure_directory(self, year: int, doc_type: str) -> Path:
        """Ensure the directory exists for storing documents."""
        folder_name = DOCUMENT_TYPE_FOLDERS.get(doc_type.upper(), 'other')
        dir_path = settings.TAX_DOCUMENTS_DIR / str(year) / folder_name
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to prevent path traversal."""
        # Remove any directory components
        filename = os.path.basename(filename)
        # Replace problematic characters
        for char in ['/', '\\', '..', '<', '>', ':', '"', '|', '?', '*']:
            filename = filename.replace(char, '_')
        return filename

    def get_documents_by_year(self, year: int) -> List[TaxDocumentUpload]:
        """Get all documents for a tax year."""
        return self.db.query(TaxDocumentUpload).filter(
            TaxDocumentUpload.tax_year == year
        ).order_by(
            TaxDocumentUpload.document_type,
            TaxDocumentUpload.upload_date.desc()
        ).all()

    def get_document_by_id(self, doc_id: int) -> Optional[TaxDocumentUpload]:
        """Get a document by ID."""
        return self.db.query(TaxDocumentUpload).filter(
            TaxDocumentUpload.id == doc_id
        ).first()

    def get_documents_by_type(self, year: int, doc_type: str) -> List[TaxDocumentUpload]:
        """Get all documents of a specific type for a year."""
        return self.db.query(TaxDocumentUpload).filter(
            TaxDocumentUpload.tax_year == year,
            TaxDocumentUpload.document_type == doc_type.upper()
        ).order_by(TaxDocumentUpload.upload_date.desc()).all()

    async def upload_document(
        self,
        year: int,
        file: UploadFile,
        doc_type: str,
        institution_name: Optional[str] = None,
        institution_ein: Optional[str] = None,
        document_date: Optional[str] = None,
        notes: Optional[str] = None
    ) -> TaxDocumentUpload:
        """
        Upload a tax document.

        Args:
            year: Tax year
            file: Uploaded file
            doc_type: Document type (e.g., '1099-INT', 'W-2')
            institution_name: Name of the institution
            institution_ein: Employer ID Number
            document_date: Date on the document (ISO format)
            notes: Additional notes

        Returns:
            Created TaxDocumentUpload instance
        """
        doc_type = doc_type.upper()

        # Ensure directory exists
        dir_path = self._ensure_directory(year, doc_type)

        # Sanitize and prepare filename
        original_filename = self._sanitize_filename(file.filename or "document")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_ext = Path(original_filename).suffix or ".pdf"
        base_name = Path(original_filename).stem

        # Create unique filename
        new_filename = f"{base_name}_{timestamp}{file_ext}"
        file_path = dir_path / new_filename

        # Save file
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        # Compute hash
        file_hash = self._compute_file_hash(file_path)

        # Check for duplicates
        existing = self.db.query(TaxDocumentUpload).filter(
            TaxDocumentUpload.tax_year == year,
            TaxDocumentUpload.file_hash == file_hash
        ).first()

        if existing:
            # Remove the just-saved duplicate file
            file_path.unlink(missing_ok=True)
            raise ValueError(f"Duplicate document detected. This file was already uploaded as '{existing.file_name}'")

        # Parse document date if provided
        parsed_doc_date = None
        if document_date:
            try:
                parsed_doc_date = datetime.fromisoformat(document_date).date()
            except ValueError:
                pass

        # Create database record
        doc = TaxDocumentUpload(
            tax_year=year,
            document_type=doc_type,
            institution_name=institution_name,
            institution_ein=institution_ein,
            file_name=original_filename,
            file_path=str(file_path.relative_to(settings.BASE_DIR)),
            file_hash=file_hash,
            file_size=len(content),
            mime_type=file.content_type,
            upload_date=datetime.utcnow(),
            document_date=parsed_doc_date,
            status='uploaded',
            notes=notes
        )

        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)

        return doc

    def delete_document(self, doc_id: int) -> bool:
        """
        Delete a document and its file.

        Args:
            doc_id: Document ID

        Returns:
            True if deleted, False if not found
        """
        doc = self.get_document_by_id(doc_id)
        if not doc:
            return False

        # Delete file
        file_path = settings.BASE_DIR / doc.file_path
        if file_path.exists():
            file_path.unlink()

        # Delete database record
        self.db.delete(doc)
        self.db.commit()

        return True

    def get_file_path(self, doc_id: int) -> Optional[Path]:
        """
        Get the full file path for a document.

        Args:
            doc_id: Document ID

        Returns:
            Full Path to the file, or None if not found
        """
        doc = self.get_document_by_id(doc_id)
        if not doc:
            return None

        return settings.BASE_DIR / doc.file_path

    def update_document_status(
        self,
        doc_id: int,
        status: str,
        extracted_data: Optional[str] = None
    ) -> Optional[TaxDocumentUpload]:
        """
        Update document status.

        Args:
            doc_id: Document ID
            status: New status ('uploaded', 'processed', 'verified')
            extracted_data: JSON string of extracted data

        Returns:
            Updated document or None if not found
        """
        doc = self.get_document_by_id(doc_id)
        if not doc:
            return None

        doc.status = status
        if extracted_data is not None:
            doc.extracted_data = extracted_data

        self.db.commit()
        self.db.refresh(doc)

        return doc

    def get_document_stats(self, year: int) -> dict:
        """
        Get statistics about uploaded documents for a year.

        Args:
            year: Tax year

        Returns:
            Dict with document counts by type and status
        """
        docs = self.get_documents_by_year(year)

        by_type = {}
        by_status = {'uploaded': 0, 'processed': 0, 'verified': 0}

        for doc in docs:
            # Count by type
            if doc.document_type not in by_type:
                by_type[doc.document_type] = 0
            by_type[doc.document_type] += 1

            # Count by status
            if doc.status in by_status:
                by_status[doc.status] += 1

        return {
            'total': len(docs),
            'by_type': by_type,
            'by_status': by_status
        }
