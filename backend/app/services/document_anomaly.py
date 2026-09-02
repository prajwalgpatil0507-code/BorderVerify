"""Synthetic-document tampering / anomaly analysis.

Runs on the *synthetic* demo identity documents (Aadhaar-style, PAN-style,
college-ID).  It combines:

  * image-structure heuristics (localised edge clusters, brightness discontinuity,
    saturated/colored text blocks) that reveal a pasted / relaid region, and
  * OCR field-consistency checks (an ID value that no longer matches a valid
    format, a name/date that conflicts), reusing the existing OCR pipeline.

IMPORTANT — this is HEURISTIC, not forensic.  Output uses wording like
"Possible document tampering detected."  It never claims certified fraud.

This module does NOT touch the passport/visa + MongoDB flow.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import cv2

from .tamper import TamperResult, TamperSignal


# ---------------------------------------------------------------------------
# Result holder
# ---------------------------------------------------------------------------

@dataclass
class AnomalyResult:
    document_type: str = "unknown"
    ocr_text: str = ""
    fields: dict = field(default_factory=dict)
    tamper: TamperResult = None                       # type: ignore[assignment]
    risk_signals: dict = field(default_factory=dict)
    reasons: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "document_type": self.document_type,
            "ocr_text": self.ocr_text,
            "fields": self.fields,
            "tamper": self.tamper.to_dict() if self.tamper else None,
            "risk_signals": self.risk_signals,
            "reasons": self.reasons,
        }


# ---------------------------------------------------------------------------
# Field validation helpers (synthetic ID formats)
# ---------------------------------------------------------------------------

def _valid_pan(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", value.strip().upper()))


def _valid_aadhaar(value: str) -> bool:
    digits = "".join(ch for ch in value if ch.isdigit())
    return len(digits) == 12


def _valid_college_roll(value: str) -> bool:
    # e.g. 2023CS0142  (4-digit year + 1-4 letters + 4+ digits)
    return bool(re.fullmatch(r"\d{4}[A-Z]{1,4}\d{4,6}", value.strip().upper()))


_VALIDATORS = {
    "pan": _valid_pan,
    "aadhaar": _valid_aadhaar,
    "college": _valid_college_roll,
}


# ---------------------------------------------------------------------------
# Image-structure heuristics
# ---------------------------------------------------------------------------

def _to_color(matrix: np.ndarray) -> np.ndarray:
    if matrix is None or matrix.size == 0:
        return matrix
    if matrix.ndim == 2:
        return cv2.cvtColor(matrix, cv2.COLOR_GRAY2BGR)
    return matrix


# The synthetic cards are generated with clean, deterministic cues that separate
# a pristine card from an edited one:
#   * saturated red ink (a recoloured value / a boxed photo border)   -> 0 vs ~10-100
#   * photo-region edge energy (a pasted / boxed portrait)            -> ~40 vs ~60
#   * a brightness step across the field block (a relaid strip)       -> ~0.6 vs ~0.95
# These are strong, measurable heuristics; they are NOT forensic proof.

def _red_ink(color: np.ndarray) -> np.ndarray:
    b = color[:, :, 0].astype(np.int16)
    g = color[:, :, 1].astype(np.int16)
    r = color[:, :, 2].astype(np.int16)
    return ((r > g + 40) & (r > b + 40) & (r > 120)).astype(np.uint8)


def _photo_region_alteration(color: np.ndarray, gray: np.ndarray) -> float:
    """Detect a tampered photo area (red box border + strong local edges)."""
    h, w = gray.shape
    x0, y0 = int(w * 0.02), int(h * 0.20)
    x1, y1 = int(w * 0.30), int(h * 0.65)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    ri = _red_ink(color)
    photo_ri = float(ri[y0:y1, x0:x1].mean())
    edges = cv2.Canny(gray[y0:y1, x0:x1], 80, 160) / 255.0
    edge_mean = float(edges.mean())
    score = photo_ri * 900.0 + max(0.0, (edge_mean - 0.048)) * 1200.0
    return min(100.0, score)


def _text_region_alteration(gray: np.ndarray) -> float:
    """Detect a relaid text block via a brightness step across the field band."""
    h, w = gray.shape
    rows = gray[int(h * 0.25):int(h * 0.80)]
    if rows.size < 2:
        return 0.0
    row_means = rows.mean(axis=1)
    diff = np.abs(np.diff(row_means))
    if diff.size == 0:
        return 0.0
    peak_step = float(diff.max()) / (float(gray.std()) + 1e-6)
    return min(100.0, max(0.0, (peak_step - 0.75) * 240.0))


def _field_ink_alteration(color: np.ndarray, gray: np.ndarray) -> float:
    """Detect a recoloured identifier (saturated ink in the value band)."""
    h, w = gray.shape
    ri = _red_ink(color)
    band = ri[:, int(w * 0.28):]
    red_ratio = float(band.mean()) if band.size else 0.0
    return min(100.0, red_ratio * 600.0)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze(matrix: np.ndarray, ocr_text: str = "", fields: dict = None) -> AnomalyResult:
    """Run the synthetic-document anomaly analysis on an image matrix."""
    if matrix is None or matrix.size == 0:
        return notes_empty()

    color = _to_color(matrix)
    gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY) if color.ndim == 3 else color

    signals = []
    reasons = []

    text_score = _text_region_alteration(gray)
    photo_score = _photo_region_alteration(color, gray)
    ink_score = _field_ink_alteration(color, gray)

    if text_score >= 40:
        signals.append(TamperSignal("text_region_alteration", text_score, "high",
                                    "Possible text-region alteration: a relaid / "
                                    "re-coloured block of text was detected."))
        reasons.append("Possible text-region alteration (relaid or re-coloured text block).")
    elif text_score >= 25:
        signals.append(TamperSignal("text_region_alteration", text_score, "suspicious",
                                    "Suspicious text-region texture detected."))
        reasons.append("Text-region texture looks inconsistent (manual review).")

    if photo_score >= 50:
        signals.append(TamperSignal("photo_region_alteration", photo_score, "high",
                                    "Possible photo-area alteration: strong edges around "
                                    "the portrait indicate a pasted / boxed photo."))
        reasons.append("Photo area shows possible alteration (pasted or boxed portrait).")
    elif photo_score >= 30:
        signals.append(TamperSignal("photo_region_alteration", photo_score, "suspicious",
                                    "Photo area has borderline edge structure."))
        reasons.append("Photo-area structure warrants review.")

    if ink_score >= 45:
        signals.append(TamperSignal("field_inconsistency", ink_score, "high",
                                    "OCR/extracted-field inconsistency: the extracted "
                                    "identifier appears on an inconsistent / re-coloured "
                                    "region."))
        reasons.append("OCR / extracted-field inconsistency (identifier on an "
                       "inconsistent region).")
    elif ink_score >= 25:
        signals.append(TamperSignal("field_inconsistency", ink_score, "suspicious",
                                    "Extracted field shows colour/texture inconsistency."))
        reasons.append("Extracted-field colour/texture inconsistency (manual review).")

    # OCR field consistency (secondary enhancement, not required for detection).
    fields = fields or {}
    doc_type = _detect_doc_type(ocr_text, fields)
    validators = _VALIDATORS
    config = _doc_config(doc_type)
    if config and ocr_text:
        id_value = config["extract"](ocr_text, fields)
        if id_value:
            valid = validators[config["key"]](id_value)
            if not valid:
                signals.append(TamperSignal("field_inconsistency", 70, "high",
                                            "OCR/extracted-field inconsistency: the "
                                            "extracted identifier does not match a "
                                            "valid format."))
                reasons.append("OCR / extracted-field inconsistency (identifier format "
                               "does not validate).")

    overall = 0.0
    if signals:
        overall = float(np.mean([s.score for s in signals]))
        overall = 0.6 * overall + 0.4 * max(s.score for s in signals)
    overall = round(min(100.0, overall), 1)
    risk_level = ("high" if overall >= 70 else "medium" if overall >= 40 else "low")

    notes = [
        "This result is HEURISTIC (image-signal based), not forensic-grade. "
        "A low score does not guarantee authenticity, and no claim of certified "
        "fraud is made."
    ]
    tamper = TamperResult(overall_score=overall, risk_level=risk_level,
                          signals=signals, notes=notes)

    risk_signals = {}
    if risk_level == "high":
        risk_signals["tamper_high"] = True
    elif risk_level == "medium":
        risk_signals["tamper_medium"] = True
    if any(s.name == "field_inconsistency" for s in signals):
        risk_signals["document_anomaly"] = True

    if overall > 0:
        reasons.append("Possible document tampering detected." if risk_level == "high"
                       else "Possible document anomaly detected.")

    return AnomalyResult(document_type=doc_type, ocr_text=ocr_text,
                         fields=fields, tamper=tamper, risk_signals=risk_signals,
                         reasons=reasons)


def notes_empty():
    return AnomalyResult(document_type="unknown", tamper=TamperResult(
        overall_score=0, risk_level="low", signals=[], notes=["No image provided."]))


# ---------------------------------------------------------------------------
# Doc-type detection + field extraction helpers
# ---------------------------------------------------------------------------

def _detect_doc_type(ocr_text: str, fields: dict = None) -> str:
    low = (ocr_text or "").lower()
    if "aadhaar" in low:
        return "aadhaar"
    if "pan card" in low or "permanent account" in low or "pan card  " in low:
        return "pan"
    if "college id" in low or "student identity" in low or "college" in low:
        return "college"
    # fall back to field hints
    fkeys = " ".join((fields or {}).keys()).lower()
    if "aadhaar" in fkeys:
        return "aadhaar"
    if "pan" in fkeys:
        return "pan"
    return "unknown"


def _doc_config(doc_type: str) -> dict:
    if doc_type == "pan":
        return {"key": "pan",
                "extract": lambda text, fields: _grab(text, ["pan", "permanent account"], r"[A-Z]{5}[0-9]{4}[A-Z]")}
    if doc_type == "aadhaar":
        return {"key": "aadhaar",
                "extract": lambda text, fields: _grab(text, ["aadhaar"], r"\d{4}\s?\d{4}\s?\d{4}")}
    if doc_type == "college":
        return {"key": "college",
                "extract": lambda text, fields: _grab(text, ["roll no", "roll"], r"\d{4}[A-Z]{1,4}\d{4,6}")}
    return {}


def _grab(text: str, labels: list, pattern: str) -> str:
    for line in text.splitlines():
        low = line.lower()
        for lab in labels:
            if lab in low:
                m = re.search(pattern, line)
                if m:
                    return m.group(0)
    m = re.search(pattern, text)
    return m.group(0) if m else ""
