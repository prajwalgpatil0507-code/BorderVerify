"""Verification orchestrator.

Runs the end-to-end pipeline:

    document image -> OCR -> field extraction -> MRZ parse + checksum
    -> OCR/MRZ cross-validation -> tamper analysis -> face verification
    -> expiry validation -> watchlist -> duplicate identity -> risk score
    -> final decision.

Supports two entry points:
  * ``verify_image``  : full pipeline on a real uploaded document image.
  * ``verify_demo``   : assemble a result from supplied/mock attributes for the
                        seven SIH demonstration cases.
"""
from __future__ import annotations

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Optional

import numpy as np
import cv2

logger = logging.getLogger("borderverify.orchestrator")


def _now() -> float:
    return time.perf_counter()


def _elapsed_since(t0: float) -> float:
    return time.perf_counter() - t0


def _log_timing(timing: dict) -> None:
    total = timing.get("total", 0.0)
    parts = " | ".join(f"{k}={v:.2f}s" for k, v in timing.items())
    logger.info("VERIFY TIMING: %s | total=%.2fs", parts, total)


def _run_face_match(reference_photo_path: str, provided_photo_path: str):
    """Runs face verification in a worker thread. Never raises; returns a
    ``FaceMatch`` on any outcome (mirrors the original inline fallback)."""
    try:
        ref_img = _load_image(reference_photo_path)
        prov_img = _load_image(provided_photo_path)
        return face_service.match_faces(
            ref_img, prov_img,
            threshold=settings.FACE_MATCH_THRESHOLD,
            review_threshold=settings.FACE_REVIEW_THRESHOLD)
    except Exception:  # noqa: BLE001 - degraded to no_face, never blocks pipeline
        return face_service.FaceMatch(
            similar=False, score=0.0, status="no_face",
            message="Face verification could not run on the provided images.",
            provided=face_service.FaceDetection(),
            reference=face_service.FaceDetection())


# Shared executor reused across requests for the advisory Gemini call only.
# It is created ONCE so we never spin up / tear down threads per request (which
# would accumulate threads over many verifications and degrade the server). The
# pool lives for the process lifetime.
_GEMINI_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gemini")

from ..config import settings
from . import ocr as ocr_service
from . import mrz as mrz_service
from . import crosscheck as crosscheck_service
from . import tamper as tamper_service
from . import document_anomaly as anomaly_service
from . import face as face_service
from . import risk as risk_service
from . import countries as countries_service
from . import providers as provider_service
from . import gemini as gemini_service
from . import document_analysis as document_analysis_service
from . import liveness as liveness_service
from .providers import SOURCE_LABEL as DS_LABEL, ENVIRONMENT as DS_ENV
from .date_utils import expiry_status, parse_iso


class VerificationError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_image(path: str) -> np.ndarray:
    if not path or not os.path.exists(path):
        raise VerificationError(f"Image file not found: {path}")
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise VerificationError("Could not decode image")
    return img


def _mrz_checksum_ok(mrz) -> bool:
    return bool(mrz and mrz.checksum_passed)


def _merge_fields(ocr_fields: dict, mrz) -> dict:
    """Merge OCR + MRZ into a single passenger record dict."""
    def ocrv(k):
        v = ocr_fields.get(k)
        return v.get("value") if isinstance(v, dict) else v

    return {
        "surname": (mrz.surname if mrz and mrz.surname else ocrv("surname") or ""),
        "given_names": (mrz.given_names if mrz and mrz.given_names else ocrv("given_names") or ""),
        "full_name": (mrz.full_name if mrz and mrz.full_name else
                      f"{ocrv('surname') or ''} {ocrv('given_names') or ''}".strip()),
        "date_of_birth": (mrz.date_of_birth if mrz and mrz.date_of_birth else ocrv("date_of_birth") or ""),
        "nationality": (mrz.nationality if mrz and mrz.nationality else ocrv("nationality") or ""),
        "sex": (mrz.sex if mrz and mrz.sex else ocrv("sex") or ""),
        "document_number": (mrz.document_number if mrz and mrz.document_number.strip("<")
                            else ocrv("passport_number") or ""),
        "date_of_expiry": (mrz.date_of_expiry if mrz and mrz.date_of_expiry else ocrv("date_of_expiry") or ""),
        "date_of_issue": ocrv("date_of_issue") or "",
        "issuing_country": (mrz.issuing_country if mrz and mrz.issuing_country else ocrv("issuing_country") or ""),
    }


# ---------------------------------------------------------------------------
# Demo / scenario verification (no real image needed for every case)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Honest verdict derivation
# ---------------------------------------------------------------------------
# A document is NEVER "verified" merely because it uploaded.  The verdict comes
# from the extracted data + the reference-database look-up.  If no identifying
# data could be extracted (unreadable / corrupt / blank), or the data could not
# be matched, we return UNVERIFIED instead of a false positive.

_VERDICT_HARD_NEGATIVES = (
    "invalid_mrz", "ocr_mrz_mismatch", "expired_passport", "face_mismatch",
    "tamper_high", "watchlist_match", "blacklist", "duplicate_identity",
    "document_anomaly", "expired_visa", "passport_field_mismatch",
    "liveness_not_live",
)


# ---------------------------------------------------------------------------
# Field-level comparison against the reference database
# ---------------------------------------------------------------------------
# A document number matching a reference record is NOT enough to certify it.
# The extracted identity fields (name, DOB, nationality, expiry) must agree with
# the record. If any populated field conflicts, the document is flagged as
# NOT_VERIFIED / REVIEW and the conflicting fields are returned so the UI can
# show exactly which data points disagree.

