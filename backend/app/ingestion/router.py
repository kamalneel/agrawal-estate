"""
Data Ingestion API routes.
Handles file scanning, processing, and import status.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pathlib import Path
import shutil
import logging

from app.core.database import get_db
from app.core.config import settings
from app.ingestion.services import save_records, create_ingestion_log, complete_ingestion_log
import hashlib

logger = logging.getLogger(__name__)


def _compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of file contents for tracking."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def _get_module_from_folder(folder_path: Path) -> str:
    """Determine module name from folder path."""
    folder_str = str(folder_path).lower()
    if "spending" in folder_str or "monarch" in folder_str:
        return "spending"
    elif "investment" in folder_str or "robinhood" in folder_str or "schwab" in folder_str or "fidelity" in folder_str:
        return "investments"
    elif "cash" in folder_str or "chase" in folder_str or "bank" in folder_str:
        return "cash"
    elif "income" in folder_str or "salary" in folder_str:
        return "income"
    elif "tax" in folder_str:
        return "tax"
    return "other"

router = APIRouter()


def get_all_parsers():
    """Get all available parsers."""
    from app.ingestion.parsers.robinhood import RobinhoodParser
    from app.ingestion.parsers.robinhood_pdf import RobinhoodPDFParser
    from app.ingestion.parsers.robinhood_1099 import Robinhood1099Parser
    from app.ingestion.parsers.fidelity_csv import FidelityCSVParser
    from app.ingestion.parsers.schwab_pdf import SchwabPDFParser
    from app.ingestion.parsers.chase import ChaseParser
    from app.ingestion.parsers.monarch import MonarchParser

    return [
        # 1099 parser must come before RobinhoodParser — both handle .csv but
        # 1099 files start with "1099-" which is a distinctive signal checked first.
        Robinhood1099Parser(),
        RobinhoodPDFParser(),
        RobinhoodParser(),
        FidelityCSVParser(),
        SchwabPDFParser(),
        ChaseParser(),
        MonarchParser(),
    ]


@router.post("/scan")
def trigger_inbox_scan(db: Session = Depends(get_db)):
    """
    Trigger a scan of all inbox folders.
    Processes any new files found.
    Creates ingestion logs for tracking and debugging.
    """
    parsers = get_all_parsers()
    
    # Define inbox folders to scan
    inbox_folders = [
        settings.INBOX_DIR / "investments" / "robinhood",
        settings.INBOX_DIR / "investments" / "schwab",
        settings.INBOX_DIR / "investments" / "fidelity",
        settings.INBOX_DIR / "investments" / "other",
        settings.INBOX_DIR / "cash" / "chase",
        settings.INBOX_DIR / "cash" / "bank_of_america",
        settings.INBOX_DIR / "spending" / "monarch",
    ]
    
    folders_scanned = []
    files_found = 0
    files_processed = 0
    files_failed = 0
    results = []
    
    for folder in inbox_folders:
        if not folder.exists():
            continue
            
        folders_scanned.append(str(folder))
        module = _get_module_from_folder(folder)
        
        # Get all files (not hidden, not directories)
        files = [f for f in folder.iterdir() if f.is_file() and not f.name.startswith('.')]
        files_found += len(files)
        
        for file_path in files:
            # Try each parser
            parsed = False
            ingestion_log = None
            
            for parser in parsers:
                try:
                    if parser.can_parse(file_path):
                        # ============================================================
                        # IDEMPOTENCY CHECK - Prevent duplicate processing
                        # ============================================================
                        file_hash = _compute_file_hash(file_path)
                        
                        from app.shared.models.ingestion import IngestionLog as IngestionLogModel
                        existing_successful = db.query(IngestionLogModel).filter(
                            IngestionLogModel.file_hash == file_hash,
                            IngestionLogModel.status == "success"
                        ).first()
                        
                        if existing_successful:
                            logger.info(
                                f"Skipping {file_path.name}: identical content already processed "
                                f"as '{existing_successful.file_name}' (ingestion_id={existing_successful.id})"
                            )
                            processed_dir = settings.PROCESSED_DIR / folder.relative_to(settings.INBOX_DIR)
                            processed_dir.mkdir(parents=True, exist_ok=True)
                            dest_path = processed_dir / file_path.name
                            if dest_path.exists():
                                from datetime import datetime
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                dest_path = processed_dir / f"{file_path.stem}_{timestamp}{file_path.suffix}"
                            shutil.move(str(file_path), str(dest_path))
                            results.append({
                                "file": file_path.name,
                                "parser": parser.source_name,
                                "status": "skipped_duplicate",
                                "original_ingestion_id": existing_successful.id,
                            })
                            parsed = True
                            break
                        
                        ingestion_log = create_ingestion_log(
                            db=db,
                            file_name=file_path.name,
                            file_path=str(file_path),
                            source=parser.source_name,
                            module=module,
                        )
                        ingestion_log.file_hash = file_hash
                        db.flush()
                        
                        result = parser.parse(file_path)
                        ingestion_log.records_in_file = len(result.records) if result.records else 0
                        
                        if result.success and result.records:
                            # ============================================================
                            # FINANCIAL SYSTEM TRANSACTION HANDLING
                            # ============================================================
                            log_id = ingestion_log.id
                            
                            save_result = save_records(db, result.records, log_id)
                            expected_created = save_result.get("created", 0)
                            expected_updated = save_result.get("updated", 0)
                            expected_skipped = save_result.get("skipped", 0)
                            
                            complete_ingestion_log(
                                db=db,
                                log=ingestion_log,
                                status="success",
                                records_created=expected_created,
                                records_updated=expected_updated,
                                records_skipped=expected_skipped,
                            )
                            
                            try:
                                db.commit()
                            except Exception as commit_error:
                                db.rollback()
                                raise RuntimeError(f"Database commit failed: {commit_error}")
                            
                            # VERIFICATION - Confirm data persisted
                            from app.core.database import SessionLocal
                            verification_session = SessionLocal()
                            try:
                                verified_log = verification_session.query(IngestionLogModel).filter(
                                    IngestionLogModel.id == log_id
                                ).first()
                                
                                if not verified_log:
                                    raise RuntimeError(
                                        f"VERIFICATION FAILED: Ingestion log {log_id} not found after commit."
                                    )
                                
                                verified_created = verified_log.records_created or 0
                                verified_updated = verified_log.records_updated or 0
                            finally:
                                verification_session.close()
                            
                            # Move file ONLY after verification
                            processed_dir = settings.PROCESSED_DIR / folder.relative_to(settings.INBOX_DIR)
                            processed_dir.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(file_path), str(processed_dir / file_path.name))
                            
                            files_processed += 1
                            results.append({
                                "file": file_path.name,
                                "parser": parser.source_name,
                                "status": "success",
                                "ingestion_id": log_id,
                                "records": {
                                    "created": verified_created,
                                    "updated": verified_updated,
                                    "skipped": expected_skipped
                                }
                            })
                            logger.info(f"Processed {file_path.name}: created={verified_created}, skipped={expected_skipped}")
                            parsed = True
                            break
                        elif result.errors:
                            # Log parsing errors
                            error_msg = "; ".join(result.errors[:5])  # First 5 errors
                            complete_ingestion_log(
                                db=db,
                                log=ingestion_log,
                                status="failed",
                                error_message=error_msg,
                            )
                            db.commit()
                            
                            results.append({
                                "file": file_path.name,
                                "parser": parser.source_name,
                                "status": "error",
                                "ingestion_id": ingestion_log.id,
                                "errors": result.errors
                            })
                            logger.warning(f"Parse errors for {file_path.name}: {error_msg}")
                except Exception as e:
                    # Log exception
                    error_msg = str(e)
                    if ingestion_log:
                        complete_ingestion_log(
                            db=db,
                            log=ingestion_log,
                            status="failed",
                            error_message=error_msg,
                        )
                        db.commit()
                    
                    results.append({
                        "file": file_path.name,
                        "parser": parser.source_name if parser else "unknown",
                        "status": "exception",
                        "error": error_msg
                    })
                    logger.error(f"Exception processing {file_path.name}: {error_msg}")
            
            if not parsed:
                files_failed += 1
    
    return {
        "status": "scan_complete",
        "folders_scanned": folders_scanned,
        "files_found": files_found,
        "files_processed": files_processed,
        "files_failed": files_failed,
        "results": results
    }


@router.get("/status")
async def get_ingestion_status(db: Session = Depends(get_db)):
    """Get current ingestion processing status."""
    return {
        "is_processing": False,
        "current_file": None,
        "queue_size": 0
    }


@router.post("/refresh-now")
def trigger_refresh_now():
    """Kick the scheduled MCP refresh job (com.neelpersonal.rh-refresh)
    on demand — same full sync the 5:40/11:40/19:40 slots run, takes
    ~5-6 minutes. launchctl start is a no-op if the job is already
    running, so double-clicks are harmless. The freshness endpoint's
    timestamps advancing is the completion signal."""
    import subprocess
    try:
        result = subprocess.run(
            ["launchctl", "start", "com.neelpersonal.rh-refresh"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise HTTPException(status_code=502,
                                detail=f"launchctl failed: {result.stderr.strip() or result.returncode}")
        return {"started": True, "expected_duration_min": 6}
    except FileNotFoundError:
        raise HTTPException(status_code=502, detail="launchctl not available on this host")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="launchctl timed out")


@router.get("/freshness")
def get_data_freshness(db: Session = Depends(get_db)):
    """Data-freshness summary for the header indicator.

    The scheduled MCP refresh (launchd com.neelpersonal.rh-refresh) runs
    weekdays at 5:40 / 11:40 / 19:40 PT. Freshness = did the newest data
    land at-or-after the most recent scheduled slot (15 min grace). The
    overall timestamp is the WEAKEST source (min), so one silently-failing
    feed can't hide behind the others.
    """
    from sqlalchemy import text as _text
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    PT = ZoneInfo("America/Los_Angeles")

    def _scalar(sql: str):
        row = db.execute(_text(sql)).fetchone()
        return row[0] if row and row[0] else None

    # DB timestamps are naive UTC (Postgres now() on this box is UTC)
    sources = {
        "holdings": _scalar("SELECT MAX(updated_at) FROM investment_holdings"),
        "options": _scalar("SELECT MAX(snapshot_date) FROM sold_options_snapshots"),
        "cash": _scalar("SELECT MAX(updated_at) FROM account_cash_balances"),
        "activity": _scalar("SELECT MAX(created_at) FROM ingestion_log WHERE status = 'success'"),
    }

    # Most recent scheduled refresh slot: weekdays 6:32/7:40/11:40/13:10 PT
    # (Neel's decision-point schedule, 2026-07-14 — post-open, coffee,
    # pre-close decision, post-close capture), walked back from now, then
    # converted to naive UTC for comparison.
    now_pt = datetime.now(PT)
    slot_times = [(6, 32), (7, 40), (11, 40), (13, 10)]
    day = now_pt.date()
    last_expected_pt = None
    for _ in range(8):  # never more than a weekend + holiday of walking back
        if day.weekday() < 5:  # Mon-Fri
            for hh, mm in reversed(slot_times):
                candidate = datetime(day.year, day.month, day.day, hh, mm, tzinfo=PT)
                if candidate <= now_pt:
                    last_expected_pt = candidate
                    break
        if last_expected_pt:
            break
        day = day - timedelta(days=1)

    last_expected_utc = (last_expected_pt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
                         if last_expected_pt else None)
    now_utc = datetime.now(ZoneInfo("UTC")).replace(tzinfo=None)

    grace = timedelta(minutes=15)
    # weakest core source (activity excluded: it only advances when new
    # fills exist, so a quiet market day would false-alarm)
    core = [v for k, v in sources.items() if k != "activity" and v is not None]
    overall = min(core) if core else None
    fresh = bool(overall and last_expected_utc and overall >= last_expected_utc - grace)

    def _iso_utc(v):
        return (v.isoformat() + "Z") if v else None  # mark as UTC for JS Date()

    return {
        "sources": {k: _iso_utc(v) for k, v in sources.items()},
        "overall": _iso_utc(overall),
        "last_expected_run": _iso_utc(last_expected_utc),
        "status": "fresh" if fresh else "stale",
        "hours_since": round((now_utc - overall).total_seconds() / 3600, 1) if overall else None,
        "schedule": "weekdays 6:32 / 7:40 / 11:40 / 13:10 PT (post-close capture at 13:10 is final for the day)",
    }


@router.get("/history")
async def get_ingestion_history(
    db: Session = Depends(get_db),
    module: Optional[str] = None,
    source: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50
):
    """
    Get history of file ingestions.
    Filter by module (investments, tax, etc.), source (robinhood, schwab, etc.), or status.
    """
    from app.shared.models.ingestion import IngestionLog
    
    query = db.query(IngestionLog)
    
    if module:
        query = query.filter(IngestionLog.module == module)
    if source:
        query = query.filter(IngestionLog.source == source)
    if status:
        query = query.filter(IngestionLog.status == status)
    
    # Get total count before limit
    total = query.count()
    
    # Get results ordered by most recent first
    logs = query.order_by(IngestionLog.started_at.desc()).limit(limit).all()
    
    ingestions = []
    for log in logs:
        ingestions.append({
            "id": log.id,
            "file_name": log.file_name,
            "file_path": log.file_path,
            "file_hash": log.file_hash,
            "source": log.source,
            "module": log.module,
            "status": log.status,
            "records_in_file": log.records_in_file,
            "records_created": log.records_created,
            "records_updated": log.records_updated,
            "records_skipped": log.records_skipped,
            "error_message": log.error_message,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "completed_at": log.completed_at.isoformat() if log.completed_at else None,
        })
    
    return {
        "ingestions": ingestions,
        "total": total
    }


@router.get("/history/{ingestion_id}")
async def get_ingestion_details(ingestion_id: int, db: Session = Depends(get_db)):
    """Get detailed results for a specific ingestion."""
    from app.shared.models.ingestion import IngestionLog
    
    log = db.query(IngestionLog).filter(IngestionLog.id == ingestion_id).first()
    
    if not log:
        raise HTTPException(status_code=404, detail=f"Ingestion {ingestion_id} not found")
    
    return {
        "ingestion": {
            "id": log.id,
            "file_name": log.file_name,
            "file_path": log.file_path,
            "file_hash": log.file_hash,
            "source": log.source,
            "module": log.module,
            "status": log.status,
            "records_in_file": log.records_in_file,
            "records_created": log.records_created,
            "records_updated": log.records_updated,
            "records_skipped": log.records_skipped,
            "error_message": log.error_message,
            "warnings": log.warnings,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "completed_at": log.completed_at.isoformat() if log.completed_at else None,
        },
        "errors": [log.error_message] if log.error_message else []
    }


@router.post("/retry/{ingestion_id}")
async def retry_failed_ingestion(ingestion_id: int, db: Session = Depends(get_db)):
    """Retry a previously failed file ingestion."""
    return {"status": "retry_initiated", "ingestion_id": ingestion_id}


@router.get("/preview")
async def preview_file(file_path: str, db: Session = Depends(get_db)):
    """
    Preview what a file contains before processing.
    Returns parsed data without committing to database.
    """
    return {
        "file_path": file_path,
        "detected_source": None,
        "detected_type": None,
        "record_count": 0,
        "sample_records": [],
        "warnings": []
    }


@router.delete("/failed/{ingestion_id}")
async def dismiss_failed_ingestion(ingestion_id: int, db: Session = Depends(get_db)):
    """Dismiss/acknowledge a failed ingestion."""
    return {"status": "dismissed", "ingestion_id": ingestion_id}


@router.post("/process-all")
def process_all_inbox_files(db: Session = Depends(get_db)):
    """
    Process all files in all inbox folders.
    Returns result in format expected by frontend.
    Creates ingestion logs for each file for tracking and debugging.
    """
    parsers = get_all_parsers()
    
    # Define inbox folders to scan
    inbox_folders = [
        ("investments/robinhood", settings.INBOX_DIR / "investments" / "robinhood"),
        ("investments/schwab", settings.INBOX_DIR / "investments" / "schwab"),
        ("investments/fidelity", settings.INBOX_DIR / "investments" / "fidelity"),
        ("investments/other", settings.INBOX_DIR / "investments" / "other"),
        ("cash/chase", settings.INBOX_DIR / "cash" / "chase"),
        ("cash/bank_of_america", settings.INBOX_DIR / "cash" / "bank_of_america"),
        ("income/salary", settings.INBOX_DIR / "income" / "salary"),
        ("tax/returns", settings.INBOX_DIR / "tax" / "returns"),
        ("spending/monarch", settings.INBOX_DIR / "spending" / "monarch"),
    ]
    
    files_processed = 0
    records_imported = 0
    errors = []
    details = []
    ingestion_ids = []
    
    for folder_name, folder_path in inbox_folders:
        if not folder_path.exists():
            continue
        
        module = _get_module_from_folder(folder_path)
        
        # Get all files (not hidden, not directories)
        files = [f for f in folder_path.iterdir() if f.is_file() and not f.name.startswith('.')]
        
        if not files:
            continue
        
        folder_files = []
        folder_records = 0
        
        for file_path in files:
            # Try each parser
            parsed = False
            ingestion_log = None
            
            for parser in parsers:
                try:
                    if parser.can_parse(file_path):
                        # ============================================================
                        # IDEMPOTENCY CHECK - Prevent duplicate processing
                        # ============================================================
                        # Compute file hash FIRST to check if we've already processed
                        # this exact file content (even under a different name)
                        file_hash = _compute_file_hash(file_path)
                        
                        # Check if this file content was already successfully processed
                        from app.shared.models.ingestion import IngestionLog as IngestionLogModel
                        existing_successful = db.query(IngestionLogModel).filter(
                            IngestionLogModel.file_hash == file_hash,
                            IngestionLogModel.status == "success"
                        ).first()
                        
                        if existing_successful:
                            # File content already processed - move to processed and skip
                            logger.info(
                                f"Skipping {file_path.name}: identical content already processed "
                                f"as '{existing_successful.file_name}' (ingestion_id={existing_successful.id})"
                            )
                            processed_dir = settings.PROCESSED_DIR / folder_path.relative_to(settings.INBOX_DIR)
                            processed_dir.mkdir(parents=True, exist_ok=True)
                            
                            # Handle duplicate filename in processed folder
                            dest_path = processed_dir / file_path.name
                            if dest_path.exists():
                                # Add timestamp to avoid overwriting
                                from datetime import datetime
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                dest_path = processed_dir / f"{file_path.stem}_{timestamp}{file_path.suffix}"
                            
                            shutil.move(str(file_path), str(dest_path))
                            parsed = True
                            break
                        
                        # Create ingestion log for new file content
                        ingestion_log = create_ingestion_log(
                            db=db,
                            file_name=file_path.name,
                            file_path=str(file_path),
                            source=parser.source_name,
                            module=module,
                        )
                        ingestion_log.file_hash = file_hash
                        db.flush()
                        
                        result = parser.parse(file_path)
                        ingestion_log.records_in_file = len(result.records) if result.records else 0
                        
                        if result.success and result.records:
                            # ============================================================
                            # FINANCIAL SYSTEM TRANSACTION HANDLING
                            # ============================================================
                            # This follows banking-grade transaction principles:
                            # 1. Execute within explicit transaction
                            # 2. Commit and verify data was persisted
                            # 3. Only perform side-effects after verification
                            # 4. Fail-safe: if uncertain, report failure
                            # ============================================================
                            
                            # Store the log ID before commit for verification
                            log_id = ingestion_log.id
                            
                            # Phase 1: Save records to database with ingestion_id for provenance
                            save_result = save_records(db, result.records, log_id)
                            expected_created = save_result.get("created", 0)
                            expected_updated = save_result.get("updated", 0)
                            expected_skipped = save_result.get("skipped", 0)
                            
                            # Phase 2: Update ingestion log with results
                            complete_ingestion_log(
                                db=db,
                                log=ingestion_log,
                                status="success",
                                records_created=expected_created,
                                records_updated=expected_updated,
                                records_skipped=expected_skipped,
                            )
                            
                            # Phase 3: Commit using EXPLICIT new connection to bypass potential session issues
                            # This is a workaround for possible FastAPI session management issues
                            from app.core.database import SessionLocal, engine
                            from app.shared.models.ingestion import IngestionLog as IngestionLogModel
                            from app.modules.investments.models import InvestmentTransaction
                            from sqlalchemy import text
                            
                            logger.info(f"Ingestion {log_id}: About to commit. Pending changes: new={len(db.new)}, dirty={len(db.dirty)}")
                            
                            try:
                                # Commit the current session
                                db.commit()
                                logger.info(f"Ingestion {log_id}: Commit returned successfully")
                            except Exception as commit_error:
                                logger.error(f"Ingestion {log_id}: Commit FAILED with exception: {commit_error}")
                                import traceback
                                logger.error(traceback.format_exc())
                                db.rollback()
                                raise RuntimeError(f"Database commit failed: {commit_error}")
                            
                            # Phase 4: VERIFICATION using raw PostgreSQL connection
                            logger.info(f"Ingestion {log_id}: Verifying with raw PostgreSQL connection...")
                            
                            import psycopg2
                            pg_conn = psycopg2.connect(
                                host='localhost',
                                port=5432,
                                database='agrawal_estate',
                                user='agrawal_user',
                                password='agrawal_secure_2024'
                            )
                            pg_cur = pg_conn.cursor()
                            
                            try:
                                pg_cur.execute(f"SELECT id, file_name, status, records_created FROM ingestion_log WHERE id = {log_id}")
                                raw_result = pg_cur.fetchone()
                                logger.info(f"Ingestion {log_id}: Raw PostgreSQL query result: {raw_result}")
                                
                                if not raw_result:
                                    # Data not in PostgreSQL - this is a serious issue
                                    # Let's also check what the max ID is
                                    pg_cur.execute("SELECT MAX(id) FROM ingestion_log")
                                    max_id = pg_cur.fetchone()[0]
                                    pg_cur.execute("SELECT last_value FROM ingestion_log_id_seq")
                                    seq_val = pg_cur.fetchone()[0]
                                    logger.error(f"Ingestion {log_id}: NOT FOUND. Max ID: {max_id}, Sequence: {seq_val}")
                                    
                                    raise RuntimeError(
                                        f"VERIFICATION FAILED: Ingestion log {log_id} not found after commit. "
                                        f"Max ID in table: {max_id}, Sequence: {seq_val}. "
                                        f"Database transaction may have been rolled back silently. "
                                        f"File NOT moved to processed."
                                    )
                                
                                verified_created = raw_result[3] or 0
                                verified_updated = 0  # We don't track this separately in raw query
                                logger.info(f"Ingestion {log_id}: VERIFIED! records_created={verified_created}")
                                
                            finally:
                                pg_cur.close()
                                pg_conn.close()
                            
                            # Phase 5: Side-effects ONLY after verification passes
                            # Move file to processed folder
                            processed_dir = settings.PROCESSED_DIR / folder_path.relative_to(settings.INBOX_DIR)
                            processed_dir.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(file_path), str(processed_dir / file_path.name))
                            
                            # Use VERIFIED counts in the response
                            files_processed += 1
                            folder_files.append(file_path.name)
                            folder_records += verified_created + verified_updated
                            records_imported += verified_created + verified_updated
                            ingestion_ids.append(log_id)
                            
                            logger.info(
                                f"Processed {file_path.name} (ingestion_id={ingestion_log.id}): "
                                f"created={save_result.get('created', 0)}, "
                                f"updated={save_result.get('updated', 0)}, "
                                f"skipped={save_result.get('skipped', 0)}"
                            )
                            parsed = True
                            break
                        elif result.success and not result.records:
                            # Successfully parsed but no records (e.g. Robinhood "no activity" file)
                            complete_ingestion_log(
                                db=db,
                                log=ingestion_log,
                                status="success",
                                records_created=0,
                                records_updated=0,
                                records_skipped=0,
                            )
                            db.commit()
                            # Move file to processed so it doesn't re-appear
                            processed_dir = settings.PROCESSED_DIR / folder_path.relative_to(settings.INBOX_DIR)
                            processed_dir.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(file_path), str(processed_dir / file_path.name))
                            files_processed += 1
                            folder_files.append(file_path.name)
                            ingestion_ids.append(ingestion_log.id)
                            if result.warnings:
                                errors.extend([f"{file_path.name}: {w}" for w in result.warnings])
                            logger.info(f"Processed {file_path.name} with 0 records (no activity)")
                            parsed = True
                            break
                        elif result.errors:
                            # Log parsing errors
                            error_msg = "; ".join(result.errors[:5])
                            complete_ingestion_log(
                                db=db,
                                log=ingestion_log,
                                status="failed",
                                error_message=error_msg,
                            )
                            db.commit()
                            
                            errors.extend([f"{file_path.name}: {e}" for e in result.errors])
                            ingestion_ids.append(ingestion_log.id)
                            logger.warning(f"Parse errors for {file_path.name}: {error_msg}")
                except Exception as e:
                    error_msg = str(e)
                    if ingestion_log:
                        complete_ingestion_log(
                            db=db,
                            log=ingestion_log,
                            status="failed",
                            error_message=error_msg,
                        )
                        try:
                            db.commit()
                        except Exception:
                            db.rollback()
                        ingestion_ids.append(ingestion_log.id)
                    
                    errors.append(f"{file_path.name}: {error_msg}")
                    logger.error(f"Exception processing {file_path.name}: {error_msg}", exc_info=True)
            
            if not parsed and not any(file_path.name in e for e in errors):
                errors.append(f"{file_path.name}: No compatible parser found")
        
        if folder_files:
            details.append({
                "folder": folder_name,
                "files": folder_files,
                "records": folder_records
            })
    
    return {
        "success": True,
        "files_processed": files_processed,
        "records_imported": records_imported,
        "errors": errors,
        "details": details,
        "ingestion_ids": ingestion_ids
    }


@router.get("/test-db-commit")
def test_db_commit(db: Session = Depends(get_db)):
    """
    Test endpoint to diagnose database commit issues.
    Creates a test ingestion log, commits, and verifies.
    """
    from app.shared.models.ingestion import IngestionLog
    from datetime import datetime
    import psycopg2
    
    # Create test log
    test_log = IngestionLog(
        file_name=f'TEST_COMMIT_{datetime.now().isoformat()}.csv',
        file_path='/tmp/test',
        source='test',
        module='test',
        status='pending',
        started_at=datetime.now()
    )
    
    db.add(test_log)
    db.flush()
    log_id = test_log.id
    
    logger.info(f"Test: Created log {log_id}, about to commit...")
    
    try:
        db.commit()
        logger.info(f"Test: Commit returned for log {log_id}")
    except Exception as e:
        logger.error(f"Test: Commit failed: {e}")
        return {"success": False, "error": str(e), "log_id": log_id}
    
    # Verify with raw PostgreSQL
    pg_conn = psycopg2.connect(
        host='localhost',
        port=5432,
        database='agrawal_estate',
        user='agrawal_user',
        password='agrawal_secure_2024'
    )
    pg_cur = pg_conn.cursor()
    
    try:
        pg_cur.execute(f"SELECT id, file_name FROM ingestion_log WHERE id = {log_id}")
        result = pg_cur.fetchone()
        
        if result:
            # Clean up test data
            pg_cur.execute(f"DELETE FROM ingestion_log WHERE id = {log_id}")
            pg_conn.commit()
            return {
                "success": True,
                "log_id": log_id,
                "verified": True,
                "file_name": result[1],
                "message": "Database commit and verification working correctly!"
            }
        else:
            pg_cur.execute("SELECT MAX(id), last_value FROM ingestion_log, ingestion_log_id_seq")
            max_seq = pg_cur.fetchone()
            return {
                "success": False,
                "log_id": log_id,
                "verified": False,
                "max_id": max_seq[0] if max_seq else None,
                "sequence": max_seq[1] if max_seq else None,
                "message": "COMMIT FAILED - data not found after commit!"
            }
    finally:
        pg_cur.close()
        pg_conn.close()


@router.get("/imported-transactions")
def get_imported_transactions(
    ingestion_ids: str,
    db: Session = Depends(get_db),
):
    """
    Fetch newly imported transactions by ingestion IDs.
    Returns only records created during those ingestions (not skipped duplicates).
    Also returns a files mapping (ingestion_id → file_name) for per-file summaries.
    """
    from app.modules.investments.models import InvestmentTransaction
    from app.shared.models.ingestion import IngestionLog

    try:
        id_list = [int(x.strip()) for x in ingestion_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="ingestion_ids must be comma-separated integers")

    if not id_list:
        return {"transactions": [], "files": {}}

    logs = db.query(IngestionLog).filter(IngestionLog.id.in_(id_list)).all()
    files = {str(log.id): log.file_name for log in logs}

    rows = (
        db.query(InvestmentTransaction)
        .filter(InvestmentTransaction.ingestion_id.in_(id_list))
        .order_by(InvestmentTransaction.transaction_date.desc())
        .all()
    )

    transactions = []
    for r in rows:
        transactions.append({
            "ingestion_id": r.ingestion_id,
            "symbol": r.symbol,
            "transaction_date": r.transaction_date.isoformat() if r.transaction_date else None,
            "amount": float(r.amount) if r.amount is not None else 0,
            "transaction_type": r.transaction_type,
            "description": r.description,
        })

    return {"transactions": transactions, "files": files}


@router.get("/inbox-status")
def get_inbox_status():
    """Get status of all inbox folders."""
    inbox_folders = [
        ("investments/robinhood", settings.INBOX_DIR / "investments" / "robinhood"),
        ("investments/schwab", settings.INBOX_DIR / "investments" / "schwab"),
        ("investments/other", settings.INBOX_DIR / "investments" / "other"),
        ("income/salary", settings.INBOX_DIR / "income" / "salary"),
        ("income/rental", settings.INBOX_DIR / "income" / "rental"),
        ("income/dividends", settings.INBOX_DIR / "income" / "dividends"),
        ("tax/property_tax", settings.INBOX_DIR / "tax" / "property_tax"),
        ("tax/returns", settings.INBOX_DIR / "tax" / "returns"),
        ("real_estate/mortgages", settings.INBOX_DIR / "real_estate" / "mortgages"),
        ("real_estate/valuations", settings.INBOX_DIR / "real_estate" / "valuations"),
        ("estate_planning/documents", settings.INBOX_DIR / "estate_planning" / "documents"),
        ("spending/monarch", settings.INBOX_DIR / "spending" / "monarch"),
    ]
    
    status = []
    for name, path in inbox_folders:
        file_count = 0
        if path.exists():
            # Exclude hidden files like .DS_Store
            file_count = len([f for f in path.iterdir() if f.is_file() and not f.name.startswith('.')])
        status.append({
            "folder": name,
            "path": str(path),
            "pending_files": file_count
        })
    
    return {"folders": status}


# ============================================================================
# ROBINHOOD PASTE IMPORT (Unified Parser)
# ============================================================================

@router.post("/robinhood-paste/preview")
async def preview_robinhood_paste(
    data: dict,
    db: Session = Depends(get_db)
):
    """
    Preview pasted Robinhood data before saving.
    
    Detects format (stocks, options list, options detail, or mixed) and returns
    parsed data for user confirmation.
    """
    from app.ingestion.robinhood_unified_parser import parse_robinhood_data
    
    text = data.get("text", "")
    account_name = data.get("account_name")
    
    if not text.strip():
        raise HTTPException(status_code=400, detail="No text provided")
    
    # Parse the data
    result = parse_robinhood_data(text, account_name)
    
    # Check if empty sections require confirmation
    requires_confirmation = False
    confirmation_message = ""
    
    if result.has_stocks_section and not result.stocks:
        requires_confirmation = True
        if result.has_options_section and not result.options:
            confirmation_message = "You have empty Options and Stocks sections. This will clear ALL options and stocks for this account. Do you want to proceed?"
        else:
            confirmation_message = "You have an empty Stocks section. This will clear ALL stocks for this account. Do you want to proceed?"
    elif result.has_options_section and not result.options:
        requires_confirmation = True
        confirmation_message = "You have an empty Options section. This will clear ALL options for this account. Do you want to proceed?"
    
    return {
        "success": True,
        "detected_format": result.detected_format,
        "stocks_count": len(result.stocks),
        "options_count": len(result.options),
        "pending_orders_count": len(result.pending_orders),
        "has_options_section": result.has_options_section,
        "has_stocks_section": result.has_stocks_section,
        "requires_confirmation": requires_confirmation,
        "confirmation_message": confirmation_message,
        "stocks": [
            {
                "symbol": s.symbol,
                "name": s.name,
                "shares": s.shares,
                "market_value": s.market_value,
                "current_price": s.current_price
            }
            for s in result.stocks
        ],
        "options": [
            {
                "symbol": o.symbol,
                "strike_price": o.strike_price,
                "option_type": o.option_type,
                "expiration_date": o.expiration_date,
                "contracts": o.contracts,
                "current_premium": o.current_premium,
                "original_premium": o.original_premium,
                "gain_loss_percent": o.gain_loss_percent
            }
            for o in result.options
        ],
        "pending_orders": [
            {
                "symbol": p.symbol,
                "order_type": p.order_type,
                "option_type": p.option_type,
                "strike_price": p.strike_price,
                "from_expiration": p.from_expiration,
                "to_expiration": p.to_expiration,
                "contracts": p.contracts,
                "limit_price": p.limit_price
            }
            for p in result.pending_orders
        ],
        "warnings": result.warnings
    }


@router.post("/robinhood-paste/save")
async def save_robinhood_paste(
    data: dict,
    db: Session = Depends(get_db)
):
    """
    Save pasted Robinhood data to database.
    
    Saves:
    - Stock holdings to investment_holdings table
    - Options to sold_options table (via snapshot)
    
    Expects account_name to map to the correct account.
    """
    from app.ingestion.robinhood_unified_parser import (
        parse_robinhood_data, 
        normalize_expiration_date
    )
    from app.modules.investments.models import InvestmentAccount, InvestmentHolding, PortfolioSnapshot
    from app.modules.strategies.models import SoldOptionsSnapshot, SoldOption, PendingOrder
    from decimal import Decimal
    from datetime import datetime, date
    
    text = data.get("text", "")
    account_name = data.get("account_name")
    save_stocks = data.get("save_stocks", True)
    save_options = data.get("save_options", True)
    confirm_empty_sections = data.get("confirm_empty_sections", False)  # User must explicitly confirm
    
    if not text.strip():
        raise HTTPException(status_code=400, detail="No text provided")
    
    if not account_name:
        raise HTTPException(status_code=400, detail="Account name is required")
    
    # Parse the data
    result = parse_robinhood_data(text, account_name)
    
    # Check if confirmation is required for empty sections
    if (result.has_stocks_section and not result.stocks) or (result.has_options_section and not result.options):
        if not confirm_empty_sections:
            raise HTTPException(
                status_code=400, 
                detail="Empty sections detected. Please confirm that you want to clear all data for empty sections."
            )
    
    stocks_saved = 0
    stocks_updated = 0
    options_saved = 0
    pending_orders_saved = 0

    # Detail lists for modal display
    stocks_created_details = []
    stocks_updated_details = []
    stocks_removed_details = []
    options_saved_details = []
    pending_orders_details = []
    
    # Save/update stock holdings
    # Only save/update if we have actual stock data
    # If has_stocks_section is True but stocks is empty, skip saving (don't clear existing data)
    if save_stocks and result.stocks:
        account_id = _normalize_account_id(account_name)
        
        # Ensure account exists
        account = db.query(InvestmentAccount).filter(
            InvestmentAccount.account_id == account_id,
            InvestmentAccount.source == 'robinhood'
        ).first()
        
        if not account:
            _owner, account_type = _parse_account_name(account_name)
            account = InvestmentAccount(
                account_id=account_id,
                account_name=account_name,
                source='robinhood',
                account_type=account_type,
                is_active='Y'
            )
            db.add(account)
            db.flush()
            logger.info(f"Created new account: {account_name} ({account_id})")
        
        # Track symbols in the new data for cleanup
        new_symbols = set()
        
        for stock in result.stocks:
            symbol = stock.symbol.upper()
            new_symbols.add(symbol)
            
            # Validate: market_value should be shares × price
            # If market_value seems wrong, recalculate
            if stock.shares > 0 and stock.current_price > 0:
                expected_value = stock.shares * stock.current_price
                if abs(expected_value - stock.market_value) > 1:  # Allow $1 rounding difference
                    logger.warning(f"{symbol}: market_value ${stock.market_value:.2f} doesn't match shares×price ${expected_value:.2f}, using calculated value")
                    stock.market_value = expected_value
            
            # Additional validation: reject obviously wrong values
            # Price should be between $0.01 and $100,000
            if stock.current_price < 0.01 or stock.current_price > 100000:
                logger.warning(f"{symbol}: Skipping - price ${stock.current_price:.4f} seems invalid")
                continue
            
            # Market value should be reasonable (> $1 for any meaningful holding)
            if stock.shares > 0 and stock.market_value < 1:
                logger.warning(f"{symbol}: Skipping - market_value ${stock.market_value:.2f} seems invalid for {stock.shares} shares")
                continue
            
            # Check if holding exists
            existing = db.query(InvestmentHolding).filter(
                InvestmentHolding.account_id == account_id,
                InvestmentHolding.source == 'robinhood',
                InvestmentHolding.symbol == symbol
            ).first()
            
            if existing:
                # Capture old values before mutation
                old_shares = float(existing.quantity) if existing.quantity else 0
                old_price = float(existing.current_price) if existing.current_price else 0
                old_market_value = float(existing.market_value) if existing.market_value else 0

                # Update existing holding
                existing.quantity = Decimal(str(stock.shares))
                existing.current_price = Decimal(str(round(stock.current_price, 4)))
                existing.market_value = Decimal(str(round(stock.market_value, 2)))
                existing.description = stock.name if stock.name != stock.symbol else existing.description
                existing.last_updated = datetime.utcnow()
                stocks_updated += 1
                stocks_updated_details.append({
                    "symbol": symbol,
                    "shares": stock.shares,
                    "old_shares": old_shares,
                    "price": round(stock.current_price, 4),
                    "old_price": round(old_price, 4),
                    "market_value": round(stock.market_value, 2),
                    "old_market_value": round(old_market_value, 2),
                })
                logger.info(f"Updated {symbol}: {stock.shares} shares @ ${stock.current_price:.2f} = ${stock.market_value:,.2f}")
            else:
                # Create new holding
                holding = InvestmentHolding(
                    account_id=account_id,
                    source='robinhood',
                    symbol=symbol,
                    description=stock.name if stock.name != stock.symbol else None,
                    quantity=Decimal(str(stock.shares)),
                    current_price=Decimal(str(round(stock.current_price, 4))),
                    market_value=Decimal(str(round(stock.market_value, 2))),
                    last_updated=datetime.utcnow()
                )
                db.add(holding)
                stocks_saved += 1
                stocks_created_details.append({
                    "symbol": symbol,
                    "name": stock.name if stock.name != stock.symbol else symbol,
                    "shares": stock.shares,
                    "price": round(stock.current_price, 4),
                    "market_value": round(stock.market_value, 2),
                })
                logger.info(f"Created {symbol}: {stock.shares} shares @ ${stock.current_price:.2f} = ${stock.market_value:,.2f}")
        
        # Remove holdings that are no longer in the account
        # (User sold the stock entirely)
        # Trust the paste as authoritative when a stocks section was detected:
        # if has_stocks_section is True, the paste contains the complete holdings list.
        # The has_stocks_section flag is the correct guard against incomplete pastes.
        if result.has_stocks_section:
            current_holdings = db.query(InvestmentHolding).filter(
                InvestmentHolding.account_id == account_id,
                InvestmentHolding.source == 'robinhood'
            ).all()

            holdings_to_remove = [h for h in current_holdings if h.symbol not in new_symbols]

            for holding in holdings_to_remove:
                stocks_removed_details.append({
                    "symbol": holding.symbol,
                    "shares": float(holding.quantity) if holding.quantity else 0,
                    "last_price": float(holding.current_price) if holding.current_price else 0,
                    "market_value": float(holding.market_value) if holding.market_value else 0,
                })
                logger.info(f"Removing {holding.symbol} from {account_name} - no longer in holdings")
                db.delete(holding)
    elif save_stocks and result.has_stocks_section and not result.stocks:
        # Stocks section header detected but empty - user has cleared all stocks
        account_id = _normalize_account_id(account_name)
        
        # Ensure account exists
        account = db.query(InvestmentAccount).filter(
            InvestmentAccount.account_id == account_id,
            InvestmentAccount.source == 'robinhood'
        ).first()
        
        if not account:
            _owner, account_type = _parse_account_name(account_name)
            account = InvestmentAccount(
                account_id=account_id,
                account_name=account_name,
                source='robinhood',
                account_type=account_type,
                is_active='Y'
            )
            db.add(account)
            db.flush()
            logger.info(f"Created new account: {account_name} ({account_id})")
        
        # Clear all stocks for this account
        current_holdings = db.query(InvestmentHolding).filter(
            InvestmentHolding.account_id == account_id,
            InvestmentHolding.source == 'robinhood'
        ).all()
        
        for holding in current_holdings:
            stocks_removed_details.append({
                "symbol": holding.symbol,
                "shares": float(holding.quantity) if holding.quantity else 0,
                "last_price": float(holding.current_price) if holding.current_price else 0,
                "market_value": float(holding.market_value) if holding.market_value else 0,
            })
            logger.info(f"Removing {holding.symbol} from {account_name} - stocks section is empty (all stocks cleared)")
            db.delete(holding)
    
    # Save options
    # Only save if we have actual options data
    # If has_options_section is True but options is empty, clear all options for this account
    snapshot_id = None
    if save_options and result.options:
        # Create snapshot
        snapshot = SoldOptionsSnapshot(
            source='robinhood',
            account_name=account_name,
            snapshot_date=datetime.utcnow(),
            parsing_status='success',
            raw_extracted_text=text[:5000]  # Limit stored text
        )
        db.add(snapshot)
        db.flush()
        snapshot_id = snapshot.id
        
        for opt in result.options:
            exp_date = normalize_expiration_date(opt.expiration_date) if opt.expiration_date else None
            
            sold_option = SoldOption(
                snapshot_id=snapshot_id,
                symbol=opt.symbol.upper(),
                strike_price=Decimal(str(opt.strike_price)),
                option_type=opt.option_type.lower(),
                expiration_date=exp_date,
                contracts_sold=opt.contracts,
                premium_per_contract=Decimal(str(opt.current_premium)) if opt.current_premium else None,
                original_premium=Decimal(str(opt.original_premium)) if opt.original_premium else None,
                gain_loss_percent=Decimal(str(opt.gain_loss_percent)) if opt.gain_loss_percent else None,
                status="open",
                raw_text=opt.raw_text[:500] if opt.raw_text else None
            )
            db.add(sold_option)
            options_saved += 1
            options_saved_details.append({
                "symbol": opt.symbol.upper(),
                "strike_price": float(opt.strike_price),
                "option_type": opt.option_type,
                "expiration_date": str(exp_date) if exp_date else None,
                "contracts": opt.contracts,
            })

        # Save pending orders to the same snapshot
        for po in result.pending_orders:
            from_exp = normalize_expiration_date(po.from_expiration) if po.from_expiration else None
            to_exp = normalize_expiration_date(po.to_expiration) if po.to_expiration else None

            pending_order = PendingOrder(
                snapshot_id=snapshot_id,
                symbol=po.symbol.upper(),
                order_type=po.order_type,
                option_type=po.option_type.lower() if po.option_type else None,
                strike_price=Decimal(str(po.strike_price)) if po.strike_price else None,
                from_expiration=from_exp,
                to_expiration=to_exp,
                contracts=po.contracts,
                limit_price=Decimal(str(po.limit_price)) if po.limit_price else None,
                account_name=account_name,
                status='pending',
                raw_text=po.raw_text[:500] if po.raw_text else None
            )
            db.add(pending_order)
            pending_orders_saved += 1
            pending_orders_details.append({
                "symbol": po.symbol.upper(),
                "order_type": po.order_type,
                "option_type": po.option_type,
                "strike_price": float(po.strike_price) if po.strike_price else None,
                "contracts": po.contracts,
                "limit_price": float(po.limit_price) if po.limit_price else None,
            })
            logger.info(f"Saved pending order: {po.order_type} {po.symbol} {po.option_type} @ ${po.limit_price}")

    # Handle case where we have pending orders but no options
    elif save_options and not result.options and result.pending_orders:
        # Create snapshot just for pending orders
        snapshot = SoldOptionsSnapshot(
            source='robinhood',
            account_name=account_name,
            snapshot_date=datetime.utcnow(),
            parsing_status='success',
            raw_extracted_text=text[:5000]
        )
        db.add(snapshot)
        db.flush()
        snapshot_id = snapshot.id

        for po in result.pending_orders:
            from_exp = normalize_expiration_date(po.from_expiration) if po.from_expiration else None
            to_exp = normalize_expiration_date(po.to_expiration) if po.to_expiration else None

            pending_order = PendingOrder(
                snapshot_id=snapshot_id,
                symbol=po.symbol.upper(),
                order_type=po.order_type,
                option_type=po.option_type.lower() if po.option_type else None,
                strike_price=Decimal(str(po.strike_price)) if po.strike_price else None,
                from_expiration=from_exp,
                to_expiration=to_exp,
                contracts=po.contracts,
                limit_price=Decimal(str(po.limit_price)) if po.limit_price else None,
                account_name=account_name,
                status='pending',
                raw_text=po.raw_text[:500] if po.raw_text else None
            )
            db.add(pending_order)
            pending_orders_saved += 1
            pending_orders_details.append({
                "symbol": po.symbol.upper(),
                "order_type": po.order_type,
                "option_type": po.option_type,
                "strike_price": float(po.strike_price) if po.strike_price else None,
                "contracts": po.contracts,
                "limit_price": float(po.limit_price) if po.limit_price else None,
            })
            logger.info(f"Saved pending order: {po.order_type} {po.symbol} {po.option_type} @ ${po.limit_price}")

    elif save_options and result.has_options_section and not result.options:
        # Options section header detected but empty - user has cleared all options
        # Delete all snapshots for this account (cascade will delete associated options)
        existing_snapshots = db.query(SoldOptionsSnapshot).filter(
            SoldOptionsSnapshot.source == 'robinhood',
            SoldOptionsSnapshot.account_name == account_name
        ).all()
        
        for snapshot in existing_snapshots:
            logger.info(f"Deleting options snapshot {snapshot.id} for {account_name} - options section is empty (all options cleared)")
            db.delete(snapshot)
    
    # Update portfolio snapshot with new data
    if (save_stocks and (stocks_saved > 0 or stocks_updated > 0)) or (save_options and options_saved > 0):
        account_id = _normalize_account_id(account_name)
        
        # Calculate total portfolio value from current holdings
        holdings = db.query(InvestmentHolding).filter(
            InvestmentHolding.account_id == account_id,
            InvestmentHolding.source == 'robinhood'
        ).all()
        
        total_portfolio_value = sum(
            float(h.market_value) if h.market_value else 0
            for h in holdings
        )
        
        # Get owner and account_type
        parts = account_id.split('_')
        owner = parts[0].title() if parts else 'Unknown'
        account_type = '_'.join(parts[1:]) if len(parts) > 1 else 'brokerage'
        
        today = date.today()
        
        # Find existing snapshot for today or most recent
        existing_snapshot = db.query(PortfolioSnapshot).filter(
            PortfolioSnapshot.source == 'robinhood',
            PortfolioSnapshot.account_id == account_id,
            PortfolioSnapshot.statement_date == today
        ).first()
        
        if existing_snapshot:
            existing_snapshot.portfolio_value = Decimal(str(round(total_portfolio_value, 2)))
            existing_snapshot.securities_value = Decimal(str(round(total_portfolio_value, 2)))
            existing_snapshot.updated_at = datetime.utcnow()
            logger.info(f"Updated snapshot for {account_name}: ${total_portfolio_value:,.2f}")
        else:
            # Create new snapshot for today
            new_snapshot = PortfolioSnapshot(
                source='robinhood',
                account_id=account_id,
                owner=owner,
                account_type=account_type,
                statement_date=today,
                portfolio_value=Decimal(str(round(total_portfolio_value, 2))),
                securities_value=Decimal(str(round(total_portfolio_value, 2))),
                cash_balance=Decimal('0')
            )
            db.add(new_snapshot)
            logger.info(f"Created snapshot for {account_name}: ${total_portfolio_value:,.2f}")
    
    db.commit()
    
    # CRITICAL: Clear recommendations cache after updating positions
    # This ensures notifications use fresh position data, not stale cached data
    from app.core.cache import clear_cache
    cleared_count = clear_cache("recommendations:")
    logger.info(f"Cleared {cleared_count} recommendations cache entries after position update for {account_name}")
    
    return {
        "success": True,
        "account_name": account_name,
        "stocks_saved": stocks_saved,
        "stocks_updated": stocks_updated,
        "stocks_removed": len(stocks_removed_details),
        "options_saved": options_saved,
        "pending_orders_saved": pending_orders_saved,
        "snapshot_id": snapshot_id,
        "detected_format": result.detected_format,
        "stocks_created_details": stocks_created_details,
        "stocks_updated_details": stocks_updated_details,
        "stocks_removed_details": stocks_removed_details,
        "options_saved_details": options_saved_details,
        "pending_orders_details": pending_orders_details,
    }


def _normalize_account_id(account_name: str) -> str:
    """Convert account name to account_id format."""
    # "Neel's Brokerage" -> "neel_brokerage"
    # "Jaya's Roth IRA" -> "jaya_roth_ira"
    import re
    
    # Remove apostrophe-s
    normalized = account_name.lower().replace("'s", "").replace("'s", "")
    # Replace spaces with underscores
    normalized = re.sub(r'\s+', '_', normalized.strip())
    # Remove any other special characters
    normalized = re.sub(r'[^a-z0-9_]', '', normalized)
    
    return normalized


def _parse_account_name(account_name: str) -> tuple:
    """Parse account name into owner and account_type."""
    # "Neel's Brokerage" -> ("Neel", "brokerage")
    # "Jaya's Roth IRA" -> ("Jaya", "roth_ira")
    
    parts = account_name.split("'s ")
    if len(parts) == 2:
        owner = parts[0]
        account_type = parts[1].lower().replace(" ", "_")
    else:
        # Fallback
        parts = account_name.split("'s ")
        if len(parts) == 2:
            owner = parts[0]
            account_type = parts[1].lower().replace(" ", "_")
        else:
            owner = "Unknown"
            account_type = account_name.lower().replace(" ", "_")
    
    return owner, account_type


@router.post("/merge-accounts")
async def merge_accounts(
    source_account_id: str,
    target_account_id: str,
    db: Session = Depends(get_db)
):
    """
    Merge one account into another.
    - Moves all holdings from source to target (aggregating quantities)
    - Moves all transactions from source to target
    - Deletes the source account
    """
    from app.modules.investments.models import InvestmentHolding, InvestmentTransaction, InvestmentAccount
    
    # Verify both accounts exist
    source_account = db.query(InvestmentAccount).filter(
        InvestmentAccount.account_id == source_account_id
    ).first()
    target_account = db.query(InvestmentAccount).filter(
        InvestmentAccount.account_id == target_account_id
    ).first()
    
    if not source_account:
        raise HTTPException(status_code=404, detail=f"Source account '{source_account_id}' not found")
    if not target_account:
        raise HTTPException(status_code=404, detail=f"Target account '{target_account_id}' not found")
    
    # Merge holdings
    source_holdings = db.query(InvestmentHolding).filter(
        InvestmentHolding.account_id == source_account_id
    ).all()
    
    holdings_merged = 0
    for src_holding in source_holdings:
        # Check if target has this symbol
        target_holding = db.query(InvestmentHolding).filter(
            InvestmentHolding.account_id == target_account_id,
            InvestmentHolding.symbol == src_holding.symbol
        ).first()
        
        if target_holding:
            # Aggregate quantities
            target_holding.quantity = float(target_holding.quantity or 0) + float(src_holding.quantity or 0)
            if src_holding.market_value:
                target_holding.market_value = float(target_holding.market_value or 0) + float(src_holding.market_value or 0)
            db.delete(src_holding)
        else:
            # Move holding to target account
            src_holding.account_id = target_account_id
        holdings_merged += 1
    
    # Move transactions
    transactions_moved = db.query(InvestmentTransaction).filter(
        InvestmentTransaction.account_id == source_account_id
    ).update({InvestmentTransaction.account_id: target_account_id})

    # Delete source account
    db.delete(source_account)
    db.commit()

    return {
        "success": True,
        "message": f"Merged '{source_account_id}' into '{target_account_id}'",
        "holdings_merged": holdings_merged,
        "transactions_moved": transactions_moved
    }


# ============================================================================
# ROBINHOOD CASH SECTION PASTE
# ============================================================================

def _calc_true_cash(cash: float, options_collateral: float, pending_orders: float,
                    margin_used: float, account_format: str) -> float:
    """Compute true net cash contribution to True Portfolio.

    Brokerage: options collateral is a margin reservation — neutral to True Portfolio.
               Only actual margin debt (margin_used) reduces the portfolio.
               true_cash = cash_balance - margin_used

    IRA/Retirement: no borrowing. Options collateral is the owner's own cash, locked.
               true_cash = cash_balance + options_collateral + pending_orders
    """
    if account_format == 'brokerage':
        return cash - margin_used
    else:
        return cash + options_collateral + pending_orders


def _parse_robinhood_cash_text(text: str) -> dict:
    """
    Parse the Robinhood cash section copy-paste.  Handles two formats:

    BROKERAGE format (margin accounts):
        Cash                  $0.00
        Margin total          $200,000.00
        Margin used           -$5,594.67
        Options collateral    -$188,500.00
        Pending orders        -$2,106.00
        Total                 $3,799.33

    IRA format (no margin — all cash is owner's money):
        Traditional IRA cash  $295,605.89   (or "Roth IRA cash")
        Options collateral    -$274,000.00
        Buying power          $21,605.89

    Brokerage:
        cash_balance       = Cash line ($0)          ← free cash only
        options_collateral = abs(Options collateral)  ← margin-funded reservation, NOT owner's cash
        pending_orders     = abs(Pending orders)      ← margin-funded reservation
        margin_used        = abs(Margin used)         ← borrowed for stock purchases, a real debt
        net_total          = Total line (buying power remaining)
        true_cash          = cash_balance - margin_used
            Options collateral is excluded: it is a reservation on the margin facility.
            When options expire worthless the reservation lifts (no cash gain).
            When options are assigned the reservation converts to stock purchased on margin
            (asset +X, liability +X → net zero). Either way it is neutral to True Portfolio.

    IRA:
        cash_balance       = Buying power ($21,605.89)   ← free/deployable cash
        options_collateral = abs(Options collateral)      ← owner's real money, locked
        margin_used        = 0                            ← IRAs can't borrow
        net_total          = Buying power (same as cash_balance)
        ira_cash_total     = Traditional/Roth IRA cash    ← stored in margin_total field for reference
        true_cash          = cash_balance + options_collateral  (= ira_cash_total)
    """
    import re

    def _extract(label: str):
        """Extract dollar value for a standalone label (inline or newline-separated)."""
        # Inline: "Label        $X.XX"  (tabs or spaces between label and value)
        inline = rf'(?:^|\n)\s*{re.escape(label)}\s+(-?\$[\d,]+\.?\d*)'
        m = re.search(inline, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1)
        # Newline-separated: "Label\n$X.XX"
        newline = rf'(?:^|\n)\s*{re.escape(label)}\s*\n\s*(-?\$[\d,]+\.?\d*)'
        m = re.search(newline, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1)
        return None

    def amt(label: str):
        """Return absolute float value for label, or None."""
        raw = _extract(label)
        if raw is None:
            return None
        return abs(float(raw.replace('$', '').replace(',', '')))

    def signed(label: str):
        """Return signed float value for label, or None."""
        raw = _extract(label)
        if raw is None:
            return None
        return float(raw.replace('$', '').replace(',', ''))

    # --- Detect IRA format first ---
    ira_cash_total = amt('Traditional IRA cash') or amt('Roth IRA cash') or amt('IRA cash')

    if ira_cash_total is not None:
        # IRA format
        options_collateral = amt('Options collateral') or 0.0
        buying_power       = amt('Buying power') or amt('Buying Power') or 0.0

        return {
            'format':            'ira',
            'cash':              buying_power,        # free/deployable cash
            'margin_total':      ira_cash_total,      # total IRA cash (for display/reference)
            'margin_used':       0.0,                 # IRAs can't borrow
            'options_collateral': options_collateral,
            'pending_orders':    0.0,
            'net_total':         buying_power,
            'found_any':         True,
        }

    # --- Brokerage format ---
    cash               = amt('Cash')
    margin_total       = amt('Margin total')
    margin_used        = amt('Margin used')
    options_collateral = amt('Options collateral')
    pending_orders     = amt('Pending orders')
    net_total          = signed('Total')

    found_any = any(v is not None for v in [cash, margin_total, margin_used, options_collateral, pending_orders, net_total])

    return {
        'format':            'brokerage',
        'cash':              cash,
        'margin_total':      margin_total,
        'margin_used':       margin_used,
        'options_collateral': options_collateral,
        'pending_orders':    pending_orders,
        'net_total':         net_total,
        'found_any':         found_any,
    }


@router.post("/robinhood-cash/preview")
async def preview_robinhood_cash(data: dict, db: Session = Depends(get_db)):
    """
    Preview parsed Robinhood cash section before saving.
    Returns the extracted fields and computed true-cash value.
    """
    text = data.get("text", "")
    account_name = data.get("account_name", "")

    if not text.strip():
        raise HTTPException(status_code=400, detail="No text provided")

    parsed = _parse_robinhood_cash_text(text)

    if not parsed['found_any']:
        raise HTTPException(
            status_code=400,
            detail="Could not detect Robinhood cash section. Expected labels like 'Cash', 'Margin total', 'Options collateral', 'Total' (brokerage) or 'Traditional IRA cash', 'Buying power' (IRA)."
        )

    cash               = parsed['cash'] or 0.0
    options_collateral = parsed['options_collateral'] or 0.0
    pending_orders     = parsed['pending_orders'] or 0.0
    margin_used        = parsed['margin_used'] or 0.0
    true_cash = _calc_true_cash(cash, options_collateral, pending_orders, margin_used, parsed['format'])

    return {
        "success":            True,
        "format":             parsed['format'],
        "account_name":       account_name,
        "cash":               parsed['cash'],
        "margin_total":       parsed['margin_total'],
        "margin_used":        parsed['margin_used'],
        "options_collateral": parsed['options_collateral'],
        "pending_orders":     parsed['pending_orders'],
        "net_total":          parsed['net_total'],
        "true_cash":          round(true_cash, 2),
    }


@router.post("/robinhood-cash/save")
async def save_robinhood_cash(data: dict, db: Session = Depends(get_db)):
    """
    Save Robinhood cash section to account_cash_balances.
    Updates the existing row for this account (or creates one).
    """
    from app.modules.strategies.models import AccountCashBalance
    from decimal import Decimal
    from datetime import datetime

    text         = data.get("text", "")
    account_name = data.get("account_name", "")

    if not text.strip():
        raise HTTPException(status_code=400, detail="No text provided")
    if not account_name:
        raise HTTPException(status_code=400, detail="account_name is required")

    parsed = _parse_robinhood_cash_text(text)

    if not parsed['found_any']:
        raise HTTPException(
            status_code=400,
            detail="Could not detect Robinhood cash section."
        )

    from app.modules.strategies.models import AccountCashBalanceHistory
    from datetime import date as date_type

    def _dec(v):
        return Decimal(str(v)) if v is not None else None

    # cash_balance = free/deployable cash (buying power for IRA, free cash for brokerage)
    cash_balance_val = parsed['cash'] if parsed['cash'] is not None else 0.0

    cash               = parsed['cash'] or 0.0
    options_collateral = parsed['options_collateral'] or 0.0
    pending_orders     = parsed['pending_orders'] or 0.0
    margin_used        = parsed['margin_used'] or 0.0
    true_cash          = _calc_true_cash(cash, options_collateral, pending_orders, margin_used, parsed['format'])

    # --- Update current record (account_cash_balances) ---
    record = db.query(AccountCashBalance).filter(
        AccountCashBalance.account_name == account_name
    ).first()

    if record:
        record.cash_balance        = _dec(cash_balance_val)
        record.margin_total        = _dec(parsed['margin_total'])
        record.margin_used         = _dec(parsed['margin_used'])
        record.options_collateral  = _dec(parsed['options_collateral'])
        record.pending_orders      = _dec(parsed['pending_orders'])
        record.net_total           = _dec(parsed['net_total'])
        record.updated_at          = datetime.utcnow()
    else:
        fmt = parsed['format']
        record = AccountCashBalance(
            account_name       = account_name,
            cash_balance       = _dec(cash_balance_val),
            margin_total       = _dec(parsed['margin_total']),
            margin_used        = _dec(parsed['margin_used']),
            options_collateral = _dec(parsed['options_collateral']),
            pending_orders     = _dec(parsed['pending_orders']),
            net_total          = _dec(parsed['net_total']),
            notes              = f"Saved from Robinhood {parsed['format']} cash section paste",
        )
        db.add(record)

    # --- Upsert history row (account_cash_balance_history) ---
    today = date_type.today()
    hist = db.query(AccountCashBalanceHistory).filter(
        AccountCashBalanceHistory.account_name  == account_name,
        AccountCashBalanceHistory.snapshot_date == today,
    ).first()

    if hist:
        hist.account_format      = parsed['format']
        hist.cash_balance        = _dec(cash_balance_val)
        hist.margin_total        = _dec(parsed['margin_total'])
        hist.margin_used         = _dec(parsed['margin_used'])
        hist.options_collateral  = _dec(parsed['options_collateral'])
        hist.pending_orders      = _dec(parsed['pending_orders'])
        hist.net_total           = _dec(parsed['net_total'])
        hist.true_cash           = _dec(true_cash)
    else:
        hist = AccountCashBalanceHistory(
            account_name       = account_name,
            snapshot_date      = today,
            account_format     = parsed['format'],
            cash_balance       = _dec(cash_balance_val),
            margin_total       = _dec(parsed['margin_total']),
            margin_used        = _dec(parsed['margin_used']),
            options_collateral = _dec(parsed['options_collateral']),
            pending_orders     = _dec(parsed['pending_orders']),
            net_total          = _dec(parsed['net_total']),
            true_cash          = _dec(true_cash),
        )
        db.add(hist)

    db.commit()

    return {
        "success":            True,
        "format":             parsed['format'],
        "account_name":       account_name,
        "cash":               parsed['cash'],
        "margin_total":       parsed['margin_total'],
        "margin_used":        parsed['margin_used'],
        "options_collateral": parsed['options_collateral'],
        "pending_orders":     parsed['pending_orders'],
        "net_total":          parsed['net_total'],
        "true_cash":          round(true_cash, 2),
    }


@router.get("/robinhood-cash/balances")
async def get_cash_balances(db: Session = Depends(get_db)):
    """
    Return all accounts with their cash breakdown and computed true-cash.
    Used by the Investments page to show True Portfolio value.
    """
    from app.modules.strategies.models import AccountCashBalance

    rows = db.query(AccountCashBalance).all()

    accounts = []
    total_true_cash = 0.0
    total_margin_used = 0.0
    total_options_collateral = 0.0

    _BROKERAGE_ACCOUNTS = {"Neel's Brokerage", "Jaya's Brokerage", "Alisha's Brokerage"}

    for row in rows:
        cash               = float(row.cash_balance or 0)
        margin_used        = float(row.margin_used or 0)
        options_collateral = float(row.options_collateral or 0)
        pending_orders     = float(row.pending_orders or 0)
        fmt = 'brokerage' if row.account_name in _BROKERAGE_ACCOUNTS else 'ira'
        true_cash          = _calc_true_cash(cash, options_collateral, pending_orders, margin_used, fmt)

        total_true_cash          += true_cash
        total_margin_used        += margin_used
        total_options_collateral += options_collateral

        accounts.append({
            "account_name":       row.account_name,
            "cash":               cash,
            "margin_total":       float(row.margin_total or 0),
            "margin_used":        margin_used,
            "options_collateral": options_collateral,
            "pending_orders":     pending_orders,
            "net_total":          float(row.net_total or 0),
            "true_cash":          round(true_cash, 2),
            "has_breakdown":      row.margin_used is not None or row.options_collateral is not None,
            "updated_at":         row.updated_at.isoformat() if row.updated_at else None,
        })

    return {
        "accounts":                accounts,
        "total_true_cash":         round(total_true_cash, 2),
        "total_margin_used":       round(total_margin_used, 2),
        "total_options_collateral": round(total_options_collateral, 2),
    }


@router.get("/robinhood-cash/portfolio-history")
async def get_portfolio_history(db: Session = Depends(get_db)):
    """
    Return a time-series of True Portfolio value: stock equity + true cash (carry-forward).

    Each row is flagged is_real=True when the cash comes from an actual per-account statement
    snapshot (account_format != 'synthetic'). Rows before that first real date use synthetic
    estimated cash and are flagged is_real=False.
    """
    from sqlalchemy import text

    # Find the first date we have real (non-synthetic) per-account cash data
    real_start_row = db.execute(text("""
        SELECT MIN(snapshot_date)
        FROM account_cash_balance_history
        WHERE account_format != 'synthetic'
    """)).scalar()
    real_data_start = str(real_start_row) if real_start_row else None

    sql = text("""
        WITH stock_dates AS (
            SELECT snapshot_date, SUM(market_value) AS stock_value
            FROM investment_holdings_history
            GROUP BY snapshot_date
        ),
        cash_snapshots AS (
            SELECT snapshot_date, SUM(true_cash) AS total_true_cash
            FROM account_cash_balance_history
            GROUP BY snapshot_date
        ),
        real_cash_snapshots AS (
            -- Per-account carry-forward: for each date, sum the most recent real snapshot per account
            SELECT snapshot_date, SUM(true_cash) AS total_true_cash
            FROM account_cash_balance_history
            WHERE account_format != 'synthetic'
            GROUP BY snapshot_date
        ),
        earliest_cash AS (
            SELECT total_true_cash FROM cash_snapshots ORDER BY snapshot_date ASC LIMIT 1
        ),
        cash_carried AS (
            SELECT
                s.snapshot_date,
                s.stock_value,
                COALESCE(
                    -- For dates with real data: use per-account carry-forward (sum of each account's latest snapshot)
                    CASE WHEN :real_start IS NOT NULL AND s.snapshot_date >= :real_start THEN (
                        SELECT SUM(latest.true_cash) FROM (
                            SELECT DISTINCT ON (account_name) true_cash
                            FROM account_cash_balance_history
                            WHERE account_format != 'synthetic'
                              AND snapshot_date <= s.snapshot_date
                            ORDER BY account_name, snapshot_date DESC
                        ) latest
                    ) END,
                    -- Fallback: most recent synthetic snapshot on or before this date
                    (SELECT c.total_true_cash FROM cash_snapshots c
                     WHERE c.snapshot_date <= s.snapshot_date
                     ORDER BY c.snapshot_date DESC LIMIT 1),
                    (SELECT total_true_cash FROM earliest_cash),
                    0
                ) AS true_cash
            FROM stock_dates s
        )
        SELECT
            snapshot_date,
            stock_value,
            true_cash,
            stock_value + true_cash AS true_portfolio
        FROM cash_carried
        ORDER BY snapshot_date ASC
    """)

    rows = db.execute(sql, {"real_start": real_data_start}).fetchall()

    return {
        "real_data_start": real_data_start,
        "history": [
            {
                "date":           str(row.snapshot_date),
                "stock_value":    float(row.stock_value or 0),
                "true_cash":      float(row.true_cash or 0),
                "true_portfolio": float(row.true_portfolio or 0),
                "is_real":        real_data_start is not None and str(row.snapshot_date) >= real_data_start,
            }
            for row in rows
        ]
    }


# Map investment_holdings_history account_id → account_cash_balance_history account_name
_ACCOUNT_CASH_NAME: dict[str, str | None] = {
    "neel_brokerage":  "Neel's Brokerage",
    "jaya_brokerage":  "Jaya's Brokerage",
    "neel_retirement": "Neel's Retirement",
    "jaya_ira":        "Jaya's IRA",
    "neel_roth_ira":   "Neel's Roth IRA",
    "jaya_roth_ira":   "Jaya's Roth IRA",
    "alisha_brokerage": None,
    "family_hsa":       None,
}


@router.get("/robinhood-cash/portfolio-history/by-account/{account_id}")
async def get_account_portfolio_history(account_id: str, db: Session = Depends(get_db)):
    """
    Per-account True Portfolio history: equity from investment_holdings_history
    filtered to one account, plus per-account cash carry-forward from real snapshots.
    """
    from sqlalchemy import text

    cash_account_name = _ACCOUNT_CASH_NAME.get(account_id)

    # First real cash date for this specific account (None if no cash data)
    if cash_account_name:
        real_start_row = db.execute(text("""
            SELECT MIN(snapshot_date)
            FROM account_cash_balance_history
            WHERE account_name = :name AND account_format != 'synthetic'
        """), {"name": cash_account_name}).scalar()
        real_data_start = str(real_start_row) if real_start_row else None
    else:
        real_data_start = None

    sql = text("""
        WITH stock_dates AS (
            SELECT snapshot_date, SUM(market_value) AS stock_value
            FROM investment_holdings_history
            WHERE account_id = :account_id
            GROUP BY snapshot_date
        ),
        cash_carried AS (
            SELECT
                s.snapshot_date,
                s.stock_value,
                CASE
                    WHEN :cash_name IS NOT NULL AND :real_start IS NOT NULL
                         AND s.snapshot_date >= :real_start THEN (
                        SELECT true_cash
                        FROM account_cash_balance_history
                        WHERE account_name = :cash_name
                          AND account_format != 'synthetic'
                          AND snapshot_date <= s.snapshot_date
                        ORDER BY snapshot_date DESC LIMIT 1
                    )
                    ELSE NULL
                END AS true_cash
            FROM stock_dates s
        )
        SELECT
            snapshot_date,
            stock_value,
            COALESCE(true_cash, 0) AS true_cash,
            stock_value + COALESCE(true_cash, 0) AS true_portfolio
        FROM cash_carried
        ORDER BY snapshot_date ASC
    """)

    rows = db.execute(sql, {
        "account_id": account_id,
        "cash_name": cash_account_name,
        "real_start": real_data_start,
    }).fetchall()

    return {
        "account_id": account_id,
        "real_data_start": real_data_start,
        "history": [
            {
                "date":           str(row.snapshot_date),
                "stock_value":    float(row.stock_value or 0),
                "true_cash":      float(row.true_cash or 0),
                "true_portfolio": float(row.true_portfolio or 0),
                "is_real":        real_data_start is not None and str(row.snapshot_date) >= real_data_start,
            }
            for row in rows
        ]
    }



# ---------------------------------------------------------------------------
# Symbol price history (Robinhood MCP historicals — market-data-source-order
# KB rule: Robinhood first, never Yahoo on must-succeed paths). Feeds the
# YTD/1Y/5Y growth columns on the Investments page; refresh via the MCP sync
# routine (docs/ROBINHOOD_MCP_SYNC.md).
# ---------------------------------------------------------------------------

@router.post("/price-history")
async def ingest_price_history(payload: dict, db: Session = Depends(get_db)):
    """Upsert weekly/daily closes: {source, bars: [{symbol, date, close}]}."""
    from sqlalchemy import text as _text
    bars = payload.get("bars") or []
    source = payload.get("source") or "robinhood_mcp"
    if not bars:
        raise HTTPException(status_code=400, detail="no bars")
    upserted = 0
    for b in bars:
        db.execute(_text("""
            INSERT INTO symbol_price_history (symbol, price_date, close_price, source)
            VALUES (:sym, :d, :c, :src)
            ON CONFLICT (symbol, price_date)
            DO UPDATE SET close_price = EXCLUDED.close_price, source = EXCLUDED.source
        """), {"sym": b["symbol"].upper(), "d": b["date"], "c": b["close"], "src": source})
        upserted += 1
    db.commit()
    return {"success": True, "upserted": upserted}


@router.post("/cost-basis")
async def ingest_cost_basis(payload: dict, db: Session = Depends(get_db)):
    """Upsert per-account, per-symbol average cost per share:
    {source, bars: [{account_id, symbol, date, cost_basis}]}.

    Sourced from Robinhood's own average_buy_price (average-cost
    accounting, already adjusted for partial sells — the MCP tool's own
    guide text: "the average cost per share shown in the Robinhood
    app") via the MCP sync, NOT reconstructed here — this is a thin
    upsert into investment_cost_basis_history, same shape as
    /price-history. Feeds assignment_loss_service.py's "vs. cost
    basis" figure on call assignments (Neel, 2026-08-08)."""
    from sqlalchemy import text as _text
    bars = payload.get("bars") or []
    source = payload.get("source") or "robinhood_mcp"
    if not bars:
        raise HTTPException(status_code=400, detail="no bars")
    upserted = 0
    for b in bars:
        db.execute(_text("""
            INSERT INTO investment_cost_basis_history
                (source, account_id, symbol, snapshot_date, avg_cost_per_share, updated_at)
            VALUES (:src, :acct, :sym, :d, :c, NOW())
            ON CONFLICT ON CONSTRAINT uq_cost_basis_history
            DO UPDATE SET avg_cost_per_share = EXCLUDED.avg_cost_per_share, updated_at = NOW()
        """), {"src": source, "acct": b["account_id"], "sym": b["symbol"].upper(),
               "d": b["date"], "c": b["cost_basis"]})
        upserted += 1
    db.commit()
    return {"success": True, "upserted": upserted}
