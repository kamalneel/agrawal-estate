"""
Estate Planning API routes.
Handles wills, trusts, beneficiaries, and important contacts.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db

router = APIRouter()


@router.get("/documents")
async def list_estate_documents(
    db: Session = Depends(get_db),
    doc_type: Optional[str] = None
):
    """
    List estate planning documents.
    Document types: will, trust, poa, healthcare_directive, other
    """
    return {"documents": []}


@router.get("/documents/{document_id}")
async def get_document_details(document_id: int, db: Session = Depends(get_db)):
    """Get details for a specific estate document."""
    return {"document": None}


@router.post("/documents")
async def upload_document(db: Session = Depends(get_db)):
    """Upload a new estate planning document."""
    return {"document": None}


@router.get("/beneficiaries")
async def list_beneficiaries(db: Session = Depends(get_db)):
    """List all beneficiaries."""
    return {"beneficiaries": []}


@router.get("/beneficiaries/{beneficiary_id}")
async def get_beneficiary_details(beneficiary_id: int, db: Session = Depends(get_db)):
    """Get beneficiary details including allocations."""
    return {"beneficiary": None, "allocations": []}


@router.post("/beneficiaries")
async def create_beneficiary(db: Session = Depends(get_db)):
    """Add a new beneficiary."""
    return {"beneficiary": None}


@router.get("/contacts")
async def list_important_contacts(db: Session = Depends(get_db)):
    """
    List important contacts (attorneys, executors, trustees, accountants).
    """
    return {"contacts": []}


@router.post("/contacts")
async def create_contact(db: Session = Depends(get_db)):
    """Add an important contact."""
    return {"contact": None}


@router.get("/checklist")
async def get_estate_planning_checklist(db: Session = Depends(get_db)):
    """Get estate planning completeness checklist."""
    return {
        "items": [
            {"item": "Will", "status": "missing"},
            {"item": "Trust", "status": "missing"},
            {"item": "Power of Attorney", "status": "missing"},
            {"item": "Healthcare Directive", "status": "missing"},
            {"item": "Beneficiaries Designated", "status": "incomplete"},
            {"item": "Executor Named", "status": "missing"},
        ],
        "completion_percentage": 0
    }