def _norm_text(value) -> str:
    """Normalise a free-text field for tolerant comparison (case/space-insensitive)."""
    return re.sub(r"[^A-Z0-9]", "", str(value or "")).upper()


def _norm_dob(value) -> str:
    """Normalise a date-of-birth string to YYYYMMDD where possible.

    MRZ uses YYMMDD (e.g. ``000504``); OCR sometimes yields DDMMYY. We normalise
    both to an unambiguous ``YYYYMMDD`` so the comparison is not tripped by a
    presentation difference. Returns ``""`` when it cannot be interpreted.
    """
    v = re.sub(r"[^0-9]", "", str(value or ""))
    if not v:
        return ""
    if len(v) == 8:
        return v                                   # YYYYMMDD
    if len(v) == 6:
        y, mo, d = int(v[0:2]), int(v[2:4]), int(v[4:6])
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"20{v[0:2]}{v[2:4]}{v[4:6]}"   # YYMMDD
        d, mo, y = int(v[0:2]), int(v[2:4]), int(v[4:6])
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"20{v[4:6]}{v[2:4]}{v[0:2]}"   # DDMMYY
    return v


def _compare_reference(passenger: dict, reference, doc_no: str) -> tuple[list, list]:
    """Compare extracted passenger fields to a matched reference-record object.

    Returns ``(matched_fields, mismatched_fields)``. A field is only evaluated
    when BOTH sides carry a non-empty value - an absent field on the extracted
    side is treated as "insufficient evidence", never as a conflict.
    """
    doc_no = _norm_text(doc_no)
    matched: list = []
    mismatched: list = []

    def record(field: str, extracted: str, reference_value: str):
        ex = _norm_text(extracted)
        ref = _norm_text(reference_value)
        if ex and ref:
            entry = {"field": field, "extracted": str(extracted or ""),
                     "reference": str(reference_value or "")}
            (matched if ex == ref else mismatched).append(entry)

    # document number is the indexed key - its equality is what made the record
    # match, so it is always recorded as a matched field (or conflict).
    record("document_number", doc_no, (reference.document_number or doc_no) if reference else doc_no)

    # Free-text identity fields
    record("surname", passenger.get("surname", ""), reference.surname)
    record("given_names", passenger.get("given_names", ""), reference.given_names)
    record("nationality", passenger.get("nationality", ""), reference.nationality)
    record("issuing_country", passenger.get("issuing_country", ""), reference.issuing_country)

    # Full name derived from surname + given names on both sides
    ex_full = _norm_text(passenger.get("full_name", "")) or (
        _norm_text(passenger.get("surname", "")) + _norm_text(passenger.get("given_names", "")))
    ref_full = _norm_text(reference.surname) + _norm_text(reference.given_names)
    if ex_full and ref_full:
        entry = {"field": "full_name", "extracted": str(passenger.get("full_name", "") or ""),
                 "reference": f"{reference.surname or ''} {reference.given_names or ''}".strip()}
        (matched if ex_full == ref_full else mismatched).append(entry)

    # Date of birth (format-tolerant)
    ex_dob = _norm_dob(passenger.get("date_of_birth", ""))
    ref_dob = _norm_dob(reference.date_of_birth)
    if ex_dob and ref_dob:
        entry = {"field": "date_of_birth", "extracted": ex_dob, "reference": ref_dob}
        (matched if ex_dob == ref_dob else mismatched).append(entry)

    # Date of expiry (format-tolerant) - a differing expiry is a real conflict
    ex_exp = _norm_dob(passenger.get("date_of_expiry", ""))
    ref_exp = _norm_dob(reference.date_of_expiry)
    if ex_exp and ref_exp:
        entry = {"field": "date_of_expiry", "extracted": ex_exp, "reference": ref_exp}
        (matched if ex_exp == ref_exp else mismatched).append(entry)

    return matched, mismatched


def _build_database_match(status: str, doc_no: str, reference_dict: dict,
                          matched: list, mismatched: list) -> dict:
    """Assemble the ``database_match`` block surfaced to the result page."""
    return {
        "status": status,                       # MATCH | CONFLICT | NOT_FOUND | NOT_APPLICABLE
        "document_number": doc_no,
        "record": reference_dict or {},
        "matched_fields": matched,
        "mismatched_fields": mismatched,
    }


def _derive_verdict(passenger: dict, ocr_text: str, ocr_conf: float,
                    mrz, risk, passport_lookup, risk_signals: dict,
                    db_match: Optional[dict] = None) -> tuple[str, str]:
    doc_no = str(passenger.get("document_number") or "").strip()
    full_name = str(passenger.get("full_name") or "").strip()
    has_extractable = bool(doc_no) or bool(mrz) or bool(full_name)
    ocr_empty = not bool((ocr_text or "").strip())
    ocr_low_conf = (str(ocr_conf or "").strip() != "" and
                    float(ocr_conf or 0) < settings.OCR_CONFIDENCE_THRESHOLD)

    # Insufficient evidence -> refuse to certify.
    if (not has_extractable) or ocr_empty or ocr_low_conf:
        return ("UNVERIFIED",
                "The document could not be read confidently - no identifying fields "
                "were extracted. Manual review is required.")

    hard_negative = any(risk_signals.get(s) for s in _VERDICT_HARD_NEGATIVES)

    # A field-level conflict against the reference record is surfaced verbatim so
    # the officer sees exactly which data points disagree.
    mismatch_reason = ""
    if db_match and db_match.get("mismatched_fields"):
        parts = [f"{m.get('field')}: extracted '{m.get('extracted')}' vs "
                 f"database '{m.get('reference')}'"
                 for m in db_match["mismatched_fields"]]
        mismatch_reason = (" Extracted identity fields conflict with the database "
                           "record: " + "; ".join(parts) + ".")

    # Strong negative evidence (tamper / watchlist / blacklist / face mismatch /
    # expired / doctored MRZ / duplicate / field conflict) -> the document did not pass.
    if risk.level == "HIGH":
        return ("NOT_VERIFIED", "; ".join(risk.reasons) or "High-risk signals detected.")
    if hard_negative:
        base = "; ".join(risk.reasons) or "Document data did not match the reference record."
        return ("NOT_VERIFIED", base + mismatch_reason)

    # Medium risk, or the document number is absent from the reference DB ->
    # the data cannot be confidently matched to a verification record.
    if risk.level == "MEDIUM" or not passport_lookup.found:
        if not passport_lookup.found:
            return ("UNVERIFIED",
                    "The document information could not be matched with an available "
                    "verification record.")
        return ("UNVERIFIED",
                "; ".join(risk.reasons) or "Uncertain; manual review is required.")

    return ("VERIFIED",
            "Document data was extracted and matched against the reference database "
            "with no negative signals.")


