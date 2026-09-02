"""Document upload & verification routes."""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Optional

import anyio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..config import settings, UPLOAD_DIR
from ..core.deps import get_current_officer, log_audit
from ..models.models import get_db, Officer, VerificationSession, Alert
from ..schemas.schemas import (UploadResponse, RawVerifyRequest, VerifyRequest,
                               SyntheticVerifyRequest)
from ..services import orchestrator

router = APIRouter(tags=["verification"])


# ---------------------------------------------------------------------------
# File validation / storage
# ---------------------------------------------------------------------------

def _validate_upload(file: UploadFile) -> None:
    if file.content_type not in settings.ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{file.content_type}'. "
                   "Allowed: " + ", ".join(settings.ALLOWED_IMAGE_TYPES))
    # Size guard
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large (max {settings.MAX_UPLOAD_MB} MB)")


# Only these extensions are ever written to disk. The client-supplied filename
# is never used directly; we derive an extension and a server-generated unique
# basename so path traversal and filename injection are impossible.
_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
_SAFE_EXT_RE = re.compile(r"^\.[A-Za-z0-9]+$")


def _safe_extension(raw_name: str) -> str:
    """Return a safe, whitelisted extension, or '.png' as a fallback."""
    ext = Path(raw_name or "").suffix.lower()
    if not _SAFE_EXT_RE.match(ext) or ext not in _ALLOWED_EXTENSIONS:
        return ".png"
    return ext


def _save_upload(file: UploadFile, prefix: str = "doc") -> str:
    """Persist an uploaded file to the UPLOAD_DIR and return its safe filename.

    The directory is created if missing. The stored filename is always a
    server-generated token prefix + uuid + whitelisted extension, so a malicious
    client filename can never escape UPLOAD_DIR or write to an arbitrary path.
    """
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = _safe_extension(file.filename)
    filename = f"{prefix}_{uuid.uuid4().hex}{ext}"
    target = upload_dir / filename
    with target.open("wb") as fh:
        fh.write(file.file.read())
    return filename


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/upload-document", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    _validate_upload(file)
    filename = _save_upload(file, "doc")
    return UploadResponse(file_id=filename, filename=filename,
                          file_type=file.content_type or "application/octet-stream",
                          size_bytes=(Path(UPLOAD_DIR) / filename).stat().st_size)


@router.post("/upload-photo")
async def upload_photo(file: UploadFile = File(...)):
    """Upload a reference/provided face photo."""
    _validate_upload(file)
    filename = _save_upload(file, "photo")
    return UploadResponse(file_id=filename, filename=filename,
                          file_type=file.content_type or "application/octet-stream",
                          size_bytes=(Path(UPLOAD_DIR) / filename).stat().st_size)


@router.post("/ocr/extract")
async def extract_ocr(filename: str = Form(...),
                      officer: Officer = Depends(get_current_officer)):
    path = Path(UPLOAD_DIR) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Uploaded file not found")
    from ..services.ocr import run_ocr_from_bytes
    try:
        data = await run_in_threadpool(path.read_bytes)
        result = await run_in_threadpool(run_ocr_from_bytes, data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"OCR failed: {exc}")
    return {"text": result.text, "confidence": result.confidence,
            "lines": result.to_dict().get("lines", [])}


@router.post("/mrz/parse")
async def mrz_parse(filename: str = Form(...),
                    officer: Officer = Depends(get_current_officer)):
    path = Path(UPLOAD_DIR) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Uploaded file not found")
    from ..services.ocr import run_ocr_from_bytes
    from ..services.mrz import extract_mrz_from_text
    try:
        data = await run_in_threadpool(path.read_bytes)
        result = await run_in_threadpool(run_ocr_from_bytes, data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"OCR failed: {exc}")
    mrz = extract_mrz_from_text(result.text)
    return {"found": mrz is not None,
            "mrz": mrz.as_dict() if mrz else None,
            "checksum_valid": bool(mrz and mrz.checksum_passed)}


