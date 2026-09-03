"""Document image analysis: quality/readability grading + supported-document check.

This is a deterministic computer-vision layer that answers two questions a border
system must ask *before* trusting an uploaded image:

  1. Is the image of an acceptable quality to be read reliably?
     (blur / sharpness / illumination / resolution / contrast / saturation)
  2. Does the image plausibly contain a *supported* travel document, rather than
     an arbitrary photo, a blank page, or an unrelated image?

It deliberately does NOT certify authenticity (that is the tamper/authenticity
layer's job) and it does NOT assume an arbitrary upload is a passport.  The
output is a structured, explainable result the risk/decision layer can consume.

The heuristics below are robust and image-size aware; they are not a learned
model, so there is no training step and no underlying data-dependency.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import cv2

# OCR-relevant label keywords that indicate a travel-document layout.  Presence
# of any of these (even without a parsed MRZ) is strong evidence the image is a
# supported document rather than an unrelated photo.
_DOC_LABELS = re.compile(
    r"passport|passeport|reiseausweis|visa|visto|nationality|date\s+of\s+birth|"
    r"date\s+of\s+expiry|surname|given\s+names|passport\s+no|document\s+no|"
    r"dob\b|expiry|issuing\s+country",
    re.IGNORECASE,
)

# The three values below follow the ICAO MRZ alphabets.  A run of 2-3 such lines is
# a strong, layout-invariant signal of a travel document (an unrelated photo rarely
# contains two 30+ char lines drawn only from letters/digits/'<').
_MRZ_RE = re.compile(r"^[A-Z0-9<]{20,}\s*$")
_MRZ_HEADS = {"P", "I", "V"}


@dataclass
class DocumentAnalysisResult:
    supported: bool                       # does the image plausibly hold a supported doc?
    doc_type: str = "unknown"             # passport | visa | id | unknown
    support_reasons: list = field(default_factory=list)
    quality_grade: str = "poor"           # good | moderate | poor
    quality_score: float = 0.0            # 0-100 (higher = better quality)
    readability: bool = False             # can the image be read reliably?
    scores: dict = field(default_factory=dict)   # per-attribute 0-100 (higher = better)

    def to_dict(self) -> dict:
        return {
            "supported": self.supported,
            "doc_type": self.doc_type,
            "support_reasons": self.support_reasons,
            "quality_grade": self.quality_grade,
            "quality_score": round(self.quality_score, 1),
            "readability": self.readability,
            "scores": {k: round(v, 1) for k, v in self.scores.items()},
        }


def _to_gray(matrix: np.ndarray) -> np.ndarray:
    if matrix is None or matrix.size == 0:
        return None
    if matrix.ndim == 3:
        return cv2.cvtColor(matrix, cv2.COLOR_BGR2GRAY)
    return matrix


def _bounded(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, v)))


# ---------------------------------------------------------------------------
# Per-attribute quality measures (all return 0-100 where higher = better)
# ---------------------------------------------------------------------------

def _blur_score(gray: np.ndarray) -> float:
    """Sharpness via variance of the Laplacian, normalised for resolution.

    A crisp document (MRZ text) yields a high local-gradient variance; a soft /
    motion-blurred image yields a low one.  We resize to a common width so the
    metric is comparable across upload sizes.
    """
    h, w = gray.shape
    if h == 0 or w == 0:
        return 0.0
    scale = 500.0 / max(h, w)
    small = cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))),
                       interpolation=cv2.INTER_AREA) if scale < 1 else gray
    lap = cv2.Laplacian(small, cv2.CV_64F)
    var = float(lap.var())
    # Empirically: a clean passport MRZ gets var ~ 400-1200; a blurry frame < 100.
    return _bounded(var / 9.0)


def _illumination_score(gray: np.ndarray) -> float:
    mean = float(gray.mean())
    # Ideal ~ 120-160. Penalise too dark (<40) or blown out (>220).
    if mean < 40 or mean > 220:
        return _bounded(max(0.0, (100 - (abs(mean - 130) - 90)) * 1.2))
    # Distance from the ideal mid-range; 100 at ~130, decaying on either side.
    dist = abs(mean - 130.0)
    return _bounded(100.0 - dist * 1.1)


def _contrast_score(gray: np.ndarray) -> float:
    std = float(gray.std())
    # std ~45-80 is healthy for a scanned/photo document.
    return _bounded(std * 1.4)


def _resolution_score(gray: np.ndarray) -> float:
    h, w = gray.shape
    min_dim = min(h, w)
    if min_dim >= 800:
        return 100.0
    if min_dim >= 500:
        return 70.0
    if min_dim >= 300:
        return 45.0
    return _bounded(min_dim / 3.0)


def _saturation_score(matrix: np.ndarray) -> float:
    """Colour saturation; a document's photo adds a little, but high saturation is
    a soft heuristic for unnatural filters.  Mid-range is ideal."""
    if matrix.ndim != 3:
        return 75.0  # greyscale documents are fine
    hsv = cv2.cvtColor(matrix, cv2.COLOR_BGR2HSV)
    sat = float(hsv[:, :, 1].mean())
    # Typical scan ~15-35. Very saturated (>80) suggests un-natural enhancement.
    if sat > 80:
        return 40.0
    return _bounded(100.0 - abs(sat - 35.0) * 0.9)


# ---------------------------------------------------------------------------
# Supported-document detection
# ---------------------------------------------------------------------------

def _detect_doc_type(ocr_text: str, mrz_format: str = "") -> str:
    low = (ocr_text or "").lower()
    if mrz_format == "TD3" or ("passport" in low) or ("passeport" in low):
        return "passport"
    if mrz_format in ("TD1", "TD2") or ("visa" in low) or ("visto" in low):
        return "visa"
    if _DOC_LABELS.search(ocr_text or ""):
        return "id"
    return "unknown"


def _has_mrz_layout(ocr_text: str) -> tuple[bool, str]:
    """Return (found, mrz_format) by scanning OCR text for 2-3 MRZ-like lines."""
    lines = [ln.strip() for ln in (ocr_text or "").splitlines() if ln.strip()]
    for window in (3, 2):
        for i in range(len(lines) - window + 1):
            group = lines[i:i + window]
            if not all(_MRZ_RE.match(ln) and len(ln) >= 20 for ln in group):
                continue
            fmt = ""
            if len(group) == 2 and len(group[0]) == 44:
                fmt = "TD3"
            elif len(group) == 3 and len(group[0]) == 30:
                fmt = "TD1"
            elif len(group) == 2 and len(group[0]) == 36:
                fmt = "TD2"
            if not fmt and group[0][0] in _MRZ_HEADS:
                fmt = "TD3"
            return True, fmt
    return False, ""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def analyze(matrix: np.ndarray, ocr_text: str = "",
            mrz_present: bool = False, mrz_format: str = "") -> DocumentAnalysisResult:
    """Grade image quality and detect whether a supported document is present."""
    if matrix is None or matrix.size == 0:
        return DocumentAnalysisResult(supported=False, doc_type="unknown",
                                      support_reasons=["No image was provided."])

    gray = _to_gray(matrix)
    if gray is None or gray.size == 0:
        return DocumentAnalysisResult(supported=False, doc_type="unknown",
                                      support_reasons=["Image could not be decoded."])

    scores = {
        "sharpness": _blur_score(gray),
        "illumination": _illumination_score(gray),
        "contrast": _contrast_score(gray),
        "resolution": _resolution_score(gray),
        "saturation": _saturation_score(matrix),
    }
    quality_score = _bounded(
        0.38 * scores["sharpness"] + 0.22 * scores["illumination"]
        + 0.16 * scores["contrast"] + 0.16 * scores["resolution"]
        + 0.08 * scores["saturation"])
    quality_grade = ("good" if quality_score >= 68 else
                     "moderate" if quality_score >= 45 else "poor")
    readability = quality_grade != "poor"

    # --- Supported-document detection ---
    reasons = []
    doc_type = _detect_doc_type(ocr_text, mrz_format)

    if mrz_present or (_has_mrz_layout(ocr_text)[0]):
        reasons.append("A machine-readable (MRZ) zone was detected.")
        if doc_type == "unknown":
            doc_type = "passport"
    if _DOC_LABELS.search(ocr_text or ""):
        tag = "passport" if re.search(r"passport|passeport", (ocr_text or ""), re.I) else \
              "visa" if re.search(r"visa|visto", (ocr_text or ""), re.I) else "identity"
        reasons.append(f"Document layout keywords ({tag}) present in the OCR text.")
        if doc_type == "unknown":
            doc_type = tag

    supported = bool(reasons)
    if not supported:
        reasons.append(
            "No supported document layout found: no MRZ zone and no passport/visa "
            "field labels in the OCR text. This may be an unrelated image, a blank "
            "page, or a document type outside the supported set.")

    return DocumentAnalysisResult(
        supported=supported, doc_type=doc_type, support_reasons=reasons,
        quality_grade=quality_grade, quality_score=quality_score,
        readability=readability, scores=scores)