def _confidence_from(ocr_conf) -> int:
    """Return a 0-100 extraction-confidence integer."""
    try:
        return max(0, min(100, round(float(ocr_conf or 0) * 100)))
    except (TypeError, ValueError):
        return 0


def verify_demo(request) -> dict:
    """Assemble an explainable result for the seven SIH demonstration cases."""
    scenario = request.scenario or "valid"

    # Base attributes (may come from the request, else sensible demo defaults)
    doc_number = request.document_number or "P12345678"
    surname = request.surname or "RAIJILO"
    given_names = request.given_names or "MARK THOMAS"
    dob = request.date_of_birth or "000504"
    nationality = request.nationality or "UTO"
    sex = request.sex or "M"
    expiry = request.date_of_expiry or "330912"   # future by default (today is 2026)
    face_score = request.face_score

    # --- construct the MRZ for this case ---
    mrz_lines = request.mrz_lines or _build_td3(doc_number, nationality, surname,
                                                given_names, dob, sex, expiry,
                                                tamper=scenario in ("mrz_mismatch",))

    mrz = None
    risk_signals: dict = {}
    ocr_fields: dict = {
        "passport_number": {"value": doc_number},
        "date_of_birth": {"value": dob},
        "surname": {"value": surname},
        "given_names": {"value": given_names},
        "nationality": {"value": nationality},
        "sex": {"value": sex},
        "date_of_expiry": {"value": expiry},
        "date_of_issue": {"value": "240504", "confidence": 0.5},
    }

    ocr_text = (
        f"REPUBLIC OF UTOPIA\nPASSPORT\nSurname {surname}  Given names {given_names}\n"
        f"Passport No. {doc_number}\nDate of birth {dob}\nSex {sex}\nNationality {nationality}\n"
        f"Date of expiry {expiry}\n"
    )

    # Per-scenario payload manipulation
    if scenario == "expired":
        # Force a past expiry date (relative to today 2026-09-02)
        expiry = "200912"
        ocr_fields["date_of_expiry"] = {"value": "200912", "confidence": 0.8}
        mrz = mrz_service.parse_mrz(_build_td3(doc_number, nationality, surname,
                                               given_names, dob, sex, expiry))
        risk_signals["expired_passport"] = True

    elif scenario == "mrz_mismatch":
        # MRZ intentionally built with a different document number AND a bad
        # check digit (as in a doctored document).
        mrz = mrz_service.parse_mrz(_build_td3("P00000000", nationality, surname,
                                               given_names, dob, sex, expiry,
                                               tamper=True))
        risk_signals["ocr_mrz_mismatch"] = True

    elif scenario == "face_mismatch":
        face_score = 0.42
        risk_signals["face_mismatch"] = True

    elif scenario == "tamper":
        risk_signals["tamper_high"] = True
        risk_signals["tamper_medium"] = True

    elif scenario == "watchlist":
        # Use the watchlisted passenger seeded in the reference DB so the look-up hits.
        doc_number = "P1111222"
        surname = "JONES"
        given_names = "MICHAEL"
        dob = "880723"
        nationality = "USA"
        sex = "M"
        expiry = "330101"
        mrz = mrz_service.parse_mrz(_build_td3(doc_number, nationality, surname,
                                               given_names, dob, sex, expiry))
        ocr_fields = {
            "passport_number": {"value": doc_number},
            "date_of_birth": {"value": dob},
            "surname": {"value": surname},
            "given_names": {"value": given_names},
            "nationality": {"value": nationality},
            "sex": {"value": sex},
            "date_of_expiry": {"value": expiry},
        }

    elif scenario == "duplicate":
        # Same identity as a prior DB record under a second travel document.
        doc_number = "P5556665"
        surname = "KUMAR"
        given_names = "ROBERT"
        dob = "950914"
        nationality = "IND"
        sex = "M"
        expiry = "330101"
        mrz = mrz_service.parse_mrz(_build_td3(doc_number, nationality, surname,
                                               given_names, dob, sex, expiry))
        ocr_fields = {
            "passport_number": {"value": doc_number},
            "date_of_birth": {"value": dob},
            "surname": {"value": surname},
            "given_names": {"value": given_names},
            "nationality": {"value": nationality},
            "sex": {"value": sex},
            "date_of_expiry": {"value": expiry},
        }

    elif scenario == "not_found":
        # A document number that does NOT exist in the reference DB.
        doc_number = "PA9999999"
        surname = "UNKNOWN"
        given_names = "TRAVELLER"
        dob = "900101"
        nationality = "XXX"
        sex = "X"
        expiry = "330101"
        mrz = mrz_service.parse_mrz(_build_td3(doc_number, nationality, surname,
                                               given_names, dob, sex, expiry))
        ocr_fields = {
            "passport_number": {"value": doc_number},
            "date_of_birth": {"value": dob},
            "surname": {"value": surname},
            "given_names": {"value": given_names},
            "nationality": {"value": nationality},
            "sex": {"value": sex},
            "date_of_expiry": {"value": expiry},
        }

    elif scenario == "visa":
        ocr_text = (
            f"VISA\nVisa No. V123456\nSurname {surname}  Given names {given_names}\n"
            f"Passport {doc_number}\nType D\nEntries MULT\nDate of issue 240504\n"
            f"Date of expiry {expiry}\n"
        )

    if mrz is None and request.mrz_lines is None:
        mrz = mrz_service.parse_mrz(mrz_lines)

    # A failed MRZ checksum always raises risk (doctored / mis-read zone).
    if mrz is not None and not mrz.checksum_passed:
        risk_signals["invalid_mrz"] = True

    # ---- Run the normal sub-analyses ----
    expiry_passport = expiry_status(parse_iso(_yyyymmdd_to_iso(expiry)), settings.EXPIRING_SOON_DAYS)
    if expiry_passport["status"] == "expired":
        risk_signals["expired_passport"] = True
    elif expiry_passport["status"] == "expiring_soon":
        risk_signals["expiring_passport"] = True

    cross_check = crosscheck_service.validate(ocr_fields, mrz)
    if not cross_check.overall_consistent:
        risk_signals["ocr_mrz_mismatch"] = True

    # Face
    if face_score is None:
        face_result = face_service.FaceMatch(similar=False, score=0.0, status="no_face",
                                             message="Face photo not provided - face "
                                                     "verification not performed.",
                                             provided=face_service.FaceDetection(),
                                             reference=face_service.FaceDetection())
    elif face_score >= settings.FACE_REVIEW_THRESHOLD:
        face_result = face_service.FaceMatch(similar=True, score=face_score, status="match",
                                             message=f"Face match: {int(face_score*100)}% - PASS.",
                                             provided=face_service.FaceDetection(),
                                             reference=face_service.FaceDetection())
    elif face_score >= settings.FACE_MATCH_THRESHOLD:
        face_result = face_service.FaceMatch(similar=False, score=face_score, status="review",
                                             message=f"Face match: {int(face_score*100)}% - manual review.",
                                             provided=face_service.FaceDetection(),
                                             reference=face_service.FaceDetection())
    else:
        face_result = face_service.FaceMatch(similar=False, score=face_score, status="mismatch",
                                             message=f"Face match: {int(face_score*100)}% - identity mismatch.",
                                             provided=face_service.FaceDetection(),
                                             reference=face_service.FaceDetection())
    if face_result.status == "mismatch":
        risk_signals["face_mismatch"] = True
    if face_result.status == "no_face":
        risk_signals["face_low_quality"] = False  # not penalising absence explicitly

    # Reference DATABASE look-ups (passport / visa)
    passport_lookup = provider_service.get_passport_provider().lookup(doc_number)
    db_match = None
    if passport_lookup.found:
        if passport_lookup.anomaly:
            risk_signals["document_anomaly"] = True
        matched_fields, mismatched_fields = _compare_reference(
            {"surname": surname, "given_names": given_names,
             "full_name": f"{surname} {given_names}".strip(), "date_of_birth": dob,
             "nationality": nationality, "date_of_expiry": expiry,
             "issuing_country": nationality},
            passport_lookup, doc_number)
        db_match = _build_database_match(
            "CONFLICT" if mismatched_fields else "MATCH",
            doc_number, passport_lookup.to_dict(), matched_fields, mismatched_fields)
        if mismatched_fields:
            risk_signals["passport_field_mismatch"] = True
    else:
        risk_signals["passport_not_found"] = True
        db_match = _build_database_match("NOT_FOUND", doc_number, {}, [], [])

    visa_lookup = provider_service.get_visa_provider().lookup(doc_number)
    if visa_lookup.found and visa_lookup.status == "expired":
        risk_signals["expired_visa"] = True

    # Watchlist (reference DB table, not the in-memory list)
    wl = provider_service.get_watchlist_provider().check(
        document_number=doc_number, surname=surname, date_of_birth=dob)
    if wl.matched:
        if wl.category == "blacklist":
            risk_signals["blacklist"] = True
        else:
            risk_signals["watchlist_match"] = True

    # Tamper (heuristic default for demo scenarios)
    tamper_result = tamper_service.TamperResult()
    if "tamper_high" in risk_signals:
        tamper_result = tamper_service.TamperResult(
            overall_score=85, risk_level="high",
            signals=[tamper_service.TamperSignal("demo_scenario", 85, "high",
                                                 "Demo tamper scenario: inconsistency "
                                                 "between printed fields and MRZ.")],
            notes=["Demo scenario - heuristic tamper signal."])
    elif "tamper_medium" in risk_signals:
        tamper_result = tamper_service.TamperResult(
            overall_score=50, risk_level="medium",
            signals=[tamper_service.TamperSignal("demo_scenario", 50, "suspicious",
                                                 "Moderate demo anomaly signal.")],
            notes=["Demo scenario - heuristic tamper signal."])
    if tamper_result.risk_level == "high":
        risk_signals["tamper_high"] = True
    elif tamper_result.risk_level == "medium":
        risk_signals["tamper_medium"] = True

    # Duplicate identity (reference DB prior-traveller records)
    dup = provider_service.get_identity_provider().check(
        {"surname": surname, "given_names": given_names, "date_of_birth": dob,
         "nationality": nationality, "document_number": doc_number},
        face_score=face_score)
    if dup.is_duplicate:
        risk_signals["duplicate_identity"] = True

    # Risk
    risk = risk_service.score(risk_signals)

    passenger = _merge_fields(ocr_fields, mrz)
    passenger["full_name"] = f"{surname} {given_names}".strip()

    # Honest verdict for the demo scenario (still derived from data, not preset).
    verification_status, verification_reason = _derive_verdict(
        passenger, ocr_text, 0.9, mrz, risk, passport_lookup, risk_signals,
        db_match=db_match)

    return {
        "scenario": scenario,
        "document_type": request.document_type or "passport",
        "passenger": passenger,
        "verification_status": verification_status,
        "verification_reason": verification_reason,
        "confidence": _confidence_from(0.9),
        "ocr": {"text": ocr_text, "confidence": 0.9,
                "lines": [{"text": l, "conf": 0.9} for l in ocr_text.splitlines() if l]},
        "extracted_fields": ocr_fields,
        "mrz": mrz.as_dict() if mrz else None,
        "mrz_checksum_valid": bool(mrz and mrz.checksum_passed),
        "cross_check": cross_check.to_dict(),
        "tamper": tamper_result.to_dict(),
        "face": face_result.to_dict(),
        "expiry": expiry_passport,
        "watchlist": wl.to_dict(),
        "duplicate": dup.to_dict(),
        "passport": passport_lookup.to_dict(),
        "visa": visa_lookup.to_dict(),
        "database_match": db_match,
        "risk": risk.to_dict(),
        "data_source": DS_LABEL,
        "environment": DS_ENV,
        "backend": provider_service.backend_kind(),
        "source_provenance": _build_source_block([
            {"check": "passport", "provider": "PassportProvider",
             "table": "passport_records", "matched": passport_lookup.found},
            {"check": "visa", "provider": "VisaProvider",
             "table": "visa_records", "matched": visa_lookup.found},
            {"check": "watchlist", "provider": "WatchlistProvider",
             "table": "watchlist_records", "matched": wl.matched},
            {"check": "duplicate_identity", "provider": "IdentityProvider",
             "table": "identity_records", "matched": dup.is_duplicate},
        ]),
    }