@router.post("/verify/document")
async def verify_document(request: VerifyRequest,
                          officer: Officer = Depends(get_current_officer),
                          db: Session = Depends(get_db)):
    """Run the full image-based verification pipeline."""
    upload_dir = Path(UPLOAD_DIR)
    image_path = upload_dir / request.image_filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Document image not found")

    ref_path = upload_dir / request.reference_photo_filename if request.reference_photo_filename else None
    prov_path = upload_dir / request.provided_photo_filename if request.provided_photo_filename else None

    timeout = float(getattr(settings, "VERIFY_TIMEOUT_S", 30) or 30)
    try:
        # Offload the CPU/IO-heavy pipeline to a Starlette worker thread so it
        # never blocks the asyncio event loop (which would freeze every other API
        # endpoint). A bounded timeout turns a stuck verification into an error
        # instead of leaving the server hanging.
        with anyio.fail_after(timeout):
            result = await run_in_threadpool(
                orchestrator.verify_image, image_path, ref_path, prov_path,
                request.document_type, extra_attrs={})
    except orchestrator.VerificationError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Verification timed out after {timeout:.0f}s. Please retry.")
    except Exception as exc:  # noqa: BLE001 - never leave the server stuck
        raise HTTPException(status_code=500, detail=f"Verification failed: {exc}")

    session = _persist(session=None, db=db, result=result,
                       officer_id=officer.id,
                       image_filename=request.image_filename,
                       reference_photo_filename=request.reference_photo_filename or "",
                       image_url=f"/media/uploads/{request.image_filename}")
    result["verification_id"] = session.id
    result["image_url"] = f"/media/uploads/{request.image_filename}"
    log_audit(db, officer.id, "verify_document",
              f"Verified {result.get('passenger', {}).get('full_name', '')} "
              f"score={result['risk']['score']}")
    return result


@router.post("/verify/complete")
async def verify_complete(filename: str = Form(...),
                          reference_photo_filename: Optional[str] = Form(None),
                          provided_photo_filename: Optional[str] = Form(None),
                          document_type: str = Form("auto"),
                          officer: Officer = Depends(get_current_officer),
                          db: Session = Depends(get_db)):
    """Convenience multipart endpoint that verifies an already-uploaded image."""
    upload_dir = Path(UPLOAD_DIR)
    path = upload_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document image not found")
    ref_path = upload_dir / reference_photo_filename if reference_photo_filename else None
    prov_path = upload_dir / provided_photo_filename if provided_photo_filename else None
    timeout = float(getattr(settings, "VERIFY_TIMEOUT_S", 30) or 30)
    try:
        with anyio.fail_after(timeout):
            result = await run_in_threadpool(
                orchestrator.verify_image, path, ref_path, prov_path, document_type)
    except orchestrator.VerificationError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Verification timed out after {timeout:.0f}s. Please retry.")
    except Exception as exc:  # noqa: BLE001 - never leave the server stuck
        raise HTTPException(status_code=500, detail=f"Verification failed: {exc}")
    session = _persist(None, db, result, officer.id, filename,
                       reference_photo_filename or "",
                       image_url=f"/media/uploads/{filename}")
    result["verification_id"] = session.id
    result["image_url"] = f"/media/uploads/{filename}"
    return result


@router.post("/verify/demo")
async def verify_demo(request: RawVerifyRequest,
                      officer: Officer = Depends(get_current_officer),
                      db: Session = Depends(get_db)):
    """Run one of the seven SIH demonstration cases."""
    result = orchestrator.verify_demo(request)
    # Show a matching sample document image for the demo result page.
    _demo_img = {
        "valid": "/media/samples/valid_passport.png",
        "expired": "/media/samples/expired_passport.png",
        "mrz_mismatch": "/media/samples/mismatch_passport.png",
        "face_mismatch": "/media/samples/valid_passport.png",
        "tamper": "/media/samples/mismatch_passport.png",
        "watchlist": "/media/samples/watchlist_passport.png",
        "duplicate": "/media/samples/valid_passport.png",
        "not_found": "/media/samples/valid_passport.png",
    }
    demo_img = _demo_img.get(request.scenario, "/media/samples/valid_passport.png")
    session = _persist(None, db, result, officer.id,
                       image_filename="", reference_photo_filename="",
                       image_url=demo_img)
    result["verification_id"] = session.id
    result["image_url"] = demo_img
    return result


@router.post("/verify/synthetic")
async def verify_synthetic(request: SyntheticVerifyRequest,
                           officer: Officer = Depends(get_current_officer),
                           db: Session = Depends(get_db)):
    """Run the synthetic-document tamper / anomaly demonstrator.

    Evaluates one of the FICTIONAL demo identity cards (Aadhaar / PAN / College
    ID) with the heuristic anomaly detector, then returns an explainable
    LOW/VERIFIED or HIGH/HIGH-RISK verdict.  No real document is involved.
    """
    try:
        result = orchestrator.verify_synthetic_document(request.synthetic_id)
    except orchestrator.VerificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    sample_file = orchestrator.synthetic_sample_file(request.synthetic_id)
    synth_img = f"/media/samples/{sample_file}" if sample_file else ""
    session = _persist(None, db, result, officer.id,
                       image_filename="", reference_photo_filename="",
                       image_url=synth_img)
    result["verification_id"] = session.id
    result["image_url"] = synth_img
    log_audit(db, officer.id, "verify_synthetic",
              f"Synthetic doc '{request.synthetic_id}' -> "
              f"{result['risk']['level']} ({result['risk']['score']})")
    return result


