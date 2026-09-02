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

import os
from typing import Optional

import numpy as np
import cv2

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
    if passport_lookup.found:
        if passport_lookup.anomaly:
            risk_signals["document_anomaly"] = True
    else:
        risk_signals["passport_not_found"] = True

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

    return {
        "scenario": scenario,
        "document_type": request.document_type or "passport",
        "passenger": passenger,
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
    risk_signals: dict = {}

    try:
        img = _load_image(image_path)
    except VerificationError:
        # Fall through to demo if image is unavailable but we have metadata
        img = None

    # --- OCR ---
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

    detected_type = ocr_service.detect_document_type(ocr_text)
    if document_type in ("auto", "", None):
        document_type = detected_type if detected_type != "unknown" else "passport"

    # --- MRZ ---
    mrz = mrz_service.extract_mrz_from_text(ocr_text)
    mrz_checksum_ok = bool(mrz and mrz.checksum_passed)

    # --- Cross validation ---
    cross_check = crosscheck_service.validate(ocr_fields, mrz)
    if not cross_check.overall_consistent:
        risk_signals["ocr_mrz_mismatch"] = True

    # --- Tamper ---
    if img is not None:
        tamper_result = tamper_service.analyze(img)
    else:
        tamper_result = tamper_service.TamperResult()
    if tamper_result.risk_level == "high":
        risk_signals["tamper_high"] = True
    elif tamper_result.risk_level == "medium":
        risk_signals["tamper_medium"] = True

    # --- Face ---
    if reference_photo_path and provided_photo_path:
        try:
            ref_img = _load_image(reference_photo_path)
            prov_img = _load_image(provided_photo_path)
            face_result = face_service.match_faces(
                ref_img, prov_img,
                threshold=settings.FACE_MATCH_THRESHOLD,
                review_threshold=settings.FACE_REVIEW_THRESHOLD)
        except Exception:  # noqa: BLE001
            face_result = face_service.FaceMatch(
                similar=False, score=0.0, status="no_face",
                message="Face verification could not run on the provided images.",
                provided=face_service.FaceDetection(),
                reference=face_service.FaceDetection())
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

    # --- Merge passenger record ---
    passenger = _merge_fields(ocr_fields, mrz)

    # --- Expiry ---
    expiry = passenger.get("date_of_expiry", "")
    expiry_iso = _yyyymmdd_to_iso(expiry)
    exp = expiry_status(parse_iso(expiry_iso), settings.EXPIRING_SOON_DAYS)
    if exp["status"] == "expired":
        risk_signals["expired_passport"] = True
    elif exp["status"] == "expiring_soon":
        risk_signals["expiring_passport"] = True

    # --- Reference DATABASE look-ups (passport / visa / watchlist / duplicate) ---
    # The storage backend (MongoDB or SQLite) is chosen by the provider factory.
    doc_no = passenger.get("document_number", "")

    passport_lookup = provider_service.get_passport_provider().lookup(doc_no)
    if passport_lookup.found:
        # If the DB record says the document is invalid / flag, add an anomaly.
        if passport_lookup.anomaly:
            risk_signals["document_anomaly"] = True
    else:
        # Document number absent from the reference DB -> passport_not_found.
        risk_signals["passport_not_found"] = True

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

    # Duplicate identity (reference DB prior-traveller records)
    dup = provider_service.get_identity_provider().check(
        {"surname": passenger.get("surname", ""),
         "given_names": passenger.get("given_names", ""),
         "date_of_birth": passenger.get("date_of_birth", ""),
         "nationality": passenger.get("nationality", ""),
         "document_number": doc_no},
        face_score=face_result.score if face_result.status != "no_face" else None)
    if dup.is_duplicate:
        risk_signals["duplicate_identity"] = True
    if not mrz_checksum_ok:
        risk_signals["invalid_mrz"] = True

    # --- Risk ---
    risk = risk_service.score(risk_signals)

    return {
        "scenario": "image",
        "document_type": document_type,
        "passenger": passenger,
        "ocr": {"text": ocr_text, "confidence": ocr_conf,
                "lines": ocr_lines_payload},
        "extracted_fields": ocr_fields,
        "mrz": mrz.as_dict() if mrz else None,
        "mrz_checksum_valid": mrz_checksum_ok,
        "cross_check": cross_check.to_dict(),
        "tamper": tamper_result.to_dict(),
        "face": face_result.to_dict(),
        "expiry": exp,
        "watchlist": wl.to_dict(),
        "duplicate": dup.to_dict(),
        "passport": passport_lookup.to_dict(),
        "visa": visa_lookup.to_dict(),
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
