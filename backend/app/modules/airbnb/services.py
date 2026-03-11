"""
Airbnb timeshare investment service.

Handles CRUD operations, financial calculations, and document management.
"""

import hashlib
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.airbnb.models import (
    AirbnbProperty, AirbnbPointsBlock, AirbnbDocument, AirbnbLink
)


def _d(val) -> Decimal:
    """Convert to Decimal safely."""
    if val is None:
        return Decimal("0")
    return Decimal(str(val))


def calculate_block_metrics(block: AirbnbPointsBlock, prop: AirbnbProperty, scenario: str = "best") -> Dict[str, Any]:
    """
    Calculate financial metrics for a single points block.

    Args:
        block: The points block (owned or borrowed)
        prop: The parent property (for shared settings)
        scenario: 'best' or 'worst' income scenario

    Returns:
        Dict with all calculated metrics
    """
    points = _d(block.points)
    points_per_week = _d(prop.points_per_week) if prop.points_per_week else Decimal("1")

    income_per_week = _d(prop.income_per_week_best if scenario == "best" else prop.income_per_week_worst)
    # Block-level housekeeping overrides property default (borrowed gets tokens)
    housekeeping_pw = _d(block.housekeeping_per_week) if block.housekeeping_per_week is not None else _d(prop.housekeeping_per_week)
    mgmt_fee_pct = _d(prop.management_fee_pct) / Decimal("100")
    capital_cost_pct = _d(prop.capital_cost_rate_pct) / Decimal("100")
    annual_cost_rate = _d(block.annual_cost_rate_pct) / Decimal("100")

    weeks = points / points_per_week if points_per_week else Decimal("0")
    annual_revenue = weeks * income_per_week
    yearly_maintenance = annual_cost_rate * points
    monthly_maintenance = yearly_maintenance / Decimal("12")
    housekeeping_total = weeks * housekeeping_pw
    gross_profit = annual_revenue - yearly_maintenance - housekeeping_total
    management_fee = mgmt_fee_pct * gross_profit
    capital_cost = capital_cost_pct * (yearly_maintenance + housekeeping_total)
    annual_profit = gross_profit - management_fee - capital_cost
    is_one_time = block.block_type == "accumulated"
    five_year_return = annual_profit if is_one_time else annual_profit * Decimal("5")

    return {
        "block_id": block.id,
        "block_type": block.block_type,
        "points": int(points),
        "cost_to_acquire": float(_d(block.cost_to_acquire)),
        "annual_cost_rate_pct": float(_d(block.annual_cost_rate_pct)),
        "housekeeping_per_week": float(housekeeping_pw),
        "weeks": float(weeks.quantize(Decimal("0.01"))),
        "annual_revenue": float(annual_revenue.quantize(Decimal("0.01"))),
        "yearly_maintenance": float(yearly_maintenance.quantize(Decimal("0.01"))),
        "monthly_maintenance": float(monthly_maintenance.quantize(Decimal("0.01"))),
        "housekeeping_total": float(housekeeping_total.quantize(Decimal("0.01"))),
        "gross_profit": float(gross_profit.quantize(Decimal("0.01"))),
        "management_fee": float(management_fee.quantize(Decimal("0.01"))),
        "capital_cost": float(capital_cost.quantize(Decimal("0.01"))),
        "annual_profit": float(annual_profit.quantize(Decimal("0.01"))),
        "five_year_return": float(five_year_return.quantize(Decimal("0.01"))),
    }