def _build_source_block(checks: list[dict]) -> dict:
    """Describe which data source each verification check queried."""
    return {
        "backend": provider_service.backend_kind(),
        "label": DS_LABEL,
        "environment": DS_ENV,
        "is_real_data": False,
        "checks": checks,
    }


def _yyyymmdd_to_iso(yymmdd: str) -> str:
    if not yymmdd or len(yymmdd) != 6 or not yymmdd.isdigit():
        return ""
    yy = int(yymmdd[0:2])
    year = 2000 + yy if yy < 50 else 1900 + yy
    return f"{year}-{yymmdd[2:4]}-{yymmdd[4:6]}"


def _build_td3(doc_num, country, surname, given, dob, sex, expiry, tamper=False):
    from .mrz import compute_check_digit
    if tamper:
        # doctor the passport number and fix nothing else -> checksum fails
        doc_check = str((compute_check_digit(doc_num) + 1) % 10)
    else:
        doc_check = str(compute_check_digit(doc_num))
    dob_check = str(compute_check_digit(dob))
    exp_check = str(compute_check_digit(expiry))
    personal = "0" + "<" * 13
    personal_check = str(compute_check_digit(personal))
    name_field = f"{surname}<<{given}"
    name_field = name_field + "<" * max(0, 39 - len(name_field))
    line1 = f"P<{country}{name_field}".ljust(44, "<")[:44]
    core = (doc_num.ljust(9, "<") + doc_check + country + dob + dob_check +
            sex + expiry + exp_check + personal + personal_check)
    comp = str(compute_check_digit(core))
    line2 = (core + comp).ljust(44, "<")[:44]
    return [line1, line2]


