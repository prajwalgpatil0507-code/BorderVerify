"""OCR pipeline using RapidOCR (ONNX-based, offline-capable).

The engine is loaded lazily and isolated so that any runtime problem inside the
ONNX inference does not crash the application process - failures surface as an
``OcrEngineError`` that the API layer can translate into a structured response.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from typing import Optional

import numpy as np
import cv2

from ..config import settings


class OcrEngineError(RuntimeError):
    """Raised when the OCR engine cannot be initialised or run."""


class OcrResult:
    """A parsed block of OCR output."""

    def __init__(self, text: str, lines: list, words: list, confidence: float):
        self.text = text                # full text with newlines
        self.lines = lines              # list of {"text", "conf", "bbox"}
        self.words = words              # every word with box
        self.confidence = confidence    # mean confidence 0..1

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "lines": self.lines,
            "confidence": round(self.confidence, 4),
        }


_ENGINE = None
_ENGINE_ERROR: Optional[str] = None
_ENGINE_TRIED = False


def _get_engine():
    """Lazily build the RapidOCR engine once."""
    global _ENGINE, _ENGINE_ERROR, _ENGINE_TRIED
    if _ENGINE is not None:
        return _ENGINE
    if _ENGINE_TRIED:
        if _ENGINE_ERROR:
            raise OcrEngineError(_ENGINE_ERROR)
        raise OcrEngineError("OCR engine not available.")
    _ENGINE_TRIED = True
    try:
        from rapidocr_onnxruntime import RapidOCR
        _ENGINE = RapidOCR()
    except Exception as exc:  # noqa: BLE001 - wrap any init failure
        _ENGINE_ERROR = f"RapidOCR initialisation failed: {exc}"
        raise OcrEngineError(_ENGINE_ERROR) from exc
    return _ENGINE


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------

def gray(matrix: np.ndarray) -> np.ndarray:
    if matrix.ndim == 3:
        return cv2.cvtColor(matrix, cv2.COLOR_BGR2GRAY)
    return matrix


def denoise(matrix: np.ndarray) -> np.ndarray:
    return cv2.fastNlMeansDenoising(gray(matrix), None, 10, 7, 21)


def enhance_contrast(matrix: np.ndarray) -> np.ndarray:
    """CLAHE based contrast enhancement on the (gray) image."""
    # Assumes 2D input; if 3D, convert first
    if matrix.ndim == 3:
        matrix = cv2.cvtColor(matrix, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    return clahe.apply(matrix)


def upscale(matrix: np.ndarray, factor: float = 2.0) -> np.ndarray:
    h, w = matrix.shape[:2]
    if factor == 1.0 or h == 0 or w == 0:
        return matrix
    return cv2.resize(matrix, (int(w * factor), int(h * factor)),
                      interpolation=cv2.INTER_CUBIC)


def preprocess(matrix: np.ndarray) -> np.ndarray:
    """Standard preprocessing pipeline for passport/visa images."""
    if matrix is None or matrix.size == 0:
        raise ValueError("Empty image")
    g = gray(matrix)
    g = upscale(g, 2.0)
    g = denoise(g)
    g = enhance_contrast(g)
    return g


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def _line_texts(ocr_lines) -> list:
    """Normalise RapidOCR output into list of {text, conf, bbox}."""
    lines = []
    for item in ocr_lines or []:
        try:
            bbox, text, conf = item[0], item[1], float(item[2])
        except (IndexError, TypeError, ValueError):
            continue
        if not text:
            continue
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        lines.append({
            "text": text,
            "conf": round(conf, 4),
            "bbox": [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))],
        })
    return lines


def run_ocr(matrix: np.ndarray) -> OcrResult:
    """Run OCR on a raw image matrix (BGR or gray)."""
    engine = _get_engine()
    prep = preprocess(matrix)
    try:
        # RapidOCR can accept either a path or an ndarray.
        result, _elapse = engine(prep)
    except Exception as exc:  # noqa: BLE001
        raise OcrEngineError(f"RapidOCR inference failed: {exc}") from exc

    lines = _line_texts(result)
    words = []
    full_lines = []
    for ln in lines:
        full_lines.append(ln["text"])
        words.append({
            "text": ln["text"],
            "conf": ln["conf"],
            "bbox": ln["bbox"],
        })
    text = "\n".join(full_lines)

    # Sort lines visually (top to bottom, left to right) for readability.
    lines_sorted = sorted(lines, key=lambda l: (l["bbox"][1] // 30, l["bbox"][0]))
    text_sorted = "\n".join(l["text"] for l in lines_sorted)
    conf = sum(l["conf"] for l in lines) / len(lines) if lines else 0.0

    return OcrResult(text=text_sorted, lines=lines_sorted, words=words,
                     confidence=conf)


def run_ocr_from_bytes(data: bytes) -> OcrResult:
    """Decode bytes (JPEG/PNG/...) into a matrix and run OCR."""
    arr = np.frombuffer(data, dtype=np.uint8)
    matrix = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if matrix is None:
        matrix = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if matrix is None:
        raise ValueError("Unsupported or corrupt image data")
    return run_ocr(matrix)


# ---------------------------------------------------------------------------
# Field extraction heuristics
# ---------------------------------------------------------------------------

# Each entry maps a field to a list of regex patterns that locate the label.
# Patterns must end where the value begins so we can capture the remainder.
_KEYWORDS = OrderedDict([
    ("surname", [r"surname", r"family name", r"last name"]),
    ("given_names", [r"given names", r"given\s*names", r"first name", r"forenames"]),
    ("passport_number", [r"passport\s*no\.?", r"passport number", r"document\s*no\.?", r"passport\s*number"]),
    ("nationality", [r"nationality", r"citizenship"]),
    ("date_of_birth", [r"date of birth", r"dateofbirth", r"\bdob\b", r"\bborn\b"]),
    ("sex", [r"\bsex\b", r"gender"]),
    ("date_of_issue", [r"date of issue", r"issue date", r"issued on", r"date of issue']"]),
    ("date_of_expiry", [r"date of expiry", r"expiry date", r"date of expiration", r"valid until", r"\bexpires\b", r"valid until:"]),
    ("issuing_country", [r"issuing country", r"country of issue", r"issuer"]),
    ("visa_number", [r"visa\s*no\.?", r"visa number"]),
    ("visa_type", [r"visa type", r"type of visa"]),
    ("number_of_entries", [r"entries", r"number of entries"]),
])


def _clean_value(value: str) -> str:
    value = value.strip(" :\t|-_/\u00a0<>\"'.,;")
    value = re.sub(r"\s{2,}", " ", value)
    return value[:60]


def extract_fields(text: str) -> dict:
    """Best-effort structured field extraction from free OCR text.

    Returns a dict of field -> {value, confidence}. Values are rough and are
    intended to be cross-checked against the (authoritative) MRZ zone.
    """
    fields = {k: {"value": None, "confidence": 0.0} for k in _KEYWORDS}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    for key, patterns in _KEYWORDS.items():
        for ln in lines:
            for pat in patterns:
                # find label anywhere; capture everything after it as the value
                m = re.search(pat, ln, flags=re.IGNORECASE)
                if not m:
                    continue
                remainder = ln[m.end():]
                remainder = _clean_value(remainder)
                # Skip pure label-noise lines
                if remainder and not re.match(r"^[:\-_.|]+$", remainder):
                    fields[key] = {"value": remainder, "confidence": 0.78}
                    break
            if fields[key]["value"] is not None:
                break
    return fields


def detect_document_type(text: str) -> str:
    """Heuristic document type from OCR text."""
    low = text.lower()
    if "visa" in low or "visto" in low:
        return "visa"
    if "passport" in low or "passeport" in low or "reiseausweis" in low:
        return "passport"
    return "unknown"