def calculate_property_metrics(prop: AirbnbProperty, scenario: str = "best") -> Dict[str, Any]:
    """
    Calculate aggregate financial metrics for a property (summing all blocks).
    """
    block_metrics = []
    totals = {
        "total_points": 0,
        "total_initial_investment": 0.0,
        "total_weeks": 0.0,
        "total_annual_revenue": 0.0,
        "total_yearly_maintenance": 0.0,
        "total_housekeeping": 0.0,
        "total_gross_profit": 0.0,
        "total_management_fee": 0.0,
        "total_capital_cost": 0.0,
        "total_annual_profit": 0.0,
        "total_five_year_return": 0.0,
    }

    for block in prop.blocks:
        metrics = calculate_block_metrics(block, prop, scenario)
        block_metrics.append(metrics)

        totals["total_points"] += metrics["points"]
        totals["total_initial_investment"] += metrics["cost_to_acquire"]
        totals["total_weeks"] += metrics["weeks"]
        totals["total_annual_revenue"] += metrics["annual_revenue"]
        totals["total_yearly_maintenance"] += metrics["yearly_maintenance"]
        totals["total_housekeeping"] += metrics["housekeeping_total"]
        totals["total_gross_profit"] += metrics["gross_profit"]
        totals["total_management_fee"] += metrics["management_fee"]
        totals["total_capital_cost"] += metrics["capital_cost"]
        totals["total_annual_profit"] += metrics["annual_profit"]
        totals["total_five_year_return"] += metrics["five_year_return"]

    # Cash flow needed = all upfront costs before revenue arrives
    totals["total_annual_cash_outflow"] = totals["total_yearly_maintenance"] + totals["total_housekeeping"]

    # Round totals
    for key in totals:
        if isinstance(totals[key], float):
            totals[key] = round(totals[key], 2)

    return {
        "blocks": block_metrics,
        **totals,
    }


# ── CRUD: Properties ──────────────────────────────────────────

def list_properties(db: Session) -> List[Dict[str, Any]]:
    """List all properties with calculated metrics."""
    props = db.query(AirbnbProperty).order_by(AirbnbProperty.name).all()
    results = []
    for prop in props:
        metrics = calculate_property_metrics(prop)
        results.append({
            "id": prop.id,
            "name": prop.name,
            "property_type": prop.property_type,
            "status": prop.status,
            "notes": prop.notes,
            "points_per_week": prop.points_per_week,
            "income_per_week_best": float(_d(prop.income_per_week_best)),
            "income_per_week_worst": float(_d(prop.income_per_week_worst)),
            "housekeeping_per_week": float(_d(prop.housekeeping_per_week)),
            "management_fee_pct": float(_d(prop.management_fee_pct)),
            "capital_cost_rate_pct": float(_d(prop.capital_cost_rate_pct)),
            "block_count": len(prop.blocks),
            "document_count": len(prop.documents),
            "link_count": len(prop.links),
            **metrics,
        })
    return results