# ---------------------------------------------------------------------------
# Synthetic demo-document tamper analysis (Aadhaar / PAN / College ID)
# ---------------------------------------------------------------------------

# Each synthetic_id -> the generated card file, its doc type and the printed
# (ground-truth) identity that was rendered onto the card in gen_synthetic_docs.
# The ``tampered`` variants carry the controlled edits described in that script.
_SYNTHETIC_DOCS = {
    "aadhaar_valid": {"file": "synthetic_aadhaar_valid.png", "type": "aadhaar",
                      "label": "Aadhaar-style ID (original)",
                      "name": "ANANYA SHARMA", "id": "7654 1098 2310", "dob": "12-04-1994"},
    "aadhaar_tampered": {"file": "synthetic_aadhaar_tampered.png", "type": "aadhaar",
                         "label": "Aadhaar-style ID (edited)",
                         "name": "ROHAN VERMA", "id": "7654 1098 2319", "dob": "01-01-1999"},
    "pan_valid": {"file": "synthetic_pan_valid.png", "type": "pan",
                  "label": "PAN-style ID (original)",
                  "name": "KIRAN MEHTA", "id": "BKMPS4892L", "dob": "22-08-1991"},
    "pan_tampered": {"file": "synthetic_pan_tampered.png", "type": "pan",
                     "label": "PAN-style ID (edited)",
                     "name": "DEV PATEL", "id": "BKMPS4892X", "dob": "15-06-1995"},
    "college_valid": {"file": "synthetic_collegeid_valid.png", "type": "college",
                      "label": "College ID (original)",
                      "name": "PRIYA NAIR", "id": "2023CS0142", "dob": ""},
    "college_tampered": {"file": "synthetic_collegeid_tampered.png", "type": "college",
                         "label": "College ID (edited)",
                         "name": "SAHIL KHAN", "id": "2023CS0714", "dob": ""},
}


