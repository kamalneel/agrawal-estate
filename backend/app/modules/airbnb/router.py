"""
Airbnb timeshare investment API routes.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from decimal import Decimal

from app.core.database import get_db
from app.core.auth import get_current_user
from app.modules.airbnb import services

router = APIRouter()


# ── Pydantic Schemas ──────────────────────────────────────────

class PropertyCreate(BaseModel):
    name: str
    property_type: Optional[str] = "WorldMark"
    points_per_week: Optional[int] = None
    income_per_week_best: Optional[float] = None
    income_per_week_worst: Optional[float] = None
    housekeeping_per_week: Optional[float] = None
    management_fee_pct: Optional[float] = 20.0
    capital_cost_rate_pct: Optional[float] = 8.0
    status: Optional[str] = "prospective"
    notes: Optional[str] = None


class PropertyUpdate(BaseModel):
    name: Optional[str] = None
    property_type: Optional[str] = None
    points_per_week: Optional[int] = None
    income_per_week_best: Optional[float] = None
    income_per_week_worst: Optional[float] = None
    housekeeping_per_week: Optional[float] = None
    management_fee_pct: Optional[float] = None
    capital_cost_rate_pct: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class BlockCreate(BaseModel):
    block_type: str  # 'owned', 'borrowed', or 'accumulated'
    points: int
    cost_to_acquire: Optional[float] = 0
    annual_cost_rate_pct: Optional[float] = None
    housekeeping_per_week: Optional[float] = None


class BlockUpdate(BaseModel):
    block_type: Optional[str] = None
    points: Optional[int] = None
    cost_to_acquire: Optional[float] = None
    annual_cost_rate_pct: Optional[float] = None
    housekeeping_per_week: Optional[float] = None


class LinkCreate(BaseModel):
    title: str
    url: str
    link_type: Optional[str] = "reference"
    notes: Optional[str] = None


# ── Property Endpoints ────────────────────────────────────────

@router.get("/properties")
async def list_properties(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """List all Airbnb properties with calculated metrics."""
    props = services.list_properties(db)
    return {"properties": props}


@router.post("/properties")
async def create_property(
    data: PropertyCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new Airbnb property."""
    prop = services.create_property(db, data.model_dump(exclude_unset=True))
    return {"success": True, "id": prop.id, "name": prop.name}


@router.get("/properties/{property_id}")
async def get_property(
    property_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get property detail with blocks, docs, links, and financial projections."""
    result = services.get_property(db, property_id)
    if not result:
        raise HTTPException(status_code=404, detail="Property not found")
    return result


@router.put("/properties/{property_id}")
async def update_property(
    property_id: int,
    data: PropertyUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Update property settings."""
    prop = services.update_property(db, property_id, data.model_dump(exclude_unset=True))
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return {"success": True, "id": prop.id}


@router.delete("/properties/{property_id}")
async def delete_property(
    property_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Delete property and all related data."""
    ok = services.delete_property(db, property_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Property not found")
    return {"success": True}


# ── Points Block Endpoints ────────────────────────────────────

@router.post("/properties/{property_id}/blocks")
async def create_block(
    property_id: int,
    data: BlockCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Add a points block to a property."""
    block = services.create_block(db, property_id, data.model_dump(exclude_unset=True))
    if not block:
        raise HTTPException(status_code=404, detail="Property not found")
    return {"success": True, "id": block.id}


@router.put("/blocks/{block_id}")
async def update_block(
    block_id: int,
    data: BlockUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Update a points block."""
    block = services.update_block(db, block_id, data.model_dump(exclude_unset=True))
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    return {"success": True, "id": block.id}


@router.delete("/blocks/{block_id}")
async def delete_block(
    block_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Delete a points block."""
    ok = services.delete_block(db, block_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Block not found")
    return {"success": True}


# ── Document Endpoints ────────────────────────────────────────

@router.post("/properties/{property_id}/documents")
async def upload_document(
    property_id: int,
    document_type: str = Form("other"),
    notes: str = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Upload a document for a property."""
    try:
        doc = await services.upload_document(db, property_id, file, document_type, notes)
        if not doc:
            raise HTTPException(status_code=404, detail="Property not found")
        return {
            "success": True,
            "document": {
                "id": doc.id,
                "file_name": doc.file_name,
                "document_type": doc.document_type,
                "file_size": doc.file_size,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/documents/{doc_id}/download")
async def download_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Download a document file."""
    doc = db.query(services.AirbnbDocument).filter(services.AirbnbDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = services.get_document_path(db, doc_id)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Document file not found")

    return FileResponse(
        path=file_path,
        filename=doc.file_name,
        media_type=doc.mime_type or "application/octet-stream",
    )


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Delete a document."""
    ok = services.delete_document(db, doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"success": True}


# ── Link Endpoints ────────────────────────────────────────────

@router.post("/properties/{property_id}/links")
async def create_link(
    property_id: int,
    data: LinkCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Add a link to a property."""
    link = services.create_link(db, property_id, data.model_dump(exclude_unset=True))
    if not link:
        raise HTTPException(status_code=404, detail="Property not found")
    return {"success": True, "id": link.id}


@router.delete("/links/{link_id}")
async def delete_link(
    link_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Delete a link."""
    ok = services.delete_link(db, link_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Link not found")
    return {"success": True}