def get_property(db: Session, property_id: int) -> Optional[Dict[str, Any]]:
    """Get property detail with blocks, docs, links, and metrics."""
    prop = db.query(AirbnbProperty).filter(AirbnbProperty.id == property_id).first()
    if not prop:
        return None

    metrics = calculate_property_metrics(prop)
    worst_metrics = calculate_property_metrics(prop, scenario="worst")

    return {
        "id": prop.id,
        "name": prop.name,
        "property_type": prop.property_type,
        "status": prop.status,
        "notes": prop.notes,
        "points_per_week": prop.points_per_week,
        "income_per_week_best": float(_d(prop.income_per_week_best)),
        "income_per_week_worst": float(_d(prop.income_per_week_worst)),
        "housekeeping_per_week": float(_d(prop.housekeeping_per_week)),
        "management_fee_pct": float(_d(prop.management_fee_pct)),
        "capital_cost_rate_pct": float(_d(prop.capital_cost_rate_pct)),
        "created_at": prop.created_at.isoformat() if prop.created_at else None,
        "updated_at": prop.updated_at.isoformat() if prop.updated_at else None,
        # Best-case metrics
        **metrics,
        # Worst-case for comparison
        "worst_case": {
            "total_annual_profit": worst_metrics["total_annual_profit"],
            "total_five_year_return": worst_metrics["total_five_year_return"],
            "total_gross_profit": worst_metrics["total_gross_profit"],
            "blocks": worst_metrics["blocks"],
        },
        # Related objects
        "documents": [
            {
                "id": doc.id,
                "document_type": doc.document_type,
                "file_name": doc.file_name,
                "file_size": doc.file_size,
                "mime_type": doc.mime_type,
                "notes": doc.notes,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in prop.documents
        ],
        "links": [
            {
                "id": link.id,
                "title": link.title,
                "url": link.url,
                "link_type": link.link_type,
                "notes": link.notes,
            }
            for link in prop.links
        ],
    }


def create_property(db: Session, data: Dict[str, Any]) -> AirbnbProperty:
    """Create a new property."""
    prop = AirbnbProperty(
        name=data["name"],
        property_type=data.get("property_type"),
        points_per_week=data.get("points_per_week"),
        income_per_week_best=data.get("income_per_week_best"),
        income_per_week_worst=data.get("income_per_week_worst"),
        housekeeping_per_week=data.get("housekeeping_per_week"),
        management_fee_pct=data.get("management_fee_pct"),
        capital_cost_rate_pct=data.get("capital_cost_rate_pct"),
        status=data.get("status", "prospective"),
        notes=data.get("notes"),
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


def update_property(db: Session, property_id: int, data: Dict[str, Any]) -> Optional[AirbnbProperty]:
    """Update property fields."""
    prop = db.query(AirbnbProperty).filter(AirbnbProperty.id == property_id).first()
    if not prop:
        return None

    for field in [
        "name", "property_type", "points_per_week",
        "income_per_week_best", "income_per_week_worst",
        "housekeeping_per_week", "management_fee_pct",
        "capital_cost_rate_pct", "status", "notes",
    ]:
        if field in data:
            setattr(prop, field, data[field])

    db.commit()
    db.refresh(prop)
    return prop


def delete_property(db: Session, property_id: int) -> bool:
    """Delete property and all related data (cascade)."""
    prop = db.query(AirbnbProperty).filter(AirbnbProperty.id == property_id).first()
    if not prop:
        return False

    # Delete document files
    for doc in prop.documents:
        _delete_document_file(doc)

    db.delete(prop)
    db.commit()
    return True


# ── CRUD: Points Blocks ──────────────────────────────────────

def create_block(db: Session, property_id: int, data: Dict[str, Any]) -> Optional[AirbnbPointsBlock]:
    """Add a points block to a property."""
    prop = db.query(AirbnbProperty).filter(AirbnbProperty.id == property_id).first()
    if not prop:
        return None

    block = AirbnbPointsBlock(
        property_id=property_id,
        block_type=data["block_type"],
        points=data["points"],
        cost_to_acquire=data.get("cost_to_acquire", 0),
        annual_cost_rate_pct=data.get("annual_cost_rate_pct"),
        housekeeping_per_week=data.get("housekeeping_per_week"),
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


def update_block(db: Session, block_id: int, data: Dict[str, Any]) -> Optional[AirbnbPointsBlock]:
    """Update a points block."""
    block = db.query(AirbnbPointsBlock).filter(AirbnbPointsBlock.id == block_id).first()
    if not block:
        return None

    for field in ["block_type", "points", "cost_to_acquire", "annual_cost_rate_pct", "housekeeping_per_week"]:
        if field in data:
            setattr(block, field, data[field])

    db.commit()
    db.refresh(block)
    return block


def delete_block(db: Session, block_id: int) -> bool:
    """Delete a points block."""
    block = db.query(AirbnbPointsBlock).filter(AirbnbPointsBlock.id == block_id).first()
    if not block:
        return False
    db.delete(block)
    db.commit()
    return True


# ── Documents ─────────────────────────────────────────────────

def _ensure_airbnb_doc_dir(property_id: int) -> Path:
    """Ensure directory for airbnb documents exists."""
    dir_path = settings.AIRBNB_DOCUMENTS_DIR / str(property_id)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def _compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal."""
    filename = os.path.basename(filename)
    for char in ['/', '\\', '..', '<', '>', ':', '"', '|', '?', '*']:
        filename = filename.replace(char, '_')
    return filename


def _delete_document_file(doc: AirbnbDocument):
    """Delete the physical file for a document."""
    try:
        file_path = settings.BASE_DIR / doc.file_path
        if file_path.exists():
            file_path.unlink()
    except Exception:
        pass


async def upload_document(
    db: Session,
    property_id: int,
    file: UploadFile,
    document_type: str,
    notes: Optional[str] = None,
) -> Optional[AirbnbDocument]:
    """Upload a document for a property."""
    prop = db.query(AirbnbProperty).filter(AirbnbProperty.id == property_id).first()
    if not prop:
        return None

    dir_path = _ensure_airbnb_doc_dir(property_id)

    original_filename = _sanitize_filename(file.filename or "document")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_ext = Path(original_filename).suffix or ".pdf"
    base_name = Path(original_filename).stem
    new_filename = f"{base_name}_{timestamp}{file_ext}"
    file_path = dir_path / new_filename

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    file_hash = _compute_file_hash(file_path)

    # Check for duplicate
    existing = db.query(AirbnbDocument).filter(
        AirbnbDocument.property_id == property_id,
        AirbnbDocument.file_hash == file_hash,
    ).first()
    if existing:
        file_path.unlink(missing_ok=True)
        raise ValueError(f"Duplicate document. Already uploaded as '{existing.file_name}'")

    doc = AirbnbDocument(
        property_id=property_id,
        document_type=document_type,
        file_name=original_filename,
        file_path=str(file_path.relative_to(settings.BASE_DIR)),
        file_hash=file_hash,
        file_size=len(content),
        mime_type=file.content_type,
        notes=notes,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def upload_document_from_path(
    db: Session,
    property_id: int,
    source_path: Path,
    document_type: str,
    notes: Optional[str] = None,
) -> Optional[AirbnbDocument]:
    """Upload a document from a local file path (not HTTP upload)."""
    prop = db.query(AirbnbProperty).filter(AirbnbProperty.id == property_id).first()
    if not prop:
        return None

    if not source_path.exists():
        raise ValueError(f"File not found: {source_path}")

    dir_path = _ensure_airbnb_doc_dir(property_id)

    original_filename = _sanitize_filename(source_path.name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_ext = source_path.suffix or ".pdf"
    base_name = source_path.stem
    new_filename = f"{base_name}_{timestamp}{file_ext}"
    dest_path = dir_path / new_filename

    # Copy file
    import shutil
    shutil.copy2(str(source_path), str(dest_path))

    file_hash = _compute_file_hash(dest_path)
    file_size = dest_path.stat().st_size

    # Check for duplicate
    existing = db.query(AirbnbDocument).filter(
        AirbnbDocument.property_id == property_id,
        AirbnbDocument.file_hash == file_hash,
    ).first()
    if existing:
        dest_path.unlink(missing_ok=True)
        raise ValueError(f"Duplicate document. Already uploaded as '{existing.file_name}'")

    # Guess mime type
    import mimetypes
    mime_type, _ = mimetypes.guess_type(str(dest_path))

    doc = AirbnbDocument(
        property_id=property_id,
        document_type=document_type,
        file_name=original_filename,
        file_path=str(dest_path.relative_to(settings.BASE_DIR)),
        file_hash=file_hash,
        file_size=file_size,
        mime_type=mime_type or "application/octet-stream",
        notes=notes,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def get_document_path(db: Session, doc_id: int) -> Optional[Path]:
    """Get the full file path for a document."""
    doc = db.query(AirbnbDocument).filter(AirbnbDocument.id == doc_id).first()
    if not doc:
        return None
    return settings.BASE_DIR / doc.file_path


def delete_document(db: Session, doc_id: int) -> bool:
    """Delete a document and its file."""
    doc = db.query(AirbnbDocument).filter(AirbnbDocument.id == doc_id).first()
    if not doc:
        return False
    _delete_document_file(doc)
    db.delete(doc)
    db.commit()
    return True


# ── Links ─────────────────────────────────────────────────────

def create_link(db: Session, property_id: int, data: Dict[str, Any]) -> Optional[AirbnbLink]:
    """Add a link to a property."""
    prop = db.query(AirbnbProperty).filter(AirbnbProperty.id == property_id).first()
    if not prop:
        return None

    link = AirbnbLink(
        property_id=property_id,
        title=data["title"],
        url=data["url"],
        link_type=data.get("link_type"),
        notes=data.get("notes"),
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def delete_link(db: Session, link_id: int) -> bool:
    """Delete a link."""
    link = db.query(AirbnbLink).filter(AirbnbLink.id == link_id).first()
    if not link:
        return False
    db.delete(link)
    db.commit()
    return True