def synthetic_sample_file(synthetic_id: str) -> str:
    """Return the sample image filename for a synthetic doc id (or '')."""
    cfg = _SYNTHETIC_DOCS.get(synthetic_id)
    return cfg["file"] if cfg else ""


def _noop_face():
    return face_service.FaceMatch(
        similar=False, score=0.0, status="no_face",
        message="Synthetic identity card - face verification not performed.",
        provided=face_service.FaceDetection(),
        reference=face_service.FaceDetection())


def verify_synthetic_document(synthetic_id: str) -> dict:
    """Run the synthetic-document tamper / anomaly analysis.

    Loads one of the FICTIONAL demo cards (Aadhaar / PAN / College ID), runs the
    OCR pipeline for free-text + field extraction, then the image-structure and
    field-consistency anomaly detector.  The anomaly signals are folded into the
    shared risk engine so the UI renders a LOW / VERIFIED or HIGH / HIGH RISK
    verdict with explainable reasons.

    These cards are synthetic - no real identity document is involved.
    """
    cfg = _SYNTHETIC_DOCS.get(synthetic_id)
    if not cfg:
        raise VerificationError(f"Unknown synthetic document id: {synthetic_id}")

    path = os.path.join(str(settings.SAMPLE_DIR), cfg["file"])
    img = _load_image(path)

    # --- OCR (free text + structured fields) ---
    ocr_result = ocr_service.run_ocr(img)
    ocr_text = ocr_result.text
    ocr_fields = ocr_service.extract_fields(ocr_text)
    ocr_lines_payload = ocr_result.to_dict().get("lines", [])

    # --- Heuristic tamper / anomaly analysis ---
    anomaly = anomaly_service.analyze(img, ocr_text, ocr_fields)
    tamper = anomaly.tamper

    # Fold the anomaly signals into the shared risk engine.
    risk_signals: dict = dict(anomaly.risk_signals)
    if tamper.risk_level == "high":
        risk_signals["tamper_high"] = True
    elif tamper.risk_level == "medium":
        risk_signals["tamper_medium"] = True

    risk = risk_service.score(risk_signals)
    # Surface the tamper explanations in the risk-reasons block too.
    for reason in anomaly.reasons:
        if reason not in risk.reasons:
            risk.reasons.append(reason)

    # Honest status for a synthetic card: driven by the tamper/anomaly result
    # (these cards are not present in the passport registry by design).
    if risk.level == "HIGH":
        verification_status, verification_reason = (
            "NOT_VERIFIED", "; ".join(risk.reasons) or "Strong tampering indicators detected.")
    elif risk.level == "MEDIUM":
        verification_status, verification_reason = (
            "UNVERIFIED", "Uncertain; manual review required.")
    else:
        verification_status, verification_reason = (
            "VERIFIED", "No tampering or anomaly indicators detected on the synthetic card.")

    passenger = _merge_fields(ocr_fields, None) or {}
    passenger["full_name"] = cfg["name"]
    passenger["document_number"] = cfg["id"]
    if cfg["dob"]:
        passenger["date_of_birth"] = cfg["dob"]
    passenger["synthetic_label"] = cfg["label"]

    return {
        "scenario": "synthetic_document",
        "document_type": cfg["type"],
        "synthetic_label": cfg["label"],
        "passenger": passenger,
        "verification_status": verification_status,
        "verification_reason": verification_reason,
        "confidence": _confidence_from(ocr_result.confidence),
        "ocr": {"text": ocr_text, "confidence": ocr_result.confidence,
                "lines": ocr_lines_payload},
        "extracted_fields": ocr_fields,
        "mrz": None,
        "mrz_checksum_valid": False,
        "cross_check": {"overall_consistent": True, "checks": [], "mismatches": []},
        "tamper": tamper.to_dict(),
        "anomaly": anomaly.to_dict(),
        "face": _noop_face().to_dict(),
        "expiry": {"status": "unknown", "days_left": None,
                   "explanation": "Expiry is not applicable to this synthetic identity card."},
        "watchlist": {"matched": False,
                      "reason": "No watchlist match. Not applicable to a synthetic identity-document demo.",
                      "source": "DEMO"},
        "duplicate": {"is_duplicate": False, "confidence": 0.0, "signals": [],
                      "explanation": "Duplicate-identity check not applicable to this synthetic card."},
        "passport": {"found": False, "document_number": "", "source": "DEMO"},
        "visa": {"found": False, "document_number": "", "status": "", "source": "DEMO"},
        "risk": risk.to_dict(),
        "data_source": DS_LABEL,
        "environment": DS_ENV,
        "backend": "synthetic-image",
        "source_provenance": {
            "backend": "synthetic-image",
            "label": DS_LABEL,
            "environment": DS_ENV,
            "is_real_data": False,
            "checks": [{
                "check": "document_anomaly", "provider": "DocumentAnomalyAnalyzer",
                "table": "image_heuristics", "matched": tamper.risk_level == "high",
            }],
        },
        "notes": [
            "Synthetic demo identity document - fictional, not a real "
            "Aadhaar / PAN / college ID.",
            "Tampering result is HEURISTIC (image-signal based), not forensic-grade.",
        ],
    }


# ---------------------------------------------------------------------------
# Full image-based verification
# ---------------------------------------------------------------------------