@router.get("/verification/history")
async def verification_history(limit: int = 50,
                               officer: Officer = Depends(get_current_officer),
                               db: Session = Depends(get_db)):
    rows = (db.query(VerificationSession)
            .order_by(VerificationSession.created_at.desc())
            .limit(min(limit, 200)).all())
    return [r.to_summary() for r in rows]


@router.get("/verification/{vid}")
async def get_verification(vid: int, officer: Officer = Depends(get_current_officer),
                           db: Session = Depends(get_db)):
    session = db.query(VerificationSession).filter(VerificationSession.id == vid).first()
    if not session:
        raise HTTPException(status_code=404, detail="Verification not found")
    result = dict(session.result_json or {})
    result["verification_id"] = session.id
    # Ensure a restored session can always show its document image, even for
    # sessions persisted before image_url was stored (fall back to /media).
    if not result.get("image_url") and session.image_filename:
        result["image_url"] = f"/media/uploads/{session.image_filename}"
    return result


@router.get("/risk-score")
async def risk_calculate(ocr_mrz_mismatch: bool = False,
                         face_mismatch: bool = False,
                         expired_passport: bool = False,
                         expired_visa: bool = False,
                         watchlist_match: bool = False,
                         tamper_high: bool = False,
                         dup_identity: bool = False,
                         officer: Officer = Depends(get_current_officer)):
    from ..services.risk import score
    signals = {
        "ocr_mrz_mismatch": ocr_mrz_mismatch,
        "face_mismatch": face_mismatch,
        "expired_passport": expired_passport,
        "expired_visa": expired_visa,
        "watchlist_match": watchlist_match,
        "tamper_high": tamper_high,
        "duplicate_identity": dup_identity,
    }
    return score(signals).to_dict()


@router.get("/alerts")
async def get_alerts(officer: Officer = Depends(get_current_officer),
                     db: Session = Depends(get_db)):
    alerts = db.query(Alert).order_by(Alert.created_at.desc()).limit(100).all()
    return [{
        "id": a.id, "title": a.title, "message": a.message,
        "severity": a.severity, "is_read": a.is_read,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    } for a in alerts]


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _persist(session, db, result, officer_id, image_filename,
             reference_photo_filename, image_url=""):
    """Persist a verification session + alerts derived from a result.

    The `session` argument is accepted for API compatibility but currently
    unused; a fresh VerificationSession is always created from the result.
    `image_url` is persisted into the session's result_json so a restored
    session can display the document image after a full page refresh.
    """
    passenger = result.get("passenger", {})
    risk = result.get("risk", {})
    stored_result = dict(result)
    if image_url:
        stored_result["image_url"] = image_url
    elif image_filename:
        stored_result["image_url"] = f"/media/uploads/{image_filename}"
    session = VerificationSession(
        officer_id=officer_id,
        status="completed",
        passenger_name=passenger.get("full_name", ""),
        document_number=passenger.get("document_number", ""),
        document_type=result.get("document_type", "passport"),
        nationality=passenger.get("nationality", ""),
        date_of_birth=passenger.get("date_of_birth", ""),
        sex=passenger.get("sex", ""),
        risk_score=risk.get("score", 0),
        risk_level=risk.get("level", "LOW"),
        decision=risk.get("decision", "VERIFIED"),
        image_filename=image_filename,
        reference_photo_filename=reference_photo_filename,
        result_json=stored_result,
    )
    db.add(session)
    db.flush()

    # Create an alert for high-risk decisions
    if (risk.get("level") == "HIGH") or (risk.get("score", 0) >= settings.RISK_THRESHOLD_HIGH):
        db.add(Alert(
            session_id=session.id, severity="high",
            title="HIGH RISK verification",
            message=f"Verification flagged {risk.get('decision', 'HIGH RISK')} "
                    f"with score {risk.get('score', 0)} for "
                    f"{passenger.get('full_name', 'unknown')}."))

    db.commit()
    return session