def verify_image(image_path: str,
                 reference_photo_path: Optional[str] = None,
                 provided_photo_path: Optional[str] = None,
                 document_type: str = "auto",
                 extra_attrs: Optional[dict] = None) -> dict:
    t_start = _now()
    timing: dict = {}
    risk_signals: dict = {}

    # Load the document image ONCE; the same array feeds OCR and tamper so it is
    # never decoded/processed twice.
    try:
        img = _load_image(image_path)
    except VerificationError:
        # Fall through to demo if image is unavailable but we have metadata
        img = None

    # ------------------------------------------------------------------
    # Independent, expensive stages are scheduled as soon as their inputs are
    # available. Gemini is started NOW so its (bounded) round-trip overlaps OCR:
    # it runs on a shared executor thread with a strict internal HTTP timeout, so
    # it can never block the pipeline. OCR runs on the main thread. Face + tamper
    # are inexpensive, so they run synchronously later - parallelising them would
    # add no measurable speed and would only complicate (and risk leaking) the
    # pipeline. Each async stage is joined with a bounded wait and degrades
    # gracefully.
    # ------------------------------------------------------------------
    # --- Gemini (advisory; never blocks) ---
    _t0 = _now()
    gemini_future = _GEMINI_POOL.submit(
        gemini_service.analyze_document,
        image_path or "",
        "",
        {},
        document_type=document_type,
    )
    timing["gemini_submit"] = _elapsed_since(_t0)

    # --- OCR (main thread; feeds MRZ / fields) ---
    _t0 = _now()
    ocr_lines_payload = []
    if img is not None:
        try:
            ocr_result = ocr_service.run_ocr(img)
            ocr_text = ocr_result.text
            ocr_lines_payload = ocr_result.to_dict().get("lines", [])
            ocr_fields = ocr_service.extract_fields(ocr_text)
            ocr_conf = ocr_result.confidence
        except Exception as exc:  # noqa: BLE001
            raise VerificationError(f"OCR pipeline failed: {exc}") from exc
    else:
        ocr_text = (extra_attrs or {}).get("ocr_text", "")
        ocr_fields = (extra_attrs or {}).get("extracted_fields", {})
        ocr_conf = 0.0
    timing["ocr"] = _elapsed_since(_t0)

    detected_type = ocr_service.detect_document_type(ocr_text)
    if document_type in ("auto", "", None):
        document_type = detected_type if detected_type != "unknown" else "passport"

    # --- MRZ ---
    _t0 = _now()
    mrz = mrz_service.extract_mrz_from_text(ocr_text)
    mrz_checksum_ok = bool(mrz and mrz.checksum_passed)
    timing["mrz"] = _elapsed_since(_t0)

    # --- Document image analysis (quality + supported-document presence) ---
    _t0 = _now()
    doc_analysis = document_analysis_service.analyze(
        img, ocr_text, mrz_present=bool(mrz),
        mrz_format=(mrz.format if mrz else ""))
    if img is not None:   # only penalise when we actually got an image
        if not doc_analysis.supported:
            risk_signals["document_type_suspect"] = True
        if doc_analysis.quality_grade == "poor":
            risk_signals["image_quality_low"] = True
    timing["document_analysis"] = _elapsed_since(_t0)

    # --- Cross validation ---
    _t0 = _now()
    cross_check = crosscheck_service.validate(ocr_fields, mrz)
    if not cross_check.overall_consistent:
        risk_signals["ocr_mrz_mismatch"] = True
    timing["cross_check"] = _elapsed_since(_t0)

    # --- Merge passenger record ---
    _t0 = _now()
    passenger = _merge_fields(ocr_fields, mrz)
    timing["merge"] = _elapsed_since(_t0)

    # --- Expiry ---
    _t0 = _now()
    expiry = passenger.get("date_of_expiry", "")
    expiry_iso = _yyyymmdd_to_iso(expiry)
    exp = expiry_status(parse_iso(expiry_iso), settings.EXPIRING_SOON_DAYS)
    if exp["status"] == "expired":
        risk_signals["expired_passport"] = True
    elif exp["status"] == "expiring_soon":
        risk_signals["expiring_passport"] = True
    timing["expiry"] = _elapsed_since(_t0)

    # --- Reference DATABASE look-ups (passport / visa / watchlist) ---
    # The storage backend (MongoDB or SQLite) is chosen by the provider factory.
    doc_no = passenger.get("document_number", "")

    _t0 = _now()
    passport_lookup = provider_service.get_passport_provider().lookup(doc_no)
    db_match = None
    if passport_lookup.found:
        # If the DB record says the document is invalid / flag, add an anomaly.
        if passport_lookup.anomaly:
            risk_signals["document_anomaly"] = True
        # Field-level comparison: a number-only match is not sufficient. If any
        # extracted identity field conflicts with the reference record, flag it.
        matched_fields, mismatched_fields = _compare_reference(
            passenger, passport_lookup, doc_no)
        db_match = _build_database_match(
            "CONFLICT" if mismatched_fields else "MATCH",
            doc_no, passport_lookup.to_dict(), matched_fields, mismatched_fields)
        if mismatched_fields:
            risk_signals["passport_field_mismatch"] = True
    else:
        # Document number absent from the reference DB -> passport_not_found.
        risk_signals["passport_not_found"] = True
        db_match = _build_database_match(
            "NOT_FOUND", doc_no, {}, [], [])

    visa_lookup = provider_service.get_visa_provider().lookup(doc_no)
    if visa_lookup.found and visa_lookup.status == "expired":
        risk_signals["expired_visa"] = True

    # Watchlist (reference DB table, not in-memory list)
    wl = provider_service.get_watchlist_provider().check(
        document_number=doc_no,
        surname=passenger.get("surname", ""),
        date_of_birth=passenger.get("date_of_birth", ""))
    if wl.matched:
        if wl.category == "blacklist":
            risk_signals["blacklist"] = True
        else:
            risk_signals["watchlist_match"] = True

    if not mrz_checksum_ok:
        risk_signals["invalid_mrz"] = True
    timing["database"] = _elapsed_since(_t0)

    # --- Tamper (inexpensive; runs synchronously) ---
    _t0 = _now()
    if img is not None:
        tamper_result = tamper_service.analyze(img)
    else:
        tamper_result = tamper_service.TamperResult()
    if tamper_result.risk_level == "high":
        risk_signals["tamper_high"] = True
    elif tamper_result.risk_level == "medium":
        risk_signals["tamper_medium"] = True
    timing["tamper"] = _elapsed_since(_t0)

    # --- Face (inexpensive; runs synchronously, skipped without photos) ---
    _t0 = _now()
    if reference_photo_path and provided_photo_path:
        face_result = _run_face_match(reference_photo_path, provided_photo_path)
    else:
        face_result = face_service.FaceMatch(
            similar=False, score=0.0, status="no_face",
            message="Face photo not provided - face verification not performed.",
            provided=face_service.FaceDetection(),
            reference=face_service.FaceDetection())
    if face_result.status == "mismatch":
        risk_signals["face_mismatch"] = True
    elif face_result.status == "no_face":
        risk_signals["face_low_quality"] = False
    timing["face"] = _elapsed_since(_t0)

    # --- Liveness (live-camera captures only; honest passive anti-spoof) ---
    _t0 = _now()
    _method = (extra_attrs or {}).get("method", "upload")
    live_photo_path = (extra_attrs or {}).get("live_photo_path") or ""
    if _method == "live_camera" and live_photo_path and os.path.exists(live_photo_path):
        try:
            liveness_result = liveness_service.check_liveness(_load_image(live_photo_path))
        except Exception:  # noqa: BLE001 - never let liveness break the pipeline
            liveness_result = {
                "status": "unknown", "confidence": 0.0, "scores": {},
                "note": "Liveness could not be assessed because the live image "
                        "was unavailable."}
    else:
        liveness_result = {
            "status": "not_applicable", "confidence": 0.0, "scores": {},
            "note": "Liveness applies only to live-camera captures; a static "
                    "uploaded image cannot prove liveness."}
    if liveness_result.get("status") == "spoof_suspected":
        risk_signals["liveness_not_live"] = True
    timing["liveness"] = _elapsed_since(_t0)

    # Duplicate identity (reference DB prior-traveller records). Depends on the
    # face result, so it must run after face verification.
    _t0 = _now()
    dup = provider_service.get_identity_provider().check(
        {"surname": passenger.get("surname", ""),
         "given_names": passenger.get("given_names", ""),
         "date_of_birth": passenger.get("date_of_birth", ""),
         "nationality": passenger.get("nationality", ""),
         "document_number": doc_no},
        face_score=face_result.score if face_result.status != "no_face" else None)
    if dup.is_duplicate:
        risk_signals["duplicate_identity"] = True
    timing["database"] += _elapsed_since(_t0)

    # --- Gemini result (bounded join so it can never block the pipeline) ---
    _t0 = _now()
    gemini_timeout = max(1.0, float(getattr(settings, "GEMINI_TIMEOUT_S", 6) or 6))
    try:
        ai_assist = gemini_future.result(timeout=gemini_timeout + 1.0)
    except FutureTimeout:
        ai_assist = gemini_service.unavailable_payload(
            f"AI-assisted analysis timed out after {gemini_timeout:.0f}s and was "
            "skipped. Verification completed on the deterministic checks.")
    except Exception:  # noqa: BLE001 - Gemini must never break verification
        ai_assist = gemini_service.unavailable_payload(
            "AI-assisted analysis failed and was skipped. Verification "
            "completed on the deterministic checks.")
    timing["gemini"] = _elapsed_since(_t0)

    # --- Risk ---
    _t0 = _now()
    risk = risk_service.score(risk_signals)
    timing["risk"] = _elapsed_since(_t0)

    # --- Honest verdict: never VERIFIED on upload success alone ---
    verification_status, verification_reason = _derive_verdict(
        passenger, ocr_text, ocr_conf, mrz, risk, passport_lookup, risk_signals,
        db_match=db_match)
    confidence = _confidence_from(ocr_conf)

    timing["total"] = _elapsed_since(t_start)
    _log_timing(timing)

    return {
        "scenario": "image",
        "ai_assist": ai_assist,
        "document_type": document_type,
        "passenger": passenger,
        "verification_status": verification_status,
        "verification_reason": verification_reason,
        "confidence": confidence,
        "ocr": {"text": ocr_text, "confidence": ocr_conf,
                "lines": ocr_lines_payload},
        "extracted_fields": ocr_fields,
        "mrz": mrz.as_dict() if mrz else None,
        "mrz_checksum_valid": mrz_checksum_ok,
        "cross_check": cross_check.to_dict(),
        "document_analysis": doc_analysis.to_dict(),
        "liveness": liveness_result,
        "tamper": tamper_result.to_dict(),
        "face": face_result.to_dict(),
        "expiry": exp,
        "watchlist": wl.to_dict(),
        "duplicate": dup.to_dict(),
        "passport": passport_lookup.to_dict(),
        "visa": visa_lookup.to_dict(),
        "database_match": db_match,
        "risk": risk.to_dict(),
        "timing": timing,
        "data_source": DS_LABEL,
        "environment": DS_ENV,
        "backend": provider_service.backend_kind(),
        "source_provenance": _build_source_block([
            {"check": "passport", "provider": "PassportProvider",
             "table": "passport_records", "matched": passport_lookup.found},
            {"check": "visa", "provider": "VisaProvider",
             "table": "visa_records", "matched": visa_lookup.found},
            {"check": "watchlist", "provider": "WatchlistProvider",
             "table": "watchlist_records", "matched": wl.matched},
            {"check": "duplicate_identity", "provider": "IdentityProvider",
             "table": "identity_records", "matched": dup.is_duplicate},
        ]),
    }
